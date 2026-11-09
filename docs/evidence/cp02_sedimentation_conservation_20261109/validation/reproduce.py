#!/usr/bin/env python3
"""Replay tracked portable arrays, figures, and native/sample regression tests."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile

BUNDLE = Path('docs/evidence/cp02_sedimentation_conservation_20261109')


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def replay(root, temporary_parent):
    bundle = root / BUNDLE
    commands, checked = [], []
    with tempfile.TemporaryDirectory(prefix='sedimentation-replay-', dir=temporary_parent) as temporary:
        scratch = Path(temporary)
        env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'TMPDIR': str(scratch),
               'MPLCONFIGDIR': str(scratch / 'mpl'), 'OMP_NUM_THREADS': '1',
               'OPENBLAS_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1'}

        def run(arguments):
            argv = [sys.executable, '-B', *map(str, arguments)]
            result = subprocess.run(argv, cwd=root, env=env, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True)
            commands.append({'argv': argv, 'exit_code': result.returncode, 'output': result.stdout})
            if result.returncode:
                raise RuntimeError(result.stdout)
            return result.stdout

        def equal(actual, expected):
            if sha(actual) != sha(expected):
                raise ValueError(f'portable reproduction differs: {expected}')
            checked.append({'path': str(expected.relative_to(root)), 'sha256': sha(expected),
                            'size_bytes': expected.stat().st_size})

        run(['tools/cp02_sedimentation_focus.py', '--compact',
             root / 'docs/evidence/cp02_protected_process_20261106/native/compact',
             '--bundle', scratch / 'focus'])
        for name in ('p01_return_corners.csv', 'p01_10min_bins.csv',
                     'p01_surface_calls.csv', 'p01_timing_receipt.json'):
            equal(scratch / 'focus/science' / name, bundle / 'science' / name)
        equal(scratch / 'focus/figures/p01_return_and_surface.png',
              bundle / 'figures/p01_return_and_surface.png')

        run([str(BUNDLE / 'evaluation/evaluate.py'), '--recount', bundle / 'evaluation/results',
             '--output', scratch / 'scores'])
        for name in ('categorical_scores.csv', 'continuous_scores.csv', 'admission_constraints.csv',
                     'observation_transitions.csv', 'verdict.json', 'FULL_SCORES.md'):
            equal(scratch / 'scores' / name, bundle / 'evaluation/results' / name)
        for name in sorted((bundle / 'evaluation/results/figures').glob('*.png')):
            equal(scratch / 'scores/figures' / name.name, bundle / 'figures' / name.name)

        run([str(BUNDLE / 'evaluation/plot_maps.py'), '--output', scratch / 'maps'])
        for name in sorted((scratch / 'maps').glob('*.png')):
            equal(name, bundle / 'figures' / name.name)
        equal(scratch / 'maps/maps_metadata.json', bundle / 'evaluation/maps_metadata.json')
        if len(checked) != 24:
            raise ValueError(f'portable output coverage differs from 24: {len(checked)}')

        tests = ['tests/test_cp02_sedimentation_raw_audit.py',
                 'tests/test_cp02_sedimentation_focus.py',
                 'tests/test_cp02_sedimentation_conservation.py',
                 str(BUNDLE / 'evaluation/test_evaluate.py')]
        test_log = run(['-m', 'pytest', '-q', '--basetemp', scratch / 'pytest', *tests])
        match = re.search(r'(\d+) passed', test_log)
        if not match or int(match.group(1)) != 18:
            raise ValueError('portable raw/native/evaluation tests did not complete all 18 cases')

        gallery = json.loads((bundle / 'gallery_receipt.json').read_text())
        if sha(bundle / 'all_figures.zip') != gallery['archive_sha256']:
            raise ValueError('gallery archive identity differs')
        with zipfile.ZipFile(bundle / 'all_figures.zip') as archive:
            if archive.testzip() is not None or set(archive.namelist()) != set(gallery['members']):
                raise ValueError('gallery CRC or inventory differs')
            for name, identity in gallery['members'].items():
                if (sha(bundle / name) != identity['sha256']
                        or hashlib.sha256(archive.read(name)).hexdigest() != identity['sha256']):
                    raise ValueError(f'gallery member identity differs: {name}')
    return {'status': 'PASS', 'byte_identical_count': len(checked), 'artifacts': checked,
            'portable_tests_passed': 18, 'gallery_pngs': 13, 'commands': commands,
            'limits': ['Original full raw streams and full WRF histories remain external.',
                       'This replay uses tracked sample raw streams and frozen forecast arrays.',
                       'Pinned Intel, NumPy/Matplotlib/netCDF4, font and coastline prerequisites apply.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--temporary-parent', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    if args.receipt.exists() or args.receipt.is_symlink():
        raise FileExistsError(args.receipt)
    result = replay(args.root.resolve(), args.temporary_parent)
    result['reproducer_sha256'] = sha(Path(__file__))
    with args.receipt.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps({'status': result['status'], 'byte_identical_count': result['byte_identical_count']}))
