from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from pr94_compact_diagnostics import compact_observer  # noqa: E402


class CompactObserverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = (ROOT / "tools/pr85_joint_stage_observer.f90").read_text(encoding="utf-8")

    def test_gates_wrap_only_existing_writes_and_keep_density_validation(self) -> None:
        generated = compact_observer(self.source, 1800)

        self.assertEqual(generated.count("  IF (itimestep.LE."), 2)
        self.assertIn("itimestep.LE.30", generated)
        self.assertIn("itimestep.EQ.60", generated)
        self.assertIn("itimestep.EQ.90", generated)
        self.assertNotIn("itimestep.EQ.180", generated)
        self.assertIn("TRIM(label).EQ.'POST_KDM6'", generated)
        self.assertIn("  CLOSE(u)\n  ENDIF\n  DEALLOCATE(dry_density)", generated)
        self.assertIn("  CLOSE(u)\n  ENDIF\nEND SUBROUTINE pr85_pbl_tendency_dump", generated)

        self.assertEqual(generated.count("CALL pr85_dry_density_from_al_alb"),
                         self.source.count("CALL pr85_dry_density_from_al_alb"))
        self.assertEqual(generated.count("CALL wrf_error_fatal('PR85 invalid AL+ALB stage density')"),
                         self.source.count("CALL wrf_error_fatal('PR85 invalid AL+ALB stage density')"))
        self.assertEqual(generated.count("WRITE(u)"), self.source.count("WRITE(u)"))

    def test_60_minute_profile_adds_only_3600_second_detail(self) -> None:
        generated = compact_observer(self.source, 3600)
        self.assertEqual(generated.count("itimestep.EQ.180"), 2)
        self.assertEqual(generated.count("itimestep.EQ.60"), 2)
        self.assertEqual(generated.count("itimestep.EQ.90"), 2)

    def test_rejects_unreviewed_duration_and_changed_source_shape(self) -> None:
        with self.assertRaises(ValueError):
            compact_observer(self.source, 1200)
        with self.assertRaises(ValueError):
            compact_observer(self.source.replace("FILE='pr85_joint_moment_stages.raw'", "FILE='altered.raw'"), 1800)


if __name__ == "__main__":
    unittest.main()
