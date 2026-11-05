#!/usr/bin/env python3
"""Distinguish each arm's first positive rain from its first paired difference."""
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
from portable_arrays import load

ROOT = Path(__file__).resolve().parents[4]
BUNDLE = ROOT / 'docs/evidence/cp02_thermo_cloud_path_20261105'
CAPTURE = BUNDLE / 'analysis'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    receipt_path = CAPTURE / 'full_capture_receipt.json'
    if sha(receipt_path) != 'e41105c152b55991784f1fcf0b8c8e1c75fe03fc3d33160b897160adadd33245':
        raise ValueError('full receipt differs')
    receipt = json.loads(receipt_path.read_text())
    with (BUNDLE / 'cohorts/results/selected_points.csv').open(newline='') as stream:
        points = list(csv.DictReader(stream))
    if [p['point_id'] for p in points] != receipt['point_ids']:
        raise ValueError('point ordering differs')
    states = {}
    for arm in ('B1', 'DM065'):
        states[arm] = load(f'{arm}_point_timeseries', receipt['arms'][arm]['output_sha256'],
                           ['entry', 'return', 'phase_8'])
    rows = []
    for stage, field, idx, units in (('wrapper_entry', 'QR', 3, 'kg kg-1'), ('wrapper_entry', 'NR', 10, 'kg-1'),
                                     ('main_post_update', 'QR', 6, 'kg kg-1'), ('main_post_update', 'NR', 12, 'm-3'),
                                     ('wrapper_return', 'QR', 3, 'kg kg-1'), ('wrapper_return', 'NR', 10, 'kg-1')):
        key = {'wrapper_entry': 'entry', 'wrapper_return': 'return', 'main_post_update': 'phase_8'}[stage]
        a, b = (states[arm][key][..., idx] for arm in ('B1', 'DM065'))
        if a.shape != (360, 39, 39) or not np.isfinite(a).all() or not np.isfinite(b).all():
            raise ValueError('invalid stage array')
        for i, point in enumerate(points):
            x, y = a[:, :, i], b[:, :, i]
            delta = y - x
            for arm, data, predicate in (('B1', x, x > 0), ('DM065', y, y > 0), ('DM065_minus_B1', delta, delta != 0)):
                hit = np.flatnonzero(np.any(predicate, axis=1))
                first = int(hit[0]) if hit.size else None
                if first is not None:
                    candidates = np.flatnonzero(predicate[first])
                    k = int(candidates[np.argmax(np.abs(data[first, candidates]))])
                    value = float(data[first, k])
                else:
                    k, value = None, ''
                loc = np.unravel_index(np.abs(data).argmax(), data.shape)
                rows.append({'point_id': point['point_id'], 'group': point['group'], 'flat_index_yx': point['flat_index_yx'],
                             'stage': stage, 'field': field, 'arm_or_difference': arm, 'units': units,
                             'first_sample_step': first + 1 if first is not None else '',
                             'first_sample_level_1based': k + 1 if k is not None else '', 'first_sample_value': value,
                             'maximum_abs': float(abs(data[loc])), 'signed_at_maximum': float(data[loc]),
                             'maximum_step': int(loc[0] + 1), 'maximum_level_1based': int(loc[1] + 1)})
    path = BUNDLE / 'analysis/rain_presence_recount.csv'
    with path.open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({'status': 'PASS', 'rows': len(rows), 'csv_sha256': sha(path),
                      'source_sha256': sha(Path(__file__)), 'full_receipt_sha256': sha(receipt_path)}))


if __name__ == '__main__':
    main()
