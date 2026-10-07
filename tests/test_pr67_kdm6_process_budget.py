from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from pr67_kdm6_process_budget import CaptureError, parse_process_capture


def _array(values: np.ndarray, kind: str) -> bytes:
    dtype = np.dtype(">f8" if kind == "f8" else ">f4")
    return np.asarray(values, dtype=dtype).tobytes(order="F")


def _record(stage: int, data: bytes, dtcld: float = 20.0, lat: int = 4) -> bytes:
    return b"PR67P001" + struct.pack(">6if", stage, lat, 1, 2, 1, 3, dtcld) + data


def _valid_capture(denr_values: tuple[float, ...] = (1000.0,)) -> bytes:
    matrix = np.arange(6, dtype=np.float32).reshape((2, 3), order="F")
    doubles = np.arange(6, dtype=np.float64).reshape((2, 3), order="F")
    bottom_fall = np.ones((2, 4), dtype=np.float32) * 1.e-6
    rows = []
    for row, denr in enumerate(denr_values):
        stage0 = _record(0, _array(doubles, "f8") + _array(matrix + 100, "f4")
                         + _array(matrix + 1, "f4") + _array(matrix / 100, "f4"), lat=4 + row)
        stage1 = _record(1, _array(matrix / 200, "f4") + _array(matrix / 10, "f4")
                         + _array(matrix / 5, "f4"), lat=4 + row)
        bottom = (np.asarray([denr], dtype=">f4").tobytes()
                  + _array(bottom_fall, "f4")
                  + np.asarray([100.0, 120.0], dtype=">f4").tobytes()
                  + np.asarray([1.0, 1.1], dtype=">f4").tobytes()
                  + np.zeros(2, dtype=">f4").tobytes()
                  + struct.pack(">2i", -1, 0)
                  + np.asarray([0.0, 0.0], dtype=">f4").tobytes())
        rows.append(stage0 + stage1 + _record(2, bottom, lat=4 + row))
    return b"".join(rows)


class Kdm6ProcessBudgetTests(unittest.TestCase):
    def test_parses_three_stages_and_big_endian_double_velocity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "process.raw"
            path.write_bytes(_valid_capture())
            records = parse_process_capture(path)
        self.assertEqual([record["stage"] for record in records], [0, 1, 2])
        self.assertEqual(records[0]["lat"], 4)
        self.assertEqual(records[0]["work1_ice"].shape, (3, 2))
        self.assertEqual(records[0]["work1_ice"][2, 1], 5.0)
        self.assertTrue(records[2]["snowncv_present"])
        self.assertFalse(records[2]["graupelncv_present"])
        self.assertEqual(records[2]["fall"].shape, (4, 2))

    def test_rejects_incomplete_or_misordered_first_record(self) -> None:
        capture = _valid_capture()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "process.raw"
            path.write_bytes(capture[156:])
            with self.assertRaises(CaptureError):
                parse_process_capture(path)
            path.write_bytes(capture[:-1])
            with self.assertRaises(CaptureError):
                parse_process_capture(path)

    def test_rejects_stage_header_mismatch(self) -> None:
        capture = _valid_capture()
        stage0_size = 8 + 28 + 6 * 8 + 3 * 6 * 4
        stage1_size = 8 + 28 + 3 * 6 * 4
        offset = stage0_size
        stage1 = capture[offset:offset + stage1_size]
        changed = bytearray(stage1)
        struct.pack_into(">f", changed, 8 + 24, 21.0)
        malformed = capture[:offset] + changed + capture[offset + stage1_size:]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "process.raw"
            path.write_bytes(malformed)
            with self.assertRaises(CaptureError):
                parse_process_capture(path)

    def test_rejects_call_scalar_density_mismatch_between_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "process.raw"
            path.write_bytes(_valid_capture((1000.0, 1001.0)))
            with self.assertRaisesRegex(CaptureError, "DENR"):
                parse_process_capture(path)


if __name__ == "__main__":
    unittest.main()
