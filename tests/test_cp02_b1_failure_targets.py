import importlib.util
from pathlib import Path
import shutil

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('failure_targets', ROOT / 'tools/cp02_b1_failure_targets.py')
t = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)


def synthetic_hourly():
    ids = np.arange(3688, dtype=np.int64)
    lat = np.full(3688, 35.0)
    lon = 125.0 + ids * 0.001
    hourly = {}
    for hour in t.HOURS:
        data = {key: np.zeros(3688) for key in t.CASES + ('reference',)}
        data.update(latitude=lat.copy(), longitude=lon.copy(), flat_index_yx=ids.copy())
        hourly[hour] = data
    h2, h5 = hourly[14], hourly[17]
    # Weak hit losses/gains and the exact .1 boundary are retained as weak.
    h2['reference'][0:2] = .1
    h2['ORIGINAL'][0] = .1
    h2['A'][0] = 0.
    h2['C'][0] = .1
    h2['A'][1] = .1
    # Dry false alarm and resolved false alarm.
    h2['A'][2] = .1
    h2['ORIGINAL'][3] = .1
    h2['reference'][3] = 0.
    h2['A'][3] = 0.
    # Threshold-five false alarm with observed values in the three requested bands.
    h5['reference'][10:13] = [0., .5, 2.]
    h5['C'][10:13] = 5.
    h5['A'][13] = 5.
    h5['C'][13] = 0.
    h5['reference'][14] = 6.
    h5['A'][14] = 6.
    h5['C'][14] = 0.
    h5['reference'][0] = 6.
    h5['A'][0] = 6.
    h5['C'][0] = 0.
    # Weak A→C hit loss, gain, and retained hit.
    h5['reference'][20:23] = [.1, .5, .999]
    h5['A'][20] = .1
    h5['C'][20] = 0.
    h5['C'][21] = .1
    h5['A'][22] = h5['C'][22] = .1
    h5['reference'][24] = 1.
    h5['reference'][25] = 5.
    return hourly


def test_observed_bands_keep_exact_threshold_edges():
    assert list(t.observed_band(np.array([0., .1, .999, 1., 4.999, 5.]))) == list(t.BANDS[:1]) + [
        t.BANDS[1], t.BANDS[1], t.BANDS[2], t.BANDS[2], t.BANDS[3]]


def test_multilabel_membership_is_deduped_and_recovery_is_partitioned():
    result = t.derive_targets(synthetic_hourly())
    rows = {row['flat_index_yx']: row for row in result['focus_membership']}
    assert len(rows) == len(result['focus_membership'])
    assert 'h02_original_A_weak_hit_loss' in rows[0]['cohort_labels']
    assert 'h02_loss_recovered_by_C' in rows[0]['cohort_labels']
    assert 'h02_original_A_new_FA' in rows[2]['cohort_labels']
    assert 'h05_A_C_5mm_new_FA_weak' in rows[11]['cohort_labels']
    assert 'h05_A_C_5mm_new_FA_1to5' in rows[12]['cohort_labels']
    assert 'h05_A_C_5mm_hit_loss' in rows[14]['cohort_labels']
    assert 'h05_A_C_weak_hit_loss' in rows[20]['cohort_labels']
    assert 'h05_A_C_weak_hit_gain' in rows[21]['cohort_labels']
    assert sum('h02_original_A_weak_hit_loss' in row['cohort_labels'] for row in rows.values()) == 1
    assert result['matched_controls']
    assert all(row['distance_km'] >= 0 for row in result['matched_controls'] if row['valid_match'])
    assert all(row['distance_km'] is None for row in result['matched_controls'] if not row['valid_match'])
    cross_lead = [row for row in result['matched_controls'] if row['target_flat_index_yx'] == 0]
    assert any(row['lead_hour'] == 2 and row['observed_band'] == '[0.1,1)' for row in cross_lead)
    assert any(row['lead_hour'] == 5 and row['observed_band'] == '[5,infinity)' for row in cross_lead)
    for row in result['matched_controls']:
        assert row['control_reuse_count'] >= int(row['valid_match'])
        assert row['control_reused_across_cohorts'] is bool(row['control_reuse_count'] > 1 and row['valid_match'])
        assert row['baseline_case'] and row['candidate_case']
    assert all(not any(label.endswith('_retained_hit') for label in row['cohort_labels'].split(';'))
               for row in rows.values())


def test_hourly_temporal_and_spatial_diagnostics_use_fixed_rows():
    result = t.derive_targets(synthetic_hourly())
    focus_count = len(result['focus_membership'])
    assert len(result['temporal_diagnostics']) == focus_count * 4
    assert {row['lead_hour'] for row in result['spatial_neighbors']} == set(t.LEADS)
    assert {row['radius_km'] for row in result['spatial_neighbors']} == set(t.RADII_KM)
    assert all(row['label'].startswith('interval_total_') for row in result['temporal_diagnostics'])


def test_receipt_bound_real_source_recounts_requested_sets():
    receipt, hourly = t.load_bundle()
    assert receipt['status'] == 'COMPLETE'
    result = t.derive_targets(hourly)
    tags = [row['cohort_labels'].split(';') for row in result['focus_membership']]
    counts = {label: sum(label in row for row in tags)
              for label in ('h02_original_A_weak_hit_loss', 'h02_original_A_weak_hit_gain',
                            'h02_original_A_new_FA', 'h02_original_A_resolved_FA',
                            'h05_A_C_5mm_new_FA', 'h05_A_C_5mm_resolved_FA',
                            'h05_A_C_5mm_hit_loss', 'h05_A_C_5mm_hit_gain',
                            'h05_A_C_weak_hit_loss', 'h05_A_C_weak_hit_gain',
                            'h06_A_C_weak_hit_loss', 'h06_A_C_weak_hit_gain')}
    assert counts == {'h02_original_A_weak_hit_loss': 10,
                      'h02_original_A_weak_hit_gain': 2,
                      'h02_original_A_new_FA': 53,
                      'h02_original_A_resolved_FA': 24,
                      'h05_A_C_5mm_new_FA': 12,
                      'h05_A_C_5mm_resolved_FA': 1,
                      'h05_A_C_5mm_hit_loss': 1,
                      'h05_A_C_5mm_hit_gain': 0,
                      'h05_A_C_weak_hit_loss': 17,
                      'h05_A_C_weak_hit_gain': 6,
                      'h06_A_C_weak_hit_loss': 8,
                      'h06_A_C_weak_hit_gain': 2}
    csi_row = next(row for row in result['csi_algebra']
                   if row['lead_hour'] == 5 and row['threshold_mm'] == 5.0 and row['contrast'] == 'C-A')
    assert csi_row['C_F'] == 234
    assert csi_row['hit_only_repair_below_A_with_candidate_F'] is True
    assert csi_row['restored_baseline_hit_with_candidate_F_exact_CSI'] == '55/282'
    assert csi_row['restored_baseline_hit_with_candidate_F_CSI'] < csi_row['A_CSI']


def test_output_is_atomic_and_refuses_existing_directory(tmp_path):
    existing = tmp_path / 'targets'
    existing.mkdir()
    marker = existing / 'keep.txt'
    marker.write_text('preserve')
    with pytest.raises(t.TargetError, match='already exists'):
        t.run(output=existing)
    assert marker.read_text() == 'preserve'


def test_source_loader_rejects_missing_and_mutated_receipt_bound_arrays(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    shutil.copy2(t.SOURCE / 'receipt.json', source / 'receipt.json')
    with pytest.raises(t.TargetError, match='missing receipt-bound source array'):
        t.load_bundle(source)
    archive = source / 'hour_13_arrays.npz'
    shutil.copy2(t.SOURCE / archive.name, archive)
    archive.write_bytes(archive.read_bytes()[:-1] + bytes([archive.read_bytes()[-1] ^ 1]))
    with pytest.raises(t.TargetError, match='identity differs from receipt'):
        t.load_bundle(source)
