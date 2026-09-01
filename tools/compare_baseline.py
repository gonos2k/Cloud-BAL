#!/usr/bin/env python3
"""Read-only byte/checksum comparison of an isolated legacy baseline and rerun.

The WPS intermediate files in this workflow are not NetCDF, so this first gate
intentionally compares the archived files without rewriting or normalizing
them.  A nonzero exit means at least one selected output changed or is absent.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def files_under(root: Path) -> dict[Path, Path]:
    return {
        path.relative_to(root): path
        for path in root.rglob("*")
        if path.is_file() and path.name not in {"README.md", "SHA256SUMS"}
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    args = parser.parse_args()

    baseline = files_under(args.baseline.resolve())
    candidate = files_under(args.candidate.resolve())
    changed = 0
    for relative in sorted(set(baseline) | set(candidate)):
        old = baseline.get(relative)
        new = candidate.get(relative)
        if old is None:
            print(f"ADDED    {relative}")
            changed += 1
        elif new is None:
            print(f"MISSING  {relative}")
            changed += 1
        elif old.stat().st_size != new.stat().st_size or digest(old) != digest(new):
            print(f"CHANGED  {relative}  {old.stat().st_size} -> {new.stat().st_size} bytes")
            changed += 1
        else:
            print(f"IDENTICAL {relative}")
    print(f"Compared {len(set(baseline) | set(candidate))} files; {changed} differ")
    return 1 if changed else 0


if __name__ == "__main__":
    raise SystemExit(main())
