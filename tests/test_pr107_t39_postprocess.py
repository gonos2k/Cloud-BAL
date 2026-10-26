import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "postprocess_t39", ROOT / "docs/evidence/pr107_t39_capture_20261026/postprocess_t39.py")
postprocess = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(postprocess)


class PR107T39PostprocessTest(unittest.TestCase):
    def test_receipt_requires_closed_unchanged_hydro_run(self):
        receipt = {"arm": "HYDRO", "status": "INCOMPLETE", "returncode": 1,
                   "candidate_build_unchanged": True, "candidate_input_unchanged": True,
                   "changed_staged_inputs": [], "changed_original_inputs": [],
                   "processing_errors": []}
        with tempfile.TemporaryDirectory(prefix="pr107-closed-receipt-") as tmp:
            path = Path(tmp) / "receipt.json"
            path.write_text(json.dumps(receipt))
            self.assertEqual(postprocess.verify_closed_hydro_receipt(path)["status"], "INCOMPLETE")
            receipt["status"] = "RUNNING"
            path.write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError, "not closed"):
                postprocess.verify_closed_hydro_receipt(path)

    def test_gzip_capture_hashes_bind_compressed_and_payload_bytes(self):
        payload = b"PR107 test payload\n"
        with tempfile.TemporaryDirectory(prefix="pr107-capture-hashes-") as tmp:
            path = Path(tmp) / "capture.raw.gz"
            path.write_bytes(gzip.compress(payload, mtime=0))
            receipt = {"generated_files": [{"path": path.name,
                                            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}],
                       "compressed_outputs": [{"path": "capture.raw",
                                               "sha256": hashlib.sha256(payload).hexdigest(),
                                               "compressed_path": path.name,
                                               "compressed_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}]}
            hashes = postprocess.verify_capture_artifact(path, receipt)
            self.assertEqual(hashes["uncompressed_payload_sha256"], hashlib.sha256(payload).hexdigest())
            path.write_bytes(gzip.compress(b"different payload\n", mtime=0))
            with self.assertRaisesRegex(ValueError, "differs from closed receipt"):
                postprocess.verify_capture_artifact(path, receipt)

    def test_fatal_consumer_joins_t39_rk1_channels_and_rejects_epoch_or_bounds(self):
        consumer = {"step": 39, "rk": 2, "i": 2, "j": 219, "k": 13,
                    "producer_identity": [39, 1, 2, 233, 2, 281, 1, 39],
                    "r64_bits": ["A", "B", "C", "D"]}
        producers = {}
        for channel, im, diff in ((7, 4, "A"), (8, 5, "B")):
            key = (39, 1, channel, im, 2, 219, 13)
            producers[key] = {"identity": consumer["producer_identity"],
                              "before32_bits": "01", "after32_bits": "02",
                              "diffusion64_bits": diff, "scale32_bits": ["1"] * 4,
                              "metrics32_bits": ["2"] * 10, "stencil": {-1: [], 0: [], 1: []}}
        result = postprocess.join_fatal_producers(producers, consumer)
        self.assertEqual(result["producer_identity_bounds"][:2], [39, 1])
        self.assertTrue(result["channels"]["7"]["matches_consumer_source_rate"])
        self.assertTrue(result["channels"]["8"]["matches_consumer_source_rate"])
        producers[(39, 2, 7, 4, 2, 219, 13)] = producers.pop((39, 1, 7, 4, 2, 219, 13))
        with self.assertRaisesRegex(ValueError, "expected one channel 7"):
            postprocess.join_fatal_producers(producers, consumer)
        producers[(39, 1, 7, 4, 2, 219, 13)] = producers.pop((39, 2, 7, 4, 2, 219, 13))
        producers[(39, 1, 7, 4, 2, 219, 13)]["identity"] = [39, 1, 2, 232, 2, 281, 1, 39]
        with self.assertRaisesRegex(ValueError, "bounds differ"):
            postprocess.join_fatal_producers(producers, consumer)

    def test_first_group_is_linked_only_for_same_cell_and_callback_pair(self):
        first = {"i": 2, "j": 219, "k": 13, "pair": 4, "key": ("run", 39, 2, 1, 4, 1),
                 "group_predicate": 1, "hex": {"HEX64_CANDIDATE": ["a", "b"]},
                 "store_failure_stage": 0}
        same, pair, status, link = postprocess.link_first_group_to_fatal(first, [2, 219, 13])
        self.assertTrue(same)
        self.assertTrue(pair)
        self.assertEqual(status, "LINKED_SAME_CELL_PAIR4")
        self.assertIsNotNone(link)
        first["pair"] = 3
        same, pair, status, link = postprocess.link_first_group_to_fatal(first, [2, 219, 13])
        self.assertTrue(same)
        self.assertFalse(pair)
        self.assertEqual(status, "SAME_CELL_PAIR_MISMATCH")
        self.assertIsNone(link)
        first["i"] = 3
        same, _, status, link = postprocess.link_first_group_to_fatal(first, [2, 219, 13])
        self.assertFalse(same)
        self.assertEqual(status, "DIFFERENT_CELL")
        self.assertIsNone(link)


if __name__ == "__main__":
    unittest.main()
