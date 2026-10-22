from __future__ import annotations

import numpy as np
import pytest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from pr98_budget import cutoff_columns


def cutoff_row(i: int = 4, j: int = 7, k: int = 2, loop: int = 1,
               mask: int = 29) -> str:
    before = [5e-16, 2e-15, 5e-10, 0.0, 0.0]
    after = [0.0, 2e-15, 0.0, 0.0, 0.0]
    rest = [2.0, 1e-15, 1e-9, *before, *after,
            1.0, 1.0, 2.0, 2.0, 3.0, 3.0,
            0.0, 0.0, 280.0, 280.0, 0.01, 0.01, 0, 0]
    return "PR85_KDM6_CUTOFF " + " ".join(map(str, [i, j, k, loop, mask, *rest])) + "\n"


def test_cutoff_columns_reduces_actual_q_change_with_fixed_call_measure(tmp_path):
    path = tmp_path / "cutoff.raw"
    path.write_text(cutoff_row())
    bounds = {"its": 4, "ite": 4, "jts": 7, "jte": 7, "kts": 2, "kte": 2}
    density = np.full((1, 1, 1), 2.0)
    thickness = np.full((1, 1, 1), 3.0)
    area = np.full((1, 1), 5.0)

    values, counts, rows, by_species = cutoff_columns(path, bounds, density, thickness, area)

    assert rows == 1
    assert counts.tolist() == [[1]]
    assert values[0, 0] == pytest.approx(-1.5000015e-8)
    assert by_species[:, 0, 0].tolist() == pytest.approx([-1.5e-14, 0, -1.5e-8, 0, 0])


def test_cutoff_columns_rejects_duplicate_event_key(tmp_path):
    path = tmp_path / "cutoff.raw"
    row = cutoff_row()
    path.write_text(row + row)
    bounds = {"its": 4, "ite": 4, "jts": 7, "jte": 7, "kts": 2, "kte": 2}
    ones = np.ones((1, 1, 1))

    with pytest.raises(ValueError, match="duplicate cutoff event"):
        cutoff_columns(path, bounds, ones, ones, ones[:, 0, :])


def test_cutoff_columns_rejects_wrong_geometry_shape(tmp_path):
    path = tmp_path / "cutoff.raw"
    path.write_text(cutoff_row())
    bounds = {"its": 4, "ite": 4, "jts": 7, "jte": 7, "kts": 2, "kte": 2}

    with pytest.raises(ValueError, match="geometry"):
        cutoff_columns(path, bounds, np.ones((2, 1, 1)), np.ones((1, 1, 1)), np.ones((1, 1)))


@pytest.mark.parametrize("edit, message", [
    (lambda row: row.replace(" 29 ", " 0 ", 1), "threshold mask"),
    (lambda row: row.replace("0.0 2e-15", "5e-16 2e-15", 1), "did not clear"),
    (lambda row: row.rsplit(" ", 1)[0] + "\n", "record width"),
])
def test_cutoff_columns_rejects_malformed_store_evidence(tmp_path, edit, message):
    path = tmp_path / "cutoff.raw"
    path.write_text(edit(cutoff_row()))
    bounds = {"its": 4, "ite": 4, "jts": 7, "jte": 7, "kts": 2, "kte": 2}
    ones = np.ones((1, 1, 1))

    with pytest.raises(ValueError, match=message):
        cutoff_columns(path, bounds, ones, ones, ones[:, 0, :])


def test_cutoff_columns_rejects_change_above_threshold(tmp_path):
    path = tmp_path / "cutoff.raw"
    row = cutoff_row().replace("5e-16 2e-15", "5e-16 2.5e-15", 1)
    path.write_text(row)
    bounds = {"its": 4, "ite": 4, "jts": 7, "jte": 7, "kts": 2, "kte": 2}
    ones = np.ones((1, 1, 1))

    with pytest.raises(ValueError, match="above its threshold"):
        cutoff_columns(path, bounds, ones, ones, ones[:, 0, :])
