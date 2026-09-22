program test_qbal_profile_face
  use iso_fortran_env, only: real64
  use ieee_arithmetic, only: ieee_is_nan, ieee_value, ieee_quiet_nan
  use qbal_pressure_flux, only: integrate_pressure_profile
  use qbal_profile_face, only: fit_edge_transport
  implicit none

  integer :: checks
  real(real64) :: xy(2,2),ps(2),pt,p(4),wind(4,2,2),variance(4,2,2)
  real(real64) :: p_sample(2),sample_wind(2,2),sample_variance(2,2)
  real(real64) :: fitted(4,2,2),innovation(2,2),flux,uncovered
  real(real64) :: normal(2),a(2,2),b(2,2),expected,d0,d1
  real(real64) :: integral_d,integral_sd,integral_d2,integral_sd2
  real(real64) :: cap,upper(2,2),lower(2,2),whole(2,2),cap_flux
  real(real64) :: upper_flux,lower_flux
  real(real64) :: fit_knot(4,2,2),innovation_knot(2,2),flux_knot
  real(real64) :: fit_cross(4,2,2),innovation_cross(2,2),flux_cross
  real(real64) :: reverse_xy(2,2),reverse_ps(2),reverse_sample(2)
  real(real64) :: reverse_wind(4,2,2),reverse_variance(4,2,2)
  real(real64) :: reverse_sw(2,2),reverse_sv(2,2),reverse_fit(4,2,2)
  real(real64) :: reverse_innovation(2,2),reverse_flux,reverse_uncovered
  real(real64) :: xy_saved(2,2),ps_saved(2),pt_saved,p_saved(4)
  real(real64) :: wind_saved(4,2,2),variance_saved(4,2,2),p_sample_saved(2)
  real(real64) :: sample_wind_saved(2,2),sample_variance_saved(2,2)
  real(real64) :: nan
  logical :: ok,valid
  integer :: k,c,e

  checks=0
  nan=ieee_value(0._real64,ieee_quiet_nan)
  normal=[3._real64,-4._real64]

  ! Unequal endpoints, a nonuniform p grid, and constant profiles give a
  ! closed-form transport with zero innovations.  The sample span is not a
  ! missing-flux value: the expected uncovered value is pressure only.
  call constant_case()
  call fit_edge_transport(xy,ps,pt,p,wind,variance,p_sample,sample_wind, &
      sample_variance,fitted,innovation,flux,uncovered,ok)
  call check(ok,'unequal-endpoint constant profile accepted')
  call check(abs(flux-358000._real64)<1.e-8_real64, &
      'constant profile analytic flux')
  call check(abs(uncovered-20000._real64)<1.e-12_real64, &
      'uncovered is mean pressure span')
  call check(maxval(abs(fitted-wind))<1.e-12_real64.and. &
      maxval(abs(innovation))<1.e-12_real64,'constant profile has no innovation')
  call check(abs(flux)>1._real64,'constant transport is nonzero')

  ! An affine-in-pressure profile remains exact when the sample matches its
  ! interpolation.  This expected value integrates the resulting cubic in
  ! the edge parameter exactly; the two-point edge quadrature must reproduce it.
  call affine_case()
  a(:,1)=[1.5_real64,-2._real64]
  a(:,2)=[4.5_real64,3._real64]
  b(:,1)=[2.e-4_real64,-1.e-4_real64]
  b(:,2)=[1.e-4_real64,-2.e-4_real64]
  do e=1,2
    do c=1,2
      do k=1,size(p)
        wind(k,c,e)=a(c,e)+b(c,e)*(p(k)-pt)
      end do
      sample_wind(c,e)=a(c,e)+b(c,e)*(p_sample(e)-pt)
    end do
  end do
  d0=p_sample(1)-pt
  d1=p_sample(2)-p_sample(1)
  integral_d=d0+d1/2._real64
  integral_sd=d0/2._real64+d1/3._real64
  integral_d2=d0*d0+d0*d1+d1*d1/3._real64
  integral_sd2=d0*d0/2._real64+2._real64*d0*d1/3._real64+d1*d1/4._real64
  expected=0._real64
  do c=1,2
    expected=expected+normal(c)*(a(c,1)*integral_d+ &
        (a(c,2)-a(c,1))*integral_sd+0.5_real64*b(c,1)*integral_d2+ &
        0.5_real64*(b(c,2)-b(c,1))*integral_sd2)
  end do
  call fit_edge_transport(xy,ps,pt,p,wind,variance,p_sample,sample_wind, &
      sample_variance,fitted,innovation,flux,uncovered,ok)
  call check(ok,'unequal-endpoint affine profile accepted')
  call check(abs(flux-expected)<1.e-7_real64*max(1._real64,abs(expected)), &
      'affine profile analytic flux')
  call check(maxval(abs(innovation))<1.e-10_real64.and. &
      maxval(abs(fitted-wind))<1.e-10_real64,'affine profile has no innovation')

  ! Once fitted, pressure integration is additive at an internal cap.  This
  ! fixes the fitted profile while comparing the complete edge integral with
  ! the sum of its upper and lower pressure pieces.
  call affine_cap_case()
  cap=87000._real64
  call fit_edge_transport(xy,ps,pt,p,wind,variance,p_sample,sample_wind, &
      sample_variance,fitted,innovation,cap_flux,uncovered,ok)
  call check(ok,'fixed profile for cap additivity accepted')
  do e=1,2
    do c=1,2
      call integrate_pressure_profile(p,fitted(:,c,e),p_sample(e),cap,upper(c,e),valid)
      call check(valid,'upper fixed-profile cap integral accepted')
      call integrate_pressure_profile(p,fitted(:,c,e),cap,pt,lower(c,e),valid)
      call check(valid,'lower fixed-profile cap integral accepted')
      whole(c,e)=upper(c,e)+lower(c,e)
    end do
  end do
  expected=0._real64
  do e=1,2
    expected=expected+0.5_real64*normal(1)*whole(1,e)+ &
        0.5_real64*normal(2)*whole(2,e)
  end do
  call check(abs(cap_flux-expected)<1.e-8_real64*max(1._real64,abs(expected)), &
      'fixed profile full integral matches cap sum')
  expected=0._real64
  do e=1,2
    expected=expected+0.5_real64*normal(1)*upper(1,e)+ &
        0.5_real64*normal(2)*upper(2,e)
  end do
  cap_flux=expected
  expected=0._real64
  do e=1,2
    expected=expected+0.5_real64*normal(1)*lower(1,e)+ &
        0.5_real64*normal(2)*lower(2,e)
  end do
  upper_flux=cap_flux
  lower_flux=expected
  ! Retain the pieces separately so a second fit cannot hide a non-additive
  ! pressure integration.
  call fit_edge_transport(xy,ps,pt,p,wind,variance,p_sample,sample_wind, &
      sample_variance,fitted,innovation,flux,uncovered,ok)
  call check(abs(flux-(upper_flux+lower_flux))<1.e-8_real64*max(1._real64,abs(flux)), &
      'fixed profile upper plus lower flux is additive')

  ! Samples straddling an internal knot exercise the split edge quadrature.
  ! A matching sample leaves the profile unchanged.  A mismatching sample
  ! has a continuous limit as either side approaches the same knot row.
  call crossing_case()
  sample_wind(1,:)=[wind(2,1,1)+4._real64,wind(2,1,2)-3._real64]
  sample_wind(2,:)=[wind(2,2,1)-2._real64,wind(2,2,2)+5._real64]
  p_sample=[87000._real64,87000._real64]
  sample_wind=wind(2,:,:)
  call fit_edge_transport(xy,ps,pt,p,wind,variance,p_sample, &
      sample_wind, &
      sample_variance,fit_knot,innovation_knot,flux_knot,uncovered,ok)
  call check(ok.and.maxval(abs(fit_knot-wind))<1.e-12_real64.and. &
      maxval(abs(innovation_knot))<1.e-12_real64, &
      'matching internal-knot samples leave profiles unchanged')
  sample_wind(1,:)=[wind(2,1,1)+4._real64,wind(2,1,2)-3._real64]
  sample_wind(2,:)=[wind(2,2,1)-2._real64,wind(2,2,2)+5._real64]
  call fit_edge_transport(xy,ps,pt,p,wind,variance,p_sample,sample_wind, &
      sample_variance,fit_knot,innovation_knot,flux_knot,uncovered,ok)
  call check(ok.and.maxval(abs(innovation_knot-reshape([4._real64,-2._real64, &
      -3._real64,5._real64],[2,2])))<1.e-11_real64, &
      'internal-knot mismatch innovations are explicit')
  p_sample=[87000.000001_real64,86999.999999_real64]
  call fit_edge_transport(xy,ps,pt,p,wind,variance,p_sample,sample_wind, &
      sample_variance,fit_cross,innovation_cross,flux_cross,uncovered,ok)
  call check(ok,'crossing internal knot accepted')
  call check(maxval(abs(fit_cross-fit_knot))<1.e-8_real64.and. &
      maxval(abs(innovation_cross-innovation_knot))<1.e-8_real64, &
      'crossing mismatch converges to internal-knot limit')
  call check(abs(flux_cross-flux_knot)<1.e-8_real64*max(1._real64,abs(flux_knot)), &
      'crossing edge flux converges to internal-knot limit')

  ! Reversing one shared face reverses exactly one oriented flux value while
  ! preserving the endpoint fit after swapping endpoint order.
  reverse_xy=xy(:,2:1:-1)
  reverse_ps=ps(2:1:-1)
  reverse_sample=p_sample(2:1:-1)
  reverse_wind(:,:,1)=wind(:,:,2)
  reverse_wind(:,:,2)=wind(:,:,1)
  reverse_variance(:,:,1)=variance(:,:,2)
  reverse_variance(:,:,2)=variance(:,:,1)
  reverse_sw(:,1)=sample_wind(:,2)
  reverse_sw(:,2)=sample_wind(:,1)
  reverse_sv(:,1)=sample_variance(:,2)
  reverse_sv(:,2)=sample_variance(:,1)
  call fit_edge_transport(reverse_xy,reverse_ps,pt,p,reverse_wind, &
      reverse_variance,reverse_sample,reverse_sw,reverse_sv,reverse_fit, &
      reverse_innovation,reverse_flux,reverse_uncovered,ok)
  call check(ok.and.abs(flux_cross)>1._real64.and. &
      abs(reverse_flux+flux_cross)<1.e-8_real64*max(1._real64,abs(flux_cross)), &
      'reversed shared face has one opposite flux sign')
  call check(abs(reverse_uncovered-uncovered)<1.e-12_real64.and. &
      maxval(abs(reverse_fit(:,:,1)-fit_cross(:,:,2)))<1.e-8_real64.and. &
      maxval(abs(reverse_fit(:,:,2)-fit_cross(:,:,1)))<1.e-8_real64, &
      'reversed shared face swaps endpoint profiles')

  ! Independent piecewise-knot regression: the same V profile is supplied at
  ! both endpoints, while p_sample runs from 90 kPa through the 80 and 40 kPa
  ! knots to 30 kPa.  The exact scalar pressure integral is (11465/54)*1000;
  ! with the oriented normal [0,-2], the flux is -11465/27*1000.
  call piecewise_crossing_case()
  call fit_edge_transport(xy,ps,pt,p,wind,variance,p_sample,sample_wind, &
      sample_variance,fitted,innovation,flux,uncovered,ok)
  call check(ok,'independent piecewise crossing accepted')
  call check(abs(flux+11465._real64/27._real64*1000._real64)<1.e-8_real64, &
      'independent piecewise crossing analytic flux')
  call check(maxval(abs(fitted-wind))<1.e-12_real64.and. &
      maxval(abs(innovation))<1.e-12_real64, &
      'independent piecewise crossing has no innovation')

  ! Successful and failed calls must not modify any input, including the late
  ! endpoint that proves failure is transactional rather than partial.
  call constant_case()
  call save_inputs()
  call fit_edge_transport(xy,ps,pt,p,wind,variance,p_sample,sample_wind, &
      sample_variance,fitted,innovation,flux,uncovered,ok)
  call check(ok.and.inputs_unchanged(),'successful fit leaves inputs immutable')
  call constant_case()
  variance(:,2,2)=nan
  call expect_rejection('late NaN failure has no partial outputs')

  ! Domain, geometry, variance, and finite-value contracts fail closed with
  ! NaN in every output slot.
  call constant_case(); p_sample(1)=p(1)+1._real64
  call expect_rejection('sample above highest knot rejected')
  call constant_case(); p_sample(1)=p(size(p))-1._real64
  call expect_rejection('sample pressure below lowest knot rejected')
  call constant_case(); pt=p(size(p))-1._real64
  call expect_rejection('top below pressure domain rejected')
  call constant_case(); pt=p(1)+1._real64
  call expect_rejection('top above pressure domain rejected')
  call constant_case(); ps(1)=p(1)-1._real64
  call expect_rejection('highest knot above common ground rejected')
  call constant_case(); variance(1,1,1)=0._real64
  call expect_rejection('zero variance rejected')
  call constant_case(); variance(1,1,1)=-1._real64
  call expect_rejection('negative variance rejected')
  call constant_case(); variance(1,1,1)=1.e-120_real64
  call expect_rejection('variance below inherited envelope rejected')
  call constant_case(); sample_variance(1,1)=1.e-120_real64
  call expect_rejection('sample variance below inherited envelope rejected')

  call constant_case(); xy(1,1)=nan
  call expect_rejection('NaN xy rejected')
  call constant_case(); ps(1)=nan
  call expect_rejection('NaN ps rejected')
  call constant_case(); pt=nan
  call expect_rejection('NaN top rejected')
  call constant_case(); p(1)=nan
  call expect_rejection('NaN pressure knot rejected')
  call constant_case(); wind(1,1,1)=nan
  call expect_rejection('NaN wind rejected')
  call constant_case(); variance(1,1,1)=nan
  call expect_rejection('NaN variance rejected')
  call constant_case(); p_sample(1)=nan
  call expect_rejection('NaN sample pressure rejected')
  call constant_case(); sample_wind(1,1)=nan
  call expect_rejection('NaN sample wind rejected')
  call constant_case(); sample_variance(1,1)=nan
  call expect_rejection('NaN sample variance rejected')

  print '(a,i0)', 'profile face checks passed: ',checks

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

  subroutine constant_case()
    xy(:,1)=[0._real64,0._real64]
    xy(:,2)=[4._real64,3._real64]
    ps=[118000._real64,108000._real64]
    pt=5000._real64
    p=[100000._real64,87000._real64,43000._real64,5000._real64]
    p_sample=[96000._real64,90000._real64]
    variance=9._real64
    sample_variance=9._real64
    wind(:,1,1)=2._real64
    wind(:,2,1)=-1._real64
    wind(:,1,2)=6._real64
    wind(:,2,2)=5._real64
    sample_wind(:,1)=[2._real64,-1._real64]
    sample_wind(:,2)=[6._real64,5._real64]
  end subroutine constant_case

  subroutine affine_case()
    call constant_case()
    ! The caller supplies the affine profile and matching samples.
  end subroutine affine_case

  subroutine affine_cap_case()
    call constant_case()
    p_sample=[90000._real64,90000._real64]
    a(:,1)=[1.5_real64,-2._real64]
    a(:,2)=[4.5_real64,3._real64]
    b(:,1)=[2.e-4_real64,-1.e-4_real64]
    b(:,2)=[1.e-4_real64,-2.e-4_real64]
    do e=1,2
      do c=1,2
        do k=1,size(p)
          wind(k,c,e)=a(c,e)+b(c,e)*(p(k)-pt)
        end do
        sample_wind(c,e)=a(c,e)+b(c,e)*(p_sample(e)-pt)
      end do
    end do
  end subroutine affine_cap_case

  subroutine crossing_case()
    call constant_case()
    ps=[112000._real64,110000._real64]
    wind(:,1,1)=[1._real64,7._real64,2._real64,-3._real64]
    wind(:,2,1)=[-2._real64,4._real64,1._real64,5._real64]
    wind(:,1,2)=[3._real64,-1._real64,8._real64,2._real64]
    wind(:,2,2)=[5._real64,0._real64,-4._real64,1._real64]
    variance=3._real64
    sample_variance=3._real64
  end subroutine crossing_case

  subroutine piecewise_crossing_case()
    xy(:,1)=[0._real64,0._real64]
    xy(:,2)=[2._real64,0._real64]
    ps=[110000._real64,105000._real64]
    pt=10000._real64
    p=[100000._real64,80000._real64,40000._real64,10000._real64]
    p_sample=[90000._real64,30000._real64]
    variance=1._real64
    sample_variance=1._real64
    wind=0._real64
    wind(:,2,1)=[0._real64,2._real64,4._real64,6._real64]
    wind(:,2,2)=wind(:,2,1)
    sample_wind=0._real64
  sample_wind(2,:)=[1._real64,14._real64/3._real64]
  end subroutine piecewise_crossing_case

  subroutine save_inputs()
    xy_saved=xy
    ps_saved=ps
    pt_saved=pt
    p_saved=p
    wind_saved=wind
    variance_saved=variance
    p_sample_saved=p_sample
    sample_wind_saved=sample_wind
    sample_variance_saved=sample_variance
  end subroutine save_inputs

  logical function inputs_unchanged()
    inputs_unchanged=all(xy==xy_saved).and.all(ps==ps_saved).and.pt==pt_saved.and. &
        all(p==p_saved).and.all(wind==wind_saved).and.all(variance==variance_saved).and. &
        all(p_sample==p_sample_saved).and.all(sample_wind==sample_wind_saved).and. &
        all(sample_variance==sample_variance_saved)
  end function inputs_unchanged

  subroutine expect_rejection(label)
    character(*), intent(in) :: label
    call fit_edge_transport(xy,ps,pt,p,wind,variance,p_sample,sample_wind, &
        sample_variance,fitted,innovation,flux,uncovered,ok)
    call check(.not.ok.and.all(ieee_is_nan(fitted)).and. &
        all(ieee_is_nan(innovation)).and.ieee_is_nan(flux).and. &
        ieee_is_nan(uncovered),label)
  end subroutine expect_rejection

end program test_qbal_profile_face
