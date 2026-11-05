#!/usr/bin/env python3
"""Extract hash-pinned, native-corner B1 failure-focus state snapshots."""
from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile

import numpy as np
from netCDF4 import Dataset

ROOT = Path(__file__).resolve().parents[1]
CASES = ('ORIGINAL', 'A', 'C', 'B1_OLD_KDM6')
HOURS = tuple(range(12, 19))
NY, NX, NZ = 282, 234, 39
NPOINTS = 3688
GRAVITY_HEIGHT_DIAGNOSTIC = 9.81
SURFACE_ABS_TOLERANCE_MM = 1.0e-10
SURFACE_REL_TOLERANCE = 1.0e-12
SURFACE_NEGATIVE_INCREMENT_TOLERANCE_MM = 1.0e-6
RAW_MASS_FIELDS = ('QVAPOR', 'QCLOUD', 'QICE', 'QRAIN', 'QSNOW', 'QGRAUP',
                   'QNRAIN', 'T', 'THM', 'P', 'PB')
RAW_SURFACE_FIELDS = ('RAINC', 'RAINNC', 'RAINSH', 'MU', 'MUB')
RAW_GEOMETRY_FIELDS = ('PH', 'PHB', 'HGT', 'MAPFAC_MX', 'MAPFAC_MY')
HYBRID_FIELDS = ('C1H', 'C2H', 'DNW', 'C3F', 'C4F', 'ZNW')
RAIN_FIELDS = ('RAINC', 'RAINNC', 'RAINSH')
SCORE_KEYS = {'ORIGINAL': 'ORIGINAL', 'A': 'IMPROVED_BG_FIXED', 'C': 'C',
              'B1_OLD_KDM6': 'ORIGINAL_B1_100'}
OUTPUT_UNITS = {
    'QVAPOR': 'kg kg-1', 'QCLOUD': 'kg kg-1', 'QICE': 'kg kg-1',
    'QRAIN': 'kg kg-1', 'QSNOW': 'kg kg-1', 'QGRAUP': 'kg kg-1',
    'QNRAIN': 'kg-1', 'T': 'K perturbation', 'THM': 'K perturbation',
    'P': 'Pa', 'PB': 'Pa', 'pressure': 'Pa', 'temperature': 'K',
    'theta_dry': 'K', 'theta_m': 'K', 'rh_liquid': '1',
    'rh_ice_or_water': '1', 'dm_mass_weighted': 'mm',
    'height_agl': 'm', 'PH': 'm2 s-2', 'PHB': 'm2 s-2',
    'HGT': 'm', 'MAPFAC_MX': '1', 'MAPFAC_MY': '1',
    'RAINC': 'mm cumulative or mm per one-hour interval',
    'RAINNC': 'mm cumulative or mm per one-hour interval',
    'RAINSH': 'mm cumulative or mm per one-hour interval',
    'MU': 'Pa', 'MUB': 'Pa', 'C1H': '1', 'C2H': 'Pa', 'DNW': '1',
    'C3F': '1', 'C4F': 'Pa', 'ZNW': '1', 'P_TOP': 'Pa',
    'W': 'm s-1', 'DX': 'm', 'DY': 'm',
}


def _feature_functions():
    path = Path(__file__).with_name('cp02_failure_state_features.py')
    spec = importlib.util.spec_from_file_location('cp02_failure_state_features', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FEATURES = _feature_functions()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def verify_pin(record: dict) -> Path:
    path = Path(record['path'])
    if path.is_symlink() or not path.is_file():
        raise ValueError(f'missing or linked pinned input: {path}')
    if path.stat().st_size != record['size_bytes'] or sha256_file(path) != record['sha256']:
        raise ValueError(f'pinned input differs: {path}')
    return path


def checked_hours(records: list[dict]) -> dict[int, dict]:
    by_hour = {}
    for record in records:
        path = Path(record['path'])
        try:
            hour = int(path.name[-8:-6])
        except ValueError as exc:
            raise ValueError(f'invalid history filename: {path}') from exc
        if hour in by_hour:
            raise ValueError(f'duplicate history hour: {hour}')
        by_hour[hour] = record
    if tuple(sorted(by_hour)) != HOURS:
        raise ValueError('history coverage must be exactly 12:00 through 18:00 UTC')
    return by_hour


def load_membership(path: Path) -> list[dict]:
    required = {'flat_index_yx', 'point_index', 'latitude', 'longitude',
                'cohort_labels', 'is_control'}
    with Path(path).open(newline='', encoding='utf-8') as stream:
        reader = csv.DictReader(stream)
        if not required.issubset(reader.fieldnames or ()):
            raise ValueError('focus membership columns differ from the frozen schema')
        rows = list(reader)
    if not rows:
        raise ValueError('focus membership is empty')
    ids = [int(row['flat_index_yx']) for row in rows]
    if len(set(ids)) != len(ids) or any(i < 0 or i >= 253 * 149 for i in ids):
        raise ValueError('focus membership has duplicate or invalid flat indices')
    point_indices = [int(row['point_index']) for row in rows]
    if len(set(point_indices)) != len(rows):
        raise ValueError('focus membership has duplicate point indices')
    for row in rows:
        if not np.isfinite([float(row['latitude']), float(row['longitude'])]).all():
            raise ValueError('focus membership has nonfinite coordinates')
        if not row['cohort_labels']:
            raise ValueError('focus membership has a point without cohort labels')
        if row['is_control'] not in ('0', '1', 'True', 'False', 'true', 'false'):
            raise ValueError('focus membership has invalid control flag')
    return rows


def validate_matched_controls(path: Path, selected_ids: np.ndarray):
    required = {'target_flat_index_yx', 'cohort_label', 'control_flat_index_yx', 'valid_match'}
    selected = set(int(value) for value in selected_ids)
    with Path(path).open(newline='', encoding='utf-8') as stream:
        reader = csv.DictReader(stream)
        if not required.issubset(reader.fieldnames or ()):
            raise ValueError('matched controls columns differ from the frozen schema')
        rows = list(reader)
    seen = set()
    for row in rows:
        key = (int(row['target_flat_index_yx']), row['cohort_label'])
        if key in seen or key[0] not in selected:
            raise ValueError('matched controls contain duplicate or absent target links')
        seen.add(key)
        if row['valid_match'].lower() == 'true':
            try:
                control = int(row['control_flat_index_yx'])
            except ValueError as exc:
                raise ValueError('valid matched control has no point index') from exc
            if control not in selected:
                raise ValueError('matched control point is absent from state membership')
    return rows


def validate_event_membership(path: Path, membership: list[dict], selected_ids: np.ndarray):
    required = {'flat_index_yx', 'cohort_label', 'lead_hour', 'threshold_mm',
                'baseline_case', 'candidate_case', 'reference_mm', 'baseline_mm',
                'candidate_mm', 'observed_band', 'transition'}
    labels_by_point = {int(row['flat_index_yx']): set(row['cohort_labels'].split(';'))
                       for row in membership}
    selected = set(int(value) for value in selected_ids)
    with Path(path).open(newline='', encoding='utf-8') as stream:
        reader = csv.DictReader(stream)
        if not required.issubset(reader.fieldnames or ()):
            raise ValueError('event membership columns differ from the frozen schema')
        rows = list(reader)
    for row in rows:
        point = int(row['flat_index_yx'])
        if point not in selected or row['cohort_label'] not in labels_by_point[point]:
            raise ValueError('event membership link is absent from focus membership')
    return rows


def subset_corners(mapping: dict, all_flat: np.ndarray, selected_flat: np.ndarray):
    if all_flat.shape != (NPOINTS,) or len(np.unique(all_flat)) != NPOINTS:
        raise ValueError('paired reference must contain 3688 unique target points')
    full_j, full_i, full_weights = FEATURES.corners(mapping, all_flat)
    positions = {int(value): index for index, value in enumerate(all_flat)}
    try:
        selected = np.asarray([positions[int(value)] for value in selected_flat], dtype=np.int64)
    except KeyError as exc:
        raise ValueError(f'focus point absent from canonical score mapping: {exc.args[0]}') from exc
    return full_j[selected], full_i[selected], full_weights[selected]


def weighted_surface(values: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Interpolate one surface value per point and corner without axis broadcast."""
    if values.ndim != 2 or values.shape != weights.shape or not np.isfinite(values).all():
        raise ValueError('surface values must be finite point-by-corner arrays')
    result = FEATURES.weighted(values[:, None, :].astype(np.float64), weights)[0][:, 0]
    if result.shape != (values.shape[0],):
        raise ValueError('surface interpolation must return one value per point')
    return result


def validate_weighted_shapes(payload: dict[str, np.ndarray], points: int):
    profiles = (*RAW_MASS_FIELDS, 'theta_dry_K', 'temperature_K', 'pressure_Pa',
                'rh_liquid', 'rh_ice_or_water', 'dm_mass_weighted_mm',
                'height_agl_m', 'theta_m_K', 'dm_valid')
    for name in profiles:
        key = f'weighted_raw_{name}' if name in RAW_MASS_FIELDS else f'weighted_{name}'
        if np.shape(payload[key]) != (points, NZ):
            raise ValueError(f'{key}: expected point-by-39-level output')
    for name in ('PH', 'PHB'):
        if payload[f'weighted_raw_{name}'].shape != (points, NZ + 1):
            raise ValueError(f'weighted_raw_{name}: expected point-by-40-interface output')
    for name in (*RAW_SURFACE_FIELDS, *RAW_GEOMETRY_FIELDS[2:]):
        if payload[f'weighted_raw_{name}'].shape != (points,):
            raise ValueError(f'weighted_raw_{name}: expected one value per point')
    for name in RAIN_FIELDS:
        if payload[f'weighted_{name.lower()}_increment_mm'].shape != (points,):
            raise ValueError(f'weighted_{name.lower()}_increment_mm: expected one value per point')
    if 'weighted_w_mass_level_m_s' in payload and payload['weighted_w_mass_level_m_s'].shape != (points, NZ):
        raise ValueError('weighted_w_mass_level_m_s: expected point-by-39-level output')


def _read_corner(ds, name: str, jj: np.ndarray, ii: np.ndarray,
                 levels: int) -> np.ndarray:
    variable = ds.variables[name]
    variable.set_auto_maskandscale(False)
    expected_dims = ('Time', 'bottom_top', 'south_north', 'west_east')
    if levels == 40:
        expected_dims = ('Time', 'bottom_top_stag', 'south_north', 'west_east')
    if variable.dimensions != expected_dims or variable.shape != (1, levels, NY, NX):
        raise ValueError(f'{name}: dimensions or shape differ from native contract')
    native = np.asarray(variable[0])
    if native.dtype != np.dtype('float32'):
        raise ValueError(f'{name}: expected native float32, got {native.dtype}')
    corner = native[:, jj, ii].transpose(1, 0, 2)
    if not np.isfinite(corner).all():
        raise ValueError(f'{name}: nonfinite value at selected source corner')
    return corner


def _read_surface(ds, name: str, jj: np.ndarray, ii: np.ndarray) -> np.ndarray:
    variable = ds.variables[name]
    variable.set_auto_maskandscale(False)
    if variable.dimensions != ('Time', 'south_north', 'west_east') or variable.shape != (1, NY, NX):
        raise ValueError(f'{name}: dimensions or shape differ from surface contract')
    native = np.asarray(variable[0])
    if native.dtype != np.dtype('float32'):
        raise ValueError(f'{name}: expected native float32, got {native.dtype}')
    corner = native[jj, ii]
    if not np.isfinite(corner).all():
        raise ValueError(f'{name}: nonfinite value at selected source corner')
    return corner


def decode_history_time(values: np.ndarray) -> str:
    values = np.asarray(values)
    if values.shape != (19,):
        raise ValueError('Times: expected 19 character values')
    if values.dtype.kind == 'S':
        return b''.join(values.tolist()).decode('ascii')
    if values.dtype.kind == 'U':
        return ''.join(values.tolist())
    raise ValueError('Times: expected a character array')


def validate_rainsh(cumulative: np.ndarray, increment: np.ndarray | None,
                    tolerance_mm: float = SURFACE_ABS_TOLERANCE_MM):
    if np.any(np.abs(cumulative) > tolerance_mm):
        raise ValueError('RAINSH cumulative field violates the zero contract')
    if increment is not None and np.any(np.abs(increment) > tolerance_mm):
        raise ValueError('RAINSH interval increment violates the zero contract')


def derive_diagnostics(raw: dict[str, np.ndarray], weights: np.ndarray,
                       height_agl: np.ndarray):
    """Derive nonlinear thermodynamics per corner, then interpolate in REAL64."""
    qv = raw['QVAPOR'].astype(np.float64)
    pressure = raw['P'].astype(np.float64) + raw['PB'].astype(np.float64)
    theta = raw['T'].astype(np.float64)
    theta_m = raw['THM'].astype(np.float64)
    moist_error = np.abs(theta + 300.0 - (theta_m + 300.0) /
                         (1.0 + (FEATURES.RV / FEATURES.RD) * qv))
    if np.any(moist_error > 6.0e-5) or np.any(pressure <= 0):
        raise ValueError('dry/moist theta consistency or total pressure failed')
    temperature = FEATURES.temperature_from_history(theta, pressure)
    rh_liquid = FEATURES.humidity(qv, temperature, pressure)
    rh_phase = FEATURES.humidity(qv, temperature, pressure, ice_or_water=True)
    dm, dm_valid = FEATURES.diameter(raw['QRAIN'].astype(np.float64),
                                     raw['QNRAIN'].astype(np.float64))
    derived = {
        'corner_theta_dry_K': theta + 300.0,
        'corner_temperature_K': temperature,
        'corner_pressure_Pa': pressure,
        'corner_rh_liquid': rh_liquid,
        'corner_rh_ice_or_water': rh_phase,
        'corner_dm_mass_weighted_mm': dm,
        'corner_dm_valid': dm_valid,
        'corner_height_agl_m': height_agl,
    }
    weighted = {}
    valid_weight = {}
    for name, values in derived.items():
        if name == 'corner_dm_valid':
            continue
        valid = dm_valid if name == 'corner_dm_mass_weighted_mm' else None
        result, coverage, allowed = FEATURES.weighted(values, weights, valid)
        weighted[name.removeprefix('corner_')] = result
        valid_weight[name.removeprefix('corner_')] = coverage
        if name == 'corner_dm_mass_weighted_mm':
            weighted['dm_valid'] = allowed
    weighted['theta_m_K'] = FEATURES.weighted(theta_m + 300.0, weights)[0]
    weighted['dry_moist_theta_max_error_K'] = float(np.max(moist_error))
    return derived, weighted, valid_weight


def _verify_history_metadata(ds, expected_time: str):
    expected_attrs = {'USE_THETA_M': 1, 'HYBRID_OPT': 2, 'GRIDTYPE': 'C',
                      'BUCKET_MM': -1.0, 'BUCKET_J': -1.0}
    for name, value in expected_attrs.items():
        if getattr(ds, name, None) != value:
            raise ValueError(f'history attribute {name} differs from frozen case')
    if getattr(ds, 'PREC_ACC_DT', None) != 0.0:
        raise ValueError('PREC_ACC_DT differs from the cumulative-precipitation contract')
    if (len(ds.dimensions['Time']) != 1 or len(ds.dimensions['bottom_top']) != NZ
            or len(ds.dimensions['bottom_top_stag']) != NZ + 1
            or len(ds.dimensions['south_north']) != NY or len(ds.dimensions['west_east']) != NX):
        raise ValueError('history dimensions differ from frozen WRF grid')
    times = ds.variables['Times']
    if times.dimensions != ('Time', 'DateStrLen') or times.shape != (1, 19):
        raise ValueError('Times: dimensions differ from WRF history contract')
    actual_time = decode_history_time(times[0])
    if actual_time != expected_time:
        raise ValueError(f'history time {actual_time!r} differs from {expected_time!r}')
    return {'bucket_mm': float(ds.BUCKET_MM), 'bucket_j': float(ds.BUCKET_J),
            'prec_acc_dt': float(ds.PREC_ACC_DT)}


def extract_snapshot(path: Path, jj: np.ndarray, ii: np.ndarray, weights: np.ndarray,
                     expected_lat: np.ndarray, expected_lon: np.ndarray,
                     previous_rain: dict[str, np.ndarray] | None,
                     expected_time: str):
    with Dataset(path, 'r') as ds:
        history_attrs = _verify_history_metadata(ds, expected_time)
        raw = {name: _read_corner(ds, name, jj, ii, NZ)
               for name in RAW_MASS_FIELDS}
        raw.update({name: _read_corner(ds, name, jj, ii, NZ + 1)
                    for name in ('PH', 'PHB')})
        raw.update({name: _read_surface(ds, name, jj, ii)
                    for name in (*RAW_SURFACE_FIELDS, *RAW_GEOMETRY_FIELDS[2:])})
        for name in HYBRID_FIELDS:
            variable = ds.variables[name]
            variable.set_auto_maskandscale(False)
            levels = NZ + 1 if name in ('C3F', 'C4F', 'ZNW') else NZ
            dimension = 'bottom_top_stag' if levels == NZ + 1 else 'bottom_top'
            if variable.dimensions != ('Time', dimension) or variable.shape != (1, levels):
                raise ValueError(f'{name}: hybrid coefficient dimensions differ from contract')
            coefficient = np.asarray(variable[0])
            if coefficient.dtype != np.dtype('float32') or not np.isfinite(coefficient).all():
                raise ValueError(f'{name}: expected finite native float32 coefficients')
            raw[name] = coefficient
        ptop_variable = ds.variables['P_TOP']
        ptop_variable.set_auto_maskandscale(False)
        if ptop_variable.dimensions != ('Time',) or ptop_variable.shape != (1,):
            raise ValueError('P_TOP: expected one Time record')
        ptop = np.asarray(ptop_variable[0])
        if ptop.shape != () or ptop.dtype != np.dtype('float32') or not np.isfinite(ptop):
            raise ValueError('P_TOP: expected finite scalar')
        if float(ds.DX) != 5000.0 or float(ds.DY) != 5000.0:
            raise ValueError('grid spacing differs from pinned histories')
        raw['P_TOP'] = ptop.astype(np.float32)
        raw['DX_m'] = np.asarray(ds.DX, dtype=np.float32)
        raw['DY_m'] = np.asarray(ds.DY, dtype=np.float32)
        lat = _read_surface(ds, 'XLAT', jj, ii)
        lon = _read_surface(ds, 'XLONG', jj, ii)
        mapped_lat = np.sum(lat.astype(np.float64) * weights, axis=-1)
        mapped_lon = np.sum(lon.astype(np.float64) * weights, axis=-1)
        if (not np.allclose(mapped_lat, expected_lat, rtol=0, atol=1e-9)
                or not np.allclose(mapped_lon, expected_lon, rtol=0, atol=1e-9)):
            raise ValueError('native mapped coordinates differ from canonical paired scores')
        geopotential = raw['PH'].astype(np.float64) + raw['PHB'].astype(np.float64)
        height = ((geopotential[:, :-1, :] + geopotential[:, 1:, :]) /
                  (2.0 * GRAVITY_HEIGHT_DIAGNOSTIC) -
                  raw['HGT'][:, None, :].astype(np.float64))
        if not np.isfinite(height).all():
            raise ValueError('nonfinite AGL height diagnostic')
        derived, weighted, valid_weight = derive_diagnostics(raw, weights, height)
        w_raw = None
        if 'W' in ds.variables:
            w_raw = _read_corner(ds, 'W', jj, ii, NZ + 1)
    payload = {f'corner_{name}': value.astype(np.float32)
               for name, value in raw.items()
               if name not in ('P_TOP', 'DX_m', 'DY_m', *HYBRID_FIELDS)}
    payload.update({f'native_hybrid_{name}': raw[name].astype(np.float32)
                    for name in HYBRID_FIELDS})
    for name, values in raw.items():
        if values.ndim == 3 and values.shape[-1] == 4:
            payload[f'weighted_raw_{name}'] = FEATURES.weighted(values.astype(np.float64), weights)[0]
        elif values.ndim == 2 and values.shape[-1] == 4:
            payload[f'weighted_raw_{name}'] = weighted_surface(values, weights)
        elif name in HYBRID_FIELDS:
            payload[f'weighted_raw_{name}'] = values.astype(np.float64)
    payload.update({name: value for name, value in derived.items()})
    payload.update({f'weighted_{name}': value for name, value in weighted.items()})
    payload.update({f'valid_weight_{name}': value for name, value in valid_weight.items()})
    payload['P_TOP_Pa'] = raw['P_TOP']
    payload['DX_m'] = raw['DX_m']
    payload['DY_m'] = raw['DY_m']
    if w_raw is not None:
        payload['corner_w_staggered_m_s'] = w_raw
        w_mass = (w_raw[:, :-1, :].astype(np.float64) +
                  w_raw[:, 1:, :].astype(np.float64)) / 2.0
        payload['corner_w_mass_level_m_s'] = w_mass
        payload['weighted_w_mass_level_m_s'] = FEATURES.weighted(w_mass, weights)[0]
    current_rain = {name: raw[name].astype(np.float64) for name in RAIN_FIELDS}
    validate_rainsh(current_rain['RAINSH'], None)
    rain_diagnostics = {}
    for name, cumulative in current_rain.items():
        payload[f'corner_{name.lower()}_cumulative_mm'] = raw[name]
        if previous_rain is None:
            payload[f'corner_{name.lower()}_increment_mm'] = np.full(cumulative.shape, np.nan, dtype=np.float64)
            payload[f'weighted_{name.lower()}_increment_mm'] = np.full(cumulative.shape[:-1], np.nan, dtype=np.float64)
            rain_diagnostics[name] = {'negative_increment_count': 0,
                                      'minimum_increment_mm': None}
        else:
            increment = cumulative - previous_rain[name]
            negative = increment[increment < 0]
            if np.any(increment < -SURFACE_NEGATIVE_INCREMENT_TOLERANCE_MM):
                raise ValueError(f'{name}: selected cumulative history reset without bucket correction')
            if name == 'RAINSH':
                validate_rainsh(cumulative, increment)
            payload[f'corner_{name.lower()}_increment_mm'] = increment
            payload[f'weighted_{name.lower()}_increment_mm'] = weighted_surface(increment, weights)
            rain_diagnostics[name] = {'negative_increment_count': int(negative.size),
                                      'minimum_increment_mm': float(increment.min())}
    rain_diagnostics['RAINSH']['cumulative_max_abs_mm'] = float(np.abs(current_rain['RAINSH']).max())
    validate_weighted_shapes(payload, weights.shape[0])
    return (payload, current_rain, float(weighted['dry_moist_theta_max_error_K']),
            history_attrs, rain_diagnostics)


def _read_score_hour(record: dict, score_key: str, selected_ids: np.ndarray):
    path = verify_pin(record)
    with np.load(path, allow_pickle=False) as archive:
        needed = {'flat_index_yx', 'latitude', 'longitude', score_key}
        if not needed.issubset(archive.files):
            raise ValueError(f'{path}: missing paired score fields for {score_key}')
        flat = np.asarray(archive['flat_index_yx'], dtype=np.int64)
        values = np.asarray(archive[score_key], dtype=np.float64)
        if flat.shape != (NPOINTS,) or values.shape != (NPOINTS,) or len(np.unique(flat)) != NPOINTS:
            raise ValueError(f'{path}: paired score point inventory differs')
        index = {int(value): i for i, value in enumerate(flat)}
        try:
            return values[np.asarray([index[int(v)] for v in selected_ids])]
        except KeyError as exc:
            raise ValueError(f'{path}: focus point missing from paired score input') from exc


def run(plan_path: Path, output_dir: Path):
    plan_path, output_dir = Path(plan_path), Path(output_dir)
    plan = json.loads(plan_path.read_text(encoding='utf-8'))
    if plan.get('status') != 'FROZEN_BEFORE_STATE_EXTRACTION':
        raise ValueError('extraction plan is not frozen')
    proposal_record = plan['inputs_proposal']
    proposal_path = verify_pin(proposal_record)
    proposal = json.loads(proposal_path.read_text(encoding='utf-8'))
    if proposal.get('status') != 'DISCOVERY_PROPOSAL_NOT_FROZEN':
        raise ValueError('input lineage proposal has unexpected status')
    membership_record = plan['membership']
    membership_path = verify_pin(membership_record)
    membership = load_membership(membership_path)
    controls_record = plan['matched_controls']
    controls_path = verify_pin(controls_record)
    events_record = plan['event_membership']
    events_path = verify_pin(events_record)
    targets_receipt_record = plan['targets_receipt']
    targets_receipt_path = verify_pin(targets_receipt_record)
    targets_receipt = json.loads(targets_receipt_path.read_text(encoding='utf-8'))
    lineage_records = list(proposal['lineage_receipts'].values())
    for record in lineage_records:
        verify_pin(record)
    selected_ids = np.asarray([int(row['flat_index_yx']) for row in membership], dtype=np.int64)
    control_rows = validate_matched_controls(controls_path, selected_ids)
    event_rows = validate_event_membership(events_path, membership, selected_ids)
    if (targets_receipt.get('unique_focus_points') != len(selected_ids)
            or targets_receipt.get('matched_control_pairs') != len(control_rows)
            or targets_receipt.get('missing_control_pairs') != 0):
        raise ValueError('target bundle receipt counts differ from focus/control files')
    for label, record in (('focus_membership.csv', membership_record),
                          ('matched_controls.csv', controls_record),
                          ('event_membership.csv', events_record)):
        output_pin = targets_receipt['outputs'].get(label)
        if output_pin is None or output_pin['sha256'] != record['sha256'] or output_pin['size_bytes'] != record['size_bytes']:
            raise ValueError(f'target bundle receipt does not bind {label}')
    expected_lat = np.asarray([float(row['latitude']) for row in membership], dtype=np.float64)
    expected_lon = np.asarray([float(row['longitude']) for row in membership], dtype=np.float64)
    if (plan.get('surface_abs_tolerance_mm') != SURFACE_ABS_TOLERANCE_MM
            or plan.get('surface_rel_tolerance') != SURFACE_REL_TOLERANCE):
        raise ValueError('surface REAL64 operation-order tolerances differ from frozen protocol')
    if (plan.get('rainsh_contract') != 'zero_cumulative_and_increment'
            or plan.get('rainsh_abs_tolerance_mm') != SURFACE_ABS_TOLERANCE_MM
            or plan.get('surface_negative_increment_tolerance_mm') != SURFACE_NEGATIVE_INCREMENT_TOLERANCE_MM):
        raise ValueError('RAINSH zero-increment contract or tolerance differs from frozen plan')
    if set(proposal['cases']) != set(CASES) or set(proposal['paired_score_arrays']) != set(CASES):
        raise ValueError('input proposal must contain exactly the four frozen state/score cases')
    for case in CASES:
        score_records = proposal['paired_score_arrays'][case]
        if (len(score_records) != 6 or
                [record.get('hour_utc') for record in score_records] != list(range(13, 19))):
            raise ValueError(f'{case}: paired score records must cover hours 13 through 18 in order')
    mapping_path = verify_pin(proposal['mapping'])
    with np.load(mapping_path, allow_pickle=False) as mapping_archive:
        mapping = {name: np.array(mapping_archive[name], copy=True) for name in mapping_archive.files}
    reference_record = proposal['paired_score_arrays']['ORIGINAL'][0]
    with np.load(verify_pin(reference_record), allow_pickle=False) as archive:
        all_flat = np.asarray(archive['flat_index_yx'], dtype=np.int64)
        all_lat = np.asarray(archive['latitude'], dtype=np.float64)
        all_lon = np.asarray(archive['longitude'], dtype=np.float64)
    jj, ii, weights = subset_corners(mapping, all_flat, selected_ids)
    expected_position = {int(value): i for i, value in enumerate(all_flat)}
    if any(not np.isclose(expected_lat[i], all_lat[expected_position[int(point)]], rtol=0, atol=1e-9)
           or not np.isclose(expected_lon[i], all_lon[expected_position[int(point)]], rtol=0, atol=1e-9)
           for i, point in enumerate(selected_ids)):
        raise ValueError('focus coordinates differ from canonical score points')
    if os.path.lexists(output_dir):
        raise FileExistsError(output_dir)
    plan_sha = sha256_file(plan_path)
    extractor_record = plan['extractor']
    extractor_path = verify_pin(extractor_record)
    if extractor_path.resolve() != Path(__file__).resolve():
        raise ValueError('extraction plan does not pin this extractor')
    feature_record = plan['feature_implementation']
    feature_path = verify_pin(feature_record)
    if feature_path.resolve() != Path(FEATURES.__file__).resolve():
        raise ValueError('extraction plan does not pin the imported feature functions')
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.' + output_dir.name + '.', dir=output_dir.parent))
    try:
        shutil.copyfile(membership_path, temporary / 'focus_membership.csv')
        shutil.copyfile(controls_path, temporary / 'matched_controls.csv')
        shutil.copyfile(events_path, temporary / 'event_membership.csv')
        shutil.copyfile(targets_receipt_path, temporary / 'targets_bundle_receipt.json')
        if (sha256_file(temporary / 'focus_membership.csv') != membership_record['sha256']
                or sha256_file(temporary / 'matched_controls.csv') != controls_record['sha256']
                or sha256_file(temporary / 'event_membership.csv') != events_record['sha256']
                or sha256_file(temporary / 'targets_bundle_receipt.json') != targets_receipt_record['sha256']):
            raise ValueError('membership bundle copy differs from frozen source')
        records, rain_checks = [], []
        for case in CASES:
            history_by_hour = checked_hours(proposal['cases'][case])
            previous_rain = None
            for hour in HOURS:
                source_record = history_by_hour[hour]
                source = verify_pin(source_record)
                payload, current_rain, theta_error, history_attrs, rain_diagnostics = extract_snapshot(
                    source, jj, ii, weights, expected_lat, expected_lon, previous_rain,
                    f'2026-08-16_{hour:02d}:00:00')
                previous_rain = current_rain
                payload.update(flat_index_yx=selected_ids, latitude=expected_lat, longitude=expected_lon,
                               point_index=np.asarray([int(row['point_index']) for row in membership], dtype=np.int64),
                               native_j_zero_based=jj, native_i_zero_based=ii,
                               corner_weights=weights,
                               membership_cohort_labels=np.asarray([row['cohort_labels'] for row in membership]),
                               membership_is_control=np.asarray([row['is_control'].lower() == 'true' or row['is_control'] == '1' for row in membership]))
                dest = temporary / f'{case}_h{hour:02d}.npz'
                np.savez_compressed(dest, **payload)
                if dest.stat().st_size >= 100 * 1024 * 1024:
                    raise ValueError(f'{case}/h{hour:02d}: derived file exceeds 100 MiB')
                if sha256_file(source) != source_record['sha256']:
                    raise ValueError(f'{case}/h{hour:02d}: source changed during extraction')
                records.append({'case': case, 'hour_utc': hour, 'input_path': str(source),
                                'valid_time': f'2026-08-16_{hour:02d}:00:00',
                                'input_sha256': source_record['sha256'], 'output': dest.name,
                                'output_sha256': sha256_file(dest), 'output_size_bytes': dest.stat().st_size,
                                'precipitation_attributes': history_attrs,
                                'rain_increment_diagnostics': rain_diagnostics,
                                'dry_moist_theta_max_error_K': theta_error,
                                'dm_valid_weighted_point_levels': int(np.count_nonzero(payload['weighted_dm_valid']))})
                if hour > HOURS[0]:
                    score_rec = proposal['paired_score_arrays'][case][hour - 13]
                    canonical = _read_score_hour(score_rec, SCORE_KEYS[case], selected_ids)
                    actual = payload['weighted_rainc_increment_mm'] + payload['weighted_rainnc_increment_mm']
                    if actual.shape != canonical.shape:
                        raise ValueError(f'{case}/h{hour:02d}: surface score shape differs from focus points')
                    error = np.abs(actual - canonical)
                    allowed = (plan['surface_abs_tolerance_mm'] +
                               plan['surface_rel_tolerance'] * np.abs(canonical))
                    if np.any(error > allowed):
                        raise ValueError(f'{case}/h{hour:02d}: surface increment differs from paired scores')
                    rainsh = payload['weighted_rainsh_increment_mm']
                    if np.any(np.abs(rainsh) > plan['rainsh_abs_tolerance_mm']):
                        raise ValueError(f'{case}/h{hour:02d}: RAINSH increment violates paired contract')
                    rain_checks.append({'case': case, 'hour_utc': hour, 'score_key': SCORE_KEYS[case],
                                        'points': len(selected_ids), 'max_abs_error_mm': float(error.max()),
                                        'tolerance_abs_mm': plan['surface_abs_tolerance_mm'],
                                        'tolerance_relative': plan['surface_rel_tolerance'],
                                        'rainsh_abs_tolerance_mm': plan['rainsh_abs_tolerance_mm'],
                                        'rainsh_max_abs_mm': float(np.abs(rainsh).max())})
                print(f'{case} h{hour:02d} done', flush=True)
        if sha256_file(plan_path) != plan_sha or sha256_file(proposal_path) != proposal_record['sha256']:
            raise ValueError('frozen plan or input proposal changed during extraction')
        if (sha256_file(membership_path) != membership_record['sha256']
                or sha256_file(controls_path) != controls_record['sha256']
                or sha256_file(events_path) != events_record['sha256']
                or sha256_file(targets_receipt_path) != targets_receipt_record['sha256']
                or sha256_file(mapping_path) != proposal['mapping']['sha256']):
            raise ValueError('frozen membership, matched controls or mapping changed during extraction')
        for record in lineage_records:
            verify_pin(record)
        verify_pin(extractor_record)
        verify_pin(feature_record)
        for case in CASES:
            for record in proposal['paired_score_arrays'][case]:
                verify_pin(record)
        receipt = {'status': 'PASS', 'plan_sha256': plan_sha,
                   'inputs_proposal_sha256': proposal_record['sha256'],
                   'membership_sha256': membership_record['sha256'],
                   'matched_controls_sha256': controls_record['sha256'],
                   'event_membership_sha256': events_record['sha256'],
                   'targets_receipt_sha256': targets_receipt_record['sha256'],
                   'event_membership_rows': len(event_rows),
                   'cases': list(CASES), 'hours_utc': list(HOURS), 'points': len(selected_ids),
                   'levels': NZ, 'records': records, 'surface_score_checks': rain_checks,
                   'units': OUTPUT_UNITS,
                   'precision': 'Raw corner values retain native float32; history-derived nonlinear diagnostics are computed in float64 at each corner before interpolation, and weighted diagnostics are float64. Surface comparison tolerances cover REAL64 operation-order differences against archived scoring, not native float32 rounding. These are history diagnostics, not native KDM6 values or rates.',
                   'surface_score_tolerance': {'absolute_mm': SURFACE_ABS_TOLERANCE_MM,
                                               'relative': SURFACE_REL_TOLERANCE,
                                               'negative_increment_mm': SURFACE_NEGATIVE_INCREMENT_TOLERANCE_MM,
                                               'rainsh_contract': 'zero cumulative and increment'},
                   'mass_scope': 'Raw MU/MUB and hybrid coefficients are retained; no dry mass or column water is derived because the actual executable gravity constant is not pinned.',
                   'limitations': ['Eulerian snapshot differences cannot identify evaporation or transport.',
                                  'No tendency, water-budget, energy-budget, or causal mechanism claim is made.',
                                  'Height uses g=9.81 m s-2 as an explicit geometry diagnostic convention.']}
        (temporary / 'receipt.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
        with (output_dir.parent / '.b1_failure_state_publish.lock').open('a') as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            if os.path.lexists(output_dir):
                raise FileExistsError(output_dir)
            os.rename(temporary, output_dir)
        return receipt
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.plan, args.output), sort_keys=True))


if __name__ == '__main__':
    main()
