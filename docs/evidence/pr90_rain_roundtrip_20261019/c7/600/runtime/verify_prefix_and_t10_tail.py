#!/usr/bin/env python3
"""Receipt-bound C7 600-to-180 prefix compare and explicit T10 tail parse."""
import gzip, hashlib, json, shutil, tempfile, sys
from pathlib import Path
import sys
ROOT = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr90_rain_roundtrip_20261019/Cloud-BAL')
sys.path.insert(0, str(ROOT/'tools'))
import pr85_joint_stage_trace as stage

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''): h.update(b)
    return h.hexdigest()
def artifact(receipt):
    rows=[x for x in receipt['compressed_outputs'] if x['path']=='pr85_joint_moment_stages.raw']
    if len(rows)!=1: raise ValueError(f'expected one trace ledger row, found {len(rows)}')
    return rows[0]
def bind_run(arm, seconds):
    root=Path(f'/var/tmp/pr90_{arm}_{seconds}s_c7_20261019')
    rp=root/'receipt.json'; pp=root/'preflight.json'
    rec=json.loads(rp.read_text()); pre=json.loads(pp.read_text())
    if seconds==600:
        if (rec['status'],rec['returncode'],rec['final_completed_step'],rec['timestep_count']) != ('INCOMPLETE',1,9,9):
            raise ValueError((arm,'unexpected closed 600 status/steps',rec['status'],rec['returncode'],rec['final_completed_step'],rec['timestep_count']))
        if 10 not in rec['snapshots']['timesteps'] or 10 in rec['snapshots']['completed_post_kdm6_timesteps']:
            raise ValueError((arm,'unexpected T10 snapshot/POST state'))
    else:
        if (rec['status'],rec['returncode'],rec['final_completed_step'],rec['timestep_count']) != ('COMPLETE',0,9,9):
            raise ValueError((arm,'unexpected 180 reference closure'))
    if rec['source_receipt_sha256']!=pre['source_receipt_sha256']:
        raise ValueError((arm,'source receipt mismatch'))
    build=Path(rec['candidate_build']['receipt_path'])
    if sha(build)!=rec['candidate_build']['receipt_sha256'] or sha(build)!=pre['candidate_build']['receipt_sha256']:
        raise ValueError((arm,'build receipt mismatch'))
    b=json.loads(build.read_text()); exe=Path(b['executable_path'])
    if sha(exe)!=rec['executed_executable_sha256'] or rec['executed_executable_sha256']!=rec['expected_executed_executable_sha256'] or sha(exe)!=b['executable_sha256']:
        raise ValueError((arm,'executable mismatch'))
    for name,row in b['source_overrides'].items():
        if sha(row['staged_path'])!=row['staged_sha256'] or row['staged_sha256']!=row['requested_sha256']:
            raise ValueError((arm,'staged source mismatch',name))
    ledger=artifact(rec); trace=root/'run'/ledger['compressed_path']
    if sha(trace)!=ledger['compressed_sha256']:
        raise ValueError((arm,'compressed trace hash mismatch'))
    return {'root':str(root),'receipt_path':str(rp),'receipt_sha256':sha(rp),'preflight_path':str(pp),'preflight_sha256':sha(pp),'status':rec['status'],'returncode':rec['returncode'],'final_completed_step':rec['final_completed_step'],'timestep_count':rec['timestep_count'],'timesteps':rec['snapshots']['timesteps'],'completed_post_kdm6_timesteps':rec['snapshots']['completed_post_kdm6_timesteps'],'source_receipt_sha256':rec['source_receipt_sha256'],'build_receipt_path':str(build),'build_receipt_sha256':sha(build),'executable_path':str(exe),'executable_sha256':sha(exe),'trace_path':str(trace),'trace_compressed_sha256':sha(trace),'trace_payload_sha256':ledger['sha256'],'trace_payload_bytes':ledger['bytes'],'trace_records':rec['snapshots']['record_count'],'fatal_lines':rec.get('fatal_lines',[]),'fatal_reason_from_receipt':rec.get('fatal_reason')},rec

def compare_and_parse_tail(arm):
    x180,r180=bind_run(arm,180); x600,r600=bind_run(arm,600)
    l180=artifact(r180); n=l180['bytes']
    if x180['trace_payload_bytes']!=n or x600['trace_payload_bytes']<n: raise ValueError((arm,'unexpected payload lengths'))
    h0=hashlib.sha256(); h1=hashlib.sha256(); done=0
    with tempfile.TemporaryDirectory(prefix=f'pr90_c7_{arm}_t10_') as td:
        tail=Path(td)/'t10_tail.raw'
        with gzip.open(x180['trace_path'],'rb') as a, gzip.open(x600['trace_path'],'rb') as b, tail.open('wb') as out:
            left=n
            while left:
                k=min(left,8*1024*1024); p=a.read(k); q=b.read(k)
                if len(p)!=k or len(q)!=k or p!=q: raise ValueError((arm,'prefix mismatch/truncation',done))
                h0.update(p); h1.update(q); done+=k; left-=k
            tailbytes=0; tailhash=hashlib.sha256()
            while True:
                block=b.read(8*1024*1024)
                if not block: break
                out.write(block); tailbytes+=len(block); tailhash.update(block)
        tail_summary=stage.summarize(tail)
        tail_records=stage.read_records(tail)['records']
        timesteps=sorted({r['timestep'] for r in tail_records})
        stages=[{'timestep':r['timestep'],'stage':r['stage'],'rkstep':r['rkstep']} for r in tail_records if r['kind']==1]
        if timesteps != [10]: raise ValueError((arm,'unexpected extra trace timestep',timesteps))
        if any(r['stage']=='POST_KDM6' for r in tail_records if r['kind']==1): raise ValueError((arm,'T10 incorrectly has POST_KDM6'))
        # Preserve only the extra-record status and stage facts; do not relabel T10 complete.
        per_state=[]
        for s in tail_summary['completed_state_summaries']:
            per_state.append({
                'stage':s['stage'], 'rkstep':s['rkstep'],
                'density_contract_status':s['density_contract_status'],
                'negative_or_nonfinite_fields':{n:{'negative':v['negative'],'nonfinite':v['nonfinite']} for n,v in s['stats'].items() if v['negative'] or v['nonfinite']},
                'pair_outside_8ulp':{n:v['feasible_cone']['outside_beyond_8_float32_ulp_cells'] for n,v in s['pairs'].items() if v['feasible_cone']['outside_beyond_8_float32_ulp_cells']},
                'number_conversion_failures':{n:v for n,v in s['number_conversion'].items() if any(z for k,z in v.items() if k!='quantity')},
            })
        partial={'record_count':len(tail_records),'payload_bytes':tailbytes,'timestep_ids':timesteps,'state_stage_sequence':stages,'summarizer_scope':'T10 tail records only; partial failing timestep, not a completed endpoint','summary_status':tail_summary.get('strict_completed_state_admission',{}).get('status'),'strict_density_contract':tail_summary.get('strict_density_contract',{}),'strict_completed_state_admission':tail_summary.get('strict_completed_state_admission'),'first_observed_violation':tail_summary.get('earliest_observed_completed_state_violation'),'per_state_generic_checks':per_state,'strict_cloud_rain_graupel_endpoint_gate':'NOT_EVALUATED for T10: tail lacks RK3/PRE_KDM6/POST_KDM6 and the existing one-timestep reader does not run the strict endpoint source audit'}
    return {'arm':arm,'prefix_bytes_compared':done,'prefix_match':True,'reference_180_payload_sha256':h0.hexdigest(),'candidate_600_prefix_sha256':h1.hexdigest(),'tail_payload_bytes':tailbytes,'tail_sha256':tailhash.hexdigest(),'run_180':x180,'run_600':x600,'t10_tail_observation':partial}

arms=(sys.argv[1].upper(),) if len(sys.argv)>1 else ('OFF','COUPLED')
if any(a not in ('OFF','COUPLED') for a in arms): raise SystemExit('arm must be OFF or COUPLED')
for arm in arms:
    result={'schema':'pr90_c7_600_incomplete_prefix_audit_v1','overall_status':'INCOMPLETE: 600-second run stopped at T10 after nine completed steps; prefix result does not change run status','arms':{arm:compare_and_parse_tail(arm)}}
    out=Path(__file__).with_name(f'{arm.lower()}_prefix_and_t10_audit.json')
    if out.exists(): raise FileExistsError(out)
    out.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(out)
