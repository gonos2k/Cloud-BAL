from __future__ import annotations

import os
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "run_isolated_native.py"
SPEC = importlib.util.spec_from_file_location("run_isolated_native", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
IsolationError = MODULE.IsolationError
run_isolated = MODULE.run_isolated


class IsolatedNativeRunTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.run = self.root / "run"
        self.run.mkdir()
        self.input = self.root / "wrfinput_d01"
        self.input.write_bytes(b"retained input")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _command(self, marker: Path, output: str) -> list[str]:
        code = (
            "from pathlib import Path; "
            f"Path({str(marker)!r}).write_text('launched'); "
            f"Path({output!r}).write_bytes(b'new run output')"
        )
        return [sys.executable, "-c", code]

    def test_launch_writes_new_output_and_records_input_hashes(self) -> None:
        marker = self.root / "launched"
        result = run_isolated(
            self.run, [self.input], ["wrfout_d01"],
            self._command(marker, "wrfout_d01"),
        )
        self.assertEqual(result["input_integrity"], "PASS")
        self.assertEqual(result["output_isolation"], "PASS")
        self.assertEqual((self.run / "wrfout_d01").read_bytes(), b"new run output")
        self.assertEqual(self.input.read_bytes(), b"retained input")
        self.assertTrue(marker.exists())

    def test_hardlinked_historical_output_is_rejected_before_launch(self) -> None:
        control = self.root / "pr61.raw"
        control.write_bytes(b"historical evidence")
        output = self.run / "kdm6.raw"
        os.link(control, output)
        marker = self.root / "launched"

        with self.assertRaisesRegex(IsolationError, "already exists"):
            run_isolated(self.run, [self.input], ["kdm6.raw"],
                         self._command(marker, "kdm6.raw"))

        self.assertFalse(marker.exists())
        self.assertEqual(control.read_bytes(), b"historical evidence")
        self.assertEqual(output.read_bytes(), b"historical evidence")
        self.assertEqual(control.stat().st_ino, output.stat().st_ino)

    def test_symlink_output_is_rejected_before_launch(self) -> None:
        control = self.root / "pr61.raw"
        control.write_bytes(b"historical evidence")
        (self.run / "kdm6.raw").symlink_to(control)
        marker = self.root / "launched"

        with self.assertRaisesRegex(IsolationError, "already exists"):
            run_isolated(self.run, [self.input], ["kdm6.raw"],
                         self._command(marker, "kdm6.raw"))

        self.assertFalse(marker.exists())
        self.assertEqual(control.read_bytes(), b"historical evidence")

    def test_symlink_output_parent_is_rejected_before_launch(self) -> None:
        control_dir = self.root / "control-dir"
        control_dir.mkdir()
        (self.run / "captures").symlink_to(control_dir, target_is_directory=True)
        marker = self.root / "launched"
        with self.assertRaisesRegex(IsolationError, "real directory"):
            run_isolated(self.run, [self.input], ["captures/kdm6.raw"],
                         self._command(marker, "captures/kdm6.raw"))
        self.assertFalse(marker.exists())
        self.assertEqual(list(control_dir.iterdir()), [])

    def test_stale_single_link_output_is_also_rejected(self) -> None:
        output = self.run / "wrfout_d01"
        output.write_bytes(b"stale output")
        marker = self.root / "launched"
        before = output.read_bytes()

        with self.assertRaisesRegex(IsolationError, "already exists"):
            run_isolated(self.run, [self.input], ["wrfout_d01"],
                         self._command(marker, "wrfout_d01"))

        self.assertFalse(marker.exists())
        self.assertEqual(output.read_bytes(), before)

    def test_normalized_duplicate_outputs_are_rejected_before_launch(self) -> None:
        marker = self.root / "launched"
        with self.assertRaisesRegex(IsolationError, "duplicate"):
            run_isolated(
                self.run, [self.input], ["nested//wrfout", "nested/wrfout"],
                self._command(marker, "nested/wrfout"),
            )
        self.assertFalse(marker.exists())

    def test_symlink_component_in_run_root_is_rejected(self) -> None:
        alias = self.root / "run-alias"
        alias.symlink_to(self.run, target_is_directory=True)
        marker = self.root / "launched"
        with self.assertRaisesRegex(IsolationError, "symlink component"):
            run_isolated(alias, [self.input], ["wrfout_d01"],
                         self._command(marker, "wrfout_d01"))
        self.assertFalse(marker.exists())

    def test_hardlinked_input_is_rejected_without_chmod(self) -> None:
        shared = self.root / "shared-input"
        os.link(self.input, shared)
        original_mode = self.input.stat().st_mode
        marker = self.root / "launched"
        with self.assertRaisesRegex(IsolationError, "single-link"):
            run_isolated(self.run, [shared], ["wrfout_d01"],
                         self._command(marker, "wrfout_d01"))
        self.assertFalse(marker.exists())
        self.assertEqual(self.input.stat().st_mode, original_mode)
        self.assertEqual(self.input.read_bytes(), b"retained input")

    def test_postrun_hardlink_is_recorded_as_failure_in_receipt(self) -> None:
        control = self.root / "control.raw"
        control.write_bytes(b"retained control")
        output = self.run / "candidate.raw"
        marker = self.root / "launched"
        code = (
            "import os; from pathlib import Path; "
            f"Path({str(marker)!r}).write_text('launched'); "
            f"os.link({str(control)!r}, {str(output)!r})"
        )
        command = [sys.executable, "-c", code]
        helper = MODULE_PATH
        result = subprocess.run(
            [sys.executable, str(helper), "--run-root", str(self.run),
             "--input", str(self.input), "--output", "candidate.raw",
             "--receipt", "run.receipt.json", "--", *command],
            check=False, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 3)
        receipt = json.loads((self.run / "run.receipt.json").read_text())
        self.assertEqual(receipt["output_isolation"], "FAIL")
        self.assertIn("hardlinked", receipt["output_issues"][0])
        self.assertTrue(marker.exists())
        self.assertEqual(control.read_bytes(), b"retained control")

    def test_persistent_input_write_is_reported_without_chmod_claim(self) -> None:
        code = (
            "from pathlib import Path; "
            f"Path({str(self.input)!r}).write_bytes(b'mutated input'); "
            "Path('wrfout_d01').write_bytes(b'new run output')"
        )
        result = run_isolated(
            self.run, [self.input], ["wrfout_d01"], [sys.executable, "-c", code]
        )
        self.assertEqual(result["input_integrity"], "FAIL")
        self.assertEqual(result["changed_inputs"], [str(self.input.resolve())])
        self.assertEqual(self.input.read_bytes(), b"mutated input")


if __name__ == "__main__":
    unittest.main()
