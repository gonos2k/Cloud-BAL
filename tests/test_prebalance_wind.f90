PROGRAM test_prebalance_wind
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32,int64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value,ieee_quiet_nan
  USE cloud_bal_state, ONLY: cloud_bal_state_type,field3d,field2d, &
    initialize_cloud_bal_state,initialize_field,configure_pressure_geometry, &
    refresh_dry_air_mass_measure,canonical_states_equal,STATUS_OK,STATUS_FAILED, &
    SOURCE_BACKGROUND_MODEL,SOURCE_COLUMN_PHYSICS,SOURCE_ANALYZED_WIND, &
    QUALITY_RAW_MISSING
  USE cloud_bal_pipeline, ONLY: restore_pre_balance_winds
  IMPLICIT NONE

  INTEGER, PARAMETER :: NX=1,NY=1,NZ=3
  INTEGER(int64), PARAMETER :: VALID_TIME=1788224400_int64
  REAL(real32), PARAMETER :: PRESSURE(NZ)=[100000.0_real32,95000.0_real32,90000.0_real32]
  CHARACTER(LEN=*), PARAMETER :: GRID_ID='prebalance-wind-test'
  INTEGER :: failures

  failures=0
  CALL test_no_change_domain
  CALL test_one_added_cell
  CALL test_missing_seed
  CALL test_malformed_seed
  CALL test_old_cell_removal

  IF (failures/=0) THEN
    PRINT '(A,I0)','Pre-balance wind tests failed: ',failures
    ERROR STOP 1
  END IF
  PRINT '(A)','Pre-balance wind tests passed'

CONTAINS

  SUBROUTINE check(ok,message)
    LOGICAL, INTENT(IN) :: ok
    CHARACTER(LEN=*), INTENT(IN) :: message
    IF (.NOT.ok) THEN
      failures=failures+1
      PRINT '(A)','FAIL: '//TRIM(message)
    END IF
  END SUBROUTINE check

  SUBROUTINE test_no_change_domain
    TYPE(cloud_bal_state_type) :: original,candidate,restored,expected
    TYPE(cloud_bal_state_type) :: original_before,candidate_before
    LOGICAL :: domain(NX,NY,NZ)
    INTEGER :: status

    domain=.TRUE.
    CALL make_state(original,domain,100010.0_real32,SOURCE_BACKGROUND_MODEL,status)
    CALL check(status==STATUS_OK,'no-change original fixture')
    IF (status/=STATUS_OK) RETURN
    candidate=original
    candidate%u%value=101.0_real32
    candidate%v%value=-102.0_real32
    candidate%omega%value=103.0_real32
    candidate%u%source=SOURCE_COLUMN_PHYSICS
    candidate%v%source=SOURCE_COLUMN_PHYSICS
    candidate%omega%source=SOURCE_COLUMN_PHYSICS
    original_before=original
    candidate_before=candidate

    CALL restore_pre_balance_winds(candidate,original,restored,status)
    expected=candidate
    expected%u%value=original%u%value
    expected%v%value=original%v%value
    expected%omega%value=original%omega%value
    CALL check(status==STATUS_OK,'no-change domain restores original winds')
    CALL check(canonical_states_equal(restored,expected), &
      'no-change domain preserves candidate state except wind values')
    CALL check(canonical_states_equal(original,original_before) .AND. &
      canonical_states_equal(candidate,candidate_before), &
      'no-change domain preserves both inputs')
  END SUBROUTINE test_no_change_domain

  SUBROUTINE test_one_added_cell
    TYPE(cloud_bal_state_type) :: original,candidate,seed,restored,expected
    TYPE(cloud_bal_state_type) :: original_before,candidate_before,seed_before
    LOGICAL :: original_domain(NX,NY,NZ),candidate_domain(NX,NY,NZ)
    INTEGER :: status

    original_domain=.FALSE.; original_domain(:,:,2:)=.TRUE.
    candidate_domain=.TRUE.
    CALL make_state(original,original_domain,99990.0_real32,SOURCE_BACKGROUND_MODEL,status)
    CALL check(status==STATUS_OK,'transition original fixture')
    IF (status/=STATUS_OK) RETURN
    CALL make_state(candidate,candidate_domain,100010.0_real32,SOURCE_COLUMN_PHYSICS,status)
    CALL check(status==STATUS_OK,'transition candidate fixture')
    IF (status/=STATUS_OK) RETURN
    CALL make_state(seed,candidate_domain,100010.0_real32,SOURCE_ANALYZED_WIND,status)
    CALL check(status==STATUS_OK,'transition seed fixture')
    IF (status/=STATUS_OK) RETURN

    candidate%u%value=101.0_real32
    candidate%v%value=-102.0_real32
    candidate%omega%value=103.0_real32
    seed%u%value=201.0_real32
    seed%v%value=-202.0_real32
    seed%omega%value=203.0_real32
    seed%u%source=SOURCE_ANALYZED_WIND
    seed%v%source=SOURCE_ANALYZED_WIND
    seed%omega%source=SOURCE_ANALYZED_WIND
    CALL check(candidate%u%value(1,1,1)/=seed%u%value(1,1,1), &
      'transition candidate new-cell wind is deliberately different')

    original_before=original
    candidate_before=candidate
    seed_before=seed
    CALL restore_pre_balance_winds(candidate,original,restored,status,seed)
    expected=candidate
    expected%u%value(1,1,2:)=original%u%value(1,1,2:)
    expected%v%value(1,1,2:)=original%v%value(1,1,2:)
    expected%omega%value(1,1,2:)=original%omega%value(1,1,2:)
    expected%u%value(1,1,1)=seed%u%value(1,1,1)
    expected%v%value(1,1,1)=seed%v%value(1,1,1)
    expected%omega%value(1,1,1)=seed%omega%value(1,1,1)
    CALL check(status==STATUS_OK,'one-cell transition restores pre-balance winds')
    CALL check(canonical_states_equal(restored,expected), &
      'transition preserves geometry support metadata and other fields')
    CALL check(ALL(restored%u%source==candidate%u%source) .AND. &
      ALL(restored%v%source==candidate%v%source) .AND. &
      ALL(restored%omega%source==candidate%omega%source), &
      'transition does not copy seed wind metadata or grant authority')
    CALL check(canonical_states_equal(original,original_before) .AND. &
      canonical_states_equal(candidate,candidate_before) .AND. &
      canonical_states_equal(seed,seed_before), &
      'transition preserves all input states')
  END SUBROUTINE test_one_added_cell

  SUBROUTINE test_missing_seed
    TYPE(cloud_bal_state_type) :: original,candidate,restored,before,original_before
    LOGICAL :: original_domain(NX,NY,NZ),candidate_domain(NX,NY,NZ)
    INTEGER :: status

    original_domain=.FALSE.; original_domain(:,:,2:)=.TRUE.
    candidate_domain=.TRUE.
    CALL make_state(original,original_domain,99990.0_real32,SOURCE_BACKGROUND_MODEL,status)
    CALL make_state(candidate,candidate_domain,100010.0_real32,SOURCE_COLUMN_PHYSICS,status)
    original_before=original
    before=candidate
    CALL restore_pre_balance_winds(candidate,original,restored,status)
    CALL check(status==STATUS_FAILED,'missing transition seed rejects')
    CALL check(canonical_states_equal(restored,before), &
      'missing transition seed is atomic')
    CALL check(canonical_states_equal(candidate,before) .AND. &
      canonical_states_equal(original,original_before), &
      'missing transition seed preserves inputs')
  END SUBROUTINE test_missing_seed

  SUBROUTINE test_malformed_seed
    TYPE(cloud_bal_state_type) :: original,candidate,seed,restored,before
    TYPE(cloud_bal_state_type) :: bad_shape
    LOGICAL :: original_domain(NX,NY,NZ),candidate_domain(NX,NY,NZ)
    INTEGER :: status

    original_domain=.FALSE.; original_domain(:,:,2:)=.TRUE.
    candidate_domain=.TRUE.
    CALL make_state(original,original_domain,99990.0_real32,SOURCE_BACKGROUND_MODEL,status)
    CALL make_state(candidate,candidate_domain,100010.0_real32,SOURCE_COLUMN_PHYSICS,status)
    CALL make_state(seed,candidate_domain,100010.0_real32,SOURCE_ANALYZED_WIND,status)
    seed%u%value(1,1,1)=ieee_value(0.0_real32,ieee_quiet_nan)
    before=candidate
    CALL restore_pre_balance_winds(candidate,original,restored,status,seed)
    CALL check(status==STATUS_FAILED,'nonfinite used seed wind rejects')
    CALL check(canonical_states_equal(restored,before), &
      'nonfinite used seed wind is atomic')

    CALL initialize_cloud_bal_state(bad_shape,NX,NY,2,VALID_TIME,GRID_ID,status)
    CALL check(status==STATUS_OK,'malformed seed shape fixture')
    IF (status/=STATUS_OK) RETURN
    before=candidate
    CALL restore_pre_balance_winds(candidate,original,restored,status,bad_shape)
    CALL check(status==STATUS_FAILED,'malformed seed shape rejects')
    CALL check(canonical_states_equal(restored,before), &
      'malformed seed shape is atomic')
  END SUBROUTINE test_malformed_seed

  SUBROUTINE test_old_cell_removal
    TYPE(cloud_bal_state_type) :: original,candidate,restored,before,original_before
    LOGICAL :: original_domain(NX,NY,NZ),removed_domain(NX,NY,NZ)
    INTEGER :: status

    original_domain=.FALSE.; original_domain(:,:,2:)=.TRUE.
    removed_domain=.FALSE.; removed_domain(:,:,3)=.TRUE.
    CALL make_state(original,original_domain,99990.0_real32,SOURCE_BACKGROUND_MODEL,status)
    CALL make_state(candidate,removed_domain,94000.0_real32,SOURCE_COLUMN_PHYSICS,status)
    original_before=original
    before=candidate
    CALL restore_pre_balance_winds(candidate,original,restored,status)
    CALL check(status==STATUS_FAILED,'old active-cell removal rejects')
    CALL check(canonical_states_equal(restored,before), &
      'old active-cell removal is atomic')
    CALL check(canonical_states_equal(candidate,before) .AND. &
      canonical_states_equal(original,original_before), &
      'old active-cell removal preserves inputs')
  END SUBROUTINE test_old_cell_removal

  SUBROUTINE make_state(state,domain,surface_pressure,wind_source,status)
    TYPE(cloud_bal_state_type), INTENT(OUT) :: state
    LOGICAL, INTENT(IN) :: domain(NX,NY,NZ)
    REAL(real32), INTENT(IN) :: surface_pressure
    INTEGER(int32), INTENT(IN) :: wind_source
    INTEGER, INTENT(OUT) :: status
    INTEGER :: k

    CALL initialize_cloud_bal_state(state,NX,NY,NZ,VALID_TIME,GRID_ID,status)
    IF (status/=STATUS_OK) RETURN
    state%grid%dx=2000.0_real64
    state%grid%dy=2200.0_real64
    DO k=1,NZ
      state%pressure%value(:,:,k)=PRESSURE(k)
      state%temperature%value(:,:,k)=280.0_real32+REAL(k,real32)
      state%geopotential%value(:,:,k)=1000.0_real32+REAL(k,real32)
      state%vapor%value(:,:,k)=0.008_real32
      state%cloud_water%value(:,:,k)=0.001_real32
      state%cloud_ice%value(:,:,k)=0.0005_real32
      state%rain%value(:,:,k)=0.0002_real32
      state%snow%value(:,:,k)=0.0001_real32
      state%graupel%value(:,:,k)=0.00005_real32
      state%u%value(:,:,k)=10.0_real32+REAL(k,real32)
      state%v%value(:,:,k)=-20.0_real32-REAL(k,real32)
      state%omega%value(:,:,k)=30.0_real32+REAL(k,real32)
    END DO
    CALL mark3(state%pressure,SOURCE_BACKGROUND_MODEL)
    CALL mark3(state%temperature,SOURCE_BACKGROUND_MODEL)
    CALL mark3(state%geopotential,SOURCE_BACKGROUND_MODEL)
    CALL mark3(state%vapor,SOURCE_BACKGROUND_MODEL)
    CALL mark3(state%cloud_water,SOURCE_BACKGROUND_MODEL)
    CALL mark3(state%cloud_ice,SOURCE_BACKGROUND_MODEL)
    CALL mark3(state%rain,SOURCE_BACKGROUND_MODEL)
    CALL mark3(state%snow,SOURCE_BACKGROUND_MODEL)
    CALL mark3(state%graupel,SOURCE_BACKGROUND_MODEL)
    CALL mark3(state%u,wind_source)
    CALL mark3(state%v,wind_source)
    CALL mark3(state%omega,wind_source)
    state%surface_pressure%value=surface_pressure
    state%surface_temperature%value=290.0_real32
    state%surface_vapor%value=0.006_real32
    state%surface_height%value=100.0_real32
    CALL mark2(state%surface_pressure,SOURCE_BACKGROUND_MODEL)
    CALL mark2(state%surface_temperature,SOURCE_BACKGROUND_MODEL)
    CALL mark2(state%surface_vapor,SOURCE_BACKGROUND_MODEL)
    CALL mark2(state%surface_height,SOURCE_BACKGROUND_MODEL)
    CALL configure_pressure_geometry(state,status,domain)
    IF (status/=STATUS_OK) RETURN
    CALL mask_to_domain(state)
    state%obs_support=0_int32
    state%hydro_support=0_int32
    state%balance_beta=0.0_real32
    WHERE(state%above_ground)
      state%obs_support=1_int32
      state%hydro_support=1_int32
      state%balance_beta=0.25_real32
    END WHERE
    CALL refresh_dry_air_mass_measure(state,status)
  END SUBROUTINE make_state

  SUBROUTINE mark3(field,source)
    TYPE(field3d), INTENT(INOUT) :: field
    INTEGER(int32), INTENT(IN) :: source
    field%valid=.TRUE.
    field%quality=0_int32
    field%source=source
  END SUBROUTINE mark3

  SUBROUTINE mark2(field,source)
    TYPE(field2d), INTENT(INOUT) :: field
    INTEGER(int32), INTENT(IN) :: source
    field%valid=.TRUE.
    field%quality=0_int32
    field%source=source
  END SUBROUTINE mark2

  SUBROUTINE mask_to_domain(state)
    TYPE(cloud_bal_state_type), INTENT(INOUT) :: state
    state%temperature%valid=state%above_ground
    state%geopotential%valid=state%above_ground
    state%vapor%valid=state%above_ground
    state%cloud_water%valid=state%above_ground
    state%cloud_ice%valid=state%above_ground
    state%rain%valid=state%above_ground
    state%snow%valid=state%above_ground
    state%graupel%valid=state%above_ground
    state%u%valid=state%above_ground
    state%v%valid=state%above_ground
    state%omega%valid=state%above_ground
    WHERE(.NOT.state%above_ground)
      state%temperature%quality=QUALITY_RAW_MISSING
      state%temperature%source=0_int32
      state%geopotential%quality=QUALITY_RAW_MISSING
      state%geopotential%source=0_int32
      state%vapor%quality=QUALITY_RAW_MISSING
      state%vapor%source=0_int32
      state%cloud_water%quality=QUALITY_RAW_MISSING
      state%cloud_water%source=0_int32
      state%cloud_ice%quality=QUALITY_RAW_MISSING
      state%cloud_ice%source=0_int32
      state%rain%quality=QUALITY_RAW_MISSING
      state%rain%source=0_int32
      state%snow%quality=QUALITY_RAW_MISSING
      state%snow%source=0_int32
      state%graupel%quality=QUALITY_RAW_MISSING
      state%graupel%source=0_int32
      state%u%quality=QUALITY_RAW_MISSING
      state%u%source=0_int32
      state%v%quality=QUALITY_RAW_MISSING
      state%v%source=0_int32
      state%omega%quality=QUALITY_RAW_MISSING
      state%omega%source=0_int32
      state%pressure%valid=.FALSE.
      state%pressure%quality=QUALITY_RAW_MISSING
      state%pressure%source=0_int32
    END WHERE
  END SUBROUTINE mask_to_domain

END PROGRAM test_prebalance_wind
