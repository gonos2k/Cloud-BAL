from pathlib import Path
import numpy as np,struct,json,hashlib,sys
repo=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr87_two_step_20261016/Cloud-BAL')
sys.path.insert(0,str(repo/'tools'));from pr87_completed_state_audit import _strict_source_checks,_strict_source_violations
import pr85_joint_stage_trace as trace
p=Path('/var/tmp/pr87_component_T3_full_v44_20261019');raw=(p/'kdm6_first_call_post.raw').read_bytes();b=struct.unpack('>20i',raw[8:88]);nx=b[9]-b[8]+1;nk=b[13]-b[12]+1;nj=b[11]-b[10]+1;cells=nx*nk*nj;off=108;fields={}
sl=(slice(b[16]-b[10],b[17]-b[10]+1),slice(b[18]-b[12],b[19]-b[12]+1),slice(b[14]-b[8],b[15]-b[8]+1))
for k in range(17):
 name=raw[off:off+8].decode().strip();off+=8;arr=np.frombuffer(raw,dtype='>f4',count=cells,offset=off).reshape((nj,nk,nx))[sl].astype('f4');off+=cells*4;fields[name]=arr
checks=_strict_source_checks(fields);bad=_strict_source_violations(checks)
policy_pairs=trace._pair_stats(fields,trace._load_policy())
policy_bad={name: row for name,row in policy_pairs.items() if row['feasible_cone']['outside_beyond_8_float32_ulp_cells']}
pairs={}
for q,n in [('QC','NC'),('QI','NI'),('QR','NR'),('QG','BG')]:
 pairs[q+'/'+n]={'orphan':int(np.count_nonzero((fields[q]>0)!=(fields[n]>0))),'negative':int(np.count_nonzero((fields[q]<0)|(fields[n]<0)))}
d={'scope':'saved actual OFF T3 full KDM6 component call, not a host timestep completion','post_sha256':hashlib.sha256(raw).hexdigest(),'stage':b[0],'model_timestep':b[1],'active_cells':cells if False else int(fields['QG'].size),'finite_all17':all(np.isfinite(a).all() for a in fields.values()),'pairs':pairs,'strict_source_checks':checks,'strict_source_violations':bad,'unchanged_global_8ulp_pair_policy':policy_pairs,'policy_violations':policy_bad}
d['status']='PASS_SCOPED' if d['finite_all17'] and not bad and not policy_bad and all(not any(v.values()) for v in pairs.values()) else 'FAIL'
(p/'post_state_audit.json').write_text(json.dumps(d,indent=2)+'\n');print(d['status'],d['active_cells'],bad)
