from __future__ import annotations
import hashlib, json, math, sys
from pathlib import Path
import netCDF4
import numpy as np
sys.path.insert(0, '/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr99_native_contract_20261022/Cloud-BAL/tools')
from native_kdm6_trace import read_dump
from pr67_kdm6_process_budget import parse_process_capture
from pr95_call_budget import _read_map_geometry, _bottom_phase_mass

ROOT=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr96_local_closure_20261021/runs_on_lustre')
HIST_REL='run/wrfout_d01_2026-08-16_13:00:00'
RUNS={
 'OFF':Path('/var/tmp/pr100_unowned_diag_replay_clean_20261022/OFF'),
 'HYDRO':Path('/var/tmp/pr100_unowned_root_guarded_20261022/HYDRO'),
 'COUPLED':Path('/var/tmp/pr100_unowned_root_guarded_20261022/COUPLED'),
}
HISTORY={a:ROOT/f'{a}_600s_c1'/HIST_REL for a in RUNS}
GROUND_SOURCES={
 'rain':('pr87_rain_sedimentation_budget.raw','PR87_RAIN_SED',0),
 'graupel':('pr85_graupel_sedimentation_budget.raw','PR85_G_SED',2),
 'ice':('pr85_ice_sedimentation_budget.raw','PR85_ICE_SED',3),
}

def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()
def stats(a: np.ndarray,b:dict) -> dict:
    pos=np.unravel_index(int(np.argmax(a)),a.shape); neg=np.unravel_index(int(np.argmin(a)),a.shape)
    def point(rc):return {'i':int(rc[1]+b['its']),'j':int(rc[0]+b['jts']),'kg':float(a[rc])}
    return {'signed_kg':math.fsum(a.flat),'L1_column_kg':math.fsum(np.abs(a).flat),
            'max_abs_column_kg':float(np.max(np.abs(a))),'largest_positive':point(pos),'most_negative':point(neg)}
def verify_arm(arm: str, run: Path) -> dict:
    pre=run/'kdm6_first_call_pre.raw'; post=run/'kdm6_first_call_post.raw'; process=run/'pr67_kdm6_process.raw'
    if arm=='OFF':
        ref=json.loads(Path('/var/tmp/pr100_snow_fulltile_replay_20261022/OFF_valid/snow_account.json').read_text())
        expected={'pre':ref['pre_sha256'],'post':ref['native_post_sha256'],'process':ref['process_sha256']}
        observed={'pre':sha(pre),'post':sha(post),'process':sha(process)}
        if observed!=expected or ref['all17_and_xland_byte_equal'] is not True or ref['existing_process_stream_byte_equal'] is not True:
            raise ValueError('OFF closed account identity mismatch')
        replay=run/'replay_post.raw'
        if sha(replay)!=expected['post']:raise ValueError('OFF replay endpoint mismatch')
        proof={'kind':'existing validated OFF full-tile C1 replay plus same-hash clean unowned capture',
               'snow_account_sha256':sha(Path('/var/tmp/pr100_snow_fulltile_replay_20261022/OFF_valid/snow_account.json')),
               'pre_sha256':observed['pre'],'native_post_sha256':observed['post'],'pr67_sha256':observed['process'],
               'all17_XLAND_equal':True,'same_call_process_stream_equal':True}
    else:
        receipt_path=run/'receipt.json'; receipt=json.loads(receipt_path.read_text())
        if receipt.get('schema')!='pr100_root_guarded_replay_v1' or receipt.get('arm')!=arm or receipt.get('returncode')!=0 or receipt.get('completion_marker') is not True or receipt.get('post_matches_native') is not True or receipt.get('native_dump_matches') is not True:
            raise ValueError(f'{arm} guarded replay receipt is not closed')
        for name in ('kdm6_first_call_pre.raw','kdm6_first_call_post.raw','pr67_kdm6_process.raw','pr87_rain_sedimentation_budget.raw','pr85_graupel_sedimentation_budget.raw','pr85_ice_sedimentation_budget.raw'):
            row=receipt['artifacts'].get(name)
            if row is None or sha(run/name)!=row['sha256'] or (run/name).stat().st_size!=row['bytes']:
                raise ValueError(f'{arm} artifact does not match receipt: {name}')
        proof={'kind':'root-guarded isolated C1 replay receipt', 'receipt_sha256':sha(receipt_path),
               'launch_manifest_sha256':receipt['launch_manifest_sha256'],'exe_sha256':receipt['executable_sha256'],
               'pre_sha256':receipt['pre_sha256_after'],'native_post_sha256':receipt['artifacts']['kdm6_first_call_post.raw']['sha256'],
               'pr67_sha256':receipt['artifacts']['pr67_kdm6_process.raw']['sha256'],
               'all17_XLAND_equal':receipt['post_matches_native'],'native_dump_matches':receipt['native_dump_matches'],
               'completion_marker':receipt['completion_marker'],'returncode':receipt['returncode']}
    return {'pre':pre,'post':post,'process':process,'proof':proof}

def arm_analysis(arm: str) -> dict:
    run=RUNS[arm]; pin=verify_arm(arm,run); pre=read_dump(pin['pre']); post=read_dump(pin['post']); b=pre['bounds']
    if pre['stage']!=1 or post['stage']!=2 or pre['itimestep']!=1 or post['itimestep']!=1 or pre['bounds']!=post['bounds'] or pre['params']!=post['params']:
        raise ValueError(f'{arm}: not matching T1 endpoint pair')
    if not np.array_equal(read_dump(run/'replay_post.raw')['fields']['XLAND'],post['fields']['XLAND']):raise ValueError(f'{arm}: XLAND mismatch')
    hist=HISTORY[arm]
    with netCDF4.Dataset(hist) as ds:
        ds.set_auto_mask(False); area,_,_=_read_map_geometry(ds,slice(b['jts']-1,b['jte']),slice(b['its']-1,b['ite']))
    stages=parse_process_capture(pin['process'])
    if len(stages)!=3*area.shape[0]:raise ValueError(f'{arm}: incomplete PR67 source rows')
    bottom=np.zeros((4,*area.shape)); public_inc=np.zeros(area.shape); r32=np.float32; denr_values=set();dt_values=set()
    for jj in range(area.shape[0]):
        row=stages[3*jj+2]; denr_values.add(row['denr']);dt_values.add(row['dtcld'])
        bottom[:,jj,:]=_bottom_phase_mass(row['fall'],row['delz'],row['denr'],row['dtcld'],area[jj])
        for ii in range(area.shape[1]):
            f=row['fall'][:,ii].astype(np.float32)
            fall_sum=r32(r32(r32(f[0]+f[1])+f[2])+f[3])
            if fall_sum>0:
                increment=r32(fall_sum*r32(row['delz'][ii])); increment=r32(increment/r32(row['denr']))
                increment=r32(increment*r32(row['dtcld'])); increment=r32(increment*r32(1000.0))
                public_inc[jj,ii]=float(increment)*area[jj,ii]
    if len(denr_values)!=1 or len(dt_values)!=1:raise ValueError(f'{arm}: inconsistent PR67 conversion constants')
    ground={name:np.zeros(area.shape) for name in GROUND_SOURCES}; row_counts={name:0 for name in GROUND_SOURCES}
    for name,(filename,tag,phase) in GROUND_SOURCES.items():
        with (run/filename).open(encoding='ascii') as stream:
            for ln,line in enumerate(stream,1):
                fields=line.split()
                if not fields or fields[0].startswith('#') or fields[0]!=tag:continue
                if len(fields)!=17:raise ValueError(f'{arm}:{filename}:{ln} invalid source row width')
                i,j=map(int,fields[1:3]); values=list(map(float,fields[5:]))
                if len(values)!=12 or not np.isfinite(values).all():raise ValueError(f'{arm}:{filename}:{ln} invalid source terms')
                if not (b['its']<=i<=b['ite'] and b['jts']<=j<=b['jte']):raise ValueError(f'{arm}:{filename}:{ln} outside source bounds')
                ground[name][j-b['jts'],i-b['its']]+=values[6]*area[j-b['jts'],i-b['its']]
                row_counts[name]+=1
    phase_index={'rain':0,'graupel':2,'ice':3}
    mismatch={name:bottom[phase_index[name]]-ground[name] for name in GROUND_SOURCES}
    combined=sum(mismatch.values(),np.zeros(area.shape))
    rain_all=bottom.sum(axis=0)
    public_minus_phase=public_inc-rain_all
    pin['proof']['read_ledger_paths_sha256']={name:sha(run/name) for name in (
        'pr87_rain_sedimentation_budget.raw','pr85_graupel_sedimentation_budget.raw',
        'pr85_ice_sedimentation_budget.raw','pr67_kdm6_process.raw')}
    return {'identity':pin['proof'],'geometry':{'history_path':str(hist),'history_sha256':sha(hist),
            'columns':int(area.size),'map_area_min_m2':float(np.min(area)),'map_area_max_m2':float(np.max(area)),
            'DENR_values':sorted(denr_values),'dtcld_values_seconds':sorted(dt_values)},
        'source_ownership':{
          'approved_ground_field':'values[6] of source PR87_RAIN_SED / PR85_G_SED / PR85_ICE_SED rows; mass per area from source paired-sedimentation helper, multiplied by same-call map area once',
          'phase_map':{'PR87_RAIN_SED':'PR67 stage-2 fall(:,1), rain; REAL64 approved helper source is cast to REAL32 falk and accumulated into REAL32 fall',
                       'PR85_G_SED':'PR67 stage-2 fall(:,3), graupel; REAL64 approved helper source is cast to REAL32 falk and accumulated into REAL32 fall',
                       'PR85_ICE_SED':'PR67 stage-2 fall(:,4), ice; REAL64 approved helper source is cast to REAL32 falk and accumulated into REAL32 fall',
                       'fall(:,2)':'snow component; zero in these calls (source snow account separately has zero ground sink)'},
          'pr87_rain_sedimentation_budget.raw_rows':row_counts['rain'],
          'pr85_graupel_sedimentation_budget.raw_rows':row_counts['graupel'],
          'pr85_ice_sedimentation_budget.raw_rows':row_counts['ice'],
          'source_formula_pins':{'helper-approved-rate':'module_mp_kdm6.F lines 8599-8605 / 8846-8847',
                                 'R32_rate_cast_and_accumulation':'module_mp_kdm6.F lines 2942-2948 and 2955-2964 (rain/graupel); 3065 (ice)',
                                 'bottom_sum_and_public_store':'module_mp_kdm6.F lines 3464-3484'}},
        'actual_PR67_bottom_per_phase_kg':{str(i+1):stats(bottom[i],b) for i in range(4)},
        'source_approved_ground_by_owner_kg':{name:stats(ground[name],b) for name in GROUND_SOURCES},
        'source_boundary_discrepancy_actual_phase_minus_helper_ground_kg':{name:stats(mismatch[name],b) for name in GROUND_SOURCES},
        'combined_ground_boundary_discrepancy_kg':stats(combined,b),
        'public_RAINNCV_increment_formula_reconstruction':{
            'method':'R32 fallSum=fall1+fall2+fall3+fall4, then source-order R32 multiply/divide by DELZ/DENR*dtcld*1000; map area applied once',
            'signed_L1_max_for_reconstructed_increment_kg':stats(public_inc,b),
            'difference_vs_same_call_PR67_phasefall_mass_kg':stats(public_minus_phase,b),
            'limitation':'PR67 records the post-call RAINNCV state but not its pre-call accumulator; this is the source-formula increment reconstruction, not a directly observed RAINNCV before/after delta. Public accumulation is separate from the Q water inventory sink.'}}

out={'schema':'pr100_ground_boundary_ratecast_analysis_v1','scope':'Read-only same-call C1 source-ledger comparison; no build or model run; no correction proposed.',
     'source_pins':{},'arms':{a:arm_analysis(a) for a in RUNS}}
for label,path in {'module_source':'/var/tmp/pr98_native_capture_build_v4_20261022/source/overrides/module_mp_kdm6.F',
                   'bottom_reducer':'/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr99_native_contract_20261022/Cloud-BAL/tools/pr95_call_budget.py',
                   'process_parser':'/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr99_native_contract_20261022/Cloud-BAL/tools/pr67_kdm6_process_budget.py',
                   'face_observer':'/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr99_native_contract_20261022/Cloud-BAL/tools/pr98_budget_face_observer.f90',
                   'instrumented_replay_source':'/var/tmp/pr100_unowned_diag_build2_20261022/source/module_mp_kdm6_snow_unowned.f90',
                   'instrumented_replay_executable':'/var/tmp/pr100_unowned_diag_build2_20261022/link/pr100_unowned_replay.exe'}.items():
    p=Path(path);out['source_pins'][label]={'path':str(p),'sha256':sha(p)}
# OFF previous remainder after the three directly observed paired water transfers, for independent cross-check.
off=json.loads(Path('/var/tmp/pr100_unowned_diag_replay_clean_20261022/one_off_account.json').read_text())
out['OFF_remaining_after_unowned_crosscheck']={'account_sha256':sha(Path('/var/tmp/pr100_unowned_diag_replay_clean_20261022/one_off_account.json')),
    'previous_remainder':off['remainder_after_three_unowned_moves'],
    'ground_boundary_term':out['arms']['OFF']['combined_ground_boundary_discrepancy_kg'],
    'difference_after_subtracting_ground_boundary_term_kg':{
      'signed':off['remainder_after_three_unowned_moves']['signed_kg']-out['arms']['OFF']['combined_ground_boundary_discrepancy_kg']['signed_kg'],
      'L1_difference_not_reconstructed_from_summary_arrays':off['remainder_after_three_unowned_moves']['L1_column_kg']-out['arms']['OFF']['combined_ground_boundary_discrepancy_kg']['L1_column_kg']}}
path=Path('/var/tmp/pr100_ground_boundary_analysis_20261022.json');path.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
print(path,sha(path)); print(json.dumps({a:{'ground':x['combined_ground_boundary_discrepancy_kg'],'public':x['public_RAINNCV_increment_formula_reconstruction']['difference_vs_same_call_PR67_phasefall_mass_kg']} for a,x in out['arms'].items()},indent=2)); print('off_compare',out['OFF_remaining_after_unowned_crosscheck'])
