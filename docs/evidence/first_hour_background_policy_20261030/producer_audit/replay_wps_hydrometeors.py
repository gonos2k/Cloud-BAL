#!/usr/bin/env python3
"""Replay all emitted WPS hydrometeor slabs against the policy shadow."""
import hashlib,json,sys
from pathlib import Path
import numpy as np
from netCDF4 import Dataset
sys.path.insert(0,'/var/tmp/cloudbal-first-hour-improvement/tools')
from compare_baseline import read_wps

root=Path('/var/tmp/firsthour-runtime-plan-20261030/producer_pair/run_HYDRO_BACKGROUND_PRECIP')
paths=[root/'output.wps',root/'output.wps.shadow.nc',Path('/var/tmp/cloudbal-first-hour-improvement/tools/compare_baseline.py')]
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
before={str(p):sha(p) for p in paths}
expected=['ab0406fc71ec7c62cf63d7240bbfc36ee133902639b538472f52fedb5d720fb6','821543471d9d9540b77ddc9cee58cb74dfc32f6679b0bb233af56aaeedae9d07']
if [before[str(p)] for p in paths[:2]]!=expected:raise ValueError('pinned output identity mismatch')
records=read_wps(paths[0]);counts={};mapping={'QC':'candidate_cloud_water','QI':'candidate_cloud_ice','QR':'candidate_rain','QS':'candidate_snow','QG':'candidate_graupel'}
with Dataset(paths[1]) as d:
 levels=np.asarray(d['pressure'][:]);above=np.asarray(d['above_ground'][:],bool)
 assert len(set(levels.tolist()))==len(levels)
 for field,var in mapping.items():
  data=np.asarray(d[var][:]);matched=[]
  for (name,level,date),(units,shape,values,metadata) in records.items():
   if name!=field:continue
   assert date=='2026-08-16_12:00:00.0000' and units=='kg kg{-1}'
   actual=values.reshape(shape,order='F')
   if level==200100.:expected_field=np.zeros(shape,dtype=np.float32)
   else:
    ix=np.flatnonzero(levels==level);assert len(ix)==1;k=int(ix[0]);expected_field=np.where(above[k].T,data[k].T,0.)
   np.testing.assert_array_equal(actual,expected_field,err_msg=f'{name} {level}')
   matched.append(float(level))
  assert set(matched)==set(float(x) for x in levels if x<=100100.) | {200100.}
  counts[field]=len(matched)
if before!={str(p):sha(p) for p in paths}:raise ValueError('input changed during read')
out={'status':'PASS_WPS_HYDROMETEOR_REPLAY','slabs_per_field':counts,'inputs_sha256':before,'scope':'Pressure-level and surface QC/QI/QR/QS/QG writer slabs against actual schema-5 policy shadow; no general shadow approval or native water closure.'}
p=root.parent/'wps_hydrometeor_replay.json'
with p.open('x') as f:json.dump(out,f,indent=2);f.write('\n')
print(json.dumps(out,indent=2))
