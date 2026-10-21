#!/usr/bin/env python3
"""Audit receipt-closed 640-second C1 runs against the matching C1 baseline."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import netCDF4  # noqa: F401 - required by the frozen C1 comparison reader

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import pr94_longrun_audit as c1_compare  # noqa: E402

RUNNER_PATH = Path("/var/tmp/pr96_runner_frozen_20261021/tools/pr86_time_response.py")
RUNNER_SHA256 = "80803b6b3e8591053d0524ed9e5b0110dfd7cbf1d105d2e40029addb5f5a55c4"
BASELINE_RUNS = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr96_local_closure_20261021/runs_on_lustre")
BASELINE_AUDITS = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr96_local_closure_20261021/closed_audits/pr96_c1_20261021")
RESULTS_PATH = ROOT / "docs/evidence/pr97_c1_results_20261022/closed_results.json"
RESULTS_SHA256 = "bb69a2ec7ce83902c589ce6b3fa0464c3ade0e3e94d13c7a9ba45b5c32b6ba7f"
OVERVIEW_PATH = BASELINE_AUDITS / "overview.json"
OVERVIEW_SHA256 = "201ab705b5f96a59f1e7c8f26e17cb42147eadfd9cbaff621cded60c92097a51"
READER_PINS = {
    "tools/pr94_longrun_audit.py": "0ce4eb5a00fa5065aef71be5436b1894813e6d3bdca9d5904283ef72dca326d1",
    "tools/pr86_compare_response.py": "64b2f97f452035cae328576d26216c54877fa778b3eeabe17cdb9980103aaa5c",
    "tools/pr87_native_history.py": "d6feb0e5fd5d53a60d7256a7b3c4faaa3c7f2488b799af25278aec7529c28a71",
    "tools/pr86_water_budget.py": "e6c00374e9730278b3c1545630af9aa3a6af4c68544c7f39dbda61f909337dc2",
    "tools/pr87_completed_state_audit.py": "2daef11c005868abf58631d84df74b8535eccb217660fbd605bd8f03216ee70d",
    "tools/pr85_joint_stage_trace.py": "5c2e9ccb3537a6bc251845e2b87c3efb991002ebbc1db5232d475e29f6c31720",
    "docs/evidence/pr93_active_ice_20261020/runtime/closed_run_audit.py": "8f9affa02e6d843d623911cfd6a9447a9ddb4ba0713cf927e2d5de2bcfb2e126",
}
EXPECTED_EXE = "a714f00d3f81c0b47d94aef815f1f765ae48842e9de629cb869323ccfc22a96d"
DURATION_SECONDS = 640
REVIEW_SNAPSHOT_SECONDS = (20, 60, 300, 600, 640)


def closed_run_complete(receipt: dict, completed_steps: list[int]) -> bool:
    return (
        receipt.get("status") == "COMPLETE"
        and receipt.get("returncode") == 0
        and not receipt.get("fatal_lines")
        and not receipt.get("processing_errors")
        and completed_steps == list(range(1, DURATION_SECONDS // 20 + 1))
        and receipt.get("final_completed_step") == DURATION_SECONDS // 20
    )


def verify_compressed_output(path: Path, row: dict, arm: str) -> None:
    require(path.is_file(), f"{arm} receipt-bound compressed stage trace is missing")
    require(path.stat().st_size == row["compressed_bytes"],
            f"{arm} compressed trace byte count differs from closed receipt")
    require(sha256(path) == row["compressed_sha256"],
            f"{arm} compressed trace hash differs from closed receipt")


def missing_snapshot_labels(snapshots: dict, schedule: dict[int, str]) -> list[str]:
    return sorted(set(schedule.values()) - set(snapshots.get("snapshots", {})))


def scoped_audit_status(procedural: str, exact_source: str, active_ice: str) -> str:
    return ("PASS_SCOPED" if procedural == "PASS" and exact_source == "PASS" and active_ice == "PASS"
            else "INCOMPLETE_OR_FAIL")


def verify_source_receipt_binding(run_root: Path, run_receipt: dict, baseline_receipt: dict,
                                  run_preflight: dict, baseline_preflight: dict) -> None:
    expected = baseline_preflight.get("source_receipt_sha256")
    require(run_preflight.get("source_receipt_sha256") == run_receipt.get("source_receipt_sha256") ==
            baseline_receipt.get("source_receipt_sha256") == expected,
            "source receipt identity differs from frozen C1")
    source_path = Path(run_preflight.get("source_receipt", ""))
    if not source_path.is_absolute():
        source_path = run_root / source_path
    require(source_path.is_file(), "source receipt file named by preflight is missing")
    require(sha256(source_path) == expected, "source receipt file changed after C1 preflight")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def load_closed_auditor():
    path = ROOT / "docs/evidence/pr93_active_ice_20261020/runtime/closed_run_audit.py"
    expected = READER_PINS["docs/evidence/pr93_active_ice_20261020/runtime/closed_run_audit.py"]
    require(sha256(path) == expected, "frozen PR93 C1 source-policy reader hash changed")
    spec = importlib.util.spec_from_file_location("pr98_c1_closed_run_audit", path)
    require(spec is not None and spec.loader is not None, "cannot load frozen C1 source-policy reader")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_frozen_runner():
    """Load snapshot readers from the exact runner used for the 640-second runs."""
    require(sha256(RUNNER_PATH) == RUNNER_SHA256, "frozen C1 runner hash changed")
    spec = importlib.util.spec_from_file_location("pr96_frozen_time_response", RUNNER_PATH)
    require(spec is not None and spec.loader is not None, "cannot load frozen C1 runner")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def verify_reader_pins() -> dict[str, str]:
    require(sha256(RUNNER_PATH) == RUNNER_SHA256, "frozen C1 runner hash changed")
    require(sha256(RESULTS_PATH) == RESULTS_SHA256, "PR97 C1 recipe hash changed")
    require(sha256(OVERVIEW_PATH) == OVERVIEW_SHA256, "PR97 C1 reader recipe hash changed")
    overview = json.loads(OVERVIEW_PATH.read_text(encoding="utf-8"))
    require(overview.get("reader_dependency_pins") == READER_PINS,
            "PR97 C1 reader pins differ from the frozen expected recipe")
    observed = {name: sha256(ROOT / name) for name in READER_PINS}
    require(observed == READER_PINS, "a PR97 C1 source-policy reader changed")
    return observed


def c1_baseline_identity(arm: str) -> tuple[dict, Path, dict, dict]:
    """Load the receipt-closed matching 600-second C1 reference and its PR97 result."""
    require(arm in ("OFF", "HYDRO", "COUPLED"), f"invalid arm: {arm}")
    require(sha256(RESULTS_PATH) == RESULTS_SHA256, "PR97 C1 recipe changed")
    results = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    baseline_root = BASELINE_RUNS / f"{arm}_600s_c1"
    receipt, receipt_path = load_closed_auditor().closed_receipt(baseline_root, arm)
    summary = results["arms"][arm]
    require(sha256(receipt_path) == summary["receipt_sha256"], f"{arm} baseline receipt is not PR97-pinned")
    require(receipt.get("status") == "COMPLETE" and receipt.get("returncode") == 0,
            f"{arm} PR97 C1 baseline is not complete")
    audit_path = BASELINE_AUDITS / f"{arm}_600s_c1_audit.json"
    preflight_path = baseline_root / "preflight.json"
    require(sha256(preflight_path) == summary["preflight_sha256"],
            f"{arm} baseline preflight is not PR97-pinned")
    require(sha256(audit_path) == summary["audit_sha256"], f"{arm} PR97 C1 policy audit is not pinned")
    baseline_audit = json.loads(audit_path.read_text(encoding="utf-8"))
    require(baseline_audit["qnb_pair_conversion_audit"]["status"] == "FAIL" and
            baseline_audit["exact_source_endpoint_audit"]["status"] == "PASS" and
            baseline_audit["active_ice_policy_split"]["status"] == "PASS",
            f"{arm} PR97 C1 policy statuses differ from the frozen recipe")
    summary["baseline_policy_statuses"] = {
        "generic_qnb": baseline_audit["qnb_pair_conversion_audit"]["status"],
        "exact_source_endpoint": baseline_audit["exact_source_endpoint_audit"]["status"],
        "active_ice_policy": baseline_audit["active_ice_policy_split"]["status"],
    }
    summary["preflight_sha256_verified"] = sha256(preflight_path)
    return receipt, receipt_path, baseline_root, summary


def validate_c1_runtime_binding(run_root: Path, arm: str,
                                run_receipt: dict, baseline_receipt: dict,
                                run_preflight: dict, baseline_preflight: dict) -> dict:
    """Reject a different executable, build, arm input, or C1 source recipe."""
    require(run_receipt.get("arm", "").upper() == arm, "closed receipt arm mismatch")
    require(run_receipt.get("duration_seconds") == DURATION_SECONDS,
            "closed receipt does not bind the requested 640-second duration")
    require(run_receipt.get("executed_executable_sha256") == EXPECTED_EXE and
            run_receipt.get("expected_executed_executable_sha256") == EXPECTED_EXE,
            "640-second run executable differs from the frozen C1 executable")
    require(run_receipt.get("candidate_build") == baseline_receipt.get("candidate_build"),
            "640-second candidate build differs from the matching C1 build receipt")
    for name in ("candidate_wrfinput_sha256", "candidate_wrfbdy_sha256"):
        require(run_receipt.get(name) == baseline_receipt.get(name),
                f"640-second run {name} differs from matching C1 arm")
    require(run_preflight.get("arm") == arm and run_preflight.get("duration_seconds") == DURATION_SECONDS,
            "640-second preflight arm or duration mismatch")
    require(run_preflight.get("candidate_build") == baseline_preflight.get("candidate_build"),
            "640-second preflight candidate build differs from C1")
    require(run_preflight.get("input_hashes") == baseline_preflight.get("input_hashes"),
            "640-second source input hashes differ from C1")
    require(run_preflight.get("source_namelist_sha256") == baseline_preflight.get("source_namelist_sha256"),
            "640-second source namelist differs from C1")
    verify_source_receipt_binding(run_root, run_receipt, baseline_receipt,
                                  run_preflight, baseline_preflight)
    require(run_preflight.get("candidate_wrfinput_sha256") == baseline_preflight.get("candidate_wrfinput_sha256") ==
            run_receipt.get("candidate_wrfinput_sha256"), "candidate input hash differs from C1")
    require(run_preflight.get("candidate_wrfbdy_sha256") == baseline_preflight.get("candidate_wrfbdy_sha256") ==
            run_receipt.get("candidate_wrfbdy_sha256"), "candidate boundary hash differs from C1")
    require(run_receipt.get("changed_original_inputs") == [] and
            run_receipt.get("changed_staged_inputs") == [] and
            run_receipt.get("candidate_build_unchanged") is True and
            run_receipt.get("candidate_input_unchanged") is True,
            "closed runner receipt reports changed C1 inputs or build")
    if arm == "HYDRO":
        require(run_preflight.get("candidate_input_binding") == baseline_preflight.get("candidate_input_binding"),
                "HYDRO source input chain differs from frozen C1")
    return {
        "status": "PASS",
        "arm": arm,
        "duration_seconds": DURATION_SECONDS,
        "executable_sha256": EXPECTED_EXE,
        "candidate_build_receipt": run_receipt["candidate_build"],
        "candidate_wrfinput_sha256": run_receipt["candidate_wrfinput_sha256"],
        "candidate_wrfbdy_sha256": run_receipt["candidate_wrfbdy_sha256"],
        "source_input_hashes_equal_to_c1": True,
        "source_namelist_sha256": run_preflight["source_namelist_sha256"],
        "hydro_source_receipt_sha256": run_preflight.get("source_receipt_sha256") if arm == "HYDRO" else None,
        "run_root": str(run_root),
    }


def verify_receipt_history(root: Path, receipt: dict) -> dict[str, str]:
    """Hash-check all receipt-listed WRF history files before history comparison."""
    files: dict[str, str] = {}
    for key in ("generated_files", "compressed_outputs", "history_files", "history_outputs"):
        for entry in receipt.get(key, []):
            name = entry.get("path", entry.get("compressed_path", ""))
            if not Path(name).name.startswith("wrfout_d01_"):
                continue
            digest = entry.get("sha256", entry.get("compressed_sha256", ""))
            require(name not in files or files[name] == digest,
                    f"closed receipt contains conflicting history hashes: {name}")
            files[name] = digest
    require(files, "closed receipt lists no WRF history files")
    for name, expected in files.items():
        path = root / "run" / name
        require(path.is_file() and sha256(path) == expected,
                f"receipt-bound history changed or is missing: {name}")
    return files


def audit_run(run_root: Path, arm: str) -> dict:
    """Audit one finalized 640-second run; never call the PR94 C4 runtime gate."""
    reader_pins = verify_reader_pins()
    c1_receipt, c1_receipt_path, c1_root, c1_result = c1_baseline_identity(arm)
    auditor = load_closed_auditor()
    receipt, receipt_path = auditor.closed_receipt(run_root, arm)
    require(receipt.get("status") in ("COMPLETE", "INCOMPLETE"), "run receipt is not finalized")
    preflight = json.loads((run_root / "preflight.json").read_text(encoding="utf-8"))
    c1_preflight = json.loads((c1_root / "preflight.json").read_text(encoding="utf-8"))
    runtime = validate_c1_runtime_binding(run_root, arm, receipt, c1_receipt, preflight, c1_preflight)
    completed = auditor.derive_prefix(receipt, arm)
    duration_complete = closed_run_complete(receipt, completed)

    trace_row = auditor.output_row(receipt, auditor.TRACE_NAME, arm)
    trace_path = run_root / "run" / trace_row["compressed_path"]
    verify_compressed_output(trace_path, trace_row, arm)
    baseline_trace_row = auditor.output_row(c1_receipt, auditor.TRACE_NAME, f"baseline {arm}")
    baseline_trace_path = c1_root / "run" / baseline_trace_row["compressed_path"]
    verify_compressed_output(baseline_trace_path, baseline_trace_row, f"baseline {arm}")
    runner = load_frozen_runner()
    schedule = runner.snapshot_schedule(DURATION_SECONDS)
    snapshots = runner.read_time_snapshots(trace_path, DURATION_SECONDS)
    schedule_by_label = {label: step * 20 for step, label in schedule.items()}
    snapshot_seconds = tuple(sorted(schedule_by_label.values()))
    present_labels = set(snapshots.get("snapshots", {}))
    missing_runner_snapshots = missing_snapshot_labels(snapshots, schedule)
    schedule_complete = not missing_runner_snapshots
    review_labels = {label for label, seconds in schedule_by_label.items()
                     if seconds in REVIEW_SNAPSHOT_SECONDS}
    review_schedule_complete = review_labels.issubset(present_labels)
    trace_620 = 31 in snapshots.get("completed_post_kdm6_timesteps", [])

    # Use only the receipt-free comparison functions from the pinned PR94 module.
    # The PR94/C4 `_verify_runtime_bindings` and `audit_compact_run` are never called.
    prefix = c1_compare.compare_first_600_seconds(c1_root, c1_receipt, run_root, receipt, arm)
    history_files = verify_receipt_history(run_root, receipt)
    history = c1_compare.compare_closed_histories(c1_root, c1_receipt, run_root, receipt, arm)

    source_policy = (auditor.audit_arm(run_root, arm) if completed else {
        "qnb_pair_conversion_audit": {"status": "NOT_EVALUATED", "reason": "no completed POST_KDM6 states"},
        "exact_source_endpoint_audit": {"status": "NOT_EVALUATED", "reason": "no completed endpoints"},
        "active_ice_policy_split": {"status": "NOT_EVALUATED", "reason": "no completed states"},
    })
    trace_prefix_status = prefix.get("status")
    history_status = history.get("status")
    procedural_status = "PASS" if (duration_complete and schedule_complete and review_schedule_complete and trace_620 and
                                     trace_prefix_status == "PASS" and history_status == "PASS") else "INCOMPLETE_OR_FAIL"
    exact_status = source_policy["exact_source_endpoint_audit"]["status"]
    ice_status = source_policy["active_ice_policy_split"]["status"]
    scoped_status = scoped_audit_status(procedural_status, exact_status, ice_status)
    return {
        "schema": "pr98_c1_640_closed_audit_v1",
        "arm": arm,
        "status": scoped_status,
        "procedural_audit_status": procedural_status,
        "review_required": True,
        "physical_approval": "FAIL_OPEN",
        "runtime": {
            "run_receipt_path": str(receipt_path), "run_receipt_sha256": sha256(receipt_path),
            "run_receipt_status": receipt["status"], "returncode": receipt.get("returncode"),
            "final_completed_step": receipt.get("final_completed_step"),
            "fatal_lines": receipt.get("fatal_lines", []),
            "processing_errors": receipt.get("processing_errors", []),
            "duration_complete": duration_complete,
            "baseline_receipt_path": str(c1_receipt_path), "baseline_receipt_sha256": sha256(c1_receipt_path),
            "baseline_receipt_status": c1_receipt["status"],
            "runtime_binding": runtime,
        },
        "trace_schedule": {
            "runner_snapshot_schedule_seconds": list(snapshot_seconds),
            "requested_review_checkpoints_seconds": list(REVIEW_SNAPSHOT_SECONDS),
            "present_snapshot_labels": sorted(present_labels),
            "required_review_snapshots_present": review_schedule_complete,
            "all_runner_snapshots_present": schedule_complete,
            "missing_runner_snapshot_labels": missing_runner_snapshots,
            "requested_review_snapshots_present": review_schedule_complete,
            "620_second_completed_post_kdm6_record_present": trace_620,
            "compressed_sha256": trace_row["compressed_sha256"],
            "expanded_sha256": trace_row["sha256"],
            "full_trace_timesteps": snapshots.get("timesteps", []),
            "full_trace_completed_post_kdm6_timesteps": snapshots.get("completed_post_kdm6_timesteps", []),
        },
        "pr97_source_policy_audit": {
            "reader_pins": reader_pins,
            "baseline_audit_sha256": c1_result["audit_sha256"],
            "baseline_policy_statuses": c1_result["baseline_policy_statuses"],
            "generic_qnb": source_policy["qnb_pair_conversion_audit"],
            "exact_source_endpoint": source_policy["exact_source_endpoint_audit"],
            "active_ice_policy": source_policy["active_ice_policy_split"],
        },
        "first_600_seconds_trace_prefix": prefix,
        "first_600_seconds_ten_field_history": history,
        "receipt_bound_history_files": history_files,
        "limits": [
            "Generic Q/N/B, exact source endpoint, and active-ice policy findings remain separate.",
            "Trace and history comparison covers only the matching PR96-C1 arm through 600 seconds.",
            "A receipt-closed run and policy audit do not establish scientific approval.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--arm", choices=("OFF", "HYDRO", "COUPLED"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"refusing to overwrite audit output: {args.output}")
    result = audit_run(args.run_root, args.arm)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"arm": args.arm, "status": result["status"],
                      "generic_qnb": result["pr97_source_policy_audit"]["generic_qnb"]["status"],
                      "exact_source_endpoint": result["pr97_source_policy_audit"]["exact_source_endpoint"]["status"],
                      "active_ice_policy": result["pr97_source_policy_audit"]["active_ice_policy"]["status"],
                      "trace_prefix": result["first_600_seconds_trace_prefix"]["status"],
                      "history": result["first_600_seconds_ten_field_history"]["status"]}))
    return 0 if result["status"] == "PASS_SCOPED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
