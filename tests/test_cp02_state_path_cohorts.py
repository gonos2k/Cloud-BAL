from __future__ import annotations

import csv
import gzip
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "tools/cp02_state_path_cohorts.py"
SPEC = importlib.util.spec_from_file_location("cp02_state_path_cohorts", SCRIPT)
cp02 = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(cp02)


def sample_arrays():
    size = 3688
    arrays = {
        "reference": np.zeros(size, dtype=np.float64),
        "ORIGINAL_B1_100": np.zeros(size, dtype=np.float64),
        "IMPROVED_BG_FIXED": np.zeros(size, dtype=np.float64),
        "flat_index_yx": np.arange(size, dtype=np.int64),
        "latitude": np.linspace(30, 40, size),
        "longitude": np.linspace(120, 130, size),
    }
    for i in (582, 899, 1870):
        arrays["ORIGINAL_B1_100"][i] = 6.0
    arrays["IMPROVED_BG_FIXED"][1772] = 6.0
    return arrays


def test_array_guards_reject_missing_short_and_duplicate_samples():
    valid = sample_arrays()
    cp02.validate_arrays(valid, "valid")

    with pytest.raises(ValueError, match="missing required fields"):
        cp02.validate_arrays({key: value for key, value in valid.items() if key != "reference"}, "missing")

    short = {key: value.copy() for key, value in valid.items()}
    short["reference"] = short["reference"][:-1]
    with pytest.raises(ValueError, match="3688 rows"):
        cp02.validate_arrays(short, "short")

    duplicate = {key: value.copy() for key, value in valid.items()}
    duplicate["flat_index_yx"][1] = duplicate["flat_index_yx"][0]
    with pytest.raises(ValueError, match="duplicate RN1 flat indices"):
        cp02.validate_arrays(duplicate, "duplicate")


def test_full_sample_threshold_recount_includes_all_transitions():
    arrays = sample_arrays()
    row = cp02.threshold_counts(arrays["reference"], arrays["ORIGINAL_B1_100"], arrays["IMPROVED_BG_FIXED"], 5.0)
    assert row["n"] == 3688
    assert (row["OLD_false_alarm"], row["FIX_false_alarm"]) == (3, 1)
    assert row["fa_old_only"] == 3
    assert row["fa_fix_only"] == 1
    assert row["fa_neither"] == 3684


def test_recalc_scores_has_six_thresholds_at_both_leads(tmp_path):
    arrays = sample_arrays()
    for hour in (13, 14):
        np.savez(tmp_path / f"hour_{hour}_arrays.npz", **arrays)
    rows, loaded = cp02.recalc_scores(tmp_path)
    assert len(loaded) == 2
    assert [(row["lead_hour"], row["threshold_mm"]) for row in rows] == [
        (lead, threshold) for lead in (1, 2) for threshold in cp02.THRESHOLDS
    ]


def test_cohorts_preserve_old_ids_and_add_explicit_transition_indices(tmp_path):
    old = tmp_path / "old.csv"
    with old.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=("point_id", "rn1_sample_index_zero_based", "target_flat_index_yx", "latitude", "longitude"))
        writer.writeheader()
        for point_id, i in zip(("P01", "P02", "P03", "P04"), (1, 2, 3, 4)):
            writer.writerow({"point_id": point_id, "rn1_sample_index_zero_based": i,
                             "target_flat_index_yx": i, "latitude": 35 + i / 1000, "longitude": 127 + i / 1000})
    arrays = sample_arrays()
    points = cp02.cohorts({2: arrays}, old)
    assert [point["point_id"] for point in points] == ["P01", "P02", "P03", "P04", "FA01", "FA02", "FA03", "FA04"]
    assert [point["rn1_sample_index_zero_based"] for point in points[4:]] == [582, 899, 1870, 1772]

    arrays["IMPROVED_BG_FIXED"][582] = 5.0
    with pytest.raises(ValueError, match="no longer matches declared threshold-5 transition"):
        cp02.cohorts({2: arrays}, old)


def test_corner_contract_requires_all_four_corners_and_32_unique_cells():
    points = [{"point_id": f"P{i}"} for i in range(8)]
    rows = []
    for point_number, point in enumerate(points):
        for corner_number, corner in enumerate(("00", "10", "01", "11")):
            cell = point_number * 4 + corner_number
            rows.append({"point_id": point["point_id"], "corner": corner,
                         "native_j_zero_based": 100 + cell, "native_i_zero_based": 200 + cell})
    cp02.validate_corner_contract(points, rows)

    with pytest.raises(ValueError, match="exactly four corners"):
        cp02.validate_corner_contract(points, rows[:-1])

    duplicate = [dict(row) for row in rows]
    duplicate[-1]["native_j_zero_based"] = duplicate[0]["native_j_zero_based"]
    duplicate[-1]["native_i_zero_based"] = duplicate[0]["native_i_zero_based"]
    with pytest.raises(ValueError, match="native corner cell repeats"):
        cp02.validate_corner_contract(points, duplicate)


def _write_gzip_csv(path: Path, fieldnames, rows):
    with gzip.open(path, "wt", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _event_state_fixture(tmp_path: Path, p01_count: int = 190, omit_state: bool = False):
    keys = ("point_id", "corner", "source_file", "rank", "call_id", "itimestep", "loop", "j", "i", "k")
    events, steps = [], []
    for n in range(p01_count):
        key = {"point_id": "P01", "corner": "00", "source_file": "raw.gz", "rank": "3", "call_id": "1",
               "itimestep": str(n + 1), "loop": "1", "j": "10", "i": "20", "k": "8"}
        events.append({**key, "weight": "1", "hour": "1", "raw_class": "negative_zero", "raw_prev": "-0.0",
                       "sat_cap_prev": "-1e-8", "process_prev": "-1e-12"})
        if not (omit_state and n == 0):
            steps.append({**key, "arm": "OLD", "q_pre": "0.01", "q_post": "0.01", "t_pre": "290", "t_post": "290",
                          "dtcld": "1", "qr_pre": "1e-8", "qr_post": "0"})
    key = {"point_id": "P02", "corner": "00", "source_file": "raw.gz", "rank": "3", "call_id": "2",
           "itimestep": "1", "loop": "1", "j": "11", "i": "21", "k": "8"}
    events.append({**key, "weight": "1", "hour": "2", "raw_class": "positive_zero", "raw_prev": "0.0",
                   "sat_cap_prev": "0.0", "process_prev": "1e-12"})
    steps.append({**key, "arm": "OLD", "q_pre": "0.02", "q_post": "0.02", "t_pre": "291", "t_post": "291",
                  "dtcld": "2", "qr_pre": "1e-8", "qr_post": "1e-8"})
    _write_gzip_csv(tmp_path / "old_zero_rate_events.csv.gz", (*keys, "weight", "hour", "raw_class", "raw_prev", "sat_cap_prev", "process_prev"), events)
    _write_gzip_csv(tmp_path / "old_cell_steps.csv.gz", (*keys, "arm", "q_pre", "q_post", "t_pre", "t_post", "dtcld", "qr_pre", "qr_post"), steps)


def test_zero_raw_state_paths_validate_p01_and_integrate_p02_k8(tmp_path):
    _event_state_fixture(tmp_path)
    rows, summary = cp02.zero_rate_state_paths(tmp_path)
    assert len(rows) == 191
    p01 = summary["P01_negative_zero_raw_final_process"]
    assert p01["events"] == 190
    assert p01["q_state_change_nonzero_events"] == 0
    assert p01["T_state_change_nonzero_events"] == 0
    assert p01["sum_process_prev_dtcld"] == pytest.approx(-190e-12)
    assert summary["P02_k8_all_raw_zero_events"]["bilinear_weighted_sum_process_prev_dtcld"] == pytest.approx(2e-12)


def test_zero_raw_join_rejects_missing_state_and_wrong_event_count(tmp_path):
    _event_state_fixture(tmp_path, omit_state=True)
    with pytest.raises(ValueError, match="no matched OLD state"):
        cp02.zero_rate_state_paths(tmp_path)

    _event_state_fixture(tmp_path, p01_count=189)
    with pytest.raises(ValueError, match="unexpected frozen zero-event counts"):
        cp02.zero_rate_state_paths(tmp_path)
