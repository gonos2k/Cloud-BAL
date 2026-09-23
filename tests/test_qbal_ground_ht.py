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


if __name__ == '__main__':
    unittest.main()
