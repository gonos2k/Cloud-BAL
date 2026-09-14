"""Independent NumPy reference for the pressure-fixed radar reconstruction.

This module deliberately does not import the Fortran implementation.  It is a
small, array-oriented statement of the equations in ``cloud_bal_column_physics``:
the radar field is diagnosed into fresh hydrometeors, then transported once as
integrated cell rates.  It is a steady reconstruction, not source-removing
time transport. Each layer segment freezes source wind, fall speed and transit
time; source rates are distributed only at their straight-line endpoints. This
reference evaluates that endpoint analytically, independently of production's
bounded continuous-position stepping. It does not integrate within-layer shear.

All three-dimensional inputs use ``(z, y, x)`` order.  ``z=0`` is the pressure
lowest pressure level and pressure decreases with increasing ``z``.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from math import ceil, floor, log10, sqrt
from typing import Any, Mapping

import numpy as np


# The values are intentionally repeated here: this file is an independent
# numerical reference, not a wrapper around a production helper.
GRAVITY = 9.80665
RD_AIR = 287.05
EPSILON_WATER = 0.622
MIN_PRESSURE_PA = 100.0
MAX_PRESSURE_PA = 120000.0
MIN_TEMPERATURE_K = 150.0
MAX_TEMPERATURE_K = 350.0

PHASE_UNKNOWN = 0
PHASE_RAIN = 1
PHASE_SNOW = 2
PHASE_FREEZING_RAIN = 3
PHASE_SLEET = 4
PHASE_GRAUPEL = 5

MISSING_PHASE_ALL_SNOW_K = 268.15
MISSING_PHASE_ALL_RAIN_K = 275.15


class RadarReferenceError(ValueError):
    """An input-contract or numerical-kernel failure in the reference."""

    def __init__(self, message: str, ledger: "PrecipitationLedger | None" = None):
        super().__init__(message)
        self.ledger = ledger


@dataclass(frozen=True)
class RadarReferenceConfig:
    """Numerical constants shared with the current pressure-fixed path."""

    cloud_fraction_threshold: float = 0.01
    radar_wavelength_m: float = 0.10
    minimum_dbz: float = 0.0
    maximum_dbz: float = 80.0
    reference_mass_concentration: float = 1.0e-4
    minimum_relative_fall_speed: float = 0.30
    maximum_horizontal_substep: float = 0.75
    maximum_transport_substeps: int = 64
    precipitation_loading_efficiency: float = 0.08
    maximum_downdraft_ms: float = 3.0
    maximum_downdraft_innovation_ms: float = 2.0
    ledger_relative_tolerance: float = 1.0e-11
    ledger_absolute_tolerance: float = 1.0e-13


@dataclass
class PrecipitationLedger:
    """The seven terminal ledger categories plus input and substep maximum."""

    input: float = 0.0
    deposited: float = 0.0
    suspended: float = 0.0
    boundary_exit: float = 0.0
    terrain_intercept: float = 0.0
    observation_blocked: float = 0.0
    no_echo_blocked: float = 0.0
    microphysical_loss: float = 0.0
    maximum_required_substeps: int = 0


@dataclass
class RadarReferenceResult:
    """Fresh radar map and transport accounting before state publication."""

    rain: np.ndarray
    snow: np.ndarray
    graupel: np.ndarray
    zlinear: np.ndarray
    phase: np.ndarray
    phase_uncertain: np.ndarray
    w: np.ndarray
    ledger: PrecipitationLedger
    pressure_interface: np.ndarray
    level_spacing_dp: np.ndarray

def _config(config: RadarReferenceConfig | Mapping[str, Any] | Any | None) -> RadarReferenceConfig:
    if config is None:
        return RadarReferenceConfig()
    if isinstance(config, RadarReferenceConfig):
        result = config
    elif isinstance(config, Mapping):
        names = {field.name for field in fields(RadarReferenceConfig)}
        unknown = set(config) - names
        if unknown:
            raise RadarReferenceError(f"unknown configuration keys: {sorted(unknown)}")
        result = RadarReferenceConfig(**{name: config[name] for name in names if name in config})
    else:
        raise RadarReferenceError("config must be RadarReferenceConfig, a mapping, or None")
    _validate_config(result)
    return result


def _validate_config(config: RadarReferenceConfig) -> None:
    finite_names = (
        "cloud_fraction_threshold", "radar_wavelength_m", "minimum_dbz",
        "maximum_dbz", "reference_mass_concentration",
        "minimum_relative_fall_speed", "maximum_horizontal_substep",
        "precipitation_loading_efficiency", "maximum_downdraft_ms",
        "maximum_downdraft_innovation_ms", "ledger_relative_tolerance",
        "ledger_absolute_tolerance",
    )
    if any(not np.isfinite(float(getattr(config, name))) for name in finite_names):
        raise RadarReferenceError("configuration contains a non-finite value")
    if not 0.0 <= config.cloud_fraction_threshold <= 1.0:
        raise RadarReferenceError("cloud_fraction_threshold must be in [0, 1]")
    if not 0.08 <= config.radar_wavelength_m <= 0.12:
        raise RadarReferenceError("radar_wavelength_m must be in [0.08, 0.12] m")
    if config.minimum_dbz < -100.0 or config.maximum_dbz <= config.minimum_dbz:
        raise RadarReferenceError("invalid reflectivity bounds")
    if config.maximum_dbz > 100.0 or config.reference_mass_concentration <= 0.0:
        raise RadarReferenceError("invalid reflectivity/mass configuration")
    if config.minimum_relative_fall_speed <= 0.0:
        raise RadarReferenceError("minimum_relative_fall_speed must be positive")
    if not 0.0 < config.maximum_horizontal_substep <= 1.0:
        raise RadarReferenceError("maximum_horizontal_substep must be in (0, 1]")
    if not 0 < int(config.maximum_transport_substeps) <= 256:
        raise RadarReferenceError("maximum_transport_substeps must be in [1, 256]")
    if not 0.0 <= config.precipitation_loading_efficiency <= 1.0:
        raise RadarReferenceError("invalid precipitation_loading_efficiency")
    if config.maximum_downdraft_ms <= 0.0 or config.maximum_downdraft_innovation_ms <= 0.0:
        raise RadarReferenceError("downdraft speed limits must be positive")
    if not 0.0 <= config.ledger_relative_tolerance <= 1.0e-6:
        raise RadarReferenceError("invalid ledger relative tolerance")
    if not 0.0 <= config.ledger_absolute_tolerance <= 1.0e-6:
        raise RadarReferenceError("invalid ledger absolute tolerance")


def _array(value: Any, name: str, dtype: Any = np.float64) -> np.ndarray:
    result = np.asarray(value, dtype=dtype)
    if np.ma.isMaskedArray(value) and np.any(np.ma.getmaskarray(value)):
        raise RadarReferenceError(f"{name}: masked input")
    if not np.all(np.isfinite(result)):
        raise RadarReferenceError(f"{name}: non-finite input")
    return result


def _bool_array(value: Any, name: str, shape: tuple[int, ...]) -> np.ndarray:
    result = np.asarray(value, dtype=bool)
    if result.shape != shape:
        raise RadarReferenceError(f"{name}: expected shape {shape}, got {result.shape}")
    return result.copy()


def _validate_inputs(
    pressure: Any, temperature: Any, vapor: Any, u: Any, v: Any, omega: Any,
    dx: Any, dy: Any, pressure_surface: Any, above: Any, domain: Any,
    radar_observed: Any, radar_no_echo: Any, radar_dbz: Any,
) -> tuple[dict[str, np.ndarray], tuple[int, int, int]]:
    arrays = {
        name: _array(value, name)
        for name, value in {
            "pressure": pressure, "temperature": temperature, "vapor": vapor,
            "u": u, "v": v, "omega": omega, "dx": dx, "dy": dy,
            "pressure_surface": pressure_surface, "radar_dbz": radar_dbz,
        }.items()
    }
    p = arrays["pressure"]
    if p.ndim != 3:
        raise RadarReferenceError("pressure: expected a 3-D (z, y, x) array")
    nz, ny, nx = p.shape
    if min(nz, ny, nx) < 1 or nz < 2:
        raise RadarReferenceError("pressure: at least two vertical levels are required")
    shape = (nz, ny, nx)
    for name in ("temperature", "vapor", "u", "v", "omega", "radar_dbz"):
        if arrays[name].shape != shape:
            raise RadarReferenceError(f"{name}: expected shape {shape}")
    horizontal_shape = (ny, nx)
    for name in ("dx", "dy", "pressure_surface"):
        if arrays[name].shape != horizontal_shape:
            raise RadarReferenceError(f"{name}: expected shape {horizontal_shape}")
    above_array = _bool_array(above, "above", shape)
    domain_array = _bool_array(domain, "domain", shape)
    observed_array = _bool_array(radar_observed, "radar_observed", shape)
    no_echo_array = _bool_array(radar_no_echo, "radar_no_echo", shape)
    arrays.update({
        "above": above_array, "domain": domain_array,
        "radar_observed": observed_array, "radar_no_echo": no_echo_array,
    })

    if np.any(arrays["dx"] <= 0.0) or np.any(arrays["dy"] <= 0.0):
        raise RadarReferenceError("dx/dy must be positive")
    # Production trajectory coordinates are grid-index coordinates.  The
    # current contract therefore requires a uniform metric, even though this
    # API keeps the (y, x) array shape for explicitness.
    dx0, dy0 = arrays["dx"][0, 0], arrays["dy"][0, 0]
    tolerance = 64.0 * np.finfo(np.float64).eps
    if not np.all(np.abs(arrays["dx"] - dx0) <= tolerance * abs(dx0)):
        raise RadarReferenceError("dx must be uniform for index-coordinate transport")
    if not np.all(np.abs(arrays["dy"] - dy0) <= tolerance * abs(dy0)):
        raise RadarReferenceError("dy must be uniform for index-coordinate transport")
    if np.any(arrays["dx"] < 1.0) or np.any(arrays["dx"] > 1.0e6):
        raise RadarReferenceError("dx outside production transport bounds")
    if np.any(arrays["dy"] < 1.0) or np.any(arrays["dy"] > 1.0e6):
        raise RadarReferenceError("dy outside production transport bounds")
    if np.any(p < MIN_PRESSURE_PA) or np.any(p > MAX_PRESSURE_PA):
        raise RadarReferenceError("pressure outside [100, 120000] Pa")
    if np.any(p[:-1] <= p[1:]):
        raise RadarReferenceError("pressure must strictly decrease with z")
    ps = arrays["pressure_surface"]
    if np.any(ps < MIN_PRESSURE_PA) or np.any(ps > MAX_PRESSURE_PA):
        raise RadarReferenceError("pressure_surface outside [100, 120000] Pa")
    if not np.any(above_array) or not np.any(domain_array):
        raise RadarReferenceError("above/domain must contain at least one active cell")
    if np.any(domain_array & ~above_array):
        raise RadarReferenceError("domain must be a subset of above")
    if np.any(observed_array & ~domain_array):
        raise RadarReferenceError("radar observations must lie inside domain")
    if np.any(no_echo_array & ~domain_array):
        raise RadarReferenceError("no-echo coverage must lie inside domain")
    if np.any(observed_array & no_echo_array):
        raise RadarReferenceError("radar observed and no-echo masks overlap")
    if np.any(observed_array & ~np.isfinite(arrays["radar_dbz"])):
        raise RadarReferenceError("observed radar dBZ must be finite")
    if not np.all(np.isfinite(arrays["radar_dbz"])):
        # Inactive cells carry no radar authority and are not used in the
        # reconstruction.  Replace their payload by a harmless marker.
        arrays["radar_dbz"] = np.where(np.isfinite(arrays["radar_dbz"]), arrays["radar_dbz"], 0.0)

    for mask_name in ("above", "domain"):
        mask = arrays[mask_name]
        if np.any(mask[:-1] & ~mask[1:]):
            raise RadarReferenceError(f"{mask_name}: active levels must be contiguous from the surface")
    if np.any(above_array & ((arrays["temperature"] < MIN_TEMPERATURE_K) |
                             (arrays["temperature"] > MAX_TEMPERATURE_K))):
        raise RadarReferenceError("active temperature outside [150, 350] K")
    if np.any(above_array & ((arrays["vapor"] < 0.0) | (arrays["vapor"] > 0.2))):
        raise RadarReferenceError("active vapor mixing ratio outside [0, 0.2]")
    if np.any(~np.isfinite(arrays["u"])) or np.any(~np.isfinite(arrays["v"])):
        raise RadarReferenceError("u/v must be finite")
    if np.any(above_array & ((np.abs(arrays["u"]) > 200.0) |
                             (np.abs(arrays["v"]) > 200.0))):
        raise RadarReferenceError("active horizontal wind outside +/-200 m/s")
    if np.any(above_array & ((np.abs(arrays["omega"]) > 1.0e9))):
        raise RadarReferenceError("active omega is outside the finite transport range")
    return arrays, shape


def _pressure_geometry(
    pressure: np.ndarray, pressure_surface: np.ndarray, above: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    nz, ny, nx = pressure.shape
    interfaces = np.zeros((nz + 1, ny, nx), dtype=np.float64)
    spacing = pressure[:-1] - pressure[1:]
    for y in range(ny):
        for x in range(nx):
            active = np.flatnonzero(above[:, y, x])
            if active.size == 0:
                raise RadarReferenceError("pressure geometry has an empty column")
            bottom = int(active[0])
            pressure_bottom = np.flatnonzero(pressure[:, y, x] <= pressure_surface[y, x])
            if pressure_bottom.size == 0 or bottom < int(pressure_bottom[0]) or bottom - int(pressure_bottom[0]) > 1:
                raise RadarReferenceError("above/pressure_surface terrain clip is inconsistent")
            if np.any(pressure[active, y, x] > pressure_surface[y, x]):
                raise RadarReferenceError("active pressure center exceeds pressure_surface")
            interfaces[0, y, x] = pressure_surface[y, x]
            for fk in range(1, nz):  # Fortran interface k=2,...,nz.
                interfaces[fk, y, x] = (
                    pressure_surface[y, x] if fk <= bottom
                    else 0.5 * (pressure[fk - 1, y, x] + pressure[fk, y, x])
                )
            top = pressure[-1, y, x] - 0.5 * spacing[-1, y, x]
            interfaces[-1, y, x] = min(pressure_surface[y, x], top)
            active_dp = interfaces[:-1, y, x] - interfaces[1:, y, x]
            if np.any(active_dp[above[:, y, x]] <= 0.0):
                raise RadarReferenceError("active pressure geometry has nonpositive cell thickness")
            if np.any(~above[:, y, x] & (np.abs(active_dp) > 64.0 * np.finfo(float).eps * max(1.0, pressure_surface[y, x]))):
                raise RadarReferenceError("inactive pressure geometry is not zero-thickness")
    return interfaces, spacing


def dry_air_density(pressure: float, temperature: float, vapor: float) -> float:
    """Dry-air density for vapor mixing ratio in kg/kg dry air."""

    if not all(np.isfinite(value) for value in (pressure, temperature, vapor)):
        return -1.0
    if not (MIN_PRESSURE_PA <= pressure <= MAX_PRESSURE_PA and
            MIN_TEMPERATURE_K <= temperature <= MAX_TEMPERATURE_K and
            0.0 <= vapor <= 0.2):
        return -1.0
    return pressure / (RD_AIR * temperature * (1.0 + vapor / EPSILON_WATER))


def moist_gas_density(pressure: float, temperature: float, vapor: float) -> float:
    dry = dry_air_density(pressure, temperature, vapor)
    return dry * (1.0 + vapor) if dry > 0.0 else -1.0


def omega_to_w(omega: np.ndarray, pressure: np.ndarray, temperature: np.ndarray,
               vapor: np.ndarray, valid: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Apply the declared omega approximation, including float32 w storage."""

    if not (pressure.shape == temperature.shape == vapor.shape == omega.shape):
        raise RadarReferenceError("omega_to_w arrays must have matching shape")
    if valid is None:
        valid = np.ones(pressure.shape, dtype=bool)
    w = np.zeros(pressure.shape, dtype=np.float32)
    w_valid = np.zeros(pressure.shape, dtype=bool)
    for index in zip(*np.where(valid)):
        z, y, x = index
        rho = moist_gas_density(float(pressure[index]), float(temperature[index]), float(vapor[index]))
        if rho <= 0.0 or not np.isfinite(omega[index]):
            raise RadarReferenceError("cannot convert omega at a required active cell")
        w[index] = -float(omega[index]) / (rho * GRAVITY)
        if not np.isfinite(w[index]):
            raise RadarReferenceError("omega_to_w produced a non-finite velocity")
        w_valid[index] = True
    return w, w_valid


def missing_phase_partition(temperature: float) -> tuple[float, float, float]:
    if not np.isfinite(temperature) or not MIN_TEMPERATURE_K <= temperature <= MAX_TEMPERATURE_K:
        raise RadarReferenceError("phase-partition temperature outside [150, 350] K")
    scaled = np.clip(
        (temperature - MISSING_PHASE_ALL_SNOW_K) /
        (MISSING_PHASE_ALL_RAIN_K - MISSING_PHASE_ALL_SNOW_K), 0.0, 1.0,
    )
    liquid = scaled * scaled * (3.0 - 2.0 * scaled)
    return float(liquid), float(1.0 - liquid), 0.0


def allocate_precipitation_phase(total: float, temperature: float, phase: int) -> tuple[float, float, float]:
    if not np.isfinite(total) or not np.isfinite(temperature) or total < 0.0:
        raise RadarReferenceError("invalid fresh precipitation mass")
    if not MIN_TEMPERATURE_K <= temperature <= MAX_TEMPERATURE_K:
        raise RadarReferenceError("fresh precipitation temperature outside [150, 350] K")
    if phase == PHASE_RAIN:
        parts = (total, 0.0, 0.0)
    elif phase == PHASE_SNOW:
        parts = (0.0, total, 0.0)
    elif phase == PHASE_FREEZING_RAIN:
        parts = (0.75 * total, 0.0, 0.25 * total)
    elif phase == PHASE_SLEET:
        parts = (0.0, 0.50 * total, 0.50 * total)
    elif phase == PHASE_GRAUPEL:
        parts = (0.0, 0.0, total)
    elif phase == PHASE_UNKNOWN:
        rain_fraction, snow_fraction, graupel_fraction = missing_phase_partition(temperature)
        parts = (rain_fraction * total, snow_fraction * total, graupel_fraction * total)
    else:
        raise RadarReferenceError(f"invalid precipitation phase code: {phase}")
    if abs(sum(parts) - total) > 16.0 * np.finfo(float).eps * max(total, np.finfo(float).tiny):
        raise RadarReferenceError("phase allocation does not close")
    return parts


def _bounded_terminal_speed(base: float, density_ratio: float) -> float:
    return float(np.clip(base / sqrt(max(density_ratio, 1.0e-4)), 0.1, 20.0))


def terminal_velocity(phase: int, pressure_pa: float, temperature_k: float, dbz: float) -> float:
    if not all(np.isfinite(value) for value in (pressure_pa, temperature_k, dbz)):
        raise RadarReferenceError("non-finite terminal-velocity input")
    if not (MIN_PRESSURE_PA <= pressure_pa <= MAX_PRESSURE_PA and
            temperature_k > MIN_TEMPERATURE_K and temperature_k <= MAX_TEMPERATURE_K and
            -100.0 <= dbz <= 100.0):
        raise RadarReferenceError("terminal-velocity input outside production bounds")
    zlinear = 10.0 ** (0.1 * dbz)
    density_ratio = (pressure_pa / 101300.0) * (273.15 / temperature_k)
    rain_speed = _bounded_terminal_speed(4.32 * zlinear ** (1.0 / 14.0), density_ratio)
    snow_speed = _bounded_terminal_speed(min(2.5, 0.80 + 0.12 * zlinear ** 0.10), density_ratio)
    graupel_speed = _bounded_terminal_speed(min(15.0, 7.0 + 0.30 * zlinear ** 0.08), density_ratio)
    if phase in (PHASE_RAIN, PHASE_FREEZING_RAIN, PHASE_SLEET):
        return rain_speed
    if phase == PHASE_SNOW:
        return snow_speed
    if phase == PHASE_GRAUPEL:
        return graupel_speed
    if phase == PHASE_UNKNOWN:
        rain_fraction, snow_fraction, graupel_fraction = missing_phase_partition(temperature_k)
        return rain_fraction * rain_speed + snow_fraction * snow_speed + graupel_fraction * graupel_speed
    raise RadarReferenceError(f"invalid precipitation phase code: {phase}")


def _diagnose_radar(
    pressure: np.ndarray, temperature: np.ndarray, vapor: np.ndarray,
    observed: np.ndarray, dbz: np.ndarray, phase_input: np.ndarray | None,
    config: RadarReferenceConfig,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    shape = pressure.shape
    phase = np.zeros(shape, dtype=np.int64)
    uncertain = np.zeros(shape, dtype=bool)
    zlinear = np.zeros(shape, dtype=np.float64)
    rain = np.zeros(shape, dtype=np.float64)
    snow = np.zeros(shape, dtype=np.float64)
    graupel = np.zeros(shape, dtype=np.float64)
    if phase_input is not None:
        if phase_input.shape != shape:
            raise RadarReferenceError("phase: expected the pressure shape")
        if (np.any(~np.isfinite(phase_input)) or
                np.any(phase_input != np.floor(phase_input)) or
                np.any((phase_input < PHASE_UNKNOWN) | (phase_input > PHASE_GRAUPEL))):
            raise RadarReferenceError("phase codes must be integer values in [0, 5]")
        phase[observed] = phase_input[observed].astype(np.int64)
    for z, y, x in zip(*np.where(observed)):
        dbz_value = float(dbz[z, y, x])
        if not config.minimum_dbz <= dbz_value <= config.maximum_dbz:
            raise RadarReferenceError("observed radar dBZ outside configured bounds")
        z_value = 10.0 ** (0.1 * dbz_value)
        zlinear[z, y, x] = z_value
        if phase[z, y, x] == PHASE_UNKNOWN:
            uncertain[z, y, x] = True
        rho = dry_air_density(float(pressure[z, y, x]), float(temperature[z, y, x]), float(vapor[z, y, x]))
        if rho <= 0.0:
            raise RadarReferenceError("invalid dry-air density at observed radar cell")
        total = config.reference_mass_concentration * (z_value / 1000.0) ** 0.55 / rho
        total = min(0.02 / rho, max(0.0, total))
        rain[z, y, x], snow[z, y, x], graupel[z, y, x] = allocate_precipitation_phase(
            total, float(temperature[z, y, x]), int(phase[z, y, x])
        )
        if sum(value > 0.0 for value in (rain[z, y, x], snow[z, y, x], graupel[z, y, x])) > 1:
            uncertain[z, y, x] = True
    return phase, uncertain, zlinear, rain, snow, graupel


def _layer_separation(
    pressure: np.ndarray, temperature: np.ndarray, vapor: np.ndarray,
    interfaces: np.ndarray, domain: np.ndarray, k: int, y: int, x: int,
) -> float:
    rho = moist_gas_density(float(pressure[k, y, x]), float(temperature[k, y, x]), float(vapor[k, y, x]))
    if rho <= 0.0:
        raise RadarReferenceError("invalid moist-gas density in layer separation")
    pressure_separation = (
        float(pressure[k - 1, y, x] - pressure[k, y, x])
        if domain[k - 1, y, x]
        else float(interfaces[k, y, x] - pressure[k, y, x])
    )
    return pressure_separation / (rho * GRAVITY)


def _scatter(
    flux: np.ndarray, zflux: np.ndarray, xstep: np.ndarray, ystep: np.ndarray,
    dx: float, dy: float, ledger: PrecipitationLedger,
) -> tuple[np.ndarray, np.ndarray]:
    # dx/dy are intentionally parameters to make the metric dependency clear;
    # index-space displacements have already divided by them in the caller.
    del dx, dy
    ny, nx = flux.shape
    next_flux = np.zeros_like(flux)
    next_zflux = np.zeros_like(zflux)
    for y, x in zip(*np.where(flux > 0.0)):
        target_x = (x + 1.0) + xstep[y, x]
        target_y = (y + 1.0) + ystep[y, x]
        base_x = floor(target_x) - 1
        base_y = floor(target_y) - 1
        fx = target_x - floor(target_x)
        fy = target_y - floor(target_y)
        for dy_offset in (0, 1):
            for dx_offset in (0, 1):
                weight = ((1.0 - fx) if dx_offset == 0 else fx) * ((1.0 - fy) if dy_offset == 0 else fy)
                yy, xx = base_y + dy_offset, base_x + dx_offset
                if yy < 0 or yy >= ny or xx < 0 or xx >= nx:
                    ledger.boundary_exit += weight * flux[y, x]
                else:
                    next_flux[yy, xx] += weight * flux[y, x]
                    next_zflux[yy, xx] += weight * zflux[y, x]
    return next_flux, next_zflux


def _transport_phase_level(
    *, k: int, phase_code: int, pressure: np.ndarray, temperature: np.ndarray,
    vapor: np.ndarray, u: np.ndarray, v: np.ndarray, w: np.ndarray,
    interfaces: np.ndarray, dx: float, dy: float, domain: np.ndarray,
    observed: np.ndarray, no_echo: np.ndarray, zlinear: np.ndarray,
    q: np.ndarray, config: RadarReferenceConfig, ledger: PrecipitationLedger,
) -> tuple[np.ndarray, np.ndarray]:
    ny, nx = pressure.shape[1:]
    flux = np.zeros((ny, nx), dtype=np.float64)
    zflux = np.zeros((ny, nx), dtype=np.float64)
    xstep = np.zeros((ny, nx), dtype=np.float64)
    ystep = np.zeros((ny, nx), dtype=np.float64)
    max_displacement = 0.0
    for y, x in zip(*np.where(q[k] > 0.0)):
        rho_source = dry_air_density(float(pressure[k, y, x]), float(temperature[k, y, x]), float(vapor[k, y, x]))
        if rho_source <= 0.0:
            raise RadarReferenceError("invalid source dry-air density", ledger)
        source_dbz = max(config.minimum_dbz, 10.0 * log10(max(float(zlinear[k, y, x]), 1.0e-12)))
        vt = terminal_velocity(phase_code, float(pressure[k, y, x]), float(temperature[k, y, x]), source_dbz)
        relative = vt - float(w[k, y, x])
        source_flux = rho_source * float(q[k, y, x]) * max(relative, 0.0) * dx * dy
        if relative <= config.minimum_relative_fall_speed:
            ledger.input += source_flux
            ledger.suspended += source_flux
            continue
        dz = _layer_separation(pressure, temperature, vapor, interfaces, domain, k, y, x)
        if dz < 0.0:
            raise RadarReferenceError("negative pressure-layer separation", ledger)
        dt = dz / relative
        xstep[y, x] = float(u[k, y, x]) * dt / dx
        ystep[y, x] = float(v[k, y, x]) * dt / dy
        if not np.isfinite(xstep[y, x]) or not np.isfinite(ystep[y, x]):
            raise RadarReferenceError("non-finite trajectory displacement", ledger)
        max_displacement = max(max_displacement, abs(xstep[y, x]), abs(ystep[y, x]))
        flux[y, x] = source_flux
        zflux[y, x] = source_flux * max(float(zlinear[k, y, x]), 1.0e-12)
    input_level = float(np.sum(flux, dtype=np.float64))
    ledger.input += input_level
    if input_level <= 0.0:
        return np.zeros((ny, nx)), np.zeros((ny, nx))
    if max_displacement > config.maximum_horizontal_substep * config.maximum_transport_substeps:
        ledger.maximum_required_substeps = max(
            ledger.maximum_required_substeps,
            int(ceil(max_displacement / config.maximum_horizontal_substep)),
        )
        raise RadarReferenceError("required transport substeps exceed configured cap", ledger)
    nsub = max(1, int(ceil(max_displacement / config.maximum_horizontal_substep)))
    ledger.maximum_required_substeps = max(ledger.maximum_required_substeps, nsub)
    if nsub > config.maximum_transport_substeps:
        raise RadarReferenceError("required transport substeps exceed configured cap", ledger)
    # Analytic endpoint of the frozen-source layer segment. Production advances
    # continuous source positions in bounded substeps; no intermediate remap or
    # velocity mixing is part of this reconstruction contract.
    flux, zflux = _scatter(flux, zflux, xstep, ystep, dx, dy, ledger)

    deposited_rate = np.zeros((ny, nx), dtype=np.float64)
    deposited_zrate = np.zeros((ny, nx), dtype=np.float64)
    for y, x in zip(*np.where(flux > 0.0)):
        amount = float(flux[y, x])
        if not domain[k - 1, y, x]:
            ledger.terrain_intercept += amount
            continue
        if observed[k - 1, y, x]:
            ledger.observation_blocked += amount
            continue
        if no_echo[k - 1, y, x]:
            ledger.no_echo_blocked += amount
            continue
        zratio = max(float(zflux[y, x] / amount), 1.0e-12)
        target_dbz = 10.0 * log10(zratio)
        vt = terminal_velocity(phase_code, float(pressure[k - 1, y, x]),
                               float(temperature[k - 1, y, x]), target_dbz)
        rho_target = dry_air_density(float(pressure[k - 1, y, x]),
                                     float(temperature[k - 1, y, x]),
                                     float(vapor[k - 1, y, x]))
        if rho_target <= 0.0:
            raise RadarReferenceError("invalid target dry-air density", ledger)
        target_relative = vt - float(w[k - 1, y, x])
        if target_relative <= config.minimum_relative_fall_speed:
            ledger.suspended += amount
            continue
        q[k - 1, y, x] += amount / (dx * dy * rho_target * target_relative)
        deposited_rate[y, x] += amount
        deposited_zrate[y, x] += float(zflux[y, x])
        ledger.deposited += amount
    return deposited_rate, deposited_zrate


def _transport(
    *, pressure: np.ndarray, temperature: np.ndarray, vapor: np.ndarray,
    u: np.ndarray, v: np.ndarray, w: np.ndarray, dx: float, dy: float,
    interfaces: np.ndarray, domain: np.ndarray, observed: np.ndarray,
    no_echo: np.ndarray, phase: np.ndarray, zlinear: np.ndarray,
    rain: np.ndarray, snow: np.ndarray, graupel: np.ndarray,
    config: RadarReferenceConfig,
) -> PrecipitationLedger:
    _validate_transport_fields(
        pressure=pressure, temperature=temperature, vapor=vapor, u=u, v=v, w=w,
        domain=domain, phase=phase, zlinear=zlinear, rain=rain, snow=snow,
        graupel=graupel, config=config)
    if np.any(no_echo & ((zlinear > 0.0) | (rain > 0.0) | (snow > 0.0) | (graupel > 0.0))):
        raise RadarReferenceError("no-echo cell contains fresh radar material")
    ledger = PrecipitationLedger()
    phase_work = phase.copy()
    z_work = zlinear.copy()
    rain_work, snow_work, graupel_work = rain.copy(), snow.copy(), graupel.copy()
    nz, ny, nx = pressure.shape
    for k in range(nz - 1, 0, -1):
        deposited_rate = np.zeros((ny, nx), dtype=np.float64)
        deposited_zrate = np.zeros((ny, nx), dtype=np.float64)
        for phase_code, q_work in ((PHASE_RAIN, rain_work), (PHASE_SNOW, snow_work), (PHASE_GRAUPEL, graupel_work)):
            phase_rate, phase_zrate = _transport_phase_level(
                k=k, phase_code=phase_code, pressure=pressure, temperature=temperature,
                vapor=vapor, u=u, v=v, w=w, interfaces=interfaces, dx=dx, dy=dy,
                domain=domain, observed=observed, no_echo=no_echo, zlinear=z_work,
                q=q_work, config=config, ledger=ledger,
            )
            deposited_rate += phase_rate
            deposited_zrate += phase_zrate
        for y, x in zip(*np.where((deposited_rate > 0.0) & ~observed[k - 1])):
            z_work[k - 1, y, x] = deposited_zrate[y, x] / deposited_rate[y, x]
            nphase = int(rain_work[k - 1, y, x] > 0.0) + int(snow_work[k - 1, y, x] > 0.0) + int(graupel_work[k - 1, y, x] > 0.0)
            if nphase != 1:
                phase_work[k - 1, y, x] = PHASE_UNKNOWN
            elif rain_work[k - 1, y, x] > 0.0:
                phase_work[k - 1, y, x] = PHASE_RAIN
            elif snow_work[k - 1, y, x] > 0.0:
                phase_work[k - 1, y, x] = PHASE_SNOW
            else:
                phase_work[k - 1, y, x] = PHASE_GRAUPEL

    # The bottom-level q is an instantaneous represented mass; account it as a
    # boundary rate exactly once, after all upper-level descendants arrive.
    for y in range(ny):
        for x in range(nx):
            for phase_code, q_work in ((PHASE_RAIN, rain_work), (PHASE_SNOW, snow_work), (PHASE_GRAUPEL, graupel_work)):
                q_value = float(q_work[0, y, x])
                if q_value <= 0.0:
                    continue
                rho = dry_air_density(float(pressure[0, y, x]), float(temperature[0, y, x]), float(vapor[0, y, x]))
                if rho <= 0.0:
                    raise RadarReferenceError("invalid bottom dry-air density", ledger)
                dbz = 10.0 * log10(max(float(z_work[0, y, x]), 10.0 ** (0.1 * config.minimum_dbz)))
                vt = terminal_velocity(phase_code, float(pressure[0, y, x]), float(temperature[0, y, x]), dbz)
                relative = vt - float(w[0, y, x])
                flux = rho * q_value * max(relative, 0.0) * dx * dy
                ledger.input += flux
                if relative <= config.minimum_relative_fall_speed:
                    ledger.suspended += flux
                else:
                    ledger.boundary_exit += flux
    if not _ledger_closes(ledger, config):
        raise RadarReferenceError("precipitation ledger does not close", ledger)
    _validate_transport_fields(
        pressure=pressure, temperature=temperature, vapor=vapor, u=u, v=v, w=w,
        domain=domain, phase=phase_work, zlinear=z_work, rain=rain_work, snow=snow_work,
        graupel=graupel_work, config=config)
    rain[...] = rain_work
    snow[...] = snow_work
    graupel[...] = graupel_work
    zlinear[...] = z_work
    phase[...] = phase_work
    return ledger


def _validate_transport_fields(
    *, pressure: np.ndarray, temperature: np.ndarray, vapor: np.ndarray,
    u: np.ndarray, v: np.ndarray, w: np.ndarray, domain: np.ndarray,
    phase: np.ndarray, zlinear: np.ndarray, rain: np.ndarray,
    snow: np.ndarray, graupel: np.ndarray, config: RadarReferenceConfig,
) -> None:
    """Mirror the production transport-values gate before running the kernel."""

    if any(value.shape != pressure.shape for value in (temperature, vapor, u, v, w, domain, phase, zlinear, rain, snow, graupel)):
        raise RadarReferenceError("transport arrays do not have one common shape")
    if np.any(~np.isfinite(pressure)) or np.any(~np.isfinite(temperature)) or np.any(~np.isfinite(vapor)):
        raise RadarReferenceError("transport thermodynamics are non-finite")
    if np.any(~np.isfinite(u)) or np.any(~np.isfinite(v)) or np.any(~np.isfinite(w)):
        raise RadarReferenceError("transport winds are non-finite")
    if np.any(domain & ((pressure < MIN_PRESSURE_PA) | (pressure > MAX_PRESSURE_PA))):
        raise RadarReferenceError("transport pressure outside production bounds")
    if np.any(domain & ((temperature < MIN_TEMPERATURE_K) | (temperature > MAX_TEMPERATURE_K))):
        raise RadarReferenceError("transport temperature outside production bounds")
    if np.any(domain & ((vapor < 0.0) | (vapor > 0.2))):
        raise RadarReferenceError("transport vapor outside production bounds")
    if np.any(domain & ((np.abs(u) > 200.0) | (np.abs(v) > 200.0) | (np.abs(w) > 200.0))):
        raise RadarReferenceError("transport wind outside production bounds")
    maximum_zlinear = 10.0 ** (0.1 * config.maximum_dbz)
    if np.any(~np.isfinite(zlinear)) or np.any(zlinear < 0.0) or np.any(zlinear > maximum_zlinear * (1.0 + 64.0 * np.finfo(float).eps)):
        raise RadarReferenceError("transport reflectivity outside configured bounds")
    for name, value in (("rain", rain), ("snow", snow), ("graupel", graupel)):
        if np.any(~np.isfinite(value)) or np.any(value < 0.0) or np.any(value > 1.0):
            raise RadarReferenceError(f"transport {name} outside [0, 1]")
        if np.any(~domain & (value > 0.0)):
            raise RadarReferenceError(f"transport {name} occupies inactive cells")
    if np.any(phase < PHASE_UNKNOWN) or np.any(phase > PHASE_GRAUPEL):
        raise RadarReferenceError("transport phase code outside [0, 5]")
    if np.any((phase == PHASE_RAIN) & ((snow > 0.0) | (graupel > 0.0))):
        raise RadarReferenceError("rain phase carries another hydrometeor")
    if np.any((phase == PHASE_SNOW) & ((rain > 0.0) | (graupel > 0.0))):
        raise RadarReferenceError("snow phase carries another hydrometeor")
    if np.any((phase == PHASE_GRAUPEL) & ((rain > 0.0) | (snow > 0.0))):
        raise RadarReferenceError("graupel phase carries another hydrometeor")
    nonempty = rain + snow + graupel > 0.0
    if np.any((phase == PHASE_FREEZING_RAIN) & nonempty & ((snow > 0.0) | (rain <= 0.0) | (graupel <= 0.0))):
        raise RadarReferenceError("freezing-rain phase requires rain and graupel only")
    if np.any((phase == PHASE_SLEET) & nonempty & ((rain > 0.0) | (snow <= 0.0) | (graupel <= 0.0))):
        raise RadarReferenceError("sleet phase requires snow and graupel only")


def _ledger_closes(ledger: PrecipitationLedger, config: RadarReferenceConfig) -> bool:
    output = (ledger.deposited + ledger.suspended + ledger.boundary_exit +
              ledger.terrain_intercept + ledger.observation_blocked +
              ledger.no_echo_blocked + ledger.microphysical_loss)
    error = abs(ledger.input - output)
    return np.isfinite(error) and error <= config.ledger_absolute_tolerance + config.ledger_relative_tolerance * max(abs(ledger.input), abs(output))


def reconstruct_radar_precipitation(
    pressure: Any, temperature: Any, vapor: Any, u: Any, v: Any, omega: Any,
    dx: Any, dy: Any, pressure_surface: Any, above: Any, domain: Any,
    radar_observed: Any, radar_no_echo: Any, radar_dbz: Any,
    phase: Any | None = None, config: RadarReferenceConfig | Mapping[str, Any] | Any | None = None,
) -> RadarReferenceResult:
    """Reconstruct fresh radar rain/snow/graupel and transport its flux.

    The input ``rain/snow/graupel`` background is intentionally absent: this
    is the current fresh-radar pressure-fixed path before publish.  The caller
    supplies explicit ``radar_observed`` and ``radar_no_echo`` masks; dBZ at
    unobserved cells is ignored. The caller maps unusable phase metadata to
    ``PHASE_UNKNOWN``; supplied phase codes outside 0--5 are rejected.
    """

    cfg = _config(config)
    arrays, shape = _validate_inputs(
        pressure, temperature, vapor, u, v, omega, dx, dy, pressure_surface,
        above, domain, radar_observed, radar_no_echo, radar_dbz,
    )
    phase_input = None if phase is None else _array(phase, "phase")
    interfaces, spacing = _pressure_geometry(arrays["pressure"], arrays["pressure_surface"], arrays["above"])
    w, w_valid = omega_to_w(
        arrays["omega"], arrays["pressure"], arrays["temperature"], arrays["vapor"], arrays["above"]
    )
    if np.any(arrays["radar_observed"] & ~w_valid):
        raise RadarReferenceError("observed radar cell lacks valid air motion")
    phase_work, uncertain, zlinear, rain, snow, graupel = _diagnose_radar(
        arrays["pressure"], arrays["temperature"], arrays["vapor"],
        arrays["radar_observed"], arrays["radar_dbz"], phase_input, cfg,
    )
    ledger = _transport(
        pressure=arrays["pressure"], temperature=arrays["temperature"], vapor=arrays["vapor"],
        u=arrays["u"], v=arrays["v"], w=w, dx=float(arrays["dx"][0, 0]), dy=float(arrays["dy"][0, 0]),
        interfaces=interfaces, domain=arrays["domain"], observed=arrays["radar_observed"],
        no_echo=arrays["radar_no_echo"], phase=phase_work, zlinear=zlinear,
        rain=rain, snow=snow, graupel=graupel, config=cfg,
    )
    # Descendants with a single allocated species are certain; mixed/unknown
    # targets remain explicitly uncertain for downstream publication logic.
    uncertain |= ((rain > 0.0).astype(int) + (snow > 0.0).astype(int) + (graupel > 0.0).astype(int) > 1)
    return RadarReferenceResult(
        rain=rain, snow=snow, graupel=graupel, zlinear=zlinear,
        phase=phase_work, phase_uncertain=uncertain, w=w, ledger=ledger,
        pressure_interface=interfaces, level_spacing_dp=spacing,
    )


def transport_precipitation_flux(
    pressure: Any, temperature: Any, vapor: Any, u: Any, v: Any, w: Any,
    dx: Any, dy: Any, pressure_surface: Any, domain: Any, observed: Any,
    no_echo: Any, phase: Any, zlinear: Any, rain: Any, snow: Any,
    graupel: Any, config: RadarReferenceConfig | Mapping[str, Any] | Any | None = None,
    *, above: Any | None = None, pressure_interface: Any | None = None,
    level_spacing_dp: Any | None = None, cell_dp: Any | None = None,
) -> RadarReferenceResult:
    """Direct transport fixture using supplied ``w`` instead of omega.

    Arrays are copied before transport.  This low-level entry point is useful
    for trajectory tests; unlike the reconstruction entry point it does not
    diagnose radar mass or phase fractions.
    """

    cfg = _config(config)
    pressure_a = _array(pressure, "pressure")
    temperature_a = _array(temperature, "temperature")
    vapor_a = _array(vapor, "vapor")
    u_a = _array(u, "u")
    v_a = _array(v, "v")
    w_a = _array(w, "w")
    if pressure_a.ndim != 3:
        raise RadarReferenceError("pressure: expected a 3-D (z, y, x) array")
    shape = pressure_a.shape
    for name, value in (("temperature", temperature_a), ("vapor", vapor_a), ("u", u_a), ("v", v_a), ("w", w_a)):
        if value.shape != shape:
            raise RadarReferenceError(f"{name}: expected shape {shape}")
    dx_a = _array(dx, "dx")
    dy_a = _array(dy, "dy")
    ps_a = _array(pressure_surface, "pressure_surface")
    if dx_a.shape != shape[1:] or dy_a.shape != shape[1:] or ps_a.shape != shape[1:]:
        raise RadarReferenceError("dx, dy and pressure_surface must have shape (y, x)")
    domain_a = _bool_array(domain, "domain", shape)
    above_a = domain_a if above is None else _bool_array(above, "above", shape)
    observed_a = _bool_array(observed, "observed", shape)
    no_echo_a = _bool_array(no_echo, "no_echo", shape)
    if np.any(observed_a & ~domain_a) or np.any(no_echo_a & ~domain_a) or np.any(observed_a & no_echo_a):
        raise RadarReferenceError("observed/no_echo masks violate the domain partition")
    if np.any(~np.isfinite(w_a)):
        raise RadarReferenceError("w must be finite")
    phase_a = np.asarray(phase, dtype=np.int64)
    if phase_a.shape != shape:
        raise RadarReferenceError(f"phase: expected shape {shape}")
    phase_raw = np.asarray(phase)
    if (not np.all(np.isfinite(phase_raw)) or
            np.any(phase_raw != np.floor(phase_raw)) or
            np.any((phase_raw < PHASE_UNKNOWN) | (phase_raw > PHASE_GRAUPEL))):
        raise RadarReferenceError("phase codes must be integer values in [0, 5]")
    arrays, _ = _validate_inputs(
        pressure_a, temperature_a, vapor_a, u_a, v_a, np.zeros_like(w_a),
        dx_a, dy_a, ps_a, above_a, domain_a, observed_a, no_echo_a, np.zeros(shape),
    )
    if pressure_interface is None:
        interfaces, spacing = _pressure_geometry(pressure_a, ps_a, above_a)
    else:
        interfaces = _array(pressure_interface, "pressure_interface")
        if interfaces.shape != (shape[0] + 1, shape[1], shape[2]):
            raise RadarReferenceError("pressure_interface: expected shape (z+1, y, x)")
        if np.any(interfaces <= 0.0) or np.any(np.diff(interfaces, axis=0) > 0.0):
            raise RadarReferenceError("pressure_interface must decrease with z")
        if not np.allclose(interfaces[0], ps_a, atol=64.0 * np.finfo(float).eps, rtol=0.0):
            raise RadarReferenceError("pressure_interface bottom does not match pressure_surface")
        spacing = pressure_a[:-1] - pressure_a[1:]
    if level_spacing_dp is not None:
        supplied_spacing = _array(level_spacing_dp, "level_spacing_dp")
        if supplied_spacing.shape != (shape[0] - 1, shape[1], shape[2]):
            raise RadarReferenceError("level_spacing_dp: expected shape (z-1, y, x)")
        if np.any(supplied_spacing <= 0.0) or not np.allclose(supplied_spacing, spacing, atol=64.0 * np.finfo(float).eps, rtol=0.0):
            raise RadarReferenceError("level_spacing_dp does not match pressure centers")
        spacing = supplied_spacing
    if cell_dp is not None:
        supplied_cell_dp = _array(cell_dp, "cell_dp")
        if supplied_cell_dp.shape != shape:
            raise RadarReferenceError("cell_dp: expected shape (z, y, x)")
        if np.any(supplied_cell_dp < 0.0) or np.any(supplied_cell_dp > MAX_PRESSURE_PA):
            raise RadarReferenceError("cell_dp outside production bounds")
        if np.any(above_a & (supplied_cell_dp <= 0.0)):
            raise RadarReferenceError("active cell_dp must be positive")
    z_a, rain_a, snow_a, graupel_a = (_array(value, name).copy() for name, value in (
        ("zlinear", zlinear), ("rain", rain), ("snow", snow), ("graupel", graupel)
    ))
    for name, value in (("zlinear", z_a), ("rain", rain_a), ("snow", snow_a), ("graupel", graupel_a)):
        if value.shape != shape or np.any(value < 0.0):
            raise RadarReferenceError(f"{name}: invalid transport field")
    phase_work = phase_a.copy()
    ledger = _transport(
        pressure=arrays["pressure"], temperature=arrays["temperature"], vapor=arrays["vapor"],
        u=arrays["u"], v=arrays["v"], w=w_a, dx=float(dx_a[0, 0]), dy=float(dy_a[0, 0]),
        interfaces=interfaces, domain=domain_a, observed=observed_a, no_echo=no_echo_a,
        phase=phase_work, zlinear=z_a, rain=rain_a, snow=snow_a,
        graupel=graupel_a, config=cfg,
    )
    mixed = (rain_a > 0.0).astype(int) + (snow_a > 0.0).astype(int) + (graupel_a > 0.0).astype(int) > 1
    return RadarReferenceResult(
        rain=rain_a, snow=snow_a, graupel=graupel_a, zlinear=z_a,
        phase=phase_work, phase_uncertain=mixed | (phase_work == PHASE_UNKNOWN),
        w=w_a, ledger=ledger, pressure_interface=interfaces,
        level_spacing_dp=spacing,
    )


__all__ = [
    "GRAVITY", "RD_AIR", "PHASE_UNKNOWN", "PHASE_RAIN", "PHASE_SNOW",
    "PHASE_FREEZING_RAIN", "PHASE_SLEET", "PHASE_GRAUPEL",
    "RadarReferenceConfig", "PrecipitationLedger", "RadarReferenceResult",
    "RadarReferenceError", "dry_air_density", "moist_gas_density", "omega_to_w",
    "missing_phase_partition", "allocate_precipitation_phase", "terminal_velocity",
    "reconstruct_radar_precipitation", "transport_precipitation_flux",
]
