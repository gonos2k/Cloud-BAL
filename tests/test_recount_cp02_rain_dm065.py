import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f'tools/{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

score = load('cp02_rain_dm065_evaluation')
independent = load('recount_cp02_rain_dm065')


def fixture(tmp_path):
    plan = tmp_path / 'plan.json'
    plan.write_text('{}')
    observed = np.resize(np.array([0., .1, .5, 1., 2.5, 5., 10.]), 3688)
    arrays = {}
    for hour in range(13, 19):
        values = {case: np.roll(observed, hour - 12) for case in score.CASES}
        values.update(reference=observed, latitude=np.arange(3688.), longitude=np.arange(3688.),
                      flat_index_yx=np.arange(3688))
        arrays[hour] = values
        np.savez_compressed(tmp_path / f'hour_{hour}_arrays.npz', **values)
    cat, cont, constraints = score.compare_scores(arrays)
    for name, rows in [('categorical_scores.csv', cat), ('continuous_scores.csv', cont),
                       ('admission_constraints.csv', constraints)]:
        score.prior.csv_output(tmp_path / name, rows)
    passed = sum(row['satisfied'] for row in constraints)
    (tmp_path / 'winner.json').write_text(json.dumps({'candidate': score.CANDIDATE, 'qualified': passed == 26,
                                                       'passed_constraints': passed, 'required_constraints': 26,
                                                       'selection': score.CANDIDATE if passed == 26 else 'NO_QUALIFIED_CANDIDATE'}))
    (tmp_path / 'receipt.json').write_text('{}')
    return plan


def test_independent_recount_and_detected_tamper(tmp_path):
    plan = fixture(tmp_path)
    report = independent.recount(tmp_path, plan, independent.sha(plan), tmp_path / 'result.json')
    assert report['status'] == 'PASS'
    path = tmp_path / 'categorical_scores.csv'
    text = path.read_text().replace(',3688,', ',3687,', 1)
    path.write_text(text)
    with pytest.raises(ValueError, match='categorical count mismatch'):
        independent.recount(tmp_path, plan, independent.sha(plan), tmp_path / 'other.json')
