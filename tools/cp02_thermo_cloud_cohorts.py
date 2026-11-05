#!/usr/bin/env python3
"""Reconstruct and freeze the 39-point CP02 thermodynamic trace cohort."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
COHORTS = ROOT / 'docs/evidence/cp02_thermo_cloud_path_20261105/cohorts'
PROTOCOL = COHORTS / 'protocol.json'
PROTOCOL_SHA = 'ffc56783af42f3c0e072321249da1c7346071aca3311d2eb502b0997e2861ad9'
ANALYSIS = ROOT / 'docs/evidence/cp02_rain_number_process_20261104/followup/analysis_dm065'
STATE = ROOT / 'docs/evidence/cp02_failure_regimes_20261104/state/results'
PREVIOUS = ROOT / 'docs/evidence/cp02_failure_regimes_20261104/science/local_initial_change.csv'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def inputs():
    if sha(PROTOCOL) != PROTOCOL_SHA:
        raise ValueError('cohort protocol is not the frozen preselection version')
    protocol = json.loads(PROTOCOL.read_text())
    if protocol['status'] != 'FROZEN_BEFORE_SELECTION' or protocol['expected_total_points'] != 39:
        raise ValueError('incorrect selection protocol')
    for name, expected in protocol['input_sha256'].items():
        if sha(ROOT / name) != expected:
            raise ValueError(f'input SHA mismatch: {name}')
    def load(path):
        with np.load(path, allow_pickle=False) as data:
            return {k: data[k].copy() for k in data.files}
    return load(ANALYSIS / 'hour_14_arrays.npz'), load(ANALYSIS / 'bilinear_mapping.npz'), load(STATE / 'B1_input.npz'), load(STATE / 'DM065_input.npz')


def native_corners(values, mapping):
    flat = values['flat_index_yx']; y, x = np.divmod(flat, 149)
    if flat.shape != (3688,) or len(np.unique(flat)) != 3688 or np.any(y < 0) or np.any(y >= 253) or not mapping['valid'][y, x].all():
        raise ValueError('invalid canonical samples or mapping')
    j, i = mapping['j0'][y, x] + 5, mapping['i0'][y, x] + 74
    u, v = mapping['u'][y, x], mapping['v'][y, x]
    jj = np.stack((j, j, j + 1, j + 1), axis=-1); ii = np.stack((i, i + 1, i, i + 1), axis=-1)
    weights = np.stack(((1-u)*(1-v), u*(1-v), (1-u)*v, u*v), axis=-1)
    if np.any(jj < 0) or np.any(jj >= 282) or np.any(ii < 0) or np.any(ii >= 234) or not np.isfinite(weights).all() or np.any(weights < 0) or not np.allclose(weights.sum(axis=1), 1, rtol=0, atol=1e-12):
        raise ValueError('invalid native stencil or weights')
    return jj, ii, weights


def choose_controls(values, lost, retained):
    """Greedy geographic comparator for each loss, sorted by canonical flat ID."""
    flat = values['flat_index_yx']; lat = np.radians(values['latitude']); lon = np.radians(values['longitude'])
    remaining = set(int(i) for i in np.flatnonzero(retained)); pairs = []
    for source in sorted(map(int, np.flatnonzero(lost)), key=lambda i: int(flat[i])):
        def rank(i):
            dlat = lat[i] - lat[source]; dlon = lon[i] - lon[source]
            hav = np.sin(dlat / 2)**2 + np.cos(lat[source]) * np.cos(lat[i]) * np.sin(dlon / 2)**2
            return float(hav), int(flat[i])
        if not remaining:
            raise ValueError('not enough retained geographic comparators')
        target = min(remaining, key=rank); remaining.remove(target)
        distance = 2 * 6371.0 * np.arcsin(np.sqrt(min(1.0, max(0.0, rank(target)[0]))))
        pairs.append((source, target, float(distance)))
    return pairs


def select(values, mapping, b1_state, dm_state):
    jj, ii, weights = native_corners(values, mapping)
    for state in (b1_state, dm_state):
        if not np.array_equal(state['flat_index_yx'], values['flat_index_yx']) or not np.array_equal(state['native_j_zero_based'], jj) or not np.array_equal(state['native_i_zero_based'], ii) or not np.array_equal(state['corner_weights'], weights):
            raise ValueError('native source mappings differ from paired sample identity')
    b1 = b1_state['corner_qnrain_per_kg']; dm = dm_state['corner_qnrain_per_kg']
    if b1.shape != (3688, 39, 4) or dm.shape != b1.shape or not np.isfinite(b1).all() or not np.isfinite(dm).all():
        raise ValueError('invalid initial native corner NR values')
    unchanged = np.all((b1 == dm) | (weights[:, None, :] == 0), axis=(1, 2))
    obs, old, new = values['reference'], values['IMPROVED_BG_FIXED'], values['B1_RAIN_NUMBER_DM065']
    if any(a.shape != (3688,) or not np.isfinite(a).all() for a in (obs, old, new, values['latitude'], values['longitude'])):
        raise ValueError('nonfinite or incomplete paired sample')
    masks = {'new_fa_initial_nr_unchanged': (obs < .1) & (old < .1) & (new >= .1) & unchanged,
             'removed_fa_initial_nr_unchanged': (obs < .1) & (old >= .1) & (new < .1) & unchanged,
             'weak_lost': (obs >= .1) & (obs < 1) & (old >= .1) & (new < .1)}
    if [int(m.sum()) for m in masks.values()] != [15, 12, 6]:
        raise ValueError('recounted focus cohort does not meet frozen expected group sizes')
    retained = (obs >= .1) & (obs < 1) & (old >= .1) & (new >= .1)
    pairs = choose_controls(values, masks['weak_lost'], retained)
    groups = []
    for group, prefix in (('new_fa_initial_nr_unchanged', 'NFA'), ('removed_fa_initial_nr_unchanged', 'RFA'), ('weak_lost', 'WLOST')):
        selected = sorted(map(int, np.flatnonzero(masks[group])), key=lambda i: int(values['flat_index_yx'][i]))
        for k, i in enumerate(selected, 1): groups.append((f'{prefix}{k:02d}', group, i, '', ''))
    for k, (source, target, distance) in enumerate(pairs, 1):
        groups.append((f'WCTRL{k:02d}', 'weak_retained_nearest_control', target, int(values['flat_index_yx'][source]), distance))
    selected_flat = [int(values['flat_index_yx'][g[2]]) for g in groups]
    if len(groups) != 39 or len(set(selected_flat)) != 39 or not {17051, 20183}.issubset(set(selected_flat[:15])):
        raise ValueError('selected identities violate frozen protocol')
    with PREVIOUS.open(newline='', encoding='utf-8') as stream: old_rows = list(csv.DictReader(stream))
    for group, prefix, transition in (('new_fa_initial_nr_unchanged', 'lead2_false_alarm', 'new_false_alarm'), ('removed_fa_initial_nr_unchanged', 'lead2_false_alarm', 'removed_false_alarm'), ('weak_lost', 'lead2_weak', 'lost_hit')):
        prior_set = {int(row['flat_index_yx']) for row in old_rows if row['focus_group'] == prefix and row['transition'] == transition and (group == 'weak_lost' or row['initial_nr_changed'] == 'False')}
        actual_set = {int(values['flat_index_yx'][i]) for _, name, i, _, _ in groups if name == group}
        if prior_set != actual_set: raise ValueError(f'PR147 group does not match independent recount: {group}')
    return groups, jj, ii, weights


def write_csv(path, rows):
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0]); writer.writeheader(); writer.writerows(rows)


def run(output):
    output = Path(output)
    if output.exists() or output.is_symlink(): raise FileExistsError(output)
    values, mapping, b1, dm = inputs(); groups, jj, ii, weights = select(values, mapping, b1, dm)
    cells = sorted({(int(jj[i, c]), int(ii[i, c])) for _, _, i, _, _ in groups for c in range(4)})
    cell_ids = {cell: f'GC{k:03d}' for k, cell in enumerate(cells, 1)}
    points, corners = [], []
    for point_id, group, i, matched, distance in groups:
        points.append({'point_id': point_id, 'group': group, 'sample_index_zero_based': i, 'flat_index_yx': int(values['flat_index_yx'][i]), 'latitude': float(values['latitude'][i]), 'longitude': float(values['longitude'][i]), 'reference_mm': float(values['reference'][i]), 'B1_mm': float(values['IMPROVED_BG_FIXED'][i]), 'DM065_mm': float(values['B1_RAIN_NUMBER_DM065'][i]), 'matched_lost_flat_index': matched, 'great_circle_distance_km': distance})
        for c in range(4):
            j, k = int(jj[i, c]), int(ii[i, c]); corners.append({'point_id': point_id, 'corner': ('00','10','01','11')[c], 'global_corner_id': cell_ids[j, k], 'native_j_zero_based': j, 'native_i_zero_based': k, 'wrf_j_1based': j+1, 'wrf_i_1based': k+1, 'weight': float(weights[i, c])})
    unique = [{'global_corner_id': cell_ids[j, i], 'native_j_zero_based': j, 'native_i_zero_based': i, 'wrf_j_1based': j+1, 'wrf_i_1based': i+1} for j, i in cells]
    output.parent.mkdir(parents=True, exist_ok=True); stage = Path(tempfile.mkdtemp(prefix='.cohort-stage-', dir=output.parent))
    try:
        for name, rows in (('selected_points.csv', points), ('point_corners.csv', corners), ('unique_global_corners.csv', unique)): write_csv(stage / name, rows)
        receipt = {'status': 'COMPLETE', 'protocol_sha256': sha(PROTOCOL), 'points': len(points), 'point_corner_rows': len(corners), 'unique_global_cells': len(cells), 'deduplicated_overlap_count': len(corners)-len(cells), 'outputs': {p.name: sha(p) for p in sorted(stage.iterdir())}}
        (stage/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n'); stage.rename(output)
    finally:
        if stage.exists(): shutil.rmtree(stage)
    return receipt


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=COHORTS/'results');args=parser.parse_args();print(json.dumps(run(args.output),indent=2))


if __name__ == '__main__': main()
