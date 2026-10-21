#!/usr/bin/env python3
"""Join compact liquid-store accounts to the same receipt-bound C1 call."""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import netCDF4
import numpy as np
from native_kdm6_trace import read_dump
from pr67_kdm6_process_budget import parse_process_capture
from pr95_call_budget import WATER, HISTORY, sha256, _read_map_geometry, _bottom_phase_mass, _stats

C1_EXE = 'a714f00d3f81c0b47d94aef815f1f765ae48842e9de629cb869323ccfc22a96d'
C1_SOURCE = 'f09a413c36b7bda9fb7376f0276e00329179c68bdbef1e4766bae2811152f58b'


def read_columns(path: Path, bounds: dict) -> tuple[np.ndarray, np.ndarray]:
    shape = (bounds['jte']-bounds['jts']+1, bounds['ite']-bounds['its']+1)
    counts = np.zeros((*shape, 6), dtype=np.int64)
    values = np.zeros((*shape, 11), dtype=np.float64)
    seen = np.zeros(shape, dtype=bool)
    with path.open() as stream:
        for line in stream:
            row = line.split()
            if len(row) != 20 or row[0] != 'LIQCOL':
                raise ValueError('invalid compact column record')
            i, j = map(int, row[1:3])
            if not (bounds['its'] <= i <= bounds['ite'] and bounds['jts'] <= j <= bounds['jte']):
                raise ValueError('column outside captured call')
            slot = (j-bounds['jts'], i-bounds['its'])
            if seen[slot]:
                raise ValueError('duplicate compact column record')
            n = np.asarray(row[3:9], dtype=np.int64)
            v = np.asarray(row[9:], dtype=np.float64)
            if np.any(n < 0) or n[:4].sum() != n[5] or not np.isfinite(v).all():
                raise ValueError('invalid event counts or finite column account')
            if n[4] > n[5] or np.any(v[[2,4,9,10]] < 0):
                raise ValueError('invalid clipped-event or absolute account')
            if n[5] == 0 and np.any(v != 0):
                raise ValueError('nonzero account without events')
            seen[slot] = True
            counts[slot], values[slot] = n, v
    if not seen.all():
        raise ValueError('missing compact column records')
    return counts, values


def bound_capture(receipt: dict, path: Path, name: str) -> None:
    rows = [r for r in receipt['compressed_outputs'] if Path(r['path']).name == name]
    if len(rows) != 1 or sha256(path) != rows[0]['sha256']:
        raise ValueError(f'expanded capture is not receipt-bound: {name}')


def same_call_bottom(process: Path, pre: dict, area: np.ndarray) -> np.ndarray:
    stages = parse_process_capture(process)
    b = pre['bounds']
    den = pre['fields']['DEN'].astype(float)
    dz = pre['fields']['DELZ'].astype(float)
    if len(stages) != 3*area.shape[0]:
        raise ValueError('process capture does not cover same call')
    bottom = np.zeros_like(area)
    for j in range(area.shape[0]):
        group = stages[3*j:3*j+3]
        for n, row in enumerate(group):
            header = (row['stage'], row['lat'], row['its'], row['ite'], row['kts'], row['kte'])
            expected = (n, b['jts']+j, b['its'], b['ite'], b['kts'], b['kte'])
            if header != expected or row['dtcld'] != pre['params']['dt_s']:
                raise ValueError('process stage identity differs from call')
        if (not np.array_equal(group[0]['density'], den[j]) or
                not np.array_equal(group[0]['delz'], dz[j]) or
                not np.array_equal(group[2]['delz'], dz[j,0])):
            raise ValueError('process carrier differs from call')
        row = group[2]
        bottom[j] = np.sum(_bottom_phase_mass(row['fall'], row['delz'], row['denr'],
                                             row['dtcld'], area[j]), axis=0)
    return bottom


def analyze(root: Path, pre_path: Path, post_path: Path, process_path: Path,
            replay_post: Path, columns_path: Path) -> dict:
    receipt_path = root/'receipt.json'
    receipt = json.loads(receipt_path.read_text())
    if (receipt.get('status') != 'COMPLETE' or receipt.get('returncode') != 0 or
            receipt.get('executed_executable_sha256') != C1_EXE):
        raise ValueError('expected closed frozen C1 run')
    candidate = receipt['candidate_build']
    build_path = Path(candidate['receipt_path'])
    if sha256(build_path) != candidate['receipt_sha256']:
        raise ValueError('candidate build receipt changed')
    build = json.loads(build_path.read_text())
    source = build['source_overrides']['module_mp_kdm6.o']
    if source['staged_sha256'] != C1_SOURCE or sha256(Path(source['staged_path'])) != C1_SOURCE:
        raise ValueError('candidate KDM6 source changed')
    for p, name in [(pre_path, 'kdm6_first_call_pre.raw'),
                    (post_path, 'kdm6_first_call_post.raw'), (process_path, 'pr67_kdm6_process.raw')]:
        bound_capture(receipt, p, name)
    if sha256(replay_post) != sha256(post_path):
        raise ValueError('instrumented full replay differs from actual 17-field post capture')
    pre, post = read_dump(pre_path), read_dump(post_path)
    if (pre['stage'], post['stage'], pre['itimestep'], post['itimestep']) != (1,2,1,1):
        raise ValueError('expected same T1 pre/post call')
    if pre['bounds'] != post['bounds'] or pre['params'] != post['params']:
        raise ValueError('pre/post headers differ')
    b = pre['bounds']
    fields, after = pre['fields'], post['fields']
    density, thickness = fields['DEN'].astype(float), fields['DELZ'].astype(float)
    if (not np.isfinite(density).all() or not np.isfinite(thickness).all() or
            np.any(density <= 0) or np.any(thickness <= 0) or
            not np.array_equal(fields['DEN'], after['DEN']) or
            not np.array_equal(fields['DELZ'], after['DELZ'])):
        raise ValueError('same-call carrier must be finite, positive and fixed')
    history = root/'run'/HISTORY
    generated = {Path(r['path']).name:r['sha256'] for r in receipt['generated_files']}
    if sha256(history) != generated.get(HISTORY):
        raise ValueError('history area source is not receipt-bound')
    with netCDF4.Dataset(history) as ds:
        ds.set_auto_mask(False)
        area, _, _ = _read_map_geometry(ds, slice(b['jts']-1,b['jte']), slice(b['its']-1,b['ite']))
    mass = density*thickness*area[:,None,:]
    delta = np.zeros_like(mass)
    for name in WATER:
        a, z = fields[name].astype(float), after[name].astype(float)
        if not np.isfinite(a).all() or not np.isfinite(z).all():
            raise ValueError('nonfinite water endpoint')
        delta += (z-a)*mass
    raw = delta.sum(axis=1)+same_call_bottom(process_path, pre, area)
    counts, v = read_columns(columns_path, b)
    rounding = (v[:,:,0]+v[:,:,1])*area
    unexplained = raw-rounding
    order = np.argsort(np.abs(unexplained), axis=None)[-20:][::-1]
    return {
        'schema':'pr97_samecall_compact_liquid_account_v1', 'arm':receipt['arm'],
        'timestep':1, 'call_seconds':pre['params']['dt_s'], 'columns':int(area.size),
        'measure':'input DEN*DELZ*map area, fixed during this KDM6 call',
        'R_raw':_stats(raw), 'C_liquid_store':_stats(rounding),
        'R_unexplained_after_liquid_only':_stats(unexplained),
        'liquid_account':{
            'event_counts':dict(zip(['activation','full_evaporation','general_negative_extent',
                'general_positive_extent','clipped_exact_target','all_events'],
                map(int, counts.sum(axis=(0,1))))),
            'columns_with_events':int(np.count_nonzero(counts[:,:,5])),
            'Q_store_error_kg':math.fsum((v[:,:,0]*area).flat),
            'QC_store_error_kg':math.fsum((v[:,:,1]*area).flat),
            'L1_event_error_kg':math.fsum((v[:,:,2]*area).flat),
            'max_abs_event_error_kg':float(np.max(v[:,:,10]*area)),
            'signed_approved_extent_kg':math.fsum((v[:,:,3]*area).flat)},
        'largest_unexplained_columns':[
            {'i':int(n%area.shape[1]+b['its']), 'j':int(n//area.shape[1]+b['jts']),
             'R_raw_kg':float(raw.flat[n]), 'C_liquid_store_kg':float(rounding.flat[n]),
             'R_unexplained_kg':float(unexplained.flat[n])} for n in order],
        'identity':{'receipt_sha256':sha256(receipt_path), 'build_receipt_sha256':sha256(build_path),
            'executable_sha256':C1_EXE, 'KDM6_source_sha256':C1_SOURCE,
            'captures':{p.name:sha256(p) for p in (pre_path,post_path,process_path)},
            'history_sha256':sha256(history), 'compact_columns_sha256':sha256(columns_path),
            'replay_post_sha256':sha256(replay_post), 'all_17_fields_and_XLAND_byte_equal':True},
        'limits':['Only liquid activation and general/full evaporation stores are reduced.',
            'Other phase, sedimentation, cutoff and representation terms remain unreduced.',
            'REAL64 compensated compact sums are numerical accounts, not exact rational tile closure.',
            'No water correction; local exact reference tests remain separate from tile aggregation.',
            'Not native hybrid host water, energy, mass-wind or observation closure.'],
        'physical_approval':'FAIL_OPEN'}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('run-root','pre','post','process','replay-post','liquid-columns','output'):
        p.add_argument('--'+name, type=Path, required=True)
    a = p.parse_args()
    report = analyze(a.run_root,a.pre,a.post,a.process,a.replay_post,a.liquid_columns)
    a.output.write_text(json.dumps(report,indent=2)+'\n')


if __name__ == '__main__':
    main()
