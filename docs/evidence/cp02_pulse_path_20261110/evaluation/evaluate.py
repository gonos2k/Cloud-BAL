#!/usr/bin/env python3
"""Score MP10 only after byte-identity proof against the frozen PR154 forecast."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from fractions import Fraction

import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
PRIOR=ROOT/'docs/evidence/cp02_first_ice_velocity_20261109/evaluation/results'
PRIOR_RECEIPT_SHA='09bd7015a9f84f3a79cd90a0dc00b2600f10f32589b26e336554e54e7dc24b16'
BALANCE=ROOT/'tools/cp02_weak_strong_balance.py'
BALANCE_SHA='2572d41d352c70d72d8488fe9f0dc9d961de8b10c21f7ade459f131e7c4fbdb5'
spec=importlib.util.spec_from_file_location('prior_ice_evaluation',PRIOR.parent/'evaluate.py')
prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
identity=prior.identity
ORIGINAL,B1,CONS,ICE=prior.CASES
NEW='MP10'
CASES=(ORIGINAL,B1,CONS,ICE,NEW)
HOURS=tuple(range(13,19))
THRESHOLDS=(.1,.5,1.,2.5,5.,10.)
BINS=(('[0,0.1)',0.,.1),('[0.1,0.5)',.1,.5),('[0.5,1)',.5,1.),('[1,2.5)',1.,2.5),('[2.5,5)',2.5,5.),('[5,10)',5.,10.),('[10,inf)',10.,None))


def verify_forecasts(runtime,previous,proof):
    payload=json.loads(proof.read_text())
    if payload.get('status')!='PASS' or payload.get('schema')!='cp02_pulse_substeps_comparability_v1': raise ValueError('independent comparability proof must PASS')
    expected={f'wrfout_d01_2026-08-16_{h:02d}:00:00' for h in range(12,19)}
    comparisons=payload.get('control_history_comparison',[])
    if len(comparisons)!=7 or {Path(r['observed']['path']).name for r in comparisons}!=expected: raise ValueError('proof must cover seven control histories')
    for row in comparisons:
        name=Path(row['observed']['path']).name
        if row.get('byte_equal') is not True or row['historical']!=identity(previous/name) or row['observed']!=identity(runtime/'CONTROL'/name): raise ValueError('control proof identity mismatch')
    first='wrfout_d01_2026-08-16_12:00:00'; initial=payload['candidate_initial_history']
    if initial.get('byte_equal') is not True or initial['historical']!=identity(previous/first) or initial['observed']!=identity(runtime/NEW/first): raise ValueError('candidate initial identity mismatch')
    records=[identity(proof)]
    for case in ('CONTROL',NEW):
        receipt=runtime/case/'run_receipt.json';data=json.loads(receipt.read_text())
        if data.get('status')!='PASS' or data.get('exit_code')!=0 or len(data.get('histories',[]))!=7 or {Path(r['path']).name for r in data['histories']}!=expected: raise ValueError('incomplete run receipt: '+case)
        records.append(identity(receipt))
        for row in data['histories']:
            actual=identity(runtime/case/Path(row['path']).name)
            if any(actual[k]!=row[k] for k in ('sha256','size_bytes')): raise ValueError('history changed')
            records.append(actual)
    for name in sorted(expected):
        historical=identity(previous/name);control=identity(runtime/'CONTROL'/name)
        if (historical['sha256'],historical['size_bytes'])!=(control['sha256'],control['size_bytes']): raise ValueError('control history differs')
        records.append(historical)
    a=identity(runtime/NEW/first);b=identity(previous/first)
    if (a['sha256'],a['size_bytes'])!=(b['sha256'],b['size_bytes']): raise ValueError('initial history differs')
    return records


def forecast_arrays(runtime):
    if identity(PRIOR/'receipt.json')['sha256']!=PRIOR_RECEIPT_SHA: raise ValueError('frozen PR154 receipt differs')
    if identity(BALANCE)['sha256']!=BALANCE_SHA: raise ValueError('mapping source differs')
    base=prior.read_arrays(PRIOR)
    mapping_path=PRIOR/'bilinear_mapping.npz'; receipt=json.loads((PRIOR/'receipt.json').read_text())
    if identity(mapping_path)['sha256']!=receipt['outputs'][mapping_path.name]: raise ValueError('frozen mapping differs')
    spec=importlib.util.spec_from_file_location('frozen_balance_mp10',BALANCE);balance=importlib.util.module_from_spec(spec);sys.modules[spec.name]=balance;spec.loader.exec_module(balance)
    balance.CASE_IDS=(NEW,);balance.CONTEXT_IDS=(*prior.CASES,NEW)
    result=balance.build_candidate_arrays({NEW:runtime/NEW},base)
    with np.load(mapping_path,allow_pickle=False) as expected:
        if set(expected.files)!=set(result[3]) or any(not np.array_equal(expected[k],result[3][k],equal_nan=True) for k in expected.files): raise ValueError('mapping differs from frozen mapping')
    inputs=[identity(PRIOR/'receipt.json'),identity(mapping_path),identity(BALANCE),identity(PRIOR.parent/'evaluate.py')]
    inputs += [identity(PRIOR/f'hour_{h}_arrays.npz') for h in HOURS]
    return result,inputs


def score(arrays):
    if set(arrays)!=set(HOURS): raise ValueError('six hours required')
    categorical=[];continuous=[];transitions=[];bands=[];weak=[];coords=None
    for hour in HOURS:
        v=arrays[hour];fields=(*CASES,'reference','latitude','longitude','flat_index_yx')
        if any(np.asarray(v[k]).shape!=(3688,) or not np.isfinite(v[k]).all() for k in fields): raise ValueError('all 3688 points must be finite')
        if any(np.any(v[k]<0) for k in (*CASES,'reference')): raise ValueError('negative precipitation')
        current=tuple(v[k] for k in ('flat_index_yx','latitude','longitude'))
        if len(np.unique(current[0]))!=3688 or (coords is not None and any(not np.array_equal(a,b) for a,b in zip(coords,current))): raise ValueError('point cohort changed')
        coords=current;obs=v['reference'];lead=hour-12
        for case in CASES:
            pred=v[case];error=pred-obs
            continuous.append({'lead_hour':lead,'case':case,'MAE_mm':float(np.abs(error).mean()),'RMSE_mm':float(np.sqrt(np.square(error).mean()))})
            for threshold in THRESHOLDS:
                o=obs>=threshold;p=pred>=threshold
                h,m,f=(int(mask.sum()) for mask in (o&p,o&~p,~o&p))
                if h+m+f==0: raise ValueError('undefined CSI')
                categorical.append({'lead_hour':lead,'threshold_mm':threshold,'case':case,'points':3688,'hit':h,'miss':m,'false_alarm':f,'CSI':h/(h+m+f)})
        maintained=np.logical_and.reduce([(v[k]>=.1)&(v[k]<1) for k in (B1,CONS,ICE)])
        for lo,hi in ((.1,.5),(.5,1.)):
            subset=(obs>=lo)&(obs<hi)
            for case in CASES:
                pred=v[case]
                weak.append({'lead_hour':lead,'observation_bin_mm':f'[{lo:g},{hi:g})','case':case,'observations':int(subset.sum()),
                             'forecast_below_0.1':int((subset&(pred<.1)).sum()),'forecast_0.1_to_1':int((subset&(pred>=.1)&(pred<1)).sum()),
                             'forecast_at_least_1':int((subset&(pred>=1)).sum()),'forecast_at_least_0.1':int((subset&(pred>=.1)).sum()),
                             'all_B1_PR153_PR154_0.1_to_1':int((subset&maintained).sum())})
        for baseline in (B1,ICE):
            before=v[baseline];after=v[NEW]
            for name,subset,threshold in (('weak_observed',(obs>=.1)&(obs<1),.1),('dry_observed',obs<.1,.1),('strong_observed',obs>=5,5.),('below_strong_observed',obs<5,5.)):
                b=before>=threshold;a=after>=threshold
                transitions.append({'lead_hour':lead,'baseline':baseline,'observation_subset':name,'forecast_threshold_mm':threshold,'n_observed_subset':int(subset.sum()),'forecast_both_below':int((subset&~b&~a).sum()),'forecast_gained':int((subset&~b&a).sum()),'forecast_lost':int((subset&b&~a).sum()),'forecast_both_at_or_above':int((subset&b&a).sum())})
            for oname,olo,ohi in BINS:
                observed=(obs>=olo)&((obs<ohi) if ohi is not None else True)
                for case,pred in ((baseline,before),(NEW,after)):
                    for pname,plo,phi in BINS:
                        predicted=(pred>=plo)&((pred<phi) if phi is not None else True)
                        bands.append({'lead_hour':lead,'baseline':baseline,'observed_band':oname,'forecast_case':case,'forecast_band':pname,'point_count':int((observed&predicted).sum())})
    lookup={(r['lead_hour'],r['threshold_mm'],r['case']):r for r in categorical};constraints=[]
    for lead in range(1,7):
        for threshold in THRESHOLDS:
            protect=lead==1 or threshold==5;recover=lead>=2 and threshold in (.1,.5,1.)
            if not (protect or recover): continue
            base=B1 if protect else ORIGINAL
            for candidate in (NEW,ICE):
                a,b=lookup[lead,threshold,candidate],lookup[lead,threshold,base]
                exact=lambda r:Fraction(r['hit'],r['hit']+r['miss']+r['false_alarm'])
                constraints.append({'candidate':candidate,'goal':'preserve_current_B1' if protect else 'recover_low_threshold_vs_ORIGINAL','lead_hour':lead,'threshold_mm':threshold,'baseline':base,'candidate_CSI':a['CSI'],'baseline_CSI':b['CSI'],'satisfied':exact(a)>=exact(b)})
    if (len(categorical),len(continuous),len(constraints),len(transitions),len(bands),len(weak))!=(180,30,52,48,1176,60): raise ValueError('scoring coverage differs')
    return categorical,continuous,constraints,transitions,bands,weak


def full_scores(path,categorical,continuous):
    labels={ORIGINAL:'규준실험',B1:'B1',CONS:'PR153',ICE:'PR154',NEW:'MP10'}
    lines=['# Five-case hourly precipitation scores','','All 3,688 paired RN1 points; each lead and threshold is evaluated independently.','','| Lead | Threshold mm | Case | Hit | Miss | False alarm | CSI |','|---:|---:|---|---:|---:|---:|---:|']
    lines.extend(f"| {r['lead_hour']} | {r['threshold_mm']:g} | {labels[r['case']]} | {r['hit']} | {r['miss']} | {r['false_alarm']} | {r['CSI']:.6f} |" for r in categorical)
    lines+=['','| Lead | Case | MAE mm | RMSE mm |','|---:|---|---:|---:|']
    lines.extend(f"| {r['lead_hour']} | {labels[r['case']]} | {r['MAE_mm']:.6f} | {r['RMSE_mm']:.6f} |" for r in continuous)
    path.write_text('\n'.join(lines)+'\n',encoding='utf-8')


def run(runtime,previous,proof,output):
    if os.path.lexists(output): raise FileExistsError(output)
    inputs=verify_forecasts(runtime,previous,proof)
    (arrays,_,histories,mapping,resets),other=forecast_arrays(runtime);inputs+=other+histories
    categorical,continuous,constraints,transitions,bands,weak=score(arrays)
    verdict={case:{'passed_constraints':sum(r['satisfied'] for r in constraints if r['candidate']==case),'required_constraints':26} for case in (NEW,ICE)}
    output.parent.mkdir(parents=True,exist_ok=True);stage=Path(tempfile.mkdtemp(prefix='.mp10-score-',dir=output.parent))
    try:
        for h,values in arrays.items(): np.savez_compressed(stage/f'hour_{h}_arrays.npz',**values)
        np.savez_compressed(stage/'bilinear_mapping.npz',**mapping)
        for name,rows in (('categorical_scores.csv',categorical),('continuous_scores.csv',continuous),('admission_constraints.csv',constraints),('observation_transitions.csv',transitions),('observed_forecast_bands.csv',bands),('weak_detection.csv',weak)):prior.write_csv(stage/name,rows)
        full_scores(stage/'FULL_SCORES.md',categorical,continuous)
        (stage/'verdict.json').write_text(json.dumps(verdict,indent=2)+'\n')
        for record in inputs:
            if identity(record['path'])!=record: raise ValueError('input changed during scoring')
        meta={'status':'COMPLETE','inputs':inputs,'source':identity(__file__),'numpy':np.__version__,'reset_report':resets,'counts':{'categorical':180,'continuous':30,'constraints':52,'transitions':48,'bands':1176,'weak_detection':60},'outputs':{p.name:identity(p)['sha256'] for p in stage.iterdir()}}
        (stage/'receipt.json').write_text(json.dumps(meta,indent=2)+'\n');prior.publish_new(stage,output)
    finally:
        if stage.exists():shutil.rmtree(stage)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ('runtime','previous','proof','output'):p.add_argument('--'+arg,type=Path,required=True)
    a=p.parse_args();run(a.runtime,a.previous,a.proof,a.output)
