from __future__ import annotations
import hashlib,json,math,sys
from pathlib import Path
import netCDF4
import numpy as np
repo=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr99_native_contract_20261022/Cloud-BAL')
sys.path.insert(0,str(repo/'tools'));sys.path.insert(0,'/var/tmp/pr100_snow_replay_20261022')
from native_kdm6_trace import read_dump
from pr95_call_budget import _read_map_geometry,_bottom_phase_mass
from pr98_budget import WATER,cutoff_columns
from pr98_budget_faces import compact_face_rows
from pr97_t1_rounding import read_columns
from pr99_compact_stage_reducer import reduce_compact
from pr99_candidate_store_reducer import reduce_public_store,reduce_graupel
import reduce_fulltile_snow_graupel as snow_old
from pr67_kdm6_process_budget import parse_process_capture

RUNS={'OFF':Path('/var/tmp/pr100_unowned_diag_replay_clean_20261022/OFF'),
      'HYDRO':Path('/var/tmp/pr100_unowned_root_guarded_20261022/HYDRO'),
      'COUPLED':Path('/var/tmp/pr100_unowned_root_guarded_20261022/COUPLED')}
HISTBASE=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr96_local_closure_20261021/runs_on_lustre/OFF_600s_c1/run/wrfout_d01_2026-08-16_13:00:00')
OLD=Path('/var/tmp/pr99_compact_stage_runs6_20261022')
V5=repo/'docs/evidence/pr99_t1_remaining_20261022/compact_v5'
SNOW_ACCOUNT=Path('/var/tmp/pr100_snow_replay_20261022/fulltile_snow_graupel_account.json')
GROUND_AUDIT=Path('/var/tmp/pr100_ground_boundary_analysis_20261022.json')
SITES={1:'QI -> QC',2:'QC -> QI complete-freeze shortcut',3:'QR -> QC small-drop conversion'}
GROUND={'rain':('pr87_rain_sedimentation_budget.raw','PR87_RAIN_SED',0),
        'graupel':('pr85_graupel_sedimentation_budget.raw','PR85_G_SED',2),
        'ice':('pr85_ice_sedimentation_budget.raw','PR85_ICE_SED',3)}

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def stats(a,b):
 pos=np.unravel_index(int(np.argmax(a)),a.shape);neg=np.unravel_index(int(np.argmin(a)),a.shape)
 def pt(x):return {'i':int(x[1]+b['its']),'j':int(x[0]+b['jts']),'kg':float(a[x])}
 return {'signed_kg':math.fsum(a.flat),'L1_column_kg':math.fsum(np.abs(a).flat),'max_abs_column_kg':float(np.max(np.abs(a))),
         'largest_positive':pt(pos),'most_negative':pt(neg)}
def verify(arm,run):
 pre=run/'kdm6_first_call_pre.raw';post=run/'kdm6_first_call_post.raw'; process=run/'pr67_kdm6_process.raw'
 if arm=='OFF':
  snow=json.loads(Path('/var/tmp/pr100_snow_fulltile_replay_20261022/OFF_valid/snow_account.json').read_text())
  if (sha(pre),sha(post),sha(process))!=(snow['pre_sha256'],snow['native_post_sha256'],snow['process_sha256']):raise ValueError('OFF C1 identity differs from frozen snow receipt')
  if not snow['all17_and_xland_byte_equal'] or not snow['existing_process_stream_byte_equal']:raise ValueError('OFF proof not byte-identical')
  proof={'receipt_or_account':'/var/tmp/pr100_snow_fulltile_replay_20261022/OFF_valid/snow_account.json','sha256':sha(Path('/var/tmp/pr100_snow_fulltile_replay_20261022/OFF_valid/snow_account.json')),
         'pre_sha256':sha(pre),'native_post_sha256':sha(post),'pr67_sha256':sha(process),'returncode':0,'all17_XLAND_equal':True}
 else:
  rp=run/'receipt.json';r=json.loads(rp.read_text())
  if (r.get('schema'),r.get('arm'),r.get('returncode'),r.get('completion_marker'),r.get('post_matches_native'),r.get('native_dump_matches')) != ('pr100_root_guarded_replay_v1',arm,0,True,True,True):raise ValueError(f'{arm} lacks closed guarded receipt')
  for n,d in r['artifacts'].items():
   if n in ('launch_manifest.json',):continue
   p=run/n
   if not p.is_file() or sha(p)!=d['sha256'] or p.stat().st_size!=d['bytes']:raise ValueError(f'{arm} receipt hash mismatch: {n}')
  proof={'receipt_path':str(rp),'receipt_sha256':sha(rp),'launch_manifest_sha256':r['launch_manifest_sha256'],'executable_sha256':r['executable_sha256'],
         'pre_sha256':sha(pre),'native_post_sha256':sha(post),'pr67_sha256':sha(process),'returncode':0,
         'completion_marker':r['completion_marker'],'all17_XLAND_equal':r['post_matches_native'],'native_dump_matches':r['native_dump_matches']}
 return proof

def arm(arm,run):
 proof=verify(arm,run); pre=read_dump(run/'kdm6_first_call_pre.raw'); post=read_dump(run/'kdm6_first_call_post.raw'); b=pre['bounds']
 if (pre['stage'],post['stage'],pre['itimestep'],post['itimestep'])!=(1,2,1,1) or pre['bounds']!=post['bounds'] or pre['params']!=post['params']:raise ValueError(f'{arm} not one matched T1 call')
 hist=Path(str(HISTBASE).replace('/OFF_600s_c1/',f'/{arm}_600s_c1/'))
 with netCDF4.Dataset(hist) as ds:ds.set_auto_mask(False);area,_,_=_read_map_geometry(ds,slice(b['jts']-1,b['jte']),slice(b['its']-1,b['ite']))
 den=pre['fields']['DEN'].astype(np.float64);dz=pre['fields']['DELZ'].astype(np.float64)
 if not np.isfinite(den).all() or not np.isfinite(dz).all() or np.any(den<=0) or np.any(dz<=0):raise ValueError('invalid active geometry')
 # Reconstruct old v5 residual from original same-call terms and frozen compact v5 observer.
 water=np.zeros_like(den*dz*area[:,None,:])
 for fld in WATER:water+=(post['fields'][fld].astype(np.float64)-pre['fields'][fld].astype(np.float64))*den*dz*area[:,None,:]
 process=run/'pr67_kdm6_process.raw'; raw=water.sum(axis=1,dtype=np.float64)+snow_old.same_call_bottom(process,pre,area)
 cutoff,_,_,_=cutoff_columns(run/'pr85_kdm6_cutoff_budget.raw',b,den,dz,area)
 _,liquid=read_columns(run/'pr97_liquid_columns.raw',b); liquid_term=(liquid[:,:,0]+liquid[:,:,1])*area
 rain,_,_=compact_face_rows(run/'pr87_rain_sedimentation_budget.raw',run/'pr87_rain_sedimentation_budget.raw','PR98_SED_FACE_SUM',3,b,area)
 ice,_,_=compact_face_rows(run/'pr85_ice_sedimentation_budget.raw',run/'pr85_ice_sedimentation_budget.raw','PR98_SED_FACE_SUM',1,b,area)
 baseline=raw-liquid_term-cutoff-rain-ice
 old=OLD/arm; v5path=V5/f'{arm}_candidate_store_account.json';v5=json.loads(v5path.read_text()); inv=v5['input_inventory_sha256']
 for n,h in inv.items():
  path=(old/n) if n=='pr99_process_stage_compact.raw' else run/n
  if sha(path)!=h:raise ValueError(f'{arm}: v5 owned input hash mismatch {n}')
 stage=reduce_compact(old/'pr99_process_stage_compact.raw',b,area)
 stage_store=sum(stage['stage_column_arrays'].values(),np.zeros_like(baseline));stage_packet=sum(stage['packet_column_arrays'].values(),np.zeros_like(baseline))
 open_v4=baseline-stage_store-stage_packet
 _,public,_=reduce_public_store(run/'pr87_qn_public_store.raw',b,area)
 _,graupel,_=reduce_graupel(run/'pr85_graupel_sedimentation_budget.raw',b,area)
 v5res=open_v4-public-graupel
 snow_terms,_=snow_old.read_snow_columns(run/'pr100_snow_columns.raw',b,area)
 gmelt,gm_cov=snow_old.read_gmelt(run/'pr87_graupel_melt.raw',pre,area,b)
 after_snow_gmelt=v5res-snow_terms['stored']-snow_terms['bottom']-gmelt['stored']
 # All source-site summary rows: one fixed row/site/column, count holds taken-branch events.
 site=np.zeros((3,*area.shape)); site_counts=np.zeros((3,*area.shape),dtype=np.int64);seen=set()
 for ln,line in enumerate((run/'pr100_unowned_columns.raw').open(),1):
  f=line.split()
  if len(f)!=8 or f[0]!='PR100_UNOWNED_COLUMN':raise ValueError(f'{arm} bad site summary row {ln}')
  i,j,sid,count=map(int,f[1:5]); sig=float(f[5]); l1=float(f[6]); mx=float(f[7]);key=(i,j,sid)
  if sid not in (1,2,3) or key in seen or not(b['its']<=i<=b['ite'] and b['jts']<=j<=b['jte']) or min(count,l1,mx)<0:raise ValueError(f'{arm} invalid site summary {key}')
  seen.add(key);r=j-b['jts'];c=i-b['its'];site[sid-1,r,c]=sig*area[r,c];site_counts[sid-1,r,c]=count
 expected={(i,j,s) for j in range(b['jts'],b['jte']+1) for i in range(b['its'],b['ite']+1) for s in (1,2,3)}
 if seen!=expected:raise ValueError(f'{arm} summary coverage mismatch')
 after_direct=after_snow_gmelt-site.sum(axis=0)
 # Ground conversion discrepancy: actual R32 phasefall sink minus accepted helper-approved R64 ground packet.
 source_ground={n:np.zeros(area.shape) for n in GROUND};ground_rows={n:0 for n in GROUND}
 for name,(filename,tag,phase) in GROUND.items():
  seen_source=set()
  for ln,line in enumerate((run/filename).open(encoding='ascii'),1):
   f=line.split()
   if not f or f[0].startswith('#') or f[0]!=tag:continue
   if len(f)!=17:raise ValueError(f'{arm} malformed ground-source row {filename}:{ln}')
   i,j,sub,nlev=map(int,f[1:5]); values=list(map(float,f[5:]));key=(i,j,sub)
   if len(values)!=12 or not np.isfinite(values).all() or key in seen_source or not(b['its']<=i<=b['ite'] and b['jts']<=j<=b['jte']):raise ValueError(f'{arm} invalid ground-source row {key}')
   seen_source.add(key);r=j-b['jts'];c=i-b['its'];source_ground[name][r,c]+=values[6]*area[r,c];ground_rows[name]+=1
 stages=parse_process_capture(process); phase_mass={name:np.zeros(area.shape) for name in GROUND}; denrset=set();dtset=set()
 for j in range(area.shape[0]):
  row=stages[3*j+2];denrset.add(row['denr']);dtset.add(row['dtcld'])
  sink=_bottom_phase_mass(row['fall'],row['delz'],row['denr'],row['dtcld'],area[j])
  phase_mass['rain'][j]=sink[0];phase_mass['graupel'][j]=sink[2];phase_mass['ice'][j]=sink[3]
 if len(denrset)!=1 or len(dtset)!=1:raise ValueError(f'{arm} inconsistent denr/dtcld')
 ground={n:phase_mass[n]-source_ground[n] for n in GROUND}
 ground_total=sum(ground.values(),np.zeros(area.shape))
 final=after_direct-ground_total
 normrows=0; normbad=0;normchanged=0;normmax=0.0
 for ln,line in enumerate((run/'pr100_norm_check.raw').open(),1):
  f=line.split()
  if not f:continue
  normrows+=1;normbad+=int(f[3]);normchanged+=int(f[4]);normmax=max(normmax,float(f[5]))
 if normrows!=area.size or normbad or normchanged or normmax!=0.:raise ValueError(f'{arm} normalization proof changed')
 full=json.loads(SNOW_ACCOUNT.read_text())['arms'];frozen=next(x for x in full if x['arm']==arm)
 old_snow=frozen['remaining_after_snow_stored_plus_bottom_and_graupel_melt_stored']
 for k in ('signed_kg','L1_column_kg','max_abs_column_kg'):
  if abs(stats(after_snow_gmelt,b)[k]-old_snow[k])>1e-7*max(1.,abs(old_snow[k])):raise ValueError(f'{arm} old snow stage mismatch {k}')
 public_audit=json.loads(GROUND_AUDIT.read_text())['arms'][arm]['public_RAINNCV_increment_formula_reconstruction']
 return {'identity':proof,'history_sha256':sha(hist),'source_pre_hash':sha(run/'kdm6_first_call_pre.raw'),
   'source_post_hash':sha(run/'kdm6_first_call_post.raw'),'raw_process_sha256':sha(process),
   'reducer_inputs':{'v5_account_sha256':sha(v5path),'v5_compact_stage_sha256':sha(old/'pr99_process_stage_compact.raw'),
      'unowned_summary_sha256':sha(run/'pr100_unowned_columns.raw'),'rain_ground_rows_sha256':sha(run/GROUND['rain'][0]),
      'graupel_ground_rows_sha256':sha(run/GROUND['graupel'][0]),'ice_ground_rows_sha256':sha(run/GROUND['ice'][0]),
      'snow_columns_sha256':sha(run/'pr100_snow_columns.raw'),'graupel_melt_sha256':sha(run/'pr87_graupel_melt.raw')},
   'input_normalization':{'full_columns':normrows,'invalid_preclamp_channel_count':normbad,'changed_channel_count':normchanged,'max_abs_change':normmax},
   'stages':{
    'after_v5_terms_QS_and_Gmelt':stats(after_snow_gmelt,b),
    'after_three_direct_transfers':stats(after_direct,b),
    'identified_ground_boundary_term_actual_R32_phasefall_minus_approved_helper':{n:stats(v,b) for n,v in ground.items()} | {'combined':stats(ground_total,b)},
    'remaining_after_ground_boundary_term':stats(final,b)},
   'owned_process_terms':{
     'QS_stored':stats(snow_terms['stored'],b),'QS_approved_source_packet':stats(snow_terms['packet'],b),
     'QS_storage_arithmetic':stats(snow_terms['diff'],b),'QS_actual_bottom_sink':stats(snow_terms['bottom'],b),
     'graupel_melt_stored':stats(gmelt['stored'],b),'graupel_melt_approved_source_packet':stats(gmelt['packet'],b),
     'graupel_melt_storage_arithmetic':stats(gmelt['diff'],b),
     'direct_transfers':{str(s+1):{'source':SITES[s+1],'signed_kg':stats(site[s],b)['signed_kg'],'L1_column_kg':stats(site[s],b)['L1_column_kg'],
                                  'max_abs_column_kg':stats(site[s],b)['max_abs_column_kg'],'taken_branch_count':int(site_counts[s].sum()),
                                  'columns_with_taken_branches':int(np.count_nonzero(site_counts[s]))} for s in range(3)},
     'ground_source_rows':ground_rows,'ground_conversion_components':{
       n:{'actual_PR67_phasefall':stats(phase_mass[n],b),'approved_helper_ground':stats(source_ground[n],b),'difference_actual_minus_approved':stats(ground[n],b)} for n in GROUND}},
   'public_RAINNCV_increment_formula_reconstruction_not_in_water_closure':public_audit,
   'equation_note':'PR67 bottom phasefall is reconstructed from actual R32 fall arrays (source casts and accumulates approved rates in R32); source helper ground is sum of its accepted R64 packet field. Both are weighted by the same-call map area once. The residual is stepped by subtracting this identified owner; that arithmetic account is not proof of physical closure.'}

summary={a:arm(a,r) for a,r in RUNS.items()}
out={'schema':'pr100_t1_ground_boundary_three_arm_account_v1','scope':'same-call C1 T1, source-owned 3-arm R64 residual decomposition; diagnostic only, no closure or physics claim',
 'source_pins':{'production_module_source':{'path':'/var/tmp/pr98_native_capture_build_v4_20261022/source/overrides/module_mp_kdm6.F','sha256':sha('/var/tmp/pr98_native_capture_build_v4_20261022/source/overrides/module_mp_kdm6.F')},
  'instrumented_source':{'path':'/var/tmp/pr100_unowned_diag_build2_20261022/source/module_mp_kdm6_snow_unowned.f90','sha256':sha('/var/tmp/pr100_unowned_diag_build2_20261022/source/module_mp_kdm6_snow_unowned.f90')},
  'analysis_reducer':{'path':str(Path(__file__)),'sha256':sha(Path(__file__))},
  'ground_boundary_audit':{'path':str(GROUND_AUDIT),'sha256':sha(GROUND_AUDIT)},
  'executable':{'path':'/var/tmp/pr100_unowned_diag_build2_20261022/link/pr100_unowned_replay.exe','sha256':sha('/var/tmp/pr100_unowned_diag_build2_20261022/link/pr100_unowned_replay.exe')},
  'subtraction_source':'helper-approved source ground is subtracted from actual phasefall remainder; no residual fitted term'},
 'arms':summary}
outpath=Path('/var/tmp/pr100_ground_boundary_final_account_20261022.json');outpath.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
print('json',sha(outpath))
for a,x in summary.items():print(a,'after_v5',x['stages']['after_v5_terms_QS_and_Gmelt'],'after_direct',x['stages']['after_three_direct_transfers'],'ground',x['stages']['identified_ground_boundary_term_actual_R32_phasefall_minus_approved_helper']['combined'],'final',x['stages']['remaining_after_ground_boundary_term'])
