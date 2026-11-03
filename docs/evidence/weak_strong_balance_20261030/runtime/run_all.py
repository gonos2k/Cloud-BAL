#!/usr/bin/env python3
"""Launch up to eight eight-rank jobs across fixed, disjoint CPU slots."""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


HERE = Path(__file__).resolve().parent
PLAN_PATH = HERE / "common_plan.json"
CASE_RUNNER = HERE / "run_case.py"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run_slot(slot: int, cases: list[str]) -> dict:
    results = []
    for case in cases:
        evidence = HERE / "cases" / case
        evidence.mkdir(parents=True, exist_ok=True)
        stdout = evidence / "runner_stdout.txt"
        command = [sys.executable, str(CASE_RUNNER), case]
        with stdout.open("xb") as stream:
            result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=False)
        receipt_path = evidence / "receipt.json"
        receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else None
        results.append({
            "case": case,
            "slot": slot,
            "runner_exit": result.returncode,
            "receipt_status": receipt["status"] if receipt else "MISSING",
            "receipt_path": str(receipt_path),
            "runner_stdout": str(stdout),
        })
    return {"slot": slot, "cases": results}


def main() -> int:
    plan_bytes = PLAN_PATH.read_bytes()
    plan = json.loads(plan_bytes)
    assert plan["status"] == "PASS_READY_TO_LAUNCH"
    assert hashlib.sha256(PLAN_PATH.read_bytes()).hexdigest() == hashlib.sha256(plan_bytes).hexdigest()
    launch_scripts = json.loads((HERE / "launch_scripts.sha256.json").read_text())
    assert all(sha256(HERE / name) == digest for name, digest in launch_scripts.items())
    assert len(plan["case_records"]) == 8 and len(plan["cpu_affinity"]["slots"]) == 8
    start_utc = datetime.now(timezone.utc).isoformat()
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            pool.submit(run_slot, int(slot), cases): int(slot)
            for slot, cases in plan["cpu_affinity"]["slot_cases"].items()
        }
        slots = []
        for future in concurrent.futures.as_completed(futures):
            slots.append(future.result())
    plan_unchanged = sha256(PLAN_PATH) == hashlib.sha256(plan_bytes).hexdigest()
    end_utc = datetime.now(timezone.utc).isoformat()
    all_cases = [item for slot in slots for item in slot["cases"]]
    expected = set(plan["case_records"])
    found = {item["case"] for item in all_cases}
    status = "SUCCESS" if (
        found == expected and plan_unchanged
        and all(item["runner_exit"] == 0 and item["receipt_status"] == "SUCCESS" for item in all_cases)
    ) else "INCOMPLETE"
    batch = {
        "status": status,
        "start_utc": start_utc,
        "end_utc": end_utc,
        "case_count": len(all_cases),
        "max_concurrent_cases": 8,
        "common_plan_sha256": hashlib.sha256(plan_bytes).hexdigest(),
        "selection_plan_sha256": plan["selection_plan_sha256"],
        "common_plan_unchanged_after_batch": plan_unchanged,
        "slots": sorted(slots, key=lambda row: row["slot"]),
    }
    path = HERE / "batch_receipt.json"
    path.write_text(json.dumps(batch, indent=2) + "\n")
    print(json.dumps({"status": status, "case_count": len(all_cases),
                      "receipt": str(path), "common_plan_sha256": batch["common_plan_sha256"]}, indent=2))
    return 0 if status == "SUCCESS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
