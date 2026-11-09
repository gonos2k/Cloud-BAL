#!/usr/bin/env python3
"""Score the frozen RN1 cohort; --recount needs only a sealed array directory."""
import argparse
import csv
import ctypes
import errno
from fractions import Fraction
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
BALANCE = ROOT / 'tools/cp02_weak_strong_balance.py'
BALANCE_SHA = '2572d41d352c70d72d8488fe9f0dc9d961de8b10c21f7ade459f131e7c4fbdb5'
ORIGINAL, B1, CONS, NEW = 'ORIGINAL', 'IMPROVED_BG_FIXED', 'CONSERVATIVE_SEDIMENTATION', 'FIRST_ICE_VELOCITY'
CASES = (ORIGINAL, B1, CONS, NEW)
HOURS = range(13, 19)
THRESHOLDS = (.1, .5, 1., 2.5, 5., 10.)


def identity(path):
    path = Path(path)
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'path': str(path.resolve()), 'sha256': digest, 'size_bytes': path.stat().st_size}


def read_arrays(folder):
    receipt = json.loads((folder / 'receipt.json').read_text())
    if receipt.get('status') != 'COMPLETE':
        raise ValueError('incomplete array receipt')
    arrays = {}
    for hour in HOURS:
        path = folder / f'hour_{hour}_arrays.npz'
        expected = receipt['outputs'][path.name]
        if isinstance(expected, dict): expected = expected['sha256']
        if identity(path)['sha256'] != expected: raise ValueError(f'array hash mismatch: {path}')
        with np.load(path, allow_pickle=False) as data:
            arrays[hour] = {k: data[k].copy() for k in data.files}
    return arrays


def score(arrays):
    if set(arrays) != set(HOURS): raise ValueError('six hours required')
    categorical, continuous, transitions = [], [], []
    coords = None
    for hour in HOURS:
        v = arrays[hour]
        fields = (*CASES, 'reference', 'latitude', 'longitude', 'flat_index_yx')
        if any(np.asarray(v[k]).shape != (3688,) or not np.isfinite(v[k]).all() for k in fields):
            raise ValueError('all 3688 points must be finite')
        if any(np.any(v[k] < 0) for k in (*CASES, 'reference')): raise ValueError('negative precipitation')
        current = tuple(v[k] for k in ('flat_index_yx', 'latitude', 'longitude'))
        if len(np.unique(current[0])) != 3688: raise ValueError('duplicate point identity')
        if coords is not None and any(not np.array_equal(a,b) for a,b in zip(coords,current)):
            raise ValueError('cohort changed across hours')
        coords = current
        obs = v['reference']
        for case in CASES:
            prediction = v[case]; err = prediction - obs
            continuous.append(dict(lead_hour=hour-12, case=case, MAE_mm=float(np.abs(err).mean()), RMSE_mm=float(np.sqrt(np.square(err).mean()))))
            for threshold in THRESHOLDS:
                o, p = obs >= threshold, prediction >= threshold
                h, m, f = (int(np.count_nonzero(mask)) for mask in (o & p, o & ~p, ~o & p))
                if not h+m+f: raise ValueError('undefined CSI')
                categorical.append(dict(lead_hour=hour-12, threshold_mm=threshold, case=case, points=3688, hit=h, miss=m, false_alarm=f, CSI=h/(h+m+f)))
        for base in (B1, CONS):
            for subset_name, subset, threshold in (('weak_observed', (obs >= .1) & (obs < 1), .1), ('dry_observed', obs < .1, .1), ('strong_observed', obs >= 5, 5.), ('below_strong_observed', obs < 5, 5.)):
                before, after = v[base] >= threshold, v[NEW] >= threshold
                transitions.append(dict(lead_hour=hour-12, baseline=base, observation_subset=subset_name, forecast_threshold_mm=threshold, n_observed_subset=int(subset.sum()), forecast_both_below=int((subset & ~before & ~after).sum()), forecast_gained=int((subset & ~before & after).sum()), forecast_lost=int((subset & before & ~after).sum()), forecast_both_at_or_above=int((subset & before & after).sum())))
    keyed = {(r['lead_hour'], r['threshold_mm'], r['case']):r for r in categorical}
    constraints = []
    for lead in range(1, 7):
        for threshold in THRESHOLDS:
            protect = lead == 1 or threshold == 5
            recover = lead >= 2 and threshold in (.1, .5, 1.)
            if not (protect or recover): continue
            base = B1 if protect else ORIGINAL
            for candidate in (NEW, CONS):
                a, b = keyed[lead,threshold,candidate], keyed[lead,threshold,base]
                exact = lambda x: Fraction(x['hit'], x['hit'] + x['miss'] + x['false_alarm'])
                constraints.append(dict(candidate=candidate, goal='preserve_current_B1' if protect else 'recover_low_threshold_vs_ORIGINAL', lead_hour=lead, threshold_mm=threshold, baseline=base, candidate_CSI=a['CSI'], baseline_CSI=b['CSI'], satisfied=exact(a)>=exact(b)))
    assert len(categorical)==144 and len(continuous)==24 and len(constraints)==52 and len(transitions)==48
    return categorical, continuous, constraints, transitions


def write_csv(path, rows):
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n'); writer.writeheader(); writer.writerows(rows)


def verify_forecasts(runtime, previous, proof):
    payload = json.loads(proof.read_text())
    if payload.get('status') != 'PASS' or payload.get('schema') != 'cp02_first_ice_velocity_comparability_v1': raise ValueError('independent comparability proof must PASS')
    rows = payload.get('control_history_comparison', [])
    if len(rows) != 7: raise ValueError('proof must cover seven control histories')
    expected_names = {f'wrfout_d01_2026-08-16_{h:02d}:00:00' for h in range(12, 19)}
    if {Path(r['observed']['path']).name for r in rows} != expected_names: raise ValueError('proof history inventory mismatch')
    for row in rows:
        name = Path(row['observed']['path']).name
        if row.get('byte_equal') is not True or row['historical'] != identity(previous/name) or row['observed'] != identity(runtime/'CONTROL'/name): raise ValueError('control proof identity mismatch')
    initial = payload['candidate_initial_history']
    name = 'wrfout_d01_2026-08-16_12:00:00'
    if initial.get('byte_equal') is not True or initial['historical'] != identity(previous/name) or initial['observed'] != identity(runtime/'ICE_FIXED'/name): raise ValueError('initial proof identity mismatch')
    records = [identity(proof)]
    for case in ('CONTROL', 'ICE_FIXED'):
        receipt = runtime / case / 'run_receipt.json'; data = json.loads(receipt.read_text())
        if data.get('status') != 'PASS' or data.get('exit_code') != 0 or len(data.get('histories', [])) != 7:
            raise ValueError(f'{case}: incomplete runtime receipt')
        expected = {f'wrfout_d01_2026-08-16_{h:02d}:00:00' for h in range(12,19)}
        if {Path(r['path']).name for r in data['histories']} != expected: raise ValueError('history inventory mismatch')
        records.append(identity(receipt))
        for row in data['histories']:
            p = runtime / case / Path(row['path']).name; actual = identity(p)
            if any(actual[k] != row[k] for k in ('sha256','size_bytes')): raise ValueError(f'history changed: {p}')
            records.append(actual)
    for hour in range(12,19):
        name = f'wrfout_d01_2026-08-16_{hour:02d}:00:00'
        old, control = identity(previous/name), identity(runtime/'CONTROL'/name)
        if (old['sha256'], old['size_bytes']) != (control['sha256'], control['size_bytes']): raise ValueError(f'CONTROL differs: {name}')
        records.append(old)
    first = identity(runtime/'ICE_FIXED'/'wrfout_d01_2026-08-16_12:00:00')
    old = identity(previous/'wrfout_d01_2026-08-16_12:00:00')
    if (first['sha256'], first['size_bytes']) != (old['sha256'], old['size_bytes']): raise ValueError('initial histories differ')
    return records


def forecast_arrays(prior, runtime):
    if identity(BALANCE)['sha256'] != BALANCE_SHA: raise ValueError('mapping source hash differs')
    spec = importlib.util.spec_from_file_location('frozen_balance', BALANCE); balance = importlib.util.module_from_spec(spec); sys.modules[spec.name] = balance; spec.loader.exec_module(balance)
    if identity(prior/'receipt.json')['sha256'] != '3b97420c8c82f285c4793a2004131cc7832d2cb1f003f19785b63f2c6688963b': raise ValueError('frozen prior receipt differs')
    base = read_arrays(prior)
    balance.CASE_IDS = (NEW,); balance.CONTEXT_IDS = (ORIGINAL, B1, CONS)
    result = balance.build_candidate_arrays({NEW:runtime/'ICE_FIXED'}, base)
    mapping_path = prior/'bilinear_mapping.npz'
    receipt = json.loads((prior/'receipt.json').read_text())
    if identity(mapping_path)['sha256'] != receipt['outputs']['bilinear_mapping.npz']: raise ValueError('frozen mapping identity differs')
    with np.load(mapping_path, allow_pickle=False) as saved:
        if set(saved.files) != set(result[3]) or any(not np.array_equal(saved[k], result[3][k], equal_nan=True) for k in saved.files): raise ValueError('remapping differs from frozen mapping')
    return result


def full_scores(path, categorical, continuous):
    lines = ['# Four-case hourly precipitation scores', '',
             'All 3,688 paired RN1 points; each lead and threshold is scored independently.', '',
             '| Lead | Threshold mm | Case | Hit | Miss | False alarm | CSI |',
             '|---:|---:|---|---:|---:|---:|---:|']
    lines += [f"| {r['lead_hour']} | {r['threshold_mm']:g} | {r['case']} | {r['hit']} | {r['miss']} | {r['false_alarm']} | {r['CSI']:.6f} |" for r in categorical]
    lines += ['', '| Lead | Case | MAE mm | RMSE mm |', '|---:|---|---:|---:|']
    lines += [f"| {r['lead_hour']} | {r['case']} | {r['MAE_mm']:.6f} | {r['RMSE_mm']:.6f} |" for r in continuous]
    path.write_text('\n'.join(lines)+'\n')


def publish_new(stage, destination):
    """Atomically publish without replacing a concurrently created destination."""
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = libc.renameat2
    renameat2.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
    renameat2.restype = ctypes.c_int
    if renameat2(-100, os.fsencode(stage), -100, os.fsencode(destination), 1) != 0:
        number = ctypes.get_errno()
        if number == errno.EEXIST: raise FileExistsError(destination)
        if number != errno.EINVAL: raise OSError(number, os.strerror(number), str(destination))
        # Some shared filesystems reject RENAME_NOREPLACE. Reserve exclusively;
        # publish the completion receipt last and roll back only our directory.
        destination.mkdir()
        try:
            paths = sorted(stage.iterdir(), key=lambda p: p.name in ('receipt.json', 'maps_metadata.json'))
            for source in paths:
                if not source.is_file(): raise ValueError('only flat staged files can be published')
                before = identity(source)
                with source.open('rb') as src, (destination/source.name).open('xb') as dst:
                    shutil.copyfileobj(src, dst)
                copied = identity(destination/source.name)
                if identity(source) != before or (copied['sha256'],copied['size_bytes']) != (before['sha256'],before['size_bytes']): raise ValueError('publication copy differs')
        except BaseException:
            shutil.rmtree(destination)
            raise



def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--recount',type=Path); p.add_argument('--prior-arrays',type=Path)
    p.add_argument('--runtime',type=Path); p.add_argument('--previous-histories',type=Path); p.add_argument('--proof',type=Path)
    p.add_argument('--output',type=Path,required=True); args=p.parse_args()
    if os.path.lexists(args.output): raise FileExistsError(args.output)
    if args.recount:
        arrays=read_arrays(args.recount); inputs=[identity(args.recount/'receipt.json')]+[identity(args.recount/f'hour_{h}_arrays.npz') for h in HOURS]; mapping=None; resets={}
    else:
        if any(x is None for x in (args.prior_arrays,args.runtime,args.previous_histories,args.proof)): p.error('forecast mode requires --prior-arrays, --runtime, --previous-histories and --proof')
        inputs=verify_forecasts(args.runtime,args.previous_histories,args.proof)
        inputs += [identity(args.prior_arrays/'receipt.json')]+[identity(args.prior_arrays/f'hour_{h}_arrays.npz') for h in HOURS]
        arrays, _, histories, mapping, resets=forecast_arrays(args.prior_arrays,args.runtime); inputs += histories + [identity(BALANCE), identity(args.prior_arrays/'bilinear_mapping.npz')]
    categorical, continuous, constraints, transitions=score(arrays)
    verdict={case:{'passed_constraints':sum(r['satisfied'] for r in constraints if r['candidate']==case),'required_constraints':26} for case in (NEW,CONS)}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.score-stage-',dir=args.output.parent))
    try:
        for h,v in arrays.items(): np.savez_compressed(stage/f'hour_{h}_arrays.npz',**v)
        if mapping is not None: np.savez_compressed(stage/'bilinear_mapping.npz',**mapping)
        for name,rows in (('categorical_scores.csv',categorical),('continuous_scores.csv',continuous),('admission_constraints.csv',constraints),('observation_transitions.csv',transitions)): write_csv(stage/name,rows)
        (stage/'verdict.json').write_text(json.dumps(verdict,indent=2)+'\n')
        full_scores(stage/'FULL_SCORES.md',categorical,continuous)
        for record in inputs:
            if identity(record['path']) != record: raise ValueError(f"input changed: {record['path']}")
        receipt={'status':'COMPLETE','mode':'recount' if args.recount else 'forecast','inputs':inputs,'scorer':identity(__file__),'numpy':np.__version__,'reset_report':resets,'rows':{'categorical':144,'continuous':24,'constraints_per_candidate':26,'transitions':48},'outputs':{x.name:identity(x)['sha256'] for x in sorted(stage.iterdir())}}
        (stage/'receipt.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
        if os.path.lexists(args.output): raise FileExistsError(args.output)
        publish_new(stage,args.output)
        print(json.dumps(verdict))
    finally:
        if stage.exists(): shutil.rmtree(stage)

if __name__=='__main__': main()
