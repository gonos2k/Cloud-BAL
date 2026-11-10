#!/usr/bin/env python3
"""Reproduce matched conservative/first-ice REAL64 face comparisons from pinned raw chunks."""
import hashlib
import json
from pathlib import Path
import re
import sys
import numpy as np
from read_frames import frames

NATIVE=Path(__file__).resolve().parents[1]
RUNTIME=NATIVE.parents[3].parent/'runtime/forecasts'


def sha(p):
    with Path(p).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()


def load_arm(arm):
    out=NATIVE/'compact'/arm; receipt=json.loads((out/'capture_receipt.json').read_text())
    if receipt['status']!='COMPLETE' or sha(out/'raw_inventory.json')!=receipt['raw_inventory_sha256']:
        raise ValueError('capture or raw inventory is not bound')
    run=RUNTIME/arm
    if sha(run/'run_receipt.json')!=receipt['run_receipt_sha256'] or sha(run/'history_comparison.json')!=receipt['history_comparison_sha256']:
        raise ValueError('run/history receipt changed')
    inv=json.loads((out/'raw_inventory.json').read_text())
    chunks={r['name']:r for r in inv if r['name'].startswith('cp04_t')}
    return run,receipt,chunks


def read_chunk(path, expected):
    if sha(path)!=expected['sha256'] or path.stat().st_size!=expected['size_bytes']: raise ValueError('raw chunk identity changed')
    schema=json.loads((NATIVE/'schema/schema.json').read_text()); counts={int(k):len(v['fields']) for k,v in schema['phases'].items()}
    counts.pop(23); counts[10]=len(schema['arm_overrides']['CONSERVATIVE and ICE_FIXED']['phase_10_fields'])
    result={}
    for (rank,call,step,j,its,ite,kts,kte), records in frames(path,counts):
        for phase,i,k,loop,loops,sub,mstep,v in records:
            if phase not in (18,22): continue
            key=(phase,step,rank,call,j,i,k,loop,loops,sub,mstep)
            if key in result: raise ValueError('duplicate shared face key')
            result[key]=v.astype(np.float64)
    return result


def main():
    a,ra,ia=load_arm('CONSERVATIVE'); b,rb,ib=load_arm('ICE_FIXED')
    if set(ia)!=set(ib): raise ValueError('shared flux raw chunk filenames differ')
    totals={p:{'matched':0,'only_conservative':0,'only_ice_fixed':0,'sum_delta':None,'max_abs_delta':None} for p in (18,22)}
    for name in sorted(ia):
        x=read_chunk(a/name,ia[name]); y=read_chunk(b/name,ib[name]); shared=x.keys()&y.keys()
        for p in (18,22):
            ka={key for key in x if key[0]==p}; kb={key for key in y if key[0]==p}; both=ka&kb
            row=totals[p];row['matched']+=len(both);row['only_conservative']+=len(ka-kb);row['only_ice_fixed']+=len(kb-ka)
            for key in sorted(both):
                delta=y[key]-x[key]
                row['sum_delta']=delta.copy() if row['sum_delta'] is None else row['sum_delta']+delta
                row['max_abs_delta']=np.abs(delta) if row['max_abs_delta'] is None else np.maximum(row['max_abs_delta'],np.abs(delta))
    for row in totals.values():
        for field in ('sum_delta','max_abs_delta'):
            if row[field] is not None: row[field]=row[field].tolist()
    result={'status':'PASS','difference':'ICE_FIXED minus CONSERVATIVE','matching':'phase,step,rank,call,j,i,k,loop,loops,substep,mstep all equal; unmatched records excluded and counted','float_kind':'REAL64 native transfers','fields':{p:json.loads((NATIVE/'schema/schema.json').read_text())['phases'][str(p)]['fields'] for p in (18,22)},'totals':totals,'reference_capture_sha256':{'CONSERVATIVE':sha(NATIVE/'compact/CONSERVATIVE/capture_receipt.json'),'ICE_FIXED':sha(NATIVE/'compact/ICE_FIXED/capture_receipt.json')},'baseline':'FIX uses legacy REAL32 local falk and has no equivalent shared-transfer field; comparisons to FIX are unavailable, not zero'}
    output=Path(sys.argv[1]); output.write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__': main()
