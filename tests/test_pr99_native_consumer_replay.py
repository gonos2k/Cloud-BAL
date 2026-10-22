from pathlib import Path
import sys
import tempfile
import unittest

import netCDF4
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import pr99_native_consumer_replay as replay  # noqa: E402


class NativeConsumerInputTest(unittest.TestCase):
    def test_native_arrays_reject_wrong_c1_grid_before_reading_variables(self):
        with tempfile.TemporaryDirectory(prefix="pr99-consumer-grid-") as tmp:
            path = Path(tmp) / "wrong_grid.nc"
            with netCDF4.Dataset(path, "w") as dataset:
                dataset.createDimension("time", 1)
                dataset.createDimension("west_east", 233)
                dataset.createDimension("south_north", 282)
                dataset.createDimension("bottom_top", 39)
            with netCDF4.Dataset(path) as dataset:
                with self.assertRaisesRegex(ValueError, "C1 calc_ww_cp requires mass dimensions"):
                    replay.native_arrays(dataset, 0)

    def test_field_rejects_fill_sentinel_and_preserves_valid_values(self):
        with tempfile.TemporaryDirectory(prefix="pr99-consumer-fill-") as tmp:
            path = Path(tmp) / "fields.nc"
            with netCDF4.Dataset(path, "w") as dataset:
                dataset.createDimension("time", 1)
                dataset.createDimension("x", 2)
                valid = dataset.createVariable("VALID", "f4", ("time", "x"), fill_value=-9999.0)
                invalid = dataset.createVariable("INVALID", "f4", ("time", "x"), fill_value=-9999.0)
                valid[0] = [1.25, 2.5]
                invalid[0] = [1.25, -9999.0]
            with netCDF4.Dataset(path) as dataset:
                np.testing.assert_array_equal(replay.field(dataset, "VALID", 0), [1.25, 2.5])
                with self.assertRaisesRegex(ValueError, "declared _FillValue"):
                    replay.field(dataset, "INVALID", 0)


if __name__ == "__main__":
    unittest.main()
