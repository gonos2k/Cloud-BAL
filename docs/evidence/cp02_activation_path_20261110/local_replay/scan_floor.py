#!/usr/bin/env python3
"""Scan complete capture streams for the first prespecified floor-binding pair."""
import hashlib
import json
import sys
from pathlib import Path
import numpy as np

here = Path(__file__).resolve().parent
native = here.parent / 'native'
sys.path.insert(0, str(native / 'runs'))
from read_frames import frames

schema_path = native / 'schema/schema.json'
schema = json.loads(schema_path.read_text())
counts = {int(k): len(v['fields']) for k, v in schema['phases'].items()}
override = schema['arm_overrides']['CONTROL and MP10']
counts[10] = len(override['phase_10_fields'])
for phase in override['absent_phases']:
    counts.pop(phase, None)
names = schema['phases']['35']['fields']
def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()
def encode(values):
    x = np.asarray(values, dtype=np.float32)
    return {'values': dict(zip(names, map(float, x))),
            'uint32_bits': {n: f'{int(v):08x}' for n, v in zip(names, x.view(np.uint32))}}

repo = Path(sys.argv[1]).resolve()
output = Path(sys.argv[2])
results = []
summary = {'selection': 'MP10 loop 1 preferred, then step/i/j/k/loop/rank/call, positive sw and actual NN decrease with post NN < 1e8',
           'inputs': [], 'pairs': 0, 'eligible': 0}
for arm in ('MP10', 'CONTROL'):
    folder = repo / 'scratch/b1_activation_path_20261110/runtime/probe' / arm
    paths = sorted(folder.glob('cp04_t*_rank*.bin'))
    if not paths:
        raise ValueError(f'no complete probe files for {arm}')
    for path in paths:
        summary['inputs'].append({'arm': arm, 'path': str(path.relative_to(repo)), 'sha256': sha(path)})
        for head, records in frames(path, counts):
            rank, call, step, j, *_ = head
            pre, post = {}, {}
            for phase, i, k, loop, loops, sub, mstep, values in records:
                key = (i, k, loop, loops, sub, mstep)
                if phase == 35:
                    if key in pre: raise ValueError('duplicate preactivation record')
                    pre[key] = values
                elif phase == 36:
                    if key in post: raise ValueError('duplicate postactivation record')
                    post[key] = values
            if pre.keys() != post.keys(): raise ValueError('activation record keys differ')
            summary['pairs'] += len(pre)
            for key, a in pre.items():
                b = post[key]
                if not (a[0] > 0 and b[2] < a[2] and b[2] < 1.e8): continue
                summary['eligible'] += 1
                i, k, loop, loops, sub, mstep = key
                choice = (0 if arm == 'MP10' and loop == 1 else 1, step, i, j, k, loop, rank, call, arm)
                sample = {'status': 'PASS', 'source': str(path.relative_to(repo)), 'source_sha256': sha(path),
                          'schema_sha256': sha(schema_path), 'step': step, 'rank': rank, 'call': call,
                          'i': i, 'j': j, 'k': k, 'loop': loop, 'loops': loops, 'substep': sub, 'mstep': mstep,
                          'phase35': encode(a), 'phase36': encode(b)}
                results.append((choice, arm, sample))
summary['status'] = 'MATCH' if results else 'NO_MATCH'
if results:
    _, arm, sample = min(results, key=lambda x: x[0])
    summary['selected_arm'] = arm
    summary['selected_sample'] = sample
output.write_text(json.dumps(summary, indent=2, allow_nan=False) + '\n')
print(json.dumps({k: v for k, v in summary.items() if k != 'selected_sample'}, indent=2))
