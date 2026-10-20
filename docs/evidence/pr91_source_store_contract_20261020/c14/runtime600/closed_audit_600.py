#!/usr/bin/env python3
"""C14 600-second closure audit; all trace parsing is delegated to the reviewed C14/C13 helpers."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import importlib.util

HERE = Path(__file__).resolve().parent
AUDITOR_PATH = HERE.parent / "runtime/closed_audit.py"
spec = importlib.util.spec_from_file_location("pr91_c14_audit", AUDITOR_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot load shared C14 auditor {AUDITOR_PATH}")
shared = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shared)
EXPECTED_EXE_SHA256 = shared.EXPECTED_EXE_SHA256
EXPECTED_BUILD_SHA256 = shared.EXPECTED_BUILD_SHA256


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def verify_identity(arm: str, receipt: dict, preflight: dict) -> dict:
    run_root = Path(f"/var/tmp/pr91_{arm}_600s_c14_20261020")
    build_path = Path(preflight["candidate_build"]["receipt_path"])
    build = json.loads(build_path.read_text())
    mismatches = []
    for name, expected in preflight["input_hashes"].items():
        if name in ("wrf.exe", "namelist.input"):
            continue
        path = run_root / "run" / name
        if not path.exists() or sha(path) != expected:
            mismatches.append(name)
    checks = {
        "closed_receipt": receipt["status"] in ("COMPLETE", "INCOMPLETE") and "returncode" in receipt,
        "build_receipt_hash": sha(build_path) == EXPECTED_BUILD_SHA256,
        "build_executable_hash": build.get("executable_sha256") == EXPECTED_EXE_SHA256,
        "receipt_build_binding": receipt["candidate_build"]["receipt_sha256"] == EXPECTED_BUILD_SHA256,
        "receipt_preflight_build_binding": preflight["candidate_build"]["receipt_sha256"] == EXPECTED_BUILD_SHA256,
        "executed_executable_hash": receipt["executed_executable_sha256"] == receipt["expected_executed_executable_sha256"] == EXPECTED_EXE_SHA256,
        "source_receipt_binding": receipt["source_receipt_sha256"] == preflight["source_receipt_sha256"],
        "candidate_build_unchanged": receipt["candidate_build_unchanged"],
        "no_changed_original_or_staged_inputs": not receipt["changed_original_inputs"] and not receipt["changed_staged_inputs"],
        "unchanged_runtime_inputs": not mismatches,
        "run_executable_file_hash": sha(run_root / "run/wrf.exe") == EXPECTED_EXE_SHA256,
        "run_namelist_hash": sha(run_root / "run/namelist.input") == preflight["candidate_namelist_sha256"],
    }
    return {"arm": arm, "status": receipt["status"], "returncode": receipt["returncode"],
            "final_completed_step": receipt["final_completed_step"],
            "maximum_seen_timestep": receipt["maximum_seen_timestep"],
            "input_mismatches": mismatches, "checks": checks,
            "all_identity_checks_pass": all(checks.values()),
            "receipt_sha256": sha(HERE / f"{arm.lower()}_receipt.json"),
            "preflight_sha256": sha(HERE / f"{arm.lower()}_preflight.json"),
            "build_receipt_sha256": sha(build_path),
            "fatal_lines": receipt["fatal_lines"], "run_identity": receipt["run_identity"]}


def audit_arm(arm: str) -> dict:
    low = arm.lower()
    run_root = Path(f"/var/tmp/pr91_{arm}_600s_c14_20261020")
    receipt = json.loads((HERE / f"{low}_receipt.json").read_text())
    preflight = json.loads((HERE / f"{low}_preflight.json").read_text())
    identity = verify_identity(arm, receipt, preflight)
    completed = int(receipt["final_completed_step"])
    if completed < 1:
        raise ValueError(f"{arm}: no completed state prefix to audit")
    # The shared selector/gates are parametric in this completed-prefix length.
    shared.EXPECTED_FINAL_STEP = completed
    prefix = shared.parse_c14_prefix(run_root, receipt, arm)
    transport = shared.c13.read_ledger(run_root)
    failures = shared.read_actual_store_failures(run_root, receipt)
    storage = shared.read_c14_storage_ledger(run_root, receipt)
    return {"identity": identity, "completed_prefix": prefix,
            "joint_transport": transport, "failure_diagnostics": failures,
            "c14_storage_ledger": storage}


def main() -> None:
    arms = {arm: audit_arm(arm) for arm in ("OFF", "COUPLED")}
    all_complete = all(x["identity"]["status"] == "COMPLETE" and x["identity"]["returncode"] == 0
                       for x in arms.values())
    checks_pass = all(
        x["identity"]["all_identity_checks_pass"]
        and x["completed_prefix"]["strict_state_status"] == "PASS"
        and x["completed_prefix"]["strict_source_boundaries"]["status"] == "PASS"
        and len(x["joint_transport"]["joint_rk_rows"]) == 3 * x["identity"]["final_completed_step"]
        and x["joint_transport"]["all_joint_theta_equal_one"]
        and x["joint_transport"]["all_joint_rows_feasible"]
        for x in arms.values())
    expected_30 = all(x["identity"]["final_completed_step"] == 30 for x in arms.values())
    status = "PASS_600" if all_complete and checks_pass and expected_30 else "CLOSED_PREFIX_REVIEW_REQUIRED"
    result = {"schema": "pr91_c14_closed_600s_audit_v1", "overall_status": status,
              "identity_scope": {"build_receipt_sha256": EXPECTED_BUILD_SHA256,
                                 "executable_sha256": EXPECTED_EXE_SHA256},
              "arms": arms}
    (HERE / "closed_runtime_audit_600.json").write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({arm: {"status": x["identity"]["status"],
        "completed_step": x["identity"]["final_completed_step"],
        "generic_state": x["completed_prefix"]["strict_state_status"],
        "exact_source": x["completed_prefix"]["strict_source_boundaries"]["status"],
        "joint_rows": len(x["joint_transport"]["joint_rk_rows"]),
        "theta1": x["joint_transport"]["all_joint_theta_equal_one"],
        "inactive_q_adjustments": x["c14_storage_ledger"]["inactive_q_quantum_adjustment_count_by_pair"]}
        for arm, x in arms.items()}, indent=2))


if __name__ == "__main__":
    main()
