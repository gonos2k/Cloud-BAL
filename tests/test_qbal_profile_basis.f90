program test_qbal_profile_basis
  use iso_fortran_env, only: real64
  use ieee_arithmetic, only: ieee_is_nan
  use qbal_pressure_flux, only: integrate_pressure_profile
  use qbal_profile_reconstruction, only: fit_profile_sample, profile_sample_row
  implicit none

  integer :: checks
  real(real64) :: state_p(5),state_prior(5),state_variance(5)
  real(real64) :: observed_p(3),row(5),row_cross(5),row_above(5),row_below(5)
  real(real64) :: affine(5)
  real(real64) :: fitted(5),innovation,expected(5),predicted
  real(real64) :: sample_p,sample_wind,sample_variance
  real(real64) :: denominator,integral_below_sample,integral_above_sample
  real(real64) :: integral_whole
  real(real64) :: integral_below_cap,integral_above_cap
  logical :: ok,top_ok,lower_ok,whole_ok

  checks=0

  ! Manufactured research state: coefficients and diagonal C are supplied
  ! explicitly.  observed_p represents a separate legacy observation grid;
  ! no value is inferred for an unobserved lower state coefficient.
  state_p=[100000._real64,80000._real64,60000._real64,40000._real64, &
           25000._real64]
  state_prior=[10._real64,20._real64,30._real64,40._real64,50._real64]
  state_variance=[4._real64,9._real64,16._real64,25._real64,36._real64]
  observed_p=[95000._real64,75000._real64,50000._real64]

  ! The row has at most two state coefficients and partitions unity at an
  ! observed pressure that is on neither pressure grid.
  sample_p=67500._real64
  call profile_sample_row(state_p,sample_p,row,ok)
  call check(ok,'sample row accepted inside fixed state domain')
  call check(abs(sum(row)-1._real64)<1.e-14_real64, &
      'sample row partition of unity')
  call check(count(abs(row)>0._real64)==2.and. &
      maxval(abs(row-[0._real64,0.375_real64,0.625_real64,0._real64, &
      0._real64]))<1.e-14_real64,'sample row has expected two-point support')
  call check(all(sample_p/=observed_p).and.all(sample_p/=state_p), &
      'sample pressure differs from observed and state knots')
  call check(observed_p(1)/=state_p(1).and.observed_p(2)/=state_p(2), &
      'observed and fixed state pressure grids are distinct')

  ! Piecewise-linear interpolation reproduces an affine pressure profile at
  ! any in-domain sample, independent of the nonuniform state spacing.
  affine=1.25_real64+7.e-5_real64*state_p
  call check(abs(dot_product(row,affine)- &
      (1.25_real64+7.e-5_real64*sample_p))<1.e-12_real64, &
      'sample row reproduces affine pressure profile')

  ! The sample conflicts with the manufactured prior.  The expected update is
  ! written from the supplied C/R rank-one formula so no covariance default is
  ! hidden in this experiment.
  sample_wind=50._real64
  sample_variance=7.5_real64
  predicted=dot_product(row,state_prior)
  denominator=sample_variance+dot_product(row,state_variance*row)
  expected=state_prior+state_variance*row*(sample_wind-predicted)/denominator
  call fit_profile_sample(state_p,state_prior,state_variance,sample_p, &
      sample_wind,sample_variance,fitted,innovation,ok)
  call check(ok,'conflicting sample softfit accepted')
  call check(abs(innovation-(sample_wind-predicted))<1.e-13_real64, &
      'softfit innovation uses explicit sample row')
  call check(maxval(abs(fitted-expected))<1.e-13_real64, &
      'softfit uses explicit state C and sample R')
  call check(maxval(abs(fitted([1,4,5])-state_prior([1,4,5])))<1.e-13_real64, &
      'softfit leaves unsupported state coefficients unchanged')

  ! Pressure increases toward lower altitude.  The former observed lowest
  ! physical level is 95 kPa; a 98 kPa sample is valid because the fixed
  ! state basis extends to 100 kPa, and is still a manufactured sample.
  sample_p=98000._real64
  call profile_sample_row(state_p,sample_p,row_cross,ok)
  call check(ok.and.sample_p>observed_p(1).and. &
      sample_p<=state_p(1), &
      'lower-altitude sample remains in fixed state domain')
  call check(maxval(abs(row_cross-[0.9_real64,0.1_real64,0._real64, &
      0._real64,0._real64]))<1.e-14_real64, &
      'lower-altitude sample uses state knots beyond observed domain')
  call profile_sample_row(state_p,95000.000001_real64,row_above,ok)
  call check(ok.and.abs(sum(row_above)-1._real64)<1.e-14_real64, &
      'sample just above former observed pressure knot is valid')
  call profile_sample_row(state_p,94999.999999_real64,row_below,ok)
  call check(ok.and.abs(sum(row_below)-1._real64)<1.e-14_real64, &
      'sample just below former observed pressure knot is valid')
  call check(maxval(abs(row_above-row_below))<1.e-9_real64, &
      'crossing former observed pressure knot has no state-row jump')
  call fit_profile_sample(state_p,state_prior,state_variance,sample_p, &
      dot_product(row_cross,state_prior),sample_variance,fitted,innovation,ok)
  call check(ok.and.abs(innovation)<1.e-13_real64.and. &
      maxval(abs(fitted-state_prior))<1.e-13_real64, &
      'matching lower sample does not alter manufactured prior')

  ! Integrate the one fitted state profile below and above the sample, then
  ! verify that changing the reporting cap leaves the total unchanged.
  sample_p=67500._real64
  call fit_profile_sample(state_p,state_prior,state_variance,sample_p, &
      sample_wind,sample_variance,fitted,innovation,ok)
  call check(ok,'refit fixed state profile for integral experiment')
  call integrate_pressure_profile(state_p,fitted,state_p(1),sample_p, &
      integral_below_sample,top_ok)
  call integrate_pressure_profile(state_p,fitted,sample_p,state_p(size(state_p)), &
      integral_above_sample,lower_ok)
  call integrate_pressure_profile(state_p,fitted,state_p(1),state_p(size(state_p)), &
      integral_whole,whole_ok)
  call check(top_ok.and.lower_ok.and.whole_ok.and. &
      abs((integral_below_sample+integral_above_sample)-integral_whole)<1.e-9_real64* &
      max(1._real64,abs(integral_whole)), &
      'below-sample and above-sample integrals sum to full profile')
  call integrate_pressure_profile(state_p,fitted,state_p(1),47000._real64, &
      integral_below_cap,top_ok)
  call integrate_pressure_profile(state_p,fitted,47000._real64, &
      state_p(size(state_p)),integral_above_cap,lower_ok)
  call check(top_ok.and.lower_ok.and. &
      abs((integral_below_cap+integral_above_cap)-integral_whole)<1.e-9_real64* &
      max(1._real64,abs(integral_whole)), &
      'integral is independent of an arbitrary reporting cap')

  ! A sample outside the fixed state domain fails closed; this protects the
  ! experiment from silently assigning an unbound or extrapolated value.
  call profile_sample_row(state_p,24000._real64,row,ok)
  call check(.not.ok.and.all(ieee_is_nan(row)), &
      'out-of-domain sample rejected with NaN row')

  print '(a,i0)', 'profile basis checks passed: ',checks

contains
  subroutine check(condition,label)
    logical, intent(in) :: condition
    character(*), intent(in) :: label
    if (.not.condition) then
      print *, 'FAIL: ',label
      error stop 1
    end if
    checks=checks+1
  end subroutine check
end program test_qbal_profile_basis
