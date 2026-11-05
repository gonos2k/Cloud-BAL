#!/usr/bin/env python3
"""Render two pinned mechanism diagrams for the CP02 initial-boundary report."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
import shutil
import struct
import tempfile
import zipfile
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / 'docs/evidence/cp02_initial_boundaries_20261105'
SCIENCE = BUNDLE / 'science'
SOURCEPINS = BUNDLE / 'native/sourcepins'
OUT = BUNDLE / 'mechanism_figures'
FONT = Path('/usr/share/fonts/truetype/nanum/NanumGothic.ttf')
NAMES = ('rk_mass_coupled_entry.png', 'phi_pressure_thermo_chain.png')
PINS = {
    'writer analysis': '81136f351c4804be078761cbfc57a715ccd58bf24ffd1537cb4c180a1b3d475b',
    'phi analysis': '47bd19bf23651971ed63f27f13a4a9b8553f7d366771134d7811bcaee794dcc4',
    'source manifest': '9bac690cbe8ec7ad32ea4bd5057fdf6fcb3e86c599c279b5758f2f7e145c41cb',
    'font': '48a28e97b34fc8e5b157657633670cd1b7de126cfc414da65ce9c3d5bc8be733',
}
NUMERATOR_PINS = {
    'closure': '15a5ffdde46d24358af3d9815fa7ff0a63d9bf4ce381cbffa1e0df6ee9f6c300',
    'B1 receipt': '8fa8cfdc075a6e3ba941572b93ae156cf5268576180cc8a034327a1b6afc3992',
    'DM065 receipt': '88a217d936f8ee98c39bc2a954e44b81cf3e0268431009b61063897fdf416a0c',
    'B1 numerator stream': '22c4f973cce3a84611a1094cbeb34aceccb8ad93875f8e7fe2ec48ebd2b5e3d5',
    'DM065 numerator stream': 'c92998e180c439e51e577e875df6faadcc18079e3b0e2acfe4283815fb209fd7',
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def f32(word: str) -> float:
    return struct.unpack('<f', bytes.fromhex(word))[0]


def read_json(path: Path) -> dict:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f'missing or unsafe input: {path}')
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f'invalid JSON input: {path}') from exc


def core_inputs() -> dict[str, Path]:
    return {
        'writer analysis': SCIENCE / 'writer_nr20330/analysis.json',
        'phi analysis': SCIENCE / 'phi_p20183/analysis.json',
        'source manifest': SOURCEPINS / 'manifest.json',
        'font': FONT,
    }


def verify_core_inputs(paths: dict[str, Path]) -> None:
    for label, expected in PINS.items():
        path = paths[label]
        if not path.is_file() or path.is_symlink() or sha(path) != expected:
            raise ValueError(f'pinned input mismatch: {label}')


def verify_sourcepins() -> dict[str, Path]:
    manifest_path = SOURCEPINS / 'manifest.json'
    verify_core_inputs(core_inputs())
    manifest = read_json(manifest_path)
    if manifest.get('status') != 'PASS':
        raise ValueError('source pin manifest is not PASS')
    inputs = {'source manifest': manifest_path}
    for row in manifest.get('files', []):
        path = SOURCEPINS / Path(row['archive_path']).name
        if not path.is_file() or path.is_symlink() or sha(path) != row['sha256']:
            raise ValueError(f'source pin mismatch: {path.name}')
        inputs[path.name] = path
    if len(inputs) != len(manifest.get('files', [])) + 1:
        raise ValueError('source pin manifest has missing or duplicate entries')
    return inputs


def load_writer() -> tuple[list[dict], dict[str, Path]]:
    path = SCIENCE / 'writer_nr20330/analysis.json'
    data = read_json(path)
    if data.get('status') != 'PASS_ACTUAL_WRITER_ANALYSIS' or data.get('target') != 'nr20330':
        raise ValueError('writer analysis target or status differs')
    if data.get('target_rank_ijk_1based') != [5, 141, 142, 2]:
        raise ValueError('writer analysis is not the pinned k=2 point')
    by_stage = {}
    for pair in data['paired_calls']:
        if pair.get('classification', {}).get('DM065') != 'KDM_NR_pointer_bound':
            continue
        row = pair['DM065']
        stage = row.get('rk_step')
        if row.get('candidate_timestep') == 1 and stage in (1, 2, 3):
            by_stage[stage] = row
    if set(by_stage) != {1, 2, 3}:
        raise ValueError('writer analysis lacks the three pointer-bound RK stages')
    rows = []
    for stage, row in sorted(by_stage.items()):
        fields = row['entry_fields_raw']
        output = row['return_fields_raw']['scalar_current']
        rows.append({
            'stage': stage,
            'dt': f32(fields['dt']),
            'nr_entry': f32(fields['scalar_current']),
            'advect': f32(fields['advection_tendency']),
            'msfty': f32(fields['msfty']),
            'sc_tend': f32(fields['scalar_tendency']),
            'nr_return': f32(output),
            'nr_candidate': row['source_order_reference']['reference_nr'],
        })
        if not math.isclose(rows[-1]['nr_return'], rows[-1]['nr_candidate'], rel_tol=0, abs_tol=0):
            raise ValueError(f'RK stage {stage} source-order candidate disagrees with captured return')
    return rows, {'writer analysis': path}


def load_phi() -> tuple[dict, dict[str, Path]]:
    path = SCIENCE / 'phi_p20183/analysis.json'
    data = read_json(path)
    if data.get('status') != 'PASS_OBSERVED_PHI_RECOUNT' or data.get('target') != 'p20183':
        raise ValueError('phi analysis target or status differs')
    arms = data['arms']
    def call(arm: str, function: str, sequence: int) -> dict:
        matches = [x for x in arms[arm]['calls'] if x['function'] == function and x['entry_sequence'] == sequence]
        if len(matches) != 1:
            raise ValueError(f'missing unique {arm} {function} call at sequence {sequence}')
        return matches[0]
    # The distinct pressure is phi call 45; prep and KDM consume its same-call result.
    phi_b1, phi_dm = call('B1', 'phi', 45), call('DM065', 'phi', 45)
    prep_b1, prep_dm = call('B1', 'prep', 52), call('DM065', 'prep', 52)
    kdm_b1, kdm_dm = call('B1', 'kdm', 54), call('DM065', 'kdm', 54)
    values = {
        'ph_B1': f32(phi_b1['entry_fields_raw']['ph']), 'ph_DM': f32(phi_dm['entry_fields_raw']['ph']),
        'ph_word_B1': phi_b1['entry_fields_raw']['ph'], 'ph_word_DM': phi_dm['entry_fields_raw']['ph'],
        'p_B1': f32(phi_b1['return_fields_raw']['p']), 'p_DM': f32(phi_dm['return_fields_raw']['p']),
        'pf_B1': f32(prep_b1['return_fields_raw']['pf']), 'pf_DM': f32(prep_dm['return_fields_raw']['pf']),
        'pii_B1': f32(prep_b1['return_fields_raw']['pii']), 'pii_DM': f32(prep_dm['return_fields_raw']['pii']),
        'th_B1': f32(prep_b1['return_fields_raw']['th']), 'th_DM': f32(prep_dm['return_fields_raw']['th']),
        'tk_B1': struct.unpack('<f', struct.pack('<f', f32(prep_b1['return_fields_raw']['th']) * f32(prep_b1['return_fields_raw']['pii'])))[0],
        'tk_DM': struct.unpack('<f', struct.pack('<f', f32(prep_dm['return_fields_raw']['th']) * f32(prep_dm['return_fields_raw']['pii'])))[0],
    }
    expected = {'ph_DM_minus_B1': -7.62939453125e-6, 'p_DM_minus_B1': -0.1328125,
                'pii_DM_minus_B1': -4.172325134277344e-7, 'tk_DM_minus_B1': -0.0001220703125}
    observed = {'ph_DM_minus_B1': values['ph_DM'] - values['ph_B1'],
                'p_DM_minus_B1': values['p_DM'] - values['p_B1'],
                'pii_DM_minus_B1': values['pii_DM'] - values['pii_B1'],
                'tk_DM_minus_B1': values['tk_DM'] - values['tk_B1']}
    for key, target in expected.items():
        if not math.isclose(observed[key], target, rel_tol=0, abs_tol=1e-12):
            raise ValueError(f'phi observed delta differs for {key}: {observed[key]}')
    if values['th_B1'] != values['th_DM'] or values['th_B1'] != 300.4675598144531:
        raise ValueError('pre-KDM TH is not identical at the selected point')
    return values, {'phi analysis': path}


def load_numerator(phi: dict) -> tuple[dict, dict[str, Path]]:
    base = BUNDLE / 'native/numerator_p20183'
    paths = {'closure': base / 'paired_closure.json'}
    closure = read_json(paths['closure'])
    if (closure.get('status') != 'PASS_NUMERATOR_OBSERVATION' or
            sha(paths['closure']) != NUMERATOR_PINS['closure']):
        raise ValueError('paired numerator closure is not PASS')
    values = {}
    expected_words = {
        'B1': ('a8178044', 'f045253d', {'ph': '7de0a842', 'ph_next': '5ef20143', 'phb': '4c280546', 'phb_next': '39751446'}),
        'DM065': ('b0178044', 'f046253d', {'ph': '7ce0a842', 'ph_next': '5ef20143', 'phb': '4c280546', 'phb_next': '39751446'}),
    }
    for arm in ('B1', 'DM065'):
        label = f'{arm} receipt'
        paths[label] = base / arm / 'numerator_receipt.json'
        receipt = read_json(paths[label])
        closure_arm = closure.get('arms', {}).get(arm, {})
        if (receipt.get('status') != 'PASS_NUMERATOR_OBSERVATION' or receipt.get('arm') != arm or
                receipt.get('target') != 'p20183' or receipt.get('lane') != 2 or
                sha(paths[label]) != NUMERATOR_PINS[label] or
                closure_arm.get('receipt_sha256') != NUMERATOR_PINS[label]):
            raise ValueError(f'{arm} numerator receipt is not pinned for the selected target')
        stream = closure_arm.get('streams', {}).get('numerator_rank5.jsonl', {})
        stream_label = f'{arm} numerator stream'
        paths[stream_label] = base / arm / 'numerator_rank5.jsonl.gz'
        if not paths[stream_label].is_file() or paths[stream_label].is_symlink() or sha(paths[stream_label]) != NUMERATOR_PINS[stream_label] or stream.get('gzip_sha256') != NUMERATOR_PINS[stream_label]:
            raise ValueError(f'{arm} archived numerator stream hash differs')
        if receipt.get('operand_slot_mapping') != {'ph': 1, 'ph_next': 0, 'phb': 3, 'phb_next': 2}:
            raise ValueError(f'{arm} numerator lane operand mapping differs')
        if receipt.get('actual_instruction_order') != 'slot0 - slot1; slot2 + result; result - slot3; then division/log and AL vector store':
            raise ValueError(f'{arm} observed numerator instruction order differs')
        words = receipt.get('input_words', {})
        expected_numerator, expected_al, expected_inputs = expected_words[arm]
        phi_word_key = 'ph_word_B1' if arm == 'B1' else 'ph_word_DM'
        if words != expected_inputs or words.get('ph') != phi[phi_word_key]:
            raise ValueError(f'{arm} numerator inputs do not bridge to selected phi call')
        if receipt.get('numerator_word') != expected_numerator or receipt.get('stored_al_word') != expected_al:
            raise ValueError(f'{arm} numerator or AL store word differs')
        values[f'numerator_{arm}'] = f32(receipt['numerator_word'])
        values[f'al_{arm}'] = f32(receipt['stored_al_word'])
        values[f'numerator_word_{arm}'] = receipt['numerator_word']
        values[f'al_word_{arm}'] = receipt['stored_al_word']
    values['delta_numerator'] = values['numerator_DM065'] - values['numerator_B1']
    values['delta_ph'] = phi['ph_DM'] - phi['ph_B1']
    if values['delta_numerator'] != 0.0009765625 or values['delta_ph'] != -7.62939453125e-6:
        raise ValueError('actual numerator and selected PH deltas differ from pinned observations')
    if abs(values['delta_numerator'] / values['delta_ph']) != 128.0:
        raise ValueError('observed numerator sensitivity ratio differs')
    return values, paths


def configure_font() -> None:
    font_manager.fontManager.addfont(str(FONT))
    plt.rcParams.update({'font.family': font_manager.FontProperties(fname=str(FONT)).get_name(),
                         'axes.unicode_minus': False, 'savefig.dpi': 150})


def box(ax, xy, width, height, title, body, color='#edf3f8', title_color='#16324f', fontsize=10):
    x, y = xy
    patch = FancyBboxPatch((x, y), width, height, boxstyle='round,pad=0.012,rounding_size=0.02',
                           transform=ax.transAxes, facecolor=color, edgecolor='#8da2b5', linewidth=1.1)
    ax.add_patch(patch)
    ax.text(x + width / 2, y + height * .70, title, transform=ax.transAxes, ha='center', va='center',
            color=title_color, fontsize=fontsize, weight='bold')
    ax.text(x + width / 2, y + height * .32, body, transform=ax.transAxes, ha='center', va='center',
            color='#263746', fontsize=fontsize - 1, linespacing=1.25)


def draw_rk(rows: list[dict], path: Path) -> None:
    fig, ax = plt.subplots(figsize=(13, 7.2), constrained_layout=True)
    ax.axis('off')
    colors = ['#d8e9f7', '#e0f0e4', '#f7e8cf']
    for i, row in enumerate(rows):
        x = .025 + i * .325
        tendency = row['advect'] * row['msfty']
        box(ax, (x, .64), .27, .23, f"RK 단계 {row['stage']} · dt {row['dt']:g} s",
            f"RK 진입 NR {row['nr_entry']:.9g} kg^-1\nadvect {row['advect']:.8g} × msfty {row['msfty']:.7g}\n질량결합 tendency 항 {tendency:.8g}",
            colors[i], fontsize=9)
        next_label = 'RK 반환 → 다음 RK 진입' if i < 2 else 'RK 반환 → 첫 KDM6 ENTRY'
        box(ax, (x, .31), .27, .19, next_label,
            f"NR {row['nr_return']:.9g} kg^-1\nsource-order 후보 일치",
            '#f5f7fa', fontsize=9)
        ax.annotate('', xy=(x + .135, .52), xytext=(x + .135, .62), xycoords=ax.transAxes,
                    arrowprops={'arrowstyle': '->', 'lw': 1.5, 'color': '#496579'})
        if i < 2:
            ax.annotate('', xy=(x + .325, .76), xytext=(x + .275, .76), xycoords=ax.transAxes,
                        arrowprops={'arrowstyle': '->', 'lw': 1.4, 'color': '#496579'})
    ax.text(.5, .14,
            'ID 20330 = flat_index_yx · native (141,142,k2) · DM065 관측 · 초기 NR=0  |  B1의 같은 RK ENTRY/RETURN NR은 모두 0',
            transform=ax.transAxes, ha='center', fontsize=11, weight='bold', color='#273849')
    footer = (
        '소스 식: tendency = advect_tend × msfty + sc_tend',
        'μold = MU_OLD + MU_BASE; μnew = MU_NEW + MU_BASE; scalar₂ = ((c₁·μold+c₂)·scalar₁ + dt·tendency)/(c₁·μnew+c₂).',
        'float32 source-order 후보(명령어 반올림 증명 아님). advect×msfty는 질량결합 tendency(단위 미지정), NR/s 또는 물리 질량 flux가 아님.',
        'SIMD 분자는 두 번째 그림 참조; grouped 재결합은 실행하지 않은 오프라인 대안만. NR은 평균 입자 직경·물리 질량수지가 아님.',
    )
    for i, line in enumerate(footer):
        ax.text(.03, .09 - i * .024, line, transform=ax.transAxes, ha='left', va='center',
                fontsize=8, color='#465867')
    fig.suptitle('초기 NR 경계: RK 질량결합 이류에서 첫 NR ENTRY까지', fontsize=16, weight='bold')
    fig.savefig(path, metadata={'Software': 'CP02 initial mechanisms plotter'})
    plt.close(fig)


def draw_phi(v: dict, numerator: dict, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(13, 7.2), constrained_layout=True)
    ax.axis('off')
    xs = [.025, .22, .415, .61, .805]
    titles = ['phi 입력 ph', 'phi 반환 Ppert', 'prep 반환 PF', 'prep 반환 PII', 'TK=TH×PII']
    body = [
        f"B1 {v['ph_B1']:.8f}\nDM065 {v['ph_DM']:.8f}\nΔ(DM-B1) -7.62939453125e-6 m²/s²",
        f"B1 {v['p_B1']:.5f} Pa\nDM065 {v['p_DM']:.5f} Pa\nΔ(DM-B1) -0.1328125 Pa",
        f"B1 {v['pf_B1']:.5f} Pa\nDM065 {v['pf_DM']:.5f} Pa\nprep 압력 입력",
        f"B1 {v['pii_B1']:.9f}\nDM065 {v['pii_DM']:.9f}\nΔ(DM-B1) -4.172325134277344e-7",
        f"B1 {v['tk_B1']:.8f} K\nDM065 {v['tk_DM']:.8f} K\nΔ(DM-B1) -0.0001220703125 K",
    ]
    palette = ['#e6eef8', '#e6eef8', '#e6eef8', '#fff0d9', '#e8f3e8']
    for i, (x, title, text) in enumerate(zip(xs, titles, body)):
        box(ax, (x, .59), .17, .28, title, text, palette[i], fontsize=9)
        if i < len(xs) - 1:
            ax.annotate('', xy=(xs[i + 1] - .008, .73), xytext=(x + .178, .73), xycoords=ax.transAxes,
                        arrowprops={'arrowstyle': '->', 'lw': 1.4, 'color': '#496579'})
    callout = FancyBboxPatch((.035, .405), .93, .155, boxstyle='round,pad=.012,rounding_size=.02',
                             transform=ax.transAxes, facecolor='#fff7e8', edgecolor='#c59b58', linewidth=1.1)
    ax.add_patch(callout)
    ax.text(.5, .535, '실제 SIMD lane 2 · phi7: (PH_next - PH) + PHB_next - PHB',
            transform=ax.transAxes, ha='center', va='center', fontsize=10, weight='bold', color='#51401f')
    ax.text(.5, .502,
            f"분자 B1 {numerator['numerator_B1']:.10f} ({numerator['numerator_word_B1']})  |  "
            f"DM065 {numerator['numerator_DM065']:.10f} ({numerator['numerator_word_DM065']})  |  Δ(DM-B1)=+0.0009765625",
            transform=ax.transAxes, ha='center', va='center', fontsize=8.5, color='#463a24')
    ax.text(.5, .470,
            f"ΔPH={numerator['delta_ph']:.14g} m²/s²  →  |Δnumerator| / |ΔPH| = 128  |  "
            f"AL B1 {numerator['al_B1']:.10f} [{numerator['al_word_B1']}]; DM065 {numerator['al_DM065']:.10f} [{numerator['al_word_DM065']}]",
            transform=ax.transAxes, ha='center', va='center', fontsize=7.8, color='#463a24')
    ax.text(.5, .427, '한 lane·arm당 phi call 1회 관측 · grouped 재결합은 실행 안 함 · forecast impact 주장 없음',
            transform=ax.transAxes, ha='center', va='center', fontsize=7.8, color='#655638')
    box(ax, (.20, .13), .27, .20, '설정 / 경로', 'ID 20183 (flat_index_yx)\nnative (144,142,k4) · phi → prep → KDM', '#f5f7fa', fontsize=9)
    box(ax, (.53, .13), .27, .20, '동일한 prep TH', f"B1 = DM065 = {v['th_B1']:.8f} K\nP 변화가 PII 및 TK 차이와 함께 관측됨", '#f5f7fa', fontsize=9)
    ax.text(.5, .075, '계산 구조: ph → calc_p_rho_phi → Ppert → PF → PII → TK=TH×PII  |  NH=-1 (branch bit 1), hypsometric_opt=2, use_theta_m=1',
            transform=ax.transAxes, ha='center', fontsize=11, weight='bold', color='#273849')
    ax.text(.5, .018,
            '소스 방정식과 캡처된 float32 결과를 나란히 표시. 차이는 관측값이며, '
            '세부 원인을 특정하지 않음. grouped 재결합은 오프라인 대안 후보이며 actual SIMD 재현식은 관측 그대로; '
            'μ는 호출 인자이나 nonhydrostatic/hypsometric_opt=2 경로에서 비활성.',
            transform=ax.transAxes, ha='center', fontsize=8.5, color='#465867', wrap=True)
    fig.suptitle('20183 압력–열 상태 경로: 같은 TH, 작은 PII·TK 차이', fontsize=16, weight='bold')
    fig.savefig(path, metadata={'Software': 'CP02 initial mechanisms plotter'})
    plt.close(fig)


def write_gallery(stage: Path, input_hashes: dict[str, str]) -> None:
    captions = [
        ('rk_mass_coupled_entry.png', '20330, k=2: 초기 NR, RK3 질량결합 이류 항, 단계별 첫 ENTRY/반환 연결.'),
        ('phi_pressure_thermo_chain.png', 'ID 20183 (flat_index_yx): phi → prep → KDM 경로와 실제 lane-2 SIMD 분자 관측.'),
    ]
    md = ['# CP02 초기 경계 메커니즘 그림', '', '두 그림은 고정된 분석 JSON과 sourcepins를 검증한 뒤 생성했습니다.', '']
    html_parts = ['<!doctype html><html lang="ko"><meta charset="utf-8"><title>CP02 초기 경계 메커니즘 그림</title>',
                  '<style>body{font:16px sans-serif;max-width:1100px;margin:2em auto;padding:0 1em;color:#263746}img{max-width:100%;border:1px solid #ccd6df}section{margin:2.5em 0}code{font-size:.85em}</style><body>',
                  '<h1>CP02 초기 경계 메커니즘 그림</h1>']
    for name, caption in captions:
        md += [f'## {caption}', '', f'![{html.escape(caption)}]({name})', '']
        html_parts += [f'<section><h2>{html.escape(caption)}</h2><img src="{name}" alt="{html.escape(caption)}"></section>']
    md += ['## 검증된 입력 SHA-256', ''] + [f'- `{name}`: `{digest}`' for name, digest in sorted(input_hashes.items())]
    html_parts += ['<h2>검증된 입력 SHA-256</h2><ul>']
    html_parts += [f'<li><code>{html.escape(name)}</code>: <code>{digest}</code></li>' for name, digest in sorted(input_hashes.items())]
    html_parts += ['</ul></body></html>']
    (stage / 'gallery.md').write_text('\n'.join(md) + '\n', encoding='utf-8')
    (stage / 'index.html').write_text('\n'.join(html_parts) + '\n', encoding='utf-8')
    with zipfile.ZipFile(stage / 'offline_gallery.zip', 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in (*NAMES, 'gallery.md', 'index.html'):
            info = zipfile.ZipInfo(name, date_time=(2026, 11, 5, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, (stage / name).read_bytes())


def write_receipt(stage: Path, input_hashes: dict[str, str]) -> None:
    output_names = (*NAMES, 'gallery.md', 'index.html', 'offline_gallery.zip')
    receipt = {
        'status': 'PASS',
        'inputs_sha256': dict(sorted(input_hashes.items())),
        'renderer_sha256': sha(Path(__file__)),
        'font_sha256': sha(FONT),
        'outputs_sha256': {name: sha(stage / name) for name in output_names},
    }
    (stage / 'receipt.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def build(output: Path = OUT) -> None:
    pinned = core_inputs()
    verify_core_inputs(pinned)
    sources = verify_sourcepins()
    if output.exists():
        if output.is_symlink() or not output.is_dir():
            raise FileExistsError(f'refusing to overwrite: {output}')
        children = list(output.iterdir())
        prior = output / 'prior_versions'
        if len(children) != 1 or children[0] != prior or prior.is_symlink() or not prior.is_dir():
            raise FileExistsError(f'refusing to overwrite: {output}')
    writer, writer_inputs = load_writer()
    phi, phi_inputs = load_phi()
    numerator, numerator_inputs = load_numerator(phi)
    paths = {**writer_inputs, **phi_inputs, **numerator_inputs, **sources, 'font': FONT}
    for label, path in paths.items():
        if not path.is_file() or path.is_symlink():
            raise ValueError(f'missing or unsafe pinned input: {label}')
    input_hashes = {label: sha(path) for label, path in paths.items()}
    configure_font()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f'.{output.name}.stage-', dir=output.parent) as temporary:
        stage = Path(temporary) / 'stage'
        stage.mkdir()
        draw_rk(writer, stage / NAMES[0])
        draw_phi(phi, numerator, stage / NAMES[1])
        write_gallery(stage, input_hashes)
        write_receipt(stage, input_hashes)
        backup = Path(temporary) / 'previous'
        if output.exists():
            shutil.copytree(output / 'prior_versions', stage / 'prior_versions')
            os.replace(output, backup)
        try:
            os.replace(stage, output)
        except Exception:
            if backup.exists():
                os.replace(backup, output)
            raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUT)
    args = parser.parse_args()
    build(args.output)


if __name__ == '__main__':
    main()
