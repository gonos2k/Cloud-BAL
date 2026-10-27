"""Portable checks for exact first-group ratio classification and source pins."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "pr107_t39_first_group_replay", ROOT / "tools/pr107_t39_first_group_replay.py")
REPLAY = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(REPLAY)


class FirstGroupReplayTests(unittest.TestCase):
    def test_classification_distinguishes_exact_real64_from_rounded_real32(self):
        event = {
            "hex": {
                "HEX32_BASE": ["00000000", "00000000"],
                "HEX32_CARRIERS_DT": ["47BA3950", "47BA309A", "3F057850", "41200000"],
                "HEX64_MASS_BOUNDS": ["4059000000000000", "408C200000000000"],
                "HEX64_SOURCE_RATE": ["3E40CE1401B7EC8D", "3DA31ECF154C2509"],
                "HEX64_TRANSPORT_RATE": ["3E925255AA4A6B83", "3DF4D88EFAA4515D"],
                "HEX64_CANDIDATE": ["3DC0321C9E375C92", "3D226D5A966EC69E"],
            }
        }
        result = REPLAY.classify(event)
        self.assertFalse(result["candidate_is_inside_exact_strict_mass_cone"])
        self.assertTrue(result["real32_rounded_candidate"]["inside_strict_mass_bounds"])
        self.assertEqual(result["source_q_minus_900n_exact"],
                         "23/154742504910672534362390528")
        self.assertEqual(result["transport_q_minus_900n_exact"],
                         "67/4835703278458516698824704")
        self.assertEqual(result["combined_q_minus_900n_exact"],
                         "2167/154742504910672534362390528")

    def test_bad_source_pin_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
            REPLAY.require_sha256("fixture", b"actual", "0" * 64)

    def test_bad_join_pin_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "preserved T39 join SHA256 mismatch"):
            REPLAY.verify_join_bytes(b"{}")

    def test_existing_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "receipt.json"
            output.write_text("keep this receipt\n")
            with self.assertRaises(FileExistsError):
                REPLAY.write_exclusive(output, {"value": 1})
            self.assertEqual(output.read_text(), "keep this receipt\n")


if __name__ == "__main__":
    unittest.main()
