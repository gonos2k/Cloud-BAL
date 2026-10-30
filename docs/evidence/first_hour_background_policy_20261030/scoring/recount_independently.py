import csv, json, math, hashlib
from pathlib import Path
import numpy as np
p=Path('docs/evidence/first_hour_background_policy_20261030/scoring/results')
old=Path('docs/evidence/current_forecast_paper_20261029/scores/hour_13_arrays.npz')
names=['PRODUCER_H','PRODUCER_BG','FIX_H','ORIGINAL','FIX_ORIGINAL']; ts=(.1,.5,1.,2.5,5.,10.);pairs=[(n,'PRODUCER_BG') for n in ('PRODUCER_H','FIX_H','ORIGINAL','FIX_ORIGINAL')]
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
files=[p/'hour_13_arrays.npz',p/'categorical_scores.csv',p/'continuous_scores.csv',p/'transitions.csv',p/'receipt.json',old]
before={str(f):digest(f) for f in files}
with np.load(files[0],allow_pickle=False) as z: a={k:np.array(z[k]) for k in z.files}
with np.load(old,allow_pickle=False) as z: prior={k:np.array(z[k]) for k in z.files}
assert set(a)==set(names)|{'reference','latitude','longitude','flat_index_yx'}
for k in ('reference','latitude','longitude','flat_index_yx'): assert np.array_equal(a[k],prior[k])
for v in a.values():assert v.shape==(3688,) and np.isfinite(v).all()
def close(x,y):
 if y is None: assert x==''
 else: assert math.isclose(float(x),y,rel_tol=2e-12,abs_tol=2e-12),(x,y)
def divide(x,y):return x/y if y else None
with (p/'categorical_scores.csv').open() as f: rows=list(csv.DictReader(f))
assert len(rows)==30
seen=set()
for r in rows:
 name=r['case']; t=float(r['threshold_mm']);key=name,t; assert key not in seen;seen.add(key)
 h=m=f=d=0
 for x,y in zip(a[name],a['reference']):
  if y>=t:
   if x>=t:h+=1
   else:m+=1
  elif x>=t:f+=1
  else:d+=1
 assert int(r['points'])==3688
 for field,value in zip(('hit','miss','false_alarm','correct_dry'),(h,m,f,d)):assert int(r[field])==value
 rh=(h+m)*(h+f)/3688
 for field,value in dict(CSI=divide(h,h+m+f),ETS=divide(h-rh,h+m+f-rh),POD=divide(h,h+m),FAR=divide(f,h+f),frequency_bias=divide(h+f,h+m)).items():close(r[field],value)
assert seen=={(name,t) for name in names for t in ts}
with (p/'continuous_scores.csv').open() as f: rows=list(csv.DictReader(f))
assert len(rows)==5;seen=set()
for r in rows:
 name=r['case'];assert name not in seen;seen.add(name);err=[float(x)-float(y) for x,y in zip(a[name],a['reference'])];assert int(r['points'])==3688
 for field,value in dict(mean_forecast_mm=math.fsum(a[name])/3688,mean_reference_mm=math.fsum(a['reference'])/3688,mean_error_mm=math.fsum(err)/3688,MAE_mm=math.fsum(map(abs,err))/3688,RMSE_mm=math.sqrt(math.fsum(x*x for x in err)/3688)).items():close(r[field],value)
assert seen==set(names)
with (p/'transitions.csv').open() as f:rows=list(csv.DictReader(f))
assert len(rows)==24;seen=set()
for r in rows:
 baseline,candidate,t=r['baseline'],r['candidate'],float(r['threshold_mm']);key=baseline,candidate,t;assert key not in seen;seen.add(key)
 hg=hl=fg=fl=0
 for x,y,o in zip(a[baseline],a[candidate],a['reference']):
  if o>=t:hg+=x<t<=y;hl+=y<t<=x
  else:fg+=x<t<=y;fl+=y<t<=x
 for field,value in zip(('hit_gains','hit_losses','false_alarm_gains','false_alarm_losses'),(hg,hl,fg,fl)):assert int(r[field])==value
assert seen=={(b,c,t) for b,c in pairs for t in ts}
comparisons={}
for n,o in [('ORIGINAL','ORIGINAL')]:
 diff=a[n]-prior[o];comparisons[n]={'equal':bool(np.array_equal(a[n],prior[o])),'changed_points':int(np.count_nonzero(diff)),'max_abs_difference_mm':float(np.max(np.abs(diff)))}
assert before=={str(f):digest(f) for f in files}
receipt={'status':'PASS','method':'Independent scalar recount and math.fsum from paired NPZ; no independent observation or model run.','rows':{'categorical':30,'continuous':5,'transitions':24},'comparisons':comparisons,'input_sha256':before,'script_sha256':digest(Path(__file__))}
out=Path('/var/tmp/firsthour-producer-scoring-20261030/independent_recount.json');out.write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
