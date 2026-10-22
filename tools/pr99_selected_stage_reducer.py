#!/usr/bin/env python3
"""Reduce selected C1 process-stage water-store discrepancies."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import netCDF4
from native_kdm6_trace import read_dump
from pr95_call_budget import HISTORY, _read_map_geometry

COORDINATES = ((192, 71), (161, 57))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stage_terms(path: Path, name: str, i: int, j: int,
                density: list[float], thickness: list[float], area: float, kts: int) -> tuple[list[float], int]:
    terms = []
    for line in path.read_text(errors="replace").splitlines():
        fields = line.split()
        if len(fields) < 4 or fields[0].startswith("#"):
            continue
        try:
            if int(fields[1]) != i or int(fields[2]) != j:
                continue
        except ValueError:
            continue
        k_index = int(fields[3]) - kts
        if not 0 <= k_index < len(density):
            raise ValueError(f"{name} event has out-of-range k={fields[3]}")
        layer_weight = density[k_index] * thickness[k_index] * area
        if name == "warm":
            residual = math.fsum(map(float, fields[-11:-6])) + float(fields[-1])
            scale = layer_weight
        elif name == "cold":
            residual = math.fsum(map(float, fields[-12:-7])) + float(fields[-1])
            scale = layer_weight
        elif name == "freezing":
            # Both PINU and PFRZ rows use one concatenated 3L1 token.
            # Field 24 is their stored-minus-approved total water residual.
            residual = float(fields[24])
            scale = thickness[k_index] * area
        elif name == "melt":
            numeric = list(map(float, fields[6:-1]))
            residual = numeric[8] + numeric[10] + numeric[4] - numeric[3]
            scale = layer_weight
        elif name == "rain_freezing":
            residual = -float(fields[28])
            scale = thickness[k_index] * area
        elif name == "ice_transition":
            residual = float(fields[14]) - float(fields[13])
            scale = layer_weight
        elif name == "ice_extinction":
            residual = float(fields[10]) - float(fields[8])
            scale = layer_weight
        else:
            raise ValueError(f"unknown stage: {name}")
        terms.append(residual * scale)
    return terms, len(terms)


def analyze(arm: str, run: Path, native: Path, history: Path,
            manifest_path: Path, face_report_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text())
    pre_path = native / "kdm6_first_call_pre.raw"
    post_path = native / "kdm6_first_call_post.raw"
    if (manifest.get("arm") != arm or manifest.get("returncode") != 0 or
            manifest.get("all_17_fields_and_XLAND_byte_equal") is not True or
            sha256(pre_path) != manifest.get("pre_sha256") or
            sha256(post_path) != manifest.get("native_post_sha256")):
        raise ValueError(f"{arm} replay manifest does not bind the receipt-native C1 states")
    for name, expected in manifest["stage_file_sha256"].items():
        if sha256(run / name) != expected:
            raise ValueError(f"{arm} stage file hash mismatch: {name}")
    pre = read_dump(pre_path)
    b = pre["bounds"]
    with netCDF4.Dataset(history) as dataset:
        dataset.set_auto_mask(False)
        area, _, _ = _read_map_geometry(dataset,
            slice(b["jts"] - 1, b["jte"]), slice(b["its"] - 1, b["ite"]))
    density = pre["fields"]["DEN"].astype(float)
    thickness = pre["fields"]["DELZ"].astype(float)
    face_report = json.loads(face_report_path.read_text())
    remaining_by_coordinate = {
        f"{i},{j}": value["remaining_after_cutoff_and_face_terms_kg"]
        for value in face_report["compact_full_tile_face_capture"][
            "extreme_remaining_columns_by_sign"].values()
        for i, j in ((value["i"], value["j"]),)
    }
    stages = {
        "melt": "pr85_kdm6_melt_budget.raw",
        "freezing": "pr85_kdm6_freezing_budget.raw",
        "rain_freezing": "pr85_rain_freezing_budget.raw",
        "cold": "pr85_kdm6_cold_budget.raw",
        "warm": "pr85_kdm6_warm_budget.raw",
        "ice_transition": "pr85_ice_transition_branch.raw",
        "ice_extinction": "pr87_ice_extinction.raw",
    }
    selected = {}
    for i, j in COORDINATES:
        row, col = j - b["jts"], i - b["its"]
        per_stage = {}
        for name, filename in stages.items():
            terms, count = stage_terms(run / filename, name, i, j,
                list(map(float, density[row, :, col])),
                list(map(float, thickness[row, :, col])),
                float(area[row, col]), b["kts"])
            per_stage[name] = {
                "events": count, "signed_store_discrepancy_kg": math.fsum(terms),
                "L1_event_discrepancy_kg": math.fsum(abs(value) for value in terms),
                "max_abs_event_discrepancy_kg": max(map(abs, terms), default=0.0),
            }
        observed_stage_error = math.fsum(
            values["signed_store_discrepancy_kg"] for values in per_stage.values())
        per_stage["combined_observed_process_stage_error_kg"] = observed_stage_error
        per_stage["residual_after_observed_process_stage_terms_kg"] = (
            remaining_by_coordinate[f"{i},{j}"] - observed_stage_error)
        selected[f"{i},{j}"] = per_stage
    return {
        "schema": "pr99_selected_process_stage_account_v1", "arm": arm,
        "coordinates": list(COORDINATES), "selected_columns": selected,
        "measure": "actual pre-state DEN × DELZ × receipt-bound history map area",
        "source_manifest_sha256": sha256(manifest_path),
        "face_report_sha256": sha256(face_report_path),
        "stage_reducer_source_sha256": sha256(Path(__file__).resolve()),
        "history_sha256": sha256(history),
        "pre_sha256": sha256(pre_path), "native_post_sha256": sha256(post_path),
        "replay_post_sha256": manifest["replay_post_sha256"],
        "all_17_fields_and_XLAND_byte_equal": True,
    }


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
    result = analyze(args.arm, args.run, args.native, args.history, args.manifest,
                     args.face_report)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    for coordinate, stages in result["selected_columns"].items():
        print(args.arm, coordinate, json.dumps(stages, sort_keys=True))


if __name__ == "__main__":
    main()
