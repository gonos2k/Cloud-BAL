#!/usr/bin/env python3
"""Run the frozen NN-end candidate only after independent launch review."""
import hashlib,importlib.util,json,os,subprocess,sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
RUNTIME=ROOT.parent/'runtime/nn_end'

def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def main():
    review_path=Path(sys.argv[1]);review=json.loads(review_path.read_text());plan_path=HERE/'launch_plan.json';plan=json.loads(plan_path.read_text());plan_sha=sha(plan_path)
    if review.get('status')!='GO_FOR_LAUNCH' or review.get('launch_plan_sha256')!=plan_sha:raise ValueError('launch review missing or mismatched')
    if plan.get('status')!='FROZEN_PRELAUNCH':raise ValueError('launch plan not frozen')
    for path,expected in plan['inputs_sha256'].items():
        if sha(path)!=expected:raise ValueError('frozen launch input changed: '+path)
    build_path=RUNTIME/'native_build/variants/MP10_NN_END/build_receipt.json';prepared_path=RUNTIME/'forecasts/MP10_NN_END/prepared.json'
    if plan['inputs_sha256'][str(build_path)]!=sha(build_path) or plan['inputs_sha256'][str(prepared_path)]!=sha(prepared_path):raise ValueError('build/prepared mismatch')
    spec=importlib.util.spec_from_file_location('nn_end_build',HERE/'build.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);env,_,_=module.load_profile()
    tmp=RUNTIME/'launch_tmp';tmp.mkdir(parents=True,exist_ok=False);env.update(TMPDIR=str(tmp),PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1');env['NETCDF']='/NHNHOME/WORKSPACE/26weather002_A/yhlee/KIM-meso/deps/netcdf-intel';env['LD_LIBRARY_PATH']=env['NETCDF']+'/lib:'+env.get('LD_LIBRARY_PATH','')
    cmd=[sys.executable,'-B',str(HERE/'forecast.py'),'run','MP10_NN_END'];process=subprocess.run(cmd,cwd=ROOT,env=env,check=False)
    unchanged=sha(plan_path)==plan_sha and all(sha(path)==expected for path,expected in plan['inputs_sha256'].items())
    passed=process.returncode==0 and unchanged
    result={'status':'PASS' if passed else 'FAIL','plan_sha256':plan_sha,'review_sha256':sha(review_path),'argv':cmd,'exit_code':process.returncode,'inputs_unchanged':unchanged}
    with (RUNTIME/'MP10_NN_END_driver_exit.json').open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    if not passed:raise RuntimeError('candidate forecast or frozen-input audit failed')
if __name__=='__main__':main()
