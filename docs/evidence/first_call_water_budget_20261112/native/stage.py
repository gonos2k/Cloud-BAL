#!/usr/bin/env python3
import hashlib,json,re,shutil,sys
from pathlib import Path
source=Path('/var/tmp/six-hour-improved-runtime-20261030/IMPROVED_BG_FIXED')
out=Path(sys.argv[1]); terminal=len(sys.argv)==3 and sys.argv[2]=='--terminal'
if len(sys.argv) not in (2,3) or (len(sys.argv)==3 and not terminal): raise ValueError('usage: stage.py OUTPUT [--terminal]')
out.mkdir(parents=True,exist_ok=False)
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
files=json.loads((source/'receipt.json').read_text())['staged_sha256_after']
assert len(files)==89
for name,h in files.items():
 p=source/name
 if sha(p)!=h: raise ValueError(f'source hash mismatch {name}')
 shutil.copy2(Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_activation_path_20261110/runtime/native_build/variants/CONTROL/wrf.exe') if name=='wrf.exe' else p,out/name)
assert sha(out/'wrf.exe')=='3a286f6691fa94c2dccf55b14e4cbf609b8c9540c2caf83556969932ca9854ea'
assert sha(out/'wrfinput_d01')=='9f8b494dbf5ce765e4320701475d6a65be1f591d72a4f9bf5e929c208be563e5'
p=out/'namelist.input';t=p.read_text()
for key,val in [('run_hours','0'),('run_minutes','1'),('run_seconds','20'),('end_hour','12'),('end_minute','1'),('end_second','20'),('history_end_s','80')]:
 t,n=re.subn(r'(?m)^(\s*'+key+r'\s*=\s*)[^,\n]+',lambda m:m.group(1)+val,t)
 if n!=1:raise ValueError(key)
if terminal:
 t,n=re.subn(r'(?m)^(\s*history_interval_s\s*=\s*)[^,\n]+',lambda m:m.group(1)+'80',t)
 if n!=1:raise ValueError('history_interval_s')
assert re.search(r'(?m)^\s*time_step\s*=\s*20\s*,?\s*$',t)
p.write_text(t)
(out/'staged.json').write_text(json.dumps({n:sha(out/n) for n in files},indent=2)+'\n')
