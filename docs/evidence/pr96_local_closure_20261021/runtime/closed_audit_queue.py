#!/usr/bin/env python3
"""Wait for closed PR96 C1 receipts, then run the frozen PR93 arm audit."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

ROOT = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr96_local_closure_20261021/Cloud-BAL")
RUNS = ROOT.parent / "runs_on_lustre"
BUILD_PATH = Path("/var/tmp/pr96_native_build_c1_20261021/pr87_native_overlay_build.json")
EXPECTED_EXE = "a714f00d3f81c0b47d94aef815f1f765ae48842e9de629cb869323ccfc22a96d"
EXPECTED_BUILD_SCHEMA = "pr87_native_overlay_build_v1"
ARMS = ("OFF", "HYDRO", "COUPLED")

sys.path.insert(0, str(ROOT / "tools"))
import pr94_longrun_audit as longrun  # noqa: E402
import pr95_closed_results as pr95  # noqa: E402


class QueueError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def is_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value.lower())


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise QueueError(f"expected JSON object: {path}")
    return value


def wait_closed_receipt(root: Path, arm: str, deadline: float, poll: float) -> tuple[dict, Path]:
    path = root / "receipt.json"
    while time.monotonic() < deadline:
        try:
            receipt = read_json(path)
        except (FileNotFoundError, json.JSONDecodeError):
            time.sleep(min(poll, max(0.0, deadline - time.monotonic())))
            continue
        if receipt.get("status") in ("COMPLETE", "INCOMPLETE"):
            # Frozen gate checks collector closure and arm identity. No run output is opened here.
            closed, closed_path = longrun.frozen.closed_receipt(root, arm)
            return closed, closed_path
        time.sleep(min(poll, max(0.0, deadline - time.monotonic())))
    raise QueueError(f"timed out waiting for finalized {arm} receipt: {path}")


def verify_run_bindings(roots: dict[str, Path], receipts: dict[str, tuple[dict, Path]],
                        build: dict, build_sha: str,
                        verify_staged_executable: bool = True) -> dict:
    exe_hashes, build_ids, boundary_hashes, profile_hashes = {}, {}, {}, {}
    per_arm = {}
    common_inputs: dict[str, str] | None = None
    fp_rows = {}
    launch_envs = {}
    for arm in ARMS:
        pre_path = roots[arm] / "preflight.json"
        pre = read_json(pre_path)
        receipt, receipt_path = receipts[arm]
        candidate = pre.get("candidate_build", {})
        expected_receipt_path = str(BUILD_PATH)
        profile_path = Path(candidate.get("profile_path", ""))
        executable_path = Path(candidate.get("executable_path", ""))
        input_hashes = pre.get("input_hashes")
        if not isinstance(input_hashes, dict) or not input_hashes:
            raise QueueError(f"{arm}: preflight input hash map is missing")
        if (pre.get("arm") != arm or pre.get("duration_seconds") != 600
                or pre.get("timestep_seconds") != 20 or pre.get("expected_timesteps") != 30
                or candidate.get("receipt_path") != expected_receipt_path
                or candidate.get("receipt_sha256") != build_sha
                or candidate.get("schema") != EXPECTED_BUILD_SCHEMA
                or candidate.get("executable_sha256") != EXPECTED_EXE
                or candidate.get("executable_sha256") != build.get("executable_sha256")
                or candidate.get("profile_sha256") != build.get("compiler_profile_sha256")
                or candidate.get("executable_path") != build.get("executable_path")
                or candidate.get("profile_path") != build.get("compiler_profile_path")
                or not all(is_sha256(value) for value in (
                    candidate.get("receipt_sha256"), candidate.get("profile_sha256"),
                    candidate.get("executable_sha256"), pre.get("candidate_wrfinput_sha256"),
                    pre.get("candidate_wrfbdy_sha256"), pre.get("candidate_namelist_sha256"),
                    pre.get("source_receipt_sha256"))) or not pre.get("source_receipt")):
            raise QueueError(f"{arm}: preflight does not pin the requested C1 build and 600s/20s/30-step gate")
        if sha256(profile_path) != candidate["profile_sha256"]:
            raise QueueError(f"{arm}: compiler profile hash differs from C1 build")
        if sha256(executable_path) != candidate["executable_sha256"]:
            raise QueueError(f"{arm}: built C1 executable hash differs from preflight")
        if (receipt.get("arm", "").upper() != arm
                or receipt.get("executed_executable_sha256") != EXPECTED_EXE
                or receipt.get("expected_executed_executable_sha256") != EXPECTED_EXE
                or receipt.get("candidate_build") != candidate
                or receipt.get("source_receipt_sha256") != pre.get("source_receipt_sha256")
                or receipt.get("candidate_input_binding") != pre.get("candidate_input_binding")
                or receipt.get("candidate_wrfinput_sha256") != pre["candidate_wrfinput_sha256"]
                or receipt.get("candidate_wrfbdy_sha256") != pre["candidate_wrfbdy_sha256"]
                or receipt.get("candidate_namelist_sha256") != pre.get("candidate_namelist_sha256")
                or receipt.get("candidate_build_unchanged") is not True
                or receipt.get("candidate_input_unchanged") is not True
                or receipt.get("processing_errors") != []
                or receipt.get("changed_staged_inputs") != []
                or receipt.get("changed_original_inputs") != []):
            raise QueueError(f"{arm}: closed receipt differs from its pinned preflight")
        source_receipt_path = Path(pre["source_receipt"])
        if sha256(source_receipt_path) != pre["source_receipt_sha256"]:
            raise QueueError(f"{arm}: source receipt changed from the preflight pin")
        expected_times = receipt.get("expected_model_timestamps")
        timestamp_rows = receipt.get("model_timestamps")
        if not isinstance(timestamp_rows, list) or any(not isinstance(row, dict) for row in timestamp_rows):
            raise QueueError(f"{arm}: closed receipt has malformed model timestamp rows")
        model_times = [row.get("timestamp") for row in timestamp_rows]
        expected_schedule = [
            (longrun.dt.datetime(2026, 8, 16, 13) + longrun.dt.timedelta(seconds=20 * step))
            .strftime("%Y-%m-%d_%H:%M:%S") for step in range(1, 31)
        ]
        if expected_times != expected_schedule:
            raise QueueError(f"{arm}: receipt lacks the expected exact 30-step timestamp schedule")
        if receipt.get("status") == "COMPLETE":
            if (model_times != expected_times or receipt.get("final_completed_step") != 30
                    or receipt.get("timestep_count") != 30):
                raise QueueError(f"{arm}: COMPLETE receipt does not prove all 30 requested timestamps")
            timestamp_gate = "PASS"
        else:
            if model_times != expected_times[:len(model_times)]:
                raise QueueError(f"{arm}: INCOMPLETE receipt timestamps are not a contiguous requested prefix")
            timestamp_gate = "INCOMPLETE"
        if verify_staged_executable:
            staged_run_exe = roots[arm] / "run" / "wrf.exe"
            if sha256(staged_run_exe) != EXPECTED_EXE:
                raise QueueError(f"{arm}: closed run/wrf.exe differs from pinned C1 executable")
        exe_hashes[arm] = receipt["executed_executable_sha256"]
        build_ids[arm] = candidate.get("receipt_sha256")
        boundary_hashes[arm] = pre["candidate_wrfbdy_sha256"]
        profile_hashes[arm] = candidate.get("profile_sha256")
        launch_envs[arm] = pre.get("launch_environment")
        fp_rows[arm] = {"compiler_profile_sha256": candidate.get("profile_sha256"),
                        "launch_environment": pre.get("launch_environment")}
        inputs = dict(input_hashes)
        # wrfinput is arm-specific; all shared model/data inputs must match.
        inputs.pop("wrfinput_d01", None)
        if common_inputs is None:
            common_inputs = inputs
        elif inputs != common_inputs:
            raise QueueError(f"{arm}: shared staged model/data input hashes differ across arms")
        per_arm[arm] = {
            "receipt_path": str(receipt_path), "receipt_sha256": sha256(receipt_path),
            "receipt_status": receipt["status"], "returncode": receipt.get("returncode"),
            "final_completed_step": receipt.get("final_completed_step"),
            "requested_duration_seconds": pre["duration_seconds"],
            "timestep_seconds": pre["timestep_seconds"],
            "expected_steps": pre["expected_timesteps"],
            "duration_gate": ("PASS" if receipt.get("status") == "COMPLETE"
                              and receipt.get("returncode") == 0
                              and receipt.get("final_completed_step") == 30 else
                              "INCOMPLETE" if receipt.get("status") == "INCOMPLETE"
                              else "FAIL"),
            "timestamp_gate": timestamp_gate,
            "candidate_wrfinput_sha256": pre["candidate_wrfinput_sha256"],
            "candidate_wrfbdy_sha256": pre["candidate_wrfbdy_sha256"],
            "candidate_namelist_sha256": pre["candidate_namelist_sha256"],
            "preflight_path": str(pre_path), "preflight_sha256": sha256(pre_path),
        }
    if len(set(exe_hashes.values())) != 1 or len(set(build_ids.values())) != 1:
        raise QueueError("C1 arms do not share executable and build receipt identity")
    if (len(set(profile_hashes.values())) != 1 or len(set(boundary_hashes.values())) != 1
            or len({json.dumps(value, sort_keys=True) for value in launch_envs.values()}) != 1):
        raise QueueError("C1 arms do not share compiler profile, launch FP environment, or boundary-input identity")
    return {"arms": per_arm, "shared_executable_sha256": next(iter(exe_hashes.values())),
            "shared_build_receipt_sha256": next(iter(build_ids.values())),
            "shared_wrfbdy_sha256": next(iter(boundary_hashes.values())),
            "shared_compiler_profile_sha256": next(iter(profile_hashes.values())),
            "shared_input_hashes_sha256": hashlib.sha256(json.dumps(common_inputs, sort_keys=True).encode()).hexdigest(),
            "fp_environment_sha256": {arm: hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()
                                      for arm, row in fp_rows.items()},
            "fp_environment": fp_rows}


def run_queue(output_dir: Path, timeout: float, poll: float) -> dict:
    if output_dir.resolve().is_relative_to(ROOT.resolve()):
        raise QueueError("audit output must remain outside the checkout")
    pinned_head = pr95.startup_head(ROOT)
    reader_pins_before = pr95.verify_source_pins(ROOT)
    queue_pin = sha256(Path(__file__).resolve())
    build = read_json(BUILD_PATH)
    if (build.get("status") != "PASS_OVERLAY_BUILD" or build.get("schema") != EXPECTED_BUILD_SCHEMA
            or build.get("executable_sha256") != EXPECTED_EXE or build.get("model_run") is not False):
        raise QueueError("C1 native overlay build receipt differs from the reviewed pin")
    deadline = time.monotonic() + timeout
    roots = {arm: RUNS / f"{arm}_600s_c1" for arm in ARMS}
    # Close all three runs before opening any trace or other run output.
    receipts = {arm: wait_closed_receipt(roots[arm], arm, deadline, poll) for arm in ARMS}
    build_sha = sha256(BUILD_PATH)
    bindings = verify_run_bindings(roots, receipts, build, build_sha)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(exist_ok=False)
    audits = {}
    for arm in ARMS:
        audit = longrun.frozen.audit_arm(roots[arm], arm)
        audit_path = output_dir / f"{arm}_600s_c1_audit.json"
        with audit_path.open("x", encoding="utf-8") as stream:
            json.dump(audit, stream, indent=2)
            stream.write("\n")
        audits[arm] = {"path": str(audit_path), "sha256": sha256(audit_path),
                       "receipt_status": audit["receipt"]["status"],
                       "completed_steps": len(audit["receipt"]["completed_prefix"]),
                       "generic": audit["qnb_pair_conversion_audit"]["status"],
                       "exact_source_endpoint": audit["exact_source_endpoint_audit"]["status"],
                       "active_ice_8ulp": audit["active_ice_policy_split"]["status"]}
    # Ensure receipts and code pins did not change while the closed audits ran.
    for arm in ARMS:
        receipt, receipt_path = receipts[arm]
        if sha256(receipt_path) != bindings["arms"][arm]["receipt_sha256"]:
            raise QueueError(f"{arm}: closed receipt changed during audit")
    reader_pins_after = pr95.verify_source_pins(ROOT)
    if (reader_pins_after != reader_pins_before
            or sha256(Path(__file__).resolve()) != queue_pin
            or sha256(BUILD_PATH) != build_sha
            or sha256(Path(build["executable_path"])) != EXPECTED_EXE
            or sha256(Path(build["compiler_profile_path"])) != build["compiler_profile_sha256"]):
        raise QueueError("reader source pins or queue script changed during audit")
    overview = {"schema": "pr96_c1_closed_audit_queue_v1",
                "status": "REVIEW_REQUIRED", "review_required": True,
                "physical_approval": "FAIL_OPEN", "audit_reader_startup_head": pinned_head,
                "source_checkout_head_at_result": pr95.startup_head(ROOT),
                "head_scope": "HEAD may advance for publication; all seven actual audit reader source hashes must remain unchanged.",
                "queue_source_sha256": queue_pin,
                "reader_dependency_pins": reader_pins_before,
                "build_receipt_path": str(BUILD_PATH), "build_receipt_sha256": sha256(BUILD_PATH),
                "build_executable_sha256": EXPECTED_EXE, "runtime_bindings": bindings,
                "arms": audits,
                "scope": "Audits only receipt-closed C1 runs. Frozen PR93 per-arm checks keep generic Q/N/B, exact source endpoint, and 8-ULP active-ice statuses distinct. Incomplete receipts remain incomplete; no status is promoted to PASS by the queue. No pre-closure history or binary is read."}
    overview_path = output_dir / "overview.json"
    with overview_path.open("x", encoding="utf-8") as stream:
        json.dump(overview, stream, indent=2)
        stream.write("\n")
    return overview


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path,
                        default=ROOT.parent / "closed_audits" / "pr96_c1_20261021")
    parser.add_argument("--timeout-seconds", type=float, default=43200)
    parser.add_argument("--poll-seconds", type=float, default=20)
    args = parser.parse_args()
    try:
        result = run_queue(args.output_dir, args.timeout_seconds, args.poll_seconds)
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        parser.error(str(error))
    print(json.dumps({"status": result["status"], "output_dir": str(args.output_dir),
                      "arms": result["arms"]}, indent=2))


if __name__ == "__main__":
    main()
