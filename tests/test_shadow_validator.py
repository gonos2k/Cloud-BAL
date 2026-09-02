#!/usr/bin/env python3
"""Small contract tests for the independent SHADOW validator."""

from pathlib import Path
import sys
import tempfile

import netCDF4
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from validate_shadow_diagnostics import (  # noqa: E402
    canonical_omega_target_cells,
    is_signed_int32,
    values,
)


def accepted(*, above=True, quality=0, source=1, target=0.0) -> bool:
    result = canonical_omega_target_cells(
        np.array([True]),
        np.array([above]),
        np.array([quality], dtype=np.int64),
        np.array([source], dtype=np.int64),
        np.array([target], dtype=np.float64),
    )
    return bool(result[0])


assert accepted()
assert not accepted(above=False)
assert not accepted(source=0)
assert not accepted(quality=1)
assert not accepted(target=100.1)
assert not accepted(target=np.nan)
assert is_signed_int32(np.dtype(np.int32))
assert is_signed_int32(np.dtype(">i4"))
assert not is_signed_int32(np.dtype(np.float32))
assert not is_signed_int32(np.dtype(np.float64))
assert not is_signed_int32(np.dtype(np.int64))
assert not is_signed_int32(np.dtype(np.uint32))

with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / "packed.nc"
    with netCDF4.Dataset(path, "w") as dataset:
        dataset.createDimension("cell", 1)
        variable = dataset.createVariable("packed", "i4", ("cell",))
        variable.add_offset = 0.5
        variable[:] = np.array([80.5])
    with netCDF4.Dataset(path) as dataset:
        assert is_signed_int32(dataset["packed"].dtype)
        assert not is_signed_int32(values(dataset["packed"]).dtype)

print("Shadow diagnostic validator tests passed")
