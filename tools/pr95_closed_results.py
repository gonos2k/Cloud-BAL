#!/usr/bin/env python3
"""Queue receipt-closed PR95 results; never inspect a live run's outputs."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path
from typing import Callable

import pr94_longrun_audit as longrun

ROOT = Path(__file__).resolve().parents[1]
DEPENDENCY_PINS = {
    "tools/pr94_longrun_audit.py": "0ce4eb5a00fa5065aef71be5436b1894813e6d3bdca9d5904283ef72dca326d1",
    "tools/pr86_compare_response.py": "64b2f97f452035cae328576d26216c54877fa778b3eeabe17cdb9980103aaa5c",
    "tools/pr87_native_history.py": "d6feb0e5fd5d53a60d7256a7b3c4faaa3c7f2488b799af25278aec7529c28a71",
    "tools/pr86_water_budget.py": "e6c00374e9730278b3c1545630af9aa3a6af4c68544c7f39dbda61f909337dc2",
    "tools/pr87_completed_state_audit.py": "2daef11c005868abf58631d84df74b8535eccb217660fbd605bd8f03216ee70d",
    "tools/pr85_joint_stage_trace.py": "5c2e9ccb3537a6bc251845e2b87c3efb991002ebbc1db5232d475e29f6c31720",
    "docs/evidence/pr93_active_ice_20261020/runtime/closed_run_audit.py": longrun.FROZEN_AUDITOR_SHA256,
}


class ClosedResultsError(RuntimeError):
    """A requested receipt or bound audit is missing, open, or inconsistent."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_source_pins(root: Path = ROOT,
                       pins: dict[str, str] = DEPENDENCY_PINS) -> dict[str, str]:
    observed = {}
    for relative, expected in pins.items():
        path = root / relative
        if not expected or not path.is_file():
            raise ClosedResultsError(f"reader dependency pin is unavailable: {relative}")
        observed[relative] = sha256(path)
        if observed[relative] != expected:
            raise ClosedResultsError(f"reader dependency changed: {relative}")
    return observed


def startup_head(root: Path = ROOT) -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()


def wait_for_receipt(root: Path, arm: str, timeout_seconds: float,
                     poll_seconds: float = 30.0,
                     sleep: Callable[[float], None] = time.sleep) -> tuple[dict, Path]:
    """Poll only receipt.json until the pinned closed reader accepts it."""
    receipt_path = root / "receipt.json"
    deadline = time.monotonic() + timeout_seconds
    while True:
        if receipt_path.is_file():
            try:
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as error:
                raise ClosedResultsError(f"{arm}: malformed runner receipt: {error}") from error
            if not isinstance(receipt, dict):
                raise ClosedResultsError(f"{arm}: runner receipt must contain a JSON object")
            if receipt.get("status") in ("COMPLETE", "INCOMPLETE"):
                try:
                    return longrun.frozen.closed_receipt(root, arm)
                except (ValueError, KeyError, RuntimeError) as error:
                    raise ClosedResultsError(f"{arm}: invalid closed runner receipt: {error}") from error
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ClosedResultsError(f"{arm}: timed out waiting for a finalized receipt at {receipt_path}")
        sleep(min(poll_seconds, remaining))


def wait_for_json(path: Path, timeout_seconds: float, poll_seconds: float = 30.0,
                  sleep: Callable[[float], None] = time.sleep) -> tuple[dict, str]:
    deadline = time.monotonic() + timeout_seconds
    while True:
        if path.is_file():
            try:
                result = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(result, dict):
                    return result, sha256(path)
            except (OSError, json.JSONDecodeError):
                pass
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        sleep(min(poll_seconds, remaining))
    raise ClosedResultsError(f"timed out waiting for a complete old audit JSON: {path}")


def _reuse_trace_audit(path: Path, digest: str, result: dict,
                       receipt_path: Path, receipt_hash: str,
                       baseline_receipt_path: Path, baseline_hash: str,
                       result_receipt: dict, result_baseline: dict,
                       arm: str, duration: int) -> dict:
    expected_baseline_hash = result.get("runtime", {}).get("baseline_receipt_sha256")
    expected_run_hash = result.get("runtime", {}).get("receipt_sha256")
    if (result.get("schema") != "pr94_compact_longrun_audit_v1"
            or result.get("arm") != arm
            or result.get("requested_duration_seconds") != duration
            or Path(result["runtime"]["receipt_path"]).resolve() != receipt_path.resolve()
            or expected_run_hash != receipt_hash
            or expected_run_hash != result.get("runtime", {}).get("receipt_sha256")
            or Path(result["runtime"]["baseline_receipt_path"]).resolve() != baseline_receipt_path.resolve()
            or expected_baseline_hash != baseline_hash
            or sha256(path) != digest
            or result.get("runtime_binding", {}).get("status") != "PASS"):
        raise ClosedResultsError(f"{arm}: old trace audit lacks matching receipt/runtime bindings")
    if (expected_run_hash != result_receipt.get("_receipt_sha256")
            or expected_baseline_hash != result_baseline.get("_receipt_sha256")):
        raise ClosedResultsError(f"{arm}: old trace audit is not bound to the just-closed receipts")
    return {"path": str(path), "sha256": digest,
            "trace_status": {key: result[key].get("status") for key in
                             ("compact_profile", "first_600_seconds_baseline_comparison",
                              "generic_completed_state_audit", "exact_source_endpoint_audit",
                              "active_ice_policy_split")},
            "duration_complete": result["runtime"]["duration_complete"]}


def _closed_arm_result(arm: str, duration: int,
                       compact_root: Path, compact_receipt: dict, compact_receipt_path: Path,
                       baseline_root: Path, baseline_receipt: dict, baseline_receipt_path: Path,
                       old_audit_path: Path, timeout_seconds: float, poll_seconds: float) -> dict:
    compact_hash, baseline_hash = sha256(compact_receipt_path), sha256(baseline_receipt_path)
    compact_receipt["_receipt_sha256"] = compact_hash
    baseline_receipt["_receipt_sha256"] = baseline_hash
    old_trace, old_hash = wait_for_json(old_audit_path, timeout_seconds, poll_seconds)
    # Validate the preexisting result without rerunning its expensive trace scan.
    trace = _reuse_trace_audit(
        old_audit_path, old_hash, old_trace, compact_receipt_path, compact_hash,
        baseline_receipt_path, baseline_hash, compact_receipt, baseline_receipt, arm, duration)
    # The pinned API binds staged build, inputs, namelist and executable before history comparison.
    binding = longrun._verify_runtime_bindings(
        compact_root, baseline_root, compact_receipt, baseline_receipt, arm, duration)
    history = longrun.compare_closed_histories(
        baseline_root, baseline_receipt, compact_root, compact_receipt, arm)
    return {"arm": arm, "trace_audit": trace, "runtime_binding": binding,
            "history_comparison": history,
            "receipt_hashes": {"compact": compact_hash, "baseline": baseline_hash},
            "receipt_paths": {"compact": str(compact_receipt_path),
                              "baseline": str(baseline_receipt_path)}}


def _hydro_skip(root: Path, timeout_seconds: float, poll_seconds: float) -> dict:
    receipt, receipt_path = wait_for_receipt(root, "HYDRO", timeout_seconds, poll_seconds)
    step_seconds = int(receipt.get("runner_timestep_seconds", 20))
    completed_seconds = int(receipt.get("final_completed_step", 0)) * step_seconds
    expected_partial = (receipt.get("status") == "INCOMPLETE"
                        and receipt.get("returncode") == 128 and completed_seconds == 500)
    reason = ("HYDRO ended incomplete with return code 128 at 500 seconds; no normal 600-second response was produced"
              if expected_partial else
              "HYDRO response is not evaluated by this queue; no normal 600-second response is produced here")
    return {"status": "SKIP", "reason": reason, "expected_incomplete_500s_control": expected_partial,
            "receipt_path": str(receipt_path), "receipt_sha256": sha256(receipt_path),
            "receipt_status": receipt.get("status"), "returncode": receipt.get("returncode"),
            "completed_seconds": completed_seconds, "requested_seconds": 600,
            "normal_600_second_response": "NOT_RUN"}


def run_queue(compact_roots: dict[str, Path], baseline_roots: dict[str, Path],
              old_audits: dict[str, Path], hydro_root: Path, output: Path,
              timeout_seconds: float = 43200, poll_seconds: float = 30,
              root: Path = ROOT) -> dict:
    if output.resolve().is_relative_to(root.resolve()):
        raise ClosedResultsError("queue output must be outside the source checkout")
    pinned_head = startup_head(root)
    queue_path = Path(__file__).resolve()
    queue_pin = sha256(queue_path)
    pins_before = verify_source_pins(root)
    # Close every run before opening any history or staged binary. Receipt polling is metadata-only.
    compact_receipts = {arm: wait_for_receipt(compact_roots[arm], arm, timeout_seconds, poll_seconds)
                        for arm in ("OFF", "COUPLED")}
    baseline_receipts = {arm: wait_for_receipt(baseline_roots[arm], arm, timeout_seconds, poll_seconds)
                         for arm in ("OFF", "COUPLED")}
    hydro = _hydro_skip(hydro_root, timeout_seconds, poll_seconds)
    arms = {}
    for arm, duration in (("OFF", 3600), ("COUPLED", 3600)):
        # Reuse closed receipt objects already gated above; pass the path roots to pinned APIs.
        compact_receipt, compact_receipt_path = compact_receipts[arm]
        baseline_receipt, baseline_receipt_path = baseline_receipts[arm]
        arms[arm] = _closed_arm_result(
            arm, duration, compact_roots[arm], compact_receipt, compact_receipt_path,
            baseline_roots[arm], baseline_receipt, baseline_receipt_path,
            old_audits[arm], timeout_seconds, poll_seconds)
    for arm in arms.values():
        for kind, expected_hash in arm["receipt_hashes"].items():
            if sha256(Path(arm["receipt_paths"][kind])) != expected_hash:
                raise ClosedResultsError(f"{arm['arm']}: finalized {kind} receipt changed during queue")
        if sha256(Path(arm["trace_audit"]["path"])) != arm["trace_audit"]["sha256"]:
            raise ClosedResultsError(f"{arm['arm']}: reused trace audit changed during queue")
    pins_after = verify_source_pins(root)
    if (pins_after != pins_before or startup_head(root) != pinned_head
            or sha256(queue_path) != queue_pin):
        raise ClosedResultsError("reader sources, queue source, or startup HEAD changed during closed audit queue")
    gates = []
    for arm in arms.values():
        gates.extend((arm["trace_audit"]["duration_complete"],
                      arm["trace_audit"]["trace_status"]["compact_profile"] == "PASS",
                      arm["trace_audit"]["trace_status"]["first_600_seconds_baseline_comparison"] == "PASS",
                      arm["runtime_binding"]["status"] == "PASS",
                      arm["history_comparison"]["status"] == "PASS"))
    result = {"schema": "pr95_closed_results_queue_v1",
              "status": "REVIEW_REQUIRED",
              "longrun_procedural_comparison": "PASS" if all(gates) else "INCOMPLETE_OR_FAIL",
              "review_required": True, "physical_approval": "FAIL_OPEN",
              "startup_head": pinned_head, "queue_source_sha256": queue_pin,
              "reader_dependency_pins": pins_before,
              "hydro": hydro, "arms": arms,
              "scope": "Reuses closed PR94 trace audit outputs and independently compares the 10 receipt-bound raw history fields. No live/running binary or history is read; only receipt-closed histories are compared. HYDRO incomplete means no normal 600-second response."}
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2)
            stream.write("\n")
    except FileExistsError as error:
        raise ClosedResultsError(f"refusing to overwrite queue result: {output}") from error
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--off-root", type=Path, required=True)
    parser.add_argument("--coupled-root", type=Path, required=True)
    parser.add_argument("--hydro-root", type=Path, required=True)
    parser.add_argument("--baseline-off-root", type=Path, required=True)
    parser.add_argument("--baseline-coupled-root", type=Path, required=True)
    parser.add_argument("--off-audit", type=Path, required=True)
    parser.add_argument("--coupled-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("/var/tmp/pr95_closed_results_20261021.json"))
    parser.add_argument("--timeout-seconds", type=float, default=43200)
    parser.add_argument("--poll-seconds", type=float, default=30)
    args = parser.parse_args()
    try:
        result = run_queue(
            {"OFF": args.off_root, "COUPLED": args.coupled_root},
            {"OFF": args.baseline_off_root, "COUPLED": args.baseline_coupled_root},
            {"OFF": args.off_audit, "COUPLED": args.coupled_audit},
            args.hydro_root, args.output, args.timeout_seconds, args.poll_seconds)
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        parser.error(str(error))
    print(json.dumps({"status": result["status"],
                      "longrun_procedural_comparison": result["longrun_procedural_comparison"],
                      "output": str(args.output),
                      "hydro": result["hydro"]["status"],
                      "arms": {arm: row["history_comparison"]["status"]
                               for arm, row in result["arms"].items()}}))


if __name__ == "__main__":
    main()
