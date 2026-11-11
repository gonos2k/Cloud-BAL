#!/usr/bin/env python3
"""Freeze implementation inputs before running pinned Intel checks."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[4]
BUNDLE = Path('docs/evidence/moment_feasibility_20261111')
PRIOR = Path('docs/evidence/physical_moment_handoff_20261110/native/actual_real')


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    output = ROOT/BUNDLE/'validation/validation_receipt.json'
    if output.exists():
        raise FileExistsError(output)
    runtime = ROOT.parent/'validation'
    runtime.mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='frozen-validation-', dir=runtime))
    tree = work/'source'
    tree.mkdir()
    paths = []
    for folder in ('src','tests','tools','patches','config','runtime','schema'):
        paths.extend(p.relative_to(ROOT) for p in (ROOT/folder).rglob('*')
                     if p.is_file() and '__pycache__' not in p.parts)
    paths.extend([Path('docs/evidence/cp02_activation_path_20261110/native/source/CONTROL.f90'),
                  PRIOR/'policy.json', PRIOR/'ice_cap_recount.json'])
    inputs = {str(p):sha(ROOT/p) for p in sorted(set(paths))}
    for name in inputs:
        destination = tree/name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT/name, destination)
    env = os.environ.copy()
    env.update(PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1',
               CLOUD_BAL_WORKSPACE_ROOT='/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50',
               CLOUD_BAL_TEST_SCRATCH_ROOT=str(work))
    jobs = {'unit':['bash',str(tree/'tests/run_unit_tests.sh')],
            'boundary':['bash',str(tree/'tests/run_initialize_model_moments.sh')],
            'figures':['python',str(tree/'tools/plot_moment_feasibility.py'),'--output',str(work/'figures')]}
    def run(item):
        label, argv = item
        started = time.monotonic()
        log = ROOT/BUNDLE/'validation'/f'{label}.log'
        with log.open('w') as stream:
            result = subprocess.run(argv, cwd=tree, env=env, stdout=stream, stderr=subprocess.STDOUT)
        receipt = {'exit_code':result.returncode,'seconds':time.monotonic()-started,'argv':argv,
                   'log':str(log.relative_to(ROOT)),'log_sha256':sha(log)}
        print(json.dumps({label:receipt}), flush=True)
        if result.returncode:
            raise RuntimeError(f'{label} failed; see {log}')
        return label,receipt
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        results = dict(pool.map(run,jobs.items()))
    exact = {}
    for name in ('01_ice_feasibility.png','ice_feasibility_curve.csv'):
        expected = ROOT/BUNDLE/'figures'/name
        if sha(expected)!=sha(work/'figures'/name):
            raise RuntimeError(f'figure/data differs: {name}')
        exact[name] = sha(expected)
    if inputs!={name:sha(ROOT/name) for name in inputs}:
        raise RuntimeError('working implementation changed during validation')
    receipt = {'status':'PASS','source_sha256':inputs,'profile_sha256':sha(tree/'tests/intel_toolchain.sh'),
               'commands':results,'exact_figure_outputs':exact,'scratch':str(work),
               'scope':'Frozen-source Intel unit and final-file fixture tests, phase/consumer tests and exact analytical plot/data; no WRF first use or forecast.'}
    output.write_text(json.dumps(receipt,indent=2)+'\n')
    print('Frozen-source validation PASS',flush=True)


if __name__=='__main__':
    main()
