from __future__ import annotations

import importlib.util
import hashlib
import json
import tempfile
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import patch

MODULE_PATH = Path(__file__).with_name("run_pr83_same13_off_native_initialization.py")
SPEC = importlib.util.spec_from_file_location("pr83_off_runner", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class OffRunnerContractTests(unittest.TestCase):
    def test_mode_off_runner_pins_exact_reviewed_namelist(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "namelist.input"
            source.write_bytes(b"same13 test source namelist")
            expected = hashlib.sha256(source.read_bytes()).hexdigest()
            with patch.object(RUNNER, "EXPECTED_OFF_SOURCE_NAMELIST_SHA256", expected):
                self.assertEqual(RUNNER.validate_off_source_namelist(source), expected)


    def test_mode_off_runner_rejects_changed_namelist_before_launch(self):
        with self.subTest("changed source namelist is rejected before launch"):
            with tempfile.TemporaryDirectory() as directory:
                changed = Path(directory) / "namelist.input"
                changed.write_text("&time_control\n run_seconds = 21,\n/\n")
                reviewed = Path(directory) / "reviewed.input"
                reviewed.write_text("&time_control\n run_seconds = 20,\n/\n")
                reviewed_sha = hashlib.sha256(reviewed.read_bytes()).hexdigest()
                with patch.object(RUNNER, "EXPECTED_OFF_SOURCE_NAMELIST_SHA256", reviewed_sha):
                    with self.assertRaisesRegex(ValueError, "reviewed same13 source namelist"):
                        RUNNER.validate_off_source_namelist(changed)

    def test_off_wrapper_pins_shared_runner_contract(self):
        arguments = ["--runtime-case", "/runtime", "--real-case", "/real",
                     "--executable", "/wrf.exe", "--run-dir", "/fresh"]
        with patch.object(RUNNER, "run_initialization", return_value=0) as shared:
            self.assertEqual(RUNNER.main(arguments), 0)
        options = shared.call_args.kwargs
        self.assertEqual(options["required_baseline_input"], RUNNER.EXPECTED_OFF_INPUT_SHA256)
        self.assertEqual(options["required_source_namelist_sha"],
                         RUNNER.EXPECTED_OFF_SOURCE_NAMELIST_SHA256)
        self.assertEqual(options["control_role"], "MODE_OFF_MASS_ONLY")
        self.assertFalse(options["allow_prior"])

    def test_shared_runner_rejects_prior_for_off_control(self):
        args = SimpleNamespace(initialized_input_receipt=Path("receipt.json"),
                               initialized_input_policy=Path("policy.json"))
        with self.assertRaisesRegex(ValueError, "cannot accept a PR83 prior"):
            RUNNER.run_initialization(args, allow_prior=False,
                                      control_role="MODE_OFF_MASS_ONLY")

    def test_successful_prior_uses_receipt_path_consumed_by_pr83_runner(self):
        schema, filename = RUNNER.initialization_receipt_contract(
            control_role="PR82_MASS_ONLY", has_prior=True)
        self.assertEqual(schema, "pr83_same13_native_initialization_v1")
        self.assertEqual(filename, "pr83_same13_native_initialization.json")
        with tempfile.TemporaryDirectory() as directory:
            receipt_path = RUNNER.write_initialization_receipt(
                Path(directory), {"status": "PASS_SCOPED_INITIALIZATION_READBACK"},
                control_role="PR82_MASS_ONLY", has_prior=True)
            stored = json.loads(receipt_path.read_text())
            self.assertEqual(stored["schema"], schema)
            self.assertEqual(receipt_path.name, "pr83_same13_native_initialization.json")


if __name__ == "__main__":
    unittest.main()
