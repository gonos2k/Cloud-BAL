import importlib.util
import csv
from pathlib import Path

import numpy as np
import pytest

TOOL = Path(__file__).resolve().parents[1] / 'tools/cp02_b1_failure_state.py'
SPEC = importlib.util.spec_from_file_location('b1_failure_state', TOOL)
state = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(state)


def sample_raw():
    shape = (1, 2, 4)
    qv = np.array([[[0.001, 0.006, 0.002, 0.010],
                    [0.004, 0.002, 0.008, 0.001]]], dtype=np.float32)
    theta = np.array([[[5., 15., -4., 8.], [12., -2., 3., 20.]]], dtype=np.float32)
    temp = (theta.astype(np.float64) + 300.) * (90000. / 100000.) ** (287. / 1004.5)
    theta_m = ((theta.astype(np.float64) + 300.) *
               (1. + (461.6 / 287.) * qv.astype(np.float64)) - 300.)
    return {
        'QVAPOR': qv,
        'QRAIN': np.full(shape, 1e-3, dtype=np.float32),
        'QNRAIN': np.full(shape, 1e4, dtype=np.float32),
        'T': theta,
        'THM': theta_m.astype(np.float32),
        'P': np.full(shape, 9000., dtype=np.float32),
        'PB': np.full(shape, 81000., dtype=np.float32),
    }


def test_dry_history_theta_is_converted_to_temperature_and_checked_against_thm():
    weights = np.array([[.1, .2, .3, .4]])
    height = np.zeros((1, 2, 4), dtype=np.float64)
    _, weighted, _ = state.derive_diagnostics(sample_raw(), weights, height)
    assert weighted['dry_moist_theta_max_error_K'] < 6e-5
    expected_corner = state.FEATURES.temperature_from_history(
        sample_raw()['T'].astype(np.float64), np.full((1, 2, 4), 90000.))
    np.testing.assert_allclose(weighted['temperature_K'],
                               np.sum(expected_corner * weights[:, None, :], axis=-1))
    broken = sample_raw()
    broken['THM'] = broken['THM'] + 1.
    with pytest.raises(ValueError, match='theta consistency'):
        state.derive_diagnostics(broken, weights, height)


def test_nonlinear_humidity_is_derived_at_each_corner_before_weighting():
    raw = sample_raw()
    weights = np.array([[.1, .2, .3, .4]])
    height = np.zeros((1, 2, 4), dtype=np.float64)
    derived, weighted, _ = state.derive_diagnostics(raw, weights, height)
    wrong = state.FEATURES.humidity(
        state.FEATURES.weighted(raw['QVAPOR'].astype(np.float64), weights)[0],
        state.FEATURES.weighted(derived['corner_temperature_K'], weights)[0],
        state.FEATURES.weighted(derived['corner_pressure_Pa'], weights)[0])
    assert np.max(np.abs(weighted['rh_liquid'] - wrong)) > 1e-4


def test_dm_stays_undefined_when_any_positive_weight_corner_is_invalid():
    raw = sample_raw()
    raw['QNRAIN'][0, 1, 1] = 0.
    weights = np.array([[.1, .2, .3, .4]])
    height = np.zeros((1, 2, 4), dtype=np.float64)
    derived, weighted, valid_weight = state.derive_diagnostics(raw, weights, height)
    assert np.isnan(derived['corner_dm_mass_weighted_mm'][0, 1, 1])
    assert not derived['corner_dm_valid'][0, 1, 1]
    assert np.isnan(weighted['dm_mass_weighted_mm'][0, 1])
    assert weighted['dm_valid'][0, 1] == 0
    assert valid_weight['dm_mass_weighted_mm'][0, 1] < 1


def test_history_inventory_rejects_duplicate_or_missing_hour():
    good = [{'path': f'/history/wrfout_d01_2026-08-16_{h:02d}:00:00'}
            for h in range(12, 19)]
    assert tuple(state.checked_hours(good)) == tuple(range(12, 19))
    with pytest.raises(ValueError, match='duplicate'):
        state.checked_hours(good + [good[-1]])
    with pytest.raises(ValueError, match='exactly 12:00'):
        state.checked_hours(good[:-1])


def test_history_times_value_must_match_expected_snapshot():
    actual = np.frombuffer(b'2026-08-16_14:00:00', dtype='S1')
    assert state.decode_history_time(actual) == '2026-08-16_14:00:00'
    corrupted = actual.copy()
    corrupted[12] = b'5'
    assert state.decode_history_time(corrupted) != '2026-08-16_14:00:00'
    with pytest.raises(ValueError, match='19 character'):
        state.decode_history_time(actual[:-1])


def test_rainsh_requires_zero_cumulative_state_even_without_an_increment():
    state.validate_rainsh(np.zeros((2, 4)), None)
    with pytest.raises(ValueError, match='cumulative field'):
        state.validate_rainsh(np.full((2, 4), 0.5), None)
    with pytest.raises(ValueError, match='interval increment'):
        state.validate_rainsh(np.zeros((2, 4)), np.full((2, 4), 0.5))


def test_focus_point_must_exist_in_canonical_mapping(monkeypatch):
    monkeypatch.setattr(state, 'NPOINTS', 3)
    monkeypatch.setattr(state.FEATURES, 'NPOINTS', 3)
    valid = np.zeros((253, 149), dtype=bool)
    valid[0, :3] = True
    mapping = {'valid': valid, 'j0': np.zeros((253, 149), dtype=np.int64),
               'i0': np.zeros((253, 149), dtype=np.int64),
               'u': np.zeros((253, 149)), 'v': np.zeros((253, 149))}
    with pytest.raises(ValueError, match='absent from canonical score mapping'):
        state.subset_corners(mapping, np.array([0, 1, 2]), np.array([0, 7]))


def test_target_tables_keep_many_to_many_control_links(tmp_path):
    membership_path = tmp_path / 'focus_membership.csv'
    with membership_path.open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['flat_index_yx', 'point_index', 'latitude', 'longitude',
                         'cohort_labels', 'is_control'])
        writer.writerow([10, 0, 33.1, 126.1, 'focus_a;focus_b', 'false'])
        writer.writerow([11, 1, 33.2, 126.2, 'control', 'true'])
    membership = state.load_membership(membership_path)
    assert [row['flat_index_yx'] for row in membership] == ['10', '11']

    controls_path = tmp_path / 'matched_controls.csv'
    with controls_path.open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['target_flat_index_yx', 'cohort_label', 'control_flat_index_yx',
                         'valid_match', 'baseline_case', 'candidate_case'])
        writer.writerow([10, 'focus_a', 11, 'True', 'ORIGINAL', 'A'])
        writer.writerow([10, 'focus_b', 11, 'True', 'A', 'C'])
    links = state.validate_matched_controls(controls_path, np.array([10, 11]))
    assert len(links) == 2


def test_surface_weighting_returns_one_value_per_point():
    values = np.array([[1., 2., 3., 4.], [10., 20., 30., 40.]])
    weights = np.array([[.1, .2, .3, .4], [.4, .3, .2, .1]])
    actual = state.weighted_surface(values, weights)
    np.testing.assert_allclose(actual, np.sum(values * weights, axis=-1))
    assert actual.shape == (2,)

