#!/usr/bin/env python3
"""Focused tests for the read-only signed boundary diagnostic."""
from __future__ import annotations

import importlib.util
import struct
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np


MODULE_PATH = Path(__file__).with_name("diagnose_qbal_boundary.py")
SPEC = importlib.util.spec_from_file_location("diagnose_qbal_boundary", MODULE_PATH)
assert SPEC and SPEC.loader
diagnostic = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = diagnostic
SPEC.loader.exec_module(diagnostic)


def write_fixture(directory: Path) -> tuple[Path, Path]:
    nx, ny, nz = 4, 4, 3
    corner = np.zeros((nx + 1, ny + 1, nz + 1), dtype=np.float32)
    legacy = corner.copy()
    erru = np.ones((nx, ny, nz), dtype=np.float32)
    beta = np.zeros((nx, ny, nz), dtype=np.float32)
    tau = np.ones((nx, ny), dtype=np.float32)
    dx = np.full((nx, ny), 10.0, dtype=np.float32)
    dy = dx.copy()
    ps = np.full((nx, ny), 500.0, dtype=np.float32)
    p = np.asarray((300.0, 200.0, 100.0), dtype=np.float32)
    dp = np.asarray((1.0, 2.0, 3.0), dtype=np.float32)
    u = np.ones((nx, ny, nz), dtype=np.float32)
    v = np.full((nx, ny, nz), 2.0, dtype=np.float32)
    w = np.full((nx, ny, nz), 3.0, dtype=np.float32)

    # Active rows A=(2,2,2), B=(3,2,2), C=(2,2,3).  The support neighbor
    # (2,3,2) has beta=0.  The terrain-sentinel neighbor (3,3,2) has
    # positive beta but an unrelated sentinel face, so it cannot be inferred
    # as ordinary support.
    active_cells = ((2, 2, 2), (3, 2, 2), (2, 2, 3))
    for i, j, k in active_cells:
        beta[i - 1, j - 1, k - 1] = 1.0
    beta[2, 2, 1] = 1.0  # physical (3,3,2), omitted due to sentinel
    u[2, 1, 0] = diagnostic.SENTINEL

    def divergence(i: int, j: int, k: int) -> float:
        return ((float(u[i - 1, j - 2, k - 2]) - float(u[i - 2, j - 2, k - 2])) / dx[i - 1, j - 1]
                + (float(v[i - 2, j - 1, k - 2]) - float(v[i - 2, j - 2, k - 2])) / dy[i - 1, j - 1]
                + (float(w[i - 1, j - 1, k - 2]) - float(w[i - 1, j - 1, k - 1])) / dp[k - 1])

    rows = [
        ((2, 2, 2), (1.0, 0.0, 0.0, 0.0, 3.0, 0.0)),
        ((3, 2, 2), (0.0, 1.0, 0.0, 0.0, 0.0, 0.0)),
        ((2, 2, 3), (0.0, 0.0, 0.0, 0.0, 0.0, 2.0)),
    ]
    row_path = directory / "rows.bin"
    with row_path.open("wb") as stream:
        stream.write(struct.pack("<4i", nx, ny, nz, len(rows)))
        for (i, j, k), coefficients in rows:
            stream.write(struct.pack("<3i7d", i, j, k, -divergence(i, j, k), *coefficients))

    snapshot_path = directory / "snapshot.bin"
    with snapshot_path.open("wb") as stream:
        stream.write(struct.pack(">3if", nx, ny, nz, 1.0))
        for array in (corner, legacy, erru, beta, tau, dx, dy, ps, p, dp, u, v, w):
            stream.write(np.asarray(array, dtype=">f4", order="F").tobytes(order="F"))
    return row_path, snapshot_path


def write_background_fixture(directory: Path) -> Path:
    shape = (4, 4, 3)
    background = (
        np.full(shape, 0.5, dtype=np.float32),
        np.full(shape, 1.0, dtype=np.float32),
        np.full(shape, 2.0, dtype=np.float32),
    )
    path = directory / "background.bin"
    with path.open("wb") as stream:
        stream.write(struct.pack(">3i", *shape))
        for array in background:
            stream.write(np.asarray(array, dtype=">f4", order="F").tobytes(order="F"))
    return path


class BoundaryDiagnostics(unittest.TestCase):
    def test_fixture_preserves_metric_detailbalance_and_boundary_partition(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            rows, snapshot = write_fixture(Path(temporary))
            result = diagnostic.diagnose(rows, snapshot)
        self.assertEqual(result["component_count"], 1)
        self.assertEqual(result["metric"]["dx_equals_dy_max_abs"], 0.0)
        self.assertEqual(result["metric"]["z_dtype"], "float64")
        self.assertLess(result["metric"]["peredge_detailbalance_max_abs"], 1e-13)
        component = result["components"][0]
        self.assertEqual(set(component["axis_signed"]), {"u", "v", "omega"})
        self.assertAlmostEqual(
            sum(component["axis_signed"].values()),
            component["weighted_rhs"],
            places=10,
        )
        self.assertEqual(component["internal_pair_count"], 2)
        self.assertEqual(sum(component["boundary_face_counts"].values()), 14)
        self.assertLess(abs(component["closure_error"]), 1e-10)
        self.assertGreater(component["boundary_face_counts"]["support"], 0)
        self.assertGreater(component["boundary_face_counts"]["terrain-sentinel"], 0)
        self.assertFalse(result["background_proposal_attribution"]["feasible_from_snapshot"])
        self.assertEqual(result["metric"]["signed_quantity"], "z^T b = -z^T D(y)")
        self.assertLess(abs(result["state_summaries"]["proposal"]["closure_error"]), 1e-10)

    def test_stored_rhs_is_checked_against_float64_flux_terms(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            rows, snapshot = write_fixture(Path(temporary))
            result = diagnostic.diagnose(rows, snapshot)
        self.assertLess(result["metric"]["row_flux_reconstruction_max_abs"], 1e-12)
        self.assertAlmostEqual(
            result["metric"]["weighted_rhs_sum"],
            sum(component["weighted_rhs"] for component in result["components"]),
            places=10,
        )

    def test_missing_face_categories_are_exclusive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            rows, snapshot = write_fixture(Path(temporary))
            result = diagnostic.diagnose(rows, snapshot)
        component = result["components"][0]
        names = result["boundary_groups"]
        self.assertEqual(set(component["boundary_face_counts"]), set(names))
        self.assertEqual(
            sum(component["boundary_face_counts"].values())
            + component["internal_pair_count"] * 2,
            component["rows"] * 6,
        )

    def test_background_and_proposal_delta_use_the_same_partition(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            rows, snapshot = write_fixture(directory)
            background = write_background_fixture(directory)
            result = diagnostic.diagnose(rows, snapshot, background)
        self.assertTrue(result["background_proposal_attribution"]["feasible_from_snapshot"])
        self.assertEqual(
            set(result["state_decompositions"]),
            {"proposal", "background", "proposal_delta"},
        )
        proposal = result["state_decompositions"]["proposal"][0]
        background_state = result["state_decompositions"]["background"][0]
        delta = result["state_decompositions"]["proposal_delta"][0]
        self.assertEqual(proposal["boundary_face_counts"], delta["boundary_face_counts"])
        self.assertEqual(
            result["state_summaries"]["proposal"]["boundary_face_counts"],
            result["state_summaries"]["background"]["boundary_face_counts"],
        )
        for name in diagnostic.BOUNDARY_NAMES:
            self.assertAlmostEqual(
                delta["boundary_signed"][name],
                proposal["boundary_signed"][name]
                - background_state["boundary_signed"][name],
                places=8,
            )
        self.assertLess(abs(delta["closure_error"]), 1e-8)

    def test_uniform_coefficient_rescale_is_checked_relatively(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            rows, snapshot = write_fixture(directory)
            raw = bytearray(rows.read_bytes())
            record_size = 12 + 8 + 6 * 8
            for record in range(3):
                coefficients_offset = 16 + record * record_size + 12 + 8
                for direction in range(6):
                    offset = coefficients_offset + direction * 8
                    value = struct.unpack_from("<d", raw, offset)[0]
                    struct.pack_into("<d", raw, offset, value * 1.0e12)
            rows.write_bytes(raw)
            result = diagnostic.diagnose(rows, snapshot)
        self.assertLess(result["metric"]["peredge_detailbalance_max_relative"], 1e-13)

    def test_altered_rhs_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            rows, snapshot = write_fixture(directory)
            raw = bytearray(rows.read_bytes())
            rhs_offset = 16 + 12
            original = struct.unpack_from("<d", raw, rhs_offset)[0]
            struct.pack_into("<d", raw, rhs_offset, original + 1.0e-4)
            rows.write_bytes(raw)
            with self.assertRaisesRegex(ValueError, "RHS"):
                diagnostic.diagnose(rows, snapshot)

    def test_reversed_edge_breaks_detail_balance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            rows, snapshot = write_fixture(directory)
            raw = bytearray(rows.read_bytes())
            # First record c(E) starts after 12-byte ijk and 8-byte RHS.
            coefficient_offset = 16 + 12 + 8
            struct.pack_into("<d", raw, coefficient_offset, 1.1)
            rows.write_bytes(raw)
            with self.assertRaisesRegex(ValueError, "detail balance"):
                diagnostic.diagnose(rows, snapshot)

    def test_positive_unpaired_face_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            rows, snapshot = write_fixture(directory)
            raw = bytearray(rows.read_bytes())
            # First record c(N) is a missing support face and must remain zero.
            coefficient_offset = 16 + 12 + 8 + 2 * 8
            struct.pack_into("<d", raw, coefficient_offset, 1.0)
            rows.write_bytes(raw)
            with self.assertRaisesRegex(ValueError, "no paired active face"):
                diagnostic.diagnose(rows, snapshot)


if __name__ == "__main__":
    unittest.main()
