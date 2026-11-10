#!/usr/bin/env python3
"""Weight actual RSG sedimentation and shared faces independently by arm."""
import csv
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
SELECTOR=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_low_threshold_process_20261110/Cloud-BAL/docs/evidence/cp02_low_threshold_process_20261110/cohorts/results/selected_points.csv')
with SELECTOR.open(newline='') as f: point=next(r for r in csv.DictReader(f) if r['flat_index_yx']=='19145')
i,j=int(point['native_i0_fortran_one_based']),int(point['native_j0_fortran_one_based'])
w={(i+di,j+dj):float(point[f'weight_j{dj}_i{di}']) for di in (0,1) for dj in (0,1)}
with (HERE/'sediment_substeps.csv').open(newline='') as f: rows=list(csv.DictReader(f))
result=[]
for step,species in ((831,'graupel'),(839,'rain')):
    for arm in ('CONSERVATIVE','ICE_FIXED'):
        subset=[r for r in rows if int(r['step'])==step and r['arm']==arm and r['species']==species]
        if {(int(r['i']),int(r['j'])) for r in subset}!=set(w): raise ValueError('missing corners')
        actual=upper=lower=0.
        for r in subset:
            weight=w[(int(r['i']),int(r['j']))];carrier=float(r['dend_kg_m3'])*float(r['delz_m'])
            if carrier<=0: raise ValueError('invalid carrier')
            actual+=weight*float(r['q_actual_delta_kg_kg'])
            upper+=weight*float(r['upper_face_kg_m2'])/carrier
            lower+=weight*float(r['lower_face_kg_m2'])/carrier
        result.append({'point':19145,'step':step,'k':16,'species':species,'arm':arm,'weighted_actual_kg_kg':actual,
                       'weighted_upper_input_kg_kg':upper,'weighted_lower_output_kg_kg':lower,
                       'weighted_face_net_kg_kg':upper-lower,'actual_minus_face_net_kg_kg':actual-upper+lower})
out=HERE/'sediment_faces_summary.csv'
with out.open('x',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=list(result[0]),lineterminator='\n');writer.writeheader();writer.writerows(result)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
paths=[SELECTOR,HERE/'extract_receipt.json',HERE/'sediment_substeps.csv',HERE/'recount_sediment.py',Path(__file__)]
(HERE/'sediment_recount_receipt.json').write_text(json.dumps({'status':'PASS','inputs':{str(p):sha(p) for p in paths},'output_sha256':sha(out)},indent=2)+'\n')
