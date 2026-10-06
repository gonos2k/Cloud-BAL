import contextlib
import io
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import native_ccn_stage_trace as trace_tool
from native_ccn_stage_trace import (
    TraceError, _boundary_delta, _read_pd_budget, _read_stage, _read_update, _stats,
)


BOUNDS = {
    "ids": 1, "ide": 3, "jds": 1, "jde": 2, "kds": 1, "kde": 2,
    "ims": 1, "ime": 3, "jms": 1, "jme": 2, "kms": 1, "kme": 2,
    "its": 1, "ite": 3, "jts": 1, "jte": 2, "kts": 1, "kte": 2,
}


def write_stage(path: Path, *, stage=1, rk=1, domain=None, memory=None, tile=None, extra=b""):
    domain = domain or (1, 3, 1, 2, 1, 2)
    memory = memory or (1, 3, 1, 2, 1, 2)
    tile = tile or (1, 3, 1, 2)
    values = np.arange(12, dtype=np.dtype(">f4"))
    path.write_bytes(b"CCNSTG1 " + struct.pack(">8i", stage, rk, *domain)
                     + struct.pack(">10i", *memory, *tile) + values.tobytes()
                     + values.tobytes() + extra)


def write_update(path: Path, *, dt=20.0, c2=(95000.0, 95000.0)):
    nx, ny, nz = 3, 2, 2
    dims = (1, 3, 1, 2, 1, 2, 1, 3, 1, 2, 1, 2)
    n3, n2 = nx * ny * nz, nx * ny
    arrays = [np.ones(n3, dtype=">f4") for _ in range(4)]
    arrays += [np.ones(n2, dtype=">f4") for _ in range(4)]
    arrays += [np.zeros(nz, dtype=">f4"), np.array(c2, dtype=">f4")]
    raw = b"CCNUPD1 " + struct.pack(">12if", *dims, dt)
    raw += b"".join(a.tobytes() for a in arrays)
    path.write_bytes(raw)


def write_pd_budget(path: Path, *, memory=(1, 3, 1, 2, 1, 2), nan_metric=False):
    nx, ny, nz = 3, 2, 2
    tile = (1, 3, 1, 2, 1, 2)
    n3, n2 = nx * ny * nz, nx * ny
    nxface, nyface, nzface = (nx + 2) * ny * nz, nx * (ny + 2) * nz, nx * ny * (nz + 1)
    arrays = [np.ones(n3, dtype=">f4") for _ in range(5)]
    arrays += [np.ones(nxface, dtype=">f4") for _ in range(2)]
    arrays += [np.ones(nyface, dtype=">f4") for _ in range(2)]
    arrays += [np.ones(nzface, dtype=">f4") for _ in range(2)]
    arrays += [np.ones(n2, dtype=">f4") for _ in range(2)]
    arrays += [np.ones(nz, dtype=">f4")]
    if nan_metric:
        arrays[11][0] = np.nan
    raw = b"CCNPDB1 " + struct.pack(">12i3f", *memory, *tile, 20.0, 0.0002, 0.0002)
    raw += b"".join(a.tobytes() for a in arrays)
    path.write_bytes(raw)


class NativeCcnStageTraceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_reads_stage_and_active_values(self):
        path = self.root / "pr61_qnn_stage_1_rk1.raw"
        write_stage(path)
        record = _read_stage(path, BOUNDS, expected_stage=1, expected_rk=1)
        self.assertEqual(record["active_shape_xyz"], [3, 2, 2])
        self.assertEqual(record["state"].shape, (2, 2, 3))

    def test_boundary_delta_uses_float64_and_marks_nonfinite_pairs_unassessed(self):
        baseline = _boundary_delta(
            np.array([1.0, 3.0], dtype=np.float32),
            np.array([1.0, 2.0], dtype=np.float32),
        )
        self.assertEqual(baseline, {"changed_cells": 1, "max_abs_change": 1.0})

        extreme = _boundary_delta(
            np.array([3.0e38], dtype=np.float32),
            np.array([-3.0e38], dtype=np.float32),
        )
        expected = float(np.float64(np.float32(3.0e38))
                         - np.float64(np.float32(-3.0e38)))
        self.assertEqual(extreme["max_abs_change"], expected)

        partial = _boundary_delta(
            np.array([1.0, np.nan], dtype=np.float32),
            np.array([0.0, 4.0], dtype=np.float32),
        )
        self.assertEqual(partial["changed_cells"], 1)
        self.assertIsNone(partial["max_abs_change"])
        self.assertEqual(partial["unassessed_nonfinite_cells"], 1)

    def test_stage_parser_preserves_nonfinite_value_counts(self):
        path = self.root / "pr61_qnn_stage_1_rk1.raw"
        write_stage(path)
        raw = bytearray(path.read_bytes())
        struct.pack_into(">f", raw, 80, float("nan"))
        struct.pack_into(">f", raw, 84, float("inf"))
        path.write_bytes(raw)
        record = _read_stage(path, BOUNDS, expected_stage=1, expected_rk=1)
        self.assertEqual(_stats(record["state"])["nonfinite"], 2)

    def test_nonfinite_pd_residual_is_counted_and_serializable(self):
        path = self.root / "pr61_qnn_pd_budget_rk3.raw"
        write_pd_budget(path, nan_metric=True)
        final_nn = np.zeros((2, 2, 3), dtype=np.float32)
        final_nn[0, 0, 0] = -1.0
        final_nn[0, 0, 1] = -1.0
        result = _read_pd_budget(path, BOUNDS, final_nn)
        self.assertEqual(result["nonfinite_postscale_budget_residuals"], 1)
        self.assertEqual(result["negative_call_cells_postscale_budget_overshoot"], 0)
        self.assertEqual(result["negative_call_cells_postscale_budget_positive"], 1)
        self.assertAlmostEqual(result["postscale_budget_residual_min"], 20.992, places=5)
        self.assertAlmostEqual(result["postscale_budget_residual_max"], 20.992, places=5)
        json.dumps(result, allow_nan=False)

    def test_cli_converts_nonfinite_json_error_to_argparse_error(self):
        stderr = io.StringIO()
        with (
            mock.patch.object(sys, "argv", ["native_ccn_stage_trace.py", "run", "pre.raw"]),
            mock.patch.object(trace_tool, "summarize", return_value={"bad": float("nan")}),
            contextlib.redirect_stderr(stderr),
        ):
            with self.assertRaises(SystemExit) as raised:
                trace_tool.main()
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("Out of range float values", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_rejects_pd_budget_memory_metadata_mismatch(self):
        path = self.root / "pr61_qnn_pd_budget_rk3.raw"
        write_pd_budget(path, memory=(1, 3, 1, 2, 0, 2))
        with self.assertRaisesRegex(TraceError, "PD budget memory bounds mismatch"):
            _read_pd_budget(path, BOUNDS, np.ones((2, 2, 3), dtype=np.float32))

    def test_rejects_filename_header_pair_mismatch(self):
        path = self.root / "pr61_qnn_stage_1_rk1.raw"
        write_stage(path, stage=2)
        with self.assertRaisesRegex(TraceError, "stage header mismatch"):
            _read_stage(path, BOUNDS, expected_stage=1, expected_rk=1)

    def test_rejects_stage_domain_metadata_mismatch(self):
        path = self.root / "pr61_qnn_stage_1_rk1.raw"
        write_stage(path, domain=(1, 2, 1, 2, 1, 2))
        with self.assertRaisesRegex(TraceError, "domain bounds mismatch"):
            _read_stage(path, BOUNDS, expected_stage=1, expected_rk=1)

    def test_rejects_stage_memory_metadata_mismatch(self):
        path = self.root / "pr61_qnn_stage_1_rk1.raw"
        write_stage(path)
        data = bytearray(path.read_bytes())
        struct.pack_into(">i", data, 40, 0)
        path.write_bytes(data)
        with self.assertRaisesRegex(TraceError, "memory bounds mismatch"):
            _read_stage(path, BOUNDS, expected_stage=1, expected_rk=1)

    def test_rejects_stage_payload_size_mismatch(self):
        path = self.root / "pr61_qnn_stage_1_rk1.raw"
        write_stage(path, extra=b"x")
        with self.assertRaisesRegex(TraceError, "payload size mismatch"):
            _read_stage(path, BOUNDS, expected_stage=1, expected_rk=1)

    def test_stage_k_origin_uses_tile_start_with_memory_halo(self):
        bounds = dict(BOUNDS, kms=0, kme=2)
        path = self.root / "pr61_qnn_stage_1_rk1.raw"
        write_stage(path, memory=(1, 3, 1, 2, 0, 2), tile=(1, 3, 1, 2))
        record = _read_stage(path, bounds, expected_stage=1, expected_rk=1)
        np.testing.assert_array_equal(record["state"], np.arange(12, dtype=np.float32).reshape(2, 2, 3))

    def test_rejects_stage_active_bounds_outside_memory(self):
        path = self.root / "pr61_qnn_stage_1_rk1.raw"
        write_stage(path, tile=(0, 3, 1, 2))
        with self.assertRaisesRegex(TraceError, "capture bounds fall outside memory"):
            _read_stage(path, BOUNDS, expected_stage=1, expected_rk=1)

    def test_reads_update_with_positive_dt_and_mass(self):
        path = self.root / "pr61_qnn_update_rkfinal.raw"
        write_update(path)
        record = _read_update(path, BOUNDS)
        self.assertEqual(record["dt_s"], 20.0)
        self.assertEqual(record["scalar_old"].shape, (2, 2, 3))

    def test_rejects_nonpositive_update_dt(self):
        path = self.root / "pr61_qnn_update_rkfinal.raw"
        write_update(path, dt=0.0)
        with self.assertRaisesRegex(TraceError, "dt must be finite and positive"):
            _read_update(path, BOUNDS)

    def test_rejects_zero_update_mass_factor(self):
        path = self.root / "pr61_qnn_update_rkfinal.raw"
        write_update(path, c2=(0.0, 0.0))
        with self.assertRaisesRegex(TraceError, "mass factors must be finite and positive"):
            _read_update(path, BOUNDS)

    def test_rejects_truncated_update_header(self):
        path = self.root / "pr61_qnn_update_rkfinal.raw"
        path.write_bytes(b"CCNUPD1")
        with self.assertRaisesRegex(TraceError, "truncated update header"):
            _read_update(path, BOUNDS)


if __name__ == "__main__":
    unittest.main()
