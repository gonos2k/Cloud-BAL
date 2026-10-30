"""Paired six-hour scoring gates and archived-array replay checks."""
import csv
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'cp02_six_hour_improvement', ROOT / 'tools/cp02_six_hour_improvement.py')
improvement = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(improvement)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def make_runtime(tmp_path, monkeypatch):
    run = tmp_path / 'run'; source = tmp_path / 'source'
    run.mkdir(parents=True); source.mkdir()
    exe, native, boundary = b'fixed executable', b'policy input', b'boundary input'
    monkeypatch.setattr(improvement, 'FIXED_EXE_SHA', hashlib.sha256(exe).hexdigest())
    monkeypatch.setattr(improvement, 'POLICY_INPUT_SHA', hashlib.sha256(native).hexdigest())
    monkeypatch.setattr(improvement, 'BOUNDARY_SHA', hashlib.sha256(boundary).hexdigest())
    monkeypatch.setattr(improvement, 'POLICY_SOURCE_DIR', source)
    baseline_namelist = b'history_end_s=3600\nrun_hours=1\nend_hour=13\n'
    improved_namelist = b'history_end_s=21600\nrun_hours=6\nend_hour=18\n'
    monkeypatch.setattr(improvement, 'ONE_HOUR_NAMELIST_SHA', hashlib.sha256(baseline_namelist).hexdigest())
    monkeypatch.setattr(improvement, 'SIX_HOUR_NAMELIST_SHA', hashlib.sha256(improved_namelist).hexdigest())
    names = ['wrf.exe', 'wrfinput_d01', 'wrfbdy_d01', 'namelist.input'] + [f'input_{i:02d}' for i in range(85)]
    source_before, staged = {}, {}
    for name in names:
        source_content = (exe if name == 'wrf.exe' else native if name == 'wrfinput_d01'
                          else boundary if name == 'wrfbdy_d01' else baseline_namelist
                          if name == 'namelist.input' else f'source:{name}'.encode())
        stage_content = improved_namelist if name == 'namelist.input' else source_content
        (source / name).write_bytes(source_content)
        (run / name).write_bytes(stage_content)
        source_before[name] = hashlib.sha256(source_content).hexdigest()
        staged[name] = hashlib.sha256(stage_content).hexdigest()
    changes = {'history_end_s': ['3600', '21600'], 'run_hours': ['1', '6'], 'end_hour': ['13', '18']}
    evidence_path = tmp_path / 'producer_evidence.json'
    evidence_path.write_text('{}')
    evidence_before = {str(evidence_path): digest(evidence_path)}
    outputs = {}
    for name in improvement.HISTORIES:
        (run / name).write_bytes(name.encode())
        outputs[name] = digest(run / name)
    inputs = {'staged': staged, 'source_policy_bg': source_before, 'source_directory': str(source),
              'input_count': 89, 'case': 'IMPROVED_BG_FIXED',
              'executable_sha256': improvement.FIXED_EXE_SHA,
              'wrfinput_sha256': improvement.POLICY_INPUT_SHA,
              'wrfbdy_sha256': improvement.BOUNDARY_SHA, 'namelist_changes': changes}
    (run / 'inputs.json').write_text(json.dumps(inputs))
    preflight = tmp_path / 'preflight.json'
    preflight.write_text(json.dumps({'status': 'PASS', 'case': 'IMPROVED_BG_FIXED',
        'scratch_directory': str(run), 'source_directory': str(source), 'declared_input_count': 89,
        'input_changes': {'namelist.input': changes}, 'staged_sha256': staged,
        'policy_source_sha256_before': source_before, 'policy_source_sha256_after': source_before,
        'candidate_executable_sha256': improvement.FIXED_EXE_SHA,
        'candidate_native_input_sha256': improvement.POLICY_INPUT_SHA,
        'boundary_sha256': improvement.BOUNDARY_SHA,
        'one_hour_namelist_sha256': source_before['namelist.input'],
        'six_hour_namelist_sha256': staged['namelist.input'],
        'existing_evidence_sha256_before': evidence_before,
        'existing_evidence_sha256_after': evidence_before}))
    receipt = {'status': 'SUCCESS', 'case': 'IMPROVED_BG_FIXED', 'exit': 0,
               'success_marker': True, 'histories_exact': True,
               'staged_inputs_unchanged': True, 'policy_source_inputs_unchanged': True,
               'existing_evidence_unchanged': True, 'histories': improvement.HISTORIES,
               'staged_sha256_after': staged, 'policy_source_sha256_after': source_before,
               'existing_evidence_sha256_after': evidence_before, 'output_sha256': outputs}
    path = run / 'receipt.json'; path.write_text(json.dumps(receipt))
    monkeypatch.setattr(improvement, 'PREFLIGHT_SHA', digest(preflight))
    monkeypatch.setattr(improvement, 'RUNTIME_RECEIPT_SHA', digest(path))
    comparison = tmp_path / 'one_hour_comparison.json'
    comparison.write_text(json.dumps({'time': '2026-08-16_13:00:00',
        'current_path': str(run / improvement.HISTORIES[1]),
        'prior_one_hour_path': str(improvement.POLICY_SOURCE_DIR / improvement.HISTORIES[1]),
        'current_sha256': 'same', 'prior_one_hour_sha256': 'same', 'whole_file_exact': True,
        'fields': {'Times': {'exact': True, 'unequal_values': 0}}}))
    monkeypatch.setattr(improvement, 'ONE_HOUR_COMPARISON', comparison)
    monkeypatch.setattr(improvement, 'ONE_HOUR_COMPARISON_SHA', digest(comparison))
    return run, path, preflight


def test_runtime_gate_pins_executable_input_manifests_and_all_histories(tmp_path, monkeypatch):
    run, receipt, preflight = make_runtime(tmp_path, monkeypatch)
    records = improvement.check_runtime(run, receipt, preflight)
    assert len(records) == 2 + 1 + 1 + 1 + 4 + 89 + 89 + 1 + 7
    (run / 'namelist.input').write_bytes(b'changed namelist')
    with pytest.raises(ValueError, match='staged input hash mismatch: namelist.input'):
        improvement.check_runtime(run, receipt, preflight)


def test_runtime_gate_rejects_wrong_case_and_incomplete_history(tmp_path, monkeypatch):
    run, receipt, preflight = make_runtime(tmp_path, monkeypatch)
    (run / 'wrfinput_d01').write_bytes(b'wrong candidate input')
    with pytest.raises(ValueError, match='staged input hash mismatch: wrfinput_d01'):
        improvement.check_runtime(run, receipt, preflight)
    run, receipt, preflight = make_runtime(tmp_path / 'incomplete', monkeypatch)
    data = json.loads(receipt.read_text())
    data['histories'] = data['histories'][:-1]
    receipt.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='exact 12–18 UTC histories'):
        improvement.check_runtime(run, receipt, preflight)


def test_runtime_gate_rejects_wrong_executable_and_boundary_contract(tmp_path, monkeypatch):
    run, receipt, preflight = make_runtime(tmp_path, monkeypatch)
    inputs = json.loads((run / 'inputs.json').read_text())
    inputs['staged']['wrf.exe'] = '0' * 64
    (run / 'inputs.json').write_text(json.dumps(inputs))
    with pytest.raises(ValueError, match='executable or producer input identity mismatch'):
        improvement.check_runtime(run, receipt, preflight)
    run, receipt, preflight = make_runtime(tmp_path / 'boundary', monkeypatch)
    inputs = json.loads((run / 'inputs.json').read_text())
    inputs['wrfbdy_sha256'] = '0' * 64
    (run / 'inputs.json').write_text(json.dumps(inputs))
    with pytest.raises(ValueError, match='boundary hash differs'):
        improvement.check_runtime(run, receipt, preflight)


def test_synthetic_hour_scores_and_candidate_transitions():
    scorer = improvement.load_scorer()
    values = {
        'reference': np.array([1., 0., 2., 0.]),
        'ORIGINAL': np.array([1., 1., 0., 0.]),
        'CURRENT_HYDRO': np.array([0., 0., 2., 0.]),
        'IMPROVED_BG_FIXED': np.array([1., 0., 2., 1.]),
    }
    categorical, continuous, transitions = improvement.score_hour(13, values, scorer)
    assert len(categorical) == 3 * 6
    assert len(continuous) == 3
    assert len(transitions) == 2 * 6
    assert categorical[0]['valid_utc'] == '2026-08-16T13:00:00Z'
    assert categorical[0]['window_start_utc'] == '2026-08-16T12:00:00Z'
    assert categorical[0]['window_end_utc'] == '2026-08-16T13:00:00Z'
    improved = next(row for row in categorical if row['case'] == 'IMPROVED_BG_FIXED'
                    and row['threshold_mm'] == 1.0)
    assert (improved['hit'], improved['miss'], improved['false_alarm'], improved['CSI']) == (2, 0, 1, pytest.approx(2/3))
    assert set(row['baseline'] for row in transitions) == {'ORIGINAL', 'CURRENT_HYDRO'}
    assert all(row['candidate'] == 'IMPROVED_BG_FIXED' for row in transitions)


def test_time_threshold_csi_summary_counts_improved_tied_and_worse():
    rows = []
    for lead in range(1, 7):
        for threshold in improvement.THRESHOLDS:
            improved = 0.6 if threshold == 0.1 else 0.5 if threshold == 0.5 else 0.3
            rows.extend([
                {'lead_hour': lead, 'case': 'ORIGINAL', 'threshold_mm': threshold, 'CSI': 0.5},
                {'lead_hour': lead, 'case': 'CURRENT_HYDRO', 'threshold_mm': threshold, 'CSI': 0.4},
                {'lead_hour': lead, 'case': 'IMPROVED_BG_FIXED', 'threshold_mm': threshold, 'CSI': improved},
            ])
    summary = improvement.csi_hour_counts(rows)
    original = {row['threshold_mm']: row for row in summary if row['baseline'] == 'ORIGINAL'}
    assert (original[0.1]['improved_hours'], original[0.5]['tied_hours'],
            original[1.0]['worse_hours']) == (6, 6, 6)
    hydro = {row['threshold_mm']: row for row in summary if row['baseline'] == 'CURRENT_HYDRO'}
    assert (hydro[0.1]['improved_hours'], hydro[0.5]['improved_hours'],
            hydro[1.0]['worse_hours']) == (6, 6, 6)


def test_archived_array_replay_is_hash_and_coordinate_bound():
    evidence = []
    arrays, first, _ = improvement.load_archived_arrays(evidence)
    assert len(arrays) == 6
    assert first['reference'].shape == (3688,)
    assert len({row['sha256'] for row in evidence if 'hour_' in row['path']}) == 6
    scorer = improvement.load_scorer()
    archived_csv = list(csv.DictReader((improvement.ARCHIVE_DIR / 'scores/categorical_scores.csv').open()))
    hour_rows = [row for row in archived_csv if row['lead_hour'] == '1' and row['case'] == 'CURRENT_HYDRO']
    for row in hour_rows:
        recomputed = scorer.scores(arrays[13]['CURRENT_HYDRO'], arrays[13]['reference'], float(row['threshold_mm']))
        assert recomputed['hit'] == int(row['hit'])
        assert recomputed['miss'] == int(row['miss'])
        assert recomputed['false_alarm'] == int(row['false_alarm'])
        assert recomputed['correct_dry'] == int(row['correct_dry'])
        assert recomputed['CSI'] == pytest.approx(float(row['CSI']))
    corrupt = {hour: dict(data) for hour, data in arrays.items()}
    corrupt[18]['flat_index_yx'] = corrupt[18]['flat_index_yx'].copy()
    corrupt[18]['flat_index_yx'][-1] += 1
    with pytest.raises(ValueError, match='differs across hours'):
        improvement.verify_baseline_arrays(corrupt)
