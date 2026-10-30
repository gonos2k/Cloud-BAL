from pathlib import Path
import json,hashlib
import numpy as np
from netCDF4 import Dataset
r=Path('/var/tmp/firsthour-runtime-plan-20261030/ablation'); result={'gravity_m_s2':9.81,'gravity_source':'retained host/share/module_model_constants.F:17','interpretation':'initial dry-air carrier-weighted change in QR and QS; not a runtime budget closure or hydrostatic adjustment','cases':{}}
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
for name in ('H_ORIGINAL_QRQS','ORIGINAL_H_QRQS'):
 d=r/('run_'+name);i=json.loads((d/'inputs.json').read_text());base=Path(i['base']);target=d/'wrfinput_d01'; assert sha(base)==i['base_sha256'] and sha(target)==i['all_staged_input_hashes']['wrfinput_d01']
 with Dataset(base) as b,Dataset(target) as a:
  def checked(v):
   assert not np.ma.getmaskarray(v).any(); x=np.asarray(v,dtype='float64'); assert np.isfinite(x).all(); return x
  def f(k):return checked(b[k][0])
  mu=f('MU')+f('MUB');dnw=f('DNW');znw=f('ZNW');c1=f('C1H');c2=f('C2H');mx=f('MAPFAC_MX');my=f('MAPFAC_MY');dx=float(b.DX);dy=float(b.DY)
  assert np.isfinite(dx) and np.isfinite(dy) and dx>0 and dy>0 and (mx>0).all() and (my>0).all()
  area=dx*dy/(mx*my);dp=(-dnw[:,None,None])*(c1[:,None,None]*mu[None,:,:]+c2[:,None,None]); assert np.isfinite(area).all() and np.isfinite(dp).all() and (area>0).all() and (dp>0).all();assert np.allclose(dnw,np.diff(znw),rtol=0,atol=2e-7)
  assert np.max(np.abs(dp.sum(axis=0)-mu)) < 0.01
  carrier=dp/9.81*area[None,:,:]; assert np.isfinite(carrier).all() and (carrier>0).all();fields={}
  for k in ('QRAIN','QSNOW'):
   delta=checked(a[k][0])-f(k);dm=delta*carrier;fields[k]={'signed_change_kg':float(dm.sum()),'positive_change_kg':float(np.maximum(dm,0).sum()),'negative_change_kg':float(np.minimum(dm,0).sum()),'domain_area_mean_change_kg_m2':float(dm.sum()/area.sum())}
  result['cases'][name]={'base_sha256':i['base_sha256'],'intervention_sha256':sha(target),'dx_m':dx,'dy_m':dy,'area_m2':float(area.sum()),'cell_area_min_m2':float(area.min()),'cell_area_max_m2':float(area.max()),'dry_layer_dp_min_pa':float(dp.min()),'dry_layer_dp_max_pa':float(dp.max()),'max_column_dp_minus_mu_pa':float(np.max(np.abs(dp.sum(axis=0)-mu))),'fields':fields}
(r/'dry_mass_inventory.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
