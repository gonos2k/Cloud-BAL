from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pr102_capture20_preflight as preflight


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Capture20PreflightTests(unittest.TestCase):
    def test_baseline_preflight_writes_only_review_receipt_without_execute_flag(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            proposal, build, output = root / "proposal.json", root / "build.json", root / "review.json"
            proposal.write_text("proposal")
            build.write_text("build")
            future = root / "future_run"
            prepared = {
                "candidate_build": {"receipt_path": str(build), "receipt_sha256": sha256(build),
                                    "executable_sha256": "base C2"},
                "candidate_input_binding": {"receipt_path": str(proposal), "receipt_sha256": sha256(proposal)},
                "candidate_wrfinput_sha256": "candidate input",
                "candidate_wrfbdy_sha256": "boundary",
                "candidate_namelist_sha256": "namelist",
                "source_receipt": "/source/receipt.json", "source_receipt_sha256": "receipt",
                "launch_environment": {"OMP_NUM_THREADS": "1"},
                "diagnostic_environment": {"PR91_RUN_ID": "id"},
                "disk_guard": {"status": "PASS"}, "pr102_native_consumer": None,
            }
            with patch.object(preflight.runner, "prepare", return_value=prepared) as prepare:
                record = preflight.make_preflight("baseline", proposal, build, future, output)
            prepare.assert_called_once()
            self.assertEqual(prepare.call_args.args[:2], ("STRUCTURED_BASELINE20", 20))
            self.assertFalse(future.exists())
            self.assertFalse(record["launch_authorized"])
            self.assertFalse(record["execution_performed"])
            self.assertNotIn("--execute", record["launch_argv_without_execute"])
            self.assertEqual(record["status"], "READY_FOR_ROOT_REVIEW_NO_LAUNCH")
            self.assertEqual(json.loads(output.read_text()), record)

    def test_capture_mode_requires_consumer_and_a_fresh_run_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            proposal, build, output = root / "proposal.json", root / "build.json", root / "review.json"
            proposal.write_text("proposal")
            build.write_text("build")
            future = root / "future_run"
            with self.assertRaisesRegex(ValueError, "requires exactly one archived-consumer"):
                preflight.make_preflight("capture", proposal, build, future, output)
            consumer = root / "consumer.json"
            consumer.write_text("consumer")
            future.mkdir()
            with self.assertRaisesRegex(FileExistsError, "future run root must be fresh"):
                preflight.make_preflight("capture", proposal, build, future, output, consumer)


if __name__ == "__main__":
    unittest.main()
