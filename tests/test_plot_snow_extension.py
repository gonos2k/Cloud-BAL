"""Unit checks for extension ranking and map selection labels."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
try:
    import plot_snow_extension as plots
finally:
    sys.path.remove(str(ROOT / "tools"))


class SnowExtensionPresentationTests(unittest.TestCase):
    def test_current_hydro_is_context_only_and_not_selectable(self) -> None:
        self.assertNotIn("CURRENT_HYDRO", plots.ELIGIBLE)
        with self.assertRaisesRegex(ValueError, "ineligible or unknown"):
            plots.selected_case({"selected_case": "CURRENT_HYDRO"})

    def test_map_panels_include_reference_both_baselines_and_one_selected_case(self) -> None:
        fields = plots.map_fields("IMPROVED_SNOW_250")
        self.assertEqual(tuple(name for name, _ in fields),
                         ("reference", "ORIGINAL", "IMPROVED_BG_FIXED", "IMPROVED_SNOW_250"))
        self.assertEqual(fields[0][1], "RN1 분석")
        self.assertIn("α=2.5", fields[-1][1])

    def test_fixed_cases_do_not_add_a_duplicate_map_panel(self) -> None:
        fields = plots.map_fields("IMPROVED_BG_FIXED")
        self.assertEqual(len(fields), 3)

    def test_new_case_csi_delta_is_candidate_minus_original(self) -> None:
        selected = 20 / 157
        original = 7 / 142
        difference = plots.delta_csi(selected, original)
        self.assertGreater(difference, 0)
        self.assertAlmostEqual(difference, 0.07809276038395982, places=12)

    def test_ranking_uses_strong_rain_csi_then_frozen_tie_breaks(self) -> None:
        categorical = []
        continuous = []
        for case in plots.ELIGIBLE:
            csi10 = 0.0
            csi5 = 0.0
            far10 = 1.0
            if case == "CONTROL_SNOW_175":
                csi10 = 0.2
            if case == "IMPROVED_SNOW_300":
                csi10 = 0.2
                csi5 = 0.4
            for threshold in plots.THRESHOLDS:
                categorical.append({"lead_hour": "1", "case": case,
                                    "threshold_mm": str(threshold),
                                    "CSI": str(csi10 if threshold == 10.0 else csi5 if threshold == 5.0 else 0.0),
                                    "FAR": str(far10 if threshold == 10.0 else 0.5)})
            continuous.append({"lead_hour": "1", "case": case, "RMSE_mm": "2.0"})
        order = plots.rank_cases(categorical, continuous)
        self.assertEqual(order[0], "IMPROVED_SNOW_300")
        self.assertEqual(order[1], "CONTROL_SNOW_175")

    def test_undefined_primary_csi_ranks_below_a_defined_score(self) -> None:
        categorical = []
        continuous = []
        for case in plots.ELIGIBLE:
            for threshold in plots.THRESHOLDS:
                csi = "None" if case == "ORIGINAL" and threshold == 10.0 else "0.1"
                categorical.append({"lead_hour": "1", "case": case,
                                    "threshold_mm": str(threshold), "CSI": csi, "FAR": "0.2"})
            continuous.append({"lead_hour": "1", "case": case, "RMSE_mm": "1.0"})
        self.assertNotEqual(plots.rank_cases(categorical, continuous)[0], "ORIGINAL")


if __name__ == "__main__":
    unittest.main()
