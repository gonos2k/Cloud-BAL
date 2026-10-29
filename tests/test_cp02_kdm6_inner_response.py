import gzip
import hashlib
import importlib.util
import json
import shutil
import struct
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/cp02_kdm6_inner_response.py"
SPEC = importlib.util.spec_from_file_location("cp02_kdm6_inner_response", SCRIPT)
inner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inner)

EVIDENCE = ROOT / "docs/evidence/cp02_thermo_response_20261029"
CAPTURE_ROOT = EVIDENCE / "captures"
PRIOR_ROOT = ROOT / "docs/evidence/cp02_kdm6_controls_20261029/captures"
SELECTION = ROOT / "docs/evidence/cp02_kdm6_controls_20261029/selection.json"
PREPARE = EVIDENCE / "runtime/prepare_v6.json"
ARMS = ("OFF", "HYDRO", "LIQUID")
REAL_CAPTURE_READY = all((CAPTURE_ROOT / arm / "receipt.json").is_file() for arm in ARMS)


class InnerResponseTests(unittest.TestCase):
    def test_profile_binding_uses_bytes_not_checkout_path(self):
        with tempfile.TemporaryDirectory(prefix="cp02-profile-binding-") as temp:
            relocated_profile = Path(temp) / "tests/intel_toolchain.sh"
            relocated_profile.parent.mkdir()
            source_profile = ROOT / "tests/intel_toolchain.sh"
            shutil.copyfile(source_profile, relocated_profile)
            captured = {"path": "/archived/checkout/tests/intel_toolchain.sh",
                        "sha256": hashlib.sha256(relocated_profile.read_bytes()).hexdigest()}

            inner.validate_profile_binding(captured, relocated_profile)

            relocated_profile.write_bytes(relocated_profile.read_bytes() + b"\n# changed\n")
            with self.assertRaisesRegex(ValueError, "does not bind the pinned Intel profile bytes"):
                inner.validate_profile_binding(captured, relocated_profile)

    def test_inner_argument_vector_reconciles_registers_stack_and_nullable_slots(self):
        nulls = {32, 39, 40, 41, 42, 43, 44, 47, 48}
        pointers = [0 if index in nulls else 0x10000 + index * 0x100
                    for index in range(1, 63)]
        stack = struct.pack("<Q", int(inner.INNER_RETURN_PC, 16))
        stack += b"".join(struct.pack("<Q", pointers[index-1]) for index in range(7, 63))
        stack += struct.pack("<Q", 0)
        record = {
            "argument_count": 62,
            "argument_pointers_hex": [hex(value) for value in pointers],
            "registers_hex": {name: hex(pointers[index])
                              for index, name in enumerate(("rdi", "rsi", "rdx", "rcx", "r8", "r9"))},
            "stack_hex_from_rsp": stack.hex(),
            "null_argument_positions": sorted(nulls),
        }
        decoded = inner.validate_inner_argument_vector(record, "3")
        self.assertEqual(decoded[31], 0)
        bad_stack_bytes = stack[:-16] + b"\x01" * 8 + stack[-8:]
        bad_stack = dict(record, stack_hex_from_rsp=bad_stack_bytes.hex())
        with self.assertRaisesRegex(ValueError, "raw stack slot"):
            inner.validate_inner_argument_vector(bad_stack, "3")

    def test_native_failed_capture_cannot_pass_or_publish(self):
        failed = EVIDENCE / "failed_attempt2"
        with tempfile.TemporaryDirectory(prefix="cp02-inner-failed-") as temp:
            output = Path(temp) / "must_not_exist"
            with self.assertRaisesRegex(ValueError, "native failure markers|receipt status is not complete"):
                inner.analyze(failed, PRIOR_ROOT / "HYDRO", SELECTION,
                              EVIDENCE / "runtime/prepare_v3.json", "HYDRO")
            self.assertFalse(output.exists())

    def test_missing_receipt_fails_closed(self):
        with tempfile.TemporaryDirectory(prefix="cp02-inner-empty-") as temp:
            with self.assertRaises((ValueError, OSError)):
                inner.analyze(temp, PRIOR_ROOT / "OFF", SELECTION,
                              EVIDENCE / "runtime/prepare_v3.json", "OFF")

    def test_existing_output_directory_is_preserved(self):
        with tempfile.TemporaryDirectory(prefix="cp02-inner-output-") as temp:
            output = Path(temp) / "existing"
            output.mkdir()
            sentinel = output / "sentinel"
            sentinel.write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "already exists"):
                inner.publish(output, {}, [], [])
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")

    def test_dangling_output_symlink_is_preserved(self):
        with tempfile.TemporaryDirectory(prefix="cp02-inner-link-") as temp:
            output = Path(temp) / "output"
            target = Path(temp) / "missing-target"
            output.symlink_to(target)
            with self.assertRaisesRegex(ValueError, "already exists"):
                inner.publish(output, {}, [], [])
            self.assertTrue(output.is_symlink())
            self.assertEqual(output.readlink(), target)
            self.assertFalse(target.exists())

    @unittest.skipUnless(REAL_CAPTURE_READY, "final three-arm raw captures are not archived yet")
    def test_real_three_arm_capture_and_atomic_outputs(self):
        with tempfile.TemporaryDirectory(prefix="cp02-inner-real-") as temp:
            for arm in ARMS:
                output = Path(temp) / arm
                summary, samples, events = inner.analyze(
                    CAPTURE_ROOT / arm, PRIOR_ROOT / arm, SELECTION, PREPARE, arm)
                self.assertEqual(summary["status"], "PASS_SCOPED_CAPTURE_CONTINUITY")
                self.assertEqual(summary["outer_byte_equal_values"],
                                 624 * len(inner.CORE_OUTER_FIELDS) * 2)
                optional = summary["outer_optional_byte_comparison_by_endpoint"]
                self.assertEqual(set(optional), {"entry", "return"})
                for endpoint in optional.values():
                    self.assertTrue(all(item["compared"] == 624
                                        for item in endpoint.values()))
                self.assertEqual(summary["inner_target_points"], 8)
                self.assertEqual(len(samples), 16)
                self.assertTrue(all(len(row["qrs_raw_hex"]) == 8 for row in samples))
                self.assertTrue(all(call["unavailable_pointer_positions"]
                                    == call["null_argument_positions"]
                                    for call in summary["inner_calls"]))
                inner.publish(output, summary, samples, events)
                manifest = json.loads((output / "artifact_manifest.json").read_text())
                for name, digest in manifest.items():
                    self.assertEqual(hashlib.sha256((output / name).read_bytes()).hexdigest(), digest)

    @unittest.skipUnless(REAL_CAPTURE_READY, "final three-arm raw captures are not archived yet")
    def test_tampered_raw_hash_is_rejected_without_output(self):
        with tempfile.TemporaryDirectory(prefix="cp02-inner-hash-") as temp:
            temp = Path(temp)
            copied = temp / "HYDRO"
            shutil.copytree(CAPTURE_ROOT / "HYDRO", copied)
            item = inner.load_json(copied / "receipt.json")["captures"][0]
            capture_path = copied / Path(item["path"]).name
            capture_path.write_bytes(capture_path.read_bytes() + b"x")
            output = temp / "must_not_exist"
            with self.assertRaisesRegex(ValueError, "compressed hash mismatch"):
                summary, samples, events = inner.analyze(
                    copied, PRIOR_ROOT / "HYDRO", SELECTION, PREPARE, "HYDRO")
                inner.publish(output, summary, samples, events)
            self.assertFalse(output.exists())

    @unittest.skipUnless(REAL_CAPTURE_READY, "final three-arm raw captures are not archived yet")
    def test_missing_rank_is_rejected_without_output(self):
        with tempfile.TemporaryDirectory(prefix="cp02-inner-missing-rank-") as temp:
            temp = Path(temp)
            copied = temp / "HYDRO"
            shutil.copytree(CAPTURE_ROOT / "HYDRO", copied)
            item = inner.load_json(copied / "receipt.json")["captures"][0]
            (copied / Path(item["path"]).name).unlink()
            output = temp / "must_not_exist"
            with self.assertRaisesRegex(ValueError, "raw capture file inventory"):
                summary, samples, events = inner.analyze(
                    copied, PRIOR_ROOT / "HYDRO", SELECTION, PREPARE, "HYDRO")
                inner.publish(output, summary, samples, events)
            self.assertFalse(output.exists())

    @unittest.skipUnless(REAL_CAPTURE_READY, "final three-arm raw captures are not archived yet")
    def test_wrong_inner_return_sequence_is_rejected_without_output(self):
        with tempfile.TemporaryDirectory(prefix="cp02-inner-sequence-") as temp:
            temp = Path(temp)
            copied = temp / "HYDRO"
            shutil.copytree(CAPTURE_ROOT / "HYDRO", copied)
            receipt = inner.load_json(copied / "receipt.json")
            target = None
            for item in receipt["captures"]:
                path = copied / Path(item["path"]).name
                raw = gzip.decompress(path.read_bytes())
                record = json.loads(raw)
                if record.get("inner"):
                    target = (item, path, record)
                    break
            self.assertIsNotNone(target, "capture has no selected inner records")
            item, path, record = target
            record["inner"][0]["return"]["pc"] = "0xdead"
            raw = (json.dumps(record, sort_keys=True, allow_nan=False) + "\n").encode()
            packed = gzip.compress(raw, mtime=0)
            path.write_bytes(packed)
            item["sha256"] = hashlib.sha256(packed).hexdigest()
            item["size_bytes"] = len(packed)
            item["uncompressed_sha256"] = hashlib.sha256(raw).hexdigest()
            item["uncompressed_size_bytes"] = len(raw)
            (copied / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n",
                                                  encoding="utf-8")
            output = temp / "must_not_exist"
            with self.assertRaisesRegex(ValueError, "missing inner return record"):
                summary, samples, events = inner.analyze(
                    copied, PRIOR_ROOT / "HYDRO", SELECTION, PREPARE, "HYDRO")
                inner.publish(output, summary, samples, events)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
