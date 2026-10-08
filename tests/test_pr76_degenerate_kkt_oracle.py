"""Exact KKT witness oracles for equality and box-bound degeneracy (PR76)."""

from fractions import Fraction
from itertools import permutations
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pr73_joint_analysis as joint


def Q(value):
    """Convert dyadic fixture values to exact rational arithmetic."""
    return Fraction(str(value))


def declaration(fields, background, B, H, observation, R, equalities, bounds):
    return {
        "schema_version": 1,
        "evidence_class": "MANUFACTURED_ALGORITHM_FIXTURE",
        "state_fields": fields,
        "background_state": background,
        "B": B,
        "observation": {"H": H, "value": observation, "R": R},
        "authorities": {name: {"evidence_id": f"manufactured:{name}"}
                        for name in ("H", "B", "R", "background_prior", "analysis_change")},
        "process_increments": {name: [0.0] * len(fields)
                               for name in ("phase", "external_source", "physical_boundary")},
        "constraints": [
            {"evidence_id": f"manufactured:pr76-equality-{index}",
             "coefficients": row, "rhs": rhs}
            for index, (row, rhs) in enumerate(equalities)
        ],
        "state_bounds": bounds,
    }


def singleton_case(permuted=False):
    fields = ["x", "y"]
    y = [-1.0, 1.0]
    equality = [1.0, 1.0]
    lower = [0.0, 0.0]
    upper = [1.0, 1.0]
    expected = [0.0, 0.0]
    lower_duals = [2.0, 0.0]
    if permuted:
        order = [1, 0]
        fields = [fields[i] for i in order]
        y = [y[i] for i in order]
        equality = [equality[i] for i in order]
        lower = [lower[i] for i in order]
        upper = [upper[i] for i in order]
        expected = [expected[i] for i in order]
        lower_duals = [lower_duals[i] for i in order]
    case = declaration(fields, [0.0, 0.0], [[1.0, 0.0], [0.0, 1.0]],
                       [[1.0, 0.0], [0.0, 1.0]], y,
                       [[1.0, 0.0], [0.0, 1.0]], [(equality, 0.0)],
                       [{"field": field, "lower": lo, "upper": hi}
                        for field, lo, hi in zip(fields, lower, upper)])
    return case, expected, [1.0], lower_duals, [0.0, 0.0]


def mixed_face_case(seed=0, scales=None, order=(0, 1, 2, 3)):
    """Build an exact KKT witness with mixed faces, duplicate equalities, and units."""
    names = ["a", "b", "fixed", "top"]
    patterns = [
        ([0.0, 0.0, 1.0, 1.0], [(0.0, 2.0), (0.0, 2.0), (1.0, 1.0), (0.0, 1.0)]),
        ([1.0, 1.0, 0.0, 0.0], [(0.0, 1.0), (0.0, 1.0), (0.0, 0.0), (0.0, 2.0)]),
        ([0.0, 1.0, 0.0, 1.0], [(0.0, 2.0), (0.0, 1.0), (0.0, 0.0), (0.0, 2.0)]),
    ]
    point, sides = patterns[seed % len(patterns)]
    if scales is None:
        scales = tuple(2.0 ** ((seed + 2 * i) % 7 - 3) for i in range(4))
    equality_multiplier = (seed % 9 - 4) / 2.0
    lagrangian_gradient = []
    lower_by_index = [0.0] * 4
    upper_by_index = [0.0] * 4
    fixed_by_index = [0.0] * 4
    for i, (lo, hi) in enumerate(sides):
        dual = ((seed + 2 * i) % 9) / 4.0
        if lo == hi:
            gradient_value = (seed % 7 - 3) / 2.0
            fixed_by_index[i] = -gradient_value
        elif point[i] == lo:
            gradient_value = dual
            lower_by_index[i] = dual
        elif point[i] == hi:
            gradient_value = -dual
            upper_by_index[i] = dual
        else:
            gradient_value = 0.0
        lagrangian_gradient.append(gradient_value)
    gradient = [value - equality_multiplier for value in lagrangian_gradient]
    observed = [2.0 * point[i] - gradient[i] for i in range(4)]
    fields = [names[i] for i in order]
    expected = [scales[i] * point[i] for i in order]
    observation = [observed[i] for i in order]
    variances = [scales[i] ** 2 for i in order]
    H = [[(1.0 / scales[order[j]]) if i == j else 0.0 for j in range(4)]
         for i in range(4)]
    B = [[variances[i] if i == j else 0.0 for j in range(4)] for i in range(4)]
    rhs = sum(point)
    equalities = [([1.0 / scales[i] for i in order], rhs),
                  ([2.0 / scales[i] for i in order], 2.0 * rhs)]
    bounds = [{"field": names[i], "lower": sides[i][0] * scales[i],
               "upper": sides[i][1] * scales[i]} for i in order]
    case = declaration(fields, [0.0] * 4, B, H, observation,
                       [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)],
                       equalities, bounds)
    equality_multipliers = [equality_multiplier, 0.0]
    lower_duals = [0.0] * 4
    upper_duals = [0.0] * 4
    fixed_duals = [0.0] * 4
    for i in range(4):
        j = order.index(i)
        lower_duals[j] = lower_by_index[i] / scales[i]
        upper_duals[j] = upper_by_index[i] / scales[i]
        fixed_duals[j] = fixed_by_index[i] / scales[i]
    return case, expected, equality_multipliers, lower_duals, upper_duals, fixed_duals


def exact_objective(case, state):
    """Evaluate the declared strictly convex quadratic using Fractions."""
    x = [Q(value) for value in state]
    B = [[Q(value) for value in row] for row in case["B"]]
    H = [[Q(value) for value in row] for row in case["observation"]["H"]]
    R = [[Q(value) for value in row] for row in case["observation"]["R"]]
    y = [Q(value) for value in case["observation"]["value"]]
    # Fixtures use diagonal B and R. This direct quadratic evaluation does not
    # share the production solver's face enumeration or KKT linear solver.
    prior = sum((x[i] * x[i] / B[i][i] for i in range(len(x))), Fraction(0))
    residual = [sum((H[i][j] * x[j] for j in range(len(x))), Fraction(0)) - y[i]
                for i in range(len(y))]
    observation = sum((residual[i] * residual[i] / R[i][i]
                       for i in range(len(residual))), Fraction(0))
    return (prior + observation) / 2


def exact_lagrangian_gradient(case, state, equality_multipliers):
    x = [Q(value) for value in state]
    B = case["B"]
    H = case["observation"]["H"]
    y = case["observation"]["value"]
    residuals = [sum((Q(H[i][k]) * x[k] for k in range(len(x))), Fraction(0)) - Q(y[i])
                 for i in range(len(y))]
    gradient = []
    for j in range(len(x)):
        prior = x[j] / Q(B[j][j])
        observation = sum((Q(H[i][j]) * residuals[i] /
                           Q(case["observation"]["R"][i][i])
                           for i in range(len(y))), Fraction(0))
        gradient.append(prior + observation)
    for row, multiplier in zip(case["constraints"], equality_multipliers):
        for j, coefficient in enumerate(row["coefficients"]):
            gradient[j] += Q(coefficient) * Q(multiplier)
    return gradient


def assert_exact_witness(test, case, expected, equality_multipliers,
                         lower_duals, upper_duals, fixed_duals):
    """Check primal feasibility and a nonnegative exact KKT certificate."""
    x = [Q(value) for value in expected]
    constraints = case["constraints"]
    for row in constraints:
        lhs = sum((Q(a) * value for a, value in zip(row["coefficients"], x)), Fraction(0))
        test.assertEqual(lhs, Q(row["rhs"]))

    lagrangian_gradient = exact_lagrangian_gradient(case, expected, equality_multipliers)

    bound_map = {bound["field"]: bound for bound in case["state_bounds"]}
    for j, field in enumerate(case["state_fields"]):
        bound = bound_map[field]
        lower = Q(bound["lower"])
        upper = Q(bound["upper"])
        test.assertGreaterEqual(x[j], lower)
        test.assertLessEqual(x[j], upper)
        if lower == upper:
            test.assertEqual(lagrangian_gradient[j] + Q(fixed_duals[j]), 0)
        elif x[j] == lower:
            test.assertEqual(lagrangian_gradient[j], Q(lower_duals[j]))
            test.assertGreaterEqual(Q(lower_duals[j]), 0)
            test.assertEqual(Q(upper_duals[j]), 0)
        elif x[j] == upper:
            test.assertEqual(lagrangian_gradient[j], -Q(upper_duals[j]))
            test.assertGreaterEqual(Q(upper_duals[j]), 0)
            test.assertEqual(Q(lower_duals[j]), 0)
        else:
            test.assertEqual(lagrangian_gradient[j], 0)
            test.assertEqual(Q(lower_duals[j]), 0)
            test.assertEqual(Q(upper_duals[j]), 0)
    return exact_objective(case, expected)


def assert_returned_certificate(test, case, result):
    """Independently check the solver's chosen, potentially nonunique certificate."""
    state = result["candidate_state"]
    diagnostic = result["kkt_diagnostics"]
    x = [Q(value) for value in state]
    for row in case["constraints"]:
        residual = sum((Q(a) * value for a, value in zip(row["coefficients"], x)), Fraction(0)) - Q(row["rhs"])
        scale = max(Fraction(1), abs(Q(row["rhs"])),
                    sum((abs(Q(a) * value) for a, value in zip(row["coefficients"], x)), Fraction(0)))
        test.assertLessEqual(abs(residual), Q("2e-12") * scale)
    bound_map = {bound["field"]: bound for bound in case["state_bounds"]}
    for field, value in zip(case["state_fields"], x):
        bound = bound_map[field]
        test.assertGreaterEqual(value + Q("2e-12"), Q(bound["lower"]))
        test.assertLessEqual(value - Q("2e-12"), Q(bound["upper"]))

    gradient = exact_lagrangian_gradient(case, state, [0.0] * len(case["constraints"]))
    state_scale = [Q(value) for value in diagnostic["normalized_covariance_scales"]["state"]]
    normalized_gradient = [state_scale[i] * gradient[i] for i in range(len(x))]
    equality_rows = diagnostic["equality_rows_normalized"]
    equality_multipliers = diagnostic["equality_multipliers_normalized"]
    test.assertEqual(len(equality_rows), len(equality_multipliers))
    for row, multiplier in zip(equality_rows, equality_multipliers):
        for i, coefficient in enumerate(row):
            normalized_gradient[i] += Q(coefficient) * Q(multiplier)
    for active in diagnostic["active_bounds"]:
        i = case["state_fields"].index(active["field"])
        multiplier = Q(active["multiplier"])
        if active["side"] == "lower":
            test.assertLessEqual(abs(x[i] - Q(bound_map[active["field"]]["lower"])), Q("2e-12"))
            test.assertGreaterEqual(multiplier, -Q("2e-12"))
            normalized_gradient[i] -= multiplier
        elif active["side"] == "upper":
            test.assertLessEqual(abs(x[i] - Q(bound_map[active["field"]]["upper"])), Q("2e-12"))
            test.assertGreaterEqual(multiplier, -Q("2e-12"))
            normalized_gradient[i] += multiplier
        else:
            test.assertEqual(Q(bound_map[active["field"]]["lower"]),
                             Q(bound_map[active["field"]]["upper"]))
            test.assertLessEqual(abs(x[i] - Q(bound_map[active["field"]]["lower"])), Q("2e-12"))
            normalized_gradient[i] += multiplier
    scale = max([Fraction(1)] + [abs(value) for value in normalized_gradient])
    for residual in normalized_gradient:
        test.assertLessEqual(abs(residual), Q("2e-10") * scale)
    test.assertEqual(diagnostic["status"], "PASS")


class DegenerateKktOracleTest(unittest.TestCase):
    def test_exact_singleton_and_variable_order_permutation(self):
        for permuted in (False, True):
            with self.subTest(permuted=permuted):
                case, expected, eq_duals, lower_duals, upper_duals = singleton_case(permuted)
                objective = assert_exact_witness(self, case, expected, eq_duals,
                                                 lower_duals, upper_duals, [0.0, 0.0])
                self.assertEqual(objective, Fraction(1, 1))
                result = joint.evaluate(case)
                for actual, reference in zip(result["candidate_state"], expected):
                    self.assertTrue(math.isclose(actual, reference, rel_tol=0, abs_tol=1e-14))
                diagnostic = result["kkt_diagnostics"]
                self.assertEqual(diagnostic["status"], "PASS")
                self.assertLessEqual(diagnostic["primal_equality_residual"], 1e-12)
                self.assertLessEqual(diagnostic["stationarity_residual"], 1e-12)
                assert_returned_certificate(self, case, result)

    def test_duplicate_equalities_mixed_active_faces_and_unit_scaling(self):
        orders = list(permutations(range(4)))
        cases = [mixed_face_case(seed=index, order=orders[index % len(orders)])
                 for index in range(160)]
        for index, (case, expected, eq_duals, lower_duals, upper_duals, fixed_duals) in enumerate(cases):
            with self.subTest(case=index):
                expected_objective = assert_exact_witness(
                    self, case, expected, eq_duals, lower_duals, upper_duals, fixed_duals)
                result = joint.evaluate(case)
                for actual, reference in zip(result["candidate_state"], expected):
                    self.assertTrue(math.isclose(actual, reference, rel_tol=0, abs_tol=2e-13),
                                    (index, actual, reference))
                self.assertTrue(math.isclose(result["objective_value"], float(expected_objective),
                                             rel_tol=0, abs_tol=2e-13))
                diagnostic = result["kkt_diagnostics"]
                self.assertEqual(diagnostic["status"], "PASS")
                self.assertLessEqual(diagnostic["primal_equality_residual"], 1e-12)
                self.assertLessEqual(diagnostic["stationarity_residual"], 1e-12)
                self.assertLessEqual(diagnostic["dual_sign_violation"], 1e-12)
                self.assertLessEqual(diagnostic["complementarity_residual"], 1e-12)
                assert_returned_certificate(self, case, result)
        self.assertEqual(len(cases), 160)

    def test_exact_feasible_nonoptimal_point_is_not_an_oracle_witness(self):
        case, optimum, eq_duals, lower_duals, upper_duals, fixed_duals = mixed_face_case(
            seed=0, scales=(1.0, 1.0, 1.0, 1.0))
        optimum_cost = assert_exact_witness(self, case, optimum, eq_duals,
                                            lower_duals, upper_duals, fixed_duals)
        control = [Fraction(1, 2), Fraction(0), Fraction(1), Fraction(1, 2)]
        self.assertEqual(sum(control), 2)
        self.assertEqual(2 * sum(control), 4)
        for value, bound in zip(control, case["state_bounds"]):
            self.assertGreaterEqual(value, Q(bound["lower"]))
            self.assertLessEqual(value, Q(bound["upper"]))
        control_lagrangian_gradient = exact_lagrangian_gradient(case, control, eq_duals)
        self.assertNotEqual(control_lagrangian_gradient[0], 0)
        self.assertNotEqual(control_lagrangian_gradient[3], 0)
        control_cost = exact_objective(case, control)
        self.assertGreater(control_cost, optimum_cost)


if __name__ == "__main__":
    unittest.main()
