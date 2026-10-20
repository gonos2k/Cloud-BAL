#!/usr/bin/env python3
"""Receipt-bound C12 completed-prefix audit using PR85 policy/stat helpers."""
import gzip, hashlib, json, os, struct, sys
from pathlib import Path
import numpy as np
ROOT=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr91_host_store_20261020/Cloud-BAL')
sys.path.insert(0,str(ROOT/'tools'))
import pr85_joint_stage_trace as stage
EVIDENCE=ROOT/'docs/evidence/pr91_source_store_contract_20261020/c12/runtime'
TRACE_NAME='pr85_joint_moment_stages.raw'
CUTOFF=float(np.nextafter(np.float32(1.e-14),np.float32(-np.inf)))

class HashingReader:
    def __init__(self,path): self.path=Path(path); self.stream=self.path.open('rb'); self.hash=hashlib.sha256()
    def read(self,n=-1):
        b=self.stream.read(n)
        if b: self.hash.update(b)
        return b
    def close(self): self.stream.close()

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''): h.update(b)
    return h.hexdigest()

def parse_stage(root,receipt,arm):
    row=[x for x in receipt['compressed_outputs'] if x['path']==TRACE_NAME]
    if len(row)!=1: raise ValueError(f'{arm}: expected one stage trace receipt row')
    artifact=row[0]; trace=Path(root)/'run'/artifact['compressed_path']
    if trace.stat().st_size!=artifact['compressed_bytes'] if 'compressed_bytes' in artifact else False:
        raise ValueError(f'{arm}: compressed trace size differs from receipt')
    source=HashingReader(trace); records=[]; per_state=[]; steps={}; policy=stage._load_policy()
    bounds,_=stage._policy_bounds(policy,'ice'); tol=[stage._eight_ulp(x) for x in bounds]
    try:
      with gzip.GzipFile(fileobj=source,mode='rb') as stream:
        while True:
          first=stream.read(8)
          if not first: break
          if len(first)!=8: raise EOFError('truncated trace magic')
          label=stream.read(32).decode('ascii').strip()
          hdr=stream.read(60)
          if len(hdr)!=60: raise EOFError('truncated trace header')
          (kind,t,rk,ims,ime,jms,jme,kms,kme,its,ite,jts,jte,kts,kte)=struct.unpack('>15i',hdr)
          magic=first.decode('ascii')
          is_state=kind==1 and magic in ('PR85QND2','PR85QNB1')
          if not is_state and not (kind==2 and magic=='PR85PLB1'):
            raise ValueError(f'{arm}: kind/magic mismatch {kind}/{magic}')
          shape=(jte-jts+1,kte-kts+1,ite-its+1); cells=int(np.prod(shape))
          names=stage.STATE_FIELDS if is_state else stage.PBL_FIELDS
          fields={}
          for name in names:
            raw=stream.read(cells*4)
            if len(raw)!=cells*4: raise EOFError(f'truncated {label} {name}')
            if is_state and t<=receipt['final_completed_step']:
              fields[name]=np.frombuffer(raw,dtype=np.dtype('>f4')).reshape(shape)
          records.append({'kind':kind,'step':t,'rk':rk,'stage':label,'cells':cells})
          if is_state and t<=receipt['final_completed_step']:
            status='AUTHORITATIVE_DRY_FROM_AL_ALB' if magic=='PR85QND2' else 'UNVERIFIED_LEGACY_DECLARATION'
            pairs=stage._pair_stats(fields,policy)
            conv=stage._conversion_stats(fields,status)
            qi=fields['QI'].astype(np.float32); ni=fields['NI'].astype(np.float32)
            valid=np.isfinite(qi)&np.isfinite(ni)&(qi>0)&(ni>0)
            ratio=qi[valid].astype(np.float64)/ni[valid].astype(np.float64)
            outside=(np.maximum(bounds[0]-ratio,0)>tol[0])|(np.maximum(ratio-bounds[1],0)>tol[1])
            qv=qi[valid].astype(np.float64)
            pair_fail={name:{k:v for k,v in value.items() if k in (
                'positive_mass_zero_moment','positive_moment_zero_mass','negative_mass','negative_moment',
                'nonfinite_mass_or_moment') and v} for name,value in pairs.items()}
            cone_fail={name:value['feasible_cone']['outside_beyond_8_float32_ulp_cells']
                       for name,value in pairs.items() if value['feasible_cone']['outside_beyond_8_float32_ulp_cells']}
            conversion_fail={name:{k:v for k,v in value.items() if k!='quantity' and v}
                             for name,value in conv.items() if any(v for k,v in value.items() if k!='quantity')}
            report={'timestep':t,'rkstep':rk,'stage':label,'density_contract_status':status,
                    'pairs':pairs,'pair_failures':pair_fail,'outside_8ulp':cone_fail,
                    'number_conversion_failures':conversion_fail,
                    'ice_native_inactive_split':{'cutoff_real32':CUTOFF,
                       'outlier_cells':int(outside.sum()),'inactive_outliers':int((outside&(qv<=CUTOFF)).sum()),
                       'active_outliers':int((outside&(qv>CUTOFF)).sum())}}
            per_state.append(report); steps.setdefault(t,[]).append(label)
    finally: source.close()
    compressed_sha=source.hash.hexdigest()
    if compressed_sha!=artifact['compressed_sha256']:
      raise ValueError(f'{arm}: compressed trace SHA does not match receipt')
    expected=stage.REQUIRED_STATES
    coverage={str(t):{'states':labs,'expected':list(expected),'pass':tuple(labs)==expected}
              for t,labs in sorted(steps.items())}
    failures=[r for r in per_state if any(r['pair_failures'].values()) or r['outside_8ulp'] or r['number_conversion_failures']]
    return {'trace':{'path':str(trace),'compressed_sha256':compressed_sha,
                     'payload_sha256':artifact['sha256'],'payload_bytes':artifact['bytes'],
                     'record_count':len(records),'records':records},
            'completed_prefix_state_count':len(per_state),'completed_prefix_coverage':coverage,
            'strict_state_failures':failures,'strict_state_status':'PASS' if not failures and all(x['pass'] for x in coverage.values()) else 'FAIL',
            'inactive_ice_cutoff_origin':'REAL32 nearest representable value below 1e-14, matching PR85 native inactive-ice cutoff',
            'inactive_ice_by_state':[{'timestep':r['timestep'],'rkstep':r['rkstep'],'stage':r['stage'],**r['ice_native_inactive_split']} for r in per_state],
            'completed_prefix_state_reports':per_state}

def read_ledger(root):
    budget=Path(root)/'run/pr85_joint_transport_budget.raw.gz'
    source_rows=Path(root)/'run/pr85_joint_source_diffusion.raw.gz'
    lines=gzip.open(budget,'rt').read().splitlines(); current_step=None; joint=[]; fallback=[]; baseline=[]
    for idx,line in enumerate(lines):
      tokens=line.split()
      if not tokens: continue
      if tokens[0]=='BASELINE_JOINT_FEASIBLE':
        current_step=int(tokens[1]); baseline.append({'timestep':int(tokens[1]),'rk':int(tokens[2]),'feasible':tokens[3]=='T'})
      elif tokens[0]=='SOURCE_FIRST_PAIR_FALLBACK':
        fallback.append({'timestep':int(tokens[1]),'rk':int(tokens[2]),'selected':tokens[3:7]})
      elif tokens[0]=='JOINT_RK':
        if idx+1>=len(lines): raise ValueError('truncated JOINT_RK ledger row')
        second=lines[idx+1].split()
        joint.append({'timestep':current_step,'rk':int(tokens[1]),'cells':int(tokens[2]),
                      'max_cfl':float(tokens[3]),'theta':float(second[0]),'feasible':second[1]=='T'})
    proposals=[]
    for line in gzip.open(source_rows,'rt'):
      x=line.split()
      if not x: continue
      if x[0]!='SOURCE_DIFFUSION_DELTA_DT_PRESSURE': raise ValueError(f'unexpected source ledger row {x[0]}')
      step,rk,pair=map(int,x[1:4]); bounds=list(map(int,x[4:10])); vals=list(map(float,x[10:16])); cells=int(x[16])
      match=[r for r in joint if r['timestep']==step and r['rk']==rk and r['feasible']]
      fb=[r for r in fallback if r['timestep']==step and r['rk']==rk]
      proposals.append({'timestep':step,'rk':rk,'pair':pair,'bounds':bounds,'weighted_delta_sum_l1_max_cells':vals,
                        'matching_feasible_joint_rk':match,'matching_source_first_pair_fallback':fb,
                        'applied_by_same_step_rk_commit':bool(match)})
    return {'baseline_feasibility_rows':baseline,'source_first_pair_fallback_rows':fallback,
            'joint_rk_rows':joint,'all_joint_theta_equal_one':bool(joint) and all(r['theta']==1.0 for r in joint),
            'all_joint_rows_feasible':bool(joint) and all(r['feasible'] for r in joint),
            'source_diffusion_proposals':proposals,'source_diffusion_ledger_path':str(source_rows),
            'joint_transport_ledger_path':str(budget)}

def verify_identity(arm):
    low=arm.lower(); root=Path(f'/var/tmp/pr91_{arm}_240s_c12_20261020')
    pre=json.loads((EVIDENCE/f'{low}_preflight.json').read_text()); rec=json.loads((EVIDENCE/f'{low}_receipt.json').read_text())
    build_path=Path(pre['candidate_build']['receipt_path']); build=json.loads(build_path.read_text())
    checks={
      'run_closed_incomplete_rc1_final_step2_seen3':(rec['status']=='INCOMPLETE' and rec['returncode']==1 and rec['final_completed_step']==2 and rec['maximum_seen_timestep']==3),
      'receipt_source_binding':rec['source_receipt_sha256']==pre['source_receipt_sha256'],
      'build_receipt_matches_preflight':sha(build_path)==pre['candidate_build']['receipt_sha256']==rec['candidate_build']['receipt_sha256'],
      'build_receipt_status_pass':build['status']=='PASS_OVERLAY_BUILD',
      'executed_executable_matches_build_and_receipt':rec['executed_executable_sha256']==rec['expected_executed_executable_sha256']==build['executable_sha256'],
      'candidate_wrfinput_matches_preflight':rec['candidate_wrfinput_sha256']==pre['candidate_wrfinput_sha256'],
      'candidate_wrfbdy_matches_preflight':rec['candidate_wrfbdy_sha256']==pre['candidate_wrfbdy_sha256'],
      'candidate_namelist_matches_preflight':rec['candidate_namelist_sha256']==pre['candidate_namelist_sha256'],
      'candidate_build_unchanged':rec['candidate_build_unchanged'],
      'no_changed_original_or_staged_inputs':not rec['changed_original_inputs'] and not rec['changed_staged_inputs'],
    }
    # The runtime tree intentionally replaces the baseline executable and namelist; all other preflight inputs must remain hash-identical.
    mismatches=[]
    for name,want in pre['input_hashes'].items():
      if name in ('wrf.exe','namelist.input'): continue
      path=root/'run'/name
      if not path.exists() or sha(path)!=want: mismatches.append(name)
    checks['all_noncandidate_runtime_inputs_match_preflight']=not mismatches
    checks['candidate_executable_hash']=sha(root/'run/wrf.exe')==build['executable_sha256']
    checks['candidate_namelist_hash']=sha(root/'run/namelist.input')==pre['candidate_namelist_sha256']
    return {'arm':arm,'receipt_sha256':sha(EVIDENCE/f'{low}_receipt.json'),
            'preflight_sha256':sha(EVIDENCE/f'{low}_preflight.json'),'build_receipt_sha256':sha(build_path),
            'executable_sha256':build['executable_sha256'],'input_mismatches_excluding_expected_candidate_replacements':mismatches,
            'checks':checks,'all_checks_pass':all(checks.values()),'run_status':rec['status'],
            'returncode':rec['returncode'],'final_completed_step':rec['final_completed_step'],
            'maximum_seen_timestep':rec['maximum_seen_timestep'],'snapshots':rec['snapshots'],
            'fatal_lines':rec['fatal_lines'],'run_identity':rec['run_identity']}

def main():
  result={'schema':'pr91_c12_closed_runtime_audit_v1','overall_status':'INCOMPLETE: two completed model steps; T3 failed at strict source-stage store; no 600-second attempt run.',
          'arms':{}}
  for arm in ('OFF','COUPLED'):
    low=arm.lower(); root=Path(f'/var/tmp/pr91_{arm}_240s_c12_20261020')
    pre=json.loads((EVIDENCE/f'{low}_preflight.json').read_text()); rec=json.loads((EVIDENCE/f'{low}_receipt.json').read_text())
    result['arms'][arm]={'identity':verify_identity(arm),'completed_prefix':parse_stage(root,rec,arm),
                         'joint_transport':read_ledger(root)}
  out=EVIDENCE/'closed_runtime_audit.json'
  out.write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+'\n')
  print(json.dumps({a:{'identity':v['identity']['all_checks_pass'],
      'status':v['identity']['run_status'],'completed':v['identity']['final_completed_step'],
      'trace_records':v['completed_prefix']['trace']['record_count'],
      'strict_state':v['completed_prefix']['strict_state_status'],
      'theta1':v['joint_transport']['all_joint_theta_equal_one'],
      'feasible':v['joint_transport']['all_joint_rows_feasible'],
      'source_proposals':v['joint_transport']['source_diffusion_proposals']}
      for a,v in result['arms'].items()},indent=2))
if __name__=='__main__': main()
