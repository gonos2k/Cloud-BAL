#!/usr/bin/env python3
"""Hash-bound composition checks for PR71 KDM6 status routing."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSER_PATH = ROOT / "tools/pr71_compose_selected_kdm6.py"
SOURCE_PATH = Path("/var/tmp/pr68_velocity_native_20261007/source/module_mp_kdm6_combined_research.f90")
PROCESS_PATCH_PATH = ROOT / "docs/evidence/pr70_coupled_process_cutoff_search_20261008.patch"
SOURCE_SHA256 = "97e9892ff527a318f6266140eecc03238485a68b050c61bbaca7ea94f28bfdaa"
PROCESS_PATCH_SHA256 = "5f1b75925ec803838f5b3cfa81012336f4d21727073c5d8c0703fb70ddc37670"
COMPOSED_PR70_SHA256 = "487afbf064b6a3598ecb12248224fc3b91c77e1b0ed921d0e0e8130cacb9b583"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_composer():
    spec = importlib.util.spec_from_file_location("pr71_composer_tested", COMPOSER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load PR71 composer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ComposerTests(unittest.TestCase):
    source: Path
    validity_patch: Path
    expected_patch_sha256: str
    expected_composed_sha256: str

    @classmethod
    def setUpClass(cls):
        cls.composer = load_composer()
        if not cls.source.is_file() or not cls.validity_patch.is_file():
            raise unittest.SkipTest("frozen PR71 composition inputs are required")

    def test_frozen_same_source_composition(self):
        self.assertEqual(sha256(self.source.read_bytes()), SOURCE_SHA256)
        self.assertEqual(sha256(PROCESS_PATCH_PATH.read_bytes()), PROCESS_PATCH_SHA256)
        self.assertEqual(sha256(self.validity_patch.read_bytes()), self.expected_patch_sha256)
        with tempfile.TemporaryDirectory(prefix="pr71_composer_test_") as temporary:
            output = Path(temporary) / "composed_pr71.F"
            receipt = self.composer.compose(
                self.source, PROCESS_PATCH_PATH, self.validity_patch, output,
                self.expected_patch_sha256,
            )
            self.assertEqual(receipt["pr70_composed_source_sha256"], COMPOSED_PR70_SHA256)
            self.assertEqual(receipt["pr71_composed_source_sha256"], self.expected_composed_sha256)
            self.assertEqual(sha256(output.read_bytes()), self.expected_composed_sha256)
            self.assertEqual(
                receipt["pr70_density_routing_counts"],
                {
                    "gas_density_references": 11,
                    "dry_carrier_density_references_including_initialization": 64,
                    "intentional_raw_den_alias_references": 1,
                    "unresolved_qi0_retained": 1,
                },
            )
            source = output.read_text(encoding="utf-8")
            self.assertEqual(len(re.findall(r"\bcall\s+ProgB_param\b", source, re.I)), 7)
            self.assertEqual(len(re.findall(r"\bcall\s+slope_kdm6\b", source, re.I)), 7)
            self.assertEqual(source.count(",dgbgmug1,progb_status)"), 8)
            self.assertEqual(source.count("rslopegbmax,progb_status)"), 8)
            self.assertEqual(source.count("ProgB transient PSD state rejected"), 1)
            self.assertIn("progb_status(i,k) == PROGB_PSD_ACTIVE", source)
            self.assertIn("PROGB_ABSENT", source)

    def test_rejects_patch_hash_mismatch_before_writing(self):
        with tempfile.TemporaryDirectory(prefix="pr71_bad_patch_") as temporary:
            output = Path(temporary) / "must_not_exist.F"
            with self.assertRaisesRegex(SystemExit, "PR71 output-contract patch SHA-256 mismatch"):
                self.composer.compose(
                    self.source, PROCESS_PATCH_PATH, self.validity_patch, output,
                    "0" * 64,
                )
            self.assertFalse(output.exists())

    def test_rejects_source_hash_mismatch_before_writing(self):
        with tempfile.TemporaryDirectory(prefix="pr71_bad_source_") as temporary:
            source = Path(temporary) / "altered.f90"
            source.write_bytes(self.source.read_bytes() + b"\n! changed\n")
            output = Path(temporary) / "must_not_exist.F"
            with self.assertRaisesRegex(SystemExit, "PR70 selected source SHA-256 mismatch"):
                self.composer.compose(
                    source, PROCESS_PATCH_PATH, self.validity_patch, output,
                    self.expected_patch_sha256,
                )
            self.assertFalse(output.exists())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=SOURCE_PATH)
    parser.add_argument("--validity-patch", type=Path, required=True)
    parser.add_argument("--expected-validity-patch-sha256", required=True)
    parser.add_argument("--expected-composed-source-sha256", required=True)
    args = parser.parse_args()
    ComposerTests.source = args.source
    ComposerTests.validity_patch = args.validity_patch
    ComposerTests.expected_patch_sha256 = args.expected_validity_patch_sha256
    ComposerTests.expected_composed_sha256 = args.expected_composed_source_sha256
    unittest.main(argv=["test_pr71_composer.py"], verbosity=2)


if __name__ == "__main__":
    main()
