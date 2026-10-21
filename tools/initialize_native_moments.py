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
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from netCDF4 import Dataset
import numpy as np

from hydrometeor_moments import validate_bulk_volume, validate_mass_number


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "docs/PR61_NATIVE_MOMENT_POLICY_20261006.json"
DEFAULT_PR83_POLICY = ROOT / "docs/PR83_NATIVE_MOMENT_POLICY_20261013.json"
EXPECTED_POLICY_SHA256 = "20fd53ec626cbb4e192583f99777b5f7f56d580959171c240b804c38873517b3"
EXPECTED_INPUT_SHA256 = "397daf0387d522243167f5e48831f7415bea07f00c22e5674ef89f73db1a2c0c"
EXPECTED_TRACE_SHA256 = "aa01a611b81cf041961748a945e91b4d52aa6704c9fea4398ec7cbe9138139b2"
EXPECTED_VALID_TIME = "2026-08-16_12:00:00"
PR83_EXPECTED_POLICY_SHA256 = "dde8df58f840d2fb11579876450749964ea2a54e36a68856c92bc979f46bae2a"
PR83_EXPECTED_INPUT_SHA256 = "dce4a2633521639a4195babc461a45427f669dc808cb7b2d99d321b153b77afb"
PR83_EXPECTED_VALID_TIME = "2026-08-16_13:00:00"
PR84_EXPECTED_POLICY_SHA256 = "7f0176742d736c9dbe2be127f43eb00ed35ebda89f0b792a51220efb7d4d7e92"
PR84_EXPECTED_SOURCE_INPUTS = {
    "OFF": "6ed69cbd2bdb8d128dbd7273ac8de216fe4537748a0e4ca474213ac408060730",
    "COUPLED": "dce4a2633521639a4195babc461a45427f669dc808cb7b2d99d321b153b77afb",
}
PR84_POLICY_SCHEMA = "pr84_same13_native_moment_policy_v2"
PR94_HYDRO_POLICY_SCHEMA = "pr94_same13_hydro_moment_policy_v1"
PR94_HYDRO_POLICY_ID = "SAME13_KDM6_NATIVE_MOMENT_PRIOR_20261013_V2_HYDRO"
PR83_BOUND_SOURCE = (
    "Selected KDM6 source PSD parameterization and source-exact same-time WRF AL+ALB density; "
    "see docs/PR83_NATIVE_MOMENT_POLICY_20261013.json"
)
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

    def __init__(self, message: str, *, diagnostics: dict[str, Any] | None = None):
        super().__init__(message)
        self.diagnostics = diagnostics or {}


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


def _validate_same13_policy_file(path: Path) -> dict[str, Any]:
    try:
        policy = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise InitializationError(f"INVALID_POLICY_FILE:{error}") from error
    if not isinstance(policy, dict):
        raise InitializationError("POLICY_ROOT_MUST_BE_OBJECT")
    if policy.get("schema") == PR94_HYDRO_POLICY_SCHEMA:
        _validate_pr94_hydro_policy(path, policy)
        return policy
    if policy.get("schema") == PR84_POLICY_SCHEMA:
        if file_sha256(path) != PR84_EXPECTED_POLICY_SHA256:
            raise InitializationError("PR84_POLICY_HASH_MISMATCH")
        _validate_pr84_policy_contract(policy)
        _validate_pr84_evidence_bindings(policy)
        return policy
    if (policy.get("schema") != "pr83_same13_native_moment_policy_v1"
            or policy.get("policy_id") != "SAME13_KDM6_NATIVE_MOMENT_PRIOR_20261013"
            or policy.get("declared_before_experiment") is not True):
        raise InitializationError("UNSUPPORTED_OR_UNDECLARED_PR83_POLICY")
    if file_sha256(path) != PR83_EXPECTED_POLICY_SHA256:
        raise InitializationError("PR83_POLICY_HASH_MISMATCH")
    source = policy["source"]
    for path_key, hash_key in (
        ("kdm6_source_path", "kdm6_source_sha256"),
        ("upstream_formula_comparison_path", "upstream_formula_comparison_sha256"),
        ("model_constants_path", "model_constants_sha256"),
        ("driver_path", "driver_sha256"),
        ("runtime_consumer_source_path", "runtime_consumer_source_sha256"),
    ):
        source_path = Path(source[path_key])
        if file_sha256(source_path) != source[hash_key]:
            raise InitializationError(f"MODEL_SOURCE_HASH_MISMATCH:{path_key}")
    for path_key, hash_key in (
        ("runtime_consumer_executable_path", "runtime_consumer_executable_sha256"),
        ("runtime_consumer_archive_path", "runtime_consumer_archive_sha256"),
        ("runtime_consumer_build_receipt_path", "runtime_consumer_build_receipt_sha256"),
        ("runtime_consumer_readback_receipt_path", "runtime_consumer_readback_receipt_sha256"),
    ):
        if file_sha256(Path(source[path_key])) != source[hash_key]:
            raise InitializationError(f"MODEL_SOURCE_HASH_MISMATCH:{path_key}")
    member = subprocess.run(
        ["ar", "p", source["runtime_consumer_archive_path"],
         source["runtime_consumer_object_member"]],
        check=True, capture_output=True,
    ).stdout
    if hashlib.sha256(member).hexdigest() != source["runtime_consumer_object_member_sha256"]:
        raise InitializationError("MODEL_SOURCE_HASH_MISMATCH:runtime_consumer_object_member")
    density_source = policy["density_source"]
    for path_key, hash_key in (
        ("wrf_source_start_path", "wrf_source_start_sha256"),
        ("wrf_source_density_path", "wrf_source_density_sha256"),
    ):
        source_path = Path(density_source[path_key])
        if file_sha256(source_path) != density_source[hash_key]:
            raise InitializationError(f"WRF_SOURCE_HASH_MISMATCH:{path_key}")
    _check_same13_policy_implementation(policy)
    return policy


def _validate_pr94_hydro_policy(path: Path, policy: dict[str, Any]) -> None:
    """Allow one separately bound HYDRO input under the unchanged PR84 v2 prior."""
    base_path = Path(__file__).resolve().parents[1] / "docs/PR84_NATIVE_MOMENT_POLICY_20261013.json"
    try:
        base = json.loads(base_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise InitializationError(f"PR94_BASE_POLICY_UNAVAILABLE:{error}") from error
    if file_sha256(base_path) != PR84_EXPECTED_POLICY_SHA256:
        raise InitializationError("PR94_BASE_POLICY_HASH_MISMATCH")
    if policy.get("policy_id") != PR94_HYDRO_POLICY_ID:
        raise InitializationError("PR94_POLICY_ID_MISMATCH")
    binding = policy.get("hydro_input_binding")
    if (not isinstance(binding, dict)
            or set(binding) != {"source_receipt_path", "source_receipt_sha256",
                                "wrfinput_path", "wrfinput_sha256"}):
        raise InitializationError("PR94_HYDRO_INPUT_BINDING_MISSING")
    receipt_path = Path(binding["source_receipt_path"])
    wrfinput_path = Path(binding["wrfinput_path"])
    if (file_sha256(receipt_path) != binding["source_receipt_sha256"]
            or file_sha256(wrfinput_path) != binding["wrfinput_sha256"]):
        raise InitializationError("PR94_HYDRO_INPUT_BINDING_HASH_MISMATCH")
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise InitializationError(f"PR94_SOURCE_RECEIPT_INVALID:{error}") from error
    wrfinput_binding = receipt.get("wrfinput", {})
    if (receipt.get("schema") != "pr94_hydro_real_input_receipt_v1"
            or receipt.get("status") != "PASS_HYDRO_REAL_INPUT"
            or receipt.get("role") != "HYDRO"
            or wrfinput_binding.get("path") != str(wrfinput_path)
            or wrfinput_binding.get("sha256") != binding["wrfinput_sha256"]):
        raise InitializationError("PR94_SOURCE_RECEIPT_IDENTITY_MISMATCH")
    restored = json.loads(json.dumps(policy))
    restored.pop("hydro_input_binding", None)
    restored["schema"] = base["schema"]
    restored["policy_id"] = base["policy_id"]
    restored["preflight"]["authorized_source_inputs"] = base["preflight"]["authorized_source_inputs"]
    if restored != base:
        raise InitializationError("PR94_POLICY_DIFFERS_FROM_PR84_V2")
    _validate_pr84_policy_contract(base)
    _validate_pr84_evidence_bindings(base)


def _validate_pr84_policy_contract(policy: dict[str, Any]) -> None:
    """Validate the v2 scope and exact source pair without changing frozen v1."""
    if (policy.get("policy_id") != "SAME13_KDM6_NATIVE_MOMENT_PRIOR_20261013_V2"
            or policy.get("declared_before_experiment") is not True):
        raise InitializationError("UNSUPPORTED_OR_UNDECLARED_PR84_POLICY")
    prior = policy.get("prior", {})
    if prior.get("active_domain_mode") != "FULL_NATIVE_HORIZONTAL":
        raise InitializationError("PR84_ACTIVE_DOMAIN_MODE_MISMATCH")
    species = policy.get("species", {})
    ice = species.get("QICE", {})
    if ice.get("internal_number_cap_mode") != "SOURCE_PSD_COMPATIBLE_ENTRY_GUARD":
        raise InitializationError("PR84_QICE_CAP_MODE_MISMATCH")
    preflight = policy.get("preflight", {})
    authorized = preflight.get("authorized_source_inputs")
    if (not isinstance(authorized, list) or len(authorized) != 2
            or any(not isinstance(entry, dict) or set(entry) != {"role", "sha256"}
                   for entry in authorized)):
        raise InitializationError("PR84_SOURCE_PAIR_MISSING")
    observed = {entry["role"]: entry["sha256"] for entry in authorized}
    if observed != PR84_EXPECTED_SOURCE_INPUTS:
        raise InitializationError("PR84_SOURCE_PAIR_MISMATCH")
    if (preflight.get("expected_source_valid_time") != PR83_EXPECTED_VALID_TIME
            or preflight.get("expected_input_spatial_shape_bottom_top_south_north_west_east")
            != [39, 282, 234]):
        raise InitializationError("PR84_INPUT_IDENTITY_MISMATCH")
    required_values = (
        ice.get("source_pidni_binary32_value"),
        ice.get("source_pidni_binary32_hex"),
        species.get("QICE", {}).get("lambda_min_m-1"),
    )
    if any(value is None for value in required_values):
        raise InitializationError("PR84_QICE_SOURCE_PARAMETERS_MISSING")
    pidni_value, pidni_hex, lambda_min = required_values
    if (not math.isfinite(float(pidni_value)) or float(pidni_value) <= 0.0
            or not isinstance(pidni_hex, str) or not math.isfinite(float(lambda_min))
            or float(lambda_min) <= 0.0):
        raise InitializationError("PR84_QICE_SOURCE_PARAMETERS_INVALID")
    try:
        declared_bits = int(pidni_hex.lower().removeprefix("0x"), 16)
    except ValueError as error:
        raise InitializationError("PR84_QICE_PIDNI_HEX_INVALID") from error
    actual_bits = int(np.asarray(np.float32(pidni_value)).view(np.uint32))
    if declared_bits != actual_bits:
        raise InitializationError("PR84_QICE_PIDNI_VALUE_HEX_MISMATCH")
    if ice.get("shape_exponent_d") != 3:
        raise InitializationError("PR84_QICE_SHAPE_EXPONENT_MISMATCH")
    try:
        _check_same13_policy_implementation(policy)
    except InitializationError as error:
        raise InitializationError(f"PR84_SPECIES_IMPLEMENTATION_MISMATCH:{error}") from error


def _validate_pr84_evidence_bindings(policy: dict[str, Any]) -> None:
    """Verify fresh retained-consumer, source-parameter, and density bindings."""
    source = policy["source"]
    for path_key, hash_key in (
        ("kdm6_source_path", "kdm6_source_sha256"),
        ("upstream_formula_comparison_path", "upstream_formula_comparison_sha256"),
        ("model_constants_path", "model_constants_sha256"),
        ("driver_path", "driver_sha256"),
        ("runtime_consumer_source_path", "runtime_consumer_source_sha256"),
        ("runtime_consumer_executable_path", "runtime_consumer_executable_sha256"),
        ("runtime_consumer_archive_path", "runtime_consumer_archive_sha256"),
        ("runtime_consumer_build_receipt_path", "runtime_consumer_build_receipt_sha256"),
    ):
        if file_sha256(Path(source[path_key])) != source[hash_key]:
            raise InitializationError(f"PR84_MODEL_SOURCE_HASH_MISMATCH:{path_key}")
    member = subprocess.run(
        ["ar", "p", source["runtime_consumer_archive_path"],
         source["runtime_consumer_object_member"]],
        check=True, capture_output=True,
    ).stdout
    if hashlib.sha256(member).hexdigest() != source["runtime_consumer_object_member_sha256"]:
        raise InitializationError("PR84_MODEL_SOURCE_HASH_MISMATCH:runtime_consumer_object_member")
    if source.get("runtime_consumer_readback_status") != "NOT_RUN":
        raise InitializationError("PR84_RUNTIME_READBACK_STATUS_MISMATCH")
    native_build = policy["native_build"]
    if file_sha256(Path(native_build["receipt_path"])) != native_build["receipt_sha256"]:
        raise InitializationError("PR84_NATIVE_BUILD_RECEIPT_HASH_MISMATCH")
    if file_sha256(Path(native_build["actual_parameter_dump_path"])) != native_build[
            "actual_parameter_dump_sha256"]:
        raise InitializationError("PR84_PARAMETER_DUMP_HASH_MISMATCH")
    if file_sha256(Path(native_build["profile_path"])) != native_build["profile_sha256"]:
        raise InitializationError("PR84_TOOLCHAIN_PROFILE_HASH_MISMATCH")
    try:
        receipt = json.loads(Path(native_build["receipt_path"]).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise InitializationError(f"PR84_INVALID_NATIVE_BUILD_RECEIPT:{error}") from error
    if (receipt.get("schema") != native_build["schema"]
            or receipt.get("model_run") is not False
            or receipt.get("production_source_sha256") != source["runtime_consumer_source_sha256"]
            or receipt.get("candidate_archive_sha256") != source["runtime_consumer_archive_sha256"]
            or receipt.get("production_executable_sha256")
            != source["runtime_consumer_executable_sha256"]
            or receipt.get("production_object_sha256")
            != source["runtime_consumer_object_member_sha256"]
            or receipt.get("production_link_dependencies_sha256", {}).get(
                source["runtime_consumer_archive_path"]
            ) != source["runtime_consumer_archive_sha256"]):
        raise InitializationError("PR84_NATIVE_BUILD_IDENTITY_MISMATCH")
    parameters = receipt.get("test_accessor", {}).get("actual_kdm6init_output", {})
    source_parameters = receipt.get("native_source_parameters", {})
    declared_parameters = native_build.get("actual_kdm6init_output", {})
    for parameter in ("pidni", "lambda_min", "dmi", "mui"):
        observed = parameters.get(parameter, {})
        source_observed = source_parameters.get(parameter, {})
        declared = declared_parameters.get(parameter, {})
        if observed != declared or source_observed != declared:
            raise InitializationError(f"PR84_KDM6_PARAMETER_MISMATCH:{parameter}")
    ice = policy["species"]["QICE"]
    if (ice["source_pidni_binary32_value"] != parameters["pidni"]["real32"]
            or ice["source_pidni_binary32_hex"].lower()
            != parameters["pidni"]["bits"].lower()
            or ice["lambda_min_m-1"] != parameters["lambda_min"]["real32"]
            or ice["shape_exponent_d"] != int(parameters["dmi"]["real32"])
            or ice["source_shape_parameter_mu"] != int(parameters["mui"]["real32"])):
        raise InitializationError("PR84_QICE_POLICY_PARAMETER_BINDING_MISMATCH")
    dump_text = Path(native_build["actual_parameter_dump_path"]).read_text(encoding="utf-8")
    for name, parameter in (("PIDNI", "pidni"), ("LAMBDA_MIN", "lambda_min"),
                            ("DMI", "dmi"), ("MUI", "mui")):
        bits = parameters[parameter]["bits"].removeprefix("0x").upper()
        if f"PR84_{name}|" not in dump_text or f"|{bits}" not in dump_text:
            raise InitializationError(f"PR84_PARAMETER_DUMP_CONTENT_MISMATCH:{name}")
    density_source = policy["density_source"]
    for path_key, hash_key in (
        ("wrf_source_start_path", "wrf_source_start_sha256"),
        ("wrf_source_density_path", "wrf_source_density_sha256"),
    ):
        if file_sha256(Path(density_source[path_key])) != density_source[hash_key]:
            raise InitializationError(f"PR84_WRF_SOURCE_HASH_MISMATCH:{path_key}")


def _pr84_float32_ceiling(values: np.ndarray) -> np.ndarray:
    """Return the least finite REAL32 value not below each REAL64 bound."""
    bounds = np.asarray(values, dtype=np.float64)
    if not np.all(np.isfinite(bounds)) or np.any(bounds < 0.0):
        raise InitializationError("PR84_INVALID_PUBLIC_NUMBER_FLOOR")
    with np.errstate(over="ignore", invalid="ignore"):
        rounded = bounds.astype(np.float32)
    rounded_up = rounded.astype(np.float64) < bounds
    rounded[rounded_up] = np.nextafter(
        rounded[rounded_up], np.float32(np.inf), dtype=np.float32
    )
    if not np.all(np.isfinite(rounded)):
        raise InitializationError("PR84_PUBLIC_NUMBER_FLOOR_OVERFLOW")
    predecessor = np.nextafter(rounded, np.float32(-np.inf), dtype=np.float32)
    if np.any(predecessor.astype(np.float64) >= bounds):
        raise InitializationError("PR84_NONMINIMAL_PUBLIC_NUMBER_FLOOR")
    if np.any(rounded.astype(np.float64) < bounds):
        raise InitializationError("PR84_PUBLIC_NUMBER_FLOOR_ROUNDING_FAILURE")
    return rounded


def _pr84_qice_entry_guard(
    mass: np.ndarray, density: np.ndarray, *, pidni: float, lambda_min: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Build minimal REAL32 QNICE meeting the public and internal PSD floors."""
    qice = np.asarray(mass, dtype=np.float64)
    rho = np.asarray(density, dtype=np.float32)
    if qice.shape != rho.shape:
        raise InitializationError("PR84_QICE_GUARD_SHAPE_MISMATCH")
    if (not np.all(np.isfinite(qice)) or np.any(qice < 0.0)
            or not np.all(np.isfinite(rho)) or np.any(rho <= 0.0)
            or not math.isfinite(pidni) or pidni <= 0.0
            or not math.isfinite(lambda_min) or lambda_min <= 0.0):
        raise InitializationError("PR84_INVALID_QICE_GUARD_INPUT")
    # QNICE is per kg dry air. Keep this source-parameter bound in REAL64;
    # only the stored public moment and native multiplication are REAL32.
    qn_floor_real64 = qice * (float(lambda_min) ** 3) / float(pidni)
    qn_floor = _pr84_float32_ceiling(qn_floor_real64)
    internal_floor_real64 = rho.astype(np.float64) * qn_floor_real64
    internal_floor = _pr84_float32_ceiling(internal_floor_real64)
    reachable_number = np.multiply(qn_floor, rho, dtype=np.float32)
    for _ in range(8):
        shortfall = reachable_number < internal_floor
        if not np.any(shortfall):
            break
        qn_floor[shortfall] = np.nextafter(
            qn_floor[shortfall], np.float32(np.inf), dtype=np.float32
        )
        reachable_number[shortfall] = np.multiply(
            qn_floor[shortfall], rho[shortfall], dtype=np.float32
        )
    if np.any(reachable_number < internal_floor):
        raise InitializationError("PR84_QICE_INTERNAL_FLOOR_UNREPRESENTABLE")
    if not np.all(np.isfinite(reachable_number)):
        raise InitializationError("PR84_QICE_INTERNAL_CAP_OVERFLOW")
    predecessor = np.nextafter(qn_floor, np.float32(-np.inf), dtype=np.float32)
    predecessor_number = np.multiply(predecessor, rho, dtype=np.float32)
    nonminimal = ((predecessor.astype(np.float64) >= qn_floor_real64)
                  & (predecessor_number >= internal_floor))
    if np.any(nonminimal):
        raise InitializationError("PR84_QICE_PUBLIC_NUMBER_FLOOR_NONMINIMAL")
    cap = np.maximum(np.float32(1.0e6), reachable_number).astype(np.float32)
    return qn_floor, internal_floor, cap


def _check_same13_policy_implementation(policy: dict[str, Any]) -> None:
    declared_species = policy["species"]
    if set(declared_species) != set(SPECIES) | {"QGRAUP", "QSNOW"}:
        raise InitializationError("PR83_POLICY_IMPLEMENTATION_MISMATCH:species_inventory")
    formulae = {
        "QCLOUD": "cmc*Gamma(1 + dmc/(muc+1)); cmc=pi*rhowater/6",
        "QRAIN": "cmr*Gamma(dmr+mur+1)/Gamma(mur+1); cmr=pi*rhowater/6",
        "QICE": "cmi*Gamma(dmi+mui+1)/Gamma(mui+1); cmi=pi*500/6",
    }
    gamma_shape = {"QCLOUD": (1000.0, 2.0, True),
                   "QRAIN": (1000.0, 1.0, False),
                   "QICE": (500.0, 0.0, False)}
    fields = (
        ("moment", "target_moment"),
        ("power", "shape_exponent_d"),
        ("lambda_min", "lambda_min_m-1"),
        ("lambda_max", "lambda_max_m-1"),
        ("internal_cap", "internal_number_cap_number_m-3"),
        ("m_min", "particle_mean_mass_bounds_kg", 0),
        ("m_max", "particle_mean_mass_bounds_kg", 1),
    )
    for mass_name, spec in SPECIES.items():
        declared = declared_species[mass_name]
        for field in fields:
            if len(field) == 2:
                code_key, policy_key = field
                expected = declared[policy_key]
            else:
                code_key, policy_key, index = field
                expected = declared[policy_key][index]
            if spec[code_key] != expected:
                raise InitializationError(
                    f"PR83_POLICY_IMPLEMENTATION_MISMATCH:{mass_name}.{code_key}"
                )
        if declared["pidn_formula"] != formulae[mass_name]:
            raise InitializationError(
                f"PR83_POLICY_IMPLEMENTATION_MISMATCH:{mass_name}.pidn_formula"
            )
        particle_density, mu, generalized = gamma_shape[mass_name]
        cm = math.pi * particle_density / 6.0
        expected_pidn = (
            cm * math.gamma(1.0 + spec["power"] / (mu + 1.0))
            if generalized else
            cm * math.gamma(spec["power"] + mu + 1.0) / math.gamma(mu + 1.0)
        )
        if not math.isclose(spec["pidn"], expected_pidn, rel_tol=16 * sys.float_info.epsilon):
            raise InitializationError(
                f"PR83_POLICY_IMPLEMENTATION_MISMATCH:{mass_name}.pidn"
            )
        derived = (spec["pidn"] / spec["lambda_max"] ** spec["power"],
                   spec["pidn"] / spec["lambda_min"] ** spec["power"])
        declared_bounds = declared["particle_mean_mass_bounds_kg"]
        if any(not math.isclose(a, b, rel_tol=16 * sys.float_info.epsilon)
               for a, b in zip(derived, declared_bounds)):
            raise InitializationError(
                f"PR83_POLICY_IMPLEMENTATION_MISMATCH:{mass_name}.mean_mass_bounds"
            )
    graupel = declared_species["QGRAUP"]
    for field, policy_field in (
        ("moment", "target_moment"),
        ("threshold", "source_active_mass_threshold_kg_kg-1"),
        ("rho_center", "bulk_density_prior_center_kg_m-3"),
        ("rho_min", "bulk_density_min_kg_m-3"),
        ("rho_max", "bulk_density_max_kg_m-3"),
    ):
        expected = graupel.get(policy_field)
        if expected is None and field == "threshold":
            continue
        if GRAUPEL[field] != expected:
            raise InitializationError(
                f"PR83_POLICY_IMPLEMENTATION_MISMATCH:QGRAUP.{field}"
            )
    if declared_species["QSNOW"].get("target_moment") is not None:
        raise InitializationError("PR83_POLICY_IMPLEMENTATION_MISMATCH:QSNOW")


def _same13_dry_density(dataset: Dataset) -> np.ndarray:
    """Return the source-exact real32 dry-carrier density from AL + ALB."""
    for name in ("AL", "ALB"):
        if name not in dataset.variables:
            raise InitializationError(f"MISSING_DENSITY_FIELD:{name}")
        variable = dataset.variables[name]
        if variable.dimensions != DIMENSIONS:
            raise InitializationError(f"MALFORMED_DIMENSIONS:{name}")
        if _canonical_units(variable) != "m3 kg-1":
            raise InitializationError(f"SERIALIZED_UNITS_MISMATCH:{name}")
    al = _read_unmasked(dataset.variables["AL"], "AL").astype(np.float32)
    alb = _read_unmasked(dataset.variables["ALB"], "ALB").astype(np.float32)
    inverse_density = np.add(al, alb, dtype=np.float32)
    if (not np.all(np.isfinite(inverse_density))
            or np.any(inverse_density <= 0.0)):
        raise InitializationError("INVALID_INVERSE_DRY_AIR_DENSITY")
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        density = np.divide(np.float32(1.0), inverse_density, dtype=np.float32)
    if not np.all(np.isfinite(density)) or np.any(density <= 0.0):
        raise InitializationError("INVALID_DRY_AIR_DENSITY")
    return density


def _same13_active_slice(policy: dict[str, Any]) -> tuple[slice, slice, slice]:
    if (policy.get("schema") in (PR84_POLICY_SCHEMA, PR94_HYDRO_POLICY_SCHEMA)
            and policy["prior"].get("active_domain_mode") == "FULL_NATIVE_HORIZONTAL"):
        return (slice(None), slice(None), slice(None))
    return (slice(None), slice(1, -1), slice(1, -1))


def _check_same13_input_metadata(dataset: Dataset) -> None:
    if "Time" not in dataset.dimensions or len(dataset.dimensions["Time"]) != 1:
        raise InitializationError("EXPECTED_ONE_TIME_RECORD")
    physics = np.asarray(getattr(dataset, "MP_PHYSICS", None))
    if physics.ndim != 0 or physics.dtype.kind not in "ifu" or physics.item() != 37:
        raise InitializationError("UNSUPPORTED_MP_PHYSICS")
    if "Times" not in dataset.variables:
        raise InitializationError("MISSING_VALID_TIME")
    time_value = b"".join(np.asarray(dataset["Times"][:]).reshape(-1)).decode("ascii")
    if time_value != PR83_EXPECTED_VALID_TIME:
        raise InitializationError("VALID_TIME_MISMATCH")
    expected_units = {
        "QCLOUD": "kg kg-1", "QICE": "kg kg-1", "QRAIN": "kg kg-1",
        "QGRAUP": "kg kg-1", "QNCLOUD": "kg-1", "QNICE": "kg-1",
        "QNRAIN": "kg-1", "QIB": "m3 kg-1", "QNCCN": "kg-1",
        "AL": "m3 kg-1", "ALB": "m3 kg-1",
    }
    for name, expected in expected_units.items():
        if name not in dataset.variables:
            raise InitializationError(f"MISSING_FIELDS:{name}")
        if _canonical_units(dataset.variables[name]) != expected:
            raise InitializationError(f"SERIALIZED_UNITS_MISMATCH:{name}")
        if dataset.variables[name].shape != (1, 39, 282, 234):
            raise InitializationError(f"SERIALIZED_SHAPE_MISMATCH:{name}")


def _same13_preflight(
    arrays: dict[str, np.ndarray], density: np.ndarray,
    policy: dict[str, Any] | None = None,
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray], dict[str, Any]]:
    is_pr84 = policy is not None and policy.get("schema") in (
        PR84_POLICY_SCHEMA, PR94_HYDRO_POLICY_SCHEMA
    )
    active_slice = _same13_active_slice(policy or {})
    active_density = density[active_slice]
    updated: dict[str, np.ndarray] = {}
    masks: dict[str, np.ndarray] = {}
    reports: dict[str, Any] = {}
    blockers: list[str] = []
    for mass_name, spec in SPECIES.items():
        mass = arrays[mass_name][active_slice].astype(np.float64)
        existing = arrays[spec["moment"]][active_slice]
        if np.any((mass == 0.0) & (existing != 0.0)):
            raise InitializationError(f"PR83_CONFLICTING_ZERO_MASS:{mass_name}")
        pidn = spec["pidn"]
        lambda_min = spec["lambda_min"]
        internal_cap: float | np.ndarray = spec["internal_cap"]
        qice_floor = None
        preparation_cap = internal_cap
        if is_pr84 and mass_name == "QICE":
            ice_policy = policy["species"]["QICE"]
            pidn = float(np.float32(ice_policy["source_pidni_binary32_value"]))
            lambda_min = float(ice_policy["lambda_min_m-1"])
            qice_floor, _, internal_cap = _pr84_qice_entry_guard(
                mass, active_density, pidni=pidn, lambda_min=lambda_min
            )
            # Keep the existing midpoint/cap path for low ice. High-mass cells
            # are replaced below by the exact minimum PSD-compatible REAL32 QN.
            preparation_cap = spec["internal_cap"]
        result, counts = _prepare_moments(
            mass, existing, active_density,
            threshold=0.0, lambda_min=lambda_min,
            lambda_max=spec["lambda_max"], power=spec["power"],
            pidn=pidn, internal_cap=preparation_cap,
        )
        if qice_floor is not None:
            high_ice_new = ((mass > 0.0) & (existing == 0.0)
                            & (internal_cap > np.float32(1.0e6)))
            result[high_ice_new] = qice_floor[high_ice_new]
            eligible = (mass > 0.0) & (existing == 0.0)
            counts["initialized_cells"] = int(np.count_nonzero(eligible & (result != 0.0)))
            counts["left_unchanged_infeasible_cells"] = int(
                np.count_nonzero(eligible & (result == 0.0))
            )
        positive_mass_missing = (mass > 0.0) & (result == 0.0)
        infeasible_count = int(np.count_nonzero(positive_mass_missing))
        if infeasible_count:
            locations = np.argwhere(positive_mass_missing)
            first = locations[0]
            k, j, i = (int(value) for value in first)
            minimum_internal_numbers = (
                mass[positive_mass_missing] * active_density[positive_mass_missing]
                * lambda_min ** spec["power"] / pidn
            )
            maximum_at = locations[int(np.argmax(minimum_internal_numbers))]
            max_k, max_j, max_i = (int(value) for value in maximum_at)
            min_internal_number = float(minimum_internal_numbers[0])
            max_internal_number = float(np.max(minimum_internal_numbers))
            reports[spec["moment"]] = {
                **counts,
                "positive_mass_without_representable_moment": infeasible_count,
                "first_infeasible_active_kji_zero_based": [k, j, i],
                "first_infeasible_wrf_ijk_one_based": [i + 2, j + 2, k + 1],
                "first_infeasible_mass_kg_kg-1": float(mass[k, j, i]),
                "first_infeasible_minimum_internal_number_m-3": min_internal_number,
                "maximum_minimum_internal_number_m-3": max_internal_number,
                "maximum_infeasible_wrf_ijk_one_based": [max_i + 2, max_j + 2, max_k + 1],
            }
            blockers.append(
                f"{spec['moment']}:{infeasible_count}:"
                f"first_wrf_ijk={i + 2},{j + 2},{k + 1}:"
                f"minimum_internal_number_m-3={min_internal_number:.9g}"
            )
        mask = result != existing
        full = np.array(arrays[spec["moment"]], copy=True)
        full[active_slice] = result
        updated[spec["moment"]] = full
        masks[spec["moment"]] = mask
        infeasibility_details = reports.get(spec["moment"], {})
        reports[spec["moment"]] = {
            **counts,
            **infeasibility_details,
            "positive_mass_without_representable_moment": infeasible_count,
            "research_fill_cutoff": "exact positive mass; no positive-mass floor or deletion",
        }
        if is_pr84 and mass_name == "QICE":
            reports[spec["moment"]].update({
                "internal_number_cap_mode": "SOURCE_PSD_COMPATIBLE_ENTRY_GUARD",
                "low_ice_internal_number_cap_m-3": 1.0e6,
                "source_lambda_min_m-1": lambda_min,
                "source_pidni_binary32": float(np.float32(pidn)),
                "source_pidni_binary32_hex": f"0x{int(np.asarray(np.float32(pidn)).view(np.uint32)):08x}",
                "high_mass_minimum_qnice_cells": int(np.count_nonzero(
                    (mass > 0.0) & (existing == 0.0)
                    & (internal_cap > np.float32(1.0e6))
                )),
                "high_mass_qnice_policy": (
                    "least REAL32 public number at or above the exact REAL64 "
                    "source lambda_min PSD bound"
                ),
                "entry_cap_formula": (
                    "max(1e6, REAL32(QNICE_minimum_REAL32 * dry_density_REAL32)); "
                    "QNICE satisfies public and REAL32 internal PSD floors"
                ),
            })
        if not infeasible_count:
            m_min = spec["m_min"]
            m_max = spec["m_max"]
            if is_pr84 and mass_name == "QICE":
                m_min = pidn / spec["lambda_max"] ** spec["power"]
                m_max = pidn / lambda_min ** spec["power"]
            reports[spec["moment"]]["preflight"] = _validate_mass_prior(
                mass, result, mass > 0.0,
                m_min=m_min, m_max=m_max,
                bound_source=("PR84 exact retained KDM6 REAL32 PIDNI and lambda bounds"
                              if is_pr84 and mass_name == "QICE" else PR83_BOUND_SOURCE),
            )
            internal_number = result.astype(np.float32) * active_density.astype(np.float32)
            if np.any((mass > 0.0) & (internal_number == 0.0)):
                raise InitializationError(
                    f"PR83_PRIOR_INTERNAL_NUMBER_UNREPRESENTABLE:{spec['moment']}"
                )
            applicable_cap = internal_cap if isinstance(internal_cap, np.ndarray) else np.float32(internal_cap)
            if np.any(internal_number > applicable_cap):
                raise InitializationError(
                    f"PR83_EXISTING_MOMENT_EXCEEDS_SOURCE_CAP:{spec['moment']}"
                )

    mass = arrays["QGRAUP"][active_slice].astype(np.float64)
    existing = arrays["QIB"][active_slice]
    if np.any((mass == 0.0) & (existing != 0.0)):
        raise InitializationError("PR83_CONFLICTING_ZERO_MASS:QGRAUP")
    active = (mass > 0.0) & (existing == 0.0)
    result = np.array(existing, copy=True)
    result[active] = (mass[active] / GRAUPEL["rho_center"]).astype(existing.dtype)
    if np.any((mass > 0.0) & (result == 0.0)):
        raise InitializationError("PR83_UNREPRESENTABLE_POSITIVE_GRAUPEL_MASS")
    if np.any((mass == 0.0) & (result != 0.0)):
        raise InitializationError("PR83_CONFLICTING_ZERO_GRAUPEL_MASS")
    volume_report = _validate_bulk_prior(
        mass, result, np.ones(mass.shape, dtype=bool),
        bound_source=PR83_BOUND_SOURCE,
    )
    full_volume = np.array(arrays["QIB"], copy=True)
    full_volume[active_slice] = result
    updated["QIB"] = full_volume
    masks["QIB"] = active
    reports["QIB"] = {
        "eligible_missing_cells": int(np.count_nonzero(active)),
        "initialized_cells": int(np.count_nonzero(active)),
        "preserved_existing_nonzero_cells": int(np.count_nonzero(existing > 0.0)),
        "positive_mass_without_representable_moment": 0,
        "research_fill_cutoff": "exact positive mass; no positive-mass floor or deletion",
        "density_center_kg_m-3": GRAUPEL["rho_center"],
        "density_support_kg_m-3": [GRAUPEL["rho_min"], GRAUPEL["rho_max"]],
        "preflight": volume_report,
    }
    if blockers:
        for report in reports.values():
            proposed = int(report.get("initialized_cells", 0))
            report["proposed_initialized_cells"] = proposed
            report["committed_initialized_cells"] = 0
            report["output_written"] = False
            report["preflight_outcome"] = "PROPOSED_ONLY_GLOBAL_REJECTION"
            report["count_semantics"] = "proposed preflight only; complete initialization rejected"
        raise InitializationError(
            ("PR84_SOURCE_CAP_INFEASIBLE:" if is_pr84 else
             "PR83_SOURCE_CAP_INFEASIBLE:") + ";".join(blockers),
            diagnostics=reports,
        )
    return updated, masks, reports


def _same13_evidence_hashes(
    source: Path, policy_file: Path, initializer_path: Path, policy: dict[str, Any]
) -> dict[str, str]:
    """Hash all consumed input and source evidence before/after preflight."""
    hashes = {
        "source_input": file_sha256(source),
        "policy": file_sha256(policy_file),
        "initializer": file_sha256(initializer_path),
    }
    source_metadata = policy["source"]
    source_keys = [
        "kdm6_source_path", "upstream_formula_comparison_path", "model_constants_path",
        "driver_path", "runtime_consumer_source_path", "runtime_consumer_executable_path",
        "runtime_consumer_archive_path", "runtime_consumer_build_receipt_path",
    ]
    if policy.get("schema") not in (PR84_POLICY_SCHEMA, PR94_HYDRO_POLICY_SCHEMA):
        source_keys.append("runtime_consumer_readback_receipt_path")
    for key in source_keys:
        hashes[key] = file_sha256(Path(source_metadata[key]))
    density_source = policy["density_source"]
    for key in ("wrf_source_start_path", "wrf_source_density_path"):
        hashes[key] = file_sha256(Path(density_source[key]))
    member = subprocess.run(
        ["ar", "p", source_metadata["runtime_consumer_archive_path"],
         source_metadata["runtime_consumer_object_member"]],
        check=True, capture_output=True,
    ).stdout
    hashes["runtime_consumer_object_member"] = hashlib.sha256(member).hexdigest()
    return hashes


def initialize_same13_copy(
    source_path: str | Path,
    output_path: str | Path,
    receipt_path: str | Path,
    *,
    policy_path: str | Path,
) -> dict[str, Any]:
    """Initialize a same-13UTC copy, failing closed if any positive Q is infeasible."""
    source = Path(source_path).resolve()
    output = Path(output_path).resolve()
    receipt_file = Path(receipt_path).resolve()
    policy_file = Path(policy_path).resolve()
    if (source == output or output == receipt_file or output.exists()
            or receipt_file.exists()):
        raise InitializationError("OUTPUT_AND_RECEIPT_MUST_BE_NEW_PATHS")
    policy = _validate_same13_policy_file(policy_file)
    is_pr84 = policy.get("schema") in (PR84_POLICY_SCHEMA, PR94_HYDRO_POLICY_SCHEMA)
    is_pr94_hydro = policy.get("schema") == PR94_HYDRO_POLICY_SCHEMA
    policy_hash = file_sha256(policy_file)
    initializer_path = Path(__file__).resolve()
    initializer_hash = file_sha256(initializer_path)
    source_hash = file_sha256(source)
    if is_pr94_hydro:
        binding = policy["hydro_input_binding"]
        if (source_hash != binding["wrfinput_sha256"]
                or str(source) != binding["wrfinput_path"]):
            raise InitializationError("PR94_HYDRO_SOURCE_INPUT_MISMATCH")
        source_role = "HYDRO"
    elif is_pr84 and source_hash not in PR84_EXPECTED_SOURCE_INPUTS.values():
        raise InitializationError("PR84_SOURCE_INPUT_HASH_MISMATCH")
    elif is_pr84:
        source_role = next(
            role for role, digest in PR84_EXPECTED_SOURCE_INPUTS.items()
            if digest == source_hash
        )
    elif source_hash != PR83_EXPECTED_INPUT_SHA256:
        raise InitializationError("PR83_SOURCE_INPUT_HASH_MISMATCH")
    evidence_hashes_before = _same13_evidence_hashes(
        source, policy_file, initializer_path, policy
    )

    required = {
        "QCLOUD", "QICE", "QRAIN", "QGRAUP", "QNCLOUD", "QNICE",
        "QNRAIN", "QIB", "QNCCN", "AL", "ALB",
    }
    with Dataset(source, "r") as original:
        _check_same13_input_metadata(original)
        missing = sorted(required - set(original.variables))
        if missing:
            raise InitializationError(f"MISSING_FIELDS:{','.join(missing)}")
        arrays = {
            name: _read_unmasked(original.variables[name], name)
            for name in required
        }
        density = _same13_dry_density(original)
        if any(value.shape != arrays["QCLOUD"].shape for value in arrays.values()):
            raise InitializationError("MOMENT_FIELD_SHAPE_MISMATCH")
        for name in ("QCLOUD", "QICE", "QRAIN", "QGRAUP"):
            if np.any(arrays[name] < 0.0):
                raise InitializationError(f"NEGATIVE_MASS_FIELD:{name}")
        for name in ("QCLOUD", "QICE", "QRAIN", "QGRAUP"):
            moment = SPECIES.get(name, {}).get("moment", "QIB")
            if np.any((arrays[name] == 0.0) & (arrays[moment] != 0.0)):
                raise InitializationError(f"PR83_CONFLICTING_ZERO_MASS:{name}")
        variable_hashes_before = {
            name: variable_sha256(variable)
            for name, variable in original.variables.items()
        }
        consumed_variable_hashes = {
            name: variable_hashes_before[name]
            for name in sorted(required)
        }

    active_slice = _same13_active_slice(policy)
    try:
        updated, initialized_masks, field_reports = _same13_preflight(arrays, density, policy)
    except InitializationError as error:
        # A physical infeasibility is a completed preflight result. Retain an
        # explicit receipt while leaving both the source and output untouched.
        cap_failure_prefix = ("PR84_SOURCE_CAP_INFEASIBLE:" if is_pr84 else
                              "PR83_SOURCE_CAP_INFEASIBLE:")
        if not str(error).startswith(cap_failure_prefix):
            raise
        evidence_hashes_after = _same13_evidence_hashes(
            source, policy_file, initializer_path, policy
        )
        if evidence_hashes_after != evidence_hashes_before:
            raise InitializationError("PR83_EVIDENCE_CHANGED_DURING_PREFLIGHT") from error
        if file_sha256(source) != source_hash:
            raise InitializationError("PR83_SOURCE_INPUT_CHANGED_DURING_PREFLIGHT") from error
        for report in error.diagnostics.values():
            proposed = int(report.get("initialized_cells", 0))
            report["proposed_initialized_cells"] = proposed
            report["committed_initialized_cells"] = 0
            report["output_written"] = False
            report["preflight_outcome"] = "PROPOSED_ONLY_GLOBAL_REJECTION"
            report["count_semantics"] = "proposed preflight only; complete initialization rejected"
        receipt = {
            "schema": "pr83_same13_native_moment_prior_receipt_v1",
            "policy_id": policy["policy_id"],
            "policy_sha256": policy_hash,
            "initializer_sha256": initializer_hash,
            "status": "BLOCKED_SOURCE_CAP_INFEASIBLE",
            "native_launch_authority": "NONE",
            "source_input": str(source),
            "source_input_sha256": source_hash,
            "source_input_unchanged": file_sha256(source) == source_hash,
            "evidence_integrity": "PASS_PRE_POST_HASHES_IDENTICAL",
            "evidence_sha256_before": evidence_hashes_before,
            "evidence_sha256_after": evidence_hashes_after,
            "consumed_variable_sha256": consumed_variable_hashes,
            "output_input": None,
            "output_input_created": False,
            "failure": str(error),
            "field_prior_preflight": error.diagnostics,
            "source_density": {
                "formula": "real32 reciprocal of real32 AL + ALB",
                "basis": "dry_air",
                "active_min_kg_m-3": float(np.min(density[active_slice])),
                "active_max_kg_m-3": float(np.max(density[active_slice])),
            },
            "same13_input_positive_mass_counts": {
                name: int(np.count_nonzero(arrays[name][active_slice] > 0.0)
                          ) for name in ("QCLOUD", "QICE", "QRAIN", "QGRAUP")
            },
            "committed_initialized_cells": 0,
            "limited_scope": "No complete prior was written because at least one positive mass has no moment satisfying both source PSD bounds and the native cap.",
        }
        if is_pr84:
            receipt["policy_schema"] = PR84_POLICY_SCHEMA
            receipt["source_input_role"] = source_role
            if is_pr94_hydro:
                receipt["policy_schema"] = PR94_HYDRO_POLICY_SCHEMA
                receipt["hydro_input_binding"] = policy["hydro_input_binding"]
        _write_receipt(receipt_file, receipt)
        return receipt

    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copy2(source, temporary)
        with Dataset(temporary, "r+") as candidate:
            for moment, values in updated.items():
                full = np.array(candidate.variables[moment][0], copy=True)
                full[active_slice] = values[active_slice]
                candidate.variables[moment][0] = full
        with Dataset(source, "r") as original, Dataset(temporary, "r") as candidate:
            _check_same13_input_metadata(candidate)
            if file_sha256(source) != source_hash:
                raise InitializationError("PR83_SOURCE_INPUT_CHANGED_DURING_INITIALIZATION")
            after_hashes = {
                name: variable_sha256(variable)
                for name, variable in candidate.variables.items()
            }
            changed_other = [
                name for name, before_hash in variable_hashes_before.items()
                if name not in updated and after_hashes[name] != before_hash
            ]
            if changed_other:
                raise InitializationError(f"UNEXPECTED_FIELD_CHANGES:{','.join(changed_other)}")
            for moment, expected_values in updated.items():
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
                stored = _read_unmasked(candidate.variables[spec["moment"]], spec["moment"])
                active_mass = arrays[mass_name][active_slice].astype(np.float64)
                m_min, m_max = spec["m_min"], spec["m_max"]
                bound_source = PR83_BOUND_SOURCE
                if is_pr84 and mass_name == "QICE":
                    ice_policy = policy["species"]["QICE"]
                    pidni = float(np.float32(ice_policy["source_pidni_binary32_value"]))
                    lambda_min = float(ice_policy["lambda_min_m-1"])
                    m_min = pidni / spec["lambda_max"] ** spec["power"]
                    m_max = pidni / lambda_min ** spec["power"]
                    bound_source = "PR84 exact retained KDM6 REAL32 PIDNI and lambda bounds"
                _validate_mass_prior(
                    active_mass, stored[active_slice], active_mass > 0.0,
                    m_min=m_min, m_max=m_max,
                    bound_source=bound_source,
                )
                if is_pr84 and mass_name == "QICE":
                    _, _, qice_cap = _pr84_qice_entry_guard(
                        active_mass, density[active_slice], pidni=pidni,
                        lambda_min=lambda_min,
                    )
                    internal_number = (stored[active_slice].astype(np.float32)
                                       * density[active_slice].astype(np.float32))
                    if np.any(internal_number > qice_cap):
                        raise InitializationError("PR84_QICE_READBACK_CAP_VIOLATION")
            graupel_mass = arrays["QGRAUP"][active_slice].astype(np.float64)
            volume = _read_unmasked(candidate.variables["QIB"], "QIB")[active_slice]
            _validate_bulk_prior(
                graupel_mass, volume, np.ones(volume.shape, dtype=bool),
                bound_source=PR83_BOUND_SOURCE,
            )
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)

    try:
        if file_sha256(source) != source_hash:
            raise InitializationError("PR83_SOURCE_INPUT_CHANGED_DURING_INITIALIZATION")
        if file_sha256(policy_file) != policy_hash:
            raise InitializationError("PR83_POLICY_CHANGED_DURING_INITIALIZATION")
        _validate_same13_policy_file(policy_file)
        if file_sha256(initializer_path) != initializer_hash:
            raise InitializationError("PR83_INITIALIZER_CHANGED_DURING_INITIALIZATION")
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    receipt = {
        "schema": "pr83_same13_native_moment_prior_receipt_v1",
        "policy_id": policy["policy_id"],
        "policy_sha256": policy_hash,
        "initializer_sha256": initializer_hash,
        "status": "RESEARCH_PRIOR_CREATED",
        "native_launch_authority": "NONE",
        "source_input": str(source),
        "source_input_sha256": source_hash,
        "consumed_variable_sha256": consumed_variable_hashes,
        "output_input": str(output),
        "output_input_sha256": file_sha256(output),
        "source_input_unchanged": file_sha256(source) == source_hash,
        "source_density": {
            "formula": "real32 reciprocal of real32 AL + ALB",
            "basis": "dry_air",
                "active_min_kg_m-3": float(np.min(density[active_slice])),
                "active_max_kg_m-3": float(np.max(density[active_slice])),
        },
        "field_prior_receipts": field_reports,
        "committed_initialized_cells": {
            name: int(report.get("initialized_cells", 0))
            for name, report in field_reports.items()
        },
        "all_other_variables_unchanged": True,
        "changed_nonmoment_variables": [],
        "limited_scope": "Explicit same-13UTC research PSD/density prior only; no observation recovery, forecast acceptance, or operational authority is implied.",
    }
    if is_pr84:
        receipt["policy_schema"] = PR84_POLICY_SCHEMA
        receipt["source_input_role"] = source_role
        if is_pr94_hydro:
            receipt["policy_schema"] = PR94_HYDRO_POLICY_SCHEMA
            receipt["hydro_input_binding"] = policy["hydro_input_binding"]
    try:
        _write_receipt(receipt_file, receipt)
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    return receipt


def _write_receipt(path: Path, receipt: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(receipt, stream, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(temporary_name, path)
    finally:
        Path(temporary_name).unlink(missing_ok=True)


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
    *,
    bound_source: str = BOUND_SOURCE,
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
        bound_source=bound_source,
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
    parser.add_argument("--denominator-trace", type=Path)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--same13-policy", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.same13_policy is not None:
            receipt = initialize_same13_copy(
                args.source, args.output, args.receipt,
                policy_path=args.same13_policy,
            )
        else:
            if args.denominator_trace is None:
                parser.error("--denominator-trace is required for the frozen PR61 mode")
            receipt = initialize_copy(
                args.source, args.output, args.denominator_trace,
                args.receipt,
                policy_path=args.policy,
            )
    except (OSError, RuntimeError, ValueError, TypeError, IndexError) as error:
        parser.error(str(error))
    output = receipt.get("output_input") or "no candidate written"
    print(f"{receipt['status']}: {output}")
    if receipt.get("output_input_sha256"):
        print(f"sha256: {receipt['output_input_sha256']}")
    return 2 if receipt["status"] == "BLOCKED_SOURCE_CAP_INFEASIBLE" else 0


if __name__ == "__main__":
    raise SystemExit(main())
