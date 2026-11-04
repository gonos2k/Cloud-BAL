import hashlib,json
from pathlib import Path
R=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_rain_number_process_20261104/runtime')
refs={'B1':Path('/var/tmp/six-hour-improved-runtime-20261030/IMPROVED_BG_FIXED'),'NR_PRIOR':Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_state_path_20261104/runtime/B1_RAIN_NUMBER_PRIOR_6H')}
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
source=R.parent/'Cloud-BAL/docs/evidence/cp02_rain_number_process_20261104/native/source/module_mp_kdm6_FIX.f90'
assert sha(source)=='605b2d6895229f287dd6dc675b84dea0596f7a247a18bf80e3615635defb0295'
assert sha(R/'build_cp03/FIX/wrf.exe')=='728bd543a47dcd78ac0b0ceff6ceceedc84ae502332658537c6310ff7543de46'
checks=[]
for arm,ref in refs.items():
 d=R/'runs'/arm;rc=json.loads((d/'launch_receipt.json').read_text());assert rc['status']=='PASS' and rc['inputs_unchanged'] and len(rc['inputs_after'])==89
 assert sha(d/'wrf.exe')=='728bd543a47dcd78ac0b0ceff6ceceedc84ae502332658537c6310ff7543de46'
 for hour in range(12,16):
  name=f'wrfout_d01_2026-08-16_{hour:02}:00:00';a,b=sha(d/name),sha(ref/name);checks.append({'arm':arm,'hour_utc':hour,'diagnostic_sha256':a,'reference_sha256':b,'identical':a==b});print(arm,hour,a==b,flush=True)
receipt={'status':'PASS' if all(x['identical'] for x in checks) else 'FAIL','checks':checks,'comparison':'whole-file SHA-256; reference same-arm standard six-hour run'}
(R/'runs/history_byte_comparison.json').write_text(json.dumps(receipt,indent=2)+'\n');assert receipt['status']=='PASS'
