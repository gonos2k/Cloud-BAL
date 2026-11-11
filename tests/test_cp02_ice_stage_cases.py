import importlib.util
from pathlib import Path
import unittest

import numpy as np

spec = importlib.util.spec_from_file_location('cases', Path(__file__).resolve().parents[1] / 'tools/cp02_ice_stage_cases.py')
cases = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cases)

class CaseTests(unittest.TestCase):
    def test_nearest_ties_and_masks(self):
        values = np.array([[[0.5, 0.5], [0.49, 0.51]]])
        self.assertEqual(cases.nearest(values, values > 0, 0.5), (0, 0, 0))
        self.assertEqual(cases.nearest(values, values > 0.5, 0.5), (0, 1, 1))
        with self.assertRaises(ValueError):
            cases.nearest(values, np.zeros_like(values, dtype=bool), 0.5)
        with self.assertRaises(ValueError):
            cases.nearest(values, np.ones((2,), dtype=bool), 0.5)

    def test_selection_masks_and_shapes(self):
        q = np.array([[[0, 0.5, 0.9, 1.1, 2.0]]])
        selected, _ = cases.select_cases(q, np.ones_like(q), 1, 1)
        self.assertEqual(selected['interior_half_boundary'], (0, 0, 1))
        self.assertEqual(selected['closest_below_boundary'], (0, 0, 2))
        self.assertEqual(selected['closest_above_boundary'], (0, 0, 3))
        with self.assertRaises(ValueError):
            cases.select_cases(q, np.ones((2,)), 1, 1)

    def test_first_infeasible_and_maximum_water_content(self):
        q = np.array([[[0.0, 4.0, 2.0, 2.0]]])
        rho = np.array([[[1.0, 0.2, 1.0, 1.0]]])
        selected, _ = cases.select_cases(q, rho, 1, 1)
        self.assertEqual(selected['first_infeasible_lexicographic'], (0, 0, 2))
        self.assertEqual(selected['maximum_ice_water_content'], (0, 0, 2))

    def test_thermo_mapping(self):
        den = cases.density(np.array([0.25], np.float32), np.array([0.75], np.float32))
        self.assertEqual(den[0], 1)
        t = cases.dry_temperature(np.array([5], np.float32), np.array([1000], np.float32), np.array([99000], np.float32))
        self.assertEqual(t[0], 305)
        t = cases.dry_temperature(np.array([0], np.float32), np.array([0], np.float32), np.array([50000], np.float32))
        expected = np.float32(300) * np.power(np.float32(0.5), np.float32(287.0) / np.float32(1004.5))
        self.assertEqual(t[0], expected)

if __name__ == '__main__':
    unittest.main()
