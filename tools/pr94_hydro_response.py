#!/usr/bin/env python3
"""Receipt-bound three-arm HYDRO response comparison for closed PR94 C4 runs."""
from __future__ import annotations

import argparse
import datetime as dt
import json
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


def validate_receipt_triplet(receipts: dict[str, dict[str, Any]]) -> None:
    """Require closed 600 s runs with the same C4 executable and matched boundary."""
    if set(receipts) != {"OFF", "COUPLED", "HYDRO"}:
        raise ValueError("expected OFF, COUPLED, and HYDRO receipts")
    common_boundary = None
    common_timestamps = None
    common_namelist = None
    for arm, receipt in receipts.items():
        if (receipt.get("arm") != arm or receipt.get("status") != "COMPLETE" or
                receipt.get("returncode") != 0 or receipt.get("final_completed_step") != 30):
            raise ValueError(f"{arm} receipt is not a complete 600-second run")
        if (receipt.get("executed_executable_sha256") != FROZEN_C4_EXECUTABLE or
                receipt.get("expected_executed_executable_sha256") != FROZEN_C4_EXECUTABLE):
            raise ValueError(f"{arm} did not execute the frozen C4 executable")
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


def analyze(hydro_root: Path, composition_path: Path = COMPOSITION,
            output: Path = EVIDENCE) -> dict[str, Any]:
    roots = {**RUNS, "HYDRO": hydro_root}
    histories, receipts, identities = {}, {}, {}
    for arm, root in roots.items():
        receipt_path = root / "receipt.json"
        receipts[arm] = json.loads(receipt_path.read_text())
        histories[arm], identities[arm] = verify_history(arm, root, receipts[arm])
    validate_receipt_triplet(receipts)
    grid_audit = verify_triplet_grid(roots)
    composition = json.loads(composition_path.read_text())["composed_qc_vertical_influence"]
    record: dict[str, Any] = {}
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
            for pair, first, second_arm in (("HYDRO_minus_OFF", "OFF", "HYDRO"),
                                            ("COUPLED_minus_HYDRO", "HYDRO", "COUPLED")):
                record[str(second)]["fields"].setdefault(name, {})[pair] = {
                    mask_name: {"selected_native_values": int(mask.sum()), "unit": unit,
                                **cloud.vector_metrics(arrays[first][mask], arrays[second_arm][mask])}
                    for mask_name, mask in masks.items()}
            check = pointwise_decomposition(arrays["OFF"], arrays["COUPLED"], arrays["HYDRO"])
            record[str(second)]["pointwise_decomposition"][name] = check
            decomposition.setdefault(name, []).append(check["max_abs_identity_residual"])
    hydro_binding = receipts["HYDRO"]["candidate_input_binding"]
    output.mkdir(parents=True, exist_ok=True)
    return {
        "schema": "pr94_hydro_response_v1", "physical_approval": "FAIL_OPEN",
        "run_scope": "Receipt-bound frozen-C4 OFF, COUPLED, and current-generation HYDRO 600-second histories at 60-second intervals.",
        "identities": identities, "paired_grid": grid_audit,
        "input_identity": {"candidate_wrfinput_sha256": {
            arm: receipts[arm].get("candidate_wrfinput_sha256") for arm in roots},
            "common_candidate_wrfbdy_sha256": receipts["OFF"]["candidate_wrfbdy_sha256"],
            "hydro_source_binding": hydro_binding,
            "interpretation": "HYDRO is a separately source-bound current-generation initial state; the paired differences describe run outcomes and do not isolate causal mechanisms."},
        "fixed_masks": mask_doc,
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
    parser.add_argument("--output", type=Path, default=EVIDENCE)
    args = parser.parse_args()
    result = analyze(args.hydro_run, output=args.output)
    path = args.output / "hydro_response.json"
    path.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
