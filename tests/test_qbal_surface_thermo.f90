PROGRAM test_qbal_surface_thermo
  USE, INTRINSIC :: iso_fortran_env, ONLY: real64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value,ieee_quiet_nan,ieee_is_finite
  USE qbal_surface_thermo
  USE qbal_lower_transport, ONLY: pressure_at_height
  IMPLICIT NONE

  INTEGER :: failures

  failures=0
  CALL test_isothermal_moist_control(failures)
  CALL test_dry_limit(failures)
  CALL test_sensitivities(failures)
  CALL test_zero_height(failures)
  CALL test_no_pressure_level_jump(failures)
  CALL test_invalid_inputs(failures)
  CALL test_linear_log_pressure_defect(failures)

  IF (failures/=0) THEN
    PRINT '(A,I0)', 'Surface thermodynamics tests failed: ',failures
    ERROR STOP 1
  END IF
  PRINT '(A)', 'Surface thermodynamics tests passed'

CONTAINS

  SUBROUTINE check(condition,message,failures)
    LOGICAL, INTENT(IN) :: condition
    CHARACTER(LEN=*), INTENT(IN) :: message
    INTEGER, INTENT(INOUT) :: failures
    IF (.NOT.condition) THEN
      failures=failures+1
      PRINT '(A)', 'FAIL: '//TRIM(message)
    END IF
  END SUBROUTINE check

  SUBROUTINE close_scalar(actual,expected,relative_tolerance,message,failures)
    REAL(real64), INTENT(IN) :: actual,expected,relative_tolerance
    CHARACTER(LEN=*), INTENT(IN) :: message
    INTEGER, INTENT(INOUT) :: failures
    CALL check(ABS(actual-expected)<=relative_tolerance*MAX(1.0_real64,ABS(expected)), &
      message,failures)
  END SUBROUTINE close_scalar

  SUBROUTINE test_isothermal_moist_control(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64), PARAMETER :: ps=100000.0_real64,temperature=280.0_real64
    REAL(real64), PARAMETER :: mixing_ratio=0.010_real64,height=50.0_real64
    REAL(real64), PARAMETER :: rd=287.05_real64,g=9.80665_real64
    REAL(real64) :: pressure,tv,dpdh,dpdtv,tv_expected,pressure_expected
    LOGICAL :: ok

    CALL thermodynamic_sample_pressure(ps,temperature,mixing_ratio,height, &
      pressure,tv,dpdh,dpdtv,ok)
    tv_expected=temperature*(1.0_real64+mixing_ratio/0.622_real64)/ &
      (1.0_real64+mixing_ratio)
    pressure_expected=ps*EXP(-g*height/(rd*tv_expected))
    CALL check(ok,'moist isothermal sample accepted',failures)
    CALL close_scalar(tv,tv_expected,1.0e-14_real64, &
      'virtual temperature follows canonical moist density',failures)
    CALL close_scalar(pressure,pressure_expected,1.0e-14_real64, &
      'isothermal moist pressure follows hydrostatic exponential',failures)
  END SUBROUTINE test_isothermal_moist_control

  SUBROUTINE test_dry_limit(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: pressure,tv,dpdh,dpdtv
    LOGICAL :: ok

    CALL thermodynamic_sample_pressure(100000.0_real64,270.0_real64,0.0_real64, &
      25.0_real64,pressure,tv,dpdh,dpdtv,ok)
    CALL check(ok,'dry limit accepted',failures)
    CALL close_scalar(tv,270.0_real64,1.0e-14_real64, &
      'dry virtual temperature equals temperature',failures)
    CALL check(pressure<100000.0_real64 .AND. dpdh<0.0_real64 .AND. dpdtv>0.0_real64, &
      'dry hydrostatic signs are correct',failures)
  END SUBROUTINE test_dry_limit

  SUBROUTINE test_sensitivities(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64), PARAMETER :: ps=101000.0_real64,t=285.0_real64,r=0.008_real64
    REAL(real64), PARAMETER :: h=40.0_real64,dh=1.0e-3_real64,dtv=1.0e-3_real64
    REAL(real64), PARAMETER :: rd=287.05_real64,g=9.80665_real64
    REAL(real64) :: p,tv,dpdh,dpdtv,pminus,pplus,tvminus,tvplus
    REAL(real64) :: finite_difference,finite_difference_tv
    LOGICAL :: ok

    CALL thermodynamic_sample_pressure(ps,t,r,h,p,tv,dpdh,dpdtv,ok)
    CALL check(ok,'sensitivity sample accepted',failures)
    pminus=ps*EXP(-g*(h-dh)/(rd*tv))
    pplus=ps*EXP(-g*(h+dh)/(rd*tv))
    finite_difference=(pplus-pminus)/(2.0_real64*dh)
    tvminus=tv-dtv
    tvplus=tv+dtv
    pminus=ps*EXP(-g*h/(rd*tvminus))
    pplus=ps*EXP(-g*h/(rd*tvplus))
    finite_difference_tv=(pplus-pminus)/(2.0_real64*dtv)
    CALL close_scalar(dpdh,finite_difference,1.0e-8_real64, &
      'height derivative agrees with centered finite difference',failures)
    CALL close_scalar(dpdtv,finite_difference_tv,1.0e-8_real64, &
      'virtual-temperature derivative agrees with centered finite difference',failures)
  END SUBROUTINE test_sensitivities

  SUBROUTINE test_zero_height(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: pressure,tv,dpdh,dpdtv
    LOGICAL :: ok

    CALL thermodynamic_sample_pressure(100500.0_real64,290.0_real64,0.012_real64, &
      0.0_real64,pressure,tv,dpdh,dpdtv,ok)
    CALL check(ok,'zero-height sample accepted',failures)
    CALL close_scalar(pressure,100500.0_real64,0.0_real64, &
      'zero height preserves surface pressure',failures)
    CALL close_scalar(dpdtv,0.0_real64,0.0_real64, &
      'zero height has zero virtual-temperature sensitivity',failures)
  END SUBROUTINE test_zero_height

  SUBROUTINE test_no_pressure_level_jump(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64), PARAMETER :: ps=100000.0_real64,t=300.0_real64,r=0.0_real64
    REAL(real64), PARAMETER :: delta=0.0078125_real64
    REAL(real64) :: below,at_level,above,tv,dpdh,dpdtv,old_below,old_above
    REAL(real64) :: levels(3),heights(3)
    LOGICAL :: ok_below,ok_level,ok_above

    levels=[100000.0_real64,95000.0_real64,90000.0_real64]
    heights=[100.0_real64,500.0_real64,1000.0_real64]
    CALL pressure_at_height(ps-delta,0.0_real64,levels,heights,10.0_real64,old_below,ok_below)
    CALL pressure_at_height(ps+delta,0.0_real64,levels,heights,10.0_real64,old_above,ok_above)
    CALL check(ok_below .AND. ok_above .AND. old_above-old_below>100.0_real64, &
      'inconsistent old height anchors reproduce pressure-level jump',failures)
    CALL thermodynamic_sample_pressure(ps-delta,t,r,10.0_real64,below,tv,dpdh,dpdtv,ok_below)
    CALL thermodynamic_sample_pressure(ps,t,r,10.0_real64,at_level,tv,dpdh,dpdtv,ok_level)
    CALL thermodynamic_sample_pressure(ps+delta,t,r,10.0_real64,above,tv,dpdh,dpdtv,ok_above)
    CALL check(ok_below .AND. ok_level .AND. ok_above, &
      'prior accepts PS below, at and above the regular pressure level',failures)
    CALL close_scalar((above-below)/(2.0_real64*delta),at_level/ps,1.0e-9_real64, &
      'prior remains proportional to PS across selector threshold',failures)
  END SUBROUTINE test_no_pressure_level_jump

  SUBROUTINE test_invalid_inputs(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: nan,tv,pressure,dpdh,dpdtv,defect
    LOGICAL :: ok

    nan=ieee_value(0.0_real64,ieee_quiet_nan)
    CALL virtual_temperature_from_mixing(nan,280.0_real64,0.01_real64,tv,ok)
    CALL check(.NOT.ok .AND. .NOT.ieee_is_finite(tv), &
      'NaN pressure rejected before comparisons',failures)
    CALL virtual_temperature_from_mixing(100000.0_real64,nan,0.01_real64,tv,ok)
    CALL check(.NOT.ok .AND. .NOT.ieee_is_finite(tv), &
      'NaN temperature rejected before comparisons',failures)
    CALL virtual_temperature_from_mixing(100000.0_real64,280.0_real64,nan,tv,ok)
    CALL check(.NOT.ok .AND. .NOT.ieee_is_finite(tv), &
      'NaN mixing ratio rejected before comparisons',failures)
    CALL virtual_temperature_from_mixing(99.0_real64,280.0_real64,0.01_real64,tv,ok)
    CALL check(.NOT.ok .AND. .NOT.ieee_is_finite(tv),'canonical pressure lower bound rejected',failures)
    CALL virtual_temperature_from_mixing(100000.0_real64,280.0_real64,0.21_real64,tv,ok)
    CALL check(.NOT.ok .AND. .NOT.ieee_is_finite(tv),'canonical mixing-ratio upper bound rejected',failures)

    CALL thermodynamic_sample_pressure(100000.0_real64,280.0_real64,0.01_real64, &
      nan,pressure,tv,dpdh,dpdtv,ok)
    CALL check(.NOT.ok .AND. .NOT.ieee_is_finite(pressure) .AND. &
      .NOT.ieee_is_finite(tv) .AND. .NOT.ieee_is_finite(dpdh) .AND. &
      .NOT.ieee_is_finite(dpdtv), &
      'NaN sample height rejected before range check',failures)
    CALL thermodynamic_sample_pressure(100000.0_real64,280.0_real64,0.01_real64, &
      -1.0_real64,pressure,tv,dpdh,dpdtv,ok)
    CALL check(.NOT.ok .AND. .NOT.any(ieee_is_finite([pressure,tv,dpdh,dpdtv])), &
      'negative sample height rejected',failures)
    CALL thermodynamic_sample_pressure(100000.0_real64,280.0_real64,0.01_real64, &
      100.1_real64,pressure,tv,dpdh,dpdtv,ok)
    CALL check(.NOT.ok .AND. .NOT.any(ieee_is_finite([pressure,tv,dpdh,dpdtv])), &
      'sample height outside research scope rejected',failures)

    CALL hydrostatic_height_defect(nan,90000.0_real64,0.0_real64,100.0_real64, &
      280.0_real64,285.0_real64,defect,ok)
    CALL check(.NOT.ok .AND. .NOT.ieee_is_finite(defect), &
      'NaN defect pressure rejected before comparisons',failures)
    CALL hydrostatic_height_defect(90000.0_real64,90001.0_real64,0.0_real64,100.0_real64, &
      280.0_real64,285.0_real64,defect,ok)
    CALL check(.NOT.ok .AND. .NOT.ieee_is_finite(defect), &
      'non-descending pressure pair rejected',failures)
    CALL hydrostatic_height_defect(100000.0_real64,99999.0_real64,0.0_real64,-2.0_real64, &
      280.0_real64,285.0_real64,defect,ok)
    CALL check(ok,'negative height difference remains a valid diagnostic',failures)
    CALL hydrostatic_height_defect(100000.0_real64,99999.0_real64,0.0_real64,2.0_real64, &
      0.0_real64,285.0_real64,defect,ok)
    CALL check(.NOT.ok .AND. .NOT.ieee_is_finite(defect), &
      'nonphysical virtual temperature rejected',failures)
  END SUBROUTINE test_invalid_inputs

  SUBROUTINE test_linear_log_pressure_defect(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64), PARAMETER :: rd=287.05_real64,g=9.80665_real64
    REAL(real64), PARAMETER :: pb=100000.0_real64,pt=90000.0_real64
    REAL(real64), PARAMETER :: tvb=280.0_real64,tvt=300.0_real64,zb=123.4_real64
    REAL(real64) :: zt,defect,offset,near_defect,near_pt,near_zt
    LOGICAL :: ok

    zt=zb+rd*0.5_real64*(tvb+tvt)/g*LOG(pb/pt)
    CALL hydrostatic_height_defect(pb,pt,zb,zt,tvb,tvt,defect,ok)
    CALL check(ok,'linear-log-pressure layer accepted',failures)
    CALL close_scalar(defect,0.0_real64,1.0e-10_real64, &
      'linear virtual temperature in log pressure has zero defect',failures)

    offset=4.25_real64
    CALL hydrostatic_height_defect(pb,pt,zb,zt+offset,tvb,tvt,defect,ok)
    CALL check(ok,'manufactured height offset accepted',failures)
    CALL close_scalar(defect,g*offset,1.0e-12_real64, &
      'manufactured height offset appears directly in defect',failures)

    near_pt=99999.0_real64
    near_zt=zb+rd*0.5_real64*(tvb+tvt)/g*LOG(pb/near_pt)
    CALL hydrostatic_height_defect(pb,near_pt,zb,near_zt,tvb,tvt,near_defect,ok)
    CALL check(ok,'near-equal pressure layer accepted',failures)
    CALL close_scalar(near_defect,0.0_real64,1.0e-10_real64, &
      'near-equal pressure defect remains numerically stable',failures)
  END SUBROUTINE test_linear_log_pressure_defect

END PROGRAM test_qbal_surface_thermo
