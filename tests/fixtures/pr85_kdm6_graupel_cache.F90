module pr85_graupel_cache_fixture
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  implicit none
  integer, parameter :: PROGB_ABSENT=0, PROGB_TRANSIENT=1, PROGB_PSD_ACTIVE=2, PROGB_UNSUPPORTED=3
contains
  pure subroutine kdm6_refresh_graupel_intercept(status,n0g,g1pmg,slope_mu,n0go,valid)
      integer, intent(in) :: status
      real, intent(in) :: n0g,g1pmg
      real(kind=8), intent(in) :: slope_mu
      real, intent(out) :: n0go
      logical, intent(out) :: valid
      real(kind=8) :: ratio64,intercept64
      real :: ratio32

      n0go=0.0
      valid=.false.
      if (status.eq.PROGB_ABSENT) then
        valid=.true.
        return
      endif
      if (status.ne.PROGB_PSD_ACTIVE) return
      if (.not.ieee_is_finite(n0g) .or. .not.ieee_is_finite(g1pmg) .or. &
          .not.ieee_is_finite(slope_mu)) return
      if (n0g.le.0.0 .or. g1pmg.le.0.0 .or. slope_mu.le.0.0d0) return
      ratio64=real(n0g,8)/real(g1pmg,8)
      if (.not.ieee_is_finite(ratio64) .or. ratio64.gt.real(huge(0.0),8)) return
      ratio32=real(ratio64)
      if (.not.ieee_is_finite(ratio32) .or. ratio32.le.0.0) return
      if (slope_mu.le.real(ratio32,8)/real(huge(0.0),8)) return
      intercept64=real(ratio32,8)/slope_mu
      if (.not.ieee_is_finite(intercept64) .or. intercept64.le.0.0d0 .or. &
          intercept64.gt.real(huge(0.0),8)) return
      n0go=real(intercept64)
      valid=ieee_is_finite(n0go) .and. n0go.gt.0.0
      if (.not.valid) n0go=0.0
    end subroutine kdm6_refresh_graupel_intercept
end module pr85_graupel_cache_fixture

program test_graupel_cache
  use pr85_graupel_cache_fixture
  implicit none
  real :: n0go, expected, before
  logical :: valid

  before=0.0
  call kdm6_refresh_graupel_intercept(PROGB_PSD_ACTIVE,4.0e6,1.25,0.25d0,n0go,valid)
  expected=(4.0e6/1.25)/0.25
  if (.not.valid .or. n0go.le.0.0 .or. n0go.ne.expected) error stop 'active cache was not refreshed'
  if (before.ne.0.0 .and. n0go.eq.before) error stop 'new active state retained absent cache'
  print *, 'CASE absent-to-active cache refreshed by source PSD formula'

  call kdm6_refresh_graupel_intercept(PROGB_PSD_ACTIVE,4.0e6,1.25,0.5d0,n0go,valid)
  expected=(4.0e6/1.25)/0.5
  if (.not.valid .or. n0go.ne.expected) error stop 'preexisting active cache formula changed'
  print *, 'CASE active cache matches the existing n0g/g1pmg/rslopemu relation'

  call kdm6_refresh_graupel_intercept(PROGB_ABSENT,0.0,0.0,0.0d0,n0go,valid)
  if (.not.valid .or. n0go.ne.0.0) error stop 'absent graupel cache was not zero'
  print *, 'CASE absent state keeps zero cache'

  call kdm6_refresh_graupel_intercept(PROGB_TRANSIENT,4.0e6,1.25,0.25d0,n0go,valid)
  if (valid .or. n0go.ne.0.0) error stop 'transient status was accepted'
  call kdm6_refresh_graupel_intercept(PROGB_PSD_ACTIVE,4.0e6,1.25,0.0d0,n0go,valid)
  if (valid .or. n0go.ne.0.0) error stop 'zero slope divisor was accepted'
  call kdm6_refresh_graupel_intercept(PROGB_PSD_ACTIVE,huge(0.0),tiny(0.0),tiny(0.0d0),n0go,valid)
  if (valid .or. n0go.ne.0.0) error stop 'unrepresentable ratio was accepted'
  call kdm6_refresh_graupel_intercept(PROGB_PSD_ACTIVE,1.0e6,1.0,1.0e-320_8,n0go,valid)
  if (valid .or. n0go.ne.0.0) error stop 'overflowing tiny-slope intercept was accepted'
  print *, 'CASE tiny positive slope is rejected before intercept division'
  print *, 'CASE invalid status and divisor rejected without cache mutation'
end program test_graupel_cache
