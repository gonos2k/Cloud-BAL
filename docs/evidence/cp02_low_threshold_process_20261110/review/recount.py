#!/usr/bin/env python3
"""Independent recount of saved evaluation points, with paired weak-rain changes."""
import hashlib
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[4]
RESULTS = ROOT / 'docs/evidence/cp02_first_ice_velocity_20261109/evaluation/results'
CASES = {'O': 'ORIGINAL', 'B1': 'IMPROVED_BG_FIXED',
         'C': 'CONSERVATIVE_SEDIMENTATION', 'I': 'FIRST_ICE_VELOCITY'}

def load(hour):
    path = RESULTS / f'hour_{hour + 12}_arrays.npz'
    with np.load(path, allow_pickle=False) as data:
        arrays = {key: data[value].copy() for key, value in CASES.items()}
        arrays['obs'] = data['reference'].copy()
    return arrays, hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    hours, hashes = {}, {}
    for hour in (3, 6):
        hours[hour], hashes[str(hour)] = load(hour)
    a = hours[6]
    obs, b, c, ice = a['obs'], a['B1'], a['C'], a['I']
    old = (obs < 5) & (b < 5) & ((c >= 5) | (ice >= 5))
    false_alarms = {}
    for baseline in ('O', 'B1', 'C'):
        masks = {}
        for threshold in (.1, .5, 1.):
            mask = (obs < threshold) & (a[baseline] < threshold) & (ice >= threshold)
            masks[threshold] = mask
            false_alarms[f'{baseline}_to_I_{threshold:g}'] = {
                'gained': int(mask.sum()), 'outside_old_128': int((mask & ~old).sum()),
                'I_below_5': int((mask & (ice < 5)).sum())}
        mask = masks[.5] | masks[1.]
        false_alarms[f'{baseline}_to_I_union_0.5_1'] = {
            'gained': int(mask.sum()), 'outside_old_128': int((mask & ~old).sum()),
            'I_below_5': int((mask & (ice < 5)).sum())}
    weak = {}
    for hour, values in hours.items():
        obs, ice = values['obs'], values['I']
        eligible = (obs >= .1) & (obs < 1)
        weak[str(hour)] = {'observations': int(eligible.sum())}
        for baseline in ('O', 'B1', 'C'):
            before = values[baseline]
            both = eligible & (before >= .1) & (ice >= .1)
            difference = ice[both] - before[both]
            weak[str(hour)][baseline] = {
                'both_detect': int(both.sum()), 'intensity_declines': int((difference < 0).sum()),
                'intensity_increases': int((difference > 0).sum()),
                'intensity_equal': int((difference == 0).sum()),
                'median_I_minus_baseline_mm': float(np.median(difference)),
                'detection_gained': int((eligible & (before < .1) & (ice >= .1)).sum()),
                'detection_lost': int((eligible & (before >= .1) & (ice < .1)).sum())}
    out = {'input_sha256_by_lead': hashes, 'old_group_count': int(old.sum()),
           'old_group_definition': 'obs<5 and B1<5 and (C>=5 or I>=5), h6',
           'false_alarm_definition': 'obs<threshold and baseline<threshold and I>=threshold, h6',
           'weak_definition': '0.1<=obs<1; both baseline and I >=0.1 for paired intensity',
           'false_alarm_gains': false_alarms, 'weak_observations': weak}
    print(json.dumps(out, indent=2))

if __name__ == '__main__':
    main()
