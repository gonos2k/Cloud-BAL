#!/usr/bin/env python3
"""Hash-bound integration tests for the full guarded PR71 source composition."""

from __future__ import annotations

import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("/var/tmp/pr68_velocity_native_20261007/source/module_mp_kdm6_combined_research.f90")
PROCESS_PATCH = ROOT / "docs/evidence/pr70_coupled_process_cutoff_search_20261008.patch"
VALIDITY_PATCH = ROOT / "docs/evidence/pr71_particle_output_contract_20261008.patch"
COUNT_PATCH = ROOT / "docs/evidence/pr71_step_count_contract_20261008_v2.patch"
COMPOSER = ROOT / "tools/pr71_compose_guarded_kdm6.py"
SOURCE_SHA256 = "97e9892ff527a318f6266140eecc03238485a68b050c61bbaca7ea94f28bfdaa"
PROCESS_SHA256 = "5f1b75925ec803838f5b3cfa81012336f4d21727073c5d8c0703fb70ddc37670"
VALIDITY_SHA256 = "94ea6189c85cd0856a28aac2663ad70091c3259fc448d48bd021adf42ff9ae45"
COUNT_SHA256 = "7bc37047bf616b50ebb506f130a2f1f0535e0a5afc26bb26183a27ee188ebb24"
BASE_SHA256 = "5de1884ab59e3de30a3e4ef1d8317405f1ba0591cf7ed9aa6fbca574d5233f41"
CHECKED_SHA256 = "6245969c87f6568cad3b6c6afddc0d1bdfe84a31baa1cee10a465b663c88d716"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class GuardedComposerTests(unittest.TestCase):
    def test_frozen_guarded_composition(self) -> None:
        self.assertEqual(digest(SOURCE), SOURCE_SHA256)
        self.assertEqual(digest(PROCESS_PATCH), PROCESS_SHA256)
        self.assertEqual(digest(VALIDITY_PATCH), VALIDITY_SHA256)
        self.assertEqual(digest(COUNT_PATCH), COUNT_SHA256)
        with tempfile.TemporaryDirectory(prefix="pr71_guarded_composer_test_") as temporary:
            output = Path(temporary) / "checked.F"
            command = [
                "python3", str(COMPOSER), str(SOURCE), str(PROCESS_PATCH),
                str(VALIDITY_PATCH), str(COUNT_PATCH), str(output),
                "--expected-validity-patch-sha256", VALIDITY_SHA256,
                "--expected-step-count-patch-sha256", COUNT_SHA256,
            ]
            result = subprocess.run(command, text=True, capture_output=True, check=True)
            self.assertIn(f"PR71_BASE_SOURCE_SHA256 {BASE_SHA256}", result.stdout)
            self.assertIn(f"PR71_CHECKED_SOURCE_SHA256 {CHECKED_SHA256}", result.stdout)
            self.assertEqual(digest(output), CHECKED_SHA256)
            self.assertTrue(output.with_suffix(".F.composition.json").is_file())
            source = output.read_text(encoding="utf-8")
            self.assertIn("PR71_STEP_COUNT_CONTRACT_BEGIN", source)
            self.assertEqual(source.count("call checked_substep_count("), 2)
            self.assertIn("PR71_STEP_COUNT_REJECT_ICE", source)

    def test_step_patch_hash_mismatch_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pr71_guarded_bad_patch_") as temporary:
            output = Path(temporary) / "checked.F"
            result = subprocess.run(
                [
                    "python3", str(COMPOSER), str(SOURCE), str(PROCESS_PATCH),
                    str(VALIDITY_PATCH), str(COUNT_PATCH), str(output),
                    "--expected-validity-patch-sha256", VALIDITY_SHA256,
                    "--expected-step-count-patch-sha256", "0" * 64,
                ], text=True, capture_output=True, check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("PR71 step-count patch SHA-256 mismatch", result.stderr)
            self.assertFalse(output.exists())
            self.assertFalse(output.with_suffix(".F.composition.json").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
