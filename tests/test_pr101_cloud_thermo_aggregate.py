import unittest
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from pr101_cloud_thermo_aggregate import (
    _arm_absolute, _branch_counts, _metadata_from_template, verify_hash,
)
from pr101_cloud_thermo_refresh_manifest import verify_pairs


def row(*, full=False, qc=0.0, rh=0.9, extent=0.0):
    return {"full_evaporation": full, "qc_before": qc, "rh_branch": rh,
            "source_extent": extent, "saturation_oracle_ulp_differences": {"qs": 0}}


class ThermoAggregateTests(unittest.TestCase):
    def test_conditional_counts_are_qc_positive_and_preserve_branch(self):
        rows = [row(full=True, qc=0.1, rh=0.8, extent=0.1),
                row(qc=0.1, rh=1.1, extent=-0.01),
                row(qc=0.0, rh=0.5, extent=0.0)]
        result = _branch_counts(rows)
        self.assertEqual(result["rows"], 3)
        self.assertEqual(result["qc_before_positive"], 2)
        self.assertEqual(result["qc_positive_liquid_RH_counts"]["rh_branch_lt_1"]["full_evaporation"], 1)
        self.assertEqual(result["qc_positive_liquid_RH_counts"]["rh_branch_ge_1"]["extent_sign"]["condensation_negative_extent"], 1)
        self.assertEqual(result["extent_sign_by_branch"]["general_branch"]["zero_extent"], 1)

    def test_arm_sums_use_rows_and_keep_oracle_advisory(self):
        values = {name: float(index) for index, name in enumerate((
            "unbounded_evaporation", "bounded_evaporation", "source_extent",
            "stored_dqv", "stored_dqc", "stored_dt"), start=1)}
        sample = row(full=True)
        sample.update(values)
        sample["saturation_oracle_ulp_differences"] = {"es": 0, "qs": 2}
        result = _arm_absolute([sample])
        self.assertEqual(result["sum"], values)
        self.assertEqual(result["python_saturation_oracle"]["max_ulp_difference"], 2)
        self.assertEqual(result["python_saturation_oracle"]["disposition"], "advisory only")

    def test_changed_fixed_input_hash_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "capture.raw"
            path.write_bytes(b"changed capture")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                verify_hash(path, "0" * 64, "pinned capture")

    def test_manifest_fixed_pin_verification_is_read_only(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "input.raw"
            path.write_bytes(b"actual fixed input")
            pair = {"path": str(path), "sha256": "0" * 64}
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                verify_pairs(pair)
            self.assertEqual(pair["sha256"], "0" * 64)

    def test_template_supplies_only_allowlisted_metadata(self):
        template = {
            "schema": "fixture", "source_sha256": "source", "executable_sha256": "exe",
            "lineage": {"OFF": "retained"}, "diagnostics": {"phase": "liquid"},
            "branch_count_semantics": "signed extent", "rh_scope_note": "cloud only",
            "arm_absolutes": {"OFF": {"rows": 999, "sum": {"stored_dqc": -999}}},
            "ranked_cells": {"wrong": {"i": -99}},
        }
        result = _metadata_from_template(template)
        self.assertEqual(result["schema"], "fixture")
        self.assertNotIn("arm_absolutes", result)
        self.assertNotIn("ranked_cells", result)


if __name__ == "__main__":
    unittest.main()
