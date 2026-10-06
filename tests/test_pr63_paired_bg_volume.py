from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pr63_paired_bg_volume as replay


BOUNDS = {"ids": 1, "ide": 2, "jds": 1, "jde": 2,
          "kds": 1, "kde": 2, "ims": 1, "ime": 2,
          "jms": 1, "jme": 2, "kms": 1, "kme": 2,
          "its": 1, "ite": 2, "jts": 1, "jte": 2,
          "kts": 1, "kte": 2}


def geometry() -> dict:
    return {"stage": "PRE_MICROPHYSICS", "timestep": 1,
            "bounds": BOUNDS.copy(), "dx_m": 10.0, "dy_m": 10.0,
            "gravity_m_s2": 10.0,
            "arrays": {"mu2": np.full((2, 2), 1000.0),
                       "mub": np.zeros((2, 2)),
                       "msftx": np.ones((2, 2)),
                       "msfty": np.ones((2, 2)),
                       "c1h": np.full(2, -1.0),
                       "c2h": np.zeros(2),
                       "dnw": np.full(2, 0.5)}}


def dump(stage: int, *, fields=None, bounds=None) -> dict:
    values = {name: np.zeros((2, 2, 2), dtype=np.float32)
              for name in ("QC", "NC", "QG", "BG")}
    values["BG"][0, 0, 0] = 0.004 if stage == 1 else 0.0
    if fields:
        values.update(fields)
    return {"stage": stage, "itimestep": 1,
            "bounds": BOUNDS.copy() if bounds is None else bounds,
            "active_shape_xyz": [2, 2, 2],
            "params": (20.0, 1.0, 1.0, 1.0, 1.0), "fields": values}


class PairedGraupelVolumeTests(unittest.TestCase):
    def _run(self, control, paired):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cgeo, pgeo, cpost, ppost = (root / name for name in
                                        ("cgeo", "pgeo", "cpost", "ppost"))
            cgeo.write_bytes(b"same geometry fixture")
            pgeo.write_bytes(b"same geometry fixture")
            cpost.write_bytes(b"control post fixture")
            ppost.write_bytes(b"paired post fixture")
            with (patch.object(replay, "parse_geometry", return_value=[geometry(), geometry()]),
                  patch.object(replay, "read_dump", side_effect=[control, paired])):
                return replay.replay(cgeo, pgeo, cpost, ppost)

    def test_replays_positive_to_zero_bg_using_hybrid_carrier(self):
        control_bg = np.zeros((2, 2, 2), dtype=np.float32)
        control_bg[0, 0, 0] = 0.004
        result = self._run(dump(2, fields={"BG": control_bg}), dump(2))
        self.assertEqual(result["changed_cells"], 1)
        self.assertAlmostEqual(result["hybrid_carrier_weighted_delta_m3"], 20.0, places=5)

    def test_rejects_kdm_active_window_outside_geometry_tile(self):
        bad = BOUNDS.copy()
        bad["ite"] = 3
        with self.assertRaisesRegex(ValueError, "outside solve_em tile"):
            self._run(dump(2, bounds=bad), dump(2, bounds=bad))

    def test_rejects_nonfinite_qg_or_bg(self):
        for name in ("QG", "BG"):
            bad = np.zeros((2, 2, 2), dtype=np.float32)
            bad[0, 0, 0] = np.nan
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "nonfinite KDM6 field"):
                self._run(dump(2, fields={name: bad}), dump(2))


if __name__ == "__main__":
    unittest.main()
