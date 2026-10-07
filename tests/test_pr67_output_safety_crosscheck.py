from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from pr67_output_safety_crosscheck import (  # noqa: E402
    _receipt_bound_output,
    validate_call_headers,
    validate_finite_pair,
    validate_output_times,
)


class PR67OutputSafetyCrosscheckTests(unittest.TestCase):
    def test_rejects_unexpected_output_timestamp(self) -> None:
        with self.assertRaisesRegex(ValueError, "timestamps"):
            validate_output_times(("2026-08-16_12:00:00", "2026-08-16_12:01:00"))

    def test_rejects_nonfirst_or_mismatched_call_headers(self) -> None:
        pre = {"stage": 1, "itimestep": 1, "bounds": {"its": 2}, "params": {"dt_s": 20}}
        post = {"stage": 2, "itimestep": 1, "bounds": {"its": 2}, "params": {"dt_s": 20}}
        validate_call_headers(pre, post)
        post["params"] = {"dt_s": 19}
        with self.assertRaisesRegex(ValueError, "headers"):
            validate_call_headers(pre, post)
        post["params"] = pre["params"]
        post["itimestep"] = 2
        with self.assertRaisesRegex(ValueError, "headers"):
            validate_call_headers(pre, post)

    def test_rejects_nonfinite_mass_or_moment_but_reflectivity_is_counted_separately(self) -> None:
        import numpy as np

        validate_finite_pair(np.array([1.0]), np.array([2.0]), "QR/NR")
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            validate_finite_pair(np.array([float("nan")]), np.array([0.0]), "QR/NR")

    def test_receipt_binds_exact_regular_output_and_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary)
            output = run / "wrfout_d01_2026-08-16_12:00:00"
            output.write_bytes(b"bound output")
            digest = hashlib.sha256(output.read_bytes()).hexdigest()
            receipt = {
                "run_root": str(run), "returncode": 0,
                "input_integrity": "PASS", "output_isolation": "PASS",
                "outputs": [{"path": output.name, "nlink": 1, "sha256": digest}],
            }
            receipt_path = run / "receipt.json"
            receipt_path.write_text(json.dumps(receipt))
            self.assertEqual(_receipt_bound_output(run, output, receipt_path), digest)

            receipt["outputs"][0]["sha256"] = "0" * 64
            receipt_path.write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError, "hash"):
                _receipt_bound_output(run, output, receipt_path)

    def test_rejects_symlinked_receipt_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary)
            real = run / "real-output"
            real.write_bytes(b"bound output")
            output = run / "wrfout_d01_2026-08-16_12:00:00"
            output.symlink_to(real.name)
            receipt = {
                "run_root": str(run), "returncode": 0,
                "input_integrity": "PASS", "output_isolation": "PASS",
                "outputs": [{"path": output.name, "nlink": 1,
                             "sha256": hashlib.sha256(real.read_bytes()).hexdigest()}],
            }
            receipt_path = run / "receipt.json"
            receipt_path.write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError, "receipt-listed"):
                _receipt_bound_output(run, output, receipt_path)


if __name__ == "__main__":
    unittest.main()
