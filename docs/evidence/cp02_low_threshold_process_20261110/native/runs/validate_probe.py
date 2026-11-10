#!/usr/bin/env python3
"""Validate three-step owner, frame, phase, substep and REAL64 payload coverage."""
import csv
import importlib.util
import json
from pathlib import Path
import sys
import numpy as np
from read_frames import frames

NATIVE=Path(__file__).resolve().parents[1]
ROOT=Path(__file__).resolve().parents[5]


def main():
    arm, folder = sys.argv[1], Path(sys.argv[2])
    if arm not in ('FIX','CONSERVATIVE','ICE_FIXED'): raise ValueError('invalid arm')
    rows=list(csv.DictReader((NATIVE/'source/columns.csv').open()))
    cells=[(int(r['wrf_i_1based']),int(r['wrf_j_1based'])) for r in rows]; cellset=set(cells)
    old=ROOT/'docs/evidence/cp02_protected_process_20261106/native/provenance/collector_v5/cp02_protected_process_capture.py'
    spec=importlib.util.spec_from_file_location('prior_capture',old); prior=importlib.util.module_from_spec(spec);sys.modules[spec.name]=prior;spec.loader.exec_module(prior)
    inventory=prior.read_call_inventory(folder.glob('state_calls_rank*.txt'),cells,steps=3)
    cohort=prior.Cohort(cells,[],[],np.empty((0,4)),np.empty((0,4)),{})
    entry,_=prior.read_state_chunks(folder.glob('state_selected_entry_t*.bin'),6,cohort,inventory,range(1,4))
    returned,_=prior.read_state_chunks(folder.glob('state_selected_return_t*.bin'),7,cohort,inventory,range(1,4))
    surface=prior.read_surface(folder.glob('surface_cp04_rank*.bin'),cohort,inventory,range(1,4))
    schema=json.loads((NATIVE/'schema/schema.json').read_text()); counts={int(k):len(v['fields']) for k,v in schema['phases'].items()}
    absent=schema['arm_overrides']['FIX']['absent_phases'] if arm=='FIX' else schema['arm_overrides']['CONSERVATIVE and ICE_FIXED']['absent_phases']
    for phase in absent: counts.pop(phase)
    if arm!='FIX': counts[10]=len(schema['arm_overrides']['CONSERVATIVE and ICE_FIXED']['phase_10_fields'])
    mandatory=(1,2,3,4,5,6,7,8,11,12)
    seen={p:set() for p in mandatory}; framekeys=set(); pair_count={9:0,20:0}; face_count={18:0,22:0,23:0}
    for path in sorted(folder.glob('cp04_t*.bin')):
        for header, records in frames(path,counts):
            rank,call,step,j,its,ite,kts,kte=header
            if step not in (1,2,3) or (step,rank,call) not in inventory.calls: raise ValueError('frame has unknown call')
            i1,i2,j1,j2,k1,k2=inventory.calls[(step,rank,call)]
            if (its,ite,kts,kte)!=(i1,i2,k1,k2) or not j1<=j<=j2: raise ValueError('frame bounds differ from inventory')
            fk=(step,rank,call,j)
            if fk in framekeys: raise ValueError('duplicate frame')
            framekeys.add(fk); local={}
            for phase,i,k,loop,loops,sub,mstep,values in records:
                if (i,j) not in cellset or not its<=i<=ite or not kts<=k<=kte: raise ValueError('record outside selected owner')
                key=(i,k,loop,sub,mstep)
                if (phase,key) in local: raise ValueError('duplicate process record')
                local[(phase,key)]=values
                if phase in mandatory:
                    index=(step,i,j,k)
                    if index in seen[phase]: raise ValueError('duplicate mandatory phase')
                    seen[phase].add(index)
                if phase in face_count: face_count[phase]+=1
            for pre,post in ((9,10),(20,21)):
                a={key for p,key in local if p==pre}; b={key for p,key in local if p==post}
                if a!=b: raise ValueError(f'phase {pre}/{post} substep mismatch')
                for key in a:
                    i,k,loop,sub,mstep=key
                    if not 1<=sub<=mstep: raise ValueError('invalid sediment substep')
                    expected=23 if arm=='FIX' and pre==20 else 18 if pre==9 else 22
                    if arm!='FIX' or pre==20:
                        if (expected,key) not in local: raise ValueError('missing actual transfer record')
                expected_cells={(i,k) for i,cj in cells if cj==j and its<=i<=ite for k in range(kts,kte+1)}
                grouped={}
                for i,k,loop,sub,mstep in a:
                    grouped.setdefault((i,k),set()).add((sub,mstep))
                if set(grouped)!=expected_cells: raise ValueError('missing sediment level/cell coverage')
                for substeps in grouped.values():
                    totals={m for _,m in substeps}
                    if len(totals)!=1 or {n for n,_ in substeps}!=set(range(1,next(iter(totals))+1)):
                        raise ValueError('missing or inconsistent sediment substeps')
                pair_count[pre]+=len(a)
    expected={(step,i,j,k) for step in (1,2,3) for i,j in cells for k in range(1,40)}
    if any(values!=expected for values in seen.values()): raise ValueError('mandatory phase level/cell/step coverage mismatch')
    if not all(pair_count.values()): raise ValueError('no sediment substeps captured')
    if arm!='FIX' and (not face_count[18] or not face_count[22]): raise ValueError('missing REAL64 shared face values')
    if arm=='FIX' and not face_count[23]: raise ValueError('missing legacy ice falk')
    result={'status':'PASS','steps':[1,2,3],'columns':len(cells),'levels':39,'mandatory_counts':{str(p):len(x) for p,x in seen.items()},'paired_substeps':pair_count,'native_faces':face_count,'wrapper_shape':list(entry.shape),'surface_shape':list(surface.shape)}
    with (folder/'probe_validation.json').open('x') as f: json.dump(result,f,indent=2);f.write('\n')


if __name__=='__main__': main()
