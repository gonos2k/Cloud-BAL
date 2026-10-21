from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import pr95_closed_results as queue  # noqa: E402


class ReceiptQueueTests(unittest.TestCase):
    def test_wait_rejects_missing_malformed_and_unfinalized_receipts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(queue.ClosedResultsError, "timed out"):
                queue.wait_for_receipt(root, "OFF", 0)
            (root / "receipt.json").write_text("{")
            with self.assertRaisesRegex(queue.ClosedResultsError, "malformed"):
                queue.wait_for_receipt(root, "OFF", 0)
            (root / "receipt.json").write_text(json.dumps({"status": "RUNNING"}))
            with self.assertRaisesRegex(queue.ClosedResultsError, "timed out"):
                queue.wait_for_receipt(root, "OFF", 0)

    def test_wait_uses_frozen_closed_receipt_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt = {"arm": "OFF", "status": "COMPLETE", "snapshots": {},
                       "compressed_outputs": [], "processing_errors": []}
            (root / "receipt.json").write_text(json.dumps(receipt))
            loaded, path = queue.wait_for_receipt(root, "OFF", 0)
            self.assertEqual(loaded["status"], "COMPLETE")
            self.assertEqual(path, root / "receipt.json")

    def test_reader_pin_mutation_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "reader.py"
            source.write_text("pinned")
            pin = hashlib.sha256(source.read_bytes()).hexdigest()
            self.assertEqual(queue.verify_source_pins(root, {"reader.py": pin}), {"reader.py": pin})
            source.write_text("changed")
            with self.assertRaisesRegex(queue.ClosedResultsError, "dependency changed"):
                queue.verify_source_pins(root, {"reader.py": pin})

    def test_closed_history_uses_existing_trace_result_and_runtime_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            compact, baseline = temp / "compact", temp / "baseline"
            compact.mkdir(); baseline.mkdir()
            compact_receipt = {"arm": "OFF", "status": "COMPLETE", "snapshots": {},
                               "compressed_outputs": [], "processing_errors": []}
            baseline_receipt = {**compact_receipt}
            (compact / "receipt.json").write_text(json.dumps(compact_receipt))
            (baseline / "receipt.json").write_text(json.dumps(baseline_receipt))
            compact_hash = queue.sha256(compact / "receipt.json")
            baseline_hash = queue.sha256(baseline / "receipt.json")
            old_path = temp / "old_audit.json"
            old = {"schema": "pr94_compact_longrun_audit_v1", "arm": "OFF",
                   "requested_duration_seconds": 3600,
                   "runtime": {"receipt_path": str(compact / "receipt.json"),
                               "receipt_sha256": compact_hash,
                               "baseline_receipt_path": str(baseline / "receipt.json"),
                               "baseline_receipt_sha256": baseline_hash,
                               "duration_complete": True},
                   "runtime_binding": {"status": "PASS"},
                   "compact_profile": {"status": "PASS"},
                   "first_600_seconds_baseline_comparison": {"status": "PASS"},
                   "generic_completed_state_audit": {"status": "PASS"},
                   "exact_source_endpoint_audit": {"status": "FAIL"},
                   "active_ice_policy_split": {"status": "PASS"}}
            old_path.write_text(json.dumps(old))
            with patch.object(queue.longrun, "_verify_runtime_bindings", return_value={"status": "PASS"}) as binding, \
                 patch.object(queue.longrun, "compare_closed_histories", return_value={"status": "PASS"}) as compare, \
                 patch.object(queue.longrun.frozen, "_trace_records", side_effect=AssertionError("trace audit rerun")):
                result = queue._closed_arm_result(
                    "OFF", 3600, compact, {**compact_receipt}, compact / "receipt.json",
                    baseline, {**baseline_receipt}, baseline / "receipt.json", old_path, 0, 0)
            self.assertEqual(result["trace_audit"]["trace_status"]["exact_source_endpoint_audit"], "FAIL")
            self.assertEqual(result["history_comparison"]["status"], "PASS")
            binding.assert_called_once()
            compare.assert_called_once()

    def test_incomplete_hydro_is_an_explicit_skip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt = {"arm": "HYDRO", "status": "INCOMPLETE", "snapshots": {},
                       "compressed_outputs": [], "processing_errors": [],
                       "returncode": 128, "final_completed_step": 25,
                       "runner_timestep_seconds": 20}
            (root / "receipt.json").write_text(json.dumps(receipt))
            result = queue._hydro_skip(root, 0, 0)
        self.assertEqual(result["status"], "SKIP")
        self.assertEqual(result["completed_seconds"], 500)
        self.assertEqual(result["returncode"], 128)
        self.assertEqual(result["normal_600_second_response"], "NOT_RUN")


if __name__ == "__main__":
    unittest.main()
