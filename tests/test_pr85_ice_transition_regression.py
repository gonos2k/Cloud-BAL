#!/usr/bin/env python3
"""Run the pinned-Intel source-form KDM6 ice transition regression."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_pr85_ice_transition_source_form() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools/pr85_ice_transition_regression.py")],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert result.returncode == 0, result.stdout
    assert "PR85 source-form ice transition cases PASS" in result.stdout
    assert "CASE lambda_min" in result.stdout
    assert "CASE inside reachable interval" in result.stdout
    assert "CASE above reachable endpoint" in result.stdout


if __name__ == "__main__":
    test_pr85_ice_transition_source_form()
    print("PR85 ice transition regression test PASS")
