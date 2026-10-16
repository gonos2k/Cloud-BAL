"""Small controls for interpretation of Eulerian analysis-response norms."""
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

import numpy as np
import netCDF4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from pr86_compare_response import response_norm, history_coverage, history_index, compare_first_call


class ResponseNormTest(unittest.TestCase):
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
