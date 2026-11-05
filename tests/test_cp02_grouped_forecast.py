import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

SPEC = importlib.util.spec_from_file_location(
    'cp02_grouped_forecast', Path(__file__).resolve().parents[1] / 'tools/cp02_grouped_forecast.py')
score = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(score)


def make_hourly():
    obs = np.resize(np.array([0.0, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0]), score.POINTS)
    forecasts = {
        'A': obs.copy(), 'B': obs.copy(), 'C': obs.copy(), 'D': obs.copy(), 'ORIGINAL': obs.copy(),
    }
    return {hour: {'reference': obs.copy(), 'latitude': np.arange(score.POINTS, dtype=float),
                   'longitude': np.arange(score.POINTS, dtype=float) + 1,
                   'flat_index_yx': np.arange(score.POINTS), **{
        case: values.copy() for case, values in forecasts.items()}} for hour in range(13, 19)}


def test_full_score_grid_frozen_gates_and_exact_tie_break():
    cat, cont, contrasts, transitions, gates = score.score(make_hourly())
    assert (len(cat), len(cont), len(contrasts), len(transitions), len(gates)) == (180, 30, 180, 24, 52)
    assert sum(row['gate'] == 'preserve_current_B1' for row in gates) == 22
    assert sum(row['gate'] == 'recover_vs_ORIGINAL' for row in gates) == 30
    assert all(row['satisfied'] for row in gates)
    assert score.choose_candidate(gates, cat)['winner'] == 'C'
    assert {row['contrast'] for row in contrasts} == {'C-A', 'D-B', 'B-A', 'D-C', 'DiD'}


def test_weak_and_dry_observation_transition_boundaries():
    hourly = make_hourly()
    values = hourly[13]
    weak = (values['reference'] >= 0.1) & (values['reference'] < 1.0)
    dry = values['reference'] < 0.1
    values['A'][weak] = 0.0
    values['C'][weak] = 0.1
    values['A'][dry] = 0.1
    values['C'][dry] = 0.0
    _, _, _, transitions, _ = score.score(hourly)
    row = next(row for row in transitions if row['lead_hour'] == 1 and row['comparison'] == 'C-A')
    assert row['weak_observed_points'] == int(weak.sum())
    assert row['weak_detection_gains'] == int(weak.sum())
    assert row['weak_detection_losses'] == 0
    assert row['dry_new_false_alarms'] == 0
    assert row['dry_resolved_false_alarms'] == int(dry.sum())


def test_empty_threshold_is_rejected():
    hourly = make_hourly()
    for values in hourly.values():
        values['A'][:] = 0.0
        values['reference'][:] = 0.0
    with pytest.raises(ValueError, match='CSI undefined'):
        score.score(hourly)


def test_full_cohort_and_shared_reference_are_required():
    bundles = {}
    for case in score.ARMS:
        hourly = make_hourly()
        for values in hourly.values():
            values[case] = values[case]
        bundles[case] = ({}, [], hourly)
    bundles['D'][2][13]['flat_index_yx'][0] = 9
    with pytest.raises(ValueError, match='point order differs'):
        score.validate_inputs(bundles)


def write_bundle(folder: Path, case: str, key: str, grouped: bool):
    folder.mkdir()
    outputs = {}
    for hour, values in make_hourly().items():
        path = folder / f'hour_{hour}_arrays.npz'
        np.savez_compressed(path, reference=values['reference'], latitude=np.arange(score.POINTS, dtype=float),
                            longitude=np.arange(score.POINTS, dtype=float) + 1,
                            flat_index_yx=np.arange(score.POINTS), **{key: values[case]})
        outputs[path.name] = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'size_bytes': path.stat().st_size}
    receipt = {'status': 'COMPLETE', 'cases': [case], 'hours_utc': list(range(13, 19)),
               'points_per_hour': score.POINTS, 'thresholds_mm': list(score.THRESHOLDS),
               'outputs': outputs}
    if grouped:
        receipt.update({'initial_time_utc': '2026-08-16T12:00:00Z',
                        'sources': {'rn1': [{'path': f'/test/DFS_VSRT_GRD_KLPS_ODAM_RN1.20260816{hour:02d}00',
                                             'sha256': digest, 'size_bytes': 1}
                                            for hour, digest in zip(range(13, 19), score.EXPECTED_RN1_HASHES)],
                                    'wrfout': {case: []}}})
        histories = []
        for hour in range(12, 19):
            history = folder / f'wrfout_d01_2026-08-16_{hour:02d}:00:00'
            history.write_bytes(f'{case}-{hour}'.encode())
            record = score.identity(history)
            histories.append(record)
        receipt['sources']['wrfout'][case] = histories
    (folder / 'receipt.json').write_text(json.dumps(receipt), encoding='utf-8')
    receipt_record = score.identity(folder / 'receipt.json')
    return receipt_record


def test_reader_requires_seven_bound_histories_and_six_arrays(tmp_path, monkeypatch):
    monkeypatch.setattr(score, '_verify_identity', lambda record: record)
    folder = tmp_path / 'C'
    write_bundle(folder, 'C', 'C', True)
    receipt = json.loads((folder / 'receipt.json').read_text())
    receipt['sources']['wrfout']['C'].pop()
    (folder / 'receipt.json').write_text(json.dumps(receipt), encoding='utf-8')
    with pytest.raises(ValueError, match='seven exact'):
        score.read_case(folder, 'C', 'C')


def test_reader_rejects_missing_lead_array(tmp_path, monkeypatch):
    monkeypatch.setattr(score, '_verify_identity', lambda record: record)
    folder = tmp_path / 'A'
    write_bundle(folder, 'A', 'A', False)
    (folder / 'hour_18_arrays.npz').unlink()
    with pytest.raises(ValueError, match='hour_18_arrays'):
        score.read_case(folder, 'A', 'A')


def test_reader_rejects_missing_required_key_even_with_extra_key(tmp_path, monkeypatch):
    monkeypatch.setattr(score, '_verify_identity', lambda record: record)
    folder = tmp_path / 'A'
    write_bundle(folder, 'A', 'A', False)
    path = folder / 'hour_13_arrays.npz'
    values = make_hourly()[13]
    np.savez_compressed(path, reference=values['reference'], latitude=values['latitude'],
                        longitude=values['longitude'], flat_index_yx=values['flat_index_yx'],
                        unexpected=np.zeros(score.POINTS))
    receipt_path = folder / 'receipt.json'
    receipt = json.loads(receipt_path.read_text())
    receipt['outputs'][path.name] = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                                     'size_bytes': path.stat().st_size}
    receipt_path.write_text(json.dumps(receipt), encoding='utf-8')
    with pytest.raises(ValueError, match='missing required array members'):
        score.read_case(folder, 'A', 'A')


def test_reader_checks_local_array_even_if_receipt_suggests_another_path(tmp_path):
    folder = tmp_path / 'A'
    write_bundle(folder, 'A', 'A', False)
    local = folder / 'hour_13_arrays.npz'
    external = tmp_path / 'receipt_hint.npz'
    external.write_bytes(local.read_bytes())
    with np.load(local, allow_pickle=False) as archive:
        values = {key: np.array(archive[key], copy=True) for key in archive.files}
    values['A'][:] = 0.0
    np.savez_compressed(local, **values)
    receipt_path = folder / 'receipt.json'
    receipt = json.loads(receipt_path.read_text())
    receipt['outputs'][local.name]['path'] = str(external)
    receipt_path.write_text(json.dumps(receipt), encoding='utf-8')
    with pytest.raises(ValueError, match='input identity changed'):
        score.read_case(folder, 'A', 'A')


def test_identity_reader_accepts_canonical_legacy_size_field(tmp_path):
    path = tmp_path / 'pinned.txt'
    path.write_bytes(b'legacy identity')
    record = score.identity(path)
    record['size'] = record.pop('size_bytes')
    assert score._verify_identity(record)['size_bytes'] == len(b'legacy identity')


def test_native_owner_comparability_binds_exact_oldsum_receipts(tmp_path):
    a = {'sha256': 'a' * 64}
    b = {'sha256': 'b' * 64}
    a_original = dict(a)
    gate = {'schema': 'grouped_forecast_oldsum_comparability_v1', 'status': 'PASS',
            'oldsum_receipts': {'A': a, 'B': b},
            'checks': {name: True for name in ('same_initialization', 'same_valid_time_bounds',
                                                'same_precip_fields', 'same_RN1_mapping',
                                                'same_hourly_increment_definition')}}
    path = tmp_path / 'comparability.json'
    path.write_text(json.dumps(gate), encoding='utf-8')
    assert score.check_comparability(path, a_original, b)['sha256']
    gate['oldsum_receipts']['A']['sha256'] = 'c' * 64
    path.write_text(json.dumps(gate), encoding='utf-8')
    with pytest.raises(ValueError, match='binds different'):
        score.check_comparability(path, a_original, b)


def test_existing_output_is_never_overwritten(tmp_path):
    out = tmp_path / 'existing'
    out.mkdir()
    with pytest.raises(FileExistsError):
        score.run({}, tmp_path / 'none.json', out)
