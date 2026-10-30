"""Small path-normalization checks for the independent byte replay."""

import importlib.util
import json
import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'recount_cp02_weak_strong_balance', ROOT / 'tools/recount_cp02_weak_strong_balance.py')
recount = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(recount)


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
