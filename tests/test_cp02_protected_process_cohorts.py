from __future__ import annotations

import csv
import importlib.util
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "cp02_protected_process_cohorts", ROOT / "tools/cp02_protected_process_cohorts.py"
)
cohorts = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(cohorts)


def test_categorical_scores_and_transition_masks_are_exact():
    obs = np.array([0.0, 0.2, 0.8, 1.0, 5.0])
    before = np.array([0.1, 0.2, 0.0, 1.2, 4.0])
    after = np.array([0.6, 0.0, 0.9, 1.1, 5.0])

    assert cohorts.categorical_score(obs, after, 0.5) == {
        "n": 5, "hit": 3, "miss": 0, "false_alarm": 1, "correct_negative": 1, "CSI": 0.75
    }
    assert cohorts.transition_counts(obs, before, after, 0.5) == {
        "observed_points": 3, "hit_gains": 1, "hit_losses": 0,
        "new_false_alarms": 1, "resolved_false_alarms": 0
    }


def test_nearest_neighbor_ties_use_smallest_canonical_flat_id():
    values = {"flat_index_yx": np.array([50, 20, 10]), "latitude": np.zeros(3),
              "longitude": np.array([0.0, 1.0, -1.0])}
    target, distance = cohorts.nearest_neighbor(values, 0, np.array([False, True, True]))
    assert target == 2
    assert distance == pytest.approx(cohorts.EARTH_KM * np.pi / 180.0)


def test_native_corner_weights_and_global_cells_are_deduplicated():
    values = {"flat_index_yx": np.arange(3688), "latitude": np.zeros(3688), "longitude": np.zeros(3688)}
    mapping = {"j0": np.zeros((253, 149), dtype=int), "i0": np.zeros((253, 149), dtype=int),
               "u": np.full((253, 149), 0.25), "v": np.full((253, 149), 0.5),
               "valid": np.ones((253, 149), dtype=bool)}
    rows = cohorts.native_corners(values, mapping, [0, 0])
    assert len(rows) == 8
    assert [row["corner"] for row in rows[:4]] == ["00", "10", "01", "11"]
    assert [row["weight"] for row in rows[:4]] == pytest.approx([0.375, 0.125, 0.375, 0.125])
    assert len({(row["native_j_zero_based"], row["native_i_zero_based"]) for row in rows[:4]}) == 4
    assert rows[:4] == rows[4:]
    mapping["valid"][0, 0] = False
    with pytest.raises(ValueError, match="lack a valid"):
        cohorts.native_corners(values, mapping, [0])


def test_full_cohort_export_recounts_roles_and_preserves_corner_contract(tmp_path):
    output = tmp_path / "cohorts"
    receipt = cohorts.run(output)
    expected = {
        "plus2_XA_weak_loss": 10,
        "plus2_OA_weak_loss": 10,
        "plus2_prior_retained_controls": 10,
        "plus2_XA_new_false_alarm": 33,
        "plus2_XA_resolved_false_alarm": 30,
        "plus2_OA_new_false_alarm": 53,
        "plus2_OA_resolved_false_alarm": 24,
        "plus5_C_A_weak_loss": 17,
        "plus5_protected_weak_X_miss_A_hit_C_miss": 11,
        "plus5_remaining_weak_loss_X_hit_A_hit_C_miss": 6,
        "plus5_strong_protected_hit_12299": 1,
        "plus5_C_strong_new_false_alarm": 12,
        "plus5_protected_strong_X_FA_A_resolved_C_FA": 7,
        "plus2_OA_nearest_Awet_RN1zero_neighbor": 4,
    }
    assert {key: receipt["role_counts"][key] for key in expected} == expected
    with (output / "selected_points.csv").open(newline="", encoding="utf-8") as stream:
        points = list(csv.DictReader(stream))
    with (output / "point_corners.csv").open(newline="", encoding="utf-8") as stream:
        corners = list(csv.DictReader(stream))
    with (output / "unique_global_corners.csv").open(newline="", encoding="utf-8") as stream:
        unique = list(csv.DictReader(stream))
    assert len(points) == 150
    assert len(corners) == 4 * len(points) == 600
    assert len(unique) == 381
    assert receipt["point_corner_rows"] - receipt["unique_native_global_corners"] == 219
    assert receipt["full_grid_5km_singleton_count"] == 3688
    assert receipt["oa_zero_rn1_neighbor_flat_ids"] == [8540, 11091, 11092, 11241]
    spatial = receipt["prior_spatial_neighbors"]
    assert spatial["rows_by_radius"] == {"5_km": 1620, "10_km": 1620, "20_km": 1620}
    assert spatial["5_km_self_only_rows"] == 1620
    assert spatial["10_km_neighbor_count_min_median_max"] == [4, 9.0, 9]
    assert spatial["20_km_neighbor_count_min_median_max"] == [13, 45.0, 45]
    by_point = {}
    for row in corners:
        by_point.setdefault(row["point_id"], []).append(row)
    assert set(by_point) == {row["point_id"] for row in points}
    assert all(len(rows) == 4 for rows in by_point.values())
    assert all(sum(float(row["weight"]) for row in rows) == pytest.approx(1.0) for rows in by_point.values())
    assert "plus5_strong_protected_hit_12299" in next(row["roles"] for row in points if row["flat_index_yx"] == "12299")
    assert "plus2_OA_weak_loss" in next(row["roles"] for row in points if row["flat_index_yx"] == "17524")
    assert "plus2_XA_weak_loss" in next(row["roles"] for row in points if row["flat_index_yx"] == "16138")
    assert "plus2_OA_nearest_Awet_RN1zero_neighbor" in next(row["roles"] for row in points if row["flat_index_yx"] == "8540")
    with (output / "qrain_group_summary.csv").open(newline="", encoding="utf-8") as stream:
        qrain = {row["role"]: row for row in csv.DictReader(stream)}
    assert int(qrain["plus2_OA_weak_loss"]["n"]) == 10
    assert float(qrain["plus2_OA_weak_loss"]["median_X_QRAIN_mgkg"]) == pytest.approx(1.5292140838)
    assert float(qrain["plus2_OA_weak_loss"]["median_A_QRAIN_mgkg"]) == pytest.approx(0.0508779597)
    assert float(qrain["plus2_OA_weak_loss"]["median_pointwise_A_minus_X_mgkg"]) == pytest.approx(-0.6927396608)
    assert int(qrain["plus2_prior_retained_controls"]["n"]) == 10
    with (output / "nearest_neighbors.csv").open(newline="", encoding="utf-8") as stream:
        neighbor_rows = list(csv.DictReader(stream))
    assert len(neighbor_rows) == 20
    neighbors = {row["loss_flat_index_yx"]: row for row in neighbor_rows if row["role"] == "plus2_OA_weak_loss"}
    assert {key: neighbors[key]["nearest_A_hit_flat_index_yx"] for key in ("8689", "10942", "10943", "11242")} == {
        "8689": "8540", "10942": "11091", "10943": "11092", "11242": "11241"
    }
    assert all(row["5km_radius_self_only"] == "True" for row in neighbor_rows)
    assert all("A_hit_points_within_10km" in row and "A_hit_points_within_20km" in row for row in neighbor_rows)
    assert (output / "point_corners.csv").read_bytes() == (ROOT / "docs/evidence/cp02_protected_process_20261106/cohorts/point_corners.csv").read_bytes()
    with pytest.raises(FileExistsError):
        cohorts.run(output)
