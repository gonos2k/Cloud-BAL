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
import sys
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
OMEGA_TARGET_ERROR_CONTRACT = "diagonal_pressure_omega_v1"
OMEGA_TARGET_ERROR_ATTRIBUTES = ("omega_target_error_contract",)
OMEGA_TARGET_ERROR_VARIABLES = (
    "omega_target_sigma",
    "omega_target_sigma_valid",
    "omega_target_sigma_quality",
    "omega_target_sigma_source",
)
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
SURFACE_BOUNDARY_CONTRACT = "CANONICAL_SURFACE_BOUNDARY_V1"
SURFACE_BOUNDARY_PREFIXES = (
    "background_surface_pressure",
    "candidate_surface_pressure",
    "background_surface_temperature",
    "candidate_surface_temperature",
    "background_surface_vapor",
    "candidate_surface_vapor",
    "background_surface_height",
    "candidate_surface_height",
)
SURFACE_BOUNDARY_REQUIRED_PREFIXES = (
    "background_surface_pressure",
    "candidate_surface_pressure",
)
SURFACE_BOUNDARY_UNITS = {
    "background_surface_pressure": "Pa",
    "candidate_surface_pressure": "Pa",
    "background_surface_temperature": "K",
    "candidate_surface_temperature": "K",
    "background_surface_vapor": "kg kg-1 dryair",
    "candidate_surface_vapor": "kg kg-1 dryair",
    "background_surface_height": "m",
    "candidate_surface_height": "m",
}
SURFACE_BOUNDARY_RANGES = {
    "background_surface_pressure": (100.0, 120000.0),
    "candidate_surface_pressure": (100.0, 120000.0),
    "background_surface_temperature": (150.0, 350.0),
    "candidate_surface_temperature": (150.0, 350.0),
    "background_surface_vapor": (0.0, 0.1),
    "candidate_surface_vapor": (0.0, 0.1),
    "background_surface_height": (-500.0, 9000.0),
    "candidate_surface_height": (-500.0, 9000.0),
}
PRESSURE_TRANSITION_CONTRACT = "pressure_transition_seed_v1"
PRESSURE_TRANSITION_V2_CONTRACT = "pressure_transition_seed_v2"
PRESSURE_TRANSITION_SUPPORT_SEMANTICS = (
    "background_support_plus_candidate_new_cells_v1"
)
PRESSURE_TRANSITION_ATTRIBUTES = (
    "pressure_transition_contract",
    "pressure_transition_support_semantics",
)
PRESSURE_TRANSITION_MASKS = (
    "candidate_above_ground",
    "transition_seed_above_ground",
)
PRESSURE_TRANSITION_SURFACE_FIELDS = ("transition_seed_surface_pressure",)
PRESSURE_TRANSITION_FIELDS = (
    "pressure",
    "temperature",
    "vapor",
    "cloud_water",
    "cloud_ice",
    "rain",
    "snow",
    "graupel",
    "u",
    "v",
    "omega",
    "geopotential",
)
PRESSURE_TRANSITION_DRY_MASS = "transition_seed_dry_air_mass_measure"
PRESSURE_TRANSITION_VARIABLES = frozenset(
    {
        *PRESSURE_TRANSITION_MASKS,
        PRESSURE_TRANSITION_DRY_MASS,
        *PRESSURE_TRANSITION_SURFACE_FIELDS,
        *(
            f"transition_seed_{field}{suffix}"
            for field in PRESSURE_TRANSITION_FIELDS
            for suffix in ("", "_valid", "_quality", "_source")
        ),
        *(f"{name}{suffix}" for name in PRESSURE_TRANSITION_SURFACE_FIELDS
          for suffix in ("_valid", "_quality", "_source")),
    }
)
PRESSURE_TRANSITION_PRESSURE_FIELDS = (
    "transition_background_pressure", "transition_candidate_pressure",
)
PRESSURE_TRANSITION_V2_VARIABLES = PRESSURE_TRANSITION_VARIABLES | frozenset(
    f"{name}{suffix}"
    for name in PRESSURE_TRANSITION_PRESSURE_FIELDS
    for suffix in ("", "_valid", "_quality", "_source")
)
PRESSURE_TRANSITION_VALUE_UNITS = {
    "pressure": "Pa",
    "temperature": "K",
    "vapor": "kg kg-1 dryair",
    "cloud_water": "kg kg-1 dryair",
    "cloud_ice": "kg kg-1 dryair",
    "rain": "kg kg-1 dryair",
    "snow": "kg kg-1 dryair",
    "graupel": "kg kg-1 dryair",
    "u": "m s-1",
    "v": "m s-1",
    "omega": "Pa s-1",
    "geopotential": "m2 s-2",
}
PRESSURE_TRANSITION_VALUE_RANGES = {
    "pressure": (100.0, 120000.0),
    "surface_pressure": (100.0, 120000.0),
    "temperature": (150.0, 350.0),
    "vapor": (0.0, 0.2),
    "cloud_water": (0.0, np.inf),
    "cloud_ice": (0.0, np.inf),
    "rain": (0.0, np.inf),
    "snow": (0.0, np.inf),
    "graupel": (0.0, np.inf),
    "u": (-200.0, 200.0),
    "v": (-200.0, 200.0),
    "omega": (-100.0, 100.0),
    "geopotential": (-np.inf, np.inf),
}
HYDROMETEORS = ("cloud_water", "cloud_ice", "rain", "snow", "graupel")
THERMO_SPECIES = ("vapor", "cloud_water", "cloud_ice", "rain", "snow", "graupel")
THERMO_FIELDS = ("temperature",) + THERMO_SPECIES
THERMO_VALUE_UNITS = {
    "temperature": "K",
    "vapor": "kg kg-1 dryair",
    "cloud_water": "kg kg-1 dryair",
    "cloud_ice": "kg kg-1 dryair",
    "rain": "kg kg-1 dryair",
    "snow": "kg kg-1 dryair",
    "graupel": "kg kg-1 dryair",
}
SOURCE_COLUMN_PHYSICS = 1 << 7
SATURATION_LIQUID = 1
SATURATION_ICE = 2
THERMO_T0 = 273.15
THERMO_CP_DRY = 1004.5
THERMO_SPECIES_CP = np.asarray(
    (1846.4, 4190.0, 2106.0, 4190.0, 2106.0, 2106.0),
    dtype=np.float64,
)
THERMO_SPECIES_H0 = np.asarray(
    (2.50e6, 0.0, -3.50e5, 0.0, -3.50e5, -3.50e5),
    dtype=np.float64,
)
RADAR_RECONSTRUCTION_CONTRACT = "pressure_radar_reconstruction_v2"
RADAR_RECONSTRUCTION_ATTRIBUTES = (
    "radar_reconstruction_contract",
    "column_minimum_dbz",
)
RADAR_RECONSTRUCTION_VARIABLES = (
    "background_precipitation_phase",
    "background_precipitation_phase_valid",
    "background_precipitation_phase_quality",
    "background_precipitation_phase_source",
)
PHASE_UNKNOWN = 0
PHASE_GRAUPEL = 5
SOURCE_CLOUD_ANALYSIS = 1 << 2
SOURCE_RADAR_DBZ = 1 << 3
SOURCE_PHASE_EVIDENCE = SOURCE_CLOUD_ANALYSIS | SOURCE_RADAR_DBZ
ANALYSIS_CONTRACT = "pressure_fixed_represented_mixture_v1"
ANALYSIS_ATTRIBUTE_NAMES = (
    "analysis_contract",
    "analysis_species_change_kg",
    "analysis_mixing_ratio_change_kg",
    "analysis_dry_mass_redistribution_kg",
    "analysis_dry_air_change_kg",
    "analysis_enthalpy_change_j",
    "analysis_total_mass_error_kg",
    "analysis_max_cell_mass_error_kg",
    "analysis_accounted_cells",
    "analysis_incomplete_background_cells",
    "analysis_incomplete_candidate_cells",
)
ANALYSIS_VECTOR_ATTRIBUTES = (
    "analysis_species_change_kg",
    "analysis_mixing_ratio_change_kg",
    "analysis_dry_mass_redistribution_kg",
)
ANALYSIS_FLOAT_ATTRIBUTES = (
    "analysis_dry_air_change_kg",
    "analysis_enthalpy_change_j",
    "analysis_total_mass_error_kg",
    "analysis_max_cell_mass_error_kg",
)
ANALYSIS_COUNT_ATTRIBUTES = (
    "analysis_accounted_cells",
    "analysis_incomplete_background_cells",
    "analysis_incomplete_candidate_cells",
)
PRESSURE_GEOMETRY_CONTRACT = "prescribed_surface_pressure_v1"
PRESSURE_GEOMETRY_CONTINUITY_SCOPE = "candidate_balance_stage_geometry_v1"
PRESSURE_GEOMETRY_VARIABLES = (
    "requested_surface_pressure",
    "candidate_pressure_interface",
    "candidate_cell_dp",
    "candidate_pressure_mass_measure",
    "candidate_dry_air_mass_measure",
)
GEOMETRY_ANALYSIS_VECTOR_ATTRIBUTES = (
    "geometry_analysis_species_change_kg",
    "geometry_analysis_mixing_ratio_change_kg",
    "geometry_analysis_dry_mass_redistribution_kg",
)
GEOMETRY_ANALYSIS_FLOAT_ATTRIBUTES = (
    "geometry_analysis_dry_air_change_kg",
    "geometry_analysis_enthalpy_change_j",
    "geometry_analysis_geometry_mass_change_kg",
    "geometry_analysis_enthalpy_composition_change_j",
    "geometry_analysis_enthalpy_mass_metric_change_j",
    "geometry_analysis_total_mass_error_kg",
    "geometry_analysis_max_cell_mass_error_kg",
)
GEOMETRY_ANALYSIS_COUNT_ATTRIBUTES = (
    "geometry_analysis_accounted_cells",
    "geometry_analysis_incomplete_background_cells",
    "geometry_analysis_incomplete_candidate_cells",
)
GEOMETRY_ANALYSIS_ATTRIBUTES = (
    *GEOMETRY_ANALYSIS_VECTOR_ATTRIBUTES,
    *GEOMETRY_ANALYSIS_FLOAT_ATTRIBUTES,
    *GEOMETRY_ANALYSIS_COUNT_ATTRIBUTES,
)
PRESSURE_GEOMETRY_ATTRIBUTES = (
    "pressure_geometry_contract",
    "continuity_geometry_scope",
    *GEOMETRY_ANALYSIS_ATTRIBUTES,
)
OUTER_ATTRIBUTE_NAMES = (
    "outer_contract",
    "outer_maximum_iterations",
    "outer_iterations",
    "outer_converged",
    "outer_feedback_fields",
    "outer_feedback_units",
    "outer_max_abs_delta",
)
OUTER_CONTRACT = "pressure_fixed_feedback_producer_replay_v1"
OUTER_FEEDBACK_FIELDS = "temperature,vapor,u,v,omega"
OUTER_FEEDBACK_UNITS = "K,kg kg-1 dryair,m s-1,m s-1,Pa s-1"
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
SOURCE_MANUFACTURED_TEST = 1 << 12
SOURCE_KNOWN_BITS = (1 << 13) - 1
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
PRESSURE_ANALYSIS_CANDIDATE_CONTRACT = "pressure_analysis_candidate_v1"
PRESSURE_ANALYSIS_SHADOW_CONTRACT = "pressure_analysis_shadow_v1"
PRESSURE_ANALYSIS_SHADOW_EVIDENCE = "PRESSURE_ANALYSIS_SHADOW_PROPOSAL"
PRESSURE_ANALYSIS_SHADOW_CONFIGURATION = "pressure-analysis-shadow-v1"
PRESSURE_ANALYSIS_CANDIDATE_ATTRIBUTES = (
    "pressure_analysis_candidate_contract",
)
PRESSURE_ANALYSIS_CANDIDATE_VARIABLES = (
    "original_omega_target",
    "original_omega_target_valid",
    "original_omega_target_quality",
    "original_omega_target_source",
)
DRY_AIR_FLUX_CONTRACT_FIXED = "pressure_fixed_dry_advection_v1"
DRY_AIR_FLUX_CONTRACT_STATE = "pressure_state_geometry_dry_advection_v1"
DRY_AIR_FLUX_BOUNDARY = "nearest_interior_composition"
DRY_AIR_FLUX_ATTRIBUTES = (
    "dry_air_flux_contract",
    "dry_air_flux_boundary",
    "dry_air_mass_tendency_assessed",
)
DRY_AIR_FLUX_VARIABLES = (
    "background_dry_air_flux_divergence",
    "candidate_dry_air_flux_divergence",
)
PRESSURE_GEOPOTENTIAL_CONTRACT = "pressure_hydrostatic_increment_v1"
PRESSURE_GEOPOTENTIAL_REFERENCE = "lowest_represented_center"
PRESSURE_GEOPOTENTIAL_SURFACE_CONTRACT = "pressure_hydrostatic_surface_increment_v1"
PRESSURE_GEOPOTENTIAL_SURFACE_REFERENCE = "fixed_terrain_surface"
PRESSURE_GEOPOTENTIAL_SURFACE_CONDENSATE_ATTRIBUTE = (
    "pressure_geopotential_surface_condensate_convention"
)
PRESSURE_GEOPOTENTIAL_SURFACE_CONDENSATE = "WPS_SURFACE_ZERO_CONDENSATE"
PRESSURE_GEOPOTENTIAL_ATTRIBUTES = (
    "pressure_geopotential_contract",
    "pressure_geopotential_reference",
    "pressure_geopotential_native_assessed",
)
PRESSURE_GEOPOTENTIAL_SURFACE_ATTRIBUTES = PRESSURE_GEOPOTENTIAL_ATTRIBUTES + (
    PRESSURE_GEOPOTENTIAL_SURFACE_CONDENSATE_ATTRIBUTE,
)
PRESSURE_GEOPOTENTIAL_VARIABLES = (
    "background_geopotential",
    "background_geopotential_valid",
    "background_geopotential_quality",
    "background_geopotential_source",
    "candidate_geopotential",
    "candidate_geopotential_valid",
    "candidate_geopotential_quality",
    "candidate_geopotential_source",
    "geopotential_support",
    "geopotential_reference_level",
)
PRESSURE_GEOPOTENTIAL_VALUE_UNITS = "m2 s-2"
PRESSURE_GEOPOTENTIAL_EXTENSION = "pressure_geopotential_v1"
PRESSURE_GEOSTROPHIC_CONTRACT = "pressure_geostrophic_original_final_v1"
PRESSURE_GEOSTROPHIC_V2_CONTRACT = "pressure_geostrophic_original_final_v2"
PRESSURE_GEOSTROPHIC_V3_CONTRACT = "pressure_geostrophic_original_seed_final_v3"
PRESSURE_GEOSTROPHIC_V3_REFERENCE = "original_retained_seed_added_cells_v1"
PRESSURE_GEOSTROPHIC_SCOPE = (
    "balance_support_union_phi_support_horizontal_cross_halo_v1"
)
PRESSURE_GEOSTROPHIC_UNITS = "m s-2"
PRESSURE_GEOSTROPHIC_BASE_ATTRIBUTES = (
    "pressure_geostrophic_contract",
    "pressure_geostrophic_scope",
    "pressure_geostrophic_units",
    "pressure_geostrophic_science_assessed",
    "original_full_geostrophic_rms",
    "candidate_full_geostrophic_rms",
)
PRESSURE_GEOSTROPHIC_V2_ATTRIBUTES = PRESSURE_GEOSTROPHIC_BASE_ATTRIBUTES + (
    "pressure_geostrophic_requested_cells",
    "pressure_geostrophic_evaluated_cells",
    "pressure_geostrophic_partial_coverage",
)
PRESSURE_GEOSTROPHIC_V3_ATTRIBUTES = (
    "pressure_geostrophic_contract",
    "pressure_geostrophic_reference",
    "pressure_geostrophic_scope",
    "pressure_geostrophic_units",
    "pressure_geostrophic_science_assessed",
    "reference_full_geostrophic_rms",
    "candidate_full_geostrophic_rms",
    "pressure_geostrophic_requested_cells",
    "pressure_geostrophic_evaluated_cells",
    "pressure_geostrophic_partial_coverage",
)
PRESSURE_GEOSTROPHIC_ATTRIBUTES = PRESSURE_GEOSTROPHIC_BASE_ATTRIBUTES
PRESSURE_GEOSTROPHIC_V1_VARIABLES = ("geostrophic_validation_support",)
PRESSURE_GEOSTROPHIC_V2_VARIABLES = (
    "geostrophic_validation_support",
    "geostrophic_stencil_support",
)
PRESSURE_GEOSTROPHIC_VARIABLES = PRESSURE_GEOSTROPHIC_V1_VARIABLES
PHYSICAL_INPUT_DIAGNOSTIC_ONLY = "PHYSICAL_INPUT_DIAGNOSTIC_ONLY"
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


def exact_scalar_integer(raw: object) -> int | None:
    """Return an integer attribute only when it is a scalar signed integer."""
    if raw is None:
        return None
    parsed = np.asarray(raw)
    if parsed.ndim != 0 or parsed.dtype.kind != "i":
        return None
    return int(parsed)


def exact_scalar_int64(raw: object) -> int | None:
    """Return an integer attribute only when it is exactly signed int64."""
    if raw is None:
        return None
    parsed = np.asarray(raw)
    if parsed.ndim != 0 or parsed.dtype != np.dtype(np.int64):
        return None
    return int(parsed)


def exact_scalar_int32(raw: object) -> int | None:
    """Return an integer attribute only when it is exactly signed int32."""
    if raw is None:
        return None
    parsed = np.asarray(raw)
    if parsed.ndim != 0 or parsed.dtype != np.dtype(np.int32):
        return None
    return int(parsed)


def exact_scalar_float64(raw: object) -> float | None:
    """Return a floating-point attribute only when it is exactly float64."""
    if raw is None:
        return None
    parsed = np.asarray(raw)
    if parsed.ndim != 0 or parsed.dtype != np.dtype(np.float64):
        return None
    return float(parsed)


def radar_ledger_operand_tolerance(expected: float) -> float:
    """Return the comparison tolerance used for one replayed flux operand."""
    return 1.0e-10 + 2.0e-10 * max(1.0, abs(expected))


def radar_ledger_residual_tolerance(expected_ledger: dict[str, float]) -> float:
    """Propagate operand comparison errors through the cancellation residual.

    The residual is an absolute difference between the input flux and the sum
    of seven non-negative terminal terms.  Its comparison error is therefore
    bounded by the sum of the already-declared per-operand comparison errors,
    rather than by the much smaller residual itself.
    """
    operand_names = (
        "flux_input",
        "flux_deposited",
        "flux_suspended",
        "flux_boundary_exit",
        "flux_terrain_intercept",
        "flux_observation_blocked",
        "flux_no_echo_blocked",
        "flux_microphysical_loss",
    )
    return sum(
        radar_ledger_operand_tolerance(expected_ledger[name])
        for name in operand_names
    )


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


def pressure_transition_payload_signalled(dataset: netCDF4.Dataset) -> bool:
    """Return whether a file carries any deferred pressure-transition artifact."""
    return bool(
        any(name.startswith("pressure_transition_") for name in dataset.ncattrs())
        or any(
            name == "candidate_above_ground"
            or name.startswith("transition_seed_")
            or name.startswith(PRESSURE_TRANSITION_PRESSURE_FIELDS)
            for name in dataset.variables
        )
    )


def read_pressure_transition_seed_payload(
    dataset: netCDF4.Dataset,
    shape: tuple[int, int, int],
    valid_time_epoch: int | None,
    require,
) -> tuple[bool, bool, dict[str, np.ndarray]]:
    """Read the optional, not-yet-authoritative pressure-transition payload.

    This reader checks the complete writer contract, but does not replay the
    physical remap. Callers must therefore keep full diagnostic acceptance
    gated until the independent transition replay and ledger are connected.
    """

    signalled = pressure_transition_payload_signalled(dataset)
    if not signalled:
        return False, False, {}

    clean = True
    contract = getattr(dataset, "pressure_transition_contract", "")
    is_v2 = contract == PRESSURE_TRANSITION_V2_CONTRACT
    required_variables = (
        PRESSURE_TRANSITION_V2_VARIABLES if is_v2 else PRESSURE_TRANSITION_VARIABLES
    )

    def check(condition: object, message: str) -> bool:
        nonlocal clean
        passed = bool(condition)
        clean = clean and passed
        require(passed, message)
        return passed

    present_attributes = {
        name
        for name in dataset.ncattrs()
        if name.startswith("pressure_transition_")
    }
    present_variables = {
        name
        for name in dataset.variables
        if name == "candidate_above_ground" or name.startswith("transition_seed_")
        or name.startswith(PRESSURE_TRANSITION_PRESSURE_FIELDS)
    }
    check(
        present_attributes <= set(PRESSURE_TRANSITION_ATTRIBUTES),
        "known pressure transition attributes",
    )
    check(
        present_variables <= required_variables,
        "known pressure transition variables",
    )
    check(
        contract in (PRESSURE_TRANSITION_CONTRACT, PRESSURE_TRANSITION_V2_CONTRACT),
        "pressure transition contract",
    )
    check(
        getattr(dataset, "pressure_transition_support_semantics", "")
        == PRESSURE_TRANSITION_SUPPORT_SEMANTICS,
        "pressure transition support semantics",
    )
    check(valid_time_epoch is not None, "pressure transition valid-time epoch")
    complete = (
        set(PRESSURE_TRANSITION_ATTRIBUTES) <= set(dataset.ncattrs())
        and required_variables <= set(dataset.variables)
    )
    check(complete, "complete pressure transition seed payload")
    if is_v2:
        complete = complete and {"above_ground", "pressure"} <= set(dataset.variables)
        check(complete, "pressure transition original domain and pressure centers")
    if not complete:
        return True, False, {}

    arrays: dict[str, np.ndarray] = {}
    expected_shape = tuple(int(value) for value in shape)
    surface_shape = expected_shape[1:]

    def read_variable(
        name: str,
        dimensions: tuple[str, ...],
        expected_dtype: np.dtype,
        units: str,
        value_time: bool = False,
    ) -> np.ndarray:
        variable = dataset.variables[name]
        check(variable.dimensions == dimensions, f"{name} dimensions")
        if expected_dtype == np.dtype(np.int32):
            check(is_signed_int32(variable.dtype), f"{name} type")
        else:
            check(np.dtype(variable.dtype) == expected_dtype, f"{name} type")
        check(getattr(variable, "units", "") == units, f"{name} units")
        check(
            "scale_factor" not in variable.ncattrs()
            and "add_offset" not in variable.ncattrs(),
            f"{name} must not be packed",
        )
        if value_time:
            field_time = exact_scalar_int64(getattr(variable, "valid_time", None))
            check(field_time is not None, f"{name} valid time type")
            if valid_time_epoch is not None and field_time is not None:
                check(field_time == valid_time_epoch, f"{name} valid time identity")
        else:
            check("valid_time" not in variable.ncattrs(), f"{name} valid time metadata")
        array = values(variable)
        if expected_dtype == np.dtype(np.int32):
            check(is_signed_int32(array.dtype), f"{name} unpacked type")
        else:
            check(array.dtype == expected_dtype, f"{name} unpacked type")
        expected = {
            ("z", "y", "x"): expected_shape,
            ("y", "x"): surface_shape,
            ("z",): (expected_shape[0],),
        }[dimensions]
        check(array.shape == expected, f"{name} shape")
        arrays[name] = array
        return array

    for name in PRESSURE_TRANSITION_MASKS:
        read_variable(name, ("z", "y", "x"), np.dtype(np.int32), "1")
    read_variable(
        PRESSURE_TRANSITION_DRY_MASS,
        ("z", "y", "x"),
        np.dtype(np.float64),
        "kg dryair",
    )

    surface_name = PRESSURE_TRANSITION_SURFACE_FIELDS[0]
    read_variable(surface_name, ("y", "x"), np.dtype(np.float32), "Pa", True)
    for suffix in ("_valid", "_quality", "_source"):
        read_variable(
            f"{surface_name}{suffix}",
            ("y", "x"),
            np.dtype(np.int32),
            "1",
        )

    for field in PRESSURE_TRANSITION_FIELDS:
        name = f"transition_seed_{field}"
        read_variable(
            name,
            ("z", "y", "x"),
            np.dtype(np.float32),
            PRESSURE_TRANSITION_VALUE_UNITS[field],
            True,
        )
        for suffix in ("_valid", "_quality", "_source"):
            read_variable(
                f"{name}{suffix}",
                ("z", "y", "x"),
                np.dtype(np.int32),
                "1",
            )

    if is_v2:
        read_variable("above_ground", ("z", "y", "x"), np.dtype(np.int32), "1")
        read_variable("pressure", ("z",), np.dtype(np.float32), "Pa")
        for name in PRESSURE_TRANSITION_PRESSURE_FIELDS:
            read_variable(name, ("z", "y", "x"), np.dtype(np.float32), "Pa", True)
            for suffix in ("_valid", "_quality", "_source"):
                read_variable(f"{name}{suffix}", ("z", "y", "x"), np.dtype(np.int32), "1")

    # Do not allow malformed dtypes/shapes to reach the domain and metadata
    # broadcasts below; the structural diagnostics above are authoritative.
    if not clean:
        return True, False, arrays

    candidate_above = arrays["candidate_above_ground"]
    seed_above = arrays["transition_seed_above_ground"]
    check(np.all((candidate_above == 0) | (candidate_above == 1)),
          "candidate above-ground binary")
    check(np.all((seed_above == 0) | (seed_above == 1)),
          "transition seed above-ground binary")
    candidate_domain = candidate_above.astype(bool)
    seed_domain = seed_above.astype(bool)
    check(np.array_equal(candidate_domain, seed_domain),
          "candidate and transition seed domain identity")

    def check_metadata(name: str, domain: np.ndarray, field: str | None = None) -> None:
        valid = arrays[f"{name}_valid"]
        quality = arrays[f"{name}_quality"].astype(np.int64)
        source = arrays[f"{name}_source"].astype(np.int64)
        value = arrays[name]
        valid_cells = valid.astype(bool)
        check(np.all((valid == 0) | (valid == 1)), f"{name} valid binary")
        check(np.all(quality >= 0), f"{name} quality nonnegative")
        check(np.all((quality & ~QUALITY_KNOWN_BITS) == 0), f"{name} quality bits")
        check(np.all(source >= 0), f"{name} source nonnegative")
        check(np.all((source & ~SOURCE_KNOWN_BITS) == 0), f"{name} source bits")
        check(np.all((source & SOURCE_MANUFACTURED_TEST) == 0),
              f"{name} manufactured source prohibited")
        check(np.all(~domain | valid_cells), f"{name} complete coverage")
        usable = (
            valid_cells
            & (source > 0)
            & ((quality & QUALITY_EXCLUDED_BITS) == 0)
        )
        check(np.all(~valid_cells | usable), f"{name} usable metadata")
        check(np.all(~valid_cells | np.isfinite(value)), f"{name} finite")
        lower, upper = PRESSURE_TRANSITION_VALUE_RANGES[
            field or name.removeprefix("transition_seed_")
        ]
        check(
            np.all(~valid_cells | ((value >= lower) & (value <= upper))),
            f"{name} range",
        )

    for field in PRESSURE_TRANSITION_FIELDS:
        check_metadata(f"transition_seed_{field}", seed_domain)
    check_metadata(surface_name, np.ones(surface_shape, dtype=bool))

    if is_v2:
        original_mask = arrays["above_ground"]
        check(np.all((original_mask == 0) | (original_mask == 1)),
              "transition original above-ground binary")
        original_domain = original_mask.astype(bool)
        check(np.all(~original_domain | candidate_domain),
              "transition pressure retains original domain")
        added = candidate_domain & ~original_domain
        check_metadata("transition_background_pressure", original_domain, "pressure")
        check_metadata("transition_candidate_pressure", candidate_domain, "pressure")
        levels = arrays["pressure"][:, None, None]
        for name in (*PRESSURE_TRANSITION_PRESSURE_FIELDS, "transition_seed_pressure"):
            check(np.array_equal(arrays[name], np.broadcast_to(levels, expected_shape)),
                  f"{name} immutable pressure centers")
        # Non-added includes original inactive cells: their metadata must not
        # be silently promoted. Only added cells take the seed's provenance.
        for suffix in ("_valid", "_quality", "_source"):
            actual = arrays[f"transition_candidate_pressure{suffix}"]
            seed_metadata = arrays[f"transition_seed_pressure{suffix}"]
            if suffix == "_source":
                seed_metadata = seed_metadata | SOURCE_COLUMN_PHYSICS
            expected = np.where(
                added, seed_metadata,
                arrays[f"transition_background_pressure{suffix}"],
            )
            check(np.array_equal(actual, expected),
                  f"transition pressure{suffix} original/seed identity")

    dry_mass = arrays[PRESSURE_TRANSITION_DRY_MASS]
    check(np.all(np.isfinite(dry_mass)), "transition seed dry-air mass finite")
    check(np.all(dry_mass >= 0.0), "transition seed dry-air mass nonnegative")
    check(np.all(dry_mass[~seed_domain] == 0.0),
          "transition seed dry-air mass below ground")
    check(np.all(dry_mass[seed_domain] > 0.0),
          "transition seed dry-air mass active")
    return True, bool(clean), arrays


def read_surface_boundary_extension(
    dataset: netCDF4.Dataset,
    shape: tuple[int, int],
    valid_time_epoch: int | None,
    canonical_schema_version: int | None,
    reference_surface_pressure: np.ndarray | None,
    require,
    allow_pressure_change: bool = False,
) -> tuple[bool, bool, dict[str, np.ndarray]]:
    """Read and validate the canonical schema-5 surface-boundary extension.

    The value payload is meaningful only where its paired valid mask is one.
    This is intentional: optional vapor and height fields commonly retain NaN
    payloads in invalid cells.  Metadata, masks, and the background/candidate
    identity are nevertheless strict for every cell.
    """

    extension_variables = {
        name
        for prefix in SURFACE_BOUNDARY_PREFIXES
        for name in (prefix, f"{prefix}_valid", f"{prefix}_quality", f"{prefix}_source")
    }
    present = bool(
        "surface_boundary_contract" in dataset.ncattrs()
        or extension_variables & set(dataset.variables)
    )
    if not present:
        if canonical_schema_version == 5:
            require(False, "canonical5 surface boundary extension")
        return False, False, {}

    supported = canonical_schema_version == 5
    require(supported, "surface boundary extension requires canonical schema 5")
    complete = (
        "surface_boundary_contract" in dataset.ncattrs()
        and extension_variables <= set(dataset.variables)
    )
    require(complete, "complete surface boundary extension")
    if not supported or not complete:
        return True, False, {}

    contract = getattr(dataset, "surface_boundary_contract", None)
    arrays: dict[str, np.ndarray] = {}
    clean = True

    def check(condition: object, message: str) -> bool:
        nonlocal clean
        passed = bool(condition)
        require(passed, message)
        clean = clean and passed
        return passed

    check(contract == SURFACE_BOUNDARY_CONTRACT, "surface boundary contract")
    check(valid_time_epoch is not None, "surface boundary valid-time epoch")
    structure_valid = True
    for prefix in SURFACE_BOUNDARY_PREFIXES:
        value_name = prefix
        valid_name = f"{prefix}_valid"
        quality_name = f"{prefix}_quality"
        source_name = f"{prefix}_source"
        value_variable = dataset.variables[value_name]
        value_array = values(value_variable)
        value_structure_ok = (
            value_variable.dimensions == ("y", "x")
            and np.dtype(value_variable.dtype) == np.dtype(np.float32)
            and value_array.shape == shape
        )
        check(value_variable.dimensions == ("y", "x"), f"{value_name} dimensions")
        check(np.dtype(value_variable.dtype) == np.dtype(np.float32), f"{value_name} type")
        check(value_array.shape == shape, f"{value_name} shape")
        check(getattr(value_variable, "units", "") == SURFACE_BOUNDARY_UNITS[prefix],
              f"{value_name} units")
        value_time = exact_scalar_int64(getattr(value_variable, "valid_time", None))
        check(value_time is not None, f"{value_name} valid time type")
        if valid_time_epoch is not None and value_time is not None:
            check(value_time == valid_time_epoch, f"{value_name} valid time identity")
        arrays[value_name] = value_array

        metadata: list[np.ndarray] = []
        for name in (valid_name, quality_name, source_name):
            variable = dataset.variables[name]
            array = values(variable)
            metadata_structure_ok = (
                variable.dimensions == ("y", "x")
                and is_signed_int32(variable.dtype)
                and array.shape == shape
            )
            check(variable.dimensions == ("y", "x"), f"{name} dimensions")
            check(is_signed_int32(variable.dtype), f"{name} type")
            check(array.shape == shape, f"{name} shape")
            check(getattr(variable, "units", "") == "1", f"{name} units")
            check("valid_time" not in variable.ncattrs(), f"{name} valid time metadata")
            metadata.append(array)
            arrays[name] = array
            value_structure_ok = value_structure_ok and metadata_structure_ok

        structure_valid = structure_valid and value_structure_ok
        if not value_structure_ok:
            continue

        valid, quality, source = metadata
        check(
            "scale_factor" not in value_variable.ncattrs()
            and "add_offset" not in value_variable.ncattrs(),
            f"{value_name} must not be packed",
        )
        for name in (valid_name, quality_name, source_name):
            variable = dataset.variables[name]
            check(
                "scale_factor" not in variable.ncattrs()
                and "add_offset" not in variable.ncattrs(),
                f"{name} must not be packed",
            )

        valid_i = valid.astype(np.int64)
        quality_i = quality.astype(np.int64)
        source_i = source.astype(np.int64)
        valid_cells = valid_i == 1
        usable = (
            valid_cells
            & (source_i > 0)
            & (quality_i >= 0)
            & ((quality_i & ~QUALITY_KNOWN_BITS) == 0)
            & ((quality_i & QUALITY_EXCLUDED_BITS) == 0)
            & ((source_i & ~SOURCE_KNOWN_BITS) == 0)
        )
        check(np.all((valid_i == 0) | (valid_i == 1)), f"{valid_name} binary")
        check(np.all(quality_i >= 0), f"{quality_name} nonnegative")
        check(np.all((quality_i & ~QUALITY_KNOWN_BITS) == 0), f"{quality_name} bits")
        check(np.all(source_i >= 0), f"{source_name} nonnegative")
        check(np.all((source_i & ~SOURCE_KNOWN_BITS) == 0), f"{source_name} bits")
        check(np.all((source_i & SOURCE_MANUFACTURED_TEST) == 0),
              f"{source_name} manufactured provenance")
        check(np.all(~valid_cells | usable), f"{value_name} usable metadata")
        lower, upper = SURFACE_BOUNDARY_RANGES[prefix]
        check(np.all(~valid_cells | np.isfinite(value_array)), f"{value_name} finite")
        check(
            np.all(~valid_cells | ((value_array >= lower) & (value_array <= upper))),
            f"{value_name} range",
        )
        if prefix in SURFACE_BOUNDARY_REQUIRED_PREFIXES:
            check(np.all(usable), f"{value_name} required coverage")

    if not structure_valid:
        return True, False, arrays

    if not allow_pressure_change:
        for suffix in ("_valid", "_quality", "_source"):
            left = arrays[f"background_surface_pressure{suffix}"]
            right = arrays[f"candidate_surface_pressure{suffix}"]
            check(np.array_equal(left, right), f"surface pressure {suffix} identity")
        changed = changed_bits(
            arrays["background_surface_pressure"].astype(np.float32),
            arrays["candidate_surface_pressure"].astype(np.float32),
        )
        check(np.all(~changed), "surface pressure value identity")

    if reference_surface_pressure is not None:
        reference = np.asarray(reference_surface_pressure, dtype=np.float32)
        background = arrays["background_surface_pressure"].astype(np.float32)
        check(reference.shape == shape, "surface pressure reference shape")
        if reference.shape == shape:
            changed = changed_bits(background, reference)
            check(np.all(~changed), "background surface pressure identity")

    for field in ("temperature", "vapor", "height"):
        background_name = f"background_surface_{field}"
        candidate_name = f"candidate_surface_{field}"
        changed = changed_bits(
            arrays[background_name].astype(np.float32),
            arrays[candidate_name].astype(np.float32),
        )
        check(np.all(~changed), f"surface {field} value identity")
        for suffix in ("_valid", "_quality", "_source"):
            left = arrays[f"{background_name}{suffix}"]
            right = arrays[f"{candidate_name}{suffix}"]
            check(np.array_equal(left, right), f"surface {field} {suffix} identity")

    return True, bool(clean), arrays


def read_pressure_geometry_extension(
    dataset: netCDF4.Dataset,
    shape: tuple[int, int, int],
    pressure: np.ndarray,
    above: np.ndarray,
    base_pressure_interface: np.ndarray,
    base_cell_dp: np.ndarray,
    base_pressure_mass: np.ndarray,
    base_dry_air_mass: np.ndarray,
    surface_boundary_present: bool,
    surface_boundary_clean: bool,
    surface_boundary_inputs: dict[str, np.ndarray],
    schema_version: int,
    require,
    *,
    candidate_above: np.ndarray | None = None,
    transition_inputs: dict[str, np.ndarray] | None = None,
) -> tuple[bool, bool, dict[str, np.ndarray]]:
    """Read and independently replay the prescribed-surface-pressure geometry.

    The ordinary pressure geometry remains the immutable background geometry.
    This extension carries a complete candidate geometry so candidate-side
    residuals and dry-mass quantities cannot accidentally be replayed against
    the background metrics.

    A supplied candidate domain comes from the separately checked transition
    payload. This reader verifies geometry, not the physical transition ledger.
    """

    present_attributes = {
        name for name in dataset.ncattrs()
        if name == "pressure_geometry_contract"
        or name == "continuity_geometry_scope"
        or name.startswith("pressure_geometry_")
        or name.startswith("geometry_analysis_")
    }
    # candidate_dry_air_mass_measure is also emitted by the ordinary thermo
    # extension.  It is therefore deliberately excluded here: only the new
    # request/geometry fields or their contract metadata signal this group.
    present_variables = {
        name for name in dataset.variables
        if name in {
            "requested_surface_pressure",
            "candidate_pressure_interface",
            "candidate_cell_dp",
            "candidate_pressure_mass_measure",
        }
        or name.startswith("requested_surface_pressure")
        or name.startswith("candidate_pressure_")
        or name == "continuity_original_background"
    }
    present = bool(present_attributes or present_variables)
    if not present:
        return False, False, {}

    clean = True

    def check(condition: object, message: str) -> None:
        nonlocal clean
        passed = bool(condition)
        clean = clean and passed
        require(passed, message)

    check(
        present_attributes <= set(PRESSURE_GEOMETRY_ATTRIBUTES),
        "known pressure geometry attributes",
    )
    check(
        present_variables <= (
            set(PRESSURE_GEOMETRY_VARIABLES) | {"continuity_original_background"}
        ),
        "known pressure geometry variables",
    )
    check(schema_version == 7, "prescribed pressure geometry requires single-pass schema 7")
    check(
        getattr(dataset, "pressure_geometry_contract", "")
        == PRESSURE_GEOMETRY_CONTRACT,
        "pressure geometry contract",
    )
    check(
        getattr(dataset, "continuity_geometry_scope", "")
        == PRESSURE_GEOMETRY_CONTINUITY_SCOPE,
        "pressure geometry continuity scope",
    )
    complete = (
        set(PRESSURE_GEOMETRY_ATTRIBUTES) <= set(dataset.ncattrs())
        and set(PRESSURE_GEOMETRY_VARIABLES) <= set(dataset.variables)
        and "continuity_original_background" in dataset.variables
    )
    check(complete, "complete pressure geometry extension")
    check(
        surface_boundary_present and surface_boundary_clean,
        "pressure geometry requires clean surface boundary",
    )
    if not complete or not surface_boundary_present:
        return True, False, {}

    arrays: dict[str, np.ndarray] = {}

    def read_variable(
        name: str,
        dimensions: tuple[str, ...],
        dtype: np.dtype,
        units: str,
    ) -> np.ndarray:
        variable = dataset.variables[name]
        check(variable.dimensions == dimensions, f"{name} dimensions")
        check(np.dtype(variable.dtype) == dtype, f"{name} type")
        check(getattr(variable, "units", "") == units, f"{name} units")
        check(
            "scale_factor" not in variable.ncattrs()
            and "add_offset" not in variable.ncattrs(),
            f"{name} must not be packed",
        )
        array = values(variable)
        check(array.dtype == dtype, f"{name} unpacked type")
        check(array.shape == (shape[1], shape[2]) if dimensions == ("y", "x")
              else array.shape == shape if dimensions == ("z", "y", "x")
              else array.shape == (shape[0] + 1, shape[1], shape[2]),
              f"{name} shape")
        arrays[name] = array
        return array

    requested = read_variable(
        "requested_surface_pressure", ("y", "x"), np.dtype(np.float64), "Pa"
    )
    candidate_interface = read_variable(
        "candidate_pressure_interface",
        ("z_interface", "y", "x"),
        np.dtype(np.float64),
        "Pa",
    )
    candidate_cell_dp = read_variable(
        "candidate_cell_dp", ("z", "y", "x"), np.dtype(np.float64), "Pa"
    )
    candidate_pressure_mass = read_variable(
        "candidate_pressure_mass_measure",
        ("z", "y", "x"),
        np.dtype(np.float64),
        "kg",
    )
    candidate_dry_air_mass = read_variable(
        "candidate_dry_air_mass_measure",
        ("z", "y", "x"),
        np.dtype(np.float64),
        "kg dryair",
    )
    check(np.all(np.isfinite(requested)), "requested surface pressure finite")
    check(
        np.all((requested >= 100.0) & (requested <= 120000.0)),
        "requested surface pressure range",
    )
    for name, array in (
        ("candidate pressure interface", candidate_interface),
        ("candidate cell dp", candidate_cell_dp),
        ("candidate pressure mass", candidate_pressure_mass),
        ("candidate dry-air mass", candidate_dry_air_mass),
    ):
        check(np.all(np.isfinite(array)), f"{name} finite")
    check(np.all(candidate_interface > 0.0), "candidate pressure interface positive")
    check(np.all(candidate_cell_dp >= 0.0), "candidate cell dp nonnegative")
    check(np.all(candidate_pressure_mass >= 0.0), "candidate pressure mass nonnegative")
    check(np.all(candidate_dry_air_mass >= 0.0), "candidate dry-air mass nonnegative")

    boundary_candidate = surface_boundary_inputs.get("candidate_surface_pressure")
    boundary_background = surface_boundary_inputs.get("background_surface_pressure")
    candidate_source = surface_boundary_inputs.get("candidate_surface_pressure_source")
    background_source = surface_boundary_inputs.get("background_surface_pressure_source")
    boundary_valid = surface_boundary_inputs.get("candidate_surface_pressure_valid")
    background_valid = surface_boundary_inputs.get("background_surface_pressure_valid")
    boundary_quality = surface_boundary_inputs.get("candidate_surface_pressure_quality")
    background_quality = surface_boundary_inputs.get("background_surface_pressure_quality")
    check(
        all(item is not None for item in (
            boundary_candidate, boundary_background, candidate_source,
            background_source, boundary_valid, background_valid,
            boundary_quality, background_quality,
        )),
        "pressure geometry surface pressure metadata",
    )
    if any(item is None for item in (
        boundary_candidate, boundary_background, candidate_source,
        background_source, boundary_valid, background_valid,
        boundary_quality, background_quality,
    )):
        return True, False, arrays

    requested32 = requested.astype(np.float32)
    background_surface = np.asarray(boundary_background, dtype=np.float32)
    candidate_surface = np.asarray(boundary_candidate, dtype=np.float32)
    changed_surface = changed_bits(background_surface, candidate_surface)
    check(np.array_equal(requested32, candidate_surface), "requested pressure rounds to stored candidate")
    background_domain = pressure[:, None, None] <= background_surface[None, :, :]
    requested_domain = pressure[:, None, None] <= requested[None, :, :]
    candidate_domain = pressure[:, None, None] <= candidate_surface[None, :, :]
    candidate_active = above
    if candidate_above is None:
        check(np.array_equal(requested_domain, background_domain),
              "requested pressure domain classification")
        check(np.array_equal(candidate_domain, background_domain),
              "stored candidate pressure domain classification")
    else:
        candidate_active = np.asarray(candidate_above)
        check(candidate_active.shape == shape and candidate_active.dtype == np.dtype(bool),
              "candidate active-domain shape and boolean type")
        if candidate_active.shape != shape or candidate_active.dtype != np.dtype(bool):
            return True, False, arrays
        check(np.array_equal(requested_domain, candidate_domain),
              "requested and stored pressure domain classification")
        check(np.all(~background_domain | candidate_domain),
              "pressure transition does not remove pressure-accessible centers")
        newly_crossed = candidate_domain & ~background_domain
        # Old pressure-accessible cells excluded by terrain stay excluded.
        check(np.array_equal(candidate_active, above | newly_crossed),
              "candidate domain preserves terrain exclusions and adds crossed centers only")
        check(np.all(~above | candidate_domain), "candidate pressure retains original active cells")
        check(np.all(np.sum(newly_crossed, axis=0) <= 1), "at most one added pressure center")
        check(np.all(~candidate_active[:-1] | candidate_active[1:]),
              "candidate active column is contiguous")
        check(np.all(candidate_surface.astype(np.float64) - background_surface <= 100.0),
              "positive pressure transition within 100 Pa")
    expected_valid = np.asarray(background_valid)
    expected_quality = np.asarray(background_quality)
    expected_source = np.asarray(background_source, dtype=np.int64)
    if transition_inputs is not None:
        positive = candidate_surface > background_surface
        expected_valid = np.where(positive,
            transition_inputs["transition_seed_surface_pressure_valid"], expected_valid)
        expected_quality = np.where(positive,
            transition_inputs["transition_seed_surface_pressure_quality"], expected_quality)
        expected_source = np.where(positive,
            transition_inputs["transition_seed_surface_pressure_source"], expected_source)
    check(np.array_equal(expected_valid, np.asarray(boundary_valid)),
          "surface pressure valid metadata identity")
    check(np.array_equal(expected_quality, np.asarray(boundary_quality)),
          "surface pressure quality metadata identity")
    expected_source = np.where(
        changed_surface,
        expected_source | SOURCE_COLUMN_PHYSICS,
        expected_source,
    )
    check(np.array_equal(np.asarray(candidate_source, dtype=np.int64), expected_source),
          "surface pressure physics source only on changed cells")

    support = values(dataset["geopotential_support"]).astype(np.int64) \
        if "geopotential_support" in dataset.variables else None
    reference = values(dataset["geopotential_reference_level"]).astype(np.int64) \
        if "geopotential_reference_level" in dataset.variables else None
    check(support is not None and reference is not None,
          "prescribed pressure geometry authorization")
    if support is None or reference is None:
        return True, False, arrays
    check(support.shape == shape and reference.shape == shape[1:],
          "prescribed pressure geometry authorization shape")
    support_bool = support.astype(bool)
    # Surface pressure is already a (y, x) field.  Rebuild from the stored
    # float32 candidate pressure, while retaining the float64 request only as
    # the receipt/round-trip check above.
    changed_columns = changed_surface
    check(np.all(~changed_columns | (reference == 0)),
          "changed pressure columns use surface reference zero")
    check(
        np.all(~changed_columns[None, :, :] | ~above | support_bool),
        "changed pressure columns have full active-level geometry support",
    )
    check(np.all(~support_bool | candidate_active), "geometry support above ground")
    check(np.all(~candidate_active | above | support_bool), "new cells have geometry support")

    from pressure_transition_reference import pressure_cell_geometry
    try:
        area = np.full(shape[1:], float(dataset.grid_dx_m) * float(dataset.grid_dy_m))
        expected_interface, expected_pressure_mass = pressure_cell_geometry(
            pressure, candidate_surface, candidate_active, area,
        )
    except (TypeError, ValueError) as error:
        check(False, f"candidate pressure geometry: {error}")
        return True, False, arrays
    expected_cell_dp = np.where(candidate_active, expected_interface[:-1] - expected_interface[1:], 0.0)
    check(np.allclose(candidate_interface, expected_interface, rtol=0.0, atol=1.0e-10),
          "candidate pressure-interface construction")
    check(np.allclose(candidate_cell_dp, expected_cell_dp, rtol=0.0, atol=1.0e-10),
          "candidate cell dp/interface identity")
    check(np.allclose(candidate_pressure_mass, expected_pressure_mass,
                      rtol=1.0e-12, atol=1.0e-6),
          "candidate pressure mass identity")

    # The writer intentionally preserves untouched columns bit-for-bit even
    # when rebuilding the rest of the candidate geometry normalizes a value.
    # Dry-air mass is state-dependent and may legitimately differ after the
    # thermo/analysis stages even where surface pressure is unchanged.
    for name, candidate_array, background_array in (
        ("candidate pressure interface", candidate_interface, base_pressure_interface),
        ("candidate cell dp", candidate_cell_dp, base_cell_dp),
        ("candidate pressure mass", candidate_pressure_mass, base_pressure_mass),
    ):
        unchanged = np.broadcast_to(~changed_columns[None, :, :], candidate_array.shape)
        check(np.all(candidate_array[unchanged] == background_array[unchanged]),
              f"{name} unchanged-column identity")

    return True, bool(clean), arrays


def read_omega_target_error_extension(
    dataset: netCDF4.Dataset,
    shape: tuple[int, ...],
    above_ground: np.ndarray,
    valid_time_epoch: int | None,
    require,
) -> tuple[bool, bool, dict[str, np.ndarray]]:
    """Read the optional diagonal omega-target error/provenance group.

    The group is self-identifying through its global contract attribute.  The
    caller binds its presence to canonical schema 4; an absent group remains
    readable only as a canonical-3 historical artifact.
    """

    present_attributes = set(OMEGA_TARGET_ERROR_ATTRIBUTES) & set(dataset.ncattrs())
    present_variables = set(OMEGA_TARGET_ERROR_VARIABLES) & set(dataset.variables)
    present = bool(present_attributes or present_variables)
    if not present:
        return False, False, {}

    complete = (
        set(OMEGA_TARGET_ERROR_ATTRIBUTES) <= set(dataset.ncattrs())
        and set(OMEGA_TARGET_ERROR_VARIABLES) <= set(dataset.variables)
    )
    require(complete, "complete omega target error group")
    if not complete:
        return True, False, {}

    contract = getattr(dataset, "omega_target_error_contract", None)
    require(contract == OMEGA_TARGET_ERROR_CONTRACT, "omega target error contract")

    sigma: dict[str, np.ndarray] = {}
    for name in OMEGA_TARGET_ERROR_VARIABLES:
        variable = dataset.variables[name]
        require(variable.dimensions == ("z", "y", "x"), f"{name} dimensions")
        expected_dtype = np.dtype(np.float32 if name == "omega_target_sigma" else np.int32)
        require(np.dtype(variable.dtype) == expected_dtype, f"{name} type")
        require(getattr(variable, "units", "") == ("Pa s-1" if name == "omega_target_sigma" else "1"),
                f"{name} units")
        require(
            "scale_factor" not in variable.ncattrs()
            and "add_offset" not in variable.ncattrs(),
            f"{name} must not be packed",
        )
        if name != "omega_target_sigma":
            require("valid_time" not in variable.ncattrs(), f"{name} valid time metadata")
        array = values(variable)
        require(array.dtype == expected_dtype, f"{name} unpacked type")
        require(array.shape == shape, f"{name} shape")
        sigma[name] = array

    sigma_time = exact_scalar_int64(
        getattr(dataset.variables["omega_target_sigma"], "valid_time", None)
    )
    require(sigma_time is not None, "omega target sigma valid time type")
    if valid_time_epoch is not None and sigma_time is not None:
        require(sigma_time == valid_time_epoch, "omega target sigma valid time")

    sigma_value = sigma["omega_target_sigma"]
    sigma_valid = sigma["omega_target_sigma_valid"]
    sigma_quality = sigma["omega_target_sigma_quality"].astype(np.int64)
    sigma_source = sigma["omega_target_sigma_source"].astype(np.int64)
    require(np.all((sigma_valid == 0) | (sigma_valid == 1)), "omega target sigma valid binary")
    require(np.all(sigma_quality >= 0), "omega target sigma quality nonnegative")
    require(
        np.all((sigma_quality & ~QUALITY_KNOWN_BITS) == 0),
        "omega target sigma quality bits",
    )
    require(np.all(sigma_source >= 0), "omega target sigma source nonnegative")
    require(
        np.all((sigma_source & ~SOURCE_KNOWN_BITS) == 0),
        "omega target sigma source bits",
    )
    valid = sigma_valid.astype(bool)
    require(np.all(~valid | above_ground), "omega target sigma below ground")
    # The canonical contract only interprets payloads selected by valid=1.
    # Invalid payloads are deliberately opaque so a missing-error no-op cannot
    # be turned into authority by inspecting stale or arbitrary values.
    require(np.all(~valid | np.isfinite(sigma_value)), "omega target sigma finite")
    require(np.all(~valid | (sigma_value > 0.0)), "omega target sigma positive")
    require(
        np.all(
            ~valid
            | (
                (sigma_source > 0)
                & ((sigma_quality & QUALITY_EXCLUDED_BITS) == 0)
            )
        ),
        "omega target sigma usable metadata",
    )

    clean = (
        contract == OMEGA_TARGET_ERROR_CONTRACT
        and sigma_time is not None
        and (valid_time_epoch is None or sigma_time == valid_time_epoch)
        and sigma["omega_target_sigma"].dtype == np.dtype(np.float32)
        and sigma["omega_target_sigma_valid"].dtype == np.dtype(np.int32)
        and sigma["omega_target_sigma_quality"].dtype == np.dtype(np.int32)
        and sigma["omega_target_sigma_source"].dtype == np.dtype(np.int32)
        and np.all((sigma_valid == 0) | (sigma_valid == 1))
        and np.all(sigma_quality >= 0)
        and np.all((sigma_quality & ~QUALITY_KNOWN_BITS) == 0)
        and np.all(sigma_source >= 0)
        and np.all((sigma_source & ~SOURCE_KNOWN_BITS) == 0)
        and np.all(~valid | above_ground)
        and np.all(~valid | np.isfinite(sigma_value))
        and np.all(~valid | (sigma_value > 0.0))
        and np.all(
            ~valid
            | ((sigma_source > 0) & ((sigma_quality & QUALITY_EXCLUDED_BITS) == 0))
        )
    )
    return True, bool(clean), sigma


def read_pressure_analysis_candidate_extension(
    dataset: netCDF4.Dataset,
    shape: tuple[int, ...],
    above_ground: np.ndarray,
    valid_time_epoch: int | None,
    canonical_schema_version: int | None,
    diagnostic_schema_version: int,
    require,
) -> tuple[bool, bool, dict[str, np.ndarray]]:
    """Read the opt-in immutable omega-target input extension.

    This extension is deliberately separate from the historical diagnostic
    schemas.  It is valid only with canonical schema 4 and must be complete;
    a partial or unknown-looking group is never treated as a legacy file.
    """

    present_attributes = set(PRESSURE_ANALYSIS_CANDIDATE_ATTRIBUTES) & set(dataset.ncattrs())
    present_variables = set(PRESSURE_ANALYSIS_CANDIDATE_VARIABLES) & set(dataset.variables)
    signalled = bool(present_attributes or present_variables)
    if not signalled:
        return False, False, {}

    require(canonical_schema_version in (4, 5), "pressure analysis candidate requires canonical schema 4 or 5")
    require(
        diagnostic_schema_version in (5, 7, 8),
        "pressure analysis candidate diagnostic schema",
    )
    complete = (
        set(PRESSURE_ANALYSIS_CANDIDATE_ATTRIBUTES) <= set(dataset.ncattrs())
        and set(PRESSURE_ANALYSIS_CANDIDATE_VARIABLES) <= set(dataset.variables)
    )
    require(complete, "complete pressure analysis candidate extension")
    if not complete:
        return True, False, {}
    require(
        getattr(dataset, "pressure_analysis_candidate_contract", "")
        == PRESSURE_ANALYSIS_CANDIDATE_CONTRACT,
        "pressure analysis candidate contract",
    )

    original: dict[str, np.ndarray] = {}
    for name in PRESSURE_ANALYSIS_CANDIDATE_VARIABLES:
        variable = dataset.variables[name]
        require(variable.dimensions == ("z", "y", "x"), f"{name} dimensions")
        expected_dtype = np.dtype(np.float32 if name == "original_omega_target" else np.int32)
        require(np.dtype(variable.dtype) == expected_dtype, f"{name} type")
        require(getattr(variable, "units", "") == ("Pa s-1" if name == "original_omega_target" else "1"),
                f"{name} units")
        require(
            "scale_factor" not in variable.ncattrs()
            and "add_offset" not in variable.ncattrs(),
            f"{name} must not be packed",
        )
        if name != "original_omega_target":
            require("valid_time" not in variable.ncattrs(), f"{name} valid time metadata")
        array = values(variable)
        require(array.dtype == expected_dtype, f"{name} unpacked type")
        require(array.shape == shape, f"{name} shape")
        original[name] = array

    value_time = exact_scalar_int64(
        getattr(dataset.variables["original_omega_target"], "valid_time", None)
    )
    require(value_time is not None, "original omega target valid time type")
    if valid_time_epoch is not None and value_time is not None:
        require(value_time == valid_time_epoch, "original omega target valid time")

    original_valid = original["original_omega_target_valid"]
    original_quality = original["original_omega_target_quality"].astype(np.int64)
    original_source = original["original_omega_target_source"].astype(np.int64)
    original_value = original["original_omega_target"]
    require(np.all((original_valid == 0) | (original_valid == 1)),
            "original omega target valid binary")
    require(np.all(original_quality >= 0), "original omega target quality nonnegative")
    require(np.all((original_quality & ~QUALITY_KNOWN_BITS) == 0),
            "original omega target quality bits")
    require(np.all(original_source >= 0), "original omega target source nonnegative")
    require(np.all((original_source & ~SOURCE_KNOWN_BITS) == 0),
            "original omega target source bits")
    require(np.all(np.isfinite(original_value)), "original omega target finite")
    require(
        np.all(
            canonical_omega_target_cells(
                original_valid.astype(bool),
                above_ground,
                original_quality,
                original_source,
                original_value,
            )
        ),
        "canonical original omega target cells",
    )

    clean = (
        canonical_schema_version in (4, 5)
        and diagnostic_schema_version in (5, 7, 8)
        and getattr(dataset, "pressure_analysis_candidate_contract", "")
        == PRESSURE_ANALYSIS_CANDIDATE_CONTRACT
        and value_time is not None
        and (valid_time_epoch is None or value_time == valid_time_epoch)
        and original_value.dtype == np.dtype(np.float32)
        and original_valid.dtype == np.dtype(np.int32)
        and original["original_omega_target_quality"].dtype == np.dtype(np.int32)
        and original["original_omega_target_source"].dtype == np.dtype(np.int32)
        and original_value.shape == shape
        and original_valid.shape == shape
        and original_quality.shape == shape
        and original_source.shape == shape
        and np.all((original_valid == 0) | (original_valid == 1))
        and np.all(original_quality >= 0)
        and np.all((original_quality & ~QUALITY_KNOWN_BITS) == 0)
        and np.all(original_source >= 0)
        and np.all((original_source & ~SOURCE_KNOWN_BITS) == 0)
        and np.all(np.isfinite(original_value))
        and np.all(
            canonical_omega_target_cells(
                original_valid.astype(bool),
                above_ground,
                original_quality,
                original_source,
                original_value,
            )
        )
    )
    return True, bool(clean), original


def validate_outer_extension(dataset: netCDF4.Dataset, schema8: bool, require) -> None:
    """Validate schema-8 producer-replay lineage metadata."""
    present = set(OUTER_ATTRIBUTE_NAMES) & set(dataset.ncattrs())
    if not schema8:
        if present:
            require(False, "schema8 outer attributes are reserved for schema 8")
        return

    require(getattr(dataset, "outer_contract", "") == OUTER_CONTRACT,
            "outer contract")
    maximum_iterations = exact_scalar_int32(
        getattr(dataset, "outer_maximum_iterations", None)
    )
    require(maximum_iterations is not None, "outer maximum iterations type")
    if maximum_iterations is not None:
        require(2 <= maximum_iterations <= 32, "outer maximum iterations range")

    iterations = exact_scalar_int32(getattr(dataset, "outer_iterations", None))
    require(iterations is not None, "outer iterations type")
    if iterations is not None and maximum_iterations is not None:
        require(1 <= iterations <= maximum_iterations, "outer iterations range")
    require(
        exact_scalar_int32(getattr(dataset, "outer_converged", None)) == 1,
        "outer converged",
    )
    require(
        getattr(dataset, "outer_feedback_fields", "") == OUTER_FEEDBACK_FIELDS,
        "outer feedback fields",
    )
    require(
        getattr(dataset, "outer_feedback_units", "") == OUTER_FEEDBACK_UNITS,
        "outer feedback units",
    )

    raw_delta = getattr(dataset, "outer_max_abs_delta", None)
    if raw_delta is None:
        require(False, "outer max-abs delta missing")
        return
    delta = np.asarray(raw_delta)
    require(delta.dtype == np.dtype(np.float64), "outer max-abs delta type")
    if (
        delta.dtype != np.dtype(np.float64)
        or delta.ndim != 1
        or iterations is None
        or iterations < 1
    ):
        require(delta.ndim == 1, "outer max-abs delta shape")
        return
    require(delta.shape == (5 * iterations,), "outer max-abs delta shape")
    if delta.shape != (5 * iterations,):
        return
    delta = np.ascontiguousarray(delta)
    require(np.all(np.isfinite(delta)), "outer max-abs delta finite")
    require(np.all(delta >= 0.0), "outer max-abs delta nonnegative")
    # The writer flattens its (component, trial) Fortran array, so each
    # consecutive group of five values belongs to one trial.
    trials = delta.reshape((iterations, 5))
    require(np.all(trials[-1] == 0.0), "outer final trial converged")
    if iterations > 1:
        require(
            np.all(np.any(trials[:-1] != 0.0, axis=1)),
            "outer prior trials made progress",
        )


def read_radar_reconstruction_extension(
    dataset: netCDF4.Dataset,
    shape: tuple[int, ...],
    valid_time_epoch: int | None,
    schema8: bool,
    require,
    *,
    allow_single_pass_transition: bool = False,
) -> tuple[bool, bool, dict[str, np.ndarray]]:
    """Read and validate the optional radar replay inputs.

    The group deliberately is not named in ``schema_extensions``.  Its global
    contract attribute makes it self-identifying, while the all-or-none check
    prevents a partially written group from being mistaken for a legacy file.
    """

    present_attributes = set(RADAR_RECONSTRUCTION_ATTRIBUTES) & set(dataset.ncattrs())
    present_variables = set(RADAR_RECONSTRUCTION_VARIABLES) & set(dataset.variables)
    present = bool(present_attributes or present_variables)
    if not schema8 and not allow_single_pass_transition:
        if present:
            require(False, "schema8 radar reconstruction inputs are reserved for schema 8")
        return False, False, {}
    if not present:
        if allow_single_pass_transition and not schema8:
            require(False, "single-pass transition requires radar reconstruction inputs")
        return False, False, {}

    complete = (
        set(RADAR_RECONSTRUCTION_ATTRIBUTES) <= set(dataset.ncattrs())
        and set(RADAR_RECONSTRUCTION_VARIABLES) <= set(dataset.variables)
    )
    require(complete, "complete radar reconstruction input group")
    if not complete:
        return True, False, {}

    contract = getattr(dataset, "radar_reconstruction_contract", None)
    require(contract == RADAR_RECONSTRUCTION_CONTRACT, "radar reconstruction contract")

    raw_minimum = getattr(dataset, "column_minimum_dbz", None)
    minimum_array = np.asarray(raw_minimum) if raw_minimum is not None else np.asarray(())
    minimum_dbz: float | None = None
    require(minimum_array.ndim == 0, "column minimum dBZ scalar")
    require(minimum_array.dtype == np.dtype(np.float64), "column minimum dBZ type")
    if minimum_array.ndim == 0 and minimum_array.dtype == np.dtype(np.float64):
        minimum_dbz = float(minimum_array)
        require(np.isfinite(minimum_dbz), "column minimum dBZ finite")
        require(0.0 <= minimum_dbz <= 80.0, "column minimum dBZ range")

    phase: dict[str, np.ndarray] = {}
    for name in RADAR_RECONSTRUCTION_VARIABLES:
        variable = dataset.variables[name]
        require(variable.dimensions == ("z", "y", "x"), f"{name} dimensions")
        require(np.dtype(variable.dtype) == np.dtype(np.int32), f"{name} type")
        require(getattr(variable, "units", "") == "1", f"{name} units")
        require(
            "scale_factor" not in variable.ncattrs()
            and "add_offset" not in variable.ncattrs(),
            f"{name} must not be packed",
        )
        array = values(variable)
        require(array.dtype == np.dtype(np.int32), f"{name} unpacked type")
        require(array.shape == shape, f"{name} shape")
        phase[name] = array

    phase_value = dataset.variables["background_precipitation_phase"]
    phase_time = exact_scalar_int64(getattr(phase_value, "valid_time", None))
    require(phase_time is not None, "background precipitation phase valid time type")
    if valid_time_epoch is not None and phase_time is not None:
        require(phase_time == valid_time_epoch, "background precipitation phase valid time")
    require(
        getattr(phase_value, "code_table", "") == "precipitation_phase_v1",
        "background precipitation phase code table",
    )

    phase_valid = phase["background_precipitation_phase_valid"]
    phase_quality = phase["background_precipitation_phase_quality"]
    phase_source = phase["background_precipitation_phase_source"]
    require(np.all((phase_valid == 0) | (phase_valid == 1)), "phase valid binary")
    require(np.all(phase_quality >= 0), "phase quality nonnegative")
    require(
        np.all((phase_quality & ~QUALITY_KNOWN_BITS) == 0),
        "phase quality bits",
    )
    require(np.all(phase_source >= 0), "phase source nonnegative")
    require(
        np.all((phase_source & ~SOURCE_KNOWN_BITS) == 0),
        "phase source bits",
    )
    valid = phase_valid.astype(bool)
    require(
        np.all(~valid | ((phase_source & SOURCE_PHASE_EVIDENCE) != 0)),
        "phase valid source evidence",
    )
    # Production phase consumers only inspect valid, usable cells.  Preserve
    # arbitrary values on invalid cells for compatibility with legacy inputs.
    require(
        np.all(~valid | ((phase["background_precipitation_phase"] >= PHASE_UNKNOWN)
                         & (phase["background_precipitation_phase"] <= PHASE_GRAUPEL))),
        "phase valid enum",
    )

    # Keep the explicit result conservative by requiring all group fields again
    # from their in-memory values.  This avoids coupling the helper to the
    # validator's failure-list implementation.
    clean = (
        contract == RADAR_RECONSTRUCTION_CONTRACT
        and minimum_dbz is not None
        and np.isfinite(minimum_dbz)
        and 0.0 <= minimum_dbz <= 80.0
        and phase_time is not None
        and (valid_time_epoch is None or phase_time == valid_time_epoch)
        and getattr(phase_value, "code_table", "") == "precipitation_phase_v1"
        and all(
            variable.dimensions == ("z", "y", "x")
            and np.dtype(variable.dtype) == np.dtype(np.int32)
            and getattr(variable, "units", "") == "1"
            and "scale_factor" not in variable.ncattrs()
            and "add_offset" not in variable.ncattrs()
            and phase[name].dtype == np.dtype(np.int32)
            and phase[name].shape == shape
            for name, variable in (
                (name, dataset.variables[name]) for name in RADAR_RECONSTRUCTION_VARIABLES
            )
        )
        and np.all((phase_valid == 0) | (phase_valid == 1))
        and np.all(phase_quality >= 0)
        and np.all((phase_quality & ~QUALITY_KNOWN_BITS) == 0)
        and np.all(phase_source >= 0)
        and np.all((phase_source & ~SOURCE_KNOWN_BITS) == 0)
        and np.all(~valid | ((phase_source & SOURCE_PHASE_EVIDENCE) != 0))
        and np.all(
            ~valid
            | ((phase["background_precipitation_phase"] >= PHASE_UNKNOWN)
               & (phase["background_precipitation_phase"] <= PHASE_GRAUPEL))
        )
    )
    return True, bool(clean), phase


def reconstruct_radar_proposal(
    dataset: netCDF4.Dataset,
    fields: dict[str, np.ndarray],
    masks: dict[str, np.ndarray],
    pressure: np.ndarray,
    surface_pressure: np.ndarray,
    phase_inputs: dict[str, np.ndarray],
    minimum_dbz: float,
    require,
    *,
    evaluation_prefix: str,
    represented_only: bool = False,
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray], dict[str, np.ndarray]] | None:
    """Reconstruct pre-thermo precipitation, independently of final remapping.

    A single-pass transition evaluates the immutable background. The existing
    converged outer loop instead evaluates the final feedback fields.
    Successful replay returns proposal values, validity masks, and source
    provenance for each precipitation species.
    """

    clean = True

    def check(condition: object, message: str) -> None:
        nonlocal clean
        clean = clean and bool(condition)
        require(bool(condition), message)

    if evaluation_prefix not in ("background", "candidate"):
        check(False, "radar reference evaluation state")
        return None

    try:
        from pressure_radar_reference import (  # type: ignore
            reconstruct_radar_precipitation,
        )
    except Exception as error:
        check(False, f"radar reference unavailable: {type(error).__name__}")
        return None

    def global_float(name: str) -> float:
        return float(getattr(dataset, name))

    config = {
        "radar_wavelength_m": global_float("configured_assumed_radar_wavelength_m"),
        "minimum_dbz": minimum_dbz,
        "maximum_dbz": global_float("maximum_usable_dbz"),
        "reference_mass_concentration": global_float("reference_mass_concentration"),
        "minimum_relative_fall_speed": global_float("minimum_relative_fall_speed"),
        "maximum_horizontal_substep": global_float("maximum_horizontal_substep"),
        "maximum_transport_substeps": exact_scalar_integer(
            getattr(dataset, "maximum_transport_substeps", None)
        ),
        "precipitation_loading_efficiency": global_float(
            "precipitation_loading_efficiency"
        ),
        "maximum_downdraft_ms": global_float("maximum_downdraft_ms"),
        "maximum_downdraft_innovation_ms": global_float(
            "maximum_downdraft_innovation_ms"
        ),
        "ledger_relative_tolerance": global_float("ledger_relative_tolerance"),
        "ledger_absolute_tolerance": global_float("ledger_absolute_tolerance"),
    }
    if config["maximum_transport_substeps"] is None:
        check(False, "radar reference maximum transport substeps")
        return None

    # The phase input is the immutable background field.  A missing/invalid
    # phase record follows production's UNKNOWN fallback and cannot create an
    # observed phase authority on its own.
    phase_value = phase_inputs["background_precipitation_phase"]
    phase_valid = phase_inputs["background_precipitation_phase_valid"].astype(bool)
    phase_quality = phase_inputs["background_precipitation_phase_quality"]
    phase_source = phase_inputs["background_precipitation_phase_source"]
    phase_usable = phase_valid & (phase_source > 0) & (
        (phase_quality & QUALITY_EXCLUDED_BITS) == 0
    )
    phase = np.where(phase_usable, phase_value, PHASE_UNKNOWN).astype(np.float64)

    above = masks["above_ground"]
    radar_observed = (
        above
        & masks["radar_valid"]
        & np.isfinite(fields["radar_dbz"])
        & (fields["radar_dbz"] >= minimum_dbz)
        & (fields["radar_dbz"] <= config["maximum_dbz"])
    )
    dx = np.full(surface_pressure.shape, global_float("grid_dx_m"), dtype=np.float64)
    dy = np.full(surface_pressure.shape, global_float("grid_dy_m"), dtype=np.float64)

    try:
        result = reconstruct_radar_precipitation(
            # The NetCDF pressure coordinate is one-dimensional; the oracle
            # consumes the broadcast pressure centers used by each column.
            pressure=np.broadcast_to(pressure[:, None, None], above.shape),
            temperature=fields[f"{evaluation_prefix}_temperature"],
            vapor=fields[f"{evaluation_prefix}_vapor"],
            u=fields[f"{evaluation_prefix}_u"],
            v=fields[f"{evaluation_prefix}_v"],
            omega=fields[f"{evaluation_prefix}_omega"],
            dx=dx,
            dy=dy,
            pressure_surface=surface_pressure,
            above=above,
            domain=above,
            radar_observed=radar_observed,
            radar_no_echo=masks["radar_no_echo"],
            radar_dbz=fields["radar_dbz"],
            phase=phase,
            config=config,
        )
    except Exception as error:
        ledger = getattr(error, "ledger", None)
        if ledger is not None:
            check(False, f"radar reference replay: {error}")
        else:
            check(False, f"radar reference replay: {type(error).__name__}: {error}")
        return None

    fresh = {
        "rain": np.asarray(result.rain, dtype=np.float64),
        "snow": np.asarray(result.snow, dtype=np.float64),
        "graupel": np.asarray(result.graupel, dtype=np.float64),
    }
    shape = above.shape
    if any(array.shape != shape for array in fresh.values()):
        check(False, "radar reference precipitation shape")
        return None

    derived = radar_observed.copy()
    for array in fresh.values():
        derived |= array > 0.0

    # Production publishes observed cells as a replacement.  Descendants add
    # only valid original background precipitation; cells with no fresh radar
    # descendant retain the immutable background unchanged.
    background_valid = {
        species: values(dataset[f"background_{species}_valid"]).astype(bool)
        for species in ("rain", "snow", "graupel")
    }
    proposal = {}
    proposal_source = {}
    for species in ("rain", "snow", "graupel"):
        background = fields[f"background_{species}"].astype(np.float64)
        background_source = values(dataset[f"background_{species}_source"])
        radar_source = SOURCE_RADAR_DBZ | SOURCE_COLUMN_PHYSICS
        proposal_source[species] = np.where(
            radar_observed, radar_source,
            np.where(derived, background_source | radar_source, background_source),
        )
        expected = np.where(
            radar_observed,
            fresh[species],
            np.where(
                derived,
                fresh[species] + np.where(background_valid[species], background, 0.0),
                background,
            ),
        )
        expected_stored = expected.astype(np.float32).astype(np.float64)
        if represented_only:
            background_quality = values(dataset[f"background_{species}_quality"])
            # Mirror publish_hydrometeor_candidate's output metadata.  Every
            # derived cell is valid and gets radar+column source authority;
            # observed cells and cells with an invalid prior clear old quality,
            # while a valid nonobserved descendant inherits its prior quality.
            published_valid = np.where(derived, True, background_valid[species])
            published_quality = np.where(
                radar_observed | (derived & ~background_valid[species]),
                0,
                background_quality,
            )
            represented = published_valid & (proposal_source[species] > 0) & (
                (published_quality & QUALITY_EXCLUDED_BITS) == 0
            )
            expected_stored = np.where(represented, expected_stored, 0.0)
        check(np.all(np.isfinite(expected_stored)), f"radar {species} proposal finite")
        proposal[species] = expected_stored

    ledger = result.ledger
    expected_ledger = {
        "flux_input": float(ledger.input),
        "flux_deposited": float(ledger.deposited),
        "flux_suspended": float(ledger.suspended),
        "flux_boundary_exit": float(ledger.boundary_exit),
        "flux_terrain_intercept": float(ledger.terrain_intercept),
        "flux_observation_blocked": float(ledger.observation_blocked),
        "flux_no_echo_blocked": float(ledger.no_echo_blocked),
        "flux_microphysical_loss": float(ledger.microphysical_loss),
    }
    expected_ledger["flux_ledger_error"] = abs(
        expected_ledger["flux_input"]
        - sum(expected_ledger[name] for name in (
            "flux_deposited", "flux_suspended", "flux_boundary_exit",
            "flux_terrain_intercept", "flux_observation_blocked",
            "flux_no_echo_blocked", "flux_microphysical_loss",
        ))
    )
    for name, expected in expected_ledger.items():
        try:
            actual = float(getattr(dataset, name))
        except (AttributeError, TypeError, ValueError):
            check(False, f"{name} reference value")
            continue
        tolerance = (
            radar_ledger_residual_tolerance(expected_ledger)
            if name == "flux_ledger_error"
            else radar_ledger_operand_tolerance(expected)
        )
        check(
            np.isfinite(actual) and abs(actual - expected) <= tolerance,
            f"{name} independent radar ledger",
        )

    expected_substeps = int(getattr(ledger, "maximum_required_substeps"))
    actual_substeps = exact_scalar_int32(
        getattr(dataset, "transport_required_substeps", None)
    )
    check(actual_substeps is not None, "transport substeps reference type")
    if actual_substeps is not None:
        check(actual_substeps == expected_substeps, "transport substeps independent radar ledger")
    proposal_validity = {
        species: background_valid[species] | derived
        for species in ("rain", "snow", "graupel")
    }
    return (proposal, proposal_validity, proposal_source) if clean else None


def validate_radar_reconstruction_reference(
    dataset: netCDF4.Dataset,
    fields: dict[str, np.ndarray],
    masks: dict[str, np.ndarray],
    pressure: np.ndarray,
    surface_pressure: np.ndarray,
    phase_inputs: dict[str, np.ndarray],
    minimum_dbz: float,
    require,
) -> bool:
    """Check final precipitation for the existing converged, non-remapped path."""
    replay = reconstruct_radar_proposal(
        dataset, fields, masks, pressure, surface_pressure, phase_inputs,
        minimum_dbz, require, evaluation_prefix="candidate",
    )
    if replay is None:
        return False
    proposal, _, _ = replay
    clean = True
    for species, expected in proposal.items():
        actual = fields[f"candidate_{species}"].astype(np.float64)
        tolerance = 1.0e-10 + 2.0e-6 * np.abs(expected)
        matched = bool(np.all(np.abs(actual - expected) <= tolerance))
        require(matched, f"independent radar {species} reconstruction")
        clean = clean and matched
    return clean


def validate_thermo_stage_budget(
    reported_budget, dry_mass, before_temperature, before_species,
    after_temperature, after_species, selected, require,
) -> bool:
    """Check a phase-stage ledger on retained dry mass, before geometry remap."""
    # Select first: absent/unselected placeholders are not physical operands.
    mass = dry_mass[selected].astype(np.float64)
    initial_t = before_temperature[selected].astype(np.float64)
    final_t = after_temperature[selected].astype(np.float64)
    before = before_species[:, selected].astype(np.float64)
    after = after_species[:, selected].astype(np.float64)
    change = after - before
    capacity = THERMO_CP_DRY + THERMO_SPECIES_CP @ after
    sensible = capacity * (final_t - initial_t)
    phase = np.sum(change * (THERMO_SPECIES_H0[:, None]
                   + THERMO_SPECIES_CP[:, None] * (initial_t - THERMO_T0)), axis=0)
    species_terms = mass * change
    sensible_terms = mass * sensible
    phase_terms = mass * phase
    species_total = np.sum(species_terms, axis=1)
    sensible_total = float(np.sum(sensible_terms))
    phase_total = float(np.sum(phase_terms))
    expected = {
        "species": species_total,
        "thermo_sensible_change_j": sensible_total,
        "thermo_phase_change_j": phase_total,
        "thermo_water_error_kg": float(np.sum(species_total)),
        "thermo_enthalpy_error_j": sensible_total + phase_total,
    }
    scales = {
        "species": np.sum(np.abs(species_terms), axis=1),
        "thermo_sensible_change_j": float(np.sum(np.abs(sensible_terms))),
        "thermo_phase_change_j": float(np.sum(np.abs(phase_terms))),
        "thermo_water_error_kg": float(np.sum(np.abs(species_terms))),
        "thermo_enthalpy_error_j": float(np.sum(np.abs(sensible_terms))
                                         + np.sum(np.abs(phase_terms))),
    }
    factor = 128.0 * np.finfo(np.float64).eps * max(1, mass.size)
    clean = True
    for name, value in expected.items():
        raw = reported_budget.get(name)
        try:
            actual = np.asarray(raw, dtype=np.float64)
            tolerance = factor * np.maximum(scales[name], np.finfo(np.float64).tiny)
            passed = (raw is not None and actual.shape == np.shape(value)
                      and np.all(np.isfinite(actual)) and np.all(np.isfinite(value))
                      and np.all(np.abs(actual - value) <= tolerance))
        except (TypeError, ValueError):
            passed = False
        require(bool(passed), f"{name} budget")
        clean = clean and bool(passed)
    return clean


def transition_replay_is_exact(errors: dict[str, float]) -> bool:
    """V1 accepts only a complete, exact stored-state replay, not telemetry."""
    expected = {"temperature", "dry_air_mass", *THERMO_SPECIES}
    return set(errors) == expected and all(
        isinstance(value, (float, np.floating))
        and np.isfinite(value) and value == 0.0
        for value in errors.values()
    )


def build_pressure_transition_replay(
    dataset, fields, masks, pressure, pressure_mass, pressure_interface,
    geometry, transition, phase_inputs, require,
) -> dict[str, np.ndarray] | None:
    """Reconstruct proposal, post-thermo and remapped states once from input."""
    from pressure_transition_reference import (
        pressure_cell_geometry,
        reconstruct_thermo_state_reference, remap_pressure_state_reference,
        validate_transition_seed_mass_reference,
    )

    above = masks["above_ground"]
    try:
        # The seed is the constructor state, not the rebased post-thermo
        # donor. Reconstruct its own full-cell metric, including columns
        # whose eventual candidate pressure decreases independently.
        seed_domain = transition["transition_seed_above_ground"].astype(bool)
        seed_ps = transition["transition_seed_surface_pressure"].astype(np.float64)
        area = np.full(above.shape[1:], float(dataset.grid_dx_m) * float(dataset.grid_dy_m))
        _, seed_metric = pressure_cell_geometry(pressure, seed_ps, seed_domain, area)
        seed_species = np.stack(tuple(
            transition[f"transition_seed_{name}"] for name in THERMO_SPECIES
        ))
        validate_transition_seed_mass_reference(
            seed_metric, seed_species, seed_domain, transition[PRESSURE_TRANSITION_DRY_MASS],
        )
        radar_proposal = reconstruct_radar_proposal(
            dataset, fields, masks, pressure, pressure_interface[0], phase_inputs,
            float(dataset.column_minimum_dbz), require,
            evaluation_prefix="background", represented_only=True,
        )
        if radar_proposal is None:
            return None
        proposal, proposal_valid, proposal_source = radar_proposal
        species = []
        species_valid = []
        species_source = []
        for name in THERMO_SPECIES:
            if name in proposal:
                value = proposal[name]
                valid = proposal_valid[name]
                source = proposal_source[name]
            else:
                valid = values(dataset[f"background_{name}_valid"]).astype(bool)
                source = values(dataset[f"background_{name}_source"])
                quality = values(dataset[f"background_{name}_quality"])
                usable = valid & (source > 0) & ((quality & QUALITY_EXCLUDED_BITS) == 0)
                value = np.where(usable, fields[f"background_{name}"], 0.0)
            species.append(np.where(above, value, 0.0))
            species_valid.append(valid)
            species_source.append(source)
        proposal_species = np.stack(species)
        post_t, post_q, post_mass = reconstruct_thermo_state_reference(
            np.broadcast_to(pressure[:, None, None], above.shape), pressure_mass,
            fields["background_temperature"], proposal_species,
            values(dataset["thermo_support"]).astype(bool),
            values(dataset["thermo_surface"]), float(dataset.thermo_target_rh),
        )
        candidate_above = transition["candidate_above_ground"].astype(bool)
        expected_mass, expected_t, expected_q = remap_pressure_state_reference(
            pressure_interface, post_mass, post_t, post_q, above,
            geometry["candidate_pressure_interface"], candidate_above,
            area, transition["transition_seed_temperature"], seed_species,
        )
        return {
            "proposal_species": proposal_species,
            "proposal_source": np.stack(species_source),
            "post_temperature": post_t,
            "post_species": post_q,
            "post_mass": post_mass,
            "post_valid": np.stack(species_valid),
            "candidate_above_ground": candidate_above,
            "final_mass": expected_mass,
            "final_temperature": expected_t,
            "final_species": expected_q,
        }
    except (KeyError, AttributeError, TypeError, ValueError, FloatingPointError) as error:
        require(False, f"pressure transition physical replay: {error}")
        return None


def pressure_transition_replay_errors(
    dataset, fields, masks, pressure, pressure_mass, pressure_interface,
    geometry, transition, phase_inputs, require, *, replay=None,
) -> dict[str, float]:
    """Check stage ledgers and measure final residuals; do not grant authority."""
    if replay is None:
        replay = build_pressure_transition_replay(
            dataset, fields, masks, pressure, pressure_mass, pressure_interface,
            geometry, transition, phase_inputs, require,
        )
    if replay is None:
        return {}
    above = masks["above_ground"]
    candidate_above = replay["candidate_above_ground"]
    try:
        reported_thermo = {
            "species": getattr(dataset, "thermo_species_change_kg", None),
            **{name: getattr(dataset, name, None) for name in (
                "thermo_sensible_change_j", "thermo_phase_change_j",
                "thermo_water_error_kg", "thermo_enthalpy_error_j",
            )},
        }
        validate_thermo_stage_budget(
            reported_thermo, replay["post_mass"], fields["background_temperature"],
            replay["proposal_species"], replay["post_temperature"], replay["post_species"],
            values(dataset["thermo_support"]).astype(bool), require,
        )
        validate_pressure_geometry_ledger(
            dataset, above, pressure_mass, values(dataset["dry_air_mass_measure"]),
            geometry["candidate_pressure_mass_measure"],
            geometry["candidate_dry_air_mass_measure"], fields, require,
            transition_replay=replay,
        )
        expected = {"temperature": replay["final_temperature"], "dry_air_mass": replay["final_mass"]}
        expected.update(zip(THERMO_SPECIES, replay["final_species"]))
        errors = {}
        for name, reference in expected.items():
            actual = (geometry["candidate_dry_air_mass_measure"] if name == "dry_air_mass"
                      else fields[f"candidate_{name}"])
            if actual.shape != reference.shape or np.any(~np.isfinite(actual[candidate_above])):
                raise ValueError(f"invalid final {name}")
            errors[name] = float(np.max(np.abs(actual[candidate_above] - reference[candidate_above]),
                                        initial=0.0))
        return errors
    except (KeyError, AttributeError, TypeError, ValueError, FloatingPointError) as error:
        require(False, f"pressure transition physical replay: {error}")
        return {}


def validate_thermo_extension(
    dataset: netCDF4.Dataset,
    above: np.ndarray,
    radar_no_echo: np.ndarray,
    pressure: np.ndarray,
    pressure_mass: np.ndarray,
    dry_air_mass: np.ndarray,
    fields: dict[str, np.ndarray],
    require,
    schema7: bool = False,
    candidate_pressure_mass: np.ndarray | None = None,
    variable_geometry: bool = False,
    *,
    transition_replay: dict[str, np.ndarray] | None = None,
) -> np.ndarray:
    """Validate the optional pressure-fixed cloud-thermo extension.

    The implementation mirrors the published equations in
    ``cloud_bal_column_physics.f90`` instead of importing production code.
    The returned mask contains value changes in temperature, vapor, or cloud
    condensate and is folded into the persisted column-change evidence by the
    caller.
    """

    shape = above.shape
    transition_mode = transition_replay is not None
    candidate_domain = above
    replay: dict[str, np.ndarray] = {}
    if transition_mode:
        expected_replay_keys = (
            "proposal_species", "proposal_source", "post_temperature", "post_species", "post_mass",
            "post_valid", "candidate_above_ground", "final_mass",
            "final_temperature", "final_species",
        )
        missing = [name for name in expected_replay_keys if name not in transition_replay]
        require(not missing, "transition thermo replay keys")
        if missing:
            return np.zeros(shape, dtype=bool)
        replay = {name: np.asarray(transition_replay[name]) for name in expected_replay_keys}
        replay_shapes = {
            "proposal_species": (6, *shape),
            "proposal_source": (6, *shape),
            "post_temperature": shape,
            "post_species": (6, *shape),
            "post_mass": shape,
            "post_valid": (6, *shape),
            "candidate_above_ground": shape,
            "final_mass": shape,
            "final_temperature": shape,
            "final_species": (6, *shape),
        }
        for name, expected_shape in replay_shapes.items():
            require(replay[name].shape == expected_shape, f"transition {name} shape")
        if any(replay[name].shape != expected_shape for name, expected_shape in replay_shapes.items()):
            return np.zeros(shape, dtype=bool)
        if all(replay[name].shape == expected_shape
               for name, expected_shape in replay_shapes.items()):
            require(replay["post_valid"].dtype == np.dtype(bool),
                    "transition post-valid type")
            require(replay["proposal_source"].dtype == np.dtype("int32"),
                    "transition proposal-source type")
            require(replay["candidate_above_ground"].dtype == np.dtype(bool),
                    "transition candidate above-ground type")
            if replay["post_valid"].dtype != np.dtype(bool) or replay["candidate_above_ground"].dtype != np.dtype(bool):
                return np.zeros(shape, dtype=bool)
            if replay["proposal_source"].dtype != np.dtype("int32"):
                return np.zeros(shape, dtype=bool)
            candidate_domain = replay["candidate_above_ground"]
            require(np.all(np.isfinite(replay["proposal_species"])),
                    "transition proposal finite")
            require(np.all(np.isfinite(replay["post_temperature"])),
                    "transition post temperature finite")
            require(np.all(np.isfinite(replay["post_species"])),
                    "transition post species finite")
            require(np.all(np.isfinite(replay["post_mass"])),
                    "transition post mass finite")
            require(np.all(np.isfinite(replay["final_temperature"])),
                    "transition final temperature finite")
            require(np.all(np.isfinite(replay["final_species"])),
                    "transition final species finite")
            require(np.all(np.isfinite(replay["final_mass"])),
                    "transition final mass finite")
            require(np.all((replay["candidate_above_ground"] == 0)
                           | (replay["candidate_above_ground"] == 1)),
                    "transition candidate above-ground binary")
            require(np.all(replay["post_mass"] >= 0.0),
                    "transition post mass nonnegative")
            require(np.all(replay["final_mass"] >= 0.0),
                    "transition final mass nonnegative")
    thermo_changed = np.zeros(shape, dtype=bool)

    def read_variable(name: str, expected_dtype: str | None = None) -> np.ndarray | None:
        if name not in dataset.variables:
            require(False, f"{name} variable")
            return None
        variable = dataset.variables[name]
        require(variable.dimensions == ("z", "y", "x"), f"{name} dimensions")
        if expected_dtype == "float32":
            require(np.dtype(variable.dtype) == np.dtype(np.float32), f"{name} type")
        elif expected_dtype == "float64":
            require(np.dtype(variable.dtype) == np.dtype(np.float64), f"{name} type")
        else:
            require(is_signed_int32(variable.dtype), f"{name} type")
        require("scale_factor" not in variable.ncattrs() and "add_offset" not in variable.ncattrs(),
                f"{name} must not be packed")
        array = values(variable)
        if expected_dtype == "float32":
            require(array.dtype == np.dtype(np.float32), f"{name} unpacked type")
        elif expected_dtype == "float64":
            require(array.dtype == np.dtype(np.float64), f"{name} unpacked type")
        else:
            require(is_signed_int32(array.dtype), f"{name} unpacked type")
        require(array.shape == shape, f"{name} shape")
        return array

    def scalar_attribute(name: str) -> float | None:
        raw = getattr(dataset, name, None)
        if raw is None:
            require(False, name)
            return None
        parsed = np.asarray(raw)
        require(parsed.ndim == 0, f"{name} scalar")
        try:
            result = float(parsed)
        except (TypeError, ValueError):
            require(False, name)
            return None
        require(np.isfinite(result), f"{name} finite")
        return result

    require(
        getattr(dataset, "thermo_contract", "")
        == "explicit_cloud_saturation_mixture_v1",
        "thermo contract",
    )
    analysis_vectors: dict[str, np.ndarray | None] = {}
    analysis_scalars: dict[str, float | None] = {}
    analysis_counts: dict[str, int | None] = {}
    if schema7:
        require(getattr(dataset, "analysis_contract", "") == ANALYSIS_CONTRACT,
                "analysis contract")

        def exact_float_attribute(name: str, shape: tuple[int, ...]) -> np.ndarray | None:
            raw = getattr(dataset, name, None)
            if raw is None:
                require(False, f"{name} missing")
                return None
            parsed = np.asarray(raw)
            require(parsed.dtype == np.dtype(np.float64), f"{name} type")
            require(parsed.shape == shape, f"{name} shape")
            if parsed.dtype != np.dtype(np.float64) or parsed.shape != shape:
                return None
            result = np.ascontiguousarray(parsed, dtype=np.float64)
            require(np.all(np.isfinite(result)), f"{name} finite")
            return result

        for name in ANALYSIS_VECTOR_ATTRIBUTES:
            analysis_vectors[name] = exact_float_attribute(name, (6,))
        for name in ANALYSIS_FLOAT_ATTRIBUTES:
            value = exact_float_attribute(name, ())
            analysis_scalars[name] = None if value is None else float(value.item())
        for name in ANALYSIS_COUNT_ATTRIBUTES:
            raw = getattr(dataset, name, None)
            value = exact_scalar_int64(raw)
            require(value is not None, f"{name} type")
            if value is not None:
                require(value >= 0, f"{name} nonnegative")
            analysis_counts[name] = value
    target_rh = scalar_attribute("thermo_target_rh")
    if target_rh is not None:
        require(0.0 <= target_rh <= 1.0, "thermo target RH range")

    reported_budget: dict[str, np.ndarray | float] = {}
    species_budget = getattr(dataset, "thermo_species_change_kg", None)
    if species_budget is None:
        require(False, "thermo_species_change_kg")
    else:
        species_budget = np.asarray(species_budget, dtype=np.float64)
        require(species_budget.shape == (6,), "thermo species budget shape")
        require(np.all(np.isfinite(species_budget)), "thermo species budget finite")
    reported_budget["species"] = species_budget
    for name in (
        "thermo_sensible_change_j",
        "thermo_phase_change_j",
        "thermo_water_error_kg",
        "thermo_enthalpy_error_j",
    ):
        reported_budget[name] = scalar_attribute(name)

    support = read_variable("thermo_support")
    surface = read_variable("thermo_surface")
    candidate_mass = read_variable("candidate_dry_air_mass_measure", "float64")
    if support is None or surface is None or candidate_mass is None:
        return thermo_changed
    require(np.all((support == 0) | (support == 1)), "thermo support binary")
    require(getattr(dataset.variables["thermo_support"], "units", "") == "1",
            "thermo support units")
    require(getattr(dataset.variables["thermo_surface"], "units", "") == "1",
            "thermo surface units")
    require(getattr(dataset.variables["candidate_dry_air_mass_measure"], "units", "") == "kg dryair",
            "candidate dry-air mass units")
    require(np.all((surface == SATURATION_LIQUID) | (surface == SATURATION_ICE) | (support == 0)),
            "thermo surface domain")
    support_mask = support.astype(bool)
    require(np.all(~support_mask | above), "thermo support above ground")
    require(
        np.all(np.isfinite(candidate_mass)) and np.all(candidate_mass >= 0.0),
        "candidate dry-air mass finite",
    )
    require(np.all(candidate_mass[~candidate_domain] == 0.0),
            "candidate dry-air mass below ground")

    background: dict[str, np.ndarray] = {}
    candidate: dict[str, np.ndarray] = {}
    metadata: dict[str, dict[str, dict[str, np.ndarray]]] = {
        "background": {},
        "candidate": {},
    }
    valid_time_epoch = exact_scalar_integer(
        getattr(dataset, "valid_time_epoch", None)
    )
    if valid_time_epoch is None:
        require(False, "valid_time_epoch")

    metadata_names = ("valid", "quality", "source")
    for species in THERMO_FIELDS:
        for prefix, output in (("background", background), ("candidate", candidate)):
            value_name = f"{prefix}_{species}"
            value = read_variable(value_name, "float32")
            if value is None:
                continue
            require(
                getattr(dataset.variables[value_name], "units", "")
                == THERMO_VALUE_UNITS[species],
                f"{value_name} units",
            )
            field_time = exact_scalar_integer(
                getattr(dataset.variables[value_name], "valid_time", None)
            )
            require(field_time is not None, f"{value_name} valid time")
            if valid_time_epoch is not None:
                require(field_time == valid_time_epoch, f"{value_name} valid time identity")
            output[species] = value
        for prefix in ("background", "candidate"):
            metadata[prefix].setdefault(species, {})
            for suffix in metadata_names:
                name = f"{prefix}_{species}_{suffix}"
                value = read_variable(name)
                if value is None:
                    continue
                variable = dataset.variables[name]
                require(getattr(variable, "units", "") == "1", f"{name} units")
                require(np.all(value >= 0), f"{name} nonnegative")
                if suffix == "valid":
                    require(np.all((value == 0) | (value == 1)), f"{name} binary")
                metadata[prefix][species][suffix] = value.astype(np.int64)

    if any(species not in background or species not in candidate for species in THERMO_FIELDS) or any(
        any(suffix not in metadata["background"].get(species, {}) for suffix in metadata_names)
        or any(suffix not in metadata["candidate"].get(species, {}) for suffix in metadata_names)
        for species in THERMO_FIELDS
    ):
        return thermo_changed

    transition_added = candidate_domain & ~above if transition_mode else np.zeros(shape, dtype=bool)
    transition_retained = ~transition_added
    transition_old_bottom: np.ndarray | None = None
    if transition_mode:
        transition_old_bottom = np.argmax(above, axis=0)
        remapped_columns = np.any(candidate_domain != above, axis=0)
        if candidate_pressure_mass is not None:
            remapped_columns |= np.any(candidate_pressure_mass != pressure_mass, axis=0)

    for species in THERMO_FIELDS:
        bg = background[species]
        cand = candidate[species]
        require(np.all(np.isfinite(bg)) and np.all(np.isfinite(cand)), f"{species} finite")
        fields[f"background_{species}"] = bg
        fields[f"candidate_{species}"] = cand
        bg_meta = metadata["background"][species]
        cand_meta = metadata["candidate"][species]
        for prefix, field_meta in (("background", bg_meta), ("candidate", cand_meta)):
            usable = (field_meta["source"] > 0) & (
                (field_meta["quality"] & QUALITY_EXCLUDED_BITS) == 0
            )
            require(np.all(~field_meta["valid"].astype(bool) | usable),
                    f"{prefix} {species} valid metadata usability")
        phase_field = species in ("temperature", "vapor", "cloud_water", "cloud_ice")
        if phase_field:
            if transition_mode:
                require(np.array_equal(bg_meta["valid"][transition_retained],
                                        cand_meta["valid"][transition_retained]),
                        f"{species} retained valid metadata unchanged")
                require(np.array_equal(bg_meta["quality"][transition_retained],
                                        cand_meta["quality"][transition_retained]),
                        f"{species} retained quality metadata unchanged")
            else:
                require(np.array_equal(bg_meta["valid"], cand_meta["valid"]),
                        f"{species} valid metadata unchanged")
                require(np.array_equal(bg_meta["quality"], cand_meta["quality"]),
                        f"{species} quality metadata unchanged")
        require(
            np.all((bg_meta["quality"] & ~QUALITY_KNOWN_BITS) == 0)
            and np.all((cand_meta["quality"] & ~QUALITY_KNOWN_BITS) == 0),
            f"{species} quality bits",
        )
        require(
            np.all((bg_meta["source"] & ~SOURCE_KNOWN_BITS) == 0)
            and np.all((cand_meta["source"] & ~SOURCE_KNOWN_BITS) == 0),
            f"{species} source bits",
        )
        if transition_mode and np.any(transition_added):
            seed_quality_name = f"transition_seed_{species}_quality"
            if seed_quality_name not in dataset.variables:
                require(False, f"{seed_quality_name} for transition metadata")
            else:
                seed_quality = values(dataset[seed_quality_name]).astype(np.int64)
                require(seed_quality.shape == shape,
                        f"{seed_quality_name} shape for transition metadata")
                if seed_quality.shape == shape and transition_old_bottom is not None:
                    yy, xx = np.indices(shape[1:])
                    donor_quality = cand_meta["quality"][transition_old_bottom, yy, xx]
                    expected_added_quality = seed_quality | donor_quality
                    require(np.array_equal(
                        cand_meta["valid"][transition_added],
                        np.ones(np.count_nonzero(transition_added), dtype=np.int64),
                    ), f"{species} added valid metadata")
                    require(np.array_equal(
                        cand_meta["quality"][transition_added],
                        expected_added_quality[transition_added],
                    ), f"{species} added quality metadata")
                    require(np.array_equal(
                        cand_meta["source"][transition_added],
                        np.full(np.count_nonzero(transition_added), SOURCE_COLUMN_PHYSICS,
                                dtype=np.int64),
                    ), f"{species} added source provenance")
        if phase_field:
            value_changed = changed_bits(bg, cand)
            if transition_mode:
                if species == "temperature":
                    post_stored = replay["post_temperature"]
                    final_stored = replay["final_temperature"]
                else:
                    species_index = THERMO_SPECIES.index(species)
                    post_stored = replay["post_species"][species_index]
                    final_stored = replay["final_species"][species_index]
                post_stored = np.where(support_mask, post_stored, bg).astype(np.float32)
                final_stored = final_stored.astype(np.float32)
                # The thermo stage is scoped to its original support.  A
                # transition remap may change any retained cell in a changed
                # column, and may populate newly represented cells.
                thermo_stage_changed = changed_bits(bg, post_stored) & support_mask
                remap_stage_changed = (changed_bits(post_stored, final_stored)
                                       & candidate_domain & remapped_columns)
                stage_changed = thermo_stage_changed | remap_stage_changed
                thermo_changed |= thermo_stage_changed
                expected_source = np.where(
                    transition_added,
                    SOURCE_COLUMN_PHYSICS,
                    np.where(
                        stage_changed,
                        bg_meta["source"] | SOURCE_COLUMN_PHYSICS,
                        bg_meta["source"],
                    ),
                )
                require(np.array_equal(cand_meta["source"], expected_source),
                        f"{species} changed source provenance")
            else:
                thermo_changed |= value_changed
                require(np.all(~value_changed | support_mask),
                        f"{species} changes outside thermo support")
                require(
                    np.array_equal(
                        cand_meta["source"],
                        np.where(
                            value_changed,
                            bg_meta["source"] | SOURCE_COLUMN_PHYSICS,
                            bg_meta["source"],
                        ),
                    ),
                    f"{species} changed source provenance",
                )
        elif transition_mode:
            species_index = THERMO_SPECIES.index(species)
            proposal_source = replay["proposal_source"][species_index]
            remap_stage_changed = changed_bits(
                replay["post_species"][species_index].astype(np.float32),
                replay["final_species"][species_index].astype(np.float32),
            ) & candidate_domain & remapped_columns
            expected_source = np.where(
                transition_added, SOURCE_COLUMN_PHYSICS,
                np.where(remap_stage_changed, proposal_source | SOURCE_COLUMN_PHYSICS,
                         proposal_source),
            )
            require(np.array_equal(cand_meta["source"], expected_source),
                    f"{species} remapped source provenance")

    # Base-schema hydrometeor values are the same variables in schema6.
    for prefix, values_by_species, domain in (
        ("background", background, above),
        ("candidate", candidate, candidate_domain),
    ):
        require(
            np.all((values_by_species["temperature"][domain] >= 150.0)
                   & (values_by_species["temperature"][domain] <= 350.0)),
            f"{prefix} temperature range",
        )
        require(
            np.all((values_by_species["vapor"][domain] >= 0.0)
                   & (values_by_species["vapor"][domain] <= 0.2)),
            f"{prefix} vapor range",
        )
        for species in THERMO_SPECIES:
            require(
                np.all(values_by_species[species][domain] >= 0.0),
                f"{prefix} {species} nonnegative",
            )

    require(np.any(support_mask), "thermo support nonempty")
    phase_before_usable = np.ones(shape, dtype=bool)
    for species in ("temperature", "vapor", "cloud_water", "cloud_ice"):
        field_metadata = metadata["background"][species]
        phase_before_usable &= (
            field_metadata["valid"].astype(bool)
            & (field_metadata["source"] > 0)
            & ((field_metadata["quality"] & QUALITY_EXCLUDED_BITS) == 0)
            & np.isfinite(background[species])
        )
    phase_after_usable = np.ones(shape, dtype=bool)
    for species in THERMO_FIELDS:
        field_metadata = metadata["candidate"][species]
        phase_after_usable &= (
            field_metadata["valid"].astype(bool)
            & (field_metadata["source"] > 0)
            & ((field_metadata["quality"] & QUALITY_EXCLUDED_BITS) == 0)
            & np.isfinite(candidate[species])
        )
    require(np.all(~support_mask | phase_before_usable), "background thermo support usability")
    require(np.all(~(candidate_domain if transition_mode else support_mask) | phase_after_usable),
            "candidate thermo support usability")

    # Pressure thermodynamics does not rewrite the other cloud reservoir.
    if transition_mode:
        require(
            np.all(
                ~support_mask
                | ~changed_bits(
                    replay["proposal_species"][2].astype(np.float32),
                    replay["post_species"][2].astype(np.float32),
                )
                | (surface == SATURATION_ICE)
            ),
            "liquid thermo must not change cloud ice",
        )
        require(
            np.all(
                ~support_mask
                | ~changed_bits(
                    replay["proposal_species"][1].astype(np.float32),
                    replay["post_species"][1].astype(np.float32),
                )
                | (surface == SATURATION_LIQUID)
            ),
            "ice thermo must not change cloud water",
        )
    else:
        require(
            np.all(~support_mask | ~changed_bits(background["cloud_ice"], candidate["cloud_ice"]) |
                   (surface == SATURATION_ICE)),
            "liquid thermo must not change cloud ice",
        )
        require(
            np.all(~support_mask | ~changed_bits(background["cloud_water"], candidate["cloud_water"]) |
                   (surface == SATURATION_LIQUID)),
            "ice thermo must not change cloud water",
        )

    precip_changed = np.zeros(shape, dtype=bool)
    for species in ("rain", "snow", "graupel"):
        precip_changed |= changed_bits(background[species], candidate[species])
        bg_meta = metadata["background"][species]
        cand_meta = metadata["candidate"][species]
        for suffix in ("valid", "quality", "source"):
            require(
                np.all(~radar_no_echo | (bg_meta[suffix] == cand_meta[suffix])),
                f"no-echo {species} {suffix} unchanged",
            )
    require(np.all(~radar_no_echo | ~precip_changed),
            "no-echo cells must not receive precipitation changes")

    def usable(prefix: str, species: str) -> np.ndarray:
        field_metadata = metadata[prefix][species]
        return (
            field_metadata["valid"].astype(bool)
            & (field_metadata["source"] > 0)
            & ((field_metadata["quality"] & QUALITY_EXCLUDED_BITS) == 0)
        )

    # The dry-air mass is a candidate-side quantity, but the pressure-fixed
    # measure is reconstructed from the pre-thermo mixture represented by the
    # background vapor/cloud fields and candidate precipitation fields.
    background_raw = np.stack(
        tuple(background[species] for species in THERMO_SPECIES), axis=0
    ).astype(np.float64)
    background_usable = np.stack(
        tuple(usable("background", species) for species in THERMO_SPECIES), axis=0
    )
    background_species = np.where(background_usable, background_raw, 0.0)
    proposal_raw = np.stack(
        (
            background["vapor"],
            background["cloud_water"],
            background["cloud_ice"],
            candidate["rain"],
            candidate["snow"],
            candidate["graupel"],
        ),
        axis=0,
    ).astype(np.float64)
    proposal_usable = np.stack(
        (
            usable("background", "vapor"),
            usable("background", "cloud_water"),
            usable("background", "cloud_ice"),
            usable("candidate", "rain"),
            usable("candidate", "snow"),
            usable("candidate", "graupel"),
        ),
        axis=0,
    )
    proposal_species = np.where(proposal_usable, proposal_raw, 0.0)
    if transition_mode:
        # Transition replay carries the original radar proposal and the
        # independently reconstructed post-thermo state.  Never derive the
        # thermo stage from final remapped precipitation.
        proposal_species = replay["proposal_species"].astype(np.float64)
        before = proposal_species
        after = replay["post_species"].astype(np.float64)
        thermo_temperature = replay["post_temperature"].astype(np.float64)
        thermo_mass = replay["post_mass"].astype(np.float64)
    else:
        before = proposal_species
        after = np.stack(tuple(candidate[name] for name in THERMO_SPECIES), axis=0).astype(np.float64)
        thermo_temperature = candidate["temperature"].astype(np.float64)
        thermo_mass = None
    final_candidate_species = np.stack(
        tuple(candidate[name] for name in THERMO_SPECIES), axis=0
    ).astype(np.float64)
    candidate_geometry_mass = (
        pressure_mass if candidate_pressure_mass is None else candidate_pressure_mass
    )
    if transition_mode:
        geometry_changed = np.any(candidate_geometry_mass != pressure_mass, axis=0)
        geometry_changed |= np.any(candidate_domain != above, axis=0)
        expected_mass = np.asarray(replay["post_mass"], dtype=np.float64).copy()
        refreshed_mass = np.divide(
            candidate_geometry_mass,
            1.0 + np.sum(np.where(
                np.stack(tuple(usable("candidate", name) for name in THERMO_SPECIES)),
                final_candidate_species, 0.0,
            ), axis=0),
            out=np.zeros_like(pressure_mass, dtype=np.float64),
            where=candidate_domain,
        )
        expected_mass = np.where(geometry_changed, refreshed_mass, expected_mass)
        expected_mass = np.where(candidate_domain, expected_mass, 0.0)
    else:
        expected_mass = np.divide(
            candidate_geometry_mass,
            1.0 + np.sum(before, axis=0),
            out=np.zeros_like(pressure_mass, dtype=np.float64),
            where=above,
        )
    if not transition_mode and candidate_pressure_mass is not None:
        # The thermo stage deliberately preserves its pre-thermo dry-mass
        # measure.  Geometry refreshes only columns whose stored float32 PSFC
        # changed; untouched columns are restored to that pre-thermo measure.
        # Changed columns use the final stored species, whose float32 phase
        # rounding may differ from the pre-thermo denominator.
        # A PS change refreshes the whole column, even where upper-cell dp
        # is unchanged but thermo storage rounded the species denominator.
        geometry_changed = np.any(candidate_geometry_mass != pressure_mass, axis=0)
        final_usable = np.stack(
            tuple(usable("candidate", species) for species in THERMO_SPECIES),
            axis=0,
        )
        final_species = np.where(final_usable, after, 0.0)
        refreshed_mass = np.divide(
            candidate_geometry_mass,
            1.0 + np.sum(final_species, axis=0),
            out=np.zeros_like(pressure_mass, dtype=np.float64),
            where=above,
        )
        expected_mass = np.where(geometry_changed, refreshed_mass, expected_mass)
    mass_tolerance = 128.0 * np.finfo(np.float64).eps * np.maximum(1.0, np.abs(expected_mass))
    require(np.all(np.abs(candidate_mass - expected_mass) <= mass_tolerance),
            "candidate dry-air mass identity")
    if transition_mode:
        # The independent remapper is the final-state oracle.  Compare final
        # storage only with that oracle; the post-thermo donor is intentionally
        # not a final T/q expectation.
        expected_temperature = replay["final_temperature"].astype(np.float32)
        expected_species = replay["final_species"].astype(np.float32)
        require(
            np.all(~candidate_domain
                   | (candidate["temperature"] == expected_temperature)),
            "independent transition final temperature reconstruction",
        )
        require(
            np.all(~candidate_domain[None, ...]
                   | (final_candidate_species.astype(np.float32) == expected_species)),
            "independent transition final species reconstruction",
        )
        final_mass_tolerance = 128.0 * np.finfo(np.float64).eps * np.maximum(
            1.0, np.abs(replay["final_mass"])
        )
        require(
            np.all(
                ~candidate_domain
                | (np.abs(candidate_mass - replay["final_mass"])
                <= final_mass_tolerance
                )
            ),
            "independent transition final dry-air mass reconstruction",
        )

    selected = support_mask
    # Reconstruct the thermo stage from its proposal, not from a final state
    # that a later pressure-domain remap may have mixed. The legacy path below
    # still uses final precipitation only because no remap is accepted here.
    from pressure_transition_reference import reconstruct_thermo_state_reference

    if not transition_mode:
        try:
            independent_temperature, independent_species, independent_mass = (
                reconstruct_thermo_state_reference(
                    np.broadcast_to(pressure[:, None, None], shape), pressure_mass,
                    background["temperature"], before, selected, surface, target_rh,
                )
            )
        except (ValueError, TypeError) as error:
            require(False, f"independent thermo reconstruction: {error}")
            return thermo_changed
        # Transition stages already came from this independent reconstruction.
        # Do not repeat it or compare the resulting state with itself.
        replay_epsilon = float(np.finfo(np.float32).eps)
        require(np.all(
            np.abs(candidate["temperature"][selected] - independent_temperature[selected])
            <= replay_epsilon * np.abs(independent_temperature[selected])
        ), "independent thermo temperature reconstruction")
        require(np.all(
            np.abs(after[:, selected] - independent_species[:, selected])
            <= 1.0e-11 + replay_epsilon * np.abs(independent_species[:, selected])
        ), "independent thermo species reconstruction")
        thermo_mass = independent_mass
    change = after - before
    initial_temperature = background["temperature"].astype(np.float64)
    candidate_temperature = thermo_temperature
    capacity = THERMO_CP_DRY + np.sum(THERMO_SPECIES_CP[:, None, None, None] * after, axis=0)
    sensible = capacity * (candidate_temperature - initial_temperature)
    phase_change = np.sum(
        change
        * (
            THERMO_SPECIES_H0[:, None, None, None]
            + THERMO_SPECIES_CP[:, None, None, None] * (initial_temperature - THERMO_T0)
        ),
        axis=0,
    )
    water_change = np.sum(change, axis=0)
    storage_epsilon = float(np.finfo(np.float32).eps)
    water_scale = np.sum(np.abs(before), axis=0)
    energy_scale = capacity * np.abs(initial_temperature) + np.sum(
        np.abs(before * (
            THERMO_SPECIES_H0[:, None, None, None]
            + THERMO_SPECIES_CP[:, None, None, None] * (initial_temperature - THERMO_T0)
        )),
        axis=0,
    )
    require(
        np.all(
            ~selected
            | (np.abs(water_change) <= 4.0 * storage_epsilon * water_scale)
        ),
        "thermo per-cell water closure",
    )
    require(
        np.all(
            ~selected
            | (np.abs(sensible + phase_change) <= 4.0 * storage_epsilon * energy_scale)
        ),
        "thermo per-cell enthalpy closure",
    )

    # Independent final saturation closure, including the exact empirical
    # liquid/ice vapor-pressure curves and reservoir-exhaustion rule.
    def saturation_mixing_ratio(temperature: np.ndarray, pressure_: np.ndarray, over_ice: np.ndarray) -> np.ndarray:
        tc = temperature - THERMO_T0
        liquid_es = 611.20 * np.exp(17.67 * tc / (tc + 243.5))
        ice_es = 611.15 * np.exp(22.452 * tc / (temperature - 0.55))
        es = np.where(over_ice, ice_es, liquid_es)
        es = np.minimum(0.99 * pressure_, np.maximum(0.0, es))
        return 0.622 * es / (pressure_ - es)

    if target_rh is not None:
        # Unselected cells may contain nonphysical placeholders (e.g. below
        # ground). They are outside this closure, not inputs to saturation.
        temperature = candidate_temperature[selected]
        selected_pressure = np.broadcast_to(pressure[:, None, None], selected.shape)[selected]
        vapor = after[0][selected]
        over_ice = surface[selected] == SATURATION_ICE
        temperature_error = storage_epsilon * np.abs(temperature)
        vapor_error = 1.0e-11 + storage_epsilon * np.abs(vapor)
        lower = target_rh * saturation_mixing_ratio(
            temperature - temperature_error, selected_pressure, over_ice
        )
        upper = target_rh * saturation_mixing_ratio(
            temperature + temperature_error, selected_pressure, over_ice
        )
        reservoir = np.where(over_ice, after[2][selected], after[1][selected])
        closed = (vapor <= upper + vapor_error) & (
            (reservoir == 0.0) | (vapor >= lower - vapor_error)
        )
        require(np.all(closed), "thermo final saturation closure")
        require(
            np.all(~over_ice | (temperature <= THERMO_T0)),
            "ice thermo temperature cap",
        )

    # Thermo is a stage before prescribed geometry is committed.  Its budget
    # therefore uses the pre-geometry dry-air measure, even though the
    # serialized candidate mass belongs to the final candidate geometry.
    validate_thermo_stage_budget(
        reported_budget, thermo_mass, initial_temperature, before,
        candidate_temperature, after, selected, require,
    )

    if schema7:
        analysis_selected = above
        accounted_cells = int(np.count_nonzero(analysis_selected))
        proposal_mass = np.divide(
            pressure_mass,
            1.0 + np.sum(proposal_species, axis=0),
            out=np.zeros_like(pressure_mass, dtype=np.float64),
            where=analysis_selected,
        )
        mb = dry_air_mass[analysis_selected].astype(np.float64)
        ma = proposal_mass[analysis_selected].astype(np.float64)
        rb = background_species[:, analysis_selected]
        ra = proposal_species[:, analysis_selected]
        dm = ma - mb
        species_terms = ma[None, :] * ra - mb[None, :] * rb
        expected_analysis_species = np.sum(species_terms, axis=1)
        expected_analysis_mixing = np.sum(mb[None, :] * (ra - rb), axis=1)
        expected_analysis_redistribution = np.sum(dm[None, :] * ra, axis=1)
        expected_analysis_dry = float(np.sum(dm))
        background_temperature_selected = initial_temperature[analysis_selected]

        def mixture_enthalpy(temperature: np.ndarray, species: np.ndarray) -> np.ndarray:
            return (
                THERMO_CP_DRY + np.sum(
                    THERMO_SPECIES_CP[:, None] * species, axis=0
                )
            ) * (temperature - THERMO_T0) + np.sum(
                THERMO_SPECIES_H0[:, None] * species, axis=0
            )

        background_enthalpy = mixture_enthalpy(
            background_temperature_selected, rb
        )
        proposal_enthalpy = mixture_enthalpy(
            background_temperature_selected, ra
        )
        enthalpy_terms = ma * proposal_enthalpy - mb * background_enthalpy
        expected_analysis_enthalpy = float(np.sum(enthalpy_terms))
        expected_analysis_total = expected_analysis_dry + float(
            np.sum(expected_analysis_species)
        )
        cell_mass_error = dm + np.sum(species_terms, axis=0)
        expected_analysis_max_cell = float(np.max(np.abs(cell_mass_error))) if accounted_cells else 0.0

        # The report is accumulated in Fortran loop order while these arrays
        # are reduced in NumPy order. Scale comparisons by the physical terms
        # that were actually subtracted, not by unrelated full-domain totals.
        accumulation_factor = 256.0 * np.finfo(np.float64).eps * max(1, accounted_cells)

        def analysis_matches(
            name: str,
            expected: np.ndarray | float,
            local_scale: np.ndarray | float,
            accumulation_scale: np.ndarray | float,
        ) -> bool:
            if name in ANALYSIS_VECTOR_ATTRIBUTES:
                actual = analysis_vectors[name]
            else:
                actual = analysis_scalars[name]
            if actual is None:
                return False
            expected_array = np.asarray(expected, dtype=np.float64)
            actual_array = np.asarray(actual, dtype=np.float64)
            local = np.asarray(local_scale, dtype=np.float64)
            accumulation = np.asarray(accumulation_scale, dtype=np.float64)
            tolerance = (
                256.0 * np.finfo(np.float64).eps * np.maximum(1.0, local)
                + accumulation_factor * np.maximum(1.0, accumulation)
            )
            return bool(np.all(np.abs(actual_array - expected_array) <= tolerance))

        species_local_scale = np.sum(
            np.abs(ma[None, :] * ra) + np.abs(mb[None, :] * rb), axis=1
        )
        species_accumulation_scale = np.sum(np.abs(species_terms), axis=1)
        mixing_local_scale = np.sum(
            np.abs(mb[None, :] * ra) + np.abs(mb[None, :] * rb), axis=1
        )
        mixing_accumulation_scale = np.sum(
            np.abs(mb[None, :] * (ra - rb)), axis=1
        )
        redistribution_local_scale = np.sum(
            (np.abs(ma) + np.abs(mb))[None, :] * np.abs(ra), axis=1
        )
        redistribution_accumulation_scale = np.sum(
            np.abs(dm[None, :] * ra), axis=1
        )
        dry_local_scale = float(np.sum(np.abs(ma) + np.abs(mb)))
        dry_accumulation_scale = float(np.sum(np.abs(dm)))
        enthalpy_local_scale = float(np.sum(
            np.abs(ma * proposal_enthalpy) + np.abs(mb * background_enthalpy)
        ))
        enthalpy_accumulation_scale = float(np.sum(np.abs(enthalpy_terms)))
        total_local_scale = dry_local_scale + float(np.sum(species_local_scale))
        total_accumulation_scale = dry_accumulation_scale + float(
            np.sum(species_accumulation_scale)
        )
        cell_scale = float(np.max(
            np.abs(ma) + np.abs(mb)
            + np.sum(np.abs(ma[None, :] * ra) + np.abs(mb[None, :] * rb), axis=0)
        )) if accounted_cells else 0.0
        require(
            analysis_matches(
                "analysis_species_change_kg", expected_analysis_species,
                species_local_scale, species_accumulation_scale,
            ),
            "analysis species budget",
        )
        require(
            analysis_matches(
                "analysis_mixing_ratio_change_kg", expected_analysis_mixing,
                mixing_local_scale, mixing_accumulation_scale,
            ),
            "analysis mixing-ratio budget",
        )
        require(
            analysis_matches(
                "analysis_dry_mass_redistribution_kg", expected_analysis_redistribution,
                redistribution_local_scale, redistribution_accumulation_scale,
            ),
            "analysis dry-mass redistribution budget",
        )
        require(
            analysis_matches(
                "analysis_dry_air_change_kg", expected_analysis_dry,
                dry_local_scale, dry_accumulation_scale,
            ),
            "analysis dry-air budget",
        )
        require(
            analysis_matches(
                "analysis_enthalpy_change_j", expected_analysis_enthalpy,
                enthalpy_local_scale, enthalpy_accumulation_scale,
            ),
            "analysis enthalpy budget",
        )
        require(
            analysis_matches(
                "analysis_total_mass_error_kg", expected_analysis_total,
                total_local_scale, total_accumulation_scale,
            ),
            "analysis total mass budget",
        )
        require(
            analysis_matches(
                "analysis_max_cell_mass_error_kg", expected_analysis_max_cell,
                cell_scale, 0.0,
            ),
            "analysis maximum cell mass budget",
        )
        require(
            np.all(np.isfinite(expected_analysis_species))
            and np.all(np.isfinite(expected_analysis_mixing))
            and np.all(np.isfinite(expected_analysis_redistribution))
            and np.isfinite(expected_analysis_dry)
            and np.isfinite(expected_analysis_enthalpy)
            and np.isfinite(expected_analysis_total)
            and np.isfinite(expected_analysis_max_cell),
            "analysis reconstructed terms finite",
        )

        background_valid = np.stack(
            tuple(metadata["background"][species]["valid"].astype(bool)
                  for species in THERMO_SPECIES),
            axis=0,
        )
        if transition_mode:
            # Analysis counters describe the original proposal, not the
            # pressure-remapped candidate precipitation.
            proposal_valid = replay["post_valid"]
        else:
            proposal_valid = np.stack(
                (
                    metadata["background"]["vapor"]["valid"].astype(bool),
                    metadata["background"]["cloud_water"]["valid"].astype(bool),
                    metadata["background"]["cloud_ice"]["valid"].astype(bool),
                    metadata["candidate"]["rain"]["valid"].astype(bool),
                    metadata["candidate"]["snow"]["valid"].astype(bool),
                    metadata["candidate"]["graupel"]["valid"].astype(bool),
                ),
                axis=0,
            )
        expected_incomplete_background = int(
            np.count_nonzero(analysis_selected & ~np.all(background_valid, axis=0))
        )
        expected_incomplete_candidate = int(
            np.count_nonzero(analysis_selected & ~np.all(proposal_valid, axis=0))
        )
        require(
            analysis_counts["analysis_accounted_cells"] == accounted_cells,
            "analysis accounted-cell count",
        )
        require(
            analysis_counts["analysis_incomplete_background_cells"] == expected_incomplete_background,
            "analysis incomplete-background count",
        )
        require(
            analysis_counts["analysis_incomplete_candidate_cells"] == expected_incomplete_candidate,
            "analysis incomplete-candidate count",
        )
        require(
            expected_analysis_total == expected_analysis_dry + float(np.sum(expected_analysis_species)),
            "analysis total mass decomposition",
        )
        require(
            np.allclose(
                expected_analysis_species,
                expected_analysis_mixing + expected_analysis_redistribution,
                rtol=0.0,
                atol=(4096.0 * np.finfo(np.float64).eps * max(1, accounted_cells)) * np.maximum(
                    1.0,
                    np.maximum(
                        np.abs(expected_analysis_species),
                        np.abs(expected_analysis_mixing)
                        + np.abs(expected_analysis_redistribution),
                    ),
                ),
            ),
            "analysis species decomposition",
        )

        # Combine the pre-thermo analysis ledger with the internal thermo
        # ledger against the final represented state. This is an identity
        # check, not a claim that the native model conserves these quantities.
        # A prescribed geometry stage has its own ledger and is checked after
        # this function; including it here would conflate the stage order.
        if variable_geometry:
            return thermo_changed
        final_usable = np.stack(
            tuple(usable("candidate", species) for species in THERMO_SPECIES), axis=0
        )
        final_species = np.where(final_usable, after, 0.0)
        background_above = background_species[:, analysis_selected]
        final_above = final_species[:, analysis_selected]
        final_mass = candidate_mass[analysis_selected]
        direct_species_change = np.sum(
            final_mass[None, :] * final_above - mb[None, :] * background_above,
            axis=1,
        )
        direct_water_scale = np.sum(
            np.abs(final_mass[None, :] * final_above)
            + np.abs(mb[None, :] * background_above),
            axis=1,
        )
        direct_water_accumulation_scale = np.sum(
            np.abs(final_mass[None, :] * final_above - mb[None, :] * background_above),
            axis=1,
        )
        direct_background_enthalpy = mixture_enthalpy(
            background_temperature_selected, background_above
        )
        direct_final_enthalpy = mixture_enthalpy(
            candidate_temperature[analysis_selected], final_above
        )
        direct_enthalpy_change = float(np.sum(
            final_mass * direct_final_enthalpy - mb * direct_background_enthalpy
        ))
        direct_enthalpy_scale = float(np.sum(
            np.abs(final_mass * direct_final_enthalpy)
            + np.abs(mb * direct_background_enthalpy)
        ))
        direct_enthalpy_accumulation_scale = float(np.sum(np.abs(
            final_mass * direct_final_enthalpy - mb * direct_background_enthalpy
        )))
        if analysis_vectors["analysis_species_change_kg"] is not None and reported_budget["species"] is not None:
            require(
                np.all(
                    np.abs(
                        analysis_vectors["analysis_species_change_kg"]
                        + np.asarray(reported_budget["species"], dtype=np.float64)
                        - direct_species_change
                    )
                    <= (
                        256.0 * np.finfo(np.float64).eps * np.maximum(1.0, direct_water_scale)
                        + accumulation_factor * np.maximum(1.0, direct_water_accumulation_scale)
                    )
                ),
                "analysis plus thermo water identity",
            )
        if analysis_scalars["analysis_enthalpy_change_j"] is not None and reported_budget["thermo_enthalpy_error_j"] is not None:
            require(
                abs(
                    analysis_scalars["analysis_enthalpy_change_j"]
                    + float(reported_budget["thermo_enthalpy_error_j"])
                    - direct_enthalpy_change
                )
                <= (
                    256.0 * np.finfo(np.float64).eps * max(1.0, direct_enthalpy_scale)
                    + accumulation_factor * max(1.0, direct_enthalpy_accumulation_scale)
                ),
                "analysis plus thermo enthalpy identity",
            )
    return thermo_changed


def pressure_geometry_budget(
    before_mass: np.ndarray,
    before_temperature: np.ndarray,
    before_species: np.ndarray,
    before_pressure_mass: np.ndarray,
    before_above: np.ndarray,
    after_mass: np.ndarray,
    after_temperature: np.ndarray,
    after_species: np.ndarray,
    after_pressure_mass: np.ndarray,
    after_above: np.ndarray,
) -> tuple[dict[str, np.ndarray | float], dict[str, np.ndarray | float]]:
    """Compute a geometry-stage ledger from two already validated states.

    Only the union of active cells participates. An absent side contributes
    no mass or species; a newly active cell is not pre-existing seed mass.
    Scales retain the units of each budget term (kg or reduced enthalpy J).
    """
    selected = before_above | after_above
    old = before_above[selected]
    new = after_above[selected]
    mb = np.where(old, before_mass[selected], 0.0).astype(np.float64)
    ma = np.where(new, after_mass[selected], 0.0).astype(np.float64)
    rb = np.where(old, before_species[:, selected], 0.0).astype(np.float64)
    ra = np.where(new, after_species[:, selected], 0.0).astype(np.float64)
    tb = np.where(old, before_temperature[selected], THERMO_T0).astype(np.float64)
    ta = np.where(new, after_temperature[selected], THERMO_T0).astype(np.float64)
    pb = np.where(old, before_pressure_mass[selected], 0.0).astype(np.float64)
    pa = np.where(new, after_pressure_mass[selected], 0.0).astype(np.float64)
    hb = ((THERMO_CP_DRY + THERMO_SPECIES_CP @ rb) * (tb - THERMO_T0)
          + THERMO_SPECIES_H0 @ rb)
    ha = ((THERMO_CP_DRY + THERMO_SPECIES_CP @ ra) * (ta - THERMO_T0)
          + THERMO_SPECIES_H0 @ ra)
    dm = ma - mb
    geometry = pa - pb
    species_terms = ma * ra - mb * rb
    species_change = np.sum(species_terms, axis=1)
    dry_change = float(np.sum(dm))
    cell_error = dm + np.sum(species_terms, axis=0) - geometry
    expected = {
        "species_change_kg": species_change,
        "mixing_ratio_change_kg": np.sum(mb * (ra - rb), axis=1),
        "dry_mass_redistribution_kg": np.sum(dm * ra, axis=1),
        "dry_air_change_kg": dry_change,
        "enthalpy_change_j": float(np.sum(ma * ha - mb * hb)),
        "geometry_mass_change_kg": float(np.sum(geometry)),
        "enthalpy_composition_change_j": float(np.sum(mb * (ha - hb))),
        "enthalpy_mass_metric_change_j": float(np.sum(dm * ha)),
        "total_mass_error_kg": dry_change + float(np.sum(species_change)) - float(np.sum(geometry)),
        "max_cell_mass_error_kg": float(np.max(np.abs(cell_error), initial=0.0)),
    }
    scales = {
        "species_change_kg": np.sum(np.abs(ma * ra) + np.abs(mb * rb), axis=1),
        "mixing_ratio_change_kg": np.sum(np.abs(mb * (ra - rb)), axis=1),
        "dry_mass_redistribution_kg": np.sum((np.abs(ma) + np.abs(mb)) * np.abs(ra), axis=1),
        "dry_air_change_kg": float(np.sum(np.abs(ma) + np.abs(mb))),
        "enthalpy_change_j": float(np.sum(np.abs(ma * ha) + np.abs(mb * hb))),
        "geometry_mass_change_kg": float(np.sum(np.abs(geometry))),
        "enthalpy_composition_change_j": float(np.sum(np.abs(mb * (ha - hb)))),
        "enthalpy_mass_metric_change_j": float(np.sum(np.abs(dm * ha))),
        "total_mass_error_kg": float(np.sum(np.abs(dm)) + np.sum(np.abs(species_terms))
                                     + np.sum(np.abs(geometry))),
        "max_cell_mass_error_kg": float(np.max(
            np.abs(dm) + np.sum(np.abs(species_terms), axis=0) + np.abs(geometry),
            initial=0.0,
        )),
    }
    return ({f"geometry_analysis_{name}": value for name, value in expected.items()},
            {f"geometry_analysis_{name}": value for name, value in scales.items()})


def validate_pressure_geometry_ledger(
    dataset: netCDF4.Dataset,
    above: np.ndarray,
    pressure_mass: np.ndarray,
    dry_air_mass: np.ndarray,
    candidate_pressure_mass: np.ndarray,
    candidate_dry_air_mass: np.ndarray,
    fields: dict[str, np.ndarray],
    require,
    *,
    transition_replay: dict[str, np.ndarray] | None = None,
) -> bool:
    """Replay the post-thermo prescribed-geometry mass/enthalpy ledger."""

    clean = True

    def check(condition: object, message: str) -> None:
        nonlocal clean
        passed = bool(condition)
        clean = clean and passed
        require(passed, message)

    def read_float_attribute(name: str, shape: tuple[int, ...]) -> np.ndarray | None:
        raw = getattr(dataset, name, None)
        if raw is None:
            check(False, f"{name} missing")
            return None
        parsed = np.asarray(raw)
        check(parsed.dtype == np.dtype(np.float64), f"{name} type")
        check(parsed.shape == shape, f"{name} shape")
        if parsed.dtype != np.dtype(np.float64) or parsed.shape != shape:
            return None
        result = np.ascontiguousarray(parsed, dtype=np.float64)
        check(np.all(np.isfinite(result)), f"{name} finite")
        return result

    def read_int_attribute(name: str) -> int | None:
        value = exact_scalar_int64(getattr(dataset, name, None))
        check(value is not None, f"{name} type")
        if value is not None:
            check(value >= 0, f"{name} nonnegative")
        return value

    reported_vectors = {
        name: read_float_attribute(name, (6,))
        for name in GEOMETRY_ANALYSIS_VECTOR_ATTRIBUTES
    }
    reported_scalars = {
        name: read_float_attribute(name, ())
        for name in GEOMETRY_ANALYSIS_FLOAT_ATTRIBUTES
    }
    reported_counts = {
        name: read_int_attribute(name)
        for name in GEOMETRY_ANALYSIS_COUNT_ATTRIBUTES
    }
    if not all(value is not None for value in (*reported_vectors.values(), *reported_scalars.values())):
        return False
    if not all(value is not None for value in reported_counts.values()):
        return False

    metadata: dict[str, dict[str, np.ndarray]] = {"background": {}, "candidate": {}}
    represented: dict[str, np.ndarray] = {}
    for prefix in ("background", "candidate"):
        for species in THERMO_SPECIES:
            value_name = f"{prefix}_{species}"
            value = fields.get(value_name)
            check(value is not None, f"{value_name} for geometry ledger")
            if value is None:
                return False
            represented[value_name] = value.astype(np.float64)
            for suffix in ("valid", "quality", "source"):
                name = f"{value_name}_{suffix}"
                if name not in dataset.variables:
                    check(False, f"{name} for geometry ledger")
                    return False
                metadata[prefix][name] = values(dataset[name]).astype(np.int64)

    def usable(prefix: str, species: str) -> np.ndarray:
        base = f"{prefix}_{species}"
        valid = metadata[prefix][f"{base}_valid"].astype(bool)
        quality = metadata[prefix][f"{base}_quality"]
        source = metadata[prefix][f"{base}_source"]
        return valid & (source > 0) & ((quality & QUALITY_EXCLUDED_BITS) == 0)

    background_species = np.stack(
        tuple(represented[f"background_{species}"] for species in THERMO_SPECIES),
        axis=0,
    )
    candidate_species = np.stack(
        tuple(represented[f"candidate_{species}"] for species in THERMO_SPECIES),
        axis=0,
    )
    for prefix, species_values in (
        ("background", background_species),
        ("candidate", candidate_species),
    ):
        for index, species in enumerate(THERMO_SPECIES):
            if species == "vapor":
                # represented_water_species always retains vapor after the
                # canonical field checks; its metadata is still counted below.
                continue
            species_values[index] = np.where(
                usable(prefix, species), species_values[index], 0.0
            )
    # The thermo stage keeps the pre-thermo dry-air measure while its phase
    # fields are rounded/stored.  Geometry therefore starts from the dry mass
    # implied by the original pressure metric and the pre-thermo proposal
    # mixture (background phase fields plus candidate precipitation).
    proposal_species = np.stack(
        (
            np.where(
                usable("background", "vapor"),
                represented["background_vapor"],
                0.0,
            ),
            np.where(
                usable("background", "cloud_water"),
                represented["background_cloud_water"],
                0.0,
            ),
            np.where(
                usable("background", "cloud_ice"),
                represented["background_cloud_ice"],
                0.0,
            ),
            np.where(usable("candidate", "rain"), represented["candidate_rain"], 0.0),
            np.where(usable("candidate", "snow"), represented["candidate_snow"], 0.0),
            np.where(
                usable("candidate", "graupel"),
                represented["candidate_graupel"],
                0.0,
            ),
        ),
        axis=0,
    )

    selected = above.astype(bool)
    candidate_above = selected
    candidate_valid = np.stack(tuple(
        metadata["candidate"][f"candidate_{species}_valid"].astype(bool)
        for species in THERMO_SPECIES
    ))
    before_valid = candidate_valid
    pregeometry_temperature = fields["candidate_temperature"]
    pregeometry_species = candidate_species
    if transition_replay is not None:
        proposal_species = transition_replay["proposal_species"]
        pregeometry_temperature = transition_replay["post_temperature"]
        pregeometry_species = transition_replay["post_species"]
        before_valid = transition_replay["post_valid"]
        candidate_above = transition_replay["candidate_above_ground"]
    pregeometry_mass = np.divide(
        pressure_mass,
        1.0 + np.sum(proposal_species, axis=0),
        out=np.zeros_like(pressure_mass, dtype=np.float64),
        where=selected,
    )
    if transition_replay is not None:
        pregeometry_mass = transition_replay["post_mass"]
    final_mass = candidate_dry_air_mass.astype(np.float64)
    # Ordinary geometry preserves T/species; transitions use the independently
    # replayed post-thermo state, never the final remapped state as the donor.
    expected_values, scales = pressure_geometry_budget(
        pregeometry_mass, pregeometry_temperature, pregeometry_species,
        pressure_mass, selected,
        final_mass, fields["candidate_temperature"], candidate_species,
        candidate_pressure_mass, candidate_above,
    )
    union = selected | candidate_above

    expected_counts = {
        "geometry_analysis_accounted_cells": int(np.count_nonzero(union)),
        "geometry_analysis_incomplete_background_cells": int(
            np.count_nonzero(selected & ~np.all(before_valid, axis=0))
        ),
        "geometry_analysis_incomplete_candidate_cells": int(
            np.count_nonzero(candidate_above & ~np.all(candidate_valid, axis=0))
        ),
    }
    accumulation_factor = 256.0 * np.finfo(np.float64).eps * max(
        1, int(np.count_nonzero(union))
    )

    def matches(name: str, expected: np.ndarray | float, scale: np.ndarray | float) -> bool:
        actual = reported_vectors[name] if name in reported_vectors else reported_scalars[name]
        expected_array = np.asarray(expected, dtype=np.float64)
        actual_array = np.asarray(actual, dtype=np.float64)
        local_scale = np.asarray(scale, dtype=np.float64)
        accumulation_scale = np.asarray(expected, dtype=np.float64)
        tolerance = (
            256.0 * np.finfo(np.float64).eps * np.maximum(1.0, local_scale)
            + accumulation_factor * np.maximum(1.0, np.abs(accumulation_scale))
        )
        return bool(np.all(np.abs(actual_array - expected_array) <= tolerance))

    for name, expected in expected_values.items():
        check(matches(name, expected, scales[name]), f"{name} ledger")
    for name, expected in expected_counts.items():
        check(reported_counts[name] == expected, f"{name} count")
    if transition_replay is not None:
        check(expected_counts["geometry_analysis_incomplete_background_cells"] == 0
              and expected_counts["geometry_analysis_incomplete_candidate_cells"] == 0,
              "pressure transition geometry species coverage")

    # Independently preserve the stage order: background -> analysis -> thermo
    # -> prescribed geometry.  This catches a forged but internally consistent
    # geometry ledger that does not agree with the serialized six-species state.
    background_usable = np.stack(
        tuple(
            usable("background", species)
            if species != "vapor"
            else np.ones_like(above, dtype=bool)
            for species in THERMO_SPECIES
        ),
        axis=0,
    )
    proposal_species = np.stack(
        (
            represented["background_vapor"],
            np.where(usable("background", "cloud_water"), represented["background_cloud_water"], 0.0),
            np.where(usable("background", "cloud_ice"), represented["background_cloud_ice"], 0.0),
            np.where(usable("candidate", "rain"), represented["candidate_rain"], 0.0),
            np.where(usable("candidate", "snow"), represented["candidate_snow"], 0.0),
            np.where(usable("candidate", "graupel"), represented["candidate_graupel"], 0.0),
        ),
        axis=0,
    )
    background_species = np.where(background_usable, background_species, 0.0)
    if transition_replay is not None:
        proposal_species = transition_replay["proposal_species"]
    analysis_mass = np.divide(
        pressure_mass,
        1.0 + np.sum(proposal_species, axis=0),
        out=np.zeros_like(pressure_mass, dtype=np.float64),
        where=selected,
    )
    analysis_change = np.sum(
        (
            analysis_mass[None, ...] * np.where(selected, proposal_species, 0.0)
            - np.where(selected, dry_air_mass, 0.0)[None, ...]
            * np.where(selected, background_species, 0.0)
        ),
        axis=(1, 2, 3),
    )
    thermo_budget = np.asarray(getattr(dataset, "thermo_species_change_kg"), dtype=np.float64)
    geometry_budget = np.asarray(reported_vectors["geometry_analysis_species_change_kg"], dtype=np.float64)
    direct_change = np.sum(
        (
            np.where(candidate_above, final_mass, 0.0)[None, ...]
            * np.where(candidate_above, candidate_species, 0.0)
            - np.where(selected, dry_air_mass, 0.0)[None, ...]
            * np.where(selected, background_species, 0.0)
        ),
        axis=(1, 2, 3),
    )
    check(
        np.allclose(
            analysis_change + thermo_budget + geometry_budget,
            direct_change,
            rtol=0.0,
            atol=256.0 * np.finfo(np.float64).eps * max(1, int(np.count_nonzero(union)))
            * np.maximum(1.0, np.abs(direct_change)),
        ),
        "analysis plus thermo plus geometry species identity",
    )
    return bool(clean)


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
    omega_authorized: np.ndarray | None = None,
) -> np.ndarray:
    """Independent finite-volume D*S using the persisted pressure geometry."""
    residual = np.zeros(du.shape, dtype=np.float64)
    volume = dx * dy * cell_dp
    if not np.any(active):
        return residual
    horizontal_u_active = active.copy()
    horizontal_v_active = active.copy()
    horizontal_u_active[:, :, 0] = False
    horizontal_u_active[:, :, -1] = False
    horizontal_v_active[:, 0, :] = False
    horizontal_v_active[:, -1, :] = False
    if active.shape[2] > 2:
        horizontal_u_active[:, :, 1:-1] &= active[:, :, :-2] & active[:, :, 2:]
    if active.shape[1] > 2:
        horizontal_v_active[:, 1:-1, :] &= active[:, :-2, :] & active[:, 2:, :]

    # Horizontal pressure faces are conservative overlaps, not same-level
    # averages. A prescribed surface pressure can move a neighboring
    # column's interface across a center, creating cross-level segments.
    for j in range(du.shape[1]):
        for i in range(du.shape[2] - 1):
            for left_level, right_level, thickness in _pressure_overlap_segments(
                pressure_interface[:, j, i], pressure_interface[:, j, i + 1]
            ):
                if not (
                    active[left_level, j, i]
                    and active[right_level, j, i + 1]
                    and (
                        horizontal_u_active[left_level, j, i]
                        or horizontal_u_active[right_level, j, i + 1]
                    )
                ):
                    continue
                flux = dy * thickness * 0.5 * (
                    du[left_level, j, i] + du[right_level, j, i + 1]
                )
                residual[left_level, j, i] += flux / volume[left_level, j, i]
                residual[right_level, j, i + 1] -= flux / volume[right_level, j, i + 1]

    for j in range(du.shape[1] - 1):
        for i in range(du.shape[2]):
            for left_level, right_level, thickness in _pressure_overlap_segments(
                pressure_interface[:, j, i], pressure_interface[:, j + 1, i]
            ):
                if not (
                    active[left_level, j, i]
                    and active[right_level, j + 1, i]
                    and (
                        horizontal_v_active[left_level, j, i]
                        or horizontal_v_active[right_level, j + 1, i]
                    )
                ):
                    continue
                flux = dx * thickness * 0.5 * (
                    dv[left_level, j, i] + dv[right_level, j + 1, i]
                )
                residual[left_level, j, i] += flux / volume[left_level, j, i]
                residual[right_level, j + 1, i] -= flux / volume[right_level, j + 1, i]

    pface = active[:-1, :, :] & active[1:, :, :]
    if omega_authorized is not None:
        pface &= omega_authorized[:-1, :, :] | omega_authorized[1:, :, :]
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
    if not np.any(active):
        return residual

    for j in range(u.shape[1]):
        for i in range(u.shape[2] - 1):
            for left_level, right_level, thickness in _pressure_overlap_segments(
                pressure_interface[:, j, i], pressure_interface[:, j, i + 1]
            ):
                if not (
                    above_ground[left_level, j, i]
                    and above_ground[right_level, j, i + 1]
                ):
                    continue
                flux = dy * thickness * 0.5 * (
                    u[left_level, j, i] + u[right_level, j, i + 1]
                )
                if active[left_level, j, i]:
                    residual[left_level, j, i] += flux / volume[left_level, j, i]
                if active[right_level, j, i + 1]:
                    residual[right_level, j, i + 1] -= flux / volume[right_level, j, i + 1]
    residual[:, :, 0] -= np.where(active[:, :, 0], u[:, :, 0] / dx, 0.0)
    residual[:, :, -1] += np.where(active[:, :, -1], u[:, :, -1] / dx, 0.0)

    for j in range(v.shape[1] - 1):
        for i in range(v.shape[2]):
            for left_level, right_level, thickness in _pressure_overlap_segments(
                pressure_interface[:, j, i], pressure_interface[:, j + 1, i]
            ):
                if not (
                    above_ground[left_level, j, i]
                    and above_ground[right_level, j + 1, i]
                ):
                    continue
                flux = dx * thickness * 0.5 * (
                    v[left_level, j, i] + v[right_level, j + 1, i]
                )
                if active[left_level, j, i]:
                    residual[left_level, j, i] += flux / volume[left_level, j, i]
                if active[right_level, j + 1, i]:
                    residual[right_level, j + 1, i] -= flux / volume[right_level, j + 1, i]
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


def _pressure_overlap_segments(
    left_interface: np.ndarray,
    right_interface: np.ndarray,
) -> list[tuple[int, int, float]]:
    """Return conserved pressure-overlap segments for one lateral face."""
    overlap = np.minimum(
        left_interface[:-1, None], right_interface[None, :-1]
    ) - np.maximum(
        left_interface[1:, None], right_interface[None, 1:]
    )
    return [
        (int(left_level), int(right_level), float(overlap[left_level, right_level]))
        for left_level, right_level in np.argwhere(overlap > 0.0)
    ]


def dry_air_flux_divergence(
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
    dry_air_mass: np.ndarray,
    pressure_mass: np.ndarray,
    *,
    return_roundoff: bool = False,
) -> np.ndarray | tuple[np.ndarray, np.ndarray]:
    """Independently recompute signed net dry-air flux divergence in kg/s.

    Horizontal faces use conserved dry-air fraction times velocity on each
    side of every pressure-overlap segment.  Vertical faces use the persisted
    pressure-center interpolation weights.  Domain boundaries use the
    nearest interior composition; top and bottom faces use the persisted
    omega boundary values.  ``active`` is the candidate balance support, so
    fluxes crossing its edge are retained only on active cells.
    """
    shape = np.asarray(pressure_mass).shape
    if len(shape) != 3:
        raise ValueError("dry-air flux fields must be three-dimensional")
    for name, array in (
        ("u", u),
        ("v", v),
        ("omega", omega),
        ("active", active),
        ("above_ground", above_ground),
        ("cell_dp", cell_dp),
        ("dry_air_mass", dry_air_mass),
    ):
        if np.asarray(array).shape != shape:
            raise ValueError(f"{name} shape")
    if np.asarray(pressure_interface).shape != (shape[0] + 1, shape[1], shape[2]):
        raise ValueError("pressure interface shape")
    if np.asarray(pressure).shape != (shape[0],):
        raise ValueError("pressure shape")
    if np.asarray(omega_top_boundary).shape != shape[1:] or np.asarray(
        omega_bottom_boundary
    ).shape != shape[1:]:
        raise ValueError("omega boundary shape")
    if not np.isfinite(dx) or not np.isfinite(dy) or dx <= 0.0 or dy <= 0.0:
        raise ValueError("grid spacing")

    dry_air_mass = np.asarray(dry_air_mass, dtype=np.float64)
    pressure_mass = np.asarray(pressure_mass, dtype=np.float64)
    u = np.asarray(u, dtype=np.float64)
    v = np.asarray(v, dtype=np.float64)
    omega = np.asarray(omega, dtype=np.float64)
    above_ground = np.asarray(above_ground, dtype=bool)
    active = np.asarray(active, dtype=bool)
    pressure = np.asarray(pressure, dtype=np.float64)
    pressure_interface = np.asarray(pressure_interface, dtype=np.float64)
    omega_top_boundary = np.asarray(omega_top_boundary, dtype=np.float64)
    omega_bottom_boundary = np.asarray(omega_bottom_boundary, dtype=np.float64)

    fraction = np.zeros(shape, dtype=np.float64)
    np.divide(
        dry_air_mass,
        pressure_mass,
        out=fraction,
        where=above_ground & (pressure_mass > 0.0),
    )
    divergence = np.zeros(shape, dtype=np.float64)
    donor_magnitude = np.zeros(shape, dtype=np.float64)
    face_count = np.zeros(shape, dtype=np.int32)

    def add_face(index, flux, magnitude):
        selected = active[index]
        divergence[index] += np.where(selected, flux, 0.0)
        donor_magnitude[index] += np.where(selected, magnitude, 0.0)
        face_count[index] += selected

    gravity = 9.80665

    # Pressure-overlap faces are essential when neighboring columns have
    # different terrain clipping.  A simple same-level average is not
    # conservative on those partial faces.
    for j in range(shape[1]):
        for i in range(shape[2] - 1):
            segments = _pressure_overlap_segments(
                pressure_interface[:, j, i], pressure_interface[:, j, i + 1]
            )
            for left_level, right_level, thickness in segments:
                if not (
                    above_ground[left_level, j, i]
                    and above_ground[right_level, j, i + 1]
                ):
                    continue
                area = 0.5 * (dy + dy) * thickness / gravity
                flux = area * 0.5 * (
                    u[left_level, j, i] * fraction[left_level, j, i]
                    + u[right_level, j, i + 1] * fraction[right_level, j, i + 1]
                )
                magnitude = area * 0.5 * (
                    abs(u[left_level, j, i] * fraction[left_level, j, i])
                    + abs(u[right_level, j, i + 1] * fraction[right_level, j, i + 1])
                )
                add_face((left_level, j, i), flux, magnitude)
                add_face((right_level, j, i + 1), -flux, magnitude)

    for j in range(shape[1] - 1):
        for i in range(shape[2]):
            segments = _pressure_overlap_segments(
                pressure_interface[:, j, i], pressure_interface[:, j + 1, i]
            )
            for left_level, right_level, thickness in segments:
                if not (
                    above_ground[left_level, j, i]
                    and above_ground[right_level, j + 1, i]
                ):
                    continue
                area = 0.5 * (dx + dx) * thickness / gravity
                flux = area * 0.5 * (
                    v[left_level, j, i] * fraction[left_level, j, i]
                    + v[right_level, j + 1, i] * fraction[right_level, j + 1, i]
                )
                magnitude = area * 0.5 * (
                    abs(v[left_level, j, i] * fraction[left_level, j, i])
                    + abs(v[right_level, j + 1, i] * fraction[right_level, j + 1, i])
                )
                add_face((left_level, j, i), flux, magnitude)
                add_face((right_level, j + 1, i), -flux, magnitude)

    # Vertical faces use the same pressure-center interpolation as the
    # production operator, applied to fraction*omega on each side.
    for k in range(shape[0] - 1):
        denominator = pressure[k] - pressure[k + 1]
        weight_left = (
            pressure_interface[k + 1] - pressure[k + 1]
        ) / denominator
        weight_right = 1.0 - weight_left
        face = above_ground[k] & above_ground[k + 1]
        flux = np.where(
            face,
            dx * dy / gravity
            * (
                weight_left[:, :] * omega[k] * fraction[k]
                + weight_right[:, :] * omega[k + 1] * fraction[k + 1]
            ),
            0.0,
        )
        magnitude = np.where(face, dx * dy / gravity * (
            np.abs(weight_left * omega[k] * fraction[k])
            + np.abs(weight_right * omega[k + 1] * fraction[k + 1])
        ), 0.0)
        add_face(k, -flux, magnitude)
        add_face(k + 1, flux, magnitude)

    cell_dp = np.asarray(cell_dp, dtype=np.float64)
    for index, width, velocity, sign in (
        ((slice(None), slice(None), 0), dy, u, -1.0),
        ((slice(None), slice(None), -1), dy, u, 1.0),
        ((slice(None), 0, slice(None)), dx, v, -1.0),
        ((slice(None), -1, slice(None)), dx, v, 1.0),
    ):
        flux = width * cell_dp[index] / gravity * velocity[index] * fraction[index]
        add_face(index, sign * flux, np.abs(flux))

    for j in range(shape[1]):
        for i in range(shape[2]):
            levels = np.flatnonzero(above_ground[:, j, i])
            if levels.size == 0:
                continue
            bottom = int(levels[0])
            top = int(levels[-1])
            boundary_area = dx * dy / gravity
            if active[top, j, i]:
                flux = (
                    boundary_area
                    * omega_top_boundary[j, i]
                    * fraction[top, j, i]
                )
                add_face((top, j, i), -flux, abs(flux))
            if active[bottom, j, i]:
                flux = (
                    boundary_area
                    * omega_bottom_boundary[j, i]
                    * fraction[bottom, j, i]
                )
                add_face((bottom, j, i), flux, abs(flux))
    divergence[~active] = 0.0
    if return_roundoff:
        # Each path forms a face (area, weights, dry fraction, products),
        # sums n terms, and Fortran additionally divides/multiplies by cell
        # mass. Ten operations cover face construction and normalization;
        # two gamma bounds cover the independently ordered float64 paths.
        # Use absolute DONOR terms, before either face or cell cancellation.
        unit_roundoff = np.finfo(np.float64).eps / 2.0
        gamma_n = (face_count + 10) * unit_roundoff
        bound = 2.0 * gamma_n / (1.0 - gamma_n) * donor_magnitude
        return divergence, bound
    return divergence


def read_dry_air_flux_extension(
    dataset: netCDF4.Dataset,
    shape: tuple[int, ...],
    pressure_candidate: bool,
    pressure_schema: bool,
    pressure_geometry: bool,
    require,
) -> tuple[bool, bool, dict[str, np.ndarray]]:
    """Read the optional pressure-candidate dry-air flux extension."""
    reserved_attributes = {
        name
        for name in dataset.ncattrs()
        if name.startswith("dry_air_flux_")
        or name == "dry_air_mass_tendency_assessed"
    }
    reserved_variables = {
        name
        for name in dataset.variables
        if name.startswith("background_dry_air_flux")
        or name.startswith("candidate_dry_air_flux")
    }
    present = bool(reserved_attributes or reserved_variables)
    if not present:
        return False, False, {}

    supported = pressure_candidate and pressure_schema
    require(supported, "dry-air flux extension context")
    complete = (
        set(DRY_AIR_FLUX_ATTRIBUTES) <= set(dataset.ncattrs())
        and set(DRY_AIR_FLUX_VARIABLES) <= set(dataset.variables)
    )
    require(complete, "complete dry-air flux extension")
    if not supported or not complete:
        return True, False, {}

    expected_contract = (
        DRY_AIR_FLUX_CONTRACT_STATE
        if pressure_geometry
        else DRY_AIR_FLUX_CONTRACT_FIXED
    )
    require(
        getattr(dataset, "dry_air_flux_contract", "") == expected_contract,
        "dry-air flux contract",
    )
    require(
        getattr(dataset, "dry_air_flux_boundary", "") == DRY_AIR_FLUX_BOUNDARY,
        "dry-air flux boundary",
    )
    tendency_assessed = exact_scalar_int32(
        getattr(dataset, "dry_air_mass_tendency_assessed", None)
    )
    require(tendency_assessed == 0, "dry-air mass tendency assessed")

    fluxes: dict[str, np.ndarray] = {}
    for name in DRY_AIR_FLUX_VARIABLES:
        variable = dataset.variables[name]
        require(variable.dimensions == ("z", "y", "x"), f"{name} dimensions")
        require(np.dtype(variable.dtype) == np.dtype(np.float64), f"{name} type")
        require(getattr(variable, "units", "") == "kg s-1", f"{name} units")
        require(
            "scale_factor" not in variable.ncattrs()
            and "add_offset" not in variable.ncattrs(),
            f"{name} must not be packed",
        )
        require("valid_time" not in variable.ncattrs(), f"{name} valid time metadata")
        array = values(variable)
        require(array.dtype == np.dtype(np.float64), f"{name} unpacked type")
        require(array.shape == shape, f"{name} shape")
        require(np.all(np.isfinite(array)), f"{name} finite")
        fluxes[name] = array

    clean = (
        supported
        and complete
        and getattr(dataset, "dry_air_flux_contract", "") == expected_contract
        and getattr(dataset, "dry_air_flux_boundary", "") == DRY_AIR_FLUX_BOUNDARY
        and tendency_assessed == 0
        and all(
            variable.dimensions == ("z", "y", "x")
            and np.dtype(variable.dtype) == np.dtype(np.float64)
            and getattr(variable, "units", "") == "kg s-1"
            and "scale_factor" not in variable.ncattrs()
            and "add_offset" not in variable.ncattrs()
            and "valid_time" not in variable.ncattrs()
            and fluxes[name].dtype == np.dtype(np.float64)
            and fluxes[name].shape == shape
            and np.all(np.isfinite(fluxes[name]))
            for name, variable in (
                (name, dataset.variables[name]) for name in DRY_AIR_FLUX_VARIABLES
            )
        )
    )
    return True, bool(clean), fluxes


def validate_pressure_geopotential_extension(
    dataset: netCDF4.Dataset,
    shape: tuple[int, ...],
    above: np.ndarray,
    pressure: np.ndarray,
    pressure_candidate: bool,
    schema_version: int,
    valid_time_epoch: int | None,
    canonical_schema_version: int | None,
    surface_boundary_present: bool,
    surface_boundary_clean: bool,
    surface_boundary_inputs: dict[str, np.ndarray],
    require,
    *,
    transition_replay: dict[str, np.ndarray] | None = None,
    transition_inputs: dict[str, np.ndarray] | None = None,
) -> tuple[bool, bool, np.ndarray]:
    """Replay the optional pressure-candidate hydrostatic Phi increment.

    The original contract anchors the lowest represented pressure center.  The
    surface variant uses canonical-schema-5 pressure/temperature/vapor and a
    fixed terrain surface anchor on every selected column.  Neither variant
    asserts native geopotential or total-energy closure.
    """

    transition_mode = transition_replay is not None or transition_inputs is not None
    if transition_mode and (transition_replay is None or transition_inputs is None):
        require(False, "pressure transition replay inputs pair")
        return True, False, np.zeros(shape, dtype=bool)

    reserved_attributes = {
        name
        for name in dataset.ncattrs()
        if name.startswith("pressure_geopotential")
    }
    reserved_variables = {
        name
        for name in dataset.variables
        if name.startswith((
            "background_geopotential",
            "candidate_geopotential",
            "geopotential_support",
            "geopotential_reference_level",
        ))
    }
    present = bool(reserved_attributes or reserved_variables)
    if not present:
        return False, False, np.zeros(shape, dtype=bool)

    clean = True

    def check(condition: bool, message: str) -> None:
        nonlocal clean
        if not condition:
            clean = False
        require(condition, message)

    contract = getattr(dataset, "pressure_geopotential_contract", "")
    reference_name = getattr(dataset, "pressure_geopotential_reference", "")
    surface_variant = (
        contract == PRESSURE_GEOPOTENTIAL_SURFACE_CONTRACT
        or reference_name == PRESSURE_GEOPOTENTIAL_SURFACE_REFERENCE
        or PRESSURE_GEOPOTENTIAL_SURFACE_CONDENSATE_ATTRIBUTE in reserved_attributes
    )
    known_attributes = set(PRESSURE_GEOPOTENTIAL_ATTRIBUTES) | set(
        PRESSURE_GEOPOTENTIAL_SURFACE_ATTRIBUTES
    )
    expected_attributes = (
        set(PRESSURE_GEOPOTENTIAL_SURFACE_ATTRIBUTES)
        if surface_variant
        else set(PRESSURE_GEOPOTENTIAL_ATTRIBUTES)
    )
    supported = pressure_candidate and schema_version in (7, 8)
    check(supported, "pressure geopotential extension context")
    check(
        reserved_attributes <= known_attributes,
        "known pressure geopotential attributes",
    )
    check(
        reserved_variables <= set(PRESSURE_GEOPOTENTIAL_VARIABLES),
        "known pressure geopotential variables",
    )
    complete = (
        expected_attributes <= set(dataset.ncattrs())
        and set(PRESSURE_GEOPOTENTIAL_VARIABLES) <= set(dataset.variables)
    )
    check(complete, "complete pressure geopotential extension")
    if surface_variant:
        check(
            canonical_schema_version == 5,
            "surface pressure geopotential requires canonical schema 5",
        )
        check(
            surface_boundary_present and surface_boundary_clean,
            "surface pressure geopotential requires clean surface boundary",
        )
    else:
        check(
            PRESSURE_GEOPOTENTIAL_SURFACE_CONDENSATE_ATTRIBUTE
            not in reserved_attributes,
            "center pressure geopotential has no surface convention",
        )
    if transition_mode:
        check(surface_variant, "pressure transition requires surface geopotential contract")
    if not supported or not complete:
        return True, False, np.zeros(shape, dtype=bool)

    check(
        contract
        == (PRESSURE_GEOPOTENTIAL_SURFACE_CONTRACT
            if surface_variant else PRESSURE_GEOPOTENTIAL_CONTRACT),
        "pressure geopotential contract",
    )
    check(
        reference_name
        == (PRESSURE_GEOPOTENTIAL_SURFACE_REFERENCE
            if surface_variant else PRESSURE_GEOPOTENTIAL_REFERENCE),
        "pressure geopotential reference",
    )
    if surface_variant:
        check(
            getattr(dataset, PRESSURE_GEOPOTENTIAL_SURFACE_CONDENSATE_ATTRIBUTE, "")
            == PRESSURE_GEOPOTENTIAL_SURFACE_CONDENSATE,
            "surface condensate convention",
        )
    native_assessed = exact_scalar_int32(
        getattr(dataset, "pressure_geopotential_native_assessed", None)
    )
    check(native_assessed == 0, "pressure geopotential native assessed")

    def read_variable(name: str, expected_dtype: np.dtype, dimensions: tuple[str, ...],
                      units: str, value_time: bool = False) -> np.ndarray:
        variable = dataset.variables[name]
        check(variable.dimensions == dimensions, f"{name} dimensions")
        check(np.dtype(variable.dtype) == expected_dtype, f"{name} type")
        check(getattr(variable, "units", "") == units, f"{name} units")
        check(
            "scale_factor" not in variable.ncattrs()
            and "add_offset" not in variable.ncattrs(),
            f"{name} must not be packed",
        )
        if value_time:
            field_time = exact_scalar_int64(getattr(variable, "valid_time", None))
            check(field_time is not None, f"{name} valid time")
            if valid_time_epoch is not None and field_time is not None:
                check(field_time == valid_time_epoch, f"{name} valid time identity")
        else:
            check("valid_time" not in variable.ncattrs(), f"{name} valid time metadata")
        array = values(variable)
        check(array.dtype == expected_dtype, f"{name} unpacked type")
        check(array.shape == shape if dimensions == ("z", "y", "x") else
              array.shape == shape[1:], f"{name} shape")
        return array

    geopotential: dict[str, np.ndarray] = {}
    geopotential_metadata: dict[str, dict[str, np.ndarray]] = {
        "background": {},
        "candidate": {},
    }
    for prefix in ("background", "candidate"):
        value_name = f"{prefix}_geopotential"
        geopotential[prefix] = read_variable(
            value_name, np.dtype(np.float32), ("z", "y", "x"),
            PRESSURE_GEOPOTENTIAL_VALUE_UNITS, value_time=True,
        )
        if not clean:
            return True, False, np.zeros(shape, dtype=bool)
        for suffix in ("valid", "quality", "source"):
            name = f"{value_name}_{suffix}"
            array = read_variable(name, np.dtype(np.int32), ("z", "y", "x"), "1")
            if not clean:
                return True, False, np.zeros(shape, dtype=bool)
            geopotential_metadata[prefix][suffix] = array.astype(np.int64)

    support = read_variable(
        "geopotential_support", np.dtype(np.int32), ("z", "y", "x"), "1"
    )
    reference_level = read_variable(
        "geopotential_reference_level", np.dtype(np.int32), ("y", "x"), "1"
    )
    reference_variable = dataset.variables["geopotential_reference_level"]
    check(exact_scalar_int32(getattr(reference_variable, "index_base", None)) == 1,
          "geopotential reference index base")
    check(exact_scalar_int32(getattr(reference_variable, "inactive_value", None)) == 0,
          "geopotential reference inactive value")
    check(
        getattr(reference_variable, "semantics", "")
        == (PRESSURE_GEOPOTENTIAL_SURFACE_REFERENCE
            if surface_variant else PRESSURE_GEOPOTENTIAL_REFERENCE),
          "geopotential reference semantics")
    if not clean:
        return True, False, np.zeros(shape, dtype=bool)
    check(np.all((support == 0) | (support == 1)), "geopotential support binary")
    check(np.all(reference_level >= 0), "geopotential reference nonnegative")
    selected = support.astype(bool)
    selected_columns = np.any(selected, axis=0)
    check(np.any(selected), "geopotential support nonempty")
    selected_domain = above & selected_columns[None, :, :]
    candidate_domain = above
    final_domain = candidate_domain & selected_columns[None, :, :]
    replay: dict[str, np.ndarray] = {}
    transition_seed: dict[str, np.ndarray] = {}
    if transition_mode:
        expected_replay_shapes = {
            "post_temperature": shape,
            "post_species": (6, *shape),
            "candidate_above_ground": shape,
            "final_temperature": shape,
            "final_species": (6, *shape),
        }
        replay_valid = True
        for name, expected_shape in expected_replay_shapes.items():
            if name not in transition_replay:
                check(False, f"transition {name} replay key")
                replay_valid = False
                continue
            try:
                value = np.asarray(transition_replay[name])
            except (TypeError, ValueError):
                check(False, f"transition {name} replay array")
                replay_valid = False
                continue
            replay[name] = value
            shape_ok = value.shape == expected_shape
            check(shape_ok, f"transition {name} replay shape")
            replay_valid = replay_valid and shape_ok
            if name == "candidate_above_ground":
                type_ok = value.dtype == np.dtype(bool)
                check(type_ok, f"transition {name} replay type")
                replay_valid = replay_valid and type_ok
            else:
                type_ok = value.dtype.kind in "fiu"
                check(type_ok, f"transition {name} replay real numeric type")
                replay_valid = replay_valid and type_ok
        seed_shapes = {
            "candidate_above_ground": shape,
            "transition_seed_pressure": shape,
            "transition_seed_temperature": shape,
            **{f"transition_seed_{name}": shape for name in THERMO_SPECIES},
            "transition_seed_geopotential": shape,
            "transition_seed_geopotential_valid": shape,
            "transition_seed_geopotential_quality": shape,
            "transition_seed_geopotential_source": shape,
            "transition_seed_surface_pressure": shape[1:],
        }
        seed_valid = True
        for name, expected_shape in seed_shapes.items():
            if name not in transition_inputs:
                check(False, f"{name} transition input key")
                seed_valid = False
                continue
            try:
                value = np.asarray(transition_inputs[name])
            except (TypeError, ValueError):
                check(False, f"{name} transition input array")
                seed_valid = False
                continue
            transition_seed[name] = value
            shape_ok = value.shape == expected_shape
            check(shape_ok, f"{name} transition input shape")
            seed_valid = seed_valid and shape_ok
            if name == "candidate_above_ground":
                try:
                    binary = np.all((value == 0) | (value == 1))
                except (TypeError, ValueError):
                    binary = False
                check(bool(binary), "transition candidate domain binary")
                seed_valid = seed_valid and bool(binary)
            elif name in (
                "transition_seed_geopotential_valid",
                "transition_seed_geopotential_quality",
                "transition_seed_geopotential_source",
            ):
                integer = value.dtype.kind in "iu"
                check(integer, f"{name} transition input integer type")
                seed_valid = seed_valid and integer
            else:
                numeric = value.dtype.kind in "fiu"
                check(numeric, f"{name} transition input real numeric type")
                seed_valid = seed_valid and numeric

        if not replay_valid or not seed_valid:
            return True, False, np.zeros(shape, dtype=bool)
        candidate_domain = replay["candidate_above_ground"]
        final_domain = candidate_domain & selected_columns[None, :, :]
        seed_domain = transition_seed["candidate_above_ground"].astype(bool)
        check(np.array_equal(candidate_domain, seed_domain),
              "transition replay/input candidate domain identity")
        check(np.all(candidate_domain | ~above),
              "transition candidate domain retains original cells")
        check(np.all(np.sum(candidate_domain & ~above, axis=0) <= 1),
              "transition candidate domain adds at most one center")
        check(np.all(~candidate_domain[:-1] | candidate_domain[1:]),
              "transition candidate domain contiguous")
        pressure_centers = np.broadcast_to(pressure[:, None, None], shape)
        check(
            np.array_equal(
                transition_seed["transition_seed_pressure"][candidate_domain],
                pressure_centers[candidate_domain],
            ),
            "transition seed pressure-center identity",
        )
        # The seed supplies positive pressure transitions only. Negative
        # requests are applied by the preceding hydrostatic stage.
        expected_seed_pressure = np.maximum(
            np.asarray(surface_boundary_inputs.get("background_surface_pressure"), dtype=np.float32),
            np.asarray(surface_boundary_inputs.get("candidate_surface_pressure"), dtype=np.float32),
        )
        check(
            np.array_equal(
                transition_seed["transition_seed_surface_pressure"].astype(np.float32),
                expected_seed_pressure,
            ),
            "transition seed surface pressure identity",
        )
        added_cells = candidate_domain & ~above
        check(np.all(~added_cells | selected), "transition new-cell geopotential support")
        seed_phi_valid = transition_seed["transition_seed_geopotential_valid"]
        seed_phi_quality = transition_seed["transition_seed_geopotential_quality"].astype(np.int64)
        seed_phi_source = transition_seed["transition_seed_geopotential_source"].astype(np.int64)
        check(np.all((seed_phi_valid == 0) | (seed_phi_valid == 1)),
              "transition seed Phi valid binary")
        check(np.all(seed_phi_quality >= 0), "transition seed Phi quality nonnegative")
        check(np.all((seed_phi_quality & ~QUALITY_KNOWN_BITS) == 0),
              "transition seed Phi quality bits")
        check(np.all(seed_phi_source >= 0), "transition seed Phi source nonnegative")
        check(np.all((seed_phi_source & ~SOURCE_KNOWN_BITS) == 0),
              "transition seed Phi source bits")
        check(np.all((seed_phi_source & SOURCE_MANUFACTURED_TEST) == 0),
              "transition seed Phi manufactured source prohibited")
        seed_phi_usable = (
            (seed_phi_valid == 1)
            & (seed_phi_source > 0)
            & ((seed_phi_quality & QUALITY_EXCLUDED_BITS) == 0)
        )
        check(np.all(~added_cells | seed_phi_usable),
              "transition seed Phi usable new cells")
        check(np.all(np.isfinite(transition_seed["transition_seed_geopotential"])[added_cells]),
              "transition seed Phi finite new cells")
        check(np.all(np.isfinite(replay["post_temperature"])[selected_domain]),
              "transition post temperature finite original domain")
        check(np.all(np.isfinite(replay["post_species"][:, selected_domain])),
              "transition post species finite original domain")
        check(np.all(np.isfinite(replay["final_temperature"])[final_domain]),
              "transition final temperature finite candidate domain")
        check(np.all(np.isfinite(replay["final_species"][:, final_domain])),
              "transition final species finite candidate domain")
    support_domain = candidate_domain if transition_mode else above
    check(np.all(~selected | support_domain), "geopotential support above ground")
    if surface_variant:
        # The surface contract is a physical input gate, not a permission to
        # manufacture missing boundary values.  Canonical-5 stores all four
        # fields for both states; pressure, temperature, vapor and terrain
        # must be usable on every selected column, with no manufactured bit.
        required_surface_fields = (
            "surface_pressure",
            "surface_temperature",
            "surface_vapor",
            "surface_height",
        )
        for prefix in ("background", "candidate"):
            for field in required_surface_fields:
                value_name = f"{prefix}_{field}"
                valid_name = f"{value_name}_valid"
                quality_name = f"{value_name}_quality"
                source_name = f"{value_name}_source"
                boundary_values = surface_boundary_inputs.get(value_name)
                boundary_valid = surface_boundary_inputs.get(valid_name)
                boundary_quality = surface_boundary_inputs.get(quality_name)
                boundary_source = surface_boundary_inputs.get(source_name)
                complete_boundary = all(
                    item is not None
                    for item in (
                        boundary_values,
                        boundary_valid,
                        boundary_quality,
                        boundary_source,
                    )
                )
                check(complete_boundary, f"{value_name} surface replay input")
                if not complete_boundary:
                    continue
                usable_boundary = (
                    (boundary_valid == 1)
                    & (boundary_source > 0)
                    & ((boundary_quality & QUALITY_EXCLUDED_BITS) == 0)
                    & ((boundary_source & SOURCE_MANUFACTURED_TEST) == 0)
                )
                check(
                    np.all(usable_boundary[selected_columns]),
                    f"{value_name} selected surface provenance",
                )
                check(
                    np.all(np.isfinite(boundary_values[selected_columns])),
                    f"{value_name} selected surface finite",
                )
    check(
        np.all(np.isfinite(geopotential["background"])[selected_domain]),
        "background geopotential finite",
    )
    check(
        np.all(np.isfinite(geopotential["candidate"])[
            final_domain if transition_mode else selected_domain
        ]),
        "candidate geopotential finite",
    )

    for prefix in ("background", "candidate"):
        metadata = geopotential_metadata[prefix]
        check(np.all((metadata["valid"] == 0) | (metadata["valid"] == 1)),
              f"{prefix} geopotential valid binary")
        check(np.all(metadata["quality"] >= 0), f"{prefix} geopotential quality nonnegative")
        check(np.all((metadata["quality"] & ~QUALITY_KNOWN_BITS) == 0),
              f"{prefix} geopotential quality bits")
        check(np.all(metadata["source"] >= 0), f"{prefix} geopotential source nonnegative")
        check(np.all((metadata["source"] & ~SOURCE_KNOWN_BITS) == 0),
              f"{prefix} geopotential source bits")
        check(np.all((metadata["source"] & SOURCE_MANUFACTURED_TEST) == 0),
              f"{prefix} geopotential manufactured source prohibited")
        usable = (
            metadata["valid"].astype(bool)
            & (metadata["source"] > 0)
            & ((metadata["quality"] & QUALITY_EXCLUDED_BITS) == 0)
        )
        domain = (
            final_domain
            if transition_mode and prefix == "candidate"
            else selected_domain
        )
        check(np.all(~domain | usable), f"{prefix} geopotential complete usable input")

    thermo: dict[str, dict[str, np.ndarray]] = {"background": {}, "candidate": {}}
    for prefix in ("background", "candidate"):
        for species in THERMO_FIELDS:
            name = f"{prefix}_{species}"
            variable = dataset.variables.get(name)
            if variable is None:
                check(False, f"{name} variable for geopotential replay")
                return True, False, np.zeros(shape, dtype=bool)
            thermo[prefix][species] = read_variable(
                name, np.dtype(np.float32), ("z", "y", "x"),
                THERMO_VALUE_UNITS[species], value_time=True,
            )
            if not clean:
                return True, False, np.zeros(shape, dtype=bool)
            value = thermo[prefix][species]
            domain = (
                final_domain
                if transition_mode and prefix == "candidate"
                else selected_domain
            )
            check(
                np.all(np.isfinite(value)[domain]),
                f"{name} finite for geopotential replay",
            )
            if species != "temperature":
                check(
                    np.all((value >= 0.0)[domain]),
                    f"{name} nonnegative for geopotential replay",
                )

            for suffix in ("valid", "quality", "source"):
                metadata_name = f"{name}_{suffix}"
                metadata_variable = dataset.variables.get(metadata_name)
                if metadata_variable is None:
                    check(False, f"{metadata_name} variable for geopotential replay")
                    return True, False, np.zeros(shape, dtype=bool)
                metadata = read_variable(
                    metadata_name, np.dtype(np.int32), ("z", "y", "x"), "1"
                )
                if not clean:
                    return True, False, np.zeros(shape, dtype=bool)
                metadata = metadata.astype(np.int64)
                check(np.all(metadata >= 0), f"{metadata_name} nonnegative")
                if suffix == "valid":
                    check(np.all((metadata == 0) | (metadata == 1)),
                          f"{metadata_name} binary")
                if suffix == "quality":
                    check(np.all((metadata & ~QUALITY_KNOWN_BITS) == 0),
                          f"{metadata_name} bits")
                if suffix == "source":
                    check(np.all((metadata & ~SOURCE_KNOWN_BITS) == 0),
                          f"{metadata_name} bits")
                    check(np.all((metadata & SOURCE_MANUFACTURED_TEST) == 0),
                          f"{metadata_name} manufactured source prohibited")
                thermo[prefix].setdefault(f"{species}_meta", {})[suffix] = metadata
            metadata = thermo[prefix][f"{species}_meta"]
            usable = (
                metadata["valid"].astype(bool)
                & (metadata["source"] > 0)
                & ((metadata["quality"] & QUALITY_EXCLUDED_BITS) == 0)
            )
            check(np.all(~domain | usable), f"{name} complete usable input")

    # Positive references are one-based pressure-center indices.  The surface
    # variant reserves zero for a fixed-terrain anchor, but only where support
    # is selected; inactive columns remain zero in both contracts.
    expected_reference = np.argmax(above, axis=0).astype(np.int64) + 1
    if surface_variant:
        check(
            np.all(reference_level[selected_columns] == 0),
            "surface geopotential selected reference level",
        )
    else:
        check(
            np.all(reference_level[selected_columns] == expected_reference[selected_columns]),
            "geopotential reference lowest represented center",
        )
    check(
        np.all(reference_level[~selected_columns] == 0),
        "inactive geopotential reference level",
    )

    background_phi = geopotential["background"]
    candidate_phi = geopotential["candidate"]
    changed = changed_bits(background_phi, candidate_phi)
    check(np.all(~changed | selected), "geopotential changes within support")
    if not transition_mode:
        for prefix in ("background", "candidate"):
            for suffix in ("valid", "quality"):
                check(
                    np.array_equal(
                        geopotential_metadata[prefix][suffix],
                        geopotential_metadata["background"][suffix],
                    ),
                    f"{prefix} geopotential {suffix} metadata identity",
                )
        expected_source = np.where(
            changed,
            geopotential_metadata["background"]["source"] | SOURCE_COLUMN_PHYSICS,
            geopotential_metadata["background"]["source"],
        )
        check(
            np.array_equal(geopotential_metadata["candidate"]["source"], expected_source),
            "geopotential source provenance",
        )

    water_species = THERMO_SPECIES
    replay_ok = True
    if transition_mode:
        from pressure_transition_reference import transition_geopotential_reference
        expected_phi = background_phi.copy()
        stage1_changed = np.zeros(shape, dtype=bool)
        stage2_changed = np.zeros(shape, dtype=bool)

    for j, i in np.argwhere(selected_columns):
        j = int(j)
        i = int(i)
        bottom = int(np.argmax(above[:, j, i]))
        if surface_variant:
            if reference_level[j, i] != 0:
                check(False, "surface geopotential reference level must be zero")
                replay_ok = False
                continue
        else:
            bottom = int(reference_level[j, i]) - 1
            if bottom < 0 or bottom >= pressure.size:
                check(False, "geopotential reference level range")
                replay_ok = False
                continue
        levels = np.arange(bottom, pressure.size)
        check(np.all(above[levels, j, i]), "geopotential selected column coverage")
        if any(species not in thermo["background"] or species not in thermo["candidate"]
               for species in THERMO_FIELDS):
            replay_ok = False
            continue
        temperature_before = thermo["background"]["temperature"][levels, j, i].astype(np.float64)
        temperature_after = (
            replay["post_temperature"][levels, j, i].astype(np.float64)
            if transition_mode
            else thermo["candidate"]["temperature"][levels, j, i].astype(np.float64)
        )
        water_before = np.stack(
            [thermo["background"][species][levels, j, i] for species in water_species],
            axis=0,
        ).astype(np.float64)
        water_after = (
            replay["post_species"][:, levels, j, i].astype(np.float64)
            if transition_mode
            else np.stack(
                [thermo["candidate"][species][levels, j, i] for species in water_species],
                axis=0,
            ).astype(np.float64)
        )
        p = pressure[levels].astype(np.float64)
        rho_d_before = p / (287.05 * temperature_before * (1.0 + water_before[0] / 0.622))
        rho_d_after = p / (287.05 * temperature_after * (1.0 + water_after[0] / 0.622))
        rho_before = rho_d_before * (1.0 + np.sum(water_before, axis=0))
        rho_after = rho_d_after * (1.0 + np.sum(water_after, axis=0))
        valid_column = (
            np.all(np.isfinite(p)) and np.all(p > 0.0)
            and np.all(np.diff(p) < 0.0)
            and np.all(np.isfinite(rho_before)) and np.all(rho_before > 0.0)
            and np.all(np.isfinite(rho_after)) and np.all(rho_after > 0.0)
            and np.all((temperature_before >= 150.0) & (temperature_before <= 350.0))
            and np.all((temperature_after >= 150.0) & (temperature_after <= 350.0))
            and np.all(water_before[0] <= float(np.float32(0.2)))
            and np.all(water_after[0] <= float(np.float32(0.2)))
        )
        check(valid_column, "geopotential replay physical inputs")
        if not valid_column:
            replay_ok = False
            continue
        delta_p_alpha = p / rho_after - p / rho_before
        delta = np.zeros(levels.size, dtype=np.float64)
        if surface_variant:
            surface_pressure_before = float(
                surface_boundary_inputs["background_surface_pressure"][j, i]
            )
            surface_pressure_after = float(
                min(
                    surface_boundary_inputs["candidate_surface_pressure"][j, i],
                    surface_pressure_before,
                )
                if transition_mode
                else surface_boundary_inputs["candidate_surface_pressure"][j, i]
            )
            surface_temperature_before = float(
                surface_boundary_inputs["background_surface_temperature"][j, i]
            )
            surface_temperature_after = float(
                surface_boundary_inputs["candidate_surface_temperature"][j, i]
            )
            surface_vapor_before = float(
                surface_boundary_inputs["background_surface_vapor"][j, i]
            )
            surface_vapor_after = float(
                surface_boundary_inputs["candidate_surface_vapor"][j, i]
            )
            surface_values = np.asarray(
                (
                    surface_pressure_before,
                    surface_pressure_after,
                    surface_temperature_before,
                    surface_temperature_after,
                    surface_vapor_before,
                    surface_vapor_after,
                ),
                dtype=np.float64,
            )
            valid_surface = (
                np.all(np.isfinite(surface_values))
                and np.all(surface_values[:2] >= p[0])
                and np.all(surface_values[:2] > 0.0)
                and np.all((surface_values[2:4] >= 150.0) & (surface_values[2:4] <= 350.0))
                and np.all(surface_values[4:] >= 0.0)
                and np.all(surface_values[4:] <= 0.1)
            )
            check(valid_surface, "surface geopotential replay physical inputs")
            if not valid_surface:
                replay_ok = False
                continue
            surface_alpha_before = 287.05 * surface_temperature_before * (
                1.0 + surface_vapor_before / 0.622
            ) / (1.0 + surface_vapor_before)
            surface_alpha_after = 287.05 * surface_temperature_after * (
                1.0 + surface_vapor_after / 0.622
            ) / (1.0 + surface_vapor_after)
            delta[0] = (
                0.5 * (surface_alpha_after + p[0] / rho_after[0])
                * np.log(surface_pressure_after / p[0])
                - 0.5 * (surface_alpha_before + p[0] / rho_before[0])
                * np.log(surface_pressure_before / p[0])
            )
        delta[1:] = delta[0] + np.cumsum(
            0.5 * (delta_p_alpha[:-1] + delta_p_alpha[1:])
            * np.log(p[:-1] / p[1:])
        )
        unsupported_delta = (delta != 0.0) & ~selected[levels, j, i]
        check(not np.any(unsupported_delta), "geopotential mathematical support")
        if np.any(unsupported_delta):
            replay_ok = False
            continue
        staged = (background_phi[levels, j, i].astype(np.float64) + delta).astype(np.float32)
        if not transition_mode:
            matches = np.array_equal(candidate_phi[levels, j, i], staged)
            check(matches, "independent pressure geopotential replay")
            replay_ok &= matches
            check(
                np.all(np.diff(candidate_phi[levels, j, i].astype(np.float64)) > 0.0),
                "candidate geopotential monotonicity",
            )
            continue

        stage1_changed[levels, j, i] = changed_bits(
            background_phi[levels, j, i], staged
        )
        candidate_levels = np.flatnonzero(candidate_domain[:, j, i])
        added = candidate_levels.size - levels.size
        positive_pressure = (
            surface_boundary_inputs["candidate_surface_pressure"][j, i]
            > surface_boundary_inputs["background_surface_pressure"][j, i]
        )
        if not positive_pressure:
            expected_phi[levels, j, i] = staged
            continue
        if added not in (0, 1) or candidate_levels.size == 0:
            check(False, "pressure transition active-center count")
            replay_ok = False
            continue
        if added and candidate_levels[1] != bottom:
            check(False, "pressure transition added-center location")
            replay_ok = False
            continue
        final_temperature = replay["final_temperature"][candidate_levels, j, i].astype(np.float64)
        final_species = replay["final_species"][:, candidate_levels, j, i].astype(np.float64)
        check(
            np.all(np.isfinite(final_temperature))
            and np.all((final_temperature >= 150.0) & (final_temperature <= 350.0))
            and np.all(np.isfinite(final_species))
            and np.all(final_species >= 0.0),
            "pressure transition final physical inputs",
        )
        if (not np.all(np.isfinite(final_temperature))
                or not np.all((final_temperature >= 150.0) & (final_temperature <= 350.0))
                or not np.all(np.isfinite(final_species))
                or not np.all(final_species >= 0.0)):
            replay_ok = False
            continue
        seed_kwargs = {}
        if added:
            new_cell = candidate_levels[0]
            seed_species = np.stack(
                [transition_seed[f"transition_seed_{name}"][new_cell, j, i]
                 for name in water_species],
                axis=0,
            ).astype(np.float64)
            seed_kwargs = {
                "seed_geopotential": float(
                    transition_seed["transition_seed_geopotential"][new_cell, j, i]
                ),
                "seed_temperature": float(
                    transition_seed["transition_seed_temperature"][new_cell, j, i]
                ),
                "seed_species": seed_species,
            }
        try:
            expected_column = transition_geopotential_reference(
                pressure[candidate_levels],
                staged,
                replay["post_temperature"][levels, j, i].astype(np.float64),
                replay["post_species"][:, levels, j, i].astype(np.float64),
                final_temperature,
                final_species,
                surface_pressure_before,
                float(surface_boundary_inputs["candidate_surface_pressure"][j, i]),
                surface_temperature_after,
                surface_vapor_after,
                float(surface_boundary_inputs["candidate_surface_height"][j, i]),
                **seed_kwargs,
            )
        except (TypeError, ValueError, FloatingPointError) as error:
            check(False, f"pressure transition geopotential replay: {error}")
            replay_ok = False
            continue
        expected_phi[candidate_levels, j, i] = expected_column.astype(np.float32)
        stage2_changed[candidate_levels[added:], j, i] = changed_bits(
            staged, expected_phi[candidate_levels[added:], j, i]
        )

    if transition_mode and replay_ok:
        matches = np.array_equal(candidate_phi[final_domain], expected_phi[final_domain])
        check(matches, "independent pressure transition geopotential replay")
        replay_ok &= matches
        for j, i in np.argwhere(selected_columns):
            j = int(j)
            i = int(i)
            check(
                np.all(np.diff(candidate_phi[candidate_domain[:, j, i], j, i].astype(np.float64)) > 0.0),
                "candidate geopotential monotonicity",
            )
        added_cells = candidate_domain & ~above
        expected_valid = geopotential_metadata["background"]["valid"].copy()
        terrain = np.broadcast_to(
            np.asarray(surface_boundary_inputs["candidate_surface_height"], dtype=np.float64), shape
        )[added_cells]
        terrain_tolerance = 256.0 * np.finfo(np.float32).eps * np.maximum(1.0, np.abs(terrain))
        check(np.all(candidate_phi[added_cells].astype(np.float64) / 9.80665 >= terrain - terrain_tolerance),
              "transition new-cell geopotential above terrain")
        expected_quality = geopotential_metadata["background"]["quality"].copy()
        expected_source = geopotential_metadata["background"]["source"].copy()
        expected_valid[added_cells] = 1
        expected_quality[added_cells] = transition_seed[
            "transition_seed_geopotential_quality"
        ][added_cells]
        expected_source[added_cells] = SOURCE_COLUMN_PHYSICS
        retained_changed = (stage1_changed | stage2_changed) & above
        expected_source[retained_changed] |= SOURCE_COLUMN_PHYSICS
        check(np.array_equal(geopotential_metadata["candidate"]["valid"], expected_valid),
              "transition geopotential valid provenance")
        check(np.array_equal(geopotential_metadata["candidate"]["quality"], expected_quality),
              "transition geopotential quality provenance")
        check(np.array_equal(geopotential_metadata["candidate"]["source"], expected_source),
              "transition geopotential source provenance")
        # This is the geometry-stage receipt, not just the final Phi delta.
        # Pressure changes affect the whole column even when stored Phi rounds
        # back to its original value; two Phi stages may also cancel.
        pressure_changed = (
            surface_boundary_inputs["candidate_surface_pressure"]
            != surface_boundary_inputs["background_surface_pressure"]
        )
        changed = (stage1_changed | stage2_changed
                   | (candidate_domain & pressure_changed[None, :, :]))

    clean = clean and replay_ok
    return True, bool(clean), changed if clean else np.zeros(shape, dtype=bool)


def validate_pressure_geostrophic_extension(
    dataset: netCDF4.Dataset,
    shape: tuple[int, ...],
    above: np.ndarray,
    latitude: np.ndarray,
    fields: dict[str, np.ndarray],
    candidate_balance_support: np.ndarray,
    geopotential_present: bool,
    geopotential_clean: bool,
    pressure_candidate: bool,
    schema_version: int,
    grid_dx: float,
    grid_dy: float,
    require,
    *,
    transition_inputs: dict[str, np.ndarray] | None = None,
    transition_replay: dict[str, np.ndarray] | None = None,
) -> tuple[bool, bool, np.ndarray]:
    """Replay the optional original/final pressure-level geostrophic metric.

    The v3 transition contract evaluates the reference state on the candidate
    domain without allowing candidate values to redefine retained background
    cells.  Retained cells use immutable background values; only newly added
    cells use the independently checked transition seed.
    """

    reserved_attributes = {
        name
        for name in dataset.ncattrs()
        if name.startswith("pressure_geostrophic")
        or name.startswith("original_full_geostrophic_rms")
        or name.startswith("reference_full_geostrophic_rms")
        or name.startswith("candidate_full_geostrophic_rms")
    }
    reserved_variables = {
        name for name in dataset.variables if name.startswith("geostrophic_")
    }
    present = bool(reserved_attributes or reserved_variables)
    if not present:
        return False, False, np.zeros(shape, dtype=bool)

    clean = True

    transition_mode = transition_inputs is not None or transition_replay is not None
    transition_pair = transition_inputs is not None and transition_replay is not None

    def check(condition: bool, message: str) -> None:
        nonlocal clean
        if not condition:
            clean = False
        require(condition, message)

    contract = getattr(dataset, "pressure_geostrophic_contract", "")
    is_v2 = contract == PRESSURE_GEOSTROPHIC_V2_CONTRACT
    is_v3 = contract == PRESSURE_GEOSTROPHIC_V3_CONTRACT
    allowed_attributes = (
        PRESSURE_GEOSTROPHIC_V3_ATTRIBUTES if is_v3
        else PRESSURE_GEOSTROPHIC_V2_ATTRIBUTES if is_v2
        else PRESSURE_GEOSTROPHIC_BASE_ATTRIBUTES
    )
    allowed_variables = (
        PRESSURE_GEOSTROPHIC_V2_VARIABLES if (is_v2 or is_v3)
        else PRESSURE_GEOSTROPHIC_V1_VARIABLES
    )

    supported = (
        pressure_candidate
        and schema_version in (7, 8)
        and geopotential_present
        and geopotential_clean
    )
    check(supported, "pressure geostrophic extension context")
    check(
        reserved_attributes <= set(allowed_attributes),
        "known pressure geostrophic attributes",
    )
    check(
        reserved_variables <= set(allowed_variables),
        "known pressure geostrophic variables",
    )
    complete = (
        set(allowed_attributes) <= set(dataset.ncattrs())
        and set(allowed_variables) <= set(dataset.variables)
    )
    check(complete, "complete pressure geostrophic extension")
    if is_v3:
        check(transition_pair, "v3 pressure geostrophic transition replay pair")
    elif transition_mode:
        check(transition_pair, "pressure geostrophic transition replay pair")
    if not supported or not complete or (is_v3 and not transition_pair):
        return True, False, np.zeros(shape, dtype=bool)

    check(
        getattr(dataset, "pressure_geostrophic_contract", "")
        in (
            PRESSURE_GEOSTROPHIC_CONTRACT,
            PRESSURE_GEOSTROPHIC_V2_CONTRACT,
            PRESSURE_GEOSTROPHIC_V3_CONTRACT,
        ),
        "pressure geostrophic contract",
    )
    if is_v3:
        check(
            getattr(dataset, "pressure_geostrophic_reference", "")
            == PRESSURE_GEOSTROPHIC_V3_REFERENCE,
            "pressure geostrophic reference",
        )
    check(
        getattr(dataset, "pressure_geostrophic_scope", "")
        == PRESSURE_GEOSTROPHIC_SCOPE,
        "pressure geostrophic scope",
    )
    check(
        getattr(dataset, "pressure_geostrophic_units", "")
        == PRESSURE_GEOSTROPHIC_UNITS,
        "pressure geostrophic units",
    )
    science_assessed = exact_scalar_int32(
        getattr(dataset, "pressure_geostrophic_science_assessed", None)
    )
    check(science_assessed == 0, "pressure geostrophic science assessed")
    requested_cells_reported = None
    evaluated_cells_reported = None
    partial_coverage_reported = None
    if is_v2 or is_v3:
        requested_cells_reported = exact_scalar_int32(
            getattr(dataset, "pressure_geostrophic_requested_cells", None)
        )
        evaluated_cells_reported = exact_scalar_int32(
            getattr(dataset, "pressure_geostrophic_evaluated_cells", None)
        )
        partial_coverage_reported = exact_scalar_int32(
            getattr(dataset, "pressure_geostrophic_partial_coverage", None)
        )
        check(
            requested_cells_reported is not None and requested_cells_reported >= 0,
            "pressure geostrophic requested cells",
        )
        check(
            evaluated_cells_reported is not None and evaluated_cells_reported >= 0,
            "pressure geostrophic evaluated cells",
        )
        check(
            partial_coverage_reported in (0, 1),
            "pressure geostrophic partial coverage",
        )
    reference_attribute = (
        "reference_full_geostrophic_rms"
        if is_v3
        else "original_full_geostrophic_rms"
    )
    reference_reported = exact_scalar_float64(
        getattr(dataset, reference_attribute, None)
    )
    candidate_reported = exact_scalar_float64(
        getattr(dataset, "candidate_full_geostrophic_rms", None)
    )
    check(
        reference_reported is not None
        and np.isfinite(reference_reported)
        and reference_reported >= 0.0,
        f"{reference_attribute}",
    )
    check(
        candidate_reported is not None
        and np.isfinite(candidate_reported)
        and candidate_reported >= 0.0,
        "candidate full geostrophic rms",
    )

    support_variable = dataset.variables["geostrophic_validation_support"]
    check(
        support_variable.dimensions == ("z", "y", "x"),
        "geostrophic validation support dimensions",
    )
    check(
        is_signed_int32(support_variable.dtype),
        "geostrophic validation support type",
    )
    check(
        getattr(support_variable, "units", "") == "1",
        "geostrophic validation support units",
    )
    check(
        "scale_factor" not in support_variable.ncattrs()
        and "add_offset" not in support_variable.ncattrs()
        and "valid_time" not in support_variable.ncattrs(),
        "geostrophic validation support metadata",
    )
    validation_support = values(support_variable)
    check(validation_support.dtype.kind == "i" and validation_support.dtype.itemsize == 4,
          "geostrophic validation support unpacked type")
    check(validation_support.shape == shape, "geostrophic validation support shape")
    check(
        np.all((validation_support == 0) | (validation_support == 1)),
        "geostrophic validation support binary",
    )
    stencil_support_values = None
    if is_v2 or is_v3:
        stencil_variable = dataset.variables["geostrophic_stencil_support"]
        check(
            stencil_variable.dimensions == ("z", "y", "x"),
            "geostrophic stencil support dimensions",
        )
        check(
            is_signed_int32(stencil_variable.dtype),
            "geostrophic stencil support type",
        )
        check(
            getattr(stencil_variable, "units", "") == "1",
            "geostrophic stencil support units",
        )
        check(
            "scale_factor" not in stencil_variable.ncattrs()
            and "add_offset" not in stencil_variable.ncattrs()
            and "valid_time" not in stencil_variable.ncattrs(),
            "geostrophic stencil support metadata",
        )
        stencil_support_values = values(stencil_variable)
        check(
            stencil_support_values.dtype.kind == "i"
            and stencil_support_values.dtype.itemsize == 4,
            "geostrophic stencil support unpacked type",
        )
        check(
            stencil_support_values.shape == shape,
            "geostrophic stencil support shape",
        )
        check(
            np.all((stencil_support_values == 0) | (stencil_support_values == 1)),
            "geostrophic stencil support binary",
        )

    candidate_domain = above
    transition_new_cells = np.zeros(shape, dtype=bool)
    reference_fields = {
        "u": fields["background_u"].astype(np.float64),
        "v": fields["background_v"].astype(np.float64),
    }
    if transition_mode:
        if not transition_pair:
            return True, False, np.zeros(shape, dtype=bool)

        replay_domain_raw = transition_replay.get("candidate_above_ground")
        input_domain_raw = transition_inputs.get("candidate_above_ground")
        if replay_domain_raw is None or input_domain_raw is None:
            check(False, "geostrophic transition candidate domain keys")
            return True, False, np.zeros(shape, dtype=bool)
        replay_domain = np.asarray(replay_domain_raw)
        input_domain = np.asarray(input_domain_raw)
        replay_domain_ok = replay_domain.shape == shape and replay_domain.dtype == np.dtype(bool)
        input_domain_ok = input_domain.shape == shape and input_domain.dtype.kind in "biu"
        check(replay_domain_ok, "geostrophic transition replay candidate domain")
        check(input_domain_ok, "geostrophic transition input candidate domain")
        if not replay_domain_ok or not input_domain_ok:
            return True, False, np.zeros(shape, dtype=bool)
        check(
            np.all((input_domain == 0) | (input_domain == 1)),
            "geostrophic transition input candidate domain binary",
        )
        candidate_domain = replay_domain.copy()
        input_domain_bool = input_domain.astype(bool)
        check(
            np.array_equal(candidate_domain, input_domain_bool),
            "geostrophic transition candidate domain identity",
        )
        if is_v3:
            check(
                np.all(~above | candidate_domain),
                "geostrophic transition retains original domain",
            )
            check(
                np.all(~candidate_domain[:-1] | candidate_domain[1:]),
                "geostrophic transition candidate domain contiguous",
            )
            check(
                np.all(np.sum(candidate_domain & ~above, axis=0) <= 1),
                "geostrophic transition adds at most one center",
            )
            transition_new_cells = candidate_domain & ~above
            transition_seed_above = transition_inputs.get(
                "transition_seed_above_ground"
            )
            if transition_seed_above is None:
                check(False, "geostrophic transition seed domain")
            else:
                transition_seed_above = np.asarray(transition_seed_above)
                seed_domain_ok = (
                    transition_seed_above.shape == shape
                        and transition_seed_above.dtype.kind in "biu"
                )
                check(seed_domain_ok, "geostrophic transition seed domain shape/type")
                if seed_domain_ok:
                    check(
                        np.all((transition_seed_above == 0) | (transition_seed_above == 1)),
                        "geostrophic transition seed domain binary",
                    )
                    check(
                        np.array_equal(
                            transition_seed_above.astype(bool), candidate_domain
                        ),
                        "geostrophic transition seed/candidate domain identity",
                    )

            seed_names = {
                "u": "transition_seed_u",
                "v": "transition_seed_v",
                "geopotential": "transition_seed_geopotential",
            }
            seed_metadata: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
            seed_values: dict[str, np.ndarray] = {}
            seed_inputs_ok = True
            for field_name, seed_name in seed_names.items():
                value = transition_inputs.get(seed_name)
                valid = transition_inputs.get(f"{seed_name}_valid")
                quality = transition_inputs.get(f"{seed_name}_quality")
                source = transition_inputs.get(f"{seed_name}_source")
                if any(item is None for item in (value, valid, quality, source)):
                    check(False, f"{seed_name} transition input keys")
                    seed_inputs_ok = False
                    continue
                value = np.asarray(value)
                valid = np.asarray(valid)
                quality = np.asarray(quality)
                source = np.asarray(source)
                value_ok = value.shape == shape and value.dtype.kind in "fiu"
                metadata_ok = all(
                    item.shape == shape and item.dtype.kind in "iu"
                    for item in (valid, quality, source)
                )
                check(value_ok, f"{seed_name} transition input value")
                check(metadata_ok, f"{seed_name} transition input metadata")
                seed_inputs_ok = seed_inputs_ok and value_ok and metadata_ok
                if not value_ok or not metadata_ok:
                    continue
                seed_values[field_name] = value.astype(np.float64)
                seed_metadata[field_name] = (
                    valid.astype(np.int64), quality.astype(np.int64), source.astype(np.int64)
                )
                valid_i, quality_i, source_i = seed_metadata[field_name]
                usable = (
                    (valid_i == 1)
                    & (source_i > 0)
                    & ((quality_i & QUALITY_EXCLUDED_BITS) == 0)
                    & ((quality_i & ~QUALITY_KNOWN_BITS) == 0)
                    & ((source_i & ~SOURCE_KNOWN_BITS) == 0)
                    & ((source_i & SOURCE_MANUFACTURED_TEST) == 0)
                )
                check(
                    np.all((valid_i == 0) | (valid_i == 1)),
                    f"{seed_name} transition valid binary",
                )
                check(
                    np.all(~transition_new_cells | usable),
                    f"{seed_name} transition new-cell usability",
                )
                check(
                    np.all(~transition_new_cells | np.isfinite(seed_values[field_name])),
                    f"{seed_name} transition new-cell finite",
                )
                if field_name in ("u", "v"):
                    lower, upper = PRESSURE_TRANSITION_VALUE_RANGES[field_name]
                elif field_name == "geopotential":
                    lower, upper = -10000.0, 500000.0
                else:
                    continue
                check(
                    np.all(
                        ~transition_new_cells
                        | ((seed_values[field_name] >= lower)
                           & (seed_values[field_name] <= upper))
                    ),
                    f"{seed_name} transition new-cell range",
                )
            if not seed_inputs_ok:
                return True, False, np.zeros(shape, dtype=bool)
            for field_name in ("u", "v"):
                reference_fields[field_name][transition_new_cells] = seed_values[field_name][
                    transition_new_cells
                ]
        else:
            # Legacy v1/v2 diagnostics have no honest reference for an added
            # domain.  Same-domain probes remain compatible with their old
            # baseline semantics.
            check(
                np.array_equal(candidate_domain, above),
                "legacy geostrophic contract cannot hide added domain",
            )
            if not np.array_equal(candidate_domain, above):
                return True, False, np.zeros(shape, dtype=bool)

    phi_support = values(dataset["geopotential_support"]).astype(bool)
    base_support = candidate_balance_support | phi_support
    expected_support = base_support.copy()
    expected_support[:, 1:, :] |= base_support[:, :-1, :]
    expected_support[:, :-1, :] |= base_support[:, 1:, :]
    expected_support[:, :, 1:] |= base_support[:, :, :-1]
    expected_support[:, :, :-1] |= base_support[:, :, 1:]
    expected_support &= candidate_domain
    if is_v3:
        check(
            np.all(~transition_new_cells | phi_support),
            "geostrophic transition new cells explicit geopotential support",
        )
    check(
        np.array_equal(validation_support == 1, expected_support),
        "independent geostrophic validation support",
    )
    check(np.any(expected_support), "nonempty geostrophic validation support")

    if is_v2 or is_v3:
        x_neighbor = np.zeros(shape, dtype=bool)
        y_neighbor = np.zeros(shape, dtype=bool)
        if shape[2] > 1:
            x_neighbor[:, :, 1:] |= candidate_domain[:, :, :-1]
            x_neighbor[:, :, :-1] |= candidate_domain[:, :, 1:]
        if shape[1] > 1:
            y_neighbor[:, 1:, :] |= candidate_domain[:, :-1, :]
            y_neighbor[:, :-1, :] |= candidate_domain[:, 1:, :]
        expected_stencil = expected_support & x_neighbor & y_neighbor
        check(
            np.array_equal(stencil_support_values == 1, expected_stencil),
            "independent geostrophic stencil support",
        )
        expected_requested_cells = int(np.count_nonzero(expected_support))
        expected_evaluated_cells = int(np.count_nonzero(expected_stencil))
        expected_partial_coverage = int(
            np.any(expected_support & ~expected_stencil)
        )
        check(
            requested_cells_reported == expected_requested_cells,
            "pressure geostrophic requested cell count",
        )
        check(
            evaluated_cells_reported == expected_evaluated_cells,
            "pressure geostrophic evaluated cell count",
        )
        check(
            partial_coverage_reported == expected_partial_coverage,
            "pressure geostrophic partial coverage flag",
        )
        check(expected_evaluated_cells > 0, "nonempty geostrophic stencil support")
    else:
        expected_stencil = expected_support
        expected_requested_cells = int(np.count_nonzero(expected_support))
        expected_evaluated_cells = expected_requested_cells
        expected_partial_coverage = 0

    geopotential: dict[str, np.ndarray] = {}
    metadata: dict[str, dict[str, np.ndarray]] = {"background": {}, "candidate": {}}
    for prefix in ("background", "candidate"):
        value_name = f"{prefix}_geopotential"
        geopotential[prefix] = values(dataset[value_name]).astype(np.float64)
        for suffix in ("valid", "quality", "source"):
            metadata[prefix][suffix] = values(
                dataset[f"{value_name}_{suffix}"]
            ).astype(np.int64)

    reference_geopotential = geopotential["background"].copy()
    reference_metadata = {
        suffix: metadata["background"][suffix].copy()
        for suffix in ("valid", "quality", "source")
    }
    if is_v3:
        reference_geopotential[transition_new_cells] = seed_values["geopotential"][
            transition_new_cells
        ]
        for suffix, values_for_field in zip(
            ("valid", "quality", "source"), seed_metadata["geopotential"]
        ):
            reference_metadata[suffix][transition_new_cells] = values_for_field[
                transition_new_cells
            ]

    common_usable = (
        candidate_domain
        & (reference_metadata["valid"] == 1)
        & (metadata["candidate"]["valid"] == 1)
        & (reference_metadata["source"] > 0)
        & (metadata["candidate"]["source"] > 0)
        & ((reference_metadata["quality"] & QUALITY_EXCLUDED_BITS) == 0)
        & ((metadata["candidate"]["quality"] & QUALITY_EXCLUDED_BITS) == 0)
        & np.isfinite(reference_geopotential)
        & np.isfinite(geopotential["candidate"])
        & np.isfinite(latitude)[None, :, :]
    )
    check(
        np.all(~expected_support | common_usable),
        "geostrophic common represented input usability",
    )
    if not clean:
        return True, False, np.zeros(shape, dtype=bool)

    def residual_rms(phi: np.ndarray, u: np.ndarray, v: np.ndarray) -> float:
        total = 0.0
        count = 0
        pi = np.arccos(-1.0)
        evaluation_support = expected_stencil if (is_v2 or is_v3) else expected_support
        for k, j, i in np.argwhere(evaluation_support):
            k = int(k)
            j = int(j)
            i = int(i)
            ix = -1
            if i + 1 < shape[2] and candidate_domain[k, j, i + 1]:
                ix = i + 1
            elif i > 0 and candidate_domain[k, j, i - 1]:
                ix = i - 1
            jy = -1
            if j + 1 < shape[1] and candidate_domain[k, j + 1, i]:
                jy = j + 1
            elif j > 0 and candidate_domain[k, j - 1, i]:
                jy = j - 1
            check(ix >= 0, "geostrophic usable horizontal x neighbor")
            check(jy >= 0, "geostrophic usable horizontal y neighbor")
            if ix < 0 or jy < 0:
                continue
            check(common_usable[k, j, i], "geostrophic center input usability")
            check(common_usable[k, j, ix], "geostrophic x-neighbor input usability")
            check(common_usable[k, jy, i], "geostrophic y-neighbor input usability")
            if not (
                common_usable[k, j, i]
                and common_usable[k, j, ix]
                and common_usable[k, jy, i]
            ):
                continue
            dphidx = (phi[k, j, ix] - phi[k, j, i]) / (
                (ix - i) * 0.5 * (grid_dx + grid_dx)
            )
            dphidy = (phi[k, jy, i] - phi[k, j, i]) / (
                (jy - j) * 0.5 * (grid_dy + grid_dy)
            )
            f = 1.458423e-4 * np.sin(latitude[j, i] * pi / 180.0)
            ru = -f * v[k, j, i] + dphidx
            rv = f * u[k, j, i] + dphidy
            check(np.isfinite(ru) and np.isfinite(rv), "finite geostrophic residual")
            term = ru * ru + rv * rv
            check(np.isfinite(term), "finite geostrophic residual square")
            if not np.isfinite(term):
                continue
            total += term
            count += 1
        check(count > 0, "nonempty geostrophic residual support")
        return float(np.sqrt(total / (2.0 * count))) if count else 0.0

    original_rms = residual_rms(
        reference_geopotential,
        reference_fields["u"],
        reference_fields["v"],
    )
    candidate_rms = residual_rms(
        geopotential["candidate"],
        fields["candidate_u"].astype(np.float64),
        fields["candidate_v"].astype(np.float64),
    )
    check(
        np.isclose(reference_reported, original_rms, rtol=1.0e-12, atol=1.0e-14),
        f"{reference_attribute} replay",
    )
    check(
        np.isclose(candidate_reported, candidate_rms, rtol=1.0e-12, atol=1.0e-14),
        "candidate full geostrophic rms replay",
    )
    return True, bool(clean), expected_support if clean else np.zeros(shape, dtype=bool)


def validate(path: Path) -> tuple[dict[str, object], list[str]]:
    failures: list[str] = []
    schema_version = -1
    canonical_schema_version: int | None = None
    schema7 = False
    schema8 = False
    radar_reconstruction_present = False
    radar_reconstruction_clean = False
    radar_reconstruction_inputs: dict[str, np.ndarray] = {}
    radar_reconstruction_replay_ok = False
    transition_replay_errors: dict[str, float] = {}
    transition_numerical_clean = False
    omega_target_error_present = False
    omega_target_error_clean = False
    omega_target_error_inputs: dict[str, np.ndarray] = {}
    pressure_analysis_candidate_present = False
    pressure_analysis_candidate_clean = False
    pressure_analysis_candidate_inputs: dict[str, np.ndarray] = {}
    dry_air_flux_present = False
    dry_air_flux_clean = False
    dry_air_flux_inputs: dict[str, np.ndarray] = {}
    dry_air_flux_replay_ok = False
    pressure_geopotential_present = False
    pressure_geopotential_clean = False
    pressure_geopotential_changed = np.zeros((1, 1, 1), dtype=bool)
    pressure_geostrophic_present = False
    pressure_geostrophic_clean = False
    pressure_geostrophic_support = np.zeros((1, 1, 1), dtype=bool)
    pressure_geostrophic_requested_cells: int | None = None
    pressure_geostrophic_evaluated_cells: int | None = None
    pressure_geostrophic_partial_coverage: bool | None = None
    surface_boundary_present = False
    surface_boundary_clean = False
    surface_boundary_inputs: dict[str, np.ndarray] = {}
    pressure_geometry_present = False
    pressure_geometry_clean = False
    pressure_geometry_inputs: dict[str, np.ndarray] = {}

    def require(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    with netCDF4.Dataset(path, "r") as dataset:
        schema_version = exact_scalar_integer(
            getattr(dataset, "diagnostic_schema_version", None)
        )
        if schema_version is None:
            schema_version = -1
        canonical_schema_version = exact_scalar_integer(
            getattr(dataset, "cloud_bal_schema_version", None)
        )
        require(
            canonical_schema_version in (3, 4, 5),
            "canonical schema version",
        )
        schema6 = schema_version == 6
        schema7 = schema_version == 7
        schema8 = schema_version == 8
        pressure_analysis_candidate_present = bool(
            set(PRESSURE_ANALYSIS_CANDIDATE_ATTRIBUTES) & set(dataset.ncattrs())
            or set(PRESSURE_ANALYSIS_CANDIDATE_VARIABLES) & set(dataset.variables)
        )
        pressure_geometry_signal_variables = {
            "requested_surface_pressure",
            "candidate_pressure_interface",
            "candidate_cell_dp",
            "candidate_pressure_mass_measure",
            "continuity_original_background",
        }
        pressure_geometry_present = bool(
            "pressure_geometry_contract" in dataset.ncattrs()
            or "continuity_geometry_scope" in dataset.ncattrs()
            or any(name in dataset.variables for name in pressure_geometry_signal_variables)
            or any(
                name.startswith("requested_surface_pressure")
                or name.startswith("candidate_pressure_")
                for name in dataset.variables
            )
            or any(
                name.startswith("geometry_analysis_")
                for name in dataset.ncattrs()
            )
        )
        present_analysis_attributes = set(ANALYSIS_ATTRIBUTE_NAMES) & set(dataset.ncattrs())
        if not (schema7 or schema8) and present_analysis_attributes:
            require(
                False,
                "schema7 analysis attributes are reserved for schema 7",
            )
        validate_outer_extension(dataset, schema8, require)
        dimensions = {name: len(dim) for name, dim in dataset.dimensions.items()}
        if schema6 or schema7 or schema8 or pressure_analysis_candidate_present:
            require(
                set(dimensions) == {"x", "y", "z", "z_interface", "z_spacing"}
                and dimensions["x"] >= 1
                and dimensions["y"] >= 1
                and dimensions["z"] >= 2
                and dimensions["z_interface"] == dimensions["z"] + 1
                and dimensions["z_spacing"] == dimensions["z"] - 1,
                "schema6 pressure geometry dimensions",
            )
        else:
            require(
                dimensions
                == {"x": 235, "y": 283, "z": 22, "z_interface": 23, "z_spacing": 21},
                "pressure geometry dimensions",
            )
        expected_contract = (
            PRESSURE_ANALYSIS_SHADOW_CONTRACT if pressure_analysis_candidate_present else
            "real_radar_thermo_shadow_v3" if schema8 else
            "real_radar_thermo_shadow_v2" if schema7 else
            "real_radar_thermo_shadow_v1" if schema6 else
            "real_radar_only_shadow_v3"
        )
        require(getattr(dataset, "contract", "") == expected_contract, "contract")
        require(schema_version in (5, 6, 7, 8), "diagnostic schema")
        require(
            getattr(dataset, "evidence_class", "")
            == (PRESSURE_ANALYSIS_SHADOW_EVIDENCE if pressure_analysis_candidate_present
                else "PRESSURE_THERMO_SHADOW_PROPOSAL"
                if schema6 or schema7 or schema8
                else "REAL_RADAR_ONLY_SHADOW_PROPOSAL"),
            "evidence class",
        )
        require(
            getattr(dataset, "configuration_id", "")
            == (PRESSURE_ANALYSIS_SHADOW_CONFIGURATION if pressure_analysis_candidate_present
                else "pressure-thermo-shadow-v3" if schema8
                else "pressure-thermo-shadow-v2" if schema7
                else "pressure-thermo-shadow-v1" if schema6
                else "real-radar-only-shadow-v3"),
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
        boundary_provenance = getattr(dataset, "omega_boundary_provenance", "")
        require(
            boundary_provenance in (
                "COPIED_INTERIOR_DIAGNOSTIC_ONLY",
                PHYSICAL_INPUT_DIAGNOSTIC_ONLY,
            ) if pressure_analysis_candidate_present else
            boundary_provenance == "COPIED_INTERIOR_DIAGNOSTIC_ONLY",
            "omega boundary provenance",
        )
        base_extensions = (
            "verified_operational_identity_v1,radar_no_echo_masks_v1,"
            "pressure_geometry_v2,omega_boundary_contract_v2"
        )
        expected_extensions = (
            base_extensions + ",pressure_thermo_v1,pressure_analysis_v1,pressure_outer_v1" if schema8
            else base_extensions + ",pressure_thermo_v1,pressure_analysis_v1" if schema7
            else base_extensions + ",pressure_thermo_v1" if schema6
            else base_extensions
        )
        # Phi is a dedicated optional pressure-candidate group.  Its contract
        # is identified by its own attributes and variables, so historical
        # files may retain either spelling of the base extension list.
        pressure_geopotential_signalled = bool(
            set(PRESSURE_GEOPOTENTIAL_ATTRIBUTES) & set(dataset.ncattrs())
            or set(PRESSURE_GEOPOTENTIAL_VARIABLES) & set(dataset.variables)
        )
        if pressure_geopotential_signalled:
            require(
                getattr(dataset, "schema_extensions", "") == expected_extensions,
                "schema extensions",
            )
        else:
            require(
                getattr(dataset, "schema_extensions", "") in (
                    expected_extensions,
                    expected_extensions + "," + PRESSURE_GEOPOTENTIAL_EXTENSION,
                ),
                "schema extensions",
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
            if (schema6 or schema7 or schema8 or pressure_analysis_candidate_present) and attribute in ("grid_dx_m", "grid_dy_m"):
                try:
                    grid_value = float(getattr(dataset, attribute))
                except (TypeError, ValueError):
                    grid_value = float("nan")
                require(np.isfinite(grid_value) and grid_value > 0.0, attribute)
            else:
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
        if schema6 or schema7 or schema8:
            required |= {
                "thermo_support", "thermo_surface",
                "candidate_dry_air_mass_measure",
            }
            required |= {
                f"{prefix}_{species}{suffix}"
                for prefix in ("background", "candidate")
                for species in THERMO_FIELDS
                for suffix in ("", "_valid", "_quality", "_source")
            }
        if pressure_geometry_present:
            required |= set(PRESSURE_GEOMETRY_VARIABLES)
            required.add("continuity_original_background")
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
        if pressure_geometry_present and "continuity_original_background" in dataset.variables:
            variable = dataset.variables["continuity_original_background"]
            require(
                variable.dimensions == ("z", "y", "x"),
                "continuity original background dimensions",
            )
            require(
                np.dtype(variable.dtype) == np.dtype(np.float64),
                "continuity original background type",
            )
            require(
                getattr(variable, "units", "") == "s-1",
                "continuity original background units",
            )
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
        candidate_dry_air_mass = (
            values(dataset["candidate_dry_air_mass_measure"]).astype(np.float64)
            if "candidate_dry_air_mass_measure" in dataset.variables
            else None
        )
        surface_pressure_raw = values(dataset["surface_pressure"])
        surface_pressure = surface_pressure_raw.astype(np.float64)
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
        physical_input_boundaries = (
            pressure_analysis_candidate_present
            and boundary_provenance == PHYSICAL_INPUT_DIAGNOSTIC_ONLY
        )
        if physical_input_boundaries:
            for name in ("omega_top_boundary_quality", "omega_bottom_boundary_quality"):
                require(np.all(boundary_metadata[name] == 0),
                        f"{name} physical-input quality")
            for name in ("omega_top_boundary_source", "omega_bottom_boundary_source"):
                require(np.all(boundary_metadata[name] == SOURCE_BOUNDARY_CONDITION),
                        f"{name} physical-input source")
            for name in ("omega_top_boundary_valid", "omega_bottom_boundary_valid"):
                require(np.all(boundary_masks[name] == 1),
                        f"{name} physical-input coverage")
        else:
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
        global_valid_time = exact_scalar_int64(
            getattr(dataset, "valid_time_epoch", None)
        )
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
        transition_present, transition_clean, transition_inputs = read_pressure_transition_seed_payload(
            dataset, above.shape, global_valid_time, require,
        )
        candidate_above = above
        if transition_present:
            require(transition_clean, "pressure transition seed payload")
            if transition_clean:
                candidate_above = transition_inputs["candidate_above_ground"].astype(bool)
        radar_reconstruction_present, radar_reconstruction_clean, radar_reconstruction_inputs = (
            read_radar_reconstruction_extension(
                dataset, above.shape, global_valid_time, schema8, require,
                allow_single_pass_transition=schema7 and transition_present and transition_clean,
            )
        )
        if radar_reconstruction_present:
            require(global_valid_time is not None, "radar reconstruction valid-time epoch type")
            radar_reconstruction_clean = radar_reconstruction_clean and global_valid_time is not None
        original_balance_support = masks["candidate_balance_support"] & above
        stage_balance_support = masks["candidate_balance_support"] & candidate_above
        balance_background = {
            component: fields[f"background_{component}"] for component in ("u", "v", "omega")
        }
        if transition_present and transition_clean:
            from pressure_transition_reference import reconstruct_prebalance_winds

            try:
                restored_winds = reconstruct_prebalance_winds(
                    np.stack(tuple(balance_background.values())), above, candidate_above,
                    np.stack(tuple(transition_inputs[f"transition_seed_{component}"]
                                   for component in ("u", "v", "omega"))),
                )
            except ValueError as error:
                require(False, f"prebalance wind reconstruction: {error}")
            else:
                balance_background = dict(zip(("u", "v", "omega"), restored_winds.astype(np.float32)))
        surface_boundary_present, surface_boundary_clean, surface_boundary_inputs = (
            read_surface_boundary_extension(
                dataset,
                above.shape[1:],
                global_valid_time,
                canonical_schema_version,
                surface_pressure_raw,
                require,
                allow_pressure_change=pressure_geometry_present,
            )
        )
        if surface_boundary_present:
            require(surface_boundary_clean, "surface boundary extension")
        radar = masks["radar_valid"]
        radar_coverage = masks["radar_coverage"]
        radar_no_echo = masks["radar_no_echo"]
        radar_missing = masks["radar_missing"]
        pressure_analysis_candidate_present, pressure_analysis_candidate_clean, pressure_analysis_candidate_inputs = (
            read_pressure_analysis_candidate_extension(
                dataset,
                above.shape,
                above,
                global_valid_time,
                canonical_schema_version,
                schema_version,
                require,
            )
        )
        if pressure_analysis_candidate_present:
            require(
                pressure_analysis_candidate_clean,
                "pressure analysis candidate extension",
            )
        pressure_geometry_present, pressure_geometry_clean, pressure_geometry_inputs = (
            read_pressure_geometry_extension(
                dataset,
                above.shape,
                pressure,
                above,
                pressure_interface,
                cell_dp,
                pressure_mass,
                dry_air_mass,
                surface_boundary_present,
                surface_boundary_clean,
                surface_boundary_inputs,
                schema_version,
                require,
                candidate_above=candidate_above if transition_present and transition_clean else None,
                transition_inputs=transition_inputs if transition_present and transition_clean else None,
            )
        )
        if pressure_geometry_present:
            require(pressure_geometry_clean, "pressure geometry extension")
        dry_air_flux_present, dry_air_flux_clean, dry_air_flux_inputs = (
            read_dry_air_flux_extension(
                dataset,
                above.shape,
                pressure_analysis_candidate_present,
                schema7 or schema8,
                pressure_geometry_present,
                require,
            )
        )
        transition_replay = None
        if (transition_present and transition_clean and pressure_geometry_clean
                and radar_reconstruction_present and radar_reconstruction_clean):
            # Raw thermo contracts are checked below before acceptance. The
            # original-input replay is shared by Phi and thermo stage checks.
            for prefix in ("background", "candidate"):
                for species in THERMO_FIELDS:
                    name = f"{prefix}_{species}"
                    if name not in fields and name in dataset.variables:
                        fields[name] = values(dataset[name])
            transition_replay = build_pressure_transition_replay(
                dataset, fields, masks, pressure, pressure_mass, pressure_interface,
                pressure_geometry_inputs, transition_inputs, radar_reconstruction_inputs, require,
            )
        (
            pressure_geopotential_present,
            pressure_geopotential_clean,
            pressure_geopotential_changed,
        ) = (
            validate_pressure_geopotential_extension(
                dataset,
                above.shape,
                above,
                pressure,
                pressure_analysis_candidate_present,
                schema_version,
                global_valid_time,
                canonical_schema_version,
                surface_boundary_present,
                surface_boundary_clean,
                surface_boundary_inputs,
                require,
                transition_replay=transition_replay,
                transition_inputs=transition_inputs if transition_replay is not None else None,
            )
        )
        if transition_present and transition_replay is None:
            require(False, "pressure transition geopotential requires clean replay")
            pressure_geopotential_clean = False
        pressure_geostrophic_present, pressure_geostrophic_clean, pressure_geostrophic_support = (
            validate_pressure_geostrophic_extension(
                dataset,
                above.shape,
                above,
                latitude,
                fields,
                masks["candidate_balance_support"],
                pressure_geopotential_present,
                pressure_geopotential_clean,
                pressure_analysis_candidate_present,
                schema_version,
                float(getattr(dataset, "grid_dx_m")),
                float(getattr(dataset, "grid_dy_m")),
                require,
                transition_replay=transition_replay,
                transition_inputs=(
                    transition_inputs if transition_present else None
                ),
            )
        )
        if pressure_geostrophic_present:
            if getattr(dataset, "pressure_geostrophic_contract", "") in (
                PRESSURE_GEOSTROPHIC_V2_CONTRACT,
                PRESSURE_GEOSTROPHIC_V3_CONTRACT,
            ):
                pressure_geostrophic_requested_cells = exact_scalar_int32(
                    getattr(dataset, "pressure_geostrophic_requested_cells", None)
                )
                pressure_geostrophic_evaluated_cells = exact_scalar_int32(
                    getattr(dataset, "pressure_geostrophic_evaluated_cells", None)
                )
                partial_coverage = exact_scalar_int32(
                    getattr(dataset, "pressure_geostrophic_partial_coverage", None)
                )
                pressure_geostrophic_partial_coverage = (
                    None if partial_coverage is None else bool(partial_coverage)
                )
            elif pressure_geostrophic_support.shape == above.shape:
                pressure_geostrophic_requested_cells = int(
                    np.count_nonzero(pressure_geostrophic_support)
                )
                pressure_geostrophic_evaluated_cells = pressure_geostrophic_requested_cells
                pressure_geostrophic_partial_coverage = False
        omega_target_error_present, omega_target_error_clean, omega_target_error_inputs = (
            read_omega_target_error_extension(
                dataset,
                above.shape,
                above,
                global_valid_time,
                require,
            )
        )
        if canonical_schema_version in (4, 5):
            require(global_valid_time is not None, "canonical4/5 valid-time epoch")
            require(
                omega_target_error_present and omega_target_error_clean,
                "canonical4/5 omega target error group",
            )
        elif canonical_schema_version == 3:
            require(
                not omega_target_error_present,
                "canonical3 omega target error group is reserved",
            )
        thermo_changed = np.zeros(above.shape, dtype=bool)
        if schema6 or schema7 or schema8:
            thermo_changed = validate_thermo_extension(
                dataset,
                above,
                radar_no_echo,
                pressure,
                pressure_mass,
                dry_air_mass,
                fields,
                require,
                schema7 or schema8,
                candidate_pressure_mass=(
                    pressure_geometry_inputs.get("candidate_pressure_mass_measure")
                    if pressure_geometry_clean
                    else None
                ),
                variable_geometry=pressure_geometry_present,
                transition_replay=transition_replay,
            )
        if pressure_geometry_present and pressure_geometry_clean and not transition_present:
            candidate_pressure_mass = pressure_geometry_inputs[
                "candidate_pressure_mass_measure"
            ]
            candidate_dry_air_mass = pressure_geometry_inputs[
                "candidate_dry_air_mass_measure"
            ]
            validate_pressure_geometry_ledger(
                dataset,
                above,
                pressure_mass,
                dry_air_mass,
                candidate_pressure_mass,
                candidate_dry_air_mass,
                fields,
                require,
            )
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
        target_changed = masks["omega_target_valid"].copy()
        if pressure_analysis_candidate_present and pressure_analysis_candidate_inputs:
            target_changed = (
                changed_bits(
                    pressure_analysis_candidate_inputs["original_omega_target"],
                    fields["omega_target"],
                )
                | (
                    pressure_analysis_candidate_inputs["original_omega_target_valid"]
                    != masks["omega_target_valid"].astype(np.int32)
                )
                | (
                    pressure_analysis_candidate_inputs["original_omega_target_quality"]
                    != target_quality_raw
                )
                | (
                    pressure_analysis_candidate_inputs["original_omega_target_source"]
                    != target_source_raw
                )
            )
        target_authority = (
            masks["omega_target_valid"]
            & quality_known
            & source_known
            & (target_metadata_source > 0)
            & ((target_metadata_source & SOURCE_DYNAMIC_TARGET) != 0)
            & ((target_metadata_source & SOURCE_DYNAMIC_EVIDENCE_BITS) != 0)
            & ((target_metadata_source & SOURCE_MANUFACTURED_TEST) == 0)
            & ((target_quality & QUALITY_DYNAMIC_TARGET_EXCLUDED_BITS) == 0)
        )
        if pressure_analysis_candidate_present and pressure_analysis_candidate_inputs:
            original_source = pressure_analysis_candidate_inputs["original_omega_target_source"]
            original_quality = pressure_analysis_candidate_inputs["original_omega_target_quality"]
            original_authority = (
                pressure_analysis_candidate_inputs["original_omega_target_valid"].astype(bool)
                & ((original_source & SOURCE_DYNAMIC_TARGET) != 0)
                & ((original_source & SOURCE_DYNAMIC_EVIDENCE_BITS) != 0)
                & ((original_source & SOURCE_MANUFACTURED_TEST) == 0)
                & ((original_quality & QUALITY_DYNAMIC_TARGET_EXCLUDED_BITS) == 0)
            )
            # An unrelated hydrometeor change must not conceal alteration or
            # insertion of an observational target in the column-change mask.
            require(
                not np.any(target_changed & (original_authority | target_authority)),
                "observational target must equal immutable input",
            )
        if omega_target_error_present:
            if omega_target_error_inputs:
                sigma_valid = omega_target_error_inputs["omega_target_sigma_valid"].astype(bool)
                sigma_quality = omega_target_error_inputs["omega_target_sigma_quality"].astype(np.int64)
                sigma_source = omega_target_error_inputs["omega_target_sigma_source"].astype(np.int64)
                sigma_usable = (
                    sigma_valid
                    & (sigma_source > 0)
                    & ((sigma_quality & QUALITY_EXCLUDED_BITS) == 0)
                    & ((sigma_quality & QUALITY_DYNAMIC_TARGET_EXCLUDED_BITS) == 0)
                    & np.isfinite(omega_target_error_inputs["omega_target_sigma"])
                    & (omega_target_error_inputs["omega_target_sigma"] > 0.0)
                )
                computed_target_authority = (
                    above
                    & target_authority
                    & sigma_usable
                    & ((sigma_source & SOURCE_MANUFACTURED_TEST) == 0)
                    & (
                        (sigma_source & target_metadata_source & SOURCE_DYNAMIC_EVIDENCE_BITS)
                        != 0
                    )
                    & np.isfinite(fields["omega_target"])
                )
            else:
                computed_target_authority = np.zeros_like(masks["omega_target_authority"])
        else:
            # Schema-5/6/7/8 files predating the diagonal target-error group
            # remain readable as historical artifacts.  Preserve their legacy
            # authority predicate, but do not report the new contract.
            computed_target_authority = target_authority
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
                balance_background[component],
                fields[f"candidate_{component}"],
            )
        hydrometeor_changed = np.zeros(above.shape, dtype=bool)
        precipitation_changed = np.zeros(above.shape, dtype=bool)
        for species in HYDROMETEORS:
            before = fields[f"background_{species}"]
            after = fields[f"candidate_{species}"]
            column_after = after
            if transition_replay is not None:
                # The column stage ends before pressure remap. New-cell and
                # remap changes belong to the persisted geometry stage.
                column_after = np.where(above,
                    transition_replay["post_species"][THERMO_SPECIES.index(species)],
                    before).astype(np.float32)
            hydrometeor_changed |= changed_bits(before, column_after)
            if species in ("rain", "snow", "graupel"):
                precipitation_changed |= changed_bits(before, after)
            require(np.all(after[above] >= 0.0), f"candidate {species} nonnegative")
        if pressure_geopotential_changed.shape != above.shape:
            require(False, "pressure geopotential changed mask shape")
            pressure_geopotential_changed = np.zeros_like(above)
        column_changed = hydrometeor_changed | thermo_changed
        require(np.array_equal(balance_changed, masks["balance_changed"]), "balance changed mask")
        require(np.all(~column_changed | masks["column_changed"]), "column changed mask")
        if schema6 or schema7 or schema8:
            require(
                np.all(~radar_no_echo | ~precipitation_changed),
                "no-echo cells must not receive precipitation changes",
            )
        else:
            require(
                np.all(~radar_no_echo | ~column_changed),
                "no-echo cells must not receive hydrometeor changes",
            )
        column_change_evidence = (
            column_changed
            | target_changed
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
                masks["column_changed"] | masks["balance_changed"] | pressure_geopotential_changed,
                masks["overall_changed"],
            ),
            "overall changed mask",
        )
        require(np.all(~balance_changed | candidate_above), "balance below ground")

        minimum_beta = float(getattr(dataset, "minimum_balance_beta"))
        computed_active = candidate_above & (
            fields["balance_beta"].astype(np.float64) > float(np.float32(minimum_beta))
        )
        require(
            np.array_equal(computed_active, masks["candidate_balance_support"]),
            "candidate balance support",
        )

        target_innovation32 = fields["omega_target"] - balance_background["omega"]
        target_resolution = (
            16.0 * np.finfo(np.float32).eps
            * np.maximum(1.0, np.abs(balance_background["omega"]))
        )
        target_source = masks["omega_target_authority"] & (
            np.abs(target_innovation32) > target_resolution
        )
        expected_beta = reconstruct_beta(
            target_source,
            candidate_above,
            pressure,
            float(getattr(dataset, "grid_dx_m")),
            float(getattr(dataset, "grid_dy_m")),
            float(getattr(dataset, "horizontal_support_radius_m")),
            float(getattr(dataset, "pressure_support_radius_pa")),
        )
        beta_error = float(np.max(np.abs(expected_beta - fields["balance_beta"])))
        require(beta_error <= 5.0e-6, "localization kernel reconstruction")

        du = fields["candidate_u"].astype(np.float64) - balance_background["u"]
        dv = fields["candidate_v"].astype(np.float64) - balance_background["v"]
        domega = fields["candidate_omega"].astype(np.float64) - balance_background["omega"]
        accepted_target = np.where(target_source, target_innovation32, 0.0).astype(np.float64)
        if omega_target_error_present and omega_target_error_inputs:
            # The operator's response diagnostic is relative to the weighted
            # proposal q_requested, while target resolution above intentionally
            # remains the raw float32 innovation predicate.
            target_innovation64 = (
                fields["omega_target"].astype(np.float64)
                - balance_background["omega"].astype(np.float64)
            )
            prior_variance = (
                fields["balance_beta"].astype(np.float64)
                * float(getattr(dataset, "kappa_omega"))
            )
            sigma_value = omega_target_error_inputs["omega_target_sigma"].astype(np.float64)
            observation_variance = sigma_value * sigma_value
            denominator = prior_variance + observation_variance
            gain = np.zeros_like(prior_variance)
            np.divide(
                prior_variance,
                denominator,
                out=gain,
                where=denominator > 0.0,
            )
            accepted_target = np.where(
                target_source,
                gain * target_innovation64,
                0.0,
            )
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
        meaningful_target = target_source & masks["candidate_balance_support"]
        if omega_target_error_present and omega_target_error_inputs:
            meaningful_target &= (
                np.abs(accepted_target)
                > float(getattr(dataset, "operator_identity_tolerance"))
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
            if not np.any(target_source):
                require(
                    not np.any(masks["candidate_balance_support"]),
                    "no-target balance support",
                )
            require(not np.any(balance_changed), "no-target wind change")
        if pressure_analysis_candidate_present:
            require(
                not target_count or physical_input_boundaries,
                "pressure analysis dynamic target requires physical boundaries",
            )
        else:
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

        if dry_air_flux_present and dry_air_flux_clean:
            if candidate_dry_air_mass is None:
                require(False, "candidate dry-air mass for flux replay")
            else:
                try:
                    expected_dry_flux = {
                        "background_dry_air_flux_divergence": dry_air_flux_divergence(
                            fields["background_u"].astype(np.float64),
                            fields["background_v"].astype(np.float64),
                            fields["background_omega"].astype(np.float64),
                            omega_top_boundary,
                            omega_bottom_boundary,
                            original_balance_support,
                            above,
                            float(getattr(dataset, "grid_dx_m")),
                            float(getattr(dataset, "grid_dy_m")),
                            pressure,
                            pressure_interface,
                            cell_dp,
                            dry_air_mass,
                            pressure_mass,
                            return_roundoff=True,
                        ),
                        "candidate_dry_air_flux_divergence": dry_air_flux_divergence(
                            fields["candidate_u"].astype(np.float64),
                            fields["candidate_v"].astype(np.float64),
                            fields["candidate_omega"].astype(np.float64),
                            omega_top_boundary,
                            omega_bottom_boundary,
                            stage_balance_support,
                            candidate_above,
                            float(getattr(dataset, "grid_dx_m")),
                            float(getattr(dataset, "grid_dy_m")),
                            pressure,
                            (
                                pressure_geometry_inputs["candidate_pressure_interface"]
                                if pressure_geometry_clean
                                else pressure_interface
                            ),
                            (
                                pressure_geometry_inputs["candidate_cell_dp"]
                                if pressure_geometry_clean
                                else cell_dp
                            ),
                            candidate_dry_air_mass,
                            (
                                pressure_geometry_inputs["candidate_pressure_mass_measure"]
                                if pressure_geometry_clean
                                else pressure_mass
                            ),
                            return_roundoff=True,
                        ),
                    }
                except Exception as error:
                    require(False, f"independent dry-air flux replay: {type(error).__name__}")
                else:
                    replay_ok = True
                    for name, (expected, roundoff) in expected_dry_flux.items():
                        actual = dry_air_flux_inputs[name]
                        scale = np.maximum(1.0, np.maximum(np.abs(expected), np.abs(actual)))
                        tolerance = 1.0e-10 + 5.0e-12 * scale + roundoff
                        matches = (
                            np.all(np.isfinite(expected))
                            and np.all(np.isfinite(actual))
                            and np.all(np.isfinite(roundoff))
                            and np.all(np.abs(actual - expected) <= tolerance)
                        )
                        require(matches, f"independent {name}")
                        replay_ok &= bool(matches)
                    dry_air_flux_replay_ok = replay_ok

        residual_before = fields["continuity_background"].astype(np.float64)
        residual_after = fields["continuity_candidate"].astype(np.float64)
        stage_pressure_interface = (
            pressure_geometry_inputs["candidate_pressure_interface"]
            if pressure_geometry_clean
            else pressure_interface
        )
        stage_cell_dp = (
            pressure_geometry_inputs["candidate_cell_dp"]
            if pressure_geometry_clean
            else cell_dp
        )
        # Balance-stage before/after share candidate geometry. The original
        # background residual below is a separate original-geometry quantity.
        independent_before = continuity_state(
            balance_background["u"].astype(np.float64),
            balance_background["v"].astype(np.float64),
            balance_background["omega"].astype(np.float64),
            omega_top_boundary,
            omega_bottom_boundary,
            stage_balance_support,
            candidate_above,
            float(getattr(dataset, "grid_dx_m")),
            float(getattr(dataset, "grid_dy_m")),
            pressure,
            stage_pressure_interface,
            stage_cell_dp,
        )
        independent_after = continuity_state(
            fields["candidate_u"].astype(np.float64),
            fields["candidate_v"].astype(np.float64),
            fields["candidate_omega"].astype(np.float64),
            omega_top_boundary,
            omega_bottom_boundary,
            stage_balance_support,
            candidate_above,
            float(getattr(dataset, "grid_dx_m")),
            float(getattr(dataset, "grid_dy_m")),
            pressure,
            stage_pressure_interface,
            stage_cell_dp,
        )
        state_residual_error = max(
            float(np.max(np.abs(independent_before - residual_before))),
            float(np.max(np.abs(independent_after - residual_after))),
        )
        require(state_residual_error <= 1.0e-12, "full-state residual reconstruction")
        if pressure_geometry_present and pressure_geometry_clean:
            original_background = values(dataset["continuity_original_background"]).astype(
                np.float64
            )
            independent_original_background = continuity_state(
                fields["background_u"].astype(np.float64),
                fields["background_v"].astype(np.float64),
                fields["background_omega"].astype(np.float64),
                omega_top_boundary,
                omega_bottom_boundary,
                original_balance_support,
                above,
                float(getattr(dataset, "grid_dx_m")),
                float(getattr(dataset, "grid_dy_m")),
                pressure,
                pressure_interface,
                cell_dp,
            )
            require(
                original_background.shape == above.shape
                and np.all(np.abs(independent_original_background - original_background) <= 1.0e-12),
                "original background residual reconstruction",
            )
        residual_increment = residual_after - residual_before
        independent_increment = continuity_increment(
            du,
            dv,
            domega,
            stage_balance_support,
            float(getattr(dataset, "grid_dx_m")),
            float(getattr(dataset, "grid_dy_m")),
            pressure,
            stage_pressure_interface,
            stage_cell_dp,
            masks["omega_target_authority"],
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
            stage_pressure_interface,
            stage_cell_dp,
            masks["omega_target_authority"],
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

        if transition_replay is not None:
            transition_replay_errors = pressure_transition_replay_errors(
                dataset, fields, masks, pressure, pressure_mass, pressure_interface,
                pressure_geometry_inputs, transition_inputs, radar_reconstruction_inputs, require,
                replay=transition_replay,
            )
        elif not transition_present and radar_reconstruction_present and radar_reconstruction_clean:
            radar_reconstruction_replay_ok = validate_radar_reconstruction_reference(
                dataset,
                fields,
                masks,
                pressure,
                surface_pressure,
                radar_reconstruction_inputs,
                float(getattr(dataset, "column_minimum_dbz")),
                require,
            )
            radar_reconstruction_clean = radar_reconstruction_clean and radar_reconstruction_replay_ok

        if transition_present:
            # All component validators above must succeed. V1 is deliberately
            # exact at stored precision; it grants no generation/native/science
            # authority and does not turn a numerical probe into a candidate.
            transition_numerical_clean = bool(
                schema7 and transition_clean and transition_replay is not None
                and pressure_analysis_candidate_present and pressure_analysis_candidate_clean
                and surface_boundary_present and surface_boundary_clean
                and pressure_geometry_present and pressure_geometry_clean
                and radar_reconstruction_present and radar_reconstruction_clean
                and pressure_geopotential_present and pressure_geopotential_clean
                and pressure_geostrophic_present and pressure_geostrophic_clean
                and "numerical_test_probe" not in dataset.ncattrs()
                and transition_replay_is_exact(transition_replay_errors)
                and not failures
            )
            require(transition_numerical_clean,
                    "pressure transition requires complete exact stored-state replay")

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
            "canonical_schema_version": canonical_schema_version,
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
            "pressure_analysis_candidate_contract_present": pressure_analysis_candidate_present,
            "pressure_analysis_candidate_contract_validated": bool(
                pressure_analysis_candidate_present
                and pressure_analysis_candidate_clean
                and not failures
            ),
            "pressure_analysis_candidate_science_assessed": False,
            "pressure_analysis_candidate_promotion_eligible": False,
            "pressure_analysis_candidate_full_fixedpoint_independently_validated": False,
            "pressure_transition_replay_max_abs_errors": transition_replay_errors,
            "pressure_transition_replay_error_units": {
                "temperature": "K", "dry_air_mass": "kg dryair",
                **{name: "kg kg-1 dryair" for name in THERMO_SPECIES},
            },
            "pressure_transition_replay_criterion": "exact_stored_state_v1" if transition_present else None,
            "pressure_transition_physics_independently_validated": bool(
                transition_present and transition_numerical_clean and not failures
            ),
            "science_assessed": False,
            "promotion_eligible": False,
            "physical_continuity_assessed": False,
            "trajectory_science_decision": "BLOCKED_MISSING_STORM_MOTION",
            "dynamic_balance_decision": (
                "EVALUATED" if target_count else "NOT_AUTHORIZED"
            ),
            "valid_time_epoch": global_valid_time,
            "radar_cells": int(np.count_nonzero(radar)),
            "dynamic_target_cells": int(np.count_nonzero(target_source)),
            "column_changed_cells": int(np.count_nonzero(masks["column_changed"])),
            "hydrometeor_value_changed_cells": int(np.count_nonzero(hydrometeor_changed)),
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
            "analysis_ledger_validated": False,
            "dry_air_flux_independently_validated": bool(
                dry_air_flux_present
                and dry_air_flux_clean
                and dry_air_flux_replay_ok
                and not failures
            ),
            "dry_air_mass_continuity_assessed": False,
            "pressure_geopotential_independently_validated": bool(
                pressure_geopotential_present
                and pressure_geopotential_clean
                and not failures
            ),
            "pressure_geopotential_native_assessed": False,
            "pressure_geostrophic_independently_validated": bool(
                pressure_geostrophic_present
                and pressure_geostrophic_clean
                and not failures
            ),
            "pressure_geostrophic_science_assessed": False,
            "pressure_geostrophic_requested_cells": pressure_geostrophic_requested_cells,
            "pressure_geostrophic_evaluated_cells": pressure_geostrophic_evaluated_cells,
            "pressure_geostrophic_partial_coverage": pressure_geostrophic_partial_coverage,
            "omega_target_error_contract_present": omega_target_error_present,
            "omega_target_error_contract_validated": bool(
                omega_target_error_present and omega_target_error_clean and not failures
            ),
            "surface_boundary_contract_present": surface_boundary_present,
            "surface_boundary_validated": bool(
                surface_boundary_present and surface_boundary_clean and not failures
            ),
            "pressure_geometry_contract_present": pressure_geometry_present,
            "pressure_geometry_contract_validated": bool(
                pressure_geometry_present and pressure_geometry_clean and not failures
            ),
            "radar_reconstruction_independently_validated": False,
            "outer_lineage_validated": False,
            "outer_fixed_point_independently_validated": False,
            "outer_validation_scope": (
                "METADATA_ONLY_PRODUCER_REPLAY_NOT_REEXECUTED"
                if schema8 else "NONE"
            ),
        }
    summary["failures"] = failures
    summary["analysis_ledger_validated"] = bool((schema7 or schema8) and not failures)
    summary["dry_air_flux_independently_validated"] = bool(
        dry_air_flux_present
        and dry_air_flux_clean
        and dry_air_flux_replay_ok
        and not failures
    )
    summary["dry_air_mass_continuity_assessed"] = False
    summary["pressure_geopotential_independently_validated"] = bool(
        pressure_geopotential_present
        and pressure_geopotential_clean
        and not failures
    )
    # The persisted extension is a pressure-level increment replay only.  It
    # never establishes native geopotential or full-energy authority.
    summary["pressure_geopotential_native_assessed"] = False
    summary["pressure_geostrophic_independently_validated"] = bool(
        pressure_geostrophic_present
        and pressure_geostrophic_clean
        and not failures
    )
    summary["pressure_geostrophic_science_assessed"] = False
    summary["pressure_geostrophic_requested_cells"] = pressure_geostrophic_requested_cells
    summary["pressure_geostrophic_evaluated_cells"] = pressure_geostrophic_evaluated_cells
    summary["pressure_geostrophic_partial_coverage"] = pressure_geostrophic_partial_coverage
    summary["omega_target_error_contract_present"] = omega_target_error_present
    summary["omega_target_error_contract_validated"] = bool(
        omega_target_error_present and omega_target_error_clean and not failures
    )
    summary["surface_boundary_contract_present"] = surface_boundary_present
    summary["surface_boundary_validated"] = bool(
        surface_boundary_present and surface_boundary_clean and not failures
    )
    summary["pressure_geometry_contract_present"] = pressure_geometry_present
    summary["pressure_geometry_contract_validated"] = bool(
        pressure_geometry_present and pressure_geometry_clean and not failures
    )
    summary["pressure_analysis_candidate_contract_present"] = pressure_analysis_candidate_present
    summary["pressure_analysis_candidate_contract_validated"] = bool(
        pressure_analysis_candidate_present
        and pressure_analysis_candidate_clean
        and not failures
    )
    summary["pressure_analysis_candidate_science_assessed"] = False
    summary["pressure_analysis_candidate_promotion_eligible"] = False
    summary["pressure_analysis_candidate_full_fixedpoint_independently_validated"] = False
    summary["science_assessed"] = False
    summary["promotion_eligible"] = False
    summary["physical_continuity_assessed"] = False
    summary["radar_reconstruction_independently_validated"] = bool(
        schema8
        and radar_reconstruction_present
        and radar_reconstruction_clean
        and radar_reconstruction_replay_ok
        and not failures
    )
    summary["outer_lineage_validated"] = bool(schema8 and not failures)
    # Producer replay establishes lineage only; it is not an independent
    # full-operator fixed-point proof.
    summary["outer_fixed_point_independently_validated"] = False
    return summary, failures


def validate_snapshot(snapshot: Path) -> dict[str, object]:
    """Validate every diagnostic in one detached transaction snapshot."""
    if snapshot.is_symlink() or not snapshot.is_dir():
        raise ValueError("semantic validation snapshot is not a directory")
    snapshot = snapshot.resolve(strict=True)
    if snapshot.parent.name != ".snapshots":
        raise ValueError("semantic validation requires a detached snapshot")
    context = json.loads((snapshot / "TRANSACTION.json").read_text(encoding="utf-8"))
    products = context.get("products")
    if not isinstance(products, list) or not products or \
            not all(isinstance(item, str) and item for item in products):
        raise ValueError("snapshot transaction products are invalid")
    diagnostics = sorted(snapshot.glob("*.nc"))
    if not diagnostics:
        raise ValueError("snapshot has no SHADOW diagnostics")
    for diagnostic in diagnostics:
        report, failures = validate(diagnostic)
        if failures:
            raise ValueError(f"snapshot diagnostic failed validation: {diagnostic.name}")
        report_path = diagnostic.with_suffix(".json")
        try:
            stored = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"snapshot diagnostic report is invalid: {diagnostic.name}") from exc
        if stored != report:
            raise ValueError(f"snapshot diagnostic report differs: {diagnostic.name}")
    product_records = []
    for product in sorted(products):
        path = snapshot.joinpath(*Path(product).parts)
        if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
            raise ValueError(f"snapshot product is not an independent regular file: {product}")
        product_records.append({
            "path": product,
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        })
    return {
        "schema": 1,
        "status": "PASS",
        "transaction_id": snapshot.name,
        "snapshot_identity": [snapshot.stat().st_dev, snapshot.stat().st_ino],
        "validator": {
            "name": "validate_shadow_diagnostics",
            "source_sha256": sha256(Path(__file__)),
        },
        "products": product_records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("diagnostic", type=Path, nargs="?")
    parser.add_argument(
        "--snapshot", type=Path,
        help="validate every SHADOW diagnostic in this detached snapshot",
    )
    parser.add_argument("--json", type=Path, help="also write the JSON report")
    args = parser.parse_args()
    if args.snapshot is not None:
        if args.diagnostic is not None or args.json is not None:
            parser.error("--snapshot cannot be combined with diagnostic or --json")
        try:
            print(json.dumps(validate_snapshot(args.snapshot), sort_keys=True))
        except Exception as error:
            print(f"snapshot semantic validation rejected: {error}", file=sys.stderr)
            return 1
        return 0
    if args.diagnostic is None:
        parser.error("diagnostic is required unless --snapshot is used")
    try:
        summary, failures = validate(args.diagnostic)
    except Exception as error:
        failures = [f"{type(error).__name__}: {error}"]
        summary = {
            "path": args.diagnostic.name,
            "standalone_provenance": "UNBOUND_REQUIRES_COMMITTED_GENERATION",
            "validation_scope": "NUMERICAL_CONTENT_ONLY",
            "canonical_schema_version": None,
            "numerical_decision": "INVALID",
            "artifact_decision": "UNBOUND",
            "candidate_decision": "UNKNOWN",
            "pressure_analysis_candidate_contract_present": False,
            "pressure_analysis_candidate_contract_validated": False,
            "pressure_analysis_candidate_science_assessed": False,
            "pressure_analysis_candidate_promotion_eligible": False,
            "pressure_analysis_candidate_full_fixedpoint_independently_validated": False,
            "science_assessed": False,
            "promotion_eligible": False,
            "physical_continuity_assessed": False,
            "analysis_ledger_validated": False,
            "dry_air_flux_independently_validated": False,
            "dry_air_mass_continuity_assessed": False,
            "pressure_geopotential_independently_validated": False,
            "pressure_geopotential_native_assessed": False,
            "pressure_geostrophic_independently_validated": False,
            "pressure_geostrophic_science_assessed": False,
            "pressure_geostrophic_requested_cells": None,
            "pressure_geostrophic_evaluated_cells": None,
            "pressure_geostrophic_partial_coverage": None,
            "omega_target_error_contract_present": False,
            "omega_target_error_contract_validated": False,
            "surface_boundary_contract_present": False,
            "surface_boundary_validated": False,
            "pressure_geometry_contract_present": False,
            "pressure_geometry_contract_validated": False,
            "radar_reconstruction_independently_validated": False,
            "outer_lineage_validated": False,
            "outer_fixed_point_independently_validated": False,
            "outer_validation_scope": "NONE",
            "failures": failures,
        }
    report = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    if args.json:
        args.json.write_text(report, encoding="utf-8")
    print(report, end="")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
