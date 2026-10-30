"""Focused selector and grid-contract tests for the strong-precipitation extension."""
import importlib.util
from pathlib import Path

import pytest
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'cp02_snow_extension', ROOT / 'tools/cp02_snow_extension.py')
extension = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(extension)


def _scores():
    categorical, continuous = [], []
    for case in extension.ELIGIBLE_CASES:
        for threshold in extension.THRESHOLDS:
            categorical.append({'lead_hour': 1, 'case': case, 'threshold_mm': threshold,
                                'CSI': 0.5, 'FAR': 0.4})
        continuous.append({'lead_hour': 1, 'case': case, 'RMSE_mm': 2.0})
    return categorical, continuous


def _set_metric(rows, case, threshold, metric, value):
    next(row for row in rows if row['case'] == case and row.get('threshold_mm') == threshold)[metric] = value


def test_extension_has_eight_new_cells_and_twenty_two_eligible_cases():
    assert len(extension.NEW_CASES) == 8
    assert len(extension.ELIGIBLE_CASES) == 22
    assert len(extension.CASE_ORDER) == 23
    assert 'CURRENT_HYDRO' not in extension.ELIGIBLE_CASES


def test_common_mask_uses_full_grid_masks_with_archived_vector_reference():
    mask = np.zeros((253, 149), dtype=bool)
    mask.flat[:extension.POINTS] = True
    mapped = mask.copy()
    reference = np.zeros(extension.POINTS)
    paired_ids = np.flatnonzero(mask)
    common = extension.check_paired_common_mask(mask, mapped, reference, paired_ids,
                                                'CONTROL_SNOW_175', 13)
    assert common.shape == (253, 149)
    assert int(common.sum()) == extension.POINTS
    with pytest.raises(ValueError, match='different grid shapes'):
        extension.check_paired_common_mask(mask, np.ones(extension.POINTS, dtype=bool),
                                           reference, paired_ids, 'CONTROL_SNOW_175', 13)


def test_remap_sets_prior_global_case_list_to_successful_extension_cases(monkeypatch):
    monkeypatch.setattr(extension, 'POINTS', 2)
    case = 'CONTROL_SNOW_175'
    mask = np.array([[True, True], [False, False]])
    old_arrays = {hour: {'reference': np.zeros(2), 'flat_index_yx': np.array([0, 1])}
                  for hour in extension.HOURS}

    class Evaluator:
        NEGATIVE_TOLERANCE_MM = 0.0
        CASES = ('ORIGINAL', 'CURRENT_HYDRO')

        @classmethod
        def check_resets(cls, snapshots):
            assert cls.CASES == (case,)
            assert set(snapshots) == {case}
            return {'cases': {case: 'PASS'}}

        @staticmethod
        def build_curvilinear_mapping(*args):
            return {'valid': mask.copy(), 'residual_max_deg': 0.0}

        @staticmethod
        def raw_total(snapshot):
            return snapshot['total'], snapshot['valid']

        @staticmethod
        def remap_field(total, valid, mapping):
            return np.ones((2, 2)), mask.copy()

    class Prior:
        evaluator = Evaluator

    class Scorer:
        @staticmethod
        def checked_snapshot(path, valid_time, inventory):
            return {'lat': np.ones((4, 4)), 'lon': np.ones((4, 4)),
                    'total': np.ones((4, 4)), 'valid': np.ones((4, 4), dtype=bool)}, {}

    arrays, _, _, resets = extension.add_extension_arrays(
        old_arrays, {case: Path('/unused')}, Prior, Scorer,
        {'grid': {'crop_x_inclusive': (2, 4), 'crop_y_inclusive': (2, 4)}},
        mask, np.ones((2, 2)), np.ones((2, 2)))
    assert arrays[13][case].shape == (2,)
    assert resets['cases'] == {case: 'PASS'}


def test_selector_uses_strong_precip_then_tie_break_fields_without_error_veto():
    categorical, continuous = _scores()
    first, second = extension.ELIGIBLE_CASES[:2]
    _set_metric(categorical, first, 10.0, 'CSI', 0.61)
    _set_metric(categorical, second, 10.0, 'CSI', 0.60)
    next(row for row in continuous if row['case'] == first)['RMSE_mm'] = 999.0
    rows, choice = extension.select_case(categorical, continuous)
    assert choice['selected_case'] == first
    assert rows[0]['lead1_RMSE_mm'] == 999.0
    assert 'not vetoes' in choice['eligibility']


def test_selector_ranks_completed_subset_and_can_exclude_incomplete_cases():
    categorical, continuous = _scores()
    completed = extension.ELIGIBLE_CASES[:14]
    rows, choice = extension.select_case(categorical, continuous, completed)
    assert len(rows) == 14
    assert len(choice['selection_order']) == 14
    assert not any(case in choice['selection_order'] for case in extension.NEW_CASES)


def test_selector_uses_csi5_far_rmse_alpha_distance_then_case_id():
    categorical, continuous = _scores()
    cases = ['CONTROL_SNOW_175', 'CONTROL_SNOW_200', 'CONTROL_SNOW_250',
             'CONTROL_SNOW_300', 'IMPROVED_SNOW_175', 'IMPROVED_SNOW_200']
    # All six have equal CSI at 10 mm. Distinguish the next fields in sequence.
    for case in cases:
        _set_metric(categorical, case, 10.0, 'CSI', 0.7)
    _set_metric(categorical, cases[1], 5.0, 'CSI', 0.8)
    _, choice = extension.select_case(categorical, continuous)
    # Better CSI at 5 mm wins before FAR and RMSE are considered.
    assert choice['selected_case'] == cases[1]

    # FAR decides when both CSI values tie.
    categorical, continuous = _scores()
    for case in cases[:2]:
        _set_metric(categorical, case, 10.0, 'CSI', 0.7)
        _set_metric(categorical, case, 5.0, 'CSI', 0.6)
    _set_metric(categorical, cases[0], 10.0, 'FAR', 0.2)
    _set_metric(categorical, cases[1], 10.0, 'FAR', 0.1)
    _, choice = extension.select_case(categorical, continuous)
    assert choice['selected_case'] == cases[1]

    # RMSE, alpha distance, then case ID decide successive exact ties.
    categorical, continuous = _scores()
    tied = ('CONTROL_SNOW_175', 'CONTROL_SNOW_200', 'IMPROVED_SNOW_175')
    for case in tied:
        _set_metric(categorical, case, 10.0, 'CSI', 0.7)
        _set_metric(categorical, case, 5.0, 'CSI', 0.6)
        _set_metric(categorical, case, 10.0, 'FAR', 0.2)
    next(row for row in continuous if row['case'] == tied[0])['RMSE_mm'] = 3.0
    next(row for row in continuous if row['case'] == tied[1])['RMSE_mm'] = 2.0
    next(row for row in continuous if row['case'] == tied[2])['RMSE_mm'] = 4.0
    _, choice = extension.select_case(categorical, continuous)
    assert choice['selected_case'] == tied[1]
    next(row for row in continuous if row['case'] == tied[0])['RMSE_mm'] = 2.0
    _, choice = extension.select_case(categorical, continuous)
    assert choice['selected_case'] == tied[0]
    _set_metric(categorical, 'CONTROL_SNOW_175', 10.0, 'CSI', 0.7)
    _set_metric(categorical, 'IMPROVED_SNOW_175', 10.0, 'CSI', 0.7)
    _set_metric(categorical, 'CONTROL_SNOW_175', 5.0, 'CSI', 0.6)
    _set_metric(categorical, 'IMPROVED_SNOW_175', 5.0, 'CSI', 0.6)
    _, choice = extension.select_case(categorical, continuous)
    assert choice['selected_case'] == 'CONTROL_SNOW_175'


def test_undefined_primary_scores_are_sorted_after_defined_scores():
    categorical, continuous = _scores()
    undefined_case, defined_case = 'CONTROL_SNOW_175', 'CONTROL_SNOW_200'
    _set_metric(categorical, undefined_case, 10.0, 'CSI', None)
    _set_metric(categorical, defined_case, 10.0, 'CSI', 0.0)
    _set_metric(categorical, defined_case, 5.0, 'CSI', None)
    _set_metric(categorical, undefined_case, 10.0, 'FAR', None)
    rows, _ = extension.select_case(categorical, continuous)
    positions = {row['case']: index for index, row in enumerate(rows)}
    assert positions[defined_case] < positions[undefined_case]
    assert next(row for row in rows if row['case'] == undefined_case)['lead1_CSI_at_10mm'] is None


def test_score_grid_rejects_missing_hour_threshold_or_case():
    categorical, continuous = [], []
    for lead in extension.LEADS:
        hour = lead + 12
        for case in extension.CASE_ORDER:
            continuous.append({'lead_hour': lead, 'case': case, 'valid_obs': extension.POINTS,
                               'valid_utc': f'2026-08-16T{hour:02d}:00:00Z',
                               'window_start_utc': f'2026-08-16T{hour - 1:02d}:00:00Z',
                               'window_end_utc': f'2026-08-16T{hour:02d}:00:00Z'})
            for threshold in extension.THRESHOLDS:
                categorical.append({'lead_hour': lead, 'case': case,
                                    'threshold_mm': threshold, 'valid_obs': extension.POINTS,
                                    'valid_utc': f'2026-08-16T{hour:02d}:00:00Z',
                                    'window_start_utc': f'2026-08-16T{hour - 1:02d}:00:00Z',
                                    'window_end_utc': f'2026-08-16T{hour:02d}:00:00Z'})
    extension.validate_score_rows(categorical, continuous)
    with pytest.raises(ValueError, match='full case/hour/threshold grid'):
        extension.validate_score_rows(categorical[:-1], continuous)


def test_selection_plan_pin_and_policy_match():
    record, plan = extension.check_selection_plan()
    assert record['sha256'] == extension.SELECTION_PLAN_SHA256
    assert plan['evaluation']['primary_threshold_mm'] == 10.0

