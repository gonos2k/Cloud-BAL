#!/usr/bin/env python3
"""Inspect runtime dependencies of the exact sealed build executable."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

from run_bound_executable import BindingError, _read_expected_digest, bind_executable


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("--sha256-file", required=True, type=Path)
    args = parser.parse_args()
    try:
        descriptor = bind_executable(args.executable, _read_expected_digest(args.sha256_file))
        try:
            result = subprocess.run(
                ["ldd", "-r", f"/proc/self/fd/{descriptor}"],
                pass_fds=(descriptor,), capture_output=True, text=True,
            )
        finally:
            os.close(descriptor)
    except (BindingError, OSError) as error:
        print(f"runtime inspection failed: {error}", file=sys.stderr)
        return 2
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    if result.returncode or any(
        message in result.stdout + result.stderr
        for message in ("not found", "undefined symbol", "not a dynamic executable")
    ):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
