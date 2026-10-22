#!/usr/bin/env python3
"""Read and summarize private PR98 native observer stream snapshots."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
from typing import Any

import numpy as np


def read_capture(path: Path, rank: int) -> tuple[dict[str, Any], np.ndarray]:
    """Read a Fortran stream snapshot; rank is explicit to avoid shape guessing."""
    data = path.read_bytes()
    header_items = {0: 0, 1: 4, 2: 8, 3: 12}.get(rank)
    if header_items is None:
        raise ValueError("rank must be 0, 1, 2, or 3")
    header_bytes = 4 * header_items
    if len(data) < header_bytes:
        raise ValueError(f"truncated capture header: {path}")
    # The pinned compile recipe passes -convert big_endian for Fortran stream IO.
    bounds = struct.unpack(">" + "i" * header_items, data[:header_bytes]) if header_items else ()
    values = np.frombuffer(data, dtype=">f4", offset=header_bytes)
    if rank == 0:
        shape = ()
        axes = []
    elif rank == 1:
        shape = (bounds[1] - bounds[0] + 1,)
        axes = ["k"]
    elif rank == 2:
        shape = (bounds[1] - bounds[0] + 1, bounds[3] - bounds[2] + 1)
        axes = ["i", "j"]
    else:
        shape = (bounds[1] - bounds[0] + 1, bounds[3] - bounds[2] + 1,
                 bounds[5] - bounds[4] + 1)
        axes = ["i", "k", "j"]
    expected = int(np.prod(shape, dtype=np.int64)) if shape else 1
    if values.size != expected:
        raise ValueError(f"capture payload size mismatch: {path} expected {expected}, got {values.size}")
    array = values.reshape(shape, order="F")
    metadata = {"path": str(path), "sha256": hashlib.sha256(data).hexdigest(),
                "rank": rank, "fortran_bounds": list(bounds), "shape_fortran": list(shape),
                "axes": axes,
                "bytes": len(data), "finite": bool(np.isfinite(array).all())}
    return metadata, array


def summarize(array: np.ndarray) -> dict[str, float | int]:
    """Return compact descriptive statistics without implying physical closure."""
    values = np.asarray(array, dtype=np.float64).ravel()
    if values.size == 0 or not np.isfinite(values).all():
        raise ValueError("capture array must be nonempty and finite")
    return {"n": int(values.size), "sum": float(np.sum(values, dtype=np.float64)),
            "mean": float(np.mean(values)), "rms": float(np.sqrt(np.mean(values * values))),
            "l2": float(np.linalg.norm(values)), "max_abs": float(np.max(np.abs(values))),
            "min": float(np.min(values)), "max": float(np.max(values))}


def inventory(run_root: Path) -> dict[str, Any]:
    """Record snapshot hashes and compact metrics; never copy array payloads."""
    run_root = run_root.resolve()
    rows = []
    for path in sorted(run_root.glob("pr98_*.bin")):
        name = path.name
        if name.startswith("pr98_dts_"):
            rank = 0
        elif name.startswith("pr98_geom_c"):
            rank = 1
        elif name.startswith(("pr98_mu_", "pr98_mudf_")):
            rank = 2
        elif "_tend" in name or name.startswith(("pr98_dyn_", "pr98_assembled_")):
            rank = 3
        else:
            rank = 2
        meta, array = read_capture(path, rank)
        meta["summary"] = summarize(array)
        rows.append(meta)
    return {"schema": "pr98_native_capture_inventory_v1", "run_root": str(run_root),
            "snapshot_count": len(rows), "snapshots": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_root", type=Path, help="run directory containing pr98_*.bin")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = inventory(args.run_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({"run_root": str(args.run_root), "snapshot_count": result["snapshot_count"],
                      "inventory": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
