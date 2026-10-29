#!/usr/bin/env python3
"""Check accepted raw records, argument slots and six store-register reconstructions."""
import gzip
import hashlib
import json
from pathlib import Path
import re
import struct

root = Path(__file__).resolve().parents[4]
captures = root / 'docs/evidence/cp02_thermo_response_20261029/captures'

def f32(x):
    return struct.unpack('<f', struct.pack('<f', x))[0]

def reg(record, n):
    m = re.search(r'^zmm' + str(n) + r'\s+.*?v16_float = \{(0x[0-9a-f]+)', record, re.M)
    if not m:
        raise ValueError(f'missing zmm{n}')
    bits = int(m.group(1), 16)
    return struct.unpack('<f', struct.pack('<I', bits))[0], f'{bits:08x}'

entries, stores = [], []
for arm in ('OFF', 'HYDRO', 'LIQUID'):
    for rank in (1, 3):
        paths = list((captures / arm).glob(f'*rank{rank}_pid*.json.gz'))
        assert len(paths) == 1
        path = paths[0]
        data = json.loads(gzip.decompress(path.read_bytes()))
        assert data['status'] == 'all_ranks_settled' and data['arm'] == arm and int(data['rank']) == rank
        for item in data['inner']:
            pointers = item['argument_pointers_hex']
            nulls = [i for i, p in enumerate(pointers, 1) if int(p, 16) == 0]
            assert pointers[31] == '0x27' and nulls == [39, 40, 41, 42, 43, 44]
            provenance = item['current_j_provenance']
            delta = int(provenance['inner_q_pointer_hex'], 16) - int(provenance['outer_q_base_pointer_hex'], 16)
            bounds = data['outer']['entry']['memory_bounds']
            stride = 4 * (bounds['ime'] - bounds['ims'] + 1) * (bounds['kme'] - bounds['kms'] + 1)
            assert provenance['outer_q_base_pointer_hex'] == data['outer']['entry']['arguments'][1]['pointer_hex']
            assert delta == provenance['byte_delta'] and stride == provenance['row_stride_bytes'] and delta % stride == 0
            assert bounds['jms'] + delta // stride == provenance['derived_current_j']
            entries.append({'arm': arm, 'rank': rank, 'j': provenance['derived_current_j'], 'argument_32_raw': pointers[31], 'null_slots': nulls, 'q_slice_byte_delta': delta, 'row_stride_bytes': provenance['row_stride_bytes']})
        events = [e for e in data['write_events'] if e['pc_after_write_hex'] == '0x25f4e5e']
        assert len(events) == 1
        event = events[0]
        registers = event['registers_at_watchpoint']
        values = {str(n): reg(registers, n) for n in (2, 6, 10, 15)}
        assert values['10'][0] == 0 and values['15'][0] == 20
        before = struct.unpack('<f', bytes.fromhex(event['raw_before_hex']))[0]
        after = struct.unpack('<f', bytes.fromhex(event['raw_after_hex']))[0]
        increment = f32(values['6'][0] * values['15'][0])
        assert increment == values['2'][0]
        unclamped = f32(before + increment)
        assert max(unclamped, 0.0) == after
        stores.append({'arm': arm, 'rank': rank, 'target': 'P05_00' if rank == 1 else 'P01_00', 'capture': str(path.relative_to(root)), 'capture_sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'before': before, 'xmm6': values['6'][0], 'xmm6_bits': values['6'][1], 'xmm10_bits': values['10'][1], 'xmm15_at_store': values['15'][0], 'xmm2_bits': values['2'][1], 'f32_xmm6_times_20': increment, 'reconstructed_preclamp_f32': unclamped, 'observed_after': after})
assert len(entries) == 12 and len(stores) == 6
print(json.dumps({'scope': 'accepted selected records; REAL32 reconstruction of six watched stores', 'entries': entries, 'stores': stores}, indent=2))
