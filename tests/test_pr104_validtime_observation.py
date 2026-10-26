import importlib.util
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from netCDF4 import Dataset
import numpy as np


SCRIPT = Path(__file__).resolve().parents[1] / "tools/pr104_validtime_observation.py"
SPEC = importlib.util.spec_from_file_location("pr104_validtime_observation", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def inverse_lambert_grid(ny, nx):
    """Independent spherical LCC inverse for valid binary32 history fixtures."""
    radius, spacing, lon0 = MODULE.PR103.RE, 5000.0, 126.0
    phi1, phi2 = np.radians([30.0, 60.0])
    cone = np.log(np.cos(phi1) / np.cos(phi2)) / np.log(
        np.tan(np.pi / 4 + phi2 / 2) / np.tan(np.pi / 4 + phi1 / 2))
    factor = np.cos(phi1) * np.tan(np.pi / 4 + phi1 / 2) ** cone / cone
    anchor_phi = np.radians(35.0)
    rho0 = radius * factor / np.tan(np.pi / 4 + anchor_phi / 2) ** cone
    lat, lon = np.empty((ny, nx)), np.empty((ny, nx))
    for j in range(ny):
        for i in range(nx):
            x, y = i * spacing, -rho0 + j * spacing
            rho = np.hypot(x, y)
            lat[j, i] = np.degrees(2 * np.arctan((radius * factor / rho) ** (1 / cone)) - np.pi / 2)
            lon[j, i] = lon0 + np.degrees(np.arctan2(x, -y) / cone)
    return lat.astype(np.float32), lon.astype(np.float32)


class ExplicitValidTimeObservationTests(unittest.TestCase):
    def write_model(self, path, times):
        with Dataset(path, "w", format="NETCDF4") as nc:
            nc.createDimension("Time", len(times))
            nc.createDimension("DateStrLen", 19)
            nc.createDimension("south_north", 5)
            nc.createDimension("west_east", 5)
            times_var = nc.createVariable("Times", "S1", ("Time", "DateStrLen"))
            for index, value in enumerate(times):
                times_var[index, :] = np.frombuffer(value.encode("ascii"), dtype="S1")
            nc.MAP_PROJ = 1
            for name, value in (("TRUELAT1", 30.0), ("TRUELAT2", 60.0),
                                ("STAND_LON", 126.0), ("DX", 5000.0), ("DY", 5000.0)):
                setattr(nc, name, value)
            lat_grid, lon_grid = inverse_lambert_grid(5, 5)
            for name, value in (("XLAT", lat_grid), ("XLONG", lon_grid), ("T2", 280.0)):
                var = nc.createVariable(name, "f4", ("Time", "south_north", "west_east"), fill_value=-9999.0)
                var.units = "K" if name == "T2" else "degrees_north"
                data = np.full((len(times), 5, 5), value, dtype=np.float32) if np.isscalar(value) else np.broadcast_to(value, (len(times), 5, 5))
                var[:] = data
            nc.variables["T2"][1:, :, :] = 281.0

    @staticmethod
    def write_lso(path, header_date="16-AUG-2026", header_time="14:00:00.00"):
        path.write_text(f"{header_date} {header_time} 0 0\n", encoding="ascii")

    def test_valid_time_requires_explicit_utc_and_lso_precision(self):
        self.assertEqual(MODULE.parse_valid_time("2026-08-16T14:00:00Z"),
                         datetime(2026, 8, 16, 14, tzinfo=timezone.utc))
        for value in ("2026-08-16T14:00:00", "2026-08-16T14:00:01Z", "not-a-time"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                MODULE.parse_valid_time(value)

    def test_model_reader_selects_exact_record_after_first(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "history.nc"
            self.write_model(path, ["2026-08-16_13:00:00", "2026-08-16_14:00:00"])
            record = {}
            _, t2, _, _ = MODULE.PR103.model_metadata(
                path, "2026-08-16T14:00:00Z", record_metadata=record)
            self.assertTrue(np.all(t2 == 281.0))
            self.assertEqual(record, {"index": 1, "stored_time": "2026-08-16_14:00:00"})

    def test_model_reader_rejects_missing_and_duplicate_exact_records(self):
        for times in (["2026-08-16_13:00:00"],
                      ["2026-08-16_14:00:00", "2026-08-16_14:00:00"]):
            with self.subTest(times=times), tempfile.TemporaryDirectory() as tempdir:
                path = Path(tempdir) / "history.nc"
                self.write_model(path, list(times))
                with self.assertRaisesRegex(ValueError, "expected exactly one history record"):
                    MODULE.PR103.model_metadata(path, "2026-08-16T14:00:00Z")

    def test_model_reader_checks_declared_fill_on_selected_record(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "history.nc"
            self.write_model(path, ["2026-08-16_13:00:00", "2026-08-16_14:00:00"])
            with Dataset(path, "a") as nc:
                nc.variables["T2"][1, 2, 2] = -9999.0
            with self.assertRaisesRegex(ValueError, "T2 contains declared _FillValue"):
                MODULE.PR103.model_metadata(path, "2026-08-16T14:00:00Z")

    def test_identical_malformed_arm_grids_fail_before_any_station_scores(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            histories = {}
            for arm in ("H", "A", "N"):
                path = root / f"{arm}.nc"
                self.write_model(path, ["2026-08-16_14:00:00"])
                with Dataset(path, "a") as nc:
                    nc.variables["XLAT"][:] = 35.0
                    nc.variables["XLONG"][:] = 126.0
                histories[arm] = path
            observation_path = root / "obs.lso"
            self.write_lso(observation_path)
            with patch.object(MODULE.PR103, "compare") as score:
                with self.assertRaisesRegex(ValueError, "fails Lambert mapping prerequisite"):
                    MODULE.load_histories(histories,
                                          MODULE.parse_valid_time("2026-08-16T14:00:00Z"),
                                          [], observation_path)
            score.assert_not_called()

    def test_lso_header_date_must_match_valid_date(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "observation.lso"
            self.write_lso(path, "17-AUG-2026")
            with self.assertRaisesRegex(ValueError, "LSO header timestamp .* does not match"):
                MODULE.load_histories({"H": path, "A": path, "N": path},
                                      MODULE.parse_valid_time("2026-08-16T14:00:00Z"), [], path)

    def test_lso_header_hour_must_match_valid_time(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "observation.lso"
            self.write_lso(path, header_time="13:00:00.00")
            with self.assertRaisesRegex(ValueError, "LSO header timestamp .* does not match"):
                MODULE.load_histories({"H": path, "A": path, "N": path},
                                      MODULE.parse_valid_time("2026-08-16T14:00:00Z"), [], path)

    def test_observation_numeric_fields_must_be_finite_but_sentinel_is_allowed(self):
        fields = ("lat", "lon", "elev_m", "temperature_f", "temperature_expected_accuracy_f")
        for field in fields:
            for value in (float("nan"), float("inf"), float("-inf")):
                with self.subTest(field=field, value=value):
                    observation = {"lat": 35.0, "lon": 126.0, "elev_m": 0.0,
                                   "temperature_f": 70.0,
                                   "temperature_expected_accuracy_f": 1.0}
                    observation[field] = value
                    with self.assertRaisesRegex(ValueError, f"nonfinite or invalid {field}"):
                        MODULE.validate_observation_values([observation])

        observation = {"lat": 35.0, "lon": 126.0, "elev_m": 0.0,
                       "temperature_f": MODULE.PR103.LSO_BADFLAG_F,
                       "temperature_expected_accuracy_f": 1.0}
        MODULE.validate_observation_values([observation])

    def test_operator_difference_requires_common_rows_and_reports_nonzero(self):
        row = {"station_id": "s1", "wmo_id": "w1", "provider": "TST",
               "time_hhmm": 1400, "model_t2_c": 10.0, "observation_c": 10.0,
               "signed_model_minus_observation_c": 0.0, "lat": 35.0, "lon": 126.0,
               "elev_m": 0.0, "temperature_expected_accuracy_f": 1.0}
        result = MODULE.paired_operator_difference(
            [{**row, "model_t2_c": 11.0, "signed_model_minus_observation_c": 1.0}],
            [row], "H(XN) - H(XA)")
        self.assertEqual(result["paired_station_count"], 1)
        self.assertTrue(result["nonzero_signal"])
        self.assertEqual(result["max_abs_delta_c"], 1.0)
        with self.assertRaisesRegex(ValueError, "different station coverage"):
            MODULE.paired_operator_difference([row], [], "H(XN) - H(XA)")

    def test_operator_difference_decomposes_paired_score_changes_exactly(self):
        def row(station, prediction, error, observation=None):
            observation = prediction - error if observation is None else observation
            return {
                "station_id": station, "wmo_id": f"w-{station}", "provider": "TST",
                "time_hhmm": 1400, "model_t2_c": prediction, "observation_c": observation,
                "signed_model_minus_observation_c": error,
                "lat": 35.0, "lon": 126.0, "elev_m": 0.0,
                "temperature_expected_accuracy_f": 1.0,
            }

        y_rows = [row("s1", 10.0, 1.0), row("s2", 20.0, -2.0)]
        x_rows = [row("s1", 13.0, 4.0), row("s2", 19.0, -3.0)]
        result = MODULE.paired_operator_difference(x_rows, y_rows, "H(X) - H(Y)")
        scores = result["paired_station_score_differences"]

        self.assertEqual(scores["prediction_delta_c"]["signed_total"], 2.0)
        self.assertEqual(scores["prediction_delta_c"]["absolute_total"], 4.0)
        self.assertEqual(scores["squared_error_delta_c2"]["signed_total"], 20.0)
        self.assertEqual(scores["squared_error_delta_c2"]["absolute_total"], 20.0)
        self.assertEqual(scores["absolute_error_delta_c"]["signed_total"], 4.0)
        self.assertEqual(scores["absolute_error_delta_c"]["absolute_total"], 4.0)
        self.assertEqual(scores["squared_error_delta_c2"]["largest_abs_contribution"],
                         {"station_key": ["s1", "w-s1", "TST", 1400], "value": 15.0})
        self.assertEqual(scores["squared_error_delta_c2"]["top_5_cumulative_signed_contribution"], 20.0)
        self.assertEqual(scores["squared_error_delta_c2"]["top_5_cumulative_absolute_contribution"], 20.0)
        self.assertEqual(scores["mean_mse_delta_c2"], 10.0)
        self.assertEqual(scores["mean_mae_delta_c"], 2.0)
        self.assertEqual(result["paired_station_score_rows"][0]["squared_error_delta_c2"], 15.0)
        self.assertEqual(result["paired_station_score_rows"][0]["direct_squared_error_delta_c2"], 15.0)
        self.assertEqual(scores["contribution_scope"], "all paired matched station records; no additional exclusions")

    def test_operator_difference_emits_ordered_station_rows_and_cancellation(self):
        def make_row(station, error, delta):
            # Binary fractions make every expected value exactly representable.
            error, delta = Fraction(error), Fraction(delta)
            observation = Fraction(0)
            f_y, f_x = observation + error, observation + error + delta
            return {
                "station_id": station, "wmo_id": station, "provider": "TST", "time_hhmm": 1400,
                "lat": 35.0, "lon": 126.0, "elev_m": 0.0,
                "temperature_expected_accuracy_f": 1.0,
                "observation_c": float(observation), "model_t2_c": float(f_x),
                "signed_model_minus_observation_c": float(f_x - observation),
            }, {
                "station_id": station, "wmo_id": station, "provider": "TST", "time_hhmm": 1400,
                "lat": 35.0, "lon": 126.0, "elev_m": 0.0,
                "temperature_expected_accuracy_f": 1.0,
                "observation_c": float(observation), "model_t2_c": float(f_y),
                "signed_model_minus_observation_c": float(f_y - observation),
            }, error, delta

        cases = [make_row("s1", Fraction(1, 4), Fraction(1, 2)),
                 make_row("s2", Fraction(1, 4), Fraction(-1, 2)),
                 make_row("s3", Fraction(32), Fraction(1, 4)),
                 make_row("s4", Fraction(0), Fraction(-1, 4))]
        x_rows = [item[0] for item in cases]
        y_rows = [item[1] for item in cases]
        result = MODULE.paired_operator_difference(x_rows, list(reversed(y_rows)), "H(X) - H(Y)")
        station_rows = result["paired_station_score_rows"]
        expected_prediction = [float(case[3]) for case in cases]
        expected_squared = [float(2 * case[2] * case[3] + case[3] * case[3]) for case in cases]
        self.assertEqual([row["station_key"][0] for row in station_rows], ["s1", "s2", "s3", "s4"])
        self.assertEqual([row["prediction_delta_c"] for row in station_rows], expected_prediction)
        self.assertEqual([row["squared_error_delta_c2"] for row in station_rows], expected_squared)
        self.assertEqual(sum(expected_prediction), 0.0)
        self.assertEqual(sum(abs(value) for value in expected_prediction), 1.5)
        self.assertEqual(station_rows[2]["cross_term_c2"], 16.0)
        self.assertEqual(station_rows[2]["squared_error_delta_c2"], expected_squared[2])
        self.assertEqual(station_rows[2]["direct_squared_error_delta_c2"], expected_squared[2])
        scores = result["paired_station_score_differences"]
        self.assertEqual(scores["prediction_delta_c"]["signed_total"], 0.0)
        self.assertEqual(scores["prediction_delta_c"]["absolute_total"], 1.5)
        self.assertEqual(scores["squared_error_delta_c2"]["mean_signed_delta"],
                         float(sum(Fraction(value) for value in expected_squared) / 4))
        self.assertEqual(scores["mean_mse_delta_c2"],
                         float(sum(2 * case[2] * case[3] + case[3] * case[3] for case in cases) / 4))

    def test_operator_difference_rejects_shared_observation_mismatch(self):
        row = {"station_id": "s1", "wmo_id": "w1", "provider": "TST", "time_hhmm": 1400,
               "observation_c": 0.0, "model_t2_c": 1.0, "signed_model_minus_observation_c": 1.0,
               "lat": 35.0, "lon": 126.0, "elev_m": 0.0,
               "temperature_expected_accuracy_f": 1.0}
        with self.assertRaisesRegex(ValueError, "different shared station observation metadata"):
            MODULE.paired_operator_difference([row], [{**row, "observation_c": 0.25,
                                                         "signed_model_minus_observation_c": 0.75}], "pair")

    def test_operator_difference_rejects_empty_common_support(self):
        with self.assertRaisesRegex(ValueError, "no matched station coverage"):
            MODULE.paired_operator_difference([], [], "H(XN) - H(XA)")

    def test_output_exclusive_create_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as tempdir:
            output = Path(tempdir) / "report.json"
            output.write_text("keep this report\n", encoding="utf-8")
            argv = ["pr104_validtime_observation.py", "--valid-time", "2026-08-16T14:00:00Z",
                    "--observation", str(Path(tempdir) / "obs.lso"),
                    "--history", "H=h.nc", "--history", "A=a.nc", "--history", "N=n.nc",
                    "--output", str(output)]
            with patch("sys.argv", argv), \
                    patch.object(MODULE.PR103, "read_lso", return_value=([], {})), \
                    patch.object(MODULE, "load_histories", return_value={}), \
                    patch.object(MODULE, "sha256", return_value="0" * 64):
                with self.assertRaises(FileExistsError):
                    MODULE.main()
            self.assertEqual(output.read_text(encoding="utf-8"), "keep this report\n")

    def test_output_rejects_nonfinite_json_before_creating_file(self):
        with tempfile.TemporaryDirectory() as tempdir:
            output = Path(tempdir) / "report.json"
            argv = ["pr104_validtime_observation.py", "--valid-time", "2026-08-16T14:00:00Z",
                    "--observation", str(Path(tempdir) / "obs.lso"),
                    "--history", "H=h.nc", "--history", "A=a.nc", "--history", "N=n.nc",
                    "--output", str(output)]
            with patch("sys.argv", argv), \
                    patch.object(MODULE.PR103, "read_lso", return_value=([], {})), \
                    patch.object(MODULE, "load_histories", return_value={"bad_number": float("nan")}), \
                    patch.object(MODULE, "sha256", return_value="0" * 64):
                with self.assertRaises(ValueError):
                    MODULE.main()
            self.assertFalse(output.exists())

    def test_comparison_filters_to_requested_report_hour(self):
        observation = {"station_id": "s1", "wmo_id": "w1", "provider": "TST",
                       "lat": 1.0, "lon": 1.0, "elev_m": 0.0, "time_hhmm": 1400,
                       "temperature_f": 32.0, "temperature_expected_accuracy_f": 1.0}
        projection = dict(lat1=0.0, lon1=0.0, stdlon=0.0,
                          truelat1=30.0, truelat2=60.0, dx=5000.0, dy=5000.0)
        with patch.object(MODULE.PR103, "lc_grid_ij", return_value=(4.5, 4.5)):
            rows, metrics = MODULE.PR103.compare([observation], np.full((8, 8), 273.15), projection, 1400)
            no_rows, no_metrics = MODULE.PR103.compare([observation], np.full((8, 8), 273.15), projection, 1300)
        self.assertEqual(len(rows), 1)
        self.assertEqual(metrics["matched_count"], 1)
        self.assertEqual(no_rows, [])
        self.assertEqual(no_metrics["excluded_counts_by_reason"], {"non_1300_report_time": 1})


if __name__ == "__main__":
    unittest.main()
