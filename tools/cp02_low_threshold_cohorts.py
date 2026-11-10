#!/usr/bin/env python3
"""Recount low-threshold transitions and freeze limited native capture points."""
import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile

import numpy as np

import cp02_ice_false_alarm as fa

E = fa.evaluation
ORIGINAL = E.ORIGINAL
THRESHOLDS = (.1, .5, 1.)


def masks(hour, baseline, threshold):
    observed = hour['reference'] >= threshold
    before = hour[baseline] >= threshold
    after = hour[fa.NEW] >= threshold
    return {'new': ~observed & ~before & after,
            'resolved': ~observed & before & ~after,
            'persistent': ~observed & before & after}


def medoid(hour, mask, used):
    """L1 medoid in within-stratum range-scaled location and precipitation."""
    ids = hour['flat_index_yx']
    indices = np.flatnonzero(mask & ~np.isin(ids, list(used)))
    if not len(indices):
        raise ValueError('empty representative stratum')
    fields = ('latitude', 'longitude', 'reference', *fa.CASES)
    x = np.column_stack([hour[field][indices] for field in fields])
    span = np.ptp(x, axis=0)
    x = (x - x.min(axis=0)) / np.where(span == 0, 1, span)
    distance = np.abs(x[:, None, :] - x[None, :, :]).sum(axis=(1, 2))
    return int(ids[indices[np.lexsort((ids[indices], distance))[0]]])


def nearest(hour, mask, target, used):
    ids = hour['flat_index_yx']
    target_index = np.flatnonzero(ids == target)
    if len(target_index) != 1:
        raise ValueError('target identity missing or duplicated')
    i = target_index[0]
    candidates = np.flatnonzero(mask & ~np.isin(ids, list(used)))
    if not len(candidates):
        raise ValueError('empty control stratum')
    lat = np.deg2rad((hour['latitude'][candidates] + hour['latitude'][i]) / 2)
    distance = ((hour['latitude'][candidates] - hour['latitude'][i]) ** 2 +
                ((hour['longitude'][candidates] - hour['longitude'][i]) * np.cos(lat)) ** 2)
    return int(ids[candidates[np.lexsort((ids[candidates], distance))[0]]])


def representatives(arrays):
    h = arrays[18]
    ids = h['flat_index_yx']
    old = np.logical_or.reduce(list(fa.cohort_masks(h).values()))
    new = {t: masks(h, ORIGINAL, t)['new'] for t in THRESHOLDS}
    selected, used = [], set()

    def add(role, point, target=''):
        if point in used:
            raise ValueError('duplicate selected point')
        selected.append((role, point, target))
        used.add(point)

    # Each populated overlap/intensity regime is represented once.
    regimes = ((True, False, .5, 1.), (False, True, 1., 2.5),
               (False, True, 2.5, 5.), (True, True, 1., 2.5),
               (True, True, 2.5, 5.))
    for a, b, lo, hi in regimes:
        mask = ((new[.5] if a else ~new[.5]) & (new[1.] if b else ~new[1.]) &
                ~old & (h[fa.NEW] >= lo) & (h[fa.NEW] < hi))
        add(f'new_h6_05_{int(a)}_1_{int(b)}_pred_{lo:g}_{hi:g}', medoid(h, mask, used))
    # Two 0.1-mm new-FA regimes: with and without a 0.5-mm new FA.
    for overlaps in (False, True):
        mask = new[.1] & (new[.5] if overlaps else ~new[.5]) & ~old
        add(f'new_h6_01_overlap05_{int(overlaps)}', medoid(h, mask, used))
    for t in THRESHOLDS:
        eligible = [point for _, point, _ in selected if new[t][np.flatnonzero(ids == point)[0]]]
        if not eligible:
            raise ValueError('no matched new false alarm')
        target = eligible[0]
        add(f'resolved_h6_{t:g}', nearest(h, masks(h, ORIGINAL, t)['resolved'], target, used), target)
    weak = ((h['reference'] >= .1) & (h['reference'] < 1) &
            np.logical_and.reduce([(h[k] >= .1) & (h[k] < 1) for k in (fa.B1, fa.CONS, fa.NEW)]))
    for lo, hi in ((.1, .5), (.5, 1.)):
        add(f'weak_h6_obs_{lo:g}_{hi:g}', medoid(h, weak & (h['reference'] >= lo) & (h['reference'] < hi), used))
    for role, mask in fa.cohort_masks(h).items():
        add(f'old_h6_{role}', medoid(h, mask, used))
    for role, point, target in fa.members(arrays):
        if role in ('named_new', 'nearest_retained_hit'):
            if point in used:
                raise ValueError('named target or matched control overlaps another selection')
            add(f'h1_{role}', point, target)
    if len(selected) > 24:
        raise ValueError('capture point limit exceeded')
    return selected


def diagnostics(arrays):
    h = arrays[18]
    old_masks = fa.cohort_masks(h)
    old = np.logical_or.reduce(list(old_masks.values()))
    low = {t: masks(h, ORIGINAL, t)['new'] for t in THRESHOLDS}
    union = low[.5] | low[1.]
    rows = []
    for i in np.flatnonzero(old | union):
        row = {'flat_index_yx': int(h['flat_index_yx'][i]),
               **{f'old_{k}': int(v[i]) for k, v in old_masks.items()},
               **{f'original_new_fa_{t:g}': int(low[t][i]) for t in THRESHOLDS},
               'low_05_1_union': int(union[i])}
        for field in ('reference', *fa.CASES):
            row[field] = float(h[field][i])
        rows.append(row)
    counts = {}
    for baseline in (ORIGINAL, fa.B1):
        counts[baseline] = {}
        for t in THRESHOLDS:
            m = masks(h, baseline, t)['new']
            counts[baseline][str(t)] = {'new': int(m.sum()), 'outside_old_128': int((m & ~old).sum()),
                                        'new_candidate_below_5': int((m & (h[fa.NEW] < 5)).sum())}
    counts['union_05_1'] = {'all': int(union.sum()), 'outside_old_128': int((union & ~old).sum())}
    counts['old_128'] = {k: int(v.sum()) for k, v in old_masks.items()}
    return rows, counts


def weak_detection(arrays):
    rows = []
    for hour in fa.HOURS:
        h = arrays[hour]
        for lo, hi in ((.1, .5), (.5, 1.)):
            obs = (h['reference'] >= lo) & (h['reference'] < hi)
            maintained = np.logical_and.reduce([(h[k] >= .1) & (h[k] < 1) for k in (fa.B1, fa.CONS, fa.NEW)])
            for case in fa.CASES:
                pred = h[case]
                rows.append({'lead_hour': hour - 12, 'observation_bin_mm': f'[{lo:g},{hi:g})',
                             'case': case, 'observations': int(obs.sum()),
                             'forecast_below_0.1': int((obs & (pred < .1)).sum()),
                             'forecast_0.1_to_1': int((obs & (pred >= .1) & (pred < 1)).sum()),
                             'forecast_at_least_1': int((obs & (pred >= 1)).sum()),
                             'forecast_at_least_0.1': int((obs & (pred >= .1)).sum()),
                             'all_B1_PR153_PR154_0.1_to_1': int((obs & maintained).sum())})
    return rows


def run(results, output, inventory_path=fa.INVENTORY):
    if os.path.lexists(output):
        raise FileExistsError(output)
    inventory = E.identity(inventory_path)
    if inventory['sha256'] != fa.INVENTORY_SHA:
        raise ValueError('inventory hash mismatch')
    offsets = fa.crop_offsets(json.loads(inventory_path.read_text()))
    receipt = json.loads((results / 'receipt.json').read_text())
    mapping_path = results / 'bilinear_mapping.npz'
    if E.identity(mapping_path)['sha256'] != receipt['outputs']['bilinear_mapping.npz']:
        raise ValueError('mapping hash mismatch')
    inputs = [inventory, E.identity(results / 'receipt.json'), E.identity(mapping_path)]
    inputs += [E.identity(results / f'hour_{h}_arrays.npz') for h in fa.HOURS]
    arrays = E.read_arrays(results)
    _, _, constraints, _ = E.score(arrays)
    if sum(r['satisfied'] for r in constraints if r['candidate'] == fa.NEW) != 21:
        raise ValueError('admission score changed')
    with np.load(mapping_path, allow_pickle=False) as data:
        mapping = {k: data[k].copy() for k in data.files}
    selected = representatives(arrays)
    rows, counts = diagnostics(arrays)
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.low-threshold-stage-', dir=output.parent))
    try:
        fa.write_csv(stage / 'classification.csv', rows)
        fa.write_csv(stage / 'selected_points.csv', fa.paths(arrays, mapping, selected, offsets))
        fa.write_csv(stage / 'lead_bins.csv', fa.intensity_bins(arrays))
        fa.write_csv(stage / 'weak_detection.csv', weak_detection(arrays))
        (stage / 'summary.json').write_text(json.dumps({'counts': counts, 'capture_points': len(selected),
            'admission': '21/26; candidate not adopted', 'native_layers': 39,
            'crop_to_native_zero_based_offsets': {'j': offsets[0], 'i': offsets[1]}}, indent=2) + '\n')
        for record in inputs:
            if E.identity(record['path']) != record:
                raise ValueError('input changed')
        receipt = {'status': 'COMPLETE', 'inputs': inputs, 'source': E.identity(__file__),
                   'helper': E.identity(fa.__file__), 'evaluator': E.identity(fa.EVALUATOR),
                   'outputs': {p.name: E.identity(p)['sha256'] for p in sorted(stage.iterdir())}}
        (stage / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
        E.publish_new(stage, output)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return counts


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--results', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--inventory', type=Path, default=fa.INVENTORY)
    a = p.parse_args()
    print(json.dumps(run(a.results, a.output, a.inventory), indent=2))


if __name__ == '__main__':
    main()
