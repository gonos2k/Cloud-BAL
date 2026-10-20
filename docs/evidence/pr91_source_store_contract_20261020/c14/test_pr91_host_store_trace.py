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

    def test_host_marks_actual_call_before_recomputed_diagnosis_and_fallback(self):
        host_path = Path("/var/tmp/pr90_sources_c7_20261019/module_em.F")
        original_core = (ROOT / "docs/evidence/pr91_host_store_20261020/validation/final_i/original_c7_core.f90").read_text()
        transformed_core = trace.instrument_core(original_core)
        transformed = trace.instrument_host(host_path.read_text(), transformed_core, original_core)
        actual = transformed.index("CALL write_pr91_actual_store_failures( &")
        fallback = transformed.index("CALL try_graupel_mixture_trial()", actual)
        self.assertLess(actual, fallback)
        self.assertIn("'ACTUAL_STORE_FAILURE'", transformed)
        self.assertIn("'ACTUAL_STORE_OPTIONS',TRIM(run_id)", transformed)
        self.assertIn("10(1x,z16.16),8(1x,z8.8)", transformed)
        self.assertIn("PR91_RUN_ID is required", transformed)
        self.assertIn("diagnostic_scale=pr91_scale", transformed)
        self.assertIn("MERGE(1,0,ANY(source_first_pair))", transformed)
        self.assertIn("PROBE_GRAUPEL_REJECT", transformed)
        self.assertIn("PR91_MIXTURE_STORE_REJECT", transformed)
        self.assertIn("WRITE(u,*) 'FULL',itimestep,rk,p,i,j,k", transformed)

    def test_transform_rejects_unpinned_sources(self):
        with self.assertRaisesRegex(ValueError, "core source hash mismatch"):
            trace.instrument_core("module cloud_bal_joint_transport\n")


if __name__ == "__main__":
    unittest.main()
