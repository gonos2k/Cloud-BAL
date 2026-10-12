"""Check independent CCN and prioritized conversion diagnostics on captured fields."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pr82_native_conversion_scale as scale


class ConversionScaleTests(unittest.TestCase):
    def summarize(self, density, cloud_number):
        density = np.asarray(density, dtype=np.float32).reshape(1, 1, -1)
        zero = np.zeros_like(density)
        fields = {"DEN": density, "Q": zero,
                  "NC": np.asarray(cloud_number, dtype=np.float32).reshape(density.shape),
                  "NI": zero, "NR": zero, "NN": np.full_like(density, 1e9),
                  "QC": zero, "QI": zero, "QR": zero}
        # No snow field is supplied: ambient CCN has no condensate counterpart.
        dump = {"fields": fields, "stage": 1, "itimestep": 1, "bounds": {}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.raw"
            path.write_bytes(b"immutable synthetic trace")
            with patch.object(scale, "read_dump", return_value=dump):
                return scale.summarize(path)["species"]

    def test_ambient_ccn_is_valid_without_any_condensate(self):
        species = self.summarize([1, 1, 1], [0, 0, 0])
        self.assertEqual(species["NN"]["public_number_positive"], 3)
        self.assertEqual(sum(species["NN"]["conversion_error_class_counts"].values()), 0)
        self.assertIsNone(species["NN"]["mass_pair"])
        self.assertNotIn("positive_number_zero_mass", species["NN"])
        for name in ("NC", "NI", "NR"):
            self.assertEqual(species[name]["positive_number_zero_mass"], 0)

    def test_invalid_density_precedes_negative_number_and_underflow_is_separate(self):
        minimum = np.nextafter(np.float32(0), np.float32(1))
        counts = self.summarize([np.nan, 0.44613719, 1, 1], [-1, minimum, -1, 0])[
            "NC"]["conversion_error_class_counts"]
        self.assertEqual(counts["NONFINITE_DENSITY"], 1)
        self.assertEqual(counts["NEGATIVE_INPUT"], 1)
        self.assertEqual(counts["POSITIVE_TO_ZERO"], 1)
        self.assertEqual(sum(counts.values()), 3)


if __name__ == "__main__":
    unittest.main()
