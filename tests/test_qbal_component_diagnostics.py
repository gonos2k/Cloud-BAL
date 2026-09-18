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


if __name__ == '__main__':
    unittest.main()
