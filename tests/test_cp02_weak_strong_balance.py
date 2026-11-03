"""Frozen admission and ranking rules for the weak/strong gate experiment."""

import importlib.util
import csv
import json
import tempfile
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'cp02_weak_strong_balance', ROOT / 'tools/cp02_weak_strong_balance.py')
balance = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(balance)


def score_row(case, lead, threshold, hit, miss, false_alarm):
    denominator = hit + miss + false_alarm
    csi = hit / denominator if denominator else None
    far_denominator = hit + false_alarm
    far = false_alarm / far_denominator if far_denominator else None
    pod_denominator = hit + miss
    pod = hit / pod_denominator if pod_denominator else None
    n = denominator + 1
    random_hits = (hit + miss) * (hit + false_alarm) / n
    ets_denominator = denominator - random_hits
    ets = (hit - random_hits) / ets_denominator if ets_denominator else None
    frequency_bias = (hit + false_alarm) / pod_denominator if pod_denominator else None
    return {'case': case, 'lead_hour': lead, 'threshold_mm': threshold,
            'hit': hit, 'miss': miss, 'false_alarm': false_alarm,
            'CSI': csi, 'FAR': far, 'POD': pod, 'ETS': ets,
            'frequency_bias': frequency_bias}


def make_score_grid(qualify_case=None, weak_failure_case=None, strong_improvement_case=None):
    categorical, continuous = [], []
    for case in balance.CONTEXT_IDS:
        for lead in range(1, 7):
            for threshold in balance.THRESHOLDS:
                hit, miss, false_alarm = 1, 1, 1
                if case == qualify_case and threshold in balance.WEAK_THRESHOLDS:
                    hit, miss = 2, 0
                if case == qualify_case and lead == 1 and threshold == 10.0:
                    hit, miss, false_alarm = 2, 0, 0
                if case == weak_failure_case and lead == 2 and threshold == 0.1:
                    hit, miss, false_alarm = 0, 2, 0
                if case == strong_improvement_case and lead == 1 and threshold == 10.0:
                    hit, miss, false_alarm = 2, 0, 0
                categorical.append(score_row(case, lead, threshold, hit, miss, false_alarm))
            continuous.append({'case': case, 'lead_hour': lead,
                               'RMSE_mm': 1.0 if case == qualify_case else 2.0,
                               'MAE_mm': 1.0 if case == qualify_case else 2.0,
                               'mean_forecast_mm': 1.0, 'mean_reference_mm': 1.0})
    return categorical, continuous


def test_plan_is_pinned_and_lead_one_rmse_is_explicit():
    record, plan = balance.check_selection_plan()
    assert record['sha256'] == balance.PLAN_SHA256
    assert plan['evaluation']['ranking_order_after_admission'][3] == 'ascending lead-1 RMSE'


def test_frozen_plan_runtime_path_survives_checkout_relocation(monkeypatch):
    frozen_path = balance.check_selection_plan()[1]['evaluation']['runtime_directory']
    monkeypatch.setattr(balance, 'RUNTIME_DIR', Path('/relocated/archive/runtime'))
    record, plan = balance.check_selection_plan()
    assert record['sha256'] == balance.PLAN_SHA256
    assert plan['evaluation']['runtime_directory'] == frozen_path


def test_csi_admission_uses_exact_cross_products():
    baseline = {'hit': 1, 'miss': 1, 'false_alarm': 1}
    equal = {'hit': 2, 'miss': 2, 'false_alarm': 2}
    above = {'hit': 2, 'miss': 1, 'false_alarm': 1}
    strict = {'hit': 2, 'miss': 0, 'false_alarm': 0}
    assert balance.csi_ge_exact(equal, baseline)
    assert not balance.csi_gt_exact(equal, baseline)
    assert balance.csi_ge_exact(above, baseline)
    assert balance.csi_gt_exact(strict, baseline)
    assert not balance.csi_ge_exact({'hit': 0, 'miss': 0, 'false_alarm': 0}, baseline)
    undefined = {'hit': 0, 'miss': 0, 'false_alarm': 0}
    assert not balance.csi_ge_exact(baseline, undefined)
    assert not balance.csi_ge_exact(undefined, undefined)
    assert not balance.csi_gt_exact(undefined, undefined)


def test_only_candidate_passing_every_weak_and_strong_cell_is_ranked():
    categorical, continuous = make_score_grid('GATE_G50_90')
    constraints, ranked, winner = balance.select_winner(categorical, continuous)
    assert len(constraints) == len(balance.CASE_IDS) * 19
    assert [row['case'] for row in ranked] == ['GATE_G50_90']
    assert winner['status'] == 'QUALIFIED_CANDIDATE'
    assert winner['selected_case'] == 'GATE_G50_90'


def test_no_qualified_candidate_does_not_relax_admission():
    categorical, continuous = make_score_grid()
    constraints, ranked, winner = balance.select_winner(categorical, continuous)
    assert len(constraints) == len(balance.CASE_IDS) * 19
    assert ranked == []
    assert winner['status'] == 'NO_QUALIFIED_CANDIDATE'
    assert winner['selected_case'] is None


def test_strong_cell_gain_cannot_override_any_failed_weak_floor():
    categorical, continuous = make_score_grid(
        weak_failure_case='EQ_G50_90', strong_improvement_case='EQ_G50_90')
    constraints, ranked, winner = balance.select_winner(categorical, continuous)
    eq_constraints = [row for row in constraints if row['case'] == 'EQ_G50_90']
    strong = next(row for row in eq_constraints if row['constraint'].startswith('lead1_CSI10'))
    failed_weak = [row for row in eq_constraints
                   if row['constraint'] == 'weak_CSI_at_least_ORIGINAL' and row['status'] == 'FAIL']
    assert strong['status'] == 'PASS'
    assert failed_weak
    assert ranked == []
    assert winner['status'] == 'NO_QUALIFIED_CANDIDATE'
    assert winner['selected_case'] is None


def test_gate_comparison_and_factorial_interaction_keep_each_dimension():
    categorical, continuous = make_score_grid('GATE_G50_90')
    gates, factorial = balance.comparison_rows(categorical, continuous)
    assert len(gates) == 3 * 6 * (len(balance.THRESHOLDS) + 1)
    assert len(factorial) == 6 * (len(balance.THRESHOLDS) * 8 + 4)
    assert {row['gate_case'] for row in gates} == {pair[0] for pair in balance.GATE_PAIRS}
    assert {row['metric'] for row in factorial} == {
        'CSI', 'FAR', 'POD', 'ETS', 'frequency_bias', 'MAE_mm', 'RMSE_mm',
        'mean_forecast_mm', 'mean_reference_mm', 'hit', 'miss', 'false_alarm'}
    assert {row['row_type'] for row in gates} == {'categorical', 'continuous'}
    assert {row['unit'] for row in gates} == {'dimensionless', 'mm'}


def test_csv_writer_unions_heterogeneous_rows_and_keeps_missing_values_blank():
    rows = [{'row_type': 'categorical', 'metric': 'CSI', 'hit': 3},
            {'row_type': 'continuous', 'metric': 'RMSE_mm', 'RMSE_mm': 1.2}]
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'mixed.csv'
        balance.write_csv(path, rows)
        with path.open(encoding='utf-8', newline='') as stream:
            result = list(csv.DictReader(stream))
    assert result[0]['hit'] == '3' and result[0]['RMSE_mm'] == ''
    assert result[1]['hit'] == '' and result[1]['RMSE_mm'] == '1.2'


def test_no_winner_postprocessing_serializes_every_table_and_point_archive():
    class Scorer:
        @staticmethod
        def scores(prediction, observed, threshold):
            forecast_event, obs_event = prediction >= threshold, observed >= threshold
            hit = int(np.count_nonzero(forecast_event & obs_event))
            miss = int(np.count_nonzero(~forecast_event & obs_event))
            false_alarm = int(np.count_nonzero(forecast_event & ~obs_event))
            denominator = hit + miss + false_alarm
            return {'hit': hit, 'miss': miss, 'false_alarm': false_alarm,
                    'CSI': hit / denominator if denominator else None,
                    'FAR': false_alarm / (hit + false_alarm) if hit + false_alarm else None,
                    'POD': hit / (hit + miss) if hit + miss else None,
                    'ETS': 0.0, 'frequency_bias': 1.0}

    obs = np.tile(np.array([0.0, 0.2, 2.0, 12.0]), balance.POINTS // 4)
    source = {'reference': obs, 'latitude': np.zeros(balance.POINTS),
              'longitude': np.zeros(balance.POINTS),
              'flat_index_yx': np.arange(balance.POINTS)}
    arrays = {hour: {**source, **{case: obs.copy() for case in balance.CONTEXT_IDS}}
              for hour in balance.HOURS}
    categorical, continuous, transitions, transition_arrays = balance.score_arrays(arrays, Scorer())
    admission, ranked, winner = balance.select_winner(categorical, continuous)
    gates, factorial = balance.comparison_rows(categorical, continuous)
    exact = balance.exact_csi_change_rows(categorical)
    bands, histograms = balance.intensity_band_rows(arrays)
    differences = balance.point_differences(arrays)
    tables = {'categorical_scores.csv': categorical, 'continuous_scores.csv': continuous,
              'transitions_vs_original.csv': transitions, 'admission_constraints.csv': admission,
              'gate_equal_mass_comparison.csv': gates,
              'factorial_difference_in_differences.csv': factorial,
              'csi_change_exact_counts.csv': exact,
              'observation_band_transitions.csv': bands,
              'observed_forecast_bin_counts.csv': histograms}
    assert winner['status'] == 'NO_QUALIFIED_CANDIDATE' and winner['selected_case'] is None
    assert len(admission) == len(balance.CASE_IDS) * 19 and ranked == []
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for filename, rows in tables.items():
            balance.write_csv(root / filename, rows)
            assert (root / filename).stat().st_size > 0
        (root / 'winner.json').write_text(json.dumps(winner, allow_nan=False), encoding='utf-8')
        for hour in balance.HOURS:
            np.savez_compressed(root / f'hour_{hour}_arrays.npz', **arrays[hour])
            np.savez_compressed(root / f'hour_{hour}_difference_vs_original.npz', **differences[hour])
            np.savez_compressed(root / f'hour_{hour}_transitions_vs_original.npz',
                                **transition_arrays[hour])
        assert len(list(root.iterdir())) == len(tables) + 1 + 3 * len(balance.HOURS)


def test_canonical_arrays_drop_prior_cases_outside_frozen_context():
    base = {hour: {**{case: np.zeros(balance.POINTS) for case in balance.CONTEXT_IDS},
                   'CONTROL_SNOW_025': np.ones(balance.POINTS),
                   'reference': np.zeros(balance.POINTS), 'latitude': np.zeros(balance.POINTS),
                   'longitude': np.zeros(balance.POINTS),
                   'flat_index_yx': np.arange(balance.POINTS)}
            for hour in balance.HOURS}
    canonical = balance.canonical_paired_arrays(base)
    for hour in balance.HOURS:
        assert set(canonical[hour]) == set(balance.CONTEXT_IDS) | {
            'reference', 'latitude', 'longitude', 'flat_index_yx'}


def test_exact_csi_change_numerator_reconciles_hit_and_false_alarm_deltas():
    categorical, _ = make_score_grid('GATE_G50_90')
    rows = balance.exact_csi_change_rows(categorical)
    assert len(rows) == (len(balance.CONTEXT_IDS) - 1) * 6 * len(balance.THRESHOLDS)
    for row in rows:
        assert row['csi_delta_exact_numerator'] == (
            row['candidate_hit'] * row['baseline_CSI_denominator']
            - row['baseline_hit'] * row['candidate_CSI_denominator'])
        assert row['csi_delta_exact_numerator'] == row['csi_delta_factorized_numerator']
        assert row['csi_delta_exact_denominator'] == (
            row['baseline_CSI_denominator'] * row['candidate_CSI_denominator'])
        assert row['observed_event_count'] == row['baseline_hit'] + row['baseline_miss']


def test_factorial_hit_and_false_alarm_dids_are_integer_counts():
    categorical, continuous = make_score_grid()
    changed = next(row for row in categorical if row['case'] == 'FIXED_ORIGINAL_100'
                   and row['lead_hour'] == 1 and row['threshold_mm'] == 1.0)
    changed['hit'], changed['miss'] = 2, 0
    _, factorial = balance.comparison_rows(categorical, continuous)
    rows = {row['metric']: row for row in factorial
            if row['lead_hour'] == 1 and row['threshold_mm'] == 1.0}
    assert rows['hit']['difference_in_differences'] == -1
    assert rows['miss']['difference_in_differences'] == 1
    assert rows['false_alarm']['difference_in_differences'] == 0


def test_disjoint_observation_bins_cover_every_point_without_masking():
    arrays = {}
    for hour in balance.HOURS:
        values = {case: [0.0, 0.2, 2.0, 12.0] for case in balance.CONTEXT_IDS}
        values.update({'reference': [0.0, 0.2, 2.0, 12.0], 'latitude': [0.0] * 4,
                       'longitude': [0.0] * 4, 'flat_index_yx': [0, 1, 2, 3]})
        arrays[hour] = values
    bands, histograms = balance.intensity_band_rows(arrays)
    assert len(bands) == (len(balance.CONTEXT_IDS) - 1) * 6 * 6 * 5
    assert len(histograms) == (len(balance.CONTEXT_IDS) - 1) * 6 * 5 * 2 * 5
    for case in balance.CONTEXT_IDS[1:]:
        for lead in range(1, 7):
            for threshold in balance.THRESHOLDS:
                rows = [row for row in bands if row['case'] == case
                        and row['lead_hour'] == lead and row['threshold_mm'] == threshold]
                assert sum(row['point_count'] for row in rows) == 4
            for obs_bin in ('dry', 'light', 'moderate', 'strong', 'very_strong'):
                rows = [row for row in histograms if row['case'] == case
                        and row['lead_hour'] == lead and row['observed_bin'] == obs_bin]
                assert len(rows) == 2 * 5


def test_gate_metadata_does_not_treat_horizontal_mean_as_scalar_dose():
    records = {}
    for case in balance.CASE_IDS:
        gate = case.startswith('GATE_')
        equal = case.startswith('EQ_')
        audit = {'transform': 'spatial gate' if gate else 'uniform equal-mass' if equal else 'unchanged',
                 'source_wrfinput_sha256': 'input', 'changed_variables': ['QSNOW'] if gate or equal else [],
                 'staged_diagnostic_snow_mass_kg': 10.0, 'gate_alpha_min': 1.0,
                 'gate_alpha_max': 3.0, 'gate_alpha_mean': 1.2, 'equal_mass_alpha': 2.5,
                 'matched_gate_relative_mass_difference': 1e-10}
        records[case] = {'qsnow_audit': audit, 'input_family': 'ORIGINAL',
                         'executable_family': 'ORIGINAL', 'alpha': 1.2,
                         'staged_sha256': {'wrf.exe': 'exe', 'wrfinput_d01': 'input'}}
    metadata = balance.case_metadata({'case_records': records})
    assert metadata['GATE_G50_90']['alpha_min'] == 1.0
    assert metadata['GATE_G50_90']['alpha_max'] == 3.0
    assert metadata['GATE_G50_90']['alpha_horizontal_mean'] == 1.2
    assert metadata['GATE_G50_90']['uniform_alpha'] is None
    assert metadata['EQ_G50_90']['uniform_alpha'] == 2.5
    assert metadata['EQ_G50_90']['matched_gate_relative_mass_difference'] == 1e-10

