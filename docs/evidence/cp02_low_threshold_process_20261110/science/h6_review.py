#!/usr/bin/env python3
"""Recount selected low-FA h6 results and extract a raw representative event."""
import csv
import gzip
import json
from pathlib import Path
import sys

import column_audit as audit

HERE = Path(__file__).resolve().parent
OUT = HERE / 'h6_review'
if OUT.exists():
    raise FileExistsError(OUT)
summary = {}
for arm in audit.ARMS:
    folder = HERE / 'full' / arm
    receipt = json.loads((folder / 'receipt.json').read_text())
    if receipt['status'] != 'PASS' or receipt['outputs']['calls.csv.gz'] != audit.sha(folder / 'calls.csv.gz'):
        raise ValueError('unsealed per-call output')
    if receipt['outputs']['weighted_points.csv.gz'] != audit.sha(folder / 'weighted_points.csv.gz'):
        raise ValueError('unsealed weighted output')
    with gzip.open(folder / 'calls.csv.gz', 'rt', newline='') as f:
        rows = [r for r in csv.DictReader(f) if r['species'] == 'rain' and 901 <= int(r['step']) <= 1080 and r['low_new_fa_corner'] == '1']
    available = [r for r in rows if r['residual_kg_m2'] != '']
    with gzip.open(folder / 'weighted_points.csv.gz', 'rt', newline='') as f:
        weighted = [r for r in csv.DictReader(f) if r['species'] == 'rain' and 901 <= int(r['step']) <= 1080 and r['role'].startswith('new_h6_')]
    entry = {'calls':len(rows), 'surface_available':len(available),
             'min_residual_kg_m2':min(float(r['residual_kg_m2']) for r in available),
             'max_residual_kg_m2':max(float(r['residual_kg_m2']) for r in available),
             'weighted_rows':len(weighted), 'weighted_available':sum(r['residual_kg_m2'] != '' for r in weighted)}
    if arm == 'FIX':
        entry['reconstructed_cap_gap_above_1e-6_calls'] = sum(float(r['legacy_incoming_cap_gap_kg_m2']) > 1e-6 for r in rows)
        entry['worst_event'] = min(available, key=lambda r:float(r['residual_kg_m2']))
    summary[arm] = entry

event = summary['FIX']['worst_event']
receipt_path = HERE / 'full/FIX/receipt.json'
receipt = json.loads(receipt_path.read_text())
rank, step, j, i = (int(event[k]) for k in ('rank','step','j','i'))
records = None
raw_path = None
for name, digest in receipt['inputs'].items():
    path = Path(name)
    if not path.name.startswith('cp04_t') or not path.name.endswith(f'_rank{rank}.bin'):
        continue
    start, end = path.name.split('_')[1][1:].split('-')
    if not int(start) <= step <= int(end):
        continue
    if audit.sha(path) != digest:
        raise ValueError('raw chunk changed')
    for header, frame in audit.frames(path, audit.phase_counts('FIX')):
        if (header[0], header[2], header[3]) == (rank, step, j):
            matches = [r for r in audit.audit_frame('FIX', header, frame) if r['i'] == i and r['species'] == 'rain']
            if len(matches) != 1 or abs(matches[0]['residual_kg_m2'] - float(event['residual_kg_m2'])) > 1e-15:
                raise ValueError('raw event recount differs')
            records = [{'phase':p, 'i':ii, 'k':k, 'loop':loop, 'loops':loops, 'substep':sub, 'mstep':ms,
                        'values':[float(x) for x in v]} for p,ii,k,loop,loops,sub,ms,v in frame if ii == i and p in (9,10,13,14)]
            raw_path = path
            break
    if records is not None:
        break
if not records:
    raise ValueError('raw event not found')
OUT.mkdir()
(OUT / 'summary.json').write_text(json.dumps({'status':'PASS', 'scope':'h6 native corners of selected low-FA RN1 points; 1e-6 is a descriptive reporting cutoff, not a conservation tolerance', 'arms':summary}, indent=2) + '\n')
(OUT / 'raw_event.json').write_text(json.dumps({'event':event, 'raw_path':str(raw_path.resolve()), 'raw_sha256':audit.sha(raw_path), 'records':records}, indent=2) + '\n')
receipt = {'status':'PASS', 'reviewer_sha256':audit.sha(__file__),
           'input_receipts':{arm:audit.sha(HERE/'full'/arm/'receipt.json') for arm in audit.ARMS},
           'selected_points_sha256':audit.sha(HERE.parent/'cohorts/results/selected_points.csv'),
           'outputs':{p.name:audit.sha(p) for p in sorted(OUT.iterdir())}}
(OUT / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(summary, indent=2))
