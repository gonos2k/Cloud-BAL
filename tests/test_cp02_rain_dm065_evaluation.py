import importlib.util
from pathlib import Path
import numpy as np
import pytest

SPEC = importlib.util.spec_from_file_location('dm065_score', Path(__file__).resolve().parents[1] / 'tools/cp02_rain_dm065_evaluation.py')
score = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(score)


def arrays():
    observed = np.resize(np.array([0., .1, .5, 1., 2.5, 5., 10.]), 3688)
    return {hour: {**{case: observed.copy() for case in score.CASES}, 'reference': observed.copy()}
            for hour in range(13, 19)}


def test_four_cases_full_rows_and_26_exact_constraints():
    data = arrays()
    cat, continuous, constraints = score.compare_scores(data)
    assert (len(cat), len(continuous), len(constraints)) == (144, 24, 26)
    assert all(row['satisfied'] for row in constraints)
    assert sum(row['goal'] == 'preserve_current_B1' for row in constraints) == 11
    assert sum(row['goal'] == 'recover_low_threshold_vs_ORIGINAL' for row in constraints) == 15
    assert {r['case'] for r in cat} == set(score.CASES)
    data[13][score.CANDIDATE][1] = 0.
    assert not all(row['satisfied'] for row in score.compare_scores(data)[2])


def test_incomplete_or_nonfinite_samples_are_rejected():
    data = arrays()
    data[18][score.CANDIDATE][0] = np.nan
    with pytest.raises(ValueError, match='3688 finite'):
        score.compare_scores(data)
    del data[13]
    with pytest.raises(ValueError, match='six hourly'):
        score.compare_scores(data)


def test_old_evaluator_reproduced_for_common_case_and_constraint_counts():
    data = arrays()
    for hour, row in data.items():
        row[score.OLD_PRIOR] = np.roll(row['reference'], hour - 12)
        row[score.CANDIDATE] = row[score.OLD_PRIOR].copy()
    old_cat, old_cont, old_constraints = score.prior.compare_scores(data)
    new_cat, new_cont, new_constraints = score.compare_scores(data)
    assert [r for r in new_cat if r['case'] != score.CANDIDATE] == old_cat
    assert [r for r in new_cont if r['case'] != score.CANDIDATE] == old_cont
    assert old_constraints == new_constraints


def test_previous_case_merge_checks_full_paired_context(tmp_path, monkeypatch):
    monkeypatch.setattr(score, 'ROOT', tmp_path)
    rows = arrays()
    records = {}
    for hour, values in rows.items():
        for name in ('latitude', 'longitude', 'flat_index_yx'):
            values[name] = np.arange(3688)
        stored = {name: values[name] for name in ('ORIGINAL', score.prior.CURRENT, score.OLD_PRIOR,
                                                  'reference', 'latitude', 'longitude', 'flat_index_yx')}
        path = tmp_path / f'hour_{hour}.npz'
        np.savez_compressed(path, **stored)
        record = score.prior.identity(path)
        record['path'] = path.name
        records[f'hour_{hour}_arrays'] = record
        del values[score.OLD_PRIOR]
    score.merge_previous(rows, records)
    assert score.OLD_PRIOR in rows[13]
    rows[13]['flat_index_yx'][0] = 2
    with pytest.raises(ValueError, match='old prior context differs'):
        score.merge_previous(rows, records)
