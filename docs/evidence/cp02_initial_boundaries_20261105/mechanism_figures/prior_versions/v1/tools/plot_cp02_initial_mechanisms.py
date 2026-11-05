#!/usr/bin/env python3
"""Render two pinned mechanism diagrams for the CP02 initial-boundary report."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import struct
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


def verify_sourcepins() -> dict[str, Path]:
    manifest_path = SOURCEPINS / 'manifest.json'
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


def configure_font() -> None:
    if not FONT.is_file():
        raise ValueError(f'pinned Nanum font missing: {FONT}')
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
    fig, ax = plt.subplots(figsize=(13, 6), constrained_layout=True)
    ax.axis('off')
    colors = ['#d8e9f7', '#e0f0e4', '#f7e8cf']
    for i, row in enumerate(rows):
        x = .025 + i * .325
        tendency = row['advect'] * row['msfty']
        box(ax, (x, .58), .27, .26, f"RK 단계 {row['stage']} · dt {row['dt']:g} s",
            f"NR ENTRY {row['nr_entry']:.9g}\nadvect {row['advect']:.8g} × msfty {row['msfty']:.7g}\n질량결합 항 후보 {tendency:.8g}",
            colors[i], fontsize=10)
        box(ax, (x, .20), .27, .22, 'RK 반환 / 다음 ENTRY',
            f"NR {row['nr_return']:.9g}\nsource-order 후보 일치",
            '#f5f7fa', fontsize=10)
        ax.annotate('', xy=(x + .135, .43), xytext=(x + .135, .56), xycoords=ax.transAxes,
                    arrowprops={'arrowstyle': '->', 'lw': 1.5, 'color': '#496579'})
        if i < 2:
            ax.annotate('', xy=(x + .325, .70), xytext=(x + .275, .70), xycoords=ax.transAxes,
                        arrowprops={'arrowstyle': '->', 'lw': 1.4, 'color': '#496579'})
            ax.text(x + .30, .54, '반환 NR이\n다음 단계로', transform=ax.transAxes,
                    ha='center', va='center', fontsize=8, color='#496579')
    ax.text(.5, .10,
            'ID 20330 = flat_index_yx · native (141,142,k2) · DM065 관측 · 초기 NR=0  |  B1의 같은 RK ENTRY/RETURN NR은 모두 0',
            transform=ax.transAxes, ha='center', fontsize=11, weight='bold', color='#273849')
    ax.text(.5, .015,
            '소스 식 (rk_step>1): tendency = advect_tend × msfty + sc_tend; '
            'scalar₂ = ((c₁·μold+c₂)·scalar₁ + dt·tendency)/(c₁·μnew+c₂). '
            'float32 소스 순서 후보이며 명령어 반올림 증명은 아님. 분자 집계/그룹화는 실제 SIMD 분자 미확보로 오프라인 후보만. '
            'NR·항 값은 직경/물리 질량수지가 아님.',
            transform=ax.transAxes, ha='center', fontsize=8.5, color='#465867', wrap=True)
    fig.suptitle('초기 NR 경계: RK 질량결합 이류에서 첫 NR ENTRY까지', fontsize=16, weight='bold')
    fig.savefig(path, metadata={'Software': 'CP02 initial mechanisms plotter'})
    plt.close(fig)


def draw_phi(v: dict, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(13, 6.2), constrained_layout=True)
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
    box(ax, (.20, .20), .27, .22, '설정 / 경로', 'ID 20183 = flat_index_yx\nnative (144,142,k4) · phi → prep → KDM', '#f5f7fa', fontsize=9)
    box(ax, (.53, .20), .27, .22, '동일한 prep TH', f"B1 = DM065 = {v['th_B1']:.8f} K\nP 변화가 PII 및 TK 차이와 함께 관측됨", '#f5f7fa', fontsize=9)
    ax.text(.5, .11, '계산 구조: ph → calc_p_rho_phi → Ppert → PF → PII → TK=TH×PII  |  NH=-1 (branch bit 1), hypsometric_opt=2, use_theta_m=1',
            transform=ax.transAxes, ha='center', fontsize=11, weight='bold', color='#273849')
    ax.text(.5, .025,
            '소스 방정식과 캡처된 float32 결과를 나란히 표시. 차이는 관측값이며, '
            '세부 원인을 특정하지 않음. Ppert/PII→TK의 마지막 비트 배분은 반올림 순서 후보로만 취급; '
            'μ는 호출 인자이나 nonhydrostatic/hypsometric_opt=2 경로에서 비활성.',
            transform=ax.transAxes, ha='center', fontsize=8.5, color='#465867', wrap=True)
    fig.suptitle('20183 압력–열 상태 경로: 같은 TH, 작은 PII·TK 차이', fontsize=16, weight='bold')
    fig.savefig(path, metadata={'Software': 'CP02 initial mechanisms plotter'})
    plt.close(fig)


def write_gallery(stage: Path, input_hashes: dict[str, str]) -> None:
    captions = [
        ('rk_mass_coupled_entry.png', '20330, k=2: 초기 NR, RK3 질량결합 이류 항, 단계별 첫 ENTRY/반환 연결.'),
        ('phi_pressure_thermo_chain.png', '20183: 관측된 phi → prep → KDM 압력·PII·TK 경로와 구분한 반올림 후보.'),
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


def build(output: Path = OUT) -> None:
    if output.exists():
        raise FileExistsError(f'refusing to overwrite: {output}')
    writer, writer_inputs = load_writer()
    phi, phi_inputs = load_phi()
    sources = verify_sourcepins()
    paths = {**writer_inputs, **phi_inputs, **sources, 'font': FONT}
    for label, path in paths.items():
        if not path.is_file() or path.is_symlink():
            raise ValueError(f'missing or unsafe pinned input: {label}')
    input_hashes = {label: sha(path) for label, path in paths.items()}
    configure_font()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()
    draw_rk(writer, output / NAMES[0])
    draw_phi(phi, output / NAMES[1])
    write_gallery(output, input_hashes)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUT)
    args = parser.parse_args()
    build(args.output)


if __name__ == '__main__':
    main()
