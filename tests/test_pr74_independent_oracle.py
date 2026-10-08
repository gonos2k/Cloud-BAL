"""Independent scalar and covariance-form oracles for PR74 solver cases."""

import copy
import json
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pr73_joint_analysis as joint


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "docs/evidence/pr73_joint_fixture_20261008.json"


def scalar_declaration(target: float, lower: float, upper: float) -> dict:
    return {
        "schema_version": 1,
        "evidence_class": "MANUFACTURED_ALGORITHM_FIXTURE",
        "state_fields": ["x"],
        "background_state": [0.0],
        "B": [[1.0]],
        "observation": {"H": [[1.0]], "value": [target], "R": [[1.0]]},
        "authorities": {
            name: {"evidence_id": f"manufactured:{name}"}
            for name in ("H", "B", "R", "background_prior", "analysis_change")
        },
        "process_increments": {
            "phase": [0.0], "external_source": [0.0], "physical_boundary": [0.0]
        },
        "constraints": [],
        "state_bounds": [{"field": "x", "lower": lower, "upper": upper}],
    }


def matmul(left: list[list[float]], right: list[list[float]]) -> list[list[float]]:
    return [[sum(a * b for a, b in zip(row, column))
             for column in zip(*right)] for row in left]


def transpose(matrix: list[list[float]]) -> list[list[float]]:
    return [list(column) for column in zip(*matrix)]


def solve(matrix: list[list[float]], rhs: list[float]) -> list[float]:
    """Solve a small positive-definite covariance system by elimination."""
    rows = [row[:] + [value] for row, value in zip(matrix, rhs)]
    size = len(rhs)
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(rows[row][column]))
        rows[column], rows[pivot] = rows[pivot], rows[column]
        divisor = rows[column][column]
        if divisor == 0.0:
            raise AssertionError("oracle covariance matrix is singular")
        rows[column] = [value / divisor for value in rows[column]]
        for row in range(size):
            if row != column:
                factor = rows[row][column]
                rows[row] = [a - factor * b for a, b in zip(rows[row], rows[column])]
    return [rows[index][-1] for index in range(size)]


def covariance_oracle(declaration: dict) -> list[float]:
    """Posterior mean followed by covariance conditioning on C delta = d.

    This is a Gaussian covariance update, independent of the production
    precision-form KKT face enumeration.
    """
    B = declaration["B"]
    H = declaration["observation"]["H"]
    R = declaration["observation"]["R"]
    fields = declaration["state_fields"]
    n = len(fields)
    background = declaration["background_state"]
    known = [sum(declaration["process_increments"][name][i]
                 for name in ("phase", "external_source", "physical_boundary"))
             for i in range(n)]
    state_with_process = [background[i] + known[i] for i in range(n)]
    innovation = [y - sum(a * b for a, b in zip(hrow, state_with_process))
                  for hrow, y in zip(H, declaration["observation"]["value"])]

    # M = H B H^T + R; solve M against each needed right-hand side.
    M = matmul(matmul(H, B), transpose(H))
    M = [[M[i][j] + R[i][j] for j in range(len(R))] for i in range(len(R))]
    solved_innovation = solve(M, innovation)
    B_Ht = matmul(B, transpose(H))
    posterior_increment = [sum(B_Ht[i][j] * solved_innovation[j]
                               for j in range(len(R))) for i in range(n)]
    solved_HB_columns = [solve(M, column) for column in transpose(matmul(H, B))]
    M_inv_HB = transpose(solved_HB_columns)
    covariance = [[B[i][j] - sum(B_Ht[i][k] * M_inv_HB[k][j]
                                 for k in range(len(R)))
                   for j in range(n)] for i in range(n)]

    constraints = declaration["constraints"]
    C = [row["coefficients"] for row in constraints]
    if not C:
        return posterior_increment
    d = [row["rhs"] - sum(a * b for a, b in zip(row["coefficients"], known))
         for row in constraints]
    residual = [d[i] - sum(a * b for a, b in zip(C[i], posterior_increment))
                for i in range(len(C))]
    C_cov = matmul(C, covariance)
    conditional_cov = matmul(C_cov, transpose(C))
    correction_weights = solve(conditional_cov, residual)
    covariance_Ct = matmul(covariance, transpose(C))
    correction = [sum(covariance_Ct[i][j] * correction_weights[j]
                      for j in range(len(C))) for i in range(n)]
    return [posterior_increment[i] + correction[i] for i in range(n)]

class IndependentOracleTest(unittest.TestCase):
    def test_396_signed_scalar_boxes_match_closed_form_minimum(self):
        endpoints = (-3.0, -1.0, -0.5, -0.2, 0.0, 0.2, 0.5, 1.0, 3.0)
        optima = (-4.0, -3.0, -1.0, -0.5, -0.2, 0.0, 0.2, 0.5, 1.0, 3.0, 4.0)
        case_count = 0
        for optimum in optima:
            for lower_index, lower in enumerate(endpoints):
                for upper in endpoints[lower_index + 1:]:
                    result = joint.evaluate(scalar_declaration(2.0 * optimum, lower, upper))
                    expected = min(upper, max(lower, optimum))
                    self.assertTrue(math.isclose(result["candidate_state"][0], expected,
                                                 rel_tol=2e-12, abs_tol=2e-12),
                                    (optimum, lower, upper, result["candidate_state"][0], expected))
                    case_count += 1
        self.assertEqual(case_count, 396)

    def test_one_sided_baseline_chooses_lower_optimum(self):
        result = joint.evaluate(scalar_declaration(-0.7, 0.3, 1.3))
        self.assertAlmostEqual(result["candidate_state"][0], 0.3, places=12)

    def test_six_variable_solution_matches_covariance_form_oracle(self):
        declaration = json.loads(FIXTURE.read_text(encoding="utf-8"))
        expected = covariance_oracle(declaration)
        result = joint.evaluate(declaration)
        for actual, reference in zip(result["analysis_increment"], expected):
            self.assertTrue(math.isclose(actual, reference, rel_tol=2e-9, abs_tol=2e-11),
                            (actual, reference))

    def test_partial_u_v_unit_transform_preserves_covariant_solution(self):
        declaration = json.loads(FIXTURE.read_text(encoding="utf-8"))
        scaled = copy.deepcopy(declaration)
        factors = [1000.0 if field in ("u", "v") else 1.0
                   for field in declaration["state_fields"]]
        for i, factor in enumerate(factors):
            scaled["background_state"][i] *= factor
            for row in scaled["observation"]["H"]:
                row[i] /= factor
            for name in ("phase", "external_source", "physical_boundary"):
                scaled["process_increments"][name][i] *= factor
            for bound in scaled["state_bounds"]:
                if bound["field"] == declaration["state_fields"][i]:
                    if bound["lower"] is not None:
                        bound["lower"] *= factor
                    if bound["upper"] is not None:
                        bound["upper"] *= factor
        scaled["B"] = [[declaration["B"][i][j] * factors[i] * factors[j]
                        for j in range(len(factors))] for i in range(len(factors))]
        for constraint in scaled["constraints"]:
            constraint["coefficients"] = [value / factor
                                           for value, factor in zip(constraint["coefficients"], factors)]

        reference = covariance_oracle(declaration)
        original = joint.evaluate(declaration)["analysis_increment"]
        transformed_result = joint.evaluate(scaled)
        transformed = transformed_result["analysis_increment"]
        for i, factor in enumerate(factors):
            self.assertTrue(math.isclose(transformed[i], factor * original[i],
                                         rel_tol=2e-9, abs_tol=2e-10),
                            (i, transformed[i], factor * original[i]))
            self.assertTrue(math.isclose(transformed[i] / factor, reference[i],
                                         rel_tol=2e-9, abs_tol=2e-11),
                            (i, transformed[i] / factor, reference[i]))


if __name__ == "__main__":
    unittest.main()
