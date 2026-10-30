"""Unit checks for fine-sensitivity ranking and map selection labels."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
try:
    import plot_snow_fine as plots
finally:
    sys.path.remove(str(ROOT / "tools"))


class SnowFinePresentationTests(unittest.TestCase):
    def test_current_hydro_is_context_only_and_not_selectable(self) -> None:
        self.assertNotIn("CURRENT_HYDRO", plots.ELIGIBLE)
        with self.assertRaisesRegex(ValueError, "ineligible or unknown"):
            plots.selected_case({"selected_case": "CURRENT_HYDRO"})

    def test_map_panels_pair_reference_with_each_experiment(self) -> None:
        fields = plots.map_fields("IMPROVED_SNOW_250")
        self.assertEqual(tuple(name for name, _ in fields),
                         ("reference", "IMPROVED_SNOW_250"))
        self.assertEqual(fields[0][1], "RN1 분석")
        self.assertIn("α=2.5", fields[-1][1])

    def test_every_experiment_uses_a_two_panel_map(self) -> None:
        fields = plots.map_fields("IMPROVED_BG_FIXED")
        self.assertEqual(fields, (("reference", "RN1 분석"),
                                  ("IMPROVED_BG_FIXED", "기존 개선안 B1")))

    def test_plot_groups_cover_all_31_experiments(self) -> None:
        groups = plots.case_groups(tuple(plots.ALL_CASES))
        self.assertEqual([name for name, _ in groups], ["control", "improved", "context"])
        self.assertEqual([len(group) for _, group in groups], [15, 15, 1])
        self.assertEqual(len({case for _, group in groups for case in group}), 31)
        self.assertEqual(groups[0][1][0], "ORIGINAL")
        self.assertEqual(groups[1][1][0], "IMPROVED_BG_FIXED")
        self.assertEqual([int(case.rsplit("_", 1)[-1]) for case in groups[0][1][1:]],
                         sorted(int(case.rsplit("_", 1)[-1]) for case in groups[0][1][1:]))
        score_keys, map_keys = plots.expected_coverage(tuple(plots.ALL_CASES))
        self.assertEqual(len(score_keys), 31 * 6 * 6)
        self.assertEqual(len(map_keys), 31 * 6)

    def test_figure_manifest_requires_full_heatmap_and_map_coverage(self) -> None:
        cases = tuple(plots.ALL_CASES)
        groups = plots.case_groups(cases)
        limits = [-0.4, 0.4]
        bins = list(plots.PRECIPITATION_LEVELS)
        heatmaps = {}
        for threshold in plots.THRESHOLDS:
            for name, group in groups:
                path = f"delta_csi/{name}/delta_csi_t{plots.threshold_slug(threshold)}.png"
                heatmaps[path] = {
                    "threshold_mm": threshold, "group": name, "cases": list(group),
                    "lead_hours": list(plots.LEADS),
                    "delta_definition": "CSI(experiment) - CSI(ORIGINAL)",
                    "color_limits": limits,
                }
        maps = {
            case: {"figure": f"hourly_maps/test/hourly_total_precip_{case}.png",
                   "lead_hours": list(plots.LEADS), "panels_per_lead": ["reference", case],
                   "precipitation_bins_mm": bins}
            for case in cases
        }
        figure_hashes = {}
        for png in (*heatmaps, *(item["figure"] for item in maps.values())):
            for suffix in ("png", "pdf", "svg"):
                figure_hashes[png[:-4] + "." + suffix] = "0" * 64
        manifest = {
            "selected_case": "ORIGINAL", "context_only_cases": ["CURRENT_HYDRO"],
            "delta_csi_heatmaps": heatmaps, "hourly_precipitation_maps": maps,
            "heatmap_coverage": {
                "cases_per_page_groups": {name: list(group) for name, group in groups},
                "cases": list(cases), "lead_hours": list(plots.LEADS),
                "thresholds_mm": list(plots.THRESHOLDS),
                "delta_cell_count": 31 * 6 * 6, "shared_color_limits": limits,
            },
            "map_coverage": {"cases": list(cases), "lead_hours": list(plots.LEADS),
                             "case_lead_count": 31 * 6,
                             "common_precipitation_bins_mm": bins},
            "figure_sha256": figure_hashes,
        }
        plots.validate_figure_coverage(manifest, cases, "ORIGINAL")
        del manifest["delta_csi_heatmaps"][next(iter(heatmaps))]
        with self.assertRaisesRegex(ValueError, "full symmetric CSI and hourly-map grids"):
            plots.validate_figure_coverage(manifest, cases, "ORIGINAL")

    def test_new_case_csi_delta_is_candidate_minus_original(self) -> None:
        selected = 20 / 157
        original = 7 / 142
        difference = plots.delta_csi(selected, original)
        self.assertGreater(difference, 0)
        self.assertAlmostEqual(difference, 0.07809276038395982, places=12)

    def test_fine_cases_cover_both_families_and_four_factors(self) -> None:
        self.assertEqual(plots.NEW_CASES, (
            "CONTROL_SNOW_110", "CONTROL_SNOW_120", "CONTROL_SNOW_130", "CONTROL_SNOW_140",
            "IMPROVED_SNOW_110", "IMPROVED_SNOW_120", "IMPROVED_SNOW_130", "IMPROVED_SNOW_140"))
        self.assertEqual(len(plots.ALL_CASES), 31)
        self.assertEqual(len(plots.ELIGIBLE), 30)

    def test_ranking_uses_strong_rain_csi_then_frozen_tie_breaks(self) -> None:
        categorical = []
        continuous = []
        for case in plots.ELIGIBLE:
            csi10 = 0.0
            csi5 = 0.0
            far10 = 1.0
            if case == "CONTROL_SNOW_130":
                csi10 = 0.2
            if case == "IMPROVED_SNOW_140":
                csi10 = 0.2
                csi5 = 0.4
            for threshold in plots.THRESHOLDS:
                categorical.append({"lead_hour": "1", "case": case,
                                    "threshold_mm": str(threshold),
                                    "CSI": str(csi10 if threshold == 10.0 else csi5 if threshold == 5.0 else 0.0),
                                    "FAR": str(far10 if threshold == 10.0 else 0.5)})
            continuous.append({"lead_hour": "1", "case": case, "RMSE_mm": "2.0"})
        order = plots.rank_cases(categorical, continuous)
        self.assertEqual(order[0], "IMPROVED_SNOW_140")
        self.assertEqual(order[1], "CONTROL_SNOW_130")

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
