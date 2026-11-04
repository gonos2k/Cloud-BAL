from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("rain_cohorts", ROOT / "tools/cp02_rain_number_process_cohorts.py")
cohorts = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(cohorts)


def test_real_cohorts_use_ranked_disjoint_stencils():
    arrays = cohorts.load_arrays()
    a = arrays[3]
    mapping = np.load(cohorts.MAPPING_ARRAY, allow_pickle=False)
    selected = cohorts.select_indices(arrays)
    assert [row[2] for row in selected] == [476, 819, 1870, 623, 575, 10, 2360, 1108, 281]

    obs, b1, candidate = a["reference"], a["IMPROVED_BG_FIXED"], a["B1_RAIN_NUMBER_PRIOR"]
    masks = [
        (obs >= .1) & (obs < 1) & (b1 >= .1) & (candidate < .1),
        (obs >= .1) & (obs < 1) & (b1 >= .5) & (candidate < .5),
        (obs >= 1) & (obs < 5) & (b1 >= .5) & (candidate < .5),
        (obs < .1) & (b1 < .1) & (candidate >= .1),
        (obs >= 1) & (obs < 5) & (b1 < 5) & (candidate >= 5),
        (obs >= 5) & (b1 >= 5) & (candidate >= 5),
    ]
    occupied = set()
    for _, _, index, _ in selected[:3]:
        cells = cohorts.map_stencil(index, a, mapping)
        assert occupied.isdisjoint(cells)
        occupied.update(cells)
    for (_, _, index, _), mask in zip(selected[3:], masks):
        ordered = sorted(np.flatnonzero(mask), key=lambda i: (-abs(candidate[i] - b1[i]), int(a["flat_index_yx"][i])))
        expected = next(i for i in ordered if cohorts.map_stencil(i, a, mapping).isdisjoint(occupied))
        assert index == expected
        if index == 575:
            assert ordered[:3] == [574, 575, 2666]
            assert cohorts.map_stencil(574, a, mapping) & occupied == {(81, 139)}
        occupied.update(cohorts.map_stencil(index, a, mapping))
    assert len(occupied) == 36


def test_equal_scores_use_lowest_flat_index(monkeypatch):
    arrays = {"flat_index_yx": np.array([9, 2, 7])}
    monkeypatch.setattr(cohorts, "map_stencil", lambda index, arrays, mapping: {(index, 0)})
    assert cohorts.choose_index(arrays, None, np.ones(3, dtype=bool), set(), np.ones(3)) == 1
    assert cohorts.choose_index(arrays, None, np.ones(3, dtype=bool), {(1, 0)}, np.ones(3)) == 2
    with pytest.raises(ValueError, match="no eligible"):
        cohorts.choose_index(arrays, None, np.ones(3, dtype=bool), {(0, 0), (1, 0), (2, 0)}, np.ones(3))


def test_transition_table_covers_all_leads_thresholds_and_cases():
    arrays = cohorts.load_arrays()
    points = cohorts.make_points(arrays)
    rows = cohorts.transition_rows(arrays, points)
    assert len(rows) == 9 * 6 * 6 * 3
    assert len({(r["point_id"], r["lead_hour"], r["threshold_mm"], r["case"]) for r in rows}) == len(rows)
    p01 = {(r["lead_hour"], r["case"]): r["transition"] for r in rows if r["point_id"] == "P01" and r["threshold_mm"] == .1}
    assert (p01[2, "B1"], p01[2, "B1_RAIN_NUMBER_PRIOR"]) == ("miss", "hit")
    assert (p01[3, "B1"], p01[3, "B1_RAIN_NUMBER_PRIOR"]) == ("hit", "miss")


def test_frozen_artifacts_match_transition_recount_and_reviewed_cells(tmp_path):
    import json

    output = ROOT / "docs/evidence/cp02_rain_number_process_20261104/newcohorts"
    arrays = cohorts.load_arrays()
    rows = cohorts.transition_rows(arrays, cohorts.make_points(arrays))
    recount = tmp_path / "point_transitions.csv"
    cohorts.write_csv(recount, rows)
    assert recount.read_bytes() == (output / "point_transitions.csv").read_bytes()
    assert cohorts.sha256(output / "point_corners.csv") == "aa5da1ef6cdb8773addb139ef4cc385d3ea9e2b9d490368f79fd77086bca4b1b"
    assert cohorts.sha256(output / "unique_global_corners.csv") == "169adba4177e9efcd11d54603a4ce451593c24927b6f8e0a93a2d16480eeddc3"
    receipt = json.loads((output / "mapping_receipt.json").read_text())
    assert receipt["history_geometry"] == {
        "source_shape_yxz": [282, 234, 39],
        "source_interior_j_zero_based_half_open": [1, 281],
        "source_interior_i_zero_based_half_open": [1, 233],
        "source_interior_shape_yx": [280, 232],
    }
    assert receipt["transition_rows"] == 972
    for relative_path, expected_hash in receipt["inputs"].items():
        assert cohorts.sha256(ROOT / relative_path) == expected_hash
