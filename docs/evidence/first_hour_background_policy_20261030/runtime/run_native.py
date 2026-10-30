from pathlib import Path
import hashlib,json,os,shutil,subprocess,sys,time
R=Path('/var/tmp/firsthour-runtime-plan-20261030/producer_pair');mode=sys.argv[1];assert mode in ('HYDRO','HYDRO_BACKGROUND_PRECIP');case=R/('run_'+mode);pr=json.loads((case/'receipt.json').read_text());assert pr['exit']==0 and pr['source_unchanged'] and pr['staged_unchanged'];out=case/'output.wps'
P=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/current_forecast_paper_20261029/run.PomEr8/native_HYDRO');WS=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50');metexe=WS/'Cloud-BAL/scratch/cp02_native_12_15.B4Lwmh/metgrid/metgrid.exe';realexe=WS/'Cloud-BAL/scratch/cp02_host_process_domain_fm547n5i/host/main/real.exe'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def records(path):
 d={}
 for line in path.read_text().splitlines():
  h,name=line.split('  ',1);assert name.startswith('./');d[name[2:]]=h
 return d
def inv(p):return {str(x.relative_to(p)):sha(x) for x in sorted(p.rglob('*')) if x.is_file()}
def run(cmd,cwd,log):
 t=time.time()
 try:
  with log.open('xb') as f:status=subprocess.run(cmd,cwd=cwd,stdout=f,stderr=subprocess.STDOUT,timeout=1200).returncode
 except subprocess.TimeoutExpired:status='TIMEOUT'
 return {'argv':cmd,'exit':status,'elapsed_seconds':time.time()-t}
assert sha(out)==pr['output_sha256']['output.wps'];assert sha(metexe)=='3107306ad0f8702e818eb84d8d4f9c96561b3632ffbaf2b157b5e284e1a18afe';assert sha(realexe)=='58118b30f35f1e817cd500fc0047ee3e0b334975a3231faf3a46b3a5728c5c10'
d=R/('native_'+mode);assert not d.exists();d.mkdir();m=d/'metgrid';m.mkdir();x=d/'real';x.mkdir();(d/'tmp').mkdir();os.environ['TMPDIR']=str(d/'tmp')
inputs=records(P/'metgrid_inputs.sha256');original={};
for name,h in inputs.items():
 if name.startswith('LAPS:'):continue
 source=P/'metgrid'/name;assert sha(source)==h,name;original[str(source)]=h;shutil.copy2(source,m/name)
shutil.copy2(out,m/'LAPS:2026-08-16_12:00');shutil.copy2(metexe,m/'metgrid.exe');mbefore=inv(m);(d/'metgrid_inputs.json').write_text(json.dumps(mbefore,indent=2)+'\n');q=run([str(m/'metgrid.exe')],m,d/'metgrid.log');output=m/'met_em.d01.2026-08-16_12:00:00.nc'; assert q['exit']==0 and output.is_file() and 'Successful completion of metgrid.' in (d/'metgrid.log').read_text(errors='replace'),q
mafter={k:sha(m/k) for k in mbefore};assert mbefore==mafter
inputs2=records(P/'real_inputs.sha256');
for name,h in inputs2.items():
 if name=='met_em.d01.2026-08-16_12:00:00.nc':continue
 source=P/'real'/name;assert sha(source)==h,name;original[str(source)]=h;shutil.copy2(source,x/name)
shutil.copy2(output,x/'met_em.d01.2026-08-16_12:00:00.nc'); assert sha(x/'real.exe')==sha(realexe);rbefore=inv(x);(d/'real_inputs.json').write_text(json.dumps(rbefore,indent=2)+'\n');q2=run([str(x/'real.exe')],x,d/'real.log');rsl=x/'rsl.out.0000'; product=x/'wrfinput_d01'; assert q2['exit']==0 and product.is_file() and rsl.exists() and 'SUCCESS COMPLETE REAL_EM INIT' in rsl.read_text(errors='replace'),q2
rafter={k:sha(x/k) for k in rbefore};source_after={p:sha(Path(p)) for p in original};rec={'mode':mode,'producer_receipt_sha256':sha(case/'receipt.json'),'producer_wps_sha256':sha(out),'metgrid':q,'real':q2,'metgrid_inputs_unchanged':mbefore==mafter,'real_inputs_unchanged':rbefore==rafter,'source_unchanged':source_after==original,'source_before':original,'source_after':source_after,'met_em_sha256':sha(output),'wrfinput_sha256':sha(product)};(d/'receipt.json').write_text(json.dumps(rec,indent=2)+'\n');assert rec['metgrid_inputs_unchanged'] and rec['real_inputs_unchanged'] and rec['source_unchanged'],rec
