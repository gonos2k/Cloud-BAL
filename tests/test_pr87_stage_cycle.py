from __future__ import annotations

import gzip
import struct
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from pr87_stage_cycle import analyze


def _record(qc: np.ndarray, nc: np.ndarray) -> bytes:
    # One j, one k, three i cells; remaining fields are zero-filled.
    header = struct.pack(">15i", 1, 1, 0, 1, 3, 1, 1, 1, 1, 1, 3, 1, 1, 1, 1)
    fields = []
    for name in ("DEN", "Q", "QC", "QI", "QR", "QS", "QG", "NN", "NC", "NI", "NR", "BG"):
        values = qc if name == "QC" else nc if name == "NC" else np.zeros(3, dtype=np.float32)
        fields.append(np.asarray(values, dtype=">f4").tobytes())
    return b"PR85QND2" + b"POST_KDM6".ljust(32) + header + b"".join(fields)


class StageCycleTests(unittest.TestCase):
    def test_predicts_only_subthreshold_paired_cell(self) -> None:
        qc = np.array([2e-8, 5e-9, 0.0], dtype=np.float32)
        nc = np.array([4.0, 8.0, 12.0], dtype=np.float32)
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / name for name in ("off.raw.gz", "coupled.raw.gz")]
            for path in paths:
                with gzip.open(path, "wb") as stream:
                    stream.write(_record(qc, nc))
            result = analyze(paths[0], paths[1])

        self.assertTrue(result["comparison"]["candidate_cells_exactly_equal"])
        for arm in ("OFF", "COUPLED"):
            summary = result["arms"][arm]
            self.assertEqual(summary["direct_zero_QC_positive_QNC_cells_at_snapshot"], 1)
            self.assertEqual(summary["positive_QC_below_threshold_with_positive_QNC_cells"], 1)
            cell = summary["candidate_cells"][0]
            self.assertEqual((cell["i"], cell["j"], cell["k"]), (2, 1, 1))
            self.assertEqual(cell["predicted_after_zero_outa_QC"], 0.0)
            self.assertEqual(cell["predicted_after_zero_outa_QNC"], 8.0)
            self.assertFalse(summary["runtime_observation"])


if __name__ == "__main__":
    unittest.main()
