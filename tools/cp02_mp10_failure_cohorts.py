#!/usr/bin/env python3
"""Freeze MP10 diagnostic points and recount paired precipitation transitions."""
import argparse
import csv
import gzip
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import tempfile

import numpy as np
import cp02_ice_false_alarm as fa

ROOT = Path(__file__).resolve().parents[1]
EVALUATOR = ROOT / 'docs/evidence/cp02_pulse_path_20261110/evaluation/evaluate.py'
spec = importlib.util.spec_from_file_location('mp10_evaluation', EVALUATOR)
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)
prior = e.prior
RECEIPT_SHA = 'c369a2b7601355b64fac8e8611528684a3be99cebda28827fe6c38446b75fa28'
THRESHOLDS = (.1, .5, 1., 2.5, 5., 10.)


def transition(hour, baseline, threshold):
    obs = hour['reference'] >= threshold
    before = hour[baseline] >= threshold
    after = hour[e.NEW] >= threshold
    return {'hit_lost': obs & before & ~after, 'hit_gained': obs & ~before & after,
            'fa_new': ~obs & ~before & after, 'fa_resolved': ~obs & before & ~after,
            'hit_maintained': obs & before & after, 'fa_maintained': ~obs & before & after,
            'miss_maintained': obs & ~before & ~after, 'correct_negative': ~obs & ~before & ~after}


def medoid(hour, mask, used):
    ids = hour['flat_index_yx']
    indices = np.flatnonzero(mask & ~np.isin(ids, list(used)))
    if not len(indices):
        raise ValueError('empty representative stratum')
    x = np.column_stack([hour[k][indices] for k in ('latitude', 'longitude', 'reference', e.B1, e.ICE, e.NEW)])
    x = (x - x.min(axis=0)) / np.maximum(np.ptp(x, axis=0), 1e-20)
    distance = np.abs(x[:, None, :] - x[None, :, :]).sum(axis=(1, 2))
    return int(ids[indices[np.lexsort((ids[indices], distance))[0]]])


def nearest(hour, mask, target, used):
    ids = hour['flat_index_yx']
    match = np.flatnonzero(ids == target)
    if len(match) != 1:
        raise ValueError('target missing or duplicated')
    i = match[0]
    candidates = np.flatnonzero(mask & ~np.isin(ids, list(used)))
    if not len(candidates):
        raise ValueError('empty control stratum')
    lat = np.deg2rad((hour['latitude'][candidates] + hour['latitude'][i]) / 2)
    distance = ((hour['latitude'][candidates] - hour['latitude'][i]) ** 2 +
                ((hour['longitude'][candidates] - hour['longitude'][i]) * np.cos(lat)) ** 2)
    return int(ids[candidates[np.lexsort((ids[candidates], distance))[0]]])


def representatives(arrays):
    used, selected = set(), []

    def add(role, point, target=''):
        if point in used:
            raise ValueError('duplicate point')
        used.add(point)
        selected.append((role, point, target))

    h = arrays[18]
    obs = h['reference']
    new = transition(h, e.B1, 5)['fa_new']
    resolved = transition(h, e.ICE, 5)['fa_resolved']
    for lo, hi in ((0, .1), (.1, 1), (1, 5)):
        band = (obs >= lo) & (obs < hi)
        for over in (False, True):
            mask = new & band & ((h[e.NEW] >= 10) if over else (h[e.NEW] < 10))
            point = medoid(h, mask, used)
            add(f'h6_B1_new_{lo:g}_{hi:g}_over{int(over)}', point)
            add(f'h6_154_resolved_{lo:g}_{hi:g}_control', nearest(h, resolved & band, point, used), point)
    point = medoid(h, transition(h, e.ICE, 5)['fa_new'], used)
    add('h6_154_new', point)
    add('h6_154_resolved_control', nearest(h, resolved, point, used), point)
    for lead, threshold in ((3, .1), (6, .5)):
        h = arrays[lead + 12]
        for role, mask in transition(h, e.ICE, threshold).items():
            if role in ('hit_lost', 'hit_gained', 'fa_new', 'fa_resolved'):
                add(f'h{lead}_{threshold:g}_{role}', medoid(h, mask, used))
                if lead == 3 and role == 'hit_lost':
                    target = selected[-1][1]
                    band = (h['reference'] >= 1) & (h['reference'] < 2.5)
                    add('h3_0.1_hit_maintained_control',
                        nearest(h, transition(h, e.ICE, threshold)['hit_maintained'] & band, target, used), target)
    h = arrays[18]
    obs = h['reference']
    weak = ((obs >= .1) & (obs < 1) &
            np.logical_and.reduce([(h[k] >= .1) & (h[k] < 1) for k in (e.B1, e.ICE, e.NEW)]))
    for lo, hi in ((.1, .5), (.5, 1)):
        add(f'h6_weak_{lo:g}_{hi:g}', medoid(h, weak & (obs >= lo) & (obs < hi), used))
    h = arrays[13]
    add('h1_9774_hit_lost', 9774)
    retained = (h['reference'] >= 10) & (h[e.ICE] >= 10) & (h[e.NEW] >= 10)
    add('h1_retained_hit_control', nearest(h, retained, 9774, used), 9774)
    for point in (19145, 19144, 17804):
        add('comparison', point)
    if len(selected) != 30:
        raise ValueError('capture point count changed')
    return selected


def paths(arrays, mapping, selected, offsets):
    # Reuse the frozen projection and weights, but include all five cases.
    previous = fa.CASES
    try:
        fa.CASES = e.CASES
        return fa.paths(arrays, mapping, selected, offsets)
    finally:
        fa.CASES = previous


def diagnostics(arrays):
    transitions, errors, classification = [], [], []
    for hour in e.HOURS:
        h = arrays[hour]
        obs = h['reference']
        all_masks = {}
        for baseline in (e.B1, e.ICE):
            for threshold in THRESHOLDS:
                masks = transition(h, baseline, threshold)
                all_masks[baseline, threshold] = masks
                transitions.append({'lead_hour': hour - 12, 'baseline': baseline, 'threshold_mm': threshold,
                                    **{k: int(v.sum()) for k, v in masks.items()}})
        for lo, hi in ((.1, .5), (.5, 1), (.1, 1)):
            mask = (obs >= lo) & (obs < hi)
            for case in e.CASES:
                diff = h[case][mask] - obs[mask]
                errors.append({'lead_hour': hour - 12, 'observation_band': f'[{lo:g},{hi:g})',
                               'case': case, 'count': int(mask.sum()),
                               'mae_mm': float(np.abs(diff).mean()),
                               'rmse_mm': float(np.sqrt(np.square(diff).mean())),
                               'detected_ge_0.1': int((h[case][mask] >= .1).sum()),
                               'predicted_0.1_to_1': int(((h[case][mask] >= .1) & (h[case][mask] < 1)).sum())})
        for i, point in enumerate(h['flat_index_yx']):
            row = {'lead_hour': hour - 12, 'flat_index_yx': int(point),
                   **{k: float(h[k][i]) for k in ('reference', *e.CASES)}}
            for baseline, label in ((e.B1, 'B1'), (e.ICE, 'PR154')):
                for threshold in THRESHOLDS:
                    masks = all_masks[baseline, threshold]
                    row[f'{label}_{threshold:g}'] = next(k for k, v in masks.items() if v[i])
            classification.append(row)
    return transitions, errors, classification


def gzip_csv(path, rows):
    with path.open('wb') as raw, gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as zipped:
        with io.TextIOWrapper(zipped, encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
            writer.writeheader()
            writer.writerows(rows)


def run(results, output, inventory_path=fa.INVENTORY):
    if os.path.lexists(output):
        raise FileExistsError(output)
    receipt_path = results / 'receipt.json'
    if prior.identity(receipt_path)['sha256'] != RECEIPT_SHA:
        raise ValueError('sealed receipt mismatch')
    receipt = json.loads(receipt_path.read_text())
    inventory = prior.identity(inventory_path)
    if inventory['sha256'] != fa.INVENTORY_SHA:
        raise ValueError('inventory hash mismatch')
    offsets = fa.crop_offsets(json.loads(inventory_path.read_text()))
    mapping_path = results / 'bilinear_mapping.npz'
    if prior.identity(mapping_path)['sha256'] != receipt['outputs'][mapping_path.name]:
        raise ValueError('mapping hash mismatch')
    inputs = [inventory, prior.identity(receipt_path), prior.identity(mapping_path),
              prior.identity(__file__), prior.identity(fa.__file__), prior.identity(EVALUATOR),
              prior.identity(prior.__file__)]
    inputs += [prior.identity(results / f'hour_{hour}_arrays.npz') for hour in e.HOURS]
    arrays = prior.read_arrays(results)
    _, _, constraints, _, _, _ = e.score(arrays)
    with np.load(mapping_path, allow_pickle=False) as data:
        mapping = {k: data[k].copy() for k in data.files}
    selected = representatives(arrays)
    point_rows = paths(arrays, mapping, selected, offsets)
    transition_rows, error_rows, classifications = diagnostics(arrays)
    columns = sorted({(r['native_j0_fortran_one_based'] + dj, r['native_i0_fortran_one_based'] + di)
                      for r in point_rows for dj in (0, 1) for di in (0, 1)})
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.mp10-cohorts-', dir=output.parent))
    try:
        fa.write_csv(stage / 'selected_points.csv', point_rows)
        fa.write_csv(stage / 'native_columns.csv', [{'j_fortran': j, 'i_fortran': i} for j, i in columns])
        fa.write_csv(stage / 'transitions.csv', transition_rows)
        fa.write_csv(stage / 'weak_conditional_errors.csv', error_rows)
        gzip_csv(stage / 'classification.csv.gz', classifications)
        summary = {'scope': 'diagnostic only; original 26 admission conditions unchanged',
                   'admission_passed': sum(r['satisfied'] for r in constraints if r['candidate'] == e.NEW),
                   'admission_required': 26, 'capture_points': len(selected), 'native_columns': len(columns),
                   'native_layers': 39, 'crop_to_native_zero_based_offsets': {'i': offsets[1], 'j': offsets[0]},
                   'selection': 'range-scaled L1 medoids; nearest unused same-observed-band resolved controls; angular distance with flat index tie break',
                   'classification': 'every paired point, all six leads and six thresholds; equality is an event'}
        (stage / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        for record in inputs:
            if prior.identity(record['path']) != record:
                raise ValueError('input changed')
        record = {'status': 'COMPLETE', 'inputs': inputs, 'source': prior.identity(__file__),
                  'helper': prior.identity(fa.__file__), 'evaluator': prior.identity(EVALUATOR),
                  'outputs': {p.name: prior.identity(p)['sha256'] for p in sorted(stage.iterdir())}}
        (stage / 'receipt.json').write_text(json.dumps(record, indent=2) + '\n')
        prior.publish_new(stage, output)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--inventory', type=Path, default=fa.INVENTORY)
    args = parser.parse_args()
    print(json.dumps(run(args.results, args.output, args.inventory), indent=2))


if __name__ == '__main__':
    main()
