import unittest

from pr75_native_fp_transform import transform


SOURCE = """   module module_mp_kdm6
   use, intrinsic :: ieee_arithmetic, only : ieee_is_finite
   integer, parameter, private :: PROGB_ABSENT = 0
   contains
   subroutine adapter()
   real :: number_value
   logical :: number_valid
         call specific_number_to_volume(ni(i,k,j), dry_density(i,k), number_value, number_valid)
   end subroutine adapter
   end module module_mp_kdm6
"""


class NativeFpTransformTest(unittest.TestCase):
    def test_records_conversion_inputs_and_runtime_state_only_on_failure(self):
        transformed = transform(SOURCE)
        self.assertIn("pr75_read_fp_state(thread_id)", transformed)
        self.assertIn("pr75_mxcsr_before = pr75_read_fp_state", transformed)
        self.assertIn("ni(i,k,j), dry_density(i,k), number_value, number_valid", transformed)
        self.assertIn("if (.not. number_valid) then", transformed)
        self.assertIn("NI_ADAPTER_FAILURE", transformed)
        self.assertIn("transfer(number_value,0)", transformed)
        self.assertIn("pr75_thread_before", transformed)
        self.assertIn("pr75_thread_after", transformed)

    def test_rejects_ambiguous_source(self):
        with self.assertRaises(ValueError):
            transform(SOURCE + "\n" + SOURCE)


if __name__ == "__main__":
    unittest.main()
