#!/usr/bin/env python3
"""Render paired hourly forecast metrics from score_forecasts.py output."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, ListedColormap
import numpy as np

ARMS = ('ORIGINAL', 'CURRENT_OFF', 'CURRENT_HYDRO', 'CURRENT_LIQUID')
LABELS = ('Original', 'Current OFF', 'Current HYDRO', 'Current LIQUID')
COLORS = ('#333333', '#0072B2', '#D55E00', '#009E73')
MARKERS = ('o', 's', '^', 'D')
THRESHOLDS = (0.1, 0.5, 1., 2.5, 5., 10.)
LEADS = np.arange(1, 7)


def read_rows(path):
    with path.open(encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream))


def metric_values(rows, arm, field, threshold=None):
    selected = [r for r in rows if r['case'] == arm and
                (threshold is None or float(r['threshold_mm']) == threshold)]
    by_lead = {int(r['lead_hour']): r for r in selected}
    if len(selected) != 6 or set(by_lead) != set(LEADS):
        raise ValueError(f'missing or duplicate rows for {arm}, threshold={threshold}')
    return [float(by_lead[h][field]) if by_lead[h][field] else np.nan for h in LEADS]


def save(fig, directory, name):
    for suffix in ('pdf', 'png'):
        fig.savefig(directory / f'{name}.{suffix}', dpi=220, bbox_inches='tight')
    plt.close(fig)


def categorical_figures(rows, directory):
    for metric in ('CSI', 'ETS'):
        fig, axes = plt.subplots(2, 3, figsize=(11.3, 6.4), sharex=True, sharey=True,
                                 layout='constrained')
        for ax, threshold in zip(axes.flat, THRESHOLDS):
            for arm, label, color, marker in zip(ARMS, LABELS, COLORS, MARKERS):
                ax.plot(LEADS, metric_values(rows, arm, metric, threshold), color=color,
                        marker=marker, markersize=4.2, linewidth=1.35, label=label,
                        linestyle='--' if arm == 'ORIGINAL' else '-')
            ax.set_title(f'≥ {threshold:g} mm per hour')
            ax.set_xticks(LEADS)
            ax.grid(alpha=.25)
            ax.set_xlabel('Forecast lead (h)')
            ax.set_ylabel(metric)
        handles, labels = axes.flat[0].get_legend_handles_labels()
        fig.legend(handles, labels, loc='outside upper center', ncol=4, frameon=False)
        save(fig, directory, f'hourly_{metric.lower()}')


def continuous_figure(rows, directory):
    fig, axes = plt.subplots(1, 3, figsize=(11.3, 3.5), layout='constrained')
    for ax, field, title in zip(axes, ('MAE_mm', 'RMSE_mm', 'mean_error_mm'),
                                ('Mean absolute error', 'Root mean square error', 'Mean error')):
        for arm, label, color, marker in zip(ARMS, LABELS, COLORS, MARKERS):
            ax.plot(LEADS, metric_values(rows, arm, field), color=color, marker=marker,
                    markersize=4.2, linewidth=1.35, label=label,
                    linestyle='--' if arm == 'ORIGINAL' else '-')
        if field == 'mean_error_mm':
            ax.axhline(0, color='#888888', linewidth=.7)
        ax.set(title=title, xlabel='Forecast lead (h)', ylabel='mm per hour', xticks=LEADS)
        ax.grid(alpha=.25)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='outside upper center', ncol=4, frameon=False)
    save(fig, directory, 'hourly_continuous')


def transition_figure(rows, directory):
    fig, axes = plt.subplots(2, 3, figsize=(11.3, 6.2), sharex=True, layout='constrained')
    for col, (arm, label) in enumerate(zip(ARMS[1:], LABELS[1:])):
        selected = [r for r in rows if r['baseline'] == 'ORIGINAL' and r['candidate'] == arm
                    and float(r['threshold_mm']) == 5.0]
        by_lead = {int(r['lead_hour']): r for r in selected}
        if len(selected) != 6 or set(by_lead) != set(LEADS):
            raise ValueError(f'missing or duplicate transitions for {arm}')
        for row, (gain, loss, title) in enumerate((('hit_gains', 'hit_losses', 'Hit'),
                                                   ('false_alarm_gains', 'false_alarm_losses', 'False alarm'))):
            ax = axes[row, col]
            ax.bar(LEADS - .18, [int(by_lead[h][gain]) for h in LEADS], width=.36,
                   color='#0072B2', label='Gained from original')
            ax.bar(LEADS + .18, [-int(by_lead[h][loss]) for h in LEADS], width=.36,
                   color='#D55E00', label='Lost from original')
            ax.axhline(0, color='#777777', linewidth=.6)
            ax.set(title=f'{label}: {title.lower()} changes', xlabel='Forecast lead (h)',
                   ylabel='Paired grid points', xticks=LEADS)
            ax.grid(axis='y', alpha=.25)
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='outside upper center', ncol=2, frameon=False,
               title='≥ 5 mm per hour: gains above zero; losses below zero')
    save(fig, directory, 'hourly_transitions_ge5')


def digest(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return {'path': str(path.resolve()), 'sha256': digest.hexdigest(), 'size': path.stat().st_size}


def read_points(path):
    required = ('reference', 'latitude', 'longitude', 'flat_index_yx', *ARMS)
    with np.load(path, allow_pickle=False) as data:
        if not set(required).issubset(data.files):
            raise ValueError(f'{path}: missing required point arrays')
        result = {name: np.asarray(data[name]) for name in required}
    if any(array.shape != (3688,) for array in result.values()):
        raise ValueError(f'{path}: expected 3688 values per point array')
    if any(not np.isfinite(array).all() for array in result.values()):
        raise ValueError(f'{path}: non-finite point data')
    indices = result['flat_index_yx']
    if not np.issubdtype(indices.dtype, np.integer) or np.unique(indices).size != 3688:
        raise ValueError(f'{path}: indices must be unique integers')
    if any((result[name] < 0).any() for name in ('reference', *ARMS)):
        raise ValueError(f'{path}: negative precipitation')
    return result


def spatial_figure(points, hour, directory, extent):
    bounds = [0, .1, .5, 1, 2.5, 5, 10, 20, 50]
    cmap = ListedColormap(['#f2f2f2', '#bfe8fc', '#7bc8ea', '#3f98d0',
                           '#48b474', '#f0d44c', '#ef8b39', '#c83232'])
    cmap.set_over('#6e237e')
    norm = BoundaryNorm(bounds, cmap.N)
    fig, axes = plt.subplots(1, 5, figsize=(13, 4.1), sharex=True, sharey=True,
                             layout='constrained')
    lat, lon = points['latitude'], points['longitude']
    for ax, field, label in zip(axes, ('reference', *ARMS), ('RN1 analysis', *LABELS)):
        scatter = ax.scatter(lon, lat, c=points[field], cmap=cmap, norm=norm, s=3.2,
                             marker='s', linewidths=0)
        ax.set_title(label)
        ax.set_xlim(extent[0], extent[1]); ax.set_ylim(extent[2], extent[3])
        ax.set_aspect(1.0 / np.cos(np.deg2rad(np.mean(lat))))
        ax.set_xlabel('Longitude (°E)')
    axes[0].set_ylabel('Latitude (°N)')
    colorbar = fig.colorbar(scatter, ax=axes, orientation='horizontal', fraction=.07,
                            pad=.13, ticks=bounds, extend='max')
    colorbar.set_label('Hourly precipitation (mm per hour)')
    fig.suptitle(f'Lead +{hour - 12} h · {hour - 1:02d}:00–{hour:02d}:00 UTC · '
                 '3,688 paired points (RN1 is an analysis)', fontsize=11)
    save(fig, directory, f'hour_{hour:02d}_paired_precipitation')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scores-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists() or args.output_dir.is_symlink():
        raise ValueError(f'output directory already exists: {args.output_dir}')
    inputs = [args.scores_dir / name for name in ('categorical_scores.csv', 'continuous_scores.csv',
              'transitions.csv', 'hour_13_arrays.npz', 'hour_18_arrays.npz')]
    plotter = Path(__file__).resolve()
    records = [digest(path) for path in [plotter, *inputs]]
    categorical = read_rows(inputs[0])
    continuous = read_rows(inputs[1])
    transitions = read_rows(inputs[2])
    points = {hour: read_points(path) for hour, path in zip((13, 18), inputs[3:])}
    for name in ('flat_index_yx', 'latitude', 'longitude'):
        if not np.array_equal(points[13][name], points[18][name]):
            raise ValueError(f'first and last hour {name} differ')
    lat, lon = points[13]['latitude'], points[13]['longitude']
    extent = (float(lon.min() - .1), float(lon.max() + .1),
              float(lat.min() - .1), float(lat.max() + .1))
    args.output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.forecast-figures-', dir=args.output_dir.parent))
    try:
        categorical_figures(categorical, temporary)
        continuous_figure(continuous, temporary)
        transition_figure(transitions, temporary)
        for hour, data in points.items():
            spatial_figure(data, hour, temporary, extent)
        if [digest(path) for path in [plotter, *inputs]] != records:
            raise ValueError('plot inputs or plotting script changed during figure generation')
        outputs = [digest(path) for path in sorted(temporary.iterdir())]
        for item in outputs:
            item['path'] = Path(item['path']).name
        manifest = {'scope': 'Paired 3688-point comparison; RN1 is a processed analysis, not independent truth.',
                    'inputs': records, 'outputs': outputs, 'spatial_hours_utc': [13, 18],
                    'spatial_color_boundaries_mm_per_hour': [0, .1, .5, 1, 2.5, 5, 10, 20, 50]}
        (temporary / 'figure_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        if args.output_dir.exists() or args.output_dir.is_symlink():
            raise ValueError(f'output directory already exists: {args.output_dir}')
        os.rename(temporary, args.output_dir)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


if __name__ == '__main__':
    main()
