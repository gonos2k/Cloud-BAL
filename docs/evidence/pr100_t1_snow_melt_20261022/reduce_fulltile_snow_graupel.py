from __future__ import annotations
import hashlib, json, math, sys, struct
from collections import defaultdict
from pathlib import Path
import netCDF4
import numpy as np
repo=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr99_native_contract_20261022/Cloud-BAL')
sys.path.insert(0,str(repo/'tools'))
from native_kdm6_trace import read_dump
from pr95_call_budget import _read_map_geometry
from pr98_budget import WATER, cutoff_columns, same_call_bottom
from pr98_budget_faces import compact_face_rows
from pr97_t1_rounding import read_columns
from pr99_compact_stage_reducer import reduce_compact
from pr99_candidate_store_reducer import reduce_public_store, reduce_graupel, column_summary
BASE=Path('/var/tmp/pr100_snow_fulltile_replay_20261022')
OLD=Path('/var/tmp/pr99_compact_stage_runs6_20261022')
ACCT=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr99_native_contract_20261022/Cloud-BAL/docs/evidence/pr99_t1_remaining_20261022/compact_v5')
HISTORY=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr96_local_closure_20261021/runs_on_lustre/OFF_600s_c1/run/wrfout_d01_2026-08-16_13:00:00')
HIST_BY_ARM={a:Path(str(HISTORY).replace('/OFF_600s_c1/',f'/{a}_600s_c1/')) for a in ('OFF','HYDRO','COUPLED')}

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def col_stats(v,b):
    pos=np.unravel_index(int(np.argmax(v)),v.shape); neg=np.unravel_index(int(np.argmin(v)),v.shape)
    def point(rc): return {'i':int(rc[1]+b['its']),'j':int(rc[0]+b['jts']),'kg':float(v[rc])}
    return {'signed_kg':math.fsum(v.flat),'L1_column_kg':math.fsum(np.abs(v).flat),
      'max_abs_column_kg':float(np.max(np.abs(v))), 'largest_positive':point(pos), 'most_negative':point(neg)}
def read_snow_columns(path,bounds,area):
    shape=area.shape
    vals={n:np.zeros(shape,dtype=np.float64) for n in ('stored','packet','diff','stored_l1','packet_l1','diff_l1','stored_max','packet_max','diff_max','bottom','bottom_r32')}
    seen=set(); counts=[]; steps=[]; bottomloops=[]
    with Path(path).open() as fh:
      for ln,line in enumerate(fh,1):
        f=line.split()
        if len(f)!=18 or f[0]!='PR100_SNOW_COLUMN':raise ValueError(f'bad snow column row {ln}')
        i,j,count,clamp,step,bloops=map(int,f[1:7]); x=np.array(f[7:],dtype=np.float64)
        if x.shape!=(11,) or not np.isfinite(x).all():raise ValueError('invalid snow column values')
        if not (bounds['its']<=i<=bounds['ite'] and bounds['jts']<=j<=bounds['jte']):raise ValueError('snow col outside tile')
        key=(i,j)
        if key in seen:raise ValueError(f'duplicate snow column {key}')
        seen.add(key); row=j-bounds['jts']; col=i-bounds['its']; a=area[row,col]
        for name,v in zip(vals,x): vals[name][row,col]=v*a
        counts.append(count); steps.append(step); bottomloops.append(bloops)
    expected={(i,j) for j in range(bounds['jts'],bounds['jte']+1) for i in range(bounds['its'],bounds['ite']+1)}
    if seen!=expected: raise ValueError(f'snow column coverage missing={len(expected-seen)} extra={len(seen-expected)}')
    return vals,{'columns':len(seen),'rows':len(seen),'event_count_min':min(counts),'event_count_max':max(counts),
                 'step_masks':dict((str(x),steps.count(x)) for x in sorted(set(steps))),
                 'bottom_loop_min':min(bottomloops),'bottom_loop_max':max(bottomloops)}
def read_gmelt(path,pre,area,bounds):
    shape=area.shape
    stored=np.zeros(shape); approved=np.zeros(shape); arithmetic=np.zeros(shape)
    event_store=[]; event_packet=[]; bycol=defaultdict(int); seen=set(); rows=0; zero_packet=0; max_pair=0.; max_resid_err=0.
    den=pre['fields']['DEN'].astype(np.float64); dz=pre['fields']['DELZ'].astype(np.float64)
    for ln,line in enumerate(Path(path).read_text().splitlines(),1):
      f=line.split()
      if not f:continue
      if f[0].startswith('#'):continue
      if f[0]!='PR87_GRAUPEL_MELT':raise ValueError(f'unexpected G melt row {ln} tag={f[0]}')
      if len(f)!=32:raise ValueError(f'G melt row {ln}: token count {len(f)}')
      i,j,k,loop=map(int,f[1:5]); statusbool=f[5]
      if len(statusbool)!=2 or statusbool[-1].upper() not in ('T','F'):raise ValueError(f'bad status+logical {statusbool}')
      status=int(statusbool[0]); feasible=statusbool[-1].upper()=='T'; v=list(map(float,f[6:]))
      if len(v)!=26 or not np.isfinite(v).all():raise ValueError(f'nonfinite/malformed G melt row {ln}')
      if not feasible: raise ValueError(f'infeasible source event recorded at {i},{j},{k}')
      if not(bounds['its']<=i<=bounds['ite'] and bounds['jts']<=j<=bounds['jte'] and bounds['kts']<=k<=bounds['kte']):raise ValueError('G melt row out of bounds')
      key=(i,j,k,loop)
      if key in seen:raise ValueError(f'duplicate G melt row {key}')
      seen.add(key); rows+=1; row=j-bounds['jts']; col=i-bounds['its']; lev=k-bounds['kts']; weight=den[row,lev,col]*dz[row,lev,col]*area[row,col]
      alpha,dt=v[:2]; qgb,qgp,qga,qgx=v[2:6]; qrb,qrp,qra,qrx=v[10:14]
      # The process vector has equal and opposite represented R32 entries; alpha multiplies each in R32.
      if np.float32(qgp)+np.float32(qrp)!=np.float32(0):raise ValueError(f'proposed QG/QR packet not opposite at {key}')
      if np.float32(alpha)*np.float32(qgp)!=np.float32(qga) or np.float32(alpha)*np.float32(qrp)!=np.float32(qra):raise ValueError(f'approved alpha operands mismatch at {key}')
      packet_r32=np.float32(qga)+np.float32(qra)
      if packet_r32==0:zero_packet+=1
      max_pair=max(max_pair,abs(float(packet_r32)))
      st=(qgx-qgb)+(qrx-qrb)
      source_expr=((qgx-qgb)+qrx)-qrb
      err=source_expr-v[22]
      max_resid_err=max(max_resid_err,abs(err))
      if err!=0.0: raise ValueError(f'source mass residual expression mismatch at {key}: {err!r}')
      wstore=st*weight; wpacket=float(np.float64(qga)+np.float64(qra))*weight; wdiff=(st-(qga+qra))*weight
      stored[row,col]+=wstore; approved[row,col]+=wpacket; arithmetic[row,col]+=wdiff
      event_store.append(wstore); event_packet.append(wpacket); bycol[(i,j)]+=1
    return {'stored':stored,'packet':approved,'diff':arithmetic}, {
      'rows':rows,'columns_with_events':len(bycol),'event_count_min_per_event_column':min(bycol.values()) if bycol else 0,
      'event_count_max_per_event_column':max(bycol.values()) if bycol else 0,
      'paired_approved_zero_event_count_R32':zero_packet,'max_abs_R32_approved_pair_kg_per_kg_dry':max_pair,
      'event_stored_signed_kg':math.fsum(event_store),'event_stored_L1_kg':math.fsum(abs(x) for x in event_store),
      'event_packet_signed_kg':math.fsum(event_packet),'event_packet_L1_kg':math.fsum(abs(x) for x in event_packet),
      'max_abs_logged_source_mass_residual_roundtrip_error':max_resid_err,'note':'actual per-species R64 deltas are summed as (QG_after-QG_before)+(QR_after-QR_before); source row residual is independently checked in source left-associative order (QG_after-QG_before+QR_after-QR_before), which can differ by R64 rounding.'}
def analyze(arm):
  run=BASE/(arm if arm!='OFF' else 'OFF_valid'); old=OLD/arm; acct=json.loads((ACCT/f'{arm}_candidate_store_account.json').read_text())
  native=run; pre=read_dump(native/'kdm6_first_call_pre.raw'); post=read_dump(native/'native_post.raw'); bounds=pre['bounds']
  with netCDF4.Dataset(HIST_BY_ARM[arm]) as ds:
    ds.set_auto_mask(False); area,_,_=_read_map_geometry(ds,slice(bounds['jts']-1,bounds['jte']),slice(bounds['its']-1,bounds['ite']))
  for field in post['fields']:
    if not np.array_equal(post['fields'][field],read_dump(run/'replay_post.raw')['fields'][field]):raise ValueError(f'{arm}: replay field mismatch {field}')
  # Validate all preserved v5 inputs except compact-stage rows, which are reused from its pinned same-call capture.
  inv=acct['input_inventory_sha256']
  for nm,h in inv.items():
    pp=(old/nm) if nm=='pr99_process_stage_compact.raw' else (run/nm)
    if sha(pp)!=h:raise ValueError(f'{arm}: changed v5 input {nm}: {sha(pp)} != {h}')
  den=pre['fields']['DEN'].astype(np.float64); dz=pre['fields']['DELZ'].astype(np.float64)
  water_delta=np.zeros_like(den*dz*area[:,None,:])
  for field in WATER: water_delta+=(post['fields'][field].astype(np.float64)-pre['fields'][field].astype(np.float64))*den*dz*area[:,None,:]
  raw=np.sum(water_delta,axis=1,dtype=np.float64)+same_call_bottom(run/'pr67_kdm6_process.raw',pre,area)
  cutoff,_,_,_=cutoff_columns(run/'pr85_kdm6_cutoff_budget.raw',bounds,den,dz,area)
  _,liquid=read_columns(run/'pr97_liquid_columns.raw',bounds)
  rain,_,_=compact_face_rows(run/'pr87_rain_sedimentation_budget.raw',run/'pr87_rain_sedimentation_budget.raw','PR98_SED_FACE_SUM',3,bounds,area)
  ice,_,_=compact_face_rows(run/'pr85_ice_sedimentation_budget.raw',run/'pr85_ice_sedimentation_budget.raw','PR98_SED_FACE_SUM',1,bounds,area)
  baseline=raw-(liquid[:,:,0]+liquid[:,:,1])*area-cutoff-rain-ice
  stage=reduce_compact(old/'pr99_process_stage_compact.raw',bounds,area)
  process=sum(stage['stage_column_arrays'].values(),np.zeros_like(baseline)); packet_stage=sum(stage['packet_column_arrays'].values(),np.zeros_like(baseline))
  open_v4=baseline-process-packet_stage
  _,public,_=reduce_public_store(run/'pr87_qn_public_store.raw',bounds,area)
  _,graupel,_=reduce_graupel(run/'pr85_graupel_sedimentation_budget.raw',bounds,area)
  oldfinal=open_v4-public-graupel
  old_summary=col_stats(oldfinal,bounds)
  for name in ('signed_kg','L1_column_kg','max_abs_column_kg'):
    exp=acct['open_after_two_additional_source_terms'][name]
    if abs(old_summary[name]-exp)>1e-7*max(1.,abs(exp)):raise ValueError(f'{arm}: rebuilt v5 {name} mismatch {old_summary[name]} vs {exp}')
  qs,qs_cov=read_snow_columns(run/'pr100_snow_columns.raw',bounds,area)
  gm,gm_cov=read_gmelt(run/'pr87_graupel_melt.raw',pre,area,bounds)
  newfinal=oldfinal-qs['stored']-qs['bottom']-gm['stored']
  return {'arm':arm,'identity':{'exe_sha256':sha(run/'replay.exe'),'pre_sha256':sha(run/'kdm6_first_call_pre.raw'),'native_post_sha256':sha(run/'native_post.raw'),'replay_post_sha256':sha(run/'replay_post.raw'),'snow_compact_sha256':sha(run/'pr100_snow_columns.raw'),'snow_events_sha256':sha(run/'pr100_snow_sedimentation.raw'),'graupel_melt_sha256':sha(run/'pr87_graupel_melt.raw'),'v5_stage_capture_reused_sha256':sha(old/'pr99_process_stage_compact.raw'),'history_sha256':sha(HIST_BY_ARM[arm])},
   'reused_v5_final_verified':old_summary,'snow_coverage':qs_cov,'snow_terms':{k:col_stats(v,bounds) for k,v in qs.items()},'graupel_melt_coverage_and_checks':gm_cov,'graupel_melt_terms':{k:col_stats(v,bounds) for k,v in gm.items()},'remaining_after_snow_stored_plus_bottom_and_graupel_melt_stored':col_stats(newfinal,bounds),
   'selected_columns':{f'{i},{j}':{'old_v5_open_kg':float(oldfinal[j-bounds['jts'],i-bounds['its']]),'snow_stored_kg':float(qs['stored'][j-bounds['jts'],i-bounds['its']]),'snow_ground_kg':float(qs['bottom'][j-bounds['jts'],i-bounds['its']]),'snow_approved_packet_kg':float(qs['packet'][j-bounds['jts'],i-bounds['its']]),'snow_storage_arithmetic_kg':float(qs['diff'][j-bounds['jts'],i-bounds['its']]),'graupel_melt_stored_kg':float(gm['stored'][j-bounds['jts'],i-bounds['its']]),'graupel_melt_approved_packet_kg':float(gm['packet'][j-bounds['jts'],i-bounds['its']]),'graupel_melt_arithmetic_kg':float(gm['diff'][j-bounds['jts'],i-bounds['its']]),'new_remaining_kg':float(newfinal[j-bounds['jts'],i-bounds['its']])} for i,j in ((169,227),(146,215))}}
if __name__=='__main__':
 out={'schema':'pr100_c1_snow_and_graupel_melt_account_v1','scope':'C1 first-call T1 replay, full active tile; fixed DEN*DELZ and same-call map area; R64 reductions','arms':[analyze(a) for a in ('OFF','HYDRO','COUPLED')]}
 dest=Path('/var/tmp/pr100_snow_replay_20261022/fulltile_snow_graupel_account.json'); dest.write_text(json.dumps(out,indent=2)+'\n'); print(json.dumps(out,indent=2))
