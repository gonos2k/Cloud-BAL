#!/usr/bin/env python3
"""Run one reviewed, privately staged eight-rank B1 capture arm."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

NATIVE = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[5]
RUNTIME = ROOT.parent / 'runtime'
ARMS = ('FIX', 'CONSERVATIVE', 'ICE_FIXED')


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('arm', choices=ARMS)
    parser.add_argument('review', type=Path)
    args = parser.parse_args()
    review = json.loads(args.review.read_text())
    artifacts = [NATIVE / 'runs/launch.py', NATIVE / 'runs/forecast.py',
                 NATIVE / 'runs/rank_wrapper.sh', NATIVE / 'runs/compare_histories.py',
                 NATIVE / 'runs/reference_pins.json', NATIVE / 'runs/closure_plan.md',
                 NATIVE / 'runs/compact.py', NATIVE / 'runs/read_frames.py', NATIVE / 'runs/compare_shared_flux.py',
                 ROOT / 'docs/evidence/cp02_protected_process_20261106/native/provenance/collector_v5/cp02_protected_process_capture.py',
                 NATIVE / 'schema/schema.json',
                 NATIVE / 'source/source_receipt.json', NATIVE / 'source/columns.csv']
    if review.get('status') != 'GO_FOR_LAUNCH':
        raise ValueError('independent launch review is not GO')
    if any(review.get('sha256', {}).get(str(p.relative_to(ROOT))) != sha(p) for p in artifacts):
        raise ValueError('launch review does not bind current recipe, source and schema')
    probe = RUNTIME / f'probe/{args.arm}/probe_receipt.json'
    if (review.get('probe_receipt_sha256', {}).get(args.arm) != sha(probe) or
            json.loads(probe.read_text()).get('status') != 'PASS'):
        raise ValueError('review does not bind a passing probe')
    build = RUNTIME / f'native_build/variants/{args.arm}/build_receipt.json'
    if review.get('build_receipt_sha256', {}).get(args.arm) != sha(build):
        raise ValueError('launch review does not bind build receipt')
    module_path = NATIVE / 'build/build.py'
    spec = importlib.util.spec_from_file_location('capture_build', module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    env, _, _ = module.load_profile()
    temporary = RUNTIME / 'launch_tmp' / args.arm
    temporary.mkdir(parents=True, exist_ok=False)
    env.update(TMPDIR=str(temporary), PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='1',
               OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
    env['NETCDF'] = '/NHNHOME/WORKSPACE/26weather002_A/yhlee/KIM-meso/deps/netcdf-intel'
    env['LD_LIBRARY_PATH'] = env['NETCDF'] + '/lib:' + env.get('LD_LIBRARY_PATH', '')
    runner = NATIVE / 'runs/forecast.py'
    commands = [[sys.executable, '-B', str(runner), 'prepare', args.arm, '--build-receipt', str(build)],
                [sys.executable, '-B', str(runner), 'run', args.arm]]
    results = []
    for command in commands:
        result = subprocess.run(command, cwd=ROOT, env=env, check=False)
        results.append({'argv': command, 'exit_code': result.returncode})
        if result.returncode:
            break
    passed = len(results) == 2 and all(x['exit_code'] == 0 for x in results)
    receipt = {'status': 'PASS' if passed else 'FAIL', 'arm': args.arm, 'review_sha256': sha(args.review),
               'build_receipt_sha256': sha(build), 'commands': results}
    with (RUNTIME / f'{args.arm}_driver_exit.json').open('x') as f:
        json.dump(receipt, f, indent=2); f.write('\n')
    if not passed:
        raise RuntimeError('forecast failed; see driver and rank logs')


if __name__ == '__main__':
    main()
