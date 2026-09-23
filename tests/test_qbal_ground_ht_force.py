import unittest

import numpy as np

from diagnose_qbal_ground_ht_force import (
    common_triangle_support,
    triangle_force_error_bound,
    triangle_pressure_force,
)


class GroundHeightForceTests(unittest.TestCase):
    def test_affine_field_uses_pr42_equal_area_metric(self):
        xy = np.array([[0.0, 1000.0, 0.0], [0.0, 0.0, 1000.0]])
        gx, gy = 0.25, -0.5
        field = (7.0 + gx * xy[0] + gy * xy[1])[:, None]
        triangles = np.array([[0, 1, 2]])
        support = np.array([[True]])
        lat0, latc = 0.6, 0.7
        gradient, acceleration = triangle_pressure_force(
            field, support, triangles, xy, np.array([latc]), lat0)
        np.testing.assert_allclose(gradient[:, 0, 0], [gx, gy], rtol=0, atol=1e-14)
        np.testing.assert_allclose(
            acceleration[:, 0, 0],
            [-np.cos(lat0) / np.cos(latc) * gx,
             -np.cos(latc) / np.cos(lat0) * gy], rtol=0, atol=1e-14)

    def test_support_requires_all_vertices_and_pr42_support(self):
        triangles = np.array([[0, 1, 2], [2, 3, 4]])
        node_support = np.array([[1, 1], [1, 1], [1, 1], [1, 1], [1, 0]], dtype=bool)
        force_support = np.array([[1, 1], [1, 1]], dtype=bool)
        actual = common_triangle_support(node_support, triangles, force_support)
        np.testing.assert_array_equal(actual, [[True, True], [True, False]])
        force_support[0, 1] = False
        actual = common_triangle_support(node_support, triangles, force_support)
        np.testing.assert_array_equal(actual, [[True, False], [True, False]])

    def test_gradient_and_force_are_linear_on_the_same_triangle(self):
        xy = np.array([[0.0, 800.0, 0.0], [0.0, 0.0, 600.0]])
        triangles = np.array([[0, 1, 2]])
        support = np.array([[True, True]])
        stage = np.array([[1.0, 2.0], [3.0, 5.0], [4.0, 8.0]])
        change = np.array([[0.5, -1.0], [-2.0, 0.25], [1.0, 3.0]])
        final = stage + change
        metric = dict(xy=xy, evaluation_latitude=np.array([0.65]), latitude0=0.6)
        _, force_stage = triangle_pressure_force(stage, support, triangles, **metric)
        _, force_change = triangle_pressure_force(change, support, triangles, **metric)
        _, force_final = triangle_pressure_force(final, support, triangles, **metric)
        np.testing.assert_allclose(force_stage + force_change, force_final, rtol=0, atol=1e-15)
        bound = triangle_force_error_bound(
            np.full((3, 2), 1e-9), np.asarray((stage, change, final)), support,
            triangles, xy, metric['evaluation_latitude'], metric['latitude0'])
        self.assertTrue(np.isfinite(bound[:, support]).all())
        self.assertTrue((bound[:, support] > 0).all())

    def test_missing_triangle_value_stays_nan_off_support(self):
        xy = np.array([[0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
        field = np.array([[0.0, np.nan], [1.0, np.nan], [2.0, np.nan]])
        support = np.array([[True, False]])
        gradient, acceleration = triangle_pressure_force(
            field, support, np.array([[0, 1, 2]]), xy, np.array([0.5]), 0.4)
        self.assertTrue(np.isfinite(gradient[:, 0, 0]).all())
        self.assertTrue(np.isfinite(acceleration[:, 0, 0]).all())
        self.assertTrue(np.isnan(gradient[:, 0, 1]).all())
        self.assertTrue(np.isnan(acceleration[:, 0, 1]).all())

    def test_degenerate_supported_triangle_is_rejected(self):
        xy = np.array([[0.0, 1.0, 2.0], [0.0, 0.0, 0.0]])
        with self.assertRaisesRegex(ValueError, 'degenerate'):
            triangle_pressure_force(np.array([[0.0], [1.0], [2.0]]),
                                    np.array([[True]]), np.array([[0, 1, 2]]),
                                    xy, np.array([0.5]), 0.4)


if __name__ == '__main__':
    unittest.main()
