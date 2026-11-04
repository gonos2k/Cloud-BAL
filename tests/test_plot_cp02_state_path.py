"""Renderer must reject changed scientific inputs before publishing figures."""
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("state_plot", ROOT / "tools/plot_cp02_state_path.py")
plot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(plot)
COHORTS = ROOT / "docs/evidence/cp02_state_path_20261104/cohorts"


def test_changed_score_does_not_publish_or_modify_existing_output(tmp_path):
    inputs = tmp_path / "cohorts"
    shutil.copytree(COHORTS, inputs)
    score = inputs / "paired_scores.csv"
    score.write_bytes(score.read_bytes().replace(b"0.3907766990291262", b"0.4907766990291262", 1))
    output = tmp_path / "figures"
    with pytest.raises(ValueError, match="differs from receipt"):
        plot.render(inputs, output)
    assert not output.exists()
    output.mkdir()
    sentinel = output / "existing.png"
    sentinel.write_bytes(b"preserve")
    with pytest.raises(FileExistsError):
        plot.render(inputs, output)
    assert sentinel.read_bytes() == b"preserve"


def test_dangling_destination_is_preserved(tmp_path):
    output = tmp_path / "figures"
    output.symlink_to(tmp_path / "absent")
    with pytest.raises(FileExistsError):
        plot.render(COHORTS, output)
    assert output.is_symlink()


def test_complete_score_scope_required(tmp_path):
    with pytest.raises(ValueError, match="2 leads by 6"):
        plot.score_figure([], tmp_path)


def test_caption_requires_actual_contingency_support(tmp_path):
    receipt = json.loads((COHORTS / "receipt.json").read_text())
    scores = plot.bound_rows(COHORTS, receipt, "paired_scores.csv")
    points = plot.bound_rows(COHORTS, receipt, "selected_points.csv")
    row = next(r for r in scores if r["lead_hour"] == "2" and float(r["threshold_mm"]) == 5)
    row["FIX_hit"] = str(int(row["FIX_hit"]) + 1)
    with pytest.raises(ValueError, match="no longer supports"):
        plot.false_alarm_figure(points, scores, tmp_path)
    assert not list(tmp_path.glob("*.png"))
