#!/usr/bin/env python3
"""Compare two actual WRF initial states, recording numerical differences."""
import argparse
import hashlib
import json
from pathlib import Path

import netCDF4
import numpy as np


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("original", type=Path)
    parser.add_argument("current", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        raise FileExistsError(args.output)
    result = {"inputs": {str(p): sha256(p) for p in (args.original, args.current)},
              "fields": {}, "metadata_differences": {}}
    with netCDF4.Dataset(args.original) as original, netCDF4.Dataset(args.current) as current:
        if set(original.variables) != set(current.variables):
            raise ValueError("variable inventories differ")
        for name in original.variables:
            a, b = original[name], current[name]
            if a.dimensions != b.dimensions or a.shape != b.shape or a.dtype != b.dtype:
                raise ValueError(f"incompatible field {name}")
            av, bv = a[:], b[:]
            if np.ma.is_masked(av) or np.ma.is_masked(bv):
                raise ValueError(f"masked field {name}")
            if not np.issubdtype(a.dtype, np.number):
                result["fields"][name] = {"equal": bool(np.array_equal(av, bv))}
                continue
            av, bv = np.asarray(av, dtype=np.float64), np.asarray(bv, dtype=np.float64)
            if not (np.isfinite(av).all() and np.isfinite(bv).all()):
                raise ValueError(f"nonfinite field {name}")
            delta = np.abs(bv - av)
            result["fields"][name] = {"shape": list(a.shape), "units": getattr(a, "units", ""),
                "changed_count": int(np.count_nonzero(delta)), "size": int(delta.size),
                "max_abs_difference": float(np.max(delta)), "mean_abs_difference": float(np.mean(delta)),
                "original": {"min": float(np.min(av)), "max": float(np.max(av)),
                             "mean": float(np.mean(av)), "positive_count": int(np.count_nonzero(av > 0))},
                "current": {"min": float(np.min(bv)), "max": float(np.max(bv)),
                            "mean": float(np.mean(bv)), "positive_count": int(np.count_nonzero(bv > 0))}}
        for name in sorted(set(original.ncattrs()) | set(current.ncattrs())):
            a, b = getattr(original, name, None), getattr(current, name, None)
            if not np.array_equal(a, b):
                result["metadata_differences"][name] = {"original": str(a), "current": str(b)}
    result["inputs_after"] = {str(p): sha256(p) for p in (args.original, args.current)}
    if result["inputs_after"] != result["inputs"]:
        raise ValueError("an input changed during comparison")
    with args.output.open("x") as stream:
        stream.write(json.dumps(result, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
