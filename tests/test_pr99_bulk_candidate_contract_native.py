from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PINNED_HOST = Path("/var/tmp/pr96_native_build_c1_20261021/source/overrides/module_em.F")
sys.path.insert(0, str(ROOT / "tools"))
import pr99_bulk_candidate_contract as contract
from pr91_host_store_trace import instrument_core


class TestBulkCandidateContractNative:
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
