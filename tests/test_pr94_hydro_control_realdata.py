from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import test_pr94_hydro_control as base


class TestPR94HydroExternalInput(unittest.TestCase):
    make_stage = base.Pr94HydroPolicyTest.make_stage

    def test_policy_changes_only_hydro_input_binding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stage, _, _ = self.make_stage(root)
            output = root / "hydro-policy.json"
            policy = base.hydro.write_policy(stage, output)

            self.assertEqual(policy["schema"], base.hydro.PR94_HYDRO_POLICY_SCHEMA)
            self.assertEqual(policy["preflight"]["authorized_source_inputs"][-1]["role"], "HYDRO")
            self.assertEqual(base._validate_same13_policy_file(output), policy)

            policy["species"]["QCLOUD"]["lambda_min_m-1"] += 1
            output.write_text(json.dumps(policy), encoding="utf-8")
            with self.assertRaisesRegex(base.InitializationError, "PR94_POLICY_DIFFERS_FROM_PR84_V2"):
                base._validate_same13_policy_file(output)


    def test_policy_rejects_modified_hydro_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stage, wrfinput, _ = self.make_stage(root)
            output = root / "hydro-policy.json"
            base.hydro.write_policy(stage, output)
            wrfinput.write_bytes(b"mutated")
            with self.assertRaisesRegex(base.InitializationError, "PR94_HYDRO_INPUT_BINDING_HASH_MISMATCH"):
                base._validate_same13_policy_file(output)


    def test_final_receipt_binds_initialized_input_and_stage_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stage_path, _, wrfbdy = self.make_stage(root)
            policy_path = root / "hydro-policy.json"
            policy = base.hydro.write_policy(stage_path, policy_path)
            stage = json.loads(stage_path.read_text(encoding="utf-8"))
            output_input = root / "initialized-wrfinput"
            output_input.write_bytes(b"initialized hydro bytes")
            initialized = {
                "status": "RESEARCH_PRIOR_CREATED",
                "source_input_role": "HYDRO",
                "policy_schema": base.hydro.PR94_HYDRO_POLICY_SCHEMA,
                "output_input": str(output_input),
                "output_input_sha256": base.hydro.sha256(output_input),
                "source_input": stage["wrfinput"]["path"],
                "source_input_sha256": stage["wrfinput"]["sha256"],
                "policy_sha256": base.hydro.sha256(policy_path),
                "hydro_input_binding": policy["hydro_input_binding"],
            }
            initializer_receipt = root / "initializer-receipt.json"
            initializer_receipt.write_text(json.dumps(initialized), encoding="utf-8")
            final_path = root / "final-receipt.json"

            final = base.hydro.write_final_receipt(
                stage_path, policy_path, initializer_receipt, final_path
            )
            self.assertEqual(final["schema"], "pr94_hydro_native_input_v1")
            self.assertEqual(final["wrfinput"]["sha256"], base.hydro.sha256(output_input))
            self.assertEqual(final["wrfbdy"]["sha256"], base.hydro.sha256(wrfbdy))


    def test_final_receipt_rejects_initializer_from_other_generation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stage_path, _, _ = self.make_stage(root)
            policy_path = root / "hydro-policy.json"
            policy = base.hydro.write_policy(stage_path, policy_path)
            stage = json.loads(stage_path.read_text(encoding="utf-8"))
            output_input = root / "other-generation-moment"
            output_input.write_bytes(b"historical initialized bytes")
            initialized = {
                "status": "RESEARCH_PRIOR_CREATED",
                "source_input_role": "HYDRO",
                "policy_schema": base.hydro.PR94_HYDRO_POLICY_SCHEMA,
                "output_input": str(output_input),
                "output_input_sha256": base.hydro.sha256(output_input),
                "source_input": stage["wrfinput"]["path"],
                "source_input_sha256": "f" * 64,
                "policy_sha256": base.hydro.sha256(policy_path),
                "hydro_input_binding": policy["hydro_input_binding"],
            }
            initializer_receipt = root / "historical-initializer-receipt.json"
            initializer_receipt.write_text(json.dumps(initialized), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not bound to this stage and policy"):
                base.hydro.write_final_receipt(
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
            base.hydro.write_policy(stage_path, policy_path)
            output_input = root / "initialized-wrfinput"
            output_input.write_bytes(b"initialized hydro bytes")
            initialized = {
                "status": "RESEARCH_PRIOR_CREATED",
                "source_input_role": "HYDRO",
                "policy_schema": base.hydro.PR94_HYDRO_POLICY_SCHEMA,
                "output_input": str(output_input),
                "output_input_sha256": base.hydro.sha256(output_input),
            }
            initializer_receipt = root / "initializer-receipt.json"
            initializer_receipt.write_text(json.dumps(initialized), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "contract boundary hash differs"):
                base.hydro.write_final_receipt(
                    stage_path, policy_path, initializer_receipt, root / "final.json"
                )


