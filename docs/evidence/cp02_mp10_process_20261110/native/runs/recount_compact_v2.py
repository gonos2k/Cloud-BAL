#!/usr/bin/env python3
"""Compare every compact native record bit-for-bit against the retained raw stream."""
import gzip, hashlib, json, sys
from pathlib import Path
import numpy as np
from read_frames_constants import frames
from compact_v2 import GROUPS, NATIVE, RUNTIME, sha


def main():
    arm=sys.argv[1];case=RUNTIME/arm;out=NATIVE/'compact'/arm
    receipt=json.loads((out/'capture_receipt.json').read_text())
    schema=json.loads((NATIVE/'schema/schema.json').read_text())
    counts={int(k):len(v['fields']) for k,v in schema['phases'].items()}
    ov=schema['arm_overrides']['CONTROL and MP10'];counts[10]=len(ov['phase_10_fields'])
    for p in ov['absent_phases']:counts.pop(p,None)
    for item in receipt['sources']:
        path=case/item['name']
        if sha(path)!=item['sha256'] or path.stat().st_size!=item['size_bytes']:raise ValueError('raw source hash mismatch')
    totals={}
    for group in GROUPS:
        stem='surface' if group=='surface' else 'cp04'
        compact=sorted(out.glob(group+'_*.npz'))
        firsts=sorted({int(p.name.split('_')[1]) for p in compact})
        total=0
        for first in firsts:
            paths=sorted(case.glob(f'{stem}_t{first:06d}-*_rank*.bin'))
            files=iter(sorted(out.glob(f'{group}_{first:06d}_*.npz')))
            keys_array=None;bits_array=None;index=0
            def compare(key,bits):
                nonlocal keys_array,bits_array,index,total
                if keys_array is None or index==len(keys_array):
                    try:
                        with np.load(next(files),allow_pickle=False) as data:
                            keys_array=data['keys'];bits_array=data['bits']
                    except StopIteration:raise ValueError('compact missing rows')
                    index=0
                if not np.array_equal(keys_array[index],np.asarray(key,dtype=np.int32)):raise ValueError('compact key mismatch')
                if not np.array_equal(bits_array[index,:len(bits)],bits):raise ValueError('compact payload bit mismatch')
                if np.any(bits_array[index,len(bits):]):raise ValueError('nonzero padding')
                index+=1;total+=1
            for path in paths:
                for head,constants,records in frames(path,counts):
                    rank,call,step,j,its,ite,kts,kte=head
                    if group=='constants':
                        compare((step,rank,call,j,0,0,0,0,0,0,0,len(constants)),constants.astype(np.float32).view(np.uint32))
                    for phase,i,k,loop,loops,sub,mstep,values in records:
                        if phase not in GROUPS[group]:continue
                        bits=values.astype(np.float64 if group=='faces' else np.float32).view(np.uint64 if group=='faces' else np.uint32)
                        compare((step,rank,call,j,i,k,loop,loops,sub,mstep,phase,len(values)),bits)
            if keys_array is not None and index!=len(keys_array):raise ValueError('extra compact rows')
            if next(files,None) is not None:raise ValueError('extra compact file')
        totals[group]=total
    wrappers=0
    for path in sorted(out.glob('state_selected_*.bin.gz')):
        source=case/path.name.removesuffix('.gz')
        with gzip.open(path,'rb') as zipped,source.open('rb') as raw:
            while True:
                a=zipped.read(1024*1024);b=raw.read(1024*1024)
                if a!=b:raise ValueError('wrapper bytes differ')
                if not a:break
        wrappers+=1
    for item in receipt['outputs']:
        path=out/item['name']
        if sha(path)!=item['sha256'] or path.stat().st_size!=item['size_bytes']:raise ValueError('compact output hash mismatch')
    result={'status':'PASS','arm':arm,'record_counts':totals,'wrapper_files_byte_equal':wrappers,'capture_receipt_sha256':sha(out/'capture_receipt.json'),'method':'every retained key and native IEEE payload bit compared in raw stream order; no numeric tolerance'}
    (out/'raw_recount_receipt.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
