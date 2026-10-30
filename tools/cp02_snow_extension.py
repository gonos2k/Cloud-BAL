#!/usr/bin/env python3
"""Score the strong-precipitation QSNOW sensitivity extension."""
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
PRIOR_TOOL = ROOT / 'tools/cp02_snow_sensitivity.py'
OLD_ANALYSIS = ROOT / 'docs/evidence/snow_sensitivity_20261030/analysis'
EVIDENCE_DIR = ROOT / 'docs/evidence/snow_extension_20261030'
RUNTIME_DIR = EVIDENCE_DIR / 'runtime'
SELECTION_PLAN = EVIDENCE_DIR / 'selection_plan.json'
SELECTION_PLAN_SHA256 = '36e094ac84d698351cdc477ec0bb58fd7580e0676e9ed830236a7d52b0818642'
OLD_ANALYSIS_RECEIPT_SHA256 = '18e2d82c3be0120b2da0e34fec75c12d6da52ddbfc28eaffb19781e94153e7ec'
COMMON_PLAN_SHA256 = 'fa4fcbfc6b21a70875297759dadbbd5a482df3ebd158fdcbbacee85df46c325d'
HOURS = tuple(range(13, 19))
LEADS = tuple(range(1, 7))
THRESHOLDS = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0)
POINTS = 3688
OLD_BASELINES = ('ORIGINAL', 'CURRENT_HYDRO', 'IMPROVED_BG_FIXED')
OLD_SUFFIXES = {'000': 0.0, '025': 0.25, '050': 0.5, '075': 0.75,
                '125': 1.25, '150': 1.5}
NEW_SUFFIXES = {'175': 1.75, '200': 2.0, '250': 2.5, '300': 3.0}
OLD_CASES = tuple(f'{arm}_SNOW_{suffix}' for arm in ('CONTROL', 'IMPROVED')
                  for suffix in OLD_SUFFIXES)
NEW_CASES = tuple(f'{arm}_SNOW_{suffix}' for arm in ('CONTROL', 'IMPROVED')
                  for suffix in NEW_SUFFIXES)
ALPHA_BY_CASE = {
    **{f'{arm}_SNOW_{suffix}': alpha for arm in ('CONTROL', 'IMPROVED')
       for suffix, alpha in OLD_SUFFIXES.items()},
    **{f'{arm}_SNOW_{suffix}': alpha for arm in ('CONTROL', 'IMPROVED')
       for suffix, alpha in NEW_SUFFIXES.items()},
}
ARM_BY_CASE = {case: case.split('_', 1)[0] for case in ALPHA_BY_CASE}
ELIGIBLE_CASES = (*OLD_BASELINES[:1], 'IMPROVED_BG_FIXED', *OLD_CASES, *NEW_CASES)
CONTEXT_CASES = (*OLD_BASELINES, *OLD_CASES, *NEW_CASES)
CASE_ORDER = CONTEXT_CASES


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def identity(path):
    path = Path(path)
    return {'path': str(path), 'sha256': sha256(path), 'size': path.stat().st_size}


def load_prior_tool():
    """Load only the established WRF reader, remapper, and categorical scorer."""
    spec = importlib.util.spec_from_file_location('pinned_cp02_snow_sensitivity', PRIOR_TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_old_scores(analysis_dir=OLD_ANALYSIS):
    """Reuse sealed 14-case scores and paired arrays from the previous experiment."""
    analysis_dir = Path(analysis_dir)
    receipt_path = analysis_dir / 'receipt.json'
    if sha256(receipt_path) != OLD_ANALYSIS_RECEIPT_SHA256:
        raise ValueError('old snow-sensitivity analysis receipt pin changed')
    receipt = json.loads(receipt_path.read_text())
    expected_cases = [*OLD_BASELINES, *OLD_CASES]
    if receipt.get('status') != 'COMPLETE' or receipt.get('cases') != expected_cases:
        raise ValueError('old snow-sensitivity analysis has unexpected case scope')
    output_hashes = receipt.get('analysis_outputs')
    if not isinstance(output_hashes, dict):
        raise ValueError('old snow-sensitivity artifact manifest is missing')
    arrays, records = {}, [identity(receipt_path)]
    for hour in HOURS:
        path = analysis_dir / f'hour_{hour}_arrays.npz'
        record = identity(path)
        if record['sha256'] != output_hashes.get(path.name, {}).get('sha256'):
            raise ValueError(f'{hour}: old paired array differs from its sealed receipt')
        records.append(record)
        with np.load(path, allow_pickle=False) as data:
            values = {key: np.array(data[key]) for key in data.files}
        if set(values) != set(expected_cases) | {'reference', 'latitude', 'longitude', 'flat_index_yx'}:
            raise ValueError(f'{hour}: old paired array case keys differ from its receipt')
        if any(value.shape != (POINTS,) or not np.isfinite(value).all()
               for value in values.values()):
            raise ValueError(f'{hour}: old paired array has invalid points or values')
        arrays[hour] = values
    cat_path, cont_path = analysis_dir / 'categorical_scores.csv', analysis_dir / 'continuous_scores.csv'
    for path in (cat_path, cont_path):
        if sha256(path) != output_hashes.get(path.name, {}).get('sha256'):
            raise ValueError(f'old score table differs from its sealed receipt: {path.name}')
        records.append(identity(path))
    with cat_path.open(newline='', encoding='utf-8') as stream:
        categorical = list(csv.DictReader(stream))
    with cont_path.open(newline='', encoding='utf-8') as stream:
        continuous = list(csv.DictReader(stream))
    return arrays, categorical, continuous, records, receipt


def check_selection_plan(plan_path=SELECTION_PLAN, plan_sha256=SELECTION_PLAN_SHA256):
    record = identity(plan_path)
    if record['sha256'] != plan_sha256:
        raise ValueError('frozen extension selection plan hash mismatch')
    plan = json.loads(Path(plan_path).read_text())
    expected_order = [
        'descending lead-1-hour CSI at 10 mm', 'descending lead-1-hour CSI at 5 mm',
        'ascending lead-1-hour FAR at 10 mm', 'ascending lead-1-hour RMSE',
        'ascending absolute snow-factor deviation from 1', 'ascending case ID']
    if (plan.get('status') != 'FROZEN_BEFORE_EXTENSION_FORECAST_OUTPUTS'
        or plan.get('evaluation', {}).get('lead_hours') != list(LEADS)
        or plan.get('evaluation', {}).get('thresholds_mm') != list(THRESHOLDS)
        or plan.get('evaluation', {}).get('paired_points_per_hour') != POINTS
        or plan.get('evaluation', {}).get('primary_lead_hour') != 1
        or plan.get('evaluation', {}).get('primary_threshold_mm') != 10.0
        or plan.get('experiment', {}).get('families') != ['CONTROL', 'IMPROVED']
        or plan.get('experiment', {}).get('snow_factors') != [1.75, 2.0, 2.5, 3.0]
        or plan.get('experiment', {}).get('new_cases') != 8
        or plan.get('selection', {}).get('ranking_order') != expected_order
        or plan.get('selection', {}).get('numerical_comparison_tolerance') != 0.0
        or plan.get('selection', {}).get('undefined_scores') !=
        'Undefined CSI ranked below defined CSI; undefined FAR after defined FAR. Never convert undefined metric to zero.'):
        raise ValueError('frozen extension selection plan contract mismatch')
    return record, plan


def check_extension_bundle(runtime_dir, plan_path, plan_sha256=None, old_tool=None):
    """Bind the eight added cases to the frozen prep plan and finalized receipts."""
    runtime_dir, plan_path = Path(runtime_dir), Path(plan_path)
    plan_record, plan = check_selection_plan(plan_path, plan_sha256 or SELECTION_PLAN_SHA256)
    cases = set(NEW_CASES)
    common_path = runtime_dir / 'common_plan.json'
    common_record = identity(common_path)
    if common_record['sha256'] != COMMON_PLAN_SHA256:
        raise ValueError('frozen extension runtime common-plan hash mismatch')
    common_plan = json.loads(common_path.read_text())
    case_records = common_plan.get('case_records')
    if (common_plan.get('status') != 'PASS_READY_TO_LAUNCH'
        or common_plan.get('selection_plan_sha256') != plan_record['sha256']
        or common_plan.get('case_count') != len(cases)
        or common_plan.get('declared_input_count_per_case') != 89
        or common_plan.get('original_native_variable_count') != 208
        or common_plan.get('all_native_metadata_unchanged') is not True
        or common_plan.get('cross_family_native_metadata_equal') is not True
        or common_plan.get('original_vs_improved_baseline_input_differences') != ['wrf.exe', 'wrfinput_d01']
        or not isinstance(case_records, dict) or set(case_records) != cases):
        raise ValueError('extension runtime common plan scope or selection-plan pin mismatch')
    affinity = common_plan.get('cpu_affinity', {})
    slots, slot_cases = affinity.get('slots'), affinity.get('slot_cases')
    if (common_plan.get('mpi_ranks_per_case') != 8 or common_plan.get('omp_threads_per_rank') != 1
        or common_plan.get('max_concurrent_cases') != 8 or not isinstance(slots, dict)
        or not isinstance(slot_cases, dict) or len(slots) != 8 or len(slot_cases) != 8):
        raise ValueError('extension CPU slot plan is incomplete')
    flattened_cpus, flattened_cases = [], []
    for slot, cpus in slots.items():
        if len(cpus) != 8 or len(set(cpus)) != 8:
            raise ValueError('extension CPU slots must contain eight unique CPUs')
        flattened_cpus.extend(cpus)
        flattened_cases.extend(slot_cases.get(slot, []))
    if (len(set(flattened_cpus)) != len(flattened_cpus)
        or not set(flattened_cpus).issubset(set(affinity.get('allowed_cpus', [])))
        or set(flattened_cases) != cases or len(flattened_cases) != len(cases)):
        raise ValueError('extension CPU slots overlap or omit/duplicate cases')
    launch_scripts = common_plan.get('launch_scripts_sha256')
    if not isinstance(launch_scripts, dict) or not launch_scripts:
        raise ValueError('extension launch script pins are missing')
    launch_records = []
    for name, expected in launch_scripts.items():
        script_record = identity(runtime_dir / name)
        if script_record['sha256'] != expected:
            raise ValueError(f'extension launch script changed: {name}')
        launch_records.append(script_record)
    launch_manifest = identity(runtime_dir / 'launch_scripts.sha256.json')
    if json.loads((runtime_dir / 'launch_scripts.sha256.json').read_text()) != launch_scripts:
        raise ValueError('extension launch-script manifest differs from common plan')
    source_records = old_tool.check_plan_sources(common_plan) if old_tool else []
    plan_inputs, field_sources, field_cases = (common_plan.get('source_b1_input_sha256_before'),
                                               common_plan.get('source_field_value_sha256'),
                                               common_plan.get('case_field_value_sha256'))
    if (not isinstance(plan_inputs, dict) or len(plan_inputs) != 89
        or not isinstance(field_sources, dict) or set(field_sources) != {'CONTROL', 'IMPROVED'}
        or not isinstance(field_cases, dict) or set(field_cases) != cases):
        raise ValueError('extension common plan input or native field audits are incomplete')
    exe_sha = {'CONTROL': 'de110a7f1d40143a74ffedbe64ed5b3717c413876093f56d200563e2f6b9c168',
               'IMPROVED': '68ed2833b5f207d037949c9b20c7c2f800500e632f911a4acf1eb09d13bf1c1f'}
    native_sha = {'CONTROL': '5d6b2bdce4121642dea994f3e953cca690ad7c9f52f6f8feb01bb6c2f0b9b6bc',
                  'IMPROVED': '9f8b494dbf5ce765e4320701475d6a65be1f591d72a4f9bf5e929c208be563e5'}
    for case in NEW_CASES:
        spec = case_records[case]
        arm, alpha = ARM_BY_CASE[case], ALPHA_BY_CASE[case]
        slot = str(spec.get('slot'))
        staged, audit = spec.get('staged_sha256'), spec.get('qsnow_audit', {})
        base_inputs = common_plan['source_b1_input_sha256_before'] if arm == 'IMPROVED' else common_plan['original_source_sha256_before']
        expected_staged_names = (set(base_inputs) - {'namelist.output', 'wrf.exe'}) | {'wrf.exe'}
        if (spec.get('case') != case or spec.get('group') != arm or spec.get('alpha') != alpha
            or not spec.get('scratch_directory') or not isinstance(staged, dict) or len(staged) != 89
            or set(staged) != expected_staged_names
            or slot not in slots or spec.get('cpu_set') != slots[slot] or case not in slot_cases[slot]
            or staged.get('wrf.exe') != exe_sha[arm] or staged.get('wrfinput_d01') == native_sha[arm]
            or staged.get('wrfbdy_d01') != common_plan.get('common_boundary_sha256')
            or staged.get('namelist.input') != common_plan.get('common_six_hour_namelist_sha256')
            or any(staged.get(name) != value for name, value in base_inputs.items()
                   if name not in ('namelist.output', 'wrf.exe', 'wrfinput_d01'))):
            raise ValueError(f'{case}: staged executable/input/boundary contract failed')
        if (audit.get('group') != arm or audit.get('alpha') != alpha
            or audit.get('scaling_rule') != 'float64(source QSNOW) * float64(alpha), then cast to native float32'
            or audit.get('dtype') != 'float32' or audit.get('variable_count') != 208
            or audit.get('other_variables_unchanged') is not True
            or audit.get('all_native_metadata_unchanged') is not True
            or audit.get('finite') is not True or audit.get('nonnegative') is not True
            or audit.get('source_input_sha256') != native_sha[arm]
            or audit.get('source_qsnow_value_sha256') != field_sources[arm].get('QSNOW')
            or audit.get('changed_value_count') is None
            or audit.get('total_value_count') is None
            or audit.get('native_metadata_contract_sha256') != common_plan.get('native_metadata_contract_sha256')):
            raise ValueError(f'{case}: staged QSNOW-only native audit failed')
        fields, family_fields = field_cases[case], field_sources[arm]
        if (not isinstance(fields, dict) or set(fields) != set(family_fields) or len(fields) != 208
            or fields.get('QSNOW') != audit.get('scaled_qsnow_value_sha256')
            or any(fields[name] != family_fields[name] for name in family_fields if name != 'QSNOW')):
            raise ValueError(f'{case}: native field hashes do not prove a sole-QSNOW change')
    final_path = runtime_dir / 'final_receipt.json'
    final = json.loads(final_path.read_text())
    if (final.get('status') not in ('SUCCESS', 'PARTIAL', 'INCOMPLETE') or final.get('case_count') != 8
        or set(final.get('cases', {})) != cases
        or final.get('common_plan_sha256') != common_record['sha256']
        or final.get('selection_plan_sha256') != plan_record['sha256']):
        raise ValueError('extension final runtime receipt is incomplete')
    batch_path, history_path = runtime_dir / 'batch_receipt.json', runtime_dir / 'history_validation.json'
    batch_record, history_record = identity(batch_path), identity(history_path)
    batch, history_validation = json.loads(batch_path.read_text()), json.loads(history_path.read_text())
    if (batch.get('status') not in ('SUCCESS', 'PARTIAL', 'INCOMPLETE') or batch.get('case_count') != 8
        or batch.get('common_plan_sha256') != common_record['sha256']
        or batch.get('selection_plan_sha256') != plan_record['sha256']
        or batch.get('common_plan_unchanged_after_batch') is not True
        or final.get('batch_receipt_sha256') != batch_record['sha256']
        or final.get('history_validation_sha256') != history_record['sha256']
        or history_validation.get('status') not in ('SUCCESS', 'PARTIAL', 'INCOMPLETE')
        or set(history_validation.get('cases', {})) != cases):
        raise ValueError('extension batch/final/history receipts are not mutually bound')
    plan_records = case_records
    run_dirs, statuses = {}, {}
    records = [plan_record, common_record, identity(final_path), batch_record,
                             history_record, launch_manifest,
                             *launch_records, *source_records]
    histories = [f'wrfout_d01_2026-08-16_{hour:02d}:00:00' for hour in range(12, 19)]
    for case in NEW_CASES:
        spec = plan_records[case]
        path = runtime_dir / 'cases' / case / 'receipt.json'
        receipt_record = identity(path)
        receipt = json.loads(path.read_text())
        alpha, arm = ALPHA_BY_CASE[case], ARM_BY_CASE[case]
        final_case = final['cases'][case]
        statuses[case] = receipt.get('status')
        if receipt.get('status') != 'SUCCESS':
            if final_case.get('status') not in ('FAILED', 'INCOMPLETE', receipt.get('status')):
                raise ValueError(f'{case}: final receipt failed to preserve unsuccessful case status')
            if final_case.get('receipt_sha256') != receipt_record['sha256']:
                raise ValueError(f'{case}: final receipt does not bind failed-case evidence')
            records.append(receipt_record)
            for name in ('launcher.txt', 'rsl.out.0000.txt'):
                log_path = path.parent / name
                if log_path.exists():
                    records.append(identity(log_path))
            for name, expected in receipt.get('output_sha256', {}).items():
                if Path(name).name != name:
                    raise ValueError(f'{case}: unsafe failed-run history filename')
                output_path = Path(spec['scratch_directory']) / name
                if output_path.is_file():
                    record = identity(output_path)
                    if record['sha256'] != expected:
                        raise ValueError(f'{case}: failed-run history hash mismatch: {name}')
                    records.append(record)
            continue
        if (receipt.get('status') != 'SUCCESS' or receipt.get('case') != case
            or receipt.get('group') != arm or receipt.get('alpha') != alpha
            or receipt.get('exit') != 0 or receipt.get('histories') != histories
            or receipt.get('common_plan_sha256') != common_record['sha256']
            or receipt.get('selection_plan_sha256') != plan_record['sha256']
            or receipt.get('launch_scripts_sha256') != launch_scripts
            or receipt.get('success_marker') is not True or receipt.get('histories_exact') is not True
            or receipt.get('common_plan_unchanged_after_run') is not True
            or receipt.get('staged_inputs_unchanged') is not True
            or receipt.get('source_unchanged') is not True
            or receipt.get('affinity_outside_assigned_set') is not False
            or receipt.get('output_sha256', {}).keys() != set(histories)
            or receipt.get('scratch_directory') != spec.get('scratch_directory')):
            raise ValueError(f'{case}: runtime receipt does not match frozen extension plan')
        if (receipt.get('preflight_case_sha256') != spec.get('staged_sha256')
            or receipt.get('staged_sha256_after') != spec.get('staged_sha256')
            or receipt.get('qsnow_audit') != spec.get('qsnow_audit')):
            raise ValueError(f'{case}: runtime staged inputs or QSNOW audit changed')
        expected_sources = {'B1': common_plan['source_b1_input_sha256_before'],
                            'ORIGINAL': common_plan['original_source_sha256_before'],
                            'evidence': common_plan['source_evidence_sha256_before']}
        if (receipt.get('source_sha256_before') != expected_sources
            or receipt.get('source_sha256_after') != expected_sources):
            raise ValueError(f'{case}: source/evidence hashes changed during runtime')
        observed = receipt.get('observed_rank_process_affinities')
        if (receipt.get('mpi_ranks') != 8 or receipt.get('omp_threads') != 1
            or receipt.get('cpu_slot') != spec.get('slot') or receipt.get('cpu_set') != spec.get('cpu_set')
            or receipt.get('i_mpi_pin_processor_list') != ','.join(str(cpu) for cpu in spec['cpu_set'])
            or not isinstance(observed, dict) or len(observed) < 8
            or any(not set(affinity).issubset(set(spec['cpu_set'])) for affinity in observed.values())):
            raise ValueError(f'{case}: runtime rank/CPU affinity evidence is incomplete')
        if final_case.get('receipt_sha256') != receipt_record['sha256']:
            raise ValueError(f'{case}: final receipt does not bind its case receipt')
        if (final_case.get('history_sha256') != receipt.get('output_sha256')
            or final_case.get('history_count') != len(histories)
            or final_case.get('receipt_path') != str(path)
            or history_validation['cases'][case].get('status') != 'PASS'):
            raise ValueError(f'{case}: final receipt or history validation does not bind outputs')
        run_dir = Path(spec['scratch_directory'])
        if sorted(item.name for item in run_dir.glob('wrfout*')) != histories:
            raise ValueError(f'{case}: scratch history list is incomplete or contains extras')
        for name in histories:
            record = identity(run_dir / name)
            if record['sha256'] != receipt['output_sha256'][name]:
                raise ValueError(f'{case}: history output hash mismatch: {name}')
            records.append(record)
        for name, expected in spec['staged_sha256'].items():
            record = identity(run_dir / name)
            if record['sha256'] != expected:
                raise ValueError(f'{case}: staged input changed after runtime: {name}')
            records.append(record)
        for name in ('launcher.txt', 'rsl.out.0000.txt'):
            records.append(identity(path.parent / name))
        records.append(receipt_record)
        run_dirs[case] = run_dir
    return plan, run_dirs, records, statuses


def check_paired_common_mask(mask, mapping_valid, reference_values, paired_ids, case, hour):
    """Keep full-grid validity separate from the archived one-dimensional cohort."""
    mask, mapping_valid = np.asarray(mask, dtype=bool), np.asarray(mapping_valid, dtype=bool)
    reference_values = np.asarray(reference_values)
    paired_ids = np.asarray(paired_ids)
    if mask.shape != mapping_valid.shape:
        raise ValueError('reference and remap validity masks have different grid shapes')
    if (reference_values.shape != (POINTS,) or not np.isfinite(reference_values).all()
        or paired_ids.shape != (POINTS,)):
        raise ValueError('archived reference and paired IDs must each contain 3688 values')
    common = mask & mapping_valid
    if int(common.sum()) != POINTS or not np.array_equal(np.flatnonzero(common), paired_ids):
        raise ValueError(f'{case}/{hour}: remapped extension uses a different paired mask')
    return common


def add_extension_arrays(old_arrays, run_dirs, prior, scorer, inventory, mask, lat, lon):
    """Remap eight new histories and derive their paired hourly precipitation."""
    evaluator = prior.evaluator
    snapshots_by_case, source_lat, source_lon, history_records = {}, None, None, []
    initial = datetime(2026, 8, 16, 12, tzinfo=timezone.utc)
    for case, run_dir in run_dirs.items():
        snapshots = {}
        for hour in range(12, 19):
            path = run_dir / f'wrfout_d01_2026-08-16_{hour:02d}:00:00'
            snapshot, record = scorer.checked_snapshot(path, initial + timedelta(hours=hour - 12), inventory)
            if source_lat is None:
                source_lat, source_lon = snapshot['lat'], snapshot['lon']
            elif not np.array_equal(source_lat, snapshot['lat']) or not np.array_equal(source_lon, snapshot['lon']):
                raise ValueError(f'{case}: extension forecast grid differs from its peers')
            snapshots[hour] = snapshot
            history_records.append(record)
        snapshots_by_case[case] = snapshots
    if not snapshots_by_case:
        return ({hour: dict(values) for hour, values in old_arrays.items()}, history_records,
                {'residual_max_deg': None}, {'cases': {}})
    evaluator.CASES = tuple(snapshots_by_case)
    reset_report = evaluator.check_resets(snapshots_by_case)
    x0, x1 = inventory['grid']['crop_x_inclusive']
    y0, y1 = inventory['grid']['crop_y_inclusive']
    ys, xs = slice(y0 - 2, y1), slice(x0 - 2, x1)
    mapping = evaluator.build_curvilinear_mapping(source_lat[ys, xs], source_lon[ys, xs], lat, lon, mask)
    result = {hour: dict(values) for hour, values in old_arrays.items()}
    for case, snapshots in snapshots_by_case.items():
        cumulative = {}
        for hour, snapshot in snapshots.items():
            total, valid = evaluator.raw_total(snapshot)
            cumulative[hour] = evaluator.remap_field(total[ys, xs], valid[ys, xs], mapping)
        for hour in HOURS:
            old = old_arrays[hour]
            common = check_paired_common_mask(mask, mapping['valid'], old['reference'],
                                              old['flat_index_yx'], case, hour)
            paired_ids = old['flat_index_yx']
            common_case = common & cumulative[hour - 1][1] & cumulative[hour][1]
            if int(common_case.sum()) != POINTS or not np.array_equal(np.flatnonzero(common_case), paired_ids):
                raise ValueError(f'{case}/{hour}: extension forecast has incomplete paired coverage')
            diff = cumulative[hour][0] - cumulative[hour - 1][0]
            if np.any(diff[common_case] < -evaluator.NEGATIVE_TOLERANCE_MM):
                raise ValueError(f'{case}/{hour}: negative accumulated hourly precipitation')
            result[hour][case] = np.maximum(diff[common_case], 0.0)
    return result, history_records, mapping, reset_report


def score_hour(hour, values, scorer):
    """Score all paired cases with hourly continuous and threshold metrics."""
    obs = np.asarray(values['reference'], dtype=np.float64)
    if obs.shape != (POINTS,) or not np.isfinite(obs).all():
        raise ValueError(f'{hour}: reference must contain {POINTS} finite points')
    when = {'lead_hour': hour - 12, 'valid_utc': f'2026-08-16T{hour:02d}:00:00Z',
            'window_start_utc': f'2026-08-16T{hour - 1:02d}:00:00Z',
            'window_end_utc': f'2026-08-16T{hour:02d}:00:00Z'}
    categorical, continuous = [], []
    cases = tuple(case for case in CASE_ORDER if case in values)
    for case in cases:
        prediction = np.asarray(values[case], dtype=np.float64)
        if prediction.shape != (POINTS,) or not np.isfinite(prediction).all():
            raise ValueError(f'{case}/{hour}: forecast must contain {POINTS} finite points')
        error = prediction - obs
        continuous.append({**when, 'case': case, 'valid_obs': int(obs.size),
                           'mean_forecast_mm': float(np.mean(prediction)),
                           'mean_reference_mm': float(np.mean(obs)),
                           'MAE_mm': float(np.mean(np.abs(error))),
                           'RMSE_mm': float(np.sqrt(np.mean(error ** 2)))})
        for threshold in THRESHOLDS:
            categorical.append({**when, 'case': case, 'threshold_mm': threshold,
                                'valid_obs': int(obs.size),
                                **scorer.scores(prediction, obs, threshold)})
    return categorical, continuous


def validate_score_rows(categorical, continuous):
    expected_cases = {row['case'] for row in categorical}
    if not set(OLD_BASELINES + OLD_CASES).issubset(expected_cases) or not expected_cases.issubset(set(CASE_ORDER)):
        raise ValueError('score grid omits sealed cases or contains an unexpected case')
    expected_cat = {(lead, case, threshold) for lead in LEADS
                    for case in expected_cases for threshold in THRESHOLDS}
    actual_cat = set()
    for row in categorical:
        key = (int(row['lead_hour']), row['case'], float(row['threshold_mm']))
        if key in actual_cat or row['valid_obs'] != POINTS:
            raise ValueError('duplicate categorical row or invalid valid-observation count')
        actual_cat.add(key)
        hour = key[0] + 12
        if (row['valid_utc'] != f'2026-08-16T{hour:02d}:00:00Z'
            or row['window_start_utc'] != f'2026-08-16T{hour - 1:02d}:00:00Z'
            or row['window_end_utc'] != f'2026-08-16T{hour:02d}:00:00Z'):
            raise ValueError('categorical score has an incorrect hourly window')
    if actual_cat != expected_cat:
        raise ValueError('categorical score rows do not form the full case/hour/threshold grid')
    expected_cont = {(lead, case) for lead in LEADS for case in expected_cases}
    actual_cont = set()
    for row in continuous:
        key = (int(row['lead_hour']), row['case'])
        if key in actual_cont or row['valid_obs'] != POINTS:
            raise ValueError('duplicate continuous row or invalid valid-observation count')
        actual_cont.add(key)
        hour = key[0] + 12
        if (row['valid_utc'] != f'2026-08-16T{hour:02d}:00:00Z'
            or row['window_start_utc'] != f'2026-08-16T{hour - 1:02d}:00:00Z'
            or row['window_end_utc'] != f'2026-08-16T{hour:02d}:00:00Z'):
            raise ValueError('continuous score has an incorrect hourly window')
    if actual_cont != expected_cont:
        raise ValueError('continuous score rows do not form the full case/hour grid')


def select_case(categorical, continuous, eligible_cases=None):
    """Rank 22 eligible cases by the frozen lexicographic lead-one ordering."""
    cat = {(int(row['lead_hour']), row['case'], float(row['threshold_mm'])): row
           for row in categorical}
    cont = {(int(row['lead_hour']), row['case']): row for row in continuous}
    rows = []
    available = set(cat_case for _, cat_case, _ in cat) & set(cont_case for _, cont_case in cont)
    eligible_cases = tuple(eligible_cases or (case for case in ELIGIBLE_CASES if case in available))
    for case in eligible_cases:
        required_cat = [(1, case, 10.0), (1, case, 5.0)]
        required_cont = (1, case)
        if any(key not in cat for key in required_cat) or required_cont not in cont:
            raise ValueError(f'{case}: selection is missing first-hour criteria')
        def finite_or_none(value):
            if value is None or value == '':
                return None
            value = float(value)
            return value if math.isfinite(value) else None

        csi10, csi5 = (finite_or_none(cat[key]['CSI']) for key in required_cat)
        far10 = finite_or_none(cat[(1, case, 10.0)]['FAR'])
        rmse = finite_or_none(cont[required_cont]['RMSE_mm'])
        alpha = ALPHA_BY_CASE.get(case, 1.0)
        rows.append({'case': case,
                     'arm': ARM_BY_CASE.get(case, 'CONTROL' if case == 'ORIGINAL' else 'IMPROVED'),
                     'alpha': alpha, 'lead1_CSI_at_10mm': csi10,
                     'lead1_CSI_at_5mm': csi5, 'lead1_FAR_at_10mm': far10,
                     'lead1_RMSE_mm': rmse, 'abs_alpha_distance_from_1': abs(alpha - 1.0)})
    rank = lambda row: (
        row['lead1_CSI_at_10mm'] is None,
        -row['lead1_CSI_at_10mm'] if row['lead1_CSI_at_10mm'] is not None else 0.0,
        row['lead1_CSI_at_5mm'] is None,
        -row['lead1_CSI_at_5mm'] if row['lead1_CSI_at_5mm'] is not None else 0.0,
        row['lead1_FAR_at_10mm'] is None,
        row['lead1_FAR_at_10mm'] if row['lead1_FAR_at_10mm'] is not None else 0.0,
        row['lead1_RMSE_mm'] is None,
        row['lead1_RMSE_mm'] if row['lead1_RMSE_mm'] is not None else 0.0,
        row['abs_alpha_distance_from_1'], row['case'])
    rows.sort(key=rank)
    for index, row in enumerate(rows, 1):
        row['rank'] = index
    return rows, {'selected_case': rows[0]['case'], 'selected_alpha': rows[0]['alpha'],
                  'selection_order': [row['case'] for row in rows],
                  'ranking_order': ['descending +1h CSI at 10 mm',
                                    'descending +1h CSI at 5 mm',
                                    'ascending +1h FAR at 10 mm',
                                    'ascending +1h RMSE',
                                    'ascending absolute alpha distance from 1',
                                    'ascending case ID'],
                  'eligibility': f'all {len(rows)} completed eligible cases ranked; forecast-error metrics are tie-breaks, not vetoes; failed/incomplete cases excluded'}


def pooled_error_summary(hour_arrays):
    """Describe six-hour forecast errors for all cases without using them as a veto."""
    summary = {}
    reference = np.concatenate([np.asarray(hour_arrays[hour]['reference'], dtype=float)
                                for hour in HOURS])
    cases = tuple(case for case in CASE_ORDER if case in hour_arrays[HOURS[0]])
    for case in cases:
        forecast = np.concatenate([np.asarray(hour_arrays[hour][case], dtype=float)
                                   for hour in HOURS])
        error = forecast - reference
        summary[case] = {'valid_obs': int(error.size),
                         'pooled_MAE_mm': float(np.mean(np.abs(error))),
                         'pooled_RMSE_mm': float(np.sqrt(np.mean(error ** 2)))}
    return summary


def pooled_error_changes(error_summary):
    """State each case's pooled error change from IMPROVED_BG_FIXED explicitly."""
    baseline = error_summary['IMPROVED_BG_FIXED']
    return {case: {
        'delta_MAE_mm': values['pooled_MAE_mm'] - baseline['pooled_MAE_mm'],
        'MAE_increased': values['pooled_MAE_mm'] > baseline['pooled_MAE_mm'],
        'delta_RMSE_mm': values['pooled_RMSE_mm'] - baseline['pooled_RMSE_mm'],
        'RMSE_increased': values['pooled_RMSE_mm'] > baseline['pooled_RMSE_mm'],
    } for case, values in error_summary.items()}


def write_csv(path, rows):
    if not rows:
        raise ValueError(f'refusing to write empty table: {path}')
    with Path(path).open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def score_extension(runtime_dir, output, plan_path=SELECTION_PLAN, plan_sha256=None,
                    old_analysis_dir=OLD_ANALYSIS):
    """Combine sealed old scores with eight new forecasts, then write extension tables."""
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError(f'refusing to replace existing analysis output: {output}')
    old_tool = load_prior_tool()
    scorer = old_tool.load_prior_scorer().load_scorer()
    old_arrays, _, _, old_records, old_receipt = load_old_scores(old_analysis_dir)
    plan_record, plan = check_selection_plan(plan_path, plan_sha256 or SELECTION_PLAN_SHA256)
    _, run_dirs, runtime_records, runtime_status = check_extension_bundle(
        runtime_dir, plan_path, plan_record['sha256'], old_tool)
    reference_inputs = scorer.reference_records(old_tool.DEFAULT_REFERENCE_DIR,
                                                old_tool.DEFAULT_ANALYSIS_DIR)
    inventory, mask, lat, lon, _ = scorer.evaluator.load_reference(
        old_tool.DEFAULT_REFERENCE_DIR, old_tool.DEFAULT_ANALYSIS_DIR)
    first = old_arrays[HOURS[0]]
    if (int(mask.sum()) != POINTS or not np.array_equal(np.flatnonzero(mask), first['flat_index_yx'])
        or not np.array_equal(lat[mask], first['latitude'])
        or not np.array_equal(lon[mask], first['longitude'])):
        raise ValueError('old paired arrays differ from the pinned RN1 reference cohort')
    hour_arrays, history_records, mapping, reset_report = add_extension_arrays(
        old_arrays, run_dirs, scorer, scorer, inventory, mask, lat, lon)
    categorical, continuous = [], []
    for hour in HOURS:
        cat_rows, cont_rows = score_hour(hour, hour_arrays[hour], scorer)
        categorical.extend(cat_rows)
        continuous.extend(cont_rows)
    validate_score_rows(categorical, continuous)
    eligible_completed = tuple(case for case in ELIGIBLE_CASES
                               if case not in NEW_CASES or runtime_status[case] == 'SUCCESS')
    selection_rows, selection = select_case(categorical, continuous, eligible_completed)
    selection_rows.extend({'case': case, 'arm': ARM_BY_CASE[case],
                           'alpha': ALPHA_BY_CASE[case], 'lead1_CSI_at_10mm': None,
                           'lead1_CSI_at_5mm': None, 'lead1_FAR_at_10mm': None,
                           'lead1_RMSE_mm': None,
                           'abs_alpha_distance_from_1': abs(ALPHA_BY_CASE[case] - 1.0),
                           'rank': None, 'runtime_status': runtime_status[case]}
                          for case in NEW_CASES if runtime_status[case] != 'SUCCESS')
    for row in selection_rows:
        row.setdefault('runtime_status', 'RANKED_COMPLETE')
    errors = pooled_error_summary(hour_arrays)
    selection.update({'selection_plan': plan_record,
                      'context_only_cases': ['CURRENT_HYDRO'],
                      'runtime_case_status': runtime_status,
                      'failed_or_incomplete_cases_unranked': [
                          case for case, status in runtime_status.items() if status != 'SUCCESS'],
                      'errors_reported_without_veto': errors,
                      'pooled_error_changes_vs_IMPROVED_BG_FIXED': pooled_error_changes(errors),
                      'same_event_selection_limitation':
                      'This is same-event parameter selection, not independent validation or a significance test.',
                      'initialization_limitation':
                      'QSNOW-only initial-water sensitivity is diagnostic; it does not claim conservative or operational initialization.',
                      'precipitation_limitation':
                      'The score verifies total surface precipitation, not surface snowfall alone.'})
    evidence = [identity(Path(__file__)), identity(PRIOR_TOOL), identity(old_tool.PRIOR_SCORER_PATH),
                identity(scorer.ARCHIVED), plan_record, *old_records, *runtime_records,
                *reference_inputs.values(), *history_records]
    scorer.verify_records(evidence)
    output.mkdir(parents=True, exist_ok=False)
    try:
        for hour, values in hour_arrays.items():
            np.savez_compressed(output / f'hour_{hour}_arrays.npz', **values)
        write_csv(output / 'categorical_scores.csv', categorical)
        write_csv(output / 'continuous_scores.csv', continuous)
        write_csv(output / 'selection_scores.csv', selection_rows)
        (output / 'selection.json').write_text(
            json.dumps(selection, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        scorer.verify_records(evidence)
        artifacts = {path.name: {'sha256': sha256(path), 'size_bytes': path.stat().st_size}
                     for path in sorted(output.iterdir())}
        scored_cases = list(case for case in CASE_ORDER if case in hour_arrays[HOURS[0]])
        completed_eligible = list(case for case in ELIGIBLE_CASES if case in scored_cases)
        receipt = {'status': 'PARTIAL' if any(status != 'SUCCESS' for status in runtime_status.values()) else 'COMPLETE',
                   'cases': scored_cases,
                   'eligible_cases': completed_eligible,
                   'context_only_cases': ['CURRENT_HYDRO'],
                   'runtime_case_status': runtime_status,
                   'unranked_failed_or_incomplete_cases': [
                       case for case, status in runtime_status.items() if status != 'SUCCESS'],
                   'alpha_by_case': dict(ALPHA_BY_CASE), 'hours_utc': list(HOURS),
                   'points_per_hour': POINTS, 'thresholds_mm': list(THRESHOLDS),
                   'row_counts': {'categorical': len(categorical), 'continuous': len(continuous),
                                  'selection_ranked': len(completed_eligible),
                                  'selection_status': len(selection_rows)},
                   'selection': selection, 'errors_reported_without_veto': errors,
                   'old_analysis_receipt': identity(Path(old_analysis_dir) / 'receipt.json'),
                   'runtime_plan': identity(Path(runtime_dir) / 'common_plan.json'),
                   'runtime_receipts': {case: identity(Path(runtime_dir) / 'cases' / case / 'receipt.json')
                                        for case in NEW_CASES},
                   'reset_checks': reset_report,
                   'mapping_residual_max_deg': mapping['residual_max_deg'],
                   'sources': evidence, 'analysis_outputs': artifacts}
        (output / 'receipt.json').write_text(json.dumps(receipt, indent=2, allow_nan=False) + '\n',
                                             encoding='utf-8')
        return receipt
    except BaseException:
        shutil.rmtree(output)
        raise


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-dir', type=Path, default=RUNTIME_DIR)
    parser.add_argument('--plan', type=Path, default=SELECTION_PLAN)
    parser.add_argument('--plan-sha256')
    parser.add_argument('--old-analysis-dir', type=Path, default=OLD_ANALYSIS)
    parser.add_argument('--output', type=Path, default=EVIDENCE_DIR / 'analysis')
    args = parser.parse_args()
    result = score_extension(args.runtime_dir, args.output, args.plan,
                             args.plan_sha256, args.old_analysis_dir)
    print(json.dumps({'status': result['status'], 'selection': result['selection']}, indent=2))
