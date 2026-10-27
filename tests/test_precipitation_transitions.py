"""Tests for paired-point precipitation transition diagnostics."""
from __future__ import annotations

import csv
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from precipitation_transitions import contingency, load_hour, run, summarize_hour  # noqa: E402


def sample_fields() -> dict[str, np.ndarray]:
    return {
        "reference": np.array([0.0, 5.0, 0.0, 8.0]),
        "OFF": np.array([0.0, 5.0, 1.0, 8.0]),
        "HYDRO": np.array([0.0, 0.0, 1.0, 8.0]),
        "LIQUID": np.array([0.0, 5.0, 0.0, 8.0]),
        "latitude": np.array([35.0, 35.0, 36.0, 36.0]),
        "longitude": np.array([128.0, 129.0, 128.0, 129.0]),
        "flat_index_yx": np.arange(4, dtype=np.int32),
    }


def write_six_hours(directory: Path, *, all_dry: bool = False, arms_match_off: bool = False) -> None:
    directory.mkdir()
    for hour in range(13, 19):
        fields = sample_fields()
        if all_dry:
            for arm in ("reference", "OFF", "HYDRO", "LIQUID"):
                fields[arm] = np.zeros_like(fields[arm])
        if arms_match_off:
            fields["HYDRO"] = fields["OFF"].copy()
            fields["LIQUID"] = fields["OFF"].copy()
        np.savez(directory / f"hour_{hour}_arrays.npz", **fields)


class PrecipitationTransitionTests(unittest.TestCase):
    def test_contingency_uses_inclusive_threshold_and_common_points(self) -> None:
        counts = contingency(np.array([0.1, 0.0, 2.5, 8.0]),
                             np.array([0.1, 1.0, 0.0, 8.0]), 0.1)
        self.assertEqual(counts, {"hits": 2, "misses": 1, "false_alarms": 1, "correct_dry": 0})
        self.assertEqual(sum(counts.values()), 4)

    def test_pair_transition_gains_and_losses_reconcile(self) -> None:
        fields = {
            "reference": np.array([5.0, 5.0, 0.0, 0.0]),
            "OFF": np.array([5.0, 0.0, 5.0, 0.0]),
            "HYDRO": np.array([0.0, 5.0, 0.0, 5.0]),
            "LIQUID": np.array([5.0, 0.0, 0.0, 0.0]),
        }
        threshold_rows, continuous_rows = summarize_hour(13, fields)
        transition = next(row for row in threshold_rows if row["threshold_mm"] == 5.0 and row["arm"] == "OFF->HYDRO")
        self.assertEqual((transition["hit_gains"], transition["hit_losses"]), (1, 1))
        self.assertEqual((transition["false_alarm_gains"], transition["false_alarm_losses"]), (1, 1))
        off = next(row for row in continuous_rows if row["arm"] == "OFF")
        self.assertEqual(off["points"], 4)
        self.assertEqual(off["rain_points"], 2)
        self.assertEqual(off["rain_intensity_q50_mm"], 5.0)

    def test_load_hour_rejects_nonfinite_and_negative_precipitation(self) -> None:
        fields = sample_fields()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "hour.npz"
            fields["HYDRO"][0] = -0.1
            np.savez(path, **fields)
            with self.assertRaisesRegex(ValueError, "nonnegative"):
                load_hour(path)
            fields["HYDRO"][0] = 0.0
            fields["reference"][0] = np.nan
            np.savez(path, **fields)
            with self.assertRaisesRegex(ValueError, "non-finite"):
                load_hour(path)

    def test_load_hour_rejects_mismatched_vector_shapes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "hour.npz"
            fields = sample_fields()
            fields["LIQUID"] = np.zeros(3)
            np.savez(path, **fields)
            with self.assertRaisesRegex(ValueError, "equal length"):
                load_hour(path)

    def test_load_hour_rejects_duplicate_or_negative_indices(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "hour.npz"
            fields = sample_fields()
            fields["flat_index_yx"][1] = fields["flat_index_yx"][0]
            np.savez(path, **fields)
            with self.assertRaisesRegex(ValueError, "unique integers"):
                load_hour(path)
            fields["flat_index_yx"] = np.array([-1, 1, 2, 3], dtype=np.int32)
            np.savez(path, **fields)
            with self.assertRaisesRegex(ValueError, "nonnegative"):
                load_hour(path)

    def test_all_dry_conditional_intensity_statistics_are_null(self) -> None:
        fields = {arm: np.zeros(4) for arm in ("OFF", "HYDRO", "LIQUID")}
        fields["reference"] = np.zeros(4)
        _, rows = summarize_hour(13, fields)
        for row in rows:
            self.assertEqual(row["rain_fraction_ge_0_1"], 0.0)
            self.assertIsNone(row["rain_conditional_mean_mm"])
            self.assertIsNone(row["rain_intensity_q50_mm"])
            self.assertEqual(row["rain_max_mm"], 0.0)

    def test_run_rejects_cross_hour_index_or_coordinate_changes_before_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "hours"
            write_six_hours(source)
            with np.load(source / "hour_14_arrays.npz") as data:
                fields = {key: data[key] for key in data.files}
            output = root / "output"
            for name in ("longitude", "flat_index_yx"):
                changed = dict(fields)
                changed[name] = fields[name].copy()
                changed[name][0] += 10 if name == "flat_index_yx" else 1
                np.savez(source / "hour_14_arrays.npz", **changed)
                with self.assertRaisesRegex(ValueError, "identical paired indices and coordinates"):
                    run(source, output)
                self.assertFalse(output.exists())

    def test_run_uses_fresh_output_directory_and_preserves_existing_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "hours"
            write_six_hours(source)
            output = root / "output"
            with patch("precipitation_transitions.create_figures"):
                result = run(source, output)
                self.assertEqual(result["paired_points_per_hour"], 4)
                self.assertIn("common 4-point paired sample", result["scope"])
                self.assertEqual(result["hour_13_off_hit_lost_union_ge_5mm"], 1)
            sentinel = output / "keep.txt"
            sentinel.write_text("preserve", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must not already exist"):
                run(source, output)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve")

    def test_real_plotting_run_off_candidate_has_rain_but_no_lost_hits(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, output = root / "hours", root / "output"
            write_six_hours(source, arms_match_off=True)
            result = run(source, output)
            self.assertEqual(result["hour_13_off_hit_lost_union_ge_5mm"], 0)
            self.assertEqual(result["hour_13_hydro_lost_hits_ge_5mm"], 0)
            self.assertEqual(result["hour_13_liquid_lost_hits_ge_5mm"], 0)
            self.assertGreater(result["hour_13_off_hits_ge_5mm"], 0)
            self.assertGreater(result["hour_13_hydro_hits_ge_5mm"], 0)
            self.assertGreater(result["hour_13_liquid_hits_ge_5mm"], 0)
            with (output / "hour_13_ge5mm_off_hit_lost_union.csv").open(
                newline="", encoding="utf-8"
            ) as stream:
                self.assertEqual(next(csv.reader(stream))[0], "focus_rank")
                self.assertEqual(list(csv.reader(stream)), [])
            for name in (
                "threshold_counts_and_transitions.csv", "continuous_metrics.csv",
                "hour_13_ge5mm_off_hit_lost_union.csv", "summary.json",
                "threshold_5mm_hit_transitions.png", "rain_point_distributions.png",
                "hour_13_ge5mm_lost_hit_focus.png", "hourly_threshold_5mm_transitions.png",
            ):
                self.assertTrue((output / name).is_file(), name)
                self.assertGreater((output / name).stat().st_size, 0, name)

    def test_real_plotting_run_all_dry_keeps_empty_loss_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, output = root / "hours", root / "output"
            write_six_hours(source, all_dry=True)
            result = run(source, output)
            self.assertEqual(result["hour_13_off_hit_lost_union_ge_5mm"], 0)
            self.assertEqual(result["hour_13_hydro_lost_hits_ge_5mm"], 0)
            self.assertEqual(result["hour_13_liquid_lost_hits_ge_5mm"], 0)
            focus_path = output / "hour_13_ge5mm_off_hit_lost_union.csv"
            with focus_path.open(newline="", encoding="utf-8") as stream:
                self.assertEqual(next(csv.reader(stream)), [
                    "focus_rank", "flat_index_yx", "latitude", "longitude", "reference_mm", "OFF_mm",
                    "HYDRO_mm", "LIQUID_mm", "OFF_hit_ge_5", "HYDRO_hit_ge_5", "LIQUID_hit_ge_5",
                    "HYDRO_lost_hit", "LIQUID_lost_hit",
                ])
                self.assertEqual(list(csv.reader(stream)), [])
            for name in (
                "threshold_counts_and_transitions.csv", "continuous_metrics.csv",
                "summary.json", "threshold_5mm_hit_transitions.png", "rain_point_distributions.png",
                "hour_13_ge5mm_lost_hit_focus.png", "hourly_threshold_5mm_transitions.png",
            ):
                self.assertTrue((output / name).is_file(), name)
                self.assertGreater((output / name).stat().st_size, 0, name)

    def test_run_removes_new_output_if_figure_creation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "hours"
            write_six_hours(source)
            output = root / "output"
            with patch("precipitation_transitions.create_figures", side_effect=RuntimeError("plot failed")):
                with self.assertRaisesRegex(RuntimeError, "plot failed"):
                    run(source, output)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
