#!/usr/bin/env python3
"""Execute one frozen, privately staged six-hour experiment and retain its exit."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

BUNDLE = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[4]
RUNTIME = ROOT.parent / 'runtime'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case', choices=('CONTROL', 'MP10'))
    args = parser.parse_args()
    plan_path = BUNDLE / 'forecast/launch_plan.json'
    initial_plan_sha = sha(plan_path)
    plan = json.loads(plan_path.read_text())
    if plan['status'] != 'FROZEN_CONTROLLED_SIX_HOUR_PLAN':
        raise ValueError('launch plan is not frozen')
    for name, expected in plan['source_sha256'].items():
        if sha(ROOT / name) != expected:
            raise ValueError(f'launch source differs from frozen plan: {name}')
    for name, expected in plan.get('external_sha256', {}).items():
        if sha(name) != expected:
            raise ValueError(f'launch external input differs from frozen plan: {name}')
    build_path = RUNTIME / f'native_build/variants/{args.case}/build_receipt.json'
    if sha(build_path) != plan['build_receipt_sha256'][args.case]:
        raise ValueError('build receipt differs from frozen plan')
    module_path = BUNDLE / 'forecast/build.py'
    spec = importlib.util.spec_from_file_location('pinned_build_profile', module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    environment, _compiler, _version = module.load_profile()
    temporary = RUNTIME / 'launch_tmp' / args.case
    temporary.mkdir(parents=True, exist_ok=False)
    environment.update(TMPDIR=str(temporary), PYTHONDONTWRITEBYTECODE='1',
                       OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
    environment['NETCDF'] = '/NHNHOME/WORKSPACE/26weather002_A/yhlee/KIM-meso/deps/netcdf-intel'
    environment['LD_LIBRARY_PATH'] = environment['NETCDF'] + '/lib:' + environment.get('LD_LIBRARY_PATH', '')
    runner = BUNDLE / 'forecast/forecast.py'
    prepared_path = RUNTIME / 'forecasts' / args.case / 'prepared.json'
    if sha(prepared_path) != plan['prepared_sha256'][args.case]:
        raise ValueError('prepared run differs from frozen plan')
    commands = [[sys.executable, '-B', str(runner), 'run', args.case]]
    started = time.monotonic()
    exits = []
    for command in commands:
        result = subprocess.run(command, cwd=ROOT, env=environment)
        exits.append({'argv': command, 'exit_code': result.returncode})
        if result.returncode:
            break
    unchanged = sha(plan_path) == initial_plan_sha and all(sha(ROOT / name) == expected for name, expected in plan['source_sha256'].items())
    unchanged = unchanged and all(sha(name) == expected for name, expected in plan.get('external_sha256', {}).items())
    passed = len(exits) == 1 and all(row['exit_code'] == 0 for row in exits) and unchanged
    output = RUNTIME / f'{args.case}_driver_exit.json'
    receipt = {'status': 'PASS' if passed else 'FAIL', 'case': args.case,
               'plan_sha256': initial_plan_sha, 'commands': exits,
               'source_inputs_unchanged': unchanged, 'elapsed_seconds': time.monotonic() - started}
    with output.open('x') as stream:
        json.dump(receipt, stream, indent=2)
        stream.write('\n')
    if not passed:
        raise RuntimeError('controlled forecast did not complete with unchanged sources')


if __name__ == '__main__':
    main()
