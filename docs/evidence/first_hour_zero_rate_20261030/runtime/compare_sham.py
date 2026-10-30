from pathlib import Path
from netCDF4 import Dataset
import numpy as np, json,hashlib
R=Path('/var/tmp/firsthour-runtime-plan-20261030/experiment'); old=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/current_forecast_paper_20261029/run.PomEr8/forecast_HYDRO'); out={}
for t in ['12','13']:
 name=f'wrfout_d01_2026-08-16_{t}:00:00'; a=R/'run_SHAM'/name;b=old/name
 with Dataset(a) as x,Dataset(b) as y:
  for v in ['RAINC','RAINNC']:
   p=np.asarray(x[v][:]);q=np.asarray(y[v][:]);delta=np.abs(p.astype('float64')-q.astype('float64'));out[t+'_'+v]={'same_shape':p.shape==q.shape,'exact':bool(np.array_equal(p,q,equal_nan=True)),'changed_count':int(np.count_nonzero(p!=q)),'max_abs':float(np.max(delta))}
(R/'sham_comparison.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out));assert all(a['exact'] for a in out.values())
