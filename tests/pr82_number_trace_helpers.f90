program test_pr82_number_trace_helpers
  use, intrinsic :: ieee_arithmetic, only: ieee_value, ieee_quiet_nan, ieee_positive_inf
  use, intrinsic :: iso_c_binding, only: c_int
  use pr82_number_trace_helpers
  implicit none
  character(len=24) :: error_class

  error_class = number_conversion_error_class(1.0, 0.0, 0.0, 1)
  call expect(error_class == 'NONPOSITIVE_DENSITY', 'density classification')
  error_class = number_conversion_error_class(-1.0, 1.0, 0.0, 1)
  call expect(error_class == 'NEGATIVE_INPUT', 'negative input classification')
  error_class = number_conversion_error_class(ieee_value(0.0, ieee_quiet_nan), 1.0, 0.0, 1)
  call expect(error_class == 'NONFINITE_INPUT', 'nonfinite input classification')
  error_class = number_conversion_error_class(1.0, ieee_value(0.0, ieee_quiet_nan), 0.0, 1)
  call expect(error_class == 'NONFINITE_DENSITY', 'nonfinite density classification')
  error_class = number_conversion_error_class(1.8e38, 2.0, 0.0, 1)
  call expect(error_class == 'OVERFLOW_GUARD', 'multiply overflow classification')
  error_class = number_conversion_error_class(1.8e38, 0.5, 0.0, 2)
  call expect(error_class == 'OVERFLOW_GUARD', 'divide overflow classification')
  error_class = number_conversion_error_class(1.0, 1.0, ieee_value(0.0, ieee_positive_inf), 1)
  call expect(error_class == 'NONFINITE_RESULT', 'nonfinite result classification')
  error_class = number_conversion_error_class(1.0e-30, 1.0e-30, 0.0, 1)
  call expect(error_class == 'POSITIVE_TO_ZERO', 'positive-to-zero classification')

  call log_number_conversion_rejection('NC', 'INPUT', 17, 2, 4, 1.0e-30, &
       1.0e-30, 0.0, 1, int(z'9FFD', c_int), int(z'9FFD', c_int), 0_c_int, 0_c_int)
  print '(A)', 'PR82_HELPER_PASS'
contains
  subroutine expect(condition, label)
    logical, intent(in) :: condition
    character(len=*), intent(in) :: label
    if (.not. condition) then
      write(*,'(A,A)') 'PR82_HELPER_FAIL ', label
      error stop 1
    endif
  end subroutine expect
end program test_pr82_number_trace_helpers
