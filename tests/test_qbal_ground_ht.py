#!/usr/bin/env python3
"""Check the retained-HT identity and unsupported-level handling."""
import unittest

import numpy as np

from diagnose_qbal_ground_ht import G0, compare


class GroundHtComparisonTest(unittest.TestCase):
    def test_same_retained_ht_cancels(self):
        height = np.array([[10., 20.], [np.nan, np.nan]])
        before = np.array([[G0*10+3, G0*20-4], [np.nan, np.nan]])
        change = np.array([[0., 5.], [np.nan, np.nan]])
        ground = {'support': np.array([[True, True], [False, False]]),
                  'before': before, 'after': before+change,
                  'delta': np.array([change, change, change]),
                  'bound': np.zeros((2, 2))}
        stage, final = compare(ground, height)
        np.testing.assert_allclose(stage[0], [3, -4], atol=1e-13)
        np.testing.assert_allclose(final[0], [3, 1], atol=1e-13)
        self.assertTrue(np.isnan(stage[1]).all())
        self.assertTrue(np.isnan(final[1]).all())

        ground['delta'][2, 0, 1] = 6.
        with self.assertRaisesRegex(ValueError, 'closure'):
            compare(ground, height)

    def test_supported_ht_must_be_finite(self):
        ground = {'support': np.array([[True]]), 'before': np.array([[0.]]),
                  'after': np.array([[0.]]), 'delta': np.zeros((3, 1, 1)),
                  'bound': np.zeros((1, 1))}
        with self.assertRaisesRegex(ValueError, 'HT support'):
            compare(ground, np.array([[np.nan]]))

    def test_supported_inputs_and_bound_must_be_finite_and_valid(self):
        base = {'support': np.array([[True, False]]),
                'before': np.array([[1., np.nan]]),
                'after': np.array([[1., np.nan]]),
                'delta': np.zeros((3, 1, 2)),
                'bound': np.array([[0., np.nan]])}
        height = np.array([[0., np.nan]])
        stage, final = compare(base, height)
        self.assertEqual(stage[0, 0], 1.)
        self.assertEqual(final[0, 0], 1.)
        self.assertTrue(np.isnan(stage[0, 1]))
        self.assertTrue(np.isnan(final[0, 1]))

        for key, value in (('before', np.nan), ('after', np.inf),
                           ('delta', np.nan), ('bound', np.inf)):
            with self.subTest(key=key, value=value):
                ground = {name: array.copy() for name, array in base.items()}
                target = ground[key]
                if key == 'delta':
                    target[2, 0, 0] = value
                else:
                    target[0, 0] = value
                with self.assertRaisesRegex(ValueError, 'nonfinite supported'):
                    compare(ground, height)

        base['bound'][0, 0] = -1.
        with self.assertRaisesRegex(ValueError, 'negative supported bound'):
            compare(base, height)

    def test_comparison_arrays_must_match_support_shape(self):
        ground = {'support': np.array([[True]]), 'before': np.array([[0.]]),
                  'after': np.array([[0.]]), 'delta': np.zeros((3, 1, 1)),
                  'bound': np.zeros((1, 2))}
        with self.assertRaisesRegex(ValueError, 'shape mismatch'):
            compare(ground, np.array([[0.]]))

        ground['bound'] = np.zeros((1, 1))
        ground['delta'] = np.zeros((2, 1, 1))
        with self.assertRaisesRegex(ValueError, 'delta shape mismatch'):
            compare(ground, np.array([[0.]]))


if __name__ == '__main__':
    unittest.main()
