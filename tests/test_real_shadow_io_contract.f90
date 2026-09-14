PROGRAM test_real_shadow_io_contract
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32,int64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value,ieee_quiet_nan
  USE netcdf
  USE cloud_bal_state
  USE cloud_bal_pipeline
  USE cloud_bal_pressure_analysis, ONLY: run_pressure_analysis_shadow
  USE cloud_bal_column_physics, ONLY: SATURATION_LIQUID,SATURATION_ICE
  USE cloud_bal_balance_operator, ONLY: TARGET_AUTHORITY_OBSERVATIONAL, &
                                        TARGET_AUTHORITY_MANUFACTURED_TEST, &
                                        balance_operator_type,build_balance_operator, &
                                        state_continuity_residual
  USE cloud_bal_real_netcdf, ONLY: validate_shadow_write_contract, &
                                   write_shadow_diagnostics,pipeline_result_replays, &
                                   put_pressure_transition_extension, &
                                   put_radar_reconstruction_inputs
  USE cloud_bal_wps_adapter, ONLY: pressure_wps_fields, &
                                   map_pressure_candidate_to_wps, &
                                   build_pressure_transition_prior
  USE setup, ONLY: valid_yyyy,valid_jjj,valid_hh,valid_min,hotstart, &
                   wind_coordinate,snow_thresh
  USE laps_static, ONLY: x,y,z3,dx,dy,grid_type
  USE lapsprep_wps, ONLY: output_ungrib_format
  IMPLICIT NONE

  TYPE(cloud_bal_state_type) :: input,candidate,operational
  TYPE(cloud_bal_pipeline_config) :: config
  TYPE(cloud_bal_pipeline_result) :: result
  REAL(real32) :: longitude(2,2)
  REAL(real64) :: residual(2,2,2)
  INTEGER :: failures,status,reason
  LOGICAL :: pressure_request_file_exists

  failures=0
  CALL test_pressure_dispatch_request_scope(failures)
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

  result%requested_surface_pressure=REAL(input%surface_pressure%value,real64)
  CALL write_shadow_diagnostics('unbound-pressure-request.nc',input,candidate,longitude, &
    result,config,residual,residual,status,operational)
  INQUIRE(FILE='unbound-pressure-request.nc',EXIST=pressure_request_file_exists)
  CALL check(status==STATUS_FAILED .AND. .NOT.pressure_request_file_exists, &
    'prescribed pressure request cannot use the old fixed-geometry sidecar',failures)
  CALL make_result(result,input%grid%nx,input%grid%ny,input%grid%nz)
  result%geometry_budget%geometry_mass_change_kg=1.0_real64
  CALL validate_shadow_write_contract(input,candidate,operational,result,config,status,reason)
  CALL check(status==STATUS_FAILED .AND. reason==REASON_AUTHORITY, &
    'unserialized geometry increment must be rejected',failures)
  CALL make_result(result,input%grid%nx,input%grid%ny,input%grid%nz)

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

  candidate%omega_target_sigma%value(1,1,1)=0.5_real32
  CALL validate_shadow_write_contract(input,candidate,operational,result,config,status,reason)
  CALL check(status==STATUS_FAILED .AND. reason==REASON_AUTHORITY, &
             'writer rejects changes to even inactive target uncertainty',failures)
  candidate=input

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

  CALL test_sigma_weighted_pipeline_shadow(failures)
  CALL test_pressure_analysis_candidate_shadow(failures)
  CALL test_joint_pressure_candidate_shadow(failures)
  CALL test_live_pressure_candidate_wps(failures)
  CALL test_geopotential_shadow_rejection(failures)
  CALL test_surface_anchored_geopotential_shadow(failures)
  CALL test_prescribed_surface_pressure_writer(failures)
  CALL test_thermo_shadow_io(failures)
  CALL test_cloud_qc_writer_replay(failures)
  CALL test_surface_boundary_serialization(failures)
  CALL test_pressure_transition_replay(failures)

  IF (failures/=0) THEN
    PRINT *,'Real SHADOW I/O contract tests failed:',failures
    ERROR STOP 1
  END IF
  PRINT *,'Real SHADOW I/O contract tests passed'

CONTAINS

  SUBROUTINE test_pressure_analysis_candidate_shadow(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: background,candidate,operational
    TYPE(cloud_bal_state_type) :: forged_input,forged_candidate,forged_operational
    TYPE(cloud_bal_pipeline_config) :: candidate_config
    TYPE(cloud_bal_pipeline_result) :: candidate_result
    TYPE(balance_operator_type) :: op
    REAL(real32) :: candidate_longitude(4,4)
    REAL(real32) :: original_target(4,4,3)
    REAL(real64) :: residual_before(4,4,3),residual_after(4,4,3)
    INTEGER(int32) :: original_valid(4,4,3),original_quality(4,4,3)
    INTEGER(int32) :: original_source(4,4,3)
    CHARACTER(LEN=256) :: text
    INTEGER :: status,reason,ncid,varid,rc,science_assessed,promotion_eligible
    LOGICAL :: seed_file_exists
    ! A single signed vertical target has no compensating vertical degree of
    ! freedom in this closed support. Preserve its target-response rejection.
    CALL make_pressure_target_case(background,15000.0_real32,3)
    candidate_config%requested_mode=MODE_SHADOW
    candidate_config%horizontal_support_radius_m=10000.0_real64
    candidate_config%pressure_support_radius_pa=20000.0_real64
    CALL run_cloud_bal_pipeline(background,candidate,operational,candidate_result, &
                                candidate_config)
    CALL check(candidate_result%status/=STATUS_OK .AND. &
      candidate_result%balance%numerical%target_response_failure_fraction>0.0_real64, &
      'uncompensated vertical target is rejected by unchanged response gate',failures)
    CALL check(canonical_states_equal(background,operational), &
      'rejected isolated target preserves operational state',failures)

    ! The opposite target at i=4 gives the [0,+a,0,-a] divergence pattern of
    ! the represented interior u(i=3) basis. Layer sums cancel, without changing
    ! geometry, observation error or gates. This tests a feasible A-grid mode;
    ! it does not certify arbitrary observational target fit or parity closure.
    CALL make_pressure_target_case(background,15000.0_real32,3)
    background%omega_target%value(4,2,3)=-background%omega_target%value(2,2,3)
    background%omega_target%valid(4,2,3)=.TRUE.
    background%omega_target%quality(4,2,3)=0_int32
    background%omega_target%source(4,2,3)=background%omega_target%source(2,2,3)
    background%omega_target_sigma%value(4,2,3)=background%omega_target_sigma%value(2,2,3)
    background%omega_target_sigma%valid(4,2,3)=.TRUE.
    background%omega_target_sigma%quality(4,2,3)=0_int32
    background%omega_target_sigma%source(4,2,3)=background%omega_target_sigma%source(2,2,3)
    CALL run_cloud_bal_pipeline(background,candidate,operational,candidate_result, &
                                candidate_config)
    CALL check(candidate_result%status==STATUS_OK .AND. &
      candidate_result%balance%numerical%solver_reason==SOLVER_CONVERGED, &
      'moderate-sigma physical-boundary pipeline converges',failures)
    CALL check(canonical_states_equal(background,operational), &
      'pressure candidate pipeline leaves operational state unchanged',failures)
    CALL check(ANY(ABS(candidate%u%value-background%u%value)>0.0_real32) .OR. &
               ANY(ABS(candidate%v%value-background%v%value)>0.0_real32) .OR. &
               ANY(ABS(candidate%omega%value-background%omega%value)>0.0_real32), &
      'moderate-sigma pressure candidate has a nonzero wind delta',failures)
    CALL check(ALL(candidate%pressure%value==background%pressure%value) .AND. &
               ALL(candidate%temperature%value==background%temperature%value) .AND. &
               ALL(candidate%vapor%value==background%vapor%value) .AND. &
               ALL(candidate%omega_target%value==background%omega_target%value) .AND. &
               ALL(candidate%omega_target%valid .EQV. background%omega_target%valid) .AND. &
               ALL(candidate%omega_target%quality==background%omega_target%quality) .AND. &
               ALL(candidate%omega_target%source==background%omega_target%source), &
      'pressure candidate preserves coordinates and original target arrays',failures)

    candidate_longitude=0.0_real32
    CALL build_balance_operator(candidate,candidate_config%balance,op,status,reason)
    CALL check(status==STATUS_OK,'pressure candidate diagnostic operator builds',failures)
    CALL state_continuity_residual(op,background,residual_before,status)
    CALL check(status==STATUS_OK,'pressure candidate background residual is derived',failures)
    CALL state_continuity_residual(op,candidate,residual_after,status)
    CALL check(status==STATUS_OK,'pressure candidate final residual is derived',failures)
    CALL check(ANY(ABS(residual_before-residual_after)>0.0_real64), &
      'pressure candidate residual arrays reflect the wind proposal',failures)

    CALL validate_shadow_write_contract(background,candidate,operational,candidate_result, &
      candidate_config,status,reason)
    CALL check(status==STATUS_FAILED .AND. reason==REASON_METADATA, &
      'physical-boundary candidate requires explicit pressure opt-in',failures)
    CALL validate_shadow_write_contract(background,candidate,operational,candidate_result, &
      candidate_config,status,reason,.TRUE.)
    CALL check(status==STATUS_OK .AND. reason==REASON_NONE, &
      'pressure candidate opt-in satisfies the extended writer contract',failures)

    CALL remove_if_present('pressure-candidate-with-seed.nc')
    candidate_result%pressure_transition_seed=candidate
    CALL validate_shadow_write_contract(background,candidate,operational,candidate_result, &
      candidate_config,status,reason,.TRUE.)
    CALL check(status==STATUS_FAILED .AND. reason==REASON_AUTHORITY, &
      'writer rejects an in-memory pressure transition seed',failures)
    CALL write_shadow_diagnostics('pressure-candidate-with-seed.nc',background,candidate, &
      candidate_longitude,candidate_result,candidate_config,residual_before,residual_after, &
      status,operational,.TRUE.)
    INQUIRE(FILE='pressure-candidate-with-seed.nc',EXIST=seed_file_exists)
    CALL check(status==STATUS_FAILED .AND. .NOT.seed_file_exists, &
      'writer does not publish an unrepresentable pressure transition seed',failures)
    DEALLOCATE(candidate_result%pressure_transition_seed)
    CALL validate_shadow_write_contract(background,candidate,operational,candidate_result, &
      candidate_config,status,reason,.TRUE.)
    CALL check(status==STATUS_OK .AND. reason==REASON_NONE, &
      'deallocating the pressure transition seed restores writer acceptance',failures)

    forged_input=background
    forged_input%omega_top_boundary%source=SOURCE_ANALYZED_WIND
    CALL validate_shadow_write_contract(forged_input,candidate,operational,candidate_result, &
      candidate_config,status,reason,.TRUE.)
    CALL check(status==STATUS_FAILED,'forged original boundary provenance is rejected',failures)
    forged_candidate=candidate
    forged_candidate%omega_bottom_boundary%quality=QUALITY_BOUNDARY_INTERIOR_COPY
    forged_candidate%omega_bottom_boundary%source=SOURCE_ANALYZED_WIND
    CALL validate_shadow_write_contract(background,forged_candidate,operational,candidate_result, &
      candidate_config,status,reason,.TRUE.)
    CALL check(status==STATUS_FAILED,'forged candidate boundary provenance is rejected',failures)
    forged_operational=operational
    forged_operational%omega_top_boundary%quality=QUALITY_BOUNDARY_INTERIOR_COPY
    forged_operational%omega_top_boundary%source=SOURCE_ANALYZED_WIND
    CALL validate_shadow_write_contract(background,candidate,forged_operational,candidate_result, &
      candidate_config,status,reason,.TRUE.)
    CALL check(status==STATUS_FAILED,'forged operational boundary provenance is rejected',failures)

    original_target=background%omega_target%value
    original_valid=MERGE(1_int32,0_int32,background%omega_target%valid)
    original_quality=background%omega_target%quality
    original_source=background%omega_target%source
    CALL write_shadow_diagnostics('pressure-candidate-shadow.nc',background,candidate, &
      candidate_longitude,candidate_result,candidate_config,residual_before,residual_after, &
      status,operational,.TRUE.)
    CALL check(status==STATUS_OK,'pressure candidate shadow artifact is writable',failures)
    IF (status/=STATUS_OK) RETURN

    rc=nf90_open('pressure-candidate-shadow.nc',NF90_NOWRITE,ncid)
    CALL check(rc==NF90_NOERR,'pressure candidate shadow opens for readback',failures)
    IF (rc/=NF90_NOERR) RETURN
    rc=nf90_get_att(ncid,NF90_GLOBAL,'contract',text)
    CALL check(rc==NF90_NOERR .AND. TRIM(text)=='pressure_analysis_shadow_v1', &
      'pressure candidate contract metadata is exact',failures)
    rc=nf90_get_att(ncid,NF90_GLOBAL,'pressure_analysis_candidate_contract',text)
    CALL check(rc==NF90_NOERR .AND. TRIM(text)=='pressure_analysis_candidate_v1', &
      'pressure candidate extension metadata is exact',failures)
    rc=nf90_get_att(ncid,NF90_GLOBAL,'evidence_class',text)
    CALL check(rc==NF90_NOERR .AND. TRIM(text)=='PRESSURE_ANALYSIS_SHADOW_PROPOSAL', &
      'pressure candidate evidence class is proposal-only',failures)
    rc=nf90_get_att(ncid,NF90_GLOBAL,'configuration_id',text)
    CALL check(rc==NF90_NOERR .AND. TRIM(text)=='pressure-analysis-shadow-v1', &
      'pressure candidate configuration id is exact',failures)
    rc=nf90_get_att(ncid,NF90_GLOBAL,'omega_boundary_provenance',text)
    CALL check(rc==NF90_NOERR .AND. TRIM(text)=='PHYSICAL_INPUT_DIAGNOSTIC_ONLY', &
      'physical boundary provenance remains explicit',failures)
    rc=nf90_get_att(ncid,NF90_GLOBAL,'science_assessed',science_assessed)
    CALL check(rc==NF90_NOERR .AND. science_assessed==0, &
      'pressure candidate does not claim science assessment',failures)
    rc=nf90_get_att(ncid,NF90_GLOBAL,'promotion_eligible',promotion_eligible)
    CALL check(rc==NF90_NOERR .AND. promotion_eligible==0, &
      'pressure candidate is not promotion eligible',failures)
    rc=nf90_inq_varid(ncid,'original_omega_target',varid)
    IF (rc==NF90_NOERR) rc=nf90_get_var(ncid,varid,original_target)
    CALL check(rc==NF90_NOERR .AND. ALL(original_target==background%omega_target%value), &
      'original omega target values are read back exactly',failures)
    rc=nf90_inq_varid(ncid,'original_omega_target_valid',varid)
    IF (rc==NF90_NOERR) rc=nf90_get_var(ncid,varid,original_valid)
    CALL check(rc==NF90_NOERR .AND. ALL(original_valid==MERGE(1_int32,0_int32, &
      background%omega_target%valid)),'original target validity is read back exactly',failures)
    rc=nf90_inq_varid(ncid,'original_omega_target_quality',varid)
    IF (rc==NF90_NOERR) rc=nf90_get_var(ncid,varid,original_quality)
    CALL check(rc==NF90_NOERR .AND. ALL(original_quality==background%omega_target%quality), &
      'original target quality is read back exactly',failures)
    rc=nf90_inq_varid(ncid,'original_omega_target_source',varid)
    IF (rc==NF90_NOERR) rc=nf90_get_var(ncid,varid,original_source)
    CALL check(rc==NF90_NOERR .AND. ALL(original_source==background%omega_target%source), &
      'original target provenance is read back exactly',failures)
    rc=nf90_close(ncid)
  END SUBROUTINE test_pressure_analysis_candidate_shadow

  SUBROUTINE test_joint_pressure_candidate_shadow(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: background,candidate,operational
    TYPE(cloud_bal_pipeline_config) :: config
    TYPE(cloud_bal_pipeline_result) :: result,forged
    TYPE(balance_operator_type) :: op
    LOGICAL :: active(4,4,3),exists
    INTEGER(int32) :: surface(4,4,3)
    REAL(real32) :: longitude(4,4)
    REAL(real64) :: before(4,4,3),after(4,4,3)
    INTEGER :: trial,status,reason
    CHARACTER(LEN=40) :: path

    CALL make_pressure_target_case(background,15000.0_real32,3)
    background%omega_target%value(4,2,3)=-background%omega_target%value(2,2,3)
    background%omega_target%valid(4,2,3)=.TRUE.
    background%omega_target%quality(4,2,3)=0_int32
    background%omega_target%source(4,2,3)=background%omega_target%source(2,2,3)
    background%omega_target_sigma%value(4,2,3)=background%omega_target_sigma%value(2,2,3)
    background%omega_target_sigma%valid(4,2,3)=.TRUE.
    background%omega_target_sigma%quality(4,2,3)=0_int32
    background%omega_target_sigma%source(4,2,3)=background%omega_target_sigma%source(2,2,3)
    background%cloud_water%value(2,2,3)=0.002_real32
    CALL refresh_dry_air_mass_measure(background,status)
    CALL check(status==STATUS_OK,'joint pressure fixture mass is canonical',failures)
    active=.FALSE.; active(2,2,3)=.TRUE.
    surface=SATURATION_LIQUID
    longitude=0.0_real32
    config%requested_mode=MODE_SHADOW
    config%horizontal_support_radius_m=10000.0_real64
    config%pressure_support_radius_pa=20000.0_real64
    DO trial=1,2
      config%maximum_outer_iterations=1
      path='pressure-thermo-candidate-shadow.nc'
      IF (trial==2) THEN
        config%maximum_outer_iterations=16
        path='pressure-outer-candidate-shadow.nc'
      END IF
      CALL run_cloud_bal_pipeline(background,candidate,operational,result,config,active,surface,0.8_real64)
      CALL check(result%status==STATUS_OK,'joint pressure pipeline accepts candidate',failures)
      IF (result%status/=STATUS_OK) CYCLE
      CALL check(canonical_states_equal(background,operational),'joint operational identity',failures)
      CALL check(ANY(candidate%temperature%value/=background%temperature%value) .AND. &
        ANY(candidate%vapor%value/=background%vapor%value) .AND. &
        ANY(candidate%omega%value/=background%omega%value), &
        'joint pressure candidate changes thermo and wind together',failures)
      IF (trial==2) CALL check(result%outer_converged .AND. result%outer_iterations>1, &
        'joint pressure outer iteration converges beyond first trial',failures)
      CALL build_balance_operator(candidate,config%balance,op,status,reason)
      CALL check(status==STATUS_OK,'joint candidate operator builds',failures)
      IF (status/=STATUS_OK) CYCLE
      CALL state_continuity_residual(op,background,before,status)
      CALL check(status==STATUS_OK,'joint original residual reconstructed',failures)
      CALL state_continuity_residual(op,candidate,after,status)
      CALL check(status==STATUS_OK,'joint final residual reconstructed',failures)
      CALL write_shadow_diagnostics(TRIM(path),background,candidate,longitude,result,config, &
        before,after,status,operational,.TRUE.)
      CALL check(status==STATUS_OK,'joint pressure candidate serializes without relabeling',failures)
      ! A balanced ledger or plausible iteration count is not producer lineage.
      ! Reject forged receipts before creating any diagnostic file.
      forged=result
      forged%column%numerical%flux_input=forged%column%numerical%flux_input+1.0_real64
      forged%column%numerical%flux_suspended=forged%column%numerical%flux_suspended+1.0_real64
      CALL write_shadow_diagnostics('forged-joint-flux.nc',background,candidate,longitude,forged,config, &
        before,after,status,operational,.TRUE.)
      INQUIRE(FILE='forged-joint-flux.nc',EXIST=exists)
      CALL check(status/=STATUS_OK .AND. .NOT.exists,'joint writer rejects balanced forged flux receipt',failures)
      forged=result
      forged%balance%numerical%solver_iterations=forged%balance%numerical%solver_iterations+1
      CALL write_shadow_diagnostics('forged-joint-solver.nc',background,candidate,longitude,forged,config, &
        before,after,status,operational,.TRUE.)
      INQUIRE(FILE='forged-joint-solver.nc',EXIST=exists)
      CALL check(status/=STATUS_OK .AND. .NOT.exists,'joint writer rejects forged solver receipt',failures)
    END DO
  END SUBROUTINE test_joint_pressure_candidate_shadow

  SUBROUTINE test_live_pressure_candidate_wps(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: background,candidate,operational
    TYPE(cloud_bal_pipeline_config) :: config
    TYPE(cloud_bal_pipeline_result) :: result
    TYPE(balance_operator_type) :: op
    TYPE(pressure_wps_fields) :: wps_background,wps_candidate
    LOGICAL :: thermo_active(4,4,3),geopotential_support(4,4,3)
    INTEGER :: thermo_surface(4,4,3),geopotential_reference_level(4,4)
    REAL(real32) :: longitude(4,4)
    REAL(real64) :: residual_before(4,4,3),residual_after(4,4,3)
    INTEGER :: status,reason,writer_status
    LOGICAL :: exists
    CHARACTER(LEN=*), PARAMETER :: background_path='pipeline_pressure_background.wps'
    CHARACTER(LEN=*), PARAMETER :: candidate_path='pipeline_pressure_candidate.wps'

    ! This is the accepted synthetic thermo/Phi pipeline fixture.  It is
    ! intentionally in-memory: no diagnostic is read back to reconstruct a
    ! canonical state, and this does not claim native/real-data provenance.
    CALL make_pressure_target_case(background,15000.0_real32,3)
    background%omega_target%value(4,2,3)=-background%omega_target%value(2,2,3)
    background%omega_target%valid(4,2,3)=.TRUE.
    background%omega_target%quality(4,2,3)=0_int32
    background%omega_target%source(4,2,3)=background%omega_target%source(2,2,3)
    background%omega_target_sigma%value(4,2,3)=background%omega_target_sigma%value(2,2,3)
    background%omega_target_sigma%valid(4,2,3)=.TRUE.
    background%omega_target_sigma%quality(4,2,3)=0_int32
    background%omega_target_sigma%source(4,2,3)=background%omega_target_sigma%source(2,2,3)
    background%cloud_water%value(3,2,2)=0.002_real32
    background%geopotential%value(:,:,1)=1000.0_real32
    background%geopotential%value(:,:,2)=1500.0_real32
    background%geopotential%value(:,:,3)=2000.0_real32
    CALL mark_valid(background%geopotential,SOURCE_BACKGROUND_MODEL)
    background%surface_temperature%value=280.0_real32
    background%surface_temperature%valid=.TRUE.
    background%surface_temperature%quality=0_int32
    background%surface_temperature%source=SOURCE_BACKGROUND_MODEL
    CALL refresh_dry_air_mass_measure(background,status)
    CALL check(status==STATUS_OK,'live WPS fixture mass is canonical',failures)

    thermo_active=.FALSE.; thermo_active(3,2,2)=.TRUE.
    thermo_surface=SATURATION_LIQUID
    geopotential_support=.FALSE.; geopotential_support(3,2,:)=.TRUE.
    geopotential_reference_level=0; geopotential_reference_level(3,2)=1
    config%requested_mode=MODE_SHADOW
    config%maximum_outer_iterations=1
    config%horizontal_support_radius_m=10000.0_real64
    config%pressure_support_radius_pa=20000.0_real64
    CALL run_cloud_bal_pipeline(background,candidate,operational,result,config, &
      thermo_active,thermo_surface,0.8_real64,geopotential_support, &
      geopotential_reference_level)
    CALL check(result%status==STATUS_OK .AND. result%geopotential%status==STATUS_OK, &
      'live WPS source pipeline is accepted',failures)
    IF (result%status/=STATUS_OK .OR. result%geopotential%status/=STATUS_OK) RETURN
    CALL check(ANY(ABS(candidate%temperature%value-background%temperature%value)>1.0e-6_real32), &
      'live WPS candidate changes temperature',failures)
    CALL check(ANY(ABS(candidate%vapor%value-background%vapor%value)>1.0e-9_real32), &
      'live WPS candidate changes vapor',failures)
    CALL check(ANY(ABS(candidate%geopotential%value-background%geopotential%value)>1.0e-5_real32), &
      'live WPS candidate changes geopotential',failures)
    CALL check(canonical_states_equal(background,operational), &
      'live WPS source pipeline preserves operational identity',failures)

    longitude=0.0_real32
    CALL build_balance_operator(candidate,config%balance,op,status,reason)
    CALL check(status==STATUS_OK,'live WPS diagnostic operator builds',failures)
    IF (status/=STATUS_OK) RETURN
    CALL state_continuity_residual(op,background,residual_before,status)
    CALL check(status==STATUS_OK,'live WPS background residual builds',failures)
    IF (status/=STATUS_OK) RETURN
    CALL state_continuity_residual(op,candidate,residual_after,status)
    CALL check(status==STATUS_OK,'live WPS candidate residual builds',failures)
    IF (status/=STATUS_OK) RETURN
    CALL remove_if_present('pipeline_pressure_candidate.nc')
    CALL write_shadow_diagnostics('pipeline_pressure_candidate.nc',background,candidate, &
      longitude,result,config,residual_before,residual_after,status,operational,.TRUE.)
    INQUIRE(FILE='pipeline_pressure_candidate.nc',EXIST=exists)
    CALL check(status==STATUS_OK .AND. exists, &
      'live WPS candidate diagnostic is from the same pipeline result',failures)

    CALL build_live_wps_inventory(background,wps_background,status)
    CALL check(status==STATUS_OK,'live WPS retained inventory is explicit and complete',failures)
    IF (status/=STATUS_OK) RETURN
    CALL map_pressure_candidate_to_wps(candidate,wps_background,wps_candidate,status, &
      'GRID_RELATIVE')
    CALL check(status==STATUS_OK,'live candidate maps into retained WPS inventory',failures)
    IF (status/=STATUS_OK) RETURN
    CALL check(ANY(ABS(wps_candidate%t-wps_background%t)>1.0e-6_real32) .AND. &
      ANY(ABS(wps_candidate%qv-wps_background%qv)>1.0e-9_real32) .AND. &
      ANY(ABS(wps_candidate%ht-wps_background%ht)>1.0e-6_real32), &
      'mapped WPS inventory retains T/QV/Phi physical changes',failures)

    ! Match writer globals to the canonical grid/time rather than the stub
    ! defaults.  The writer is the actual LAPSPREP WPS binary writer.
    x=background%grid%nx; y=background%grid%ny; z3=background%grid%nz
    dx=REAL(background%grid%dx(1,1),KIND(dx)); dy=REAL(background%grid%dy(1,1),KIND(dy))
    hotstart=.TRUE.; wind_coordinate='GRID_RELATIVE'; grid_type='mercator'
    valid_yyyy=2026; valid_jjj=244; valid_hh=1; valid_min=0; snow_thresh=0.5
    CALL remove_if_present(background_path)
    CALL output_ungrib_format(wps_background%p,wps_background%t,wps_background%ht, &
      wps_background%u,wps_background%v,wps_background%rh,wps_background%slp, &
      wps_background%psfc,wps_background%qc,wps_background%qr,wps_background%qs, &
      wps_background%qi,wps_background%qg,wps_background%snow_cover, &
      wps_background%skin_temperature,writer_status, &
      resolved_output_file=background_path,vapor_mixing_ratio=wps_background%qv)
    INQUIRE(FILE=background_path,EXIST=exists)
    CALL check(writer_status==1 .AND. exists,'actual WPS writer emits background inventory',failures)
    CALL remove_if_present(candidate_path)
    CALL output_ungrib_format(wps_candidate%p,wps_candidate%t,wps_candidate%ht, &
      wps_candidate%u,wps_candidate%v,wps_candidate%rh,wps_candidate%slp, &
      wps_candidate%psfc,wps_candidate%qc,wps_candidate%qr,wps_candidate%qs, &
      wps_candidate%qi,wps_candidate%qg,wps_candidate%snow_cover, &
      wps_candidate%skin_temperature,writer_status, &
      resolved_output_file=candidate_path,vapor_mixing_ratio=wps_candidate%qv)
    INQUIRE(FILE=candidate_path,EXIST=exists)
    CALL check(writer_status==1 .AND. exists,'actual WPS writer emits candidate inventory',failures)
  END SUBROUTINE test_live_pressure_candidate_wps

  SUBROUTINE build_live_wps_inventory(state,wps,status)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    TYPE(pressure_wps_fields), INTENT(OUT) :: wps
    INTEGER, INTENT(OUT) :: status
    INTEGER :: nx,ny,nz,l,k,alloc_status

    status=STATUS_FAILED
    nx=state%grid%nx; ny=state%grid%ny; nz=state%grid%nz
    IF (nx/=4 .OR. ny/=4 .OR. nz/=3) RETURN
    ALLOCATE(wps%p(nz+1),wps%t(nx,ny,nz+1),wps%ht(nx,ny,nz+1), &
      wps%u(nx,ny,nz+1),wps%v(nx,ny,nz+1),wps%rh(nx,ny,nz+1), &
      wps%qv(nx,ny,nz+1),wps%qc(nx,ny,nz),wps%qi(nx,ny,nz), &
      wps%qr(nx,ny,nz),wps%qs(nx,ny,nz),wps%qg(nx,ny,nz), &
      wps%psfc(nx,ny),wps%slp(nx,ny),wps%skin_temperature(nx,ny), &
      wps%snow_cover(nx,ny),STAT=alloc_status)
    IF (alloc_status/=0) RETURN
    wps%p=0.0_real32; wps%t=280.0_real32; wps%ht=0.0_real32
    wps%u=5.0_real32; wps%v=-2.0_real32; wps%rh=55.0_real32
    wps%qv=0.008_real32; wps%qc=0.0_real32; wps%qi=0.0_real32
    wps%qr=0.0_real32; wps%qs=0.0_real32; wps%qg=0.0_real32
    wps%psfc=100000.0_real32; wps%slp=101000.0_real32
    wps%skin_temperature=280.0_real32; wps%snow_cover=0.0_real32
    DO l=1,nz
      k=nz+1-l
      IF (ANY(state%pressure%value(:,:,k)/=state%pressure%value(1,1,k))) RETURN
      wps%p(l)=state%pressure%value(1,1,k)/100.0_real32
      wps%t(:,:,l)=state%temperature%value(:,:,k)
      wps%ht(:,:,l)=REAL(REAL(state%geopotential%value(:,:,k),real64)/9.80665_real64,real32)
      wps%u(:,:,l)=state%u%value(:,:,k); wps%v(:,:,l)=state%v%value(:,:,k)
      wps%qv(:,:,l)=state%vapor%value(:,:,k)
      wps%qc(:,:,l)=state%cloud_water%value(:,:,k)
      wps%qi(:,:,l)=state%cloud_ice%value(:,:,k)
      wps%qr(:,:,l)=state%rain%value(:,:,k)
      wps%qs(:,:,l)=state%snow%value(:,:,k)
      wps%qg(:,:,l)=state%graupel%value(:,:,k)
    END DO
    wps%p(nz+1)=2001.0_real32
    wps%t(:,:,nz+1)=state%surface_temperature%value
    wps%ht(:,:,nz+1)=wps%ht(:,:,1)
    wps%qv(:,:,nz+1)=0.008_real32
    wps%psfc=state%surface_pressure%value
    wps%slp=state%surface_pressure%value+1000.0_real32
    wps%skin_temperature=state%surface_temperature%value
    wps%valid_time=state%pressure%valid_time
    wps%grid_id=state%grid%grid_id
    wps%wind_coordinate='GRID_RELATIVE'
    status=STATUS_OK
  END SUBROUTINE build_live_wps_inventory

  SUBROUTINE test_geopotential_shadow_rejection(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: background,candidate,operational
    TYPE(cloud_bal_state_type) :: forged_candidate
    TYPE(cloud_bal_pipeline_config) :: config,outer_config
    TYPE(cloud_bal_pipeline_result) :: result,outer_result,off_result,forged_result
    TYPE(balance_operator_type) :: op
    LOGICAL :: thermo_active(4,4,3),geopotential_support(4,4,3),exists
    LOGICAL :: malformed_support(4,4,2)
    INTEGER :: thermo_surface(4,4,3),geopotential_reference_level(4,4)
    INTEGER :: malformed_reference(4,4)
    REAL(real32) :: longitude(4,4)
    REAL(real64) :: residual_before(4,4,3),residual_after(4,4,3)
    INTEGER :: k,status,reason
    CHARACTER(LEN=*), PARAMETER :: path='geopotential-candidate-shadow.nc'
    CHARACTER(LEN=*), PARAMETER :: outer_path='geopotential-outer-candidate-shadow.nc'
    CHARACTER(LEN=*), PARAMETER :: hidden_path='geopotential-hidden-shadow.nc'
    CHARACTER(LEN=*), PARAMETER :: malformed_path='geopotential-malformed-shadow.nc'

    ! Reuse the accepted joint pressure/thermo fixture, but provide the
    ! monotonic Phi profile required by the explicit geopotential stage.
    CALL make_pressure_target_case(background,15000.0_real32,3)
    background%omega_target%value(4,2,3)=-background%omega_target%value(2,2,3)
    background%omega_target%valid(4,2,3)=.TRUE.
    background%omega_target%quality(4,2,3)=0_int32
    background%omega_target%source(4,2,3)=background%omega_target%source(2,2,3)
    background%omega_target_sigma%value(4,2,3)=background%omega_target_sigma%value(2,2,3)
    background%omega_target_sigma%valid(4,2,3)=.TRUE.
    background%omega_target_sigma%quality(4,2,3)=0_int32
    background%omega_target_sigma%source(4,2,3)=background%omega_target_sigma%source(2,2,3)
    ! Heating at level 2 propagates the hydrostatic increment into level 3,
    ! exercising a Phi-only propagated cell in the serialized support.
    background%cloud_water%value(3,2,2)=0.002_real32
    DO k=1,3
      background%geopotential%value(:,:,k)=1000.0_real32+ &
        500.0_real32*REAL(k-1,real32)
    END DO
    CALL mark_valid(background%geopotential,SOURCE_BACKGROUND_MODEL)
    CALL refresh_dry_air_mass_measure(background,status)
    CALL check(status==STATUS_OK,'geopotential fixture mass is canonical',failures)

    thermo_active=.FALSE.; thermo_active(3,2,2)=.TRUE.
    thermo_surface=SATURATION_LIQUID
    geopotential_support=.FALSE.; geopotential_support(3,2,:)=.TRUE.
    ! References are Fortran 1-based only for active columns; zero is the
    ! serialized inactive sentinel required by the optional Phi extension.
    geopotential_reference_level=0; geopotential_reference_level(3,2)=1
    longitude=0.0_real32
    config%requested_mode=MODE_SHADOW
    config%maximum_outer_iterations=1
    config%horizontal_support_radius_m=10000.0_real64
    config%pressure_support_radius_pa=20000.0_real64
    CALL run_cloud_bal_pipeline(background,candidate,operational,result,config, &
      thermo_active,thermo_surface,0.8_real64,geopotential_support, &
      geopotential_reference_level)
    CALL check(result%status==STATUS_OK .AND. result%geopotential%status==STATUS_OK .AND. &
      ALLOCATED(result%geopotential_support) .AND. &
      ALLOCATED(result%geopotential_reference_level), &
      'accepted geopotential request reaches SHADOW result',failures)
    IF (ALLOCATED(result%geopotential_support) .AND. &
        ALLOCATED(result%geopotential_reference_level)) THEN
      CALL check(ALL(result%geopotential_support .EQV. geopotential_support) .AND. &
        ALL(result%geopotential_reference_level==geopotential_reference_level), &
        'geopotential request stores support and inactive references exactly',failures)
    END IF
    CALL check(ANY(candidate%geopotential%value/=background%geopotential%value), &
      'accepted geopotential request changes candidate Phi',failures)
    CALL check(canonical_states_equal(background,operational), &
      'geopotential proposal preserves operational identity',failures)

    ! The writer receives independently reconstructed continuity ledgers, as
    ! the Python validator does; zero placeholders would hide a changed wind.
    CALL build_balance_operator(candidate,config%balance,op,status,reason)
    CALL check(status==STATUS_OK,'geopotential candidate diagnostic operator builds',failures)
    IF (status==STATUS_OK) THEN
      CALL state_continuity_residual(op,background,residual_before,status)
      CALL check(status==STATUS_OK,'geopotential background residual is derived',failures)
      CALL state_continuity_residual(op,candidate,residual_after,status)
      CALL check(status==STATUS_OK,'geopotential candidate residual is derived',failures)
    ELSE
      residual_before=0.0_real64; residual_after=0.0_real64
    END IF

    CALL remove_if_present(path)
    CALL write_shadow_diagnostics(path,background,candidate,longitude,result,config, &
      residual_before,residual_after,status,operational,.TRUE.)
    INQUIRE(FILE=path,EXIST=exists)
    CALL check(status==STATUS_OK .AND. exists, &
      'schema-7 geopotential pressure candidate is writable',failures)

    ! The same immutable background is replayed for the bounded outer solve;
    ! this produces the schema-8 fixture consumed by independent validation.
    outer_config=config
    outer_config%maximum_outer_iterations=16
    CALL run_cloud_bal_pipeline(background,candidate,operational,outer_result,outer_config, &
      thermo_active,thermo_surface,0.8_real64,geopotential_support, &
      geopotential_reference_level)
    CALL check(outer_result%status==STATUS_OK .AND. outer_result%outer_converged .AND. &
      outer_result%outer_iterations>1 .AND. ALLOCATED(outer_result%geopotential_support), &
      'outer geopotential pressure candidate converges with Phi support',failures)
    IF (outer_result%status==STATUS_OK) THEN
      CALL build_balance_operator(candidate,outer_config%balance,op,status,reason)
      CALL check(status==STATUS_OK,'outer geopotential diagnostic operator builds',failures)
      IF (status==STATUS_OK) THEN
        CALL state_continuity_residual(op,background,residual_before,status)
        CALL state_continuity_residual(op,candidate,residual_after,status)
      ELSE
        residual_before=0.0_real64; residual_after=0.0_real64
      END IF
      CALL remove_if_present(outer_path)
      CALL write_shadow_diagnostics(outer_path,background,candidate,longitude,outer_result, &
        outer_config,residual_before,residual_after,status,operational,.TRUE.)
      INQUIRE(FILE=outer_path,EXIST=exists)
      CALL check(status==STATUS_OK .AND. exists, &
        'schema-8 geopotential pressure candidate is writable',failures)
    END IF

    ! A receipt cannot be replayed with a missing or malformed Phi permission.
    forged_result=result
    IF (ALLOCATED(forged_result%geopotential_reference_level)) &
      DEALLOCATE(forged_result%geopotential_reference_level)
    CALL remove_if_present(malformed_path)
    CALL write_shadow_diagnostics(malformed_path,background,candidate,longitude,forged_result, &
      config,residual_before,residual_after,status,operational,.TRUE.)
    INQUIRE(FILE=malformed_path,EXIST=exists)
    CALL check(status/=STATUS_OK .AND. .NOT.exists, &
      'writer rejects malformed geopotential request pair before file creation',failures)

    forged_result=result
    forged_result%geopotential_support(1,1,1)=.TRUE.
    CALL remove_if_present(malformed_path)
    CALL write_shadow_diagnostics(malformed_path,background,candidate,longitude,forged_result, &
      config,residual_before,residual_after,status,operational,.TRUE.)
    INQUIRE(FILE=malformed_path,EXIST=exists)
    CALL check(status/=STATUS_OK .AND. .NOT.exists, &
      'writer rejects Phi support outside its reference column',failures)

    forged_result=result
    forged_result%geopotential_reference_level(2,2)=0
    CALL remove_if_present(malformed_path)
    CALL write_shadow_diagnostics(malformed_path,background,candidate,longitude,forged_result, &
      config,residual_before,residual_after,status,operational,.TRUE.)
    INQUIRE(FILE=malformed_path,EXIST=exists)
    CALL check(status/=STATUS_OK .AND. .NOT.exists, &
      'writer rejects invalid active Phi reference level',failures)

    forged_result=result
    forged_result%status=STATUS_FAILED
    CALL remove_if_present(malformed_path)
    CALL write_shadow_diagnostics(malformed_path,background,candidate,longitude,forged_result, &
      config,residual_before,residual_after,status,operational,.TRUE.)
    INQUIRE(FILE=malformed_path,EXIST=exists)
    CALL check(status/=STATUS_OK .AND. .NOT.exists, &
      'writer rejects failed Phi result before file creation',failures)

    ! A changed Phi candidate with its request receipt stripped is the hidden
    ! replay that the legacy pressure writer must reject.
    forged_result=result
    IF (ALLOCATED(forged_result%geopotential_support)) &
      DEALLOCATE(forged_result%geopotential_support)
    IF (ALLOCATED(forged_result%geopotential_reference_level)) &
      DEALLOCATE(forged_result%geopotential_reference_level)
    forged_candidate=candidate
    forged_candidate%geopotential%value(1,1,1)= &
      forged_candidate%geopotential%value(1,1,1)+1.0_real32
    CALL remove_if_present(hidden_path)
    CALL write_shadow_diagnostics(hidden_path,background,forged_candidate,longitude, &
      forged_result,config,residual_before,residual_after,status,operational,.TRUE.)
    INQUIRE(FILE=hidden_path,EXIST=exists)
    CALL check(status/=STATUS_OK .AND. .NOT.exists, &
      'writer rejects changed Phi hidden from replay receipt',failures)

    ! A legacy non-pressure caller cannot serialize a Phi candidate merely by
    ! passing the old writer opt-in; the receipt itself is required.
    forged_result=result
    forged_candidate=candidate
    CALL remove_if_present(hidden_path)
    CALL write_shadow_diagnostics(hidden_path,background,forged_candidate,longitude, &
      forged_result,config,residual_before,residual_after,status,operational)
    INQUIRE(FILE=hidden_path,EXIST=exists)
    CALL check(status/=STATUS_OK .AND. .NOT.exists, &
      'legacy nonpressure writer rejects requested Phi without opt-in',failures)

    ! The pipeline rejects malformed optional request pairs and support shapes
    ! before any analysis can leak into candidate or operational state.
    CALL run_cloud_bal_pipeline(background,candidate,operational,forged_result,config, &
      thermo_active,thermo_surface,0.8_real64,geopotential_support)
    CALL check(forged_result%status==STATUS_FAILED .AND. &
      canonical_states_equal(background,candidate) .AND. &
      canonical_states_equal(background,operational), &
      'missing Phi request pair rolls back before analysis',failures)
    malformed_support=.TRUE.
    malformed_reference=geopotential_reference_level
    CALL run_cloud_bal_pipeline(background,candidate,operational,forged_result,config, &
      thermo_active,thermo_surface,0.8_real64,malformed_support,malformed_reference)
    CALL check(forged_result%status==STATUS_FAILED .AND. &
      canonical_states_equal(background,candidate) .AND. &
      canonical_states_equal(background,operational), &
      'wrong Phi support shape rolls back before analysis',failures)

    ! MODE_OFF remains a strict no-op even when a geopotential request is
    ! supplied; the request is not accepted or stored in the result.
    config%requested_mode=MODE_OFF
    CALL run_cloud_bal_pipeline(background,candidate,operational,off_result,config, &
      thermo_active,thermo_surface,0.8_real64,geopotential_support, &
      geopotential_reference_level)
    CALL check(off_result%status==STATUS_OK .AND. &
      .NOT.ALLOCATED(off_result%geopotential_support) .AND. &
      .NOT.ALLOCATED(off_result%geopotential_reference_level) .AND. &
      canonical_states_equal(background,candidate) .AND. &
      canonical_states_equal(background,operational), &
      'MODE_OFF preserves candidate and operational identity',failures)
  END SUBROUTINE test_geopotential_shadow_rejection

  SUBROUTINE test_surface_anchored_geopotential_shadow(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: background,candidate,operational
    TYPE(cloud_bal_pipeline_config) :: config
    TYPE(cloud_bal_pipeline_result) :: result
    TYPE(balance_operator_type) :: op
    LOGICAL :: thermo_active(4,4,3),geopotential_support(4,4,3),exists
    INTEGER :: thermo_surface(4,4,3),geopotential_reference_level(4,4)
    REAL(real32) :: longitude(4,4)
    REAL(real64) :: residual_before(4,4,3),residual_after(4,4,3)
    INTEGER :: k,status,reason,rc,ncid
    CHARACTER(LEN=256) :: contract,reference,condensate
    CHARACTER(LEN=*), PARAMETER :: path='surface-geopotential-shadow.nc'

    ! Reuse the accepted coupled pressure/thermo/Phi fixture.  This case adds
    ! only complete surface fields required by the explicit surface anchor;
    ! it is not a second pipeline framework.
    CALL make_pressure_target_case(background,15000.0_real32,3)
    background%omega_target%value(4,2,3)=-background%omega_target%value(2,2,3)
    background%omega_target%valid(4,2,3)=.TRUE.
    background%omega_target%quality(4,2,3)=0_int32
    background%omega_target%source(4,2,3)=background%omega_target%source(2,2,3)
    background%omega_target_sigma%value(4,2,3)=background%omega_target_sigma%value(2,2,3)
    background%omega_target_sigma%valid(4,2,3)=.TRUE.
    background%omega_target_sigma%quality(4,2,3)=0_int32
    background%omega_target_sigma%source(4,2,3)=background%omega_target_sigma%source(2,2,3)
    ! Put the thermo perturbation at the first represented layer so the
    ! surface-to-first-layer hydrostatic thickness changes measurably.
    background%cloud_water%value(3,2,1)=0.002_real32
    DO k=1,3
      background%geopotential%value(:,:,k)=1000.0_real32+ &
        500.0_real32*REAL(k-1,real32)
    END DO
    CALL mark_valid(background%geopotential,SOURCE_BACKGROUND_MODEL)

    ! Use complete field2d values with model-source metadata, including terrain
    ! below the lowest represented geopotential (1000 m2 s-2 / g ~= 102 m).
    ! This remains a synthetic test state; source bits do not claim observations.
    ! Surface condensates follow WPS_SURFACE_ZERO_CONDENSATE: qv is supplied
    ! and all surface condensate components are explicit zeros in the kernel.
    background%surface_pressure%value=100000.0_real32
    background%surface_pressure%valid=.TRUE.
    background%surface_pressure%quality=0_int32
    background%surface_pressure%source=SOURCE_BACKGROUND_MODEL
    background%surface_temperature%value=280.0_real32
    background%surface_temperature%valid=.TRUE.
    background%surface_temperature%quality=0_int32
    background%surface_temperature%source=SOURCE_BACKGROUND_MODEL
    background%surface_vapor%value=0.008_real32
    background%surface_vapor%valid=.TRUE.
    background%surface_vapor%quality=0_int32
    background%surface_vapor%source=SOURCE_BACKGROUND_MODEL
    background%surface_height%value=50.0_real32
    background%surface_height%valid=.TRUE.
    background%surface_height%quality=0_int32
    background%surface_height%source=SOURCE_BACKGROUND_MODEL
    CALL check(ALL(background%surface_pressure%value>background%pressure%value(:,:,1)), &
      'surface anchor pressure is above the first represented level',failures)
    CALL check(ALL(REAL(background%surface_height%value,real64)<= &
      REAL(background%geopotential%value(:,:,1),real64)/9.80665_real64), &
      'surface anchor terrain is below the first represented Phi',failures)
    CALL refresh_dry_air_mass_measure(background,status)
    CALL check(status==STATUS_OK,'surface-anchor fixture mass is canonical',failures)

    thermo_active=.FALSE.; thermo_active(3,2,1)=.TRUE.
    thermo_surface=SATURATION_LIQUID
    geopotential_support=.FALSE.; geopotential_support(3,2,:)=.TRUE.
    geopotential_reference_level=0
    geopotential_reference_level(3,2)=0
    longitude=0.0_real32
    residual_before=0.0_real64; residual_after=0.0_real64
    config%requested_mode=MODE_SHADOW
    config%maximum_outer_iterations=1
    config%horizontal_support_radius_m=10000.0_real64
    config%pressure_support_radius_pa=20000.0_real64
    CALL run_cloud_bal_pipeline(background,candidate,operational,result,config, &
      thermo_active,thermo_surface,0.8_real64,geopotential_support, &
      geopotential_reference_level)
    CALL check(result%status==STATUS_OK .AND. result%geopotential%status==STATUS_OK, &
      'surface-anchored coupled pipeline is accepted',failures)
    IF (result%status/=STATUS_OK .OR. result%geopotential%status/=STATUS_OK) RETURN
    CALL check(ABS(REAL(candidate%geopotential%value(3,2,1),real64)- &
      REAL(background%geopotential%value(3,2,1),real64))>0.0_real64, &
      'surface anchor changes the first represented-layer Phi',failures)
    CALL check(canonical_states_equal(background,operational), &
      'surface-anchored pipeline preserves operational identity',failures)
    CALL check(ALL(candidate%surface_pressure%value==background%surface_pressure%value) .AND. &
      ALL(candidate%surface_temperature%value==background%surface_temperature%value) .AND. &
      ALL(candidate%surface_vapor%value==background%surface_vapor%value) .AND. &
      ALL(candidate%surface_height%value==background%surface_height%value), &
      'surface anchor preserves the supplied surface fields',failures)

    CALL build_balance_operator(candidate,config%balance,op,status,reason)
    CALL check(status==STATUS_OK,'surface-anchor diagnostic operator builds',failures)
    IF (status==STATUS_OK) THEN
      CALL state_continuity_residual(op,background,residual_before,status)
      CALL check(status==STATUS_OK,'surface-anchor background residual builds',failures)
      CALL state_continuity_residual(op,candidate,residual_after,status)
      CALL check(status==STATUS_OK,'surface-anchor candidate residual builds',failures)
    END IF

    CALL remove_if_present(path)
    CALL write_shadow_diagnostics(path,background,candidate,longitude,result,config, &
      residual_before,residual_after,status,operational,.TRUE.)
    INQUIRE(FILE=path,EXIST=exists)
    CALL check(status==STATUS_OK .AND. exists, &
      'surface-anchored geopotential artifact is serialized',failures)
    IF (.NOT.exists .OR. status/=STATUS_OK) RETURN

    ! Keep the artifact self-describing for the independent Python replay.
    rc=nf90_open(path,NF90_NOWRITE,ncid)
    CALL check(rc==NF90_NOERR,'surface-anchor artifact opens for readback',failures)
    IF (rc/=NF90_NOERR) RETURN
    contract=''
    rc=nf90_get_att(ncid,NF90_GLOBAL,'pressure_geopotential_contract',contract)
    CALL check(rc==NF90_NOERR .AND. TRIM(contract)== &
      'pressure_hydrostatic_surface_increment_v1', &
      'surface-anchor contract metadata is exact',failures)
    reference=''
    rc=nf90_get_att(ncid,NF90_GLOBAL,'pressure_geopotential_reference',reference)
    CALL check(rc==NF90_NOERR .AND. TRIM(reference)=='fixed_terrain_surface', &
      'surface-anchor reference metadata is exact',failures)
    condensate=''
    rc=nf90_get_att(ncid,NF90_GLOBAL, &
      'pressure_geopotential_surface_condensate_convention',condensate)
    CALL check(rc==NF90_NOERR .AND. TRIM(condensate)=='WPS_SURFACE_ZERO_CONDENSATE', &
      'surface-anchor condensate convention is explicit',failures)
    rc=nf90_close(ncid)
    CALL check(rc==NF90_NOERR,'surface-anchor artifact closes after readback',failures)
  END SUBROUTINE test_surface_anchored_geopotential_shadow

  SUBROUTINE test_pressure_dispatch_request_scope(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: original,candidate,operational
    TYPE(cloud_bal_pipeline_result) :: result
    TYPE(cloud_bal_pipeline_config) :: config
    REAL(real64) :: request(2,2)
    INTEGER :: status

    CALL make_state(original)
    request=100001.0_real64
    CALL run_pressure_analysis_shadow(original,candidate,operational,result,config, &
      'LIQUID_RADAR_RH1_SURFACE_PHI',status,requested_surface_pressure=request)
    CALL check(status==STATUS_FAILED .AND. result%reason_code==REASON_AUTHORITY .AND. &
      canonical_states_equal(original,candidate) .AND. canonical_states_equal(original,operational), &
      'dispatcher refuses pressure request in the implicit outer loop',failures)
    CALL run_pressure_analysis_shadow(original,candidate,operational,result,config, &
      'LIQUID_RADAR_RH1_SURFACE_PHI',status,requested_surface_pressure=request,single_pass=.FALSE.)
    CALL check(status==STATUS_FAILED .AND. result%reason_code==REASON_AUTHORITY, &
      'dispatcher refuses explicit multi-step pressure request',failures)
    CALL run_pressure_analysis_shadow(original,candidate,operational,result,config, &
      'HYDRO',status,requested_surface_pressure=request,single_pass=.TRUE.)
    CALL check(status==STATUS_FAILED .AND. result%reason_code==REASON_AUTHORITY, &
      'dispatcher refuses pressure request without surface anchoring',failures)
    CALL run_pressure_analysis_shadow(original,candidate,operational,result,config, &
      'OFF',status,requested_surface_pressure=request,single_pass=.TRUE.)
    CALL check(status==STATUS_OK .AND. canonical_states_equal(original,candidate) .AND. &
      canonical_states_equal(original,operational) .AND. .NOT.ALLOCATED(result%requested_surface_pressure), &
      'dispatcher OFF ignores an unused pressure request and preserves the original',failures)
  END SUBROUTINE test_pressure_dispatch_request_scope

  SUBROUTINE test_prescribed_surface_pressure_writer(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: background,candidate,operational,bad_candidate
    TYPE(cloud_bal_pipeline_config) :: config
    TYPE(cloud_bal_pipeline_result) :: result,bad_result
    TYPE(balance_operator_type) :: op
    LOGICAL :: thermo_active(4,4,3),geopotential_support(4,4,3),exists
    INTEGER :: thermo_surface(4,4,3),reference_level(4,4)
    INTEGER :: status,reason,ncid,varid,xtype,rc,k,natts,att
    LOGICAL :: geometry_ledger_present
    REAL(real32) :: longitude(4,4)
    REAL(real64) :: residual_before(4,4,3),residual_after(4,4,3)
    REAL(real64) :: requested_surface_pressure(4,4)
    REAL(real64) :: requested_read(4,4)
    REAL(real64) :: candidate_interface(4,4,4),candidate_cell_dp(4,4,3)
    REAL(real64) :: candidate_pressure_mass(4,4,3),candidate_dry_mass(4,4,3)
    CHARACTER(LEN=128) :: contract,attribute_name
    CHARACTER(LEN=*), PARAMETER :: path='variable-pressure-shadow.nc'

    ! Reuse the accepted coupled thermo/Phi fixture, but make the geometry
    ! request explicit.  Every column has full support and a zero reference
    ! level, so this is the prescribed fixed-terrain surface-pressure path.
    ! Middle-level targets include the changed bottom cell in balance support.
    CALL make_pressure_target_case(background,15000.0_real32,2)
    background%omega%value(2,2,1)=0.01_real32
    background%omega_target%value(4,2,2)=-background%omega_target%value(2,2,2)
    background%omega_target%valid(4,2,2)=.TRUE.
    background%omega_target%quality(4,2,2)=0_int32
    background%omega_target%source(4,2,2)=background%omega_target%source(2,2,2)
    background%omega_target_sigma%value(4,2,2)=background%omega_target_sigma%value(2,2,2)
    background%omega_target_sigma%valid(4,2,2)=.TRUE.
    background%omega_target_sigma%quality(4,2,2)=0_int32
    background%omega_target_sigma%source(4,2,2)=background%omega_target_sigma%source(2,2,2)
    ! This amount exercises nonzero total-water float32 storage roundoff.
    background%cloud_water%value(3,2,1)=0.00201500021_real32
    background%cloud_water%value(2,2,1)=0.00201500021_real32
    background%cloud_water%value(2,2,2)=0.00201500021_real32
    DO k=1,3
      background%geopotential%value(:,:,k)=1000.0_real32+ &
        500.0_real32*REAL(k-1,real32)
    END DO
    CALL mark_valid(background%geopotential,SOURCE_BACKGROUND_MODEL)
    background%surface_pressure%value=100000.0_real32
    background%surface_pressure%valid=.TRUE.
    background%surface_pressure%quality=0_int32
    background%surface_pressure%source=SOURCE_BACKGROUND_MODEL
    background%surface_temperature%value=280.0_real32
    background%surface_temperature%valid=.TRUE.
    background%surface_temperature%quality=0_int32
    background%surface_temperature%source=SOURCE_BACKGROUND_MODEL
    background%surface_vapor%value=0.008_real32
    background%surface_vapor%valid=.TRUE.
    background%surface_vapor%quality=0_int32
    background%surface_vapor%source=SOURCE_BACKGROUND_MODEL
    background%surface_height%value=50.0_real32
    background%surface_height%valid=.TRUE.
    background%surface_height%quality=0_int32
    background%surface_height%source=SOURCE_BACKGROUND_MODEL
    CALL refresh_dry_air_mass_measure(background,status)
    CALL check(status==STATUS_OK,'prescribed-PS fixture mass is canonical',failures)

    thermo_active=.FALSE.; thermo_active(3,2,1)=.TRUE.; thermo_active(2,2,1)=.TRUE.
    ! PS changes only bottom-cell dp, but refreshes dry mass in the entire
    ! column, including this upper cell's rounded thermo composition.
    thermo_active(2,2,2)=.TRUE.
    thermo_surface=SATURATION_LIQUID
    geopotential_support=.TRUE.
    reference_level=0
    requested_surface_pressure=REAL(background%surface_pressure%value,real64)
    requested_surface_pressure(2,2)=requested_surface_pressure(2,2)+20.003_real64
    requested_surface_pressure(1,4)=requested_surface_pressure(1,4)+10.001_real64
    longitude=0.0_real32
    config%requested_mode=MODE_SHADOW
    config%maximum_outer_iterations=1
    config%horizontal_support_radius_m=10000.0_real64
    config%pressure_support_radius_pa=20000.0_real64
    CALL run_cloud_bal_pipeline(background,candidate,operational,result,config, &
      thermo_active,thermo_surface,0.8_real64,geopotential_support,reference_level, &
      requested_surface_pressure)
    CALL check(result%status==STATUS_OK .AND. result%geopotential%status==STATUS_OK .AND. &
      ALLOCATED(result%requested_surface_pressure) .AND. &
      ALL(candidate%surface_pressure%value==REAL(requested_surface_pressure,real32)) .AND. &
      ANY(candidate%surface_pressure%value/=background%surface_pressure%value) .AND. &
      ALL(candidate%pressure%value==background%pressure%value) .AND. &
      ALL(candidate%grid%pressure_interface(:,:,4)==background%grid%pressure_interface(:,:,4)), &
      'single-pass localized fractional-Pa pressure requests are accepted',failures)
    IF (result%status/=STATUS_OK .OR. .NOT.ALLOCATED(result%requested_surface_pressure)) RETURN
    CALL check(canonical_states_equal(background,operational), &
      'prescribed-pressure pipeline preserves operational identity',failures)
    CALL check(result%geometry_budget%accounted_cells>0_int64 .AND. &
      result%geometry_budget%geometry_mass_change_kg>0.0_real64, &
      'prescribed-pressure geometry ledger records a nonzero mass change',failures)

    CALL build_balance_operator(candidate,config%balance,op,status,reason)
    CALL check(status==STATUS_OK,'prescribed-pressure diagnostic operator builds',failures)
    IF (status/=STATUS_OK) RETURN
    CALL state_continuity_residual(op,background,residual_before,status)
    CALL check(status==STATUS_OK,'prescribed-pressure background residual builds',failures)
    CALL state_continuity_residual(op,candidate,residual_after,status)
    CALL check(status==STATUS_OK,'prescribed-pressure candidate residual builds',failures)
    CALL check(ANY(ABS(residual_before-residual_after)>0.0_real64), &
      'prescribed-pressure candidate carries a nonzero balance delta',failures)

    CALL remove_if_present(path)
    CALL write_shadow_diagnostics(path,background,candidate,longitude,result,config, &
      residual_before,residual_after,status,operational,.TRUE.)
    INQUIRE(FILE=path,EXIST=exists)
    CALL check(status==STATUS_OK .AND. exists, &
      'prescribed-pressure writer emits variable-pressure-shadow.nc',failures)
    IF (.NOT.exists .OR. status/=STATUS_OK) RETURN

    rc=nf90_open(path,NF90_NOWRITE,ncid)
    CALL check(rc==NF90_NOERR,'prescribed-pressure artifact opens for readback',failures)
    IF (rc/=NF90_NOERR) RETURN
    contract=''
    rc=nf90_get_att(ncid,NF90_GLOBAL,'pressure_geometry_contract',contract)
    CALL check(rc==NF90_NOERR .AND. TRIM(contract)== &
      'prescribed_surface_pressure_v1', &
      'prescribed-pressure geometry contract metadata is exact',failures)
    rc=nf90_inq_varid(ncid,'requested_surface_pressure',varid)
    IF (rc==NF90_NOERR) THEN
      rc=nf90_inquire_variable(ncid,varid,xtype=xtype)
      CALL check(rc==NF90_NOERR .AND. xtype==NF90_DOUBLE, &
        'prescribed-pressure request is stored as f64',failures)
      rc=nf90_get_var(ncid,varid,requested_read)
    END IF
    CALL check(rc==NF90_NOERR .AND. ALL(requested_read==requested_surface_pressure), &
      'prescribed-pressure request is stored exactly',failures)
    rc=nf90_inq_varid(ncid,'candidate_pressure_interface',varid)
    IF (rc==NF90_NOERR) rc=nf90_get_var(ncid,varid,candidate_interface)
    CALL check(rc==NF90_NOERR .AND. ALL(candidate_interface==candidate%grid%pressure_interface), &
      'candidate pressure interfaces are stored exactly',failures)
    rc=nf90_inq_varid(ncid,'candidate_cell_dp',varid)
    IF (rc==NF90_NOERR) rc=nf90_get_var(ncid,varid,candidate_cell_dp)
    CALL check(rc==NF90_NOERR .AND. ALL(candidate_cell_dp==candidate%grid%cell_dp), &
      'candidate cell pressure thickness is stored exactly',failures)
    rc=nf90_inq_varid(ncid,'candidate_pressure_mass_measure',varid)
    IF (rc==NF90_NOERR) rc=nf90_get_var(ncid,varid,candidate_pressure_mass)
    CALL check(rc==NF90_NOERR .AND. ALL(candidate_pressure_mass== &
      candidate%grid%pressure_mass_measure), &
      'candidate pressure mass measure is stored exactly',failures)
    rc=nf90_inq_varid(ncid,'candidate_dry_air_mass_measure',varid)
    IF (rc==NF90_NOERR) rc=nf90_get_var(ncid,varid,candidate_dry_mass)
    CALL check(rc==NF90_NOERR .AND. ALL(candidate_dry_mass== &
      candidate%grid%dry_air_mass_measure), &
      'candidate dry-air mass measure is stored exactly',failures)
    geometry_ledger_present=.FALSE.
    rc=nf90_inquire(ncid,nAttributes=natts)
    IF (rc==NF90_NOERR) THEN
      DO att=1,natts
        attribute_name=''
        rc=nf90_inq_attname(ncid,NF90_GLOBAL,att,attribute_name)
        IF (rc==NF90_NOERR .AND. INDEX(TRIM(attribute_name),'geometry_analysis_')==1) &
          geometry_ledger_present=.TRUE.
      END DO
    END IF
    CALL check(geometry_ledger_present,'full geometry analysis ledger is serialized',failures)
    rc=nf90_close(ncid)
    CALL check(rc==NF90_NOERR,'prescribed-pressure artifact closes after readback',failures)

    CALL write_transition_state_replay_probe(background,candidate,longitude,result,config, &
      residual_before,residual_after,failures)

    ! Each mutation must fail before the NOCLOBBER create call.  These cover
    ! stale candidate metrics, a changed mass ledger, a changed request receipt,
    ! and removal of the explicit full-surface authorization.
    bad_candidate=candidate
    bad_candidate%grid%pressure_interface(1,1,1)= &
      bad_candidate%grid%pressure_interface(1,1,1)+1.0_real64
    CALL expect_variable_pressure_rejection(path,background,bad_candidate,operational, &
      result,config,longitude,residual_before,residual_after,failures, &
      'stale candidate pressure geometry')

    bad_result=result
    bad_result%geometry_budget%geometry_mass_change_kg= &
      bad_result%geometry_budget%geometry_mass_change_kg+1.0_real64
    CALL expect_variable_pressure_rejection(path,background,candidate,operational, &
      bad_result,config,longitude,residual_before,residual_after,failures, &
      'changed geometry analysis ledger')

    bad_result=result
    bad_result%requested_surface_pressure(1,1)= &
      bad_result%requested_surface_pressure(1,1)+1.0_real64
    CALL expect_variable_pressure_rejection(path,background,candidate,operational, &
      bad_result,config,longitude,residual_before,residual_after,failures, &
      'request receipt differs from candidate geometry')

    bad_result=result
    DEALLOCATE(bad_result%geopotential_support)
    DEALLOCATE(bad_result%geopotential_reference_level)
    CALL expect_variable_pressure_rejection(path,background,candidate,operational, &
      bad_result,config,longitude,residual_before,residual_after,failures, &
      'missing full-surface pressure geometry authorization')
  END SUBROUTINE test_prescribed_surface_pressure_writer

  SUBROUTINE write_transition_state_replay_probe(background,candidate,longitude,result,config, &
                                                 residual_before,residual_after,failures)
    TYPE(cloud_bal_state_type), INTENT(IN) :: background,candidate
    REAL(real32), INTENT(IN) :: longitude(:,:)
    TYPE(cloud_bal_pipeline_result), INTENT(IN) :: result
    TYPE(cloud_bal_pipeline_config), INTENT(IN) :: config
    REAL(real64), INTENT(IN) :: residual_before(:,:,:),residual_after(:,:,:)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_pipeline_result) :: probe_result
    INTEGER :: ncid,xdim,ydim,zdim,rc,status
    LOGICAL :: exists,ok
    CHARACTER(LEN=*), PARAMETER :: path='transition-state-replay-probe.nc'

    CALL remove_if_present(path)
    ! Write the ordinary candidate first.  The transition/radar payloads are
    ! appended below solely for numerical replay instrumentation; production
    ! writer validation still sees the original result without a seed.
    CALL write_shadow_diagnostics(path,background,candidate,longitude,result,config, &
      residual_before,residual_after,status,background,.TRUE.)
    INQUIRE(FILE=path,EXIST=exists)
    CALL check(status==STATUS_OK .AND. exists, &
      'transition replay probe ordinary artifact writes',failures)
    IF (.NOT.exists .OR. status/=STATUS_OK) RETURN

    probe_result=result
    ALLOCATE(probe_result%pressure_transition_seed)
    probe_result%pressure_transition_seed=candidate

    rc=nf90_open(path,NF90_WRITE,ncid)
    CALL check(rc==NF90_NOERR,'transition replay probe reopens for append',failures)
    IF (rc/=NF90_NOERR) RETURN
    rc=nf90_inq_dimid(ncid,'x',xdim)
    IF (rc==NF90_NOERR) rc=nf90_inq_dimid(ncid,'y',ydim)
    IF (rc==NF90_NOERR) rc=nf90_inq_dimid(ncid,'z',zdim)
    CALL check(rc==NF90_NOERR,'transition replay probe reuses dimensions',failures)
    IF (rc/=NF90_NOERR) THEN
      rc=nf90_close(ncid)
      RETURN
    END IF
    ok=put_pressure_transition_extension(ncid,(/xdim,ydim/),(/xdim,ydim,zdim/), &
      background,candidate,probe_result)
    CALL check(ok,'transition replay probe appends same-domain seed',failures)
    IF (ok) ok=put_radar_reconstruction_inputs(ncid,(/xdim,ydim,zdim/),background,config)
    CALL check(ok,'transition replay probe appends radar reconstruction inputs',failures)
    rc=nf90_redef(ncid)
    IF (rc==NF90_NOERR) rc=nf90_put_att(ncid,NF90_GLOBAL,'numerical_test_probe',1_int32)
    IF (rc==NF90_NOERR) rc=nf90_enddef(ncid)
    CALL check(rc==NF90_NOERR,'transition replay probe marks test artifact',failures)
    rc=nf90_close(ncid)
    CALL check(rc==NF90_NOERR,'transition replay probe closes after append',failures)
  END SUBROUTINE write_transition_state_replay_probe

  SUBROUTINE expect_variable_pressure_rejection(path,background,candidate,operational, &
                                                result,config,longitude,residual_before, &
                                                residual_after,failures,label)
    CHARACTER(LEN=*), INTENT(IN) :: path,label
    TYPE(cloud_bal_state_type), INTENT(IN) :: background,candidate,operational
    TYPE(cloud_bal_pipeline_result), INTENT(IN) :: result
    TYPE(cloud_bal_pipeline_config), INTENT(IN) :: config
    REAL(real32), INTENT(IN) :: longitude(:,:)
    REAL(real64), INTENT(IN) :: residual_before(:,:,:),residual_after(:,:,:)
    INTEGER, INTENT(INOUT) :: failures
    INTEGER :: status
    LOGICAL :: exists
    CHARACTER(LEN=:), ALLOCATABLE :: rejected_path

    rejected_path=TRIM(path)//'.rejected'
    CALL remove_if_present(rejected_path)
    CALL write_shadow_diagnostics(rejected_path,background,candidate,longitude,result,config, &
      residual_before,residual_after,status,operational,.TRUE.)
    INQUIRE(FILE=rejected_path,EXIST=exists)
    CALL check(status==STATUS_FAILED .AND. .NOT.exists, &
      TRIM(label)//' is rejected before file creation',failures)
  END SUBROUTINE expect_variable_pressure_rejection

  SUBROUTINE remove_if_present(path)
    CHARACTER(LEN=*), INTENT(IN) :: path
    LOGICAL :: exists
    INTEGER :: unit
    INQUIRE(FILE=path,EXIST=exists)
    IF (.NOT.exists) RETURN
    OPEN(NEWUNIT=unit,FILE=path,STATUS='OLD',ACTION='READWRITE')
    CLOSE(unit,STATUS='DELETE')
  END SUBROUTINE remove_if_present

  SUBROUTINE make_pressure_target_case(state,spacing,target_level)
    TYPE(cloud_bal_state_type), INTENT(OUT) :: state
    REAL(real32), INTENT(IN) :: spacing
    INTEGER, INTENT(IN) :: target_level
    INTEGER :: k,status
    CALL make_state(state,4,4,3)
    DO k=1,3
      state%pressure%value(:,:,k)=95000.0_real32-spacing*REAL(k-1,real32)
    END DO
    state%geopotential%value=1000.0_real32
    CALL mark_valid(state%geopotential,SOURCE_BACKGROUND_MODEL)
    state%latitude%value=36.0_real32
    state%latitude%valid=.TRUE.
    state%latitude%quality=0_int32
    state%latitude%source=SOURCE_BACKGROUND_MODEL
    state%omega_top_boundary%quality=0_int32
    state%omega_bottom_boundary%quality=0_int32
    state%omega_top_boundary%source=SOURCE_BOUNDARY_CONDITION
    state%omega_bottom_boundary%source=SOURCE_BOUNDARY_CONDITION
    CALL configure_pressure_geometry(state,status)
    IF (status/=STATUS_OK) ERROR STOP 'pressure candidate geometry'
    CALL refresh_dry_air_mass_measure(state,status)
    IF (status/=STATUS_OK) ERROR STOP 'pressure candidate mass'
    state%omega_target%value(2,2,target_level)=0.08_real32
    state%omega_target%valid(2,2,target_level)=.TRUE.
    state%omega_target%quality(2,2,target_level)=0_int32
    state%omega_target%source(2,2,target_level)=IOR(SOURCE_CONVENTIONAL_OBS,SOURCE_DYNAMIC_TARGET)
    state%omega_target_sigma%value(2,2,target_level)=0.5_real32
    state%omega_target_sigma%valid(2,2,target_level)=.TRUE.
    state%omega_target_sigma%quality(2,2,target_level)=0_int32
    state%omega_target_sigma%source(2,2,target_level)=state%omega_target%source(2,2,target_level)
    state%radar_reflectivity%value(2,2,target_level)=30.0_real32
    state%radar_reflectivity%valid(2,2,target_level)=.TRUE.
    state%radar_reflectivity%quality(2,2,target_level)=0_int32
    state%radar_reflectivity%source(2,2,target_level)=SOURCE_RADAR_DBZ
  END SUBROUTINE make_pressure_target_case

  SUBROUTINE test_sigma_weighted_pipeline_shadow(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: background,candidate,operational
    TYPE(cloud_bal_state_type) :: write_background,write_candidate,write_operational
    TYPE(cloud_bal_pipeline_config) :: sigma_config
    TYPE(cloud_bal_pipeline_result) :: sigma_result
    REAL(real32) :: sigma_longitude(4,4),sigma_read(4,4,2)
    REAL(real64) :: sigma_residual(4,4,2)
    INTEGER(int32) :: sigma_valid(4,4,2),sigma_quality(4,4,2),sigma_source(4,4,2)
    LOGICAL :: thermo_active(4,4,2)
    INTEGER(int32) :: thermo_surface(4,4,2)
    INTEGER :: status,reason,ncid,varid,rc
    REAL(real32), PARAMETER :: target_sigma=1.0e6_real32
    REAL(real32), PARAMETER :: target_omega=0.08_real32

    ! This synthetic bounded fixture runs with physical boundaries.  Its very
    ! large finite sigma exercises the accepted weighted no-op while retaining
    ! nonzero localization support.
    CALL make_state(background,4,4)
    background%geopotential%value=0.0_real32
    background%geopotential%valid=.TRUE.
    background%geopotential%quality=0_int32
    background%geopotential%source=SOURCE_BACKGROUND_MODEL
    background%latitude%value=35.0_real32
    background%latitude%valid=.TRUE.
    background%latitude%quality=0_int32
    background%latitude%source=SOURCE_BACKGROUND_MODEL
    background%omega_target%value(2,2,1)=target_omega
    background%omega_target%valid(2,2,1)=.TRUE.
    background%omega_target%quality(2,2,1)=0_int32
    background%omega_target%source(2,2,1)=IOR(SOURCE_ANALYZED_WIND, &
                                              SOURCE_DYNAMIC_TARGET)
    background%omega_target_sigma%value(2,2,1)=target_sigma
    background%omega_target_sigma%valid(2,2,1)=.TRUE.
    background%omega_target_sigma%quality(2,2,1)=0_int32
    background%omega_target_sigma%source(2,2,1)=background%omega_target%source(2,2,1)
    background%omega_top_boundary%quality=0_int32
    background%omega_bottom_boundary%quality=0_int32
    background%omega_top_boundary%source=SOURCE_BOUNDARY_CONDITION
    background%omega_bottom_boundary%source=SOURCE_BOUNDARY_CONDITION
    sigma_config%requested_mode=MODE_SHADOW
    sigma_config%horizontal_support_radius_m=10000.0_real64
    sigma_config%pressure_support_radius_pa=30000.0_real64
    CALL run_cloud_bal_pipeline(background,candidate,operational,sigma_result, &
      sigma_config)
    CALL check(sigma_result%status==STATUS_OK .AND. &
      sigma_result%balance%status==STATUS_OK, &
      'sigma-weighted physical-boundary pipeline is accepted',failures)
    CALL check(ANY(candidate%balance_beta>0.0_real64), &
      'sigma-weighted no-op retains nonzero localization support',failures)
    CALL check(ALL(candidate%u%value==background%u%value) .AND. &
      ALL(candidate%v%value==background%v%value) .AND. &
      ALL(candidate%omega%value==background%omega%value), &
      'huge sigma produces a numerical no-op',failures)
    CALL check(ALL(candidate%omega_target_sigma%value== &
                   background%omega_target_sigma%value) .AND. &
      ALL(candidate%omega_target_sigma%valid .EQV. &
          background%omega_target_sigma%valid), &
      'pipeline preserves the explicit synthetic uncertainty',failures)

    ! Physical-boundary publication is not yet supported by this diagnostic
    ! writer.  Do not relabel a completed run to bypass that restriction.
    CALL validate_shadow_write_contract(background,candidate,operational, &
      sigma_result,sigma_config,status,reason)
    CALL check(status==STATUS_FAILED .AND. reason==REASON_METADATA, &
      'physical-boundary candidate remains unsupported by diagnostic writer',failures)

    ! Separate no-target run: copied boundaries and unused target uncertainty
    ! travel unchanged through the small-grid schema-7 diagnostic path.
    write_background=background
    write_background%omega_target%value=write_background%omega%value
    write_background%omega_target%valid=.FALSE.
    write_background%omega_target%quality=0_int32
    write_background%omega_target%source=0_int32
    write_background%omega_top_boundary%quality=IOR(QUALITY_LEGACY_PROVENANCE, &
      QUALITY_BOUNDARY_INTERIOR_COPY)
    write_background%omega_bottom_boundary%quality=IOR(QUALITY_LEGACY_PROVENANCE, &
      QUALITY_BOUNDARY_INTERIOR_COPY)
    write_background%omega_top_boundary%source=SOURCE_ANALYZED_WIND
    write_background%omega_bottom_boundary%source=SOURCE_ANALYZED_WIND
    thermo_active=.FALSE.
    thermo_active(1,1,1)=.TRUE.
    thermo_surface=SATURATION_LIQUID
    write_background%vapor%value(1,1,1)=0.001_real32
    CALL refresh_dry_air_mass_measure(write_background,status)
    CALL check(status==STATUS_OK,'sigma serialization fixture mass is canonical',failures)
    sigma_config%pressure_support_radius_pa=20000.0_real64
    CALL run_cloud_bal_pipeline(write_background,write_candidate,write_operational, &
      sigma_result,sigma_config,thermo_active,thermo_surface,0.8_real64)
    CALL check(sigma_result%status==STATUS_OK, &
      'zero-innovation sigma pipeline is accepted with diagnostic boundaries',failures)
    sigma_longitude=0.0_real32
    sigma_residual=0.0_real64
    CALL validate_shadow_write_contract(write_background,write_candidate, &
      write_operational,sigma_result,sigma_config,status,reason)
    CALL check(status==STATUS_OK .AND. reason==REASON_NONE, &
      'zero-innovation sigma result satisfies SHADOW authority',failures)
    CALL write_shadow_diagnostics('sigma-noop-shadow.nc',write_background, &
      write_candidate,sigma_longitude,sigma_result,sigma_config,sigma_residual, &
      sigma_residual,status,write_operational)
    CALL check(status==STATUS_OK,'sigma-weighted shadow artifact is writable',failures)
    IF (status/=STATUS_OK) RETURN
    rc=nf90_open('sigma-noop-shadow.nc',NF90_NOWRITE,ncid)
    CALL check(rc==NF90_NOERR,'sigma-weighted shadow artifact opens',failures)
    IF (rc/=NF90_NOERR) RETURN
    rc=nf90_inq_varid(ncid,'omega_target_sigma',varid)
    IF (rc==NF90_NOERR) rc=nf90_get_var(ncid,varid,sigma_read)
    CALL check(rc==NF90_NOERR .AND. ALL(sigma_read== &
      write_candidate%omega_target_sigma%value), &
      'synthetic uncertainty values persist in shadow artifact',failures)
    rc=nf90_inq_varid(ncid,'omega_target_sigma_valid',varid)
    IF (rc==NF90_NOERR) rc=nf90_get_var(ncid,varid,sigma_valid)
    CALL check(rc==NF90_NOERR .AND. ALL(sigma_valid==MERGE(1_int32,0_int32, &
      write_candidate%omega_target_sigma%valid)), &
      'synthetic uncertainty validity persists in shadow artifact',failures)
    rc=nf90_inq_varid(ncid,'omega_target_sigma_quality',varid)
    IF (rc==NF90_NOERR) rc=nf90_get_var(ncid,varid,sigma_quality)
    CALL check(rc==NF90_NOERR .AND. ALL(sigma_quality== &
      write_candidate%omega_target_sigma%quality), &
      'synthetic uncertainty quality persists in shadow artifact',failures)
    rc=nf90_inq_varid(ncid,'omega_target_sigma_source',varid)
    IF (rc==NF90_NOERR) rc=nf90_get_var(ncid,varid,sigma_source)
    CALL check(rc==NF90_NOERR .AND. ALL(sigma_source== &
      write_candidate%omega_target_sigma%source), &
      'synthetic uncertainty provenance persists in shadow artifact',failures)
    rc=nf90_close(ncid)
  END SUBROUTINE test_sigma_weighted_pipeline_shadow

  SUBROUTINE test_thermo_shadow_io(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: background,candidate,operational
    TYPE(cloud_bal_state_type) :: bad_candidate,bad_operational,noecho, &
      noecho_candidate,noecho_operational
    TYPE(cloud_bal_state_type) :: outer_candidate,outer_operational
    TYPE(cloud_bal_pipeline_config) :: thermo_config
    TYPE(cloud_bal_pipeline_config) :: outer_config
    TYPE(cloud_bal_pipeline_result) :: thermo_result,outer_result,bad_result
    LOGICAL :: active(4,4,2)
    INTEGER :: surface(4,4,2),status,reason,ncid,varid,rc,schema,mutation
    INTEGER :: outer_cap_attr,outer_count_attr,outer_converged_attr
    INTEGER(int64) :: analysis_count
    INTEGER(int32) :: support(4,4,2),surface_read(4,4,2),expected_support(4,4,2)
    INTEGER(int32) :: authority(4,4,2),balance_support(4,4,2)
    REAL(real32) :: values(4,4,2),thermo_longitude(4,4)
    REAL(real64) :: mass(4,4,2),species(6),scalar,thermo_residual(4,4,2)
    REAL(real64), ALLOCATABLE :: outer_history(:)
    REAL(real64) :: analysis_species(6),analysis_mixing(6),analysis_dry_mass(6)
    REAL(real64) :: analysis_scalar
    CHARACTER(LEN=256) :: analysis_contract,outer_contract,outer_config_id
    CHARACTER(LEN=256) :: outer_extensions,outer_fields,outer_units
    CALL make_state(background,4,4)
    background%cloud_water%value(1,1,1)=0.002_real32
    background%rain%value(2,2,2)=1.0e-4_real32
    background%temperature%value(4,4,1)=263.0_real32
    background%vapor%value(4,4,1)=0.001_real32
    background%cloud_ice%value(4,4,1)=0.0005_real32
    background%snow%value(4,4,1)=1.0e-4_real32
    background%graupel%value(4,4,1)=2.0e-4_real32
    background%radar_reflectivity%value(1,1,1)=20.0_real32
    background%radar_reflectivity%valid(1,1,1)=.TRUE.
    background%radar_reflectivity%quality(1,1,1)=0_int32
    background%radar_reflectivity%source(1,1,1)=SOURCE_RADAR_DBZ
    CALL refresh_dry_air_mass_measure(background,status)
    CALL check(status==STATUS_OK,'thermo-shadow fixture mass is canonical',failures)
    active=.FALSE.; active(1,1,1)=.TRUE.; active(4,4,1)=.TRUE.
    surface=SATURATION_LIQUID; surface(4,4,1)=SATURATION_ICE
    thermo_longitude=0.0_real32; thermo_residual=0.0_real64
    thermo_config%requested_mode=MODE_SHADOW
    thermo_config%horizontal_support_radius_m=10000.0_real64
    thermo_config%pressure_support_radius_pa=20000.0_real64
    CALL run_cloud_bal_pipeline(background,candidate,operational,thermo_result, &
      thermo_config,active,surface,0.8_real64)
    CALL check(thermo_result%status==STATUS_OK .AND. &
      ALLOCATED(thermo_result%thermo_support) .AND. &
      ALLOCATED(thermo_result%thermo_surface), &
      'accepted thermo request reaches SHADOW result',failures)
    CALL check(ANY(candidate%grid%dry_air_mass_measure/= &
      background%grid%dry_air_mass_measure), &
      'radar precipitation changes candidate dry-air mass',failures)
    CALL write_shadow_diagnostics('thermo-shadow.nc',background,candidate, &
      thermo_longitude,thermo_result,thermo_config,thermo_residual, &
      thermo_residual,status,operational)
    CALL check(status==STATUS_OK,'schema-7 thermo shadow is writable',failures)
    rc=nf90_open('thermo-shadow.nc',NF90_NOWRITE,ncid)
    CALL check(rc==NF90_NOERR,'thermo shadow opens for direct inspection',failures)
    IF (rc==NF90_NOERR) THEN
      rc=nf90_get_att(ncid,NF90_GLOBAL,'diagnostic_schema_version',schema)
      CALL check(rc==NF90_NOERR .AND. schema==7,'thermo shadow has schema 7',failures)
      expected_support=MERGE(1_int32,0_int32,thermo_result%thermo_support)
      rc=nf90_inq_varid(ncid,'thermo_support',varid)
      IF (rc==NF90_NOERR) rc=nf90_get_var(ncid,varid,support)
      CALL check(rc==NF90_NOERR .AND. ALL(support==expected_support), &
        'thermo support is stored exactly',failures)
      rc=nf90_inq_varid(ncid,'thermo_surface',varid)
      IF (rc==NF90_NOERR) rc=nf90_get_var(ncid,varid,surface_read)
      CALL check(rc==NF90_NOERR .AND. ALL(surface_read==INT(surface,int32)), &
        'thermo surface is stored exactly',failures)
      rc=nf90_inq_varid(ncid,'candidate_dry_air_mass_measure',varid)
      IF (rc==NF90_NOERR) rc=nf90_get_var(ncid,varid,mass)
      CALL check(rc==NF90_NOERR .AND. ALL(mass==candidate%grid%dry_air_mass_measure), &
        'candidate dry-air mass is stored exactly',failures)
      rc=nf90_inq_varid(ncid,'background_temperature',varid)
      IF (rc==NF90_NOERR) rc=nf90_get_var(ncid,varid,values)
      CALL check(rc==NF90_NOERR .AND. ALL(values==background%temperature%value), &
        'background temperature is stored exactly',failures)
      rc=nf90_inq_varid(ncid,'candidate_temperature',varid)
      IF (rc==NF90_NOERR) rc=nf90_get_var(ncid,varid,values)
      CALL check(rc==NF90_NOERR .AND. ALL(values==candidate%temperature%value), &
        'candidate temperature is stored exactly',failures)
      rc=nf90_inq_varid(ncid,'background_vapor',varid)
      IF (rc==NF90_NOERR) rc=nf90_get_var(ncid,varid,values)
      CALL check(rc==NF90_NOERR .AND. ALL(values==background%vapor%value), &
        'background vapor is stored exactly',failures)
      rc=nf90_inq_varid(ncid,'candidate_vapor',varid)
      IF (rc==NF90_NOERR) rc=nf90_get_var(ncid,varid,values)
      CALL check(rc==NF90_NOERR .AND. ALL(values==candidate%vapor%value), &
        'candidate vapor is stored exactly',failures)
      rc=nf90_inq_varid(ncid,'candidate_cloud_water',varid)
      IF (rc==NF90_NOERR) rc=nf90_get_var(ncid,varid,values)
      CALL check(rc==NF90_NOERR .AND. ALL(values==candidate%cloud_water%value), &
        'candidate cloud liquid is stored exactly',failures)
      rc=nf90_get_att(ncid,NF90_GLOBAL,'thermo_species_change_kg',species)
      CALL check(rc==NF90_NOERR .AND. ALL(species==thermo_result%thermo_budget%species_change_kg), &
        'thermo species budget is stored exactly',failures)
      rc=nf90_get_att(ncid,NF90_GLOBAL,'thermo_sensible_change_j',scalar)
      CALL check(rc==NF90_NOERR .AND. scalar==thermo_result%thermo_budget%sensible_change_j, &
        'thermo sensible budget is stored exactly',failures)
      rc=nf90_get_att(ncid,NF90_GLOBAL,'thermo_phase_change_j',scalar)
      CALL check(rc==NF90_NOERR .AND. scalar==thermo_result%thermo_budget%phase_change_j, &
        'thermo phase budget is stored exactly',failures)
      rc=nf90_get_att(ncid,NF90_GLOBAL,'thermo_water_error_kg',scalar)
      CALL check(rc==NF90_NOERR .AND. scalar==thermo_result%thermo_budget%water_error_kg, &
        'water budget stored',failures)
      rc=nf90_get_att(ncid,NF90_GLOBAL,'thermo_enthalpy_error_j',scalar)
      CALL check(rc==NF90_NOERR .AND. scalar==thermo_result%thermo_budget%enthalpy_error_j, &
        'enthalpy budget stored',failures)
      rc=nf90_get_att(ncid,NF90_GLOBAL,'analysis_contract',analysis_contract)
      CALL check(rc==NF90_NOERR .AND. TRIM(analysis_contract)== &
        'pressure_fixed_represented_mixture_v1', &
        'analysis budget contract is stored exactly',failures)
      rc=nf90_get_att(ncid,NF90_GLOBAL,'analysis_species_change_kg',analysis_species)
      CALL check(rc==NF90_NOERR .AND. ALL(analysis_species== &
        thermo_result%analysis_budget%species_change_kg), &
        'analysis species budget is stored exactly',failures)
      rc=nf90_get_att(ncid,NF90_GLOBAL,'analysis_mixing_ratio_change_kg',analysis_mixing)
      CALL check(rc==NF90_NOERR .AND. ALL(analysis_mixing== &
        thermo_result%analysis_budget%mixing_ratio_change_kg), &
        'analysis mixing-ratio budget is stored exactly',failures)
      rc=nf90_get_att(ncid,NF90_GLOBAL,'analysis_dry_mass_redistribution_kg',analysis_dry_mass)
      CALL check(rc==NF90_NOERR .AND. ALL(analysis_dry_mass== &
        thermo_result%analysis_budget%dry_mass_redistribution_kg), &
        'analysis dry-mass redistribution budget is stored exactly',failures)
      rc=nf90_get_att(ncid,NF90_GLOBAL,'analysis_dry_air_change_kg',analysis_scalar)
      CALL check(rc==NF90_NOERR .AND. analysis_scalar== &
        thermo_result%analysis_budget%dry_air_change_kg, &
        'analysis dry-air budget is stored exactly',failures)
      rc=nf90_get_att(ncid,NF90_GLOBAL,'analysis_enthalpy_change_j',analysis_scalar)
      CALL check(rc==NF90_NOERR .AND. analysis_scalar== &
        thermo_result%analysis_budget%enthalpy_change_j, &
        'analysis enthalpy budget is stored exactly',failures)
      rc=nf90_get_att(ncid,NF90_GLOBAL,'analysis_total_mass_error_kg',analysis_scalar)
      CALL check(rc==NF90_NOERR .AND. analysis_scalar== &
        thermo_result%analysis_budget%total_mass_error_kg, &
        'analysis total-mass error is stored exactly',failures)
      rc=nf90_get_att(ncid,NF90_GLOBAL,'analysis_max_cell_mass_error_kg',analysis_scalar)
      CALL check(rc==NF90_NOERR .AND. analysis_scalar== &
        thermo_result%analysis_budget%max_cell_mass_error_kg, &
        'analysis maximum cell-mass error is stored exactly',failures)
      rc=nf90_get_att(ncid,NF90_GLOBAL,'analysis_accounted_cells',analysis_count)
      CALL check(rc==NF90_NOERR .AND. analysis_count== &
        thermo_result%analysis_budget%accounted_cells, &
        'analysis accounted-cell count is stored exactly',failures)
      rc=nf90_get_att(ncid,NF90_GLOBAL,'analysis_incomplete_background_cells',analysis_count)
      CALL check(rc==NF90_NOERR .AND. analysis_count== &
        thermo_result%analysis_budget%incomplete_background_cells, &
        'analysis incomplete-background count is stored exactly',failures)
      rc=nf90_get_att(ncid,NF90_GLOBAL,'analysis_incomplete_candidate_cells',analysis_count)
      CALL check(rc==NF90_NOERR .AND. analysis_count== &
        thermo_result%analysis_budget%incomplete_candidate_cells, &
        'analysis incomplete-candidate count is stored exactly',failures)
      rc=nf90_close(ncid)
    END IF

    ! A bounded accepted thermo run is the schema-8 publication path.  Keep
    ! the schema-7 artifact above as the legacy thermo contract fixture.
    outer_config=thermo_config
    outer_config%maximum_outer_iterations=16
    CALL run_cloud_bal_pipeline(background,outer_candidate,outer_operational, &
      outer_result,outer_config,active,surface,0.8_real64)
    CALL check(outer_result%status==STATUS_OK .AND. outer_result%outer_converged .AND. &
      outer_result%outer_iterations==3 .AND. &
      ANY(outer_result%outer_max_abs_delta(:,1)>0.0_real64) .AND. &
      ANY(outer_result%outer_max_abs_delta(:,2)>0.0_real64) .AND. &
      ALL(outer_result%outer_max_abs_delta(:,3)==0.0_real64) .AND. &
      ALL(outer_result%outer_max_abs_delta(:,4:32)==0.0_real64), &
      'bounded thermo fixture has three trials and a zero final residual',failures)
    CALL write_shadow_diagnostics('outer-thermo-shadow.nc',background,outer_candidate, &
      thermo_longitude,outer_result,outer_config,thermo_residual,thermo_residual, &
      status,outer_operational)
    CALL check(status==STATUS_OK,'schema-8 thermo shadow is writable',failures)
    rc=nf90_open('outer-thermo-shadow.nc',NF90_NOWRITE,ncid)
    CALL check(rc==NF90_NOERR,'schema-8 thermo shadow opens for direct inspection',failures)
    IF (rc==NF90_NOERR) THEN
      rc=nf90_get_att(ncid,NF90_GLOBAL,'diagnostic_schema_version',schema)
      CALL check(rc==NF90_NOERR .AND. schema==8,'outer thermo shadow has schema 8',failures)
      rc=nf90_get_att(ncid,NF90_GLOBAL,'contract',outer_contract)
      CALL check(rc==NF90_NOERR .AND. TRIM(outer_contract)== &
        'real_radar_thermo_shadow_v3','schema-8 contract is exact',failures)
      rc=nf90_get_att(ncid,NF90_GLOBAL,'configuration_id',outer_config_id)
      CALL check(rc==NF90_NOERR .AND. TRIM(outer_config_id)== &
        'pressure-thermo-shadow-v3','schema-8 configuration is exact',failures)
      rc=nf90_get_att(ncid,NF90_GLOBAL,'schema_extensions',outer_extensions)
      CALL check(rc==NF90_NOERR .AND. TRIM(outer_extensions)== &
        'verified_operational_identity_v1,radar_no_echo_masks_v1,'// &
        'pressure_geometry_v2,omega_boundary_contract_v2,pressure_thermo_v1,'// &
        'pressure_analysis_v1,pressure_outer_v1', &
        'schema-8 extensions are exact',failures)
      rc=nf90_get_att(ncid,NF90_GLOBAL,'outer_contract',outer_contract)
      CALL check(rc==NF90_NOERR .AND. TRIM(outer_contract)== &
        'pressure_fixed_feedback_producer_replay_v1', &
        'outer replay contract is exact',failures)
      rc=nf90_get_att(ncid,NF90_GLOBAL,'outer_maximum_iterations',outer_cap_attr)
      CALL check(rc==NF90_NOERR .AND. outer_cap_attr==16, &
        'outer cap attribute is exact',failures)
      rc=nf90_get_att(ncid,NF90_GLOBAL,'outer_iterations',outer_count_attr)
      CALL check(rc==NF90_NOERR .AND. outer_count_attr==outer_result%outer_iterations, &
        'outer count attribute is exact',failures)
      rc=nf90_get_att(ncid,NF90_GLOBAL,'outer_converged',outer_converged_attr)
      CALL check(rc==NF90_NOERR .AND. outer_converged_attr==1, &
        'outer convergence attribute is exact',failures)
      rc=nf90_get_att(ncid,NF90_GLOBAL,'outer_feedback_fields',outer_fields)
      CALL check(rc==NF90_NOERR .AND. TRIM(outer_fields)=='temperature,vapor,u,v,omega', &
        'outer feedback fields attribute is exact',failures)
      rc=nf90_get_att(ncid,NF90_GLOBAL,'outer_feedback_units',outer_units)
      CALL check(rc==NF90_NOERR .AND. TRIM(outer_units)== &
        'K,kg kg-1 dryair,m s-1,m s-1,Pa s-1', &
        'outer feedback units attribute is exact',failures)
      IF (rc==NF90_NOERR .AND. outer_count_attr>0 .AND. outer_count_attr<=32) THEN
        ALLOCATE(outer_history(5*outer_count_attr))
        rc=nf90_get_att(ncid,NF90_GLOBAL,'outer_max_abs_delta',outer_history)
        CALL check(rc==NF90_NOERR .AND. ALL(outer_history== &
          RESHAPE(outer_result%outer_max_abs_delta(:,1:outer_count_attr), &
                  [5*outer_count_attr])), &
          'outer residual history is exact flat 5*count storage',failures)
        DEALLOCATE(outer_history)
      ELSE
        CALL check(.FALSE.,'outer residual history has a valid count',failures)
      END IF
      expected_support=MERGE(1_int32,0_int32,outer_result%thermo_support)
      rc=nf90_inq_varid(ncid,'thermo_support',varid)
      IF (rc==NF90_NOERR) rc=nf90_get_var(ncid,varid,support)
      CALL check(rc==NF90_NOERR .AND. ALL(support==expected_support), &
        'schema-8 thermo support is stored exactly',failures)
      rc=nf90_inq_varid(ncid,'omega_target_authority',varid)
      IF (rc==NF90_NOERR) rc=nf90_get_var(ncid,varid,authority)
      CALL check(rc==NF90_NOERR .AND. ALL(authority==0_int32), &
        'schema-8 reader does not promote thermo to target authority',failures)
      rc=nf90_inq_varid(ncid,'candidate_balance_support',varid)
      IF (rc==NF90_NOERR) rc=nf90_get_var(ncid,varid,balance_support)
      CALL check(rc==NF90_NOERR .AND. ALL(balance_support==0_int32), &
        'schema-8 reader does not promote thermo to balance support',failures)
      rc=nf90_close(ncid)
    END IF

    ! A schema-7 result that merely has a larger configured cap remains an
    ! unaccepted/non-converged result and must not be upgraded to schema 8.
    bad_candidate=candidate; bad_candidate%temperature%value(1,1,1)= &
      bad_candidate%temperature%value(1,1,1)+1.0_real32
    CALL validate_shadow_write_contract(background,bad_candidate,operational, &
      thermo_result,thermo_config,status,reason)
    CALL check(status==STATUS_FAILED,'forged thermo temperature is rejected',failures)
    thermo_config%maximum_outer_iterations=8
    CALL validate_shadow_write_contract(background,candidate,operational, &
      thermo_result,thermo_config,status,reason)
    CALL check(status==STATUS_FAILED, &
      'forged existing non-converged result cannot be promoted to schema 8',failures)
    thermo_config%maximum_outer_iterations=1
    bad_result=thermo_result; bad_result%outer_iterations=2
    CALL validate_shadow_write_contract(background,candidate,operational, &
      bad_result,thermo_config,status,reason)
    CALL check(status==STATUS_FAILED,'outer iteration history cannot use single-pass schema',failures)
    bad_result=thermo_result; bad_result%outer_converged=.TRUE.
    CALL validate_shadow_write_contract(background,candidate,operational, &
      bad_result,thermo_config,status,reason)
    CALL check(status==STATUS_FAILED,'outer convergence cannot use single-pass schema',failures)

    outer_config%maximum_outer_iterations=16
    bad_result=outer_result
    bad_result%outer_iterations=outer_result%outer_iterations+1
    CALL validate_shadow_write_contract(background,outer_candidate,outer_operational, &
      bad_result,outer_config,status,reason)
    CALL check(status==STATUS_FAILED,'forged outer iteration count is rejected',failures)
    bad_result=outer_result
    bad_result%outer_max_abs_delta(1,1)=bad_result%outer_max_abs_delta(1,1)+1.0_real64
    CALL validate_shadow_write_contract(background,outer_candidate,outer_operational, &
      bad_result,outer_config,status,reason)
    CALL check(status==STATUS_FAILED,'forged outer residual history is rejected',failures)
    bad_result=outer_result
    bad_result%outer_max_abs_delta(1,1)=-1.0_real64
    CALL validate_shadow_write_contract(background,outer_candidate,outer_operational, &
      bad_result,outer_config,status,reason)
    CALL check(status==STATUS_FAILED,'negative outer residual is rejected',failures)
    bad_result=outer_result
    bad_result%outer_max_abs_delta(1,1)=ieee_value(0.0_real64,ieee_quiet_nan)
    CALL validate_shadow_write_contract(background,outer_candidate,outer_operational, &
      bad_result,outer_config,status,reason)
    CALL check(status==STATUS_FAILED,'nonfinite outer residual is rejected',failures)
    bad_result=outer_result
    bad_result%outer_max_abs_delta(1,outer_result%outer_iterations+1)=1.0_real64
    CALL validate_shadow_write_contract(background,outer_candidate,outer_operational, &
      bad_result,outer_config,status,reason)
    CALL check(status==STATUS_FAILED,'nonzero outer residual tail is rejected',failures)
    bad_result=outer_result
    bad_result%outer_max_abs_delta(1,outer_result%outer_iterations)=1.0_real64
    CALL validate_shadow_write_contract(background,outer_candidate,outer_operational, &
      bad_result,outer_config,status,reason)
    CALL check(status==STATUS_FAILED,'nonzero final outer residual is rejected',failures)
    bad_candidate=outer_candidate
    bad_candidate%temperature%value(1,1,1)=bad_candidate%temperature%value(1,1,1)+1.0_real32
    CALL validate_shadow_write_contract(background,bad_candidate,outer_operational, &
      outer_result,outer_config,status,reason)
    CALL check(status==STATUS_FAILED,'forged outer candidate is rejected',failures)

    thermo_config%maximum_outer_iterations=1
    bad_result=thermo_result
    bad_result%thermo_budget%species_change_kg(1)= &
      bad_result%thermo_budget%species_change_kg(1)+1.0_real64
    CALL validate_shadow_write_contract(background,candidate,operational,bad_result, &
      thermo_config,status,reason)
    CALL check(status==STATUS_FAILED,'tampered thermo budget is rejected',failures)
    DO mutation=1,10
      bad_result=thermo_result
      SELECT CASE (mutation)
      CASE (1); bad_result%analysis_budget%species_change_kg(1)= &
        bad_result%analysis_budget%species_change_kg(1)+1.0_real64
      CASE (2); bad_result%analysis_budget%mixing_ratio_change_kg(1)= &
        bad_result%analysis_budget%mixing_ratio_change_kg(1)+1.0_real64
      CASE (3); bad_result%analysis_budget%dry_mass_redistribution_kg(1)= &
        bad_result%analysis_budget%dry_mass_redistribution_kg(1)+1.0_real64
      CASE (4); bad_result%analysis_budget%dry_air_change_kg= &
        bad_result%analysis_budget%dry_air_change_kg+1.0_real64
      CASE (5); bad_result%analysis_budget%enthalpy_change_j= &
        bad_result%analysis_budget%enthalpy_change_j+1.0_real64
      CASE (6); bad_result%analysis_budget%total_mass_error_kg= &
        bad_result%analysis_budget%total_mass_error_kg+1.0_real64
      CASE (7); bad_result%analysis_budget%max_cell_mass_error_kg= &
        bad_result%analysis_budget%max_cell_mass_error_kg+1.0_real64
      CASE (8); bad_result%analysis_budget%accounted_cells= &
        bad_result%analysis_budget%accounted_cells+1_int64
      CASE (9); bad_result%analysis_budget%incomplete_background_cells= &
        bad_result%analysis_budget%incomplete_background_cells+1_int64
      CASE (10); bad_result%analysis_budget%incomplete_candidate_cells= &
        bad_result%analysis_budget%incomplete_candidate_cells+1_int64
      END SELECT
      CALL validate_shadow_write_contract(background,candidate,operational,bad_result, &
        thermo_config,status,reason)
      CALL check(status==STATUS_FAILED,'forged analysis budget is rejected',failures)
    END DO
    DO mutation=1,7
      bad_result=thermo_result
      SELECT CASE (mutation)
      CASE (1); bad_result%analysis_budget%species_change_kg(1)= &
        ieee_value(0.0_real64,ieee_quiet_nan)
      CASE (2); bad_result%analysis_budget%mixing_ratio_change_kg(1)= &
        ieee_value(0.0_real64,ieee_quiet_nan)
      CASE (3); bad_result%analysis_budget%dry_mass_redistribution_kg(1)= &
        ieee_value(0.0_real64,ieee_quiet_nan)
      CASE (4); bad_result%analysis_budget%dry_air_change_kg= &
        ieee_value(0.0_real64,ieee_quiet_nan)
      CASE (5); bad_result%analysis_budget%enthalpy_change_j= &
        ieee_value(0.0_real64,ieee_quiet_nan)
      CASE (6); bad_result%analysis_budget%total_mass_error_kg= &
        ieee_value(0.0_real64,ieee_quiet_nan)
      CASE (7); bad_result%analysis_budget%max_cell_mass_error_kg= &
        ieee_value(0.0_real64,ieee_quiet_nan)
      END SELECT
      CALL validate_shadow_write_contract(background,candidate,operational,bad_result, &
        thermo_config,status,reason)
      CALL check(status==STATUS_FAILED,'nonfinite analysis budget is rejected',failures)
    END DO
    bad_result=thermo_result; DEALLOCATE(bad_result%thermo_support)
    CALL validate_shadow_write_contract(background,candidate,operational,bad_result, &
      thermo_config,status,reason)
    CALL check(status==STATUS_FAILED,'missing thermo support is rejected',failures)
    bad_result=thermo_result; DEALLOCATE(bad_result%thermo_surface)
    CALL validate_shadow_write_contract(background,candidate,operational,bad_result, &
      thermo_config,status,reason)
    CALL check(status==STATUS_FAILED,'missing thermo surface is rejected',failures)
    bad_operational=operational; bad_operational%u%value(1,1,1)= &
      bad_operational%u%value(1,1,1)+1.0_real32
    CALL validate_shadow_write_contract(background,candidate,bad_operational, &
      thermo_result,thermo_config,status,reason)
    CALL check(status==STATUS_FAILED,'thermo operational mutation is rejected',failures)
    noecho=background
    noecho%radar_reflectivity%value(1,1,1)=RADAR_NO_ECHO_DBZ
    noecho%radar_reflectivity%valid(1,1,1)=.FALSE.
    noecho%radar_reflectivity%quality(1,1,1)=0_int32
    noecho%radar_reflectivity%source(1,1,1)=SOURCE_RADAR_DBZ
    CALL refresh_dry_air_mass_measure(noecho,status)
    CALL run_cloud_bal_pipeline(noecho,noecho_candidate,noecho_operational, &
      bad_result,thermo_config,active,surface,0.8_real64)
    CALL check(bad_result%status==STATUS_OK .AND. noecho_candidate%rain%value(1,1,1)== &
      noecho%rain%value(1,1,1),'no-echo thermo retains background rain',failures)
    CALL validate_shadow_write_contract(noecho,noecho_candidate,noecho_operational, &
      bad_result,thermo_config,status,reason)
    CALL check(status==STATUS_OK,'no-echo thermo result remains writable',failures)
    DO mutation=1,5
      bad_candidate=noecho_candidate
      SELECT CASE (mutation)
      CASE (1); bad_candidate%omega_target%source(1,1,1)= &
        IOR(bad_candidate%omega_target%source(1,1,1),SOURCE_COLUMN_PHYSICS)
      CASE (2); bad_candidate%precipitation_phase%quality(1,1,1)= &
        IOR(bad_candidate%precipitation_phase%quality(1,1,1),QUALITY_PHASE_UNCERTAIN)
      CASE (3); bad_candidate%hydro_support(1,1,1)=1_int32
      CASE (4); bad_candidate%rain%source(1,1,1)= &
        IOR(bad_candidate%rain%source(1,1,1),SOURCE_COLUMN_PHYSICS)
      CASE (5); bad_candidate%rain%quality(1,1,1)= &
        IOR(bad_candidate%rain%quality(1,1,1),QUALITY_PHASE_UNCERTAIN)
      END SELECT
      CALL validate_shadow_write_contract(noecho,bad_candidate,noecho_operational, &
        bad_result,thermo_config,status,reason)
      CALL check(status==STATUS_FAILED,'no-echo candidate mutation is rejected',failures)
    END DO
  END SUBROUTINE test_thermo_shadow_io

  SUBROUTINE test_cloud_qc_writer_replay(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: background,candidate,operational,bad_candidate
    TYPE(cloud_bal_pipeline_config) :: config
    TYPE(cloud_bal_pipeline_result) :: result
    LOGICAL :: thermo_active(4,4,2)
    INTEGER :: thermo_surface(4,4,2),status,reason
    REAL(real32) :: longitude(4,4)
    REAL(real64) :: residual(4,4,2)

    CALL make_state(background,4,4)
    background%cloud_fraction%value(1,1,1)=0.0_real32
    background%cloud_fraction%valid(1,1,1)=.TRUE.
    background%cloud_fraction%quality(1,1,1)=0_int32
    background%cloud_fraction%source(1,1,1)=SOURCE_CLOUD_ANALYSIS
    background%cloud_type%value(1,1,1)=1_int32
    background%cloud_type%valid(1,1,1)=.TRUE.
    background%cloud_type%quality(1,1,1)=0_int32
    background%cloud_type%source(1,1,1)=SOURCE_CLOUD_ANALYSIS
    ! Keep one ordinary cloudy cell so the HYDRO fixture reaches the column
    ! path; the separate zero-LCP cell is the contradiction under test.
    background%cloud_fraction%value(2,2,1)=0.5_real32
    background%cloud_fraction%valid(2,2,1)=.TRUE.
    background%cloud_fraction%quality(2,2,1)=0_int32
    background%cloud_fraction%source(2,2,1)=SOURCE_CLOUD_ANALYSIS
    background%cloud_type%value(2,2,1)=1_int32
    background%cloud_type%valid(2,2,1)=.TRUE.
    background%cloud_type%quality(2,2,1)=0_int32
    background%cloud_type%source(2,2,1)=SOURCE_CLOUD_ANALYSIS
    config%requested_mode=MODE_SHADOW
    longitude=0.0_real32; residual=0.0_real64

    ! HYDRO: CTY>0 with LCP=0 is a valid cloud observation whose QC is
    ! carried into the candidate and must remain writable through replay.
    CALL run_cloud_bal_pipeline(background,candidate,operational,result,config)
    CALL check(result%status==STATUS_OK .AND. &
      IAND(candidate%cloud_fraction%quality(1,1,1),QUALITY_QC_REJECTED)/=0 .AND. &
      IAND(candidate%cloud_type%quality(1,1,1),QUALITY_QC_REJECTED)/=0, &
      'HYDRO CTY>0/LCP=0 cloud QC is generated',failures)
    CALL write_shadow_diagnostics('cloud-qc-hydro-shadow.nc',background,candidate, &
      longitude,result,config,residual,residual,status,operational)
    CALL check(status==STATUS_OK,'HYDRO cloud QC candidate is writable',failures)
    bad_candidate=candidate
    bad_candidate%cloud_fraction%quality(1,1,1)=IOR( &
      bad_candidate%cloud_fraction%quality(1,1,1),QUALITY_PHASE_UNCERTAIN)
    CALL validate_shadow_write_contract(background,bad_candidate,operational,result, &
      config,status,reason)
    CALL check(status==STATUS_FAILED,'HYDRO cloud quality mutation is rejected',failures)
    CALL remove_if_present('cloud-qc-hydro-shadow.nc')

    ! Thermodynamic feedback uses the same cloud QC path and the same replay
    ! guard, with the existing explicit support fixture shape.
    thermo_active=.FALSE.; thermo_active(1,1,1)=.TRUE.
    thermo_surface=SATURATION_LIQUID
    CALL run_cloud_bal_pipeline(background,candidate,operational,result,config, &
      thermo_active,thermo_surface,0.8_real64)
    CALL check(result%status==STATUS_OK .AND. ALLOCATED(result%thermo_support) .AND. &
      IAND(candidate%cloud_fraction%quality(1,1,1),QUALITY_QC_REJECTED)/=0 .AND. &
      IAND(candidate%cloud_type%quality(1,1,1),QUALITY_QC_REJECTED)/=0, &
      'thermo CTY>0/LCP=0 cloud QC is generated',failures)
    CALL write_shadow_diagnostics('cloud-qc-thermo-shadow.nc',background,candidate, &
      longitude,result,config,residual,residual,status,operational)
    CALL check(status==STATUS_OK,'thermo cloud QC candidate is writable',failures)
    bad_candidate=candidate
    bad_candidate%cloud_type%source(1,1,1)=IOR( &
      bad_candidate%cloud_type%source(1,1,1),SOURCE_COLUMN_PHYSICS)
    CALL validate_shadow_write_contract(background,bad_candidate,operational,result, &
      config,status,reason)
    CALL check(status==STATUS_FAILED,'thermo cloud metadata mutation is rejected',failures)
    CALL remove_if_present('cloud-qc-thermo-shadow.nc')
  END SUBROUTINE test_cloud_qc_writer_replay

  SUBROUTINE test_surface_boundary_serialization(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: background,candidate,operational,bad_state
    TYPE(cloud_bal_pipeline_config) :: surface_config
    TYPE(cloud_bal_pipeline_result) :: surface_result
    REAL(real32) :: longitude(2,2)
    REAL(real64) :: residual(2,2,2)
    INTEGER :: status,reason,ncid,rc,canonical_schema,diagnostic_schema
    CHARACTER(LEN=256) :: contract
    LOGICAL :: exists
    CHARACTER(LEN=*), PARAMETER :: path='surface-boundary-shadow.nc'

    ! Keep the fixture local: optional surface coverage is deliberately
    ! asymmetric, while the pressure/temperature boundaries remain complete
    ! enough to exercise their ordinary value and metadata serialization.
    CALL make_state(background)
    background%surface_pressure%value=RESHAPE([100000.0_real32,100000.0_real32, &
      100000.0_real32,100000.0_real32],[2,2])
    background%surface_pressure%valid=.TRUE.
    background%surface_pressure%quality=0_int32
    background%surface_pressure%source=SOURCE_BACKGROUND_MODEL
    background%surface_temperature%value=RESHAPE([280.0_real32,281.0_real32, &
      282.0_real32,283.0_real32],[2,2])
    background%surface_temperature%valid=.TRUE.
    background%surface_temperature%quality=0_int32
    background%surface_temperature%source=SOURCE_BACKGROUND_MODEL
    background%surface_vapor%value=RESHAPE([0.010_real32,0.0_real32, &
      0.0_real32,0.020_real32],[2,2])
    background%surface_vapor%valid=RESHAPE([.TRUE.,.FALSE.,.FALSE.,.TRUE.],[2,2])
    background%surface_vapor%quality=RESHAPE([0_int32,QUALITY_RAW_MISSING, &
      QUALITY_RAW_MISSING,0_int32],[2,2])
    background%surface_vapor%source=RESHAPE([SOURCE_BACKGROUND_MODEL,0_int32, &
      0_int32,SOURCE_BACKGROUND_MODEL],[2,2])
    background%surface_height%value=RESHAPE([0.0_real32,50.0_real32, &
      75.0_real32,0.0_real32],[2,2])
    background%surface_height%valid=RESHAPE([.FALSE.,.TRUE.,.TRUE.,.FALSE.],[2,2])
    background%surface_height%quality=RESHAPE([QUALITY_RAW_MISSING,0_int32, &
      0_int32,QUALITY_RAW_MISSING],[2,2])
    background%surface_height%source=RESHAPE([0_int32,SOURCE_BACKGROUND_MODEL, &
      SOURCE_BACKGROUND_MODEL,0_int32],[2,2])
    candidate=background
    operational=background
    CALL make_result(surface_result,2,2,2)
    surface_config%requested_mode=MODE_SHADOW
    longitude=0.0_real32
    residual=0.0_real64

    CALL remove_if_present(path)
    CALL validate_shadow_write_contract(background,candidate,operational, &
      surface_result,surface_config,status,reason)
    CALL check(status==STATUS_OK .AND. reason==REASON_NONE, &
      'asymmetric surface-boundary fixture satisfies SHADOW authority',failures)
    CALL write_shadow_diagnostics(path,background,candidate,longitude, &
      surface_result,surface_config,residual,residual,status,operational)
    INQUIRE(FILE=path,EXIST=exists)
    CALL check(status==STATUS_OK .AND. exists, &
      'surface-boundary fixture is serialized',failures)
    IF (.NOT.exists .OR. status/=STATUS_OK) RETURN

    rc=nf90_open(path,NF90_NOWRITE,ncid)
    CALL check(rc==NF90_NOERR,'surface-boundary artifact opens for readback',failures)
    IF (rc/=NF90_NOERR) RETURN
    contract=''; canonical_schema=0; diagnostic_schema=0
    rc=nf90_get_att(ncid,NF90_GLOBAL,'surface_boundary_contract',contract)
    CALL check(rc==NF90_NOERR .AND. TRIM(contract)=='CANONICAL_SURFACE_BOUNDARY_V1', &
      'surface-boundary contract metadata is exact',failures)
    rc=nf90_get_att(ncid,NF90_GLOBAL,'cloud_bal_schema_version',canonical_schema)
    CALL check(rc==NF90_NOERR .AND. canonical_schema==5, &
      'canonical schema version remains 5',failures)
    rc=nf90_get_att(ncid,NF90_GLOBAL,'diagnostic_schema_version',diagnostic_schema)
    CALL check(rc==NF90_NOERR .AND. diagnostic_schema==5, &
      'base diagnostic schema version remains unchanged',failures)
    CALL check_surface_field_readback(ncid,'background_surface_pressure', &
      background%surface_pressure,failures)
    CALL check_surface_field_readback(ncid,'candidate_surface_pressure', &
      candidate%surface_pressure,failures)
    CALL check_surface_field_readback(ncid,'background_surface_temperature', &
      background%surface_temperature,failures)
    CALL check_surface_field_readback(ncid,'candidate_surface_temperature', &
      candidate%surface_temperature,failures)
    CALL check_surface_field_readback(ncid,'background_surface_vapor', &
      background%surface_vapor,failures)
    CALL check_surface_field_readback(ncid,'candidate_surface_vapor', &
      candidate%surface_vapor,failures)
    CALL check_surface_field_readback(ncid,'background_surface_height', &
      background%surface_height,failures)
    CALL check_surface_field_readback(ncid,'candidate_surface_height', &
      candidate%surface_height,failures)
    rc=nf90_close(ncid)
    CALL check(rc==NF90_NOERR,'surface-boundary artifact closes after readback',failures)

    ! Provenance is part of the writer authority contract.  In particular, a
    ! manufactured bit must not be serialized merely because values are finite.
    bad_state=background
    bad_state%surface_vapor%source(1,1)=IOR( &
      bad_state%surface_vapor%source(1,1),SOURCE_MANUFACTURED_TEST)
    candidate=bad_state
    operational=bad_state
    CALL remove_if_present(path)
    CALL write_shadow_diagnostics(path,bad_state,candidate,longitude, &
      surface_result,surface_config,residual,residual,status,operational)
    INQUIRE(FILE=path,EXIST=exists)
    CALL check(status==STATUS_FAILED .AND. .NOT.exists, &
      'manufactured surface-boundary provenance is rejected before publication',failures)
  END SUBROUTINE test_surface_boundary_serialization

  SUBROUTINE check_surface_field_readback(ncid,name,expected,failures)
    INTEGER, INTENT(IN) :: ncid
    CHARACTER(LEN=*), INTENT(IN) :: name
    TYPE(field2d), INTENT(IN) :: expected
    INTEGER, INTENT(INOUT) :: failures
    INTEGER :: rc,value_var,valid_var,quality_var,source_var
    REAL(real32) :: values(2,2)
    INTEGER(int32) :: valid(2,2),quality(2,2),source(2,2)
    INTEGER(int64) :: valid_time
    CHARACTER(LEN=32) :: units

    rc=nf90_inq_varid(ncid,TRIM(name),value_var)
    CALL check(rc==NF90_NOERR,'surface value variable exists: '//TRIM(name),failures)
    IF (rc/=NF90_NOERR) RETURN
    values=0.0_real32
    rc=nf90_get_var(ncid,value_var,values)
    CALL check(rc==NF90_NOERR .AND. ALL(values==expected%value), &
      'surface values read back exactly: '//TRIM(name),failures)
    units=''
    rc=nf90_get_att(ncid,value_var,'units',units)
    CALL check(rc==NF90_NOERR .AND. TRIM(units)==TRIM(expected%unit), &
      'surface units read back exactly: '//TRIM(name),failures)
    valid_time=0_int64
    rc=nf90_get_att(ncid,value_var,'valid_time',valid_time)
    CALL check(rc==NF90_NOERR .AND. valid_time==expected%valid_time, &
      'surface valid_time read back exactly: '//TRIM(name),failures)

    rc=nf90_inq_varid(ncid,TRIM(name)//'_valid',valid_var)
    CALL check(rc==NF90_NOERR,'surface validity variable exists: '//TRIM(name),failures)
    IF (rc/=NF90_NOERR) RETURN
    valid=0_int32
    rc=nf90_get_var(ncid,valid_var,valid)
    CALL check(rc==NF90_NOERR .AND. ALL(valid==MERGE(1_int32,0_int32,expected%valid)), &
      'surface validity mask read back exactly: '//TRIM(name),failures)
    CALL check_surface_mask_units(ncid,valid_var,name//' validity',failures)

    rc=nf90_inq_varid(ncid,TRIM(name)//'_quality',quality_var)
    CALL check(rc==NF90_NOERR,'surface quality variable exists: '//TRIM(name),failures)
    IF (rc/=NF90_NOERR) RETURN
    quality=0_int32
    rc=nf90_get_var(ncid,quality_var,quality)
    CALL check(rc==NF90_NOERR .AND. ALL(quality==expected%quality), &
      'surface quality read back exactly: '//TRIM(name),failures)
    CALL check_surface_mask_units(ncid,quality_var,name//' quality',failures)

    rc=nf90_inq_varid(ncid,TRIM(name)//'_source',source_var)
    CALL check(rc==NF90_NOERR,'surface source variable exists: '//TRIM(name),failures)
    IF (rc/=NF90_NOERR) RETURN
    source=0_int32
    rc=nf90_get_var(ncid,source_var,source)
    CALL check(rc==NF90_NOERR .AND. ALL(source==expected%source), &
      'surface source read back exactly: '//TRIM(name),failures)
    CALL check_surface_mask_units(ncid,source_var,name//' source',failures)
  END SUBROUTINE check_surface_field_readback

  SUBROUTINE check_surface_mask_units(ncid,varid,label,failures)
    INTEGER, INTENT(IN) :: ncid,varid
    CHARACTER(LEN=*), INTENT(IN) :: label
    INTEGER, INTENT(INOUT) :: failures
    INTEGER :: rc
    CHARACTER(LEN=32) :: units
    units=''
    rc=nf90_get_att(ncid,varid,'units',units)
    CALL check(rc==NF90_NOERR .AND. TRIM(units)=='1', &
      'surface metadata units are 1: '//TRIM(label),failures)
  END SUBROUTINE check_surface_mask_units

  SUBROUTINE test_pressure_transition_replay(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: background
    TYPE(pressure_wps_fields) :: retained
    TYPE(field3d) :: retained_omega
    INTEGER :: status

    CALL make_transition_replay_fixture(background,retained,retained_omega,status)
    CALL check(status==STATUS_OK,'transition replay fixture is canonical',failures)
    IF (status/=STATUS_OK) RETURN
    CALL check_transition_replay_case(background,retained,retained_omega,99999.5_real64, &
      .FALSE.,'same-domain transition replay',failures)
    CALL check_transition_replay_case(background,retained,retained_omega,100010.0_real64, &
      .TRUE.,'one-center transition replay',failures)
  END SUBROUTINE test_pressure_transition_replay

  SUBROUTINE check_transition_replay_case(background,retained,retained_omega,requested_column, &
                                          expect_new_center,label,failures)
    TYPE(cloud_bal_state_type), INTENT(IN) :: background
    TYPE(pressure_wps_fields), INTENT(IN) :: retained
    TYPE(field3d), INTENT(IN) :: retained_omega
    REAL(real64), INTENT(IN) :: requested_column
    LOGICAL, INTENT(IN) :: expect_new_center
    CHARACTER(LEN=*), INTENT(IN) :: label
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: seed,candidate,operational
    TYPE(cloud_bal_state_type) :: forged_candidate,forged_operational
    TYPE(cloud_bal_pipeline_config) :: config
    TYPE(cloud_bal_pipeline_result) :: result,forged
    TYPE(balance_operator_type) :: background_operator,candidate_operator
    LOGICAL :: support(4,4,3),thermo_active(4,4,3)
    INTEGER :: reference_level(4,4),thermo_surface(4,4,3),status
    INTEGER :: reason
    REAL(real64) :: requested(4,4),seed_request(4,4)
    REAL(real32) :: longitude(4,4)
    REAL(real64) :: residual_before(4,4,3),residual_after(4,4,3)

    seed_request=REAL(background%surface_pressure%value,real64)
    seed_request(1,1)=requested_column
    CALL build_pressure_transition_prior(background,retained,retained_omega, &
      seed_request,seed,status)
    CALL check(status==STATUS_OK,TRIM(label)//' seed construction',failures)
    IF (status/=STATUS_OK) RETURN

    requested=seed_request
    support=background%above_ground
    thermo_active=background%above_ground
    thermo_surface=SATURATION_LIQUID
    reference_level=0
    config%requested_mode=MODE_SHADOW
    config%horizontal_support_radius_m=10000.0_real64
    config%pressure_support_radius_pa=20000.0_real64
    config%maximum_outer_iterations=1
    config%balance%minimum_target_response_ratio=0.05_real64
    CALL run_cloud_bal_pipeline(background,candidate,operational,result,config, &
      thermo_active=thermo_active,thermo_surface=thermo_surface,target_rh=0.8_real64, &
      geopotential_support=support,geopotential_reference_level=reference_level, &
      requested_surface_pressure=requested,pressure_transition_seed=seed)
    CALL check(result%status==STATUS_OK .AND. &
      canonical_states_equal(background,operational),TRIM(label)//' pipeline acceptance',failures)
    IF (result%status/=STATUS_OK) RETURN
    CALL check(ANY(ABS(result%thermo_budget%species_change_kg)>0.0_real64), &
      TRIM(label)//' thermo condensation changes species',failures)
    CALL check(ABS(REAL(candidate%surface_pressure%value(1,1),real64)-requested_column)<0.01_real64 .AND. &
      (candidate%above_ground(1,1,1).EQV.expect_new_center), &
      TRIM(label)//' requested PS and domain',failures)
    IF (expect_new_center) THEN
      CALL check(candidate%above_ground(1,1,1),TRIM(label)//' activates one center',failures)
    ELSE
      CALL check(.NOT.candidate%above_ground(1,1,1),TRIM(label)//' preserves original domain',failures)
    END IF
    CALL check(ALLOCATED(result%pressure_transition_seed) .AND. &
      canonical_states_equal(result%pressure_transition_seed,seed), &
      TRIM(label)//' stores the accepted seed',failures)
    CALL check(pipeline_result_replays(background,candidate,result,config), &
      TRIM(label)//' producer replay succeeds',failures)

    forged=result
    IF (expect_new_center) THEN
      forged%pressure_transition_seed%temperature%value(1,1,1)= &
        forged%pressure_transition_seed%temperature%value(1,1,1)+1.0_real32
    ELSE
      forged%pressure_transition_seed%surface_pressure%value(1,1)= &
        forged%pressure_transition_seed%surface_pressure%value(1,1)+1.0_real32
    END IF
    CALL check(.NOT.pipeline_result_replays(background,candidate,forged,config), &
      TRIM(label)//' rejects a mutated consumed seed',failures)
    forged=result
    forged%geometry_budget%geometry_mass_change_kg= &
      forged%geometry_budget%geometry_mass_change_kg+1.0_real64
    CALL check(.NOT.pipeline_result_replays(background,candidate,forged,config), &
      TRIM(label)//' rejects a forged geometry budget',failures)
    forged=result
    forged%thermo_budget%sensible_change_j=forged%thermo_budget%sensible_change_j+1.0_real64
    CALL check(.NOT.pipeline_result_replays(background,candidate,forged,config), &
      TRIM(label)//' rejects a forged thermo budget',failures)

    ! Serialize the same producer result through the real writer.  The
    ! original and candidate operators own their respective pressure
    ! geometries, which matters when the one-center case exposes a new cell.
    longitude=0.0_real32
    residual_before=0.0_real64; residual_after=0.0_real64
    CALL build_balance_operator(background,config%balance,background_operator,status,reason)
    CALL check(status==STATUS_OK,TRIM(label)//' background diagnostic operator builds',failures)
    IF (status==STATUS_OK) CALL state_continuity_residual(background_operator,background, &
      residual_before,status)
    CALL check(status==STATUS_OK,TRIM(label)//' background residual is derived',failures)
    CALL build_balance_operator(candidate,config%balance,candidate_operator,status,reason)
    CALL check(status==STATUS_OK,TRIM(label)//' candidate diagnostic operator builds',failures)
    IF (status==STATUS_OK) CALL state_continuity_residual(candidate_operator,candidate, &
      residual_after,status)
    CALL check(status==STATUS_OK,TRIM(label)//' candidate residual is derived',failures)
    CALL check(canonical_states_equal(background,operational), &
      TRIM(label)//' writer preserves background operational identity',failures)
    IF (expect_new_center) THEN
      CALL write_transition_payload(background,candidate,result,'transition-replay-one-center.nc', &
        TRIM(label),failures)
      CALL write_transition_full(background,candidate,operational,result,config,longitude, &
        residual_before,residual_after,'transition-full-one-center.nc',TRIM(label),failures)
    ELSE
      CALL write_transition_payload(background,candidate,result,'transition-replay-same-domain.nc', &
        TRIM(label),failures)
      CALL write_transition_full(background,candidate,operational,result,config,longitude, &
        residual_before,residual_after,'transition-full-same-domain.nc',TRIM(label),failures)
    END IF

    ! Every serialized transition is tied to the consumed seed and to the
    ! final state/permission receipts.  A forged receipt or endpoint must fail
    ! before the writer's NOCLOBBER create call.
    forged=result
    IF (expect_new_center) THEN
      forged%pressure_transition_seed%temperature%value(1,1,1)= &
        forged%pressure_transition_seed%temperature%value(1,1,1)+1.0_real32
    ELSE
      forged%pressure_transition_seed%surface_pressure%value(1,1)= &
        forged%pressure_transition_seed%surface_pressure%value(1,1)+1.0_real32
    END IF
    CALL expect_transition_writer_rejection('transition-full-rejected.nc',background,candidate, &
      operational,forged,config,longitude,residual_before,residual_after, &
      TRIM(label)//' forged consumed seed',failures)

    forged_candidate=candidate
    forged_candidate%temperature%value(2,2,2)=forged_candidate%temperature%value(2,2,2)+0.25_real32
    CALL expect_transition_writer_rejection('transition-full-rejected.nc',background, &
      forged_candidate,operational,result,config,longitude,residual_before,residual_after, &
      TRIM(label)//' forged final temperature',failures)

    forged_candidate=candidate
    forged_candidate%vapor%value(2,2,2)=forged_candidate%vapor%value(2,2,2)+0.001_real32
    CALL expect_transition_writer_rejection('transition-full-rejected.nc',background, &
      forged_candidate,operational,result,config,longitude,residual_before,residual_after, &
      TRIM(label)//' forged final vapor',failures)

    forged_candidate=candidate
    forged_candidate%grid%dry_air_mass_measure(2,2,2)= &
      forged_candidate%grid%dry_air_mass_measure(2,2,2)+1.0e6_real64
    CALL expect_transition_writer_rejection('transition-full-rejected.nc',background, &
      forged_candidate,operational,result,config,longitude,residual_before,residual_after, &
      TRIM(label)//' forged final dry-air mass',failures)

    forged_candidate=candidate
    forged_candidate%geopotential%value(2,2,2)= &
      forged_candidate%geopotential%value(2,2,2)+1.0_real32
    CALL expect_transition_writer_rejection('transition-full-rejected.nc',background, &
      forged_candidate,operational,result,config,longitude,residual_before,residual_after, &
      TRIM(label)//' forged final Phi',failures)

    forged=result
    forged%geopotential_support(2,2,2)=.FALSE.
    CALL expect_transition_writer_rejection('transition-full-rejected.nc',background,candidate, &
      operational,forged,config,longitude,residual_before,residual_after, &
      TRIM(label)//' forged Phi support',failures)

    forged=result
    forged%requested_surface_pressure(1,1)=forged%requested_surface_pressure(1,1)+1.0_real64
    CALL expect_transition_writer_rejection('transition-full-rejected.nc',background,candidate, &
      operational,forged,config,longitude,residual_before,residual_after, &
      TRIM(label)//' forged pressure request',failures)

    forged_operational=operational
    forged_operational%temperature%value(2,2,2)= &
      forged_operational%temperature%value(2,2,2)+0.25_real32
    CALL expect_transition_writer_rejection('transition-full-rejected.nc',background,candidate, &
      forged_operational,result,config,longitude,residual_before,residual_after, &
      TRIM(label)//' forged operational state',failures)
  END SUBROUTINE check_transition_replay_case

  SUBROUTINE write_transition_full(background,candidate,operational,result,config,longitude, &
                                    residual_before,residual_after,path,label,failures)
    TYPE(cloud_bal_state_type), INTENT(IN) :: background,candidate,operational
    TYPE(cloud_bal_pipeline_result), INTENT(IN) :: result
    TYPE(cloud_bal_pipeline_config), INTENT(IN) :: config
    REAL(real32), INTENT(IN) :: longitude(:,:)
    REAL(real64), INTENT(IN) :: residual_before(:,:,:),residual_after(:,:,:)
    CHARACTER(LEN=*), INTENT(IN) :: path,label
    INTEGER, INTENT(INOUT) :: failures
    INTEGER :: status
    LOGICAL :: exists

    CALL remove_if_present(path)
    CALL write_shadow_diagnostics(path,background,candidate,longitude,result,config, &
      residual_before,residual_after,status,operational,.TRUE.)
    INQUIRE(FILE=path,EXIST=exists)
    CALL check(status==STATUS_OK .AND. exists,TRIM(label)//' full transition artifact writes',failures)
  END SUBROUTINE write_transition_full

  SUBROUTINE expect_transition_writer_rejection(path,background,candidate,operational,result,config, &
                                                longitude,residual_before,residual_after,label,failures)
    TYPE(cloud_bal_state_type), INTENT(IN) :: background,candidate,operational
    TYPE(cloud_bal_pipeline_result), INTENT(IN) :: result
    TYPE(cloud_bal_pipeline_config), INTENT(IN) :: config
    REAL(real32), INTENT(IN) :: longitude(:,:)
    REAL(real64), INTENT(IN) :: residual_before(:,:,:),residual_after(:,:,:)
    CHARACTER(LEN=*), INTENT(IN) :: path,label
    INTEGER, INTENT(INOUT) :: failures
    INTEGER :: status
    LOGICAL :: exists

    CALL remove_if_present(path)
    CALL write_shadow_diagnostics(path,background,candidate,longitude,result,config, &
      residual_before,residual_after,status,operational,.TRUE.)
    INQUIRE(FILE=path,EXIST=exists)
    CALL check(status/=STATUS_OK .AND. .NOT.exists,TRIM(label)//' is rejected before publication',failures)
  END SUBROUTINE expect_transition_writer_rejection

  SUBROUTINE write_transition_payload(background,candidate,result,path,label,failures)
    TYPE(cloud_bal_state_type), INTENT(IN) :: background
    TYPE(cloud_bal_state_type), INTENT(IN) :: candidate
    TYPE(cloud_bal_pipeline_result), INTENT(IN) :: result
    CHARACTER(LEN=*), INTENT(IN) :: path,label
    INTEGER, INTENT(INOUT) :: failures
    INTEGER :: ncid,xdim,ydim,zdim,rc,varid,pressure_var,above_ground_var
    INTEGER(int32) :: candidate_domain(4,4,3),seed_domain(4,4,3)
    INTEGER(int32) :: background_domain(4,4,3)
    REAL(real64) :: seed_dry_mass(4,4,3)
    REAL(real32) :: seed_surface_pressure(4,4)
    REAL(real32) :: pressure_levels(3)
    CHARACTER(LEN=64) :: contract,semantics
    LOGICAL :: ok

    CALL remove_if_present(path)
    rc=nf90_create(path,IOR(NF90_NOCLOBBER,NF90_NETCDF4),ncid)
    CALL check(rc==NF90_NOERR,TRIM(label)//' transition payload creates',failures)
    IF (rc/=NF90_NOERR) RETURN
    rc=nf90_def_dim(ncid,'x',4,xdim)
    IF (rc==NF90_NOERR) rc=nf90_def_dim(ncid,'y',4,ydim)
    IF (rc==NF90_NOERR) rc=nf90_def_dim(ncid,'z',3,zdim)
    IF (rc==NF90_NOERR) rc=nf90_def_var(ncid,'pressure',NF90_FLOAT,(/zdim/),pressure_var)
    IF (rc==NF90_NOERR) rc=nf90_def_var(ncid,'above_ground',NF90_INT, &
      (/xdim,ydim,zdim/),above_ground_var)
    IF (rc==NF90_NOERR) rc=nf90_put_att(ncid,pressure_var,'units','Pa')
    IF (rc==NF90_NOERR) rc=nf90_put_att(ncid,above_ground_var,'units','1')
    IF (rc==NF90_NOERR) rc=nf90_enddef(ncid)
    CALL check(rc==NF90_NOERR,TRIM(label)//' transition payload defines dimensions',failures)
    IF (rc/=NF90_NOERR) THEN
      rc=nf90_close(ncid)
      RETURN
    END IF
    pressure_levels=background%pressure%value(1,1,:)
    background_domain=MERGE(1_int32,0_int32,background%above_ground)
    rc=nf90_put_var(ncid,pressure_var,pressure_levels)
    IF (rc==NF90_NOERR) rc=nf90_put_var(ncid,above_ground_var,background_domain)
    CALL check(rc==NF90_NOERR,TRIM(label)//' transition header writes',failures)
    IF (rc/=NF90_NOERR) THEN
      rc=nf90_close(ncid)
      RETURN
    END IF
    ok=put_pressure_transition_extension(ncid,(/xdim,ydim/),(/xdim,ydim,zdim/), &
      background,candidate,result)
    CALL check(ok,TRIM(label)//' transition payload writes',failures)
    IF (ok) ok=put_transition_physical_fields(ncid,(/xdim,ydim/),(/xdim,ydim,zdim/), &
      background,candidate,result)
    CALL check(ok,TRIM(label)//' transition physical payload writes',failures)
    rc=nf90_close(ncid)
    CALL check(ok .AND. rc==NF90_NOERR,TRIM(label)//' transition payload closes',failures)
    IF (.NOT.ok .OR. rc/=NF90_NOERR) RETURN

    rc=nf90_open(path,NF90_NOWRITE,ncid)
    CALL check(rc==NF90_NOERR,TRIM(label)//' transition payload reopens',failures)
    IF (rc/=NF90_NOERR) RETURN
    contract=''; semantics=''
    rc=nf90_get_att(ncid,NF90_GLOBAL,'pressure_transition_contract',contract)
    CALL check(rc==NF90_NOERR .AND. TRIM(contract)=='pressure_transition_seed_v2', &
      TRIM(label)//' transition contract metadata',failures)
    rc=nf90_get_att(ncid,NF90_GLOBAL,'pressure_transition_support_semantics',semantics)
    CALL check(rc==NF90_NOERR .AND. TRIM(semantics)== &
      'background_support_plus_candidate_new_cells_v1', &
      TRIM(label)//' transition support metadata',failures)
    rc=nf90_inq_varid(ncid,'candidate_above_ground',varid)
    IF (rc==NF90_NOERR) rc=nf90_get_var(ncid,varid,candidate_domain)
    CALL check(rc==NF90_NOERR .AND. ALL(candidate_domain==MERGE(1_int32,0_int32, &
      candidate%above_ground)),TRIM(label)//' candidate domain readback',failures)
    rc=nf90_inq_varid(ncid,'transition_seed_above_ground',varid)
    IF (rc==NF90_NOERR) rc=nf90_get_var(ncid,varid,seed_domain)
    CALL check(rc==NF90_NOERR .AND. ALL(seed_domain==MERGE(1_int32,0_int32, &
      result%pressure_transition_seed%above_ground)),TRIM(label)//' seed domain readback',failures)
    rc=nf90_inq_varid(ncid,'transition_seed_dry_air_mass_measure',varid)
    IF (rc==NF90_NOERR) rc=nf90_get_var(ncid,varid,seed_dry_mass)
    CALL check(rc==NF90_NOERR .AND. ALL(seed_dry_mass== &
      result%pressure_transition_seed%grid%dry_air_mass_measure), &
      TRIM(label)//' seed dry mass readback',failures)
    rc=nf90_inq_varid(ncid,'transition_seed_surface_pressure',varid)
    IF (rc==NF90_NOERR) rc=nf90_get_var(ncid,varid,seed_surface_pressure)
    CALL check(rc==NF90_NOERR .AND. ALL(seed_surface_pressure== &
      result%pressure_transition_seed%surface_pressure%value), &
      TRIM(label)//' seed surface pressure readback',failures)
    CALL check_thermo_field_readback(ncid,'transition_background_pressure', &
      background%pressure,TRIM(label)//' transition background pressure',failures)
    CALL check_thermo_field_readback(ncid,'transition_candidate_pressure', &
      candidate%pressure,TRIM(label)//' transition candidate pressure',failures)
    rc=nf90_close(ncid)
    CALL check(rc==NF90_NOERR,TRIM(label)//' transition payload readback closes',failures)
  END SUBROUTINE write_transition_payload

  LOGICAL FUNCTION put_transition_physical_fields(ncid,surface_dims,volume_dims, &
                                                  background,candidate,result)
    INTEGER, INTENT(IN) :: ncid,surface_dims(2),volume_dims(3)
    TYPE(cloud_bal_state_type), INTENT(IN) :: background,candidate
    TYPE(cloud_bal_pipeline_result), INTENT(IN) :: result
    INTEGER :: support_var,surface_var,background_mass_var,candidate_mass_var
    INTEGER :: background_ps_var,candidate_ps_var,rc
    INTEGER(int32), ALLOCATABLE :: support(:,:,:)

    put_transition_physical_fields=.FALSE.
    IF (.NOT.ALLOCATED(result%thermo_support) .OR. &
        .NOT.ALLOCATED(result%thermo_surface)) RETURN
    IF (ANY(SHAPE(result%thermo_support)/= &
      (/candidate%grid%nx,candidate%grid%ny,candidate%grid%nz/)) .OR. &
        ANY(SHAPE(result%thermo_surface)/= &
      (/candidate%grid%nx,candidate%grid%ny,candidate%grid%nz/))) RETURN
    ALLOCATE(support(SIZE(result%thermo_support,1),SIZE(result%thermo_support,2), &
                    SIZE(result%thermo_support,3)))
    support=MERGE(1_int32,0_int32,result%thermo_support)

    rc=nf90_redef(ncid)
    IF (rc/=NF90_NOERR) RETURN
    IF (nf90_put_att(ncid,NF90_GLOBAL,'numerical_test_probe',1_int32)/=NF90_NOERR) RETURN
    IF (nf90_put_att(ncid,NF90_GLOBAL,'science_authority',0_int32)/=NF90_NOERR) RETURN
    IF (nf90_put_att(ncid,NF90_GLOBAL,'thermo_contract', &
      'explicit_cloud_saturation_mixture_v1')/=NF90_NOERR) RETURN
    IF (nf90_put_att(ncid,NF90_GLOBAL,'thermo_configuration', &
      'test_pipeline_transition_reference_v1')/=NF90_NOERR) RETURN
    IF (nf90_put_att(ncid,NF90_GLOBAL,'thermo_target_rh',result%thermo_target_rh)/=NF90_NOERR) RETURN
    IF (nf90_put_att(ncid,NF90_GLOBAL,'grid_dx_m',background%grid%dx(1,1))/=NF90_NOERR) RETURN
    IF (nf90_put_att(ncid,NF90_GLOBAL,'grid_dy_m',background%grid%dy(1,1))/=NF90_NOERR) RETURN
    IF (nf90_def_var(ncid,'thermo_support',NF90_INT,volume_dims,support_var)/=NF90_NOERR) RETURN
    IF (nf90_def_var(ncid,'thermo_surface',NF90_INT,volume_dims,surface_var)/=NF90_NOERR) RETURN
    IF (nf90_def_var(ncid,'dry_air_mass_measure',NF90_DOUBLE,volume_dims, &
      background_mass_var)/=NF90_NOERR) RETURN
    IF (nf90_def_var(ncid,'candidate_dry_air_mass_measure',NF90_DOUBLE,volume_dims, &
      candidate_mass_var)/=NF90_NOERR) RETURN
    IF (nf90_def_var(ncid,'background_surface_pressure',NF90_DOUBLE,surface_dims, &
      background_ps_var)/=NF90_NOERR) RETURN
    IF (nf90_def_var(ncid,'candidate_surface_pressure',NF90_DOUBLE,surface_dims, &
      candidate_ps_var)/=NF90_NOERR) RETURN
    IF (nf90_put_att(ncid,support_var,'units','1')/=NF90_NOERR .OR. &
        nf90_put_att(ncid,surface_var,'units','1')/=NF90_NOERR .OR. &
        nf90_put_att(ncid,background_mass_var,'units','kg dryair')/=NF90_NOERR .OR. &
        nf90_put_att(ncid,candidate_mass_var,'units','kg dryair')/=NF90_NOERR .OR. &
        nf90_put_att(ncid,background_ps_var,'units','Pa')/=NF90_NOERR .OR. &
        nf90_put_att(ncid,candidate_ps_var,'units','Pa')/=NF90_NOERR) RETURN
    IF (nf90_put_att(ncid,background_ps_var,'valid_time',background%surface_pressure%valid_time)/=NF90_NOERR .OR. &
        nf90_put_att(ncid,candidate_ps_var,'valid_time',candidate%surface_pressure%valid_time)/=NF90_NOERR) RETURN
    IF (nf90_enddef(ncid)/=NF90_NOERR) RETURN
    IF (nf90_put_var(ncid,support_var,support)/=NF90_NOERR .OR. &
        nf90_put_var(ncid,surface_var,result%thermo_surface)/=NF90_NOERR .OR. &
        nf90_put_var(ncid,background_mass_var,background%grid%dry_air_mass_measure)/=NF90_NOERR .OR. &
        nf90_put_var(ncid,candidate_mass_var,candidate%grid%dry_air_mass_measure)/=NF90_NOERR .OR. &
        nf90_put_var(ncid,background_ps_var,REAL(background%surface_pressure%value,real64))/=NF90_NOERR .OR. &
        nf90_put_var(ncid,candidate_ps_var,REAL(candidate%surface_pressure%value,real64))/=NF90_NOERR) RETURN

    IF (.NOT.put_thermo_field(ncid,volume_dims,'background_temperature',background%temperature)) RETURN
    IF (.NOT.put_thermo_field(ncid,volume_dims,'candidate_temperature',candidate%temperature)) RETURN
    IF (.NOT.put_thermo_field(ncid,volume_dims,'background_vapor',background%vapor)) RETURN
    IF (.NOT.put_thermo_field(ncid,volume_dims,'candidate_vapor',candidate%vapor)) RETURN
    IF (.NOT.put_thermo_field(ncid,volume_dims,'background_cloud_water',background%cloud_water)) RETURN
    IF (.NOT.put_thermo_field(ncid,volume_dims,'candidate_cloud_water',candidate%cloud_water)) RETURN
    IF (.NOT.put_thermo_field(ncid,volume_dims,'background_cloud_ice',background%cloud_ice)) RETURN
    IF (.NOT.put_thermo_field(ncid,volume_dims,'candidate_cloud_ice',candidate%cloud_ice)) RETURN
    IF (.NOT.put_thermo_field(ncid,volume_dims,'background_rain',background%rain)) RETURN
    IF (.NOT.put_thermo_field(ncid,volume_dims,'candidate_rain',candidate%rain)) RETURN
    IF (.NOT.put_thermo_field(ncid,volume_dims,'background_snow',background%snow)) RETURN
    IF (.NOT.put_thermo_field(ncid,volume_dims,'candidate_snow',candidate%snow)) RETURN
    IF (.NOT.put_thermo_field(ncid,volume_dims,'background_graupel',background%graupel)) RETURN
    IF (.NOT.put_thermo_field(ncid,volume_dims,'candidate_graupel',candidate%graupel)) RETURN
    put_transition_physical_fields=.TRUE.
  END FUNCTION put_transition_physical_fields

  LOGICAL FUNCTION put_thermo_field(ncid,dims,name,field)
    INTEGER, INTENT(IN) :: ncid,dims(3)
    CHARACTER(LEN=*), INTENT(IN) :: name
    TYPE(field3d), INTENT(IN) :: field
    INTEGER :: value_var,valid_var,quality_var,source_var,allocation_status
    INTEGER(int32), ALLOCATABLE :: valid_mask(:,:,:)

    put_thermo_field=.FALSE.
    ALLOCATE(valid_mask(SIZE(field%valid,1),SIZE(field%valid,2),SIZE(field%valid,3)), &
      STAT=allocation_status)
    IF (allocation_status/=0) RETURN
    valid_mask=MERGE(1_int32,0_int32,field%valid)
    IF (nf90_redef(ncid)/=NF90_NOERR) RETURN
    IF (nf90_def_var(ncid,name,NF90_FLOAT,dims,value_var)/=NF90_NOERR) RETURN
    IF (nf90_def_var(ncid,name//'_valid',NF90_INT,dims,valid_var)/=NF90_NOERR) RETURN
    IF (nf90_def_var(ncid,name//'_quality',NF90_INT,dims,quality_var)/=NF90_NOERR) RETURN
    IF (nf90_def_var(ncid,name//'_source',NF90_INT,dims,source_var)/=NF90_NOERR) RETURN
    IF (nf90_put_att(ncid,value_var,'units',TRIM(field%unit))/=NF90_NOERR .OR. &
        nf90_put_att(ncid,value_var,'valid_time',field%valid_time)/=NF90_NOERR .OR. &
        nf90_put_att(ncid,valid_var,'units','1')/=NF90_NOERR .OR. &
        nf90_put_att(ncid,quality_var,'units','1')/=NF90_NOERR .OR. &
        nf90_put_att(ncid,source_var,'units','1')/=NF90_NOERR) RETURN
    IF (nf90_enddef(ncid)/=NF90_NOERR) RETURN
    IF (nf90_put_var(ncid,value_var,field%value)/=NF90_NOERR .OR. &
        nf90_put_var(ncid,valid_var,valid_mask)/=NF90_NOERR .OR. &
        nf90_put_var(ncid,quality_var,field%quality)/=NF90_NOERR .OR. &
        nf90_put_var(ncid,source_var,field%source)/=NF90_NOERR) RETURN
    put_thermo_field=.TRUE.
  END FUNCTION put_thermo_field

  SUBROUTINE check_thermo_field_readback(ncid,name,expected,label,failures)
    INTEGER, INTENT(IN) :: ncid
    CHARACTER(LEN=*), INTENT(IN) :: name,label
    TYPE(field3d), INTENT(IN) :: expected
    INTEGER, INTENT(INOUT) :: failures
    INTEGER :: rc,value_var,valid_var,quality_var,source_var
    REAL(real32), ALLOCATABLE :: values(:,:,:)
    INTEGER(int32), ALLOCATABLE :: valid(:,:,:),quality(:,:,:),source(:,:,:)
    INTEGER(int64) :: valid_time
    CHARACTER(LEN=32) :: units

    rc=nf90_inq_varid(ncid,TRIM(name),value_var)
    CALL check(rc==NF90_NOERR,'thermo value variable exists: '//TRIM(label),failures)
    IF (rc/=NF90_NOERR) RETURN
    ALLOCATE(values,MOLD=expected%value)
    ALLOCATE(valid,quality,source,MOLD=expected%quality)
    values=0.0_real32
    rc=nf90_get_var(ncid,value_var,values)
    CALL check(rc==NF90_NOERR .AND. ALL(values==expected%value), &
      'thermo values read back exactly: '//TRIM(label),failures)
    units=''
    rc=nf90_get_att(ncid,value_var,'units',units)
    CALL check(rc==NF90_NOERR .AND. TRIM(units)==TRIM(expected%unit), &
      'thermo units read back exactly: '//TRIM(label),failures)
    valid_time=0_int64
    rc=nf90_get_att(ncid,value_var,'valid_time',valid_time)
    CALL check(rc==NF90_NOERR .AND. valid_time==expected%valid_time, &
      'thermo valid_time read back exactly: '//TRIM(label),failures)

    rc=nf90_inq_varid(ncid,TRIM(name)//'_valid',valid_var)
    CALL check(rc==NF90_NOERR,'thermo validity variable exists: '//TRIM(label),failures)
    IF (rc/=NF90_NOERR) RETURN
    valid=0_int32
    rc=nf90_get_var(ncid,valid_var,valid)
    CALL check(rc==NF90_NOERR .AND. ALL(valid==MERGE(1_int32,0_int32,expected%valid)), &
      'thermo validity mask read back exactly: '//TRIM(label),failures)
    CALL check_surface_mask_units(ncid,valid_var,TRIM(label)//' validity',failures)

    rc=nf90_inq_varid(ncid,TRIM(name)//'_quality',quality_var)
    CALL check(rc==NF90_NOERR,'thermo quality variable exists: '//TRIM(label),failures)
    IF (rc/=NF90_NOERR) RETURN
    quality=0_int32
    rc=nf90_get_var(ncid,quality_var,quality)
    CALL check(rc==NF90_NOERR .AND. ALL(quality==expected%quality), &
      'thermo quality read back exactly: '//TRIM(label),failures)
    CALL check_surface_mask_units(ncid,quality_var,TRIM(label)//' quality',failures)

    rc=nf90_inq_varid(ncid,TRIM(name)//'_source',source_var)
    CALL check(rc==NF90_NOERR,'thermo source variable exists: '//TRIM(label),failures)
    IF (rc/=NF90_NOERR) RETURN
    source=0_int32
    rc=nf90_get_var(ncid,source_var,source)
    CALL check(rc==NF90_NOERR .AND. ALL(source==expected%source), &
      'thermo source read back exactly: '//TRIM(label),failures)
    CALL check_surface_mask_units(ncid,source_var,TRIM(label)//' source',failures)
  END SUBROUTINE check_thermo_field_readback

  SUBROUTINE make_transition_replay_fixture(state,retained,omega,status)
    TYPE(cloud_bal_state_type), INTENT(OUT) :: state
    TYPE(pressure_wps_fields), INTENT(OUT) :: retained
    TYPE(field3d), INTENT(OUT) :: omega
    INTEGER, INTENT(OUT) :: status
    INTEGER :: i,j,k
    CALL make_state(state,4,4,3)
    state%pressure%value(:,:,1)=100000.0_real32
    state%pressure%value(:,:,2)=95000.0_real32
    state%pressure%value(:,:,3)=90000.0_real32
    CALL mark_valid(state%pressure,SOURCE_BACKGROUND_MODEL)
    state%surface_pressure%value=99999.125_real32
    state%surface_pressure%valid=.TRUE.; state%surface_pressure%quality=0_int32
    state%surface_pressure%source=SOURCE_BACKGROUND_MODEL
    state%surface_temperature%value=290.0_real32
    state%surface_temperature%valid=.TRUE.; state%surface_temperature%quality=0_int32
    state%surface_temperature%source=SOURCE_BACKGROUND_MODEL
    state%surface_vapor%value=0.006_real32
    state%surface_vapor%valid=.TRUE.; state%surface_vapor%quality=0_int32
    state%surface_vapor%source=SOURCE_BACKGROUND_MODEL
    state%surface_height%value=100.0_real32
    state%surface_height%valid=.TRUE.; state%surface_height%quality=0_int32
    state%surface_height%source=SOURCE_BACKGROUND_MODEL
    ! The real writer's pressure/geostrophic diagnostic requires a usable
    ! latitude on every evaluated column; keep this replay fixture physical.
    state%latitude%value=37.0_real32
    state%latitude%valid=.TRUE.; state%latitude%quality=0_int32
    state%latitude%source=SOURCE_BACKGROUND_MODEL
    DO k=1,3
      state%geopotential%value(:,:,k)=REAL(9.80665_real64* &
        REAL(100.0_real64+100.0_real64*REAL(k,real64),real64),real32)
    END DO
    CALL mark_valid(state%geopotential,SOURCE_BACKGROUND_MODEL)
    CALL configure_pressure_geometry(state,status)
    IF (status/=STATUS_OK) RETURN
    CALL mask_transition_replay_state(state)
    CALL refresh_dry_air_mass_measure(state,status)
    IF (status/=STATUS_OK) RETURN

    ALLOCATE(retained%p(4),retained%t(4,4,4),retained%ht(4,4,4), &
      retained%u(4,4,4),retained%v(4,4,4),retained%rh(4,4,4),retained%qv(4,4,4), &
      retained%qc(4,4,3),retained%qi(4,4,3),retained%qr(4,4,3), &
      retained%qs(4,4,3),retained%qg(4,4,3),retained%psfc(4,4),retained%slp(4,4), &
      retained%skin_temperature(4,4),retained%snow_cover(4,4))
    retained%p=[1000.0_real32,950.0_real32,900.0_real32,2001.0_real32]
    DO k=1,3
      retained%t(:,:,k)=280.0_real32+REAL(k,real32)
      retained%ht(:,:,k)=100.0_real32+100.0_real32*REAL(k,real32)
      retained%u(:,:,k)=5.0_real32; retained%v(:,:,k)=-2.0_real32
      retained%rh(:,:,k)=50.0_real32; retained%qv(:,:,k)=0.008_real32
      retained%qc(:,:,k)=0.0002_real32; retained%qi(:,:,k)=0.0001_real32
      retained%qr(:,:,k)=0.0001_real32; retained%qs(:,:,k)=0.0001_real32
      retained%qg(:,:,k)=0.0001_real32
    END DO
    retained%t(:,:,4)=290.0_real32; retained%ht(:,:,4)=100.0_real32
    retained%u(:,:,4)=5.0_real32; retained%v(:,:,4)=-2.0_real32
    retained%rh(:,:,4)=50.0_real32; retained%qv(:,:,4)=0.006_real32
    retained%psfc=state%surface_pressure%value; retained%slp=101000.0_real32
    retained%skin_temperature=290.0_real32; retained%snow_cover=0.0_real32
    retained%valid_time=state%pressure%valid_time
    retained%grid_id=state%grid%grid_id; retained%wind_coordinate='GRID_RELATIVE'
    CALL initialize_field(omega,4,4,3,state%pressure%valid_time,'Pa s-1')
    omega%value=0.0_real32; omega%valid=.TRUE.; omega%quality=0_int32
    omega%source=SOURCE_ANALYZED_WIND
  END SUBROUTINE make_transition_replay_fixture

  SUBROUTINE mask_transition_replay_state(state)
    TYPE(cloud_bal_state_type), INTENT(INOUT) :: state
    WHERE (.NOT.state%above_ground)
      state%pressure%valid=.FALSE.; state%pressure%quality=QUALITY_RAW_MISSING; state%pressure%source=0_int32
      state%temperature%valid=.FALSE.; state%temperature%quality=QUALITY_RAW_MISSING; state%temperature%source=0_int32
      state%vapor%valid=.FALSE.; state%vapor%quality=QUALITY_RAW_MISSING; state%vapor%source=0_int32
      state%u%valid=.FALSE.; state%u%quality=QUALITY_RAW_MISSING; state%u%source=0_int32
      state%v%valid=.FALSE.; state%v%quality=QUALITY_RAW_MISSING; state%v%source=0_int32
      state%omega%valid=.FALSE.; state%omega%quality=QUALITY_RAW_MISSING; state%omega%source=0_int32
      state%geopotential%valid=.FALSE.; state%geopotential%quality=QUALITY_RAW_MISSING; state%geopotential%source=0_int32
    END WHERE
  END SUBROUTINE mask_transition_replay_state

  SUBROUTINE make_state(state,nx_in,ny_in,nz_in)
    TYPE(cloud_bal_state_type), INTENT(OUT) :: state
    INTEGER, INTENT(IN), OPTIONAL :: nx_in,ny_in,nz_in
    INTEGER :: i,j,k,nx,ny,local_status
    INTEGER :: nz
    nx=2; ny=2; nz=2
    IF (PRESENT(nx_in)) nx=nx_in
    IF (PRESENT(ny_in)) ny=ny_in
    IF (PRESENT(nz_in)) nz=nz_in
    CALL initialize_cloud_bal_state(state,nx,ny,nz,1788224400_int64, &
                                    'io-contract-test',local_status)
    IF (local_status/=STATUS_OK) ERROR STOP 'state initialization failed'
    DO k=1,nz; DO j=1,ny; DO i=1,nx
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
