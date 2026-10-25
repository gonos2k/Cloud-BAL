from pathlib import Path
import hashlib
import json
import sys
import unittest
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("/var/tmp/pr99-c2-source.2n00oy19/module_em.F")
sys.path.insert(0, str(ROOT / "tools"))
from pr101_upper_wind_capture import C2_MODULE_EM_SHA256, transform  # noqa: E402
from pr101_upper_wind_build_plan import BASE_RECEIPT, make_plan  # noqa: E402


def c2_build_assets_available():
    try:
        receipt = json.loads(BASE_RECEIPT.read_text())
        sources = [Path(row["requested_path"]) for member, row in receipt["source_overrides"].items()
                   if member != "module_em.o"]
        sources.append(Path(receipt["extra_observer"]["requested_source_path"]))
        return SOURCE.is_file() and all(path.is_file() for path in sources)
    except (OSError, KeyError, json.JSONDecodeError):
        return False


class UpperWindCaptureTransformTest(unittest.TestCase):
    @unittest.skipUnless(SOURCE.is_file(), "requires retained C2 module_em.F source asset")
    def test_transforms_receipt_pinned_c2_source_at_both_native_calls(self):
        raw = SOURCE.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), C2_MODULE_EM_SHA256)
        helper = (ROOT / "tools/pr101_upper_wind_capture.F90").read_text()
        result = transform(raw.decode(), helper)
        self.assertEqual(result.count("CALL pr101_capture_upper_wind('u', 1"), 1)
        self.assertEqual(result.count("CALL pr101_capture_upper_wind('u', 2"), 1)
        self.assertEqual(result.count("CALL pr101_capture_upper_wind('v', 1"), 1)
        self.assertEqual(result.count("CALL pr101_capture_upper_wind('v', 2"), 1)
        self.assertEqual(result.count("\nMODULE pr101_upper_wind_capture\n"), 1)
        self.assertEqual(result.count("USE pr101_upper_wind_capture, ONLY:"), 1)
        self.assertIn("CONVERT='BIG_ENDIAN'", helper)

    def test_rejects_sources_without_exact_call_anchors(self):
        helper = (ROOT / "tools/pr101_upper_wind_capture.F90").read_text()
        with self.assertRaisesRegex(ValueError, "MODULE module_em"):
            transform("MODULE other\n", helper)

    def test_rejects_double_application(self):
        helper = (ROOT / "tools/pr101_upper_wind_capture.F90").read_text()
        with self.assertRaisesRegex(ValueError, "already has"):
            transform("MODULE pr101_upper_wind_capture\n", helper)

    @unittest.skipUnless(c2_build_assets_available(),
                         "requires retained C2 source overrides and base build receipt")
    def test_build_plan_replaces_only_module_em_and_does_not_build(self):
        raw = SOURCE.read_bytes()
        helper = (ROOT / "tools/pr101_upper_wind_capture.F90").read_text()
        with tempfile.TemporaryDirectory() as directory:
            transformed = Path(directory) / "module_em.F"
            transformed.write_text(transform(raw.decode(), helper))
            scratch = Path(directory) / "fresh_build"
            plan = make_plan(transformed, scratch)
        self.assertFalse(scratch.exists())
        self.assertEqual(len(plan["source_overrides"]), 9)
        self.assertEqual(plan["source_overrides"]["module_em.o"], str(transformed.resolve()))
        self.assertIn("--reproduction-profile", plan["builder_argv"])


if __name__ == "__main__":
    unittest.main()
