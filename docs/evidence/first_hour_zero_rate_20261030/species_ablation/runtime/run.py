from pathlib import Path
import hashlib,json,os,subprocess,sys,time
r=Path('/var/tmp/firsthour-runtime-plan-20261030/species_ablation'); d=r/('run_'+sys.argv[1]); i=json.loads((d/'inputs.json').read_text()); staging=i['all_staged_input_hashes']
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
assert not (d/'launcher.log').exists() and not (d/'receipt.json').exists()
assert {n:sha(d/n) for n in staging}==staging
pbase=Path(i['base']);pdonor=Path(i['donor']);assert sha(pbase)==i['base_sha256'] and sha(pdonor)==i['donor_sha256']
prior=Path(i['prior_case']);prior_hash=json.loads((prior/'inputs.json').read_text())['staged'];assert {n:sha(prior/n) for n in prior_hash}==prior_hash
expected=['wrfout_d01_2026-08-16_12:00:00','wrfout_d01_2026-08-16_13:00:00'];env=os.environ.copy();env.update(OMP_NUM_THREADS='1',OMP_DYNAMIC='FALSE');start=time.time();status=None
try:
 with (d/'launcher.log').open('wb') as log:
  status=subprocess.run(['/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/bin/mpirun','-np','8',str(d/'wrf.exe')],cwd=d,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=2400).returncode
except subprocess.TimeoutExpired:status='TIMEOUT'
hist=sorted(p.name for p in d.glob('wrfout*'));log=(d/'rsl.out.0000').read_text(errors='replace') if (d/'rsl.out.0000').is_file() else ''
rec={'exit':status,'elapsed_seconds':time.time()-start,'success_marker':'SUCCESS COMPLETE WRF' in log,'histories':hist,'histories_exact':hist==expected,'staged_unchanged':{n:sha(d/n) for n in staging}==staging,'source_unchanged':sha(pbase)==i['base_sha256'] and sha(pdonor)==i['donor_sha256'] and {n:sha(prior/n) for n in prior_hash}==prior_hash,'output_sha256':{n:sha(d/n) for n in hist}}
(d/'receipt.json').write_text(json.dumps(rec,indent=2)+'\n');assert rec['exit']==0 and all(rec[k] for k in ('success_marker','histories_exact','staged_unchanged','source_unchanged')),rec
