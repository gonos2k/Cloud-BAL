import csv, hashlib, json
from pathlib import Path
from netCDF4 import Dataset
import numpy as np
root=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/Cloud-BAL')
run=root/'scratch/cp02_six_hour_20260914/hydro/run'
out=Path('/var/tmp/cloudbal-cp02-wrf-first-call/docs/evidence/cp02_wrf_first_call_20261029/inputs')
mapfile=Path('/var/tmp/cloudbal-cp02-wrf-first-call/docs/evidence/cp02_density_controls_20261029/controls/wrf_mapping.csv')
points={}
with mapfile.open(newline='') as f:
 for r in csv.DictReader(f):
  if r['point_id'] in {'P01','P05','P09','P13'}:
   points.setdefault(r['point_id'],r)
# include the four actual surrounding WRF mass-grid cells for each selected mapped point
corners={}
with mapfile.open(newline='') as f:
 for r in csv.DictReader(f):
  if r['point_id'] in points and r['corner'] in {'00','10','01','11'}:
   corners.setdefault(r['point_id'],[]).append(r)
sources={'wrfinput_d01':run/'wrfinput_d01','native_initial_history':run/'wrfout_d01_2026-08-16_12:00:00'}
fields=['QVAPOR','QCLOUD','QRAIN','QICE','QSNOW','QGRAUP','QNCCN','QNCLOUD','QNICE','QNRAIN','QIB']
geometry=['C1H','C2H','C3H','C4H','C1F','C2F','C3F','C4F','ZNU','ZNW','P_TOP']
records=[]; metadata={}; source_hash={}; coeff_rows=[]
for label,path in sources.items():
 source_hash[label]=hashlib.sha256(path.read_bytes()).hexdigest()
 d=Dataset(path)
 metadata[label]={'path':str(path),'sha256':source_hash[label],'dimensions':{k:len(v) for k,v in d.dimensions.items()},'variables':{}}
 for name in fields+geometry:
  if name in d.variables:
   v=d.variables[name]; metadata[label]['variables'][name]={'dims':list(v.dimensions),'shape':list(v.shape),'dtype':str(v.dtype),'units':getattr(v,'units','(attribute absent)')}
 for name in geometry:
  if name in d.variables:
   var=d.variables[name]
   flat=np.asarray(var[:]).reshape(-1)
   for ix,value in enumerate(flat): coeff_rows.append({'source':label,'field':name,'flat_index0':ix,'value':float(value),'units':getattr(var,'units','(attribute absent)')})
 for pid,rs in corners.items():
  for r in rs:
   j,i=int(r['native_j_zero_based']),int(r['native_i_zero_based'])
   lat=float(d.variables['XLAT'][0,j,i]); lon=float(d.variables['XLONG'][0,j,i])
   for k in range(39):
    row={'source':label,'point_id':pid,'role':points[pid]['role'],'corner':r['corner'],'weight':r['weight'],'native_j0':j,'native_i0':i,'level_k0':k,'latitude_deg_n':lat,'longitude_deg_e':lon}
    for name in fields:
     if name in d.variables: row[name]=float(d.variables[name][0,k,j,i])
    records.append(row)
 d.close()
with (out/'wrf_corner_profiles.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(records[0])); w.writeheader(); w.writerows(records)
with (out/'hybrid_coefficients.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(coeff_rows[0])); w.writeheader(); w.writerows(coeff_rows)
# Array byte counts for a float32 WRF mass-grid column bundle and full domain; observed netCDF dtype retained above.
manifest={'purpose':'Read-only extraction from retained HYDRO input and initial-time history; four mapped WRF mass-grid corners per P01/P05/P09/P13.','mapping_csv':str(mapfile),'mapping_sha256':hashlib.sha256(mapfile.read_bytes()).hexdigest(),'sources':metadata,'point_roles':{k:v['role'] for k,v in points.items()},'corners':{k:[{'corner':r['corner'],'j0':int(r['native_j_zero_based']),'i0':int(r['native_i_zero_based']),'weight':float(r['weight'])} for r in corners[k]] for k in corners},'array_abi_sanity':{'dtype':'float32 / 4 bytes per element (NetCDF source dtypes recorded per field)','mass_grid_shape_kji':[39,282,234],'full_mass_grid_bytes_per_field':39*282*234*4,'fourpoint_fourcorner_profile_shape_kp':[39,16],'selected_profile_bytes_per_field':39*16*4,'staggered_vertical_shape_kji':[40,282,234],'full_staggered_vertical_bytes_per_field':40*282*234*4,'warning':'Expected sizes for layout sanity only; not evidence the model consumed these values at its first call.'},'launcher':{'script':str(root/'scratch/cp02_six_hour_20260914/hydro/run.sh'),'binary':str(root/'scratch/cp02_host_unit_contract_x3bcr8ui/host/main/wrf.exe'),'binary_sha256_expected':'de110a7f1d40143a74ffedbe64ed5b3717c413876093f56d200563e2f6b9c168','mpi_command':'timeout 14400 mpirun -np 8','mpi_ranks':8,'omp_threads':1,'environment_script':str(root/'tests/intel_toolchain.sh'),'runtime_env':'source intel_toolchain.sh; export OMP_NUM_THREADS=1; ulimit -s unlimited; run from a fresh copied run directory; do not run real.exe unless explicitly staged; timeout 14400 mpirun -np 8 pinned wrf.exe'},'boundary':{'path':str(run/'wrfbdy_d01'),'sha256':hashlib.sha256((run/'wrfbdy_d01').read_bytes()).hexdigest(),'source_from_prepare':'/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/Cloud-BAL/scratch/cp02_native_12_18_AkoPPp/real/wrfbdy_d01'},'namelist':{'path':str(run/'namelist.input'),'sha256':hashlib.sha256((run/'namelist.input').read_bytes()).hexdigest()},'interpretation':'Native initial-history record is t=12:00:00 output; it may follow startup or integration, so it is not asserted to equal values at the first MP37 call.'}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
