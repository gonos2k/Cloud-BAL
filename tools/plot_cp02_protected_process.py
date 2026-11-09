#!/usr/bin/env python3
"""Render receipt-bound whole-domain, spatial, and QRAIN diagnostics."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import zipfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.ticker import FuncFormatter
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / 'docs/evidence/cp02_protected_process_20261106'
COHORTS = BUNDLE / 'cohorts'
CONTEXT = BUNDLE / 'residual_fix/context'
PLAN = BUNDLE / 'analysis_plan.json'
OUTPUT = BUNDLE / 'figures'
RUNTIME = ROOT.parent / 'runtime'
FONT = Path('/usr/share/fonts/truetype/nanum/NanumGothic.ttf')
BOUNDARY_PATH = ROOT / 'docs/evidence/cp02_grouped_forecast_20261105/figures/data/ne_50m_coastline.geojson'
BOUNDARY_SHA256 = '271f1c4c1908312bac6b29d158ea1356544beafc129f260005300913aa5ea283'
BOUNDARY_URL = 'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/ca96624a56bd078437bca8184e78163e5039ad19/geojson/ne_50m_coastline.geojson'
PLAN_SHA256 = 'c14da5350a21957eea0e320e5b6cb4da3c8ca82430c38b98cfc096c0c4b24d6f'
COHORT_RECEIPT_SHA256 = 'cd1e03fbc075c25f6a4904ce278935dea8d23a2157162274835fca21fc911826'
CONTEXT_RECEIPT_SHA256 = '8faf1ae646279e9bce55472cbd8930997cbc1fd7ca6db06bfa0fb1ff45d11077'
FONT_SHA256 = '48a28e97b34fc8e5b157657633670cd1b7de126cfc414da65ce9c3d5bc8be733'
HOURS = tuple(range(13, 19))
WEAK_THRESHOLDS = (0.1, 0.5, 1.0)
COMPARISONS = ('ORIGINAL_to_FIX', 'X_to_A', 'ORIGINAL_to_A', 'C_to_A', 'A_to_C')
ROLE_COUNTS = {
    'plus2_XA_weak_gain': 2, 'plus2_XA_weak_loss': 10, 'plus2_OA_weak_loss': 10,
    'plus2_XA_new_false_alarm': 33, 'plus2_XA_resolved_false_alarm': 30,
    'plus2_OA_new_false_alarm': 53, 'plus2_OA_resolved_false_alarm': 24,
    'plus2_prior_retained_controls': 10, 'plus5_C_A_weak_loss': 17,
    'plus2_OA_nearest_Awet_RN1zero_neighbor': 4,
    'plus5_protected_weak_X_miss_A_hit_C_miss': 11,
    'plus5_remaining_weak_loss_X_hit_A_hit_C_miss': 6,
    'plus5_strong_protected_hit_12299': 1, 'plus5_C_strong_new_false_alarm': 12,
    'plus5_protected_strong_X_FA_A_resolved_C_FA': 7,
}
ROLE_LABELS = {
    'plus2_OA_weak_loss': '규준실험 → 현재 B1 약한 적중 소실 (n=10)',
    'plus2_XA_weak_loss': 'B1 초기장·OLD (X) → 현재 B1 약한 적중 소실 (n=10)',
    'plus2_prior_retained_controls': '+2 h 규준실험→현재 B1 약한 적중 matched controls (n=10)',
    'plus2_XA_new_false_alarm': '현재 B1 신규 오경보 (n=33)',
    'plus2_XA_resolved_false_alarm': '현재 B1 해소 오경보 (n=30)',
    'plus2_OA_nearest_Awet_RN1zero_neighbor': '규준실험 → 현재 B1: 관측 0 mm·예측 습윤 이웃 (n=4)',
    'plus5_protected_weak_X_miss_A_hit_C_miss': '+5 h 보호 약한 적중 · X 실패/A 적중/C 실패 (n=11)',
    'plus5_strong_protected_hit_12299': '+5 h 보호 5 mm 적중 · 12299 (n=1)',
    'plus5_protected_strong_X_FA_A_resolved_C_FA': '+5 h 보호 오경보 해소 · C 재발 (n=7)',
}
ROLE_STYLE = {
    'plus2_OA_weak_loss': ('#1769aa', 'o'),
    'plus2_XA_weak_loss': ('#303f9f', 'P'),
    'plus2_prior_retained_controls': ('#7e57c2', 'o'),
    'plus2_XA_new_false_alarm': ('#c62828', '^'),
    'plus2_XA_resolved_false_alarm': ('#00897b', 's'),
    'plus2_OA_nearest_Awet_RN1zero_neighbor': ('#212121', 'h'),
    'plus5_protected_weak_X_miss_A_hit_C_miss': ('#ef6c00', 'D'),
    'plus5_strong_protected_hit_12299': ('#6a1b9a', '*'),
    'plus5_protected_strong_X_FA_A_resolved_C_FA': ('#ad1457', 'X'),
}
CONTEXT_TABLES = ('layer_features.csv', 'point_surface_paths.csv')
COHORT_TABLES = ('categorical_scores.csv', 'transitions.csv', 'role_membership.csv',
                 'selected_points.csv', 'nearest_neighbors.csv', 'qrain_point_contrasts.csv',
                 'qrain_group_summary.csv')


class PlotInputError(ValueError):
    """A source receipt or selected plotting population is invalid."""


def sha256(path: Path) -> str:
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def require_pinned(path: Path, digest: str, label: str) -> None:
    if not path.is_file() or path.is_symlink() or sha256(path) != digest:
        raise PlotInputError(f'{label} is missing or differs from its pinned hash: {path}')


def read_csv(path: Path, fields: set[str]) -> list[dict[str, str]]:
    if not path.is_file() or path.is_symlink():
        raise PlotInputError(f'required table is missing: {path}')
    with path.open(newline='', encoding='utf-8') as stream:
        reader = csv.DictReader(stream)
        if not fields <= set(reader.fieldnames or ()):
            raise PlotInputError(f'{path.name}: required columns are missing')
        rows = list(reader)
    if not rows:
        raise PlotInputError(f'{path.name}: table has no data rows')
    return rows


def verify_output_files(directory: Path, receipt: dict, names: tuple[str, ...]) -> dict[str, str]:
    outputs = receipt.get('outputs', {})
    digests = {}
    for name in names:
        record = outputs.get(name)
        path = directory / name
        if not record or not path.is_file() or path.is_symlink():
            raise PlotInputError(f'{name}: receipt-bound input is missing')
        actual_hash = sha256(path)
        expected_hash = record if isinstance(record, str) else record.get('sha256')
        expected_size = None if isinstance(record, str) else record.get('size_bytes')
        if actual_hash != expected_hash or (expected_size is not None and path.stat().st_size != expected_size):
            raise PlotInputError(f'{name}: receipt-bound input hash or size differs')
        digests[name] = actual_hash
    return digests


def verify_cohort_sources(root: Path, receipt: dict) -> None:
    for relative, digest in receipt.get('inputs', {}).items():
        require_pinned(root / relative, digest, f'cohort source {relative}')


def read_boundary(path: Path) -> list[np.ndarray]:
    payload = json.loads(path.read_text(encoding='utf-8'))
    features = payload.get('features', []) if payload.get('type') == 'FeatureCollection' else [payload]
    lines = []
    for feature in features:
        geometry = feature.get('geometry', feature)
        kind, coordinates = geometry.get('type'), geometry.get('coordinates')
        segments = [coordinates] if kind == 'LineString' else coordinates if kind == 'MultiLineString' else []
        for segment in segments:
            line = np.asarray(segment, dtype=np.float64)
            if line.ndim != 2 or line.shape[1] < 2 or not np.isfinite(line[:, :2]).all():
                raise PlotInputError('coastline coordinates must be finite longitude/latitude pairs')
            lines.append(line[:, :2])
    if not lines:
        raise PlotInputError('pinned coastline has no line geometry')
    return lines


def load_weak_hit_counts(root: Path, receipt: dict) -> dict:
    """Count forecasts >=0.1 mm only within observed 0.1<=RN1<1 mm points."""
    filenames = [f'docs/evidence/weak_strong_balance_20261030/analysis/hour_{hour}_arrays.npz'
                 for hour in HOURS]
    output = {}
    flat_order = None
    case_pairs = {
        'ORIGINAL_initialization': ('ORIGINAL', 'FIXED_ORIGINAL_100'),
        'B1_initialization': ('ORIGINAL_B1_100', 'IMPROVED_BG_FIXED'),
    }
    for hour, relative in zip(HOURS, filenames):
        if relative not in receipt.get('inputs', {}):
            raise PlotInputError(f'cohort receipt does not bind {relative}')
        path = root / relative
        require_pinned(path, receipt['inputs'][relative], f'weak-detection score array {hour}')
        with np.load(path, allow_pickle=False) as archive:
            required = {'flat_index_yx', 'reference', *(case for pair in case_pairs.values() for case in pair)}
            if not required <= set(archive.files):
                raise PlotInputError(f'hour {hour}: weak-detection arrays are incomplete')
            flat = np.asarray(archive['flat_index_yx'])
            reference = np.asarray(archive['reference'], dtype=np.float64)
            forecasts = {case: np.asarray(archive[case], dtype=np.float64)
                         for pair in case_pairs.values() for case in pair}
        if (flat.shape != (3688,) or reference.shape != flat.shape or len(np.unique(flat)) != flat.size
            or not np.isfinite(reference).all()
            or any(values.shape != flat.shape or not np.isfinite(values).all() for values in forecasts.values())):
            raise PlotInputError(f'hour {hour}: invalid full-population weak-detection arrays')
        if flat_order is not None and not np.array_equal(flat, flat_order):
            raise PlotInputError(f'hour {hour}: canonical point order differs across score arrays')
        flat_order = flat
        observed_weak = (reference >= 0.1) & (reference < 1.0)
        row = {'n_weak_observations': int(observed_weak.sum()), 'n_grid_points': int(flat.size), 'pairs': {}}
        for label, (before_case, after_case) in case_pairs.items():
            before = int(np.count_nonzero(observed_weak & (forecasts[before_case] >= 0.1)))
            after = int(np.count_nonzero(observed_weak & (forecasts[after_case] >= 0.1)))
            row['pairs'][label] = {'before_case': before_case, 'after_case': after_case,
                                   'before_hits': before, 'after_hits': after, 'delta_hits': after - before}
        output[hour] = row
    expected = {(13, 'ORIGINAL_initialization'): (218, 249),
                (13, 'B1_initialization'): (219, 246),
                (14, 'B1_initialization'): (238, 230),
                (17, 'B1_initialization'): (262, 258)}
    for (hour, label), pair in expected.items():
        counts = output[hour]['pairs'][label]
        if (counts['before_hits'], counts['after_hits']) != pair:
            raise PlotInputError(f'{hour}/{label}: frozen observed-weak recount differs')
    return output


def read_point_coordinates(root: Path, receipt: dict, points: list[dict[str, str]]) -> dict[int, tuple[float, float]]:
    source_name = 'docs/evidence/weak_strong_balance_20261030/analysis/hour_14_arrays.npz'
    expected = receipt.get('inputs', {}).get(source_name)
    if not expected:
        raise PlotInputError('cohort receipt does not bind the +2 h coordinate array')
    path = root / source_name
    require_pinned(path, expected, 'coordinate array')
    with np.load(path, allow_pickle=False) as archive:
        required = {'flat_index_yx', 'latitude', 'longitude'}
        if not required <= set(archive.files):
            raise PlotInputError('coordinate array is missing point keys or coordinates')
        flat = np.asarray(archive['flat_index_yx'])
        latitude = np.asarray(archive['latitude'], dtype=np.float64)
        longitude = np.asarray(archive['longitude'], dtype=np.float64)
    if (flat.shape != (3688,) or latitude.shape != flat.shape or longitude.shape != flat.shape
        or len(np.unique(flat)) != flat.size or not np.isfinite(latitude).all()
        or not np.isfinite(longitude).all()):
        raise PlotInputError('coordinate array has an invalid 3,688-point population')
    coordinates = {int(key): (float(lon), float(lat))
                   for key, lon, lat in zip(flat, longitude, latitude)}
    for row in points:
        key = int(row['flat_index_yx'])
        if key not in coordinates or not np.allclose(
                coordinates[key], (float(row['longitude']), float(row['latitude'])), rtol=0, atol=1e-6):
            raise PlotInputError(f'point {key}: coordinates differ from the paired score array')
    return coordinates


def validate_roles(receipt: dict, role_rows: list[dict[str, str]], point_rows: list[dict[str, str]]) -> dict[int, set[str]]:
    if receipt.get('role_counts') != ROLE_COUNTS:
        raise PlotInputError('cohort role counts differ from the frozen scope')
    if receipt.get('point_count_deduplicated') != 150:
        raise PlotInputError('cohort point population differs from the frozen receipt')
    memberships: dict[int, set[str]] = {}
    for row in role_rows:
        key, role = int(row['flat_index_yx']), row['role']
        if role not in ROLE_COUNTS or role in memberships.setdefault(key, set()):
            raise PlotInputError('role membership has an unknown or duplicate point-role pair')
        memberships[key].add(role)
    counts = {role: sum(role in roles for roles in memberships.values()) for role in ROLE_COUNTS}
    if counts != ROLE_COUNTS or len(memberships) != 150:
        raise PlotInputError('role membership does not match the frozen populations')
    point_roles = {}
    for row in point_rows:
        key = int(row['flat_index_yx'])
        if key in point_roles:
            raise PlotInputError(f'point {key}: selected point appears more than once')
        point_roles[key] = set(filter(None, row['roles'].split(';')))
    if point_roles != memberships:
        raise PlotInputError('selected point roles disagree with role membership')
    return memberships


def validate_scores(score_rows: list[dict[str, str]], transition_rows: list[dict[str, str]]) -> dict:
    expected_keys = {(str(hour), comparison, str(threshold))
                     for hour in HOURS for comparison in COMPARISONS for threshold in (0.1, 0.5, 1.0, 2.5, 5.0, 10.0)}
    scores, transitions = {}, {}
    for row in score_rows:
        key = (row['valid_hour_utc'], row['comparison'], row['threshold_mm'])
        if key in scores or int(row['n']) != 3688:
            raise PlotInputError('categorical table has a duplicate key or non-whole-domain denominator')
        scores[key] = row
    for row in transition_rows:
        key = (row['valid_hour_utc'], row['comparison'], row['threshold_mm'])
        if key in transitions:
            raise PlotInputError('transition table has a duplicate comparison key')
        transitions[key] = row
    if set(scores) != expected_keys or set(transitions) != expected_keys:
        raise PlotInputError('score or transition table is incomplete for all six hours and thresholds')
    return {'scores': scores, 'transitions': transitions}


def validate_qrain(rows: list[dict[str, str]], summaries: list[dict[str, str]],
                   layer_rows: list[dict[str, str]]) -> dict:
    by_point = {}
    for row in rows:
        key = (row['role'], row['flat_index_yx'])
        if key in by_point or row['hour_utc'] != '13' or row['layer_agl'] != '[0,1000)m':
            raise PlotInputError('QRAIN table has duplicate points or an unexpected time/layer')
        if (row['X_case'] != 'B1_OLD_KDM6' or row['A_case'] != 'A'
            or not row['point_id'].endswith(row['flat_index_yx'])):
            raise PlotInputError('QRAIN table has an unexpected comparison or point identity')
        by_point[key] = row
    expected_roles = {'plus2_OA_weak_loss': 10, 'plus2_prior_retained_controls': 10}
    for role, count in expected_roles.items():
        if sum(key[0] == role for key in by_point) != count:
            raise PlotInputError(f'{role}: QRAIN point count differs from {count}')
    if len(by_point) != sum(expected_roles.values()):
        raise PlotInputError('QRAIN table contains unexpected roles or points')
    layers = {(row['flat_index_yx'], row['case'], row['hour_utc'], row['layer_agl']): row
              for row in layer_rows}
    grouped = {}
    for (role, point), row in by_point.items():
        for case, column in (('B1_OLD_KDM6', 'X_QRAIN_mgkg'), ('A', 'A_QRAIN_mgkg')):
            layer = layers.get((point, case, '13', '[0,1000)m'))
            if not layer or layer['QRAIN_kgkg_valid'] != 'True':
                raise PlotInputError(f'{point}/{case}: paired lower-layer QRAIN is unavailable')
            expected = float(layer['QRAIN_kgkg']) * 1e6
            actual = float(row[column])
            if not np.isfinite(actual) or actual < 0 or not np.isclose(expected, actual, rtol=0, atol=1e-9):
                raise PlotInputError(f'{point}/{case}: QRAIN differs from the receipt-bound context table')
        x, a, delta = (float(row[column]) for column in
                       ('X_QRAIN_mgkg', 'A_QRAIN_mgkg', 'pointwise_A_minus_X_mgkg'))
        if not np.isclose(delta, a - x, rtol=0, atol=1e-10):
            raise PlotInputError(f'{point}: pointwise QRAIN delta differs from A-X')
        grouped.setdefault(role, {'x': [], 'a': [], 'delta': []})
        grouped[role]['x'].append(x); grouped[role]['a'].append(a); grouped[role]['delta'].append(delta)
    summary_map = {row['role']: row for row in summaries}
    if set(summary_map) != set(expected_roles):
        raise PlotInputError('QRAIN group summary has missing or unexpected groups')
    for role, values in grouped.items():
        summary = summary_map[role]
        if int(summary['n']) != expected_roles[role]:
            raise PlotInputError(f'{role}: QRAIN summary denominator differs')
        for key, column in (('x', 'median_X_QRAIN_mgkg'), ('a', 'median_A_QRAIN_mgkg'),
                            ('delta', 'median_pointwise_A_minus_X_mgkg')):
            if not np.isclose(float(summary[column]), np.median(values[key]), rtol=0, atol=1e-10):
                raise PlotInputError(f'{role}: reported {column} differs from pointwise values')
    return grouped


def load_inputs(cohorts_dir: Path = COHORTS, context_dir: Path = CONTEXT, plan_path: Path = PLAN,
                *, root: Path = ROOT, cohort_receipt_sha256: str = COHORT_RECEIPT_SHA256,
                plan_sha256: str = PLAN_SHA256, context_receipt_sha256: str = CONTEXT_RECEIPT_SHA256) -> dict:
    cohorts_dir, context_dir, plan_path, root = map(Path, (cohorts_dir, context_dir, plan_path, root))
    cohort_receipt_path = cohorts_dir / 'receipt.json'
    context_receipt_path = context_dir / 'bundle_receipt.json'
    require_pinned(plan_path, plan_sha256, 'frozen analysis plan')
    require_pinned(cohort_receipt_path, cohort_receipt_sha256, 'cohort tool receipt')
    require_pinned(context_receipt_path, context_receipt_sha256, 'context receipt')
    plan = json.loads(plan_path.read_text(encoding='utf-8'))
    receipt = json.loads(cohort_receipt_path.read_text(encoding='utf-8'))
    context_receipt = json.loads(context_receipt_path.read_text(encoding='utf-8'))
    if (plan.get('status') != 'FROZEN_DIAGNOSTIC_SCOPE' or receipt.get('status') != 'COMPLETE'
        or receipt.get('hours_utc') != list(HOURS) or context_receipt.get('status') != 'COMPLETE'
        or context_receipt.get('cases') != ['ORIGINAL', 'A', 'C', 'B1_OLD_KDM6']):
        raise PlotInputError('input plan or receipt status/inventory differs')
    verify_cohort_sources(root, receipt)
    cohort_hashes = verify_output_files(cohorts_dir, receipt, tuple(receipt.get('outputs', {})))
    context_hashes = verify_output_files(context_dir, context_receipt, CONTEXT_TABLES)
    score_rows = read_csv(cohorts_dir / 'categorical_scores.csv',
                          {'valid_hour_utc', 'lead_hour', 'comparison', 'threshold_mm', 'n', 'hit'})
    transition_rows = read_csv(cohorts_dir / 'transitions.csv',
                               {'valid_hour_utc', 'comparison', 'threshold_mm', 'hit_gains', 'hit_losses',
                                'new_false_alarms', 'resolved_false_alarms'})
    role_rows = read_csv(cohorts_dir / 'role_membership.csv', {'flat_index_yx', 'role'})
    point_rows = read_csv(cohorts_dir / 'selected_points.csv',
                          {'point_id', 'flat_index_yx', 'latitude', 'longitude', 'roles'})
    nearest_rows = read_csv(cohorts_dir / 'nearest_neighbors.csv',
                            {'role', 'loss_flat_index_yx', 'nearest_A_hit_flat_index_yx',
                             'nearest_distance_km', 'loss_reference_mm', 'neighbor_reference_mm',
                             'neighbor_A_mm', 'canonical_points_within_5km',
                             'canonical_points_within_10km', 'canonical_points_within_20km',
                             'A_hit_points_within_5km', 'A_hit_points_within_10km',
                             'A_hit_points_within_20km', '5km_radius_self_only'})
    qrain_rows = read_csv(cohorts_dir / 'qrain_point_contrasts.csv',
                          {'role', 'flat_index_yx', 'point_id', 'hour_utc', 'layer_agl', 'X_case', 'A_case',
                           'X_QRAIN_mgkg', 'A_QRAIN_mgkg', 'pointwise_A_minus_X_mgkg'})
    qrain_summaries = read_csv(cohorts_dir / 'qrain_group_summary.csv',
                               {'role', 'n', 'median_X_QRAIN_mgkg', 'median_A_QRAIN_mgkg',
                                'median_pointwise_A_minus_X_mgkg'})
    layer_rows = read_csv(context_dir / 'layer_features.csv',
                          {'flat_index_yx', 'case', 'hour_utc', 'layer_agl', 'QRAIN_kgkg_valid', 'QRAIN_kgkg'})
    score_tables = validate_scores(score_rows, transition_rows)
    memberships = validate_roles(receipt, role_rows, point_rows)
    qrain_groups = validate_qrain(qrain_rows, qrain_summaries, layer_rows)
    coordinates = read_point_coordinates(root, receipt, point_rows)
    weak_hit_counts = load_weak_hit_counts(root, receipt)
    require_pinned(BOUNDARY_PATH, BOUNDARY_SHA256, 'Natural Earth coastline')
    boundary_lines = read_boundary(BOUNDARY_PATH)
    point_map = {int(row['flat_index_yx']): row for row in point_rows}
    if len(nearest_rows) != 20:
        raise PlotInputError('nearest-neighbor table must include 10 OA and 10 XA weak-loss rows')
    nearest_counts = {'plus2_OA_weak_loss': 0, 'plus2_XA_weak_loss': 0}
    for row in nearest_rows:
        role = row['role']
        if role not in ('plus2_OA_weak_loss', 'plus2_XA_weak_loss'):
            raise PlotInputError('nearest-neighbor row has an unexpected weak-loss role')
        nearest_counts[role] += 1
        loss_id, neighbor_id = int(row['loss_flat_index_yx']), int(row['nearest_A_hit_flat_index_yx'])
        if (loss_id not in point_map or loss_id not in coordinates or neighbor_id not in coordinates
            or float(row['nearest_distance_km']) < 0 or float(row['neighbor_A_mm']) < 0.1):
            raise PlotInputError('nearest predicted-wet point is absent or invalid')
        if role not in memberships.get(loss_id, set()):
            raise PlotInputError(f'{loss_id}: nearest-neighbor role differs from role membership')
        canonical = [int(row[f'canonical_points_within_{radius}km']) for radius in (5, 10, 20)]
        wet = [int(row[f'A_hit_points_within_{radius}km']) for radius in (5, 10, 20)]
        if (canonical != sorted(canonical) or wet != sorted(wet)
            or str(canonical[0] == 1).lower() != row['5km_radius_self_only'].lower()):
            raise PlotInputError('5/10/20-km neighborhood counts are inconsistent or mislabeled')
    if nearest_counts != {'plus2_OA_weak_loss': 10, 'plus2_XA_weak_loss': 10}:
        raise PlotInputError('nearest-neighbor roles do not each contain 10 loss points')
    arrows = sorted((row for row in nearest_rows if row['role'] == 'plus2_OA_weak_loss'
                     and float(row['neighbor_reference_mm']) == 0.0),
                    key=lambda row: float(row['nearest_distance_km']))[:4]
    if len(arrows) != 4 or len({row['loss_flat_index_yx'] for row in arrows}) != 4:
        raise PlotInputError('four distinct OA observed-zero nearest predicted-wet pairs are required')
    arrow_neighbors = {int(row['nearest_A_hit_flat_index_yx']) for row in arrows}
    designated_neighbors = {key for key, roles in memberships.items()
                            if 'plus2_OA_nearest_Awet_RN1zero_neighbor' in roles}
    if arrow_neighbors != designated_neighbors:
        raise PlotInputError('four OA observed-zero arrow endpoints differ from the frozen neighbor role')
    return {'plan': plan, 'plan_sha256': sha256(plan_path), 'cohort_receipt': receipt,
            'cohort_receipt_sha256': sha256(cohort_receipt_path), 'context_receipt': context_receipt,
            'context_receipt_sha256': sha256(context_receipt_path), 'cohort_hashes': cohort_hashes,
            'context_hashes': context_hashes, 'scores': score_tables['scores'],
            'transitions': score_tables['transitions'], 'memberships': memberships,
            'points': point_map, 'coordinates': coordinates, 'nearest_rows': nearest_rows,
            'zero_observation_arrows': arrows, 'weak_hit_counts': weak_hit_counts,
            'boundary_lines': boundary_lines, 'qrain_rows': qrain_rows,
            'qrain_summaries': qrain_summaries, 'qrain_groups': qrain_groups,
            'font': FONT}


def configure_font() -> None:
    font_manager.fontManager.addfont(str(FONT))
    name = font_manager.FontProperties(fname=str(FONT)).get_name()
    plt.rcParams.update({'font.family': name, 'axes.unicode_minus': False,
                         'savefig.dpi': 170, 'figure.facecolor': 'white'})


def make_weak_hits_plot(data: dict, path: Path) -> None:
    comparisons = (
        ('규준실험 초기장: ORIGINAL → FIX', 'ORIGINAL_initialization', 'ORIGINAL', 'FIX'),
        ('B1 초기장: OLD (X) → FIX (A)', 'B1_initialization', 'X/OLD', 'FIX (A)'),
    )
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5), sharey=True, constrained_layout=False)
    colors = ('#7b8794', '#1565c0')
    for ax, (title, key, before_label, after_label) in zip(axes, comparisons):
        weak_denominators = []
        for hour_index, hour in enumerate(HOURS):
            counts = data['weak_hit_counts'][hour]
            pair = counts['pairs'][key]
            weak_denominators.append(counts['n_weak_observations'])
            before, after = pair['before_hits'], pair['after_hits']
            width, center = .34, float(hour_index)
            ax.bar(center - width/2, before, width, color=colors[0], zorder=2)
            ax.bar(center + width/2, after, width, color=colors[1], zorder=2)
            ax.text(center, max(before, after) + 5, f"{pair['delta_hits']:+d}",
                    ha='center', va='bottom', fontsize=8, color='#30343b')
        ax.set_title(title)
        ax.set_xticks(range(6), [f'+{i} h\nn={count}' for i, count in enumerate(weak_denominators, 1)])
        ax.set_xlabel('예측시간')
        ax.grid(axis='y', alpha=.22, zorder=0)
        ax.set_ylim(0, 310)
    axes[0].set_ylabel('적중 관측 약한 강수점 수\n(0.1 ≤ RN1 < 1 mm, 예측 ≥ 0.1 mm)')
    handles = [plt.Line2D([0], [0], color=colors[0], linewidth=8, label='비교 전'),
               plt.Line2D([0], [0], color=colors[1], linewidth=8, label='FIX')]
    fig.legend(handles=handles, loc='upper center', ncol=2, frameon=False, bbox_to_anchor=(0.5, .91))
    fig.suptitle('관측 약한 강수점의 전 영역 탐지 수: 각 초기장별 비교', y=.99, fontsize=15)
    fig.text(.5, .025,
             '각 막대는 3,688개 전체 격자에서 관측 0.1-<1 mm인 점 중 예측 ≥0.1 mm인 탐지 수입니다. x축 n은 해당 시간의 약한 강수 관측점 분모; 막대 위 Δ=FIX - 비교 전입니다.',
             ha='center', fontsize=9)
    fig.subplots_adjust(left=.12, right=.99, bottom=.16, top=.82, wspace=.12)
    fig.savefig(path, bbox_inches='tight', metadata={'Software': 'CP02 protected process plotter'})
    plt.close(fig)


def make_failure_map(data: dict, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(11, 9), constrained_layout=False)
    styles = ROLE_STYLE
    plot_roles = tuple(styles)
    all_xy = []
    for role in plot_roles:
        ids = sorted(key for key, roles in data['memberships'].items() if role in roles)
        if not ids:
            raise PlotInputError(f'{role}: map population is empty')
        color, marker = styles[role]
        points = np.asarray([data['coordinates'][key] for key in ids])
        all_xy.extend(points.tolist())
        ax.scatter(points[:, 0], points[:, 1], s=45 if role != 'plus5_strong_protected_hit_12299' else 130,
                   marker=marker, c=color, edgecolors='white' if marker not in ('X', '*') else color,
                   linewidths=.7, alpha=.9, label=ROLE_LABELS[role], zorder=3)
    for index, row in enumerate(data['zero_observation_arrows'], 1):
        source = int(row['loss_flat_index_yx'])
        target = int(row['nearest_A_hit_flat_index_yx'])
        x0, y0 = data['coordinates'][source]
        x1, y1 = data['coordinates'][target]
        ax.annotate('', xy=(x1, y1), xytext=(x0, y0),
                    arrowprops={'arrowstyle': '->', 'color': '#111111', 'lw': 1.0, 'alpha': .75}, zorder=5)
        ax.annotate(str(index), xy=((x0 + x1)/2, (y0 + y1)/2), xytext=(4 + (index % 2) * 5, 4 + (index % 3) * 4),
                    textcoords='offset points', fontsize=7, color='black',
                    bbox={'boxstyle': 'circle,pad=.15', 'facecolor': 'white', 'edgecolor': '#555555', 'linewidth': .5},
                    ha='center', va='center', zorder=6)
    for line in data['boundary_lines']:
        ax.plot(line[:, 0], line[:, 1], color='#9aa3aa', linewidth=.35, alpha=.55, zorder=1)
    all_xy = np.asarray(all_xy)
    ax.set_xlim(all_xy[:, 0].min() - .30, all_xy[:, 0].max() + .30)
    ax.set_ylim(all_xy[:, 1].min() - .25, all_xy[:, 1].max() + .25)
    ax.set_xlabel('경도 (°E)')
    ax.set_ylabel('위도 (°N)')
    ax.set_title('+2 h 실패·오경보 집단과 +5 h 보호 표본의 공간 위치')
    ax.grid(alpha=.22)
    ax.set_aspect(1 / np.cos(np.deg2rad(37.0)), adjustable='box')
    handles, labels = ax.get_legend_handles_labels()
    fig.legend(handles, labels, loc='upper left', bbox_to_anchor=(.68, .96),
               frameon=False, fontsize=7, ncol=1)
    fig.subplots_adjust(left=.08, right=.65, bottom=.14, top=.92)
    fig.text(.68, .02,
             '화살표 1–4는 규준실험→현재 B1 손실과 관측 0 mm인 가장 가까운 현재-B1 예측 습윤 표본을 연결합니다. 공간 이웃이며 폭풍 이동·인과가 아닙니다. 5 km는 평가점만 포함할 수 있고, 10/20 km는 별도 반경의 이웃 수입니다.',
             ha='left', va='bottom', fontsize=8, wrap=True)
    for index, row in enumerate(data['zero_observation_arrows'], 1):
        source, target = int(row['loss_flat_index_yx']), int(row['nearest_A_hit_flat_index_yx'])
        x0, y0 = data['coordinates'][source]
        x1, y1 = data['coordinates'][target]
        lat0 = (y0 + y1) / 2
        x0, x1 = (x0 - 127.0) * np.cos(np.deg2rad(lat0)), (x1 - 127.0) * np.cos(np.deg2rad(lat0))
        y0, y1 = y0 - lat0, y1 - lat0
        scale = 111.32
        x0, x1, y0, y1 = (value * scale for value in (x0, x1, y0, y1))
        pair_ax = fig.add_axes([.68 + ((index-1) % 2) * .16, .31 - ((index-1) // 2) * .19, .15, .16])
        pair_ax.set_facecolor('#fbfbfb')
        pair_ax.scatter(x0, y0, marker='o', s=28, color='#1769aa', zorder=3)
        pair_ax.scatter(x1, y1, marker='h', s=32, color='#212121', zorder=3)
        pair_ax.annotate('', xy=(x1, y1), xytext=(x0, y0),
                         arrowprops={'arrowstyle': '->', 'color': '#111111', 'lw': 1.1}, zorder=4)
        pair_ax.annotate(f"RN1 {source}\nobs {float(row['loss_reference_mm']):g} mm", xy=(x0, y0), xytext=(-3, -13),
                         textcoords='offset points', fontsize=5, ha='right', color='#1769aa', zorder=5)
        pair_ax.annotate(f"P {target}\nobs {float(row['neighbor_reference_mm']):.3g} · A {float(row['neighbor_A_mm']):.3g} mm",
                         xy=(x1, y1), xytext=(3, 7), textcoords='offset points', fontsize=5,
                         ha='left', color='#212121', zorder=5)
        pad = max(1.2, float(row['nearest_distance_km']) * .40)
        pair_ax.set_xlim(min(x0, x1)-pad, max(x0, x1)+pad)
        pair_ax.set_ylim(min(y0, y1)-pad, max(y0, y1)+pad)
        pair_ax.set_aspect('equal', adjustable='box')
        pair_ax.set_xticks([]); pair_ax.set_yticks([])
        pair_ax.set_title(f'{index}. {float(row["nearest_distance_km"]):.1f} km', fontsize=6, pad=1)
        pair_ax.grid(alpha=.15)
    fig.savefig(path, bbox_inches='tight', metadata={'Software': 'CP02 protected process plotter'})
    plt.close(fig)


def _median_iqr(values: list[float]) -> tuple[float, float, float]:
    q25, median, q75 = np.quantile(np.asarray(values, dtype=np.float64), (.25, .5, .75))
    return float(median), float(q25), float(q75)


def make_qrain_plot(data: dict, path: Path) -> None:
    points = data['qrain_rows']
    role_order = ('plus2_OA_weak_loss', 'plus2_prior_retained_controls')
    labels = ('약한 적중 소실 지점', 'matched-control 지점')
    grouped = {role: {case: [] for case in ('X_QRAIN_mgkg', 'A_QRAIN_mgkg')} for role in role_order}
    deltas = {role: [] for role in role_order}
    point_ids = {role: [] for role in role_order}
    for row in points:
        role = row['role']
        grouped[role]['X_QRAIN_mgkg'].append(float(row['X_QRAIN_mgkg']))
        grouped[role]['A_QRAIN_mgkg'].append(float(row['A_QRAIN_mgkg']))
        deltas[role].append(float(row['pointwise_A_minus_X_mgkg']))
        point_ids[role].append(int(row['flat_index_yx']))
    fig, axes = plt.subplots(1, 2, figsize=(14, 7), constrained_layout=False,
                             gridspec_kw={'width_ratios': (1.35, 1)})
    ax = axes[0]
    colors = {'X_QRAIN_mgkg': '#455a64', 'A_QRAIN_mgkg': '#1565c0'}
    positions = []
    position = 0
    rng = np.random.default_rng(135)
    for role, group_label in zip(role_order, labels):
        for case_key, case_label in (('X_QRAIN_mgkg', 'B1 초기장·OLD (X)'), ('A_QRAIN_mgkg', 'B1 초기장·FIX (A)')):
            values = grouped[role][case_key]
            x = position + rng.uniform(-.08, .08, len(values))
            ax.scatter(x, values, s=33, alpha=.78, color=colors[case_key], edgecolors='white', linewidths=.5,
                       zorder=3, label=case_label if position == 0 else None)
            median, q25, q75 = _median_iqr(values)
            ax.vlines(position, q25, q75, color='#111111', linewidth=3, zorder=4)
            ax.hlines(median, position-.14, position+.14, color='#111111', linewidth=2, zorder=5)
            positions.append(position)
            position += 1
        position += .5
    ax.set_xticks(positions, ['소실\nX', '소실\nA', '대조\nX', '대조\nA'])
    ax.set_ylabel('0–1 km 평균 QRAIN (mg kg⁻¹)')
    ax.set_yscale('symlog', linthresh=0.01, linscale=1)
    ax.set_ylim(0, 100)
    ax.set_yticks((0, .01, .1, 1, 10, 100))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _position: f'{value:g}'))
    ax.minorticks_off()
    ax.axhline(0, color='#777777', linewidth=.7)
    ax.grid(axis='y', which='both', alpha=.2)
    ax.set_title('절대 혼합비 · 개별 점과 각각 계산한 중앙값·사분위 범위')
    abs_summary = []
    for role, group_label in zip(role_order, labels):
        xstats = _median_iqr(grouped[role]['X_QRAIN_mgkg'])
        astats = _median_iqr(grouped[role]['A_QRAIN_mgkg'])
        abs_summary.append(f'{group_label}: X {xstats[0]:.3g} [{xstats[1]:.3g}, {xstats[2]:.3g}], '
                           f'A {astats[0]:.3g} [{astats[1]:.3g}, {astats[2]:.3g}]')
    ax.text(.02, .98, '\n'.join(abs_summary), transform=ax.transAxes, fontsize=7,
            ha='left', va='top', bbox={'facecolor': 'white', 'edgecolor': '#cccccc', 'alpha': .9})
    ax.text(.02, .02, 'symlog linear zone ±0.01 mg/kg; exact zero is shown at y=0',
            transform=ax.transAxes, fontsize=7, va='bottom')
    ax = axes[1]
    for index, (role, group_label) in enumerate(zip(role_order, labels)):
        values = deltas[role]
        x = index + rng.uniform(-.08, .08, len(values))
        ax.scatter(x, values, s=35, alpha=.82, color=('#1769aa', '#7e57c2')[index],
                   edgecolors='white', linewidths=.5, zorder=3)
        median, q25, q75 = _median_iqr(values)
        ax.vlines(index, q25, q75, color='#111111', linewidth=3, zorder=4)
        ax.hlines(median, index-.17, index+.17, color='#111111', linewidth=2, zorder=5)
    ax.axhline(0, color='#111111', linewidth=.8)
    ax.set_xticks((0, 1), ('소실 지점 (n=10)', 'matched control (n=10)'))
    ax.set_ylabel('점별 ΔQRAIN = B1 초기장·FIX (A) - B1 초기장·OLD (X), mg kg⁻¹')
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _position: f'{value:g}'))
    ax.minorticks_off()
    ax.set_yticks((-40, -30, -20, -10, 0, 10, 20))
    ax.set_ylim(-42, 20)
    ax.grid(axis='y', alpha=.2)
    ax.set_title('점별 paired Δ · median of differences')
    delta_summary = []
    for role, group_label in zip(role_order, labels):
        median, q25, q75 = _median_iqr(deltas[role])
        delta_summary.append(f'{group_label}: median {median:.3g}, IQR [{q25:.3g}, {q75:.3g}]')
    ax.text(.03, .98, '\n'.join(delta_summary), transform=ax.transAxes, fontsize=8,
            ha='left', va='top', bbox={'facecolor': 'white', 'edgecolor': '#cccccc', 'alpha': .9})
    fig.suptitle('+1 h UTC 13 · 선택된 약한 적중 소실 10점과 고정 대조점 10점', fontsize=14)
    fig.legend(handles=[plt.Line2D([0], [0], marker='o', linestyle='', color=colors['X_QRAIN_mgkg'],
                                  label='B1 초기장·OLD (X)'),
                       plt.Line2D([0], [0], marker='o', linestyle='', color=colors['A_QRAIN_mgkg'],
                                  label='B1 초기장·FIX (A)')],
               loc='upper center', ncol=2, frameon=False, bbox_to_anchor=(.44, .91))
    fig.text(.5, .025,
             '각 표본의 0–1 km 모형층 평균을 보입니다. X, A의 median은 각각 산출했고, 오른쪽은 20개 점별 A-X 차이의 median/IQR입니다. 서로 다른 집단 median을 빼서 paired Δ를 만들지 않았습니다.',
             ha='center', fontsize=9)
    fig.subplots_adjust(left=.08, right=.98, bottom=.16, top=.78, wspace=.28)
    fig.savefig(path, bbox_inches='tight', metadata={'Software': 'CP02 protected process plotter'})
    plt.close(fig)


def write_assets(data: dict, stage: Path) -> tuple[str, ...]:
    names = ('whole_domain_weak_hits.png', 'protected_failure_map.png', 'qrain_lower_layer_plus1h.png')
    make_weak_hits_plot(data, stage / names[0])
    make_failure_map(data, stage / names[1])
    make_qrain_plot(data, stage / names[2])
    return names


def write_gallery(stage: Path, names: tuple[str, ...], metadata: dict) -> None:
    captions = {
        names[0]: '전체 3,688 격자에서 관측 약한 강수(0.1≤RN1<1 mm) 중 예측 ≥0.1 mm 탐지 수. 막대 위 Δ와 시간별 약한 관측 분모를 표시합니다.',
        names[1]: '고정 약한 적중 실패·대조·오경보 집단과 +5 h 보호 표본. 네 화살표는 OA 손실과 관측 0인 예측 습윤 이웃의 공간 관계입니다.',
        names[2]: 'UTC 13의 0–1 km QRAIN 절대값과 점별 paired A-X. 절대값은 symlog 축에서 exact zero를 포함합니다.',
    }
    markdown = '# CP02 보호·실패 과정 진단 그림\n\n'
    markdown += ('이 그림은 고정 2026-08-16 사례의 점수·표본 통계와 밀봉된 상태 표를 요약합니다. '
                 '공간 연관은 storm motion이 아니며, 점별 차이는 과정 인과나 전체 물·에너지 수지를 입증하지 않습니다.\n\n')
    for name in names:
        markdown += f'## {captions[name]}\n\n![{captions[name]}]({name})\n\n'
    (stage / 'gallery.md').write_text(markdown, encoding='utf-8')
    html = ['<!doctype html><html lang="ko"><meta charset="utf-8"><title>CP02 보호·실패 과정 진단</title>',
            '<style>body{font:16px sans-serif;max-width:1200px;margin:2rem auto;padding:0 1rem;color:#222}img{width:100%;height:auto}figure{margin:2rem 0}figcaption{line-height:1.5}</style>',
            '<h1>CP02 보호·실패 과정 진단 그림</h1>',
            '<p>고정 사례의 전 영역 점수와 밀봉된 표본을 요약합니다. 공간 쌍은 storm motion이 아니며 인과를 입증하지 않습니다.</p>']
    for name in names:
        html.append(f'<figure><figcaption>{captions[name]}</figcaption><img src="{name}" alt="{captions[name]}" loading="lazy"></figure>')
    html.append('</html>\n')
    (stage / 'index.html').write_text('\n'.join(html), encoding='utf-8')
    (stage / 'metadata.json').write_text(json.dumps(metadata, indent=2, ensure_ascii=False, sort_keys=True) + '\n',
                                         encoding='utf-8')


def write_zip(stage: Path, names: tuple[str, ...]) -> None:
    members = (*names, 'gallery.md', 'index.html', 'metadata.json')
    with zipfile.ZipFile(stage / 'offline_gallery.zip', 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name in members:
            info = zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, (stage / name).read_bytes())
    with zipfile.ZipFile(stage / 'offline_gallery.zip') as archive:
        if archive.testzip() is not None or archive.namelist() != list(members):
            raise PlotInputError('offline gallery ZIP integrity or member order differs')


def verify_attempt_archive(directory: Path) -> str:
    manifest_path = directory / 'attempt_manifest.json'
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise PlotInputError('preserved attempt archive has no regular manifest')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    for relative, record in manifest.get('files', {}).items():
        path = directory / relative
        expected = record if isinstance(record, str) else record.get('sha256')
        expected_size = None if isinstance(record, str) else record.get('size_bytes')
        if (not path.is_file() or path.is_symlink() or sha256(path) != expected
            or (expected_size is not None and path.stat().st_size != expected_size)):
            raise PlotInputError(f'preserved attempt archive differs: {relative}')
    if len(manifest.get('files', {})) != 10:
        raise PlotInputError('preserved attempt archive has an unexpected file inventory')
    return sha256(manifest_path)


def run(output: Path = OUTPUT, *, runtime: Path = RUNTIME, preserve_attempts: bool = False) -> dict:
    output, runtime = Path(output), Path(runtime)
    if os.path.lexists(output) and not preserve_attempts:
        raise FileExistsError(output)
    if os.path.lexists(output) and (output.is_symlink() or not output.is_dir()):
        raise PlotInputError('existing output must be a regular directory for preserved replacement')
    attempt_source = output / 'attempts/before_actual_weak_scope' if preserve_attempts else None
    attempt_hash = verify_attempt_archive(attempt_source) if attempt_source else None
    data = load_inputs()
    if not FONT.is_file() or sha256(FONT) != FONT_SHA256:
        raise PlotInputError('pinned Nanum font is missing or changed')
    configure_font()
    output.parent.mkdir(parents=True, exist_ok=True)
    runtime.mkdir(parents=True, exist_ok=True)
    if output.parent.stat().st_dev != runtime.stat().st_dev:
        raise PlotInputError('staging directory and output must share a filesystem for atomic publication')
    stage = Path(tempfile.mkdtemp(prefix='.cp02-protected-figures-', dir=runtime))
    backup = None
    try:
        if attempt_source:
            shutil.copytree(attempt_source, stage / 'attempts/before_actual_weak_scope')
        names = write_assets(data, stage)
        metadata = {
            'schema': 'cp02_protected_process_figures_v1', 'status': 'PASS',
            'analysis_plan': {'path': str(PLAN.relative_to(ROOT)), 'sha256': data['plan_sha256']},
            'cohort_tool_receipt': {'path': str((COHORTS / 'receipt.json').relative_to(ROOT)),
                                    'sha256': data['cohort_receipt_sha256'],
                                    'status': data['cohort_receipt']['status']},
            'cohort_source_inputs': data['cohort_receipt']['inputs'],
            'analysis_plan_frozen_source_pins': data['plan']['frozen_source_pins'],
            'context_receipt': {'path': str((CONTEXT / 'bundle_receipt.json').relative_to(ROOT)),
                                'sha256': data['context_receipt_sha256']},
            'cohort_tables': data['cohort_hashes'], 'context_tables': data['context_hashes'],
            'font_sha256': sha256(FONT), 'renderer_sha256': sha256(Path(__file__)),
            'coastline': {'path': str(BOUNDARY_PATH.relative_to(ROOT)), 'sha256': BOUNDARY_SHA256,
                          'source_url': BOUNDARY_URL},
            'matplotlib_version': matplotlib.__version__, 'whole_domain_denominator': 3688,
            'observed_weak_detection_definition': {
                'observed_RN1_mm': '[0.1, 1.0)', 'forecast_threshold_mm': 0.1,
                'universe': 'all 3,688 canonical grid points', 'counts_by_hour': data['weak_hit_counts']},
            'weak_hit_case_pairs': {
                'ORIGINAL_initialization': {'comparison': 'ORIGINAL_to_FIX', 'before': 'ORIGINAL',
                                            'after': 'FIXED_ORIGINAL_100'},
                'B1_initialization': {'comparison': 'X_to_A', 'before': 'ORIGINAL_B1_100',
                                      'after': 'IMPROVED_BG_FIXED'},
            },
            'qrain_population': {'plus2_OA_weak_loss': 10, 'plus2_prior_retained_controls': 10,
                                 'time_utc': 13, 'layer_agl_m': [0, 1000], 'units': 'mg kg-1',
                                 'symlog_linthresh_mgkg': 0.01},
            'nearest_pair_arrows': {'role': 'plus2_OA_weak_loss', 'count': len(data['zero_observation_arrows']),
                                    'neighbor_reference_mm': 0.0,
             'interpretation': 'spatial diagnostic only; not storm motion; 5 km can be self-only, 10/20 km are separate radii'},
            'neighborhood_counts': {
                'canonical_points_within_5km_10km_20km': 'inclusive counts on the full paired 3,688-point grid',
                'A_hit_points_within_5km_10km_20km': 'thresholded A wet-point counts, separate from canonical counts',
                '5km_radius_self_only': 'explicit flag; never interpreted as 10/20 km neighborhood evidence',
            },
            'external_history_opened': False,
            'preserved_prior_attempt_manifest_sha256': attempt_hash,
            'outputs': {name: sha256(stage / name) for name in names},
        }
        write_gallery(stage, names, metadata)
        metadata['outputs'].update({name: sha256(stage / name) for name in ('gallery.md', 'index.html')})
        (stage / 'metadata.json').write_text(json.dumps(metadata, indent=2, ensure_ascii=False, sort_keys=True) + '\n',
                                             encoding='utf-8')
        write_zip(stage, names)
        receipt = {'schema': 'cp02_protected_process_figure_receipt_v1', 'status': 'PASS',
                   'renderer_sha256': metadata['renderer_sha256'],
                   'metadata_sha256': sha256(stage / 'metadata.json'),
                   'offline_gallery_sha256': sha256(stage / 'offline_gallery.zip'),
                   'figures': {name: sha256(stage / name) for name in names}}
        (stage / 'receipt.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        output.parent.mkdir(parents=True, exist_ok=True)
        if os.path.lexists(output):
            backup = Path(tempfile.mkdtemp(prefix='.cp02-protected-backup-', dir=runtime))
            backup.rmdir()
            os.rename(output, backup)
        try:
            os.rename(stage, output)
        except Exception:
            if backup is not None and backup.exists() and not output.exists():
                os.rename(backup, output)
                backup = None
            raise
        if backup is not None:
            shutil.rmtree(backup)
            backup = None
        return receipt
    finally:
        if stage.exists():
            shutil.rmtree(stage)
        if backup is not None and backup.exists() and not output.exists():
            os.rename(backup, output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--preserve-attempts', action='store_true')
    args = parser.parse_args()
    print(json.dumps(run(args.output, preserve_attempts=args.preserve_attempts), sort_keys=True))


if __name__ == '__main__':
    main()
