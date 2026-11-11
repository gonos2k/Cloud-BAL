#!/usr/bin/env python3
"""Recount the captured first-preparation density relation in five cells."""
import hashlib
import json
from pathlib import Path
import struct
import numpy as np

BUNDLE=Path(__file__).resolve().parents[1]
HOST=Path('/var/tmp/firsthour-runtime-plan-20261030/experiment/host')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    paths=sorted((BUNDLE/'native/capturedsmallrecords').glob('rank*.jsonl'))
    rows=[json.loads(line) for path in paths for line in path.read_text().splitlines()]
    result=[]
    for cell in sorted({tuple(row['cell']) for row in rows}):
        records=[row for row in rows if row['cell']==list(cell)]
        before=next(row for row in records if row['kind']=='prep' and row['event']=='entry')
        after=next(row for row in records if row['kind']=='prep' and row['event']=='return')
        kdm=next(row for row in records if row['kind']=='kdm' and row['event']=='entry')
        al,alb=(before['fields'][name]['value'] for name in ('al','alb'))
        den=np.float32(1)/np.float32(np.float32(al)+np.float32(alb))
        word=struct.pack('<f',den).hex()
        assert word==after['fields']['rho']['hex_le']==kdm['fields']['den']['hex_le']
        result.append({'cell':cell,'al':al,'alb':alb,'density':float(den),'density_hex_le':word})
    source=HOST/'dyn_em/module_big_step_utilities_em.f90'
    lines=source.read_text().splitlines()
    assert 'SUBROUTINE moist_physics_prep_em' in lines[5262]
    assert 'rho(i,k,j)  = 1./(al(i,k,j)+alb(i,k,j))' in lines[5397]
    data={'status':'PASS','cells':result,'exact_word_relations':5,
          'sources_sha256':{str(p):sha(p) for p in [*paths,source,HOST/'Registry/Registry.EM_COMMON']},
          'source_context':{'routine_line':5263,'density_line':5398,'binary_symbol':'module_big_step_utilities_em_mp_moist_physics_prep_em_',
                            'captured_break_address':'0x2190470'},
          'scope':'The five captured preparation states reproduce the reciprocal relation exactly. This is not file-to-entry equality, all-domain validation or proof of every physical mass-basis convention.'}
    with (BUNDLE/'analysis/density_recount.json').open('x') as stream:
        json.dump(data,stream,indent=2);stream.write('\n')
    print('PASS: five captured density words match preparation AL/ALB and wrapper DEN')


if __name__=='__main__':
    main()
