import unittest
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from pr84_ice_cap_pair_audit import (
    CAP_KG_M3,
    carrier_weighted_excess,
    cap_violation_mask,
    checked_field,
    interior_mask,
    source_density,
    validate_pair_metadata,
)


class Field:
    def __init__(self, value, fill=None):
        self.value = value
        if fill is not None:
            self._FillValue = fill

    def __getitem__(self, _):
        return self.value


class IceCapAuditTests(unittest.TestCase):
    def test_checked_field_rejects_mask_fill_and_nan(self):
        with self.assertRaisesRegex(ValueError, "masked/fill"):
            checked_field(Field(np.ma.array([1.0, 2.0], mask=[False, True])), "x")
        with self.assertRaisesRegex(ValueError, "_FillValue"):
            checked_field(Field(np.array([1.0, -9999.0]), -9999.0), "x")
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            checked_field(Field(np.array([1.0, np.nan])), "x")

    def test_source_density_preserves_real32_operation_order(self):
        al = np.array([0.1], dtype=np.float32)
        alb = np.array([0.2], dtype=np.float32)
        expected_alt = np.add(al, alb, dtype=np.float32)
        expected = np.reciprocal(expected_alt, dtype=np.float32).astype(np.float64)
        self.assertTrue(np.array_equal(source_density(al, alb), expected))

    def test_pairing_requires_same_time_grid_coordinates_and_staggers(self):
        common = {"valid_time": "13:00", "qi": np.zeros((2, 3, 4)),
                  "fields": {"XLAT": np.zeros((3, 4)), "XLONG": np.ones((3, 4))},
                  "staggers": {"bottom_top_stag": 3},
                  "stagger_coordinates": {"XLAT_U": np.zeros((3, 5))}}
        validate_pair_metadata(common, common)
        for key, value in (("valid_time", "14:00"), ("qi", np.zeros((2, 2, 4))),
                           ("staggers", {"bottom_top_stag": 4})):
            right = dict(common, **{key: value})
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_pair_metadata(common, right)
        right = dict(common, fields={"XLAT": np.ones((3, 4)), "XLONG": np.ones((3, 4))})
        with self.assertRaisesRegex(ValueError, "XLAT"):
            validate_pair_metadata(common, right)
        right = dict(common, stagger_coordinates={"XLAT_U": np.ones((3, 5))})
        with self.assertRaisesRegex(ValueError, "XLAT_U"):
            validate_pair_metadata(common, right)

    def test_excess_is_weighted_by_native_dry_carrier_mass(self):
        qi = np.array([0.0, 2.0 * CAP_KG_M3])
        rho = np.array([1.0, 2.0])
        dry_mass = np.array([10.0, 3.0])
        expected = (qi[1] - CAP_KG_M3 / rho[1]) * dry_mass[1]
        self.assertAlmostEqual(carrier_weighted_excess(qi, rho, dry_mass), expected)
        with self.assertRaisesRegex(ValueError, "shapes differ"):
            carrier_weighted_excess(qi, rho[:1], dry_mass)

    def test_cap_boundary_is_strict_and_interior_excludes_outer_ring(self):
        density = np.ones((1, 3, 4), dtype=np.float64)
        qi = np.full_like(density, CAP_KG_M3)
        qi[0, 1, 2] = np.nextafter(CAP_KG_M3, np.inf)
        violation = cap_violation_mask(qi, density)
        self.assertEqual(np.count_nonzero(violation), 1)
        interior = interior_mask(qi.shape)
        self.assertFalse(interior[0, 0, 1])
        self.assertTrue(interior[0, 1, 2])
        self.assertEqual(np.count_nonzero(violation & interior), 1)


if __name__ == "__main__":
    unittest.main()
