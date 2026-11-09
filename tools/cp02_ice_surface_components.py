#!/usr/bin/env python3
"""Extract and replay stored hourly RAINC and RAINNC on the frozen RN1 cohort."""
import argparse
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

import netCDF4
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'docs/evidence/cp02_first_ice_velocity_20261109/evaluation/results'
EVAL = ROOT / 'docs/evidence/precip_hourly_20261027/rn1_recovery/archived_compare_six_hour_csi.py'
EVAL_SHA = '1cfa4965155ec273e8e1ca9f963bd79a5ece3bc47beb4ae3db4e8b8f5e21b2c0'
REFERENCE = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/Cloud-BAL/scratch/cp02_six_hour_20260914/reference')
ANALYSIS = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/ANAL/NE57/DAOU/DFSD/20260816/klps_lc05_anal_20260816_1300')
WORK = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch')
CASES = {'ORIGINAL': WORK/'current_forecast_paper_20261029/run.PomEr8/original',
         'IMPROVED_BG_FIXED': Path('/var/tmp/six-hour-improved-runtime-20261030/IMPROVED_BG_FIXED'),
         'CONSERVATIVE_SEDIMENTATION': WORK/'b1_sedimentation_conservation_20261109/runtime/forecasts/CONSERVATIVE',
         'FIRST_ICE_VELOCITY': WORK/'b1_ice_velocity_20261109/runtime/forecasts/ICE_FIXED'}
NAMES = ('RAINC', 'RAINNC')
B1, CONS, NEW = list(CASES)[1:]


def identity(path):
    p = Path(path)
    with p.open('rb') as f: digest = hashlib.file_digest(f, 'sha256').hexdigest()
    return {'path': str(p.resolve()), 'sha256': digest, 'size_bytes': p.stat().st_size}


def module(path):
    spec = importlib.util.spec_from_file_location('surface_evaluator', path)
    obj = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = obj
    spec.loader.exec_module(obj)
    return obj


def interpolate(corners, u, v):
    """Interpolate in the pinned evaluator's 00,10,01,11 operation order."""
    return ((1-u)*(1-v)*corners[..., 0] + u*(1-v)*corners[..., 1]
            + (1-u)*v*corners[..., 2] + u*v*corners[..., 3])


def replay(corners, u, v, tolerance):
    """Remap cumulative fields, then difference; do not clamp each corner increment."""
    corners = np.asarray(corners, dtype=np.float64)
    if corners.ndim != 4 or corners.shape[1:3] != (7, 2) or corners.shape[-1] != 4:
        raise ValueError('corners must have shape (points, 7, 2, 4)')
    if not np.isfinite(corners).all() or np.any(corners < -tolerance):
        raise ValueError('invalid cumulative corner precipitation')
    if np.any(np.diff(corners, axis=1) < -tolerance):
        raise ValueError('cumulative component reset')
    u, v = np.asarray(u), np.asarray(v)
    if u.shape != (len(corners),) or v.shape != u.shape or not np.isfinite(u).all() or not np.isfinite(v).all() or np.any((u < 0) | (u > 1) | (v < 0) | (v > 1)):
        raise ValueError('invalid bilinear weights')
    u, v = u[:, None, None], v[:, None, None]
    positive = np.maximum(corners, 0.)
    component_cum = interpolate(positive, u, v)
    component_diff = np.diff(component_cum, axis=1)
    if np.any(component_diff < -tolerance): raise ValueError('negative component hourly difference')
    component = np.maximum(component_diff, 0.)
    # Addition at the native corners must precede remapping to reproduce PR154.
    total_cum = interpolate(positive.sum(axis=2), u[:, :, 0], v[:, :, 0])
    total_diff = np.diff(total_cum, axis=1)
    if np.any(total_diff < -tolerance): raise ValueError('negative total hourly difference')
    return component, np.maximum(total_diff, 0.)


def read_base():
    receipt_path = BASE/'receipt.json'
    receipt = json.loads(receipt_path.read_text())
    if receipt.get('status') != 'COMPLETE' or identity(receipt_path)['sha256'] != '09bd7015a9f84f3a79cd90a0dc00b2600f10f32589b26e336554e54e7dc24b16': raise ValueError('PR154 receipt identity mismatch')
    arrays = []
    for h in range(13,19):
        p = BASE/f'hour_{h}_arrays.npz'
        if identity(p)['sha256'] != receipt['outputs'][p.name]: raise ValueError('PR154 array hash mismatch')
        with np.load(p, allow_pickle=False) as z: arrays.append({k:z[k].copy() for k in z.files})
    return arrays


def group_masks(arrays):
    h6, h1 = arrays[-1], arrays[0]
    eligible = (h6['reference'] < 5) & (h6[B1] < 5)
    before, after = h6[CONS] >= 5, h6[NEW] >= 5
    groups = {'h6_persistent': eligible & before & after,
              'h6_new': eligible & ~before & after,
              'h6_resolved': eligible & before & ~after,
              'h1_new_fa': (h1['reference'] < 10) & (h1[B1] < 10) & (h1[NEW] >= 10)}
    if [int(x.sum()) for x in groups.values()] != [65,26,37,3]: raise ValueError('fixed cohort counts differ')
    return groups


def native_extract(arrays):
    if identity(EVAL)['sha256'] != EVAL_SHA: raise ValueError('pinned evaluator changed')
    evaluator = module(EVAL)
    inventory, mask, lat, lon, provenance = evaluator.load_reference(REFERENCE, ANALYSIS)
    keys = arrays[0]['flat_index_yx']
    if not np.array_equal(np.flatnonzero(mask), keys) or not np.array_equal(lat[mask], arrays[0]['latitude']) or not np.array_equal(lon[mask], arrays[0]['longitude']): raise ValueError('RN1 mapping cohort mismatch')
    map_path = BASE/'bilinear_mapping.npz'
    receipt = json.loads((BASE/'receipt.json').read_text())
    if identity(map_path)['sha256'] != receipt['outputs'][map_path.name]: raise ValueError('frozen mapping hash mismatch')
    with np.load(map_path, allow_pickle=False) as z: mapping = {k:z[k].copy() for k in z.files}
    x0,x1 = inventory['grid']['crop_x_inclusive']; y0,y1 = inventory['grid']['crop_y_inclusive']
    ys,xs = slice(y0-2,y1),slice(x0-2,x1)
    j,i = mapping['j0'][mask],mapping['i0'][mask]
    u,v = mapping['u'][mask],mapping['v'][mask]
    prior = ROOT/'docs/evidence/snow_sensitivity_20261030/analysis/receipt.json'
    prior_record = identity(prior)
    if prior_record['sha256'] != '18e2d82c3be0120b2da0e34fec75c12d6da52ddbfc28eaffb19781e94153e7ec': raise ValueError('historical receipt identity mismatch')
    expected = {r['path']:r['sha256'] for r in json.loads(prior.read_text())['sources']}
    expected.update({r['path']:r['sha256'] for r in receipt['inputs']})
    output, records, checks, grid = {}, [prior_record], {}, None
    for case,directory in CASES.items():
        snapshots, case_meta, selected = {}, [], []
        for hour in range(12,19):
            path = directory/f'wrfout_d01_2026-08-16_{hour:02d}:00:00'
            before = identity(path)
            if expected.get(before['path']) != before['sha256']: raise ValueError(f'history not bound to historical receipt: {path}')
            snapshot = evaluator.read_wrf_snapshot(path, datetime(2026,8,16,12,tzinfo=timezone.utc)+timedelta(hours=hour-12), inventory)
            with netCDF4.Dataset(path) as d:
                counters = {}
                for name in ('I_RAINC','I_RAINNC','I_RAINSH'):
                    if name in d.variables:
                        a = np.ma.asarray(d.variables[name][:])
                        if np.ma.is_masked(a) or not np.isfinite(a).all() or np.any(a != 0): raise ValueError(f'{case}: nonzero or invalid bucket counter {name}')
                        counters[name] = 'present and zero'
                    else: counters[name] = 'absent'
            if identity(path) != before: raise ValueError(f'history changed while reading: {path}')
            records.append(before); case_meta.append({'hour_utc':hour,'bucket_mm':snapshot['bucket_mm'],'prec_acc_dt':snapshot['prec_acc_dt'],'counters':counters})
            if grid is None:
                grid = snapshot['lat'],snapshot['lon']
                calculated = evaluator.build_curvilinear_mapping(grid[0][ys,xs],grid[1][ys,xs],lat,lon,mask)
                if set(calculated) != set(mapping) or any(not np.array_equal(mapping[k],calculated[k],equal_nan=True) for k in mapping): raise ValueError('frozen mapping differs from native coordinates')
            elif not np.array_equal(snapshot['lat'],grid[0]) or not np.array_equal(snapshot['lon'],grid[1]): raise ValueError('native coordinate grid changed')
            snapshots[hour] = snapshot
            evaluator.raw_total(snapshot)
            cols = []
            for name in NAMES:
                field,valid = snapshot['components'][name]; field,valid = field[ys,xs],valid[ys,xs]
                if not (valid[j,i] & valid[j,i+1] & valid[j+1,i] & valid[j+1,i+1]).all(): raise ValueError('missing native corner')
                cols.append(np.stack((field[j,i],field[j,i+1],field[j+1,i],field[j+1,i+1]),axis=-1))
            selected.append(np.stack(cols,axis=1))
        evaluator.CASES = (case,)
        reset = evaluator.check_resets({case:snapshots})
        output[case] = np.stack(selected,axis=1)
        checks[case] = {'history_metadata':case_meta,'full_grid_reset':reset[case]}
    return output,u,v,records,checks,provenance,float(mapping['residual_max_deg'])


def make_outputs(arrays, corners, u, v, tolerance):
    groups = group_masks(arrays); rows = []; summaries = []; worst = 0.
    for case in CASES:
        component,total = replay(corners[case],u,v,tolerance)
        for h,a in enumerate(arrays):
            expected = a[case]
            if not np.array_equal(total[:,h],expected): raise ValueError(f'{case}/{h+1}: native total does not reproduce PR154')
            rounding = component[:,h].sum(axis=1)-total[:,h]
            worst = max(worst,float(np.max(np.abs(rounding))))
            for n,key in enumerate(a['flat_index_yx']):
                rows.append([h+1,case,int(key),float(component[n,h,0]),float(component[n,h,1]),float(total[n,h]),float(rounding[n])])
            for group,mask in groups.items():
                summaries.append({'cohort':group,'lead_hour':h+1,'case':case,'count':int(mask.sum()),'mean_rainc_mm':float(component[mask,h,0].mean()),'mean_rainnc_mm':float(component[mask,h,1].mean()),'mean_total_mm':float(total[mask,h].mean())})
    if worst > 1e-10: raise ValueError(f'component sum rounding exceeds 1e-10 mm: {worst}')
    return rows,summaries,worst


def main():
    p=argparse.ArgumentParser(); p.add_argument('--output',type=Path,required=True); p.add_argument('--replay',type=Path); args=p.parse_args()
    if os.path.lexists(args.output): raise FileExistsError(args.output)
    arrays=read_base(); source_records=[identity(Path(__file__)), identity(EVAL), identity(BASE/'receipt.json'), identity(BASE/'bilinear_mapping.npz')] + [identity(BASE/f'hour_{h}_arrays.npz') for h in range(13,19)]
    if args.replay:
        with np.load(args.replay,allow_pickle=False) as z:
            corners={case:z[case].copy() for case in CASES}; u=z['u'].copy(); v=z['v'].copy(); keys=z['flat_index_yx'].copy()
        if not np.array_equal(keys,arrays[0]['flat_index_yx']): raise ValueError('replay point keys differ')
        source_records.append(identity(args.replay)); checks={}; provenance={}; residual=None
    else:
        corners,u,v,records,checks,provenance,residual=native_extract(arrays); source_records += records
    rows,summary,worst=make_outputs(arrays,corners,u,v,1e-6)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.surface-',dir=args.output.parent))
    try:
        np.savez_compressed(stage/'native_corners.npz',**corners,u=u,v=v,flat_index_yx=arrays[0]['flat_index_yx'])
        with (stage/'hourly_points.csv').open('w',newline='') as f:
            w=csv.writer(f);w.writerow(['lead_hour','case','flat_index_yx','rainc_mm','rainnc_mm','pr154_total_mm','component_sum_minus_pr154_mm']);w.writerows(rows)
        with (stage/'group_means.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(summary[0]));w.writeheader();w.writerows(summary)
        for record in source_records:
            if identity(record['path']) != record: raise ValueError('input changed during extraction')
        receipt={'status':'COMPLETE','mode':'replay' if args.replay else 'native','inputs':source_records,'checks':checks,'reference_provenance':{k:str(v) for k,v in provenance.items()},'mapping_residual_max_deg':residual,'rows':len(rows),'max_component_sum_rounding_mm':worst,'interpretation':'Stored hourly RAINC and RAINNC components, not process attribution; hourly output cannot resolve subhour timing.','outputs':{x.name:identity(x)['sha256'] for x in stage.iterdir()}}
        (stage/'receipt.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
        # Same protected atomic no-replace publication used by PR154.
        ev=module(ROOT/'docs/evidence/cp02_first_ice_velocity_20261109/evaluation/evaluate.py'); ev.publish_new(stage,args.output)
    finally:
        if stage.exists(): shutil.rmtree(stage)
    print(json.dumps({'rows':len(rows),'max_component_sum_rounding_mm':worst}))

if __name__ == '__main__': main()
