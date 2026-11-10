#!/usr/bin/env python3
"""Bind activation, final condensation and native floor to one raw loop key."""
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
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

sample_path = here / 'binding_sample.json'
sample = json.loads(sample_path.read_text())
schema_path = native / 'schema/schema.json'
schema = json.loads(schema_path.read_text())
repo = Path(sys.argv[1]).resolve()
source = repo / sample['source']
if sha(source) != sample['source_sha256'] or sha(schema_path) != sample['schema_sha256']:
    raise ValueError('source or schema hash mismatch')
counts = {int(k): len(v['fields']) for k, v in schema['phases'].items()}
override = schema['arm_overrides']['CONTROL and MP10']
counts[10] = len(override['phase_10_fields'])
for phase in override['absent_phases']:
    counts.pop(phase, None)
phases = (11, 12, 33, 34, 35, 36)
matched = {}
for head, records in frames(source, counts):
    rank, call, step, j, *_ = head
    if (rank, call, step, j) != tuple(sample[x] for x in ('rank', 'call', 'step', 'j')):
        continue
    for phase, i, k, loop, loops, sub, mstep, values in records:
        if phase not in phases or (i, k, loop, loops, sub, mstep) != tuple(
                sample[x] for x in ('i', 'k', 'loop', 'loops', 'substep', 'mstep')):
            continue
        if phase in matched:
            raise ValueError('duplicate record')
        x = np.asarray(values, dtype=np.float32)
        names = schema['phases'][str(phase)]['fields']
        matched[phase] = {'values': {n: float(v) for n, v in zip(names, x)},
                          'uint32_bits': {n: f'{int(v):08x}' for n, v in zip(names, x.view(np.uint32))}}
if set(matched) != set(phases): raise ValueError('missing phase')
for phase in (35, 36):
    if matched[phase] != sample[f'phase{phase}']: raise ValueError('sample bits do not match source')
pre = matched[33]['values']['nci3']; post = matched[34]['values']['nci3']
if not pre < 1.e8 or post != 1.e8: raise ValueError('native floor did not restore NN')
result = {'status': 'PASS', 'source': sample['source'], 'source_sha256': sha(source),
          'schema_sha256': sha(schema_path), 'sample_sha256': sha(sample_path),
          'key': {k: sample[k] for k in ('step', 'rank', 'call', 'i', 'j', 'k', 'loop', 'loops', 'substep', 'mstep')},
          'native_NN_pre_floor': pre, 'native_NN_post_floor': post,
          'phases': {str(p): matched[p] for p in phases},
          'scope': 'native per-loop state records; phase 33 to 34 includes the PSD block and NN floor'}
(here / 'native_floor_proof.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
print('PASS native floor', pre, '->', post, 'source', result['source_sha256'])
