from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("/NHNHOME/WORKSPACE/26weather002_A/yhlee/KIM-meso/KIM_RDPS_MODL_V2026.2/dyn_em/module_em.F")
SOURCE_SHA256 = "7695bfb05a7f99763334a6e69523bbcc1de0f2c659177a18c10a6e1cf530a0c7"
PATCH = ROOT / "patches/pr83_rk_operands_trace.patch"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestRKOperandsPatchNative(unittest.TestCase):
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

