#!/usr/bin/env python3
"""Focused contract tests for PR86 multistep time-response handling."""

from __future__ import annotations

import struct
import re
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pr86_time_response as response


def record(step: int, value: float) -> bytes:
    bounds = (1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1)
    header = struct.pack(">15i", 1, step, 0, *bounds)
    fields = b"".join(np.array([value], dtype=">f4").tobytes() for _ in response.STATE_FIELDS)
    return response.STATE_MAGIC + b"POST_KDM6".ljust(32, b" ") + header + fields


class TimeResponseTests(unittest.TestCase):
    def test_runtime_and_history_edits_preserve_physics_namelist(self) -> None:
        source = """&time_control
 run_days = 0,
 run_hours = 0,
 run_minutes = 0,
 run_seconds = 20,
 start_year = 2026,
 start_month = 08,
 start_day = 16,
 start_hour = 13,
 start_minute = 00,
 start_second = 00,
 end_year = 2026,
 end_month = 08,
 end_day = 16,
 end_hour = 13,
 end_minute = 00,
 end_second = 20,
 history_interval = 60,
 /
 &physics
 mp_physics = 37,
 time_step = 20,
 /
"""
        edited = response.edit_namelist(source, 600)
        self.assertIn("run_minutes = 10,", edited)
        self.assertIn("end_minute = 10,", edited)
        self.assertIn("end_second = 00,", edited)
        self.assertIn("history_interval = 1,", edited)
        self.assertIn("mp_physics = 37,", edited)
        self.assertIn("time_step = 20,", edited)
        names = ("run_days", "run_hours", "run_minutes", "run_seconds", "end_year", "end_month",
                 "end_day", "end_hour", "end_minute", "end_second", "history_interval")
        source_values = {name: re.search(rf"(?m)^\s*{name}\s*=\s*([^,]+)", source).group(1).strip()
                         for name in names}
        edited_values = {name: re.search(rf"(?m)^\s*{name}\s*=\s*([^,]+)", edited).group(1).strip()
                         for name in names}
        changed = {name for name in names if source_values[name] != edited_values[name]}
        self.assertEqual(changed, {"run_minutes", "run_seconds", "end_minute", "end_second",
                                   "history_interval"})

    def test_streaming_snapshot_reader_selects_true_model_timesteps(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stages.raw"
            path.write_bytes(b"".join(record(step, float(step)) for step in (1, 2, 3, 15, 30)))
            result = response.read_time_snapshots(path)
        self.assertEqual(result["timesteps"], [1, 2, 3, 15, 30])
        self.assertEqual(result["completed_post_kdm6_timesteps"], [1, 2, 3, 15, 30])
        self.assertEqual(set(result["snapshots"]), {"20s", "1min", "5min", "10min"})
        self.assertEqual(result["snapshots"]["5min"]["model_seconds"], 300)
        self.assertEqual(result["snapshots"]["10min"]["fields"]["QC"]["max"], 30.0)

    def test_duplicate_post_kdm6_timestep_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stages.raw"
            path.write_bytes(record(1, 1.0) + record(1, 2.0))
            result = response.read_time_snapshots(path)
        self.assertEqual(result["completed_post_kdm6_timesteps"], [1])
        self.assertEqual(result["duplicate_post_kdm6_timesteps"], [1])
        self.assertEqual(result["snapshots"]["20s"]["fields"]["QC"]["max"], 1.0)

    def test_model_timestamps_allow_mirrors_but_reject_within_log_duplicates(self) -> None:
        line = "Timing for main: time 2026-08-16_13:00:20 on domain   1:  1.25 elapsed seconds\n"
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory)
            (stage / "rsl.error.0000").write_text(line)
            (stage / "rsl.out.0000").write_text(line)
            self.assertEqual(len(response._model_times(stage)), 1)
            (stage / "rsl.error.0000").write_text(line + line)
            with self.assertRaisesRegex(ValueError, "duplicate model timestamps"):
                response._model_times(stage)


if __name__ == "__main__":
    unittest.main()
