from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from pr83_same13_native_pair_readback import native_transfer_inventory
from test_native_hybrid_geometry import species_values, write_native_pair


class NativePairReadbackTests(unittest.TestCase):
    def test_native_pair_inventory_reports_xa_minus_xb_water_signs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            xa, xb = root / "xa.nc", root / "xb.nc"
            # Same geometry, with cloud transferred to vapor in Xa.
            write_native_pair(
                xb, xa,
                baseline_species=species_values(vapor=0.015, cloud=0.015),
                candidate_species=species_values(vapor=0.020, cloud=0.010),
            )
            report = native_transfer_inventory(xa, xb)

        self.assertEqual(report["dry_mass_change_kg"], 0.0)
        vapor = report["water_by_species"]["QVAPOR"]
        cloud = report["water_by_species"]["QCLOUD"]
        self.assertGreater(vapor["change_kg"], 0.0)
        self.assertEqual(vapor["composition_change_kg"], vapor["change_kg"])
        self.assertEqual(vapor["mass_metric_change_kg"], 0.0)
        self.assertLess(cloud["change_kg"], 0.0)
        self.assertEqual(cloud["composition_change_kg"], cloud["change_kg"])
        self.assertEqual(cloud["mass_metric_change_kg"], 0.0)
        self.assertEqual(report["field_delta_direction"], "Xa minus Xb")
        self.assertIn("not physical-time closure", report["interpretation"])
        self.assertEqual(report["gravity_assumption_m_s2"], 9.81)


if __name__ == "__main__":
    unittest.main()
