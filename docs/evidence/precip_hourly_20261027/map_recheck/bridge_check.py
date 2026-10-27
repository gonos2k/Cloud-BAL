"""Reproduce CP02 native first-hour precipitation and bridge it to retained PR NPZ."""
import importlib.util, json, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
import numpy as np
from netCDF4 import Dataset
helper=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/Cloud-BAL/scratch/cp02_six_hour_20260914/compare_six_hour_csi.py')
spec=importlib.util.spec_from_file_location('csi',helper); csi=importlib.util.module_from_spec(spec); sys.modules['csi']=csi; spec.loader.exec_module(csi)
root=helper.parent; inv,mask,tlat,tlon,prov=csi.load_reference(root/'reference',Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/ANAL/NE57/DAOU/DFSD/20260816/klps_lc05_anal_20260816_1300'))
npz_path=Path('/var/tmp/cloudbal-precip-validation/docs/evidence/precip_hourly_20261027/first_hour_pairs.npz')
npz=np.load(npz_path); flat=np.asarray(npz['flat_index_yx'],int); lat=tlat.ravel()[flat]; lon=tlon.ravel()[flat]
start=datetime(2026,8,16,12,tzinfo=timezone.utc); results={}
x0,x1=inv['grid']['crop_x_inclusive']; y0,y1=inv['grid']['crop_y_inclusive']; cy0,cy1=y0-2,y1-1; cx0,cx1=x0-2,x1-1
for case,key in [('off','OFF'),('hydro','HYDRO'),('liquid','LIQUID')]:
 snaps=[]
 for h in (12,13): snaps.append(csi.read_wrf_snapshot(root/case/'run'/f'wrfout_d01_2026-08-16_{h:02d}:00:00',start+timedelta(hours=h-12),inv))
 s0,s1=snaps
 if not np.array_equal(s0['lat'],s1['lat']) or not np.array_equal(s0['lon'],s1['lon']): raise RuntimeError('native coordinates changed')
 mapping=csi.build_curvilinear_mapping(s0['lat'][cy0:cy1+1,cx0:cx1+1],s0['lon'][cy0:cy1+1,cx0:cx1+1],tlat,tlon,mask)
 v0,g0=csi.raw_total(s0); v1,g1=csi.raw_total(s1); good=g0&g1
 a0,m0=csi.remap_field(v0[cy0:cy1+1,cx0:cx1+1],g0[cy0:cy1+1,cx0:cx1+1],mapping)
 a1,m1=csi.remap_field(v1[cy0:cy1+1,cx0:cx1+1],g1[cy0:cy1+1,cx0:cx1+1],mapping)
 mapped=a1-a0; vals=mapped.ravel()[flat]; diff=v1-v0
 nativecoords=(float(s1['lat'][np.unravel_index(np.nanargmax(diff),diff.shape)]),float(s1['lon'][np.unravel_index(np.nanargmax(diff),diff.shape)]))
 maxindex=int(np.nanargmax(vals)); maxlatlon=[float(lat[maxindex]),float(lon[maxindex])]
 results[key]={'max_abs_forecast_difference_mm':float(np.max(np.abs(vals-npz[key]))),'exact_forecast_values':bool(np.array_equal(vals,npz[key])),'max_abs_latitude_difference_deg':float(np.max(np.abs(lat-npz['latitude']))),'max_abs_longitude_difference_deg':float(np.max(np.abs(lon-npz['longitude']))),'coordinates_equal':bool(np.array_equal(lat,npz['latitude']) and np.array_equal(lon,npz['longitude'])),'native_max_yx':list(map(int,np.unravel_index(np.nanargmax(diff),diff.shape))),'native_max_latlon':nativecoords,'mapped_max_flat_index':int(flat[maxindex]),'mapped_max_latlon':maxlatlon,'mapped_max_mm':float(vals[maxindex]),'mapped_ge10_count':int(np.count_nonzero(vals>=10.0)),'mapped_gt10_count':int(np.count_nonzero(vals>10.0)),'threshold_comparator':'>= 10 mm'}
out={'forecast_npz':str(npz_path),'mapping':'Existing load_reference and build_curvilinear_mapping; same source-bound mask; fields gathered by NPZ flat_index_yx','results':results}
outpath=Path('/var/tmp/precip_map_checks/npz_bridge.json');outpath.write_text(json.dumps(out,indent=2)+'\n');print(outpath.read_text())
