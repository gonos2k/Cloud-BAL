import importlib.util
import hashlib
import json
import shutil
import tempfile
import copy
import struct
import sys
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
spec = importlib.util.spec_from_file_location("preclamp", ROOT / "tools/cp02_preclamp_response.py")
preclamp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preclamp)


def scalar(value):
    raw = struct.pack("<f", value)
    return {"raw_hex": raw.hex(), "value_f32": struct.unpack("<f", raw)[0], "finite": True}


class PreclampTests(unittest.TestCase):
    def test_instruction_order_and_float32_rounding(self):
        operands = {name: scalar(value) for name, value in {
            "xmm2": 16777216, "xmm14": 1, "xmm6": -16777216,
            "xmm9": 0, "xmm7": 0, "xmm10": 0, "xmm15": 1}.items()}
        self.assertEqual(preclamp.reconstruct(operands, scalar(2)), (2.0, 0.0))

    def test_rejects_mismatched_scalar_metadata(self):
        record = scalar(1)
        record["value_f32"] = 1.00000001
        with self.assertRaisesRegex(ValueError, "differs"):
            preclamp.scalar(record, "sample")

    def test_rejects_invalid_and_nonfinite_bytes(self):
        for raw in ("000000", "0000zz00", "0000807f"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                preclamp.scalar({"raw_hex": raw, "value_f32": 0, "finite": True}, "sample")


    def event_records(self):
        roles = {"before_sum": "0x25f4e24", "before_clamp": "0x25f4e50", "before_store": "0x25f4e58", "after_store": "0x25f4e5e"}
        records = []
        for label, rank in (("P05_00", "1"), ("P01_00", "3")):
            events = []
            for role, pc in roles.items():
                regs = {name: scalar(0) for name in ("xmm2", "xmm6", "xmm7", "xmm9", "xmm10", "xmm14", "xmm15")}
                qrs = dict(scalar(0), address_hex="0x1234")
                registers = f"rbx 0x100\nr8 0x0\nr12 0x1234\nrip {pc}\n" + "".join(
                    f"zmm{name[3:]} {{v16_int32 = {{0x{int.from_bytes(bytes.fromhex(value['raw_hex']), 'little'):x}}}}}\n"
                    for name, value in regs.items())
                events.append({"target": label, "role": role, "pc_hex": pc, "rank": rank, "pid": int(rank),
                               "registers_at_breakpoint": registers, "scalar_registers": regs,
                               "backtrace": "backtrace", "instructions": "instructions", "frame_rbx_hex": "0x100",
                               "frame_rbx_raw_hex": "00" * 0x500, "qrs_address_hex": "0x1234", "values": {"qrs": qrs}})
            records.append({"rank": rank, "pid": int(rank), "preclamp_events": events})
        return records

    def test_event_completeness_and_order(self):
        records = self.event_records()
        self.assertEqual(len(preclamp.validate_events(records, "OFF")), 2)
        for mode in ("missing", "duplicate", "order", "pc"):
            bad = copy.deepcopy(records)
            events = bad[0]["preclamp_events"]
            if mode == "missing": events.pop()
            if mode == "duplicate": events.append(copy.deepcopy(events[0]))
            if mode == "order": events[0], events[1] = events[1], events[0]
            if mode == "pc": events[0]["pc_hex"] = "0x25f4e50"
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                preclamp.validate_events(bad, "OFF")

    def test_rejects_changed_direct_register_and_store(self):
        for event_index, field in ((1, "register"), (3, "store")):
            bad = self.event_records()
            event = bad[0]["preclamp_events"][event_index]
            if field == "register": event["scalar_registers"]["xmm9"] = scalar(1)
            else: event["values"]["qrs"] = dict(scalar(1), address_hex="0x1234")
            with self.subTest(field=field), self.assertRaises(ValueError):
                preclamp.validate_events(bad, "OFF")

    def test_existing_output_and_dangling_symlink_are_preserved(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "result"
            output.mkdir()
            (output / "sentinel").write_text("keep")
            with self.assertRaisesRegex(ValueError, "already exists"):
                preclamp.publish(output, [], [])
            self.assertEqual((output / "sentinel").read_text(), "keep")
            (output / "sentinel").unlink()
            output.rmdir()
            output.symlink_to(Path(tmp) / "missing")
            with self.assertRaisesRegex(ValueError, "already exists"):
                preclamp.publish(output, [], [])
            self.assertTrue(output.is_symlink())


    @unittest.skipUnless((ROOT / "docs/evidence/cp02_preclamp_20261029/captures/OFF/receipt.json").is_file(), "OFF capture unavailable")
    def test_receipt_and_rank_pid_mutations_fail_closed(self):
        source = ROOT / "docs/evidence/cp02_preclamp_20261029/captures/OFF"
        preparation = ROOT / "docs/evidence/cp02_preclamp_20261029/runtime/prepare_v2.json"
        for mode in ("build_id", "manifest", "rank", "pid", "filename", "hash"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                capture = Path(tmp) / "capture"
                shutil.copytree(source, capture)
                receipt_path = capture / "receipt.json"
                receipt = json.loads(receipt_path.read_text())
                item = receipt["captures"][0]
                if mode == "build_id": del receipt["binary"]["build_id"]
                if mode == "manifest": del receipt["input_manifest_sha256"]
                if mode == "rank": item["rank"] = "999"
                if mode == "pid": item["pid"] += 1
                if mode == "filename":
                    old = capture / Path(item["path"]).name
                    new = old.with_name(old.name.replace("_pid", "_rank999_pid"))
                    old.rename(new)
                    item["path"] = str(new)
                if mode == "hash":
                    path = capture / Path(item["path"]).name
                    path.write_bytes(path.read_bytes() + b"x")
                receipt_path.write_text(json.dumps(receipt))
                with self.assertRaises(ValueError):
                    preclamp.read_new_stage(capture, "OFF", preparation)


    @unittest.skipUnless(all((ROOT / "docs/evidence/cp02_preclamp_20261029/captures" / arm / "receipt.json").is_file() for arm in ("OFF", "HYDRO", "LIQUID")), "three-arm captures unavailable")
    def test_three_arm_captures_and_artifact_hashes(self):
        evidence = ROOT / "docs/evidence/cp02_preclamp_20261029"
        prior = ROOT / "docs/evidence/cp02_kdm6_controls_20261029"
        rows = []
        summaries = []
        for arm in ("OFF", "HYDRO", "LIQUID"):
            summary, observations = preclamp.analyze(evidence / "captures" / arm, prior / "captures" / arm,
                                                      prior / "selection.json", evidence / "runtime/prepare_v2.json", arm)
            self.assertEqual(summary["status"], "PASS_SCOPED_CAPTURE_CONTINUITY")
            for endpoint in summary["outer_optional_byte_comparison_by_endpoint"].values():
                self.assertTrue(all(counts["compared"] == 624 for counts in endpoint.values()))
            self.assertTrue(all(row["direct_preclamp"] == row["reconstructed_preclamp"] for row in observations))
            self.assertTrue(all(row["before_raw_hex"] == row["pr127_before_raw_hex"] and
                                row["actual_store_raw_hex"] == row["pr127_store_raw_hex"] for row in observations))
            summaries.append(summary)
            rows.extend(observations)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "result"
            preclamp.publish(out, summaries, rows)
            manifest = json.loads((out / "artifact_manifest.json").read_text())
            for name, digest in manifest.items():
                self.assertEqual(hashlib.sha256((out / name).read_bytes()).hexdigest(), digest)


    def test_register_and_frame_evidence_mutations_fail(self):
        for mode in ("register", "destination", "frame"):
            bad = self.event_records()
            event = bad[0]["preclamp_events"][0]
            if mode == "register": event["registers_at_breakpoint"] = event["registers_at_breakpoint"].replace("zmm2 {v16_int32 = {0x0}", "zmm2 {v16_int32 = {0x1}")
            if mode == "destination": event["registers_at_breakpoint"] = event["registers_at_breakpoint"].replace("r12 0x1234", "r12 0x1235")
            if mode == "frame":
                data = bytearray.fromhex(event["frame_rbx_raw_hex"])
                data[0x40] = 1
                event["frame_rbx_raw_hex"] = data.hex()
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                preclamp.validate_events(bad, "OFF")

    @unittest.skipUnless(all((ROOT / "docs/evidence/cp02_preclamp_20261029/captures" / arm / "receipt.json").is_file() for arm in ("OFF", "HYDRO", "LIQUID")), "three-arm captures unavailable")
    def test_cli_default_preparation(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "analysis"
            subprocess.run([sys.executable, str(ROOT / "tools/cp02_preclamp_response.py"),
                            "--capture-root", str(ROOT / "docs/evidence/cp02_preclamp_20261029/captures"),
                            "--output", str(output)], cwd=tmp, check=True, capture_output=True, text=True)
            self.assertTrue((output / "artifact_manifest.json").is_file())


if __name__ == "__main__":
    unittest.main()
