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

    @unittest.skipUnless(PINNED_HOST.is_file(), "receipt-pinned C1 host source is unavailable")
    def test_pinned_host_transform_preserves_core_and_wires_full_candidate(self) -> None:
        host = PINNED_HOST.read_text()
        core_path = ROOT / "src/common/cloud_bal_joint_transport.f90"
        core = core_path.read_text()
        baseline = (ROOT / "tests/fixtures/pr99_c1_core_pre_certificate.f90").read_text()
        transformed = contract.transform_module(host, core, baseline)
        self.assertEqual(contract.digest(transformed), "98a44389d693ec28533d492c129204fc0bdba22e6ed3ae71acc9e65df7b9cb1a")

        module_start = transformed.index("module cloud_bal_joint_transport\n")
        module_end = transformed.index("end module cloud_bal_joint_transport", module_start) + len(
            "end module cloud_bal_joint_transport")
        self.assertEqual(transformed[module_start:module_end], instrument_core(core, contract.CORE_SHA256).rstrip())

        host_start = transformed.index("  SUBROUTINE certify_graupel_storage(")
        host_end = transformed.index("  END SUBROUTINE certify_graupel_storage", host_start)
        certifier = transformed[host_start:host_end]
        self.assertEqual(certifier.count("joint_bulk_candidate_absence_is_valid("), 1)
        self.assertIn("IF (.NOT.store_valid.AND.use_bulk_absence) THEN", certifier)
        self.assertIn("qa64(c,4),na64(c,4),1.0_real64,minmass(4),maxmass(4),value_q,value_n", certifier)
        self.assertIn("CALL add_graupel_diffusion_mixture", certifier)
        self.assertIn("reject_reason=6", certifier)
        self.assertEqual(transformed.count("CALL certify_graupel_storage("), 2)

        with self.assertRaisesRegex(ValueError, "reviewed grouped-transport core"):
            contract.transform_module(host, baseline, baseline)
        with self.assertRaisesRegex(ValueError, "pre-certificate C1 core"):
            contract.transform_module(host, core, core)


if __name__ == "__main__":
    unittest.main()
