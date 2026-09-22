program test_qbal_profile_reconstruction
  use iso_fortran_env, only: real64
  use ieee_arithmetic, only: ieee_is_nan, ieee_value, ieee_quiet_nan
  use qbal_pressure_flux, only: integrate_pressure_profile
  use qbal_profile_reconstruction, only: fit_profile_sample
  implicit none
  integer :: checks
  real(real64) :: p2(2),v2(2),c2(2),fit2(2),expected2(2),innovation
  real(real64) :: p(4),v(4),c(4),fit(4),fit_scaled(4),scaled_c(4)
  real(real64) :: edge_c(4),edge_small(4),edge_large(4)
  real(real64) :: fit_above(4),fit_below(4),fit_exact(4)
  real(real64) :: expected(4),p_before(4),v_before(4),c_before(4)
  real(real64) :: nan,upper,lower,whole,whole_above,whole_below,cap
  real(real64) :: expected_denominator
  real(real64) :: badp(4),badv(4),badc(4)
  logical :: ok,upper_ok,lower_ok,whole_ok

  checks=0
  nan=ieee_value(0._real64,ieee_quiet_nan)

  ! Explicit two-node dense formula: a=[1/2,1/2], C and R are supplied.
  p2=[100000._real64,90000._real64]
  v2=[10._real64,20._real64]
  c2=[4._real64,9._real64]
  expected_denominator=25._real64+0.25_real64*(4._real64+9._real64)
  expected2=v2+c2*0.5_real64*(25._real64-15._real64)/expected_denominator
  call fit_profile_sample(p2,v2,c2,95000._real64,25._real64,25._real64, &
      fit2,innovation,ok)
  call check(ok,'dense two-node fit accepted')
  call check(abs(innovation-10._real64)<1.e-13_real64,'analytic innovation')
  call check(maxval(abs(fit2-expected2))<1.e-13_real64,'analytic two-node formula')

  p=[100000._real64,95000._real64,90000._real64,5000._real64]
  v=[2._real64,4._real64,8._real64,16._real64]
  c=[1._real64,9._real64,25._real64,49._real64]
  p_before=p
  v_before=v
  c_before=c

  ! Coincident observation: matching data produce no update; mismatch updates
  ! only the coincident knot when the interpolation row is one-hot.
  call fit_profile_sample(p,v,c,95000._real64,4._real64,7._real64, &
      fit,innovation,ok)
  call check(ok.and.abs(innovation)<1.e-13_real64,'matching coincident observation')
  call check(maxval(abs(fit-v))<1.e-13_real64,'matching observation leaves profile')
  call fit_profile_sample(p,v,c,95000._real64,20._real64,7._real64, &
      fit,innovation,ok)
  expected=v
  expected(2)=4._real64+9._real64*16._real64/16._real64
  call check(ok.and.abs(innovation-16._real64)<1.e-13_real64, &
      'mismatching coincident observation')
  call check(maxval(abs(fit-expected))<1.e-13_real64, &
      'coincident update uses supplied knot variance')

  ! The two-sided interpolation rows converge to the same one-hot row at the
  ! internal 95000 Pa knot, with a derivative allowed to change there.
  call fit_profile_sample(p,v,c,95000.000000001_real64,13._real64,7._real64, &
      fit_above,innovation,ok)
  call check(ok,'sample just above internal knot')
  call fit_profile_sample(p,v,c,95000._real64,13._real64,7._real64, &
      fit_exact,innovation,ok)
  call check(ok,'sample at internal knot')
  call fit_profile_sample(p,v,c,94999.999999999_real64,13._real64,7._real64, &
      fit_below,innovation,ok)
  call check(ok,'sample just below internal knot')
  call check(maxval(abs(fit_above-fit_exact))<1.e-9_real64.and. &
      maxval(abs(fit_below-fit_exact))<1.e-9_real64.and. &
      maxval(abs(fit_above-fit_below))<2.e-9_real64, &
      'continuous profile fusion across 95000 Pa')
  call integrate_pressure_profile(p,fit_above,p(1),p(size(p)),whole_above,upper_ok)
  call integrate_pressure_profile(p,fit_below,p(1),p(size(p)),whole_below,lower_ok)
  call check(upper_ok.and.lower_ok.and.abs(whole_above-whole_below)<1.e-6_real64, &
      'cap-independent integral continuity across 95000 Pa')

  ! A nonuniform supplied research covariance is used directly in the dense
  ! rank-one update; no default covariance or observation error is invented.
  call fit_profile_sample(p,v,c,92500._real64,20._real64,7.5_real64, &
      fit,innovation,ok)
  expected=v
  expected(2)=4._real64+9._real64*0.5_real64*14._real64/16._real64
  expected(3)=8._real64+25._real64*0.5_real64*14._real64/16._real64
  call check(ok.and.abs(innovation-14._real64)<1.e-13_real64, &
      'supplied research variance innovation')
  call check(maxval(abs(fit-expected))<1.e-13_real64, &
      'supplied research variances used without defaults')

  ! Multiplying every supplied variance by one common positive factor leaves
  ! the rank-one fit unchanged.
  scaled_c=37._real64*c
  call fit_profile_sample(p,v,scaled_c,92500._real64,20._real64,7.5_real64*37._real64, &
      fit_scaled,innovation,ok)
  call check(ok.and.maxval(abs(fit_scaled-fit))<1.e-13_real64, &
      'common variance scaling invariance')
  edge_c=1.e-100_real64
  call fit_profile_sample(p,v,edge_c,92500._real64,20._real64,1.e-100_real64, &
      edge_small,innovation,ok)
  call check(ok,'lower finite variance envelope endpoint accepted')
  edge_c=1.e100_real64
  call fit_profile_sample(p,v,edge_c,92500._real64,20._real64,1.e100_real64, &
      edge_large,innovation,ok)
  call check(ok.and.maxval(abs(edge_small-edge_large))<1.e-13_real64, &
      'upper/lower variance endpoint scaling invariance')

  ! Partition one already-fitted profile at a knot and at an arbitrary cap.
  ! Both sums must equal the same full-profile integral; neither branch fits.
  call fit_profile_sample(p,v,c,92500._real64,20._real64,7.5_real64, &
      fit,innovation,ok)
  call check(ok,'profile for cap additivity')
  cap=95000._real64
  call integrate_pressure_profile(p,fit,p(1),cap,upper,upper_ok)
  call integrate_pressure_profile(p,fit,cap,p(size(p)),lower,lower_ok)
  call integrate_pressure_profile(p,fit,p(1),p(size(p)),whole,whole_ok)
  call check(upper_ok.and.lower_ok.and.whole_ok.and. &
      abs((upper+lower)-whole)<1.e-10_real64, 'upper/lower additivity at knot')
  cap=87777.3_real64
  call integrate_pressure_profile(p,fit,p(1),cap,upper,upper_ok)
  call integrate_pressure_profile(p,fit,cap,p(size(p)),lower,lower_ok)
  call check(upper_ok.and.lower_ok.and.abs((upper+lower)-whole)<1.e-8_real64, &
      'upper/lower additivity at arbitrary cap')

  ! Inputs are immutable, including after the successful fit sequence.
  call check(all(p==p_before).and.all(v==v_before).and.all(c==c_before), &
      'profile and supplied variances unchanged')

  ! Every variance must be explicit, finite, and strictly positive.
  badc=c
  badc(2)=0._real64
  call expect_reject(p,v,badc,92500._real64,20._real64,7.5_real64, &
      'zero background variance rejected')
  badc(2)=-1._real64
  call expect_reject(p,v,badc,92500._real64,20._real64,7.5_real64, &
      'negative background variance rejected')
  call expect_reject(p,v,c,92500._real64,20._real64,0._real64, &
      'zero sample variance rejected')
  call expect_reject(p,v,c,92500._real64,20._real64,-1._real64, &
      'negative sample variance rejected')
  badc=c
  badc(2)=1.e-120_real64
  call expect_reject(p,v,badc,92500._real64,20._real64,7.5_real64, &
      'below arithmetic envelope background variance rejected')
  call expect_reject(p,v,c,92500._real64,20._real64,1.e-120_real64, &
      'below arithmetic envelope sample variance rejected')

  ! NaN, reversed/duplicate knots, size mismatch, and outside-domain samples
  ! all fail closed with NaN outputs.
  call expect_reject(p,v,c,nan,20._real64,7.5_real64,'NaN sample pressure rejected')
  badp=p
  badp(2)=nan
  call expect_reject(badp,v,c,92500._real64,20._real64,7.5_real64, &
      'NaN pressure knot rejected')
  badv=v
  badv(2)=nan
  call expect_reject(p,badv,c,92500._real64,20._real64,7.5_real64, &
      'NaN wind knot rejected')
  call expect_reject(p,v,c,p(1)+1._real64,20._real64,7.5_real64, &
      'upper pressure extrapolation rejected')
  call expect_reject(p,v,c,p(size(p))-1._real64,20._real64,7.5_real64, &
      'lower pressure extrapolation rejected')
  badp=p([4,3,2,1])
  call expect_reject(badp,v,c,50000._real64,20._real64,7.5_real64, &
      'reversed pressure knots rejected')
  badp=p
  badp(3)=badp(2)
  call expect_reject(badp,v,c,92500._real64,20._real64,7.5_real64, &
      'duplicate pressure knot rejected')
  call fit_profile_sample(p,v(1:3),c,92500._real64,20._real64,7.5_real64, &
      fit,innovation,ok)
  call check(.not.ok.and.all(ieee_is_nan(fit)).and.ieee_is_nan(innovation), &
      'mismatched profile length rejected')

  print '(a,i0)', 'profile reconstruction checks passed: ',checks
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

  subroutine expect_reject(pp,ww,cc,ps,ws,rr,label)
    real(real64), intent(in) :: pp(:),ww(:),cc(:),ps,ws,rr
    character(*), intent(in) :: label
    real(real64) :: result(size(pp)),residual
    logical :: accepted
    call fit_profile_sample(pp,ww,cc,ps,ws,rr,result,residual,accepted)
    call check(.not.accepted.and.all(ieee_is_nan(result)).and. &
        ieee_is_nan(residual),label)
  end subroutine expect_reject
end program test_qbal_profile_reconstruction
