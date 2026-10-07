"""Focused tests for PR67 completed-boundary and raw-schema replay guards."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
spec = importlib.util.spec_from_file_location(
    "pr67_negative_qc_replay", TOOLS / "pr67_negative_qc_replay.py")
assert spec is not None and spec.loader is not None
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)


class NegativeQcReplayTests(unittest.TestCase):
    def test_preexisting_negative_is_not_counted_as_new_rk_appearance(self) -> None:
        initial = (1, 2, 1)
        first = (2, 2, 1)
        final = (3, 2, 1)
        masks = [{initial}, {initial, first}, {initial, first, final},
                 {initial, final}]
        groups = replay.first_appearance_sets(masks, {initial, final})
        self.assertEqual(groups, [set(), {final}, set()])

    def test_reads_core_update_from_16_and_21_value_rows(self) -> None:
        common = ["1.0e-3", "1.0e-3", "-1.0", "1.0", "-1.0", "0.0"]
        masses = ["-1.0", "1.0", "1.0", "0.0", "1.0", "1.0", "0.0", "1.0", "1.0", "-0.999"]
        row16 = "QC_PRE 1 2 2 1 " + " ".join(common + masses)
        run3_values = common + ["0.0", "0.0", "NaN", "0.0", "NaN"] + masses
        row21 = "QC_PRE 1 2 2 1 " + " ".join(run3_values)
        post = "QC_POST AFTER_UPDATE 1 2 2 1 -0.999"
        for row, invalid_channels in ((row16, 0), (row21, 2)):
            with self.subTest(schema=len(row.split())):
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "observer.raw"
                    path.write_text(row + "\n" + post + "\n")
                    before, after, counts = replay.read_observer(path)
                self.assertIn((1, (2, 2, 1)), before)
                self.assertAlmostEqual(float(after["AFTER_UPDATE"][(1, (2, 2, 1))]),
                                       -0.999, places=6)
                self.assertEqual(counts.get("ignored_run3_channel_invalid_shcu", 0),
                                 invalid_channels // 2)
                self.assertEqual(counts.get("ignored_run3_channel_invalid_nc_shcu", 0),
                                 invalid_channels // 2)

    def test_receipt_paths_must_remain_inside_run_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            root = parent / "run"
            root.mkdir()
            outside = parent / "outside"
            outside.write_text("outside")
            with self.assertRaisesRegex(ValueError, "escapes run root"):
                replay.verify_receipt_file(root, {"path": str(outside)})


if __name__ == "__main__":
    unittest.main()
