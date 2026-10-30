import unittest
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from initial_precip_gate import (CASE_TO_GATE, QUANTILE_PAIRS, UNCHANGED_CASES,
                                case_qsnow_transform, dry_snow_mass, equal_mass_alpha,
                                gate_alpha, scaled_qsnow)


class InitialPrecipGateTest(unittest.TestCase):
    def test_gate_uses_positive_linear_quantiles_and_is_bounded(self):
        proxy = np.array([[0.0, 1.0, 2.0], [3.0, 4.0, 5.0]])
        alpha, thresholds = gate_alpha(proxy, 0.25, 0.75)
        self.assertAlmostEqual(thresholds["lower_value_kg_kg"], 2.0)
        self.assertAlmostEqual(thresholds["upper_value_kg_kg"], 4.0)
        self.assertEqual(alpha[0, 0], 1.0)
        self.assertEqual(alpha[1, 2], 3.0)
        self.assertTrue(np.all((alpha >= 1.0) & (alpha <= 3.0)))

    def test_gate_rejects_degenerate_positive_quantiles(self):
        with self.assertRaisesRegex(ValueError, "distinct"):
            gate_alpha(np.array([[0.0, 2.0, 2.0, 2.0]]), 0.50, 0.90)

    def test_alpha_is_horizontal_and_scaled_values_are_float32(self):
        source = np.array([[[0.1, 0.2], [0.3, 0.4]], [[0.5, 0.6], [0.7, 0.8]]],
                           dtype=np.float32)
        alpha = np.array([[1.0, 2.0], [2.5, 3.0]])
        result = scaled_qsnow(source, alpha)
        self.assertEqual(result.dtype, np.dtype("float32"))
        np.testing.assert_array_equal(result[0], (source[0].astype(np.float64) * alpha).astype(np.float32))
        np.testing.assert_array_equal(result[1], (source[1].astype(np.float64) * alpha).astype(np.float32))

    def test_equal_mass_scalar_matches_rounded_gate(self):
        source = np.array([[[0.1, 0.2], [0.3, 0.4]]], dtype=np.float32)
        dry_mass = np.array([[[1.0, 2.0], [3.0, 4.0]]])
        gate = scaled_qsnow(source, np.array([[1.0, 2.0], [2.5, 3.0]]))
        alpha, uniform, audit = equal_mass_alpha(source, gate, dry_mass)
        self.assertGreater(alpha, 1.0)
        self.assertLess(alpha, 3.0)
        self.assertLessEqual(audit["relative_mass_difference"], 1e-6)
        self.assertAlmostEqual(dry_snow_mass(uniform, dry_mass), audit["gate_diagnostic_mass_kg"], delta=1e-6)
        self.assertEqual(uniform.dtype, np.dtype("float32"))

    def test_scaled_qsnow_rejects_bad_shape_and_negative_values(self):
        source = np.ones((2, 3, 4), dtype=np.float32)
        with self.assertRaisesRegex(ValueError, "horizontal"):
            scaled_qsnow(source, np.ones((4, 3)))
        with self.assertRaisesRegex(ValueError, "nonnegative"):
            scaled_qsnow(-source, np.ones((3, 4)))

    def test_all_eight_case_paths_resolve_frozen_fields_without_cross_mutation(self):
        source = np.linspace(0.001, 0.02, 24, dtype=np.float32).reshape(2, 3, 4)
        source_before = source.copy()
        proxy = np.array([[0.0, 1.0, 2.0, 3.0], [4.0, 5.0, 6.0, 7.0],
                          [8.0, 9.0, 10.0, 11.0]])
        dry_mass = np.linspace(1.0, 10.0, 24).reshape(2, 3, 4)
        frozen = {}
        for name, pair in QUANTILE_PAIRS.items():
            gate_alpha_map, _ = gate_alpha(proxy, *pair)
            gate = scaled_qsnow(source, gate_alpha_map)
            eq_alpha, eq, _ = equal_mass_alpha(source, gate, dry_mass)
            frozen[f"{name}_alpha"] = gate_alpha_map
            frozen[f"{name}_qsn_gated"] = gate
            frozen[f"{name}_alpha_equal_mass"] = np.full(proxy.shape, eq_alpha)
            frozen[f"{name}_qsn_equal_mass"] = eq

        self.assertEqual(len(CASE_TO_GATE), 6)
        for case_id in CASE_TO_GATE:
            result = case_qsnow_transform(case_id, source, frozen)
            self.assertTrue(result["write_qsnow"])
            self.assertEqual(result["gate_name"], CASE_TO_GATE[case_id][1])
            self.assertEqual(result["replacement"].dtype, np.dtype("float32"))
        for case_id in UNCHANGED_CASES:
            result = case_qsnow_transform(case_id, source, frozen)
            self.assertFalse(result["write_qsnow"])
            self.assertIs(result["replacement"], source)
            np.testing.assert_array_equal(result["replacement"], source_before)
        np.testing.assert_array_equal(source, source_before)
        with self.assertRaisesRegex(ValueError, "unknown"):
            case_qsnow_transform("UNPLANNED_CASE", source, frozen)


if __name__ == "__main__":
    unittest.main()
