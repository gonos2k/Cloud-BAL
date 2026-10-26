from __future__ import annotations

import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools/pr98_boundary_audit.py"
SPEC = importlib.util.spec_from_file_location("pr98_boundary_audit", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_snapshot_schedule_comes_from_pinned_frozen_runner() -> None:
    runner = MODULE.load_frozen_runner()
    schedule = runner.snapshot_schedule(640)
    assert tuple(sorted(step * 20 for step in schedule)) == (20, 60, 300, 320, 480, 500, 600, 640)



def test_all_frozen_runner_snapshots_are_mandatory() -> None:
    runner = MODULE.load_frozen_runner()
    schedule = runner.snapshot_schedule(640)
    labels = set(schedule.values())
    assert MODULE.missing_snapshot_labels({"snapshots": {label: {} for label in labels}}, schedule) == []
    labels.remove("320s")
    assert MODULE.missing_snapshot_labels({"snapshots": {label: {} for label in labels}}, schedule) == ["320s"]
