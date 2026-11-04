#!/usr/bin/env python3
"""Evaluate the one predeclared DM065 contrast on the frozen RN1 cohort."""
from __future__ import annotations

import argparse
from fractions import Fraction
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OLD_EVALUATOR = ROOT / 'tools/cp02_rain_number_evaluation.py'
OLD_EVALUATOR_SHA256 = '426fad4aa6fccf71c35bafb7a9b006fa59fb4b3ea05bd5baec49d41cf6a546cf'
spec = importlib.util.spec_from_file_location('rain_prior_evaluation', OLD_EVALUATOR)
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)
CANDIDATE = 'B1_RAIN_NUMBER_DM065'
OLD_PRIOR = 'B1_RAIN_NUMBER_PRIOR'
CASES = ('ORIGINAL', prior.CURRENT, OLD_PRIOR, CANDIDATE)
THRESHOLDS = prior.THRESHOLDS
POLICY_SHA256 = 'c9afca77f42c0e3bba6d7f421f1e612a82ddd8912a722414d892918d4773ad7a'
INPUT_SHA256 = 'e6ed0750f88cb36e2600fd38c05e75513e8267dca72d9ee095cd5340a24ed175'


def compare_scores(arrays):
    if set(arrays) != set(range(13, 19)):
        raise ValueError('six hourly forecast arrays are required')
    categorical, continuous = [], []
    for hour in range(13, 19):
        values = arrays[hour]
        for name in (*CASES, 'reference'):
            if np.shape(values[name]) != (3688,) or not np.isfinite(values[name]).all():
                raise ValueError('all cases must cover the same 3688 finite samples')
        observed = values['reference']
        for case in CASES:
            prediction = values[case]
            error = prediction - observed
            continuous.append({'lead_hour': hour - 12, 'case': case,
                               'MAE_mm': float(np.abs(error).mean()),
                               'RMSE_mm': float(np.sqrt(np.square(error).mean()))})
            for threshold in THRESHOLDS:
                obs, pred = observed >= threshold, prediction >= threshold
                hit = int(np.count_nonzero(obs & pred))
                miss = int(np.count_nonzero(obs & ~pred))
                false = int(np.count_nonzero(~obs & pred))
                denominator = hit + miss + false
                if not denominator:
                    raise ValueError('CSI undefined in a required comparison')
                categorical.append({'lead_hour': hour - 12, 'threshold_mm': threshold, 'case': case,
                                    'points': 3688, 'hit': hit, 'miss': miss,
                                    'false_alarm': false, 'CSI': hit / denominator})
    keyed = {(row['lead_hour'], row['threshold_mm'], row['case']): row for row in categorical}
    constraints = []
    for lead in range(1, 7):
        for threshold in THRESHOLDS:
            protect = lead == 1 or threshold == 5
            recover = lead >= 2 and threshold in (0.1, 0.5, 1.0)
            if not (protect or recover):
                continue
            baseline = prior.CURRENT if protect else 'ORIGINAL'
            candidate = keyed[lead, threshold, CANDIDATE]
            control = keyed[lead, threshold, baseline]
            def fraction(row):
                return Fraction(row['hit'], row['hit'] + row['miss'] + row['false_alarm'])
            constraints.append({'goal': 'preserve_current_B1' if protect else 'recover_low_threshold_vs_ORIGINAL',
                                'lead_hour': lead, 'threshold_mm': threshold, 'baseline': baseline,
                                'candidate_CSI': candidate['CSI'], 'baseline_CSI': control['CSI'],
                                'satisfied': fraction(candidate) >= fraction(control)})
    if (len(categorical), len(continuous), len(constraints)) != (144, 24, 26):
        raise ValueError('evaluation scope differs from 144/24/26')
    return categorical, continuous, constraints


def merge_previous(arrays, old_records):
    """Bind old-NR values to exactly the same sample IDs and baseline arrays."""
    for hour in range(13, 19):
        path = ROOT / old_records[f'hour_{hour}_arrays']['path']
        prior.require_identity(path, old_records[f'hour_{hour}_arrays'])
        with np.load(path, allow_pickle=False) as archive:
            required = {'ORIGINAL', prior.CURRENT, OLD_PRIOR, 'reference', 'latitude', 'longitude', 'flat_index_yx'}
            if set(archive.files) != required:
                raise ValueError(f'{hour}: old prior context inventory mismatch')
            for name in required - {OLD_PRIOR}:
                if not np.array_equal(archive[name], arrays[hour][name]):
                    raise ValueError(f'{hour}: old prior context differs for {name}')
            values = np.asarray(archive[OLD_PRIOR])
            if values.shape != (3688,) or not np.isfinite(values).all():
                raise ValueError(f'{hour}: old prior samples are incomplete or nonfinite')
            arrays[hour][OLD_PRIOR] = values.copy()


def run(plan_path, plan_sha256, runtime, gate_path, output):
    plan_path, runtime, gate_path, output = map(Path, (plan_path, runtime, gate_path, output))
    if os.path.lexists(output):
        raise FileExistsError(output)
    if prior.identity(plan_path)['sha256'] != plan_sha256:
        raise ValueError('evaluation plan hash differs')
    plan = json.loads(plan_path.read_text())
    if (plan.get('schema') != 'b1_rain_dm065_evaluation_v1' or plan.get('candidate') != CANDIDATE
        or plan.get('thresholds_mm') != list(THRESHOLDS) or plan.get('leads_hours') != list(range(1, 7))
        or plan.get('constraint_count') != 26):
        raise ValueError('evaluation scope differs from frozen plan')
    gate = json.loads(gate_path.read_text())
    if gate.get('status') != 'COMPLETE' or gate.get('case') != CANDIDATE:
        raise ValueError('complete candidate runtime gate is required')
    keys = ('policy_sha256', 'input_sha256', 'executable_sha256', 'boundary_sha256', 'namelist_sha256')
    for key in keys:
        if gate.get(key) != plan.get(key) or not isinstance(plan.get(key), str) or len(plan[key]) != 64:
            raise ValueError(f'runtime differs from frozen plan: {key}')
    records = plan.get('bound_artifacts', {})
    required = {'policy', 'initialization', 'candidate_preflight', 'prior_receipt'} | {f'hour_{h}_arrays' for h in range(13, 19)}
    if set(records) != required:
        raise ValueError('bound artifact inventory differs from plan contract')
    inputs = [prior.identity(plan_path), prior.identity(gate_path)]
    for record in records.values():
        inputs.append(prior.require_identity(ROOT / record['path'], record))
    if (records['policy']['sha256'] != POLICY_SHA256 or plan['policy_sha256'] != POLICY_SHA256
        or plan['input_sha256'] != INPUT_SHA256):
        raise ValueError('policy or input differs from declared contrast')
    initialization = json.loads((ROOT / records['initialization']['path']).read_text())
    if (initialization.get('policy_sha256') != POLICY_SHA256 or
        initialization.get('output_sha256') != INPUT_SHA256 or
        initialization.get('candidate_cells') != 200182):
        raise ValueError('initialization receipt differs from declared contrast')
    old_receipt = json.loads((ROOT / records['prior_receipt']['path']).read_text())
    if old_receipt.get('status') != 'COMPLETE':
        raise ValueError('previous prior receipt is not complete')
    for hour in range(13, 19):
        name = f'hour_{hour}_arrays.npz'
        expected_old = old_receipt.get('outputs', {}).get(name, {})
        record = records[f'hour_{hour}_arrays']
        if any(record.get(k) != expected_old.get(k) for k in ('sha256', 'size_bytes')):
            raise ValueError(f'{name}: old prior receipt binding differs')
    preflight = json.loads((ROOT / records['candidate_preflight']['path']).read_text())
    if (preflight.get('status') != 'PASS' or preflight.get('policy_sha256') != plan['policy_sha256']
        or preflight.get('wrfinput_sha256') != plan['input_sha256']
        or preflight.get('called_cells') != 2533440
        or preflight.get('conversion_max0_matches_all_actual_pre_update_cells') is not True
        or preflight.get('rain_number_cap_pass') is not True
        or preflight.get('source_unchanged') is not True):
        raise ValueError('candidate preflight does not admit this input and policy')
    for name, key in (('wrfinput_d01', 'input_sha256'), ('wrf.exe', 'executable_sha256'),
                      ('wrfbdy_d01', 'boundary_sha256'), ('namelist.input', 'namelist_sha256')):
        item = prior.identity(runtime / name)
        if item['sha256'] != plan[key]:
            raise ValueError(f'candidate runtime input changed: {name}')
        inputs.append(item)
    history = gate.get('history', {})
    expected = {f'wrfout_d01_2026-08-16_{hour:02d}:00:00' for hour in range(12, 19)}
    if set(history) != expected:
        raise ValueError('candidate runtime requires seven hourly histories')
    inputs.extend(prior.require_identity(runtime / name, history[name]) for name in sorted(expected))
    if prior.identity(OLD_EVALUATOR)['sha256'] != OLD_EVALUATOR_SHA256:
        raise ValueError('pinned prior evaluator changed')
    if prior.identity(prior.BALANCE)['sha256'] != prior.BALANCE_SHA256:
        raise ValueError('pinned remapping source changed')
    mapper_spec = importlib.util.spec_from_file_location('dm065_mapping', prior.BALANCE)
    mapping_module = importlib.util.module_from_spec(mapper_spec)
    mapper_spec.loader.exec_module(mapping_module)
    _, baselines, prior_records = mapping_module.load_prior_arrays()
    # Configure only this isolated module instance, matching the existing validated evaluator.
    mapping_module.CASE_IDS = (CANDIDATE,)
    mapping_module.CONTEXT_IDS = ('ORIGINAL', prior.CURRENT)
    arrays, _, histories, mapping, resets = mapping_module.build_candidate_arrays({CANDIDATE: runtime}, baselines)
    merge_previous(arrays, records)
    categorical, continuous, constraints = compare_scores(arrays)
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.rain-dm065-evaluation-', dir=output.parent))
    try:
        for name, rows in (('categorical_scores.csv', categorical), ('continuous_scores.csv', continuous),
                           ('admission_constraints.csv', constraints)):
            prior.csv_output(stage / name, rows)
        for hour, values in arrays.items():
            np.savez_compressed(stage / f'hour_{hour}_arrays.npz', **values)
        np.savez_compressed(stage / 'bilinear_mapping.npz', **mapping)
        qualified = all(row['satisfied'] for row in constraints)
        verdict = {'candidate': CANDIDATE, 'qualified': qualified,
                   'selection': CANDIDATE if qualified else 'NO_QUALIFIED_CANDIDATE',
                   'passed_constraints': sum(row['satisfied'] for row in constraints), 'required_constraints': 26,
                   'ranking_metric': 'CSI per lead and threshold, no averaging; RMSE diagnostic only'}
        (stage / 'winner.json').write_text(json.dumps(verdict, indent=2, sort_keys=True) + '\n')
        for record in inputs + prior_records + histories:
            prior.require_identity(Path(record['path']), record)
        receipt = {'status': 'COMPLETE', 'inputs': inputs + prior_records + histories,
                   'scorer': prior.identity(Path(__file__)), 'prior_evaluator': prior.identity(OLD_EVALUATOR),
                   'mapping_source': prior.identity(prior.BALANCE),
                   'reset_report': resets, 'rows': {'categorical': 144, 'continuous': 24, 'constraints': 26},
                   'outputs': {p.name: prior.identity(p) for p in sorted(stage.iterdir())}}
        for record in receipt['outputs'].values():
            record.pop('path')
        (stage / 'receipt.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
        stage.rename(output)
        return verdict
    finally:
        if stage.exists():
            shutil.rmtree(stage)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--plan-sha256', required=True)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--runtime-gate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.plan, args.plan_sha256, args.runtime, args.runtime_gate, args.output), sort_keys=True))
