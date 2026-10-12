import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pr82_observation_signal_readback as pr82


class ObservationSignalReadbackTests(unittest.TestCase):
    class ArrayDataset:
        def __init__(self, **values):
            self.variables = {name: self.ArrayVariable(value) for name, value in values.items()}

        class ArrayVariable:
            def __init__(self, value):
                self.value = value
                self.units = ""

            def __getitem__(self, _key):
                return self.value

    def test_direct_lwc_operator_matches_source_density_conversion(self):
        pressure = np.array([100_000.0])
        temperature = np.array([280.0])
        vapor = np.array([0.004])
        cloud_water = np.array([1.2e-4])

        rho_d = pr82.dry_air_density(pressure, temperature, vapor)
        raw_lwc = rho_d * cloud_water

        expected_density = 100_000.0 / (287.05 * 280.0 * (1.0 + 0.004 / 0.622))
        self.assertTrue(np.isclose(rho_d[0], expected_density, rtol=1e-14))
        self.assertTrue(np.isclose(raw_lwc[0], expected_density * 1.2e-4, rtol=1e-14))

    def test_residual_summary_uses_only_the_frozen_mask_and_raw_units(self):
        residual = np.array([0.0, -2.0, 99.0, 101.0])
        footprint = np.array([True, True, False, False])

        result = pr82.residual_summary(residual, footprint)

        self.assertEqual(result["count"], 2)
        self.assertEqual(result["bias"], -1.0)
        self.assertEqual(result["mae"], 1.0)
        self.assertTrue(np.isclose(result["rmse"], np.sqrt(2.0)))
        self.assertEqual(result["max_abs"], 2.0)
        self.assertEqual(result["p95_abs"], 1.9)

    def test_invalid_modeled_cell_is_rejected_before_density(self):
        above_ground = np.array([[[True, True]]])
        pressure = np.array([[[100_000.0, 100_000.0]]])
        temperature = np.array([[[280.0, 280.0]]])
        vapor = np.array([[[0.004, 0.004]]])
        dry_mass = np.array([[[1.0, 1.0]]])
        base_condensates = {name: np.zeros_like(pressure) for name in pr82.SPECIES}
        invalid_cases = (
            ("pressure", pressure, 0.0, "pressure must be positive"),
            ("temperature", temperature, np.nan, "temperature is non-finite"),
            ("vapor", vapor, -1e-8, "vapor must be nonnegative"),
            ("dry_mass", dry_mass, 0.0, "dry_air_mass_measure must be positive"),
        )
        for field_name, field, invalid_value, expected_error in invalid_cases:
            with self.subTest(field=field_name):
                field[0, 0, 1] = invalid_value
                with self.assertRaisesRegex(ValueError, expected_error):
                    pr82.validate_state_fields("injected", pressure, temperature,
                                               vapor, base_condensates, dry_mass,
                                               above_ground)
                field[0, 0, 1] = {"pressure": 100_000.0, "temperature": 280.0,
                                  "vapor": 0.004, "dry_mass": 1.0}[field_name]

        for species in pr82.SPECIES:
            condensates = {name: value.copy() for name, value in base_condensates.items()}
            condensates[species][0, 0, 1] = -1e-8
            with self.subTest(species=species):
                with self.assertRaisesRegex(ValueError, f"{species} must be nonnegative"):
                    pr82.validate_state_fields("injected", pressure, temperature,
                                               vapor, condensates, dry_mass,
                                               above_ground)

        with self.assertRaisesRegex(ValueError, "finite and physical before EOS"):
            pr82.dry_air_density(np.array([0.0]), np.array([280.0]), np.array([0.004]))

    def test_below_ground_missing_state_values_are_allowed(self):
        above_ground = np.array([[[True, False]]])
        pressure = np.array([[[100_000.0, np.nan]]])
        temperature = np.array([[[280.0, np.nan]]])
        vapor = np.array([[[0.004, np.nan]]])
        dry_mass = np.array([[[1.0, np.nan]]])
        condensates = {name: np.array([[[0.0, np.nan]]]) for name in pr82.SPECIES}

        pr82.validate_state_fields("below-ground-missing", pressure, temperature,
                                   vapor, condensates, dry_mass, above_ground)

    def test_binary_masks_reject_nonbinary_nonfinite_and_fill_values(self):
        for malformed in (np.array([0, 2]), np.array([0.0, np.nan])):
            with self.subTest(malformed=malformed):
                dataset = self.ArrayDataset(mask=malformed)
                with self.assertRaisesRegex(ValueError, "finite binary 0/1"):
                    pr82.read_binary_mask(dataset, "mask")

        masked = np.ma.array([0, 1], mask=[False, True])
        dataset = self.ArrayDataset(mask=masked)
        with self.assertRaisesRegex(ValueError, "masked/fill"):
            pr82.read_binary_mask(dataset, "mask")

        dataset = self.ArrayDataset(mask=np.array([0, 1], dtype=np.int8))
        np.testing.assert_array_equal(pr82.read_binary_mask(dataset, "mask"), [False, True])

    def test_units_must_be_present_and_match_the_physical_field(self):
        dataset = self.ArrayDataset(
            pressure=np.array([100_000.0]),
            candidate_temperature=np.array([280.0]),
            candidate_vapor=np.array([0.004]),
            candidate_dry_mass_measure=np.array([1.0]),
            thermo_preprior_dry_air_mass_measure=np.array([0.9]),
        )
        var = dataset.variables
        var["pressure"].units = "Pa"
        var["candidate_temperature"].units = "K"
        var["candidate_vapor"].units = "kg kg-1 dryair"
        var["candidate_dry_mass_measure"].units = "kg dryair"
        var["thermo_preprior_dry_air_mass_measure"].units = "kg"

        pr82.require_units(dataset, "pressure", pr82.PRESSURE_UNITS, "pressure")
        pr82.require_units(dataset, "candidate_temperature", pr82.TEMPERATURE_UNITS,
                           "temperature")
        pr82.require_units(dataset, "candidate_vapor", pr82.MIXING_RATIO_UNITS,
                           "water-vapor mixing ratio")
        pr82.require_units(dataset, "candidate_dry_mass_measure",
                           pr82.DRY_AIR_MASS_UNITS, "dry-air cell mass")
        # Only the saved pre-density cell-mass vector accepts plain kg.
        pr82.require_units(dataset, "thermo_preprior_dry_air_mass_measure",
                           pr82.PREPRIOR_DRY_MASS_UNITS, "saved pre-density cell mass")

        for name, units in (("pressure", "hPa"),
                            ("candidate_temperature", "degC"),
                            ("candidate_vapor", "kg kg-1 moistair"),
                            ("candidate_dry_mass_measure", "kg"),
                            ("thermo_preprior_dry_air_mass_measure", "kg dryair")):
            with self.subTest(name=name):
                var[name].units = units
                accepted = {
                    "pressure": pr82.PRESSURE_UNITS,
                    "candidate_temperature": pr82.TEMPERATURE_UNITS,
                    "candidate_vapor": pr82.MIXING_RATIO_UNITS,
                    "candidate_dry_mass_measure": pr82.DRY_AIR_MASS_UNITS,
                    "thermo_preprior_dry_air_mass_measure": pr82.PREPRIOR_DRY_MASS_UNITS,
                }[name]
                with self.assertRaisesRegex(ValueError, "missing or unsupported units"):
                    pr82.require_units(dataset, name, accepted, name)

        var["candidate_temperature"].units = ""
        with self.assertRaisesRegex(ValueError, "missing or unsupported units"):
            pr82.require_units(dataset, "candidate_temperature", pr82.TEMPERATURE_UNITS,
                               "temperature")

    def test_fixed_mask_set_and_support_subset_are_enforced(self):
        above = np.array([[[True, True, False]]])
        reference = {
            "above_ground": above,
            "analysis_support": np.array([[[True, False, False]]]),
            "radar_valid": np.array([[[True, False, False]]]),
            "radar_no_echo": np.array([[[False, True, False]]]),
            "radar_missing": np.array([[[False, False, False]]]),
        }
        pr82.validate_mask_set("reference", reference, above)
        pr82.validate_fixed_common_masks(reference, dict(reference), "candidate")

        changed = dict(reference)
        changed["analysis_support"] = np.array([[[False, True, False]]])
        with self.assertRaisesRegex(ValueError, "changed common mask analysis_support"):
            pr82.validate_fixed_common_masks(reference, changed, "candidate")

        invalid_support = dict(reference)
        invalid_support["analysis_support"] = np.array([[[False, False, True]]])
        with self.assertRaisesRegex(ValueError, "subset of above-ground"):
            pr82.validate_mask_set("candidate", invalid_support, above)

    def test_new_output_rejects_existing_file_without_replacing_it(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "receipt.json"
            output.write_text("old receipt\n", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                pr82.write_new_json(output, {"new": True})

            self.assertEqual(output.read_text(encoding="utf-8"), "old receipt\n")

    def test_new_output_rejects_dangling_symlink_and_symlink_ancestor(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dangling = root / "dangling.json"
            dangling.symlink_to(root / "absent.json")
            with self.assertRaisesRegex(ValueError, "symlink"):
                pr82.write_new_json(dangling, {})

            real = root / "real"
            real.mkdir()
            alias = root / "alias"
            alias.symlink_to(real, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlink"):
                pr82.write_new_json(alias / "receipt.json", {})

    def test_new_output_writes_once(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "nested" / "receipt.json"
            pr82.write_new_json(output, {"status": "ok"})
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), {"status": "ok"})

    def test_new_output_rejects_nonstandard_json_nan(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "receipt.json"
            with self.assertRaises(ValueError):
                pr82.write_new_json(output, {"invalid": float("nan")})
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
