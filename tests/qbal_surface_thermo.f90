! Small surface thermodynamics research kernel.
!
! The vapor input is a dry-air mixing ratio (kg vapor / kg dry air).  This
! module describes only the constant-temperature, constant-mixing-ratio
! hydrostatic slab used by the surface diagnostic.  It carries no covariance
! or physical-authority state.
MODULE qbal_surface_thermo
  USE, INTRINSIC :: iso_fortran_env, ONLY: real64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite,ieee_value,ieee_quiet_nan
  USE cloud_bal_state, ONLY: moist_gas_density
  IMPLICIT NONE
  PRIVATE

  REAL(real64), PARAMETER :: RD_AIR=287.05_real64
  REAL(real64), PARAMETER :: GRAVITY=9.80665_real64
  REAL(real64), PARAMETER :: MIN_PRESSURE=100.0_real64
  REAL(real64), PARAMETER :: MAX_PRESSURE=120000.0_real64
  REAL(real64), PARAMETER :: MIN_VIRTUAL_TEMPERATURE=100.0_real64
  REAL(real64), PARAMETER :: MAX_VIRTUAL_TEMPERATURE=500.0_real64
  REAL(real64), PARAMETER :: MAX_ABS_HEIGHT=1000000.0_real64
  REAL(real64), PARAMETER :: MAX_SAMPLE_HEIGHT=100.0_real64

  PUBLIC :: thermodynamic_sample_pressure
  PUBLIC :: virtual_temperature_from_mixing
  PUBLIC :: hydrostatic_height_defect

CONTAINS

  SUBROUTINE virtual_temperature_from_mixing(p,temperature,mixing_ratio,tv,ok)
    REAL(real64), INTENT(IN) :: p,temperature,mixing_ratio
    REAL(real64), INTENT(OUT) :: tv
    LOGICAL, INTENT(OUT) :: ok
    REAL(real64) :: rho

    tv=ieee_value(0.0_real64,ieee_quiet_nan)
    ok=.FALSE.
    IF (.NOT.ieee_is_finite(p) .OR. &
        .NOT.ieee_is_finite(temperature) .OR. &
        .NOT.ieee_is_finite(mixing_ratio)) RETURN
    rho=moist_gas_density(p,temperature,mixing_ratio)
    IF (.NOT.ieee_is_finite(rho) .OR. rho<=0.0_real64) RETURN
    tv=p/(RD_AIR*rho)
    IF (.NOT.ieee_is_finite(tv) .OR. tv<MIN_VIRTUAL_TEMPERATURE .OR. &
        tv>MAX_VIRTUAL_TEMPERATURE) THEN
      tv=ieee_value(0.0_real64,ieee_quiet_nan)
      RETURN
    END IF
    ok=.TRUE.
  END SUBROUTINE virtual_temperature_from_mixing

  SUBROUTINE thermodynamic_sample_pressure(ps,temperature,mixing_ratio, &
      sample_height,p_sample,virtual_temperature, &
      dp_dheight,dp_dvirtual_temperature,ok)
    REAL(real64), INTENT(IN) :: ps,temperature,mixing_ratio
    REAL(real64), INTENT(IN) :: sample_height
    REAL(real64), INTENT(OUT) :: p_sample,virtual_temperature
    REAL(real64), INTENT(OUT) :: dp_dheight,dp_dvirtual_temperature
    LOGICAL, INTENT(OUT) :: ok
    REAL(real64) :: exponent

    p_sample=ieee_value(0.0_real64,ieee_quiet_nan)
    virtual_temperature=ieee_value(0.0_real64,ieee_quiet_nan)
    dp_dheight=ieee_value(0.0_real64,ieee_quiet_nan)
    dp_dvirtual_temperature=ieee_value(0.0_real64,ieee_quiet_nan)
    ok=.FALSE.
    IF (.NOT.ieee_is_finite(ps) .OR. &
        .NOT.ieee_is_finite(temperature) .OR. &
        .NOT.ieee_is_finite(mixing_ratio) .OR. &
        .NOT.ieee_is_finite(sample_height)) RETURN
    IF (sample_height<0.0_real64 .OR. sample_height>MAX_SAMPLE_HEIGHT) RETURN
    CALL virtual_temperature_from_mixing(ps,temperature, &
                                         mixing_ratio,virtual_temperature,ok)
    IF (.NOT.ok) RETURN

    exponent=-GRAVITY*sample_height/(RD_AIR*virtual_temperature)
    p_sample=ps*EXP(exponent)
    dp_dheight=-GRAVITY*p_sample/(RD_AIR*virtual_temperature)
    dp_dvirtual_temperature=GRAVITY*sample_height*p_sample/ &
      (RD_AIR*virtual_temperature*virtual_temperature)
    IF (.NOT.ieee_is_finite(p_sample) .OR. p_sample<=0.0_real64 .OR. &
        .NOT.ieee_is_finite(dp_dheight) .OR. &
        .NOT.ieee_is_finite(dp_dvirtual_temperature)) THEN
      p_sample=ieee_value(0.0_real64,ieee_quiet_nan)
      virtual_temperature=ieee_value(0.0_real64,ieee_quiet_nan)
      dp_dheight=ieee_value(0.0_real64,ieee_quiet_nan)
      dp_dvirtual_temperature=ieee_value(0.0_real64,ieee_quiet_nan)
      ok=.FALSE.
      RETURN
    END IF
    ok=.TRUE.
  END SUBROUTINE thermodynamic_sample_pressure

  SUBROUTINE hydrostatic_height_defect(bottom_pressure,top_pressure, &
      bottom_height,top_height,bottom_virtual_temperature, &
      top_virtual_temperature,defect,ok)
    REAL(real64), INTENT(IN) :: bottom_pressure,top_pressure
    REAL(real64), INTENT(IN) :: bottom_height,top_height
    REAL(real64), INTENT(IN) :: bottom_virtual_temperature,top_virtual_temperature
    REAL(real64), INTENT(OUT) :: defect
    LOGICAL, INTENT(OUT) :: ok
    REAL(real64) :: log_pressure_ratio

    defect=ieee_value(0.0_real64,ieee_quiet_nan)
    ok=.FALSE.
    IF (.NOT.ieee_is_finite(bottom_pressure) .OR. &
        .NOT.ieee_is_finite(top_pressure) .OR. &
        .NOT.ieee_is_finite(bottom_height) .OR. &
        .NOT.ieee_is_finite(top_height) .OR. &
        .NOT.ieee_is_finite(bottom_virtual_temperature) .OR. &
        .NOT.ieee_is_finite(top_virtual_temperature)) RETURN
    IF (bottom_pressure<MIN_PRESSURE .OR. bottom_pressure>MAX_PRESSURE .OR. &
        top_pressure<MIN_PRESSURE .OR. top_pressure>MAX_PRESSURE .OR. &
        bottom_pressure<=top_pressure) RETURN
    IF (ABS(bottom_height)>MAX_ABS_HEIGHT .OR. ABS(top_height)>MAX_ABS_HEIGHT .OR. &
        bottom_virtual_temperature<MIN_VIRTUAL_TEMPERATURE .OR. &
        bottom_virtual_temperature>MAX_VIRTUAL_TEMPERATURE .OR. &
        top_virtual_temperature<MIN_VIRTUAL_TEMPERATURE .OR. &
        top_virtual_temperature>MAX_VIRTUAL_TEMPERATURE) RETURN

    log_pressure_ratio=LOG(bottom_pressure/top_pressure)
    IF (.NOT.ieee_is_finite(log_pressure_ratio) .OR. log_pressure_ratio<=0.0_real64) RETURN
    defect=GRAVITY*(top_height-bottom_height)-RD_AIR*0.5_real64* &
      (bottom_virtual_temperature+top_virtual_temperature)*log_pressure_ratio
    IF (.NOT.ieee_is_finite(defect)) THEN
      defect=ieee_value(0.0_real64,ieee_quiet_nan)
      RETURN
    END IF
    ok=.TRUE.
  END SUBROUTINE hydrostatic_height_defect

END MODULE qbal_surface_thermo
