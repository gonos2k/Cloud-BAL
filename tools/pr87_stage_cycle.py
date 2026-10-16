#!/usr/bin/env python3
"""Replay the saved POST_KDM6 cloud state against the native zero-out cutoff."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import struct
from pathlib import Path
from typing import BinaryIO

import numpy as np


STATE_MAGICS = {b"PR85QND2", b"PR85QNB1"}
TENDENCY_MAGIC = b"PR85PLB1"
STATE_FIELDS = ("DEN", "Q", "QC", "QI", "QR", "QS", "QG", "NN", "NC", "NI", "NR", "BG")


class TraceError(ValueError):
    """Raised when a saved stage stream is incomplete or malformed."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_exact(stream: BinaryIO, count: int, label: str) -> bytes:
    data = stream.read(count)
    if len(data) != count:
        raise TraceError(f"truncated {label}: expected {count} bytes, got {len(data)}")
    return data


def _open_stream(path: Path) -> BinaryIO:
    with path.open("rb") as source:
        compressed = source.read(2) == b"\x1f\x8b"
    return gzip.open(path, "rb") if compressed else path.open("rb")


def read_post_kdm6(path: Path, *, timestep: int = 1) -> dict:
    """Read QC and NC from exactly one POST_KDM6 state record."""
    matches = []
    with _open_stream(path) as stream:
        while magic := stream.read(8):
            if magic not in STATE_MAGICS | {TENDENCY_MAGIC}:
                raise TraceError(f"unknown record magic: {magic!r}")
            label = _read_exact(stream, 32, "stage label").decode("ascii").strip()
            header = struct.unpack(">15i", _read_exact(stream, 15 * 4, "record header"))
            kind, record_timestep, rkstep, *raw_bounds = header
            is_state = magic in STATE_MAGICS
            expected_kind = 1 if is_state else 2
            if kind != expected_kind:
                raise TraceError(f"record kind disagrees with magic for {label}")
            (ims, ime, jms, jme, kms, kme,
             its, ite, jts, jte, kts, kte) = raw_bounds
            shape = (jte - jts + 1, kte - kts + 1, ite - its + 1)
            if min(shape) <= 0:
                raise TraceError(f"invalid active bounds for {label}: {raw_bounds}")
            cells = int(np.prod(shape))
            target = is_state and label == "POST_KDM6" and record_timestep == timestep
            if is_state:
                selected = {}
                for name in STATE_FIELDS:
                    raw = _read_exact(stream, cells * 4, f"{label} {name}")
                    if target and name in ("QC", "NC"):
                        selected[name] = np.frombuffer(raw, dtype=">f4").astype(np.float32).reshape(shape)
            else:
                for name in ("QV_TEND", "QC_TEND", "QI_TEND", "QNC_TEND", "QNI_TEND"):
                    _read_exact(stream, cells * 4, f"{label} {name}")
            if target:
                matches.append({
                    "stage": label, "timestep": record_timestep, "rkstep": rkstep,
                    "bounds": {key: value for key, value in zip(
                        ("ims", "ime", "jms", "jme", "kms", "kme",
                         "its", "ite", "jts", "jte", "kts", "kte"), raw_bounds, strict=True)},
                    "shape_jki": list(shape), "QC": selected["QC"], "NC": selected["NC"],
                    "magic": magic.decode("ascii"),
                })
    if len(matches) != 1:
        raise TraceError(f"expected one POST_KDM6 timestep {timestep} record, found {len(matches)}")
    return matches[0]


def _cycle_summary(record: dict, threshold: float) -> dict:
    qc, nc = record["QC"], record["NC"]
    direct_orphan = (qc == 0) & (nc > 0)
    below_cutoff = (qc > 0) & (qc < threshold) & (nc > 0)
    cells = []
    bounds = record["bounds"]
    for j_offset, k_offset, i_offset in np.argwhere(below_cutoff):
        cells.append({
            "i": int(i_offset + bounds["its"]),
            "j": int(j_offset + bounds["jts"]),
            "k": int(k_offset + bounds["kts"]),
            "POST_KDM6_QC": float(qc[j_offset, k_offset, i_offset]),
            "POST_KDM6_QNC": float(nc[j_offset, k_offset, i_offset]),
            "predicted_after_zero_outa_QC": 0.0,
            "predicted_after_zero_outa_QNC": float(nc[j_offset, k_offset, i_offset]),
        })
    return {
        "stage": record["stage"], "timestep": record["timestep"], "rkstep": record["rkstep"],
        "magic": record["magic"], "bounds": record["bounds"], "shape_jki": record["shape_jki"],
        "threshold": threshold,
        "direct_zero_QC_positive_QNC_cells_at_snapshot": int(direct_orphan.sum()),
        "positive_QC_below_threshold_with_positive_QNC_cells": len(cells),
        "candidate_cells": cells,
        "prediction_basis": "microphysics_zero_outa sets moist fields below mp_zero_out_thresh to zero; scalar QNC is only passed through zero_outa when mp_zero_out_all > 0",
        "runtime_observation": False,
    }


def analyze(off_path: Path, coupled_path: Path, threshold: float = 1e-8) -> dict:
    if not np.isfinite(threshold) or threshold <= 0:
        raise ValueError("threshold must be finite and positive")
    summaries = {}
    records = {}
    for arm, path in (("OFF", off_path), ("COUPLED", coupled_path)):
        record = read_post_kdm6(path)
        records[arm] = record
        summaries[arm] = {"path": str(path), "sha256": sha256(path),
                           **_cycle_summary(record, threshold)}
    same_bounds = summaries["OFF"]["bounds"] == summaries["COUPLED"]["bounds"]
    if not same_bounds:
        raise TraceError("OFF and COUPLED POST_KDM6 supports differ")
    same_candidates = (summaries["OFF"]["candidate_cells"] ==
                       summaries["COUPLED"]["candidate_cells"])
    return {
        "schema": "pr87_post_kdm6_zero_out_cycle_v1",
        "scope": "Saved timestep-1 POST_KDM6 state screened for the configured native moisture zero-out threshold.",
        "cycle": ["POST_KDM6(1)", "microphysics_zero_outb/a", "next PBL call / FogDES input"],
        "comparison": {"same_active_bounds": same_bounds,
                       "candidate_cells_exactly_equal": same_candidates},
        "arms": summaries,
        "limitations": [
            "The archive has no state dump after microphysics_zero_outa and no timestep-2 FogDES-entry field dump.",
            "Candidate cells are predicted from source semantics; their timestep-2 values are not directly observed here.",
            "FogDES loop support must be checked against the runtime tile bounds and vertical bounds.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--off", type=Path, required=True)
    parser.add_argument("--coupled", type=Path, required=True)
    parser.add_argument("--threshold", type=float, default=1e-8)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = analyze(args.off, args.coupled, args.threshold)
    encoded = json.dumps(result, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")


if __name__ == "__main__":
    main()
