#!/usr/bin/env python3
"""Copy a native WRF case without sharing writable inodes with its source."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from run_isolated_native import copy_detached_input


MUTABLE_RUN_FILES = {
    "namelist.output",
    "rsl.error.0000",
    "rsl.out.0000",
    "candidate_run.log",
}
OUTPUT_PREFIXES = ("wrfout", "wrfrst", "wrfdiag")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot_files(directory: Path) -> dict[str, str]:
    return {
        path.name: file_sha256(path)
        for path in sorted(directory.iterdir())
        if path.is_file()
    }


def copy_case(source: Path, executable: Path, destination: Path) -> dict[str, str]:
    if destination.exists():
        raise FileExistsError(f"refusing to reuse run directory: {destination}")
    if not executable.is_file() or not executable.stat().st_mode & 0o111:
        raise FileNotFoundError(f"candidate executable is not executable: {executable}")
    for required in ("namelist.input", "wrfinput_d01", "wrfbdy_d01", "wrf.exe"):
        if not (source / required).is_file():
            raise FileNotFoundError(f"case input missing: {source / required}")

    source_before = snapshot_files(source)
    destination.mkdir(parents=True)
    for path in source.iterdir():
        if not path.is_file():
            continue
        if path.name in MUTABLE_RUN_FILES or path.name == "wrf.exe":
            continue
        if path.suffix == ".exe" or path.name.startswith(OUTPUT_PREFIXES):
            continue
        copy_detached_input(path, destination / path.name)
    copy_detached_input(executable, destination / "wrf.exe")

    source_after = snapshot_files(source)
    if source_after != source_before:
        raise RuntimeError("source case changed while it was copied")
    return source_before


def main() -> int:
    source, executable, destination, snapshot_path = map(Path, sys.argv[1:])
    before = copy_case(source, executable, destination)
    with snapshot_path.open("x") as stream:
        stream.write(json.dumps({"pre": before}, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
