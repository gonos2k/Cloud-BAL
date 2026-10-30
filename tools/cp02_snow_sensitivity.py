#!/usr/bin/env python3
"""Paired six-hour scoring for the frozen QSNOW sensitivity sweep."""
import csv
import hashlib
import importlib.util
import json
import math
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PRIOR_SCORER_PATH = ROOT / 'tools/cp02_six_hour_improvement.py'
PRIOR_SCORER_SHA = '03f276ba462d4d46523823b82dcd4f83a3367404bfb95d41f20dfa9c80688467'
ALPHAS = {'000': 0.0, '025': 0.25, '050': 0.5, '075': 0.75, '125': 1.25, '150': 1.5}
ALPHA_BY_CASE = {f'{arm}_SNOW_{suffix}': alpha
                 for arm in ('CONTROL', 'IMPROVED') for suffix, alpha in ALPHAS.items()}
ARM_BY_CASE = {case: case.split('_', 1)[0] for case in ALPHA_BY_CASE}
BASELINE_CASES = ('ORIGINAL', 'CURRENT_HYDRO', 'IMPROVED_BG_FIXED')
CASES = BASELINE_CASES + tuple(ALPHA_BY_CASE)
HOURS = tuple(range(13, 19))
THRESHOLDS = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0)
POINTS = 3688
EQUALITY_TOLERANCE = 1e-12
ELIGIBILITY_CSI_THRESHOLD_MM = 5.0
SIX_HOUR_ANALYSIS = ROOT / 'docs/evidence/six_hour_improvement_20261030/analysis'
SIX_HOUR_RECEIPT_SHA = '0db2f02ceece4d2f12cec459f5af26ca589b2f70c53c3d559b596b10828d8826'
SIX_HOUR_RUNTIME_RECEIPT = ROOT / 'docs/evidence/six_hour_improvement_20261030/runtime/receipt.json'
ORIGINAL_RUNTIME_RECEIPT = ROOT / 'docs/evidence/current_forecast_paper_20261029/runtime/original_hydro_completed_receipt.json'
SELECTION_PLAN = ROOT / 'docs/evidence/snow_sensitivity_20261030/selection_plan.json'
SELECTION_PLAN_SHA = '1a5e236793f276ba9781664980ad37f79efa565038b17e0e90aa916fe953d6ef'
OLD_EXE_SHA = 'de110a7f1d40143a74ffedbe64ed5b3717c413876093f56d200563e2f6b9c168'
ORIGINAL_INPUT_SHA = '5d6b2bdce4121642dea994f3e953cca690ad7c9f52f6f8feb01bb6c2f0b9b6bc'
FIXED_EXE_SHA = '68ed2833b5f207d037949c9b20c7c2f800500e632f911a4acf1eb09d13bf1c1f'
IMPROVED_INPUT_SHA = '9f8b494dbf5ce765e4320701475d6a65be1f591d72a4f9bf5e929c208be563e5'
BOUNDARY_SHA = '74102ac2063f17a9007f3352e6e6c2f52629055bdf3f05b4f4d6d77aef835f45'
SIX_HOUR_NAMELIST_SHA = 'eced598028b71b996c0c22cf7bd4bacb067087575ec06c4b65d71ab4913156df'
COMMON_PLAN = ROOT / 'docs/evidence/snow_sensitivity_20261030/runtime/common_plan.json'
COMMON_PLAN_SHA = '3fb0c6c4a2770394a7ed1a4cd690cd61767c3f886deae9a0aa686f42bfb33a41'
LAUNCH_SCRIPT_SHA = {
    'prepare_cases.py': '700b81a028f123e6d15ceef62ee865d3fc41b51098017c8232d18f164689512a',
    'run_case.py': 'ad7c199742278220b59d5273e454413f168703b70fd683ca65a3beb80c4ec979',
    'run_all.py': 'e2467c7ef501bd02a098a496d6bb81d11a3961378ba27772cd169769e93e5bda',
    'env.sh': 'f5ea8c614cc1f78eecd7b7b218c275ca97ae33a48e3fd6dadfc2d843be189be5',
}
LAUNCH_MANIFEST_SHA = '93d2a917da850db31a572520ed9a4f66340312a52214e1eea20b1154c7179da6'
B1_SOURCE_DIR = Path('/var/tmp/six-hour-improved-runtime-20261030/IMPROVED_BG_FIXED')
ORIGINAL_SOURCE_DIR = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/current_forecast_paper_20261029/run.PomEr8/original')
OLD_EXE_PATH = Path('/var/tmp/firsthour-runtime-plan-20261030/experiment/run_BASE_H/wrf.exe')
RUNTIME_EVIDENCE = ROOT / 'docs/evidence/snow_sensitivity_20261030/runtime'
EVIDENCE_DIR = ROOT / 'docs/evidence/snow_sensitivity_20261030'
DEFAULT_REFERENCE_DIR = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/Cloud-BAL/scratch/cp02_six_hour_20260914/reference')
DEFAULT_ANALYSIS_DIR = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/ANAL/NE57/DAOU/DFSD/20260816/klps_lc05_anal_20260816_1300')
DEFAULT_ODAM_DIR = Path('/NHNHOME/DATA/yhlee_data/ODAM/20260816')


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def identity(path):
    path = Path(path)
    return {'path': str(path), 'sha256': sha256(path), 'size': path.stat().st_size}


def load_prior_scorer():
    if sha256(PRIOR_SCORER_PATH) != PRIOR_SCORER_SHA:
        raise ValueError('pinned six-hour scorer changed')
    spec = importlib.util.spec_from_file_location('pinned_six_hour_improvement', PRIOR_SCORER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_selection_plan(path=SELECTION_PLAN):
    """Bind the selector to the immutable pre-output plan before reading scores."""
    record = identity(path)
    if record['sha256'] != SELECTION_PLAN_SHA:
        raise ValueError('frozen preregistered selection plan changed')
    plan = json.loads(Path(path).read_text())
    expected_thresholds = list(THRESHOLDS)
    if (plan.get('status') != 'FROZEN_BEFORE_CANDIDATE_FORECAST_OUTPUTS'
        or plan.get('base_commit') != 'e8f2e7e2c668672b5209a8cb142ca9d9d8e4138a'
        or plan.get('evaluation', {}).get('paired_points_per_hour') != POINTS
        or plan.get('evaluation', {}).get('thresholds_mm') != expected_thresholds
        or plan.get('selection', {}).get('reference_case') != 'IMPROVED_BG_FIXED'
        or plan.get('selection', {}).get('numerical_comparison_tolerance') != EQUALITY_TOLERANCE
        or plan.get('selection', {}).get('ranking_order', [])[-1:] != ['ascending case ID']):
        raise ValueError('frozen selection plan contract mismatch')
    return record, plan


def validate_case_plan_record(case, row, base_inputs, family_fields, case_fields,
                              metadata_sha256):
    """Check one cell's immutable executable/input identities and QSNOW-only field audit."""
    alpha, group = ALPHA_BY_CASE[case], ARM_BY_CASE[case]
    staged = row.get('staged_sha256')
    if (row.get('case') != case or row.get('group') != group or row.get('alpha') != alpha
        or not row.get('scratch_directory') or not isinstance(staged, dict) or len(staged) != 89):
        raise ValueError(f'{case}: plan cell identity or staged manifest is invalid')
    expected_exe = OLD_EXE_SHA if group == 'CONTROL' else FIXED_EXE_SHA
    expected_native = ORIGINAL_INPUT_SHA if group == 'CONTROL' else IMPROVED_INPUT_SHA
    if (staged.get('wrf.exe') != expected_exe or staged.get('wrfbdy_d01') != BOUNDARY_SHA
        or staged.get('namelist.input') != SIX_HOUR_NAMELIST_SHA
        or staged.get('wrfinput_d01') == expected_native):
        raise ValueError(f'{case}: wrong executable/input/boundary or missing QSNOW perturbation')
    if any(staged[name] != expected for name, expected in base_inputs.items()
           if name not in ('wrf.exe', 'wrfinput_d01')):
        raise ValueError(f'{case}: staged runtime changed a non-factor input')
    audit = row.get('qsnow_audit', {})
    if (audit.get('group') != group or audit.get('alpha') != alpha
        or audit.get('scaling_rule') != 'float64(source QSNOW) * float64(alpha), then cast to native float32'
        or audit.get('dtype') != 'float32' or audit.get('variable_count') != 208
        or audit.get('other_variables_unchanged') is not True
        or audit.get('all_native_metadata_unchanged') is not True
        or audit.get('finite') is not True or audit.get('nonnegative') is not True
        or audit.get('changed_value_count') is None or audit.get('total_value_count') is None
        or audit.get('source_input_sha256') != expected_native
        or audit.get('native_metadata_contract_sha256') != metadata_sha256):
        raise ValueError(f'{case}: native QSNOW perturbation audit failed')
    values, source_values = case_fields.get(case), family_fields.get(group)
    if (not isinstance(values, dict) or not isinstance(source_values, dict)
        or set(values) != set(source_values) or len(values) != 208
        or values.get('QSNOW') != audit.get('scaled_qsnow_value_sha256')
        or any(values[name] != source_values[name] for name in source_values if name != 'QSNOW')):
        raise ValueError(f'{case}: native QSNOW audit does not prove sole-variable perturbation')


def check_common_plan(path, expected_sha, expected_launch_scripts_sha=None):
    """Validate the frozen 12-cell prep plan before trusting any runtime receipts."""
    record = identity(path)
    if record['sha256'] != expected_sha:
        raise ValueError('frozen QSNOW common plan hash mismatch')
    plan = json.loads(Path(path).read_text())
    selection_record, _ = check_selection_plan()
    if (plan.get('status') != 'PASS_READY_TO_LAUNCH'
        or plan.get('selection_plan_sha256') != selection_record['sha256']
        or plan.get('case_count') != len(ALPHA_BY_CASE)
        or plan.get('declared_input_count_per_case') != 89
        or plan.get('original_native_variable_count') != 208
        or plan.get('all_native_metadata_unchanged') is not True
        or plan.get('original_vs_improved_baseline_input_differences') != ['wrf.exe', 'wrfinput_d01']
        or plan.get('expected_histories') != [
            f'wrfout_d01_2026-08-16_{hour:02d}:00:00' for hour in range(12, 19)]):
        raise ValueError('QSNOW common plan scope or baseline contract mismatch')
    if plan.get('launch_scripts_sha256') != LAUNCH_SCRIPT_SHA:
        raise ValueError('QSNOW common plan launch script hashes differ from pinned scripts')
    for name, expected in LAUNCH_SCRIPT_SHA.items():
        if sha256(Path(path).parent / name) != expected:
            raise ValueError(f'QSNOW runtime launch script changed: {name}')
    expected_manifest_sha = expected_launch_scripts_sha or LAUNCH_MANIFEST_SHA
    if sha256(Path(path).parent / 'launch_scripts.sha256.json') != expected_manifest_sha:
        raise ValueError('QSNOW launch script manifest hash mismatch')
    records = plan.get('case_records')
    if not isinstance(records, dict) or set(records) != set(ALPHA_BY_CASE):
        raise ValueError('QSNOW plan does not contain the exact 12 candidate cells')
    affinity = plan.get('cpu_affinity', {})
    slots, slot_cases = affinity.get('slots'), affinity.get('slot_cases')
    if (plan.get('mpi_ranks_per_case') != 8 or plan.get('omp_threads_per_rank') != 1
        or plan.get('max_concurrent_cases') != 8 or not isinstance(slots, dict)
        or not isinstance(slot_cases, dict) or len(slots) != 8 or len(slot_cases) != 8
        or not isinstance(affinity.get('allowed_cpus'), list)):
        raise ValueError('QSNOW runtime rank/CPU slot plan is incomplete')
    all_cpus = []
    flattened_cases = []
    for slot, cpus in slots.items():
        if len(cpus) != 8 or len(set(cpus)) != 8:
            raise ValueError('QSNOW runtime CPU slots must contain eight unique CPUs')
        all_cpus.extend(cpus)
        flattened_cases.extend(slot_cases.get(slot, []))
    if (len(set(all_cpus)) != len(all_cpus)
        or not set(all_cpus).issubset(set(affinity['allowed_cpus']))
        or set(flattened_cases) != set(ALPHA_BY_CASE)
        or len(flattened_cases) != len(ALPHA_BY_CASE)):
        raise ValueError('QSNOW runtime CPU slots overlap or omit/duplicate cases')
    for case, row in records.items():
        slot = str(row.get('slot'))
        if slot not in slots or row.get('cpu_set') != slots[slot] or case not in slot_cases[slot]:
            raise ValueError(f'{case}: QSNOW case CPU assignment differs from the frozen slots')
    base_inputs = plan.get('source_b1_input_sha256_before')
    family_fields = plan.get('source_field_value_sha256')
    case_fields = plan.get('case_field_value_sha256')
    if (not isinstance(base_inputs, dict) or len(base_inputs) != 89
        or not isinstance(family_fields, dict) or set(family_fields) != {'CONTROL', 'IMPROVED'}
        or not isinstance(case_fields, dict) or set(case_fields) != set(ALPHA_BY_CASE)):
        raise ValueError('QSNOW plan baseline source manifests or field hashes are incomplete')
    if (plan.get('original_executable_sha256') != OLD_EXE_SHA
        or plan.get('fixed_executable_sha256') != FIXED_EXE_SHA
        or plan.get('original_wrfinput_sha256') != ORIGINAL_INPUT_SHA
        or plan.get('improved_wrfinput_sha256') != IMPROVED_INPUT_SHA
        or plan.get('common_boundary_sha256') != BOUNDARY_SHA
        or plan.get('common_six_hour_namelist_sha256') != SIX_HOUR_NAMELIST_SHA):
        raise ValueError('QSNOW plan executable/input/boundary/namelist pins are wrong')
    old_runtime = json.loads(ORIGINAL_RUNTIME_RECEIPT.read_text())['ORIGINAL']
    old_histories = {Path(item['path']).name: item['sha256'] for item in old_runtime['histories']}
    b1_runtime = json.loads(SIX_HOUR_RUNTIME_RECEIPT.read_text())
    expected_hours = [f'wrfout_d01_2026-08-16_{hour:02d}:00:00' for hour in range(12, 19)]
    if (old_runtime.get('status') != 'COMPLETE' or old_runtime.get('metadata', {}).get('exit') != '0'
        or len(old_histories) != 7 or old_runtime.get('full_input_inventory_timing') != 'DURING_RUN'
        or b1_runtime.get('status') != 'SUCCESS' or b1_runtime.get('exit') != 0
        or b1_runtime.get('histories') != expected_hours
        or plan.get('original_alpha_one_history_sha256') != old_histories
        or plan.get('improved_alpha_one_history_sha256') != b1_runtime.get('output_sha256')):
        raise ValueError('reused ORIGINAL or IMPROVED alpha=1 runtime output pins mismatch')
    for case in ALPHA_BY_CASE:
        validate_case_plan_record(case, records[case], base_inputs, family_fields,
                                  case_fields, plan.get('native_metadata_contract_sha256'))
    if plan.get('source_b1_input_sha256_before') != plan.get('source_b1_input_sha256_after'):
        raise ValueError('QSNOW plan B1 source inputs changed during staging')
    if plan.get('original_source_sha256_before') != plan.get('original_source_sha256_after'):
        raise ValueError('QSNOW plan original-family source inputs changed during staging')
    if plan.get('source_evidence_sha256_before') != plan.get('source_evidence_sha256_after'):
        raise ValueError('QSNOW plan producer evidence changed during staging')
    if (plan.get('cross_family_native_metadata_equal') is not True
        or plan.get('field_count') != 208 or plan.get('dimension_count') != 16
        or plan.get('source_b1_input_sha256_before', {}).get('wrfbdy_d01') != BOUNDARY_SHA
        or plan.get('source_b1_input_sha256_before', {}).get('namelist.input') != SIX_HOUR_NAMELIST_SHA):
        raise ValueError('QSNOW plan native metadata or shared runtime config contract failed')
    plan['_sha256'] = record['sha256']
    return record, plan


def check_case_receipt(case, plan, receipt_path):
    """Require one complete, hash-bound six-hour run and unchanged staged/source inputs."""
    path = Path(receipt_path)
    receipt = json.loads(path.read_text())
    spec = plan['case_records'][case]
    histories = [f'wrfout_d01_2026-08-16_{hour:02d}:00:00' for hour in range(12, 19)]
    if (receipt.get('status') != 'SUCCESS' or receipt.get('case') != case
        or receipt.get('group') != spec['group'] or receipt.get('alpha') != spec['alpha']
        or receipt.get('exit') != 0
        or receipt.get('success_marker') is not True
        or receipt.get('histories_exact') is not True
        or receipt.get('histories') != histories
        or receipt.get('common_plan_sha256') != plan.get('_sha256')
        or receipt.get('selection_plan_sha256') != SELECTION_PLAN_SHA
        or receipt.get('launch_scripts_sha256') != plan.get('launch_scripts_sha256')
        or receipt.get('scratch_directory') != spec.get('scratch_directory')
        or receipt.get('common_plan_unchanged_after_run') is not True
        or receipt.get('staged_inputs_unchanged') is not True
        or receipt.get('source_unchanged') is not True
        or receipt.get('affinity_outside_assigned_set') is not False):
        raise ValueError(f'{case}: raw runtime receipt is failed or incomplete')
    if (receipt.get('preflight_case_sha256') != spec['staged_sha256']
        or receipt.get('staged_sha256_after') != spec['staged_sha256']):
        raise ValueError(f'{case}: staged 89-input receipt does not match frozen common plan')
    expected_sources = {
        'B1': plan['source_b1_input_sha256_before'],
        'ORIGINAL': plan['original_source_sha256_before'],
        'evidence': plan['source_evidence_sha256_before'],
    }
    if (receipt.get('source_sha256_before') != expected_sources
        or receipt.get('source_sha256_after') != expected_sources):
        raise ValueError(f'{case}: family source or producer evidence changed during runtime')
    if receipt.get('qsnow_audit') != spec['qsnow_audit']:
        raise ValueError(f'{case}: runtime QSNOW audit differs from frozen staging plan')
    if (receipt.get('cpu_slot') != spec.get('slot') or receipt.get('cpu_set') != spec.get('cpu_set')
        or receipt.get('mpi_ranks') != 8 or receipt.get('omp_threads') != 1
        or receipt.get('i_mpi_pin_processor_list') != ','.join(str(cpu) for cpu in spec['cpu_set'])):
        raise ValueError(f'{case}: MPI rank/CPU affinity configuration differs from preflight')
    observed = receipt.get('observed_rank_process_affinities')
    if (not isinstance(observed, dict) or len(observed) < 8
        or any(not set(affinity).issubset(set(spec['cpu_set'])) for affinity in observed.values())):
        raise ValueError(f'{case}: observed MPI rank affinity is incomplete or outside assigned CPUs')
    output_hashes = receipt.get('output_sha256')
    if not isinstance(output_hashes, dict) or set(output_hashes) != set(histories):
        raise ValueError(f'{case}: runtime history output hashes are incomplete')
    run_dir = Path(spec['scratch_directory'])
    if sorted(item.name for item in run_dir.glob('wrfout*')) != histories:
        raise ValueError(f'{case}: scratch contains incomplete or extra histories')
    records = [identity(path)]
    for name, expected_sha in spec['staged_sha256'].items():
        if Path(name).name != name:
            raise ValueError(f'{case}: unsafe staged input name')
        item = identity(run_dir / name)
        if item['sha256'] != expected_sha:
            raise ValueError(f'{case}: staged input changed after runtime: {name}')
        records.append(item)
    for name in histories:
        item = identity(run_dir / name)
        if item['sha256'] != output_hashes[name]:
            raise ValueError(f'{case}: runtime output hash mismatch: {name}')
        records.append(item)
    for name in ('launcher.txt', 'rsl.out.0000.txt', 'runner_stdout.txt'):
        log_path = path.parent / name
        if not log_path.is_file():
            raise ValueError(f'{case}: runtime evidence log is missing: {name}')
        records.append(identity(log_path))
    return run_dir, records


def check_final_runtime_bundle(runtime_dir, plan, expected_final_receipt_sha=None):
    """Cross-check batch receipt, all case receipts, and finalized history validation."""
    runtime_dir = Path(runtime_dir)
    final_path = runtime_dir / 'final_receipt.json'
    final_record = identity(final_path)
    if expected_final_receipt_sha and final_record['sha256'] != expected_final_receipt_sha:
        raise ValueError('frozen QSNOW final runtime receipt hash mismatch')
    final = json.loads(final_path.read_text())
    batch_path = runtime_dir / 'batch_receipt.json'
    batch_record = identity(batch_path)
    batch = json.loads(batch_path.read_text())
    histories_path = runtime_dir / 'history_validation.json'
    histories_record = identity(histories_path)
    histories = json.loads(histories_path.read_text())
    expected_cases = set(ALPHA_BY_CASE)
    if (final.get('status') != 'SUCCESS' or final.get('case_count') != 12
        or final.get('common_plan_sha256') != plan.get('_sha256')
        or final.get('selection_plan_sha256') != SELECTION_PLAN_SHA
        or final.get('batch_receipt_sha256') != batch_record['sha256']
        or final.get('history_validation_sha256') != histories_record['sha256']
        or set(final.get('cases', {})) != expected_cases
        or final.get('all_case_histories_validated') is not True):
        raise ValueError('QSNOW final runtime receipt is incomplete or mismatched')
    if (batch.get('status') != 'SUCCESS' or batch.get('case_count') != 12
        or batch.get('common_plan_sha256') != plan.get('_sha256')
        or batch.get('selection_plan_sha256') != SELECTION_PLAN_SHA
        or batch.get('common_plan_unchanged_after_batch') is not True):
        raise ValueError('QSNOW batch runtime receipt failed')
    if histories.get('status') != 'SUCCESS' or set(histories.get('cases', {})) != expected_cases:
        raise ValueError('QSNOW history validation report is incomplete')
    for case in expected_cases:
        result = final['cases'][case]
        case_dir = runtime_dir / 'cases' / case
        receipt_path = case_dir / 'receipt.json'
        receipt_record = identity(receipt_path)
        receipt = json.loads(receipt_path.read_text())
        if (result.get('status') != 'SUCCESS'
            or result.get('receipt_path') != str(receipt_path)
            or result.get('receipt_sha256') != receipt_record['sha256']
            or result.get('history_count') != 7
            or result.get('history_sha256') != receipt.get('output_sha256')
            or histories['cases'].get(case, {}).get('status') != 'PASS'):
            raise ValueError(f'{case}: finalized receipt does not bind raw runtime proof')
    return [final_record, batch_record, histories_record]


def check_plan_sources(plan):
    """Rehash both family source inputs and every producer-evidence path in the plan."""
    b1_hashes = plan['source_b1_input_sha256_before']
    records = []
    for name, expected in b1_hashes.items():
        if Path(name).name != name:
            raise ValueError('unsafe B1 source input name in QSNOW plan')
        record = identity(B1_SOURCE_DIR / name)
        if record['sha256'] != expected:
            raise ValueError(f'B1 source input changed after QSNOW preparation: {name}')
        records.append(record)
    old_hashes = plan.get('original_source_sha256_before')
    if not isinstance(old_hashes, dict) or len(old_hashes) != 89:
        raise ValueError('QSNOW plan original-family source manifest is incomplete')
    if old_hashes != plan.get('original_source_sha256_after'):
        raise ValueError('QSNOW plan original-family source before/after maps differ')
    for name, expected in old_hashes.items():
        if Path(name).name != name:
            raise ValueError('unsafe original source input name in QSNOW plan')
        record = identity(ORIGINAL_SOURCE_DIR / name)
        if record['sha256'] != expected:
            raise ValueError(f'original family source input changed after QSNOW preparation: {name}')
        records.append(record)
    original_native = identity(ORIGINAL_SOURCE_DIR / 'wrfinput_d01')
    if original_native['sha256'] != ORIGINAL_INPUT_SHA:
        raise ValueError('original family native input changed after QSNOW preparation')
    old_exe = identity(OLD_EXE_PATH)
    if old_exe['sha256'] != OLD_EXE_SHA:
        raise ValueError('original family executable changed after QSNOW preparation')
    records.extend((original_native, old_exe))
    before = plan.get('source_evidence_sha256_before')
    after = plan.get('source_evidence_sha256_after')
    if not isinstance(before, dict) or before != after:
        raise ValueError('QSNOW plan producer evidence before/after maps differ')
    for name, expected in before.items():
        record = identity(Path(name))
        if record['sha256'] != expected:
            raise ValueError(f'producer evidence changed after QSNOW preparation: {name}')
        records.append(record)
    return records


def _equal_metadata_value(left, right):
    if isinstance(left, np.ndarray) or isinstance(right, np.ndarray):
        left, right = np.asarray(left), np.asarray(right)
        if left.shape != right.shape or left.dtype != right.dtype:
            return False
        if left.dtype.kind in 'fc':
            return bool(np.array_equal(left, right, equal_nan=True))
        return bool(np.array_equal(left, right))
    if isinstance(left, (float, np.floating)) and isinstance(right, (float, np.floating)):
        return (np.isnan(left) and np.isnan(right)) or left == right
    return type(left) is type(right) and left == right


def _equal_values(left, right):
    left, right = np.asanyarray(left), np.asanyarray(right)
    if left.shape != right.shape or left.dtype != right.dtype:
        return False
    if np.ma.isMaskedArray(left) or np.ma.isMaskedArray(right):
        if not np.array_equal(np.ma.getmaskarray(left), np.ma.getmaskarray(right)):
            return False
        left, right = np.ma.getdata(left), np.ma.getdata(right)
    if left.dtype.kind in 'fc':
        return bool(np.array_equal(left, right, equal_nan=True))
    return bool(np.array_equal(left, right))


def _field_value_sha(variable):
    values = np.asanyarray(variable[:])
    digest = hashlib.sha256()
    digest.update(str(values.dtype).encode())
    digest.update(json.dumps(list(values.shape)).encode())
    if np.ma.isMaskedArray(values):
        digest.update(np.ascontiguousarray(np.ma.getmaskarray(values)).tobytes())
        values = np.ma.getdata(values)
    digest.update(np.ascontiguousarray(values).tobytes())
    return digest.hexdigest()


def check_native_qsnow_case(case, plan):
    """Independently verify QSNOW-only values and exact metadata/fields for one staged cell."""
    import netCDF4
    group = ARM_BY_CASE[case]
    record = plan['case_records'][case]
    staged_path = Path(record['scratch_directory']) / 'wrfinput_d01'
    source_path = ORIGINAL_SOURCE_DIR / 'wrfinput_d01' if group == 'CONTROL' else B1_SOURCE_DIR / 'wrfinput_d01'
    expected_fields = plan['case_field_value_sha256'][case]
    source_fields = plan['source_field_value_sha256'][group]
    alpha = ALPHA_BY_CASE[case]
    with netCDF4.Dataset(source_path) as source, netCDF4.Dataset(staged_path) as target:
        if (source.ncattrs() != target.ncattrs()
            or any(not _equal_metadata_value(source.getncattr(name), target.getncattr(name))
                   for name in source.ncattrs())
            or list(source.dimensions) != list(target.dimensions)
            or list(source.variables) != list(target.variables)):
            raise ValueError(f'{case}: native NetCDF global metadata/schema changed')
        for name in source.dimensions:
            left, right = source.dimensions[name], target.dimensions[name]
            if len(left) != len(right) or left.isunlimited() != right.isunlimited():
                raise ValueError(f'{case}: native NetCDF dimension changed: {name}')
        if len(source.variables) != 208 or len(expected_fields) != 208:
            raise ValueError(f'{case}: native field count differs from 208')
        qsnow_values = None
        for name in source.variables:
            left, right = source.variables[name], target.variables[name]
            if (left.dtype != right.dtype or left.dimensions != right.dimensions
                or left.shape != right.shape or left.ncattrs() != right.ncattrs()
                or left.chunking() != right.chunking() or left.filters() != right.filters()
                or left.endian() != right.endian()
                or any(not _equal_metadata_value(left.getncattr(attr), right.getncattr(attr))
                       for attr in left.ncattrs())):
                raise ValueError(f'{case}: native variable metadata changed: {name}')
            actual_hash = _field_value_sha(right)
            if actual_hash != expected_fields.get(name):
                raise ValueError(f'{case}: native field value SHA differs from frozen audit: {name}')
            if name == 'QSNOW':
                source_hash = _field_value_sha(left)
                if (source_hash != source_fields.get('QSNOW')
                    or source_hash != record['qsnow_audit']['source_qsnow_value_sha256']):
                    raise ValueError(f'{case}: source QSNOW hash differs from its family baseline')
                source_values = np.asarray(left[:], dtype=np.float64)
                if right.dtype != np.dtype('float32'):
                    raise ValueError(f'{case}: QSNOW native dtype changed')
                qsnow_values = (source_values * np.float64(alpha)).astype(np.float32)
                if not _equal_values(right[:], qsnow_values):
                    raise ValueError(f'{case}: QSNOW values do not match frozen alpha scaling')
                if actual_hash != record['qsnow_audit']['scaled_qsnow_value_sha256']:
                    raise ValueError(f'{case}: QSNOW output hash differs from runtime audit')
            else:
                if not _equal_values(left[:], right[:]):
                    raise ValueError(f'{case}: non-QSNOW native field changed: {name}')
                if actual_hash != source_fields.get(name):
                    raise ValueError(f'{case}: non-QSNOW source field hash mismatch: {name}')
    return identity(staged_path)


def build_candidate_snapshots(run_dir, case, prior, inventory, expected_lat=None, expected_lon=None):
    """Read and identity-check the seven hourly WRF histories for one candidate case."""
    snapshots, records = {}, []
    initial = datetime(2026, 8, 16, 12, tzinfo=timezone.utc)
    for hour in range(12, 19):
        path = Path(run_dir) / f'wrfout_d01_2026-08-16_{hour:02d}:00:00'
        snapshot, record = prior.checked_snapshot(path, initial + timedelta(hours=hour - 12), inventory)
        if expected_lat is None:
            expected_lat, expected_lon = snapshot['lat'], snapshot['lon']
        elif not np.array_equal(expected_lat, snapshot['lat']) or not np.array_equal(expected_lon, snapshot['lon']):
            raise ValueError(f'{case}: candidate WRF grid differs from shared grid')
        snapshots[hour] = snapshot
        records.append(record)
    return snapshots, records, expected_lat, expected_lon


def score_all_hours(runtime_dir, reference_dir, analysis, odam_dir,
                    output, common_plan=COMMON_PLAN, common_plan_sha=COMMON_PLAN_SHA):
    """Score the 12 completed cells beside the sealed three baseline forecast cases."""
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError(f'refusing to replace existing analysis output: {output}')
    prior = load_prior_scorer()
    scorer = prior.load_scorer()
    plan_record, plan = check_common_plan(common_plan, common_plan_sha)
    runtime_dir = Path(runtime_dir)
    evidence = [identity(PRIOR_SCORER_PATH), identity(scorer.ARCHIVED),
                identity(SELECTION_PLAN), plan_record]
    evidence.extend(identity(Path(runtime_dir) / name) for name in LAUNCH_SCRIPT_SHA)
    evidence.append(identity(Path(runtime_dir) / 'launch_scripts.sha256.json'))
    source_records = check_plan_sources(plan)
    evidence.extend(source_records)
    runtime_records = check_final_runtime_bundle(runtime_dir, plan)
    evidence.extend(runtime_records)

    baselines, archive_first, archive_receipt = load_baseline_arrays(evidence, prior)
    reference_dir, analysis, odam_dir = map(Path, (reference_dir, analysis, odam_dir))
    reference_inputs = scorer.reference_records(reference_dir, analysis)
    evidence.extend(reference_inputs.values())
    evaluator = scorer.evaluator
    inventory, mask, lat, lon, _ = evaluator.load_reference(reference_dir, analysis)
    if int(mask.sum()) != POINTS or not np.array_equal(np.flatnonzero(mask), archive_first['flat_index_yx']):
        raise ValueError('source-bound RN1 mask differs from the pinned paired archive')

    snapshots_by_case, history_records = {}, []
    source_lat = source_lon = None
    case_run_dirs = {}
    native_records = []
    for case in ALPHA_BY_CASE:
        receipt_path = runtime_dir / 'cases' / case / 'receipt.json'
        run_dir, records = check_case_receipt(case, plan, receipt_path)
        case_run_dirs[case] = run_dir
        evidence.extend(records)
        native_records.append(check_native_qsnow_case(case, plan))
        snapshots, records, source_lat, source_lon = build_candidate_snapshots(
            run_dir, case, scorer, inventory, source_lat, source_lon)
        snapshots_by_case[case] = snapshots
        history_records.extend(records)
    evaluator.CASES = tuple(ALPHA_BY_CASE)
    reset_report = evaluator.check_resets(snapshots_by_case)

    x0, x1 = inventory['grid']['crop_x_inclusive']
    y0, y1 = inventory['grid']['crop_y_inclusive']
    ys, xs = slice(y0 - 2, y1), slice(x0 - 2, x1)
    mapping = evaluator.build_curvilinear_mapping(source_lat[ys, xs], source_lon[ys, xs], lat, lon, mask)
    cumulative = {}
    for case, snapshots in snapshots_by_case.items():
        cumulative[case] = {}
        for hour, snapshot in snapshots.items():
            total, valid = evaluator.raw_total(snapshot)
            cumulative[case][hour] = evaluator.remap_field(total[ys, xs], valid[ys, xs], mapping)

    references, rn1_records = {}, []
    for hour, expected_sha in zip(HOURS, scorer.RN1_HASHES, strict=True):
        path = odam_dir / f'DFS_VSRT_GRD_KLPS_ODAM_RN1.20260816{hour:02d}00'
        record = identity(path)
        if record['sha256'] != expected_sha:
            raise ValueError(f'{hour}: canonical RN1 SHA-256 mismatch')
        references[hour] = evaluator.read_rn1(path, hour)
        rn1_records.append(record)

    expected_mask = np.zeros(mask.size, dtype=bool)
    expected_mask[archive_first['flat_index_yx']] = True
    expected_mask = expected_mask.reshape(mask.shape)
    arrays, categorical, continuous, transitions = {}, [], [], []
    for hour in HOURS:
        reference, reference_valid = references[hour]
        common = mask & mapping['valid'] & reference_valid & expected_mask
        expected_flat = archive_first['flat_index_yx']
        if int(common.sum()) != POINTS or not np.array_equal(np.flatnonzero(common), expected_flat):
            raise ValueError(f'{hour}: expected 3688 paired RN1/mapping points')
        values = {key: np.array(value) for key, value in baselines[hour].items()}
        if not np.array_equal(values['reference'], reference[common]):
            raise ValueError(f'{hour}: baseline reference differs from source-bound RN1')
        for case in ALPHA_BY_CASE:
            common_case = common & cumulative[case][hour - 1][1] & cumulative[case][hour][1]
            if int(common_case.sum()) != POINTS or not np.array_equal(np.flatnonzero(common_case), expected_flat):
                raise ValueError(f'{case}/{hour}: case has a non-comparable paired mask')
            diff = cumulative[case][hour][0] - cumulative[case][hour - 1][0]
            if np.any(diff[common_case] < -evaluator.NEGATIVE_TOLERANCE_MM):
                raise ValueError(f'{case}/{hour}: negative accumulated hourly precipitation')
            values[case] = np.maximum(diff[common_case], 0.0)
        values.update(reference=reference[common], latitude=lat[common], longitude=lon[common],
                       flat_index_yx=np.flatnonzero(common))
        for key in ('latitude', 'longitude', 'flat_index_yx'):
            if not np.array_equal(values[key], archive_first[key]):
                raise ValueError(f'{hour}: selected candidate {key} differs from pinned RN1 cohort')
        c_rows, u_rows, t_rows = score_hour(hour, values, scorer)
        categorical.extend(c_rows)
        continuous.extend(u_rows)
        transitions.extend(t_rows)
        arrays[hour] = values

    validate_pairing(arrays)
    validate_score_rows(categorical, continuous, transitions)
    pooled = pooled_errors(arrays)
    selection_rows, selection = selection_table(categorical, continuous, pooled)
    selection['selection_plan'] = identity(SELECTION_PLAN)
    selection['eligibility_reference_case'] = 'IMPROVED_BG_FIXED'
    selection['eligibility_reference_values'] = {
        'lead1_CSI_at_5mm': next(float(row['CSI']) for row in categorical
                                 if row['lead_hour'] == 1 and row['case'] == 'IMPROVED_BG_FIXED'
                                 and float(row['threshold_mm']) == 5.0),
        'lead1_RMSE_mm': next(float(row['RMSE_mm']) for row in continuous
                              if row['lead_hour'] == 1 and row['case'] == 'IMPROVED_BG_FIXED'),
        'pooled6h_MAE_mm': pooled['IMPROVED_BG_FIXED']['pooled_MAE_mm'],
        'pooled6h_RMSE_mm': pooled['IMPROVED_BG_FIXED']['pooled_RMSE_mm'],
    }
    selection['eligibility_rules'] = [
        'lead-1 CSI at 5 mm >= IMPROVED_BG_FIXED',
        'lead-1 RMSE <= IMPROVED_BG_FIXED',
        'pooled six-hour MAE <= IMPROVED_BG_FIXED',
        'pooled six-hour RMSE <= IMPROVED_BG_FIXED',
    ]
    selection['rank_metric'] = 'equal-weight arithmetic mean of six lead-1 threshold CSI values'
    selection['pooled_error_definitions'] = {
        'MAE': 'sum_h(N_h * MAE_h) / sum_h(N_h)',
        'RMSE': 'sqrt(sum_h(N_h * RMSE_h^2) / sum_h(N_h))',
    }
    selection['comparison_tolerance'] = EQUALITY_TOLERANCE

    scorer.verify_records(evidence + history_records + rn1_records + native_records +
                          list(reference_inputs.values()) + source_records)
    check_plan_sources(plan)
    selection_record, _ = check_selection_plan()
    if selection_record['sha256'] != SELECTION_PLAN_SHA:
        raise ValueError('selection plan changed during scoring')

    output.mkdir(parents=True, exist_ok=False)
    try:
        for hour, values in arrays.items():
            np.savez_compressed(output / f'hour_{hour}_arrays.npz', **values)
        write_csv(output / 'categorical_scores.csv', categorical)
        write_csv(output / 'continuous_scores.csv', continuous)
        write_csv(output / 'transitions.csv', transitions)
        write_csv(output / 'selection_scores.csv', selection_rows)
        (output / 'selection.json').write_text(json.dumps(selection, indent=2, allow_nan=False) + '\n')
        scorer.verify_records(evidence + history_records + rn1_records + native_records +
                              list(reference_inputs.values()) + source_records)
        check_plan_sources(plan)
        artifacts = {path.name: {'sha256': sha256(path), 'size_bytes': path.stat().st_size}
                     for path in sorted(output.iterdir())}
        receipt = {
            'status': 'COMPLETE', 'cases': list(CASES), 'eligible_cases': [
                'ORIGINAL', 'IMPROVED_BG_FIXED', *ALPHA_BY_CASE],
            'baseline_cases': list(BASELINE_CASES), 'alpha_by_case': dict(ALPHA_BY_CASE),
            'hours_utc': list(HOURS), 'points_per_hour': POINTS,
            'thresholds_mm': list(THRESHOLDS),
            'row_counts': {'categorical': len(categorical), 'continuous': len(continuous),
                           'transitions': len(transitions), 'selection': len(selection_rows)},
            'units': {'hourly_precipitation': 'mm per preceding one-hour window',
                      'continuous_scores': 'mm per preceding one-hour window',
                      'thresholds': 'mm per preceding one-hour window'},
            'precipitation_window': 'Hourly differences between consecutive WRF histories; not 0–lead accumulation.',
            'selection': selection,
            'initial_qsnow_audits': {case: plan['case_records'][case]['qsnow_audit']
                                     for case in ALPHA_BY_CASE},
            'qSnow_intervention': 'Only QSNOW values are scaled; native float32 from float64(alpha × source); 207 other native variables exact and all metadata unchanged.',
            'interpretation_limitation': 'Initial QSNOW ablation/sensitivity of total ground precipitation, not surface snowfall verification; no mass/energy balance or initialization balance is claimed.',
            'same_event_selection_limitation': 'Selection and evaluation use this same event; ranking is a predeclared exploratory ranking, not independent validation or a significance test.',
            'mapping_residual_max_deg': mapping['residual_max_deg'],
            'reset_checks': reset_report,
            'reference_limitation': 'RN1 processed analysis lacks a coverage bitmap; hourly input freshness is not proven and may use previous-hour fallback. All scores are unweighted over the common 3688 points.',
            'common_plan': plan_record,
            'runtime_final_receipt': identity(runtime_dir / 'final_receipt.json'),
            'runtime_batch_receipt': identity(runtime_dir / 'batch_receipt.json'),
            'runtime_history_validation': identity(runtime_dir / 'history_validation.json'),
            'runtime_case_receipts': {case: identity(runtime_dir / 'cases' / case / 'receipt.json')
                                      for case in ALPHA_BY_CASE},
            'sources': evidence + history_records + rn1_records + native_records,
            'analysis_outputs': artifacts,
        }
        receipt_path = output / 'receipt.json'
        receipt_path.write_text(json.dumps(receipt, indent=2, allow_nan=False) + '\n')
        return receipt
    except BaseException:
        shutil.rmtree(output)
        raise


def main():
    import argparse
    import contextlib
    import sys

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-dir', type=Path, default=RUNTIME_EVIDENCE)
    parser.add_argument('--reference-dir', type=Path, default=DEFAULT_REFERENCE_DIR)
    parser.add_argument('--analysis-dir', type=Path, default=DEFAULT_ANALYSIS_DIR)
    parser.add_argument('--odam-dir', type=Path, default=DEFAULT_ODAM_DIR)
    parser.add_argument('--output', type=Path,
                        default=EVIDENCE_DIR / 'analysis')
    args = parser.parse_args()
    command_path = EVIDENCE_DIR / 'scoring_command.json'
    stdout_path = EVIDENCE_DIR / 'scoring_stdout.txt'
    command = {
        'argv': [str(Path(__file__).resolve()), '--runtime-dir', str(args.runtime_dir),
                 '--reference-dir', str(args.reference_dir), '--analysis-dir', str(args.analysis_dir),
                 '--odam-dir', str(args.odam_dir), '--output', str(args.output)],
        'cwd': str(Path.cwd()), 'scoring_tool_sha256': sha256(Path(__file__).resolve()),
        'selection_plan_sha256': SELECTION_PLAN_SHA, 'common_plan_sha256': COMMON_PLAN_SHA,
    }
    encoded = json.dumps(command, indent=2) + '\n'
    if command_path.exists():
        if command_path.read_text() != encoded:
            raise FileExistsError(f'refusing to replace scoring command: {command_path}')
    else:
        command_path.write_text(encoded, encoding='utf-8')
    if stdout_path.exists():
        raise FileExistsError(f'refusing to replace scorer stdout: {stdout_path}')
    with stdout_path.open('x', encoding='utf-8') as stream, contextlib.redirect_stdout(stream):
        result = score_all_hours(args.runtime_dir, args.reference_dir, args.analysis_dir,
                                 args.odam_dir, args.output)
        print(json.dumps({'status': result['status'], 'row_counts': result['row_counts'],
                          'selection': result['selection']}, indent=2))
    receipt_path = args.output / 'receipt.json'
    receipt = json.loads(receipt_path.read_text())
    receipt['reproduction'] = {'command': identity(command_path), 'stdout_log': identity(stdout_path)}
    receipt_path.write_text(json.dumps(receipt, indent=2, allow_nan=False) + '\n')


def write_csv(path, rows):
    if not rows:
        raise ValueError('refusing to write an empty score table')
    with Path(path).open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def load_baseline_arrays(evidence, prior):
    """Load original/HYDRO controls and the archived six-hour B1 analysis arrays."""
    archived, first, archive_receipt = prior.load_archived_arrays(evidence)
    receipt_path = SIX_HOUR_ANALYSIS / 'receipt.json'
    receipt_record = identity(receipt_path)
    if receipt_record['sha256'] != SIX_HOUR_RECEIPT_SHA:
        raise ValueError('pinned six-hour B1 analysis receipt changed')
    receipt = json.loads(receipt_path.read_text())
    outputs = receipt.get('analysis_outputs')
    if receipt.get('status') != 'COMPLETE' or receipt.get('cases') != [
            'ORIGINAL', 'CURRENT_HYDRO', 'IMPROVED_BG_FIXED']:
        raise ValueError('pinned six-hour baseline analysis has unexpected cases')
    evidence.append(receipt_record)
    result = {}
    for hour in HOURS:
        path = SIX_HOUR_ANALYSIS / f'hour_{hour}_arrays.npz'
        record = identity(path)
        expected = outputs.get(path.name, {}).get('sha256') if isinstance(outputs, dict) else None
        if not expected or record['sha256'] != expected:
            raise ValueError(f'{hour}: six-hour baseline array differs from its sealed receipt')
        evidence.append(record)
        with np.load(path, allow_pickle=False) as data:
            candidate = {key: np.array(data[key]) for key in data.files}
        expected_keys = set(CASES[:3]) | {'reference', 'latitude', 'longitude', 'flat_index_yx'}
        if set(candidate) != expected_keys:
            raise ValueError(f'{hour}: baseline array keys differ from expected three-case set')
        for key, value in candidate.items():
            if np.asarray(value).shape != (POINTS,) or not np.isfinite(value).all():
                raise ValueError(f'{hour}: baseline array {key} has invalid shape or values')
        for key in ('reference', 'latitude', 'longitude', 'flat_index_yx'):
            if not np.array_equal(candidate[key], archived[hour][key]):
                raise ValueError(f'{hour}: six-hour baseline paired {key} differs from archive')
        for case in ('ORIGINAL', 'CURRENT_HYDRO'):
            if not np.array_equal(candidate[case], archived[hour][case]):
                raise ValueError(f'{hour}: six-hour {case} baseline differs from archived control')
        result[hour] = candidate
    prior.verify_baseline_arrays(archived)
    return result, first, archive_receipt


def validate_pairing(hour_arrays):
    """Reject shifted reference values, coordinates, or flat IDs across the 6-hour NPZ set."""
    if tuple(sorted(hour_arrays)) != HOURS:
        raise ValueError('paired arrays must cover exactly 13–18 UTC')
    first = hour_arrays[HOURS[0]]
    ids = first['flat_index_yx']
    if not np.issubdtype(np.asarray(ids).dtype, np.integer) or len(np.unique(ids)) != POINTS:
        raise ValueError('paired flat IDs must be 3688 unique integers')
    for hour in HOURS:
        values = hour_arrays[hour]
        if set(values) != set(CASES) | {'reference', 'latitude', 'longitude', 'flat_index_yx'}:
            raise ValueError(f'{hour}: paired array keys are incomplete')
        for key, value in values.items():
            array = np.asarray(value)
            if array.shape != (POINTS,) or not np.isfinite(array).all():
                raise ValueError(f'{hour}: paired {key} array is non-finite or wrong shape')
        for key in ('flat_index_yx', 'latitude', 'longitude'):
            if not np.array_equal(values[key], first[key]):
                raise ValueError(f'{hour}: paired {key} differs across hours')


def validate_score_rows(categorical, continuous, transitions):
    """Check complete case/hour/threshold row grids and one-hour UTC windows."""
    expected_cat = {(hour - 12, case, threshold) for hour in HOURS
                    for case in CASES for threshold in THRESHOLDS}
    actual_cat = set()
    for row in categorical:
        key = (int(row['lead_hour']), row['case'], float(row['threshold_mm']))
        if key in actual_cat or row['points'] != POINTS:
            raise ValueError('duplicate categorical row or wrong paired point count')
        actual_cat.add(key)
        hour = int(row['lead_hour']) + 12
        if (row['valid_utc'] != f'2026-08-16T{hour:02d}:00:00Z'
            or row['window_start_utc'] != f'2026-08-16T{hour - 1:02d}:00:00Z'
            or row['window_end_utc'] != f'2026-08-16T{hour:02d}:00:00Z'):
            raise ValueError('categorical row uses an incorrect UTC precipitation window')
    if actual_cat != expected_cat:
        raise ValueError('categorical rows do not form the complete 15×6×6 grid')
    expected_cont = {(hour - 12, case) for hour in HOURS for case in CASES}
    actual_cont = set()
    for row in continuous:
        key = (int(row['lead_hour']), row['case'])
        if key in actual_cont or row['points'] != POINTS:
            raise ValueError('duplicate continuous row or wrong paired point count')
        actual_cont.add(key)
        hour = int(row['lead_hour']) + 12
        if (row['valid_utc'] != f'2026-08-16T{hour:02d}:00:00Z'
            or row['window_start_utc'] != f'2026-08-16T{hour - 1:02d}:00:00Z'
            or row['window_end_utc'] != f'2026-08-16T{hour:02d}:00:00Z'):
            raise ValueError('continuous row uses an incorrect UTC precipitation window')
    if actual_cont != expected_cont:
        raise ValueError('continuous rows do not form the complete 15×6 grid')
    expected_transition = {(hour - 12, case, baseline, threshold) for hour in HOURS
                           for case in ALPHA_BY_CASE
                           for baseline in ('ORIGINAL', 'IMPROVED_BG_FIXED')
                           for threshold in THRESHOLDS}
    actual_transition = set()
    for row in transitions:
        key = (int(row['lead_hour']), row['candidate'], row['baseline'],
               float(row['threshold_mm']))
        if key in actual_transition:
            raise ValueError('duplicate transition row')
        actual_transition.add(key)
        hour = key[0] + 12
        if (row['valid_utc'] != f'2026-08-16T{hour:02d}:00:00Z'
            or row['window_start_utc'] != f'2026-08-16T{hour - 1:02d}:00:00Z'
            or row['window_end_utc'] != f'2026-08-16T{hour:02d}:00:00Z'):
            raise ValueError('transition row uses an incorrect UTC precipitation window')
    if actual_transition != expected_transition:
        raise ValueError('transition rows do not form the complete 12×2×6×6 grid')


def score_hour(hour, values, scorer):
    """Score all fifteen paired cases and twelve candidate-vs-control transitions."""
    expected = set(CASES) | {'reference', 'latitude', 'longitude', 'flat_index_yx'}
    if set(values) != expected:
        raise ValueError('hour array case/coordinate keys do not match the pinned 15-case design')
    if any(np.asarray(value).shape != (POINTS,) for value in values.values()):
        raise ValueError('hour arrays must contain exactly 3688 paired points')
    obs = values['reference']
    time = {'lead_hour': hour - 12,
            'valid_utc': f'2026-08-16T{hour:02d}:00:00Z',
            'window_start_utc': f'2026-08-16T{hour - 1:02d}:00:00Z',
            'window_end_utc': f'2026-08-16T{hour:02d}:00:00Z'}
    categorical, continuous, transitions = [], [], []
    for case in CASES:
        prediction = np.asarray(values[case], dtype=np.float64)
        error = prediction - obs
        continuous.append({**time, 'case': case, 'points': POINTS,
                           'mean_forecast_mm': float(np.mean(prediction)),
                           'mean_reference_mm': float(np.mean(obs)),
                           'mean_error_mm': float(np.mean(error)),
                           'MAE_mm': float(np.mean(np.abs(error))),
                           'RMSE_mm': float(np.sqrt(np.mean(error ** 2)))})
        for threshold in THRESHOLDS:
            categorical.append({**time, 'case': case, 'threshold_mm': threshold,
                                'points': POINTS,
                                **scorer.scores(prediction, obs, threshold)})
    for case in ALPHA_BY_CASE:
        for baseline in ('ORIGINAL', 'IMPROVED_BG_FIXED'):
            for threshold in THRESHOLDS:
                transitions.append({**time, 'baseline': baseline, 'candidate': case,
                                    'threshold_mm': threshold,
                                    **scorer.transitions(values[baseline], values[case], obs, threshold)})
    return categorical, continuous, transitions


def pooled_errors(hour_arrays):
    """Return six-hour pooled MAE/RMSE for each case from paired values."""
    if tuple(sorted(hour_arrays)) != HOURS:
        raise ValueError('pooled scoring requires exactly the six 13–18 UTC hours')
    result = {}
    reference_parts = []
    for hour in HOURS:
        values = hour_arrays[hour]
        if set(values) != set(CASES) | {'reference', 'latitude', 'longitude', 'flat_index_yx'}:
            raise ValueError(f'{hour}: pooled array has missing or unexpected cases')
        reference_parts.append(np.asarray(values['reference'], dtype=np.float64))
    reference = np.concatenate(reference_parts)
    for case in CASES:
        forecast = np.concatenate([np.asarray(hour_arrays[h][case], dtype=np.float64) for h in HOURS])
        error = forecast - reference
        result[case] = {'pooled_MAE_mm': float(np.mean(np.abs(error))),
                        'pooled_RMSE_mm': float(np.sqrt(np.mean(error ** 2)))}
    return result


def selection_table(categorical, continuous, pooled):
    """Apply the predeclared feasibility and rank rule against alpha=1 baseline."""
    baseline = 'IMPROVED_BG_FIXED'
    csi, cont = {}, {}
    for row in categorical:
        key = (int(row['lead_hour']), row['case'], float(row['threshold_mm']))
        if key in csi:
            raise ValueError('duplicate categorical case/hour/threshold row')
        csi[key] = row['CSI']
    for row in continuous:
        key = (int(row['lead_hour']), row['case'])
        if key in cont:
            raise ValueError('duplicate continuous case/hour row')
        cont[key] = row
    required = [(1, case, threshold) for case in CASES for threshold in THRESHOLDS]
    if any(key not in csi for key in required):
        raise ValueError('selection requires every case and threshold at lead hour 1')
    if any(csi[key] is None or not math.isfinite(float(csi[key])) for key in required):
        raise ValueError('selection CSI is undefined or non-finite')
    if any((1, case) not in cont for case in CASES):
        raise ValueError('selection requires each case first-hour continuous scores')
    required_pool = set(CASES)
    if set(pooled) != required_pool:
        raise ValueError('selection pooled metrics must cover exactly the fifteen cases')
    for case in CASES:
        for key in ('MAE_mm', 'RMSE_mm'):
            if not math.isfinite(float(cont[(1, case)][key])):
                raise ValueError(f'selection {key} is non-finite for {case}')
        for key in ('pooled_MAE_mm', 'pooled_RMSE_mm'):
            if not math.isfinite(float(pooled[case][key])):
                raise ValueError(f'selection pooled {key} is non-finite for {case}')
    b_csi = float(csi[(1, baseline, ELIGIBILITY_CSI_THRESHOLD_MM)])
    b_rmse = float(cont[(1, baseline)]['RMSE_mm'])
    b_mae6 = float(pooled[baseline]['pooled_MAE_mm'])
    b_rmse6 = float(pooled[baseline]['pooled_RMSE_mm'])
    eligible_cases = ('ORIGINAL', 'IMPROVED_BG_FIXED', *ALPHA_BY_CASE.keys())
    rows = []
    feasible = []
    for case in eligible_cases:
        alpha = 1.0 if case in ('ORIGINAL', 'IMPROVED_BG_FIXED') else ALPHA_BY_CASE[case]
        arm = 'CONTROL' if case == 'ORIGINAL' or ARM_BY_CASE.get(case) == 'CONTROL' else 'IMPROVED'
        first_mean_csi = float(np.mean([float(csi[(1, case, threshold)]) for threshold in THRESHOLDS]))
        first_mae = float(cont[(1, case)]['MAE_mm'])
        first_rmse = float(cont[(1, case)]['RMSE_mm'])
        metrics = pooled[case]
        criteria = {
            'first_hour_CSI_at_5mm_at_least_alpha1': float(csi[(1, case, 5.0)]) >= b_csi - EQUALITY_TOLERANCE,
            'first_hour_RMSE_at_most_alpha1': first_rmse <= b_rmse + EQUALITY_TOLERANCE,
            'pooled_6h_MAE_at_most_alpha1': float(metrics['pooled_MAE_mm']) <= b_mae6 + EQUALITY_TOLERANCE,
            'pooled_6h_RMSE_at_most_alpha1': float(metrics['pooled_RMSE_mm']) <= b_rmse6 + EQUALITY_TOLERANCE,
        }
        is_feasible = all(criteria.values())
        row = {'case': case, 'arm': arm, 'alpha': alpha,
               'first_hour_mean_CSI_6_thresholds': first_mean_csi,
               'first_hour_CSI_at_5mm': float(csi[(1, case, 5.0)]),
               'first_hour_MAE_mm': first_mae, 'first_hour_RMSE_mm': first_rmse,
               **metrics, 'feasible': is_feasible,
               **{f'criterion_{key}': value for key, value in criteria.items()}}
        rows.append(row)
        if is_feasible:
            feasible.append(row)
    rank = lambda row: (-row['first_hour_mean_CSI_6_thresholds'],
                        row['first_hour_MAE_mm'], row['first_hour_RMSE_mm'],
                        abs(row['alpha'] - 1.0), row['case'])
    improved_feasible = [row for row in feasible if row['arm'] == 'IMPROVED']
    overall = min(feasible, key=rank) if feasible else None
    improved = min(improved_feasible, key=rank) if improved_feasible else None
    ranking = sorted(rows, key=rank)
    overall_ranks = {row['case']: index for index, row in enumerate(ranking, 1)}
    feasible_ranks = {row['case']: index for index, row in enumerate(
        [row for row in ranking if row['feasible']], 1)}
    for row in rows:
        row['rank_all_cases'] = overall_ranks[row['case']]
        row['rank_feasible_cases'] = feasible_ranks.get(row['case'])
    feasible_ranked = [row['case'] for row in ranking if row['feasible']]
    failed = {row['case']: [key.removeprefix('criterion_') for key, value in row.items()
                            if key.startswith('criterion_') and not value]
              for row in rows if not row['feasible']}
    return rows, {
        'best_eligible_overall_case': overall['case'] if overall else baseline,
        'best_eligible_overall_alpha': overall['alpha'] if overall else 1.0,
        'best_eligible_improved_case': improved['case'] if improved else baseline,
        'best_eligible_improved_alpha': improved['alpha'] if improved else 1.0,
        'ranking_all_eligible_cases': [row['case'] for row in ranking],
        'ranking_feasible_cases': feasible_ranked,
        'feasibility_failures': failed,
        'overall_fallback_used': overall is None or overall['case'] == baseline,
        'improved_fallback_used': improved is None or improved['case'] == baseline,
    }


if __name__ == '__main__':
    main()

