"""Fail-closed one-hour scoring gates and the pinned precipitation reader."""
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest
from netCDF4 import Dataset

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / 'docs/evidence/first_hour_zero_rate_20261030/scoring/score_first_hour.py'
spec = importlib.util.spec_from_file_location('first_hour_scorer', PATH)
score = importlib.util.module_from_spec(spec)
spec.loader.exec_module(score)


def make_history(path, hour, *, rainsh=0., bucket=-1., rainnc=0.):
    with Dataset(path, 'w') as d:
        d.createDimension('Time', 1); d.createDimension('DateStrLen', 19)
        d.createDimension('south_north', 2); d.createDimension('west_east', 2)
        v = d.createVariable('Times', 'S1', ('Time', 'DateStrLen'))
        v[0, :] = np.frombuffer(f'2026-08-16_{hour:02d}:00:00'.encode(), dtype='S1')
        d.BUCKET_MM = bucket; d.PREC_ACC_DT = 0.
        for name, value in [('RAINC', 0.), ('RAINNC', rainnc), ('RAINSH', rainsh), ('XLAT', 35.), ('XLONG', 127.)]:
            v = d.createVariable(name, 'f4', ('Time', 'south_north', 'west_east'))
            v[:] = value
            if name.startswith('RAIN'): v.units = 'mm'
            if name == 'RAINSH': v.description = 'shallow cumulus precipitation'


def test_receipt_gates_block_publication(tmp_path):
    output = tmp_path / 'out'
    cases = {name: tmp_path / name for name in score.EXPECTED_INPUT}
    for d in cases.values():
        d.mkdir()
        (d / 'receipt.json').write_text(json.dumps({'exit': 1, 'success_marker': False}))
        (d / 'inputs.json').write_text('{}')
    with pytest.raises(ValueError, match='not complete'):
        score.run(cases, tmp_path, tmp_path, tmp_path, output, tmp_path / 'build.json')
    assert not output.exists()


def test_receipt_detects_history_mutation(tmp_path, monkeypatch):
    ev = score.load_scorer().evaluator
    (tmp_path / 'wrfinput_d01').write_bytes(b'initial')
    initial_sha = ev.sha256(tmp_path / 'wrfinput_d01')
    monkeypatch.setitem(score.EXPECTED_INPUT, 'SHAM', initial_sha)
    (tmp_path / 'inputs.json').write_text(json.dumps({'source': str(tmp_path), 'source_before': {}, 'source_after': {}, 'staged': {'wrfinput_d01': initial_sha}}))
    for h in score.HISTORIES: (tmp_path / h).write_bytes(b'history')
    hashes = {h: ev.sha256(tmp_path / h) for h in score.HISTORIES}
    receipt = {'exit': 0, 'success_marker': True, 'histories_exact': True, 'staged_unchanged': True,
               'source_unchanged': True, 'histories': score.HISTORIES, 'output_sha256': hashes}
    (tmp_path / 'receipt.json').write_text(json.dumps(receipt))
    score.checked_run('SHAM', tmp_path, ev)
    (tmp_path / score.HISTORIES[1]).write_bytes(b'tampered')
    with pytest.raises(ValueError, match='history hash mismatch'):
        score.checked_run('SHAM', tmp_path, ev)


def test_actual_reader_rejects_bad_contract_and_resets(tmp_path):
    ev = score.load_scorer().evaluator
    inventory = {'bucket_contract': {'BUCKET_MM': -1., 'PREC_ACC_DT': 0.}, 'rainsh': {'zero_tolerance_mm': 0.}}
    t12 = datetime(2026, 8, 16, 12, tzinfo=timezone.utc)
    t13 = datetime(2026, 8, 16, 13, tzinfo=timezone.utc)
    before, after = tmp_path / 'before', tmp_path / 'after'
    make_history(before, 12, rainnc=1.)
    make_history(after, 13, rainnc=.5)
    s0 = ev.read_wrf_snapshot(before, t12, inventory)
    s1 = ev.read_wrf_snapshot(after, t13, inventory)
    ev.CASES, ev.COMPARE_HOURS = ('case',), (13,)
    with pytest.raises(RuntimeError, match='reset'):
        ev.check_resets({'case': {12: s0, 13: s1}})
    make_history(after, 13, rainsh=1.)
    with pytest.raises(RuntimeError, match='RAINSH is nonzero'):
        ev.read_wrf_snapshot(after, t13, inventory)
    make_history(after, 13, bucket=100.)
    with pytest.raises(RuntimeError, match='bucket contract'):
        ev.read_wrf_snapshot(after, t13, inventory)
    with pytest.raises(RuntimeError, match='Times mismatch'):
        ev.read_wrf_snapshot(before, t13, inventory)


def test_pair_input_identity_and_categorical_transitions():
    staged = {name: {'wrf.exe': name, 'wrfinput_d01': 'same', 'namelist.input': 'same'} for name in score.EXPECTED_INPUT}
    for name in ('SHAM', 'BASE_H', 'BASE_ORIGINAL'): staged[name]['wrf.exe'] = score.BASE_EXE_SHA
    for name in ('FIX_H', 'FIX_ORIGINAL'): staged[name]['wrf.exe'] = score.FIX_EXE_SHA
    score.verify_pair_inputs(staged)
    staged['FIX_H']['wrfinput_d01'] = 'different'
    with pytest.raises(ValueError, match='staged inputs differ'):
        score.verify_pair_inputs(staged)
    old = score.load_scorer()
    ref = np.array([2., 2., 0., 0.])
    first = np.array([2., 0., 2., 0.]); second = np.array([0., 2., 0., 2.])
    assert old.scores(first, ref, 1.)['CSI'] == pytest.approx(1/3)
    assert old.transitions(first, second, ref, 1.) == {'hit_gains': 1, 'hit_losses': 1, 'false_alarm_gains': 1, 'false_alarm_losses': 1}


@pytest.mark.parametrize('fault', ['swapped', 'arbitrary', 'sham_input', 'build_receipt'])
def test_cohort_identity_failures_leave_no_output(tmp_path, monkeypatch, fault):
    ev = score.load_scorer().evaluator
    import hashlib
    digest = lambda data: hashlib.sha256(data).hexdigest()
    base, fix = b'known base executable', b'known fixed executable'
    monkeypatch.setattr(score, 'BASE_EXE_SHA', digest(base))
    monkeypatch.setattr(score, 'FIX_EXE_SHA', digest(fix))
    initial = b'identical initial field'
    for name in score.EXPECTED_INPUT:
        monkeypatch.setitem(score.EXPECTED_INPUT, name, digest(initial))
    receipt = {'host_unchanged': True, 'arms': {name: {'exe': sha, 'compile': {'exit': 0}, 'link': {'exit': 0}}
              for name, sha in [('BASE', digest(base)), ('FIX', digest(fix))]}}
    build = tmp_path / 'build.json'
    build.write_text(json.dumps(receipt))
    monkeypatch.setattr(score, 'BUILD_RECEIPT_SHA', ev.sha256(build))
    if fault == 'build_receipt': build.write_text(build.read_text() + ' ')
    source = tmp_path / 'source'; source.mkdir()
    cases = {}
    for name in score.EXPECTED_INPUT:
        directory = tmp_path / name; directory.mkdir(); cases[name] = directory
        exe = base if name in ('SHAM', 'BASE_H', 'BASE_ORIGINAL') else fix
        if fault == 'swapped' and name == 'FIX_H': exe = base
        if fault == 'arbitrary' and name == 'BASE_H': exe = b'arbitrary'
        namelist = b'changed' if fault == 'sham_input' and name == 'SHAM' else b'common'
        for filename, data in [('wrf.exe', exe), ('wrfinput_d01', initial), ('namelist.input', namelist)]:
            (directory / filename).write_bytes(data)
        staged = {f: ev.sha256(directory / f) for f in ('wrf.exe', 'wrfinput_d01', 'namelist.input')}
        (directory / 'inputs.json').write_text(json.dumps({'source': str(source), 'source_before': {}, 'source_after': {}, 'staged': staged}))
        for history in score.HISTORIES: (directory / history).write_bytes(b'history')
        hashes = {h: ev.sha256(directory / h) for h in score.HISTORIES}
        (directory / 'receipt.json').write_text(json.dumps({'exit': 0, 'success_marker': True, 'histories_exact': True,
            'staged_unchanged': True, 'source_unchanged': True, 'histories': score.HISTORIES, 'output_sha256': hashes}))
    output = tmp_path / 'output'
    expected = {'swapped': 'executable identity', 'arbitrary': 'executable identity',
                'sham_input': 'staged inputs differ', 'build_receipt': 'build receipt hash mismatch'}[fault]
    with pytest.raises(ValueError, match=expected):
        score.run(cases, tmp_path, tmp_path, tmp_path, output, build)
    assert not output.exists()
