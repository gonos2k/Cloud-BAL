#!/usr/bin/env python3
"""Focused time-schema tests for the sloping-face input replay."""

from pathlib import Path
import sys
import tempfile

import netCDF4
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from diagnose_qbal_sloping_faces import (  # noqa: E402
    TIME_UNITS,
    validate_product_time,
)


EPOCH = 1786885200


def write_time_file(
    path: Path,
    value,
    *,
    dtype: str = "f8",
    dimensions: tuple[str, ...] = ("record",),
    record_size: int = 1,
    units: str | None = TIME_UNITS,
    fill_value=None,
) -> None:
    with netCDF4.Dataset(path, "w", format="NETCDF4") as dataset:
        dataset.createDimension("record", record_size)
        if "sample" in dimensions:
            dataset.createDimension("sample", 1)
        options = {} if fill_value is None else {"fill_value": fill_value}
        variable = dataset.createVariable("valtime", dtype, dimensions, **options)
        if units is not None:
            variable.units = units
        variable[:] = np.asarray(value, dtype=dtype)


def expect_rejection(path: Path, expected_message: str) -> None:
    with netCDF4.Dataset(path) as dataset:
        try:
            validate_product_time(dataset, EPOCH, "LSX")
        except ValueError as error:
            assert expected_message in str(error), str(error)
        else:
            raise AssertionError(f"accepted malformed time file: {path.name}")


def test_exact_integer_times_pass() -> None:
    with tempfile.TemporaryDirectory(prefix="qbal-sloping-time-") as directory:
        root = Path(directory)
        for product_name in ("lsx", "lw3"):
            path = root / f"{product_name}.nc"
            write_time_file(path, EPOCH)
            with netCDF4.Dataset(path) as dataset:
                assert validate_product_time(dataset, EPOCH, product_name.upper()) == EPOCH


def test_fractional_wrong_nonfinite_and_fill_times_reject() -> None:
    cases = (
        ("fraction-025.nc", EPOCH + 0.25, {}, "fractional seconds"),
        ("fraction-075.nc", EPOCH + 0.75, {}, "fractional seconds"),
        ("wrong-integer.nc", EPOCH + 1, {}, "time mismatch"),
        ("nan.nc", np.nan, {}, "nonfinite"),
        ("fill.nc", -9999.0, {"fill_value": -9999.0}, "missing value"),
    )
    with tempfile.TemporaryDirectory(prefix="qbal-sloping-time-") as directory:
        root = Path(directory)
        for name, value, options, message in cases:
            path = root / name
            write_time_file(path, value, **options)
            expect_rejection(path, message)


def test_units_and_schema_reject() -> None:
    cases = (
        ("wrong-units.nc", {"units": "hours since (1970-1-1 00:00:00.0)"}, "invalid units"),
        ("missing-units.nc", {"units": None}, "missing units"),
        ("wrong-dtype.nc", {"dtype": "f4"}, "scalar double required"),
        ("wrong-dimension.nc", {"dimensions": ("sample",)}, "record dimension required"),
        ("multiple-records.nc", {"record_size": 2, "value": [EPOCH, EPOCH]}, "single record required"),
    )
    with tempfile.TemporaryDirectory(prefix="qbal-sloping-time-") as directory:
        root = Path(directory)
        for name, options, message in cases:
            path = root / name
            value = options.pop("value", EPOCH)
            write_time_file(path, value, **options)
            expect_rejection(path, message)


if __name__ == "__main__":
    test_exact_integer_times_pass()
    test_fractional_wrong_nonfinite_and_fill_times_reject()
    test_units_and_schema_reject()
    print("QBAL sloping input time checks passed")
