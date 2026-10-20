import unittest
import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools/pr93_qc_chain.py"
SPEC = importlib.util.spec_from_file_location("pr93_qc_chain", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
QC_TABLE = MODULE.QC_TABLE
horizontal_summary = MODULE.horizontal_summary


class HorizontalSummaryTests(unittest.TestCase):
    def test_fixed_support_counts_and_bitwise_matches(self):
        rows = [
            {"target_i0": target % 16, "target_j0": target // 16,
             "pressure_pa": 95_000 - level * 5_000,
             "prediction_hex": "3F800000", "met_em_qc_hex": "3F800000"}
            for target in range(16) for level in range(18)
        ]
        result = horizontal_summary({"comparison_rows": rows,
                                     "inverse_support": {str(i): [] for i in range(9)},
                                     "source_levels_k0": list(range(3, 21))})
        self.assertEqual(result, {
            "source_support_pressure_cells": 162,
            "unique_horizontal_source_cells": 9,
            "target_metgrid_columns": 16,
            "pressure_levels": 18,
            "comparisons": 288,
            "bitwise_matches": 288,
        })

    def test_rejects_mismatch(self):
        rows = [
            {"target_i0": target % 16, "target_j0": target // 16,
             "pressure_pa": 95_000 - level * 5_000,
             "prediction_hex": "00000000", "met_em_qc_hex": "00000000"}
            for target in range(16) for level in range(18)
        ]
        rows[-1]["met_em_qc_hex"] = "3F800000"
        with self.assertRaisesRegex(ValueError, "1 QC mismatches"):
            horizontal_summary({"comparison_rows": rows,
                                "inverse_support": {str(i): [] for i in range(9)},
                                "source_levels_k0": list(range(3, 21))})

    def test_qc_routing_records_no_mask_and_zero_missing_fill(self):
        self.assertEqual(QC_TABLE["interp_option"], "four_pt+average_4pt")
        self.assertEqual(QC_TABLE["fill_missing"], "0.")
        self.assertFalse(QC_TABLE["qc_specific_interpolation_mask"])


if __name__ == "__main__":
    unittest.main()
