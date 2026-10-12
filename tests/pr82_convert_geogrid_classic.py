#!/usr/bin/env python3
"""Convert a detached real geogrid file to classic NetCDF without data changes."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

source, output = map(Path, sys.argv[1:3])

def same_value(left, right):
    return np.array_equal(np.asarray(left), np.asarray(right))
source = source.resolve(strict=True)
if not source.is_file():
    raise SystemExit(f"resolved source geogrid is not a regular file: {source}")
if output.exists() or output.is_symlink():
    raise SystemExit(f"classic geogrid destination already exists: {output}")

with Dataset(source) as src, Dataset(output, "w", format="NETCDF3_CLASSIC") as dst:
    if src.groups:
        raise SystemExit("grouped geogrid format is outside this converter's contract")
    for name, dim in src.dimensions.items():
        dst.createDimension(name, None if dim.isunlimited() else len(dim))
    for name in src.ncattrs():
        dst.setncattr(name, src.getncattr(name))
    for name, variable in src.variables.items():
        if variable.dtype.kind not in "biufcS":
            raise SystemExit(f"unsupported geogrid variable dtype {name}: {variable.dtype}")
        kwargs = {}
        if "_FillValue" in variable.ncattrs():
            kwargs["fill_value"] = variable.getncattr("_FillValue")
        target = dst.createVariable(name, variable.dtype, variable.dimensions, **kwargs)
        for attr in variable.ncattrs():
            if attr != "_FillValue":
                target.setncattr(attr, variable.getncattr(attr))
        target[:] = variable[:]

# Verify the converted artifact preserves every global and per-variable value
# and attribute exactly. Only the NetCDF container representation may change.
with Dataset(source) as src, Dataset(output) as dst:
    if set(src.dimensions) != set(dst.dimensions) or set(src.variables) != set(dst.variables):
        raise SystemExit("classic geogrid variable/dimension inventory changed")
    for name in src.ncattrs():
        if not same_value(src.getncattr(name), dst.getncattr(name)):
            raise SystemExit(f"classic geogrid global attribute changed: {name}")
    for name, variable in src.variables.items():
        target = dst.variables[name]
        if variable.dimensions != target.dimensions or variable.dtype != target.dtype:
            raise SystemExit(f"classic geogrid schema changed: {name}")
        if not np.array_equal(variable[:], target[:]):
            raise SystemExit(f"classic geogrid data changed: {name}")
        for attr in variable.ncattrs():
            if not same_value(variable.getncattr(attr), target.getncattr(attr)):
                raise SystemExit(f"classic geogrid variable attribute changed: {name}.{attr}")
print(f"preserved_variables={len(src.variables)}")
