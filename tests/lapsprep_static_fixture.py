#!/usr/bin/env python3
"""Write the static-grid file used by the actual lapsprep writer regression."""

from __future__ import annotations

import argparse
from pathlib import Path

import netCDF4
import numpy as np


def write_static(root: Path, case: str) -> None:
    path = root / "static" / "static.nest7grid"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    with netCDF4.Dataset(path, "w", format="NETCDF3_CLASSIC") as dataset:
        dataset.createDimension("x", 2)
        dataset.createDimension("y", 2)
        dataset.createDimension("z", 1)
        dataset.createDimension("record", 1)
        dataset.createDimension("projection_length", 132)
        projection = "secant lambert conformal" if case in {"latin1_nan", "latin2_91"} else "mercator"
        grid_type = np.frombuffer(projection.encode("ascii").ljust(132), dtype="S1")
        dataset.createVariable("grid_type", "S1", ("record", "projection_length"))[:] = grid_type.reshape(1, 132)

        dx = dataset.createVariable("Dx", "f4", ("record",), fill_value=5000.0 if case == "dx_fill_5000" else None)
        if case != "dx_unwritten":
            dx[:] = 5000.0 if case in {"dx_fill_5000", "dx_missing_value_5000"} else 1000.0
        if case == "dx_missing_value_5000":
            dx.missing_value = np.float32(5000.0)
        for name, value in (("Dy", 1000.0), ("LoV", 126.0), ("Latin1", 30.0), ("Latin2", 91.0 if case == "latin2_91" else 60.0)):
            var = dataset.createVariable(name, "f4", ("record",))
            var[:] = np.nan if case in {"latin1_nan", "lov_nan"} and name == ("Latin1" if case == "latin1_nan" else "LoV") else value
            if case == "lov_400" and name == "LoV":
                var[:] = 400.0

        for name in ("lat", "lon", "avg"):
            var = dataset.createVariable(name, "f4", ("record", "z", "y", "x"))
            var[:] = 100.0 if name == "avg" else (
                np.array([[[[35.0, 35.0], [36.0, 36.0]]]], dtype=np.float32)
                if name == "lat" else
                np.array([[[[126.0, 127.0], [126.0, 127.0]]]], dtype=np.float32)
            )
        if case == "swlat_200":
            dataset["lat"][0, 0, 0, 0] = 200.0
        elif case == "lat_array_missing":
            lat = dataset.variables["lat"]
            lat.set_auto_mask(False)
            # Keep the single bad value off the southwest/northeast corner pair.
            lat[0, 0, 0, 1] = np.float32(1.0e20)
            lat.missing_value = np.float32(1.0e20)
        elif case == "lat_array_nonfinite":
            dataset["lat"][0, 0, 0, 1] = np.nan
        elif case == "lon_400":
            dataset["lon"][0, 0, 0, 0] = 400.0
        elif case == "avg_array_missing":
            avg = dataset.variables["avg"]
            avg.set_auto_mask(False)
            avg[0, 0, 0, 1] = np.float32(1.0e20)
            avg.missing_value = np.float32(1.0e20)
        elif case == "lat_nan_marker":
            dataset["lat"].missing_value = np.float32(np.nan)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("case", nargs="?", default="valid")
    args = parser.parse_args()
    write_static(args.root, args.case)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
