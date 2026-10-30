#!/usr/bin/env python3
"""Validate eight raw case receipts and bind their output histories."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import netCDF4
import numpy as np


HERE = Path(__file__).resolve().parent
PLAN_PATH = HERE / "common_plan.json"
EXPECTED_HOURS = [f"wrfout_d01_2026-08-16_{hour:02d}:00:00" for hour in range(12, 19)]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    plan_bytes = PLAN_PATH.read_bytes()
    plan = json.loads(plan_bytes)
    plan_sha = hashlib.sha256(plan_bytes).hexdigest()
    selection_path = HERE.parent / "selection_plan.json"
    selection_sha = sha256(selection_path)
    assert selection_sha == plan["selection_plan_sha256"]
    batch_path = HERE / "batch_receipt.json"
    batch = json.loads(batch_path.read_text())
    assert batch["common_plan_sha256"] == plan_sha
    case_results = {}
    history_validation = {}
    for case_id, case in plan["case_records"].items():
        evidence = HERE / "cases" / case_id
        receipt_path = evidence / "receipt.json"
        receipt = json.loads(receipt_path.read_text())
        scratch = Path(case["scratch_directory"])
        assert receipt["case"] == case_id and receipt["alpha"] == case["alpha"]
        assert receipt["common_plan_sha256"] == plan_sha
        assert receipt["selection_plan_sha256"] == selection_sha
        assert receipt["status"] == "SUCCESS" and receipt["exit"] == 0 and receipt["success_marker"]
        assert receipt["histories"] == EXPECTED_HOURS and receipt["histories_exact"]
        assert receipt["staged_inputs_unchanged"] and receipt["source_unchanged"]
        assert receipt["common_plan_unchanged_after_run"]
        assert not receipt["affinity_outside_assigned_set"]
        assert receipt["cpu_set"] == case["cpu_set"] and receipt["cpu_slot"] == case["slot"]
        staged_actual = {name: sha256(scratch / name) for name in case["staged_sha256"]}
        assert staged_actual == case["staged_sha256"] == receipt["staged_sha256_after"]
        assert set(receipt["output_sha256"]) == set(EXPECTED_HOURS)
        time_rows = []
        for name in EXPECTED_HOURS:
            path = scratch / name
            digest = sha256(path)
            assert digest == receipt["output_sha256"][name]
            expected_time = name.removeprefix("wrfout_d01_")
            with netCDF4.Dataset(path) as dataset:
                times = netCDF4.chartostring(dataset["Times"][:]).tolist()
                assert times == [expected_time], (case_id, name, times)
                fields = {}
                for field in ("RAINC", "RAINNC", "RAINSH"):
                    values = dataset[field][:]
                    assert not np.ma.is_masked(values) and np.isfinite(values).all(), (case_id, name, field)
                    fields[field] = {"finite": True, "shape": list(values.shape)}
            time_rows.append({"file": name, "time": expected_time, "sha256": digest, "fields": fields})
        history_validation[case_id] = {"status": "PASS", "histories": time_rows}
        case_results[case_id] = {
            "status": receipt["status"],
            "group": receipt["group"],
            "alpha": receipt["alpha"],
            "elapsed_seconds": receipt["elapsed_seconds"],
            "cpu_slot": receipt["cpu_slot"],
            "cpu_set": receipt["cpu_set"],
            "staged_unchanged": receipt["staged_inputs_unchanged"],
            "source_unchanged": receipt["source_unchanged"],
            "history_count": len(receipt["output_sha256"]),
            "history_sha256": receipt["output_sha256"],
            "receipt_path": str(receipt_path),
            "receipt_sha256": sha256(receipt_path),
        }
    status = "SUCCESS" if batch["status"] == "SUCCESS" and len(case_results) == 8 else "INCOMPLETE"
    histories_path = HERE / "history_validation.json"
    histories_path.write_text(json.dumps({"status": status, "cases": history_validation}, indent=2) + "\n")
    result = {
        "status": status,
        "selection_plan_sha256": selection_sha,
        "common_plan_sha256": plan_sha,
        "batch_receipt_sha256": sha256(batch_path),
        "case_count": len(case_results),
        "cases": case_results,
        "history_validation_sha256": sha256(histories_path),
        "all_case_histories_validated": all(row["status"] == "PASS" for row in history_validation.values()),
    }
    final_path = HERE / "final_receipt.json"
    final_path.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": status, "case_count": len(case_results),
                      "selection_plan_sha256": selection_sha,
                      "common_plan_sha256": plan_sha,
                      "final_receipt": str(final_path)}, indent=2))
    return 0 if status == "SUCCESS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
