#!/usr/bin/env python3
"""Fixed six-case precipitation evaluation; no tuning or relaxed gates."""
import argparse
import csv
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
from fractions import Fraction
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OLD = ROOT / 'docs/evidence/cp02_pulse_path_20261110/evaluation/results'
POLICY = HERE.parent / 'forecast/policy.json'
POLICY_SHA = 'b9fbbf9cc9e216b8bb9334cecdf079591058e129705414fb8ab93c070aca85b0'
BALANCE = ROOT / 'tools/cp02_weak_strong_balance.py'
BALANCE_SHA = '2572d41d352c70d72d8488fe9f0dc9d961de8b10c21f7ade459f131e7c4fbdb5'
CASES = ('ORIGINAL', 'IMPROVED_BG_FIXED', 'CONSERVATIVE_SEDIMENTATION', 'FIRST_ICE_VELOCITY', 'MP10', 'MP10_NN_END')
ORIGINAL, B1, PR153, PR154, MP10, NEW = CASES
HOURS = tuple(range(13, 19))
THRESHOLDS = (.1, .5, 1., 2.5, 5., 10.)
POINTS = 3688

def identity(path):
    path = Path(path).resolve()
    with path.open('rb') as f: digest = hashlib.file_digest(f, 'sha256').hexdigest()
    return {'path': str(path), 'sha256': digest, 'size_bytes': path.stat().st_size}

def load_policy():
    if identity(POLICY)['sha256'] != POLICY_SHA: raise ValueError('frozen policy changed')
    policy = json.loads(POLICY.read_text())
    if policy['comparison_cases'] != list(CASES) or policy['thresholds_mm'] != list(THRESHOLDS) or policy['lead_hours'] != list(range(1, 7)): raise ValueError('policy coverage differs')
    expected = {(h, t, B1) for h in range(1, 7) for t in THRESHOLDS if h == 1 or t == 5.}
    expected |= {(h, t, ORIGINAL) for h in range(2, 7) for t in (.1, .5, 1.)}
    gates = policy['admission']['protection'] + policy['admission']['recovery']
    if len(gates) != 26 or {(x['lead_hour'], x['threshold_mm'], x['baseline']) for x in gates} != expected: raise ValueError('policy gates differ')
    return policy

def frozen_arrays(policy):
    if identity(OLD/'receipt.json')['sha256'] != policy['frozen_evaluation_receipt_sha256']: raise ValueError('prior receipt mismatch')
    if identity(OLD/'bilinear_mapping.npz')['sha256'] != policy['frozen_mapping_sha256']: raise ValueError('mapping mismatch')
    arrays = {}
    for hour in HOURS:
        path = OLD/f'hour_{hour}_arrays.npz'
        if identity(path)['sha256'] != policy['frozen_hour_array_sha256'][str(hour-12)]: raise ValueError('prior array mismatch')
        with np.load(path, allow_pickle=False) as data: arrays[hour] = {k: data[k].copy() for k in data.files}
    return arrays

def score(arrays, policy):
    if set(arrays) != set(HOURS): raise ValueError('six hours required')
    categorical, continuous, weak, transition = [], [], [], []
    coords = None
    for hour in HOURS:
        values = arrays[hour]; lead = hour-12
        fields = (*CASES, 'reference', 'latitude', 'longitude', 'flat_index_yx')
        if any(k not in values or np.asarray(values[k]).shape != (POINTS,) or not np.isfinite(values[k]).all() for k in fields): raise ValueError('all fixed cohort points must be finite')
        if any(np.any(values[k] < 0) for k in (*CASES, 'reference')): raise ValueError('negative precipitation')
        current = tuple(values[k] for k in ('flat_index_yx', 'latitude', 'longitude'))
        if len(np.unique(current[0])) != POINTS or (coords is not None and any(not np.array_equal(a,b) for a,b in zip(coords,current))): raise ValueError('cohort changed')
        coords = current; obs = values['reference']
        for case in CASES:
            pred = values[case]; error = pred-obs
            continuous.append({'lead_hour':lead,'case':case,'MAE_mm':float(np.abs(error).mean()),'RMSE_mm':float(np.sqrt(np.square(error).mean()))})
            for threshold in THRESHOLDS:
                observed = obs >= threshold; predicted = pred >= threshold
                h, m, f = (int(x.sum()) for x in (observed & predicted, observed & ~predicted, ~observed & predicted))
                if h+m+f == 0: raise ValueError('undefined CSI')
                categorical.append({'lead_hour':lead,'threshold_mm':threshold,'case':case,'points':POINTS,'hit':h,'miss':m,'false_alarm':f,'CSI':h/(h+m+f)})
            for lo, hi in ((.1,.5),(.5,1.),(.1,1.)):
                subset = (obs >= lo) & (obs < hi); count = int(subset.sum())
                if not count: raise ValueError('empty observed weak band')
                weak.append({'lead_hour':lead,'case':case,'observed_min_mm':lo,'observed_max_mm_exclusive':hi,'count':count,
                    'detected_at_0.1':int((subset & (pred>=.1)).sum()), 'same_band':int((subset & (pred>=lo) & (pred<hi)).sum()),
                    'MAE_mm':float(np.abs(error[subset]).mean()),'RMSE_mm':float(np.sqrt(np.square(error[subset]).mean()))})
        for base in (B1, MP10):
            before = values[base]; after = values[NEW]
            for threshold in THRESHOLDS:
                dry = obs < threshold; old = before >= threshold; new = after >= threshold
                transition.append({'lead_hour':lead,'baseline':base,'threshold_mm':threshold,'n_observed_below':int(dry.sum()),
                    'false_alarm_created':int((dry & ~old & new).sum()),'false_alarm_resolved':int((dry & old & ~new).sum()),
                    'false_alarm_retained':int((dry & old & new).sum())})
    lookup = {(x['lead_hour'],x['threshold_mm'],x['case']):x for x in categorical}
    gates = []
    for group in ('protection','recovery'):
        for criterion in policy['admission'][group]:
            h,t,base = criterion['lead_hour'], criterion['threshold_mm'], criterion['baseline']
            a,b = lookup[h,t,NEW], lookup[h,t,base]
            exact = lambda x: Fraction(x['hit'], x['hit']+x['miss']+x['false_alarm'])
            gates.append({'goal':group,'lead_hour':h,'threshold_mm':t,'baseline':base,
                          'candidate_hit':a['hit'],'candidate_denominator':a['hit']+a['miss']+a['false_alarm'],
                          'baseline_hit':b['hit'],'baseline_denominator':b['hit']+b['miss']+b['false_alarm'],
                          'satisfied':exact(a)>=exact(b)})
    if (len(categorical),len(continuous),len(gates),len(weak),len(transition)) != (216,36,26,108,72): raise ValueError('incomplete scoring')
    return categorical,continuous,gates,weak,transition

def write_csv(path, rows):
    with path.open('w', newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)

def compare_prior(categorical, continuous):
    for filename, rows in (('categorical_scores.csv',categorical),('continuous_scores.csv',continuous)):
        with (OLD/filename).open(newline='') as f: old=list(csv.DictReader(f))
        new=[r for r in rows if r['case'] != NEW]
        if len(old) != len(new): raise ValueError('prior score coverage changed')
        for a,b in zip(old,new):
            if any(str(b[k]) != v for k,v in a.items()): raise ValueError(f'prior score changed in {filename}')

def remap(candidate, arrays, policy):
    if identity(BALANCE)['sha256'] != BALANCE_SHA: raise ValueError('mapping code mismatch')
    spec=importlib.util.spec_from_file_location('nn_balance',BALANCE); balance=importlib.util.module_from_spec(spec);sys.modules[spec.name]=balance;spec.loader.exec_module(balance)
    balance.CASE_IDS=(NEW,);balance.CONTEXT_IDS=CASES
    (result,_,histories,mapping,resets)=balance.build_candidate_arrays({NEW:candidate},arrays)
    with np.load(OLD/'bilinear_mapping.npz',allow_pickle=False) as frozen:
        if set(frozen.files)!=set(mapping) or any(not np.array_equal(frozen[k],mapping[k],equal_nan=True) for k in frozen.files): raise ValueError('candidate grid mapping differs')
    return result,histories,resets

INITIAL_SHA = 'b637f559e5e5e633916b6bcd35e16424c8f3f1f3ef5309ca1ac554a6edd09ef6'

def verify_run(candidate, proof, policy):
    candidate=Path(candidate).resolve(); proof=Path(proof).resolve()
    p=json.loads(proof.read_text()); run_path=candidate/'run_receipt.json'; prep_path=candidate/'prepared.json'
    run=json.loads(run_path.read_text()); prep=json.loads(prep_path.read_text())
    build_path=Path(prep['build_receipt']); build=json.loads(build_path.read_text())
    probe=candidate.parent.parent/'probe/probe_receipt.json'
    if identity(probe)['sha256']!=p['probe_receipt_sha256'] or json.loads(probe.read_text()).get('status')!='PASS': raise ValueError('native probe mismatch')
    if p.get('status')!='PASS' or p.get('schema')!='cp02_nn_end_forecast_comparability_v1' or p.get('unchanged_inputs') is not True: raise ValueError('comparability proof not PASS')
    if p['policy_sha256']!=POLICY_SHA or p['candidate_source_sha256']!=policy['candidate_source_sha256'] or p['parent_source_sha256']!=policy['parent_source_sha256']: raise ValueError('proof policy/source mismatch')
    if p['run_receipt_sha256']!=identity(run_path)['sha256'] or p['prepared_sha256']!=identity(prep_path)['sha256'] or p['build_receipt_sha256']!=identity(build_path)['sha256']: raise ValueError('proof receipt mismatch')
    if run.get('status')!='PASS' or run.get('exit_code')!=0 or run.get('case')!=NEW or run.get('variant')!=NEW or run.get('prepared_sha256')!=p['prepared_sha256']: raise ValueError('run did not pass')
    if (run.get('initial_time_utc'),run.get('end_time_utc'))!=('2026-08-16T12:00:00Z','2026-08-16T18:00:00Z'): raise ValueError('run interval mismatch')
    if prep.get('status')!='PREPARED' or prep.get('case')!=NEW or prep.get('build_receipt_sha256')!=p['build_receipt_sha256'] or run.get('inputs_after')!=prep.get('inputs'): raise ValueError('prepared inputs mismatch')
    if build.get('status')!='PASS' or build.get('variant')!=NEW or build.get('inputs_unchanged') is not True or build['source']['sha256']!=policy['candidate_source_sha256'] or build['compile']['exit_code']!=0 or build['link']['exit_code']!=0: raise ValueError('build mismatch')
    if build['executable']['sha256']!=p['executable_sha256'] or prep['inputs']['wrf.exe']!=p['executable_sha256']: raise ValueError('executable mismatch')
    if identity(build['executable']['path'])['sha256']!=p['executable_sha256']: raise ValueError('build executable changed')
    for name, expected in prep['inputs'].items():
        if identity(candidate/name)['sha256']!=expected: raise ValueError('runtime input changed')
        if name!='wrf.exe' and prep['source_hashes'].get(name)!=expected: raise ValueError('source input differs')
    histories=[];expected_names=[f'wrfout_d01_2026-08-16_{hour:02d}:00:00' for hour in range(12,19)]
    if [Path(x['path']).name for x in run['histories']]!=expected_names or p['histories']!=run['histories']: raise ValueError('history coverage/proof mismatch')
    for hour,row in zip(range(12,19),run['histories']):
        path=candidate/Path(row['path']).name; actual=identity(path)
        if Path(row['path']).resolve()!=path or actual['sha256']!=row['sha256'] or actual['size_bytes']!=row['size_bytes'] or row['valid_utc']!=f'2026-08-16T{hour:02d}:00:00Z': raise ValueError('history identity/time mismatch')
        histories.append(actual)
    if histories[0]['sha256']!=INITIAL_SHA or p['initial_history_sha256']!=INITIAL_SHA or p['initial_reference_sha256']!=INITIAL_SHA: raise ValueError('initial history differs')
    return [identity(proof),identity(probe),identity(run_path),identity(prep_path),identity(build_path),*histories]

def run(candidate, proof, output, freeze):
    output=Path(output)
    if os.path.lexists(output): raise FileExistsError(output)
    policy=load_policy(); frozen=json.loads(Path(freeze).read_text())
    if frozen.get('status')!='FROZEN_BEFORE_FORECAST_EVALUATION' or frozen['policy_sha256']!=POLICY_SHA or frozen['evaluation_sha256']!=identity(__file__)['sha256'] or frozen['test_sha256']!=identity(HERE/'test_nn_frequency_evaluation.py')['sha256']: raise ValueError('evaluation freeze mismatch')
    inputs=verify_run(candidate,proof,policy)
    arrays=frozen_arrays(policy); arrays,histories,resets=remap(Path(candidate),arrays,policy)
    categorical,continuous,gates,weak,transition=score(arrays,policy);compare_prior(categorical,continuous)
    output.parent.mkdir(parents=True,exist_ok=True);stage=Path(tempfile.mkdtemp(prefix='.nn-score-',dir=output.parent))
    try:
        for hour,values in arrays.items(): np.savez_compressed(stage/f'hour_{hour}_arrays.npz',**values)
        for name,rows in (('categorical_scores.csv',categorical),('continuous_scores.csv',continuous),('admission_constraints.csv',gates),('weak_bands.csv',weak),('false_alarm_transitions.csv',transition)): write_csv(stage/name,rows)
        passed=sum(x['satisfied'] for x in gates)
        (stage/'verdict.json').write_text(json.dumps({'passed':passed,'required':26,'all_gates_pass':passed==26,'selection':'B1 remains selected pending all gates and independent validation','open_items':['domain budget','independent case']},indent=2)+'\n')
        for record in inputs+histories:
            if identity(record['path'])!=record: raise ValueError('forecast changed during scoring')
        receipt={'status':'COMPLETE','policy_sha256':POLICY_SHA,'evaluation_sha256':identity(__file__)['sha256'],'freeze':identity(freeze),'inputs':inputs,'remapped_histories':histories,'reset_report':resets,'prior_score_rows':'all 180 categorical and 30 continuous rows unchanged','outputs':{p.name:identity(p)['sha256'] for p in stage.iterdir()}}
        (stage/'receipt.json').write_text(json.dumps(receipt,indent=2,allow_nan=False)+'\n')
        os.rename(stage,output)
    finally:
        if stage.exists(): shutil.rmtree(stage)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for arg in ('candidate','proof','output','freeze'): parser.add_argument('--'+arg,type=Path,required=True)
    args=parser.parse_args();run(args.candidate,args.proof,args.output,args.freeze)
