from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import test_pr84_shared_runner_contract as base_module
RUNNER = base_module.RUNNER


class TestPR84SharedRunnerNativeEvidence(unittest.TestCase):
    def test_pr67_trace_created_by_launcher_is_bound_in_native_receipt(self):
        base = base_module.Pr84SharedRunnerContractTests()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = base._inputs(root)
            _runtime, real_case, _executable, _receipt, _policy = paths
            args = base._args(root, paths)
            args.initialized_input_receipt = None
            args.initialized_input_policy = None
            args.run_dir = root / "receipt-run"
            boundary = real_case / "wrfbdy_d01"
            boundary_sha = hashlib.sha256(boundary.read_bytes()).hexdigest()
            trace_bytes = b"PR67 captured by the mocked native launcher\x00\x01"
            observed_reserved_outputs: list[str] = []

            def launch(run_dir, inputs, outputs, command, *, reserved_outputs):
                self.assertTrue(run_dir.is_dir())
                self.assertIn("pr67_kdm6_process.raw", reserved_outputs)
                observed_reserved_outputs.extend(reserved_outputs)
                (run_dir / "pr67_kdm6_process.raw").write_bytes(trace_bytes)
                return {
                    "returncode": 0,
                    "input_integrity": "PASS",
                    "output_isolation": "PASS",
                }

            source_namelist_sha = hashlib.sha256((real_case / "namelist.input").read_bytes()).hexdigest()
            with patch.object(RUNNER, "EXPECTED_RETAINED_BOUNDARY_SHA256", boundary_sha), \
                    patch.object(RUNNER, "run_isolated", side_effect=launch):
                result = RUNNER.run_initialization(
                    args,
                    required_baseline_input=hashlib.sha256(
                        (real_case / "wrfinput_d01").read_bytes()
                    ).hexdigest(),
                    control_role="MODE_OFF_MASS_ONLY",
                    required_source_namelist_sha=source_namelist_sha,
                    allow_prior=False,
                )

            self.assertEqual(result, 1)  # Initialization readback is absent in this receipt-path fixture.
            self.assertIn("pr67_kdm6_process.raw", observed_reserved_outputs)
            receipt = json.loads((args.run_dir / "pr83_same13_off_native_initialization.json").read_text())
            trace_record = receipt["native_trace_outputs"]["pr67_kdm6_process.raw"]
            self.assertEqual(trace_record["bytes"], len(trace_bytes))
            self.assertEqual(trace_record["sha256"], hashlib.sha256(trace_bytes).hexdigest())
