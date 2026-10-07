#!/usr/bin/env python3
"""Decode PR67 same-call KDM6 process records and focused water accounting.

The raw stream is a research observer artifact from pinned Intel ifx on the
current x86_64 host. The pinned-object `-convert big_endian` flag gives this
stream its on-disk byte order. It does not alter maintained WRF or Cloud-BAL
source.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import stat
from pathlib import Path
from typing import Any

import numpy as np

from native_kdm6_call_geometry import active_geometry_measure, audit as audit_geometry, parse_geometry
from native_kdm6_trace import BOUNDS, FIELDS_3D, read_dump

MAGIC = b"PR67P001"
WATER_FIELDS = ("Q", "QC", "QR", "QI", "QS", "QG")


class CaptureError(ValueError):
    """The process capture or its paired call artifacts are incomplete."""


def _array(raw: bytes, offset: int, count: int, kind: str, label: str) -> tuple[np.ndarray, int]:
    dtype = {"f4": np.dtype(">f4"), "f8": np.dtype(">f8")}[kind]
    size = count * dtype.itemsize
    end = offset + size
    if count < 0 or end > len(raw):
        raise CaptureError(f"truncated {label} at byte {offset}")
    return np.frombuffer(raw, dtype=dtype, count=count, offset=offset).astype(np.float64), end


def _ints(raw: bytes, offset: int, count: int, label: str) -> tuple[tuple[int, ...], int]:
    end = offset + count * 4
    if end > len(raw):
        raise CaptureError(f"truncated {label} at byte {offset}")
    return struct.unpack_from(">" + "i" * count, raw, offset), end


def _matrix(raw: bytes, offset: int, nx: int, nk: int, kind: str,
            label: str) -> tuple[np.ndarray, int]:
    values, offset = _array(raw, offset, nx * nk, kind, label)
    return values.reshape((nx, nk), order="F").T, offset


def parse_process_capture(path: Path) -> list[dict[str, Any]]:
    """Parse stage 0/1/2 arrays, validating each record and ordered j row."""
    raw = path.read_bytes()
    offset = 0
    records: list[dict[str, Any]] = []
    expected_lat: int | None = None
    expected_stage = 0
    row_header: tuple[int, int, int, float] | None = None
    call_header: tuple[int, int, int, int, float] | None = None
    call_denr: float | None = None
    call_flags: tuple[int, int] | None = None
    while offset < len(raw):
        if raw[offset:offset + len(MAGIC)] != MAGIC:
            raise CaptureError(f"wrong record magic at byte {offset}")
        offset += len(MAGIC)
        (stage, lat, its, ite, kts, kte), offset = _ints(raw, offset, 6, "record header")
        (dtcld,), offset = _array(raw, offset, 1, "f4", "dtcld")
        nx, nk = ite - its + 1, kte - kts + 1
        if stage != expected_stage:
            raise CaptureError(f"expected stage {expected_stage}, found {stage}")
        if nx <= 0 or nk <= 0 or not math.isfinite(dtcld) or dtcld <= 0:
            raise CaptureError("invalid active bounds or cloud timestep")
        current_header = (its, ite, kts, kte, float(dtcld))
        if stage == 0:
            work1_ice, offset = _matrix(raw, offset, nx, nk, "f8", "work1 ice slope")
            delz, offset = _matrix(raw, offset, nx, nk, "f4", "layer thickness")
            density, offset = _matrix(raw, offset, nx, nk, "f4", "air density")
            qice, offset = _matrix(raw, offset, nx, nk, "f4", "pre-substep ice")
            if (not np.isfinite(work1_ice).all() or not np.isfinite(delz).all() or np.any(delz <= 0) or
                    not np.isfinite(density).all() or np.any(density <= 0) or
                    not np.isfinite(qice).all()):
                raise CaptureError("stage 0 has invalid DELZ, density, or QI")
            row_header = current_header
            if call_header is None:
                call_header = current_header
            elif current_header != call_header:
                raise CaptureError("process stage-0 bounds or dtcld differs across j rows")
            data = {"work1_ice": work1_ice, "delz": delz, "density": density, "qice": qice}
        elif stage == 1:
            qice, offset = _matrix(raw, offset, nx, nk, "f4", "post-substep ice")
            flux, offset = _matrix(raw, offset, nx, nk, "f4", "first-substep ice flux")
            fall, offset = _matrix(raw, offset, nx, nk, "f4", "ice fall accumulator")
            if (current_header != row_header or not np.isfinite(qice).all() or
                    not np.isfinite(flux).all() or not np.isfinite(fall).all()):
                raise CaptureError("stage 1 header or QI differs from stage 0")
            data = {"qice": qice, "flux": flux, "fall": fall}
        else:
            (denr,), offset = _array(raw, offset, 1, "f4", "water density")
            if current_header != row_header or not math.isfinite(denr) or denr <= 0:
                raise CaptureError("stage 2 header or DENR differs from stage 0")
            flat_fall, offset = _array(raw, offset, nx * 4, "f4", "bottom species fall")
            fall = flat_fall.reshape((nx, 4), order="F").T
            dz, offset = _array(raw, offset, nx, "f4", "bottom layer thickness")
            density, offset = _array(raw, offset, nx, "f4", "bottom air density")
            rainncv, offset = _array(raw, offset, nx, "f4", "rainncv")
            present, offset = _ints(raw, offset, 2, "optional accumulator flags")
            if any(value not in (0, 1, -1) for value in present):
                raise CaptureError("optional accumulator flags are not logical values")
            if call_denr is None:
                call_denr = float(denr)
                call_flags = present
            elif denr != call_denr or present != call_flags:
                raise CaptureError("stage-2 DENR or optional accumulators differ across j rows")
            snow, offset = _array(raw, offset, nx if present[0] != 0 else 0, "f4", "snowncv")
            graupel, offset = _array(raw, offset, nx if present[1] != 0 else 0, "f4", "graupelncv")
            if (not np.isfinite(fall).all() or np.any(fall < 0) or
                    not np.isfinite(dz).all() or np.any(dz <= 0) or
                    not np.isfinite(density).all() or np.any(density <= 0) or
                    not np.isfinite(rainncv).all() or not np.isfinite(snow).all() or
                    not np.isfinite(graupel).all()):
                raise CaptureError("stage 2 has invalid DELZ, density, or rainncv")
            data = {"denr": float(denr), "fall": fall, "delz": dz,
                    "density": density, "rainncv": rainncv,
                    "snowncv_present": present[0] != 0, "graupelncv_present": present[1] != 0,
                    "snowncv": snow, "graupelncv": graupel}
        if expected_lat is None:
            expected_lat = lat
        if stage == 0 and lat != expected_lat:
            raise CaptureError(f"j rows are not ordered: expected {expected_lat}, found {lat}")
        if stage > 0 and (not records or records[-1]["lat"] != lat):
            raise CaptureError(f"stage {stage} row does not match the prior stage")
        records.append({"stage": stage, "lat": lat, "its": its, "ite": ite,
                        "kts": kts, "kte": kte, "dtcld": float(dtcld), **data})
        expected_stage = (stage + 1) % 3
        if stage == 2:
            expected_lat += 1
    if not records or expected_stage != 0:
        raise CaptureError("capture must contain complete stage 0/1/2 row groups")
    return records


def _verify_receipt(paths: tuple[Path, ...], receipt_path: Path) -> dict[str, Any]:
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("returncode") != 0 or receipt.get("input_integrity") != "PASS" or receipt.get("output_isolation") != "PASS":
        raise CaptureError("paired run receipt is not a successful isolated run")
    rows = {row["path"]: row for row in receipt.get("outputs", [])}
    for path in paths:
        try:
            relative = path.resolve().relative_to(receipt_path.parent.resolve()).as_posix()
        except ValueError as exc:
            raise CaptureError(f"capture is outside receipt run root: {path}") from exc
        row = rows.get(relative)
        try:
            file_stat = path.lstat()
        except FileNotFoundError as exc:
            raise CaptureError(f"capture is missing: {path}") from exc
        if (row is None or not stat.S_ISREG(file_stat.st_mode) or path.is_symlink() or
                row.get("nlink") != 1 or file_stat.st_nlink != 1 or
                hashlib.sha256(path.read_bytes()).hexdigest() != row.get("sha256")):
            raise CaptureError(f"capture is not hash-bound as a declared output: {relative}")
    return receipt


def analyze(process_path: Path, geometry_path: Path, pre_path: Path, post_path: Path,
            receipt_path: Path) -> dict[str, Any]:
    """Return focused mass and precipitation results for one public KDM6 call."""
    receipt = _verify_receipt((process_path, geometry_path, pre_path, post_path), receipt_path)
    records = parse_process_capture(process_path)
    geometry_audit = audit_geometry(geometry_path, pre_path, post_path, receipt_path)
    pre, post = read_dump(pre_path), read_dump(post_path)
    if pre["stage"] != 1 or post["stage"] != 2:
        raise CaptureError("KDM6 raw trace stages must be pre=1, post=2")
    geom_records = parse_geometry(geometry_path.read_bytes())
    if len(geom_records) != 2:
        raise CaptureError("geometry capture must contain pre/post records")
    geometry = geom_records[0]
    measure = active_geometry_measure(geometry, {"bounds": pre["bounds"]})
    dry_mass, area = measure["dry_mass"], measure["area"]
    if not np.isfinite(dry_mass).all() or not np.isfinite(area).all():
        raise CaptureError("active geometry weights must be finite")

    header = pre["bounds"]
    water: dict[str, dict[str, float]] = {}
    for name in WATER_FIELDS:
        before = pre["fields"][name].transpose(1, 0, 2)
        after = post["fields"][name].transpose(1, 0, 2)
        if not np.isfinite(before).all() or not np.isfinite(after).all():
            raise CaptureError(f"six-water field {name} contains nonfinite values")
        pre_mass = float(np.sum(before * dry_mass, dtype=np.float64))
        post_mass = float(np.sum(after * dry_mass, dtype=np.float64))
        delta_mass = float(np.sum((after - before) * dry_mass, dtype=np.float64))
        if not all(math.isfinite(value) for value in (pre_mass, post_mass, delta_mass)):
            raise CaptureError(f"six-water mass reduction for {name} is nonfinite")
        water[name] = {"pre_kg": pre_mass, "post_kg": post_mass, "delta_kg": delta_mass}

    rows = [records[i:i + 3] for i in range(0, len(records), 3)]
    if len(rows) != area.shape[0]:
        raise CaptureError("process j rows do not span active geometry")
    first = rows[0]
    expected = (header["its"], header["ite"], header["kts"], header["kte"])
    if any((r[0]["its"], r[0]["ite"], r[0]["kts"], r[0]["kte"]) != expected for r in rows):
        raise CaptureError("process and public KDM6 active bounds differ")
    if len(rows) != header["jte"] - header["jts"] + 1 or rows[0][0]["lat"] != header["jts"]:
        raise CaptureError("process rows do not align with public KDM6 j bounds")
    outer_dt = float(pre["params"]["dt_s"])
    loops = max(math.floor(outer_dt / 120.0 + 0.5), 1)
    expected_dtcld = outer_dt if outer_dt <= 120.0 else outer_dt / loops
    if any(not math.isclose(row[0]["dtcld"], expected_dtcld, rel_tol=1.0e-7, abs_tol=1.0e-6)
           for row in rows):
        raise CaptureError("process DTCLD does not match source outer-step substep formula")
    qice_pre = np.stack([row[0]["qice"] for row in rows], axis=1)
    qice_post_first = np.stack([row[1]["qice"] for row in rows], axis=1)
    if qice_pre.shape != dry_mass.shape or qice_post_first.shape != dry_mass.shape:
        raise CaptureError("process ice arrays do not match the active dry-mass map")
    dend = np.stack([row[0]["density"] for row in rows], axis=1)
    process_delz = np.stack([row[0]["delz"] for row in rows], axis=1)
    if (dend.shape != dry_mass.shape or process_delz.shape != dry_mass.shape or
            not np.isfinite(dend).all() or np.any(dend <= 0) or
            not np.isfinite(process_delz).all() or np.any(process_delz <= 0)):
        raise CaptureError("captured DEND/DELZ do not match active dry-mass map")
    native_carrier = dend * process_delz * area[None, :, :]
    carrier_relative_difference = np.abs(native_carrier - dry_mass) / dry_mass
    process_ice = {
        "weight_basis_note": "The process stream's native DEND*DELZ*area carrier is the local sedimentation mass basis; hybrid-pressure dry mass is a separate call-budget basis.",
        "pre_first_ice_substep_hybrid_dry_mass_kg": float(np.sum(qice_pre * dry_mass, dtype=np.float64)),
        "post_first_ice_substep_hybrid_dry_mass_kg": float(np.sum(qice_post_first * dry_mass, dtype=np.float64)),
        "pre_first_ice_substep_native_carrier_kg": float(np.sum(qice_pre * native_carrier, dtype=np.float64)),
        "post_first_ice_substep_native_carrier_kg": float(np.sum(qice_post_first * native_carrier, dtype=np.float64)),
        "max_relative_native_to_hybrid_carrier_difference": float(np.max(carrier_relative_difference)),
    }
    process_ice["pre_first_ice_substep_kg"] = process_ice["pre_first_ice_substep_hybrid_dry_mass_kg"]
    process_ice["post_first_ice_substep_kg"] = process_ice["post_first_ice_substep_hybrid_dry_mass_kg"]
    if not math.isfinite(process_ice["pre_first_ice_substep_kg"]) or process_ice["pre_first_ice_substep_kg"] <= 0:
        raise CaptureError("pre-substep ice mass must be finite and positive")
    if not math.isfinite(process_ice["post_first_ice_substep_kg"]):
        raise CaptureError("post-substep ice mass must be finite")
    process_ice["fraction_retained"] = (process_ice["post_first_ice_substep_kg"] /
                                        process_ice["pre_first_ice_substep_kg"])
    process_ice["native_carrier_delta_kg"] = (
        process_ice["post_first_ice_substep_native_carrier_kg"] -
        process_ice["pre_first_ice_substep_native_carrier_kg"])
    phase_mm = np.stack([row[2]["fall"] * row[2]["delz"][None, :] /
                         row[2]["denr"] * row[2]["dtcld"] * 1000.0 for row in rows], axis=1)
    if not np.isfinite(phase_mm).all():
        raise CaptureError("source bottom precipitation increments are nonfinite")
    mapped_phase_kg = {f"phase_{i + 1}": float(np.sum(phase_mm[i] * area, dtype=np.float64))
                       for i in range(4)}
    mapped_precip = sum(mapped_phase_kg.values())
    if not all(math.isfinite(x) for x in (*mapped_phase_kg.values(), mapped_precip)):
        raise CaptureError("mapped precipitation mass must be finite")
    six_pre = sum(item["pre_kg"] for item in water.values())
    six_post = sum(item["post_kg"] for item in water.values())
    six_delta = six_post - six_pre
    if not all(math.isfinite(x) for x in (six_pre, six_post, six_delta)):
        raise CaptureError("six-water mass sum must be finite")
    return {
        "schema": "pr67_kdm6_samecall_budget_v1",
        "receipt": {"path": str(receipt_path), "run_root": receipt["run_root"],
                    "returncode": receipt["returncode"], "input_integrity": receipt["input_integrity"],
                    "output_isolation": receipt["output_isolation"]},
        "geometry_audit": {key: geometry_audit[key] for key in ("executable_sha256", "kdm6_active_shape_xyz", "kdm6_timestep", "mapped_hybrid_dry_mass_kg", "max_layer_to_interface_dp_difference_pa", "max_column_dp_to_mu2_mub_difference_pa")},
        "capture_sha256": {str(p.name): hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in (process_path, geometry_path, pre_path, post_path)},
        "extent": {"i": [header["its"], header["ite"]], "j": [header["jts"], header["jte"]],
                   "k": [header["kts"], header["kte"]], "j_rows": len(rows),
                   "process_records": len(records), "dtcld_s": first[0]["dtcld"]},
        "ice_process": process_ice,
        "six_water": {"pre_kg": six_pre, "post_kg": six_post, "delta_kg": six_delta,
                      "species": water},
        "surface_precipitation": {"mapped_increment_kg": mapped_precip,
                                  "phase_increment_kg": mapped_phase_kg,
                                  "source_accumulator_units": "mm; mapped with 1 mm = 1 kg m^-2 times active map area"},
        "focused_residual_kg": six_delta + mapped_precip,
        "limitations": [
            "This compares one public KDM6 call's six-water state change with its source-derived surface precipitation increment. It is a focused diagnostic, not whole-scheme water or energy closure.",
            "rainncv is a cumulative millimeter accumulator. The mapped increment comes from the captured bottom fall rates using the source equation; snow and graupel accumulators are subsets and are not added again.",
            "DTCLD is checked against the KDM6 source formula: loops=max(NINT(DELT/120 s),1), DTCLD=DELT/loops, with DTCLD=DELT when DELT<=120 s. The result is unsupported if the captured value does not match.",
            "The capture is a research-only observer and normalization experiment. Maintained WRF and operational input sources are unchanged.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("process", type=Path)
    parser.add_argument("geometry", type=Path)
    parser.add_argument("pre", type=Path)
    parser.add_argument("post", type=Path)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = analyze(args.process, args.geometry, args.pre, args.post, args.receipt)
    except (OSError, ValueError, CaptureError, KeyError, struct.error) as exc:
        parser.error(str(exc))
    encoded = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
