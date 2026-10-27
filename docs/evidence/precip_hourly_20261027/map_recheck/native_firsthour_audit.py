import importlib.util, json, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
import numpy as np
spec=importlib.util.spec_from_file_location('csi','/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/Cloud-BAL/scratch/cp02_six_hour_20260914/compare_six_hour_csi.py')
csi=importlib.util.module_from_spec(spec); sys.modules['csi']=csi; spec.loader.exec_module(csi)
root=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/Cloud-BAL/scratch/cp02_six_hour_20260914')
ref=root/'reference'; analysis=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/ANAL/NE57/DAOU/DFSD/20260816/klps_lc05_anal_20260816_1300')
inv, mask, tlat, tlon, prov=csi.load_reference(ref,analysis)
start=datetime(2026,8,16,12,tzinfo=timezone.utc)
reports={}; resets={}
for case in csi.CASES:
 ss={}
 for hour in range(12,19):
  p=root/case/'run'/f'wrfout_d01_2026-08-16_{hour:02d}:00:00'
  ss[hour]=csi.read_wrf_snapshot(p,start+timedelta(hours=hour-12),inv)
 # native grid shape and corner crop same as csi mapping
 x0,x1=inv['grid']['crop_x_inclusive']; y0,y1=inv['grid']['crop_y_inclusive']
 cy0,cy1=y0-2,y1-1; cx0,cx1=x0-2,x1-1
 m=csi.build_curvilinear_mapping(ss[12]['lat'][cy0:cy1+1,cx0:cx1+1],ss[12]['lon'][cy0:cy1+1,cx0:cx1+1],tlat,tlon,mask)
 init={}; incs={}; all_neg={}
 for name in ('RAINC','RAINNC'):
  v0,ok0=ss[12]['components'][name]; v1,ok1=ss[13]['components'][name]
  init[name]={'min':float(np.nanmin(v0)),'max':float(np.nanmax(v0)),'nonzero':int(np.count_nonzero(np.abs(v0)>1e-6)),'valid':int(ok0.sum())}
  d=v1-v0; good=ok0&ok1; incs[name]=(d,good)
  mins=[]; nneg=0
  for h in range(13,19):
   a,va=ss[h-1]['components'][name]; b,vb=ss[h]['components'][name]; dd=b-a; gg=va&vb; nneg+=int(np.count_nonzero(gg&(dd < -1e-6))); mins.append(float(np.nanmin(dd[gg])))
  all_neg[name]={'negative_increment_cells_13_18':nneg,'minimum_hourly_increment_mm':min(mins)}
 total,valid=csi.raw_total(ss[13]); total0,valid0=csi.raw_total(ss[12]); dh=total-total0; native_ok=valid&valid0
 # same reduced crop used for reference mapper
 sub=dh[cy0:cy1+1,cx0:cx1+1]; subok=native_ok[cy0:cy1+1,cx0:cx1+1]
 mapped,mgood=csi.remap_field(sub,subok,m)
 # include map points for common source mask; selected mask is the fixed 149x253 source bound land mask
 arr=mapped[mgood]
 def summ(a):
  q=np.quantile(a,[0,.5,.9,.95,.99,1]).tolist()
  return {'count':len(a),'min':float(np.min(a)),'mean':float(np.mean(a)),'max':float(np.max(a)),'quantiles_min_p50_p90_p95_p99_max':q,'sum_point_mm':float(np.sum(a)),'wet_counts':{str(t):int(np.count_nonzero(a>=t)) for t in (.1,.5,1,2.5,5,10)}}
 jn,in_=np.unravel_index(np.nanargmax(dh),dh.shape); jm,im=np.unravel_index(np.nanargmax(mapped),mapped.shape)
 contribution={}
 for nm,(d,g) in incs.items():
  dn=d[cy0:cy1+1,cx0:cx1+1]; gn=g[cy0:cy1+1,cx0:cx1+1]
  rem,good=csi.remap_field(dn,gn,m); contribution[nm]={'mapped_sum_point_mm':float(np.sum(rem[good])),'fraction_total':float(np.sum(rem[good])/np.sum(arr)),'mapped_max_mm':float(np.max(rem[good])),'native_sum_full_grid_mm':float(np.sum(d[g])),'native_max_mm':float(np.max(d[g]))}
 reports[case]={'source_files':{h:str(ss[h]['path']) for h in (12,13)},'units':'mm (validated WRF variable units)','Times_UTC':[csi.decode_times(__import__('netCDF4').Dataset(ss[h]['path']).variables['Times'])[0] for h in (12,13)], 'native_shape':list(ss[12]['lat'].shape),'initial_accumulators':init,'native_hourly_reset_check_13_18':all_neg,'native_hour1_total':summ(dh[native_ok]),'native_hour1_total_max_native_grid_location_yx':list(map(int,(jn,in_))),'native_hour1_total_max_native_grid_location_latlon':[float(ss[13]['lat'][jn,in_]),float(ss[13]['lon'][jn,in_])],'mapped_hour1_common_mask':summ(arr),'mapped_max_target_yx':list(map(int,(jm,im))),'mapped_max_target_latlon':[float(tlat[jm,im]),float(tlon[jm,im])],'mapped_components_point_sum_contributions':contribution,'mapping_residual_max_deg':m['residual_max_deg'],'mapped_point_count':int(mgood.sum()),'target_mask_count':int(mask.sum())}
out={'case_definition':'CP02 12:00 initial to 13:00 UTC first-hour native accumulated precipitation; hourly = 13h minus 12h; RAINC+RAINNC; RAINSH separately required and checked zero; common fixed mask and original curvilinear mapping','reference_arrays':'Original RN1 raw files for 14-18 UTC absent; this diagnostic only assesses model rainfall quantities and geometry, no CSI.','reference_paths':{k:str(v) for k,v in prov.items()},'cases':reports}
Path('/var/tmp/precip_map_checks').mkdir(exist_ok=True)
import hashlib
sha=lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
result=json.loads((root/'RESULT.json').read_text())
history={}
for case in csi.CASES:
 history[case]={}
 for hour in (12,13):
  p=root/case/'run'/f'wrfout_d01_2026-08-16_{hour:02d}:00:00'
  expected=next(x for x in result['sources']['wrfout'][case] if f'_{hour:02d}:00:00' in x['path'])
  actual=sha(p)
  history[case][str(hour)]={'path':str(p),'sha256':actual,'matches_archived_RESULT':actual==expected['sha256']}
out['reproducibility']={'audit_script':'/var/tmp/precip_map_checks/native_firsthour_audit.py','helper':str(root/'compare_six_hour_csi.py'),'helper_sha256':sha(root/'compare_six_hour_csi.py'),'history_file_hashes':history,'first_hour_pairs_npz':'/var/tmp/cloudbal-precip-validation/docs/evidence/precip_hourly_20261027/first_hour_pairs.npz','first_hour_pairs_npz_sha256':sha('/var/tmp/cloudbal-precip-validation/docs/evidence/precip_hourly_20261027/first_hour_pairs.npz'),'pair_receipt_sha256':sha('/var/tmp/cloudbal-precip-validation/docs/evidence/precip_hourly_20261027/first_hour_pairs_receipt.json'),'npz_bridge_check':'/var/tmp/precip_map_checks/bridge_check.py','npz_bridge_result':'/var/tmp/precip_map_checks/npz_bridge.json','original_RN1_paths_missing_UTC_hours':[13,14,15,16,17,18]}
Path('/var/tmp/precip_map_checks/native_firsthour.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:{'initial':v['initial_accumulators'],'native':v['native_hour1_total'],'mapped':v['mapped_hour1_common_mask'],'component_sum':v['mapped_components_point_sum_contributions'],'resets':v['native_hourly_reset_check_13_18']} for k,v in reports.items()},indent=2))
