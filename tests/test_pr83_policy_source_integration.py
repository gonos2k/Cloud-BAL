"""Integration check against the exact external evidence bound by PR83 policy."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import initialize_native_moments as initializer  # noqa: E402


class PR83PolicySourceIntegrationTests(unittest.TestCase):
    def test_policy_hashes_all_bound_source_and_runtime_receipts(self):
        policy = initializer._validate_same13_policy_file(initializer.DEFAULT_PR83_POLICY)
        self.assertEqual(policy["policy_id"], "SAME13_KDM6_NATIVE_MOMENT_PRIOR_20261013")


if __name__ == "__main__":
    unittest.main()
