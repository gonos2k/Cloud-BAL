import hashlib,json,shutil
from pathlib import Path
ROOT=Path('/var/tmp/b1-two-hour-probe-20261103')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
p=ROOT/'case_plan.json'; plan=json.loads(p.read_text())
for arm,build_arm in [('OLD','BASE'),('FIX','FIX')]:
 case=Path(plan['case_receipts'][arm]['path'])
 exe=ROOT/'build'/build_arm/'wrf.exe'
 shutil.copy2(exe,case/'wrf.exe')
 plan['case_receipts'][arm]['input_files']['wrf.exe']=sha(case/'wrf.exe')
 plan['case_receipts'][arm]['executable_sha256']=sha(case/'wrf.exe')
 assert plan['case_receipts'][arm]['time_control_changes']['run_hours']['new']=='2'
 assert plan['case_receipts'][arm]['time_control_changes']['end_hour']['new']=='14'
 assert plan['case_receipts'][arm]['time_control_changes']['history_end_s']['new']=='7200'
 plan['case_receipts'][arm]['launch_receipt_expected']=str(case/'launch_receipt.json')
plan['status']='PREPARED_NOT_RUN'
plan['source_stage_sha256_unchanged']=all(v==hashlib.sha256((Path(plan['source_stage'])/k).read_bytes()).hexdigest() for k,v in plan['source_stage_files'].items())
assert plan['source_stage_sha256_unchanged']
p.write_text(json.dumps(plan,indent=2)+'\n')
