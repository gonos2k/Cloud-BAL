#!/usr/bin/env python3
"""Independent readback for the pinned same-time operational metgrid run."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from compare_baseline import read_wps


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


candidate_path, geo_path, output_path, receipt_path = map(Path, sys.argv[1:5])
for path in (candidate_path, geo_path, output_path):
    if path.is_symlink() or not path.is_file():
        raise AssertionError(f"metgrid readback input is not a regular file: {path}")
if receipt_path.exists() or receipt_path.is_symlink():
    raise AssertionError(f"metgrid readback receipt already exists: {receipt_path}")

candidate = read_wps(candidate_path)
with Dataset(geo_path) as geo, Dataset(output_path) as met:
    if met.variables["Times"].shape != (1, 19):
        raise AssertionError("metgrid output does not contain exactly one timestamp")
    time = b"".join(met.variables["Times"][0].tolist()).decode("ascii")
    if time != "2026-08-16_13:00:00":
        raise AssertionError(f"metgrid output has wrong valid time: {time}")
    if len(met.dimensions["west_east"]) != 234 or len(met.dimensions["south_north"]) != 282:
        raise AssertionError("metgrid output dimensions do not match retained NE57 grid")
    if len(met.dimensions["num_metgrid_levels"]) != 21:
        raise AssertionError("metgrid output has unexpected vertical coordinate count")
    flags = ("FLAG_QV", "FLAG_QC", "FLAG_QI", "FLAG_QR", "FLAG_QS", "FLAG_QG",
             "FLAG_PSFC", "FLAG_SOILHGT")
    flag_values = {name: int(getattr(met, name, -1)) for name in flags}
    if any(value != 1 for value in flag_values.values()):
        raise AssertionError(f"metgrid did not consume every declared candidate/geometry field: {flag_values}")
    required = ("PRES", "TT", "GHT", "UU", "VV", "QV", "QC", "QI", "QR", "QS", "QG",
                "RH", "PMSL", "PSFC", "SKINTEMP", "SOILHGT")
    missing = [name for name in required if name not in met.variables]
    if missing:
        raise AssertionError(f"metgrid output omitted required candidate or ancillary fields: {missing}")
    if not np.array_equal(met.variables["XLAT_M"][:], geo.variables["XLAT_M"][:]):
        raise AssertionError("metgrid output changed the retained mass-grid latitude")
    if not np.array_equal(met.variables["XLONG_M"][:], geo.variables["XLONG_M"][:]):
        raise AssertionError("metgrid output changed the retained mass-grid longitude")
    fields = {name: np.asarray(met.variables[name][:]) for name in required}
    for name, values in fields.items():
        if not np.all(np.isfinite(values)):
            raise AssertionError(f"metgrid output {name} contains non-finite values")

levels = sorted((key[1] for key in candidate if key[0] == "QV" and key[1] != 200100.0), reverse=True)
if len(levels) != 20:
    raise AssertionError(f"candidate WPS has {len(levels)} pressure QV levels, expected 20")
source_qv = {}
for key, (unit, shape, flat, _) in candidate.items():
    if key[0] == "QV":
        nx, ny = shape
        source_qv[key[1]] = np.asarray(flat, dtype=np.float32).reshape((nx, ny), order="F").T

pressure_qv_offsets = []
for shift_y in (0, 1):
    for shift_x in (0, 1):
        differences = []
        for out_level, source_level in enumerate(levels, start=1):
            expected = source_qv[source_level][shift_y:shift_y + 282, shift_x:shift_x + 234]
            actual = fields["QV"][0, out_level]
            if expected.shape != actual.shape:
                raise AssertionError("candidate WPS scalar slice has the wrong dimensions")
            differences.append(np.abs(actual.astype(np.float64) - expected.astype(np.float64)))
        error = np.concatenate([item.ravel() for item in differences])
        record = {
            "shift_y": shift_y,
            "shift_x": shift_x,
            "max_abs_error": float(error.max(initial=0.0)),
            "mean_abs_error": float(error.mean()),
            "exact_cell_count": int(np.count_nonzero(error == 0.0)),
            "cell_count": int(error.size),
        }
        pressure_qv_offsets.append(record)
surface = source_qv[200100.0]
surface_qv_offsets = []
for shift_y in (0, 1):
    for shift_x in (0, 1):
        expected = surface[shift_y:shift_y + 282, shift_x:shift_x + 234]
        actual = fields["QV"][0, 0]
        if expected.shape == actual.shape:
            error = np.abs(actual.astype(np.float64) - expected.astype(np.float64))
            surface_qv_offsets.append({
                "shift_y": shift_y, "shift_x": shift_x,
                "max_abs_error": float(error.max(initial=0.0)),
                "mean_abs_error": float(error.mean()),
                "exact_cell_count": int(np.count_nonzero(error == 0.0)),
                "cell_count": int(error.size),
            })

json_receipt = {
    "status": "PASS_SCOPED_SAME13_PINNED_INTEL_METGRID_READBACK",
    "science_authority": "NONE",
    "valid_time": time,
    "grid_dimensions_mass": [234, 282],
    "metgrid_levels": 21,
    "required_fields": list(required),
    "direct_candidate_qv_pressure_comparison_all_offsets": pressure_qv_offsets,
    "direct_candidate_qv_surface_comparison_all_offsets": surface_qv_offsets,
    "candidate_metgrid_flags": flag_values,
    "real_qv_selection": {
        "metgrid_FLAG_QV": flag_values["FLAG_QV"],
        "metgrid_QV_source": "same-time PR81 candidate WPS QV profile and surface",
        "real_namelist_use_sh_qv": True,
        "selection_scope": "input/configuration provenance only; not a physics validation",
    },
    "candidate_wps_sha256": digest(candidate_path),
    "geo_em_sha256": digest(geo_path),
    "met_em_sha256": digest(output_path),
    "met_em_bytes": output_path.stat().st_size,
    "direct_qv_field_present": True,
    "real_exe_executed": False,
}
with receipt_path.open("x", encoding="utf-8") as receipt:
    json.dump(json_receipt, receipt, indent=2, sort_keys=True, allow_nan=False)
