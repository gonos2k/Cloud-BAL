import csv
import gzip
import shutil
from pathlib import Path

import numpy as np
import pytest

import cp02_mp10_failure_cohorts as cohort

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / 'docs/evidence/cp02_pulse_path_20261110/evaluation/results'


def test_threshold_equality_and_transition_partition():
    h = {'reference': np.array([.1, .1, .099, .099]),
         cohort.e.ICE: np.array([.1, .099, .1, .099]),
         cohort.e.NEW: np.array([.099, .1, .099, .1])}
    masks = cohort.transition(h, cohort.e.ICE, .1)
    assert [int(masks[k].sum()) for k in ('hit_lost', 'hit_gained', 'fa_resolved', 'fa_new')] == [1, 1, 1, 1]
    assert np.all(np.sum(list(masks.values()), axis=0) == 1)


def test_real_selection_and_transition_counts():
    arrays = cohort.prior.read_arrays(RESULTS)
    selected = cohort.representatives(arrays)
    points = [p for _, p, _ in selected]
    assert len(points) == len(set(points)) == 30
    assert points.count(9774) == 1
    assert {19145, 19144, 17804, 12300, 12301} <= set(points)
    for lead, threshold, expected in ((6, 5, (9, 3, 57, 44)), (3, .1, (40, 7, 24, 16)),
                                      (6, .5, (12, 35, 67, 67))):
        masks = cohort.transition(arrays[lead + 12], cohort.e.ICE, threshold)
        assert tuple(int(masks[k].sum()) for k in ('hit_lost', 'hit_gained', 'fa_new', 'fa_resolved')) == expected
    h = arrays[18]
    mask = cohort.transition(h, cohort.e.B1, 5)['fa_new']
    assert mask.sum() == 121
    assert (mask & (h[cohort.e.NEW] >= 10)).sum() == 32
    assert [int((mask & (h['reference'] >= lo) & (h['reference'] < hi)).sum())
            for lo, hi in ((0, .1), (.1, 1), (1, 5))] == [52, 19, 50]


def test_publish_deterministic_and_refuses_destination(tmp_path):
    first, second = tmp_path / 'one', tmp_path / 'two'
    cohort.run(RESULTS, first)
    cohort.run(RESULTS, second)
    for name in ('selected_points.csv', 'native_columns.csv', 'transitions.csv',
                 'weak_conditional_errors.csv', 'classification.csv.gz', 'summary.json'):
        assert (first / name).read_bytes() == (second / name).read_bytes()
    with gzip.open(first / 'classification.csv.gz', 'rt') as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 6 * 3688
    assert sum(r['lead_hour'] == '6' and r['B1_5'] == 'fa_new' for r in rows) == 121
    with pytest.raises(FileExistsError):
        cohort.run(RESULTS, first)
    link = tmp_path / 'dangling'
    link.symlink_to(tmp_path / 'missing')
    with pytest.raises(FileExistsError):
        cohort.run(RESULTS, link)


def test_tampered_array_rejected(tmp_path):
    copy = tmp_path / 'results'
    shutil.copytree(RESULTS, copy)
    with (copy / 'hour_18_arrays.npz').open('ab') as stream:
        stream.write(b'changed')
    with pytest.raises(ValueError, match='array hash mismatch'):
        cohort.run(copy, tmp_path / 'out')
    assert not (tmp_path / 'out').exists()
