import tempfile
import unittest
from pathlib import Path
import sys
import gzip
import hashlib
import json
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from pr91_host_store_replay import main, parse_trace, trace_metadata


class TraceParserTests(unittest.TestCase):
    def write_trace(self, text):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = Path(temp.name) / "trace.raw"
        path.write_text(text)
        return path

    def test_exact_hex_record_and_options_are_joined(self):
        # Whitespace-separated version of the Fortran formatted record. The
        # decimal R64 fields are intentionally bogus; replay inputs come from HEX.
        hex64 = ["3FF0000000000000"] * 10
        hex32 = ["3F800000"] * 8
        integers = ["0", "120", "2", "4", "8", "9", "10"]
        reals = ["9.99999999999999999E-99"] * 19
        tail = ["5", "2"]
        failure = " ".join(["ACTUAL_STORE_FAILURE", "runA", *integers, *reals,
                            *hex64, *hex32, *tail])
        options = " ".join(["ACTUAL_STORE_OPTIONS", "runA", "BASELINE", *integers[1:],
                            "T", "T", "T", "F", "F", "T", "T", "F", "0.0"])
        path = self.write_trace("\n".join(["PR91_HOST_STORE_TRACE_V1 runA", failure, options]))
        rows = parse_trace(path)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual((row.attempt, row.timestep, row.rk, row.pair), (0, 120, 2, 4))
        self.assertEqual((row.candidate_q, row.candidate_n), tuple(hex64[:2]))
        self.assertEqual((row.source_q, row.source_n), tuple(hex64[2:4]))
        self.assertEqual((row.transport_q, row.transport_n), tuple(hex64[4:6]))
        self.assertEqual((row.dry_density, row.min_mass, row.max_mass),
                         (hex32[2], hex64[6], hex64[7]))
        self.assertEqual((row.stage, row.adjustment), (5, 2))
        self.assertTrue(row.allow_subnormal)
        self.assertTrue(row.volume_present)
        self.assertFalse(row.strict_mass)

    def test_missing_options_is_rejected(self):
        hex64 = ["3FF0000000000000"] * 10
        hex32 = ["3F800000"] * 8
        line = " ".join(["ACTUAL_STORE_FAILURE", "runA", *(["1"] * 7),
                         *(["1.0"] * 19), *hex64, *hex32, "2", "0"])
        path = self.write_trace("PR91_HOST_STORE_TRACE_V1 runA\n" + line)
        with self.assertRaisesRegex(ValueError, "missing matching"):
            parse_trace(path)

    def test_header_only_capture_is_explicitly_empty(self):
        path = self.write_trace("PR91_HOST_STORE_TRACE_V1 runA\n")
        self.assertEqual(parse_trace(path), [])

    def test_list_directed_concatenated_header(self):
        path = self.write_trace("PR91_HOST_STORE_TRACE_V1runA\n")
        self.assertEqual(parse_trace(path), [])

    def test_duplicate_and_orphan_options_fail_closed(self):
        option = "ACTUAL_STORE_OPTIONS runA BASELINE 120 2 4 8 9 10 T T T F F T T F 0.0"
        duplicate = self.write_trace("PR91_HOST_STORE_TRACE_V1 runA\n" + option + "\n" + option)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            parse_trace(duplicate)
        orphan = self.write_trace("PR91_HOST_STORE_TRACE_V1 runA\n" + option)
        with self.assertRaisesRegex(ValueError, "orphan"):
            parse_trace(orphan)

    def test_truncated_gzip_fails_closed(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = Path(temp.name) / "trace.raw.gz"
        path.write_bytes(gzip.compress(b"PR91_HOST_STORE_TRACE_V1 runA\n")[:-5])
        with self.assertRaises((EOFError, OSError)):
            parse_trace(path)

    def test_attempt_label_is_part_of_the_join_key(self):
        # The geometry may recur under the second attempt, but it must not
        # consume baseline options for a SOURCE_FIRST_FALLBACK failure.
        hex64 = ["3FF0000000000000"] * 10
        hex32 = ["3F800000"] * 8
        ints = ["0", "120", "2", "4", "8", "9", "10"]
        def failure_line(attempt):
            fields = ["ACTUAL_STORE_FAILURE", "runA", *ints]
            fields[2] = str(attempt)
            return " ".join([*fields, *(["1.0"] * 19), *hex64, *hex32, "5", "0"])
        base = " ".join(["ACTUAL_STORE_OPTIONS", "runA", "BASELINE", *ints[1:],
                         *(["T"] * 8), "0.0"])
        source = " ".join(["ACTUAL_STORE_OPTIONS", "runA", "SOURCE_FIRST_FALLBACK", *ints[1:],
                           *(["T"] * 8), "0.0"])
        source_failure = failure_line(1)
        path = self.write_trace("\n".join(["PR91_HOST_STORE_TRACE_V1 runA", base, source,
                                            failure_line(0), source_failure]))
        rows = parse_trace(path)
        self.assertEqual([row.attempt for row in rows], [0, 1])

    def test_header_and_record_run_ids_must_agree(self):
        option = "ACTUAL_STORE_OPTIONS runB BASELINE 120 2 4 8 9 10 T T T F F T T F 0.0"
        for body in (option, "PR91_HOST_STORE_TRACE_V1 runB"):
            with self.subTest(body=body):
                with self.assertRaisesRegex(ValueError, "run ID"):
                    parse_trace(self.write_trace("PR91_HOST_STORE_TRACE_V1 runA\n" + body))
        with self.assertRaisesRegex(ValueError, "closed diagnostic"):
            parse_trace(self.write_trace("PR91_HOST_STORE_TRACE_V1 runA\n"),
                        expected_run_id="runB")
        with self.assertRaisesRegex(ValueError, "lacks a run header"):
            parse_trace(self.write_trace(""), expected_run_id="runA")

    def test_metadata_binds_raw_and_compressed_artifacts(self):
        path = self.write_trace("PR91_HOST_STORE_TRACE_V1 runA\n")
        payload = path.read_bytes()
        capture = {"trace_sha256": hashlib.sha256(payload).hexdigest(),
                   "bytes": len(payload), "selected_failure_records": 0, "run_root": "/run/A"}
        closed = {"identity": "runA", "source_run_root": "/run/A",
                  "raw_failure_trace_sha256": capture["trace_sha256"]}
        for compressed in (False, True):
            with self.subTest(compressed=compressed):
                current = path.with_suffix(".gz") if compressed else path
                if compressed:
                    current.write_bytes(gzip.compress(payload))
                    closed["compressed_failure_trace_sha256"] = hashlib.sha256(current.read_bytes()).hexdigest()
                (path.parent / "capture.json").write_text(json.dumps(capture))
                (path.parent / "closed_run.json").write_text(json.dumps(closed))
                metadata, run_id, count = trace_metadata(current)
                self.assertEqual((run_id, count), ("runA", 0))
                self.assertEqual(metadata["trace_uncompressed_sha256"], capture["trace_sha256"])
                self.assertEqual(parse_trace(current, expected_run_id=run_id), [])
                wrong = dict(closed)
                wrong["compressed_failure_trace_sha256" if compressed else "raw_failure_trace_sha256"] = "0" * 64
                (path.parent / "closed_run.json").write_text(json.dumps(wrong))
                with self.assertRaisesRegex(ValueError, "does not match"):
                    trace_metadata(current)

    def test_capture_sidecar_mismatch_is_rejected_before_replay(self):
        path = self.write_trace("PR91_HOST_STORE_TRACE_V1 runA\n")
        capture = {"trace_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                   "bytes": path.stat().st_size, "selected_failure_records": 1}
        sidecar = path.parent / "capture.json"
        sidecar.write_text(json.dumps(capture))
        with patch.object(sys, "argv", ["replay", str(path)]):
            with self.assertRaisesRegex(ValueError, "count differs"):
                main()
        capture["trace_sha256"] = "0" * 64
        sidecar.write_text(json.dumps(capture))
        with self.assertRaisesRegex(ValueError, "capture metadata"):
            trace_metadata(path)

    def test_sidecars_cannot_bind_different_source_runs(self):
        path = self.write_trace("PR91_HOST_STORE_TRACE_V1 runA\n")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        (path.parent / "capture.json").write_text(json.dumps({
            "trace_sha256": digest, "bytes": path.stat().st_size,
            "selected_failure_records": 0, "run_root": "/run/A"}))
        (path.parent / "closed_run.json").write_text(json.dumps({
            "identity": "runA", "raw_failure_trace_sha256": digest, "source_run_root": "/run/B"}))
        with self.assertRaisesRegex(ValueError, "different source runs"):
            trace_metadata(path)


if __name__ == "__main__":
    unittest.main()
