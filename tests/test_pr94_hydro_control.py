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

    def test_policy_changes_only_hydro_input_binding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stage, _, _ = self.make_stage(root)
            output = root / "hydro-policy.json"
            policy = hydro.write_policy(stage, output)

            self.assertEqual(policy["schema"], hydro.PR94_HYDRO_POLICY_SCHEMA)
            self.assertEqual(policy["preflight"]["authorized_source_inputs"][-1]["role"], "HYDRO")
            self.assertEqual(_validate_same13_policy_file(output), policy)

            policy["species"]["QCLOUD"]["lambda_min_m-1"] += 1
            output.write_text(json.dumps(policy), encoding="utf-8")
            with self.assertRaisesRegex(InitializationError, "PR94_POLICY_DIFFERS_FROM_PR84_V2"):
                _validate_same13_policy_file(output)

    def test_policy_rejects_modified_hydro_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stage, wrfinput, _ = self.make_stage(root)
            output = root / "hydro-policy.json"
            hydro.write_policy(stage, output)
            wrfinput.write_bytes(b"mutated")
            with self.assertRaisesRegex(InitializationError, "PR94_HYDRO_INPUT_BINDING_HASH_MISMATCH"):
                _validate_same13_policy_file(output)

    def test_final_receipt_binds_initialized_input_and_stage_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stage_path, _, wrfbdy = self.make_stage(root)
            policy_path = root / "hydro-policy.json"
            policy = hydro.write_policy(stage_path, policy_path)
            stage = json.loads(stage_path.read_text(encoding="utf-8"))
            output_input = root / "initialized-wrfinput"
            output_input.write_bytes(b"initialized hydro bytes")
            initialized = {
                "status": "RESEARCH_PRIOR_CREATED",
                "source_input_role": "HYDRO",
                "policy_schema": hydro.PR94_HYDRO_POLICY_SCHEMA,
                "output_input": str(output_input),
                "output_input_sha256": hydro.sha256(output_input),
                "source_input": stage["wrfinput"]["path"],
                "source_input_sha256": stage["wrfinput"]["sha256"],
                "policy_sha256": hydro.sha256(policy_path),
                "hydro_input_binding": policy["hydro_input_binding"],
            }
            initializer_receipt = root / "initializer-receipt.json"
            initializer_receipt.write_text(json.dumps(initialized), encoding="utf-8")
            final_path = root / "final-receipt.json"

            final = hydro.write_final_receipt(
                stage_path, policy_path, initializer_receipt, final_path
            )
            self.assertEqual(final["schema"], "pr94_hydro_native_input_v1")
            self.assertEqual(final["wrfinput"]["sha256"], hydro.sha256(output_input))
            self.assertEqual(final["wrfbdy"]["sha256"], hydro.sha256(wrfbdy))

    def test_final_receipt_rejects_initializer_from_other_generation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stage_path, _, _ = self.make_stage(root)
            policy_path = root / "hydro-policy.json"
            policy = hydro.write_policy(stage_path, policy_path)
            stage = json.loads(stage_path.read_text(encoding="utf-8"))
            output_input = root / "other-generation-moment"
            output_input.write_bytes(b"historical initialized bytes")
            initialized = {
                "status": "RESEARCH_PRIOR_CREATED",
                "source_input_role": "HYDRO",
                "policy_schema": hydro.PR94_HYDRO_POLICY_SCHEMA,
                "output_input": str(output_input),
                "output_input_sha256": hydro.sha256(output_input),
                "source_input": stage["wrfinput"]["path"],
                "source_input_sha256": "f" * 64,
                "policy_sha256": hydro.sha256(policy_path),
                "hydro_input_binding": policy["hydro_input_binding"],
            }
            initializer_receipt = root / "historical-initializer-receipt.json"
            initializer_receipt.write_text(json.dumps(initialized), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not bound to this stage and policy"):
                hydro.write_final_receipt(
                    stage_path, policy_path, initializer_receipt, root / "final.json"
                )

    def test_final_receipt_rejects_contract_boundary_typo(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stage_path, _, _ = self.make_stage(root)
            stage = json.loads(stage_path.read_text(encoding="utf-8"))
            stage["comparison_contract"]["boundary_sha256"] = "0" * 64
            stage_path.write_text(json.dumps(stage), encoding="utf-8")
            policy_path = root / "hydro-policy.json"
            hydro.write_policy(stage_path, policy_path)
            output_input = root / "initialized-wrfinput"
            output_input.write_bytes(b"initialized hydro bytes")
            initialized = {
                "status": "RESEARCH_PRIOR_CREATED",
                "source_input_role": "HYDRO",
                "policy_schema": hydro.PR94_HYDRO_POLICY_SCHEMA,
                "output_input": str(output_input),
                "output_input_sha256": hydro.sha256(output_input),
            }
            initializer_receipt = root / "initializer-receipt.json"
            initializer_receipt.write_text(json.dumps(initialized), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "contract boundary hash differs"):
                hydro.write_final_receipt(
                    stage_path, policy_path, initializer_receipt, root / "final.json"
                )


if __name__ == "__main__":
    unittest.main()
