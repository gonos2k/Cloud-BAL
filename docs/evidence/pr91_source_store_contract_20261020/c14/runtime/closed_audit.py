#!/usr/bin/env python3
"""C14 closure audit reusing the reviewed C13 bounded-prefix parsers."""
from __future__ import annotations
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = Path(__file__).resolve().parents[5]
C13_AUDITOR = REPO / "docs/evidence/pr91_source_store_contract_20261020/c13/runtime/closed_audit.py"
EXPECTED_BUILD_SHA256 = "273b08fa9bb31d4070f59c817b3d59f77154947366dbcf8edb53c546360e053f"
EXPECTED_EXE_SHA256 = "5581e1be3febd54409304ccf7cbe305830a75968858075bf0d95f68b48d812be"
EXPECTED_FINAL_STEP = 12

spec = importlib.util.spec_from_file_location("pr91_c13_closed_audit", C13_AUDITOR)
if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot load reviewed C13 auditor: {C13_AUDITOR}")
c13 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c13)
sys_path_tools = str(REPO / "tools")
if sys_path_tools not in __import__("sys").path:
    __import__("sys").path.insert(0, sys_path_tools)
import pr87_completed_state_audit as strict_audit


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def verify_identity(arm: str) -> dict:
    low = arm.lower()
    run_root = Path(f"/var/tmp/pr91_{arm}_240s_c14_20261020")
    pre = json.loads((HERE / f"{low}_preflight.json").read_text())
    rec = json.loads((HERE / f"{low}_receipt.json").read_text())
    build_path = Path(pre["candidate_build"]["receipt_path"])
    build = json.loads(build_path.read_text())
    status = rec["status"]
    checks = {
        "closed_complete_12_steps": (
            status == "COMPLETE" and rec["returncode"] == 0
            and rec["final_completed_step"] == EXPECTED_FINAL_STEP
            and rec["maximum_seen_timestep"] == EXPECTED_FINAL_STEP
        ),
        "candidate_c14_build_receipt": sha(build_path) == EXPECTED_BUILD_SHA256,
        "candidate_executable_hash": build["executable_sha256"] == EXPECTED_EXE_SHA256,
        "executed_executable_matches_candidate": (
            rec["executed_executable_sha256"] == rec["expected_executed_executable_sha256"]
            == EXPECTED_EXE_SHA256
        ),
        "receipt_source_binding": rec["source_receipt_sha256"] == pre["source_receipt_sha256"],
        "build_receipt_matches_preflight_and_run": (
            pre["candidate_build"]["receipt_sha256"]
            == rec["candidate_build"]["receipt_sha256"] == EXPECTED_BUILD_SHA256
        ),
        "build_status_pass_overlay": build["status"] == "PASS_OVERLAY_BUILD",
        "candidate_build_unchanged": rec["candidate_build_unchanged"],
        "no_changed_original_or_staged_inputs": (
            not rec["changed_original_inputs"] and not rec["changed_staged_inputs"]
        ),
    }
    mismatches = []
    for name, expected in pre["input_hashes"].items():
        if name in ("wrf.exe", "namelist.input"):
            continue
        path = run_root / "run" / name
        if not path.exists() or sha(path) != expected:
            mismatches.append(name)
    checks["all_noncandidate_runtime_inputs_match_preflight"] = not mismatches
    checks["runtime_executable_file_matches_candidate"] = sha(run_root / "run/wrf.exe") == EXPECTED_EXE_SHA256
    checks["runtime_namelist_matches_preflight"] = (
        sha(run_root / "run/namelist.input") == pre["candidate_namelist_sha256"]
    )
    return {
        "arm": arm,
        "run_status": status,
        "returncode": rec["returncode"],
        "final_completed_step": rec["final_completed_step"],
        "maximum_seen_timestep": rec["maximum_seen_timestep"],
        "receipt_sha256": sha(HERE / f"{low}_receipt.json"),
        "preflight_sha256": sha(HERE / f"{low}_preflight.json"),
        "build_receipt_sha256": sha(build_path),
        "executed_executable_sha256": rec["executed_executable_sha256"],
        "input_mismatches_excluding_expected_candidate_replacements": mismatches,
        "checks": checks,
        "all_checks_pass": all(checks.values()),
        "fatal_lines": rec["fatal_lines"],
        "run_identity": rec["run_identity"],
    }


def read_c14_storage_ledger(run_root: Path, receipt: dict) -> dict:
    artifact = next((x for x in receipt["compressed_outputs"] if x["path"] == "pr87_joint_storage.raw"), None)
    if artifact is None:
        raise ValueError("receipt lacks pr87_joint_storage.raw")
    path = run_root / "run" / artifact["compressed_path"]
    labels = {"JOINT_STORAGE", "INACTIVE_Q_QUANTUM_ADJUSTMENTS",
              "STORAGE_DELTA_PRESSURE_Q", "STORAGE_DELTA_PRESSURE_MOMENT"}
    logical_rows = []
    pending_label = None
    pending_values = []
    ignore_other_rows = False
    payload_hash = hashlib.sha256()
    payload_bytes = 0
    with gzip.open(path, "rb") as stream:
        for line_no, raw_line in enumerate(stream, 1):
            payload_hash.update(raw_line)
            payload_bytes += len(raw_line)
            tokens = raw_line.decode("ascii").split()
            if not tokens:
                continue
            if tokens[0] in labels:
                if pending_label is not None:
                    logical_rows.append((pending_label, pending_values))
                pending_label, pending_values = tokens[0], tokens[1:]
                ignore_other_rows = False
            elif tokens[0][0].isalpha() and tokens[0][0].isupper():
                if pending_label is not None:
                    logical_rows.append((pending_label, pending_values))
                    pending_label, pending_values = None, []
                # Other rows in pr87_joint_storage.raw are diagnostics, not ledger continuations.
                ignore_other_rows = True
            elif pending_label is not None:
                pending_values.extend(tokens)
            elif not ignore_other_rows:
                raise ValueError(f"orphan storage-ledger continuation at line {line_no}: {tokens}")
    if pending_label is not None:
        logical_rows.append((pending_label, pending_values))

    records = []
    current = None
    for label, values in logical_rows:
        if label == "JOINT_STORAGE":
            if current is not None:
                records.append(current)
            if len(values) != 7:
                raise ValueError(f"malformed JOINT_STORAGE row: {values}")
            step, rk, cells, *adjustments = map(int, values)
            current = {"timestep": step, "rk": rk, "cells": cells,
                       "storage_adjustments_by_pair": adjustments}
            continue
        if current is None:
            raise ValueError(f"{label} precedes JOINT_STORAGE")
        if label == "INACTIVE_Q_QUANTUM_ADJUSTMENTS":
            if len(values) != 4:
                raise ValueError(f"malformed inactive-Q adjustment row: {values}")
            current["inactive_q_quantum_adjustments_by_pair"] = list(map(int, values))
        elif label in ("STORAGE_DELTA_PRESSURE_Q", "STORAGE_DELTA_PRESSURE_MOMENT"):
            if len(values) != 4:
                raise ValueError(f"malformed {label} row: {values}")
            key = "storage_delta_pressure_q_by_pair" if label.endswith("_Q") else "storage_delta_pressure_moment_by_pair"
            if key in current:
                raise ValueError(f"duplicate {label} row")
            current[key] = [float(x.replace("D", "E").replace("d", "e")) for x in values]
        else:
            raise ValueError(f"unexpected storage ledger row {label}")
    if current is not None:
        records.append(current)
    required = ("inactive_q_quantum_adjustments_by_pair", "storage_delta_pressure_q_by_pair",
                "storage_delta_pressure_moment_by_pair")
    if any(any(key not in row for key in required) for row in records):
        raise ValueError("incomplete C14 joint-storage ledger block")
    per_pair_counts = [sum(row["inactive_q_quantum_adjustments_by_pair"][p] for row in records) for p in range(4)]
    return {
        "path": str(path),
        "compressed_sha256": sha(path),
        "compressed_sha256_matches_receipt": sha(path) == artifact["compressed_sha256"],
        "payload_sha256": payload_hash.hexdigest(),
        "payload_sha256_matches_receipt": payload_hash.hexdigest() == artifact["sha256"],
        "compressed_bytes": path.stat().st_size,
        "payload_bytes": payload_bytes,
        "record_count": len(records),
        "records": records,
        "inactive_q_quantum_adjustment_count_by_pair": per_pair_counts,
        "signed_storage_delta_scope": "per-pair Q/N, pressure-coordinate units; numerical storage representation only, not kg or energy closure",
        "source_representation_is_separate": True,
    }


def read_actual_store_failures(run_root: Path, receipt: dict) -> dict:
    artifact = next((x for x in receipt["compressed_outputs"] if x["path"] == "pr91_actual_store_failures.raw"), None)
    if artifact is None:
        raise ValueError("receipt lacks pr91_actual_store_failures.raw")
    path = run_root / "run" / artifact["compressed_path"]
    rows = {"ACTUAL_STORE_FAILURE": [], "ACTUAL_STORE_OPTIONS": []}
    payload_hash = hashlib.sha256()
    payload_bytes = 0
    with gzip.open(path, "rb") as stream:
        for line_no, raw_line in enumerate(stream, 1):
            payload_hash.update(raw_line)
            payload_bytes += len(raw_line)
            tokens = raw_line.decode("ascii").split()
            if tokens and tokens[0] in rows:
                rows[tokens[0]].append(tokens[1:])
    if len(rows["ACTUAL_STORE_FAILURE"]) != len(rows["ACTUAL_STORE_OPTIONS"]):
        raise ValueError("actual-store diagnostic rows and option rows do not pair")
    failures = []
    for idx, (failure, options) in enumerate(zip(rows["ACTUAL_STORE_FAILURE"], rows["ACTUAL_STORE_OPTIONS"])):
        if len(failure) < 9 or len(options) < 17:
            raise ValueError(f"malformed actual-store diagnostic pair {idx}")
        failures.append({
            "run_id": failure[0], "attempt_id": int(failure[1]),
            "timestep": int(failure[2]), "rk": int(failure[3]), "pair": int(failure[4]),
            "ijk": list(map(int, failure[5:8])), "failure_stage": int(failure[-2]),
            "adjustment_code": int(failure[-1]),
            "options_row": options,
        })
    return {
        "compressed_path": str(path),
        "compressed_sha256": sha(path),
        "compressed_sha256_matches_receipt": sha(path) == artifact["compressed_sha256"],
        "payload_sha256": payload_hash.hexdigest(),
        "payload_sha256_matches_receipt": payload_hash.hexdigest() == artifact["sha256"],
        "payload_bytes": payload_bytes,
        "partial_failed_call_rows": failures,
        "row_count": len(failures),
        "scope": "Sparse attempted-call failures only; retained separately from completed state and committed storage ledgers.",
    }


def parse_c14_prefix(run_root: Path, receipt: dict, arm: str) -> dict:
    original = c13.stage._pair_stats
    strict_by_state = []

    def pair_stats_with_exact_source_checks(fields, policy):
        pairs = original(fields, policy)
        checks = strict_audit._strict_source_checks(fields)
        strict_by_state.append({"checks": checks,
                                "violations": strict_audit._strict_source_violations(checks)})
        return pairs

    c13.stage._pair_stats = pair_stats_with_exact_source_checks
    try:
        prefix = c13.parse_stage(run_root, receipt, arm)
    finally:
        c13.stage._pair_stats = original
    reports = prefix["completed_prefix_state_reports"]
    if len(reports) != len(strict_by_state):
        raise ValueError("strict source checks do not align with completed state reports")

    selected = []
    violations = []
    by_stage_species = {}
    for row, strict in zip(reports, strict_by_state):
        step, rk, label = row["timestep"], row["rkstep"], row["stage"]
        if not ((label == "RK_STAGE_END" and rk == 3)
                or (label in ("PRE_KDM6", "POST_KDM6") and rk == 0)):
            continue
        selected_row = {"timestep": step, "rk": rk, "stage": label,
                        "violations": strict["violations"]}
        selected.append(selected_row)
        if strict["violations"]:
            violations.append(selected_row)
        for species, check in strict["checks"].items():
            aggregate = by_stage_species.setdefault(label, {}).setdefault(species, {})
            for key, value in check["counts"].items():
                aggregate[key] = aggregate.get(key, 0) + int(value)
    expected_steps = set(range(1, EXPECTED_FINAL_STEP + 1))
    selected_keys = {(row["timestep"], row["rk"], row["stage"]) for row in selected}
    required = ({(step, 3, "RK_STAGE_END") for step in expected_steps}
                | {(step, 0, stage) for step in expected_steps
                   for stage in ("PRE_KDM6", "POST_KDM6")})
    coverage_ok = (set(prefix["completed_prefix_coverage"]) == {str(x) for x in expected_steps}
                   and all(value["pass"] for value in prefix["completed_prefix_coverage"].values())
                   and selected_keys == required)
    prefix["strict_source_boundaries"] = {
        "contract": "exact cloud/rain mass-ratio plus dual REAL64/REAL32 volume bounds; exact stored graupel QG/BG [100,900]; no ULP allowance",
        "stages": selected,
        "stage_species_aggregate_counts": by_stage_species,
        "violations": violations,
        "coverage_expected_steps": EXPECTED_FINAL_STEP,
        "coverage_selected_stage_records": len(selected),
        "coverage_all_12_steps_x_3_boundaries": coverage_ok,
        "status": "PASS" if coverage_ok and not violations else "FAIL",
    }
    return prefix


def audit_arm(arm: str) -> dict:
    low = arm.lower()
    run_root = Path(f"/var/tmp/pr91_{arm}_240s_c14_20261020")
    rec = json.loads((HERE / f"{low}_receipt.json").read_text())
    identity = verify_identity(arm)
    prefix = parse_c14_prefix(run_root, rec, arm)
    transport = c13.read_ledger(run_root)
    failures = read_actual_store_failures(run_root, rec)
    store = read_c14_storage_ledger(run_root, rec)
    per_step_records = {}
    for item in prefix["trace"]["records"]:
        per_step_records.setdefault(str(item["step"]), []).append(item["stage"])
    prefix["all_records_by_timestep"] = per_step_records
    return {
        "identity": identity,
        "completed_prefix": prefix,
        "joint_transport": transport,
        "failure_diagnostics": failures,
        "c14_storage_ledger": store,
    }


def main() -> None:
    arms = {arm: audit_arm(arm) for arm in ("OFF", "COUPLED")}
    passed = all(
        arm["identity"]["all_checks_pass"]
        and arm["completed_prefix"]["strict_state_status"] == "PASS"
        and arm["completed_prefix"]["strict_source_boundaries"]["status"] == "PASS"
        and arm["identity"]["final_completed_step"] == EXPECTED_FINAL_STEP
        and len(arm["joint_transport"]["joint_rk_rows"]) == 3 * EXPECTED_FINAL_STEP
        and arm["joint_transport"]["all_joint_theta_equal_one"]
        and arm["joint_transport"]["all_joint_rows_feasible"]
        for arm in arms.values()
    )
    result = {
        "schema": "pr91_c14_closed_runtime_audit_v1",
        "overall_status": "PASS_240_PREFIX" if passed else "FAIL_OR_INCOMPLETE_240_PREFIX",
        "identity_scope": {"build_receipt_sha256": EXPECTED_BUILD_SHA256,
                           "executable_sha256": EXPECTED_EXE_SHA256},
        "arms": arms,
    }
    output = HERE / "closed_runtime_audit.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({arm: {
        "identity": data["identity"]["all_checks_pass"],
        "status": data["identity"]["run_status"],
        "completed_step": data["identity"]["final_completed_step"],
        "strict_state": data["completed_prefix"]["strict_state_status"],
        "strict_source": data["completed_prefix"]["strict_source_boundaries"]["status"],
        "strict_boundary_records": data["completed_prefix"]["strict_source_boundaries"]["coverage_selected_stage_records"],
        "joint_rows": len(data["joint_transport"]["joint_rk_rows"]),
        "theta1": data["joint_transport"]["all_joint_theta_equal_one"],
        "joint_feasible": data["joint_transport"]["all_joint_rows_feasible"],
        "inactive_q_quantum_adjustments_by_pair": data["c14_storage_ledger"]["inactive_q_quantum_adjustment_count_by_pair"],
    } for arm, data in arms.items()}, indent=2))


if __name__ == "__main__":
    main()
