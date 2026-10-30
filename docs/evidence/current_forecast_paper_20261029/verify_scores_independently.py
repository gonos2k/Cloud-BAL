#!/usr/bin/env python3
"""Recount paired arrays independently of the forecast scoring implementation."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np

ARMS = ('ORIGINAL', 'CURRENT_OFF', 'CURRENT_HYDRO', 'CURRENT_LIQUID')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def close(actual, expected):
    if expected is None:
        assert actual == '', ('undefined', actual)
    else:
        assert math.isclose(float(actual), expected, rel_tol=2e-12, abs_tol=2e-12), (actual, expected)


def divide(a, b):
    return a / b if b else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scores', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        raise FileExistsError(args.output)
    files = list(args.scores.glob('hour_*_arrays.npz')) + [args.scores / n for n in ('categorical_scores.csv', 'continuous_scores.csv', 'transitions.csv', 'receipt.json')]
    hashes = {str(p): digest(p) for p in files}
    arrays = {}
    expected_keys = set(ARMS) | {'reference', 'latitude', 'longitude', 'flat_index_yx'}
    for hour in range(13, 19):
        with np.load(args.scores / f'hour_{hour}_arrays.npz', allow_pickle=False) as data:
            assert set(data.files) == expected_keys
            arrays[hour-12] = {k: np.array(data[k]) for k in data.files}
            for value in arrays[hour-12].values():
                assert value.shape == (3688,) and np.isfinite(value).all()
            indices = arrays[hour-12]['flat_index_yx']
            assert np.issubdtype(indices.dtype, np.integer)
            assert len(np.unique(indices)) == 3688 and (indices >= 0).all()
            for name in ('latitude', 'longitude', 'flat_index_yx'):
                assert np.array_equal(arrays[hour-12][name], arrays[1][name])
    counts = {}
    for table in ('categorical_scores', 'continuous_scores', 'transitions'):
        with (args.scores / f'{table}.csv').open(newline='') as stream:
            rows = list(csv.DictReader(stream))
        seen = set()
        for row in rows:
            d = arrays[int(row['lead_hour'])]
            obs = d['reference'].tolist()
            if table != 'transitions':
                assert int(row['points']) == len(obs) == 3688
            if table == 'categorical_scores':
                threshold = float(row['threshold_mm']); prediction = d[row['case']].tolist()
                key = (row['lead_hour'], row['case'], threshold)
                h = m = f = c = 0
                for p, o in zip(prediction, obs):
                    if o >= threshold:
                        if p >= threshold: h += 1
                        else: m += 1
                    elif p >= threshold: f += 1
                    else: c += 1
                for name, value in zip(('hit','miss','false_alarm','correct_dry'), (h,m,f,c)):
                    assert int(row[name]) == value
                random_hits = (h+m)*(h+f)/len(obs)
                expected = dict(CSI=divide(h,h+m+f), ETS=divide(h-random_hits,h+m+f-random_hits),
                                POD=divide(h,h+m), FAR=divide(f,h+f), frequency_bias=divide(h+f,h+m))
                for name, value in expected.items(): close(row[name], value)
            elif table == 'continuous_scores':
                key = (row['lead_hour'], row['case'])
                prediction = d[row['case']].tolist(); error = [p-o for p,o in zip(prediction,obs)]
                expected = dict(mean_forecast_mm=math.fsum(prediction)/len(obs), mean_reference_mm=math.fsum(obs)/len(obs),
                                mean_error_mm=math.fsum(error)/len(obs), MAE_mm=math.fsum(map(abs,error))/len(obs),
                                RMSE_mm=math.sqrt(math.fsum(e*e for e in error)/len(obs)))
                for name, value in expected.items(): close(row[name], value)
            else:
                threshold = float(row['threshold_mm']); key = (row['lead_hour'],row['baseline'],row['candidate'],threshold)
                old = d[row['baseline']].tolist(); new = d[row['candidate']].tolist()
                gains = losses = false_gains = false_losses = 0
                for a,b,o in zip(old,new,obs):
                    if o >= threshold:
                        gains += a < threshold <= b; losses += b < threshold <= a
                    else:
                        false_gains += a < threshold <= b; false_losses += b < threshold <= a
                for name,value in zip(('hit_gains','hit_losses','false_alarm_gains','false_alarm_losses'),(gains,losses,false_gains,false_losses)):
                    assert int(row[name]) == value
            assert key not in seen
            seen.add(key)
        thresholds = (0.1,0.5,1.0,2.5,5.0,10.0)
        if table == 'categorical_scores':
            expected_keys = {(str(h),a,t) for h in range(1,7) for a in ARMS for t in thresholds}
        elif table == 'continuous_scores':
            expected_keys = {(str(h),a) for h in range(1,7) for a in ARMS}
        else:
            pairs = [('ORIGINAL',a) for a in ARMS[1:]] + [('CURRENT_OFF',a) for a in ARMS[2:]]
            expected_keys = {(str(h),b,a,t) for h in range(1,7) for b,a in pairs for t in thresholds}
        assert seen == expected_keys, table
        counts[table] = len(rows)
    assert counts == {'categorical_scores':144,'continuous_scores':24,'transitions':180}, counts
    assert hashes == {str(p):digest(p) for p in files}
    result = {'status':'PASS','scope':'Independent scalar recount and fsum from fresh paired arrays; not independent observation or model execution.',
              'rows':counts, 'points_per_hour':3688,'input_sha256':hashes,'script_sha256':digest(Path(__file__))}
    with args.output.open('x') as stream:
        json.dump(result,stream,indent=2,allow_nan=False);stream.write('\n')
    print(counts)


if __name__ == '__main__':
    main()
