#!/usr/bin/env python3
"""Integrate fixed-mask PR102 saved-history RMS responses over time."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path


SCHEDULE = tuple(range(0, 601, 60))
FIELDS = {"pressure": "Pa", "Phi": "m2/s2", "W": "m/s", "QC": "kg/kg dry"}
SOURCE_FIELDS = {"pressure": "pressure", "Phi": "geopotential", "W": "W", "QC": "QCLOUD"}
ARMS = {"H": "HYDRO", "C": "COUPLED", "P": "P", "N": "STRUCTURED"}
REGIONS = {"support": 613, "buffer": 7644}
A_CANDIDATE_PATH = Path("/var/tmp/pr103_amplitude_generation_20261026/candidate/wrfinput_d01")
A_CANDIDATE_SHA256 = "9038d0a26896a630b7048091a97a2c0055b26934513392195eb8e609626e74e2"
A_PROPOSAL_PATH = Path("/var/tmp/pr103_amplitude_generation_20261026/candidate/wrfinput_d01.proposal.json")
A_PROPOSAL_SHA256 = "93821aa86b188a91a7f43de9e6c5d49815bde71fe92faa7a59cc3a340c78057f"
A_EXECUTABLE_SHA256 = "387f46df03e87b8693a57fdefc4ddb62a848e7a946ce417ee8b3d54d2c62cc9a"
A_BOUNDARY_SHA256 = "885591e6008e219d0b0f8a5a9c6cc3b48eae097d951d1ed731234108706b25d7"
A_NAMELIST_SHA256 = "58c194b8846d25a6c7cbfedac1477fbf65fcc1a12705c8cb11851096ee7d2fc8"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _finite_number(value, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")
    return float(value)


def _read_series(readback: dict, arm: str, field: str, region: str) -> list[float]:
    if readback.get("fields", {}).get(field, {}).get("unit") != FIELDS[field]:
        raise ValueError(f"{field} unit differs from the fixed contract")
    metrics = readback.get("metrics")
    if not isinstance(metrics, dict):
        raise ValueError("readback metrics are missing")
    values = []
    for second in SCHEDULE:
        at_time = metrics.get(str(second))
        if not isinstance(at_time, dict) or field not in at_time:
            raise ValueError(f"missing {field} metrics at {second}s")
        item = at_time[field]
        if item.get("unit") != FIELDS[field]:
            raise ValueError(f"{field} metric unit differs at {second}s")
        arm_metric = item.get("minus_OFF", {}).get(arm)
        if not isinstance(arm_metric, dict):
            raise ValueError(f"missing {arm} minus_OFF at {second}s for {field}")
        metric = arm_metric.get(region)
        if not isinstance(metric, dict) or metric.get("count") != REGIONS[region]:
            raise ValueError(f"{region} count/shape contract differs at {second}s for {field}/{arm}")
        rms = _finite_number(metric.get("rms"), f"{field}/{arm}/{region} RMS at {second}s")
        if rms < 0:
            raise ValueError(f"{field}/{arm}/{region} RMS at {second}s must be nonnegative")
        values.append(rms)
    return values


def _read_pair_series(readback: dict, pair: str, field: str, region: str) -> list[float]:
    by_time = readback.get("paired_metrics", {}).get(pair)
    if not isinstance(by_time, dict):
        raise ValueError(f"missing explicit paired series {pair}")
    values = []
    for second in SCHEDULE:
        item = by_time.get(str(second), {}).get(field)
        if not isinstance(item, dict) or item.get("unit") != FIELDS[field]:
            raise ValueError(f"missing or wrong-unit {pair}/{field} at {second}s")
        metric = item.get(region)
        if not isinstance(metric, dict) or metric.get("count") != REGIONS[region]:
            raise ValueError(f"{region} count/shape contract differs at {second}s for {field}/{pair}")
        rms = _finite_number(metric.get("rms"), f"{field}/{pair}/{region} RMS at {second}s")
        if rms < 0:
            raise ValueError(f"{field}/{pair}/{region} RMS at {second}s must be nonnegative")
        values.append(rms)
    return values


def _integral(times: tuple[int, ...], values: list[float]) -> float:
    return sum((right - left) * (a * a + b * b) / 2.0
               for left, right, a, b in zip(times, times[1:], values, values[1:]))


def _summarize(times: tuple[int, ...], values: list[float]) -> dict:
    maximum = max(values)
    peak_times = [time for time, value in zip(times, values) if value == maximum]
    first_values = values[:2]
    segment_area = _integral(times[:2], first_values)
    return {
        "saved_maximum": maximum,
        "saved_maximum_times_seconds": peak_times,
        "I_0_600": _integral(times, values) / (times[-1] - times[0]),
        "I_0_60": segment_area / (times[1] - times[0]),
        "integral_0_60": segment_area,
        "endpoint_0s": first_values[0],
        "endpoint_60s": first_values[1],
        "saved_values": values,
    }


def _verify_legacy_execution(receipt_path: Path, input_path: Path, input_hash: str) -> dict:
    receipt = json.loads(receipt_path.read_text())
    product_key = "products/fivearm_history_readback.json"
    if (receipt.get("status") != "COMPLETE" or receipt.get("task") != "fivearm"
            or receipt.get("returncode") != 0):
        raise ValueError("PR102 five-arm execution receipt is not complete")
    if receipt.get("products", {}).get(product_key) != input_hash:
        raise ValueError("PR102 execution receipt does not pin this readback")
    return {"path": str(receipt_path.resolve()), "sha256": sha256(receipt_path),
            "input_path": str(input_path.resolve()), "input_sha256": input_hash}


def _verify_new_arm_receipt(receipt_path: Path, input_path: Path, input_hash: str,
                            times: tuple[int, ...]) -> dict:
    receipt = json.loads(receipt_path.read_text())
    run_pin = receipt.get("model_run_receipt", {})
    run_path = Path(run_pin.get("path", ""))
    if (receipt.get("schema") != "pr103_closed_history_readback_receipt_v1"
            or receipt.get("status") != "CLOSED"
            or receipt.get("arm") != "A"
            or receipt.get("readback_sha256") != input_hash
            or receipt.get("times_seconds") != list(SCHEDULE)
            or list(times) != list(SCHEDULE)
            or not run_path.is_file()
            or sha256(run_path) != run_pin.get("sha256")):
        raise ValueError("new A arm requires a receipt binding the fixed schedule, readback, and model run")
    if Path(receipt.get("readback_path", "")).resolve() != input_path.resolve():
        raise ValueError("new A arm receipt path differs from readback")
    model_run = json.loads(run_path.read_text())
    expected_preflight = receipt.get("execution_preflight", {})
    run_preflight = model_run.get("pr103_execution_preflight", {})
    if (model_run.get("arm") != "AMPLITUDE" or model_run.get("status") != "COMPLETE"
            or model_run.get("returncode") != 0 or model_run.get("timestep_count") != 32
            or model_run.get("final_completed_step") != 32
            or model_run.get("maximum_seen_timestep") != 32
            or model_run.get("candidate_wrfinput_sha256") != receipt.get("candidate_wrfinput_sha256")
            or model_run.get("executed_executable_sha256") != receipt.get("executed_executable_sha256")
            or model_run.get("candidate_wrfbdy_sha256") != receipt.get("candidate_wrfbdy_sha256")
            or model_run.get("candidate_namelist_sha256") != receipt.get("candidate_namelist_sha256")
            or run_preflight.get("path") != expected_preflight.get("path")
            or run_preflight.get("sha256") != expected_preflight.get("sha256")
            or model_run.get("earliest_fatal") is not None or model_run.get("fatal_lines")
            or model_run.get("processing_errors") or model_run.get("changed_staged_inputs")
            or model_run.get("changed_original_inputs")):
        raise ValueError("new A model run receipt is not a clean, closed 640-second AMPLITUDE run")
    proposal_path = Path(receipt.get("proposal_path", ""))
    candidate_binding = model_run.get("candidate_input_binding", {})
    if (receipt.get("candidate_wrfinput_path") != str(A_CANDIDATE_PATH)
            or receipt.get("candidate_wrfinput_sha256") != A_CANDIDATE_SHA256
            or proposal_path.resolve() != A_PROPOSAL_PATH.resolve()
            or receipt.get("proposal_sha256") != A_PROPOSAL_SHA256
            or not proposal_path.is_file() or sha256(proposal_path) != A_PROPOSAL_SHA256
            or candidate_binding.get("receipt_path") != str(A_PROPOSAL_PATH)
            or candidate_binding.get("receipt_sha256") != A_PROPOSAL_SHA256
            or receipt.get("executed_executable_sha256") != A_EXECUTABLE_SHA256
            or receipt.get("candidate_wrfbdy_sha256") != A_BOUNDARY_SHA256
            or receipt.get("candidate_namelist_sha256") != A_NAMELIST_SHA256):
        raise ValueError("new A receipt model inputs differ from the frozen PR103 candidate/run")
    preflight_path = Path(expected_preflight.get("path", ""))
    if (not preflight_path.is_file() or sha256(preflight_path) != expected_preflight.get("sha256")):
        raise ValueError("new A receipt prerequisite preflight path or hash is missing")
    preflight = json.loads(preflight_path.read_text())
    if (preflight.get("schema") != "pr103_execution_preflight_v1"
            or preflight.get("status") != "READY_FOR_ROOT_REVIEW_NO_LAUNCH"
            or preflight.get("launch_authorized") is not False
            or preflight.get("duration_seconds") != 640 or preflight.get("expected_timesteps") != 32
            or preflight.get("candidate_input_receipt_path") != str(A_PROPOSAL_PATH)
            or preflight.get("candidate_input_receipt_sha256") != A_PROPOSAL_SHA256
            or preflight.get("candidate_wrfinput_sha256") != A_CANDIDATE_SHA256
            or preflight.get("candidate_executable_sha256") != A_EXECUTABLE_SHA256
            or preflight.get("candidate_wrfbdy_sha256") != A_BOUNDARY_SHA256
            or preflight.get("candidate_namelist_sha256") != A_NAMELIST_SHA256):
        raise ValueError("new A receipt prerequisite preflight differs from the frozen 640-second run")
    artifacts_by_name = {Path(row.get("path", "")).name: row.get("sha256")
                         for row in model_run.get("generated_files", [])}
    snapshots = receipt.get("history_snapshots")
    expected_snapshot_times = list(SCHEDULE)
    if not isinstance(snapshots, list) or len(snapshots) != len(expected_snapshot_times):
        raise ValueError("new A receipt must bind every fixed-schedule history snapshot")
    run_directory = run_path.parent / "run"
    checked_snapshot_hashes = {}
    for index, (expected_time, row) in enumerate(zip(expected_snapshot_times, snapshots)):
        snapshot_path = Path(row.get("path", ""))
        try:
            resolved_snapshot = snapshot_path.resolve(strict=True)
            inside_closed_run = resolved_snapshot.parent == run_directory.resolve(strict=True)
        except OSError:
            inside_closed_run = False
            resolved_snapshot = snapshot_path
        actual_sha = checked_snapshot_hashes.get(resolved_snapshot)
        if actual_sha is None and inside_closed_run:
            actual_sha = sha256(resolved_snapshot)
            checked_snapshot_hashes[resolved_snapshot] = actual_sha
        if (row.get("time_seconds") != expected_time or row.get("record_index") != index
                or not inside_closed_run or actual_sha != row.get("sha256")
                or artifacts_by_name.get(resolved_snapshot.name) != row.get("sha256")):
            raise ValueError("new A history snapshot is not bound to the closed model run receipt")
    return {"path": str(receipt_path.resolve()), "sha256": sha256(receipt_path),
            "input_path": str(input_path.resolve()), "input_sha256": input_hash,
            "arm": "A", "status": "CLOSED",
            "paired_comparisons": receipt.get("paired_comparisons", []),
            "model_run_receipt": {"path": str(run_path.resolve()), "sha256": run_pin["sha256"]}}


def build_response(readback: dict, *, input_path: Path, receipt_path: Path | None = None,
                   new_arm_receipt: Path | None = None) -> dict:
    times = readback.get("times_seconds")
    if not isinstance(times, list) or times != list(SCHEDULE) or len(set(times)) != len(times):
        raise ValueError("saved times must match the predeclared unique 0..600s, 60s schedule")
    if (readback.get("status") != "DESCRIPTIVE_ONLY"
            or readback.get("physical_approval") != "FAIL_OPEN"
            or readback.get("observation_skill") != "NOT_EVALUATED"):
        raise ValueError("readback approval and observation-skill states differ from the descriptive-only contract")
    if set(readback.get("fields", {})) != set(FIELDS):
        raise ValueError("readback field set differs from the fixed field contract")
    for field, unit in FIELDS.items():
        metadata = readback["fields"][field]
        if metadata.get("unit") != unit or metadata.get("source_field") != SOURCE_FIELDS[field]:
            raise ValueError(f"{field} source/unit differs from the fixed contract")
    if set(readback.get("metrics", {})) != {str(second) for second in SCHEDULE}:
        raise ValueError("metrics must contain each predeclared time exactly once and no extras")
    if readback.get("fixed_support", {}).get("support_cells") != REGIONS["support"] or \
            readback.get("fixed_support", {}).get("support_columns") != 16 or \
            readback.get("fixed_support", {}).get("buffer_columns") != 196 or \
            readback.get("fixed_support", {}).get("buffer_levels") != 39:
        raise ValueError("fixed support/buffer metadata differs from the frozen contract")
    input_hash = sha256(input_path)
    if new_arm_receipt:
        source_identity = _verify_new_arm_receipt(new_arm_receipt, input_path, input_hash, tuple(times))
        arms = {**ARMS, "A": "A"}
        pairs = source_identity["paired_comparisons"]
        allowed_pairs = {"A_minus_P", "A_minus_N", "A_minus_H"}
        if not isinstance(pairs, list) or len(set(pairs)) != len(pairs) or not set(pairs) <= allowed_pairs:
            raise ValueError("A receipt has invalid paired comparison labels")
    else:
        if receipt_path is None:
            raise ValueError("the PR102 five-arm execution receipt is required")
        source_identity = _verify_legacy_execution(receipt_path, input_path, input_hash)
        arms = ARMS
        pairs = []

    result = {}
    for field in FIELDS:
        result[field] = {arm: {region: _summarize(SCHEDULE, _read_series(readback, raw_arm, field, region))
                               for region in REGIONS}
                         for arm, raw_arm in arms.items()}
        for region, count in REGIONS.items():
            result[field]["OFF"] = result[field].get("OFF", {})
            result[field]["OFF"][region] = _summarize(SCHEDULE, [0.0] * len(SCHEDULE))
    paired_results = {pair: {field: {region: _summarize(SCHEDULE,
                       _read_pair_series(readback, pair, field, region)) for region in REGIONS}
                       for field in FIELDS} for pair in pairs}
    return {
        "schema": "pr103_saved_time_response_v1",
        "status": "DESCRIPTIVE_ONLY",
        "times_seconds": list(SCHEDULE),
        "fields": FIELDS,
        "I_units": {field: f"({unit})^2" for field, unit in FIELDS.items()},
        "arms": {**{alias: label for alias, label in ARMS.items()}, **({"A": "A"} if "A" in arms else {}), "OFF": "OFF"},
        "regions": REGIONS,
        "physical_approval": "FAIL_OPEN",
        "observation_skill": "NOT_EVALUATED",
        "metrics": result,
        "explicit_paired_metrics": paired_results,
        "source_receipt": source_identity,
        "limits": [
            "E_X(t) is fixed-mask native-field RMS of arm X minus OFF; OFF is zero by definition.",
            "I_X is 1/T times the trapezoidal integral of E_X squared over saved time, in original field units squared; it is not energy.",
            "The raw 0..60s trapezoid area is reported separately in original field units squared times seconds.",
            "The 0..60s segment contains only two saved snapshots and makes no high-frequency claim.",
            "Masks, fields, units, arms, and saved schedule are fixed before response calculation; no favorable time or mask selection is used.",
            "These are descriptive comparisons, not observation or reference-truth skill scores. Physical approval remains FAIL_OPEN; observation skill remains NOT_EVALUATED.",
            "Any A_minus_P/N/H series is integrated only when the closed A receipt explicitly lists that pair and the reader readback provides its paired native RMS at every frozen time.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="closed-reader history readback JSON")
    parser.add_argument("--receipt", type=Path, help="PR102 five-arm execution receipt")
    parser.add_argument("--new-arm-receipt", type=Path,
                        help="explicit closed A-arm receipt; required to include a later A arm")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    readback = json.loads(args.input.read_text())
    result = build_response(readback, input_path=args.input, receipt_path=args.receipt,
                            new_arm_receipt=args.new_arm_receipt)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        with args.output.open("x") as stream:
            created = True
            json.dump(result, stream, indent=2, sort_keys=True)
            stream.write("\n")
    except Exception:
        if created:
            args.output.unlink(missing_ok=True)
        raise
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
