#!/usr/bin/env python3
"""Recount limited cloud-to-rain rates and liquid relative humidity for all points."""
import csv
import hashlib
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[4]
BUNDLE = ROOT / 'docs/evidence/cp02_thermo_cloud_path_20261105'
CAPTURE = ROOT.parent / 'runtime/full/analysis'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    receipt = CAPTURE / 'receipt.json'
    if sha(receipt) != 'e41105c152b55991784f1fcf0b8c8e1c75fe03fc3d33160b897160adadd33245':
        raise ValueError('full receipt differs')
    full = json.loads(receipt.read_text())
    source = CAPTURE / 'paired_differences.npz'
    if full['status'] != 'PASS_FULL_CAPTURE' or sha(source) != full['paired_outputs']['paired_differences.npz']['sha256']:
        raise ValueError('paired source differs')
    with (BUNDLE / 'cohorts/results/selected_points.csv').open(newline='') as stream:
        points = list(csv.DictReader(stream))
    if [p['point_id'] for p in points] != full['point_ids']:
        raise ValueError('point ordering differs')
    rows = []
    with np.load(source, allow_pickle=False) as data:
        rate = data['phase_5_difference']
        sat = data['phase_3_difference']
        for field, values in (('praut_kgkg_s', rate[..., 0]), ('pracw_kgkg_s', rate[..., 1]),
                              ('liquid_relative_humidity', sat[..., 6])):
            if values.shape != (360, 39, 39) or not np.isfinite(values).all():
                raise ValueError('invalid paired field')
            for i, point in enumerate(points):
                x = values[:, :, i]
                first = np.flatnonzero(np.any(x != 0, axis=1))
                k = np.unravel_index(np.abs(x).argmax(), x.shape)
                rows.append({'point_id': point['point_id'], 'group': point['group'],
                             'flat_index_yx': point['flat_index_yx'], 'field': field,
                             'first_step': int(first[0]+1) if first.size else '',
                             'max_abs': float(abs(x[k])), 'signed_at_max': float(x[k]),
                             'max_step': int(k[0]+1), 'max_level_1based': int(k[1]+1)})
    target = BUNDLE / 'analysis/cloud_rate_recount.csv'
    with target.open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({'status': 'PASS', 'rows': len(rows), 'csv_sha256': sha(target),
                      'full_receipt_sha256': sha(receipt), 'source_sha256': sha(Path(__file__))}))


if __name__ == '__main__':
    main()
