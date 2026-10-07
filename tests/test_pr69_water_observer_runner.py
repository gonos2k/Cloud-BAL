#!/usr/bin/env python3
"""Guard tests for the injected PR69 observer run wrapper."""
from __future__ import annotations

import json
import sys
import tempfile
import hashlib
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

from pr69_run_water_observer import REQUIRED_OUTPUTS, run  # noqa: E402


def _fixture(root: Path) -> tuple[Path, Path, Path]:
    source = root / "source.dat"
    source.write_bytes(b"immutable input")
    executable = root / "wrf.exe"
    executable.write_bytes(b"research executable")
    receipt = root / "inputs.json"
    receipt.write_text(json.dumps({"inputs": [{"path": str(source),
                                                  "sha256_before": hashlib.sha256(source.read_bytes()).hexdigest()}]}))
    return receipt, executable, root / "run"


def _successful_fake_run(*, symlink_output: bool = False, replace_executable: bool = False,
                         symlink_receipt: bool = False):
    def fake_run(_argv, *, cwd, check):
        run_dir = Path(cwd)
        assert check is False
        for name in REQUIRED_OUTPUTS:
            (run_dir / name).write_text("captured\n")
        if symlink_output:
            target = run_dir / "target.txt"
            target.write_text("target\n")
            (run_dir / "pr69_water.raw").unlink()
            (run_dir / "pr69_water.raw").symlink_to(target)
        if replace_executable:
            target = run_dir / "replacement.exe"
            target.write_text("replacement\n")
            (run_dir / "wrf.exe").unlink()
            (run_dir / "wrf.exe").symlink_to(target)
        if symlink_receipt:
            (run_dir / "run_receipt.json").symlink_to(run_dir / "candidate_run.log")
        class Result:
            returncode = 0
        return Result()
    return fake_run


def test_complete_regular_run_passes() -> None:
    with tempfile.TemporaryDirectory() as directory:
        receipt, executable, run_dir = _fixture(Path(directory))
        with patch("pr69_run_water_observer.subprocess.run", _successful_fake_run()):
            result = run(receipt, executable, run_dir)
    assert result["returncode"] == 0
    assert result["input_integrity"] == "PASS"
    assert result["output_isolation"] == "PASS"


def test_missing_required_capture_fails_closed() -> None:
    with tempfile.TemporaryDirectory() as directory:
        receipt, executable, run_dir = _fixture(Path(directory))
        def fake_run(_argv, *, cwd, check):
            for name in REQUIRED_OUTPUTS - {"pr69_water.raw"}:
                (Path(cwd) / name).write_text("captured\n")
            class Result:
                returncode = 0
            return Result()
        with patch("pr69_run_water_observer.subprocess.run", fake_run):
            result = run(receipt, executable, run_dir)
    assert result["output_isolation"] == "FAIL"


def test_symlink_output_fails_closed() -> None:
    with tempfile.TemporaryDirectory() as directory:
        receipt, executable, run_dir = _fixture(Path(directory))
        with patch("pr69_run_water_observer.subprocess.run", _successful_fake_run(symlink_output=True)):
            result = run(receipt, executable, run_dir)
    assert result["output_isolation"] == "FAIL"


def test_replaced_executable_fails_closed() -> None:
    with tempfile.TemporaryDirectory() as directory:
        receipt, executable, run_dir = _fixture(Path(directory))
        with patch("pr69_run_water_observer.subprocess.run", _successful_fake_run(replace_executable=True)):
            result = run(receipt, executable, run_dir)
    assert result["input_integrity"] == "FAIL"


def test_executable_created_receipt_symlink_is_never_followed() -> None:
    with tempfile.TemporaryDirectory() as directory:
        receipt, executable, run_dir = _fixture(Path(directory))
        with patch("pr69_run_water_observer.subprocess.run",
                   _successful_fake_run(symlink_receipt=True)):
            try:
                run(receipt, executable, run_dir)
            except FileExistsError:
                pass
            else:
                raise AssertionError("existing receipt symlink must prevent receipt creation")
        assert (run_dir / "run_receipt.json").is_symlink()


def test_receipt_with_only_executable_is_rejected() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        receipt, executable, run_dir = _fixture(root)
        receipt.write_text(json.dumps({"inputs": [{"path": str(executable),
                                                    "sha256_before": hashlib.sha256(executable.read_bytes()).hexdigest()}]}))
        try:
            run(receipt, executable, run_dir)
        except ValueError as error:
            assert "physical run inputs" in str(error)
        else:
            raise AssertionError("executable-only receipt must fail closed")


if __name__ == "__main__":
    test_complete_regular_run_passes()
    test_missing_required_capture_fails_closed()
    test_symlink_output_fails_closed()
    test_replaced_executable_fails_closed()
    test_executable_created_receipt_symlink_is_never_followed()
    test_receipt_with_only_executable_is_rejected()
    print("PR69 observer runner guard tests passed")
