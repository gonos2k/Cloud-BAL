#!/usr/bin/env python3
"""Score the fine-factor QSNOW sensitivity extension."""

import csv
import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT / 'docs/evidence/snow_fine_20261030'
RUNTIME_DIR = EVIDENCE_DIR / 'runtime'
PLAN_PATH = EVIDENCE_DIR / 'selection_plan.json'
PLAN_SHA256 = '99d810d036d3bb6931065cc54117e90d85e2a76e388fbb12f5760729a2b703d3'
PRIOR_ANALYSIS = ROOT / 'docs/evidence/snow_extension_20261030/analysis'
PRIOR_RECEIPT_SHA256 = 'c1a10562d9d8bef95a3a3cdc5ad71ef574b78649c2313fe49e7061273c876086'
PRIOR_TOOL = ROOT / 'tools/cp02_snow_extension.py'
PRIOR_TOOL_SHA256 = 'b450747f0d376a353eff8c33da7ebbddfedc5d137fa9e53e0b37f0e71907da86'
PRIOR_SENSITIVITY_TOOL = ROOT / 'tools/cp02_snow_sensitivity.py'
PRIOR_SENSITIVITY_TOOL_SHA256 = '95c3e8591318eafda06598616fdec1c11f67aa78aef3306ab473a1602ccadc17'
COMMON_PLAN_SHA256 = 'e9b38c481d19251062957fde4fd2be0e965979bef3ae0f02ed5b6503ef305978'
EXECUTABLE_SHA256 = {'CONTROL': 'de110a7f1d40143a74ffedbe64ed5b3717c413876093f56d200563e2f6b9c168',
                     'IMPROVED': '68ed2833b5f207d037949c9b20c7c2f800500e632f911a4acf1eb09d13bf1c1f'}
LEADS = tuple(range(1, 7))
HOURS = tuple(range(13, 19))
THRESHOLDS = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0)
POINTS = 3688
NEW_SUFFIXES = {'110': 1.1, '120': 1.2, '130': 1.3, '140': 1.4}
NEW_CASES = tuple(f'{arm}_SNOW_{suffix}' for arm in ('CONTROL', 'IMPROVED')
                  for suffix in NEW_SUFFIXES)
NEW_ALPHAS = {case: NEW_SUFFIXES[case.rsplit('_', 1)[1]] for case in NEW_CASES}
NEW_ARMS = {case: case.split('_', 1)[0] for case in NEW_CASES}
ELIGIBLE_CASES = ('ORIGINAL', 'IMPROVED_BG_FIXED', *(
    f'{arm}_SNOW_{suffix}' for arm in ('CONTROL', 'IMPROVED')
    for suffix in ('000', '025', '050', '075', '125', '150', '175', '200', '250', '300', '110', '120', '130', '140')))
CONTEXT_CASES = ('ORIGINAL', 'CURRENT_HYDRO', 'IMPROVED_BG_FIXED', *(
    f'{arm}_SNOW_{suffix}' for arm in ('CONTROL', 'IMPROVED')
    for suffix in ('000', '025', '050', '075', '125', '150', '175', '200', '250', '300', '110', '120', '130', '140')))


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def identity(path):
    path = Path(path)
    return {'path': str(path), 'sha256': sha256(path), 'size': path.stat().st_size}


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_selection_plan(path=PLAN_PATH, expected_sha256=PLAN_SHA256):
    record = identity(path)
    if record['sha256'] != expected_sha256:
        raise ValueError('frozen fine selection plan hash mismatch')
    plan = json.loads(Path(path).read_text())
    if (plan.get('status') != 'FROZEN_BEFORE_NEW_FORECAST_OUTPUTS_PRIOR_RESULTS_KNOWN'
        or plan.get('experiment', {}).get('families') != ['CONTROL', 'IMPROVED']
        or plan.get('experiment', {}).get('factor_codes') != list(NEW_SUFFIXES)
        or plan.get('experiment', {}).get('snow_factors') != list(NEW_SUFFIXES.values())
        or plan.get('experiment', {}).get('new_cases') != 8
        or plan.get('evaluation', {}).get('lead_hours') != list(LEADS)
        or plan.get('evaluation', {}).get('thresholds_mm') != list(THRESHOLDS)
        or plan.get('evaluation', {}).get('paired_points_per_hour') != POINTS
        or plan.get('evaluation', {}).get('primary_lead_hour') != 1
        or plan.get('evaluation', {}).get('primary_threshold_mm') != 10.0
        or plan.get('selection', {}).get('undefined_scores') !=
        'Undefined CSI ranks below defined CSI; undefined FAR after defined FAR. Do not replace undefined metrics with zero.'
        or plan.get('selection', {}).get('numerical_comparison_tolerance') != 0.0):
        raise ValueError('fine selection plan contract mismatch')
    expected_order = ['descending lead-1-hour CSI at 10 mm',
                      'descending lead-1-hour CSI at 5 mm',
                      'ascending lead-1-hour FAR at 10 mm',
                      'ascending lead-1-hour RMSE',
                      'ascending absolute snow-factor deviation from 1',
                      'ascending case ID']
    if plan.get('selection', {}).get('ranking_order') != expected_order:
        raise ValueError('fine selection ranking changed')
    return record, plan


def load_prior_analysis(path=PRIOR_ANALYSIS):
    path = Path(path)
    receipt_path = path / 'receipt.json'
    if sha256(receipt_path) != PRIOR_RECEIPT_SHA256:
        raise ValueError('sealed snow-extension analysis receipt pin changed')
    receipt = json.loads(receipt_path.read_text())
    if (receipt.get('status') != 'COMPLETE' or len(receipt.get('cases', [])) != 23
        or len(receipt.get('eligible_cases', [])) != 22
        or set(receipt.get('context_only_cases', [])) != {'CURRENT_HYDRO'}):
        raise ValueError('sealed snow-extension analysis scope is incomplete')
    source_hashes = {Path(row['path']).name: row['sha256'] for row in receipt.get('sources', [])}
    if (source_hashes.get(PRIOR_TOOL.name) != PRIOR_TOOL_SHA256
        or source_hashes.get(PRIOR_SENSITIVITY_TOOL.name) != PRIOR_SENSITIVITY_TOOL_SHA256
        or sha256(PRIOR_TOOL) != PRIOR_TOOL_SHA256
        or sha256(PRIOR_SENSITIVITY_TOOL) != PRIOR_SENSITIVITY_TOOL_SHA256):
        raise ValueError('sealed snow-extension scorer source pins changed')
    outputs = receipt.get('analysis_outputs')
    if not isinstance(outputs, dict):
        raise ValueError('sealed snow-extension artifact manifest is missing')
    arrays = {}
    for hour in HOURS:
        artifact = path / f'hour_{hour}_arrays.npz'
        if sha256(artifact) != outputs.get(artifact.name, {}).get('sha256'):
            raise ValueError(f'{hour}: sealed snow-extension array hash mismatch')
        with np.load(artifact, allow_pickle=False) as data:
            values = {key: np.array(data[key]) for key in data.files}
        if set(values) != set(receipt['cases']) | {'reference', 'latitude', 'longitude', 'flat_index_yx'}:
            raise ValueError(f'{hour}: sealed snow-extension array scope mismatch')
        if any(value.shape != (POINTS,) or not np.isfinite(value).all()
               for value in values.values()):
            raise ValueError(f'{hour}: sealed snow-extension arrays are invalid')
        arrays[hour] = values
    for name in ('categorical_scores.csv', 'continuous_scores.csv', 'selection_scores.csv',
                 'selection.json'):
        artifact = path / name
        if sha256(artifact) != outputs.get(name, {}).get('sha256'):
            raise ValueError(f'sealed snow-extension table hash mismatch: {name}')
    records = [identity(receipt_path)]
    records.extend(identity(path / name) for name in
                   [*(f'hour_{hour}_arrays.npz' for hour in HOURS),
                    'categorical_scores.csv', 'continuous_scores.csv',
                    'selection_scores.csv', 'selection.json'])
    return receipt, arrays, records


def check_runtime(runtime_dir, plan_record, expected_common_sha256=COMMON_PLAN_SHA256):
    runtime_dir = Path(runtime_dir)
    common_path = runtime_dir / 'common_plan.json'
    common_record = identity(common_path)
    if expected_common_sha256 is None or common_record['sha256'] != expected_common_sha256:
        raise ValueError('fine runtime common-plan pin is missing or mismatched')
    common = json.loads(common_path.read_text())
    if (common.get('status') != 'PASS_READY_TO_LAUNCH'
        or common.get('selection_plan_sha256') != plan_record['sha256']
        or common.get('case_count') != len(NEW_CASES)
        or common.get('declared_input_count_per_case') != 89
        or common.get('original_native_variable_count') != 208
        or common.get('all_native_metadata_unchanged') is not True
        or set(common.get('case_records', {})) != set(NEW_CASES)):
        raise ValueError('fine runtime common plan has incomplete scope or wrong selection pin')
    slots = common.get('cpu_affinity', {}).get('slots', {})
    slot_cases = common.get('cpu_affinity', {}).get('slot_cases', {})
    if len(slots) != 8 or len(slot_cases) != 8:
        raise ValueError('fine runtime CPU slot plan is incomplete')
    cases = common['case_records']
    field_sources = common.get('source_field_value_sha256', {})
    field_cases = common.get('case_field_value_sha256', {})
    source_inputs = {'CONTROL': common.get('original_source_sha256_before', {}),
                     'IMPROVED': common.get('source_b1_input_sha256_before', {})}
    if (set(field_sources) != {'CONTROL', 'IMPROVED'} or set(field_cases) != set(NEW_CASES)
        or any(len(field_sources[arm]) != 208 for arm in field_sources)
        or any(len(source_inputs[arm]) != 89 for arm in source_inputs)):
        raise ValueError('fine runtime source or native field manifests are incomplete')
    all_cpus, assigned_cases = [], []
    for case in NEW_CASES:
        row = cases[case]
        slot = str(row.get('slot'))
        arm, alpha = NEW_ARMS[case], NEW_ALPHAS[case]
        staged, audit = row.get('staged_sha256', {}), row.get('qsnow_audit', {})
        base_inputs = source_inputs[arm]
        expected_staged_names = (set(base_inputs) - {'namelist.output', 'wrf.exe'}) | {'wrf.exe'}
        if (row.get('case') != case or row.get('group') != NEW_ARMS[case]
            or row.get('alpha') != alpha or not row.get('scratch_directory')
            or not isinstance(staged, dict) or set(staged) != expected_staged_names or slot not in slots
            or row.get('cpu_set') != slots[slot] or case not in slot_cases.get(slot, [])
            or staged.get('wrf.exe') != EXECUTABLE_SHA256[arm]
            or staged.get('wrfinput_d01') == base_inputs.get('wrfinput_d01')
            or staged.get('wrfbdy_d01') != common.get('common_boundary_sha256')
            or staged.get('namelist.input') != common.get('common_six_hour_namelist_sha256')
            or any(staged.get(name) != digest for name, digest in base_inputs.items()
                   if name not in ('namelist.output', 'wrf.exe', 'wrfinput_d01'))):
            raise ValueError(f'{case}: fine runtime staged case contract failed')
        if (audit.get('group') != arm or audit.get('alpha') != alpha
            or audit.get('scaling_rule') != 'float64(source QSNOW) * float64(alpha), then cast to native float32'
            or audit.get('dtype') != 'float32' or audit.get('variable_count') != 208
            or audit.get('other_variables_unchanged') is not True
            or audit.get('all_native_metadata_unchanged') is not True
            or audit.get('finite') is not True or audit.get('nonnegative') is not True
            or audit.get('source_input_sha256') != base_inputs.get('wrfinput_d01')
            or audit.get('source_qsnow_value_sha256') != field_sources[arm].get('QSNOW')
            or audit.get('native_metadata_contract_sha256') != common.get('native_metadata_contract_sha256')):
            raise ValueError(f'{case}: fine QSNOW-only input audit failed')
        fields = field_cases[case]
        if (set(fields) != set(field_sources[arm]) or len(fields) != 208
            or fields.get('QSNOW') != audit.get('scaled_qsnow_value_sha256')
            or any(fields[name] != field_sources[arm][name] for name in field_sources[arm]
                   if name != 'QSNOW')):
            raise ValueError(f'{case}: native field hashes do not prove a sole-QSNOW change')
    for slot, cpus in slots.items():
        if len(cpus) != 8 or len(set(cpus)) != 8:
            raise ValueError('fine runtime CPU slot must contain eight unique CPUs')
        all_cpus.extend(cpus)
        assigned_cases.extend(slot_cases.get(slot, []))
    if (len(set(all_cpus)) != len(all_cpus) or not set(all_cpus).issubset(
            set(common.get('cpu_affinity', {}).get('allowed_cpus', [])))
        or set(assigned_cases) != set(NEW_CASES) or len(assigned_cases) != len(NEW_CASES)):
        raise ValueError('fine runtime CPU slots overlap or omit/duplicate cases')
    launch_scripts = common.get('launch_scripts_sha256')
    if not isinstance(launch_scripts, dict) or not launch_scripts:
        raise ValueError('fine runtime launch script pins are missing')
    launch_records = []
    for name, expected in launch_scripts.items():
        record = identity(runtime_dir / name)
        if record['sha256'] != expected:
            raise ValueError(f'fine runtime launch script changed: {name}')
        launch_records.append(record)
    launch_manifest = runtime_dir / 'launch_scripts.sha256.json'
    if json.loads(launch_manifest.read_text()) != launch_scripts:
        raise ValueError('fine runtime launch manifest differs from common plan')

    expected_histories = [f'wrfout_d01_2026-08-16_{hour:02d}:00:00' for hour in range(12, 19)]
    final = json.loads((runtime_dir / 'final_receipt.json').read_text())
    batch = json.loads((runtime_dir / 'batch_receipt.json').read_text())
    history = json.loads((runtime_dir / 'history_validation.json').read_text())
    final_path, batch_path, history_path = (runtime_dir / name for name in
                                            ('final_receipt.json', 'batch_receipt.json', 'history_validation.json'))
    if (final.get('status') != 'SUCCESS' or batch.get('status') != 'SUCCESS'
        or history.get('status') != 'SUCCESS' or final.get('case_count') != 8
        or batch.get('case_count') != 8 or final.get('common_plan_sha256') != common_record['sha256']
        or batch.get('common_plan_sha256') != common_record['sha256']
        or final.get('selection_plan_sha256') != plan_record['sha256']
        or batch.get('selection_plan_sha256') != plan_record['sha256']
        or final.get('batch_receipt_sha256') != sha256(batch_path)
        or final.get('history_validation_sha256') != sha256(history_path)
        or set(final.get('cases', {})) != set(NEW_CASES)
        or set(history.get('cases', {})) != set(NEW_CASES)):
        raise ValueError('fine runtime receipts are incomplete or not mutually bound')
    runs, records = {}, [common_record, identity(final_path), identity(batch_path),
                         identity(history_path), identity(launch_manifest), *launch_records]
    for case in NEW_CASES:
        receipt_path = runtime_dir / 'cases' / case / 'receipt.json'
        receipt_record = identity(receipt_path)
        receipt = json.loads(receipt_path.read_text())
        spec = cases[case]
        if (receipt.get('status') != 'SUCCESS' or receipt.get('case') != case
            or receipt.get('group') != NEW_ARMS[case] or receipt.get('alpha') != NEW_ALPHAS[case]
            or receipt.get('common_plan_sha256') != common_record['sha256']
            or receipt.get('selection_plan_sha256') != plan_record['sha256']
            or receipt.get('staged_inputs_unchanged') is not True
            or receipt.get('source_unchanged') is not True
            or receipt.get('common_plan_unchanged_after_run') is not True
            or receipt.get('launch_scripts_sha256') != launch_scripts
            or receipt.get('histories') != expected_histories
            or set(receipt.get('output_sha256', {})) != set(expected_histories)
            or receipt.get('preflight_case_sha256') != spec.get('staged_sha256')
            or receipt.get('staged_sha256_after') != spec.get('staged_sha256')):
            raise ValueError(f'{case}: fine runtime case receipt failed validation')
        run_dir = Path(receipt['scratch_directory'])
        if str(run_dir) != spec.get('scratch_directory'):
            raise ValueError(f'{case}: scratch directory differs from frozen plan')
        if {name: sha256(run_dir / name) for name in spec['staged_sha256']} != spec['staged_sha256']:
            raise ValueError(f'{case}: staged source files changed after the run')
        for name in expected_histories:
            history_path = run_dir / name
            if sha256(history_path) != receipt['output_sha256'][name]:
                raise ValueError(f'{case}/{name}: forecast history hash mismatch')
        runs[case] = run_dir
        records.append(receipt_record)
    return runs, records, common_record


def score_fine(runtime_dir, output, plan_path=PLAN_PATH, plan_sha256=PLAN_SHA256,
               prior_analysis=PRIOR_ANALYSIS, common_plan_sha256=COMMON_PLAN_SHA256):
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError(f'refusing to replace existing analysis output: {output}')
    plan_record, plan = check_selection_plan(plan_path, plan_sha256)
    prior_receipt, arrays, prior_records = load_prior_analysis(prior_analysis)
    runs, runtime_records, common_record = check_runtime(
        runtime_dir, plan_record, common_plan_sha256)
    if sha256(PRIOR_TOOL) != PRIOR_TOOL_SHA256:
        raise ValueError('pinned prior scorer source changed')
    extension = load_module('pinned_snow_extension', PRIOR_TOOL)
    old_tool = extension.load_prior_tool()
    scorer = old_tool.load_prior_scorer().load_scorer()
    runtime_plan = json.loads((Path(runtime_dir) / 'common_plan.json').read_text())
    source_records = old_tool.check_plan_sources(runtime_plan)
    inventory, mask, lat, lon, _ = scorer.evaluator.load_reference(
        old_tool.DEFAULT_REFERENCE_DIR, old_tool.DEFAULT_ANALYSIS_DIR)
    first = arrays[HOURS[0]]
    if (int(mask.sum()) != POINTS or not np.array_equal(np.flatnonzero(mask), first['flat_index_yx'])
        or not np.array_equal(lat[mask], first['latitude'])
        or not np.array_equal(lon[mask], first['longitude'])):
        raise ValueError('sealed paired arrays differ from the pinned RN1 reference cohort')
    extension.CASE_ORDER = CONTEXT_CASES
    extension.ELIGIBLE_CASES = ELIGIBLE_CASES
    extension.ALPHA_BY_CASE.update(NEW_ALPHAS)
    extension.ARM_BY_CASE.update(NEW_ARMS)
    combined, histories, mapping, resets = extension.add_extension_arrays(
        arrays, runs, scorer, scorer, inventory, mask, lat, lon)
    categorical, continuous = [], []
    for hour in HOURS:
        cat_rows, cont_rows = extension.score_hour(hour, combined[hour], scorer)
        categorical.extend(cat_rows)
        continuous.extend(cont_rows)
    extension.validate_score_rows(categorical, continuous)
    selected_rows, selection = extension.select_case(categorical, continuous, ELIGIBLE_CASES)
    errors = extension.pooled_error_summary(combined)
    selection.update({
        'selection_plan': plan_record,
        'context_only_cases': ['CURRENT_HYDRO'],
        'prior_known_selection': prior_receipt['selection']['selected_case'],
        'completed_candidate_count': len(selected_rows),
        'errors_reported_without_veto': errors,
        'pooled_error_changes_vs_IMPROVED_BG_FIXED': extension.pooled_error_changes(errors),
        'same_event_selection_limitation': 'All 30 candidates use the same event; this is diagnostic selection, not independent validation.',
        'initialization_limitation': 'QSNOW-only initial-water sensitivity is diagnostic and does not claim conservative or operational initialization.',
        'precipitation_limitation': 'Scores total surface precipitation, not surface snowfall alone.'})
    inputs = [identity(Path(__file__)), identity(PRIOR_TOOL), identity(extension.PRIOR_TOOL),
              identity(old_tool.PRIOR_SCORER_PATH), plan_record, common_record,
              *prior_records, *runtime_records,
              *source_records, *histories]
    scorer.verify_records(inputs)
    output.mkdir(parents=True, exist_ok=False)
    try:
        for hour, values in combined.items():
            np.savez_compressed(output / f'hour_{hour}_arrays.npz', **values)
        extension.write_csv(output / 'categorical_scores.csv', categorical)
        extension.write_csv(output / 'continuous_scores.csv', continuous)
        extension.write_csv(output / 'selection_scores.csv', selected_rows)
        (output / 'selection.json').write_text(json.dumps(selection, indent=2, allow_nan=False) + '\n')
        scorer.verify_records(inputs)
        artifacts = {path.name: {'sha256': sha256(path), 'size_bytes': path.stat().st_size}
                     for path in sorted(output.iterdir())}
        receipt = {
            'status': 'COMPLETE', 'cases': list(CONTEXT_CASES),
            'eligible_cases': list(ELIGIBLE_CASES), 'context_only_cases': ['CURRENT_HYDRO'],
            'runtime_case_status': {case: 'SUCCESS' for case in NEW_CASES},
            'alpha_by_case': {case: extension.ALPHA_BY_CASE[case] for case in ELIGIBLE_CASES
                              if case in extension.ALPHA_BY_CASE},
            'hours_utc': list(HOURS), 'points_per_hour': POINTS,
            'thresholds_mm': list(THRESHOLDS),
            'row_counts': {'categorical': len(categorical), 'continuous': len(continuous),
                           'selection_ranked': len(selected_rows)},
            'selection': selection, 'errors_reported_without_veto': errors,
            'reset_checks': resets, 'mapping_residual_max_deg': mapping['residual_max_deg'],
            'prior_analysis_receipt': identity(Path(prior_analysis) / 'receipt.json'),
            'runtime_plan': common_record,
            'runtime_case_receipts': {case: identity(Path(runtime_dir) / 'cases' / case / 'receipt.json')
                                      for case in NEW_CASES},
            'sources': inputs, 'analysis_outputs': artifacts}
        (output / 'receipt.json').write_text(json.dumps(receipt, indent=2, allow_nan=False) + '\n')
        return receipt
    except BaseException:
        shutil.rmtree(output)
        raise


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-dir', type=Path, default=RUNTIME_DIR)
    parser.add_argument('--plan', type=Path, default=PLAN_PATH)
    parser.add_argument('--plan-sha256', default=PLAN_SHA256)
    parser.add_argument('--common-plan-sha256', default=COMMON_PLAN_SHA256)
    parser.add_argument('--prior-analysis', type=Path, default=PRIOR_ANALYSIS)
    parser.add_argument('--output', type=Path, default=EVIDENCE_DIR / 'analysis')
    args = parser.parse_args()
    result = score_fine(args.runtime_dir, args.output, args.plan, args.plan_sha256,
                        args.prior_analysis, args.common_plan_sha256)
    print(json.dumps({'status': result['status'], 'selection': result['selection']}, indent=2))
