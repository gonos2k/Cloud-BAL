#!/usr/bin/env python3
"""Reconcile captured surface rain and hourly WRF rain components at selected RN1 points."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import tempfile

import netCDF4
import numpy as np

ROOT = Path(__file__).resolve().parents[5]
BUNDLE = ROOT / "docs/evidence/cp02_protected_process_20261106"
RUNTIME = ROOT.parent / "runtime/native"
DEFAULT_CAPTURE = RUNTIME / "analysis/full_v4"
ANALYSIS_PLAN_SHA256 = "c14da5350a21957eea0e320e5b6cb4da3c8ca82430c38b98cfc096c0c4b24d6f"
QUICK_PLAN_SHA256 = "d8fbf329e658b292d9710617b9b501bf47bcbe89585fe9759095162656d40d28"
CAPTURE_PLAN_SHA256 = "9183bd9f6bf7d0781cb6793d7f88e7ad6e44d2adb166e065c923bb0b7e67434e"
SCHEMA_SHA256 = "677847102d32b1637340d94bcd24c3856d63348bd15ceb0a319d8b5eda8ff25c"
SOURCE_RECEIPT_SHA256 = "7ed9bf6189249468695e5ce4784f3733d04eed41dae95b3cb31bb46d6bc0ae37"
COHORT_RECEIPT_SHA256 = "cd1e03fbc075c25f6a4904ce278935dea8d23a2157162274835fca21fc911826"
POINT_CORNERS_SHA256 = "12a000e1dab5963f7327cce49a44e988940b8e1c208049dd7f5285f126e85ea9"
UNIQUE_CORNERS_SHA256 = "62b365cb0cc57b7b6006d8f6f760021f7424b94d7b381b507aeed093a9664b58"
SELECTED_POINTS_SHA256 = "f66afa0f60ea02389fae5d0112426bcffdbec8aad0bb2487486f3e945da3d18d"
WEAK_ANALYSIS = ROOT / "docs/evidence/weak_strong_balance_20261030/analysis"
GROUPED_ANALYSIS = ROOT / "docs/evidence/cp02_grouped_forecast_20261105/analysis"
ARMS = {"OLD": "ORIGINAL_B1_100", "FIX": "IMPROVED_BG_FIXED"}
HISTORY_HOURS = tuple(range(12, 18))
LEADS = tuple(range(1, 6))
DEFAULT_OUTPUT_DIR = BUNDLE / "science/surface/validated"
DEFAULT_BOUNDARY_OUTPUT = BUNDLE / "science/first_call_boundaries.json"


def sha(path: Path) -> str:
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def require_pin(path: Path, expected: str) -> None:
    if not path.is_file() or path.is_symlink() or sha(path) != expected:
        raise ValueError(f"frozen input hash differs: {path}")


def read_receipt(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_full_run(path: Path, expected_sha: str) -> tuple[dict, dict[str, dict[int, Path]]]:
    if sha(path) != expected_sha:
        raise ValueError("full run receipt hash differs")
    receipt = read_receipt(path)
    if receipt.get("status") != "PASS" or receipt.get("stage") != "full" or receipt.get("duration_seconds") != 18000:
        raise ValueError("paired five-hour native run did not PASS")
    if (receipt.get("quick_plan_sha256") != QUICK_PLAN_SHA256
            or receipt.get("capture_plan_sha256") not in (None, CAPTURE_PLAN_SHA256)):
        raise ValueError("native run differs from the frozen quick/capture plans")
    histories: dict[str, dict[int, Path]] = {}
    for arm in ARMS:
        row = receipt["arms"][arm]
        comparisons = row.get("history_comparisons", {})
        if row.get("status") != "PASS" or row.get("exit_code") != 0 or not row.get("success_marker"):
            raise ValueError(f"{arm}: full native execution did not PASS")
        if set(comparisons) != {f"{hour:02d}" for hour in HISTORY_HOURS}:
            raise ValueError(f"{arm}: history set is incomplete")
        histories[arm] = {}
        for hour in HISTORY_HOURS:
            comp = comparisons[f"{hour:02d}"]
            actual = Path(comp["actual"])
            if (not comp.get("all_variables_coordinates_attributes_exact")
                    or comp.get("actual_sha256") != comp.get("reference_sha256")
                    or sha(actual) != comp.get("actual_sha256")):
                raise ValueError(f"{arm} {hour:02d}Z history is not exact against its reference")
            histories[arm][hour] = actual
    return receipt, histories


def verify_collector(arm: str, run_sha: str, capture_root: Path) -> tuple[dict, dict[int, Path]]:
    directory = capture_root / arm
    receipt_path = directory / "capture_receipt.json"
    receipt = read_receipt(receipt_path)
    if (receipt.get("status") != "FULL_CAPTURE_STREAMS_VALIDATED" or receipt.get("mode") != "full"
            or receipt.get("arm") != arm or receipt.get("launch_receipt_sha256") != run_sha
            or receipt.get("actual_timesteps") != list(range(1, 901))
            or receipt.get("process_actual_timesteps") != list(range(1, 361)) + list(range(721, 901))
            or receipt.get("native_columns") != 381 or receipt.get("levels") != 39
            or receipt.get("surface_rows") != 900 * 381):
        raise ValueError(f"{arm}: strict full collector coverage or run binding is incomplete")
    if receipt.get("tool_sha256") != sha(ROOT / "tools/cp02_protected_process_capture.py"):
        raise ValueError(f"{arm}: collector source changed after full capture")
    for key, expected in (("capture_plan_sha256", CAPTURE_PLAN_SHA256),
                          ("schema_sha256", SCHEMA_SHA256),
                          ("source_generation_receipt_sha256", SOURCE_RECEIPT_SHA256),
                          ("cohort_receipt_sha256", COHORT_RECEIPT_SHA256)):
        if receipt.get(key) != expected:
            raise ValueError(f"{arm}: strict capture {key} pin differs")
    surface_paths = {}
    for lead in LEADS:
        start, end = (lead - 1) * 180 + 1, lead * 180
        rows = [row for row in receipt["outputs"] if row.get("channel") == "surface_rain_cumulative"
                and row.get("actual_start") == start and row.get("actual_end") == end]
        if len(rows) != 1:
            raise ValueError(f"{arm}: surface cumulative block {start}-{end} is missing or duplicated")
        row = rows[0]
        path = directory / row["path"]
        if path.is_symlink() or path.stat().st_size != row["size_bytes"] or sha(path) != row["sha256"]:
            raise ValueError(f"{arm}: captured surface block differs from its receipt")
        surface_paths[lead] = path
    return receipt, surface_paths


def verify_array_sources() -> tuple[dict, dict[int, dict], dict[int, dict]]:
    plan_path = BUNDLE / "analysis_plan.json"
    require_pin(plan_path, ANALYSIS_PLAN_SHA256)
    plan = read_receipt(plan_path)
    for relative, identity in plan["frozen_source_pins"].items():
        require_pin(ROOT / relative, identity["sha256"])
    weak_receipt = read_receipt(WEAK_ANALYSIS / "receipt.json")
    grouped_receipt = read_receipt(GROUPED_ANALYSIS / "receipt.json")
    if weak_receipt.get("status") != "COMPLETE" or grouped_receipt.get("status") != "COMPLETE":
        raise ValueError("frozen weak/strong X/A analysis receipt is not COMPLETE")
    weak, grouped = {}, {}
    for lead in LEADS:
        hour = 12 + lead
        name = f"hour_{hour}_arrays.npz"
        weak_record = weak_receipt["analysis_outputs"][name]
        grouped_record = grouped_receipt["outputs"][name]
        paths = ((WEAK_ANALYSIS / name, weak_record), (GROUPED_ANALYSIS / name, grouped_record))
        loaded = []
        for path, identity in paths:
            if path.stat().st_size != identity["size_bytes"] or sha(path) != identity["sha256"]:
                raise ValueError(f"frozen forecast array differs from its receipt: {path}")
            with np.load(path, allow_pickle=False) as archive:
                loaded.append({key: archive[key].copy() for key in archive.files})
        weak[hour], grouped[hour] = loaded
        ref, grp = loaded
        required = {"reference", "latitude", "longitude", "flat_index_yx", *ARMS.values()}
        if not required <= ref.keys() or not {"reference", "latitude", "longitude", "flat_index_yx", "A"} <= grp.keys():
            raise ValueError(f"hour {hour}: frozen weak/strong X/A fields are incomplete")
        for arrays in loaded:
            for name in ("reference", "latitude", "longitude", "flat_index_yx"):
                if arrays[name].shape != (3688,):
                    raise ValueError(f"hour {hour}: frozen sample vector differs: {name}")
            if not np.isfinite(ref["reference"]).all() or not np.isfinite(ref["ORIGINAL_B1_100"]).all() or not np.isfinite(ref["IMPROVED_BG_FIXED"]).all():
                raise ValueError(f"hour {hour}: frozen 3,688-point X/A arrays contain nonfinite values")
        if any(not np.array_equal(ref[key], grp[key]) for key in ("reference", "latitude", "longitude", "flat_index_yx")):
            raise ValueError(f"hour {hour}: paired score arrays disagree on sample coordinates")
    return plan, weak, grouped


def read_history(path: Path, expected_hour: int, native_i: np.ndarray, native_j: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    with netCDF4.Dataset(path) as dataset:
        if "Times" not in dataset.variables or not {"RAINNC", "RAINC"} <= dataset.variables.keys():
            raise ValueError(f"history lacks Times/RAINNC/RAINC: {path}")
        times = np.asarray(dataset.variables["Times"][:])
        text = b"".join(np.asarray(times[0]).reshape(-1).tolist()).decode("ascii").rstrip("\x00")
        expected = f"2026-08-16_{expected_hour:02d}:00:00"
        if text != expected:
            raise ValueError(f"history timestamp differs: {path}: {text} != {expected}")
        fields = []
        for name in ("RAINNC", "RAINC"):
            variable = dataset.variables[name]
            if (len(variable.shape) != 3 or variable.shape[0] != 1
                    or np.dtype(variable.dtype) != np.dtype(np.float32)):
                raise ValueError(f"history {name} does not contain exactly one time record")
            values = np.ma.asarray(variable[0])
            if np.ma.getmaskarray(values)[native_j - 1, native_i - 1].any():
                raise ValueError(f"history {name} has masked selected native corners")
            array = np.asarray(values.data, dtype=np.float32)
            selected = array[native_j - 1, native_i - 1]
            if not np.isfinite(selected).all():
                raise ValueError(f"history {name} has nonfinite selected native corners")
            fields.append(selected)
    return fields[0], fields[1]


def native_surface_values(path: Path, lead: int, native_ids: list[str], native_i: np.ndarray,
                          native_j: np.ndarray) -> tuple[np.ndarray, dict]:
    with np.load(path, allow_pickle=False) as archive:
        steps = archive["actual_timestep"]
        ids = archive["native_column_ids"].astype(str)
        ix, jx = archive["native_i_1based"], archive["native_j_1based"]
        values = archive["native_values"]
    if (not np.array_equal(steps, np.arange((lead - 1) * 180 + 1, lead * 180 + 1))
            or not np.array_equal(ids, np.asarray(native_ids))
            or not np.array_equal(ix, native_i) or not np.array_equal(jx, native_j)
            or values.shape != (180, 1, 381) or values.dtype != np.float32
            or not np.isfinite(values).all()):
        raise ValueError(f"captured surface timeline/column order differs for lead {lead}")
    endpoint = values[-1, 0, :].copy()
    return endpoint, {"path": str(path), "sha256": sha(path), "size_bytes": path.stat().st_size}


def build_rows(run_receipt: dict, histories: dict[str, dict[int, Path]], collectors: dict,
               weak_arrays: dict[int, dict], selected: list[dict[str, str]],
               point_corners: list[dict[str, str]], native_map: list[dict[str, str]]) -> tuple[list[dict], dict, dict[str, np.ndarray]]:
    native_ids = [row["global_corner_id"] for row in native_map]
    native_i = np.asarray([int(row["wrf_i_1based"]) for row in native_map], dtype=np.int32)
    native_j = np.asarray([int(row["wrf_j_1based"]) for row in native_map], dtype=np.int32)
    points = {row["point_id"]: row for row in selected}
    if len(points) != 150 or len(native_ids) != 381 or len(set(native_ids)) != 381:
        raise ValueError("frozen selected point/native-column population differs")
    by_point: dict[str, list[dict[str, str]]] = {}
    for row in point_corners:
        by_point.setdefault(row["point_id"], []).append(row)
    if set(by_point) != set(points) or any(len(rows) != 4 for rows in by_point.values()):
        raise ValueError("frozen native corner mapping does not cover exactly four corners per selected point")
    native_index = {(int(j), int(i)): ix for ix, (i, j) in enumerate(zip(native_i, native_j))}
    stencils = {}
    for point_id, rows in by_point.items():
        rows = sorted(rows, key=lambda row: row["corner"])
        indexes = [native_index[(int(row["wrf_j_1based"]), int(row["wrf_i_1based"]))] for row in rows]
        weights = np.asarray([float(row["weight"]) for row in rows], dtype=np.float64)
        if abs(weights.sum() - 1.0) > 1e-12 or not np.isfinite(weights).all():
            raise ValueError(f"{point_id}: bilinear weights are invalid")
        stencils[point_id] = (indexes, weights)
    old_history = {h: read_history(histories["OLD"][h], h, native_i, native_j) for h in HISTORY_HOURS}
    fix_history = {h: read_history(histories["FIX"][h], h, native_i, native_j) for h in HISTORY_HOURS}
    surface_endpoint_checks = {}
    surface_file_pins = {}
    rows = []
    point_ids = list(points)
    point_index = {point_id: index for index, point_id in enumerate(point_ids)}
    corner_indices = np.empty((len(point_ids), 4), dtype=np.int32)
    corner_weights = np.empty((len(point_ids), 4), dtype=np.float64)
    for point_id in point_ids:
        indexes, weights = stencils[point_id]
        corner_indices[point_index[point_id]] = indexes
        corner_weights[point_index[point_id]] = weights
    hourly_scores = np.empty((len(ARMS), len(LEADS), len(point_ids)), dtype=np.float64)
    endpoint_rainnc = np.stack([[old_history[hour][0] if arm == "OLD" else fix_history[hour][0]
                                 for hour in HISTORY_HOURS] for arm in ARMS])
    endpoint_rainc = np.stack([[old_history[hour][1] if arm == "OLD" else fix_history[hour][1]
                                for hour in HISTORY_HOURS] for arm in ARMS])
    surface_endpoints = np.empty((len(ARMS), len(LEADS), len(native_ids)), dtype=np.float32)
    score_differences: dict[str, list[float]] = {arm: [] for arm in ARMS}
    score_exact_matches: dict[str, int] = {arm: 0 for arm in ARMS}
    for arm_index, (arm, score_case, native_history) in enumerate((("OLD", ARMS["OLD"], old_history), ("FIX", ARMS["FIX"], fix_history))):
        surface_endpoint_checks[arm] = {}
        surface_file_pins[arm] = {}
        for lead in LEADS:
            captured, file_pin = native_surface_values(collectors[arm]["surface_paths"][lead], lead,
                                                       native_ids, native_i, native_j)
            history_rainnc = native_history[12 + lead][0]
            if not np.array_equal(captured.view(np.uint32), history_rainnc.view(np.uint32)):
                mismatch = int(np.count_nonzero(captured.view(np.uint32) != history_rainnc.view(np.uint32)))
                raise ValueError(f"{arm} lead {lead}: native cumulative KDM6 rain differs from RAINNC at {mismatch}/381 corners")
            surface_endpoint_checks[arm][str(lead)] = {"history_hour_utc": 12 + lead, "native_columns": 381,
                                                       "bitwise_equal_to_RAINNC": True, "mismatch_count": 0}
            surface_file_pins[arm][str(lead)] = file_pin
            surface_endpoints[arm_index, lead - 1] = captured
            prev_nc, prev_c = native_history[11 + lead]
            curr_nc, curr_c = native_history[12 + lead]
            delta_nc = curr_nc.astype(np.float64) - prev_nc.astype(np.float64)
            delta_c = curr_c.astype(np.float64) - prev_c.astype(np.float64)
            for point_id, point in points.items():
                indexes, weights = stencils[point_id]
                nc_hour = float(np.dot(delta_nc[indexes], weights))
                c_hour = float(np.dot(delta_c[indexes], weights))
                total_hour = nc_hour + c_hour
                flat = int(point["flat_index_yx"])
                sample = int(point["sample_index_zero_based"])
                score_arrays = weak_arrays[12 + lead]
                if (score_arrays["flat_index_yx"][sample] != flat
                        or not np.isclose(float(score_arrays["latitude"][sample]), float(point["latitude"]), rtol=0, atol=1e-6)
                        or not np.isclose(float(score_arrays["longitude"][sample]), float(point["longitude"]), rtol=0, atol=1e-6)):
                    raise ValueError(f"{point_id}: score-array sample index no longer maps to this flat ID")
                score_total = float(score_arrays[score_case][sample])
                hourly_scores[arm_index, lead - 1, point_index[point_id]] = score_total
                if not all(np.isfinite((nc_hour, c_hour, total_hour, score_total))):
                    raise ValueError(f"{point_id} lead {lead}: nonfinite hourly surface component")
                score_differences[arm].append(total_hour - score_total)
                score_exact_matches[arm] += int(total_hour == score_total)
                rows.append({"arm": arm, "frozen_score_case": score_case, "point_id": point_id,
                             "flat_index_yx": flat, "sample_index_zero_based": sample,
                             "latitude": float(point["latitude"]), "longitude": float(point["longitude"]),
                             "lead_hour": lead, "valid_hour_utc": 12 + lead,
                             "window_start_hour_utc": 11 + lead, "window_end_hour_utc": 12 + lead,
                             "RAINNC_hour_mm": nc_hour, "RAINC_hour_mm": c_hour,
                             "total_hour_mm": total_hour, "frozen_3688_hour_total_mm": score_total,
                             "actual_minus_frozen_mm": total_hour - score_total})
    if len(rows) != 150 * 5 * 2:
        raise ValueError(f"hourly component table has {len(rows)} rows, expected 1500")
    for arm in ARMS:
        if max(abs(value) for value in score_differences[arm]) > 1e-12:
            raise ValueError(f"{arm}: hourly surface totals disagree with the frozen score arrays")
    diagnostics = {"surface_rain_vs_history_RAINNC": surface_endpoint_checks,
                   "surface_channel_file_pins": surface_file_pins,
                   "hourly_total_vs_frozen_3688_score_arrays": {
                       arm: {"rows": len(score_differences[arm]), "exact_matches": score_exact_matches[arm],
                             "max_absolute_difference_mm": max(abs(value) for value in score_differences[arm]),
                             "mean_absolute_difference_mm": float(np.mean(np.abs(score_differences[arm])))}
                       for arm in ARMS}}
    packet = {"arm_labels": np.asarray(list(ARMS), dtype="U3"),
              "score_case_labels": np.asarray([ARMS[arm] for arm in ARMS], dtype="U32"),
              "history_hours_utc": np.asarray(HISTORY_HOURS, dtype=np.int32),
              "history_timestamps_utc": np.asarray([[f"2026-08-16_{hour:02d}:00:00" for hour in HISTORY_HOURS]
                                                   for _arm in ARMS], dtype="U19"),
              "native_column_ids": np.asarray(native_ids, dtype="U6"),
              "native_i_1based": native_i, "native_j_1based": native_j,
              "RAINNC_history_mm": endpoint_rainnc.astype(np.float32),
              "RAINC_history_mm": endpoint_rainc.astype(np.float32),
              "KDM6_surface_rain_cumulative_lead_end_mm": surface_endpoints,
              "point_ids": np.asarray(point_ids, dtype="U16"),
              "point_flat_index_yx": np.asarray([int(points[pid]["flat_index_yx"]) for pid in point_ids], dtype=np.int64),
              "point_sample_index_zero_based": np.asarray([int(points[pid]["sample_index_zero_based"]) for pid in point_ids], dtype=np.int32),
              "point_latitude": np.asarray([float(points[pid]["latitude"]) for pid in point_ids], dtype=np.float64),
              "point_longitude": np.asarray([float(points[pid]["longitude"]) for pid in point_ids], dtype=np.float64),
              "point_native_corner_indices": corner_indices, "point_corner_weights": corner_weights,
              "frozen_score_hour_total_mm": hourly_scores}
    return rows, diagnostics, packet


def first_call_boundaries(histories: dict[str, dict[int, Path]], collectors: dict,
                          native_map: list[dict[str, str]]) -> dict:
    native_ids = [row["global_corner_id"] for row in native_map]
    native_i = np.asarray([int(row["wrf_i_1based"]) for row in native_map], dtype=np.int32)
    native_j = np.asarray([int(row["wrf_j_1based"]) for row in native_map], dtype=np.int32)
    field_names = ("TH", "QV", "QC", "QR", "QI", "QS", "QG", "NN", "NC", "NI", "NR", "BG", "DEN", "TK", "P", "PII")
    first_values: dict[str, dict[str, np.ndarray]] = {arm: {} for arm in ARMS}
    first_files: dict[str, dict[str, dict]] = {arm: {} for arm in ARMS}
    for arm in ARMS:
        receipt = collectors[arm]["receipt"]
        for field in field_names:
            channel = f"state_entry_{field}"
            row = next((item for item in receipt["outputs"] if item.get("channel") == channel
                        and item.get("actual_start") == 1 and item.get("actual_end") == 180), None)
            if row is None:
                raise ValueError(f"{arm}: first-call entry state is missing: {field}")
            path = collectors[arm]["directory"] / row["path"]
            if path.is_symlink() or path.stat().st_size != row["size_bytes"] or sha(path) != row["sha256"]:
                raise ValueError(f"{arm}: first-call entry state file differs from receipt: {field}")
            with np.load(path, allow_pickle=False) as archive:
                steps = archive["actual_timestep"]
                ids = archive["native_column_ids"].astype(str)
                values = archive["native_values"]
                ix, jx = archive["native_i_1based"], archive["native_j_1based"]
                if (not np.array_equal(steps, np.arange(1, 181)) or not np.array_equal(ids, native_ids)
                        or not np.array_equal(ix, native_i) or not np.array_equal(jx, native_j)
                        or values.shape != (180, 39, 381) or values.dtype != np.float32
                        or not np.isfinite(values[0]).all()):
                    raise ValueError(f"{arm}: first-call entry state has invalid keys/shape: {field}")
                first_values[arm][field] = values[0].copy()
            first_files[arm][field] = {"path": row["path"], "sha256": row["sha256"], "size_bytes": row["size_bytes"]}
    entry_comparison = {}
    for field in field_names:
        old, fix = first_values["OLD"][field], first_values["FIX"][field]
        unequal = old.view(np.uint32) != fix.view(np.uint32)
        entry_comparison[field] = {"bitwise_identical": not bool(unequal.any()), "mismatch_count": int(unequal.sum())}
        if unequal.any():
            raise ValueError(f"first-call entry field differs between OLD/FIX: {field}")

    def first_stream_value(arm: str, channel: str) -> tuple[np.ndarray, dict]:
        receipt = collectors[arm]["receipt"]
        row = next((item for item in receipt["outputs"] if item.get("channel") == channel
                    and item.get("actual_start") == 1 and item.get("actual_end") == 180), None)
        if row is None:
            raise ValueError(f"{arm}: first-call stream is missing: {channel}")
        path = collectors[arm]["directory"] / row["path"]
        if path.is_symlink() or path.stat().st_size != row["size_bytes"] or sha(path) != row["sha256"]:
            raise ValueError(f"{arm}: first-call stream file differs from receipt: {channel}")
        with np.load(path, allow_pickle=False) as archive:
            steps, ids = archive["actual_timestep"], archive["native_column_ids"].astype(str)
            values = archive["native_values"]
            if (not np.array_equal(steps, np.arange(1, 181)) or not np.array_equal(ids, native_ids)
                    or values.shape != (180, 1, 381) or values.dtype != np.float32
                    or not np.isfinite(values).all()):
                raise ValueError(f"{arm}: invalid first-call surface stream")
            return values[:, 0, :].copy(), {"path": row["path"], "sha256": row["sha256"], "size_bytes": row["size_bytes"]}

    surface, surface_files = {}, {}
    entry_surface_equal = None
    for arm in ARMS:
        first_surface, first_file = first_stream_value(arm, "surface_rain_cumulative")
        segments = []
        files = []
        for lead in LEADS:
            path = collectors[arm]["surface_paths"][lead]
            with np.load(path, allow_pickle=False) as archive:
                values = archive["native_values"]
                if values.shape != (180, 1, 381):
                    raise ValueError(f"{arm}: full surface stream shape differs at lead {lead}")
                segments.append(values[:, 0, :].copy())
            files.append({"path": str(path.relative_to(collectors[arm]["directory"])), "sha256": sha(path), "size_bytes": path.stat().st_size})
        surface[arm] = np.concatenate(segments, axis=0)
        surface_files[arm] = {"first_call": first_file, "all_leads": files}
        if surface[arm].shape != (900, 381):
            raise ValueError(f"{arm}: concatenated full surface stream shape differs")
    entry_surface_equal = bool(np.array_equal(surface["OLD"][0].view(np.uint32), surface["FIX"][0].view(np.uint32)))
    if not entry_surface_equal:
        raise ValueError("first-call cumulative surface rain differs between OLD/FIX")

    return_differences = {}
    return_files = {}
    for field in field_names:
        channel = f"state_return_{field}"
        streams = {}
        files = {}
        for arm in ARMS:
            row = next((item for item in collectors[arm]["receipt"]["outputs"] if item.get("channel") == channel
                        and item.get("actual_start") == 1 and item.get("actual_end") == 180), None)
            if row is None:
                raise ValueError(f"{arm}: first-call return state is missing: {field}")
            path = collectors[arm]["directory"] / row["path"]
            if path.is_symlink() or path.stat().st_size != row["size_bytes"] or sha(path) != row["sha256"]:
                raise ValueError(f"{arm}: first-call return state file differs from receipt: {field}")
            with np.load(path, allow_pickle=False) as archive:
                values = archive["native_values"]
                if (not np.array_equal(archive["actual_timestep"], np.arange(1, 181))
                        or not np.array_equal(archive["native_column_ids"].astype(str), native_ids)
                        or values.shape != (180, 39, 381) or values.dtype != np.float32
                        or not np.isfinite(values[0]).all()):
                    raise ValueError(f"{arm}: invalid first-call return state: {field}")
                streams[arm] = values[0].copy()
            files[arm] = {"path": row["path"], "sha256": row["sha256"], "size_bytes": row["size_bytes"]}
        delta = streams["FIX"].astype(np.float64) - streams["OLD"].astype(np.float64)
        return_differences[field] = {"mismatch_count": int(np.count_nonzero(delta)),
                                     "max_absolute_difference": float(np.max(np.abs(delta)))}
        return_files[field] = files

    per_arm_first_rain = {}
    for arm in ARMS:
        baseline, _ = read_history(histories[arm][12], 12, native_i, native_j)
        previous = baseline.astype(np.float64)
        earliest = None
        max_abs = None
        max_cell = None
        for index, values in enumerate(surface[arm]):
            current = values.astype(np.float64)
            delta = current - previous
            if earliest is None and np.any(delta != 0.0):
                earliest = index + 1
                max_abs = float(np.max(np.abs(delta)))
                max_cell = int(np.argmax(np.abs(delta)))
            previous = current
        per_arm_first_rain[arm] = {"earliest_step_with_nonzero_selected_RAINNC_increment": earliest,
                                   "max_abs_increment_at_that_step_mm": max_abs,
                                   "native_column_id_at_max_abs_increment": native_ids[max_cell] if max_cell is not None else None}

    cumulative_divergence = None
    cumulative_max = None
    for index, (old, fix) in enumerate(zip(surface["OLD"], surface["FIX"])):
        unequal = old.view(np.uint32) != fix.view(np.uint32)
        if unequal.any():
            cumulative_divergence = index + 1
            cumulative_max = float(np.max(np.abs(fix.astype(np.float64) - old.astype(np.float64))))
            break
    return {"schema": "cp02_protected_process_first_call_boundaries_v1",
            "scope": "381 selected native columns × 39 levels; exact selected columns only",
            "entry_call_step": 1,
            "entry_fields": entry_comparison,
            "all_16_entry_fields_bitwise_identical": True,
            "entry_surface_rain_cumulative_bitwise_identical": entry_surface_equal,
            "first_call_surface_rain_inputs": surface_files,
            "first_call_entry_state_inputs": first_files,
            "first_call_return_state_inputs": return_files,
            "first_call_return_state_old_fix_differences": return_differences,
            "first_call_native_RAINNC_increment": per_arm_first_rain,
            "earliest_step_with_any_old_fix_cumulative_RAINNC_difference": cumulative_divergence,
            "max_abs_old_fix_cumulative_RAINNC_difference_at_first_divergence_mm": cumulative_max,
            "interpretation_limit": "Source-order boundary evidence only; it does not attribute later precipitation differences causally to a particular process."}


def run(expected_full_run_sha256: str, output_dir: Path,
        capture_root: Path = DEFAULT_CAPTURE, boundary_output: Path = DEFAULT_BOUNDARY_OUTPUT) -> dict:
    if os.path.lexists(output_dir) or os.path.lexists(boundary_output):
        raise FileExistsError(output_dir if os.path.lexists(output_dir) else boundary_output)
    require_pin(BUNDLE / "native/schema/cp05_schema.json", SCHEMA_SHA256)
    require_pin(BUNDLE / "native/source/source_generation_receipt.json", SOURCE_RECEIPT_SHA256)
    require_pin(BUNDLE / "cohorts/receipt.json", COHORT_RECEIPT_SHA256)
    require_pin(BUNDLE / "cohorts/point_corners.csv", POINT_CORNERS_SHA256)
    require_pin(BUNDLE / "cohorts/unique_global_corners.csv", UNIQUE_CORNERS_SHA256)
    require_pin(BUNDLE / "cohorts/selected_points.csv", SELECTED_POINTS_SHA256)
    run_path = RUNTIME / "full_run_receipt.json"
    run_receipt, histories = verify_full_run(run_path, expected_full_run_sha256)
    collectors = {}
    for arm in ARMS:
        receipt, surface_paths = verify_collector(arm, expected_full_run_sha256, capture_root)
        collectors[arm] = {"receipt": receipt, "receipt_path": capture_root / arm / "capture_receipt.json",
                           "directory": capture_root / arm,
                           "surface_paths": surface_paths}
    _, weak_arrays, _ = verify_array_sources()
    selected = read_csv(BUNDLE / "cohorts/selected_points.csv")
    point_corners = read_csv(BUNDLE / "cohorts/point_corners.csv")
    native_map = read_csv(BUNDLE / "cohorts/unique_global_corners.csv")
    rows, diagnostics, packet = build_rows(run_receipt, histories, collectors, weak_arrays, selected, point_corners, native_map)
    boundaries = first_call_boundaries(histories, collectors, native_map)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".surface-reconciliation-", dir=output_dir.parent))
    try:
        table = stage / "point_hourly_surface_components.csv"
        with table.open("x", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        packet_path = stage / "surface_reconciliation_packet.npz"
        with packet_path.open("xb") as stream:
            np.savez_compressed(stream, **packet)
        boundary_file = stage / "first_call_boundaries.json"
        boundary_file.write_text(json.dumps(boundaries, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        output = {table.name: {"sha256": sha(table), "size_bytes": table.stat().st_size},
                  packet_path.name: {"sha256": sha(packet_path), "size_bytes": packet_path.stat().st_size},
                  boundary_file.name: {"sha256": sha(boundary_file), "size_bytes": boundary_file.stat().st_size}}
        receipt = {"schema": "cp02_protected_process_surface_reconciliation_v1",
                   "status": "PASS_SURFACE_HISTORY_AND_FROZEN_ARRAY_RECONCILIATION",
                   "producer_sha256": sha(Path(__file__)),
                   "full_science_scope": "150 selected points × five forecast-hour windows × two actual arms; component increments are hourly history differences at native corners, promoted to float64 before bilinear interpolation.",
                   "full_run_receipt_sha256": sha(run_path), "full_run_history_status": "PASS_ALL_12_ARM_HOUR_COMPARISONS",
                   "capture_root": str(capture_root),
                   "quick_plan_sha256": QUICK_PLAN_SHA256, "capture_plan_sha256": CAPTURE_PLAN_SHA256,
                   "schema_sha256": SCHEMA_SHA256, "source_generation_receipt_sha256": SOURCE_RECEIPT_SHA256,
                   "cohort_receipt_sha256": COHORT_RECEIPT_SHA256,
                   "collector_receipt_sha256": {arm: sha(collectors[arm]["receipt_path"]) for arm in ARMS},
                   "collector_tool_sha256": {arm: collectors[arm]["receipt"]["tool_sha256"] for arm in ARMS},
                   "frozen_score_analysis_plan_sha256": ANALYSIS_PLAN_SHA256,
                   "frozen_score_array_receipt_sha256": {
                       "weak_strong": sha(WEAK_ANALYSIS / "receipt.json"),
                       "grouped": sha(GROUPED_ANALYSIS / "receipt.json")},
                   "native_surface_endpoint_checks": diagnostics["surface_rain_vs_history_RAINNC"],
                   "surface_channel_inputs": diagnostics["surface_channel_file_pins"],
                   "history_input_sha256": {arm: {str(hour): sha(path) for hour, path in histories[arm].items()} for arm in ARMS},
                   "portable_packet": {"path": packet_path.name, "sha256": sha(packet_path),
                                       "size_bytes": packet_path.stat().st_size,
                                       "native_columns": 381, "history_endpoints_per_arm": 6,
                                       "selected_points": 150, "point_corner_shape": [150, 4]},
                   "score_array_comparison": {"population_per_arm": 150, "lead_hours": list(LEADS),
                                              "frozen_cases": ARMS, "value": "hourly total (RAINNC + RAINC), not 0-to-lead cumulative",
                                              "absolute_tolerance_mm": 1e-12,
                                              "diagnostics": diagnostics["hourly_total_vs_frozen_3688_score_arrays"]},
                   "output": output,
                   "limits": ["KDM6 cumulative surface rain is compared with RAINNC only; RAINC is retained as a separate convective history component.",
                              "The hourly table is derived from actual full-run histories and checked against frozen X/A score arrays.",
                              "This is a selected-point precipitation-component reconciliation, not a full-grid closure or causal source attribution."]}
        (stage / "surface_reconciliation_receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        packet_receipt = {"schema": "cp02_protected_process_surface_packet_v1",
                          "status": "PASS_PACKET_EXTRACTED_FROM_VALIDATED_HISTORY_AND_FROZEN_SCORE_ARRAYS",
                          "producer_sha256": sha(Path(__file__)),
                          "packet": packet_path.name, "packet_sha256": sha(packet_path),
                          "packet_size_bytes": packet_path.stat().st_size,
                          "reference_table": table.name, "reference_table_sha256": sha(table),
                          "reference_table_size_bytes": table.stat().st_size,
                          "full_run_receipt_sha256": sha(run_path),
                          "collector_receipt_sha256": {arm: sha(collectors[arm]["receipt_path"]) for arm in ARMS},
                          "collector_tool_sha256": {arm: collectors[arm]["receipt"]["tool_sha256"] for arm in ARMS},
                          "history_input_sha256": {arm: {str(hour): sha(path) for hour, path in histories[arm].items()} for arm in ARMS},
                          "native_surface_endpoint_checks": diagnostics["surface_rain_vs_history_RAINNC"],
                          "cohort_inputs": {"cohort_receipt_sha256": COHORT_RECEIPT_SHA256,
                                            "selected_points_sha256": SELECTED_POINTS_SHA256,
                                            "point_corners_sha256": POINT_CORNERS_SHA256,
                                            "unique_global_corners_sha256": UNIQUE_CORNERS_SHA256},
                          "frozen_score_inputs": {"analysis_plan_sha256": ANALYSIS_PLAN_SHA256,
                                                  "weak_strong_receipt_sha256": sha(WEAK_ANALYSIS / "receipt.json"),
                                                  "grouped_receipt_sha256": sha(GROUPED_ANALYSIS / "receipt.json")},
                          "contents": {"history_hours_utc": list(HISTORY_HOURS), "native_columns": 381,
                                       "arm_count": 2, "points": 150, "corners_per_point": 4,
                                       "forecast_hours": list(LEADS), "RAINNC_and_RAINC_dtype": "float32",
                                       "point_weights_dtype": "float64", "frozen_score_values_included": True},
                          "limits": ["The packet carries selected endpoint values and frozen score samples; it does not contain NetCDF files or replace validation of their hashes/timestamps.",
                                     "Hourly components are reconstructed from float32 history endpoints after promotion to float64, then bilinearly interpolated.",
                                     "This is selected-point surface reconciliation, not full-grid closure or causal attribution."]}
        (stage / "surface_reconciliation_packet_receipt.json").write_text(json.dumps(packet_receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        output_dir.mkdir(exist_ok=False)
        os.replace(table, output_dir / table.name)
        os.replace(packet_path, output_dir / packet_path.name)
        os.replace(stage / "surface_reconciliation_packet_receipt.json", output_dir / "surface_reconciliation_packet_receipt.json")
        os.replace(boundary_file, boundary_output)
        os.replace(stage / "surface_reconciliation_receipt.json", output_dir / "surface_reconciliation_receipt.json")
    finally:
        if stage.exists():
            import shutil
            shutil.rmtree(stage)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full-run-receipt-sha256", required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--capture-root", type=Path, default=DEFAULT_CAPTURE)
    parser.add_argument("--first-call-output", type=Path, default=DEFAULT_BOUNDARY_OUTPUT)
    args = parser.parse_args()
    result = run(args.full_run_receipt_sha256, args.output_dir, args.capture_root, args.first_call_output)
    print(json.dumps({"status": result["status"], "output": result["output"]}, sort_keys=True))


if __name__ == "__main__":
    main()
