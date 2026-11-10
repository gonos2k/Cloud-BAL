#!/usr/bin/env python3
"""Freeze named adjacent observation points using the sealed PR158 mapping and arrays."""
import csv, hashlib, json, sys
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[4]
BUNDLE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'tools'))
import cp02_mp10_failure_cohorts as original

RESULTS=ROOT/'docs/evidence/cp02_pulse_path_20261110/evaluation/results'
PRIOR=ROOT/'docs/evidence/cp02_mp10_process_20261110/cohorts/receipt.json'
POINTS=(12000,12001,12002)

def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    previous=json.loads(PRIOR.read_text()); pins={Path(x['path']).name:x['sha256'] for x in previous['inputs']}
    inventory=original.fa.INVENTORY
    files=[inventory,RESULTS/'receipt.json',RESULTS/'bilinear_mapping.npz']+[RESULTS/f'hour_{h}_arrays.npz' for h in original.e.HOURS]
    for p in files:
        if sha(p)!=pins[p.name]:raise ValueError(f'frozen input changed: {p}')
    arrays=original.prior.read_arrays(RESULTS)
    with np.load(RESULTS/'bilinear_mapping.npz',allow_pickle=False) as data:mapping={k:data[k].copy() for k in data.files}
    offsets=original.fa.crop_offsets(json.loads(inventory.read_text()))
    rows=original.paths(arrays,mapping,[('h3_weak_adjacent',x,'') for x in POINTS],offsets)
    columns=sorted({(r['native_j0_fortran_one_based']+dj,r['native_i0_fortran_one_based']+di) for r in rows for dj in (0,1) for di in (0,1)})
    expected=[(j,i) for j in (86,87) for i in (155,156,157,158)]
    if columns!=expected:raise ValueError(f'unexpected union: {columns}')
    old=list(csv.DictReader((ROOT/'docs/evidence/cp02_mp10_process_20261110/cohorts/selected_points.csv').open()))
    oldrow=next(x for x in old if x['flat_index_yx']=='12001')
    for key,value in rows[1].items():
        if key not in ('cohort','target_flat_index_yx') and str(value)!=oldrow[key]:raise ValueError(f'12001 differs from parent: {key}')
    path=BUNDLE/'selected_points.csv'
    with path.open('x',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    selector=BUNDLE/'native_columns.csv'
    if list(csv.reader(selector.open()))!=[['j_fortran','i_fortran']]+[[str(j),str(i)] for j,i in expected]:raise ValueError('selector differs')
    receipt={'status':'PASS','point_ids':POINTS,'mapping_and_array_inputs':{str(p):sha(p) for p in files},'parent_receipt_sha256':sha(PRIOR),'parent_12001_values_match':True,'native_columns':expected,'selector_sha256':sha(selector),'selected_points_sha256':sha(path),'generator_sha256':sha(Path(__file__)),'crop_to_native_zero_based_offsets':{'j':offsets[0],'i':offsets[1]}}
    (BUNDLE/'mapping_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))
if __name__=='__main__':main()
