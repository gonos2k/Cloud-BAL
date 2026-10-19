#!/usr/bin/env python3
import gzip, hashlib, json, struct, sys
from pathlib import Path
import numpy as np
ROOT=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr90_rain_roundtrip_20261019/Cloud-BAL')
sys.path.insert(0,str(ROOT/'tools'))
import pr85_joint_stage_trace as stage

def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
def read_exact(f,n):
 b=f.read(n)
 if len(b)!=n:raise EOFError(f'wanted {n}, got {len(b)}')
 return b
def analyze(arm):
 root=Path(f'/var/tmp/pr90_{arm}_180s_c7_20261019')
 rec=json.loads((root/'receipt.json').read_text()); pre=json.loads((root/'preflight.json').read_text())
 if rec['status']!='COMPLETE' or rec['returncode']!=0 or rec['final_completed_step']!=9 or rec['timestep_count']!=9:raise ValueError((arm,'not nine-step COMPLETE'))
 if rec['source_receipt_sha256']!=pre['source_receipt_sha256']:raise ValueError((arm,'source binding'))
 build=Path(rec['candidate_build']['receipt_path'])
 if sha(build)!=rec['candidate_build']['receipt_sha256'] or sha(build)!=pre['candidate_build']['receipt_sha256']:raise ValueError((arm,'build binding'))
 b=json.loads(build.read_text()); exe=Path(b['executable_path'])
 if sha(exe)!=rec['executed_executable_sha256'] or rec['executed_executable_sha256']!=rec['expected_executed_executable_sha256']:raise ValueError((arm,'exe binding'))
 if sha(exe)!=b['executable_sha256']:raise ValueError((arm,'build exe hash'))
 for member,row in b['source_overrides'].items():
  if sha(Path(row['staged_path']))!=row['staged_sha256'] or row['staged_sha256']!=row['requested_sha256']:raise ValueError((arm,'source override',member))
 artifact=[x for x in rec['compressed_outputs'] if x['path']=='pr85_joint_moment_stages.raw']
 if len(artifact)!=1:raise ValueError((arm,'trace ledger'))
 artifact=artifact[0]; trace=root/'run'/artifact['compressed_path']
 if sha(trace)!=artifact['compressed_sha256']:raise ValueError((arm,'trace binding'))
 pol=stage._load_policy(); bounds,_=stage._policy_bounds(pol,'ice');tol=[stage._eight_ulp(v) for v in bounds]
 cutoff=float(np.nextafter(np.float32(1.e-14),np.float32(-np.inf)))
 gates=[]; target=None; records=0; states=0; timesteps=set()
 with gzip.open(trace,'rb') as f:
  while True:
   magic=f.read(8)
   if not magic:break
   label=read_exact(f,32).decode('ascii').strip()
   hdr=struct.unpack('>15i',read_exact(f,60));kind,t,rk,ims,ime,jms,jme,kms,kme,its,ite,jts,jte,kts,kte=hdr
   timesteps.add(t); records+=1
   names=stage.STATE_FIELDS if kind==1 else stage.PBL_FIELDS
   shape=(jte-jts+1,kte-kts+1,ite-its+1); cells=int(np.prod(shape)); arrays={}
   for name in names:
    buf=read_exact(f,cells*4)
    if kind==1 and name in ('QI','NI','QR','NR','DEN'):
     arrays[name]=np.frombuffer(buf,dtype='>f4').astype(np.float32,copy=False).reshape(shape)
   if kind==1:
    states+=1
    qi=arrays['QI'];ni=arrays['NI'];valid=np.isfinite(qi)&np.isfinite(ni)&(qi>0)&(ni>0)
    ratio=qi[valid].astype(np.float64)/ni[valid].astype(np.float64)
    out=(np.maximum(bounds[0]-ratio,0)>tol[0])|(np.maximum(ratio-bounds[1],0)>tol[1])
    qv=qi[valid].astype(np.float64);inactive=out&(qv<=cutoff);active=out&(qv>cutoff)
    if out.sum(): gates.append({'timestep':t,'rkstep':rk,'stage':label,'valid_positive_ice_pairs':int(valid.sum()),'outside_8ulp':int(out.sum()),'inactive':int(inactive.sum()),'active':int(active.sum()),'qi_min':float(qv[out].min()),'qi_max':float(qv[out].max())})
    if t==8 and label=='POST_KDM6':
     ii,jj,kk=188,222,5
     loc=(jj-jts,kk-kts,ii-its)
     if all(0<=loc[n]<shape[n] for n in range(3)):
      def val(field):
       x=arrays[field][loc]
       return {'decimal':float(x),'hex':struct.pack('>f',float(x)).hex().upper()}
      target={'global_i_j_k':[ii,jj,kk],'record_bounds':{'its':its,'ite':ite,'jts':jts,'jte':jte,'kts':kts,'kte':kte},'QR_kg_per_kgdry':val('QR'),'NR_public_per_kgdry':val('NR'),'DEN_kg_per_m3':val('DEN'),'source_call_status':'POST_KDM6 record after timestep 8 KDM6 call returned normally'}
     else:target={'global_i_j_k':[ii,jj,kk],'active_bounds':{'its':its,'ite':ite,'jts':jts,'jte':jte,'kts':kts,'kte':kte},'present':False}
 return {'arm':arm,'status':rec['status'],'completed_steps':rec['final_completed_step'],'timestep_count':rec['timestep_count'],'receipt_path':str(root/'receipt.json'),'receipt_sha256':sha(root/'receipt.json'),'preflight_sha256':sha(root/'preflight.json'),'source_receipt_sha256':rec['source_receipt_sha256'],'build_receipt_path':str(build),'build_receipt_sha256':sha(build),'executable_path':str(exe),'executable_sha256':sha(exe),'trace_path':str(trace),'trace_compressed_sha256':sha(trace),'trace_payload_sha256':artifact['sha256'],'trace_payload_bytes':artifact['bytes'],'trace_records':records,'state_records':states,'timesteps':sorted(timesteps),'source_inactive_ice_split':{'source_cutoff_real32':cutoff,'source':'module_mp_kdm6.F PR85_ICE_NATIVE_INACTIVE_MAX=NEAREST(1.e-14,-1.0)','cone_bounds':bounds,'eight_ulp_tolerances':tol,'outlier_gates':gates,'scope':'all positive finite QI/NI state pairs; generic 8-ULP FAIL is preserved separately'},'t8_post_kdm6_target':target}
res={'schema':'pr90_c7_complete_runtime_target_ice_audit_v1','arms':{a:analyze(a) for a in ('OFF','COUPLED')}}
Path('/var/tmp/pr90_c7_complete_runtime_target_ice_audit_20261019.json').write_text(json.dumps(res,indent=2,sort_keys=True)+'\n')
print(json.dumps({a:{'status':x['status'],'steps':x['completed_steps'],'records':x['trace_records'],'target':x['t8_post_kdm6_target'],'ice_outlier_states':x['source_inactive_ice_split']['outlier_gates']} for a,x in res['arms'].items()},indent=2))
