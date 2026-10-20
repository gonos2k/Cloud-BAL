#!/usr/bin/env python3
"""Summarize receipt-bound C14 P, PH, and W responses by native-grid scope."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import netCDF4
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "pr89_paired_history", ROOT / "tools/pr89_paired_history.py")
paired = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(paired)

FIELDS = {"pressure": ("P+PB", "Pa"),
          "geopotential": ("PH+PHB", "m2 s-2"),
          "vertical_velocity": ("W", "m s-1")}
TIMES = (0, 60, 120, 180, 240)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def receipt_identity(receipt_path: Path, history: Path, arm: str) -> dict[str, Any]:
    receipt = json.loads(receipt_path.read_text())
    if receipt.get("arm") != arm or receipt.get("status") != "COMPLETE" or receipt.get("returncode") != 0:
        raise ValueError(f"{receipt_path} is not a successful COMPLETE {arm} receipt")
    bindings = {Path(row["path"]).name: row["sha256"]
                for row in receipt.get("generated_files", []) if "path" in row and "sha256" in row}
    if bindings.get(history.name) != sha256(history):
        raise ValueError(f"{history} is not hash-bound by its {arm} receipt")
    if receipt.get("executed_executable_sha256") != \
            "5581e1be3febd54409304ccf7cbe305830a75968858075bf0d95f68b48d812be":
        raise ValueError(f"{receipt_path} does not bind the pinned C14 executable")
    if receipt.get("final_completed_step") != 12 or receipt.get("timestep_count") != 12:
        raise ValueError(f"{receipt_path} does not bind exactly twelve completed C14 steps")
    return {"arm": arm, "receipt": str(receipt_path), "receipt_sha256": sha256(receipt_path),
            "history": str(history), "history_sha256": sha256(history),
            "candidate_wrfinput_sha256": receipt.get("candidate_wrfinput_sha256"),
            "candidate_wrfbdy_sha256": receipt.get("candidate_wrfbdy_sha256")}


def scopes(support: np.ndarray) -> dict[str, np.ndarray]:
    ny, nx = support.shape
    interior = np.zeros_like(support)
    interior[1:-1, 1:-1] = True
    neighbors = np.zeros_like(support)
    for dj in (-1, 0, 1):
        for di in (-1, 0, 1):
            if (dj, di) == (0, 0):
                continue
            neighbors[max(0, dj):ny + min(0, dj), max(0, di):nx + min(0, di)] |= \
                support[max(0, -dj):ny - max(0, dj), max(0, -di):nx - max(0, di)]
    return {"whole_grid": np.ones_like(support),
            "interior_boundary_ring_excluded": interior,
            "domain_boundary_ring": ~interior,
            "fixed_C14_T0_water_support": support,
            "one_cell_neighbor_of_fixed_support": neighbors & ~support}


def stats(delta: np.ndarray, mask: np.ndarray) -> dict[str, Any]:
    selected = delta[..., mask]
    return {"horizontal_columns": int(mask.sum()), "selected_values": int(selected.size),
            "signed_total": float(selected.sum(dtype=np.float64)),
            "signed_mean": float(selected.mean()) if selected.size else None,
            "mean_absolute": float(np.abs(selected).mean()) if selected.size else None,
            "max_absolute": float(np.max(np.abs(selected))) if selected.size else None,
            "rms": float(np.sqrt(np.mean(selected * selected))) if selected.size else None}


def analyze(off_history: Path, coupled_history: Path, off_receipt: Path,
            coupled_receipt: Path) -> dict[str, Any]:
    identity = {
        "OFF": receipt_identity(off_receipt, off_history, "OFF"),
        "COUPLED": receipt_identity(coupled_receipt, coupled_history, "COUPLED")}
    grid_check = paired._verify_static_geometry(off_history, coupled_history)
    off_index, grid = paired._records(off_history)
    coupled_index, coupled_grid = paired._records(coupled_history)
    paired._pair_geometry(grid, coupled_grid)
    if sorted(off_index) != sorted(coupled_index) or len(off_index) != 5:
        raise ValueError("C14 arms must have the same five history snapshots")
    ordered_times = sorted(off_index)
    elapsed = [int((when - ordered_times[0]).total_seconds()) for when in ordered_times]
    if elapsed != list(TIMES):
        raise ValueError(f"C14 history timestamps must be exactly {list(TIMES)} seconds apart; got {elapsed}")
    with netCDF4.Dataset(off_history) as off, netCDF4.Dataset(coupled_history) as coupled:
        off.set_auto_mask(False); coupled.set_auto_mask(False)
        support = np.zeros(grid["shape"], dtype=bool)
        for name in paired.native.WATER:
            support |= np.any(np.asarray(off.variables[name][0]) !=
                               np.asarray(coupled.variables[name][0]), axis=0)
    if int(support.sum()) != 27:
        raise ValueError(f"expected the documented fixed C14 T0 water support of 27 columns, found {support.sum()}")
    masks = scopes(support)
    by_time = []
    for elapsed_seconds, when in zip(elapsed, ordered_times):
        row = {"elapsed_seconds": elapsed_seconds, "fields": {}}
        a = paired._load_snapshot(off_history, off_index, when, grid, 9.8100004196167)
        b = paired._load_snapshot(coupled_history, coupled_index, when, coupled_grid, 9.8100004196167)
        for label, (name, units) in FIELDS.items():
            delta = b[name] - a[name]
            row["fields"][label] = {"source_fields": name, "units": units,
                                    "shape": list(delta.shape),
                                    "scopes": {scope: stats(delta, mask) for scope, mask in masks.items()}}
        by_time.append(row)
    return {"schema": "pr92_c14_native_field_scopes_v1",
            "scope": "Receipt-bound descriptive COUPLED-minus-OFF same-time history response; native fields and levels retained without interpolation.",
            "times_elapsed_seconds": list(TIMES), "fixed_support_columns": 27,
            "support_definition": "mass-grid columns where any native water tracer differs between the two arms at T0",
            "run_identity": identity, "static_geometry_check": grid_check,
            "field_responses": by_time,
            "interpretation_limit": "Analysis-arm response only; not observational skill, pure-model causal effect, QC-only influence, or full native vertical support attribution."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--off-history", type=Path, required=True)
    parser.add_argument("--coupled-history", type=Path, required=True)
    parser.add_argument("--off-receipt", type=Path, required=True)
    parser.add_argument("--coupled-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite {args.output}")
    result = analyze(args.off_history, args.coupled_history, args.off_receipt,
                     args.coupled_receipt)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
