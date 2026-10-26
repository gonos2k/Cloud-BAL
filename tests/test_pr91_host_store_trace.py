from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import pr91_host_store_trace as trace


class HostStoreTraceTests(unittest.TestCase):
    def test_core_captures_failed_final_store_call_through_existing_failure_stage(self):
        source = (ROOT / "docs/evidence/pr91_host_store_20261020/validation/final_i/original_c7_core.f90").read_text()
        transformed = trace.instrument_core(source)
        self.assertEqual(transformed.count("failure_stage=local_store_stage"), 3)
        self.assertIn("diagnostic_candidate(trace_cell,1,p) = q_value", transformed)
        self.assertIn("diagnostic_stored(trace_cell,2,p) = n_candidate(i,p)", transformed)
        self.assertIn("diagnostic_cells(:)", transformed)
        self.assertIn("if (present(diagnostic_stage)) diagnostic_stage = 0", transformed)


    def test_transform_rejects_unpinned_sources(self):
        with self.assertRaisesRegex(ValueError, "core source hash mismatch"):
            trace.instrument_core("module cloud_bal_joint_transport\n")


if __name__ == "__main__":
    unittest.main()
