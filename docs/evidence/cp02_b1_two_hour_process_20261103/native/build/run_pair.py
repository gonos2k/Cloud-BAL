from __future__ import annotations
import argparse,hashlib,json,os,re,subprocess,time
from pathlib import Path

ROOT=Path('/var/tmp/b1-two-hour-probe-20261103')
MPI=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/bin/mpirun')
CPU={'OLD':[32,33,34,35,36,37,38,39],'FIX':[40,41,42,43,44,45,46,47]}
EXPECTED=[f'wrfout_d01_2026-08-16_{h:02d}:00:00' for h in (12,13,14)]

def sha(path:Path)->str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):
            h.update(b)
    return h.hexdigest()

def cpus(text:str)->set[int]:
    result=set()
    for part in text.strip().split(','):
        if '-' in part:
            lo,hi=map(int,part.split('-',1)); result.update(range(lo,hi+1))
        elif part: result.add(int(part))
    return result

def rank_affinities(case:Path, expected_exe:Path, proc_root:Path=Path('/proc'))->dict[str,list[int]]:
    case=case.resolve(); expected_exe=expected_exe.resolve(); found={}
    for entry in proc_root.iterdir():
        if not entry.name.isdigit(): continue
        try:
            if (entry/'cwd').resolve()!=case or (entry/'exe').resolve()!=expected_exe: continue
            status=(entry/'status').read_text()
            match=re.search(r'^Cpus_allowed_list:\s*(.+)$',status,re.M)
            if match: found[entry.name]=sorted(cpus(match.group(1)))
        except (OSError,PermissionError):
            continue
    return found

def main()->None:
    parser=argparse.ArgumentParser()
    parser.add_argument('--case',choices=('OLD','FIX'),required=True)
    parser.add_argument('--authorize-native',action='store_true')
    args=parser.parse_args()
    assert args.authorize_native and os.environ.get('B1_NATIVE_GO')=='ROOT_GO', 'native launch requires parent GO plus --authorize-native'
    plan=json.loads((ROOT/'case_plan.json').read_text())
    assert plan['status']=='PREPARED_NOT_RUN'
    arm=args.case; case=Path(plan['case_receipts'][arm]['path'])
    receipt_path=case/'launch_receipt.json'
    assert not receipt_path.exists(), f'refusing to overwrite prior launch receipt: {receipt_path}'
    before={name:sha(case/name) for name in plan['case_receipts'][arm]['input_files']}
    assert before==plan['case_receipts'][arm]['input_files']
    allowed=CPU[arm]; assert len(allowed)==8
    env=os.environ.copy()
    env.update(OMP_NUM_THREADS='1',OMP_DYNAMIC='FALSE',I_MPI_PIN='1',I_MPI_PIN_DOMAIN='core',I_MPI_PIN_RESPECT_CPUSET='1',I_MPI_PIN_PROCESSOR_LIST=','.join(map(str,allowed)))
    cmd=['taskset','--cpu-list',','.join(map(str,allowed)),str(MPI),'-np','8','./wrf.exe']
    start=time.time(); observed={}
    with (case/'launcher.log').open('xb') as log:
        proc=subprocess.Popen(cmd,cwd=case,env=env,stdout=log,stderr=subprocess.STDOUT)
        while proc.poll() is None:
            observed.update(rank_affinities(case,case/'wrf.exe'))
            time.sleep(0.2)
        exit_code=proc.returncode
    observed.update(rank_affinities(case,case/'wrf.exe'))
    log_text='\n'.join(p.read_text(errors='replace') for p in sorted(case.glob('rsl.out.*')))
    outputs=sorted(p.name for p in case.glob('wrfout*'))
    after={name:sha(case/name) for name in before}
    affinity_sets=list(observed.values())
    rank_count=len(observed)==8
    disjoint=rank_count and all(not(set(a)&set(b)) for ix,a in enumerate(affinity_sets) for b in affinity_sets[ix+1:])
    within=all(set(a)<=set(allowed) for a in affinity_sets)
    receipt={'status':'SUCCESS' if exit_code==0 and 'SUCCESS COMPLETE WRF' in log_text and outputs==EXPECTED and after==before and rank_count and disjoint and within else 'FAIL',
      'arm':arm,'argv':cmd,'exit':exit_code,'elapsed_seconds':time.time()-start,'process_scope':{'case_directory':str(case.resolve()),'expected_executable':str((case/'wrf.exe').resolve()),'filter':'rank PID cwd and resolved executable must both match this arm'},'success_marker':'SUCCESS COMPLETE WRF' in log_text,'history_files':outputs,'history_files_exact':outputs==EXPECTED,
      'staged_inputs_before':before,'staged_inputs_after':after,'staged_inputs_unchanged':before==after,
      'expected_cpus':allowed,'observed_rank_process_affinities':observed,'observed_rank_count':len(observed),'rank_count_exact':rank_count,'rank_affinities_pairwise_nonoverlapping':disjoint,'affinity_within_assigned_set':within,
      'trace_files':{p.name:sha(p) for p in sorted(case.glob('kdm6_trace_rank*.bits'))},'output_sha256':{name:sha(case/name) for name in outputs},
      'runtime_env':{k:env[k] for k in ('OMP_NUM_THREADS','OMP_DYNAMIC','I_MPI_PIN','I_MPI_PIN_DOMAIN','I_MPI_PIN_RESPECT_CPUSET','I_MPI_PIN_PROCESSOR_LIST')}}
    receipt_path.write_text(json.dumps(receipt,indent=2)+'\n')
    assert receipt['status']=='SUCCESS',json.dumps(receipt,indent=2)
if __name__=='__main__': main()
