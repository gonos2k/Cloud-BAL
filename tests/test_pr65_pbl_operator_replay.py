#!/usr/bin/env python3
"""Contract tests for PR65's captured Shinhong matrix replay."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from pr65_pbl_operator_replay import validate  # noqa: E402


def captures() -> tuple[str, str]:
    operator = "\n".join(
        (
            "CALL,172,76,1,2,4.0000000000000000E+001,2.5000000000000000E-002,1,T",
            "ROW,1,5.0000000000000000E+002,2.0000000000000001E-001,2.0000000000000001E-001,0.0,1.0,0.0",
            "ROW,2,5.0000000000000000E+002,3.0000000000000004E-001,3.0000000000000004E-001,0.0,1.0,0.0",
            "SOL,1,2.0000000298023224E-001",
            "SOL,2,3.0000001192092896E-001",
        )
    ) + "\n"
    nc = "\n".join(
        (
            "CALL,172,76,1,2,2.0000000000000000E+001,6,6,T,0,T",
            "NC,1,2.0000000000000001E-001,1.0000000000000000E+006",
            "NC,2,3.0000000000000004E-001,2.0000000000000000E+006",
        )
    ) + "\n"
    return operator, nc


class PR65PblOperatorReplayTest(unittest.TestCase):
    def run_capture(self, operator: str, nc: str) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as directory:
            operator_path = Path(directory) / "operator.raw"
            nc_path = Path(directory) / "nc.raw"
            operator_path.write_text(operator)
            nc_path.write_text(nc)
            return validate(operator_path, nc_path)

    def test_shared_nonuniform_mixing_preserves_donor_ratio_and_weighted_totals(self) -> None:
        # DEL=(500,1000) and one shared interface give this closed diffusion
        # matrix. Its exact solution for (0,x) is (2*x/7,6*x/7).
        operator = "\n".join((
            "CALL,172,76,1,2,40,0.02500000037252903,1,T",
            "ROW,1,500,0,0,0,1.5,-0.5",
            "ROW,2,1000,0.001,0.001,-0.25,1.25,0",
            f"SOL,1,{2e-3 / 7:.17g}",
            f"SOL,2,{6e-3 / 7:.17g}",
        )) + "\n"
        nc = "CALL,172,76,1,2,20,3,6\nNC,1,0,0\nNC,2,0.001,1000000\n"
        result = self.run_capture(operator, nc)
        water = result["same_matrix_replay"]["QC"]
        number = result["same_matrix_replay"]["NC"]
        for mass, count in zip(water["output"], number["output"]):
            self.assertGreater(mass, 0)
            self.assertGreater(count, 0)
            self.assertAlmostEqual(mass / count / 1e-9, 1.0, delta=3e-7)
        for state in (water, number):
            self.assertLess(abs(state["del_weighted_relative_change"]), 3e-7)
        self.assertAlmostEqual(water["output"][0], 2e-3 / 7, delta=2e-10)
        self.assertAlmostEqual(number["output"][1], 6e6 / 7, delta=0.2)

    def test_replays_full_matrix_on_qc_and_paired_nc(self) -> None:
        operator, nc = captures()
        result = self.run_capture(operator, nc)
        self.assertEqual(result["target"], {"i": 172, "j": 76, "kts": 1, "kte": 2})
        self.assertLessEqual(result["same_matrix_replay"]["QC"]["max_abs_difference_from_captured_solution"], 1e-9)
        self.assertTrue(result["scope"]["nc_is_same_matrix_research_counterfactual"])
        self.assertTrue(result["scope"]["native_call_observed"])
        self.assertFalse(result["scope"]["native_solution_captured"])
        self.assertFalse(result["scope"]["del_equals_native_hybrid_dry_carrier"])
        self.assertEqual(result["same_matrix_replay"]["NC"]["output_min"], 1_000_000.0)
        self.assertTrue(result["nc_activation_gates"]["activation_gates_verified"])

    def test_validates_native_nc_output_against_same_a_replay_and_single_accumulation(self) -> None:
        operator, nc = captures()
        nc += "NC_OUT,1,0,0,0\nNC_OUT,2,0,0,0\n"
        result = self.run_capture(operator, nc)
        self.assertTrue(result["scope"]["native_call_observed"])
        self.assertFalse(result["scope"]["native_solution_captured"])
        self.assertTrue(result["scope"]["native_returned_tendency_captured"])
        self.assertTrue(result["scope"]["native_scalar_tend_accumulation_captured"])
        self.assertEqual(result["native_nc_validation"]["levels"], 2)
        self.assertEqual(
            result["native_nc_validation"]["tendency_units"],
            "number/(kg dry air*s); module_em applies the native carrier later",
        )
        self.assertEqual(
            result["native_nc_validation"]["max_abs_tendency_difference_from_same_a_replay"], 0.0
        )

        duplicate_update = nc.replace("NC_OUT,2,0,0,0", "NC_OUT,2,0,0,1")
        with self.assertRaisesRegex(ValueError, "exactly one NC tendency addition"):
            self.run_capture(operator, duplicate_update)

        wrong_tendency = nc.replace("NC_OUT,1,0,0,0", "NC_OUT,1,1,0,1")
        with self.assertRaisesRegex(ValueError, "differs from same-A"):
            self.run_capture(operator, wrong_tendency)

    def test_rejects_disabled_shared_nc_activation_and_reports_legacy_gates(self) -> None:
        operator, nc = captures()
        with self.assertRaisesRegex(ValueError, "enabled=T, qnc_flag=T, scalar_pblmix=0"):
            self.run_capture(operator, nc.replace(",6,6,T,0,T", ",6,6,F,0,T"))
        with self.assertRaisesRegex(ValueError, "enabled=T, qnc_flag=T, scalar_pblmix=0"):
            self.run_capture(operator, nc.replace(",6,6,T,0,T", ",6,6,T,1,T"))

        legacy_nc = nc.replace(",6,6,T,0,T", ",6,6")
        result = self.run_capture(operator, legacy_nc)
        self.assertFalse(result["nc_activation_gates"]["activation_gates_verified"])
        self.assertEqual(result["nc_activation_gates"]["schema"], "legacy_8_field")
        self.assertFalse(result["scope"]["native_call_observed"])
        self.assertFalse(result["scope"]["native_returned_tendency_captured"])
        self.assertFalse(result["scope"]["native_solution_captured"])

    def test_rejects_incomplete_and_mismatched_columns(self) -> None:
        operator, nc = captures()
        with self.assertRaisesRegex(ValueError, "full selected column"):
            self.run_capture("\n".join(operator.splitlines()[:-1]) + "\n", nc)
        with self.assertRaisesRegex(ValueError, "columns do not match"):
            self.run_capture(operator, nc.replace("CALL,172,76", "CALL,173,76"))

    def test_rejects_nonpositive_del_or_non_metzler_matrix(self) -> None:
        operator, nc = captures()
        with self.assertRaisesRegex(ValueError, "DEL must be positive"):
            self.run_capture(operator.replace("ROW,1,5.000", "ROW,1,0.000", 1), nc)
        with self.assertRaisesRegex(ValueError, "positive off-diagonal"):
            self.run_capture(operator.replace("ROW,2,5.0000000000000000E+002,3.0000000000000004E-001,3.0000000000000004E-001,0.0,1.0,0.0",
                                              "ROW,2,5.0000000000000000E+002,3.0000000000000004E-001,3.0000000000000004E-001,0.1,1.0,0.0"), nc)

    def test_rejects_unrepresentable_and_unbounded_replay_inputs(self) -> None:
        operator, nc = captures()
        with self.assertRaisesRegex(ValueError, "binary32-range"):
            self.run_capture(operator.replace("2.0000000000000001E-001", "1.0e300", 1), nc)

        weakly_dominant = operator.replace(
            "ROW,2,5.0000000000000000E+002,3.0000000000000004E-001,3.0000000000000004E-001,0.0,1.0,0.0",
            "ROW,2,5.0000000000000000E+002,3.0000000000000004E-001,3.0000000000000004E-001,-1.0,1.0,0.0",
        )
        with self.assertRaisesRegex(ValueError, "strict row-dominance margin"):
            self.run_capture(weakly_dominant, nc)


if __name__ == "__main__":
    unittest.main()
