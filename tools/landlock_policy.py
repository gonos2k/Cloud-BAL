"""Apply an explicit filesystem read/write/execute policy before producer exec.

The trusted coordinator must detach and hash inputs first, and close unintended
inherited descriptors. Landlock does not revoke already-open descriptors, pin
file contents, confine network access, or restrict every metadata syscall.
"""

from __future__ import annotations

import ctypes
import os
from pathlib import Path
import platform
import stat
from typing import Sequence


EXECUTE = 1 << 0
READ_FILE = 1 << 2
READ_DIR = 1 << 3
WRITE_ACCESS = sum(1 << bit for bit in (1, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14))
FILE_ACCESS = EXECUTE | READ_FILE | (1 << 1) | (1 << 14)
HANDLED_ACCESS = EXECUTE | READ_FILE | READ_DIR | WRITE_ACCESS
LIBC = ctypes.CDLL(None, use_errno=True)


class Ruleset(ctypes.Structure):
    _fields_ = [("handled_access_fs", ctypes.c_uint64)]


class PathRule(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int)]


def checked(result: int) -> int:
    if result < 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    return result


def landlock_abi() -> int:
    # These syscall numbers are shared by the supported Linux architectures.
    if platform.system() != "Linux" or platform.machine() not in ("x86_64", "aarch64"):
        raise RuntimeError("Landlock policy requires Linux x86_64 or aarch64")
    return checked(LIBC.syscall(444, 0, 0, 1))


def checked_path(value: Path | str) -> Path:
    path = Path(value)
    if not path.is_absolute() or path == Path("/") or path.resolve(strict=True) != path:
        raise ValueError(f"policy path must be absolute, canonical, and narrower than /: {path}")
    return path


def require_detached_read_tree(path: Path) -> set[tuple[int, int]]:
    """Reject aliases which could expose input bytes through writable paths.

    The coordinator owns these trees exclusively while validating/installing
    policy. This check cannot exclude another unsandboxed namespace writer.
    """
    paths = [path]
    if path.is_dir():
        paths.extend(path.rglob("*"))
    identities = set()
    for item in paths:
        metadata = item.lstat()
        identities.add((metadata.st_dev, metadata.st_ino))
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1:
            continue
        # Pseudo-devices must be explicitly named, never admitted by a tree.
        if item == path and stat.S_ISCHR(metadata.st_mode) and metadata.st_nlink == 1:
            continue
        raise ValueError(f"read input is not a detached directory or single-link file: {item}")
    return identities


def restrict_filesystem(
    *,
    read_paths: Sequence[Path | str],
    write_dirs: Sequence[Path | str],
    execute_paths: Sequence[Path | str] = (),
    write_files: Sequence[Path | str] = (),
) -> int:
    """Restrict this process and descendants; return the supported Landlock ABI.

    Read/write directories also allow reads of their output contents. Ordinary
    filesystem executables require explicit execute permission; anonymous sealed
    memfd execution is tested separately by the runtime launcher. This function
    never adds ambient /lib, /etc, /proc, /dev, or Python installation access.
    """
    abi = landlock_abi()
    if abi < 3:
        raise RuntimeError("Landlock ABI >=3 is required, including truncate confinement")
    reads = [checked_path(p) for p in read_paths]
    writes = [checked_path(p) for p in write_dirs]
    executables = [checked_path(p) for p in execute_paths]
    files = [checked_path(p) for p in write_files]
    read_identities = set()
    for read in reads:
        for write in (*writes, *files):
            if read == write or read in write.parents or write in read.parents:
                raise ValueError(f"read-only and writable policy paths overlap: {read}, {write}")
        read_identities.update(require_detached_read_tree(read))
    for write in (*writes, *files):
        objects = [write]
        if write.is_dir():
            objects.extend(write.rglob("*"))
        for item in objects:
            metadata = item.lstat()
            if stat.S_ISREG(metadata.st_mode) and metadata.st_nlink != 1:
                raise ValueError(f"writable object is not a detached single-link file: {item}")
            if (metadata.st_dev, metadata.st_ino) in read_identities:
                raise ValueError(f"writable object aliases a read-only input: {item}")

    handles = []
    ruleset_fd = -1
    try:
        requests = (
            [(p, READ_FILE | READ_DIR, False) for p in reads]
            + [(p, READ_FILE | READ_DIR | WRITE_ACCESS, True) for p in writes]
            + [(p, EXECUTE, False) for p in executables]
            + [(p, (1 << 1) | (1 << 14), False) for p in files]
        )
        # Bind every path before installing any irreversible restriction.
        for path, access, directory_required in requests:
            fd = os.open(path, os.O_PATH | os.O_CLOEXEC | os.O_NOFOLLOW)
            handles.append((fd, access))
            mode = os.fstat(fd).st_mode
            if stat.S_ISLNK(mode) or not (
                stat.S_ISDIR(mode) or stat.S_ISREG(mode) or stat.S_ISCHR(mode)
            ):
                raise ValueError(f"unsupported policy object: {path}")
            if directory_required and not stat.S_ISDIR(mode):
                raise ValueError(f"writable root is not a directory: {path}")
            if path in files and stat.S_ISDIR(mode):
                raise ValueError(f"write_files contains a directory: {path}")
            if not stat.S_ISDIR(mode):
                access &= FILE_ACCESS
            handles[-1] = (fd, access)
        ruleset = Ruleset(HANDLED_ACCESS)
        ruleset_fd = checked(LIBC.syscall(444, ctypes.byref(ruleset), ctypes.sizeof(ruleset), 0))
        for fd, access in handles:
            rule = PathRule(access, fd)
            checked(LIBC.syscall(445, ruleset_fd, 1, ctypes.byref(rule), 0))
        checked(LIBC.prctl(38, 1, 0, 0, 0))
        checked(LIBC.syscall(446, ruleset_fd, 0))
    finally:
        for fd, _ in handles:
            os.close(fd)
        if ruleset_fd >= 0:
            os.close(ruleset_fd)
    return abi
