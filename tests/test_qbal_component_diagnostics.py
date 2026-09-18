#!/usr/bin/env python3
"""Independent counterexamples for the component audit, not model runs."""
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('diagnostic', Path(__file__).with_name('diagnose_qbal_components.py'))
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)


class ComponentDiagnostics(unittest.TestCase):
    def run_rows(self, rows):
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / 'rows.bin'
            data = struct.pack('<4i', 4, 3, 3, len(rows))
            for ijk, rhs, coeff in rows:
                data += struct.pack('<3i7d', *ijk, rhs, *coeff)
            path.write_bytes(data)
            return diagnostic.diagnose(path)['components']

    @staticmethod
    def scale_rows(rows, scale):
        return [(ijk, rhs * scale, [value * scale for value in coeff])
                for ijk, rhs, coeff in rows]

    def test_weighted_compatibility_not_global_sum(self):
        result = self.run_rows([((2, 2, 2), 2., [2., 0, 0, 0, 0, 0]),
                                ((3, 2, 2), -1., [0, 1., 0, 0, 0, 0])])
        self.assertEqual(result[0]['compatibility'], 'COMPATIBLE_TO_ARITHMETIC')
        self.assertLess(abs(result[0]['left_rhs']), 1e-14)

    def test_zero_global_sum_can_be_incompatible(self):
        result = self.run_rows([((2, 2, 2), 1., [2., 0, 0, 0, 0, 0]),
                                ((3, 2, 2), -1., [0, 1., 0, 0, 0, 0])])
        self.assertEqual(result[0]['compatibility'], 'INCOMPATIBLE')
        self.assertAlmostEqual(result[0]['left_rhs'], -1 / 3)

    def test_nonreversible_cycle_uses_full_left_null_solve(self):
        result = self.run_rows([((2, 2, 2), 1., [2, 0, 1, 0, 0, 0]),
                                ((3, 2, 2), -1., [0, 1, 2, 0, 0, 0]),
                                ((3, 3, 2), 2., [0, 2, 0, 1, 0, 0]),
                                ((2, 3, 2), -2., [1, 0, 0, 2, 0, 0])])
        self.assertEqual(result[0]['compatibility'], 'COMPATIBLE_TO_ARITHMETIC')
        self.assertLess(abs(result[0]['left_rhs']), 1e-14)

    def test_zero_rows_and_declared_anchor(self):
        result = self.run_rows([((2, 2, 2), 1e-30, [0] * 6),
                                ((3, 3, 3), 1., [1, 0, 0, 0, 0, 0])])
        self.assertEqual(result[0]['compatibility'], 'INCOMPATIBLE')
        self.assertTrue(result[1]['anchored'])

    def test_two_row_obstruction_matches_exact_left_certificate(self):
        result = self.run_rows([((2, 2, 2), 2., [2., 0, 0, 0, 0, 0]),
                                ((3, 2, 2), 0., [0, 1., 0, 0, 0, 0])])[0]
        self.assertAlmostEqual(result['left_rhs'], 2 / 3)
        self.assertAlmostEqual(result['left_norm2'], (5 ** 0.5) / 3)
        self.assertAlmostEqual(result['obstruction_inf'], 2 / 3)
        self.assertAlmostEqual(result['obstruction_2'], 2 / (5 ** 0.5))
        self.assertTrue(result['fixed_tolerance_infeasible'])
        self.assertEqual(result['positive_diagonal_min'], 1.)
        self.assertEqual(result['positive_diagonal_max'], 2.)
        self.assertEqual(result['positive_diagonal_ratio'], 2.)

    def test_singleton_certificate_has_direct_obstruction_bound(self):
        result = self.run_rows([((2, 2, 2), 3., [0] * 6)])[0]
        self.assertEqual(result['obstruction_inf'], 3.)
        self.assertEqual(result['obstruction_2'], 3.)
        self.assertTrue(result['fixed_tolerance_infeasible'])
        self.assertIsNone(result['positive_diagonal_ratio'])

    def test_common_operator_rhs_scaling_preserves_relative_diagnostics(self):
        rows = [((2, 2, 2), 2., [2., 0, 0, 0, 0, 0]),
                ((3, 2, 2), 0., [0, 1., 0, 0, 0, 0])]
        base = self.run_rows(rows)[0]
        scaled = self.run_rows(self.scale_rows(rows, 7.))[0]
        for field in ('relative_defect', 'positive_diagonal_ratio'):
            self.assertAlmostEqual(base[field], scaled[field])
        self.assertAlmostEqual(scaled['left_rhs'], 7 * base['left_rhs'])
        self.assertAlmostEqual(scaled['rhs_norm_inf'], 7 * base['rhs_norm_inf'])
        self.assertAlmostEqual(scaled['rhs_norm2'], 7 * base['rhs_norm2'])
        self.assertAlmostEqual(scaled['obstruction_inf'],
                               7 * base['obstruction_inf'])
        self.assertAlmostEqual(scaled['obstruction_2'],
                               7 * base['obstruction_2'])
        self.assertAlmostEqual(scaled['left_norm2'], base['left_norm2'])


if __name__ == '__main__':
    unittest.main()
