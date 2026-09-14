"""Private filesystem capability checks must preserve existing publications."""
from __future__ import annotations

import errno
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
import cloud_bal_transaction as publication


class FilesystemPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="filesystem-preflight-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "generations").mkdir()
        (self.root / "generations" / "existing").write_bytes(b"preserve publication")
        (self.root / "current").symlink_to("generations/existing")

    def assert_preserved(self):
        self.assertEqual(sorted(path.name for path in self.root.iterdir()), ["current", "generations"])
        self.assertEqual(os.readlink(self.root / "current"), "generations/existing")
        self.assertEqual((self.root / "current").read_bytes(), b"preserve publication")

    def test_real_primitives_and_cli_preserve_existing_publication(self):
        result = subprocess.run(
            [sys.executable, str(TOOLS / "cloud_bal_transaction.py"), "preflight", str(self.root)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(result.stdout)
        self.assertEqual(receipt["status"], "PASS")
        self.assertEqual(len(receipt["checks"]), 6)
        self.assert_preserved()

    def test_unsupported_no_replace_fails_closed(self):
        with mock.patch.object(publication, "_rename_noreplace", side_effect=publication.TransactionError("unsupported no-replace")):
            with self.assertRaisesRegex(publication.TransactionError, "unsupported no-replace"):
                publication.preflight_publication_filesystem(self.root)
        self.assert_preserved()

    def test_fsync_failure_fails_closed(self):
        with mock.patch.object(publication.os, "fsync", side_effect=OSError(errno.EIO, "injected fsync failure")):
            with self.assertRaises(publication.TransactionError):
                publication.preflight_publication_filesystem(self.root)
        self.assert_preserved()

    def test_ineffective_lock_fails_closed(self):
        with mock.patch.object(publication.fcntl, "flock"):
            with self.assertRaisesRegex(publication.TransactionError, "does not exclude"):
                publication.preflight_publication_filesystem(self.root)
        self.assert_preserved()

    def test_existing_target_overwrite_is_rejected(self):
        with mock.patch.object(publication, "_rename_noreplace", side_effect=os.replace):
            with self.assertRaisesRegex(publication.TransactionError, "overwrote"):
                publication.preflight_publication_filesystem(self.root)
        self.assert_preserved()

    def test_missing_and_symlink_roots_are_rejected(self):
        missing = self.root / "missing"
        with self.assertRaises(publication.TransactionError):
            publication.preflight_publication_filesystem(missing)
        self.assertFalse(missing.exists())
        link = self.root / "link"
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(publication.TransactionError):
            publication.preflight_publication_filesystem(link)
        link.unlink()
        self.assert_preserved()

    def test_symlink_layout_rejected_before_probe(self):
        link = self.root / ".staging"
        link.symlink_to(self.root / "generations", target_is_directory=True)
        with mock.patch.object(publication.tempfile, "TemporaryDirectory") as probe:
            with self.assertRaises(publication.TransactionError):
                publication.preflight_publication_filesystem(self.root)
            probe.assert_not_called()
        link.unlink()
        self.assert_preserved()

    def test_cross_device_layout_rejected_before_probe(self):
        identity = publication._directory_identity

        def different_device(path):
            value = identity(path)
            return [value[0] + 1, value[1]] if path.name == "generations" else value

        with mock.patch.object(publication, "_directory_identity", side_effect=different_device):
            with mock.patch.object(publication.tempfile, "TemporaryDirectory") as probe:
                with self.assertRaisesRegex(publication.TransactionError, "another filesystem"):
                    publication.preflight_publication_filesystem(self.root)
                probe.assert_not_called()
        self.assert_preserved()


if __name__ == "__main__":
    unittest.main()
