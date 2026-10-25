#!/usr/bin/env python3
"""Run the retained strict-profile calc_ww_cp binary on fresh staged inputs."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

import netCDF4
import numpy as np

import pr86_time_response as runner
import pr99_native_consumer_replay as native
from pr99_native_consumer_metrics import read_ww
from pr101_guarded_replay import unlimited_stack

ROOT = Path(__file__).resolve().parents[1]
EXECUTABLE = Path('/var/tmp/pr99-native-consumer-q7y9dgzx/native_consumer.exe')
EXECUTABLE_SHA = 'ae83118c881da4dee24cdf43c15ecacda3cf07b2b2f5b403902acb10e7322c61'
DRIVER_SHA = '9ca9f3846313180ae8913258ed54e740f375b6a3bc1fd2d93a404996c141604f'
PROFILE_SHA = '5439fa3a692acc9ee63571ee8dd8ff1ce50d1810e9339d9ead906f3c817111b4'
PROFILE = ROOT / 'tests/intel_toolchain.sh'
MPI_ENV = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/env/vars.sh')
LIBRARIES = ':'.join((
    '/NHNHOME/WORKSPACE/26weather002_A/Library/WRF_LIBS/lib',
    '/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/compiler/2026.0/lib',
    '/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/lib'))
HYDRO_WW_SHA = '71ea495f0897a07c84be63bcf2ae7a168f59d32fa6546fd7e42a118d8b0f1707'
CANONICAL = ROOT / 'docs/evidence/pr99_native_consumer_20261022_canonical.json'
CANONICAL_SHA = '6d826e46510d08d6dd6c9e572f116090ce5ef1a5530c37454b6623d58e6ce91f'
MEMBER_PROOF = ROOT / 'docs/evidence/pr102_execution_20261025/calc_ww_archive_member_identity.json'
MEMBER_PROOF_SHA = '6d7455927c79b7e15ea46ae22173a150c00a676b444513e2bb765d442c2d039c'


def pin(path: Path) -> dict:
    return {'path': str(path.resolve()), 'sha256': runner.sha256(path)}


def require_pin(path: Path, expected: str) -> None:
    if not path.is_file() or runner.sha256(path) != expected:
        raise ValueError(f'archived consumer artifact changed: {path}')


def require_fresh_directory(directory: Path) -> None:
    if (not directory.is_absolute() or directory.resolve() != directory
            or directory.exists() or directory.is_symlink()
            or any((p / '.git').exists() for p in directory.parents)):
        raise ValueError('consumer requires a fresh scratch directory outside checkouts')


def run_case(input_path: Path, expected_input_sha: str, directory: Path,
             expected_ww_sha: str | None = None) -> dict:
    require_pin(input_path, expected_input_sha)
    require_fresh_directory(directory)
    bindings = {str(path): pin(path)['sha256'] for path in (
        input_path, EXECUTABLE, PROFILE, MPI_ENV, native.DRIVER,
        Path(native.__file__), Path(__file__), CANONICAL, MEMBER_PROOF,
        Path(runner.__file__),
        ROOT / 'tools/pr87_native_history.py', ROOT / 'tools/pr99_native_consumer_metrics.py',
        ROOT / 'tools/pr101_guarded_replay.py')}
    directory.mkdir(parents=True, exist_ok=False)
    shutil.copy2(EXECUTABLE, directory / 'consumer.exe')
    with netCDF4.Dataset(input_path) as ds:
        ds.set_auto_mask(False)
        arrays, *_ = native.native_arrays(ds, 0)
    native.write_input(directory / 'native_consumer_input.bin', arrays)
    input_binary = pin(directory / 'native_consumer_input.bin')
    command = ['bash', '-c',
               'set -e; source "$1"; source "$2"; '
               'export LD_LIBRARY_PATH="$3:${LD_LIBRARY_PATH:-}"; exec "$4"',
               'pr102-archived-consumer', str(PROFILE), str(MPI_ENV), LIBRARIES,
               str(directory / 'consumer.exe')]
    launch = {'schema': 'pr102_archived_consumer_launch_v1', 'argv': command,
              'cwd': str(directory), 'bindings': bindings, 'input_binary': input_binary,
              'start_utc': datetime.now(timezone.utc).isoformat(),
              'scope': 'Retained archived calc_ww_cp call only; not a WRF time integration.'}
    (directory / 'launch.json').write_text(json.dumps(launch, indent=2) + '\n')
    environment = {**os.environ, 'OMP_NUM_THREADS': '1', 'OMP_DYNAMIC': 'FALSE'}
    with (directory / 'run.log').open('x') as log:
        result = subprocess.run(command, cwd=directory, env=environment, stdout=log,
                                stderr=subprocess.STDOUT, preexec_fn=unlimited_stack)
    changed = [name for name, digest in bindings.items()
               if runner.sha256(Path(name)) != digest]
    output = directory / 'native_consumer_ww.bin'
    issues = []
    if result.returncode:
        issues.append(f'native executable return code {result.returncode}')
    if changed:
        issues.append('input or source dependency changed')
    if runner.sha256(directory / 'consumer.exe') != EXECUTABLE_SHA:
        issues.append('staged executable changed')
    if runner.sha256(directory / 'native_consumer_input.bin') != input_binary['sha256']:
        issues.append('staged consumer input changed')
    values = None
    if not issues:
        try:
            values = read_ww(output)
            if np.any(values[[0, -1]] != 0):
                issues.append('native bottom or top ww face is nonzero')
            if expected_ww_sha is not None and runner.sha256(output) != expected_ww_sha:
                issues.append('retained HYDRO reference output differs bytewise')
        except (OSError, ValueError) as error:
            issues.append(str(error))
    receipt = {'schema': 'pr102_archived_consumer_run_v1',
               'status': 'COMPLETE' if not issues else 'INCOMPLETE',
               'returncode': result.returncode, 'issues': issues,
               'launch': pin(directory / 'launch.json'),
               'log': pin(directory / 'run.log'), 'input': pin(input_path),
               'output': pin(output) if output.is_file() else None,
               'active_shape': list(values.shape) if values is not None else None,
               'finite_value_count': int(values.size) if values is not None else None,
               'expected_ww_sha256': expected_ww_sha,
               'end_utc': datetime.now(timezone.utc).isoformat()}
    (directory / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    if issues:
        raise ValueError(f'archived consumer failed; see {directory / "receipt.json"}')
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--proposal', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    require_pin(EXECUTABLE, EXECUTABLE_SHA)
    require_pin(native.DRIVER, DRIVER_SHA)
    require_pin(PROFILE, PROFILE_SHA)
    require_pin(CANONICAL, CANONICAL_SHA)
    require_pin(MEMBER_PROOF, MEMBER_PROOF_SHA)
    canonical = json.loads(CANONICAL.read_text())['provenance']
    proof = json.loads(MEMBER_PROOF.read_text())
    if (canonical['standalone_executable_sha256'] != EXECUTABLE_SHA
            or canonical['driver_sha256'] != DRIVER_SHA
            or canonical['intel_profile_sha256'] != PROFILE_SHA
            or proof['status'] != 'BYTE_IDENTICAL' or len(proof['cohorts']) != 2):
        raise ValueError('archived native consumer provenance does not match')
    for row in proof['cohorts']:
        require_pin(Path(row['build_receipt']), row['build_receipt_sha256'])
        payload = subprocess.check_output(['ar', 'p', row['archive'], row['member']])
        if (hashlib.sha256(payload).hexdigest() != row['member_sha256']
                or row['member_sha256'] != canonical['archived_calc_ww_cp_object_sha256']):
            raise ValueError('C1/C2 archived calc_ww object identity changed')
    proposal_pin, runner_pin = pin(args.proposal), pin(Path(runner.__file__))
    binding = runner._wind_structure_input_binding(args.proposal)
    require_pin(args.proposal, proposal_pin['sha256'])
    require_pin(Path(runner.__file__), runner_pin['sha256'])
    inputs = {name: binding['artifacts'][name] for name in ('reference_hydro', 'candidate')}
    if not args.execute:
        print(json.dumps({'status': 'PLAN_ONLY', 'inputs': inputs,
                          'executable': pin(EXECUTABLE)}, indent=2))
        return
    require_fresh_directory(args.output)
    args.output.mkdir(parents=True, exist_ok=False)
    shutil.copy2(args.proposal, args.output / 'proposal.json')
    require_pin(args.output / 'proposal.json', proposal_pin['sha256'])
    result = {}
    for name, row in inputs.items():
        result[name] = run_case(Path(row['path']), row['sha256'], args.output / name,
                               HYDRO_WW_SHA if name == 'reference_hydro' else None)
    proposal_changed = (runner.sha256(args.proposal) != proposal_pin['sha256']
                        or runner.sha256(args.output / 'proposal.json') != proposal_pin['sha256'])
    runner_changed = runner.sha256(Path(runner.__file__)) != runner_pin['sha256']
    report = {'schema': 'pr102_archived_consumer_runs_v1',
              'status': 'INCOMPLETE' if proposal_changed or runner_changed else 'COMPLETE',
              'proposal': proposal_pin, 'proposal_changed': proposal_changed,
              'binding_validator': runner_pin, 'binding_validator_changed': runner_changed,
              'executable': pin(EXECUTABLE),
              'canonical_provenance': pin(CANONICAL), 'archive_identity': pin(MEMBER_PROOF),
              'cohorts': result, 'physical_approval': 'FAIL_OPEN',
              'scope': 'Closed native calls and HYDRO bit identity only; arithmetic/constraint assessment is a separate gate.'}
    (args.output / 'runs.json').write_text(json.dumps(report, indent=2) + '\n')
    if report['status'] != 'COMPLETE':
        raise ValueError('proposal or binding-validator source changed during native calls')
    print(json.dumps({'status': report['status'], 'directory': str(args.output)}, indent=2))


if __name__ == '__main__':
    main()
