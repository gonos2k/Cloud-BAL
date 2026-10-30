#!/usr/bin/env python3
"""Draw the precipitation analysis pathway and paired threshold-skill examples."""
import argparse
import csv
import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

CASES = ('ORIGINAL', 'CURRENT_OFF', 'CURRENT_HYDRO', 'CURRENT_LIQUID')
EXPECTED = 'f746eb6b55bc6ba6510ba27660d6086c4c7a774bcf4ddcc4caec0ccaf8daec77'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scores(path):
    if digest(path) != EXPECTED:
        raise ValueError('categorical score file differs from independent verification receipt')
    with path.open(newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    result = {}
    for lead in (1, 6):
        for case in CASES:
            selected = [r for r in rows if int(r['lead_hour']) == lead and r['case'] == case
                        and float(r['threshold_mm']) == 5]
            if len(selected) != 1:
                raise ValueError(f'missing or duplicate row: {lead}, {case}')
            row = selected[0]
            h, m, fa = (int(row[k]) for k in ('hit', 'miss', 'false_alarm'))
            csi = h / (h + m + fa)
            if abs(csi - float(row['CSI'])) > 1e-12 or int(row['points']) != 3688:
                raise ValueError(f'inconsistent score: {lead}, {case}')
            result[lead, case] = h, m, fa, csi
    return result


def box(ax, x, y, w, h, text, color='#eef5fa', size=12):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.012,rounding_size=0.012',
                                linewidth=1.1, edgecolor='#4c6575', facecolor=color))
    ax.text(x+w/2, y+h/2, text, ha='center', va='center', fontsize=size, linespacing=1.45)


def arrow(ax, x1, y1, x2, y2):
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops={'arrowstyle': '->', 'lw': 1.8, 'color': '#425968'})


def physics():
    fig, ax = plt.subplots(figsize=(12, 8))
    ax.set(xlim=(0, 1), ylim=(0, 1)); ax.axis('off')
    ax.text(.5, .965, 'From radar reflectivity to forecast precipitation', ha='center',
            va='top', fontsize=17, weight='bold')
    box(ax, .05, .76, .26, .12, 'Reflectivity D\n[dBZ]', '#eef5fa', 13)
    box(ax, .37, .76, .26, .12, r'$Z=10^{D/10}$'+'\n'+r'[$\mathrm{mm^6\,m^{-3}}$]', size=13)
    box(ax, .69, .76, .26, .12, r'$C=\min[0.02,10^{-4}(Z/1000)^{0.55}]$'+'\n'+r'[$\mathrm{kg\,m^{-3}}$]', size=11)
    arrow(ax, .32, .82, .36, .82); arrow(ax, .64, .82, .68, .82)
    box(ax, .69, .53, .26, .12, r'$q_{total}=C/\rho_d$'+'\n'+r'$\rho_d$: dry-air density [$\mathrm{kg\,m^{-3}}$]'+'\n'+r'$q$: [$\mathrm{kg\,kg^{-1}}$ dry air]', '#f1f7ec', 11)
    box(ax, .37, .53, .26, .12, 'Phase partition\n'+r'$(q_r, q_s, q_g)$', '#f1f7ec', 13)
    box(ax, .05, .53, .26, .12, 'Background + radar proposal\n'+r'Initial $q_v, q_c, q_i, q_r, q_s, q_g, T, p$', '#f1f7ec', 10.5)
    arrow(ax, .82, .75, .82, .67); arrow(ax, .68, .59, .64, .59); arrow(ax, .36, .59, .32, .59)
    box(ax, .05, .28, .40, .13, 'WRF evolution: microphysics + transport\nFallout and convective parameterization\nCondensation heats; evaporation cools', '#fff5e7', 11)
    box(ax, .55, .28, .40, .13, '1-h accumulated precipitation\n'+r'$P_h=[RAINC+RAINNC](t)-[RAINC+RAINNC](t-1h)$'+'\n'+r'$P_h$ [mm]', '#fff5e7', 11)
    arrow(ax, .18, .52, .18, .43); arrow(ax, .46, .345, .54, .345)
    ax.text(.05, .13, 'Interpretation: reflectivity inversion is non-unique; dry-air density sets the mixing-ratio baseline.\n'
            'Model transport, fallout, microphysics and convective precipitation jointly affect the result.\n'
            'The diagram does not establish the cause of a forecast difference or a closed mass budget.',
            fontsize=10.5, ha='left', va='center', linespacing=1.5)
    fig.subplots_adjust(left=.02, right=.98, top=.98, bottom=.02)
    return fig


def skill(data):
    fig, ax = plt.subplots(figsize=(12, 7.5))
    ax.axis('off')
    ax.text(.5, .97, 'Location agreement for 1-h precipitation ≥ 5 mm', ha='center', va='top',
            fontsize=17, weight='bold', transform=ax.transAxes)
    ax.text(.5, .88, 'H = hit: both ≥ 5 mm     M = miss: analysis only     F = false alarm: forecast only',
            ha='center', fontsize=12, transform=ax.transAxes)
    ax.text(.5, .81, r'$CSI = H/(H+M+F)$', ha='center', fontsize=16, transform=ax.transAxes)
    table_data = [[case, *(str(v) for v in data[1, case][:3]), f'{data[1, case][3]:.4f}',
                   f'{data[6, case][3]:.4f}'] for case in CASES]
    table = ax.table(cellText=table_data,
                     colLabels=['Experiment', '+1 h H', '+1 h M', '+1 h F', '+1 h CSI', '+6 h CSI'],
                     cellLoc='center', colLoc='center', bbox=[.04, .37, .92, .36],
                     colWidths=[.30, .14, .14, .14, .14, .14])
    table.auto_set_font_size(False); table.set_fontsize(12)
    for (row, _), cell in table.get_celld().items():
        cell.set_edgecolor('#c4d0d5')
        if row == 0:
            cell.set_facecolor('#dcebf2'); cell.set_text_props(weight='bold')
        elif row % 2 == 0:
            cell.set_facecolor('#f4f7f8')
    ax.text(.05, .28, 'Detection and false-alarm tradeoff:', weight='bold', fontsize=12, transform=ax.transAxes)
    ax.text(.05, .21, 'CURRENT_HYDRO / CURRENT_LIQUID: H = 55 / 55; F = 103 / 99 at +1 h.',
            fontsize=11.5, transform=ax.transAxes)
    ax.text(.05, .14, '+1 h: ORIGINAL has the highest CSI; +6 h: CURRENT_LIQUID has the highest CSI here.',
            fontsize=11.5, transform=ax.transAxes)
    ax.text(.05, .07, '3,688 paired points; RN1 is a processed analysis. Results depend on lead, threshold and baseline.',
            fontsize=10.5, transform=ax.transAxes)
    fig.subplots_adjust(left=.02, right=.98, top=.98, bottom=.02)
    return fig


def render(csv_path, output):
    if output.exists() or output.is_symlink():
        raise FileExistsError(output)
    script = Path(__file__).resolve()
    before = {'score_sha256': digest(csv_path), 'script_sha256': digest(script)}
    data = scores(csv_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix='.precip-concepts-', dir=output.parent))
    try:
        plt.rcParams['svg.hashsalt'] = 'precipitation-concepts-20261030'
        for name, fig in (('precipitation_physics_flow', physics()), ('threshold_skill_comparison', skill(data))):
            for extension in ('png', 'pdf', 'svg'):
                metadata = {'CreationDate': None, 'ModDate': None} if extension == 'pdf' else ({'Date': None} if extension == 'svg' else None)
                fig.savefig(temp / f'{name}.{extension}', dpi=220, bbox_inches='tight', metadata=metadata)
            plt.close(fig)
        after = {'score_sha256': digest(csv_path), 'script_sha256': digest(script)}
        if before != after:
            raise ValueError('score input or script changed during rendering')
        manifest = {'score_source': 'docs/evidence/current_forecast_paper_20261029/scores/categorical_scores.csv',
                    'score_hash_receipt': 'docs/evidence/current_forecast_paper_20261029/validation/independent_scores.json',
                    'script': 'tools/plot_precipitation_concept_diagrams.py', 'sha256_before': before,
                    'sha256_after': after, 'outputs': {p.name: digest(p) for p in sorted(temp.iterdir())}}
        (temp / 'figure_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.renameat2(-100, os.fsencode(temp), -100, os.fsencode(output), 1):
            err = ctypes.get_errno(); raise OSError(err, os.strerror(err), str(output))
    finally:
        if temp.exists():
            shutil.rmtree(temp)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scores', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    render(args.scores, args.output_dir)


if __name__ == '__main__':
    main()
