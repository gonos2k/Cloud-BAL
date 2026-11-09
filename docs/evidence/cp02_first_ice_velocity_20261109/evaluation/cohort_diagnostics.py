#!/usr/bin/env python3
"""Trace frozen PR153 failure cohorts and two named points across forecast leads."""
import argparse
import csv
import json
import os
from pathlib import Path
import shutil
import tempfile
import numpy as np
from evaluate import B1, CASES, CONS, HOURS, NEW, ORIGINAL, identity, publish_new, read_arrays, score


def cohort_indices(arrays):
    h4=arrays[16]; h6=arrays[18]
    lost=np.flatnonzero((h4['reference']>=5) & (h4[B1]>=5) & (h4[CONS]<5))
    false_alarm=np.flatnonzero((h6['reference']<5) & (h6[B1]<5) & (h6[CONS]>=5))
    if len(lost)!=8 or len(false_alarm)!=102: raise ValueError('frozen PR153 cohort counts differ')
    return {'h4_pr153_hit_loss':lost, 'h6_pr153_new_false_alarm':false_alarm}


def collect(arrays):
    groups=cohort_indices(arrays); ids=arrays[13]['flat_index_yx']; rows=[]
    for name in ('point_12461','point_10196'):
        matches=np.flatnonzero(ids==int(name.split('_')[1]))
        if len(matches)!=1: raise ValueError(f'{name}: missing or duplicate')
        groups[name]=matches
    for group, indexes in groups.items():
        for index in indexes:
            row={'cohort':group,'flat_index_yx':int(ids[index]),'latitude':float(arrays[13]['latitude'][index]),'longitude':float(arrays[13]['longitude'][index])}
            for field in ('reference',*CASES):
                for hour in range(15,19): row[f'{field}_h{hour-12}_mm']=float(arrays[hour][field][index])
                for label,hours in (('h3_h5',(15,16,17)),('h5_h6',(17,18))): row[f'{field}_{label}_sum_mm']=float(sum(arrays[h][field][index] for h in hours))
            h4,h6=arrays[16],arrays[18]
            row.update(h4_observed_event=bool(h4['reference'][index]>=5),h4_new_event=bool(h4[NEW][index]>=5),h6_observed_event=bool(h6['reference'][index]>=5),h6_new_event=bool(h6[NEW][index]>=5))
            rows.append(row)
    lost=groups['h4_pr153_hit_loss']; false_alarm=groups['h6_pr153_new_false_alarm']
    summary={'selection':'frozen PR153 versus B1; selected independently of FIRST_ICE_VELOCITY','h4_pr153_hit_loss':{'count':len(lost),'new_hit_recovered':int((arrays[16][NEW][lost]>=5).sum()),'new_still_missed':int((arrays[16][NEW][lost]<5).sum())},'h6_pr153_new_false_alarm':{'count':len(false_alarm),'new_false_alarm_removed':int((arrays[18][NEW][false_alarm]<5).sum()),'new_false_alarm_remains':int((arrays[18][NEW][false_alarm]>=5).sum())},'named_points':[12461,10196],'scope':'diagnostic only; fixed 26-condition admission unchanged','time_windows':'initial 2026-08-16 12 UTC; each lead denotes the preceding UTC hour; sums are hourly amounts'}
    return rows,summary


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--results',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    if os.path.lexists(args.output): raise FileExistsError(args.output)
    arrays=read_arrays(args.results);score(arrays)
    inputs=[identity(args.results/'receipt.json')]+[identity(args.results/f'hour_{h}_arrays.npz') for h in HOURS]
    rows,summary=collect(arrays);args.output.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.cohort-stage-',dir=args.output.parent))
    try:
        with (stage/'cohorts.csv').open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)
        (stage/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
        for record in inputs:
            if identity(record['path'])!=record: raise ValueError('input changed')
        receipt={'status':'COMPLETE','inputs':inputs,'source':identity(__file__),'outputs':{f.name:identity(f)['sha256'] for f in sorted(stage.iterdir())}}
        (stage/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');publish_new(stage,args.output)
        print(json.dumps(summary))
    finally:
        if stage.exists():shutil.rmtree(stage)

if __name__=='__main__':main()
