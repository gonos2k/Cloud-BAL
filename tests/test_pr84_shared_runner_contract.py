from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "tests"))
SPEC = importlib.util.spec_from_file_location(
    "pr82_shared_runner", Path(__file__).with_name("run_pr82_same13_native_initialization.py")
)
assert SPEC is not None and SPEC.loader is not None
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)
import pr83_moment_candidate_readback as READBACK


class Pr84SharedRunnerContractTests(unittest.TestCase):
    def _inputs(self, root: Path) -> tuple[Path, Path, Path, Path, Path]:
        runtime = root / "runtime"
        real_case = root / "real"
        runtime.mkdir()
        real_case.mkdir()
        (runtime / "met_em.d01.nc").write_bytes(b"static runtime")
        source = real_case / "wrfinput_d01"
        source.write_bytes(b"OFF source")
        (real_case / "wrfbdy_d01").write_bytes(b"boundary")
        nml = ("&time_control\n run_seconds = 0,\n end_hour = 15,\n"
               " end_second = 00,\n start_hour = 13,\n start_second = 00,\n/\n"
               "&domains\n max_dom = 1,\n/\n"
               "&physics\n use_sh_qv                           = .true.\n"
               " sfcp_to_sfcp                        = .true.\n mp_physics                          = 37,\n/\n")
        (real_case / "namelist.input").write_text(nml)
        executable = root / "wrf.exe"
        executable.write_bytes(b"wrong binary")
        candidate = root / "prior-input"
        candidate.write_bytes(b"candidate")
        policy_path = root / "policy.json"
        pidni = np.float32(np.pi * 500.0)
        policy = {
            "schema": READBACK.PR84_POLICY_SCHEMA,
            "policy_id": "SAME13_KDM6_NATIVE_MOMENT_PRIOR_20261013_V2",
            "declared_before_experiment": True,
            "status": "RESEARCH_PRIOR_NOT_OPERATIONAL_OR_SCIENCE_APPROVAL",
            "prior": {"active_domain_mode": "FULL_NATIVE_HORIZONTAL"},
            "species": {"QICE": {
                "internal_number_cap_mode": "SOURCE_PSD_COMPATIBLE_ENTRY_GUARD",
                "source_pidni_binary32_value": float(pidni),
                "source_pidni_binary32_hex": f"{int(pidni.view(np.uint32)):08x}",
                "shape_exponent_d": 3,
                "lambda_min_m-1": 9080.0,
            }},
            "preflight": {
                "authorized_source_inputs": [
                    {"role": role, "sha256": digest}
                    for role, digest in READBACK.PR84_SOURCE_INPUTS.items()
                ],
                "expected_source_valid_time": READBACK.TIME,
                "expected_input_spatial_shape_bottom_top_south_north_west_east": [39, 282, 234],
            },
            "source": {"runtime_consumer_executable_sha256": hashlib.sha256(b"expected binary").hexdigest()},
        }
        policy_path.write_text(json.dumps(policy, sort_keys=True))
        receipt_path = root / "prior-receipt.json"
        receipt_path.write_text(json.dumps({
            "schema": "pr83_same13_native_moment_prior_receipt_v1",
            "status": "RESEARCH_PRIOR_CREATED",
            "policy_schema": READBACK.PR84_POLICY_SCHEMA,
            "policy_id": policy["policy_id"],
            "policy_sha256": hashlib.sha256(policy_path.read_bytes()).hexdigest(),
            "source_input": str(source),
            "source_input_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "source_input_role": "OFF",
            "output_input": str(candidate),
            "output_input_sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
            "all_other_variables_unchanged": True,
            "changed_nonmoment_variables": [],
        }))
        return runtime, real_case, executable, receipt_path, policy_path

    def _args(self, root: Path, paths: tuple[Path, Path, Path, Path, Path]) -> SimpleNamespace:
        runtime, real_case, executable, receipt, policy = paths
        nml_sha = hashlib.sha256((real_case / "namelist.input").read_bytes()).hexdigest()
        return SimpleNamespace(runtime_case=runtime, real_case=real_case, executable=executable,
                               run_dir=root / "must-not-create", initialized_input_receipt=receipt,
                               initialized_input_policy=policy, source_namelist_sha=nml_sha)

    def test_wrong_consumer_executable_fails_before_run_dir_and_launcher(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = self._inputs(root)
            args = self._args(root, paths)
            policy_sha = hashlib.sha256(paths[4].read_bytes()).hexdigest()
            with patch.object(READBACK, "EXPECTED_PR84_POLICY_SHA256", policy_sha), \
                    patch.object(RUNNER, "run_isolated") as launch:
                with self.assertRaisesRegex(ValueError, "runtime executable differs"):
                    RUNNER.run_initialization(args, required_source_namelist_sha=args.source_namelist_sha)
            launch.assert_not_called()
            self.assertFalse(args.run_dir.exists())

    def test_invalid_boundary_summary_fails_before_run_dir_and_launcher(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = self._inputs(root)
            executable = root / "expected.exe"
            executable.write_bytes(b"expected binary")
            paths = (*paths[:2], executable, *paths[3:])
            args = self._args(root, paths)
            policy_sha = hashlib.sha256(paths[4].read_bytes()).hexdigest()
            with patch.object(READBACK, "EXPECTED_PR84_POLICY_SHA256", policy_sha), \
                    patch.object(RUNNER, "summarize_boundary", return_value={"status": "BLOCKED_BOUNDARY_SUPPORT"}), \
                    patch.object(RUNNER, "run_isolated") as launch:
                with self.assertRaisesRegex(ValueError, "wrfbdy does not pass"):
                    RUNNER.run_initialization(args, required_source_namelist_sha=args.source_namelist_sha)
            launch.assert_not_called()
            self.assertFalse(args.run_dir.exists())

    def test_pr67_trace_created_by_launcher_is_bound_in_native_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = self._inputs(root)
            _runtime, real_case, _executable, _receipt, _policy = paths
            args = self._args(root, paths)
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


if __name__ == "__main__":
    unittest.main()
