import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pr72_joint_candidate_preflight as preflight


CASE_TIME = "2026-08-16T12:00:00Z"


def complete_declaration():
    authorities = {}
    for name in (
        "radar_analysis", "external_source", "physical_boundary",
        "phase_exchange", "common_air_moments",
    ):
        authorities[name] = {
            "status": "AUTHORIZED",
            "valid_time": CASE_TIME,
            "evidence_id": f"independent:{name}",
        }
    authorities["radar_analysis"].update(per_cell=True, error_bound=True)
    authorities["external_source"]["per_cell"] = True
    authorities["physical_boundary"]["per_cell"] = True
    return {
        "schema_version": 1,
        "valid_time": CASE_TIME,
        "scope": "ALL_OBSERVATIONS",
        "authorities": authorities,
        "wind": {"mode": "FIXED_BACKGROUND"},
    }


class JointCandidatePreflightTest(unittest.TestCase):
    def test_current_case_fails_closed_and_fixed_wind_is_not_completion(self):
        declaration = json.loads(
            (Path(__file__).resolve().parents[1] / "docs/evidence/"
             "pr72_joint_candidate_declaration_20261008.json").read_text()
        )
        result = preflight.evaluate(declaration)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertFalse(result["wind_component_complete"])
        self.assertIn("radar_analysis: status is MISSING", result["failed_gates"])
        self.assertIn("phase_exchange: status is CONDITIONAL", result["failed_gates"])

    def test_exact_time_mismatch_is_rejected_before_evaluation(self):
        declaration = complete_declaration()
        declaration["valid_time"] = "2026-08-16T13:00:00Z"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "declaration.json"
            path.write_text(json.dumps(declaration))
            with self.assertRaisesRegex(ValueError, "exact case time"):
                preflight._read_declaration(path)

    def test_fixed_wind_allows_readiness_but_never_claims_wind_completion(self):
        result = preflight.evaluate(complete_declaration())
        self.assertEqual(result["status"], "READY_FOR_CANDIDATE_EVALUATION")
        self.assertFalse(result["wind_component_complete"])

    def test_observed_wind_requires_a_matched_uncertainty_declaration(self):
        declaration = complete_declaration()
        declaration["wind"] = {"mode": "OBSERVATION"}
        declaration["authorities"]["wind"] = {
            "status": "AUTHORIZED", "valid_time": CASE_TIME,
            "evidence_id": "independent:omega-target",
        }
        result = preflight.evaluate(declaration)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("wind: independent target/prior uncertainty missing",
                      result["failed_gates"])

    def test_malformed_nested_shapes_and_evidence_ids_are_rejected(self):
        variants = (
            ({"authorities": None}, "authorities must be a JSON object"),
            ({"authorities": []}, "authorities must be a JSON object"),
            ({"wind": {"mode": []}}, "wind.mode must be a nonempty string"),
            ({"authorities": {"radar_analysis": {
                "status": "MISSING", "valid_time": CASE_TIME,
                "per_cell": False, "error_bound": False, "evidence_id": ["bad"],
            }}}, "authorities.radar_analysis.evidence_id must be a nonempty string"),
        )
        for replacement, message in variants:
            with self.subTest(replacement=replacement):
                declaration = complete_declaration()
                declaration.update(replacement)
                with self.assertRaisesRegex(ValueError, message):
                    preflight.evaluate(declaration)

    def test_cli_reports_malformed_declaration_without_traceback(self):
        declaration = complete_declaration()
        declaration["wind"]["mode"] = []
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "malformed.json"
            path.write_text(json.dumps(declaration))
            completed = subprocess.run(
                [sys.executable, str(Path(preflight.__file__)), str(path)],
                capture_output=True, text=True, check=False,
            )
        self.assertEqual(completed.returncode, 2)
        self.assertNotIn("Traceback", completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["status"], "INVALID_DECLARATION")


if __name__ == "__main__":
    unittest.main()
