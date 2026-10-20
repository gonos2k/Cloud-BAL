import json
from pathlib import Path
from netCDF4 import Dataset
import numpy as np
bundle=Path(__file__).resolve().parent
met_em='/var/tmp/pr82_same13_real_candidate.final20261012/met_em.d01.2026-08-16_13:00:00.nc'
with Dataset(met_em) as ds:
    pres=np.asarray(ds['PRES'][0],dtype=np.float32)
    qc=np.asarray(ds['QC'][0],dtype=np.float32)
    lat=np.asarray(ds['XLAT_M'][0],dtype=np.float32)
    lon=np.asarray(ds['XLONG_M'][0],dtype=np.float32)
rows=json.loads((bundle.parent/'laps_qc_horizontal_rows.json').read_text())
targets=[(x['target_i0'],x['target_j0']) for x in rows['union_target_cells']]
levels=[]
for k in range(3,21):
    p=float(100000-5000*(k-2)) # candidate source zero k=3 ->95000, k20 ->10000
    matches=np.flatnonzero(np.any(pres==p,axis=(1,2)))
    if len(matches)!=1: raise RuntimeError(f'{p}: expected one met_em pressure index, found {matches}')
    mk=int(matches[0])
    for i,j in targets:
        observedp=float(pres[mk,j,i])
        if observedp != p: raise RuntimeError(f'{p} Pa target {(i,j)} has PRES={observedp}')
        levels.append((p,i,j,float(lat[j,i]),float(lon[j,i]),float(qc[mk,j,i]),mk,observedp))
with open(bundle/'targets_288.txt','w') as f:
    for p,i,j,la,lo,v,mk,observedp in levels:
        f.write(f'{p:.1f} {i} {j} {la:.9g} {lo:.9g} {v:.9g} {mk} {observedp:.1f}\n')
print('targets',len(levels),'pressures',len(set(x[0] for x in levels)),'target cells',len(targets))
print('target file written; exact met_em pressure index unique per source level')
