#!/usr/bin/env python3
"""Plot measured frozen-ice probe stages at the selected B1 target levels."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROLES = (
    ('interior_half_boundary', 'Interior\n(half)'),
    ('closest_below_boundary', 'Below\nboundary'),
    ('closest_above_boundary', 'Above\nboundary'),
    ('first_infeasible_lexicographic', 'First\ninfeasible'),
    ('maximum_ice_water_content', 'Maximum\nIWC'),
)
VARIANTS = (
    ('QNICE', 'File QNICE', '#0072B2'),
    ('NI_nominal_maximum_mass_kg-1', 'Nominal maximum mass', '#D55E00'),
    ('NI_fixed_50um_kg-1', 'Fixed 50 µm', '#009E73'),
)


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def target_rows(profiles, metadata, values):
    if len(metadata) != len(values) or values.ndim != 2 or values.shape[1] != 6:
        raise ValueError('probe records and metadata must match with six output columns')
    index = {}
    for meta, row in zip(metadata, values):
        for role in meta['case']:
            key = (role, int(meta['k']), meta['variant'])
            if key in index:
                raise ValueError(f'duplicate probe record {key}')
            index[key] = row
    result = []
    for role, label in ROLES:
        matches = [case for case in profiles['cases'] if role in case['roles']]
        if len(matches) != 1:
            raise ValueError(f'expected one selected point for {role}')
        case = matches[0]
        level = case['selected_zyx'][0] + 1
        for variant, seed_label, _ in VARIANTS:
            row = index[(role, level, variant)]
            expected_den = case['profiles']['den'][level - 1]
            expected_qi = case['profiles']['QICE'][level - 1]
            expected_seed = case['profiles'][variant][level - 1]
            if not (np.isclose(row[0], expected_den, rtol=1e-6, atol=0) and
                    np.isclose(row[1], expected_qi, rtol=1e-6, atol=0) and
                    np.isclose(row[2], expected_seed, rtol=1e-6, atol=0)):
                raise ValueError(f'profile and probe disagree for {role}, {variant}')
            if not np.all(np.isfinite(row)) or row[4] <= 0:
                raise ValueError('invalid measured output')
            result.append(dict(role=role, category=label.replace('\n', ' '),
                               target_k_fortran=level, variant=variant, seed=seed_label,
                               density_kg_m3=row[0], qi_kg_kg=row[1], seed_ni_kg_1=row[2],
                               entry_ni_m3=row[3], first_inverse_lambda_m=row[4],
                               first_lambda_m_1=1.0 / row[4], psd1_ni_m3=row[5]))
    return result


def write_figure(rows, cap, output):
    fig, (ax, slope) = plt.subplots(2, 1, figsize=(10.2, 8.1), sharex=True,
                                    gridspec_kw={'height_ratios': [1.15, 1]})
    x = np.arange(len(ROLES))
    for offset, (variant, seed, color) in zip((-0.22, 0, 0.22), VARIANTS):
        subset = [row for row in rows if row['variant'] == variant]
        xs = x + offset
        entry = np.array([row['entry_ni_m3'] for row in subset]) / 1e6
        psd = np.array([row['psd1_ni_m3'] for row in subset]) / 1e6
        for xi, a, b in zip(xs, entry, psd):
            ax.plot([xi, xi], [a, b], color=color, linewidth=1.3, alpha=0.65, zorder=1)
        ax.scatter(xs, entry, marker='o', s=95, facecolors='white', edgecolors=color,
                   linewidths=1.5, zorder=3)
        ax.scatter(xs, psd, marker='s', s=30, color=color, zorder=4)
        slope.scatter(xs, [row['first_lambda_m_1'] / 1e4 for row in subset],
                      s=46, color=color, label=seed, zorder=3)
    ax.axhline(cap / 1e6, color='0.25', linewidth=1, linestyle='--', label='Entry cap')
    ax.scatter([], [], marker='o', facecolors='white', edgecolors='0.2', label='Post-entry clamp')
    ax.scatter([], [], marker='s', color='0.2', label='Post-PSD1')
    ax.set_ylabel('Ice number ($10^6$ m$^{-3}$)')
    ax.set_title('Frozen ice operators: selected B1 file-state levels', loc='left', weight='bold')
    ax.legend(loc='upper left', frameon=False, ncol=3, fontsize=9)
    ax.set_ylim(bottom=-0.08)
    slope.set_ylabel('First slope $1/r_{slope}$\n($10^4$ m$^{-1}$)')
    slope.set_xticks(x, [label for _, label in ROLES])
    slope.legend(title='Input number seed', frameon=False, ncol=3, loc='upper right', fontsize=9)
    for axis in (ax, slope):
        axis.grid(axis='y', color='0.87', linewidth=0.8)
        axis.set_axisbelow(True)
        axis.spines[['top', 'right']].set_visible(False)
    fig.text(0.09, 0.012, 'Frozen QI operator composition; source file-state density proxy. '
             'Not a full microphysics routine or forecast.\n'
             'Connecting lines show post-entry to post-PSD1 number; lower panel is reciprocal of the measured first-slope inverse lambda.',
             fontsize=8.5, ha='left', va='bottom')
    fig.tight_layout(rect=(0, 0.065, 1, 1))
    fig.savefig(output, dpi=180, metadata={'Software': 'Matplotlib'})
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('profiles', type=Path)
    parser.add_argument('metadata', type=Path)
    parser.add_argument('probe_output', type=Path)
    parser.add_argument('output_dir', type=Path)
    args = parser.parse_args()
    profiles = json.loads(args.profiles.read_text())
    metadata = json.loads(args.metadata.read_text())
    values = np.loadtxt(args.probe_output, ndmin=2)
    rows = target_rows(profiles, metadata, values)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = args.output_dir / 'target_levels.csv'
    with csv_path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    image_path = args.output_dir / 'ice_stage_contract.png'
    write_figure(rows, profiles['selection']['nominal_ice_cap_m-3'], image_path)
    provenance = {'profiles_sha256': sha(args.profiles), 'metadata_sha256': sha(args.metadata),
                  'probe_output_sha256': sha(args.probe_output), 'plotter_sha256': sha(Path(__file__)),
                  'csv_sha256': sha(csv_path), 'png_sha256': sha(image_path),
                  'scope': 'Frozen-QI operator composition; not a full microphysics routine or forecast.'}
    (args.output_dir / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')

if __name__ == '__main__':
    main()
