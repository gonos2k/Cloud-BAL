import hashlib,json,os,re,shutil,subprocess,sys,time
from pathlib import Path
R=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_thermo_cloud_path_20261105/runtime')
B=Path('/var/tmp/six-hour-improved-runtime-20261030/IMPROVED_BG_FIXED')
N=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_rain_number_process_20261104/runtime/next_candidate/full')
EXE=R/'build_cp04/FIX/wrf.exe'
EXPECTED_EXE=json.loads((R/'build_cp04_receipt.json').read_text())['arms']['FIX']['executable_sha256']
EXPECTED_NR='e6ed0750f88cb36e2600fd38c05e75513e8267dca72d9ee095cd5340a24ed175'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def prepare(kind,arm):
 assert sha(EXE)==EXPECTED_EXE==json.loads((R/'build_cp04_receipt.json').read_text())['arms']['FIX']['executable_sha256']
 source=B if arm=='B1' else N
 receipt=json.loads((B/'receipt.json').read_text())['staged_sha256_after'] if arm=='B1' else json.loads((N/'case_receipt.json').read_text())['inputs']
 assert len(receipt)==89
 assert all(sha(source/k)==v for k,v in receipt.items())
 dest=R/kind/arm;dest.mkdir(parents=True,exist_ok=False)
 for name in receipt: shutil.copy2(EXE if name=='wrf.exe' else source/name,dest/name)
 p=dest/'namelist.input'; t=p.read_text()
 controls=[('run_hours','0' if kind=='quick' else '2'),('end_hour','12' if kind=='quick' else '14'),('history_end_s','20' if kind=='quick' else '7200')]
 if kind=='quick':controls += [('run_minutes','0'),('run_seconds','20'),('end_minute','0'),('end_second','20')]
 for k,v in controls:
  t,n=re.subn(r'(?m)^(\s*'+k+r'\s*=\s*)[^,\n]+',lambda m:m.group(1)+v,t);assert n==1,(k,n)
 p.write_text(t)
 assert re.search(r'(?m)^\s*time_step\s*=\s*20\s*,?\s*$',t)
 hashes={n:sha(dest/n) for n in receipt}
 assert all(hashes[n]==receipt[n] for n in receipt if n not in ('wrf.exe','namelist.input'))
 assert hashes['wrfinput_d01']==('9f8b494dbf5ce765e4320701475d6a65be1f591d72a4f9bf5e929c208be563e5' if arm=='B1' else EXPECTED_NR)
 (dest/'case_receipt.json').write_text(json.dumps({'source':str(source),'source_hashes':receipt,'inputs':hashes,'controls':controls},indent=2)+'\n')
def run(kind,arm):
 assert sha(EXE)==EXPECTED_EXE==json.loads((R/'build_cp04_receipt.json').read_text())['arms']['FIX']['executable_sha256']
 d=R/kind/arm;rc=json.loads((d/'case_receipt.json').read_text());before={n:sha(d/n) for n in rc['inputs']};assert before==rc['inputs']
 cpus=list(range(48,56) if arm=='B1' else range(56,64));env=os.environ.copy();env.update(OMP_NUM_THREADS='1',OMP_DYNAMIC='FALSE',I_MPI_PIN='1',I_MPI_PIN_DOMAIN='core',I_MPI_PIN_RESPECT_CPUSET='1',I_MPI_PIN_PROCESSOR_LIST=','.join(map(str,cpus)))
 cmd=['taskset','-c',','.join(map(str,cpus)),'/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/bin/mpirun','-np','8','./wrf.exe'];start=time.time()
 with (d/'launcher.log').open('xb') as f:
  p=subprocess.Popen(cmd,cwd=d,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
  cap=False
  while p.poll() is None:
   size=sum(x.stat().st_size for pattern in ('state_*.bin','kdm6_trace_rank*.bits','cp04_rank*.bin','surface_cp04_rank*.bin') for x in d.glob(pattern))
   if size>50*1024**3:
    import signal
    os.killpg(p.pid,signal.SIGTERM);cap=True;break
   time.sleep(2)
  exitcode=p.wait()
 after={n:sha(d/n) for n in before};log=''.join(p.read_text(errors='replace') for p in d.glob('rsl.out.*'));out=sorted(p.name for p in d.glob('wrfout*'))
 wanted=[f'wrfout_d01_2026-08-16_{x:02}:00:00' for x in (range(12,13) if kind=='quick' else range(12,15))]
 result={'exit':exitcode,'capture_cap_reached':cap,'success_marker':'SUCCESS COMPLETE WRF' in log,'history':out,'expected_history':wanted,'inputs_unchanged':after==before,'inputs_after':after,'argv':cmd,'elapsed_seconds':time.time()-start,'cpus':cpus}
 reference=B if arm=='B1' else N
 history_comparisons={n:{'actual_sha256':sha(d/n),'reference_sha256':sha(reference/n)} for n in out if (reference/n).is_file()}
 result['history_comparisons']=history_comparisons
 result['history_byte_parity']=len(history_comparisons)==len(wanted) and all(v['actual_sha256']==v['reference_sha256'] for v in history_comparisons.values())
 result['status']='PASS' if exitcode==0 and not cap and result['success_marker'] and out==wanted and after==before and result['history_byte_parity'] else 'FAIL';(d/'launch_receipt.json').write_text(json.dumps(result,indent=2)+'\n');print(kind,arm,result['status'],flush=True);assert result['status']=='PASS'
if __name__=='__main__':
 action,kind,arm=sys.argv[1:]; {'prepare':prepare,'run':run}[action](kind,arm)
