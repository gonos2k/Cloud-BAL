#!/usr/bin/env python3
"""Independent PR82 candidate WPS readback against captured same-time inputs."""
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


def field(fields, short: str, level: float):
    keys = [key for key in fields if key[0] == short and key[1] == level]
    if len(keys) != 1:
        raise AssertionError(f"expected one {short}@{level} record, got {len(keys)}")
    key = keys[0]
    unit, shape, flat, metadata = fields[key]
    nx, ny = shape
    return key, unit, np.asarray(flat).reshape((nx, ny), order="F"), metadata


def read_inventory(path: Path):
    raw = path.read_bytes()
    header_length = int.from_bytes(raw[:4], "big")
    if header_length != 12 or int.from_bytes(raw[16:20], "big") != 12:
        raise AssertionError("captured LAPSPREP inventory has an invalid dimension record")
    nx, ny, nz = np.frombuffer(raw, dtype=">i4", count=3, offset=4).astype(int)
    payload_length = int.from_bytes(raw[20:24], "big")
    if int.from_bytes(raw[24 + payload_length : 28 + payload_length], "big") != payload_length:
        raise AssertionError("captured LAPSPREP inventory record is truncated")
    if 28 + payload_length != len(raw):
        raise AssertionError("captured LAPSPREP inventory has trailing bytes")
    values = np.frombuffer(raw, dtype=">f4", count=payload_length // 4, offset=24)
    offset = 0

    def take(count: int, shape: tuple[int, ...]):
        nonlocal offset
        result = values[offset : offset + count].astype(np.float32).reshape(shape, order="F")
        if result.size != count:
            raise AssertionError("captured LAPSPREP inventory is shorter than its declared dimensions")
        offset += count
        return result

    p = take(nz + 1, (nz + 1,))
    profile_shape = (nx, ny, nz + 1)
    t, ht, u, v, rh, qv = (take(nx * ny * (nz + 1), profile_shape) for _ in range(6))
    hydro_shape = (nx, ny, nz)
    qc, qr, qs, qi, qg = (take(nx * ny * nz, hydro_shape) for _ in range(5))
    surface_shape = (nx, ny)
    psfc, slp, skin, snow = (take(nx * ny, surface_shape) for _ in range(4))
    if offset != values.size:
        raise AssertionError("captured LAPSPREP inventory layout does not match the declared schema")
    return {
        "dims": (nx, ny, nz), "p": p, "t": t, "ht": ht, "u": u, "v": v,
        "rh": rh, "qv": qv, "qc": qc, "qr": qr, "qs": qs, "qi": qi,
        "qg": qg, "psfc": psfc, "slp": slp, "skin": skin, "snow": snow,
    }


candidate_path, baseline_path, wps_path, inventory_path, out_path = map(Path, sys.argv[1:6])
for artifact in (candidate_path, baseline_path, wps_path, inventory_path):
    if artifact.is_symlink() or not artifact.is_file():
        raise AssertionError(f"readback input is not a regular non-symlink file: {artifact}")
if out_path.exists() or out_path.is_symlink():
    raise AssertionError(f"readback receipt already exists: {out_path}")
candidate_wps = read_wps(wps_path)
baseline_wps = read_wps(baseline_path)
legacy = read_inventory(inventory_path)
for name, values in legacy.items():
    if isinstance(values, np.ndarray) and not np.all(np.isfinite(values)):
        raise AssertionError(f"captured inventory field {name} contains non-finite values")
for key, (_, shape, values, metadata) in candidate_wps.items():
    if shape != (235, 283):
        raise AssertionError(f"WPS field {key} has unexpected horizontal shape {shape}")
    if not np.all(np.isfinite(values)):
        raise AssertionError(f"WPS field {key} contains non-finite values")
    if key[2] != "2026-08-16_13:00:00.0000":
        raise AssertionError(f"WPS field {key} has the wrong timestamp")
    if metadata["geometry"] != field(baseline_wps, "TT", 5000.0)[3]["geometry"]:
        raise AssertionError(f"WPS field {key} changed the captured geometry")

expected_units = {
    "TT": "K", "SKINTEMP": "K", "HGT": "m", "SOILHGT": "m",
    "UU": "m s{-1}", "VV": "m s{-1}", "QV": "kg kg{-1}",
    "QC": "kg kg{-1}", "QI": "kg kg{-1}", "QR": "kg kg{-1}",
    "QS": "kg kg{-1}", "QG": "kg kg{-1}", "RH": "%",
    "PMSL": "Pa", "PSFC": "Pa",
}
for key, (unit, _, _, metadata) in candidate_wps.items():
    if expected_units.get(key[0]) != unit:
        raise AssertionError(f"unexpected units for {key}: {unit!r}")
    if key[0] in ("UU", "VV") and not metadata.get("wind_grid_relative", False):
        raise AssertionError(f"WPS wind frame is not grid-relative for {key}")

with Dataset(candidate_path) as nc:
    pressure = np.asarray(nc["pressure"][:], dtype=np.float32)
    above = np.asarray(nc["above_ground"][:], dtype=np.int32).astype(bool)
    profile = {
        "TT": np.asarray(nc["candidate_temperature"][:], dtype=np.float32),
        "HGT": (np.asarray(nc["candidate_geopotential"][:], dtype=np.float64) / 9.80665).astype(np.float32),
        "UU": np.asarray(nc["candidate_u"][:], dtype=np.float32),
        "VV": np.asarray(nc["candidate_v"][:], dtype=np.float32),
        "QV": np.asarray(nc["candidate_vapor"][:], dtype=np.float32),
        "QC": np.asarray(nc["candidate_cloud_water"][:], dtype=np.float32),
        "QI": np.asarray(nc["candidate_cloud_ice"][:], dtype=np.float32),
        "QR": np.asarray(nc["candidate_rain"][:], dtype=np.float32),
        "QS": np.asarray(nc["candidate_snow"][:], dtype=np.float32),
        "QG": np.asarray(nc["candidate_graupel"][:], dtype=np.float32),
    }
    surface = {
        "TT": (np.asarray(nc["candidate_surface_temperature"][:], dtype=np.float32).T,
               np.asarray(nc["candidate_surface_temperature_valid"][:], dtype=bool).T),
        "HGT": (np.asarray(nc["candidate_surface_height"][:], dtype=np.float32).T,
                np.asarray(nc["candidate_surface_height_valid"][:], dtype=bool).T),
        "QV": (np.asarray(nc["candidate_surface_vapor"][:], dtype=np.float32).T,
               np.asarray(nc["candidate_surface_vapor_valid"][:], dtype=bool).T),
        "PSFC": (np.asarray(nc["candidate_surface_pressure"][:], dtype=np.float32).T,
                 np.asarray(nc["candidate_surface_pressure_valid"][:], dtype=bool).T),
    }
    valid_time = int(nc.getncattr("valid_time_epoch"))
    grid_id = str(nc.getncattr("grid_id"))

candidate_id = digest(candidate_path)
expected_id = "135c2315d0953182d248ff650ad50fcab7c0b21075b208e693a04fd7f8487ef1"
if candidate_id != expected_id:
    raise AssertionError(f"candidate identity changed: {candidate_id}")
if valid_time != 1786885200 or grid_id != "NE57_LAPS_PRESSURE":
    raise AssertionError("the writer replay is not the pinned same-time candidate")
if legacy["dims"] != (235, 283, 22) or pressure.size != legacy["dims"][2]:
    raise AssertionError("candidate and captured LAPSPREP dimensions differ")

# The writer must preserve every retained same-time ancillary record exactly.
for short in ("RH", "PMSL", "PSFC", "SKINTEMP"):
    baseline_levels = {key[1] for key in baseline_wps if key[0] == short}
    writer_levels = {key[1] for key in candidate_wps if key[0] == short}
    if baseline_levels != writer_levels:
        raise AssertionError(f"captured ancillary levels changed for {short}")
    for level in baseline_levels:
        _, base_unit, base, base_meta = field(baseline_wps, short, level)
        _, unit, got, meta = field(candidate_wps, short, level)
        if unit != base_unit or meta["geometry"] != base_meta["geometry"] or not np.array_equal(base, got):
            raise AssertionError(f"same-time captured ancillary changed: {short}@{level}")

max_candidate_error: dict[str, float] = {}
profile_counts: dict[str, int] = {}
for k, pressure_pa in enumerate(pressure):
    level = float(pressure_pa)
    if level > 100100.0:
        continue  # The legacy WPS writer omits 1050 and 1100 hPa.
    legacy_index = pressure.size - 1 - k
    if legacy["p"][legacy_index] * 100.0 != level:
        raise AssertionError(f"candidate pressure does not map to captured LAPSPREP level {level}")
    active = above[k].T
    if active.shape != (legacy["dims"][0], legacy["dims"][1]):
        raise AssertionError("candidate support mask has the wrong horizontal shape")
    host_index = legacy_index
    host_fields = {
        "TT": legacy["t"][:, :, host_index], "HGT": legacy["ht"][:, :, host_index],
        "UU": legacy["u"][:, :, host_index], "VV": legacy["v"][:, :, host_index],
        "QV": legacy["qv"][:, :, host_index], "QC": legacy["qc"][:, :, host_index],
        "QI": legacy["qi"][:, :, host_index], "QR": legacy["qr"][:, :, host_index],
        "QS": legacy["qs"][:, :, host_index], "QG": legacy["qg"][:, :, host_index],
    }
    for short, candidate_data in profile.items():
        key, unit, got, meta = field(candidate_wps, short, level)
        if key[2] != "2026-08-16_13:00:00.0000":
            raise AssertionError(f"unexpected WPS valid time for {short}@{level}: {key[2]}")
        expected = np.where(active, candidate_data[k].T, host_fields[short])
        error = np.abs(got.astype(np.float64) - expected.astype(np.float64))
        if not np.array_equal(got, expected):
            raise AssertionError(f"{short}@{level} candidate/retained readback mismatch {error.max()}")
        max_candidate_error[short] = max(max_candidate_error.get(short, 0.0), float(error.max(initial=0.0)))
        profile_counts[short] = profile_counts.get(short, 0) + int(active.sum())

surface_host = {
    "TT": legacy["t"][:, :, -1], "HGT": legacy["ht"][:, :, -1],
    "QV": legacy["qv"][:, :, -1], "PSFC": legacy["psfc"],
    "UU": legacy["u"][:, :, -1], "VV": legacy["v"][:, :, -1],
}
for short, (candidate_values, valid) in surface.items():
    level = 200100.0
    _, unit, got, meta = field(candidate_wps, short, level)
    if (short, level, "2026-08-16_13:00:00.0000") not in candidate_wps:
        raise AssertionError(f"candidate surface {short} has the wrong WPS valid time")
    if short in ("TT", "PSFC") and not np.all(valid):
        raise AssertionError(f"candidate surface {short} must be complete for this handoff")
    expected = np.where(valid, candidate_values, surface_host[short])
    error = np.abs(got.astype(np.float64) - expected.astype(np.float64))
    if not np.array_equal(got, expected):
        raise AssertionError(f"candidate surface {short} readback mismatch {error.max()}")

for short in ("UU", "VV"):
    _, unit, got, metadata = field(candidate_wps, short, 200100.0)
    expected = surface_host[short]
    if unit != "m s{-1}" or not metadata.get("wind_grid_relative", False):
        raise AssertionError(f"retained surface wind metadata changed for {short}")
    if not np.array_equal(got, expected):
        raise AssertionError(f"retained surface wind changed for {short}")

# Legacy WPS writer emits zero-valued hydrometeor surface markers; these are
# writer fill records, not observed surface condensate.
for short in ("QC", "QI", "QR", "QS", "QG"):
    _, unit, got, _ = field(candidate_wps, short, 200100.0)
    if not np.array_equal(got, np.zeros_like(got)):
        raise AssertionError(f"legacy surface fill {short} is not exactly zero")

with out_path.open("x", encoding="utf-8") as receipt:
    json.dump({
    "status": "PASS_SCOPED_SAME13_CANDIDATE_WPS_READBACK",
    "science_authority": "NONE",
    "candidate_id": candidate_id,
    "valid_time_epoch": valid_time,
    "grid_id": grid_id,
    "wps_sha256": digest(wps_path),
    "wps_bytes": wps_path.stat().st_size,
    "captured_baseline_sha256": digest(baseline_path),
    "captured_inventory_sha256": digest(inventory_path),
    "ancillary_exact_fields": ["RH", "PMSL", "PSFC", "SKINTEMP"],
    "candidate_profile_fields": sorted(profile),
    "candidate_profile_above_ground_cells_verified": profile_counts,
    "candidate_profile_max_abs_error": max_candidate_error,
    "candidate_surface_fields": sorted(surface),
    "retained_surface_wind_fields": ["UU", "VV"],
    "legacy_surface_hydrometeor_zero_fill_fields": ["QC", "QI", "QR", "QS", "QG"],
    "wps_record_count": len(candidate_wps),
    "wps_metgrid_real_executed": False,
    }, receipt, indent=2, sort_keys=True, allow_nan=False)
