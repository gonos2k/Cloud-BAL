#!/usr/bin/env python3
"""Read-only, source-order 14Z GK2A IR112 -> LVD support replay hypothesis."""
from pathlib import Path
import argparse, hashlib, json, math, os, struct
import numpy as np
from netCDF4 import Dataset
ROOT=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50')
raw_path=ROOT/'ANAL/NE57/DAIO/2026081614/gk2a_ami_le1b_ir112_ko020lc_202608161400.nc'
lvd_path=ROOT/'ANAL/NE57/DAOU/00/lapsprd/lvd/kogk2a/262281400.lvd'
nav_path=ROOT/'ANAL/NE57/DABA/lvd/kogk2a-llij-ir-ami.lut'
bt_path=ROOT/'ANAL/NE57/DABA/lvd/kogk2alookup/11u.lut'
source_support=ROOT/'scratch/pr105_observation_pairing_20261026/Cloud-BAL/docs/evidence/pr105_satellite_scope_20261026/satellite_lvd_audit_v3.json'
config_path=ROOT/'ANAL/NE57/DABA/namelist/satellite_lvd.nl'
source_paths=[ROOT/p for p in [
 'klaps-v5.0_/src/ingest/satellite/lvd_gk2a/read_gk2a_ami.f',
 'klaps-v5.0_/src/ingest/satellite/lvd_gk2a/btempconvert_ami.f',
 'klaps-v5.0_/src/ingest/satellite/lvd_gk2a/lvd_driver_sub.f',
 'klaps-v5.0_/src/ingest/satellite/lvd_gk2a/satir_process.f',
 'klaps-v5.0_/src/ingest/satellite/lvd_gk2a/satir2laps.f',
 'klaps-v5.0_/src/ingest/satellite/lvd_gk2a/readlut.f',
 'klaps-v5.0_/src/ingest/satellite/lvd_gk2a/read_gvarimg_cnt2btemp_lut.f',
 'klaps-v5.0_/src/lib/satellite/lvd_file_specifier.f',
 'klaps-v5.0_/src/lib/util/filter_2dx.f']]
inputs=[raw_path,lvd_path,nav_path,bt_path,source_support,config_path]
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
hashes_before={str(p.relative_to(ROOT)):sha(p) for p in inputs+source_paths}
def jsonable(x):
  return x.item() if isinstance(x, np.generic) else x
raw=Dataset(raw_path)
words=np.asarray(raw.variables['image_pixel_values'][:],dtype=np.uint16)
attrs={k:jsonable(getattr(raw,k)) for k in raw.ncattrs()}
var_attrs={k:jsonable(getattr(raw.variables['image_pixel_values'],k)) for k in raw.variables['image_pixel_values'].ncattrs()}
assert var_attrs['channel_name']=='IR112' and attrs['channel_center_wavelength']=='11.2'
assert words.shape==(900,900)
raw.close()
# Source read_gk2a_ami.f: mask low 13 data bits, upper two QC bits; load_image_ami.f reverses rows then crops 1-based 155:746,96:805.
counts=words & np.uint16(8191)
qc=words >> np.uint16(14)
counts=counts[::-1, :][95:805,154:746]
qc=qc[::-1, :][95:805,154:746]
assert counts.shape==(710,592)
fill=np.float32(-9999.0)
# Exact DABA table that runtime path `<static>/lvd/kogk2alookup/11u.lut` resolves to.
tab=np.loadtxt(bt_path,dtype=np.float32)
assert tab.shape==(8192,2) and np.array_equal(tab[:,0],np.arange(8192,dtype=np.float32))
bt=tab[counts,1].astype(np.float32)
bt[qc!=0]=fill
# Decode readlut.f's four big-endian Fortran sequential records (first two ignored; then ri and rj).
b=nav_path.read_bytes(); off=0; rec=[]
for k in range(4):
    n=struct.unpack_from('>i',b,off)[0]; off+=4
    a=np.frombuffer(b,dtype='>f4',count=n//4,offset=off).astype(np.float32).reshape((235,283),order='F')
    off+=n
    assert struct.unpack_from('>i',b,off)[0]==n; off+=4
    rec.append(a)
assert off==len(b)
ri,rj=rec[2],rec[3]
# DABA satellite_lvd.nl config: type 1/satellite 5 IR pixel resolution 2000m; PR105 LAPS grid 5000m => saved-config-implied ratio .4.
ratio=np.float32(2000.0/5000.0)
assert ratio==np.float32(0.4)
mean=np.full((283,235),fill,dtype=np.float32)
maximum=np.full((283,235),fill,dtype=np.float32)
minimum=np.full((283,235),fill,dtype=np.float32)
npix=np.zeros((283,235),dtype=np.int16)
for x in range(235):
  for y in range(283):
    if ri[x,y] == fill or rj[x,y] == fill: continue
    # satir2laps.f Fortran nint/trunc formulas, translated to 1-based ranges.
    i0=math.floor(float(ri[x,y] - np.float32(1.25) + np.float32(0.5)) + 0.5)
    i1=int(float(ri[x,y] + np.float32(1.25)))
    j0=math.floor(float(rj[x,y] - np.float32(1.25) + np.float32(0.5)) + 0.5)
    j1=int(float(rj[x,y] + np.float32(1.25)))
    if i0 < 1 or j0 < 1 or i1 > bt.shape[1] or j1 > bt.shape[0] or i0 > i1 or j0 > j1:
      continue  # source skips insufficient/out-of-range footprints; never use Python negative-index wrap
    vals=bt[j0-1:j1, i0-1:i1]
    vals=vals[vals!=fill]
    npix[y,x]=len(vals)
    if len(vals):
      # Fortran loop sum uses REAL*4 accumulation in JJ then II order.
      s=np.float32(0.)
      for v in vals: s=np.float32(s+v)
      mean[y,x]=np.float32(s/np.float32(len(vals)))
      maximum[y,x]=np.max(vals)
      minimum[y,x]=np.min(vals)
# Fortran filter_2dx implementation, as applied to ta8 with +.5 then -.5 in lvd_driver_sub.
def filt(field, smth):
  a=field.copy(); ix,iy=a.shape[1],a.shape[0]
  s1=np.float32(.25)*np.float32(smth)*np.float32(smth)
  s2=np.float32(.50)*np.float32(smth)*(np.float32(1.)-np.float32(smth))
  s3=(np.float32(1.)-np.float32(smth))*(np.float32(1.)-np.float32(smth))
  s4=np.float32(1.)-np.float32(smth); s5=np.float32(.5)*np.float32(smth)
  hold=np.zeros((2,ix),dtype=np.float32); i1,i2=1,0
  for j in range(1,iy-1):
    i1,i2=i2,i1
    for i in range(1,ix-1):
      sum1=np.float32(a[j+1,i-1]+a[j-1,i-1]+a[j+1,i+1]+a[j-1,i+1])
      sum2=np.float32(a[j+1,i]+a[j,i+1]+a[j-1,i]+a[j,i-1])
      hold[i1,i]=np.float32(s1*sum1+s2*sum2+s3*a[j,i])
    if j != 1: a[j-1,1:-1]=hold[i2,1:-1]
  a[iy-2,1:-1]=hold[i1,1:-1]
  a[0,1:-1]=s4*a[0,1:-1]+s5*(a[0,:-2]+a[0,2:])
  a[-1,1:-1]=s4*a[-1,1:-1]+s5*(a[-1,:-2]+a[-1,2:])
  a[1:-1,0]=s4*a[1:-1,0]+s5*(a[:-2,0]+a[2:,0])
  a[1:-1,-1]=s4*a[1:-1,-1]+s5*(a[:-2,-1]+a[2:,-1])
  return a
# satir_process passes tb8,tc8,ta8 to (sa,sc,st); satir2laps puts mean in sa, warmest in st.
# Therefore source as written routes the warmest output (maximum) to ta8/S8A; filter that array.
source_s8a=filt(filt(maximum,.5),-.5)
with Dataset(lvd_path) as d:
  actual=np.asarray(d.variables['s8a'][0,0,:,:],dtype=np.float32)
  actual_s8w=np.asarray(d.variables['s8w'][0,0,:,:],dtype=np.float32)
indices=json.loads(source_support.read_text())['source_composed_support']['source_laps_grid_indices_zero_based_j_i']
results=[]
for j,i in indices:
  x,y=ri[i,j],rj[i,j]
  i0=math.floor(float(np.float32(x-np.float32(1.25)+np.float32(.5)))+.5); i1=int(float(np.float32(x+np.float32(1.25))))
  j0=math.floor(float(np.float32(y-np.float32(1.25)+np.float32(.5)))+.5); j1=int(float(np.float32(y+np.float32(1.25))))
  results.append({'j':j,'i':i,'nav_ri_1based':float(x),'nav_rj_1based':float(y),'source_i_1based_bounds':[i0,i1],'source_j_1based_bounds':[j0,j1],'S8A_actual':float(actual[j,i]),'S8W_actual':float(actual_s8w[j,i]),'S8W_mean_unfiltered':float(mean[j,i]),'S8W_minus_mean_K':float(np.float32(actual_s8w[j,i]-mean[j,i])),'S8A_source_hypothesis_filtered_max':float(source_s8a[j,i]),'S8A_minus_filtered_max_K':float(np.float32(actual[j,i]-source_s8a[j,i])),'S8A_actual_float32_hex':actual[j,i].tobytes().hex(),'S8A_replay_float32_hex':source_s8a[j,i].tobytes().hex(),'S8W_actual_float32_hex':actual_s8w[j,i].tobytes().hex(),'mean_float32_hex':mean[j,i].tobytes().hex(),'nvalid_pixels':int(npix[j,i])})
# Since filter output near fixed support depends on neighbors, report max hypothesis error at cells where all input pixels valid.
errs=[abs(x['S8A_actual']-x['S8A_source_hypothesis_filtered_max']) for x in results]
hashes_after={str(p.relative_to(ROOT)):sha(p) for p in inputs+source_paths}
out={'schema':'pr106_ir112_nine_cell_source_replay_hypothesis_v2','input_hashes_before':hashes_before,'input_hashes_after':hashes_after,'hashes_unchanged':hashes_before==hashes_after,'source_file_hashes':{str(p.relative_to(ROOT)):sha(p) for p in source_paths},'raw_attrs':attrs,'raw_variable_attrs':var_attrs,'raw_shape':list(words.shape),'cropped_shape_yx':list(counts.shape),'valid_qc_counts':{'all':int((qc==0).sum()),'total':int(qc.size)},'nav_lut':{'sha256':hashlib.sha256(nav_path.read_bytes()).hexdigest(),'valid_cells':int(np.count_nonzero((ri>0)&(rj>0))),'ri_minmax':[float(ri.min()),float(ri.max())],'rj_minmax':[float(rj.min()),float(rj.max())]},'ratio_config_inference':{'ir_resolution_m':2000,'laps_grid_spacing_m':5000,'ratio':float(ratio),'not_historical_runtime_receipt':True},'aggregation_window_pixel_count_unique':[int(x) for x in np.unique(npix)],'source_argument_order':{'process_ir_satellite_call':'tb8, tc8, ta8','satdat2laps_outputs':'sa=mean, sc=extremum, st=warmest','driver_S8A':'ta8; thus source hypothesis is filtered warmest'},'comparison':{'fixed_support_cells':results,'mean_abs_error_actual_vs_filtered_max':sum(errs)/len(errs),'max_abs_error_actual_vs_filtered_max':max(errs)}}
parser=argparse.ArgumentParser()
parser.add_argument('--output',required=True)
out_path=Path(parser.parse_args().output)
payload=json.dumps(out,indent=2,allow_nan=False)+'\n'  # serialize fully before exclusive create
fd=os.open(out_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as f: f.write(payload)
print(json.dumps({'output':str(out_path),'fixed_support_cells':results,'mean_abs_s8a_err':out['comparison']['mean_abs_error_actual_vs_filtered_max'],'max_abs_s8a_err':out['comparison']['max_abs_error_actual_vs_filtered_max'],'mean_abs_s8w_err':sum(abs(x['S8W_minus_mean_K']) for x in results)/len(results),'max_abs_s8w_err':max(abs(x['S8W_minus_mean_K']) for x in results),'hashes_unchanged':out['hashes_unchanged'],'qc_valid':out['valid_qc_counts'],'npix_unique':out['aggregation_window_pixel_count_unique']},indent=2))
