"""Regression tests for native NetCDF masks and fill values."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import netCDF4
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pr82_same13_native_readback import (  # noqa: E402
    bind_run_receipt, field_record, sha256, unmasked_values,
)


class NativeReadbackMissingDataTests(unittest.TestCase):
    def _write_field(self, path: Path, *, fill_value: float = 9.969209968386869e36) -> None:
        with netCDF4.Dataset(path, "w") as dataset:
            dataset.createDimension("Time", 1)
            dataset.createDimension("bottom_top", 2)
            dataset.createDimension("south_north", 2)
            dataset.createDimension("west_east", 2)
            variable = dataset.createVariable(
                "QNCLOUD", "f4",
                ("Time", "bottom_top", "south_north", "west_east"),
                fill_value=np.float32(fill_value),
            )
            variable.units = "kg-1"
            variable[:] = np.ones((1, 2, 2, 2), dtype=np.float32)
            variable[0, 0, 0, 0] = np.float32(fill_value)

    def test_masked_fill_value_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "masked.nc"
            self._write_field(path)
            with netCDF4.Dataset(path) as dataset:
                with self.assertRaisesRegex(ValueError, "masked values are forbidden"):
                    unmasked_values(dataset.variables["QNCLOUD"])

    def test_fill_is_rejected_even_when_netcdf_masking_is_disabled(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "unmasked-fill.nc"
            self._write_field(path)
            with netCDF4.Dataset(path) as dataset:
                variable = dataset.variables["QNCLOUD"]
                variable.set_auto_mask(False)
                with self.assertRaisesRegex(ValueError, "explicit _FillValue"):
                    field_record(
                        variable,
                        ("Time", "bottom_top", "south_north", "west_east"),
                        None,
                        "kg-1",
                    )

    def test_fully_valid_number_field_is_readable(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "valid.nc"
            with netCDF4.Dataset(path, "w") as dataset:
                dataset.createDimension("Time", 1)
                dataset.createDimension("bottom_top", 2)
                dataset.createDimension("south_north", 2)
                dataset.createDimension("west_east", 2)
                variable = dataset.createVariable(
                    "QNCLOUD", "f4",
                    ("Time", "bottom_top", "south_north", "west_east"),
                    fill_value=np.float32(-9999.0),
                )
                variable.units = "kg-1"
                variable[:] = np.ones((1, 2, 2, 2), dtype=np.float32)
            with netCDF4.Dataset(path) as dataset:
                record = field_record(
                    dataset.variables["QNCLOUD"],
                    ("Time", "bottom_top", "south_north", "west_east"),
                    None,
                    "kg-1",
                )
            self.assertEqual(record["positive_cells"], 8)
            self.assertEqual(record["zero_cells"], 0)

    def test_receipt_binding_rejects_swapped_readback_output(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source, output, wrong_output = (root / name for name in
                                             ("wrfin.nc", "wrfout.nc", "other-wrfout.nc"))
            source.write_bytes(b"candidate-input")
            output.write_bytes(b"matching-initial-output")
            wrong_output.write_bytes(b"different-initial-output")
            receipt = {
                "candidate_wrfinput_sha256": sha256(source),
                "initial_wrfo_sha256": sha256(output),
            }
            self.assertEqual(bind_run_receipt(receipt, source, output)["initial_wrfo_sha256"],
                             sha256(output))
            with self.assertRaisesRegex(ValueError, "initial wrfout hash"):
                bind_run_receipt(receipt, source, wrong_output)


if __name__ == "__main__":
    unittest.main()
