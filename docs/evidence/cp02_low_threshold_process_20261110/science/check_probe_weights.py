#!/usr/bin/env python3
"""Independently recount each probe point's weighted residual and missing mask."""
import csv
import gzip
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
selected = ROOT.parent / 'cohorts/results/selected_points.csv'
corners = {}
with selected.open(newline='') as f:
    for r in csv.DictReader(f):
        i, j = int(r['native_i0_fortran_one_based']), int(r['native_j0_fortran_one_based'])
        corners[r['flat_index_yx']] = [(i, j, float(r['weight_j0_i0'])),
            (i+1, j, float(r['weight_j0_i1'])), (i, j+1, float(r['weight_j1_i0'])),
            (i+1, j+1, float(r['weight_j1_i1']))]
result = {}
for arm in ('FIX', 'CONSERVATIVE', 'ICE_FIXED'):
    folder = ROOT / 'probe' / arm
    with gzip.open(folder / 'calls.csv.gz', 'rt', newline='') as f:
        calls = {(r['step'], int(r['i']), int(r['j']), r['species']):r for r in csv.DictReader(f)}
    valid = missing = 0
    with gzip.open(folder / 'weighted_points.csv.gz', 'rt', newline='') as f:
        for row in csv.DictReader(f):
            parts = [(calls.get((row['step'], i, j, row['species'])), w)
                     for i, j, w in corners[row['flat_index_yx']] if w > 0]
            complete = all(r is not None and r['residual_kg_m2'] != '' for r, _ in parts)
            if bool(int(row['all_positive_weight_corners_valid'])) != complete:
                raise ValueError('validity mismatch')
            if complete:
                expected = sum(float(r['residual_kg_m2']) * w for r, w in parts)
                if abs(float(row['residual_kg_m2']) - expected) > 1e-14:
                    raise ValueError('weighted residual differs')
                valid += 1
            else:
                if row['residual_kg_m2']:
                    raise ValueError('unavailable residual is not blank')
                missing += 1
    if (valid, missing) != (108, 144):
        raise ValueError('unexpected probe coverage')
    result[arm] = {'valid':valid, 'unavailable':missing}
print(json.dumps({'status':'PASS', 'arms':result}, indent=2))
