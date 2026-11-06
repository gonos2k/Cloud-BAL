#!/usr/bin/env python3
"""Summarize sealed point-state and surface context for frozen CP02 cohorts."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'docs/evidence/cp02_failure_focus_20261105'
STATE = EVIDENCE / 'state/extracted'
TARGETS = EVIDENCE / 'targets'
SCORES = ROOT / 'docs/evidence/cp02_grouped_forecast_20261105/analysis'
OUTPUT = EVIDENCE / 'context'
STATE_RECEIPT_SHA256 = '39f1cede1e47b173491a47e5f4f0182ef7f682be834fbea0f0e1ab37889e23ba'
STATE_PLAN_SHA256 = 'c3961eee66da7e1979d47baad64df15e75701ea586462b6b4a634c184d798c27'
TARGET_RECEIPT_SHA256 = '3ea1a834f61fa7a88c8f199c5ef8710298c489abc83c3c11965241d5dd7a420f'
TARGETS_SHA256 = {
    'focus_membership.csv': '74a3667635442d0075a8af1689522c137b240249645a7a7ab86e8c09dfa88c8d',
    'event_membership.csv': 'ebfe97c1e3bb3714289c502432f75be7313d1ee80b40199624b13cd1fb31e942',
    'matched_controls.csv': 'b9cb77c8bd7fa9dbc5890c997ce86bb5e18ada565a934f340717396025824b3a',
}
CASES = ('ORIGINAL', 'A', 'C', 'B1_OLD_KDM6')
SCORE_CASES = {'ORIGINAL': 'ORIGINAL', 'A': 'A', 'C': 'C'}
HOURS = tuple(range(12, 19))
LEADS = tuple(range(1, 7))
LAYERS = ((0.0, 1000.0), (1000.0, 3000.0))
FIELDS = {
    'QVAPOR_kgkg': 'corner_QVAPOR', 'QCLOUD_kgkg': 'corner_QCLOUD',
    'QRAIN_kgkg': 'corner_QRAIN', 'QSNOW_kgkg': 'corner_QSNOW',
    'temperature_K': 'corner_temperature_K', 'RH_liquid': 'corner_rh_liquid',
    'totalP_Pa': 'corner_pressure_Pa', 'W_ms': 'corner_w_mass_level_m_s',
}
SURFACE_ATOL, SURFACE_RTOL = 1e-10, 1e-12


class ContextError(ValueError):
    """Invalid or changed frozen inputs for the context analysis."""


def identity(path: Path) -> dict:
    path = Path(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {'path': str(path), 'sha256': digest, 'size_bytes': path.stat().st_size}


def _pinned(path: Path, digest: str) -> dict:
    if not path.is_file() or identity(path)['sha256'] != digest:
        raise ContextError(f'input hash differs: {path}')
    return identity(path)


def load_inputs(state_dir: Path = STATE, targets_dir: Path = TARGETS,
                scores_dir: Path = SCORES) -> tuple[dict, dict, list[dict], list[dict], list[dict], dict, dict]:
    """Verify state, target and score receipts; load only receipt-bound NPZ archives."""
    state_dir, targets_dir, scores_dir = map(Path, (state_dir, targets_dir, scores_dir))
    state_receipt_path = state_dir / 'receipt.json'
    state_receipt_identity = _pinned(state_receipt_path, STATE_RECEIPT_SHA256)
    state_receipt = json.loads(state_receipt_path.read_text(encoding='utf-8'))
    plan_path = EVIDENCE / 'state/extraction_plan.json'
    plan_identity = _pinned(plan_path, STATE_PLAN_SHA256)
    plan = json.loads(plan_path.read_text(encoding='utf-8'))
    if (state_receipt.get('status') != 'PASS' or state_receipt.get('points') != 270
        or state_receipt.get('cases') != list(CASES) or plan.get('status') != 'FROZEN_BEFORE_STATE_EXTRACTION'
        or plan.get('hours_utc') != list(HOURS) or plan.get('cases') != list(CASES)):
        raise ContextError('state receipt or frozen plan inventory differs')
    target_receipt_path = targets_dir / 'bundle_receipt.json'
    target_receipt_identity = _pinned(target_receipt_path, TARGET_RECEIPT_SHA256)
    target_receipt = json.loads(target_receipt_path.read_text(encoding='utf-8'))
    if target_receipt.get('status') != 'COMPLETE' or target_receipt.get('unique_focus_points') != 270:
        raise ContextError('target receipt is incomplete')
    tables = {}
    for name, digest in TARGETS_SHA256.items():
        path = targets_dir / name
        _pinned(path, digest)
        with path.open(newline='', encoding='utf-8') as stream:
            tables[name] = list(csv.DictReader(stream))
    if len(tables['focus_membership.csv']) != 270:
        raise ContextError('focus membership row count differs')
    state_records = {(row['case'], row['hour_utc']): row for row in state_receipt['records']}
    if len(state_records) != len(CASES) * len(HOURS):
        raise ContextError('state receipt must bind 28 case-hour archives')
    state_arrays = {}
    for case in CASES:
        for hour in HOURS:
            record = state_records.get((case, hour))
            name = f'{case}_h{hour}.npz'
            path = state_dir / name
            if not record or record['output'] != name or not path.is_file():
                raise ContextError(f'missing receipt-bound state archive {name}')
            actual = identity(path)
            if actual['sha256'] != record['output_sha256'] or actual['size_bytes'] != record['output_size_bytes']:
                raise ContextError(f'state archive identity differs: {name}')
            with np.load(path, allow_pickle=False) as archive:
                keys = set(archive.files)
                required = set(FIELDS.values()) | {
                    'corner_height_agl_m', 'corner_weights', 'flat_index_yx', 'point_index',
                    'latitude', 'longitude', 'membership_cohort_labels', 'membership_is_control',
                    'weighted_rainc_increment_mm', 'weighted_rainnc_increment_mm',
                }
                if not required <= keys:
                    raise ContextError(f'{name}: missing arrays {sorted(required - keys)}')
                data = {key: np.array(archive[key], copy=True) for key in required}
            if (data['flat_index_yx'].shape != (270,) or data['point_index'].shape != (270,)
                or data['corner_weights'].shape != (270, 4) or data['corner_height_agl_m'].shape != (270, 39, 4)):
                raise ContextError(f'{name}: point, level or corner shape differs')
            for array_name in FIELDS.values():
                if data[array_name].shape != (270, 39, 4):
                    raise ContextError(f'{name}/{array_name}: expected 270x39x4')
            for array_name in ('weighted_rainc_increment_mm', 'weighted_rainnc_increment_mm'):
                if data[array_name].shape != (270,) or (hour >= 13 and not np.isfinite(data[array_name]).all()):
                    raise ContextError(f'{name}/{array_name}: invalid surface increments')
            weights = data['corner_weights']
            if (not np.isfinite(weights).all() or np.any(weights < 0)
                or not np.allclose(weights.sum(axis=1), 1.0, rtol=0, atol=1e-12)):
                raise ContextError(f'{name}: invalid interpolation weights')
            state_arrays[case, hour] = data
    focus_rows = tables['focus_membership.csv']
    for case in CASES:
        for hour in HOURS:
            data = state_arrays[case, hour]
            if ([int(x) for x in data['flat_index_yx']] != [int(r['flat_index_yx']) for r in focus_rows]
                or [int(x) for x in data['point_index']] != [int(r['point_index']) for r in focus_rows]):
                raise ContextError(f'{case}/h{hour}: state points differ from target membership order')
            if ([str(x) for x in data['membership_cohort_labels']] != [r['cohort_labels'] for r in focus_rows]
                or [bool(x) for x in data['membership_is_control']] != [r['is_control'] == 'true' for r in focus_rows]):
                raise ContextError(f'{case}/h{hour}: state role labels differ from target membership')
            if (not np.allclose(data['latitude'], [float(r['latitude']) for r in focus_rows], rtol=0, atol=1e-12)
                or not np.allclose(data['longitude'], [float(r['longitude']) for r in focus_rows], rtol=0, atol=1e-12)):
                raise ContextError(f'{case}/h{hour}: state coordinates differ from target membership')
    source_receipt_path = targets_dir / 'source_receipt.json'
    output_record = target_receipt.get('outputs', {}).get('source_receipt.json', {})
    source_identity = identity(source_receipt_path)
    if source_identity['sha256'] != output_record.get('sha256') or source_identity['size_bytes'] != output_record.get('size_bytes'):
        raise ContextError('source score receipt differs from target bundle binding')
    source_receipt = json.loads(source_receipt_path.read_text(encoding='utf-8'))
    score_inputs = {Path(row['path']).name: row for row in source_receipt['files']
                    if Path(row['path']).name.endswith('.npz')}
    score_arrays = {}
    for hour in range(13, 19):
        name = f'hour_{hour}_arrays.npz'
        record, path = score_inputs.get(name), scores_dir / name
        if not record or not path.is_file():
            raise ContextError(f'missing receipt-bound score array {name}')
        actual = identity(path)
        if actual['sha256'] != record['sha256'] or actual['size_bytes'] != record['size_bytes']:
            raise ContextError(f'score array identity differs: {name}')
        with np.load(path, allow_pickle=False) as archive:
            required = {'flat_index_yx', 'reference', *SCORE_CASES.values()}
            if not required <= set(archive.files):
                raise ContextError(f'{name}: missing paired score arrays')
            values = {key: np.array(archive[key], copy=True) for key in required}
        if any(a.shape != (3688,) for a in values.values()) or not np.isfinite(values['reference']).all():
            raise ContextError(f'{name}: invalid paired score array shape or values')
        if (not np.issubdtype(values['flat_index_yx'].dtype, np.integer)
            or np.unique(values['flat_index_yx']).size != 3688
            or any(not np.isfinite(values[key]).all() for key in SCORE_CASES.values())):
            raise ContextError(f'{name}: duplicate point keys or nonfinite forecast')
        score_arrays[hour] = values
    target_table_identities = {name: identity(targets_dir / name) for name in TARGETS_SHA256}
    score_identities = [identity(scores_dir / f'hour_{hour}_arrays.npz') for hour in range(13, 19)]
    return (state_receipt, state_arrays, focus_rows, tables['event_membership.csv'],
            tables['matched_controls.csv'], score_arrays,
            {'state_receipt': state_receipt_identity, 'state_plan': plan_identity,
             'target_receipt': target_receipt_identity, 'target_source_receipt': source_identity,
             'target_tables': target_table_identities, 'score_arrays': score_identities})


def layer_corner_means(values: np.ndarray, height: np.ndarray, weights: np.ndarray,
                       low_m: float, high_m: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Unweighted mean at each native corner, then fixed-weight bilinear sum."""
    if values.shape != height.shape or values.ndim != 3 or values.shape[2] != 4 or weights.shape != (values.shape[0], 4):
        raise ContextError('layer input shapes must be point,level,corner with four weights')
    selected = np.isfinite(height) & np.isfinite(values) & (height >= low_m) & (height < high_m)
    counts = selected.sum(axis=1).astype(np.int16)
    sums = np.sum(np.where(selected, values, 0.0), axis=1, dtype=np.float64)
    means = np.full((values.shape[0], 4), np.nan, dtype=np.float64)
    np.divide(sums, counts, out=means, where=counts > 0)
    required = weights > 0
    valid = np.all((counts > 0) | ~required, axis=1)
    weighted = np.sum(np.where(np.isfinite(means), means, 0.0) * weights, axis=1)
    weighted[~valid] = np.nan
    return means, counts, weighted, valid


def summarize(values: list[float]) -> dict:
    valid = np.asarray([v for v in values if v is not None and np.isfinite(v)], dtype=np.float64)
    if not valid.size:
        return {'n_valid': 0, 'minimum': None, 'q25': None, 'median': None, 'q75': None, 'maximum': None}
    q25, median, q75 = np.quantile(valid, (0.25, 0.5, 0.75))
    return {'n_valid': int(valid.size), 'minimum': float(valid.min()), 'q25': float(q25),
            'median': float(median), 'q75': float(q75), 'maximum': float(valid.max())}


def role_pairs(events: list[dict], controls: list[dict]) -> dict[str, list[tuple[int, int]]]:
    links = {}
    for row in controls:
        key = (row['cohort_label'], int(row['target_flat_index_yx']))
        if row.get('valid_match') != 'True' or key in links:
            raise ContextError('control link is missing, invalid or duplicated within a cohort')
        links[key] = int(row['control_flat_index_yx'])
    groups = {}
    for row in events:
        role, point = row['cohort_label'], int(row['flat_index_yx'])
        if (role, point) not in links:
            raise ContextError(f'{role}/{point}: matched control is missing')
        groups.setdefault(role, []).append((point, links[role, point]))
    for role, pairs in groups.items():
        if len({target for target, _ in pairs}) != len(pairs) or len({control for _, control in pairs}) != len(pairs):
            raise ContextError(f'{role}: duplicate target or control within role')
    return groups


def derive_context(state_arrays: dict, focus: list[dict], events: list[dict], controls: list[dict],
                   scores: dict) -> dict[str, list[dict]]:
    focus_by_id = {int(row['flat_index_yx']): row for row in focus}
    event_rows = [{**row, 'flat_index_yx': int(row['flat_index_yx']), 'lead_hour': int(row['lead_hour']),
                   'threshold_mm': float(row['threshold_mm'])} for row in events]
    pairs_by_role = role_pairs(event_rows, controls)
    layer_rows, layer_lookup, surface_rows, surface_lookup = [], {}, [], {}
    surface_checks = []
    summary_labels = {key: value for key, value in FIELDS.items()}
    for hour in HOURS:
        ref_score = scores.get(hour) if hour in scores else None
        for case in CASES:
            data = state_arrays[case, hour]
            ids = [int(x) for x in data['flat_index_yx']]
            weights, heights = data['corner_weights'], data['corner_height_agl_m']
            for low_m, high_m in LAYERS:
                label = f'[{int(low_m)},{int(high_m)})m'
                field_data = {name: layer_corner_means(data[array_name].astype(np.float64), heights, weights, low_m, high_m)
                              for name, array_name in FIELDS.items()}
                for point_idx, point_id in enumerate(ids):
                    row = {'flat_index_yx': point_id, 'point_index': int(data['point_index'][point_idx]),
                           'cohort_labels': str(data['membership_cohort_labels'][point_idx]),
                           'is_control': str(bool(data['membership_is_control'][point_idx])).lower(),
                           'case': case, 'hour_utc': hour, 'layer_agl': label,
                           **{f'n_levels_corner{corner}': int(field_data['QVAPOR_kgkg'][1][point_idx, corner])
                              for corner in range(4)}}
                    feature_values = {}
                    for field_name, (means, _, weighted, valid) in field_data.items():
                        row[f'{field_name}_valid'] = bool(valid[point_idx])
                        row[field_name] = float(weighted[point_idx]) if valid[point_idx] else None
                        for corner in range(4):
                            value = means[point_idx, corner]
                            row[f'{field_name}_corner{corner}_mean'] = float(value) if np.isfinite(value) else None
                        feature_values[field_name] = row[field_name]
                    layer_rows.append(row)
                    layer_lookup[point_id, case, hour, label] = feature_values
            if hour >= 13:
                lead, score = hour - 12, scores[hour]
                reference = score['reference']
                score_indices = score['flat_index_yx']
                for point_idx, point_id in enumerate(ids):
                    score_index = int(data['point_index'][point_idx])
                    if int(score_indices[score_index]) != point_id:
                        raise ContextError(f'{case}/{hour}: flat-index order differs from score array')
                    rainc = float(data['weighted_rainc_increment_mm'][point_idx])
                    rainnc = float(data['weighted_rainnc_increment_mm'][point_idx])
                    total = rainc + rainnc
                    score_key = SCORE_CASES.get(case)
                    if score_key:
                        residual = total - float(score[score_key][score_index])
                        tolerance = SURFACE_ATOL + SURFACE_RTOL * abs(float(score[score_key][score_index]))
                        verified, verification = abs(residual) <= tolerance, 'paired_score_array'
                        if not verified:
                            raise ContextError(f'{case}/{hour}/{point_id}: surface total exceeds paired score tolerance')
                    else:
                        residual, verified, verification = None, True, 'state_receipt_only_no_score_arm'
                    row = {'flat_index_yx': point_id, 'point_index': score_index,
                           'cohort_labels': focus_by_id[point_id]['cohort_labels'],
                           'is_control': focus_by_id[point_id]['is_control'],
                           'lead_hour': lead, 'hour_utc': hour, 'case': case,
                           'RN1_reference_mm': float(reference[score_index]),
                           'RAINC_increment_mm': rainc, 'RAINNC_increment_mm': rainnc,
                           'surface_total_mm': total, 'score_case': score_key or '',
                           'surface_score_residual_mm': residual, 'surface_verified': verified,
                           'surface_verification': verification}
                    surface_rows.append(row)
                    surface_lookup[point_id, case, lead] = row
                    if point_idx == 0:
                        surface_checks.append({'case': case, 'hour_utc': hour, 'points': len(ids),
                                               'max_abs_residual_mm': float(max(abs(r['surface_score_residual_mm'] or 0)
                                                                                for r in surface_rows[-len(ids):])),
                                               'verification': verification})
    contrasts, surface_context, surface_summary = [], [], []
    roles = sorted(pairs_by_role)
    for role in roles:
        role_events = [row for row in event_rows if row['cohort_label'] == role]
        lead = role_events[0]['lead_hour']
        if any(row['lead_hour'] != lead for row in role_events):
            raise ContextError(f'{role}: event lead is inconsistent')
        pairs = pairs_by_role[role]
        populations = {'target': [pair[0] for pair in pairs], 'matched_control': [pair[1] for pair in pairs]}
        for label, hour in (('antecedent', 12 + lead - 1), ('event_end', 12 + lead)):
            for layer in (f'[{int(a)},{int(b)})m' for a, b in LAYERS):
                for field_name in FIELDS:
                    for contrast, case_a, case_b in (('A-X', 'A', 'B1_OLD_KDM6'),
                                                     ('A-ORIGINAL', 'A', 'ORIGINAL'), ('C-A', 'C', 'A')):
                        for population, point_ids in populations.items():
                            differences = []
                            for point_id in point_ids:
                                av = layer_lookup[point_id, case_a, hour, layer][field_name]
                                bv = layer_lookup[point_id, case_b, hour, layer][field_name]
                                differences.append(av - bv if av is not None and bv is not None else None)
                            contrasts.append({'cohort_label': role, 'lead_hour': lead,
                                              'time_role': label, 'hour_utc': hour, 'layer_agl': layer,
                                              'field': field_name, 'contrast': contrast,
                                              'population': population, **summarize(differences)})
        for event, control_id in zip(role_events, populations['matched_control']):
            point_id = event['flat_index_yx']
            for population, sample_id in (('target', point_id), ('matched_control', control_id)):
                lead = event['lead_hour']
                surface = surface_lookup[sample_id, 'A', lead]
                sample = {'cohort_label': role, 'population': population,
                          'target_flat_index_yx': point_id, 'flat_index_yx': sample_id,
                          'lead_hour': lead, 'hour_utc': 12 + lead,
                          'threshold_mm': event['threshold_mm'], 'observed_band': event['observed_band'],
                          'transition': event['transition'], 'RN1_reference_mm': surface['RN1_reference_mm'],
                          'new_h05_5mm_FA_target': role == 'h05_A_C_5mm_new_FA' and population == 'target',
                          'ORIGINAL_already_ge_5mm': surface_lookup[sample_id, 'ORIGINAL', lead]['surface_total_mm'] >= 5.0,
                          'X_already_ge_5mm': surface_lookup[sample_id, 'B1_OLD_KDM6', lead]['surface_total_mm'] >= 5.0}
                for case in CASES:
                    values = surface_lookup[sample_id, case, lead]
                    sample[f'{case}_RAINC_increment_mm'] = values['RAINC_increment_mm']
                    sample[f'{case}_RAINNC_increment_mm'] = values['RAINNC_increment_mm']
                    sample[f'{case}_total_mm'] = values['surface_total_mm']
                    sample[f'{case}_crossed_role_threshold'] = values['surface_total_mm'] >= event['threshold_mm']
                sample['all_old_cases_below_5mm'] = all(sample[f'{case}_total_mm'] < 5.0
                                                        for case in ('ORIGINAL', 'A', 'B1_OLD_KDM6'))
                surface_context.append(sample)
        for population in ('target', 'matched_control'):
            sample_ids = populations[population]
            lead = role_events[0]['lead_hour']
            threshold = role_events[0]['threshold_mm']
            for case in (*CASES, 'RN1_REFERENCE'):
                values = [surface_lookup[key, case, lead]['surface_total_mm'] if case != 'RN1_REFERENCE'
                          else surface_lookup[key, 'A', lead]['RN1_reference_mm'] for key in sample_ids]
                stats = summarize(values)
                ge = sum(value is not None and value >= threshold for value in values)
                surface_summary.append({'cohort_label': role, 'population': population, 'lead_hour': lead,
                                        'hour_utc': 12 + lead, 'threshold_mm': threshold, 'case': case,
                                        'n_points': len(sample_ids), 'n_crossed_role_threshold': ge, **stats})
            if role == 'h05_A_C_5mm_new_FA' and population == 'target':
                rows = [row for row in surface_context if row['cohort_label'] == role and row['population'] == population]
                flags = {'new_FA_target_count': len(rows),
                         'ORIGINAL_already_ge_5mm_count': sum(row['ORIGINAL_already_ge_5mm'] for row in rows),
                         'X_already_ge_5mm_count': sum(row['X_already_ge_5mm'] for row in rows),
                         'all_old_cases_below_5mm_count': sum(row['all_old_cases_below_5mm'] for row in rows)}
                for row in surface_summary[-(len(CASES) + 1):]:
                    row.update(flags)
    return {'point_surface_paths': surface_rows, 'layer_features': layer_rows,
            'cohort_physical_contrasts': contrasts, 'cohort_surface_context': surface_context,
            'cohort_surface_context_summary': surface_summary,
            '_layer_lookup': layer_lookup, '_surface_checks': surface_checks}


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ContextError(f'required output table is empty: {path.name}')
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def run(state_dir: Path = STATE, targets_dir: Path = TARGETS, scores_dir: Path = SCORES,
        output: Path = OUTPUT, command: list[str] | None = None) -> dict:
    output = Path(output)
    if os.path.lexists(output):
        raise ContextError(f'output already exists: {output}')
    state_receipt, state_arrays, focus, events, controls, scores, pins = load_inputs(state_dir, targets_dir, scores_dir)
    tables = derive_context(state_arrays, focus, events, controls, scores)
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.context-', dir=output.parent))
    try:
        names = ('point_surface_paths', 'layer_features', 'cohort_physical_contrasts',
                 'cohort_surface_context', 'cohort_surface_context_summary')
        for name in names:
            write_csv(stage / f'{name}.csv', tables[name])
        source_files = [pins['state_receipt'], pins['state_plan'], pins['target_receipt'],
                        pins['target_source_receipt'], identity(Path(__file__))]
        source_files.extend(pins['target_tables'].values())
        source_files.extend(pins['score_arrays'])
        source_files.extend(identity(Path(state_dir) / f'{case}_h{hour}.npz') for case in CASES for hour in HOURS)
        outputs = {}
        for path in sorted(stage.iterdir()):
            row = identity(path)
            row['path'] = str(output / path.name)
            outputs[path.name] = row
        receipt = {'schema': 'cp02_b1_failure_context_v1', 'status': 'COMPLETE',
                   'command_argv': command or ['python', 'tools/cp02_b1_failure_context.py',
                                               '--output', str(output)],
                   'exit_status': 0, 'state_receipt_sha256': STATE_RECEIPT_SHA256,
                   'state_plan_sha256': STATE_PLAN_SHA256, 'target_receipt_sha256': TARGET_RECEIPT_SHA256,
                   'cases': list(CASES), 'hours_utc': list(HOURS), 'focus_points': len(focus),
                   'event_rows': len(events), 'matched_control_rows': len(controls),
                   'surface_score_checks': tables['_surface_checks'],
                   'outputs': outputs,
                   'sources': source_files,
                   'limits': ['History fields are sealed Eulerian snapshots, not native KDM6 process states.',
                              'Layer averages are unweighted model-level means per native corner followed by fixed bilinear weights; no mass weighting or renormalization.',
                              'Matched controls are cohort-specific analysis controls; repeated points across roles do not make independent samples.',
                              'No causal mechanism, physical equivalence, trajectory, or water/energy budget is inferred.']}
        (stage / 'bundle_receipt.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        os.rename(stage, output)
        receipt['bundle_receipt_sha256'] = identity(output / 'bundle_receipt.json')['sha256']
        return receipt
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, default=STATE)
    parser.add_argument('--targets', type=Path, default=TARGETS)
    parser.add_argument('--scores', type=Path, default=SCORES)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    print(json.dumps(run(args.state, args.targets, args.scores, args.output,
                         ['python', *sys.argv]), sort_keys=True))


if __name__ == '__main__':
    main()
