#!/usr/bin/env python3
"""Copy a native WRF case without sharing writable inodes with its source."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path


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
        shutil.copy2(path, destination / path.name)
    shutil.copy2(executable, destination / "wrf.exe")

    source_after = snapshot_files(source)
    if source_after != source_before:
        raise RuntimeError("source case changed while it was copied")
    source_executable = source / "wrf.exe"
    if ((destination / "wrf.exe").stat().st_dev,
            (destination / "wrf.exe").stat().st_ino) == (
            source_executable.stat().st_dev, source_executable.stat().st_ino):
        raise RuntimeError("candidate executable shares an inode with the source case")
    for name in source_before:
        copied = destination / name
        if copied.exists() and (copied.stat().st_dev, copied.stat().st_ino) == (
                (source / name).stat().st_dev, (source / name).stat().st_ino):
            raise RuntimeError(f"copied case file shares a source inode: {name}")
    return source_before


def main() -> int:
    source, executable, destination, snapshot_path = map(Path, sys.argv[1:])
    before = copy_case(source, executable, destination)
    snapshot_path.write_text(json.dumps({"pre": before}, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
