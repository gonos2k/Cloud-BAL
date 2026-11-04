#!/usr/bin/env python3
"""Recount CP02 two-hour scores and map four threshold-5 FA transitions.

All precipitation metrics use the complete, paired 3,688-point arrays. The
four mapped FA points are instrumentation locations, not a new candidate or
an evaluation subset.
"""
from __future__ import annotations

import argparse
import csv
import gzip
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
from netCDF4 import Dataset

REPO = Path(__file__).resolve().parents[1]
EVIDENCE = REPO / "docs/evidence/cp02_state_path_20261104/cohorts"
DEFAULT_BASE = Path("/var/tmp/cloudbal-recount-contract")
ANALYSIS_DIR = DEFAULT_BASE / "docs/evidence/weak_strong_balance_20261030/analysis"
OLD_POINTS = REPO / "docs/evidence/cp02_b1_two_hour_process_20261103/cohorts/selected_points.csv"
MAPPING_TOOL = REPO / "tools/cp02_precip_control_mapping.py"
ANALYSIS_COORDS = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/ANAL/NE57/DAOU/DFSD/20260816/klps_lc05_anal_20260816_1300")
WRF_HISTORY = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/weak_strong_balance_20261030/ORIGINAL_B1_100/wrfout_d01_2026-08-16_12:00:00")
MAPPER = REPO / "docs/evidence/precip_hourly_20261027/rn1_recovery/archived_compare_six_hour_csi.py"
THRESHOLDS = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0)
LOW_THRESHOLDS = (0.1, 0.5, 1.0)
FA_POINTS = (("FA01", 582), ("FA02", 899), ("FA03", 1870), ("FA04", 1772))
PROCESS_EVIDENCE = REPO / "docs/evidence/cp02_b1_two_hour_process_20261103/analysis_gates/compact_tables"
PHASE_RECORDS = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_two_hour_probe_20261103/analysis_run1/OLD/old_phase_records.csv")
PHASE_RECORDS_SHA256 = "8fb2ed1f7b630e2a4327a53427f5e93bdaa5b81da359664c0db87a6c9f70261d"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def validate_arrays(arrays: Any, label: str) -> None:
    required = {"reference", "ORIGINAL_B1_100", "IMPROVED_BG_FIXED", "flat_index_yx", "latitude", "longitude"}
    available = set(arrays.files) if hasattr(arrays, "files") else set(arrays)
    missing = sorted(required.difference(available))
    if missing:
        raise ValueError(f"{label}: missing required fields: {missing}")
    lengths = {key: int(arrays[key].shape[0]) for key in required}
    if set(lengths.values()) != {3688}:
        raise ValueError(f"{label}: expected all six canonical fields to have 3688 rows; got {lengths}")
    if any(arrays[key].ndim != 1 for key in required):
        raise ValueError(f"{label}: canonical fields must be one-dimensional")
    indices = np.asarray(arrays["flat_index_yx"], dtype=np.int64)
    if len(np.unique(indices)) != 3688:
        raise ValueError(f"{label}: duplicate RN1 flat indices")
    if not all(np.isfinite(np.asarray(arrays[key], dtype=np.float64)).all()
               for key in ("reference", "ORIGINAL_B1_100", "IMPROVED_BG_FIXED", "latitude", "longitude")):
        raise ValueError(f"{label}: non-finite value in canonical arrays")


def threshold_counts(obs: np.ndarray, old: np.ndarray, fix: np.ndarray, threshold: float) -> dict[str, int | float]:
    o, a, b = obs >= threshold, old >= threshold, fix >= threshold
    hh = int(np.count_nonzero(o & a & b))
    old_only = int(np.count_nonzero(o & a & ~b))
    fix_only = int(np.count_nonzero(o & ~a & b))
    neither_hit = int(np.count_nonzero(o & ~a & ~b))
    no_obs = ~o
    fa_old_only = int(np.count_nonzero(no_obs & a & ~b))
    fa_fix_only = int(np.count_nonzero(no_obs & ~a & b))
    fa_both = int(np.count_nonzero(no_obs & a & b))
    fa_neither = int(np.count_nonzero(no_obs & ~a & ~b))
    old_hit, fix_hit = hh + old_only, hh + fix_only
    miss_old, miss_fix = int(np.count_nonzero(o & ~a)), int(np.count_nonzero(o & ~b))
    fa_old, fa_fix = fa_old_only + fa_both, fa_fix_only + fa_both
    denom_old, denom_fix = old_hit + miss_old + fa_old, fix_hit + miss_fix + fa_fix
    return {
        "threshold_mm": threshold, "n": int(obs.size),
        "OLD_hit": old_hit, "OLD_miss": miss_old, "OLD_false_alarm": fa_old,
        "OLD_CSI": old_hit / denom_old if denom_old else float("nan"),
        "FIX_hit": fix_hit, "FIX_miss": miss_fix, "FIX_false_alarm": fa_fix,
        "FIX_CSI": fix_hit / denom_fix if denom_fix else float("nan"),
        "hit_both": hh, "hit_old_only": old_only, "hit_fix_only": fix_only,
        "hit_neither": neither_hit, "fa_neither": fa_neither,
        "fa_old_only": fa_old_only, "fa_fix_only": fa_fix_only, "fa_both": fa_both,
    }


def recalc_scores(analysis_dir: Path) -> tuple[list[dict[str, Any]], dict[int, Any]]:
    rows, arrays_by_hour = [], {}
    for lead, valid_hour in ((1, 13), (2, 14)):
        path = analysis_dir / f"hour_{valid_hour}_arrays.npz"
        arrays = np.load(path, allow_pickle=False)
        validate_arrays(arrays, path.name)
        arrays_by_hour[lead] = arrays
        for threshold in THRESHOLDS:
            rows.append({"lead_hour": lead, **threshold_counts(
                arrays["reference"], arrays["ORIGINAL_B1_100"], arrays["IMPROVED_BG_FIXED"], threshold)})
    return rows, arrays_by_hour


def cohorts(arrays_by_hour: dict[int, Any], old_points_path: Path) -> list[dict[str, Any]]:
    points = []
    with old_points_path.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            points.append({**row, "point_id": row["point_id"], "source": "preserved_cp02_b1_two_hour_process_20261103"})
    arrays = arrays_by_hour[2]
    for point_id, i in FA_POINTS:
        if not 0 <= i < arrays["reference"].size:
            raise ValueError(f"required RN1 sample index outside canonical array: {i}")
        flat = int(arrays["flat_index_yx"][i])
        old, fix, obs = (float(arrays[key][i]) for key in ("ORIGINAL_B1_100", "IMPROVED_BG_FIXED", "reference"))
        if not (obs < 5.0 and old >= 5.0 and fix < 5.0) if point_id != "FA04" else not (obs < 5.0 and old < 5.0 and fix >= 5.0):
            raise ValueError(f"{point_id} flat index {flat} no longer matches declared threshold-5 transition")
        points.append({"point_id": point_id, "diagnostic_group": "threshold5_removed_false_alarm" if point_id != "FA04" else "threshold5_new_false_alarm",
                       "rn1_sample_index_zero_based": i, "target_flat_index_yx": flat,
                       "latitude": float(arrays["latitude"][i]), "longitude": float(arrays["longitude"][i]),
                       "reference_plus2_mm": obs, "OLD_plus2_mm": old, "FIX_plus2_mm": fix,
                       "selection_rule": "explicitly requested threshold-5 transition; instrumentation point only; full-array scores remain authoritative",
                       "source": "weak_strong_balance_20261030/hour_14_arrays.npz"})
    ids = [p["point_id"] for p in points]
    if ids[:4] != ["P01", "P02", "P03", "P04"] or ids[4:] != ["FA01", "FA02", "FA03", "FA04"]:
        raise ValueError("preserved P01..P04 order or new FA01..FA04 order changed")
    return points


def map_corners(points: list[dict[str, Any]], arrays: Any, history: Path, analysis_coords: Path,
                mapping_tool: Path, mapper_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    mapper_tool = load_module(mapping_tool, "cp02_state_path_control_mapping")
    mapper = mapper_tool.load_archived_mapper()
    with Dataset(analysis_coords) as ds:
        lat = np.asarray(ds["lat"][6:259, 75:224], dtype=np.float64)
        lon = np.asarray(ds["lon"][6:259, 75:224], dtype=np.float64)
    if lat.shape != (253, 149) or lon.shape != lat.shape:
        raise ValueError(f"unexpected ODAM coordinate crop shape {lat.shape}/{lon.shape}")
    with Dataset(history) as ds:
        source_lat = np.asarray(ds["XLAT"][0], dtype=np.float64)
        source_lon = np.asarray(ds["XLONG"][0], dtype=np.float64)
    jbase, ibase = 5, 74
    mask = np.zeros(lat.shape, dtype=bool)
    positions = {}
    for point in points:
        index = int(point["rn1_sample_index_zero_based"])
        y, x = divmod(int(point["target_flat_index_yx"]), 149)
        if not (0 <= y < 253 and 0 <= x < 149):
            raise ValueError(f"{point['point_id']}: RN1 flat index outside canonical crop")
        if int(arrays["flat_index_yx"][index]) != int(point["target_flat_index_yx"]):
            raise ValueError(f"{point['point_id']}: sample index and flat index disagree")
        point_lat, point_lon = float(point["latitude"]), float(point["longitude"])
        if (float(lat[y, x]), float(lon[y, x])) != (point_lat, point_lon):
            raise ValueError(f"{point['point_id']}: NPZ and ODAM coordinates disagree")
        mask[y, x] = True
        positions[point["point_id"]] = (y, x)
    mapped = mapper.build_curvilinear_mapping(source_lat[jbase:259, ibase:224], source_lon[jbase:259, ibase:224], lat, lon, mask)
    rows = []
    for point in points:
        y, x = positions[point["point_id"]]
        j0, i0 = int(mapped["j0"][y, x]) + jbase, int(mapped["i0"][y, x]) + ibase
        u, v = float(mapped["u"][y, x]), float(mapped["v"][y, x])
        cells = ((j0, i0), (j0, i0 + 1), (j0 + 1, i0), (j0 + 1, i0 + 1))
        weights = ((1-u)*(1-v), u*(1-v), (1-u)*v, u*v)
        recon_lat = sum(w * source_lat[j, i] for (j, i), w in zip(cells, weights))
        recon_lon = sum(w * source_lon[j, i] for (j, i), w in zip(cells, weights))
        if abs(sum(weights) - 1.0) > 1e-12 or max(abs(recon_lat - float(point["latitude"])), abs(recon_lon - float(point["longitude"]))) > 1e-6:
            raise ValueError(f"{point['point_id']}: bilinear WRF stencil failed coordinate reconstruction")
        for corner, (j, i), weight in zip(("00", "10", "01", "11"), cells, weights):
            rows.append({"point_id": point["point_id"], "diagnostic_group": point["diagnostic_group"],
                         "rn1_sample_index_zero_based": point["rn1_sample_index_zero_based"],
                         "target_flat_index_yx": point["target_flat_index_yx"], "target_y_zero_based": y,
                         "target_x_zero_based": x, "latitude": point["latitude"], "longitude": point["longitude"],
                         "corner": corner, "native_j_zero_based": j, "native_i_zero_based": i,
                         "wrf_j_1based": j+1, "wrf_i_1based": i+1, "weight": weight,
                         "bilinear_u": u, "bilinear_v": v,
                         "coordinate_residual_max_deg": float(mapped["residual_max_deg"]),
                         "reconstructed_latitude": recon_lat, "reconstructed_longitude": recon_lon,
                         "weight_sum": sum(weights), "coordinate_source": str(history)})
    validate_corner_contract(points, rows)
    coordinates = {"description": "8 canonical RN1 cells for native instrumentation; four actual WRF bilinear corners each",
                   "points": [{key: value for key, value in row.items() if key not in ("source",)} for row in points],
                   "unique_global_native_cells": sorted({(r["native_j_zero_based"], r["native_i_zero_based"]) for r in rows}),
                   "mapping": {"algorithm": "build_curvilinear_mapping from pinned cp02_precip_control_mapping tool and archived mapper",
                               "jbase": jbase, "ibase": ibase, "analysis_crop_shape_yx": [253,149],
                               "analysis_crop": "lat/lon[6:259,75:224]", "native_crop": "[j=5:259,i=74:224]",
                               "wrf_history": str(history), "wrf_history_sha256": sha256(history),
                               "analysis_coordinate_file": str(analysis_coords), "analysis_coordinate_sha256": sha256(analysis_coords),
                               "mapping_tool": str(mapping_tool), "mapping_tool_sha256": sha256(mapping_tool),
                               "archived_mapper": str(mapper_path), "archived_mapper_sha256": sha256(mapper_path),
                               "max_mapping_residual_deg": float(mapped["residual_max_deg"])}}
    return rows, coordinates


def validate_corner_contract(points: list[dict[str, Any]], rows: list[dict[str, Any]]) -> None:
    expected_ids = {str(point["point_id"]) for point in points}
    corners = {"00", "10", "01", "11"}
    if len(expected_ids) != len(points):
        raise ValueError("point list contains duplicate IDs")
    if len(rows) != len(points) * 4:
        raise ValueError(f"expected exactly four corners for each point; got {len(rows)} rows for {len(points)} points")
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["point_id"]), []).append(row)
    if set(grouped) != expected_ids:
        raise ValueError(f"corner point-ID set mismatch: expected {sorted(expected_ids)}, got {sorted(grouped)}")
    if any(len(grouped[point_id]) != 4 or {str(row["corner"]) for row in grouped[point_id]} != corners for point_id in expected_ids):
        raise ValueError("each point must contain exactly one of corners 00, 10, 01, and 11")
    cells = {(int(row["native_j_zero_based"]), int(row["native_i_zero_based"])) for row in rows}
    if len(cells) != len(rows):
        raise ValueError("native corner cell repeats across the requested eight point stencils")
    if len(points) == 8 and len(cells) != 32:
        raise ValueError(f"expected 32 unique global WRF cells for the eight frozen points; got {len(cells)}")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"refusing to write empty table: {path}")
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def read_gzip_csv(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def keyed_latent_temperature(p02_events: list[dict[str, Any]], phase_records_path: Path) -> dict[str, Any]:
    if sha256(phase_records_path) != PHASE_RECORDS_SHA256:
        raise ValueError("OLD phase-record CSV does not match its run1 receipt SHA-256")
    target = {}
    for event in p02_events:
        # The saved phase key preserves the event table's full model indices.
        key = (int(event["rank"]), int(event["call_id"]), int(event["itimestep"]), int(event["loop"]),
               int(event["j"]), int(event["i"]), int(event["k"]))
        target[key] = event
    found = {}
    with phase_records_path.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            if row["phase"] != "LATENT_INPUT":
                continue
            key = tuple(int(value) for value in json.loads(row["key_json"]))
            if key not in target:
                continue
            if key in found:
                raise ValueError(f"duplicate LATENT_INPUT key for P02 k=8 zero event: {key}")
            values = json.loads(row["values_json"])
            found[key] = {"xlwork2": float(values["xlwork2"]), "cpm": float(values["cpm"]),
                          "dtcld": float(values["dtcld"]), "xl": float(values["xl"]),
                          "raw_words_json": row["raw_words_json"]}
    if set(found) != set(target):
        raise ValueError(f"LATENT_INPUT key mismatch: expected {len(target)}, found {len(found)}")
    terms = []
    xl_terms = []
    for key, event in target.items():
        row = found[key]
        rate = np.float32(float(event["process_prev"]))
        dt = np.float32(row["dtcld"])
        xl = np.float32(row["xl"])
        cpm = np.float32(row["cpm"])
        total_term = np.float32(-np.float32(np.float32(row["xlwork2"]) / cpm) * dt)
        xl_component = np.float32(np.float32(-xl) * rate)
        process_term = np.float32(-np.float32(np.float32(xl_component / cpm) * dt))
        terms.append({"event": event, "total_local_latent_T_term": float(total_term),
                      "prevp_xl_T_term": float(process_term), "latent": row})
        xl_terms.append(float(event["weight"]) * float(process_term))
    weighted_total = sum(float(x["event"]["weight"]) * x["total_local_latent_T_term"] for x in terms)
    differences = [x["total_local_latent_T_term"] - x["prevp_xl_T_term"] for x in terms]
    return {"phase_records": str(phase_records_path), "phase_records_sha256": PHASE_RECORDS_SHA256,
            "matched_keys": len(terms), "key_rule": "full rank/call/step/loop/j/i/k exact",
            "P02_k8_zero_event_bilinear_weighted_total_local_latent_T_K": weighted_total,
            "P02_k8_zero_event_bilinear_weighted_xl_times_final_prevp_T_K": sum(xl_terms),
            "P02_k8_zero_event_unweighted_total_local_latent_T_K": sum(x["total_local_latent_T_term"] for x in terms),
            "sign_review": {"preserved_initial_wrong_sign_attempt_formula": "-REAL32(REAL32(xl*prevp)/cpm*dtcld) (omitted source xl_component=-xl*prevp sign)",
                            "preserved_initial_wrong_sign_bilinear_weighted_sum_K": -sum(xl_terms),
                            "correct_source_order": "xl_component=REAL32(REAL32(-xl)*prevp); T_term=-REAL32(REAL32(xl_component/cpm)*dtcld)",
                            "correct_isolated_prevp_bilinear_weighted_sum_K": sum(xl_terms)},
            "total_equals_isolated_prevp_term": {"events_equal_numeric": sum(d == 0.0 for d in differences),
                                                  "events_compared": len(differences),
                                                  "max_abs_event_difference_K": max(abs(d) for d in differences)},
            "scope": "15-event zero-raw subset only; total_local_latent uses logged xlwork2, while isolated PREVP uses xl_component=REAL32(REAL32(-xl)*prevp) and T term=-REAL32(REAL32(xl_component/cpm)*dtcld); equality is reported only if the per-event numerical comparison supports it; neither is a full-column or full-hour temperature integral",
            "matched_event_terms": [{"corner": x["event"]["corner"], "hour": x["event"]["hour"],
                                     "itimestep": x["event"]["itimestep"], "loop": x["event"]["loop"],
                                     "j": x["event"]["j"], "i": x["event"]["i"], "k": x["event"]["k"],
                                     "weight": x["event"]["weight"], "process_prev": x["event"]["process_prev"],
                                     "xlwork2": x["latent"]["xlwork2"], "cpm": x["latent"]["cpm"],
                                     "dtcld": x["latent"]["dtcld"], "xl": x["latent"]["xl"],
                                     "total_local_latent_T_term": x["total_local_latent_T_term"],
                                     "prevp_xl_T_term": x["prevp_xl_T_term"]} for x in terms]}


def zero_rate_state_paths(process_dir: Path, phase_records_path: Path | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Join classified zero-raw events to their PRE_UPDATE/POST_STEP records."""
    events = read_gzip_csv(process_dir / "old_zero_rate_events.csv.gz")
    steps = read_gzip_csv(process_dir / "old_cell_steps.csv.gz")
    key_fields = ("point_id", "corner", "source_file", "rank", "call_id", "itimestep", "loop", "j", "i", "k")
    states = {tuple(row[key] for key in key_fields): row for row in steps if row["arm"] == "OLD"}
    if len(states) != sum(row["arm"] == "OLD" for row in steps):
        raise ValueError("duplicate OLD cell-step join key")
    selected = [row for row in events if (row["point_id"] == "P01" and row["raw_class"] == "negative_zero")
                or (row["point_id"] == "P02" and int(row["k"]) == 8 and row["raw_class"] in ("negative_zero", "positive_zero"))]
    joined = []
    for event in selected:
        state = states.get(tuple(event[key] for key in key_fields))
        if state is None:
            raise ValueError(f"zero event has no matched OLD state: {event['point_id']} {event['corner']} {event['itimestep']}")
        q_pre, q_post = float(state["q_pre"]), float(state["q_post"])
        t_pre, t_post = float(state["t_pre"]), float(state["t_post"])
        q_ulp = float(np.spacing(np.float32(q_pre)))
        process = float(event["process_prev"])
        dt = float(state["dtcld"])
        joined.append({"point_id": event["point_id"], "corner": event["corner"], "weight": float(event["weight"]),
                       "hour": int(event["hour"]), "itimestep": int(event["itimestep"]), "loop": int(event["loop"]),
                       "j": int(event["j"]), "i": int(event["i"]), "k": int(event["k"]),
                       "raw_class": event["raw_class"], "raw_prev": float(event["raw_prev"]),
                       "last_cap_prev": float(event["sat_cap_prev"]), "process_prev": process,
                       "dtcld_s": dt, "process_increment_q_units": process * dt,
                       "q_pre": q_pre, "q_post": q_post, "q_change": q_post - q_pre,
                       "q_pre_ulp_real32": q_ulp, "increment_abs_over_q_ulp": abs(process * dt) / q_ulp if q_ulp else None,
                       "increment_abs_over_q_state": abs(process * dt) / abs(q_pre) if q_pre else None,
                       "t_pre_k": t_pre, "t_post_k": t_post, "t_change_k": t_post - t_pre,
                       "qr_pre": float(state["qr_pre"]), "qr_post": float(state["qr_post"]),
                       "qr_state_change": float(state["qr_post"]) - float(state["qr_pre"]),
                       "source_file": event["source_file"], "rank": int(event["rank"]), "call_id": int(event["call_id"])})
    p01 = [row for row in joined if row["point_id"] == "P01"]
    p02k8 = [row for row in joined if row["point_id"] == "P02"]
    if len(p01) != 190 or len(p02k8) == 0:
        raise ValueError(f"unexpected frozen zero-event counts: P01={len(p01)}, P02 k8={len(p02k8)}")
    if any(row["q_change"] != 0.0 or row["t_change_k"] != 0.0 for row in p01):
        raise ValueError("P01 zero-raw event changed observed q or T across PRE_UPDATE/POST_STEP")
    def stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
        vals = [r["process_increment_q_units"] for r in rows]
        ratios = [r["increment_abs_over_q_ulp"] for r in rows]
        return {"events": len(rows), "sum_process_prev_dtcld": sum(vals),
                "min_process_prev": min(r["process_prev"] for r in rows),
                "max_process_prev": max(r["process_prev"] for r in rows),
                "max_abs_process_increment": max(abs(v) for v in vals),
                "sum_abs_process_increment": sum(abs(v) for v in vals),
                "max_increment_in_real32_q_ulps": max(ratios),
                "max_increment_over_abs_q_pre": max(r["increment_abs_over_q_state"] for r in rows),
                "q_state_change_nonzero_events": sum(r["q_change"] != 0.0 for r in rows),
                "T_state_change_nonzero_events": sum(r["t_change_k"] != 0.0 for r in rows),
                "sum_qr_state_change": sum(r["qr_state_change"] for r in rows)}
    p02_groups = {}
    for hour in sorted({r["hour"] for r in p02k8}):
        group = [r for r in p02k8 if r["hour"] == hour]
        p02_groups[str(hour)] = {**stats(group),
                                 "bilinear_weighted_sum_process_prev_dtcld": sum(r["weight"] * r["process_increment_q_units"] for r in group)}
    p02_latent = keyed_latent_temperature(p02k8, phase_records_path) if phase_records_path is not None else None
    summary = {"source_scope": "existing archived OLD zero-rate events joined by full cell-step key to PRE_UPDATE/POST_STEP; no model rerun",
               "P01_negative_zero_raw_final_process": stats(p01),
               "P01_amplitude_interpretation": {"max_process_increment_vs_q_ulp": "REAL32 spacing at actual q_pre; increments are process_prev*dtcld",
               "actual_q_and_T_comparison": "every selected P01 event has numeric equality PRE_UPDATE==POST_STEP for q and T; raw-word columns are not present in this compact table",
                                                "rain_state_change": "observed qr_post-qr_pre in the same local update; not accumulated precipitation"},
               "P02_k8_all_raw_zero_events": {"all_event_stats": stats(p02k8),
                                              "bilinear_weighted_sum_process_prev_dtcld": sum(r["weight"] * r["process_increment_q_units"] for r in p02k8),
                                              "by_hour": p02_groups,
                                              "time_integral_definition": "sum(process_prev * dtcld) over selected zero-raw events; also report sum(weight * process_prev * dtcld) across the four mapped corners",
                                              "latent_temperature": p02_latent}}
    return joined, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis-dir", type=Path, default=ANALYSIS_DIR)
    parser.add_argument("--old-points", type=Path, default=OLD_POINTS)
    parser.add_argument("--wrf-history", type=Path, default=WRF_HISTORY)
    parser.add_argument("--analysis-coords", type=Path, default=ANALYSIS_COORDS)
    parser.add_argument("--process-dir", type=Path, default=PROCESS_EVIDENCE)
    parser.add_argument("--phase-records", type=Path, default=PHASE_RECORDS)
    parser.add_argument("--output-dir", type=Path, default=EVIDENCE)
    args = parser.parse_args()
    score_rows, arrays_by_hour = recalc_scores(args.analysis_dir)
    points = cohorts(arrays_by_hour, args.old_points)
    corner_rows, coordinates = map_corners(points, arrays_by_hour[2], args.wrf_history, args.analysis_coords, MAPPING_TOOL, MAPPER)
    state_rows, state_summary = zero_rate_state_paths(args.process_dir, args.phase_records)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "paired_scores.csv", score_rows)
    write_csv(args.output_dir / "selected_points.csv", points)
    write_csv(args.output_dir / "point_corners.csv", corner_rows)
    write_csv(args.output_dir / "zero_rate_state_paths.csv", state_rows)
    (args.output_dir / "native_instrumentation_coordinates.json").write_text(json.dumps(coordinates, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.output_dir / "zero_rate_state_path_summary.json").write_text(json.dumps(state_summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    input_paths = {f"hour_{hour+12}_arrays": args.analysis_dir / f"hour_{hour+12}_arrays.npz" for hour in (1,2)}
    input_paths.update({"preserved_selected_points": args.old_points,
                        "OLD_zero_rate_events": args.process_dir / "old_zero_rate_events.csv.gz",
                        "OLD_cell_steps": args.process_dir / "old_cell_steps.csv.gz",
                        "OLD_run1_phase_records": args.phase_records,
                        "WRF_history_coordinates": args.wrf_history,
                        "ODAM_analysis_coordinates": args.analysis_coords,
                        "control_mapping_tool": MAPPING_TOOL,
                        "archived_mapping_implementation": MAPPER})
    source_paths = {"analysis_script": Path(__file__).resolve(), "mapping_tool": MAPPING_TOOL, "archived_mapper": MAPPER}
    receipt = {"status": "complete", "created_utc": datetime.now(timezone.utc).isoformat(),
               "evaluation_scope": {"paired_valid_samples_per_lead": 3688, "leads_hours": [1,2],
               "thresholds_mm": list(THRESHOLDS), "score_reduction": "none; each lead/threshold recounted over all 3688 samples"},
               "inputs": {name: {"path": str(path), "sha256": sha256(path), "size_bytes": path.stat().st_size} for name,path in input_paths.items()},
               "source_pins": {name: {"path": str(path), "sha256": sha256(path)} for name,path in source_paths.items()},
               "preserved_point_ids": ["P01", "P02", "P03", "P04"],
               "added_transition_points": [{"point_id": p["point_id"], "flat_index_yx": p["target_flat_index_yx"]} for p in points[4:]],
               "outputs": {p.name: {"sha256": sha256(p), "size_bytes": p.stat().st_size} for p in args.output_dir.iterdir() if p.is_file() and p.name != "receipt.json"}}
    (args.output_dir / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "complete", "samples": 3688, "points": [p["point_id"] for p in points],
                      "unique_native_cells": len(coordinates["unique_global_native_cells"]), "output": str(args.output_dir)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
