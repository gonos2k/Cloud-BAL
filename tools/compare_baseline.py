#!/usr/bin/env python3
"""Read-only byte/checksum comparison of an isolated legacy baseline and rerun.

The WPS intermediate files in this workflow are not NetCDF, so this first gate
intentionally compares the archived files without rewriting or normalizing
them.  A nonzero exit means at least one selected output changed or is absent.
"""

from __future__ import annotations

import argparse
import hashlib
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
    return {
        path.relative_to(root): path
        for path in root.rglob("*")
        if path.is_file() and path.name not in {"README.md", "SHA256SUMS"}
    }


def _records(path: Path):
    """Yield Fortran sequential-unformatted records and detected endianness."""
    with path.open("rb") as stream:
        marker = stream.read(4)
        if len(marker) != 4:
            return
        endian = ">" if struct.unpack(">i", marker)[0] == 4 else "<"
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
        nx, ny, _projection = struct.unpack(endian + "iii", metadata[144:156])
        next(records)  # projection metadata
        next(records)  # wind-relative flag
        _, slab_record = next(records)
        if len(slab_record) != 4 * nx * ny:
            raise ValueError("WPS slab size does not match metadata")
        slab = np.frombuffer(slab_record, dtype=endian + "f4").astype(np.float64)
        fields[(field, level, hdate)] = (units, (nx, ny), slab)
    return fields


def numeric_summary(old_path: Path, new_path: Path) -> list[str]:
    """Return field-level differences for NetCDF or WPS intermediate files."""
    summaries: list[str] = []
    try:
        if old_path.suffix == ".nc" and new_path.suffix == ".nc":
            from netCDF4 import Dataset

            with Dataset(old_path) as old_ds, Dataset(new_path) as new_ds:
                old_fields = {
                    name: (getattr(var, "units", ""), var.shape,
                           np.ma.filled(var[:], np.nan).astype(np.float64).ravel())
                    for name, var in old_ds.variables.items()
                    if np.issubdtype(var.dtype, np.number)
                }
                new_fields = {
                    name: (getattr(var, "units", ""), var.shape,
                           np.ma.filled(var[:], np.nan).astype(np.float64).ravel())
                    for name, var in new_ds.variables.items()
                    if np.issubdtype(var.dtype, np.number)
                }
        else:
            old_fields = read_wps(old_path)
            new_fields = read_wps(new_path)
    except (ImportError, OSError, ValueError, KeyError, StopIteration):
        return summaries

    for key in sorted(set(old_fields) | set(new_fields), key=str):
        if key not in old_fields or key not in new_fields:
            summaries.append(f"    FIELD {'added' if key not in old_fields else 'missing'}: {key}")
            continue
        old_units, old_shape, old_values = old_fields[key]
        new_units, new_shape, new_values = new_fields[key]
        if old_shape != new_shape or old_units != new_units:
            summaries.append(
                f"    FIELD {key}: shape {old_shape}->{new_shape}, units {old_units!r}->{new_units!r}"
            )
            continue
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
            f"rms_delta={rms:.7g}, max_abs_delta={maximum:.7g}"
        )
    return summaries


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
            for summary in numeric_summary(old, new):
                print(summary)
            changed += 1
        else:
            print(f"IDENTICAL {relative}")
    print(f"Compared {len(set(baseline) | set(candidate))} files; {changed} differ")
    return 1 if changed else 0


if __name__ == "__main__":
    raise SystemExit(main())
