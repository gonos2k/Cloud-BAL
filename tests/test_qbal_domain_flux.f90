program test_qbal_domain_flux
  use iso_fortran_env, only: real64
  use ieee_arithmetic, only: ieee_is_nan, ieee_quiet_nan, ieee_value
  use qbal_domain_flux
  implicit none
  integer, parameter :: nc=2,ne=5
  integer :: incidence(3,nc),bad_incidence(3,nc),checks
  integer :: boundary_unknown,internal_unknown,top_unknown
  real(real64) :: surface(nc),covered(ne),missing(ne),top(nc),subtotal,residual,nan_value
  logical :: missing_known(ne),top_known(nc),complete,orientation_ok,ok
  real(real64) :: expected_cell(nc)

  checks=0
  nan_value=ieee_value(0._real64,ieee_quiet_nan)
  ! Edge 2 is shared.  Boundary edges are 1, 3, 4 and 5.
  incidence=reshape([1,2,3,-2,4,5],[3,nc])
  surface=[10._real64,20._real64]
  covered=[1._real64,2._real64,3._real64,4._real64,5._real64]
  missing=[.1_real64,.2_real64,.3_real64,.4_real64,.5_real64]
  missing_known=.true.
  top=[3._real64,4._real64]
  top_known=.true.

  call domain_flux_budget(incidence,surface,covered,missing,missing_known,top,top_known, &
                          subtotal,residual,complete,boundary_unknown,orientation_ok,ok, &
                          internal_unknown,top_unknown)
  expected_cell=[10._real64+1.1_real64+2.2_real64+3.3_real64-3._real64, &
                 20._real64-2.2_real64+4.4_real64+5.5_real64-4._real64]
  call check(ok.and.orientation_ok,'valid incidence accepted')
  call check(complete.and.boundary_unknown==0.and.internal_unknown==0.and.top_unknown==0, &
             'fully known external terms complete')
  call check(abs(residual-sum(expected_cell))<1.e-12_real64, &
             'global residual equals sum of complete column budgets')
  call check(abs(subtotal-residual)<1.e-12_real64,'known subtotal equals full residual when complete')

  ! An unresolved shared face is not an external unknown: its two signed
  ! contributions cancel before the domain sum.
  missing(2)=nan_value
  missing_known(2)=.false.
  call domain_flux_budget(incidence,surface,covered,missing,missing_known,top,top_known, &
                          subtotal,residual,complete,boundary_unknown,orientation_ok,ok, &
                          internal_unknown,top_unknown)
  call check(ok.and.complete.and.internal_unknown==1.and.boundary_unknown==0, &
             'unknown internal face cancels globally')
  call check(abs(residual-sum(expected_cell))<1.e-12_real64, &
             'internal unknown does not change global residual')

  ! A missing boundary strip stays unresolved and is counted exactly once.
  missing(1)=nan_value
  missing_known(1)=.false.
  call domain_flux_budget(incidence,surface,covered,missing,missing_known,top,top_known, &
                          subtotal,residual,complete,boundary_unknown,orientation_ok,ok, &
                          internal_unknown,top_unknown)
  call check(ok.and.orientation_ok.and..not.complete.and.boundary_unknown==1, &
             'unknown boundary face is reported')
  call check(ieee_is_nan(residual),'unknown boundary face keeps full residual NaN')
  call check(abs(subtotal-(sum(expected_cell)-.1_real64))<1.e-12_real64, &
             'known subtotal excludes only unresolved boundary fill')

  ! Invalid same-sign shared incidence must not be silently treated as a
  ! boundary or accepted as a cancellation pair.
  bad_incidence=incidence
  bad_incidence(1,2)=2
  missing=0._real64
  missing_known=.true.
  call domain_flux_budget(bad_incidence,surface,covered,missing,missing_known,top,top_known, &
                          subtotal,residual,complete,boundary_unknown,orientation_ok,ok, &
                          internal_unknown,top_unknown)
  call check(.not.ok.and..not.orientation_ok,'same-sign internal incidence rejected')
  call check(ieee_is_nan(subtotal).and.ieee_is_nan(residual),'invalid incidence has no budget')

  bad_incidence=incidence
  bad_incidence(1,2)=ne+1
  call domain_flux_budget(bad_incidence,surface,covered,missing,missing_known,top,top_known, &
                          subtotal,residual,complete,boundary_unknown,orientation_ok,ok)
  call check(.not.ok.and..not.orientation_ok,'out-of-range edge id rejected before abs')
  surface(1)=1.e101_real64
  call domain_flux_budget(incidence,surface,covered,missing,missing_known,top,top_known, &
                          subtotal,residual,complete,boundary_unknown,orientation_ok,ok)
  call check(.not.ok,'finite magnitude envelope rejects overflow input')
  print '(a,i0)', 'domain flux checks passed: ',checks

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

end program test_qbal_domain_flux
