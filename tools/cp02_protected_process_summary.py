#!/usr/bin/env python3
"""Compare validated OLD/FIX process increments at fixed native levels."""
from __future__ import annotations
import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path
import shutil
import uuid

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / 'docs/evidence/cp02_protected_process_20261106'
FIELDS = {'QV': 'kg kg-1', 'QC': 'kg kg-1', 'QR': 'kg kg-1', 'TK': 'K'}
HOURS = (1, 2, 5)
PINNED = {
    'schema_sha256': ('native/schema/cp05_schema.json', '677847102d32b1637340d94bcd24c3856d63348bd15ceb0a319d8b5eda8ff25c'),
    'source_generation_receipt_sha256': ('native/source/source_generation_receipt.json', '7ed9bf6189249468695e5ce4784f3733d04eed41dae95b3cb31bb46d6bc0ae37'),
    'cohort_receipt_sha256': ('cohorts/receipt.json', 'cd1e03fbc075c25f6a4904ce278935dea8d23a2157162274835fca21fc911826'),
    'capture_plan_sha256': ('native/plans/capture_plan.md', '9183bd9f6bf7d0781cb6793d7f88e7ad6e44d2adb166e065c923bb0b7e67434e'),
}
POINTS_SHA = '12a000e1dab5963f7327cce49a44e988940b8e1c208049dd7f5285f126e85ea9'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def ledger(entry, returned):
    """Both arrays contain FIX minus OLD; time is the first axis."""
    if entry.shape != returned.shape or entry.shape[0] != 180:
        raise ValueError('ledger requires one complete contiguous 180-call hour')
    local = np.sum(returned - entry, axis=0, dtype=np.float64)
    external = np.sum(entry[1:] - returned[:-1], axis=0, dtype=np.float64)
    endpoint = returned[-1] - entry[0]
    residual = endpoint - local - external
    return local, external, endpoint, residual


def write_csv(path, rows):
    if not rows:
        raise ValueError('cannot publish an empty scientific table')
    with path.open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def read_capture(directory, arm, launch_sha):
    path = directory / 'capture_receipt.json'
    receipt = json.loads(path.read_text())
    if (receipt['status'] != 'FULL_CAPTURE_STREAMS_VALIDATED' or receipt['arm'] != arm
            or receipt['mode'] != 'full' or receipt['launch_receipt_sha256'] != launch_sha
            or receipt['actual_timesteps'] != list(range(1, 901))
            or receipt['process_actual_timesteps'] != list(range(1, 361)) + list(range(721, 901))
            or receipt['native_columns'] != 381 or receipt['levels'] != 39
            or receipt['surface_rows'] != 900 * 381):
        raise ValueError(f'{arm}: full capture coverage or execution binding differs')
    if receipt['tool_sha256'] != sha(ROOT / 'tools/cp02_protected_process_capture.py'):
        raise ValueError('collector source changed after collection')
    for key, (relative, expected) in PINNED.items():
        if receipt.get(key) != expected or sha(BUNDLE / relative) != expected:
            raise ValueError(f'{arm}: frozen {key} binding differs')
    return receipt


def channel_path(directory, receipt, name, hour):
    start, end = (hour - 1) * 180 + 1, hour * 180
    matches = [row for row in receipt['outputs'] if row.get('channel') == name
               and row['actual_start'] == start and row['actual_end'] == end]
    if len(matches) != 1:
        raise ValueError(f'exactly one channel is required: {name}, hour {hour}')
    row = matches[0]
    relative = Path(row['path'])
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('unsafe captured channel path')
    path = directory / relative
    if path.stat().st_size != row['size_bytes'] or sha(path) != row['sha256']:
        raise ValueError(f'captured channel identity differs: {path}')
    return path


def load_channel(directory, receipt, name, hour, allow_missing=False):
    start, end = (hour - 1) * 180 + 1, hour * 180
    path = channel_path(directory, receipt, name, hour)
    with np.load(path, allow_pickle=False) as data:
        steps = data['actual_timestep'].copy()
        points = data['point_ids'].copy()
        values = data['point_values'].astype(np.float64)
    if not np.array_equal(steps, np.arange(start, end + 1)) or len(points) != 150:
        raise ValueError('captured actual time or point scope differs')
    point_path = BUNDLE / 'cohorts/point_corners.csv'
    if sha(point_path) != POINTS_SHA:
        raise ValueError('frozen point/corner map changed')
    with point_path.open(newline='') as stream:
        expected_points = list(dict.fromkeys(row['point_id'] for row in csv.DictReader(stream)))
    if list(points) != expected_points:
        raise ValueError('captured point IDs differ from the frozen selector')
    if values.shape != (180, 39, 150) or (not allow_missing and not np.isfinite(values).all()):
        raise ValueError('required scientific channel is incomplete or nonfinite')
    return points, values


def nominal_rate_integral(directory, receipt, name, hour):
    """Apply source f32 multiplication at native cells before interpolation."""
    rate_path = channel_path(directory, receipt, 'phase05_' + name, hour)
    dt_path = channel_path(directory, receipt, 'phase06_dtcld', hour)
    with np.load(rate_path, allow_pickle=False) as rate, np.load(dt_path, allow_pickle=False) as dt:
        for key in ('actual_timestep', 'point_ids', 'native_column_ids',
                    'point_native_corner_indices', 'point_corner_weights'):
            if not np.array_equal(rate[key], dt[key]):
                raise ValueError('rate/timestep native coordinates differ')
        values = np.multiply(rate['native_values'], dt['native_values'], dtype=np.float32)
        if values.shape != (180, 39, 381) or not np.isfinite(values).all():
            raise ValueError('nominal rate integral lacks required native coverage')
        corners = np.take(values, rate['point_native_corner_indices'], axis=-1)
        points = np.sum(corners.astype(np.float64) * rate['point_corner_weights'], axis=-1)
        return np.sum(points, axis=0, dtype=np.float64)


def group_profiles(rows):
    role_path = BUNDLE / 'cohorts/role_membership.csv'
    cohort = json.loads((BUNDLE / 'cohorts/receipt.json').read_text())
    if sha(role_path) != cohort['outputs']['role_membership.csv']:
        raise ValueError('frozen role membership changed')
    roles = defaultdict(set)
    with role_path.open(newline='') as stream:
        for row in csv.DictReader(stream):
            roles[row['point_id']].add(row['role'])
    groups = defaultdict(list)
    for row in rows:
        for role in roles[row['point_id']]:
            groups[(role, row['lead_hour'], row['field'], row['native_k_1based'])].append(row)
    metrics = ('old_entry_first', 'fix_entry_first', 'old_return_last', 'fix_return_last',
               'delta_call_internal_sum', 'delta_between_call_sum', 'delta_endpoint_change',
               'delta_phase8_minus_phase6_sum', 'delta_rain_sedimentation_sum',
               'delta_condensation_substep_sum', 'remaining_call_internal_sum')
    result = []
    for (role, hour, field, level), members in sorted(groups.items()):
        row = {'role': role, 'lead_hour': hour, 'field': field,
               'native_k_1based': level, 'n_points': len(members), 'units': FIELDS[field]}
        for metric in metrics:
            values = [float(member[metric]) for member in members if member[metric] is not None]
            row[metric + '_n_finite'] = len(values)
            for label, quantile in [('q25', .25), ('median', .5), ('q75', .75)]:
                row[metric + '_' + label] = float(np.quantile(values, quantile)) if values else None
        result.append(row)
    return result


def summarize(old_dir, fix_dir, launch_path, expected_launch_sha, output):
    if sha(launch_path) != expected_launch_sha:
        raise ValueError('full launch receipt hash differs')
    launch = json.loads(launch_path.read_text())
    if launch['status'] != 'PASS' or launch['stage'] != 'full' or launch['duration_seconds'] != 18000:
        raise ValueError('completed five-hour paired execution is required')
    for arm in ('OLD', 'FIX'):
        histories = launch['arms'][arm]['history_comparisons']
        if set(histories) != {f'{hour:02d}' for hour in range(12, 18)} or not all(
                row['all_variables_coordinates_attributes_exact'] for row in histories.values()):
            raise ValueError('all twelve hourly reference comparisons must pass')
    directories = {'OLD': old_dir, 'FIX': fix_dir}
    receipts = {arm: read_capture(path, arm, expected_launch_sha) for arm, path in directories.items()}
    def pair(name, hour, allow_missing=False):
        values = []
        ids = None
        for arm in ('OLD', 'FIX'):
            point_ids, array = load_channel(directories[arm], receipts[arm], name, hour, allow_missing)
            if ids is not None and not np.array_equal(ids, point_ids):
                raise ValueError('OLD/FIX point coordinates differ')
            ids = point_ids
            values.append(array)
        return ids, values[0], values[1]
    rows, rate_rows = [], []
    for hour in HOURS:
        for field, unit in FIELDS.items():
            points, old_entry, fix_entry = pair(f'state_entry_{field}', hour)
            _ids, old_return, fix_return = pair(f'state_return_{field}', hour)
            local, external, endpoint, residual = ledger(fix_entry - old_entry, fix_return - old_return)
            _ids, old_update, fix_update = pair(f'phase8_minus_phase6_{field}', hour)
            update = np.sum(fix_update - old_update, axis=0, dtype=np.float64)
            if field == 'QR':
                _ids, old_sed, fix_sed = pair('sedimentation_net_QR', hour, allow_missing=True)
                sed_present = np.isfinite(fix_sed) & np.isfinite(old_sed)
                sed_count = sed_present.sum(axis=0)
                sedimentation = np.sum(fix_sed - old_sed, axis=0, dtype=np.float64)
                condensation = np.zeros_like(update)
            else:
                # Only rain/snow/graupel sedimentation is captured as state
                # increments. Do not invent a sedimentation term for QV/QC/T.
                sedimentation = np.zeros_like(update)
                _ids, old_cond, fix_cond = pair(f'phase12_minus_phase11_{field}', hour)
                condensation = np.sum(fix_cond - old_cond, axis=0, dtype=np.float64)
            unresolved = local - update - sedimentation - condensation
            if np.max(np.abs(residual)) > 1e-10:
                raise ValueError('contiguous call-state ledger does not close')
            for level in range(39):
                for point, point_id in enumerate(points):
                    rows.append({'lead_hour': hour, 'point_id': str(point_id), 'native_k_1based': level + 1,
                                 'field': field, 'units': unit,
                                 'old_entry_first': old_entry[0, level, point],
                                 'fix_entry_first': fix_entry[0, level, point],
                                 'old_return_last': old_return[-1, level, point],
                                 'fix_return_last': fix_return[-1, level, point],
                                 'delta_call_internal_sum': local[level, point],
                                 'delta_between_call_sum': external[level, point],
                                 'delta_endpoint_change': endpoint[level, point],
                                 'ledger_residual': residual[level, point],
                                 'delta_phase8_minus_phase6_sum': update[level, point],
                                 'delta_rain_sedimentation_sum': (float(sedimentation[level, point]) if field == 'QR' and np.isfinite(sedimentation[level, point]) else None),
                                 'paired_sedimentation_calls': int(sed_count[level, point]) if field == 'QR' else None,
                                 'delta_condensation_substep_sum': condensation[level, point] if field != 'QR' else None,
                                 'remaining_call_internal_sum': float(unresolved[level, point]) if np.isfinite(unresolved[level, point]) else None})
        for arm in ('OLD', 'FIX'):
            terms = {name: nominal_rate_integral(directories[arm], receipts[arm], name, hour)
                     for name in ('prevp', 'praut', 'pracw')}
            for level in range(39):
                for point, point_id in enumerate(points):
                    rate_rows.append({'lead_hour': hour, 'arm': arm, 'point_id': str(point_id),
                                      'native_k_1based': level + 1, 'units': 'kg kg-1 source term',
                                      **{name + '_dt_sum': values[level, point] for name, values in terms.items()}})
    if len(rows) != 70200 or len(rate_rows) != 35100:
        raise ValueError('required fixed-level process table scope is incomplete')
    write_csv(output / 'point_level_process_ledger.csv', rows)
    write_csv(output / 'point_level_nominal_rates.csv', rate_rows)
    group_rows = group_profiles(rows)
    write_csv(output / 'group_level_process_profiles.csv', group_rows)
    paths = [output / name for name in ('point_level_process_ledger.csv', 'point_level_nominal_rates.csv', 'group_level_process_profiles.csv')]
    result = {'status': 'CONTIGUOUS_PROCESS_COMPARISON_VALIDATED', 'rows': len(rows), 'hours': list(HOURS),
              'nominal_rate_rows': len(rate_rows), 'group_profile_rows': len(group_rows), 'points': 150, 'levels': 39, 'fields': FIELDS, 'full_launch_receipt_sha256': expected_launch_sha,
              'collector_receipt_sha256': {arm: sha(path / 'capture_receipt.json') for arm, path in directories.items()},
              'tool_sha256': sha(Path(__file__)),
              'outputs': {p.name: {'size_bytes': p.stat().st_size, 'sha256': sha(p)} for p in paths},
              'limits': ['Sums are over time at fixed native k, without vertical summation.',
                         'PREVP/PRAUT/PRACW time integrals are nominal source terms; they are not observed net state changes or causal rain fractions.',
                         'Between-call net changes include all external operations; they are not pure transport.',
                         'Remaining internal terms include unmeasured stages, clipping, and wrapper conversion/rounding.',
                         'Local state ledgers do not establish a column or domain water/energy budget.',
                         'Role profiles report point quantiles at each native k; groups overlap and are spatially correlated, and quantiles of components do not generally add.',
                         'No ledger bridges the uncaptured steps 361–720.',
                         'Missing conditional sedimentation records remain missing; incomplete 180-call sedimentation sums and remaining internal terms are null.',
                         'Condensation substep is followed by additional source processing.']}
    (output / 'summary_receipt.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--old-dir', type=Path, required=True)
    parser.add_argument('--fix-dir', type=Path, required=True)
    parser.add_argument('--launch-receipt', type=Path, required=True)
    parser.add_argument('--launch-receipt-sha256', required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists() or args.output_dir.is_symlink():
        raise FileExistsError(args.output_dir)
    stage = args.output_dir.with_name('.' + args.output_dir.name + '.stage-' + uuid.uuid4().hex)
    stage.mkdir(parents=True)
    try:
        result = summarize(args.old_dir, args.fix_dir, args.launch_receipt,
                           args.launch_receipt_sha256, stage)
        stage.rename(args.output_dir)
    except BaseException:
        shutil.rmtree(stage)
        raise
    print(json.dumps({'status': result['status'], 'rows': result['rows']}))


if __name__ == '__main__':
    main()
