#!/usr/bin/env python3
"""Render the frozen one-case DM065 comparison without pooling leads or thresholds."""
from __future__ import annotations

import argparse
import csv
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import PowerNorm, SymLogNorm
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FOLLOWUP = ROOT / 'docs/evidence/cp02_rain_number_process_20261104/followup'
PLAN_SHA = 'bf57b08377138a7e0e3554a6f314e8f8a58bb4dcf722fc30c9c1a046d76e31fe'
POLICY_SHA = 'c9afca77f42c0e3bba6d7f421f1e612a82ddd8912a722414d892918d4773ad7a'
FONT = Path('/usr/share/fonts/truetype/nanum/NanumGothic.ttf')
FONT_SHA = '48a28e97b34fc8e5b157657633670cd1b7de126cfc414da65ce9c3d5bc8be733'
HOURS = tuple(range(13, 19))
THRESHOLDS = (.1, .5, 1., 2.5, 5., 10.)
CASES = ('ORIGINAL', 'IMPROVED_BG_FIXED', 'B1_RAIN_NUMBER_PRIOR', 'B1_RAIN_NUMBER_DM065')
BASE = CASES[1]
CANDIDATE = CASES[3]
LABELS = {CASES[0]: '규준실험', BASE: '현재 B1', CASES[2]: '기존 입자수 후보 (Dm 0.862 mm)', CANDIDATE: '조정 입자수 후보 (Dm 0.65 mm)', 'reference': 'RN1 기준자료'}
COLORS = {CASES[0]: '#68757c', BASE: '#1769a3', CASES[2]: '#a85720', CANDIDATE: '#a22972'}


def sha(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def configure_font():
    if not FONT.is_file() or sha(FONT) != FONT_SHA:
        raise ValueError('pinned Korean font is missing or changed')
    font_manager.fontManager.addfont(str(FONT))
    plt.rcParams.update({'font.family': font_manager.FontProperties(fname=str(FONT)).get_name(), 'axes.unicode_minus': False, 'savefig.dpi': 130})


def csv_rows(path):
    with path.open(newline='', encoding='utf-8') as stream:
        return list(csv.DictReader(stream))


def load_verified(analysis: Path, plan_path: Path, expected_plan_sha: str):
    if sha(plan_path) != expected_plan_sha:
        raise ValueError('frozen evaluation plan identity differs')
    plan = json.loads(plan_path.read_text(encoding='utf-8'))
    if (plan.get('schema') != 'b1_rain_dm065_evaluation_v1' or plan.get('candidate') != CANDIDATE
        or plan.get('leads_hours') != list(range(1, 7)) or plan.get('thresholds_mm') != list(THRESHOLDS)
        or plan.get('constraint_count') != 26 or plan.get('policy_sha256') != POLICY_SHA):
        raise ValueError('frozen plan scope differs')
    receipt = json.loads((analysis / 'receipt.json').read_text(encoding='utf-8'))
    if receipt.get('status') != 'COMPLETE' or receipt.get('rows') != {'categorical': 144, 'continuous': 24, 'constraints': 26}:
        raise ValueError('analysis receipt lacks 144/24/26 complete scope')
    if not any(item.get('sha256') == expected_plan_sha for item in receipt.get('inputs', [])):
        raise ValueError('analysis receipt does not bind frozen plan')
    names = [*(f'hour_{hour}_arrays.npz' for hour in HOURS), 'categorical_scores.csv', 'continuous_scores.csv', 'admission_constraints.csv', 'winner.json']
    for name in names:
        path, pin = analysis / name, receipt.get('outputs', {}).get(name, {})
        if path.is_symlink() or not path.is_file() or path.stat().st_size != pin.get('size_bytes') or sha(path) != pin.get('sha256'):
            raise ValueError(f'analysis input differs from receipt: {name}')
    hourly = {}
    for hour in HOURS:
        with np.load(analysis / f'hour_{hour}_arrays.npz', allow_pickle=False) as data:
            required = {*CASES, 'reference', 'latitude', 'longitude', 'flat_index_yx'}
            if set(data.files) != required:
                raise ValueError('hourly array fields differ from declared cohort')
            values = {key: np.asarray(data[key]).copy() for key in required}
        if any(v.shape != (3688,) or not np.isfinite(v).all() for v in values.values()) or len(np.unique(values['flat_index_yx'])) != 3688:
            raise ValueError('hourly cohort is incomplete, nonfinite, or duplicated')
        if any(np.any(values[key] < 0) for key in ('reference', *CASES)):
            raise ValueError('negative hourly precipitation')
        if hourly and any(not np.array_equal(values[key], hourly[13][key]) for key in ('latitude', 'longitude', 'flat_index_yx')):
            raise ValueError('hourly sample locations differ')
        hourly[hour] = values
    scores = validate_tables(hourly, analysis)
    return hourly, scores, receipt


def validate_tables(hourly, analysis):
    rows = csv_rows(analysis / 'categorical_scores.csv')
    by_key = {(r['case'], int(r['lead_hour']), float(r['threshold_mm'])): r for r in rows}
    keys = {(case, lead, t) for case in CASES for lead in range(1, 7) for t in THRESHOLDS}
    if len(rows) != 144 or set(by_key) != keys:
        raise ValueError('categorical score keys differ from 144 declared cells')
    scores, fractions = {}, {}
    for case, lead, threshold in sorted(keys):
        values = hourly[12 + lead]; observed = values['reference'] >= threshold; pred = values[case] >= threshold
        hit = int(np.count_nonzero(observed & pred)); miss = int(np.count_nonzero(observed & ~pred)); false = int(np.count_nonzero(~observed & pred))
        if not hit + miss + false:
            raise ValueError('CSI is undefined')
        row = by_key[case, lead, threshold]
        if (int(row['points']), int(row['hit']), int(row['miss']), int(row['false_alarm'])) != (3688, hit, miss, false):
            raise ValueError('categorical table does not match paired arrays')
        frac = Fraction(hit, hit + miss + false)
        if not np.isclose(float(row['CSI']), float(frac), rtol=1e-13, atol=1e-15):
            raise ValueError('CSI table differs from independent recount')
        scores[case, lead, threshold] = float(frac); fractions[case, lead, threshold] = frac
    continuous = csv_rows(analysis / 'continuous_scores.csv')
    cont = {(r['case'], int(r['lead_hour'])): r for r in continuous}
    if len(continuous) != 24 or set(cont) != {(c, lead) for c in CASES for lead in range(1, 7)}:
        raise ValueError('continuous score keys differ from 24 declared cells')
    for (case, lead), row in cont.items():
        error = hourly[12 + lead][case] - hourly[12 + lead]['reference']
        if not np.isclose(float(row['MAE_mm']), np.abs(error).mean(), rtol=1e-13, atol=1e-15) or not np.isclose(float(row['RMSE_mm']), np.sqrt(np.square(error).mean()), rtol=1e-13, atol=1e-15):
            raise ValueError('continuous score differs from paired arrays')
    constraints = csv_rows(analysis / 'admission_constraints.csv')
    expected = {(lead, t) for lead in range(1, 7) for t in THRESHOLDS if lead == 1 or t == 5 or (lead >= 2 and t in (.1, .5, 1.))}
    keyed = {(int(r['lead_hour']), float(r['threshold_mm'])): r for r in constraints}
    if len(constraints) != 26 or set(keyed) != expected:
        raise ValueError('constraint table differs from 26 frozen cells')
    passed = 0
    for (lead, t), row in keyed.items():
        protect = lead == 1 or t == 5
        baseline = BASE if protect else 'ORIGINAL'
        good = fractions[CANDIDATE, lead, t] >= fractions[baseline, lead, t]
        if row['baseline'] != baseline or row['goal'] != ('preserve_current_B1' if protect else 'recover_low_threshold_vs_ORIGINAL') or row['satisfied'] != str(good) or not np.isclose(float(row['candidate_CSI']), scores[CANDIDATE, lead, t]) or not np.isclose(float(row['baseline_CSI']), scores[baseline, lead, t]):
            raise ValueError('constraint result differs from frozen policy')
        passed += good
    winner = json.loads((analysis / 'winner.json').read_text(encoding='utf-8'))
    if winner.get('candidate') != CANDIDATE or winner.get('required_constraints') != 26 or winner.get('passed_constraints') != passed or winner.get('qualified') != (passed == 26) or winner.get('selection') != (CANDIDATE if passed == 26 else 'NO_QUALIFIED_CANDIDATE'):
        raise ValueError('winner receipt differs from constraint table')
    return scores


def map_scales(hourly):
    max_rain = max(float(np.max(v[key])) for v in hourly.values() for key in ('reference', *CASES))
    delta = max(float(np.max(np.abs(v[a] - v[b]))) for v in hourly.values() for a, b in ((BASE, 'ORIGINAL'), (CASES[2], 'ORIGINAL'), (CANDIDATE, 'ORIGINAL'), (CANDIDATE, BASE)))
    return max(max_rain, 1e-12), max(delta, 1e-12)


def draw_csi(scores, threshold, path):
    fig, axes = plt.subplots(1, 2, figsize=(14, 5), constrained_layout=True)
    for case in CASES:
        vals = np.array([scores[case, lead, threshold] for lead in range(1, 7)])
        baseline = np.array([scores[BASE, lead, threshold] for lead in range(1, 7)])
        for ax, data in zip(axes, (vals, vals - baseline)):
            ax.plot(range(1, 7), data, marker='o', color=COLORS[case], label=LABELS[case])
    axes[0].set(title='절대 CSI', ylabel='CSI', ylim=(0, 1)); axes[1].set(title='현재 B1 대비 CSI 차이', ylabel='CSI 차이')
    axes[1].axhline(0, color='#555555', linewidth=.7)
    for ax in axes:
        ax.set_xlabel('예측시간 (h)'); ax.set_xticks(range(1, 7)); ax.grid(alpha=.25)
    fig.legend(*axes[0].get_legend_handles_labels(), loc='outside lower center', ncols=2, fontsize=9)
    fig.suptitle(f'시간 강수 CSI · 임계값 {threshold:g} mm 이상 · 각 예측시간 개별', fontsize=14)
    fig.savefig(path, metadata={'Software': 'CP02 DM065 renderer'}); plt.close(fig)


def draw_map(values, hour, rain_max, delta_max, path):
    abs_norm = PowerNorm(gamma=.5, vmin=0, vmax=rain_max)
    delta_norm = SymLogNorm(linthresh=min(.1, delta_max / 100), vmin=-delta_max, vmax=delta_max)
    maps = [('RN1 기준자료', values['reference']), *((LABELS[c], values[c]) for c in CASES),
            ('현재 B1 - 규준실험', values[BASE] - values['ORIGINAL']),
            ('기존 후보 - 규준실험', values[CASES[2]] - values['ORIGINAL']),
            ('조정 후보 - 규준실험', values[CANDIDATE] - values['ORIGINAL']),
            ('조정 후보 - 현재 B1', values[CANDIDATE] - values[BASE])]
    fig, axes = plt.subplots(3, 3, figsize=(17, 15))
    fig.subplots_adjust(left=.06, right=.97, bottom=.13, top=.93, wspace=.25, hspace=.33)
    abs_artist = delta_artist = None
    for index, (ax, (title, data)) in enumerate(zip(axes.flat, maps)):
        artist = ax.scatter(values['longitude'], values['latitude'], c=data, s=4, linewidths=0,
                            cmap='viridis' if index < 5 else 'RdBu_r', norm=abs_norm if index < 5 else delta_norm, rasterized=True)
        if index < 5: abs_artist = artist
        else: delta_artist = artist
        ax.set_title(title, fontsize=10); ax.set_xlabel('경도 (°E)'); ax.set_ylabel('위도 (°N)'); ax.set_aspect('equal', adjustable='box')
    fig.colorbar(abs_artist, cax=fig.add_axes([.11, .055, .34, .015]), orientation='horizontal', label='시간 강수량 (mm)')
    fig.colorbar(delta_artist, cax=fig.add_axes([.57, .055, .34, .015]), orientation='horizontal', label='시간 강수량 차이 (mm)',
                 ticks=[-delta_max, -delta_max / 100, 0, delta_max / 100, delta_max], format=lambda x, _: f'{x:.2g}')
    fig.suptitle(f'2026-08-16 {hour:02d} UTC · +{hour - 12} h · 3,688개 실제 대응 지점', fontsize=15)
    fig.savefig(path, metadata={'Software': 'CP02 DM065 renderer'}); plt.close(fig)


def render(analysis: Path, plan: Path, plan_sha: str, output: Path):
    configure_font()
    hourly, scores, receipt = load_verified(analysis, plan, plan_sha)
    rain_max, delta_max = map_scales(hourly)
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.dm065-figures-', dir=output.parent))
    backup = None
    try:
        names = []
        for t in THRESHOLDS:
            name = f'csi_{t:g}mm.png'; draw_csi(scores, t, stage / name); names.append(name)
        for hour in HOURS:
            name = f'hour_{hour}_map.png'; draw_map(hourly[hour], hour, rain_max, delta_max, stage / name); names.append(name)
        score_rows = csv_rows(analysis / 'categorical_scores.csv')
        table = ['# 시간별 임계값별 전체 CSI (144행)', '', '각 행은 3,688개 대응 지점에 대한 별도 점수이며 평균하지 않았습니다.', '', '| 예측시간 (h) | 임계값 (mm) | 실험 | Hit | Miss | False alarm | CSI |', '| ---: | ---: | --- | ---: | ---: | ---: | ---: |']
        table.extend(f"| {r['lead_hour']} | {float(r['threshold_mm']):g} | {LABELS[r['case']]} | {r['hit']} | {r['miss']} | {r['false_alarm']} | {float(r['CSI']):.8f} |" for r in score_rows)
        (stage / 'FULLSCORES.md').write_text('\n'.join(table) + '\n', encoding='utf-8')
        gallery = '# DM 0.65 mm 연구 비교\n\n각 예측시간과 임계값을 개별 표시합니다. 지도는 3,688개 실제 대응 지점만 표시하며 공간을 보간하지 않습니다. 색상 범위는 모든 시간에 동일합니다. [전체 CSI 표 (144행)](FULLSCORES.md).\n\n' + '\n\n'.join(f'![{name}]({name})' for name in names) + '\n'
        (stage / 'gallery.md').write_text(gallery, encoding='utf-8')
        metadata = {'plan_sha256': plan_sha, 'analysis_receipt_sha256': sha(analysis / 'receipt.json'), 'inputs': {n: receipt['outputs'][n]['sha256'] for n in [*(f'hour_{h}_arrays.npz' for h in HOURS), 'categorical_scores.csv', 'continuous_scores.csv', 'admission_constraints.csv', 'winner.json']}, 'font_sha256': sha(FONT), 'renderer_sha256': sha(Path(__file__)), 'matplotlib_version': matplotlib.__version__, 'shared_limits': {'rain_max_mm': rain_max, 'absolute_difference_max_mm': delta_max}, 'outputs': {n: sha(stage / n) for n in (*names, 'gallery.md', 'FULLSCORES.md')}}
        (stage / 'metadata.json').write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        if output.exists():
            backup = Path(tempfile.mkdtemp(prefix='.dm065-backup-', dir=output.parent)); backup.rmdir(); output.rename(backup)
        try:
            stage.rename(output)
        except BaseException:
            if backup is not None: backup.rename(output)
            raise
        if backup is not None: shutil.rmtree(backup)
    finally:
        if stage.exists(): shutil.rmtree(stage)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--analysis', type=Path, default=FOLLOWUP / 'analysis_dm065')
    parser.add_argument('--plan', type=Path, default=FOLLOWUP / 'evaluation_plan.json')
    parser.add_argument('--output', type=Path, default=FOLLOWUP / 'figures')
    args = parser.parse_args()
    render(args.analysis, args.plan, PLAN_SHA, args.output)


if __name__ == '__main__':
    main()
