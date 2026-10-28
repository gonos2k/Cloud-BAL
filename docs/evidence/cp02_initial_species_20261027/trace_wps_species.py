#!/usr/bin/env python3
"""Compare archived QR/QS WPS records with the paired shadow state by pressure."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from netCDF4 import Dataset

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "tools"))
from compare_baseline import read_wps

ARCHIVE = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/Cloud-BAL/scratch")
PAIR = ARCHIVE / "cp02_actual12_liquid_wps.HisIOM"
DATE = "2026-08-16_12:00:00.0000"


def pin(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "path": str(path),
        "sha256": digest.hexdigest(),
        "bytes": path.stat().st_size,
    }


def compare(wps, shadow_path, prefix):
    rows = []
    with Dataset(shadow_path) as shadow:
        for field, species in (("QR", "rain"), ("QS", "snow")):
            for k, pressure in enumerate(shadow["pressure"][:]):
                key = (field, float(pressure), DATE)
                if key not in wps:
                    continue  # 1100 and 1050 hPa are not emitted by this writer.
                units, shape, values, metadata = wps[key]
                if units != "kg kg{-1}" or shape != (235, 283):
                    raise ValueError(
                        f"Unexpected WPS units/shape: {key}: {units}, {shape}"
                    )
                reference = np.ma.asarray(shadow[f"{prefix}_{species}"][k])
                if (
                    np.ma.getmaskarray(reference).any()
                    or not np.isfinite(reference).all()
                ):
                    raise ValueError(f"Invalid shadow values: {key}")
                slab = values.reshape(shape[::-1])
                if not np.isfinite(slab).all():
                    raise ValueError(f"Invalid WPS values: {key}")
                delta = slab - reference
                rows.append(
                    {
                        "field": field,
                        "pressure_pa": float(pressure),
                        "projection_record_sha256": metadata["projection_record_sha256"],
                        "exact_equal": bool(np.array_equal(slab, reference)),
                        "changed_cells": int(np.count_nonzero(delta)),
                        "max_abs_difference_kgkg": float(np.max(np.abs(delta))),
                    }
                )
    if len(rows) != 40:
        raise ValueError(
            f"Expected 20 pressure records for each species, got {len(rows)}"
        )
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    sources, checks = [], {}
    for arm in ("HYDRO", "LIQUID_RADAR_RH1"):
        path = PAIR / f"{arm}_vapor2.wps"
        shadow = PAIR / f"{arm}_vapor2.wps.shadow.nc"
        sources.extend((pin(path), pin(shadow)))
        rows = compare(read_wps(path), shadow, "candidate")
        checks[arm] = rows
    original = ARCHIVE / "cp02_native_12_15.B4Lwmh/metgrid/LAPS:2026-08-16_12:00"
    sources.append(pin(original))
    checks["ACTUAL_OFF_WPS_VS_HYDRO_SHADOW_BACKGROUND"] = compare(
        read_wps(original), PAIR / "HYDRO_vapor2.wps.shadow.nc", "background"
    )
    for label, rows in checks.items():
        if not all(row["exact_equal"] for row in rows):
            raise ValueError(f"{label} WPS differs from shadow")
    geometries = {row["projection_record_sha256"] for rows in checks.values() for row in rows}
    if len(geometries) != 1:
        raise ValueError("WPS projection records differ across compared inputs")
    for expected in sources:
        if pin(Path(expected["path"])) != expected:
            raise RuntimeError(f'Input changed: {expected["path"]}')
    result = {
        "status": "PASS_SCOPED_WPS_READBACK",
        "sources": sources,
        "reader": pin(REPO / "tools/compare_baseline.py"),
        "checks": checks,
        "shared_projection_record_sha256": next(iter(geometries)),
        "scope": "Full horizontal slabs at shared pressures only. The two extra shadow levels and WPS surface record are excluded. Does not reconstruct historical source arithmetic or prove forecast causality.",
    }
    text = json.dumps(result, indent=2, allow_nan=False) + "\n"
    with args.output.open("x") as stream:
        stream.write(text)


if __name__ == "__main__":
    main()
