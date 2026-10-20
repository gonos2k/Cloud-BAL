#!/usr/bin/env python3
"""Reuse the existing receipt/source/area join for closed PR93 cold ledgers."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tools"))
from pr90_cold_column_summary import area_weighted_totals


def reduce(run_root: Path) -> dict:
    receipt_path = run_root / "receipt.json"
    receipt = json.loads(receipt_path.read_text())
    if receipt.get("status") not in {"COMPLETE", "INCOMPLETE"} or receipt.get("processing_errors"):
        raise ValueError("a collector-closed receipt without processing errors is required")
    stage = run_root / "run"
    histories = sorted(stage.glob("wrfout_d01_*"))
    if len(histories) != 1:
        raise ValueError("this frozen profile requires one multi-record history file")
    result = area_weighted_totals(
        stage / "pr90_kdm6_cold_column.raw.gz", run_receipt_path=receipt_path,
        history_path=histories[0], stage_record_path=stage / "pr85_joint_moment_stages.raw.gz")
    complete = receipt["final_completed_step"]
    expected = set(range(1, complete + 1))
    actual = {int(step) for step in result["by_timestep"] if int(step) <= complete}
    if actual != expected:
        raise ValueError("cold activity does not cover the completed prefix")
    for step in expected:
        coverage = result["coverage_by_timestep"][step]
        if coverage["status"] != "FULL" or coverage["observed_columns"] != coverage["expected_columns"]:
            raise ValueError(f"incomplete column coverage at timestep {step}")
    totals = {}
    for group in ("NG", "AUT", "G"):
        totals[group] = {}
        for end in sorted({min(23, complete), complete}):
            amounts = {kind: sum(result["by_timestep"][step][group][kind]["half_l1_kg"]
                                 for step in range(1, end + 1))
                       for kind in ("proposed", "applied", "deferred")}
            amounts["deferred_over_proposed"] = (
                amounts["deferred"] / amounts["proposed"] if amounts["proposed"] else None)
            totals[group][f"steps_1_to_{end}"] = amounts
    return {**result, "completed_prefix_totals": totals,
            "physical_approval": "FAIL_OPEN",
            "interpretation": "Area-weighted group half-L1 activity, not reaction throughput, precipitation suppression or water/energy closure. The common 23-step window is separate from the full completed window."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = reduce(args.run_root)
    result["reducer_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    helper = ROOT / "tools/pr90_cold_column_summary.py"
    result["existing_area_join_sha256"] = hashlib.sha256(helper.read_bytes()).hexdigest()
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
