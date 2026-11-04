#!/usr/bin/env python3
"""Recount frozen scores and write complete paired transition regimes."""
from __future__ import annotations

import argparse
import collections
import csv
from fractions import Fraction
import gzip
import hashlib
import io
import json
import math
import os
from pathlib import Path
import shutil
import tempfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'docs/evidence/cp02_failure_regimes_20261104/transitions'
PROTOCOL = EVIDENCE / 'protocol.json'
PROTOCOL_SHA256 = '7951cec54525031d949a11204ffa11a793a0fa745545cb9835005c53f2c73753'
SOURCE = ROOT / 'docs/evidence/cp02_rain_number_process_20261104/followup/analysis_dm065'
OLD = ROOT / 'docs/evidence/cp02_state_path_20261104/candidate/analysis'
BASE = 'IMPROVED_BG_FIXED'
PRIOR = 'B1_RAIN_NUMBER_PRIOR'
DM = 'B1_RAIN_NUMBER_DM065'
CASES = ('ORIGINAL', BASE, PRIOR, DM)
COMPARISONS = ('ORIGINAL', PRIOR, DM)
THRESHOLDS = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0)
BANDS = ('[0,0.1)', '[0.1,1)', '[1,5)', '[5,infinity)')
LABELS = ('retained_hit', 'lost_hit', 'gained_hit', 'both_miss',
          'retained_false_alarm', 'removed_false_alarm', 'new_false_alarm', 'retained_correct_negative')
COLUMNS = ('lead_hour', 'threshold_mm', 'comparison', 'flat_index_yx', 'latitude', 'longitude',
           'reference_mm', 'original_mm', 'b1_mm', 'prior_mm', 'dm065_mm', 'observed_band',
           'reference_event', 'baseline_event', 'candidate_event', 'transition')


class RegimeError(ValueError):
    pass


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def csv_rows(path, key_fields, expected):
    with Path(path).open(newline='', encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream))
    keys = [tuple(row[k] for k in key_fields) for row in rows]
    if len(rows) != expected or len(set(keys)) != expected:
        raise RegimeError(f'{path}: wrong or duplicate row inventory')
    return rows


def input_pins(protocol_path=PROTOCOL):
    if sha(protocol_path) != PROTOCOL_SHA256:
        raise RegimeError('frozen protocol SHA differs')
    protocol = json.loads(Path(protocol_path).read_text())
    if (protocol.get('status') != 'FROZEN_BEFORE_TRANSITION_OUTPUT' or
        protocol.get('sample_count') != 3688 or protocol.get('target_grid_yx') != [253, 149] or
        protocol.get('thresholds_mm') != list(THRESHOLDS) or
        protocol.get('leads_hours') != list(range(1, 7)) or
        protocol.get('comparisons') != list(COMPARISONS) or
        protocol.get('row_columns') != list(COLUMNS)):
        raise RegimeError('protocol scope differs')
    pins = protocol['inputs']
    for rel, record in pins.items():
        path = ROOT / rel
        if path.is_symlink() or not path.is_file() or path.stat().st_size != record['size_bytes'] or sha(path) != record['sha256']:
            raise RegimeError(f'frozen input differs: {rel}')
    return protocol


def load_arrays(source=SOURCE, expected_points=3688, grid=(253, 149)):
    arrays, coordinates = {}, None
    keys = set(CASES) | {'reference', 'latitude', 'longitude', 'flat_index_yx'}
    for hour in range(13, 19):
        with np.load(source / f'hour_{hour}_arrays.npz', allow_pickle=False) as archive:
            if set(archive.files) != keys:
                raise RegimeError(f'{hour}: input context inventory differs')
            data = {name: np.array(archive[name], copy=True) for name in archive.files}
        if any(a.shape != (expected_points,) for a in data.values()):
            raise RegimeError(f'{hour}: input point shape differs')
        if any(not np.isfinite(a).all() for a in data.values()):
            raise RegimeError(f'{hour}: nonfinite input')
        ids = data['flat_index_yx']
        if (not np.issubdtype(ids.dtype, np.integer) or len(np.unique(ids)) != expected_points or
            np.any(ids < 0) or np.any(ids >= grid[0] * grid[1])):
            raise RegimeError(f'{hour}: duplicate or invalid flat index')
        if any(np.any(data[name] < 0) for name in (*CASES, 'reference')):
            raise RegimeError(f'{hour}: negative precipitation')
        now = tuple(data[name] for name in ('flat_index_yx', 'latitude', 'longitude'))
        if coordinates is None:
            coordinates = tuple(x.copy() for x in now)
        elif any(not np.array_equal(a, b) for a, b in zip(coordinates, now)):
            raise RegimeError(f'{hour}: paired contexts differ across leads')
        arrays[hour] = data
    return arrays


def transitions(observed, baseline, candidate, threshold):
    ref = observed >= threshold
    old = baseline >= threshold
    new = candidate >= threshold
    result = np.full(observed.shape, '', dtype='<U32')
    for mask, label in ((ref & old & new, LABELS[0]), (ref & old & ~new, LABELS[1]),
                        (ref & ~old & new, LABELS[2]), (ref & ~old & ~new, LABELS[3]),
                        (~ref & old & new, LABELS[4]), (~ref & old & ~new, LABELS[5]),
                        (~ref & ~old & new, LABELS[6]), (~ref & ~old & ~new, LABELS[7])):
        result[mask] = label
    if np.any(result == ''):
        raise RegimeError('incomplete transition partition')
    return result


def observed_band(values):
    return np.asarray(BANDS)[np.searchsorted([0.1, 1.0, 5.0], values, side='right')]


def score_counts(observed, predicted, threshold):
    ref, pred = observed >= threshold, predicted >= threshold
    hit = int(np.count_nonzero(ref & pred))
    miss = int(np.count_nonzero(ref & ~pred))
    false = int(np.count_nonzero(~ref & pred))
    denominator = hit + miss + false
    if not denominator:
        raise RegimeError('undefined CSI on a required threshold')
    return hit, miss, false, Fraction(hit, denominator)


def validate_scores(arrays, source=SOURCE, old=OLD, expected_points=3688):
    cats = csv_rows(source / 'categorical_scores.csv', ('lead_hour', 'threshold_mm', 'case'), 144)
    conts = csv_rows(source / 'continuous_scores.csv', ('lead_hour', 'case'), 24)
    admissions = csv_rows(source / 'admission_constraints.csv', ('goal', 'lead_hour', 'threshold_mm'), 26)
    previous = csv_rows(old / 'admission_constraints.csv', ('goal', 'lead_hour', 'threshold_mm'), 26)
    by_cat = {(int(r['lead_hour']), float(r['threshold_mm']), r['case']): r for r in cats}
    by_cont = {(int(r['lead_hour']), r['case']): r for r in conts}
    scores = {}
    eps = np.finfo(np.float64).eps / 2
    gamma = expected_points * eps / (1 - expected_points * eps)
    for hour, data in arrays.items():
        lead = hour - 12
        for case in CASES:
            prediction, ref = data[case], data['reference']
            errors = prediction.astype(np.float64) - ref.astype(np.float64)
            mae = math.fsum(abs(float(x)) for x in errors) / expected_points
            rmse = math.sqrt(math.fsum(float(x) * float(x) for x in errors) / expected_points)
            row = by_cont[lead, case]
            stored_mae, stored_rmse = float(row['MAE_mm']), float(row['RMSE_mm'])
            if (not math.isfinite(stored_mae) or not math.isfinite(stored_rmse) or
                abs(stored_mae - mae) > gamma * mae + 4 * math.ulp(mae) or
                abs(stored_rmse - rmse) > gamma * rmse + 4 * math.ulp(rmse)):
                raise RegimeError('continuous score does not recount')
            for threshold in THRESHOLDS:
                hit, miss, false, fraction = score_counts(ref, prediction, threshold)
                row = by_cat[lead, threshold, case]
                if ((int(row['points']), int(row['hit']), int(row['miss']), int(row['false_alarm'])) !=
                    (expected_points, hit, miss, false) or float(row['CSI']) != float(fraction)):
                    raise RegimeError('categorical score does not recount')
                scores[lead, threshold, case] = (hit, miss, false, fraction)
    def check_admission(rows, candidate):
        keys = set()
        for row in rows:
            lead, threshold, goal = int(row['lead_hour']), float(row['threshold_mm']), row['goal']
            protect = lead == 1 or threshold == 5
            recover = lead >= 2 and threshold in (0.1, 0.5, 1.0)
            expected_goal = 'preserve_current_B1' if protect else 'recover_low_threshold_vs_ORIGINAL' if recover else None
            if goal != expected_goal or expected_goal is None:
                raise RegimeError('admission scope differs')
            baseline = BASE if protect else 'ORIGINAL'
            got, control = scores[lead, threshold, candidate][3], scores[lead, threshold, baseline][3]
            if (row['baseline'] != baseline or row['satisfied'] != str(got >= control) or
                float(row['candidate_CSI']) != float(got) or float(row['baseline_CSI']) != float(control)):
                raise RegimeError('admission fraction does not recount')
            keys.add((lead, threshold))
        wanted = {(h, t) for h in range(1, 7) for t in THRESHOLDS
                  if h == 1 or t == 5 or (h >= 2 and t in (0.1, 0.5, 1.0))}
        if keys != wanted:
            raise RegimeError('incomplete admission keys')
    check_admission(admissions, DM)
    check_admission(previous, PRIOR)
    return scores


def focus_group(lead, threshold, band, label):
    if lead in (2, 3) and threshold == .1:
        if band == BANDS[1] and label in LABELS[:4]:
            return f'lead{lead}_weak'
        if band == BANDS[0] and label in LABELS[4:7]:
            return f'lead{lead}_false_alarm'
    if lead == 5 and threshold == 5 and band == BANDS[3] and label in LABELS[:3]:
        return 'lead5_heavy'
    return ''


def write_csv(path, fieldnames, rows):
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def run(output=EVIDENCE / 'results'):
    output = Path(output)
    if os.path.lexists(output):
        raise RegimeError('output already exists')
    protocol = input_pins()
    arrays = load_arrays()
    scores = validate_scores(arrays)
    recovery = []
    for lead in range(2, 7):
        for threshold in (0.1, 0.5, 1.0):
            original = scores[lead, threshold, 'ORIGINAL'][3]
            fractions = {case: scores[lead, threshold, case][3] for case in (BASE, PRIOR, DM)}
            recovery.append({'lead_hour': lead, 'threshold_mm': threshold,
                             'baseline_recovered': fractions[BASE] >= original,
                             'prior_recovered': fractions[PRIOR] >= original,
                             'dm065_recovered': fractions[DM] >= original,
                             'newly_recovered_vs_b1': fractions[BASE] < original <= fractions[DM],
                             'original_csi': float(original), 'baseline_csi': float(fractions[BASE]),
                             'prior_csi': float(fractions[PRIOR]), 'dm065_csi': float(fractions[DM])})
    if (sum(x['baseline_recovered'] for x in recovery), sum(x['dm065_recovered'] for x in recovery),
        sum(x['newly_recovered_vs_b1'] for x in recovery)) != (2, 2, 0):
        raise RegimeError('recovery result differs from declared frozen comparison')
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.regimes-', dir=output.parent))
    try:
        counts, focused, count_total = [], [], 0
        for hour, data in arrays.items():
            lead = hour - 12
            bands = observed_band(data['reference'])
            with (stage / f'lead_{lead}_point_transitions.csv.gz').open('wb') as raw:
                with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as zipped:
                    with io.TextIOWrapper(zipped, encoding='utf-8', newline='') as stream:
                        writer = csv.DictWriter(stream, fieldnames=COLUMNS, lineterminator='\n')
                        writer.writeheader()
                        for threshold in THRESHOLDS:
                            for case in COMPARISONS:
                                labels = transitions(data['reference'], data[BASE], data[case], threshold)
                                frequency = collections.Counter(zip(bands, labels))
                                for band in BANDS:
                                    for label in LABELS:
                                        counts.append({'lead_hour': lead, 'threshold_mm': threshold,
                                                       'comparison': case, 'observed_band': band,
                                                       'transition': label, 'count': frequency[band, label]})
                                for i, label in enumerate(labels):
                                    row = {'lead_hour': lead, 'threshold_mm': threshold, 'comparison': case,
                                           'flat_index_yx': int(data['flat_index_yx'][i]),
                                           'latitude': float(data['latitude'][i]), 'longitude': float(data['longitude'][i]),
                                           'reference_mm': float(data['reference'][i]), 'original_mm': float(data['ORIGINAL'][i]),
                                           'b1_mm': float(data[BASE][i]), 'prior_mm': float(data[PRIOR][i]),
                                           'dm065_mm': float(data[DM][i]), 'observed_band': bands[i],
                                           'reference_event': bool(data['reference'][i] >= threshold),
                                           'baseline_event': bool(data[BASE][i] >= threshold),
                                           'candidate_event': bool(data[case][i] >= threshold), 'transition': label}
                                    writer.writerow(row)
                                    group = focus_group(lead, threshold, bands[i], label)
                                    if group:
                                        focused.append({'focus_group': group, **row})
                                    count_total += 1
        if count_total != protocol['full_ledger_rows']:
            raise RegimeError('complete transition row count differs')
        write_csv(stage / 'transition_counts.csv', ('lead_hour','threshold_mm','comparison','observed_band','transition','count'), counts)
        write_csv(stage / 'focus_membership.csv', ('focus_group', *COLUMNS), focused)
        write_csv(stage / 'recovery_conditions.csv', tuple(recovery[0]), recovery)
        input_pins()
        summary = {'status':'PASS', 'scope':'one event; paired point descriptions, no causal attribution',
                   'sample_count':3688, 'point_rows':count_total, 'count_rows':len(counts),
                   'focus_rows':len(focused), 'categorical_rows_recounted':144,
                   'continuous_rows_recounted':24, 'admission_rows_recounted':52,
                   'baseline_recovered':2, 'baseline_deficits':13, 'dm065_recovered':2,
                   'newly_recovered_vs_b1':0, 'prior_recovered':sum(r['prior_recovered'] for r in recovery),
                   'protocol_sha256':PROTOCOL_SHA256, 'source_sha256':sha(Path(__file__)),
                   'outputs':{p.name:{'sha256':sha(p),'size_bytes':p.stat().st_size} for p in sorted(stage.iterdir())}}
        (stage / 'receipt.json').write_text(json.dumps(summary, indent=2, sort_keys=True)+'\n')
        os.rename(stage, output)
        return summary
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=EVIDENCE / 'results')
    args = parser.parse_args()
    print(json.dumps(run(args.output), sort_keys=True))


if __name__ == '__main__':
    main()
