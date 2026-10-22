#!/usr/bin/env python3
"""Reduce per-column compact process and approved-packet accounts with mapped area."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import netCDF4
import numpy as np

from native_kdm6_trace import read_dump
from pr95_call_budget import _read_map_geometry
from pr97_t1_rounding import read_columns
from pr98_budget import WATER, cutoff_columns, same_call_bottom
from pr98_budget_faces import compact_face_rows

STAGES = {1: "melt", 2: "freezing", 3: "cold", 4: "warm", 5: "ice_transition", 6: "rain_freezing"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reduce_compact(path: Path, bounds: dict, area: np.ndarray) -> dict:
    shape = area.shape
    signed = {name: np.zeros(shape) for name in STAGES.values()}
    l1 = {name: np.zeros(shape) for name in STAGES.values()}
    maximum = {name: np.zeros(shape) for name in STAGES.values()}
    counts = {name: np.zeros(shape, dtype=np.int64) for name in STAGES.values()}
    packet_signed = {name: np.zeros(shape) for name in STAGES.values()}
    packet_l1 = {name: np.zeros(shape) for name in STAGES.values()}
    packet_max = {name: np.zeros(shape) for name in STAGES.values()}
    packet_counts = {name: np.zeros(shape, dtype=np.int64) for name in STAGES.values()}
    seen: set[tuple[int, int, int]] = set()
    with path.open(encoding="ascii") as stream:
        for line in stream:
            fields = line.split()
            if not fields:
                continue
            if fields[0] != "PR99_STAGE_COLUMN" or len(fields) != 12:
                raise ValueError("malformed compact stage row")
            i, j, stage, count, packet_count = map(int, fields[1:6])
            if stage not in STAGES:
                raise ValueError(f"unknown compact stage id {stage}")
            if not (bounds["its"] <= i <= bounds["ite"] and
                    bounds["jts"] <= j <= bounds["jte"]):
                raise ValueError("compact stage coordinate outside active tile")
            key = (i, j, stage)
            if key in seen:
                raise ValueError("duplicate compact stage coordinate")
            seen.add(key)
            row, col = j - bounds["jts"], i - bounds["its"]
            weight = float(area[row, col])
            name = STAGES[stage]
            signed[name][row, col] = float(fields[6]) * weight
            l1[name][row, col] = float(fields[7]) * weight
            maximum[name][row, col] = float(fields[8]) * weight
            counts[name][row, col] = count
            packet_signed[name][row, col] = float(fields[9]) * weight
            packet_l1[name][row, col] = float(fields[10]) * weight
            packet_max[name][row, col] = float(fields[11]) * weight
            packet_counts[name][row, col] = packet_count
    expected = area.size * len(STAGES)
    if len(seen) != expected:
        raise ValueError(f"compact stage coverage {len(seen)} != {expected}")

    def summary(values: np.ndarray, abs_values: np.ndarray, max_values: np.ndarray,
                event_counts: np.ndarray) -> dict:
        return {
            "signed_kg": math.fsum(values.flat),
            "L1_event_kg": math.fsum(abs_values.flat),
            "max_abs_event_kg": float(np.max(max_values)),
            "max_abs_column_kg": float(np.max(np.abs(values))),
            "columns_with_events": int(np.count_nonzero(event_counts)),
            "event_count": int(np.sum(event_counts)),
        }

    stages = {}
    packet = {}
    combined = np.zeros(shape)
    combined_abs = np.zeros(shape)
    combined_max = np.zeros(shape)
    combined_counts = np.zeros(shape, dtype=np.int64)
    packet_total = np.zeros(shape)
    packet_abs = np.zeros(shape)
    packet_maximum = np.zeros(shape)
    packet_total_counts = np.zeros(shape, dtype=np.int64)
    for name in STAGES.values():
        stages[name] = summary(signed[name], l1[name], maximum[name], counts[name])
        packet[name] = summary(packet_signed[name], packet_l1[name], packet_max[name], packet_counts[name])
        combined += signed[name]
        combined_abs += l1[name]
        combined_max = np.maximum(combined_max, maximum[name])
        combined_counts += counts[name]
        packet_total += packet_signed[name]
        packet_abs += packet_l1[name]
        packet_maximum = np.maximum(packet_maximum, packet_max[name])
        packet_total_counts += packet_counts[name]
    return {
        "stage_rows": len(seen), "expected_stage_rows": expected,
        "process_stages": stages,
        "combined_process_store_discrepancy": summary(combined, combined_abs, combined_max, combined_counts),
        "approved_packet_water": packet,
        "combined_approved_packet_water": summary(packet_total, packet_abs, packet_maximum, packet_total_counts),
        "stage_column_arrays": signed,
        "packet_column_arrays": packet_signed,
        "stage_count_arrays": counts,
        "packet_count_arrays": packet_counts,
    }


def analyze(arm: str, run: Path, native: Path, history: Path, manifest_path: Path,
            face_report_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text())
    if (manifest.get("arm") != arm or manifest.get("returncode") != 0 or
            manifest.get("completion_marker_observed") is not True or
            manifest.get("all_17_fields_and_XLAND_byte_equal") is not True):
        raise ValueError("compact replay lacks successful completion or 17-field/XLAND identity")
    pre_path, post_path = native / "kdm6_first_call_pre.raw", native / "kdm6_first_call_post.raw"
    if sha256(pre_path) != manifest["pre_sha256"] or sha256(post_path) != manifest["native_post_sha256"]:
        raise ValueError("compact replay states differ from native first-call states")
    compact = run / "pr99_process_stage_compact.raw"
    if sha256(compact) != manifest["stage_file_sha256"][compact.name]:
        raise ValueError("compact stage file differs from replay receipt")
    pre = read_dump(pre_path)
    b = pre["bounds"]
    with netCDF4.Dataset(history) as dataset:
        dataset.set_auto_mask(False)
        area, _, _ = _read_map_geometry(dataset, slice(b["jts"]-1,b["jte"]),
                                        slice(b["its"]-1,b["ite"]))
    stages = reduce_compact(compact, b, area)
    stage_arrays = stages.pop("stage_column_arrays")
    packet_arrays = stages.pop("packet_column_arrays")
    stage_counts = stages.pop("stage_count_arrays")
    packet_counts = stages.pop("packet_count_arrays")
    face = json.loads(face_report_path.read_text())
    if face.get("arm") != arm or face.get("identity", {}).get("history_sha256") != sha256(history):
        raise ValueError("compact account face baseline differs in arm or map geometry")
    baseline = face["compact_full_tile_face_capture"]["open_residual_after_independent_face_term"]
    stages["baseline_after_liquid_cutoff_face"] = baseline
    process = run / "pr67_kdm6_process.raw"
    bottom = same_call_bottom(process, pre, area)
    density = pre["fields"]["DEN"].astype(np.float64)
    thickness = pre["fields"]["DELZ"].astype(np.float64)
    post = read_dump(post_path)
    water_delta = np.zeros_like(density * thickness * area[:, None, :])
    for field in WATER:
        water_delta += (post["fields"][field].astype(np.float64) -
                        pre["fields"][field].astype(np.float64)) * density * thickness * area[:, None, :]
    raw = np.sum(water_delta, axis=1, dtype=np.float64) + bottom
    cutoff, _, _, _ = cutoff_columns(run / "pr85_kdm6_cutoff_budget.raw", b,
                                     density, thickness, area)
    _, liquid_values = read_columns(run / "pr97_liquid_columns.raw", b)
    rain, _, _ = compact_face_rows(run / "pr87_rain_sedimentation_budget.raw",
        run / "pr87_rain_sedimentation_budget.raw", "PR98_SED_FACE_SUM", 3, b, area)
    ice, _, _ = compact_face_rows(run / "pr85_ice_sedimentation_budget.raw",
        run / "pr85_ice_sedimentation_budget.raw", "PR98_SED_FACE_SUM", 1, b, area)
    calculated_baseline = raw - (liquid_values[:, :, 0] + liquid_values[:, :, 1]) * area - cutoff - rain - ice
    for metric, calculated in (("signed_kg", math.fsum(calculated_baseline.flat)),
                               ("L1_column_kg", math.fsum(np.abs(calculated_baseline).flat)),
                               ("max_abs_column_kg", float(np.max(np.abs(calculated_baseline))))):
        if abs(calculated - baseline[metric]) > 1.0e-7 * max(1.0, abs(baseline[metric])):
            raise ValueError(f"reconstructed full-tile baseline {metric} differs from face receipt")
    combined_stages = np.zeros_like(calculated_baseline)
    combined_packets = np.zeros_like(calculated_baseline)
    for name in STAGES.values():
        combined_stages += stage_arrays[name]
        combined_packets += packet_arrays[name]
    remaining_store = calculated_baseline - combined_stages
    remaining_packet = remaining_store - combined_packets

    def final_summary(values: np.ndarray) -> dict:
        positive = np.unravel_index(int(np.argmax(values)), values.shape)
        negative = np.unravel_index(int(np.argmin(values)), values.shape)
        def column_detail(point: tuple[int, int]) -> dict:
            row, col = point
            return {
                "i": int(col+b["its"]), "j": int(row+b["jts"]), "kg": float(values[point]),
                "baseline_after_liquid_cutoff_face_kg": float(calculated_baseline[point]),
                "process_stages": {name: {
                    "stored_minus_approved_kg": float(stage_arrays[name][point]),
                    "event_count": int(stage_counts[name][point]),
                } for name in STAGES.values()},
                "approved_packet_water": {name: {
                    "approved_sum_kg": float(packet_arrays[name][point]),
                    "event_count": int(packet_counts[name][point]),
                } for name in STAGES.values()},
            }
        return {
            "signed_kg": math.fsum(values.flat),
            "L1_column_kg": math.fsum(np.abs(values).flat),
            "max_abs_column_kg": float(np.max(np.abs(values))),
            "largest_positive": column_detail(positive),
            "most_negative": column_detail(negative),
        }
    stages["remaining_after_process_store_discrepancies"] = final_summary(remaining_store)
    stages["remaining_after_store_and_approved_packet"] = final_summary(remaining_packet)
    stages["remaining_after_process_store_discrepancies_signed_kg"] = (
        baseline["signed_kg"] - stages["combined_process_store_discrepancy"]["signed_kg"])
    stages["remaining_after_store_and_approved_packet_signed_kg"] = (
        stages["remaining_after_process_store_discrepancies_signed_kg"] -
        stages["combined_approved_packet_water"]["signed_kg"])
    stages["measure"] = "source-ordered actual stored-minus-approved stage terms and approved packet water; per-column R64 Kahan, actual area applied once"
    stages["all_17_fields_and_XLAND_byte_equal"] = True
    stages["source_sha256"] = manifest["prepared_source_sha256"]
    stages["executable_sha256"] = manifest["executable_sha256"]
    stages["manifest_sha256"] = sha256(manifest_path)
    stages["face_report_sha256"] = sha256(face_report_path)
    stages["history_sha256"] = sha256(history)
    return stages


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", choices=("OFF", "HYDRO", "COUPLED"), required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--native", type=Path, required=True)
    parser.add_argument("--history", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--face-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.arm,args.run,args.native,args.history,args.manifest,args.face_report)
    args.output.write_text(json.dumps(result,indent=2)+"\n")
    print(args.arm,json.dumps({key:result[key] for key in (
        "remaining_after_process_store_discrepancies_signed_kg",
        "remaining_after_store_and_approved_packet_signed_kg")},sort_keys=True))


if __name__ == "__main__":
    main()
