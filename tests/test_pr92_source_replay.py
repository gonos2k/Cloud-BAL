from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("pr92_source_replay", ROOT / "tools/pr92_source_replay.py")
assert SPEC and SPEC.loader
replay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(replay)


class SourceReplayTests(unittest.TestCase):
    def test_transform_is_pinned_and_injects_capture_at_identity_guard(self) -> None:
        source = (ROOT / "docs/evidence/pr91_source_store_contract_20261020/c14/module_em.F").read_text()
        transformed = replay.transform_c14_module(source)
        self.assertNotIn("PR87_GRAUPEL_SOURCE_IDENTITY_FAIL", transformed)
        self.assertIn("write_pr92_graupel_source_capture(c,i,k,j", transformed)
        self.assertIn("PR92_CACHE_DELTA", transformed)
        self.assertIn("'PR92_STORE_FAIL_'//TRIM(context)", transformed)
        self.assertEqual(1, transformed.count("  END SUBROUTINE write_pr92_graupel_source_capture"))

    def test_transform_rejects_unpinned_source(self) -> None:
        with self.assertRaisesRegex(ValueError, "pinned PR91 C14"):
            replay.transform_c14_module("unrelated source")

    def test_summary_uses_exact_record_bits_and_reports_first_location(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "capture.raw"
            path.write_text(
                "PR92_FAIL 50 1 2 218 13 99\n"
                "PR92_PRODUCER_IDENTITY UNAVAILABLE\n"
                "PR92_R32 0 0 0 0 0 0 0 0\n"
                "PR92_R64 3FF0000000000000 4000000000000000 "
                "3FE0000000000000 3FF8000000000000 " + "0 " * 8 + "\n"
                "PR92_STENCIL -1 " + "0 " * 12 + "\n"
                "PR92_STENCIL 0 " + "0 " * 12 + "\n"
                "PR92_STENCIL 1 " + "0 " * 12 + "\n"
                "PR92_METRICS " + "0 " * 10 + "\n"
                "PR92_WEIGHTS " + "0 " * 7 + "\n"
                "PR92_DONOR_TERMS " + "0 " * 14 + "\n"
                "PR92_FACE_COEFFICIENTS " + "0 " * 16 + "\n"
            )
            summary = replay.summarize_capture(path)
        self.assertEqual(1, summary["identity_failure_count"])
        self.assertEqual({"step": 50, "rk": 1, "i": 2, "j": 218, "k": 13, "cell": 99},
                         summary["first_failure"])
        self.assertEqual([0.5, 0.5], summary["max_abs_source_minus_recomputed_diffusion"])

    def test_summary_rejects_empty_capture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty.raw"
            path.write_text("")
            with self.assertRaisesRegex(ValueError, "no recognized"):
                replay.summarize_capture(path)

    def test_summary_rejects_truncated_identity_block(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "truncated.raw"
            path.write_text("PR92_FAIL 50 1 2 218 13 99\nPR92_R64 1 2\n")
            with self.assertRaisesRegex(ValueError, "malformed PR92_R64"):
                replay.summarize_capture(path)

    def test_summary_requires_store_failure_r32_companion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "store.raw"
            path.write_text("PR92_STORE_FAIL_FULL " + "1 " * 7 + "0 " * 13 + "\n")
            with self.assertRaisesRegex(ValueError, "truncated PR92 store failure"):
                replay.summarize_capture(path)


if __name__ == "__main__":
    unittest.main()
