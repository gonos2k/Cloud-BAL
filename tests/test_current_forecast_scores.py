"""Check paired precipitation statistics, including undefined denominators."""
import importlib.util
from pathlib import Path

import numpy as np

PATH = Path(__file__).resolve().parents[1] / 'docs/evidence/current_forecast_paper_20261029/score_forecasts.py'
SPEC = importlib.util.spec_from_file_location('current_forecast_scores', PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_contingency_and_paired_transitions():
    reference = np.array([1., 1., 0., 0.])
    original = np.array([1., 0., 1., 0.])
    candidate = 1. - original
    result = MODULE.scores(original, reference, 1.)
    assert [result[k] for k in ('hit', 'miss', 'false_alarm', 'correct_dry')] == [1, 1, 1, 1]
    assert [result[k] for k in ('CSI', 'ETS', 'POD', 'FAR', 'frequency_bias')] == [1/3, 0, 0.5, 0.5, 1]
    assert list(MODULE.transitions(original, candidate, reference, 1.).values()) == [1, 1, 1, 1]


def test_all_dry_scores_are_undefined():
    dry = np.zeros(4)
    result = MODULE.scores(dry, dry, 1.)
    assert all(result[k] is None for k in ('CSI', 'ETS', 'POD', 'FAR', 'frequency_bias'))


def fake_reference(monkeypatch):
    monkeypatch.setattr(MODULE, 'reference_records', lambda *_: {})
    monkeypatch.setattr(MODULE.evaluator, 'load_reference',
                        lambda *_: ({}, np.ones(3688, dtype=bool), None, None, {}))


def test_missing_hour_leaves_no_output(tmp_path, monkeypatch):
    import pytest

    fake_reference(monkeypatch)
    history = tmp_path / 'history'
    history.mkdir()
    (history / 'wrfout_d01_2026-08-16_12:00:00').write_text('first hour')
    monkeypatch.setattr(MODULE.evaluator, 'read_wrf_snapshot',
                        lambda *_: {'lat': np.ones((2, 2)), 'lon': np.ones((2, 2))})
    output = tmp_path / 'result'
    with pytest.raises(FileNotFoundError):
        MODULE.run({'ORIGINAL': history, 'CURRENT_OFF': history}, 'ORIGINAL',
                   tmp_path, tmp_path, tmp_path, output)
    assert not output.exists()


def test_history_mutation_leaves_no_output(tmp_path, monkeypatch):
    import pytest

    fake_reference(monkeypatch)
    history = tmp_path / 'history'
    history.mkdir()
    path = history / 'wrfout_d01_2026-08-16_12:00:00'
    path.write_text('before')
    def mutate_during_read(path, *_):
        path.write_text('after')
        return {'lat': np.ones((2, 2)), 'lon': np.ones((2, 2))}
    monkeypatch.setattr(MODULE.evaluator, 'read_wrf_snapshot', mutate_during_read)
    output = tmp_path / 'result'
    with pytest.raises(ValueError, match='changed while reading'):
        MODULE.run({'ORIGINAL': history, 'CURRENT_OFF': history}, 'ORIGINAL',
                   tmp_path, tmp_path, tmp_path, output)
    assert not output.exists()


def test_reference_mutation_leaves_no_output(tmp_path, monkeypatch):
    import pytest

    source = tmp_path / 'reference'
    source.write_text('before')
    record = MODULE.evaluator.identity(source)
    monkeypatch.setattr(MODULE, 'reference_records', lambda *_: {'reference': record})
    def mutate_reference(*_):
        source.write_text('after')
        return {}, np.ones(3688, dtype=bool), None, None, {}
    monkeypatch.setattr(MODULE.evaluator, 'load_reference', mutate_reference)
    output = tmp_path / 'result'
    with pytest.raises(ValueError, match='input changed'):
        MODULE.run({'ORIGINAL': tmp_path, 'CURRENT_OFF': tmp_path}, 'ORIGINAL',
                   tmp_path, tmp_path, tmp_path, output)
    assert not output.exists()


def test_dangling_output_symlink_is_not_overwritten(tmp_path):
    import pytest

    target = tmp_path / 'absent'
    output = tmp_path / 'result'
    output.symlink_to(target)
    with pytest.raises(ValueError, match='already exists'):
        MODULE.run({'ORIGINAL': tmp_path, 'CURRENT_OFF': tmp_path}, 'ORIGINAL',
                   tmp_path, tmp_path, tmp_path, output)
    assert output.is_symlink() and not target.exists()


def test_additional_baseline_transitions_use_its_own_values():
    values = {'reference': np.array([1., 1., 0., 0.]),
              'ORIGINAL': np.array([1., 0., 1., 0.]),
              'CURRENT_OFF': np.array([0., 1., 0., 1.]),
              'CURRENT_HYDRO': np.array([1., 1., 0., 0.])}
    rows = MODULE.transition_rows(values, list(values)[1:], 'ORIGINAL', ['CURRENT_OFF'], 13)
    rows = [row for row in rows if row['threshold_mm'] == 1.]
    pairs = {(row['baseline'], row['candidate']): row for row in rows}
    assert set(pairs) == {('ORIGINAL', 'CURRENT_OFF'), ('ORIGINAL', 'CURRENT_HYDRO'),
                          ('CURRENT_OFF', 'CURRENT_HYDRO')}
    assert (pairs['ORIGINAL', 'CURRENT_HYDRO']['hit_gains'],
            pairs['ORIGINAL', 'CURRENT_HYDRO']['hit_losses']) == (1, 0)
    assert (pairs['CURRENT_OFF', 'CURRENT_HYDRO']['hit_gains'],
            pairs['CURRENT_OFF', 'CURRENT_HYDRO']['false_alarm_losses']) == (1, 1)
