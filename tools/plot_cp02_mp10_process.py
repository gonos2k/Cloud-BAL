#!/usr/bin/env python3
"""Plot the frozen MP10 diagnostic cohorts and paired surface components."""
import argparse
import csv
import json
import os
from pathlib import Path
import shutil
import tempfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.ticker import MaxNLocator
import numpy as np

import cp02_mp10_failure_cohorts as cohorts

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / 'docs/evidence/cp02_mp10_process_20261110'
COHORT = BUNDLE / 'cohorts'
SURFACE = BUNDLE / 'surface/results'
E = cohorts.prior
POINTS_SHA = 'f36d193647d04a4eb811318431dd15f0b92d0644d9815b35a3650d70b073888d'
CASES = ('ORIGINAL', 'IMPROVED_BG_FIXED', 'CONSERVATIVE_SEDIMENTATION', 'FIRST_ICE_VELOCITY', 'MP10')
LABELS = ('규준실험', 'B1', 'PR153', 'PR154', 'MP10')
FONT = Path('/usr/share/fonts/truetype/nanum/NanumGothic.ttf')
FONT_SHA = '48a28e97b34fc8e5b157657633670cd1b7de126cfc414da65ce9c3d5bc8be733'
COLORS = ('#666666', '#2b6cb0', '#cd8a13', '#a83b53', '#198364')


def read_csv(path):
    with path.open(newline='') as stream:
        return list(csv.DictReader(stream))


def sealed(folder, names):
    receipt_path = folder / 'receipt.json'
    receipt = json.loads(receipt_path.read_text())
    if receipt.get('status') != 'COMPLETE':
        raise ValueError('incomplete input receipt')
    records = [E.identity(receipt_path)]
    for name in names:
        record = E.identity(folder / name)
        if record['sha256'] != receipt['outputs'][name]:
            raise ValueError(f'input hash mismatch: {name}')
        records.append(record)
    return records


def save(fig, path):
    fig.savefig(path, dpi=150, metadata={'Software': 'Cloud-BAL MP10 diagnostic'})
    plt.close(fig)


def transitions_map(points, rows, arrays, out):
    fig, (ax, mp) = plt.subplots(1, 2, figsize=(13, 5.4), constrained_layout=True,
                                 gridspec_kw={'width_ratios': [1.2, 1]})
    definitions = ((6, 5., 'h6 ≥5 mm'), (3, .1, 'h3 ≥0.1 mm'), (6, .5, 'h6 ≥0.5 mm'))
    keys = ('fa_new', 'fa_resolved', 'hit_lost', 'hit_gained')
    names = ('New false alarm', 'Resolved false alarm', 'Lost hit', 'Gained hit')
    colors = ('#b6383c', '#36856f', '#d49322', '#4678ac')
    x = np.arange(len(definitions))
    for k, label, color, offset in zip(keys, names, colors, (-.3, -.1, .1, .3)):
        values = [int(next(r[k] for r in rows if int(r['lead_hour']) == lead and
                           float(r['threshold_mm']) == threshold and r['baseline'] == 'FIRST_ICE_VELOCITY'))
                  for lead, threshold, _ in definitions]
        ax.bar(x + offset, values, width=.19, color=color, label=label)
        for xx, value in zip(x + offset, values):
            ax.text(xx, value + 1, str(value), ha='center', va='bottom', fontsize=8)
    ax.set(xticks=x, xticklabels=[d[2] for d in definitions], ylabel='Number of paired RN1 points',
           title='PR154 → MP10 transitions', ylim=(0, 80))
    ax.legend(fontsize=8, ncol=2, loc='upper right')
    h = arrays[13]
    mp.scatter(h['longitude'], h['latitude'], s=2, color='#c6c6c6', label='Paired RN1 points')
    for marker, label, selected, color in (
        ('o', 'h6 B1 new FA', [r for r in points if r['cohort'].startswith('h6_B1_new')], '#b6383c'),
        ('s', 'h6 resolved controls', [r for r in points if r['cohort'].startswith('h6_154_resolved')], '#36856f'),
        ('^', 'h3/h6 transition points', [r for r in points if r['cohort'].startswith(('h3_', 'h6_0.5_'))], '#d49322'),
        ('D', 'Other selected points', [r for r in points if not r['cohort'].startswith(('h6_B1_new', 'h6_154_resolved', 'h3_', 'h6_0.5_'))], '#4c6b9b')):
        mp.scatter([float(r['longitude']) for r in selected], [float(r['latitude']) for r in selected],
                   marker=marker, s=37, color=color, edgecolor='white', linewidth=.4, label=label, zorder=3)
    mp.set(xlabel='Longitude (°E)', ylabel='Latitude (°N)', title='30 predetermined diagnostic points')
    mp.legend(fontsize=7.5, loc='best')
    fig.suptitle('Precipitation failure transitions and frozen sampling geometry', fontsize=13)
    save(fig, out / '01_transition_geometry.png')


def weak(rows, out):
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    fields = (('mae_mm', 'MAE (mm)'), ('rmse_mm', 'RMSE (mm)'),
              ('detected_ge_0.1', 'Forecast ≥0.1 mm (% of observed band)'),
              ('predicted_0.1_to_1', 'Forecast in [0.1, 1) mm (% of observed band)'))
    for case, label, color in zip(CASES, LABELS, COLORS):
        group = sorted((r for r in rows if r['case'] == case and r['observation_band'] == '[0.1,1)'),
                       key=lambda r: int(r['lead_hour']))
        if len(group) != 6 or any(int(r['count']) <= 0 for r in group):
            raise ValueError('weak observation denominator missing')
        for ax, (field, ylabel) in zip(axes.flat, fields):
            values = [float(r[field]) * (100 / int(r['count']) if field.startswith(('detected', 'predicted')) else 1)
                      for r in group]
            ax.plot(range(1, 7), values, marker='o', ms=3.5, lw=1.6, color=color, label=label)
            ax.set(xlabel='Lead hour', ylabel=ylabel, xticks=range(1, 7))
            ax.grid(alpha=.2)
    axes[0, 0].legend(ncol=3, fontsize=8)
    counts = [next(r['count'] for r in rows if r['case'] == 'MP10' and r['observation_band'] == '[0.1,1)' and int(r['lead_hour']) == h) for h in range(1, 7)]
    fig.suptitle('Conditional errors and detection: observed 0.1 ≤ RN1 < 1 mm\n'
                 + 'Paired observations by lead: ' + ', '.join(counts), fontsize=12)
    save(fig, out / '02_weak_conditional.png')


def surface_contrasts(rows, out):
    selected = [(1, 9774, 'h1 lost hit 9774'), (1, 9624, 'h1 retained 9624'),
                (3, 12300, 'h3 lost hit 12300 (obs 1.4 mm)'), (3, 12301, 'h3 retained 12301'),
                (6, 18110, 'h6 dry FA 18110'), (6, 9751, 'h6 dry FA ≥10: 9751'),
                (6, 18710, 'h6 weak FA 18710'), (6, 12893, 'h6 weak FA ≥10: 12893'),
                (6, 12010, 'h6 mid FA 12010'), (6, 12446, 'h6 mid FA ≥10: 12446'),
                (6, 12892, 'h6 PR154 new FA 12892')]
    lookup = {(int(r['lead_hour']), int(r['flat_index_yx']), r['case']): r for r in rows}
    values = []
    for lead, point, _ in selected:
        old, new = lookup[lead, point, 'FIRST_ICE_VELOCITY'], lookup[lead, point, 'MP10']
        values.append([float(new[k]) - float(old[k]) for k in ('rainc_mm', 'rainnc_mm')])
    values = np.array(values)
    fig, axes = plt.subplots(1, 2, figsize=(13, 6.2), sharey=True, constrained_layout=True,
                             gridspec_kw={'width_ratios': [1, 1.3]})
    y = np.arange(len(selected))
    for ax, index, title, color in zip(axes, (0, 1), ('RAINC', 'RAINNC'), ('#ad7041', '#287d9a')):
        ax.barh(y, values[:, index], color=color)
        ax.axvline(0, color='black', lw=.8)
        ax.set(xlabel='MP10 - PR154 hourly component (mm)', title=title)
        ax.grid(axis='x', alpha=.2)
        ax.xaxis.set_major_locator(MaxNLocator(4))
        for pos, value in zip(y, values[:, index]):
            ax.annotate(f'{value:+.3g}', (value, pos), xytext=(4 if value >= 0 else -4, 0),
                        textcoords='offset points', ha='left' if value >= 0 else 'right', va='center', fontsize=7)
        ax.margins(x=.23)
    axes[0].set_yticks(y, [r[2] for r in selected]); axes[0].invert_yaxis()
    fig.suptitle('Paired surface output components at selected diagnostic points\n'
                 'Components describe hourly accumulations, not process causation', fontsize=12)
    save(fig, out / '03_surface_components.png')



# A common external call is 20 seconds. Each arm has already collapsed its
# own actual inner loops before these arrays were bilinearly weighted.
TARGETS = ((1, 9774, 'h1 9774 lost hit'), (3, 12300, 'h3 12300 lost hit, obs 1.4 mm'),
           (6, 12892, 'h6 12892 PR154 new FA'), (6, 12446, 'h6 12446 B1 new FA ≥10 mm'))
TARGET_COLORS = ('#375c9a', '#b35d37', '#28816f', '#aa4084')


def native_data(folder):
    data = {}
    for hour in (1, 3, 6):
        for arm in ('CONTROL', 'MP10', 'paired'):
            with np.load(folder / f'{arm}_h{hour:02d}.npz', allow_pickle=False) as z:
                names = ('psd_number_column', 'entry') if arm == 'paired' else ('zero_removed_column',)
                values = {name: z[name] for name in names}
                selected = {}
                for h, point, _ in TARGETS:
                    if h != hour:
                        continue
                    match = np.flatnonzero(z['point'] == point)
                    if len(match) != 1 or not np.array_equal(z['k'], np.arange(1, 40)):
                        raise ValueError('native point or levels differ')
                    p = match[0]
                    if len(z['step']) != 180 or np.any(np.diff(z['step']) != 1):
                        raise ValueError('external call sequence differs')
                    selected[point] = {name: value[:, p].copy() for name, value in values.items()}
                data[hour, arm] = {'step': z['step'].copy(), 'points': selected,
                                   'source_fields': z['source_fields'].tolist(),
                                   'number_fields': z['psd_number_fields'].tolist()}
    return data


def write_csv(path, rows):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def native_plots(folder, out):
    data = native_data(folder)
    times = np.arange(1, 181) / 3
    zero_rows, number_rows, field_rows = [], [], []
    fig, axes = plt.subplots(2, 2, figsize=(11, 7.5), constrained_layout=True)
    for ax, (hour, point, label) in zip(axes.flat, TARGETS):
        for arm, color, name in (('CONTROL', '#a83b53', 'PR154'), ('MP10', '#198364', 'MP10')):
            record = data[hour, arm]
            values = record['points'][point]['zero_removed_column']
            if not np.isfinite(values).all():
                raise ValueError('cleanup removal has missing values')
            cumulative = np.cumsum(values, dtype=np.float64)
            ax.plot(times, cumulative, color=color, label=name)
            zero_rows.extend({'hour': hour, 'point': point, 'arm': arm, 'step': int(step),
                              'minutes_into_hour': float(t), 'removed_kg_m2': float(value),
                              'cumulative_removed_kg_m2': float(total)}
                             for step, t, value, total in zip(record['step'], times, values, cumulative))
        ax.set(title=label, xlabel='Minutes into selected lead hour', ylabel='Cumulative removal (kg m⁻²)')
        ax.grid(alpha=.2)
    axes[0, 0].legend()
    fig.suptitle('Inner-loop zeroing: selected-column removal\nSource density × layer thickness; not a domain budget', fontsize=12)
    save(fig, out / '04_cleanup_removal.png')
    write_csv(out / '04_cleanup_values.csv', zero_rows)

    fields = ('NC_volume', 'NI_volume', 'NN_volume', 'NR_volume')
    fig, axes = plt.subplots(2, 2, figsize=(11, 7.5), constrained_layout=True)
    for target, color in zip(TARGETS, TARGET_COLORS):
        hour, point, label = target
        record = data[hour, 'paired']
        values = record['points'][point]['psd_number_column']
        if record['number_fields'] != list(fields) or values.shape != (180, 4) or not np.isfinite(values).all():
            raise ValueError('PSD number field coverage differs')
        sums = np.cumsum(values, axis=0, dtype=np.float64)
        for i, ax in enumerate(axes.flat):
            ax.plot(times, sums[:, i], color=color, label=label)
            ax.axhline(0, color='black', lw=.6)
            ax.grid(alpha=.2)
            ax.set(title=fields[i], xlabel='Minutes into selected lead hour',
                   ylabel='Cumulative difference (number m⁻²)')
        for step, t, row, total in zip(record['step'], times, values, sums):
            number_rows.append({'hour': hour, 'point': point, 'step': int(step), 'minutes_into_hour': float(t),
                                **{f'{name}_delta_number_m2': float(row[i]) for i, name in enumerate(fields)},
                                **{f'{name}_cumulative_delta_number_m2': float(total[i]) for i, name in enumerate(fields)}})
    axes[0, 0].legend(fontsize=7)
    fig.suptitle('PSD number adjustment: MP10 - PR154\nInternal number per volume × layer thickness; signed selected-column sum', fontsize=12)
    save(fig, out / '05_psd_number_adjustment.png')
    write_csv(out / '05_psd_values.csv', number_rows)

    state_fields = ('QR', 'QG', 'TK')
    units = ('kg kg⁻¹', 'kg kg⁻¹', 'K')
    matrices = []
    for hour, point, label in TARGETS:
        record = data[hour, 'paired']
        entry = record['points'][point]['entry']
        indices = [record['source_fields'].index(field) for field in state_fields]
        if entry.shape != (180, 39, 11):
            raise ValueError('paired entry shape differs')
        matrices.append([entry[:, :, i].T for i in indices])
        for step_index, step in enumerate(record['step']):
            for k in range(39):
                field_rows.append({'hour': hour, 'point': point, 'step': int(step), 'k': k + 1,
                                   **{field: float(entry[step_index, k, i])
                                      for field, i in zip(state_fields, indices)}})
    fig, axes = plt.subplots(4, 3, figsize=(13, 10), constrained_layout=True)
    for column, (field, unit) in enumerate(zip(state_fields, units)):
        finite = np.concatenate([m[column][np.isfinite(m[column])] for m in matrices])
        scale = float(np.max(np.abs(finite))) if len(finite) else 0.
        for row, ((hour, point, label), ax) in enumerate(zip(TARGETS, axes[:, column])):
            values = matrices[row][column]
            if not np.isfinite(values).any():
                ax.text(.5, .5, 'No observed values', transform=ax.transAxes, ha='center')
            elif scale == 0:
                ax.text(.5, .5, 'Observed difference is zero', transform=ax.transAxes, ha='center')
            else:
                image = ax.imshow(values, origin='lower', aspect='auto', extent=(0, 60, .5, 39.5),
                                  interpolation='nearest', cmap='RdBu_r', vmin=-scale, vmax=scale)
                fig.colorbar(image, ax=ax, label=unit, shrink=.9)
            ax.set(xlabel='Minutes into selected lead hour', ylabel='Native k (1–39)')
            ax.set_title(f'{label} • {field}', fontsize=9)
    fig.suptitle('Paired inner-entry state: MP10 - PR154\nNative differences formed before frozen bilinear weights', fontsize=12)
    save(fig, out / '06_state_contrasts.png')
    write_csv(out / '06_state_values.csv', field_rows)

    ledger = read_csv(folder / 'public_ledger.csv')
    fig, axes = plt.subplots(4, 2, figsize=(11, 11), constrained_layout=True)
    ledger_rows = []
    for row_index, (hour, point, label) in enumerate(TARGETS):
        for column, (field, unit) in enumerate((('QR', 'kg kg⁻¹'), ('TK', 'K'))):
            selected = sorted((r for r in ledger if int(r['hour']) == hour and int(r['point']) == point and r['field'] == field),
                              key=lambda r: int(r['k']))
            if len(selected) != 39 or [int(r['k']) for r in selected] != list(range(1, 40)):
                raise ValueError('public ledger coverage differs')
            ax = axes[row_index, column]
            for key, name, color in (('local_sum', 'Within calls', '#b6383c'),
                                     ('between_calls_sum', 'Between calls', '#2c7998'),
                                     ('difference_change', 'Net change', '#484848')):
                ax.plot([float(r[key]) for r in selected], range(1, 40), color=color, lw=1.3, label=name)
            ax.axvline(0, color='black', lw=.6); ax.grid(alpha=.2)
            ax.set(title=f'{label} • public {field}', xlabel=f'Change in paired difference ({unit})', ylabel='Native k (1–39)')
            ledger_rows.extend(selected)
    axes[0, 0].legend(fontsize=7)
    fig.suptitle('Public entry/return difference ledger over selected hour\nBetween-call changes include all external processing; no transport attribution', fontsize=12)
    save(fig, out / '07_public_ledger.png')
    write_csv(out / '07_public_ledger_values.csv', ledger_rows)


def write_gallery(stage, has_analysis):
    figures = [
        ('01_transition_geometry.png', 'Transition counts and selected-point geography', 'selected_points.csv, transitions.csv'),
        ('02_weak_conditional.png', 'Weak-observation errors and detection by lead', 'weak_conditional_errors.csv'),
        ('03_surface_components.png', 'Hourly RAINC and RAINNC contrasts', 'point_components.csv'),
    ]
    if has_analysis:
        figures += [
            ('04_cleanup_removal.png', 'Actual zeroing removal at selected columns', '04_cleanup_values.csv'),
            ('05_psd_number_adjustment.png', 'Signed internal PSD number changes', '05_psd_values.csv'),
            ('06_state_contrasts.png', 'Native-level QR, QG and temperature contrasts', '06_state_values.csv'),
            ('07_public_ledger.png', 'Public local and between-call differences', '07_public_ledger_values.csv'),
        ]
    lines = ['# MP10 diagnostic figure gallery', '',
             'The 30 diagnostic points and bilinear weights were fixed from the sealed prior evaluation. '
             'The fixed forecast admission result remains 22/26; B1 is retained.', '',
             '| Figure | View | Full plotted values |', '|---|---|---|']
    for name, title, csvs in figures:
        links = ', '.join(f'[{csv}]({csv})' for csv in csvs.split(', '))
        lines.append(f'| [{title}]({name}) | ![{title}]({name}) | {links} |')
    lines.extend(['', 'Observed weak rain means 0.1 ≤ RN1 < 1 mm. Point 12300 has observed '
                  '1.4 mm and is not in that weak band.', '',
                  'Native k is a model level index, not altitude. Selected-column values use frozen '
                  'bilinear weights; they are not a domain budget. Internal number per volume is '
                  'kept separate from public number mixing ratios.', '',
                  'RAINC/RAINNC are stored output components, and between-call changes include '
                  'all external processes; neither by itself identifies a physical cause.', ''])
    (stage / 'FIGURES.md').write_text('\n'.join(lines), encoding='utf-8')

def run(output, analysis=None):
    if os.path.lexists(output):
        raise FileExistsError(output)
    names = ('selected_points.csv', 'transitions.csv', 'weak_conditional_errors.csv')
    surface_names = ('point_components.csv',)
    records = sealed(COHORT, names) + sealed(SURFACE, surface_names)
    if E.identity(COHORT / 'selected_points.csv')['sha256'] != POINTS_SHA:
        raise ValueError('frozen points changed')
    analysis_names = [f'{arm}_h{hour:02d}.npz' for hour in (1, 3, 6) for arm in ('CONTROL', 'MP10', 'paired')] + ['public_ledger.csv']
    if analysis is not None:
        records += sealed(analysis, analysis_names)
    source = E.identity(__file__)
    font = E.identity(FONT)
    if font['sha256'] != FONT_SHA:
        raise ValueError('NanumGothic font differs from pinned identity')
    records.extend((source, font))
    results = ROOT / 'docs/evidence/cp02_pulse_path_20261110/evaluation/results'
    if E.identity(results / 'receipt.json')['sha256'] != cohorts.RECEIPT_SHA:
        raise ValueError('evaluation receipt changed')
    records.extend([E.identity(results / 'receipt.json')] +
                   [E.identity(results / f'hour_{h}_arrays.npz') for h in cohorts.e.HOURS])
    arrays = E.read_arrays(results)
    points = read_csv(COHORT / names[0]); transition_rows = read_csv(COHORT / names[1])
    weak_rows = read_csv(COHORT / names[2]); surface_rows = read_csv(SURFACE / surface_names[0])
    if len(points) != 30 or len(surface_rows) != 360:
        raise ValueError('input coverage mismatch')
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.mp10-figures-', dir=output.parent))
    try:
        font_manager.fontManager.addfont(str(FONT))
        family = font_manager.FontProperties(fname=str(FONT)).get_name()
        plt.rcParams.update({'font.family': family, 'axes.unicode_minus': False,
                             'font.size': 9, 'figure.facecolor': 'white', 'savefig.facecolor': 'white',
                             'axes.spines.top': False, 'axes.spines.right': False})
        transitions_map(points, transition_rows, arrays, stage)
        weak(weak_rows, stage)
        surface_contrasts(surface_rows, stage)
        if analysis is not None:
            native_plots(analysis, stage)
        for name in names:
            shutil.copyfile(COHORT / name, stage / name)
        shutil.copyfile(SURFACE / surface_names[0], stage / surface_names[0])
        write_gallery(stage, analysis is not None)
        for record in records:
            if E.identity(record['path']) != record:
                raise ValueError('plot input changed')
        receipt = {'status': 'COMPLETE', 'inputs': records, 'matplotlib': matplotlib.__version__,
                   'scope': '30 frozen points; conditional weak observations [0.1,1) mm; diagnostic only',
                   'outputs': {p.name: E.identity(p)['sha256'] for p in sorted(stage.iterdir())}}
        (stage / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
        E.publish_new(stage, output)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--analysis', type=Path, help='sealed paired native analysis directory')
    args = parser.parse_args()
    run(args.output, args.analysis)
