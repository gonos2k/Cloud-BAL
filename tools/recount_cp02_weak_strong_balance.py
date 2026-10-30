#!/usr/bin/env python3
"""Independently recount frozen weak/strong scores and replay their artifacts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import shutil
import tempfile
from pathlib import Path
from fractions import Fraction

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SCORER_PATH = ROOT / 'tools/cp02_weak_strong_balance.py'
SCORER_SHA256 = '2572d41d352c70d72d8488fe9f0dc9d961de8b10c21f7ade459f131e7c4fbdb5'


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def identity(path: Path):
    path = Path(path)
    return {'path': str(path), 'sha256': sha256(path), 'size_bytes': path.stat().st_size}


def load_scorer():
    if SCORER_SHA256 and sha256(SCORER_PATH) != SCORER_SHA256:
        raise ValueError('pinned weak/strong scorer changed before independent recount')
    spec = importlib.util.spec_from_file_location('weak_strong_replay_scorer', SCORER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ratio(numerator: int, denominator: int):
    return numerator / denominator if denominator else None


def independent_scores(forecast: np.ndarray, reference: np.ndarray, threshold: float):
    predicted = np.asarray(forecast, dtype=np.float64) >= threshold
    observed = np.asarray(reference, dtype=np.float64) >= threshold
    hit = int(np.count_nonzero(predicted & observed))
    miss = int(np.count_nonzero(~predicted & observed))
    false_alarm = int(np.count_nonzero(predicted & ~observed))
    correct_dry = int(np.count_nonzero(~predicted & ~observed))
    total = hit + miss + false_alarm + correct_dry
    random_hits = (hit + miss) * (hit + false_alarm) / total if total else 0.0
    ets_denominator = hit + miss + false_alarm - random_hits
    return {'hit': hit, 'miss': miss, 'false_alarm': false_alarm, 'correct_dry': correct_dry,
            'CSI': ratio(hit, hit + miss + false_alarm),
            'ETS': ratio(hit - random_hits, ets_denominator),
            'POD': ratio(hit, hit + miss), 'FAR': ratio(false_alarm, hit + false_alarm),
            'frequency_bias': ratio(hit + false_alarm, hit + miss)}


def float_value(value):
    return None if value == '' else float(value)


def assert_metric(actual, expected, label):
    if expected is None:
        if actual not in (None, ''):
            raise ValueError(f'{label}: expected undefined metric, got {actual!r}')
        return
    if float_value(actual) != expected:
        raise ValueError(f'{label}: {actual!r} differs from independent result {expected!r}')


def read_csv(path):
    with Path(path).open(encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream))


def recount(analysis_dir: Path):
    analysis_dir = Path(analysis_dir)
    receipt_path = analysis_dir / 'receipt.json'
    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    if receipt.get('status') != 'COMPLETE':
        raise ValueError('analysis receipt is not complete')
    for name, record in receipt.get('analysis_outputs', {}).items():
        path = analysis_dir / name
        if path.stat().st_size != record.get('size_bytes') or sha256(path) != record.get('sha256'):
            raise ValueError(f'analysis output does not match receipt: {name}')
    cases = receipt['cases']
    hours = receipt['hours_utc']
    thresholds = receipt['thresholds_mm']
    expected_case_order = ['ORIGINAL', 'CONTROL_SNOW_300', 'IMPROVED_BG_FIXED', 'IMPROVED_SNOW_080',
                           'GATE_G50_90', 'EQ_G50_90', 'GATE_G75_95', 'EQ_G75_95',
                           'GATE_G90_99', 'EQ_G90_99', 'FIXED_ORIGINAL_100', 'ORIGINAL_B1_100']
    if (cases != expected_case_order or receipt.get('eligible_cases') != expected_case_order[4:]
        or receipt.get('context_only_cases') != expected_case_order[1:4]
        or hours != list(range(13, 19)) or len(cases) != 12 or len(hours) != 6
        or receipt['points_per_hour'] != 3688):
        raise ValueError('analysis output scope differs from the frozen contract')
    arrays, difference_arrays, transition_arrays = {}, {}, {}
    first_keys = None
    for hour in hours:
        path = analysis_dir / f'hour_{hour}_arrays.npz'
        with np.load(path, allow_pickle=False) as archive:
            values = {key: np.asarray(archive[key]) for key in archive.files}
        expected_keys = set(cases) | {'reference', 'latitude', 'longitude', 'flat_index_yx'}
        if set(values) != expected_keys:
            raise ValueError(f'{hour}: array archive keys differ from the receipt')
        for name, value in values.items():
            if value.shape != (3688,):
                raise ValueError(f'{hour}/{name}: expected 3688 paired values')
            if name == 'flat_index_yx':
                if len(np.unique(value)) != 3688:
                    raise ValueError(f'{hour}: paired point keys are not unique')
            elif not np.isfinite(value).all():
                raise ValueError(f'{hour}/{name}: array contains nonfinite data')
        if first_keys is None:
            first_keys = values['flat_index_yx'].copy()
        elif not np.array_equal(first_keys, values['flat_index_yx']):
            raise ValueError(f'{hour}: paired point keys vary by lead')
        arrays[hour] = values
        with np.load(analysis_dir / f'hour_{hour}_difference_vs_original.npz', allow_pickle=False) as archive:
            difference_arrays[hour] = {key: np.asarray(archive[key]) for key in archive.files}
        with np.load(analysis_dir / f'hour_{hour}_transitions_vs_original.npz', allow_pickle=False) as archive:
            transition_arrays[hour] = {key: np.asarray(archive[key]) for key in archive.files}
        expected_transition_keys = {
            f'{case}__t{threshold:g}__{kind}'
            for case in cases if case != 'ORIGINAL' for threshold in receipt['thresholds_mm']
            for kind in ('hit_gained', 'hit_lost', 'new_false_alarm', 'false_alarm_removed')}
        if set(transition_arrays[hour]) != expected_transition_keys:
            raise ValueError(f'{hour}: transition mask archive keys differ from expected scope')
        expected_difference_keys = set(cases) | {'reference', 'latitude', 'longitude', 'flat_index_yx'}
        if set(difference_arrays[hour]) != expected_difference_keys:
            raise ValueError(f'{hour}: difference archive keys differ from expected scope')
    category_rows = read_csv(analysis_dir / 'categorical_scores.csv')
    continuous_rows = read_csv(analysis_dir / 'continuous_scores.csv')
    transition_rows = read_csv(analysis_dir / 'transitions_vs_original.csv')
    band_transition_rows = read_csv(analysis_dir / 'observation_band_transitions.csv')
    bin_count_rows = read_csv(analysis_dir / 'observed_forecast_bin_counts.csv')
    admission_rows = read_csv(analysis_dir / 'admission_constraints.csv')
    gate_comparison_rows = read_csv(analysis_dir / 'gate_equal_mass_comparison.csv')
    factorial_rows = read_csv(analysis_dir / 'factorial_difference_in_differences.csv')
    csi_change_rows = read_csv(analysis_dir / 'csi_change_exact_counts.csv')
    category_index = {(row['case'], int(row['lead_hour']), float(row['threshold_mm'])): row
                      for row in category_rows}
    continuous_index = {(row['case'], int(row['lead_hour'])): row for row in continuous_rows}
    if len(category_index) != len(cases) * 6 * 6 or len(continuous_index) != len(cases) * 6:
        raise ValueError('score CSVs do not form the complete context/lead/threshold grid')
    transition_index = {(row['case'], int(row['lead_hour']), float(row['threshold_mm'])): row
                        for row in transition_rows}
    if len(transition_index) != (len(cases) - 1) * 6 * 6:
        raise ValueError('transition CSV does not form the complete non-baseline grid')
    bands = (('dry', 0.0, 0.1), ('light', 0.1, 1.0), ('moderate', 1.0, 5.0),
             ('strong', 5.0, 10.0), ('very_strong', 10.0, None))
    band_index = {(row['case'], int(row['lead_hour']), float(row['threshold_mm']), row['observed_bin']): row
                  for row in band_transition_rows}
    bin_index = {(row['case'], int(row['lead_hour']), row['observed_bin'],
                  row['forecast_case'], row['forecast_bin']): row for row in bin_count_rows}
    if len(band_index) != (len(cases) - 1) * 6 * 6 * len(bands):
        raise ValueError('observation-band transition table has incomplete coverage')
    if len(bin_index) != (len(cases) - 1) * 6 * len(bands) * 2 * len(bands):
        raise ValueError('observed/forecast bin table has incomplete coverage')
    counts = {'categorical': 0, 'continuous': 0, 'transitions': 0, 'admission': 0,
              'observation_band_transitions': 0, 'observed_forecast_bins': 0}
    for hour in hours:
        lead = hour - 12
        values = arrays[hour]
        observed = values['reference'].astype(np.float64)
        baseline = values['ORIGINAL'].astype(np.float64)
        differences = difference_arrays[hour]
        for name in ('reference', 'latitude', 'longitude', 'flat_index_yx'):
            if not np.array_equal(differences[name], values[name]):
                raise ValueError(f'{hour}/{name}: difference archive coordinates differ from paired arrays')
        for case in cases:
            expected_difference = values[case].astype(np.float64) - baseline
            if not np.array_equal(differences[case], expected_difference):
                raise ValueError(f'{hour}/{case}: pointwise difference archive mismatch')
        for case in cases:
            forecast = values[case].astype(np.float64)
            error = forecast - observed
            row = continuous_index[(case, lead)]
            expected_cont = {
                'valid_obs': 3688,
                'mean_forecast_mm': float(np.mean(forecast)),
                'mean_reference_mm': float(np.mean(observed)),
                'MAE_mm': float(np.mean(np.abs(error))),
                'RMSE_mm': float(np.sqrt(np.mean(error ** 2))),
            }
            for field, expected in expected_cont.items():
                if field == 'valid_obs':
                    if int(row[field]) != expected:
                        raise ValueError(f'{case}/{lead}/{field}: valid count mismatch')
                else:
                    assert_metric(row[field], expected, f'{case}/{lead}/{field}')
            counts['continuous'] += 1
            for threshold in thresholds:
                expected = independent_scores(forecast, observed, threshold)
                row = category_index[(case, lead, threshold)]
                for field in ('hit', 'miss', 'false_alarm', 'correct_dry'):
                    if int(row[field]) != expected[field]:
                        raise ValueError(f'{case}/{lead}/{threshold}/{field}: count mismatch')
                for field in ('CSI', 'ETS', 'POD', 'FAR', 'frequency_bias'):
                    assert_metric(row[field], expected[field], f'{case}/{lead}/{threshold}/{field}')
                counts['categorical'] += 1
                if case == 'ORIGINAL':
                    continue
                baseline_event = values['ORIGINAL'].astype(np.float64) >= threshold
                candidate_event = forecast >= threshold
                obs_event = observed >= threshold
                transitions = {
                    'hit_gained': obs_event & ~baseline_event & candidate_event,
                    'hit_lost': obs_event & baseline_event & ~candidate_event,
                    'new_false_alarm': ~obs_event & ~baseline_event & candidate_event,
                    'false_alarm_removed': ~obs_event & baseline_event & ~candidate_event,
                }
                actual = transition_index[(case, lead, threshold)]
                for field, mask in transitions.items():
                    counted = int(np.count_nonzero(mask))
                    if int(actual[field]) != counted:
                        raise ValueError(f'{case}/{lead}/{threshold}/{field}: transition count mismatch')
                    archive_key = f'{case}__t{threshold:g}__{field}'
                    if not np.array_equal(transition_arrays[hour][archive_key], mask.astype(np.uint8)):
                        raise ValueError(f'{case}/{lead}/{threshold}/{field}: per-point transition mask mismatch')
                counts['transitions'] += 1
        for case in cases:
            if case == 'ORIGINAL':
                continue
            forecast = values[case].astype(np.float64)
            for band_name, low, high in bands:
                in_band = observed >= low
                if high is not None:
                    in_band &= observed < high
                for threshold in thresholds:
                    event = observed >= threshold
                    baseline_event = baseline >= threshold
                    candidate_event = forecast >= threshold
                    expected = {
                        'point_count': int(np.count_nonzero(in_band)),
                        'baseline_hits': int(np.count_nonzero(in_band & event & baseline_event)),
                        'candidate_hits': int(np.count_nonzero(in_band & event & candidate_event)),
                        'hit_gained': int(np.count_nonzero(in_band & event & ~baseline_event & candidate_event)),
                        'hit_lost': int(np.count_nonzero(in_band & event & baseline_event & ~candidate_event)),
                        'baseline_direct_event_misses': int(np.count_nonzero(in_band & event & ~baseline_event)),
                        'candidate_direct_event_misses': int(np.count_nonzero(in_band & event & ~candidate_event)),
                        'baseline_predicted_events': int(np.count_nonzero(in_band & baseline_event)),
                        'candidate_predicted_events': int(np.count_nonzero(in_band & candidate_event)),
                        'baseline_false_alarms': int(np.count_nonzero(in_band & ~event & baseline_event)),
                        'candidate_false_alarms': int(np.count_nonzero(in_band & ~event & candidate_event)),
                    }
                    actual = band_index[(case, lead, threshold, band_name)]
                    for field, expected_count in expected.items():
                        if int(actual[field]) != expected_count:
                            raise ValueError(f'{case}/{lead}/{threshold}/{band_name}/{field}: band recount mismatch')
                    counts['observation_band_transitions'] += 1
                for forecast_case, prediction in (('ORIGINAL', baseline), (case, forecast)):
                    for pred_name, pred_low, pred_high in bands:
                        predicted_bin = prediction >= pred_low
                        if pred_high is not None:
                            predicted_bin &= prediction < pred_high
                        expected_count = int(np.count_nonzero(in_band & predicted_bin))
                        actual = bin_index[(case, lead, band_name, forecast_case, pred_name)]
                        if int(actual['point_count']) != expected_count:
                            raise ValueError(f'{case}/{lead}/{band_name}/{forecast_case}/{pred_name}: bin recount mismatch')
                        counts['observed_forecast_bins'] += 1
    base_rows = {(row['case'], int(row['lead_hour']), float(row['threshold_mm'])): row
                 for row in category_rows}
    expected_admission = {}
    new_cases = receipt['eligible_cases']
    for case in new_cases:
        for lead in range(1, 7):
            for threshold in (0.1, 0.5, 1.0):
                candidate = base_rows[(case, lead, threshold)]
                baseline = base_rows[('ORIGINAL', lead, threshold)]
                cd = int(candidate['hit']) + int(candidate['miss']) + int(candidate['false_alarm'])
                bd = int(baseline['hit']) + int(baseline['miss']) + int(baseline['false_alarm'])
                passed = cd > 0 and bd > 0 and int(candidate['hit']) * bd >= int(baseline['hit']) * cd
                expected_admission[(case, 'weak_CSI_at_least_ORIGINAL', lead, threshold)] = {
                    'status': 'PASS' if passed else 'FAIL', 'candidate': candidate, 'baseline': baseline}
        candidate = base_rows[(case, 1, 10.0)]
        baseline = base_rows[('ORIGINAL', 1, 10.0)]
        cd = int(candidate['hit']) + int(candidate['miss']) + int(candidate['false_alarm'])
        bd = int(baseline['hit']) + int(baseline['miss']) + int(baseline['false_alarm'])
        passed = cd > 0 and bd > 0 and int(candidate['hit']) * bd > int(baseline['hit']) * cd
        expected_admission[(case, 'lead1_CSI10_strictly_greater_than_ORIGINAL', 1, 10.0)] = {
            'status': 'PASS' if passed else 'FAIL', 'candidate': candidate, 'baseline': baseline}
    if len(expected_admission) != len(admission_rows):
        raise ValueError('admission table row count mismatch')
    for actual in admission_rows:
        key = (actual['case'], actual['constraint'], int(actual['lead_hour']), float(actual['threshold_mm']))
        expected = expected_admission[key]
        if actual['status'] != expected['status']:
            raise ValueError(f'{key}: admission constraint status differs')
        for prefix, source in (('candidate', expected['candidate']), ('baseline', expected['baseline'])):
            for name in ('hit', 'miss', 'false_alarm'):
                if int(actual[f'{prefix}_{name}']) != int(source[name]):
                    raise ValueError(f'{key}/{prefix}_{name}: admission contingency count differs')
    counts['admission'] = len(admission_rows)
    categorical_metrics = ('CSI', 'FAR', 'POD', 'ETS', 'frequency_bias')
    count_metrics = ('hit', 'miss', 'false_alarm')
    continuous_metrics = ('MAE_mm', 'RMSE_mm', 'mean_forecast_mm', 'mean_reference_mm')
    gate_pairs = (('GATE_G50_90', 'EQ_G50_90'), ('GATE_G75_95', 'EQ_G75_95'),
                  ('GATE_G90_99', 'EQ_G90_99'))
    gate_index = {(row['gate_case'], row['equal_mass_case'], int(row['lead_hour']),
                   None if row['threshold_mm'] == '' else float(row['threshold_mm'])): row
                  for row in gate_comparison_rows}
    if len(gate_index) != len(gate_pairs) * 6 * 7:
        raise ValueError('gate/equal-mass comparison table has incomplete dimensions')

    def verify_difference(actual, left, right, label):
        left_value, right_value = float_value(left), float_value(right)
        expected = None if left_value is None or right_value is None else left_value - right_value
        assert_metric(actual, expected, label)

    for gate, equal in gate_pairs:
        for lead in range(1, 7):
            for threshold in thresholds:
                row = gate_index[(gate, equal, lead, threshold)]
                left, right = category_index[(gate, lead, threshold)], category_index[(equal, lead, threshold)]
                for metric in categorical_metrics:
                    assert_metric(row[f'{metric}_gate'], float_value(left[metric]), f'{gate}/{lead}/{metric}')
                    assert_metric(row[f'{metric}_equal_mass'], float_value(right[metric]), f'{equal}/{lead}/{metric}')
                    verify_difference(row[f'delta_{metric}_gate_minus_equal_mass'], left[metric], right[metric],
                                      f'{gate}/{equal}/{lead}/{threshold}/delta_{metric}')
            row = gate_index[(gate, equal, lead, None)]
            left, right = continuous_index[(gate, lead)], continuous_index[(equal, lead)]
            for metric in continuous_metrics:
                assert_metric(row[f'{metric}_gate'], float_value(left[metric]), f'{gate}/{lead}/{metric}')
                assert_metric(row[f'{metric}_equal_mass'], float_value(right[metric]), f'{equal}/{lead}/{metric}')
                verify_difference(row[f'delta_{metric}_gate_minus_equal_mass'], left[metric], right[metric],
                                  f'{gate}/{equal}/{lead}/delta_{metric}')

    factorial_index = {(int(row['lead_hour']),
                        None if row['threshold_mm'] == '' else float(row['threshold_mm']), row['metric']): row
                       for row in factorial_rows}
    if len(factorial_index) != 6 * (6 * (len(categorical_metrics) + len(count_metrics)) + len(continuous_metrics)):
        raise ValueError('factorial difference-in-differences table has incomplete dimensions')
    csi_change_index = {(row['case'], int(row['lead_hour']), float(row['threshold_mm'])): row
                        for row in csi_change_rows}
    if len(csi_change_index) != (len(cases) - 1) * 6 * 6:
        raise ValueError('exact CSI contingency algebra table has incomplete dimensions')
    factorial_cases = ('ORIGINAL', 'FIXED_ORIGINAL_100', 'ORIGINAL_B1_100', 'IMPROVED_BG_FIXED')
    for lead in range(1, 7):
        for threshold in thresholds:
            for metric in categorical_metrics:
                score_values = {case: float_value(category_index[(case, lead, threshold)][metric])
                                for case in factorial_cases}
                expected = (None if any(value is None for value in score_values.values()) else
                            score_values['IMPROVED_BG_FIXED'] - score_values['ORIGINAL_B1_100']
                            - score_values['FIXED_ORIGINAL_100'] + score_values['ORIGINAL'])
                row = factorial_index[(lead, threshold, metric)]
                for field, case in (('original_old_exe', 'ORIGINAL'),
                                    ('original_fixed_exe', 'FIXED_ORIGINAL_100'),
                                    ('b1_original_exe', 'ORIGINAL_B1_100'),
                                    ('b1_fixed_exe', 'IMPROVED_BG_FIXED')):
                    assert_metric(row[field], score_values[case], f'{lead}/{threshold}/{metric}/{field}')
                assert_metric(row['difference_in_differences'], expected,
                              f'{lead}/{threshold}/{metric}/difference_in_differences')
            for metric in count_metrics:
                count_values = {case: int(category_index[(case, lead, threshold)][metric])
                                for case in factorial_cases}
                expected_count_did = (count_values['IMPROVED_BG_FIXED'] - count_values['ORIGINAL_B1_100']
                                      - count_values['FIXED_ORIGINAL_100'] + count_values['ORIGINAL'])
                row = factorial_index[(lead, threshold, metric)]
                for field, case in (('original_old_exe', 'ORIGINAL'),
                                    ('original_fixed_exe', 'FIXED_ORIGINAL_100'),
                                    ('b1_original_exe', 'ORIGINAL_B1_100'),
                                    ('b1_fixed_exe', 'IMPROVED_BG_FIXED')):
                    if int(row[field]) != count_values[case]:
                        raise ValueError(f'{lead}/{threshold}/{metric}/{field}: count DID input mismatch')
                if int(row['difference_in_differences']) != expected_count_did:
                    raise ValueError(f'{lead}/{threshold}/{metric}: exact count DID mismatch')
            for case in cases:
                if case == 'ORIGINAL':
                    continue
                base = category_index[('ORIGINAL', lead, threshold)]
                candidate = category_index[(case, lead, threshold)]
                observed_base = int(base['hit']) + int(base['miss'])
                observed_candidate = int(candidate['hit']) + int(candidate['miss'])
                if observed_base != observed_candidate:
                    raise ValueError(f'{case}/{lead}/{threshold}: event cohort differs from ORIGINAL')
                h0, f0 = int(base['hit']), int(base['false_alarm'])
                hc, fc = int(candidate['hit']), int(candidate['false_alarm'])
                d0 = h0 + int(base['miss']) + f0
                dc = hc + int(candidate['miss']) + fc
                defined = d0 > 0 and dc > 0
                expected_num = hc * d0 - h0 * dc if defined else None
                expected_factorized_num = ((observed_base + f0) * (hc - h0) - h0 * (fc - f0)
                                           if defined else None)
                expected_den = d0 * dc if defined else None
                if expected_num != expected_factorized_num:
                    raise ValueError(f'{case}/{lead}/{threshold}: independent CSI algebra forms disagree')
                sign = 'UNDEFINED' if not defined else 'POSITIVE' if expected_num > 0 else 'NEGATIVE' if expected_num < 0 else 'ZERO'
                row = csi_change_index[(case, lead, threshold)]
                expected_ints = {
                    'observed_event_count': observed_base,
                    'baseline_hit': h0,
                    'candidate_hit': hc,
                    'hit_delta_candidate_minus_baseline': hc - h0,
                    'baseline_miss': int(base['miss']),
                    'candidate_miss': int(candidate['miss']),
                    'miss_delta_candidate_minus_baseline': int(candidate['miss']) - int(base['miss']),
                    'baseline_false_alarm': f0,
                    'candidate_false_alarm': fc,
                    'false_alarm_delta_candidate_minus_baseline': fc - f0,
                    'baseline_CSI_denominator': d0,
                    'candidate_CSI_denominator': dc,
                }
                for field, expected_value in expected_ints.items():
                    if int(row[field]) != expected_value:
                        raise ValueError(f'{case}/{lead}/{threshold}/{field}: exact CSI count input mismatch')
                for field, expected_value in (('csi_delta_exact_numerator', expected_num),
                                              ('csi_delta_factorized_numerator', expected_factorized_num),
                                              ('csi_delta_exact_denominator', expected_den)):
                    if expected_value is None:
                        if row[field] != '':
                            raise ValueError(f'{case}/{lead}/{threshold}/{field}: undefined ratio must remain blank')
                    elif int(row[field]) != expected_value:
                        raise ValueError(f'{case}/{lead}/{threshold}/{field}: exact CSI algebra mismatch')
                if row['csi_delta_sign'] != sign:
                    raise ValueError(f'{case}/{lead}/{threshold}: exact CSI sign mismatch')
        for metric in continuous_metrics:
            score_values = {case: float_value(continuous_index[(case, lead)][metric])
                            for case in factorial_cases}
            expected = (None if any(value is None for value in score_values.values()) else
                        score_values['IMPROVED_BG_FIXED'] - score_values['ORIGINAL_B1_100']
                        - score_values['FIXED_ORIGINAL_100'] + score_values['ORIGINAL'])
            row = factorial_index[(lead, None, metric)]
            for field, case in (('original_old_exe', 'ORIGINAL'),
                                ('original_fixed_exe', 'FIXED_ORIGINAL_100'),
                                ('b1_original_exe', 'ORIGINAL_B1_100'),
                                ('b1_fixed_exe', 'IMPROVED_BG_FIXED')):
                assert_metric(row[field], score_values[case], f'{lead}/{metric}/{field}')
            assert_metric(row['difference_in_differences'], expected,
                          f'{lead}/{metric}/difference_in_differences')

    admission_index = {(row['case'], row['constraint'], int(row['lead_hour']), float(row['threshold_mm'])): row
                       for row in admission_rows}
    ranked = []
    for case in receipt['eligible_cases']:
        weak_pass = all(admission_index[(case, 'weak_CSI_at_least_ORIGINAL', lead, threshold)]['status'] == 'PASS'
                        for lead in range(1, 7) for threshold in (0.1, 0.5, 1.0))
        strong_pass = admission_index[(case, 'lead1_CSI10_strictly_greater_than_ORIGINAL', 1, 10.0)]['status'] == 'PASS'
        if weak_pass and strong_pass:
            ten = category_index[(case, 1, 10.0)]
            five = category_index[(case, 1, 5.0)]
            ten_den = int(ten['hit']) + int(ten['miss']) + int(ten['false_alarm'])
            five_den = int(five['hit']) + int(five['miss']) + int(five['false_alarm'])
            far_den = int(ten['hit']) + int(ten['false_alarm'])
            ranked.append({'case': case,
                'lead1_CSI_at_10mm': float_value(ten['CSI']),
                'lead1_CSI_at_5mm': float_value(five['CSI']),
                'lead1_FAR_at_10mm': float_value(ten['FAR']),
                'lead1_RMSE_mm': float_value(continuous_index[(case, 1)]['RMSE_mm']),
                '_rank_csi10': Fraction(int(ten['hit']), ten_den),
                '_rank_csi5': Fraction(int(five['hit']), five_den),
                '_rank_far10': Fraction(int(ten['false_alarm']), far_den)})
    ranked.sort(key=lambda row: (row['lead1_CSI_at_10mm'] is None,
        -row['_rank_csi10'], row['lead1_CSI_at_5mm'] is None,
        -row['_rank_csi5'], row['lead1_FAR_at_10mm'] is None,
        row['_rank_far10'],
        row['lead1_RMSE_mm'] is None,
        row['lead1_RMSE_mm'] if row['lead1_RMSE_mm'] is not None else 0.0,
        row['case']))
    winner = json.loads((analysis_dir / 'winner.json').read_text(encoding='utf-8'))
    expected_case = ranked[0]['case'] if ranked else None
    expected_status = 'QUALIFIED_CANDIDATE' if ranked else 'NO_QUALIFIED_CANDIDATE'
    if winner.get('selected_case') != expected_case or winner.get('status') != expected_status:
        raise ValueError('winner.json differs from independent admission/ranking')
    if winner.get('qualified_cases') != [row['case'] for row in ranked]:
        raise ValueError('winner.json qualified case order differs from independent ranking')
    ranking_path = analysis_dir / 'qualified_ranking.csv'
    if ranked:
        if not ranking_path.exists():
            raise ValueError('qualified ranking file is missing')
        actual_ranks = read_csv(ranking_path)
        if len(actual_ranks) != len(ranked):
            raise ValueError('qualified ranking row count mismatch')
        for index, (actual, expected) in enumerate(zip(actual_ranks, ranked), 1):
            if actual['case'] != expected['case'] or int(actual['rank']) != index:
                raise ValueError('qualified case ordering differs from independent ranking')
            for field in ('lead1_CSI_at_10mm', 'lead1_CSI_at_5mm', 'lead1_FAR_at_10mm', 'lead1_RMSE_mm'):
                assert_metric(actual[field], expected[field], f'rank-{index}/{field}')
    elif ranking_path.exists():
        raise ValueError('qualified ranking emitted when no candidate passed admission')
    return {'status': 'PASS', 'analysis_receipt_sha256': sha256(receipt_path),
            'recount_tool': identity(Path(__file__)), 'scoring_tool': identity(SCORER_PATH),
            'independently_recounted_rows': counts,
            'checked_arrays': [sha256(analysis_dir / f'hour_{hour}_arrays.npz') for hour in hours],
            'limitations': 'Recounts saved paired point arrays; runtime histories are separately hash-bound by receipts.'}


def replay(runtime_dir: Path, analysis_dir: Path, plan_path: Path, plan_sha256: str):
    analysis_dir = Path(analysis_dir).resolve()
    runtime_dir = Path(runtime_dir).resolve()
    plan_path = Path(plan_path).resolve()
    recorded = json.loads((analysis_dir / 'receipt.json').read_text(encoding='utf-8'))
    temp_root = Path(tempfile.mkdtemp(prefix='weak-strong-replay-'))
    replay_dir = temp_root / 'analysis'
    try:
        scorer = load_scorer()
        scorer.score(runtime_dir, replay_dir, plan_path, plan_sha256)
        expected_files = {path.name for path in analysis_dir.iterdir() if path.is_file()}
        replay_files = {path.name for path in replay_dir.iterdir() if path.is_file()}
        if expected_files != replay_files:
            raise ValueError('replay output file set differs from the sealed analysis')
        differences = []
        for name in sorted(expected_files):
            original, replayed = analysis_dir / name, replay_dir / name
            if original.read_bytes() != replayed.read_bytes():
                differences.append(name)
        if differences:
            raise ValueError(f'full-byte replay differs for outputs: {differences}')
        return {'status': 'PASS', 'analysis_receipt_sha256': sha256(analysis_dir / 'receipt.json'),
                'replayed_outputs': len(expected_files), 'byte_identical_outputs': sorted(expected_files),
                'winner': recorded['winner']}
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--analysis', type=Path, default=ROOT / 'docs/evidence/weak_strong_balance_20261030/analysis')
    parser.add_argument('--runtime-dir', type=Path, default=ROOT / 'docs/evidence/weak_strong_balance_20261030/runtime')
    parser.add_argument('--plan', type=Path, default=ROOT / 'docs/evidence/weak_strong_balance_20261030/selection_plan.json')
    parser.add_argument('--plan-sha256', required=True)
    parser.add_argument('--replay', action='store_true')
    parser.add_argument('--output', type=Path, help='write audit JSON to this path')
    args = parser.parse_args()
    result = recount(args.analysis)
    if args.replay:
        result['replay'] = replay(args.runtime_dir, args.analysis, args.plan, args.plan_sha256)
    text = json.dumps(result, indent=2, allow_nan=False) + '\n'
    if args.output:
        args.output.write_text(text, encoding='utf-8')
    print(text, end='')


if __name__ == '__main__':
    main()
