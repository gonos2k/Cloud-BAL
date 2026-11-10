#!/usr/bin/env python3
"""Recount selected actual sedimentation changes and captured interface transfers."""
import csv
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OLD = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_low_threshold_process_20261110/Cloud-BAL/docs/evidence/cp02_low_threshold_process_20261110/native')
spec=importlib.util.spec_from_file_location('frames',HERE/'read_frames_with_constants.py'); mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
schema=json.loads((OLD/'schema/schema.json').read_text())
receipt=json.loads((HERE/'extract_receipt.json').read_text())
rows=[]
for arm in ('FIX','CONSERVATIVE','ICE_FIXED'):
    counts={int(k):len(v['fields']) for k,v in schema['phases'].items()}
    override=schema['arm_overrides']['FIX' if arm=='FIX' else 'CONSERVATIVE and ICE_FIXED']
    for phase in override['absent_phases']: del counts[phase]
    if arm!='FIX': counts[10]=len(override['phase_10_fields'])
    path=HERE/receipt['arms'][arm]['output']
    if hashlib.sha256(path.read_bytes()).hexdigest()!=receipt['arms'][arm]['output_sha256']: raise ValueError('subset changed')
    for header,constants,records in mod.frames(path,counts):
        rank,call,step,j,*_=header
        if step not in (831,839) or j not in (134,135): continue
        groups={}
        for phase,i,k,loop,loops,sub,mstep,v in records:
            if phase not in (9,10,18) or i not in (148,149) or k!=16: continue
            key=(i,k,loop,loops,sub,mstep)
            if phase in groups.setdefault(key,{}): raise ValueError('duplicate')
            groups[key][phase]=v.astype('float64')
        for (i,k,loop,loops,sub,mstep),g in groups.items():
            if 9 not in g or 10 not in g or (arm!='FIX' and 18 not in g): raise ValueError('missing sediment endpoint')
            for species,index,face in (('rain',5,0),('graupel',7,4)):
                before,after=g[9][index],g[10][index]
                row={'arm':arm,'step':step,'rank':rank,'call':call,'i':i,'j':j,'k':k,'loop':loop,'loops':loops,'substep':sub,'mstep':mstep,'species':species,
                     'q_pre_kg_kg':before,'q_post_kg_kg':after,'q_actual_delta_kg_kg':after-before,
                     'dend_kg_m3':g[9][10],'delz_m':g[9][11], 'dtcld_s':g[9][12],
                     'lower_face_kg_m2':g[18][face] if 18 in g else '', 'upper_face_kg_m2':g[18][face+1] if 18 in g else ''}
                rows.append(row)
if {r['step'] for r in rows}!={831,839}: raise ValueError('missing selected step')
rows.sort(key=lambda r:(r['arm'],r['step'],r['j'],r['i'],r['species'],r['loop'],r['substep']))
out=HERE/'sediment_substeps.csv'
with out.open('x',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
print('rows',len(rows),'sha256',hashlib.sha256(out.read_bytes()).hexdigest())
