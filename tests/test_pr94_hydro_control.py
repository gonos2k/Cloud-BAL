from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pr94_hydro_control as hydro
from initialize_native_moments import InitializationError, _validate_same13_policy_file
from pr94_hydro_wps_readback import generation_for_candidate_sha


class Pr94HydroPolicyTest(unittest.TestCase):
    def test_wps_generation_label_is_bound_to_candidate_hash(self) -> None:
        self.assertIn("PR81 same13 current-generation", generation_for_candidate_sha(
            "97a98c5bb05a8dc70528c2b6c025ae8cb359ed46f23b7d3c28941535f71ae9d6"
        ))
        with self.assertRaisesRegex(ValueError, "no pinned generation identity"):
            generation_for_candidate_sha("0" * 64)

    def make_stage(self, root: Path) -> tuple[Path, Path, Path]:
        wrfinput = root / "hydro-wrfinput"
        wrfinput.write_bytes(b"hydro input bytes")
        wrfbdy = root / "hydro-wrfbdy"
        wrfbdy.write_bytes(b"shared boundary bytes")
        candidate = Path("/var/tmp/pr78_cp06a_spatial.V9LYrN/O2/hydro.nc")
        receipt = {
            "schema": hydro.REAL_INPUT_RECEIPT_SCHEMA,
            "status": "PASS_HYDRO_REAL_INPUT",
            "role": "HYDRO",
            "wrfinput": {"path": str(wrfinput), "sha256": hydro.sha256(wrfinput)},
            "wrfbdy": {"path": str(wrfbdy), "sha256": hydro.sha256(wrfbdy)},
            "source_candidate": {
                "path": str(candidate), "sha256": hydro.HYDRO_CANDIDATE_SHA256,
                "mode": "HYDRO", "generation": "PR78 CP06A spatial O2",
            },
            "source_chain_receipts": [],
            "comparison_contract": {
                "physics": "same frozen profile",
                "boundary_sha256": hydro.sha256(wrfbdy),
            },
        }
        path = root / "real-input-receipt.json"
        path.write_text(json.dumps(receipt), encoding="utf-8")
        return path, wrfinput, wrfbdy







if __name__ == "__main__":
    unittest.main()
