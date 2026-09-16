#!/usr/bin/env python3
"""Independent readback of the scoped, all-valid 6x6x4 BALCON candidate."""

import hashlib
import json
from pathlib import Path
import sys

import netCDF4
import numpy as np


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify(candidate, output_root, i4time):
    raw = candidate.read_bytes()
    dimensions = np.frombuffer(raw, dtype="<i4", count=3)
    require(tuple(dimensions) == (6, 6, 4), "unexpected candidate dimensions")
    nx, ny, nz = map(int, dimensions)
    count = nx * ny * nz
    require(len(raw) == 12 + 4 * (nz + 6 * count), "candidate length mismatch")
    pressure = np.frombuffer(raw, dtype="<f4", count=nz, offset=12)
    fields = np.frombuffer(raw, dtype="<f4", offset=12 + 4 * nz).reshape(6, nz, ny, nx)
    require(np.isfinite(fields).all(), "candidate contains nonfinite values")
    require(np.array_equal(pressure, [100000, 90000, 80000, 70000]), "candidate pressure mismatch")
    u, v, phi, temperature, moisture, omega = fields
    # Match the declared float32 conversion at qbalpe's writer boundary.
    height = phi / np.float32(9.80665)
    expected = {
        "lw3": [("u3", u, "meters / second"), ("v3", v, "meters / second"),
                ("om", omega, "pascals / second")],
        "lt1": [("ht", height, "meters"), ("t3", temperature, "degrees Kelvin")],
        "lq3": [("sh", moisture, "kg/kg")],
    }
    laps_units = {"u3": "M/S", "v3": "M/S", "om": "PA/S", "ht": "METERS",
                  "t3": "K", "sh": "none"}  # Preserve the actual upstream CDL attributes.
    results = []
    for extension, variables in expected.items():
        paths = list((output_root / "balance" / extension).glob(f"*.{extension}"))
        require(len(paths) == 1, f"expected one {extension} output")
        path = paths[0]
        with netCDF4.Dataset(path) as dataset:
            require(tuple(len(dataset.dimensions[name]) for name in ("record", "z", "y", "x"))
                    == (1, nz, ny, nx), f"{extension}: dimensions mismatch")
            levels = dataset.variables["level"]
            require(levels.units == "hectopascals", f"{extension}: pressure units mismatch")
            level_values = levels[:]
            require(not np.ma.getmaskarray(level_values).any(),
                    f"{extension}: level: unexpected missing mask")
            require(np.isfinite(np.asarray(level_values)).all(),
                    f"{extension}: level: nonfinite coordinate")
            # The actual LAPS writer stores pressure levels in ascending order.
            require(np.array_equal(level_values, pressure[::-1] / np.float32(100)),
                    f"{extension}: pressure levels mismatch")
            for name in ("reftime", "valtime"):
                time = dataset.variables[name]
                require(time.units == "seconds since (1970-1-1 00:00:00.0)",
                        f"{extension}: {name} units mismatch")
                time_values = time[:]
                require(not np.ma.getmaskarray(time_values).any(),
                        f"{extension}: {name}: unexpected missing mask")
                require(np.isfinite(np.asarray(time_values)).all(),
                        f"{extension}: {name}: nonfinite coordinate")
                require(np.array_equal(time_values, [i4time - 315619200]),
                        f"{extension}: {name} mismatch")
            for name, values, units in variables:
                variable = dataset.variables[name]
                require(variable.dimensions == ("record", "z", "y", "x"),
                        f"{name}: array order mismatch")
                require(variable.dtype == np.dtype("float32"), f"{name}: precision mismatch")
                require(variable.units == units and variable.lvl_coord.strip() == "HPA",
                        f"{name}: units or level coordinate mismatch")
                require(variable.LAPS_var == name.upper() and variable.LAPS_units == laps_units[name],
                        f"{name}: LAPS metadata mismatch")
                actual = variable[0]
                require(not np.ma.getmaskarray(actual).any(), f"{name}: unexpected missing mask")
                require(np.isfinite(actual).all(), f"{name}: nonfinite output")
                # NetCDF float32 storage is lossless, including the sign of zero.
                require(np.array_equal(np.asarray(actual, dtype="<f4").view("<u4"),
                                       values[::-1].astype("<f4").view("<u4")),
                        f"{name}: candidate/readback bits differ")
                inventory = dataset.variables[name + "_fcinv"]
                require(inventory.dimensions == ("record", "z") and inventory.dtype == np.dtype("int16"),
                        f"{name}: inventory layout mismatch")
                require(not np.ma.getmaskarray(inventory[:]).any() and np.all(inventory[:] == 1),
                        f"{name}: incomplete level inventory")
                results.append({"field": name, "units": units, "comparison": "float32 bitwise",
                                "all_valid": True})
    return {"status": "PASS_SCOPED", "candidate_sha256": hashlib.sha256(raw).hexdigest(),
            "fields": results, "height_conversion": "float32 PHI / float32(9.80665)",
            "level_mapping": "descending candidate pressure -> ascending file pressure",
            "scope": "Actual LAPS writer readback; uniform pressure, all-valid synthetic candidate",
            "open": ["full main postprocessing", "terrain/missing masks", "native consumption",
                     "full mass closure", "thermodynamic accuracy", "forecast effects"]}


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("usage: verify_qbal_writer.py candidate.bin output_root i4time")
    try:
        print(json.dumps(verify(Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3])), indent=2))
    except (ValueError, KeyError, OSError) as error:
        raise SystemExit(f"QBAL writer readback failed: {error}") from error
