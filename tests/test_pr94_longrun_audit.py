from __future__ import annotations

import gzip
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import pr94_longrun_audit as audit  # noqa: E402


class CompactProfileTests(unittest.TestCase):
    def records(self, completed: int = 35) -> list[dict]:
        rows = []
        for step in range(1, completed + 1):
            states = (audit.EXPECTED_SEQUENCE if step <= 30 or step in audit.DETAIL_STEPS
                      else (("POST_KDM6", 0),))
            rows.extend({"timestep": step, "stage": stage, "rkstep": rk}
                        for stage, rk in states)
        return rows

    def test_accepts_full_prefix_snapshots_and_post_cadence(self):
        result = audit.validate_compact_state_profile(self.records(), list(range(1, 36)))
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["retained_state_records"], 30 * 6 + 5)
        self.assertEqual(result["post_only_steps"], [31, 32, 33, 34, 35])

    def test_rejects_missing_extra_and_wrong_rk_records(self):
        rows = self.records()
        rows.remove(next(row for row in rows if row["timestep"] == 4 and row["stage"] == "RK_STAGE_END" and row["rkstep"] == 2))
        with self.assertRaises(audit.LongrunAuditError):
            audit.validate_compact_state_profile(rows, list(range(1, 36)))

        rows = self.records()
        rows.append({"timestep": 31, "stage": "PRE_RK", "rkstep": 0})
        with self.assertRaises(audit.LongrunAuditError):
            audit.validate_compact_state_profile(rows, list(range(1, 36)))

        rows = self.records(60)
        next(row for row in rows if row["timestep"] == 60 and row["stage"] == "RK_STAGE_END")["rkstep"] = 3
        with self.assertRaises(audit.LongrunAuditError):
            audit.validate_compact_state_profile(rows, list(range(1, 61)))

    def test_profile_metadata_does_not_retain_state_arrays(self):
        record = {"timestep": 1, "stage": "POST_KDM6", "rkstep": 0,
                  "fields": {"QC": object()}}
        self.assertEqual(audit._profile_metadata(record),
                         {"timestep": 1, "stage": "POST_KDM6", "rkstep": 0})


class RuntimeBindingTests(unittest.TestCase):
    def test_rejects_wrong_executable_hash(self):
        build = {"executable_sha256": "expected", "receipt_sha256": "receipt"}
        preflight = {"candidate_build": build, "output": "/missing/run"}
        receipt = {"executed_executable_sha256": "wrong",
                   "expected_executed_executable_sha256": "expected",
                   "candidate_build": build}
        with self.assertRaises(audit.LongrunAuditError):
            audit._verify_executable_binding(receipt, preflight, "expected", "manufactured")


class PrefixComparisonTests(unittest.TestCase):
    def _write_trace(self, path: Path, steps: int = 30, mutate: bool = False) -> dict:
        expanded = bytearray()
        bounds = (1, 2, 1, 1, 1, 1, 1, 2, 1, 1, 1, 1)
        header_tail = (0,) * 3 + bounds
        with path.open("wb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as stream:
                for step in range(1, steps + 1):
                    for stage, rkstep in audit.EXPECTED_SEQUENCE:
                        magic = b"PR85QND2"
                        label = stage.encode("ascii").ljust(32, b" ")
                        header = np.asarray((1, step, rkstep, *bounds), dtype=">i4").tobytes()
                        fields = []
                        for index, _name in enumerate(audit.FIELDS):
                            values = np.asarray([step, index], dtype=">f4")
                            if mutate and step == 12 and stage == "POST_KDM6" and index == 0:
                                values[1] = np.float32(999)
                            fields.append(values.tobytes())
                        record = magic + label + header + b"".join(fields)
                        stream.write(record)
                        expanded.extend(record)
        raw_bytes = path.read_bytes()
        return {"path": path.name.removesuffix(".gz"), "sha256": hashlib.sha256(expanded).hexdigest(),
                "bytes": len(expanded), "compressed_path": path.name,
                "compressed_sha256": hashlib.sha256(raw_bytes).hexdigest(),
                "compressed_bytes": len(raw_bytes)}

    def _receipt(self, row: dict, completed: int = 30) -> dict:
        return {"snapshots": {"completed_post_kdm6_timesteps": list(range(1, completed + 1)),
                              "duplicate_post_kdm6_timesteps": []},
                "final_completed_step": completed,
                "compressed_outputs": [row],
                "generated_files": [{"path": row["path"], "sha256": row["sha256"], "bytes": row["bytes"]}]}

    def test_prefix_bytes_match_and_detect_changed_field(self):
        with tempfile.TemporaryDirectory() as temp:
            baseline = Path(temp) / "baseline"
            compact = Path(temp) / "compact"
            (baseline / "run").mkdir(parents=True)
            (compact / "run").mkdir(parents=True)
            base_row = self._write_trace(baseline / "run" / audit.TRACE_NAME)
            good_row = self._write_trace(compact / "run" / audit.TRACE_NAME)
            good = audit.compare_first_600_seconds(baseline, self._receipt(base_row),
                                                   compact, self._receipt(good_row), "OFF")
            self.assertEqual(good["status"], "PASS")
            self.assertEqual(good["compared_state_records"], 180)

            bad_row = self._write_trace(compact / "run" / audit.TRACE_NAME, mutate=True)
            bad = audit.compare_first_600_seconds(
                baseline, self._receipt(base_row), compact,
                self._receipt(bad_row), "OFF")
            self.assertEqual(bad["status"], "FAIL")
            self.assertIn("step 12", bad["differences"][0])

    def test_partial_completed_prefix_is_reported_as_incomplete(self):
        with tempfile.TemporaryDirectory() as temp:
            baseline = Path(temp) / "baseline"
            compact = Path(temp) / "compact"
            (baseline / "run").mkdir(parents=True)
            (compact / "run").mkdir(parents=True)
            base_row = self._write_trace(baseline / "run" / audit.TRACE_NAME)
            partial_row = self._write_trace(compact / "run" / audit.TRACE_NAME, steps=3)
            result = audit.compare_first_600_seconds(
                baseline, self._receipt(base_row), compact,
                self._receipt(partial_row, completed=3), "OFF")
            self.assertEqual(result["status"], "INCOMPLETE")
            self.assertEqual(result["common_prefix_steps"], 3)
            self.assertEqual(result["compared_state_records"], 18)


if __name__ == "__main__":
    unittest.main()
