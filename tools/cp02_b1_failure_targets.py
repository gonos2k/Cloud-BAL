#!/usr/bin/env python3
"""Derive point-level failure targets from the sealed grouped-forecast arrays."""
from __future__ import annotations

import argparse
import csv
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'docs/evidence/cp02_grouped_forecast_20261105/analysis'
PLAN = ROOT / 'docs/evidence/cp02_failure_focus_20261105/analysis_plan.json'
PLAN_SHA256 = 'bc33612e6d719791034d72a7de3e4ddfa09b81d66a9c1b73a8a7fffe668eb0d2'
OUTPUT = ROOT / 'docs/evidence/cp02_failure_focus_20261105/targets'
CASES = ('ORIGINAL', 'A', 'B', 'C', 'D')
PAIR_CASES = ('ORIGINAL', 'A', 'C', 'D')
LEADS = tuple(range(1, 7))
HOURS = tuple(range(13, 19))
THRESHOLDS = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0)
BANDS = ('[0,0.1)', '[0.1,1)', '[1,5)', '[5,infinity)')
RADII_KM = (5.0, 10.0, 20.0)
EARTH_RADIUS_KM = 6371.0
ARRAY_KEYS = (*CASES, 'reference', 'latitude', 'longitude', 'flat_index_yx')


class TargetError(ValueError):
    """Invalid or incomplete source data for the failure-target analysis."""


def file_identity(path: Path) -> dict:
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return {'path': str(path), 'sha256': digest.hexdigest(), 'size_bytes': Path(path).stat().st_size}


def load_bundle(source: Path = SOURCE) -> tuple[dict, dict[int, dict]]:
    source = Path(source)
    if file_identity(PLAN)['sha256'] != PLAN_SHA256:
        raise TargetError('frozen failure-focus plan SHA differs')
    plan = json.loads(PLAN.read_text(encoding='utf-8'))
    if plan.get('status') != 'FROZEN_DIAGNOSTIC_SCOPE' or plan.get('schema') != 'cp02_b1_failure_focus_plan_v1':
        raise TargetError('failure-focus plan is not frozen')
    receipt_path = source / 'receipt.json'
    if not receipt_path.is_file():
        raise TargetError(f'missing source receipt: {receipt_path}')
    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    if (receipt.get('status') != 'COMPLETE' or receipt.get('schema') != 'cp02_grouped_forecast_result_v1'
        or receipt.get('hours_utc') != list(HOURS) or receipt.get('lead_hours') != list(LEADS)
        or receipt.get('points_per_hour') != 3688 or receipt.get('thresholds_mm') != list(THRESHOLDS)
        or set(receipt.get('cases', ())) != set(CASES)):
        raise TargetError('source receipt inventory is not the complete frozen six-lead comparison')
    receipt_identity = file_identity(receipt_path)
    pinned_receipt = plan['sources']['analysis_receipt']
    if (receipt_identity['sha256'] != pinned_receipt['sha256'] or
        receipt_identity['size_bytes'] != pinned_receipt['size_bytes']):
        raise TargetError('source receipt differs from frozen plan pin')
    records = receipt.get('outputs', {})
    plan_arrays = {Path(item['path']).name: item for item in plan['sources']['analysis_outputs']}
    hourly = {}
    baseline = None
    for hour in HOURS:
        name = f'hour_{hour}_arrays.npz'
        record = records.get(name)
        path = source / name
        if not isinstance(record, dict) or not path.is_file():
            raise TargetError(f'missing receipt-bound source array: {name}')
        actual = file_identity(path)
        if (actual['sha256'] != record.get('sha256') or
            actual['size_bytes'] != record.get('size_bytes', record.get('size'))):
            raise TargetError(f'source array identity differs from receipt: {name}')
        pinned = plan_arrays.get(name, {})
        if actual['sha256'] != pinned.get('sha256') or actual['size_bytes'] != pinned.get('size_bytes'):
            raise TargetError(f'source array differs from frozen plan pin: {name}')
        with np.load(path, allow_pickle=False) as archive:
            if set(archive.files) != set(ARRAY_KEYS):
                raise TargetError(f'{name}: array member inventory differs')
            data = {key: np.array(archive[key], copy=True) for key in ARRAY_KEYS}
        if any(value.shape != (3688,) for value in data.values()):
            raise TargetError(f'{name}: expected six arrays of 3688 paired values')
        if any(not np.isfinite(data[key]).all() for key in (*CASES, 'reference', 'latitude', 'longitude')):
            raise TargetError(f'{name}: nonfinite forecast, observation, or coordinate')
        point_keys = data['flat_index_yx']
        if (not np.issubdtype(point_keys.dtype, np.integer) or np.unique(point_keys).size != 3688
            or np.any(point_keys < 0) or np.any(point_keys >= 253 * 149)):
            raise TargetError(f'{name}: invalid or duplicate flat_index_yx keys')
        if any(np.any(data[key] < 0) for key in (*CASES, 'reference')):
            raise TargetError(f'{name}: negative precipitation')
        identity = tuple(data[key] for key in ('flat_index_yx', 'latitude', 'longitude'))
        if baseline is None:
            baseline = tuple(value.copy() for value in identity)
        elif any(not np.array_equal(a, b) for a, b in zip(baseline, identity)):
            raise TargetError(f'{name}: cross-lead point ordering or coordinates differ')
        hourly[hour] = data
    return receipt, hourly


def observed_band(values: np.ndarray) -> np.ndarray:
    return np.asarray(BANDS)[np.searchsorted((0.1, 1.0, 5.0), values, side='right')]


def haversine_km(lat1, lon1, lat2, lon2) -> np.ndarray:
    lat1, lon1, lat2, lon2 = (np.radians(value) for value in (lat1, lon1, lat2, lon2))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def _add_label(labels: dict[int, set[str]], index: int, label: str) -> None:
    labels.setdefault(index, set()).add(label)


def _transition(reference, baseline, candidate, threshold):
    observed = reference >= threshold
    old, new = baseline >= threshold, candidate >= threshold
    return observed, old, new


def _indices(mask: np.ndarray, keys: np.ndarray) -> list[int]:
    return [int(value) for value in keys[mask]]


def derive_targets(hourly: dict[int, dict]) -> dict[str, list[dict]]:
    """Build deterministic, point-keyed diagnostic tables from the complete arrays."""
    labels: dict[int, set[str]] = {}
    cases: dict[int, dict] = {}
    counts = []
    event_rows = []
    target_spec = (
        (2, 0.1, 'ORIGINAL', 'A', '[0.1,1)', 'lost_hit', 'h02_original_A_weak_hit_loss'),
        (2, 0.1, 'ORIGINAL', 'A', '[0.1,1)', 'gained_hit', 'h02_original_A_weak_hit_gain'),
        (2, 0.1, 'ORIGINAL', 'A', '[0,0.1)', 'new_false_alarm', 'h02_original_A_new_FA'),
        (2, 0.1, 'ORIGINAL', 'A', '[0,0.1)', 'removed_false_alarm', 'h02_original_A_resolved_FA'),
        (5, 5.0, 'A', 'C', '[0,0.1)', 'new_false_alarm', 'h05_A_C_5mm_new_FA_dry'),
        (5, 5.0, 'A', 'C', None, 'new_false_alarm', 'h05_A_C_5mm_new_FA'),
        (5, 5.0, 'A', 'C', '[0.1,1)', 'new_false_alarm', 'h05_A_C_5mm_new_FA_weak'),
        (5, 5.0, 'A', 'C', '[1,5)', 'new_false_alarm', 'h05_A_C_5mm_new_FA_1to5'),
        (5, 5.0, 'A', 'C', '[0,0.1)', 'removed_false_alarm', 'h05_A_C_5mm_resolved_FA'),
        (5, 5.0, 'A', 'C', '[5,infinity)', 'lost_hit', 'h05_A_C_5mm_hit_loss'),
        (5, 5.0, 'A', 'C', '[5,infinity)', 'gained_hit', 'h05_A_C_5mm_hit_gain'),
    )
    for hour, data in hourly.items():
        lead, keys = hour - 12, data['flat_index_yx']
        bands = observed_band(data['reference'])
        for i, key in enumerate(keys):
            cases[int(key)] = {'flat_index_yx': int(key), 'point_index': i,
                               'latitude': float(data['latitude'][i]), 'longitude': float(data['longitude'][i]),
                               'observed_band': str(bands[i])}
        for lead_i, threshold, old_case, new_case, band, transition, group in target_spec:
            if lead != lead_i:
                continue
            observed, old, new = _transition(data['reference'], data[old_case], data[new_case], threshold)
            if transition == 'lost_hit':
                mask = observed & old & ~new
            elif transition == 'gained_hit':
                mask = observed & ~old & new
            elif transition == 'new_false_alarm':
                mask = ~observed & ~old & new
            else:
                mask = ~observed & old & ~new
            if band is not None:
                mask &= bands == band
            ids = _indices(mask, keys)
            for key in ids:
                _add_label(labels, key, group)
            for i in np.flatnonzero(mask):
                event_rows.append({'flat_index_yx': int(keys[i]), 'cohort_label': group,
                                   'lead_hour': lead, 'threshold_mm': threshold,
                                   'baseline_case': old_case, 'candidate_case': new_case,
                                   'reference_mm': float(data['reference'][i]),
                                   'baseline_mm': float(data[old_case][i]), 'candidate_mm': float(data[new_case][i]),
                                   'observed_band': str(bands[i]), 'transition': transition})
        if lead == 2:
            weak = (data['reference'] >= .1) & (data['reference'] < 1.)
            original_a_lost = weak & (data['ORIGINAL'] >= .1) & (data['A'] < .1)
            c_recovers = original_a_lost & (data['C'] >= .1)
            for group, mask in (('h02_loss_recovered_by_C', c_recovers),
                                ('h02_loss_unrecovered_by_C', original_a_lost & ~c_recovers)):
                ids = _indices(mask, keys)
                for key in ids:
                    _add_label(labels, key, group)
                for i in np.flatnonzero(mask):
                    event_rows.append({'flat_index_yx': int(keys[i]), 'cohort_label': group,
                                       'lead_hour': lead, 'threshold_mm': .1,
                                       'baseline_case': 'A', 'candidate_case': 'C',
                                       'reference_mm': float(data['reference'][i]),
                                       'baseline_mm': float(data['A'][i]), 'candidate_mm': float(data['C'][i]),
                                       'observed_band': str(bands[i]),
                                       'transition': 'gained_hit' if c_recovers[i] else 'both_miss'})
        if lead in (2, 5, 6):
            for threshold, old_case, new_case, tag in (
                (0.1, 'ORIGINAL', 'A', 'h2_original_to_A_weak'),
                (0.1, 'A', 'C', f'h{lead}_A_to_C_weak'),
            ):
                if lead == 2 and tag.startswith('h5') or lead != 2 and tag == 'h2_original_to_A_weak':
                    continue
                if lead == 5 and threshold == .1 or lead == 6 and threshold == .1:
                    obs, old, new = _transition(data['reference'], data[old_case], data[new_case], threshold)
                    weak = (data['reference'] >= .1) & (data['reference'] < 1.0)
                    for state, mask in (('lost_hit', weak & old & ~new), ('gained_hit', weak & ~old & new)):
                        group_state = {'lost_hit': 'hit_loss', 'gained_hit': 'hit_gain'}.get(state, state)
                        group = f'h{lead:02d}_A_C_weak_{group_state}'
                        ids = _indices(mask, keys)
                        for key in ids:
                            _add_label(labels, key, group)
                        for i in np.flatnonzero(mask):
                            event_rows.append({'flat_index_yx': int(keys[i]), 'cohort_label': group,
                                               'lead_hour': lead, 'threshold_mm': .1,
                                               'baseline_case': old_case, 'candidate_case': new_case,
                                               'reference_mm': float(data['reference'][i]),
                                               'baseline_mm': float(data[old_case][i]),
                                               'candidate_mm': float(data[new_case][i]),
                                               'observed_band': str(bands[i]), 'transition': group_state})
        # Transition census rows for the exact target comparisons and all requested leads.
        comparisons = [(2, .1, 'ORIGINAL', 'A'), (5, 5., 'A', 'C'), (5, .1, 'A', 'C'), (6, .1, 'A', 'C')]
        for wanted_lead, threshold, old_case, new_case in comparisons:
            if lead != wanted_lead:
                continue
            obs, old, new = _transition(data['reference'], data[old_case], data[new_case], threshold)
            names = ('retained_hit', 'lost_hit', 'gained_hit', 'both_miss', 'retained_false_alarm',
                     'removed_false_alarm', 'new_false_alarm', 'retained_correct_negative')
            masks = (obs & old & new, obs & old & ~new, obs & ~old & new, obs & ~old & ~new,
                     ~obs & old & new, ~obs & old & ~new, ~obs & ~old & new, ~obs & ~old & ~new)
            for name, mask in zip(names, masks):
                for band in BANDS:
                    counts.append({'lead_hour': lead, 'valid_hour_utc': hour, 'threshold_mm': threshold,
                                   'baseline_case': old_case, 'candidate_case': new_case,
                                   'observed_band': band, 'transition': name,
                                   'count': int(np.count_nonzero(mask & (bands == band)))})

    # Match one unused stable control in the same observed band for each unique target.
    membership_ids = sorted(labels)
    control_links = []
    reserved: dict[tuple[str, str, str], set[int]] = {}
    for target_id in membership_ids:
        target_labels = sorted(labels[target_id])
        row = cases[target_id]
        for group in target_labels:
            if group.startswith('control_for:'):
                continue
            if group.startswith('h02_original_A_weak_hit_'):
                lead, threshold, old_case, new_case, control_state = 2, .1, 'ORIGINAL', 'A', 'retained_hit'
            elif group.startswith('h02_loss_'):
                lead, threshold, old_case, new_case, control_state = 2, .1, 'ORIGINAL', 'A', 'retained_hit'
            elif group.startswith('h02_original_A_'):
                lead, threshold, old_case, new_case, control_state = 2, .1, 'ORIGINAL', 'A', 'retained_correct_negative'
            elif group.startswith('h05_A_C_5mm_new_FA') or group.startswith('h05_A_C_5mm_resolved_FA'):
                lead, threshold, old_case, new_case, control_state = 5, 5., 'A', 'C', 'retained_correct_negative'
            elif group.startswith('h05_A_C_5mm_'):
                lead, threshold, old_case, new_case, control_state = 5, 5., 'A', 'C', 'retained_hit'
            else:
                lead, threshold, old_case, new_case, control_state = int(group[1:3]), .1, 'A', 'C', 'retained_hit'
            data = hourly[12 + lead]
            obs, old, new = _transition(data['reference'], data[old_case], data[new_case], threshold)
            stable = obs & old & new if control_state == 'retained_hit' else ~obs & ~old & ~new
            ti = int(np.flatnonzero(data['flat_index_yx'] == target_id)[0])
            target_band = str(observed_band(data['reference'])[ti])
            same_band = observed_band(data['reference']) == target_band
            candidate_ids = np.flatnonzero(stable & same_band & (data['flat_index_yx'] != target_id))
            slot = (group, control_state, target_band)
            used = reserved.setdefault(slot, set())
            candidate_ids = [i for i in candidate_ids if int(data['flat_index_yx'][i]) not in used]
            if not candidate_ids:
                control_links.append({'target_flat_index_yx': target_id, 'cohort_label': group,
                                      'control_flat_index_yx': None, 'control_state': control_state,
                                      'lead_hour': lead, 'threshold_mm': threshold,
                                      'baseline_case': old_case, 'candidate_case': new_case,
                                      'observed_band': target_band,
                                      'target_reference_mm': float(data['reference'][ti]),
                                      'target_baseline_mm': float(data[old_case][ti]),
                                      'target_candidate_mm': float(data[new_case][ti]),
                                      'control_reference_mm': None, 'control_baseline_mm': None,
                                      'control_candidate_mm': None, 'distance_km': None,
                                      'valid_match': False})
                continue
            distances = haversine_km(data['latitude'][ti], data['longitude'][ti],
                                     data['latitude'][candidate_ids], data['longitude'][candidate_ids])
            order = np.lexsort((data['flat_index_yx'][candidate_ids], distances))
            ci = int(candidate_ids[int(order[0])])
            control_id = int(data['flat_index_yx'][ci])
            used.add(control_id)
            control_links.append({'target_flat_index_yx': target_id, 'cohort_label': group,
                                  'control_flat_index_yx': control_id, 'control_state': control_state,
                                  'lead_hour': lead, 'threshold_mm': threshold,
                                  'baseline_case': old_case, 'candidate_case': new_case,
                                  'observed_band': target_band,
                                  'target_reference_mm': float(data['reference'][ti]),
                                  'target_baseline_mm': float(data[old_case][ti]),
                                  'target_candidate_mm': float(data[new_case][ti]),
                                  'control_reference_mm': float(data['reference'][ci]),
                                  'control_baseline_mm': float(data[old_case][ci]),
                                  'control_candidate_mm': float(data[new_case][ci]),
                                  'distance_km': float(distances[int(order[0])]), 'valid_match': True})
            _add_label(labels, control_id, f'control_for:{group}')
            cases.setdefault(control_id, {'flat_index_yx': control_id, 'point_index': ci,
                                          'latitude': float(data['latitude'][ci]),
                                          'longitude': float(data['longitude'][ci]),
                                          'observed_band': str(observed_band(data['reference'])[ci])})
    focus_rows = []
    for key in sorted(labels):
        is_control = any(label.startswith('control_for:') for label in labels[key])
        focus_rows.append({'flat_index_yx': key, 'point_index': cases[key]['point_index'],
                           'latitude': cases[key]['latitude'], 'longitude': cases[key]['longitude'],
                           'cohort_labels': ';'.join(sorted(labels[key])),
                           'is_control': str(is_control).lower()})
    control_use: dict[int, list[dict]] = {}
    for row in control_links:
        if row['valid_match']:
            control_use.setdefault(row['control_flat_index_yx'], []).append(row)
    reuse_audit = []
    for control_id, rows in control_use.items():
        cohorts = sorted({row['cohort_label'] for row in rows})
        for row in rows:
            row['control_reuse_count'] = len(rows)
            row['control_reused_across_cohorts'] = len(cohorts) > 1
        if len(cohorts) > 1:
            reuse_audit.append({'control_flat_index_yx': control_id, 'reuse_count': len(rows),
                                'cohort_labels': ';'.join(cohorts)})
    for row in control_links:
        if not row['valid_match']:
            row['control_reuse_count'] = 0
            row['control_reused_across_cohorts'] = False

    # Include the requested h2 and h5 weak-hit controls plus every labeled focus point.
    focus_keys = sorted(labels)
    temporal, spatial = [], []
    for key in focus_keys:
        base = cases[key]
        for case in ('ORIGINAL', 'A', 'C', 'D'):
            values = [float(hourly[12 + lead][case][np.flatnonzero(hourly[12 + lead]['flat_index_yx'] == key)[0]])
                      for lead in LEADS]
            interval = sum(values[3:6])
            peak_lead = LEADS[int(np.argmax(values))]
            fraction_h5 = values[4] / interval if interval else None
            row_index = int(np.flatnonzero(hourly[17]['flat_index_yx'] == key)[0])
            c_interval = sum(float(hourly[12 + lead]['C'][np.flatnonzero(hourly[12 + lead]['flat_index_yx'] == key)[0]]) for lead in (4, 5, 6))
            a_interval = sum(float(hourly[12 + lead]['A'][np.flatnonzero(hourly[12 + lead]['flat_index_yx'] == key)[0]]) for lead in (4, 5, 6))
            h5_delta = float(hourly[17]['C'][row_index] - hourly[17]['A'][row_index])
            interval_delta = c_interval - a_interval
            trend = 'interval_total_up' if interval_delta > 0 else 'interval_total_down' if interval_delta < 0 else 'interval_total_equal'
            phase_note = 'with_evaluation_hour_loss' if h5_delta < 0 else 'without_evaluation_hour_loss'
            temporal.append({'flat_index_yx': key, 'case': case, **{f'h{lead}_mm': values[lead - 1] for lead in LEADS},
                             'h4_h5_h6_sum_mm': interval, 'peak_lead_hour': peak_lead,
                             'peak_hour_utc': 12 + peak_lead,
                             'h5_fraction_of_h4_h5_h6': fraction_h5,
                             'C_minus_A_interval_sum_mm': interval_delta, 'C_minus_A_h5_mm': h5_delta,
                             'label': f'{trend}_{phase_note}'})
        for lead in LEADS:
            data = hourly[12 + lead]
            idx = int(np.flatnonzero(data['flat_index_yx'] == key)[0])
            distances = haversine_km(data['latitude'][idx], data['longitude'][idx], data['latitude'], data['longitude'])
            for radius in RADII_KM:
                neighbors = distances <= radius
                row = {'flat_index_yx': key, 'lead_hour': lead, 'radius_km': radius,
                       'neighbor_count_including_query_point': int(np.count_nonzero(neighbors))}
                for arm in ('reference', 'A', 'C'):
                    forecast = data[arm]
                    for threshold in THRESHOLDS:
                        event_ids = np.flatnonzero(forecast >= threshold)
                        nearest = float(np.min(distances[event_ids])) if event_ids.size else None
                        row[f'nearest_{arm}_event_{threshold:g}mm_km'] = nearest
                        row[f'nearest_{arm}_event_{threshold:g}mm_valid'] = event_ids.size > 0
                    row[f'{arm}_neighbor_min_mm'] = float(np.min(forecast[neighbors])) if np.any(neighbors) else None
                    row[f'{arm}_neighbor_max_mm'] = float(np.max(forecast[neighbors])) if np.any(neighbors) else None
                spatial.append(row)

    weak = []
    for lead in range(2, 7):
        data = hourly[12 + lead]
        band = (data['reference'] >= .1) & (data['reference'] < 1.)
        for case in ('A', 'C', 'D'):
            detections = band & (data[case] >= .1)
            population = int(np.count_nonzero(band))
            weak.append({'lead_hour': lead, 'case': case, 'observed_weak_points': population,
                         'detected_weak_points': int(np.count_nonzero(detections)),
                         'valid_population': population > 0,
                         'detection_fraction': float(np.count_nonzero(detections) / population) if population else None})

    algebra = []
    for lead in range(1, 7):
        data = hourly[12 + lead]
        for threshold in THRESHOLDS:
            obs = data['reference'] >= threshold
            observed_count = int(np.count_nonzero(obs))
            counts_by_case = {}
            for case in ('A', 'C', 'D'):
                pred = data[case] >= threshold
                hit, false = int(np.count_nonzero(obs & pred)), int(np.count_nonzero(~obs & pred))
                counts_by_case[case] = (hit, false)
            for candidate in ('C', 'D'):
                ha, fa = counts_by_case['A']
                hc, fc = counts_by_case[candidate]
                den_a, den_c = observed_count + fa, observed_count + fc
                valid_csi = den_a > 0 and den_c > 0
                csi_a = Fraction(ha, den_a) if den_a else None
                csi_c = Fraction(hc, den_c) if den_c else None
                hit_part = Fraction(hc - ha, den_c) if den_c else None
                false_part = Fraction(-ha * (fc - fa), den_a * den_c) if den_a and den_c else None
                delta_csi = csi_c - csi_a if valid_csi else None
                hit_only_csi = Fraction(ha, den_c) if den_c else None
                algebra.append({'lead_hour': lead, 'threshold_mm': threshold, 'contrast': f'{candidate}-A',
                                'observed_O_H_plus_M': observed_count, 'A_H': ha, 'A_F': fa,
                                f'{candidate}_H': hc, f'{candidate}_F': fc,
                                'A_M': observed_count - ha, f'{candidate}_M': observed_count - hc,
                                'delta_H': hc - ha, 'delta_F': fc - fa,
                                'valid_csi': valid_csi,
                                'hit_algebra_term': str(hit_part) if hit_part is not None else None,
                                'false_alarm_algebra_term': str(false_part) if false_part is not None else None,
                                'delta_CSI_reconstructed': str(hit_part + false_part) if valid_csi else None,
                                'delta_CSI_recount': str(delta_csi) if delta_csi is not None else None,
                                'candidate_H_with_A_F_CSI': float(Fraction(hc, den_a)) if den_a else None,
                                'A_H_with_candidate_F_CSI': float(hit_only_csi) if hit_only_csi is not None else None,
                                'restored_baseline_hit_with_candidate_F_exact_CSI': str(hit_only_csi) if hit_only_csi is not None else None,
                                'restored_baseline_hit_with_candidate_F_CSI': float(hit_only_csi) if hit_only_csi is not None else None,
                                'hit_only_repair_below_A_with_candidate_F': hit_only_csi < csi_a if valid_csi else None,
                                'A_CSI': float(csi_a) if csi_a is not None else None,
                                'candidate_CSI': float(csi_c) if csi_c is not None else None})
    temporal_summary = []
    temporal_by_id = {row['flat_index_yx']: row for row in temporal if row['case'] == 'C'}
    for cohort in ('h05_A_C_weak_hit_loss', 'h05_A_C_weak_hit_gain',
                   'h06_A_C_weak_hit_loss', 'h06_A_C_weak_hit_gain'):
        point_ids = [row['flat_index_yx'] for row in focus_rows
                     if cohort in row['cohort_labels'].split(';')]
        deltas = [float(temporal_by_id[key]['C_minus_A_interval_sum_mm']) for key in point_ids]
        h5_deltas = [float(temporal_by_id[key]['C_minus_A_h5_mm']) for key in point_ids]
        trend = ('up' if sum(deltas) > 0 else 'down' if sum(deltas) < 0 else 'unchanged')
        evaluation_hour = ('decrease' if sum(h5_deltas) < 0 else
                           'increase' if sum(h5_deltas) > 0 else 'unchanged')
        temporal_summary.append({'cohort_label': cohort, 'point_count': len(point_ids),
                                 'C_minus_A_h4_h5_h6_sum_mm': sum(deltas),
                                 'positive_point_count': sum(value > 0 for value in deltas),
                                 'negative_point_count': sum(value < 0 for value in deltas),
                                 'zero_point_count': sum(value == 0 for value in deltas),
                                 'C_minus_A_h5_sum_mm': sum(h5_deltas),
                                 'label': f'interval_total_{trend}_with_evaluation_hour_{evaluation_hour}'})
    return {'focus_membership': focus_rows, 'event_membership': event_rows,
            'matched_controls': control_links, 'control_reuse_audit': reuse_audit,
            'transition_counts': counts, 'temporal_diagnostics': temporal,
            'temporal_cohort_summary': temporal_summary,
            'spatial_neighbors': spatial, 'conditional_weak_detections': weak,
            'csi_algebra': algebra}


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise TargetError(f'cannot write empty required table: {path.name}')
    fieldnames = list(dict.fromkeys(key for row in rows for key in row))
    with Path(path).open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def validate_targets(plan: dict, tables: dict[str, list[dict]]) -> None:
    membership = {row['flat_index_yx']: set(row['cohort_labels'].split(';'))
                  for row in tables['focus_membership']}
    expected_labels = {
        'h02_original_A_weak_hit_loss': 'h02_original_A_weak_hit_loss',
        'h02_original_A_weak_hit_gain': 'h02_original_A_weak_hit_gain',
        'h02_loss_recovered_by_C': 'h02_loss_recovered_by_C',
        'h02_loss_unrecovered_by_C': 'h02_loss_unrecovered_by_C',
        'h02_original_A_new_FA': 'h02_original_A_new_FA',
        'h02_original_A_resolved_FA': 'h02_original_A_resolved_FA',
        'h05_A_C_5mm_new_FA': 'h05_A_C_5mm_new_FA',
        'h05_A_C_5mm_resolved_FA': 'h05_A_C_5mm_resolved_FA',
        'h05_A_C_5mm_hit_loss': 'h05_A_C_5mm_hit_loss',
        'h05_A_C_5mm_hit_gain': 'h05_A_C_5mm_hit_gain',
        'h05_A_C_weak_hit_loss': 'h05_A_C_weak_hit_loss',
        'h05_A_C_weak_hit_gain': 'h05_A_C_weak_hit_gain',
        'h06_A_C_weak_hit_loss': 'h06_A_C_weak_hit_loss',
        'h06_A_C_weak_hit_gain': 'h06_A_C_weak_hit_gain',
    }
    expected_counts = {row['id']: row['expected_count'] for row in plan['cohorts'] if 'expected_count' in row}
    for cohort_id, label in expected_labels.items():
        actual_ids = {key for key, row_labels in membership.items() if label in row_labels}
        if len(actual_ids) != expected_counts.get(cohort_id):
            raise TargetError(f'{cohort_id}: derived count differs from frozen expected count')
    recovered = {key for key, row_labels in membership.items() if 'h02_loss_recovered_by_C' in row_labels}
    recovered_expected = next(row['expected_ids'] for row in plan['cohorts'] if row['id'] == 'h02_loss_recovered_by_C')
    if sorted(recovered) != sorted(recovered_expected):
        raise TargetError('C-recovered point IDs differ from frozen plan')
    hit_loss_ids = {key for key, row_labels in membership.items() if 'h05_A_C_5mm_hit_loss' in row_labels}
    hit_loss_expected = next(row['expected_ids'] for row in plan['cohorts'] if row['id'] == 'h05_A_C_5mm_hit_loss')
    if sorted(hit_loss_ids) != sorted(hit_loss_expected):
        raise TargetError('5 mm hit-loss point IDs differ from frozen plan')
    band_counts = [sum('h05_A_C_5mm_new_FA_' + suffix in row_labels for row_labels in membership.values())
                   for suffix in ('dry', 'weak', '1to5')]
    expected_bands = next(row['expected_observed_band_counts'] for row in plan['cohorts']
                          if row['id'] == 'h05_A_C_5mm_new_FA')
    if band_counts != expected_bands:
        raise TargetError('5 mm new-false-alarm observed-band counts differ from frozen plan')
    expected_pairs = {}
    for row_labels in membership.values():
        for label in row_labels:
            if not label.startswith('control_for:'):
                expected_pairs[label] = expected_pairs.get(label, 0) + 1
    actual_pairs = {}
    for row in tables['matched_controls']:
        actual_pairs[row['cohort_label']] = actual_pairs.get(row['cohort_label'], 0) + 1
    if actual_pairs != expected_pairs:
        raise TargetError('matched-control table omits a target or has duplicate cohort rows')
    matched_keys = [(row['cohort_label'], row['control_flat_index_yx'])
                    for row in tables['matched_controls'] if row['valid_match']]
    if len(matched_keys) != len(set(matched_keys)):
        raise TargetError('a control point is reused within a cohort')


def run(source: Path = SOURCE, output: Path = OUTPUT, command: list[str] | None = None) -> dict:
    output = Path(output)
    if os.path.lexists(output):
        raise TargetError(f'output already exists: {output}')
    receipt, hourly = load_bundle(source)
    tables = derive_targets(hourly)
    plan = json.loads(PLAN.read_text(encoding='utf-8'))
    validate_targets(plan, tables)
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.failure-targets-', dir=output.parent))
    try:
        for name, rows in tables.items():
            write_csv(stage / f'{name}.csv', rows)
        source_files = [file_identity(PLAN), file_identity(Path(__file__)),
                        file_identity(Path(source) / 'receipt.json')] + [
            file_identity(Path(source) / f'hour_{hour}_arrays.npz') for hour in HOURS]
        (stage / 'source_receipt.json').write_text(json.dumps({'plan_sha256': PLAN_SHA256,
                                                                'receipt': receipt, 'files': source_files},
                                                                indent=2, sort_keys=True) + '\n', encoding='utf-8')
        outputs = {}
        for path in sorted(stage.iterdir()):
            identity = file_identity(path)
            identity['path'] = str(output / path.name)
            outputs[path.name] = identity
        control_counts = {}
        for row in tables['matched_controls']:
            stats = control_counts.setdefault(row['cohort_label'], {'target_count': 0, 'matched_count': 0,
                                                                     'missing_count': 0})
            stats['target_count'] += 1
            stats['matched_count' if row['valid_match'] else 'missing_count'] += 1
        bundle = {'schema': 'cp02_failure_focus_targets_v1', 'status': 'COMPLETE',
                  'command_argv': command or ['python', 'tools/cp02_b1_failure_targets.py',
                                              '--source', str(source), '--output', str(output)],
                  'exit_status': 0,
                  'analysis_plan_sha256': PLAN_SHA256,
                  'tool_sha256': source_files[1]['sha256'],
                  'source_receipt_sha256': source_files[2]['sha256'], 'points_per_hour': 3688,
                  'lead_hours': list(LEADS), 'thresholds_mm': list(THRESHOLDS),
                  'unique_focus_points': len(tables['focus_membership']),
                  'cohort_membership_rows': len(tables['focus_membership']),
                  'matched_control_pairs': sum(row['valid_match'] for row in tables['matched_controls']),
                  'missing_control_pairs': sum(not row['valid_match'] for row in tables['matched_controls']),
                  'reused_control_ids_across_cohorts': len(tables['control_reuse_audit']),
                  'control_reuse_audit': tables['control_reuse_audit'],
                  'control_counts_by_cohort': control_counts,
                  'outputs': outputs}
        (stage / 'bundle_receipt.json').write_text(json.dumps(bundle, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        os.rename(stage, output)
        return bundle
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=SOURCE)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    print(json.dumps(run(args.source, args.output, ['python', *sys.argv]), sort_keys=True))


if __name__ == '__main__':
    main()
