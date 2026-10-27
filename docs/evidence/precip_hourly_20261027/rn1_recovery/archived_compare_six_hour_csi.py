#!/usr/bin/env python3
"""Compare six hourly WRF precipitation increments with ODAM RN1.

This is a scratch-only comparison.  It expects the source-bound reference
directory already staged for this experiment: ``inventory.json`` and
``mask_receipt.json``.  The latter names a uint8 raw mask in Fortran order
with shape (149, 253), which is transposed to the comparison shape (253, 149).
The target latitude/longitude crop is read from the inventory's ODAM analysis
grid and crop indices.  The sibling ``run_contract.md`` must record the
RAINSH source/model-driver explanation and no-bucket contract, for example::

    {
      "grid": {"nx": 149, "ny": 253},
      "bucket_contract": {"BUCKET_MM": -1.0, "PREC_ACC_DT": 0.0}
    }

The run contract records RAINSH as a separate shallow-cumulus accumulator and
the retained one-hour outputs show it is zero.  This comparison therefore
requires RAINSH in every history file, checks it is zero, and computes the
model total as RAINC + RAINNC.  No bucket reset is repaired by this script: a
large negative cumulative difference is a hard failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
from netCDF4 import Dataset


OUT = Path(__file__).resolve().parent
DEFAULT_ODAM = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee_data/ODAM/20260816")
CASES = ("off", "hydro", "liquid")
HOURS = tuple(range(12, 19))
COMPARE_HOURS = tuple(range(13, 19))
THRESHOLDS_MM = (0.1, 1.0, 5.0, 10.0)
TARGET_SHAPE = (253, 149)
NEGATIVE_TOLERANCE_MM = 1.0e-6
MAP_TOLERANCE = 1.0e-10
MAP_RESIDUAL_TOLERANCE_DEG = 1.0e-7
RAINSH_SOURCE = "Registry.EM_COMMON:1593-1595 (rh01du, units mm); run_contract.md:38"
RAINSH_DRIVER = "retained WRF history output; run_contract.md:38 and ONE_HOUR_REPRODUCTION.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def identity(path: Path) -> dict[str, Any]:
    return {"path": str(path), "sha256": sha256(path), "size": path.stat().st_size}


def fail(message: str) -> None:
    raise RuntimeError(message)


def decode_times(variable: Any) -> list[str]:
    raw = np.asarray(variable[:])
    if raw.ndim != 2:
        fail(f"Times must be 2-D, got {raw.shape}")
    decoded: list[str] = []
    for row in raw:
        if raw.dtype.kind == "S":
            value = b"".join(row.tolist()).decode("ascii", "replace")
        elif raw.dtype.kind == "U":
            value = "".join(row.tolist())
        else:
            value = bytes(np.asarray(row, dtype=np.uint8).tolist()).decode("ascii", "replace")
        decoded.append(value.strip())
    return decoded


def read_2d_field(variable: Any, name: str) -> tuple[np.ndarray, np.ndarray]:
    raw = variable[:]
    masked = np.ma.asarray(raw)
    values = np.asarray(np.ma.getdata(masked), dtype=np.float64)
    missing = np.ma.getmaskarray(masked)
    values = np.squeeze(values)
    missing = np.squeeze(missing)
    if values.ndim != 2:
        fail(f"{name} must have one time slab and two horizontal dimensions, got {values.shape}")
    if missing.shape != values.shape:
        missing = np.broadcast_to(missing, values.shape)
    fill = getattr(variable, "_FillValue", None)
    valid = (~missing) & np.isfinite(values)
    if fill is not None:
        valid &= values != float(fill)
    values = np.where(valid, values, np.nan)
    return values, valid


def validate_units(variable: Any, name: str) -> None:
    units = str(getattr(variable, "units", "")).strip().lower()
    if units != "mm":
        fail(f"{name} units must be mm, got {units!r}")


def load_reference(reference_dir: Path, analysis_path: Path) -> tuple[dict[str, Any], np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    inventory_path = reference_dir / "inventory.json"
    if not inventory_path.exists():
        fail(f"missing source-bound inventory: {inventory_path}")
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    grid = inventory.get("grid", {})
    if grid.get("nx") != TARGET_SHAPE[1] or grid.get("ny") != TARGET_SHAPE[0] or grid.get("values") != TARGET_SHAPE[0] * TARGET_SHAPE[1]:
        fail(f"inventory grid must describe nx=149, ny=253, values=37697")
    mask_receipt_path = reference_dir / "mask_receipt.json"
    if not mask_receipt_path.exists():
        fail(f"missing source-bound mask receipt: {mask_receipt_path}")
    mask_receipt = json.loads(mask_receipt_path.read_text(encoding="utf-8"))
    artifact_name = mask_receipt.get("artifact")
    if not isinstance(artifact_name, str) or not artifact_name:
        fail("mask_receipt must name artifact")
    mask_path = Path(artifact_name)
    if not mask_path.is_absolute():
        mask_path = reference_dir / mask_path
    if not mask_path.exists():
        fail(f"missing source-bound mask payload: {mask_path}")
    declared_hash = mask_receipt.get("artifact_sha256")
    if not isinstance(declared_hash, str) or not declared_hash:
        fail("mask_receipt must declare artifact_sha256")
    if declared_hash != sha256(mask_path):
        fail(f"source-bound mask hash mismatch: {mask_path}")
    shape_nx_ny = tuple(mask_receipt.get("shape_nx_ny", ()))
    if shape_nx_ny != (TARGET_SHAPE[1], TARGET_SHAPE[0]) or mask_receipt.get("layout") != "uint8 raw Fortran order":
        fail("mask_receipt must declare uint8 raw Fortran order with shape_nx_ny [149, 253]")
    raw_mask = np.fromfile(mask_path, dtype=np.uint8)
    if raw_mask.size != TARGET_SHAPE[0] * TARGET_SHAPE[1]:
        fail(f"source-bound mask byte count must be {TARGET_SHAPE[0] * TARGET_SHAPE[1]}")
    # The source writes i1mask(nx,ny) as direct Fortran records.  Comparison
    # arrays use (y,x), so transpose after the Fortran-order reshape.
    mask_codes = raw_mask.reshape(shape_nx_ny, order="F")
    mask = mask_codes.T > 0
    if int(mask.sum()) != int(mask_receipt.get("selected_count", -1)):
        fail("source-bound mask selected_count does not match mask receipt")
    crop_x = grid.get("crop_x_inclusive")
    crop_y = grid.get("crop_y_inclusive")
    if crop_x != [76, 224] or crop_y != [7, 259]:
        fail("unexpected ODAM crop; source-bound coordinates are not the pinned 149x253 crop")
    if not analysis_path.exists():
        fail(f"missing ODAM analysis coordinate file: {analysis_path}")
    with Dataset(analysis_path) as analysis:
        if "lat" not in analysis.variables or "lon" not in analysis.variables:
            fail(f"analysis coordinate variables missing: {analysis_path}")
        full_lat = np.asarray(analysis["lat"][:]).squeeze()
        full_lon = np.asarray(analysis["lon"][:]).squeeze()
    if full_lat.shape != (283, 235) or full_lon.shape != (283, 235):
        fail(f"ODAM analysis coordinates must have shape (283, 235), got {full_lat.shape} / {full_lon.shape}")
    x0, x1 = crop_x
    y0, y1 = crop_y
    target_lat = full_lat[y0 - 1 : y1, x0 - 1 : x1].astype(np.float64)
    target_lon = full_lon[y0 - 1 : y1, x0 - 1 : x1].astype(np.float64)
    if target_lat.shape != TARGET_SHAPE or target_lon.shape != TARGET_SHAPE:
        fail("inventory crop does not produce shape (253, 149)")
    if not np.any(mask) or not np.isfinite(target_lat[mask]).all() or not np.isfinite(target_lon[mask]).all():
        fail("source-bound mask must select finite coordinates")
    contract_path = reference_dir.parent / "run_contract.md"
    if not contract_path.exists():
        fail(f"missing RAINSH/bucket source contract: {contract_path}")
    one_hour_path = reference_dir.parent / "ONE_HOUR_REPRODUCTION.json"
    if not one_hour_path.exists():
        fail(f"missing retained one-hour RAINSH driver receipt: {one_hour_path}")
    contract_text = contract_path.read_text(encoding="utf-8").lower()
    for phrase in ("rainc", "rainnc", "rainsh", "registry.em_common:1593-1595", "rainsh=0", "bucket_mm=-1", "prec_acc_dt=0"):
        if phrase not in contract_text:
            fail(f"run contract does not document required precipitation fact: {phrase}")
    # The retained contract explicitly keeps RAINSH separate and records it as
    # zero in the one-hour checks.  Keep this run's accumulator definition
    # fixed and expose the source/driver evidence in the result receipt.
    inventory["rainsh"] = {
        "policy": "exclude_zero",
        "source": RAINSH_SOURCE,
        "model_driver": RAINSH_DRIVER,
        "zero_tolerance_mm": NEGATIVE_TOLERANCE_MM,
    }
    bucket = inventory.get("bucket_contract", {"BUCKET_MM": -1.0, "PREC_ACC_DT": 0.0})
    if float(bucket.get("BUCKET_MM", np.nan)) != -1.0 or float(bucket.get("PREC_ACC_DT", np.nan)) != 0.0:
        fail("inventory bucket_contract must declare BUCKET_MM=-1 and PREC_ACC_DT=0")
    inventory["bucket_contract"] = {"BUCKET_MM": -1.0, "PREC_ACC_DT": 0.0}
    provenance = {"inventory": inventory_path, "mask_receipt": mask_receipt_path, "mask": mask_path, "analysis_coordinates": analysis_path, "run_contract": contract_path, "one_hour_reproduction": one_hour_path}
    return inventory, mask, target_lat, target_lon, provenance


def build_curvilinear_mapping(
    source_corner_lat: np.ndarray,
    source_corner_lon: np.ndarray,
    target_lat: np.ndarray,
    target_lon: np.ndarray,
    target_mask: np.ndarray,
) -> dict[str, np.ndarray | float]:
    if source_corner_lat.shape != source_corner_lon.shape or source_corner_lat.ndim != 2:
        fail("native XLAT/XLONG corner crop must have identical 2-D shapes")
    expected_shape = (target_lat.shape[0] + 1, target_lat.shape[1] + 1)
    if source_corner_lat.shape != expected_shape or target_lon.shape != target_lat.shape:
        fail(f"native corner crop must be one cell larger than target: expected {expected_shape}, got {source_corner_lat.shape}")
    if not np.isfinite(source_corner_lat).all() or not np.isfinite(source_corner_lon).all():
        fail("native XLAT/XLONG corner crop contains nonfinite values")
    # The existing ODAM comparison binds each analysis point to the
    # corresponding one-cell-halo WRF coordinate crop, then solves the full
    # curvilinear bilinear map.  This keeps the source-bound mapping explicit;
    # it does not perform conservative area remapping.
    j0, i0 = np.indices(target_lat.shape)
    u = np.full(target_lat.shape, 0.5, dtype=np.float64)
    v = np.full(target_lat.shape, 0.5, dtype=np.float64)
    for _ in range(10):
        p00_lat = source_corner_lat[:-1, :-1]
        p10_lat = source_corner_lat[:-1, 1:]
        p01_lat = source_corner_lat[1:, :-1]
        p11_lat = source_corner_lat[1:, 1:]
        p00_lon = source_corner_lon[:-1, :-1]
        p10_lon = source_corner_lon[:-1, 1:]
        p01_lon = source_corner_lon[1:, :-1]
        p11_lon = source_corner_lon[1:, 1:]
        one_u, one_v = 1.0 - u, 1.0 - v
        dlat_du = one_v * (p10_lat - p00_lat) + v * (p11_lat - p01_lat)
        dlat_dv = one_u * (p01_lat - p00_lat) + u * (p11_lat - p10_lat)
        dlon_du = one_v * (p10_lon - p00_lon) + v * (p11_lon - p01_lon)
        dlon_dv = one_u * (p01_lon - p00_lon) + u * (p11_lon - p10_lon)
        determinant = dlat_du * dlon_dv - dlon_du * dlat_dv
        if np.any(target_mask & (~np.isfinite(determinant) | (np.abs(determinant) < 1.0e-14))):
            fail("singular native bilinear cell in source-bound region")
        error_lat = one_u * one_v * p00_lat + u * one_v * p10_lat + one_u * v * p01_lat + u * v * p11_lat - target_lat
        error_lon = one_u * one_v * p00_lon + u * one_v * p10_lon + one_u * v * p01_lon + u * v * p11_lon - target_lon
        u -= (error_lat * dlon_dv - error_lon * dlat_dv) / determinant
        v -= (dlat_du * error_lon - dlon_du * error_lat) / determinant
    one_u, one_v = 1.0 - u, 1.0 - v
    mapped_lat = one_u * one_v * source_corner_lat[:-1, :-1] + u * one_v * source_corner_lat[:-1, 1:] + one_u * v * source_corner_lat[1:, :-1] + u * v * source_corner_lat[1:, 1:]
    mapped_lon = one_u * one_v * source_corner_lon[:-1, :-1] + u * one_v * source_corner_lon[:-1, 1:] + one_u * v * source_corner_lon[1:, :-1] + u * v * source_corner_lon[1:, 1:]
    residual = np.maximum(np.abs(mapped_lat - target_lat), np.abs(mapped_lon - target_lon))
    valid = target_mask & np.isfinite(residual) & (residual <= MAP_RESIDUAL_TOLERANCE_DEG)
    valid &= u >= -MAP_TOLERANCE
    valid &= u <= 1.0 + MAP_TOLERANCE
    valid &= v >= -MAP_TOLERANCE
    valid &= v <= 1.0 + MAP_TOLERANCE
    if not np.any(valid):
        fail("source-bound region has no valid native bilinear mapping")
    if not np.all(valid[target_mask]):
        fail(f"source-bound cells outside native grid or mapping tolerance: {np.count_nonzero(target_mask & ~valid)}")
    return {"j0": j0, "i0": i0, "u": np.where(valid, np.clip(u, 0.0, 1.0), 0.0), "v": np.where(valid, np.clip(v, 0.0, 1.0), 0.0), "valid": valid, "residual_max_deg": float(np.max(residual[valid]))}


def remap_field(values: np.ndarray, valid: np.ndarray, mapping: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    j0, i0, u, v = mapping["j0"], mapping["i0"], mapping["u"], mapping["v"]
    one_u, one_v = 1.0 - u, 1.0 - v
    result = one_u * one_v * values[j0, i0] + u * one_v * values[j0, i0 + 1] + one_u * v * values[j0 + 1, i0] + u * v * values[j0 + 1, i0 + 1]
    good = mapping["valid"] & valid[j0, i0] & valid[j0, i0 + 1] & valid[j0 + 1, i0] & valid[j0 + 1, i0 + 1] & np.isfinite(result)
    return np.where(good, result, np.nan), good


def read_wrf_snapshot(path: Path, expected_time: datetime, inventory: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        fail(f"missing WRF history file: {path}")
    with Dataset(path) as dataset:
        if "Times" not in dataset.variables:
            fail(f"missing Times in {path}")
        times = decode_times(dataset.variables["Times"])
        expected = expected_time.strftime("%Y-%m-%d_%H:%M:%S")
        if times != [expected]:
            fail(f"Times mismatch in {path}: expected [{expected!r}], got {times!r}")
        bucket_mm = getattr(dataset, "BUCKET_MM", None)
        prec_acc_dt = getattr(dataset, "PREC_ACC_DT", None)
        if bucket_mm is None or prec_acc_dt is None:
            fail(f"bucket attributes missing in {path}")
        declared = inventory["bucket_contract"]
        if float(bucket_mm) != float(declared["BUCKET_MM"]) or float(prec_acc_dt) != float(declared["PREC_ACC_DT"]):
            fail(f"bucket contract mismatch in {path}: BUCKET_MM={bucket_mm}, PREC_ACC_DT={prec_acc_dt}")
        required = {}
        for name in ("RAINC", "RAINNC"):
            if name not in dataset.variables:
                fail(f"missing required {name} in {path}")
            validate_units(dataset.variables[name], name)
            required[name] = read_2d_field(dataset.variables[name], name)
        if "RAINSH" not in dataset.variables:
            fail(f"missing required RAINSH in {path}")
        validate_units(dataset.variables["RAINSH"], "RAINSH")
        rainsh = read_2d_field(dataset.variables["RAINSH"], "RAINSH")
        description = str(getattr(dataset.variables["RAINSH"], "description", ""))
        if "shallow" not in description.lower() or "cumulus" not in description.lower():
            fail(f"RAINSH description is not the shallow-cumulus field in {path}: {description!r}")
        values, rainsh_valid = rainsh
        nonzero = rainsh_valid & (np.abs(values) > inventory["rainsh"]["zero_tolerance_mm"])
        if np.any(nonzero):
            fail(f"RAINSH is nonzero under exclude_zero policy in {path}: max={float(np.nanmax(np.abs(values[nonzero])))} mm")
        lat, lat_valid = read_2d_field(dataset.variables["XLAT"], "XLAT") if "XLAT" in dataset.variables else (None, None)
        lon, lon_valid = read_2d_field(dataset.variables["XLONG"], "XLONG") if "XLONG" in dataset.variables else (None, None)
        if lat is None or lon is None or not lat_valid.all() or not lon_valid.all():
            fail(f"native XLAT/XLONG are missing or incomplete in {path}")
        if any(array.shape != lat.shape for array, _ in required.values()) or rainsh[0].shape != lat.shape or lon.shape != lat.shape:
            fail(f"native field/grid shape mismatch in {path}")
        return {"path": path, "components": required, "rainsh": rainsh, "lat": lat, "lon": lon, "bucket_mm": float(bucket_mm), "prec_acc_dt": float(prec_acc_dt), "rainsh_description": str(getattr(dataset.variables.get("RAINSH"), "description", "")) if "RAINSH" in dataset.variables else ""}


def raw_total(snapshot: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    arrays = [snapshot["components"]["RAINC"], snapshot["components"]["RAINNC"]]
    total = np.zeros_like(arrays[0][0], dtype=np.float64)
    # RAINSH is excluded from the total by contract, but its validity still
    # belongs to the common data mask because every output must carry the
    # checked, separate component.
    valid = arrays[0][1] & arrays[1][1] & snapshot["rainsh"][1]
    for values, field_valid in arrays:
        bad_negative = field_valid & (values < -NEGATIVE_TOLERANCE_MM)
        if np.any(bad_negative):
            fail(f"negative cumulative precipitation in {snapshot['path']}")
        total += np.where(field_valid, np.maximum(values, 0.0), 0.0)
    return total, valid


def check_resets(snapshots: dict[str, dict[int, dict[str, Any]]]) -> dict[str, Any]:
    report: dict[str, Any] = {}
    component_names = ["RAINC", "RAINNC", "RAINSH"]
    for case in CASES:
        case_report: dict[str, Any] = {"components": {}}
        for component in component_names:
            negatives = 0
            smallest = 0.0
            for hour in COMPARE_HOURS:
                previous = snapshots[case][hour - 1]["components"].get(component) if component != "RAINSH" else snapshots[case][hour - 1]["rainsh"]
                current = snapshots[case][hour]["components"].get(component) if component != "RAINSH" else snapshots[case][hour]["rainsh"]
                if previous is None or current is None:
                    fail(f"{component} presence changes across {case} accumulation series")
                old, old_valid = previous
                new, new_valid = current
                common = old_valid & new_valid
                difference = new - old
                bad = common & (difference < -NEGATIVE_TOLERANCE_MM)
                negatives += int(np.count_nonzero(bad))
                if np.any(common):
                    smallest = min(smallest, float(np.min(difference[common])))
                if np.any(bad):
                    fail(f"cumulative reset/bucket decrease in {case} {component} at {hour:02d} UTC")
            case_report["components"][component] = {"negative_large_differences": negatives, "minimum_common_difference_mm": smallest}
        report[case] = case_report
    return report


def read_rn1(path: Path, hour: int) -> tuple[np.ndarray, np.ndarray]:
    if not path.exists():
        fail(f"missing RN1 reference file: {path}")
    lines = path.read_text(encoding="ascii").splitlines()
    expected_stamp = f"20260816{hour:02d}"
    if not lines or not lines[0].startswith(expected_stamp):
        fail(f"RN1 header mismatch in {path}: expected prefix {expected_stamp}")
    values: list[float] = []
    for line in lines[1:]:
        for offset in range(0, len(line), 7):
            field = line[offset : offset + 7]
            if field.strip():
                values.append(float(field))
    if len(values) != TARGET_SHAPE[0] * TARGET_SHAPE[1]:
        fail(f"RN1 value count in {path}: expected {TARGET_SHAPE[0] * TARGET_SHAPE[1]}, got {len(values)}")
    array = np.asarray(values, dtype=np.float64).reshape(TARGET_SHAPE)
    valid = np.isfinite(array) & (array >= 0.0)
    return np.where(valid, array, np.nan), valid


def threshold_counts(forecast: np.ndarray, reference: np.ndarray, valid: np.ndarray, threshold: float) -> dict[str, Any]:
    model_wet = valid & (forecast >= threshold)
    reference_wet = valid & (reference >= threshold)
    hit = int(np.count_nonzero(model_wet & reference_wet))
    miss = int(np.count_nonzero(~model_wet & reference_wet & valid))
    false_alarm = int(np.count_nonzero(model_wet & ~reference_wet & valid))
    correct_dry = int(np.count_nonzero(~model_wet & ~reference_wet & valid))
    denominator = hit + miss + false_alarm
    return {"hit": hit, "miss": miss, "false_alarm": false_alarm, "correct_dry": correct_dry, "CSI": hit / denominator if denominator else None}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=OUT, help="six-hour case root")
    parser.add_argument("--reference-dir", type=Path, default=OUT / "reference")
    parser.add_argument("--analysis", type=Path, default=OUT.parents[2] / "ANAL/NE57/DAOU/DFSD/20260816/klps_lc05_anal_20260816_1300")
    parser.add_argument("--odam-dir", type=Path, default=DEFAULT_ODAM)
    parser.add_argument("--output", type=Path, default=OUT / "RESULT_CSI.json")
    args = parser.parse_args()
    root = args.root.resolve()
    reference_dir = args.reference_dir.resolve()
    analysis_path = args.analysis.resolve()
    inventory, fixed_mask, target_lat, target_lon, provenance = load_reference(reference_dir, analysis_path)
    snapshots: dict[str, dict[int, dict[str, Any]]] = {case: {} for case in CASES}
    source_records: dict[str, list[dict[str, Any]]] = {case: [] for case in CASES}
    source_lat: np.ndarray | None = None
    source_lon: np.ndarray | None = None
    start = datetime(2026, 8, 16, 12, tzinfo=timezone.utc)
    for case in CASES:
        for hour in HOURS:
            path = root / case / "run" / f"wrfout_d01_2026-08-16_{hour:02d}:00:00"
            snapshot = read_wrf_snapshot(path, start + timedelta(hours=hour - 12), inventory)
            source_records[case].append(identity(path))
            if source_lat is None:
                source_lat, source_lon = snapshot["lat"], snapshot["lon"]
            elif not np.array_equal(source_lat, snapshot["lat"]) or not np.array_equal(source_lon, snapshot["lon"]):
                fail(f"native grid changed between WRF history files: {path}")
            snapshots[case][hour] = snapshot
    assert source_lat is not None and source_lon is not None
    crop_x = inventory["grid"]["crop_x_inclusive"]
    crop_y = inventory["grid"]["crop_y_inclusive"]
    corner_y0, corner_y1 = crop_y[0] - 2, crop_y[1] - 1
    corner_x0, corner_x1 = crop_x[0] - 2, crop_x[1] - 1
    if corner_y0 < 0 or corner_x0 < 0 or corner_y1 >= source_lat.shape[0] or corner_x1 >= source_lat.shape[1]:
        fail("source-bound WRF corner halo is outside the native grid")
    source_corner_lat = source_lat[corner_y0 : corner_y1 + 1, corner_x0 : corner_x1 + 1]
    source_corner_lon = source_lon[corner_y0 : corner_y1 + 1, corner_x0 : corner_x1 + 1]
    mapping = build_curvilinear_mapping(source_corner_lat, source_corner_lon, target_lat, target_lon, fixed_mask)
    reset_report = check_resets(snapshots)
    cumulative: dict[str, dict[int, tuple[np.ndarray, np.ndarray]]] = {case: {} for case in CASES}
    for case in CASES:
        for hour in HOURS:
            total, valid = raw_total(snapshots[case][hour])
            corner_total = total[corner_y0 : corner_y1 + 1, corner_x0 : corner_x1 + 1]
            corner_valid = valid[corner_y0 : corner_y1 + 1, corner_x0 : corner_x1 + 1]
            cumulative[case][hour] = remap_field(corner_total, corner_valid, mapping)
    reference: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    rn1_records = []
    for hour in COMPARE_HOURS:
        path = args.odam_dir / f"DFS_VSRT_GRD_KLPS_ODAM_RN1.20260816{hour:02d}00"
        reference[hour] = read_rn1(path, hour)
        rn1_records.append(dict(identity(path), hour_utc=hour))
    hourly: dict[str, dict[str, Any]] = {case: {} for case in CASES}
    pooled: dict[str, dict[str, dict[str, Any]]] = {case: {} for case in CASES}
    for hour in COMPARE_HOURS:
        common = fixed_mask & mapping["valid"] & reference[hour][1]
        for case in CASES:
            common &= cumulative[case][hour][1] & cumulative[case][hour - 1][1]
        reference_hour = reference[hour][0]
        predictions = {}
        for case in CASES:
            previous, previous_valid = cumulative[case][hour - 1]
            current, current_valid = cumulative[case][hour]
            valid = common & previous_valid & current_valid
            difference = current - previous
            bad = valid & (difference < -NEGATIVE_TOLERANCE_MM)
            if np.any(bad):
                fail(f"negative large remapped hourly difference in {case} at {hour:02d} UTC")
            predictions[case] = np.where(valid, np.maximum(difference, 0.0), np.nan)
            hourly[case][str(hour)] = {
                "valid_cells": int(np.count_nonzero(valid)),
                "forecast_min_mm": float(np.nanmin(predictions[case])) if np.any(valid) else None,
                "forecast_max_mm": float(np.nanmax(predictions[case])) if np.any(valid) else None,
                "threshold_mm": {str(threshold): threshold_counts(predictions[case], reference_hour, valid, threshold) for threshold in THRESHOLDS_MM},
            }
    for case in CASES:
        for threshold in THRESHOLDS_MM:
            totals = {key: 0 for key in ("hit", "miss", "false_alarm", "correct_dry")}
            for hour in COMPARE_HOURS:
                counts = hourly[case][str(hour)]["threshold_mm"][str(threshold)]
                for key in totals:
                    totals[key] += counts[key]
            denominator = totals["hit"] + totals["miss"] + totals["false_alarm"]
            totals["CSI"] = totals["hit"] / denominator if denominator else None
            pooled[case][str(threshold)] = totals
    output = {
        "status": "SIX_HOUR_HOURLY_CSI_COMPUTED",
        "evidence_class": "hourly_model_precipitation_vs_RN1_analysis_product",
        "initial_time_utc": "2026-08-16T12:00:00Z",
        "valid_hours_utc": [f"2026-08-16T{hour:02d}:00:00Z" for hour in COMPARE_HOURS],
        "region": "South Korean land-only source-bound mask; geographic country interpretation remains the mask receipt's documented provenance inference",
        "grid": {"target_shape_yx": list(TARGET_SHAPE), "source_native_shape_yx": list(source_lat.shape), "source_corner_crop_inclusive_yx": [[corner_y0, corner_y1], [corner_x0, corner_x1]], "fixed_mask_cells": int(np.count_nonzero(fixed_mask)), "mapping_valid_cells": int(np.count_nonzero(mapping["valid"])), "bilinear_residual_max_deg": mapping["residual_max_deg"], "mapping": "existing one-cell-halo native WRF curvilinear bilinear interpolation to ODAM points; source-bound cells only; no extrapolation"},
        "accumulation": {"model": "hourly differences of cumulative RAINC + RAINNC; RAINSH is checked separately and excluded because the source-bound contract records it as zero", "reference": "RN1 file for the matching UTC hour", "pooled_definition": "sum of six consecutive 1-hour contingency tables; no six-hour accumulated threshold", "missing_policy": "one fixed source-bound mask and one common valid mask per hour shared by all three cases and all thresholds"},
        "rainsh": {"policy": "exclude_zero", "source": inventory["rainsh"]["source"], "model_driver": inventory["rainsh"]["model_driver"], "included_in_total": False, "variable_description_examples": sorted({snapshots[case][hour]["rainsh_description"] for case in CASES for hour in HOURS})},
        "bucket_contract": inventory["bucket_contract"],
        "reset_bucket_checks": reset_report,
        "sources": {"inventory": identity(provenance["inventory"]), "mask": identity(provenance["mask"]), "mask_receipt": identity(provenance["mask_receipt"]), "analysis_coordinates": identity(provenance["analysis_coordinates"]), "run_contract": identity(provenance["run_contract"]), "one_hour_reproduction": identity(provenance["one_hour_reproduction"]), "rn1": rn1_records, "wrfout": source_records},
        "cases": {case: {"hourly": hourly[case], "pooled_6h": pooled[case]} for case in CASES},
        "limitations": ["RN1 is retained under the supplied one-hour/mm product convention; this script does not infer an independent observation uncertainty.", "The fixed land mask and its source-bound coordinates are external local inputs and must be independently inventoried before this result is interpreted.", "No forecast run, source, or maintained document is modified by this script."],
    }
    output_path = args.output.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, output_path)
    print(json.dumps({case: output["cases"][case]["pooled_6h"] for case in CASES}, indent=2))


if __name__ == "__main__":
    main()
