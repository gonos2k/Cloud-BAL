"""Fail-closed gates and arithmetic for the first-hour factorial scorer."""
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'cp02_first_hour_factorial', ROOT / 'tools/cp02_first_hour_factorial.py')
factorial = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(factorial)


class HashEvaluator:
    @staticmethod
    def identity(path):
        path = Path(path)
        data = path.read_bytes()
        return {'path': str(path), 'sha256': hashlib.sha256(data).hexdigest()}


def build_run(tmp_path, *, incomplete=False):
    tmp_path.mkdir(parents=True, exist_ok=True)
    run = tmp_path / 'run'
    source = tmp_path / 'source'
    run.mkdir(); source.mkdir()
    staged = {}
    for index in range(89):
        name = 'wrf.exe' if index == 0 else f'input_{index:02d}'
        content = f'staged:{name}'.encode()
        (run / name).write_bytes(content)
        staged[name] = hashlib.sha256(content).hexdigest()
    source_hashes = {}
    for index in range(88):
        name = f'source_{index:02d}'
        content = f'source:{name}'.encode()
        (source / name).write_bytes(content)
        source_hashes[name] = hashlib.sha256(content).hexdigest()
    for name in factorial.HISTORIES:
        (run / name).write_bytes(name.encode())
    receipt = {'exit': 0, 'success_marker': True, 'histories_exact': True,
               'staged_unchanged': True, 'source_unchanged': True,
               'histories': factorial.HISTORIES,
               'output_sha256': {name: HashEvaluator.identity(run / name)['sha256']
                                 for name in factorial.HISTORIES}}
    if incomplete:
        receipt['output_sha256'].pop(factorial.HISTORIES[1])
    (run / 'receipt.json').write_text(json.dumps(receipt))
    inputs = {'source': str(source), 'source_before': source_hashes,
              'source_after': dict(source_hashes), 'staged': staged}
    (run / 'inputs.json').write_text(json.dumps(inputs))
    return run, staged


def valid_staged():
    common = {f'input_{i:02d}': f'h{i}' for i in range(1, 88)}
    return {
        'BASE_H': {'wrf.exe': factorial.BASE_EXE_SHA,
                   'wrfinput_d01': factorial.HYDRO_INPUT_SHA, **common},
        'FIX_H': {'wrf.exe': factorial.FIX_EXE_SHA,
                  'wrfinput_d01': factorial.HYDRO_INPUT_SHA, **common},
        'BG_BASE': {'wrf.exe': factorial.BASE_EXE_SHA,
                    'wrfinput_d01': factorial.POLICY_INPUT_SHA, **common},
        'POLICY_BG': {'wrf.exe': factorial.FIX_EXE_SHA,
                      'wrfinput_d01': factorial.POLICY_INPUT_SHA, **common},
        'BASE_ORIGINAL': {'wrf.exe': factorial.BASE_EXE_SHA,
                          'wrfinput_d01': factorial.ORIGINAL_INPUT_SHA, **common},
    }


def test_factorial_input_gate_rejects_wrong_executable_or_initial_input():
    staged = valid_staged()
    factorial.verify_factorial_inputs(staged)
    staged['POLICY_BG']['wrf.exe'] = factorial.BASE_EXE_SHA
    with pytest.raises(ValueError, match='POLICY_BG: unexpected executable'):
        factorial.verify_factorial_inputs(staged)
    staged = valid_staged()
    staged['BG_BASE']['wrfinput_d01'] = factorial.HYDRO_INPUT_SHA
    with pytest.raises(ValueError, match='BG_BASE: unexpected initial input'):
        factorial.verify_factorial_inputs(staged)


def test_pairing_gate_rejects_reference_or_flat_id_drift():
    mask = np.ones(3688, dtype=bool)
    lat = np.arange(3688, dtype=float)
    lon = lat + 100.
    ref = lat / 10.
    prior = {'flat_index_yx': np.flatnonzero(mask), 'latitude': lat.copy(),
             'longitude': lon.copy(), 'reference': ref.copy()}
    args = (mask, lat, lon, ref)
    factorial.verify_paired_reference(*args, prior)
    bad_reference = args[3].copy(); bad_reference[-1] += .1
    with pytest.raises(ValueError, match='pinned paired arrays'):
        factorial.verify_paired_reference(*args[:3], bad_reference, prior)
    bad_ids = prior['flat_index_yx'].copy(); bad_ids[-1] -= 1
    bad_prior = dict(prior, flat_index_yx=bad_ids)
    with pytest.raises(ValueError, match='pinned paired arrays'):
        factorial.verify_paired_reference(*args, bad_prior)


def test_runtime_gate_rejects_incomplete_or_mutated_run(tmp_path):
    incomplete, _ = build_run(tmp_path / 'incomplete', incomplete=True)
    with pytest.raises(ValueError, match='manifest is incomplete'):
        factorial.checked_run('BASE_H', incomplete, HashEvaluator())
    intact, _ = build_run(tmp_path / 'intact')
    (intact / factorial.HISTORIES[1]).write_bytes(b'tampered')
    with pytest.raises(ValueError, match='history hash mismatch'):
        factorial.checked_run('BASE_H', intact, HashEvaluator())


def test_score_interaction_is_difference_in_differences_not_share():
    rows = [
        {'case': 'BASE_H', 'MAE_mm': 10., 'RMSE_mm': 10., 'mean_error_mm': 0., 'mean_forecast_mm': 1.},
        {'case': 'FIX_H', 'MAE_mm': 8., 'RMSE_mm': 8., 'mean_error_mm': 0., 'mean_forecast_mm': 2.},
        {'case': 'BG_BASE', 'MAE_mm': 9., 'RMSE_mm': 9., 'mean_error_mm': 0., 'mean_forecast_mm': 3.},
        {'case': 'POLICY_BG', 'MAE_mm': 6., 'RMSE_mm': 6., 'mean_error_mm': 0., 'mean_forecast_mm': 5.},
        {'case': 'BASE_ORIGINAL', 'MAE_mm': 12., 'RMSE_mm': 12., 'mean_error_mm': 0., 'mean_forecast_mm': 0.},
    ]
    out = factorial.contrast_rows(rows)
    interaction = next(row for row in out if row['metric'] == 'MAE_mm'
                       and row['contrast'] == 'interaction_(B1-B0)-(H1-H0)')
    assert interaction['difference'] == pytest.approx(-1.)
    assert 'not a physical causal share' in interaction['interpretation']
