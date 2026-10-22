from pathlib import Path
import json
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import pr94_cloud_response as cloud  # noqa: E402
from pr99_cutoff_inventory import (SPECIES, region_summary, validate_pre_call_fields,
                                   weighted_removal)  # noqa: E402


class CutoffInventoryTest(unittest.TestCase):
    def test_source_composition_masks_have_fixed_support_and_buffer_sizes(self):
        path = ROOT / "docs/evidence/pr93_qc_chain_20261020/qc_vertical_composition.json"
        composition = json.loads(path.read_text())["composed_qc_vertical_influence"]
        masks = cloud.make_masks(composition, (39, 280, 232))
        support = masks["original_613_native_support"]
        buffer = masks["fixed_5_cell_chebyshev_buffer"]
        self.assertEqual(int(support.sum()), 613)
        self.assertEqual(int(support.any(axis=0).sum()), 16)
        self.assertEqual(int(buffer.any(axis=0).sum()), 196)
        self.assertTrue(np.all(buffer == buffer[0:1]))

    def test_weighted_region_summary_uses_per_level_inventory_and_distinct_counts(self):
        inventory = np.zeros((len(SPECIES), 2, 1, 2), dtype=np.float64)
        inventory[0] = [[[2.0, 4.0]], [[6.0, 8.0]]]
        removed = np.zeros_like(inventory)
        removed[0] = [[[0.5, 0.0]], [[1.5, 0.0]]]
        events = np.zeros_like(inventory, dtype=np.int32)
        events[0] = [[[1, 0]], [[2, 0]]]
        any_events = events.any(axis=0)
        event_max = removed.copy()
        region = np.array([[[True, False]], [[True, True]]])
        result = region_summary(inventory, removed, events, any_events, region, event_max)
        self.assertEqual(result["selected_native_cells"], 3)
        self.assertEqual(result["removed_by_species_kg"]["QC"], 2.0)
        self.assertEqual(result["pre_call_inventory_by_species_kg"]["QC"], 16.0)
        self.assertEqual(result["removed_to_pre_inventory_ratio_by_species"]["QC"], 0.125)
        self.assertEqual(result["cutoff_event_rows_by_species"]["QC"], 3)
        self.assertEqual(result["distinct_cutoff_cells_by_species"]["QC"], 2)
        self.assertIsNone(result["removed_to_pre_inventory_ratio_by_species"]["QI"])

    def test_cutoff_event_uses_its_actual_level_weight(self):
        # Two species events at different k levels have distinct DEN*DELZ.
        # Reusing the first level's weight would produce 4 kg rather than 10 kg.
        level0 = weighted_removal(0.5, 0.0, 2.0)
        level1 = weighted_removal(1.5, 0.0, 6.0)
        self.assertEqual(level0, 1.0)
        self.assertEqual(level1, 9.0)
        self.assertEqual(level0 + level1, 10.0)

    def test_all_active_geometry_and_inventory_values_are_validated(self):
        density = np.ones((2, 1, 2), dtype=np.float64)
        thickness = np.full_like(density, 2.0)
        condensates = {name: np.zeros_like(density) for name in SPECIES}
        validate_pre_call_fields(density, thickness, condensates)

        bad_cases = (
            (np.array([[[1.0, np.nan]], [[1.0, 1.0]]]), thickness, condensates,
             "DEN"),
            (density, np.array([[[2.0, -1.0]], [[2.0, 2.0]]]), condensates,
             "DELZ"),
            (density, thickness, {**condensates, "QG": np.array([[[0.0, np.inf]], [[0.0, 0.0]]])},
             "QG"),
            (density, thickness, {**condensates, "QI": np.array([[[0.0, -0.1]], [[0.0, 0.0]]])},
             "QI"),
        )
        for bad_density, bad_thickness, bad_condensates, field in bad_cases:
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, field):
                validate_pre_call_fields(bad_density, bad_thickness, bad_condensates)


if __name__ == "__main__":
    unittest.main()
