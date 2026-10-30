#!/usr/bin/env python3
"""Render archived paired 1-hour precipitation distributions for all six leads."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.colors import BoundaryNorm, ListedColormap
import numpy as np

ARMS = ('ORIGINAL', 'CURRENT_OFF', 'CURRENT_HYDRO', 'CURRENT_LIQUID')
HOURS = range(13, 19)
BOUNDS = (0, .1, .5, 1, 2.5, 5, 10, 20, 50)
# Archived independent_scores.json input_sha256, verified 2026-10-29.
EXPECTED = dict(zip(HOURS, (
    '0df6e55167373751a2a9e50f10325c6d6d1e02603f1225e448c8e766184da9e4',
    '1228ba4d4106c151c79bcf01fb2f3a609e91a81bce4833f611da6f726283bf49',
    '2495bb333cb7b5b47b6b494e9d7b9ac39d48e224228b1bad06960d448c283711',
    '18da1d6c0e061849477030911091cee2c32d4ff7543e3684b11a991260b4c8e4',
    '4bf01eb3aecf5e6c7f35188b8110d42ee34c50eb670230b44b77852dc851103b',
    '28d298166ce100d0135ee1ce1061372602fe964606768587350d998fa22486d2',
)))


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_points(path):
    fields = ('reference', 'latitude', 'longitude', 'flat_index_yx', *ARMS)
    with np.load(path, allow_pickle=False) as data:
        if not set(fields).issubset(data.files):
            raise ValueError(f'{path}: missing required arrays')
        points = {field: np.asarray(data[field]) for field in fields}
    if any(value.shape != (3688,) for value in points.values()):
        raise ValueError(f'{path}: expected 3688 points per array')
    if any(not np.isfinite(value).all() for value in points.values()):
        raise ValueError(f'{path}: non-finite values')
    index = points['flat_index_yx']
    if not np.issubdtype(index.dtype, np.integer) or (index < 0).any() or np.unique(index).size != 3688:
        raise ValueError(f'{path}: indices must be nonnegative unique integers')
    if any((points[field] < 0).any() for field in ('reference', *ARMS)):
        raise ValueError(f'{path}: negative precipitation')
    if (np.abs(points['latitude']) > 90).any() or (np.abs(points['longitude']) > 180).any():
        raise ValueError(f'{path}: invalid latitude or longitude')
    return points


def load_inputs(scores_dir):
    paths = {hour: scores_dir / f'hour_{hour:02d}_arrays.npz' for hour in HOURS}
    before = {hour: sha256(path) for hour, path in paths.items()}
    for hour in HOURS:
        if before[hour] != EXPECTED[hour]:
            raise ValueError(f'{paths[hour]}: SHA-256 differs from independent score receipt')
    points = {hour: read_points(path) for hour, path in paths.items()}
    for hour in HOURS:
        for field in ('flat_index_yx', 'latitude', 'longitude'):
            if not np.array_equal(points[13][field], points[hour][field]):
                raise ValueError(f'hour {hour}: {field} differs from hour 13')
    return paths, before, points


def figure(points, hour, extent):
    cmap = ListedColormap(['#f2f2f2', '#bfe8fc', '#7bc8ea', '#3f98d0',
                           '#48b474', '#f0d44c', '#ef8b39', '#c83232'])
    cmap.set_over('#6e237e')
    norm = BoundaryNorm(BOUNDS, cmap.N)
    fig, grid = plt.subplots(2, 3, figsize=(11.5, 9), sharex=True, sharey=True,
                             layout='constrained')
    axes = grid.ravel()
    axes[5].set_visible(False)
    lat, lon = points['latitude'], points['longitude']
    for ax, field, label in zip(axes[:5], ('reference', *ARMS), ('RN1 analysis', *ARMS)):
        scatter = ax.scatter(lon, lat, c=points[field], cmap=cmap, norm=norm, s=4,
                             marker='s', linewidths=0, rasterized=True)
        ax.set_title(label, fontsize=13)
        ax.set_xlim(extent[:2])
        ax.set_ylim(extent[2:])
        ax.set_aspect(1 / np.cos(np.deg2rad(np.mean(lat))))
        ax.set_xlabel('Longitude (°E)', fontsize=11)
    axes[0].set_ylabel('Latitude (°N)', fontsize=11)
    axes[3].set_ylabel('Latitude (°N)', fontsize=11)
    bar = fig.colorbar(scatter, ax=axes[:5], orientation='horizontal', fraction=.045,
                       pad=.06, ticks=BOUNDS, extend='max')
    bar.set_label('1-h accumulated precipitation (mm)', fontsize=12)
    fig.suptitle(f'2026-08-16 {hour:02d}:00 UTC · Lead +{hour - 12} h\n'
                 f'Accumulation {hour - 1:02d}:00–{hour:02d}:00 UTC · 3,688 paired points',
                 fontsize=14)
    return fig


def publish_no_replace(source, destination):
    # Linux renameat2 atomically refuses an existing destination, including symlinks.
    libc = ctypes.CDLL(None, use_errno=True)
    result = libc.renameat2(-100, os.fsencode(source), -100, os.fsencode(destination), 1)
    if result:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(destination))


def render(scores_dir, output_dir):
    if output_dir.exists() or output_dir.is_symlink():
        raise FileExistsError(f'output directory already exists: {output_dir}')
    script = Path(__file__).resolve()
    script_before = sha256(script)
    paths, before, points = load_inputs(scores_dir)
    lat, lon = points[13]['latitude'], points[13]['longitude']
    extent = (float(lon.min() - .1), float(lon.max() + .1),
              float(lat.min() - .1), float(lat.max() + .1))
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.hourly-precip-', dir=output_dir.parent))
    try:
        metadata = {'CreationDate': None, 'ModDate': None}
        with PdfPages(temporary / 'hourly_precipitation_all_leads.pdf', metadata=metadata) as combined:
            for hour in HOURS:
                fig = figure(points[hour], hour, extent)
                name = f'hour_{hour:02d}_paired_precipitation'
                fig.savefig(temporary / f'{name}.png', dpi=220, bbox_inches='tight')
                fig.savefig(temporary / f'{name}.pdf', bbox_inches='tight', metadata=metadata)
                combined.savefig(fig, bbox_inches='tight')
                plt.close(fig)
        after = {hour: sha256(path) for hour, path in paths.items()}
        script_after = sha256(script)
        if after != before or script_after != script_before:
            raise ValueError('inputs or script changed during rendering')
        manifest = {
            'scope': '3,688 paired points; RN1 is a processed analysis, not independent truth.',
            'initialization_utc': '2026-08-16T12:00:00Z',
            'source_hash_receipt': 'docs/evidence/current_forecast_paper_20261029/validation/independent_scores.json',
            'script': {'path': 'tools/plot_hourly_forecast_distribution.py', 'sha256_before': script_before, 'sha256_after': script_after},
            'inputs': [{'path': f'docs/evidence/current_forecast_paper_20261029/scores/{paths[h].name}',
                        'sha256_before': before[h], 'sha256_after': after[h]} for h in HOURS],
            'outputs': [{'path': p.name, 'sha256': sha256(p)} for p in sorted(temporary.iterdir())],
            'color_boundaries_mm': BOUNDS, 'extent_degrees': extent,
        }
        (temporary / 'figure_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        publish_no_replace(temporary, output_dir)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scores-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    render(args.scores_dir, args.output_dir)


if __name__ == '__main__':
    main()
