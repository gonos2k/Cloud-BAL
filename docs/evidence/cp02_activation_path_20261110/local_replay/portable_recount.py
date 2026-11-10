#!/usr/bin/env python3
"""Compare saved probe words with the published MP10 packed forecast records."""
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT/'tools'))
import cp02_mp10_process as prior

HERE = Path(__file__).resolve().parent
NATIVE = HERE.parent/'native'


def main():
    proof_path = NATIVE/'proof/comparability.json'
    schema_path = NATIVE/'schema/schema.json'
    folder = NATIVE/'packed/MP10'
    packing_path = folder/'packing_receipt.json'
    saved_paths = (HERE/'native_floor_proof.json', HERE/'actual_loop2_contrast.json')
    inputs = [prior.identity(p) for p in (proof_path,schema_path,packing_path,*saved_paths,
                                          Path(__file__),Path(prior.__file__))]
    proof, schema = json.loads(proof_path.read_text()), json.loads(schema_path.read_text())
    packing = json.loads(packing_path.read_text())
    if (proof['status'] != 'PASS' or packing['status'] != 'PASS'
            or prior.identity(schema_path)['sha256'] != proof['schema_sha256']
            or prior.identity(packing_path)['sha256'] != proof['arms']['MP10']['packing_receipt_sha256']):
        raise ValueError('published proof binding differs')
    inventory = {r['name']:r for r in packing['outputs']}
    grouped = {}
    for group in ('core','state'):
        names = sorted(n for n in inventory if n.startswith(group+'_000361_') and n.endswith('.npz'))
        if not names:
            raise ValueError('missing packed records')
        for name in names:
            identity = prior.identity(folder/name)
            if (identity['sha256'],identity['size_bytes']) != (inventory[name]['sha256'],inventory[name]['size_bytes']):
                raise ValueError('packed record changed: '+name)
            inputs.append(identity)
        grouped[group] = prior.load_group(folder,names,group,361)
    saved = [json.loads(p.read_text()) for p in saved_paths]
    if any(x['status'] != 'PASS' or x['schema_sha256'] != proof['schema_sha256'] for x in saved):
        raise ValueError('saved probe proof differs')
    expected_key = {'step':361,'rank':3,'call':361,'i':156,'j':86,'k':14,
                    'loops':2,'substep':0,'mstep':0}
    for loop, sample in enumerate(saved,1):
        if sample['key'] != {**expected_key,'loop':loop}:
            raise ValueError('saved probe key differs')
    if saved[0]['source_sha256'] != saved[1]['source_sha256']:
        raise ValueError('saved probe sources differ')
    cases = [(1,phase,saved[0]['phases'][str(phase)]) for phase in (11,12,33,34,35,36)]
    cases += [(2,phase,saved[1]['phase'+str(phase)]) for phase in (35,36)]
    counts = []
    for loop,phase,expected in cases:
        keys,bits = grouped['core' if phase in (11,12) else 'state']
        key = np.array([361,3,361,86,156,14,loop,2,0,0,phase],dtype=np.int32)
        matches = np.flatnonzero(np.all(keys[:,:11] == key,axis=1))
        if len(matches) != 1:
            raise ValueError(f'missing or duplicate native key: loop={loop}, phase={phase}')
        index = matches[0]
        fields = schema['phases'][str(phase)]['fields']
        if keys[index,11] != len(fields) or set(fields) != set(expected['uint32_bits']):
            raise ValueError('phase field schema differs')
        actual = bits[index,:len(fields)]
        if any(int(actual[i]) != int(expected['uint32_bits'][name],16) for i,name in enumerate(fields)):
            raise ValueError(f'probe/forecast word differs: loop={loop}, phase={phase}')
        counts.append({'loop':loop,'phase':phase,'words':len(fields)})
    if sum(x['words'] for x in counts if x['loop']==1) != 86 or sum(x['words'] for x in counts if x['loop']==2) != 24:
        raise ValueError('unexpected word coverage')
    for item in inputs:
        if prior.identity(item['path']) != item:
            raise ValueError('input changed during recount')
    result = {'status':'PASS','comparison':'saved probe words versus published MP10 packed forecast',
              'native_key':{'step':361,'rank':3,'call':361,'i':156,'j':86,'k':14,'loops':2},
              'loop1_words':86,'loop2_words':24,'phases':counts,'inputs':inputs,
              'scope':'Exact IEEE REAL32 bit equality at the one selected native cell; no forecast skill inference.'}
    with (HERE/'portable_recount_receipt.json').open('x') as stream:
        json.dump(result,stream,indent=2)
        stream.write('\n')
    print('PASS: 86 loop-1 and 24 loop-2 words match published packed records')


if __name__ == '__main__':
    main()
