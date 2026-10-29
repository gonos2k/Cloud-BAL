#!/usr/bin/env python3
"""Independently recompute captured operations from raw IEEE bytes."""
import argparse
import gzip
import hashlib
import json
import math
import struct
from pathlib import Path

import numpy as np


def unpack(record, bits):
    return struct.unpack('<f' if bits == 32 else '<d', bytes.fromhex(record))[0]


def packed(value, bits):
    return struct.pack('<f' if bits == 32 else '<d', value).hex()


def review(path):
    raw = path.read_bytes()
    data = json.loads(gzip.decompress(raw) if path.suffix == '.gz' else raw)
    events = {e['role']: e for e in data['candidate_events']}
    if not events:
        return None
    expected = ['before_array_load', 'before_subtract', 'before_convert_to_double',
                'before_double_multiply', 'before_product', 'before_divide',
                'before_convert_to_single', 'before_single_multiply', 'before_compare', 'before_branch']
    assert list(events) == expected
    assert len({(e['frame_rbx_hex'], e['index_r15'], e['selected_inner_id'], e['target']) for e in events.values()}) == 1
    assert all(events[a]['callback_ordinal'] < events[b]['callback_ordinal'] for a, b in zip(expected, expected[1:]))
    assert all((e['mxcsr'] & 0xe040) == 0 for e in events.values()), 'Requires nearest rounding, FTZ and DAZ disabled'
    first = events['before_array_load']['operands']
    op = lambda n, b: unpack(first[n]['raw_hex'], b)
    reg = lambda role, n, b: unpack(events[role]['scalar_registers'][n][f'raw_hex{b}'], b)
    same = lambda value, role, n, b: packed(value, b) == events[role]['scalar_registers'][n][f'raw_hex{b}']
    difference = np.float32(np.float32(op('array_0x1b8', 32)) - np.float32(op('constant_34b9028', 32)))
    assert same(difference, 'before_convert_to_double', 'xmm2', 32)
    assert same(float(difference), 'before_double_multiply', 'xmm2', 64)
    factor = float(difference) * op('array_0xe8', 64)
    assert same(factor, 'before_product', 'xmm2', 64)
    product = reg('before_product', 'xmm4', 64) * factor
    assert same(product, 'before_divide', 'xmm4', 64)
    quotient = product / op('array_0x160', 64)
    assert same(quotient, 'before_convert_to_single', 'xmm4', 64)
    converted = np.float32(quotient)
    assert same(converted, 'before_single_multiply', 'xmm0', 32)
    candidate = np.float32(converted * np.float32(op('constant_34b9028', 32)))
    assert same(candidate, 'before_compare', 'xmm0', 32)
    assert math.isfinite(candidate) and candidate == 0 and math.copysign(1, candidate) < 0
    frame = op('frame_0x18', 32)
    min_operand = np.float32(np.float32(frame) / np.float32(op('constant_34bbaf4', 32)))
    assert min_operand < 0
    negative_bound = np.float32(-np.float32(np.float32(op('frame_0x50', 32)) / np.float32(op('frame_0x140', 32))))
    counterfactual = max(float(np.float32(-1.e-12)), float(negative_bound), float(min_operand))
    b = data['b_events']
    named = {e['role']: e for e in b if e['role'] != 'watch_access'}
    bm, bd, bf, bs = (named[x] for x in ('before_b_min', 'before_b_divide', 'before_b_floor', 'before_b_store'))
    read32 = lambda obj: np.float32(unpack(obj['raw_hex'], 32))
    xr = lambda event, n: read32(event['scalar_registers'][n])
    cap = np.float32(read32(bm['operands']['array_0x30']) * read32(bm['operands']['constant_34c0e5c']))
    assert packed(cap, 32) == bm['scalar_registers']['xmm1']['raw_hex']
    limited = min(xr(bm, 'xmm0'), cap)
    assert packed(limited, 32) == bm['scalar_registers']['xmm0']['raw_hex']
    numerator = np.float32(read32(bm['operands']['frame_0x470']) * limited)
    denominator = np.float32(read32(bm['operands']['array_0x30']) - limited)
    assert packed(numerator, 32) == bd['scalar_registers']['xmm1']['raw_hex']
    assert packed(denominator, 32) == bd['scalar_registers']['xmm2']['raw_hex']
    quotient_b = np.float32(numerator / denominator)
    assert packed(quotient_b, 32) == bf['scalar_registers']['xmm1']['raw_hex']
    bounded_b = max(quotient_b, read32(bm['operands']['frame_0x1d0']))
    assert packed(bounded_b, 32) == bs['scalar_registers']['xmm1']['raw_hex']
    watches = [e for e in b if e['role'] == 'watch_access' and e['callback_ordinal'] <= events['before_array_load']['callback_ordinal']]
    assert [e['pc_after_access_hex'] for e in watches] == ['0x25e5c7d', '0x25eed31', '0x25ef2ee']
    assert all(e['address_hex'] == bs['address_hex'] == first['array_0xb0']['address_hex'] for e in watches)
    assert watches[0]['after']['raw_hex'] == packed(bounded_b, 32) == first['array_0xb0']['raw_hex']
    assert all(e['after']['raw_hex'] == packed(bounded_b, 32) for e in watches)
    return {'file': str(path), 'sha256': hashlib.sha256(raw).hexdigest(), 'arm': data['arm'], 'rank': data['rank'], 'target': events['before_compare']['target'], 'B': float(bounded_b), 'B_raw': packed(bounded_b, 32), 'B_previous_raw': watches[0]['before']['raw_hex'], 'difference': float(difference), 'weight': op('array_0xe8', 64), 'weight_raw': first['array_0xe8']['raw_hex'], 'candidate_raw': packed(candidate, 32), 'mxcsr': events['before_compare']['mxcsr'], 'min_operand': float(min_operand), 'max_first_bound': float(negative_bound), 'counterfactual_candidate': float(np.float32(-1.e-12)), 'counterfactual_result': counterfactual}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('paths', nargs='+', type=Path)
    args = parser.parse_args()
    rows = [r for p in args.paths if (r := review(p)) is not None]
    print(json.dumps({'status': 'PASS', 'cases': rows}, indent=2))


if __name__ == '__main__':
    main()
