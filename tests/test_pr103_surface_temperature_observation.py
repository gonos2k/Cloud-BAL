import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from netCDF4 import Dataset
import numpy as np


SCRIPT = Path(__file__).resolve().parents[1] / "tools/pr103_surface_temperature_observation.py"
SPEC = importlib.util.spec_from_file_location("pr103_surface_temperature_observation", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def inverse_lambert_grid(ny, nx, *, lat1=35.0, lon1=126.0):
    """Independent spherical LCC inverse used to make nondegenerate fixtures."""
    radius, dx, dy, lon0 = MODULE.RE, 5000.0, 5000.0, 126.0
    phi1, phi2 = np.radians([30.0, 60.0])
    cone = np.log(np.cos(phi1) / np.cos(phi2)) / np.log(
        np.tan(np.pi / 4 + phi2 / 2) / np.tan(np.pi / 4 + phi1 / 2))
    factor = np.cos(phi1) * np.tan(np.pi / 4 + phi1 / 2) ** cone / cone

    def projected(lat, lon):
        phi = np.radians(lat)
        rho = radius * factor / np.tan(np.pi / 4 + phi / 2) ** cone
        theta = cone * np.radians(lon - lon0)
        return rho * np.sin(theta), -rho * np.cos(theta)

    x0, y0 = projected(lat1, lon1)
    lat_grid = np.empty((ny, nx), dtype=np.float64)
    lon_grid = np.empty((ny, nx), dtype=np.float64)
    for j in range(ny):
        for i in range(nx):
            x, y = x0 + i * dx, y0 + j * dy
            rho = np.hypot(x, y)
            lat_grid[j, i] = np.degrees(2 * np.arctan((radius * factor / rho) ** (1 / cone)) - np.pi / 2)
            lon_grid[j, i] = lon0 + np.degrees(np.arctan2(x, -y) / cone)
    return lat_grid.astype(np.float32), lon_grid.astype(np.float32)


class SurfaceTemperatureObservationTests(unittest.TestCase):
    def write_model_file(self, path, missing_variable=None):
        with Dataset(path, "w", format="NETCDF4") as nc:
            nc.createDimension("Time", 1)
            nc.createDimension("DateStrLen", 19)
            nc.createDimension("south_north", 4)
            nc.createDimension("west_east", 4)
            times = nc.createVariable("Times", "S1", ("Time", "DateStrLen"))
            times[0, :] = np.frombuffer(b"2026-08-16_13:00:00", dtype="S1")
            nc.MAP_PROJ = 1
            for name, value in (("TRUELAT1", 30.0), ("TRUELAT2", 60.0),
                                ("STAND_LON", 126.0), ("DX", 5000.0), ("DY", 5000.0)):
                setattr(nc, name, value)
            lat_grid, lon_grid = inverse_lambert_grid(4, 4)
            for name, value in (("XLAT", lat_grid), ("XLONG", lon_grid), ("T2", 280.0)):
                var = nc.createVariable(name, "f4", ("Time", "south_north", "west_east"), fill_value=-9999.0)
                var.units = "K" if name == "T2" else "degrees_north"
                data = np.full((1, 4, 4), value, dtype=np.float32) if np.isscalar(value) else value[np.newaxis, :, :]
                if name == missing_variable:
                    data[0, 1, 1] = -9999.0
                var[:] = data

    def test_model_reader_rejects_declared_fill_for_each_required_field(self):
        for name in ("T2", "XLAT", "XLONG"):
            with self.subTest(variable=name), tempfile.TemporaryDirectory() as tempdir:
                path = Path(tempdir) / "history.nc"
                self.write_model_file(path, missing_variable=name)
                with self.assertRaisesRegex(ValueError, f"{name} contains declared _FillValue"):
                    MODULE.model_metadata(path)

    def test_model_reader_requires_lambert_map_projection_and_valid_parameters(self):
        for attrs, message in (({"MAP_PROJ": 0}, "unsupported MAP_PROJ"),
                               ({"DX": 0.0}, "must be positive"),
                               ({"TRUELAT1": 90.0}, "strictly between"),
                               ({"TRUELAT2": float("nan")}, "invalid or missing Lambert parameter")):
            with self.subTest(attrs=attrs), tempfile.TemporaryDirectory() as tempdir:
                path = Path(tempdir) / "history.nc"
                self.write_model_file(path)
                with Dataset(path, "a") as nc:
                    for name, value in attrs.items():
                        setattr(nc, name, value)
                with self.assertRaisesRegex(ValueError, message):
                    MODULE.model_metadata(path)

        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "history.nc"
            self.write_model_file(path)
            with Dataset(path, "a") as nc:
                del nc.MAP_PROJ
            with self.assertRaisesRegex(ValueError, "missing MAP_PROJ"):
                MODULE.model_metadata(path)

    def test_lambert_mapping_gate_rejects_identical_malformed_grids(self):
        bad_lat = np.full((4, 4), 35.0, dtype=np.float32)
        bad_lon = np.full((4, 4), 126.0, dtype=np.float32)
        projection = dict(lat1=35.0, lon1=126.0, stdlon=126.0,
                          truelat1=30.0, truelat2=60.0, dx=5000.0, dy=5000.0)
        for arm in ("H", "A", "N"):
            with self.subTest(arm=arm), self.assertRaisesRegex(ValueError, "fails Lambert mapping prerequisite"):
                MODULE.grid_mapping_residuals(bad_lat.copy(), bad_lon.copy(), projection)

    def test_lambert_mapping_gate_accepts_real32_coordinates_from_independent_inverse(self):
        lat, lon = inverse_lambert_grid(18, 20)
        projection = dict(lat1=float(lat[0, 0]), lon1=float(lon[0, 0]), stdlon=126.0,
                          truelat1=30.0, truelat2=60.0, dx=5000.0, dy=5000.0)
        audit = MODULE.grid_mapping_residuals(lat, lon, projection)
        self.assertLessEqual(audit["i_delta_grid_units"]["max_abs"], audit["acceptance_tolerance_grid_units"])
        self.assertLessEqual(audit["j_delta_grid_units"]["max_abs"], audit["acceptance_tolerance_grid_units"])

    def test_lambert_mapping_gate_rejects_nonfinite_inverse_output(self):
        lat, lon = inverse_lambert_grid(4, 4)
        projection = dict(lat1=float(lat[0, 0]), lon1=float(lon[0, 0]), stdlon=126.0,
                          truelat1=30.0, truelat2=60.0, dx=5000.0, dy=5000.0)
        with patch.object(MODULE, "lc_grid_ij", return_value=(float("nan"), 1.0)):
            with self.assertRaisesRegex(ValueError, "nonfinite grid coordinates"):
                MODULE.grid_mapping_residuals(lat, lon, projection)

    def test_model_reader_all_zero_guard_is_diagnostic_only(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "history.nc"
            self.write_model_file(path)
            with Dataset(path, "a") as nc:
                nc.variables["T2"][:] = 0.0
            with self.assertRaisesRegex(ValueError, "all-zero.*likely uncomputed history diagnostic"):
                MODULE.model_metadata(path)

    @staticmethod
    def station(station_id, temperature_f, lat=0.0):
        return {
            "station_id": station_id, "wmo_id": station_id, "provider": "TST",
            "lat": lat, "lon": 0.0, "elev_m": 0.0, "time_hhmm": 1300,
            "temperature_f": temperature_f, "temperature_expected_accuracy_f": 1.0,
        }

    @staticmethod
    def compare_with_ij(observations, model, ij_by_lat):
        projection = dict(lat1=0.0, lon1=0.0, stdlon=0.0,
                          truelat1=30.0, truelat2=60.0, dx=5000.0, dy=5000.0)
        with patch.object(MODULE, "lc_grid_ij", side_effect=lambda lat, lon, **kw: ij_by_lat[lat]):
            return MODULE.compare(observations, model, projection)

    def test_wrf_mass_grid_lower_left_maps_to_one_one(self):
        projection = dict(lat1=34.0, lon1=126.0, stdlon=126.0,
                          truelat1=30.0, truelat2=60.0, dx=5000.0, dy=5000.0)
        i, j = MODULE.lc_grid_ij(34.0, 126.0, **projection)
        self.assertAlmostEqual(i, 1.0, places=7)
        self.assertAlmostEqual(j, 1.0, places=7)

    def test_gdtost_reproduces_bilinear_polynomial_at_fractional_point(self):
        y, x = np.mgrid[1:8, 1:8]
        field = 7.0 + 3.0 * x + 2.0 * y
        value, reason = MODULE.gdtost(field, 3.5, 3.25)
        self.assertIsNone(reason)
        self.assertAlmostEqual(value, 7.0 + 3.0 * 3.5 + 2.0 * 3.25, places=12)

    def test_gdtost_reproduces_quadratic_and_mixed_terms(self):
        y, x = np.mgrid[1:9, 1:9]
        field = x * x + 2 * y * y + 3 * x * y - 4 * x + 5 * y + 7
        i, j = 4.5, 3.25
        expected = i * i + 2 * j * j + 3 * i * j - 4 * i + 5 * j + 7
        value, reason = MODULE.gdtost(field, i, j)
        self.assertIsNone(reason)
        self.assertAlmostEqual(value, expected, places=11)

    def test_gdtost_masks_outer_and_inner_missing_stencils(self):
        field = np.full((8, 8), 2.0)
        field[1, :] = MODULE.MISSING_FLAG
        value, reason = MODULE.gdtost(field, 3.5, 3.25)
        self.assertIsNone(reason)
        self.assertAlmostEqual(value, 2.0)
        field[:] = 2.0
        field[3, 3] = MODULE.MISSING_FLAG
        value, reason = MODULE.gdtost(field, 4.5, 4.5)
        self.assertIsNone(value)
        self.assertEqual(reason, "invalid_model_stencil")

    def test_gdtost_matches_source_outer_stencil_fallback_value(self):
        y, x = np.mgrid[1:9, 1:9]
        field = (x * x + 2 * y * y + 3 * x * y - 4 * x + 5 * y + 7).astype(np.float64)
        field[:, 1] = MODULE.MISSING_FLAG
        value, reason = MODULE.gdtost(field, 3.5, 3.25)
        self.assertIsNone(reason)
        self.assertAlmostEqual(value, 76.875, places=11)

    def test_gdtost_rejects_incomplete_domain_stencil(self):
        field = np.ones((8, 8))
        value, reason = MODULE.gdtost(field, 0.5, 4.5)
        self.assertIsNone(value)
        self.assertEqual(reason, "outside_or_incomplete_4x4_stencil")

    def test_gdtost_accepts_source_boundary_fallback_but_rejects_extrapolation(self):
        field = np.full((8, 8), 4.0)
        value, reason = MODULE.gdtost(field, 2.0, 2.0)
        self.assertIsNone(reason)
        self.assertEqual(value, 4.0)
        value, reason = MODULE.gdtost(field, 1.5, 4.5)
        self.assertIsNone(reason)
        self.assertEqual(value, 4.0)
        value, reason = MODULE.gdtost(field, 0.5, 4.5)
        self.assertIsNone(value)
        self.assertEqual(reason, "outside_or_incomplete_4x4_stencil")

    def test_gdtost_rejects_invalid_model_stencil(self):
        field = np.ones((8, 8))
        field[3, 3] = np.nan
        value, reason = MODULE.gdtost(field, 4.5, 4.5)
        self.assertIsNone(value)
        self.assertEqual(reason, "invalid_model_stencil")

    def test_compare_skips_missing_first_record_and_keeps_valid_last_record(self):
        observations = [self.station("missing", MODULE.LSO_BADFLAG_F), self.station("valid", 32.0)]
        rows, counts = self.compare_with_ij(observations, np.full((8, 8), 273.15), {0.0: (4.5, 4.5)})
        self.assertEqual([row["station_id"] for row in rows], ["valid"])
        self.assertEqual(rows[0]["signed_model_minus_observation_c"], 0.0)
        self.assertEqual(counts["excluded_counts_by_reason"], {"missing_lso_temperature_sentinel": 1})

    def test_compare_skips_invalid_stencil_first_and_last(self):
        observations = [self.station("before", 68.0, -1.0), self.station("after", 68.0, 1.0)]
        model = np.full((8, 8), 273.15)
        model[3, 3] = np.nan
        rows, counts = self.compare_with_ij(
            observations, model, {-1.0: (4.5, 4.5), 1.0: (4.5, 4.5)}
        )
        self.assertEqual(rows, [])
        self.assertEqual(counts["excluded_counts_by_reason"], {"invalid_model_stencil": 2})

    def test_compare_skips_outside_first_and_last(self):
        observations = [self.station("outside", 68.0, -1.0), self.station("inside", 68.0, 1.0)]
        field = np.full((8, 8), 273.15)
        rows, counts = self.compare_with_ij(
            observations, field, {-1.0: (0.5, 4.5), 1.0: (4.5, 4.5)}
        )
        self.assertEqual([row["station_id"] for row in rows], ["inside"])
        self.assertEqual(counts["excluded_counts_by_reason"], {"outside_or_incomplete_4x4_stencil": 1})
        rows, counts = self.compare_with_ij(
            list(reversed(observations)), field, {-1.0: (0.5, 4.5), 1.0: (4.5, 4.5)}
        )
        self.assertEqual([row["station_id"] for row in rows], ["inside"])
        self.assertEqual(counts["excluded_counts_by_reason"], {"outside_or_incomplete_4x4_stencil": 1})

    def test_observation_units_are_converted_to_celsius(self):
        self.assertAlmostEqual(MODULE.fahrenheit_to_celsius(32.0), 0.0)
        self.assertAlmostEqual(MODULE.fahrenheit_to_celsius(212.0), 100.0)
        self.assertAlmostEqual(MODULE.kelvin_to_celsius(273.15), 0.0)


if __name__ == "__main__":
    unittest.main()
