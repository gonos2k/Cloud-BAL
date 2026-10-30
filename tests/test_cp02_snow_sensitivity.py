"""Synthetic paired scoring and preregistered QSNOW selector checks."""
import importlib.util
import hashlib
import json
import ast
from pathlib import Path

import numpy as np
import pytest

ROOT = __import__('pathlib').Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'cp02_snow_sensitivity', ROOT / 'tools/cp02_snow_sensitivity.py')
snow = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(snow)


def _selection_fixture():
    categorical, continuous = [], []
    for case in snow.CASES:
        for lead in range(1, 7):
            continuous.append({'lead_hour': lead, 'case': case,
                               'MAE_mm': 1.0, 'RMSE_mm': 2.0})
            for threshold in snow.THRESHOLDS:
                csi = 0.5 if case == 'IMPROVED_BG_FIXED' else 0.6
                categorical.append({'lead_hour': lead, 'case': case,
                                    'threshold_mm': threshold, 'CSI': csi})
    pooled = {case: {'pooled_MAE_mm': 1.5, 'pooled_RMSE_mm': 2.5} for case in snow.CASES}
    return categorical, continuous, pooled


def test_score_hour_covers_15_cases_and_candidate_control_transitions():
    scorer = type('Scorer', (), {
        'scores': staticmethod(lambda pred, obs, threshold: {
            'hit': 2, 'miss': 1, 'false_alarm': 1, 'correct_dry': 3684,
            'CSI': 0.5, 'ETS': 0.0, 'POD': 2/3, 'FAR': 1/3, 'frequency_bias': 1.0}),
        'transitions': staticmethod(lambda old, new, obs, threshold: {
            'changed_to_correct': 1, 'changed_to_incorrect': 0})})
    values = {case: np.zeros(snow.POINTS) for case in snow.CASES}
    values.update(reference=np.zeros(snow.POINTS), latitude=np.ones(snow.POINTS),
                  longitude=np.ones(snow.POINTS), flat_index_yx=np.arange(snow.POINTS))
    categorical, continuous, transitions = snow.score_hour(13, values, scorer)
    assert len(categorical) == 15 * 6
    assert len(continuous) == 15
    assert len(transitions) == 12 * 2 * 6
    assert {row['baseline'] for row in transitions} == {'ORIGINAL', 'IMPROVED_BG_FIXED'}
    assert categorical[0]['window_start_utc'] == '2026-08-16T12:00:00Z'
    assert categorical[0]['window_end_utc'] == '2026-08-16T13:00:00Z'


def test_full_score_grid_enforces_all_cases_hours_thresholds_and_windows():
    scorer = type('Scorer', (), {
        'scores': staticmethod(lambda pred, obs, threshold: {'hit': 0, 'miss': 0,
            'false_alarm': 0, 'correct_dry': 3688, 'CSI': 0.0, 'ETS': 0.0,
            'POD': 0.0, 'FAR': 0.0, 'frequency_bias': 1.0}),
        'transitions': staticmethod(lambda old, new, obs, threshold: {
            'changed_to_correct': 0, 'changed_to_incorrect': 0})})
    categorical, continuous, transitions = [], [], []
    for hour in snow.HOURS:
        values = {case: np.zeros(snow.POINTS) for case in snow.CASES}
        values.update(reference=np.full(snow.POINTS, hour, dtype=float), latitude=np.ones(snow.POINTS),
                      longitude=np.ones(snow.POINTS), flat_index_yx=np.arange(snow.POINTS))
        rows = snow.score_hour(hour, values, scorer)
        categorical.extend(rows[0]); continuous.extend(rows[1]); transitions.extend(rows[2])
    snow.validate_score_rows(categorical, continuous, transitions)
    with pytest.raises(ValueError, match='complete 15×6×6 grid'):
        snow.validate_score_rows(categorical[:-1], continuous, transitions)


def test_selector_picks_best_case_that_passes_all_four_frozen_gates():
    categorical, continuous, pooled = _selection_fixture()
    for row in categorical:
        if row['case'] == 'IMPROVED_BG_FIXED' and row['lead_hour'] == 1 and row['threshold_mm'] == 5.0:
            row['CSI'] = 0.55
    for case, alpha in snow.ALPHA_BY_CASE.items():
        if case == 'IMPROVED_SNOW_050':
            for row in categorical:
                if row['case'] == case and row['lead_hour'] == 1:
                    row['CSI'] = 0.70
        if case in ('CONTROL_SNOW_000', 'IMPROVED_SNOW_050'):
            for row in continuous:
                if row['case'] == case and row['lead_hour'] == 1:
                    row['RMSE_mm'] = 1.9
                    row['MAE_mm'] = 0.9
            pooled[case] = {'pooled_MAE_mm': 1.4, 'pooled_RMSE_mm': 2.4}
    rows, choice = snow.selection_table(categorical, continuous, pooled)
    assert choice['best_eligible_improved_case'] == 'IMPROVED_SNOW_050'
    assert choice['best_eligible_overall_case'] == 'IMPROVED_SNOW_050'
    selected = next(row for row in rows if row['case'] == 'IMPROVED_SNOW_050')
    assert selected['feasible']
    assert all(selected[f'criterion_{name}'] for name in (
        'first_hour_CSI_at_5mm_at_least_alpha1', 'first_hour_RMSE_at_most_alpha1',
        'pooled_6h_MAE_at_most_alpha1', 'pooled_6h_RMSE_at_most_alpha1'))


def test_selector_fallback_and_equality_tolerance():
    categorical, continuous, pooled = _selection_fixture()
    for row in categorical:
        if row['case'] in snow.ALPHA_BY_CASE and row['lead_hour'] == 1 and row['threshold_mm'] == 5.0:
            row['CSI'] = 0.49
        if row['case'] == 'ORIGINAL' and row['lead_hour'] == 1 and row['threshold_mm'] == 5.0:
            row['CSI'] = 0.4
    rows, choice = snow.selection_table(categorical, continuous, pooled)
    assert choice['best_eligible_overall_case'] == 'IMPROVED_BG_FIXED'
    assert choice['best_eligible_improved_case'] == 'IMPROVED_BG_FIXED'
    assert choice['ranking_feasible_cases'] == ['IMPROVED_BG_FIXED']
    categorical, continuous, pooled = _selection_fixture()
    for row in categorical:
        if row['case'] == 'IMPROVED_BG_FIXED' and row['lead_hour'] == 1 and row['threshold_mm'] == 5.0:
            row['CSI'] = 0.5000000000005
        if row['case'] == 'CONTROL_SNOW_025' and row['lead_hour'] == 1 and row['threshold_mm'] == 5.0:
            row['CSI'] = 0.5
    for row in continuous:
        if row['case'] == 'CONTROL_SNOW_025' and row['lead_hour'] == 1:
            row['RMSE_mm'] = 2.0 + 5e-13
    pooled['CONTROL_SNOW_025'] = {'pooled_MAE_mm': 1.5 + 5e-13,
                                  'pooled_RMSE_mm': 2.5 + 5e-13}
    _, choice = snow.selection_table(categorical, continuous, pooled)
    assert 'CONTROL_SNOW_025' in choice['ranking_feasible_cases']


def test_selector_uses_alpha_deviation_then_case_id_for_ties():
    categorical, continuous, pooled = _selection_fixture()
    for row in categorical:
        if row['case'] == 'ORIGINAL' and row['lead_hour'] == 1 and row['threshold_mm'] == 5.0:
            row['CSI'] = 0.4
    _, choice = snow.selection_table(categorical, continuous, pooled)
    assert choice['best_eligible_overall_case'] == 'CONTROL_SNOW_075'
    assert choice['best_eligible_improved_case'] == 'IMPROVED_SNOW_075'
    assert choice['ranking_all_eligible_cases'].index('CONTROL_SNOW_075') < \
        choice['ranking_all_eligible_cases'].index('CONTROL_SNOW_125')


def test_selector_rejects_incomplete_rows_and_undefined_csi():
    categorical, continuous, pooled = _selection_fixture()
    categorical = [row for row in categorical if not (
        row['case'] == 'CONTROL_SNOW_000' and row['lead_hour'] == 1 and row['threshold_mm'] == 0.1)]
    with pytest.raises(ValueError, match='every case and threshold'):
        snow.selection_table(categorical, continuous, pooled)
    categorical, continuous, pooled = _selection_fixture()
    categorical[0]['CSI'] = None
    with pytest.raises(ValueError, match='undefined or non-finite'):
        snow.selection_table(categorical, continuous, pooled)
    categorical, continuous, pooled = _selection_fixture()
    categorical.append(dict(categorical[0]))
    with pytest.raises(ValueError, match='duplicate categorical'):
        snow.selection_table(categorical, continuous, pooled)


def test_frozen_selection_plan_hash_is_bound():
    record, plan = snow.check_selection_plan()
    assert record['sha256'] == snow.SELECTION_PLAN_SHA
    assert plan['status'] == 'FROZEN_BEFORE_CANDIDATE_FORECAST_OUTPUTS'


def test_cli_entrypoint_follows_all_helper_definitions():
    source = (ROOT / 'tools/cp02_snow_sensitivity.py').read_text()
    module = ast.parse(source)
    guards = [node for node in module.body if isinstance(node, ast.If)
              and isinstance(node.test, ast.Compare)
              and isinstance(node.test.left, ast.Name)
              and node.test.left.id == '__name__']
    assert len(guards) == 1
    guard = guards[0]
    functions = [node for node in module.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    assert guard is module.body[-1]
    assert all(function.lineno < guard.lineno for function in functions)


def _plan_case(case):
    source_fields = {'QSNOW': 'source-q'} | {f'F{i:03}': f'v{i}' for i in range(207)}
    case_fields = dict(source_fields)
    case_fields['QSNOW'] = 'scaled-q'
    base_inputs = {'wrf.exe': 'b' * 64, 'wrfinput_d01': 'c' * 64,
                   'wrfbdy_d01': snow.BOUNDARY_SHA,
                   'namelist.input': snow.SIX_HOUR_NAMELIST_SHA}
    base_inputs.update({f'input_{i:02}': f'{i:064x}' for i in range(85)})
    staged = dict(base_inputs)
    staged['wrf.exe'] = snow.OLD_EXE_SHA
    staged['wrfinput_d01'] = 'd' * 64
    audit = {
        'group': 'CONTROL', 'alpha': 0.0,
        'source_input_sha256': snow.ORIGINAL_INPUT_SHA,
        'source_qsnow_value_sha256': 'source-q',
        'scaled_qsnow_value_sha256': 'scaled-q',
        'scaling_rule': 'float64(source QSNOW) * float64(alpha), then cast to native float32',
        'dtype': 'float32', 'shape': [1], 'changed_value_count': 1, 'total_value_count': 1,
        'variable_count': 208, 'other_variables_unchanged': True,
        'all_native_metadata_unchanged': True, 'finite': True, 'nonnegative': True,
        'native_metadata_contract_sha256': 'm' * 64,
    }
    row = {'case': case, 'group': 'CONTROL', 'alpha': 0.0, 'scratch_directory': 'scratch/case',
           'staged_sha256': staged, 'qsnow_audit': audit, 'slot': 0, 'cpu_set': list(range(8))}
    families = {'CONTROL': source_fields, 'IMPROVED': source_fields}
    cases = {case: case_fields}
    return row, base_inputs, families, cases


def test_preflight_rejects_wrong_executable_or_baseline_native_input():
    case = 'CONTROL_SNOW_000'
    row, base, families, case_fields = _plan_case(case)
    snow.validate_case_plan_record(case, row, base, families, case_fields, 'm' * 64)
    row['staged_sha256']['wrf.exe'] = snow.FIXED_EXE_SHA
    with pytest.raises(ValueError, match='wrong executable/input/boundary'):
        snow.validate_case_plan_record(case, row, base, families, case_fields, 'm' * 64)
    row, base, families, case_fields = _plan_case(case)
    row['staged_sha256']['wrfinput_d01'] = snow.ORIGINAL_INPUT_SHA
    with pytest.raises(ValueError, match='wrong executable/input/boundary'):
        snow.validate_case_plan_record(case, row, base, families, case_fields, 'm' * 64)


def _receipt_fixture(tmp_path):
    case = 'CONTROL_SNOW_000'
    row, base, families, case_fields = _plan_case(case)
    run_dir = tmp_path / 'run'; run_dir.mkdir()
    staged = {}
    for name in row['staged_sha256']:
        payload = name.encode()
        (run_dir / name).write_bytes(payload)
        staged[name] = hashlib.sha256(payload).hexdigest()
    row['staged_sha256'] = staged
    row['scratch_directory'] = str(run_dir)
    histories = [f'wrfout_d01_2026-08-16_{hour:02d}:00:00' for hour in range(12, 19)]
    outputs = {}
    for name in histories:
        (run_dir / name).write_bytes(name.encode())
        outputs[name] = hashlib.sha256(name.encode()).hexdigest()
    source_maps = {'B1': {'wrf.exe': snow.FIXED_EXE_SHA},
                   'ORIGINAL': {'wrfinput_d01': snow.ORIGINAL_INPUT_SHA}, 'evidence': {}}
    receipt = {
        'status': 'SUCCESS', 'case': case, 'group': 'CONTROL', 'alpha': 0.0, 'exit': 0,
        'success_marker': True, 'histories_exact': True, 'histories': histories,
        'common_plan_sha256': 'p' * 64, 'selection_plan_sha256': snow.SELECTION_PLAN_SHA,
        'launch_scripts_sha256': {'run_case.py': 'l' * 64},
        'scratch_directory': str(run_dir),
        'common_plan_unchanged_after_run': True, 'staged_inputs_unchanged': True,
        'source_unchanged': True, 'affinity_outside_assigned_set': False,
        'preflight_case_sha256': staged, 'staged_sha256_after': staged,
        'source_sha256_before': source_maps, 'source_sha256_after': source_maps,
        'qsnow_audit': row['qsnow_audit'], 'cpu_slot': 0, 'cpu_set': list(range(8)),
        'mpi_ranks': 8, 'omp_threads': 1, 'i_mpi_pin_processor_list': ','.join(map(str, range(8))),
        'observed_rank_process_affinities': {str(i): [i] for i in range(8)},
        'output_sha256': outputs,
    }
    case_dir = tmp_path / 'case'; case_dir.mkdir()
    for name, content in (('launcher.txt', b'launcher'), ('rsl.out.0000.txt', b'WRF SUCCESS'),
                          ('runner_stdout.txt', b'case success')):
        (case_dir / name).write_bytes(content)
    receipt_path = case_dir / 'receipt.json'
    receipt_path.write_text(json.dumps(receipt))
    plan = {'_sha256': 'p' * 64, 'case_records': {case: row},
            'launch_scripts_sha256': {'run_case.py': 'l' * 64},
            'source_b1_input_sha256_before': source_maps['B1'],
            'original_source_sha256_before': source_maps['ORIGINAL'],
            'source_evidence_sha256_before': source_maps['evidence']}
    return case, plan, receipt_path, receipt


def test_runtime_receipt_rejects_incomplete_histories_and_wrong_output_hash(tmp_path):
    case, plan, receipt_path, receipt = _receipt_fixture(tmp_path)
    run_dir, evidence = snow.check_case_receipt(case, plan, receipt_path)
    assert len(evidence) == 1 + 89 + 7 + 3
    assert run_dir == Path(plan['case_records'][case]['scratch_directory'])
    first_history = receipt['histories'][0]
    receipt['output_sha256'][first_history] = '0' * 64
    receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match='runtime output hash mismatch'):
        snow.check_case_receipt(case, plan, receipt_path)
    receipt['output_sha256'][first_history] = hashlib.sha256(first_history.encode()).hexdigest()
    receipt['histories'] = receipt['histories'][:-1]
    receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match='raw runtime receipt is failed or incomplete'):
        snow.check_case_receipt(case, plan, receipt_path)


def test_paired_arrays_reject_a_shifted_reference_id():
    arrays = {}
    for hour in snow.HOURS:
        values = {case: np.zeros(snow.POINTS) for case in snow.CASES}
        values.update(reference=np.full(snow.POINTS, hour, dtype=float), latitude=np.ones(snow.POINTS),
                      longitude=np.ones(snow.POINTS), flat_index_yx=np.arange(snow.POINTS))
        arrays[hour] = values
    snow.validate_pairing(arrays)
    arrays[17]['flat_index_yx'] = arrays[17]['flat_index_yx'].copy()
    arrays[17]['flat_index_yx'][-1] += 1
    with pytest.raises(ValueError, match='flat_index_yx differs across hours'):
        snow.validate_pairing(arrays)

