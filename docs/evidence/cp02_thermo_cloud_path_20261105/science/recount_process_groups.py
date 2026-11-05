#!/usr/bin/env python3
"""Descriptive group and telescoping-ledger recount from verified NPZ parts."""
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile

import numpy as np

ROOT = Path(__file__).resolve().parents[4]
BUNDLE = ROOT / 'docs/evidence/cp02_thermo_cloud_path_20261105'
sys.path.insert(0, str(ROOT / 'tools'))
from pack_cp02_selected_npz import load_partarrays

PINS = {
    'analysis/paired_differences_parts/paired_differences.parts.json': 'ecc4729ce321510e93aaef118e9b578464cb46776b8f5c3fbca74c55dd851440',
    'analysis/full_capture_receipt.json': 'e41105c152b55991784f1fcf0b8c8e1c75fe03fc3d33160b897160adadd33245',
    'cohorts/results/selected_points.csv': '3343201b904a9b9874fea8f174715e37f1d642871f371bf1f378ed8a13a62197',
    'science/surface_reference/point_components.csv': 'de81cd987b12c32ea84a240af17b5edd7391bd26e2e500f47e93b4ebb81137e2',
}
LOADER_SHA = '3c929e783856119daebf5b35487a0b10330d368db201024e5e57e7b37c34fb4d'
GROUPS = ('new_fa_initial_nr_unchanged', 'removed_fa_initial_nr_unchanged')
ANCHORS = (17051, 20183, 16454, 20330)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def check_pins():
    for path, expected in PINS.items():
        if sha(BUNDLE / path) != expected:
            raise ValueError(f'input changed: {path}')
    if sha(ROOT / 'tools/pack_cp02_selected_npz.py') != LOADER_SHA:
        raise ValueError('parts loader changed')


def read_inputs():
    check_pins()
    receipt = json.loads((BUNDLE / 'analysis/full_capture_receipt.json').read_text())
    with (BUNDLE / 'cohorts/results/selected_points.csv').open(newline='') as stream:
        points = list(csv.DictReader(stream))
    if receipt['status'] != 'PASS_FULL_CAPTURE' or [p['point_id'] for p in points] != receipt['point_ids']:
        raise ValueError('point order or receipt differs')
    if len(points) != 39 or len({p['point_id'] for p in points}) != 39:
        raise ValueError('point inventory differs')
    if [sum(p['group'] == g for p in points) for g in GROUPS] != [15, 12]:
        raise ValueError('comparison group inventory differs')
    fields = ['entry_difference', 'return_difference', 'within_call_difference',
              'between_call_difference', 'phase_5_difference', 'condensation_q_change_difference',
              'condensation_temperature_change_difference', 'sedimentation_net_difference']
    arrays = load_partarrays(BUNDLE / 'analysis/paired_differences_parts/paired_differences.parts.json', names=fields)
    for key in fields:
        a = arrays[key]
        if a.shape[0] != (359 if key == 'between_call_difference' else 360) or a.shape[1:3] != (39, 39) or not np.isfinite(a).all():
            raise ValueError(f'invalid {key} array')
    with (BUNDLE / 'science/surface_reference/point_components.csv').open(newline='') as stream:
        surface = list(csv.DictReader(stream))
    lookup = {}
    for row in surface:
        key = (row['arm'], row['point_id'], int(row['lead_hour']))
        if key in lookup:
            raise ValueError('duplicate surface component')
        val = float(row['RAINNC_hour_mm'])
        if not math.isfinite(val):
            raise ValueError('nonfinite surface component')
        lookup[key] = val
    if set(lookup) != {(arm, p['point_id'], h) for arm in ('B1', 'DM065') for p in points for h in (1, 2)}:
        raise ValueError('surface component inventory differs')
    return points, arrays, lookup


def selected_metrics(arrays):
    entry, within, between, rates = (arrays[k] for k in ('entry_difference', 'within_call_difference', 'between_call_difference', 'phase_5_difference'))
    return {
        'entry_qv_max_abs_kgkg': entry[..., 1], 'entry_tk_max_abs_K': entry[..., 13],
        'within_qv_max_abs_kgkg': within[..., 1], 'within_tk_max_abs_K': within[..., 13],
        'between_qv_max_abs_kgkg': between[..., 1], 'between_tk_max_abs_K': between[..., 13],
        'limited_praut_max_abs_kgkg_s': rates[..., 0], 'limited_pracw_max_abs_kgkg_s': rates[..., 1],
        'condensation_qv_max_abs_kgkg': arrays['condensation_q_change_difference'],
        'condensation_tk_max_abs_K': arrays['condensation_temperature_change_difference'],
        'wrapper_entry_qr_max_abs_kgkg': entry[..., 3],
        'sedimentation_qr_increment_max_abs_kgkg': arrays['sedimentation_net_difference'][..., 0],
    }


def point_rows(points, arrays, surface):
    rows = []
    for name, values in selected_metrics(arrays).items():
        between = name.startswith('between_')
        for hour in (1, 2):
            # Between index 0 joins step 1 return to step 2 entry; classify by destination step.
            lo, hi = ((0, 179) if hour == 1 else (179, 359)) if between else ((0, 180) if hour == 1 else (180, 360))
            for i, point in enumerate(points):
                all_values = values[:, :, i]
                first = np.flatnonzero(np.any(all_values != 0, axis=1))
                sample = all_values[lo:hi]
                loc = np.unravel_index(np.abs(sample).argmax(), sample.shape)
                rows.append({'point_id': point['point_id'], 'flat_index_yx': point['flat_index_yx'], 'group': point['group'],
                             'hour': hour, 'metric': name, 'value': float(abs(sample[loc])),
                             'signed_at_max': float(sample[loc]), 'max_sample_step': int(lo + loc[0] + (2 if between else 1)),
                             'max_level_1based': int(loc[1] + 1),
                             'first_nonzero_sample_step': int(first[0] + (2 if between else 1)) if first.size else ''})
    for hour in (1, 2):
        for point in points:
            pid = point['point_id']
            val = surface['DM065', pid, hour] - surface['B1', pid, hour]
            rows.append({'point_id': pid, 'flat_index_yx': point['flat_index_yx'], 'group': point['group'],
                         'hour': hour, 'metric': 'RAINNC_hour_signed_difference_mm', 'value': val,
                         'signed_at_max': '', 'max_sample_step': '', 'max_level_1based': '', 'first_nonzero_sample_step': ''})
    return rows


def group_rows(rows):
    result = []
    for group in GROUPS:
        for hour in (1, 2):
            metrics = sorted({r['metric'] for r in rows if r['group'] == group and r['hour'] == hour})
            for metric in metrics:
                values = np.array([r['value'] for r in rows if r['group'] == group and r['hour'] == hour and r['metric'] == metric], dtype='f8')
                if values.size != (15 if group == GROUPS[0] else 12):
                    raise ValueError('group size differs')
                q1, median, q3 = np.quantile(values, [0.25, 0.5, 0.75], method='linear')
                result.append({'group': group, 'hour': hour, 'metric': metric, 'n': int(values.size),
                               'median': float(median), 'q1': float(q1), 'q3': float(q3)})
    return result


def ledger_rows(points, arrays):
    rows = []
    index = {int(p['flat_index_yx']): i for i, p in enumerate(points)}
    for anchor in ANCHORS:
        if anchor not in index:
            raise ValueError('ledger anchor absent')
        point = points[index[anchor]]
        for name, field in (('QV_kgkg', 1), ('TK_K', 13)):
            i = index[anchor]
            entry = arrays['entry_difference'][:, 1, i, field]
            returned = arrays['return_difference'][:, 1, i, field]
            within = arrays['within_call_difference'][:, 1, i, field]
            between = arrays['between_call_difference'][:, 1, i, field]
            for n in (180, 360):
                initial, final = float(entry[0]), float(returned[n - 1])
                sw, sb = float(np.sum(within[:n], dtype='f8')), float(np.sum(between[:n-1], dtype='f8'))
                lhs = final - initial
                residual = lhs - (sw + sb)
                magnitude = abs(initial) + abs(final) + float(np.sum(np.abs(within[:n]), dtype='f8')) + float(np.sum(np.abs(between[:n-1]), dtype='f8'))
                u = np.finfo('f8').eps / 2
                count = 4 * n + 16
                bound = count * u / (1 - count * u) * magnitude
                if abs(residual) > bound:
                    raise ValueError('ledger exceeds float64 roundoff bound')
                rows.append({'point_id': point['point_id'], 'flat_index_yx': anchor, 'group': point['group'], 'level_1based': 2,
                             'field': name, 'steps': n, 'entry_step1_difference': initial, 'return_step_n_difference': final,
                             'return_minus_initial': lhs, 'sum_within': sw, 'sum_between': sb, 'residual': residual,
                             'float64_roundoff_bound': bound})
    return rows


def write_csv(path, rows):
    with path.open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def main():
    points, arrays, surface = read_inputs()
    rows = point_rows(points, arrays, surface)
    groups = group_rows(rows)
    ledger = ledger_rows(points, arrays)
    target = BUNDLE / 'science/process_groups/results'
    if os.path.lexists(target):
        raise FileExistsError('refusing to replace prior result')
    stage = Path(tempfile.mkdtemp(prefix='.process-groups-', dir=target.parent))
    try:
        for filename, data in (('point_metrics.csv', rows), ('group_quantiles.csv', groups), ('anchor_ledger.csv', ledger)):
            write_csv(stage / filename, data)
        check_pins()
        receipt = {'status': 'PASS', 'point_metric_rows': len(rows), 'group_rows': len(groups), 'ledger_rows': len(ledger),
                   'pins': PINS, 'parts_loader_sha256': LOADER_SHA, 'script_sha256': sha(Path(__file__)),
                   'outputs': {p.name: sha(p) for p in stage.iterdir()},
                   'semantics': 'DM065 minus B1. Point amplitudes are maxima over sampled steps and 39 Eulerian levels; quantiles use numpy linear interpolation. RAINNC is signed hourly difference, excludes RAINC. Between-call samples are classified by destination step. No attribution or causality. Sedimentation precedes main process rates. Sums in the ledger are per-call local kg/kg or K, not column mass.'}
        (stage / 'receipt.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
        if os.path.lexists(target):
            raise FileExistsError('result appeared during calculation')
        os.rename(stage, target)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    print(json.dumps({'status': 'PASS', 'receipt_sha256': sha(target / 'receipt.json'), 'rows': [len(rows), len(groups), len(ledger)]}))


if __name__ == '__main__':
    main()
