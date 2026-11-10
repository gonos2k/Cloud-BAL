#!/usr/bin/env python3
"""Summarize fixed diagnostic anchors from sealed native boundary arrays."""
import argparse
import csv
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

B=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(B.parents[2]/'tools'))
from cp02_ice_false_alarm import evaluation
TARGETS=((1,9774),(3,12300),(6,12892),(6,12446))


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def read(path):
    with Path(path).open(newline='') as stream:return list(csv.DictReader(stream))


def write(path,rows):
    with Path(path).open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=rows[0],lineterminator='\n');writer.writeheader();writer.writerows(rows)


def main(folder):
    if folder.exists():raise FileExistsError(folder)
    receipt_path=B/'analysis/receipt.json';receipt=json.loads(receipt_path.read_text())
    if receipt['status']!='COMPLETE':raise ValueError('analysis incomplete')
    inputs={str(receipt_path):sha(receipt_path),str(Path(__file__)):sha(__file__)}
    for name,digest in receipt['outputs'].items():
        path=B/'analysis'/name
        if sha(path)!=digest:raise ValueError('analysis changed')
        inputs[str(path)]=digest
    surface_path=B/'surface/results/point_components.csv';inputs[str(surface_path)]=sha(surface_path)
    surface=read(surface_path);rows=[]
    for hour,point in TARGETS:
        row={'hour':hour,'point':point}
        for arm in ('CONTROL','MP10','paired'):
            with np.load(B/'analysis'/f'{arm}_h{hour:02d}.npz',allow_pickle=False) as data:
                p=list(data['point']).index(point)
                row[arm+'_zero_removed_kg_m2']=float(data['zero_removed_column'][:,p].sum())
                if arm=='paired':
                    for i,name in enumerate(data['psd_number_fields']):
                        row[str(name)+'_psd_difference_number_m2']=float(data['psd_number_column'][:,p,i].sum())
                    qr=list(data['source_fields']).index('QR')
                    row['max_abs_entry_QR_difference_kg_kg']=float(abs(data['entry'][:,p,:,qr]).max())
                    row['max_abs_zero_QR_difference_kg_kg']=float(abs(data['zero_delta'][:,p,:,qr]).max())
        paired_surface={case:next(r for r in surface if int(r['flat_index_yx'])==point and int(r['lead_hour'])==hour and r['case']==case)
                        for case in ('FIRST_ICE_VELOCITY','MP10')}
        for name in ('rainc_mm','rainnc_mm','total_mm'):
            row[name+'_difference']=float(paired_surface['MP10'][name])-float(paired_surface['FIRST_ICE_VELOCITY'][name])
        rows.append(row)
    ledger=[r for r in read(B/'analysis/public_ledger.csv') if (int(r['hour']),int(r['point'])) in TARGETS
            and int(r['k'])==2 and r['field'] in ('QV','QR','TK')]
    if len(ledger)!=12:raise ValueError('anchor ledger scope differs')
    if any(sha(path)!=digest for path,digest in inputs.items()):raise ValueError('input changed')
    folder.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.summary-',dir=folder.parent))
    try:
        write(stage/'target_operator_summary.csv',rows);write(stage/'k2_public_ledger.csv',ledger)
        result={'status':'COMPLETE','inputs':inputs,'outputs':{p.name:sha(p) for p in stage.iterdir()},
                'limits':['Fixed four diagnostic anchors; native k=2 is not a fixed altitude.',
                          'Zero removal uses source DEN*DELZ, number area uses DELZ only.',
                          'NN is an activation-number reservoir; its signed adjustment is not hydrometeor mass.',
                          'Signed operator sums and surface differences are not causal contributions.']}
        (stage/'receipt.json').write_text(json.dumps(result,indent=2)+'\n')
        evaluation.publish_new(stage,folder)
    finally:
        if stage.exists():shutil.rmtree(stage)



if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=B/'science/results')
    main(parser.parse_args().output)
