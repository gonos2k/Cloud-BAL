"""Verify default PR82 provenance against the native host installation."""
from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_default_provenance_sources_exist_on_native_host():
    runner_path = ROOT / "tests/run_pr82_same13_native_initialization.py"
    spec = importlib.util.spec_from_file_location("pr82_native_runner", runner_path)
    assert spec is not None and spec.loader is not None
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)

    paths = runner.provenance_paths()
    assert all(path.is_file() for path in paths.values())

