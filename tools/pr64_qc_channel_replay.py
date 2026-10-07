#!/usr/bin/env python3
"""Validate the PR64 native QC source-channel observer against the guarded baseline."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

from pr63_transition_replay import read_stage_text


MATCHED_OUTPUTS = (
    "wrfout_d01_2026-08-16_12:00:00",
    "namelist.output",
    "kdm6_first_call_pre.raw",
    "kdm6_first_call_post.raw",
    "pr62_extent_cells.txt",
    "pr61_cell_process.raw",
    "pr63_kdm_stages.raw",
    "pr63_transition_stages.raw",
    "pr63_geometry.raw",
    "candidate_run.log",
)
CHANNEL_COLUMNS = (
    "QCCHAN",
    "rkstep",
    "i",
    "j",
    "k",
    "bl_pbl",
    "cu",
    "shcu",
    "diff_opt",
    "km_opt",
    "qc_moist_tend",
    "rqcblten",
    "rqccuten",
    "rqcshten",
    "rqcncuten",
    "rqcnshten",
)
INTEGER_COLUMNS = CHANNEL_COLUMNS[1:10]
REAL_COLUMNS = CHANNEL_COLUMNS[10:]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_qc_channel(path: Path) -> dict[str, float | int]:
    lines = path.read_text().splitlines()
    if len(lines) < 2:
        raise ValueError(f"QC channel capture is empty: {path}")
    columns = lines[0].split()
    if tuple(columns) != CHANNEL_COLUMNS:
        raise ValueError("unexpected QC channel header or schema")
    rows = []
    for line in lines[1:]:
        values = line.split()
        if not values or values[0] != "QCCHAN" or len(values) != len(columns):
            raise ValueError("malformed QC channel record")
        try:
            row: dict[str, float | int] = {"QCCHAN": "QCCHAN"}
            row.update({key: int(values[index]) for index, key in enumerate(INTEGER_COLUMNS, 1)})
            row.update({key: float(values[index]) for index, key in enumerate(REAL_COLUMNS, 10)})
        except (ValueError, OverflowError) as exc:
            raise ValueError("QC channel record has an invalid numeric field") from exc
        if any(not math.isfinite(row[key]) for key in REAL_COLUMNS):
            raise ValueError("QC channel record contains a non-finite value")
        if (row["i"], row["j"], row["k"]) == (172, 76, 1):
            rows.append(row)
    if len(rows) != 1:
        raise ValueError(f"expected one target QC channel row, found {len(rows)}")
    return rows[0]


def target_stage_rows(path: Path) -> list[dict[str, object]]:
    return [row for row in read_stage_text(path) if row["stage"] in {"RK_STAGE_END", "POST_MICROPHYSICS"}]


def validate(observer: Path, baseline: Path) -> dict[str, object]:
    receipt_path = observer / "run-isolation.json"
    receipt = json.loads(receipt_path.read_text())
    if receipt["returncode"] != 0 or receipt["input_integrity"] != "PASS" or receipt["output_isolation"] != "PASS":
        raise ValueError("guarded observer run did not pass")
    if receipt["changed_inputs"] or receipt["input_read_issues"] or receipt["output_issues"]:
        raise ValueError("guarded observer receipt reports path integrity issues")

    outputs = {record["path"]: record["sha256"] for record in receipt["outputs"]}
    if len(outputs) != len(receipt["outputs"]):
        raise ValueError("guarded receipt contains duplicate output paths")
    channel_name = "pr64_qc_channels.raw"
    if channel_name not in outputs:
        raise ValueError("guarded receipt omits QC channel capture")
    channel_path = observer / channel_name
    if sha256(channel_path) != outputs[channel_name]:
        raise ValueError("QC channel capture hash differs from receipt")

    channel = read_qc_channel(channel_path)
    if channel["rkstep"] != 1 or (channel["bl_pbl"], channel["cu"], channel["shcu"]) != (11, 37, 0):
        raise ValueError("unexpected RK step or physics configuration")
    if channel["diff_opt"] != 1 or channel["km_opt"] != 4:
        raise ValueError("unexpected diffusion configuration")
    if channel["qc_moist_tend"] != channel["rqcblten"]:
        raise ValueError("QC moist tendency does not match PBL channel")
    if channel["qc_moist_tend"] <= 0.0 or channel["rqcblten"] <= 0.0:
        raise ValueError("captured PBL QC source is not positive")
    if any(channel[key] != 0.0 for key in ("rqccuten", "rqcshten", "rqcncuten", "rqcnshten")):
        raise ValueError("non-PBL QC/NC channel is nonzero at target")

    comparisons = {}
    for name in MATCHED_OUTPUTS:
        if name not in outputs:
            raise ValueError(f"guarded receipt omits required baseline artifact: {name}")
        observed_hash = sha256(observer / name)
        if observed_hash != outputs[name]:
            raise ValueError(f"observer artifact hash differs from receipt: {name}")
        baseline_hash = sha256(baseline / name)
        comparisons[name] = {"observer_sha256": observed_hash, "baseline_sha256": baseline_hash, "match": observed_hash == baseline_hash}
        if observed_hash != baseline_hash:
            raise ValueError(f"baseline artifact differs: {name}")

    observed_stages = target_stage_rows(observer / "pr63_transition_stages.raw")
    baseline_stages = target_stage_rows(baseline / "pr63_transition_stages.raw")
    if observed_stages != baseline_stages:
        raise ValueError("named selected-cell transition stages differ from baseline")
    return {
        "observer_receipt_sha256": sha256(receipt_path),
        "observer_qc_channel_sha256": outputs[channel_name],
        "declared_input_count": len(receipt["inputs"]),
        "declared_output_count": len(receipt["outputs"]),
        "qc_channel": channel,
        "matched_outputs": comparisons,
        "selected_cell_stages_match": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("observer_run", type=Path)
    parser.add_argument("baseline_run", type=Path)
    args = parser.parse_args()
    try:
        result = validate(args.observer_run, args.baseline_run)
    except (OSError, ValueError, KeyError, TypeError, IndexError, json.JSONDecodeError) as exc:
        print(f"pr64_qc_channel_replay: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
