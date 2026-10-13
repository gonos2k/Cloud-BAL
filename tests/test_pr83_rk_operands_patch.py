#!/usr/bin/env python3
"""Check the pinned RK operand observer patch without editing model sources."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(
    "/NHNHOME/WORKSPACE/26weather002_A/yhlee/KIM-meso/"
    "KIM_RDPS_MODL_V2026.2/dyn_em/module_em.F"
)
SOURCE_SHA256 = "7695bfb05a7f99763334a6e69523bbcc1de0f2c659177a18c10a6e1cf530a0c7"
PATCH = ROOT / "patches/pr83_rk_operands_trace.patch"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RKOperandsPatchTest(unittest.TestCase):
    def test_builder_binds_module_inputs_and_replaces_archive_member_in_place(self) -> None:
        builder = (ROOT / "tests/build_pr83_rk_operands_observer.sh").read_text()
        self.assertLess(
            builder.index("build_inputs_pre.json"),
            builder.index("subprocess.run(compile_args"),
        )
        self.assertIn("directory.glob('*.mod')", builder)
        self.assertIn("['ar','r',str(scratch_archive)", builder)
        self.assertNotIn("['ar','d',str(scratch_archive)", builder)
        self.assertIn("'-real-size', '32'", builder)
        self.assertIn("base_target_slots != [337]", builder)
        self.assertIn("candidate_target_slots != base_target_slots", builder)

    def test_patch_applies_to_pinned_source_copy(self) -> None:
        self.assertEqual(sha256(SOURCE), SOURCE_SHA256)
        with tempfile.TemporaryDirectory(prefix="pr83_rk_patch_check_") as tmp:
            root = Path(tmp)
            target = root / "dyn_em/module_em.F"
            target.parent.mkdir()
            shutil.copyfile(SOURCE, target)
            subprocess.run(
                ["patch", "--fuzz=0", "-p1", "-i", str(PATCH)],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            patched = target.read_text()
            self.assertIn("p_qnc", patched.split("CONTAINS", 1)[0].lower())
            for marker in (
                "PR83_RK_PRODUCT",
                "PR83_RK_TENDENCY",
                "PR83_RK_INPUT",
                "PR83_RK_OUTPUT",
            ):
                self.assertEqual(patched.count(marker), 2, marker)
            self.assertEqual(
                patched.count("IF (im==p_qnc .AND. i==4 .AND. j==2 .AND. k==22)"),
                8,
            )
        self.assertEqual(sha256(SOURCE), SOURCE_SHA256)


if __name__ == "__main__":
    unittest.main()
