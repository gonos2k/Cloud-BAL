#!/usr/bin/env python3
"""Reduce terminal OFF/COUPLED histories on PR93's fixed QC source support."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import netCDF4
import numpy as np

ROOT = Path(__file__).resolve().parents[4]
TOOLS = ROOT / 'tools'
QC_EVIDENCE = ROOT / 'docs/evidence/pr93_qc_chain_20261020'


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'cannot load existing reader module: {path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Reuse existing history and fixed-support implementations; this reducer adds no reader framework.
sys_path = __import__('sys').path
sys_path.insert(0, str(TOOLS))
from pr86_compare_response import history_index, load_history  # noqa: E402
qc_support = load_module('pr93_qc_fixed_support_response', TOOLS / 'pr93_qc_fixed_support_response.py')

TIMESTAMP_FORMAT = '%Y-%m-%d_%H:%M:%S'
FIELDS = ('QCLOUD', 'pressure', 'geopotential', 'W')
UNITS = {'QCLOUD': 'kg/kg dry', 'pressure': 'Pa',
         'geopotential': 'm2 s-2', 'W': 'm s-1'}
MODEL_TIMESTEP_SECONDS = 20


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            value.update(block)
    return value.hexdigest()


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def terminal_receipt(path: Path, preflight_path: Path, arm: str) -> dict[str, Any]:
    raw = path.read_bytes()
    receipt = json.loads(raw)
    preflight_raw = preflight_path.read_bytes()
    preflight = json.loads(preflight_raw)
    require(receipt.get('arm', '').upper() == arm, f'{arm}: receipt arm identity mismatch')
    require(preflight.get('arm', '').upper() == arm, f'{arm}: preflight arm identity mismatch')
    status = receipt.get('status')
    require(status in ('COMPLETE', 'INCOMPLETE'),
            f'{arm}: receipt is not terminal (expected COMPLETE or INCOMPLETE)')
    returncode = receipt.get('returncode')
    require(isinstance(returncode, int), f'{arm}: missing terminal return code')
    if status == 'COMPLETE':
        require(returncode == 0, f'{arm}: COMPLETE receipt has nonzero return code')
    requested_seconds = preflight.get('duration_seconds')
    timestep_seconds = preflight.get('timestep_seconds')
    expected_timesteps = preflight.get('expected_timesteps')
    require(isinstance(requested_seconds, int) and isinstance(timestep_seconds, int) and
            isinstance(expected_timesteps, int), f'{arm}: incomplete hash-bound preflight timing')
    require(timestep_seconds == MODEL_TIMESTEP_SECONDS and
            expected_timesteps * timestep_seconds == requested_seconds,
            f'{arm}: preflight duration/timestep contract is inconsistent')
    require(preflight.get('launch_environment') == receipt.get('launch_environment'),
            f'{arm}: receipt launch environment differs from preflight')
    frozen_executable_sha = (receipt.get('frozen_executable_sha256') or
                             receipt.get('baseline_frozen_executable_sha256'))
    require(preflight.get('source_receipt_sha256') == receipt.get('source_receipt_sha256') and
            preflight.get('executable_sha256') == frozen_executable_sha,
            f'{arm}: receipt source/frozen executable differs from preflight')
    preflight_candidate_sha = preflight.get('candidate_build', {}).get('executable_sha256')
    if preflight_candidate_sha:
        require(preflight_candidate_sha == receipt.get('executed_executable_sha256'),
                f'{arm}: executed candidate executable differs from preflight build')
    for field in ('candidate_wrfinput_sha256', 'candidate_wrfbdy_sha256', 'candidate_namelist_sha256'):
        if preflight.get(field):
            require(preflight[field] == receipt.get(field), f'{arm}: receipt {field} differs from preflight')
    final_step = receipt.get('final_completed_step')
    require(isinstance(final_step, int) and final_step > 0, f'{arm}: missing completed timestep count')
    require(not receipt.get('processing_errors'), f'{arm}: receipt contains processing errors')
    completed_steps = (receipt.get('snapshots') or {}).get('completed_post_kdm6_timesteps',
                       receipt.get('completed_post_kdm6_timesteps'))
    require(completed_steps == list(range(1, final_step + 1)),
            f'{arm}: completed timesteps are not the verified contiguous prefix 1..{final_step}')
    executable_sha = receipt.get('executed_executable_sha256') or receipt.get('candidate_build', {}).get('executable_sha256')
    require(isinstance(executable_sha, str) and len(executable_sha) == 64,
            f'{arm}: no executable hash in terminal receipt')
    executable_path = receipt.get('candidate_build', {}).get('executable_path')
    candidate_sha = receipt.get('candidate_build', {}).get('executable_sha256')
    if candidate_sha:
        require(candidate_sha == executable_sha, f'{arm}: executed and candidate executable hashes differ')
    if executable_path and Path(executable_path).is_file():
        require(sha256(Path(executable_path)) == executable_sha,
                f'{arm}: executable file does not match receipt hash')
    inputs = receipt.get('source_inputs_after_sha256')
    if not isinstance(inputs, dict) or not inputs:
        inputs = {name: receipt.get(name) for name in
                  ('candidate_wrfinput_sha256', 'candidate_wrfbdy_sha256', 'candidate_namelist_sha256')
                  if receipt.get(name)}
    require(bool(inputs), f'{arm}: receipt has no source/input hashes')
    expected_times = receipt.get('expected_model_timestamps')
    require(isinstance(expected_times, list) and len(expected_times) == expected_timesteps,
            f'{arm}: expected model timestamps differ from preflight timestep count')
    expected_first = dt.datetime.strptime(expected_times[0], TIMESTAMP_FORMAT)
    model_start = expected_first - dt.timedelta(seconds=timestep_seconds)
    if status == 'COMPLETE' and requested_seconds is not None:
        require(final_step * timestep_seconds >= requested_seconds,
                f'{arm}: COMPLETE receipt ends before its declared requested window')
    return {
        'path': str(path.resolve()), 'sha256': hashlib.sha256(raw).hexdigest(),
        'preflight': {'path': str(preflight_path.resolve()),
                      'sha256': hashlib.sha256(preflight_raw).hexdigest(),
                      'duration_seconds': requested_seconds,
                      'timestep_seconds': timestep_seconds,
                      'expected_timesteps': expected_timesteps,
                      'launch_request_sha256': preflight.get('launch_environment', {}).get('launch_request_sha256')},
        'status': status, 'returncode': returncode,
        'final_completed_step': final_step,
        'requested_window_seconds': requested_seconds,
        'timestep_seconds': timestep_seconds,
        'completed_prefix_window_seconds': final_step * timestep_seconds,
        'model_start_timestamp': model_start.strftime(TIMESTAMP_FORMAT),
        'completed_post_kdm6_timesteps': completed_steps,
        'executed_executable_sha256': executable_sha,
        'executable_path': executable_path,
        'candidate_build': receipt.get('candidate_build'),
        'inputs_sha256': inputs,
        'source_receipt_sha256': receipt.get('source_receipt_sha256'),
        'candidate_wrfinput_sha256': receipt.get('candidate_wrfinput_sha256'),
        'candidate_wrfbdy_sha256': receipt.get('candidate_wrfbdy_sha256'),
        'candidate_namelist_sha256': receipt.get('candidate_namelist_sha256'),
        'generated_history_files': [row for row in receipt.get('generated_files', [])
                                    if Path(row.get('path', '')).name.startswith('wrfout_d01_')],
    }


def stats(values: np.ndarray) -> dict[str, float]:
    return {'mean': float(np.mean(values)),
            'rms': float(np.sqrt(np.mean(values * values))),
            'max_abs': float(np.max(np.abs(values))),
            'signed_sum': float(np.sum(values))}


def grid_geometry(path: Path, mask: np.ndarray, composition: dict[str, Any]) -> dict[str, Any]:
    with netCDF4.Dataset(path) as ds:
        ds.set_auto_mask(False)
        shape = ds['QCLOUD'].shape
        require(len(shape) == 4 and shape[1:] == (39, 282, 234),
                f'unexpected WRF QCLOUD shape: {shape}')
        lats = np.asarray(ds['XLAT'][0, 1:-1, 1:-1], dtype=np.float64)
        lons = np.asarray(ds['XLONG'][0, 1:-1, 1:-1], dtype=np.float64)
        if 'Times' in ds.variables:
            first_time = netCDF4.chartostring(ds['Times'][:]).tolist()[0]
        attrs = {name: ds.getncattr(name) for name in
                 ('GRID_ID', 'PARENT_ID', 'I_PARENT_START', 'J_PARENT_START',
                  'WEST-EAST_GRID_DIMENSION', 'SOUTH-NORTH_GRID_DIMENSION')
                 if name in ds.ncattrs()}
        attrs = {name: value.item() if isinstance(value, np.generic) else value
                 for name, value in attrs.items()}
    columns = np.argwhere(mask.any(axis=0))
    details = []
    for active_j, active_i in columns:
        details.append({
            'active_j0_i0': [int(active_j), int(active_i)],
            'wrf_domain_j0_i0': [int(active_j + 1), int(active_i + 1)],
            'latitude_deg': float(lats[active_j, active_i]),
            'longitude_deg': float(lons[active_j, active_i]),
        })
    source_targets = [[int(row['target_i0']), int(row['target_j0'])]
                      for row in composition['targets']]
    return {
        'history_first_timestamp': first_time,
        'raw_qcloud_shape_t_k_j_i': list(shape),
        'active_mass_grid_shape_k_j_i': [39, 280, 232],
        'active_to_raw_outer_ring_offset': {'j': 1, 'i': 1},
        'source_target_columns_i0_j0': source_targets,
        'support_columns': details,
        'wrf_global_attributes_if_present': attrs,
        'index_note': ('WRF domain-grid indices are reported zero-based. Active indices are relative '
                       'to the outer-ring-cropped mass grid; raw/domain indices add one. Parent-start '
                       'attributes are included when available; no unverified global offset is inferred.'),
    }


def reduce(args: argparse.Namespace) -> dict[str, Any]:
    receipts = {arm: terminal_receipt(getattr(args, f'{arm.lower()}_receipt'),
                                     getattr(args, f'{arm.lower()}_preflight'), arm)
                for arm in ('OFF', 'COUPLED')}
    composition_path = QC_EVIDENCE / 'qc_vertical_composition.json'
    composition_doc = json.loads(composition_path.read_text())
    composition = composition_doc['composed_qc_vertical_influence']
    mask = qc_support.fixed_support(composition_path)
    require(int(mask.sum()) == 613 and int(mask.any(axis=0).sum()) == 16,
            'fixed source-derived mask changed')

    roots = {'OFF': args.off_history_root.resolve(), 'COUPLED': args.coupled_history_root.resolve()}
    indices, file_ids = {}, {}
    for arm in roots:
        indices[arm], file_ids[arm] = history_index(roots[arm])
        require(indices[arm], f'{arm}: no indexed history frames')
        generated = {Path(row['path']).name: row for row in receipts[arm]['generated_history_files']}
        indexed = {Path(path).name: (Path(path), identity) for path, identity in file_ids[arm].items()}
        require(generated and set(generated) == set(indexed),
                f'{arm}: indexed history filenames differ from receipt generated_files')
        for name, (path, identity) in indexed.items():
            row = generated[name]
            require(identity['sha256'] == row.get('sha256') and path.stat().st_size == row.get('bytes'),
                    f'{arm}: current history file differs from terminal receipt: {name}')
    all_common_times = sorted(set(indices['OFF']) & set(indices['COUPLED']))
    require(all_common_times, 'OFF/COUPLED have no common stored history times')
    model_starts = {receipts[arm]['model_start_timestamp'] for arm in receipts}
    require(len(model_starts) == 1, 'OFF/COUPLED preflights imply different model start times')
    start = dt.datetime.strptime(next(iter(model_starts)), TIMESTAMP_FORMAT)
    all_seconds = {time: int((dt.datetime.strptime(time, TIMESTAMP_FORMAT) - start).total_seconds())
                   for time in all_common_times}
    require(all(value >= 0 for value in all_seconds.values()),
            'common history contains a stored timestamp before preflight-derived model T0')
    require(start.strftime(TIMESTAMP_FORMAT) in set(indices['OFF']) & set(indices['COUPLED']),
            'expected model T0 is not present in both histories')
    common_prefix_seconds = min(receipts[arm]['completed_prefix_window_seconds'] for arm in receipts)
    common_times = [time for time in all_common_times if all_seconds[time] <= common_prefix_seconds]
    require(common_times, 'no common stored history frames lie within both completed prefixes')
    seconds = {time: all_seconds[time] for time in common_times}
    stored_windows = {}
    for arm in receipts:
        arm_times = {time for identity in file_ids[arm].values() for time in identity['timestamps']}
        arm_seconds = [(dt.datetime.strptime(time, TIMESTAMP_FORMAT) - start).total_seconds()
                       for time in arm_times]
        stored_windows[arm] = [int(min(arm_seconds)), int(max(arm_seconds))]

    records = []
    initial_delta: dict[str, np.ndarray] | None = None
    geometry = None
    for timestamp in common_times:
        fields = {}
        for arm in ('OFF', 'COUPLED'):
            actual_time, data, artifact = load_history(*indices[arm][timestamp])
            require(actual_time == timestamp, f'{arm}: history frame/time mismatch')
            fields[arm] = {name: data[name][mask].copy() for name in FIELDS}
            if arm == 'OFF' and geometry is None:
                geometry = grid_geometry(Path(artifact['path']), mask, composition)
        deltas = {name: fields['COUPLED'][name] - fields['OFF'][name] for name in FIELDS}
        if initial_delta is None:
            initial_delta = {name: value.copy() for name, value in deltas.items()}
        row = {'timestamp': timestamp, 'stored_seconds_from_T0': seconds[timestamp], 'fields': {}}
        for name in FIELDS:
            row['fields'][name] = {
                'unit': UNITS[name],
                'delta_coupled_minus_off': stats(deltas[name]),
                'delta_minus_T0': stats(deltas[name] - initial_delta[name]),
            }
        records.append(row)

    for arm in roots:
        for path, identity in file_ids[arm].items():
            require(sha256(Path(path)) == identity['sha256'],
                    f'{arm}: history changed while being read: {path}')
    common_path = composition_path
    return {
        'schema': 'pr93_closed_runtime_fixed_support_response_v1',
        'physical_approval': 'FAIL_OPEN',
        'analysis_status': ('INCOMPLETE_RECEIPT_VALID_PREFIX_ANALYZED'
                            if any(receipts[arm]['status'] == 'INCOMPLETE' for arm in receipts)
                            else 'COMPLETE_RECEIPTS_PREFIX_ANALYZED'),
        'scope': ('Same-cell OFF/COUPLED response on the PR93 613-point QC source-operator mask; '
                  'unweighted state differences, not carrier inventory, observations, or closure.'),
        'run_receipts': receipts,
        'history': {
            'OFF_root': str(roots['OFF']), 'COUPLED_root': str(roots['COUPLED']),
            'OFF_files': file_ids['OFF'], 'COUPLED_files': file_ids['COUPLED'],
            'common_stored_timestamps': common_times,
            'stored_seconds_from_common_T0': [seconds[t] for t in common_times],
            'requested_window_seconds_by_arm': {arm: receipts[arm]['requested_window_seconds']
                                                for arm in receipts},
            'completed_prefix_window_seconds_by_arm': {
                arm: receipts[arm]['completed_prefix_window_seconds'] for arm in receipts},
            'common_completed_prefix_seconds': common_prefix_seconds,
            'stored_history_window_seconds_by_arm': stored_windows,
            'stored_common_times_beyond_analyzed_prefix': [time for time in all_common_times
                                                            if all_seconds[time] > common_prefix_seconds],
            'common_stored_history_window_seconds_analyzed': [seconds[t] for t in (common_times[0], common_times[-1])],
            'note': ('A stored history timestamp identifies an output record, not the count of '
                     'completed model timesteps; requested duration, verified completed prefix, and '
                     'actual stored window are reported separately. Only common records at or before '
                     'both completed-prefix limits are analyzed. T600 is included only if stored in '
                     'both arms and within both completed prefixes.'),
        },
        'support': {
            'composition_path': str(common_path), 'composition_sha256': sha256(common_path),
            'rule': 'include native eta cell iff composed_qc_source_links is nonempty',
            'point_count': int(mask.sum()), 'column_count': int(mask.any(axis=0).sum()),
            'level_count': int(mask.any(axis=(1, 2)).sum()),
            'mask_shape_kji': list(mask.shape), 'geometry': geometry,
        },
        'records': records,
        'units': UNITS,
        'history_reader': {'path': str(TOOLS / 'pr86_compare_response.py'),
                           'sha256': sha256(TOOLS / 'pr86_compare_response.py')},
        'mask_reducer': {'path': str(TOOLS / 'pr93_qc_fixed_support_response.py'),
                         'sha256': sha256(TOOLS / 'pr93_qc_fixed_support_response.py')},
        'reducer': {'path': str(Path(__file__).resolve()), 'sha256': sha256(Path(__file__))},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--off-receipt', type=Path, required=True)
    parser.add_argument('--coupled-receipt', type=Path, required=True)
    parser.add_argument('--off-preflight', type=Path, required=True)
    parser.add_argument('--coupled-preflight', type=Path, required=True)
    parser.add_argument('--off-history-root', type=Path, required=True)
    parser.add_argument('--coupled-history-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = reduce(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + '\n')
    print(f'wrote {args.output}')


if __name__ == '__main__':
    main()
