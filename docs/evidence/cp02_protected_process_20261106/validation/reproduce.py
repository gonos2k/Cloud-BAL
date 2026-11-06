#!/usr/bin/env python3
"""Reproduce portable tables and figures using only an exported Git tree."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

BUNDLE = Path('docs/evidence/cp02_protected_process_20261106')
LAUNCH_SHA = '41a1d6e8dd2b0821dc03bdc6927465513c31e877981497eb795ad349284201e5'


def sha(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def compare(actual: Path, expected: Path, checked: list[dict]) -> None:
    if sha(actual) != sha(expected):
        raise ValueError(f'reproduced bytes differ: {expected}')
    checked.append({'artifact': str(expected), 'sha256': sha(expected),
                    'size_bytes': expected.stat().st_size})


def replay(root: Path, scratch_parent: Path) -> dict:
    root = root.resolve()
    bundle = root / BUNDLE
    checked, commands = [], []
    with tempfile.TemporaryDirectory(prefix='protected-replay-', dir=scratch_parent) as temporary:
        scratch = Path(temporary)
        env = os.environ.copy()
        env.update(PYTHONDONTWRITEBYTECODE='1', MPLCONFIGDIR=str(scratch / 'mpl'),
                   TMPDIR=str(scratch), OMP_NUM_THREADS='1', MKL_NUM_THREADS='1',
                   OPENBLAS_NUM_THREADS='1', NUMEXPR_NUM_THREADS='1')

        def run(arguments: list[str]) -> None:
            command = [sys.executable, '-B', *map(str, arguments)]
            result = subprocess.run(command, cwd=root, env=env, text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            commands.append({'command': command, 'exit_code': result.returncode,
                             'output': result.stdout})
            if result.returncode:
                raise RuntimeError(f'replay command failed: {command}\n{result.stdout}')

        run(['tools/cp02_protected_process_cohorts.py', '--output', scratch / 'cohorts'])
        cohort_names = sorted(path.name for path in (bundle / 'cohorts').glob('*.csv'))
        if len(cohort_names) != 9:
            raise ValueError('expected exactly nine cohort tables')
        for name in cohort_names:
            compare(scratch / 'cohorts' / name, bundle / 'cohorts' / name, checked)
        run(['tools/cp02_b1_failure_context.py', '--output', scratch / 'context'])
        context_names = sorted(path.name for path in (bundle / 'residual_fix/context').glob('*.csv'))
        if len(context_names) != 5:
            raise ValueError('expected exactly five corrected context tables')
        for name in context_names:
            compare(scratch / 'context' / name, bundle / 'residual_fix/context' / name, checked)
        run(['tools/plot_cp02_protected_process.py', '--output', scratch / 'figures'])
        basic_names = sorted(path.name for path in (bundle / 'figures').glob('*.png'))
        if len(basic_names) != 3:
            raise ValueError('expected exactly three basic figures')
        for name in basic_names:
            compare(scratch / 'figures' / name, bundle / 'figures' / name, checked)
        run(['tools/cp02_protected_process_summary.py',
             '--old-dir', bundle / 'native/compact/OLD',
             '--fix-dir', bundle / 'native/compact/FIX',
             '--launch-receipt', bundle / 'native/provenance/full_run/full_run_receipt.json',
             '--launch-receipt-sha256', LAUNCH_SHA, '--output-dir', scratch / 'summary'])
        for name in ('point_level_process_ledger.csv', 'point_level_nominal_rates.csv',
                     'group_level_process_profiles.csv', 'summary_receipt.json'):
            compare(scratch / 'summary' / name, bundle / 'native/analysis/summary' / name, checked)
        run(['tools/plot_cp02_protected_process_native.py',
             '--ledger', scratch / 'summary/point_level_process_ledger.csv',
             '--summary-receipt', scratch / 'summary/summary_receipt.json',
             '--output-dir', scratch / 'native_figures'])
        for name in ('two_point_process_components.png', 'metadata.json', 'receipt.json'):
            compare(scratch / 'native_figures' / name, bundle / 'native_figures' / name, checked)

        surface = bundle / 'science/surface/validated'
        run([str(BUNDLE / 'science/surface/portable_recount_surface.py'),
             '--packet', surface / 'surface_reconciliation_packet.npz',
             '--packet-receipt', surface / 'surface_reconciliation_packet_receipt.json',
             '--reference-csv', surface / 'point_hourly_surface_components.csv',
             '--output-receipt', scratch / 'surface_recount.json'])
        surface_result = json.loads((scratch / 'surface_recount.json').read_text())
        if not surface_result.get('byte_identical') or surface_result.get('rows') != 1500:
            raise ValueError('portable surface recount is incomplete')

        spec = importlib.util.spec_from_file_location('protected_full_scores', bundle / 'tables/generate_tables.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.OUTPUT = scratch / 'tables'
        module.generate()
        compare(scratch / 'tables/FULL_SCORES.md', bundle / 'tables/FULL_SCORES.md', checked)
        compare(scratch / 'tables/receipt.json', bundle / 'tables/receipt.json', checked)

        gallery = json.loads((bundle / 'gallery_receipt.json').read_text())
        archive = bundle / gallery['archive']['path']
        if sha(archive) != gallery['archive']['sha256']:
            raise ValueError('combined gallery archive identity differs')
        with zipfile.ZipFile(archive) as package:
            if package.testzip() is not None or set(package.namelist()) != set(gallery['members']):
                raise ValueError('combined gallery members or CRC differ')
            for name, identity in gallery['members'].items():
                if (hashlib.sha256(package.read(name)).hexdigest() != identity['sha256']
                        or sha(bundle / name) != identity['sha256']):
                    raise ValueError(f'combined gallery member differs: {name}')
        if len(checked) != 26:
            raise ValueError(f'portable output inventory differs from 26: {len(checked)}')
        for row in checked:
            row['artifact'] = str(Path(row['artifact']).relative_to(root))
    return {'status': 'PASS', 'root': str(root), 'byte_identical_artifact_count': len(checked),
            'artifacts': checked, 'surface_recount': surface_result, 'commands': commands,
            'combined_gallery_verified': True,
            'limits': ['Full raw-stream replay, native model integration and original NetCDF extraction require the external archive.',
                       'Basic figure metadata and its earlier attempt-containing ZIP are not claimed byte-identical across output directories.']}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--scratch-parent', type=Path, required=True)
    parser.add_argument('--output-receipt', type=Path, required=True)
    args = parser.parse_args()
    if args.output_receipt.exists() or args.output_receipt.is_symlink():
        raise FileExistsError(args.output_receipt)
    result = replay(args.root, args.scratch_parent)
    result['reproducer_sha256'] = sha(Path(__file__))
    args.output_receipt.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'status': result['status'], 'byte_identical_artifact_count': result['byte_identical_artifact_count']}))


if __name__ == '__main__':
    main()
