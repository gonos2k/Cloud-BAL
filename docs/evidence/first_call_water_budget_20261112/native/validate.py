#!/usr/bin/env python3
"""Verify the sealed row's identity and entry/return coverage."""
import collections
import gzip
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
receipt = json.loads((HERE / 'receipt.json').read_text())
capture = HERE / 'capturedsmallrecords/rank3.jsonl.gz'
with capture.open('rb') as stream:
    assert hashlib.file_digest(stream, 'sha256').hexdigest() == receipt['capture_sha256']
seen = collections.defaultdict(set)
with gzip.open(capture, 'rt') as stream:
    for line in stream:
        record = json.loads(line)
        assert record['bounds'] == receipt['bounds'] and record['step'] == 1
        cell = tuple(record['cell'])
        assert cell not in seen[record['event']]
        seen[record['event']].add(cell)
        assert sorted(record['fields']) == receipt['fields']
        for value in record['fields'].values():
            assert len(bytes.fromhex(value['hex_le'])) == 4
bounds = receipt['bounds']
expected = {(i, 72, k) for i in range(bounds['its'], min(bounds['ite'], bounds['ide'] - 1) + 1)
            for k in range(bounds['kts'], bounds['kte'] + 1)}
assert seen['entry'] == seen['return'] == expected
print(f'PASS: {len(expected)} cells at entry and return; capture SHA256 matches')
