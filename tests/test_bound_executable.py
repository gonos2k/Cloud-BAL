#!/usr/bin/env python3
"""Focused tests for hash-pinned sealed-memfd producer launches."""

from __future__ import annotations

import errno
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
TOOLS = PROJECT / "tools"
RUNNER = TOOLS / "run_bound_executable.py"
sys.path.insert(0, str(TOOLS))

import run_bound_executable  # noqa: E402
from run_bound_executable import BindingError, bind_executable  # noqa: E402


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def invoke(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RUNNER), *arguments],
        text=True,
        capture_output=True,
        check=False,
    )


def assert_rejected(result: subprocess.CompletedProcess[str], fragment: str) -> None:
    assert result.returncode == 2, result
    assert "BOUND_EXECUTABLE_REJECTED:" in result.stderr
    assert fragment in result.stderr, result.stderr


def test_valid_launch_and_sha256_manifest() -> None:
    with tempfile.TemporaryDirectory(prefix="cloud-bal-bound-") as directory:
        root = Path(directory)
        executable = root / "producer"
        shutil.copy2("/bin/echo", executable)
        expected = root / "executable.sha256"
        expected.write_text(f"{digest(executable)}  {executable}\n", encoding="ascii")

        result = invoke(
            "--sha256-file",
            str(expected),
            str(executable),
            "--",
            "bound-launch-pass",
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout == "bound-launch-pass\n"
        assert "BOUND_EXECUTABLE_READY method=sealed_memfd" in result.stderr
        assert digest(executable) in result.stderr


def test_missing_and_tampered_executable_fail_closed() -> None:
    with tempfile.TemporaryDirectory(prefix="cloud-bal-bound-") as directory:
        root = Path(directory)
        missing = root / "missing"
        result = invoke("--expected-sha256", "0" * 64, str(missing))
        assert_rejected(result, "cannot open executable")

        executable = root / "producer"
        shutil.copy2("/bin/echo", executable)
        expected = digest(executable)
        contents = bytearray(executable.read_bytes())
        contents[len(contents) // 2] ^= 1
        executable.write_bytes(contents)
        result = invoke("--expected-sha256", expected, str(executable))
        assert_rejected(result, "SHA-256 mismatch")


def test_tampered_expected_manifest_and_symlink_fail_closed() -> None:
    with tempfile.TemporaryDirectory(prefix="cloud-bal-bound-") as directory:
        root = Path(directory)
        executable = root / "producer"
        shutil.copy2("/bin/echo", executable)
        expected = root / "executable.sha256"
        expected.write_text("not-a-digest\n", encoding="ascii")
        result = invoke("--sha256-file", str(expected), str(executable))
        assert_rejected(result, "invalid expected SHA-256")

        link = root / "producer-link"
        link.symlink_to(executable)
        result = invoke("--expected-sha256", digest(executable), str(link))
        assert_rejected(result, "cannot open executable")


def test_sealed_memfd_rejects_writes() -> None:
    with tempfile.TemporaryDirectory(prefix="cloud-bal-bound-") as directory:
        executable = Path(directory) / "producer"
        shutil.copy2("/bin/echo", executable)
        fd = bind_executable(executable, digest(executable))
        try:
            try:
                os.write(fd, b"tamper")
            except OSError as exc:
                assert exc.errno == errno.EPERM, exc
            else:
                raise AssertionError("sealed executable memfd accepted a write")
        finally:
            os.close(fd)


def test_destination_mutation_before_seal_is_rejected() -> None:
    with tempfile.TemporaryDirectory(prefix="cloud-bal-bound-") as directory:
        executable = Path(directory) / "producer"
        shutil.copy2("/bin/echo", executable)
        expected = digest(executable)
        original_fcntl = run_bound_executable.fcntl.fcntl
        mutated = False

        def mutate_before_seal(fd: int, command: int, *arguments: object) -> int:
            nonlocal mutated
            if command == run_bound_executable.fcntl.F_ADD_SEALS and not mutated:
                mutated = True
                os.lseek(fd, 0, os.SEEK_SET)
                os.write(fd, b"X")
            return original_fcntl(fd, command, *arguments)

        run_bound_executable.fcntl.fcntl = mutate_before_seal
        try:
            try:
                bind_executable(executable, expected)
            except BindingError as exc:
                assert "SHA-256 mismatch" in str(exc), exc
            else:
                raise AssertionError("destination mutation before seal was accepted")
        finally:
            run_bound_executable.fcntl.fcntl = original_fcntl
        assert mutated


def test_replacement_after_binding_executes_bound_bytes() -> None:
    """A pathname swap after binding cannot change the bytes that exec sees."""

    with tempfile.TemporaryDirectory(prefix="cloud-bal-bound-") as directory:
        root = Path(directory)
        executable = root / "producer"
        replacement = root / "replacement"
        shutil.copy2("/bin/echo", executable)
        shutil.copy2("/bin/false", replacement)
        expected = digest(executable)
        child_env = os.environ.copy()
        child_env["PYTHONPATH"] = os.pathsep.join(
            [str(TOOLS), child_env.get("PYTHONPATH", "")]
        )
        child = """
import os
import sys
from pathlib import Path

from run_bound_executable import bind_executable, exec_bound

executable = Path(sys.argv[1])
replacement = Path(sys.argv[3])
fd = bind_executable(executable, sys.argv[2])
executable.unlink()
executable.symlink_to(replacement)
exec_bound(fd, [executable.name, "replacement-race-pass"])
"""
        result = subprocess.run(
            [sys.executable, "-c", child, str(executable), expected, str(replacement)],
            text=True,
            capture_output=True,
            env=child_env,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout == "replacement-race-pass\n"


def main() -> None:
    test_valid_launch_and_sha256_manifest()
    test_missing_and_tampered_executable_fail_closed()
    test_tampered_expected_manifest_and_symlink_fail_closed()
    test_sealed_memfd_rejects_writes()
    test_destination_mutation_before_seal_is_rejected()
    test_replacement_after_binding_executes_bound_bytes()
    print("Bound executable tests passed")


if __name__ == "__main__":
    main()
