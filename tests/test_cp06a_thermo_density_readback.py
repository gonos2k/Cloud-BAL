import importlib.util
from pathlib import Path
import tempfile
import unittest

import numpy as np
from netCDF4 import Dataset


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools/cp06a_thermo_density_readback.py"
SPEC = importlib.util.spec_from_file_location("cp06a_thermo_density_readback", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def make_state(path: Path) -> None:
    shape = (2, 1, 1)
    with Dataset(path, "w") as ds:
        for name, size in (("z", 2), ("y", 1), ("x", 1), ("analysis_cell", 2),
                           ("condensate_species", 5)):
            ds.createDimension(name, size)
        pressure = np.array([85000.0, 70000.0])
        ds.createVariable("pressure", "f8", ("z",))[:] = pressure
        values = {
            "background_temperature": np.full(shape, 290.0),
            "background_vapor": np.full(shape, 0.010),
            "thermo_preprior_temperature": np.full(shape, 280.0),
            "thermo_preprior_vapor": np.full(shape, 0.008),
            "analysis_support": np.ones(shape, dtype=np.int32),
            "thermo_support": np.array([[[1]], [[0]]], dtype=np.int32),
            "thermo_surface": np.array([[[MODULE.LIQUID]], [[0]]], dtype=np.int32),
        }
        for species in ("cloud_water", "cloud_ice", "rain", "snow", "graupel"):
            values[f"background_{species}"] = np.full(shape, 0.001)
            values[f"candidate_{species}"] = np.full(shape, 0.002)
        for name, value in values.items():
            ds.createVariable(name, "i4" if value.dtype.kind in "iu" else "f8",
                              ("z", "y", "x"))[:] = value
        ds.createVariable("thermo_preprior_condensates", "f8",
                          ("analysis_cell", "condensate_species"))[:] = 0.002
        ds.createVariable("thermo_preprior_dry_air_mass_measure", "f8", ("analysis_cell",))[:] = 95.0
        ds.createVariable("candidate_dry_air_mass_measure", "f8", ("z", "y", "x"))[:] = 95.0
        ds.thermo_target_rh = 1.0


class ThermodynamicDensityReadbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "state.nc"
        make_state(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_equal_alpha_blend_has_saturated_and_fixed_vapor_roots(self):
        with Dataset(self.path) as ds:
            result = MODULE.expected_thermodynamics(ds, 0.5)
            condensates = tuple(MODULE.get(ds, f"candidate_{name}")
                                for name in ("cloud_water", "cloud_ice", "rain", "snow", "graupel"))
            actual_alpha = MODULE.alpha(result["expected_temperature"],
                                        result["expected_vapor"], condensates)
            np.testing.assert_allclose(actual_alpha, result["alpha_target"], rtol=2e-14, atol=1e-9)
            self.assertAlmostEqual(
                result["expected_vapor"][0, 0, 0],
                MODULE.saturation_mixing_ratio(result["expected_temperature"][0, 0, 0],
                                               85000.0, MODULE.LIQUID), places=13)
            self.assertEqual(result["expected_vapor"][1, 0, 0], 0.008)
            self.assertNotEqual(result["expected_temperature"][1, 0, 0], 280.0)

    def test_impossible_saturated_target_rejects(self):
        with self.assertRaisesRegex(ValueError, "no saturated root"):
            MODULE.saturated_alpha_root(85000.0, 1.0e6, 0.01, MODULE.LIQUID, 1.0)

    def test_empty_reservoir_retains_vapor_when_fixed_vapor_solution_is_subsaturated(self):
        with Dataset(self.path, "a") as ds:
            ds.variables["thermo_support"][:] = 1
            ds.variables["thermo_surface"][1, 0, 0] = MODULE.LIQUID
            ds.variables["candidate_cloud_water"][1, 0, 0] = 0.0
            ds.variables["thermo_preprior_condensates"][1, 0] = 0.0
            result = MODULE.expected_thermodynamics(ds, 0.5)
            t = result["expected_temperature"][1, 0, 0]
            qv = result["expected_vapor"][1, 0, 0]
            self.assertEqual(ds.variables["candidate_cloud_water"][1, 0, 0], 0.0)
            self.assertEqual(qv, ds.variables["thermo_preprior_vapor"][1, 0, 0])
            self.assertLessEqual(qv, MODULE.saturation_mixing_ratio(t, 70000.0, MODULE.LIQUID))

    def test_empty_reservoir_binds_supersaturation_inequality(self):
        with Dataset(self.path, "a") as ds:
            ds.variables["thermo_support"][:] = 1
            ds.variables["thermo_surface"][1, 0, 0] = MODULE.LIQUID
            ds.variables["candidate_cloud_water"][1, 0, 0] = 0.0
            ds.variables["thermo_preprior_condensates"][1, 0] = 0.0
            ds.variables["thermo_preprior_vapor"][1, 0, 0] = 0.03
            result = MODULE.expected_thermodynamics(ds, 0.5)
            t = result["expected_temperature"][1, 0, 0]
            qv = result["expected_vapor"][1, 0, 0]
            self.assertEqual(ds.variables["candidate_cloud_water"][1, 0, 0], 0.0)
            self.assertAlmostEqual(qv, MODULE.saturation_mixing_ratio(t, 70000.0, MODULE.LIQUID), places=12)
            self.assertNotEqual(qv, ds.variables["thermo_preprior_vapor"][1, 0, 0])

    def test_analysis_budget_closes_fixed_pressure_mass_identity(self):
        shape = (2, 1, 1)
        pre_t = np.full(shape, 280.0)
        pre_q = np.full(shape, 0.008)
        final_t = np.array([[[278.0]], [[280.0]]])
        final_q = np.array([[[0.009]], [[0.008]]])
        condensates_before = tuple(np.full(shape, 0.002) for _ in range(5))
        condensates_after = tuple(np.full(shape, 0.002) for _ in range(5))
        pressure_mass = 100.0
        pre_dry_mass = np.full(shape, pressure_mass / (1.0 + 0.008 + 5.0 * 0.002))
        final_dry_mass = pre_dry_mass.copy()
        pre_dry_mass[0, 0, 0] = pressure_mass / (1.0 + 0.008 + 5.0 * 0.002)
        final_dry_mass[0, 0, 0] = pressure_mass / (1.0 + 0.009 + 5.0 * 0.002)
        support = np.array([[[True]], [[False]]])
        valid = tuple(np.ones(shape, dtype=np.int32) for _ in range(6))
        budget = MODULE.endpoint_budget(pre_t, pre_q, final_t, final_q,
                                        condensates_before, condensates_after,
                                        pre_dry_mass, final_dry_mass, support,
                                        np.ones(shape, dtype=bool), candidate_valid=valid)
        self.assertLess(abs(budget["total_mass_error_kg"]), 1e-12)
        self.assertLess(abs(budget["enthalpy_split_error_j"]), 1e-8)
        self.assertEqual(len(budget["species_arithmetic_scale_kg"]), 6)
        self.assertEqual(budget["support_cells"], 1)
        self.assertEqual(budget["accounted_cells"], 2)
        # The unsupported cell is still an above-ground Fortran budget cell:
        # its unchanged finite state contributes nonzero arithmetic scale.
        outside_dry_mass = pressure_mass / (1.0 + 0.008 + 5.0 * 0.002)
        before_cell_mass = pressure_mass / (1.0 + 0.008 + 5.0 * 0.002)
        after_cell_mass = pressure_mass / (1.0 + 0.009 + 5.0 * 0.002)
        change = after_cell_mass - before_cell_mass
        vapor_scale = (2.0 * outside_dry_mass * 0.008 + after_cell_mass * 0.009 +
                       before_cell_mass * 0.008 + before_cell_mass * 0.001 + abs(change * 0.009))
        self.assertAlmostEqual(budget["species_arithmetic_scale_kg"][0], vapor_scale)
        for scale in budget["species_arithmetic_scale_kg"][1:]:
            condensate_scale = (2.0 * outside_dry_mass * 0.002 + after_cell_mass * 0.002 +
                                before_cell_mass * 0.002 + abs(change * 0.002))
            self.assertAlmostEqual(scale, condensate_scale)


if __name__ == "__main__":
    unittest.main()
