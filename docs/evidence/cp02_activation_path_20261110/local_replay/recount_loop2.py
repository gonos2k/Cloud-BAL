#!/usr/bin/env python3
"""Record actual loop-2 activation state at the selected native point."""
import hashlib
import json
import sys
from pathlib import Path
import numpy as np

here = Path(__file__).resolve().parent
native = here.parent / 'native'
sys.path.insert(0, str(native / 'runs'))
from read_frames import frames

def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

sample_path = here / 'binding_sample.json'
sample = json.loads(sample_path.read_text())
schema_path = native / 'schema/schema.json'
schema = json.loads(schema_path.read_text())
source = Path(sys.argv[1]).resolve() / sample['source']
if sha(source) != sample['source_sha256'] or sha(schema_path) != sample['schema_sha256']:
    raise ValueError('source or schema hash differs from selected loop 1')
counts = {int(k): len(v['fields']) for k, v in schema['phases'].items()}
override = schema['arm_overrides']['CONTROL and MP10']
counts[10] = len(override['phase_10_fields'])
for phase in override['absent_phases']:
    counts.pop(phase, None)
found = {}
for head, records in frames(source, counts):
    rank, call, step, j, *_ = head
    if (rank, call, step, j) != tuple(sample[x] for x in ('rank', 'call', 'step', 'j')):
        continue
    for phase, i, k, loop, loops, substep, mstep, values in records:
        if phase not in (35, 36) or (i, k, loop, loops, substep, mstep) != (
                sample['i'], sample['k'], 2, sample['loops'], sample['substep'], sample['mstep']):
            continue
        if phase in found:
            raise ValueError('duplicate loop 2 record')
        array = np.asarray(values, dtype=np.float32)
        names = schema['phases'][str(phase)]['fields']
        found[phase] = {'values': {n: float(v) for n, v in zip(names, array)},
                        'uint32_bits': {n: f'{int(v):08x}' for n, v in zip(names, array.view(np.uint32))}}
if set(found) != {35, 36}: raise ValueError('missing actual loop 2 phase')
if found[35]['values']['sw'] >= 0 or found[35]['uint32_bits']['NN'] != found[36]['uint32_bits']['NN']:
    raise ValueError('actual loop 2 activation conditions differ')
result = {'status': 'PASS', 'source': sample['source'], 'source_sha256': sha(source),
          'schema_sha256': sha(schema_path), 'loop1_sample_sha256': sha(sample_path),
          'key': {**{k: sample[k] for k in ('step', 'rank', 'call', 'i', 'j', 'k', 'loops', 'substep', 'mstep')}, 'loop': 2},
          'phase35': found[35], 'phase36': found[36],
          'actual_activation_NN_consumed_m-3': found[35]['values']['NN'] - found[36]['values']['NN'],
          'scope': 'actual loop 2 state and activation; compare separately with frozen-input reduced operator, not identical inputs'}
(here / 'actual_loop2_contrast.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
print('PASS actual loop 2 sw, NN before/after:', found[35]['values']['sw'], found[35]['values']['NN'], found[36]['values']['NN'])
