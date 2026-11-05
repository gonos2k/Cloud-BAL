#!/usr/bin/env python3
"""Score the frozen 2x2 grouped-forecast comparison on paired RN1 arrays."""
from __future__ import annotations

import argparse
import csv
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / 'docs/evidence/cp02_grouped_forecast_20261105/evaluation_plan.json'
PLAN_SHA256 = '583c4eb95a5bf2939bd3a40fa640cc3e6bad615f04bb3f903386840cbb1ccb8c'
THRESHOLDS = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0)
LEADS = tuple(range(1, 7))
POINTS = 3688
ARMS = ('A', 'B', 'C', 'D', 'ORIGINAL')
FACTORIAL = ('A', 'B', 'C', 'D')
PAIRS = (('C', 'A'), ('D', 'B'), ('B', 'A'), ('D', 'C'))
EXPECTED_RN1_HASHES = (
    '5f435e9e7845860636b8ac6d4a982563f1d709f4340dadb7828df2f2cda8e9a1',
    '54ba0fe609630eec8366b9f4a21fddd29baabbd1ad89e8a2ac4e769900887497',
    '00219ebc741da5bbdc79b408a1363e4a920d4f58d41118978234d2cbe089f346',
    '74f2b96af4e0686b15dc1c8a75e337f964a9e25841540a61b3d3546e22187af6',
    '77145a0b095203e452cc029cf56a97f1ff10a5485b69f76ab1d21219c15fa2d5',
    'f0b6834a27449904efb7f6242e47a6246d75ad1403d6eb24ce82c689f00557bc',
)
REFERENCE_ARRAYS = {'reference', 'latitude', 'longitude', 'flat_index_yx'}


def identity(path: Path) -> dict:
    path = Path(path)
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return {'path': str(path), 'sha256': digest.hexdigest(), 'size_bytes': path.stat().st_size}


def _verify_identity(record: dict) -> dict:
    path = Path(record['path'])
    actual = identity(path)
    expected_size = record.get('size_bytes', record.get('size'))
    if actual['sha256'] != record.get('sha256') or actual['size_bytes'] != expected_size:
        raise ValueError(f'input identity changed: {path}')
    return actual


def _receipt(folder: Path, expected_case: str, new_history: bool = False) -> tuple[dict, dict]:
    path = folder / 'receipt.json'
    record = identity(path)
    receipt = json.loads(path.read_text(encoding='utf-8'))
    if receipt.get('status') not in ('COMPLETE', 'PASS'):
        raise ValueError(f'{folder}: scoring receipt is not complete')
    if new_history:
        if receipt.get('initial_time_utc') != '2026-08-16T12:00:00Z':
            raise ValueError(f'{folder}: initial history boundary is not 12 UTC')
        if receipt.get('hours_utc') != list(range(13, 19)) or receipt.get('points_per_hour') != POINTS:
            raise ValueError(f'{folder}: receipt must declare all six leads and 3688 points')
        if tuple(receipt.get('thresholds_mm', ())) != THRESHOLDS or expected_case not in receipt.get('cases', ()):
            raise ValueError(f'{folder}: case or threshold inventory differs from frozen contract')
        rn1 = receipt.get('sources', {}).get('rn1', ())
        expected_paths = [f'DFS_VSRT_GRD_KLPS_ODAM_RN1.20260816{hour:02d}00' for hour in range(13, 19)]
        if (len(rn1) != 6 or [row.get('sha256') for row in rn1] != list(EXPECTED_RN1_HASHES)
            or [Path(row.get('path', '')).name for row in rn1] != expected_paths):
            raise ValueError(f'{folder}: canonical RN1 lead files are not fully bound')
        for row in rn1:
            _verify_identity(row)
        for row in receipt.get('sources', {}).get('reference', {}).values():
            if isinstance(row, dict) and {'path', 'sha256', 'size_bytes'} <= row.keys():
                _verify_identity(row)
    return receipt, record


def _history_boundary(receipt: dict, case: str) -> list[dict]:
    """Require receipts from the canonical history scorer to bind 12..18 UTC."""
    sources = receipt.get('sources', {})
    histories = sources.get('wrfout', {}).get(case)
    if histories is None:
        # Older sealed bundles carry history identities in receipt.inputs.
        histories = [row for row in receipt.get('inputs', ())
                     if Path(row.get('path', '')).name.startswith('wrfout_d01_2026-08-16_')]
    expected = [f'wrfout_d01_2026-08-16_{hour:02d}:00:00' for hour in range(12, 19)]
    names = [Path(row['path']).name for row in histories]
    if sorted(names) != sorted(expected):
        raise ValueError(f'{case}: receipt must bind the seven exact 12..18 UTC histories')
    for row in histories:
        _verify_identity(row)
    return histories


def read_case(folder: Path, case: str, array_key: str) -> tuple[dict, list[dict], dict]:
    folder = Path(folder)
    receipt, receipt_record = _receipt(folder, case, new_history=case in ('C', 'D'))
    records = [receipt_record]
    if case in ('C', 'D'):
        records.extend(receipt['sources']['rn1'])
        for row in receipt.get('sources', {}).get('reference', {}).values():
            if isinstance(row, dict) and {'path', 'sha256', 'size_bytes'} <= row.keys():
                records.append(row)
        records.extend(_history_boundary(receipt, case))
    output_records = receipt.get('outputs') or receipt.get('analysis_outputs', {})
    arrays = {}
    for hour in range(13, 19):
        name = f'hour_{hour}_arrays.npz'
        path = folder / name
        expected = output_records.get(name)
        if expected is None:
            raise ValueError(f'{folder}: receipt lacks {name} identity')
        if not path.is_file():
            raise ValueError(f'{folder}: required lead array is missing: {name}')
        expected = {**expected, 'path': str(path)}
        record = _verify_identity(expected)
        records.append(record)
        with np.load(path, allow_pickle=False) as archive:
            required = REFERENCE_ARRAYS | {array_key}
            if not required <= set(archive.files):
                raise ValueError(f'{path}: missing required array members {sorted(required-set(archive.files))}')
            arrays[hour] = {key: np.array(archive[key], copy=True) for key in required}
            arrays[hour]['forecast'] = arrays[hour][array_key].copy()
            for key in required:
                value = arrays[hour][key]
                if value.shape != (POINTS,):
                    raise ValueError(f'{path}/{key}: expected {POINTS} paired values')
            if not np.isfinite(arrays[hour]['reference']).all() or not np.isfinite(arrays[hour][array_key]).all():
                raise ValueError(f'{path}: forecast and reference must be finite')
            if not np.isfinite(arrays[hour]['latitude']).all() or not np.isfinite(arrays[hour]['longitude']).all():
                raise ValueError(f'{path}: coordinates must be finite')
            keys = arrays[hour]['flat_index_yx']
            if not np.issubdtype(keys.dtype, np.integer) or np.unique(keys).size != POINTS:
                raise ValueError(f'{path}: point keys must be unique integers')
    return receipt, records, arrays


def validate_inputs(inputs: dict[str, tuple[dict, list[dict], dict]]) -> dict[int, dict]:
    if set(inputs) != set(ARMS):
        raise ValueError(f'exactly these five cases are required: {ARMS}')
    hourly = {}
    for hour in range(13, 19):
        rows = {name: bundle[2][hour] for name, bundle in inputs.items()}
        reference = rows['ORIGINAL']['reference']
        keys = rows['ORIGINAL']['flat_index_yx']
        for case, values in rows.items():
            if not np.array_equal(values['reference'], reference):
                raise ValueError(f'{case}/{hour}: RN1 reference differs from immutable benchmark')
            if not np.array_equal(values['flat_index_yx'], keys):
                raise ValueError(f'{case}/{hour}: RN1 point order differs')
            for coord in ('latitude', 'longitude'):
                if not np.array_equal(values[coord], rows['ORIGINAL'][coord]):
                    raise ValueError(f'{case}/{hour}: RN1 coordinates differ')
        if hour > 13:
            for key in ('latitude', 'longitude', 'flat_index_yx'):
                if not np.array_equal(rows['ORIGINAL'][key], hourly[hour - 1][key]):
                    raise ValueError(f'RN1 {key} cohort changes across leads')
        hourly[hour] = {'reference': reference.copy(), 'latitude': rows['ORIGINAL']['latitude'].copy(),
                        'longitude': rows['ORIGINAL']['longitude'].copy(), 'flat_index_yx': keys.copy()}
        for case in FACTORIAL:
            hourly[hour][case] = rows[case]['forecast'].copy()
        hourly[hour]['ORIGINAL'] = rows['ORIGINAL']['forecast'].copy()
    return hourly


def contingency(forecast: np.ndarray, reference: np.ndarray, threshold: float) -> dict:
    pred, obs = forecast >= threshold, reference >= threshold
    h = int(np.count_nonzero(pred & obs))
    m = int(np.count_nonzero(~pred & obs))
    f = int(np.count_nonzero(pred & ~obs))
    d = int(np.count_nonzero(~pred & ~obs))
    n = h + m + f + d
    if h + m + f == 0:
        raise ValueError(f'CSI undefined for threshold {threshold:g}')
    pod_den = h + m
    far_den = h + f
    bias_den = h + m
    random_hits = (h + m) * (h + f) / n if n else 0.0
    ets_den = h + m + f - random_hits
    return {'hit': h, 'miss': m, 'false_alarm': f, 'correct_dry': d, 'points': n,
            'csi_numerator': h, 'csi_denominator': h + m + f, 'CSI': h / (h + m + f),
            'POD': h / pod_den if pod_den else None, 'FAR': f / far_den if far_den else None,
            'frequency_bias': (h + f) / bias_den if bias_den else None,
            'ETS': (h - random_hits) / ets_den if ets_den else None}


def score(hourly: dict[int, dict]) -> tuple[list[dict], list[dict], list[dict], list[dict], list[dict]]:
    categorical, continuous, contrasts, transitions, gates = [], [], [], [], []
    by_cell = {}
    by_cont = {}
    for hour in range(13, 19):
        lead, values = hour - 12, hourly[hour]
        obs = values['reference']
        for case in ARMS:
            forecast = values[case]
            error = forecast - obs
            cont = {'lead_hour': lead, 'case': case, 'points': POINTS,
                    'mean_forecast_mm': float(np.mean(forecast)), 'mean_reference_mm': float(np.mean(obs)),
                    'mean_error_mm': float(np.mean(error)), 'MAE_mm': float(np.mean(np.abs(error))),
                    'RMSE_mm': float(np.sqrt(np.mean(error ** 2)))}
            continuous.append(cont)
            by_cont[(lead, case)] = cont
            for threshold in THRESHOLDS:
                row = {'lead_hour': lead, 'valid_utc': f'2026-08-16T{hour:02d}:00:00Z',
                       'threshold_mm': threshold, 'case': case, **contingency(forecast, obs, threshold)}
                categorical.append(row)
                by_cell[(lead, threshold, case)] = row
        for lead_threshold in THRESHOLDS:
            base_counts = {case: by_cell[(lead, lead_threshold, case)] for case in ARMS}
            for candidate, baseline in PAIRS:
                c, b = base_counts[candidate], base_counts[baseline]
                contrasts.append({'lead_hour': lead, 'threshold_mm': lead_threshold,
                                  'contrast': f'{candidate}-{baseline}', 'candidate': candidate, 'baseline': baseline,
                                  **{f'delta_{key}': c[key] - b[key] for key in ('hit', 'miss', 'false_alarm', 'correct_dry')},
                                  'delta_CSI': c['CSI'] - b['CSI'],
                                  'candidate_CSI_num': c['csi_numerator'], 'candidate_CSI_den': c['csi_denominator'],
                                  'baseline_CSI_num': b['csi_numerator'], 'baseline_CSI_den': b['csi_denominator']})
            # Difference-in-differences compares score deltas for D-B versus C-A.
            d, b = base_counts['D'], base_counts['B']
            c, a = base_counts['C'], base_counts['A']
            contrasts.append({'lead_hour': lead, 'threshold_mm': lead_threshold, 'contrast': 'DiD',
                              'candidate': 'D-B', 'baseline': 'C-A',
                              **{f'delta_{key}': (d[key] - b[key]) - (c[key] - a[key])
                                 for key in ('hit', 'miss', 'false_alarm', 'correct_dry')},
                              'delta_CSI': (d['CSI'] - b['CSI']) - (c['CSI'] - a['CSI']),
                              'candidate_CSI_num': None, 'candidate_CSI_den': None,
                              'baseline_CSI_num': None, 'baseline_CSI_den': None})
            if lead == 1 or lead_threshold == 5.0:
                a = base_counts['A']
                for candidate in ('C', 'D'):
                    c = base_counts[candidate]
                    gates.append({'gate': 'preserve_current_B1', 'lead_hour': lead, 'threshold_mm': lead_threshold,
                                  'candidate': candidate, 'baseline': 'A',
                                  'candidate_CSI_num': c['csi_numerator'], 'candidate_CSI_den': c['csi_denominator'],
                                  'baseline_CSI_num': a['csi_numerator'], 'baseline_CSI_den': a['csi_denominator'],
                                  'satisfied': c['csi_numerator'] * a['csi_denominator'] >= a['csi_numerator'] * c['csi_denominator']})
            if lead >= 2 and lead_threshold in (0.1, 0.5, 1.0):
                original = base_counts['ORIGINAL']
                for candidate in ('C', 'D'):
                    c = base_counts[candidate]
                    gates.append({'gate': 'recover_vs_ORIGINAL', 'lead_hour': lead, 'threshold_mm': lead_threshold,
                                  'candidate': candidate, 'baseline': 'ORIGINAL',
                                  'candidate_CSI_num': c['csi_numerator'], 'candidate_CSI_den': c['csi_denominator'],
                                  'baseline_CSI_num': original['csi_numerator'], 'baseline_CSI_den': original['csi_denominator'],
                                  'satisfied': c['csi_numerator'] * original['csi_denominator'] >= original['csi_numerator'] * c['csi_denominator']})
        weak = (obs >= 0.1) & (obs < 1.0)
        dry = obs < 0.1
        for candidate, baseline in PAIRS:
            new, old = values[candidate] >= 0.1, values[baseline] >= 0.1
            transitions.append({'lead_hour': lead, 'comparison': f'{candidate}-{baseline}',
                                'weak_observed_points': int(weak.sum()),
                                'weak_detection_gains': int(np.count_nonzero(weak & ~old & new)),
                                'weak_detection_losses': int(np.count_nonzero(weak & old & ~new)),
                                'dry_observed_points': int(dry.sum()),
                                'dry_new_false_alarms': int(np.count_nonzero(dry & ~old & new)),
                                'dry_resolved_false_alarms': int(np.count_nonzero(dry & old & ~new))})
    if (len(categorical), len(continuous), len(gates)) != (180, 30, 52):
        raise ValueError('score grid differs from frozen 180/30/52 row contract')
    return categorical, continuous, contrasts, transitions, gates


def csi_fraction(row: dict) -> Fraction:
    return Fraction(row['csi_numerator'], row['csi_denominator'])


def choose_candidate(gates: list[dict], categorical: list[dict]) -> dict:
    qualified = []
    for candidate in ('C', 'D'):
        candidate_gates = [row for row in gates if row['candidate'] == candidate]
        if len(candidate_gates) != 26:
            raise ValueError(f'{candidate}: expected exactly 26 frozen gate cells')
        if all(row['satisfied'] for row in candidate_gates):
            qualified.append(candidate)
    if not qualified:
        return {'winner': 'B1_RETAINED', 'qualified_candidates': [],
                'selection_rule': 'No candidate passed all 26 frozen cells; retain current B1.'}
    cells = {(row['lead_hour'], row['threshold_mm'], row['case']): row for row in categorical}
    priority = [(1, 10.0), *((lead, 10.0) for lead in range(2, 7)),
                *((lead, 5.0) for lead in range(1, 7))]
    ranked = sorted(qualified, key=lambda candidate: tuple(
        csi_fraction(cells[(lead, threshold, candidate)]) for lead, threshold in priority), reverse=True)
    # A complete score-vector tie goes to C, which keeps the current B1 initial number field.
    best_score = tuple(csi_fraction(cells[(lead, threshold, ranked[0])]) for lead, threshold in priority)
    tied = [candidate for candidate in qualified if tuple(
        csi_fraction(cells[(lead, threshold, candidate)]) for lead, threshold in priority) == best_score]
    winner = 'C' if 'C' in tied else ranked[0]
    return {'winner': winner, 'qualified_candidates': sorted(qualified),
            'priority_cells': [{'lead_hour': lead, 'threshold_mm': threshold} for lead, threshold in priority],
            'selection_rule': 'Among candidates passing all 26 gates, lexicographically maximize exact CSI at +1 h/10 mm, then +2..+6 h/10 mm, then +1..+6 h/5 mm; a full tie prefers C.'}


def check_comparability(path: Path, a_receipt: dict, b_receipt: dict) -> dict:
    record = identity(path)
    gate = json.loads(path.read_text(encoding='utf-8'))
    if gate.get('schema') != 'grouped_forecast_oldsum_comparability_v1' or gate.get('status') != 'PASS':
        raise ValueError('native-owner oldsum comparability receipt is not PASS')
    bound = gate.get('oldsum_receipts', {})
    if bound.get('A', {}).get('sha256') != a_receipt['sha256'] or bound.get('B', {}).get('sha256') != b_receipt['sha256']:
        raise ValueError('native-owner comparability receipt binds different A/B input receipts')
    required = {'same_initialization', 'same_valid_time_bounds', 'same_precip_fields', 'same_RN1_mapping', 'same_hourly_increment_definition'}
    if not required <= set(gate.get('checks', {})) or not all(gate['checks'][key] is True for key in required):
        raise ValueError('native-owner receipt does not pass all oldsum comparability checks')
    return record


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError(f'refusing empty table: {path.name}')
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run(case_dirs: dict[str, tuple[Path, str]], comparability: Path, output: Path) -> dict:
    output = Path(output)
    if os.path.lexists(output):
        raise FileExistsError(output)
    if identity(PLAN)['sha256'] != PLAN_SHA256:
        raise ValueError('frozen evaluation plan changed')
    bundles, inputs = {}, []
    for case in ARMS:
        folder, key = case_dirs[case]
        bundles[case] = read_case(folder, key, key)
        inputs.extend(bundles[case][1])
    plan = json.loads(PLAN.read_text(encoding='utf-8'))
    expected_receipts = plan['source_refs']
    if bundles['A'][1][0]['sha256'] != expected_receipts['B1_oldsum_cache_receipt']['sha256']:
        raise ValueError('A must use the frozen current-B1 oldsum cache receipt')
    if bundles['B'][1][0]['sha256'] != expected_receipts['DM065_oldsum_cache_receipt']['sha256']:
        raise ValueError('B must use the frozen DM065 oldsum cache receipt')
    if bundles['ORIGINAL'][1][0]['sha256'] != bundles['A'][1][0]['sha256']:
        raise ValueError('ORIGINAL must come from the immutable A benchmark bundle')
    gate_record = check_comparability(Path(comparability), bundles['A'][1][0], bundles['B'][1][0])
    inputs.append(gate_record)
    hourly = validate_inputs(bundles)
    categorical, continuous, contrasts, transitions, gates = score(hourly)
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.cp02-grouped-forecast-', dir=output.parent))
    try:
        for name, rows in (('categorical_scores.csv', categorical), ('continuous_scores.csv', continuous),
                           ('contrasts.csv', contrasts), ('weak_transition_counts.csv', transitions),
                           ('gate_results.csv', gates)):
            _write_csv(stage / name, rows)
        (stage / 'winner.json').write_text(json.dumps(choose_candidate(gates, categorical), indent=2, sort_keys=True) + '\n', encoding='utf-8')
        for hour, values in hourly.items():
            np.savez_compressed(stage / f'hour_{hour}_arrays.npz', **values)
        receipt = {'schema': 'cp02_grouped_forecast_result_v1', 'status': 'COMPLETE',
                   'evaluation_plan': identity(PLAN),
                   'initial_time_utc': '2026-08-16T12:00:00Z', 'hours_utc': list(range(13, 19)),
                   'lead_hours': list(LEADS), 'points_per_hour': POINTS, 'thresholds_mm': list(THRESHOLDS),
                   'arms': list(FACTORIAL), 'benchmark': 'ORIGINAL', 'cases': list(ARMS),
                   'comparison_scope': 'Factorial score contrasts; ORIGINAL remains an immutable external benchmark. DiD is diagnostic and not causal attribution.',
                   'precipitation_window': 'one-hour increments of RAINC + RAINNC; not cumulative lead totals',
                   'rows': {'categorical': len(categorical), 'continuous': len(continuous),
                            'contrasts': len(contrasts), 'weak_transitions': len(transitions), 'gates': len(gates)},
                   'inputs': inputs, 'scorer': identity(Path(__file__))}
        receipt['outputs'] = {path.name: identity(path) for path in sorted(stage.iterdir())}
        for item in receipt['outputs'].values():
            item.pop('path')
        (stage / 'receipt.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        for record in inputs:
            _verify_identity(record)
        stage.rename(output)
        return receipt
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--a-oldsum', type=Path, required=True, help='sealed current B1 oldsum analysis bundle')
    parser.add_argument('--b-oldsum', type=Path, required=True, help='sealed DM065 oldsum analysis bundle')
    parser.add_argument('--c-grouped', type=Path, required=True, help='new current B1 grouped score bundle')
    parser.add_argument('--d-grouped', type=Path, required=True, help='new DM065 grouped score bundle')
    parser.add_argument('--original', type=Path, required=True, help='immutable ORIGINAL benchmark bundle')
    parser.add_argument('--comparability', type=Path, required=True, help='native-owner A/B comparability receipt')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    case_dirs = {'A': (args.a_oldsum, 'IMPROVED_BG_FIXED'),
                 'B': (args.b_oldsum, 'B1_RAIN_NUMBER_DM065'),
                 'C': (args.c_grouped, 'C'), 'D': (args.d_grouped, 'D'),
                 'ORIGINAL': (args.original, 'ORIGINAL')}
    print(json.dumps(run(case_dirs, args.comparability, args.output), sort_keys=True))


if __name__ == '__main__':
    main()
