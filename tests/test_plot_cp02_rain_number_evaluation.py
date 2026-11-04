"""Rain-number figure scales and paired-map coordinate validation."""
import importlib.util
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("rain_number_renderer", ROOT / "tools/plot_cp02_rain_number_evaluation.py")
rain = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rain)


def _hourly_fixture():
    hourly = {}
    for index, hour in enumerate(rain.HOURS):
        base = np.full(3688, index + 1.0)
        hourly[hour] = {"reference": base, "ORIGINAL": base + index,
                        "IMPROVED_BG_FIXED": base + 2 * index,
                        "B1_RAIN_NUMBER_PRIOR": base + 3 * index}
    return hourly


def test_all_six_hours_use_one_absolute_and_symmetric_delta_scale():
    absolute, delta = rain.shared_map_scales(_hourly_fixture())
    assert absolute == (1.0, 21.0)
    assert delta == 10.0
    cmap, norm, bounds = rain.precipitation_norm(absolute)
    assert norm.vmin == absolute[0] and norm.vmax == absolute[1]
    assert bounds[0] == absolute[0] and bounds[-1] == absolute[1]
    for hour in rain.HOURS:
        assert rain.shared_map_scales(_hourly_fixture())[0] == absolute
        assert rain.shared_map_scales(_hourly_fixture())[1] == delta


def test_every_map_requires_actual_paired_point_coordinates(tmp_path):
    n = 3688
    path = tmp_path / "hour_13_arrays.npz"
    np.savez(path, reference=np.zeros(n), ORIGINAL=np.zeros(n), IMPROVED_BG_FIXED=np.zeros(n),
             B1_RAIN_NUMBER_PRIOR=np.zeros(n), latitude=np.arange(n, dtype=float),
             longitude=np.arange(n, dtype=float), flat_index_yx=np.arange(n))
    assert rain._npz_values(path)["latitude"].shape == (n,)
    with np.load(path) as archive:
        broken = {key: archive[key] for key in archive.files}
    broken["flat_index_yx"][-1] = broken["flat_index_yx"][-2]
    np.savez(path, **broken)
    with pytest.raises(ValueError, match="duplicate paired sample"):
        rain._npz_values(path)


def test_scale_range_requires_all_hourly_arrays():
    incomplete = _hourly_fixture()
    incomplete.pop(18)
    with pytest.raises(ValueError, match="13 through 18"):
        rain.shared_map_scales(incomplete)
