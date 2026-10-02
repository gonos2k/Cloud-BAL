#!/usr/bin/env python3
"""Hemisphere and standard-parallel checks for the independent WPS mapper."""

from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from verify_shadow_wps_pair import _lambert_latlon  # noqa: E402


def geometry(*, startlat: float, truelat1: float, truelat2: float) -> dict[str, float]:
    return {
        "startlat": startlat,
        "startlon": 145.0,
        "xlonc": 135.0,
        "truelat1": truelat1,
        "truelat2": truelat2,
        "earth_radius_km": 6370.0,
        "dx_km": 12.0,
        "dy_km": 15.0,
    }


class LambertHemisphereTests(unittest.TestCase):
    def test_northern_lambert_coordinates_are_unchanged(self) -> None:
        latitude, longitude = _lambert_latlon(
            geometry(startlat=35.0, truelat1=30.0, truelat2=60.0), (3, 4)
        )
        expected = np.array(
            [35.0, 35.12256554, 35.23071405, 145.0, 145.15435868, 145.44287157]
        )
        actual = np.array(
            [latitude[0, 0], latitude[1, 1], latitude[2, 3],
             longitude[0, 0], longitude[1, 1], longitude[2, 3]]
        )
        np.testing.assert_allclose(actual, expected, rtol=0.0, atol=5e-9)

    def test_southern_lambert_reference_and_grid_shapes(self) -> None:
        # Reference geometry: SW=-35/145, Lambert center=135, parallels=-30/-60.
        expected_reference = np.array(
            [-35.0, -34.835983194144326, 145.0, 145.24483279708045]
        )
        for shape in ((2, 3), (3, 4), (17, 23), (40, 40)):
            with self.subTest(shape=shape):
                latitude, longitude = _lambert_latlon(
                    geometry(startlat=-35.0, truelat1=-30.0, truelat2=-60.0), shape
                )
                self.assertEqual(latitude.shape, shape)
                self.assertEqual(longitude.shape, shape)
                np.testing.assert_allclose(
                    [latitude[0, 0], latitude[1, 2],
                     longitude[0, 0], longitude[1, 2]],
                    expected_reference,
                    rtol=0.0,
                    atol=5e-9,
                )
                self.assertTrue(np.all(np.diff(latitude, axis=0) > 0.0))
                self.assertTrue(np.all(np.diff(longitude, axis=1) > 0.0))
                self.assertTrue(np.all((-90.0 <= latitude) & (latitude < 0.0)))

    def test_equal_southern_standard_parallels(self) -> None:
        latitude, longitude = _lambert_latlon(
            geometry(startlat=-35.0, truelat1=-45.0, truelat2=-45.0), (11, 13)
        )
        self.assertAlmostEqual(latitude[0, 0], -35.0, places=12)
        self.assertAlmostEqual(longitude[0, 0], 145.0, places=12)
        self.assertTrue(np.all(np.isfinite(latitude)))
        self.assertTrue(np.all(np.isfinite(longitude)))
        self.assertTrue(np.all(np.diff(latitude, axis=0) > 0.0))
        self.assertTrue(np.all(np.diff(longitude, axis=1) > 0.0))

    def test_optional_pyproj_reference(self) -> None:
        try:
            from pyproj import Proj
        except ImportError:
            self.skipTest("pyproj/PROJ is not installed in this environment")

        for startlat, parallel1, parallel2 in (
            (35.0, 30.0, 60.0),
            (-35.0, -30.0, -60.0),
        ):
            geom = geometry(startlat=startlat, truelat1=parallel1, truelat2=parallel2)
            projection = Proj(
                proj="lcc",
                lat_0=startlat,
                lon_0=geom["xlonc"],
                lat_1=parallel1,
                lat_2=parallel2,
                R=geom["earth_radius_km"] * 1000.0,
                units="m",
            )
            x_start, y_start = projection(geom["startlon"], startlat)
            rows, columns = np.indices((9, 12), dtype=np.float64)
            longitude_ref, latitude_ref = projection(
                x_start + columns * geom["dx_km"] * 1000.0,
                y_start + rows * geom["dy_km"] * 1000.0,
                inverse=True,
            )
            latitude, longitude = _lambert_latlon(geom, (9, 12))
            np.testing.assert_allclose(latitude, latitude_ref, rtol=0.0, atol=1e-9)
            np.testing.assert_allclose(longitude, longitude_ref, rtol=0.0, atol=1e-9)


if __name__ == "__main__":
    unittest.main()
