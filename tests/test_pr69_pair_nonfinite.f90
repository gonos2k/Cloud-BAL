program test_pr69_pair_nonfinite
  use, intrinsic :: ieee_arithmetic, only: ieee_value,ieee_quiet_nan
  use pr69_helper, only: kdm6_shared_pair_fraction
  implicit none
  real :: fraction
  fraction=kdm6_shared_pair_fraction(ieee_value(1.0,ieee_quiet_nan),0.0,1.0,0.0)
  write(*,*) fraction
  error stop 'nonfinite paired rate unexpectedly returned'
end program test_pr69_pair_nonfinite
