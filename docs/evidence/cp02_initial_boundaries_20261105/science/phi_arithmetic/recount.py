#!/usr/bin/env python3
"""Replay two float32 expression orders using the observed phi call inputs."""
import hashlib
import json
import struct
import sys
from pathlib import Path
import numpy as np

source=Path(sys.argv[1]); output=Path(sys.argv[2])
if hashlib.sha256(source.read_bytes()).hexdigest()!='47bd19bf23651971ed63f27f13a4a9b8553f7d366771134d7811bcaee794dcc4':raise ValueError('input hash differs')
data=json.loads(source.read_text()); rows={}
for arm in ('B1','DM065'):
    call=[x for x in data['arms'][arm]['calls'] if x['function']=='phi'][6]
    if (call['kdm_entered'],call['kdm_completed'],call['caller_class'])!=(1,1,'solve_em_RK'):raise ValueError('phi call identity differs')
    words=call['entry_fields_raw']
    f={key:np.float32(struct.unpack('<f',bytes.fromhex(value))[0]) for key,value in words.items()}
    ph,ph_next,phb,phb_next=(f[k] for k in ('ph','ph_next','phb','phb_next'))
    exact=float(ph_next)-float(ph)+float(phb_next)-float(phb)
    source_order=np.float32(np.float32(np.float32(ph_next-ph)+phb_next)-phb)
    grouped=np.float32(np.float32(ph_next-ph)+np.float32(phb_next-phb))
    rows[arm]={'entry_sequence':call['entry_sequence'],'all_input_words':words,'f64_exact_on_captured_f32':exact,
               'source_left_associated_f32':float(source_order),'source_error':float(source_order)-exact,
               'grouped_f32':float(grouped),'grouped_error':float(grouped)-exact}
result={'analysis_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'producer_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'status':'PASS_LOCAL_ARITHMETIC_REPLAY','arms':rows,
        'scope':'Arithmetic on captured input words only; no claim about compiled instruction order, physical truth, model change, or forecast.'}
with output.open('x') as f:json.dump(result,f,indent=2,allow_nan=False);f.write('\n')
