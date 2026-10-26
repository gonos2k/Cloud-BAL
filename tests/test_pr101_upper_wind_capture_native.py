from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import test_pr101_upper_wind_capture as base
c2_build_assets_available = base.c2_build_assets_available


class TestPR101UpperWindCaptureNative(unittest.TestCase):
    @unittest.skipUnless(base.SOURCE.is_file(), "requires retained C2 module_em.F source asset")
    def test_transforms_receipt_pinned_c2_source_at_both_native_calls(self):
        raw = base.SOURCE.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), base.C2_MODULE_EM_SHA256)
        helper = (base.ROOT / "tools/pr101_upper_wind_capture.F90").read_text()
        result = base.transform(raw.decode(), helper)
        self.assertEqual(result.count("CALL pr101_capture_upper_wind('u', 1"), 1)
        self.assertEqual(result.count("CALL pr101_capture_upper_wind('u', 2"), 1)
        self.assertEqual(result.count("CALL pr101_capture_upper_wind('v', 1"), 1)
        self.assertEqual(result.count("CALL pr101_capture_upper_wind('v', 2"), 1)
        self.assertEqual(result.count("\nMODULE pr101_upper_wind_capture\n"), 1)
        self.assertEqual(result.count("USE pr101_upper_wind_capture, ONLY:"), 1)
        self.assertIn("CONVERT='BIG_ENDIAN'", helper)


    @unittest.skipUnless(c2_build_assets_available(),
                         "requires retained C2 source overrides and base build receipt")
    def test_build_plan_replaces_only_module_em_and_does_not_build(self):
        raw = base.SOURCE.read_bytes()
        helper = (base.ROOT / "tools/pr101_upper_wind_capture.F90").read_text()
        with tempfile.TemporaryDirectory() as directory:
            transformed = Path(directory) / "module_em.F"
            transformed.write_text(base.transform(raw.decode(), helper))
            scratch = Path(directory) / "fresh_build"
            plan = base.make_plan(transformed, scratch)
        self.assertFalse(scratch.exists())
        self.assertEqual(len(plan["source_overrides"]), 9)
        self.assertEqual(plan["source_overrides"]["module_em.o"], str(transformed.resolve()))
        self.assertIn("--reproduction-profile", plan["builder_argv"])
