from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from pr101_upper_wind_fortran_replay import DIFFUSION_SOURCE, extract_routine, generate
from pr101_upper_wind_replay import compare
sys.path.insert(0, str(ROOT / "tests"))
from test_pr101_upper_wind_replay import record, write_record


class TestPR101UpperWindReplayNative(unittest.TestCase):
    @unittest.skipUnless(DIFFUSION_SOURCE.is_file(),
                         "requires retained horizontal_diffusion source asset")
    def test_big_endian_call_records_replay_to_captured_output(self):
        x = record("u")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pr101_upper_wind.raw"
            with path.open("wb") as stream:
                write_record(stream, x, 1, 1)
                write_record(stream, x, 2, 7)
            result = compare(path)
            generated = generate(path)
        self.assertEqual(result["records"], 2)
        self.assertEqual(result["faces"][0]["levels"][2]["residual"], 0.0)
        routine = extract_routine(DIFFUSION_SOURCE.read_text())
        self.assertIn(routine, generated)
        self.assertIn("TYPE :: grid_config_rec_type", generated)
        self.assertIn("CALL horizontal_diffusion('u'", generated)
        self.assertIn("TRANSFER(tendency(136,39,16),0_int32) /= expected_bits", generated)
        self.assertIn("PR101_UPPER_WIND_FORTRAN_REPLAY_PASS v1", generated)
        self.assertIn("ERROR STOP 1", generated)


    @unittest.skipUnless(DIFFUSION_SOURCE.is_file(),
                         "requires retained horizontal_diffusion source asset")
    def test_multiple_timestep_events_pair_independently(self):
        x = record("u")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pr101_upper_wind.raw"
            with path.open("wb") as stream:
                for timestep in (20, 21):
                    x.time_step = timestep
                    write_record(stream, x, 1, 1)
                    write_record(stream, x, 2, 7)
            self.assertEqual(len(compare(path)["faces"]), 2)
            self.assertEqual(len(generate(path).split("Capture pair ")) - 1, 2)


