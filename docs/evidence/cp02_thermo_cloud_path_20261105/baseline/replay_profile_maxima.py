#!/usr/bin/env python3
"""Record maxima of saved bilinear profiles alongside the raw-corner replay."""
import csv
import hashlib
import json
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
PRIOR = HERE.parents[1] / 'cp02_failure_regimes_20261104/state/results'
FIVE = (16606, 17051, 17199, 17792, 20183)


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    receipt = json.loads((PRIOR / 'receipt.json').read_text())
    replay = json.loads((HERE / 'pr147_observation_replay.json').read_text())
    if receipt['status'] != 'PASS' or replay['status'] != 'PASS':
        raise ValueError('source receipt is not PASS')
    with (HERE / 'pr147_observation_replay.csv').open(newline='') as stream:
        corners = {int(r['flat_index_yx']): r for r in csv.DictReader(stream)
                   if r['group'] == 'new_false_alarm' and int(r['flat_index_yx']) in FIVE}
    if sha(HERE / 'pr147_observation_replay.csv') != replay['csv_sha256'] or set(corners) != set(FIVE):
        raise ValueError('raw replay changed')
    states = []
    for arm in ('B1', 'DM065'):
        rec = next(r for r in receipt['records'] if r['case'] == arm and r['time'] == 'h01')
        path = PRIOR / rec['name']
        if sha(path) != rec['sha256'] or path.stat().st_size != rec['size_bytes']:
            raise ValueError('state input changed')
        with np.load(path, allow_pickle=False) as data:
            states.append({k: data[k].copy() for k in ('flat_index_yx', 'qvapor_kgkg', 'temperature_K', 'pressure_Pa')})
    if not np.array_equal(states[0]['flat_index_yx'], states[1]['flat_index_yx']):
        raise ValueError('state identities differ')
    rows = []
    for point in FIVE:
        indices = np.flatnonzero(states[0]['flat_index_yx'] == point)
        if indices.size != 1:
            raise ValueError('point missing or duplicate')
        i = indices[0]
        row = {'flat_index_yx': point}
        for field in ('qvapor_kgkg', 'temperature_K', 'pressure_Pa'):
            delta = np.abs(states[1][field][i].astype('f8') - states[0][field][i].astype('f8'))
            if delta.shape != (39,) or not np.isfinite(delta).all():
                raise ValueError('invalid profile')
            row['bilinear_' + field + '_maxabs'] = float(delta.max())
            row['bilinear_' + field + '_max_level_1based'] = int(delta.argmax()) + 1
        for field in ('QVAPOR', 'T', 'P'):
            for suffix in ('maxabs_delta', 'max_level_1based'):
                row['raw_corner_' + field + '_' + suffix] = corners[point]['h01_raw_' + field + '_' + suffix]
        rows.append(row)
    if rows[-1]['bilinear_qvapor_kgkg_max_level_1based'] != 2 or rows[-1]['bilinear_temperature_K_max_level_1based'] != 2:
        raise ValueError('20183 profile maxima differ')
    out = HERE / 'pr147_profile_maxima.csv'
    with out.open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({'status': 'PASS', 'csv_sha256': sha(out), 'source_sha256': sha(Path(__file__)),
                      'raw_replay_sha256': replay['csv_sha256'], 'state_receipt_sha256': sha(PRIOR / 'receipt.json')}))


if __name__ == '__main__':
    main()
