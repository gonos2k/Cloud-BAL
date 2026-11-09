#!/usr/bin/env python3
"""Recount fixed false-alarm cohorts and observation-strength distributions."""
import argparse
import csv
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
EVALUATOR = ROOT / 'docs/evidence/cp02_first_ice_velocity_20261109/evaluation/evaluate.py'
spec = importlib.util.spec_from_file_location('ice_evaluate', EVALUATOR)
evaluation = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = evaluation
spec.loader.exec_module(evaluation)
B1, CONS, NEW = evaluation.B1, evaluation.CONS, evaluation.NEW
CASES, HOURS = evaluation.CASES, evaluation.HOURS
INVENTORY = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/Cloud-BAL/scratch/cp02_six_hour_20260914/reference/inventory.json')
INVENTORY_SHA = 'fc65b7ff026d2813ede107d3c60e58f702f6d6286ae8c0940196ff7283d3f460'
TARGETS = (10813, 11571, 11855)
EDGES = (0., .1, .5, 1., 2.5, 5., 10., float('inf'))
LABELS = ('[0,0.1)', '[0.1,0.5)', '[0.5,1)', '[1,2.5)', '[2.5,5)', '[5,10)', '[10,inf)')


def cohort_masks(hour):
    eligible = (hour['reference'] < 5) & (hour[B1] < 5)
    old, new = hour[CONS] >= 5, hour[NEW] >= 5
    return {'persistent': eligible & old & new, 'new': eligible & ~old & new,
            'resolved': eligible & old & ~new}


def transitions(hour, baseline):
    eligible = hour['reference'] < 5
    before, after = hour[baseline] >= 5, hour[NEW] >= 5
    return {'before_false_alarms': int((eligible & before).sum()),
            'after_false_alarms': int((eligible & after).sum()),
            'gained': int((eligible & ~before & after).sum()),
            'lost': int((eligible & before & ~after).sum())}


def members(arrays):
    h1, h6 = arrays[13], arrays[18]
    ids = h6['flat_index_yx']
    rows = [(name, int(ids[i]), '') for name, mask in cohort_masks(h6).items()
            for i in np.flatnonzero(mask)]
    retained = ((h1['reference'] >= 10) & (h1[B1] >= 10) &
                (h1[CONS] >= 10) & (h1[NEW] >= 10))
    for target in TARGETS:
        matches = np.flatnonzero(ids == target)
        if len(matches) != 1: raise ValueError(f'missing target {target}')
        index = matches[0]
        if not (h1['reference'][index] < 10 and h1[B1][index] < 10 and h1[NEW][index] >= 10):
            raise ValueError(f'target {target} no longer meets selection')
        candidates = np.flatnonzero(retained)
        if not len(candidates): raise ValueError('no retained hits for controls')
        # Equirectangular angular distance; ties broken by flat grid identity.
        lat = np.deg2rad((h6['latitude'][candidates] + h6['latitude'][index]) / 2)
        distance = ((h6['latitude'][candidates] - h6['latitude'][index]) ** 2 +
                    ((h6['longitude'][candidates] - h6['longitude'][index]) * np.cos(lat)) ** 2)
        control = candidates[np.lexsort((ids[candidates], distance))[0]]
        rows.append(('named_new', target, target))
        rows.append(('nearest_retained_hit', int(ids[control]), target))
    return rows


def crop_offsets(inventory):
    x0, x1 = inventory['grid']['crop_x_inclusive']
    y0, y1 = inventory['grid']['crop_y_inclusive']
    if (x0, x1, y0, y1) != (76, 224, 7, 259):
        raise ValueError('pinned crop differs')
    return y0 - 2, x0 - 2


def paths(arrays, mapping, selected, offsets):
    ids = arrays[13]['flat_index_yx']
    lookup = {int(value): i for i, value in enumerate(ids)}
    shape = mapping['valid'].shape
    rows = []
    for cohort, point, target in selected:
        i = lookup[point]
        y, x = np.unravel_index(point, shape)
        if not mapping['valid'][y, x]: raise ValueError('selected mapping invalid')
        j, k = int(mapping['j0'][y, x]), int(mapping['i0'][y, x])
        u, v = float(mapping['u'][y, x]), float(mapping['v'][y, x])
        row = {'cohort': cohort, 'flat_index_yx': point, 'target_flat_index_yx': target,
               'latitude': float(arrays[13]['latitude'][i]), 'longitude': float(arrays[13]['longitude'][i]),
               'obs_y': int(y), 'obs_x': int(x), 'crop_j0_zero_based': j, 'crop_i0_zero_based': k,
               'native_j0_zero_based': j + offsets[0], 'native_i0_zero_based': k + offsets[1],
               'native_j0_fortran_one_based': j + offsets[0] + 1,
               'native_i0_fortran_one_based': k + offsets[1] + 1,
               'weight_j0_i0': (1-u)*(1-v), 'weight_j0_i1': u*(1-v),
               'weight_j1_i0': (1-u)*v, 'weight_j1_i1': u*v}
        for field in ('reference', *CASES):
            for hour in HOURS: row[f'{field}_h{hour-12}_mm'] = float(arrays[hour][field][i])
            row[f'{field}_h5_h6_sum_mm'] = float(arrays[17][field][i] + arrays[18][field][i])
        rows.append(row)
    return rows


def intensity_bins(arrays):
    rows = []
    for hour in HOURS:
        obs = arrays[hour]['reference']
        for case in CASES:
            pred = arrays[hour][case]
            for n, label in enumerate(LABELS):
                subset = (obs >= EDGES[n]) & (obs < EDGES[n+1])
                row = {'lead_hour': hour-12, 'case': case, 'observation_bin_mm': label,
                       'observations': int(subset.sum()),
                       'forecast_ge_0.1_mm': int((subset & (pred >= .1)).sum()),
                       'forecast_ge_5_mm': int((subset & (pred >= 5)).sum()),
                       'forecast_exceeds_observation': int((subset & (pred > obs)).sum())}
                for j, forecast_label in enumerate(LABELS):
                    row['forecast_' + forecast_label] = int((subset & (pred >= EDGES[j]) & (pred < EDGES[j+1])).sum())
                rows.append(row)
    return rows


def write_csv(path, rows):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader(); writer.writerows(rows)


def run(results, output, inventory_path=INVENTORY):
    if os.path.lexists(output): raise FileExistsError(output)
    inventory_record = evaluation.identity(inventory_path)
    if inventory_record['sha256'] != INVENTORY_SHA: raise ValueError('inventory hash mismatch')
    offsets = crop_offsets(json.loads(inventory_path.read_text()))
    receipt_path = results / 'receipt.json'
    receipt = json.loads(receipt_path.read_text())
    mapping_path = results / 'bilinear_mapping.npz'
    if evaluation.identity(mapping_path)['sha256'] != receipt['outputs']['bilinear_mapping.npz']:
        raise ValueError('mapping hash mismatch')
    inputs = [inventory_record, evaluation.identity(receipt_path), evaluation.identity(mapping_path)]
    inputs += [evaluation.identity(results / f'hour_{h}_arrays.npz') for h in HOURS]
    arrays = evaluation.read_arrays(results)
    _, _, constraints, _ = evaluation.score(arrays)
    with np.load(mapping_path, allow_pickle=False) as data:
        mapping = {k: data[k].copy() for k in data.files}
    selected = members(arrays)
    counts = {name: int(mask.sum()) for name, mask in cohort_masks(arrays[18]).items()}
    full = {case: transitions(arrays[18], case) for case in (B1, CONS)}
    verdict = sum(row['satisfied'] for row in constraints if row['candidate'] == NEW)
    if counts != {'persistent': 65, 'new': 26, 'resolved': 37} or verdict != 21:
        raise ValueError('frozen cohort or admission count changed')
    if full[B1] != {'before_false_alarms': 226, 'after_false_alarms': 285, 'gained': 91, 'lost': 32} or full[CONS] != {'before_false_alarms': 287, 'after_false_alarms': 285, 'gained': 48, 'lost': 50}:
        raise ValueError('full false-alarm transitions changed')
    summary = {'scope': 'diagnostic only; fixed 26-condition admission unchanged',
               'selection': 'h6 observation <5 and B1 <5; PR153 and FIRST_ICE_VELOCITY event threshold >=5 mm',
               'cohorts': counts, 'full_false_alarm_transitions_h6': full,
               'control_selection': 'nearest retained h1 hit with observation, B1, PR153 and candidate all >=10 mm; equirectangular angular distance, ties by smallest flat_index_yx; sampling with replacement',
               'named_targets': list(TARGETS), 'candidate_admission': {'passed': verdict, 'required': 26},
               'bins': 'left inclusive, right exclusive; each lead is preceding hourly precipitation',
               'mapping': 'flat_index_yx indexes observation grid; crop anchors are zero-based, native anchors are full WRF grid in zero- and Fortran one-based conventions; +1 gives adjacent corners; bilinear weights unchanged',
               'crop_to_native_zero_based_offsets': {'j': offsets[0], 'i': offsets[1]}}
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.false-alarm-stage-', dir=output.parent))
    try:
        write_csv(stage / 'membership.csv', [dict(cohort=c, flat_index_yx=p, target_flat_index_yx=t) for c,p,t in selected])
        write_csv(stage / 'point_paths.csv', paths(arrays, mapping, selected, offsets))
        write_csv(stage / 'lead_bins.csv', intensity_bins(arrays))
        (stage / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        for record in inputs:
            if evaluation.identity(record['path']) != record: raise ValueError('input changed')
        record = {'status': 'COMPLETE', 'inputs': inputs, 'source': evaluation.identity(__file__),
                  'evaluator': evaluation.identity(EVALUATOR),
                  'outputs': {p.name: evaluation.identity(p)['sha256'] for p in sorted(stage.iterdir())}}
        (stage / 'receipt.json').write_text(json.dumps(record, indent=2) + '\n')
        evaluation.publish_new(stage, output)
    finally:
        if stage.exists(): shutil.rmtree(stage)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--inventory', type=Path, default=INVENTORY)
    args = parser.parse_args()
    print(json.dumps(run(args.results, args.output, args.inventory), indent=2))


if __name__ == '__main__': main()
