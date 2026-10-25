from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pr86_time_response as runner
import pr102_execution_preflight as preflight


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PR102PreflightTests(unittest.TestCase):
    def test_binding_requires_every_artifact_and_u_v_noninterference_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifacts = {}
            for name in ("candidate", "original_p", "reference_hydro", "reference_coupled",
                         "boundary", "generator", "policy", "composition"):
                path = root / name
                path.write_bytes(name.encode())
                artifacts[name] = {"path": str(path), "sha256": digest(path)}
            receipt = {"schema": "pr102_wind_structure_proposal_v1",
                       "status": "PROPOSAL_REQUIRES_NATIVE_CONSUMER_AND_SOURCE_CAPTURE",
                       "role": "COUPLED", **artifacts,
                       "composition_sha256": artifacts["composition"]["sha256"],
                       "parent_sha256": artifacts["original_p"]["sha256"],
                       "change_contract": {"changed_variables": ["U", "V"],
                                            "non_target_variables_identical": True}}
            path = root / "proposal.json"
            path.write_text(json.dumps(receipt))
            binding = runner._wind_structure_input_binding(path)
            self.assertEqual(binding["binding_kind"], "wind_structure")
            self.assertTrue(runner._input_binding_unchanged(binding))
            Path(artifacts["policy"]["path"]).write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "policy artifact changed"):
                runner._wind_structure_input_binding(path)

    def test_template_requires_original_p_and_boundary_match(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = {}
            for name in ("candidate", "original_p", "reference_hydro", "reference_coupled",
                         "boundary", "generator", "policy", "composition"):
                path = root / name
                path.write_bytes(name.encode())
                rows[name] = {"path": str(path), "sha256": digest(path)}
            proposal = {"schema": "pr102_wind_structure_proposal_v1",
                        "status": "PROPOSAL_REQUIRES_NATIVE_CONSUMER_AND_SOURCE_CAPTURE",
                        "role": "COUPLED", **rows,
                        "composition_sha256": rows["composition"]["sha256"],
                        "change_contract": {"changed_variables": ["U", "V"],
                                             "non_target_variables_identical": True}}
            receipt_path = root / "proposal.json"
            receipt_path.write_text(json.dumps(proposal))
            binding = runner._wind_structure_input_binding(receipt_path)
            template = {"candidate_wrfinput_sha256": rows["reference_coupled"]["sha256"],
                        "candidate_wrfbdy_sha256": rows["boundary"]["sha256"]}
            with patch.object(runner, "PR102_ORIGINAL_P_C2_SHA256", rows["original_p"]["sha256"]), \
                 patch.object(runner, "PR102_REFERENCE_HYDRO_SHA256", rows["reference_hydro"]["sha256"]), \
                 patch.object(runner, "PR102_REFERENCE_COUPLED_SHA256", rows["reference_coupled"]["sha256"]), \
                 patch.object(runner, "PR102_BOUNDARY_C2_SHA256", rows["boundary"]["sha256"]):
                runner._validate_wind_structure_template(binding, template)
                binding["artifacts"]["original_p"]["sha256"] = "wrong"
                with self.assertRaisesRegex(ValueError, "original_p differs from the closed C2 PROJECTED input"):
                    runner._validate_wind_structure_template(binding, template)
                binding["artifacts"]["original_p"]["sha256"] = rows["original_p"]["sha256"]
                binding["artifacts"]["reference_coupled"]["sha256"] = "wrong"
                with self.assertRaisesRegex(ValueError, "reference_coupled differs"):
                    runner._validate_wind_structure_template(binding, template)
                binding["artifacts"]["reference_coupled"]["sha256"] = rows["reference_coupled"]["sha256"]
                template["candidate_wrfbdy_sha256"] = "wrong"
                with self.assertRaisesRegex(ValueError, "boundary differs from the closed C2 matched boundary"):
                    runner._validate_wind_structure_template(binding, template)

    def test_preflight_requires_same_candidate_and_complete_consumer_capture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            proposal_path = root / "proposal.json"
            candidate = root / "candidate"
            original = root / "original_p"
            other = root / "other"
            for path in (candidate, original, other):
                path.write_bytes(path.name.encode())
            rows = {}
            for name, path in (("candidate", candidate), ("original_p", original),
                               ("reference_hydro", other), ("reference_coupled", other),
                               ("boundary", other), ("generator", other), ("policy", other),
                               ("composition", other)):
                rows[name] = {"path": str(path), "sha256": digest(path)}
            proposal_path.write_text(json.dumps({
                "schema": "pr102_wind_structure_proposal_v1",
                "status": "PROPOSAL_REQUIRES_NATIVE_CONSUMER_AND_SOURCE_CAPTURE",
                "role": "COUPLED", **rows,
                "composition_sha256": rows["composition"]["sha256"],
                "change_contract": {"changed_variables": ["U", "V"],
                                     "non_target_variables_identical": True}}))
            build_path = root / "build.json"
            build_path.write_text("synthetic build")
            consumer = root / "consumer.json"
            consumer.write_text(json.dumps({"schema": "pr102_native_consumer_check_v1",
                                            "status": "COMPLETE",
                                            "candidate_wrfinput_sha256": digest(candidate),
                                            "native_consumer": "module_big_step_utilities_em_mp_calc_ww_cp_",
                                            "archive_member_sha256": preflight.EXPECTED_CONSUMER_MEMBER,
                                            "compiler_profile_sha256": preflight.EXPECTED_PROFILE,
                                            "dry_mass_check": {
                                                "schema": "pr102_native_drymass_constraint_v1",
                                                "status": "PASS",
                                                "consumer": "module_big_step_utilities_em_mp_calc_ww_cp_",
                                                "comparison": "candidate_minus_HYDRO", "units": "Pa/s",
                                                "composition_sha256": rows["composition"]["sha256"],
                                                "finite": True, "support_count": 4,
                                                "observed_l2_pa_s": 1e-7, "allowed_l2_pa_s": 1e-6,
                                                "observed_max_abs_pa_s": 1e-8,
                                                "allowed_max_abs_pa_s": 1e-7,
                                                "reference_constraint": {"status": "PASS",
                                                    "observed_l2_pa_s": 1e-7, "allowed_l2_pa_s": 1e-6,
                                                    "observed_max_abs_pa_s": 1e-8,
                                                    "allowed_max_abs_pa_s": 1e-7},
                                                "source_arithmetic": {"status": "PASS",
                                                    "observed_l2_pa_s": 1e-7, "allowed_l2_pa_s": 1e-6,
                                                    "observed_max_abs_pa_s": 1e-8,
                                                    "allowed_max_abs_pa_s": 1e-7}},
                                            "artifacts": [{"path": str(other), "sha256": digest(other)}]}))
            diagnostic_build_path = root / "diagnostic_build.json"
            diagnostic_build_path.write_text(json.dumps({
                "schema": "pr102_c2_native_capture_build_v1", "status": "PASS_C2_CAPTURE_OVERLAY",
                "base_c2_receipt_sha256": preflight.BASE_C2_RECEIPT_SHA256,
                "base_c2_executable_sha256": preflight.EXPECTED_EXECUTABLE,
                "executable_sha256": "diagnostic executable digest"}))
            capture_paths = {}
            controls = {
                "HYDRO": {"candidate_wrfinput_sha256": digest(other)},
                "PROJECTED": {"candidate_wrfinput_sha256": digest(original)},
                "COUPLED": {"candidate_wrfinput_sha256": digest(other)},
                "OFF": {"candidate_wrfinput_sha256": "unused"},
            }
            for label, input_sha in (("HYDRO", digest(other)), ("ORIGINAL_P", digest(original)),
                                     ("CANDIDATE", digest(candidate))):
                raw = root / f"{label.lower()}_raw.bin"
                raw.write_bytes(label.encode())
                receipt = root / f"{label.lower()}_capture.json"
                receipt.write_text(json.dumps({"schema": "pr102_native_source_capture_v1",
                    "status": "COMPLETE", "candidate_wrfinput_sha256": input_sha,
                    "baseline_c2_executable_sha256": preflight.EXPECTED_EXECUTABLE,
                    "diagnostic_executable_sha256": "diagnostic executable digest",
                    "diagnostic_build_receipt_sha256": digest(diagnostic_build_path),
                    "diagnostic_build_receipt": {"path": str(diagnostic_build_path),
                                                  "sha256": digest(diagnostic_build_path)},
                    "captured_sources": ["RU", "RV", "MUDF"], "completed_steps": 1,
                    "noninterference": {"status": "PASS"},
                    "artifacts": [{"path": str(diagnostic_build_path), "sha256": digest(diagnostic_build_path)},
                                  {"path": str(raw), "sha256": digest(raw)}]}))
                capture_paths[label] = receipt
            output = root / "preflight.json"
            mocked_build = {"receipt_path": str(build_path), "receipt_sha256": digest(build_path),
                            "executable_sha256": preflight.EXPECTED_EXECUTABLE}
            controls = {arm: {"receipt": {"path": str(consumer), "sha256": digest(consumer)},
                              "preflight": {"path": str(consumer), "sha256": digest(consumer)},
                              "candidate_wrfinput_sha256": row["candidate_wrfinput_sha256"]}
                        for arm, row in controls.items()}
            with patch.object(runner, "_candidate_build_binding", return_value=mocked_build), \
                 patch.object(preflight, "verify_only_wind_changed"), \
                 patch.object(preflight, "_controls", return_value=controls):
                result = preflight.build_preflight(proposal_path, build_path, consumer, capture_paths, output)
            self.assertEqual(result["status"], "READY_FOR_ROOT_REVIEW_NO_LAUNCH")
            self.assertFalse(result["launch_authorized"])
            with self.assertRaises(FileExistsError):
                with patch.object(runner, "_candidate_build_binding", return_value=mocked_build), \
                     patch.object(preflight, "verify_only_wind_changed"), \
                     patch.object(preflight, "_controls", return_value=controls):
                    preflight.build_preflight(proposal_path, build_path, consumer, capture_paths, output)

    def test_native_consumer_requires_both_finite_nested_gates(self) -> None:
        gate = {"status": "PASS", "observed_l2_pa_s": 1e-8, "allowed_l2_pa_s": 1e-7,
                "observed_max_abs_pa_s": 1e-9, "allowed_max_abs_pa_s": 1e-8}
        check = {"schema": "pr102_native_drymass_constraint_v1", "status": "PASS",
                 "consumer": "module_big_step_utilities_em_mp_calc_ww_cp_",
                 "comparison": "candidate_minus_HYDRO", "units": "Pa/s",
                 "composition_sha256": "composition", "finite": True, "support_count": 10,
                 "observed_l2_pa_s": 1e-8, "allowed_l2_pa_s": 1e-7,
                 "observed_max_abs_pa_s": 1e-9, "allowed_max_abs_pa_s": 1e-8,
                 "reference_constraint": dict(gate), "source_arithmetic": dict(gate)}
        preflight._validate_native_consumer(check, "composition")
        for gate_name in ("reference_constraint", "source_arithmetic"):
            for malformed in ({**gate, "status": "FAIL"},
                              {**gate, "allowed_l2_pa_s": float("nan")},
                              {**gate, "observed_max_abs_pa_s": 2e-8}):
                with self.subTest(gate=gate_name, malformed=malformed):
                    bad = dict(check)
                    bad[gate_name] = malformed
                    with self.assertRaisesRegex(ValueError, f"{gate_name} gate"):
                        preflight._validate_native_consumer(bad, "composition")

    def test_structured_runner_arm_fails_closed_without_all_three_prerequisites(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "source-bound wind proposal"):
                runner.prepare("STRUCTURED", 640, root / "out")
            with self.assertRaisesRegex(ValueError, "matched 640-second run"):
                runner.prepare("STRUCTURED", 20, root / "out",
                               wind_structure_input_receipt_path=root / "proposal.json")


if __name__ == "__main__":
    unittest.main()
