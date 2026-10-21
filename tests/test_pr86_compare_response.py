"""Small controls for interpretation of Eulerian analysis-response norms."""
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from contextlib import contextmanager

import numpy as np
import netCDF4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pr86_compare_response as compare_response
from pr86_compare_response import response_norm, history_coverage, history_index, compare_first_call
from pr87_native_history import _finite


class ResponseNormTest(unittest.TestCase):
    def test_load_history_validates_pressure_and_geopotential_operands_before_composition(self):
        raw_names = ("QVAPOR", "QCLOUD", "QICE", "QRAIN", "QSNOW", "QGRAUP",
                     "QNCLOUD", "QNICE", "QNRAIN", "QIB", "T", "P", "PB", "PH", "PHB",
                     "U", "V", "W")
        raw_shapes = {name: (40 if name in ("PH", "PHB", "W") else 39,
                             283 if name == "V" else 282,
                             235 if name == "U" else 234)
                      for name in raw_names}
        raw_shapes["QVAPOR"] = (39, 282, 234)

        class BroadcastVariable:
            def __init__(self, variable, target_shape):
                self.variable = variable
                self.shape = (1, *target_shape)

            def __getitem__(self, key):
                scalar = self.variable[key][0, 1, 1]
                return np.broadcast_to(scalar, self.shape[1:])

            def __getattr__(self, name):
                return getattr(self.variable, name)

        class FrozenDomainView:
            def __init__(self, dataset):
                self.dataset = dataset
                self.variables = {name: (BroadcastVariable(dataset[name], raw_shapes[name])
                                         if name in raw_shapes else dataset[name])
                                  for name in dataset.variables}

            def __enter__(self):
                self.dataset.__enter__()
                return self

            def __exit__(self, *args):
                return self.dataset.__exit__(*args)

            def set_auto_mask(self, enabled):
                self.dataset.set_auto_mask(enabled)

            def __getitem__(self, name):
                return self.variables[name]

        def make_history(path, sentinel_field=None, sentinel_attribute="missing_value", bad_value=-9999.0):
            with netCDF4.Dataset(path, "w") as ds:
                ds.createDimension("Time", 1)
                ds.createDimension("DateStrLen", 19)
                ds.createDimension("k", 1)
                ds.createDimension("j", 3)
                ds.createDimension("i", 3)
                times = ds.createVariable("Times", "S1", ("Time", "DateStrLen"))
                times[0, :] = np.asarray(list("2026-08-16_13:00:00"), dtype="S1")
                for name in raw_names:
                    kwargs = {"fill_value": bad_value} if name == sentinel_field and sentinel_attribute == "_FillValue" else {}
                    variable = ds.createVariable(name, "f8", ("Time", "k", "j", "i"), **kwargs)
                    variable[:] = 1.0
                    if name == sentinel_field:
                        if sentinel_attribute == "missing_value":
                            variable.missing_value = bad_value
                        variable[0, 0, 1, 1] = bad_value

        def load(path):
            original_dataset = netCDF4.Dataset

            @contextmanager
            def open_view(*args, **kwargs):
                with original_dataset(*args, **kwargs) as dataset:
                    view = FrozenDomainView(dataset)
                    yield view

            with patch.object(compare_response.netCDF4, "Dataset", side_effect=open_view):
                return compare_response.load_history(path)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            valid_path = root / "valid.nc"
            make_history(valid_path)
            _, valid, _ = load(valid_path)
            self.assertEqual(valid["pressure"][0, 0, 0], 2.0)
            self.assertEqual(valid["geopotential"][0, 0, 0], 2.0)
            for name in ("P", "PB", "PH", "PHB"):
                for attribute in ("_FillValue", "missing_value"):
                    path = root / f"{name}_{attribute}.nc"
                    make_history(path, name, attribute)
                    with self.assertRaisesRegex(ValueError, f"{name} contains declared {attribute} sentinel"):
                        load(path)

            for arm in ("OFF", "COUPLED"):
                path = root / f"{arm}_same_sentinel.nc"
                make_history(path, "PB", "missing_value")
                with self.assertRaisesRegex(ValueError, "PB contains declared missing_value sentinel"):
                    load(path)

    def test_declared_sentinels_and_nonfinite_values_fail_before_state_composition(self):
        state_fields = ("U", "V", "W", "P", "PB", "PH", "PHB")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.nc"
            with netCDF4.Dataset(path, "w") as ds:
                ds.createDimension("Time", 1)
                ds.createDimension("k", 3)
                ds.createDimension("j", 4)
                ds.createDimension("i", 4)
                for name in state_fields:
                    variable = ds.createVariable(name, "f8", ("Time", "k", "j", "i"))
                    variable[:] = 1.0
                    variable.missing_value = -9999.0
            for name in state_fields:
                with netCDF4.Dataset(path, "a") as ds:
                    ds[name][0, 0, 1, 1] = -9999.0
                with netCDF4.Dataset(path) as ds, self.assertRaisesRegex(
                        ValueError, f"{name} contains declared missing_value sentinel"):
                    _finite(ds, name, 0)
                with netCDF4.Dataset(path, "a") as ds:
                    ds[name][:] = 1.0

            for bad in (np.nan, np.inf):
                with netCDF4.Dataset(path, "a") as ds:
                    ds["P"][0, 0, 1, 1] = bad
                with netCDF4.Dataset(path) as ds, self.assertRaisesRegex(
                        ValueError, "P contains nonfinite"):
                    _finite(ds, "P", 0)

    def test_call_temperature_is_reconstructed_and_uncaptured_winds_stay_missing(self):
        def call(arm, theta, exner):
            fields = {name: np.array([0.]) for name in ("Q", "QC", "QI", "QR", "QS", "QG", "NC", "NI", "NR", "BG", "P")}
            fields.update(TH=np.array([theta]), PII=np.array([exner]))
            return {"arm": arm, "identities": {}, "pre": {"fields": fields}, "post": {"fields": fields}}
        off, coupled = call("OFF", 300., 0.9), call("COUPLED", 302., 0.9)
        with patch("pr86_compare_response.load_call_measure", side_effect=[off, coupled]):
            result = compare_first_call(Path("off"), Path("coupled"))
        self.assertAlmostEqual(result["records"][1]["fields"]["T"]["mean"], 1.8)
        self.assertNotIn("U", result["records"][1]["fields"])
        with patch("pr86_compare_response.load_call_measure", side_effect=[coupled, off]):
            with self.assertRaises(ValueError):
                compare_first_call(Path("off"), Path("coupled"))

    def test_multiple_history_frames_are_indexed_by_stored_times(self):
        times = ("2026-08-16_13:00:00", "2026-08-16_13:01:00")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ("wrfout_d01_" + times[0])
            with netCDF4.Dataset(path, "w") as ds:
                ds.createDimension("Time", 2)
                ds.createDimension("DateStrLen", 19)
                variable = ds.createVariable("Times", "S1", ("Time", "DateStrLen"))
                variable[:] = np.asarray([list(t) for t in times], dtype="S1")
            index, identities = history_index(Path(directory))
            self.assertEqual(set(index), set(times))
            self.assertEqual(index[times[1]], (path, 1))
            self.assertEqual(identities[str(path)]["timestamps"], list(times))

    def test_final_history_cannot_hide_missing_intermediate_outputs(self):
        initial = {"2026-08-16_13:00:00", "2026-08-16_13:10:00"}
        coverage = history_coverage(initial, initial)
        self.assertFalse(coverage["complete"])
        self.assertEqual(len(coverage["missing_timestamps"]["OFF"]), 9)
        expected = set(coverage["expected_timestamps"])
        self.assertTrue(history_coverage(expected, expected)["complete"])
        self.assertFalse(history_coverage(expected, initial)["complete"])

    def test_identical_states_have_zero_analysis_response(self):
        a = np.array([1., 3., 7.])
        self.assertEqual(response_norm(a, a)["rms"], 0.)

    def test_signed_changes_are_not_hidden_by_mean_cancellation(self):
        r = response_norm(np.zeros(2), np.array([-3., 3.]))
        self.assertEqual(r["mean"], 0.)
        self.assertEqual(r["rms"], 3.)

    def test_mismatched_support_and_nonfinite_fail(self):
        for a, b in ((np.ones(1), np.ones(2)), (np.ones(1), np.array([np.nan]))):
            with self.assertRaises(ValueError):
                response_norm(a, b)


if __name__ == "__main__":
    unittest.main()
