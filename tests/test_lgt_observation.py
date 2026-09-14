#!/usr/bin/env python3
"""Focused E01 checks for the declared original LGT observation bytes."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = REPO_ROOT.parent
SPEC_PATH = REPO_ROOT / "tests/original_upstream_replay_20260816.json"
TOOL_PATH = REPO_ROOT / "tools/original_upstream_replay.py"
MODULE_SPEC = importlib.util.spec_from_file_location("original_replay", TOOL_PATH)
assert MODULE_SPEC is not None and MODULE_SPEC.loader is not None
REPLAY = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(REPLAY)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class LightningObservationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
        cls.contract = cls.spec["lightning_contract"]
        cls.declarations = cls.spec["lightning_observations"]

    def test_real_four_case_lgt_is_hash_bound_and_content_validated(self) -> None:
        for case_id, _, stamp in REPLAY.EXPECTED_CASES:
            with self.subTest(case_id=case_id):
                row = {"laps_stamp": stamp}
                receipt, source, findings = REPLAY.audit_lightning_observation(
                    WORKSPACE, row, self.declarations[case_id], self.contract
                )
                self.assertEqual(findings, [])
                self.assertEqual(receipt["status"], "PASS")
                self.assertEqual(receipt["content_validation"], "PASS")
                self.assertEqual(receipt["line_count"], 235 * 283)
                self.assertEqual(receipt["grid_nx"], 235)
                self.assertEqual(receipt["grid_ny"], 283)
                self.assertEqual(receipt["coordinate_order"], "i_outer_j_inner")
                self.assertEqual(receipt["count_missing"], 1032)
                self.assertEqual(
                    receipt["count_zero"], self.declarations[case_id]["expected_counts"]["zero"]
                )
                self.assertEqual(
                    receipt["count_positive"], self.declarations[case_id]["expected_counts"]["positive"]
                )
                self.assertIsNotNone(source)
                self.assertEqual(receipt["sha256"], receipt["expected_sha256"])

    def test_lgt_materializes_to_legacy_reader_path_with_same_hash(self) -> None:
        case_id, valid_time, stamp = REPLAY.EXPECTED_CASES[0]
        row = {"case_id": case_id, "valid_time_utc": valid_time, "laps_stamp": stamp}
        receipt, source, findings = REPLAY.audit_lightning_observation(
            WORKSPACE, row, self.declarations[case_id], self.contract
        )
        self.assertFalse(findings)
        assert source is not None
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / "scratch") as temporary:
            output_root = Path(temporary)
            result = REPLAY.materialize_case_runtime(
                output_root, row, [], input_sources=[(receipt, source)]
            )
            self.assertEqual(result["status"], "PARTIAL")
            destination = (
                output_root
                / "cases"
                / case_id
                / "runtime"
                / "lapsprd/lgt"
                / source.name
            )
            self.assertEqual(destination.read_bytes(), source.read_bytes())
            self.assertEqual(sha256_bytes(destination.read_bytes()), receipt["expected_sha256"])
            self.assertEqual(destination.stat().st_mode & 0o222, 0)

    def _portable_case(
        self, payload: bytes, *, declaration_path: str | None = None
    ) -> tuple[tempfile.TemporaryDirectory[str], Path, dict[str, str], dict[str, object]]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        relative = f"{REPLAY.LIGHTNING_ALLOWED_ROOT}/262281200.lgt"
        source = root / relative
        source.parent.mkdir(parents=True)
        source.write_bytes(payload)
        declaration = dict(self.declarations["20260816T120000Z"])
        declaration["path"] = declaration_path or relative
        declaration["sha256"] = sha256_bytes(payload)
        return temporary, root, {"laps_stamp": "262281200"}, declaration

    def _assert_rejected(self, payload: bytes, expected_finding: str) -> None:
        actual = (
            WORKSPACE
            / self.declarations["20260816T120000Z"]["path"]
        ).read_bytes()
        temporary, root, row, declaration = self._portable_case(payload)
        try:
            receipt, source, findings = REPLAY.audit_lightning_observation(
                root, row, declaration, self.contract
            )
            self.assertIsNone(source)
            self.assertEqual(receipt["status"], "BLOCKED")
            self.assertIn(expected_finding, findings)
        finally:
            temporary.cleanup()
        self.assertEqual(actual, (
            WORKSPACE / self.declarations["20260816T120000Z"]["path"]
        ).read_bytes())

    def test_truncated_fixed_record_is_rejected(self) -> None:
        source = WORKSPACE / self.declarations["20260816T120000Z"]["path"]
        self._assert_rejected(source.read_bytes()[:-1], "LIGHTNING_FIXED_LINE_INVALID:66505")

    def test_malformed_negative_other_than_missing_value_is_rejected(self) -> None:
        source = WORKSPACE / self.declarations["20260816T120000Z"]["path"]
        payload = bytearray(source.read_bytes())
        payload[18:26] = b"     -98"
        self._assert_rejected(bytes(payload), "LIGHTNING_NEGATIVE_VALUE_DISALLOWED:1")

    def test_coordinate_order_and_non_ascii_are_rejected(self) -> None:
        source = WORKSPACE / self.declarations["20260816T120000Z"]["path"]
        coordinate = bytearray(source.read_bytes())
        coordinate[1:9] = b"       2"
        self._assert_rejected(bytes(coordinate), "LIGHTNING_COORDINATE_ORDER_INVALID:1")

        non_ascii = bytearray(source.read_bytes())
        non_ascii[18] = 0xFF
        self._assert_rejected(bytes(non_ascii), "LIGHTNING_NON_ASCII_BYTES")

    def test_bad_hash_wrong_path_and_symlink_are_rejected(self) -> None:
        source = WORKSPACE / self.declarations["20260816T120000Z"]["path"]
        payload = source.read_bytes()
        temporary, root, row, declaration = self._portable_case(payload)
        try:
            declaration["sha256"] = "0" * 64
            receipt, materialized, findings = REPLAY.audit_lightning_observation(
                root, row, declaration, self.contract
            )
            self.assertIsNone(materialized)
            self.assertIn("SOURCE_SHA256_MISMATCH:lgt", findings)
            self.assertEqual(receipt["content_validation"], "NOT_RUN_HASH_MISMATCH")
        finally:
            temporary.cleanup()

        wrong_path = "ANAL/NE57/DAOU/00/lapsprd/lgt/262281300.lgt"
        temporary, root, row, declaration = self._portable_case(payload, declaration_path=wrong_path)
        try:
            _, materialized, findings = REPLAY.audit_lightning_observation(
                root, row, declaration, self.contract
            )
            self.assertIsNone(materialized)
            self.assertIn("LIGHTNING_OBSERVATION_PATH_MISMATCH", findings)
        finally:
            temporary.cleanup()

        temporary, root, row, declaration = self._portable_case(payload)
        try:
            expected = root / declaration["path"]
            outside = root / "outside.lgt"
            outside.write_bytes(payload)
            expected.unlink()
            expected.symlink_to(outside)
            _, materialized, findings = REPLAY.audit_lightning_observation(
                root, row, declaration, self.contract
            )
            self.assertIsNone(materialized)
            self.assertIn("SOURCE_PATH_CONTAINS_SYMLINK:lgt", findings)
        finally:
            temporary.cleanup()


if __name__ == "__main__":
    unittest.main()
