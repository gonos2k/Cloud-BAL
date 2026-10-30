"""Renderer checks for same-point precipitation differences and shared scales."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "plot_snow_lower", ROOT / "tools/plot_snow_lower.py")
plotter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(plotter)


def _paired_hour(cases, hour):
    index = np.arange(plotter.POINTS, dtype=np.int64)
    original = (index % 11).astype(np.float64) + hour / 100
    data = {
        "reference": np.full(plotter.POINTS, 1000.0),
        "flat_index_yx": index,
        "latitude": np.full(plotter.POINTS, 35.0),
        "longitude": np.full(plotter.POINTS, 127.0),
        "ORIGINAL": original,
    }
    for case_index, case in enumerate(case for case in cases if case != "ORIGINAL"):
        data[case] = original + (case_index - 12) / 10 + hour / 1000
    return data


def test_difference_npz_matches_same_point_precipitation_and_not_reference_error(tmp_path):
    cases = plotter.ALL_CASES
    hours = {hour: _paired_hour(cases, hour) for hour in plotter.HOURS}
    for hour in plotter.HOURS:
        source = hours[hour]
        np.savez_compressed(
            tmp_path / f"hour_{hour}_difference_vs_original.npz",
            reference=source["reference"], flat_index_yx=source["flat_index_yx"],
            latitude=source["latitude"], longitude=source["longitude"],
            **{case: source[case].astype(np.float64) - source["ORIGINAL"]
               for case in cases})

    differences, hashes, sizes = plotter.load_precipitation_differences(tmp_path, cases, hours)
    case, hour, point = "CONTROL_SNOW_060", 15, 29
    assert differences[hour][case][point] == pytest.approx(
        hours[hour][case][point] - hours[hour]["ORIGINAL"][point])
    assert differences[hour][case][point] != pytest.approx(
        hours[hour][case][point] - hours[hour]["reference"][point])
    assert np.count_nonzero(differences[hour]["ORIGINAL"]) == 0
    assert len(hashes) == len(plotter.HOURS)
    assert sizes == {name: (tmp_path / name).stat().st_size for name in hashes}

    wrong = np.load(tmp_path / "hour_13_difference_vs_original.npz")
    changed = {name: wrong[name] for name in wrong.files}
    wrong.close()
    changed[case] = changed[case].copy()
    changed[case][point] += 0.01
    np.savez_compressed(tmp_path / "hour_13_difference_vs_original.npz", **changed)
    with pytest.raises(ValueError, match="same-point"):
        plotter.load_precipitation_differences(tmp_path, cases, hours)


def test_difference_color_scale_covers_every_case_and_lead_symmetrically():
    differences = {
        hour: {case: np.zeros(4, dtype=np.float64) for case in plotter.ALL_CASES}
        for hour in plotter.HOURS
    }
    differences[14]["CONTROL_SNOW_060"] = np.array([0.1, 0.2, -0.4, 0.0])
    differences[18]["IMPROVED_SNOW_090"] = np.array([0.3, -1.21, 0.0, -0.2])

    observed_min, observed_max, limits = plotter.precipitation_difference_color_scale(
        differences, plotter.ALL_CASES)

    assert (observed_min, observed_max) == (-1.21, 0.3)
    assert limits == [-1.3, 1.3]
    assert limits[0] <= observed_min <= observed_max <= limits[1]
