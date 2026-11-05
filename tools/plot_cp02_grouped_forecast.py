#!/usr/bin/env python3
"""Render receipt-bound CSI curves and paired RN1 precipitation maps."""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
from pathlib import Path
import shutil
import tempfile
import zipfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import BoundaryNorm, SymLogNorm
from matplotlib.ticker import FuncFormatter
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_PLAN = ROOT / 'docs/evidence/cp02_grouped_forecast_20261105/evaluation_plan.json'
PLAN_SHA256 = '583c4eb95a5bf2939bd3a40fa640cc3e6bad615f04bb3f903386840cbb1ccb8c'
SCORER = ROOT / 'tools/cp02_grouped_forecast.py'
BOUNDARY_PATH = ROOT / 'docs/evidence/cp02_grouped_forecast_20261105/figures/data/ne_50m_coastline.geojson'
BOUNDARY_SHA256 = '271f1c4c1908312bac6b29d158ea1356544beafc129f260005300913aa5ea283'
BOUNDARY_COMMIT = 'ca96624a56bd078437bca8184e78163e5039ad19'
BOUNDARY_URL = f'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/{BOUNDARY_COMMIT}/geojson/ne_50m_coastline.geojson'
BOUNDARY_TERMS_URL = 'https://www.naturalearthdata.com/about/terms-of-use/'
LEADS = tuple(range(1, 7))
HOURS = tuple(range(13, 19))
THRESHOLDS = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0)
CASES = ('ORIGINAL', 'A', 'B', 'C', 'D')
PAIRS = (('C', 'A'), ('D', 'B'), ('B', 'A'), ('D', 'A'),
         ('C', 'ORIGINAL'), ('D', 'ORIGINAL'))
POINTS = 3688
SOURCE_VALIDATION = 'sealed_analysis_recount; rawhistorynotreopened'
RAIN_BINS_MM = (0.0, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 20.0, 50.0, 100.0)
ARRAY_KEYS = {'reference', 'latitude', 'longitude', 'flat_index_yx', *CASES}
EXPECTED_OUTPUTS = {
    'categorical_scores.csv', 'continuous_scores.csv', 'contrasts.csv',
    'weak_transition_counts.csv', 'gate_results.csv', 'winner.json',
    *(f'hour_{hour}_arrays.npz' for hour in HOURS),
}
SCHEMATIC_FILENAME = 'grouped_math_met_schematic.png'
LABELS = {
    'ORIGINAL': '규준실험 (ORIGINAL)', 'A': '현재 B1 (A)', 'B': 'DM065 (B)',
    'C': 'B1+합산식 (C)', 'D': 'DM065+합산식 (D)',
}
COLORS = {'ORIGINAL': '#55575b', 'A': '#2166ac', 'B': '#e69f00', 'C': '#009e73', 'D': '#d55e00'}
PAIR_LABELS = {
    ('C', 'A'): 'C-A', ('D', 'B'): 'D-B', ('B', 'A'): 'B-A', ('D', 'A'): 'D-A',
    ('C', 'ORIGINAL'): 'C-ORIGINAL', ('D', 'ORIGINAL'): 'D-ORIGINAL',
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def identity(path: Path) -> dict:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f'input is missing or a symlink: {path}')
    return {'path': str(path), 'sha256': sha256(path), 'size_bytes': path.stat().st_size}


def verify_record(record: dict) -> dict:
    current = identity(Path(record['path']))
    if any(current[key] != record.get(key) for key in ('sha256', 'size_bytes')):
        raise ValueError(f'input hash or size mismatch: {record["path"]}')
    return current


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream))


def verify_analysis(analysis: Path) -> tuple[dict, dict, list[dict[str, str]], list[dict[str, str]]]:
    analysis = Path(analysis)
    receipt_path = analysis / 'receipt.json'
    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    if receipt.get('schema') != 'cp02_grouped_forecast_result_v1' or receipt.get('status') != 'COMPLETE':
        raise ValueError('complete grouped-forecast result receipt is required')
    if (receipt.get('initial_time_utc') != '2026-08-16T12:00:00Z'
            or receipt.get('hours_utc') != list(HOURS) or receipt.get('lead_hours') != list(LEADS)
            or receipt.get('points_per_hour') != POINTS or tuple(receipt.get('thresholds_mm', ())) != THRESHOLDS
            or receipt.get('cases') != ['A', 'B', 'C', 'D', 'ORIGINAL']
            or receipt.get('arms') != ['A', 'B', 'C', 'D'] or receipt.get('benchmark') != 'ORIGINAL'
            or receipt.get('precipitation_window') != 'one-hour increments of RAINC + RAINNC; not cumulative lead totals'):
        raise ValueError('receipt scope differs from the frozen five-case, six-lead design')
    if receipt.get('rows') != {'categorical': 180, 'continuous': 30, 'contrasts': 180,
                               'weak_transitions': 24, 'gates': 52}:
        raise ValueError('receipt row counts differ from the frozen 180/30/180/24/52 contract')
    plan_record = receipt.get('evaluation_plan', {})
    local_plan = identity(ANALYSIS_PLAN)
    if (plan_record.get('sha256') != PLAN_SHA256 or local_plan['sha256'] != PLAN_SHA256
            or plan_record.get('size_bytes') != local_plan['size_bytes']):
        raise ValueError('frozen grouped-forecast evaluation plan hash mismatch')
    source_record = receipt.get('scorer', {})
    local_scorer = identity(SCORER)
    if (Path(source_record.get('path', '')).name != SCORER.name
            or source_record.get('sha256') != local_scorer['sha256']
            or source_record.get('size_bytes') != local_scorer['size_bytes']):
        raise ValueError('analysis scorer source pin differs from the local frozen scorer')
    outputs = receipt.get('outputs', {})
    if set(outputs) != EXPECTED_OUTPUTS:
        raise ValueError('analysis receipt output inventory is incomplete or unexpected')
    for name, record in outputs.items():
        local = analysis / name
        current = identity(local)
        if (current['sha256'] != record.get('sha256') or current['size_bytes'] != record.get('size_bytes')):
            raise ValueError(f'analysis output hash mismatch: {name}')
    inputs = receipt.get('inputs', ())
    if not inputs:
        raise ValueError('analysis receipt has no bound source inputs')
    for record in inputs:
        digest = record.get('sha256')
        size = record.get('size_bytes', record.get('size'))
        if (not isinstance(record.get('path'), str) or not record['path']
                or not isinstance(digest, str) or len(digest) != 64
                or any(character not in '0123456789abcdef' for character in digest)
                or not isinstance(size, int) or size < 0):
            raise ValueError('analysis source identity record is malformed')
    categorical = read_csv(analysis / 'categorical_scores.csv')
    continuous = read_csv(analysis / 'continuous_scores.csv')
    contrasts = read_csv(analysis / 'contrasts.csv')
    transitions = read_csv(analysis / 'weak_transition_counts.csv')
    gates = read_csv(analysis / 'gate_results.csv')
    expected_cat = {(lead, case, threshold) for lead in LEADS for case in CASES for threshold in THRESHOLDS}
    cat_by_key = {(int(row['lead_hour']), row['case'], float(row['threshold_mm'])): row for row in categorical}
    expected_cont = {(lead, case) for lead in LEADS for case in CASES}
    cont_by_key = {(int(row['lead_hour']), row['case']): row for row in continuous}
    if len(categorical) != 180 or len(cat_by_key) != 180 or set(cat_by_key) != expected_cat:
        raise ValueError('categorical score table is not the complete 180-cell grid')
    if len(continuous) != 30 or len(cont_by_key) != 30 or set(cont_by_key) != expected_cont:
        raise ValueError('continuous score table is not the complete 30-cell grid')
    arrays = load_arrays(analysis)
    verify_scores_from_arrays(arrays, cat_by_key, cont_by_key)
    verify_auxiliary_tables(contrasts, transitions, gates, cat_by_key, arrays)
    winner = json.loads((analysis / 'winner.json').read_text(encoding='utf-8'))
    if winner.get('winner') not in ('C', 'D', 'B1_RETAINED'):
        raise ValueError('winner result is outside the frozen candidate/retain-B1 choices')
    return receipt, arrays, categorical, continuous


def load_arrays(analysis: Path) -> dict[int, dict[str, np.ndarray]]:
    hourly = {}
    for hour in HOURS:
        path = analysis / f'hour_{hour}_arrays.npz'
        with np.load(path, allow_pickle=False) as archive:
            if set(archive.files) != ARRAY_KEYS:
                raise ValueError(f'{path.name}: NPZ key set differs from the frozen score schema')
            values = {name: np.array(archive[name], copy=True) for name in archive.files}
        if any(values[name].shape != (POINTS,) for name in ARRAY_KEYS):
            raise ValueError(f'{path.name}: all fields must contain 3688 paired points')
        if not np.issubdtype(values['flat_index_yx'].dtype, np.integer):
            raise ValueError(f'{path.name}: point IDs must be integers')
        if len(np.unique(values['flat_index_yx'])) != POINTS:
            raise ValueError(f'{path.name}: point IDs are duplicated')
        if any(not np.isfinite(values[name]).all() for name in ARRAY_KEYS - {'flat_index_yx'}):
            raise ValueError(f'{path.name}: a plotted field or coordinate is non-finite')
        if any(np.any(values[case] < 0) for case in CASES) or np.any(values['reference'] < 0):
            raise ValueError(f'{path.name}: precipitation values cannot be negative')
        hourly[hour] = values
    first = hourly[13]
    for hour in HOURS[1:]:
        for name in ('latitude', 'longitude', 'flat_index_yx'):
            if not np.array_equal(first[name], hourly[hour][name]):
                raise ValueError(f'lead +{hour - 12}: paired point keys or coordinates changed')
    return hourly


def verify_scores_from_arrays(hourly: dict[int, dict[str, np.ndarray]],
                              categorical: dict[tuple, dict[str, str]],
                              continuous: dict[tuple, dict[str, str]]) -> None:
    for hour in HOURS:
        lead, values = hour - 12, hourly[hour]
        reference = values['reference']
        for case in CASES:
            prediction = values[case]
            error = prediction - reference
            cont = continuous[lead, case]
            calculated = {'points': POINTS, 'mean_forecast_mm': float(prediction.mean()),
                          'mean_reference_mm': float(reference.mean()), 'mean_error_mm': float(error.mean()),
                          'MAE_mm': float(np.abs(error).mean()), 'RMSE_mm': float(np.sqrt(np.square(error).mean()))}
            for name, value in calculated.items():
                if name == 'points':
                    if int(cont[name]) != value:
                        raise ValueError(f'{case}/+{lead}: continuous point count mismatch')
                elif not np.isclose(float(cont[name]), value, rtol=1e-12, atol=1e-12):
                    raise ValueError(f'{case}/+{lead}: {name} does not reconcile to NPZ arrays')
            for threshold in THRESHOLDS:
                pred_event, obs_event = prediction >= threshold, reference >= threshold
                hit = int(np.count_nonzero(pred_event & obs_event))
                miss = int(np.count_nonzero(~pred_event & obs_event))
                false = int(np.count_nonzero(pred_event & ~obs_event))
                dry = POINTS - hit - miss - false
                denominator = hit + miss + false
                if denominator == 0:
                    raise ValueError(f'{case}/+{lead}/≥{threshold:g}: empty CSI threshold')
                row = categorical[lead, case, threshold]
                if row.get('valid_utc') != f'2026-08-16T{hour:02d}:00:00Z':
                    raise ValueError(f'{case}/+{lead}/≥{threshold:g}: valid time differs from one-hour window')
                exact = {'points': POINTS, 'hit': hit, 'miss': miss, 'false_alarm': false,
                         'correct_dry': dry, 'csi_numerator': hit, 'csi_denominator': denominator}
                for name, value in exact.items():
                    if int(row[name]) != value:
                        raise ValueError(f'{case}/+{lead}/≥{threshold:g}: {name} mismatch')
                if not np.isclose(float(row['CSI']), hit / denominator, rtol=0, atol=1e-15):
                    raise ValueError(f'{case}/+{lead}/≥{threshold:g}: CSI differs from exact counts')
                random_hits = (hit + miss) * (hit + false) / POINTS
                ets_denominator = hit + miss + false - random_hits
                expected_ratios = {
                    'POD': hit / (hit + miss) if hit + miss else None,
                    'FAR': false / (hit + false) if hit + false else None,
                    'frequency_bias': (hit + false) / (hit + miss) if hit + miss else None,
                    'ETS': (hit - random_hits) / ets_denominator if ets_denominator else None,
                }
                for name, expected_value in expected_ratios.items():
                    actual = row[name].strip()
                    if expected_value is None:
                        if actual not in ('', 'None'):
                            raise ValueError(f'{case}/+{lead}/≥{threshold:g}: {name} should be undefined')
                    elif not np.isclose(float(actual), expected_value, rtol=1e-12, atol=1e-12):
                        raise ValueError(f'{case}/+{lead}/≥{threshold:g}: {name} differs from exact counts')


def verify_auxiliary_tables(contrasts: list[dict[str, str]], transitions: list[dict[str, str]],
                            gates: list[dict[str, str]], categorical: dict[tuple, dict[str, str]],
                            hourly: dict[int, dict[str, np.ndarray]]) -> None:
    contrast_names = ('C-A', 'D-B', 'B-A', 'D-C', 'DiD')
    contrast_index = {(int(row['lead_hour']), float(row['threshold_mm']), row['contrast']): row
                      for row in contrasts}
    expected_contrasts = {(lead, threshold, contrast) for lead in LEADS for threshold in THRESHOLDS
                          for contrast in contrast_names}
    if len(contrasts) != 180 or len(contrast_index) != 180 or set(contrast_index) != expected_contrasts:
        raise ValueError('contrast table does not cover the complete 180-row five-contrast grid')
    pair_cases = {'C-A': ('C', 'A'), 'D-B': ('D', 'B'), 'B-A': ('B', 'A'), 'D-C': ('D', 'C')}
    for lead, threshold, name in expected_contrasts:
        row = contrast_index[lead, threshold, name]
        if name == 'DiD':
            candidate, baseline = pair_cases['D-B'], pair_cases['C-A']
            fields = ('hit', 'miss', 'false_alarm', 'correct_dry')
            for field in fields:
                expected = ((int(categorical[lead, candidate[0], threshold][field])
                             - int(categorical[lead, candidate[1], threshold][field]))
                            - (int(categorical[lead, baseline[0], threshold][field])
                               - int(categorical[lead, baseline[1], threshold][field])))
                if int(row[f'delta_{field}']) != expected:
                    raise ValueError(f'DiD {field} does not reconcile at +{lead}/≥{threshold:g}')
            expected_csi = ((float(categorical[lead, 'D', threshold]['CSI'])
                             - float(categorical[lead, 'B', threshold]['CSI']))
                            - (float(categorical[lead, 'C', threshold]['CSI'])
                               - float(categorical[lead, 'A', threshold]['CSI'])))
        else:
            candidate, baseline = pair_cases[name]
            for field in ('hit', 'miss', 'false_alarm', 'correct_dry'):
                expected = (int(categorical[lead, candidate, threshold][field])
                            - int(categorical[lead, baseline, threshold][field]))
                if int(row[f'delta_{field}']) != expected:
                    raise ValueError(f'{name} {field} does not reconcile at +{lead}/≥{threshold:g}')
            expected_csi = (float(categorical[lead, candidate, threshold]['CSI'])
                            - float(categorical[lead, baseline, threshold]['CSI']))
        if not np.isclose(float(row['delta_CSI']), expected_csi, rtol=0, atol=1e-15):
            raise ValueError(f'{name} ΔCSI does not reconcile at +{lead}/≥{threshold:g}')
    transition_index = {(int(row['lead_hour']), row['comparison']): row for row in transitions}
    expected_transitions = {(lead, f'{candidate}-{baseline}') for lead in LEADS
                            for candidate, baseline in (('C', 'A'), ('D', 'B'), ('B', 'A'), ('D', 'C'))}
    if len(transitions) != 24 or len(transition_index) != 24 or set(transition_index) != expected_transitions:
        raise ValueError('weak/dry transition table does not cover every lead and comparison')
    for lead, comparison in expected_transitions:
        candidate, baseline = comparison.split('-')
        values, obs = hourly[12 + lead], hourly[12 + lead]['reference']
        weak, dry = (obs >= .1) & (obs < 1.0), obs < .1
        forecast_new, forecast_old = values[candidate] >= .1, values[baseline] >= .1
        expected = {'weak_observed_points': int(weak.sum()),
                    'weak_detection_gains': int(np.count_nonzero(weak & ~forecast_old & forecast_new)),
                    'weak_detection_losses': int(np.count_nonzero(weak & forecast_old & ~forecast_new)),
                    'dry_observed_points': int(dry.sum()),
                    'dry_new_false_alarms': int(np.count_nonzero(dry & ~forecast_old & forecast_new)),
                    'dry_resolved_false_alarms': int(np.count_nonzero(dry & forecast_old & ~forecast_new))}
        if any(int(transition_index[lead, comparison][key]) != val for key, val in expected.items()):
            raise ValueError(f'{comparison}: weak/dry transitions do not reconcile at +{lead} h')
    gate_index = {(row['gate'], int(row['lead_hour']), float(row['threshold_mm']), row['candidate']): row
                  for row in gates}
    expected_gates = set()
    for candidate in ('C', 'D'):
        expected_gates.update(('preserve_current_B1', lead, threshold, candidate)
                              for lead in LEADS for threshold in THRESHOLDS if lead == 1 or threshold == 5.0)
        expected_gates.update(('recover_vs_ORIGINAL', lead, threshold, candidate)
                              for lead in LEADS for threshold in (0.1, 0.5, 1.0) if lead >= 2)
    if len(gates) != 52 or len(gate_index) != 52 or set(gate_index) != expected_gates:
        raise ValueError('admission gates do not cover the frozen 52-row two-candidate grid')
    for gate, lead, threshold, candidate in expected_gates:
        row = gate_index[gate, lead, threshold, candidate]
        baseline = 'A' if gate == 'preserve_current_B1' else 'ORIGINAL'
        score, reference = categorical[lead, candidate, threshold], categorical[lead, baseline, threshold]
        n, d = int(score['csi_numerator']), int(score['csi_denominator'])
        rn, rd = int(reference['csi_numerator']), int(reference['csi_denominator'])
        expected = n * rd >= rn * d
        if (int(row['candidate_CSI_num']), int(row['candidate_CSI_den']),
                int(row['baseline_CSI_num']), int(row['baseline_CSI_den'])) != (n, d, rn, rd):
            raise ValueError(f'{candidate} gate CSI rational differs at +{lead}/≥{threshold:g}')
        if row['satisfied'].lower() != str(expected).lower():
            raise ValueError(f'{candidate} gate pass flag differs at +{lead}/≥{threshold:g}')


def korean_font() -> tuple[str, Path]:
    preferred = ('NanumGothic', 'NanumBarunGothic', 'Noto Sans CJK KR')
    for family in preferred:
        for entry in font_manager.fontManager.ttflist:
            if entry.name == family:
                path = Path(entry.fname)
                font_manager.fontManager.addfont(path)
                return family, path
    raise RuntimeError('A pinned Korean font (NanumGothic, NanumBarunGothic, or Noto Sans CJK KR) is required')


def csi_index(categorical: list[dict[str, str]]) -> dict[tuple[str, int, float], float]:
    return {(row['case'], int(row['lead_hour']), float(row['threshold_mm'])): float(row['CSI'])
            for row in categorical}


def draw_csi_panels(scores: dict[tuple[str, int, float], float], output: Path) -> list[str]:
    names = []
    for threshold in THRESHOLDS:
        fig, axes = plt.subplots(1, 2, figsize=(12.6, 4.8), constrained_layout=True)
        for case in CASES:
            axes[0].plot(LEADS, [scores[case, lead, threshold] for lead in LEADS],
                         marker='o', linewidth=2, markersize=4, color=COLORS[case], label=LABELS[case])
        delta_series = (
            ('C', 'A', '-', 'C-A (현재 B1의 합산식 효과)'),
            ('D', 'B', '-', 'D-B (DM065의 합산식 효과)'),
            ('D', 'A', '--', 'D-A (결합후보-현재 B1)'),
        )
        for candidate, baseline, linestyle, label in delta_series:
            axes[1].plot(LEADS, [scores[candidate, lead, threshold] - scores[baseline, lead, threshold]
                                 for lead in LEADS], marker='o', linewidth=2, markersize=4,
                         linestyle=linestyle, color=COLORS[candidate], label=label)
        axes[0].set(title='CSI by forecast lead', ylabel='CSI')
        axes[1].set(title='ΔCSI by forecast lead', ylabel='ΔCSI')
        for ax in axes:
            ax.set_xlabel('예보 선행시간 (h)')
            ax.set_xticks(LEADS, [f'+{lead}' for lead in LEADS])
            ax.grid(alpha=.25)
            ax.legend(frameon=False, fontsize=8)
        fig.suptitle(f'한 시간 강수 CSI · 임계값 ≥ {threshold:g} mm · lead별 개별 점수')
        name = f'csi_threshold_{str(threshold).replace(".", "p")}mm.png'
        fig.savefig(output / name, dpi=190, metadata={'Software': 'plot_cp02_grouped_forecast'})
        plt.close(fig)
        names.append(name)
    return names


def draw_process_schematic(output: Path) -> str:
    """Show computational and evaluation links without claiming rain causation."""
    fig, ax = plt.subplots(figsize=(16, 7.4), constrained_layout=True)
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 8)
    ax.axis('off')
    ax.text(8, 7.55, 'Grouped arithmetic → model state → forecast evaluation',
            ha='center', va='center', fontsize=19, weight='bold')
    ax.text(8, 7.05, '계산 연결을 요약한 개념도 · 특정 강수 원인을 입증하지 않음',
            ha='center', va='center', fontsize=11, color='#444444')
    boxes = [
        (0.35, 2.05, 3.3, 4.35, '1  Vertical geopotential increment',
         'OLD left-associated order\n((PHₖ₊₁ - PHₖ) + PHBₖ₊₁)\n - PHBₖ\n\nGROUPED source order\n(PHₖ₊₁ - PHₖ) +\n(PHBₖ₊₁ - PHBₖ)\n\nSame real-arithmetic terms;\nfloating-point grouping differs.'),
        (4.35, 2.05, 3.3, 4.35, '2  AL / pressure coupling',
         'AL = ΔΦ /\n(PHM · ln(PFD/PFU)) - ALB\n\nΔΦ combines PH and PHB\nlayer differences.\n\nThe grouped expression\nchanges this sum order.'),
        (8.35, 2.05, 3.3, 4.35, '3  Thermodynamic state',
         'Pressure state P\n        ↓\nExner factor Π\n        ↓\nTemperature TK = θ · Π\n\nComputational state linkage\nthrough the model equations.'),
        (12.35, 2.05, 3.3, 4.35, '4  Actual forecast scoring',
         'C: current B1 + grouped\nD: DM065 + grouped\n        ↓\nHourly RN1 paired values\n        ↓\nH / M / F → exact CSI\n\n26 frozen gates per candidate:\n11 vs A + 15 vs ORIGINAL'),
    ]
    for x, y, width, height, title, body in boxes:
        ax.add_patch(FancyBboxPatch((x, y), width, height, boxstyle='round,pad=0.12',
                                    facecolor='#f7f9fb', edgecolor='#4a6478', linewidth=1.4))
        ax.text(x + .18, y + height - .32, title, ha='left', va='top', fontsize=10.2, weight='bold')
        ax.text(x + .18, y + height - .88, body, ha='left', va='top', fontsize=9.2,
                family='monospace' if x < 4 else None, linespacing=1.3)
    for left, right in ((3.67, 4.32), (7.67, 8.32), (11.67, 12.32)):
        ax.add_patch(FancyArrowPatch((left, 4.18), (right, 4.18), arrowstyle='-|>',
                                    mutation_scale=15, color='#4a6478', linewidth=1.6))
        ax.text((left + right) / 2, 4.65, 'computational\nlinkage', ha='center', va='bottom',
                fontsize=7, color='#4a6478')
    ax.text(8, 1.35,
            'Forecast scores test the end-to-end C/D outcomes against fixed references; '
            'they do not isolate this arithmetic as the cause of a rainfall difference.',
            ha='center', va='center', fontsize=10, color='#7a2e2e', wrap=True)
    ax.text(8, .65, 'One event · +1 to +6 h hourly increments · no lead/threshold CSI averages',
            ha='center', va='center', fontsize=9, color='#444444')
    fig.savefig(Path(output) / SCHEMATIC_FILENAME, dpi=190,
                metadata={'Software': 'plot_cp02_grouped_forecast'})
    plt.close(fig)
    return SCHEMATIC_FILENAME


def map_scales(hourly: dict[int, dict[str, np.ndarray]]) -> tuple[tuple[float, float], float]:
    if tuple(sorted(hourly)) != HOURS:
        raise ValueError('shared map scales require all six lead hours')
    all_rain = np.concatenate([hourly[hour][case] for hour in HOURS for case in ('reference', *CASES)])
    if not np.isfinite(all_rain).all() or np.any(all_rain < 0):
        raise ValueError('map scale input has invalid hourly precipitation')
    absolute = (0.0, max(float(all_rain.max()), 0.01))
    delta_limit = max((float(np.max(np.abs(hourly[hour][left] - hourly[hour][right])))
                       for hour in HOURS for left, right in PAIRS), default=0.0)
    return absolute, max(delta_limit, 0.01)


def rain_boundaries(maximum_mm: float) -> tuple[float, ...]:
    if not np.isfinite(maximum_mm) or maximum_mm < 0:
        raise ValueError('rainfall maximum must be finite and nonnegative')
    return (*RAIN_BINS_MM, max(100.0, float(maximum_mm)) + 1.0)


def delta_colorbar_ticks(limit_mm: float) -> tuple[float, ...]:
    if not np.isfinite(limit_mm) or limit_mm <= 0:
        raise ValueError('symmetric delta limit must be finite and positive')
    magnitudes = {float(limit_mm)}
    magnitudes.update(value for value in (0.1, 0.5, 1.0, 5.0, 10.0) if value < limit_mm)
    return tuple(sorted({-value for value in magnitudes} | {0.0} | magnitudes))


def format_delta_tick(value: float, _position: int | None = None) -> str:
    return '0' if value == 0 else f'{value:g}'


def draw_hourly_maps(hourly: dict[int, dict[str, np.ndarray]], output: Path,
                     absolute_limits: tuple[float, float], delta_limit: float,
                     boundary: Path | None = None) -> list[str]:
    names = []
    lon, lat = hourly[13]['longitude'], hourly[13]['latitude']
    boundary_lines = read_boundary(boundary) if boundary else []
    rain_levels = rain_boundaries(absolute_limits[1])
    rain_cmap = plt.get_cmap('viridis')
    rain_norm = BoundaryNorm(rain_levels, rain_cmap.N, clip=True)
    delta_norm = SymLogNorm(linthresh=0.1, linscale=1.0,
                            vmin=-delta_limit, vmax=delta_limit, clip=True)
    delta_ticks = delta_colorbar_ticks(delta_limit)
    for hour in HOURS:
        data = hourly[hour]
        fig, axes = plt.subplots(3, 4, figsize=(18, 11), constrained_layout=True, sharex=True, sharey=True)
        abs_artist = delta_artist = None
        panels = [('reference', 'RN1 분석', False), ('ORIGINAL', LABELS['ORIGINAL'], False),
                  ('A', LABELS['A'], False), ('B', LABELS['B'], False), ('C', LABELS['C'], False),
                  ('D', LABELS['D'], False), ('C-A', 'C-A', True), ('D-B', 'D-B', True),
                  ('B-A', 'B-A', True), ('D-A', 'D-A', True),
                  ('C-ORIGINAL', 'C-ORIGINAL', True), ('D-ORIGINAL', 'D-ORIGINAL', True)]
        for ax, (field, title, is_delta) in zip(axes.flat, panels):
            if is_delta:
                left, right = {'C-A': ('C', 'A'), 'D-B': ('D', 'B'), 'B-A': ('B', 'A'),
                               'D-A': ('D', 'A'),
                               'C-ORIGINAL': ('C', 'ORIGINAL'), 'D-ORIGINAL': ('D', 'ORIGINAL')}[field]
                artist = ax.scatter(lon, lat, c=data[left] - data[right], s=7, cmap='RdBu_r',
                                    norm=delta_norm,
                                    linewidths=0, rasterized=True, zorder=3)
                delta_artist = artist
            else:
                key = 'reference' if field == 'reference' else field
                artist = ax.scatter(lon, lat, c=data[key], s=7, cmap=rain_cmap, norm=rain_norm,
                                    linewidths=0, rasterized=True, zorder=3)
                abs_artist = artist
            for line in boundary_lines:
                ax.plot(line[:, 0], line[:, 1], color='#333333', linewidth=.65, zorder=4)
            ax.set_title(title, fontsize=9)
            ax.set_xlim(float(lon.min()), float(lon.max()))
            ax.set_ylim(float(lat.min()), float(lat.max()))
            ax.set_aspect(1.0 / np.cos(np.deg2rad(float(lat.mean()))), adjustable='box')
            ax.grid(alpha=.18, linewidth=.4)
            ax.tick_params(labelsize=7)
        fig.colorbar(abs_artist, ax=axes[:, :3], label='한 시간 강수량 (mm)', orientation='horizontal',
                     ticks=rain_levels, spacing='uniform', pad=.05, fraction=.035)
        fig.colorbar(delta_artist, ax=axes[:, 3:], label='같은 RN1 지점 강수량 차이 (mm)', orientation='horizontal',
                     ticks=delta_ticks, format=FuncFormatter(format_delta_tick), pad=.05, fraction=.035)
        for colorbar in fig.axes[-2:]:
            colorbar.tick_params(labelsize=7)
        fig.suptitle(f'2026-08-16 {hour:02d}:00 UTC · +{hour - 12} h · RN1 paired points (n={POINTS})\n'
                     'paired point만 표시 · 공간보간 없음 · 비선형색눈금')
        name = f'rn1_hour_{hour}_maps.png'
        fig.savefig(output / name, dpi=190, metadata={'Software': 'plot_cp02_grouped_forecast'})
        plt.close(fig)
        names.append(name)
    return names


def read_boundary(path: Path) -> list[np.ndarray]:
    """Read an explicitly supplied offline GeoJSON LineString/MultiLineString boundary."""
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('Korea boundary input is missing or a symlink')
    payload = json.loads(path.read_text(encoding='utf-8'))
    lines = []
    features = payload.get('features', []) if payload.get('type') == 'FeatureCollection' else [payload]
    for feature in features:
        geometry = feature.get('geometry', feature)
        kind, coordinates = geometry.get('type'), geometry.get('coordinates')
        if kind == 'LineString':
            segments = [coordinates]
        elif kind == 'MultiLineString':
            segments = coordinates
        else:
            continue
        for segment in segments:
            line = np.asarray(segment, dtype=float)
            if line.ndim != 2 or line.shape[1] < 2 or not np.isfinite(line[:, :2]).all():
                raise ValueError('boundary coordinates must be finite longitude/latitude pairs')
            lines.append(line[:, :2])
    if not lines:
        raise ValueError('boundary file has no valid LineString or MultiLineString geometry')
    return lines


def build_score_markdown(categorical: list[dict[str, str]], continuous: list[dict[str, str]]) -> str:
    rows = sorted(categorical, key=lambda r: (int(r['lead_hour']), float(r['threshold_mm']), CASES.index(r['case'])))
    text = ['# Grouped forecast: all lead × threshold scores', '',
            'Each row is a separate one-hour precipitation increment on the frozen paired RN1 cohort. '
            'CSI is shown with exact H/(H+M+F) counts. No lead or threshold averages are used.', '',
            '## Categorical scores', '',
            '| Lead | Threshold (mm) | Case | H | M | F | D | N | CSI exact | CSI | POD | FAR | Bias | ETS |',
            '|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for row in rows:
        text.append(f"| +{row['lead_hour']} h | {float(row['threshold_mm']):g} | {LABELS[row['case']]} "
                    f"| {row['hit']} | {row['miss']} | {row['false_alarm']} | {row['correct_dry']} | {row['points']} | "
                    f"{row['csi_numerator']}/{row['csi_denominator']} | {float(row['CSI']):.6f} | "
                    f"{row['POD']} | {row['FAR']} | {row['frequency_bias']} | {row['ETS']} |")
    text.extend(['', '## Continuous scores', '',
                 '| Lead | Case | Mean forecast (mm) | Mean RN1 (mm) | Mean error (mm) | MAE (mm) | RMSE (mm) |',
                 '|---:|---|---:|---:|---:|---:|---:|'])
    for row in sorted(continuous, key=lambda r: (int(r['lead_hour']), CASES.index(r['case']))):
        text.append(f"| +{row['lead_hour']} h | {LABELS[row['case']]} | {float(row['mean_forecast_mm']):.4f} | "
                    f"{float(row['mean_reference_mm']):.4f} | {float(row['mean_error_mm']):+.4f} | "
                    f"{float(row['MAE_mm']):.4f} | {float(row['RMSE_mm']):.4f} |")
    return '\n'.join(text) + '\n'


def write_gallery(directory: Path, names: list[str], metadata: dict) -> None:
    cards = '\n'.join(f'<figure><a href="{html.escape(name)}"><img loading="lazy" src="{html.escape(name)}" alt="{html.escape(name)}"></a><figcaption>{html.escape(name)}</figcaption></figure>' for name in names)
    body = ('<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Grouped forecast figures</title><style>body{font-family:sans-serif;margin:2rem;color:#202124}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:1rem}figure{margin:0;border:1px solid #ddd;padding:.5rem}img{width:100%;height:auto}figcaption{font-size:.9rem;overflow-wrap:anywhere}</style>'
            f'<h1>Grouped forecast · receipt-bound figures</h1><p>Six separate CSI thresholds and six hourly RN1 maps. All map panels use paired sample points without spatial interpolation. Analysis receipt SHA-256: {metadata["analysis_receipt_sha256"]}</p><p><a href="full_score_tables.md">Full lead × threshold score tables</a></p><main>{cards}</main></html>')
    (directory / 'index.html').write_text(body + '\n', encoding='utf-8')


def package_zip(directory: Path, zip_path: Path, members: list[Path]) -> dict:
    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(members, key=lambda item: item.relative_to(directory).as_posix()):
            rel = path.relative_to(directory).as_posix()
            info = zipfile.ZipInfo(rel, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    with zipfile.ZipFile(zip_path) as archive:
        bad = archive.testzip()
        if bad:
            raise ValueError(f'ZIP CRC check failed: {bad}')
    return identity(zip_path)


def render(analysis: Path, output: Path, boundary: Path | None = None) -> dict:
    output = Path(output)
    if os.path.lexists(output):
        raise FileExistsError(output)
    family, font_path = korean_font()
    font_manager.fontManager.addfont(font_path)
    plt.rcParams['font.family'] = font_manager.FontProperties(fname=font_path).get_name()
    plt.rcParams['axes.unicode_minus'] = False
    receipt, hourly, categorical, continuous = verify_analysis(analysis)
    boundary = Path(boundary or BOUNDARY_PATH)
    boundary_record = identity(boundary)
    if boundary_record['sha256'] != BOUNDARY_SHA256:
        raise ValueError('pinned Natural Earth coastline hash differs')
    source_pins = {'renderer': identity(Path(__file__)), 'scorer': identity(SCORER),
                   'evaluation_plan': identity(ANALYSIS_PLAN), 'font': identity(font_path)}
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.cp02-grouped-figures-', dir=output.parent))
    try:
        names = [draw_process_schematic(stage)]
        names += draw_csi_panels(csi_index(categorical), stage)
        absolute, delta_limit = map_scales(hourly)
        names += draw_hourly_maps(hourly, stage, absolute, delta_limit, boundary)
        (stage / 'data').mkdir()
        shutil.copyfile(boundary, stage / 'data/ne_50m_coastline.geojson')
        (stage / 'fonts').mkdir()
        shutil.copyfile(font_path, stage / f'fonts/{font_path.name}')
        full_table = stage / 'full_score_tables.md'
        full_table.write_text(build_score_markdown(categorical, continuous), encoding='utf-8')
        gallery_metadata = {'analysis_receipt_sha256': sha256(Path(analysis) / 'receipt.json')}
        write_gallery(stage, names, gallery_metadata)
        (stage / 'README.md').write_text(
            '# Grouped forecast figures\n\n'
            'This offline bundle contains one computational/meteo schematic, six threshold-specific CSI panels, and six hourly RN1 maps. '
            'Each map plots only the 3,688 paired RN1 coordinates; no spatial interpolation is applied. '
            'The left panel of each CSI figure shows the five case scores; the right panel shows C-A, D-B and joint contrast D-A. '
            'Maps use shared boundary bins for rainfall and a symmetric logarithmic color scale for differences. '
            f'Source validation: `{SOURCE_VALIDATION}`; raw histories are not reopened during plotting.\n\n'
            'Coastline overlay: [Natural Earth 1:50m coastline](https://github.com/nvkelso/natural-earth-vector), '
            f'commit `{BOUNDARY_COMMIT}`; public-domain terms at [Natural Earth terms]({BOUNDARY_TERMS_URL}).\n\n'
            '- [Full lead × threshold score tables](full_score_tables.md)\n'
            '- [Offline figure gallery](index.html)\n'
            '- `figures.zip` contains this README, score tables, gallery, manifest, source coastline, font, and all PNGs.\n'
            '- `render_receipt.json` is beside the ZIP and pins its hash.\n',
            encoding='utf-8')
        inventory = sorted(p for p in stage.rglob('*') if p.is_file())
        artifact_manifest = {'schema': 'cp02_grouped_forecast_figures_v1', 'status': 'COMPLETE',
                             'analysis_receipt_sha256': sha256(Path(analysis) / 'receipt.json'),
                             'source_validation': SOURCE_VALIDATION,
                             'source_pins': source_pins,
                             'boundary': {**boundary_record, 'source_url': BOUNDARY_URL,
                                          'repository_commit': BOUNDARY_COMMIT,
                                          'license': 'Public domain', 'terms_url': BOUNDARY_TERMS_URL},
                             'cases': list(CASES), 'case_labels': LABELS,
                             'lead_hours': list(LEADS), 'thresholds_mm': list(THRESHOLDS),
                             'paired_points': POINTS,
                             'map_scales': {'absolute_rain_mm': list(absolute),
                                            'absolute_rain_norm': 'BoundaryNorm; uniform intervals',
                                            'absolute_rain_boundaries_mm': list(rain_boundaries(absolute[1])),
                                            'symmetric_delta_mm': [-delta_limit, delta_limit],
                                            'delta_norm': {'name': 'SymLogNorm', 'linthresh_mm': 0.1,
                                                           'linscale': 1.0},
                                            'delta_ticks_mm': list(delta_colorbar_ticks(delta_limit)),
                                            'delta_definitions': [PAIR_LABELS[pair] for pair in PAIRS],
                                            'boundary_overlay': bool(boundary_record),
                                            'spatial_interpolation': False},
                             'figure_inventory': names,
                             'bundle_files': {p.relative_to(stage).as_posix():
                                              {'sha256': sha256(p), 'size_bytes': p.stat().st_size}
                                              for p in inventory},
                             'font': {'family': family, 'path': str(font_path), 'sha256': sha256(font_path)},
                             'analysis_inputs': receipt.get('inputs', []),
                             'analysis_outputs': receipt.get('outputs', {}),
                             'software': {'matplotlib': matplotlib.__version__, 'numpy': np.__version__}}
        (stage / 'figure_manifest.json').write_text(json.dumps(artifact_manifest, indent=2, sort_keys=True, ensure_ascii=False) + '\n', encoding='utf-8')
        inventory = sorted(p for p in stage.rglob('*') if p.is_file())
        zip_path = stage / 'figures.zip'
        zip_identity = package_zip(stage, zip_path, inventory)
        zip_record = {key: zip_identity[key] for key in ('sha256', 'size_bytes')}
        render_receipt = {'schema': 'cp02_grouped_forecast_render_receipt_v1',
                          'status': 'COMPLETE', 'analysis_receipt_sha256': artifact_manifest['analysis_receipt_sha256'],
                          'source_validation': SOURCE_VALIDATION,
                          'renderer_sha256': source_pins['renderer']['sha256'],
                          'font': artifact_manifest['font'], 'figure_manifest_sha256': sha256(stage / 'figure_manifest.json'),
                          'figures_zip': zip_record,
                          'outputs': {p.relative_to(stage).as_posix():
                                      {key: identity(p)[key] for key in ('sha256', 'size_bytes')}
                                      for p in sorted(stage.rglob('*')) if p.is_file()}}
        (stage / 'render_receipt.json').write_text(json.dumps(render_receipt, indent=2, sort_keys=True, ensure_ascii=False) + '\n', encoding='utf-8')
        # Recheck all source and analysis pins after rendering before atomic publish.
        verify_analysis(analysis)
        for record in source_pins.values():
            verify_record(record)
        verify_record(boundary_record)
        stage.rename(output)
        return render_receipt
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--analysis', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--korea-boundary', type=Path, help='optional existing offline GeoJSON line boundary')
    args = parser.parse_args()
    print(json.dumps(render(args.analysis, args.output, args.korea_boundary), sort_keys=True))


if __name__ == '__main__':
    main()
