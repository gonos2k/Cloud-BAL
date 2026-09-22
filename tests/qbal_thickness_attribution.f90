! Small research-only attribution of hydrostatic thickness changes.
!
! Endpoint index 1 is the bottom of the layer (pb), and endpoint index 2 is
! the top (pt).  The inputs use specific humidity, so virtual temperature is
! Tv = T * (1 + (1/0.622 - 1) * q).  No production state or equation of state
! is consulted here.
MODULE qbal_thickness_attribution
  USE, INTRINSIC :: iso_fortran_env, ONLY: real64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite, ieee_quiet_nan, &
                                           ieee_value
  IMPLICIT NONE
  PRIVATE

  REAL(real64), PARAMETER :: RD_AIR=287.05_real64
  REAL(real64), PARAMETER :: G0=9.80665_real64
  REAL(real64), PARAMETER :: EPSILON_WATER=0.622_real64
  REAL(real64), PARAMETER :: ALPHA=1.0_real64/EPSILON_WATER-1.0_real64
  REAL(real64), PARAMETER :: MIN_PRESSURE=100.0_real64
  REAL(real64), PARAMETER :: MAX_PRESSURE=120000.0_real64
  REAL(real64), PARAMETER :: MIN_TEMPERATURE=100.0_real64
  REAL(real64), PARAMETER :: MAX_TEMPERATURE=500.0_real64
  REAL(real64), PARAMETER :: MIN_HUMIDITY=0.0_real64
  REAL(real64), PARAMETER :: MAX_HUMIDITY=1.0_real64
  REAL(real64), PARAMETER :: CLOSURE_FACTOR=128.0_real64

  PUBLIC :: thickness_change

CONTAINS

  SUBROUTINE thickness_change(pb,pt,ta,qa,tf,qf,before,after,temp,moist, &
                              total,arithmetic_bound,ok)
    REAL(real64), INTENT(IN) :: pb,pt
    REAL(real64), INTENT(IN) :: ta(2),qa(2),tf(2),qf(2)
    REAL(real64), INTENT(OUT) :: before,after,temp,moist,total
    REAL(real64), INTENT(OUT) :: arithmetic_bound
    LOGICAL, INTENT(OUT) :: ok
    REAL(real64) :: nan
    REAL(real64) :: tv_before(2),tv_after(2)
    REAL(real64) :: delta_tv_temperature(2),delta_tv_humidity(2)
    REAL(real64) :: log_pressure_ratio,layer_factor
    REAL(real64) :: before_work,after_work,temp_work,moist_work,total_work
    REAL(real64) :: uncancelled_scale,closure,state_closure,bound_work

    nan=ieee_value(0.0_real64,ieee_quiet_nan)
    before=nan
    after=nan
    temp=nan
    moist=nan
    total=nan
    arithmetic_bound=nan
    ok=.FALSE.

    IF (.NOT.ieee_is_finite(pb) .OR. .NOT.ieee_is_finite(pt) .OR. &
        .NOT.all(ieee_is_finite(ta)) .OR. .NOT.all(ieee_is_finite(qa)) .OR. &
        .NOT.all(ieee_is_finite(tf)) .OR. .NOT.all(ieee_is_finite(qf))) RETURN
    IF (pt<MIN_PRESSURE .OR. pt>=pb .OR. pb>MAX_PRESSURE) RETURN
    IF (ANY(ta<MIN_TEMPERATURE) .OR. ANY(ta>MAX_TEMPERATURE) .OR. &
        ANY(tf<MIN_TEMPERATURE) .OR. ANY(tf>MAX_TEMPERATURE)) RETURN
    IF (ANY(qa<MIN_HUMIDITY) .OR. ANY(qa>=MAX_HUMIDITY) .OR. &
        ANY(qf<MIN_HUMIDITY) .OR. ANY(qf>=MAX_HUMIDITY)) RETURN

    log_pressure_ratio=LOG(pb/pt)
    IF (.NOT.ieee_is_finite(log_pressure_ratio) .OR. log_pressure_ratio<=0.0_real64) RETURN
    layer_factor=RD_AIR/G0*log_pressure_ratio
    IF (.NOT.ieee_is_finite(layer_factor) .OR. layer_factor<=0.0_real64) RETURN

    tv_before=ta*(1.0_real64+ALPHA*qa)
    tv_after=tf*(1.0_real64+ALPHA*qf)
    IF (.NOT.all(ieee_is_finite(tv_before)) .OR. &
        .NOT.all(ieee_is_finite(tv_after)) .OR. &
        ANY(tv_before<=0.0_real64) .OR. ANY(tv_after<=0.0_real64)) RETURN

    ! These endpoint identities are exact in real arithmetic.  They use the
    ! arithmetic midpoint state so the same trapezoid is used for every term.
    delta_tv_temperature=(1.0_real64+ALPHA*(qf+qa)/2.0_real64)*(tf-ta)
    delta_tv_humidity=ALPHA*(tf+ta)/2.0_real64*(qf-qa)
    IF (.NOT.all(ieee_is_finite(delta_tv_temperature)) .OR. &
        .NOT.all(ieee_is_finite(delta_tv_humidity))) RETURN

    before_work=layer_factor*0.5_real64*SUM(tv_before)
    after_work=layer_factor*0.5_real64*SUM(tv_after)
    temp_work=layer_factor*0.5_real64*SUM(delta_tv_temperature)
    moist_work=layer_factor*0.5_real64*SUM(delta_tv_humidity)
    ! Compute the total independently from the two attribution terms.
    total_work=layer_factor*0.5_real64*SUM(tv_after-tv_before)
    IF (.NOT.ieee_is_finite(before_work) .OR. &
        .NOT.ieee_is_finite(after_work) .OR. &
        .NOT.ieee_is_finite(temp_work) .OR. &
        .NOT.ieee_is_finite(moist_work) .OR. &
        .NOT.ieee_is_finite(total_work)) RETURN

    ! The closure check is an arithmetic check only.  Its scale retains all
    ! uncancelled endpoint and contribution magnitudes for near cancellation.
    uncancelled_scale=ABS(before_work)+ABS(after_work)+ABS(temp_work)+ABS(moist_work)
    IF (.NOT.ieee_is_finite(uncancelled_scale) .OR. uncancelled_scale<=0.0_real64) RETURN
    bound_work=CLOSURE_FACTOR*EPSILON(1.0_real64)*uncancelled_scale
    closure=total_work-(temp_work+moist_work)
    state_closure=(after_work-before_work)-total_work
    IF (.NOT.ieee_is_finite(bound_work) .OR. bound_work<0.0_real64 .OR. &
        .NOT.ieee_is_finite(closure) .OR. ABS(closure)>bound_work .OR. &
        .NOT.ieee_is_finite(state_closure) .OR. ABS(state_closure)>bound_work) RETURN

    before=before_work
    after=after_work
    temp=temp_work
    moist=moist_work
    total=total_work
    arithmetic_bound=bound_work
    ok=.TRUE.
  END SUBROUTINE thickness_change

END MODULE qbal_thickness_attribution
