PROGRAM test_state_atomic_refresh
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32,int64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value,ieee_quiet_nan
  USE cloud_bal_state
  IMPLICIT NONE

  INTEGER :: failures

  failures=0
  CALL test_usable_contract(failures)
  CALL test_late_failure_is_atomic(failures)
  CALL test_water_metadata_failure_is_atomic(failures)
  CALL test_water_value_failure_is_atomic(failures)
  IF (failures/=0) THEN
    PRINT *,'State atomic-refresh tests failed:',failures
    ERROR STOP 1
  END IF
  PRINT *,'State atomic-refresh tests passed'

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

  SUBROUTINE test_usable_contract(failures)
    INTEGER, INTENT(INOUT) :: failures
    INTEGER(int64), PARAMETER :: analysis_time=1788224400_int64

    CALL check(cell_is_usable(.TRUE.,0_int32,SOURCE_BACKGROUND_MODEL), &
      'the three-argument usable predicate must remain compatible',failures)
    CALL check(cell_is_usable(.TRUE.,0_int32,SOURCE_BACKGROUND_MODEL, &
      analysis_time,analysis_time), &
      'matching field and analysis times must be usable',failures)
    CALL check(.NOT.cell_is_usable(.TRUE.,0_int32,SOURCE_BACKGROUND_MODEL, &
      analysis_time+1_int64,analysis_time), &
      'a field-time mismatch must not be usable',failures)
    CALL check(.NOT.cell_is_usable(.TRUE.,0_int32,SOURCE_BACKGROUND_MODEL, &
      field_valid_time=analysis_time), &
      'an incomplete time contract must fail closed',failures)
    CALL check(.NOT.cell_is_usable(.TRUE.,QUALITY_TIME_MISMATCH, &
      SOURCE_BACKGROUND_MODEL,analysis_time,analysis_time), &
      'a cell-level time-mismatch flag must not be usable',failures)
    CALL check(.NOT.cell_is_usable(.TRUE.,0_int32,0_int32), &
      'valid data without provenance must not be usable',failures)
    CALL check(radar_echo_cell(20.0_real32,.TRUE.,0_int32,SOURCE_RADAR_DBZ), &
      'usable radar reflectivity must be classified as echo',failures)
    CALL check(radar_no_echo_cell(RADAR_NO_ECHO_DBZ,.FALSE.,0_int32, &
      SOURCE_RADAR_DBZ), &
      'observed no-echo must have one canonical representation',failures)
    CALL check(radar_missing_cell(0.0_real32,.FALSE.,QUALITY_RAW_MISSING,0_int32), &
      'missing radar must remain distinct from observed no-echo',failures)
    CALL check(.NOT.radar_echo_cell(101.0_real32,.TRUE.,0_int32,SOURCE_RADAR_DBZ), &
      'echo predicate must reject out-of-range reflectivity',failures)
    CALL check(.NOT.radar_missing_cell(1.0_real32,.FALSE.,QUALITY_RAW_MISSING,0_int32), &
      'missing-radar predicate must require the zero marker',failures)
  END SUBROUTINE test_usable_contract

  SUBROUTINE test_late_failure_is_atomic(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: state
    REAL(real64), ALLOCATABLE :: before(:,:,:)
    INTEGER :: status

    CALL make_refresh_state(state)
    before=state%grid%dry_air_mass_measure
    state%grid%pressure_mass_measure(2,2,2)= &
      ieee_value(0.0_real64,ieee_quiet_nan)
    CALL refresh_dry_air_mass_measure(state,status)
    CALL check(status==STATUS_FAILED, &
      'a nonfinite final mass candidate must fail',failures)
    CALL check(ALL(state%grid%dry_air_mass_measure==before), &
      'a late failure must not publish any earlier cell update',failures)
  END SUBROUTINE test_late_failure_is_atomic

  SUBROUTINE test_water_metadata_failure_is_atomic(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: state
    REAL(real64), ALLOCATABLE :: before(:,:,:)
    INTEGER :: status

    CALL make_refresh_state(state)
    before=state%grid%dry_air_mass_measure
    state%rain%valid_time=state%pressure%valid_time+1_int64
    CALL refresh_dry_air_mass_measure(state,status)
    CALL check(status==STATUS_FAILED, &
      'a stale water field must fail the refresh contract',failures)
    CALL check(ALL(state%grid%dry_air_mass_measure==before), &
      'a water metadata failure must leave the mass field unchanged',failures)
  END SUBROUTINE test_water_metadata_failure_is_atomic

  SUBROUTINE test_water_value_failure_is_atomic(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: state
    REAL(real64), ALLOCATABLE :: before(:,:,:)
    INTEGER :: status

    CALL make_refresh_state(state)
    before=state%grid%dry_air_mass_measure
    state%rain%value(2,2,2)=-0.001_real32
    state%rain%valid(2,2,2)=.TRUE.
    state%rain%quality(2,2,2)=0_int32
    state%rain%source(2,2,2)=SOURCE_BACKGROUND_MODEL
    CALL refresh_dry_air_mass_measure(state,status)
    CALL check(status==STATUS_FAILED, &
      'a negative water species must fail before aggregation',failures)
    CALL check(ALL(state%grid%dry_air_mass_measure==before), &
      'a water value failure must leave the mass field unchanged',failures)
  END SUBROUTINE test_water_value_failure_is_atomic

  SUBROUTINE make_refresh_state(state)
    TYPE(cloud_bal_state_type), INTENT(OUT) :: state
    INTEGER(int64), PARAMETER :: analysis_time=1788224400_int64
    INTEGER :: status

    CALL initialize_cloud_bal_state(state,2,2,2,analysis_time, &
      'atomic-refresh-test',status)
    IF (status/=STATUS_OK) ERROR STOP 'state initialization failed'
    state%grid%dx=1000.0_real64
    state%grid%dy=1000.0_real64
    state%grid%pressure_interface(:,:,1)=100000.0_real64
    state%grid%pressure_interface(:,:,2)=90000.0_real64
    state%grid%pressure_interface(:,:,3)=80000.0_real64
    state%grid%cell_dp=10000.0_real64
    state%grid%level_spacing_dp=10000.0_real64
    state%grid%pressure_mass_measure=1000.0_real64
    state%grid%dry_air_mass_measure=777.0_real64
    state%vapor%value=0.01_real32
    state%vapor%valid=.TRUE.
    state%vapor%quality=0_int32
    state%vapor%source=SOURCE_BACKGROUND_MODEL
  END SUBROUTINE make_refresh_state

END PROGRAM test_state_atomic_refresh
