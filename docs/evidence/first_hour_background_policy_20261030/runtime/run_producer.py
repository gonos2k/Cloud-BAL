from pathlib import Path
import os,hashlib,json,subprocess,sys,time
r=Path('/var/tmp/firsthour-runtime-plan-20261030/producer_pair'); mode=sys.argv[1];assert mode in ('HYDRO','HYDRO_BACKGROUND_PRECIP');d=r/('run_'+mode);prep=json.loads((d/'preparation.json').read_text());src=Path(prep['source']);exe=Path(sys.argv[2]).resolve();build=exe.parent

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def inv(p):
 x={}
 for f in sorted(p.rglob('*')):
  if f.is_symlink():raise RuntimeError('unexpected symlink '+str(f))
  if f.is_file():x[str(f.relative_to(p))]=sha(f)
  elif not f.is_dir():raise RuntimeError('unexpected input type '+str(f))
 return x
assert not (d/'receipt.json').exists();before=inv(d/'input');assert before==prep['staged_before'] and inv(src)==prep['source_before'];exe_hash=sha(exe); shell=build/'run_verified.sh';assert shell.is_file()
for n in ['inputs.sha256','runtime.sha256','executable.sha256']:
 subprocess.run(['sha256sum','-c',str(build/n)],check=True,stdout=subprocess.DEVNULL)
env=os.environ.copy();env.update(OMP_NUM_THREADS='1',OMP_DYNAMIC='FALSE',OMP_STACKSIZE='128M',LANG='C',LAPS_DATA_ROOT=str(d/'input'),TMPDIR=str(d/'work'),CLOUD_BAL_WPS_OUTPUT=str(d/'output.wps'),CLOUD_BAL_SHADOW_EXPERIMENT=mode);env.pop('CLOUD_BAL_STAGE_MODE',None);env.pop('CLOUD_BAL_STAGE_CONTEXT',None)
cmd=[str(shell),'262281200'];t=time.time();rc=None
try:
 with (d/'lapsprep.log').open('xb') as f:rc=subprocess.run(cmd,cwd=d/'work',env=env,stdout=f,stderr=subprocess.STDOUT,timeout=1200).returncode
except subprocess.TimeoutExpired:rc='TIMEOUT'
after=inv(d/'input');origafter=inv(src);diff=sorted(k for k in before.keys()|after.keys() if before.get(k)!=after.get(k));outputs={p.name:sha(p) for p in [d/'output.wps',d/'output.wps.shadow.nc'] if p.is_file()}; checks={}
for n in ['inputs.sha256','runtime.sha256','executable.sha256']:
 q=subprocess.run(['sha256sum','-c',str(build/n)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);checks[n]=q.returncode==0
receipt={'mode':mode,'argv':cmd,'executable':str(exe),'executable_sha256':exe_hash,'elapsed_seconds':time.time()-t,'exit':rc,'input_count':len(before),'input_hashes_before':before,'input_hashes_after':after,'staged_unchanged':before==after,'source_unchanged':origafter==prep['source_before'],'changed_input_paths':diff,'build_manifest_postchecks':checks,'output_sha256':outputs,'environment_controls':{'CLOUD_BAL_SHADOW_EXPERIMENT':mode,'CLOUD_BAL_STAGE_MODE':'unset','CLOUD_BAL_STAGE_CONTEXT':'unset','OMP_NUM_THREADS':'1','OMP_DYNAMIC':'FALSE','OMP_STACKSIZE':'128M','LANG':'C'}}
(d/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');assert rc==0 and receipt['staged_unchanged'] and receipt['source_unchanged'] and all(checks.values()) and len(outputs)==2,receipt
