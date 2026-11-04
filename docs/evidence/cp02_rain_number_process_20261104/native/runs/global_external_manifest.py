import hashlib,json
from pathlib import Path
R=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_rain_number_process_20261104')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
result={}
for arm in ('B1','NR_PRIOR'):
 d=R/'runtime/runs'/arm;files=[]
 for stage in ('entry','pre_update','post_process','kdm62d_return','wrapper_return'):
  for rank in range(8):
   p=d/f'state_{stage}_rank{rank}.bin';assert p.is_file();files.append({'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)})
 result[arm]=files
out={'scope':'External raw first-step global state streams; omitted from Git capture. Selected state and process records separately archived losslessly.','files':result}
(R/'Cloud-BAL/docs/evidence/cp02_rain_number_process_20261104/native/runs/global_external_manifest.json').write_text(json.dumps(out,indent=2)+'\n')
