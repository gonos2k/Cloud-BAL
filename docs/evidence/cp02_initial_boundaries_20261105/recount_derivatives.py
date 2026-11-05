#!/usr/bin/env python3
"""Independently recount portable sparse derivatives without external captures."""
import csv
import hashlib
import json
from pathlib import Path
import struct
import numpy as np

HERE = Path(__file__).resolve().parent
RESULTS = HERE / 'results'
RECEIPT = 'f76b74141410d5b287c554467fd0f3803fe9a8c8debceb6e33dd30639aa69681'
FIELDS = ('NR','QV','QC','TH','TK')


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    if sha(RESULTS/'receipt.json') != RECEIPT:
        raise ValueError('capture receipt changed')
    rec = json.loads((RESULTS/'receipt.json').read_text())
    if rec['status'] != 'PASS' or rec['plan_sha256'] != sha(HERE/'plan.json'):
        raise ValueError('capture/plan binding differs')
    for name, info in rec['outputs'].items():
        path=RESULTS/name
        if path.stat().st_size != info['bytes'] or sha(path) != info['sha256']:
            raise ValueError(f'derivative changed: {name}')
    with np.load(RESULTS/'domain_and_support.npz', allow_pickle=False) as data:
        called=data['called'];owners=data['owner_token'];input_support=data['initial_NR_changed'];entry_support=data['entry_NR_changed']
        if called.shape != (282,234,39) or not np.array_equal(owners >= 0,called):
            raise ValueError('owner support differs')
        if not np.array_equal(data['initial_NR_changed_levels'],input_support.sum(axis=2)) or not np.array_equal(data['entry_NR_changed_levels'],entry_support.sum(axis=2)):
            raise ValueError('horizontal supports differ')
    valid=called.transpose(0,2,1).reshape(-1);size=valid.size
    masks={};payload={}
    for name in ['initial_NR']+[f'{s}_{f}' for s in ('entry','return') for f in FIELDS]:
        with np.load(RESULTS/'sparse'/f'{name}.npz', allow_pickle=False) as data:
            ix=data['index_jki_zero_based'];a=data['B1'];b=data['DM065']
            if ix.ndim != 1 or len(ix)!=len(a) or len(a)!=len(b) or np.any(ix<0) or np.any(ix>=size) or np.any(np.diff(ix)<=0):
                raise ValueError(f'invalid sparse keys: {name}')
            if not np.isfinite(a).all() or not np.isfinite(b).all() or np.any(a==b):
                raise ValueError(f'invalid sparse values: {name}')
            if name != 'initial_NR' and not valid[ix].all():
                raise ValueError('stage difference includes uncalled cell')
            mask=np.zeros(size,dtype=bool);mask[ix]=True;masks[name]=mask
            payload[name]=(ix.copy(),a.copy(),b.copy())
    if not np.array_equal(masks['initial_NR'].reshape(282,39,234).transpose(0,2,1),input_support) or not np.array_equal(masks['entry_NR'].reshape(282,39,234).transpose(0,2,1),entry_support):
        raise ValueError('sparse and dense supports differ')
    summary=rec['summary'];assert int(valid.sum())==summary['called_cells'] and int((~valid).sum())==summary['uncalled_cells']
    ini=masks['initial_NR'];assert int(ini.sum())==summary['input_nr_changed_all'] and int((ini&valid).sum())==summary['input_nr_changed_called'] and int((ini&~valid).sum())==summary['input_nr_changed_uncalled']
    for name, info in summary['comparisons'].items():
        mask=masks[name]; cross={'neither':int((valid&~ini&~mask).sum()),'input_only':int((valid&ini&~mask).sum()),'entry_only':int((valid&~ini&mask).sum()),'both':int((valid&ini&mask).sum())}
        if int(mask.sum())!=info['changed'] or cross!=info['input_NR_cross']:
            raise ValueError('global cross-tabulation differs')
    with (RESULTS/'anchors.csv').open(newline='') as stream:rows=list(csv.DictReader(stream))
    if len(rows)!=624 or len({(r['flat_index_yx'],r['corner'],r['k_1based']) for r in rows})!=624:
        raise ValueError('anchor inventory differs')
    for r in rows:
        i,j,k=(int(r[f'{x}_1based']) for x in ('i','j','k'));ix=((j-1)*39+k-1)*234+i-1
        if (r['called']=='True') != bool(valid[ix]):raise ValueError('anchor ownership differs')
        comparisons=[('initial_NR','input_NR')]+[(f'{s}_{f}',f'{s}_{f}') for s in ('entry','return') for f in FIELDS]
        for name,col in comparisons:
            if name!='initial_NR' and not valid[ix]:continue
            raw=[bytes.fromhex(r[f'{arm}_{col}_f32_le_hex']) for arm in ('B1','DM065')]
            values=[struct.unpack('<f',x)[0] for x in raw]
            if (values[0]!=values[1]) != bool(masks[name][ix]):raise ValueError('anchor difference mask differs')
            if masks[name][ix]:
                indices,a,b=payload[name];at=int(np.searchsorted(indices,ix))
                if at>=len(indices) or indices[at]!=ix or struct.pack('<f',float(a[at]))!=raw[0] or struct.pack('<f',float(b[at]))!=raw[1]:raise ValueError('anchor raw words differ')
    print(json.dumps({'status':'PASS_PORTABLE_DERIVATIVE_RECOUNT','receipt_sha256':RECEIPT,'called':int(valid.sum()),'uncalled':int((~valid).sum()),'anchor_rows':len(rows),'sparse_files':len(masks),'source_sha256':sha(Path(__file__))}))


if __name__=='__main__':main()
