#!/usr/bin/env python3
"""Focused math check for the same-A dry left-invariant solve."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from pr67_pbl_carrier_audit import _records, _transpose_weights


class DryLeftInvariantTests(unittest.TestCase):
    def test_nonuniform_tridiagonal_transpose_matches_dense_solve(self) -> None:
        lower = [0.0, -0.07, -0.19, -0.11]
        diagonal = [1.04, 1.21, 1.18, 1.10]
        upper = [-0.04, -0.17, -0.08, 0.0]
        weights = [0.8, 3.2, 0.9, 5.7]
        matrix = np.diag(diagonal)
        for row in range(1, len(lower)):
            matrix[row, row - 1] = lower[row]
        for row in range(len(upper) - 1):
            matrix[row, row + 1] = upper[row]

        actual = np.asarray(_transpose_weights(lower, diagonal, upper, weights))
        expected = np.linalg.solve(matrix.T, np.asarray(weights))

        np.testing.assert_allclose(actual, expected, rtol=1.0e-13, atol=1.0e-13)
        np.testing.assert_allclose(matrix.T @ actual, weights, rtol=1.0e-13, atol=1.0e-13)

    def test_qc_record_levels_must_be_in_order(self) -> None:
        lines = [
            "RUNTIME_CALL,1,1,1,20,1,2,100000,9.81,5000,5000,25000000,5000,5000",
            "RUNTIME_ROW,1,1000,500,1,0.5,0.75,25000000",
            "RUNTIME_ROW,2,500,100,0.5,0,0.25,25000000",
            "GRID_STATIC_INPUT_LINKED",
            "QC_PBL,2,0.0",
            "QC_PBL,1,0.0",
            "QC_SETTLED,1,0.0",
            "QC_SETTLED,2,0.0",
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "carrier.raw"
            path.write_text("\n".join(lines) + "\n")
            with self.assertRaisesRegex(ValueError, "returned QC records.*out of order"):
                _records(path)

    def test_qc_rates_must_be_finite(self) -> None:
        lines = [
            "RUNTIME_CALL,1,1,1,20,1,2,100000,9.81,5000,5000,25000000,5000,5000",
            "RUNTIME_ROW,1,1000,500,1,0.5,0.75,25000000",
            "RUNTIME_ROW,2,500,100,0.5,0,0.25,25000000",
            "GRID_STATIC_INPUT_LINKED",
            "QC_PBL,1,nan",
            "QC_PBL,2,0.0",
            "QC_SETTLED,1,0.0",
            "QC_SETTLED,2,0.0",
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "carrier.raw"
            path.write_text("\n".join(lines) + "\n")
            with self.assertRaisesRegex(ValueError, "returned QC rates must be finite"):
                _records(path)


if __name__ == "__main__":
    unittest.main()
