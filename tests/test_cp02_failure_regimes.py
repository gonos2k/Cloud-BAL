import csv
import importlib.util
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('failure_regimes', ROOT / 'tools/cp02_failure_regimes.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


def test_all_eight_transitions_and_threshold_boundaries():
    ref = np.array([.1, .1, .1, .1, 0., 0., 0., 0.])
    old = np.array([.1, .1, 0., 0., .1, .1, 0., 0.])
    new = np.array([.1, 0., .1, 0., .1, 0., .1, 0.])
    assert list(r.transitions(ref, old, new, .1)) == list(r.LABELS)
    assert list(r.observed_band(np.array([0., .1, .999, 1., 5.]))) == [r.BANDS[0], r.BANDS[1], r.BANDS[1], r.BANDS[2], r.BANDS[3]]


def write_archives(folder, mutate=None):
    for hour in range(13, 19):
        data = {k: np.array([0., .1, 10.], dtype=np.float64) for k in (*r.CASES, 'reference')}
        data.update(latitude=np.array([30., 31., 32.]), longitude=np.array([125., 126., 127.]),
                    flat_index_yx=np.array([2, 4, 6], dtype=np.int64))
        if mutate and hour == 14:
            mutate(data)
        np.savez_compressed(folder / f'hour_{hour}_arrays.npz', **data)


def test_load_arrays_rejects_duplicate_nonfinite_and_cross_lead_mismatch(tmp_path):
    for mutation in (lambda d: d.update(flat_index_yx=np.array([2, 2, 6])),
                     lambda d: d.update(reference=np.array([0., np.nan, 10.])),
                     lambda d: d.update(latitude=np.array([30., 31., 33.]))):
        write_archives(tmp_path, mutation)
        with pytest.raises(r.RegimeError):
            r.load_arrays(tmp_path, expected_points=3, grid=(3, 3))
    write_archives(tmp_path)
    assert len(r.load_arrays(tmp_path, expected_points=3, grid=(3, 3))) == 6


def test_undefined_csi_and_focus_groups():
    with pytest.raises(r.RegimeError, match='undefined CSI'):
        r.score_counts(np.zeros(2), np.zeros(2), 1.)
    assert r.focus_group(2, .1, r.BANDS[1], 'lost_hit') == 'lead2_weak'
    assert r.focus_group(3, .1, r.BANDS[0], 'new_false_alarm') == 'lead3_false_alarm'
    assert r.focus_group(5, 5., r.BANDS[3], 'gained_hit') == 'lead5_heavy'
    assert not r.focus_group(2, .1, r.BANDS[0], 'retained_correct_negative')


def test_duplicate_rows_rejected(tmp_path):
    p = tmp_path / 'rows.csv'
    p.write_text('a,b\n1,2\n1,2\n')
    with pytest.raises(r.RegimeError, match='duplicate'):
        r.csv_rows(p, ('a', 'b'), 2)
