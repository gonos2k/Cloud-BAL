#!/usr/bin/env python3
"""Tests for WRF axis and timestamp binding in the PR73 native input audit."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from pr73_native_input_pair_audit import _selectors, wrf_valid_time  # noqa: E402


class VariableShape:
    dimensions = ("west_east", "Time", "bottom_top", "south_north")
    shape = (4, 1, 3, 2)


class PR73NativeInputAuditTest(unittest.TestCase):
    def test_selectors_follow_dimension_names_and_one_based_wrf_coordinates(self) -> None:
        selectors = _selectors(VariableShape(), {"i": 3, "j": 2, "k": 2})
        self.assertEqual(selectors, (2, 0, 1, 1))
        vertical = _selectors(VariableShape(), {"i": 3, "j": 2, "k": 2},
                              vertical=(1, 3))
        self.assertEqual(vertical, (2, 0, slice(0, 3), 1))

    def test_rejects_nonpositive_or_out_of_bounds_coordinates(self) -> None:
        with self.assertRaisesRegex(ValueError, "one-based positive"):
            _selectors(VariableShape(), {"i": 0, "j": 2, "k": 2})
        with self.assertRaisesRegex(ValueError, "outside west_east"):
            _selectors(VariableShape(), {"i": 5, "j": 2, "k": 2})

    def test_decodes_and_binds_single_wrf_time(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wrfinput_d01"
            with Dataset(path, "w") as dataset:
                dataset.createDimension("Time", 1)
                dataset.createDimension("DateStrLen", 19)
                times = dataset.createVariable("Times", "S1", ("Time", "DateStrLen"))
                times[0, :] = np.frombuffer(b"2026-08-16_12:00:00", dtype="S1")
            with Dataset(path) as dataset:
                self.assertEqual(wrf_valid_time(dataset), "2026-08-16_12:00:00")


if __name__ == "__main__":
    unittest.main()
