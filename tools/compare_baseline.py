#!/usr/bin/env python3
"""Read-only byte/checksum comparison of an isolated legacy baseline and rerun.

The WPS intermediate files in this workflow are not NetCDF, so this first gate
intentionally compares the archived files without rewriting or normalizing
them.  A nonzero exit means at least one selected output changed or is absent.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import stat
import struct
from pathlib import Path

import numpy as np


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def files_under(root: Path) -> dict[Path, Path]:
    files: dict[Path, Path] = {}
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if path.is_symlink():
            raise ValueError(f"symbolic link is not an independent product: {path}")
        mode = path.lstat().st_mode
        if stat.S_ISDIR(mode):
            continue
        if not stat.S_ISREG(mode):
            raise ValueError(f"non-regular product entry: {path}")
        if relative in {Path("README.md"), Path("SHA256SUMS")}:
            continue
        if path.stat().st_nlink != 1:
            raise ValueError(f"multiply-linked product is not independent: {path}")
        files[relative] = path
    return files


def comparison_files(
    baseline_argument: Path, candidate_argument: Path
) -> tuple[dict[Path, Path], dict[Path, Path]]:
    """Validate independent roots and return their complete file inventories."""
    if baseline_argument.is_symlink() or candidate_argument.is_symlink():
        raise ValueError("comparison roots must not be symbolic links")
    baseline_root = baseline_argument.resolve(strict=True)
    candidate_root = candidate_argument.resolve(strict=True)
    if not baseline_root.is_dir() or not candidate_root.is_dir():
        raise ValueError("comparison roots must be directories")
    if baseline_root == candidate_root or baseline_root in candidate_root.parents or \
            candidate_root in baseline_root.parents:
        raise ValueError("comparison roots must be distinct and non-overlapping")
    baseline = files_under(baseline_root)
    candidate = files_under(candidate_root)
    if not baseline or not candidate:
        raise ValueError("comparison roots must each contain at least one product")
    baseline_inodes = {
        (path.stat().st_dev, path.stat().st_ino) for path in baseline.values()
    }
    candidate_inodes = {
        (path.stat().st_dev, path.stat().st_ino) for path in candidate.values()
    }
    if baseline_inodes & candidate_inodes:
        raise ValueError("baseline and candidate contain the same inode")
    return baseline, candidate


def _records(path: Path):
    """Yield Fortran sequential-unformatted records and detected endianness."""
    with path.open("rb") as stream:
        marker = stream.read(4)
        if len(marker) != 4:
            return
        if struct.unpack(">i", marker)[0] == 4:
            endian = ">"
        elif struct.unpack("<i", marker)[0] == 4:
            endian = "<"
        else:
            raise ValueError(f"invalid first Fortran record marker: {path}")
        stream.seek(0)
        while True:
            marker = stream.read(4)
            if not marker:
                return
            if len(marker) != 4:
                raise ValueError(f"truncated record marker: {path}")
            size = struct.unpack(endian + "i", marker)[0]
            payload = stream.read(size)
            trailer = stream.read(4)
            if len(payload) != size or len(trailer) != 4 or \
                    struct.unpack(endian + "i", trailer)[0] != size:
                raise ValueError(f"invalid Fortran record: {path}")
            yield endian, payload


def read_wps(path: Path):
    """Read the field metadata/slabs used by the WPS intermediate format."""
    records = iter(_records(path))
    fields = {}
    while True:
        try:
            endian, version_record = next(records)
        except StopIteration:
            break
        if len(version_record) != 4 or struct.unpack(endian + "i", version_record)[0] != 5:
            raise ValueError("not a WPS intermediate file")
        _, metadata = next(records)
        if len(metadata) < 156:
            raise ValueError("short WPS metadata record")
        hdate = metadata[0:24].decode("ascii", "replace").strip()
        field = metadata[60:69].decode("ascii", "replace").strip()
        units = metadata[69:94].decode("ascii", "replace").strip()
        level = struct.unpack(endian + "f", metadata[140:144])[0]
        nx, ny, projection = struct.unpack(endian + "iii", metadata[144:156])
        _, projection_record = next(records)
        _, wind_record = next(records)
        if len(wind_record) != 4:
            raise ValueError("invalid WPS wind-coordinate record")
        wind_relative = struct.unpack(endian + "i", wind_record)[0]
        # The record is a Fortran LOGICAL, not a portable C boolean.  Preserve
        # the two encodings present in the legacy archive and reject every
        # other integer as corrupt metadata.
        if wind_relative not in {-1, 0, 1}:
            raise ValueError("invalid WPS wind-coordinate flag")
        _, slab_record = next(records)
        if len(slab_record) != 4 * nx * ny:
            raise ValueError("WPS slab size does not match metadata")
        slab = np.frombuffer(slab_record, dtype=endian + "f4").astype(np.float64)
        key = (field, level, hdate)
        if key in fields:
            raise ValueError(f"duplicate WPS field identity {key!r}: {path}")
        fields[key] = (
            units,
            (nx, ny),
            slab,
            {
                "projection": projection,
                "projection_record_sha256": hashlib.sha256(projection_record).hexdigest(),
                "wind_grid_relative": bool(wind_relative),
            },
        )
    return fields


def looks_like_wps(path: Path) -> bool:
    try:
        records = iter(_records(path))
        endian, version = next(records)
        return len(version) == 4 and struct.unpack(endian + "i", version)[0] == 5
    except (OSError, ValueError, StopIteration):
        return False


def numeric_summary(old_path: Path, new_path: Path) -> list[str]:
    """Return field-level differences for NetCDF or WPS intermediate files."""
    summaries: list[str] = []
    old_netcdf = old_path.suffix == ".nc"
    new_netcdf = new_path.suffix == ".nc"
    old_wps = looks_like_wps(old_path)
    new_wps = looks_like_wps(new_path)
    if not (old_netcdf or new_netcdf or old_wps or new_wps):
        return summaries
    if old_netcdf != new_netcdf or old_wps != new_wps:
        raise ValueError(f"file format changed: {old_path} -> {new_path}")

    if old_netcdf:
        try:
            from netCDF4 import Dataset
        except ImportError as exc:
            raise RuntimeError("netCDF4 is required to compare changed NetCDF fields") from exc
        try:
            with Dataset(old_path) as old_ds, Dataset(new_path) as new_ds:
                old_fields = {
                    name: (getattr(var, "units", ""), var.shape,
                           np.ma.asarray(var[:]).astype(np.float64).filled(np.nan).ravel(),
                           {"dimensions": tuple(var.dimensions)})
                    for name, var in old_ds.variables.items()
                    if np.issubdtype(var.dtype, np.number)
                }
                new_fields = {
                    name: (getattr(var, "units", ""), var.shape,
                           np.ma.asarray(var[:]).astype(np.float64).filled(np.nan).ravel(),
                           {"dimensions": tuple(var.dimensions)})
                    for name, var in new_ds.variables.items()
                    if np.issubdtype(var.dtype, np.number)
                }
        except (OSError, ValueError, KeyError) as exc:
            raise ValueError(f"NetCDF comparison failed: {old_path} -> {new_path}") from exc
    else:
        try:
            old_fields = read_wps(old_path)
            new_fields = read_wps(new_path)
        except (OSError, ValueError, KeyError, StopIteration) as exc:
            raise ValueError(f"WPS comparison failed: {old_path} -> {new_path}") from exc

    for key in sorted(set(old_fields) | set(new_fields), key=str):
        if key not in old_fields or key not in new_fields:
            summaries.append(f"    FIELD {'added' if key not in old_fields else 'missing'}: {key}")
            continue
        old_units, old_shape, old_values, old_metadata = old_fields[key]
        new_units, new_shape, new_values, new_metadata = new_fields[key]
        if old_shape != new_shape or old_units != new_units:
            summaries.append(
                f"    FIELD {key}: shape {old_shape}->{new_shape}, units {old_units!r}->{new_units!r}"
            )
            continue
        if old_metadata != new_metadata:
            changed_metadata = sorted(
                item for item in set(old_metadata) | set(new_metadata)
                if old_metadata.get(item) != new_metadata.get(item)
            )
            summaries.append(
                f"    FIELD {key}: metadata changed {','.join(changed_metadata)}"
            )
        old_valid = np.isfinite(old_values) & (np.abs(old_values) < 1.0e20)
        new_valid = np.isfinite(new_values) & (np.abs(new_values) < 1.0e20)
        common = old_valid & new_valid
        if np.any(common):
            delta = new_values[common] - old_values[common]
            rms = float(np.sqrt(np.mean(delta * delta)))
            maximum = float(np.max(np.abs(delta)))
        else:
            rms = maximum = float("nan")
        summaries.append(
            f"    FIELD {key}: valid {old_valid.sum()}->{new_valid.sum()}, "
            f"valid_mask_changed={np.count_nonzero(old_valid != new_valid)}, "
            f"rms_delta={rms:.7g}, max_abs_delta={maximum:.7g}"
        )
    return summaries


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    args = parser.parse_args()

    try:
        baseline, candidate = comparison_files(args.baseline, args.candidate)
    except (OSError, ValueError) as exc:
        print(f"COMPARISON ERROR: {exc}")
        return 2
    changed = 0
    parse_errors = 0
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
            try:
                for summary in numeric_summary(old, new):
                    print(summary)
            except (RuntimeError, ValueError) as exc:
                print(f"    PARSE ERROR: {exc}")
                parse_errors += 1
            changed += 1
        else:
            print(f"IDENTICAL {relative}")
    print(f"Compared {len(set(baseline) | set(candidate))} files; {changed} differ")
    if parse_errors:
        return 2
    return 1 if changed else 0


if __name__ == "__main__":
    raise SystemExit(main())
