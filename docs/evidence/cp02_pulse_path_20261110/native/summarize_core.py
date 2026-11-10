#!/usr/bin/env python3
"""Summarize selected weighted cold-branch graupel source terms."""
import csv
import gzip
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SELECTOR = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_low_threshold_process_20261110/Cloud-BAL/docs/evidence/cp02_low_threshold_process_20261110/cohorts/results/selected_points.csv')


def main():
    with SELECTOR.open(newline='') as f:
        point = next(r for r in csv.DictReader(f) if r['flat_index_yx'] == '19145')
    i, j = int(point['native_i0_fortran_one_based']), int(point['native_j0_fortran_one_based'])
    weights = {(i+di,j+dj): float(point[f'weight_j{dj}_i{di}']) for di in (0,1) for dj in (0,1)}
    if abs(sum(weights.values())-1) > 1e-12: raise ValueError('weights')
    with gzip.open(HERE / 'core_recount.csv.gz', 'rt', newline='') as f:
        rows = [r for r in csv.DictReader(f) if r['step'] == '858' and r['k'] == '17' and (int(r['i']),int(r['j'])) in weights]
    result = []
    for arm in ('CONSERVATIVE','ICE_FIXED'):
        selected = [r for r in rows if r['arm'] == arm]
        if len(selected) != 4 or any(r['branch'] != 'cold' for r in selected): raise ValueError('not four cold corners')
        totals = dict.fromkeys(('pgdep','pgaut','piacr','praci','psacr','pracs','pgaci','paacw','pgacr','pgacs'), 0.)
        for r in selected:
            rate = lambda n: float(r[f'rate_{n}(i,k)'])
            d2,d3 = float(r['rate_delta2']),float(r['rate_delta3'])
            terms = {'pgdep':rate('pgdep'),'pgaut':rate('pgaut'),'piacr':rate('piacr')*(1-d3),
                     'praci':rate('praci')*(1-d3),'psacr':rate('psacr')*(1-d2),'pracs':rate('pracs')*(1-d2),
                     'pgaci':rate('pgaci'),'paacw':rate('paacw'),'pgacr':rate('pgacr'),'pgacs':rate('pgacs')}
            factor = weights[(int(r['i']),int(r['j']))]*float(r['dt_s'])
            for name,value in terms.items(): totals[name] += factor*value
        for term,value in totals.items(): result.append({'point':'19145','step':858,'k':17,'arm':arm,'term':term,'weighted_integral_kg_kg':value})
    with (HERE/'core_qg_partition.csv').open('x',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(result[0]),lineterminator='\n');writer.writeheader();writer.writerows(result)
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    inputs=[SELECTOR,HERE/'core_recount.csv.gz',HERE/'extract_receipt.json',HERE/'recount.py',HERE/'read_frames_with_constants.py',Path(__file__)]
    receipt={'status':'PASS','inputs':{str(p):sha(p) for p in inputs},'output_sha256':sha(HERE/'core_qg_partition.csv')}
    (HERE/'recount_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')


if __name__ == '__main__': main()
