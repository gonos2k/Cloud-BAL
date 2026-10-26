from __future__ import annotations

import gzip
import hashlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from pr87_progb_failure_context import V36_KDM6_SHA256, add_progb_failure_context

V36_SOURCE = ROOT / "docs/evidence/pr87_two_step_v36_20261016/module_mp_kdm6.F.gz"


class TestPR87ProgBArchivedV36(unittest.TestCase):
    def test_v36_reports_first_unsupported_and_post_rounding_density(self):
        original = gzip.open(V36_SOURCE, "rt").read()
        self.assertEqual(hashlib.sha256(original.encode()).hexdigest(), V36_KDM6_SHA256)
        generated = add_progb_failure_context(original)
        self.assertEqual(generated.count("source_context="), 7)
        routine = generated[
            generated.index("   SUBROUTINE ProgB_param("):
            generated.index("  END subroutine ProgB_param")
        ]
        self.assertEqual(routine.count("'PR87_PROGB_UNSUPPORTED'"), 6)
        self.assertIn("if (brs(i,k).gt.0.0) then", routine)
        self.assertIn("pr87_ratio=dble(qrs(i,k,3))/dble(brs(i,k))", routine)
        self.assertIn("transfer(qrs(i,k,3),0),transfer(brs(i,k),0)", routine)
        self.assertEqual(routine.count("'PR87_PROGB_POST_BG_RATIO'"), 1)
        self.assertIn("pr87_bg_before=brs(i,k)", routine)
        self.assertIn("dble(pr87_bg_before),dble(brs(i,k))", routine)
        self.assertIn("transfer(pr87_bg_before,0),transfer(brs(i,k),0)", routine)
        self.assertEqual(routine.count("brs(i,k) = qrs(i,k,3)/rhox(i,k)"), 1)
        for unchanged in (
            "progb_status(i,k) = PROGB_UNSUPPORTED",
            "progb_status(i,k) = PROGB_TRANSIENT",
            "progb_status(i,k) = PROGB_PSD_ACTIVE",
            "raw_density = dble(qrs(i,k,3))/dble(brs(i,k))",
        ):
            self.assertEqual(
                routine.count(unchanged),
                original[
                    original.index("   SUBROUTINE ProgB_param("):
                    original.index("  END subroutine ProgB_param")
                ].count(unchanged),
            )
        with self.assertRaises(ValueError):
            add_progb_failure_context(original + "\n")
        with self.assertRaises(ValueError):
            add_progb_failure_context(generated)
