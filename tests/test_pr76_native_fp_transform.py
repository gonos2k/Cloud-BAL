import unittest

from pr76_native_fp_transform import transform


SOURCE = """   module module_mp_kdm6
   use, intrinsic :: ieee_arithmetic, only : ieee_is_finite
   integer, parameter, private :: PROGB_ABSENT = 0
   contains
   subroutine kdm6(th, q, qc, qr, qi, qs, qg,             &
   real :: z_sum
   logical :: pr67_trace_this_call
   pr67_trace_this_call = .not. pr67_trace_complete
   end subroutine kdm6
   subroutine adapter()
   real :: number_value
   logical :: number_valid
         call specific_number_to_volume(ni(i,k,j), dry_density(i,k), number_value, number_valid)
   end subroutine adapter
   end module module_mp_kdm6
"""


class NativeFpPolicyTransformTest(unittest.TestCase):
    def test_baseline_adds_failure_observation_without_entry_policy(self):
        transformed = transform(SOURCE, gradual=False)
        self.assertIn("NI_ADAPTER_FAILURE", transformed)
        self.assertNotIn("pr76_apply_gradual", transformed)

    def test_treatment_applies_policy_at_kdm6_entry(self):
        transformed = transform(SOURCE, gradual=True)
        call = "pr76_mxcsr_before = pr76_apply_gradual(pr76_mxcsr_after, pr76_thread_id)"
        entry_trace = "'KDM6_ENTRY'"
        first_statement = "pr67_trace_this_call = .not. pr67_trace_complete"
        self.assertEqual(transformed.count("= pr76_apply_gradual("), 1)
        self.assertEqual(transformed.count(entry_trace), 1)
        self.assertEqual(transformed.count("'TARGET_CALL'"), 1)
        self.assertEqual(transformed.count("'TARGET_BITS'"), 1)
        self.assertLess(transformed.index(call), transformed.index(first_statement))
        self.assertLess(transformed.index(entry_trace), transformed.index(first_statement))
        self.assertIn("pr76_mxcsr_before, pr76_mxcsr_after, pr76_thread_id", transformed)

    def test_rejects_ambiguous_failure_anchor(self):
        with self.assertRaises(ValueError):
            transform(SOURCE + SOURCE, gradual=False)


if __name__ == "__main__":
    unittest.main()
