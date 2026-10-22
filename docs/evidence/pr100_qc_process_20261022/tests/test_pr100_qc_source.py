from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re

import pytest


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/pr100_qc_source_anchors.txt"
COMPOSITION = ROOT / "docs/evidence/pr93_qc_chain_20261020/qc_vertical_composition.json"
MODULE = ROOT / "tools/pr100_qc_source.py"


def load_module():
    spec = importlib.util.spec_from_file_location("pr100_qc_source", MODULE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def qc_assignments(source: str) -> list[str]:
    return re.findall(r"^[ \t]*qci\(i,k,1\)[ \t]*=.*$", source, re.MULTILINE)


def test_support_is_the_pinned_composition_selection():
    points = load_module().support_points(json.loads(COMPOSITION.read_text()))
    assert len(points) == 613
    assert len({(j, i) for k, j, i in points}) == 16
    assert min(k for k, _, _ in points) == 1
    assert max(k for k, _, _ in points) == 39


def test_pr100_hooks_preserve_qc_assignments(monkeypatch):
    source = FIXTURE.read_text()
    module = load_module()
    monkeypatch.setattr(module.compact, "prepare", lambda text: text)
    generated, points = module.prepare(source, json.loads(COMPOSITION.read_text()))

    assert qc_assignments(generated) == qc_assignments(source)
    assert generated.count("'COLD_COMMIT'") == 1
    assert generated.count("'WARM_COMMIT'") == 1
    assert generated.count("'ENTRY'") == 1
    assert generated.count("'EXIT'") == 1
    assert len(points) == 613
    for group in ("rain_ng_q_process(1)", "rain_aut_q_process(1)",
                  "rain_q_process_request(1)", "rain_warm_q_process(1)"):
        assert group in generated
    assert "transfer(before,0)" in generated and "transfer(after,0)" in generated


def test_pr100_transform_rejects_missing_anchor(monkeypatch):
    source = FIXTURE.read_text().replace("            qci(i,k,1)=rain_warm_q_after(1)\n", "", 1)
    module = load_module()
    monkeypatch.setattr(module.compact, "prepare", lambda text: text)

    with pytest.raises(ValueError, match="QC warm commit"):
        module.prepare(source, json.loads(COMPOSITION.read_text()))
