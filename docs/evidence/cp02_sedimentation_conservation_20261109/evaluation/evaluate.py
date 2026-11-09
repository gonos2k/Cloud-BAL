#!/usr/bin/env python3
"""Evaluate frozen six-hour sedimentation experiment; or recount saved arrays."""
import argparse
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import shutil
import tempfile

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

BUNDLE = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[4]
RUNTIME = ROOT.parent / 'runtime'
HISTORICAL = Path('/var/tmp/six-hour-improved-runtime-20261030/IMPROVED_BG_FIXED')
CANDIDATE = 'CONSERVATIVE_SEDIMENTATION'
CURRENT = 'IMPROVED_BG_FIXED'
CASES = ('ORIGINAL', CURRENT, CANDIDATE)
THRESHOLDS = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0)
FONT = Path('/usr/share/fonts/truetype/nanum/NanumGothic.ttf')
PINNED = {'tools/cp02_weak_strong_balance.py':'2572d41d352c70d72d8488fe9f0dc9d961de8b10c21f7ade459f131e7c4fbdb5',
          'tools/cp02_rain_number_evaluation.py':'426fad4aa6fccf71c35bafb7a9b006fa59fb4b3ea05bd5baec49d41cf6a546cf'}


def identity(path):
    path = Path(path)
    with path.open('rb') as stream: digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'path': str(path.resolve()), 'sha256': digest, 'size_bytes': path.stat().st_size}


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module; spec.loader.exec_module(module)
    return module


def pinned_modules():
    for path, digest in PINNED.items():
        if identity(ROOT / path)['sha256'] != digest: raise ValueError(f'pinned scorer changed: {path}')
    balance = load_module('frozen_balance', ROOT/'tools/cp02_weak_strong_balance.py')
    score = load_module('frozen_rain_number_scores', ROOT/'tools/cp02_rain_number_evaluation.py')
    score.CANDIDATE = CANDIDATE; score.CASES = CASES
    return balance, score


def transitions(arrays):
    rows = []
    for hour in range(13, 19):
        v = arrays[hour]; obs = v['reference']; candidate = v[CANDIDATE]
        for baseline in ('ORIGINAL', CURRENT):
            old = v[baseline]
            for name, subset, threshold in (('weak_observed', (obs >= .1) & (obs < 1), .1),
                                            ('dry_observed', obs < .1, .1),
                                            ('strong_observed', obs >= 5, 5),
                                            ('below_strong_observed', obs < 5, 5)):
                before = old >= threshold; after = candidate >= threshold
                rows.append({'lead_hour':hour-12, 'baseline':baseline, 'observation_subset':name,
                             'forecast_threshold_mm':threshold, 'n_observed_subset':int(subset.sum()),
                             'forecast_both_below':int((subset & ~before & ~after).sum()),
                             'forecast_gained':int((subset & ~before & after).sum()),
                             'forecast_lost':int((subset & before & ~after).sum()),
                             'forecast_both_at_or_above':int((subset & before & after).sum())})
    return rows


def csv_write(path, rows):
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n'); w.writeheader(); w.writerows(rows)


def read_arrays(folder):
    arrays = {}
    receipt = json.loads((folder/'receipt.json').read_text())
    if receipt.get('status') != 'COMPLETE': raise ValueError('saved input receipt is incomplete')
    for h in range(13,19):
        path = folder/f'hour_{h}_arrays.npz'
        if receipt['outputs'].get(path.name) != identity(path)['sha256']:
            raise ValueError(f'saved array identity differs: {path}')
        with np.load(path, allow_pickle=False) as archive:
            arrays[h] = {k: archive[k].copy() for k in archive.files}
    return arrays


def products(arrays, output, score):
    categorical, continuous, constraints = score.compare_scores(arrays)
    transition = transitions(arrays)
    output.mkdir(parents=True, exist_ok=True)
    for name, rows in (('categorical_scores.csv',categorical), ('continuous_scores.csv',continuous),
                       ('admission_constraints.csv',constraints), ('observation_transitions.csv',transition)):
        csv_write(output/name,rows)
    passed = sum(r['satisfied'] for r in constraints)
    verdict = {'candidate':CANDIDATE,'qualified':passed == 26,'passed_constraints':passed,
               'required_constraints':26,'selection':'all 26; no averaging across leads or thresholds',
               'protection_reference':CURRENT,'recovery_reference':'ORIGINAL',
               'adoption':'requires separate decision; current B1 retained'}
    (output/'verdict.json').write_text(json.dumps(verdict,indent=2)+'\n')
    return categorical, continuous, constraints, transition, verdict


def figures(categorical, directory):
    if identity(FONT)['sha256'] != '48a28e97b34fc8e5b157657633670cd1b7de126cfc414da65ce9c3d5bc8be733':
        raise ValueError('pinned font differs')
    font_manager.fontManager.addfont(str(FONT)); plt.rcParams['font.family'] = font_manager.FontProperties(fname=str(FONT)).get_name()
    directory.mkdir(parents=True,exist_ok=True)
    names = {'ORIGINAL':'규준실험 (ORIGINAL)', CURRENT:'현행 B1', CANDIDATE:'보존 침강 후보'}
    colors = {'ORIGINAL':'#555555',CURRENT:'#2166ac',CANDIDATE:'#d14932'}
    styles = {'ORIGINAL':('--','s'),CURRENT:(':','^'),CANDIDATE:('-','o')}
    for threshold in THRESHOLDS:
        fig, ax = plt.subplots(figsize=(7.4,4.3))
        all_csi = []
        for case in CASES:
            rows = [r for r in categorical if r['threshold_mm']==threshold and r['case']==case]
            y = [r['CSI'] for r in rows]; all_csi.extend(y); linestyle, marker = styles[case]
            ax.plot([r['lead_hour'] for r in rows],y,marker=marker,linestyle=linestyle,label=names[case],color=colors[case])
        margin = max((max(all_csi)-min(all_csi))*0.12, .015)
        limits = (max(0, min(all_csi)-margin), min(1, max(all_csi)+margin))
        ax.set(xlabel='Forecast lead (hours)',ylabel='CSI (axis varies by threshold)',title=f'CSI at ≥ {threshold:g} mm per hour',xticks=range(1,7),ylim=limits)
        ax.grid(alpha=.25); ax.legend(frameon=False); fig.tight_layout()
        fig.savefig(directory/f'candidate_csi_{threshold:g}mm.png',dpi=170); plt.close(fig)


def summary(output, categorical, continuous, constraints, transition, verdict):
    lines=['# Controlled sedimentation forecast scoring','',
           f"Candidate satisfies {verdict['passed_constraints']}/26 fixed conditions. Current B1 remains the adopted baseline pending a separate decision.",
           'Each value is scored independently at its lead and threshold over the same 3,688 RN1 points; there is no averaging across leads or thresholds.',
           'Recount using `python docs/evidence/cp02_sedimentation_conservation_20261109/evaluation/evaluate.py --recount PATH_TO_THIS_RESULT --output NEW_SCRATCH_DIRECTORY`. This requires the SHA-pinned repository scorers, NumPy, Matplotlib, netCDF4 and pinned font; it does not read forecast histories.',
           'Weak-observed transitions use 0.1 ≤ observed < 1 mm and forecast threshold 0.1 mm; dry-observed transitions use observed < 0.1 mm. Strong transitions use the 5 mm threshold and split observed ≥ 5 versus < 5 mm.',
           '', '## Categorical scores', '', '| Lead | Threshold mm | Case | Hit | Miss | False alarm | CSI |', '|---:|---:|---|---:|---:|---:|---:|']
    lines += [f"| {r['lead_hour']} | {r['threshold_mm']:g} | {r['case']} | {r['hit']} | {r['miss']} | {r['false_alarm']} | {r['CSI']:.6f} |" for r in categorical]
    lines += ['', '## Continuous scores', '', '| Lead | Case | MAE mm | RMSE mm |','|---:|---|---:|---:|']
    lines += [f"| {r['lead_hour']} | {r['case']} | {r['MAE_mm']:.6f} | {r['RMSE_mm']:.6f} |" for r in continuous]
    lines += ['', '## Fixed constraints', '', '| Goal | Lead | Threshold mm | Baseline | Candidate CSI | Baseline CSI | Pass |','|---|---:|---:|---|---:|---:|---|']
    lines += [f"| {r['goal']} | {r['lead_hour']} | {r['threshold_mm']:g} | {r['baseline']} | {r['candidate_CSI']:.6f} | {r['baseline_CSI']:.6f} | {r['satisfied']} |" for r in constraints]
    lines += ['', '## Point transitions', '', '| Lead | Baseline | Observation subset | Threshold | N | Both below | Gained | Lost | Both above |','|---:|---|---|---:|---:|---:|---:|---:|---:|']
    lines += [f"| {r['lead_hour']} | {r['baseline']} | {r['observation_subset']} | {r['forecast_threshold_mm']:g} | {r['n_observed_subset']} | {r['forecast_both_below']} | {r['forecast_gained']} | {r['forecast_lost']} | {r['forecast_both_at_or_above']} |" for r in transition]
    (output/'FULL_SCORES.md').write_text('\n'.join(lines)+'\n')


def verify_runs():
    plan_path = BUNDLE/'forecast/launch_plan.json'; plan = json.loads(plan_path.read_text()); plan_id = identity(plan_path)
    evaluation = plan['evaluation']
    if (plan['status'] != 'FROZEN_CONTROLLED_SIX_HOUR_PLAN' or evaluation['candidate'] != CANDIDATE
            or evaluation['leads_hours'] != list(range(1,7)) or evaluation['thresholds_mm'] != list(THRESHOLDS)
            or evaluation['protection_conditions'] != 11 or evaluation['recovery_conditions'] != 15
            or evaluation['protection_reference'] != CURRENT or evaluation['recovery_reference'] != 'ORIGINAL'):
        raise ValueError('frozen plan mismatch')
    if plan['source_sha256']['docs/evidence/cp02_sedimentation_conservation_20261109/native/source/module_mp_kdm6_FIX.f90'] != 'ad255ae8b505af6b4ceebd177a54948d8bfff7fcd2c9f6d45c90122be0b57786':
        raise ValueError('candidate source hash mismatch')
    inputs = [plan_id]
    for case in ('CONTROL','CONSERVATIVE'):
        dpath = RUNTIME/f'{case}_driver_exit.json'; rpath = RUNTIME/'forecasts'/case/'run_receipt.json'
        driver = json.loads(dpath.read_text()); run = json.loads(rpath.read_text())
        if (driver['status'] != 'PASS' or driver['case'] != case or driver['plan_sha256'] != plan_id['sha256'] or
            driver['source_inputs_unchanged'] is not True or len(driver['commands']) != 2 or
            any(row['exit_code'] != 0 for row in driver['commands']) or
            run['status'] != 'PASS' or run['case'] != case or run['exit_code'] != 0 or len(run['histories']) != 7):
            raise ValueError(f'{case}: runtime gate failed')
        expected_names = {f'wrfout_d01_2026-08-16_{h:02d}:00:00' for h in range(12,19)}
        if {Path(row['path']).name for row in run['histories']} != expected_names:
            raise ValueError('runtime history inventory differs')
        for row in run['histories']:
            actual = identity(row['path'])
            if any(actual[k] != row[k] for k in ('sha256','size_bytes')): raise ValueError('history identity changed')
            inputs.append(actual)
        inputs.extend((identity(dpath),identity(rpath)))
    return plan, inputs


def verify_proof(path, plan_id):
    proof = json.loads(path.read_text())
    if (proof.get('status') != 'PASS' or proof.get('schema') != 'cp02_sedimentation_forecast_comparability_v1'
            or proof.get('plan') != plan_id):
        raise ValueError('comparability proof or plan identity differs')
    for case in ('CONTROL', 'CONSERVATIVE'):
        entry = proof['cases'][case]
        for key, actual in (('prepared', RUNTIME/'forecasts'/case/'prepared.json'),
                            ('run', RUNTIME/'forecasts'/case/'run_receipt.json'),
                            ('driver', RUNTIME/f'{case}_driver_exit.json')):
            if entry[key] != identity(actual): raise ValueError(f'{case}: proof {key} identity differs')
        if (not entry['all_89_source_hashes_match_base'] or not entry['non_executable_staged_inputs_match_base']
                or not entry['input_after_matches_staged'] or entry['rank_success_count'] != 8
                or entry['finite_history_count'] != 7):
            raise ValueError(f'{case}: proof input/history gate failed')
    rows = proof['control_history_comparison']
    expected = {f'wrfout_d01_2026-08-16_{h:02d}:00:00' for h in range(12,19)}
    if len(rows) != 7 or {r['filename'] for r in rows} != expected:
        raise ValueError('CONTROL proof does not cover all seven histories')
    def check(row, case, label):
        name = row['filename']
        old = identity(HISTORICAL/name); new = identity(RUNTIME/'forecasts'/case/name)
        if (row['byte_equal'] is not True or row['historical'] != old or row['observed'] != new
                or row['historical_sha256'] != old['sha256'] or row[label] != new['sha256']
                or old['size_bytes'] != new['size_bytes'] or old['sha256'] != new['sha256']):
            raise ValueError(f'{case}/{name}: proof history identity differs')
    for row in rows: check(row, 'CONTROL', 'control_sha256')
    initial = proof['candidate_initial_history']
    if initial['filename'] != 'wrfout_d01_2026-08-16_12:00:00': raise ValueError('wrong candidate initial history')
    check(initial, 'CONSERVATIVE', 'conservative_sha256')
    return identity(path)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recount', type=Path, help='portable saved array directory; no forecast needed')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--control-proof', type=Path, help='independent seven-history CONTROL identity proof')
    args=parser.parse_args()
    balance, score = pinned_modules()
    if args.output.exists(): raise FileExistsError(args.output)
    if args.recount:
        arrays = read_arrays(args.recount); inputs = [identity(args.recount/'receipt.json')] + [identity(args.recount/f'hour_{h}_arrays.npz') for h in range(13,19)]
        mapping = None; histories=[]; resets={}
    else:
        if args.control_proof is None: raise ValueError('CONTROL identity proof required')
        plan, inputs = verify_runs()
        inputs.append(verify_proof(args.control_proof, inputs[0]))
        _, base, prior = balance.load_prior_arrays()
        balance.CASE_IDS = (CANDIDATE,); balance.CONTEXT_IDS = ('ORIGINAL', CURRENT)
        arrays, _, histories, mapping, resets = balance.build_candidate_arrays({CANDIDATE:RUNTIME/'forecasts/CONSERVATIVE'},base)
        inputs.extend(prior); inputs.extend(histories)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".score-stage-", dir=args.output.parent))
    try:
        for hour, values in arrays.items(): np.savez_compressed(stage/f'hour_{hour}_arrays.npz',**values)
        if mapping is not None: np.savez_compressed(stage/'bilinear_mapping.npz',**mapping)
        categorical, continuous, constraints, transition, verdict = products(arrays,stage,score)
        figures(categorical,stage/'figures'); summary(stage,categorical,continuous,constraints,transition,verdict)
        for item in inputs:
            if identity(item['path']) != item: raise ValueError(f"input changed: {item['path']}")
        receipt = {'status':'COMPLETE','mode':'recount' if args.recount else 'forecast', 'inputs':inputs,
                   'scorer':identity(Path(__file__)), 'pinned_helpers':{k:identity(ROOT/k) for k in PINNED},
                   'font':identity(FONT),'numpy':np.__version__,'matplotlib':matplotlib.__version__,
                   'reset_report':resets,'rows':{'categorical':len(categorical),'continuous':len(continuous),
                                              'constraints':len(constraints),'transitions':len(transition)},
                   'outputs':{str(p.relative_to(stage)):identity(p)['sha256'] for p in sorted(stage.rglob('*')) if p.is_file()}}
        (stage/'receipt.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
        print(json.dumps(verdict))
        stage.rename(args.output)
    finally:
        if stage.exists(): shutil.rmtree(stage)


if __name__ == '__main__': main()
