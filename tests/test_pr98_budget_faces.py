from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from pr98_budget_faces import compact_face_rows, face_rows


BOUNDS = {"its": 4, "ite": 4, "jts": 7, "jte": 7, "kts": 1, "kte": 2}


def source_row(prefix: str, i: int, j: int, substep: int, nlevels: int,
               stored_q: float, ground_q: float, residual_q: float) -> str:
    values = [0.5, 0.5, 0, 0, 0, 0, ground_q, 0,
              stored_q, 0, residual_q, 0]
    return " ".join(map(str, [prefix, i, j, substep, nlevels, *values])) + "\n"


def face_row(donor: int, receiver: int, has_receiver: int, before: float, after: float,
             receiver_before: float = 0.0, receiver_after: float = 0.0) -> str:
    values = [1.0, 0.5, before, after, 2.0, 3.0,
              receiver_before, receiver_after, 2.0 if has_receiver else 0.0,
              3.0 if has_receiver else 0.0]
    return " ".join(map(str, ["PR98_SED_FACE", 4, 7, 1, 3, donor, receiver,
                               has_receiver, *values])) + "\n"


def test_selected_faces_reconcile_actual_packet_donor_receiver_and_ground(tmp_path):
    faces = tmp_path / "faces.raw"
    rain = tmp_path / "rain.raw"
    ice = tmp_path / "ice.raw"
    faces.write_text(face_row(2, 1, 1, 1.0, 0.75, 2.0, 2.25) +
                     face_row(1, 0, 0, 0.25, 0.0))
    rain.write_text(source_row("PR87_RAIN_SED", 4, 7, 1, 2, -0.5, 0.5, -1.0))
    ice.write_text("")

    result = face_rows(faces, BOUNDS, np.full((1, 2, 1), 2.0),
                       np.full((1, 2, 1), 3.0), np.array([[5.0]]), rain, ice)
    assert result["accepted_face_capture_counts_by_mode"]["rain"] == {
        "captured_accepted_face_records": 2, "nonzero_approved_packets": 2,
        "positive_approved_packets": 2, "negative_approved_packets": 0,
        "zero_approved_packets": 0}
    term = result["selected_columns"]["4,7"]["rain"]
    assert term["accepted_face_records"] == 2
    assert term["approved_packet_kg"] == pytest.approx(5.0)
    assert term["donor_store_packet_discrepancy_kg"] == pytest.approx(-10.0)
    assert term["receiver_store_packet_discrepancy_kg"] == pytest.approx(5.0)
    assert term["net_source_face_discrepancy_kg"] == pytest.approx(-5.0)


def test_selected_faces_reject_duplicate_or_truncated_events(tmp_path):
    rain = tmp_path / "rain.raw"
    ice = tmp_path / "ice.raw"
    rain.write_text(source_row("PR87_RAIN_SED", 4, 7, 1, 2, -0.5, 0.5, -1.0))
    ice.write_text("")
    row = face_row(2, 1, 1, 1.0, 0.75, 2.0, 2.25)
    args = (BOUNDS, np.full((1, 2, 1), 2.0), np.full((1, 2, 1), 3.0),
            np.array([[5.0]]), rain, ice)
    duplicate = tmp_path / "duplicate.raw"
    duplicate.write_text(row + row + face_row(1, 0, 0, 0.25, 0.0))
    with pytest.raises(ValueError, match="duplicate"):
        face_rows(duplicate, *args)
    truncated = tmp_path / "truncated.raw"
    truncated.write_text(" ".join(row.split()[:-1]) + "\n")
    with pytest.raises(ValueError, match="width"):
        face_rows(truncated, *args)


def test_compact_faces_match_every_source_substep(tmp_path):
    path = tmp_path / "ice.raw"
    values = [0.5, 0.5, 0.01, 0.0, 0.01, -0.49, 0.5, 0.49, 0.02, 0.01]
    compact = " ".join(map(str, ["PR98_SED_FACE_SUM", 4, 7, 1, 1, 1, 1, *values])) + "\n"
    path.write_text(source_row("PR85_ICE_SED", 4, 7, 1, 1, -0.49, 0.5, 0.01) + compact)
    values, counts, report = compact_face_rows(path, path, "PR98_SED_FACE_SUM", 1,
                                               BOUNDS, np.array([[2.0]]))
    np.testing.assert_allclose(values, np.array([[0.02]]), rtol=0, atol=1e-15)
    assert counts.tolist() == [[1]]
    assert report["accepted_face_records"] == 1
    assert report["nonzero_approved_packet_records"] == 1
    assert report["L1_face_event_kg"] == pytest.approx(0.04)
    assert report["max_abs_face_event_kg"] == pytest.approx(0.02)
    assert report["net_discrepancy"]["signed_kg"] == pytest.approx(0.02)


@pytest.mark.parametrize("extra, message", [
    (" ".join(["PR98_SED_FACE_SUM", "4", "7", "1", "1", "1", "1", *map(str, [0.5, 0.5, 0.01, 0.0, 0.01, -0.49, 0.5, 0.49, 0.02, 0.01])]) + "\n" +
     " ".join(["PR98_SED_FACE_SUM", "4", "7", "1", "1", "1", "1", *map(str, [0.5, 0.5, 0.01, 0.0, 0.01, -0.49, 0.5, 0.49, 0.02, 0.01])]) + "\n", "duplicate"),
    ("PR98_SED_FACE_SUM 4 7 1 1 1 1 0.5 0.5 0.01 0 0.01 -0.49 0.5\n", "width"),
    ("PR98_SED_FACE_SUM 4 7 1 1 1 1 0.5 0.5 0.01 0 nan -0.49 0.5 0.49 0.02 0.01\n", "finite"),
])
def test_compact_faces_reject_bad_rows(tmp_path, extra, message):
    path = tmp_path / "ice.raw"
    path.write_text(source_row("PR85_ICE_SED", 4, 7, 1, 1, -0.49, 0.5, 0.01) + extra)
    with pytest.raises(ValueError, match=message):
        compact_face_rows(path, path, "PR98_SED_FACE_SUM", 1, BOUNDS, np.array([[2.0]]))
