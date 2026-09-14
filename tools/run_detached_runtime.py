#!/usr/bin/env python3
"""Load a hash-bound ELF with a detached, hash-checked runtime snapshot.

This helper binds the main executable and the dynamic loader into sealed
memfds.  Declared shared libraries are copied as regular files into a fresh
private directory, checked against the build runtime manifest, and selected
through the loader's explicit ``--library-path`` option.  The loader list is
checked before an optional producer exec so a system-library fallback is
rejected.  An actual exec also requires explicit Landlock read and write
roots; ``--list-only`` remains a discovery-only operation.

Actual execution installs the caller's explicit Landlock read and write
allowlists after the detached loader list check.  ``--list-only`` performs
discovery without installing that policy.  The helper does not discover
constructor-time or ``dlopen`` dependencies, and the caller remains
responsible for input-tree integrity, exclusive namespaces, and evidence for
any dependencies outside the declared runtime manifest.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import errno
import fcntl
import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
from typing import Iterable, Sequence

from landlock_policy import restrict_filesystem
from run_bound_executable import (
    BindingError,
    SEAL_FLAGS,
    _read_expected_digest,
    bind_executable,
)


CHUNK_SIZE = 1024 * 1024
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
LOADER_BASENAMES = frozenset(
    {
        "ld-linux-x86-64.so.2",
        "ld-linux-aarch64.so.1",
        "ld-linux-armhf.so.3",
        "ld-linux-ppc64le.so.2",
        "ld64.so.2",
    }
)
SANITIZED_ENV_NAMES = frozenset(
    {
        "GCONV_PATH",
        "LOCPATH",
        "GLIBC_TUNABLES",
    }
)
STAT_FIELDS = (
    "st_dev",
    "st_ino",
    "st_size",
    "st_mode",
    "st_mtime_ns",
    "st_ctime_ns",
)
LOADER_LINE = re.compile(
    r"^(?:(?P<name>\S+) => )?(?P<path>\S+) \(0x[0-9a-fA-F]+\)\Z"
)
KERNEL_OBJECTS = frozenset({"linux-vdso.so.1", "linux-gate.so.1"})


class DetachedRuntimeError(RuntimeError):
    """Raised when the declared detached runtime cannot be bound safely."""


@dataclass(frozen=True)
class ManifestEntry:
    source: Path
    sha256: str


@dataclass(frozen=True)
class SnapshotEntry:
    source: Path
    resolved: Path
    snapshot: Path
    sha256: str


@dataclass(frozen=True)
class RuntimeSnapshot:
    root: Path
    entries: tuple[SnapshotEntry, ...]
    loader: SnapshotEntry

    @property
    def library_paths(self) -> tuple[str, ...]:
        return (str(self.root),)

    @property
    def paths(self) -> frozenset[str]:
        return frozenset(str(entry.snapshot) for entry in self.entries)


@dataclass(frozen=True)
class LoaderList:
    stdout: str
    stderr: str
    listed_paths: tuple[str, ...]
    normalized_paths: frozenset[str]
    kernel_objects: tuple[str, ...]
    loader_fd_path: str


def _metadata_changed(before: os.stat_result, after: os.stat_result) -> bool:
    return any(getattr(before, field) != getattr(after, field) for field in STAT_FIELDS)


def _digest_fd(fd: int) -> str:
    digest = hashlib.sha256()
    os.lseek(fd, 0, os.SEEK_SET)
    while True:
        chunk = os.read(fd, CHUNK_SIZE)
        if not chunk:
            return digest.hexdigest()
        digest.update(chunk)


def _write_all(fd: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        offset += os.write(fd, payload[offset:])


def _read_manifest_line(line: str, manifest: Path, line_number: int) -> ManifestEntry:
    fields = line.split()
    if len(fields) != 2 or SHA256_RE.fullmatch(fields[0]) is None:
        raise DetachedRuntimeError(
            f"invalid runtime manifest line {manifest}:{line_number}"
        )
    source = Path(fields[1])
    if not source.is_absolute() or source.name in {"", ".", ".."}:
        raise DetachedRuntimeError(
            f"runtime manifest source must be an absolute regular-file path: {source}"
        )
    return ManifestEntry(source=source, sha256=fields[0])


def read_runtime_manifest(path: Path) -> tuple[ManifestEntry, ...]:
    """Read a strict two-column sha256sum manifest."""

    try:
        lines = path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise DetachedRuntimeError(f"cannot read runtime manifest {path}: {exc}") from exc
    if not lines:
        raise DetachedRuntimeError(f"runtime manifest is empty: {path}")
    entries = tuple(
        _read_manifest_line(line, path, number)
        for number, line in enumerate(lines, start=1)
        if line.strip()
    )
    if len({entry.source for entry in entries}) != len(entries):
        raise DetachedRuntimeError(f"duplicate source path in runtime manifest: {path}")
    return entries


def _select_loader(
    entries: Iterable[ManifestEntry], loader_source: Path | None = None
) -> ManifestEntry:
    entries = tuple(entries)
    if loader_source is not None:
        requested = loader_source.absolute()
        matches = [
            entry
            for entry in entries
            if entry.source == requested or entry.source.resolve(strict=False) == requested
        ]
        if len(matches) != 1:
            raise DetachedRuntimeError(
                f"loader source is missing or ambiguous in runtime manifest: {requested}"
            )
        return matches[0]
    matches = [entry for entry in entries if entry.source.name in LOADER_BASENAMES]
    if len(matches) != 1:
        if not matches:
            raise DetachedRuntimeError("runtime manifest has no dynamic loader entry")
        raise DetachedRuntimeError("runtime manifest has ambiguous dynamic loader entries")
    return matches[0]


def _validate_aliases(entries: Iterable[ManifestEntry]) -> None:
    aliases: dict[str, Path] = {}
    for entry in entries:
        alias = entry.source.name
        previous = aliases.get(alias)
        if previous is not None:
            raise DetachedRuntimeError(
                f"ambiguous runtime alias {alias}: {previous} and {entry.source}"
            )
        aliases[alias] = entry.source


def _resolved_regular_source(source: Path) -> Path:
    try:
        resolved = source.resolve(strict=True)
    except OSError as exc:
        raise DetachedRuntimeError(f"runtime source is missing: {source}: {exc}") from exc
    try:
        fd = os.open(
            resolved,
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
        )
    except OSError as exc:
        raise DetachedRuntimeError(f"cannot open runtime source {source}: {exc}") from exc
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise DetachedRuntimeError(f"runtime source is not regular: {source}")
    finally:
        os.close(fd)
    return resolved


def _copy_entry(entry: ManifestEntry, root: Path) -> SnapshotEntry:
    resolved = _resolved_regular_source(entry.source)
    target = root / entry.source.name
    try:
        source_fd = os.open(
            resolved,
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
        )
    except OSError as exc:
        raise DetachedRuntimeError(f"cannot reopen runtime source {resolved}: {exc}") from exc
    target_fd = -1
    try:
        before = os.fstat(source_fd)
        if not stat.S_ISREG(before.st_mode):
            raise DetachedRuntimeError(f"runtime source is not regular: {entry.source}")
        target_fd = os.open(
            target,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o500,
        )
        digest = hashlib.sha256()
        while True:
            chunk = os.read(source_fd, CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
            _write_all(target_fd, chunk)
        after = os.fstat(source_fd)
        if _metadata_changed(before, after):
            raise DetachedRuntimeError(f"runtime source changed while copied: {entry.source}")
        if digest.hexdigest() != entry.sha256:
            raise DetachedRuntimeError(
                f"runtime source SHA-256 mismatch for {entry.source}: "
                f"expected {entry.sha256}, got {digest.hexdigest()}"
            )
        os.fsync(target_fd)
        os.fchmod(target_fd, 0o500)
        os.lseek(target_fd, 0, os.SEEK_SET)
        copied_digest = _digest_fd(target_fd)
        if copied_digest != entry.sha256:
            raise DetachedRuntimeError(
                f"runtime snapshot SHA-256 mismatch for {target}: "
                f"expected {entry.sha256}, got {copied_digest}"
            )
    except DetachedRuntimeError:
        raise
    except OSError as exc:
        raise DetachedRuntimeError(f"cannot copy runtime source {entry.source}: {exc}") from exc
    finally:
        if target_fd >= 0:
            os.close(target_fd)
        os.close(source_fd)
    return SnapshotEntry(
        source=entry.source,
        resolved=resolved,
        snapshot=target,
        sha256=entry.sha256,
    )


def verify_snapshot(snapshot: RuntimeSnapshot) -> None:
    """Verify every expected regular file and reject extra snapshot aliases."""

    expected_names = {entry.snapshot.name for entry in snapshot.entries}
    try:
        children = tuple(snapshot.root.iterdir())
    except OSError as exc:
        raise DetachedRuntimeError(f"cannot inspect runtime snapshot {snapshot.root}: {exc}") from exc
    extra = sorted(child.name for child in children if child.name not in expected_names)
    if extra:
        raise DetachedRuntimeError(
            f"runtime snapshot contains unexpected aliases: {', '.join(extra)}"
        )
    for entry in snapshot.entries:
        try:
            fd = os.open(
                entry.snapshot,
                os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
            )
        except OSError as exc:
            raise DetachedRuntimeError(
                f"runtime snapshot entry is missing or not regular: {entry.snapshot}: {exc}"
            ) from exc
        try:
            metadata = os.fstat(fd)
            if not stat.S_ISREG(metadata.st_mode):
                raise DetachedRuntimeError(f"runtime snapshot entry is not regular: {entry.snapshot}")
            actual = _digest_fd(fd)
        finally:
            os.close(fd)
        if actual != entry.sha256:
            raise DetachedRuntimeError(
                f"runtime snapshot entry was tampered: {entry.snapshot}: "
                f"expected {entry.sha256}, got {actual}"
            )


def stage_runtime(
    manifest_path: Path,
    snapshot_parent: Path,
    loader_source: Path | None = None,
) -> RuntimeSnapshot:
    """Create a fresh private regular-file snapshot from a runtime manifest."""

    entries = read_runtime_manifest(manifest_path)
    _validate_aliases(entries)
    loader_manifest_entry = _select_loader(entries, loader_source)
    try:
        parent = snapshot_parent.resolve(strict=True)
        if not parent.is_dir():
            raise DetachedRuntimeError(f"snapshot parent is not a directory: {snapshot_parent}")
        root = Path(tempfile.mkdtemp(prefix="cloud-bal-runtime-", dir=parent))
    except DetachedRuntimeError:
        raise
    except OSError as exc:
        raise DetachedRuntimeError(
            f"cannot create detached runtime snapshot under {snapshot_parent}: {exc}"
        ) from exc
    try:
        copied = tuple(_copy_entry(entry, root) for entry in entries)
        loader = next(item for item in copied if item.source == loader_manifest_entry.source)
        root.chmod(0o500)
        snapshot = RuntimeSnapshot(root=root, entries=copied, loader=loader)
        verify_snapshot(snapshot)
        return snapshot
    except Exception:
        # Keep failed snapshots for the coordinator's evidence and diagnosis.
        try:
            root.chmod(0o700)
        except OSError:
            pass
        raise


def sanitize_environment(snapshot: RuntimeSnapshot) -> dict[str, str]:
    """Remove loader override variables and select only the snapshot library path."""

    environment = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("LD_") and name not in SANITIZED_ENV_NAMES
    }
    environment["LD_LIBRARY_PATH"] = os.pathsep.join(snapshot.library_paths)
    return environment


def _clear_close_on_exec(fd: int) -> None:
    flags = fcntl.fcntl(fd, fcntl.F_GETFD)
    fcntl.fcntl(fd, fcntl.F_SETFD, flags & ~fcntl.FD_CLOEXEC)


def close_unintended_fds(keep_fds: Iterable[int]) -> None:
    """Close inherited descriptors while retaining stdio and bound ELF fds."""

    keep = {0, 1, 2}
    for fd in keep_fds:
        if fd < 0:
            raise DetachedRuntimeError(f"cannot retain invalid descriptor {fd}")
        keep.add(fd)
    try:
        directory_fd = os.open(
            "/proc/self/fd",
            os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW,
        )
    except OSError as exc:
        raise DetachedRuntimeError(f"cannot enumerate inherited descriptors: {exc}") from exc
    try:
        try:
            descriptors = os.listdir(directory_fd)
        except OSError as exc:
            raise DetachedRuntimeError(
                f"cannot enumerate inherited descriptors: {exc}"
            ) from exc
        for name in descriptors:
            try:
                fd = int(name)
            except ValueError:
                continue
            if fd == directory_fd or fd in keep:
                continue
            try:
                os.close(fd)
            except OSError as exc:
                if exc.errno != errno.EBADF:
                    raise DetachedRuntimeError(
                        f"cannot close inherited descriptor {fd}: {exc}"
                    ) from exc
    finally:
        os.close(directory_fd)


def _loader_command(loader_fd: int, main_fd: int, snapshot: RuntimeSnapshot) -> list[str]:
    return [
        f"/proc/self/fd/{loader_fd}",
        "--inhibit-cache",
        "--library-path",
        os.pathsep.join(snapshot.library_paths),
        "--list",
        f"/proc/self/fd/{main_fd}",
    ]


def _parse_loader_line(line: str) -> tuple[str | None, str]:
    match = LOADER_LINE.fullmatch(line.strip())
    if match is None:
        raise DetachedRuntimeError(f"unparseable dynamic-loader listing line: {line!r}")
    return match.group("name"), match.group("path")


def validate_loader_list(
    stdout: str,
    snapshot: RuntimeSnapshot,
    loader_fd: int,
) -> LoaderList:
    """Require exactly the detached aliases and this invocation's loader fd."""

    loader_fd_path = f"/proc/self/fd/{loader_fd}"
    listed: list[str] = []
    normalized: set[str] = set()
    kernel_objects: list[str] = []
    for raw_line in stdout.splitlines():
        if not raw_line.strip():
            continue
        name, path = _parse_loader_line(raw_line)
        if name is None and path in KERNEL_OBJECTS:
            kernel_objects.append(name or path)
            continue
        listed.append(path)
        normalized_path = str(snapshot.loader.snapshot) if path == loader_fd_path else path
        if normalized_path not in snapshot.paths:
            raise DetachedRuntimeError(
                f"dynamic loader resolved an unexpected runtime path: {path}"
            )
        if normalized_path in normalized:
            raise DetachedRuntimeError(f"dynamic loader listed a duplicate path: {path}")
        normalized.add(normalized_path)
    expected = snapshot.paths
    missing = sorted(expected - normalized)
    if missing:
        raise DetachedRuntimeError(
            "dynamic loader omitted detached runtime paths: " + ", ".join(missing)
        )
    if loader_fd_path not in listed:
        raise DetachedRuntimeError(
            f"dynamic loader did not resolve its interpreter to exact bound fd {loader_fd_path}"
        )
    return LoaderList(
        stdout=stdout,
        stderr="",
        listed_paths=tuple(listed),
        normalized_paths=frozenset(normalized),
        kernel_objects=tuple(kernel_objects),
        loader_fd_path=loader_fd_path,
    )


def inspect_bound_loader(
    snapshot: RuntimeSnapshot,
    main_fd: int,
    loader_fd: int,
    timeout: float = 30.0,
) -> LoaderList:
    """Run the detached loader's non-executing ``--list`` inspection."""

    command = _loader_command(loader_fd, main_fd, snapshot)
    try:
        result = subprocess.run(
            command,
            env=sanitize_environment(snapshot),
            pass_fds=(main_fd, loader_fd),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DetachedRuntimeError(f"detached loader inspection failed: {exc}") from exc
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise DetachedRuntimeError(
            f"detached loader inspection exited {result.returncode}: {detail}"
        )
    parsed = validate_loader_list(result.stdout, snapshot, loader_fd)
    return LoaderList(
        stdout=parsed.stdout,
        stderr=result.stderr,
        listed_paths=parsed.listed_paths,
        normalized_paths=parsed.normalized_paths,
        kernel_objects=parsed.kernel_objects,
        loader_fd_path=parsed.loader_fd_path,
    )


def _require_sealed(fd: int, label: str) -> None:
    try:
        seals = fcntl.fcntl(fd, fcntl.F_GET_SEALS)
    except OSError as exc:
        raise DetachedRuntimeError(f"{label} is not a valid sealed memfd: {exc}") from exc
    if seals & SEAL_FLAGS != SEAL_FLAGS:
        raise DetachedRuntimeError(f"{label} is not fully sealed")


def _require_runtime_read_root(
    snapshot: RuntimeSnapshot, read_paths: Sequence[Path | str]
) -> tuple[Path | str, ...]:
    try:
        runtime_root = snapshot.root.resolve(strict=True)
        candidates = tuple(Path(path).resolve(strict=True) for path in read_paths)
    except (OSError, RuntimeError) as exc:
        raise DetachedRuntimeError(f"cannot resolve execution policy paths: {exc}") from exc
    if runtime_root not in candidates:
        raise DetachedRuntimeError(
            "execution policy must explicitly include the detached runtime snapshot root"
        )
    return (snapshot.root, *read_paths)


def exec_detached_runtime(
    snapshot: RuntimeSnapshot,
    main_fd: int,
    loader_fd: int,
    argv0: str,
    arguments: Sequence[str] = (),
    *,
    read_paths: Sequence[Path | str],
    write_dirs: Sequence[Path | str],
    execute_paths: Sequence[Path | str] = (),
    write_files: Sequence[Path | str] = (),
    retain_fds: Sequence[int] = (),
) -> None:
    """Replace the caller with the sealed main ELF through the sealed loader.

    The caller must call :func:`inspect_bound_loader` first.  This function
    closes inherited descriptors, installs the explicit Landlock policy, and
    then executes through the sealed loader fd.  ``read_paths`` and
    ``write_dirs`` are required to make the caller's confinement decision
    explicit; the detached runtime root must be present in ``read_paths``.
    ``retain_fds`` is an optional explicit list of additional sealed
    descriptors, such as a bound utility and its loader, that a trusted
    coordinator has named for a direct child closure.
    """

    if not argv0:
        raise DetachedRuntimeError("detached runtime argv0 must be non-empty")
    retained_fds = tuple(retain_fds)
    if len(set(retained_fds)) != len(retained_fds):
        raise DetachedRuntimeError("retained executable descriptors must be unique")
    if any(fd in (main_fd, loader_fd) for fd in retained_fds):
        raise DetachedRuntimeError(
            "retained executable descriptors must not duplicate the main or loader fd"
        )
    policy_reads = _require_runtime_read_root(snapshot, read_paths)
    _require_sealed(main_fd, "main executable")
    _require_sealed(loader_fd, "dynamic loader")
    for index, fd in enumerate(retained_fds, start=1):
        _require_sealed(fd, f"retained executable {index}")
    close_unintended_fds((main_fd, loader_fd, *retained_fds))
    try:
        landlock_abi = restrict_filesystem(
            read_paths=policy_reads,
            write_dirs=write_dirs,
            execute_paths=execute_paths,
            write_files=write_files,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        raise DetachedRuntimeError(f"cannot install execution filesystem policy: {exc}") from exc
    print(f"DETACHED_RUNTIME_LANDLOCK_PASS abi={landlock_abi}", file=sys.stderr, flush=True)
    for fd in (main_fd, loader_fd, *retained_fds):
        _clear_close_on_exec(fd)
    loader_path = f"/proc/self/fd/{loader_fd}"
    command = [
        loader_path,
        "--inhibit-cache",
        "--library-path",
        os.pathsep.join(snapshot.library_paths),
        "--argv0",
        argv0,
        f"/proc/self/fd/{main_fd}",
        *arguments,
    ]
    try:
        os.execve(loader_path, command, sanitize_environment(snapshot))
    except OSError as exc:
        raise DetachedRuntimeError(f"cannot execute sealed loader fd: {exc}") from exc


def _parse_arguments(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-manifest", required=True, type=Path)
    parser.add_argument("--snapshot-parent", required=True, type=Path)
    parser.add_argument("--loader-source", type=Path)
    parser.add_argument("--read-path", dest="read_paths", action="append", type=Path, default=[])
    parser.add_argument("--write-dir", dest="write_dirs", action="append", type=Path, default=[])
    parser.add_argument("--execute-path", dest="execute_paths", action="append", type=Path, default=[])
    parser.add_argument("--write-file", dest="write_files", action="append", type=Path, default=[])
    parser.add_argument("--no-write", action="store_true")
    expected = parser.add_mutually_exclusive_group(required=True)
    expected.add_argument("--expected-sha256")
    expected.add_argument("--sha256-file", type=Path)
    parser.add_argument("--list-only", action="store_true")
    parser.add_argument("--list-timeout", type=float, default=30.0)
    parser.add_argument("executable", type=Path)
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    parsed = parser.parse_args(argv)
    if parsed.arguments and parsed.arguments[0] == "--":
        parsed.arguments.pop(0)
    if parsed.list_timeout <= 0:
        parser.error("--list-timeout must be positive")
    if parsed.no_write and parsed.write_dirs:
        parser.error("--no-write cannot be combined with --write-dir")
    if not parsed.list_only and not (parsed.no_write or parsed.write_dirs):
        parser.error("actual execution requires --write-dir or explicit --no-write")
    return parsed


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_arguments(sys.argv[1:] if argv is None else argv)
    main_fd = -1
    loader_fd = -1
    try:
        expected = (
            args.expected_sha256
            if args.expected_sha256 is not None
            else _read_expected_digest(args.sha256_file)
        )
        snapshot = stage_runtime(args.runtime_manifest, args.snapshot_parent, args.loader_source)
        verify_snapshot(snapshot)
        main_fd = bind_executable(args.executable, expected)
        loader_fd = bind_executable(snapshot.loader.snapshot, snapshot.loader.sha256)
        loader_list = inspect_bound_loader(snapshot, main_fd, loader_fd, args.list_timeout)
        print(
            f"DETACHED_RUNTIME_LIST_PASS files={len(loader_list.normalized_paths)} "
            f"snapshot={snapshot.root} loader_fd={loader_list.loader_fd_path}",
            file=sys.stderr,
            flush=True,
        )
        if args.list_only:
            sys.stdout.write(loader_list.stdout)
            sys.stderr.write(loader_list.stderr)
            return 0
        exec_detached_runtime(
            snapshot,
            main_fd,
            loader_fd,
            args.executable.name,
            args.arguments,
            read_paths=(snapshot.root, *args.read_paths),
            write_dirs=() if args.no_write else args.write_dirs,
            execute_paths=args.execute_paths,
            write_files=args.write_files,
        )
    except (BindingError, DetachedRuntimeError, OSError, ValueError) as exc:
        print(f"DETACHED_RUNTIME_REJECTED: {exc}", file=sys.stderr)
        return 2
    finally:
        if main_fd >= 0:
            os.close(main_fd)
        if loader_fd >= 0:
            os.close(loader_fd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
