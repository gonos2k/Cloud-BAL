import unittest

from pr78_native_fp_runtime_choice import transform_kdm6, transform_host_main as transform_runtime_host
from pr78_native_fp_runtime_run import (
    add_noah_operand_observer,
    parse_fp_trace,
    parse_noah_operand_trace,
)
from test_pr77_native_state_transform import HOST_MAIN, kdm6_source


class RuntimeChoiceTransformTest(unittest.TestCase):
    def test_kdm6_uses_environment_choice_and_keeps_state_observers(self):
        source = transform_kdm6(kdm6_source())
        self.assertIn("PR78_FP_MODE", source)
        self.assertIn("trim(pr78_fp_mode) == 'CLEAR_FTZ_DAZ'", source)
        self.assertIn("trim(pr78_fp_mode) /= 'PRESERVE'", source)
        self.assertEqual(source.count("= pr76_apply_gradual("), 1)
        self.assertIn("call pr77_scan_entry_state(", source)
        self.assertIn("call validate_kdm6_species_states(", source)

    def test_host_startup_uses_same_runtime_choice(self):
        source = transform_runtime_host(HOST_MAIN)
        self.assertIn("PR78_FP_MODE", source)
        self.assertIn("CLEAR_FTZ_DAZ", source)
        self.assertIn("OMP_STARTUP_TEAM", source)
        self.assertEqual(source.count("CALL wrf_init"), 1)

    def test_changed_source_anchors_are_rejected(self):
        with self.assertRaises(ValueError):
            transform_kdm6(kdm6_source().replace("pr67_trace_complete", "renamed"))
        with self.assertRaises(ValueError):
            transform_runtime_host(HOST_MAIN + "  CALL wrf_init\n")

    def test_runtime_trace_observer_checks_only_the_selected_control_bits(self):
        trace = ("PR77_HOST_FP,MAIN_STARTUP,00009FFD,00009FFD,41\n"
                 "PR77_HOST_FP,OMP_STARTUP_TEAM,00009FFD,00009FFD,41\n")
        preserved = parse_fp_trace(trace, "PRESERVE", 1)
        self.assertEqual(preserved["startup_team_size"], 1)
        self.assertTrue(preserved["only_ftz_daz_choice_applied"])

        cleared_trace = trace.replace("00009FFD,00009FFD", "00009FFD,00001FBD")
        cleared = parse_fp_trace(cleared_trace, "CLEAR_FTZ_DAZ", 1)
        self.assertEqual(cleared["records"][0]["after"], "0x00001FBD")
        with self.assertRaises(ValueError):
            parse_fp_trace(cleared_trace, "PRESERVE", 1)

    def test_noah_observer_precedes_original_equation_without_dividing(self):
        source = ("MODULE module_sf_noahdrv\n"
                  "              FK=(( (HLICE/(GRAV*(-PSISAT))) *                              &\n"
                  "                 ((TSLB(I,NS,J)-T0)/TSLB(I,NS,J)) )**(-1/BX) )*SMCMAX\n")
        observed = add_noah_operand_observer(source)
        self.assertLess(observed.index("PR78_NOAH_FK"), observed.index("FK=(("))
        self.assertIn("PR78_NONPOSITIVE_BASE", observed)
        self.assertIn("ieee_is_finite(PSISAT)", observed)
        self.assertEqual(observed.count("FK=(("), 1)
        with self.assertRaises(ValueError):
            add_noah_operand_observer(source.replace("FK=((", "FK = (", 1))

    def test_noah_trace_reconstructs_full_base_from_captured_operands(self):
        trace = ("PR78_NOAH_FK,138,4,197, 2.7281405639648438E+002, "
                 "2.7314999389648438E+002, 5.5000000000000000E+000, "
                 "2.1899999678134918E-001, 4.3999999761581421E-001, "
                 "3.3350000000000000E+005, 9.8100004196166992E+000,T,F, "
                 "43886833,43889333,40B00000,3E604189,3EE147AE,48A2D780,411CF5C3\n")
        record = parse_noah_operand_trace(trace)[0]
        self.assertEqual((record["i"], record["soil_layer"], record["j"]), (138, 4, 197))
        self.assertTrue(record["all_operands_finite"])
        self.assertFalse(record["base_nonpositive_by_sign"])
        self.assertGreater(record["base_from_captured_values"], 0)
        self.assertTrue(record["base_sign_matches_observer"])
        self.assertEqual(record["binary32_bits"]["bx"], "40B00000")


if __name__ == "__main__":
    unittest.main()
