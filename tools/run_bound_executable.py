#!/usr/bin/env python3
"""Execute exactly the hash-pinned bytes copied from an ELF executable.

The source pathname is opened once and is never used for execution.  On Linux
the bytes read from that descriptor are copied to a sealed memfd and the
memfd is executed through its descriptor path.  This closes the replacement
window between a pathname hash and a later pathname exec.  The caller remains
responsible for trusting the expected digest and for sandboxing the process.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import os
import re
import stat
import sys
from pathlib import Path
from typing import Mapping, Sequence


CHUNK_SIZE = 1024 * 1024
ELF_MAGIC = b"\x7fELF"
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
SEAL_FLAGS = (
    fcntl.F_SEAL_WRITE
    | fcntl.F_SEAL_GROW
    | fcntl.F_SEAL_SHRINK
    | fcntl.F_SEAL_SEAL
)


class BindingError(RuntimeError):
    """Raised when the expected executable cannot be bound safely."""


def _read_only_flags() -> int:
    try:
        return os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
    except AttributeError as exc:
        raise BindingError("Linux O_CLOEXEC, O_NOFOLLOW, and O_NONBLOCK are required") from exc


def _read_all(fd: int) -> bytes:
    chunks = []
    while True:
        chunk = os.read(fd, CHUNK_SIZE)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def _sha256_fd(fd: int) -> str:
    digest = hashlib.sha256()
    while True:
        chunk = os.read(fd, CHUNK_SIZE)
        if not chunk:
            return digest.hexdigest()
        digest.update(chunk)


def _read_expected_digest(path: Path) -> str:
    flags = _read_only_flags()
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise BindingError(f"cannot open expected SHA-256 file {path}: {exc}") from exc
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise BindingError(f"expected SHA-256 file is not regular: {path}")
        try:
            text = _read_all(fd).decode("ascii")
        except (UnicodeDecodeError, OSError) as exc:
            raise BindingError(f"expected SHA-256 file is not ASCII: {path}") from exc
    finally:
        os.close(fd)

    lines = text.splitlines()
    if len(lines) != 1:
        raise BindingError(
            f"expected SHA-256 file must contain exactly one sha256sum line: {path}"
        )
    fields = lines[0].split()
    digest = fields[0] if fields else ""
    if SHA256_RE.fullmatch(digest) is None:
        raise BindingError(f"invalid expected SHA-256 in {path}")
    return digest


def _source_changed(before: os.stat_result, after: os.stat_result) -> bool:
    # ctime catches an in-place write that restores the original bytes or
    # timestamp.  The inode/device pair proves the opened object stayed put;
    # pathname replacement after open is harmless because execution uses the
    # sealed memfd.
    fields = (
        "st_dev",
        "st_ino",
        "st_size",
        "st_mode",
        "st_mtime_ns",
        "st_ctime_ns",
    )
    return any(getattr(before, field) != getattr(after, field) for field in fields)


def _write_all(fd: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        offset += os.write(fd, payload[offset:])


def _new_sealed_memfd() -> int:
    create = getattr(os, "memfd_create", None)
    if create is None:
        raise BindingError("Linux memfd_create is required for bound executable launch")
    try:
        flags = os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING
    except AttributeError as exc:
        raise BindingError("memfd sealing flags are unavailable") from exc
    try:
        return create("cloud-bal-bound-executable", flags)
    except OSError as exc:
        raise BindingError(f"cannot create sealed executable memfd: {exc}") from exc


def bind_executable(executable: Path, expected_sha256: str) -> int:
    """Return a sealed memfd containing the hash-pinned executable bytes."""

    if SHA256_RE.fullmatch(expected_sha256) is None:
        raise BindingError("expected SHA-256 must be 64 lowercase hexadecimal characters")

    flags = _read_only_flags()
    try:
        source_fd = os.open(executable, flags)
    except OSError as exc:
        raise BindingError(f"cannot open executable {executable}: {exc}") from exc

    memfd = -1
    try:
        before = os.fstat(source_fd)
        if not stat.S_ISREG(before.st_mode):
            raise BindingError(f"executable is not a regular file: {executable}")
        if not before.st_mode & 0o111:
            raise BindingError(f"executable has no execute permission: {executable}")

        memfd = _new_sealed_memfd()
        prefix = bytearray()
        while True:
            chunk = os.read(source_fd, CHUNK_SIZE)
            if not chunk:
                break
            if len(prefix) < len(ELF_MAGIC):
                prefix.extend(chunk[: len(ELF_MAGIC) - len(prefix)])
            _write_all(memfd, chunk)

        after = os.fstat(source_fd)
        if _source_changed(before, after):
            raise BindingError(f"executable changed while being bound: {executable}")
        if bytes(prefix) != ELF_MAGIC:
            raise BindingError(f"executable is not an ELF binary: {executable}")

        os.lseek(memfd, 0, os.SEEK_SET)
        try:
            fcntl.fcntl(memfd, fcntl.F_ADD_SEALS, SEAL_FLAGS)
            seals = fcntl.fcntl(memfd, fcntl.F_GET_SEALS)
        except OSError as exc:
            raise BindingError(f"cannot seal executable memfd: {exc}") from exc
        if seals & SEAL_FLAGS != SEAL_FLAGS:
            raise BindingError("sealed executable memfd did not retain all required seals")

        # Hash the now-immutable destination.  If another process changed the
        # memfd during the copy, sealing preserves that changed content and
        # this check rejects it before exec.  The bytes checked here are the
        # same bytes that exec_bound() receives.
        os.lseek(memfd, 0, os.SEEK_SET)
        actual_sha256 = _sha256_fd(memfd)
        if actual_sha256 != expected_sha256:
            raise BindingError(
                f"executable SHA-256 mismatch for {executable}: "
                f"expected {expected_sha256}, got {actual_sha256}"
            )
        os.lseek(memfd, 0, os.SEEK_SET)
        return memfd
    except Exception:
        if memfd >= 0:
            os.close(memfd)
        raise
    finally:
        os.close(source_fd)


def exec_bound(fd: int, argv: Sequence[str], env: Mapping[str, str] | None = None) -> None:
    """Replace this process with the sealed executable represented by ``fd``."""

    if not argv or not argv[0]:
        raise BindingError("bound executable argv must contain a non-empty argv[0]")
    try:
        seals = fcntl.fcntl(fd, fcntl.F_GET_SEALS)
    except OSError as exc:
        raise BindingError(f"bound executable fd is invalid: {exc}") from exc
    if seals & SEAL_FLAGS != SEAL_FLAGS:
        raise BindingError("refusing to execute an unsealed executable fd")

    proc_fd = f"/proc/self/fd/{fd}"
    if not os.path.exists(proc_fd):
        raise BindingError("/proc/self/fd is required to execute the sealed memfd")
    try:
        os.execve(proc_fd, list(argv), dict(os.environ if env is None else env))
    except OSError as exc:
        raise BindingError(f"cannot execute sealed executable fd: {exc}") from exc


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Hash-check and execute immutable bytes copied to a sealed Linux memfd."
    )
    expected = parser.add_mutually_exclusive_group(required=True)
    expected.add_argument("--expected-sha256", help="64 lowercase hexadecimal digest")
    expected.add_argument(
        "--sha256-file", type=Path, help="sha256sum output containing the expected digest"
    )
    parser.add_argument("executable", type=Path)
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    parsed = parser.parse_args(argv)
    if parsed.arguments and parsed.arguments[0] == "--":
        parsed.arguments.pop(0)
    return parsed


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    fd = -1
    try:
        expected_sha256 = (
            args.expected_sha256
            if args.expected_sha256 is not None
            else _read_expected_digest(args.sha256_file)
        )
        fd = bind_executable(args.executable, expected_sha256)
        print(
            "BOUND_EXECUTABLE_READY "
            f"method=sealed_memfd sha256={expected_sha256} "
            f"executable={args.executable}",
            file=sys.stderr,
            flush=True,
        )
        exec_bound(
            fd,
            [args.executable.name, *args.arguments],
            os.environ,
        )
    except BindingError as exc:
        print(f"BOUND_EXECUTABLE_REJECTED: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"BOUND_EXECUTABLE_REJECTED: {exc}", file=sys.stderr)
        return 2
    finally:
        if fd >= 0:
            os.close(fd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
