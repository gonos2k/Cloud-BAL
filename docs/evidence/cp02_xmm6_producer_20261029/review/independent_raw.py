#!/usr/bin/env python3
"""Independently decode the six saved producer-to-sum observations."""
import glob
import gzip
import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
CAPTURES = ROOT / 'docs/evidence/cp02_xmm6_producer_20261029/captures'

def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]

def decode(raw):
    return struct.unpack('<f', bytes.fromhex(raw))[0]

def lane(event, name):
    return decode(event['scalar_registers'][name]['raw_hex'])

rows = []
for path in sorted(CAPTURES.glob('*/raw_*rank[13]_*.json.gz')):
    with gzip.open(path, 'rt') as stream:
        record = json.load(stream)
    events = {event['role']: event for event in record['producer_events']}
    load, loaded, compare, onward = (events[x] for x in ('before_load', 'after_load', 'before_compare', 'path_to_sum'))
    before_sum = next(e for e in record['preclamp_events'] if e['role'] == 'before_sum')
    frame = bytes.fromhex(load['frame_rbx_raw_hex'])
    index = load['index_r8']
    assert int(load['source']['address_hex'], 16) == struct.unpack_from('<Q', frame, 0xc0)[0] + 4 * index
    assert int(load['qrs_address_hex'], 16) == struct.unpack_from('<Q', frame, 0x18)[0] + 4 * index
    source = decode(load['source']['raw_hex'])
    assert load['source']['raw_hex'] == loaded['scalar_registers']['xmm6']['raw_hex']
    lhs, rhs = lane(compare, 'xmm4'), lane(compare, 'xmm3')
    scale = decode(loaded['frame_scale_0x140']['raw_hex'])
    assert scale == 20.0 and f32(f32(lane(loaded, 'xmm4') - source) * scale) == lhs
    if lhs > rhs:
        factor = lane(events['before_multiply'], 'xmm3')
        assert factor == f32(rhs / lhs)
        result = f32(source * factor)
        assert result == lane(events['after_multiply'], 'xmm6')
        branch = 'multiply'
    else:
        assert 'before_multiply' not in events and 'after_multiply' not in events
        result, branch = source, 'skip'
    assert result == lane(onward, 'xmm6') == lane(before_sum, 'xmm6')
    assert load['qrs_address_hex'] == before_sum['qrs_address_hex']
    rows.append({'arm': record['arm'], 'rank': str(record['rank']), 'source': source,
                 'compare_xmm4': lhs, 'compare_xmm3': rhs, 'branch': branch, 'xmm6': result})
assert {(r['arm'], r['rank']) for r in rows} == {(a, r) for a in ('OFF', 'HYDRO', 'LIQUID') for r in ('1', '3')}
print(json.dumps(rows, indent=2))
