PROGRAM test_real_shadow_io_contract
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32,int64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value,ieee_quiet_nan
  USE cloud_bal_state
  USE cloud_bal_pipeline
  USE cloud_bal_balance_operator, ONLY: TARGET_AUTHORITY_OBSERVATIONAL, &
                                        TARGET_AUTHORITY_MANUFACTURED_TEST
  USE cloud_bal_real_netcdf, ONLY: validate_shadow_write_contract, &
                                   write_shadow_diagnostics
  IMPLICIT NONE

  TYPE(cloud_bal_state_type) :: input,candidate,operational
  TYPE(cloud_bal_pipeline_config) :: config
  TYPE(cloud_bal_pipeline_result) :: result
  REAL(real32) :: longitude(2,2)
  REAL(real64) :: residual(2,2,2)
  INTEGER :: failures,status,reason

  failures=0
  CALL make_state(input)
  candidate=input
  operational=input
  CALL make_result(result,input%grid%nx,input%grid%ny,input%grid%nz)
  config%requested_mode=MODE_SHADOW

  longitude=0.0_real32; residual=0.0_real64
  CALL validate_shadow_write_contract(input,candidate,operational,result,config, &
                                      status,reason)
  CALL check(status==STATUS_OK .AND. reason==REASON_NONE, &
             'verified SHADOW state must pass',failures)

  result%column%numerical%flux_deposited=-1.0_real64
  CALL validate_shadow_write_contract(input,candidate,operational,result,config, &
                                      status,reason)
  CALL check(status==STATUS_FAILED .AND. reason==REASON_GATE, &
             'negative flux ledger terms must fail before publication',failures)
  CALL make_result(result,input%grid%nx,input%grid%ny,input%grid%nz)
  CALL write_shadow_diagnostics('verified-shadow.nc',input,candidate,longitude, &
    result,config,residual,residual,status,operational)
  CALL check(status==STATUS_OK,'verified dynamic-size state must be writable',failures)

  result%reason_code=REASON_GATE
  CALL validate_shadow_write_contract(input,candidate,operational,result,config, &
                                      status,reason)
  CALL check(status==STATUS_FAILED .AND. reason==REASON_AUTHORITY, &
             'OK result with nonzero reason must be rejected',failures)
  CALL make_result(result,input%grid%nx,input%grid%ny,input%grid%nz)

  config%column%ledger_relative_tolerance= &
    ieee_value(0.0_real64,ieee_quiet_nan)
  CALL validate_shadow_write_contract(input,candidate,operational,result,config, &
                                      status,reason)
  CALL check(status==STATUS_FAILED .AND. reason==REASON_RANGE, &
             'invalid column configuration must fail before publication',failures)
  config%column%ledger_relative_tolerance=1.0e-11_real64

  result%status=STATUS_DEGRADED
  result%reason_code=REASON_GATE
  result%balance%status=STATUS_DEGRADED
  result%balance%reason_code=REASON_GATE
  result%overall%status=STATUS_DEGRADED
  result%overall%reason_code=REASON_GATE
  CALL validate_shadow_write_contract(input,candidate,operational,result,config, &
                                      status,reason)
  CALL check(status==STATUS_OK .AND. reason==REASON_NONE, &
             'verified rejected proposal may remain diagnostic evidence',failures)
  result%overall%reason_code=REASON_NONE
  CALL validate_shadow_write_contract(input,candidate,operational,result,config, &
                                      status,reason)
  CALL check(status==STATUS_FAILED .AND. reason==REASON_AUTHORITY, &
             'degraded stage reasons must agree',failures)
  CALL make_result(result,input%grid%nx,input%grid%ny,input%grid%nz)

  config%requested_mode=MODE_OFF
  CALL validate_shadow_write_contract(input,candidate,operational,result,config, &
                                      status,reason)
  CALL check(status==STATUS_FAILED .AND. reason==REASON_AUTHORITY, &
             'OFF result cannot claim SHADOW authority',failures)
  config%requested_mode=MODE_SHADOW

  result%requested_mode=MODE_OFF
  CALL validate_shadow_write_contract(input,candidate,operational,result,config, &
                                      status,reason)
  CALL check(status==STATUS_FAILED .AND. reason==REASON_AUTHORITY, &
             'result mode must agree with requested SHADOW mode',failures)
  result%requested_mode=MODE_SHADOW

  operational=input
  operational%u%value(1,1,1)=operational%u%value(1,1,1)+1.0_real32
  CALL validate_shadow_write_contract(input,candidate,operational,result,config, &
                                      status,reason)
  CALL check(status==STATUS_FAILED .AND. reason==REASON_AUTHORITY, &
             'operational value mutation must be rejected',failures)
  CALL write_shadow_diagnostics('unverified-shadow.nc',input,candidate,longitude, &
    result,config,residual,residual,status,operational)
  CALL check(status==STATUS_FAILED, &
             'writer must not publish an unverified SHADOW claim',failures)

  operational=input
  operational%cloud_fraction%valid_time=operational%cloud_fraction%valid_time+1_int64
  CALL validate_shadow_write_contract(input,candidate,operational,result,config, &
                                      status,reason)
  CALL check(status==STATUS_FAILED .AND. reason==REASON_AUTHORITY, &
             'optional-field metadata mutation must be rejected',failures)

  operational=input
  operational%radar_los%vrad%unit='changed'
  CALL validate_shadow_write_contract(input,candidate,operational,result,config, &
                                      status,reason)
  CALL check(status==STATUS_FAILED .AND. reason==REASON_RADAR_CONTRACT, &
             'absent LOS metadata mutation must be rejected',failures)

  operational=input
  ALLOCATE(operational%radar_los%vrad%valid(1,1,1,1))
  operational%radar_los%vrad%valid=.FALSE.
  CALL validate_shadow_write_contract(input,candidate,operational,result,config, &
                                      status,reason)
  CALL check(status==STATUS_FAILED .AND. reason==REASON_RADAR_CONTRACT, &
             'partially allocated absent LOS must be rejected',failures)

  operational=input
  input%cloud_fraction%valid(1,1,1)=.TRUE.
  input%cloud_fraction%quality(1,1,1)=0_int32
  input%cloud_fraction%source(1,1,1)=SOURCE_CLOUD_ANALYSIS
  input%cloud_fraction%value(1,1,1)=0.5_real32
  CALL validate_shadow_write_contract(input,candidate,operational,result,config, &
                                      status,reason)
  CALL check(status==STATUS_FAILED .AND. reason==REASON_AUTHORITY, &
             'radar-only writer must reject cloud-analysis authority',failures)

  input=operational; candidate=input
  candidate%cloud_fraction%valid(1,1,1)=.TRUE.
  candidate%cloud_fraction%quality(1,1,1)=0_int32
  candidate%cloud_fraction%source(1,1,1)=SOURCE_CLOUD_ANALYSIS
  candidate%cloud_fraction%value(1,1,1)=0.5_real32
  CALL validate_shadow_write_contract(input,candidate,operational,result,config, &
                                      status,reason)
  CALL check(status==STATUS_FAILED .AND. reason==REASON_AUTHORITY, &
             'candidate cloud authority must be rejected',failures)

  candidate=input
  candidate%pressure%value(1,1,1)=candidate%pressure%value(1,1,1)-1.0_real32
  CALL validate_shadow_write_contract(input,candidate,operational,result,config, &
                                      status,reason)
  CALL check(status==STATUS_FAILED .AND. reason==REASON_AUTHORITY, &
             'candidate coordinate mutation must be rejected',failures)

  candidate=input
  candidate%u%value(1,1,1)=candidate%u%value(1,1,1)+1.0_real32
  CALL validate_shadow_write_contract(input,candidate,operational,result,config, &
                                      status,reason)
  CALL check(status==STATUS_FAILED .AND. reason==REASON_AUTHORITY, &
             'candidate delta must agree with result masks',failures)

  candidate=input
  candidate%u%source(1,1,1)=IOR(candidate%u%source(1,1,1), &
                                SOURCE_BALANCE_OPERATOR)
  CALL validate_shadow_write_contract(input,candidate,operational,result,config, &
                                      status,reason)
  CALL check(status==STATUS_FAILED .AND. reason==REASON_AUTHORITY, &
             'wind provenance cannot change without a value change',failures)

  candidate=input
  result%column%changed(1,1,1)=.TRUE.
  result%overall%changed(1,1,1)=.TRUE.
  CALL validate_shadow_write_contract(input,candidate,operational,result,config, &
                                      status,reason)
  CALL check(status==STATUS_FAILED .AND. reason==REASON_AUTHORITY, &
             'result masks must describe candidate deltas',failures)
  CALL make_result(result,input%grid%nx,input%grid%ny,input%grid%nz)

  input%omega_target%value(1,1,1)=input%omega%value(1,1,1)
  input%omega_target%valid(1,1,1)=.TRUE.
  input%omega_target%quality(1,1,1)=0_int32
  input%omega_target%source(1,1,1)=IOR(SOURCE_ANALYZED_WIND, &
                                          SOURCE_DYNAMIC_TARGET)
  candidate=input; operational=input
  CALL validate_shadow_write_contract(input,candidate,operational,result,config, &
                                      status,reason)
  CALL check(status==STATUS_OK .AND. reason==REASON_NONE, &
             'unchanged pre-existing target is not a new column change',failures)

  input%radar_reflectivity%value(1,1,1)=-10.0_real32
  input%radar_reflectivity%valid(1,1,1)=.FALSE.
  input%radar_reflectivity%quality(1,1,1)=0_int32
  input%radar_reflectivity%source(1,1,1)=SOURCE_RADAR_DBZ
  candidate=input; operational=input
  CALL validate_shadow_write_contract(input,candidate,operational,result,config, &
                                      status,reason)
  CALL check(status==STATUS_OK .AND. reason==REASON_NONE, &
             'observed no-echo must remain distinct from missing radar',failures)

  candidate=input
  candidate%rain%value(1,1,1)=1.0e-4_real32
  candidate%rain%source(1,1,1)=IOR(candidate%rain%source(1,1,1), &
                                   SOURCE_COLUMN_PHYSICS)
  candidate%hydro_support(1,1,1)=1_int32
  CALL refresh_dry_air_mass_measure(candidate,status)
  result%column%changed(1,1,1)=.TRUE.
  result%overall%changed(1,1,1)=.TRUE.
  CALL validate_shadow_write_contract(input,candidate,operational,result,config, &
                                      status,reason)
  CALL check(status==STATUS_FAILED .AND. reason==REASON_AUTHORITY, &
             'no-echo cells must reject hydrometeor candidate changes',failures)
  CALL make_result(result,input%grid%nx,input%grid%ny,input%grid%nz)

  CALL make_state(input)
  input%radar_reflectivity%value(1,1,1)=1.0_real32
  candidate=input; operational=input
  CALL validate_shadow_write_contract(input,candidate,operational,result,config, &
                                      status,reason)
  CALL check(status==STATUS_FAILED .AND. reason==REASON_RADAR_CONTRACT, &
             'missing radar must retain its canonical zero marker',failures)

  CALL make_state(input)
  input%omega_top_boundary%valid(1,1)=.FALSE.
  candidate=input; operational=input
  CALL validate_shadow_write_contract(input,candidate,operational,result,config, &
                                      status,reason)
  CALL check(status==STATUS_FAILED .AND. reason==REASON_METADATA, &
             'invalid diagnostic boundary mask must fail closed',failures)

  CALL make_state(input)
  input%omega_top_boundary%source=SOURCE_BOUNDARY_CONDITION
  input%omega_bottom_boundary%source=SOURCE_BOUNDARY_CONDITION
  candidate=input; operational=input
  CALL validate_shadow_write_contract(input,candidate,operational,result,config, &
                                      status,reason)
  CALL check(status==STATUS_FAILED .AND. reason==REASON_METADATA, &
             'real SHADOW writer must reject physical-boundary provenance',failures)

  CALL make_state(input)
  candidate=input; operational=input
  config%balance%target_authority=TARGET_AUTHORITY_MANUFACTURED_TEST
  CALL validate_shadow_write_contract(input,candidate,operational,result,config, &
                                      status,reason)
  CALL check(status==STATUS_FAILED .AND. reason==REASON_AUTHORITY, &
             'real SHADOW writer must reject manufactured test mode',failures)
  config%balance%target_authority=TARGET_AUTHORITY_OBSERVATIONAL

  input%omega_target%source(1,1,1)=SOURCE_MANUFACTURED_TEST
  candidate=input; operational=input
  CALL validate_shadow_write_contract(input,candidate,operational,result,config, &
                                      status,reason)
  CALL check(status==STATUS_FAILED .AND. reason==REASON_AUTHORITY, &
             'invalid targets cannot carry manufactured provenance',failures)

  CALL make_state(input)
  input%temperature%source(1,1,1)=IOR(input%temperature%source(1,1,1), &
                                     SOURCE_MANUFACTURED_TEST)
  candidate=input; operational=input
  CALL validate_shadow_write_contract(input,candidate,operational,result,config, &
                                      status,reason)
  CALL check(status==STATUS_FAILED .AND. reason==REASON_AUTHORITY, &
             'real SHADOW fields cannot carry manufactured provenance',failures)

  CALL make_state(input)
  input%omega_top_boundary%source=IOR(SOURCE_ANALYZED_WIND,SOURCE_MANUFACTURED_TEST)
  input%omega_bottom_boundary%source= &
    IOR(SOURCE_ANALYZED_WIND,SOURCE_MANUFACTURED_TEST)
  candidate=input; operational=input
  CALL validate_shadow_write_contract(input,candidate,operational,result,config, &
                                      status,reason)
  CALL check(status==STATUS_FAILED .AND. reason==REASON_AUTHORITY, &
             'copied boundaries cannot carry manufactured provenance',failures)

  CALL make_state(input)
  input%omega_top_boundary%value(1,1)= &
    ieee_value(0.0_real32,ieee_quiet_nan)
  candidate=input; operational=input
  CALL validate_shadow_write_contract(input,candidate,operational,result,config, &
                                      status,reason)
  CALL check(status==STATUS_FAILED .AND. reason==REASON_METADATA, &
             'nonfinite diagnostic boundary must fail closed',failures)

  CALL make_state(input)
  candidate=input; operational=input

  residual=ieee_value(0.0_real64,ieee_quiet_nan)
  CALL write_shadow_diagnostics('nonfinite-residual.nc',input,candidate,longitude, &
    result,config,residual,residual,status,operational)
  CALL check(status==STATUS_FAILED, &
             'nonfinite residual must be rejected before file creation',failures)

  IF (failures/=0) THEN
    PRINT *,'Real SHADOW I/O contract tests failed:',failures
    ERROR STOP 1
  END IF
  PRINT *,'Real SHADOW I/O contract tests passed'

CONTAINS

  SUBROUTINE make_state(state)
    TYPE(cloud_bal_state_type), INTENT(OUT) :: state
    INTEGER :: i,j,k,local_status
    CALL initialize_cloud_bal_state(state,2,2,2,1788224400_int64, &
                                    'io-contract-test',local_status)
    IF (local_status/=STATUS_OK) ERROR STOP 'state initialization failed'
    DO k=1,2; DO j=1,2; DO i=1,2
      state%grid%dx(i,j)=2000.0_real64
      state%grid%dy(i,j)=2200.0_real64
      state%pressure%value(i,j,k)=REAL(90000-20000*(k-1),real32)
      state%temperature%value(i,j,k)=280.0_real32
      state%vapor%value(i,j,k)=0.008_real32
      state%u%value(i,j,k)=5.0_real32
      state%v%value(i,j,k)=-2.0_real32
      state%omega%value(i,j,k)=0.0_real32
    END DO; END DO; END DO
    CALL mark_valid(state%pressure,SOURCE_BACKGROUND_MODEL)
    CALL mark_valid(state%temperature,SOURCE_BACKGROUND_MODEL)
    CALL mark_valid(state%vapor,SOURCE_BACKGROUND_MODEL)
    CALL mark_valid(state%u,SOURCE_ANALYZED_WIND)
    CALL mark_valid(state%v,SOURCE_ANALYZED_WIND)
    CALL mark_valid(state%omega,SOURCE_ANALYZED_WIND)
    CALL mark_valid(state%cloud_water,SOURCE_BACKGROUND_MODEL)
    CALL mark_valid(state%cloud_ice,SOURCE_BACKGROUND_MODEL)
    CALL mark_valid(state%rain,SOURCE_BACKGROUND_MODEL)
    CALL mark_valid(state%snow,SOURCE_BACKGROUND_MODEL)
    CALL mark_valid(state%graupel,SOURCE_BACKGROUND_MODEL)
    state%surface_pressure%value=100000.0_real32
    state%surface_pressure%valid=.TRUE.
    state%surface_pressure%quality=0_int32
    state%surface_pressure%source=SOURCE_BACKGROUND_MODEL
    CALL configure_pressure_geometry(state,local_status)
    IF (local_status/=STATUS_OK) ERROR STOP 'pressure geometry initialization failed'
    CALL refresh_dry_air_mass_measure(state,local_status)
    IF (local_status/=STATUS_OK) ERROR STOP 'dry-air mass refresh failed'
    state%omega_top_boundary%value=0.0_real32
    state%omega_bottom_boundary%value=0.0_real32
    state%omega_top_boundary%valid=.TRUE.
    state%omega_bottom_boundary%valid=.TRUE.
    state%omega_top_boundary%quality=IOR(QUALITY_LEGACY_PROVENANCE, &
      QUALITY_BOUNDARY_INTERIOR_COPY)
    state%omega_bottom_boundary%quality=IOR(QUALITY_LEGACY_PROVENANCE, &
      QUALITY_BOUNDARY_INTERIOR_COPY)
    state%omega_top_boundary%source=SOURCE_ANALYZED_WIND
    state%omega_bottom_boundary%source=SOURCE_ANALYZED_WIND
  END SUBROUTINE make_state

  SUBROUTINE mark_valid(field,source)
    TYPE(field3d), INTENT(INOUT) :: field
    INTEGER(int32), INTENT(IN) :: source
    field%valid=.TRUE.
    field%quality=0_int32
    field%source=source
  END SUBROUTINE mark_valid

  SUBROUTINE make_result(pipeline,nx,ny,nz)
    TYPE(cloud_bal_pipeline_result), INTENT(OUT) :: pipeline
    INTEGER, INTENT(IN) :: nx,ny,nz
    pipeline%status=STATUS_OK
    pipeline%reason_code=REASON_NONE
    pipeline%requested_mode=MODE_SHADOW
    CALL initialize_stage_result(pipeline%column,nx,ny,nz,STATUS_OK,REASON_NONE)
    CALL initialize_stage_result(pipeline%balance,nx,ny,nz,STATUS_OK,REASON_NONE)
    CALL initialize_stage_result(pipeline%overall,nx,ny,nz,STATUS_OK,REASON_NONE)
  END SUBROUTINE make_result

  SUBROUTINE check(condition,message,count)
    LOGICAL, INTENT(IN) :: condition
    CHARACTER(LEN=*), INTENT(IN) :: message
    INTEGER, INTENT(INOUT) :: count
    IF (.NOT.condition) THEN
      count=count+1
      PRINT *,'FAIL: ',TRIM(message)
    END IF
  END SUBROUTINE check

END PROGRAM test_real_shadow_io_contract
