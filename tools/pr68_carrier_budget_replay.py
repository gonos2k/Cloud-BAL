#!/usr/bin/env python3
"""Decompose the PR67 same-call water residual by its mass carrier.

This replays immutable PR67 captures. It does not alter or run WRF, and a
nonzero residual remains an open budget term rather than a closure result.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import stat
from pathlib import Path
from typing import Any

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

from native_kdm6_call_geometry import active_geometry_measure, parse_geometry
from native_kdm6_trace import read_dump
from pr67_kdm6_process_budget import WATER_FIELDS, analyze, parse_process_capture


class ReplayError(ValueError):
    """Capture arrays cannot support a strict carrier comparison."""


def _finite_array(array: np.ndarray, label: str, *, positive: bool = False) -> None:
    if not np.isfinite(array).all() or (positive and np.any(array <= 0)):
        raise ReplayError(f"{label} must be finite" + (" and positive" if positive else ""))


def _finite_fsum(values: Any, label: str) -> float:
    try:
        result = math.fsum(values)
    except OverflowError as exc:
        raise ReplayError(f"{label} overflowed during reduction") from exc
    if not math.isfinite(result):
        raise ReplayError(f"{label} is nonfinite")
    return result


def decompose_carriers(hybrid_global_delta: float, native_global_delta: float,
                       hybrid_cell_delta: float, native_cell_delta: float,
                       precipitation_kg: float, reported_residual_kg: float) -> dict[str, float | bool]:
    """Reconcile independent cellwise carrier terms to the reported global budget."""
    values = (hybrid_global_delta, native_global_delta, hybrid_cell_delta,
              native_cell_delta, precipitation_kg, reported_residual_kg)
    if not all(math.isfinite(value) for value in values):
        raise ReplayError("budget operands must be finite")
    try:
        native_cell_residual = math.fsum((native_cell_delta, precipitation_kg))
        carrier_choice = math.fsum((hybrid_cell_delta, -native_cell_delta))
        hybrid_global_reduction = math.fsum((hybrid_global_delta, -hybrid_cell_delta))
        native_global_reduction = math.fsum((native_global_delta, -native_cell_delta))
        reconstructed = math.fsum((native_cell_residual, carrier_choice, hybrid_global_reduction))
        error = reported_residual_kg - reconstructed
        operand_scale = math.fsum(abs(value) for value in values)
    except OverflowError as exc:
        raise ReplayError("finite budget operands overflowed during scalar reduction") from exc
    tolerance = 16.0 * np.finfo(np.float64).eps * max(1.0, operand_scale)
    if abs(error) > tolerance:
        raise ReplayError("carrier decomposition exceeds its operand-based roundoff bound")
    return {
        "hybrid_global_delta_kg": hybrid_global_delta,
        "native_global_delta_kg": native_global_delta,
        "hybrid_cell_delta_kg": hybrid_cell_delta,
        "native_cell_delta_kg": native_cell_delta,
        "mapped_precipitation_kg": precipitation_kg,
        "reported_hybrid_residual_kg": reported_residual_kg,
        "native_cell_residual_kg": native_cell_residual,
        "carrier_choice_term_kg": carrier_choice,
        "hybrid_global_reduction_correction_kg": hybrid_global_reduction,
        "native_global_reduction_correction_kg": native_global_reduction,
        "reconciliation_error_kg": error,
        "reconciliation_roundoff_bound_kg": tolerance,
        "reconciliation_within_bound": bool(abs(error) <= tolerance),
    }


def _summation_bound(term_count: int, absolute_operand_sum: float,
                     epsilon: float = np.finfo(np.float64).eps,
                     operation_factor: float = 1.0) -> float:
    """Conservative sequential-sum roundoff bound from array operand scale."""
    if term_count < 1 or not math.isfinite(absolute_operand_sum):
        raise ReplayError("array reduction has empty support or nonfinite operands")
    product = term_count * epsilon
    if product >= 1.0:
        raise ReplayError("array reduction is too large for a finite roundoff bound")
    gamma = product / (1.0 - product)
    bound = float(operation_factor * gamma * absolute_operand_sum)
    if not math.isfinite(bound):
        raise ReplayError("array reduction roundoff bound is nonfinite")
    return bound


def _require_regular_file(path: Path, label: str) -> None:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError as exc:
        raise ReplayError(f"missing {label}: {path}") from exc
    if not stat.S_ISREG(mode) or path.is_symlink():
        raise ReplayError(f"{label} must be a regular nonsymlink file")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_receipt_inputs(receipt: dict[str, Any], run_root: Path) -> int:
    """Recheck all declared input identities against the preserved run tree."""
    if (receipt.get("returncode") != 0 or receipt.get("input_integrity") != "PASS" or
            receipt.get("output_isolation") != "PASS"):
        raise ReplayError("run receipt is not a successful isolated run")
    rows = receipt.get("inputs")
    if not isinstance(rows, list) or not rows:
        raise ReplayError("run receipt has no declared input inventory")
    seen: set[Path] = set()
    for row in rows:
        try:
            path = Path(row["path"])
            before, after = row["sha256_before"], row["sha256_after"]
        except (KeyError, TypeError) as exc:
            raise ReplayError("run input receipt row is malformed") from exc
        if (not path.is_absolute() or not isinstance(before, str) or
                not isinstance(after, str) or not re.fullmatch(r"[0-9a-f]{64}", before) or
                not re.fullmatch(r"[0-9a-f]{64}", after) or before != after):
            raise ReplayError("run input receipt hashes are malformed or changed")
        resolved = path.resolve()
        try:
            resolved.relative_to(run_root.resolve())
        except ValueError as exc:
            raise ReplayError("declared run input is outside the isolated run root") from exc
        if resolved in seen:
            raise ReplayError("run receipt contains duplicate input paths")
        seen.add(resolved)
        _require_regular_file(path, "declared run input")
        if _sha256_file(path) != before:
            raise ReplayError("current declared run input does not match its receipt hash")
    return len(rows)


def validate_runtime_provenance(receipt_path: Path, runtime_manifest_path: Path,
                                source_path: Path, manifest_path: Path) -> dict[str, Any]:
    """Bind the selected combined variant to its immutable build evidence."""
    _require_regular_file(receipt_path, "run receipt")
    _require_regular_file(runtime_manifest_path, "runtime reference manifest")
    _require_regular_file(source_path, "retained native source")
    _require_regular_file(manifest_path, "PR67 evidence manifest")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    manifest = json.loads(runtime_manifest_path.read_text(encoding="utf-8"))
    evidence = json.loads(manifest_path.read_text(encoding="utf-8"))
    build_path = manifest_path.parent / evidence["build_provenance_file"]
    _require_regular_file(build_path, "PR67 build provenance")
    build_hash = hashlib.sha256(build_path.read_bytes()).hexdigest()
    if build_hash != evidence.get("build_provenance_sha256"):
        raise ReplayError("PR67 build provenance does not match its evidence manifest")
    build = json.loads(build_path.read_text(encoding="utf-8"))
    run_root = Path(receipt.get("run_root", ""))
    if not run_root.is_absolute() or run_root.resolve() != receipt_path.parent.resolve():
        raise ReplayError("receipt run root does not match its containing directory")
    executable_path = run_root / "wrf.exe"
    _require_regular_file(executable_path, "run executable")
    live_input_count = validate_receipt_inputs(receipt, run_root)
    executable_hash = _sha256_file(executable_path)
    executable_input = next((item for item in receipt.get("inputs", [])
                             if Path(item["path"]).resolve() == executable_path.resolve()), None)
    if (executable_input is None or executable_input.get("sha256_before") != executable_hash or
            executable_input.get("sha256_after") != executable_hash):
        raise ReplayError("run executable does not match the isolated-run input receipt")
    manifest_hashes = {
        key: manifest.get(key)
        for key in ("source_observer_sha256", "observer_object_sha256", "observer_executable_sha256")
    }
    if any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
           for value in manifest_hashes.values()):
        raise ReplayError("runtime manifest has missing or malformed provenance hashes")
    source_hash = _sha256_file(source_path)
    combined = evidence.get("research_objects", {})
    combined_build = build.get("selected_artifacts", {})
    combined_run = build.get("runs", {}).get("combined", {})
    expected_source = combined.get("combined_generated_source_sha256")
    expected_object = combined.get("combined_object_sha256")
    expected_executable = combined.get("combined_executable_sha256")
    if (source_hash != expected_source or
            combined_build.get("generated_combined_research_source", {}).get("sha256") != expected_source or
            combined_build.get("combined_kdm_object", {}).get("sha256") != expected_object or
            combined_run.get("executable", {}).get("sha256") != expected_executable or
            expected_executable != executable_hash or
            combined_run.get("executable", {}).get("sha256") !=
            next((item.get("sha256_before") for item in receipt.get("inputs", [])
                  if Path(item["path"]).resolve() == executable_path.resolve()), None)):
        raise ReplayError("selected combined source/object/executable provenance does not match evidence")
    object_record = combined_build["combined_kdm_object"]
    object_path = Path(object_record["path"])
    _require_regular_file(object_path, "selected combined KDM6 object")
    object_hash = _sha256_file(object_path)
    if object_hash != expected_object:
        raise ReplayError("selected combined KDM6 object does not match build provenance")
    return {
        "receipt_bound_run_executable": {"path": str(executable_path), "sha256": executable_hash},
        "receipt_declared_inputs": {
            "count": live_input_count,
            "live_current_bytes_match_receipt": True,
            "scope": "all declared input files in the preserved run tree; not full runtime process closure",
        },
        "retained_native_source_reference": {"path": str(source_path), "sha256": source_hash,
                                             "matches_selected_combined_source": True},
        "selected_combined_source_object_executable": {
            "source_sha256": source_hash,
            "object_path": str(object_path),
            "object_sha256": object_hash,
            "executable_sha256": executable_hash,
            "binding": "MATCHES_IMMUTABLE_PR67_COMBINED_EVIDENCE",
        },
        "pr67_evidence_manifest_sha256": _sha256_file(manifest_path),
        "pr67_build_provenance_sha256": build_hash,
        "runtime_reference_manifest_sha256": _sha256_file(runtime_manifest_path),
        "reference_manifest_claims": manifest_hashes,
        "reference_manifest_source_matches_selected_source":
            manifest_hashes["source_observer_sha256"] == source_hash,
        "reference_manifest_object_matches_selected_object":
            manifest_hashes["observer_object_sha256"] == object_hash,
        "reference_manifest_executable_matches_receipt":
            manifest_hashes["observer_executable_sha256"] == executable_hash,
        "reference_manifest_role": "AUXILIARY_CONTROL_VARIANT_REFERENCE",
        "full_host_and_expanded_compiler_argv": "PARTIAL_NOT_ESTABLISHED",
    }


def validate_same_call(pre: dict[str, Any], post: dict[str, Any],
                       native_density: np.ndarray, native_delz: np.ndarray) -> None:
    """Require identical KDM call headers and frozen source carrier fields."""
    if (pre["stage"], pre["itimestep"], pre["bounds"], pre["params"]) != (
            1, post["itimestep"], post["bounds"], post["params"]):
        raise ReplayError("pre/post KDM captures do not describe the same supported call")
    if post["stage"] != 2 or pre["itimestep"] < 1:
        raise ReplayError("KDM stages or first-call timestep are unsupported")
    for field, carrier_values in (("DEN", native_density), ("DELZ", native_delz)):
        before = pre["fields"][field].transpose(1, 0, 2)
        after = post["fields"][field].transpose(1, 0, 2)
        if before.shape != carrier_values.shape or after.shape != carrier_values.shape:
            raise ReplayError(f"captured {field} does not match the native process carrier")
        if not np.array_equal(before, after) or not np.array_equal(before, carrier_values):
            raise ReplayError(f"captured {field} changed or differs from the native carrier")


def replay(process_path: Path, geometry_path: Path, pre_path: Path, post_path: Path,
           receipt_path: Path, source_path: Path, manifest_path: Path) -> dict[str, Any]:
    base = analyze(process_path, geometry_path, pre_path, post_path, receipt_path)
    pre, post = read_dump(pre_path), read_dump(post_path)
    process = parse_process_capture(process_path)
    geo = parse_geometry(geometry_path.read_bytes())[0]
    measure = active_geometry_measure(geo, {"bounds": pre["bounds"]})
    rows = [process[index:index + 3] for index in range(0, len(process), 3)]
    if not rows or len(rows) != measure["area"].shape[0]:
        raise ReplayError("process rows do not span active map rows")
    if any(row[0]["lat"] != pre["bounds"]["jts"] + index for index, row in enumerate(rows)):
        raise ReplayError("process row coordinates do not match the KDM6 active j bounds")
    dend = np.stack([row[0]["density"] for row in rows], axis=1)
    delz = np.stack([row[0]["delz"] for row in rows], axis=1)
    bottom_dend = np.stack([row[2]["density"] for row in rows], axis=0)
    bottom_delz = np.stack([row[2]["delz"] for row in rows], axis=0)
    if not np.array_equal(dend[0, :, :], bottom_dend) or not np.array_equal(delz[0, :, :], bottom_delz):
        raise ReplayError("captured bottom carrier changed between process and precipitation stages")
    validate_same_call(pre, post, dend, delz)
    native_mass = dend * delz * measure["area"][None, :, :]
    hybrid_mass = measure["dry_mass"]
    _finite_array(native_mass, "native DEND*DELZ*area mass", positive=True)
    _finite_array(hybrid_mass, "hybrid dry-air mass", positive=True)
    if native_mass.shape != hybrid_mass.shape:
        raise ReplayError("native and hybrid carrier shapes differ")

    native_ratio = native_mass / hybrid_mass
    if not np.isfinite(native_ratio).all() or np.any(native_ratio <= 0):
        raise ReplayError("native-to-hybrid carrier ratio is invalid")
    species: dict[str, dict[str, float]] = {}
    hybrid_cell_delta_terms: list[float] = []
    native_cell_delta_terms: list[float] = []
    hybrid_legacy_float32_cell_delta_kg = 0.0
    native_legacy_float32_cell_delta_kg = 0.0
    long_type = np.longdouble
    hybrid_delta_extended = long_type(0.0)
    native_delta_extended = long_type(0.0)
    direct_carrier_extended = long_type(0.0)
    extended_absolute_operand_sum = long_type(0.0)
    hybrid_pre_cell = np.zeros_like(hybrid_mass, dtype=np.float64)
    hybrid_post_cell = np.zeros_like(hybrid_mass, dtype=np.float64)
    native_pre_cell = np.zeros_like(native_mass, dtype=np.float64)
    native_post_cell = np.zeros_like(native_mass, dtype=np.float64)
    for field in WATER_FIELDS:
        before_raw = pre["fields"][field].transpose(1, 0, 2)
        after_raw = post["fields"][field].transpose(1, 0, 2)
        before = before_raw.astype(np.float64)
        after = after_raw.astype(np.float64)
        if before.shape != hybrid_mass.shape or after.shape != native_mass.shape:
            raise ReplayError(f"{field} does not match active carrier shape")
        _finite_array(before, f"pre {field}")
        _finite_array(after, f"post {field}")
        hybrid_before = before * hybrid_mass
        hybrid_after = after * hybrid_mass
        native_before = before * native_mass
        native_after = after * native_mass
        for label, product in ((f"hybrid pre {field}", hybrid_before),
                               (f"hybrid post {field}", hybrid_after),
                               (f"native pre {field}", native_before),
                               (f"native post {field}", native_after)):
            _finite_array(product, label)
        hybrid_pre_cell += hybrid_before
        hybrid_post_cell += hybrid_after
        native_pre_cell += native_before
        native_post_cell += native_after
        hybrid_delta_cell = float(np.sum((after - before) * hybrid_mass, dtype=np.float64))
        native_delta_cell = float(np.sum((after - before) * native_mass, dtype=np.float64))
        legacy_delta = (after_raw - before_raw).astype(np.float64)
        hybrid_legacy_delta = legacy_delta * hybrid_mass
        native_legacy_delta = legacy_delta * native_mass
        delta_extended = after_raw.astype(long_type) - before_raw.astype(long_type)
        hybrid_extended = hybrid_mass.astype(long_type)
        native_extended = native_mass.astype(long_type)
        hybrid_extended_delta = delta_extended * hybrid_extended
        native_extended_delta = delta_extended * native_extended
        direct_carrier_delta = delta_extended * (hybrid_extended - native_extended)
        _finite_array((after - before) * hybrid_mass, f"hybrid delta {field}")
        _finite_array((after - before) * native_mass, f"native delta {field}")
        _finite_array(hybrid_legacy_delta, f"legacy float32 hybrid delta {field}")
        _finite_array(native_legacy_delta, f"legacy float32 native delta {field}")
        _finite_array(direct_carrier_delta, f"direct carrier difference {field}")
        _finite_array(hybrid_extended_delta, f"extended hybrid delta {field}")
        _finite_array(native_extended_delta, f"extended native delta {field}")
        hybrid_delta_extended += np.sum(hybrid_extended_delta, dtype=long_type)
        native_delta_extended += np.sum(native_extended_delta, dtype=long_type)
        direct_carrier_extended += np.sum(direct_carrier_delta, dtype=long_type)
        extended_absolute_operand_sum += (
            np.sum(np.abs(hybrid_extended_delta), dtype=long_type)
            + np.sum(np.abs(native_extended_delta), dtype=long_type)
            + np.sum(np.abs(direct_carrier_delta), dtype=long_type))
        hybrid_cell_delta_terms.append(hybrid_delta_cell)
        native_cell_delta_terms.append(native_delta_cell)
        hybrid_legacy_float32_cell_delta_kg += float(np.sum(hybrid_legacy_delta, dtype=np.float64))
        native_legacy_float32_cell_delta_kg += float(np.sum(native_legacy_delta, dtype=np.float64))
        species[field] = {
            "hybrid_pre_kg": float(np.sum(hybrid_before, dtype=np.float64)),
            "hybrid_post_kg": float(np.sum(hybrid_after, dtype=np.float64)),
            "hybrid_cell_delta_kg": hybrid_delta_cell,
            "hybrid_legacy_float32_cell_delta_kg": float(np.sum(hybrid_legacy_delta, dtype=np.float64)),
            "native_pre_kg": float(np.sum(native_before, dtype=np.float64)),
            "native_post_kg": float(np.sum(native_after, dtype=np.float64)),
            "native_cell_delta_kg": native_delta_cell,
            "native_legacy_float32_cell_delta_kg": float(np.sum(native_legacy_delta, dtype=np.float64)),
        }
    for label, values in (("hybrid pre state", hybrid_pre_cell), ("hybrid post state", hybrid_post_cell),
                          ("native pre state", native_pre_cell), ("native post state", native_post_cell)):
        _finite_array(values, label)
    hybrid_cell_delta_kg = _finite_fsum(hybrid_cell_delta_terms, "hybrid cellwise state change")
    native_cell_delta_kg = _finite_fsum(native_cell_delta_terms, "native cellwise state change")
    native_pre_kg = _finite_fsum((species[field]["native_pre_kg"] for field in WATER_FIELDS),
                                 "native pre-state mass")
    native_post_kg = _finite_fsum((species[field]["native_post_kg"] for field in WATER_FIELDS),
                                  "native post-state mass")
    native_global_delta_kg = native_post_kg - native_pre_kg
    if not math.isfinite(native_global_delta_kg):
        raise ReplayError("native global state change is nonfinite")
    precipitation_kg = base["surface_precipitation"]["mapped_increment_kg"]
    _finite_array(np.asarray([hybrid_delta_extended, native_delta_extended,
                              direct_carrier_extended, extended_absolute_operand_sum]),
                  "extended carrier reductions")
    direct_carrier_term_kg = float(direct_carrier_extended)
    carrier_extended_identity_error_kg = float(
        (hybrid_delta_extended - native_delta_extended) - direct_carrier_extended)
    separate_carrier_term_kg = _finite_fsum((hybrid_cell_delta_kg, -native_cell_delta_kg),
                                             "separate carrier term")
    carrier_direct_reduction_difference_kg = separate_carrier_term_kg - direct_carrier_term_kg
    absolute_operand_sum = float(extended_absolute_operand_sum)
    carrier_direct_bound_kg = _summation_bound(
        len(WATER_FIELDS) * int(np.prod(hybrid_mass.shape)),
        absolute_operand_sum,
        epsilon=float(np.finfo(long_type).eps),
        operation_factor=4.0,
    )
    carrier_direct_within_bound = bool(abs(carrier_extended_identity_error_kg) <= carrier_direct_bound_kg)
    if not carrier_direct_within_bound:
        raise ReplayError("direct carrier-difference replay exceeds its array roundoff bound")
    split = decompose_carriers(base["six_water"]["delta_kg"], native_post_kg - native_pre_kg,
                               hybrid_cell_delta_kg, native_cell_delta_kg, precipitation_kg,
                               base["focused_residual_kg"])
    split["native_pre_kg"] = native_pre_kg
    split["native_post_kg"] = native_post_kg
    split["hybrid_pre_kg"] = base["six_water"]["pre_kg"]
    split["hybrid_post_kg"] = base["six_water"]["post_kg"]
    split["hybrid_species_delta_sum_kg"] = math.fsum(species[field]["hybrid_cell_delta_kg"]
                                                     for field in WATER_FIELDS)
    split["hybrid_float32_subtraction_effect_kg"] = (
        hybrid_legacy_float32_cell_delta_kg - hybrid_cell_delta_kg)
    split["native_float32_subtraction_effect_kg"] = (
        native_legacy_float32_cell_delta_kg - native_cell_delta_kg)
    split["direct_carrier_difference_term_kg"] = direct_carrier_term_kg
    split["carrier_extended_identity_error_kg"] = carrier_extended_identity_error_kg
    split["carrier_direct_reduction_difference_kg"] = carrier_direct_reduction_difference_kg
    split["carrier_direct_array_roundoff_bound_kg"] = carrier_direct_bound_kg
    split["carrier_direct_within_array_roundoff_bound"] = carrier_direct_within_bound
    provenance = validate_runtime_provenance(
        receipt_path, receipt_path.parent / "runtime_reference_manifest.json", source_path,
        manifest_path)
    return {
        "schema": "pr68_carrier_budget_decomposition_v1",
        "support": {
            "status": "PASS_SCOPED_CAPTURE_AND_NUMERICAL_RECONCILIATION",
            "scope": "one PR67 public KDM6 call, active tile only",
            "time_step": {"kdm6_dt_s": base["extent"]["dtcld_s"],
                          "active_extent": base["extent"]},
            "active_i_j_k": base["extent"],
            "receipt": base["receipt"],
            "capture_sha256": base["capture_sha256"],
            "provenance": provenance,
            "kdm6_itimestep": base["geometry_audit"]["kdm6_timestep"],
            "maximum_native_to_hybrid_relative_difference": float(
                np.max(np.abs(native_mass - hybrid_mass) / hybrid_mass)),
        },
        "species": species,
        "decomposition": split,
        "unmeasured_terms": [
            "Per-process internal water transfer closure for vapor, cloud, rain, snow, and graupel.",
            "Float32 tendency/update rounding, nonnegative clipping, and substep accumulation effects separated from physical transfers.",
            "A full source-level budget of all boundary, storage, and sedimentation terms over every KDM6 substep.",
            "Independent validation that captured DEND*DELZ*area is the correct extensive carrier for all six-water state fields throughout the full call.",
        ],
        "limits": [
            "A carrier decomposition is algebraic attribution, not closure or scientific validation.",
            "The native carrier is source-defined for local KDM6 sedimentation; its extension to all six water fields is diagnostic only.",
            "No PBL matrix or tendency is changed by this replay.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("process", type=Path)
    parser.add_argument("geometry", type=Path)
    parser.add_argument("pre", type=Path)
    parser.add_argument("post", type=Path)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--source", type=Path, required=True,
                        help="selected combined generated KDM6 source file")
    parser.add_argument("--manifest", type=Path, required=True,
                        help="immutable PR67 evidence manifest that selects the combined variant")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = replay(args.process, args.geometry, args.pre, args.post, args.receipt,
                        args.source, args.manifest)
    except (OSError, ValueError, KeyError, IndexError) as exc:
        parser.error(str(exc))
    encoded = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
