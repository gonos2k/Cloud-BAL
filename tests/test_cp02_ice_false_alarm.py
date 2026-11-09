"""Membership, threshold boundaries and sealed input publication checks."""
import importlib.util
import json
from pathlib import Path
import shutil

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / 'docs/evidence/cp02_first_ice_velocity_20261109/evaluation/results'
spec = importlib.util.spec_from_file_location('fa', ROOT / 'tools/cp02_ice_false_alarm.py')
fa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fa)


def test_exact_membership_and_thresholds():
    h = {'reference': np.array([0., 4.999, 0., 5., 0., 0.]),
         fa.B1: np.array([0., 0., 0., 0., 5., 0.]),
         fa.CONS: np.array([5., 4.999, 5., 5., 5., 4.999]),
         fa.NEW: np.array([5., 5., 4.999, 5., 5., 4.999])}
    masks = fa.cohort_masks(h)
    assert {k: np.flatnonzero(v).tolist() for k, v in masks.items()} == {
        'persistent': [0], 'new': [1], 'resolved': [2]}


def test_sealed_members_and_bins():
    arrays = fa.evaluation.read_arrays(RESULTS)
    selected = fa.members(arrays)
    assert {k: int(v.sum()) for k, v in fa.cohort_masks(arrays[18]).items()} == {
        'persistent': 65, 'new': 26, 'resolved': 37}
    assert [p for c, p, _ in selected if c == 'named_new'] == list(fa.TARGETS)
    bins = fa.intensity_bins(arrays)
    for hour in range(1, 7):
        for case in fa.CASES:
            subset = [r for r in bins if r['lead_hour'] == hour and r['case'] == case]
            assert sum(r['observations'] for r in subset) == 3688
            assert all(sum(r['forecast_' + label] for label in fa.LABELS) == r['observations'] for r in subset)


def test_stale_inputs_and_no_overwrite(tmp_path):
    dest = tmp_path / 'output'
    dest.symlink_to(tmp_path / 'missing', target_is_directory=True)
    with pytest.raises(FileExistsError): fa.run(RESULTS, dest)
    copied = tmp_path / 'input'
    shutil.copytree(RESULTS, copied)
    with (copied / 'hour_18_arrays.npz').open('ab') as f: f.write(b'stale')
    with pytest.raises(ValueError, match='array hash mismatch'): fa.run(copied, tmp_path / 'other')
    assert not (tmp_path / 'other').exists()
    receipt = json.loads((RESULTS / 'receipt.json').read_text())
    assert receipt['status'] == 'COMPLETE'


def test_intensity_bins_are_left_inclusive():
    values = np.array([0., .1, .5, 1., 2.5, 5., 10.])
    h = {'reference': values, **{case: values for case in fa.CASES}}
    rows = fa.intensity_bins({hour: h for hour in fa.HOURS})
    first = [r for r in rows if r['lead_hour'] == 1 and r['case'] == fa.B1]
    assert [r['observations'] for r in first] == [1] * 7
    assert [r['forecast_ge_0.1_mm'] for r in first] == [0, 1, 1, 1, 1, 1, 1]
    assert [r['forecast_ge_5_mm'] for r in first] == [0, 0, 0, 0, 0, 1, 1]


def test_native_mapping_uses_pinned_crop_and_index_conventions():
    inventory = json.loads(fa.INVENTORY.read_text())
    offsets = fa.crop_offsets(inventory)
    assert offsets == (5, 74)
    arrays = fa.evaluation.read_arrays(RESULTS)
    with np.load(RESULTS / 'bilinear_mapping.npz', allow_pickle=False) as data:
        mapping = {k: data[k].copy() for k in data.files}
    row = fa.paths(arrays, mapping, [('sample', 9897, '')], offsets)[0]
    assert (row['crop_j0_zero_based'], row['crop_i0_zero_based']) == (66, 63)
    assert (row['native_j0_zero_based'], row['native_i0_zero_based']) == (71, 137)
    assert (row['native_j0_fortran_one_based'], row['native_i0_fortran_one_based']) == (72, 138)
    assert sum(row[k] for k in ('weight_j0_i0', 'weight_j0_i1', 'weight_j1_i0', 'weight_j1_i1')) == pytest.approx(1.)
    inventory['grid']['crop_y_inclusive'][0] += 1
    with pytest.raises(ValueError, match='pinned crop differs'): fa.crop_offsets(inventory)
