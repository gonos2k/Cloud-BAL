#!/usr/bin/env python3
"""Create a copied WRF input with an explicit, source-bounded KDM6 PSD prior."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from netCDF4 import Dataset
import numpy as np

from hydrometeor_moments import validate_bulk_volume, validate_mass_number


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "docs/PR61_NATIVE_MOMENT_POLICY_20261006.json"
EXPECTED_POLICY_SHA256 = "20fd53ec626cbb4e192583f99777b5f7f56d580959171c240b804c38873517b3"
EXPECTED_INPUT_SHA256 = "397daf0387d522243167f5e48831f7415bea07f00c22e5674ef89f73db1a2c0c"
EXPECTED_TRACE_SHA256 = "aa01a611b81cf041961748a945e91b4d52aa6704c9fea4398ec7cbe9138139b2"
EXPECTED_VALID_TIME = "2026-08-16_12:00:00"
EXPECTED_TRACE_BOUNDS = {
    "ids": 1, "ide": 235, "jds": 1, "jde": 283, "kds": 1, "kde": 40,
    "ims": -4, "ime": 240, "jms": -4, "jme": 288, "kms": 1, "kme": 40,
    "its": 2, "ite": 233, "jts": 2, "jte": 281, "kts": 1, "kte": 39,
}
DIMENSIONS = ("Time", "bottom_top", "south_north", "west_east")
SPECIES = {
    "QCLOUD": {
        "moment": "QNCLOUD", "threshold": 1.0e-15, "lambda_min": 1.2e4,
        "lambda_max": 5.0e5, "power": 3, "pidn": math.pi * 1000.0 / 6.0,
        "internal_cap": 5.0e10,
        "m_min": 4.188790204786391e-15,
        "m_max": 3.0300855069345996e-10,
    },
    "QRAIN": {
        "moment": "QNRAIN", "threshold": 1.0e-9, "lambda_min": 961.0,
        "lambda_max": 3.5e4, "power": 3,
        "pidn": (math.pi * 1000.0 / 6.0) * math.gamma(5.0),
        "internal_cap": 5.0e7,
        "m_min": 2.930931921716425e-10,
        "m_max": 1.4159232106169906e-5,
    },
    "QICE": {
        "moment": "QNICE", "threshold": 1.0e-15, "lambda_min": 9080.0,
        "lambda_max": 1.82e6, "power": 3,
        "pidn": (math.pi * 500.0 / 6.0) * math.gamma(4.0),
        "internal_cap": 1.0e6,
        "m_min": 2.605587805918249e-16,
        "m_max": 2.098274638742861e-9,
    },
}
GRAUPEL = {
    "moment": "QIB", "threshold": 1.0e-9, "rho_center": 400.0,
    "rho_min": 100.0, "rho_max": 900.0,
}
UNCERTAINTY = (
    "Source-parameter admissibility envelope, not statistical sigma. Gamma PSD "
    "individual diameter support is unbounded; derived particle-mass limits "
    "describe the mean particle mass implied by lambda, not every particle."
)
BOUND_SOURCE = "Selected KDM6 source lambda bounds and source mass-size equations; policy docs/PR61_NATIVE_MOMENT_POLICY_20261006.json"
_SHA = set("0123456789abcdef")


class InitializationError(ValueError):
    """The source input cannot support this explicitly scoped prior."""


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def variable_sha256(variable: Any) -> str:
    data = np.asarray(variable[:])
    return hashlib.sha256(np.ascontiguousarray(data).tobytes()).hexdigest()


def _read_unmasked(variable: Any, name: str) -> np.ndarray:
    if variable.dimensions != DIMENSIONS:
        raise InitializationError(f"MALFORMED_DIMENSIONS:{name}")
    raw = variable[0]
    if np.any(np.ma.getmaskarray(raw)):
        raise InitializationError(f"MASKED_FIELD:{name}")
    values = np.asarray(raw)
    if not np.all(np.isfinite(values)):
        raise InitializationError(f"NONFINITE_FIELD:{name}")
    return values


def _check_policy_implementation(policy: dict[str, Any]) -> None:
    """Reject drift between the frozen policy and executable declarations."""
    policy_species = policy["species"]
    if set(policy_species) != set(SPECIES) | {"QGRAUP"}:
        raise InitializationError("POLICY_IMPLEMENTATION_MISMATCH:species_inventory")

    policy_fields = (
        ("moment", "target_moment"),
        ("threshold", "source_active_mass_threshold_kg_kg-1"),
        ("power", "shape_exponent_d"),
        ("lambda_min", "lambda_min_m-1"),
        ("lambda_max", "lambda_max_m-1"),
        ("internal_cap", "internal_number_cap_number_m-3"),
    )
    for mass_name, spec in SPECIES.items():
        declared = policy_species[mass_name]
        for code_field, policy_field in policy_fields:
            if spec[code_field] != declared[policy_field]:
                raise InitializationError(
                    f"POLICY_IMPLEMENTATION_MISMATCH:{mass_name}.{code_field}"
                )
        mean_mass_bounds = declared["particle_mean_mass_bounds_kg"]
        derived_bounds = (
            spec["pidn"] / spec["lambda_max"] ** spec["power"],
            spec["pidn"] / spec["lambda_min"] ** spec["power"],
        )
        for actual, expected, field in (
            (spec["m_min"], mean_mass_bounds[0], "m_min"),
            (spec["m_max"], mean_mass_bounds[1], "m_max"),
        ):
            if actual != expected:
                raise InitializationError(
                    f"POLICY_IMPLEMENTATION_MISMATCH:{mass_name}.{field}"
                )
        for actual, expected, field in (
            (derived_bounds[0], mean_mass_bounds[0], "pidn_min"),
            (derived_bounds[1], mean_mass_bounds[1], "pidn_max"),
        ):
            if not math.isclose(actual, expected, rel_tol=16 * sys.float_info.epsilon):
                raise InitializationError(
                    f"POLICY_IMPLEMENTATION_MISMATCH:{mass_name}.{field}"
                )

    declared_graupel = policy_species["QGRAUP"]
    graupel_fields = (
        ("moment", "target_moment"),
        ("threshold", "source_active_mass_threshold_kg_kg-1"),
        ("rho_center", "bulk_density_prior_center_kg_m-3"),
        ("rho_min", "bulk_density_min_kg_m-3"),
        ("rho_max", "bulk_density_max_kg_m-3"),
    )
    for code_field, policy_field in graupel_fields:
        if GRAUPEL[code_field] != declared_graupel[policy_field]:
            raise InitializationError(
                f"POLICY_IMPLEMENTATION_MISMATCH:QGRAUP.{code_field}"
            )


def _validate_policy_file(path: Path) -> dict[str, Any]:
    try:
        policy = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise InitializationError(f"INVALID_POLICY_FILE:{error}") from error
    if not isinstance(policy, dict):
        raise InitializationError("POLICY_ROOT_MUST_BE_OBJECT")
    if (policy.get("schema") != "pr61_native_moment_policy_v1"
            or policy.get("declared_before_experiment") is not True
            or policy.get("policy_id") != "PSD_PRIOR_RESEARCH_20261006"):
        raise InitializationError("UNSUPPORTED_OR_UNDECLARED_POLICY")
    if file_sha256(path) != EXPECTED_POLICY_SHA256:
        raise InitializationError("POLICY_HASH_MISMATCH")
    _check_policy_implementation(policy)
    return policy


def _verify_source_identities(policy: dict[str, Any]) -> None:
    source = policy["source"]
    for path_key, hash_key in (
        ("kdm6_source_path", "kdm6_source_sha256"),
        ("trace_instrumented_source_path", "trace_instrumented_source_sha256"),
        ("upstream_formula_comparison_path", "upstream_formula_comparison_sha256"),
        ("model_constants_path", "model_constants_sha256"),
        ("driver_path", "driver_sha256"),
    ):
        path = Path(source[path_key])
        if file_sha256(path) != source[hash_key]:
            raise InitializationError(f"MODEL_SOURCE_HASH_MISMATCH:{path_key}")


def _canonical_units(variable: Any) -> str | None:
    value = getattr(variable, "units", None)
    if isinstance(value, bytes):
        try:
            value = value.decode("ascii")
        except UnicodeDecodeError:
            return None
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.split()).lower()
    aliases = {
        "kg kg-1": "kg kg-1",
        "kg-1": "kg-1", "kg(-1)": "kg-1",
        "m3 kg-1": "m3 kg-1", "m(3) kg(-1)": "m3 kg-1",
    }
    return aliases.get(normalized)


def _check_input_metadata(dataset: Dataset) -> None:
    if "Time" not in dataset.dimensions or len(dataset.dimensions["Time"]) != 1:
        raise InitializationError("EXPECTED_ONE_TIME_RECORD")
    physics = np.asarray(getattr(dataset, "MP_PHYSICS", None))
    if physics.ndim != 0 or physics.dtype.kind not in "ifu" or physics.item() != 37:
        raise InitializationError("UNSUPPORTED_MP_PHYSICS")
    if "Times" not in dataset.variables:
        raise InitializationError("MISSING_VALID_TIME")
    time_value = b"".join(np.asarray(dataset["Times"][:]).reshape(-1)).decode("ascii")
    if time_value != EXPECTED_VALID_TIME:
        raise InitializationError("VALID_TIME_MISMATCH")
    expected_units = {
        "QCLOUD": "kg kg-1", "QICE": "kg kg-1", "QRAIN": "kg kg-1",
        "QGRAUP": "kg kg-1", "QNCLOUD": "kg-1", "QNICE": "kg-1",
        "QNRAIN": "kg-1", "QIB": "m3 kg-1", "QNCCN": "kg-1",
    }
    for name, expected in expected_units.items():
        if _canonical_units(dataset.variables[name]) != expected:
            raise InitializationError(f"SERIALIZED_UNITS_MISMATCH:{name}")
    expected_shape = (39, 282, 234)
    for name in ("QCLOUD", "QICE", "QRAIN", "QGRAUP", "QNCLOUD", "QNICE",
                 "QNRAIN", "QIB", "QNCCN"):
        if dataset.variables[name].shape != (1, *expected_shape):
            raise InitializationError(f"SERIALIZED_SHAPE_MISMATCH:{name}")


def _prepare_moments(
    mass: np.ndarray,
    existing: np.ndarray,
    dry_density: np.ndarray,
    *,
    threshold: float,
    lambda_min: float,
    lambda_max: float,
    power: int,
    pidn: float,
    internal_cap: float,
) -> tuple[np.ndarray, dict[str, Any]]:
    if mass.shape != existing.shape or mass.shape != dry_density.shape:
        raise InitializationError("ACTIVE_SHAPE_MISMATCH")
    if (not np.all(np.isfinite(mass)) or np.any(mass < 0.0)
            or not np.all(np.isfinite(existing)) or np.any(existing < 0.0)):
        raise InitializationError("INVALID_MASS_OR_EXISTING_MOMENT")
    if not np.all(np.isfinite(dry_density)) or np.any(dry_density <= 0.0):
        raise InitializationError("INVALID_DRY_AIR_DENSITY")

    eligible = (mass > threshold) & (existing == 0.0)
    upper_lambda = np.full(mass.shape, lambda_max, dtype=np.float64)
    if np.any(eligible):
        maximum_lambda = np.power(
            (internal_cap * pidn) / (mass[eligible] * dry_density[eligible]),
            1.0 / power,
        )
        upper_lambda[eligible] = np.minimum(lambda_max, maximum_lambda)
    feasible = eligible & (upper_lambda >= lambda_min)
    infeasible = eligible & ~feasible

    updated = np.array(existing, copy=True)
    if np.any(feasible):
        selected_lambda = np.sqrt(lambda_min * upper_lambda[feasible])
        number_per_kg = mass[feasible] * selected_lambda**power / pidn
        if not np.all(np.isfinite(number_per_kg)) or np.any(number_per_kg <= 0.0):
            raise InitializationError("NONFINITE_OR_NONPOSITIVE_PRIOR")
        stored = number_per_kg.astype(existing.dtype)
        if np.any(~np.isfinite(stored)) or np.any(stored <= 0.0):
            raise InitializationError("PRIOR_NOT_REPRESENTABLE_IN_NATIVE_DTYPE")
        updated[feasible] = stored

        # Match the native stored-number * DEN arithmetic. If rounding the
        # candidate to the model's storage dtype crosses the source cap, move
        # that stored value down by one representable value and check again.
        density_storage = dry_density[feasible].astype(existing.dtype)
        cap_storage = np.asarray(internal_cap, dtype=existing.dtype)
        for _ in range(4):
            internal_number = updated[feasible] * density_storage
            over_cap = internal_number > cap_storage
            if not np.any(over_cap):
                break
            updated_feasible = updated[feasible]
            updated_feasible[over_cap] = np.nextafter(
                updated_feasible[over_cap], np.asarray(0.0, dtype=existing.dtype)
            )
            updated[feasible] = updated_feasible
        if np.any(updated[feasible] * density_storage > cap_storage):
            raise InitializationError("PRIOR_EXCEEDS_INTERNAL_NUMBER_CAP")

    return updated, {
        "eligible_missing_cells": int(np.count_nonzero(eligible)),
        "research_fill_cutoff": "strict mass > declared threshold",
        "initialized_cells": int(np.count_nonzero(feasible)),
        "left_unchanged_infeasible_cells": int(np.count_nonzero(infeasible)),
        "preserved_existing_nonzero_cells": int(np.count_nonzero(existing > 0.0)),
        "source_lambda_min_m-1": lambda_min,
        "source_lambda_max_m-1": lambda_max,
        "cap_rounding_policy": "Stored number is checked with stored DEN and exact source cap; an over-cap stored value is stepped toward zero by one representable native dtype value until admissible.",
        "prior_center_lambda_m-1_range": (
            [float(np.min(np.sqrt(lambda_min * upper_lambda[feasible]))),
             float(np.max(np.sqrt(lambda_min * upper_lambda[feasible])))]
            if np.any(feasible) else None
        ),
    }


def _validate_mass_prior(
    mass: np.ndarray,
    number: np.ndarray,
    initialized: np.ndarray,
    *,
    m_min: float,
    m_max: float,
    bound_source: str,
) -> dict[str, Any]:
    if not np.any(initialized):
        return {"status": "NOT_RUN", "reason": "EMPTY_INITIALIZED_MASK",
                "checked_count": 0, "violation_count": 0}
    report = validate_mass_number(
        mass[initialized], number[initialized],
        mass_units="kg kg-1", number_units="kg-1",
        mass_basis="dry_air", number_basis="dry_air",
        particle_mass_min_kg=m_min, particle_mass_max_kg=m_max,
        bound_source=bound_source, uncertainty_description=UNCERTAINTY,
    )
    if report["status"] != "PASS_SCOPED":
        raise InitializationError(f"MASS_NUMBER_PREFLIGHT:{report['reason']}")
    return {key: value for key, value in report.items() if key != "violation_mask"}


def _validate_bulk_prior(
    mass: np.ndarray,
    volume: np.ndarray,
    initialized: np.ndarray,
) -> dict[str, Any]:
    if not np.any(initialized):
        return {"status": "NOT_RUN", "reason": "EMPTY_INITIALIZED_MASK",
                "checked_count": 0, "violation_count": 0}
    report = validate_bulk_volume(
        mass[initialized], volume[initialized],
        mass_units="kg kg-1", volume_units="m3 kg-1",
        mass_basis="dry_air", volume_basis="dry_air",
        bulk_density_min_kg_m3=GRAUPEL["rho_min"],
        bulk_density_max_kg_m3=GRAUPEL["rho_max"],
        bound_source=BOUND_SOURCE,
        uncertainty_description="Source rho_min..rho_max is an admissibility envelope, not a statistical sigma; rho_mid is the declared research center.",
    )
    if report["status"] != "PASS_SCOPED":
        raise InitializationError(f"MASS_VOLUME_PREFLIGHT:{report['reason']}")
    return {key: value for key, value in report.items() if key != "violation_mask"}


def initialize_copy(
    source_path: str | Path,
    output_path: str | Path,
    denominator_trace: str | Path,
    receipt_path: str | Path,
    *,
    policy_path: str | Path = DEFAULT_POLICY,
) -> dict[str, Any]:
    """Write a new prior-initialized copy and a complete field-hash receipt."""
    source = Path(source_path).resolve()
    output = Path(output_path).resolve()
    receipt_file = Path(receipt_path).resolve()
    trace_path = Path(denominator_trace).resolve()
    policy_file = Path(policy_path).resolve()
    initializer_path = Path(__file__).resolve()
    initializer_hash_before = file_sha256(initializer_path)
    if (source == output or output == receipt_file or output.exists()
            or receipt_file.exists()):
        raise InitializationError("OUTPUT_AND_RECEIPT_MUST_BE_NEW_PATHS")
    policy = _validate_policy_file(policy_file)
    _verify_source_identities(policy)
    source_hash = file_sha256(source)
    if source_hash != EXPECTED_INPUT_SHA256:
        raise InitializationError("SOURCE_INPUT_HASH_MISMATCH")

    # Imports are delayed so this CLI can validate policy/path before decoding a
    # large native trace, and tests can exercise the array policy separately.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from native_kdm6_trace import read_dump

    trace = read_dump(trace_path)
    if (trace["stage"] != 1 or trace["itimestep"] != 1
            or trace["sha256"] != EXPECTED_TRACE_SHA256
            or trace["bounds"] != EXPECTED_TRACE_BOUNDS):
        raise InitializationError("EXPECTED_BASELINE_FIRST_CALL_PRE_TRACE")
    den_active = np.transpose(trace["fields"]["DEN"], (1, 0, 2)).astype(np.float64)

    output.parent.mkdir(parents=True, exist_ok=True)
    receipt_file.parent.mkdir(parents=True, exist_ok=True)
    with Dataset(source, "r") as original:
        if "Time" not in original.dimensions or len(original.dimensions["Time"]) != 1:
            raise InitializationError("EXPECTED_ONE_TIME_RECORD")
        required = {
            "QCLOUD", "QICE", "QRAIN", "QGRAUP", "QNCLOUD", "QNICE",
            "QNRAIN", "QIB", "QNCCN",
        }
        missing = sorted(required - set(original.variables))
        if missing:
            raise InitializationError(f"MISSING_FIELDS:{','.join(missing)}")
        _check_input_metadata(original)
        variable_hashes_before = {
            name: variable_sha256(variable)
            for name, variable in original.variables.items()
        }
        arrays = {
            name: _read_unmasked(original.variables[name], name)
            for name in required
        }
        spatial = arrays["QCLOUD"].shape
        if any(value.shape != spatial for value in arrays.values()):
            raise InitializationError("MOMENT_FIELD_SHAPE_MISMATCH")
        if spatial[1] < 3 or spatial[2] < 3:
            raise InitializationError("EXPECTED_TWO_CELL_OUTER_RING")
        active_slice = (slice(None), slice(1, -1), slice(1, -1))
        active_shape = arrays["QCLOUD"][active_slice].shape
        if active_shape != den_active.shape:
            raise InitializationError("TRACE_AND_NATIVE_ACTIVE_SHAPE_MISMATCH")
        for name in ("QCLOUD", "QICE", "QRAIN", "QGRAUP"):
            mass = arrays[name]
            if np.any(mass < 0.0):
                raise InitializationError(f"NEGATIVE_MASS_FIELD:{name}")

    updated: dict[str, np.ndarray] = {}
    initialized_masks: dict[str, np.ndarray] = {}
    field_reports: dict[str, Any] = {}
    for mass_name, spec in SPECIES.items():
        mass = arrays[mass_name][active_slice].astype(np.float64)
        existing = arrays[spec["moment"]][active_slice]
        result, counts = _prepare_moments(
            mass, existing, den_active,
            threshold=spec["threshold"], lambda_min=spec["lambda_min"],
            lambda_max=spec["lambda_max"], power=spec["power"],
            pidn=spec["pidn"], internal_cap=spec["internal_cap"],
        )
        mask = result != existing
        updated[spec["moment"]] = result
        initialized_masks[spec["moment"]] = mask
        validation = _validate_mass_prior(
            mass, result, mask, m_min=spec["m_min"], m_max=spec["m_max"],
            bound_source=BOUND_SOURCE,
        )
        field_reports[spec["moment"]] = {**counts, "preflight": validation}
        if mass_name == "QRAIN":
            internal_number_proxy = result.astype(np.float32) * den_active.astype(np.float32)
            field_reports[spec["moment"]]["initialized_below_source_nrmin_cells"] = int(
                np.count_nonzero(mask & (internal_number_proxy < 0.01))
            )
            field_reports[spec["moment"]]["source_nrmin_number_m-3"] = 0.01

    graupel_mass = arrays["QGRAUP"][active_slice].astype(np.float64)
    old_volume = arrays["QIB"][active_slice]
    graupel_active = (graupel_mass > GRAUPEL["threshold"]) & (old_volume == 0.0)
    new_volume = np.array(old_volume, copy=True)
    new_volume[graupel_active] = (
        graupel_mass[graupel_active] / GRAUPEL["rho_center"]
    ).astype(old_volume.dtype)
    volume_validation = _validate_bulk_prior(
        graupel_mass, new_volume, graupel_active,
    )
    updated[GRAUPEL["moment"]] = new_volume
    initialized_masks[GRAUPEL["moment"]] = graupel_active
    field_reports[GRAUPEL["moment"]] = {
        "eligible_missing_cells": int(np.count_nonzero(
            (graupel_mass > GRAUPEL["threshold"]) & (old_volume == 0.0))),
        "initialized_cells": int(np.count_nonzero(graupel_active)),
        "left_unchanged_infeasible_cells": 0,
        "preserved_existing_nonzero_cells": int(np.count_nonzero(old_volume > 0.0)),
        "density_center_kg_m-3": GRAUPEL["rho_center"],
        "density_support_kg_m-3": [GRAUPEL["rho_min"], GRAUPEL["rho_max"]],
        "preflight": volume_validation,
    }
    for moment, report in field_reports.items():
        report["units"] = "m3 kg-1" if moment == "QIB" else "kg-1"
        report["basis"] = "dry_air"
        report["stored_dtype"] = str(arrays[moment].dtype)
        changed_values = updated[moment][initialized_masks[moment]]
        report["changed_value_min"] = (
            float(np.min(changed_values)) if changed_values.size else None
        )
        report["changed_value_max"] = (
            float(np.max(changed_values)) if changed_values.size else None
        )
        report["mass_field"] = {
            "name": next(name for name, spec in SPECIES.items()
                         if spec["moment"] == moment)
                         if moment != "QIB" else "QGRAUP",
            "unchanged": True,
            "units": "kg kg-1",
            "basis": "dry_air",
        }

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    receipt_temporary: Path | None = None
    try:
        shutil.copy2(source, temporary)
        with Dataset(temporary, "r+") as candidate:
            for moment, active_values in updated.items():
                all_values = np.array(candidate.variables[moment][0], copy=True)
                all_values[active_slice] = active_values
                candidate.variables[moment][0] = all_values
        with Dataset(source, "r") as original, Dataset(temporary, "r") as candidate:
            _check_input_metadata(candidate)
            changed_nonmoment = []
            variable_hashes_after = {}
            for name, before_variable in original.variables.items():
                after_variable = candidate.variables[name]
                after_hash = variable_sha256(after_variable)
                variable_hashes_after[name] = after_hash
                if name in updated:
                    continue
                if variable_hashes_before[name] != after_hash:
                    changed_nonmoment.append(name)
            if changed_nonmoment:
                raise InitializationError(
                    f"UNEXPECTED_FIELD_CHANGES:{','.join(changed_nonmoment)}"
                )
            for moment, active_values in updated.items():
                expected_values = np.array(arrays[moment], copy=True)
                expected_values[active_slice] = active_values
                actual_values = _read_unmasked(candidate.variables[moment], moment)
                if not np.array_equal(actual_values, expected_values):
                    raise InitializationError(f"UNEXPECTED_MOMENT_CHANGES:{moment}")
                outside_active = np.ones(actual_values.shape, dtype=bool)
                outside_active[active_slice] = False
                if not np.array_equal(
                    actual_values[outside_active], arrays[moment][outside_active]
                ):
                    raise InitializationError(f"OUTER_RING_MOMENT_CHANGED:{moment}")
            for mass_name, spec in SPECIES.items():
                mask = initialized_masks[spec["moment"]]
                number = np.asarray(candidate[spec["moment"]][0][active_slice])
                _validate_mass_prior(
                    arrays[mass_name][active_slice].astype(np.float64),
                    number, mask,
                    m_min=spec["m_min"], m_max=spec["m_max"],
                    bound_source=BOUND_SOURCE,
                )
            stored_volume = np.asarray(candidate["QIB"][0][active_slice])
            _validate_bulk_prior(graupel_mass, stored_volume, graupel_active)

        gaps = {}
        for mass_name, moment in (
            ("QCLOUD", "QNCLOUD"), ("QICE", "QNICE"),
            ("QRAIN", "QNRAIN"), ("QGRAUP", "QIB"),
        ):
            mass = arrays[mass_name][active_slice]
            number = updated.get(moment, arrays[moment][active_slice])
            gaps[mass_name] = {
                "positive_mass_cells": int(np.count_nonzero(mass > 0.0)),
                "positive_mass_zero_moment_cells": int(np.count_nonzero(
                    (mass > 0.0) & (number == 0.0)
                )),
            }
        unsupported = sum(
            report["left_unchanged_infeasible_cells"] for report in field_reports.values()
        )
        initializer_hash_after = file_sha256(initializer_path)
        receipt = {
            "schema": "pr61_native_moment_prior_receipt_v1",
            "policy_id": policy["policy_id"],
            "policy_sha256": file_sha256(policy_file),
            "initializer_sha256_before": initializer_hash_before,
            "initializer_sha256_after": initializer_hash_after,
            "initializer_unchanged_during_initialization": initializer_hash_before == initializer_hash_after,
            "declared_before_experiment": True,
            "status": "PARTIAL_RESEARCH_PRIOR_CREATED" if unsupported else "RESEARCH_PRIOR_CREATED",
            "native_launch_authority": "NONE",
            "source_input": str(source),
            "source_input_sha256_before": source_hash,
            "source_input_sha256_after": file_sha256(source),
            "source_input_unchanged": source_hash == file_sha256(source),
            "output_input": str(output),
            "output_input_sha256": file_sha256(temporary),
            "source_trace": str(trace_path),
            "source_trace_sha256": trace["sha256"],
            "source_trace_timestep": trace["itimestep"],
            "source_trace_active_shape_xyz": trace["active_shape_xyz"],
            "source_trace_DEN_basis": "kg dry air m-3; used only as a prior-run first-call cap proxy. It is not asserted to be initial wrfinput density and must be rechecked against the actual first-call trace.",
            "field_prior_receipts": field_reports,
            "source_active_positive_mass_zero_moment_gaps": gaps,
            "all_other_variables_unchanged": True,
            "changed_nonmoment_variables": [],
            "input_variable_sha256_before": variable_hashes_before,
            "input_variable_sha256_after": variable_hashes_after,
            "limited_scope": "Conditional research initialization only. Unresolved cells remain unchanged; no forecast, science, or operational acceptance is implied.",
        }
        if receipt["source_input_unchanged"] is not True:
            raise InitializationError("SOURCE_INPUT_CHANGED_DURING_INITIALIZATION")
        if receipt["initializer_unchanged_during_initialization"] is not True:
            raise InitializationError("INITIALIZER_CHANGED_DURING_INITIALIZATION")
        if file_sha256(policy_file) != receipt["policy_sha256"]:
            raise InitializationError("POLICY_CHANGED_DURING_INITIALIZATION")
        _verify_source_identities(policy)
        receipt_descriptor, receipt_name = tempfile.mkstemp(
            prefix=f".{receipt_file.name}.", suffix=".tmp", dir=receipt_file.parent
        )
        receipt_temporary = Path(receipt_name)
        with os.fdopen(receipt_descriptor, "w", encoding="utf-8") as stream:
            json.dump(receipt, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        published_output = False
        published_receipt = False
        try:
            os.link(temporary, output)
            published_output = True
            os.link(receipt_temporary, receipt_file)
            published_receipt = True
            if file_sha256(initializer_path) != initializer_hash_before:
                raise InitializationError("INITIALIZER_CHANGED_DURING_PUBLICATION")
        except BaseException:
            if published_output:
                output.unlink(missing_ok=True)
            if published_receipt:
                receipt_file.unlink(missing_ok=True)
            raise
        return receipt

    finally:
        temporary.unlink(missing_ok=True)
        if receipt_temporary is not None:
            receipt_temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--denominator-trace", type=Path, required=True)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    try:
        receipt = initialize_copy(
            args.source, args.output, args.denominator_trace,
            args.receipt,
            policy_path=args.policy,
        )
    except (OSError, RuntimeError, ValueError, TypeError, IndexError) as error:
        parser.error(str(error))
    print(f"{receipt['status']}: {receipt['output_input']}")
    print(f"sha256: {receipt['output_input_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
