#!/usr/bin/env python3
"""Focused source/hash and DEN-role checks for the PR70 composition."""

from __future__ import annotations

import hashlib
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSER_PATH = ROOT / "tools/pr70_compose_selected_kdm6.py"
SOURCE_PATH = Path(os.environ.get(
    "PR70_KDM6_SOURCE",
    "/var/tmp/pr68_velocity_native_20261007/source/module_mp_kdm6_combined_research.f90",
))
PATCH_PATH = ROOT / "docs/evidence/pr70_coupled_process_cutoff_search_20261008.patch"
PATCH_SHA256 = "5f1b75925ec803838f5b3cfa81012336f4d21727073c5d8c0703fb70ddc37670"
SOURCE_SHA256 = "97e9892ff527a318f6266140eecc03238485a68b050c61bbaca7ea94f28bfdaa"
PROCESS_SHA256 = "513804fa340db3011017ec21b7a0678d41b82875087625bfc2e8993e7f3e4692"
COMPOSED_SHA256 = "487afbf064b6a3598ecb12248224fc3b91c77e1b0ed921d0e0e8130cacb9b583"


def load_composer():
    spec = importlib.util.spec_from_file_location("pr70_composer_tested", COMPOSER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load PR70 composer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class CompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SOURCE_PATH.is_file():
            raise unittest.SkipTest(f"captured source required for source-bound tests: {SOURCE_PATH}")
        cls.composer = load_composer()
        cls.transformer = cls.composer.load_unit_transformer()
        cls.composer.extend_density_role_profile(cls.transformer)
        cls.source = SOURCE_PATH.read_text()
        cls.patch_bytes = PATCH_PATH.read_bytes()

    def test_frozen_hashes_roles_and_whole_module_binding(self):
        self.assertEqual(digest(SOURCE_PATH.read_bytes()), SOURCE_SHA256)
        self.assertEqual(digest(self.patch_bytes), PATCH_SHA256)
        original_records = self.composer.inventory_all_density_uses(
            self.source, self.transformer
        )
        self.assertEqual(sum(record["references"] for record in original_records), 71)
        records = self.composer.inventory_all_density_uses(
            self.apply_process_patch(), self.transformer
        )
        self.assertEqual(sum(record["references"] for record in records), 73)
        role_counts = {}
        for record in records:
            role_counts[record["role"]] = role_counts.get(record["role"], 0) + record["references"]
        self.assertEqual(role_counts.get("dry_number_to_mass_process_gate"), 2)
        self.assertEqual(role_counts.get("unresolved_ice_threshold"), 2)

        with tempfile.TemporaryDirectory(prefix="pr70_composer_test_") as temp:
            output = Path(temp) / "composed.f90"
            receipt = self.composer.compose(
                SOURCE_PATH, PATCH_PATH, output, PATCH_SHA256
            )
            composed = output.read_bytes()
            self.assertEqual(receipt["process_patched_source_sha256"], PROCESS_SHA256)
            self.assertEqual(receipt["composed_source_sha256"], COMPOSED_SHA256)
            self.assertEqual(digest(composed), COMPOSED_SHA256)
            self.assertEqual(
                receipt["routing_counts"],
                {
                    "gas_density_references": 11,
                    "dry_carrier_density_references_including_initialization": 64,
                    "intentional_raw_den_alias_references": 1,
                    "unresolved_qi0_retained": 1,
                },
            )
            text = composed.decode()
            self.assertIn("subroutine kdm6_rain_process_fraction", text)
            self.assertIn("rain_process_search_status", text)
            self.assertIn("gas_density = den(its:ite,kts:kte)", text)
            self.assertIn("dry_carrier_density", text)
            self.assertIn("if (t_trial.le.0.0)", text)
            self.assertIn("if (temperature.le.0.0) return", text)

    def test_rejects_selected_source_hash_mismatch(self):
        with tempfile.TemporaryDirectory(prefix="pr70_bad_source_") as temp:
            source = Path(temp) / "source.f90"
            source.write_bytes(SOURCE_PATH.read_bytes() + b"\n! altered\n")
            with self.assertRaisesRegex(SystemExit, "selected source SHA-256 mismatch"):
                self.composer.compose(source, PATCH_PATH, Path(temp) / "out.f90", PATCH_SHA256)

    def test_rejects_process_patch_hash_mismatch(self):
        with tempfile.TemporaryDirectory(prefix="pr70_bad_patch_") as temp:
            with self.assertRaisesRegex(SystemExit, "PR70 process patch SHA-256 mismatch"):
                self.composer.compose(
                    SOURCE_PATH, PATCH_PATH, Path(temp) / "out.f90", "0" * 64
                )

    def test_rejects_unrouted_den_use(self):
        processed = self.apply_process_patch()
        start, _ = self.composer.kdm62d_bounds(processed)
        insertion = start + processed[start:].index("\n") + 1
        contaminated = processed[:insertion] + "   call unsupported_role(den(i,k))\n" + processed[insertion:]
        with self.assertRaisesRegex(SystemExit, "unclassified DEN reference"):
            self.composer.inventory_all_density_uses(contaminated, self.transformer)

    def apply_process_patch(self) -> str:
        with tempfile.TemporaryDirectory(prefix="pr70_patch_test_") as temp:
            directory = Path(temp)
            source = directory / SOURCE_PATH.name
            source.write_bytes(SOURCE_PATH.read_bytes())
            import subprocess

            result = subprocess.run(
                ["patch", "--fuzz=0", "-p0", "-d", str(directory)],
                input=self.patch_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout.decode(errors="replace"))
            return source.read_text()


if __name__ == "__main__":
    unittest.main(verbosity=2)
