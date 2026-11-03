#!/usr/bin/env python3
"""Derive per-level time-integrated CP02 PREVP component diagnostics."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import struct
import sys
from collections import defaultdict
from pathlib import Path


TRACE_KEY_FIELDS = ("rank", "call_id", "itimestep", "loop", "j", "i", "k")
OUTPUT_FIELDS = (
    "arm", "point_id", "diagnostic_group", "corner", "weight", "k", "hour", "cell_step_count",
    "qrain_branch_count", "raw_positive_count", "raw_negative_count", "raw_positive_zero_count",
    "raw_negative_zero_count", "qr_cap_count", "sat_cap_count", "zero_raw_count",
    "zero_raw_positive_count", "zero_raw_negative_count", "zero_raw_positive_zero_count",
    "zero_raw_negative_zero_count", "zero_raw_sat_cap_present_count", "zero_raw_sat_cap_absent_count",
    "zero_raw_sat_cap_negative_count",
    "zero_raw_final_negative_count", "zero_raw_final_positive_count",
    "zero_raw_final_negative_zero_count", "zero_raw_final_positive_zero_count",
    "integrated_prevp_rate_dt", "delta_qv_prevp", "delta_qr_prevp", "delta_t_prevp",
    "delta_t_latent_total", "delta_qv_state", "delta_qr_state", "delta_t_state",
    "max_abs_q_residual", "max_abs_t_residual",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha256_and_size(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def read_corner_metadata(path: Path) -> dict[tuple[str, str], dict]:
    result = {}
    with path.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            key = (row["point_id"], row["corner"])
            require(key not in result, f"duplicate frozen corner metadata: {key}")
            result[key] = {
                "diagnostic_group": row["diagnostic_group"],
                "weight": float(row["weight"]),
            }
    require(result, f"{path}: no corner metadata")
    return result


def verify_run_inputs(analysis_dir: Path, receipt_path: Path, receipt: dict) -> dict[str, Path]:
    require(receipt.get("status") == "PASS_BOTH_ARMS", f"{receipt_path}: analyzer receipt is not PASS_BOTH_ARMS")
    pinned = {Path(entry["path"]).name: entry for entry in receipt["analysis_outputs"]}
    paths = {}
    for arm in ("OLD", "FIX"):
        prefix = arm.lower()
        for suffix in ("cell_steps.csv", "phase_records.csv"):
            name = f"{prefix}_{suffix}"
            path = analysis_dir / arm / name
            require(name in pinned, f"{receipt_path}: missing output pin {name}")
            actual_hash, actual_size = sha256_and_size(path)
            expected = pinned[name]
            require(actual_hash == expected["sha256"] and actual_size == expected["bytes"],
                    f"{path}: differs from analyzer run receipt")
            paths[f"{arm}_{suffix[:-4]}"] = path
    return paths


def read_latent_inputs(path: Path) -> tuple[dict, dict[str, int], int]:
    latent = {}
    source_ordinals = defaultdict(set)
    phase_count = 0
    with path.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            if row["phase"] != "LATENT_INPUT":
                continue
            phase_count += 1
            key = tuple(int(value) for value in json.loads(row["key_json"]))
            require(len(key) == 7, f"{path}:{row['line_number']}: LATENT_INPUT key length is not seven")
            source = row["source"]
            ordinal = int(row["file_ordinal"])
            values = json.loads(row["values_json"])
            for name in ("xl", "cpm", "dtcld", "xlwork2"):
                value = float(values[name])
                require(math.isfinite(value), f"{path}:{row['line_number']}: non-finite LATENT_INPUT.{name}")
                values[name] = value
            identity = (source, ordinal, *key)
            require(identity not in latent, f"{path}:{row['line_number']}: duplicate LATENT_INPUT key {identity}")
            latent[identity] = values
            source_ordinals[source].add(ordinal)
    require(phase_count > 0, f"{path}: no LATENT_INPUT records")
    require(all(len(ordinals) == 1 for ordinals in source_ordinals.values()),
            f"{path}: a source path has multiple file ordinals")
    source_to_ordinal = {source: next(iter(ordinals)) for source, ordinals in source_ordinals.items()}
    return latent, source_to_ordinal, phase_count


def raw_sign(value: float, word_hex: str) -> str:
    if value > 0:
        return "positive"
    if value < 0:
        return "negative"
    sign_bit = int.from_bytes(bytes.fromhex(word_hex), "little") & 0x80000000
    return "negative_zero" if sign_bit else "positive_zero"


def final_sign(value: float) -> str:
    if value > 0:
        return "positive"
    if value < 0:
        return "negative"
    return "negative_zero" if math.copysign(1.0, value) < 0 else "positive_zero"


def empty_group() -> dict[str, float | int]:
    fields = OUTPUT_FIELDS[7:]
    return {name: 0 for name in fields if name.endswith("_count") or name in (
        "cell_step_count", "qrain_branch_count") } | {
            name: 0.0 for name in fields if name not in (
                "cell_step_count", "qrain_branch_count") and not name.endswith("_count")
        }


def add_step(group: dict, cell: dict, latent: dict, raw_present: bool) -> None:
    prevp = float(cell["prevp"])
    dtcld = float(cell["dtcld"])
    cpm = float(cell["cpm"])
    xl = latent["xl"]
    require(dtcld == latent["dtcld"] and cpm == latent["cpm"],
            "cell_steps dtcld/cpm differ from the key-matched LATENT_INPUT")
    group["cell_step_count"] += 1

    prevp_dt = f32(prevp * dtcld)
    group["integrated_prevp_rate_dt"] += prevp_dt
    group["delta_qv_prevp"] += f32(-prevp_dt)
    group["delta_qr_prevp"] += prevp_dt
    # Isolated PREVP term from xlwork2=-xl*prevp-...; report it as a
    # source-term component, not exact nonlinear attribution of full T change.
    xl_component = f32(f32(-xl) * prevp)
    temp_component = f32(-f32(f32(xl_component / cpm) * dtcld))
    group["delta_t_prevp"] += temp_component
    group["delta_t_latent_total"] += f32(-f32(f32(float(cell["xlwork2"]) / cpm) * dtcld))
    group["delta_qv_state"] += f32(float(cell["q_post"]) - float(cell["q_pre"]))
    group["delta_qr_state"] += f32(float(cell["qr_post"]) - float(cell["qr_pre"]))
    group["delta_t_state"] += f32(float(cell["t_post"]) - float(cell["t_pre"]))
    group["max_abs_q_residual"] = max(group["max_abs_q_residual"], abs(float(cell["q_residual"])))
    group["max_abs_t_residual"] = max(group["max_abs_t_residual"], abs(float(cell["t_residual"])))

    if not raw_present:
        return
    group["qrain_branch_count"] += 1
    raw = float(cell["raw_prev"])
    sign = raw_sign(raw, cell["raw_prev_word_hex"])
    group[f"raw_{sign}_count"] += 1
    if cell["qr_cap_prev"] != "":
        group["qr_cap_count"] += 1
    if cell["sat_cap_prev"] != "":
        group["sat_cap_count"] += 1
    if raw != 0.0:
        return
    group["zero_raw_count"] += 1
    group[f"zero_raw_{sign}_count"] += 1
    if cell["sat_cap_prev"] == "":
        group["zero_raw_sat_cap_absent_count"] += 1
    else:
        group["zero_raw_sat_cap_present_count"] += 1
        if float(cell["sat_cap_prev"]) < 0:
            group["zero_raw_sat_cap_negative_count"] += 1
    group[f"zero_raw_final_{final_sign(prevp)}_count"] += 1


def derive_arm(arm: str, cell_path: Path, phase_path: Path,
               corner_metadata: dict[tuple[str, str], dict]) -> tuple[dict, int]:
    latent, source_to_ordinal, latent_count = read_latent_inputs(phase_path)
    used_latent = set()
    seen_cells = set()
    groups = defaultdict(empty_group)
    with cell_path.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            corner_key = (row["point_id"], row["corner"])
            require(corner_key in corner_metadata, f"{cell_path}: cell has no frozen point/corner mapping {corner_key}")
            meta = corner_metadata[corner_key]
            require(abs(float(row["weight"]) - meta["weight"]) <= 1e-14,
                    f"{cell_path}: corner weight differs from frozen mapping {corner_key}")
            source = row["source_file"]
            require(source in source_to_ordinal, f"{cell_path}: source file absent from phase trace {source}")
            key = tuple(int(row[name]) for name in TRACE_KEY_FIELDS)
            latent_key = (source, source_to_ordinal[source], *key)
            require(latent_key in latent, f"{cell_path}: missing key-matched LATENT_INPUT {latent_key}")
            cell_key = (*corner_key, source, *key)
            require(cell_key not in seen_cells, f"{cell_path}: duplicate cell-step identity {cell_key}")
            seen_cells.add(cell_key)
            used_latent.add(latent_key)
            group_key = (arm, row["point_id"], meta["diagnostic_group"], row["corner"],
                         float(row["weight"]), int(row["k"]), int(row["hour"]))
            raw_present = row["raw_prev"] != ""
            if raw_present:
                require(row["raw_prev_word_hex"] != "", f"{cell_path}: raw PREVP value has no exact word")
            add_step(groups[group_key], row, latent[latent_key], raw_present)
    require(used_latent == set(latent),
            f"{arm}: cell_steps/LATENT_INPUT key inventory differs; unused latent={len(set(latent)-used_latent)}")
    return groups, latent_count


def derive(analysis_dir: Path, run_receipt_path: Path, corners_path: Path,
           output_path: Path, receipt_output: Path) -> dict:
    run_bytes = run_receipt_path.read_bytes()
    run_receipt = json.loads(run_bytes.decode("utf-8"))
    paths = verify_run_inputs(analysis_dir, run_receipt_path, run_receipt)
    corner_metadata = read_corner_metadata(corners_path)
    arm_groups = {}
    phase_counts = {}
    for arm in ("OLD", "FIX"):
        group_rows, latent_count = derive_arm(
            arm, paths[f"{arm}_cell_steps"], paths[f"{arm}_phase_records"], corner_metadata)
        arm_groups.update(group_rows)
        phase_counts[arm] = latent_count

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        for key, values in sorted(arm_groups.items()):
            arm, point_id, diagnostic_group, corner, weight, k, hour = key
            writer.writerow({"arm": arm, "point_id": point_id, "diagnostic_group": diagnostic_group,
                             "corner": corner, "weight": weight, "k": k, "hour": hour, **values})

    out_hash, out_size = sha256_and_size(output_path)
    expected_pins = {Path(entry["path"]).name: entry for entry in run_receipt["analysis_outputs"]}
    receipt = {
        "status": "PASS_KEYED_LATENT_COMPONENT_DERIVATION",
        "run_receipt_path": str(run_receipt_path),
        "run_receipt_sha256": hashlib.sha256(run_bytes).hexdigest(),
        "run1_status": run_receipt["status"],
        "analysis_inputs": {name: {"path": str(path),
                                   "sha256": expected_pins[path.name]["sha256"],
                                   "bytes": expected_pins[path.name]["bytes"]}
                            for name, path in paths.items()},
        "corners_path": str(corners_path),
        "corners_sha256": sha256_and_size(corners_path)[0],
        "derive_tool_sha256": sha256_and_size(Path(__file__))[0],
        "latent_input_record_counts": phase_counts,
        "output_path": str(output_path),
        "output_sha256": out_hash,
        "output_bytes": out_size,
        "groups": len(arm_groups),
        "scope": "per-arm, point, bilinear corner, model level k, and hour; summed over time only; no vertical, area, or pooled budget",
        "term_definitions": {
            "delta_qv_prevp": "sum(REAL32(-prevp*dtcld))",
            "delta_qr_prevp": "sum(REAL32(prevp*dtcld)); paired vapor/rain terms cancel by construction",
            "delta_t_prevp": "termwise REAL32 contribution from -xl*prevp in xlwork2; diagnostic component, not exact nonlinear attribution",
            "delta_t_latent_total": "sum(REAL32(-REAL32(REAL32(xlwork2/cpm)*dtcld))) from full LATENT_INPUT",
            "delta_qv_state/delta_qr_state/delta_t_state": "sum of observed POST_STEP minus PRE_UPDATE state over steps; local process-update state deltas, not whole KDM6 return",
        },
    }
    receipt_output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis-dir", type=Path, required=True)
    parser.add_argument("--run-receipt", type=Path, required=True)
    parser.add_argument("--corners", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = derive(args.analysis_dir, args.run_receipt, args.corners, args.out, args.receipt)
    except (OSError, UnicodeError, ValueError, KeyError, csv.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
