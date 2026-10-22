from pathlib import Path
import sys
import tempfile

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from pr99_candidate_store_reducer import reduce_graupel, reduce_public_store


BOUNDS = {"its": 5, "ite": 5, "jts": 7, "jte": 7, "kts": 1, "kte": 1}


def test_public_store_rows_are_weighted_with_emitted_geometry_and_area() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "public.raw"
        path.write_text(
            "PR87_RAIN_PUBLIC_STORE 1 7 5 1 2 "
            "0.25 4 4 0.5 5 2 3 0.25 0 0\n"
        )
        report, columns, counts = reduce_public_store(path, BOUNDS, np.array([[11.0]]))
        assert report["rows"] == 1
        assert report["rows_by_kind"]["PR87_RAIN_PUBLIC_STORE"] == 1
        assert counts[0, 0] == 1
        assert columns[0, 0] == pytest.approx(16.5)
        assert report["combined"]["largest_positive"] == {"i": 5, "j": 7, "kg": pytest.approx(16.5)}


def test_adjustment_zero_cannot_hide_a_public_q_change() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "public.raw"
        path.write_text(
            "PR87_RAIN_PUBLIC_STORE 1 7 5 1 0 "
            "0.25 4 4 0.5 5 2 3 0.25 0 0\n"
        )
        with pytest.raises(ValueError, match="adjustment-zero Q changed"):
            reduce_public_store(path, BOUNDS, np.array([[11.0]]))


def test_public_q_delta_must_match_emitted_r32_endpoints() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "public.raw"
        path.write_text(
            "PR87_RAIN_PUBLIC_STORE 1 7 5 1 2 "
            "0.25 4 4 0.5 5 2 3 0.5 0 0\n"
        )
        with pytest.raises(ValueError, match="Q delta differs from emitted endpoints"):
            reduce_public_store(path, BOUNDS, np.array([[11.0]]))


def test_graupel_residual_is_column_stored_delta_plus_ground_flux() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "graupel.raw"
        values = [0.375, 0.25, 0.125, 0.0, 0.0, 0.0, 0.125, 0.0, 0.25, 0.0, 0.375, 0.0]
        path.write_text("# PR85_G_SED: fixture\nPR85_G_SED 5 7 1 1 " +
                        " ".join(map(str, values)) + "\n")
        report, columns, events = reduce_graupel(path, BOUNDS, np.array([[3.0]]))
        assert report["rows"] == report["columns"] == 1
        assert report["event_rows_cover_all_active_columns_and_contiguous_substeps"]
        assert columns[0, 0] == pytest.approx(1.125)
        assert events[0, 0] == 1


def test_graupel_residual_must_match_exact_source_addition() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "graupel.raw"
        values = [0.375, 0.25, 0.125, 0.0, 0.0, 0.0, 0.125, 0.0, 0.25, 0.0,
                  "0.37500000000000006", 0.0]
        path.write_text("# PR85_G_SED: fixture\nPR85_G_SED 5 7 1 1 " +
                        " ".join(map(str, values)) + "\n")
        with pytest.raises(ValueError, match="source residual identity failed"):
            reduce_graupel(path, BOUNDS, np.array([[3.0]]))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
