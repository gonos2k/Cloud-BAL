#!/usr/bin/env python3
"""Plot the measured full-column trace at the maximum-IWC B1 level."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROLE = 'maximum_ice_water_content'
STAGES = ('ENTRY', 'SLOPE', 'PSD1_PRE', 'PSD1_POST', 'PSD2_POST', 'PSD3_PRE', 'FINAL')
VARIANTS = (
    ('QNICE', 'File QNICE', '#0072B2', 'o'),
    ('NI_nominal_maximum_mass_kg-1', 'Nominal maximum mass', '#D55E00', 's'),
    ('NI_fixed_50um_kg-1', 'Fixed 50 µm', '#009E73', '^'),
)


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def selected_rows(csv_path, profiles):
    matches = [c for c in profiles['cases'] if ROLE in c['roles']]
    if len(matches) != 1:
        raise ValueError('expected one maximum-IWC case')
    level = matches[0]['selected_zyx'][0] + 1
    with csv_path.open(newline='') as stream:
        rows = [r for r in csv.DictReader(stream)
                if r['optimization'] == 'O0' and r['role'] == ROLE and int(r['k']) == level]
    index = {}
    for row in rows:
        key = (row['variant'], row['stage'])
        if key in index:
            raise ValueError(f'duplicate target stage: {key}')
        for field in ('ni', 'qi', 'den'):
            if not np.isfinite(float(row[field])):
                raise ValueError('non-finite stage value')
        index[key] = row
    for variant, _, _, _ in VARIANTS:
        for stage in ('WRAPPER', *STAGES):
            if (variant, stage) not in index:
                raise ValueError(f'missing stage {stage} for {variant}')
    return rows, index, level


def draw(index, level, cap, path):
    fig, (number, mass) = plt.subplots(2, 1, figsize=(10.8, 7.8), sharex=True)
    x = np.arange(len(STAGES))
    wrappers = []
    for offset, (variant, label, color, marker) in zip((-0.09, 0.0, 0.09), VARIANTS):
        series = [index[(variant, stage)] for stage in STAGES]
        number.plot(x + offset, [float(row['ni']) / 1e6 for row in series],
                    color=color, marker=marker, linewidth=1.4, markersize=6, label=label)
        mass.plot(x + offset, [float(row['qi']) * 1000 for row in series],
                  color=color, marker=marker, linewidth=1.4, markersize=6)
        wrappers.append(f"{label}: {float(index[(variant, 'WRAPPER')]['ni']) / 1e6:.3f}")
    number.axhline(cap / 1e6, linestyle='--', color='0.25', linewidth=1, label='Entry cap')
    number.set_ylim(top=max(float(index[(variant, stage)]['ni']) / 1e6
                            for variant, _, _, _ in VARIANTS for stage in STAGES) * 1.23)
    number.set_ylabel('Ice number ($10^6$ m$^{-3}$)')
    number.set_title(f'Full-column stage trace: maximum IWC, level {level}', loc='left', weight='bold')
    number.legend(ncol=4, loc='upper center', frameon=False, fontsize=9)
    mass.set_ylabel('Ice mixing ratio (g kg$^{-1}$)')
    mass.set_xticks(x, ['Entry', 'First\nslope', 'PSD1\npre', 'PSD1\npost',
                        'PSD2\npost', 'PSD3\npre', 'Final'])
    for ax in (number, mass):
        ax.set_ylim(bottom=-0.05 if ax is number else -0.4)
        ax.grid(axis='y', color='0.87', linewidth=0.8)
        ax.set_axisbelow(True)
        ax.spines[['top', 'right']].set_visible(False)
    fig.text(0.09, 0.012,
             'Incoming wrapper NI ($10^6$ m$^{-3}$): ' + '; '.join(wrappers) + '.\n'
             'Instrumented and unmodified column terminal outputs agree byte-for-byte; this is not a captured WRF first-use state.\n'
             'Stage intervals contain intervening processes; this trace does not attribute changes to an individual process.',
             fontsize=8.5, ha='left', va='bottom')
    fig.tight_layout(rect=(0, 0.09, 1, 1))
    fig.savefig(path, dpi=180, metadata={'Software': 'Matplotlib'})
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stages', type=Path)
    parser.add_argument('profiles', type=Path)
    parser.add_argument('output_dir', type=Path)
    args = parser.parse_args()
    profiles = json.loads(args.profiles.read_text())
    rows, index, level = selected_rows(args.stages, profiles)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = args.output_dir / 'full_column_target_stages.csv'
    with csv_path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    png_path = args.output_dir / 'full_column_trace.png'
    draw(index, level, profiles['selection']['nominal_ice_cap_m-3'], png_path)
    provenance = {'target_stages_sha256': sha(args.stages), 'profiles_sha256': sha(args.profiles),
                  'plotter_sha256': sha(Path(__file__)), 'csv_sha256': sha(csv_path),
                  'png_sha256': sha(png_path), 'optimization': 'O0', 'target_k_fortran': level,
                  'scope': 'Instrumented full-column experiment; not captured WRF first-use.'}
    (args.output_dir / 'full_column_trace_provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')

if __name__ == '__main__':
    main()
