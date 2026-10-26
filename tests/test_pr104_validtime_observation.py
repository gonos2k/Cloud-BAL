import importlib.util
from datetime import datetime, timezone
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
            for name, value in (("TRUELAT1", 30.0), ("TRUELAT2", 60.0),
                                ("STAND_LON", 126.0), ("DX", 5000.0), ("DY", 5000.0)):
                setattr(nc, name, value)
            for name, value in (("XLAT", 35.0), ("XLONG", 126.0), ("T2", 280.0)):
                var = nc.createVariable(name, "f4", ("Time", "south_north", "west_east"), fill_value=-9999.0)
                var.units = "K" if name == "T2" else "degrees_north"
                var[:] = np.full((len(times), 5, 5), value, dtype=np.float32)
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
               "time_hhmm": 1400, "model_t2_c": 10.0}
        result = MODULE.paired_operator_difference([{**row, "model_t2_c": 11.0}], [row], "H(XN) - H(XA)")
        self.assertEqual(result["paired_station_count"], 1)
        self.assertTrue(result["nonzero_signal"])
        self.assertEqual(result["max_abs_delta_c"], 1.0)
        with self.assertRaisesRegex(ValueError, "different station coverage"):
            MODULE.paired_operator_difference([row], [], "H(XN) - H(XA)")

    def test_operator_difference_rejects_empty_common_support(self):
        with self.assertRaisesRegex(ValueError, "no matched station coverage"):
            MODULE.paired_operator_difference([], [], "H(XN) - H(XA)")

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
