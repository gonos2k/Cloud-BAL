"""Lower-factor scoring contract, comparison baseline, and ranking tests."""

import ast
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'cp02_snow_lower', ROOT / 'tools/cp02_snow_lower.py')
lower = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lower)
extension = lower.load_module('snow_extension_for_lower_tests', lower.EXTENSION_TOOL)
lower.validate_candidate_metadata()
extension.ALPHA_BY_CASE.update(lower.ALPHA_BY_CASE)
extension.ARM_BY_CASE.update(lower.ARM_BY_CASE)


def _selection_rows():
    categorical, continuous = [], []
    for index, case in enumerate(lower.ELIGIBLE_CASES):
        for threshold in lower.THRESHOLDS:
            categorical.append({
                'lead_hour': 1, 'case': case, 'threshold_mm': threshold,
                'CSI': 0.1 + index / 100.0, 'FAR': 0.5 - index / 1000.0})
        continuous.append({'lead_hour': 1, 'case': case,
                           'RMSE_mm': 12.0 - index / 10.0})
    return categorical, continuous


def test_lower_case_scope_reuses_prior_30_and_adds_eight_new_cases():
    assert lower.NEW_CASES == tuple(
        f'{arm}_SNOW_{suffix}' for arm in ('CONTROL', 'IMPROVED')
        for suffix in ('060', '070', '080', '090'))
    assert len(lower.NEW_CASES) == 8
    assert len(lower.ELIGIBLE_CASES) == 38
    assert len(lower.CONTEXT_CASES) == 39
    assert lower.CONTEXT_CASES.count('CURRENT_HYDRO') == 1
    assert 'CURRENT_HYDRO' not in lower.ELIGIBLE_CASES
    assert lower.CONTEXT_CASES.count('CONTROL_SNOW_050') == 1
    assert lower.CONTEXT_CASES.count('IMPROVED_SNOW_050') == 1


def test_alpha_and_family_metadata_covers_every_eligible_snow_case():
    expected = set(lower.ELIGIBLE_CASES) - {'ORIGINAL', 'IMPROVED_BG_FIXED'}
    assert set(lower.ALPHA_BY_CASE) == expected
    assert set(lower.ARM_BY_CASE) == expected
    for case in expected:
        family, suffix = case.split('_SNOW_')
        assert lower.ARM_BY_CASE[case] == family
        assert lower.ALPHA_BY_CASE[case] == lower.SNOW_SUFFIXES[suffix]


def test_lower_plan_and_reused_fine_analysis_are_hash_bound():
    plan_record, plan = lower.check_selection_plan()
    assert plan_record['sha256'] == lower.PLAN_SHA256
    assert plan['experiment']['factor_codes'] == ['060', '070', '080', '090']
    receipt, arrays, records = lower.load_prior_analysis()
    assert len(receipt['cases']) == 31
    assert len(receipt['eligible_cases']) == 30
    assert set(arrays[13]) == set(lower.CONTEXT_CASES) - set(lower.NEW_CASES) | {
        'reference', 'latitude', 'longitude', 'flat_index_yx'}
    assert len(records) == 11


def test_comparison_rows_use_original_at_matching_lead_and_threshold():
    categorical = []
    for case in lower.ELIGIBLE_CASES:
        for lead in lower.LEADS:
            for threshold in lower.THRESHOLDS:
                csi = (0.2 if case == 'ORIGINAL' else 0.2 + lead / 100 + threshold / 1000)
                categorical.append({'case': case, 'lead_hour': lead,
                                    'threshold_mm': threshold, 'CSI': csi,
                                    'FAR': 0.4})
    rows = lower.comparison_rows(categorical)
    assert len(rows) == 38 * 6 * 6
    row = next(row for row in rows if row['case'] == 'CONTROL_SNOW_060'
               and row['lead_hour'] == 3 and row['threshold_mm'] == 5.0)
    assert row['baseline_case'] == 'ORIGINAL'
    assert row['baseline_CSI'] == 0.2
    assert row['delta_CSI_vs_ORIGINAL'] == pytest.approx(0.2 + 0.03 + 0.005 - 0.2)
    original = next(row for row in rows if row['case'] == 'ORIGINAL'
                    and row['lead_hour'] == 3 and row['threshold_mm'] == 5.0)
    assert original['delta_CSI_vs_ORIGINAL'] == 0.0


def test_hourly_point_differences_share_original_and_preserve_paired_coordinates():
    baseline = np.arange(lower.POINTS, dtype=float)
    values = {case: baseline.copy() for case in lower.CONTEXT_CASES}
    values['CONTROL_SNOW_060'] = baseline + 1.25
    values['IMPROVED_SNOW_090'] = baseline - 2.5
    values.update(reference=baseline.copy(), flat_index_yx=np.arange(lower.POINTS),
                  latitude=np.full(lower.POINTS, 35.0),
                  longitude=np.full(lower.POINTS, 127.0))
    differences = lower.hourly_differences_vs_original(values)
    assert set(differences) == set(lower.CONTEXT_CASES) | {
        'reference', 'flat_index_yx', 'latitude', 'longitude'}
    assert (differences['CONTROL_SNOW_060'] == 1.25).all()
    assert (differences['IMPROVED_SNOW_090'] == -2.5).all()
    assert (differences['CURRENT_HYDRO'] == 0.0).all()
    assert (differences['ORIGINAL'] == 0.0).all()
    assert (differences['flat_index_yx'] == values['flat_index_yx']).all()


def test_selector_keeps_frozen_lexicographic_single_winner_policy():
    categorical, continuous = _selection_rows()
    target = 'IMPROVED_SNOW_080'
    next(row for row in categorical if row['case'] == target and row['threshold_mm'] == 10.0)['CSI'] = 0.99
    next(row for row in continuous if row['case'] == target)['RMSE_mm'] = 999.0
    rows, selection = lower.select_lower_case(categorical, continuous)
    assert selection['selected_case'] == target
    assert len(rows) == 38
    assert selection['ranking_order'] == [
        'descending +1h CSI at 10 mm', 'descending +1h CSI at 5 mm',
        'ascending +1h FAR at 10 mm', 'ascending +1h RMSE',
        'ascending absolute snow-factor deviation from 1', 'ascending case ID']


def test_selector_uses_far_rmse_alpha_and_id_tiebreakers_without_averaging():
    categorical, continuous = _selection_rows()
    ordered = ['CONTROL_SNOW_110', 'IMPROVED_SNOW_110']
    for row in categorical:
        if row['case'] in ordered:
            row['CSI'] = 0.75
            if row['threshold_mm'] == 10.0:
                row['FAR'] = 0.2
        if row['case'] == 'ORIGINAL':
            row['CSI'] = 0.0
    for row in continuous:
        if row['case'] in ordered:
            row['RMSE_mm'] = 3.0
    rows, selection = lower.select_lower_case(categorical, continuous)
    # Equal factors make the exact tie go to case ID. The separate metadata
    # coverage test catches an omitted 1.1 mapping before this selector runs.
    assert selection['selected_case'] == 'CONTROL_SNOW_110'
    assert 'pooled' not in json.dumps(selection).lower()
    assert rows[0]['case'] == selection['selected_case']


def test_selector_prefers_factor_closer_to_one_before_case_id():
    categorical, continuous = _selection_rows()
    candidates = {'IMPROVED_SNOW_075', 'CONTROL_SNOW_050'}
    for row in categorical:
        if row['case'] in candidates:
            row['CSI'] = 0.95
            if row['threshold_mm'] == 10.0:
                row['FAR'] = 0.2
        if row['case'] == 'ORIGINAL':
            row['CSI'] = 0.0
    for row in continuous:
        if row['case'] in candidates:
            row['RMSE_mm'] = 2.0
    _, selection = lower.select_lower_case(categorical, continuous)
    # CONTROL_SNOW_050 sorts earlier by ID, but alpha .75 is closer to 1 than .5.
    assert selection['selected_case'] == 'IMPROVED_SNOW_075'


@pytest.mark.parametrize(('control_case', 'improved_case'), [
    ('CONTROL_SNOW_060', 'IMPROVED_SNOW_140'),
    ('CONTROL_SNOW_110', 'IMPROVED_SNOW_090'),
])
def test_exact_decimal_symmetric_factors_reach_case_id_tiebreak(control_case, improved_case):
    categorical, continuous = _selection_rows()
    candidates = {control_case, improved_case}
    for row in categorical:
        if row['case'] in candidates:
            row['CSI'] = 0.95
            if row['threshold_mm'] == 10.0:
                row['FAR'] = 0.2
        if row['case'] == 'ORIGINAL':
            row['CSI'] = 0.0
    for row in continuous:
        if row['case'] in candidates:
            row['RMSE_mm'] = 2.0
    _, selection = lower.select_lower_case(categorical, continuous)
    assert selection['selected_case'] == control_case
    assert selection['alpha_distance_method'].startswith('Exact integer factor-code distance')


def test_runtime_common_plan_rejects_wrong_frozen_pin(tmp_path):
    runtime = tmp_path / 'runtime'
    runtime.mkdir()
    common = runtime / 'common_plan.json'
    common.write_text(json.dumps({'status': 'PASS_READY_TO_LAUNCH', 'case_records': {}}))
    with pytest.raises(ValueError, match='common-plan pin'):
        lower.check_runtime(runtime, {'sha256': 'plan-pin'}, 'wrong-pin')


def test_reused_half_case_analysis_receipt_rejects_wrong_pin(tmp_path, monkeypatch):
    (tmp_path / 'receipt.json').write_text('{}\n')
    monkeypatch.setattr(lower, 'PRIOR_HALF_RECEIPT_SHA256', '0' * 64)
    with pytest.raises(ValueError, match='analysis receipt pin changed'):
        lower.check_reused_half_runs(tmp_path)


def test_reused_half_cases_reject_a_different_physics_baseline():
    common = {
        'fixed_executable_sha256': 'control-exe',
        'original_executable_sha256': 'improved-exe',
        'improved_wrfinput_sha256': 'improved-input',
        'original_wrfinput_sha256': 'original-input',
        'original_source_wrfinput_sha256_before': 'source-input',
        'common_boundary_sha256': 'boundary',
        'common_six_hour_namelist_sha256': 'namelist',
        'native_metadata_contract_sha256': 'metadata',
        'source_b1_input_sha256_before': {'input': 'b1'},
        'original_source_sha256_before': {'input': 'original'},
        'source_field_value_sha256': {'CONTROL': {'QSNOW': 'c'},
                                      'IMPROVED': {'QSNOW': 'i'}},
    }
    lower.validate_reused_common_baseline(common, dict(common))
    changed = dict(common, common_boundary_sha256='different-boundary')
    with pytest.raises(ValueError, match='common_boundary_sha256'):
        lower.validate_reused_common_baseline(common, changed)


def test_cli_entrypoint_follows_all_helper_definitions():
    source = (ROOT / 'tools/cp02_snow_lower.py').read_text()
    module = ast.parse(source)
    guards = [node for node in module.body if isinstance(node, ast.If)
              and isinstance(node.test, ast.Compare)
              and isinstance(node.test.left, ast.Name)
              and node.test.left.id == '__name__']
    functions = [node for node in module.body if isinstance(node, ast.FunctionDef)]
    assert len(guards) == 1
    assert guards[0] is module.body[-1]
    assert all(function.lineno < guards[0].lineno for function in functions)
