#!/usr/bin/env python3
"""Independently audit producer shadow and native fields, without writing inputs."""
import argparse, hashlib, importlib.util, json
from pathlib import Path
import numpy as np
from netCDF4 import Dataset

CHECKER=Path('/var/tmp/cloudbal-first-hour-improvement/tools/check_background_precip_shadow.py')
CHECKER_SHA='17ee6d5e23925e34b9fdc881d3e1c81a27ef60f832cb4702b8dd0247a0825abd'
H='7fd13466f8e19d0f8d88ce0499bcb249aa9803bb8ad7df9eee39c757bc315126'

def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()

def attrs_equal(a,b):
 return set(a.ncattrs())==set(b.ncattrs()) and all(np.array_equal(a.getncattr(k),b.getncattr(k)) for k in a.ncattrs())

def compare(a,b):
 with Dataset(a) as x,Dataset(b) as y:
  x.set_auto_mask(False);y.set_auto_mask(False)
  dims=set(x.dimensions)==set(y.dimensions) and all(len(x.dimensions[k])==len(y.dimensions[k]) and x.dimensions[k].isunlimited()==y.dimensions[k].isunlimited() for k in x.dimensions)
  if not dims or set(x.variables)!=set(y.variables):raise ValueError('native dimension/variable sets differ')
  result={}
  for k in x.variables:
   a,b=x[k],y[k]
   if a.dimensions!=b.dimensions or a.shape!=b.shape or a.dtype!=b.dtype:raise ValueError(f'{k}: incompatible metadata')
   v,w=np.asarray(a[:]),np.asarray(b[:]);eq=np.equal(v,w)
   if v.dtype.kind in 'fc':
    if not np.isfinite(v).all() or not np.isfinite(w).all():raise ValueError(f'{k}: nonfinite')
    maximum=float(np.max(np.abs(w.astype(np.float64)-v.astype(np.float64)))) if v.size else 0.
   elif v.dtype.kind in 'iu':maximum=int(np.max(np.abs(w.astype(np.int64)-v.astype(np.int64)))) if v.size else 0
   else:maximum=None
   count=int(np.count_nonzero(~eq));meta=attrs_equal(a,b)
   if count or not meta:result[k]={'changed_count':count,'size':int(v.size),'max_abs_difference':maximum,'units':str(getattr(a,'units','')),'dimensions':list(a.dimensions),'metadata_equal':meta}
  return {'changed':result,'global_attributes_equal':attrs_equal(x,y),'variable_count':len(x.variables)}

def main():
 p=argparse.ArgumentParser();p.add_argument('--historical',type=Path,required=True);p.add_argument('--baseline',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--shadow',type=Path,required=True);p.add_argument('--baseline-sha',required=True);p.add_argument('--candidate-sha',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if a.output.exists() or a.output.is_symlink():raise ValueError('output exists')
 paths=[a.historical,a.baseline,a.candidate,a.shadow,CHECKER];before={str(x):sha(x) for x in paths}
 if before[str(a.historical)]!=H or before[str(a.baseline)]!=a.baseline_sha or before[str(a.candidate)]!=a.candidate_sha or before[str(CHECKER)]!=CHECKER_SHA:raise ValueError('source hash mismatch')
 spec=importlib.util.spec_from_file_location('scoped_background_checker',CHECKER);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);shadow=m.check(a.shadow)
 result={'status':'PASS_SCOPED','checker':shadow,'historical_vs_baseline':compare(a.historical,a.baseline),'baseline_vs_candidate':compare(a.baseline,a.candidate),'inputs_sha256':before,'baseline_bitwise_matches_historical':before[str(a.baseline)]==H,'scope':'Read-only full native field and metadata comparison and scoped shadow contract; not a water or energy closure test.'}
 if before!={str(x):sha(x) for x in paths}:raise ValueError('source changed during audit')
 with a.output.open('x') as f:json.dump(result,f,indent=2,allow_nan=False);f.write('\n')
 print(json.dumps({'status':result['status'],'baseline_bitwise_matches_historical':result['baseline_bitwise_matches_historical'],'changed_fields':len(result['baseline_vs_candidate']['changed'])},indent=2))

if __name__=='__main__':main()
