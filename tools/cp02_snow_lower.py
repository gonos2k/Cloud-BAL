#!/usr/bin/env python3
"""Score the lower-factor QSNOW sensitivity extension."""

import csv
import hashlib
import importlib.util
import json
import math
import shutil
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT / 'docs/evidence/snow_lower_20261030'
RUNTIME_DIR = EVIDENCE_DIR / 'runtime'
PLAN_PATH = EVIDENCE_DIR / 'selection_plan.json'
PLAN_SHA256 = '8d30f3f7a3d82a34332013334d5f0d6c66f1a1576198db228b98b1a89c950cf2'
PRIOR_ANALYSIS = ROOT / 'docs/evidence/snow_fine_20261030/analysis'
PRIOR_RECEIPT_SHA256 = '62519a61700aa106419517a2acb4b31c50dd5c1f8860cdadf6c7314e65c948ae'
PRIOR_HALF_ANALYSIS = ROOT / 'docs/evidence/snow_sensitivity_20261030/analysis'
PRIOR_HALF_RECEIPT_SHA256 = '18e2d82c3be0120b2da0e34fec75c12d6da52ddbfc28eaffb19781e94153e7ec'
PRIOR_HALF_COMMON_SHA256 = '3fb0c6c4a2770394a7ed1a4cd690cd61767c3f886deae9a0aa686f42bfb33a41'
PRIOR_HALF_PLAN_SHA256 = '1a5e236793f276ba9781664980ad37f79efa565038b17e0e90aa916fe953d6ef'
REUSED_HALF_CASES = ('CONTROL_SNOW_050', 'IMPROVED_SNOW_050')
PRIOR_FINE_TOOL = ROOT / 'tools/cp02_snow_fine.py'
PRIOR_FINE_TOOL_SHA256 = '7af0a40574d197a445d4c8c016e8a201dcbc6fe78578ef99c9d0e54da8b40410'
EXTENSION_TOOL = ROOT / 'tools/cp02_snow_extension.py'
EXTENSION_TOOL_SHA256 = 'b450747f0d376a353eff8c33da7ebbddfedc5d137fa9e53e0b37f0e71907da86'
SENSITIVITY_TOOL = ROOT / 'tools/cp02_snow_sensitivity.py'
COMMON_PLAN_SHA256 = '58dae266e4b4f893f5a9d940e30c8e38574823b03785e68b089811ef9d085871'
EXECUTABLE_SHA256 = {'CONTROL': 'de110a7f1d40143a74ffedbe64ed5b3717c413876093f56d200563e2f6b9c168',
                     'IMPROVED': '68ed2833b5f207d037949c9b20c7c2f800500e632f911a4acf1eb09d13bf1c1f'}
LEADS = tuple(range(1, 7))
HOURS = tuple(range(13, 19))
THRESHOLDS = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0)
POINTS = 3688
NEW_SUFFIXES = {'060': 0.6, '070': 0.7, '080': 0.8, '090': 0.9}
NEW_CASES = tuple(f'{arm}_SNOW_{suffix}' for arm in ('CONTROL', 'IMPROVED')
                  for suffix in NEW_SUFFIXES)
NEW_ALPHAS = {case: NEW_SUFFIXES[case.rsplit('_', 1)[1]] for case in NEW_CASES}
NEW_ARMS = {case: case.split('_', 1)[0] for case in NEW_CASES}
SNOW_SUFFIXES = {'000': 0.0, '025': 0.25, '050': 0.5, '060': 0.6,
                 '070': 0.7, '075': 0.75, '080': 0.8, '090': 0.9,
                 '110': 1.1, '120': 1.2, '130': 1.3, '140': 1.4,
                 '125': 1.25, '150': 1.5, '175': 1.75, '200': 2.0,
                 '250': 2.5, '300': 3.0}
ALPHA_BY_CASE = {f'{arm}_SNOW_{suffix}': alpha for arm in ('CONTROL', 'IMPROVED')
                 for suffix, alpha in SNOW_SUFFIXES.items()}
ARM_BY_CASE = {case: case.split('_', 1)[0] for case in ALPHA_BY_CASE}
ELIGIBLE_CASES = ('ORIGINAL', 'IMPROVED_BG_FIXED', *(
    f'{arm}_SNOW_{suffix}' for arm in ('CONTROL', 'IMPROVED')
    for suffix in ('000', '025', '050', '060', '070', '075', '080', '090', '125',
                   '150', '175', '200', '250', '300', '110', '120', '130', '140')))
CONTEXT_CASES = ('ORIGINAL', 'CURRENT_HYDRO', 'IMPROVED_BG_FIXED', *(
    f'{arm}_SNOW_{suffix}' for arm in ('CONTROL', 'IMPROVED')
    for suffix in ('000', '025', '050', '060', '070', '075', '080', '090', '125',
                   '150', '175', '200', '250', '300', '110', '120', '130', '140')))


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
    if not expected_sha256 or record['sha256'] != expected_sha256:
        raise ValueError('frozen lower-factor selection plan hash mismatch')
    plan = json.loads(Path(path).read_text())
    if (plan.get('status') != 'FROZEN_BEFORE_NEW_FORECAST_OUTPUTS_PRIOR_RESULTS_KNOWN'
        or plan.get('experiment', {}).get('families') != ['CONTROL', 'IMPROVED']
        or plan.get('experiment', {}).get('factor_codes') != list(NEW_SUFFIXES)
        or plan.get('experiment', {}).get('snow_factors') != list(NEW_SUFFIXES.values())
        or any(int(code) != round(100 * factor) for code, factor in NEW_SUFFIXES.items())
        or plan.get('experiment', {}).get('new_cases') != 8
        or plan.get('evaluation', {}).get('lead_hours') != list(LEADS)
        or plan.get('evaluation', {}).get('thresholds_mm') != list(THRESHOLDS)
        or plan.get('evaluation', {}).get('paired_points_per_hour') != POINTS
        or plan.get('evaluation', {}).get('primary_lead_hour') != 1
        or plan.get('evaluation', {}).get('primary_threshold_mm') != 10.0
        or plan.get('selection', {}).get('undefined_scores') !=
        'Undefined CSI ranks below defined CSI; undefined FAR after defined FAR. Do not replace undefined metrics with zero.'
        or plan.get('selection', {}).get('numerical_comparison_tolerance') != 0.0):
        raise ValueError('lower-factor selection plan contract mismatch')
    expected_order = ['descending lead-1-hour CSI at 10 mm',
                      'descending lead-1-hour CSI at 5 mm',
                      'ascending lead-1-hour FAR at 10 mm',
                      'ascending lead-1-hour RMSE',
                      'ascending absolute snow-factor deviation from 1',
                      'ascending case ID']
    if plan.get('selection', {}).get('ranking_order') != expected_order:
        raise ValueError('lower-factor selection ranking changed')
    return record, plan


def load_prior_analysis(path=PRIOR_ANALYSIS):
    path = Path(path)
    receipt_path = path / 'receipt.json'
    if sha256(receipt_path) != PRIOR_RECEIPT_SHA256:
        raise ValueError('sealed fine-factor analysis receipt pin changed')
    receipt = json.loads(receipt_path.read_text())
    if (receipt.get('status') != 'COMPLETE' or len(receipt.get('cases', [])) != 31
        or len(receipt.get('eligible_cases', [])) != 30
        or set(receipt.get('context_only_cases', [])) != {'CURRENT_HYDRO'}):
        raise ValueError('sealed fine-factor analysis scope is incomplete')
    source_hashes = {Path(row['path']).name: row['sha256'] for row in receipt.get('sources', [])}
    if (source_hashes.get(PRIOR_FINE_TOOL.name) != PRIOR_FINE_TOOL_SHA256
        or source_hashes.get(EXTENSION_TOOL.name) != EXTENSION_TOOL_SHA256
        or sha256(PRIOR_FINE_TOOL) != PRIOR_FINE_TOOL_SHA256
        or sha256(EXTENSION_TOOL) != EXTENSION_TOOL_SHA256):
        raise ValueError('sealed fine-factor scorer source pins changed')
    outputs = receipt.get('analysis_outputs')
    if not isinstance(outputs, dict):
        raise ValueError('sealed fine-factor artifact manifest is missing')
    arrays = {}
    for hour in HOURS:
        artifact = path / f'hour_{hour}_arrays.npz'
        if sha256(artifact) != outputs.get(artifact.name, {}).get('sha256'):
            raise ValueError(f'{hour}: sealed fine-factor array hash mismatch')
        with np.load(artifact, allow_pickle=False) as data:
            values = {key: np.array(data[key]) for key in data.files}
        if set(values) != set(receipt['cases']) | {'reference', 'latitude', 'longitude', 'flat_index_yx'}:
            raise ValueError(f'{hour}: sealed fine-factor array scope mismatch')
        if any(value.shape != (POINTS,) or not np.isfinite(value).all()
               for value in values.values()):
            raise ValueError(f'{hour}: sealed fine-factor arrays are invalid')
        arrays[hour] = values
    for name in ('categorical_scores.csv', 'continuous_scores.csv', 'selection_scores.csv',
                 'selection.json'):
        artifact = path / name
        if sha256(artifact) != outputs.get(name, {}).get('sha256'):
            raise ValueError(f'sealed fine-factor table hash mismatch: {name}')
    records = [identity(receipt_path)]
    records.extend(identity(path / name) for name in
                   [*(f'hour_{hour}_arrays.npz' for hour in HOURS),
                    'categorical_scores.csv', 'continuous_scores.csv',
                    'selection_scores.csv', 'selection.json'])
    return receipt, arrays, records


def validate_reused_common_baseline(prior_common, current_common):
    """Require reused forecasts and new forecasts to share physics inputs."""
    exact_pins = (
        'fixed_executable_sha256', 'original_executable_sha256',
        'improved_wrfinput_sha256', 'original_wrfinput_sha256',
        'original_source_wrfinput_sha256_before',
        'common_boundary_sha256', 'common_six_hour_namelist_sha256',
        'native_metadata_contract_sha256', 'source_b1_input_sha256_before',
        'original_source_sha256_before', 'source_field_value_sha256',
    )
    for name in exact_pins:
        if prior_common.get(name) != current_common.get(name):
            raise ValueError(f'reused 0.5 cases do not match current runtime baseline: {name}')


def check_reused_half_runs(analysis_dir=PRIOR_HALF_ANALYSIS,
                           current_common_path=RUNTIME_DIR / 'common_plan.json'):
    """Verify both reused 0.5 runtime runs against their sealed source plan."""
    analysis_dir = Path(analysis_dir)
    analysis_receipt_path = analysis_dir / 'receipt.json'
    if sha256(analysis_receipt_path) != PRIOR_HALF_RECEIPT_SHA256:
        raise ValueError('sealed 0.5-case analysis receipt pin changed')
    analysis_receipt = json.loads(analysis_receipt_path.read_text())
    common_pin = analysis_receipt.get('common_plan', {})
    common_path = Path(common_pin.get('path', ''))
    common_record = identity(common_path)
    if (common_record['sha256'] != PRIOR_HALF_COMMON_SHA256
        or common_pin.get('sha256') != PRIOR_HALF_COMMON_SHA256):
        raise ValueError('sealed 0.5-case common-plan pin changed')
    common = json.loads(common_path.read_text())
    if (common.get('selection_plan_sha256') != PRIOR_HALF_PLAN_SHA256
        or common.get('case_count') != 12 or common.get('original_native_variable_count') != 208
        or common.get('declared_input_count_per_case') != 89):
        raise ValueError('sealed 0.5-case runtime plan scope or plan pin changed')
    current_common_path = Path(current_common_path)
    current_common_record = identity(current_common_path)
    if current_common_record['sha256'] != COMMON_PLAN_SHA256:
        raise ValueError('current lower-factor common-plan pin is missing or mismatched')
    validate_reused_common_baseline(common, json.loads(current_common_path.read_text()))
    source_snapshot = {
        'B1': common['source_b1_input_sha256_before'],
        'ORIGINAL': common['original_source_sha256_before'],
        'evidence': common['source_evidence_sha256_before'],
    }
    expected_histories = [f'wrfout_d01_2026-08-16_{hour:02d}:00:00' for hour in range(12, 19)]
    records = [identity(analysis_receipt_path), common_record, current_common_record]
    case_receipts = {}
    for case in REUSED_HALF_CASES:
        pin = analysis_receipt.get('runtime_case_receipts', {}).get(case)
        if not isinstance(pin, dict):
            raise ValueError(f'{case}: reused case receipt pin is missing')
        receipt_path = Path(pin['path'])
        receipt_record = identity(receipt_path)
        if receipt_record['sha256'] != pin.get('sha256'):
            raise ValueError(f'{case}: reused case receipt hash mismatch')
        receipt = json.loads(receipt_path.read_text())
        arm = case.split('_', 1)[0]
        spec = common.get('case_records', {}).get(case, {})
        staged = spec.get('staged_sha256', {})
        if (receipt.get('status') != 'SUCCESS' or receipt.get('case') != case
            or receipt.get('group') != arm or receipt.get('alpha') != 0.5
            or receipt.get('selection_plan_sha256') != PRIOR_HALF_PLAN_SHA256
            or receipt.get('common_plan_sha256') != PRIOR_HALF_COMMON_SHA256
            or receipt.get('staged_inputs_unchanged') is not True
            or receipt.get('source_unchanged') is not True
            or receipt.get('common_plan_unchanged_after_run') is not True
            or receipt.get('source_sha256_before') != source_snapshot
            or receipt.get('source_sha256_after') != source_snapshot
            or receipt.get('histories') != expected_histories
            or receipt.get('launch_scripts_sha256') != common.get('launch_scripts_sha256')
            or receipt.get('preflight_case_sha256') != staged
            or receipt.get('staged_sha256_after') != staged
            or spec.get('alpha') != 0.5 or spec.get('group') != arm):
            raise ValueError(f'{case}: reused runtime receipt does not match its sealed plan')
        run_dir = Path(receipt.get('scratch_directory', ''))
        if str(run_dir) != spec.get('scratch_directory'):
            raise ValueError(f'{case}: reused scratch directory differs from its sealed plan')
        if {name: sha256(run_dir / name) for name in staged} != staged:
            raise ValueError(f'{case}: reused staged input hashes changed')
        output_hashes = receipt.get('output_sha256', {})
        if set(output_hashes) != set(expected_histories):
            raise ValueError(f'{case}: reused runtime history set is incomplete')
        for name in expected_histories:
            record = identity(run_dir / name)
            if record['sha256'] != output_hashes[name]:
                raise ValueError(f'{case}/{name}: reused runtime history hash mismatch')
            records.append(record)
        records.extend(identity(run_dir / name) for name in staged)
        records.append(receipt_record)
        case_receipts[case] = receipt_record
    return {'analysis_receipt': identity(analysis_receipt_path),
            'common_plan': common_record, 'current_common_plan': current_common_record,
            'case_receipts': case_receipts}, records


def check_runtime(runtime_dir, plan_record, expected_common_sha256=COMMON_PLAN_SHA256):
    runtime_dir = Path(runtime_dir)
    common_path = runtime_dir / 'common_plan.json'
    common_record = identity(common_path)
    if expected_common_sha256 is None or not expected_common_sha256 or common_record['sha256'] != expected_common_sha256:
        raise ValueError('lower-factor runtime common-plan pin is missing or mismatched')
    common = json.loads(common_path.read_text())
    if (common.get('status') != 'PASS_READY_TO_LAUNCH'
        or common.get('selection_plan_sha256') != plan_record['sha256']
        or common.get('case_count') != len(NEW_CASES)
        or common.get('declared_input_count_per_case') != 89
        or common.get('original_native_variable_count') != 208
        or common.get('all_native_metadata_unchanged') is not True
        or set(common.get('case_records', {})) != set(NEW_CASES)):
        raise ValueError('lower-factor runtime common plan has incomplete scope or wrong selection pin')
    slots = common.get('cpu_affinity', {}).get('slots', {})
    slot_cases = common.get('cpu_affinity', {}).get('slot_cases', {})
    if len(slots) != 8 or len(slot_cases) != 8:
        raise ValueError('lower-factor runtime CPU slot plan is incomplete')
    cases = common['case_records']
    field_sources = common.get('source_field_value_sha256', {})
    field_cases = common.get('case_field_value_sha256', {})
    source_inputs = {'CONTROL': common.get('original_source_sha256_before', {}),
                     'IMPROVED': common.get('source_b1_input_sha256_before', {})}
    if (set(field_sources) != {'CONTROL', 'IMPROVED'} or set(field_cases) != set(NEW_CASES)
        or any(len(field_sources[arm]) != 208 for arm in field_sources)
        or any(len(source_inputs[arm]) != 89 for arm in source_inputs)):
        raise ValueError('lower-factor runtime source or native field manifests are incomplete')
    all_cpus, assigned_cases = [], []
    for case in NEW_CASES:
        row = cases[case]
        slot = str(row.get('slot'))
        arm, alpha = NEW_ARMS[case], NEW_ALPHAS[case]
        staged, audit = row.get('staged_sha256', {}), row.get('qsnow_audit', {})
        base_inputs = source_inputs[arm]
        expected_staged_names = (set(base_inputs) - {'namelist.output', 'wrf.exe'}) | {'wrf.exe'}
        if (row.get('case') != case or row.get('group') != arm or row.get('alpha') != alpha
            or not row.get('scratch_directory') or not isinstance(staged, dict)
            or set(staged) != expected_staged_names or slot not in slots
            or row.get('cpu_set') != slots[slot] or case not in slot_cases.get(slot, [])
            or staged.get('wrf.exe') != EXECUTABLE_SHA256[arm]
            or staged.get('wrfinput_d01') == base_inputs.get('wrfinput_d01')
            or staged.get('wrfbdy_d01') != common.get('common_boundary_sha256')
            or staged.get('namelist.input') != common.get('common_six_hour_namelist_sha256')
            or any(staged.get(name) != digest for name, digest in base_inputs.items()
                   if name not in ('namelist.output', 'wrf.exe', 'wrfinput_d01'))):
            raise ValueError(f'{case}: lower-factor runtime staged case contract failed')
        if (audit.get('group') != arm or audit.get('alpha') != alpha
            or audit.get('scaling_rule') != 'float64(source QSNOW) * float64(alpha), then cast to native float32'
            or audit.get('dtype') != 'float32' or audit.get('variable_count') != 208
            or audit.get('other_variables_unchanged') is not True
            or audit.get('all_native_metadata_unchanged') is not True
            or audit.get('finite') is not True or audit.get('nonnegative') is not True
            or audit.get('source_input_sha256') != base_inputs.get('wrfinput_d01')
            or audit.get('source_qsnow_value_sha256') != field_sources[arm].get('QSNOW')
            or audit.get('native_metadata_contract_sha256') != common.get('native_metadata_contract_sha256')):
            raise ValueError(f'{case}: lower-factor QSNOW-only input audit failed')
        fields = field_cases[case]
        if (set(fields) != set(field_sources[arm]) or len(fields) != 208
            or fields.get('QSNOW') != audit.get('scaled_qsnow_value_sha256')
            or any(fields[name] != field_sources[arm][name] for name in field_sources[arm]
                   if name != 'QSNOW')):
            raise ValueError(f'{case}: native field hashes do not prove a sole-QSNOW change')
    for slot, cpus in slots.items():
        if len(cpus) != 8 or len(set(cpus)) != 8:
            raise ValueError('lower-factor runtime CPU slot must contain eight unique CPUs')
        all_cpus.extend(cpus)
        assigned_cases.extend(slot_cases.get(slot, []))
    if (len(set(all_cpus)) != len(all_cpus) or not set(all_cpus).issubset(
            set(common.get('cpu_affinity', {}).get('allowed_cpus', [])))
        or set(assigned_cases) != set(NEW_CASES) or len(assigned_cases) != len(NEW_CASES)):
        raise ValueError('lower-factor runtime CPU slots overlap or omit/duplicate cases')
    launch_scripts = common.get('launch_scripts_sha256')
    if not isinstance(launch_scripts, dict) or not launch_scripts:
        raise ValueError('lower-factor runtime launch script pins are missing')
    launch_records = []
    for name, expected in launch_scripts.items():
        record = identity(runtime_dir / name)
        if record['sha256'] != expected:
            raise ValueError(f'lower-factor runtime launch script changed: {name}')
        launch_records.append(record)
    launch_manifest = runtime_dir / 'launch_scripts.sha256.json'
    if json.loads(launch_manifest.read_text()) != launch_scripts:
        raise ValueError('lower-factor runtime launch manifest differs from common plan')

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
        raise ValueError('lower-factor runtime receipts are incomplete or not mutually bound')
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
            raise ValueError(f'{case}: lower-factor runtime case receipt failed validation')
        run_dir = Path(receipt['scratch_directory'])
        if str(run_dir) != spec.get('scratch_directory'):
            raise ValueError(f'{case}: scratch directory differs from frozen plan')
        if {name: sha256(run_dir / name) for name in spec['staged_sha256']} != spec['staged_sha256']:
            raise ValueError(f'{case}: staged source files changed after the run')
        for name in expected_histories:
            if sha256(run_dir / name) != receipt['output_sha256'][name]:
                raise ValueError(f'{case}/{name}: forecast history hash mismatch')
        runs[case] = run_dir
        records.append(receipt_record)
    return runs, records, common_record


def comparison_rows(categorical):
    by_key = {(row['case'], row['lead_hour'], row['threshold_mm']): row for row in categorical}
    rows = []
    for case in ELIGIBLE_CASES:
        for lead in LEADS:
            for threshold in THRESHOLDS:
                candidate = by_key[(case, lead, threshold)]
                baseline = by_key[('ORIGINAL', lead, threshold)]
                rows.append({
                    'case': case, 'baseline_case': 'ORIGINAL',
                    'lead_hour': lead, 'threshold_mm': threshold,
                    'CSI': candidate['CSI'], 'baseline_CSI': baseline['CSI'],
                    'delta_CSI_vs_ORIGINAL': (None if candidate['CSI'] is None or baseline['CSI'] is None
                                              else candidate['CSI'] - baseline['CSI']),
                    'FAR': candidate['FAR'], 'baseline_FAR': baseline['FAR'],
                    'delta_FAR_vs_ORIGINAL': (None if candidate['FAR'] is None or baseline['FAR'] is None
                                              else candidate['FAR'] - baseline['FAR']),
                })
    if len(rows) != len(ELIGIBLE_CASES) * len(LEADS) * len(THRESHOLDS):
        raise ValueError('comparison table does not cover the complete eligible score grid')
    return rows


def hourly_differences_vs_original(values):
    """Return paired pointwise hourly precipitation differences in mm."""
    baseline = np.asarray(values['ORIGINAL'], dtype=np.float64)
    if baseline.shape != (POINTS,) or not np.isfinite(baseline).all():
        raise ValueError('ORIGINAL comparison baseline must contain 3688 finite points')
    differences = {
        'reference': np.asarray(values['reference'], dtype=np.float64),
        'flat_index_yx': np.asarray(values['flat_index_yx'], dtype=np.int64),
        'latitude': np.asarray(values['latitude'], dtype=np.float64),
        'longitude': np.asarray(values['longitude'], dtype=np.float64),
    }
    if (differences['reference'].shape != (POINTS,)
        or not np.isfinite(differences['reference']).all()
        or differences['flat_index_yx'].shape != (POINTS,)
        or differences['latitude'].shape != (POINTS,)
        or differences['longitude'].shape != (POINTS,)
        or not np.isfinite(differences['latitude']).all()
        or not np.isfinite(differences['longitude']).all()):
        raise ValueError('pointwise comparison cohort coordinates are invalid')
    for case in CONTEXT_CASES:
        forecast = np.asarray(values[case], dtype=np.float64)
        if forecast.shape != (POINTS,) or not np.isfinite(forecast).all():
            raise ValueError(f'{case}: comparison forecast must contain 3688 finite points')
        differences[case] = forecast - baseline
    if not np.array_equal(differences['ORIGINAL'], np.zeros(POINTS, dtype=np.float64)):
        raise ValueError('ORIGINAL pointwise precipitation difference must be zero')
    return differences


def validate_candidate_metadata():
    expected_cases = set(ELIGIBLE_CASES) - {'ORIGINAL', 'IMPROVED_BG_FIXED'}
    if set(ALPHA_BY_CASE) != expected_cases or set(ARM_BY_CASE) != expected_cases:
        raise ValueError('lower-factor candidate metadata does not cover the exact eligible snow cases')
    for case in expected_cases:
        arm, suffix = case.split('_SNOW_')
        if ALPHA_BY_CASE[case] != SNOW_SUFFIXES[suffix] or ARM_BY_CASE[case] != arm:
            raise ValueError(f'{case}: candidate family or QSNOW factor metadata is incorrect')


def select_lower_case(categorical, continuous):
    """Rank all eligible cases using the frozen lead-one-only ordering."""
    categories = {(int(row['lead_hour']), row['case'], float(row['threshold_mm'])): row
                  for row in categorical}
    continuous_by_case = {(int(row['lead_hour']), row['case']): row for row in continuous}
    if len(categories) != len(categorical) or len(continuous_by_case) != len(continuous):
        raise ValueError('duplicate score row before lower-factor selection')

    def finite_or_none(value):
        if value is None or value == '':
            return None
        value = float(value)
        return value if math.isfinite(value) else None

    rows = []
    for case in ELIGIBLE_CASES:
        key_csi10, key_csi5 = (1, case, 10.0), (1, case, 5.0)
        key_cont = (1, case)
        if key_csi10 not in categories or key_csi5 not in categories or key_cont not in continuous_by_case:
            raise ValueError(f'{case}: selection is missing first-hour criteria')
        csi10 = finite_or_none(categories[key_csi10]['CSI'])
        csi5 = finite_or_none(categories[key_csi5]['CSI'])
        far10 = finite_or_none(categories[key_csi10]['FAR'])
        rmse = finite_or_none(continuous_by_case[key_cont]['RMSE_mm'])
        if case == 'ORIGINAL':
            alpha, arm, factor_code = 1.0, 'CONTROL', 100
        elif case == 'IMPROVED_BG_FIXED':
            alpha, arm, factor_code = 1.0, 'IMPROVED', 100
        else:
            alpha, arm = ALPHA_BY_CASE[case], ARM_BY_CASE[case]
            factor_code = int(case.rsplit('_', 1)[1])
        distance_code = abs(factor_code - 100)
        rows.append({
            'case': case, 'arm': arm, 'alpha': alpha,
            'lead1_CSI_at_10mm': csi10, 'lead1_CSI_at_5mm': csi5,
            'lead1_FAR_at_10mm': far10, 'lead1_RMSE_mm': rmse,
            'abs_alpha_distance_from_1': distance_code / 100.0,
            '_distance_code': distance_code,
        })

    def ranking_key(row):
        return (
            row['lead1_CSI_at_10mm'] is None,
            -row['lead1_CSI_at_10mm'] if row['lead1_CSI_at_10mm'] is not None else 0.0,
            row['lead1_CSI_at_5mm'] is None,
            -row['lead1_CSI_at_5mm'] if row['lead1_CSI_at_5mm'] is not None else 0.0,
            row['lead1_FAR_at_10mm'] is None,
            row['lead1_FAR_at_10mm'] if row['lead1_FAR_at_10mm'] is not None else 0.0,
            row['lead1_RMSE_mm'] is None,
            row['lead1_RMSE_mm'] if row['lead1_RMSE_mm'] is not None else 0.0,
            row['_distance_code'], row['case'])

    rows.sort(key=ranking_key)
    for index, row in enumerate(rows, 1):
        row['rank'] = index
        del row['_distance_code']
    selection = {
        'selected_case': rows[0]['case'], 'selected_alpha': rows[0]['alpha'],
        'selection_order': [row['case'] for row in rows],
        'ranking_order': ['descending +1h CSI at 10 mm',
                          'descending +1h CSI at 5 mm',
                          'ascending +1h FAR at 10 mm',
                          'ascending +1h RMSE',
                          'ascending absolute snow-factor deviation from 1',
                          'ascending case ID'],
        'alpha_distance_method': ('Exact integer factor-code distance abs(code - 100), '
                                  'equivalent to abs(alpha - 1) because code = 100 * alpha; '
                                  'zero tolerance, no floating-point distance comparison.'),
        'eligibility': f'all {len(rows)} completed eligible cases ranked; forecast-error metrics are tie-breaks, not vetoes; failed/incomplete cases excluded'}
    return rows, selection


def write_csv(path, rows):
    if not rows:
        raise ValueError(f'cannot write empty CSV: {path}')
    with Path(path).open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def score_lower(runtime_dir, output, plan_path=PLAN_PATH, plan_sha256=PLAN_SHA256,
                prior_analysis=PRIOR_ANALYSIS, common_plan_sha256=COMMON_PLAN_SHA256):
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError(f'refusing to replace existing analysis output: {output}')
    plan_record, plan = check_selection_plan(plan_path, plan_sha256)
    prior_receipt, arrays, prior_records = load_prior_analysis(prior_analysis)
    reused_half_runs, reused_half_records = check_reused_half_runs()
    runs, runtime_records, common_record = check_runtime(runtime_dir, plan_record, common_plan_sha256)
    if sha256(PRIOR_FINE_TOOL) != PRIOR_FINE_TOOL_SHA256 or sha256(EXTENSION_TOOL) != EXTENSION_TOOL_SHA256:
        raise ValueError('pinned prior scorer source changed')
    extension = load_module('pinned_snow_extension', EXTENSION_TOOL)
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
    validate_candidate_metadata()
    extension.CASE_ORDER = CONTEXT_CASES
    extension.ELIGIBLE_CASES = ELIGIBLE_CASES
    extension.ALPHA_BY_CASE.update(ALPHA_BY_CASE)
    extension.ARM_BY_CASE.update(ARM_BY_CASE)
    combined, histories, mapping, resets = extension.add_extension_arrays(
        arrays, runs, scorer, scorer, inventory, mask, lat, lon)
    categorical, continuous = [], []
    for hour in HOURS:
        cat_rows, cont_rows = extension.score_hour(hour, combined[hour], scorer)
        categorical.extend(cat_rows)
        continuous.extend(cont_rows)
    extension.validate_score_rows(categorical, continuous)
    selected_rows, selection = select_lower_case(categorical, continuous)
    errors = extension.pooled_error_summary(combined)
    comparisons = comparison_rows(categorical)
    pointwise_differences = {hour: hourly_differences_vs_original(combined[hour])
                             for hour in HOURS}
    selection.update({
        'selection_plan': plan_record,
        'context_only_cases': ['CURRENT_HYDRO'],
        'comparison_baseline': 'ORIGINAL (CONTROL QSNOW alpha=1.0)',
        'comparison_metric': 'same-lead/same-threshold CSI difference from ORIGINAL',
        'prior_known_selection': prior_receipt['selection']['selected_case'],
        'completed_candidate_count': len(selected_rows),
        'errors_reported_without_veto': errors,
        'pooled_error_changes_vs_IMPROVED_BG_FIXED': extension.pooled_error_changes(errors),
        'same_event_selection_limitation': 'All 38 candidates use the same event; this is diagnostic selection, not independent validation.',
        'initialization_limitation': 'QSNOW-only initial-water sensitivity is diagnostic and does not claim conservative or operational initialization.',
        'precipitation_limitation': 'Scores total surface precipitation, not surface snowfall alone.'})
    inputs = [identity(Path(__file__)), identity(PRIOR_FINE_TOOL), identity(EXTENSION_TOOL),
              identity(SENSITIVITY_TOOL),
              identity(old_tool.PRIOR_SCORER_PATH),
              plan_record, common_record, *prior_records, *reused_half_records, *runtime_records,
              *source_records, *histories]
    scorer.verify_records(inputs)
    output.mkdir(parents=True, exist_ok=False)
    try:
        for hour, values in combined.items():
            np.savez_compressed(output / f'hour_{hour}_arrays.npz', **values)
        extension.write_csv(output / 'categorical_scores.csv', categorical)
        extension.write_csv(output / 'continuous_scores.csv', continuous)
        extension.write_csv(output / 'selection_scores.csv', selected_rows)
        write_csv(output / 'comparison_vs_original.csv', comparisons)
        for hour, differences in pointwise_differences.items():
            np.savez_compressed(output / f'hour_{hour}_difference_vs_original.npz', **differences)
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
                           'selection_ranked': len(selected_rows), 'comparison_vs_original': len(comparisons),
                           'pointwise_difference_arrays': len(pointwise_differences)},
            'selection': selection, 'comparison_baseline': 'ORIGINAL',
            'pointwise_comparison': {'baseline_case': 'ORIGINAL',
                                    'difference': 'candidate hourly total precipitation minus ORIGINAL',
                                    'cases': len(CONTEXT_CASES), 'unit': 'mm',
                                    'points_per_case_lead': POINTS,
                                    'coordinates': ['flat_index_yx', 'latitude', 'longitude']},
            'selection_distance_method': selection['alpha_distance_method'],
            'errors_reported_without_veto': errors,
            'reset_checks': resets, 'mapping_residual_max_deg': mapping['residual_max_deg'],
            'prior_analysis_receipt': identity(Path(prior_analysis) / 'receipt.json'),
            'reused_0_5_runtime_pins': reused_half_runs,
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
    result = score_lower(args.runtime_dir, args.output, args.plan, args.plan_sha256,
                         args.prior_analysis, args.common_plan_sha256)
    print(json.dumps({'status': result['status'], 'selection': result['selection']}, indent=2))
