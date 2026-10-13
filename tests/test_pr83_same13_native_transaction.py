from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
from types import SimpleNamespace
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PR83Same13NativeTransactionTests(unittest.TestCase):
    def test_pr82_default_provenance_has_no_optional_pr83_paths(self) -> None:
        runner = load_module("pr82_native_runner", ROOT / "tests/run_pr82_same13_native_initialization.py")
        paths = runner.provenance_paths()
        self.assertNotIn("native_moment_initializer", paths)
        self.assertNotIn("native_moment_policy", paths)
        self.assertTrue(all(isinstance(path, Path) and path.is_file() for path in paths.values()))

    def test_policy_reject_writes_evidence_without_creating_native_run_or_candidate(self) -> None:
        wrapper = load_module("pr83_native_wrapper", ROOT / "tests/run_pr83_same13_native_initialization.py")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real = root / "real"
            runtime = root / "runtime"
            real.mkdir()
            runtime.mkdir()
            source = real / "wrfinput_d01"
            source.write_bytes(b"immutable same13 source")
            executable = runtime / "wrf.exe"
            executable.write_bytes(b"retained test executable")
            policy = root / "policy.json"
            policy.write_text('{"policy_id":"PR83_TEST"}\n')
            run_root = root / "evidence"
            receipt_path = run_root / "pr83_same13_native_moment_prior.json"
            initializer_sha = hashlib.sha256((ROOT / "tools/initialize_native_moments.py").read_bytes()).hexdigest()

            def reject_prior(source_path, output_path, receipt_output, *, policy_path):
                self.assertEqual(source_path, source)
                self.assertEqual(policy_path, policy)
                receipt = {
                    "schema": "pr83_same13_native_moment_prior_receipt_v1",
                    "status": "BLOCKED_SOURCE_CAP_INFEASIBLE",
                    "initializer_sha256": initializer_sha,
                    "diagnostics": {"QNICE": {"unrepresentable_positive_mass_cells": 2305}},
                }
                receipt_output.write_text(json.dumps(receipt) + "\n")
                return receipt

            argv = ["run_pr83_same13_native_initialization.py",
                    "--runtime-case", str(runtime), "--real-case", str(real),
                    "--executable", str(executable), "--run-dir", str(run_root),
                    "--policy", str(policy)]
            with patch.object(wrapper, "initialize_same13_copy", side_effect=reject_prior), \
                    patch.object(wrapper.subprocess, "run", side_effect=AssertionError("native launch forbidden")), \
                    patch.object(sys, "argv", argv):
                self.assertEqual(wrapper.main(), 2)

            evidence = json.loads((run_root / "pr83_same13_native_initialization_evidence.json").read_text())
            self.assertEqual(evidence["native_status"], "SKIPPED_SOURCE_CAP_INFEASIBLE")
            self.assertFalse(evidence["native_launch_attempted"])
            self.assertFalse(evidence["native_output_directory_created"])
            self.assertEqual(evidence["native_runner_returncode"], None)
            self.assertEqual(evidence["policy_diagnostics"]["QNICE"]["unrepresentable_positive_mass_cells"], 2305)
            self.assertFalse((run_root / "wrfinput_d01.pr83").exists())
            self.assertFalse((run_root / "native").exists())
            self.assertEqual(source.read_bytes(), b"immutable same13 source")

    def test_initialization_pass_and_first_step_rejection_are_reported_separately(self) -> None:
        wrapper = load_module("pr83_native_wrapper_success", ROOT / "tests/run_pr83_same13_native_initialization.py")
        shared = load_module("pr82_native_runner_receipt", ROOT / "tests/run_pr82_same13_native_initialization.py")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real = root / "real"
            runtime = root / "runtime"
            real.mkdir()
            runtime.mkdir()
            source = real / "wrfinput_d01"
            source.write_bytes(b"immutable same13 source")
            executable = runtime / "wrf.exe"
            executable.write_bytes(b"retained test executable")
            policy = root / "policy.json"
            policy.write_text('{"policy_id":"PR83_TEST"}\n')
            run_root = root / "evidence"
            candidate = run_root / "wrfinput_d01.pr83"
            initializer_sha = hashlib.sha256(
                (ROOT / "tools/initialize_native_moments.py").read_bytes()
            ).hexdigest()

            def create_prior(source_path, output_path, receipt_output, *, policy_path):
                self.assertEqual(source_path, source)
                self.assertEqual(policy_path, policy)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b"authorized initialized candidate")
                receipt = {
                    "schema": "pr83_same13_native_moment_prior_receipt_v1",
                    "status": "RESEARCH_PRIOR_CREATED",
                    "initializer_sha256": initializer_sha,
                    "source_input_unchanged": True,
                }
                receipt_output.write_text(json.dumps(receipt) + "\n")
                return receipt

            def mocked_subprocess(command, **_kwargs):
                if "run_pr82_same13_native_initialization.py" in command[1]:
                    native_dir = Path(command[command.index("--run-dir") + 1])
                    native_dir.mkdir(parents=True)
                    shared.write_initialization_receipt(
                        native_dir,
                        {
                            "initialization_gate": "PASS_SCOPED_INITIALIZATION_READBACK",
                            "first_step_gate": "REJECTED_KDM6_UNSUPPORTED_NUMBER_BASIS",
                            "run_isolation": {"returncode": 128},
                            "native_trace_outputs": {},
                        },
                        control_role="PR82_MASS_ONLY",
                        has_prior=True,
                    )
                    (native_dir / "wrfout_d01_2026-08-16_13:00:00").write_bytes(b"mock initial wrfout")
                    return SimpleNamespace(returncode=0, stdout="", stderr="")
                self.assertIn("pr83_moment_candidate_readback.py", command[1])
                return SimpleNamespace(returncode=0, stdout="mock readback pass", stderr="")

            argv = ["run_pr83_same13_native_initialization.py",
                    "--runtime-case", str(runtime), "--real-case", str(real),
                    "--executable", str(executable), "--run-dir", str(run_root),
                    "--policy", str(policy)]
            with patch.object(wrapper, "initialize_same13_copy", side_effect=create_prior), \
                    patch.object(wrapper.subprocess, "run", side_effect=mocked_subprocess), \
                    patch.object(sys, "argv", argv):
                self.assertEqual(wrapper.main(), 0)

            evidence = json.loads((run_root / "pr83_same13_native_initialization_evidence.json").read_text())
            self.assertEqual(evidence["native_status"], "NATIVE_INITIALIZATION_READBACK_PASSED")
            self.assertEqual(evidence["native_runner_returncode"], 0)
            self.assertEqual(evidence["native_initialization_gate"], "PASS_SCOPED_INITIALIZATION_READBACK")
            self.assertEqual(evidence["native_model_returncode"], 128)
            self.assertEqual(evidence["first_step_status"], "REJECTED_KDM6_UNSUPPORTED_NUMBER_BASIS")
            self.assertEqual(evidence["wrapper_returncode_scope"],
                             "initialization runner and independent input/output readback only; "
                             "first-step outcome is reported separately")
            self.assertTrue(evidence["native_launch_attempted"])
            self.assertEqual(evidence["native_run_receipt_sha256"], hashlib.sha256(
                (run_root / "native/pr83_same13_native_initialization.json").read_bytes()
            ).hexdigest())
            self.assertTrue(candidate.is_file())


if __name__ == "__main__":
    unittest.main()
