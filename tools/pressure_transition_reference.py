#!/usr/bin/env python3
"""Independent thermodynamic adjustment and pressure-column remap reference.

All pressure interfaces descend in Pa.  Dry mass and the six species are
remapped as extensive quantities over pressure overlap; temperature is then
recovered from the linear mixture-enthalpy moment used by the Cloud-BAL
column equations.  The cloud equilibrium calculation reconstructs donor
thermodynamics before remapping.  Neither calculation depends on production
Fortran or state types.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import Any

import numpy as np


@dataclass(frozen=True)
class ThermoEquilibriumCertificate:
    """Certified ideal equilibrium and float32-storage enclosures.

    ``temperature_bounds`` and ``species_bounds`` enclose the mathematical
    six-species equilibrium for the supplied float64 inputs.  The stored
    intervals additionally include round-to-nearest float32 storage.  The
    existing transfer solver has a separate finite stopping criterion; its
    result is intentionally not represented as certified by these fields.
    """

    equilibrium_temperature: float
    equilibrium_species: np.ndarray
    temperature_bounds: tuple[float, float]
    species_bounds: tuple[np.ndarray, np.ndarray]
    stored_temperature_bounds: tuple[float, float]
    stored_species_bounds: tuple[np.ndarray, np.ndarray]
    exhausted: bool
    # Maximum width of a directed Decimal residual interval encountered.
    residual_error: float

    @property
    def temperature_error(self) -> float:
        return max(
            self.equilibrium_temperature - self.temperature_bounds[0],
            self.temperature_bounds[1] - self.equilibrium_temperature,
        )

    @property
    def species_error(self) -> np.ndarray:
        return np.maximum(
            self.equilibrium_species - self.species_bounds[0],
            self.species_bounds[1] - self.equilibrium_species,
        )

    @property
    def equilibrium_temperature_bounds(self) -> tuple[float, float]:
        return self.temperature_bounds

    @property
    def equilibrium_species_bounds(self) -> tuple[np.ndarray, np.ndarray]:
        return self.species_bounds

    @property
    def storage_temperature_bounds(self) -> tuple[float, float]:
        return self.stored_temperature_bounds

    @property
    def storage_species_bounds(self) -> tuple[np.ndarray, np.ndarray]:
        return self.stored_species_bounds


THERMO_T0 = 273.15
THERMO_CP_DRY = 1004.5
THERMO_SPECIES_CP = np.asarray(
    (1846.4, 4190.0, 2106.0, 4190.0, 2106.0, 2106.0),
    dtype=np.float64,
)
THERMO_SPECIES_H0 = np.asarray(
    (2.5e6, 0.0, -3.5e5, 0.0, -3.5e5, -3.5e5),
    dtype=np.float64,
)
MIN_TEMPERATURE_K = 150.0
MAX_TEMPERATURE_K = 350.0
MAX_VAPOR_MIXING_RATIO = 0.2
MAX_FLOAT32 = float(np.finfo(np.float32).max)
GRAVITY = 9.80665


def _array(value: Any, name: str) -> np.ndarray:
    if np.ma.isMaskedArray(value) and np.any(np.ma.getmaskarray(value)):
        raise ValueError(f"{name} contains masked values")
    array = np.asarray(value, dtype=np.float64)
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} contains non-finite values")
    return array


def _state_array(value: Any, name: str) -> np.ndarray:
    if np.ma.isMaskedArray(value) and np.any(np.ma.getmaskarray(value)):
        raise ValueError(f"{name} contains masked values")
    return np.asarray(value, dtype=np.float64)


def pressure_cell_geometry(pressure, surface_pressure, above, area):
    """Return pressure interfaces and total cell mass on the declared domain."""
    pressure = _array(pressure, "pressure")
    surface = _array(surface_pressure, "surface pressure")
    area = _array(area, "cell area")
    if np.ma.isMaskedArray(above) and np.any(np.ma.getmaskarray(above)):
        raise ValueError("pressure geometry domain contains masked values")
    above = np.asarray(above)
    if pressure.ndim != 1 or pressure.size < 2 or surface.ndim != 2:
        raise ValueError("pressure geometry dimensions")
    if above.dtype != np.dtype(bool) or above.shape != (pressure.size, *surface.shape):
        raise ValueError("pressure geometry domain shape/type")
    if area.shape != surface.shape or np.any(area <= 0):
        raise ValueError("pressure geometry area")
    if np.any(np.diff(pressure) >= 0) or np.any(pressure < 100) or np.any(pressure > 120000):
        raise ValueError("pressure geometry centers")
    if np.any(surface < 100) or np.any(surface > 120000):
        raise ValueError("pressure geometry surface range")
    pressure_domain = pressure[:, None, None] <= surface
    if (not np.all(np.any(above, axis=0)) or np.any(above & ~pressure_domain)
            or np.any(above[:-1] & ~above[1:])):
        raise ValueError("pressure geometry contiguous atmospheric domain")
    bottom = np.argmax(above, axis=0)
    if np.any(bottom - np.argmax(pressure_domain, axis=0) > 1):
        raise ValueError("pressure geometry terrain clip")
    top = pressure[-1] - 0.5 * (pressure[-2] - pressure[-1])
    if top <= 0:
        raise ValueError("pressure geometry top interface")
    interfaces = np.empty((pressure.size + 1, *surface.shape), dtype=np.float64)
    interfaces[0] = surface
    for level in range(1, pressure.size):
        interfaces[level] = np.where(
            level <= bottom, surface, 0.5 * (pressure[level - 1] + pressure[level])
        )
    interfaces[-1] = np.minimum(surface, top)
    dp = np.where(above, interfaces[:-1] - interfaces[1:], 0.0)
    if np.any(dp[above] <= 0):
        raise ValueError("pressure geometry positive cell thickness")
    return interfaces, area * dp / 9.80665


def _validate_inputs(
    old_interfaces: Any,
    old_dry_mass: Any,
    old_temperature: Any,
    old_species: Any,
    new_interfaces: Any,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    old_i = _array(old_interfaces, "old_interfaces")
    old_m = _array(old_dry_mass, "old_dry_mass")
    old_t = _array(old_temperature, "old_temperature")
    old_q = _array(old_species, "old_species")
    new_i = _array(new_interfaces, "new_interfaces")

    if old_i.ndim != 1 or new_i.ndim != 1:
        raise ValueError("pressure interfaces must be one-dimensional")
    if old_m.ndim != 1 or old_t.ndim != 1:
        raise ValueError("donor mass and temperature must be one-dimensional")
    if old_q.ndim != 2 or old_q.shape[0] != 6:
        raise ValueError("old_species must have shape (6, donor_cells)")
    donor_count = old_m.size
    if (
        old_i.size != donor_count + 1
        or old_t.size != donor_count
        or old_q.shape[1] != donor_count
        or new_i.size < 2
    ):
        raise ValueError("inconsistent donor or destination shapes")

    if np.any(old_i <= 0.0) or np.any(new_i <= 0.0):
        raise ValueError("pressure interfaces must be positive")
    if np.any(old_i[:-1] <= old_i[1:]) or np.any(new_i[:-1] <= new_i[1:]):
        raise ValueError("pressure interfaces must strictly descend")
    if old_i[0] != new_i[0] or old_i[-1] != new_i[-1]:
        raise ValueError("donor and destination endpoints must match")
    if np.any(old_m <= 0.0):
        raise ValueError("donor dry masses must be positive")
    if np.any((old_t < MIN_TEMPERATURE_K) | (old_t > MAX_TEMPERATURE_K)):
        raise ValueError("donor temperature is outside the canonical range")
    if np.any(old_q < 0.0) or np.any(old_q > MAX_FLOAT32):
        raise ValueError("donor species must be nonnegative and representable")
    if np.any(old_q[0] > MAX_VAPOR_MIXING_RATIO):
        raise ValueError("donor vapor exceeds the canonical range")
    return old_i, old_m, old_t, old_q, new_i


def _mixture_enthalpy(temperature: np.ndarray, species: np.ndarray) -> np.ndarray:
    capacity = THERMO_CP_DRY + np.sum(
        THERMO_SPECIES_CP[:, None] * species, axis=0
    )
    return capacity * (temperature - THERMO_T0) + np.sum(
        THERMO_SPECIES_H0[:, None] * species, axis=0
    )


def _check_conservation(
    old_mass: np.ndarray,
    old_temperature: np.ndarray,
    old_species: np.ndarray,
    new_mass: np.ndarray,
    new_temperature: np.ndarray,
    new_species: np.ndarray,
) -> None:
    old_water = old_mass @ old_species.T
    new_water = new_mass @ new_species.T
    old_energy = np.sum(old_mass * _mixture_enthalpy(old_temperature, old_species))
    new_energy = np.sum(new_mass * _mixture_enthalpy(new_temperature, new_species))
    epsilon = np.finfo(np.float64).eps
    dry_scale = max(
        float(np.finfo(np.float64).tiny),
        float(np.sum(np.abs(old_mass)) + np.sum(np.abs(new_mass))),
    )
    if not np.isclose(
        new_mass.sum(), old_mass.sum(), rtol=0.0,
        atol=256.0 * epsilon * dry_scale,
    ):
        raise ValueError("dry-mass conservation failed")
    species_scale = np.maximum(
        np.finfo(np.float64).tiny, np.abs(old_water) + np.abs(new_water)
    )
    if not np.all(np.abs(new_water - old_water) <= 256.0 * epsilon * species_scale):
        raise ValueError("species-mass conservation failed")

    def absolute_enthalpy_scale(mass: np.ndarray, temperature: np.ndarray,
                                species: np.ndarray) -> float:
        # Temperature recovery forms a capacity*T moment before subtracting
        # T0 in the energy check. Bound those operands even when T == T0.
        temperature_scale = np.abs(temperature) + abs(THERMO_T0)
        sensible_dry = np.sum(np.abs(mass * THERMO_CP_DRY) * temperature_scale)
        sensible_species = np.sum(
            np.abs(mass[None, :] * THERMO_SPECIES_CP[:, None] * species)
            * temperature_scale
        )
        phase_species = np.sum(
            np.abs(mass[None, :] * THERMO_SPECIES_H0[:, None] * species)
        )
        return float(sensible_dry + sensible_species + phase_species)

    energy_scale = max(
        float(np.finfo(np.float64).tiny),
        absolute_enthalpy_scale(old_mass, old_temperature, old_species)
        + absolute_enthalpy_scale(new_mass, new_temperature, new_species),
    )
    if not np.isclose(
        new_energy, old_energy, rtol=0.0,
        atol=256.0 * epsilon * energy_scale,
    ):
        raise ValueError("mixture enthalpy conservation failed")


def dry_mass_from_pressure_width_reference(
    area: Any, pressure_width: Any, species: Any,
) -> float:
    """Return dry mass implied by one pressure-width donor cell.

    ``pressure_width`` is deliberately caller-supplied.  A transition seed
    carries the mass of its full cell, while the conservative remap adds only
    the newly requested surface-pressure strip; those widths must not be
    conflated.  The result is the dry-air mass corresponding to the total
    pressure mass ``A * pressure_width / g`` for the supplied mixing ratios.
    """
    cell_area = _array(area, "area")
    width = _array(pressure_width, "pressure_width")
    donor_q = _array(species, "species")
    if cell_area.ndim != 0 or width.ndim != 0 or donor_q.shape != (6,):
        raise ValueError("pressure-width donor requires scalar area/width and six species")
    if cell_area <= 0.0 or width <= 0.0:
        raise ValueError("area and pressure width must be positive")
    if np.any(donor_q < 0.0) or np.any(donor_q > MAX_FLOAT32):
        raise ValueError("donor species must be nonnegative and representable")
    if donor_q[0] > MAX_VAPOR_MIXING_RATIO:
        raise ValueError("donor vapor exceeds the canonical range")
    pressure_mass = float(cell_area) * float(width) / GRAVITY
    dry_mass = pressure_mass / (1.0 + float(np.sum(donor_q)))
    if not np.isfinite(dry_mass) or dry_mass <= 0.0:
        raise ValueError("pressure-width dry mass is invalid")
    return dry_mass


def validate_transition_seed_mass_reference(
    seed_pressure_mass: Any,
    seed_species: Any,
    seed_domain: Any,
    seed_dry_mass: Any,
) -> None:
    """Bind seed dry mass to its own pressure metric and stored composition.

    A conservative phase step may retain dry mass while rounding each species
    to float32. Allow that storage error, not an arbitrary donor discrepancy.
    This full-cell check does not define the surface-strip remap donor.
    """
    seed_pm = _state_array(seed_pressure_mass, "seed_pressure_mass")
    seed_q = _state_array(seed_species, "seed_species")
    domain = np.asarray(seed_domain)
    stored_mass = _state_array(seed_dry_mass, "seed_dry_mass")
    if np.ma.isMaskedArray(seed_domain):
        raise ValueError("seed domain may not be masked")
    if domain.dtype != np.dtype(bool):
        raise ValueError("seed domain must be boolean")
    if (stored_mass.shape != seed_pm.shape
            or domain.shape != seed_pm.shape
            or seed_q.shape != (6, *seed_pm.shape)):
        raise ValueError("transition seed mass shapes differ")

    inactive = ~domain
    if np.any(stored_mass[inactive] != 0.0):
        raise ValueError("transition seed dry mass below ground")
    if not np.any(domain):
        return
    if (np.any(~np.isfinite(seed_pm[domain]))
            or np.any(~np.isfinite(stored_mass[domain]))
            or np.any(seed_pm[domain] <= 0.0)
            or np.any(stored_mass[domain] <= 0.0)):
        raise ValueError("transition seed mass is invalid on the active domain")
    active_species = seed_q[:, domain]
    if (np.any(~np.isfinite(active_species))
            or np.any(active_species < 0.0)
            or np.any(active_species > MAX_FLOAT32)
            or np.any(active_species[0] > MAX_VAPOR_MIXING_RATIO)):
        raise ValueError("transition seed species is invalid on the active domain")

    represented_mass = stored_mass[domain] * (1.0 + np.sum(active_species, axis=0))
    # frexp gives the float32 binade spacing without overflowing at max float.
    _, exponent = np.frexp(active_species)
    half_ulp = np.where(active_species == 0.0, 2.0**-150,
                        np.maximum(np.ldexp(1.0, exponent - 25), 2.0**-150))
    tolerance = stored_mass[domain] * np.sum(half_ulp, axis=0)
    tolerance += 64.0 * np.finfo(np.float64).eps * np.maximum(1.0, seed_pm[domain])
    if (np.any(~np.isfinite(represented_mass))
            or np.any(np.abs(represented_mass - seed_pm[domain]) > tolerance)):
        raise ValueError("transition seed dry mass does not match pressure and species")


def remap_pressure_column_reference(
    old_interfaces: Any,
    old_dry_mass: Any,
    old_temperature: Any,
    old_species: Any,
    new_interfaces: Any,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Conservatively remap one pressure column onto new interfaces.

    ``old_species`` has shape ``(6, n_old)`` and contains mixing ratios in
    the order vapor, cloud water, cloud ice, rain, snow, graupel.  The return
    values are ``(new_dry_mass, new_temperature, new_species)`` with shapes
    ``(n_new,)``, ``(n_new,)`` and ``(6, n_new)``.  Inputs are never modified.
    """

    old_i, old_m, old_t, old_q, new_i = _validate_inputs(
        old_interfaces, old_dry_mass, old_temperature, old_species, new_interfaces
    )
    if old_i.size == new_i.size and np.array_equal(old_i, new_i):
        return old_m.copy(), old_t.copy(), old_q.copy()

    old_top = old_i[:-1, None]
    old_bottom = old_i[1:, None]
    new_top = new_i[None, :-1]
    new_bottom = new_i[None, 1:]
    overlap = np.maximum(
        0.0,
        np.minimum(old_top, new_top) - np.maximum(old_bottom, new_bottom),
    )
    old_width = old_i[:-1] - old_i[1:]
    donor_fraction = overlap / old_width[:, None]
    donor_mass = donor_fraction * old_m[:, None]
    new_mass = np.sum(donor_mass, axis=0)
    if np.any(~np.isfinite(new_mass)) or np.any(new_mass <= 0.0):
        raise ValueError("destination column has an empty or invalid cell")

    species_mass = donor_mass.T @ old_q.T
    new_species = (species_mass / new_mass[:, None]).T
    donor_capacity = THERMO_CP_DRY + THERMO_SPECIES_CP @ old_q
    # Species-mass conservation cancels the reference and latent offsets;
    # capacity-weighted temperature therefore preserves the same linear
    # reduced mixture enthalpy, not full model energy.
    temperature_moment = donor_mass.T @ (donor_capacity * old_t)
    mixture_capacity = THERMO_CP_DRY * new_mass + species_mass @ THERMO_SPECIES_CP
    new_temperature = temperature_moment / mixture_capacity

    if (
        np.any(~np.isfinite(new_species))
        or np.any(new_species < 0.0)
        or np.any(new_species > MAX_FLOAT32)
        or np.any(new_species[0] > MAX_VAPOR_MIXING_RATIO)
        or np.any(~np.isfinite(new_temperature))
        or np.any((new_temperature < MIN_TEMPERATURE_K) | (new_temperature > MAX_TEMPERATURE_K))
    ):
        raise ValueError("remapped state is outside the canonical range")
    _check_conservation(
        old_m, old_t, old_q, new_mass, new_temperature, new_species
    )
    return new_mass, new_temperature, new_species


def remap_pressure_column_bounds_reference(
    old_interfaces: Any,
    old_dry_mass: Any,
    old_temperature: Any,
    old_species: Any,
    new_interfaces: Any,
    *,
    dry_mass_error: Any = None,
    temperature_error: Any = None,
    species_error: Any = None,
) -> tuple[tuple[np.ndarray, np.ndarray], tuple[np.ndarray, np.ndarray],
           tuple[np.ndarray, np.ndarray]]:
    """Enclose pressure remap outputs under explicit donor uncertainty.

    The intervals follow the remap equations above.  Overlap lengths and all
    additions, products, and divisions are rounded outwards with ``nextafter``
    so zero input uncertainty still has a finite arithmetic enclosure.  Donor
    mass and species are nonnegative, which makes the extensive overlap sums
    monotone; output species and temperature use the corresponding quotient
    extrema.  Uncertainty is absolute and independent for each donor value.
    """
    old_i, old_m, old_t, old_q, new_i = _validate_inputs(
        old_interfaces, old_dry_mass, old_temperature, old_species, new_interfaces
    )
    negative_inf = np.float64(-np.inf)
    positive_inf = np.float64(np.inf)

    def uncertainty(value: Any, shape: tuple[int, ...], name: str) -> np.ndarray:
        if value is None:
            return np.zeros(shape, dtype=np.float64)
        if np.ma.isMaskedArray(value):
            raise ValueError(f"{name} may not be masked")
        result = np.asarray(value, dtype=np.float64)
        if result.shape != shape or np.any(~np.isfinite(result)) or np.any(result < 0.0):
            raise ValueError(f"{name} must be finite, nonnegative, and shape-compatible")
        return result

    def endpoint_bounds(value: np.ndarray, error: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Form outward donor endpoints, preserving exact zero-error values."""
        lower = value - error
        upper = value + error
        nonzero = error != 0.0
        lower = np.where(nonzero, np.nextafter(lower, negative_inf), lower)
        upper = np.where(nonzero, np.nextafter(upper, positive_inf), upper)
        return lower, upper

    mass_error = uncertainty(dry_mass_error, old_m.shape, "dry_mass_error")
    temp_error = uncertainty(temperature_error, old_t.shape, "temperature_error")
    q_error = uncertainty(species_error, old_q.shape, "species_error")
    mass_lo, mass_hi = endpoint_bounds(old_m, mass_error)
    temp_lo, temp_hi = endpoint_bounds(old_t, temp_error)
    species_lo, species_hi = endpoint_bounds(old_q, q_error)
    if np.any(q_error > old_q):
        raise ValueError("species uncertainty crosses physical zero")
    # Only remove outward-rounding underflow at an exact zero endpoint;
    # a genuinely negative donor interval is rejected above.
    species_lo = np.maximum(species_lo, 0.0)
    return remap_pressure_column_intervals_reference(
        old_i, (mass_lo, mass_hi), (temp_lo, temp_hi),
        (species_lo, species_hi), new_i,
    )


def remap_pressure_column_intervals_reference(
    old_interfaces: Any,
    dry_mass_bounds: tuple[Any, Any],
    temperature_bounds: tuple[Any, Any],
    species_bounds: tuple[Any, Any],
    new_interfaces: Any,
) -> tuple[tuple[np.ndarray, np.ndarray], tuple[np.ndarray, np.ndarray],
           tuple[np.ndarray, np.ndarray]]:
    """Propagate explicit donor endpoints through conservative pressure remap.

    Bounds are inclusive (lower, upper) arrays. Asymmetric intervals allow
    a zero condensate reservoir to have a positive upper bound without an
    artificial negative lower endpoint. Every endpoint must be physically
    valid; this routine neither clips input intervals nor infers uncertainty.
    """
    for bounds in (dry_mass_bounds, temperature_bounds, species_bounds):
        if len(bounds) != 2 or any(np.ma.isMaskedArray(v) for v in bounds):
            raise ValueError("donor bounds require two unmasked endpoints")
    old_i, mass_lo, temp_lo, species_lo, new_i = _validate_inputs(
        old_interfaces, dry_mass_bounds[0], temperature_bounds[0],
        species_bounds[0], new_interfaces,
    )
    _, mass_hi, temp_hi, species_hi, _ = _validate_inputs(
        old_interfaces, dry_mass_bounds[1], temperature_bounds[1],
        species_bounds[1], new_interfaces,
    )
    if (np.any(mass_lo > mass_hi) or np.any(temp_lo > temp_hi)
            or np.any(species_lo > species_hi)):
        raise ValueError("donor interval endpoints are reversed")
    negative_inf = np.float64(-np.inf)
    positive_inf = np.float64(np.inf)

    def outward_add(lower: float, upper: float,
                    term_lower: float, term_upper: float) -> tuple[float, float]:
        lo = np.nextafter(lower + term_lower, negative_inf)
        hi = np.nextafter(upper + term_upper, positive_inf)
        if not np.isfinite(lo) or not np.isfinite(hi):
            raise ValueError("remap interval overflow")
        return max(0.0, float(lo)), float(hi)

    def outward_mul(lower_a: float, upper_a: float,
                    lower_b: float, upper_b: float) -> tuple[float, float]:
        lo = np.nextafter(lower_a * lower_b, negative_inf)
        hi = np.nextafter(upper_a * upper_b, positive_inf)
        if not np.isfinite(lo) or not np.isfinite(hi):
            raise ValueError("remap interval overflow")
        return max(0.0, float(lo)), float(hi)

    def outward_div(lower_a: float, upper_a: float,
                    lower_b: float, upper_b: float) -> tuple[float, float]:
        if lower_b <= 0.0:
            raise ValueError("remap interval has an unbounded denominator")
        lo = np.nextafter(lower_a / upper_b, negative_inf)
        hi = np.nextafter(upper_a / lower_b, positive_inf)
        if not np.isfinite(lo) or not np.isfinite(hi):
            raise ValueError("remap interval overflow")
        return max(0.0, float(lo)), float(hi)

    def sum_interval(terms: list[tuple[float, float]]) -> tuple[float, float]:
        lower = upper = 0.0
        for term_lower, term_upper in terms:
            lower, upper = outward_add(lower, upper, term_lower, term_upper)
        return lower, upper

    old_top = old_i[:-1]
    old_bottom = old_i[1:]
    old_width = old_top - old_bottom
    new_top = new_i[:-1]
    new_bottom = new_i[1:]
    new_count = new_top.size
    mass_bounds = np.empty((2, new_count), dtype=np.float64)
    temperature_bounds = np.empty((2, new_count), dtype=np.float64)
    species_bounds = np.empty((2, 6, new_count), dtype=np.float64)

    fractions: list[tuple[float, float]] = []
    for donor in range(mass_lo.size):
        width_lower = np.nextafter(old_width[donor], negative_inf)
        width_upper = np.nextafter(old_width[donor], positive_inf)
        for destination in range(new_count):
            raw_overlap = min(old_top[donor], new_top[destination]) - max(
                old_bottom[donor], new_bottom[destination]
            )
            if raw_overlap <= 0.0:
                fractions.append((0.0, 0.0))
                continue
            overlap_lower = max(0.0, float(np.nextafter(raw_overlap, negative_inf)))
            overlap_upper = float(np.nextafter(raw_overlap, positive_inf))
            fractions.append(outward_div(
                overlap_lower, overlap_upper, width_lower, width_upper
            ))

    def fraction(donor: int, destination: int) -> tuple[float, float]:
        return fractions[donor * new_count + destination]

    for destination in range(new_count):
        donor_mass_terms = []
        species_mass_terms = [[] for _ in range(6)]
        temperature_terms = []
        for donor in range(mass_lo.size):
            fraction_lower, fraction_upper = fraction(donor, destination)
            if fraction_upper == 0.0:
                continue
            donor_mass = outward_mul(
                fraction_lower, fraction_upper, mass_lo[donor], mass_hi[donor]
            )
            donor_mass_terms.append(donor_mass)
            capacity_lower, capacity_upper = sum_interval(
                [(THERMO_CP_DRY, THERMO_CP_DRY)]
                + [outward_mul(
                    float(THERMO_SPECIES_CP[s]), float(THERMO_SPECIES_CP[s]),
                    species_lo[s, donor], species_hi[s, donor],
                ) for s in range(6)]
            )
            temperature_terms.append(outward_mul(
                *outward_mul(*donor_mass, capacity_lower, capacity_upper),
                temp_lo[donor], temp_hi[donor],
            ))
            for species in range(6):
                species_mass_terms[species].append(outward_mul(
                    *donor_mass, species_lo[species, donor], species_hi[species, donor]
                ))

        mass_lower, mass_upper = sum_interval(donor_mass_terms)
        if mass_lower <= 0.0:
            raise ValueError("destination interval has an unbounded mass denominator")
        mass_bounds[:, destination] = (mass_lower, mass_upper)
        species_mass = [sum_interval(terms) for terms in species_mass_terms]
        for species, (numerator_lower, numerator_upper) in enumerate(species_mass):
            species_bounds[:, species, destination] = outward_div(
                numerator_lower, numerator_upper, mass_lower, mass_upper
            )
        moment_lower, moment_upper = sum_interval(temperature_terms)
        capacity_terms = [outward_mul(
            THERMO_CP_DRY, THERMO_CP_DRY, mass_lower, mass_upper
        )]
        capacity_terms.extend(
            outward_mul(
                float(THERMO_SPECIES_CP[s]), float(THERMO_SPECIES_CP[s]),
                species_mass[s][0], species_mass[s][1],
            ) for s in range(6)
        )
        capacity_lower, capacity_upper = sum_interval(capacity_terms)
        temperature_bounds[:, destination] = outward_div(
            moment_lower, moment_upper, capacity_lower, capacity_upper
        )

    return (
        (mass_bounds[0], mass_bounds[1]),
        (temperature_bounds[0], temperature_bounds[1]),
        (species_bounds[0], species_bounds[1]),
    )


def reconstruct_prebalance_winds(
    original_winds: np.ndarray,
    original_above: np.ndarray,
    candidate_above: np.ndarray,
    seed_winds: np.ndarray | None = None,
) -> np.ndarray:
    """Restore u/v/omega before balance, including explicitly seeded new cells.

    Wind arrays have shape (3, *domain_shape). Thermo and pressure remapping
    do not change old-cell winds. Only added cells take seed winds, never the
    potentially balanced final candidate values. No observation authority is
    inferred by this numerical reconstruction.
    """
    original = np.asarray(original_winds, dtype=np.float64)
    old = np.asarray(original_above)
    new = np.asarray(candidate_above)
    if (old.dtype != np.dtype(bool) or new.dtype != np.dtype(bool)
            or old.shape != new.shape or original.shape != (3, *old.shape)):
        raise ValueError("prebalance wind/domain shapes or types differ")
    if np.any(old & ~new):
        raise ValueError("prebalance reconstruction cannot remove original cells")
    if np.any(~np.isfinite(original[:, old])):
        raise ValueError("original active winds are nonfinite")
    added = new & ~old
    result = original.copy()
    if np.any(added):
        if seed_winds is None:
            raise ValueError("new cells require explicit seed winds")
        seed = np.asarray(seed_winds, dtype=np.float64)
        if seed.shape != original.shape or np.any(~np.isfinite(seed[:, added])):
            raise ValueError("seed winds missing or nonfinite on added cells")
        result[:, added] = seed[:, added]
    return result


def remap_surface_pressure_reference(
    old_interfaces: np.ndarray,
    old_dry_mass: np.ndarray,
    old_temperature: np.ndarray,
    old_species: np.ndarray,
    new_interfaces: np.ndarray,
    boundary_temperature: float,
    boundary_species: np.ndarray,
    area: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Add the explicit pressure boundary strip and conservatively remap.

    Existing donors retain their stored post-thermo dry mass. The new strip
    uses prior bottom-cell composition, but its mass is only A*delta_PS/g,
    not the full seed cell mass. Same-domain thickening and one new cell are
    supported, matching the currently implemented positive transition scope.
    """
    old_i = _array(old_interfaces, "old_interfaces")
    new_i = _array(new_interfaces, "new_interfaces")
    boundary_q = _array(boundary_species, "boundary_species")
    boundary_t = _array(boundary_temperature, "boundary_temperature")
    cell_area = _array(area, "area")
    if (old_i.ndim != 1 or new_i.ndim != 1 or old_i.size < 2
            or new_i.size not in (old_i.size, old_i.size + 1)):
        raise ValueError("surface transition requires zero or one added cell")
    if boundary_q.shape != (6,) or boundary_t.ndim != 0 or cell_area.ndim != 0:
        raise ValueError("boundary requires scalar temperature/area and six species")
    if cell_area <= 0.0 or np.any(boundary_q < 0.0):
        raise ValueError("invalid boundary area or species")
    delta_ps = new_i[0] - old_i[0]
    if not 0.0 < delta_ps <= 100.0:
        raise ValueError("surface pressure increase must be in (0, 100] Pa")
    boundary_mass = dry_mass_from_pressure_width_reference(
        cell_area, delta_ps, boundary_q
    )
    return remap_pressure_column_reference(
        np.concatenate(([new_i[0]], old_i)),
        np.concatenate(([boundary_mass], _array(old_dry_mass, "old_dry_mass"))),
        np.concatenate(([float(boundary_t)], _array(old_temperature, "old_temperature"))),
        np.column_stack((boundary_q, _array(old_species, "old_species"))),
        new_i,
    )


def remap_pressure_state_reference(
    old_interfaces: Any,
    old_mass: Any,
    old_temperature: Any,
    old_species: Any,
    old_above: Any,
    new_interfaces: Any,
    new_above: Any,
    area: Any,
    seed_temperature: Any = None,
    seed_species: Any = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Replay signed surface-pressure state transitions column by column.

    State arrays use ``(z, y, x)`` and pressure interfaces use
    ``(z+1, y, x)``.  Active cells must form a contiguous suffix in each
    column.  The supplied post-thermo dry mass is the immutable donor for
    positive transitions; final mass is refreshed only for changed columns
    from the final stored (float32) species and pressure geometry.
    """
    old_i = _state_array(old_interfaces, "old_interfaces")
    donor_mass = _state_array(old_mass, "old_mass")
    donor_t = _state_array(old_temperature, "old_temperature")
    donor_q = _state_array(old_species, "old_species")
    new_i = _state_array(new_interfaces, "new_interfaces")
    cell_area = _state_array(area, "area")
    old_domain = np.asarray(old_above)
    new_domain = np.asarray(new_above)
    if np.ma.isMaskedArray(old_above) or np.ma.isMaskedArray(new_above):
        raise ValueError("domain masks may not be masked")
    if old_domain.dtype != np.dtype(bool) or new_domain.dtype != np.dtype(bool):
        raise ValueError("domain masks must be boolean")
    if old_domain.ndim != 3 or new_domain.shape != old_domain.shape:
        raise ValueError("domain masks must have matching (z, y, x) shapes")
    nz, ny, nx = old_domain.shape
    if (old_i.shape != (nz + 1, ny, nx)
            or new_i.shape != (nz + 1, ny, nx)
            or donor_mass.shape != old_domain.shape
            or donor_t.shape != old_domain.shape
            or donor_q.shape != (6, nz, ny, nx)
            or cell_area.shape != (ny, nx)):
        raise ValueError("pressure state shapes differ")
    if (np.any(~np.isfinite(cell_area)) or np.any(cell_area <= 0.0)
            or np.any(~np.isfinite(old_i[0]))
            or np.any(~np.isfinite(new_i[0]))
            or np.any(old_i[0] <= 0.0) or np.any(new_i[0] <= 0.0)):
        raise ValueError("surface pressure or area is invalid")
    if np.any(old_domain & ~new_domain):
        raise ValueError("pressure transition cannot remove active cells")
    if (seed_temperature is None) != (seed_species is None):
        raise ValueError("temperature and species seeds must be supplied together")
    seed_t = seed_q = None
    if seed_temperature is not None:
        seed_t = _state_array(seed_temperature, "seed_temperature")
        seed_q = _state_array(seed_species, "seed_species")
        if seed_t.shape != old_domain.shape or seed_q.shape != (6, nz, ny, nx):
            raise ValueError("seed shapes differ from the pressure state")

    final_mass = donor_mass.copy()
    final_t = donor_t.copy()
    final_q = donor_q.copy()
    gravity = 9.80665

    def active_bottom(mask: np.ndarray) -> int:
        levels = np.flatnonzero(mask)
        if levels.size == 0 or not np.array_equal(
            levels, np.arange(levels[0], mask.size)
        ):
            raise ValueError("active cells must form a contiguous trailing suffix")
        return int(levels[0])

    for j in range(ny):
        for i in range(nx):
            old_mask = old_domain[:, j, i]
            new_mask = new_domain[:, j, i]
            old_bottom = active_bottom(old_mask)
            new_bottom = active_bottom(new_mask)
            old_count = nz - old_bottom
            new_count = nz - new_bottom
            if new_count - old_count not in (0, 1):
                raise ValueError("pressure transition may add at most one bottom cell")
            old_active_i = old_i[old_bottom:, j, i]
            new_active_i = new_i[new_bottom:, j, i]
            if (np.any(~np.isfinite(old_active_i))
                    or np.any(~np.isfinite(new_active_i))
                    or np.any(old_active_i <= 0.0)
                    or np.any(new_active_i <= 0.0)
                    or np.any(old_active_i[:-1] <= old_active_i[1:])
                    or np.any(new_active_i[:-1] <= new_active_i[1:])):
                raise ValueError("active pressure interfaces must strictly descend")
            active_mass = donor_mass[old_bottom:, j, i]
            active_t = donor_t[old_bottom:, j, i]
            active_q = donor_q[:, old_bottom:, j, i]
            if (np.any(~np.isfinite(active_mass)) or np.any(active_mass <= 0.0)
                    or np.any(~np.isfinite(active_t))
                    or np.any((active_t < MIN_TEMPERATURE_K)
                              | (active_t > MAX_TEMPERATURE_K))
                    or np.any(~np.isfinite(active_q)) or np.any(active_q < 0.0)
                    or np.any(active_q > MAX_FLOAT32)
                    or np.any(active_q[0] > MAX_VAPOR_MIXING_RATIO)):
                raise ValueError("active post-thermo state is invalid")

            delta_ps = float(new_i[0, j, i] - old_i[0, j, i])
            if not np.isfinite(delta_ps) or abs(delta_ps) > 100.0:
                raise ValueError("surface pressure change exceeds 100 Pa")
            if (old_active_i[0] != old_i[0, j, i]
                    or new_active_i[0] != new_i[0, j, i]):
                raise ValueError("active lower interface must equal surface pressure")

            if delta_ps == 0.0:
                if (not np.array_equal(old_mask, new_mask)
                        or not np.array_equal(
                            old_i[:, j, i], new_i[:, j, i], equal_nan=True
                        )):
                    raise ValueError("zero pressure change requires identical geometry")
                continue
            if not np.array_equal(new_active_i[-old_count:], old_active_i[1:]):
                raise ValueError("pressure transition moved an existing interface")
            if delta_ps < 0.0:
                if not np.array_equal(old_mask, new_mask):
                    raise ValueError("pressure decreases cannot change the active domain")
            else:
                if new_bottom not in (old_bottom, old_bottom - 1):
                    raise ValueError("pressure increase has an unsupported domain change")
                if new_bottom < old_bottom:
                    if seed_t is None or seed_q is None:
                        raise ValueError("new cells require explicit thermodynamic seeds")
                    boundary_t = float(seed_t[new_bottom, j, i])
                    boundary_q = seed_q[:, new_bottom, j, i]
                else:
                    boundary_t = float(donor_t[old_bottom, j, i])
                    boundary_q = donor_q[:, old_bottom, j, i]
                _, remapped_t, remapped_q = remap_surface_pressure_reference(
                    old_active_i,
                    active_mass,
                    active_t,
                    active_q,
                    new_active_i,
                    boundary_t,
                    boundary_q,
                    float(cell_area[j, i]),
                )
                stored_t = remapped_t.astype(np.float32).astype(np.float64)
                stored_q = remapped_q.astype(np.float32).astype(np.float64)
                final_t[new_bottom:, j, i] = stored_t
                final_q[:, new_bottom:, j, i] = stored_q

            final_mass[new_bottom:, j, i] = (
                float(cell_area[j, i])
                * (new_active_i[:-1] - new_active_i[1:])
                / gravity
                / (1.0 + np.sum(final_q[:, new_bottom:, j, i], axis=0))
            )
            if (np.any(~np.isfinite(final_mass[new_bottom:, j, i]))
                    or np.any(final_mass[new_bottom:, j, i] <= 0.0)):
                raise ValueError("refreshed dry mass is invalid")
    return final_mass, final_t, final_q


def saturation_adjust_reference(
    pressure: float,
    temperature: float,
    species: np.ndarray,
    target_rh: float,
    *,
    over_ice: bool = False,
) -> tuple[float, np.ndarray]:
    """Recover the pre-remap equilibrium from water and reduced enthalpy.

    Unlike the production transfer-space solve, this solves directly for
    temperature with vapor=min(available water, RH*saturation(T)).  The
    returned float64 state precedes canonical float32 storage.  Only vapor
    and the selected cloud reservoir exchange mass; precipitation contributes
    heat capacity but is not evaporated by this cloud adjustment.
    """
    inputs = _array([pressure, temperature, target_rh], "thermo inputs")
    before = _array(species, "species")
    maximum_t = THERMO_T0 if over_ice else MAX_TEMPERATURE_K
    if inputs.shape != (3,) or before.shape != (6,):
        raise ValueError("thermo requires scalar inputs and six species")
    if not 100.0 <= pressure <= 120000.0 or not 0.0 <= target_rh <= 1.0:
        raise ValueError("pressure or target RH outside range")
    if not MIN_TEMPERATURE_K <= temperature <= maximum_t:
        raise ValueError("initial temperature outside phase range")
    if np.any(before < 0.0) or np.any(before > MAX_FLOAT32) or before[0] > float(np.float32(0.2)):
        raise ValueError("initial species outside range")

    phase = 2 if over_ice else 1
    available = before[0] + before[phase]
    latent = (THERMO_SPECIES_H0[0] - THERMO_SPECIES_H0[phase]
              + (THERMO_SPECIES_CP[0] - THERMO_SPECIES_CP[phase])
              * (temperature - THERMO_T0))

    def equilibrium(trial_t: float) -> tuple[float, np.ndarray]:
        tc = trial_t - THERMO_T0
        es = (611.15 * np.exp(22.452 * tc / (trial_t - 0.55)) if over_ice
              else 611.20 * np.exp(17.67 * tc / (tc + 243.5)))
        es = min(0.99 * pressure, max(0.0, es))
        vapor = min(available, target_rh * 0.622 * es / (pressure - es))
        after = before.copy()
        after[0], after[phase] = vapor, available - vapor
        capacity = THERMO_CP_DRY + THERMO_SPECIES_CP @ after
        # Difference form avoids subtracting two large reference enthalpies.
        residual = capacity * (trial_t - temperature) + (vapor - before[0]) * latent
        return float(residual), after

    lower, upper = MIN_TEMPERATURE_K, maximum_t
    low_error, low_state = equilibrium(lower)
    high_error, high_state = equilibrium(upper)
    if low_error > 0.0 or high_error < 0.0:
        raise ValueError("no saturation equilibrium within temperature bounds")
    if low_error == 0.0:
        result_t, after = lower, low_state
    elif high_error == 0.0:
        result_t, after = upper, high_state
    else:
        for _ in range(100):
            result_t = lower + 0.5 * (upper - lower)
            error, after = equilibrium(result_t)
            if error == 0.0 or result_t == lower or result_t == upper:
                break
            if error > 0.0:
                upper = result_t
            else:
                lower = result_t
        else:
            raise ValueError("saturation reference failed to converge")
    if after[0] > float(np.float32(0.2)):
        raise ValueError("equilibrium vapor outside canonical range")
    return result_t, after


_DECIMAL_PRECISION = 96


@dataclass(frozen=True)
class _DecimalInterval:
    lower: Decimal
    upper: Decimal

    def __post_init__(self) -> None:
        if self.lower > self.upper:
            raise ValueError("invalid Decimal interval")


def _decimal_operation(left: Decimal, right: Decimal, operation: str, rounding: str) -> Decimal:
    with localcontext() as context:
        context.prec = _DECIMAL_PRECISION
        context.rounding = rounding
        if operation == "add":
            return left + right
        if operation == "subtract":
            return left - right
        if operation == "multiply":
            return left * right
        if operation == "divide":
            return left / right
    raise ValueError("unknown Decimal operation")


def _decimal_interval(value: Decimal) -> _DecimalInterval:
    return _DecimalInterval(value, value)


def _decimal_add(left: _DecimalInterval, right: _DecimalInterval) -> _DecimalInterval:
    return _DecimalInterval(
        _decimal_operation(left.lower, right.lower, "add", "ROUND_FLOOR"),
        _decimal_operation(left.upper, right.upper, "add", "ROUND_CEILING"),
    )


def _decimal_subtract(left: _DecimalInterval, right: _DecimalInterval) -> _DecimalInterval:
    return _DecimalInterval(
        _decimal_operation(left.lower, right.upper, "subtract", "ROUND_FLOOR"),
        _decimal_operation(left.upper, right.lower, "subtract", "ROUND_CEILING"),
    )


def _decimal_multiply(left: _DecimalInterval, right: _DecimalInterval) -> _DecimalInterval:
    products = [
        (left.lower, right.lower), (left.lower, right.upper),
        (left.upper, right.lower), (left.upper, right.upper),
    ]
    lower = min(_decimal_operation(a, b, "multiply", "ROUND_FLOOR") for a, b in products)
    upper = max(_decimal_operation(a, b, "multiply", "ROUND_CEILING") for a, b in products)
    return _DecimalInterval(lower, upper)


def _decimal_divide(left: _DecimalInterval, right: _DecimalInterval) -> _DecimalInterval:
    if right.lower <= 0 <= right.upper:
        raise ValueError("Decimal interval denominator crosses zero")
    quotients = [
        (left.lower, right.lower), (left.lower, right.upper),
        (left.upper, right.lower), (left.upper, right.upper),
    ]
    lower = min(_decimal_operation(a, b, "divide", "ROUND_FLOOR") for a, b in quotients)
    upper = max(_decimal_operation(a, b, "divide", "ROUND_CEILING") for a, b in quotients)
    return _DecimalInterval(lower, upper)


def _decimal_exp(value: _DecimalInterval) -> _DecimalInterval:
    # Decimal.exp is correctly rounded in the active context.  next_minus /
    # next_plus protect the enclosure against that context's final rounding.
    with localcontext() as context:
        context.prec = _DECIMAL_PRECISION
        context.rounding = "ROUND_FLOOR"
        lower = value.lower.exp().next_minus()
        context.rounding = "ROUND_CEILING"
        upper = value.upper.exp().next_plus()
    return _DecimalInterval(lower, upper)


def _decimal_float(value: float) -> Decimal:
    """Represent the supplied float64 value exactly in Decimal arithmetic."""
    return Decimal.from_float(float(value))


def _decimal_qsat_interval(
    pressure: _DecimalInterval, temperature: _DecimalInterval, over_ice: bool,
) -> _DecimalInterval:
    tc = _decimal_subtract(temperature, _decimal_interval(_decimal_float(THERMO_T0)))
    if over_ice:
        exponent = _decimal_divide(
            _decimal_multiply(tc, _decimal_interval(_decimal_float(22.452))),
            _decimal_subtract(temperature, _decimal_interval(_decimal_float(0.55))),
        )
        vapor_pressure = _decimal_multiply(
            _decimal_interval(_decimal_float(611.15)), _decimal_exp(exponent)
        )
    else:
        exponent = _decimal_divide(
            _decimal_multiply(tc, _decimal_interval(_decimal_float(17.67))),
            _decimal_add(tc, _decimal_interval(_decimal_float(243.5))),
        )
        vapor_pressure = _decimal_multiply(
            _decimal_interval(_decimal_float(611.20)), _decimal_exp(exponent)
        )
    cap = _decimal_multiply(
        pressure, _decimal_interval(_decimal_float(0.99))
    )
    # min(cap, raw) is monotone in both operands: use the minimum of the
    # lower endpoints and the minimum of the upper endpoints.  Taking
    # ``max(0, raw.lower)`` before the cap would invert the interval whenever
    # the raw Clausius-Clapeyron pressure exceeds the pressure cap.
    vapor_pressure = _DecimalInterval(
        max(_decimal_float(0.0), min(cap.lower, vapor_pressure.lower)),
        max(_decimal_float(0.0), min(cap.upper, vapor_pressure.upper)),
    )
    denominator = _decimal_subtract(pressure, vapor_pressure)
    return _decimal_multiply(
        _decimal_interval(_decimal_float(0.622)),
        _decimal_divide(vapor_pressure, denominator),
    )


def _decimal_temperature_interval_for_transfer(
    initial_temperature: _DecimalInterval,
    transfer: _DecimalInterval,
    capacity: _DecimalInterval,
    latent: _DecimalInterval,
    delta_cp: _DecimalInterval,
) -> _DecimalInterval:
    denominator = _decimal_add(capacity, _decimal_multiply(transfer, delta_cp))
    if denominator.lower <= 0:
        raise ValueError("thermo transfer has non-positive heat capacity")
    return _decimal_subtract(
        initial_temperature,
        _decimal_divide(_decimal_multiply(transfer, latent), denominator),
    )


def _decimal_transfer_residual(
    pressure: _DecimalInterval,
    initial_temperature: _DecimalInterval,
    initial_vapor: _DecimalInterval,
    target_rh: _DecimalInterval,
    transfer: Decimal,
    capacity: _DecimalInterval,
    latent: _DecimalInterval,
    delta_cp: _DecimalInterval,
    over_ice: bool,
) -> tuple[Decimal, Decimal, _DecimalInterval]:
    transfer_interval = _decimal_interval(transfer)
    trial_temperature = _decimal_temperature_interval_for_transfer(
        initial_temperature, transfer_interval, capacity, latent, delta_cp,
    )
    saturation = _decimal_multiply(
        target_rh, _decimal_qsat_interval(pressure, trial_temperature, over_ice),
    )
    residual = _decimal_subtract(
        _decimal_add(initial_vapor, transfer_interval), saturation
    )
    return residual.lower, residual.upper, trial_temperature


def _outward_float_interval(lower: Decimal, upper: Decimal) -> tuple[float, float]:
    lower_float = float(lower)
    upper_float = float(upper)
    if not np.isfinite(lower_float) or not np.isfinite(upper_float):
        raise ValueError("thermo certificate interval is not representable")
    for _ in range(2):
        lower_float = float(np.nextafter(lower_float, -np.inf))
        upper_float = float(np.nextafter(upper_float, np.inf))
    return lower_float, upper_float


def _stored_float32_interval(lower: Decimal, upper: Decimal) -> tuple[float, float]:
    lower32 = np.float32(float(lower))
    upper32 = np.float32(float(upper))
    lower32 = np.nextafter(lower32, np.float32(-np.inf))
    upper32 = np.nextafter(upper32, np.float32(np.inf))
    lower_float = max(0.0, float(lower32))
    upper_float = float(upper32)
    if not np.isfinite(lower_float) or not np.isfinite(upper_float):
        raise ValueError("thermo float32 storage interval is not representable")
    return lower_float, upper_float


def saturation_equilibrium_certificate_reference(
    pressure: float,
    temperature: float,
    species: np.ndarray,
    target_rh: float,
    *,
    over_ice: bool = False,
) -> ThermoEquilibriumCertificate:
    """Certify ideal equilibrium and canonical float32 storage bounds.

    The transfer variable is the vapor change used by the Fortran kernel.  Its
    saturation residual is strictly increasing because qsat(T) is monotone,
    T'(e) is negative, and therefore F'(e) >= 1.  Every arithmetic operation
    and exp evaluation is enclosed with directed 96-digit Decimal intervals.
    Thus a plain float64 bisection bracket is never presented as certified.
    """
    inputs = _array([pressure, temperature, target_rh], "thermo inputs")
    before = _array(species, "species")
    maximum_t = THERMO_T0 if over_ice else MAX_TEMPERATURE_K
    if inputs.shape != (3,) or before.shape != (6,):
        raise ValueError("thermo requires scalar inputs and six species")
    if not 100.0 <= pressure <= 120000.0 or not 0.0 <= target_rh <= 1.0:
        raise ValueError("pressure or target RH outside range")
    if not MIN_TEMPERATURE_K <= temperature <= maximum_t:
        raise ValueError("initial temperature outside phase range")
    if np.any(before < 0.0) or np.any(before > MAX_FLOAT32) or before[0] > float(np.float32(0.2)):
        raise ValueError("initial species outside range")

    phase = 2 if over_ice else 1
    with localcontext() as context:
        context.prec = _DECIMAL_PRECISION
        point = lambda value: _decimal_interval(_decimal_float(value))
        p = point(pressure)
        initial_t = point(temperature)
        initial_q = [point(value) for value in before]
        rh = point(target_rh)
        t0 = point(THERMO_T0)
        cp_dry = point(THERMO_CP_DRY)
        cp = [point(value) for value in THERMO_SPECIES_CP]
        h0 = [point(value) for value in THERMO_SPECIES_H0]
        capacity = cp_dry
        for index in range(6):
            capacity = _decimal_add(capacity, _decimal_multiply(cp[index], initial_q[index]))
        delta_cp = _decimal_subtract(cp[0], cp[phase])
        latent = _decimal_add(
            _decimal_subtract(h0[0], h0[phase]),
            _decimal_multiply(delta_cp, _decimal_subtract(initial_t, t0)),
        )
        zero = point(0.0)
        vapor_cap = _decimal_subtract(point(float(np.float32(0.2))), initial_q[0])

        def transfer_at_temperature(bound: Decimal) -> _DecimalInterval:
            offset = _decimal_subtract(initial_t, point(bound))
            denominator = _decimal_subtract(
                latent, _decimal_multiply(offset, delta_cp)
            )
            return _decimal_divide(_decimal_multiply(offset, capacity), denominator)

        lower_constraint = transfer_at_temperature(maximum_t)
        upper_temperature_constraint = transfer_at_temperature(MIN_TEMPERATURE_K)
        # Use inner feasible endpoints.  The outward interval endpoint for
        # T(max/min) is deliberately advanced into the physical domain; if
        # that loses a root by one Decimal ulp, the sign gate below rejects
        # rather than certifying an out-of-range root.
        lower = max(initial_q[0].upper.copy_negate(), lower_constraint.upper)
        upper = min(
            initial_q[phase].lower,
            vapor_cap.lower,
            upper_temperature_constraint.lower,
        )
        if lower > upper:
            raise ValueError("no certified saturation transfer interval")
        phase_is_upper_constraint = initial_q[phase].upper <= min(
            vapor_cap.lower, upper_temperature_constraint.lower
        )

        def evaluate(transfer: Decimal) -> tuple[Decimal, Decimal, _DecimalInterval]:
            return _decimal_transfer_residual(
                p, initial_t, initial_q[0], rh, transfer,
                capacity, latent, delta_cp, over_ice,
            )

        low_lower, low_upper, _ = evaluate(lower)
        high_lower, high_upper, _ = evaluate(upper)
        residual_error = max(
            low_upper - low_lower, high_upper - high_lower
        )
        exhausted = False
        if low_lower > 0:
            raise ValueError("no certified saturation equilibrium below lower bound")
        if low_lower == 0 and low_upper == 0:
            transfer_lower = transfer_upper = lower
        elif low_lower <= 0 <= low_upper:
            raise ValueError("lower saturation residual sign is uncertified")
        elif high_upper < 0:
            if not phase_is_upper_constraint:
                raise ValueError("saturation equilibrium is outside canonical bounds")
            exhausted = True
            transfer_lower = transfer_upper = initial_q[phase].lower
        elif high_lower <= 0 <= high_upper:
            raise ValueError("upper saturation residual sign is uncertified")
        else:
            negative, positive = lower, upper
            transfer_lower, transfer_upper = negative, positive
            for _ in range(200):
                middle = (negative + positive) / Decimal(2)
                residual_lower, residual_upper, _ = evaluate(middle)
                residual_error = max(
                    residual_error, residual_upper - residual_lower
                )
                if residual_upper < 0:
                    negative = middle
                    transfer_lower = negative
                elif residual_lower > 0:
                    positive = middle
                    transfer_upper = positive
                else:
                    # F'(e)>=1.  If zero lies in F(m), this radius encloses
                    # every possible root despite the interval evaluation.
                    transfer_lower = max(
                        lower,
                        _decimal_subtract(
                            _decimal_interval(middle),
                            _decimal_interval(max(Decimal(0), residual_upper)),
                        ).lower,
                    )
                    transfer_upper = min(
                        upper,
                        _decimal_subtract(
                            _decimal_interval(middle),
                            _decimal_interval(min(Decimal(0), residual_lower)),
                        ).upper,
                    )
                    break
            else:
                transfer_lower, transfer_upper = negative, positive

        transfer_center = (transfer_lower + transfer_upper) / Decimal(2)
        center_temperature = _decimal_temperature_interval_for_transfer(
            initial_t, _decimal_interval(transfer_center), capacity, latent, delta_cp
        )
        temperature_interval = _decimal_temperature_interval_for_transfer(
            initial_t, _DecimalInterval(transfer_lower, transfer_upper),
            capacity, latent, delta_cp,
        )
        physical_lower = _decimal_float(MIN_TEMPERATURE_K)
        physical_upper = _decimal_float(maximum_t)
        temperature_interval = _DecimalInterval(
            max(physical_lower, temperature_interval.lower),
            min(physical_upper, temperature_interval.upper),
        )
        vapor_interval = _decimal_add(initial_q[0], _DecimalInterval(transfer_lower, transfer_upper))
        phase_interval = _decimal_subtract(initial_q[phase], _DecimalInterval(transfer_lower, transfer_upper))
        species_lower_decimal = [value.lower for value in initial_q]
        species_upper_decimal = [value.upper for value in initial_q]
        species_lower_decimal[0], species_upper_decimal[0] = max(zero.lower, vapor_interval.lower), vapor_interval.upper
        species_lower_decimal[phase], species_upper_decimal[phase] = max(zero.lower, phase_interval.lower), phase_interval.upper
        equilibrium_temperature = float(center_temperature.lower + (center_temperature.upper - center_temperature.lower) / Decimal(2))
        equilibrium_species = np.asarray(
            [float(initial_q[index].lower + (transfer_center if index == 0 else -transfer_center if index == phase else Decimal(0)))
             for index in range(6)], dtype=np.float64
        )
        temperature_bounds = _outward_float_interval(
            temperature_interval.lower, temperature_interval.upper
        )
        species_bounds = (
            np.asarray(
                [max(0.0, _outward_float_interval(lower_value, upper_value)[0])
                 for lower_value, upper_value in zip(species_lower_decimal, species_upper_decimal)],
                dtype=np.float64,
            ),
            np.asarray(
                [_outward_float_interval(lower_value, upper_value)[1]
                 for lower_value, upper_value in zip(species_lower_decimal, species_upper_decimal)],
                dtype=np.float64,
            ),
        )
        stored_temperature_bounds = _stored_float32_interval(
            temperature_interval.lower, temperature_interval.upper
        )
        stored_species_bounds = (
            np.asarray(
                [_stored_float32_interval(lower_value, upper_value)[0]
                 for lower_value, upper_value in zip(species_lower_decimal, species_upper_decimal)],
                dtype=np.float64,
            ),
            np.asarray(
                [_stored_float32_interval(lower_value, upper_value)[1]
                 for lower_value, upper_value in zip(species_lower_decimal, species_upper_decimal)],
                dtype=np.float64,
            ),
        )
    return ThermoEquilibriumCertificate(
        equilibrium_temperature=equilibrium_temperature,
        equilibrium_species=equilibrium_species,
        temperature_bounds=temperature_bounds,
        species_bounds=species_bounds,
        stored_temperature_bounds=stored_temperature_bounds,
        stored_species_bounds=stored_species_bounds,
        exhausted=exhausted,
        residual_error=float(residual_error),
    )


def reconstruct_thermo_state_reference(
    pressure: np.ndarray,
    pressure_mass: np.ndarray,
    temperature: np.ndarray,
    species: np.ndarray,
    support: np.ndarray,
    surface: np.ndarray,
    target_rh: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Reconstruct stored post-thermo donors from the pre-thermo proposal.

    All cell arrays share a shape; species adds a leading six-species axis.
    Pressure mass is zero outside the represented domain. Dry mass is fixed
    from the proposal, before phase-transfer float32 rounding. Unsupported
    values are retained, including below-ground temperature placeholders.
    """
    p = _array(pressure, "pressure")
    mass = _array(pressure_mass, "pressure_mass")
    initial_t = _array(temperature, "temperature")
    before = _array(species, "species")
    selected = np.asarray(support)
    phase = _array(surface, "surface")
    if (p.shape != initial_t.shape or mass.shape != initial_t.shape
            or selected.shape != initial_t.shape or phase.shape != initial_t.shape
            or before.shape != (6, *initial_t.shape)):
        raise ValueError("thermo reconstruction shapes differ")
    if selected.dtype != np.dtype(bool):
        raise ValueError("thermo support must be boolean")
    if (np.any(mass < 0.0) or np.any(before < 0.0)
            or np.any(before > MAX_FLOAT32)):
        raise ValueError("negative mass or invalid proposal species")
    if np.any(selected & (mass == 0.0)):
        raise ValueError("thermo support outside represented domain")
    if np.any(selected & (phase != 1) & (phase != 2)):
        raise ValueError("unsupported thermo phase")
    if not np.isfinite(target_rh) or not 0.0 <= target_rh <= 1.0:
        raise ValueError("target RH outside range")

    dry_mass = mass / (1.0 + np.sum(before, axis=0))
    stored_t, stored_q = initial_t.copy(), before.copy()
    for index in zip(*np.nonzero(selected)):
        cell = (slice(None), *index)
        adjusted_t, adjusted_q = saturation_adjust_reference(
            float(p[index]), float(initial_t[index]), before[cell], target_rh,
            over_ice=phase[index] == 2,
        )
        stored_t[index] = float(np.float32(adjusted_t))
        stored_q[cell] = adjusted_q.astype(np.float32).astype(np.float64)
    return stored_t, stored_q, dry_mass


def surface_geopotential_profile_reference(
    pressure, temperature, species, surface_pressure, surface_temperature,
    surface_vapor, surface_height,
) -> np.ndarray:
    """Integrate full-mixture specific volume in log pressure from terrain.

    Inputs contain active centers only, ordered from bottom to top. Surface
    condensate is zero under the existing surface-boundary contract.
    """
    p = _array(pressure, "pressure")
    t = _array(temperature, "temperature")
    q = _array(species, "species")
    surface = _array(
        [surface_pressure, surface_temperature, surface_vapor, surface_height],
        "surface state",
    )
    if p.ndim != 1 or p.size == 0 or t.shape != p.shape or q.shape != (6, p.size):
        raise ValueError("geopotential column shapes differ")
    if (surface.shape != (4,) or np.any(p <= 0.0) or np.any(np.diff(p) >= 0.0)
            or surface[0] < p[0]):
        raise ValueError("invalid geopotential pressure column")
    if (np.any((t < 150.0) | (t > 350.0)) or not 150.0 <= surface[1] <= 350.0
            or np.any(q < 0.0) or np.any(q > MAX_FLOAT32)
            or np.any(q[0] > float(np.float32(0.2))) or not 0.0 <= surface[2] <= 0.1):
        raise ValueError("invalid geopotential thermodynamics")
    alpha = 287.05 * t * (1.0 + q[0] / 0.622) / (1.0 + q.sum(axis=0))
    surface_alpha = 287.05 * surface[1] * (1.0 + surface[2] / 0.622) / (1.0 + surface[2])
    bottom = 9.80665 * surface[3] + 0.5 * (surface_alpha + alpha[0]) * np.log(surface[0] / p[0])
    increments = 0.5 * (alpha[:-1] + alpha[1:]) * np.log(p[:-1] / p[1:])
    profile = np.r_[bottom, bottom + np.cumsum(increments)]
    if not np.all(np.isfinite(profile)):
        raise ValueError("non-finite geopotential profile")
    return profile


def transition_geopotential_reference(
    pressure, old_geopotential, old_temperature, old_species,
    final_temperature, final_species, old_surface_pressure, new_surface_pressure,
    surface_temperature, surface_vapor, surface_height, *,
    seed_geopotential=None, seed_temperature=None, seed_species=None,
) -> np.ndarray:
    """Replay the positive-PS stage, preserving old and new-cell Phi residuals.

    Old inputs are the stored post-thermo/Phi state, not the original analysis.
    Pressure and final fields cover the final active domain, with at most one
    added bottom center. A seed is used only for that added center. This is a
    numerical reference; it grants neither input authority nor native closure.
    """
    p = _array(pressure, "pressure")
    phi = _array(old_geopotential, "old geopotential")
    old_t = _array(old_temperature, "old temperature")
    old_q = _array(old_species, "old species")
    ps = _array([old_surface_pressure, new_surface_pressure], "surface pressures")
    if p.ndim != 1 or phi.ndim != 1 or phi.size == 0:
        raise ValueError("invalid transition geopotential shape")
    added = p.size - phi.size
    if added not in (0, 1) or old_t.shape != phi.shape or old_q.shape != (6, phi.size):
        raise ValueError("transition must retain old centers and add at most one")
    if ps.shape != (2,) or not 0.0 < ps[1] - ps[0] <= 100.0:
        raise ValueError("transition requires a positive PS increment of at most 100 Pa")
    if added and ps[0] >= p[0]:
        raise ValueError("new center was already pressure accessible")

    old_profile = surface_geopotential_profile_reference(
        p[added:], old_t, old_q, ps[0], surface_temperature, surface_vapor, surface_height,
    )
    final_profile = surface_geopotential_profile_reference(
        p, final_temperature, final_species, ps[1], surface_temperature, surface_vapor, surface_height,
    )
    expected = np.empty(p.size, dtype=np.float64)
    expected[added:] = phi + final_profile[added:] - old_profile
    if added:
        seed = _array([seed_geopotential, seed_temperature], "new-center seed")
        seed_q = _array(seed_species, "new-center species")
        if seed.shape != (2,) or seed_q.shape != (6,):
            raise ValueError("new center requires scalar Phi/T and six species")
        prior_profile = surface_geopotential_profile_reference(
            p, np.r_[seed[1], old_t], np.column_stack((seed_q, old_q)),
            ps[1], surface_temperature, surface_vapor, surface_height,
        )
        expected[0] = seed[0] + final_profile[0] - prior_profile[0]
    if np.any(~np.isfinite(expected)) or np.any(np.abs(expected) > MAX_FLOAT32):
        raise ValueError("transition geopotential exceeds float32 storage range")
    return expected.astype(np.float32).astype(np.float64)


__all__ = [
    "surface_geopotential_profile_reference",
    "transition_geopotential_reference",
    "reconstruct_prebalance_winds",
    "remap_surface_pressure_reference",
    "remap_pressure_state_reference",
    "reconstruct_thermo_state_reference",
    "saturation_adjust_reference",
    "saturation_equilibrium_certificate_reference",
    "ThermoEquilibriumCertificate",
    "remap_pressure_column_reference",
    "remap_pressure_column_bounds_reference",
    "remap_pressure_column_intervals_reference",
    "THERMO_T0",
    "THERMO_CP_DRY",
    "THERMO_SPECIES_CP",
    "THERMO_SPECIES_H0",
]
