#!/usr/bin/env python3
"""Independently read back the CP06-A thermodynamic density-prior state."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import numpy as np
from netCDF4 import Dataset


RD_AIR = 287.05
EPSILON_WATER = 0.622
GRAVITY = 9.80665
CP_DRY = 1004.5
SPECIES_CP = np.array([1846.4, 4190.0, 2106.0, 4190.0, 2106.0, 2106.0])
SPECIES_H0 = np.array([2.50e6, 0.0, -3.50e5, 0.0, -3.50e5, -3.50e5])
THERMO_T0 = 273.15
TEMP_MIN = 150.0
TEMP_MAX = 350.0
VAPOR_MAX = 0.2
LIQUID = 1
ICE = 2
CONTRACT = "cp06a_background_alpha_blend_v2"

FORCE_TOOL_PATH = Path(__file__).with_name("cp06a_state_force_flux.py")
SPEC = importlib.util.spec_from_file_location("cp06a_state_force_flux", FORCE_TOOL_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot import independent force/flux builder: {FORCE_TOOL_PATH}")
FORCE_TOOL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FORCE_TOOL)


def get(dataset: Dataset, name: str) -> np.ndarray:
    value = dataset.variables[name][:]
    if np.ma.isMaskedArray(value):
        value = value.filled(np.nan if np.issubdtype(value.dtype, np.floating) else 0)
    return np.asarray(value)


def require_variables(dataset: Dataset, names: tuple[str, ...], role: str) -> None:
    missing = [name for name in names if name not in dataset.variables]
    if missing:
        raise ValueError(f"{role} is missing required variables: {', '.join(missing)}")


def alpha(temperature: np.ndarray, vapor: np.ndarray,
          condensates: tuple[np.ndarray, ...]) -> np.ndarray:
    total_water = vapor.astype(np.float64, copy=True)
    for field in condensates:
        total_water += field.astype(np.float64)
    return RD_AIR * temperature * (1.0 + vapor / EPSILON_WATER) / (1.0 + total_water)


def saturation_mixing_ratio(temperature: float, pressure: float, surface: int) -> float:
    tc = temperature - 273.15
    if surface == ICE:
        es = 611.15 * np.exp(22.452 * tc / (temperature - 0.55))
    elif surface == LIQUID:
        es = 611.20 * np.exp(17.67 * tc / (tc + 243.5))
    else:
        raise ValueError(f"unsupported saturation surface code {surface}")
    es = min(0.99 * pressure, max(0.0, float(es)))
    return EPSILON_WATER * es / (pressure - es)


def saturated_alpha_root(pressure: float, target_alpha: float, condensate_sum: float,
                         surface: int, target_rh: float) -> tuple[float, float]:
    upper_temperature = min(TEMP_MAX, THERMO_T0 if surface == ICE else TEMP_MAX)

    def saturated_vapor(temperature: float) -> float:
        return target_rh * saturation_mixing_ratio(temperature, pressure, surface)

    if saturated_vapor(TEMP_MIN) > VAPOR_MAX:
        raise ValueError("background-alpha target has no saturated root in the canonical range")
    if saturated_vapor(upper_temperature) > VAPOR_MAX:
        low_vapor, high_vapor = TEMP_MIN, upper_temperature
        for _ in range(80):
            middle_vapor = low_vapor + 0.5 * (high_vapor - low_vapor)
            if saturated_vapor(middle_vapor) > VAPOR_MAX:
                high_vapor = middle_vapor
            else:
                low_vapor = middle_vapor
        upper_temperature = low_vapor

    def residual(temperature: float) -> float:
        vapor = saturated_vapor(temperature)
        return float(alpha(np.array(temperature), np.array(vapor),
                           (np.array(condensate_sum),))) - target_alpha

    low, high = TEMP_MIN, upper_temperature
    f_low, f_high = residual(low), residual(high)
    if f_low == 0.0:
        return low, saturated_vapor(low)
    if f_high == 0.0:
        return high, saturated_vapor(high)
    if f_low * f_high > 0.0:
        raise ValueError("background-alpha target has no saturated root in the canonical range")
    for _ in range(80):
        middle = low + 0.5 * (high - low)
        f_middle = residual(middle)
        if f_middle == 0.0 or middle == low or middle == high:
            low = high = middle
            break
        if f_middle > 0.0:
            high = middle
        else:
            low = middle
    temperature = low + 0.5 * (high - low)
    vapor = saturated_vapor(temperature)
    return temperature, vapor


def expected_thermodynamics(dataset: Dataset, background_weight: float) -> dict[str, Any]:
    pressure = get(dataset, "pressure").astype(np.float64)
    background_temperature = get(dataset, "background_temperature").astype(np.float64)
    background_vapor = get(dataset, "background_vapor").astype(np.float64)
    pre_temperature = get(dataset, "thermo_preprior_temperature").astype(np.float64)
    pre_vapor = get(dataset, "thermo_preprior_vapor").astype(np.float64)
    if pressure.ndim == 1:
        pressure = np.broadcast_to(pressure[:, None, None], pre_temperature.shape)
    analysis_support = get(dataset, "analysis_support") != 0
    thermo_support = get(dataset, "thermo_support") != 0
    surface = get(dataset, "thermo_surface").astype(np.int32)

    species_names = ("cloud_water", "cloud_ice", "rain", "snow", "graupel")
    background_condensates = tuple(get(dataset, f"background_{name}").astype(np.float64)
                                   for name in species_names)
    candidate_condensates = tuple(get(dataset, f"candidate_{name}").astype(np.float64)
                                  for name in species_names)
    preprior_condensates = preprior_condensate_fields(dataset, analysis_support, candidate_condensates)
    alpha_background = alpha(background_temperature, background_vapor, background_condensates)
    alpha_preprior = alpha(pre_temperature, pre_vapor, preprior_condensates)
    alpha_target = (background_weight * alpha_background +
                    (1.0 - background_weight) * alpha_preprior)
    target_rh = float(dataset.getncattr("thermo_target_rh"))

    condensate_sum = sum(candidate_condensates)
    if np.any(thermo_support & ~analysis_support):
        raise ValueError("thermo_support is not contained in analysis_support")
    if np.any(thermo_support & (surface != LIQUID) & (surface != ICE)):
        raise ValueError("thermo_support contains an unsupported saturation surface")
    expected_temperature = pre_temperature.copy()
    expected_vapor = pre_vapor.copy()
    phase_reservoir = np.zeros_like(pre_vapor)
    phase_reservoir[surface == LIQUID] = candidate_condensates[0][surface == LIQUID]
    phase_reservoir[surface == ICE] = candidate_condensates[1][surface == ICE]
    solve_saturation = np.zeros_like(thermo_support)
    fixed_vapor = analysis_support.copy()
    expected_temperature[fixed_vapor] = (
        alpha_target[fixed_vapor] *
        (1.0 + pre_vapor[fixed_vapor] + condensate_sum[fixed_vapor]) /
        (RD_AIR * (1.0 + pre_vapor[fixed_vapor] / EPSILON_WATER)))
    for k, j, i in zip(*np.where(thermo_support)):
        if phase_reservoir[k, j, i] > 0.0:
            solve_saturation[k, j, i] = True
            fixed_vapor[k, j, i] = False
        else:
            qsat = target_rh * saturation_mixing_ratio(
                float(expected_temperature[k, j, i]), float(pressure[k, j, i]), int(surface[k, j, i]))
            # An empty reservoir has no subsaturation equality. Retain qv and
            # solve alpha with T when feasible; only bind the saturation
            # inequality if that fixed-qv solution would be supersaturated.
            if pre_vapor[k, j, i] > qsat + 1.0e-11:
                solve_saturation[k, j, i] = True
                fixed_vapor[k, j, i] = False
    for k, j, i in zip(*np.where(solve_saturation)):
        expected_temperature[k, j, i], expected_vapor[k, j, i] = saturated_alpha_root(
            float(pressure[k, j, i]), float(alpha_target[k, j, i]),
            float(condensate_sum[k, j, i]), int(surface[k, j, i]), target_rh)

    if np.any((expected_temperature[analysis_support] < TEMP_MIN) |
              (expected_temperature[analysis_support] > TEMP_MAX)):
        raise ValueError("alpha-prior solution exceeds canonical temperature limits")
    if np.any((expected_vapor[analysis_support] < 0.0) |
              (expected_vapor[analysis_support] > VAPOR_MAX)):
        raise ValueError("alpha-prior solution exceeds canonical vapor limits")
    return {"alpha_background": alpha_background, "alpha_preprior": alpha_preprior,
            "alpha_target": alpha_target, "expected_temperature": expected_temperature,
            "expected_vapor": expected_vapor, "analysis_support": analysis_support,
            "thermo_support": thermo_support, "target_rh": target_rh,
            "preprior_condensates": preprior_condensates}


def preprior_condensate_fields(dataset: Dataset, support: np.ndarray,
                               final_condensates: tuple[np.ndarray, ...]) -> tuple[np.ndarray, ...]:
    """Read the fresh pre-prior snapshot and prove fixed condensates."""
    name = "thermo_preprior_condensates"
    if name not in dataset.variables:
        raise ValueError("candidate is missing the independent pre-prior condensate snapshot")
    snapshot = get(dataset, name).astype(np.float64)
    support_indices = tuple(zip(*np.where(support)))
    if snapshot.shape != (len(support_indices), 5):
        raise ValueError(f"{name} must have shape (analysis_support_cells, 5)")
    fields = [field.copy() for field in final_condensates]
    for row, index in enumerate(support_indices):
        for species, field in enumerate(fields):
            if snapshot[row, species] != field[index]:
                raise ValueError(f"condensate changed across density prior at {index}, species={species}")
            field[index] = snapshot[row, species]
    return tuple(fields)


def _max_abs(array: np.ndarray, mask: np.ndarray) -> float:
    return float(np.max(np.abs(array[mask]))) if np.any(mask) else 0.0


def _rms(array: np.ndarray, mask: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(array[mask])))) if np.any(mask) else 0.0


def v1_empty_reservoir_counterexample(dataset: Dataset, background_weight: float) -> dict[str, Any]:
    """Report the worst v1 fixed-qv supersaturation that motivated v2."""
    pressure = get(dataset, "pressure").astype(np.float64)
    source_is_preprior = "thermo_preprior_temperature" not in dataset.variables
    pre_temperature = get(dataset, "candidate_temperature" if source_is_preprior
                          else "thermo_preprior_temperature").astype(np.float64)
    pre_vapor = get(dataset, "candidate_vapor" if source_is_preprior
                    else "thermo_preprior_vapor").astype(np.float64)
    if pressure.ndim == 1:
        pressure = np.broadcast_to(pressure[:, None, None], pre_temperature.shape)
    surface = get(dataset, "thermo_surface").astype(np.int32)
    condensates = tuple(get(dataset, f"candidate_{name}").astype(np.float64)
                        for name in ("cloud_water", "cloud_ice", "rain", "snow", "graupel"))
    thermo_support = get(dataset, "thermo_support") != 0
    analysis_support = get(dataset, "analysis_support") != 0
    preprior_condensates = (preprior_condensate_fields(dataset, analysis_support, condensates)
                            if "thermo_preprior_condensates" in dataset.variables else condensates)
    phase_reservoir = np.zeros_like(pre_vapor)
    phase_reservoir[surface == LIQUID] = condensates[0][surface == LIQUID]
    phase_reservoir[surface == ICE] = condensates[1][surface == ICE]
    empty_thermo = thermo_support & (phase_reservoir == 0.0)
    if not np.any(empty_thermo):
        return {"v1_fixed_vapor_failure_found": False,
                "reason": "no thermo_support cells have an empty saturation reservoir"}

    background_temperature = get(dataset, "background_temperature").astype(np.float64)
    background_vapor = get(dataset, "background_vapor").astype(np.float64)
    background_condensates = tuple(get(dataset, f"background_{name}").astype(np.float64)
                                   for name in ("cloud_water", "cloud_ice", "rain", "snow", "graupel"))
    target_alpha = ((1.0 - background_weight) * alpha(pre_temperature, pre_vapor, preprior_condensates) +
                    background_weight * alpha(background_temperature, background_vapor,
                                              background_condensates))
    total_condensate = sum(condensates)
    fixed_vapor_temperature = (
        target_alpha * (1.0 + pre_vapor + total_condensate) /
        (RD_AIR * (1.0 + pre_vapor / EPSILON_WATER)))
    target_rh = float(dataset.getncattr("thermo_target_rh"))
    supersaturation = np.full_like(pre_vapor, -np.inf, dtype=np.float64)
    for k, j, i in zip(*np.where(empty_thermo)):
        qsat = target_rh * saturation_mixing_ratio(
            float(fixed_vapor_temperature[k, j, i]), float(pressure[k, j, i]), int(surface[k, j, i]))
        supersaturation[k, j, i] = pre_vapor[k, j, i] - qsat
    index = tuple(int(v) for v in np.unravel_index(int(np.argmax(supersaturation)), supersaturation.shape))
    k, j, i = index
    excess = float(supersaturation[index])
    float32_tolerance = float(np.finfo(np.float32).eps)
    qsat_stored_upper = target_rh * saturation_mixing_ratio(
        float(fixed_vapor_temperature[index] * (1.0 + float32_tolerance)),
        float(pressure[index]), int(surface[index]))
    closure_margin = 1.0e-11 + float32_tolerance * abs(float(pre_vapor[index]))
    return {"v1_fixed_vapor_failure_found": bool(excess > closure_margin),
            "preprior_source_kind": "candidate arrays in retained preprior NetCDF" if source_is_preprior
                                    else "thermo_preprior arrays in v2 candidate",
            "thermo_index_kji": [k, j, i],
            "pressure_pa": float(pressure[index]),
            "fixed_vapor_temperature_k": float(fixed_vapor_temperature[index]),
            "retained_vapor_kg_kg": float(pre_vapor[index]),
            "target_rh_saturation_vapor_kg_kg": float(
                target_rh * saturation_mixing_ratio(float(fixed_vapor_temperature[index]),
                                                    float(pressure[index]), int(surface[index]))),
            "supersaturation_excess_kg_kg": excess,
            "float32_closure_upper_kg_kg": float(qsat_stored_upper + closure_margin),
            "liquid_or_ice_reservoir_kg_kg": float(phase_reservoir[index]),
            "interpretation": "v1 fixed-qv alpha update violates the empty-reservoir supersaturation inequality; v2 binds the inequality only when needed"}


def _assert_close(name: str, actual: np.ndarray, expected: np.ndarray,
                  mask: np.ndarray, absolute_tolerance: float) -> float:
    delta = actual.astype(np.float64) - expected.astype(np.float64)
    maximum = _max_abs(delta, mask)
    if maximum > absolute_tolerance:
        raise ValueError(f"{name} max abs difference {maximum:.9g} exceeds {absolute_tolerance:.9g}")
    return maximum


def verify_saturation_closure(dataset: Dataset, actual_temperature: np.ndarray,
                              actual_vapor: np.ndarray, saturated: np.ndarray) -> None:
    pressure = get(dataset, "pressure").astype(np.float64)
    if pressure.ndim == 1:
        pressure = np.broadcast_to(pressure[:, None, None], actual_temperature.shape)
    surface = get(dataset, "thermo_surface").astype(np.int32)
    target_rh = float(dataset.getncattr("thermo_target_rh"))
    tolerance = np.finfo(np.float32).eps
    for k, j, i in zip(*np.where(saturated)):
        t = float(actual_temperature[k, j, i])
        p = float(pressure[k, j, i])
        q = float(actual_vapor[k, j, i])
        surface_code = int(surface[k, j, i])
        q_lower = target_rh * saturation_mixing_ratio(t * (1.0 - tolerance), p, surface_code)
        q_upper = target_rh * saturation_mixing_ratio(t * (1.0 + tolerance), p, surface_code)
        vapor_error = 1.0e-11 + tolerance * abs(q)
        if q > q_upper + vapor_error:
            raise ValueError(f"saturation closure is supersaturated at {(k, j, i)}")
        reservoir_name = "candidate_cloud_water" if surface_code == LIQUID else "candidate_cloud_ice"
        reservoir = float(get(dataset, reservoir_name)[k, j, i])
        if reservoir > 0.0 and q < q_lower - vapor_error:
            raise ValueError(f"saturation closure is subsaturated with available condensate at {(k, j, i)}")


def _assert_same_variable(source: Dataset, candidate: Dataset, name: str) -> None:
    if name not in source.variables or name not in candidate.variables:
        raise ValueError(f"source/candidate observation field {name} is missing")
    left, right = get(source, name), get(candidate, name)
    if left.shape != right.shape or not np.array_equal(left, right, equal_nan=True):
        raise ValueError(f"observation/provenance field changed: {name}")


def _attribute_value(dataset: Dataset, name: str) -> Any:
    if name not in dataset.ncattrs():
        raise ValueError(f"missing required global attribute {name}")
    value = dataset.getncattr(name)
    if isinstance(value, np.ndarray):
        return value
    return value


def phase_ledger_summary(candidate: Dataset) -> dict[str, Any]:
    names = ("thermo_contract", "thermo_target_rh", "thermo_species_change_kg",
             "thermo_sensible_change_j", "thermo_phase_change_j",
             "thermo_water_error_kg", "thermo_enthalpy_error_j")
    values: dict[str, Any] = {}
    for name in names:
        after = _attribute_value(candidate, name)
        values[name] = np.asarray(after).tolist() if isinstance(after, np.ndarray) else after
    return {"validation_scope": "producer-replayed internal saturation ledger; not independently recomputed here",
            "values": values}


def compare_persisted_budget(candidate: Dataset, calculated: dict[str, Any]) -> dict[str, float]:
    contract = str(_attribute_value(candidate, "thermo_density_analysis_contract"))
    if contract != "signed_represented_mixture_endpoint_v2":
        raise ValueError(f"unexpected density-analysis endpoint contract {contract!r}")
    persisted_names = {
        "species_change_kg": "thermo_density_analysis_species_change_kg",
        "mixing_ratio_change_kg": "thermo_density_analysis_mixing_ratio_change_kg",
        "dry_mass_redistribution_kg": "thermo_density_analysis_dry_mass_redistribution_kg",
        "species_arithmetic_scale_kg": "thermo_density_analysis_species_arithmetic_scale_kg",
        "dry_air_change_kg": "thermo_density_analysis_dry_air_change_kg",
        "enthalpy_change_j": "thermo_density_analysis_enthalpy_change_j",
        "geometry_mass_change_kg": "thermo_density_analysis_geometry_mass_change_kg",
        "enthalpy_composition_change_j": "thermo_density_analysis_enthalpy_composition_change_j",
        "enthalpy_mass_metric_change_j": "thermo_density_analysis_enthalpy_mass_metric_change_j",
        "enthalpy_arithmetic_scale_j": "thermo_density_analysis_enthalpy_arithmetic_scale_j",
        "total_mass_error_kg": "thermo_density_analysis_total_mass_error_kg",
        "max_cell_mass_error_kg": "thermo_density_analysis_max_cell_mass_error_kg",
        "accounted_cells": "thermo_density_analysis_accounted_cells",
        "incomplete_background_cells": "thermo_density_analysis_incomplete_background_cells",
        "incomplete_candidate_cells": "thermo_density_analysis_incomplete_candidate_cells",
    }
    differences = {}
    for key, attribute in persisted_names.items():
        stored = np.asarray(_attribute_value(candidate, attribute), dtype=np.float64)
        expected = np.asarray(calculated[key], dtype=np.float64)
        if stored.shape != expected.shape:
            raise ValueError(f"persisted density-analysis budget shape mismatch: {attribute}")
        difference = np.abs(stored - expected)
        scale = np.maximum(1.0, np.abs(expected))
        tolerance = 5.0e-9 * scale + (2.0e-5 if key == "total_mass_error_kg" else 1.0e-7)
        if np.any(difference > tolerance):
            raise ValueError(f"persisted density-analysis budget differs from independent calculation: {attribute}")
        differences[key] = float(np.max(difference)) if difference.size else 0.0
    return differences


def endpoint_budget(pre_temperature: np.ndarray, pre_vapor: np.ndarray,
                    final_temperature: np.ndarray, final_vapor: np.ndarray,
                    condensates_before: tuple[np.ndarray, ...],
                    condensates_after: tuple[np.ndarray, ...],
                    pre_dry_mass_measure: np.ndarray, final_dry_mass_measure: np.ndarray,
                    support: np.ndarray, above_ground: np.ndarray,
                    pre_geometry_mass_measure: np.ndarray | None = None,
                    final_geometry_mass_measure: np.ndarray | None = None,
                    candidate_valid: tuple[np.ndarray, ...] | None = None) -> dict[str, Any]:
    """Replay account_pressure_analysis in its k,j,i order over the full domain.

    Pre/post dry mass measures are persisted state, not reconstructed on the
    analysis mask. The prior's pre-state mass witness overrides the final
    candidate measure on support; outside support the producer guarantees
    the measure and state were restored unchanged.
    """
    before_fields = (pre_vapor, *condensates_before)
    after_fields = (final_vapor, *condensates_after)
    shape = np.shape(pre_temperature)
    if len(before_fields) != 6 or len(after_fields) != 6:
        raise ValueError("endpoint budget requires vapor and five condensate species")
    if any(np.shape(field) != shape for field in (*before_fields, *after_fields,
                                                   pre_dry_mass_measure, final_dry_mass_measure,
                                                   support, above_ground)):
        raise ValueError("endpoint budget arrays have inconsistent shapes")
    before_mass = np.asarray(final_dry_mass_measure, dtype=np.float64).copy()
    before_mass[support] = np.asarray(pre_dry_mass_measure, dtype=np.float64)[support]
    after_mass = np.asarray(final_dry_mass_measure, dtype=np.float64)
    if pre_geometry_mass_measure is None:
        geometry_change = np.zeros(shape, dtype=np.float64)
    elif final_geometry_mass_measure is None:
        raise ValueError("final geometry mass measure is required with the pre-state measure")
    else:
        geometry_change = (np.asarray(final_geometry_mass_measure, dtype=np.float64) -
                           np.asarray(pre_geometry_mass_measure, dtype=np.float64))

    species_change = np.zeros(6, dtype=np.float64)
    mixing_change = np.zeros(6, dtype=np.float64)
    redistribution = np.zeros(6, dtype=np.float64)
    species_arithmetic_scale = np.zeros(6, dtype=np.float64)
    dry_air_change = 0.0
    enthalpy = 0.0
    enthalpy_composition = 0.0
    enthalpy_mass = 0.0
    enthalpy_arithmetic_scale = 0.0
    geometry_mass_change = 0.0
    max_cell_mass_error = 0.0
    incomplete = 0
    nz, ny, nx = shape
    # Fortran account_pressure_analysis traverses k outer, j middle, i inner.
    for k in range(nz):
        for j in range(ny):
            for i in range(nx):
                if not above_ground[k, j, i]:
                    continue
                before = np.array([field[k, j, i] for field in before_fields], dtype=np.float64)
                after = np.array([field[k, j, i] for field in after_fields], dtype=np.float64)
                mb = float(before_mass[k, j, i])
                ma = float(after_mass[k, j, i])
                hb = float((CP_DRY + np.sum(SPECIES_CP * before)) *
                           (float(pre_temperature[k, j, i]) - THERMO_T0) + np.sum(SPECIES_H0 * before))
                ha = float((CP_DRY + np.sum(SPECIES_CP * after)) *
                           (float(final_temperature[k, j, i]) - THERMO_T0) + np.sum(SPECIES_H0 * after))
                dm = ma - mb
                change = ma * after - mb * before
                cell_geometry_change = float(geometry_change[k, j, i])
                geometry_mass_change += cell_geometry_change
                species_change += change
                mixing_change += mb * (after - before)
                redistribution += dm * after
                species_arithmetic_scale += (np.abs(ma * after) + np.abs(mb * before) +
                                             np.abs(mb * (after - before)) + np.abs(dm * after))
                dry_air_change += dm
                enthalpy += ma * ha - mb * hb
                enthalpy_composition += mb * (ha - hb)
                enthalpy_mass += dm * ha
                enthalpy_arithmetic_scale += (abs(ma * ha) + abs(mb * hb) +
                                              abs(mb * (ha - hb)) + abs(dm * ha))
                max_cell_mass_error = max(max_cell_mass_error,
                                          abs(dm + float(np.sum(change)) - cell_geometry_change))
    if candidate_valid is not None:
        complete = np.logical_and.reduce(tuple(np.asarray(field) != 0 for field in candidate_valid))
        incomplete = int(np.count_nonzero(above_ground & ~complete))
    return {"support_cells": int(np.count_nonzero(support)),
            "species_change_kg": species_change.tolist(),
            "mixing_ratio_change_kg": mixing_change.tolist(),
            "dry_mass_redistribution_kg": redistribution.tolist(),
            "species_arithmetic_scale_kg": species_arithmetic_scale.tolist(),
            "dry_air_change_kg": dry_air_change,
            "enthalpy_change_j": enthalpy,
            "geometry_mass_change_kg": geometry_mass_change,
            "enthalpy_composition_change_j": enthalpy_composition,
            "enthalpy_mass_metric_change_j": enthalpy_mass,
            "enthalpy_arithmetic_scale_j": enthalpy_arithmetic_scale,
            "total_mass_error_kg": float(dry_air_change + np.sum(species_change) - geometry_mass_change),
            "max_cell_mass_error_kg": max_cell_mass_error,
            "accounted_cells": int(np.count_nonzero(above_ground)),
            "incomplete_background_cells": incomplete,
            "incomplete_candidate_cells": incomplete,
            "enthalpy_split_error_j": enthalpy - enthalpy_composition - enthalpy_mass}


def compare_preprior_source(source: Dataset, candidate: Dataset,
                            analysis_support: np.ndarray) -> dict[str, Any]:
    require_variables(candidate, ("thermo_preprior_temperature", "thermo_preprior_vapor",
                                  "thermo_preprior_condensates",
                                  "thermo_preprior_dry_air_mass_measure"), "candidate pre-prior snapshot")
    snapshot = get(candidate, "thermo_preprior_condensates")
    if snapshot.shape != (int(np.count_nonzero(analysis_support)), 5):
        raise ValueError("pre-prior condensate snapshot does not match analysis_support order/size")

    observation_names = (
        "radar_dbz", "radar_valid", "radar_coverage", "radar_no_echo", "radar_missing",
        "background_precipitation_phase", "background_precipitation_phase_valid",
        "background_precipitation_phase_quality", "background_precipitation_phase_source",
        "background_cloud_fraction", "background_cloud_fraction_valid",
        "background_cloud_fraction_quality", "background_cloud_fraction_source",
        "background_cloud_type", "background_cloud_type_valid",
        "background_cloud_type_quality", "background_cloud_type_source",
        "omega_target", "omega_target_valid", "omega_target_quality", "omega_target_source",
        "omega_target_authority", "omega_target_sigma", "omega_target_sigma_valid",
        "omega_target_sigma_quality", "omega_target_sigma_source", "original_omega_target",
        "original_omega_target_valid", "original_omega_target_quality", "original_omega_target_source",
        "original_omega_target_sigma", "original_omega_target_sigma_valid",
        "original_omega_target_sigma_quality", "original_omega_target_sigma_source",
    )
    for name in observation_names:
        _assert_same_variable(source, candidate, name)
    return {"preprior_temperature_cells_saved": int(np.count_nonzero(analysis_support)),
            "preprior_vapor_cells_saved": int(np.count_nonzero(analysis_support)),
            "preprior_condensate_values_saved": int(snapshot.size),
            "preprior_dry_air_mass_values_saved": int(np.count_nonzero(analysis_support)),
            "observation_and_phase_observation_metadata_bitwise_equal_to_retained_source": True,
            "preprior_thermodynamics_compared_to_old_candidate": False,
            "reason": "outer feedback rederives the immediate pre-prior state for this candidate"}


def thermo_density_report(candidate_path: Path, preprior_path: Path) -> dict[str, Any]:
    metadata_names = (
        "pressure", "pressure_interface", "cell_dp", "level_spacing_dp", "pressure_mass_measure",
        "above_ground", "analysis_support", "thermo_support", "thermo_surface",
        "background_temperature", "background_vapor", "background_cloud_water",
        "background_cloud_ice", "background_rain", "background_snow", "background_graupel",
        "candidate_temperature", "candidate_vapor", "candidate_cloud_water", "candidate_cloud_ice",
        "candidate_rain", "candidate_snow", "candidate_graupel",
        "candidate_dry_air_mass_measure", "thermo_preprior_temperature", "thermo_preprior_vapor",
        "thermo_preprior_condensates", "thermo_preprior_dry_air_mass_measure",
        "pre_force_u", "pre_force_v")
    with Dataset(candidate_path) as candidate, Dataset(preprior_path) as source:
        require_variables(candidate, metadata_names, "candidate")
        condensate_snapshot = candidate.variables["thermo_preprior_condensates"]
        if str(_attribute_value(condensate_snapshot, "units")) != "kg kg-1 dryair":
            raise ValueError("pre-prior condensate snapshot has unexpected units")
        if str(_attribute_value(condensate_snapshot, "species_order")) != \
                "cloud_water,cloud_ice,rain,snow,graupel":
            raise ValueError("pre-prior condensate snapshot species order differs from the contract")
        if str(_attribute_value(condensate_snapshot, "cell_order")) != \
                "analysis_support:k,j,i;i_fastest":
            raise ValueError("pre-prior condensate snapshot cell order differs from the contract")
        if str(_attribute_value(candidate.variables["thermo_preprior_temperature"], "units")) != "K":
            raise ValueError("pre-prior temperature snapshot has unexpected units")
        if str(_attribute_value(candidate.variables["thermo_preprior_vapor"], "units")) != \
                "kg kg-1 dryair":
            raise ValueError("pre-prior vapor snapshot has unexpected units")
        dry_mass_snapshot = candidate.variables["thermo_preprior_dry_air_mass_measure"]
        if str(_attribute_value(dry_mass_snapshot, "units")) != "kg":
            raise ValueError("pre-prior dry-air mass snapshot has unexpected units")
        if str(_attribute_value(dry_mass_snapshot, "cell_order")) != \
                "analysis_support:k,j,i;i_fastest":
            raise ValueError("pre-prior dry-air mass snapshot cell order differs from the contract")
        prior_contract = str(_attribute_value(candidate, "thermo_density_prior_contract"))
        if prior_contract != CONTRACT:
            raise ValueError(f"unexpected thermodynamic density prior contract {prior_contract!r}")
        if ("thermo_density_prior_enabled" in candidate.ncattrs() and
                int(candidate.getncattr("thermo_density_prior_enabled")) != 1):
            raise ValueError("candidate records the density prior as disabled")
        if int(_attribute_value(candidate, "thermo_density_prior_observation_covariance_assessed")) != 0:
            raise ValueError("density prior must remain explicitly uncalibrated")
        background_weight = float(_attribute_value(candidate, "thermo_density_prior_background_weight"))
        if background_weight != 0.5:
            raise ValueError(f"expected predeclared equal alpha blend weight 0.5, got {background_weight}")
        max_temperature = float(_attribute_value(candidate, "thermo_density_prior_max_temperature_increment_k"))
        max_vapor = float(_attribute_value(candidate, "thermo_density_prior_max_vapor_increment_kg_kg"))
        if max_temperature != 5.0 or max_vapor != 0.005:
            raise ValueError("candidate cap attributes differ from declared 5 K / 0.005 kg kg-1 research caps")
        if str(_attribute_value(candidate, "force_prior_contract")) != \
                "cp06a_background_geostrophic_force_prior_v1":
            raise ValueError("candidate is missing the retained force-prior contract")
        force_status = int(_attribute_value(candidate, "force_prior_status"))
        force_reason = int(_attribute_value(candidate, "force_prior_reason"))
        if force_status != 20 or force_reason != 0:
            raise ValueError("candidate force-prior receipt is not an accepted status/reason")
        backtracking_steps = int(_attribute_value(candidate, "force_prior_backtracking_steps"))
        if not 0 <= backtracking_steps <= 20:
            raise ValueError("force-prior backtracking count is outside the declared 0..20 range")
        solver_residual_fraction = float(_attribute_value(candidate, "solver_residual_fraction"))
        if not np.isfinite(solver_residual_fraction):
            raise ValueError("candidate solver residual fraction is nonfinite")

        actual_temperature = get(candidate, "candidate_temperature").astype(np.float64)
        actual_vapor = get(candidate, "candidate_vapor").astype(np.float64)
        pre_temperature = get(candidate, "thermo_preprior_temperature").astype(np.float64)
        pre_vapor = get(candidate, "thermo_preprior_vapor").astype(np.float64)
        expected = expected_thermodynamics(candidate, background_weight)
        support = expected["analysis_support"]
        thermo = expected["thermo_support"]
        if not np.any(support) or not np.any(thermo):
            raise ValueError("candidate density prior support is empty")
        if not np.array_equal(get(candidate, "analysis_support"), get(source, "analysis_support")):
            raise ValueError("analysis_support changed from retained preprior source")
        if not np.array_equal(get(candidate, "thermo_support"), get(source, "thermo_support")):
            raise ValueError("thermo_support changed from retained preprior source")
        if not np.array_equal(get(candidate, "thermo_surface"), get(source, "thermo_surface")):
            raise ValueError("thermo_surface changed from retained preprior source")
        if not np.array_equal(get(candidate, "above_ground"), get(source, "above_ground")):
            raise ValueError("above_ground geometry changed from retained preprior source")
        for name in ("pressure", "pressure_interface", "cell_dp", "level_spacing_dp", "pressure_mass_measure"):
            if not np.array_equal(get(candidate, name), get(source, name)):
                raise ValueError(f"pressure geometry changed from retained preprior source: {name}")

        preprior_check = compare_preprior_source(source, candidate, support)
        v1_counterexample = v1_empty_reservoir_counterexample(candidate, background_weight)
        expected_temperature = expected["expected_temperature"]
        expected_vapor = expected["expected_vapor"]
        # Allow only the rounding needed to store the independently solved state as REAL32.
        temperature_tolerance = 4.0 * np.finfo(np.float32).eps * np.maximum(1.0, np.abs(expected_temperature))
        vapor_tolerance = 4.0 * np.finfo(np.float32).eps * np.maximum(1.0, np.abs(expected_vapor))
        temperature_error = np.abs(actual_temperature - expected_temperature)
        vapor_error = np.abs(actual_vapor - expected_vapor)
        if np.any(temperature_error[support] > temperature_tolerance[support]):
            raise ValueError("candidate temperature does not match independent alpha/saturation solution")
        if np.any(vapor_error[support] > vapor_tolerance[support]):
            raise ValueError("candidate vapor does not match independent alpha/saturation solution")
        outside = ~support
        if not np.array_equal(actual_temperature[outside], pre_temperature[outside]):
            raise ValueError("temperature changed outside analysis_support")
        if not np.array_equal(actual_vapor[outside], pre_vapor[outside]):
            raise ValueError("vapor changed outside analysis_support")
        temperature_increment = np.abs(actual_temperature - pre_temperature)
        vapor_increment = np.abs(actual_vapor - pre_vapor)
        if np.any(temperature_increment[support] > max_temperature + 2.0e-5):
            raise ValueError("temperature increment exceeds the configured research cap")
        if np.any(vapor_increment[support] > max_vapor + 2.0e-8):
            raise ValueError("vapor increment exceeds the configured research cap")

        condensates = tuple(get(candidate, f"candidate_{name}").astype(np.float64)
                            for name in ("cloud_water", "cloud_ice", "rain", "snow", "graupel"))
        above_ground = get(candidate, "above_ground") != 0
        candidate_valid = tuple(get(candidate, f"candidate_{name}_valid")
                                for name in ("vapor", "cloud_water", "cloud_ice", "rain", "snow", "graupel"))
        final_alpha = alpha(actual_temperature, actual_vapor, condensates)
        alpha_error = final_alpha - expected["alpha_target"]
        alpha_tolerance = 8.0 * np.finfo(np.float32).eps * np.maximum(1.0, np.abs(expected["alpha_target"]))
        if np.any(np.abs(alpha_error[support]) > alpha_tolerance[support]):
            raise ValueError("candidate mixture alpha does not match declared background/preprior blend")
        verify_saturation_closure(candidate, actual_temperature, actual_vapor, thermo)

        phase_ledger = phase_ledger_summary(candidate)
        condensates_before = expected["preprior_condensates"]
        final_dry_mass = get(candidate, "candidate_dry_air_mass_measure").astype(np.float64)
        pre_dry_mass = final_dry_mass.copy()
        dry_mass_values = get(candidate, "thermo_preprior_dry_air_mass_measure").astype(np.float64)
        support_indices = tuple(zip(*np.where(support)))
        if dry_mass_values.shape != (len(support_indices),):
            raise ValueError("pre-prior dry-air mass snapshot does not match analysis_support order/size")
        for row, index in enumerate(support_indices):
            pre_dry_mass[index] = dry_mass_values[row]
        thermodynamic_budget = endpoint_budget(
            pre_temperature, pre_vapor, actual_temperature, actual_vapor,
            condensates_before, condensates, pre_dry_mass, final_dry_mass,
            support, above_ground, candidate_valid=candidate_valid)
        persisted_budget_differences = compare_persisted_budget(candidate, thermodynamic_budget)
        # Force and flux are recalculated from persisted state and geometry by the existing independent builder.
        force_mask = get(candidate, "geostrophic_validation_support") != 0
        if not np.array_equal(force_mask, get(source, "geostrophic_validation_support") != 0):
            raise ValueError("geostrophic 900-cell mask differs from retained source mask")
        if int(np.count_nonzero(force_mask)) != 900:
            raise ValueError("geostrophic validation mask is not the retained 900-cell mask")
        force_background, count_background = FORCE_TOOL.geostrophic_rms(candidate, "background", force_mask)
        force_candidate, count_candidate = FORCE_TOOL.geostrophic_rms(candidate, "candidate", force_mask)
        if count_background != 900 or count_candidate != 900:
            raise ValueError("fixed force mask lost geostrophic coverage")
        pre_force_rms, pre_force_count = FORCE_TOOL.geostrophic_rms(
            candidate, "candidate", force_mask,
            (get(candidate, "pre_force_u"), get(candidate, "pre_force_v")))
        if pre_force_count != 900:
            raise ValueError("fixed force mask lost pre-refinement geostrophic coverage")
        stored_force_input = float(_attribute_value(candidate, "force_prior_input_rms"))
        stored_force_candidate = float(_attribute_value(candidate, "force_prior_candidate_rms"))
        stored_objective_input = float(_attribute_value(candidate, "force_prior_input_objective"))
        stored_objective_candidate = float(_attribute_value(candidate, "force_prior_candidate_objective"))
        if not np.isfinite(stored_objective_input) or not np.isfinite(stored_objective_candidate) or \
                stored_objective_candidate >= stored_objective_input:
            raise ValueError("accepted force-prior objective did not strictly decrease")
        force_rms_tolerance = 5.0e-9 * max(1.0, abs(force_candidate)) + 1.0e-12
        if abs(force_candidate - stored_force_candidate) > force_rms_tolerance or \
                abs(pre_force_rms - stored_force_input) > force_rms_tolerance:
            raise ValueError("stored force-prior RMS receipt differs from independent fixed-mask result")
        background_flux = FORCE_TOOL.independent_flux(candidate, "background")
        candidate_flux = FORCE_TOOL.independent_flux(candidate, "candidate")
        volume = get(candidate, "pressure_mass_measure").astype(np.float64)
        shell = get(candidate, "background_validation_shell") != 0
        control = get(candidate, "background_control_support") != 0
        if not np.array_equal(shell, get(source, "background_validation_shell") != 0):
            raise ValueError("980-cell continuity validation shell differs from retained source mask")
        if not np.array_equal(control, get(source, "background_control_support") != 0):
            raise ValueError("500-cell continuity control mask differs from retained source mask")
        continuity = {}
        for name, mask, expected_count in (("control_500", control, 500),
                                           ("validation_shell_980", shell, 980)):
            if int(np.count_nonzero(mask)) != expected_count:
                raise ValueError(f"{name} does not match the retained fixed support")
            before = FORCE_TOOL.dry_flux_norm(background_flux["divergence"], volume, mask)
            after = FORCE_TOOL.dry_flux_norm(candidate_flux["divergence"], volume, mask)
            prior_residual = FORCE_TOOL.dry_flux_norm(
                candidate_flux["divergence"] - background_flux["divergence"], volume, mask)
            continuity[name] = {"background_rms_s-1": before[0], "candidate_rms_s-1": after[0],
                                "candidate_minus_background_rms_s-1": prior_residual[0],
                                "candidate_minus_background_max_abs_s-1": prior_residual[1],
                                "cells": prior_residual[2]}
        shell_receipt = continuity["validation_shell_980"]
        for key, attribute in (("candidate_minus_background_rms_s-1",
                                "force_prior_continuity_candidate_rms"),
                               ("candidate_minus_background_max_abs_s-1",
                                "force_prior_continuity_candidate_max")):
            stored = float(_attribute_value(candidate, attribute))
            if abs(stored - shell_receipt[key]) > 1.0e-18:
                raise ValueError(f"persisted force-prior continuity receipt differs from independent result: {attribute}")

        return {"schema": "cp06a_thermo_density_readback_v1",
                "candidate": {"path": str(candidate_path),
                              "sha256": hashlib.sha256(candidate_path.read_bytes()).hexdigest()},
                "preprior_source": {"path": str(preprior_path),
                                    "sha256": hashlib.sha256(preprior_path.read_bytes()).hexdigest()},
                "contract": prior_contract,
                "v1_failure_preserved_as_diagnostic": v1_counterexample,
                "interpretation": {
                    "prior_type": "predeclared equal-weight background-alpha research control",
                    "observation_covariance_assessed": False,
                    "observation_fit_assessed": False,
                    "force_residual_is_source": False,
                    "science_pass": False,
                },
                "controls": {"background_alpha_weight": background_weight,
                             "max_temperature_increment_k": max_temperature,
                             "max_vapor_increment_kg_kg": max_vapor},
                "support": {"analysis_cells": int(np.count_nonzero(support)),
                            "saturation_cells": int(np.count_nonzero(thermo))},
                "independent_solution": {
                    "temperature_error_max_k": _max_abs(actual_temperature - expected_temperature, support),
                    "vapor_error_max_kg_kg": _max_abs(actual_vapor - expected_vapor, support),
                    "alpha_blend_error_max_m2_s2": _max_abs(alpha_error, support),
                    "alpha_blend_error_rms_m2_s2": _rms(alpha_error, support),
                    "temperature_increment_max_k": _max_abs(temperature_increment, support),
                    "vapor_increment_max_kg_kg": _max_abs(vapor_increment, support),
                    "warm_temperature_min_max_k": [float(np.min(actual_temperature[thermo])),
                                                     float(np.max(actual_temperature[thermo]))],
                    "warm_vapor_min_max_kg_kg": [float(np.min(actual_vapor[thermo])),
                                                  float(np.max(actual_vapor[thermo]))],
                },
                "retention": preprior_check,
                "density_budget_replay": {
                    "domain": "union of pre/post above_ground cells; this contract has unchanged geometry",
                    "traversal": "Fortran account_pressure_analysis order: k,j,i",
                    "preprior_dry_air_mass": (
                        "saved thermo_preprior_dry_air_mass_measure on analysis_support; "
                        "final candidate_dry_air_mass_measure outside support per producer restore contract"),
                    "candidate_dry_air_mass": "candidate_dry_air_mass_measure over the full domain",
                    "endpoint_residual_used_as_source": False,
                },
                "fixed_condensates": {
                    "snapshot_shape": list(get(candidate, "thermo_preprior_condensates").shape),
                    "snapshot_equal_to_final_in_analysis_support": True,
                    "condensates_are_prior_degrees_of_freedom": False,
                },
                "internal_saturation_phase_ledger": phase_ledger,
                "density_adjustment_analysis_budget": thermodynamic_budget,
                "persisted_budget_max_abs_difference": persisted_budget_differences,
                "independent_force": {"background_rms_m_s2": force_background,
                                      "candidate_rms_m_s2": force_candidate,
                                      "pre_refinement_rms_m_s2": pre_force_rms,
                                      "objective_input": stored_objective_input,
                                      "objective_candidate": stored_objective_candidate,
                                      "accepted_objective_strictly_decreased": True,
                                      "accepted_backtracking_halvings": backtracking_steps,
                                      "backtracking_halving_limit": 20,
                                      "force_prior_status": force_status,
                                      "force_prior_reason": force_reason,
                                      "pipeline_solver_residual_fraction": solver_residual_fraction,
                                      "wind_pressure_metadata_limit": (
                                          "force replay uses persisted pressure centers, geopotential, and "
                                          "co-located wind fields; no separate wind-pressure coordinate or "
                                          "wind observation covariance is stored"),
                                      "candidate_over_background": force_candidate / force_background
                                      if force_background > 0.0 else None,
                                      "fixed_mask_cells": 900,
                                      "builder": "tools/cp06a_state_force_flux.py"},
                "independent_continuity": continuity}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path, help="new writer output NetCDF")
    parser.add_argument("--preprior-source", required=True, type=Path,
                        help="same-case retained candidate before the density-prior stage")
    parser.add_argument("--output", type=Path, help="write JSON report to this path")
    args = parser.parse_args()
    result = thermo_density_report(args.candidate, args.preprior_source)
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
