"""Boundary, coverage, capture selection, and publication invariants."""
import csv
import json
from pathlib import Path
import shutil
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import cp02_low_threshold_cohorts as low

RESULTS = ROOT / 'docs/evidence/cp02_first_ice_velocity_20261109/evaluation/results'


def test_threshold_equality():
    h = {'reference': np.array([0., .5, 0., 0., 0.]),
         low.ORIGINAL: np.array([0., 0., .5, .499, .5]),
         low.fa.NEW: np.array([.5, .5, .499, .499, .5])}
    m = low.masks(h, low.ORIGINAL, .5)
    assert np.flatnonzero(m['new']).tolist() == [0]
    assert np.flatnonzero(m['resolved']).tolist() == [2]
    assert np.flatnonzero(m['persistent']).tolist() == [4]


def test_full_coverage_and_representatives():
    arrays = low.E.read_arrays(RESULTS)
    rows, counts = low.diagnostics(arrays)
    assert counts['union_05_1'] == {'all': 233, 'outside_old_128': 226}
    assert [counts['ORIGINAL'][str(t)]['new'] for t in low.THRESHOLDS] == [115, 138, 167]
    assert sum(r['low_05_1_union'] for r in rows) == 233
    assert sum(any(r['old_' + k] for k in ('persistent', 'new', 'resolved')) for r in rows) == 128
    selected = low.representatives(arrays)
    assert len(selected) == len({p for _, p, _ in selected}) == 21
    assert [p for role, p, _ in selected if role == 'h1_named_new'] == list(low.fa.TARGETS)
    assert low.representatives(arrays) == selected
    for r in low.weak_detection(arrays):
        assert r['forecast_below_0.1'] + r['forecast_0.1_to_1'] + r['forecast_at_least_1'] == r['observations']
        assert r['forecast_0.1_to_1'] + r['forecast_at_least_1'] == r['forecast_at_least_0.1']


def test_publication_replay_and_guards(tmp_path):
    first, second = tmp_path / 'first', tmp_path / 'second'
    low.run(RESULTS, first)
    low.run(RESULTS, second)
    receipt = json.loads((first / 'receipt.json').read_text())
    assert receipt['status'] == 'COMPLETE'
    for name in receipt['outputs']:
        assert (first / name).read_bytes() == (second / name).read_bytes()
    with pytest.raises(FileExistsError):
        low.run(RESULTS, first)
    copied = tmp_path / 'input'
    shutil.copytree(RESULTS, copied)
    with (copied / 'hour_18_arrays.npz').open('ab') as f:
        f.write(b'stale')
    with pytest.raises(ValueError, match='array hash mismatch'):
        low.run(copied, tmp_path / 'bad')
    assert not (tmp_path / 'bad').exists()
    with (first / 'selected_points.csv').open() as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        assert int(r['native_j0_zero_based']) == int(r['crop_j0_zero_based']) + 5
        assert int(r['native_i0_zero_based']) == int(r['crop_i0_zero_based']) + 74
        assert int(r['native_j0_fortran_one_based']) == int(r['native_j0_zero_based']) + 1
        assert int(r['native_i0_fortran_one_based']) == int(r['native_i0_zero_based']) + 1
        assert sum(float(r[k]) for k in ('weight_j0_i0', 'weight_j0_i1', 'weight_j1_i0', 'weight_j1_i1')) == pytest.approx(1.)
