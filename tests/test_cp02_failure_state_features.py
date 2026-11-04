import importlib.util
from pathlib import Path

import numpy as np
import pytest

SPEC = importlib.util.spec_from_file_location('failure_state', Path(__file__).resolve().parents[1] / 'tools/cp02_failure_state_features.py')
state = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(state)


def test_temperature_uses_dry_history_theta_and_pressure():
    theta = np.array([0.0, 4.0])
    pressure = np.array([100000.0, 80000.0])
    actual = state.temperature_from_history(theta, pressure)
    np.testing.assert_allclose(actual, (theta + 300) * (pressure / 100000) ** (287 / 1004.5))
    with pytest.raises(ValueError, match='pressure'):
        state.temperature_from_history(theta, np.array([100000., 0.]))


def test_liquid_and_ice_saturation_at_and_below_triple_point():
    p = np.array([100000., 80000.])
    t = np.array([273.16, 260.])
    qsat = (287 / 461.6) * 610.78 / (100000 - 610.78)
    qv = np.array([qsat, 0.002])
    liquid = state.humidity(qv, t, p)
    phase = state.humidity(qv, t, p, ice_or_water=True)
    assert liquid[0] == pytest.approx(1.0)
    assert phase[0] == pytest.approx(liquid[0])
    assert phase[1] > liquid[1]  # ice saturation pressure is lower below freezing
    assert state.humidity(np.array([-0.1]), np.array([273.16]), np.array([100000.]))[0] == state.QMIN


def test_native_humidity_precedes_bilinear_interpolation():
    q = np.array([[[0.002, 0.010, 0.004, 0.006]]])
    t = np.array([[[260., 290., 265., 280.]]])
    p = np.full_like(q, 90000.)
    w = np.array([[.1, .2, .3, .4]])
    corner_rh = state.humidity(q, t, p)
    actual = state.weighted(corner_rh, w)[0]
    wrong = state.humidity(state.weighted(q, w)[0], state.weighted(t, w)[0], state.weighted(p, w)[0])
    assert abs(float(actual[0, 0] - wrong[0, 0])) > 0.001


def test_diameter_missing_never_becomes_physical_zero():
    q = np.array([[[1e-3, 1e-3, 0., 1e-3]]])
    n = np.array([[[1e4, 0., 1e4, 1e4]]])
    dm, valid = state.diameter(q, n)
    expected = 5000 / np.cbrt(4000 * np.pi * 1e4 / 1e-3)
    assert dm[0, 0, 0] == pytest.approx(expected)
    assert np.isnan(dm[0, 0, 1:3]).all()
    result, coverage, mask = state.weighted(dm, np.array([[.25, .25, .25, .25]]), valid)
    assert np.isnan(result[0, 0]) and coverage[0, 0] == .5 and not mask[0, 0]
    result, coverage, mask = state.weighted(dm, np.array([[.5, 0., 0., .5]]), valid)
    assert result[0, 0] == pytest.approx(expected) and coverage[0, 0] == 1 and mask[0, 0]


def test_layer_means_use_each_corner_height_before_weighting():
    values = np.array([[[1., 5., 7., 9.], [3., 10., 11., 13.], [8., 15., 17., 19.]]])
    height = np.array([[[100., 100., 100., 100.], [900., 1100., 900., 900.], [1500., 1900., 2100., 2200.]]])
    means, count = state.layer_mean(values, height, 0, 1000)
    assert count.tolist() == [[2, 1, 2, 2]]
    result, coverage, valid = state.weighted(means, np.array([[.25, .25, .25, .25]]), count[:, None, :] > 0)
    assert result[0, 0] == pytest.approx((2 + 5 + 9 + 11) / 4)
    assert coverage[0, 0] == 1 and valid[0, 0]
    means, count = state.layer_mean(values, height, 3000, 4000)
    result, coverage, valid = state.weighted(means, np.full((1, 4), .25), count[:, None, :] > 0)
    assert np.isnan(result[0, 0]) and coverage[0, 0] == 0 and not valid[0, 0]


def test_mapping_crop_offsets_and_duplicate_keys(monkeypatch):
    monkeypatch.setattr(state, 'NPOINTS', 1)
    mapping = {'valid': np.zeros((253,149), dtype=bool), 'j0': np.zeros((253,149), dtype=int),
               'i0': np.zeros((253,149), dtype=int), 'u': np.zeros((253,149)), 'v': np.zeros((253,149))}
    y, x = 73, 65
    mapping['valid'][y, x] = True
    mapping['j0'][y, x], mapping['i0'][y, x] = 73, 65
    mapping['u'][y, x], mapping['v'][y, x] = .4, .6
    j, i, w = state.corners(mapping, np.array([y * 149 + x]))
    assert j.tolist() == [[78, 78, 79, 79]] and i.tolist() == [[139, 140, 139, 140]]
    np.testing.assert_allclose(w, [[.24, .16, .36, .24]])
    with pytest.raises(ValueError, match='valid mapping'):
        state.corners(mapping, np.array([0]))
