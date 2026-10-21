from __future__ import annotations

import sys
import unittest
import gzip
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import pr97_620_c4_failure_classify as classifier


class C4FailureClassificationTests(unittest.TestCase):
    def test_generic_eight_ulp_validator_is_not_source_strict_gate(self) -> None:
        row = [32, 1, 4, 163, 63, 22, 95176.06, 95183.7, 0, 0, 0, 0,
               1.728904501183349e-7, 1.921005001314832e-10,
               1.21092480127459e-11, 1.345472001416211e-14,
               -1, -1, 0.4795779, 6.666667]

        result = classifier.source_storage.classify_full_row(row)

        self.assertTrue(result["continuous_valid_with_coded_8ulp_tolerance"])
        self.assertEqual(result["classification"], "continuous_and_rounded_pair_pass")

    def test_exact_captures_and_replay_are_reported_separately(self) -> None:
        report = classifier.create_report()
        for arm_name, arm in report["arms"].items():
            self.assertEqual(arm["ledger_full_failure_count"], arm["source_capture_full_count"])
            self.assertEqual(arm["source_capture_full_count"], 7 if arm_name == "OFF" else 6)
            for failure in arm["failures"]:
                self.assertIn(failure["full_store_failure_stage"], (2, 6))
                self.assertEqual(len(failure["candidate_real64_bits"]["q"]), 16)
                self.assertEqual(len(failure["candidate_real64_bits"]["n"]), 16)
        mismatches = [(name, item["i"], item["j"], item["k"])
                      for name, arm in report["arms"].items() for item in arm["failures"]
                      if not item["runtime_store_behavior_reproduced"]]
        self.assertEqual(mismatches, [])

    def test_reversed_captures_join_replay_stages_by_cell_key(self) -> None:
        root = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr94_physics_20261021/runs_on_lustre")
        for arm in ("OFF", "COUPLED"):
            run_root = root / f"{arm}_3600s_c4_compact/run"
            rows, _ = classifier.source_storage.read_full_rows(run_root / "pr85_joint_source_failure.raw.gz")
            captures = classifier._full_captures(run_root / "pr92_graupel_source_capture.raw.gz")
            captures.reverse()
            replay_results = [
                {"valid": False, "failure_stage": capture["stage"]}
                for capture in captures
            ]

            joined = classifier._join_replays_to_full_rows(rows, captures, replay_results)

            self.assertEqual(len(joined), len(rows))
            for row, (capture, result) in zip(rows, joined):
                self.assertEqual(classifier._full_key(row), classifier._capture_key(capture))
                self.assertEqual(result["failure_stage"], capture["stage"])


if __name__ == "__main__":
    unittest.main()
