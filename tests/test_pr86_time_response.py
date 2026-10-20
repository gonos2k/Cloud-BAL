#!/usr/bin/env python3
"""Focused contract tests for PR86 multistep time-response handling."""

from __future__ import annotations

import hashlib
import gzip
import json
import re
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pr86_time_response as response


def record(step: int, value: float) -> bytes:
    bounds = (1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1)
    header = struct.pack(">15i", 1, step, 0, *bounds)
    fields = b"".join(np.array([value], dtype=">f4").tobytes() for _ in response.STATE_FIELDS)
    return response.STATE_MAGIC + b"POST_KDM6".ljust(32, b" ") + header + fields


def make_finalizer_fixture(root: Path, duration: int, steps: tuple[int, ...] | None = None,
                           duplicate_step: int | None = None, truncate: bool = False,
                           fatal: bool = False, rsl_error: str | None = None) -> Path:
    out = root / "run_bundle"
    stage = out / "run"
    runtime = root / "source"
    stage.mkdir(parents=True)
    runtime.mkdir()
    input_bytes = b"frozen input"
    executable_bytes = b"frozen executable"
    (stage / "input.dat").write_bytes(input_bytes)
    (runtime / "input.dat").write_bytes(input_bytes)
    (stage / "wrf.exe").write_bytes(executable_bytes)
    (runtime / "wrf.exe").write_bytes(executable_bytes)
    receipt_path = root / "source_receipt.json"
    receipt_path.write_text(json.dumps({"run_isolation": {"inputs": []}}))
    digest = hashlib.sha256(input_bytes).hexdigest()
    preflight = {"input_hashes": {"input.dat": digest,
                                   "wrf.exe": hashlib.sha256(executable_bytes).hexdigest()},
                 "executable_sha256": hashlib.sha256(executable_bytes).hexdigest(),
                 "baseline_frozen_executable_sha256": hashlib.sha256(executable_bytes).hexdigest(),
                 "candidate_namelist_sha256": "unused",
                 "runtime_dir": str(runtime), "source_receipt": str(receipt_path),
                 "source_receipt_sha256": response.sha256(receipt_path)}
    (out / "preflight.json").write_text(json.dumps(preflight))
    (out / "receipt.json").write_text(json.dumps({"returncode": 0, "compressed_outputs": []}))
    count = duration // 20
    selected_steps = steps if steps is not None else tuple(range(1, count + 1))
    trace = b"".join(record(step, float(step)) for step in selected_steps)
    if duplicate_step is not None:
        trace += record(duplicate_step, 99.0)
    if truncate:
        trace = trace[:-1]
    (stage / "pr85_joint_moment_stages.raw").write_bytes(trace)
    lines = []
    for step in selected_steps:
        stamp = (response.dt.datetime(2026, 8, 16, 13) + response.dt.timedelta(seconds=20 * step))
        lines.append(f"Timing for main: time {stamp:%Y-%m-%d_%H:%M:%S} on domain 1: 1.25 elapsed seconds\n")
    if fatal:
        lines.append("FATAL: manufactured rejection\n")
    (stage / "candidate_run.log").write_text("".join(lines))
    if rsl_error is not None:
        (stage / "rsl.error.0000").write_text(rsl_error)
    return out


class TimeResponseTests(unittest.TestCase):
    def _make_disk_reference(self, root: Path) -> tuple[Path, dict]:
        bundle, stage = root / "reference", root / "reference" / "run"
        stage.mkdir(parents=True)
        source_sha, namelist_sha = "a" * 64, "b" * 64
        input_hashes = {"input.dat": "c" * 64}
        executable_sha, input_sha, boundary_sha = "d" * 64, "e" * 64, "f" * 64
        raw = b"step trace payload"
        archive_name = "trace.raw.gz"
        archive = gzip.compress(raw, mtime=0)
        (stage / archive_name).write_bytes(archive)
        once_raw = b"first-call raw trace"
        once_archive_name = "kdm6_first_call_pre.raw.gz"
        once_archive = gzip.compress(once_raw, mtime=0)
        (stage / once_archive_name).write_bytes(once_archive)
        history = b"history bytes"
        (stage / "wrfout_d01_2026-08-16_13:00:00").write_bytes(history)
        rows = [
            {"path": archive_name, "bytes": len(archive),
             "sha256": hashlib.sha256(archive).hexdigest()},
            {"path": once_archive_name, "bytes": len(once_archive),
             "sha256": hashlib.sha256(once_archive).hexdigest()},
            {"path": "wrfout_d01_2026-08-16_13:00:00", "bytes": len(history),
             "sha256": hashlib.sha256(history).hexdigest()},
        ]
        expected_timestamps = ["step-1", "step-2"]
        timestamps = [{"timestamp": value} for value in expected_timestamps]
        preflight = {"arm": "COUPLED", "source_receipt_sha256": source_sha,
                     "source_namelist_sha256": namelist_sha, "input_hashes": input_hashes,
                     "baseline_frozen_executable_sha256": executable_sha,
                     "candidate_wrfinput_sha256": input_sha,
                     "candidate_wrfbdy_sha256": boundary_sha, "timestep_seconds": 20,
                     "executable_sha256": executable_sha, "candidate_build": None,
                     "namelist_changes": {"history_interval_minutes": 1},
                     "launch_environment": {"OMP_NUM_THREADS": "1", "OMP_DYNAMIC": "FALSE",
                         "launch_request_sha256": response.LAUNCH_ENVIRONMENT_SHA256}}
        (bundle / "preflight.json").write_text(json.dumps(preflight))
        receipt = {"status": "COMPLETE", "returncode": 0, "arm": "COUPLED",
                   "timestep_count": 2, "final_completed_step": 2, "maximum_seen_timestep": 2,
                   "model_timestamps": timestamps, "expected_model_timestamps": expected_timestamps,
                   "duplicate_post_kdm6_timesteps": [], "earliest_fatal": None,
                   "fatal_lines": [], "processing_errors": [], "changed_staged_inputs": [],
                   "changed_original_inputs": [], "source_receipt_sha256": source_sha,
                   "candidate_wrfinput_sha256": input_sha,
                   "candidate_wrfbdy_sha256": boundary_sha,
                   "baseline_frozen_executable_sha256": executable_sha, "pr87_probe": None,
                   "candidate_build": None, "candidate_build_unchanged": True,
                   "expected_executed_executable_sha256": executable_sha,
                   "executed_executable_sha256": executable_sha,
                   "generated_files": rows,
                   "compressed_outputs": [{"path": "trace.raw", "bytes": len(raw),
                       "sha256": hashlib.sha256(raw).hexdigest(), "compressed_path": archive_name,
                       "compressed_bytes": len(archive),
                       "compressed_sha256": hashlib.sha256(archive).hexdigest()},
                      {"path": "kdm6_first_call_pre.raw", "bytes": len(once_raw),
                       "sha256": hashlib.sha256(once_raw).hexdigest(),
                       "compressed_path": once_archive_name,
                       "compressed_bytes": len(once_archive),
                       "compressed_sha256": hashlib.sha256(once_archive).hexdigest()}]}
        receipt_path = bundle / "receipt.json"
        receipt_path.write_text(json.dumps(receipt))
        context = {"source_sha": source_sha, "namelist_sha": namelist_sha,
                   "input_hashes": input_hashes, "executable_sha": executable_sha,
                   "input_sha": input_sha, "boundary_sha": boundary_sha,
                   "reference": receipt_path}
        return receipt_path, context

    def test_disk_reference_projection_verifies_inventory_and_calibrates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference, ctx = self._make_disk_reference(root)
            result = response._disk_reference_projection(
                reference, "COUPLED", ctx["source_sha"], ctx["namelist_sha"],
                ctx["input_hashes"], ctx["executable_sha"], ctx["input_sha"],
                ctx["boundary_sha"], None)
            expected = 3 * ((len(b"step trace payload") + len(b"first-call raw trace") +
                             len(b"history bytes") + 1) // 2) + 64 * 1024 * 1024
            self.assertEqual(result["per_step_projection_bytes"], expected)
            self.assertEqual(result["source_trace_uncompressed_bytes"],
                             len(b"step trace payload") + len(b"first-call raw trace"))
            self.assertEqual(result["compressed_archive_count"], 2)
            self.assertEqual(result["reference_preflight_sha256"],
                             response.sha256(reference.parent / "preflight.json"))

    def test_disk_reference_rejects_incomplete_or_changed_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference, ctx = self._make_disk_reference(root)
            receipt = json.loads(reference.read_text())
            receipt["returncode"] = 1
            reference.write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError, "incomplete"):
                response._disk_reference_projection(
                    reference, "COUPLED", ctx["source_sha"], ctx["namelist_sha"],
                    ctx["input_hashes"], ctx["executable_sha"], ctx["input_sha"],
                    ctx["boundary_sha"], None)
            receipt["returncode"] = 0
            reference.write_text(json.dumps(receipt))
            (reference.parent / "run" / "trace.raw.gz").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "artifact changed"):
                response._disk_reference_projection(
                    reference, "COUPLED", ctx["source_sha"], ctx["namelist_sha"],
                    ctx["input_hashes"], ctx["executable_sha"], ctx["input_sha"],
                    ctx["boundary_sha"], None)

    def test_disk_reference_rejects_candidate_build_metadata_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reference, ctx = self._make_disk_reference(root)
            preflight_path = reference.parent / "preflight.json"
            preflight = json.loads(preflight_path.read_text())
            receipt = json.loads(reference.read_text())
            build = {"receipt_path": str(root / "build_receipt.json"),
                     "executable_sha256": "7" * 64}
            preflight["candidate_build"] = build
            receipt["candidate_build"] = build
            receipt["expected_executed_executable_sha256"] = build["executable_sha256"]
            receipt["executed_executable_sha256"] = build["executable_sha256"]
            preflight_path.write_text(json.dumps(preflight))
            reference.write_text(json.dumps(receipt))
            with patch.object(response, "_candidate_build_binding", return_value=build):
                result = response._disk_reference_projection(
                    reference, "COUPLED", ctx["source_sha"], ctx["namelist_sha"],
                    ctx["input_hashes"], ctx["executable_sha"], ctx["input_sha"],
                    ctx["boundary_sha"], None)
                self.assertEqual(result["compressed_archive_count"], 2)
                receipt["candidate_build"] = {**build, "executable_sha256": "8" * 64}
                reference.write_text(json.dumps(receipt))
                with self.assertRaisesRegex(ValueError, "candidate build differs"):
                    response._disk_reference_projection(
                        reference, "COUPLED", ctx["source_sha"], ctx["namelist_sha"],
                        ctx["input_hashes"], ctx["executable_sha"], ctx["input_sha"],
                        ctx["boundary_sha"], None)

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
            path.write_bytes(b"".join(record(step, float(step)) for step in (1, 2, 3, 15, 16, 30)))
            result = response.read_time_snapshots(path)
        self.assertEqual(result["timesteps"], [1, 2, 3, 15, 16, 30])
        self.assertEqual(result["completed_post_kdm6_timesteps"], [1, 2, 3, 15, 16, 30])
        self.assertEqual(set(result["snapshots"]), {"20s", "1min", "5min", "320s", "10min"})
        self.assertEqual(result["snapshots"]["5min"]["model_seconds"], 300)
        self.assertEqual(result["snapshots"]["320s"]["fields"]["QC"]["max"], 16.0)
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

    def test_duration_schedule_includes_frozen_milestones_and_final_step(self) -> None:
        expected = {
            20: {1: "20s"},
            40: {1: "20s", 2: "40s"},
            60: {1: "20s", 3: "1min"},
            300: {1: "20s", 3: "1min", 15: "5min"},
            320: {1: "20s", 3: "1min", 15: "5min", 16: "320s"},
            600: {1: "20s", 3: "1min", 15: "5min", 16: "320s", 30: "10min"},
        }
        for duration, schedule in expected.items():
            with self.subTest(duration=duration):
                self.assertEqual(response.snapshot_schedule(duration), schedule)
        with self.assertRaisesRegex(ValueError, "positive multiple"):
            response.snapshot_schedule(30)

    def test_finalizer_completes_each_supported_duration_schedule(self) -> None:
        for duration in (20, 40, 60, 300, 320, 600):
            with self.subTest(duration=duration), tempfile.TemporaryDirectory() as directory:
                out = make_finalizer_fixture(Path(directory), duration)
                receipt = response.finalize_existing_run("OFF", out, duration)
                self.assertEqual(receipt["status"], "COMPLETE")
                self.assertEqual(receipt["final_completed_step"], duration // 20)
                self.assertEqual(set(receipt["snapshots"]["snapshots"]),
                                 set(response.snapshot_schedule(duration).values()))
                self.assertEqual(receipt["expected_model_timestamps"][-1],
                                 (response.dt.datetime(2026, 8, 16, 13) +
                                  response.dt.timedelta(seconds=duration)).strftime("%Y-%m-%d_%H:%M:%S"))

    def test_finalizer_rejects_gaps_duplicates_truncation_and_fatal_output(self) -> None:
        cases = (
            ("gap", {"steps": (1, 3)}),
            ("duplicate", {"duplicate_step": 2}),
            ("truncated", {"truncate": True}),
            ("fatal", {"fatal": True}),
        )
        for name, fixture_options in cases:
            with self.subTest(case=name), tempfile.TemporaryDirectory() as directory:
                out = make_finalizer_fixture(Path(directory), 60, **fixture_options)
                receipt = response.finalize_existing_run("OFF", out, 60)
                self.assertEqual(receipt["status"], "INCOMPLETE")

    def test_kdm6_invalid_base_is_fatal_but_admission_diagnostics_are_not(self) -> None:
        diagnostic = "deferred admission: no eligible nongraupel candidate\n"
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory)
            (stage / "rsl.error.0000").write_text(diagnostic)
            self.assertEqual(response._fatal_lines(stage), ([], []))

            (stage / "rsl.error.0000").write_text(
                diagnostic + "KDM6 invalid base before nongraupel admission\n")
            fatal, issues = response._fatal_lines(stage)
            self.assertEqual(issues, [])
            self.assertEqual(fatal, ["KDM6 invalid base before nongraupel admission"])

        with tempfile.TemporaryDirectory() as directory:
            out = make_finalizer_fixture(
                Path(directory), 20,
                rsl_error=(diagnostic + "KDM6 invalid base before nongraupel admission\n"))
            stage = out / "run"
            with response.gzip.open(stage / "rsl.error.0000.gz", "wt") as stream:
                stream.write((stage / "rsl.error.0000").read_text())
            (stage / "rsl.error.0000").unlink()
            receipt = response.finalize_existing_run("OFF", out, 20)
            self.assertEqual(receipt["status"], "INCOMPLETE")
            self.assertEqual(receipt["earliest_fatal"],
                             "KDM6 invalid base before nongraupel admission")

    def test_bare_warm_endpoint_failure_is_fatal(self) -> None:
        message = "KDM6 warm native endpoint search failed"
        with tempfile.TemporaryDirectory() as directory:
            out = make_finalizer_fixture(Path(directory), 20, rsl_error=message + "\n")
            receipt = response.finalize_existing_run("OFF", out, 20)
            self.assertEqual(receipt["status"], "INCOMPLETE")
            self.assertEqual(receipt["earliest_fatal"], message)

    def test_bare_rain_packet_rejection_is_fatal(self) -> None:
        message = "PR87 rain sedimentation packet rejected"
        with tempfile.TemporaryDirectory() as directory:
            out = make_finalizer_fixture(Path(directory), 20, rsl_error=message + "\n")
            receipt = response.finalize_existing_run("OFF", out, 20)
            self.assertEqual(receipt["status"], "INCOMPLETE")
            self.assertEqual(receipt["earliest_fatal"], message)

    def test_bare_progb_rejection_is_fatal(self) -> None:
        message = "ProgB unsupported PSD state rejected"
        with tempfile.TemporaryDirectory() as directory:
            out = make_finalizer_fixture(Path(directory), 20, rsl_error=message + "\n")
            receipt = response.finalize_existing_run("OFF", out, 20)
            self.assertEqual(receipt["status"], "INCOMPLETE")
            self.assertEqual(receipt["earliest_fatal"], message)

    def test_computed_model_end_time_matches_duration(self) -> None:
        start = "start_year = 2026, start_month = 08, start_day = 16, start_hour = 13, start_minute = 00, start_second = 00,"
        self.assertEqual(response.model_end_time(start, 40), "2026-08-16_13:00:40")

    def test_prepare_records_computed_end_time(self) -> None:
        namelist = """&time_control
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
"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime_OFF"
            runtime.mkdir()
            (runtime / "wrf.exe").write_bytes(b"exe")
            (runtime / "wrfinput_d01").write_bytes(b"input")
            (runtime / "wrfbdy_d01").write_bytes(b"boundary")
            (runtime / "rsl.error.0000").write_bytes(b"log")
            (runtime / "namelist.input").write_text(namelist)
            (runtime / "namelist.input.source").write_text(namelist)
            (runtime / "auxiliary.dat").write_bytes(b"aux")
            input_names = ("namelist.input", "namelist.input.source", "auxiliary.dat")
            inputs = [{"path": str(runtime / name), "sha256_after": response.sha256(runtime / name)}
                      for name in input_names]
            receipt = {"native_executable_sha256": response.sha256(runtime / "wrf.exe"),
                       "candidate_wrfinput_sha256": response.sha256(runtime / "wrfinput_d01"),
                       "candidate_wrfbdy_sha256": response.sha256(runtime / "wrfbdy_d01"),
                       "native_trace_outputs": {}, "run_isolation": {"inputs": inputs}}
            receipt_path = root / "receipt.json"
            receipt_path.write_text(json.dumps(receipt))
            with patch.object(response, "RUNTIME", root / "runtime_{arm}"), \
                 patch.object(response, "RUN_RECEIPT", root / "receipt_{arm}.json"):
                (root / "receipt_OFF.json").write_text(json.dumps(receipt))
                prepared = response.prepare("OFF", 40, root / "output")
        self.assertEqual(prepared["namelist_changes"]["end_time"], "2026-08-16_13:00:40")

    def test_candidate_executable_stage_swap_keeps_baseline_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime"
            runtime.mkdir()
            baseline_executable = b"baseline frozen executable"
            candidate_executable = b"candidate overlay executable"
            shared_input = b"unchanged baseline input"
            (runtime / "wrf.exe").write_bytes(baseline_executable)
            (runtime / "other.dat").write_bytes(shared_input)
            (runtime / "namelist.input.source").write_text("source namelist")
            candidate = root / "candidate.exe"
            candidate.write_bytes(candidate_executable)
            baseline_hash = hashlib.sha256(baseline_executable).hexdigest()
            shared_hash = hashlib.sha256(shared_input).hexdigest()
            candidate_hash = hashlib.sha256(candidate_executable).hexdigest()
            prepared = {"runtime_dir": str(runtime), "input_hashes": {
                            "wrf.exe": baseline_hash, "other.dat": shared_hash},
                        "candidate_build": {"executable_path": str(candidate),
                                            "executable_sha256": candidate_hash},
                        "namelist_text": "candidate namelist", "namelist_diff": ""}

            stage = response._stage(prepared, root / "output")

            self.assertEqual((runtime / "wrf.exe").read_bytes(), baseline_executable)
            staged_hashes = {name: response.sha256(stage / name) for name in prepared["input_hashes"]}
            expected_hashes = {name: response._staged_expected_hash(
                name, prepared["input_hashes"], prepared["candidate_build"])
                for name in prepared["input_hashes"]}
            self.assertEqual(staged_hashes, expected_hashes)
            self.assertNotEqual(expected_hashes["wrf.exe"], baseline_hash)


if __name__ == "__main__":
    unittest.main()
