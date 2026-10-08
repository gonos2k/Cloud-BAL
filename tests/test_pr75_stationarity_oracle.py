"""Independent high-precision stationarity oracles for PR75."""

import copy
import math
import sys
import unittest
from decimal import Decimal, localcontext
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pr73_joint_analysis as joint


ROOT = Path(__file__).resolve().parents[1]


def declaration(fields, background, B, H, observation, R, *, equality=None, bounds=None):
    n = len(fields)
    constraints = [] if equality is None else [{
        "evidence_id": "manufactured:pr75-equality",
        "coefficients": equality[0], "rhs": equality[1],
    }]
    return {
        "schema_version": 1,
        "evidence_class": "MANUFACTURED_ALGORITHM_FIXTURE",
        "state_fields": fields,
        "background_state": background,
        "B": B,
        "observation": {"H": H, "value": observation, "R": R},
        "authorities": {name: {"evidence_id": f"manufactured:{name}"}
                        for name in ("H", "B", "R", "background_prior", "analysis_change")},
        "process_increments": {name: [0.0] * n
                               for name in ("phase", "external_source", "physical_boundary")},
        "constraints": constraints,
        "state_bounds": [] if bounds is None else bounds,
    }


def D(value):
    return Decimal(str(value))


def transpose(a):
    return [list(row) for row in zip(*a)]


def mm(a, b):
    return [[sum((x * y for x, y in zip(row, col)), Decimal(0))
             for col in zip(*b)] for row in a]


def add(a, b):
    return [[x + y for x, y in zip(ar, br)] for ar, br in zip(a, b)]


def solve(a, b):
    """Decimal Gauss-Jordan solve, separate from production precision KKT."""
    rows = [row[:] + [value] for row, value in zip(a, b)]
    for col in range(len(b)):
        pivot = max(range(col, len(b)), key=lambda i: abs(rows[i][col]))
        if rows[pivot][col] == 0:
            raise AssertionError("oracle matrix is singular")
        rows[col], rows[pivot] = rows[pivot], rows[col]
        divisor = rows[col][col]
        rows[col] = [value / divisor for value in rows[col]]
        for i in range(len(b)):
            if i == col:
                continue
            factor = rows[i][col]
            rows[i] = [x - factor * y for x, y in zip(rows[i], rows[col])]
    return [rows[i][-1] for i in range(len(b))]


def covariance_oracle(case):
    """Posterior mean and covariance conditioning, evaluated at 80 digits."""
    with localcontext() as ctx:
        ctx.prec = 80
        B = [[D(v) for v in row] for row in case["B"]]
        H = [[D(v) for v in row] for row in case["observation"]["H"]]
        R = [[D(v) for v in row] for row in case["observation"]["R"]]
        y = [D(v) for v in case["observation"]["value"]]
        nobs, nstate = len(H), len(B)
        BHt = mm(B, transpose(H))
        M = add(mm(H, BHt), R)
        mean = [sum((BHt[i][j] * z for j, z in enumerate(solve(M, y))), Decimal(0))
                for i in range(nstate)]
        solved_columns = [solve(M, col) for col in transpose(mm(H, B))]
        covariance = [[B[i][j] - sum((BHt[i][k] * transpose(solved_columns)[k][j]
                                       for k in range(nobs)), Decimal(0))
                       for j in range(nstate)] for i in range(nstate)]
        if case["constraints"]:
            C = [[D(v) for v in row["coefficients"]] for row in case["constraints"]]
            rhs = [D(row["rhs"]) for row in case["constraints"]]
            residual = [rhs[i] - sum((C[i][j] * mean[j] for j in range(nstate)), Decimal(0))
                        for i in range(len(C))]
            Ccov = mm(C, covariance)
            weights = solve(mm(Ccov, transpose(C)), residual)
            covCt = mm(covariance, transpose(C))
            mean = [mean[i] + sum((covCt[i][j] * weights[j] for j in range(len(C))), Decimal(0))
                    for i in range(nstate)]
        return [float(value) for value in mean]


def scalar_case(optimum, lower, upper, sensitivity, background_variance, obs_variance):
    # Choose y so the unconstrained minimum of .5*d^2/B + .5*(H*d-y)^2/R
    # is the specified d=optimum; H is intentionally not restricted to one.
    y = optimum * (background_variance * sensitivity ** 2 + obs_variance) / (
        background_variance * sensitivity)
    return declaration(["x"], [0.0], [[background_variance]], [[sensitivity]], [y],
                       [[obs_variance]], bounds=[{"field": "x", "lower": lower, "upper": upper}])


class StationarityOracleTest(unittest.TestCase):
    def test_396_scalar_box_cases_with_varied_H_and_covariance_scales(self):
        endpoints = (-3.0, -1.0, -0.5, -0.2, 0.0, 0.2, 0.5, 1.0, 3.0)
        optima = (-4.0, -3.0, -1.0, -0.5, -0.2, 0.0, 0.2, 0.5, 1.0, 3.0, 4.0)
        sensitivities = (0.25, 0.5, 1.0, 2.0, 4.0)
        variances = ((0.25, 0.5), (1.0, 1.0), (4.0, 3.0))
        cases = 0
        for optimum in optima:
            for lower_i, lower in enumerate(endpoints):
                for upper_i, upper in enumerate(endpoints[lower_i + 1:]):
                    h = sensitivities[cases % len(sensitivities)]
                    b, r = variances[cases % len(variances)]
                    result = joint.evaluate(scalar_case(optimum, lower, upper, h, b, r))
                    expected = min(upper, max(lower, optimum))
                    self.assertTrue(math.isclose(result["candidate_state"][0], expected,
                                                 rel_tol=2e-11, abs_tol=2e-11),
                                    (optimum, lower, upper, h, b, r, result["candidate_state"]))
                    cases += 1
        self.assertEqual(cases, 396)

    def test_128_spd_posterior_covariance_oracles(self):
        # Eight well-conditioned SPD covariance/H fixtures, each tested with
        # sixteen feasible equality right-hand sides.
        checked = 0
        for seed in range(8):
            # Fixed integer factors make the inputs deterministic and exactly
            # reproducible while yielding varied, non-diagonal SPD matrices.
            A = [[1 + ((seed + i * 3 + j * 2) % 5) / 4.0 if j <= i else 0.0
                  for j in range(4)] for i in range(4)]
            B = [[sum(A[i][k] * A[j][k] for k in range(4)) + (0.5 if i == j else 0.0)
                  for j in range(4)] for i in range(4)]
            F = [[1 + ((seed * 2 + i * 3 + j) % 4) / 5.0 if j <= i else 0.0
                  for j in range(3)] for i in range(3)]
            R = [[sum(F[i][k] * F[j][k] for k in range(3)) + (0.75 if i == j else 0.0)
                  for j in range(3)] for i in range(3)]
            H = [[((seed + 2 * i + 3 * j) % 7 - 3) / 5.0 for j in range(4)]
                 for i in range(3)]
            y = [((seed * 3 + i * 2) % 9 - 4) / 3.0 for i in range(3)]
            C = [1.0, -0.5, 0.25, 1.5]
            for rhs_index in range(16):
                rhs = (rhs_index - 7.5) / 8.0
                case = declaration(["a", "b", "c", "d"], [0.0] * 4, B, H, y, R,
                                   equality=(C, rhs))
                expected = covariance_oracle(case)
                result = joint.evaluate(case)
                for i, (actual, reference) in enumerate(zip(result["analysis_increment"], expected)):
                    self.assertTrue(math.isclose(actual, reference, rel_tol=5e-9, abs_tol=5e-10),
                                    (seed, rhs, i, actual, reference))
                self.assertLessEqual(result["kkt_diagnostics"]["stationarity_residual"], 1e-12)
                checked += 1
        self.assertEqual(checked, 128)

    def test_ill_conditioned_scalar_objective_returns_analytical_minimum(self):
        case = scalar_case(0.4, -2.0, 2.0, 2.0, 1.0, 1.0)
        result = joint.evaluate(case)
        self.assertTrue(math.isclose(result["candidate_state"][0], 0.4, rel_tol=0, abs_tol=2e-14))
        self.assertEqual(result["kkt_diagnostics"]["status"], "PASS")

    def test_unit_reexpression_preserves_active_bound_and_equality_certificate(self):
        case = declaration(["x", "y"], [0.0, 0.0], [[1.0, 0.0], [0.0, 1.0]],
                           [[1.0, 0.0], [0.0, 1.0]], [-1.0, 0.5],
                           [[1.0, 0.0], [0.0, 1.0]], equality=([1.0, 1.0], 0.5),
                           bounds=[{"field": "x", "lower": 0.3, "upper": 1.3},
                                   {"field": "y", "lower": -2.0, "upper": 2.0}])
        original = joint.evaluate(case)
        scaled = copy.deepcopy(case)
        factor = 1000.0
        scaled["B"][0][0] *= factor * factor
        scaled["observation"]["H"][0][0] /= factor
        scaled["constraints"][0]["coefficients"][0] /= factor
        scaled["state_bounds"][0]["lower"] *= factor
        scaled["state_bounds"][0]["upper"] *= factor
        scaled["state_fields"][0] = "x_millunits"
        scaled["state_bounds"][0]["field"] = "x_millunits"
        transformed = joint.evaluate(scaled)
        self.assertAlmostEqual(original["candidate_state"][0], 0.3, places=14)
        self.assertAlmostEqual(original["candidate_state"][1], 0.2, places=14)
        self.assertAlmostEqual(transformed["candidate_state"][0], 300.0, places=12)
        self.assertAlmostEqual(transformed["candidate_state"][1], 0.2, places=12)
        for result in (original, transformed):
            diagnostics = result["kkt_diagnostics"]
            self.assertEqual(diagnostics["status"], "PASS")
            self.assertEqual(diagnostics["active_bounds"][0]["side"], "lower")
            self.assertLessEqual(diagnostics["primal_equality_residual"], 1e-12)
            self.assertLessEqual(diagnostics["stationarity_residual"], 1e-12)
            self.assertLessEqual(diagnostics["dual_sign_violation"], 1e-12)
            self.assertLessEqual(diagnostics["complementarity_residual"], 1e-12)

    def test_certificate_rejects_wrong_interior_solution(self):
        case = scalar_case(0.4, -2.0, 2.0, 2.0, 1.0, 1.0)
        with mock.patch.object(joint, "_solve", return_value=[0.5]):
            with self.assertRaisesRegex(ValueError, "KKT certificate"):
                joint.evaluate(case)

    def test_certificate_rejects_wrong_upper_bound_dual_sign(self):
        # The upper face at x=1 has positive objective derivative, so its
        # upper-bound multiplier must be negative under the reported convention.
        case = scalar_case(0.4, 0.0, 1.0, 2.0, 1.0, 1.0)
        real_quadratic = joint._quadratic

        def favor_wrong_upper(matrix, vector):
            if len(vector) == 1 and abs(vector[0] - 1.0) < 1e-14:
                return -100.0
            return real_quadratic(matrix, vector)

        with mock.patch.object(joint, "_quadratic", side_effect=favor_wrong_upper):
            with self.assertRaisesRegex(ValueError, "KKT certificate"):
                joint.evaluate(case)


if __name__ == "__main__":
    unittest.main()
