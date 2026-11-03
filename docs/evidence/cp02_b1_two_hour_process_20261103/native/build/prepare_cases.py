from __future__ import annotations
import hashlib,json,re,shutil
from pathlib import Path

ROOT=Path('/var/tmp/b1-two-hour-probe-20261103')
SOURCE=Path('/var/tmp/six-hour-improved-runtime-20261030/IMPROVED_BG_FIXED')
RECEIPT=SOURCE/'receipt.json'
EXES={'OLD':ROOT/'build/BASE/wrf.exe','FIX':ROOT/'build/FIX/wrf.exe'}
CPU={'OLD':[32,33,34,35,36,37,38,39],'FIX':[40,41,42,43,44,45,46,47]}

def sha(path:Path)->str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def snapshot(paths): return {str(p):sha(p) for p in paths}

receipt=json.loads(RECEIPT.read_text())
staged=receipt['staged_sha256_after']
assert len(staged)==89 and staged['wrfinput_d01']=='9f8b494dbf5ce765e4320701475d6a65be1f591d72a4f9bf5e929c208be563e5'
assert staged['wrfbdy_d01']=='74102ac2063f17a9007f3352e6e6c2f52629055bdf3f05b4f4d6d77aef835f45'
assert staged['wrf.exe']=='68ed2833b5f207d037949c9b20c7c2f800500e632f911a4acf1eb09d13bf1c1f'
source_before={name:sha(SOURCE/name) for name in staged}
assert source_before==staged
case_receipts={}
for arm in ('OLD','FIX'):
    dest=ROOT/'cases'/arm
    dest.mkdir(parents=True,exist_ok=False)
    for name in staged:
        if name=='wrf.exe': shutil.copy2(EXES[arm],dest/name)
        else: shutil.copy2(SOURCE/name,dest/name)
    path=dest/'namelist.input'
    original=path.read_text()
    changes={}
    for key,value in [('run_hours','2'),('end_hour','14'),('history_end_s','7200')]:
        updated,count=re.subn(r'(?m)^(\s*'+key+r'\s*=\s*)[^,\n]+',lambda m:m.group(1)+value,original)
        assert count==1,(arm,key,count)
        changes[key]={'old':re.search(r'(?m)^\s*'+key+r'\s*=\s*([^,\n]+)',original).group(1).strip(),'new':value}
        original=updated
    path.write_text(original)
    assert re.search(r'(?m)^\s*time_step\s*=\s*20\s*,?\s*$',original)
    case_receipts[arm]={'path':str(dest),'source_stage':str(SOURCE),'input_files':{n:sha(dest/n) for n in staged},'time_control_changes':changes,'cpu_set':CPU[arm],'mpi_ranks':8,'omp_threads':1,'executable_sha256':sha(dest/'wrf.exe'),'namelist_sha256':sha(path)}
    assert all(case_receipts[arm]['input_files'][n]==source_before[n] for n in staged if n not in ('wrf.exe','namelist.input'))
    assert case_receipts[arm]['input_files']['wrfinput_d01']==source_before['wrfinput_d01']
    assert case_receipts[arm]['input_files']['wrfbdy_d01']==source_before['wrfbdy_d01']
assert {name:sha(SOURCE/name) for name in staged}==source_before
plan={'status':'PREPARED_NOT_RUN','source_stage':str(SOURCE),'source_stage_receipt_sha256':sha(RECEIPT),'source_stage_files':source_before,'source_unchanged':True,'case_receipts':case_receipts,'launch_constraints':{'mpi_ranks':8,'omp_threads':1,'old_cpu_set':CPU['OLD'],'fix_cpu_set':CPU['FIX'],'launch_authorized':False}}
(ROOT/'case_plan.json').write_text(json.dumps(plan,indent=2)+'\n')
