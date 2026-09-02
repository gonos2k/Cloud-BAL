PROGRAM test_missing_phase_continuity
  USE, INTRINSIC :: iso_fortran_env, ONLY: real64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite,ieee_value,ieee_quiet_nan
  USE cloud_bal_state, ONLY: STATUS_OK,STATUS_FAILED
  USE cloud_bal_column_physics, ONLY: PHASE_UNKNOWN,PHASE_RAIN,PHASE_SNOW, &
    PHASE_FREEZING_RAIN,PHASE_SLEET,PHASE_GRAUPEL,missing_phase_partition, &
    allocate_precipitation_phase,terminal_velocity
  IMPLICIT NONE

  INTEGER :: failures

  failures=0
  CALL test_partition_closure(failures)
  CALL test_representable_boundary_continuity(failures)
  CALL test_partition_velocity_consistency(failures)
  CALL test_explicit_phase_unchanged(failures)
  CALL test_finite_range_guards(failures)
  IF (failures/=0) THEN
    PRINT *,'Missing-phase continuity tests failed:',failures
    ERROR STOP 1
  END IF
  PRINT *,'Missing-phase continuity tests passed'

CONTAINS

  SUBROUTINE check(condition,message,failures)
    LOGICAL, INTENT(IN) :: condition
    CHARACTER(LEN=*), INTENT(IN) :: message
    INTEGER, INTENT(INOUT) :: failures
    IF (.NOT.condition) THEN
      failures=failures+1
      PRINT *,'FAIL: ',TRIM(message)
    END IF
  END SUBROUTINE check

  SUBROUTINE test_partition_closure(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64), PARAMETER :: temperatures(11)=(/ &
      150.0_real64,260.0_real64,268.149_real64,268.15_real64, &
      268.151_real64,270.0_real64,273.15_real64,275.149_real64, &
      275.15_real64,275.151_real64,350.0_real64/)
    REAL(real64), PARAMETER :: total=0.004_real64
    REAL(real64) :: rain_fraction,snow_fraction,graupel_fraction
    REAL(real64) :: rain,snow,graupel,previous_rain
    INTEGER :: n,status

    previous_rain=-1.0_real64
    DO n=1,SIZE(temperatures)
      CALL missing_phase_partition(temperatures(n),rain_fraction,snow_fraction, &
                                   graupel_fraction,status)
      CALL check(status==STATUS_OK,'finite in-range partition must succeed',failures)
      CALL check(ieee_is_finite(rain_fraction) .AND. &
                 ieee_is_finite(snow_fraction) .AND. &
                 ieee_is_finite(graupel_fraction), &
                 'phase fractions must be finite',failures)
      CALL check(MIN(rain_fraction,snow_fraction,graupel_fraction)>=0.0_real64 .AND. &
                 MAX(rain_fraction,snow_fraction,graupel_fraction)<=1.0_real64, &
                 'phase fractions must remain in [0,1]',failures)
      CALL check(ABS(rain_fraction+snow_fraction+graupel_fraction-1.0_real64)<= &
                 8.0_real64*EPSILON(1.0_real64), &
                 'phase fractions must close',failures)
      CALL check(graupel_fraction==0.0_real64, &
                 'temperature-only fallback must not infer graupel',failures)
      CALL check(rain_fraction>=previous_rain, &
                 'rain fraction must be monotone with temperature',failures)
      previous_rain=rain_fraction

      CALL allocate_precipitation_phase(total,temperatures(n),PHASE_UNKNOWN, &
                                        rain,snow,graupel,status)
      CALL check(status==STATUS_OK,'unknown-phase allocation must succeed',failures)
      CALL check(ABS(rain+snow+graupel-total)<= &
                 16.0_real64*EPSILON(1.0_real64)*total, &
                 'unknown-phase allocation must conserve mass',failures)
      CALL check(ABS(rain-total*rain_fraction)<= &
                 16.0_real64*EPSILON(1.0_real64)*total .AND. &
                 ABS(snow-total*snow_fraction)<= &
                 16.0_real64*EPSILON(1.0_real64)*total .AND. graupel==0.0_real64, &
                 'allocation must use the shared fallback partition',failures)
    END DO
  END SUBROUTINE test_partition_closure

  SUBROUTINE test_representable_boundary_continuity(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64), PARAMETER :: boundaries(2)=(/268.15_real64,275.15_real64/)
    REAL(real64) :: left,center,right,rf(3),sf(3),gf(3),vt(3),relative(3),transit(3)
    REAL(real64) :: near_left,near_right,near_rf(2),near_sf,near_gf
    REAL(real64) :: near_vt(2),near_relative,near_transit(2)
    INTEGER :: boundary,n,status

    DO boundary=1,SIZE(boundaries)
      center=boundaries(boundary)
      left=NEAREST(center,-1.0_real64)
      right=NEAREST(center,1.0_real64)
      CALL evaluate_fallback(left,rf(1),sf(1),gf(1),vt(1),relative(1),transit(1),status)
      CALL check(status==STATUS_OK,'left adjacent value must evaluate',failures)
      CALL evaluate_fallback(center,rf(2),sf(2),gf(2),vt(2),relative(2),transit(2),status)
      CALL check(status==STATUS_OK,'boundary value must evaluate',failures)
      CALL evaluate_fallback(right,rf(3),sf(3),gf(3),vt(3),relative(3),transit(3),status)
      CALL check(status==STATUS_OK,'right adjacent value must evaluate',failures)

      DO n=1,2
        CALL check(ABS(rf(n+1)-rf(n))<=256.0_real64*EPSILON(1.0_real64), &
                   'phase fraction must be adjacent-representable continuous',failures)
        CALL check(ABS(vt(n+1)-vt(n))<= &
                   256.0_real64*EPSILON(1.0_real64)*MAX(1.0_real64,ABS(vt(n))), &
                   'fall speed must be adjacent-representable continuous',failures)
        CALL check(ABS(relative(n+1)-relative(n))<= &
                   256.0_real64*EPSILON(1.0_real64)*MAX(1.0_real64,ABS(relative(n))), &
                   'relative fall speed must be adjacent-representable continuous',failures)
        CALL check(ABS(transit(n+1)-transit(n))<= &
                   512.0_real64*EPSILON(1.0_real64)*MAX(1.0_real64,ABS(transit(n))), &
                   'fall transit time must be adjacent-representable continuous',failures)
      END DO

      near_left=center-1.0e-6_real64
      near_right=center+1.0e-6_real64
      CALL evaluate_fallback(near_left,near_rf(1),near_sf,near_gf,near_vt(1), &
                             near_relative,near_transit(1),status)
      CALL check(status==STATUS_OK,'near-left value must evaluate',failures)
      CALL evaluate_fallback(near_right,near_rf(2),near_sf,near_gf,near_vt(2), &
                             near_relative,near_transit(2),status)
      CALL check(status==STATUS_OK,'near-right value must evaluate',failures)
      CALL check(ABS(near_rf(2)-near_rf(1))<1.0e-8_real64, &
                 'phase fraction must have no near-boundary jump',failures)
      CALL check(ABS(near_vt(2)-near_vt(1))<1.0e-6_real64, &
                 'fall speed must have no near-boundary jump',failures)
      CALL check(ABS(near_transit(2)-near_transit(1))<1.0e-3_real64, &
                 'trajectory time must have no near-boundary jump',failures)
    END DO
  END SUBROUTINE test_representable_boundary_continuity

  SUBROUTINE evaluate_fallback(temperature,rain_fraction,snow_fraction, &
                               graupel_fraction,vt,relative,transit,status)
    REAL(real64), INTENT(IN) :: temperature
    REAL(real64), INTENT(OUT) :: rain_fraction,snow_fraction,graupel_fraction
    REAL(real64), INTENT(OUT) :: vt,relative,transit
    INTEGER, INTENT(OUT) :: status
    INTEGER :: velocity_status

    CALL missing_phase_partition(temperature,rain_fraction,snow_fraction, &
                                 graupel_fraction,status)
    IF (status/=STATUS_OK) RETURN
    vt=terminal_velocity(PHASE_UNKNOWN,80000.0_real64,temperature,30.0_real64, &
                         velocity_status)
    IF (velocity_status/=STATUS_OK) THEN
      status=STATUS_FAILED
      RETURN
    END IF
    relative=vt-0.25_real64
    transit=1000.0_real64/MAX(relative,0.30_real64)
    IF (.NOT.ieee_is_finite(vt) .OR. .NOT.ieee_is_finite(relative) .OR. &
        .NOT.ieee_is_finite(transit)) status=STATUS_FAILED
  END SUBROUTINE evaluate_fallback

  SUBROUTINE test_partition_velocity_consistency(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: temperature,rain,snow,graupel,vt,vr,vs,vg,expected
    INTEGER :: n,status,status_r,status_s,status_g

    DO n=0,56
      temperature=264.0_real64+0.25_real64*REAL(n,real64)
      CALL allocate_precipitation_phase(1.0_real64,temperature,PHASE_UNKNOWN, &
                                        rain,snow,graupel,status)
      vt=terminal_velocity(PHASE_UNKNOWN,80000.0_real64,temperature,30.0_real64,status)
      vr=terminal_velocity(PHASE_RAIN,80000.0_real64,temperature,30.0_real64,status_r)
      vs=terminal_velocity(PHASE_SNOW,80000.0_real64,temperature,30.0_real64,status_s)
      vg=terminal_velocity(PHASE_GRAUPEL,80000.0_real64,temperature,30.0_real64,status_g)
      expected=rain*vr+snow*vs+graupel*vg
      CALL check(status==STATUS_OK .AND. status_r==STATUS_OK .AND. &
                 status_s==STATUS_OK .AND. status_g==STATUS_OK, &
                 'all fall-speed components must evaluate',failures)
      CALL check(ABS(vt-expected)<=64.0_real64*EPSILON(1.0_real64)* &
                 MAX(1.0_real64,ABS(expected)), &
                 'unknown fall speed must use allocation phase fractions',failures)
    END DO
  END SUBROUTINE test_partition_velocity_consistency

  SUBROUTINE test_explicit_phase_unchanged(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64), PARAMETER :: total=0.004_real64
    REAL(real64) :: rain,snow,graupel,vr,vf,vsl
    INTEGER :: status,status_f,status_sl

    CALL allocate_precipitation_phase(total,250.0_real64,PHASE_RAIN, &
                                      rain,snow,graupel,status)
    CALL check(status==STATUS_OK .AND. rain==total .AND. snow==0.0_real64 .AND. &
               graupel==0.0_real64,'explicit rain allocation must be unchanged',failures)
    CALL allocate_precipitation_phase(total,300.0_real64,PHASE_SNOW, &
                                      rain,snow,graupel,status)
    CALL check(status==STATUS_OK .AND. rain==0.0_real64 .AND. snow==total .AND. &
               graupel==0.0_real64,'explicit snow allocation must be unchanged',failures)
    CALL allocate_precipitation_phase(total,270.0_real64,PHASE_FREEZING_RAIN, &
                                      rain,snow,graupel,status)
    CALL check(status==STATUS_OK .AND. rain==0.75_real64*total .AND. &
               graupel==0.25_real64*total, &
               'explicit freezing-rain allocation must be unchanged',failures)
    CALL allocate_precipitation_phase(total,270.0_real64,PHASE_SLEET, &
                                      rain,snow,graupel,status)
    CALL check(status==STATUS_OK .AND. snow==0.50_real64*total .AND. &
               graupel==0.50_real64*total, &
               'explicit sleet allocation must be unchanged',failures)
    CALL allocate_precipitation_phase(total,270.0_real64,PHASE_GRAUPEL, &
                                      rain,snow,graupel,status)
    CALL check(status==STATUS_OK .AND. graupel==total, &
               'explicit graupel allocation must be unchanged',failures)

    vr=terminal_velocity(PHASE_RAIN,80000.0_real64,270.0_real64,30.0_real64,status)
    vf=terminal_velocity(PHASE_FREEZING_RAIN,80000.0_real64,270.0_real64, &
                         30.0_real64,status_f)
    vsl=terminal_velocity(PHASE_SLEET,80000.0_real64,270.0_real64, &
                          30.0_real64,status_sl)
    CALL check(status==STATUS_OK .AND. status_f==STATUS_OK .AND. &
               status_sl==STATUS_OK .AND. vr==vf .AND. vr==vsl, &
               'explicit liquid-family fall speed must be unchanged',failures)
  END SUBROUTINE test_explicit_phase_unchanged

  SUBROUTINE test_finite_range_guards(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: nan,rain,snow,graupel,vt
    INTEGER :: status

    nan=ieee_value(0.0_real64,ieee_quiet_nan)
    CALL missing_phase_partition(nan,rain,snow,graupel,status)
    CALL check(status==STATUS_FAILED .AND. rain==0.0_real64 .AND. &
               snow==0.0_real64 .AND. graupel==0.0_real64, &
               'NaN partition input must fail closed',failures)
    CALL missing_phase_partition(149.0_real64,rain,snow,graupel,status)
    CALL check(status==STATUS_FAILED,'low temperature must fail partition range',failures)
    CALL missing_phase_partition(351.0_real64,rain,snow,graupel,status)
    CALL check(status==STATUS_FAILED,'high temperature must fail partition range',failures)

    CALL allocate_precipitation_phase(-1.0_real64,270.0_real64,PHASE_UNKNOWN, &
                                      rain,snow,graupel,status)
    CALL check(status==STATUS_FAILED .AND. rain==0.0_real64 .AND. &
               snow==0.0_real64 .AND. graupel==0.0_real64, &
               'negative mass must fail allocation closed',failures)
    CALL allocate_precipitation_phase(1.0_real64,nan,PHASE_UNKNOWN, &
                                      rain,snow,graupel,status)
    CALL check(status==STATUS_FAILED,'NaN temperature must fail allocation',failures)
    CALL allocate_precipitation_phase(1.0_real64,270.0_real64,99, &
                                      rain,snow,graupel,status)
    CALL check(status==STATUS_FAILED,'invalid phase must fail allocation',failures)

    vt=terminal_velocity(PHASE_UNKNOWN,100.0_real64,270.0_real64,30.0_real64,status)
    CALL check(status==STATUS_FAILED .AND. vt==0.0_real64, &
               'invalid pressure must fail fall speed closed',failures)
    vt=terminal_velocity(PHASE_UNKNOWN,80000.0_real64,351.0_real64,30.0_real64,status)
    CALL check(status==STATUS_FAILED .AND. vt==0.0_real64, &
               'invalid temperature must fail fall speed closed',failures)
    vt=terminal_velocity(PHASE_UNKNOWN,80000.0_real64,270.0_real64,101.0_real64,status)
    CALL check(status==STATUS_FAILED .AND. vt==0.0_real64, &
               'invalid reflectivity must fail fall speed closed',failures)
    vt=terminal_velocity(99,80000.0_real64,270.0_real64,30.0_real64,status)
    CALL check(status==STATUS_FAILED .AND. vt==0.0_real64, &
               'invalid phase must fail fall speed closed',failures)
    vt=terminal_velocity(PHASE_UNKNOWN,80000.0_real64,nan,30.0_real64,status)
    CALL check(status==STATUS_FAILED .AND. vt==0.0_real64 .AND. ieee_is_finite(vt), &
               'NaN fall-speed input must fail with finite output',failures)
  END SUBROUTINE test_finite_range_guards

END PROGRAM test_missing_phase_continuity
