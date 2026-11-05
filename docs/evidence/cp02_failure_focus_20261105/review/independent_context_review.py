#!/usr/bin/env python3
"""Independently recount context tables from receipt-bound state and target arrays."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[4]
EVIDENCE = ROOT / 'docs/evidence/cp02_failure_focus_20261105'
CONTEXT = EVIDENCE / 'context'
STATE = EVIDENCE / 'state/extracted'
TARGETS = EVIDENCE / 'targets'
CASES = ('ORIGINAL', 'A', 'C', 'B1_OLD_KDM6')
HOURS = tuple(range(12, 19))
FIELDS = {
    'QVAPOR_kgkg': 'corner_QVAPOR', 'QCLOUD_kgkg': 'corner_QCLOUD',
    'QRAIN_kgkg': 'corner_QRAIN', 'QSNOW_kgkg': 'corner_QSNOW',
    'temperature_K': 'corner_temperature_K', 'RH_liquid': 'corner_rh_liquid',
    'totalP_Pa': 'corner_pressure_Pa', 'W_ms': 'corner_w_mass_level_m_s',
}
LAYERS = ('[0,1000)m', '[1000,3000)m')
CONTRASTS = {'A-X': ('A', 'B1_OLD_KDM6'), 'A-ORIGINAL': ('A', 'ORIGINAL'), 'C-A': ('C', 'A')}


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict]:
    with path.open(newline='', encoding='utf-8') as stream:
        return list(csv.DictReader(stream))


def verify(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def near(actual, expected, message: str, atol=2e-12, rtol=2e-12):
    if actual is None or expected is None:
        verify(actual is None and expected is None, message + ': null mismatch')
    else:
        verify(np.isclose(float(actual), float(expected), atol=atol, rtol=rtol),
               f'{message}: {actual!r} != {expected!r}')


def boolean(value: str) -> bool:
    verify(value in ('true', 'false', 'True', 'False'), f'not a serialized boolean: {value}')
    return value.lower() == 'true'


def stats(values: list[float | None]) -> dict:
    a = np.asarray([v for v in values if v is not None and np.isfinite(v)], dtype=np.float64)
    if not a.size:
        return {'n_valid': 0, 'minimum': None, 'q25': None, 'median': None,
                'q75': None, 'maximum': None}
    q25, median, q75 = np.quantile(a, (0.25, 0.5, 0.75))
    return {'n_valid': int(a.size), 'minimum': float(a.min()), 'q25': float(q25),
            'median': float(median), 'q75': float(q75), 'maximum': float(a.max())}


def assert_stats(row: dict, expected: dict, key: str) -> None:
    for field in ('n_valid', 'minimum', 'q25', 'median', 'q75', 'maximum'):
        if field == 'n_valid':
            verify(int(row[field]) == expected[field], f'{key}/{field}')
        else:
            actual = None if row[field] == '' else float(row[field])
            near(actual, expected[field], f'{key}/{field}')


def main() -> None:
    bundle_path = CONTEXT / 'bundle_receipt.json'
    bundle = json.loads(bundle_path.read_text(encoding='utf-8'))
    bundle_hash = sha(bundle_path)
    verify(bundle_hash == 'a63d4b0d43f94b7456a9ebd8dde68b1616aec521f28bab04e73ee8d48c3e014e', 'bundle receipt pin')
    verify(bundle['schema'] == 'cp02_b1_failure_context_v1' and bundle['exit_status'] == 0, 'bundle schema/status')
    verify(bundle['cases'] == list(CASES) and bundle['hours_utc'] == list(HOURS), 'case/hour pin')
    verify(bundle['focus_points'] == 270 and bundle['event_rows'] == 158 and bundle['matched_control_rows'] == 158,
           'frozen target counts')
    output_hashes = {}
    for name, record in bundle['outputs'].items():
        path = Path(record['path'])
        verify(path == CONTEXT / name and path.is_file(), f'{name}: output path')
        verify(path.stat().st_size == record['size_bytes'] and sha(path) == record['sha256'], f'{name}: output hash')
        output_hashes[name] = record['sha256']
    source_hashes = {}
    for record in bundle['sources']:
        path = Path(record['path'])
        verify(path.is_file() and path.stat().st_size == record['size_bytes'] and sha(path) == record['sha256'],
               f'source pin: {path}')
        source_hashes[str(path)] = record['sha256']

    state_receipt = json.loads((STATE / 'receipt.json').read_text(encoding='utf-8'))
    state_by_key = {(r['case'], int(r['hour_utc'])): r for r in state_receipt['records']}
    states = {}
    for case in CASES:
        for hour in HOURS:
            record = state_by_key[case, hour]
            path = STATE / record['output']
            with np.load(path, allow_pickle=False) as archive:
                states[case, hour] = {key: np.array(archive[key], copy=True) for key in (
                    'flat_index_yx', 'point_index', 'corner_weights', 'corner_height_agl_m',
                    'corner_QVAPOR', 'corner_QCLOUD', 'corner_QRAIN', 'corner_QSNOW',
                    'corner_temperature_K', 'corner_rh_liquid', 'corner_pressure_Pa',
                    'corner_w_mass_level_m_s', 'weighted_rainc_increment_mm',
                    'weighted_rainnc_increment_mm')}

    focus = read_csv(TARGETS / 'focus_membership.csv')
    events = read_csv(TARGETS / 'event_membership.csv')
    controls = read_csv(TARGETS / 'matched_controls.csv')
    verify(len(focus) == 270 and len(events) == len(controls) == 158, 'target table row counts')
    ids = [int(r['flat_index_yx']) for r in focus]
    point_index = [int(r['point_index']) for r in focus]
    verify(len(set(ids)) == 270 and len(set(point_index)) == 270, 'focus keys unique')
    for key, state in states.items():
        verify(state['flat_index_yx'].tolist() == ids and state['point_index'].tolist() == point_index,
               f'{key}: state membership order')

    # Recompute all 6*270*4 surface paths from stored component increments.
    surface_rows = read_csv(CONTEXT / 'point_surface_paths.csv')
    verify(len(surface_rows) == 270 * 4 * 6, 'surface row count')
    state_index = {(case, hour): {int(point): idx for idx, point in enumerate(states[case, hour]['flat_index_yx'])}
                   for case in CASES for hour in HOURS}
    surface_lookup = {}
    for row in surface_rows:
        case, hour, point = row['case'], int(row['hour_utc']), int(row['flat_index_yx'])
        verify(case in CASES and 13 <= hour <= 18, 'surface case/hour scope')
        idx = state_index[case, hour][point]
        state = states[case, hour]
        rainc = float(state['weighted_rainc_increment_mm'][idx])
        rainnc = float(state['weighted_rainnc_increment_mm'][idx])
        total = rainc + rainnc
        near(row['RAINC_increment_mm'], rainc, f'{case}h{hour}/{point} RAINC')
        near(row['RAINNC_increment_mm'], rainnc, f'{case}h{hour}/{point} RAINNC')
        near(row['surface_total_mm'], total, f'{case}h{hour}/{point} total')
        verify(boolean(row['surface_verified']), f'{case}h{hour}/{point} surface verification')
        verify(row['surface_verification'] == ('paired_score_array' if case != 'B1_OLD_KDM6'
                                               else 'state_receipt_only_no_score_arm'), 'score-arm label')
        surface_lookup[point, case, hour - 12] = row
    verify(len(surface_lookup) == 270 * 4 * 6, 'surface key coverage')

    # Recompute per-corner means, valid flags and weighted values without renormalizing.
    layer_rows = read_csv(CONTEXT / 'layer_features.csv')
    verify(len(layer_rows) == 270 * 4 * 7 * 2, 'layer row count')
    layer_lookup = {}
    layer_checks = 0
    valid_flags = 0
    invalid_weighted = 0
    for row in layer_rows:
        point, case, hour, layer = int(row['flat_index_yx']), row['case'], int(row['hour_utc']), row['layer_agl']
        verify(layer in LAYERS and case in CASES and hour in HOURS, 'layer key scope')
        idx = state_index[case, hour][point]
        data = states[case, hour]
        weights = data['corner_weights'][idx]
        height = data['corner_height_agl_m'][idx].astype(np.float64)
        low, high = ((0.0, 1000.0) if layer == LAYERS[0] else (1000.0, 3000.0))
        expected_counts = None
        values_for_lookup = {}
        for name, array_key in FIELDS.items():
            values = data[array_key][idx].astype(np.float64)
            selected = np.isfinite(height) & np.isfinite(values) & (height >= low) & (height < high)
            counts = selected.sum(axis=0)
            sums = np.where(selected, values, 0.0).sum(axis=0, dtype=np.float64)
            means = np.full(4, np.nan)
            np.divide(sums, counts, out=means, where=counts > 0)
            if name == 'QVAPOR_kgkg':
                expected_counts = counts
            required = weights > 0
            valid = bool(np.all((counts > 0) | ~required))
            weighted = float(np.sum(np.where(np.isfinite(means), means, 0.0) * weights)) if valid else None
            verify(boolean(row[f'{name}_valid']) == valid, f'{point}/{case}h{hour}/{layer}/{name} valid')
            for c in range(4):
                got = None if row[f'{name}_corner{c}_mean'] == '' else float(row[f'{name}_corner{c}_mean'])
                want = float(means[c]) if np.isfinite(means[c]) else None
                near(got, want, f'{point}/{case}h{hour}/{layer}/{name} corner{c}')
            got_weighted = None if row[name] == '' else float(row[name])
            near(got_weighted, weighted, f'{point}/{case}h{hour}/{layer}/{name} weighted')
            values_for_lookup[name] = got_weighted
            layer_checks += 1
            valid_flags += int(valid)
            invalid_weighted += int(not valid)
        verify([int(row[f'n_levels_corner{c}']) for c in range(4)] == expected_counts.tolist(),
               f'{point}/{case}h{hour}/{layer} level counts')
        layer_lookup[point, case, hour, layer] = values_for_lookup

    # Validate matched controls, role-reuse accounting, and recompute all physical contrast summaries.
    control_map = {}
    reuse = {}
    for row in controls:
        key = (row['cohort_label'], int(row['target_flat_index_yx']))
        verify(row['valid_match'] == 'True' and key not in control_map, f'control key {key}')
        control_map[key] = int(row['control_flat_index_yx'])
        reuse.setdefault(control_map[key], set()).add(row['cohort_label'])
    for row in controls:
        point = int(row['control_flat_index_yx'])
        labels = reuse[point]
        verify(int(row['control_reuse_count']) == len(labels), f'control {point}: reuse count audit')
        verify(boolean(row['control_reused_across_cohorts']) == (len(labels) > 1),
               f'control {point}: cross-cohort reuse flag')
    events_by_role = {}
    for row in events:
        role, point = row['cohort_label'], int(row['flat_index_yx'])
        events_by_role.setdefault(role, []).append(row)
        verify((role, point) in control_map, f'missing pair {role}/{point}')
    for role, rows in events_by_role.items():
        targets = [int(r['flat_index_yx']) for r in rows]
        matched = [control_map[role, point] for point in targets]
        verify(len(set(targets)) == len(targets) and len(set(matched)) == len(matched), f'{role}: within-role uniqueness')

    expected_contrasts = {}
    for role, rows in events_by_role.items():
        lead_set = {int(r['lead_hour']) for r in rows}
        verify(len(lead_set) == 1, f'{role}: mixed leads')
        lead = next(iter(lead_set))
        for time_role, hour in (('antecedent', 11 + lead), ('event_end', 12 + lead)):
            for layer in LAYERS:
                for field in FIELDS:
                    for contrast, (a, b) in CONTRASTS.items():
                        for population in ('target', 'matched_control'):
                            point_ids = ([int(r['flat_index_yx']) for r in rows] if population == 'target'
                                         else [control_map[role, int(r['flat_index_yx'])] for r in rows])
                            differences = []
                            for point in point_ids:
                                av, bv = layer_lookup[point, a, hour, layer][field], layer_lookup[point, b, hour, layer][field]
                                differences.append(av - bv if av is not None and bv is not None else None)
                            key = (role, lead, time_role, hour, layer, field, contrast, population)
                            expected_contrasts[key] = stats(differences)
    contrasts = read_csv(CONTEXT / 'cohort_physical_contrasts.csv')
    verify(len(contrasts) == len(expected_contrasts), 'physical contrast row count/key coverage')
    seen = set()
    for row in contrasts:
        key = (row['cohort_label'], int(row['lead_hour']), row['time_role'], int(row['hour_utc']),
               row['layer_agl'], row['field'], row['contrast'], row['population'])
        verify(key in expected_contrasts and key not in seen, f'physical contrast duplicate/unexpected key: {key}')
        seen.add(key)
        assert_stats(row, expected_contrasts[key], f'contrast {key}')

    # Recount surface cohort rows and summaries from event/control tables and point paths.
    expected_surface_context = {}
    expected_surface_summary = {}
    for role, rows in events_by_role.items():
        lead = int(rows[0]['lead_hour'])
        threshold = float(rows[0]['threshold_mm'])
        for event in rows:
            point = int(event['flat_index_yx'])
            for population, sample_point in (('target', point), ('matched_control', control_map[role, point])):
                key = (role, population, point, sample_point)
                orig = float(surface_lookup[sample_point, 'ORIGINAL', lead]['surface_total_mm'])
                oldx = float(surface_lookup[sample_point, 'B1_OLD_KDM6', lead]['surface_total_mm'])
                context = {'event': event, 'lead': lead, 'point': point, 'sample_point': sample_point,
                           'population': population, 'ORIGINAL_already_ge_5mm': orig >= 5,
                           'X_already_ge_5mm': oldx >= 5,
                           'all_old_cases_below_5mm': all(float(surface_lookup[sample_point, c, lead]['surface_total_mm']) < 5
                                                          for c in ('ORIGINAL', 'A', 'B1_OLD_KDM6'))}
                expected_surface_context[key] = context
        for population in ('target', 'matched_control'):
            sample_points = ([int(r['flat_index_yx']) for r in rows] if population == 'target'
                             else [control_map[role, int(r['flat_index_yx'])] for r in rows])
            for case in (*CASES, 'RN1_REFERENCE'):
                vals = [float(surface_lookup[p, 'A', lead]['RN1_reference_mm']) if case == 'RN1_REFERENCE'
                        else float(surface_lookup[p, case, lead]['surface_total_mm']) for p in sample_points]
                s = stats(vals)
                expected_surface_summary[role, population, lead, 12 + lead, threshold, case] = {
                    **s, 'n_points': len(sample_points),
                    'n_crossed_role_threshold': sum(v >= threshold for v in vals)}
    surface_context = read_csv(CONTEXT / 'cohort_surface_context.csv')
    verify(len(surface_context) == len(expected_surface_context), 'surface cohort row count')
    seen = set()
    for row in surface_context:
        key = (row['cohort_label'], row['population'], int(row['target_flat_index_yx']), int(row['flat_index_yx']))
        verify(key in expected_surface_context and key not in seen, f'surface cohort duplicate/unexpected {key}')
        seen.add(key)
        exp = expected_surface_context[key]
        ev, lead, point, sample_point = exp['event'], exp['lead'], exp['point'], exp['sample_point']
        verify(int(row['lead_hour']) == lead and int(row['hour_utc']) == 12 + lead and int(row['flat_index_yx']) == sample_point,
               f'{key}: time/point')
        verify(float(row['threshold_mm']) == float(ev['threshold_mm']) and row['observed_band'] == ev['observed_band']
               and row['transition'] == ev['transition'], f'{key}: cohort event attributes')
        verify(boolean(row['ORIGINAL_already_ge_5mm']) == exp['ORIGINAL_already_ge_5mm']
               and boolean(row['X_already_ge_5mm']) == exp['X_already_ge_5mm']
               and boolean(row['all_old_cases_below_5mm']) == exp['all_old_cases_below_5mm'], f'{key}: threshold flags')
        for case in CASES:
            surf = surface_lookup[sample_point, case, lead]
            near(row[f'{case}_total_mm'], float(surf['surface_total_mm']), f'{key}/{case} total')
            verify(boolean(row[f'{case}_crossed_role_threshold']) == (float(surf['surface_total_mm']) >= float(ev['threshold_mm'])),
                   f'{key}/{case} threshold')
            near(row[f'{case}_RAINC_increment_mm'], float(surf['RAINC_increment_mm']), f'{key}/{case} rainc')
            near(row[f'{case}_RAINNC_increment_mm'], float(surf['RAINNC_increment_mm']), f'{key}/{case} rainnc')

    surface_summary = read_csv(CONTEXT / 'cohort_surface_context_summary.csv')
    verify(len(surface_summary) == len(expected_surface_summary), 'surface summary row count')
    seen = set()
    for row in surface_summary:
        key = (row['cohort_label'], row['population'], int(row['lead_hour']), int(row['hour_utc']),
               float(row['threshold_mm']), row['case'])
        verify(key in expected_surface_summary and key not in seen, f'surface summary duplicate/unexpected {key}')
        seen.add(key)
        expected = expected_surface_summary[key]
        verify(int(row['n_points']) == expected['n_points'] and int(row['n_crossed_role_threshold']) == expected['n_crossed_role_threshold'],
               f'{key}: counts')
        assert_stats(row, expected, f'surface summary {key}')

    # Explicit legacy/threshold cross-checks from the frozen event cohorts.
    weak_rows = [r for r in events if r['cohort_label'] == 'h02_original_A_weak_hit_loss']
    verify(len(weak_rows) == 10, 'h02 weak-hit-loss count')
    weak_x_hits = sum(float(surface_lookup[int(r['flat_index_yx']), 'B1_OLD_KDM6', 2]['surface_total_mm']) >= float(r['threshold_mm'])
                      for r in weak_rows)
    verify(weak_x_hits == 9, 'h02 weak-loss B1 legacy hit recount')
    h02_newfa = [r for r in events if r['cohort_label'] == 'h02_original_A_new_FA']
    verify(len(h02_newfa) == 53, 'h02 new false-alarm count')
    miss_to_false = sum(float(surface_lookup[int(r['flat_index_yx']), 'B1_OLD_KDM6', 2]['surface_total_mm']) < float(r['threshold_mm'])
                        and float(surface_lookup[int(r['flat_index_yx']), 'A', 2]['surface_total_mm']) >= float(r['threshold_mm'])
                        for r in h02_newfa)
    verify(miss_to_false == 32, 'h02 B1 miss to A false-alarm recount')
    h05_newfa = [r for r in events if r['cohort_label'] == 'h05_A_C_5mm_new_FA']
    verify(len(h05_newfa) == 12, 'h05 5-mm new false-alarm count')
    h05_counts = {'ORIGINAL': 0, 'B1_OLD_KDM6': 0, 'all_old_cases_below_5mm': 0}
    for event in h05_newfa:
        point = int(event['flat_index_yx'])
        lead = int(event['lead_hour'])
        h05_counts['ORIGINAL'] += float(surface_lookup[point, 'ORIGINAL', lead]['surface_total_mm']) >= 5
        h05_counts['B1_OLD_KDM6'] += float(surface_lookup[point, 'B1_OLD_KDM6', lead]['surface_total_mm']) >= 5
        h05_counts['all_old_cases_below_5mm'] += all(float(surface_lookup[point, c, lead]['surface_total_mm']) < 5
                                                     for c in ('ORIGINAL', 'A', 'B1_OLD_KDM6'))
    verify(h05_counts == {'ORIGINAL': 7, 'B1_OLD_KDM6': 7, 'all_old_cases_below_5mm': 5}, 'h05 5-mm cross-check')

    review = {
        'schema': 'cp02_b1_failure_context_independent_review_v1', 'status': 'PASS_CONTEXT_RECOUNT',
        'context_bundle_sha256': bundle_hash, 'state_receipt_sha256': sha(STATE / 'receipt.json'),
        'state_plan_sha256': sha(EVIDENCE / 'state/extraction_plan.json'),
        'target_receipt_sha256': sha(TARGETS / 'bundle_receipt.json'),
        'analyzer_sha256': source_hashes[str(ROOT / 'tools/cp02_b1_failure_context.py')],
        'output_sha256': output_hashes,
        'coverage': {
            'focus_points': 270, 'event_rows': len(events), 'matched_control_rows': len(controls),
            'surface_path_rows_recomputed': len(surface_rows),
            'surface_case_hour_point_paths': 270 * 4 * 6,
            'layer_feature_rows_recomputed': len(layer_rows), 'layer_field_rows_recomputed': layer_checks,
            'layer_valid_field_rows': valid_flags, 'layer_invalid_field_rows': invalid_weighted,
            'cohort_physical_contrast_rows_recomputed': len(contrasts),
            'cohort_surface_context_rows_recomputed': len(surface_context),
            'cohort_surface_summary_rows_recomputed': len(surface_summary),
            'cohort_count': len(events_by_role), 'matched_control_ids_reused_across_roles': sum(len(x) > 1 for x in reuse.values()),
            'unique_matched_control_ids': len(reuse), 'within_role_control_reuse': False,
            'cross_checks': {'h02_weak_loss': '9/10 B1_OLD_KDM6 crossed role threshold',
                             'h02_new_false_alarm': '32/53 B1_OLD_KDM6 misses became A hits',
                             'h05_new_5mm_false_alarm': h05_counts},
        },
        'limits': ['Layer summaries were recomputed as unweighted per-corner model-level means, followed by the stored fixed bilinear weights; no renormalization or mass weighting.',
                   'Medians and quantiles are descriptive summaries of event-defined target/control groups; repeated controls across roles do not imply independent samples.',
                   'The inputs are sealed Eulerian history snapshots and one-hour surface increments, not captured process rates; no causal or budget claim follows.'],
    }
    out = EVIDENCE / 'review/independent_context_review.json'
    out.write_text(json.dumps(review, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps({'review_sha256': sha(out), 'status': review['status'], 'coverage': review['coverage']}, indent=2))


if __name__ == '__main__':
    main()
