"""Run the source-extracted sedimentation budget with the pinned Intel profile."""
from pathlib import Path
import subprocess
from uuid import uuid4


def test_sedimentation_conservation():
    root = Path(__file__).resolve().parents[1]
    runner = root / "docs/evidence/cp02_sedimentation_conservation_20261109/native/run_intel.sh"
    scratch = root.parent / ("kernel_pytest_" + uuid4().hex)
    result = subprocess.run(["bash", str(runner), str(scratch)], text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    assert result.returncode == 0, result.stdout
    assert result.stdout.count("Baseline failure expected and observed") == 2
    assert result.stdout.count("PASS case           7") == 2
