"""Independent arithmetic/coordinate guards for first-call accounting."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from pr86_water_budget import cell_slot, weighted_change


class WaterAccountingTest(unittest.TestCase):
    def test_nonunit_global_coordinates(self):
        bounds = dict(its=100, ite=102, jts=50, jte=51, kts=7, kte=10)
        self.assertEqual(cell_slot(bounds, 102, 51, 8), (1, 1, 2))
        for xyz in ((99, 50, 7), (100, 52, 7), (100, 50, 11)):
            with self.assertRaises(ValueError):
                cell_slot(bounds, *xyz)

    def test_promote_snapshots_before_subtraction(self):
        # Direct REAL32 subtraction loses the small addend at this separation.
        before = np.array([2**25, 1], dtype=np.float32)
        after = np.array([1, 2**25], dtype=np.float32)
        weights = np.array([3.0, 1.0])
        self.assertEqual(weighted_change(before, after, weights), -2 * (2**25 - 1))
        self.assertNotEqual(weighted_change(before, after, weights),
                            float(np.sum((after - before).astype(float) * weights)))

    def test_internal_transfer_cancels_and_external_sink_does_not(self):
        mass = np.array([2., 7.])
        donor = np.array([0.5, 0.25])
        receiver = np.zeros(2)
        transfer = np.array([0.125, 0.0625])
        self.assertEqual(weighted_change(donor, donor - transfer, mass) +
                         weighted_change(receiver, receiver + transfer, mass), 0)
        self.assertEqual(weighted_change(donor, donor - transfer, mass), -0.6875)

    def test_nonfinite_or_nonpositive_measure_fails(self):
        for weights in (np.array([0.]), np.array([-1.]), np.array([np.nan])):
            with self.assertRaises(ValueError):
                weighted_change(np.array([1.]), np.array([0.]), weights)


if __name__ == "__main__":
    unittest.main()
