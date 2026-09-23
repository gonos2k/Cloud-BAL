#!/usr/bin/env python3
"""Check the fixed-temperature cloud force integration and support gaps."""
import json
import unittest

import numpy as np

from diagnose_qbal_cloud_force import (
    ALPHA, G0, RD_AIR, _acceleration_at_pressure, _column_increment, relative_geopotential,
)
from diagnose_qbal_ground_ht_force import triangle_pressure_force


class CloudRelativeForceTest(unittest.TestCase):
    def setUp(self):
        self.pressure = np.array([100000., 50000., 5000.])
        self.xy = np.array([[0., 1000., 0.], [0., 0., 2000.]])
        self.triangles = np.array([[0, 1, 2]])
        self.latitude = np.array([0.4])
        self.latitude0 = 0.4

    def test_fixed_final_temperature_and_zero_reference(self):
        q_effect = np.array([[.01, .01, .01], [.02, .02, .02], [.04, .04, .04]])
        temperature = np.full_like(q_effect, 280.)
        support = np.ones_like(q_effect, dtype=bool)
        delta_tv = ALPHA * temperature * q_effect
        phi, reached = relative_geopotential(delta_tv, self.pressure, support, 2)
        self.assertTrue(reached.all())
        np.testing.assert_array_equal(phi[:, 2], 0.)
        expected = -RD_AIR * ALPHA * 280. * q_effect[:, 0] * np.log(20.)
        np.testing.assert_allclose(phi[:, 0], expected, rtol=2e-15, atol=1e-12)

        triangle_support = reached[self.triangles].all(axis=1)
        gradient, force = triangle_pressure_force(
            phi, triangle_support, self.triangles, self.xy, self.latitude, self.latitude0)
        expected_phi = -RD_AIR * ALPHA * 280. * np.log(20.) * q_effect[:, 0]
        expected_gx = (expected_phi[1] - expected_phi[0]) / 1000.
        expected_gy = (expected_phi[2] - expected_phi[0]) / 2000.
        np.testing.assert_allclose(gradient[:, 0, 0], [expected_gx, expected_gy], rtol=2e-15)
        np.testing.assert_allclose(force[:, 0, 0], [-expected_gx, -expected_gy], rtol=2e-15)
        np.testing.assert_array_equal(phi[:, 2], 0.)

    def test_missing_layer_stays_nan_and_does_not_bridge(self):
        valid = np.ones((3, 3), dtype=bool)
        valid[1, 1] = False
        delta_tv = np.ones((3, 3))
        delta_tv[~valid] = np.nan
        phi, reached = relative_geopotential(delta_tv, self.pressure, valid, 2)
        self.assertTrue(np.isnan(phi[1, :2]).all())
        self.assertFalse(reached[1, :2].any())
        support = np.ones((1, 3), dtype=bool)
        triangle_support = reached[self.triangles].all(axis=1)
        _, force = triangle_pressure_force(
            phi, support & triangle_support, self.triangles, self.xy, self.latitude, self.latitude0)
        self.assertTrue(np.isnan(force[:, 0, :2]).all())
        self.assertTrue(np.isfinite(force[:, 0, 2]).all())

    def test_vapor_increment_requires_supported_regular_layers(self):
        q_effect = np.array([.01, .02, .03])
        layer_support = np.array([True, True])
        increment, segments = _column_increment(q_effect, self.pressure, layer_support)
        expected = ((100000. - 50000.) * .015 + (50000. - 5000.) * .025) / G0
        self.assertAlmostEqual(increment, expected, places=13)
        self.assertEqual([row['layers'] for row in segments], [2])
        missing, no_segments = _column_increment(q_effect, self.pressure, np.zeros(2, bool))
        self.assertIsNone(missing)
        self.assertEqual(no_segments, [])

    def test_cli_100000_pa_acceleration_is_null_when_unsupported(self):
        support = np.array([False, True])
        acceleration = np.array([[np.nan, 1.0], [np.nan, 2.0]])
        value = _acceleration_at_pressure(
            np.array([100000.0, 50000.0]), support, acceleration, 100000.0)
        summary = {'100000_Pa_acceleration_en_m_s2': value}
        self.assertIsNone(json.loads(json.dumps(summary))['100000_Pa_acceleration_en_m_s2'])

    def test_cli_100000_pa_acceleration_is_preserved_when_supported(self):
        self.assertEqual(_acceleration_at_pressure(
            np.array([100000.0]), np.array([True]), np.array([[1.0], [2.0]]),
            100000.0), [1.0, 2.0])

    def test_cli_rejects_triangle_without_supported_levels(self):
        with self.assertRaisesRegex(ValueError, 'no supported pressure levels'):
            _acceleration_at_pressure(
                np.array([100000.0]), np.array([False]),
                np.full((2, 1), np.nan), 100000.0)


if __name__ == '__main__':
    unittest.main()
