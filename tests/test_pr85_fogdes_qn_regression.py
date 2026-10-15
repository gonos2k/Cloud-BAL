#!/usr/bin/env python3
"""Run the source-bound PR85 paired FogDES sedimentation regression."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_pr85_fogdes_qn_source_form() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools/pr85_fogdes_qn_regression.py")],
        cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        check=False,
    )
    assert result.returncode == 0, result.stdout
    assert "PR85 source-form FogDES paired Stokes cases PASS" in result.stdout
    assert '"O0"' in result.stdout and '"O2"' in result.stdout


if __name__ == "__main__":
    test_pr85_fogdes_qn_source_form()
    print("PR85 FogDES Q/N source-form regression PASS")
