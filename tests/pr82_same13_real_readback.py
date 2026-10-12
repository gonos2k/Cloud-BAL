#!/usr/bin/env python3
"""Read back a same-time real.exe product without modifying it."""
import hashlib
import json
from pathlib import Path
import sys

import netCDF4
import numpy as np


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


met_em, wrfinput, receipt = map(Path, sys.argv[1:])
if receipt.exists() or receipt.is_symlink():
    raise SystemExit("real readback receipt already exists")
with netCDF4.Dataset(met_em) as met, netCDF4.Dataset(wrfinput) as wrf:
    met_time = b"".join(met.variables["Times"][0].tolist()).decode().strip()
    wrf_time = b"".join(wrf.variables["Times"][0].tolist()).decode().strip()
    dims = {name: len(wrf.dimensions[name]) for name in
            ("Time", "west_east", "south_north", "bottom_top", "bottom_top_stag")}
    expected_dims = {"Time": 1, "west_east": 234, "south_north": 282,
                     "bottom_top": 39, "bottom_top_stag": 40}
    if dims != expected_dims:
        raise SystemExit(f"unexpected wrfinput dimensions: {dims}")
    if met_time != "2026-08-16_13:00:00" or wrf_time != met_time:
        raise SystemExit(f"unexpected real/metgrid timestamps: {met_time}, {wrf_time}")
    required = ("QVAPOR", "QCLOUD", "QICE", "QRAIN", "QSNOW", "QGRAUP",
                "PSFC", "P", "PB", "T", "PH", "PHB", "U", "V", "W", "MU", "MUB")
    expected_contract = {
        **{name: (("Time", "bottom_top", "south_north", "west_east"), "kg kg-1")
           for name in ("QVAPOR", "QCLOUD", "QICE", "QRAIN", "QSNOW", "QGRAUP")},
        "PSFC": (("Time", "south_north", "west_east"), "Pa"),
        "MU": (("Time", "south_north", "west_east"), "Pa"),
        "MUB": (("Time", "south_north", "west_east"), "Pa"),
        "P": (("Time", "bottom_top", "south_north", "west_east"), "Pa"),
        "PB": (("Time", "bottom_top", "south_north", "west_east"), "Pa"),
        "T": (("Time", "bottom_top", "south_north", "west_east"), "K"),
        "PH": (("Time", "bottom_top_stag", "south_north", "west_east"), "m2 s-2"),
        "PHB": (("Time", "bottom_top_stag", "south_north", "west_east"), "m2 s-2"),
        "U": (("Time", "bottom_top", "south_north", "west_east_stag"), "m s-1"),
        "V": (("Time", "bottom_top", "south_north_stag", "west_east"), "m s-1"),
        "W": (("Time", "bottom_top_stag", "south_north", "west_east"), "m s-1"),
    }
    n_moments = sorted(name for name in wrf.variables if name.startswith("QN"))
    for name in required:
        if name not in wrf.variables:
            raise SystemExit(f"real.exe did not write required variable {name}")
    checks = {}
    for name in (*required, *n_moments):
        variable = wrf.variables[name]
        if name in expected_contract:
            expected_dimensions, expected_units = expected_contract[name]
            if variable.dimensions != expected_dimensions or getattr(variable, "units", None) != expected_units:
                raise SystemExit(f"real.exe {name} dimensions/units mismatch")
        elif variable.dimensions != expected_contract["P"][0] or not getattr(variable, "units", "").strip():
            raise SystemExit(f"real.exe {name} number-moment dimensions/units mismatch")
        values = np.asarray(variable[:])
        if not np.isfinite(values).all():
            raise SystemExit(f"non-finite value in {name}")
        checks[name] = {"shape": list(values.shape), "dtype": str(values.dtype),
                        "dimensions": list(variable.dimensions),
                        "units": getattr(variable, "units", None),
                        "sha256_f32": hashlib.sha256(values.astype("<f4", copy=False).tobytes()).hexdigest(),
                        "min": float(values.min()), "max": float(values.max())}
    q = np.asarray(wrf.variables["QVAPOR"][:])
    if np.any(q < 0):
        raise SystemExit("negative QVAPOR in real.exe output")
    for name in ("QCLOUD", "QICE", "QRAIN", "QSNOW", "QGRAUP"):
        if np.any(np.asarray(wrf.variables[name][:]) < 0):
            raise SystemExit(f"negative mixing ratio in {name}")
    physical_pressure = np.asarray(wrf.variables["P"][:], dtype=np.float64) + \
        np.asarray(wrf.variables["PB"][:], dtype=np.float64)
    if not np.isfinite(physical_pressure).all() or np.any(physical_pressure <= 0):
        raise SystemExit("physical pressure P+PB is not finite and positive")
    if wrf.variables["T"].getncattr("description") != "perturbation potential temperature theta-t0":
        raise SystemExit("unexpected WRF T semantics")
    evidence = {
        "status": "PASS_SCOPED_SAME13_REAL_READBACK",
        "time": wrf_time,
        "dims": dims,
        "candidate_met_em_sha256": sha256(met_em),
        "wrfinput_sha256": sha256(wrfinput),
        "variables": checks,
        "required_mass_and_staggered_fields": list(required),
        "available_number_moment_fields": n_moments,
        "physical_pressure_p_plus_pb_pa": {
            "shape": list(physical_pressure.shape), "min": float(physical_pressure.min()),
            "max": float(physical_pressure.max()),
        },
        "T_semantics": "perturbation potential temperature theta minus base theta; stored units K do not make T an absolute temperature",
        "native_component_version_note": "real.exe output is WRF V4.6.0; retained native diagnostic consumer is a distinct WRF v4.8 component",
        "science_authority": "NONE",
    }
receipt.write_text(json.dumps(evidence, sort_keys=True, indent=2) + "\n")
