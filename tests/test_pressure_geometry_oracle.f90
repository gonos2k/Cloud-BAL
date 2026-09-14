! Independent table oracle for pressure-diagnostic geometry, not native mass.
PROGRAM test_pressure_geometry_oracle
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32,int64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite,ieee_value,ieee_quiet_nan
  USE cloud_bal_state
  IMPLICIT NONE
  REAL(real32), PARAMETER :: ps(6)=[100000.,99000.,95500.,95000.,92500.,91000.]
  REAL(real64), PARAMETER :: dp(3,6)=RESHAPE([ &
    2500._real64,5000._real64,5000._real64, &
    0._real64,6500._real64,5000._real64, &
    0._real64,3000._real64,5000._real64, &
    0._real64,2500._real64,5000._real64, &
    0._real64,0._real64,5000._real64, &
    0._real64,0._real64,3500._real64],[3,6])
  REAL(real64), PARAMETER :: edges(4,6)=RESHAPE([ &
    100000._real64,97500._real64,92500._real64,87500._real64, &
    99000._real64,99000._real64,92500._real64,87500._real64, &
    95500._real64,95500._real64,92500._real64,87500._real64, &
    95000._real64,95000._real64,92500._real64,87500._real64, &
    92500._real64,92500._real64,92500._real64,87500._real64, &
    91000._real64,91000._real64,91000._real64,87500._real64],[4,6])
  ! Decimal references: 6000000*(PSFC-87500)/9.80665, computed outside the module.
  REAL(real64), PARAMETER :: column_mass(6)=[ &
    7647871597.3344618193_real64,7036041869.5477048737_real64, &
    4894637822.2940555643_real64,4588722958.4006770916_real64, &
    3059148638.9337847277_real64,2141404047.2536493094_real64]
  TYPE(cloud_bal_state_type) :: state,saved
  INTEGER :: status,reason,i,k

  CALL initialize_cloud_bal_state(state,6,1,3,1786885200_int64,'pressure-oracle',status)
  IF (status/=STATUS_OK) ERROR STOP 'initialize'
  state%grid%dx=2000._real64; state%grid%dy=3000._real64
  state%pressure%valid=.TRUE.; state%pressure%quality=0_int32
  state%pressure%source=SOURCE_BACKGROUND_MODEL
  state%pressure%value(:,:,1)=100000._real32
  state%pressure%value(:,:,2)=95000._real32
  state%pressure%value(:,:,3)=90000._real32
  CALL fill_field(state%temperature,280._real32,SOURCE_BACKGROUND_MODEL)
  CALL fill_field(state%vapor,0.01_real32,SOURCE_BACKGROUND_MODEL)
  CALL fill_field(state%u,5._real32,SOURCE_ANALYZED_WIND)
  CALL fill_field(state%v,-2._real32,SOURCE_ANALYZED_WIND)
  CALL fill_field(state%omega,0._real32,SOURCE_BACKGROUND_MODEL)
  state%surface_pressure%value(:,1)=ps
  state%surface_pressure%valid=.TRUE.; state%surface_pressure%quality=0_int32
  state%surface_pressure%source=SOURCE_BACKGROUND_MODEL
  CALL fill_surface_field(state%surface_temperature,290._real32)
  ! OM is deliberately unavailable: it must not determine pressure geometry.
  state%omega%valid=.FALSE.
  CALL configure_pressure_geometry(state,status)
  IF (status/=STATUS_OK) ERROR STOP 'configure table'
  DO i=1,6
    DO k=1,4
      CALL close(state%grid%pressure_interface(i,1,k),edges(k,i),1.e-8_real64,'interface')
    END DO
    DO k=1,3
      CALL close(state%grid%cell_dp(i,1,k),dp(k,i),1.e-8_real64,'cell dp')
      IF (state%above_ground(i,1,k) .NEQV. (dp(k,i)>0._real64)) ERROR STOP 'domain'
      CALL close(state%grid%pressure_mass_measure(i,1,k), &
        column_mass(i)*dp(k,i)/SUM(dp(:,i)),1.e-6_real64,'cell pressure mass')
    END DO
    DO k=1,2
      CALL close(state%grid%level_spacing_dp(i,1,k),5000._real64,1.e-8_real64,'spacing')
    END DO
    CALL close(SUM(state%grid%pressure_mass_measure(i,1,:)), &
      column_mass(i),1.e-6_real64,'column pressure mass')
  END DO
  IF (ANY(state%grid%dry_air_mass_measure/=0._real64)) ERROR STOP 'premature dry mass'
  state%omega%valid=.TRUE.
  CALL refresh_dry_air_mass_measure(state,status)
  IF (status/=STATUS_OK) ERROR STOP 'refresh dry mass'
  IF (.NOT.pressure_geometry_is_valid(state)) ERROR STOP 'valid geometry rejected'
  CALL validate_canonical_state(state,.FALSE.,.FALSE.,status,reason)
  IF (status/=STATUS_OK) ERROR STOP 'valid canonical geometry rejected'
  saved=state
  state%surface_pressure%unit='hPa'
  CALL rejected_without_geometry_change()
  state=saved
  state%surface_pressure%value(6,1)=ieee_value(0._real32,ieee_quiet_nan)
  CALL rejected_without_geometry_change()
  state=saved
  state%pressure%value(6,1,2)=100001._real32
  CALL rejected_without_geometry_change()
  state=saved
  state%pressure%value(6,1,2)=ieee_value(0._real32,ieee_quiet_nan)
  CALL rejected_without_geometry_change()
  state=saved
  state%grid%dx(6,1)=ieee_value(0._real64,ieee_quiet_nan)
  CALL rejected_without_geometry_change()
  state=saved
  state%grid%dx(6,1)=ieee_value(0._real64,ieee_quiet_nan)
  CALL rejected_geometry_validator('dx')
  state=saved
  state%grid%dy(6,1)=ieee_value(0._real64,ieee_quiet_nan)
  CALL rejected_geometry_validator('dy')
  state=saved
  state%grid%pressure_interface(6,1,2)=ieee_value(0._real64,ieee_quiet_nan)
  CALL rejected_geometry_validator('pressure interface')
  state=saved
  state%grid%cell_dp(6,1,2)=ieee_value(0._real64,ieee_quiet_nan)
  CALL rejected_geometry_validator('cell dp')
  state=saved
  state%grid%level_spacing_dp(6,1,2)=ieee_value(0._real64,ieee_quiet_nan)
  CALL rejected_geometry_validator('level spacing')
  state=saved
  state%grid%pressure_mass_measure(6,1,2)=ieee_value(0._real64,ieee_quiet_nan)
  CALL rejected_geometry_validator('pressure mass')
  state=saved
  state%grid%dry_air_mass_measure(6,1,2)=ieee_value(0._real64,ieee_quiet_nan)
  CALL rejected_geometry_validator('dry-air mass')
  state=saved
  state%pressure%value(6,1,2)=ieee_value(0._real32,ieee_quiet_nan)
  CALL rejected_geometry_validator('pressure center')
  state=saved
  state%surface_pressure%value(6,1)=ieee_value(0._real32,ieee_quiet_nan)
  CALL rejected_geometry_validator('surface pressure')
  PRINT *,'Pressure geometry oracle passed: 6 columns, 5 atomic rejection cases'
  PRINT *,'Direct validators rejected 9 NaN geometry mutations without trapping'
  PRINT *,'Scope: pressure diagnostic only; native partial-face and dry mass NOT assessed'
CONTAINS
  SUBROUTINE fill_field(field,value,source)
    TYPE(field3d), INTENT(INOUT) :: field
    REAL(real32), INTENT(IN) :: value
    INTEGER(int32), INTENT(IN) :: source
    field%value=value
    field%valid=.TRUE.
    field%quality=0_int32
    field%source=source
  END SUBROUTINE fill_field

  SUBROUTINE fill_surface_field(field,value)
    TYPE(field2d), INTENT(INOUT) :: field
    REAL(real32), INTENT(IN) :: value
    field%value=value
    field%valid=.TRUE.
    field%quality=0_int32
    field%source=SOURCE_BACKGROUND_MODEL
  END SUBROUTINE fill_surface_field

  SUBROUTINE close(value,reference,abs_tol,label)
    REAL(real64), INTENT(IN) :: value,reference,abs_tol
    CHARACTER(*), INTENT(IN) :: label
    IF (.NOT.ieee_is_finite(value) .OR. &
        ABS(value-reference)>abs_tol+64._real64*EPSILON(1._real64)*ABS(reference)) THEN
      PRINT *,'FAIL ',label,value,reference
      ERROR STOP 1
    END IF
  END SUBROUTINE close

  SUBROUTINE rejected_without_geometry_change()
    CALL configure_pressure_geometry(state,status)
    IF (status/=STATUS_FAILED) ERROR STOP 'invalid input accepted'
    IF (ANY(state%grid%pressure_interface/=saved%grid%pressure_interface) .OR. &
        ANY(state%grid%cell_dp/=saved%grid%cell_dp) .OR. &
        ANY(state%grid%level_spacing_dp/=saved%grid%level_spacing_dp) .OR. &
        ANY(state%grid%pressure_mass_measure/=saved%grid%pressure_mass_measure) .OR. &
        ANY(state%grid%dry_air_mass_measure/=saved%grid%dry_air_mass_measure) .OR. &
        ANY(state%above_ground .NEQV. saved%above_ground)) ERROR STOP 'non-atomic geometry'
  END SUBROUTINE rejected_without_geometry_change

  SUBROUTINE rejected_geometry_validator(label)
    CHARACTER(*), INTENT(IN) :: label
    INTEGER :: validator_status,validator_reason
    IF (pressure_geometry_is_valid(state)) ERROR STOP 'NaN geometry accepted'
    CALL validate_canonical_state(state,.FALSE.,.FALSE.,validator_status,validator_reason)
    IF (validator_status==STATUS_OK) THEN
      PRINT *,'FAIL accepted NaN geometry ',TRIM(label)
      ERROR STOP 1
    END IF
  END SUBROUTINE rejected_geometry_validator
END PROGRAM test_pressure_geometry_oracle
