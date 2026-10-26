from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pr103_archived_consumer as consumer
import pr86_time_response as runner


class ArchivedConsumerNativeTests(unittest.TestCase):
    def _closed_assessment(self, root: Path) -> tuple[Path, dict]:
        candidate = root / "candidate-input"
        candidate.write_bytes(b"candidate")
        parent_sha = "parent-p-sha"
        proposal_sha = "proposal-sha"
        candidate_sha = runner.sha256(candidate)
        candidate_dir = root / "call" / "candidate"
        candidate_dir.mkdir(parents=True)
        staged_executable = candidate_dir / "consumer.exe"
        staged_executable.write_bytes(consumer.archived.EXECUTABLE.read_bytes())
        ww = candidate_dir / "native_consumer_ww.bin"
        ww.write_bytes(b"closed ww")
        log = candidate_dir / "run.log"
        log.write_text("complete\n")
        input_binary = candidate_dir / "native_consumer_input.bin"
        input_binary.write_bytes(b"serialized input")
        exe = consumer.archived.EXECUTABLE.resolve()
        profile = consumer.archived.PROFILE.resolve()
        driver = consumer.archived.native.DRIVER.resolve()
        bindings = {str(candidate.resolve()): candidate_sha,
                    str(exe): consumer.archived.EXECUTABLE_SHA,
                    str(profile): consumer.archived.PROFILE_SHA,
                    str(driver): consumer.archived.DRIVER_SHA}
        launch = candidate_dir / "launch.json"
        launch.write_text(json.dumps({"schema": "pr102_archived_consumer_launch_v1",
                                      "cwd": str(candidate_dir),
                                      "argv": ["bash", "-c", "exec", "pr103",
                                               str(profile), "mpi-env", "libs",
                                               str(staged_executable)],
                                      "bindings": bindings,
                                      "input_binary": {"path": str(input_binary),
                                                       "sha256": runner.sha256(input_binary)}}))
        run_receipt = candidate_dir / "receipt.json"
        run_receipt.write_text(json.dumps({
            "schema": "pr102_archived_consumer_run_v1", "status": "COMPLETE",
            "returncode": 0, "issues": [],
            "launch": {"path": str(launch), "sha256": runner.sha256(launch)},
            "log": {"path": str(log), "sha256": runner.sha256(log)},
            "input": {"path": str(candidate), "sha256": candidate_sha},
            "output": {"path": str(ww), "sha256": runner.sha256(ww)}}))
        output_dir = candidate_dir.parent
        go_path = root / "go.json"
        go_path.write_text(json.dumps({"schema": "pr103_archived_consumer_go_v1",
                                       "status": "GO", "launch_authorized": True,
                                       "proposal_sha256": proposal_sha,
                                       "candidate_wrfinput_sha256": candidate_sha,
                                       "archived_consumer_executable_sha256":
                                           consumer.archived.EXECUTABLE_SHA,
                                       "compiler_profile_sha256": consumer.archived.PROFILE_SHA,
                                       "output_directory": str(output_dir)}))
        pin = lambda path: {"path": str(path), "sha256": runner.sha256(path)}
        before = [pin(path) for path in (candidate, staged_executable, profile, exe, driver)]
        assessment = {
            "schema": "pr103_archived_consumer_assessment_v1", "status": "PASS",
            "execution_status": "COMPLETE", "candidate_wrfinput_sha256": candidate_sha,
            "candidate_parent_sha256": parent_sha, "proposal": {"sha256": proposal_sha},
            "base_c2_executable_sha256": runner.PR102_BASE_C2_EXECUTABLE_SHA256,
            "archived_consumer_executable": {"path": str(exe),
                                             "sha256": consumer.archived.EXECUTABLE_SHA},
            "compiler_profile": {"path": str(profile), "sha256": consumer.archived.PROFILE_SHA},
            "actual_call": {"arm": "AMPLITUDE", "receipt": pin(run_receipt),
                            "output": pin(ww)},
            "root_go": {**pin(go_path), "output_directory": str(output_dir)},
            "source_bindings_before": before, "source_bindings_after": before,
            "gates": {name: {"status": "PASS", "observed_l2_pa_s": 0.0,
                             "allowed_l2_pa_s": 1.0, "observed_max_abs_pa_s": 0.0,
                             "allowed_max_abs_pa_s": 1.0, "pointwise_exceedances": 0}
                      for name in ("reference_constraint", "source_arithmetic")},
            "artifacts": [pin(path) for path in (candidate, staged_executable, ww, log,
                                                  input_binary, launch, run_receipt, go_path,
                                                  exe, profile, driver)]}
        assessment_path = root / "assessment.json"
        assessment_path.write_text(json.dumps(assessment))
        binding = {"receipt_sha256": proposal_sha,
                   "artifacts": {"candidate": {"path": str(candidate), "sha256": candidate_sha},
                                 "original_p": {"sha256": parent_sha}}}
        return assessment_path, binding

    def test_changed_profile_blocks_before_output_setup_or_consumer_call(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            changed_profile = root / "intel-profile.sh"
            changed_profile.write_text("# changed profile\n")
            output = root / "consumer-output"
            binding = {"artifacts": {}}
            with (mock.patch.object(consumer, "_proposal_receipt", return_value=({}, binding)),
                  mock.patch.object(consumer, "_root_go", return_value={}),
                  mock.patch.object(consumer.archived, "PROFILE", changed_profile),
                  mock.patch.object(consumer.archived, "run_case") as run_case):
                with self.assertRaisesRegex(ValueError, "pinned archived-consumer artifact changed"):
                    consumer.assess(root / "proposal.json", output, root / "go.json", execute=True)
            self.assertFalse(output.exists())
            run_case.assert_not_called()

    def test_assessment_requires_receipt_bound_closed_archived_call(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assessment_path, binding = self._closed_assessment(root)
            self.assertEqual(consumer.runner._validate_pr103_consumer_assessment(
                assessment_path, binding)["status"], "PASS")
            assessment = json.loads(assessment_path.read_text())
            receipt_path = Path(assessment["actual_call"]["receipt"]["path"])
            receipt = json.loads(receipt_path.read_text())
            receipt["status"] = "INCOMPLETE"
            receipt_path.write_text(json.dumps(receipt))
            assessment["actual_call"]["receipt"]["sha256"] = runner.sha256(receipt_path)
            assessment_path.write_text(json.dumps(assessment))
            with self.assertRaisesRegex(ValueError, "not a closed call"):
                consumer.runner._validate_pr103_consumer_assessment(assessment_path, binding)


if __name__ == "__main__":
    unittest.main()
