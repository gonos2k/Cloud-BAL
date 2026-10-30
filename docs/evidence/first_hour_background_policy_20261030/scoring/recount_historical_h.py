#!/usr/bin/env python3
"""Independently recount the historical HYDRO comparator from the sealed paired NPZ."""
import hashlib,json,math
from pathlib import Path
import numpy as np

old=Path('docs/evidence/current_forecast_paper_20261029/scores/hour_13_arrays.npz')
new=Path('docs/evidence/first_hour_background_policy_20261030/scoring/results/hour_13_arrays.npz')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
before={str(p):sha(p) for p in (old,new)}
if before[str(old)]!='0df6e55167373751a2a9e50f10325c6d6d1e02603f1225e448c8e766184da9e4':raise ValueError('historical hash mismatch')
with np.load(old,allow_pickle=False) as z: ref=z['reference'].tolist();forecast=z['CURRENT_HYDRO'].tolist(); lat=z['latitude'];lon=z['longitude'];idx=z['flat_index_yx']
with np.load(new,allow_pickle=False) as z:
 assert np.array_equal(ref,z['reference']) and np.array_equal(lat,z['latitude']) and np.array_equal(lon,z['longitude']) and np.array_equal(idx,z['flat_index_yx'])
assert len(ref)==3688
rows=[]
for t in (.1,.5,1.,2.5,5.,10.):
 h=m=f=d=0
 for x,y in zip(forecast,ref):
  if y>=t:
   if x>=t:h+=1
   else:m+=1
  elif x>=t:f+=1
  else:d+=1
 rows.append({'threshold_mm':t,'hit':h,'miss':m,'false_alarm':f,'correct_dry':d,'CSI':h/(h+m+f) if h+m+f else None})
e=[x-y for x,y in zip(forecast,ref)];result={'status':'PASS','case':'HISTORICAL_HYDRO','categorical':rows,'mean_error_mm':math.fsum(e)/len(e),'MAE_mm':math.fsum(map(abs,e))/len(e),'RMSE_mm':math.sqrt(math.fsum(x*x for x in e)/len(e)),'input_sha256':before,'scope':'Independent scalar historical HYDRO recount against identical pinned RN1/reference points.'}
assert before=={str(p):sha(p) for p in (old,new)}
p=Path('/var/tmp/firsthour-producer-scoring-20261030/historical_h.json')
with p.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps(result,indent=2))
