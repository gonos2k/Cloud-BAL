import importlib.util
from pathlib import Path

import numpy as np
import pytest

PATH = Path(__file__).resolve().parents[1] / 'tools/cp02_sedimentation_focus.py'
spec = importlib.util.spec_from_file_location('sed_focus', PATH)
focus = importlib.util.module_from_spec(spec)
spec.loader.exec_module(focus)


def test_bin_boundaries_include_30_returns_and_prior_cumulative():
    steps = np.arange(181, 361)
    qr = np.arange(180, dtype=float)
    # A pulse exactly at step 210 must belong only to the first interval.
    rain = np.zeros(180); rain[29:] = 7
    result = focus.bins(steps, qr, rain, -2)
    assert result[0] == (181, 210, 14.5, 9.0)
    assert result[1] == (211, 240, 44.5, 0.0)
    assert result[-1][:2] == (331, 360)
    assert sum(row[3] for row in result) == 9


def test_mismatched_steps_and_coordinates_rejected():
    with pytest.raises(ValueError):
        focus.bins(np.arange(180, 360), np.zeros(180), np.zeros(180), 0)
    a = {key: np.array([1]) for key in focus.COORDS}
    b = {key: val.copy() for key, val in a.items()}
    b['point_corner_weights'][0] = 2
    with pytest.raises(ValueError, match='point_corner_weights'):
        focus.require_matching(a, b)


def test_real_capture_point_matches_original_native_corners():
    path = focus.COMPACT / 'OLD/state_return_QR/lead_02/state_return_QR.npz'
    record, corners, weighted, i = focus.load(path, np.arange(181, 361), 'kg kg-1')
    assert np.allclose(weighted[:, 11], record['point_values'][:, 11, i], rtol=0, atol=1e-18)
    assert corners.shape == (180, 39, 4)
    with pytest.raises(ValueError, match='steps or units'):
        focus.load(path, np.arange(181, 361), 'mm')
