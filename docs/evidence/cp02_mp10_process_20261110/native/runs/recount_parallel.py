#!/usr/bin/env python3
"""Recount raw versus compact bits with bounded independent chunk workers."""
from concurrent.futures import ProcessPoolExecutor
import gzip,json,sys
import numpy as np
from read_frames_constants import frames
from compact_v2 import GROUPS,NATIVE,RUNTIME,sha


def compare_chunk(task):
    case,out,group,first,counts=task
    stem='surface' if group=='surface' else 'cp04'
    paths=sorted(case.glob(f'{stem}_t{first:06d}-*_rank*.bin'))
    files=iter(sorted(out.glob(f'{group}_{first:06d}_*.npz')))
    keys_array=None;bits_array=None;index=0;total=0
    def compare(key,bits):
        nonlocal keys_array,bits_array,index,total
        if keys_array is None or index==len(keys_array):
            try:
                with np.load(next(files),allow_pickle=False) as data:keys_array=data['keys'];bits_array=data['bits']
            except StopIteration:raise ValueError('compact missing rows')
            index=0
        if not np.array_equal(keys_array[index],np.asarray(key,dtype=np.int32)):raise ValueError('compact key mismatch')
        if not np.array_equal(bits_array[index,:len(bits)],bits):raise ValueError('compact payload bit mismatch')
        if np.any(bits_array[index,len(bits):]):raise ValueError('nonzero padding')
        index+=1;total+=1
    for path in paths:
        for head,constants,records in frames(path,counts):
            rank,call,step,j,its,ite,kts,kte=head
            if group=='constants':compare((step,rank,call,j,0,0,0,0,0,0,0,len(constants)),constants.astype(np.float32).view(np.uint32))
            for phase,i,k,loop,loops,sub,mstep,values in records:
                if phase not in GROUPS[group]:continue
                bits=values.astype(np.float64 if group=='faces' else np.float32).view(np.uint64 if group=='faces' else np.uint32)
                compare((step,rank,call,j,i,k,loop,loops,sub,mstep,phase,len(values)),bits)
    if keys_array is not None and index!=len(keys_array):raise ValueError('extra compact rows')
    if next(files,None) is not None:raise ValueError('extra compact file')
    return group,total

def main():
    arm=sys.argv[1];case=RUNTIME/arm;out=NATIVE/'compact'/arm
    receipt=json.loads((out/'capture_receipt.json').read_text());schema=json.loads((NATIVE/'schema/schema.json').read_text())
    counts={int(k):len(v['fields']) for k,v in schema['phases'].items()};ov=schema['arm_overrides']['CONTROL and MP10'];counts[10]=len(ov['phase_10_fields'])
    for p in ov['absent_phases']:counts.pop(p,None)
    for item in receipt['sources']:
        path=case/item['name']
        if sha(path)!=item['sha256'] or path.stat().st_size!=item['size_bytes']:raise ValueError('raw source hash mismatch')
    tasks=[]
    for group in GROUPS:
        firsts=sorted({int(p.name.split('_')[1]) for p in out.glob(group+'_*.npz')})
        expected=set(range(1,1081,3)) if group=='surface' else set(range(1,181,3))|set(range(361,541,3))|set(range(901,1081,3))
        if set(firsts)!=expected:raise ValueError('compact chunk coverage mismatch: '+group)
        tasks.extend((case,out,group,first,counts) for first in firsts)
    totals={g:0 for g in GROUPS}
    with ProcessPoolExecutor(max_workers=8) as pool:
        for group,n in pool.map(compare_chunk,tasks,chunksize=1):totals[group]+=n
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
    for item in receipt['sources']:
        if sha(case/item['name'])!=item['sha256']:raise ValueError('raw source changed during recount')
    result={'status':'PASS','arm':arm,'record_counts':totals,'wrapper_files_byte_equal':wrappers,'capture_receipt_sha256':sha(out/'capture_receipt.json'),'workers':8,'method':'every retained key and native IEEE payload bit compared in raw stream order; no numeric tolerance'}
    (out/'raw_recount_receipt.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
