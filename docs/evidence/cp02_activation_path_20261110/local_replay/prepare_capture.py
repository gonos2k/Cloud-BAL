#!/usr/bin/env python3
"""Create round-trip REAL32 driver input from a hash-bound native sample."""
import hashlib
import json
import struct
import sys
from pathlib import Path

sample_path = Path(sys.argv[1]).resolve()
repo_root = Path(sys.argv[2]).resolve()
out = Path(sys.argv[3])
sample = json.loads(sample_path.read_text())
if sample['status'] != 'PASS':
    raise ValueError('native sample did not pass')
source = repo_root / sample['source']
schema = Path(__file__).resolve().parent.parent / 'native/schema/schema.json'
def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
if digest(source) != sample['source_sha256'] or digest(schema) != sample['schema_sha256']:
    raise ValueError('source or schema hash mismatch')
order = ['sw', 'NC', 'NN', 'q', 'qc', 't', 'den', 'xl', 'cpm', 'pi', 'denr', 'dtcld']
post_order = ['NC', 'NN', 'q', 'qc', 't']
def encode(phase, name):
    section = sample[phase]
    word = int(section['uint32_bits'][name], 16)
    value = struct.unpack('>f', struct.pack('>I', word))[0]
    if struct.pack('>f', section['values'][name]) != struct.pack('>I', word):
        raise ValueError(f'{phase} {name}: sample value and bits differ')
    text = format(value, '.9g')
    if struct.pack('>f', float(text)) != struct.pack('>I', word):
        raise ValueError(f'{phase} {name}: decimal does not round-trip')
    return text
payload = ' '.join(encode('phase35', x) for x in order) + '\n'
payload += ' '.join(encode('phase36', x) for x in post_order) + '\n'
out.write_text(payload)
receipt = {'status': 'PASS', 'sample_sha256': digest(sample_path), 'raw_source_sha256': digest(source),
           'schema_sha256': digest(schema), 'input_sha256': digest(out),
           'key': {x: sample[x] for x in ('step', 'rank', 'call', 'i', 'j', 'k', 'loop', 'loops', 'substep', 'mstep')},
           'verified': 'all 17 serialized values round-trip to the sample REAL32 words'}
out.with_suffix('.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt, indent=2))
