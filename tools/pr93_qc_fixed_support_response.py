#!/usr/bin/env python3
"""Reproduce the C18 fixed-QC-support response and matched C14 activity window."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import netCDF4
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'docs/evidence/pr93_qc_chain_20261020'
C18_ROOT = ROOT / 'docs/evidence/pr92_source_store_20261020/c18'
C18_COMMON = C18_ROOT / 'closed_runtime_20261020/history_common_c17.json'
C14_ACTIVITY = ROOT / 'docs/evidence/pr91_science_sources_20261020/c14_current_response/cold_area_weighted.json'
SECONDS = (0, 60, 120, 180, 240, 300, 360, 420)
ARMS = ('OFF', 'COUPLED')
GROUPS = ('AUT', 'G', 'NG')
FIELDS = ('QCLOUD', 'pressure', 'geopotential', 'W')
UNITS = {'QCLOUD': 'kg/kg dry', 'pressure': 'Pa',
         'geopotential': 'm2 s-2', 'W': 'm s-1'}

sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'tools'))
from pr86_compare_response import load_history  # noqa: E402


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            value.update(block)
    return value.hexdigest()


def metric(values: np.ndarray) -> dict[str, float]:
    return {
        'mean': float(np.mean(values)),
        'rms': float(np.sqrt(np.mean(values * values))),
        'max_abs': float(np.max(np.abs(values))),
        'signed_sum': float(np.sum(values)),
    }


def fixed_support(composition_path: Path) -> np.ndarray:
    composition = json.loads(composition_path.read_text())['composed_qc_vertical_influence']
    mask = np.zeros((39, 280, 232), dtype=bool)
    for target in composition['targets']:
        i0, j0 = int(target['target_i0']), int(target['target_j0'])
        for level in target['native_levels']:
            if level['composed_qc_source_links']:
                mask[int(level['native_eta_level0']), j0 - 1, i0 - 1] = True
    if int(mask.sum()) != composition['totals']['levels_with_qc_support']:
        raise ValueError('source-link mask count differs from QC composition totals')
    if int(mask.sum()) != 613 or int(mask.any(axis=0).sum()) != 16:
        raise ValueError('fixed support no longer has 613 native points in 16 columns')
    return mask


def load_histories(common: dict[str, Any], mask: np.ndarray) -> tuple[dict, dict]:
    frames: dict[str, dict[int, dict[str, np.ndarray]]] = {}
    identities: dict[str, dict[str, Any]] = {}
    for arm in ARMS:
        record = common['arms'][arm.lower()]
        path = Path(record['c18_path'])
        if digest(path) != record['c18_sha256'] or not record['whole_file_bit_identical']:
            raise ValueError(f'{arm} history no longer matches common-history receipt')
        receipt_path = C18_ROOT / arm.lower() / 'receipt.json'
        receipt = json.loads(receipt_path.read_text())
        if receipt['arm'] != arm or receipt['final_completed_step'] != 23:
            raise ValueError(f'{arm} run receipt identity changed')
        with netCDF4.Dataset(path) as dataset:
            times = netCDF4.chartostring(dataset['Times'][:]).tolist()
        expected = record['times_c18']
        if times != expected or len(times) != len(SECONDS):
            raise ValueError(f'{arm} history timestamp sequence changed')
        by_second = {}
        for frame, second in enumerate(SECONDS):
            _, fields, _ = load_history(path, frame)
            by_second[second] = {name: fields[name][mask].copy() for name in FIELDS}
        frames[arm] = by_second
        identities[arm] = {
            'path': str(path), 'sha256': digest(path), 'timestamps': times,
            'run_receipt': {'path': str(receipt_path), 'sha256': digest(receipt_path),
                            'source_receipt_sha256': receipt['source_receipt_sha256'],
                            'run_status': receipt['status'],
                            'final_completed_step': receipt['final_completed_step']},
        }
    return frames, identities


def activity_comparison() -> dict[str, Any]:
    c14 = json.loads(C14_ACTIVITY.read_text())
    paths = {
        arm: C18_ROOT / 'closed_runtime_20261020' / f'{arm.lower()}_area_activity_through_step23.json'
        for arm in ARMS
    }
    c18 = {arm: json.loads(path.read_text()) for arm, path in paths.items()}
    result = {}
    for arm in ARMS:
        rows = []
        for step in range(1, 13):
            old = c14[arm]['by_timestep'][str(step)]
            new = c18[arm]['by_timestep'][str(step)]
            row: dict[str, Any] = {'timestep': step, 'model_seconds': 20 * step}
            for stage in ('proposed', 'applied', 'deferred'):
                old_sum = sum(old[group][stage]['half_l1_kg'] for group in GROUPS)
                new_sum = sum(new[group][stage]['half_l1_kg'] for group in GROUPS)
                row[stage] = {
                    'C14_kg': old_sum, 'C18_kg': new_sum,
                    'C18_minus_C14_kg': new_sum - old_sum,
                    'C18_over_C14': new_sum / old_sum if old_sum else None,
                }
            rows.append(row)
        result[arm] = {
            'timestep_range_inclusive': [1, 12], 'model_seconds_range': [20, 240],
            'groups_summed': list(GROUPS), 'rows': rows,
        }
    return {
        'interpretation': ('C18 versus C14 same timestep indices 1..12 (20..240 s), by-timestep '
                           'kg activity; this diagnostic sum is not total physical throughput and '
                           'does not compare old 240 s with new 460 s aggregates.'),
        'arms': result,
        'bindings': {
            'C14': {'path': str(C14_ACTIVITY), 'sha256': digest(C14_ACTIVITY)},
            **{f'C18_{arm}': {'path': str(path), 'sha256': digest(path)}
               for arm, path in paths.items()},
        },
    }


def build() -> dict[str, Any]:
    composition_path = EVIDENCE / 'qc_vertical_composition.json'
    qc_chain_path = EVIDENCE / 'qc_chain.json'
    common = json.loads(C18_COMMON.read_text())
    mask = fixed_support(composition_path)
    frames, histories = load_histories(common, mask)
    result: dict[str, Any] = {}
    for second in SECONDS:
        result[str(second)] = {}
        for field in FIELDS:
            delta = frames['COUPLED'][second][field] - frames['OFF'][second][field]
            initial = frames['COUPLED'][0][field] - frames['OFF'][0][field]
            result[str(second)][field] = {
                'unit': UNITS[field],
                'delta_coupled_minus_off': metric(delta),
                'delta_minus_t0': metric(delta - initial),
            }
    composition = json.loads(composition_path.read_text())['composed_qc_vertical_influence']
    chain = json.loads(qc_chain_path.read_text())
    result['schema'] = 'pr93_c18_fixed_support_response_v1'
    result['physical_approval'] = 'FAIL_OPEN'
    result['support'] = {
        'source_path': str(composition_path), 'source_sha256': digest(composition_path),
        'rule': ('native eta level included iff its composed_qc_source_links list is nonempty; '
                 'mask independent of runtime QC differences'),
        'target_columns_i0_j0': [[int(t['target_i0']), int(t['target_j0'])]
                                 for t in composition['targets']],
        'shape_kji': [39, 280, 232],
        'axis_order': ['eta_level_k', 'active_j', 'active_i'],
        'outer_ring_mapping': ('load_history removes the raw mass-grid outer ring via [1:-1,1:-1]; '
                               'raw index 1 is returned index 0, so source target i0,j0 maps to '
                               'active indices i0-1,j0-1.'),
        'supported_native_cell_count': int(mask.sum()),
        'levels_with_support': int(mask.any(axis=(1, 2)).sum()),
        'supported_columns': int(mask.any(axis=0).sum()),
    }
    result['history_identities'] = {
        'arms': histories, 'common_history_path': str(C18_COMMON),
        'common_history_sha256': digest(C18_COMMON),
    }
    result['qc_chain_source_bindings'] = {
        'qc_chain_path': str(qc_chain_path), 'qc_chain_sha256': digest(qc_chain_path),
        'met_em': chain['input_bindings']['met_em'],
        'LAPS': chain['input_bindings']['laps'], 'wrfinput': chain['input_bindings']['wrfinput'],
        'qc_vertical_composition_sha256': digest(composition_path),
    }
    result['common_time_cold_activity_c18_vs_c14'] = activity_comparison()
    result['generator'] = {'path': str(Path(__file__).resolve()), 'sha256': digest(Path(__file__))}
    return result


def main() -> None:
    output = EVIDENCE / 'c18_fixed_support_response.json'
    output.write_text(json.dumps(build(), indent=2, sort_keys=True, allow_nan=False) + '\n')
    print(f'wrote {output}')


if __name__ == '__main__':
    main()
