#!/usr/bin/env python3
"""Replay portable CP02 context and figures from a sealed export."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

CONTEXT_FILES = (
    'point_surface_paths.csv', 'layer_features.csv', 'cohort_physical_contrasts.csv',
    'cohort_surface_context.csv', 'cohort_surface_context_summary.csv',
)
FIGURE_FILES = (
    'csi_algebra_h5_5mm.png', 'h2_transition_maps.png', 'h5_transition_maps.png',
    'selected_point_hourly_paths.png', 'conditional_layer_contrasts.png',
)
BUNDLE = Path('docs/evidence/cp02_failure_focus_20261105')


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def replay(root: Path) -> dict:
    root = root.resolve()
    context_dir, figure_dir = root / BUNDLE / 'context', root / BUNDLE / 'figures'
    required = [root / 'tools/cp02_b1_failure_context.py', root / 'tools/plot_cp02_b1_failure_focus.py',
                context_dir / 'bundle_receipt.json', figure_dir / 'offline_gallery.zip']
    if any(not path.is_file() for path in required):
        raise FileNotFoundError('export is missing a pinned context or figure input')
    with tempfile.TemporaryDirectory(prefix='cp02-failure-replay-') as temporary:
        scratch = Path(temporary)
        env = os.environ.copy()
        env.update(PYTHONDONTWRITEBYTECODE='1', MPLCONFIGDIR=str(scratch / 'mplconfig'))
        for key in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
            env[key] = '1'
        commands = (
            [sys.executable, 'tools/cp02_b1_failure_context.py', '--output', str(scratch / 'context')],
            [sys.executable, 'tools/plot_cp02_b1_failure_focus.py', '--output', str(scratch / 'figures')],
        )
        for command in commands:
            result = subprocess.run(command, cwd=root, env=env, text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            if result.returncode:
                raise RuntimeError(f"command failed ({result.returncode}): {' '.join(command)}\n{result.stdout}")
        for name in CONTEXT_FILES:
            if digest(scratch / 'context' / name) != digest(context_dir / name):
                raise ValueError(f'context CSV bytes differ: {name}')
        for name in FIGURE_FILES:
            if digest(scratch / 'figures' / name) != digest(figure_dir / name):
                raise ValueError(f'figure PNG bytes differ: {name}')
        with zipfile.ZipFile(scratch / 'figures/offline_gallery.zip') as actual, \
                zipfile.ZipFile(figure_dir / 'offline_gallery.zip') as expected:
            actual_inventory = actual.namelist()
            expected_inventory = expected.namelist()
            if actual_inventory != expected_inventory:
                raise ValueError('offline gallery ZIP inventory differs')
        return {'status': 'PASS', 'context_csvs_byte_equal': list(CONTEXT_FILES),
                'figure_pngs_byte_equal': list(FIGURE_FILES),
                'zip_inventory_equal': actual_inventory,
                'metadata_json_compared': False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True, help='root of the final clean export')
    args = parser.parse_args()
    print(replay(args.root))


if __name__ == '__main__':
    main()
