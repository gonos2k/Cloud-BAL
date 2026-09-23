"""Focused independent checks for the one-column gas mass transform."""

import unittest
from decimal import Decimal, localcontext

import numpy as np

from qbal_dry_mass_column import G0, RD, EPSILON, dry_mass_column, remap_component_masses


class DryMassColumnTests(unittest.TestCase):
    def test_dry_mass_pressure_and_eos(self):
        pressure = np.array([10806.65, 1000.0])
        result = dry_mass_column(pressure, [0.01, 0.01], [0.02, 0.02], [300, 300])
        self.assertAlmostEqual(result['dry_mass'][0], 990.0)
        self.assertAlmostEqual(result['old_vapor'][0], 10.0)
        self.assertAlmostEqual(result['new_vapor'][0], 990.0 * .02 / .98)
        self.assertEqual(result['new_pressure'][-1], 1000.0)
        self.assertAlmostEqual((result['new_pressure'][0] - pressure[0]) / G0,
                               result['new_vapor'][0] - result['old_vapor'][0])
        mixing_ratio = .02 / .98
        virtual_temperature = 300 * (1 + mixing_ratio / EPSILON) / (1 + mixing_ratio)
        expected_height = RD * virtual_temperature / G0 * np.log(
            result['new_pressure'][0] / result['new_pressure'][1])
        self.assertAlmostEqual(result['new_thickness'][0], expected_height)
        midpoint_pressure = np.sqrt(np.prod(result['new_pressure']))
        dry_density = midpoint_pressure / (RD * 300 * (1 + mixing_ratio / EPSILON))
        gas_density = dry_density * (1 + mixing_ratio)
        self.assertAlmostEqual(midpoint_pressure / gas_density, RD * virtual_temperature)

    def test_no_humidity_change_is_identity(self):
        pressure = np.array([100000., 90000., 5000.])
        q = np.array([.01, .012, .003])
        state = dry_mass_column(pressure, q, q, [300., 280., 220.])
        np.testing.assert_allclose(state['new_pressure'], pressure, rtol=0, atol=2e-11)
        np.testing.assert_allclose(state['new_vapor'], state['old_vapor'], rtol=1e-15)
        np.testing.assert_allclose(state['new_thickness'], state['old_thickness'], rtol=1e-15)

    def test_decimal_mass_oracle(self):
        rng = np.random.default_rng(824)
        with localcontext() as context:
            context.prec = 70
            gravity = Decimal(str(G0))
            for _ in range(120):
                widths = rng.uniform(2000, 12000, 4)
                pressure = np.r_[5000 + np.sum(widths), 5000 + np.sum(widths[1:]),
                                 5000 + np.sum(widths[2:]), 5000 + widths[-1], 5000.]
                q0 = rng.uniform(0, .02, 5)
                q1 = rng.uniform(0, .02, 5)
                state = dry_mass_column(pressure, q0, q1, np.full(5, 290.))
                for k in range(4):
                    d = lambda x: Decimal(str(x))
                    q_before = (d(q0[k]) + d(q0[k + 1])) / 2
                    q_after = (d(q1[k]) + d(q1[k + 1])) / 2
                    width = d(pressure[k]) - d(pressure[k + 1])
                    dry = width * (1 - q_before) / gravity
                    vapor = dry * q_after / (1 - q_after)
                    new_width = gravity * (dry + vapor)
                    self.assertAlmostEqual(state['dry_mass'][k], float(dry), places=11)
                    self.assertAlmostEqual(state['new_vapor'][k], float(vapor), places=11)
                    self.assertAlmostEqual(state['new_pressure'][k] - state['new_pressure'][k + 1],
                                           float(new_width), places=9)

    def test_component_remap_split_and_merge(self):
        donor = [100000., 90000., 5000.]
        dry = [900., 7000.]
        vapor = [10., 100.]
        target = [100000., 95000., 80000., 5000.]
        mapped_dry, mapped_vapor = remap_component_masses(donor, dry, vapor, target)
        np.testing.assert_allclose(mapped_dry, [450., 450. + 7000. / 85000. * 10000.,
                                               7000. / 85000. * 75000.])
        np.testing.assert_allclose(mapped_vapor, [5., 5. + 100. / 85000. * 10000.,
                                                 100. / 85000. * 75000.])
        self.assertAlmostEqual(sum(mapped_dry), sum(dry))
        self.assertAlmostEqual(sum(mapped_vapor), sum(vapor))
        same_dry, same_vapor = remap_component_masses(donor, dry, vapor, donor)
        np.testing.assert_array_equal(same_dry, dry)
        np.testing.assert_array_equal(same_vapor, vapor)
        with self.assertRaises(ValueError):
            remap_component_masses(donor, dry, vapor, [99000., 90000., 5000.])
        with np.errstate(over='ignore'):
            with self.assertRaises(ValueError):
                remap_component_masses(donor, [1e308, 1e308], vapor,
                                       [100000., 5000.])

    def test_bad_state_rejected(self):
        cases = [
            ([100000, 5000], [0, np.nan], [0, 0], [300, 300]),
            ([100000, 5000], [0, 0], [0, 1], [300, 300]),
            ([5000, 100000], [0, 0], [0, 0], [300, 300]),
            ([100000, 5000], [0, 0], [0, 0], [300, np.inf]),
            ([100000, 5000], [0, 0], [0, 0], [300]),
        ]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                dry_mass_column(*case)


if __name__ == '__main__':
    unittest.main()
