#!/usr/bin/env python3
"""Independently recount frozen forecast scores and admission constraints."""
import csv
import hashlib
from fractions import Fraction
import json
from pathlib import Path
import sys
import numpy as np

folder = Path(sys.argv[1])
receipt = json.loads((folder/'receipt.json').read_text())
def sha(path):
    with path.open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()
assert receipt['status'] == 'COMPLETE'
for name in ('categorical_scores.csv','continuous_scores.csv','admission_constraints.csv','verdict.json', *(f'hour_{h}_arrays.npz' for h in range(13,19))):
    assert sha(folder/name) == receipt['outputs'][name]
receipt_sha = sha(folder/'receipt.json')
cases = ('ORIGINAL', 'IMPROVED_BG_FIXED', 'CONSERVATIVE_SEDIMENTATION', 'FIRST_ICE_VELOCITY')
thresholds = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0)
with (folder / 'categorical_scores.csv').open(newline='') as stream:
    categorical = {(int(r['lead_hour']), float(r['threshold_mm']), r['case']): r for r in csv.DictReader(stream)}
with (folder / 'continuous_scores.csv').open(newline='') as stream:
    continuous = {(int(r['lead_hour']), r['case']): r for r in csv.DictReader(stream)}
with (folder / 'observation_transitions.csv').open(newline='') as stream:
    transitions = {(int(r['lead_hour']), r['baseline'], r['observation_subset']): r for r in csv.DictReader(stream)}
with (folder / 'admission_constraints.csv').open(newline='') as stream:
    constraints = {(int(r['lead_hour']), float(r['threshold_mm']), r['candidate']): r for r in csv.DictReader(stream)}
assert (len(categorical), len(continuous), len(constraints), len(transitions)) == (144, 24, 52, 48)
passed = {case: 0 for case in cases[2:]}
for lead in range(1, 7):
    with np.load(folder / f'hour_{lead+12}_arrays.npz', allow_pickle=False) as data:
        obs = data['reference']
        assert obs.shape == (3688,) and np.isfinite(obs).all()
        ratios = {}
        for case in cases:
            pred = data[case]
            assert pred.shape == obs.shape and np.isfinite(pred).all()
            error = pred - obs
            row = continuous[lead, case]
            assert np.isclose(float(row['MAE_mm']), np.mean(abs(error)), rtol=1e-13, atol=1e-13)
            assert np.isclose(float(row['RMSE_mm']), np.sqrt(np.mean(error**2)), rtol=1e-13, atol=1e-13)
            for threshold in thresholds:
                o, p = obs >= threshold, pred >= threshold
                hit = int(np.sum(o & p)); miss = int(np.sum(o & ~p)); false = int(np.sum(~o & p))
                row = categorical[lead, threshold, case]
                assert tuple(int(row[k]) for k in ('hit','miss','false_alarm','points')) == (hit,miss,false,3688)
                ratios[threshold,case] = Fraction(hit,hit+miss+false)
                assert np.isclose(float(row['CSI']), float(ratios[threshold,case]),rtol=1e-14,atol=0)
        candidate = data[cases[3]]
        for baseline in cases[1:3]:
            for label, subset, threshold in (('weak_observed', (obs >= .1) & (obs < 1), .1),
                ('dry_observed', obs < .1, .1), ('strong_observed', obs >= 5, 5.),
                ('below_strong_observed', obs < 5, 5.)):
                before, after = data[baseline] >= threshold, candidate >= threshold
                counts = (int(np.sum(subset)), int(np.sum(subset & ~before & ~after)),
                          int(np.sum(subset & ~before & after)), int(np.sum(subset & before & ~after)),
                          int(np.sum(subset & before & after)))
                row = transitions[lead,baseline,label]
                keys = ('n_observed_subset','forecast_both_below','forecast_gained','forecast_lost','forecast_both_at_or_above')
                assert tuple(int(row[key]) for key in keys) == counts
                assert float(row['forecast_threshold_mm']) == threshold
        for threshold in thresholds:
            protect = lead == 1 or threshold == 5.0
            recover = lead >= 2 and threshold in (0.1,0.5,1.0)
            if not (protect or recover): continue
            baseline = cases[1] if protect else cases[0]
            for case in cases[2:]:
                ok = ratios[threshold,case] >= ratios[threshold,baseline]
                row = constraints[lead,threshold,case]
                assert row['baseline'] == baseline and (row['satisfied'] == 'True') == ok
                passed[case] += ok
verdict = json.loads((folder/'verdict.json').read_text())
assert all(verdict[case]['passed_constraints'] == count and verdict[case]['required_constraints'] == 26 for case,count in passed.items())
assert sha(folder/'receipt.json') == receipt_sha
assert all(sha(folder/name) == expected for name,expected in receipt['outputs'].items())
print(json.dumps({'receipt_sha256':receipt_sha,'status':'PASS','categorical_rows':144,'continuous_rows':24,'transition_rows':48,'constraints_per_candidate':26,'passed_constraints':passed}, indent=2))
