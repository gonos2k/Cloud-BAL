import json
from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime'))
import score_new_histories as scorer


def make_histories(folder):
    rows = []
    for hour, name in zip(range(12, 19), scorer.HISTORY_NAMES):
        path = folder / name
        path.write_bytes(f'history-{hour}'.encode())
        rows.append({
            'path': str(path), 'sha256': scorer.sha256(path), 'size_bytes': path.stat().st_size,
            'valid_utc': datetime(2026, 8, 16, hour, tzinfo=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        })
    return rows


def make_run(folder, rows):
    return {
        'schema': 'cp02_grouped_six_hour_run_v1', 'status': 'PASS', 'case': 'C',
        'variant': 'GROUPED', 'initialization': 'A',
        'initial_time_utc': '2026-08-16T12:00:00Z', 'end_time_utc': '2026-08-16T18:00:00Z',
        'histories': rows,
    }


def test_rejects_incomplete_history_coverage(tmp_path):
    rows = make_histories(tmp_path)
    rows.pop(3)
    with pytest.raises(ValueError, match='exactly seven histories'):
        scorer.validate_histories('C', tmp_path, make_run(tmp_path, rows))


def test_rejects_history_hash_mismatch(tmp_path):
    rows = make_histories(tmp_path)
    rows[0]['sha256'] = '0' * 64
    with pytest.raises(ValueError, match='identity differs'):
        scorer.validate_histories('C', tmp_path, make_run(tmp_path, rows))


def test_rejects_nonpassing_run_before_scoring(tmp_path):
    rows = make_histories(tmp_path)
    receipt = make_run(tmp_path, rows)
    receipt['status'] = 'FAIL'
    with pytest.raises(ValueError, match='passing grouped six-hour run'):
        scorer.validate_histories('C', tmp_path, receipt)


def test_incomplete_run_cannot_publish_or_invoke_scorer(tmp_path, monkeypatch):
    output = tmp_path / 'new-cache'

    def reject_incomplete(case, run_dir):
        raise ValueError(f'{case} must have exactly seven histories')

    def scorer_must_not_load():
        pytest.fail('canonical scorer invoked before complete history validation')

    monkeypatch.setattr(scorer, 'validate_run', reject_incomplete)
    monkeypatch.setattr(scorer, 'load_scorer', scorer_must_not_load)
    with pytest.raises(ValueError, match='exactly seven histories'):
        scorer.publish_score_cache(tmp_path / 'C', tmp_path / 'D', output)
    assert not output.exists()
