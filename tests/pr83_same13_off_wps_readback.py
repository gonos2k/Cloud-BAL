#!/usr/bin/env python3
"""Read back the 13 UTC MODE_OFF replay through the PR82 WPS mapper/writer."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from compare_baseline import read_wps


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def field(fields, short: str, level: float):
    keys = [key for key in fields if key[0] == short and key[1] == level]
    if len(keys) != 1:
        raise ValueError(f"expected one {short}@{level} WPS record, found {len(keys)}")
    key = keys[0]
    unit, shape, flat, metadata = fields[key]
    nx, ny = shape
    values = np.asarray(flat, dtype=np.float32).reshape((nx, ny), order="F")
    return key, unit, values, metadata


def read_inventory(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    record_length = int.from_bytes(raw[:4], "big")
    if record_length != 12 or int.from_bytes(raw[16:20], "big") != 12:
        raise ValueError("captured LAPSPREP inventory dimension record is invalid")
    nx, ny, nz = np.frombuffer(raw, dtype=">i4", count=3, offset=4).astype(int)
    payload_length = int.from_bytes(raw[20:24], "big")
    if int.from_bytes(raw[24 + payload_length:28 + payload_length], "big") != payload_length:
        raise ValueError("captured LAPSPREP inventory payload is truncated")
    if 28 + payload_length != len(raw):
        raise ValueError("captured LAPSPREP inventory has trailing bytes")
    data = np.frombuffer(raw, dtype=">f4", count=payload_length // 4, offset=24)
    offset = 0

    def take(shape: tuple[int, ...]) -> np.ndarray:
        nonlocal offset
        count = int(np.prod(shape))
        values = data[offset:offset + count].astype(np.float32).reshape(shape, order="F")
        if values.size != count:
            raise ValueError("captured LAPSPREP inventory does not match its schema")
        offset += count
        return values

    profiles = (nx, ny, nz + 1)
    hydro = (nx, ny, nz)
    surface = (nx, ny)
    result: dict[str, object] = {
        "dims": (nx, ny, nz), "p": take((nz + 1,)),
    }
    for name in ("t", "ht", "u", "v", "rh", "qv"):
        result[name] = take(profiles)
    for name in ("qc", "qi", "qr", "qs", "qg"):
        result[name] = take(hydro)
    for name in ("psfc", "slp", "skin", "snow"):
        result[name] = take(surface)
    if offset != data.size:
        raise ValueError("captured LAPSPREP inventory field layout differs")
    if not all(np.isfinite(values).all() for values in result.values()
               if isinstance(values, np.ndarray)):
        raise ValueError("captured LAPSPREP inventory contains non-finite fields")
    return result


def main() -> int:
    if len(sys.argv) != 6:
        raise SystemExit("usage: pr83_same13_off_wps_readback.py OFF_WPS BASELINE_WPS INVENTORY MAPPED_WITNESS OUTPUT_JSON")
    off_path, baseline_path, inventory_path, witness_path, output_path = map(Path, sys.argv[1:])
    if output_path.exists() or output_path.is_symlink():
        raise FileExistsError(f"refusing to overwrite readback receipt: {output_path}")
    for path in (off_path, baseline_path, inventory_path, witness_path):
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"readback input is not a regular file: {path}")
    off, baseline = read_wps(off_path), read_wps(baseline_path)
    captured = read_inventory(witness_path)
    if len(off) != 235:
        raise ValueError(f"same mapper/writer should emit 235 records; received {len(off)}")
    expected = {
        "TT": "K", "HGT": "m", "UU": "m s{-1}", "VV": "m s{-1}",
        "QV": "kg kg{-1}", "RH": "%", "QC": "kg kg{-1}",
        "QI": "kg kg{-1}", "QR": "kg kg{-1}", "QS": "kg kg{-1}",
        "QG": "kg kg{-1}", "SOILHGT": "m", "PSFC": "Pa",
        "PMSL": "Pa", "SKINTEMP": "K",
    }
    for key, (unit, shape, flat, metadata) in off.items():
        if shape != (235, 283) or key[2] != "2026-08-16_13:00:00.0000":
            raise ValueError(f"wrong same13 WPS shape or time for {key}: {shape}")
        values = np.asarray(flat, dtype=np.float32)
        if not np.isfinite(values).all():
            raise ValueError(f"non-finite MODE_OFF WPS values for {key}")
        if expected.get(key[0]) != unit:
            raise ValueError(f"unexpected units for {key}: {unit!r}")
        if key[0] in ("UU", "VV") and not metadata.get("wind_grid_relative", False):
            raise ValueError(f"MODE_OFF wind record has wrong frame: {key}")

    # Record historical CP02 overlap for context only; it is not the paired
    # M(Xb) control and cannot gate this frozen-producer OFF readback.
    historical_overlap = []
    historical_missing = []
    historical_metadata_differences = []
    for key in baseline:
        if key not in off:
            historical_missing.append({"field": key[0], "level": key[1], "time": key[2]})
            continue
        base_unit, base_shape, base_flat, base_meta = baseline[key]
        unit, shape, values_flat, metadata = off[key]
        if (unit != base_unit or shape != base_shape or
                metadata.get("geometry") != base_meta.get("geometry")):
            historical_metadata_differences.append({
                "field": key[0], "level": key[1], "time": key[2],
                "units_match": unit == base_unit, "shape_match": shape == base_shape,
                "geometry_match": metadata.get("geometry") == base_meta.get("geometry"),
            })
            continue
        before = np.asarray(base_flat, dtype=np.float32)
        after = np.asarray(values_flat, dtype=np.float32)
        changed = before != after
        if np.any(changed):
            delta = np.abs(after.astype(np.float64) - before.astype(np.float64))
            ulp = np.abs(np.spacing(before))
            historical_overlap.append({
                "field": key[0], "level": key[1], "time": key[2],
                "changed_cells": int(np.count_nonzero(changed)),
                "max_abs_difference": float(delta.max(initial=0.0)),
                "max_float32_ulp": float(ulp.max(initial=0.0)) if key[0] == "HGT" else None,
            })

    nx, ny, nz = captured["dims"]
    levels = np.asarray(captured["p"], dtype=np.float32)
    if (nx, ny, nz) != (235, 283, 22) or levels.size != nz + 1:
        raise ValueError("captured host inventory has unexpected same13 dimensions")
    # This witness is emitted after the same mapper and before the writer. It
    # lets this separate parser independently verify every serialized field.
    profiles = {"TT": "t", "HGT": "ht", "UU": "u", "VV": "v", "RH": "rh", "QV": "qv"}
    hydros = {"QC": "qc", "QI": "qi", "QR": "qr", "QS": "qs", "QG": "qg"}
    compared_records = 0
    for key in off:
        short, level_pa, _ = key
        _, _, actual, _ = field(off, short, level_pa)
        expected_values = None
        if short in profiles:
            indices = np.flatnonzero(np.isclose(levels.astype(np.float64) * 100.0, level_pa, atol=0.25, rtol=0.0))
            if indices.size != 1:
                raise ValueError(f"mapped witness has no unique {short} level {level_pa}")
            expected_values = captured[profiles[short]][:, :, int(indices[0])]
        elif short in hydros:
            if level_pa == 200100.0:
                expected_values = np.zeros_like(actual)
            else:
                indices = np.flatnonzero(np.isclose(levels[:-1].astype(np.float64) * 100.0,
                                                    level_pa, atol=0.25, rtol=0.0))
                if indices.size != 1:
                    raise ValueError(f"mapped witness has no unique {short} level {level_pa}")
                expected_values = captured[hydros[short]][:, :, int(indices[0])]
        elif short == "SOILHGT":
            expected_values = captured["ht"][:, :, -1]
        elif short == "PSFC":
            expected_values = captured["psfc"]
        elif short == "PMSL":
            expected_values = captured["slp"]
        elif short == "SKINTEMP":
            expected_values = captured["skin"]
        elif short == "SNOW":
            expected_values = captured["snow"]
        if expected_values is None:
            raise ValueError(f"no independent mapped witness field for serialized WPS record {key}")
        if not np.array_equal(actual, expected_values):
            delta = np.abs(actual.astype(np.float64) - expected_values.astype(np.float64))
            raise ValueError(f"serialized {short}@{level_pa} differs from canonical mapped witness; "
                             f"max_abs={delta.max(initial=0.0)}")
        compared_records += 1
    if compared_records != len(off):
        raise ValueError("not all serialized WPS records were checked against the mapped witness")

    with output_path.open("x", encoding="utf-8") as stream:
        json.dump({
            "schema": "pr83_same13_off_wps_readback_v1",
            "status": "PASS_SCOPED_SAME13_OFF_MAPPER_WRITER_READBACK",
            "mode": "MODE_OFF exact no-op, then existing same-mode WPS mapper/writer",
            "science_authority": "NONE",
            "operational_authority": "NONE",
            "valid_time": "2026-08-16_13:00:00Z",
            "off_wps_sha256": digest(off_path),
            "same13_baseline_wps_sha256": digest(baseline_path),
            "captured_inventory_sha256": digest(inventory_path),
            "canonical_mapped_witness_sha256": digest(witness_path),
            "canonical_mapped_witness_role": "frozen MODE_OFF background after the retained pressure-to-WPS mapper, serialized before legacy WPS writer",
            "wps_record_count": len(off),
            "canonical_mapped_witness_records_compared": compared_records,
            "historical_baseline_records_compared": len(baseline),
            "historical_baseline_role": "context only; not the paired same-operator M(Xa)-M(Xb) control",
            "historical_baseline_differences": historical_overlap,
            "historical_baseline_missing_records": historical_missing,
            "historical_baseline_metadata_differences": historical_metadata_differences,
            "captured_inventory_role": "historical LAPSPREP diagnostic only; acceptance compares all records to same-run canonical mapped witness",
            "surface_hydrometeor_zero_records": sorted(hydros),
            "candidate_promoted": False,
        }, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": "PASS_SCOPED_SAME13_OFF_MAPPER_WRITER_READBACK",
                      "wps_sha256": digest(off_path), "records": len(off)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
