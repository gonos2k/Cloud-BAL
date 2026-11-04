from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tools/plot_cp02_rain_dm065.py'
spec = importlib.util.spec_from_file_location('dm065_plots', SCRIPT)
plot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plot)
ANALYSIS = plot.FOLLOWUP / 'analysis_dm065'
PLAN = plot.FOLLOWUP / 'evaluation_plan.json'


def test_real_scoring_matches_independent_array_recount_and_scope():
    hourly, scores, receipt = plot.load_verified(ANALYSIS, PLAN, plot.PLAN_SHA)
    assert len(scores) == 144 and len(hourly) == 6
    assert receipt['rows'] == {'categorical': 144, 'continuous': 24, 'constraints': 26}
    for hour, values in hourly.items():
        assert len(values['reference']) == 3688
        assert len(np.unique(values['flat_index_yx'])) == 3688
    rain_max, delta_max = plot.map_scales(hourly)
    assert all(np.max(v[key]) <= rain_max for v in hourly.values() for key in ('reference', *plot.CASES))
    for v in hourly.values():
        for a, b in ((plot.BASE, 'ORIGINAL'), (plot.CASES[2], 'ORIGINAL'), (plot.CANDIDATE, 'ORIGINAL'), (plot.CANDIDATE, plot.BASE)):
            assert np.max(np.abs(v[a] - v[b])) <= delta_max


def test_tampered_input_and_score_rejected_without_touching_output(tmp_path):
    analysis = tmp_path / 'analysis'; shutil.copytree(ANALYSIS, analysis)
    output = tmp_path / 'figures'; output.mkdir(); sentinel = output / 'existing.png'; sentinel.write_bytes(b'keep existing output')
    score = analysis / 'categorical_scores.csv'
    with score.open(newline='', encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream))
    rows[0]['CSI'] = '0.123456789'
    with score.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0]); writer.writeheader(); writer.writerows(rows)
    with pytest.raises(ValueError, match='input differs from receipt'):
        plot.render(analysis, PLAN, plot.PLAN_SHA, output)
    assert sentinel.read_bytes() == b'keep existing output' and list(output.iterdir()) == [sentinel]
    receipt_path = analysis / 'receipt.json'; receipt = json.loads(receipt_path.read_text())
    receipt['outputs'][score.name]['sha256'] = plot.sha(score); receipt['outputs'][score.name]['size_bytes'] = score.stat().st_size
    receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match='CSI table differs'):
        plot.render(analysis, PLAN, plot.PLAN_SHA, output)
    assert sentinel.read_bytes() == b'keep existing output' and list(output.iterdir()) == [sentinel]


def test_wrong_frozen_plan_is_rejected(tmp_path):
    bad = tmp_path / 'plan.json'; bad.write_text(PLAN.read_text() + ' ')
    with pytest.raises(ValueError, match='plan identity'):
        plot.load_verified(ANALYSIS, bad, plot.PLAN_SHA)
