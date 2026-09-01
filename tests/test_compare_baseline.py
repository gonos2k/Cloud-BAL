#!/usr/bin/env python3
"""Contract tests for strict WPS baseline parsing."""

from __future__ import annotations

import struct
import sys
import tempfile
import os
from pathlib import Path

import numpy as np

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))

from compare_baseline import comparison_files, numeric_summary, read_wps  # noqa: E402


def record(payload: bytes) -> bytes:
    marker = struct.pack("<i", len(payload))
    return marker + payload + marker


def field_records(value: float, *, projection_record: bytes = b"projection", wind: int = 1) -> bytes:
    metadata = bytearray(156)
    metadata[0:24] = b"2026-09-01_03:00:00.000"
    metadata[60:69] = b"TT       "
    metadata[69:94] = b"K                        "
    metadata[140:144] = struct.pack("<f", 50000.0)
    metadata[144:156] = struct.pack("<iii", 2, 2, 1)
    slab = np.full(4, value, dtype="<f4").tobytes()
    return b"".join(
        (
            record(struct.pack("<i", 5)),
            record(bytes(metadata)),
            record(projection_record),
            record(struct.pack("<i", wind)),
            record(slab),
        )
    )


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="cloud-bal-compare-") as directory:
        root = Path(directory)
        valid = root / "valid"
        valid.write_bytes(field_records(1.0))
        assert len(read_wps(valid)) == 1

        intel_true = root / "intel_true"
        intel_true.write_bytes(field_records(1.0, wind=-1))
        assert next(iter(read_wps(intel_true).values()))[3][
            "wind_grid_relative"
        ] is True
        summaries = numeric_summary(valid, intel_true)
        assert not any("metadata changed" in summary for summary in summaries)

        wind_changed = root / "wind_changed"
        wind_changed.write_bytes(field_records(1.0, wind=0))
        summaries = numeric_summary(valid, wind_changed)
        assert any("wind_grid_relative" in summary for summary in summaries)

        projection_changed = root / "projection_changed"
        projection_changed.write_bytes(field_records(1.0, projection_record=b"different"))
        summaries = numeric_summary(valid, projection_changed)
        assert any("projection_record_sha256" in summary for summary in summaries)

        duplicate = root / "duplicate"
        duplicate.write_bytes(field_records(1.0) + field_records(2.0))
        try:
            read_wps(duplicate)
        except ValueError as exc:
            assert "duplicate" in str(exc)
        else:
            raise AssertionError("duplicate WPS identity was accepted")

        truncated = root / "truncated"
        truncated.write_bytes(field_records(1.0)[:-3])
        try:
            numeric_summary(valid, truncated)
        except ValueError:
            pass
        else:
            raise AssertionError("changed WPS parse failure was hidden")

        plain_a = root / "a.txt"
        plain_b = root / "b.txt"
        plain_a.write_text("a", encoding="utf-8")
        plain_b.write_text("b", encoding="utf-8")
        assert numeric_summary(plain_a, plain_b) == []

        independent_a = root / "independent_a"
        independent_b = root / "independent_b"
        independent_a.mkdir()
        independent_b.mkdir()
        (independent_a / "product").write_bytes(b"same")
        (independent_b / "product").write_bytes(b"same")
        (independent_a / "nested").mkdir()
        (independent_b / "nested").mkdir()
        (independent_a / "nested" / "README.md").write_text("kept")
        (independent_b / "nested" / "README.md").write_text("kept")
        left_files, right_files = comparison_files(independent_a, independent_b)
        assert Path("nested/README.md") in left_files
        assert Path("nested/README.md") in right_files
        try:
            comparison_files(independent_a, independent_a)
        except ValueError as exc:
            assert "non-overlapping" in str(exc)
        else:
            raise AssertionError("self-comparison was accepted")

        empty_a = root / "empty_a"
        empty_b = root / "empty_b"
        empty_a.mkdir()
        empty_b.mkdir()
        try:
            comparison_files(empty_a, empty_b)
        except ValueError as exc:
            assert "at least one" in str(exc)
        else:
            raise AssertionError("empty comparison was accepted")

        symlink_root = root / "symlink_root"
        symlink_root.mkdir()
        (symlink_root / "product").symlink_to(independent_a / "product")
        try:
            comparison_files(independent_a, symlink_root)
        except ValueError as exc:
            assert "symbolic link" in str(exc)
        else:
            raise AssertionError("symlink candidate was accepted")

        hardlink_root = root / "hardlink_root"
        hardlink_root.mkdir()
        os.link(independent_a / "product", hardlink_root / "product")
        try:
            comparison_files(independent_a, hardlink_root)
        except ValueError as exc:
            assert "multiply-linked" in str(exc)
        else:
            raise AssertionError("hardlink candidate was accepted")

        from netCDF4 import Dataset

        old_nc = root / "old.nc"
        new_nc = root / "new.nc"
        for path, mask in ((old_nc, [False, True, False]),
                           (new_nc, [False, False, True])):
            with Dataset(path, "w") as dataset:
                dataset.createDimension("cell", 3)
                valid_mask = dataset.createVariable(
                    "valid", "i4", ("cell",), fill_value=-999
                )
                valid_mask.units = "1"
                valid_mask[:] = np.ma.array([1, 0, 0], mask=mask, dtype=np.int32)
        summaries = numeric_summary(old_nc, new_nc)
        assert any("valid_mask_changed=2" in summary for summary in summaries)

    print("Cloud-BAL baseline comparator tests passed")


if __name__ == "__main__":
    main()
