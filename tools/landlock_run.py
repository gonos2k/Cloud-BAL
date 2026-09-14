#!/usr/bin/env python3
"""Run a command with pathname writes confined to one private directory."""

from __future__ import annotations

import ctypes
import os
import sys


LIBC = ctypes.CDLL(None, use_errno=True)
WRITE_ACCESS = sum(1 << bit for bit in (1, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14))


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


def main() -> int:
    if len(sys.argv) < 3:
        print(f"usage: {sys.argv[0]} PRIVATE_ROOT COMMAND [ARG ...]", file=sys.stderr)
        return 2
    private_root = os.path.realpath(sys.argv[1])
    abi = checked(LIBC.syscall(444, 0, 0, 1))
    if abi < 3:
        raise RuntimeError("Landlock ABI >=3 is required")
    ruleset = Ruleset(WRITE_ACCESS)
    ruleset_fd = checked(LIBC.syscall(444, ctypes.byref(ruleset), ctypes.sizeof(ruleset), 0))
    for path, access in ((private_root, WRITE_ACCESS), ("/dev/null", 1 << 1)):
        parent_fd = os.open(path, os.O_PATH | os.O_CLOEXEC)
        try:
            rule = PathRule(access, parent_fd)
            checked(LIBC.syscall(445, ruleset_fd, 1, ctypes.byref(rule), 0))
        finally:
            os.close(parent_fd)
    checked(LIBC.prctl(38, 1, 0, 0, 0))
    checked(LIBC.syscall(446, ruleset_fd, 0))
    os.close(ruleset_fd)
    try:
        outside_fd = os.open(__file__, os.O_WRONLY)
    except PermissionError:
        pass
    else:
        os.close(outside_fd)
        raise RuntimeError("Landlock write confinement probe failed")
    print(f"LANDLOCK_WRITE_CONFINEMENT_PASS abi={abi} private={private_root}", flush=True)
    os.execvp(sys.argv[2], sys.argv[2:])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
