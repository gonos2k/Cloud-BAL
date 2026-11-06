import importlib.util
from pathlib import Path
import shutil

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('failure_context', ROOT / 'tools/cp02_b1_failure_context.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


def test_native_layer_mean_precedes_weighting_and_invalid_corner_is_flagged():
    values = np.array([
        [[1, 5, 9, 13], [3, 7, 11, 15], [21, 25, 29, 33], [23, 27, 31, 35]],
        [[2, 4, 6, 8], [4, 6, 8, 10], [12, 14, 16, 18], [14, 16, 18, 20]],
    ], dtype=float)
    height = np.array([
        [[100, 100, 100, 100], [900, 900, 900, 900], [1500, 1500, 1500, 1500], [2500, 2500, 2500, 3500]],
        [[100, 100, 100, 100], [900, 900, 900, 900], [1500, 1500, 1500, 1500], [2500, 2500, 2500, 3500]],
    ], dtype=float)
    weights = np.array([[.1, .2, .3, .4], [.1, .2, .3, .4]])
    means, counts, weighted, valid = c.layer_corner_means(values, height, weights, 0, 1000)
    assert counts.tolist() == [[2, 2, 2, 2], [2, 2, 2, 2]]
    assert means[0].tolist() == [2, 6, 10, 14]
    assert weighted[0] == pytest.approx(10.0)
    means, counts, weighted, valid = c.layer_corner_means(values, height, weights, 1000, 3000)
    assert counts[0].tolist() == [2, 2, 2, 1]
    assert means[0].tolist() == [22, 26, 30, 33]
    assert weighted[0] == pytest.approx(29.6)
    height[1, :, 3] = 3500
    _, counts, weighted, valid = c.layer_corner_means(values, height, weights, 0, 1000)
    assert counts[1, 3] == 0
    assert not valid[1] and np.isnan(weighted[1])


def test_control_reuse_across_roles_does_not_merge_role_samples():
    events = [{'cohort_label': 'loss', 'flat_index_yx': 10},
              {'cohort_label': 'recovered', 'flat_index_yx': 10}]
    controls = [{'cohort_label': 'loss', 'target_flat_index_yx': 10,
                 'control_flat_index_yx': 99, 'valid_match': 'True'},
                {'cohort_label': 'recovered', 'target_flat_index_yx': 10,
                 'control_flat_index_yx': 99, 'valid_match': 'True'}]
    roles = c.role_pairs(events, controls)
    assert roles == {'loss': [(10, 99)], 'recovered': [(10, 99)]}
    assert sum(len(pairs) for pairs in roles.values()) == 2


def test_surface_checks_use_each_complete_case_hour_and_keep_unpaired_null():
    def rows_with_peak(peak):
        rows = [{'surface_score_residual_mm': 0.01,
                 'surface_verification': 'paired_score_array'} for _ in range(270)]
        rows[269]['surface_score_residual_mm'] = peak
        return rows

    original = c.surface_check('ORIGINAL', 13, rows_with_peak(0.9))
    modified = c.surface_check('A', 13, rows_with_peak(0.6))
    unpaired_rows = [{'surface_score_residual_mm': None,
                      'surface_verification': 'state_receipt_only_no_score_arm'} for _ in range(270)]
    unpaired = c.surface_check('B1_OLD_KDM6', 13, unpaired_rows)

    assert original == {'case': 'ORIGINAL', 'hour_utc': 13, 'points': 270,
                        'max_abs_residual_mm': 0.9, 'verification': 'paired_score_array'}
    assert modified['max_abs_residual_mm'] == 0.6
    assert unpaired == {'case': 'B1_OLD_KDM6', 'hour_utc': 13, 'points': 270,
                        'max_abs_residual_mm': None,
                        'verification': 'state_receipt_only_no_score_arm'}


def test_loader_rejects_missing_and_mutated_state_archives(tmp_path):
    state_dir = tmp_path / 'missing'
    state_dir.mkdir()
    shutil.copy2(c.STATE / 'receipt.json', state_dir / 'receipt.json')
    with pytest.raises(c.ContextError, match='missing receipt-bound state archive'):
        c.load_inputs(state_dir=state_dir)

    changed = tmp_path / 'changed'
    changed.mkdir()
    shutil.copy2(c.STATE / 'receipt.json', changed / 'receipt.json')
    archive = changed / 'ORIGINAL_h12.npz'
    shutil.copy2(c.STATE / archive.name, archive)
    content = bytearray(archive.read_bytes())
    content[-1] ^= 1
    archive.write_bytes(content)
    with pytest.raises(c.ContextError, match='state archive identity differs'):
        c.load_inputs(state_dir=changed)


def test_context_output_refuses_existing_directory(tmp_path):
    output = tmp_path / 'context'
    output.mkdir()
    keep = output / 'keep.txt'
    keep.write_text('unchanged')
    with pytest.raises(c.ContextError, match='already exists'):
        c.run(output=output)
    assert keep.read_text() == 'unchanged'


def test_pinned_state_context_recounts_legacy_crossings_and_surface_paths():
    _, arrays, focus, events, controls, scores, _pins = c.load_inputs()
    tables = c.derive_context(arrays, focus, events, controls, scores)
    assert len(tables['point_surface_paths']) == 270 * 4 * 6
    assert len(tables['layer_features']) == 270 * 4 * 7 * 2
    checks = tables['_surface_checks']
    assert len(checks) == 24
    for check in checks:
        rows = [row for row in tables['point_surface_paths']
                if row['case'] == check['case'] and row['hour_utc'] == check['hour_utc']]
        assert check['points'] == len(rows) == 270
        residuals = [abs(row['surface_score_residual_mm']) for row in rows
                     if row['surface_score_residual_mm'] is not None]
        assert check['max_abs_residual_mm'] == max(residuals, default=None)
        if check['case'] == 'B1_OLD_KDM6':
            assert check['max_abs_residual_mm'] is None
            assert check['verification'] == 'state_receipt_only_no_score_arm'
    summary = tables['cohort_surface_context_summary']
    h02 = next(r for r in summary if r['cohort_label'] == 'h02_original_A_weak_hit_loss'
               and r['population'] == 'target' and r['case'] == 'B1_OLD_KDM6')
    assert (h02['n_points'], h02['n_crossed_role_threshold']) == (10, 9)
    recovered = next(r for r in summary if r['cohort_label'] == 'h02_loss_recovered_by_C'
                     and r['population'] == 'target' and r['case'] == 'B1_OLD_KDM6')
    assert (recovered['n_points'], recovered['n_crossed_role_threshold']) == (3, 3)
    new_fa = next(r for r in summary if r['cohort_label'] == 'h05_A_C_5mm_new_FA'
                  and r['population'] == 'target' and r['case'] == 'ORIGINAL')
    assert (new_fa['new_FA_target_count'], new_fa['ORIGINAL_already_ge_5mm_count'],
            new_fa['X_already_ge_5mm_count'], new_fa['all_old_cases_below_5mm_count']) == (12, 7, 7, 5)
