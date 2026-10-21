#!/usr/bin/env python3
"""Receipt-bound three-arm HYDRO response comparison for closed runs."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/evidence/pr94_hydro_response_20261021"
COMPOSITION = ROOT / "docs/evidence/pr93_qc_chain_20261020/qc_vertical_composition.json"
RUNS = {
    "OFF": Path("/var/tmp/pr93_OFF_600s_c4_bound_20261020"),
    "COUPLED": Path("/var/tmp/pr93_COUPLED_600s_c4_bound_20261020"),
}
FROZEN_C4_EXECUTABLE = "20aaa6058797e7d1ec7a874ae92ed44f9ac19876ef2f14477b5eedb6a1ae44be"
SECONDS = tuple(range(0, 601, 60))
FIELDS = {
    "QVAPOR": "kg/kg dry", "QCLOUD": "kg/kg dry", "QICE": "kg/kg dry",
    "QRAIN": "kg/kg dry", "QSNOW": "kg/kg dry", "QGRAUP": "kg/kg dry",
    "pressure": "Pa", "geopotential": "m2 s-2",
    "U": "m s-1", "V": "m s-1", "W": "m s-1",
}

sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "tools"))
import pr94_cloud_response as cloud  # noqa: E402
from pr86_compare_response import load_history  # noqa: E402
from pr86_time_response import _input_binding_unchanged  # noqa: E402
from pr94_water_budget import verify_paired_grid  # noqa: E402


def _validated_executable_sha256(value: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-fA-F]{64}", value) is None:
        raise ValueError("expected executable SHA-256 must be 64 hexadecimal characters")
    return value.lower()


def validate_receipt_triplet(
        receipts: dict[str, dict[str, Any]], *,
        expected_executable_sha256: str = FROZEN_C4_EXECUTABLE) -> None:
    """Require closed 600 s runs with the expected executable and matched boundary."""
    expected_executable_sha256 = _validated_executable_sha256(expected_executable_sha256)
    if set(receipts) != {"OFF", "COUPLED", "HYDRO"}:
        raise ValueError("expected OFF, COUPLED, and HYDRO receipts")
    common_boundary = None
    common_timestamps = None
    common_namelist = None
    for arm, receipt in receipts.items():
        if (receipt.get("arm") != arm or receipt.get("status") != "COMPLETE" or
                receipt.get("returncode") != 0 or receipt.get("final_completed_step") != 30):
            raise ValueError(f"{arm} receipt is not a complete 600-second run")
        if (receipt.get("executed_executable_sha256") != expected_executable_sha256 or
                receipt.get("expected_executed_executable_sha256") != expected_executable_sha256):
            raise ValueError(f"{arm} did not execute the expected executable SHA-256")
        namelist = receipt.get("candidate_namelist_sha256")
        if not namelist:
            raise ValueError(f"{arm} lacks its physics namelist identity")
        if common_namelist is None:
            common_namelist = namelist
        elif namelist != common_namelist:
            raise ValueError("three arms do not share one candidate namelist")
        boundary = receipt.get("candidate_wrfbdy_sha256")
        if not boundary:
            raise ValueError(f"{arm} lacks its boundary identity")
        if common_boundary is None:
            common_boundary = boundary
        elif boundary != common_boundary:
            raise ValueError("three arms do not share one candidate wrfbdy")
        timestamps = [row.get("timestamp") for row in receipt.get("model_timestamps", [])]
        expected = [(dt.datetime(2026, 8, 16, 13) + dt.timedelta(seconds=20 * step)).strftime("%Y-%m-%d_%H:%M:%S")
                    for step in range(1, 31)]
        if timestamps != expected or timestamps != receipt.get("expected_model_timestamps"):
            raise ValueError(f"{arm} receipt does not contain the exact 30-step schedule")
        if common_timestamps is None:
            common_timestamps = timestamps
        elif timestamps != common_timestamps:
            raise ValueError("three arms have different model timestamp schedules")
    hydro_binding = receipts["HYDRO"].get("candidate_input_binding")
    contract = (hydro_binding or {}).get("comparison_contract") or {}
    if contract.get("current_generation") is not True:
        raise ValueError("HYDRO receipt is not bound to current-generation input")
    input_artifact = (hydro_binding or {}).get("artifacts", {}).get("wrfinput", {})
    boundary_artifact = (hydro_binding or {}).get("artifacts", {}).get("wrfbdy", {})
    if (not input_artifact.get("sha256") or
            input_artifact["sha256"] != receipts["HYDRO"].get("candidate_wrfinput_sha256")):
        raise ValueError("HYDRO candidate input does not match its source-bound receipt")
    if boundary_artifact.get("sha256") != receipts["HYDRO"].get("candidate_wrfbdy_sha256"):
        raise ValueError("HYDRO boundary does not match its source-bound receipt")
    if not _input_binding_unchanged(hydro_binding):
        raise ValueError("HYDRO source-bound input artifacts or chain receipts changed")
    if not (receipts["OFF"].get("candidate_wrfinput_sha256") !=
            receipts["HYDRO"].get("candidate_wrfinput_sha256")):
        raise ValueError("HYDRO input unexpectedly equals the OFF initial condition")


def verify_triplet_grid(roots: dict[str, Path]) -> dict[str, Any]:
    """Use the paired-grid audit and require HYDRO's grid to match both arms."""
    paired = verify_paired_grid({"OFF": roots["OFF"], "COUPLED": roots["COUPLED"]})
    verify_paired_grid({"OFF": roots["OFF"], "COUPLED": roots["HYDRO"]})
    return {**paired, "three_arm_timestamps_exact_match": True,
            "three_arm_coordinates_and_hybrid_coefficients_exact_match": True}


def verify_history(arm: str, root: Path, receipt: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    history, verified_receipt, identity = cloud.verify_run(arm, root)
    if verified_receipt != receipt:
        raise ValueError(f"{arm} receipt changed during history validation")
    return history, identity


def pointwise_decomposition(off: np.ndarray, coupled: np.ndarray,
                            hydro: np.ndarray) -> dict[str, float]:
    """Check C-O=(H-O)+(C-H) at points; never infer closure from RMS values."""
    if off.shape != coupled.shape or off.shape != hydro.shape:
        raise ValueError("decomposition arrays must have identical shape")
    if not all(np.isfinite(values).all() for values in (off, coupled, hydro)):
        raise ValueError("decomposition arrays must be finite")
    left = coupled - off
    right = (hydro - off) + (coupled - hydro)
    residual = left - right
    return {"max_abs_identity_residual": float(np.max(np.abs(residual))),
            "identity_holds_within_roundoff": bool(np.allclose(left, right, rtol=1e-12, atol=1e-14))}


def paired_field_metrics(arrays: dict[str, np.ndarray],
                         masks: dict[str, np.ndarray], unit: str) -> dict[str, Any]:
    """Measure each arm difference directly on the supplied arrays and masks."""
    result = {}
    for pair, first, second in (("HYDRO_minus_OFF", "OFF", "HYDRO"),
                                ("COUPLED_minus_HYDRO", "HYDRO", "COUPLED"),
                                ("COUPLED_minus_OFF", "OFF", "COUPLED")):
        result[pair] = {
            mask_name: {"selected_native_values": int(mask.sum()), "unit": unit,
                        **cloud.vector_metrics(arrays[first][mask], arrays[second][mask])}
            for mask_name, mask in masks.items()}
    return result


def analyze(hydro_root: Path, composition_path: Path = COMPOSITION,
            output: Path = EVIDENCE, *, off_root: Path = RUNS["OFF"],
            coupled_root: Path = RUNS["COUPLED"],
            expected_executable_sha256: str = FROZEN_C4_EXECUTABLE) -> dict[str, Any]:
    expected_executable_sha256 = _validated_executable_sha256(expected_executable_sha256)
    roots = {"OFF": off_root, "COUPLED": coupled_root, "HYDRO": hydro_root}
    histories, receipts, identities = {}, {}, {}
    for arm, root in roots.items():
        receipt_path = root / "receipt.json"
        receipts[arm] = json.loads(receipt_path.read_text())
        histories[arm], identities[arm] = verify_history(arm, root, receipts[arm])
    validate_receipt_triplet(receipts, expected_executable_sha256=expected_executable_sha256)
    grid_audit = verify_triplet_grid(roots)
    composition = json.loads(composition_path.read_text())["composed_qc_vertical_influence"]
    record: dict[str, Any] = {}
    face_records: dict[str, Any] = {}
    mask_doc = None
    decomposition: dict[str, Any] = {}
    for second in SECONDS:
        frame = second // 60
        expected = (dt.datetime(2026, 8, 16, 13) + dt.timedelta(seconds=second)).strftime("%Y-%m-%d_%H:%M:%S")
        loaded: dict[str, dict[str, np.ndarray]] = {}
        timestamps = {}
        for arm, history in histories.items():
            timestamp, fields, _ = load_history(history, frame)
            if timestamp != expected:
                raise ValueError(f"{arm} frame {frame} is {timestamp}, expected {expected}")
            loaded[arm], timestamps[arm] = fields, timestamp
        if len(set(timestamps.values())) != 1:
            raise ValueError(f"paired history timestamps differ at {second}s")
        if mask_doc is None:
            sample = loaded["OFF"]["QCLOUD"]
            masks = cloud.make_masks(composition, sample.shape)
            mask_doc = {name: int(mask.sum()) for name, mask in masks.items()}
        record[str(second)] = {"fields": {}, "pointwise_decomposition": {}}
        for name, unit in FIELDS.items():
            arrays = {arm: loaded[arm][name] for arm in roots}
            if len({values.shape for values in arrays.values()}) != 1:
                raise ValueError(f"{name} shape differs across arms")
            record[str(second)]["fields"][name] = paired_field_metrics(arrays, masks, unit)
            check = pointwise_decomposition(arrays["OFF"], arrays["COUPLED"], arrays["HYDRO"])
            record[str(second)]["pointwise_decomposition"][name] = check
            decomposition.setdefault(name, []).append(check["max_abs_identity_residual"])
        if second in (0, 60, 120, 600):
            face_fields = {arm: cloud.read_face_winds(history, frame)
                           for arm, history in histories.items()}
            face_records[str(second)] = {"fields": {}}
            for field in ("U_face", "V_face", "W_face"):
                arrays = {arm: face_fields[arm][field] for arm in roots}
                if len({values.shape for values in arrays.values()}) != 1:
                    raise ValueError(f"{field} shape differs across arms")
                face_records[str(second)]["fields"][field] = {
                    "shape_kji": list(arrays["OFF"].shape),
                    "unit": "m s-1",
                    "direct_pair_differences": {
                        pair: {"selected_native_values": int(arrays[first].size),
                               **cloud.vector_metrics(arrays[first], arrays[second_arm])}
                        for pair, first, second_arm in (
                            ("HYDRO_minus_OFF", "OFF", "HYDRO"),
                            ("COUPLED_minus_HYDRO", "HYDRO", "COUPLED"),
                            ("COUPLED_minus_OFF", "OFF", "COUPLED"))}}
    hydro_binding = receipts["HYDRO"]["candidate_input_binding"]
    output.mkdir(parents=True, exist_ok=True)
    return {
        "schema": "pr94_hydro_response_v1", "physical_approval": "FAIL_OPEN",
        "run_scope": (f"Receipt-bound executable SHA-256 {expected_executable_sha256} OFF, COUPLED, "
                      "and current-generation HYDRO 600-second histories at 60-second intervals."),
        "identities": identities, "paired_grid": grid_audit,
        "input_identity": {"candidate_wrfinput_sha256": {
            arm: receipts[arm].get("candidate_wrfinput_sha256") for arm in roots},
            "common_candidate_wrfbdy_sha256": receipts["OFF"]["candidate_wrfbdy_sha256"],
            "hydro_source_binding": hydro_binding,
            "interpretation": "HYDRO is a separately source-bound current-generation initial state; the paired differences describe run outcomes and do not isolate causal mechanisms."},
        "fixed_masks": mask_doc,
        "actual_staggered_face_winds": {
            "scope": "Actual U, V, and W C-grid face arrays read from the saved histories using pr94_cloud_response.read_face_winds; outer mass-grid ring cropped as in PR94. Full declared active face crop; separate from the 613-cell mass-point mask and mass-point U/V/W statistics.",
            "times_seconds": [0, 60, 120, 600],
            "fields": face_records,
            "limits": ["No face flux, continuity, or mass-wind closure is inferred."]},
        "mask_definition": "Reused source-composed 613 native QC support, fixed clipped 2/5-cell Chebyshev buffers, and full active history domain; all masks are unchanged at every time.",
        "records": record,
        "pointwise_identity": {name: {"max_abs_residual_over_times": max(values),
                                        "meaning": "C-O=(H-O)+(C-H) checked on actual arrays; this is algebraic decomposition only, not additive RMS or causal attribution."}
                               for name, values in decomposition.items()},
        "limits": ["RMS values are not additive; only the pointwise field identity is decomposed.",
                   "No causal attribution, observation-skill claim, or continuity closure is inferred.",
                   "The report is limited to saved history times and the fixed source-derived masks."],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hydro-run", type=Path, required=True)
    parser.add_argument("--off-run", type=Path, default=RUNS["OFF"])
    parser.add_argument("--coupled-run", type=Path, default=RUNS["COUPLED"])
    parser.add_argument("--expected-executable-sha256", default=FROZEN_C4_EXECUTABLE)
    parser.add_argument("--output", type=Path, default=EVIDENCE)
    args = parser.parse_args()
    result = analyze(args.hydro_run, output=args.output, off_root=args.off_run,
                     coupled_root=args.coupled_run,
                     expected_executable_sha256=args.expected_executable_sha256)
    path = args.output / "hydro_response.json"
    path.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
