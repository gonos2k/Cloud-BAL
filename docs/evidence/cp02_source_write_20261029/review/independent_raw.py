#!/usr/bin/env python3
"""Independently decode the six raw GDB events; argument is capture root."""
import glob, gzip, json, struct, sys
from pathlib import Path

def f32(x):
    return struct.unpack('<f', struct.pack('<f', x))[0]

def raw(value):
    return struct.unpack('<f', bytes.fromhex(value['raw_hex']))[0]

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / 'captures'
rows = []
for arm in ('OFF', 'HYDRO', 'LIQUID'):
    for rank, target in ((1, 'P05_00'), (3, 'P01_00')):
        path, = glob.glob(str(root / arm / ('raw_*rank%d_*.json.gz' % rank)))
        with gzip.open(path, 'rt') as handle:
            data = json.load(handle)
        events = [e for e in data['source_events'] if e['target'] == target]
        by_role = {e['role']: e for e in events if e['role'] != 'watch_access'}
        before = by_role['before_upstream_2cf']
        frame = by_role['after_frame_store_2fb']
        minimum = by_role['before_min_29d']
        written = by_role['writer_after_2a8']
        a = raw(before['operands']['array_0x120'])
        b = raw(before['operands']['array_0xb0'])
        floor = raw(before['scalar_registers']['xmm9'])
        dt = raw(before['operands']['frame_0x140'])
        divisor = raw(before['operands']['constant_34bbaf4'])
        computed_frame = f32(f32(max(a, floor) - b) / dt)
        bound = f32(computed_frame / divisor)
        candidate = raw(minimum['scalar_registers']['xmm0'])
        recorded_bound = raw(minimum['scalar_registers']['xmm1'])
        observed = raw(written['source'])
        assert computed_frame == raw(frame['operands']['frame_0x18'])
        assert bound == recorded_bound == observed
        assert minimum['scalar_registers']['xmm0']['raw_hex'] == '00000080'
        assert candidate == 0.0 and bound < candidate
        assert before['operands']['array_0x120']['address_hex'] == before['values']['q']['address_hex']
        accesses = [(e['event_ordinal'], e['pc_after_write_hex']) for e in events if e['role'] == 'watch_access']
        prior = [x for x in accesses if x[0] <= next(x[0] for x in accesses if x[1] == '0x25f4498')]
        assert [pc for _, pc in prior] == ['0x25ef2ae', '0x25f4498']
        rows.append(dict(arm=arm,target=target,q=a,other=b,floor=floor,dt=dt,divisor=divisor,frame=computed_frame,candidate=candidate,bound=bound,watch_before_load=prior))
print(json.dumps(rows, indent=2))
