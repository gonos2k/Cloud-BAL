from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

import numpy as np
from netCDF4 import Dataset

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from pr84_same13_boundary_contract import (
    BOUNDARY_UNITS,
    KDM6_MOMENTS,
    SUFFIXES,
    WATER_MASSES,
    sha256,
    summarize_boundary,
)


def write_boundary(path: Path, *, positive_unpaired_cloud: bool = False,
                   positive_orphan_number: bool = False,
                   masked_cloud: bool = False, nonfinite_number: bool = False,
                   negative_boundary_tendency: bool = False) -> None:
    carriers = tuple(dict.fromkeys((*WATER_MASSES, *KDM6_MOMENTS)))
    with Dataset(path, "w") as boundary:
        boundary.createDimension("Time", 2)
        boundary.createDimension("DateStrLen", 19)
        boundary.createDimension("bdy_width", 5)
        boundary.createDimension("bottom_top", 39)
        boundary.createDimension("south_north", 282)
        boundary.createDimension("west_east", 234)
        times = boundary.createVariable("Times", "S1", ("Time", "DateStrLen"))
        times[:] = np.array([list("2026-08-16_13:00:00"),
                             list("2026-08-16_14:00:00")], dtype="S1")
        for base in carriers:
            for suffix in SUFFIXES:
                dims = (("Time", "bdy_width", "bottom_top", "south_north")
                        if suffix.endswith(("BXS", "BXE", "BTXS", "BTXE")) else
                        ("Time", "bdy_width", "bottom_top", "west_east"))
                variable = boundary.createVariable(base + suffix, "f4", dims,
                                                   zlib=True, fill_value=9.96921e36)
                variable.units = BOUNDARY_UNITS[base]
                variable[:] = 0.0
        if positive_unpaired_cloud:
            boundary.variables["QCLOUD_BXS"][0, 0, 0, 0] = 1e-5
        if positive_orphan_number:
            boundary.variables["QNCLOUD_BXS"][0, 0, 0, 0] = 1.0
        if masked_cloud:
            cloud = boundary.variables["QCLOUD_BXS"]
            cloud[0, 0, 0, 0] = cloud._FillValue
        if nonfinite_number:
            boundary.variables["QNICE_BXS"][0, 0, 0, 0] = np.nan
        if negative_boundary_tendency:
            boundary.variables["QCLOUD_BTXS"][0, 0, 0, 0] = -1e-7
        # BT mass/moment tendencies can differ under microphysical sources.


class Same13BoundaryContractTest(unittest.TestCase):
    def test_zero_zero_boundary_forcing_is_supported_and_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wrfbdy_d01"
            write_boundary(path)
            result = summarize_boundary(path, expected_empty_sha256=sha256(path))

        self.assertEqual(result["status"], "PASS_RETAINED_EMPTY_BOUNDARY")
        self.assertTrue(result["empty_forcing_pair_support"])
        self.assertEqual(result["field_count_expected"], 80)
        self.assertEqual(result["field_count_observed"], 80)
        self.assertEqual(result["times"], ["2026-08-16_13:00:00", "2026-08-16_14:00:00"])
        self.assertTrue(result["read_only_integrity"])

    def test_positive_mass_with_zero_number_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wrfbdy_d01"
            write_boundary(path, positive_unpaired_cloud=True)
            result = summarize_boundary(path)

        self.assertFalse(result["structural_pass"])
        self.assertIn("positive_mass_zero_moment:QCLOUD_BXS:QNCLOUD_BXS",
                      result["positive_mass_zero_moment_boundary_pairs"])

    def test_orphan_number_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wrfbdy_d01"
            write_boundary(path, positive_orphan_number=True)
            result = summarize_boundary(path)
        self.assertIn("zero_mass_positive_moment:QCLOUD_BXS:QNCLOUD_BXS",
                      result["positive_mass_zero_moment_boundary_pairs"])

    def test_masked_fill_and_nonfinite_values_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wrfbdy_d01"
            write_boundary(path, masked_cloud=True, nonfinite_number=True)
            result = summarize_boundary(path)
        self.assertIn("masked", result["invalid_values"]["QCLOUD_BXS"])
        self.assertIn("_FillValue", result["invalid_values"]["QCLOUD_BXS"])
        self.assertIn("nonfinite", result["invalid_values"]["QNICE_BXS"])

    def test_finite_negative_tendency_is_not_a_negative_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wrfbdy_d01"
            write_boundary(path, negative_boundary_tendency=True)
            result = summarize_boundary(path)
        self.assertEqual(result["positive_mass_zero_moment_boundary_pairs"], [])
        self.assertEqual(result["invalid_values"], {})


if __name__ == "__main__":
    unittest.main()
