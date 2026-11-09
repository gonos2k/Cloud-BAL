#!/usr/bin/env python3
"""Build receipt-bound full OLD/FIX categorical score tables."""
from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
import tempfile
import shutil

import numpy as np

BUNDLE = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[4]
COHORTS = BUNDLE / 'cohorts'
OUTPUT = BUNDLE / 'tables'
COHORT_RECEIPT_SHA256 = 'cd1e03fbc075c25f6a4904ce278935dea8d23a2157162274835fca21fc911826'
SCORE_SHA256 = 'b6483f53b24e96cf5c75a9ef618b4c4090dcbb43f59198e9470c596bd4c0fe2f'
TRANSITION_SHA256 = '8bfba6b20924f34a73fe119f3ed793c7ed537dcdd9104c41ca1fcf89e4928ae3'
HOURS = tuple(range(13, 19))
THRESHOLDS = ('0.1', '0.5', '1.0', '2.5', '5.0', '10.0')
COMPARISONS = {
    'ORIGINAL_to_FIX': {
        'initialization': '규준실험 초기장',
        'old_case': 'ORIGINAL',
        'fix_case': 'FIXED_ORIGINAL_100',
        'old_label': 'ORIGINAL (규준실험)',
        'fix_label': 'FIX (수정 후)',
    },
    'X_to_A': {
        'initialization': '현재 B1 초기장',
        'old_case': 'ORIGINAL_B1_100',
        'fix_case': 'IMPROVED_BG_FIXED',
        'old_label': 'X = B1_OLD_KDM6 (기존 B1)',
        'fix_label': 'A = 현재 B1 (FIX)',
    },
}


class TableError(ValueError):
    """A frozen input, key, or arithmetic check failed."""


def sha256(path: Path) -> str:
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read_csv(path: Path, required: set[str]) -> list[dict[str, str]]:
    with path.open(newline='', encoding='utf-8') as stream:
        reader = csv.DictReader(stream)
        if not required <= set(reader.fieldnames or ()):
            raise TableError(f'{path.name}: required columns are missing')
        rows = list(reader)
    if not rows:
        raise TableError(f'{path.name}: no data rows')
    return rows


def load_frozen_inputs() -> tuple[dict, list[dict[str, str]], list[dict[str, str]], dict[str, str]]:
    receipt_path = COHORTS / 'receipt.json'
    if sha256(receipt_path) != COHORT_RECEIPT_SHA256:
        raise TableError('cohort receipt hash differs from the frozen receipt')
    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    if receipt.get('status') != 'COMPLETE' or receipt.get('hours_utc') != list(HOURS):
        raise TableError('cohort receipt status or hour inventory differs')
    source_hashes = {}
    for relative, expected in receipt.get('inputs', {}).items():
        path = ROOT / relative
        if not path.is_file() or sha256(path) != expected:
            raise TableError(f'receipt-bound source differs: {relative}')
    for name, expected in (('categorical_scores.csv', SCORE_SHA256),
                           ('transitions.csv', TRANSITION_SHA256)):
        path = COHORTS / name
        actual = sha256(path)
        if actual != expected or receipt.get('outputs', {}).get(name) != actual:
            raise TableError(f'{name}: source hash differs from frozen receipt')
        source_hashes[name] = actual
    scores = read_csv(COHORTS / 'categorical_scores.csv',
                      {'valid_hour_utc', 'lead_hour', 'comparison', 'threshold_mm', 'n',
                       'hit', 'miss', 'false_alarm', 'correct_negative', 'CSI'})
    transitions = read_csv(COHORTS / 'transitions.csv',
                           {'valid_hour_utc', 'lead_hour', 'comparison', 'threshold_mm',
                            'observed_points', 'hit_gains', 'hit_losses',
                            'new_false_alarms', 'resolved_false_alarms'})
    source_hashes['receipt.json'] = sha256(receipt_path)
    return receipt, scores, transitions, source_hashes


def count_events(reference: np.ndarray, forecast: np.ndarray, threshold: float) -> dict[str, int]:
    observed = reference >= threshold
    predicted = forecast >= threshold
    return {
        'observed_points': int(observed.sum()),
        'hit': int(np.count_nonzero(observed & predicted)),
        'miss': int(np.count_nonzero(observed & ~predicted)),
        'false_alarm': int(np.count_nonzero(~observed & predicted)),
        'correct_negative': int(np.count_nonzero(~observed & ~predicted)),
    }


def recount_source_arrays(receipt: dict) -> tuple[dict, dict[str, str]]:
    arrays_by_key = {}
    array_hashes = {}
    canonical_flat = None
    for hour in HOURS:
        relative = f'docs/evidence/weak_strong_balance_20261030/analysis/hour_{hour}_arrays.npz'
        expected_hash = receipt.get('inputs', {}).get(relative)
        path = ROOT / relative
        if not expected_hash or not path.is_file() or sha256(path) != expected_hash:
            raise TableError(f'hour {hour}: weak/strong source array is not receipt-bound')
        with np.load(path, allow_pickle=False) as data:
            required = {'flat_index_yx', 'reference'} | {
                case for spec in COMPARISONS.values() for case in (spec['old_case'], spec['fix_case'])}
            if not required <= set(data.files):
                raise TableError(f'hour {hour}: required forecast arrays are missing')
            flat = np.asarray(data['flat_index_yx'])
            reference = np.asarray(data['reference'], dtype=np.float64)
            forecasts = {case: np.asarray(data[case], dtype=np.float64)
                         for spec in COMPARISONS.values() for case in (spec['old_case'], spec['fix_case'])}
        if (flat.shape != (3688,) or len(np.unique(flat)) != 3688 or reference.shape != flat.shape
            or not np.isfinite(reference).all()
            or any(values.shape != flat.shape or not np.isfinite(values).all()
                   for values in forecasts.values())):
            raise TableError(f'hour {hour}: invalid canonical full-grid forecast arrays')
        if canonical_flat is not None and not np.array_equal(flat, canonical_flat):
            raise TableError(f'hour {hour}: canonical grid ordering differs across input arrays')
        canonical_flat = flat
        arrays_by_key[hour] = {'reference': reference, **forecasts}
        array_hashes[relative] = expected_hash
    return arrays_by_key, array_hashes


def score_maps(scores: list[dict[str, str]], transitions: list[dict[str, str]]) -> tuple[dict, dict]:
    expected = {(str(hour), comparison, threshold)
                for hour in HOURS for comparison in COMPARISONS for threshold in THRESHOLDS}
    score_map, transition_map = {}, {}
    for rows, target in ((scores, score_map), (transitions, transition_map)):
        for row in rows:
            if row['comparison'] not in COMPARISONS:
                continue
            key = (row['valid_hour_utc'], row['comparison'], row['threshold_mm'])
            if key in target:
                raise TableError(f'duplicate selected score key: {key}')
            target[key] = row
        if set(target) != expected:
            raise TableError(f'incomplete selected table keys: expected {len(expected)}, got {len(target)}')
    return score_map, transition_map


def prepare_rows(receipt: dict, scores: list[dict[str, str]], transitions: list[dict[str, str]]) -> tuple[dict, dict[str, str]]:
    score_map, transition_map = score_maps(scores, transitions)
    arrays, array_hashes = recount_source_arrays(receipt)
    output = {}
    for hour in HOURS:
        for comparison, spec in COMPARISONS.items():
            data = arrays[hour]
            for threshold_text in THRESHOLDS:
                key = (str(hour), comparison, threshold_text)
                score, transition = score_map[key], transition_map[key]
                threshold = float(threshold_text)
                old_raw = count_events(data['reference'], data[spec['old_case']], threshold)
                fix_raw = count_events(data['reference'], data[spec['fix_case']], threshold)
                target = {name: int(score[field]) for name, field in
                          (('hit', 'hit'), ('miss', 'miss'), ('false_alarm', 'false_alarm'),
                           ('correct_negative', 'correct_negative'))}
                n = int(score['n'])
                if n != 3688 or fix_raw != {'observed_points': old_raw['observed_points'], **target}:
                    raise TableError(f'{key}: FIX score CSV does not match the raw full-grid recount')
                target_denom = target['hit'] + target['miss'] + target['false_alarm']
                target_csi = target['hit'] / target_denom if target_denom else 0.0
                if not np.isclose(float(score['CSI']), target_csi, rtol=0, atol=1e-12):
                    raise TableError(f'{key}: FIX CSV CSI does not match its contingency counts')
                observed = int(transition['observed_points'])
                if observed != old_raw['observed_points']:
                    raise TableError(f'{key}: transition observed count differs from raw reference')
                old_hit = target['hit'] - int(transition['hit_gains']) + int(transition['hit_losses'])
                old_false = target['false_alarm'] - int(transition['new_false_alarms']) + int(transition['resolved_false_alarms'])
                old_miss = observed - old_hit
                old_correct = n - observed - old_false
                old = {'hit': old_hit, 'miss': old_miss, 'false_alarm': old_false,
                       'correct_negative': old_correct, 'observed_points': observed}
                if min(old.values()) < 0 or sum(old[name] for name in
                        ('hit', 'miss', 'false_alarm', 'correct_negative')) != n:
                    raise TableError(f'{key}: reconstructed OLD contingency counts are invalid')
                if old != old_raw:
                    raise TableError(f'{key}: transition-derived OLD scores differ from raw-array recount')
                before = count_events(data['reference'], data[spec['old_case']], threshold)
                after = count_events(data['reference'], data[spec['fix_case']], threshold)
                gains = int(np.count_nonzero((data['reference'] >= threshold)
                                             & (data[spec['old_case']] < threshold)
                                             & (data[spec['fix_case']] >= threshold)))
                losses = int(np.count_nonzero((data['reference'] >= threshold)
                                              & (data[spec['old_case']] >= threshold)
                                              & (data[spec['fix_case']] < threshold)))
                new_fa = int(np.count_nonzero((data['reference'] < threshold)
                                              & (data[spec['old_case']] < threshold)
                                              & (data[spec['fix_case']] >= threshold)))
                resolved_fa = int(np.count_nonzero((data['reference'] < threshold)
                                                   & (data[spec['old_case']] >= threshold)
                                                   & (data[spec['fix_case']] < threshold)))
                if (gains != int(transition['hit_gains']) or losses != int(transition['hit_losses'])
                    or new_fa != int(transition['new_false_alarms'])
                    or resolved_fa != int(transition['resolved_false_alarms'])):
                    raise TableError(f'{key}: transition CSV does not match raw paired forecasts')
                csi_old = old_hit / (old_hit + old_miss + old_false) if old_hit + old_miss + old_false else 0.0
                csi_fix = target['hit'] / (target['hit'] + target['miss'] + target['false_alarm']) if target['hit'] + target['miss'] + target['false_alarm'] else 0.0
                output[key] = {'lead_hour': int(score['lead_hour']), 'old': old, 'fix': target,
                               'old_csi': csi_old, 'fix_csi': csi_fix, 'delta_csi': csi_fix - csi_old}
    return output, array_hashes


def render_markdown(rows: dict) -> str:
    lines = [
        '# 전 영역 강수 범주 점수: OLD/FIX 전체 시간·임계값', '',
        '두 초기장 비교에서 OLD와 FIX 각각의 H/M/F/CSI를 모두 표시합니다. 각 표는 하나의 임계값이며, 행은 개별 예측시간입니다. 시간이나 임계값 평균은 계산하지 않았습니다.', '',
        '- 매 예측시간의 전체 격자: `n=3,688`.',
        '- H: hit, M: miss, F: false alarm; CSI = `H/(H+M+F)`.',
        '- ΔCSI = FIX CSI − OLD CSI.',
        '- 규준실험 초기장: `ORIGINAL` → `FIXED_ORIGINAL_100`.',
        '- 현재 B1 초기장: `X = ORIGINAL_B1_100` (B1_OLD_KDM6) → `A = IMPROVED_BG_FIXED` (현재 B1/FIX).',
        '- OLD H/M/F는 고정 transition 표로 역산하고, 모든 OLD/FIX contingency counts 및 transition counts를 receipt-pinned full-grid arrays로 독립 재계산해 대조했습니다.',
    ]
    for comparison, spec in COMPARISONS.items():
        lines += ['', f"## {spec['initialization']}: {spec['old_label']} → {spec['fix_label']}", '']
        for threshold in THRESHOLDS:
            lines += [f'### 임계값 {float(threshold):g} mm', '',
                      '| 유효시각 UTC | Lead | OLD H | OLD M | OLD F | OLD CSI | FIX H | FIX M | FIX F | FIX CSI | ΔCSI |',
                      '|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
            for hour in HOURS:
                row = rows[(str(hour), comparison, threshold)]
                old, fix = row['old'], row['fix']
                lines.append(f"| {hour:02d}:00 | +{row['lead_hour']} h | {old['hit']} | {old['miss']} | {old['false_alarm']} | {row['old_csi']:.6f} | {fix['hit']} | {fix['miss']} | {fix['false_alarm']} | {row['fix_csi']:.6f} | {row['delta_csi']:+.6f} |")
            lines.append('')
    return '\n'.join(lines).rstrip() + '\n'


def generate() -> dict:
    receipt, scores, transitions, source_hashes = load_frozen_inputs()
    rows, array_hashes = prepare_rows(receipt, scores, transitions)
    markdown = render_markdown(rows)
    receipt_output = {
        'schema': 'cp02_protected_process_full_scores_v2',
        'status': 'PASS_INDEPENDENT_OLD_FIX_RECOUNT',
        'generator_sha256': sha256(Path(__file__)),
        'cohort_receipt_sha256': source_hashes['receipt.json'],
        'csv_sources': source_hashes,
        'raw_array_sources': array_hashes,
        'scope': {
            'comparisons': list(COMPARISONS), 'hours_utc': list(HOURS),
            'thresholds_mm': [float(value) for value in THRESHOLDS], 'rows': len(rows),
            'n_grid_points_each_row': 3688,
            'metrics': ['H', 'M', 'F', 'CSI', 'delta_CSI_FIX_minus_OLD'],
            'aggregation': 'none',
        },
        'validation': {
            'fix_scores_match_raw_arrays': True,
            'old_scores_reconstructed_from_transitions_and_match_raw_arrays': True,
            'transition_counts_match_raw_paired_arrays': True,
            'all_contingency_counts_sum_to_3688': True,
            'rows_independently_verified': len(rows),
        },
        'outputs': {'FULL_SCORES.md': hashlib.sha256(markdown.encode('utf-8')).hexdigest()},
    }
    if OUTPUT.exists() and not OUTPUT.is_dir():
        raise TableError('table output path is not a directory')
    OUTPUT.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.full-scores-stage-', dir=OUTPUT))
    try:
        (stage / 'FULL_SCORES.md').write_text(markdown, encoding='utf-8')
        (stage / 'receipt.json').write_text(json.dumps(receipt_output, indent=2, ensure_ascii=False,
                                                        sort_keys=True) + '\n', encoding='utf-8')
        os.replace(stage / 'FULL_SCORES.md', OUTPUT / 'FULL_SCORES.md')
        os.replace(stage / 'receipt.json', OUTPUT / 'receipt.json')
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return receipt_output


if __name__ == '__main__':
    print(json.dumps(generate(), sort_keys=True))
