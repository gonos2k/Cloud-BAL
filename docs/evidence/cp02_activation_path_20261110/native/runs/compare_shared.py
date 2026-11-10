#!/usr/bin/env python3
"""Compare every shared-column native phase payload against PR158 raw streams."""
import collections, csv, hashlib, json, sys
from pathlib import Path
from read_frames_constants import frames
from read_wrapper import read_wrapper
import numpy as np

NATIVE=Path(__file__).resolve().parents[1]
ROOT=NATIVE.parents[3]
PARENT=ROOT.parent.parent/'b1_mp10_process_20261110'
CURRENT=ROOT.parent/'runtime/forecasts'
REFERENCE=PARENT/'runtime/forecasts'
OLD_CSV=PARENT/'Cloud-BAL/docs/evidence/cp02_mp10_process_20261110/cohorts/native_columns.csv'

def cells(path):
    return {(int(r['i_fortran']),int(r['j_fortran'])) for r in csv.DictReader(path.open())}

def sha(path):
    with path.open('rb') as stream: return hashlib.file_digest(stream,'sha256').hexdigest()

def records(paths, counts, shared):
    result=collections.Counter()
    for path in paths:
        for head, constants, values in frames(path, counts):
            rank,call,step,j,_,_,_,_=head
            for phase,i,k,loop,loops,sub,mstep,payload in values:
                if (i,j) in shared and phase not in (35,36):
                    key=(step,j,i,k,loop,loops,sub,mstep,phase)
                    result[(key,payload.tobytes())]+=1
    return result

def main():
    arm=sys.argv[1]; case=CURRENT/arm; reference=REFERENCE/arm
    shared=cells(NATIVE.parent/'cohorts/native_columns.csv') & cells(OLD_CSV)
    if shared!={(156,86),(157,86),(155,87),(156,87),(157,87)}:raise ValueError('unexpected shared geometry')
    schema=json.loads((NATIVE/'schema/schema.json').read_text()); counts={int(k):len(v['fields']) for k,v in schema['phases'].items()}
    ov=schema['arm_overrides']['CONTROL and MP10'];counts[10]=len(ov['phase_10_fields'])
    for p in ov['absent_phases']:counts.pop(p,None)
    totals=collections.Counter();source_hashes={}
    for first in range(361,541,3):
        pattern=f'cp04_t{first:06d}-{first+2:06d}_rank*.bin'
        old=sorted(reference.glob(pattern)); new=sorted(case.glob(pattern))
        if not old or not new:raise ValueError('missing process chunk')
        actual=records(new,counts,shared); expected=records(old,counts,shared)
        if actual!=expected:
            raise ValueError(f'raw process mismatch {first}: {sum((actual-expected).values())} extra, {sum((expected-actual).values())} missing')
        for (key,_),n in actual.items():totals[str(key[-1])]+=n
        source_hashes[str(first)]={'parent':{p.name:sha(p) for p in old},'current':{p.name:sha(p) for p in new}}
        steps=range(first,first+3)
        for stage,name in [(6,'entry'),(7,'return')]:
            pattern=f'state_selected_{name}_t{first:06d}-{first+2:06d}_rank*.bin'
            old_w=sorted(reference.glob(pattern));new_w=sorted(case.glob(pattern))
            a,_=read_wrapper(new_w,stage,steps,sorted(shared));b,_=read_wrapper(old_w,stage,steps,sorted(shared))
            if not np.array_equal(a.view(np.uint32),b.view(np.uint32)):raise ValueError(f'wrapper bits differ {first} {name}')
    if not totals:raise ValueError('vacuous comparison')
    result={'status':'PASS','arm':arm,'steps':[361,540],'shared_cells_ij':sorted(shared),'phase_record_counts':dict(totals),'wrapper':'both stages, all five columns, all 39 levels, each step bit-identical','method':'multiset of complete native phase record keys and raw big-endian IEEE payloads; includes missing-record identity; excludes new phases 35 and 36','source_sha256':source_hashes}
    (case/'shared_comparison.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='source_sha256'}))
if __name__=='__main__':main()
