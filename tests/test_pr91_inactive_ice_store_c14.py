from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from pr91_inactive_ice_store_c14 import transform_module

PROFILE = ROOT / "tests/intel_toolchain.sh"
CORE_TEST = ROOT / "tests/test_joint_qnb_transport.f90"


class InactiveIceStoreC14Tests(unittest.TestCase):
    def test_pinned_c12_host_receives_bounded_ice_optin_and_ledger(self) -> None:
        c12 = (ROOT / "docs/evidence/pr91_source_store_contract_20261020/c12/generated/module_em.F").read_text()
        core = (ROOT / "src/common/cloud_bal_joint_transport.f90").read_text()

        generated = transform_module(c12, core)

        self.assertEqual(
            hashlib.sha256(generated.encode()).hexdigest(),
            "6a7a97c23c84f05837a3bb5e384ce944ecd2df220ea1889d990349cd509094b1",
        )
        self.assertIn("inactive_q_quantum_adjustment_pairs=[.FALSE.,.TRUE.,.FALSE.,.FALSE.]", generated)
        self.assertIn("'INACTIVE_Q_QUANTUM_ADJUSTMENTS',inactive_q_quantum_adjustments", generated)
        self.assertEqual(generated.count("allow_inactive_q_quantum_adjustment=(p==2)"), 4)
        self.assertEqual(generated.count("allow_inactive_q_quantum_adjustment=(pair==2)"), 1)
        self.assertIn("inactive_q_quantum_adjustments=trial_inactive_q_quantum_adjustments", generated)
        self.assertIn("diagnostic_stage, diagnostic_candidate, diagnostic_stored", generated)
        self.assertIn("failure_stage=local_store_stage", generated)

    def test_instrumented_core_compiles_and_runs_joint_transport_suite(self) -> None:
        c12 = (ROOT / "docs/evidence/pr91_source_store_contract_20261020/c12/generated/module_em.F").read_text()
        core = (ROOT / "src/common/cloud_bal_joint_transport.f90").read_text()
        generated = transform_module(c12, core)
        end_marker = "end module cloud_bal_joint_transport"
        end = generated.index(end_marker) + len(end_marker)

        with tempfile.TemporaryDirectory(prefix="pr91_c14_core_test.", dir="/var/tmp") as scratch:
            scratch_path = Path(scratch)
            core_path = scratch_path / "cloud_bal_joint_transport.f90"
            core_path.write_text(generated[:end] + "\n")
            for flag_var in ("CLOUD_BAL_FREE_FLAGS", "CLOUD_BAL_REPRO_FLAGS"):
                executable = scratch_path / f"test_joint_qnb_transport_{flag_var}"
                command = (
                    f'. "{PROFILE}" && cd "{scratch_path}" && '
                    f'"$CLOUD_BAL_FC" "${{{flag_var}[@]}}" '
                    f'-module "{scratch_path}" -I "{scratch_path}" '
                    f'"{core_path}" "{CORE_TEST}" -o "{executable}" && '
                    f'"{executable}"'
                )
                result = subprocess.run(
                    ["bash", "-lc", command], capture_output=True, text=True, check=False
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("PASS test_joint_qnb_transport", result.stdout)


if __name__ == "__main__":
    unittest.main()
