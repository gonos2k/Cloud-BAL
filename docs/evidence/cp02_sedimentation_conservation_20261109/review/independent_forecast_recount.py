#!/usr/bin/env python3
"""Independent count-fraction recount from six sealed arrays, without scorer helpers."""
import csv
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import numpy as np

BUNDLE = Path(__file__).resolve().parents[1]
SOURCE = BUNDLE / 'evaluation/results'
CASES = ('ORIGINAL', 'IMPROVED_BG_FIXED', 'CONSERVATIVE_SEDIMENTATION')
THRESHOLDS = (.1, .5, 1., 2.5, 5., 10.)


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def read_csv(name):
    with (SOURCE / name).open(newline='') as stream:
        return list(csv.DictReader(stream))


def main():
    receipt = json.loads((SOURCE/'receipt.json').read_text())
    if receipt['status'] != 'COMPLETE': raise ValueError('input receipt incomplete')
    expected_c = {(int(r['lead_hour']), float(r['threshold_mm']), r['case']): r for r in read_csv('categorical_scores.csv')}
    expected_d = {(int(r['lead_hour']), r['case']): r for r in read_csv('continuous_scores.csv')}
    expected_t = {(int(r['lead_hour']), r['baseline'], r['observation_subset']): r for r in read_csv('observation_transitions.csv')}
    expected_g = {(int(r['lead_hour']), float(r['threshold_mm'])): r for r in read_csv('admission_constraints.csv')}
    if (len(expected_c),len(expected_d),len(expected_t),len(expected_g)) != (108,18,48,26): raise ValueError('published row inventory differs')
    scores = {}; inputs = {}; observed_transitions = {}; counts = {'categorical':0,'continuous':0,'transitions':0,'constraints':0}
    index = None
    for lead in range(1, 7):
        path = SOURCE / f'hour_{lead+12}_arrays.npz'; digest = sha(path)
        if digest != receipt['outputs'][path.name]: raise ValueError(f'array hash mismatch: {path}')
        inputs[path.name] = digest
        with np.load(path, allow_pickle=False) as archive:
            data = {key: archive[key] for key in archive.files}
        if any(data[k].shape != (3688,) or not np.isfinite(data[k]).all() for k in ('reference',*CASES)):
            raise ValueError('invalid scoring samples')
        if index is None: index = data['flat_index_yx']
        elif not np.array_equal(index, data['flat_index_yx']): raise ValueError('sample order changed')
        obs = data['reference']
        for case in CASES:
            pred = data[case]; err = pred-obs
            mae = float(np.sum(np.abs(err),dtype=np.float64)/len(err))
            rmse = math.sqrt(float(np.sum(err*err,dtype=np.float64)/len(err)))
            published = expected_d[(lead,case)]
            if not all(math.isclose(value,float(published[key]),rel_tol=1e-14,abs_tol=1e-14) for key,value in [('MAE_mm',mae),('RMSE_mm',rmse)]): raise ValueError('continuous score mismatch')
            counts['continuous'] += 1
            for threshold in THRESHOLDS:
                o, p = obs >= threshold, pred >= threshold
                hit = int(np.sum(o & p)); miss = int(np.sum(o & ~p)); false = int(np.sum(~o & p)); denom = hit+miss+false
                if not denom: raise ValueError('undefined CSI')
                row = expected_c[(lead,threshold,case)]
                if (int(row['points']),int(row['hit']),int(row['miss']),int(row['false_alarm'])) != (3688,hit,miss,false): raise ValueError('categorical counts mismatch')
                if not math.isclose(float(row['CSI']),hit/denom,rel_tol=0,abs_tol=1e-15): raise ValueError('CSI mismatch')
                scores[(lead,threshold,case)] = Fraction(hit,denom); counts['categorical'] += 1
        candidate=data[CASES[2]]
        for baseline in CASES[:2]:
            before=data[baseline]
            for label,mask,t in [('weak_observed',(obs>=.1)&(obs<1),.1),('dry_observed',obs<.1,.1),('strong_observed',obs>=5,5),('below_strong_observed',obs<5,5)]:
                b=before>=t; a=candidate>=t
                vector=[int(mask.sum()),int((mask & ~b & ~a).sum()),int((mask & ~b & a).sum()),int((mask & b & ~a).sum()),int((mask & b & a).sum())]
                row=expected_t[(lead,baseline,label)]; fields=('n_observed_subset','forecast_both_below','forecast_gained','forecast_lost','forecast_both_at_or_above')
                if vector != [int(row[k]) for k in fields]: raise ValueError('transition mismatch')
                if label in ('weak_observed','dry_observed'):observed_transitions[f'{lead}/{baseline}/{label}']=dict(zip(fields,vector))
                counts['transitions']+=1
    failed=[]
    for (lead,t), row in expected_g.items():
        protect = lead==1 or t==5.; recover = lead>=2 and t in (.1,.5,1.)
        if not (protect or recover): raise ValueError('unexpected constraint')
        base=CASES[1] if protect else CASES[0]
        if row['baseline'] != base: raise ValueError('wrong baseline')
        actual=scores[(lead,t,CASES[2])] >= scores[(lead,t,base)]
        if actual != (row['satisfied']=='True'): raise ValueError('exact gate mismatch')
        counts['constraints']+=1
        if not actual: failed.append({'lead_hour':lead,'threshold_mm':t,'baseline':base,'candidate':str(scores[(lead,t,CASES[2])]),'reference':str(scores[(lead,t,base)])})
    verdict=json.loads((SOURCE/'verdict.json').read_text());passed=26-len(failed)
    if (passed,passed==26)!=(verdict['passed_constraints'],verdict['qualified']):raise ValueError('verdict mismatch')
    out={'status':'PASS','method':'Independent NumPy counts, exact fractions.Fraction CSI comparisons, direct MAE/RMSE; no scorer helpers imported.','array_sha256':inputs,'published_files_sha256':{name:sha(SOURCE/name) for name in ('receipt.json','categorical_scores.csv','continuous_scores.csv','admission_constraints.csv','observation_transitions.csv','verdict.json')},'helper_sha256':sha(Path(__file__)),'rows_verified':counts,'passed_constraints':passed,'failed_constraints':failed,'candidate_qualified':passed==26,'weak_and_dry_transitions':observed_transitions,'scope':'Recounts the sealed scored arrays; does not independently validate gridded-to-point mapping or observations.'}
    (Path(__file__).parent/'independent_forecast_score_recount.json').write_text(json.dumps(out,indent=2)+'\n')
    print('PASS',counts,'qualified',passed,'/26')

if __name__=='__main__':main()
