#!/usr/bin/env python3
"""Validate numerical content in one Cloud-BAL SHADOW diagnostic file.

This standalone check does not establish source or build provenance.  A result
becomes evidence only after the generation transaction binds it to a clean
source commit, pinned inputs, and pinned build dependencies.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import netCDF4
import numpy as np
from scipy.ndimage import distance_transform_edt


FLOAT_UNITS = {
    "radar_dbz": "dBZ",
    "background_u": "m s-1",
    "background_v": "m s-1",
    "background_omega": "Pa s-1",
    "candidate_u": "m s-1",
    "candidate_v": "m s-1",
    "candidate_omega": "Pa s-1",
    "omega_target": "Pa s-1",
    "background_cloud_water": "kg kg-1 dryair",
    "background_cloud_ice": "kg kg-1 dryair",
    "background_rain": "kg kg-1 dryair",
    "background_snow": "kg kg-1 dryair",
    "background_graupel": "kg kg-1 dryair",
    "candidate_cloud_water": "kg kg-1 dryair",
    "candidate_cloud_ice": "kg kg-1 dryair",
    "candidate_rain": "kg kg-1 dryair",
    "candidate_snow": "kg kg-1 dryair",
    "candidate_graupel": "kg kg-1 dryair",
    "balance_beta": "1",
    "continuity_background": "s-1",
    "continuity_candidate": "s-1",
}
MASKS = (
    "above_ground",
    "radar_valid",
    "radar_coverage",
    "radar_no_echo",
    "radar_missing",
    "omega_target_valid",
    "omega_target_authority",
    "candidate_balance_support",
    "column_changed",
    "balance_changed",
    "overall_changed",
    "obs_support",
    "hydro_support",
)
TARGET_METADATA = ("omega_target_quality", "omega_target_source")
BOUNDARY_METADATA = (
    "omega_top_boundary_quality",
    "omega_top_boundary_source",
    "omega_bottom_boundary_quality",
    "omega_bottom_boundary_source",
)
BOUNDARY_MASKS = (
    "omega_top_boundary_valid",
    "omega_bottom_boundary_valid",
)
HYDROMETEORS = ("cloud_water", "cloud_ice", "rain", "snow", "graupel")
STATUS_DEGRADED = 10
STATUS_OK = 20
REASON_GATE = 7
SOLVER_NOT_RUN = 0
SOLVER_CONVERGED = 1
GATE_INCREMENT_RMS = 1 << 0
GATE_INCREMENT_MAX = 1 << 1
GATE_PHYSICAL_RMS = 1 << 2
GATE_PHYSICAL_MAX = 1 << 3
GATE_WIND_INCREMENT = 1 << 4
GATE_OMEGA_INCREMENT = 1 << 5
GATE_TARGET_RESPONSE = 1 << 6
GATE_GEOSTROPHIC = 1 << 7
GATE_OUTSIDE_SUPPORT = 1 << 8
GATE_TARGET_FRACTION = 1 << 9
GATE_OPERATOR_IDENTITY = 1 << 10
SOURCE_CONVENTIONAL_OBS = 1 << 1
SOURCE_RADAR_VRAD = 1 << 4
SOURCE_ANALYZED_WIND = 1 << 6
SOURCE_DYNAMIC_TARGET = 1 << 10
SOURCE_BOUNDARY_CONDITION = 1 << 11
SOURCE_KNOWN_BITS = (1 << 12) - 1
SOURCE_DYNAMIC_EVIDENCE_BITS = (
    SOURCE_CONVENTIONAL_OBS | SOURCE_RADAR_VRAD | SOURCE_ANALYZED_WIND
)
QUALITY_BOUNDARY_INTERIOR_COPY = 1 << 9
QUALITY_KNOWN_BITS = (1 << 10) - 1
QUALITY_EXCLUDED_BITS = (1 << 0) | (1 << 1) | (1 << 2)
QUALITY_DYNAMIC_TARGET_EXCLUDED_BITS = (
    QUALITY_EXCLUDED_BITS | (1 << 4) | (1 << 5) |
    (1 << 6) | (1 << 7) | (1 << 8) | QUALITY_BOUNDARY_INTERIOR_COPY
)
EXPECTED_FLOAT_ATTRIBUTES = {
    "minimum_usable_dbz": 0.0,
    "maximum_usable_dbz": 80.0,
    "configured_assumed_radar_wavelength_m": 0.10,
    "reference_mass_concentration": 1.0e-4,
    "minimum_relative_fall_speed": 0.30,
    "maximum_horizontal_substep": 0.75,
    "precipitation_loading_efficiency": 0.08,
    "maximum_downdraft_ms": 3.0,
    "maximum_downdraft_innovation_ms": 2.0,
    "ledger_relative_tolerance": 1.0e-11,
    "ledger_absolute_tolerance": 1.0e-13,
    "horizontal_support_radius_m": 10_000.0,
    "pressure_support_radius_pa": 20_000.0,
    "minimum_balance_beta": 1.0e-3,
    "kappa_u": 16.0,
    "kappa_v": 16.0,
    "kappa_omega": 0.25,
    "maximum_wind_increment_ms": 10.0,
    "maximum_omega_increment_pas": 5.0,
    "increment_headroom": 0.95,
    "solver_residual_fraction": 2.0e-3,
    "required_residual_fraction": 0.25,
    "minimum_target_response_ratio": 0.05,
    "maximum_target_response_ratio": 1.50,
    "minimum_trust_region_fraction": 0.05,
    "physical_residual_tolerance": 1.0e-7,
    "maximum_physical_residual": 1.0e-3,
    "operator_identity_tolerance": 1.0e-12,
    "geostrophic_relative_tolerance": 0.05,
    "geostrophic_absolute_tolerance": 1.0e-3,
    "grid_dx_m": 5_000.0,
    "grid_dy_m": 5_000.0,
}


def values(variable: netCDF4.Variable) -> np.ndarray:
    data = variable[:]
    if np.ma.isMaskedArray(data) and np.any(np.ma.getmaskarray(data)):
        raise ValueError(f"masked NetCDF values are forbidden: {variable.name}")
    return np.ascontiguousarray(np.ma.getdata(data))


def is_signed_int32(dtype: np.dtype) -> bool:
    """Match the signed 32-bit integer type written by NF90_INT."""
    parsed = np.dtype(dtype)
    return parsed.kind == "i" and parsed.itemsize == 4


def canonical_omega_target_cells(
    valid: np.ndarray,
    above_ground: np.ndarray,
    quality: np.ndarray,
    source: np.ndarray,
    target: np.ndarray,
) -> np.ndarray:
    """Return the canonical contract result for every omega-target cell."""
    usable = (
        above_ground
        & (source > 0)
        & ((quality & QUALITY_EXCLUDED_BITS) == 0)
        & np.isfinite(target)
        & (np.abs(target) <= 100.0)
    )
    return ~valid | usable


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def changed_bits(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    if left.dtype != np.float32 or right.dtype != np.float32:
        raise TypeError("bitwise field comparison requires float32")
    return left.view(np.uint32) != right.view(np.uint32)


def percentile(values_: np.ndarray, levels: tuple[int, ...]) -> dict[str, float]:
    if values_.size == 0:
        return {str(level): 0.0 for level in levels}
    result = np.percentile(values_, levels)
    return {str(level): float(value) for level, value in zip(levels, result)}


def reconstruct_beta(
    source: np.ndarray,
    above_ground: np.ndarray,
    pressure: np.ndarray,
    dx: float,
    dy: float,
    horizontal_radius: float,
    pressure_radius: float,
) -> np.ndarray:
    """Reproduce the small Wendland-C2 localization stencil."""
    nz, ny, nx = source.shape
    expected = np.zeros(source.shape, dtype=np.float32)
    max_di = min(nx - 1, int(np.ceil(horizontal_radius / dx)))
    max_dj = min(ny - 1, int(np.ceil(horizontal_radius / dy)))
    for source_k in range(nz):
        for target_k in range(nz):
            pressure_distance = abs(float(pressure[target_k] - pressure[source_k]))
            if pressure_distance >= pressure_radius:
                continue
            for dj in range(-max_dj, max_dj + 1):
                for di in range(-max_di, max_di + 1):
                    horizontal_distance = np.hypot(di * dx, dj * dy)
                    radius = np.hypot(
                        horizontal_distance / horizontal_radius,
                        pressure_distance / pressure_radius,
                    )
                    if radius >= 1.0:
                        continue
                    weight = np.float32((1.0 - radius) ** 4 * (1.0 + 4.0 * radius))
                    source_x = slice(max(0, -di), min(nx, nx - di))
                    target_x = slice(max(0, di), min(nx, nx + di))
                    source_y = slice(max(0, -dj), min(ny, ny - dj))
                    target_y = slice(max(0, dj), min(ny, ny + dj))
                    contribution = weight * source[source_k, source_y, source_x]
                    target = expected[target_k, target_y, target_x]
                    np.maximum(target, contribution, out=target)
    expected[~above_ground] = 0.0
    expected[source] = 1.0
    return expected


def continuity_increment(
    du: np.ndarray,
    dv: np.ndarray,
    domega: np.ndarray,
    active: np.ndarray,
    dx: float,
    dy: float,
    pressure: np.ndarray,
    pressure_interface: np.ndarray,
    cell_dp: np.ndarray,
) -> np.ndarray:
    """Independent finite-volume D*S using the persisted pressure geometry."""
    residual = np.zeros(du.shape, dtype=np.float64)
    volume = dx * dy * cell_dp

    xface = active[:, :, :-1] & active[:, :, 1:]
    xarea = dy * 0.5 * (cell_dp[:, :, :-1] + cell_dp[:, :, 1:])
    xflux = np.where(xface, xarea * 0.5 * (du[:, :, :-1] + du[:, :, 1:]), 0.0)
    residual[:, :, :-1] += np.divide(
        xflux, volume[:, :, :-1], out=np.zeros_like(xflux), where=xface
    )
    residual[:, :, 1:] -= np.divide(
        xflux, volume[:, :, 1:], out=np.zeros_like(xflux), where=xface
    )

    yface = active[:, :-1, :] & active[:, 1:, :]
    yarea = dx * 0.5 * (cell_dp[:, :-1, :] + cell_dp[:, 1:, :])
    yflux = np.where(yface, yarea * 0.5 * (dv[:, :-1, :] + dv[:, 1:, :]), 0.0)
    residual[:, :-1, :] += np.divide(
        yflux, volume[:, :-1, :], out=np.zeros_like(yflux), where=yface
    )
    residual[:, 1:, :] -= np.divide(
        yflux, volume[:, 1:, :], out=np.zeros_like(yflux), where=yface
    )

    pface = active[:-1, :, :] & active[1:, :, :]
    denominator = pressure[:-1] - pressure[1:]
    left_weight = (
        pressure_interface[1:-1] - pressure[1:, None, None]
    ) / denominator[:, None, None]
    pflux = np.where(
        pface,
        dx * dy * (
            left_weight * domega[:-1, :, :]
            + (1.0 - left_weight) * domega[1:, :, :]
        ),
        0.0,
    )
    residual[:-1, :, :] -= np.divide(
        pflux, volume[:-1, :, :], out=np.zeros_like(pflux), where=pface
    )
    residual[1:, :, :] += np.divide(
        pflux, volume[1:, :, :], out=np.zeros_like(pflux), where=pface
    )
    residual[~active] = 0.0
    return residual


def continuity_state(
    u: np.ndarray,
    v: np.ndarray,
    omega: np.ndarray,
    omega_top_boundary: np.ndarray,
    omega_bottom_boundary: np.ndarray,
    active: np.ndarray,
    above_ground: np.ndarray,
    dx: float,
    dy: float,
    pressure: np.ndarray,
    pressure_interface: np.ndarray,
    cell_dp: np.ndarray,
) -> np.ndarray:
    """Independent full-state finite-volume residual from persisted geometry."""
    residual = np.zeros(u.shape, dtype=np.float64)
    volume = dx * dy * cell_dp

    xface = above_ground[:, :, :-1] & above_ground[:, :, 1:]
    xarea = dy * 0.5 * (cell_dp[:, :, :-1] + cell_dp[:, :, 1:])
    xflux = np.where(xface, xarea * 0.5 * (u[:, :, :-1] + u[:, :, 1:]), 0.0)
    residual[:, :, :-1] += np.divide(
        xflux,
        volume[:, :, :-1],
        out=np.zeros_like(xflux),
        where=active[:, :, :-1],
    )
    residual[:, :, 1:] -= np.divide(
        xflux,
        volume[:, :, 1:],
        out=np.zeros_like(xflux),
        where=active[:, :, 1:],
    )
    residual[:, :, 0] -= np.where(active[:, :, 0], u[:, :, 0] / dx, 0.0)
    residual[:, :, -1] += np.where(active[:, :, -1], u[:, :, -1] / dx, 0.0)

    yface = above_ground[:, :-1, :] & above_ground[:, 1:, :]
    yarea = dx * 0.5 * (cell_dp[:, :-1, :] + cell_dp[:, 1:, :])
    yflux = np.where(yface, yarea * 0.5 * (v[:, :-1, :] + v[:, 1:, :]), 0.0)
    residual[:, :-1, :] += np.divide(
        yflux,
        volume[:, :-1, :],
        out=np.zeros_like(yflux),
        where=active[:, :-1, :],
    )
    residual[:, 1:, :] -= np.divide(
        yflux,
        volume[:, 1:, :],
        out=np.zeros_like(yflux),
        where=active[:, 1:, :],
    )
    residual[:, 0, :] -= np.where(active[:, 0, :], v[:, 0, :] / dy, 0.0)
    residual[:, -1, :] += np.where(active[:, -1, :], v[:, -1, :] / dy, 0.0)

    pface = above_ground[:-1, :, :] & above_ground[1:, :, :]
    denominator = pressure[:-1] - pressure[1:]
    left_weight = (
        pressure_interface[1:-1] - pressure[1:, None, None]
    ) / denominator[:, None, None]
    pflux = np.where(
        pface,
        dx * dy * (
            left_weight * omega[:-1, :, :]
            + (1.0 - left_weight) * omega[1:, :, :]
        ),
        0.0,
    )
    residual[:-1, :, :] -= np.divide(
        pflux,
        volume[:-1, :, :],
        out=np.zeros_like(pflux),
        where=active[:-1, :, :],
    )
    residual[1:, :, :] += np.divide(
        pflux,
        volume[1:, :, :],
        out=np.zeros_like(pflux),
        where=active[1:, :, :],
    )

    for j, i in np.argwhere(np.any(above_ground, axis=0)):
        levels = np.flatnonzero(above_ground[:, j, i])
        bottom, top = int(levels[0]), int(levels[-1])
        if active[bottom, j, i]:
            residual[bottom, j, i] += (
                dx * dy * omega_bottom_boundary[j, i] / volume[bottom, j, i]
            )
        if active[top, j, i]:
            residual[top, j, i] -= (
                dx * dy * omega_top_boundary[j, i] / volume[top, j, i]
            )
    residual[~active] = 0.0
    return residual


def validate(path: Path) -> tuple[dict[str, object], list[str]]:
    failures: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    with netCDF4.Dataset(path, "r") as dataset:
        require(
            {name: len(dim) for name, dim in dataset.dimensions.items()}
            == {"x": 235, "y": 283, "z": 22, "z_interface": 23, "z_spacing": 21},
            "pressure geometry dimensions",
        )
        require(getattr(dataset, "contract", "") == "real_radar_only_shadow_v3", "contract")
        require(int(getattr(dataset, "diagnostic_schema_version", -1)) == 5, "diagnostic schema")
        require(
            getattr(dataset, "evidence_class", "")
            == "REAL_RADAR_ONLY_SHADOW_PROPOSAL",
            "evidence class",
        )
        require(
            getattr(dataset, "configuration_id", "") == "real-radar-only-shadow-v3",
            "configuration identity",
        )
        require(
            getattr(dataset, "result_authority", "") == "DIAGNOSTIC_PROPOSAL_ONLY",
            "result authority",
        )
        require(
            getattr(dataset, "radar_wavelength_provenance", "")
            == "CONFIGURED_ASSUMPTION_NOT_OBSERVATION",
            "radar wavelength provenance",
        )
        require(
            getattr(dataset, "trajectory_horizontal_frame", "")
            == "INPUT_WIND_NATIVE_UNRESOLVED",
            "trajectory horizontal frame",
        )
        require(
            getattr(dataset, "storm_motion_provenance", "")
            == "NOT_AVAILABLE_ZERO_TRANSLATION_ASSUMPTION",
            "storm-motion provenance",
        )
        require(
            getattr(dataset, "radar_no_echo_transport_policy", "")
            == "DESTINATION_HARD_BLOCK_SEPARATE_LEDGER",
            "no-echo transport policy",
        )
        require(getattr(dataset, "radar_valid_semantics", "") == "ECHO_ONLY", "radar valid semantics")
        require(
            getattr(dataset, "pressure_interface_semantics", "")
            == "SURFACE_CLIPPED_CONTROL_VOLUME_BOUNDARY",
            "pressure interface semantics",
        )
        require(
            getattr(dataset, "above_ground_mask_provenance", "")
            == "PSFC_PRESSURE_CENTER_AND_STATIC_TERRAIN_HEIGHT",
            "above-ground mask provenance",
        )
        require(
            getattr(dataset, "grid_spacing_adapter_policy", "")
            == "KM_TO_M_OR_PINNED_LEGACY_NUMERIC_METERS",
            "grid-spacing adapter policy",
        )
        require(
            getattr(dataset, "omega_boundary_provenance", "")
            == "COPIED_INTERIOR_DIAGNOSTIC_ONLY",
            "omega boundary provenance",
        )
        for attribute, expected in (
            ("promotion_eligible", 0),
            ("operational_state_changed", 0),
            ("science_assessed", 0),
            ("cloud_analysis_present", 0),
            ("radar_los_used", 0),
            ("physical_continuity_assessed", 0),
            ("column_status", STATUS_OK),
            ("maximum_solver_iterations", 800),
            ("maximum_transport_substeps", 64),
        ):
            require(int(getattr(dataset, attribute, -999)) == expected, attribute)
        for attribute, expected in EXPECTED_FLOAT_ATTRIBUTES.items():
            require(
                np.isclose(float(getattr(dataset, attribute)), expected, rtol=0.0, atol=1.0e-12),
                attribute,
            )

        pipeline_status = int(getattr(dataset, "pipeline_status", -999))
        balance_status = int(getattr(dataset, "balance_status", -999))
        acceptance_failures = int(getattr(dataset, "acceptance_failures", -1))
        accepted = pipeline_status == STATUS_OK
        require(balance_status == pipeline_status, "pipeline/balance status agreement")
        require(pipeline_status in (STATUS_DEGRADED, STATUS_OK), "pipeline status")
        if not accepted:
            require(int(getattr(dataset, "pipeline_reason", -1)) == REASON_GATE, "rejection reason")

        required = set(FLOAT_UNITS) | set(MASKS) | set(TARGET_METADATA) | \
            set(BOUNDARY_METADATA) | set(BOUNDARY_MASKS) | {
            "pressure", "latitude", "longitude", "pressure_interface", "cell_dp",
            "level_spacing_dp", "pressure_mass_measure", "dry_air_mass_measure",
            "surface_pressure", "omega_top_boundary", "omega_bottom_boundary",
        }
        require(required <= set(dataset.variables), "required variables")
        for name, dimensions, unit in (
            ("pressure", ("z",), "Pa"),
            ("latitude", ("y", "x"), "degree_north"),
            ("longitude", ("y", "x"), "degree_east"),
            ("pressure_interface", ("z_interface", "y", "x"), "Pa"),
            ("cell_dp", ("z", "y", "x"), "Pa"),
            ("level_spacing_dp", ("z_spacing", "y", "x"), "Pa"),
            ("pressure_mass_measure", ("z", "y", "x"), "kg"),
            ("dry_air_mass_measure", ("z", "y", "x"), "kg dryair"),
            ("surface_pressure", ("y", "x"), "Pa"),
            ("omega_top_boundary", ("y", "x"), "Pa s-1"),
            ("omega_bottom_boundary", ("y", "x"), "Pa s-1"),
        ):
            if name not in dataset.variables:
                continue
            variable = dataset.variables[name]
            require(variable.dimensions == dimensions, f"{name} dimensions")
            require(getattr(variable, "units", "") == unit, f"{name} units")
        for name, unit in FLOAT_UNITS.items():
            if name not in dataset.variables:
                continue
            variable = dataset.variables[name]
            require(variable.dimensions == ("z", "y", "x"), f"{name} dimensions")
            require(getattr(variable, "units", "") == unit, f"{name} units")
        for name in MASKS:
            if name not in dataset.variables:
                continue
            variable = dataset.variables[name]
            require(variable.dimensions == ("z", "y", "x"), f"{name} dimensions")
            require(getattr(variable, "units", "") == "1", f"{name} units")
            require(is_signed_int32(variable.dtype), f"{name} type")
        for name in TARGET_METADATA:
            if name not in dataset.variables:
                continue
            variable = dataset.variables[name]
            require(variable.dimensions == ("z", "y", "x"), f"{name} dimensions")
            require(getattr(variable, "units", "") == "1", f"{name} units")
            require(is_signed_int32(variable.dtype), f"{name} type")
        for name in BOUNDARY_METADATA:
            if name not in dataset.variables:
                continue
            variable = dataset.variables[name]
            require(variable.dimensions == ("y", "x"), f"{name} dimensions")
            require(getattr(variable, "units", "") == "1", f"{name} units")
            require(is_signed_int32(variable.dtype), f"{name} type")
        for name in BOUNDARY_MASKS:
            if name not in dataset.variables:
                continue
            variable = dataset.variables[name]
            require(variable.dimensions == ("y", "x"), f"{name} dimensions")
            require(getattr(variable, "units", "") == "1", f"{name} units")
            require(is_signed_int32(variable.dtype), f"{name} type")

        pressure = values(dataset["pressure"]).astype(np.float64)
        require(np.all(np.isfinite(pressure)) and np.all(np.diff(pressure) < 0.0), "pressure order")
        pressure_interface = values(dataset["pressure_interface"]).astype(np.float64)
        cell_dp = values(dataset["cell_dp"]).astype(np.float64)
        level_spacing_dp = values(dataset["level_spacing_dp"]).astype(np.float64)
        pressure_mass = values(dataset["pressure_mass_measure"]).astype(np.float64)
        dry_air_mass = values(dataset["dry_air_mass_measure"]).astype(np.float64)
        surface_pressure = values(dataset["surface_pressure"]).astype(np.float64)
        omega_top_boundary = values(dataset["omega_top_boundary"]).astype(np.float64)
        omega_bottom_boundary = values(dataset["omega_bottom_boundary"]).astype(np.float64)
        boundary_metadata = {
            name: values(dataset[name]).astype(np.int64) for name in BOUNDARY_METADATA
        }
        boundary_masks = {
            name: values(dataset[name]).astype(np.int64) for name in BOUNDARY_MASKS
        }
        require(np.all(np.isfinite(pressure_interface)) and np.all(pressure_interface > 0.0), "pressure interface")
        require(np.all(np.isfinite(cell_dp)) and np.all(cell_dp >= 0.0), "cell dp")
        require(np.all(np.isfinite(level_spacing_dp)) and np.all(level_spacing_dp > 0.0), "level spacing")
        require(np.all(np.isfinite(pressure_mass)) and np.all(pressure_mass >= 0.0), "pressure mass")
        require(np.all(np.isfinite(dry_air_mass)) and np.all(dry_air_mass >= 0.0), "dry-air mass")
        require(np.all(np.isfinite(surface_pressure)) and np.all(surface_pressure > 0.0), "surface pressure")
        require(np.all(np.isfinite(omega_top_boundary)), "top omega boundary")
        require(np.all(np.isfinite(omega_bottom_boundary)), "bottom omega boundary")
        for name, mask in boundary_masks.items():
            require(np.all((mask == 0) | (mask == 1)), f"{name} binary")
            require(np.all(mask == 1), f"{name} complete coverage")
        for name in ("omega_top_boundary_quality", "omega_bottom_boundary_quality"):
            require(
                np.all((boundary_metadata[name] & ~QUALITY_KNOWN_BITS) == 0),
                f"{name} known bits",
            )
            require(
                np.all(
                    (boundary_metadata[name] & QUALITY_BOUNDARY_INTERIOR_COPY) != 0
                ),
                f"{name} copied-interior provenance",
            )
        for name in ("omega_top_boundary_source", "omega_bottom_boundary_source"):
            require(
                np.all((boundary_metadata[name] & ~SOURCE_KNOWN_BITS) == 0),
                f"{name} known bits",
            )
            require(
                np.all((boundary_metadata[name] & SOURCE_ANALYZED_WIND) != 0),
                f"{name} analyzed-wind provenance",
            )
            require(
                np.all((boundary_metadata[name] & SOURCE_BOUNDARY_CONDITION) == 0),
                f"{name} must remain diagnostic-only",
            )
        latitude = values(dataset["latitude"]).astype(np.float64)
        longitude = values(dataset["longitude"]).astype(np.float64)
        require(
            np.all(np.isfinite(latitude))
            and np.all((-90.0 <= latitude) & (latitude <= 90.0)),
            "latitude range",
        )
        require(
            np.all(np.isfinite(longitude))
            and np.all((-180.0 <= longitude) & (longitude <= 180.0)),
            "longitude range",
        )
        fields = {name: values(dataset[name]) for name in FLOAT_UNITS}
        masks = {name: values(dataset[name]) for name in MASKS}
        target_quality_raw = values(dataset["omega_target_quality"])
        target_source_raw = values(dataset["omega_target_source"])
        require(is_signed_int32(target_quality_raw.dtype), "omega target quality unpacked type")
        require(is_signed_int32(target_source_raw.dtype), "omega target source unpacked type")
        target_quality = target_quality_raw.astype(np.int64)
        target_metadata_source = target_source_raw.astype(np.int64)
        for name, field in fields.items():
            require(np.all(np.isfinite(field)), f"{name} finite")
        for name, mask in masks.items():
            require(is_signed_int32(mask.dtype), f"{name} unpacked type")
            require(np.all((mask == 0) | (mask == 1)), f"{name} binary")
            masks[name] = mask.astype(bool)

        above = masks["above_ground"]
        radar = masks["radar_valid"]
        radar_coverage = masks["radar_coverage"]
        radar_no_echo = masks["radar_no_echo"]
        radar_missing = masks["radar_missing"]
        require(np.array_equal(radar_coverage, radar | radar_no_echo), "radar coverage partition")
        require(np.all(~radar_no_echo | ~radar), "echo/no-echo disjointness")
        require(np.all(~radar_coverage | ~radar_missing), "coverage/missing disjointness")
        require(np.all(~radar_no_echo | radar_coverage), "no-echo coverage subset")
        require(
            np.all(~radar_no_echo | (fields["radar_dbz"] == -10.0)),
            "no-echo marker identity",
        )
        require(
            np.all(~radar_missing | (fields["radar_dbz"] == 0.0)),
            "missing-radar marker identity",
        )
        require(
            np.array_equal(above, radar | radar_no_echo | radar_missing),
            "above-ground radar coverage/missing partition",
        )
        pressure_domain = pressure[:, None, None] <= surface_pressure[None, :, :]
        require(
            np.all(np.any(pressure_domain, axis=0)),
            "at least one pressure-domain level per column",
        )
        require(np.all(np.any(above, axis=0)), "at least one active level per column")
        require(
            np.all(~above[:-1] | above[1:]),
            "vertically contiguous above-ground domain",
        )
        pressure_bottom = np.argmax(pressure_domain, axis=0)
        active_bottom = np.argmax(above, axis=0)
        require(
            np.all((active_bottom >= pressure_bottom) &
                   (active_bottom - pressure_bottom <= 1)),
            "pressure/terrain domain alignment",
        )
        expected_interface = np.empty_like(pressure_interface)
        expected_interface[0] = surface_pressure
        for interface_index in range(1, pressure.size):
            midpoint = 0.5 * (
                pressure[interface_index - 1] + pressure[interface_index]
            )
            expected_interface[interface_index] = np.where(
                interface_index <= active_bottom,
                surface_pressure,
                midpoint,
            )
        expected_interface[-1] = np.minimum(
            surface_pressure,
            pressure[-1] - 0.5 * (pressure[-2] - pressure[-1]),
        )
        require(
            np.allclose(
                pressure_interface, expected_interface, rtol=0.0, atol=1.0e-10
            ),
            "canonical pressure-interface construction",
        )
        expected_cell_dp = pressure_interface[:-1] - pressure_interface[1:]
        require(
            np.allclose(pressure_interface[0], surface_pressure, rtol=0.0, atol=1.0e-10),
            "surface pressure/interface identity",
        )
        require(
            np.allclose(
                level_spacing_dp,
                (pressure[:-1] - pressure[1:])[:, None, None],
                rtol=0.0,
                atol=1.0e-10,
            ),
            "pressure center/level spacing identity",
        )
        require(np.allclose(cell_dp, np.where(above, expected_cell_dp, 0.0), rtol=0.0, atol=1.0e-10), "cell dp/interface identity")
        expected_pressure_mass = (
            float(getattr(dataset, "grid_dx_m"))
            * float(getattr(dataset, "grid_dy_m"))
            * cell_dp
            / 9.80665
        )
        require(np.allclose(pressure_mass, expected_pressure_mass, rtol=1.0e-12, atol=1.0e-6), "pressure mass identity")
        require(np.all(dry_air_mass <= pressure_mass + 1.0e-8), "dry-air mass bound")
        require(np.all(cell_dp[~above] == 0.0) and np.all(cell_dp[above] > 0.0), "domain cell thickness")
        require(np.all(~radar | above), "radar cells above ground")
        quality_known = (target_quality >= 0) & (
            (target_quality & ~QUALITY_KNOWN_BITS) == 0
        )
        source_known = (target_metadata_source >= 0) & (
            (target_metadata_source & ~SOURCE_KNOWN_BITS) == 0
        )
        require(np.all(quality_known), "omega target quality bits")
        require(np.all(source_known), "omega target source bits")
        require(
            np.all(
                canonical_omega_target_cells(
                    masks["omega_target_valid"],
                    above,
                    target_quality,
                    target_metadata_source,
                    fields["omega_target"],
                )
            ),
            "canonical omega target cells",
        )
        computed_target_authority = (
            masks["omega_target_valid"]
            & quality_known
            & source_known
            & (target_metadata_source > 0)
            & ((target_metadata_source & SOURCE_DYNAMIC_TARGET) != 0)
            & ((target_metadata_source & SOURCE_DYNAMIC_EVIDENCE_BITS) != 0)
            & ((target_quality & QUALITY_DYNAMIC_TARGET_EXCLUDED_BITS) == 0)
        )
        require(
            np.array_equal(computed_target_authority, masks["omega_target_authority"]),
            "dynamic target authority predicate",
        )
        require(
            np.all(
                ~radar
                | ((fields["radar_dbz"] >= 0.0) & (fields["radar_dbz"] <= 100.0))
            ),
            "radar threshold",
        )
        inactive_radar = ~radar
        require(
            np.all(
                ~inactive_radar
                | ~above
                | (fields["radar_dbz"] == -10.0)
                | (fields["radar_dbz"] == 0.0)
            ),
            "inactive above-ground radar marker",
        )
        require(
            np.all(above | (fields["radar_dbz"] == 0.0)),
            "below-ground radar marker",
        )

        balance_changed = np.zeros(above.shape, dtype=bool)
        for component in ("u", "v", "omega"):
            balance_changed |= changed_bits(
                fields[f"background_{component}"],
                fields[f"candidate_{component}"],
            )
        column_changed = np.zeros(above.shape, dtype=bool)
        for species in HYDROMETEORS:
            before = fields[f"background_{species}"]
            after = fields[f"candidate_{species}"]
            column_changed |= changed_bits(before, after)
            require(np.all(after[above] >= 0.0), f"candidate {species} nonnegative")
        require(np.array_equal(balance_changed, masks["balance_changed"]), "balance changed mask")
        require(np.all(~column_changed | masks["column_changed"]), "column changed mask")
        require(
            np.all(~radar_no_echo | ~column_changed),
            "no-echo cells must not receive hydrometeor changes",
        )
        column_change_evidence = (
            column_changed
            | masks["omega_target_valid"]
            | masks["obs_support"]
            | masks["hydro_support"]
            | radar
        )
        require(
            np.array_equal(masks["column_changed"], column_change_evidence),
            "column changed mask must equal persisted stage evidence",
        )
        require(
            np.array_equal(
                masks["column_changed"] | masks["balance_changed"],
                masks["overall_changed"],
            ),
            "overall changed mask",
        )
        require(np.all(~balance_changed | above), "balance below ground")

        minimum_beta = float(getattr(dataset, "minimum_balance_beta"))
        computed_active = above & (
            fields["balance_beta"].astype(np.float64) > float(np.float32(minimum_beta))
        )
        require(
            np.array_equal(computed_active, masks["candidate_balance_support"]),
            "candidate balance support",
        )

        target_innovation32 = fields["omega_target"] - fields["background_omega"]
        target_resolution = (
            16.0 * np.finfo(np.float32).eps
            * np.maximum(1.0, np.abs(fields["background_omega"]))
        )
        target_source = masks["omega_target_authority"] & (
            np.abs(target_innovation32) > target_resolution
        )
        expected_beta = reconstruct_beta(
            target_source,
            above,
            pressure,
            float(getattr(dataset, "grid_dx_m")),
            float(getattr(dataset, "grid_dy_m")),
            float(getattr(dataset, "horizontal_support_radius_m")),
            float(getattr(dataset, "pressure_support_radius_pa")),
        )
        beta_error = float(np.max(np.abs(expected_beta - fields["balance_beta"])))
        require(beta_error <= 5.0e-6, "localization kernel reconstruction")

        du = fields["candidate_u"].astype(np.float64) - fields["background_u"]
        dv = fields["candidate_v"].astype(np.float64) - fields["background_v"]
        domega = fields["candidate_omega"].astype(np.float64) - fields["background_omega"]
        accepted_target = np.where(target_source, target_innovation32, 0.0).astype(np.float64)
        wind_increment = np.hypot(du, dv)
        actual_max_wind = float(np.max(wind_increment))
        actual_max_omega = float(np.max(np.abs(domega)))
        require(
            np.isclose(actual_max_wind, float(getattr(dataset, "max_wind_increment_ms")), atol=1e-12),
            "max wind increment metadata",
        )
        require(
            np.isclose(actual_max_omega, float(getattr(dataset, "max_omega_increment_pas")), atol=1e-12),
            "max omega increment metadata",
        )
        target_fraction = float(getattr(dataset, "trust_region_fraction"))
        require(0.0 <= target_fraction <= 1.0, "target fraction range")
        meaningful_target = (
            target_source
            & masks["candidate_balance_support"]
        )
        target_count = int(np.count_nonzero(meaningful_target))
        response_ratio = np.zeros_like(domega)
        response_ratio[meaningful_target] = (
            domega[meaningful_target] / accepted_target[meaningful_target]
        )
        minimum_response = float(getattr(dataset, "minimum_target_response_ratio"))
        maximum_response = float(getattr(dataset, "maximum_target_response_ratio"))
        response_tolerance = 64.0 * np.finfo(np.float32).eps * np.maximum.reduce(
            (
                np.ones_like(response_ratio),
                np.abs(response_ratio),
                np.full_like(response_ratio, abs(minimum_response)),
                np.full_like(response_ratio, abs(maximum_response)),
            )
        )
        response_failure = meaningful_target & (
            (response_ratio < minimum_response - response_tolerance)
            | (response_ratio > maximum_response + response_tolerance)
        )
        response_failure_fraction = (
            float(np.count_nonzero(response_failure) / target_count)
            if target_count
            else 0.0
        )
        solver_reason = int(getattr(dataset, "solver_reason", -999))
        solver_iterations = int(getattr(dataset, "solver_iterations", -1))
        raw_wind = float(getattr(dataset, "unscaled_max_wind_increment_ms"))
        raw_omega = float(getattr(dataset, "unscaled_max_omega_increment_pas"))
        require(
            np.isfinite(raw_wind)
            and np.isfinite(raw_omega)
            and raw_wind >= 0.0
            and raw_omega >= 0.0,
            "unscaled increment maxima",
        )
        if target_count:
            require(target_fraction > 0.0, "target fraction range")
            expected_trust = 1.0
            if raw_wind > 0.0:
                expected_trust = min(
                    expected_trust,
                    float(getattr(dataset, "increment_headroom"))
                    * float(getattr(dataset, "maximum_wind_increment_ms"))
                    / raw_wind,
                )
            if raw_omega > 0.0:
                expected_trust = min(
                    expected_trust,
                    float(getattr(dataset, "increment_headroom"))
                    * float(getattr(dataset, "maximum_omega_increment_pas"))
                    / raw_omega,
                )
            require(
                np.isclose(target_fraction, expected_trust, rtol=5.0e-12, atol=1.0e-14),
                "trust-region fraction",
            )
            require(solver_reason == SOLVER_CONVERGED, "solver reason")
            require(
                0 < solver_iterations
                <= int(getattr(dataset, "maximum_solver_iterations")),
                "solver iteration gate",
            )
        else:
            require(target_fraction == 0.0, "no-target trust fraction")
            require(raw_wind == 0.0 and raw_omega == 0.0, "no-target raw increments")
            require(solver_reason == SOLVER_NOT_RUN, "no-target solver reason")
            require(solver_iterations == 0, "no-target solver iterations")
            require(
                not np.any(masks["candidate_balance_support"]),
                "no-target balance support",
            )
            require(not np.any(balance_changed), "no-target wind change")
        require(
            target_count == 0,
            "v3 real-data evidence forbids unvalidated dynamic wind authority",
        )
        require(
            np.isclose(
                response_failure_fraction,
                float(getattr(dataset, "target_response_failure_fraction")),
                atol=0.0,
            ),
            "target response metadata",
        )

        residual_before = fields["continuity_background"].astype(np.float64)
        residual_after = fields["continuity_candidate"].astype(np.float64)
        independent_before = continuity_state(
            fields["background_u"].astype(np.float64),
            fields["background_v"].astype(np.float64),
            fields["background_omega"].astype(np.float64),
            omega_top_boundary,
            omega_bottom_boundary,
            masks["candidate_balance_support"],
            above,
            float(getattr(dataset, "grid_dx_m")),
            float(getattr(dataset, "grid_dy_m")),
            pressure,
            pressure_interface,
            cell_dp,
        )
        independent_after = continuity_state(
            fields["candidate_u"].astype(np.float64),
            fields["candidate_v"].astype(np.float64),
            fields["candidate_omega"].astype(np.float64),
            omega_top_boundary,
            omega_bottom_boundary,
            masks["candidate_balance_support"],
            above,
            float(getattr(dataset, "grid_dx_m")),
            float(getattr(dataset, "grid_dy_m")),
            pressure,
            pressure_interface,
            cell_dp,
        )
        state_residual_error = max(
            float(np.max(np.abs(independent_before - residual_before))),
            float(np.max(np.abs(independent_after - residual_after))),
        )
        require(state_residual_error <= 1.0e-12, "full-state residual reconstruction")
        residual_increment = residual_after - residual_before
        independent_increment = continuity_increment(
            du,
            dv,
            domega,
            masks["candidate_balance_support"],
            float(getattr(dataset, "grid_dx_m")),
            float(getattr(dataset, "grid_dy_m")),
            pressure,
            pressure_interface,
            cell_dp,
        )
        active_error = np.abs(independent_increment - residual_increment)[
            masks["candidate_balance_support"]
        ]
        operator_error = float(np.max(active_error)) if active_error.size else 0.0
        operator_tolerance = float(getattr(dataset, "operator_identity_tolerance"))
        require(
            np.isclose(
                operator_error,
                float(getattr(dataset, "continuity_operator_identity_max")),
                rtol=5.0e-8,
                atol=1.0e-18,
            ),
            "operator identity metadata",
        )
        def norms(array: np.ndarray) -> tuple[float, float]:
            active_values = array[masks["candidate_balance_support"]]
            if not active_values.size:
                return 0.0, 0.0
            return float(np.sqrt(np.mean(active_values**2))), float(np.max(np.abs(active_values)))

        background_rms, background_max = norms(residual_before)
        candidate_rms, candidate_max = norms(residual_after)
        projected_rms, projected_max = norms(independent_increment)
        proposed_increment = continuity_increment(
            np.zeros_like(du),
            np.zeros_like(dv),
            accepted_target,
            masks["candidate_balance_support"],
            float(getattr(dataset, "grid_dx_m")),
            float(getattr(dataset, "grid_dy_m")),
            pressure,
            pressure_interface,
            cell_dp,
        )
        proposed_rms, proposed_max = norms(proposed_increment)
        for name, actual in (
            ("continuity_background_rms", background_rms),
            ("continuity_background_max", background_max),
            ("continuity_candidate_rms", candidate_rms),
            ("continuity_candidate_max", candidate_max),
            ("continuity_projected_increment_rms", projected_rms),
            ("continuity_projected_increment_max", projected_max),
            ("continuity_proposed_increment_rms", proposed_rms),
            ("continuity_proposed_increment_max", proposed_max),
        ):
            require(np.isclose(actual, float(getattr(dataset, name)), rtol=5e-8, atol=1e-13), name)
        required_fraction = float(getattr(dataset, "required_residual_fraction"))
        physical_tolerance = float(getattr(dataset, "physical_residual_tolerance"))
        physical_maximum = float(getattr(dataset, "maximum_physical_residual"))

        def physical_limit(background: float) -> float:
            return min(background + physical_tolerance, physical_maximum)

        geostrophic_background = float(getattr(dataset, "geostrophic_background_rms"))
        geostrophic_candidate = float(getattr(dataset, "geostrophic_candidate_rms"))
        require(
            np.isfinite(geostrophic_background)
            and np.isfinite(geostrophic_candidate)
            and geostrophic_background >= 0.0
            and geostrophic_candidate >= 0.0,
            "geostrophic metrics finite",
        )
        expected_failures = 0
        if projected_rms > max(required_fraction * proposed_rms, operator_tolerance):
            expected_failures |= GATE_INCREMENT_RMS
        if projected_max > max(required_fraction * proposed_max, operator_tolerance):
            expected_failures |= GATE_INCREMENT_MAX
        if candidate_rms > physical_limit(background_rms):
            expected_failures |= GATE_PHYSICAL_RMS
        if candidate_max > physical_limit(background_max):
            expected_failures |= GATE_PHYSICAL_MAX
        if actual_max_wind > float(getattr(dataset, "maximum_wind_increment_ms")):
            expected_failures |= GATE_WIND_INCREMENT
        if actual_max_omega > float(getattr(dataset, "maximum_omega_increment_pas")):
            expected_failures |= GATE_OMEGA_INCREMENT
        if target_count and response_failure_fraction > 0.0:
            expected_failures |= GATE_TARGET_RESPONSE
        if target_count and target_fraction < float(getattr(dataset, "minimum_trust_region_fraction")):
            expected_failures |= GATE_TARGET_FRACTION
        if operator_error > operator_tolerance:
            expected_failures |= GATE_OPERATOR_IDENTITY
        if geostrophic_candidate > geostrophic_background * (
            1.0 + float(getattr(dataset, "geostrophic_relative_tolerance"))
        ) + float(getattr(dataset, "geostrophic_absolute_tolerance")):
            expected_failures |= GATE_GEOSTROPHIC
        if np.any(balance_changed & ~masks["candidate_balance_support"]):
            expected_failures |= GATE_OUTSIDE_SUPPORT
        require(expected_failures == acceptance_failures, "acceptance failure bitset")
        require(accepted == (expected_failures == 0), "candidate decision")
        flux_names = (
                "flux_deposited",
                "flux_suspended",
                "flux_boundary_exit",
                "flux_terrain_intercept",
                "flux_observation_blocked",
                "flux_no_echo_blocked",
                "flux_microphysical_loss",
        )
        flux_input = float(getattr(dataset, "flux_input"))
        flux_terms = np.asarray(
            [float(getattr(dataset, name)) for name in flux_names], dtype=np.float64
        )
        reported_ledger_error = float(getattr(dataset, "flux_ledger_error"))
        require(
            np.isfinite(flux_input) and flux_input >= 0.0
            and np.all(np.isfinite(flux_terms)) and np.all(flux_terms >= 0.0)
            and np.isfinite(reported_ledger_error) and reported_ledger_error >= 0.0,
            "flux ledger finite nonnegative terms",
        )
        flux_accounted = float(np.sum(flux_terms))
        ledger_error = abs(flux_input - flux_accounted)
        ledger_limit = float(getattr(dataset, "ledger_absolute_tolerance")) + float(
            getattr(dataset, "ledger_relative_tolerance")
        ) * max(abs(flux_input), abs(flux_accounted))
        require(ledger_error <= ledger_limit, "independent flux ledger gate")
        require(
            np.isclose(reported_ledger_error, ledger_error, rtol=1.0e-12, atol=1.0e-15)
            and reported_ledger_error <= ledger_limit,
            "reported flux ledger gate",
        )
        require(
            int(getattr(dataset, "transport_required_substeps"))
            <= int(getattr(dataset, "maximum_transport_substeps")),
            "transport substep gate",
        )

        radar_columns = np.any(radar, axis=0)
        changed_columns = np.any(balance_changed, axis=0)
        dx = float(getattr(dataset, "grid_dx_m"))
        dy = float(getattr(dataset, "grid_dy_m"))
        radar_distance = distance_transform_edt(~radar_columns, sampling=(dy, dx))
        changed_distance = radar_distance[changed_columns]
        # Geometry is diagnostic here.  Canonical authority is already checked
        # by target-source, reconstructed-beta, and outside-support invariants.
        changed_dbz = fields["radar_dbz"][balance_changed]
        changed_beta = fields["balance_beta"][balance_changed]
        summary = {
            "path": path.name,
            "sha256": sha256(path),
            "standalone_provenance": "UNBOUND_REQUIRES_COMMITTED_GENERATION",
            "validation_scope": "NUMERICAL_CONTENT_ONLY",
            "numerical_decision": "VALID" if not failures else "INVALID",
            "artifact_decision": "UNBOUND",
            "candidate_decision": (
                "HYDROMETEOR_ENGINEERING_VALID_WITH_TRAJECTORY_ASSUMPTION"
                if accepted and not failures
                else "REJECTED"
            ),
            "hydrometeor_engineering_decision": (
                "VALID" if accepted and not failures else "REJECTED"
            ),
            "trajectory_science_decision": "BLOCKED_MISSING_STORM_MOTION",
            "dynamic_balance_decision": (
                "EVALUATED" if target_count else "NOT_AUTHORIZED"
            ),
            "valid_time_epoch": int(getattr(dataset, "valid_time_epoch")),
            "radar_cells": int(np.count_nonzero(radar)),
            "dynamic_target_cells": int(np.count_nonzero(target_source)),
            "column_changed_cells": int(np.count_nonzero(masks["column_changed"])),
            "hydrometeor_value_changed_cells": int(np.count_nonzero(column_changed)),
            "balance_changed_cells": int(np.count_nonzero(balance_changed)),
            "balance_changed_non_radar_cells": int(np.count_nonzero(balance_changed & ~radar)),
            "balance_changed_columns": int(np.count_nonzero(changed_columns)),
            "max_wind_increment_ms": actual_max_wind,
            "max_omega_increment_pas": actual_max_omega,
            "trust_region_fraction": target_fraction,
            "target_response_failure_fraction": response_failure_fraction,
            "solver_iterations": solver_iterations,
            "localization_max_abs_error": beta_error,
            "independent_operator_max_abs_error": operator_error,
            "independent_state_residual_max_abs_error": state_residual_error,
            "radar_column_distance_m": percentile(changed_distance, (50, 90, 99, 100)),
            "dbz_at_balance_changes": percentile(changed_dbz, (0, 25, 50, 75, 100)),
            "beta_at_balance_changes": percentile(changed_beta, (0, 25, 50, 75, 100)),
            "wind_increment_cell_counts": {
                str(level): int(np.count_nonzero(wind_increment >= level))
                for level in (0.01, 0.1, 0.5, 1.0, 2.0, 5.0, 9.0)
            },
        }
    summary["failures"] = failures
    return summary, failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("diagnostic", type=Path)
    parser.add_argument("--json", type=Path, help="also write the JSON report")
    args = parser.parse_args()
    try:
        summary, failures = validate(args.diagnostic)
    except Exception as error:
        failures = [f"{type(error).__name__}: {error}"]
        summary = {
            "path": args.diagnostic.name,
            "standalone_provenance": "UNBOUND_REQUIRES_COMMITTED_GENERATION",
            "validation_scope": "NUMERICAL_CONTENT_ONLY",
            "numerical_decision": "INVALID",
            "artifact_decision": "UNBOUND",
            "candidate_decision": "UNKNOWN",
            "failures": failures,
        }
    report = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    if args.json:
        args.json.write_text(report, encoding="utf-8")
    print(report, end="")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
