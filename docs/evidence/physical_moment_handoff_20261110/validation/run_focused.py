#!/usr/bin/env python3
"""Validate frozen source copies, independent of a writable shared worktree."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[4]
BUNDLE = Path('docs/evidence/physical_moment_handoff_20261110')


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    output=ROOT/BUNDLE/'validation/focused_receipt.json'
    if output.exists(): raise FileExistsError(output)
    work=Path(tempfile.mkdtemp(prefix='focused-',dir=ROOT.parent/'validation'))
    tree=work/'source';tree.mkdir()
    paths=['src/common/cloud_bal_state.f90','src/common/cloud_bal_column_physics.f90',
           'src/common/cloud_bal_microphysics_initialization.f90','tools/model_moment_driver.f90',
           'tools/initialize_model_moments.py','tools/plot_physical_moment_handoff.py',
           'tests/intel_toolchain.sh','tests/test_initialize_model_moments.py',
           'tests/run_initialize_model_moments.sh','tests/test_tier_exceptions.json',
           'docs/evidence/cp02_activation_path_20261110/native/source/CONTROL.f90']
    for folder in ('science','native'):
        paths += [str(p.relative_to(ROOT)) for p in (ROOT/BUNDLE/folder).glob('*') if p.is_file()]
    inputs={n:sha(ROOT/n) for n in paths}
    for n in paths:
        dest=tree/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/n,dest)
    env=os.environ.copy()
    env.update(PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
    jobs={'boundary':['bash',str(tree/'tests/run_initialize_model_moments.sh')],
          'physics':['bash',str(tree/BUNDLE/'science/run_integration_cases.sh')],
          'rain_consumer':['bash',str(tree/BUNDLE/'native/run_rain_intercept_proof.sh')],
          'figures':[sys.executable,str(tree/'tools/plot_physical_moment_handoff.py'),'--output',str(work/'figures')]}
    def run(item):
        label,cmd=item;started=time.monotonic()
        result=subprocess.run(cmd,cwd=tree,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        log=work/(label+'.log');log.write_text(result.stdout)
        if result.returncode:raise RuntimeError(f'{label} failed: {log}\n{result.stdout[-2500:]}')
        return label,{'exit_code':0,'seconds':time.monotonic()-started,'argv':cmd,'log':str(log),'log_sha256':sha(log)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results=dict(pool.map(run,jobs.items()))
    assert 'Ran 11 tests' in (work/'boundary.log').read_text()
    assert (work/'physics.log').read_text().count('six physical integration cases PASS')==2
    checks={}
    for n in ('01_initialization_path.png','02_rain_psd_freedom.png','rain_psd_family.csv'):
        assert sha(ROOT/BUNDLE/'figures'/n)==sha(work/'figures'/n),n
        checks[n]=sha(work/'figures'/n)
    assert inputs=={n:sha(ROOT/n) for n in paths},'working inputs changed'
    r={'status':'PASS','boundary_tests':11,'composed_cases':6,'physics_profiles':['O0','O2'],
       'source_sha256':inputs,'commands':results,'exact_figure_outputs':checks,
       'profile_sha256':sha(tree/'tests/intel_toolchain.sh'),'scratch':str(work),
       'scope':'Frozen-source fixture boundary, six composed physical cases, isolated rain-consumer sign proof and exact figure/data replay; no first native use or forecast.'}
    output.write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps({'status':'PASS','boundary_tests':11,'physical_cases':6,'figure_outputs':3}))


if __name__=='__main__':main()
