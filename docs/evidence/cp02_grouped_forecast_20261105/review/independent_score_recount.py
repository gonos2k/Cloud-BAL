#!/usr/bin/env python3
"""Independently recount grouped-forecast tables from the six saved NPZ files.

This module deliberately does not import the production scorer or plotter. It
is prepared for use after a complete result bundle exists; it has not been run
against forecast outputs that are still in progress.
"""
from __future__ import annotations

import argparse
import csv
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path

import numpy as np

WORKTREE = Path(__file__).resolve().parents[4]
PLAN = WORKTREE / 'docs/evidence/cp02_grouped_forecast_20261105/evaluation_plan.json'
PLAN_SHA256 = '583c4eb95a5bf2939bd3a40fa640cc3e6bad615f04bb3f903386840cbb1ccb8c'
LEADS = tuple(range(1, 7))
HOURS = tuple(range(13, 19))
THRESHOLDS = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0)
CASES = ('A', 'B', 'C', 'D', 'ORIGINAL')
FACTORIAL = ('A', 'B', 'C', 'D')
PAIRS = (('C', 'A'), ('D', 'B'), ('B', 'A'), ('D', 'C'))
POINTS = 3688
RN1_SHA256 = (
    '5f435e9e7845860636b8ac6d4a982563f1d709f4340dadb7828df2f2cda8e9a1',
    '54ba0fe609630eec8366b9f4a21fddd29baabbd1ad89e8a2ac4e769900887497',
    '00219ebc741da5bbdc79b408a1363e4a920d4f58d41118978234d2cbe089f346',
    '74f2b96af4e0686b15dc1c8a75e337f964a9e25841540a61b3d3546e22187af6',
    '77145a0b095203e452cc029cf56a97f1ff10a5485b69f76ab1d21219c15fa2d5',
    'f0b6834a27449904efb7f6242e47a6246d75ad1403d6eb24ce82c689f00557bc',
)
CSV_TABLES = {
    'categorical_scores.csv': ('lead_hour', 'threshold_mm', 'case'),
    'continuous_scores.csv': ('lead_hour', 'case'),
    'contrasts.csv': ('lead_hour', 'threshold_mm', 'contrast'),
    'weak_transition_counts.csv': ('lead_hour', 'comparison'),
    'gate_results.csv': ('gate', 'lead_hour', 'threshold_mm', 'candidate'),
}
FLOAT_TOLERANCE = 1e-12


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def identity_matches(path: Path, record: dict) -> bool:
    expected_size = record.get('size_bytes', record.get('size'))
    return (path.is_file() and path.stat().st_size == expected_size
            and digest(path) == record.get('sha256'))


def resolve_record_path(path: str | Path) -> Path:
    path = Path(path)
    return path if path.is_absolute() else WORKTREE / path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def verify_result_bundle(result_dir: Path) -> tuple[dict, dict[int, dict[str, np.ndarray]]]:
    require(digest(PLAN) == PLAN_SHA256, 'frozen evaluation plan changed')
    plan = json.loads(PLAN.read_text(encoding='utf-8'))
    receipt_path = result_dir / 'receipt.json'
    require(receipt_path.is_file(), 'complete score result receipt is missing')
    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    require(receipt.get('status') == 'COMPLETE', 'score result is not COMPLETE')
    require(receipt.get('evaluation_plan', {}).get('sha256') == PLAN_SHA256,
            'result receipt does not bind the frozen plan')
    require(receipt.get('initial_time_utc') == '2026-08-16T12:00:00Z'
            and receipt.get('hours_utc') == list(HOURS)
            and receipt.get('lead_hours') == list(LEADS)
            and receipt.get('points_per_hour') == POINTS
            and tuple(receipt.get('thresholds_mm', ())) == THRESHOLDS
            and tuple(receipt.get('cases', ())) == CASES,
            'result receipt scope differs from the frozen evaluation contract')
    require(receipt.get('rows') == {'categorical': 180, 'continuous': 30,
                                    'contrasts': 180, 'weak_transitions': 24, 'gates': 52},
            'result receipt row counts differ from the frozen contract')

    source_refs = plan['source_refs']
    input_rows = receipt.get('inputs', [])
    input_by_hash = {row.get('sha256'): row for row in input_rows}
    for key in ('B1_oldsum_cache_receipt', 'DM065_oldsum_cache_receipt'):
        pin = source_refs[key]
        require(pin['sha256'] in input_by_hash, f'{key} not bound as a scored input')
        row = input_by_hash[pin['sha256']]
        require(resolve_record_path(row['path']) == resolve_record_path(pin['path']),
                f'{key} path differs from plan')
    for pin in source_refs['canonical_RN1']:
        require(pin['sha256'] in input_by_hash,
                f"canonical RN1 lead is not bound as a scored input: {pin['path']}")
    for row in input_rows:
        path = resolve_record_path(row['path'])
        require(identity_matches(path, row), f'scored source identity changed: {path}')

    outputs = receipt.get('outputs', {})
    required_outputs = set(CSV_TABLES) | {'winner.json'} | {
        f'hour_{hour}_arrays.npz' for hour in HOURS
    }
    require(required_outputs <= set(outputs), 'result receipt omits required output files')
    for name in required_outputs:
        path = result_dir / name
        record = outputs[name]
        require(path.is_file() and path.stat().st_size == record['size_bytes']
                and digest(path) == record['sha256'], f'result output identity differs: {name}')

    hourly: dict[int, dict[str, np.ndarray]] = {}
    for hour in HOURS:
        path = result_dir / f'hour_{hour}_arrays.npz'
        with np.load(path, allow_pickle=False) as archive:
            needed = {'reference', 'latitude', 'longitude', 'flat_index_yx', *CASES}
            require(needed <= set(archive.files), f'{path.name} lacks required arrays')
            values = {key: np.array(archive[key], copy=True) for key in needed}
        for key, value in values.items():
            require(value.shape == (POINTS,), f'{path.name}/{key} shape differs')
        require(np.issubdtype(values['flat_index_yx'].dtype, np.integer)
                and np.unique(values['flat_index_yx']).size == POINTS,
                f'{path.name} point keys are not unique integers')
        for key in ('reference', 'latitude', 'longitude', *CASES):
            require(np.isfinite(values[key]).all(), f'{path.name}/{key} has nonfinite values')
        hourly[hour] = values

    first = hourly[HOURS[0]]
    for hour in HOURS[1:]:
        values = hourly[hour]
        for key in ('latitude', 'longitude', 'flat_index_yx'):
            require(np.array_equal(values[key], first[key]), f'{key} paired cohort changes at hour {hour}')
    return receipt, hourly


def contingency(forecast: np.ndarray, observed: np.ndarray, threshold: float) -> dict:
    pred, obs = forecast >= threshold, observed >= threshold
    h = int(np.count_nonzero(pred & obs))
    m = int(np.count_nonzero(~pred & obs))
    f = int(np.count_nonzero(pred & ~obs))
    d = int(np.count_nonzero(~pred & ~obs))
    n = h + m + f + d
    den = h + m + f
    require(n == POINTS and den > 0, f'undefined/incorrect contingency at {threshold:g} mm')
    random_hits = (h + m) * (h + f) / n
    ets_den = den - random_hits
    return {'hit': h, 'miss': m, 'false_alarm': f, 'correct_dry': d, 'points': n,
            'csi_numerator': h, 'csi_denominator': den, 'CSI': h / den,
            'POD': h / (h + m) if h + m else None,
            'FAR': f / (h + f) if h + f else None,
            'frequency_bias': (h + f) / (h + m) if h + m else None,
            'ETS': (h - random_hits) / ets_den if ets_den else None}


def recount(hourly: dict[int, dict[str, np.ndarray]]) -> dict[str, list[dict]]:
    categorical, continuous, contrasts, transitions, gates = [], [], [], [], []
    cells: dict[tuple[int, float, str], dict] = {}
    for hour in HOURS:
        lead = hour - 12
        values = hourly[hour]
        obs = values['reference']
        for case in CASES:
            forecast = values[case]
            error = forecast - obs
            continuous.append({
                'lead_hour': lead, 'case': case, 'points': POINTS,
                'mean_forecast_mm': float(np.mean(forecast)),
                'mean_reference_mm': float(np.mean(obs)),
                'mean_error_mm': float(np.mean(error)),
                'MAE_mm': float(np.mean(np.abs(error))),
                'RMSE_mm': float(np.sqrt(np.mean(error ** 2))),
            })
            for threshold in THRESHOLDS:
                row = {'lead_hour': lead, 'valid_utc': f'2026-08-16T{hour:02d}:00:00Z',
                       'threshold_mm': threshold, 'case': case,
                       **contingency(forecast, obs, threshold)}
                categorical.append(row)
                cells[(lead, threshold, case)] = row

        weak_obs = (obs >= 0.1) & (obs < 1.0)
        dry_obs = obs < 0.1
        for threshold in THRESHOLDS:
            current = {case: cells[(lead, threshold, case)] for case in CASES}
            for candidate, baseline in PAIRS:
                c, b = current[candidate], current[baseline]
                contrasts.append({
                    'lead_hour': lead, 'threshold_mm': threshold,
                    'contrast': f'{candidate}-{baseline}', 'candidate': candidate,
                    'baseline': baseline,
                    **{f'delta_{key}': c[key] - b[key]
                       for key in ('hit', 'miss', 'false_alarm', 'correct_dry')},
                    'delta_CSI': c['CSI'] - b['CSI'],
                    'candidate_CSI_num': c['csi_numerator'],
                    'candidate_CSI_den': c['csi_denominator'],
                    'baseline_CSI_num': b['csi_numerator'],
                    'baseline_CSI_den': b['csi_denominator'],
                })
            d, b = current['D'], current['B']
            c, a = current['C'], current['A']
            contrasts.append({
                'lead_hour': lead, 'threshold_mm': threshold, 'contrast': 'DiD',
                'candidate': 'D-B', 'baseline': 'C-A',
                **{f'delta_{key}': (d[key] - b[key]) - (c[key] - a[key])
                   for key in ('hit', 'miss', 'false_alarm', 'correct_dry')},
                'delta_CSI': (d['CSI'] - b['CSI']) - (c['CSI'] - a['CSI']),
                'candidate_CSI_num': None, 'candidate_CSI_den': None,
                'baseline_CSI_num': None, 'baseline_CSI_den': None,
            })
            if lead == 1 or threshold == 5.0:
                a = current['A']
                for candidate in ('C', 'D'):
                    c = current[candidate]
                    gates.append({
                        'gate': 'preserve_current_B1', 'lead_hour': lead,
                        'threshold_mm': threshold, 'candidate': candidate, 'baseline': 'A',
                        'candidate_CSI_num': c['csi_numerator'],
                        'candidate_CSI_den': c['csi_denominator'],
                        'baseline_CSI_num': a['csi_numerator'],
                        'baseline_CSI_den': a['csi_denominator'],
                        'satisfied': c['csi_numerator'] * a['csi_denominator']
                        >= a['csi_numerator'] * c['csi_denominator'],
                    })
            if lead >= 2 and threshold in (0.1, 0.5, 1.0):
                original = current['ORIGINAL']
                for candidate in ('C', 'D'):
                    c = current[candidate]
                    gates.append({
                        'gate': 'recover_vs_ORIGINAL', 'lead_hour': lead,
                        'threshold_mm': threshold, 'candidate': candidate,
                        'baseline': 'ORIGINAL',
                        'candidate_CSI_num': c['csi_numerator'],
                        'candidate_CSI_den': c['csi_denominator'],
                        'baseline_CSI_num': original['csi_numerator'],
                        'baseline_CSI_den': original['csi_denominator'],
                        'satisfied': c['csi_numerator'] * original['csi_denominator']
                        >= original['csi_numerator'] * c['csi_denominator'],
                    })

        for candidate, baseline in PAIRS:
            old = values[baseline] >= 0.1
            new = values[candidate] >= 0.1
            transitions.append({
                'lead_hour': lead, 'comparison': f'{candidate}-{baseline}',
                'weak_observed_points': int(weak_obs.sum()),
                'weak_detection_gains': int(np.count_nonzero(weak_obs & ~old & new)),
                'weak_detection_losses': int(np.count_nonzero(weak_obs & old & ~new)),
                'dry_observed_points': int(dry_obs.sum()),
                'dry_new_false_alarms': int(np.count_nonzero(dry_obs & ~old & new)),
                'dry_resolved_false_alarms': int(np.count_nonzero(dry_obs & old & ~new)),
            })
    require((len(categorical), len(continuous), len(contrasts), len(transitions), len(gates))
            == (180, 30, 180, 24, 52), 'independent recount row grid differs')
    return {'categorical_scores.csv': categorical,
            'continuous_scores.csv': continuous,
            'contrasts.csv': contrasts,
            'weak_transition_counts.csv': transitions,
            'gate_results.csv': gates}


def key_for(row: dict, fields: tuple[str, ...]) -> tuple:
    key = []
    for field in fields:
        value = row[field]
        key.append(float(value) if field == 'threshold_mm' else int(value) if field == 'lead_hour' else value)
    return tuple(key)


def parse_scalar(value: str):
    if value == '':
        return None
    if value in ('True', 'False'):
        return value == 'True'
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value


def compare_table(path: Path, expected: list[dict], key_fields: tuple[str, ...]) -> dict:
    with path.open('r', encoding='utf-8', newline='') as stream:
        actual_rows = list(csv.DictReader(stream))
    actual = {key_for(row, key_fields): row for row in actual_rows}
    expected_by_key = {key_for(row, key_fields): row for row in expected}
    require(len(actual) == len(actual_rows) == len(expected_by_key) == len(expected),
            f'{path.name}: duplicate or missing rows')
    require(set(actual) == set(expected_by_key), f'{path.name}: row keys differ')
    mismatches = []
    for key, expected_row in expected_by_key.items():
        actual_row = actual[key]
        require(set(actual_row) == set(expected_row), f'{path.name}/{key}: columns differ')
        for field, expected_value in expected_row.items():
            observed_value = parse_scalar(actual_row[field])
            if isinstance(expected_value, float):
                same = (observed_value is not None and math.isclose(
                    float(observed_value), expected_value,
                    rel_tol=FLOAT_TOLERANCE, abs_tol=FLOAT_TOLERANCE))
            else:
                same = observed_value == expected_value
            if not same:
                mismatches.append({'key': key, 'field': field,
                                   'expected': expected_value, 'observed': observed_value})
    require(not mismatches, f'{path.name}: {len(mismatches)} independent recount mismatches')
    return {'rows': len(expected), 'mismatches': 0, 'sha256': digest(path)}


def winner(gates: list[dict], categorical: list[dict]) -> dict:
    qualified = []
    for candidate in ('C', 'D'):
        candidate_gates = [r for r in gates if r['candidate'] == candidate]
        require(len(candidate_gates) == 26, f'{candidate}: expected 26 separate gates')
        if all(r['satisfied'] for r in candidate_gates):
            qualified.append(candidate)
    priority = [(1, 10.0), *((lead, 10.0) for lead in range(2, 7)),
                *((lead, 5.0) for lead in range(1, 7))]
    if not qualified:
        return {'winner': 'B1_RETAINED', 'qualified_candidates': [],
                'selection_rule': 'No candidate passed all 26 frozen cells; retain current B1.'}
    cells = {(r['lead_hour'], r['threshold_mm'], r['case']): r for r in categorical}
    vectors = {candidate: tuple(Fraction(
        cells[(lead, threshold, candidate)]['csi_numerator'],
        cells[(lead, threshold, candidate)]['csi_denominator'])
        for lead, threshold in priority) for candidate in qualified}
    best = max(vectors.values())
    tied = [candidate for candidate, values in vectors.items() if values == best]
    selected = 'C' if 'C' in tied else tied[0]
    return {'winner': selected, 'qualified_candidates': sorted(qualified),
            'priority_cells': [{'lead_hour': lead, 'threshold_mm': threshold}
                               for lead, threshold in priority],
            'selection_rule': 'Among candidates passing all 26 gates, lexicographically maximize exact CSI at +1 h/10 mm, then +2..+6 h/10 mm, then +1..+6 h/5 mm; a full tie prefers C.'}


def verify_and_recount(result_dir: Path, output_dir: Path) -> dict:
    require(not output_dir.exists(), f'refusing existing recount directory: {output_dir}')
    receipt, hourly = verify_result_bundle(result_dir)
    tables = recount(hourly)
    table_reports = {}
    for name, key_fields in CSV_TABLES.items():
        table_reports[name] = compare_table(result_dir / name, tables[name], key_fields)
    expected_winner = winner(tables['gate_results.csv'], tables['categorical_scores.csv'])
    observed_winner = json.loads((result_dir / 'winner.json').read_text(encoding='utf-8'))
    require(observed_winner == expected_winner, 'winner.json differs from independent exact-ratio decision')
    output_dir.mkdir(parents=True)
    for name, rows in tables.items():
        fields = list(rows[0])
        with (output_dir / name).open('x', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    (output_dir / 'winner.json').write_text(json.dumps(expected_winner, indent=2, sort_keys=True) + '\n')
    report = {
        'schema': 'cp02_grouped_independent_recount_v1', 'status': 'PASS',
        'evaluation_plan_sha256': PLAN_SHA256,
        'result_receipt_sha256': digest(result_dir / 'receipt.json'),
        'result_inputs_verified': len(receipt['inputs']),
        'result_arrays_verified': len(HOURS), 'points_per_hour': POINTS,
        'rows': {'categorical': len(tables['categorical_scores.csv']),
                 'continuous': len(tables['continuous_scores.csv']),
                 'contrasts': len(tables['contrasts.csv']),
                 'weak_transitions': len(tables['weak_transition_counts.csv']),
                 'gates': len(tables['gate_results.csv'])},
        'source_table_comparisons': table_reports,
        'winner_independent': expected_winner,
        'winner_source_matches': True,
        'recount_output_hashes': {p.name: digest(p) for p in sorted(output_dir.iterdir())},
    }
    (output_dir / 'recount_receipt.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--result-dir', type=Path, required=True,
                        help='complete production result directory with receipt.json')
    parser.add_argument('--output-dir', type=Path, required=True,
                        help='new, absent directory under review/ for independent outputs')
    args = parser.parse_args()
    print(json.dumps(verify_and_recount(args.result_dir, args.output_dir), indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
