#!/usr/bin/env python3
"""Independently recount CP02 protected-process cohorts from pinned arrays."""
from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[4]
EVIDENCE = ROOT / 'docs/evidence/cp02_protected_process_20261106'
COHORTS = EVIDENCE / 'cohorts'
OLD_ROOT = ROOT / 'docs/evidence/weak_strong_balance_20261030/analysis'
GROUPED_ROOT = ROOT / 'docs/evidence/cp02_grouped_forecast_20261105/analysis'
TARGETS = ROOT / 'docs/evidence/cp02_failure_focus_20261105/targets'
CONTEXT = ROOT / 'docs/evidence/cp02_failure_focus_20261105/context'
MAPPING = ROOT / 'docs/evidence/cp02_rain_number_process_20261104/followup/analysis_dm065/bilinear_mapping.npz'
THRESHOLDS = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0)
HOURS = tuple(range(13, 19))
EARTH_KM = 6371.0


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline='', encoding='utf-8') as stream:
        return list(csv.DictReader(stream))


def load_npz(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as archive:
        return {key: archive[key].copy() for key in archive.files}


def csi_counts(obs: np.ndarray, pred: np.ndarray, threshold: float) -> dict:
    wet_obs, wet_pred = obs >= threshold, pred >= threshold
    hit = int(np.count_nonzero(wet_obs & wet_pred))
    miss = int(np.count_nonzero(wet_obs & ~wet_pred))
    false = int(np.count_nonzero(~wet_obs & wet_pred))
    correct = int(np.count_nonzero(~wet_obs & ~wet_pred))
    return {'n': int(obs.size), 'hit': hit, 'miss': miss, 'false_alarm': false,
            'correct_negative': correct, 'CSI': hit / (hit + miss + false)}


def transition_counts(obs: np.ndarray, before: np.ndarray, after: np.ndarray, threshold: float) -> dict:
    observed = obs >= threshold
    was, now = before >= threshold, after >= threshold
    return {'observed_points': int(observed.sum()),
            'hit_gains': int(np.count_nonzero(observed & ~was & now)),
            'hit_losses': int(np.count_nonzero(observed & was & ~now)),
            'new_false_alarms': int(np.count_nonzero(~observed & ~was & now)),
            'resolved_false_alarms': int(np.count_nonzero(~observed & was & ~now))}


def distances_km(data: dict[str, np.ndarray], source: int) -> np.ndarray:
    lat = np.radians(data['latitude'])
    lon = np.radians(data['longitude'])
    dlat, dlon = lat - lat[source], lon - lon[source]
    a = np.sin(dlat / 2) ** 2 + np.cos(lat[source]) * np.cos(lat) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def main() -> None:
    receipt = json.loads((COHORTS / 'receipt.json').read_text(encoding='utf-8'))
    plan = json.loads((EVIDENCE / 'analysis_plan.json').read_text(encoding='utf-8'))
    for name, expected in receipt['outputs'].items():
        assert sha256(COHORTS / name) == expected, f'cohort output hash mismatch: {name}'
    for relative, record in receipt['inputs'].items():
        assert sha256(ROOT / relative) == record, f'cohort input hash mismatch: {relative}'

    old = {hour: load_npz(OLD_ROOT / f'hour_{hour}_arrays.npz') for hour in HOURS}
    grouped = {hour: load_npz(GROUPED_ROOT / f'hour_{hour}_arrays.npz') for hour in HOURS}
    flat = old[14]['flat_index_yx'].astype(np.int64)
    assert flat.shape == (3688,) and len(np.unique(flat)) == 3688
    ids_by_role: dict[str, set[int]] = {}
    obs = old[14]['reference']
    original = old[14]['ORIGINAL']
    x = old[14]['ORIGINAL_B1_100']
    a = old[14]['IMPROVED_BG_FIXED']
    weak, dry = (obs >= .1) & (obs < 1.0), obs < .1
    masks = {
        'plus2_XA_weak_gain': weak & (x < .1) & (a >= .1),
        'plus2_XA_weak_loss': weak & (x >= .1) & (a < .1),
        'plus2_OA_weak_loss': weak & (original >= .1) & (a < .1),
        'plus2_XA_new_false_alarm': dry & (x < .1) & (a >= .1),
        'plus2_XA_resolved_false_alarm': dry & (x >= .1) & (a < .1),
        'plus2_OA_new_false_alarm': dry & (original < .1) & (a >= .1),
        'plus2_OA_resolved_false_alarm': dry & (original >= .1) & (a < .1),
    }
    prior_controls = rows(TARGETS / 'matched_controls.csv')
    oa_matches = [row for row in prior_controls if row['cohort_label'] == 'h02_original_A_weak_hit_loss'
                  and row['control_state'] == 'retained_hit' and row['valid_match'] == 'True']
    oa_targets = {int(row['target_flat_index_yx']) for row in oa_matches}
    control_ids = {int(row['control_flat_index_yx']) for row in oa_matches}
    assert len(oa_targets) == len(control_ids) == 10
    assert len({int(row['control_flat_index_yx']) for row in oa_matches}) == 10
    assert oa_targets == set(map(int, flat[masks['plus2_OA_weak_loss']]))
    assert np.all(weak[np.isin(flat, list(control_ids))])
    assert np.all(original[np.isin(flat, list(control_ids))] >= .1)
    assert np.all(a[np.isin(flat, list(control_ids))] >= .1)
    masks['plus2_prior_retained_controls'] = np.isin(flat, list(control_ids))

    g5, o5 = grouped[17], old[17]
    ref5, x5, a5, c5 = g5['reference'], o5['ORIGINAL_B1_100'], g5['A'], g5['C']
    weak5 = (ref5 >= .1) & (ref5 < 1.0) & (a5 >= .1) & (c5 < .1)
    masks['plus5_C_A_weak_loss'] = weak5
    masks['plus5_protected_weak_X_miss_A_hit_C_miss'] = weak5 & (x5 < .1)
    masks['plus5_remaining_weak_loss_X_hit_A_hit_C_miss'] = weak5 & (x5 >= .1)
    masks['plus5_strong_protected_hit_12299'] = ((g5['flat_index_yx'] == 12299) & (ref5 >= 5.0)
                                                 & (x5 < 5.0) & (a5 >= 5.0) & (c5 < 5.0))
    c_fa = (ref5 < 5.0) & (a5 < 5.0) & (c5 >= 5.0)
    masks['plus5_C_strong_new_false_alarm'] = c_fa
    masks['plus5_protected_strong_X_FA_A_resolved_C_FA'] = c_fa & (x5 >= 5.0)
    expected_sets = {role: set(map(int, flat[mask])) for role, mask in masks.items()}

    wet_a = a >= .1
    oa_weak_indices = np.flatnonzero(masks['plus2_OA_weak_loss'])
    xa_weak_indices = np.flatnonzero(masks['plus2_XA_weak_loss'])
    oa_zero_neighbors = set()
    nearest_by_index = {}
    for index in oa_weak_indices:
        distance = distances_km(old[14], int(index))
        candidates = np.flatnonzero(wet_a)
        candidates = candidates[candidates != index]
        nearest = min(map(int, candidates), key=lambda i: (float(distance[i]), int(flat[i])))
        nearest_by_index[int(index)] = (nearest, distance, int(flat[nearest]))
        if obs[nearest] == 0.0:
            oa_zero_neighbors.add(int(flat[nearest]))
    assert oa_zero_neighbors == {8540, 11091, 11092, 11241}
    expected_sets['plus2_OA_nearest_Awet_RN1zero_neighbor'] = oa_zero_neighbors

    membership = rows(COHORTS / 'role_membership.csv')
    actual_sets: dict[str, set[int]] = defaultdict(set)
    for row in membership:
        actual_sets[row['role']].add(int(row['flat_index_yx']))
    assert dict(actual_sets) == expected_sets
    assert len(expected_sets['plus2_XA_weak_loss']) == len(expected_sets['plus2_OA_weak_loss']) == 10
    xa_loss, oa_loss = expected_sets['plus2_XA_weak_loss'], expected_sets['plus2_OA_weak_loss']
    assert len(xa_loss & oa_loss) == 9 and oa_loss - xa_loss == {17524} and xa_loss - oa_loss == {16138}
    assert len(expected_sets['plus2_XA_new_false_alarm']) == 33
    assert len(expected_sets['plus2_XA_resolved_false_alarm']) == 30
    oa_new = expected_sets['plus2_OA_new_false_alarm']
    assert len(oa_new) == 53 and int(np.count_nonzero(np.isin(flat, list(oa_new)) & (x < .1))) == 32
    assert len(expected_sets['plus5_protected_weak_X_miss_A_hit_C_miss']) == 11
    assert expected_sets['plus5_strong_protected_hit_12299'] == {12299}
    assert len(expected_sets['plus5_protected_strong_X_FA_A_resolved_C_FA']) == 7

    point_rows = rows(COHORTS / 'selected_points.csv')
    expected_point_ids = set.union(*expected_sets.values())
    assert {int(row['flat_index_yx']) for row in point_rows} == expected_point_ids
    assert len(point_rows) == len(expected_point_ids) == 150
    role_string = {int(row['flat_index_yx']): set(row['roles'].split(';')) for row in point_rows}
    for role, point_ids in expected_sets.items():
        assert all(role in role_string[point] for point in point_ids)

    mapping = load_npz(MAPPING)
    point_corners = rows(COHORTS / 'point_corners.csv')
    assert len(point_corners) == 600
    assert {int(row['flat_index_yx']) for row in point_corners} == expected_point_ids
    expected_cells = set()
    by_point: dict[int, list[dict]] = defaultdict(list)
    for row in point_corners:
        point = int(row['flat_index_yx'])
        index = int(np.flatnonzero(flat == point)[0])
        y, xidx = divmod(point, 149)
        j, i = int(mapping['j0'][y, xidx]) + 5, int(mapping['i0'][y, xidx]) + 74
        u, v = float(mapping['u'][y, xidx]), float(mapping['v'][y, xidx])
        corners = {'00': (j, i, (1-u)*(1-v)), '10': (j, i+1, u*(1-v)),
                   '01': (j+1, i, (1-u)*v), '11': (j+1, i+1, u*v)}
        cj, ci, weight = corners[row['corner']]
        assert int(row['sample_index_zero_based']) == index
        assert (int(row['native_j_zero_based']), int(row['native_i_zero_based'])) == (cj, ci)
        assert math.isclose(float(row['weight']), weight, rel_tol=0, abs_tol=1e-15)
        assert int(row['wrf_j_1based']) == cj+1 and int(row['wrf_i_1based']) == ci+1
        assert set(row['roles'].split(';')) == role_string[point]
        expected_cells.add((cj, ci))
        by_point[point].append(row)
    assert all(len(rows_) == 4 and math.isclose(sum(float(row['weight']) for row in rows_), 1.0,
                                                   rel_tol=0, abs_tol=1e-12)
               for rows_ in by_point.values())
    unique_rows = rows(COHORTS / 'unique_global_corners.csv')
    assert len(expected_cells) == len(unique_rows) == 381
    assert [(int(row['native_j_zero_based']), int(row['native_i_zero_based'])) for row in unique_rows] == sorted(expected_cells)
    assert [row['global_corner_id'] for row in unique_rows] == [f'GC{k:04d}' for k in range(1, 382)]

    neighbor_rows = rows(COHORTS / 'nearest_neighbors.csv')
    assert len(neighbor_rows) == 20
    neighbor_check = []
    for row in neighbor_rows:
        source = int(row['loss_flat_index_yx'])
        source_i = int(np.flatnonzero(flat == source)[0])
        if row['role'] == 'plus2_OA_weak_loss':
            assert source_i in set(map(int, oa_weak_indices))
        else:
            assert row['role'] == 'plus2_XA_weak_loss' and source_i in set(map(int, xa_weak_indices))
        dist = distances_km(old[14], source_i)
        candidates = np.flatnonzero(wet_a)
        candidates = candidates[candidates != source_i]
        near = min(map(int, candidates), key=lambda i: (float(dist[i]), int(flat[i])))
        assert int(row['nearest_A_hit_flat_index_yx']) == int(flat[near])
        assert math.isclose(float(row['nearest_distance_km']), float(dist[near]), rel_tol=0, abs_tol=1e-12)
        assert float(row['neighbor_reference_mm']) == float(obs[near])
        # Status remains directly recoverable from the explicit nearest sample's RN1 value.
        radius_counts = {radius: (int(np.count_nonzero(dist <= radius)),
                                  int(np.count_nonzero((dist <= radius) & wet_a))) for radius in (5, 10, 20)}
        for radius, (all_count, wet_count) in radius_counts.items():
            assert int(row[f'canonical_points_within_{radius}km']) == all_count
            assert int(row[f'A_hit_points_within_{radius}km']) == wet_count
        assert (row['5km_radius_self_only'] == 'True') == (radius_counts[5][0] == 1)
        neighbor_check.append({'role': row['role'], 'loss_flat_index_yx': source,
                               'nearest_A_hit_flat_index_yx': int(flat[near]),
                               'nearest_observation_mm': float(obs[near]),
                               'nearest_observation_wet_at_0p1': bool(obs[near] >= .1),
                               'distance_km': float(dist[near]), 'radii': radius_counts})
    assert sum(int(row['canonical_points_within_5km']) == 1 for row in neighbor_rows) == 20
    # The finite 3,688-point archive has 3,688 5-km self-only neighborhoods.
    singleton_count = 0
    for index in range(flat.size):
        singleton_count += int(np.count_nonzero(distances_km(old[14], index) <= 5.0) == 1)
    assert singleton_count == receipt['full_grid_5km_singleton_count'] == 3688

    # Independently rejoin layer QRAIN for absolute X/A and pointwise differences.
    qrain_rows = rows(COHORTS / 'qrain_point_contrasts.csv')
    qrain_summary = rows(COHORTS / 'qrain_group_summary.csv')
    layer_rows = rows(CONTEXT / 'layer_features.csv')
    qrain_inputs = {}
    needed = {('plus2_OA_weak_loss', point) for point in oa_loss} | {
        ('plus2_prior_retained_controls', point) for point in control_ids}
    for row in layer_rows:
        key = (row['flat_index_yx'], row['case'])
        if row['hour_utc'] == '13' and row['layer_agl'] == '[0,1000)m' and row['case'] in {'A', 'B1_OLD_KDM6'}:
            for role, point in needed:
                if point == int(row['flat_index_yx']):
                    qrain_inputs[(role, point, row['case'])] = float(row['QRAIN_kgkg']) * 1e6
    assert len(qrain_rows) == 20 and len(needed) == 20
    for row in qrain_rows:
        role, point = row['role'], int(row['flat_index_yx'])
        qx = qrain_inputs[(role, point, 'B1_OLD_KDM6')]
        qa = qrain_inputs[(role, point, 'A')]
        assert float(row['X_QRAIN_mgkg']) == qx and float(row['A_QRAIN_mgkg']) == qa
        assert float(row['pointwise_A_minus_X_mgkg']) == qa - qx
    for summary in qrain_summary:
        group = [row for row in qrain_rows if row['role'] == summary['role']]
        qx = np.asarray([float(row['X_QRAIN_mgkg']) for row in group])
        qa = np.asarray([float(row['A_QRAIN_mgkg']) for row in group])
        assert int(summary['n']) == 10
        assert float(summary['median_X_QRAIN_mgkg']) == float(np.median(qx))
        assert float(summary['median_A_QRAIN_mgkg']) == float(np.median(qa))
        assert float(summary['median_pointwise_A_minus_X_mgkg']) == float(np.median(qa - qx))

    # Independently rebuild every categorical and transition row from arrays.
    score_rows = rows(COHORTS / 'categorical_scores.csv')
    transition_rows = rows(COHORTS / 'transitions.csv')
    assert len(score_rows) == len(transition_rows) == 180
    pairs = ('ORIGINAL_to_FIX', 'X_to_A', 'ORIGINAL_to_A', 'C_to_A', 'A_to_C')
    for hour in HOURS:
        old_hour, group_hour = old[hour], grouped[hour]
        pair_data = {
            'ORIGINAL_to_FIX': (old_hour['ORIGINAL'], old_hour['FIXED_ORIGINAL_100'], old_hour['FIXED_ORIGINAL_100']),
            'X_to_A': (old_hour['ORIGINAL_B1_100'], old_hour['IMPROVED_BG_FIXED'], old_hour['IMPROVED_BG_FIXED']),
            'ORIGINAL_to_A': (old_hour['ORIGINAL'], old_hour['IMPROVED_BG_FIXED'], old_hour['IMPROVED_BG_FIXED']),
            'C_to_A': (group_hour['C'], group_hour['A'], group_hour['A']),
            'A_to_C': (group_hour['A'], group_hour['C'], group_hour['C']),
        }
        for pair in pairs:
            before, after, forecast = pair_data[pair]
            for threshold in THRESHOLDS:
                key = (hour, pair, threshold)
                score_row = next(row for row in score_rows if (int(row['valid_hour_utc']), row['comparison'], float(row['threshold_mm'])) == key)
                transition_row = next(row for row in transition_rows if (int(row['valid_hour_utc']), row['comparison'], float(row['threshold_mm'])) == key)
                for name, value in csi_counts(old_hour['reference'], forecast, threshold).items():
                    assert math.isclose(float(score_row[name]), value, rel_tol=0, abs_tol=1e-15), (key, name)
                for name, value in transition_counts(old_hour['reference'], before, after, threshold).items():
                    assert int(transition_row[name]) == value, (key, name)

    result = {
        'status': 'PASS_INDEPENDENT_COHORT_AND_SCORE_RECOUNT',
        'cohort_receipt_sha256': sha256(COHORTS / 'receipt.json'),
        'analysis_plan_sha256': sha256(EVIDENCE / 'analysis_plan.json'),
        'output_sha256': receipt['outputs'],
        'checks': {
            'all_output_and_input_hashes_match_receipt': True,
            'all_15_role_sets_recounted_from_frozen_arrays': True,
            'OA_XA_weak_loss_overlap': 9,
            'OA_only_weak_loss': [17524],
            'XA_only_weak_loss': [16138],
            'whole_XA_false_alarm_new_resolved': [33, 30],
            'conditional_ORIGINAL_A_new_false_alarms': 53,
            'X_below_threshold_in_conditional_53': 32,
            'protected_plus5_counts_weak_strong_false_alarm': [11, 1, 7],
            'prior_OA_target_control_bindings': {'targets': sorted(oa_targets), 'controls': sorted(control_ids)},
            'nearest_neighbor_rows': neighbor_check,
            'nearest_sample_status_source_field': 'neighbor_reference_mm; wet event iff >= 0.1 mm',
            'neighborhood_radii_checked_km': [5, 10, 20],
            'full_grid_5km_self_only_neighborhoods': singleton_count,
            'point_corner_contract': {'points': 150, 'corners': 600, 'deduplicated_native_columns': 381},
            'qrain': [{'role': row['role'], 'n': int(row['n']),
                       'median_X_QRAIN_mgkg': float(row['median_X_QRAIN_mgkg']),
                       'median_A_QRAIN_mgkg': float(row['median_A_QRAIN_mgkg']),
                       'median_pointwise_A_minus_X_mgkg': float(row['median_pointwise_A_minus_X_mgkg'])}
                      for row in qrain_summary],
            'categorical_and_transition_rows_recounted': 180,
        },
        'limitations': [
            'The cohort and score recounts use the frozen 3,688-point hourly arrays and source-bound match table.',
            'Nearest-sample observed status is read from the exact paired RN1 observation; neighborhood populations are only the archived canonical points.',
            'Corner stencils reuse the pinned mapping; no native process state is inferred before the protected run.',
            'These recounts do not establish process causality or new candidate skill.',
        ],
    }
    out = EVIDENCE / 'review/cohort_independent_recount.json'
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps({'status': result['status'], 'points': 150, 'corners': 600, 'native_columns': 381,
                      'roles': len(expected_sets), 'neighbors': len(neighbor_rows),
                      'score_rows': 180, 'transition_rows': 180,
                      'OA_only': [17524], 'XA_only': [16138], 'prior_controls': len(control_ids)}, indent=2))


if __name__ == '__main__':
    main()
