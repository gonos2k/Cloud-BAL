#!/usr/bin/env python3
"""Run one 20-second full-scheme diagnostic and check native NN bound timing."""
import hashlib,importlib.util,json,os,re,resource,shutil,subprocess,sys,time
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
RUNTIME=ROOT.parent/'runtime/nn_end'

def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module);return module

def main():
    review_path=Path(sys.argv[1]);review=json.loads(review_path.read_text());build=RUNTIME/'native_build/variants/MP10_NN_END_PROBE/build_receipt.json'
    artifacts=[HERE/'probe.py',HERE/'forecast.py',HERE/'rank_wrapper.sh',HERE/'source/probe_source_receipt.json',HERE/'policy.json',HERE/'build_probe.py']
    if review['status']!='GO_FOR_PROBE' or any(review['sha256'].get(str(p.relative_to(ROOT)))!=sha(p) for p in artifacts) or review['build_receipt_sha256']!=sha(build):raise ValueError('probe review does not bind current inputs')
    b=json.loads(build.read_text());assert b['status']=='PASS';f=load(HERE/'forecast.py','nn_end_forecast'); hashes=f.input_map('A');f.verify_inputs(f.SOURCES['A'],hashes)
    out=RUNTIME/'probe';out.mkdir(parents=True,exist_ok=False);exe=Path(b['executable']['path']);assert sha(exe)==b['executable']['sha256']
    for name in hashes:shutil.copy2(exe if name=='wrf.exe' else f.SOURCES['A']/name,out/name)
    namelist=out/'namelist.input';text=namelist.read_text();f.validate_namelist(text)
    for key,value in [('run_hours',0),('run_seconds',20),('end_hour',12),('end_minute',0),('end_second',20),('history_end_s',20)]:
        text,n=re.subn(r'(?im)^(\s*'+key+r'\s*=\s*)\d+(\s*,?\s*)$',lambda m:m.group(1)+str(value)+m.group(2),text)
        if n!=1:raise ValueError('namelist field differs: '+key)
    namelist.write_text(text)
    module=load(HERE/'build_probe.py','nn_end_probe_build');env,_,_=module.load_profile();cpus=f.CASES['MP10_NN_END'][2];cpulist=','.join(map(str,cpus))
    env.update(OMP_NUM_THREADS='1',OMP_DYNAMIC='FALSE',MKL_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',I_MPI_PIN='1',I_MPI_PIN_DOMAIN='core',I_MPI_PIN_RESPECT_CPUSET='1',I_MPI_PIN_PROCESSOR_LIST=cpulist,GROUPED_CPUS=cpulist,GROUPED_PYTHON=sys.executable)
    env['NETCDF']='/NHNHOME/WORKSPACE/26weather002_A/yhlee/KIM-meso/deps/netcdf-intel';env['LD_LIBRARY_PATH']=env['NETCDF']+'/lib:'+env.get('LD_LIBRARY_PATH','')
    resource.setrlimit(resource.RLIMIT_STACK,(resource.RLIM_INFINITY,resource.RLIM_INFINITY));cmd=['taskset','-c',cpulist,str(f.MPI),'-np','8','/bin/bash',str(HERE/'rank_wrapper.sh')]
    seen={};error=None;code=None;start=time.monotonic()
    with (out/'launcher.log').open('xb') as log:
        process=subprocess.Popen(cmd,cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try:
            while True:
                f.observe_descendants(process.pid,seen)
                try:code=process.wait(timeout=2);break
                except subprocess.TimeoutExpired:
                    if time.monotonic()-start>1200:raise TimeoutError('probe timeout')
        except BaseException as exc:error=repr(exc);f.stop_owned(process,seen)
    survivors=f.surviving_descendants(seen)
    if survivors:f.stop_owned(process,seen);survivors=f.surviving_descendants(seen)
    if error or survivors or code!=0:raise RuntimeError(f'probe failed: {error} {survivors} {code}')
    logs=sorted(out.glob('rsl.out.*'))
    if len(logs)!=8 or not all('SUCCESS COMPLETE WRF' in p.read_text(errors='replace') for p in logs):raise ValueError('missing WRF success markers')
    traces=[]
    for path in logs:
        for line in path.read_text(errors='replace').splitlines():
            match=re.search(r'NN_END_TRACE\s+(ENTRY_PRE|ENTRY_POST|LOOP_PRE|LOOP_POST)\s+(.+)$',line)
            if match:traces.append((match.group(1),*[int(x) for x in match.group(2).split()]))
    if [x[0] for x in traces]!=['ENTRY_PRE','ENTRY_POST','LOOP_PRE','LOOP_POST','LOOP_PRE','LOOP_POST']:raise ValueError(f'unexpected trace: {traces}')
    def f32(word):return np.array([word],dtype=np.int32).view(np.float32)[0]
    if f32(traces[1][1])!=np.minimum(np.maximum(f32(traces[0][1]),np.float32(1e8)),np.float32(2e10)):raise ValueError('entry clamp mismatch')
    for loop in (1,2):
        a,b=traces[2*loop],traces[2*loop+1]
        if a[1:4]!=b[1:4] or a[1:3]!=(loop,2) or f32(a[3])!=10:raise ValueError('actual timing/loop differs')
        expected=np.minimum(np.maximum(f32(a[4]),np.float32(1e8)) if loop==2 else f32(a[4]),np.float32(2e10))
        if f32(b[4])!=expected:raise ValueError('candidate bound result differs')
    result={'status':'PASS','review_sha256':sha(review_path),'build_receipt_sha256':sha(build),'cell_ijk':[156,86,14],'model_call_seconds':20,'actual_loops':2,'actual_dtcld_seconds':10,'trace_words':traces,'entry_lower_bound_applications':1,'inner_lower_bound_applications':1,'inner_upper_bound_applications':2,'scope':'one full KDM6 diagnostic cell and one 20-second WRF call; policy counts are observed loop/branch timing, not a domain budget','logs':{p.name:sha(p) for p in logs},'launcher_sha256':sha(out/'launcher.log'),'namelist_sha256':sha(namelist)}
    (out/'probe_receipt.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
