#!/usr/bin/env python3
"""Run reviewed reduced operator cases and publish exact REAL32 result words."""
import csv
import hashlib
import json
import math
import re
import struct
import subprocess
from pathlib import Path

here = Path(__file__).resolve().parent
out = here / 'results'
out.mkdir(exist_ok=True)
cases = [('synthetic', None), ('control_nonbinding', 'control_sample'),
         ('mp10_nonbinding', 'mp10_sample'), ('mp10_binding', 'binding_input')]
variants = {1: '20_once', 2: '10_eachfloor', 3: '10_endonly'}
fields = ('NC', 'NN', 'QV', 'QC', 'T')
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
rows, receipts = [], {}
for label, filename in cases:
    args = ['bash', str(here / 'run.sh')]
    if filename:
        args.append(str(here / (filename + '.txt')))
    text = subprocess.run(args, check=True, text=True, capture_output=True).stdout
    (out / (label + '.log')).write_text(text)
    if filename and 'captured activation post-state bitwise match: PASS' not in text:
        raise ValueError(f'{label}: missing native bitwise check')
    matches = re.findall(r'method=(\d) NC NN QV QC T raw32=\s*((?:[0-9A-F]{8}\s*){5})', text)
    if [int(x[0]) for x in matches] != [1, 2, 3]: raise ValueError('missing method bits')
    for method, payload in matches:
        bits = payload.split()
        values = [struct.unpack('>f', bytes.fromhex(x))[0] for x in bits]
        if not all(map(math.isfinite, values)): raise ValueError('nonfinite output')
        row = {'input': label, 'variant': variants[int(method)]}
        for name, value, word in zip(fields, values, bits):
            row[name] = repr(value)
            row[name + '_bits'] = word.lower()
        rows.append(row)
    receipts[label] = {'native_post_match': True if filename else None,
                       'capture_receipt': json.loads((here / (filename + '.json')).read_text()) if filename else None,
                       'log_sha256': sha(out / (label + '.log'))}
columns = ['input', 'variant'] + [entry for name in fields for entry in (name, name + '_bits')]
with (out / 'comparisons.csv').open('w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=columns, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
receipt = {'status': 'PASS', 'scope': 'reduced frozen-input activation plus NN floor, not full KDM6',
           'float_type': 'native REAL32; values decoded exactly from raw output bits',
           'units': {'NC': 'm-3', 'NN': 'm-3', 'QV': 'kg kg-1', 'QC': 'kg kg-1', 'T': 'K'},
           'row_count': len(rows), 'comparisons_sha256': sha(out / 'comparisons.csv'),
           'inputs': receipts, 'driver_sha256': sha(here / 'driver.f90'),
           'extractor_sha256': sha(here / 'prepare.py'), 'runner_sha256': sha(here / 'run.sh')}
(out / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
print('published', len(rows), 'finite rows, SHA256', receipt['comparisons_sha256'])
