#!/usr/bin/env python3
"""Closed-only receipt audit for the PR99-C2 640-second native candidate."""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr99_native_contract_20261022/Cloud-BAL")
RUNS = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/pr99_c2_matched640_20261022")
BUILD = Path("/var/tmp/pr99_bulk_candidate_native_c2_20261022/pr87_native_overlay_build.json")
BUILD_SHA = "9c4802e12ea1d6a8f3c8b5ef1a5ff72116e5fbdbf9f6c78e906935622d45dafb"
EXE_SHA = "387f46df03e87b8693a57fdefc4ddb62a848e7a946ce417ee8b3d54d2c62cc9a"
PREFLIGHT = Path("/var/tmp/pr99_c2_inputs_preflight_20261022/preflight.json")
PREFLIGHT_SHA = "e5ebd3fe173ec8deee525d2553a347f88ff86a68041f6fc2fac8fbd7df4554a1"
ROOT_GO = Path("/var/tmp/pr99_c2_root_launch_go_20261022.json")
ROOT_GO_SHA = "5420c264a6dabf1361e6ff4b0e448efdeee9b0f51811fcef79cb894005760363"
RUNNER_SHA = "80803b6b3e8591053d0524ed9e5b0110dfd7cbf1d105d2e40029addb5f5a55c4"
ARMS = ("OFF", "HYDRO", "COUPLED")
T1_PAYLOADS = ("kdm6_first_call_pre.raw", "kdm6_first_call_post.raw",
               "pr67_kdm6_process.raw")

sys.path.insert(0, str(ROOT / "tools"))
import pr98_boundary_audit as c1  # noqa: E402
import pr94_longrun_audit as compare  # noqa: E402


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def check_global_pins() -> tuple[dict, dict, dict]:
    require(sha256(BUILD) == BUILD_SHA, "reviewed C2 build receipt hash changed")
    build = read_json(BUILD)
    require(build.get("schema") == "pr87_native_overlay_build_v1" and
            build.get("status") == "PASS_OVERLAY_BUILD" and
            build.get("full_clean_build") is False and build.get("model_run") is False,
            "C2 build receipt identity/status changed")
    exe = Path(build["executable_path"])
    require(build.get("executable_sha256") == EXE_SHA and exe.is_file() and
            sha256(exe) == EXE_SHA, "reviewed C2 executable hash mismatch")
    require(sha256(PREFLIGHT) == PREFLIGHT_SHA,
            "reviewed read-only C2 input preflight hash changed")
    pre = read_json(PREFLIGHT)
    require(pre.get("schema") == "pr99_c2_inputs_readonly_preflight_v1" and
            pre.get("status") == "PASS_PREFLIGHT_ONLY_NO_MODEL_LAUNCHED" and
            pre.get("build_receipt_sha256") == BUILD_SHA and
            pre.get("build_executable_sha256") == EXE_SHA and
            pre.get("runner_sha256") == RUNNER_SHA and
            pre.get("duration_seconds") == 640 and pre.get("timestep_seconds") == 20 and
            pre.get("same_candidate_build_path_for_all_arms") is True,
            "reviewed C2 input preflight does not bind this candidate and schedule")
    require(sha256(ROOT_GO) == ROOT_GO_SHA, "root C2 launch-GO artifact hash changed")
    go = read_json(ROOT_GO)
    require(go.get("schema") == "pr99_c2_root_launch_go_v1" and
            go.get("status") == "GO_MATCHED_THREE_ARM_640_ONLY" and
            go.get("candidate") == "PR99-C2" and
            go.get("build_receipt_sha256") == BUILD_SHA and
            go.get("executable_sha256") == EXE_SHA and
            go.get("preflight_sha256") == PREFLIGHT_SHA and
            go.get("run_roots") == {arm: str(RUNS / arm) for arm in ARMS} and
            go.get("physical_approval") == "FAIL_OPEN" and
            go.get("observations") == "NOT_EVALUATED",
            "root C2 launch-GO artifact does not authorize these exact run roots/build")
    return build, pre, go


def validate_arm_identity(arm: str, run_root: Path, receipt: dict, receipt_path: Path,
                          preflight: dict, baseline: dict, baseline_receipt: dict,
                          baseline_receipt_path: Path, baseline_root: Path, reviewed_preflight: dict,
                          build: dict, auditor, runner) -> dict:
    require(preflight.get("arm") == arm and preflight.get("duration_seconds") == 640 and
            preflight.get("timestep_seconds") == 20 and preflight.get("expected_timesteps") == 32,
            f"{arm}: run preflight arm or 640-second schedule mismatch")
    require(receipt.get("arm", "").upper() == arm, f"{arm}: receipt arm mismatch")
    expected_build = preflight.get("candidate_build")
    require(isinstance(expected_build, dict) and expected_build.get("receipt_path") == str(BUILD) and
            expected_build.get("receipt_sha256") == BUILD_SHA and
            expected_build.get("executable_sha256") == EXE_SHA and
            receipt.get("candidate_build") == expected_build,
            f"{arm}: run preflight/receipt do not bind reviewed C2 build")
    require(receipt.get("executed_executable_sha256") == EXE_SHA and
            receipt.get("expected_executed_executable_sha256") == EXE_SHA,
            f"{arm}: executed executable differs from reviewed C2 executable")
    require(receipt.get("launch_runner_source_sha256") == RUNNER_SHA and
            receipt.get("launch_runner_source_sha256_status") ==
            "captured at run entry before model execution",
            f"{arm}: closed receipt does not bind the frozen launch runner source")
    staged_exe = run_root / "run" / "wrf.exe"
    require(staged_exe.is_file() and sha256(staged_exe) == EXE_SHA,
            f"{arm}: staged run executable differs from reviewed C2 executable")

    require(preflight.get("input_hashes") == baseline.get("input_hashes") and
            preflight.get("source_namelist_sha256") == baseline.get("source_namelist_sha256"),
            f"{arm}: original runtime input or source namelist differs from C1")
    for name, staged_name in (("candidate_wrfinput_sha256", "wrfinput_d01"),
                              ("candidate_wrfbdy_sha256", "wrfbdy_d01")):
        staged_path = run_root / "run" / staged_name
        require(preflight.get(name) == baseline.get(name) == receipt.get(name) and
                staged_path.is_file() and sha256(staged_path) == receipt.get(name),
                f"{arm}: {staged_name} differs from receipt/C1 input hash")
    source_namelist = Path(preflight["runtime_dir"]) / "namelist.input"
    staged_namelist = run_root / "run" / "namelist.input"
    require(source_namelist.is_file() and
            sha256(source_namelist) == preflight.get("source_namelist_sha256") ==
            baseline.get("source_namelist_sha256"),
            f"{arm}: original source namelist differs from C1")
    expected_namelist = hashlib.sha256(
        runner.edit_namelist(source_namelist.read_text(encoding="utf-8"), 640).encode()
    ).hexdigest()
    require(preflight.get("candidate_namelist_sha256") == receipt.get("candidate_namelist_sha256") ==
            expected_namelist and staged_namelist.is_file() and
            sha256(staged_namelist) == expected_namelist,
            f"{arm}: staged 640-second namelist differs from the frozen runner transformation")
    require(receipt.get("candidate_build_unchanged") is True and
            receipt.get("candidate_input_unchanged") is True and
            receipt.get("changed_original_inputs") == [] and
            receipt.get("changed_staged_inputs") == [],
            f"{arm}: receipt reports changed build or inputs")

    reviewed_arm = reviewed_preflight["arms"][arm]
    require(reviewed_arm.get("receipt_sha256") == sha256(baseline_receipt_path) and
            reviewed_arm.get("candidate_wrfinput_sha256") == baseline.get("candidate_wrfinput_sha256") and
            reviewed_arm.get("candidate_wrfbdy_sha256") == baseline.get("candidate_wrfbdy_sha256") and
            reviewed_arm.get("source_receipt_sha256") == baseline.get("source_receipt_sha256") and
            reviewed_arm.get("status") == "COMPLETE" and reviewed_arm.get("returncode") == 0 and
            reviewed_arm.get("expected_input_match") is True and
            reviewed_arm.get("boundary_match") is True and
            reviewed_arm.get("candidate_input_unchanged") is True and
            reviewed_arm.get("candidate_build_unchanged") is True,
            f"{arm}: reviewed prelaunch input preflight no longer matches its C1 baseline")
    require(receipt.get("source_receipt_sha256") == preflight.get("source_receipt_sha256") ==
            baseline_receipt.get("source_receipt_sha256"), f"{arm}: source receipt differs from C1")
    c1.verify_source_receipt_binding(run_root, receipt, baseline_receipt, preflight, baseline)
    if arm == "HYDRO":
        hydro = c1.verify_hydro_input_binding(run_root, receipt, baseline_receipt,
                                               preflight, baseline)
    else:
        hydro = None

    baseline_times = baseline_receipt.get("expected_model_timestamps", [])
    require(baseline_times, f"{arm}: matching C1 receipt has no timestamps")
    start = dt.datetime.strptime(baseline_times[0], "%Y-%m-%d_%H:%M:%S") - dt.timedelta(seconds=20)
    expected_times = [(start + dt.timedelta(seconds=20 * step)).strftime("%Y-%m-%d_%H:%M:%S")
                      for step in range(1, 33)]
    require(receipt.get("expected_model_timestamps") == expected_times,
            f"{arm}: receipt timestamps do not bind the matching C1 start and 640 seconds")
    return {"status": "PASS", "run_receipt": str(receipt_path),
            "run_receipt_sha256": sha256(receipt_path), "run_preflight_sha256": sha256(run_root / "preflight.json"),
            "build_receipt_sha256": BUILD_SHA, "executable_sha256": EXE_SHA,
            "candidate_wrfinput_sha256": receipt.get("candidate_wrfinput_sha256"),
            "candidate_wrfbdy_sha256": receipt.get("candidate_wrfbdy_sha256"),
            "source_namelist_sha256": preflight.get("source_namelist_sha256"),
            "inputs_match_c1": True, "hydro_input_binding": hydro}


def procedural_status(receipt: dict, completed: list[int], trace: dict,
                      schedule: dict[int, str]) -> dict:
    missing = sorted(set(schedule.values()) - set(trace.get("snapshots", {})))
    complete = (receipt.get("status") == "COMPLETE" and receipt.get("returncode") == 0 and
                not receipt.get("fatal_lines") and not receipt.get("processing_errors") and
                completed == list(range(1, 33)) and receipt.get("final_completed_step") == 32 and
                not receipt.get("snapshots", {}).get("duplicate_post_kdm6_timesteps") and
                not missing and 31 in trace.get("completed_post_kdm6_timesteps", []))
    return {"status": "PASS" if complete else "INCOMPLETE_OR_FAIL",
            "receipt_status": receipt.get("status"), "returncode": receipt.get("returncode"),
            "completed_steps": len(completed), "final_completed_step": receipt.get("final_completed_step"),
            "missing_runner_snapshots": missing, "620_second_post_kdm6_present":
                31 in trace.get("completed_post_kdm6_timesteps", []),
            "required_review_seconds": [20, 60, 300, 600, 640]}


def equivalence_status(result: dict) -> dict:
    original_status = result.get("status")
    if original_status == "FAIL" and result.get("differences"):
        label = "FAIL_DIFFERENT"
    elif original_status in ("PASS", "INCOMPLETE"):
        label = original_status
    else:
        label = "FAIL"
    differences = result.get("differences", [])
    return {**result, "comparator_status": original_status, "status": label,
            "first_difference": differences[0] if differences else None}


def expanded_payload_identity(run_root: Path, receipt: dict, arm: str, raw_name: str,
                              auditor) -> dict:
    compressed_name = f"{raw_name}.gz"
    matches = [row for row in receipt.get("compressed_outputs", [])
               if row.get("compressed_path") == compressed_name]
    if not matches:
        return {"status": "MISSING", "reason": "receipt row absent", "raw_name": raw_name}
    row = auditor.output_row(receipt, compressed_name, arm)
    require(row.get("path") == raw_name,
            f"{arm}: compressed receipt row points to unexpected raw payload for {raw_name}")
    path = run_root / "run" / compressed_name
    if not path.is_file():
        return {"status": "MISSING", "reason": "compressed payload file absent",
                "raw_name": raw_name, "receipt_row": row}
    c1.verify_compressed_output(path, row, arm)

    expanded = hashlib.sha256()
    expanded_bytes = 0
    with gzip.open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            expanded.update(block)
            expanded_bytes += len(block)
    expanded_sha = expanded.hexdigest()
    require(expanded_bytes == row["bytes"] and expanded_sha == row["sha256"],
            f"{arm}: expanded payload identity differs from receipt for {raw_name}")
    return {"status": "VERIFIED", "raw_name": raw_name,
            "expanded_bytes": expanded_bytes, "expanded_sha256": expanded_sha,
            "compressed_bytes": row["compressed_bytes"],
            "compressed_sha256": row["compressed_sha256"]}


def compare_t1_payloads(c2_root: Path, c2_receipt: dict, c2_receipt_path: Path,
                        c1_root: Path, c1_receipt: dict, c1_receipt_path: Path,
                        arm: str, auditor) -> dict:
    """Compare first-call payload identity separately from 640-second completion."""
    payloads = {}
    for raw_name in T1_PAYLOADS:
        current = expanded_payload_identity(c2_root, c2_receipt, arm, raw_name, auditor)
        baseline = expanded_payload_identity(c1_root, c1_receipt,
                                             f"matching C1 {arm}", raw_name, auditor)
        if current["status"] == "MISSING" or baseline["status"] == "MISSING":
            status = "MISSING"
        else:
            status = ("PASS_IDENTICAL" if
                      current["expanded_bytes"] == baseline["expanded_bytes"] and
                      current["expanded_sha256"] == baseline["expanded_sha256"]
                      else "FAIL_DIFFERENT")
        payloads[raw_name] = {"status": status, "c2": current, "matching_c1": baseline}
    return {"scope": "C2 versus matching frozen C1 first-call T1 payload identity",
            "candidate_identities": {
                "c2": {"candidate": "PR99-C2", "arm": arm,
                       "receipt_path": str(c2_receipt_path),
                       "receipt_sha256": sha256(c2_receipt_path)},
                "matching_c1": {"candidate": "frozen C1 baseline", "arm": arm,
                                "receipt_path": str(c1_receipt_path),
                                "receipt_sha256": sha256(c1_receipt_path)}},
            "payloads": payloads,
            "does_not_gate_procedural_completion": True,
            "does_not_promote_water_closure": True}


def audit_arm(arm: str, run_root: Path, build: dict, reviewed_preflight: dict,
              auditor, runner) -> dict:
    receipt, receipt_path = auditor.closed_receipt(run_root, arm)
    preflight_path = run_root / "preflight.json"
    require(preflight_path.is_file(), f"{arm}: per-arm run preflight missing")
    preflight = read_json(preflight_path)
    baseline_receipt, baseline_receipt_path, baseline_root, baseline_summary = c1.c1_baseline_identity(arm)
    baseline_preflight = read_json(baseline_root / "preflight.json")
    identity = validate_arm_identity(arm, run_root, receipt, receipt_path, preflight,
                                     baseline_preflight, baseline_receipt, baseline_receipt_path,
                                     baseline_root, reviewed_preflight, build, auditor, runner)
    trace_row = auditor.output_row(receipt, auditor.TRACE_NAME, arm)
    trace_path = run_root / "run" / trace_row["compressed_path"]
    c1.verify_compressed_output(trace_path, trace_row, arm)
    snapshots = runner.read_time_snapshots(trace_path, 640)
    schedule = runner.snapshot_schedule(640)
    completed = auditor.derive_prefix(receipt, arm) if receipt.get("snapshots", {}).get(
        "completed_post_kdm6_timesteps") else []
    require(snapshots.get("completed_post_kdm6_timesteps", []) == completed and
            not snapshots.get("duplicate_post_kdm6_timesteps"),
            f"{arm}: decoded trace completed prefix or POST_KDM6 uniqueness differs from receipt")

    trace_cmp = equivalence_status(compare.compare_first_600_seconds(
        baseline_root, baseline_receipt, run_root, receipt, arm))
    history_files = c1.verify_receipt_history(run_root, receipt)
    history_cmp = equivalence_status(compare.compare_closed_histories(
        baseline_root, baseline_receipt, run_root, receipt, arm))
    t1_payload_identity = compare_t1_payloads(
        run_root, receipt, receipt_path, baseline_root, baseline_receipt,
        baseline_receipt_path, arm, auditor)
    source_policy = (auditor.audit_arm(run_root, arm) if completed else {
        "qnb_pair_conversion_audit": {"status": "NOT_EVALUATED", "reason": "no completed POST_KDM6 states"},
        "exact_source_endpoint_audit": {"status": "NOT_EVALUATED", "reason": "no completed endpoints"},
        "active_ice_policy_split": {"status": "NOT_EVALUATED", "reason": "no completed states"}})
    procedure = procedural_status(receipt, completed, snapshots, schedule)
    require(sha256(receipt_path) == identity["run_receipt_sha256"] and
            sha256(preflight_path) == identity["run_preflight_sha256"] and
            sha256(trace_path) == trace_row["compressed_sha256"],
            f"{arm}: receipt, preflight, or trace changed during audit")
    regression_ready = all(row["status"] == "PASS" for row in (trace_cmp, history_cmp))
    return {"arm": arm, "identity": identity, "procedural": procedure,
            "first_600_trace_equivalence": trace_cmp,
            "first_600_history_equivalence": history_cmp,
            "t1_payload_identity": t1_payload_identity,
            "generic_qnb": source_policy["qnb_pair_conversion_audit"],
            "exact_source_endpoint": source_policy["exact_source_endpoint_audit"],
            "active_ice_policy": source_policy["active_ice_policy_split"],
            "regression_approval": "READY_FOR_REVIEW" if regression_ready else "PENDING_SOURCE_BACKED_EXPLANATION",
            "trace": {"row": trace_row, "snapshots": snapshots,
                      "sha256_after_audit": sha256(trace_path)},
            "receipt_history_files": history_files,
            "physical_disposition": "FAIL_OPEN"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    roots = {arm: RUNS / arm for arm in ARMS}
    require(not args.output.exists(), f"output already exists: {args.output}")
    closed_receipts = {}
    for arm, root in roots.items():
        receipt_path, preflight_path = root / "receipt.json", root / "preflight.json"
        require(receipt_path.is_file() and preflight_path.is_file(),
                f"{arm}: run receipt/preflight absent; closed-only audit will not read live run")
        receipt = read_json(receipt_path)
        require(receipt.get("status") in ("COMPLETE", "INCOMPLETE"),
                f"{arm}: receipt is not finalized; refusing to read run outputs")
        closed_receipts[arm] = sha256(receipt_path)
    build, preflight, root_go = check_global_pins()
    c1.verify_reader_pins()
    auditor = c1.load_closed_auditor()
    runner = c1.load_frozen_runner()
    arms = {}
    for arm in ARMS:
        try:
            arms[arm] = audit_arm(arm, roots[arm], build, preflight, auditor, runner)
        except Exception as error:
            arms[arm] = {"arm": arm, "audit_status": "FAIL",
                         "error_type": type(error).__name__, "error": str(error),
                         "physical_disposition": "FAIL_OPEN"}
    require(all(sha256(roots[arm] / "receipt.json") == closed_receipts[arm] for arm in ARMS),
            "a finalized run receipt changed during the multi-arm audit")
    require(sha256(BUILD) == BUILD_SHA and sha256(Path(build["executable_path"])) == EXE_SHA and
            sha256(PREFLIGHT) == PREFLIGHT_SHA and sha256(ROOT_GO) == ROOT_GO_SHA,
            "reviewed C2 build/preflight/GO changed during audit")
    result = {"schema": "pr99_c2_closed_audit_v1", "candidate": "PR99-C2",
              "reviewed_c2_preflight_sha256": PREFLIGHT_SHA,
              "root_launch_go_sha256": ROOT_GO_SHA, "build_receipt_sha256": BUILD_SHA,
              "executable_sha256": EXE_SHA, "reader_pins": c1.verify_reader_pins(),
              "driver_path": str(Path(__file__).resolve()),
              "driver_sha256": sha256(Path(__file__).resolve()),
              "run_roots": {arm: str(roots[arm]) for arm in ARMS},
              "arms": arms, "overall_disposition": "FAIL_OPEN",
              "note": "Procedural completion and C1 equivalence are separate; every C2 difference requires source-backed explanation before regression approval."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(args.output)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError, EOFError, RuntimeError) as error:
        raise SystemExit(f"PR99-C2 closed audit refused: {error}")
