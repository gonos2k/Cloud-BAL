from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PINNED_HOST = Path("/var/tmp/pr96_native_build_c1_20261021/source/overrides/module_em.F")
sys.path.insert(0, str(ROOT / "tools"))
import pr99_bulk_candidate_contract as contract
from pr91_host_store_trace import instrument_core


class BulkCandidateContractTests(unittest.TestCase):
    def test_fatal_fixture_binds_full_candidate_operands_and_scope(self) -> None:
        fixture_path = ROOT / "tests/fixtures/pr99_bulk_candidate_fatal.json"
        data = json.loads(fixture_path.read_text())
        event = data["event"]
        self.assertEqual(data["schema"], "pr99_bulk_candidate_fatal_fixture_v1")
        self.assertEqual(data["provenance"]["source_module_em_sha256"], contract.HOST_SHA256)
        self.assertEqual(event["source_q_hex64"], "3753214B46A3BC21")
        self.assertEqual(event["source_b_hex64"], "36B5C40847451A51")
        self.assertEqual(event["reference_candidate_q_hex64"], "36796B3BA65C1BE8")
        self.assertEqual(event["reference_candidate_b_hex64"], "35DCEBC8FCFEFC7A")
        self.assertTrue(event["expected_certificate"])
        self.assertIn("not an upstream source-precision proof", data["provenance"]["scope"])
        old_arms = data["provenance"]["historical_three_arm_comparison"]
        self.assertTrue(old_arms["all_arms_share_event_bits"])
        self.assertEqual(set(old_arms["arms"]), {"OFF", "HYDRO", "COUPLED"})
        for arm in old_arms["arms"].values():
            self.assertEqual(arm["status"], "INCOMPLETE")
        self.assertIn("future modified run", old_arms["scope_note"])

    def test_transform_rejects_unpinned_sources(self) -> None:
        with self.assertRaisesRegex(ValueError, "pinned C1 host"):
            contract.transform_module("not the pinned host", "", "")




if __name__ == "__main__":
    unittest.main()
