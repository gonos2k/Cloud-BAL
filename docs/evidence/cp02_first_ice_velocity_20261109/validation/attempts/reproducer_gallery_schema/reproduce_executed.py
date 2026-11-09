#!/usr/bin/env python3
"""Reproduce the tracked first-ice scores, plots and fixed cohorts in fresh scratch."""
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

BUNDLE = Path('docs/evidence/cp02_first_ice_velocity_20261109')


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def replay(root, temporary_parent):
    bundle = root / BUNDLE
    commands, checked = [], []
    with tempfile.TemporaryDirectory(prefix='first-ice-replay-', dir=temporary_parent) as temporary:
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

        run([BUNDLE / 'evaluation/evaluate.py', '--recount', bundle / 'evaluation/results',
             '--output', scratch / 'scores'])
        for name in ('categorical_scores.csv', 'continuous_scores.csv', 'admission_constraints.csv',
                     'observation_transitions.csv', 'verdict.json', 'FULL_SCORES.md'):
            equal(scratch / 'scores' / name, bundle / 'evaluation/results' / name)
        run([BUNDLE / 'evaluation/plot.py', '--results', bundle / 'evaluation/results',
             '--output', scratch / 'figures'])
        figures = sorted((scratch / 'figures').glob('*.png'))
        if len(figures) != 12:
            raise ValueError('must reproduce six CSI and six hourly maps')
        for path in figures:
            equal(path, bundle / 'figures' / path.name)
        run([BUNDLE / 'evaluation/cohort_diagnostics.py', '--results', bundle / 'evaluation/results',
             '--output', scratch / 'cohorts'])
        for name in ('cohorts.csv', 'summary.json'):
            equal(scratch / 'cohorts' / name, bundle / 'evaluation/cohorts' / name)
        if len(checked) != 20:
            raise ValueError('portable artifact coverage must be exactly 20')
        test_log = run(['-m', 'pytest', '-q', '--basetemp', scratch / 'pytest',
                        'tests/test_cp02_first_ice_velocity.py',
                        BUNDLE / 'evaluation/test_first_ice_evaluation.py'])
        match = re.search(r'(\d+) passed', test_log)
        if not match or int(match.group(1)) != 5:
            raise ValueError('all five native/evaluation tests must complete')
        gallery = json.loads((bundle / 'gallery_receipt.json').read_text())
        if sha(bundle / 'all_figures.zip') != gallery['archive_sha256']:
            raise ValueError('gallery archive changed')
        with zipfile.ZipFile(bundle / 'all_figures.zip') as archive:
            if archive.testzip() is not None or set(archive.namelist()) != set(gallery['members']):
                raise ValueError('gallery inventory or CRC differs')
            for name, identity in gallery['members'].items():
                if (sha(bundle / name) != identity['sha256'] or
                    hashlib.sha256(archive.read(name)).hexdigest() != identity['sha256']):
                    raise ValueError(f'gallery member changed: {name}')
    return {'status': 'PASS', 'byte_identical_count': len(checked), 'artifacts': checked,
            'portable_tests_passed': 5, 'gallery_pngs': 12, 'commands': commands,
            'limits': ['WRF histories, executable, modules and archives remain external.',
                       'Replay uses sealed paired RN1 arrays, not a new WRF integration.',
                       'Path-bearing receipts and plot metadata are hash checked, not claimed byte-identical across paths.',
                       'Pinned Intel profile, NumPy/Matplotlib and font prerequisites apply.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--temporary-parent', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    if os.path.lexists(args.receipt):
        raise FileExistsError(args.receipt)
    result = replay(args.root.resolve(), args.temporary_parent)
    result['reproducer_sha256'] = sha(Path(__file__))
    with args.receipt.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps({'status': result['status'], 'byte_identical_count': result['byte_identical_count']}))
