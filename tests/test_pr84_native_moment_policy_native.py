from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import initialize_native_moments as initializer


class TestPR84NativeMomentPolicyEvidence(unittest.TestCase):
    def test_frozen_policy_binds_actual_kdm6_parameters_and_toolchain(self):
        policy_path = ROOT / "docs/PR84_NATIVE_MOMENT_POLICY_20261013.json"
        policy = initializer._validate_same13_policy_file(policy_path)
        self.assertEqual(
            policy["species"]["QICE"]["source_pidni_binary32_hex"], "0x44C4597C"
        )
        self.assertEqual(policy["native_build"]["runtime_consumer_readback_status"], "NOT_RUN")

        # A self-consistent replacement value and bit pattern still fail against
        # the source kdm6init accessor and independently hashed parameter dump.
        tampered = json.loads(json.dumps(policy))
        tampered["species"]["QICE"]["source_pidni_binary32_value"] = 1570.0
        tampered["species"]["QICE"]["source_pidni_binary32_hex"] = "0x44C44000"
        with self.assertRaisesRegex(initializer.InitializationError,
                                    "PR84_QICE_POLICY_PARAMETER_BINDING_MISMATCH"):
            initializer._validate_pr84_evidence_bindings(tampered)

