#!/usr/bin/env python3
"""CLI path-boundary tests for the real manufactured-generation verifier."""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


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

    def test_workspace_root_uses_configured_original_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cloud-bal-workspace-") as directory:
            workspace = Path(directory)
            with patch.dict(
                os.environ, {"CLOUD_BAL_WORKSPACE_ROOT": str(workspace)}
            ):
                self.assertEqual(
                    verifier.resolve_workspace_root(Path("/unused/repo")),
                    workspace,
                )

    def test_workspace_root_rejects_symlink_component(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cloud-bal-workspace-") as directory:
            root = Path(directory)
            target = root / "target"
            target.mkdir()
            alias = root / "alias"
            alias.symlink_to(target, target_is_directory=True)
            with patch.dict(
                os.environ, {"CLOUD_BAL_WORKSPACE_ROOT": str(alias)}
            ):
                with self.assertRaisesRegex(ValueError, "workspace root.*symlink"):
                    verifier.resolve_workspace_root(Path("/unused/repo"))

    def test_workspace_root_rejects_missing_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cloud-bal-workspace-") as directory:
            missing = Path(directory) / "missing"
            with patch.dict(
                os.environ, {"CLOUD_BAL_WORKSPACE_ROOT": str(missing)}
            ):
                with self.assertRaisesRegex(
                    ValueError, "workspace root.*strict existing path"
                ):
                    verifier.resolve_workspace_root(Path("/unused/repo"))

    def test_workspace_root_rejects_regular_file(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cloud-bal-workspace-") as directory:
            workspace_file = Path(directory) / "workspace-file"
            workspace_file.write_text("not a workspace\n", encoding="utf-8")
            with patch.dict(
                os.environ, {"CLOUD_BAL_WORKSPACE_ROOT": str(workspace_file)}
            ):
                with self.assertRaisesRegex(
                    ValueError, "workspace root is not a directory"
                ):
                    verifier.resolve_workspace_root(Path("/unused/repo"))

    def test_snapshot_validation_returns_explicit_product_binding(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cloud-bal-snapshot-") as directory:
            snapshot = Path(directory) / ".snapshots" / "candidate"
            snapshot.mkdir(parents=True)
            (snapshot / "TRANSACTION.json").write_text(
                '{"transaction_id":"candidate","products":["product"]}\n',
                encoding="utf-8",
            )
            (snapshot / "product").write_bytes(b"validated")
            with patch.object(verifier, "source_identity", return_value="head"):
                with patch.object(verifier, "reviewed_cases", return_value=[]):
                    with patch.object(verifier, "verify_bundle") as verify_bundle:
                        receipt = verifier.verify_snapshot(snapshot, Path("manifest"), Path("repo"))
            verify_bundle.assert_called_once()
            self.assertEqual(receipt["status"], "PASS")
            self.assertEqual(receipt["transaction_id"], "candidate")
            self.assertEqual(receipt["products"][0]["sha256"], verifier.sha256(snapshot / "product"))

    def test_snapshot_validation_rejects_mutable_staging_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cloud-bal-snapshot-") as directory:
            staging = Path(directory) / ".staging" / "candidate"
            staging.mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, "detached snapshot"):
                verifier.verify_snapshot(staging, Path("manifest"), Path("repo"))


if __name__ == "__main__":
    unittest.main()
