#!/usr/bin/env python3
"""Audit sampled native-corner rain-field differences for every DM065 focus row."""
from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
import tempfile

import numpy as np

ROOT = Path(__file__).resolve().parents[4]
EVIDENCE = ROOT / 'docs/evidence/cp02_failure_regimes_20261104'
STATE = EVIDENCE / 'state/results'
TRANSITIONS = EVIDENCE / 'transitions/results'
STATE_RECEIPT = '9e6a4cea51bdd88ae45a6052e6818a07ee5003de7dfc5dc2050c048075277d8c'
TRANSITION_RECEIPT = '10643ef606714df93385cdb82be75542584af41f7400d4fced73512f96f0db38'
FOCUS_SHA = '05c557bae2e5d4702f6c377a17d78f48eaee289e8a65abbd745f85a74c8c08e3'
TAGS = ('input', 'h00', 'h01', 'h02', 'h03', 'h04', 'h05', 'h06')


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load_bound():
    state_path = STATE / 'receipt.json'
    transition_path = TRANSITIONS / 'receipt.json'
    focus_path = TRANSITIONS / 'focus_membership.csv'
    if (sha(state_path) != STATE_RECEIPT or sha(transition_path) != TRANSITION_RECEIPT or
        sha(focus_path) != FOCUS_SHA):
        raise ValueError('source receipt or focus table pin changed')
    state = json.loads(state_path.read_text())
    transition = json.loads(transition_path.read_text())
    if state.get('status') != 'PASS' or transition.get('status') != 'PASS':
        raise ValueError('source analysis did not pass')
    if transition['outputs']['focus_membership.csv']['sha256'] != FOCUS_SHA:
        raise ValueError('focus receipt binding differs')
    records = {(r['case'], r['time']): r for r in state['records']}
    wanted = {(case, tag) for case in ('B1', 'NR_PRIOR', 'DM065') for tag in TAGS}
    if len(state['records']) != 24 or set(records) != wanted:
        raise ValueError('state receipt case/time inventory differs')
    for record in records.values():
        path = STATE / record['name']
        if path.is_symlink() or path.stat().st_size != record['size_bytes'] or sha(path) != record['sha256']:
            raise ValueError(f'state artifact differs: {path.name}')
    with focus_path.open(newline='', encoding='utf-8') as stream:
        rows = [r for r in csv.DictReader(stream) if r['comparison'] == 'B1_RAIN_NUMBER_DM065']
    keys = [(r['focus_group'], r['transition'], int(r['flat_index_yx'])) for r in rows]
    if not rows or len(set(keys)) != len(keys):
        raise ValueError('focus rows empty or duplicate')
    return records, rows


def fields_for_tag(records, tag, expected_coordinates=None):
    arrays = []
    for case in ('B1', 'DM065'):
        with np.load(STATE / records[case, tag]['name'], allow_pickle=False) as archive:
            names = ('flat_index_yx', 'latitude', 'longitude', 'native_j_zero_based', 'native_i_zero_based',
                     'corner_weights', 'corner_qrain_kgkg', 'corner_qnrain_per_kg')
            values = {name: np.array(archive[name], copy=True) for name in names}
        if (values['flat_index_yx'].shape != (3688,) or
            len(np.unique(values['flat_index_yx'])) != 3688 or
            values['corner_weights'].shape != (3688, 4) or
            values['corner_qrain_kgkg'].shape != (3688, 39, 4) or
            values['corner_qnrain_per_kg'].shape != (3688, 39, 4)):
            raise ValueError(f'{case}/{tag}: state shape differs')
        if (not np.isfinite(values['corner_weights']).all() or np.any(values['corner_weights'] < 0) or
            not np.allclose(values['corner_weights'].sum(axis=1), 1., rtol=0, atol=1e-12) or
            not np.isfinite(values['corner_qrain_kgkg']).all() or
            not np.isfinite(values['corner_qnrain_per_kg']).all()):
            raise ValueError(f'{case}/{tag}: invalid weights or rain fields')
        arrays.append(values)
    coordinates = tuple(arrays[0][k] for k in names[:6])
    if any(not np.array_equal(arrays[0][k], arrays[1][k]) for k in names[:6]):
        raise ValueError(f'{tag}: B1 and DM065 coordinates differ')
    if expected_coordinates is not None and any(not np.array_equal(a, b) for a, b in zip(coordinates, expected_coordinates)):
        raise ValueError(f'{tag}: coordinates differ across sampled times')
    positive = arrays[0]['corner_weights'][:, None, :] > 0
    maxima = {}
    for field, short in (('corner_qrain_kgkg', 'qr'), ('corner_qnrain_per_kg', 'nr')):
        # Convert first so subtraction is exact for finite REAL32 values.
        difference = np.abs(arrays[1][field].astype(np.float64) - arrays[0][field].astype(np.float64))
        maxima[short] = np.max(np.where(positive, difference, 0.), axis=(1, 2))
    return coordinates, maxima


def main():
    records, groups = load_bound()
    coordinates = None
    sampled = {}
    for tag in TAGS:
        coordinates, sampled[tag] = fields_for_tag(records, tag, coordinates)
    flat, lat, lon, jj, ii, weights = coordinates
    index = {int(value): i for i, value in enumerate(flat)}
    columns = ['focus_group', 'transition', 'lead_hour', 'threshold_mm', 'flat_index_yx',
               'latitude', 'longitude', 'native_j_zero_based', 'native_i_zero_based',
               'corner_weights', 'initial_nr_changed']
    for tag in TAGS:
        columns += [f'{tag}_maxabs_qrain_kgkg', f'{tag}_maxabs_qnrain_per_kg']
    rows = []
    for group in groups:
        point = int(group['flat_index_yx'])
        if point not in index:
            raise ValueError('focus point absent from state cohort')
        i = index[point]
        if float(group['latitude']) != lat[i] or float(group['longitude']) != lon[i]:
            raise ValueError('focus coordinates differ from state cohort')
        row = {k: group[k] for k in ('focus_group','transition','lead_hour','threshold_mm','flat_index_yx','latitude','longitude')}
        row.update(native_j_zero_based=';'.join(str(int(x)) for x in jj[i]),
                   native_i_zero_based=';'.join(str(int(x)) for x in ii[i]),
                   corner_weights=';'.join(repr(float(x)) for x in weights[i]),
                   initial_nr_changed=bool(sampled['input']['nr'][i] != 0.))
        for tag in TAGS:
            row[f'{tag}_maxabs_qrain_kgkg'] = float(sampled[tag]['qr'][i])
            row[f'{tag}_maxabs_qnrain_per_kg'] = float(sampled[tag]['nr'][i])
        rows.append(row)
    rows.sort(key=lambda r: (r['focus_group'], r['transition'], int(r['flat_index_yx'])))
    summary = {}
    for group in sorted({(r['focus_group'],r['transition']) for r in rows}):
        selected = [r for r in rows if (r['focus_group'],r['transition']) == group]
        unchanged = [r for r in selected if not r['initial_nr_changed']]
        summary['/'.join(group)] = {'points': len(selected),
                                    'initial_nr_changed': len(selected)-len(unchanged),
                                    'initial_nr_unchanged': len(unchanged),
                                    'h00_qr_changed': sum(float(r['h00_maxabs_qrain_kgkg']) != 0 for r in selected),
                                    'unchanged_initial_h01_qr_changed': sum(float(r['h01_maxabs_qrain_kgkg']) != 0 for r in unchanged),
                                    'unchanged_initial_h01_nr_changed': sum(float(r['h01_maxabs_qnrain_per_kg']) != 0 for r in unchanged),
                                    'unchanged_initial_h02_qr_changed': sum(float(r['h02_maxabs_qrain_kgkg']) != 0 for r in unchanged),
                                    'unchanged_initial_h02_nr_changed': sum(float(r['h02_maxabs_qnrain_per_kg']) != 0 for r in unchanged)}
    directory = EVIDENCE / 'science'
    target, receipt = directory / 'local_initial_change.csv', directory / 'local_initial_change.json'
    if os.path.lexists(target) or os.path.lexists(receipt):
        raise FileExistsError('refuse to overwrite audit outputs')
    directory.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.local-change-', dir=directory)
    try:
        with os.fdopen(fd, 'w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=columns, lineterminator='\n')
            writer.writeheader(); writer.writerows(rows)
        load_bound()
        result = {'status':'PASS', 'rows':len(rows), 'groups':summary,
                  'csv_sha256':sha(name), 'source_sha256':sha(Path(__file__)),
                  'state_receipt_sha256':STATE_RECEIPT, 'transition_receipt_sha256':TRANSITION_RECEIPT,
                  'focus_sha256':FOCUS_SHA, 'method':'numerical inequality of raw REAL32 native corner values, positive-weight corners and all 39 levels; signed zeros equal; max absolute difference in float64',
                  'interpretation':'Diagnostic outcome group only; Eulerian snapshot differences are not trajectories or causal transport. First sampled hour with difference is not the true first difference.'}
        stat = os.stat(name)
        target_identity = (stat.st_dev, stat.st_ino)
        os.link(name, target)
        receipt_identity = None
        try:
            with receipt.open('x', encoding='utf-8') as stream:
                stat = os.fstat(stream.fileno())
                receipt_identity = (stat.st_dev, stat.st_ino)
                json.dump(result, stream, indent=2, sort_keys=True); stream.write('\n')
        except BaseException:
            for path, identity in ((target, target_identity), (receipt, receipt_identity)):
                if identity is not None:
                    try:
                        stat = path.lstat()
                        if (stat.st_dev, stat.st_ino) == identity:
                            path.unlink()
                    except FileNotFoundError:
                        pass
            raise
    finally:
        Path(name).unlink(missing_ok=True)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
