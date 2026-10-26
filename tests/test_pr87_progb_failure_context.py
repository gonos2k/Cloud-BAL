from pathlib import Path
import sys
import gzip
import hashlib
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from pr87_progb_failure_context import (  # noqa: E402
    V31_KDM6_SHA256,
    V36_KDM6_SHA256,
    add_progb_failure_context,
)


V31_SOURCE = Path("/var/tmp/pr87_joint_cycle_sources_20261016_v31/module_mp_kdm6.F")
V36_SOURCE = ROOT / "docs/evidence/pr87_two_step_v36_20261016/module_mp_kdm6.F.gz"


class ProgBFailureContextTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = V31_SOURCE.read_text()
        cls.generated = add_progb_failure_context(cls.original)

    def test_call_sites_are_tagged_in_source_order(self):
        calls = [
            line.strip()
            for line in self.generated.splitlines()
            if "source_context=" in line
        ]
        self.assertEqual(len(calls), 7)
        for number, call in enumerate(calls, start=1):
            self.assertIn(f"source_context={number},source_lat=lat", call)

    def test_diagnostic_only_runs_on_first_transient_per_call(self):
        routine = self.generated[
            self.generated.index("   SUBROUTINE ProgB_param("):
            self.generated.index("  END subroutine ProgB_param")
        ]
        self.assertIn("integer, optional, intent(in) :: source_context, source_lat", routine)
        self.assertIn("if (present(source_context) .and. present(source_lat) .and. &", routine)
        self.assertIn(".not.pr87_transient_logged)", routine)
        self.assertIn("transfer(qrs(i,k,3),0),transfer(brs(i,k),0)", routine)
        self.assertIn("dble(qrs(i,k,3))/dble(brs(i,k))", routine)
        self.assertIn("flush(6)", routine)
        self.assertIn("progb_status(i,k) = PROGB_TRANSIENT", routine)
        self.assertNotIn("brs(i,k) =", routine[routine.index("if (qrs(i,k,3) <= qcrmin"):
                                               routine.index("raw_density =")])

    def test_transform_is_pinned_and_rejects_other_sources(self):
        self.assertEqual(len(V31_KDM6_SHA256), 64)
        with self.assertRaises(ValueError):
            add_progb_failure_context(self.original + "\n")



if __name__ == "__main__":
    unittest.main()
