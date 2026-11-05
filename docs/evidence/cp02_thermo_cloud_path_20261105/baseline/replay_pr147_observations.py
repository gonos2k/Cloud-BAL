#!/usr/bin/env python3
"""Replay prior paired observations; unchanged initial points are diagnostics only."""
from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
import tempfile

import numpy as np
from netCDF4 import Dataset

ROOT = Path(__file__).resolve().parents[4]
PRIOR = ROOT / 'docs/evidence/cp02_failure_regimes_20261104'
OUT = ROOT / 'docs/evidence/cp02_thermo_cloud_path_20261105/baseline'
PINS = {
    'science/local_initial_change.csv': '658c18fa55ed6b3a12ff6ecd03fff845a8628ee160a49fe5ba57ea30577d541c',
    'state/results/receipt.json': '9e6a4cea51bdd88ae45a6052e6818a07ee5003de7dfc5dc2050c048075277d8c',
    'state/protocol.json': '5f44ad36d60e3443f7da7bbf7253359160114e954d3015ed8cef6ca059237690',
}
GROUPS = ('new_false_alarm', 'removed_false_alarm', 'retained_false_alarm')
FIVE = (16606, 17051, 17199, 17792, 20183)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load_pinned():
    for rel, expected in PINS.items():
        if sha(PRIOR / rel) != expected:
            raise ValueError(f'prior pinned artifact changed: {rel}')
    receipt = json.loads((PRIOR/'state/results/receipt.json').read_text())
    protocol = json.loads((PRIOR/'state/protocol.json').read_text())
    if receipt.get('status') != 'PASS' or receipt.get('protocol_sha256') != PINS['state/protocol.json']:
        raise ValueError('prior state receipt does not bind pinned protocol')
    records = {(r['case'], r['time']): r for r in receipt['records']}
    if len(records) != 24 or len(receipt['records']) != 24:
        raise ValueError('prior case/time inventory differs')
    states = {}
    for arm in ('B1', 'DM065'):
        for tag in ('input', 'h01'):
            item = records[arm, tag]; path = PRIOR/'state/results'/item['name']
            if sha(path) != item['sha256'] or path.stat().st_size != item['size_bytes']:
                raise ValueError(f'prior state file differs: {path}')
            with np.load(path, allow_pickle=False) as data:
                states[arm, tag] = {key: np.array(data[key]) for key in data.files}
    raw = {arm: protocol['case_time_files'][arm]['h01'] for arm in ('B1', 'DM065')}
    for arm, item in raw.items():
        p = Path(item['path'])
        if p.stat().st_size != item['size_bytes'] or sha(p) != item['sha256']:
            raise ValueError(f'{arm} raw +1-hour history differs')
    return states, raw


def run():
    states, raw = load_pinned()
    with (PRIOR/'science/local_initial_change.csv').open(newline='', encoding='utf-8') as stream:
        rows = [r for r in csv.DictReader(stream) if r['focus_group']=='lead2_false_alarm' and
                r['transition'] in GROUPS and r['initial_nr_changed']=='False']
    counts = {g: sum(r['transition']==g for r in rows) for g in GROUPS}
    if counts != {'new_false_alarm':15, 'removed_false_alarm':12, 'retained_false_alarm':252}:
        raise ValueError('prior initial-unchanged focus populations changed')
    keys = [(r['transition'],int(r['flat_index_yx'])) for r in rows]
    if len(set(keys)) != len(keys):
        raise ValueError('duplicate focus point')
    base = states['B1','input']; ids=base['flat_index_yx']; lookup={int(v):i for i,v in enumerate(ids)}
    for state in states.values():
        for field in ('flat_index_yx','latitude','longitude','native_j_zero_based','native_i_zero_based','corner_weights'):
            if not np.array_equal(base[field],state[field]):
                raise ValueError(f'prior state coordinate mismatch: {field}')
    rawfiles={arm:Dataset(item['path']) for arm,item in raw.items()}
    output=[]
    try:
        for row in rows:
            point=int(row['flat_index_yx']); i=lookup[point]; weights=base['corner_weights'][i];positive=weights>0
            if float(row['latitude']) != base['latitude'][i] or float(row['longitude']) != base['longitude'][i]:
                raise ValueError('focus coordinates differ')
            item={'group':row['transition'],'flat_index_yx':point,'latitude':float(row['latitude']),'longitude':float(row['longitude'])}
            for tag in ('input','h01'):
                for field in ('corner_qrain_kgkg','corner_qnrain_per_kg'):
                    a=states['B1',tag][field][i][:,positive];b=states['DM065',tag][field][i][:,positive]
                    item[f'{tag}_{field}_both_zero'] = bool(np.all(a==0) and np.all(b==0))
                    item[f'{tag}_{field}_maxabs_delta'] = float(np.max(np.abs(b.astype(np.float64)-a.astype(np.float64))))
            for field in ('rh_liquid','temperature_K','pressure_Pa','qvapor_kgkg'):
                a=states['B1','h01'][field][i,1];b=states['DM065','h01'][field][i,1]
                item[f'h01_k2_{field}_delta'] = float(np.float64(b)-np.float64(a))
            for field in ('rh_liquid','temperature_K'):
                key=f'layer_0to1km_{field}_level_mean';a=states['B1','h01'][key][i];b=states['DM065','h01'][key][i]
                item[f'h01_0to1km_{field}_delta'] = float(np.float64(b)-np.float64(a)) if np.isfinite(a) and np.isfinite(b) else ''
            jj=base['native_j_zero_based'][i];ii=base['native_i_zero_based'][i]
            for var in ('QVAPOR','T','P','PB'):
                chunks=[]
                for arm in ('B1','DM065'):
                    ds=rawfiles[arm]
                    chunks.append(np.stack([np.asarray(ds.variables[var][0,:,int(y),int(x)],dtype=np.float64) for y,x in zip(jj[positive],ii[positive])],axis=1))
                delta=np.abs(chunks[1]-chunks[0]); k,c=np.unravel_index(np.argmax(delta),delta.shape)
                item[f'h01_raw_{var}_maxabs_delta']=float(delta[k,c]);item[f'h01_raw_{var}_max_level_1based']=int(k+1)
            output.append(item)
    finally:
        for ds in rawfiles.values(): ds.close()
    selected=[r for r in output if r['group']=='new_false_alarm']
    if any(not r['input_corner_qrain_kgkg_both_zero'] or not r['input_corner_qnrain_per_kg_both_zero'] for r in selected):
        raise ValueError('one of 15 initial cases is not zero at every positive-weight corner/level')
    zero=[r for r in selected if r['h01_corner_qrain_kgkg_both_zero'] and r['h01_corner_qnrain_per_kg_both_zero']]
    if sorted(r['flat_index_yx'] for r in zero)!=list(FIVE):
        raise ValueError('five dry-rain +1-hour point identities differ')
    if any(not all(r[f'h01_raw_{v}_maxabs_delta']>0 for v in ('QVAPOR','T','P')) for r in zero):
        raise ValueError('one dry-rain point lacks qv/T/P difference')
    summaries={}
    for group in GROUPS:
        subset=[r for r in output if r['group']==group]
        summaries[group]={'points':len(subset)}
        for field in ('rh_liquid','temperature_K'):
            for layer in ('k2','0to1km'):
                key=f'h01_{layer}_{field}_delta';values=np.array([r[key] for r in subset if r[key]!=''],dtype=np.float64)
                summaries[group][f'{key}_n']=len(values)
                summaries[group][f'{key}_median']=float(np.median(values)) if values.size else None
    for arm,item in raw.items():
        if sha(item['path']) != item['sha256']:
            raise ValueError(f'{arm} +1-hour source changed during replay')
    for rel,expected in PINS.items():
        if sha(PRIOR/rel)!=expected:raise ValueError('prior pin changed during replay')
    target=OUT/'pr147_observation_replay.csv';receipt=OUT/'pr147_observation_replay.json'
    if os.path.lexists(target) or os.path.lexists(receipt):raise FileExistsError('preserve existing replay')
    fd,tmp=tempfile.mkstemp(prefix='.replay-',dir=OUT)
    try:
        with os.fdopen(fd,'w',newline='',encoding='utf-8') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(output[0]),lineterminator='\n');writer.writeheader();writer.writerows(output)
        record={'status':'PASS','groups':summaries,'rows':len(output),'five_h01_both_qrain_qnrain_zero':list(FIVE),'initial_15_all_corners_all_levels_zero':True,
                'id20183_qv_max_level_1based':next(r['h01_raw_QVAPOR_max_level_1based'] for r in zero if r['flat_index_yx']==20183),
                'id20183_t_max_level_1based':next(r['h01_raw_T_max_level_1based'] for r in zero if r['flat_index_yx']==20183),
                'input_pins':PINS,'raw_history_pins':raw,'source_sha256':sha(Path(__file__)),'csv_sha256':sha(tmp),
                'limitations':'Eulerian fixed-location snapshots, not trajectories or source attribution; sampled h01 is not first divergence; RH/T medians use saved rounded f32 snapshots and are descriptive.'}
        os.link(tmp,target)
        with receipt.open('x',encoding='utf-8') as stream:json.dump(record,stream,indent=2,sort_keys=True);stream.write('\n')
    finally:
        Path(tmp).unlink(missing_ok=True)
    return record

if __name__=='__main__':print(json.dumps(run(),sort_keys=True))
