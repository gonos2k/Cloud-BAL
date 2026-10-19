#!/usr/bin/env python3
import gzip, hashlib, json, sys, tempfile
from pathlib import Path
import numpy as np
ROOT=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr90_rain_roundtrip_20261019/Cloud-BAL')
sys.path.insert(0,str(ROOT/'tools'))
import pr85_joint_stage_trace as stage
import pr87_completed_state_audit as completed

def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''): h.update(b)
 return h.hexdigest()
def artifact(receipt, name):
 rows=[x for x in receipt['compressed_outputs'] if x['path']==name]
 if len(rows)!=1: raise ValueError(f'artifact {name}: {len(rows)} rows')
 return rows[0]
def verify_run(arm):
 root=Path(f'/var/tmp/pr90_{arm}_180s_c6_20261019')
 recp=root/'receipt.json'; prep=root/'preflight.json'
 rec=json.loads(recp.read_text()); pre=json.loads(prep.read_text())
 if (rec['status']!='INCOMPLETE' or rec['returncode']!=128 or rec['final_completed_step']!=7 or rec['timestep_count']!=7):
  raise ValueError((arm,'unexpected run closure',rec['status'],rec['returncode'],rec['final_completed_step'],rec['timestep_count']))
 if rec['source_receipt_sha256']!=pre['source_receipt_sha256']:
  raise ValueError((arm,'source receipt binding mismatch'))
 build=Path(rec['candidate_build']['receipt_path'])
 if sha(build)!=rec['candidate_build']['receipt_sha256'] or sha(build)!=pre['candidate_build']['receipt_sha256']:
  raise ValueError((arm,'build receipt hash mismatch'))
 b=json.loads(build.read_text()); exe=Path(b['executable_path'])
 if sha(exe)!=rec['executed_executable_sha256'] or rec['executed_executable_sha256']!=rec['expected_executed_executable_sha256']:
  raise ValueError((arm,'executable binding mismatch'))
 for member,row in b['source_overrides'].items():
  if sha(Path(row['staged_path']))!=row['staged_sha256'] or row['staged_sha256']!=row['requested_sha256']:
   raise ValueError((arm,'source override mismatch',member))
 ledger=artifact(rec,'pr85_joint_moment_stages.raw')
 compressed=root/'run'/ledger['compressed_path']
 if sha(compressed)!=ledger['compressed_sha256']: raise ValueError((arm,'trace gzip hash mismatch'))
 return {'root':str(root),'receipt_path':str(recp),'receipt_sha256':sha(recp),'preflight_sha256':sha(prep),'status':rec['status'],'returncode':rec['returncode'],'final_completed_step':rec['final_completed_step'],'timestep_count':rec['timestep_count'],'model_timestamps':rec['model_timestamps'],'fatal_lines':rec['fatal_lines'],'source_receipt_sha256':rec['source_receipt_sha256'],'build_receipt_path':str(build),'build_receipt_sha256':sha(build),'executable_path':str(exe),'executable_sha256':sha(exe),'trace_path':str(compressed),'trace_compressed_sha256':sha(compressed),'trace_payload_sha256':ledger['sha256'],'trace_payload_bytes':ledger['bytes'],'trace_records':rec['snapshots']['record_count'],'completed_post_kdm6_timesteps':rec['snapshots']['completed_post_kdm6_timesteps'],'execution_layout':rec['execution_layout'],'build':b}
def prefix_compare(arm, c6):
 oldroot=Path(f'/var/tmp/pr89_{arm}_120s_c5_20261019')
 oldrec=json.loads((oldroot/'receipt.json').read_text())
 old=artifact(oldrec,'pr85_joint_moment_stages.raw')
 newrec=json.loads(Path(c6['receipt_path']).read_text())
 new=artifact(newrec,'pr85_joint_moment_stages.raw')
 if old['bytes']!=5042096500: raise ValueError((arm,'unexpected C5 prefix bytes',old['bytes']))
 oldp=oldroot/'run'/old['compressed_path']; newp=Path(c6['trace_path'])
 oldh=hashlib.sha256(); newh=hashlib.sha256(); compared=0
 with gzip.open(oldp,'rb') as a, gzip.open(newp,'rb') as b:
  remain=old['bytes']
  while remain:
   n=min(remain,8*1024*1024); x=a.read(n); y=b.read(n)
   if len(x)!=n or len(y)!=n: raise ValueError((arm,'truncated prefix'))
   if x!=y: raise ValueError((arm,'prefix byte difference',compared))
   oldh.update(x); newh.update(y); compared+=n; remain-=n
 return {'bytes_compared':compared,'exact_match':True,'c5_prefix_sha256':oldh.hexdigest(),'c6_prefix_sha256':newh.hexdigest(),'c5_trace_gzip_sha256':sha(oldp),'c5_trace_payload_sha256':old['sha256']}
def ice_split(arm, c6):
 policy=stage._load_policy(); bounds,_=stage._policy_bounds(policy,'ice')
 tol=[stage._eight_ulp(x) for x in bounds]
 cutoff=float(np.float32(1.0e-14))
 p=Path(c6['trace_path'])
 with tempfile.TemporaryDirectory(prefix=f'pr90_{arm}_ice_split_') as tmp:
  raw=Path(tmp)/'trace.raw'
  with gzip.open(p,'rb') as z,raw.open('wb') as out:
   for block in iter(lambda:z.read(8*1024*1024),b''):out.write(block)
  recs=stage.read_records(raw)['records']
  out=[]
  for r in recs:
   if r['kind']!=1: continue
   f=r['fields']; qi=np.asarray(f['QI'],dtype=np.float32); ni=np.asarray(f['NI'],dtype=np.float32)
   valid=np.isfinite(qi)&np.isfinite(ni)&(qi>0)&(ni>0)
   ratio=qi[valid].astype(np.float64)/ni[valid].astype(np.float64)
   below=np.maximum(bounds[0]-ratio,0.0); above=np.maximum(ratio-bounds[1],0.0)
   outside=(below>tol[0])|(above>tol[1])
   qival=qi[valid].astype(np.float64)
   inactive=outside&(qival<=cutoff); active=outside&(qival>cutoff)
   if int(outside.sum()):
    out.append({'timestep':r['timestep'],'rkstep':r['rkstep'],'stage':r['stage'],'valid_positive_ice_pairs':int(valid.sum()),'all_positive_ice_outside_8ulp':int(outside.sum()),'inactive_outliers':int(inactive.sum()),'active_outliers':int(active.sum()),'outlier_qi_min':float(qival[outside].min()),'outlier_qi_max':float(qival[outside].max())})
 return {'native_inactive_cutoff_real32':cutoff,'source': 'module_mp_kdm6.F: PR85_ICE_NATIVE_INACTIVE_MAX=NEAREST(1.e-14,-1.0); exact promoted REAL32 cutoff','cone_bounds':bounds,'eight_ulp_tolerances':tol,'scope':'all complete state records in stage trace, including partial T8 pre-KDM6/rk states; classify source-native inactive mass separately, no tolerance change','outlier_gates':out}

result={'schema':'pr90_c6_incomplete_runtime_audit_v1','arms':{}}
for arm in ('OFF','COUPLED'):
 x=verify_run(arm)
 x['prefix_comparison_to_c5_off_or_coupled_120s']=prefix_compare(arm,x)
 # Whole-array auditor result is generated separately with the maintained auditor.
 audit=json.loads(Path(f'/var/tmp/pr90_{arm}_180s_c6_20261019_completed_state_audit.json').read_text())
 x['completed_state_audit']={'path':f'/var/tmp/pr90_{arm}_180s_c6_20261019_completed_state_audit.json','sha256':sha(Path(f'/var/tmp/pr90_{arm}_180s_c6_20261019_completed_state_audit.json')),'status':audit['status'],'state_record_count':audit['state_record_count'],'state_stage_counts':audit['state_stage_counts'],'trace_timesteps':audit['trace_timesteps'],'completed_post_kdm6_timestep_count':audit['completed_post_kdm6_timestep_count'],'completed_post_kdm6_timesteps':x['completed_post_kdm6_timesteps'],'per_timestep_status':{str(t['timestep']):{'status':t['status'],'post_kdm6_complete':t['completed_post_kdm6'],'state_sequence_complete':t['required_state_sequence_complete'],'rk_sequence_complete':t['required_rkstep_sequence_complete'],'first_violation':t['first_recorded_state_violation']} for t in audit['timestep_audits']}}
 x['source_inactive_ice_split']=ice_split(arm,x)
 result['arms'][arm]=x
out=Path('/var/tmp/pr90_c6_incomplete_runtime_audit_20261019.json')
out.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
print(json.dumps({arm:{'status':v['status'],'returncode':v['returncode'],'completed_step':v['final_completed_step'],'prefix':v['prefix_comparison_to_c5_off_or_coupled_120s'],'ice_gates':v['source_inactive_ice_split']['outlier_gates']} for arm,v in result['arms'].items()},indent=2))
