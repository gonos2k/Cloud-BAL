#!/usr/bin/env python3
"""Independently recount frozen four-case hourly outputs one sample at a time."""
from __future__ import annotations

import argparse
import csv
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path

import numpy as np

CASES = ('ORIGINAL', 'IMPROVED_BG_FIXED', 'B1_RAIN_NUMBER_PRIOR', 'B1_RAIN_NUMBER_DM065')
THRESHOLDS = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def keyed_csv(path, fields):
    with Path(path).open(newline='', encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream))
    keyed = {tuple(row[field] for field in fields): row for row in rows}
    if len(keyed) != len(rows):
        raise ValueError(f'{path}: duplicate score keys')
    return rows, keyed


def recount(analysis, plan, plan_sha256, output):
    analysis, plan, output = map(Path, (analysis, plan, output))
    if output.exists() or output.is_symlink():
        raise FileExistsError(output)
    if sha(plan) != plan_sha256:
        raise ValueError('frozen evaluation plan changed')
    names = [f'hour_{hour}_arrays.npz' for hour in range(13, 19)]
    names += ['categorical_scores.csv', 'continuous_scores.csv', 'admission_constraints.csv', 'winner.json', 'receipt.json']
    pins = {name: sha(analysis / name) for name in names}
    cat_rows, categorical = keyed_csv(analysis / 'categorical_scores.csv', ('lead_hour', 'threshold_mm', 'case'))
    cont_rows, continuous = keyed_csv(analysis / 'continuous_scores.csv', ('lead_hour', 'case'))
    con_rows, constraints = keyed_csv(analysis / 'admission_constraints.csv', ('lead_hour', 'threshold_mm', 'goal'))
    if (len(cat_rows), len(cont_rows), len(con_rows)) != (144, 24, 26):
        raise ValueError('score row counts differ from 144/24/26')
    exact, max_mae_residual, max_rmse_residual = {}, 0., 0.
    eps = np.finfo(np.float64).eps / 2
    gamma = (3688 * eps) / (1 - 3688 * eps)
    coordinates = None
    for hour in range(13, 19):
        lead = hour - 12
        with np.load(analysis / f'hour_{hour}_arrays.npz', allow_pickle=False) as archive:
            needed = set(CASES) | {'reference', 'latitude', 'longitude', 'flat_index_yx'}
            if set(archive.files) != needed:
                raise ValueError(f'{hour}: archive context inventory mismatch')
            arrays = {name: np.asarray(archive[name]) for name in archive.files}
        if any(value.shape != (3688,) for value in arrays.values()):
            raise ValueError(f'{hour}: archive does not contain 3688 paired values')
        if any(not np.isfinite(value).all() for value in arrays.values()):
            raise ValueError(f'{hour}: nonfinite paired value')
        if len(np.unique(arrays['flat_index_yx'])) != 3688:
            raise ValueError(f'{hour}: duplicate paired sample index')
        current = tuple(arrays[name] for name in ('flat_index_yx', 'latitude', 'longitude'))
        if coordinates is None:
            coordinates = tuple(value.copy() for value in current)
        elif any(not np.array_equal(a, b) for a, b in zip(coordinates, current)):
            raise ValueError(f'{hour}: paired sample coordinates changed')
        for case in CASES:
            counts = [[0, 0, 0] for _ in THRESHOLDS]
            errors, squares = [], []
            for index in range(3688):
                prediction = float(arrays[case][index])
                reference = float(arrays['reference'][index])
                error = prediction - reference
                errors.append(abs(error))
                squares.append(error * error)
                for n, threshold in enumerate(THRESHOLDS):
                    obs, pred = reference >= threshold, prediction >= threshold
                    counts[n][0] += int(obs and pred)
                    counts[n][1] += int(obs and not pred)
                    counts[n][2] += int(not obs and pred)
            absolute_sum, square_sum = math.fsum(errors), math.fsum(squares)
            mae = absolute_sum / 3688
            rmse = math.sqrt(square_sum / 3688)
            row = continuous[(str(lead), case)]
            mdiff, rdiff = abs(float(row['MAE_mm']) - mae), abs(float(row['RMSE_mm']) - rmse)
            max_mae_residual, max_rmse_residual = max(max_mae_residual, mdiff), max(max_rmse_residual, rdiff)
            mae_bound = gamma * (absolute_sum / 3688) + 4 * math.ulp(mae)
            rmse_bound = gamma * rmse + 4 * math.ulp(rmse)
            if mdiff > mae_bound or rdiff > rmse_bound:
                raise ValueError(f'{lead}/{case}: continuous score exceeds rounding bound')
            for threshold, (hit, miss, false) in zip(THRESHOLDS, counts):
                denominator = hit + miss + false
                if not denominator:
                    raise ValueError('required CSI is undefined')
                row = categorical[(str(lead), str(threshold), case)]
                if (int(row['points']), int(row['hit']), int(row['miss']), int(row['false_alarm'])) != (3688, hit, miss, false):
                    raise ValueError(f'{lead}/{threshold}/{case}: categorical count mismatch')
                if float(row['CSI']) != hit / denominator:
                    raise ValueError('stored CSI differs from exact counts')
                exact[(lead, threshold, case)] = Fraction(hit, denominator)
    passed = 0
    for lead in range(1, 7):
        for threshold in THRESHOLDS:
            protect = lead == 1 or threshold == 5
            recover = lead >= 2 and threshold in (0.1, 0.5, 1.0)
            if not (protect or recover):
                continue
            goal = 'preserve_current_B1' if protect else 'recover_low_threshold_vs_ORIGINAL'
            baseline = 'IMPROVED_BG_FIXED' if protect else 'ORIGINAL'
            row = constraints[(str(lead), str(threshold), goal)]
            correct = exact[(lead, threshold, CASES[-1])] >= exact[(lead, threshold, baseline)]
            if (row['baseline'] != baseline or row['satisfied'] != str(correct)
                or float(row['candidate_CSI']) != float(exact[(lead, threshold, CASES[-1])])
                or float(row['baseline_CSI']) != float(exact[(lead, threshold, baseline)])):
                raise ValueError('constraint differs from exact count comparison')
            passed += correct
    winner = json.loads((analysis / 'winner.json').read_text())
    if (winner['qualified'] != (passed == 26) or winner['passed_constraints'] != passed
        or winner['required_constraints'] != 26 or winner['candidate'] != CASES[-1]
        or winner['selection'] != (CASES[-1] if passed == 26 else 'NO_QUALIFIED_CANDIDATE')):
        raise ValueError('winner differs from exact admission recount')
    if sha(plan) != plan_sha256 or any(sha(analysis / name) != digest for name, digest in pins.items()):
        raise ValueError('frozen inputs changed during independent recount')
    report = {'status': 'PASS', 'method': 'independent per-sample scalar recount with exact Fraction constraints',
              'plan_sha256': plan_sha256, 'input_sha256': pins, 'cases': list(CASES),
              'rows': {'categorical': 144, 'continuous': 24, 'constraints': 26},
              'passed_constraints': passed, 'max_mae_roundoff': max_mae_residual,
              'max_rmse_roundoff': max_rmse_residual, 'float64_gamma_n': gamma}
    with output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write('\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--analysis', required=True, type=Path)
    parser.add_argument('--plan', required=True, type=Path)
    parser.add_argument('--plan-sha256', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(recount(args.analysis, args.plan, args.plan_sha256, args.output), sort_keys=True))


if __name__ == '__main__':
    main()
