from pathlib import Path
import hashlib,json,os,shutil,subprocess,time
R=Path('/var/tmp/firsthour-runtime-plan-20261030/producer_pair');root=R/'forecast'; d=root/'run_POLICY_BG';ref=Path('/var/tmp/firsthour-runtime-plan-20261030/experiment/run_FIX_H'); native=R/'native_HYDRO_BACKGROUND_PRECIP'; case=R/'run_HYDRO_BACKGROUND_PRECIP'; checker=Path('/var/tmp/cloudbal-first-hour-improvement/tools/check_background_precip_shadow.py')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
reference=json.loads((ref/'inputs.json').read_text())['staged'];refrec=json.loads((ref/'receipt.json').read_text());assert refrec['exit']==0 and all(refrec[k] for k in ('success_marker','histories_exact','staged_unchanged','source_unchanged'));assert len(reference)==89
assert reference['wrf.exe']=='68ed2833b5f207d037949c9b20c7c2f800500e632f911a4acf1eb09d13bf1c1f' and reference['namelist.input']=='23f5c3cb94d44831c22d86a754fa30d242456d8d14cd70a72d89b00cdec4f3a3' and reference['wrfbdy_d01']=='74102ac2063f17a9007f3352e6e6c2f52629055bdf3f05b4f4d6d77aef835f45' and reference['wrfinput_d01']=='7fd13466f8e19d0f8d88ce0499bcb249aa9803bb8ad7df9eee39c757bc315126'
original={n:sha(ref/n) for n in reference};assert original==reference
product=native/'real/wrfinput_d01';expected='9f8b494dbf5ce765e4320701475d6a65be1f591d72a4f9bf5e929c208be563e5';assert sha(product)==expected
p=json.loads((case/'receipt.json').read_text());n=json.loads((native/'receipt.json').read_text());s=json.loads((R/'policy_scoped_check.json').read_text());build=json.loads((R/'build_receipt.json').read_text());assert p['exit']==0 and p['staged_unchanged'] and p['source_unchanged'] and n['wrfinput_sha256']==expected and n['metgrid_inputs_unchanged'] and n['real_inputs_unchanged'] and n['source_unchanged'] and s['status']=='PASS_SCOPED_BACKGROUND_PRECIPITATION' and s['shadow_sha256']==p['output_sha256']['output.wps.shadow.nc'] and p['executable_sha256']==build['executable_sha256'];assert sha(checker)=='17ee6d5e23925e34b9fdc881d3e1c81a27ef60f832cb4702b8dd0247a0825abd'==build['checker_sha256']
bind_paths=[ref/'inputs.json',ref/'receipt.json',product,case/'receipt.json',case/'output.wps.shadow.nc',native/'receipt.json',R/'build_receipt.json',R/'policy_scoped_check.json',checker];bindings={str(x):sha(x) for x in bind_paths}
assert not d.exists();d.mkdir()
for name in reference:
 shutil.copy2(product if name=='wrfinput_d01' else ref/name,d/name)
staged={n:sha(d/n) for n in reference};assert staged['wrfinput_d01']==expected and all(staged[n]==reference[n] for n in reference if n!='wrfinput_d01');assert {n:sha(ref/n) for n in reference}==original and {str(p):sha(p) for p in bind_paths}==bindings
(d/'inputs.json').write_text(json.dumps({'staged':staged,'source_before':original,'source_after':original,'reference_case':str(ref),'candidate_native_input':str(product),'evidence_before':bindings,'input_count':len(staged)},indent=2)+'\n')
env=os.environ.copy();env.update(OMP_NUM_THREADS='1',OMP_DYNAMIC='FALSE');cmd=['/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/bin/mpirun','-np','8',str(d/'wrf.exe')];t=time.time()
try:
 with (d/'launcher.log').open('xb') as f:status=subprocess.run(cmd,cwd=d,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=2400).returncode
except subprocess.TimeoutExpired:status='TIMEOUT'
outputs=sorted(x.name for x in d.glob('wrfout*'));expected_outputs=['wrfout_d01_2026-08-16_12:00:00','wrfout_d01_2026-08-16_13:00:00'];log=(d/'rsl.out.0000').read_text(errors='replace') if (d/'rsl.out.0000').exists() else ''
rec={'exit':status,'argv':cmd,'elapsed_seconds':time.time()-t,'success_marker':'SUCCESS COMPLETE WRF' in log,'histories':outputs,'histories_exact':outputs==expected_outputs,'staged_unchanged':{n:sha(d/n) for n in staged}==staged,'source_unchanged':{n:sha(ref/n) for n in original}==original,'evidence_unchanged':{str(p):sha(p) for p in bind_paths}==bindings,'output_sha256':{name:sha(d/name) for name in outputs},'evidence_before':bindings,'policy':'HYDRO_BACKGROUND_PRECIP','scope':'diagnostic research forecast; not operational'}
(d/'receipt.json').write_text(json.dumps(rec,indent=2)+'\n');assert status==0 and all(rec[k] for k in ('success_marker','histories_exact','staged_unchanged','source_unchanged','evidence_unchanged')),rec
