#!/usr/bin/env python3
"""Focused schema and receipt tests for the PR64 QC source-channel replay."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

spec = importlib.util.spec_from_file_location("pr64_qc_channel_replay", TOOLS / "pr64_qc_channel_replay.py")
assert spec is not None and spec.loader is not None
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)

HEADER = "QCCHAN rkstep i j k bl_pbl cu shcu diff_opt km_opt qc_moist_tend rqcblten rqccuten rqcshten rqcncuten rqcnshten"
VALID_ROW = "QCCHAN 1 172 76 1 11 37 0 1 4 2.4263537488877773E-03 2.4263537488877773E-03 0 0 0 0"


def state_stages() -> str:
    rows = [
        ("PRE_RK", 0, 0.0, 0.0),
        ("RK_STAGE_END", 1, 1.6839790e-7, -1773.7578125),
        ("RK_STAGE_END", 2, 2.5137101e-7, -3662.8056641),
        ("RK_STAGE_END", 3, 5.0365270e-7, 0.0),
        ("PRE_MOIST_PREP", 4, 5.0365270e-7, 0.0),
        ("POST_MOIST_PREP", 4, 5.0365270e-7, 0.0),
        ("PRE_MICROPHYSICS", 4, 5.0365270e-7, 0.0),
        ("POST_MICROPHYSICS", 4, 3.0767936e-7, 0.0),
    ]
    return "".join(
        f"STATE_STAGE {name} 1 {step} 100 0 0 1.0e-15 -1.0e-7 {qc:.16e} {nc:.16e} 0.0 0.0\n"
        for name, step, qc, nc in rows
    )


class QcChannelParserTests(unittest.TestCase):
    def read_text(self, text: str) -> dict[str, float | int]:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "channels.raw"
            path.write_text(text)
            return replay.read_qc_channel(path)

    def test_actual_format_positive_pbl_channel(self) -> None:
        row = self.read_text(HEADER + "\n" + VALID_ROW + "\n")
        self.assertEqual(row["qc_moist_tend"], row["rqcblten"])
        self.assertGreater(row["rqcblten"], 0.0)
        self.assertEqual(row["rqccuten"], 0.0)

    def test_rejects_empty_or_wrong_header(self) -> None:
        for text in ("", "QCCHAN\n" + VALID_ROW + "\n", HEADER.replace("rqcblten", "wrong") + "\n" + VALID_ROW + "\n"):
            with self.subTest(text=text[:30]), self.assertRaises(ValueError):
                self.read_text(text)

    def test_rejects_nonfinite_numeric_value(self) -> None:
        row = VALID_ROW.replace("2.4263537488877773E-03", "Infinity", 1)
        with self.assertRaisesRegex(ValueError, "non-finite"):
            self.read_text(HEADER + "\n" + row + "\n")

    def test_rejects_missing_or_duplicate_target_rows(self) -> None:
        non_target = VALID_ROW.replace("172 76 1", "171 76 1")
        with self.assertRaisesRegex(ValueError, "found 0"):
            self.read_text(HEADER + "\n" + non_target + "\n")
        with self.assertRaisesRegex(ValueError, "found 2"):
            self.read_text(HEADER + "\n" + VALID_ROW + "\n" + VALID_ROW + "\n")


class QcChannelReceiptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.observer = self.root / "observer"
        self.baseline = self.root / "baseline"
        self.observer.mkdir()
        self.baseline.mkdir()
        common = state_stages()
        for name in replay.MATCHED_OUTPUTS:
            contents = common if name == "pr63_transition_stages.raw" else f"fixture:{name}\n"
            (self.observer / name).write_text(contents)
            (self.baseline / name).write_text(contents)
        (self.observer / "pr64_qc_channels.raw").write_text(HEADER + "\n" + VALID_ROW + "\n")
        records = []
        for path in [*(self.observer / name for name in replay.MATCHED_OUTPUTS), self.observer / "pr64_qc_channels.raw"]:
            records.append({"path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        receipt = {
            "returncode": 0,
            "input_integrity": "PASS",
            "output_isolation": "PASS",
            "changed_inputs": [],
            "input_read_issues": [],
            "output_issues": [],
            "inputs": [],
            "outputs": records,
        }
        (self.observer / "run-isolation.json").write_text(json.dumps(receipt))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def receipt(self) -> dict:
        path = self.observer / "run-isolation.json"
        return json.loads(path.read_text())

    def write_receipt(self, receipt: dict) -> None:
        (self.observer / "run-isolation.json").write_text(json.dumps(receipt))

    def test_valid_fixture_passes_and_checks_all_declared_hashes(self) -> None:
        result = replay.validate(self.observer, self.baseline)
        self.assertTrue(result["selected_cell_stages_match"])
        self.assertEqual(result["qc_channel"]["rqcblten"], result["qc_channel"]["qc_moist_tend"])

    def test_zero_pbl_tendency_is_not_a_source_pass(self) -> None:
        zero_row = VALID_ROW.replace("2.4263537488877773E-03", "0.0")
        (self.observer / "pr64_qc_channels.raw").write_text(HEADER + "\n" + zero_row + "\n")
        receipt = self.receipt()
        for record in receipt["outputs"]:
            if record["path"] == "pr64_qc_channels.raw":
                record["sha256"] = hashlib.sha256((self.observer / record["path"]).read_bytes()).hexdigest()
        self.write_receipt(receipt)
        with self.assertRaisesRegex(ValueError, "not positive"):
            replay.validate(self.observer, self.baseline)

    def test_missing_receipt_artifact_is_rejected(self) -> None:
        receipt = self.receipt()
        receipt["outputs"] = [record for record in receipt["outputs"] if record["path"] != "candidate_run.log"]
        self.write_receipt(receipt)
        with self.assertRaisesRegex(ValueError, "omits required"):
            replay.validate(self.observer, self.baseline)

    def test_receipt_hash_mismatch_is_rejected(self) -> None:
        receipt = self.receipt()
        next(record for record in receipt["outputs"] if record["path"] == "namelist.output")["sha256"] = "0" * 64
        self.write_receipt(receipt)
        with self.assertRaisesRegex(ValueError, "differs from receipt"):
            replay.validate(self.observer, self.baseline)


if __name__ == "__main__":
    unittest.main()
