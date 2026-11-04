"""Independent recount contract and byte replay checks."""

import csv
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'recount_cp02_weak_strong_balance', ROOT / 'tools/recount_cp02_weak_strong_balance.py')
recount = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(recount)
ANALYSIS = ROOT / 'docs/evidence/weak_strong_balance_20261030/analysis'


def copy_analysis(destination):
    shutil.copytree(ANALYSIS, destination)
    return destination


def refresh_receipt(analysis, *names):
    receipt_path = analysis / 'receipt.json'
    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    for name in names:
        path = analysis / name
        receipt['analysis_outputs'][name] = {
            'size_bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    receipt_path.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')


def run_cli(analysis, output):
    return subprocess.run(
        [sys.executable, str(ROOT / 'tools/recount_cp02_weak_strong_balance.py'),
         '--analysis', str(analysis), '--output', str(output)],
        capture_output=True, text=True, check=False)


def test_recount_accepts_the_frozen_analysis_with_saved_arrays():
    result = recount.recount(ANALYSIS)
    assert result['status'] == 'PASS'
    assert result['independently_recounted_rows'] == {
        'categorical': 432, 'continuous': 72, 'transitions': 396, 'admission': 152,
        'observation_band_transitions': 1980, 'observed_forecast_bins': 3300,
    }


def test_recount_rejects_threshold_lists_outside_the_fixed_contract():
    threshold_lists = (None, [], [0.1, 0.5, 1.0, 2.5, 5.0],
                       [0.5, 0.1, 1.0, 2.5, 5.0, 10.0],
                       [0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 10.0],
                       [0.1, 0.5, 1.0, 5.0, 10.0])
    with tempfile.TemporaryDirectory() as temp_dir:
        for index, thresholds in enumerate(threshold_lists):
            analysis = copy_analysis(Path(temp_dir) / str(index))
            receipt_path = analysis / 'receipt.json'
            receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
            receipt['thresholds_mm'] = thresholds
            receipt_path.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
            try:
                recount.recount(analysis)
            except ValueError as error:
                assert 'threshold scope' in str(error)
            else:
                raise AssertionError(f'accepted invalid threshold list: {thresholds!r}')


def test_recount_guards_missing_and_duplicate_mandatory_table_rows():
    with tempfile.TemporaryDirectory() as temp_dir:
        for mutation in ('missing', 'duplicate'):
            analysis = copy_analysis(Path(temp_dir) / mutation)
            name = 'continuous_scores.csv'
            path = analysis / name
            with path.open(encoding='utf-8', newline='') as stream:
                rows = list(csv.reader(stream))
            changed_rows = rows[:-1] if mutation == 'missing' else rows + [rows[-1]]
            with path.open('w', encoding='utf-8', newline='') as stream:
                writer = csv.writer(stream, lineterminator='\n')
                writer.writerows(changed_rows)
            refresh_receipt(analysis, name)
            try:
                recount.recount(analysis)
            except ValueError as error:
                assert 'continuous score row count mismatch' in str(error)
                expected_rows = 71 if mutation == 'missing' else 73
                assert f'found {expected_rows}' in str(error)
            else:
                raise AssertionError(f'accepted a {mutation} continuous-score row')


def test_recount_rejects_duplicate_admission_key_with_unchanged_row_count():
    with tempfile.TemporaryDirectory() as temp_dir:
        analysis = copy_analysis(Path(temp_dir) / 'analysis')
        name = 'admission_constraints.csv'
        path = analysis / name
        with path.open(encoding='utf-8', newline='') as stream:
            rows = list(csv.reader(stream))
        duplicate_key = ['GATE_G50_90', 'weak_CSI_at_least_ORIGINAL', '6', '0.1']
        duplicate_index = next(index for index, row in enumerate(rows)
                               if row[:4] == duplicate_key)
        rows[duplicate_index] = rows[1]
        with path.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.writer(stream, lineterminator='\n')
            writer.writerows(rows)
        refresh_receipt(analysis, name)
        try:
            recount.recount(analysis)
        except ValueError as error:
            assert 'admission table does not form the complete constraint grid' in str(error)
        else:
            raise AssertionError('accepted a duplicate admission key with 152 physical rows')


def test_cli_rejects_empty_threshold_and_transition_archives_without_output():
    with tempfile.TemporaryDirectory() as temp_dir:
        analysis = copy_analysis(Path(temp_dir) / 'analysis')
        receipt_path = analysis / 'receipt.json'
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        receipt['thresholds_mm'] = []
        changed = []
        for hour in range(13, 19):
            name = f'hour_{hour}_transitions_vs_original.npz'
            with (analysis / name).open('wb') as stream:
                np.savez_compressed(stream)
            changed.append(name)
        for name in changed:
            path = analysis / name
            receipt['analysis_outputs'][name] = {
                'size_bytes': path.stat().st_size,
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        receipt_path.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
        output = Path(temp_dir) / 'audit.json'
        result = run_cli(analysis, output)
        assert result.returncode != 0
        assert 'threshold scope' in result.stderr
        assert not output.exists()


def test_replay_resolves_relative_runtime_and_plan_before_scoring(monkeypatch):
    with tempfile.TemporaryDirectory(dir=ROOT) as temp_dir:
        root = Path(temp_dir).resolve()
        analysis = root / 'analysis'
        analysis.mkdir()
        (analysis / 'receipt.json').write_text(json.dumps({'winner': None}), encoding='utf-8')
        (analysis / 'data.csv').write_text('ok\n', encoding='utf-8')
        runtime = root / 'runtime'
        plan = root / 'plan.json'
        relative_runtime = Path(os.path.relpath(runtime, Path.cwd()))
        relative_analysis = Path(os.path.relpath(analysis, Path.cwd()))
        relative_plan = Path(os.path.relpath(plan, Path.cwd()))
        seen = {}

        class FakeScorer:
            @staticmethod
            def score(runtime_arg, output_arg, plan_arg, plan_sha256):
                seen.update(runtime=runtime_arg, output=output_arg, plan=plan_arg,
                            plan_sha256=plan_sha256)
                output_arg.mkdir(parents=True)
                (output_arg / 'receipt.json').write_text(
                    json.dumps({'winner': None}), encoding='utf-8')
                (output_arg / 'data.csv').write_text('ok\n', encoding='utf-8')

        monkeypatch.setattr(recount, 'load_scorer', lambda: FakeScorer())
        result = recount.replay(relative_runtime, relative_analysis, relative_plan, 'frozen-plan')

    assert result['status'] == 'PASS'
    assert seen['runtime'] == runtime
    assert seen['plan'] == plan
    assert seen['output'].is_absolute()
    assert seen['plan_sha256'] == 'frozen-plan'


def test_cli_recounts_without_replay_only_arguments(tmp_path):
    output = tmp_path / 'audit.json'
    result = run_cli(ANALYSIS, output)
    assert result.returncode == 0, result.stderr
    assert json.loads(output.read_text())['status'] == 'PASS'


def test_cli_rejects_replay_only_options_without_replay_and_missing_plan_hash(tmp_path):
    for index, options in enumerate((
            ['--plan-sha256', 'unused'], ['--plan', 'unused.json'],
            ['--runtime-dir', 'unused'], ['--replay'])):
        output = tmp_path / f'audit_{index}.json'
        result = subprocess.run(
            [sys.executable, str(ROOT / 'tools/recount_cp02_weak_strong_balance.py'),
             '--analysis', str(ANALYSIS), '--output', str(output), *options],
            capture_output=True, text=True, check=False)
        assert result.returncode == 2
        assert ('required with --replay' if options == ['--replay'] else 'require --replay') in result.stderr
        assert not output.exists()
