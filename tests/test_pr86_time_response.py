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


def make_hydro_binding(root: Path) -> dict:
    artifacts = {}
    for name in ("wrfinput", "wrfbdy", "source_candidate", "moment_policy", "initialization_receipt", "source_chain"):
        path = root / name
        path.write_bytes(("HYDRO " + name).encode())
        artifacts[name] = {"path": str(path), "sha256": response.sha256(path)}
    receipt = {"schema": "pr94_hydro_native_input_v1", "role": "HYDRO",
               "status": "PASS_HYDRO_NATIVE_INPUT",
               **{key: value for key, value in artifacts.items() if key != "source_chain"},
               "source_chain_receipts": [artifacts["source_chain"]],
               "comparison_contract": {"physics": "frozen C4"}}
    path = root / "hydro_input.json"
    path.write_text(json.dumps(receipt))
    return response._hydro_input_binding(path)


def make_native_input_binding(root: Path) -> dict:
    artifacts = {}
    for name in ("candidate", "parent", "reference", "boundary", "generator", "composition"):
        path = root / f"native_{name}"
        path.write_bytes(("native " + name).encode())
        artifacts[name] = {"path": str(path), "sha256": response.sha256(path)}
    receipt = {"schema": "pr99_native_uv_projection_proposal_v1",
               "status": "PROPOSAL_REQUIRES_NATIVE_CONSUMER_AND_TENDENCY_VALIDATION",
               "role": "COUPLED", **artifacts,
               "composition_sha256": artifacts["composition"]["sha256"]}
    path = root / "native_input.json"
    path.write_text(json.dumps(receipt))
    return response._native_input_binding(path)


class TimeResponseTests(unittest.TestCase):
    def test_structured_capture_requires_matching_archived_consumer_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifacts = {}
            for name in ("candidate", "original_p", "reference_hydro", "reference_coupled",
                         "boundary", "generator", "policy", "composition"):
                path = root / f"wind_{name}"
                path.write_bytes(name.encode())
                artifacts[name] = {"path": str(path), "sha256": response.sha256(path)}
            proposal = {"schema": "pr102_wind_structure_proposal_v1",
                        "status": "PROPOSAL_REQUIRES_NATIVE_CONSUMER_AND_SOURCE_CAPTURE",
                        "role": "COUPLED", **artifacts,
                        "composition_sha256": artifacts["composition"]["sha256"],
                        "parent_sha256": artifacts["original_p"]["sha256"],
                        "change_contract": {"changed_variables": ["U", "V"],
                                             "non_target_variables_identical": True}}
            proposal_path = root / "proposal.json"
            proposal_path.write_text(json.dumps(proposal))
            binding = response._wind_structure_input_binding(proposal_path)
            evidence = root / "consumer_evidence.txt"
            evidence.write_text("archived consumer output")
            consumer = {"schema": "pr102_native_consumer_check_v1", "status": "COMPLETE",
                        "native_consumer": "module_big_step_utilities_em_mp_calc_ww_cp_",
                        "candidate_wrfinput_sha256": artifacts["candidate"]["sha256"],
                        "archive_member_sha256": "8f7a0666664bdccb45c414cb9e6ec481f7daaad3fa6170f0d51f524515572343",
                        "compiler_profile_sha256": "5439fa3a692acc9ee63571ee8dd8ff1ce50d1810e9339d9ead906f3c817111b4",
                        "dry_mass_check": {"schema": "pr102_native_drymass_constraint_v1", "status": "PASS",
                                           "finite": True,
                                           "composition_sha256": binding["composition_sha256"],
                                           "consumer": "module_big_step_utilities_em_mp_calc_ww_cp_",
                                           "comparison": "candidate_minus_HYDRO", "units": "Pa/s",
                                           "support_count": 10,
                                           "reference_constraint": {"status": "PASS",
                                               "observed_l2_pa_s": 1e-9, "allowed_l2_pa_s": 1e-8,
                                               "observed_max_abs_pa_s": 1e-10, "allowed_max_abs_pa_s": 1e-9},
                                           "source_arithmetic": {"status": "PASS",
                                               "observed_l2_pa_s": 1e-9, "allowed_l2_pa_s": 1e-8,
                                               "observed_max_abs_pa_s": 1e-10, "allowed_max_abs_pa_s": 1e-9}},
                        "artifacts": [{"path": str(evidence), "sha256": response.sha256(evidence)}]}
            consumer_path = root / "consumer.json"
            consumer_path.write_text(json.dumps(consumer))
            pin = response._validate_pr102_consumer_capture(consumer_path, binding)
            self.assertEqual(pin["status"], "COMPLETE")
            self.assertEqual(pin["sha256"], response.sha256(consumer_path))
            consumer["candidate_wrfinput_sha256"] = "wrong candidate"
            consumer_path.write_text(json.dumps(consumer))
            with self.assertRaisesRegex(ValueError, "does not bind this candidate"):
                response._validate_pr102_consumer_capture(consumer_path, binding)
            consumer["candidate_wrfinput_sha256"] = artifacts["candidate"]["sha256"]
            consumer["dry_mass_check"]["reference_constraint"]["status"] = "FAIL"
            consumer_path.write_text(json.dumps(consumer))
            with self.assertRaisesRegex(ValueError, "reference_constraint gate"):
                response._validate_pr102_consumer_capture(consumer_path, binding)

    def test_structured_capture_is_one_step_and_requires_consumer_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "one 20-second step"):
                response.prepare("STRUCTURED_CAPTURE", 640, root / "wrong_duration",
                                 wind_structure_input_receipt_path=root / "proposal.json")
            with self.assertRaisesRegex(ValueError, "explicit C2 build and passing archived consumer"):
                response.prepare("STRUCTURED_CAPTURE", 20, root / "missing_consumer",
                                 candidate_build_path=root / "build.json",
                                 wind_structure_input_receipt_path=root / "proposal.json")

    def test_structured_baseline20_requires_exact_c2_executable(self) -> None:
        response._require_pr102_base_c2({
            "executable_sha256": response.PR102_BASE_C2_EXECUTABLE_SHA256})
        with self.assertRaisesRegex(ValueError, "exact matched base C2 executable"):
            response._require_pr102_base_c2({"executable_sha256": "wrong"})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "one 20-second step"):
                response.prepare("STRUCTURED_BASELINE20", 640, root / "wrong_duration",
                                 wind_structure_input_receipt_path=root / "proposal.json")
            with self.assertRaisesRegex(ValueError, "explicit base C2 build receipt"):
                response.prepare("STRUCTURED_BASELINE20", 20, root / "missing_build",
                                 wind_structure_input_receipt_path=root / "proposal.json")

    def test_hydro_binding_rejects_changed_artifact_and_failed_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binding = make_hydro_binding(root)
            self.assertTrue(response._input_binding_unchanged(binding))
            (root / "source_chain").write_text("changed source provenance")
            with self.assertRaisesRegex(ValueError, "artifact changed"):
                response._input_binding_unchanged(binding)
            path = Path(binding["receipt_path"])
            receipt = json.loads(path.read_text())
            receipt["status"] = "FAILED"
            path.write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError, "source-bound"):
                response._hydro_input_binding(path)

    def test_native_binding_checks_every_declared_artifact_and_proposal_identity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binding = make_native_input_binding(root)
            self.assertTrue(response._input_binding_unchanged(binding))
            for name in ("candidate", "parent", "reference", "boundary", "generator", "composition"):
                with self.subTest(artifact=name):
                    path = Path(binding["artifacts"][name]["path"])
                    original = path.read_bytes()
                    path.write_bytes(original + b" changed")
                    with self.assertRaisesRegex(ValueError, "native proposal artifact changed"):
                        response._input_binding_unchanged(binding)
                    path.write_bytes(original)
            path = Path(binding["receipt_path"])
            receipt = json.loads(path.read_text())
            receipt["role"] = "HYDRO"
            path.write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError, "COUPLED native input proposal"):
                response._native_input_binding(path)

    def test_native_binding_requires_frozen_coupled_parent_and_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binding = make_native_input_binding(root)
            parent = binding["artifacts"]["parent"]["sha256"]
            boundary = binding["artifacts"]["boundary"]["sha256"]
            response._validate_native_template(
                binding, {"candidate_wrfinput_sha256": parent, "candidate_wrfbdy_sha256": boundary})
            with self.assertRaisesRegex(ValueError, "parent differs"):
                response._validate_native_template(
                    binding, {"candidate_wrfinput_sha256": "wrong", "candidate_wrfbdy_sha256": boundary})
            with self.assertRaisesRegex(ValueError, "boundary differs"):
                response._validate_native_template(
                    binding, {"candidate_wrfinput_sha256": parent, "candidate_wrfbdy_sha256": "wrong"})

    def test_native_candidate_is_staged_and_hydro_arm_rejects_native_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binding = make_native_input_binding(root)
            runtime = root / "runtime"
            runtime.mkdir()
            (runtime / "wrfinput_d01").write_bytes(b"frozen parent")
            (runtime / "namelist.input.source").write_text("source namelist")
            prepared = {"runtime_dir": str(runtime),
                        "input_hashes": {"wrfinput_d01": response.sha256(runtime / "wrfinput_d01")},
                        "candidate_input_binding": binding,
                        "candidate_wrfinput_sha256": binding["artifacts"]["candidate"]["sha256"],
                        "namelist_text": "candidate namelist", "namelist_diff": ""}
            stage = response._stage(prepared, root / "output")
            self.assertEqual(response.sha256(stage / "wrfinput_d01"), prepared["candidate_wrfinput_sha256"])
            with self.assertRaisesRegex(ValueError, "only valid for COUPLED or PROJECTED"):
                response.prepare("OFF", 20, root / "rejected", native_input_receipt_path=Path(binding["receipt_path"]))
            with self.assertRaisesRegex(ValueError, "HYDRO requires its own input receipt"):
                response.prepare("HYDRO", 20, root / "rejected_hydro",
                                 native_input_receipt_path=Path(binding["receipt_path"]))
            with self.assertRaisesRegex(ValueError, "limited to one 20-second step"):
                response.prepare("COUPLED", 40, root / "rejected_longrun",
                                 native_input_receipt_path=Path(binding["receipt_path"]))

    def test_projected_arm_requires_receipt_candidate_build_and_matched_duration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binding = make_native_input_binding(root)
            receipt_path = Path(binding["receipt_path"])
            with self.assertRaisesRegex(ValueError, "requires a source-bound"):
                response.prepare("PROJECTED", 640, root / "missing_receipt")
            with self.assertRaisesRegex(ValueError, "explicit C2 candidate build"):
                response.prepare("PROJECTED", 640, root / "missing_build",
                                 native_input_receipt_path=receipt_path)
            with self.assertRaisesRegex(ValueError, "matched 640-second run"):
                response.prepare("PROJECTED", 20, root / "wrong_duration",
                                 candidate_build_path=root / "unused_build.json",
                                 native_input_receipt_path=receipt_path)

    def test_projected_native_binding_rejects_wrong_parent_or_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binding = make_native_input_binding(root)
            template = {"candidate_wrfinput_sha256": "wrong-parent",
                        "candidate_wrfbdy_sha256": binding["artifacts"]["boundary"]["sha256"]}
            with self.assertRaisesRegex(ValueError, "parent differs"):
                response._validate_native_template(binding, template)
            template["candidate_wrfinput_sha256"] = binding["artifacts"]["parent"]["sha256"]
            template["candidate_wrfbdy_sha256"] = "wrong-boundary"
            with self.assertRaisesRegex(ValueError, "boundary differs"):
                response._validate_native_template(binding, template)

    def test_projected_finalizer_rejects_missing_input_binding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            out = make_finalizer_fixture(root, 640)
            preflight_path = out / "preflight.json"
            preflight = json.loads(preflight_path.read_text())
            preflight.update(arm="PROJECTED", template_arm="COUPLED", duration_seconds=640,
                             candidate_input_binding=None, candidate_build=None)
            preflight_path.write_text(json.dumps(preflight))
            launch_path = out / "receipt.json"
            launch = json.loads(launch_path.read_text())
            launch.update(arm="PROJECTED", candidate_input_binding=None)
            launch_path.write_text(json.dumps(launch))
            result = response.finalize_existing_run("PROJECTED", out, 640)
            self.assertEqual(result["status"], "INCOMPLETE")
            self.assertIn("PROJECTED arm requires its source-bound native projection input",
                          result["processing_errors"])

    def test_native_finalizer_requires_coupled_role_template_and_launch_binding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binding = make_native_input_binding(root)
            out = make_finalizer_fixture(root, 20)
            preflight_path = out / "preflight.json"
            preflight = json.loads(preflight_path.read_text())
            template_path = Path(preflight["source_receipt"])
            template = json.loads(template_path.read_text())
            template.update(candidate_wrfinput_sha256=binding["artifacts"]["parent"]["sha256"],
                            candidate_wrfbdy_sha256=binding["artifacts"]["boundary"]["sha256"])
            template_path.write_text(json.dumps(template))
            preflight.update(arm="COUPLED", template_arm="COUPLED", duration_seconds=20,
                            candidate_input_binding=binding,
                            candidate_wrfinput_sha256=binding["artifacts"]["candidate"]["sha256"],
                            candidate_wrfbdy_sha256=binding["artifacts"]["boundary"]["sha256"],
                            source_receipt_sha256=response.sha256(template_path))
            preflight_path.write_text(json.dumps(preflight))
            launch = {"returncode": 0, "arm": "COUPLED", "compressed_outputs": [],
                      "candidate_input_binding": binding,
                      "candidate_wrfinput_sha256": preflight["candidate_wrfinput_sha256"]}
            (out / "receipt.json").write_text(json.dumps(launch))
            self.assertEqual(response.finalize_existing_run("COUPLED", out, 20)["status"], "COMPLETE")
            launch["arm"] = "HYDRO"
            (out / "receipt.json").write_text(json.dumps(launch))
            result = response.finalize_existing_run("COUPLED", out, 20)
            self.assertEqual(result["status"], "INCOMPLETE")
            self.assertIn("COUPLED native proposal provenance differs from preflight",
                          result["processing_errors"])
            launch["arm"] = "COUPLED"
            (out / "receipt.json").write_text(json.dumps(launch))
            result = response.finalize_existing_run("COUPLED", out, 40)
            self.assertEqual(result["status"], "INCOMPLETE")
            self.assertIn("COUPLED native proposal provenance differs from preflight",
                          result["processing_errors"])

    def test_hydro_stage_preserves_off_template_and_checks_injected_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binding = make_hydro_binding(root)
            runtime = root / "runtime"
            runtime.mkdir()
            (runtime / "wrfinput_d01").write_bytes(b"original OFF input")
            (runtime / "namelist.input.source").write_text("source namelist")
            original_hash = response.sha256(runtime / "wrfinput_d01")
            input_hash = binding["artifacts"]["wrfinput"]["sha256"]
            prepared = {"runtime_dir": str(runtime), "input_hashes": {"wrfinput_d01": original_hash},
                        "candidate_input_binding": binding, "candidate_wrfinput_sha256": input_hash,
                        "namelist_text": "HYDRO namelist", "namelist_diff": ""}
            stage = response._stage(prepared, root / "output")
            self.assertEqual(response.sha256(runtime / "wrfinput_d01"), original_hash)
            self.assertEqual(response.sha256(stage / "wrfinput_d01"), input_hash)
            self.assertEqual(response._staged_expected_hash("wrfinput_d01", prepared["input_hashes"],
                                                           None, None, input_hash), input_hash)
            (root / "source_candidate").write_text("changed upstream candidate")
            with self.assertRaisesRegex(ValueError, "artifact changed"):
                response._stage(prepared, root / "rejected_output")

    def test_stage_copies_template_inputs_and_isolates_staged_writes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime"
            runtime.mkdir()
            (runtime / "input.dat").write_bytes(b"frozen input")
            (runtime / "namelist.input.source").write_text("source namelist")
            prepared = {"runtime_dir": str(runtime), "input_hashes": {"input.dat": "unused"},
                        "namelist_text": "candidate namelist", "namelist_diff": ""}
            stage = response._stage(prepared, root / "copied")
            staged_input = stage / "input.dat"
            self.assertEqual(staged_input.read_bytes(), b"frozen input")
            self.assertNotEqual(staged_input.stat().st_ino, (runtime / "input.dat").stat().st_ino)
            staged_input.write_bytes(b"model changed staged auxiliary input")
            self.assertEqual((runtime / "input.dat").read_bytes(), b"frozen input")

    def test_corrupt_cross_device_copy_is_rejected_before_consumption(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime"
            runtime.mkdir()
            original = runtime / "input.dat"
            original.write_bytes(b"frozen input")
            (runtime / "namelist.input.source").write_text("source namelist")
            prepared = {"runtime_dir": str(runtime), "input_hashes": {"input.dat": response.sha256(original)},
                        "namelist_text": "candidate namelist", "namelist_diff": ""}
            copy = response.shutil.copy2
            def corrupt_input(source, destination):
                if Path(source).name == "input.dat":
                    Path(destination).write_bytes(b"corrupt copy")
                else:
                    copy(source, destination)
            with patch.object(response.shutil, "copy2", side_effect=corrupt_input):
                stage = response._stage(prepared, root / "output")
            with self.assertRaisesRegex(ValueError, "input.dat"):
                response.verify_staged_inputs(prepared, stage)
            self.assertEqual(original.read_bytes(), b"frozen input")

    def test_hydro_finalizer_rejects_changed_source_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binding = make_hydro_binding(root)
            out = make_finalizer_fixture(root, 40)
            preflight_path = out / "preflight.json"
            preflight = json.loads(preflight_path.read_text())
            input_sha = binding["artifacts"]["wrfinput"]["sha256"]
            preflight.update(arm="HYDRO", template_arm="OFF", candidate_input_binding=binding,
                             candidate_wrfinput_sha256=input_sha)
            preflight_path.write_text(json.dumps(preflight))
            launch = {"returncode": 0, "arm": "HYDRO", "compressed_outputs": [],
                      "candidate_input_binding": binding, "candidate_wrfinput_sha256": input_sha}
            (out / "receipt.json").write_text(json.dumps(launch))
            self.assertEqual(response.finalize_existing_run("HYDRO", out, 40)["status"], "COMPLETE")
            with self.subTest(missing_launch_binding=True):
                (out / "receipt.json").write_text(json.dumps({**launch, "candidate_input_binding": None}))
                self.assertEqual(response.finalize_existing_run("HYDRO", out, 40)["status"], "INCOMPLETE")
            (out / "receipt.json").write_text(json.dumps(launch))
            with self.subTest(wrong_arm=True):
                self.assertEqual(response.finalize_existing_run("OFF", out, 40)["status"], "INCOMPLETE")
            (out / "receipt.json").write_text(json.dumps(launch))
            (root / "source_chain").write_text("changed source provenance")
            result = response.finalize_existing_run("HYDRO", out, 40)
            self.assertEqual(result["status"], "INCOMPLETE")
            self.assertFalse(result["candidate_input_unchanged"])
            self.assertIn("HYDRO input binding changed after preflight", result["processing_errors"])

    def test_longrun_finalizer_requires_every_step_and_final_snapshot(self) -> None:
        for duration in (1800, 3600):
            with self.subTest(duration=duration), tempfile.TemporaryDirectory() as directory:
                out = make_finalizer_fixture(Path(directory), duration)
                result = response.finalize_existing_run("OFF", out, duration)
                self.assertEqual(result["status"], "COMPLETE")
                self.assertEqual(result["final_completed_step"], duration // 20)
                schedule = response.snapshot_schedule(duration)
                self.assertIn(90, schedule)
                self.assertIn(duration // 20, schedule)
            with self.subTest(duration=duration, missing=True), tempfile.TemporaryDirectory() as directory:
                steps = tuple(range(1, duration // 20))
                out = make_finalizer_fixture(Path(directory), duration, steps=steps)
                self.assertEqual(response.finalize_existing_run("OFF", out, duration)["status"], "INCOMPLETE")

    def test_diagnostic_identity_is_stable_and_distinguishes_runs(self) -> None:
        output = Path("/var/tmp/diagnostic run with spaces")
        identity = response.diagnostic_run_id("OFF", output)
        self.assertEqual(identity, response.diagnostic_run_id("OFF", output))
        self.assertRegex(identity, r"^OFF_[0-9a-f]{16}$")
        self.assertNotEqual(identity, response.diagnostic_run_id("COUPLED", output))
        self.assertNotEqual(identity, response.diagnostic_run_id("OFF", output / "other"))

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
            path.write_bytes(b"".join(record(step, float(step)) for step in (1, 2, 3, 15, 16, 24, 25, 30)))
            result = response.read_time_snapshots(path)
        self.assertEqual(result["timesteps"], [1, 2, 3, 15, 16, 24, 25, 30])
        self.assertEqual(result["completed_post_kdm6_timesteps"], [1, 2, 3, 15, 16, 24, 25, 30])
        self.assertEqual(set(result["snapshots"]), {"20s", "1min", "5min", "320s", "480s", "500s", "10min"})
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
            480: {1: "20s", 3: "1min", 15: "5min", 16: "320s", 24: "480s"},
            500: {1: "20s", 3: "1min", 15: "5min", 16: "320s", 24: "480s", 25: "500s"},
            600: {1: "20s", 3: "1min", 15: "5min", 16: "320s", 24: "480s", 25: "500s", 30: "10min"},
        }
        for duration, schedule in expected.items():
            with self.subTest(duration=duration):
                self.assertEqual(response.snapshot_schedule(duration), schedule)
        with self.assertRaisesRegex(ValueError, "positive multiple"):
            response.snapshot_schedule(30)

    def test_finalizer_completes_each_supported_duration_schedule(self) -> None:
        for duration in (20, 40, 60, 300, 320, 480, 500, 600):
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

    def test_bare_research_packet_rejections_are_fatal(self) -> None:
        for message in ("PR87 rain sedimentation packet rejected",
                        "PR85 invalid cloud-ice freezing packet base",
                        "PR93 invalid active ice PSD input"):
            with self.subTest(message=message), tempfile.TemporaryDirectory() as directory:
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
