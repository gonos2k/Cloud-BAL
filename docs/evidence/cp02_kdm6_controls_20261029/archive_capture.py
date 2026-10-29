import pathlib,json,hashlib,gzip,shutil,sys
root=pathlib.Path('/var/tmp/cloudbal-cp02-kdm6-controls'); e=root/'docs/evidence/cp02_kdm6_controls_20261029'
s=pathlib.Path('/var/tmp/cp02_controls_scratch_path').read_text(); s=pathlib.Path(s)
arm=sys.argv[1]; d=s/arm; out=e/'captures'/arm; out.mkdir(parents=True,exist_ok=True)
def sha(p):
 with open(p,'rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()
def pin(p):return {'sha256':sha(p),'size_bytes':p.stat().st_size}
m=json.loads((e/'inputs/copy_manifest.json').read_text()); a=m['arms'][arm]
assert sha(s/'capture_kdm6.gdb')==sha(e/'capture_kdm6.gdb')
assert not list((d/'capture').glob('*.failed.json'))
files=sorted((d/'capture').glob('capture_rank*_pid*.json')); assert len(files)==8
ranks=[]; captures=[]
for f in files:
 raw=f.read_bytes(); rec=json.loads(raw); assert rec['status']=='two_calls_returned' and len(rec['calls'])==2 and all(c['return'] for c in rec['calls'])
 ranks.append({'rank':int(rec['rank']),'calls':2,'status':rec['status'],'steps':[c['entry']['observed_itimestep'] for c in rec['calls']],'dts':[c['entry']['observed_dt'] for c in rec['calls']]})
 p=out/(f.name+'.gz'); p.write_bytes(gzip.compress(raw,mtime=0)); captures.append({'path':str(p.relative_to(root)),**pin(p),'uncompressed_sha256':hashlib.sha256(raw).hexdigest(),'uncompressed_size_bytes':len(raw)})
assert sorted(r['rank'] for r in ranks)==list(range(8))
for f in a['copy_files']:
 assert pin(pathlib.Path(f['source_path']))=={'sha256':f['sha256'],'size_bytes':f['size_bytes']}
 assert pin(d/'run'/f['destination_name'])=={'sha256':f['sha256'],'size_bytes':f['size_bytes']}
for f in (d/'capture').glob('*.txt'):shutil.copy2(f,out/f.name)
for f in (d/'run').glob('rsl.*'):shutil.copy2(f,out/(f.name+'.txt'))
for name in ['launch.sh','rank_wrapper.sh','launcher.txt','launcher.exit']:shutil.copy2(d/name,out/name)
runtime={}; unavailable=set()
for maps in (d/'capture').glob('maps*.txt'):
 for line in maps.read_text().splitlines():
  bits=line.split(maxsplit=5)
  if len(bits)==6 and bits[5].startswith('/'):
   p=pathlib.Path(bits[5])
   if p.is_file(): runtime[str(p)]=pin(p)
   else: unavailable.add(bits[5])
h=d/'run/wrfout_d01_2026-08-16_12:00:00'; old=pathlib.Path(a['source_run_directory'])/h.name
binary=pin(s/'wrf.exe'); assert binary['sha256']=='de110a7f1d40143a74ffedbe64ed5b3717c413876093f56d200563e2f6b9c168'
rc=int((d/'launcher.exit').read_text()); assert rc not in (124,137)
receipt={'status':'TWO_CALLS_CAPTURED_INTENTIONAL_STOP','forecast_status':'NOT_COMPLETED','arm':arm,'ranks':8,'omp_threads':1,'launcher_exit':rc,'termination':'GDB quit after two KDM6 returns from each rank; intentional diagnostic stop, not forecast completion','binary':{'path':str(s/'wrf.exe'),**binary},'script_sha256':sha(s/'capture_kdm6.gdb'),'profile_sha256':sha(root/'tests/intel_toolchain.sh'),'selection_sha256':sha(s/'selection.json'),'copy_manifest_sha256':sha(e/'inputs/copy_manifest.json'),'selected_points':624,'input_files_unchanged':88,'original_input_files_unchanged':88,'initial_history':{'path':str(h),'size_bytes':h.stat().st_size,'sha256':sha(h),'archived_sha256':sha(old),'byte_identical':sha(h)==sha(old)},'runtime_mapped_files':runtime,'unavailable_mappings':sorted(unavailable),'captures':captures,'rank_status':sorted(ranks,key=lambda x:x['rank'])}
(out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(arm,rc,'initialsame',receipt['initial_history']['byte_identical'],'steps',[r['steps'] for r in ranks],'runtime',len(runtime))
