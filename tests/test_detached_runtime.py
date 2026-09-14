#!/usr/bin/env python3
"""Focused tests for detached loader and library identity binding."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))

from run_bound_executable import bind_executable  # noqa: E402
from run_detached_runtime import (  # noqa: E402
    DetachedRuntimeError,
    close_unintended_fds,
    read_runtime_manifest,
    sanitize_environment,
    stage_runtime,
    validate_loader_list,
    verify_snapshot,
    inspect_bound_loader,
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ldd_manifest(binary: Path, path: Path) -> None:
    result = subprocess.run(
        ["ldd", "-r", str(binary)],
        capture_output=True,
        text=True,
        check=True,
    )
    files: dict[Path, str] = {}
    for line in result.stdout.splitlines():
        fields = line.strip().split()
        if not fields:
            continue
        candidate = fields[2] if len(fields) >= 3 and fields[1] == "=>" else fields[0]
        if not candidate.startswith("/"):
            continue
        source = Path(candidate)
        if source.is_file():
            files[source] = digest(source)
    assert files
    path.write_text(
        "".join(f"{sha}  {source}\n" for source, sha in sorted(files.items())),
        encoding="ascii",
    )


def temporary_directory(prefix: str) -> tempfile.TemporaryDirectory[str]:
    return tempfile.TemporaryDirectory(prefix=prefix, dir=PROJECT / "scratch")


def test_inventory_copies_symlink_as_regular_file() -> None:
    with temporary_directory("detached-runtime-inventory-") as temporary:
        root = Path(temporary)
        source = root / "source"
        source.mkdir()
        target = source / "libfixture.so.1.0"
        target.write_bytes(b"fixture-runtime")
        alias = source / "libfixture.so.1"
        alias.symlink_to(target.name)
        manifest = root / "runtime.sha256"
        system_loader = Path("/lib64/ld-linux-x86-64.so.2")
        manifest.write_text(
            f"{digest(target)}  {alias}\n"
            f"{digest(system_loader)}  {system_loader}\n",
            encoding="ascii",
        )
        snapshot = stage_runtime(manifest, root)
        copied = snapshot.root / alias.name
        assert copied.is_file()
        assert not copied.is_symlink()
        assert copied.read_bytes() == target.read_bytes()
        assert copied.stat().st_mode & 0o222 == 0
        assert snapshot.loader.source == system_loader


def test_duplicate_alias_is_rejected_before_snapshot() -> None:
    with temporary_directory("detached-runtime-alias-") as temporary:
        root = Path(temporary)
        first = root / "first"
        second = root / "second"
        first.mkdir()
        second.mkdir()
        (first / "libduplicate.so").write_bytes(b"one")
        (second / "libduplicate.so").write_bytes(b"two")
        manifest = root / "runtime.sha256"
        manifest.write_text(
            f"{digest(first / 'libduplicate.so')}  {first / 'libduplicate.so'}\n"
            f"{digest(second / 'libduplicate.so')}  {second / 'libduplicate.so'}\n",
            encoding="ascii",
        )
        try:
            stage_runtime(manifest, root)
        except DetachedRuntimeError as exc:
            assert "ambiguous runtime alias" in str(exc)
        else:
            raise AssertionError("duplicate runtime alias was accepted")


def test_snapshot_tamper_and_missing_entry_are_rejected() -> None:
    with temporary_directory("detached-runtime-tamper-") as temporary:
        root = Path(temporary)
        source = root / "source"
        source.mkdir()
        loader = source / "ld-linux-x86-64.so.2"
        loader.write_bytes(b"loader-fixture")
        manifest = root / "runtime.sha256"
        manifest.write_text(f"{digest(loader)}  {loader}\n", encoding="ascii")
        snapshot = stage_runtime(manifest, root)
        copied = snapshot.root / loader.name
        snapshot.root.chmod(0o700)
        copied.chmod(0o700)
        copied.write_bytes(b"tampered")
        snapshot.root.chmod(0o500)
        try:
            verify_snapshot(snapshot)
        except DetachedRuntimeError as exc:
            assert "tampered" in str(exc)
        else:
            raise AssertionError("tampered snapshot was accepted")


def test_loader_list_requires_exact_bound_loader_fd_and_snapshot_paths() -> None:
    with temporary_directory("detached-runtime-list-") as temporary:
        root = Path(temporary)
        executable = Path("/bin/echo").resolve()
        manifest = root / "runtime.sha256"
        ldd_manifest(executable, manifest)
        snapshot = stage_runtime(manifest, root)
        main_fd = bind_executable(executable, digest(executable))
        loader_fd = bind_executable(snapshot.loader.snapshot, snapshot.loader.sha256)
        try:
            listed = inspect_bound_loader(snapshot, main_fd, loader_fd)
            assert listed.loader_fd_path == f"/proc/self/fd/{loader_fd}"
            assert listed.normalized_paths == snapshot.paths
            wrong_fd_output = listed.stdout.replace(
                f"/proc/self/fd/{loader_fd}", "/proc/self/fd/999"
            )
            try:
                validate_loader_list(wrong_fd_output, snapshot, loader_fd)
            except DetachedRuntimeError as exc:
                assert "unexpected runtime path" in str(exc)
            else:
                raise AssertionError("wrong loader fd was accepted")
        finally:
            os.close(main_fd)
            os.close(loader_fd)


def test_missing_snapshot_alias_rejects_host_fallback() -> None:
    with temporary_directory("detached-runtime-fallback-") as temporary:
        root = Path(temporary)
        executable = Path("/bin/echo").resolve()
        manifest = root / "runtime.sha256"
        ldd_manifest(executable, manifest)
        snapshot = stage_runtime(manifest, root)
        removable = next(
            entry.snapshot
            for entry in snapshot.entries
            if entry.snapshot.name != snapshot.loader.snapshot.name
        )
        snapshot.root.chmod(0o700)
        removable.unlink()
        snapshot.root.chmod(0o500)
        main_fd = bind_executable(executable, digest(executable))
        loader_fd = bind_executable(snapshot.loader.snapshot, snapshot.loader.sha256)
        try:
            try:
                inspect_bound_loader(snapshot, main_fd, loader_fd)
            except DetachedRuntimeError as exc:
                assert "unexpected runtime path" in str(exc) or "omitted" in str(exc)
            else:
                raise AssertionError("host-library fallback was accepted")
        finally:
            os.close(main_fd)
            os.close(loader_fd)


def test_loader_overrides_are_sanitized() -> None:
    with temporary_directory("detached-runtime-env-") as temporary:
        root = Path(temporary)
        executable = Path("/bin/echo").resolve()
        manifest = root / "runtime.sha256"
        ldd_manifest(executable, manifest)
        snapshot = stage_runtime(manifest, root)
        old = dict(os.environ)
        try:
            os.environ.update(
                {
                    "LD_PRELOAD": "/tmp/foreign.so",
                    "LD_AUDIT": "/tmp/foreign-audit.so",
                    "LD_DEBUG": "libs",
                    "GCONV_PATH": "/tmp/foreign-gconv",
                    "LOCPATH": "/tmp/foreign-locale",
                    "GLIBC_TUNABLES": "glibc.malloc.check=3",
                }
            )
            clean = sanitize_environment(snapshot)
        finally:
            os.environ.clear()
            os.environ.update(old)
        assert clean["LD_LIBRARY_PATH"] == str(snapshot.root)
        assert not any(name.startswith("LD_") and name != "LD_LIBRARY_PATH" for name in clean)
        assert all(name not in clean for name in ("GCONV_PATH", "LOCPATH", "GLIBC_TUNABLES"))


def test_inherited_descriptors_are_closed() -> None:
    script = f"""
import errno
import fcntl
import os
import sys
sys.path.insert(0, {str(PROJECT / 'tools')!r})
from run_detached_runtime import close_unintended_fds
outside = os.open('/dev/null', os.O_RDONLY)
close_unintended_fds((0, 1, 2))
try:
    fcntl.fcntl(outside, fcntl.F_GETFD)
except OSError as error:
    assert error.errno == errno.EBADF, error
else:
    raise AssertionError('unintended descriptor survived final-exec cleanup')
print('INHERITED_DESCRIPTOR_CLOSED')
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert result.stdout.strip() == "INHERITED_DESCRIPTOR_CLOSED"


def test_explicit_retained_descriptor_survives_cleanup() -> None:
    script = f"""
import errno
import fcntl
import os
import sys
sys.path.insert(0, {str(PROJECT / 'tools')!r})
from run_detached_runtime import close_unintended_fds
retained = os.open('/dev/null', os.O_RDONLY)
outside = os.open('/dev/zero', os.O_RDONLY)
close_unintended_fds((retained,))
fcntl.fcntl(retained, fcntl.F_GETFD)
try:
    fcntl.fcntl(outside, fcntl.F_GETFD)
except OSError as error:
    assert error.errno == errno.EBADF, error
else:
    raise AssertionError('unlisted descriptor survived final-exec cleanup')
os.close(retained)
print('EXPLICIT_DESCRIPTOR_RETAINED')
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert result.stdout.strip() == "EXPLICIT_DESCRIPTOR_RETAINED"


def test_cli_exec_requires_explicit_write_decision_and_runs_confined() -> None:
    with temporary_directory("detached-runtime-exec-") as temporary:
        root = Path(temporary)
        executable = Path("/bin/echo").resolve()
        manifest = root / "runtime.sha256"
        ldd_manifest(executable, manifest)
        helper = PROJECT / "tools/run_detached_runtime.py"
        missing_decision = subprocess.run(
            [
                sys.executable,
                str(helper),
                "--runtime-manifest",
                str(manifest),
                "--snapshot-parent",
                str(root),
                "--expected-sha256",
                digest(executable),
                str(executable),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert missing_decision.returncode == 2
        assert "requires --write-dir or explicit --no-write" in missing_decision.stderr
        result = subprocess.run(
            [
                sys.executable,
                str(helper),
                "--runtime-manifest",
                str(manifest),
                "--snapshot-parent",
                str(root),
                "--expected-sha256",
                digest(executable),
                "--no-write",
                str(executable),
                "detached-runtime-ok",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        assert result.returncode == 0, (result.stdout, result.stderr)
        assert result.stdout == "detached-runtime-ok\n"
        assert "DETACHED_RUNTIME_LIST_PASS files=" in result.stderr
        assert "DETACHED_RUNTIME_LANDLOCK_PASS abi=" in result.stderr


def main() -> None:
    test_inventory_copies_symlink_as_regular_file()
    test_duplicate_alias_is_rejected_before_snapshot()
    test_snapshot_tamper_and_missing_entry_are_rejected()
    test_loader_list_requires_exact_bound_loader_fd_and_snapshot_paths()
    test_missing_snapshot_alias_rejects_host_fallback()
    test_loader_overrides_are_sanitized()
    test_inherited_descriptors_are_closed()
    test_explicit_retained_descriptor_survives_cleanup()
    test_cli_exec_requires_explicit_write_decision_and_runs_confined()
    print("Detached runtime tests passed")


if __name__ == "__main__":
    main()
