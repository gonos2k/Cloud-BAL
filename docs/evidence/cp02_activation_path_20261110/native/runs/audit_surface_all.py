#!/usr/bin/env python3
"""Replay each recorded positive rain increment in native float32 source order."""
import csv,json,sys
from pathlib import Path
import numpy as np
from compact_v2 import NATIVE,sha


def bits(x):return np.asarray(x,dtype=np.float32).view(np.uint32)
def main():
    arm=sys.argv[1];loops={'CONTROL':1,'MP10':2}[arm];folder=NATIVE/'compact'/arm
    capture=folder/'capture_receipt.json';recount=folder/'raw_recount_receipt.json'
    audit=json.loads(recount.read_text())
    if audit['status']!='PASS' or audit['capture_receipt_sha256']!=sha(capture):raise ValueError('recount not passed or not bound to capture')
    cells={(int(r['i_fortran']),int(r['j_fortran'])) for r in csv.DictReader((NATIVE.parent/'cohorts/native_columns.csv').open())}
    counts={'positive_updates':0,'conditional_branch_not_executed':0,'loop_boundaries':0,'step_columns':0,'solid_carry':0};file_count=0
    for path in sorted(folder.glob('surface_*.npz')):
        with np.load(path,allow_pickle=False) as data:keys=data['keys'];raw=data['bits']
        records={}
        for k,v in zip(keys,raw):
            step,rank,call,j,i,z,loop,nloop,sub,mstep,phase,nfields=map(int,k)
            key=(step,i,j,loop,phase)
            if key in records:raise ValueError('duplicate surface phase')
            records[key]=v[:nfields].copy()
        steps=sorted({k[0] for k in records})
        for step in steps:
            for i,j in cells:
                get=lambda loop,p:records.get((step,i,j,loop,p))
                pre=get(0,40);reset=get(0,41)
                if pre is None or reset is None or pre[0]!=reset[0] or reset[1]!=0:raise ValueError('outer rain reset differs')
                for loop in range(1,loops+1):
                    start=get(loop,42);end=get(loop,43);p=get(loop,46);q=get(loop,47)
                    if start is None or end is None:raise ValueError('missing loop boundary')
                    if loop==1 and not np.array_equal(start,reset):raise ValueError('first loop differs from reset')
                    if loop>1 and not np.array_equal(start,get(loop-1,43)):raise ValueError('rain loop carry differs')
                    if (p is None)!=(q is None):raise ValueError('unpaired executed update')
                    if p is None:
                        if not np.array_equal(start,end):raise ValueError('unrecorded update')
                        counts['conditional_branch_not_executed']+=1
                    else:
                        a=p.view(np.float32);b=q.view(np.float32)
                        if not np.array_equal(p[-2:],start) or not np.array_equal(q[-2:],end):raise ValueError('executed update boundaries differ')
                        if not a[4]>0 or not np.array_equal(p[:10],q[:10]):raise ValueError('invalid fall operands')
                        x=np.float32(a[4]*a[7]);x=np.float32(x/a[8]);x=np.float32(x*a[9]);x=np.float32(x*np.float32(1000))
                        expected=np.array([np.float32(a[-2]+x),np.float32(a[-1]+x)],dtype=np.float32)
                        if not np.array_equal(bits(expected),q[-2:]):raise ValueError('source-order REAL32 accumulation differs')
                        counts['positive_updates']+=1
                    if loop>1:
                        for endp,startp in ((53,52),(63,62),(73,72)):
                            a,b=get(loop-1,endp),get(loop,startp)
                            if (a is None)!=(b is None) or (a is not None and not np.array_equal(a,b)):raise ValueError('solid carry differs')
                            if a is not None:counts['solid_carry']+=1
                    counts['loop_boundaries']+=1
                counts['step_columns']+=1
        file_count+=1
    if file_count!=180 or counts['step_columns']!=540*len(cells) or counts['positive_updates']==0:raise ValueError('incomplete or vacuous all-step audit')
    result={'status':'PASS','arm':arm,'steps':[1,540],'columns':len(cells),'loops':loops,**counts,'capture_receipt_sha256':sha(capture),'raw_recount_sha256':sha(recount),'method':'actual fallsum>0 operands and before/after counters replayed in source order REAL32; missing conditional updates checked against equal loop boundaries; exact bits','branch_absence':'phase 46 absent means positive-fallsum branch not executed; fallsum value itself was not measured on that branch', 'limitation':'snow and graupel overlap total precipitation; cumulative RAINNC subtraction may differ due to rounding'}
    (folder/'surface_audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
