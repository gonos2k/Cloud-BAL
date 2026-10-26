from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pr103_archived_consumer as consumer


class ArchivedConsumerTests(unittest.TestCase):
    def test_root_go_must_bind_proposal_candidate_executable_profile_and_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            go_path = root / "go.json"
            binding = {"receipt_sha256": "proposal-sha",
                       "artifacts": {"candidate": {"sha256": "candidate-sha"}}}
            output = (root / "consumer-output").resolve()
            record = {"schema": "pr103_archived_consumer_go_v1", "status": "GO",
                      "launch_authorized": True, "proposal_sha256": "proposal-sha",
                      "candidate_wrfinput_sha256": "candidate-sha",
                      "archived_consumer_executable_sha256": consumer.archived.EXECUTABLE_SHA,
                      "compiler_profile_sha256": consumer.archived.PROFILE_SHA,
                      "output_directory": str(output)}
            go_path.write_text(json.dumps(record))
            pin = consumer._root_go(go_path, {}, binding, output)
            self.assertEqual(pin["candidate_wrfinput_sha256"], "candidate-sha")
            record["candidate_wrfinput_sha256"] = "another-candidate"
            go_path.write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError, "does not authorize this exact call"):
                consumer._root_go(go_path, {}, binding, output)

    def test_plan_only_has_no_launch_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(FileNotFoundError):
                consumer.assess(root / "missing-proposal.json", root / "consumer", execute=False)

if __name__ == "__main__":
    unittest.main()
