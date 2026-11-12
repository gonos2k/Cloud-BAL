#!/usr/bin/env python3
"""Validate a frozen source copy with pinned Intel in fresh external scratch."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[4]
BUNDLE = Path('docs/evidence/ice_background_prior_20261112')
SOURCES = (
    'src/common/cloud_bal_state.f90', 'src/common/cloud_bal_microphysics_initialization.f90',
    'tools/ice_background_driver.f90', 'tools/model_moment_driver.f90',
    'tools/propose_ice_background.py', 'tools/initialize_model_moments.py',
    'tests/intel_toolchain.sh', 'tests/run_ice_background_prior.sh',
    'tests/test_ice_background_prior.f90', 'tests/test_ice_snow_initialization.f90',
    'tests/test_microphysics_initialization.f90', 'tests/test_ice_background_prior.py',
    'tests/test_initialize_model_moments.py', 'tests/test_tier_exceptions.json',
    'tests/check_test_tiers.py', 'tests/python_script_test_allowlist.json',
    'tests/run_unit_tests.sh',
    'docs/evidence/cp02_activation_path_20261110/native/source/CONTROL.f90',
    str(BUNDLE / 'validation/run.py'),
)


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def hashes(root):
    return {name: sha(root / name) for name in SOURCES}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scratch', type=Path)
    args = parser.parse_args()
    parent = ROOT.parent / 'ice_background_prior_20261112'
    parent.mkdir(exist_ok=True)
    scratch = args.scratch or Path(tempfile.mkdtemp(prefix='validation.', dir=parent))
    scratch = scratch.resolve()
    if scratch == ROOT or ROOT in scratch.parents:
        raise ValueError('build scratch must be outside source checkout')
    freeze = scratch / 'freeze/Cloud-BAL'
    freeze.mkdir(parents=True)
    before = hashes(ROOT)
    for name in SOURCES:
        target = freeze / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    assert hashes(freeze) == before
    logs = scratch / 'logs'
    logs.mkdir()
    commands = []
    for label, command, cwd in (
            ('native_boundary', ['bash', str(freeze / 'tests/run_ice_background_prior.sh')], freeze),
            ('test_registry', [sys.executable, 'tests/check_test_tiers.py'], ROOT)):
        log = logs / (label + '.log')
        with log.open('wb') as stream:
            result = subprocess.run(command, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT)
        commands.append({'label': label, 'argv': command, 'cwd': str(cwd),
                         'exit_code': result.returncode, 'log': 'logs/' + log.name, 'log_sha256': sha(log)})
        if result.returncode:
            raise RuntimeError(f'{label} failed; retained log: {log}')
    after = hashes(ROOT)
    frozen_after = hashes(freeze)
    assert before == after == frozen_after
    receipt = {'status': 'PASS', 'source_sha256_before': before, 'source_sha256_after': after,
               'freeze_sha256_after': frozen_after, 'scratch': str(scratch), 'commands': commands,
               'scope': 'Synthetic proposal and file handoff; no independent background or new WRF forecast.',
               'profiles': ['pinned Intel audit O0', 'pinned Intel strict repro O2'],
               'checks_per_profile': {'new_python_methods': 10, 'existing_python_methods': 19,
                                      'fortran_programs': 3}}
    destination = ROOT / BUNDLE / 'validation'
    assert not (destination / 'receipt.json').exists(), 'final receipt already exists'
    shutil.copytree(logs, destination / 'logs')
    with (destination / 'receipt.json').open('x') as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True)
        stream.write('\n')
    (scratch / 'receipt.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'status': 'PASS', 'source_files': len(before), 'scratch': str(scratch)}))


if __name__ == '__main__':
    main()
