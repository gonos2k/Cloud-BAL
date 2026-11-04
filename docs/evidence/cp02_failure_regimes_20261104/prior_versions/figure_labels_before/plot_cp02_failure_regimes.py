#!/usr/bin/env python3
"""Plot paired threshold transitions in the preserved six-hour RN1 cohort."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import Normalize
from matplotlib.ticker import FuncFormatter
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / 'docs/evidence/cp02_rain_number_process_20261104/followup/analysis_dm065'
OUTPUT = ROOT / 'docs/evidence/cp02_failure_regimes_20261104/figures'
RECEIPT_SHA = '600d2cd041ea24f538af8ac477322b46393c2ab154ebbf2629c3eda2f15f3812'
STATE_PROTOCOL_SHA = '5f44ad36d60e3443f7da7bbf7253359160114e954d3015ed8cef6ca059237690'
STATE_RECEIPT_SHA = '9e6a4cea51bdd88ae45a6052e6818a07ee5003de7dfc5dc2050c048075277d8c'
FONT = Path('/usr/share/fonts/truetype/nanum/NanumGothic.ttf')
FONT_SHA = '48a28e97b34fc8e5b157657633670cd1b7de126cfc414da65ce9c3d5bc8be733'
THRESHOLDS = (.1, .5, 1., 2.5, 5., 10.)
BASE = 'IMPROVED_BG_FIXED'
COMPARISONS = ('ORIGINAL', 'B1_RAIN_NUMBER_PRIOR', 'B1_RAIN_NUMBER_DM065')
LABELS = {'ORIGINAL': '규준실험', 'B1_RAIN_NUMBER_PRIOR': '기존 입자수 후보 (Dm 0.862 mm)', 'B1_RAIN_NUMBER_DM065': '조정 입자수 후보 (Dm 0.65 mm)'}
COLORS = ('#17804b', '#c34435', '#a553a0', '#3574ae')


def sha(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def configure_font():
    if not FONT.is_file() or sha(FONT) != FONT_SHA:
        raise ValueError('pinned Korean font missing or changed')
    font_manager.fontManager.addfont(str(FONT))
    plt.rcParams.update({'font.family': font_manager.FontProperties(fname=str(FONT)).get_name(), 'axes.unicode_minus': False, 'savefig.dpi': 130})


def read_hourly(folder: Path, expected_receipt_sha: str = RECEIPT_SHA):
    receipt = folder / 'receipt.json'
    if sha(receipt) != expected_receipt_sha:
        raise ValueError('source analysis receipt differs from pinned PR146 identity')
    outputs = json.loads(receipt.read_text(encoding='utf-8'))['outputs']
    hourly = {}
    for hour in range(13, 19):
        name = f'hour_{hour}_arrays.npz'; path = folder / name; pin = outputs[name]
        if path.stat().st_size != pin['size_bytes'] or sha(path) != pin['sha256']:
            raise ValueError(f'source array differs from receipt: {name}')
        with np.load(path, allow_pickle=False) as data:
            required = {BASE, *COMPARISONS, 'reference', 'latitude', 'longitude', 'flat_index_yx'}
            if set(data.files) != required:
                raise ValueError('source arrays have unexpected fields')
            values = {key: data[key].copy() for key in required}
        if any(v.shape != (3688,) or not np.isfinite(v).all() for v in values.values()) or len(np.unique(values['flat_index_yx'])) != 3688:
            raise ValueError('paired samples incomplete or duplicated')
        if hourly and any(not np.array_equal(values[key], hourly[13][key]) for key in ('latitude', 'longitude', 'flat_index_yx')):
            raise ValueError('paired sample coordinates differ across hours')
        hourly[hour] = values
    return hourly, outputs


def count_transitions(reference, baseline, candidate, threshold):
    obs, old, new = reference >= threshold, baseline >= threshold, candidate >= threshold
    h0 = int(np.sum(obs & old)); m0 = int(np.sum(obs & ~old)); f0 = int(np.sum(~obs & old))
    gain = int(np.sum(obs & ~old & new)); loss = int(np.sum(obs & old & ~new))
    new_fa = int(np.sum(~obs & ~old & new)); removed_fa = int(np.sum(~obs & old & ~new))
    h1, m1, f1 = h0 + gain - loss, m0 - gain + loss, f0 + new_fa - removed_fa
    if h0 + m0 + f0 == 0 or h1 + m1 + f1 == 0:
        raise ValueError('CSI undefined')
    return {'baseline_hit': h0, 'baseline_miss': m0, 'baseline_fa': f0, 'gained_hit': gain, 'lost_hit': loss, 'new_fa': new_fa, 'removed_fa': removed_fa, 'comparison_hit': h1, 'comparison_miss': m1, 'comparison_fa': f1, 'baseline_CSI': h0 / (h0 + m0 + f0), 'comparison_CSI': h1 / (h1 + m1 + f1)}


def build_counts(hourly):
    return [{'lead_hour': lead, 'threshold_mm': t, 'comparison': case, **count_transitions(hourly[12 + lead]['reference'], hourly[12 + lead][BASE], hourly[12 + lead][case], t)} for lead in range(1, 7) for t in THRESHOLDS for case in COMPARISONS]


def draw_threshold(rows, threshold, path):
    fig, axes = plt.subplots(2, 2, figsize=(15, 10), constrained_layout=True)
    fields = ('gained_hit', 'lost_hit', 'new_fa', 'removed_fa')
    field_labels = ('새 적중', '잃은 적중', '새 오경보', '사라진 오경보')
    x = np.arange(6)
    for ax, case in zip(axes.flat[:3], COMPARISONS):
        selected = [r for r in rows if r['comparison'] == case and r['threshold_mm'] == threshold]
        for i, (field, label, color) in enumerate(zip(fields, field_labels, COLORS)):
            ax.bar(x + (i - 1.5) * .2, [r[field] for r in selected], width=.2, label=label, color=color)
        ax.set_title(LABELS[case] + ' - 현재 B1'); ax.set_xticks(x, range(1, 7)); ax.set_xlabel('예측시간 (h)'); ax.set_ylabel('대응 지점 수'); ax.grid(axis='y', alpha=.2)
    ax = axes.flat[3]
    for case, color in zip(COMPARISONS, ('#68757c', '#a85720', '#a22972')):
        selected = [r for r in rows if r['comparison'] == case and r['threshold_mm'] == threshold]
        ax.plot(range(1, 7), [r['comparison_CSI'] - r['baseline_CSI'] for r in selected], marker='o', color=color, label=LABELS[case])
    ax.axhline(0, color='#555555', linewidth=.7); ax.set_xticks(range(1, 7)); ax.set_xlabel('예측시간 (h)'); ax.set_ylabel('CSI 차이'); ax.set_title('CSI 차이: 비교 실험 - 현재 B1'); ax.grid(alpha=.2)
    handles, labels = axes.flat[0].get_legend_handles_labels(); handles2, labels2 = ax.get_legend_handles_labels()
    fig.legend(handles + handles2, labels + labels2, loc='outside lower center', ncols=4, fontsize=8)
    fig.suptitle(f'임계값 {threshold:g} mm · 3,688개 지점의 대응 전환과 CSI', fontsize=16)
    fig.savefig(path, metadata={'Software': 'CP02 failure-regime renderer'}); plt.close(fig)


def masks(hourly):
    a = hourly[14]; r, b, c = a['reference'], a[BASE], a['B1_RAIN_NUMBER_DM065']; weak = (r >= .1) & (r < 1); dry = r < .1
    return {'weak_gained': weak & (b < .1) & (c >= .1), 'weak_lost': weak & (b >= .1) & (c < .1), 'dry_new_fa': dry & (b < .1) & (c >= .1), 'dry_removed_fa': dry & (b >= .1) & (c < .1)}


def draw_weak(hourly, path):
    group = masks(hourly); numbers = [int(group[k].sum()) for k in ('weak_gained', 'weak_lost', 'dry_new_fa', 'dry_removed_fa')]
    fig, ax = plt.subplots(figsize=(10, 6), constrained_layout=True)
    bars = ax.bar(range(4), numbers, color=COLORS)
    ax.set_xticks(range(4), ['약한 강수\n새 적중', '약한 강수\n잃은 적중', '0.1 mm 미만\n새 오경보', '0.1 mm 미만\n사라진 오경보'])
    ax.bar_label(bars, padding=4); ax.set_ylim(0, max(numbers) * 1.25 + 1); ax.set_ylabel('대응 지점 수'); ax.grid(axis='y', alpha=.2)
    ax.set_title('+2 h · 0.1 mm 판정 · 조정 입자수 후보 vs 현재 B1\n약한 강수: 0.1 ≤ RN1 < 1 mm', fontsize=14)
    fig.savefig(path, metadata={'Software': 'CP02 failure-regime renderer'}); plt.close(fig)


def focus_masks(hourly):
    def compare(hour):
        d = hourly[hour]; return d['reference'], d[BASE], d['B1_RAIN_NUMBER_DM065']
    r2, b2, c2 = compare(14); r3, b3, c3 = compare(15); r5, b5, c5 = compare(17)
    return [('plus2_weak_lost', 14, '+2 h 약한 강수 적중 상실 · 0.1 mm', (r2 >= .1) & (r2 < 1) & (b2 >= .1) & (c2 < .1)),
            ('plus2_new_fa', 14, '+2 h 새 오경보 · 0.1 mm', (r2 < .1) & (b2 < .1) & (c2 >= .1)),
            ('plus3_weak_lost', 15, '+3 h 약한 강수 적중 상실 · 0.1 mm', (r3 >= .1) & (r3 < 1) & (b3 >= .1) & (c3 < .1)),
            ('plus5_strong_lost', 17, '+5 h 적중 상실 · 5 mm', (r5 >= 5) & (b5 >= 5) & (c5 < 5))]


def draw_focus(values, mask, title, path, state=None, rh_limits=None):
    fig, ax = plt.subplots(figsize=(7, 8), constrained_layout=True)
    lon, lat = values['longitude'], values['latitude']
    if state is None:
        ax.scatter(lon, lat, s=4, color='#d5d9dc', linewidths=0, label='전체 대응 지점')
    else:
        valid = state['layer_0to1km_rh_liquid_valid']; values_rh = state['layer_0to1km_rh_liquid_level_mean']
        ax.scatter(lon[~valid], lat[~valid], s=5, color='#a0a0a0', linewidths=0, label='RH 진단 불가')
        points = ax.scatter(lon[valid], lat[valid], s=5, c=values_rh[valid], cmap='viridis', norm=Normalize(*rh_limits), linewidths=0)
        fig.colorbar(points, ax=ax, label='현재 B1 · 구간 시작 · 0–1 km RH (1)')
    ax.scatter(lon[mask], lat[mask], s=50, facecolors='none', edgecolors='#d22b16', linewidths=1.3, label=f'해당 전환 ({int(mask.sum())}개)')
    ax.set_title(title); ax.set_xlabel('경도 (°E)'); ax.set_ylabel('위도 (°N)'); ax.set_aspect('equal', adjustable='box'); ax.legend(loc='best')
    fig.savefig(path, metadata={'Software': 'CP02 failure-regime renderer'}); plt.close(fig)


def draw_physics_schematic(path):
    fig, ax = plt.subplots(figsize=(15, 8), constrained_layout=True); ax.axis('off')
    fig.suptitle('기준 상태 진단: 각 모형 모서리의 비선형 계산 후 보간', fontsize=18, fontweight='bold')
    ax.text(.5, .88, r'입력: $T_{history}$, $P$, $PB$, $q_v$, $q_r$, $N_r$, 연직 지오포텐셜', ha='center', fontsize=15, transform=ax.transAxes)
    ax.text(.5, .73, r'$p=P+PB,\quad T_{air}=(T_{history}+300)(p/100000)^{287/1004.5}$', ha='center', fontsize=19, transform=ax.transAxes)
    ax.text(.5, .62, '건조 온위 교란 T에서 기온 계산 · THM을 건조 온위로 대체하지 않음', ha='center', fontsize=12, transform=ax.transAxes)
    ax.text(.5, .49, r'$r=T_{tp}/T_{air},\quad e_w=\min[p_{sat}\exp(a\log r+b(1-r)),\ 0.99p]$', ha='center', fontsize=16, transform=ax.transAxes)
    ax.text(.5, .39, r'$q_{sw}=\max[\epsilon e_w/(p-e_w),q_{min}],\quad RH_w=\max(q_v/q_{sw},q_{min})$', ha='center', fontsize=16, transform=ax.transAxes)
    ax.text(.5, .29, r'$a=-(c_{pv}-c_{liq})/R_v,\quad b=a+L_v/(R_vT_{tp})$', ha='center', fontsize=13, transform=ax.transAxes)
    ax.text(.5, .17, '각 모서리에서 계산 → 양의 가중치 모서리가 모두 유효할 때만 결합', ha='center', fontsize=14, transform=ax.transAxes)
    ax.text(.5, .065, '진단은 float64 함수 평가이며 모델 연산과 비트 동일성을 주장하지 않음 · 고도 구간은 질량가중 열적분이 아님', ha='center', fontsize=11, color='#984128', transform=ax.transAxes)
    fig.savefig(path, metadata={'Software': 'CP02 failure-regime renderer'}); plt.close(fig)


def population_groups(hourly):
    groups = []
    for lead in (2, 3):
        d = hourly[12 + lead]; obs = d['reference']; b1 = d[BASE]; dm = d['B1_RAIN_NUMBER_DM065']
        weak = (obs >= .1) & (obs < 1); dry = obs < .1
        groups.append((f'weak_plus{lead}', lead - 1, '약한 강수 적중 유지', weak & (b1 >= .1) & (dm >= .1), '약한 강수 적중 상실', weak & (b1 >= .1) & (dm < .1)))
        groups.append((f'fa_plus{lead}', lead - 1, '새 오경보', dry & (b1 < .1) & (dm >= .1), '사라진 오경보', dry & (b1 >= .1) & (dm < .1)))
    d = hourly[17]; obs, b1, dm = d['reference'], d[BASE], d['B1_RAIN_NUMBER_DM065']; heavy = obs >= 5
    groups.append(('heavy_plus5', 4, '5 mm 적중 유지', heavy & (b1 >= 5) & (dm >= 5), '5 mm 적중 상실', heavy & (b1 >= 5) & (dm < 5)))
    return groups


def read_control_states(folder, hourly):
    receipt_path = folder / 'receipt.json'; receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    protocol = folder.parent / 'protocol.json'
    if sha(receipt_path) != STATE_RECEIPT_SHA or receipt.get('status') != 'PASS' or receipt.get('protocol_sha256') != STATE_PROTOCOL_SHA or sha(protocol) != STATE_PROTOCOL_SHA or receipt.get('points') != 3688 or receipt.get('levels') != 39:
        raise ValueError('control-state receipt/protocol does not match validated scope')
    records = {r['name']: r for r in receipt['records']}
    states = {}
    for time in ('input', 'h01', 'h02', 'h04'):
        name = f'B1_{time}.npz'; path = folder / name; rec = records[name]
        if path.stat().st_size != rec['size_bytes'] or sha(path) != rec['sha256']:
            raise ValueError(f'control-state input hash mismatch: {name}')
        with np.load(path, allow_pickle=False) as a:
            state = {key: a[key].copy() for key in a.files}
        if not np.array_equal(state['flat_index_yx'], hourly[13]['flat_index_yx']) or not np.array_equal(state['model_level_1based'], np.arange(1, 40)):
            raise ValueError('control-state coordinates or model levels differ')
        for key in ('qrain_kgkg', 'qnrain_per_kg', 'qvapor_kgkg', 'temperature_K', 'rh_liquid'):
            if state[key].shape != (3688, 39) or not np.isfinite(state[key]).all():
                raise ValueError(f'invalid control-state field {key}')
        dm_valid = state['dm_valid']; dm = state['dm_mass_weighted_mm']; weights = state['corner_weights']
        expected_dm = np.all(state['corner_dm_valid'] | (weights[:, None, :] == 0), axis=2)
        if dm_valid.shape != (3688, 39) or not np.array_equal(dm_valid, expected_dm) or not np.isfinite(dm[dm_valid]).all() or np.isfinite(dm[~dm_valid]).any():
            raise ValueError('invalid Dm validity contract')
        for layer in ('0to1km', '1to3km'):
            for field in ('rh_liquid', 'temperature_K'):
                prefix = f'layer_{layer}_{field}'
                valid = state[prefix + '_valid']; val = state[prefix + '_level_mean']
                expected = np.all((state[f'layer_{layer}_corner_level_count'] > 0) | (weights == 0), axis=1)
                if valid.shape != (3688,) or not np.array_equal(valid, expected) or not np.isfinite(val[valid]).all() or np.isfinite(val[~valid]).any():
                    raise ValueError(f'invalid layer summary {prefix}')
        states[time] = state
    for time in ('input', 'h01', 'h02'):
        name = f'DM065_{time}.npz'; path = folder / name; rec = records[name]
        if path.stat().st_size != rec['size_bytes'] or sha(path) != rec['sha256']:
            raise ValueError(f'candidate-state input hash mismatch: {name}')
        with np.load(path, allow_pickle=False) as a:
            state = {key: a[key].copy() for key in ('flat_index_yx', 'corner_weights', 'corner_qrain_kgkg', 'corner_qnrain_per_kg', 'qrain_kgkg', 'qnrain_per_kg', 'rh_liquid', 'temperature_K')}
        if not np.array_equal(state['flat_index_yx'], states[time]['flat_index_yx']) or not np.array_equal(state['corner_weights'], states[time]['corner_weights']):
            raise ValueError('candidate native point mapping differs')
        states['DM_' + time] = state
    return states, receipt


def summary(values):
    values = np.asarray(values, dtype=np.float64); values = values[np.isfinite(values)]
    if not values.size:
        return {'n_valid': 0, 'minimum': '', 'q25': '', 'median': '', 'q75': '', 'maximum': ''}
    q25, median, q75 = np.quantile(values, (.25, .5, .75))
    return {'n_valid': int(values.size), 'minimum': float(values.min()), 'q25': float(q25), 'median': float(median), 'q75': float(q75), 'maximum': float(values.max())}


def draw_population_profiles(name, start, descriptions, states, path):
    fields = [('qrain_kgkg', '빗물 혼합비', 'kg/kg'), ('qnrain_per_kg', '비 입자수 혼합비', 'kg⁻¹'), ('qvapor_kgkg', '수증기 혼합비', 'kg/kg'), ('rh_liquid', '물 기준 상대습도', '1'), ('temperature_K', '기온', 'K'), ('dm_mass_weighted_mm', '질량가중 평균 직경', 'mm')]
    fig, axes = plt.subplots(2, 3, figsize=(17, 10), constrained_layout=True); rows = []
    for ax, (field, label, unit) in zip(axes.flat, fields):
        for group_idx, (group_label, mask) in enumerate(descriptions):
            for time, style in (('input', '--'), (f'h{start:02d}', '-')):
                state = states[time]; arr = state[field]; color = ('#1769a3', '#c34435')[group_idx]
                stats = []
                for level in range(39):
                    valid = mask.copy()
                    if field == 'dm_mass_weighted_mm': valid &= state['dm_valid'][:, level]
                    item = summary(arr[valid, level]); stats.append(item)
                    rows.append({'population': name, 'group': group_label, 'group_n': int(mask.sum()), 'time': time, 'field': field, 'level_or_layer': str(level + 1), **item})
                median = np.array([s['median'] if s['n_valid'] else np.nan for s in stats], dtype=float)
                lo = np.array([s['q25'] if s['n_valid'] else np.nan for s in stats], dtype=float); hi = np.array([s['q75'] if s['n_valid'] else np.nan for s in stats], dtype=float)
                ax.plot(median, np.arange(1, 40), color=color, linestyle=style, linewidth=1.5, label=f'{group_label} · {time} (n={int(mask.sum())})')
                ax.fill_betweenx(np.arange(1, 40), lo, hi, color=color, alpha=.08 if time == 'input' else .17)
        if field in ('qrain_kgkg', 'qnrain_per_kg'):
            ax.set_xscale('symlog', linthresh=1e-9 if field == 'qrain_kgkg' else 1.)
            ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f'{value:.1g}'))
        if field == 'dm_mass_weighted_mm':
            ax.text(.03, .97, 'B1 초기 Dm: 유효 자료 없음', va='top', transform=ax.transAxes, fontsize=8)
        ax.set_title(label); ax.set_xlabel(unit); ax.set_ylabel('모형 연직층 번호 (1 = 최하층)'); ax.set_ylim(.5, 39.5); ax.grid(alpha=.2)
    fig.legend(*axes.flat[0].get_legend_handles_labels(), loc='outside lower center', ncols=2, fontsize=8)
    fig.suptitle(f'{name} · 현재 B1 초기 입력 및 시간 구간 시작 상태 · 중앙값 / 사분위수', fontsize=15)
    fig.savefig(path, metadata={'Software': 'CP02 failure-regime renderer'}); plt.close(fig)
    return rows


def draw_population_layers(name, start, descriptions, states, path):
    fig, axes = plt.subplots(2, 2, figsize=(13, 10), constrained_layout=True); rows = []
    for ax, (layer, field, title, unit) in zip(axes.flat, [(l, f, f'{l} · {label}', unit) for l in ('0to1km', '1to3km') for f, label, unit in (('rh_liquid', '물 기준 상대습도', '1'), ('temperature_K', '기온', 'K'))]):
        labels = []; positions = []; boxes = []
        for group_label, mask in descriptions:
            for time in ('input', f'h{start:02d}'):
                state = states[time]; prefix = f'layer_{layer}_{field}'; valid = mask & state[prefix + '_valid']; item = summary(state[prefix + '_level_mean'][valid]); position = len(labels) + 1
                labels.append(f'{group_label}\n{time}\nn={item["n_valid"]}/{int(mask.sum())}')
                rows.append({'population': name, 'group': group_label, 'group_n': int(mask.sum()), 'time': time, 'field': field, 'level_or_layer': layer, **item})
                if item['n_valid']:
                    boxes.append({'med': item['median'], 'q1': item['q25'], 'q3': item['q75'], 'whislo': item['minimum'], 'whishi': item['maximum'], 'fliers': []}); positions.append(position)
        if boxes: ax.bxp(boxes, positions=positions, showfliers=False, widths=.55)
        ax.set_xticks(range(1, len(labels) + 1), labels, fontsize=8); ax.set_title(title); ax.set_ylabel(unit); ax.grid(axis='y', alpha=.2)
    fig.suptitle(f'{name} · 초기 입력과 구간 시작 · 중앙값 / 사분위수 / 전체 범위', fontsize=15)
    fig.savefig(path, metadata={'Software': 'CP02 failure-regime renderer'}); plt.close(fig)
    return rows


def draw_initial_delta_profiles(name, descriptions, states, limits, path):
    fields = [('qrain_kgkg', '빗물 혼합비', 'kg/kg'), ('qnrain_per_kg', '비 입자수 혼합비', 'kg-1'), ('rh_liquid', '물 기준 상대습도', '1'), ('temperature_K', '기온', 'K')]
    fig, axes = plt.subplots(2, 2, figsize=(13, 10), constrained_layout=True); rows = []
    for ax, (field, title, unit) in zip(axes.flat, fields):
        difference = states['DM_input'][field].astype(np.float64) - states['input'][field].astype(np.float64)
        for n, (label, mask) in enumerate(descriptions):
            items = [summary(difference[mask, level]) for level in range(39)]
            rows.extend({'population': name, 'group': label, 'group_n': int(mask.sum()), 'time': 'input_DM_minus_B1', 'field': field, 'level_or_layer': str(level + 1), **item} for level, item in enumerate(items))
            def vals(key): return np.array([item[key] if item['n_valid'] else np.nan for item in items], dtype=float)
            color = ('#1769a3', '#c34435')[n]
            ax.plot(vals('median'), np.arange(1, 40), color=color, label=f'{label} (n={int(mask.sum())})')
            ax.fill_betweenx(np.arange(1, 40), vals('q25'), vals('q75'), color=color, alpha=.17)
        limit = limits[field]
        if limit:
            ax.set_xscale('symlog', linthresh=max(limit / 1000, 1e-30)); ax.set_xlim(-limit * 1.05, limit * 1.05)
            ax.set_xticks([-limit, -limit / 100, 0, limit / 100, limit])
            ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f'{value:.1g}'))
        else:
            ax.set_xlim(-.5, .5); ax.set_xticks([0]); ax.text(.04, .96, '전체 지점에서 정확히 0', va='top', transform=ax.transAxes, fontsize=9)
        ax.axvline(0, color='#555555', linewidth=.7); ax.set_ylim(.5, 39.5); ax.set_title(title); ax.set_xlabel('초기 후보 - 현재 B1 (' + unit + ')'); ax.set_ylabel('모형 연직층 번호'); ax.grid(alpha=.2)
    fig.legend(*axes.flat[0].get_legend_handles_labels(), loc='outside lower center', ncols=2, fontsize=9)
    fig.suptitle(f'{name} · 초기 입력 차이 · 중앙값 / 사분위수', fontsize=15)
    fig.savefig(path, metadata={'Software': 'CP02 failure-regime renderer'}); plt.close(fig)
    return rows


def corner_max_difference(b1, candidate, field):
    difference = np.abs(candidate[field].astype(np.float64) - b1[field].astype(np.float64))
    positive = b1['corner_weights'][:, None, :] > 0
    if difference.shape != (3688, 39, 4) or not np.isfinite(difference).all():
        raise ValueError('invalid native-corner comparison')
    return np.max(np.where(positive, difference, 0.), axis=(1, 2))


def draw_initial_change(hourly, states, path):
    initial_nr = corner_max_difference(states['input'], states['DM_input'], 'corner_qnrain_per_kg')
    groups = [(key, mask) for key, _, _, mask in focus_masks(hourly)]
    fa_mask = dict(groups)['plus2_new_fa'] & (initial_nr == 0)
    ids = hourly[14]['flat_index_yx'][fa_mask]
    comparisons = {}
    for time in ('h01', 'h02'):
        for field in ('corner_qrain_kgkg', 'corner_qnrain_per_kg'):
            comparisons[time, field] = corner_max_difference(states[time], states['DM_' + time], field)
    fig, axes = plt.subplots(3, 1, figsize=(14, 13), constrained_layout=True)
    labels = ['+2 약한 적중 상실', '+2 새 오경보', '+3 약한 적중 상실', '+5 강수 적중 상실']
    changed = [int(np.sum(mask & (initial_nr != 0))) for _, mask in groups]
    unchanged = [int(np.sum(mask & (initial_nr == 0))) for _, mask in groups]
    x = np.arange(len(groups)); a = axes[0].bar(x - .18, changed, .36, label='초기 한 모서리 이상 차이', color='#b54b30'); b = axes[0].bar(x + .18, unchanged, .36, label='초기 모든 양의 가중치 모서리 동일', color='#3974a0')
    axes[0].bar_label(a, padding=3); axes[0].bar_label(b, padding=3); axes[0].set_xticks(x, labels); axes[0].set_ylabel('지점 수'); axes[0].legend(fontsize=9); axes[0].set_title('초기 비 입자수 혼합비 원시 모서리: 전 39층 비교')
    for ax, (field, title, unit) in zip(axes[1:], [('corner_qrain_kgkg', '빗물 혼합비 차이 크기', 'kg/kg'), ('corner_qnrain_per_kg', '비 입자수 혼합비 차이 크기', 'kg-1')]):
        for time, color in (('h01', '#1769a3'), ('h02', '#b54b30')):
            ax.scatter(range(len(ids)), comparisons[time, field][fa_mask], label=time, s=22, color=color)
        ax.set_yscale('symlog', linthresh=1e-12 if field == 'corner_qrain_kgkg' else 1e-5); ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f'{value:.1g}'))
        ax.set_yticks([0, 1e-10, 1e-7, 1e-4] if field == 'corner_qrain_kgkg' else [0, 1e-3, 1, 1e3, 1e5])
        ax.set_xticks(range(len(ids)), ids, rotation=65, fontsize=7); ax.set_ylabel('최대 절대 차이 (' + unit + ')'); ax.set_title(title + ' · +2 새 오경보 중 초기 동일 지점'); ax.legend(); ax.grid(alpha=.2)
    axes[-1].set_xlabel('RN1 평면 지점 인덱스 (0부터)')
    fig.suptitle('초기 국지 상태와 이후 시각 표본의 차이 · 인과 경로 판정 아님', fontsize=15)
    fig.savefig(path, metadata={'Software': 'CP02 failure-regime renderer'}); plt.close(fig)
    records = []
    for i in np.flatnonzero(fa_mask):
        records.append({'flat_index_yx': int(hourly[14]['flat_index_yx'][i]), 'initial_qnrain_max_abs_difference_per_kg': float(initial_nr[i]), **{f'{time}_{field}_max_abs_difference': float(value[i]) for (time, field), value in comparisons.items()}})
    return records


def write_counts(path, rows):
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0]); writer.writeheader(); writer.writerows(rows)


def render(folder: Path, output: Path, state_folder: Path | None = None):
    configure_font(); hourly, source_pins = read_hourly(folder); counts = build_counts(hourly)
    states, state_receipt = read_control_states(state_folder, hourly) if state_folder else (None, None)
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.failure-plots-', dir=output.parent)); backup = None
    try:
        names = []
        for t in THRESHOLDS:
            name = f'transitions_{t:g}mm.png'; draw_threshold(counts, t, stage / name); names.append(name)
        name = 'weak_plus2.png'; draw_weak(hourly, stage / name); names.append(name)
        rh_limits = None
        if states is not None:
            rh_values = np.concatenate([states[t]['layer_0to1km_rh_liquid_level_mean'][states[t]['layer_0to1km_rh_liquid_valid']] for t in ('h01', 'h02', 'h04')])
            rh_limits = (float(rh_values.min()), float(rh_values.max()))
        for key, hour, title, mask in focus_masks(hourly):
            state = states[f'h{hour - 13:02d}'] if states is not None else None
            name = f'{key}.png'; draw_focus(hourly[hour], mask, title, stage / name, state, rh_limits); names.append(name)
        name = 'control_physics_schematic.png'; draw_physics_schematic(stage / name); names.append(name)
        if states is not None:
            stats = []
            initial_limits = {field: float(np.max(np.abs(states['DM_input'][field].astype(np.float64) - states['input'][field].astype(np.float64)))) for field in ('qrain_kgkg', 'qnrain_per_kg', 'rh_liquid', 'temperature_K')}
            for key, start, label1, mask1, label2, mask2 in population_groups(hourly):
                descriptions = ((label1, mask1), (label2, mask2))
                name = f'profiles_{key}.png'; stats.extend(draw_population_profiles(key, start, descriptions, states, stage / name)); names.append(name)
                name = f'layers_{key}.png'; stats.extend(draw_population_layers(key, start, descriptions, states, stage / name)); names.append(name)
                name = f'initial_delta_{key}.png'; stats.extend(draw_initial_delta_profiles(key, descriptions, states, initial_limits, stage / name)); names.append(name)
            write_counts(stage / 'population_summaries.csv', stats)
            name = 'initial_corner_changes.png'; initial_rows = draw_initial_change(hourly, states, stage / name); names.append(name); write_counts(stage / 'unchanged_initial_new_fa.csv', initial_rows)
        write_counts(stage / 'transition_counts.csv', counts)
        table = ['# 전환과 CSI 전체 표 (108행)', '', '각 행은 같은 예측시간·임계값의 3,688개 대응 지점에 대한 독립 비교다.', '', '| 예측시간 | 임계값 (mm) | 비교 실험 | 새 적중 | 잃은 적중 | 새 오경보 | 사라진 오경보 | B1 CSI | 비교 CSI | CSI 차이 |', '| ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
        table.extend(f"| {r['lead_hour']} | {r['threshold_mm']:g} | {LABELS[r['comparison']]} | {r['gained_hit']} | {r['lost_hit']} | {r['new_fa']} | {r['removed_fa']} | {r['baseline_CSI']:.8f} | {r['comparison_CSI']:.8f} | {r['comparison_CSI'] - r['baseline_CSI']:+.8f} |" for r in counts)
        (stage / 'FULLTABLES.md').write_text('\n'.join(table) + '\n', encoding='utf-8')
        gallery = '# 강수 실패 유형: 대응 전환 진단\n\n모든 비교는 현재 B1을 기준으로 같은 예측시간과 지점에서 계산합니다. 각 임계값과 시간을 개별 표시하며, 변화 위치는 실제 RN1 대응 지점입니다. 원인이나 새로운 예보 설정을 확정하지 않습니다. [전환과 CSI 전체 표](FULLTABLES.md)\n\n'
        if states is not None:
            gallery += '현재 B1 초기 입력과 각 시간 구간 시작 상태를 사후 분류한 집단별로 표시합니다. 프로파일의 범례 n은 전체 집단 크기이며 각 층의 유효 n과 전체 범위는 [집단 통계](population_summaries.csv)에 있습니다. B1 초기 Dm은 모두 유효하지 않아 0으로 대체하지 않습니다. 지도 배경은 구간 시작 0–1 km 물 기준 상대습도의 연직층 평균이며 추정 원인이나 판정 기준이 아닙니다. 상자 수염은 전체 범위이고, 높이 구간의 층 평균은 질량가중 적분이 아닙니다. 이후 시각 차이는 첫 분기 시각이나 인과 경로를 뜻하지 않습니다. [초기 동일 새 오경보 지점별 차이](unchanged_initial_new_fa.csv)\n\n'
        gallery += '\n\n'.join(f'![{name}]({name})' for name in names) + '\n'
        (stage / 'gallery.md').write_text(gallery, encoding='utf-8')
        metadata = {'source_receipt_sha256': sha(folder / 'receipt.json'), 'inputs': {f'hour_{hour}_arrays.npz': source_pins[f'hour_{hour}_arrays.npz']['sha256'] for hour in range(13, 19)}, 'renderer_sha256': sha(Path(__file__)), 'font_sha256': sha(FONT), 'matplotlib_version': matplotlib.__version__, 'outputs': {name: sha(stage / name) for name in (*names, 'gallery.md', 'FULLTABLES.md', 'transition_counts.csv')}}
        if states is not None:
            metadata['state_receipt_sha256'] = sha(state_folder / 'receipt.json'); metadata['state_protocol_sha256'] = state_receipt['protocol_sha256']; metadata['outputs']['population_summaries.csv'] = sha(stage / 'population_summaries.csv'); metadata['outputs']['unchanged_initial_new_fa.csv'] = sha(stage / 'unchanged_initial_new_fa.csv')
        (stage / 'metadata.json').write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        if output.exists():
            backup = Path(tempfile.mkdtemp(prefix='.failure-backup-', dir=output.parent)); backup.rmdir(); output.rename(backup)
        try:
            stage.rename(output)
        except BaseException:
            if backup is not None: backup.rename(output)
            raise
        if backup is not None: shutil.rmtree(backup)
    finally:
        if stage.exists(): shutil.rmtree(stage)


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--analysis', type=Path, default=ANALYSIS); parser.add_argument('--output', type=Path, default=OUTPUT); parser.add_argument('--state-results', type=Path)
    args = parser.parse_args(); render(args.analysis, args.output, args.state_results)


if __name__ == '__main__': main()
