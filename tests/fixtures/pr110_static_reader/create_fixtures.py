#!/usr/bin/env python3
"""Create tiny classic NetCDF static-grid files for the actual reader test."""
from pathlib import Path
import sys

import numpy as np
from netCDF4 import Dataset


root = Path(sys.argv[1])
root.mkdir(parents=True, exist_ok=True)


def write_case(name: str, *, dx_type="f4", dx_value=5000.0, dx_length=1,
               dy_value=5000.0, lat_type="f4", lat_shape=(1, 1, 2, 3),
               lat_dims=None, avg_type="f4", omit_lat=False, grid_type_dims=("nav", "namelen"), grid_len=132):
    directory = root / name / "static"
    directory.mkdir(parents=True, exist_ok=True)
    with Dataset(directory / "static.nest7grid", "w", format="NETCDF3_CLASSIC") as ds:
        ds.createDimension("x", 3)
        ds.createDimension("y", 2)
        ds.createDimension("z", 1)
        ds.createDimension("record", lat_shape[0])
        ds.createDimension("nav", 1)
        ds.createDimension("namelen", grid_len)
        ds.createDimension("dxn", dx_length)
        grid_data = np.frombuffer(b"lambert".ljust(grid_len), dtype="S1")
        ds.createVariable("grid_type", "S1", grid_type_dims)[:] = grid_data.reshape((1, grid_len)) if len(grid_type_dims) == 2 else grid_data
        for var, dtype, values in (("Dx", dx_type, [dx_value] * dx_length), ("Dy", "f4", [dy_value]), ("LoV", "f4", [0.0]), ("Latin1", "f4", [30.0]), ("Latin2", "f4", [60.0])):
            ds.createVariable(var, dtype, ("dxn",) if var == "Dx" else ("nav",))[:] = values
        shape = lat_shape
        for var, dtype in (("lat", lat_type), ("lon", "f4"), ("avg", avg_type)):
            if var == "lat" and omit_lat:
                continue
            dims = lat_dims or (("record", "z", "y", "x") if len(shape) == 4 else ("record", "z", "y", "x", "extra"))
            if "extra" in dims and "extra" not in ds.dimensions:
                ds.createDimension("extra", 1)
            if "extra2" in dims and "extra2" not in ds.dimensions:
                ds.createDimension("extra2", 2)
            data_shape = tuple(len(ds.dimensions[dim]) for dim in dims)
            data = np.arange(np.prod(data_shape), dtype=np.float32).reshape(data_shape)
            ds.createVariable(var, dtype, dims)[:] = data


write_case("float_ok")
write_case("double_dx", dx_type="f8")
write_case("double_lat", lat_type="f8")
write_case("double_avg", avg_type="f8")
write_case("bad_lat_rank", lat_shape=(1, 1, 2, 3, 1))
write_case("missing_lat", omit_lat=True)
write_case("zero_dx", dx_value=0.0)
write_case("negative_dx", dx_value=-5000.0)
write_case("nan_dx", dx_value=float("nan"))
write_case("zero_dy", dy_value=0.0)
write_case("negative_dy", dy_value=-5000.0)
write_case("nan_dy", dy_value=float("nan"))
write_case("long_dx", dx_length=2)
write_case("swapped_lat_axes", lat_dims=("record", "z", "x", "y"))
write_case("long_trailing_lat_axis", lat_shape=(2, 1, 2, 3), lat_dims=("record", "z", "y", "x"))
write_case("bad_grid_type_length", grid_type_dims=("nav", "namelen"), grid_len=133)
write_case("bad_grid_type_rank", grid_type_dims=("namelen",))
