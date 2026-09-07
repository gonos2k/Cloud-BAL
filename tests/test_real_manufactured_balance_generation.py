#!/usr/bin/env python3
"""CLI path-boundary tests for the real manufactured-generation verifier."""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
VERIFIER_PATH = PROJECT / "tools/verify_real_manufactured_balance_generation.py"
spec = importlib.util.spec_from_file_location("real_manufactured_verifier", VERIFIER_PATH)
assert spec is not None and spec.loader is not None
verifier = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = verifier
spec.loader.exec_module(verifier)


class TestStrictCliPath(unittest.TestCase):
    def test_cloud_bal_cwd_repo_dot_matches_absolute_repo(self) -> None:
        previous = Path.cwd()
        try:
            os.chdir(PROJECT)
            self.assertEqual(
                verifier.strict_cli_path(Path("."), "repo"),
                verifier.strict_cli_path(PROJECT, "repo"),
            )
        finally:
            os.chdir(previous)

    def test_relative_path_is_absolute_and_canonical(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cloud-bal-path-") as directory:
            root = Path(directory)
            (root / "publication").mkdir()
            (root / "manifest").write_text("manifest\n", encoding="utf-8")
            (root / "repo").mkdir()
            (root / ".staging/transaction").mkdir(parents=True)

            previous = Path.cwd()
            try:
                os.chdir(root)
                self.assertEqual(
                    verifier.strict_cli_path(Path("publication"), "publication"),
                    root / "publication",
                )
                self.assertEqual(
                    verifier.strict_cli_path(Path("manifest"), "manifest"),
                    root / "manifest",
                )
                self.assertEqual(
                    verifier.strict_cli_path(Path("repo/."), "repo"),
                    root / "repo",
                )
                self.assertEqual(
                    verifier.strict_cli_path(Path(".staging/transaction"), "staging"),
                    root / ".staging/transaction",
                )
            finally:
                os.chdir(previous)

    def test_symlink_component_is_rejected_before_resolution(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cloud-bal-path-") as directory:
            root = Path(directory)
            target = root / "target"
            target.mkdir()
            (target / "manifest").write_text("manifest\n", encoding="utf-8")
            alias = root / "alias"
            alias.symlink_to(target, target_is_directory=True)

            with self.assertRaisesRegex(ValueError, "symlink"):
                verifier.strict_cli_path(alias / "manifest", "manifest")
            with self.assertRaisesRegex(ValueError, "symlink"):
                verifier.strict_cli_path(alias, "repo")
            with self.assertRaisesRegex(ValueError, "symlink"):
                verifier.strict_cli_path(alias / ".." / "target", "repo")

    def test_missing_path_is_rejected_strictly(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cloud-bal-path-") as directory:
            with self.assertRaisesRegex(ValueError, "strict existing path"):
                verifier.strict_cli_path(Path(directory) / "missing", "staging")


if __name__ == "__main__":
    unittest.main()
