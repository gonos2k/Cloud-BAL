#!/usr/bin/env python3
"""Check actual optional solid and solid-step counters across inner loops."""
import csv,json,sys
from pathlib import Path
import numpy as np
from read_frames import frames

NATIVE=Path(__file__).resolve().parents[1]
ROOT=Path(__file__).resolve().parents[5]
def main():
    arm=sys.argv[1]; nloops={'CONTROL':1,'MP10':2}[arm];case=ROOT.parent/'runtime/probe'/arm
    schema=json.loads((NATIVE/'schema/schema.json').read_text());counts={int(k):len(v['fields']) for k,v in schema['phases'].items()}
    cells={(int(r['i_fortran']),int(r['j_fortran'])) for r in csv.DictReader((NATIVE.parent/'cohorts/native_columns.csv').open())}
    seen={}
    for path in sorted(case.glob('surface_t*_rank*.bin')):
        for h,records in frames(path,counts):
            rank,call,step,j,*_=h
            for p,i,k,loop,loops,sub,ms,v in records:
                if p not in (51,52,53,60,61,62,63,70,71,72,73):continue
                key=(p,i,j,loop)
                if key in seen:raise ValueError('duplicate record')
                seen[key]=v.astype(np.float32).view(np.uint32)
    for i,j in cells:
        if not np.array_equal(seen[51,i,j,0],np.zeros(2,dtype=np.uint32)):raise ValueError('step solid reset failed')
        for l in range(1,nloops+1):
            for p in (52,53,62,63,72,73):
                if (p,i,j,l) not in seen:raise ValueError('optional solid record missing')
            if l==1 and not np.array_equal(seen[51,i,j,0],seen[52,i,j,1]):raise ValueError('solid reset carry failed')
            if l>1:
                for end,start in ((53,52),(63,62),(73,72)):
                    if not np.array_equal(seen[end,i,j,l-1],seen[start,i,j,l]):raise ValueError('solid carry mismatch')
    result={'status':'PASS','arm':arm,'columns':len(cells),'loops':nloops,'optional_snow_and_graupel_present':True,'step_solid_reset_and_inner_loop_carry':'bitwise equal','interpretation':'snow and graupel overlap total precipitation; do not sum as independent totals'}
    (case/'solid_carry_validation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
