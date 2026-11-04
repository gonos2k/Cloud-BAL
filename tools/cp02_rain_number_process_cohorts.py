#!/usr/bin/env python3
"""Freeze diagnostic RN1 transitions and exact WRF corner stencils for CP02 B1."""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np

REPO = Path(__file__).resolve().parents[1]
ANALYSIS = REPO / "docs/evidence/cp02_state_path_20261104/candidate/analysis"
OUT = REPO / "docs/evidence/cp02_rain_number_process_20261104/newcohorts"
MAPPING_TOOL = REPO / "tools/cp02_state_path_cohorts.py"
COORDINATE_TOOL = REPO / "tools/cp02_precip_control_mapping.py"
ARCHIVED_MAPPER = REPO / "docs/evidence/precip_hourly_20261027/rn1_recovery/archived_compare_six_hour_csi.py"
ANALYSIS_COORDS = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/ANAL/NE57/DAOU/DFSD/20260816/klps_lc05_anal_20260816_1300")
HISTORY = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_state_path_20261104/runtime/B1_RAIN_NUMBER_PRIOR_6H/wrfout_d01_2026-08-16_12:00:00")
THRESHOLDS = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0)
LEADS = (1, 2, 3, 4, 5, 6)
# P01/P02/FA03 retain their established IDs and sample coordinates from the
# earlier process cohort. Added H3 IDs are scoped explicitly to the +3h sample.
LEGACY = (
    ("P01", "preserved_weak_hit_lost", 476, None),
    ("P02", "preserved_weak_new_false_alarm", 819, None),
    ("FA03", "preserved_re_FA_threshold5", 1870, None),
)
MAPPING_ARRAY = ANALYSIS / "bilinear_mapping.npz"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def import_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import helper {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_arrays() -> dict[int, Any]:
    arrays = {}
    for lead, hour in zip(LEADS, range(13, 19)):
        path = ANALYSIS / f"hour_{hour}_arrays.npz"
        data = np.load(path, allow_pickle=False)
        required = {"ORIGINAL", "reference", "IMPROVED_BG_FIXED", "B1_RAIN_NUMBER_PRIOR", "flat_index_yx", "latitude", "longitude"}
        if set(data.files) != required:
            raise ValueError(f"{path.name}: unexpected field set {data.files}")
        if any(data[key].shape != (3688,) for key in required):
            raise ValueError(f"{path.name}: expected 3,688 paired values in every field")
        if len(np.unique(data["flat_index_yx"])) != 3688:
            raise ValueError(f"{path.name}: duplicate canonical sample coordinates")
        if any(not np.all(np.isfinite(data[key])) for key in required):
            raise ValueError(f"{path.name}: non-finite paired value or coordinate")
        if arrays and any(not np.array_equal(data[key], arrays[1][key])
                          for key in ("flat_index_yx", "latitude", "longitude")):
            raise ValueError(f"{path.name}: paired sample coordinates differ across leads")
        arrays[lead] = data
    return arrays


def map_stencil(index: int, arrays: Any, mapping: Any) -> set[tuple[int, int]]:
    flat = int(arrays["flat_index_yx"][index])
    y, x = divmod(flat, 149)
    if not bool(mapping["valid"][y, x]):
        raise ValueError(f"RN1 index {index} lacks a valid archived native mapping")
    j0, i0 = int(mapping["j0"][y, x]) + 5, int(mapping["i0"][y, x]) + 74
    return {(j0, i0), (j0, i0 + 1), (j0 + 1, i0), (j0 + 1, i0 + 1)}


def choose_index(arrays: Any, mapping: Any, eligible: np.ndarray, occupied: set[tuple[int, int]],
                 score: np.ndarray) -> int:
    flat = np.asarray(arrays["flat_index_yx"], dtype=np.int64)
    candidates = np.flatnonzero(eligible)
    order = sorted(candidates, key=lambda i: (-float(score[i]), int(flat[i])))
    for index in order:
        cells = map_stencil(int(index), arrays, mapping)
        if cells.isdisjoint(occupied):
            return int(index)
    raise ValueError("no eligible diagnostic point has a disjoint native corner stencil")


def select_indices(arrays_by_lead: dict[int, Any]) -> list[tuple[str, str, int, float]]:
    a = arrays_by_lead[3]
    mapping = np.load(MAPPING_ARRAY, allow_pickle=False)
    obs, b1, candidate = a["reference"], a["IMPROVED_BG_FIXED"], a["B1_RAIN_NUMBER_PRIOR"]
    definitions = [(*row[:3], row[3]) for row in LEGACY]
    occupied: set[tuple[int, int]] = set()
    for _, _, index, _ in LEGACY:
        occupied.update(map_stencil(index, a, mapping))
    rules = (
        ("H3_L01", "plus3_hit_loss_weak_0p1", (obs >= 0.1) & (obs < 1.0) & (b1 >= 0.1) & (candidate < 0.1), 0.1, np.abs(candidate - b1)),
        ("H3_L05", "plus3_hit_loss_weak_0p5", (obs >= 0.1) & (obs < 1.0) & (b1 >= 0.5) & (candidate < 0.5), 0.5, np.abs(candidate - b1)),
        ("H3_L1", "plus3_hit_loss_moderate_observed_1to5", (obs >= 1.0) & (obs < 5.0) & (b1 >= 0.5) & (candidate < 0.5), 0.5, np.abs(candidate - b1)),
        ("H3_FA01", "plus3_new_false_alarm_0p1", (obs < 0.1) & (b1 < 0.1) & (candidate >= 0.1), 0.1, candidate - b1),
        ("H3_FA5", "plus3_new_false_alarm_5_observed_1to5", (obs >= 1.0) & (obs < 5.0) & (b1 < 5.0) & (candidate >= 5.0), 5.0, candidate - b1),
        ("H3_H5", "plus3_retained_hit_5", (obs >= 5.0) & (b1 >= 5.0) & (candidate >= 5.0), 5.0, np.abs(candidate - b1)),
    )
    for point_id, role, eligible, threshold, score in rules:
        index = choose_index(a, mapping, eligible, occupied, score)
        definitions.append((point_id, role, index, threshold))
        occupied.update(map_stencil(index, a, mapping))
    return definitions


def make_points(arrays_by_lead: dict[int, Any]) -> list[dict[str, Any]]:
    a = arrays_by_lead[3]
    output = []
    for point_id, role, index, threshold in select_indices(arrays_by_lead):
        obs = float(a["reference"][index])
        b1 = float(a["IMPROVED_BG_FIXED"][index])
        candidate = float(a["B1_RAIN_NUMBER_PRIOR"][index])
        if point_id == "H3_L01" and not (0.0 < obs < 1.0 and b1 >= 0.1 and candidate < 0.1):
            raise ValueError("H3_L01 no longer meets its frozen +3h 0.1 mm weak hit-loss rule")
        if point_id == "H3_L05" and not (0.0 < obs < 1.0 and b1 >= 0.5 and candidate < 0.5):
            raise ValueError("H3_L05 no longer meets its frozen +3h 0.5 mm weak hit-loss rule")
        if point_id == "H3_L1" and not (1.0 <= obs < 5.0 and b1 >= 0.5 and candidate < 0.5):
            raise ValueError("H3_L1 no longer meets its frozen +3h moderate-rain hit-loss rule")
        if point_id == "H3_FA01" and not (obs < 0.1 and b1 < 0.1 <= candidate):
            raise ValueError("H3_FA01 no longer meets its frozen +3h new-FA rule")
        if point_id == "H3_FA5" and not (1.0 <= obs < 5.0 and b1 < 5.0 <= candidate):
            raise ValueError("H3_FA5 no longer meets its frozen +3h observed 1–5 mm new-FA rule")
        if point_id == "H3_H5" and not (obs >= 5.0 and b1 >= 5.0 and candidate >= 5.0):
            raise ValueError("H3_H5 no longer meets its frozen +3h retained-hit rule")
        output.append({
            "point_id": point_id,
            "diagnostic_group": role,
            "rn1_sample_index_zero_based": index,
            "target_flat_index_yx": int(a["flat_index_yx"][index]),
            "latitude": float(a["latitude"][index]),
            "longitude": float(a["longitude"][index]),
            "reference_plus3_mm": obs,
            "B1_plus3_mm": b1,
            "candidate_plus3_mm": candidate,
            "transition_threshold_mm": "" if threshold is None else threshold,
            "selection_rule": selection_rule(point_id),
        })
    return output


def selection_rule(point_id: str) -> str:
    if point_id in {"P01", "P02", "FA03"}:
        return "Preserved prior cohort identity and RN1 sample index; transition re-evaluated against current canonical arrays."
    rules = {
        "H3_L01": "Among +3h paired cases observed 0.1–1 mm with B1 hit and candidate miss at 0.1 mm, maximize |candidate−B1|; tie-break lowest flat index; selected native stencil must not overlap frozen points.",
        "H3_L05": "Among +3h paired cases observed 0.1–1 mm with B1 hit and candidate miss at 0.5 mm, maximize |candidate−B1| after excluding stencils overlapping previously selected points; tie-break lowest flat index. Index 574 is excluded because its mapped stencil overlaps H3_L01; the next disjoint eligible point is selected.",
        "H3_L1": "Among +3h paired cases observed 1–5 mm with B1 hit and candidate miss at 0.5 mm, maximize |candidate−B1|; tie-break lowest flat index.",
        "H3_FA01": "Among +3h paired cases observed <0.1 mm with B1 below and candidate at/above 0.1 mm, maximize candidate−B1; tie-break lowest flat index.",
        "H3_FA5": "Among +3h paired cases observed 1–5 mm with B1 below and candidate at/above 5 mm, maximize candidate−B1; tie-break lowest flat index.",
        "H3_H5": "Among +3h paired cases observed at/above 5 mm with both B1 and candidate at/above 5 mm, maximize |candidate−B1|; tie-break lowest flat index.",
    }
    return rules[point_id]


def transition_rows(arrays_by_lead: dict[int, Any], points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for lead, arrays in arrays_by_lead.items():
        for point in points:
            i = int(point["rn1_sample_index_zero_based"])
            obs = float(arrays["reference"][i])
            values = {case: float(arrays[key][i]) for case, key in (
                ("ORIGINAL", "ORIGINAL"), ("B1", "IMPROVED_BG_FIXED"), ("B1_RAIN_NUMBER_PRIOR", "B1_RAIN_NUMBER_PRIOR"))}
            for threshold in THRESHOLDS:
                observed = obs >= threshold
                for case, forecast in values.items():
                    hit = forecast >= threshold
                    rows.append({
                        "point_id": point["point_id"], "lead_hour": lead,
                        "valid_hour_utc": 12 + lead, "threshold_mm": threshold,
                        "reference_mm": obs, "case": case, "forecast_mm": forecast,
                        "observed_event": observed, "forecast_event": hit,
                        "transition": "hit" if observed and hit else "miss" if observed else "false_alarm" if hit else "correct_negative",
                    })
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"refusing empty output: {path}")
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    arrays_by_lead = load_arrays()
    points = make_points(arrays_by_lead)
    helper = import_module(MAPPING_TOOL, "cp02_state_path_cohorts_for_rain_number")
    corners, mapping = helper.map_corners(points, arrays_by_lead[3], HISTORY, ANALYSIS_COORDS, COORDINATE_TOOL, ARCHIVED_MAPPER)
    unique_cells = sorted({(int(row["native_j_zero_based"]), int(row["native_i_zero_based"])) for row in corners})
    if len(unique_cells) != 36:
        raise ValueError(f"expected 36 unique global corner cells, got {len(unique_cells)}")
    global_ids = {cell: f"GC{index:03d}" for index, cell in enumerate(unique_cells, start=1)}
    for row in corners:
        row["global_corner_id"] = global_ids[(int(row["native_j_zero_based"]), int(row["native_i_zero_based"]))]
    global_rows = [{"global_corner_id": global_ids[(j, i)], "native_j_zero_based": j, "native_i_zero_based": i,
                    "wrf_j_1based": j + 1, "wrf_i_1based": i + 1}
                   for j, i in unique_cells]
    args.output.mkdir(parents=True, exist_ok=True)
    write_csv(args.output / "selected_points.csv", points)
    write_csv(args.output / "point_corners.csv", corners)
    write_csv(args.output / "unique_global_corners.csv", global_rows)
    write_csv(args.output / "point_transitions.csv", transition_rows(arrays_by_lead, points))
    receipt = {
        "selection": "9 diagnostic locations; not a forecast-score subset or postselected candidate winner",
        "points": len(points), "point_corner_rows": len(corners), "unique_global_corner_cells": len(unique_cells),
        "transition_rows": len(transition_rows(arrays_by_lead, points)),
        "preserved_ids": ["P01", "P02", "FA03"],
        "history_geometry": {"source_shape_yxz": [282, 234, 39], "source_interior_j_zero_based_half_open": [1, 281],
                             "source_interior_i_zero_based_half_open": [1, 233], "source_interior_shape_yx": [280, 232]},
        "sample_index_contract": "NPZ RN1 sample index is zero based; flat_index_yx indexes the 253x149 ODAM crop. Native WRF j/i columns include explicit zero and Fortran one based indices.",
        "mapping": mapping["mapping"],
        "inputs": {str(path.relative_to(REPO)): sha256(path) for path in [
            *(ANALYSIS / f"hour_{hour}_arrays.npz" for hour in range(13, 19)), MAPPING_ARRAY, MAPPING_TOOL, COORDINATE_TOOL, ARCHIVED_MAPPER]},
    }
    (args.output / "mapping_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: receipt[key] for key in ("points", "point_corner_rows", "unique_global_corner_cells", "transition_rows")}, sort_keys=True))


if __name__ == "__main__":
    main()
