"""Focused checks for the supported surface strip and moved pressure cells."""

import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from qbal_dry_mass_column import G0, dry_mass_column
from qbal_surface_mass_bridge import (common_pressure_projection,
                                      fixed_ps_gap_requirement, gas_enthalpy,
                                      surface_support)
from diagnose_qbal_surface_mass_bridge import (read_pinned_json, state_from_receipt,
                                               verify_input_hashes)


class SurfaceMassBridgeTests(unittest.TestCase):
    def test_surface_prior_stops_at_10_m(self):
        support = surface_support(100500, 100400, 100000, 100100, 0.02)
        self.assertEqual(support['old']['supported_span_Pa'], 100)
        self.assertEqual(support['old']['unsupported_span_Pa'], 400)
        self.assertEqual(support['new_if_PS_fixed']['unsupported_span_Pa'], 300)
        self.assertAlmostEqual(sum(support['old'][name] for name in
                                   ('supported_dry_mass_kg_m2',
                                    'supported_vapor_mass_kg_m2')), 100 / G0)
        self.assertAlmostEqual(support['old']['supported_vapor_mass_kg_m2'] /
                               support['old']['supported_dry_mass_kg_m2'], 0.02)

    def test_supported_partial_without_gap(self):
        support = surface_support(100500, 100400, 100450, 100470, 0.01)
        self.assertEqual(support['old']['unsupported_span_Pa'], 0)
        self.assertEqual(support['old']['supported_span_Pa'], 50)
        self.assertEqual(support['new_if_PS_fixed']['supported_span_Pa'], 30)

    def test_fixed_ps_gap_requirement_is_only_a_bound(self):
        result = fixed_ps_gap_requirement(40, 30, 10)
        self.assertEqual(result['minimum_initial_gap_vapor_mass_kg_m2'], 10)
        self.assertEqual(result['minimum_initial_gap_q_kg_kg'], 0.25)
        with self.assertRaises(ValueError):
            fixed_ps_gap_requirement(40, 30, 9)

    def test_moved_edge_is_kept_and_enthalpy_repartitions(self):
        state = dry_mass_column([100000, 95000, 5000],
                                [0.01, 0.01, 0.01],
                                [0.02, 0.02, 0.02],
                                [300, 300, 260])
        projected = common_pressure_projection(state)
        edge_width = state['new_pressure'][0] - state['old_pressure'][0]
        first_width = state['new_pressure'][0] - state['new_pressure'][1]
        fraction = edge_width / first_width
        self.assertAlmostEqual(projected['edge_dry_mass_kg_m2'],
                               fraction * state['dry_mass'][0])
        self.assertAlmostEqual(projected['edge_vapor_mass_kg_m2'],
                               fraction * state['new_vapor'][0])
        for component, edge, common in (
                (state['dry_mass'], projected['edge_dry_mass_kg_m2'],
                 projected['old_pressure_cell_dry_mass_kg_m2']),
                (state['new_vapor'], projected['edge_vapor_mass_kg_m2'],
                 projected['old_pressure_cell_vapor_mass_kg_m2'])):
            self.assertAlmostEqual(np.sum(component), edge + np.sum(common), places=10)
        expected = sum(gas_enthalpy(state['dry_mass'], state['new_vapor'],
                                    state['layer_temperature_K']))
        self.assertAlmostEqual(projected['total_enthalpy_J_m2'], expected, places=7)
        np.testing.assert_allclose(gas_enthalpy(
            projected['old_pressure_cell_dry_mass_kg_m2'],
            projected['old_pressure_cell_vapor_mass_kg_m2'],
            projected['old_pressure_cell_temperature_K']),
            projected['old_pressure_cell_enthalpy_J_m2'], rtol=2e-14, atol=1e-8)
        self.assertAlmostEqual(sum(projected['old_pressure_cell_dry_mass_kg_m2'] +
                                   projected['old_pressure_cell_vapor_mass_kg_m2']),
                               95000 / G0, places=10)

    def test_identity_and_unsupported_inputs(self):
        state = dry_mass_column([100000, 90000, 5000],
                                [0.01, 0.01, 0.01],
                                [0.01, 0.01, 0.01],
                                [300, 290, 220])
        projected = common_pressure_projection(state)
        self.assertEqual(projected['edge_dry_mass_kg_m2'], 0)
        np.testing.assert_allclose(projected['old_pressure_cell_q_kg_kg'], state['new_q'])
        np.testing.assert_allclose(projected['old_pressure_cell_temperature_K'],
                                   state['layer_temperature_K'], atol=1e-12)
        state['new_pressure'][0] = 99000
        with self.assertRaises(ValueError):
            common_pressure_projection(state)
        with self.assertRaises(ValueError):
            surface_support(100000, float('nan'), 99000, 99500, 0.01)
        drying = dry_mass_column([100000, 90000, 5000],
                                 [0.02, 0.02, 0.02],
                                 [0.01, 0.01, 0.01],
                                 [300, 290, 220])
        with self.assertRaises(ValueError):
            common_pressure_projection(drying)

    def test_changed_receipt_vapor_mass_is_rejected(self):
        path = Path(__file__).resolve().parents[1] / 'docs/evidence/pr47_dry_mass_column.json'
        receipt = json.loads(path.read_text())
        receipt['layers'][0]['old_vapor_kg_m2'] += 1
        with self.assertRaises(ValueError):
            state_from_receipt(receipt)

    def test_receipt_change_after_read_is_rejected(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'receipt.json'
            path.write_text('{"temperature": 300}')
            loaded, digest = read_pinned_json(path)
            path.write_text('{"temperature": 303}')
            self.assertEqual(loaded['temperature'], 300)
            with self.assertRaisesRegex(ValueError, 'input changed during calculation'):
                verify_input_hashes({'dry_report': (path, digest)})


if __name__ == '__main__':
    unittest.main()
