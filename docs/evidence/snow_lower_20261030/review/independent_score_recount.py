#!/usr/bin/env python3
"""Independently recount archived lower-factor scores from paired arrays."""

import csv
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[4]
BUNDLE = Path(__file__).resolve().parents[1]
ANALYSIS = BUNDLE / 'analysis'
PRIOR_ANALYSIS = ROOT / 'docs/evidence/snow_fine_20261030/analysis'
SCORING_TOOL = ROOT / 'tools/cp02_snow_sensitivity.py'
HOURS = tuple(range(13, 19))
THRESHOLDS = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_csv(path):
    with Path(path).open(newline='') as stream:
        return list(csv.DictReader(stream))


def number(value):
    return None if value is None or value == '' else float(value)


def same_metric(actual, expected):
    if expected is None:
        return actual in (None, '')
    return float(actual) == float(expected)


def alpha_by_case():
    factors = {'000': 0.0, '025': 0.25, '050': 0.5, '060': 0.6,
               '070': 0.7, '075': 0.75, '080': 0.8, '090': 0.9,
               '110': 1.1, '120': 1.2, '130': 1.3, '140': 1.4,
               '125': 1.25, '150': 1.5, '175': 1.75, '200': 2.0,
               '250': 2.5, '300': 3.0}
    return {f'{arm}_SNOW_{suffix}': alpha for arm in ('CONTROL', 'IMPROVED')
            for suffix, alpha in factors.items()}


def recount():
    receipt_path = ANALYSIS / 'receipt.json'
    receipt = json.loads(receipt_path.read_text())
    if receipt.get('status') != 'COMPLETE' or len(receipt.get('cases', [])) != 39:
        raise ValueError('lower-factor analysis is incomplete or has wrong context scope')
    if len(receipt.get('eligible_cases', [])) != 38 or receipt.get('context_only_cases') != ['CURRENT_HYDRO']:
        raise ValueError('lower-factor eligibility scope changed')
    for name, manifest in receipt['analysis_outputs'].items():
        if sha256(ANALYSIS / name) != manifest['sha256']:
            raise ValueError(f'analysis output hash mismatch: {name}')

    prior = json.loads((PRIOR_ANALYSIS / 'receipt.json').read_text())
    extension = load_module('snow_extension_independent_review', ROOT / 'tools/cp02_snow_extension.py')
    old_tool = extension.load_prior_tool()
    scorer = old_tool.load_prior_scorer().load_scorer()
    case_order = receipt['cases']
    eligible = receipt['eligible_cases']
    categorical = read_csv(ANALYSIS / 'categorical_scores.csv')
    continuous = read_csv(ANALYSIS / 'continuous_scores.csv')
    categorical_index = {}
    continuous_index = {}
    recomputed_cat, recomputed_cont = [], []
    pointwise_difference_arrays = 0
    for hour in HOURS:
        with np.load(ANALYSIS / f'hour_{hour}_arrays.npz', allow_pickle=False) as data:
            values = {key: np.asarray(data[key]) for key in data.files}
        if set(values) != set(case_order) | {'reference', 'latitude', 'longitude', 'flat_index_yx'}:
            raise ValueError(f'{hour}: paired array keys do not match receipt context')
        if any(array.shape != (3688,) or not np.isfinite(array).all() for array in values.values()):
            raise ValueError(f'{hour}: paired arrays contain invalid shape or values')
        with np.load(PRIOR_ANALYSIS / f'hour_{hour}_arrays.npz', allow_pickle=False) as old_data:
            old = {key: np.asarray(old_data[key]) for key in old_data.files}
        for case in prior['cases']:
            if not np.array_equal(values[case], old[case]):
                raise ValueError(f'{hour}/{case}: reused prior forecast array changed')
        with np.load(ANALYSIS / f'hour_{hour}_difference_vs_original.npz', allow_pickle=False) as data:
            differences = {key: np.asarray(data[key]) for key in data.files}
        expected_difference_keys = set(case_order) | {
            'reference', 'flat_index_yx', 'latitude', 'longitude'}
        if set(differences) != expected_difference_keys:
            raise ValueError(f'{hour}: pointwise difference array keys differ from the context')
        for key in ('reference', 'flat_index_yx', 'latitude', 'longitude'):
            if not np.array_equal(differences[key], values[key]):
                raise ValueError(f'{hour}: pointwise difference coordinate/observation mismatch: {key}')
        for case in case_order:
            expected = np.asarray(values[case], dtype=np.float64) - np.asarray(
                values['ORIGINAL'], dtype=np.float64)
            if differences[case].shape != (3688,) or not np.array_equal(differences[case], expected):
                raise ValueError(f'{hour}/{case}: pointwise precipitation difference mismatch')
        pointwise_difference_arrays += 1
        obs = np.asarray(values['reference'], dtype=np.float64)
        lead = hour - 12
        for case in case_order:
            pred = np.asarray(values[case], dtype=np.float64)
            error = pred - obs
            cont = {'lead_hour': lead, 'case': case, 'valid_obs': obs.size,
                    'mean_forecast_mm': float(np.mean(pred)),
                    'mean_reference_mm': float(np.mean(obs)),
                    'MAE_mm': float(np.mean(np.abs(error))),
                    'RMSE_mm': float(np.sqrt(np.mean(error ** 2)))}
            recomputed_cont.append(cont)
            continuous_index[(lead, case)] = cont
            for threshold in THRESHOLDS:
                metrics = scorer.scores(pred, obs, threshold)
                row = {'lead_hour': lead, 'case': case, 'threshold_mm': threshold, **metrics}
                recomputed_cat.append(row)
                categorical_index[(lead, case, threshold)] = row

    if len(categorical) != len(recomputed_cat) or len(continuous) != len(recomputed_cont):
        raise ValueError('analysis score tables have incomplete grids')
    if (len({(int(row['lead_hour']), row['case'], float(row['threshold_mm'])) for row in categorical})
        != len(categorical)
        or len({(int(row['lead_hour']), row['case']) for row in continuous}) != len(continuous)):
        raise ValueError('analysis score tables contain duplicate rows')
    cat_fields = ('hit', 'miss', 'false_alarm', 'correct_dry', 'CSI', 'ETS', 'POD', 'FAR',
                  'frequency_bias')
    for row in categorical:
        key = (int(row['lead_hour']), row['case'], float(row['threshold_mm']))
        expected = categorical_index[key]
        for field in cat_fields:
            if not same_metric(row.get(field), expected[field]):
                raise ValueError(f'{key}/{field}: categorical recount mismatch')
    cont_fields = ('valid_obs', 'mean_forecast_mm', 'mean_reference_mm', 'MAE_mm', 'RMSE_mm')
    for row in continuous:
        key = (int(row['lead_hour']), row['case'])
        expected = continuous_index[key]
        for field in cont_fields:
            if not same_metric(row.get(field), expected[field]):
                raise ValueError(f'{key}/{field}: continuous recount mismatch')

    alphas = {'ORIGINAL': 1.0, 'IMPROVED_BG_FIXED': 1.0, **alpha_by_case()}
    arms = {'ORIGINAL': 'CONTROL', 'IMPROVED_BG_FIXED': 'IMPROVED',
            **{case: case.split('_', 1)[0] for case in alpha_by_case()}}
    rank_rows = []
    for case in eligible:
        csi10 = number(categorical_index[(1, case, 10.0)]['CSI'])
        csi5 = number(categorical_index[(1, case, 5.0)]['CSI'])
        far10 = number(categorical_index[(1, case, 10.0)]['FAR'])
        rmse = number(continuous_index[(1, case)]['RMSE_mm'])
        alpha = alphas.get(case, 1.0)
        rank_rows.append((case, csi10, csi5, far10, rmse, alpha))

    def order_key(row):
        case, csi10, csi5, far10, rmse, alpha = row
        factor_code = int(case.rsplit('_', 1)[1]) if '_SNOW_' in case else 100
        return (csi10 is None, -csi10 if csi10 is not None else 0.0,
                csi5 is None, -csi5 if csi5 is not None else 0.0,
                far10 is None, far10 if far10 is not None else 0.0,
                rmse is None, rmse if rmse is not None else 0.0,
                abs(factor_code - 100), case)

    selection_order = [row[0] for row in sorted(rank_rows, key=order_key)]
    selection = json.loads((ANALYSIS / 'selection.json').read_text())
    if (selection.get('selected_case') != selection_order[0]
        or selection.get('selection_order') != selection_order
        or selection.get('completed_candidate_count') != 38):
        raise ValueError('single-winner selection does not match independent lead-one recount')
    selection_rows = read_csv(ANALYSIS / 'selection_scores.csv')
    if len(selection_rows) != len(selection_order):
        raise ValueError('selection ranking table is incomplete')
    for index, row in enumerate(selection_rows, 1):
        case = selection_order[index - 1]
        if (row['case'] != case or int(row['rank']) != index
            or float(row['alpha']) != alphas[case]
            or float(row['abs_alpha_distance_from_1']) != abs(
                (int(case.rsplit('_', 1)[1]) if '_SNOW_' in case else 100) - 100) / 100.0
            or row['arm'] != arms[case]):
            raise ValueError(f'{case}: selection row metadata or rank mismatch')

    comparison = read_csv(ANALYSIS / 'comparison_vs_original.csv')
    if len(comparison) != 38 * 6 * 6:
        raise ValueError('comparison table has incomplete eligible coverage')
    comparison_keys = {(row['case'], int(row['lead_hour']), float(row['threshold_mm']))
                       for row in comparison}
    expected_comparison_keys = {(case, lead, threshold) for case in eligible
                                for lead in range(1, 7) for threshold in THRESHOLDS}
    if len(comparison_keys) != len(comparison) or comparison_keys != expected_comparison_keys:
        raise ValueError('comparison table contains duplicate or missing case/lead/threshold rows')
    for row in comparison:
        lead, threshold, case = int(row['lead_hour']), float(row['threshold_mm']), row['case']
        candidate = categorical_index[(lead, case, threshold)]
        baseline = categorical_index[(lead, 'ORIGINAL', threshold)]
        if (row['baseline_case'] != 'ORIGINAL'
            or not same_metric(row['CSI'], candidate['CSI'])
            or not same_metric(row['baseline_CSI'], baseline['CSI'])
            or not same_metric(row['delta_CSI_vs_ORIGINAL'],
                               None if candidate['CSI'] is None or baseline['CSI'] is None
                               else candidate['CSI'] - baseline['CSI'])
            or not same_metric(row['FAR'], candidate['FAR'])
            or not same_metric(row['baseline_FAR'], baseline['FAR'])
            or not same_metric(row['delta_FAR_vs_ORIGINAL'],
                               None if candidate['FAR'] is None or baseline['FAR'] is None
                               else candidate['FAR'] - baseline['FAR'])):
            raise ValueError(f'{case}/{lead}/{threshold}: comparison baseline/recount mismatch')

    return {
        'schema': 'snow-lower-independent-score-recount-v1',
        'status': 'PASS',
        'analysis_receipt_sha256': sha256(receipt_path),
        'case_context_count': len(case_order), 'eligible_count': len(eligible),
        'context_only': ['CURRENT_HYDRO'],
        'lead_hours': list(range(1, 7)), 'thresholds_mm': list(THRESHOLDS),
        'categorical_rows_recomputed': len(recomputed_cat),
        'continuous_rows_recomputed': len(recomputed_cont),
        'comparison_rows_recomputed': len(comparison),
        'pointwise_difference_arrays_recomputed': pointwise_difference_arrays,
        'pointwise_case_differences_recomputed': pointwise_difference_arrays * len(case_order),
        'max_absolute_metric_error': 0.0,
        'reused_prior_case_arrays_exact': True,
        'selection_rule_recomputed_from_lead1_only': True,
        'no_average_or_pooled_error_in_selection': True,
        'comparison_baseline': 'ORIGINAL (CONTROL QSNOW alpha=1.0)',
        'pointwise_comparison': 'hourly candidate total precipitation minus ORIGINAL at each paired point (mm)',
        'selection_order': selection_order,
        'selected_case': selection_order[0],
        'all_analysis_output_hashes_verified': True,
    }


if __name__ == '__main__':
    result = recount()
    output = BUNDLE / 'review/independent_score_recount.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
