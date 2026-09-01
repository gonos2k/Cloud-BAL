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
SOURCE_KNOWN_BITS = (1 << 11) - 1
SOURCE_DYNAMIC_EVIDENCE_BITS = (
    SOURCE_CONVENTIONAL_OBS | SOURCE_RADAR_VRAD | SOURCE_ANALYZED_WIND
)
QUALITY_KNOWN_BITS = (1 << 9) - 1
QUALITY_EXCLUDED_BITS = (1 << 0) | (1 << 1) | (1 << 2)
QUALITY_DYNAMIC_TARGET_EXCLUDED_BITS = (
    QUALITY_EXCLUDED_BITS | (1 << 4) | (1 << 5) |
    (1 << 6) | (1 << 7) | (1 << 8)
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
    "grid_dp_pa": 5_000.0,
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
    dp: float,
) -> np.ndarray:
    """Independent finite-volume D*S for this uniform real-data contract."""
    residual = np.zeros(du.shape, dtype=np.float64)

    xface = active[:, :, :-1] & active[:, :, 1:]
    xflux = np.where(xface, 0.5 * (du[:, :, :-1] + du[:, :, 1:]) / dx, 0.0)
    residual[:, :, :-1] += xflux
    residual[:, :, 1:] -= xflux

    yface = active[:, :-1, :] & active[:, 1:, :]
    yflux = np.where(yface, 0.5 * (dv[:, :-1, :] + dv[:, 1:, :]) / dy, 0.0)
    residual[:, :-1, :] += yflux
    residual[:, 1:, :] -= yflux

    pface = active[:-1, :, :] & active[1:, :, :]
    pflux = np.where(pface, 0.5 * (domega[:-1, :, :] + domega[1:, :, :]) / dp, 0.0)
    residual[:-1, :, :] -= pflux
    residual[1:, :, :] += pflux
    residual[~active] = 0.0
    return residual


def continuity_state(
    u: np.ndarray,
    v: np.ndarray,
    omega: np.ndarray,
    boundary_omega: np.ndarray,
    active: np.ndarray,
    above_ground: np.ndarray,
    dx: float,
    dy: float,
    dp: float,
) -> np.ndarray:
    """Independent full-state finite-volume residual for the uniform real grid."""
    residual = np.zeros(u.shape, dtype=np.float64)

    xface = above_ground[:, :, :-1] & above_ground[:, :, 1:]
    xflux = np.where(xface, 0.5 * (u[:, :, :-1] + u[:, :, 1:]) / dx, 0.0)
    residual[:, :, :-1] += np.where(active[:, :, :-1], xflux, 0.0)
    residual[:, :, 1:] -= np.where(active[:, :, 1:], xflux, 0.0)
    residual[:, :, 0] -= np.where(active[:, :, 0], u[:, :, 0] / dx, 0.0)
    residual[:, :, -1] += np.where(active[:, :, -1], u[:, :, -1] / dx, 0.0)

    yface = above_ground[:, :-1, :] & above_ground[:, 1:, :]
    yflux = np.where(yface, 0.5 * (v[:, :-1, :] + v[:, 1:, :]) / dy, 0.0)
    residual[:, :-1, :] += np.where(active[:, :-1, :], yflux, 0.0)
    residual[:, 1:, :] -= np.where(active[:, 1:, :], yflux, 0.0)
    residual[:, 0, :] -= np.where(active[:, 0, :], v[:, 0, :] / dy, 0.0)
    residual[:, -1, :] += np.where(active[:, -1, :], v[:, -1, :] / dy, 0.0)

    pface = above_ground[:-1, :, :] & above_ground[1:, :, :]
    pflux = np.where(
        pface, 0.5 * (omega[:-1, :, :] + omega[1:, :, :]) / dp, 0.0
    )
    residual[:-1, :, :] -= np.where(active[:-1, :, :], pflux, 0.0)
    residual[1:, :, :] += np.where(active[1:, :, :], pflux, 0.0)

    for j, i in np.argwhere(np.any(above_ground, axis=0)):
        levels = np.flatnonzero(above_ground[:, j, i])
        bottom, top = int(levels[0]), int(levels[-1])
        if active[bottom, j, i]:
            residual[bottom, j, i] += boundary_omega[bottom, j, i] / dp
        if active[top, j, i]:
            residual[top, j, i] -= boundary_omega[top, j, i] / dp
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
            == {"x": 235, "y": 283, "z": 22},
            "dimensions must be x=235,y=283,z=22",
        )
        require(getattr(dataset, "contract", "") == "real_radar_only_shadow_v3", "contract")
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
        for attribute, expected in (
            ("promotion_eligible", 0),
            ("operational_state_changed", 0),
            ("science_assessed", 0),
            ("cloud_analysis_present", 0),
            ("radar_los_used", 0),
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

        required = set(FLOAT_UNITS) | set(MASKS) | set(TARGET_METADATA) | {
            "pressure", "latitude", "longitude"
        }
        require(required <= set(dataset.variables), "required variables")
        for name, dimensions, unit in (
            ("pressure", ("z",), "Pa"),
            ("latitude", ("y", "x"), "degree_north"),
            ("longitude", ("y", "x"), "degree_east"),
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

        pressure = values(dataset["pressure"]).astype(np.float64)
        require(np.all(np.isfinite(pressure)) and np.all(np.diff(pressure) < 0.0), "pressure order")
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
            fields["background_omega"].astype(np.float64),
            masks["candidate_balance_support"],
            above,
            float(getattr(dataset, "grid_dx_m")),
            float(getattr(dataset, "grid_dy_m")),
            float(getattr(dataset, "grid_dp_pa")),
        )
        independent_after = continuity_state(
            fields["candidate_u"].astype(np.float64),
            fields["candidate_v"].astype(np.float64),
            fields["candidate_omega"].astype(np.float64),
            fields["background_omega"].astype(np.float64),
            masks["candidate_balance_support"],
            above,
            float(getattr(dataset, "grid_dx_m")),
            float(getattr(dataset, "grid_dy_m")),
            float(getattr(dataset, "grid_dp_pa")),
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
            float(getattr(dataset, "grid_dp_pa")),
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
            float(getattr(dataset, "grid_dp_pa")),
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
        flux_input = float(getattr(dataset, "flux_input"))
        flux_accounted = sum(
            float(getattr(dataset, name))
            for name in (
                "flux_deposited",
                "flux_suspended",
                "flux_boundary_exit",
                "flux_terrain_intercept",
                "flux_observation_blocked",
                "flux_microphysical_loss",
            )
        )
        ledger_error = abs(flux_input - flux_accounted)
        ledger_limit = float(getattr(dataset, "ledger_absolute_tolerance")) + float(
            getattr(dataset, "ledger_relative_tolerance")
        ) * flux_input
        require(ledger_error <= ledger_limit, "independent flux ledger gate")
        require(
            float(getattr(dataset, "flux_ledger_error")) <= ledger_limit,
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
            "path": str(path.resolve()),
            "sha256": sha256(path),
            "standalone_provenance": "UNBOUND_REQUIRES_COMMITTED_GENERATION",
            "validation_scope": "NUMERICAL_CONTENT_ONLY",
            "numerical_decision": "VALID" if not failures else "INVALID",
            "artifact_decision": "UNBOUND",
            "candidate_decision": (
                "HYDROMETEOR_ENGINEERING_VALID_WITH_TRAJECTORY_ASSUMPTION"
                if accepted
                else "REJECTED"
            ),
            "hydrometeor_engineering_decision": "VALID" if accepted else "REJECTED",
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
            "path": str(args.diagnostic.resolve()),
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
