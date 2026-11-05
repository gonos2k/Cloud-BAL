#!/usr/bin/env python3
"""Compare two evaluation orders against the exact sum of captured REAL32 terms."""
import csv
from fractions import Fraction
import hashlib
import json
import struct
import sys
from pathlib import Path
import numpy as np

expected={'p20183':'47bd19bf23651971ed63f27f13a4a9b8553f7d366771134d7811bcaee794dcc4',
          'p17051':'699474b149f4fb37bda809194f5f044929fa3741708149458edaeffd52d3b3ef'}
inputs=[Path(sys.argv[1]),Path(sys.argv[2])];directory=Path(sys.argv[3]);directory.mkdir(parents=True,exist_ok=False)
rows=[]
for target,source in zip(expected,inputs):
    if hashlib.sha256(source.read_bytes()).hexdigest()!=expected[target]:raise ValueError('input hash differs')
    data=json.loads(source.read_text())
    if data['target']!=target:raise ValueError('target differs')
    for arm in ('B1','DM065'):
        calls=[x for x in data['arms'][arm]['calls'] if x['function']=='phi']
        if len(calls)!=15:raise ValueError('phi call count differs')
        for number,call in enumerate(calls,1):
            names=('ph','ph_next','phb','phb_next')
            raw={k:call['entry_fields_raw'][k] for k in names}
            f={k:np.float32(struct.unpack('<f',bytes.fromhex(raw[k]))[0]) for k in names}
            ph,upper,base,base_upper=(f[k] for k in names)
            exact=Fraction(float(upper))-Fraction(float(ph))+Fraction(float(base_upper))-Fraction(float(base))
            left=np.float32(np.float32(np.float32(upper-ph)+base_upper)-base)
            grouped=np.float32(np.float32(upper-ph)+np.float32(base_upper-base))
            error_left=abs(Fraction(float(left))-exact);error_group=abs(Fraction(float(grouped))-exact)
            comparison='better' if error_group<error_left else 'worse' if error_group>error_left else 'equal'
            rows.append({'target':target,'arm':arm,'phi_call':number,'entry_sequence':call['entry_sequence'],
                         'kdm_entered':call['kdm_entered'],'kdm_completed':call['kdm_completed'],**{k+'_word':raw[k] for k in names},
                         'exact_fraction':str(exact),'exact_float':float(exact),'source_left_f32':float(left),'grouped_f32':float(grouped),
                         'source_abs_error_fraction':str(error_left),'grouped_abs_error_fraction':str(error_group),
                         'source_abs_error':float(error_left),'grouped_abs_error':float(error_group),'grouped_vs_source':comparison})
if len(rows)!=60:raise ValueError('sample count differs')
with (directory/'rows.csv').open('x',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=rows[0]);writer.writeheader();writer.writerows(rows)
summary={'status':'PASS_60_CAPTURED_PHI_SAMPLES','input_sha256':expected,'producer_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
         'row_count':len(rows),'grouped_better':sum(r['grouped_vs_source']=='better' for r in rows),
         'grouped_equal':sum(r['grouped_vs_source']=='equal' for r in rows),'grouped_worse':sum(r['grouped_vs_source']=='worse' for r in rows),
         'max_source_abs_error':max(r['source_abs_error'] for r in rows),'max_grouped_abs_error':max(r['grouped_abs_error'] for r in rows),
         'rows_sha256':hashlib.sha256((directory/'rows.csv').read_bytes()).hexdigest(),
         'units':'geopotential m2 s-2','scope':'Exact rational sum of captured binary32 terms; source-order and grouped float32 are local arithmetic comparisons only, not a claim about executable instructions, physical truth, or a model change.'}
with (directory/'receipt.json').open('x') as f:json.dump(summary,f,indent=2);f.write('\n')
