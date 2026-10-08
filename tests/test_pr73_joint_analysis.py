import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pr73_joint_analysis as joint


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "docs/evidence/pr73_joint_fixture_20261008.json"


class JointAnalysisTest(unittest.TestCase):
    def setUp(self):
        self.declaration = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_objective_derives_increment_under_independent_constraints(self):
        result = joint.evaluate(self.declaration)
        self.assertEqual(result["status"], "MANUFACTURED_ALGORITHM_TRIAL")
        self.assertTrue(any(abs(value) > 1e-8 for value in result["analysis_increment"]))
        self.assertAlmostEqual(result["analysis_increment"][1] + result["analysis_increment"][2], 0.0, places=10)
        self.assertAlmostEqual(result["analysis_increment"][5], 0.0, places=10)
        self.assertNotEqual(result["analysis_increment"], result["phase_increment"])
        self.assertTrue(result["cloud_bal_component_contract"]["analysis_increment_retained_separately"])
        self.assertEqual(result["cloud_bal_component_contract"]["status"], "READY_FOR_ENDPOINT_EVALUATION")
        self.assertEqual(len(result["physical_analysis_increment"]), 8)
        self.assertEqual(result["physical_components"]["vapor"]["component_index"], 2)
        self.assertEqual(result["physical_components"]["cloud_water"]["component_index"], 3)

    def test_h_b_r_and_change_authority_are_required(self):
        for authority in ("H", "B", "R", "background_prior", "analysis_change"):
            broken = copy.deepcopy(self.declaration)
            del broken["authorities"][authority]
            with self.subTest(authority=authority), self.assertRaisesRegex(ValueError, "evidence_id"):
                joint.evaluate(broken)

    def test_non_spd_covariance_is_rejected(self):
        broken = copy.deepcopy(self.declaration)
        broken["observation"]["R"][0][0] = -1
        with self.assertRaisesRegex(ValueError, "positive definite"):
            joint.evaluate(broken)

    def test_infeasible_constraints_fail_closed(self):
        broken = copy.deepcopy(self.declaration)
        broken["constraints"][0]["rhs"] = 0.1
        with self.assertRaisesRegex(ValueError, "infeasible"):
            joint.evaluate(broken)

    def test_redundant_scaled_equalities_are_reduced(self):
        duplicated = copy.deepcopy(self.declaration)
        original = duplicated["constraints"][0]
        duplicated["constraints"].append({
            "evidence_id": "manufactured:duplicate-water-equality",
            "coefficients": [7.0 * value for value in original["coefficients"]],
            "rhs": 7.0 * original["rhs"],
        })
        result = joint.evaluate(duplicated)
        expected = joint.evaluate(self.declaration)
        for left, right in zip(result["analysis_increment"], expected["analysis_increment"]):
            self.assertAlmostEqual(left, right, places=12)

    def test_inconsistent_dependent_equalities_are_rejected(self):
        inconsistent = copy.deepcopy(self.declaration)
        original = inconsistent["constraints"][0]
        inconsistent["constraints"].append({
            "evidence_id": "manufactured:conflicting-water-equality",
            "coefficients": [3.0 * value for value in original["coefficients"]],
            "rhs": 3.0 * original["rhs"] + 0.1,
        })
        with self.assertRaisesRegex(ValueError, "constraints are inconsistent"):
            joint.evaluate(inconsistent)

    def test_active_upper_bound_is_enforced(self):
        bounded = copy.deepcopy(self.declaration)
        bounded["state_bounds"][1]["upper"] = 0.0041
        result = joint.evaluate(bounded)
        self.assertEqual(result["candidate_state"][1], 0.0041)
        self.assertLessEqual(result["candidate_state"][1], 0.0041)

    def test_active_lower_bound_is_enforced(self):
        bounded = copy.deepcopy(self.declaration)
        bounded["state_bounds"][1]["lower"] = 0.0046
        result = joint.evaluate(bounded)
        self.assertEqual(result["candidate_state"][1], 0.0046)
        self.assertGreaterEqual(result["candidate_state"][1], 0.0046)

    def test_scalar_lower_bound_roundoff_keeps_exact_active_state_and_kkt_certificate(self):
        scalar = copy.deepcopy(self.declaration)
        scalar.pop("physical_reference", None)
        scalar["state_fields"] = ["x"]
        scalar["background_state"] = [0.0]
        scalar["B"] = [[1.0]]
        scalar["observation"] = {"H": [[1.0]], "value": [-0.7], "R": [[1.0]]}
        scalar["process_increments"] = {
            "phase": [0.0], "external_source": [0.0], "physical_boundary": [0.0],
        }
        scalar["constraints"] = []
        scalar["state_bounds"] = [{"field": "x", "lower": 0.3, "upper": 1.3}]

        result = joint.evaluate(scalar)

        self.assertEqual(result["candidate_state"], [0.3])
        self.assertEqual(result["kkt_diagnostics"]["status"], "PASS")
        self.assertEqual(result["kkt_diagnostics"]["active_bounds"][0]["side"], "lower")
        for key in ("primal_equality_residual", "primal_bound_violation", "stationarity_residual",
                    "dual_sign_violation", "complementarity_residual"):
            self.assertLessEqual(result["kkt_diagnostics"][key], 1e-12)

    def test_unconstrained_scalar_cancellation_uses_uncancelled_stationarity_scale(self):
        scalar = copy.deepcopy(self.declaration)
        scalar.pop("physical_reference", None)
        scalar["state_fields"] = ["x"]
        scalar["background_state"] = [0.0]
        scalar["B"] = [[1.0]]
        scalar["observation"] = {"H": [[2.0]], "value": [1.0], "R": [[1.0]]}
        scalar["process_increments"] = {
            "phase": [0.0], "external_source": [0.0], "physical_boundary": [0.0],
        }
        scalar["constraints"] = []
        scalar["state_bounds"] = []

        result = joint.evaluate(scalar)

        self.assertAlmostEqual(result["candidate_state"][0], 0.4, places=14)
        self.assertEqual(result["kkt_diagnostics"]["status"], "PASS")
        self.assertLess(result["kkt_diagnostics"]["stationarity_residual"], 1e-15)

    def test_stationarity_certificate_rejects_perturbed_unconstrained_solution(self):
        scalar = copy.deepcopy(self.declaration)
        scalar.pop("physical_reference", None)
        scalar["state_fields"] = ["x"]
        scalar["background_state"] = [0.0]
        scalar["B"] = [[1.0]]
        scalar["observation"] = {"H": [[2.0]], "value": [1.0], "R": [[1.0]]}
        scalar["process_increments"] = {
            "phase": [0.0], "external_source": [0.0], "physical_boundary": [0.0],
        }
        scalar["constraints"] = []
        scalar["state_bounds"] = []
        solve = joint._solve

        def perturbed_solve(matrix, rhs):
            solution = solve(matrix, rhs)
            solution[0] += 1e-5
            return solution

        with patch.object(joint, "_solve", side_effect=perturbed_solve):
            with self.assertRaisesRegex(ValueError, "KKT certificate did not pass"):
                joint.evaluate(scalar)

    def test_feasible_fixed_bound_redundant_with_equality(self):
        fixed = copy.deepcopy(self.declaration)
        fixed["constraints"].append({
            "evidence_id": "manufactured:fixed-u-equality",
            "coefficients": [0.0, 0.0, 0.0, 1.0, 0.0, 0.0],
            "rhs": 0.0,
        })
        fixed["state_bounds"][3] = {"field": "u", "lower": 2.0, "upper": 2.0}
        result = joint.evaluate(fixed)
        self.assertEqual(result["candidate_state"][3], 2.0)
        scalar = copy.deepcopy(self.declaration)
        scalar.pop("physical_reference", None)
        scalar["state_fields"] = ["x"]
        scalar["background_state"] = [0.0]
        scalar["B"] = [[1.0]]
        scalar["observation"] = {"H": [[1.0]], "value": [0.0], "R": [[1.0]]}
        scalar["process_increments"] = {
            "phase": [0.0], "external_source": [0.0], "physical_boundary": [0.0],
        }
        scalar["constraints"] = []
        scalar["state_bounds"] = [{"field": "x", "lower": 0.3, "upper": 0.3}]
        fixed_result = joint.evaluate(scalar)
        self.assertEqual(fixed_result["candidate_state"], [0.3])
        self.assertEqual(fixed_result["kkt_diagnostics"]["active_bounds"][0]["side"], "fixed")

    def test_equality_at_active_lower_bound_is_not_treated_as_infeasible(self):
        scalar = copy.deepcopy(self.declaration)
        scalar.pop("physical_reference", None)
        scalar["state_fields"] = ["x"]
        scalar["background_state"] = [0.0]
        scalar["B"] = [[1.0]]
        scalar["observation"] = {"H": [[1.0]], "value": [-0.7], "R": [[1.0]]}
        scalar["process_increments"] = {
            "phase": [0.0], "external_source": [0.0], "physical_boundary": [0.0],
        }
        scalar["constraints"] = [{
            "evidence_id": "manufactured:bound-equality",
            "coefficients": [1.0], "rhs": 0.3,
        }]
        scalar["state_bounds"] = [{"field": "x", "lower": 0.3, "upper": 1.3}]

        result = joint.evaluate(scalar)

        self.assertEqual(result["candidate_state"], [0.3])
        self.assertEqual(result["kkt_diagnostics"]["status"], "PASS")
        self.assertEqual(result["kkt_diagnostics"]["active_bounds"][0]["side"], "lower")

    def test_box_feasibility_rounding_does_not_claim_infeasibility(self):
        declaration = copy.deepcopy(self.declaration)
        declaration.pop("physical_reference", None)
        declaration["state_fields"] = ["x", "z"]
        declaration["background_state"] = [0.0, 0.0]
        declaration["B"] = [[1.0, 0.0], [0.0, 1.0]]
        declaration["observation"] = {
            "H": [[1.0, 0.0], [0.0, 1.0]], "value": [0.0, 0.0],
            "R": [[1.0, 0.0], [0.0, 1.0]],
        }
        declaration["process_increments"] = {
            "phase": [0.0, 0.0], "external_source": [0.0, 0.0],
            "physical_boundary": [0.0, 0.0],
        }
        declaration["constraints"] = [{
            "evidence_id": "manufactured:decimal-box-edge",
            "coefficients": [1.0, 1.0], "rhs": 0.3,
        }]
        declaration["state_bounds"] = [
            {"field": "x", "lower": 0.1, "upper": 1.0},
            {"field": "z", "lower": 0.2, "upper": 1.0},
        ]

        with self.assertRaisesRegex(ValueError, "NUMERICAL_FAILURE"):
            joint.evaluate(declaration)

    def test_finite_inputs_that_overflow_process_or_equality_arithmetic_are_numerical_failures(self):
        process_overflow = copy.deepcopy(self.declaration)
        process_overflow["process_increments"]["phase"][1] = 1e308
        process_overflow["process_increments"]["external_source"][1] = 1e308
        with self.assertRaisesRegex(ValueError, "NUMERICAL_FAILURE"):
            joint.evaluate(process_overflow)

        equality_overflow = copy.deepcopy(self.declaration)
        equality_overflow["process_increments"]["phase"][1] = 1e200
        equality_overflow["process_increments"]["external_source"][1] = 1e200
        equality_overflow["constraints"][0]["coefficients"][1] = 1e200
        with self.assertRaisesRegex(ValueError, "NUMERICAL_FAILURE"):
            joint.evaluate(equality_overflow)

    def test_near_dependent_feasible_equalities_are_not_declared_infeasible(self):
        near_dependent = copy.deepcopy(self.declaration)
        near_dependent.pop("physical_reference", None)
        near_dependent["state_fields"] = ["x", "z"]
        near_dependent["background_state"] = [0.0, 0.0]
        near_dependent["B"] = [[1.0, 0.0], [0.0, 1.0]]
        near_dependent["observation"] = {
            "H": [[1.0, 0.0], [0.0, 1.0]], "value": [0.0, 0.0],
            "R": [[1.0, 0.0], [0.0, 1.0]],
        }
        near_dependent["process_increments"] = {
            "phase": [0.0, 0.0], "external_source": [0.0, 0.0],
            "physical_boundary": [0.0, 0.0],
        }
        near_dependent["state_bounds"] = []
        near_dependent["constraints"] = [
            {"evidence_id": "manufactured:rank-row-1", "coefficients": [1.0, 0.0], "rhs": 1.0},
            {"evidence_id": "manufactured:rank-row-2", "coefficients": [1.0, 1e-15], "rhs": 2.0},
        ]

        with self.assertRaisesRegex(ValueError, "NUMERICAL_FAILURE: equality rank is numerically ambiguous"):
            joint.evaluate(near_dependent)

    def test_scaled_equality_is_rank_checked_after_state_unit_normalization(self):
        scalar = copy.deepcopy(self.declaration)
        scalar.pop("physical_reference", None)
        scalar["state_fields"] = ["x"]
        scalar["background_state"] = [0.0]
        scalar["B"] = [[1e30]]
        scalar["observation"] = {"H": [[1e-15]], "value": [0.0], "R": [[1.0]]}
        scalar["process_increments"] = {
            "phase": [0.0], "external_source": [0.0], "physical_boundary": [0.0],
        }
        scalar["constraints"] = [{
            "evidence_id": "manufactured:rescaled-scalar-equality",
            "coefficients": [1e-15], "rhs": 0.3,
        }]
        scalar["state_bounds"] = [{"field": "x", "lower": 0.0, "upper": 1e15}]

        result = joint.evaluate(scalar)

        self.assertAlmostEqual(result["candidate_state"][0], 3e14, places=-1)
        self.assertEqual(result["kkt_diagnostics"]["status"], "PASS")

    def test_common_unit_rescaling_preserves_solution(self):
        scaled = copy.deepcopy(self.declaration)
        scaled["background_state"] = [value * 1000 for value in scaled["background_state"]]
        scaled["B"] = [[value * 1_000_000 for value in row] for row in scaled["B"]]
        scaled["observation"]["value"] = [value * 1000 for value in scaled["observation"]["value"]]
        scaled["observation"]["R"] = [[value * 1_000_000 for value in row]
                                         for row in scaled["observation"]["R"]]
        for component in ("phase", "external_source", "physical_boundary"):
            scaled["process_increments"][component] = [
                value * 1000 for value in scaled["process_increments"][component]
            ]
        for constraint in scaled["constraints"]:
            constraint["rhs"] *= 1000
        for bound in scaled["state_bounds"]:
            if bound["lower"] is not None:
                bound["lower"] *= 1000
            if bound["upper"] is not None:
                bound["upper"] *= 1000
        original = joint.evaluate(self.declaration)["analysis_increment"]
        changed_units = joint.evaluate(scaled)["analysis_increment"]
        for left, right in zip(original, changed_units):
            self.assertAlmostEqual(left, right / 1000, places=12)

    def test_cli_failure_preserves_existing_output_file(self):
        broken = copy.deepcopy(self.declaration)
        broken["state_fields"] = ["vapor", "vapor"]
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "bad.json"
            output = Path(tmp) / "result.json"
            source.write_text(json.dumps(broken), encoding="utf-8")
            output.write_text("sentinel\n", encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(joint.__file__), str(source), "--output", str(output)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertEqual(output.read_text(encoding="utf-8"), "sentinel\n")
            self.assertEqual(json.loads(completed.stdout)["status"], "INVALID_TRIAL")

    def test_success_cli_writes_result_atomically(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "result.json"
            physical_control = Path(tmp) / "trial.control"
            completed = subprocess.run(
                [sys.executable, str(joint.__file__), str(FIXTURE), "--output", str(output),
                 "--physical-control", str(physical_control)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(json.loads(output.read_text())["status"], "MANUFACTURED_ALGORITHM_TRIAL")
            contract = json.loads(output.read_text())["cloud_bal_component_contract"]
            self.assertEqual(contract["status"], "READY_FOR_ENDPOINT_EVALUATION")
            self.assertEqual(len(physical_control.read_text().splitlines()), 4)
            self.assertFalse(output.with_name("result.json.tmp").exists())


if __name__ == "__main__":
    unittest.main()
