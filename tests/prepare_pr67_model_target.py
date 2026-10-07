#!/usr/bin/env python3
"""Create a scratch model-target copy with support narrowed to actual input."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import stat
from pathlib import Path

import netCDF4
import numpy as np


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_new_output(source: Path, output: Path) -> None:
    try:
        source_mode = source.lstat().st_mode
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"source target is missing: {source}") from exc
    if not stat.S_ISREG(source_mode):
        raise ValueError(f"source target must be a regular non-symlink file: {source}")
    if os.path.lexists(output):
        raise FileExistsError(f"output path already exists: {output}")
    if output.resolve(strict=False) == source.resolve(strict=True):
        raise ValueError("output path aliases the source target")


def read_masks(path: Path, nx: int, ny: int, nz: int) -> tuple[np.ndarray, np.ndarray]:
    raw = np.fromfile(path, dtype=np.int32)
    cells = nx * ny * nz
    if raw.size != 2 * cells:
        raise ValueError(f"expected {2 * cells} mask values, got {raw.size}")
    shape_xyz = (nx, ny, nz)
    target = raw[:cells].reshape(shape_xyz, order="F").transpose(2, 1, 0).copy()
    coverage = raw[cells:].reshape(shape_xyz, order="F").transpose(2, 1, 0).copy()
    return target, coverage


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("masks", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    require_new_output(args.source, args.output)
    source_hash = sha256(args.source)
    with netCDF4.Dataset(args.source, "r") as original:
        target, coverage = read_masks(args.masks, len(original.dimensions["x"]),
                                      len(original.dimensions["y"]),
                                      len(original.dimensions["z"]))
        original_target = np.asarray(original.variables["target_mask"][:], dtype=np.int32)
        original_coverage = np.asarray(original.variables["coverage_mask"][:], dtype=np.int32)
        if target.shape != original_target.shape or coverage.shape != original_coverage.shape:
            raise ValueError("derived masks do not match target artifact dimensions")
        if not np.isin(target, (0, 1)).all() or not np.isin(coverage, (0, 1)).all():
            raise ValueError("derived masks are not binary")
        if np.any(target > original_target) or np.any(coverage > original_coverage):
            raise ValueError("support derivation widened the source masks")
        if np.any(target > coverage):
            raise ValueError("target mask extends beyond derived coverage")
        if int(original_target.sum()) != 892339 or int(original_coverage.sum()) != 1150135:
            raise ValueError("source masks differ from the pinned paired target")
        if int(target.sum()) != 892338 or int(coverage.sum()) != 1150134:
            raise ValueError("derived masks differ from the measured support filter")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    require_new_output(args.source, args.output)
    shutil.copy2(args.source, args.output)
    with netCDF4.Dataset(args.source, "r") as original, netCDF4.Dataset(
        args.output, "r+"
    ) as derived:
        for name in original.variables:
            if name in {"target_mask", "coverage_mask"}:
                continue
            before = np.asarray(original.variables[name][:])
            after = np.asarray(derived.variables[name][:])
            if not np.array_equal(before, after, equal_nan=True):
                raise ValueError(f"non-mask variable changed in copied artifact: {name}")
        derived.variables["target_mask"][:] = target
        derived.variables["coverage_mask"][:] = coverage
        derived.setncattr("pr67_source_target_sha256", source_hash)
        derived.setncattr(
            "pr67_support_derivation",
            "source masks intersected with the exact 13 UTC reader above_ground; "
            "target cells retained only when model_target_level_is_interior is true",
        )
        derived.setncattr("pr67_support_cells_removed_from_coverage", 1)
        derived.setncattr("pr67_target_cells_removed_without_interior_support", 1)
        derived.sync()

    print(f"source_target_sha256={source_hash}")
    print(f"source_mask_sha256={sha256(args.masks)}")
    print(f"derived_target_sha256={sha256(args.output)}")
    print(f"derived_target_cells={int(target.sum())}")
    print(f"derived_coverage_cells={int(coverage.sum())}")
    print("retained_nonmask_variables=EXACT")
    print("support_widened=FALSE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
