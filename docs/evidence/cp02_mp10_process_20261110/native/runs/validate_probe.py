#!/usr/bin/env python3
"""Audit observed 20-second native loop carry and source precipitation updates."""
import csv, json, sys
from pathlib import Path
import numpy as np
from read_frames import frames

NATIVE = Path(__file__).resolve().parents[1]
BUNDLE = NATIVE.parent

def bits(a): return np.asarray(a, dtype=np.float32).view(np.uint32)
def main():
    arm, dirname = sys.argv[1:]; folder = Path(dirname)
    expected_loops = {'CONTROL':1,'MP10':2}[arm]
    schema=json.loads((NATIVE/'schema/schema.json').read_text())
    counts={int(k):len(v['fields']) for k,v in schema['phases'].items()}
    overrides=schema['arm_overrides']['CONTROL and MP10']
    counts[10]=len(overrides['phase_10_fields'])
    for p in overrides['absent_phases']: counts.pop(p,None)
    cells={(int(r['i_fortran']),int(r['j_fortran'])) for r in csv.DictReader((BUNDLE/'cohorts/native_columns.csv').open())}
    state={}; surf={}; executed={}; actual=set(); face={18:0,22:0}
    for kind in ('cp04','surface'):
        paths=sorted(folder.glob(kind+'_t*_rank*.bin'))
        if not paths: raise ValueError('missing '+kind+' files')
        for path in paths:
            for header, records in frames(path,counts):
                rank,call,step,j,its,ite,kts,kte=header
                if step != 1 or (kts,kte)!=(1,39): raise ValueError('unexpected timestep or levels')
                for phase,i,k,loop,loops,substep,mstep,v in records:
                    if (i,j) not in cells: raise ValueError('outside selector')
                    key=(i,j,k,loop)
                    if phase in (30,32,33,34):
                        if loops != expected_loops or not 1<=loop<=loops: raise ValueError('wrong loop count')
                        if float(v[5]) != 20./expected_loops: raise ValueError('wrong actual dtcld')
                        if (phase,key) in state: raise ValueError('duplicate state')
                        state[phase,key]=bits(v).copy(); actual.add((i,j,k))
                    if phase in (40,41,42,43):
                        key=(i,j,loop)
                        if (phase,key) in surf: raise ValueError('duplicate surface')
                        surf[phase,key]=bits(v).copy()
                    if phase in (46,47):
                        key=(i,j,loop)
                        if (phase,key) in executed: raise ValueError('duplicate executed rain update')
                        executed[phase,key]=v.astype(np.float32)
                    if phase in face: face[phase]+=1
    expected={(i,j,k) for i,j in cells for k in range(1,40)}
    if actual != expected: raise ValueError(f'coverage differs {len(actual)} != {len(expected)}')
    for i,j,k in expected:
        for loop in range(1,expected_loops+1):
            for p in (30,32,33,34):
                if (p,(i,j,k,loop)) not in state: raise ValueError('missing state')
        if expected_loops == 2 and not np.array_equal(state[34,(i,j,k,1)],state[30,(i,j,k,2)]): raise ValueError('state carry bit mismatch')
    updates=0
    for i,j in cells:
        before=surf[41,(i,j,0)]
        if before[1] != bits(np.float32(0)): raise ValueError('rainncv reset mismatch')
        for loop in range(1,expected_loops+1):
            start=surf[42,(i,j,loop)]; end=surf[43,(i,j,loop)]
            if loop==1 and not np.array_equal(start,before): raise ValueError('reset boundary mismatch')
            if loop>1 and not np.array_equal(start,surf[43,(i,j,loop-1)]): raise ValueError('surface carry bit mismatch')
            key=(i,j,loop); pre=executed.get((46,key)); post=executed.get((47,key))
            if (pre is None)!=(post is None): raise ValueError('unpaired rain update')
            if pre is None:
                if not np.array_equal(start,end): raise ValueError('unrecorded rain update')
            else:
                if not np.array_equal(bits(pre[-2:]),start) or not np.array_equal(bits(post[-2:]),end): raise ValueError('rain boundary mismatch')
                # Fortran evaluates the source increment in REAL32 in written order.
                x=np.float32(pre[4]*pre[7]); x=np.float32(x/pre[8]); x=np.float32(x*pre[9]); x=np.float32(x*np.float32(1000.))
                calculated=np.array([np.float32(pre[-2]+x),np.float32(pre[-1]+x)],dtype=np.float32)
                if not np.array_equal(bits(calculated),bits(post[-2:])): raise ValueError('source precipitation update mismatch')
                updates+=1
    if not all(face.values()): raise ValueError('missing native REAL64 faces')
    result={'status':'PASS','steps':[1],'columns':len(cells),'levels':39,'loops':expected_loops,'dtcld_seconds':20/expected_loops,'carry_bitwise_levels':len(expected) if expected_loops==2 else None,'source_ordered_float32_updates':updates,'real64_face_records':face,'rainncv_reset_and_loop_boundaries':'bitwise exact','missing_conditional_update':'not treated as zero'}
    (folder/'probe_validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
if __name__=='__main__':main()
