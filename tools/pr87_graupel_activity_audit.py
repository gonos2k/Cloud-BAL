#!/usr/bin/env python3
"""Reclassify saved QG/BG snapshots by the frozen ProgB activity gates."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import tempfile
from pathlib import Path

import numpy as np

import pr85_joint_stage_trace as trace


FROZEN_SOURCE_SHA256 = "bdb1882afed860068cecbb6c7b958eef0938cadbd4225222ba7522e28ecc071a"
QCRMIN = np.float32(1.0e-9)
BRS_MIN = np.float32(1.0e-15)
RHO_MIN = 100.0
RHO_MAX = 900.0
CLASS_NAMES = ("ABSENT", "TRANSIENT", "ACTIVE_GATES_PASS", "UNSUPPORTED_PAIR", "UNSUPPORTED_DENSITY")


class ActivityAuditError(ValueError):
    """Inputs do not match the pinned trace or source contract."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _indices(record: dict, jki: tuple[int, int, int]) -> dict:
    j, k, i = jki
    bounds = record["bounds"]
    return {"i": i + bounds["its"], "j": j + bounds["jts"], "k": k + bounds["kts"]}


def _float32_bits(value: np.float32) -> str:
    return f"0x{int(np.asarray(value, dtype=np.float32).view(np.uint32)):08x}"


def _first_cell(mask: np.ndarray, record: dict, fields: dict) -> dict | None:
    positions = np.argwhere(mask)
    if not len(positions):
        return None
    j, k, i = map(int, positions[0])
    result = {"indices_ijk": _indices(record, (j, k, i)), "array_indices_jki": [j, k, i]}
    for name in ("QG", "BG", "DEN"):
        value = np.float32(fields[name][j, k, i])
        result[name] = {"value": float(value), "float32_bits": _float32_bits(value)}
    qg, bg = np.float32(fields["QG"][j, k, i]), np.float32(fields["BG"][j, k, i])
    result["qg_bg_density_kg_m3"] = float(np.float64(qg) / np.float64(bg)) if bg != 0 else None
    return result


def classify_state(record: dict) -> dict:
    """Apply ProgB's saved-state pair, transient, and raw-density gates."""
    fields = record["fields"]
    qg = np.asarray(fields["QG"], dtype=np.float32)
    bg = np.asarray(fields["BG"], dtype=np.float32)
    den = np.asarray(fields["DEN"], dtype=np.float32)
    if qg.shape != bg.shape or qg.shape != den.shape:
        raise ActivityAuditError("QG, BG, and DEN shapes differ")

    finite = np.isfinite(qg) & np.isfinite(bg)
    absent = finite & (qg == 0.0) & (bg == 0.0)
    positive_pair = finite & (qg > 0.0) & (bg > 0.0)
    transient = positive_pair & (qg <= QCRMIN) & (bg <= BRS_MIN)
    density = np.full(qg.shape, np.nan, dtype=np.float64)
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        np.divide(qg.astype(np.float64), bg.astype(np.float64), out=density, where=positive_pair)
    density_ok = positive_pair & ~transient & np.isfinite(density) & (density >= RHO_MIN) & (density <= RHO_MAX)
    unsupported_density = positive_pair & ~transient & ~density_ok
    unsupported_pair = ~(absent | positive_pair)
    classes = np.full(qg.shape, "UNSUPPORTED_PAIR", dtype=object)
    classes[absent] = "ABSENT"
    classes[transient] = "TRANSIENT"
    classes[density_ok] = "ACTIVE_GATES_PASS"
    classes[unsupported_density] = "UNSUPPORTED_DENSITY"

    finite_den = np.isfinite(den)
    cone_density = positive_pair & np.isfinite(density) & (density >= RHO_MIN) & (density <= RHO_MAX)
    result = {
        "timestep": record["timestep"], "stage": record["stage"], "rkstep": record["rkstep"],
        "counts": {name: int(np.count_nonzero(classes == name)) for name in CLASS_NAMES},
        "stored_pair": {
            "finite_qg_bg_cells": int(finite.sum()),
            "nonfinite_qg_or_bg_cells": int((~finite).sum()),
            "positive_pair_cells": int(positive_pair.sum()),
            "orphan_or_negative_pair_cells": int(unsupported_pair.sum()),
            "exact_qg_bg_density_cone_cells": int(cone_density.sum()),
            "exact_qg_bg_density_cone": [RHO_MIN, RHO_MAX],
        },
        "host_dry_density": {
            "finite_positive_cells": int((finite_den & (den > 0)).sum()),
            "nonfinite_or_nonpositive_cells": int((~finite_den | (den <= 0)).sum()),
        },
        "first_by_class": {name: _first_cell(classes == name, record, fields) for name in CLASS_NAMES},
        "interpretation": "ACTIVE_GATES_PASS reproduces the source pair/transient/raw-density gates; ProgB's later derived-parameter finite checks are not recorded in this snapshot.",
    }
    return result


def _read_trace(path: Path) -> dict:
    before = sha256(path)
    with tempfile.TemporaryDirectory(prefix="pr87_activity_") as temp:
        expanded = Path(temp) / "moment_stages.raw"
        with gzip.open(path, "rb") as compressed, expanded.open("wb") as raw:
            while block := compressed.read(8 * 1024 * 1024):
                raw.write(block)
        decoded = trace.read_records(expanded)
    if sha256(path) != before:
        raise ActivityAuditError("saved trace changed during read")
    return {"path": str(path), "sha256": before, "bytes": path.stat().st_size,
            "decoded_sha256": decoded["sha256"], "records": decoded["records"]}


def audit(trace_path: Path, source_path: Path) -> dict:
    source_hash = sha256(source_path)
    if source_hash != FROZEN_SOURCE_SHA256:
        raise ActivityAuditError(f"source SHA-256 mismatch: expected {FROZEN_SOURCE_SHA256}, got {source_hash}")
    saved = _read_trace(trace_path)
    states = [classify_state(item) for item in saved["records"] if item["kind"] == 1]
    if not states or not any(item["stage"] == "PRE_KDM6" and item["timestep"] == 3 for item in states):
        raise ActivityAuditError("trace is missing the required T3 PRE_KDM6 state")
    return {
        "schema": "pr87_graupel_activity_audit_v1",
        "source": {"path": str(source_path), "sha256": source_hash,
                   "binding": "exact frozen module_mp_kdm6.F SHA-256; source gates at ProgB_param"},
        "trace": {key: saved[key] for key in ("path", "sha256", "bytes", "decoded_sha256")},
        "states": states,
        "t3_pre_kdm6": next(item for item in states if item["stage"] == "PRE_KDM6" and item["timestep"] == 3),
        "source_conditions": {
            "absent": "finite QG=0 and BG=0",
            "transient": "finite QG>0 and BG>0 and QG<=REAL32(1e-9) and BG<=REAL32(1e-15)",
            "active_gates_pass": "positive pair, not transient, finite REAL64(QG)/REAL64(BG) in inclusive [100,900] kg m-3",
            "limitation": "This is a saved-state source-gate classification; it does not read native progb_status or replay ProgB's downstream derived gamma/PSD finite checks, so it cannot prove the actual fatal cell or cause.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path, help="saved pr85_joint_moment_stages.raw.gz")
    parser.add_argument("source", type=Path, help="frozen actual compiled module_mp_kdm6.F")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        report = audit(args.trace, args.source)
    except (ActivityAuditError, trace.TraceError, OSError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "source_sha256": report["source"]["sha256"],
                      "trace_sha256": report["trace"]["sha256"],
                      "t3_pre_kdm6_counts": report["t3_pre_kdm6"]["counts"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
