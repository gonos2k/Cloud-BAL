#!/usr/bin/env python3
"""Recount first-call global entry/return against frozen initial rain number."""
from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

from netCDF4 import Dataset
import numpy as np

import cp02_state_path as state

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / 'docs/evidence/cp02_initial_boundaries_20261105'
PRIOR = ROOT / 'docs/evidence/cp02_thermo_cloud_path_20261105'
PLAN_SHA = '06bcef5161a9d1016e19f8344c8ca086f8f83650c94f1a284054fda9ef184812'
FIELDS = ('TH', 'QV', 'QC', 'QR', 'QI', 'QS', 'QG', 'NN', 'NC', 'NI', 'NR', 'BG', 'DEN', 'TK')
COMPARE = ('NR', 'QV', 'QC', 'TH', 'TK')
SHAPE = (282, 234, 39)
ARMS = ('B1', 'DM065')


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify_plan(path):
    if sha(path) != PLAN_SHA:
        raise ValueError('frozen plan differs')
    plan = json.loads(Path(path).read_text())
    if plan['status'] != 'FROZEN_BEFORE_ANALYSIS' or tuple(plan['shape_yxz']) != SHAPE:
        raise ValueError('invalid frozen plan')
    for relative, expected in plan['sources'].items():
        if sha(PRIOR / relative) != expected:
            raise ValueError(f'prior source differs: {relative}')
    if sha(ROOT / 'tools/cp02_state_path.py') != plan['reader_sha256']:
        raise ValueError('strict global reader differs')
    if sha(ROOT / 'docs/evidence/cp02_state_path_20261104/native/state_schema.json') != '96207bce9553f94f0457f1daaea0afb534fd34a07a107f24973adc87141afced':
        raise ValueError('global state schema differs')
    return plan


def verify_inputs():
    streams = json.loads((PRIOR / 'native/runs/external_global_streams.json').read_text())['arms']
    manifest = json.loads((PRIOR / 'analysis/input_manifest.json').read_text())['arms']
    result = {}
    for arm in ARMS:
        records = streams[arm]
        expected = {f'state_{stage}_rank{rank}.bin' for stage in ('entry','pre_update','post_process','kdm62d_return','wrapper_return') for rank in range(8)}
        if len(records) != 40 or {Path(r['path']).name for r in records} != expected:
            raise ValueError(f'{arm}: global stream inventory differs')
        call_records = [r for r in manifest[arm] if Path(r['path']).name.startswith('state_calls_rank')]
        if len(call_records) != 8 or {Path(r['path']).name for r in call_records} != {f'state_calls_rank{i}.txt' for i in range(8)}:
            raise ValueError(f'{arm}: call inventory differs')
        case = json.loads((PRIOR / f'native/runs/{arm}_case_receipt.json').read_text())
        expected_input = case['source_hashes']['wrfinput_d01']
        launch = json.loads((PRIOR / f'native/runs/{arm}_launch_receipt.json').read_text())
        if launch['status'] != 'PASS' or not launch['inputs_unchanged'] or launch['inputs_after']['wrfinput_d01'] != expected_input:
            raise ValueError(f'{arm}: launch/source input binding differs')
        root = Path(records[0]['path']).parent
        input_path = root / 'wrfinput_d01'
        all_records = [{'path':str(input_path), 'sha256':expected_input, 'bytes':input_path.stat().st_size}]
        all_records += [{'path':x['path'], 'sha256':x['sha256'], 'bytes':x['bytes']} for x in records]
        all_records += [{'path':x['path'], 'sha256':x['sha256'], 'bytes':x['size_bytes']} for x in call_records]
        if any(Path(r['path']).parent != root for r in all_records):
            raise ValueError(f'{arm}: mixed runtime roots')
        for record in all_records:
            path = Path(record['path'])
            if path.is_symlink() or not path.is_file() or path.stat().st_size != record['bytes'] or sha(path) != record['sha256']:
                raise ValueError(f'input differs: {path}')
        result[arm] = {'root':str(root), 'files':all_records}
    return result


def read_initial(path):
    fields = {}
    with Dataset(path) as dataset:
        for name in ('QNRAIN', 'QVAPOR', 'QCLOUD', 'T'):
            var = dataset.variables[name]
            if var.dimensions != ('Time', 'bottom_top', 'south_north', 'west_east') or var.shape != (1, SHAPE[2], SHAPE[0], SHAPE[1]):
                raise ValueError(f'input {name}: dimensions differ')
            raw = var[0]
            if np.ma.isMaskedArray(raw) and np.ma.getmaskarray(raw).any():
                raise ValueError(f'input {name}: masked cells')
            value = np.asarray(raw, dtype=np.float32).transpose(1, 0, 2).copy().reshape(-1)
            if not np.isfinite(value).all():
                raise ValueError(f'input {name}: nonfinite')
            fields[name] = value
    return fields


def differing(a, b, valid):
    if a.shape != b.shape or a.shape != valid.shape or not np.isfinite(a[valid]).all() or not np.isfinite(b[valid]).all():
        raise ValueError('invalid comparison arrays')
    return valid & (a != b)


def cross_counts(a, b, valid):
    a, b = a & valid, b & valid
    return {'neither':int(np.count_nonzero(valid & ~a & ~b)), 'input_only':int(np.count_nonzero(a & ~b)),
            'entry_only':int(np.count_nonzero(~a & b)), 'both':int(np.count_nonzero(a & b))}


def write_sparse(path, a, b, mask):
    ix = np.flatnonzero(mask).astype(np.int32)
    np.savez_compressed(path, index_jki_zero_based=ix, B1=np.asarray(a[ix], dtype=np.float32), DM065=np.asarray(b[ix], dtype=np.float32))
    if path.stat().st_size >= 90 * 1024 * 1024:
        raise ValueError(f'sparse output exceeds part limit: {path}')
    return len(ix)


def read_anchors():
    with (PRIOR / 'cohorts/results/selected_points.csv').open(newline='') as stream:
        selected = {int(r['flat_index_yx']):r for r in csv.DictReader(stream)}
    wanted = (20330, 16454, 20183, 17051)
    if any(x not in selected for x in wanted):
        raise ValueError('missing anchor point')
    with (PRIOR / 'cohorts/results/point_corners.csv').open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    result = []
    for flat in wanted:
        point = selected[flat]
        corners = [r for r in rows if r['point_id'] == point['point_id']]
        if len(corners) != 4 or {r['corner'] for r in corners} != {'00','01','10','11'}:
            raise ValueError('anchor corners incomplete')
        for r in corners:
            weight = float(r['weight'])
            if not np.isfinite(weight) or weight <= 0:
                raise ValueError('invalid corner weight')
            result.append((flat, point, r))
    return result


def compare_global(inputs, initial, global_states, masks, owners, output):
    size = int(np.prod(SHAPE))
    valid = masks['B1', 1]
    if valid.shape != (size,) or not valid.any():
        raise ValueError('invalid global coverage')
    for arm in ARMS:
        for stage in (1, 5):
            if not np.array_equal(masks[arm, stage], valid) or not np.array_equal(owners[arm, stage], owners['B1', 1]):
                raise ValueError('entry/return ownership differs between arms')
    for name in ('QVAPOR', 'QCLOUD', 'T'):
        if not np.array_equal(initial['B1'][name], initial['DM065'][name]):
            raise ValueError(f'initial non-NR state differs: {name}')
    input_a, input_b = (initial[arm]['QNRAIN'] for arm in ARMS)
    input_diff = differing(input_a, input_b, np.ones(size, dtype=bool))
    summary = {'shape_yxz': list(SHAPE), 'linear_index_order':'j,k,i, zero based',
               'domain_cells':size, 'called_cells':int(valid.sum()), 'uncalled_cells':int((~valid).sum()),
               'input_nr_changed_all':int(input_diff.sum()), 'input_nr_changed_called':int(np.count_nonzero(input_diff & valid)),
               'input_nr_changed_uncalled':int(np.count_nonzero(input_diff & ~valid)), 'comparisons':{}}
    sparse = output / 'sparse'
    sparse.mkdir()
    write_sparse(sparse/'initial_NR.npz', input_a, input_b, input_diff)
    for stage, label in ((1,'entry'), (5,'return')):
        for field in COMPARE:
            fi = FIELDS.index(field)
            a, b = (global_states[arm, stage][fi] for arm in ARMS)
            mask = differing(a, b, valid)
            count = write_sparse(sparse/f'{label}_{field}.npz', a, b, mask)
            summary['comparisons'][f'{label}_{field}'] = {'changed':count, 'input_NR_cross':cross_counts(input_diff, mask, valid)}
    owner = owners['B1', 1].reshape(SHAPE[0], SHAPE[2], SHAPE[1]).transpose(0,2,1)
    called = valid.reshape(SHAPE[0], SHAPE[2], SHAPE[1]).transpose(0,2,1)
    input_3d = input_diff.reshape(SHAPE[0], SHAPE[2], SHAPE[1]).transpose(0,2,1)
    entry_diff = differing(global_states['B1', 1][10], global_states['DM065', 1][10], valid).reshape(SHAPE[0], SHAPE[2], SHAPE[1]).transpose(0,2,1)
    np.savez_compressed(output/'domain_and_support.npz', called=called, owner_token=owner,
                        initial_NR_changed=input_3d, entry_NR_changed=entry_diff,
                        initial_NR_changed_levels=input_3d.sum(axis=2).astype(np.uint8),
                        entry_NR_changed_levels=entry_diff.sum(axis=2).astype(np.uint8))
    return summary


def anchor_rows(initial, global_states, valid, owners):
    import struct
    rows = []
    for flat, point, corner in read_anchors():
        i, j = int(corner['wrf_i_1based']), int(corner['wrf_j_1based'])
        if not (1 <= i <= SHAPE[1] and 1 <= j <= SHAPE[0]):
            raise ValueError('corner outside grid')
        for k in range(1, SHAPE[2] + 1):
            ix = ((j-1)*SHAPE[2]+(k-1))*SHAPE[1]+(i-1)
            token = int(owners[ix])
            row = {'flat_index_yx':flat, 'point_id':point['point_id'], 'group':point['group'],
                   'corner':corner['corner'], 'i_1based':i, 'j_1based':j, 'k_1based':k,
                   'weight':corner['weight'], 'called':bool(valid[ix]),
                   'owner_rank':token >> 32 if token >= 0 else '', 'owner_call_id':token & 0xffffffff if token >= 0 else ''}
            for arm in ARMS:
                value = np.float32(initial[arm]['QNRAIN'][ix])
                row[f'{arm}_input_NR'] = float(value)
                row[f'{arm}_input_NR_f32_le_hex'] = struct.pack('<f',value).hex()
                for stage, name in ((1,'entry'),(5,'return')):
                    for field in COMPARE:
                        if valid[ix]:
                            value = np.float32(global_states[arm, stage][FIELDS.index(field), ix])
                            row[f'{arm}_{name}_{field}'] = float(value)
                            row[f'{arm}_{name}_{field}_f32_le_hex'] = struct.pack('<f',value).hex()
                        else:
                            row[f'{arm}_{name}_{field}'] = ''
                            row[f'{arm}_{name}_{field}_f32_le_hex'] = ''
            rows.append(row)
    return rows


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    verify_plan(BUNDLE/'plan.json')
    if os.path.lexists(args.output):
        raise FileExistsError('output exists')
    inputs = verify_inputs()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.first-call-', dir=args.output.parent))
    work = Path(tempfile.mkdtemp(prefix='.first-call-work-', dir=args.output.parent))
    try:
        initial = {arm:read_initial(Path(inputs[arm]['root'])/'wrfinput_d01') for arm in ARMS}
        schema, specs = state.load_schema(ROOT/'docs/evidence/cp02_state_path_20261104/native/state_schema.json')
        if tuple(specs[1].fields) != tuple(specs[5].fields) or len(specs[1].fields) != len(FIELDS):
            raise ValueError('global schema differs')
        calls = {arm:state.read_call_inventory(Path(inputs[arm]['root'])) for arm in ARMS}
        state._calls_equal(calls['B1'], calls['DM065'])
        global_states, masks, owners, coverage = {}, {}, {}, {}
        for arm in ARMS:
            for sid in (1, 5):
                v, mask, owner, stats = state.read_global_stage(Path(inputs[arm]['root']), specs[sid], calls[arm], [], SHAPE, work/arm)
                global_states[arm, sid], masks[arm, sid], owners[arm, sid] = v, mask, owner
                coverage[f'{arm}_{sid}'] = stats
        summary = compare_global(inputs, initial, global_states, masks, owners, stage)
        rows = anchor_rows(initial, global_states, masks['B1', 1], owners['B1', 1])
        with (stage/'anchors.csv').open('x', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
            writer.writeheader();writer.writerows(rows)
        verify_plan(BUNDLE/'plan.json')
        if verify_inputs() != inputs:
            raise ValueError('inputs changed during analysis')
        files = {str(p.relative_to(stage)):{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(stage.rglob('*')) if p.is_file()}
        receipt = {'status':'PASS', 'plan_sha256':PLAN_SHA, 'analyzer_sha256':sha(Path(__file__)), 'inputs':inputs,
                   'summary':summary, 'coverage':coverage, 'anchor_rows':len(rows), 'outputs':files,
                   'interpretation':'Numerical inequality uses float32 values and treats signed zeros equally. Uncalled cells are missing. Wrapper first call is not a transport attribution; pressure and Exner are unavailable in this global 14-field stream.'}
        (stage/'receipt.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
        if os.path.lexists(args.output):
            raise FileExistsError('output appeared during analysis')
        os.rename(stage,args.output)
        print(json.dumps({'status':'PASS','receipt_sha256':sha(args.output/'receipt.json'),'summary':summary},sort_keys=True))
    finally:
        shutil.rmtree(work,ignore_errors=True)
        if stage.exists():shutil.rmtree(stage)


if __name__ == '__main__':
    main()
