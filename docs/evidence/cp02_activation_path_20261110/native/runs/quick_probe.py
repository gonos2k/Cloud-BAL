#!/usr/bin/env python3
"""Run three timesteps per arm and gate framed diagnostic integrity before the full run."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import sys

NATIVE = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[5]
RUNTIME = ROOT.parent / 'runtime'


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module; spec.loader.exec_module(module)
    return module


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('arm', choices=('CONTROL','MP10')); ap.add_argument('review', type=Path); args = ap.parse_args()
    review = json.loads(args.review.read_text())
    checks = [NATIVE / 'runs/quick_probe.py', NATIVE / 'runs/validate_probe.py', NATIVE / 'runs/read_frames.py', NATIVE / 'runs/forecast.py', NATIVE / 'runs/rank_wrapper.sh',
              NATIVE / 'schema/schema.json', NATIVE / 'source/source_receipt.json', ROOT / 'docs/evidence/cp02_activation_path_20261110/cohorts/native_columns.csv',
              ROOT / 'docs/evidence/cp02_protected_process_20261106/native/provenance/collector_v5/cp02_protected_process_capture.py']
    if review.get('status') != 'GO_FOR_PROBE' or any(review.get('sha256', {}).get(str(p.relative_to(ROOT))) != sha(p) for p in checks):
        raise ValueError('probe review does not bind current recipe and source')
    build_receipt = RUNTIME / f'native_build/variants/{args.arm}/build_receipt.json'
    if review.get('build_receipt_sha256', {}).get(args.arm) != sha(build_receipt):
        raise ValueError('probe review does not bind build receipt')
    build = json.loads(build_receipt.read_text()); assert build['status'] == 'PASS'
    f = load(NATIVE/'runs/forecast.py','probe_forecast')
    input_hashes = f.input_map('A'); f.verify_inputs(f.SOURCES['A'],input_hashes)
    destination = RUNTIME/'probe'/args.arm; destination.mkdir(parents=True, exist_ok=False)
    exe = Path(build['executable']['path']); assert sha(exe) == build['executable']['sha256']
    for name in input_hashes:
        shutil.copy2(exe if name=='wrf.exe' else f.SOURCES['A']/name, destination/name)
    namelist = destination/'namelist.input'; text = namelist.read_text(); f.validate_namelist(text)
    for key, value in [('run_hours',2),('run_seconds',20),('end_hour',14),('end_minute',0),('end_second',20),('history_end_s',7220)]:
        text, n = re.subn(r'(?im)^(\s*'+key+r'\s*=\s*)\d+(\s*,?\s*)$',lambda m:m.group(1)+str(value)+m.group(2),text)
        if n != 1: raise ValueError('probe namelist key missing or ambiguous: '+key)
    namelist.write_text(text)
    module = load(NATIVE/'build/build.py','probe_build'); env,_,_ = module.load_profile()
    cpus = f.CASES[args.arm][2]; cpulist = ','.join(map(str,cpus))
    env.update(OMP_NUM_THREADS='1',OMP_DYNAMIC='FALSE',MKL_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',I_MPI_PIN='1',I_MPI_PIN_DOMAIN='core',I_MPI_PIN_RESPECT_CPUSET='1',I_MPI_PIN_PROCESSOR_LIST=cpulist,GROUPED_CPUS=cpulist,GROUPED_PYTHON=sys.executable)
    env['NETCDF']='/NHNHOME/WORKSPACE/26weather002_A/yhlee/KIM-meso/deps/netcdf-intel'; env['LD_LIBRARY_PATH']=env['NETCDF']+'/lib:'+env.get('LD_LIBRARY_PATH','')
    import resource
    resource.setrlimit(resource.RLIMIT_STACK,(resource.RLIM_INFINITY,resource.RLIM_INFINITY))
    command=['taskset','-c',cpulist,str(f.MPI),'-np','8','/bin/bash',str(NATIVE/'runs/rank_wrapper.sh')]
    seen={}; error=None; code=None; start=time.monotonic()
    with (destination/'launcher.log').open('xb') as log:
        process=subprocess.Popen(command,cwd=destination,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try:
            while True:
                f.observe_descendants(process.pid,seen)
                try:
                    code=process.wait(timeout=2); break
                except subprocess.TimeoutExpired:
                    if time.monotonic()-start>3600: raise TimeoutError('probe timeout')
        except BaseException as exc:
            error=repr(exc); f.stop_owned(process,seen)
    survivors=f.surviving_descendants(seen)
    if survivors:
        f.stop_owned(process,seen); survivors=f.surviving_descendants(seen)
    if error or survivors: raise RuntimeError(f'probe interrupted or descendants survive: {error}, {survivors}')
    if code != 0: raise RuntimeError(f'probe model failed: {code}')
    logs=sorted(destination.glob('rsl.out.*'))
    if len(logs)!=8 or not all('SUCCESS COMPLETE WRF' in p.read_text(errors='replace') for p in logs): raise ValueError('probe missing rank success markers')
    proof=subprocess.run([sys.executable,str(NATIVE/'runs/validate_probe.py'),args.arm,str(destination)],check=False)
    if proof.returncode: raise RuntimeError('probe diagnostic validation failed')
    output={'status':'PASS','arm':args.arm,'steps':[361],'review_sha256':sha(args.review),'build_receipt_sha256':sha(build_receipt), 'namelist_sha256':sha(namelist),'launcher_sha256':sha(destination/'launcher.log'),'capture_validation_sha256':sha(destination/'probe_validation.json'),'argv':command}
    with (destination/'probe_receipt.json').open('x') as stream: json.dump(output,stream,indent=2); stream.write('\n')


if __name__=='__main__': main()
