#!/usr/bin/env python3
"""Reproduce selected PR154 and MP10 hourly surface rain from parent histories."""
import argparse
import csv
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

import netCDF4
import numpy as np

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'tools'))
import cp02_ice_surface_components as surface
import cp02_mp10_failure_cohorts as cohorts

BUNDLE = Path(__file__).resolve().parent.parent
RESULTS = ROOT / 'docs/evidence/cp02_pulse_path_20261110/evaluation/results'
PR154_RESULTS = ROOT / 'docs/evidence/cp02_first_ice_velocity_20261109/evaluation/results'
WORK = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch')
HISTORIES = {'FIRST_ICE_VELOCITY': WORK / 'b1_ice_velocity_20261109/runtime/forecasts/ICE_FIXED',
             'MP10': WORK / 'b1_pulse_path_20261110/runtime/forecasts/MP10'}
POINTS_SHA = 'f36d193647d04a4eb811318431dd15f0b92d0644d9815b35a3650d70b073888d'
RECEIPT_SHA = {'FIRST_ICE_VELOCITY': '882a33589369041d25eb235fb17567406e1b4f2765aa2983590f8a9326239fea',
               'MP10': 'c4afef355babc82744b1efca847ad596c784cd4bc1da55edb299b1c016569c33'}


def geometry(points, mapping):
    ids = np.array([int(r['flat_index_yx']) for r in points])
    if len(ids) != 30 or len(set(ids)) != 30:
        raise ValueError('expected 30 unique points')
    y, x = np.unravel_index(ids, mapping['valid'].shape)
    j, i = mapping['j0'][y, x] + 5, mapping['i0'][y, x] + 74
    if not mapping['valid'][y, x].all():
        raise ValueError('invalid mapping')
    if any(int(r['native_j0_fortran_one_based']) != jj + 1 or int(r['native_i0_fortran_one_based']) != ii + 1
           for r, jj, ii in zip(points, j, i)):
        raise ValueError('selected native geometry differs from mapping')
    u, v = mapping['u'][y, x], mapping['v'][y, x]
    weights = np.column_stack(((1-u)*(1-v), u*(1-v), (1-u)*v, u*v))
    if any(float(r[k]) != w for r, row in zip(points, weights) for k, w in zip(
            ('weight_j0_i0', 'weight_j0_i1', 'weight_j1_i0', 'weight_j1_i1'), row)):
        raise ValueError('selected weights differ from mapping')
    return ids, j, i, u, v


def extract_snapshot(path, expected_time, inventory, j, i):
    evaluator = surface.module(surface.EVAL)
    snap = evaluator.read_wrf_snapshot(path, expected_time, inventory)
    evaluator.raw_total(snap)
    with netCDF4.Dataset(path) as d:
        for name in ('I_RAINC', 'I_RAINNC', 'I_RAINSH'):
            if name in d.variables:
                values = np.ma.asarray(d.variables[name][:])
                if np.ma.is_masked(values) or not np.isfinite(values).all() or np.any(values != 0):
                    raise ValueError('invalid bucket counter')
    rows = []
    for name in surface.NAMES:
        field, valid = snap['components'][name]
        if not (valid[j, i] & valid[j, i+1] & valid[j+1, i] & valid[j+1, i+1]).all():
            raise ValueError('missing selected native corner')
        values = np.stack((field[j, i], field[j, i+1], field[j+1, i], field[j+1, i+1]), axis=-1)
        raw = values.astype(np.float32)
        if not np.array_equal(raw.astype(np.float64), values):
            raise ValueError('native corner is not lossless float32')
        rows.append(raw)
    return np.stack(rows, axis=1)


def run(output):
    if os.path.lexists(output):
        raise FileExistsError(output)
    points_path = BUNDLE / 'cohorts/selected_points.csv'
    if surface.identity(points_path)['sha256'] != POINTS_SHA:
        raise ValueError('frozen point identity mismatch')
    receipt_path = RESULTS / 'receipt.json'
    if surface.identity(receipt_path)['sha256'] != cohorts.RECEIPT_SHA:
        raise ValueError('evaluation receipt mismatch')
    inventory_path = surface.REFERENCE / 'inventory.json'
    if surface.identity(inventory_path)['sha256'] != cohorts.fa.INVENTORY_SHA:
        raise ValueError('inventory mismatch')
    evaluator = surface.module(surface.EVAL)
    inventory, mask, lat, lon, provenance = evaluator.load_reference(surface.REFERENCE, surface.ANALYSIS)
    with points_path.open() as stream:
        points = list(csv.DictReader(stream))
    mapping_path = RESULTS / 'bilinear_mapping.npz'
    eval_receipt = json.loads(receipt_path.read_text())
    if surface.identity(mapping_path)['sha256'] != eval_receipt['outputs'][mapping_path.name]:
        raise ValueError('mapping hash mismatch')
    with np.load(mapping_path, allow_pickle=False) as z:
        mapping = {k: z[k].copy() for k in z.files}
    ids, j, i, u, v = geometry(points, mapping)
    y, x = np.unravel_index(ids, mask.shape)
    if not mask[y, x].all() or any(float(r['latitude']) != lat[yy, xx] or float(r['longitude']) != lon[yy, xx]
                                    for r, yy, xx in zip(points, y, x)):
        raise ValueError('selected coordinates differ from reference')
    records = [surface.identity(p) for p in (Path(__file__), Path(surface.__file__),
        Path(cohorts.__file__), Path(cohorts.fa.__file__), surface.EVAL, points_path,
        inventory_path, receipt_path, mapping_path, PR154_RESULTS / 'receipt.json')]
    records.extend(surface.identity(p) for p in provenance.values())
    if surface.identity(surface.EVAL)['sha256'] != surface.EVAL_SHA:
        raise ValueError('surface evaluator changed')
    if surface.identity(PR154_RESULTS / 'receipt.json')['sha256'] != '09bd7015a9f84f3a79cd90a0dc00b2600f10f32589b26e336554e54e7dc24b16':
        raise ValueError('PR154 evaluation receipt changed')
    arrays = cohorts.prior.read_arrays(RESULTS)
    records.extend(surface.identity(RESULTS / f'hour_{h}_arrays.npz') for h in range(13, 19))
    index = {int(k): n for n, k in enumerate(arrays[13]['flat_index_yx'])}
    positions = [index[k] for k in ids]
    corners, rows, worst = {}, [], 0.
    for case, directory in HISTORIES.items():
        rp = directory / 'run_receipt.json'
        rr = surface.identity(rp)
        if rr['sha256'] != RECEIPT_SHA[case]:
            raise ValueError('run receipt changed')
        records.append(rr)
        receipt = json.loads(rp.read_text())
        if receipt['status'] != 'PASS' or receipt['exit_code'] != 0 or len(receipt['histories']) != 7:
            raise ValueError('incomplete parent run')
        expected = {Path(r['path']).name: r for r in receipt['histories']}
        fields = []
        for h in range(12, 19):
            path = directory / f'wrfout_d01_2026-08-16_{h:02d}:00:00'
            before = surface.identity(path)
            entry = expected.get(path.name, {})
            if any(before[k] != entry.get(k) for k in ('path', 'sha256', 'size_bytes')):
                raise ValueError('history does not match receipt')
            records.append(before)
            fields.append(extract_snapshot(path, datetime(2026, 8, 16, h, tzinfo=timezone.utc), inventory, j, i))
            if surface.identity(path) != before:
                raise ValueError('history changed while reading')
        corners[case] = np.stack(fields, axis=1)
        components, total = surface.replay(corners[case], u, v, 1e-6)
        for lead in range(1, 7):
            expected_total = arrays[lead + 12][case][positions]
            if not np.array_equal(total[:, lead-1], expected_total):
                raise ValueError(f'{case} lead {lead}: total does not reproduce frozen array')
            residual = components[:, lead-1].sum(axis=1) - total[:, lead-1]
            worst = max(worst, float(np.abs(residual).max()))
            for n, point in enumerate(points):
                rows.append({'lead_hour': lead, 'case': case, 'flat_index_yx': int(ids[n]),
                    'cohort': point['cohort'], 'rainc_mm': float(components[n, lead-1, 0]),
                    'rainnc_mm': float(components[n, lead-1, 1]), 'total_mm': float(total[n, lead-1]),
                    'component_sum_minus_total_mm': float(residual[n])})
    if worst > 1e-10:
        raise ValueError('component sum rounding exceeds tolerance')
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.surface-', dir=output.parent))
    try:
        np.savez_compressed(stage / 'native_corners.npz', **corners, u=u, v=v, flat_index_yx=ids)
        with (stage / 'point_components.csv').open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n')
            writer.writeheader(); writer.writerows(rows)
        for record in records:
            if surface.identity(record['path']) != record:
                raise ValueError('input changed')
        receipt = {'status': 'COMPLETE', 'inputs': records, 'rows': len(rows),
            'histories': 14, 'points': 30, 'native_corner_dtype': 'float32',
            'native_corners_axes': ['point', 'history', 'component RAINC,RAINNC', 'corner 00,10,01,11'],
            'evaluation_total': 'bitwise identical at all 360 point/case/lead combinations',
            'max_component_sum_rounding_mm': worst,
            'interpretation': 'Stored hourly components; differences do not establish process causation.',
            'outputs': {p.name: surface.identity(p)['sha256'] for p in sorted(stage.iterdir())}}
        (stage / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
        cohorts.prior.publish_new(stage, output)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return {'rows': len(rows), 'max_component_sum_rounding_mm': worst}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    print(json.dumps(run(parser.parse_args().output), indent=2))
