#!/usr/bin/env python3
"""Focused tests for the canonical schema-5 surface-boundary extension."""

from pathlib import Path
import sys
import tempfile

import netCDF4
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from validate_shadow_diagnostics import (  # noqa: E402
    read_surface_boundary_extension,
)


SHAPE = (2, 2)
EPOCH = 1_725_000_000
UNITS = {
    "pressure": "Pa",
    "temperature": "K",
    "vapor": "kg kg-1 dryair",
    "height": "m",
}


def write_fixture(path: Path, *, canonical: int = 5, omit: str | None = None,
                  mutate=None, mask_dtype: str = "i4") -> None:
    values = {
        "pressure": np.full(SHAPE, 100000.0, dtype=np.float32),
        "temperature": np.full(SHAPE, 290.0, dtype=np.float32),
        "vapor": np.array([[0.01, np.nan], [0.02, np.nan]], dtype=np.float32),
        "height": np.array([[100.0, np.nan], [np.nan, 200.0]], dtype=np.float32),
    }
    valid = {
        "pressure": np.ones(SHAPE, dtype=np.int32),
        "temperature": np.ones(SHAPE, dtype=np.int32),
        "vapor": np.array([[1, 0], [1, 0]], dtype=np.int32),
        "height": np.array([[1, 0], [0, 1]], dtype=np.int32),
    }
    quality = {
        name: np.where(mask, 0, 1).astype(np.int32)
        for name, mask in ((key, value == 1) for key, value in valid.items())
    }
    source = {
        name: np.where(mask, 1, 0).astype(np.int32)
        for name, mask in ((key, value == 1) for key, value in valid.items())
    }
    if mutate is not None:
        mutate(values, valid, quality, source)

    with netCDF4.Dataset(path, "w") as dataset:
        dataset.createDimension("y", SHAPE[0])
        dataset.createDimension("x", SHAPE[1])
        dataset.setncattr("cloud_bal_schema_version", np.int32(canonical))
        dataset.setncattr("surface_boundary_contract", "CANONICAL_SURFACE_BOUNDARY_V1")
        for role in ("background", "candidate"):
            for name in ("pressure", "temperature", "vapor", "height"):
                prefix = f"{role}_surface_{name}"
                if prefix == omit:
                    continue
                value = dataset.createVariable(prefix, "f4", ("y", "x"))
                value.units = UNITS[name]
                value.valid_time = np.int64(EPOCH)
                value[:] = values[name]
                metadata_variables = (
                    (f"{prefix}_valid", mask_dtype, valid[name]),
                    (f"{prefix}_quality", "i4", quality[name]),
                    (f"{prefix}_source", "i4", source[name]),
                )
                for metadata_name, metadata_type, metadata_values in metadata_variables:
                    if metadata_name == omit:
                        continue
                    metadata_variable = dataset.createVariable(
                        metadata_name, metadata_type, ("y", "x")
                    )
                    metadata_variable.units = "1"
                    metadata_variable[:] = metadata_values


def read(path: Path, *, canonical: int = 5, reference: bool = True):
    failures: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    with netCDF4.Dataset(path) as dataset:
        result = read_surface_boundary_extension(
            dataset,
            SHAPE,
            EPOCH,
            canonical,
            np.full(SHAPE, 100000.0, dtype=np.float32) if reference else None,
            require,
        )
    return result, failures


with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    positive = root / "positive.nc"
    write_fixture(positive)
    (present, clean, _), failures = read(positive)
    assert present and clean and not failures

    # Invalid optional payloads are opaque, including NaN bit patterns.
    (present, clean, _), failures = read(positive)
    assert present and clean and not failures

    cases = {
        "missing_member.nc": lambda: write_fixture(
            root / "missing_member.nc", omit="candidate_surface_height_source"
        ),
        "downgraded.nc": lambda: write_fixture(root / "downgraded.nc", canonical=4),
        "bad_mask.nc": lambda: write_fixture(root / "bad_mask.nc", mask_dtype="i2"),
    }
    for name, build in cases.items():
        build()
        (present, clean, _), failures = read(
            root / name, canonical=4 if name == "downgraded.nc" else 5
        )
        assert present and not clean and failures, name

    changed = root / "changed_candidate.nc"
    write_fixture(changed)
    with netCDF4.Dataset(changed, "r+") as dataset:
        dataset.variables["candidate_surface_temperature"][0, 0] = np.float32(291.0)
    (present, clean, _), failures = read(changed)
    assert present and not clean and failures, "changed_candidate.nc"

print("Surface-boundary validator tests passed")
