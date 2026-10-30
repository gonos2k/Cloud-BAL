from pathlib import Path
import hashlib,json,shutil
import numpy as np
from netCDF4 import Dataset
root=Path('/var/tmp/firsthour-runtime-plan-20261030/ablation'); exp=root.parent/'experiment'; source=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/current_forecast_paper_20261029/run.PomEr8'); H=source/'forecast_HYDRO/wrfinput_d01'; O=source/'original/wrfinput_d01'
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def eq(a,b):return np.array_equal(np.asarray(a),np.asarray(b),equal_nan=True) if np.asarray(a).dtype.kind not in 'SUO' else np.array_equal(a,b)
def attrs(d):return {k:d.getncattr(k) for k in d.ncattrs()}
def attr_eq(a,b):return a.keys()==b.keys() and all(eq(a[k],b[k]) for k in a)
parent_before={str(p):sha(p) for p in (H,O)}; assert parent_before[str(H)]=='7fd13466f8e19d0f8d88ce0499bcb249aa9803bb8ad7df9eee39c757bc315126'; assert parent_before[str(O)]=='5d6b2bdce4121642dea994f3e953cca690ad7c9f52f6f8feb01bb6c2f0b9b6bc'
with Dataset(H) as h,Dataset(O) as o:
 assert list(h.variables)==list(o.variables) and list(h.dimensions)==list(o.dimensions)
 assert all((len(h.dimensions[k]),h.dimensions[k].isunlimited())==(len(o.dimensions[k]),o.dimensions[k].isunlimited()) for k in h.dimensions)
 assert attr_eq(attrs(h),attrs(o))
 for k in h.variables:
  x,y=h[k],o[k]; assert x.dtype==y.dtype and x.dimensions==y.dimensions and x.shape==y.shape,k
  assert attr_eq(attrs(x),attrs(y)),k
 for k in ['XLAT','XLONG','XLAT_U','XLONG_U','XLAT_V','XLONG_V','ZNU','ZNW','DN','DNW']:
  if k in h.variables: assert eq(h[k][:],o[k][:]),k
receipt={'schema':'initial_qrain_qsnow_reciprocal_v1','parent_before':parent_before,'parent_dimensions_dtypes_variable_and_global_attributes_match':True,'coordinate_names_checked':[k for k in ['XLAT','XLONG','XLAT_U','XLONG_U','XLAT_V','XLONG_V','ZNU','ZNW','DN','DNW'] if k in h.variables],'cases':{},'interpretation':'unbalanced initial-state sensitivity; P and PH retained, no hydrostatic adjustment; not an operational initialization'}
for label,base,donor,previous in [('H_ORIGINAL_QRQS',H,O,'FIX_H'),('ORIGINAL_H_QRQS',O,H,'FIX_ORIGINAL')]:
 d=root/('run_'+label); assert not d.exists(); d.mkdir(); prev=exp/('run_'+previous); prior=json.loads((prev/'inputs.json').read_text())['staged']; before={n:sha(prev/n) for n in prior}; assert before==prior
 for n in prior: shutil.copy2(prev/n,d/n)
 assert {n:sha(prev/n) for n in prior}==before
 with Dataset(d/'wrfinput_d01','r+') as target,Dataset(donor) as from_data:
  for v in ('QRAIN','QSNOW'): target[v][:]=from_data[v][:]
 fields={}; changed=[]
 with Dataset(base) as original,Dataset(d/'wrfinput_d01') as target,Dataset(donor) as donor_data:
  assert attr_eq(attrs(original),attrs(target)); assert list(original.variables)==list(target.variables)
  assert all((len(original.dimensions[k]),original.dimensions[k].isunlimited())==(len(target.dimensions[k]),target.dimensions[k].isunlimited()) for k in original.dimensions)
  for k in original.variables:
   x,y=original[k],target[k]; assert x.dtype==y.dtype and x.dimensions==y.dimensions and x.shape==y.shape and attr_eq(attrs(x),attrs(y)),k
   a,b=x[:],y[:]
   if not eq(a,b):changed.append(k)
   if k in ('QRAIN','QSNOW'):
    assert eq(b,donor_data[k][:]),k; aa=np.asarray(a,dtype='float64');bb=np.asarray(b,dtype='float64'); assert np.isfinite(aa).all() and np.isfinite(bb).all() and (aa>=0).all() and (bb>=0).all(),k
    delta=bb-aa;fields[k]={'units':x.units,'base_min':float(aa.min()),'base_max':float(aa.max()),'donor_min':float(bb.min()),'donor_max':float(bb.max()),'changed_cells':int(np.count_nonzero(delta)),'delta_min':float(delta.min()),'delta_max':float(delta.max()),'delta_mean_unweighted':float(delta.mean()),'delta_sum_unweighted':float(delta.sum()),'note':'sum over mixing ratios is not total water mass'}
 assert set(changed).issubset({'QRAIN','QSNOW'}) and set(changed)=={'QRAIN','QSNOW'},changed
 staged={n:sha(d/n) for n in prior}; assert all(staged[n]==prior[n] for n in prior if n!='wrfinput_d01'); assert staged['wrf.exe']=='68ed2833b5f207d037949c9b20c7c2f800500e632f911a4acf1eb09d13bf1c1f'
 info={'base':str(base),'donor':str(donor),'base_sha256':sha(base),'donor_sha256':sha(donor),'prior_case':str(prev),'prior_case_hashes_before_after_equal':True,'changed_variables':changed,'fields':fields,'other_variable_values_and_all_metadata_unchanged':True,'all_staged_input_hashes':staged,'input_count':len(staged)}
 (d/'inputs.json').write_text(json.dumps(info,indent=2)+'\n'); receipt['cases'][label]=info
parent_after={str(p):sha(p) for p in (H,O)}; assert parent_before==parent_after;receipt['parent_after']=parent_after;receipt['parent_unchanged']=True
(root/'preparation.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({k:{'input':v['all_staged_input_hashes']['wrfinput_d01'],'counts':v['input_count'],'fields':v['fields']} for k,v in receipt['cases'].items()},indent=2))
