import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from pr74_common_moment_audit import audit_fields


class CommonMomentAuditTest(unittest.TestCase):
    def setUp(self):
        self.shape = (1, 1, 4)
        self.fields = {name: np.zeros(self.shape, dtype=np.float32)
                       for name in ("QR", "NR", "QC", "NC", "QI", "NI", "QG", "BG")}
        self.fields["QR"][0, 0, 0] = 1.0e-30
        self.fields["QC"][0, 0, 1] = 2.0
        self.fields["NC"][0, 0, 1] = 3.0
        self.fields["QI"][0, 0, 2] = -0.5
        self.fields["NI"][0, 0, 2] = 1.0
        self.fields["QG"][0, 0, 3] = 1.0
        self.fields["BG"][0, 0, 3] = 1.0e-20
        self.density = np.full(self.shape, 2.0, dtype=np.float32)
        self.weight = np.full(self.shape, 10.0, dtype=np.float64)
        self.bounds = {"its": 10, "jts": 5, "kts": 2}

    def test_global_classes_conversion_and_first_violation(self):
        report = audit_fields(self.fields, self.density, self.weight, self.bounds)
        self.assertEqual(report["first_violation"], {
            "species": "rain", "state": "mass_only", "i": 10, "j": 5, "k": 2,
            "q_kg_kg": float(np.float32(1.0e-30)), "public_moment": 0.0,
            "internal_moment": 0.0,
        })
        by_species = {row["species"]: row for row in report["species"]}
        self.assertEqual(by_species["rain"]["counts"]["mass_only"], 1)
        self.assertEqual(by_species["cloud"]["values"]["public_moment_basis"],
                         "number_per_kg_dry_air")
        self.assertEqual(by_species["cloud"]["values"]["internal_moment_basis"], "number_per_m3")
        self.assertEqual(by_species["cloud"]["values"]["internal_moment"]["max"], 6.0)
        self.assertEqual(by_species["ice"]["counts"]["negative"], 1)
        self.assertEqual(by_species["graupel"]["counts"]["active"], 1)
        self.assertEqual(report["global_counts"]["mass_only"], 1)
        self.assertEqual(report["global_max_violation"]["largest_mass_only_q_kg_kg"]["value"],
                         float(np.float32(1.0e-30)))
        self.assertEqual(report["global_same_carrier_mass_weighted_scale"]["mass_only"]["absolute_q_dry_air_mass_kg"],
                         float(np.float32(1.0e-30) * 10.0))

    def test_nonfinite_is_counted_and_exact_zero_defines_absent(self):
        self.fields["QR"][0, 0, 1] = np.nan
        report = audit_fields(self.fields, self.density, self.weight, self.bounds)
        by_species = {row["species"]: row for row in report["species"]}
        self.assertEqual(by_species["rain"]["counts"]["nonfinite"], 1)
        self.assertEqual(by_species["rain"]["counts"]["absent"], 2)
        self.assertEqual(report["global_counts"]["invalid"], 2)
        self.assertEqual(report["scope"]["positive_carrier_zero_equivalence"].split(":")[0], "exact")


if __name__ == "__main__":
    unittest.main()
