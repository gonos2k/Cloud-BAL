from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import cp02_initial_boundaries as cp


def test_numeric_difference_treats_signed_zero_equal_and_halos_missing():
    a = np.array([0., 1., 3., 7.], dtype='f4')
    b = np.array([-0., 2., 3., 9.], dtype='f4')
    valid = np.array([True, True, True, False])
    d = cp.differing(a, b, valid)
    assert d.tolist() == [False, True, False, False]
    assert cp.cross_counts(np.array([False, True, True, True]), d, valid) == {'neither':1, 'input_only':1, 'entry_only':0, 'both':1}


def test_nonfinite_called_fails_and_uncalled_is_not_observed():
    a = np.array([1., np.nan], dtype='f4')
    b = np.array([1., 4.], dtype='f4')
    assert not cp.differing(a, b, np.array([True, False])).any()
    with pytest.raises(ValueError, match='invalid'):
        cp.differing(a, b, np.array([True, True]))


def test_sparse_indices_and_raw_float32_roundtrip(tmp_path):
    a = np.array([0., np.float32(1.25), -3., 0.], dtype='f4')
    b = np.array([0., np.float32(1.5), -3., np.float32(1.e-20)], dtype='f4')
    d = cp.differing(a, b, np.ones(4, dtype=bool))
    path = tmp_path/'sparse.npz'
    assert cp.write_sparse(path, a, b, d) == 2
    with np.load(path, allow_pickle=False) as data:
        assert data['index_jki_zero_based'].tolist() == [1, 3]
        assert np.array_equal(data['B1'].view('u4'), a[d].view('u4'))
        assert np.array_equal(data['DM065'].view('u4'), b[d].view('u4'))


def test_anchor_mapping_uses_actual_corner_coordinates():
    rows = cp.read_anchors()
    anchor = [(int(r['wrf_i_1based']), int(r['wrf_j_1based'])) for flat, _, r in rows if flat == 20330]
    assert set(anchor) == {(141, 142), (142, 142), (141, 143), (142, 143)}
    assert len(rows) == 16


def test_frozen_plan_and_prior_identity():
    assert cp.verify_plan(cp.BUNDLE/'plan.json')['base_commit'] == '4e193057538840c47631761ac22e70169fbfc0c3'


def test_launch_receipt_is_bound_to_pinned_parity_gate(tmp_path):
    path = tmp_path/'launch.json'
    path.write_text('{"status":"PASS"}')
    expected = cp.sha(path)
    assert cp.validate_launch_binding(path, expected)['status'] == 'PASS'
    path.write_text('{"status":"CHANGED"}')
    with pytest.raises(ValueError, match='pinned parity gate'):
        cp.validate_launch_binding(path, expected)
