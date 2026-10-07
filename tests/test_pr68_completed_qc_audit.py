"""Focused guards for completed-QC boundary evidence parsing."""
from __future__ import annotations

import importlib.util
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "pr68_completed_qc_audit", ROOT / "tools" / "pr68_completed_qc_audit.py")
assert spec is not None and spec.loader is not None
audit = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = audit
spec.loader.exec_module(audit)


class CompletedQcAuditTests(unittest.TestCase):
    def test_input_inventory_rejects_duplicate_escape_and_bad_digest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "run"
            root.mkdir()
            (root / "sub").mkdir()
            source = root / "input.bin"
            source.write_bytes(b"input")
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            row = {"path": str(source), "sha256_before": digest, "sha256_after": digest}
            self.assertEqual(audit.validate_input_inventory(root, [row]), {"input.bin": source.resolve()})
            duplicate = dict(row, path=str(root / "sub" / ".." / "input.bin"))
            with self.assertRaisesRegex(ValueError, "duplicate normalized path"):
                audit.validate_input_inventory(root, [row, duplicate])
            outside = Path(tmp) / "outside.bin"
            outside.write_bytes(b"outside")
            outside_hash = hashlib.sha256(outside.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError, "escapes its root"):
                audit.validate_input_inventory(root, [dict(row, path=str(outside),
                    sha256_before=outside_hash, sha256_after=outside_hash)])
            with self.assertRaisesRegex(ValueError, "malformed paths or SHA256"):
                audit.validate_input_inventory(root, [dict(row, sha256_before="short")])
            with self.assertRaisesRegex(ValueError, "malformed paths or SHA256"):
                audit.validate_input_inventory(root, [dict(row, sha256_after="0" * 64)])


    def test_target_coordinates_reject_duplicates_and_missing_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "coords.txt"
            path.write_text("2\n2 3 4\n2 3 4\n", encoding="ascii")
            with self.assertRaisesRegex(ValueError, "duplicate, malformed, or missing"):
                audit.read_targets(path)

    def test_stage_reader_checks_unique_target_keys_and_float32_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "stages.raw"
            target = {(2, 3, 4)}
            row = "QC_STAGE RK_TEND_PRE 1 2 3 4 1.0000000000000000E+00 2.0000000000000000E+00\n"
            path.write_text(row + row, encoding="ascii")
            with self.assertRaisesRegex(ValueError, "duplicate stage key"):
                audit.read_stages(path, target)
            path.write_text(row, encoding="ascii")
            parsed = audit.read_stages(path, target)
            self.assertEqual(parsed["RK_TEND_PRE"][(1, (2, 3, 4))],
                             (np.float32(1), np.float32(2)))

    def test_keyed_binary32_equality_rejects_value_or_key_changes(self) -> None:
        key = (1, (2, 3, 4))
        self.assertEqual(audit.keyed_equal({key: np.array([1], dtype=np.float32)},
                                           {key: np.array([1], dtype=np.float32)}, "test"), 1)
        with self.assertRaisesRegex(ValueError, "values differ"):
            audit.keyed_equal({key: np.array([1], dtype=np.float32)},
                              {key: np.array([2], dtype=np.float32)}, "test")

    def test_increment_summary_reports_binary32_signs_and_extent(self) -> None:
        result = audit.increment_stats([np.float32(-2), np.float32(0), np.float32(3)])
        self.assertEqual(result["signs"], {"negative": 1, "positive": 1, "zero": 1})
        self.assertEqual((result["min"], result["max"]), (-2.0, 3.0))


if __name__ == "__main__":
    unittest.main()
