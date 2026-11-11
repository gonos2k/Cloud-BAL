#!/usr/bin/env python3
"""Run the directly affected tests from frozen inputs with pinned Intel."""
import hashlib,json,os,shutil,subprocess,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
B=Path('docs/evidence/phase_preconditions_20261111')
PATHS=['src/common/cloud_bal_state.f90','src/common/cloud_bal_column_physics.f90',
       'src/common/cloud_bal_microphysics_initialization.f90','src/common/cloud_bal_phase_moments.f90',
       'tests/intel_toolchain.sh','tests/run_phase_moment_consumer.sh','tests/test_phase_moments.f90',
       'tests/test_phase_initialization_chain.f90','tests/test_phase_consumer_native.f90',
       'tests/source_extract_phase_consumer.py',
       'docs/evidence/cp02_activation_path_20261110/native/source/CONTROL.f90']

def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    output=ROOT/B/'validation/receipt.json'
    if output.exists():raise FileExistsError(output)
    runtime=ROOT.parent/'runtime';runtime.mkdir(exist_ok=True)
    work=Path(tempfile.mkdtemp(prefix='frozen-',dir=runtime)); tree=work/'source'
    hashes={n:sha(ROOT/n) for n in PATHS}
    for n in PATHS:
        dst=tree/n;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/n,dst)
        assert sha(dst)==hashes[n]
    env=os.environ.copy();env.update(PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',
        CLOUD_BAL_TEST_SCRATCH_ROOT=str(work),OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
    argv=['bash',str(tree/'tests/run_phase_moment_consumer.sh')]
    log=ROOT/B/'validation/intel.log';start=time.monotonic()
    with log.open('x') as stream:
        result=subprocess.run(argv,cwd=tree,env=env,stdout=stream,stderr=subprocess.STDOUT)
    assert result.returncode==0, str(log)
    text=log.read_text()
    for message in ['phase moment completion: PASS','phase to initialization chain: PASS',
                    'native slope equality and active branches: PASS']:
        assert text.count(message)==2,message
    assert hashes=={n:sha(ROOT/n) for n in PATHS},'source inputs changed'
    receipt={'status':'PASS','base':'359ef4be308fb44693fce87f601ae9b7fabe3835','source_sha256':hashes,
       'command':argv,'exit_code':result.returncode,'seconds':time.monotonic()-start,
       'log':str(log.relative_to(ROOT)),'log_sha256':sha(log),'profiles':['O0 checked','O2 optimized'],
       'scope':'Affected phase helper, phase-to-completion chain and extracted native consumer only. Prior full unit run not repeated. No WRF integration or physical NI policy decision.'}
    with output.open('x') as f:json.dump(receipt,f,indent=2);f.write('\n')
    print(json.dumps({'status':'PASS','profiles':receipt['profiles'],'input_files':len(PATHS)}))

if __name__=='__main__':main()
