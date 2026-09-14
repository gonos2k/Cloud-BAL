PROGRAM test_pipeline
  USE, INTRINSIC :: iso_fortran_env,ONLY: real32,real64,int32,int64
  USE cloud_bal_state
  USE cloud_bal_column_physics,ONLY: derive_column_physics,SATURATION_LIQUID,SATURATION_ICE, &
    pressure_analysis_budget,water_phase_budget
  USE cloud_bal_balance_operator,ONLY: TARGET_AUTHORITY_OBSERVATIONAL, &
    TARGET_AUTHORITY_MANUFACTURED_TEST,TARGET_AUTHORITY_MODEL_DYNAMICS, &
    BOUNDARY_INCREMENT_HOMOGENEOUS_MODEL,apply_localized_balance
  USE cloud_bal_pipeline
  IMPLICIT NONE
  TYPE(cloud_bal_state_type) :: input,candidate,operational,column_candidate
  TYPE(cloud_bal_pipeline_config) :: config
  TYPE(cloud_bal_pipeline_result) :: result
  INTEGER :: failures,status
  REAL(real64) :: saved_minimum_target_response_ratio
  REAL(real64), PARAMETER :: ORACLE_T0=273.15_real64,ORACLE_CPD=1004.5_real64
  REAL(real64), PARAMETER :: ORACLE_CP(6)=[1846.4_real64,4190.0_real64,2106.0_real64, &
                                           4190.0_real64,2106.0_real64,2106.0_real64]
  REAL(real64), PARAMETER :: ORACLE_H0(6)=[2.50e6_real64,0.0_real64,-3.50e5_real64, &
                                           0.0_real64,-3.50e5_real64,-3.50e5_real64]

  failures=0
  CALL make_state(input)
  config%requested_mode=MODE_OFF
  CALL run_cloud_bal_pipeline(input,candidate,operational,result,config)
  CALL check(result%status==STATUS_OK,'OFF must be a successful no-op',failures)
  CALL check(same_pipeline_state(input,operational), &
             'OFF must preserve operational state',failures)
  CALL check(zero_analysis_budget(result%analysis_budget), &
             'OFF must publish a zero analysis budget',failures)

  config%requested_mode=MODE_SHADOW
  CALL run_cloud_bal_pipeline(input,candidate,operational,result,config)
  CALL check(result%status==STATUS_OK .AND. same_pipeline_state(input,candidate) .AND. &
             same_pipeline_state(input,operational) .AND. &
             zero_analysis_budget(result%analysis_budget), &
             'SHADOW with no observations must publish no analysis budget',failures)

  CALL make_complete_water_fields(input)
  CALL add_radar_cell(input)
  config%horizontal_support_radius_m=5000.0_real64
  config%balance%required_residual_fraction=0.50_real64
  config%balance%minimum_target_response_ratio=0.0_real64
  config%balance%maximum_target_response_ratio=100.0_real64
  config%balance%geostrophic_absolute_tolerance=1.0_real64
  CALL run_cloud_bal_pipeline(input,candidate,operational,result,config)
  CALL check(result%status==STATUS_OK .AND. &
             result%balance%numerical%solver_reason==SOLVER_NOT_RUN .AND. &
             .NOT.ANY(result%balance%changed), &
             'uncertain radar loading cannot seed the wind solver',failures)
  CALL check(same_pipeline_state(input,operational), &
             'SHADOW must not change operational state',failures)
  CALL derive_column_physics(input,column_candidate,result%column,config%column)
  CALL build_compact_balance_beta(column_candidate,config%horizontal_support_radius_m, &
                                  config%pressure_support_radius_pa,status)
  CALL check(result%column%status==STATUS_OK .AND. ANY(column_candidate%rain%value>0.0_real32), &
             'SHADOW column stage must calculate the radar hydrometeor candidate',failures)
  CALL check(.NOT.ANY(column_candidate%balance_beta>0.0_real32), &
             'uncertain radar target must have zero balance support',failures)
  CALL check(candidate%rain%value(2,2,3)>input%rain%value(2,2,3) .AND. &
             ALL(candidate%vapor%value==input%vapor%value) .AND. &
             candidate%grid%dry_air_mass_measure(2,2,3)< &
             input%grid%dry_air_mass_measure(2,2,3) .AND. &
             result%analysis_budget%dry_air_change_kg<0.0_real64 .AND. &
             result%analysis_budget%species_change_kg(1)<0.0_real64 .AND. &
             ABS(result%analysis_budget%mixing_ratio_change_kg(1))<1.0e-8_real64, &
             'radar rain lowers dry and vapor mass despite unchanged vapor ratio',failures)
  CALL check_analysis_budget(input,candidate,result%analysis_budget,failures, &
                             'complete radar budget')

  CALL make_state(input)
  CALL remove_cloud_analysis(input)
  CALL remove_unused_surface_temperature(input)
  input%cloud_water%value=0.123_real32
  input%cloud_ice%value=0.234_real32
  CALL add_radar_cell(input)
  CALL run_cloud_bal_pipeline(input,candidate,operational,result,config)
  CALL check(result%status==STATUS_OK .AND. result%column%status==STATUS_OK .AND. &
             result%balance%numerical%solver_reason==SOLVER_NOT_RUN, &
             'radar-only input must remain a hydrometeor-only proposal',failures)
  CALL check(same_pipeline_state(input,operational), &
             'radar-only SHADOW must not change operational state',failures)
  CALL check(ALL(candidate%temperature%value==input%temperature%value) .AND. &
             ALL(candidate%vapor%value==input%vapor%value), &
             'radar-only proposal must not implicitly enable thermodynamic adjustment',failures)
  CALL check_analysis_budget(input,candidate,result%analysis_budget,failures, &
                             'incomplete radar budget')
  CALL check(result%analysis_budget%incomplete_background_cells>0_int64 .AND. &
             result%analysis_budget%incomplete_candidate_cells>0_int64 .AND. &
             result%analysis_budget%accounted_cells>0_int64, &
             'unknown hydrometeors are reported as incomplete coverage',failures)

  config%horizontal_support_radius_m=-1.0_real64
  CALL run_cloud_bal_pipeline(input,candidate,operational,result,config)
  CALL check(result%status==STATUS_FAILED .AND. same_pipeline_state(input,candidate) .AND. &
             same_pipeline_state(input,operational) .AND. &
             zero_analysis_budget(result%analysis_budget), &
             'late localization failure must rollback the radar analysis budget',failures)
  config%horizontal_support_radius_m=5000.0_real64

  CALL make_state(input)
  CALL add_radar_cell(input)
  input%omega_target%value(2,2,3)=0.08_real32
  input%omega_target%valid(2,2,3)=.TRUE.
  input%omega_target%quality(2,2,3)=0_int32
  input%omega_target%source(2,2,3)= &
    IOR(SOURCE_CONVENTIONAL_OBS,SOURCE_DYNAMIC_TARGET)
  ! Synthetic observational target: carry an explicit finite uncertainty with
  ! the same dynamic evidence, without implying calibrated retrieval errors.
  input%omega_target_sigma%value(2,2,3)=0.5_real32
  input%omega_target_sigma%valid(2,2,3)=.TRUE.
  input%omega_target_sigma%quality(2,2,3)=0_int32
  input%omega_target_sigma%source(2,2,3)=input%omega_target%source(2,2,3)
  CALL run_cloud_bal_pipeline(input,candidate,operational,result,config)
  CALL check(result%status==STATUS_OK .AND. &
             result%balance%numerical%solver_reason==SOLVER_CONVERGED .AND. &
             ANY(candidate%balance_beta>0.0_real32), &
             'an explicit trusted dynamic target must reach the solver',failures)
  CALL check(same_pipeline_state(input,operational), &
             'trusted SHADOW target still cannot change operational state',failures)
  CALL check(result%analysis_budget%accounted_cells>0_int64 .AND. &
             ANY(ABS(result%analysis_budget%species_change_kg)>0.0_real64), &
             'accepted radar-plus-balance proposal carries its analysis budget',failures)
  CALL check_analysis_budget(input,candidate,result%analysis_budget,failures, &
                             'accepted radar-plus-balance budget')

  saved_minimum_target_response_ratio=config%balance%minimum_target_response_ratio
  config%balance%minimum_target_response_ratio=0.50_real64
  CALL run_cloud_bal_pipeline(input,candidate,operational,result,config)
  CALL check(result%status==STATUS_DEGRADED, &
             'rejected balance must report degraded status',failures)
  CALL check(same_pipeline_state(input,candidate) .AND. &
             same_pipeline_state(input,operational), &
             'rejected balance must publish the original state',failures)
  CALL check(.NOT.ANY(result%column%changed) .AND. &
             .NOT.ANY(result%balance%changed) .AND. &
             .NOT.ANY(result%overall%changed), &
             'rejected balance must clear all change masks',failures)
  CALL check(zero_analysis_budget(result%analysis_budget), &
             'rejected balance must clear the analysis budget',failures)
  config%balance%minimum_target_response_ratio=saved_minimum_target_response_ratio

  CALL make_state(input)
  input%surface_pressure%value=90000.0_real32
  CALL configure_pressure_geometry(input,status)
  IF (status/=STATUS_OK) ERROR STOP 'terrain fixture geometry failed'
  CALL invalidate_level(input,1)
  CALL remove_cloud_analysis(input)
  CALL refresh_dry_air_mass_measure(input,status)
  IF (status/=STATUS_OK) ERROR STOP 'terrain fixture mass refresh failed'
  CALL add_radar_cell(input)
  CALL derive_column_physics(input,column_candidate,result%column,config%column)
  CALL build_compact_balance_beta(column_candidate,config%horizontal_support_radius_m, &
                                  config%pressure_support_radius_pa,status)
  CALL check(result%column%status==STATUS_OK .AND. status==STATUS_OK .AND. &
             .NOT.ANY(column_candidate%balance_beta(:,:,1)>0.0_real32), &
             'localization must never enter below-ground cells',failures)

  config%requested_mode=2
  CALL run_cloud_bal_pipeline(input,candidate,operational,result,config)
  CALL check(result%status==STATUS_FAILED .AND. result%reason_code==REASON_AUTHORITY, &
             'this research build must reject every active request',failures)
  CALL check(same_pipeline_state(input,operational), &
             'authority rejection must rollback',failures)
  CALL check(zero_analysis_budget(result%analysis_budget), &
             'authority rejection must clear the analysis budget',failures)

  config%requested_mode=MODE_SHADOW
  config%balance%target_authority=TARGET_AUTHORITY_MANUFACTURED_TEST
  CALL run_cloud_bal_pipeline(input,candidate,operational,result,config)
  CALL check(result%status==STATUS_FAILED .AND. &
             result%reason_code==REASON_AUTHORITY .AND. &
             same_pipeline_state(input,operational), &
    'manufactured authority must never enter the normal pipeline',failures)
  config%balance%target_authority=TARGET_AUTHORITY_OBSERVATIONAL

  CALL make_state(input)
  input%omega_top_boundary%source= &
    IOR(SOURCE_BOUNDARY_CONDITION,SOURCE_MANUFACTURED_TEST)
  input%omega_bottom_boundary%source= &
    IOR(SOURCE_BOUNDARY_CONDITION,SOURCE_MANUFACTURED_TEST)
  CALL run_cloud_bal_pipeline(input,candidate,operational,result,config)
  CALL check(result%status==STATUS_FAILED .AND. &
             result%reason_code==REASON_AUTHORITY .AND. &
             same_pipeline_state(input,operational), &
    'manufactured boundaries must never enter the normal pipeline',failures)

  CALL make_state(input)
  input%omega_target%source(2,2,2)=SOURCE_MANUFACTURED_TEST
  CALL run_cloud_bal_pipeline(input,candidate,operational,result,config)
  CALL check(result%status==STATUS_FAILED .AND. &
             result%reason_code==REASON_AUTHORITY .AND. &
             same_pipeline_state(input,operational), &
    'invalid target cells cannot carry manufactured provenance',failures)

  ! Sigma provenance is part of the observational authority contract too.
  ! It must reject even when the target field itself is not valid.
  CALL make_state(input)
  input%omega_target_sigma%value(2,2,2)=0.5_real32
  input%omega_target_sigma%valid(2,2,2)=.TRUE.
  input%omega_target_sigma%quality(2,2,2)=0_int32
  input%omega_target_sigma%source=IOR(SOURCE_ANALYZED_WIND,SOURCE_MANUFACTURED_TEST)
  config%requested_mode=MODE_OFF
  CALL run_cloud_bal_pipeline(input,candidate,operational,result,config)
  CALL check(result%status==STATUS_OK .AND. result%reason_code==REASON_NONE .AND. &
             same_pipeline_state(input,candidate) .AND. same_pipeline_state(input,operational), &
    'OFF must remain an exact no-op regardless of target provenance',failures)
  config%requested_mode=MODE_SHADOW
  CALL run_cloud_bal_pipeline(input,candidate,operational,result,config)
  CALL check(result%status==STATUS_FAILED .AND. result%reason_code==REASON_AUTHORITY .AND. &
             same_pipeline_state(input,candidate) .AND. same_pipeline_state(input,operational), &
    'SHADOW must reject manufactured sigma provenance before analysis',failures)

  CALL make_state(input)
  DEALLOCATE(input%omega_target%source)
  CALL run_cloud_bal_pipeline(input,candidate,operational,result,config)
  CALL check(result%status==STATUS_FAILED .AND. result%reason_code==REASON_SHAPE, &
    'malformed target provenance storage must fail without array conformability',failures)

  CALL make_state(input)
  input%precipitation_phase%valid(2,2,3)=.TRUE.
  input%precipitation_phase%quality(2,2,3)=0_int32
  input%precipitation_phase%source(2,2,3)=SOURCE_CLOUD_ANALYSIS
  input%precipitation_phase%value(2,2,3)=99_int32
  config%requested_mode=MODE_SHADOW
  CALL run_cloud_bal_pipeline(input,candidate,operational,result,config)
  CALL check(result%status==STATUS_FAILED .AND. &
             same_pipeline_state(input,candidate) .AND. &
             same_pipeline_state(input,operational), &
             'non-OK shadow stage must return the exact input state',failures)

  CALL test_explicit_thermo_pipeline(failures)
  CALL test_analysis_budget_with_thermo(failures)
  CALL test_outer_iterations(failures)
  CALL test_geopotential_pipeline(failures)
  CALL test_requested_surface_pressure(failures)
  CALL test_model_dynamic_pipeline(failures)
  IF (failures/=0) THEN
    PRINT *,'Pipeline tests failed:',failures
    ERROR STOP 1
  END IF
  PRINT *,'Cloud-BAL pipeline authority tests passed'

CONTAINS

  SUBROUTINE test_model_dynamic_pipeline(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: input,candidate,operational
    TYPE(field3d) :: target_before
    TYPE(cloud_bal_pipeline_config) :: config
    TYPE(cloud_bal_pipeline_result) :: result
    INTEGER(int32), PARAMETER :: model_source=IOR( &
      SOURCE_BACKGROUND_MODEL,SOURCE_DYNAMIC_TARGET)

    config%requested_mode=MODE_SHADOW
    config%balance%target_authority=TARGET_AUTHORITY_MODEL_DYNAMICS
    config%balance%boundary_increment_contract=BOUNDARY_INCREMENT_HOMOGENEOUS_MODEL
    CALL make_state(input,7)
    input%model_target_coverage=.TRUE.
    input%omega_target%value=input%omega%value
    input%omega_target%valid=.FALSE.
    input%omega_target%quality=QUALITY_RAW_MISSING
    input%omega_target%source=0_int32
    input%omega_target%valid(:,:,3:5)=.TRUE.
    input%omega_target%quality(:,:,3:5)=0_int32
    input%omega_target%source(:,:,3:5)=model_source
    input%omega_target_sigma%valid=.FALSE.
    input%omega_target_sigma%quality=QUALITY_RAW_MISSING
    input%omega_target_sigma%source=0_int32
    CALL run_cloud_bal_pipeline(input,candidate,operational,result,config)
    CALL check(result%status==STATUS_OK .AND. &
      .NOT.ANY(result%overall%changed) .AND. same_pipeline_state(input,operational) .AND. &
      same_field(input%u,candidate%u) .AND. same_field(input%v,candidate%v) .AND. &
      same_field(input%omega,candidate%omega) .AND. ANY(candidate%balance_beta>0.0_real32), &
      'model pipeline accepts a resolved zero target without sigma weighting',failures)

    ! A radar-derived diagnostic at an absent cell must not append empirical
    ! omega target data to a supplied model field. Preserve distinctive data
    ! and provenance at both the resolved and absent cells to test the whole
    ! value/mask/quality/source payload through column and balance stages.
    CALL make_state(input,7)
    CALL add_radar_cell(input)
    input%model_target_coverage=.TRUE.
    input%omega_target%value=-0.3125_real32
    input%omega_target%valid=.FALSE.
    input%omega_target%quality=QUALITY_RAW_MISSING
    input%omega_target%source=SOURCE_BACKGROUND_MODEL
    input%omega_target%value(3,3,4)=0.0_real32
    input%omega_target%valid(3,3,4)=.TRUE.
    input%omega_target%quality(3,3,4)=0_int32
    input%omega_target%source(3,3,4)=model_source
    target_before=input%omega_target
    CALL run_cloud_bal_pipeline(input,candidate,operational,result,config)
    CALL check(result%status==STATUS_OK .AND. &
      same_field(candidate%omega_target,target_before) .AND. &
      same_field(operational%omega_target,target_before), &
      'model pipeline preserves every supplied target value and provenance cell',failures)

    CALL make_state(input,7)
    input%model_target_coverage=.TRUE.
    CALL run_cloud_bal_pipeline(input,candidate,operational,result,config)
    CALL check(result%status==STATUS_FAILED .AND. result%reason_code==REASON_AUTHORITY .AND. &
      same_pipeline_state(input,candidate) .AND. same_pipeline_state(input,operational), &
      'model pipeline rejects a missing paired target',failures)
  END SUBROUTINE test_model_dynamic_pipeline

  SUBROUTINE test_outer_iterations(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: background,single_candidate,single_operational
    TYPE(cloud_bal_state_type) :: fixed_candidate,fixed_operational
    TYPE(cloud_bal_state_type) :: replay_column,replay_balance
    TYPE(cloud_bal_state_type) :: contradiction_background
    TYPE(cloud_bal_state_type) :: contradiction_candidate,contradiction_operational
    TYPE(cloud_bal_pipeline_config) :: single_config,fixed_config,cap_config
    TYPE(cloud_bal_pipeline_result) :: single_result,fixed_result,cap_result
    TYPE(cloud_bal_pipeline_result) :: contradiction_result
    TYPE(stage_result) :: replay_column_result,replay_balance_result
    TYPE(water_phase_budget) :: replay_thermo_budget
    TYPE(pressure_analysis_budget) :: replay_analysis_budget
    LOGICAL :: active(4,4,3)
    INTEGER :: surface(4,4,3),status

    ! OFF is a true no-op even when its outer-loop cap is nonsensical.
    CALL make_state(background)
    single_config%requested_mode=MODE_OFF
    single_config%maximum_outer_iterations=0
    CALL run_cloud_bal_pipeline(background,single_candidate,single_operational, &
                                single_result,single_config)
    CALL check(single_result%status==STATUS_OK .AND. single_result%outer_iterations==0 .AND. &
      .NOT.single_result%outer_converged .AND. same_pipeline_state(background,single_candidate) .AND. &
      same_pipeline_state(background,single_operational) .AND. &
      zero_analysis_budget(single_result%analysis_budget), &
      'OFF ignores an invalid outer iteration cap',failures)

    ! Active modes validate the cap before doing any column work.
    single_config%requested_mode=MODE_SHADOW
    CALL run_cloud_bal_pipeline(background,single_candidate,single_operational, &
                                single_result,single_config)
    CALL check(single_result%status==STATUS_FAILED .AND. single_result%reason_code==REASON_RANGE .AND. &
      single_result%outer_iterations==0 .AND. .NOT.single_result%outer_converged .AND. &
      same_pipeline_state(background,single_candidate) .AND. &
      same_pipeline_state(background,single_operational) .AND. &
      zero_analysis_budget(single_result%analysis_budget), &
      'SHADOW rejects an outer iteration cap outside 1..32',failures)

    CALL make_outer_thermo_radar_fixture(background,active,surface,status)
    CALL check(status==STATUS_OK,'outer-loop thermo/radar fixture setup',failures)
    single_config%requested_mode=MODE_SHADOW
    single_config%maximum_outer_iterations=1
    CALL run_cloud_bal_pipeline(background,single_candidate,single_operational, &
                                single_result,single_config,active,surface,0.8_real64)
    CALL check(single_result%status==STATUS_OK .AND. single_result%outer_iterations==1 .AND. &
      .NOT.single_result%outer_converged .AND. single_result%analysis_budget%accounted_cells>0_int64, &
      'single-pass mode retains its non-convergence contract',failures)

    fixed_config=single_config
    fixed_config%maximum_outer_iterations=16
    CALL run_cloud_bal_pipeline(background,fixed_candidate,fixed_operational,fixed_result, &
                                fixed_config,active,surface,0.8_real64)
    CALL check(fixed_result%status==STATUS_OK .AND. fixed_result%outer_converged .AND. &
      fixed_result%outer_iterations==3 .AND. &
      same_pipeline_state(background,fixed_operational), &
      'bounded thermo/radar outer loop reaches an exact fixed point in three trials',failures)
    CALL check(ANY(fixed_result%outer_max_abs_delta(:,1)>0.0_real64) .AND. &
      ANY(fixed_result%outer_max_abs_delta(:,2)>0.0_real64) .AND. &
      ALL(fixed_result%outer_max_abs_delta(:,3)==0.0_real64) .AND. &
      ALL(fixed_result%outer_max_abs_delta(:,4:32)==0.0_real64), &
      'outer residual history has nonzero prior trials and a zero final trial',failures)
    CALL check(ANY(fixed_candidate%rain%value/=single_candidate%rain%value) .OR. &
      ANY(fixed_candidate%snow%value/=single_candidate%snow%value) .OR. &
      ANY(fixed_candidate%graupel%value/=single_candidate%graupel%value), &
      'EOS feedback changes fresh radar precipitation after the single pass',failures)

    ! Re-run the final fixed-point evaluation through the production derive and
    ! balance path.  Both feedback fields and the pressure-fixed analysis
    ! ledger must remain anchored to the accepted trial.
    CALL derive_column_physics(background,replay_column,replay_column_result, &
      fixed_config%column,active,surface,0.8_real64,replay_thermo_budget, &
      replay_analysis_budget,fixed_candidate)
    CALL check(replay_column_result%status==STATUS_OK, &
      'independent fixed-point column replay succeeds',failures)
    CALL build_compact_balance_beta(replay_column,fixed_config%horizontal_support_radius_m, &
      fixed_config%pressure_support_radius_pa,status)
    CALL check(status==STATUS_OK,'independent fixed-point localization succeeds',failures)
    CALL apply_localized_balance(replay_column,replay_balance,replay_balance_result, &
      fixed_config%balance)
    CALL check(replay_balance_result%status==STATUS_OK .AND. &
      same_feedback_fields(fixed_candidate,replay_balance), &
      'separate production derive-to-balance replay reproduces exact feedback',failures)
    CALL check(analysis_budgets_equal(fixed_result%analysis_budget,replay_analysis_budget), &
      'fixed-point analysis budget remains anchored to the accepted trial',failures)

    ! A deliberately small cap must roll back before this changed thermo/radar
    ! fixture reaches its exact fixed point.
    cap_config=fixed_config
    cap_config%maximum_outer_iterations=2
    CALL run_cloud_bal_pipeline(background,single_candidate,single_operational,cap_result, &
                                cap_config,active,surface,0.8_real64)
    CALL check(fixed_result%outer_iterations>2, &
      'changed thermo/radar fixture requires more than two outer iterations',failures)
    CALL check(cap_result%status==STATUS_FAILED .AND. cap_result%reason_code==REASON_SOLVER .AND. &
      cap_result%outer_iterations==2 .AND. .NOT.cap_result%outer_converged .AND. &
      same_pipeline_state(background,single_candidate) .AND. &
      same_pipeline_state(background,single_operational) .AND. &
      zero_analysis_budget(cap_result%analysis_budget) .AND. &
      zero_thermo_budget(cap_result%thermo_budget) .AND. &
      .NOT.ALLOCATED(cap_result%thermo_support) .AND. &
      .NOT.ALLOCATED(cap_result%thermo_surface), &
      'outer cap exhaustion rolls back candidate and accepted budgets/support',failures)
    CALL check(ANY(cap_result%outer_max_abs_delta(:,1)>0.0_real64) .AND. &
      ANY(cap_result%outer_max_abs_delta(:,2)>0.0_real64) .AND. &
      ALL(cap_result%outer_max_abs_delta(:,3:32)==0.0_real64), &
      'failed outer cap retains measured residual history only',failures)

    CALL make_outer_thermo_radar_fixture(contradiction_background,active,surface,status)
    contradiction_background%cloud_fraction%value(2,2,2)=0.005_real32
    contradiction_background%cloud_type%value(2,2,2)=1_int32
    CALL run_cloud_bal_pipeline(contradiction_background,contradiction_candidate, &
      contradiction_operational,contradiction_result,fixed_config,active,surface,0.8_real64)
    CALL check(contradiction_result%status==STATUS_OK .AND. contradiction_result%outer_converged .AND. &
      same_pipeline_state(contradiction_background,contradiction_operational) .AND. &
      IAND(contradiction_candidate%cloud_fraction%quality(2,2,2),QUALITY_QC_REJECTED)/=0_int32, &
      'contradictory cloud metadata is QC-rejected without breaking outer convergence',failures)
  END SUBROUTINE test_outer_iterations

  SUBROUTINE test_geopotential_pipeline(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: background,normal_candidate,normal_operational
    TYPE(cloud_bal_state_type) :: bounded_candidate,bounded_operational
    TYPE(cloud_bal_state_type) :: repeat_candidate,repeat_operational
    TYPE(cloud_bal_state_type) :: failed_candidate,failed_operational
    TYPE(cloud_bal_state_type) :: cap_candidate,cap_operational
    TYPE(cloud_bal_pipeline_config) :: config,bounded_config,fail_config,cap_config
    TYPE(cloud_bal_pipeline_result) :: normal_result,bounded_result,repeat_result
    TYPE(cloud_bal_pipeline_result) :: missing_pair_result,shape_result,truncated_result
    TYPE(cloud_bal_pipeline_result) :: failure_result,cap_result
    LOGICAL :: active(4,4,3),support(4,4,3),bad_support(4,4,2),truncated_support(4,4,3)
    INTEGER :: surface(4,4,3),reference_level(4,4),status

    CALL make_geopotential_thermo_fixture(background,active,surface,support, &
                                           reference_level,status)
    CALL check(status==STATUS_OK,'geopotential thermo fixture setup',failures)

    config%requested_mode=MODE_SHADOW
    config%maximum_outer_iterations=1
    config%horizontal_support_radius_m=12000.0_real64
    config%pressure_support_radius_pa=30000.0_real64
    config%balance%minimum_target_response_ratio=0.0_real64
    CALL run_cloud_bal_pipeline(background,normal_candidate,normal_operational, &
      normal_result,config,active,surface,0.8_real64,support,reference_level)
    CALL check(normal_result%status==STATUS_OK .AND. &
      normal_result%column%status==STATUS_OK .AND. &
      normal_result%geopotential%status==STATUS_OK .AND. &
      ANY(normal_result%column%changed) .AND. &
      ANY(normal_result%geopotential%changed) .AND. &
      ANY(normal_result%overall%changed), &
      'thermodynamic proposal reaches the geopotential stage',failures)
    CALL check(ANY(normal_candidate%geopotential%value/=background%geopotential%value) .AND. &
      ALL(normal_candidate%u%value==background%u%value) .AND. &
      ALL(normal_candidate%v%value==background%v%value) .AND. &
      ALL(normal_candidate%omega%value==background%omega%value), &
      'geopotential adjustment changes Phi without wind authority',failures)
    CALL check(normal_candidate%geopotential%value(2,2,1)== &
      background%geopotential%value(2,2,1), &
      'geopotential request keeps the lowest represented center fixed',failures)
    CALL check(ALLOCATED(normal_result%geopotential_support) .AND. &
      ALLOCATED(normal_result%geopotential_reference_level) .AND. &
      ALL(normal_result%geopotential_support .EQV. support) .AND. &
      ALL(normal_result%geopotential_reference_level==reference_level), &
      'accepted geopotential request stores its support receipt',failures)
    CALL check(same_pipeline_state(background,normal_operational), &
      'accepted geopotential proposal preserves operational state',failures)

    ! Every bounded trial is recomputed from the same background Phi.  A
    ! second request from that background must therefore be bitwise stable,
    ! rather than accumulating the previous hydrostatic increment.
    bounded_config=config
    bounded_config%maximum_outer_iterations=16
    CALL run_cloud_bal_pipeline(background,bounded_candidate,bounded_operational, &
      bounded_result,bounded_config,active,surface,0.8_real64,support,reference_level)
    CALL run_cloud_bal_pipeline(background,repeat_candidate,repeat_operational, &
      repeat_result,bounded_config,active,surface,0.8_real64,support,reference_level)
    CALL check(bounded_result%status==STATUS_OK .AND. bounded_result%outer_converged .AND. &
      bounded_result%outer_iterations>1 .AND. same_pipeline_state(bounded_candidate,repeat_candidate) .AND. &
      same_field(bounded_candidate%geopotential,normal_candidate%geopotential), &
      'bounded outer geopotential trials are deterministic from one background',failures)
    CALL check(ALL(bounded_result%geopotential%changed .EQV. &
      normal_result%geopotential%changed) .AND. &
      bounded_result%overall%changed(2,2,2), &
      'bounded outer result retains the accepted geopotential mask',failures)
    CALL check(same_pipeline_state(background,bounded_operational) .AND. &
      same_pipeline_state(background,repeat_operational), &
      'bounded geopotential trials never update operational state',failures)

    ! MODE_OFF is an identity even when all explicit request arguments are
    ! supplied, and it must not retain a permission receipt.
    config%requested_mode=MODE_OFF
    config%maximum_outer_iterations=0
    CALL run_cloud_bal_pipeline(background,failed_candidate,failed_operational, &
      failure_result,config,active,surface,0.8_real64,support,reference_level)
    CALL check(failure_result%status==STATUS_OK .AND. &
      same_pipeline_state(background,failed_candidate) .AND. &
      same_pipeline_state(background,failed_operational) .AND. &
      .NOT.ALLOCATED(failure_result%geopotential_support) .AND. &
      .NOT.ALLOCATED(failure_result%geopotential_reference_level), &
      'MODE_OFF keeps geopotential request as a strict identity',failures)

    config%requested_mode=MODE_SHADOW
    config%maximum_outer_iterations=1
    CALL run_cloud_bal_pipeline(background,failed_candidate,failed_operational, &
      missing_pair_result,config,active,surface,0.8_real64,support)
    CALL check(missing_pair_result%status==STATUS_FAILED .AND. &
      missing_pair_result%reason_code==REASON_AUTHORITY .AND. &
      same_pipeline_state(background,failed_candidate) .AND. &
      same_pipeline_state(background,failed_operational) .AND. &
      .NOT.ALLOCATED(missing_pair_result%geopotential_support), &
      'missing geopotential request pair rolls back before analysis',failures)

    bad_support=.TRUE.
    CALL run_cloud_bal_pipeline(background,failed_candidate,failed_operational, &
      shape_result,config,active,surface,0.8_real64,bad_support,reference_level)
    CALL check(shape_result%status==STATUS_FAILED .AND. &
      shape_result%reason_code==REASON_SHAPE .AND. &
      same_pipeline_state(background,failed_candidate) .AND. &
      same_pipeline_state(background,failed_operational) .AND. &
      .NOT.ANY(shape_result%overall%changed), &
      'wrong geopotential support shape rolls back the full request',failures)

    truncated_support=.FALSE.; truncated_support(2,2,2)=.TRUE.
    CALL run_cloud_bal_pipeline(background,failed_candidate,failed_operational, &
      truncated_result,config,active,surface,0.8_real64,truncated_support,reference_level)
    CALL check(truncated_result%status==STATUS_FAILED .AND. &
      same_pipeline_state(background,failed_candidate) .AND. &
      same_pipeline_state(background,failed_operational) .AND. &
      .NOT.ANY(truncated_result%geopotential%changed) .AND. &
      .NOT.ALLOCATED(truncated_result%geopotential_support), &
      'support truncation rejects an unauthorized Phi increment',failures)

    ! A downstream balance rejection must discard an already computed
    ! thermo/geopotential proposal and its budgets together.
    CALL make_geopotential_thermo_fixture(background,active,surface,support, &
                                           reference_level,status)
    CALL add_radar_cell(background)
    background%omega_target%value(2,2,3)=0.08_real32
    background%omega_target%valid(2,2,3)=.TRUE.
    background%omega_target%quality(2,2,3)=0_int32
    background%omega_target%source(2,2,3)= &
      IOR(SOURCE_CONVENTIONAL_OBS,SOURCE_DYNAMIC_TARGET)
    background%omega_target_sigma%value(2,2,3)=0.5_real32
    background%omega_target_sigma%valid(2,2,3)=.TRUE.
    background%omega_target_sigma%quality(2,2,3)=0_int32
    background%omega_target_sigma%source(2,2,3)=background%omega_target%source(2,2,3)
    fail_config=config
    fail_config%balance%minimum_target_response_ratio=0.50_real64
    CALL run_cloud_bal_pipeline(background,failed_candidate,failed_operational, &
      failure_result,fail_config,active,surface,0.8_real64,support,reference_level)
    CALL check(failure_result%status==STATUS_DEGRADED .AND. &
      same_pipeline_state(background,failed_candidate) .AND. &
      same_pipeline_state(background,failed_operational) .AND. &
      .NOT.ANY(failure_result%column%changed) .AND. &
      .NOT.ANY(failure_result%geopotential%changed) .AND. &
      .NOT.ANY(failure_result%overall%changed) .AND. &
      zero_analysis_budget(failure_result%analysis_budget) .AND. &
      zero_thermo_budget(failure_result%thermo_budget) .AND. &
      .NOT.ALLOCATED(failure_result%geopotential_support), &
      'later balance rejection rolls back thermo and geopotential stages',failures)

    ! The outer-loop cap must also rollback a completed geopotential trial.
    CALL make_outer_thermo_radar_fixture(background,active,surface,status)
    support=.FALSE.; support(2,2,:)=.TRUE.; reference_level=1
    cap_config=config
    cap_config%maximum_outer_iterations=2
    CALL run_cloud_bal_pipeline(background,cap_candidate,cap_operational,cap_result, &
      cap_config,active,surface,0.8_real64,support,reference_level)
    CALL check(cap_result%status==STATUS_FAILED .AND. cap_result%reason_code==REASON_SOLVER .AND. &
      cap_result%outer_iterations==2 .AND. .NOT.cap_result%outer_converged .AND. &
      same_pipeline_state(background,cap_candidate) .AND. &
      same_pipeline_state(background,cap_operational) .AND. &
      .NOT.ANY(cap_result%geopotential%changed) .AND. &
      .NOT.ANY(cap_result%overall%changed) .AND. zero_analysis_budget(cap_result%analysis_budget) .AND. &
      zero_thermo_budget(cap_result%thermo_budget) .AND. &
      .NOT.ALLOCATED(cap_result%geopotential_support), &
      'outer iteration cap rolls back completed geopotential trial',failures)
  END SUBROUTINE test_geopotential_pipeline

  SUBROUTINE test_requested_surface_pressure(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: background,background_before
    TYPE(cloud_bal_state_type) :: candidate,operational
    TYPE(cloud_bal_state_type) :: frozen_candidate,frozen_operational
    TYPE(cloud_bal_state_type) :: failed_candidate,failed_operational
    TYPE(cloud_bal_pipeline_config) :: config,off_config
    TYPE(cloud_bal_pipeline_result) :: result,frozen_result
    TYPE(cloud_bal_pipeline_result) :: off_result,malformed_result
    TYPE(cloud_bal_pipeline_result) :: missing_geo_result,unsupported_result
    TYPE(cloud_bal_pipeline_result) :: crossing_result
    LOGICAL :: thermo_active(4,4,3),support(4,4,3),unsupported_support(4,4,3)
    INTEGER :: thermo_surface(4,4,3),reference_level(4,4),status
    REAL(real64) :: requested_surface_pressure(4,4),requested_before(4,4)
    REAL(real64) :: malformed_surface_pressure(3,4),crossing_surface_pressure(4,4)

    CALL make_geopotential_thermo_fixture(background,thermo_active,thermo_surface, &
      support,reference_level,status)
    CALL check(status==STATUS_OK,'requested-PS fixture setup',failures)
    CALL add_surface_anchor_fields(background)
    background_before=background
    support=.TRUE.
    reference_level=0
    requested_surface_pressure=REAL(background%surface_pressure%value,real64)+20.0_real64
    requested_before=requested_surface_pressure

    config%requested_mode=MODE_SHADOW
    config%maximum_outer_iterations=1
    config%horizontal_support_radius_m=12000.0_real64
    config%pressure_support_radius_pa=30000.0_real64
    config%balance%minimum_target_response_ratio=0.0_real64
    CALL run_cloud_bal_pipeline(background,candidate,operational,result,config, &
      thermo_active,thermo_surface,0.8_real64,support,reference_level, &
      requested_surface_pressure)
    CALL check(result%status==STATUS_OK .AND. result%geopotential%status==STATUS_OK .AND. &
      ALL(candidate%surface_pressure%value==REAL(requested_surface_pressure,real32)) .AND. &
      result%geometry_budget%accounted_cells>0_int64 .AND. &
      result%geometry_budget%geometry_mass_change_kg>0.0_real64, &
      'full-surface +20 Pa request commits geometry and its budget',failures)
    CALL check(ALLOCATED(result%requested_surface_pressure), &
      'accepted pressure request stores its receipt',failures)
    IF (ALLOCATED(result%requested_surface_pressure)) THEN
      CALL check(ALL(result%requested_surface_pressure==requested_surface_pressure), &
        'pressure receipt preserves the prescribed surface field',failures)
    END IF
    CALL check(same_pipeline_state(background,background_before) .AND. &
      same_pipeline_state(background,operational) .AND. &
      ALL(requested_surface_pressure==requested_before), &
      'accepted pressure request preserves caller inputs and operational state',failures)

    ! A prescribed field is not yet a variable-geometry outer-loop solve.  The
    ! request is therefore rejected before any trial can reinterpret it as
    ! pressure-geometry feedback; the accepted single-pass receipt above remains the
    ! exact caller-supplied field.
    config%maximum_outer_iterations=16
    CALL run_cloud_bal_pipeline(background,frozen_candidate,frozen_operational, &
      frozen_result,config,thermo_active,thermo_surface,0.8_real64,support, &
      reference_level,requested_surface_pressure)
    CALL check_requested_pressure_failure(background,frozen_candidate,frozen_operational, &
      frozen_result,failures,'multi-outer prescribed pressure')
    config%maximum_outer_iterations=1

    ! MODE_OFF remains an identity even when the new request is malformed and
    ! the legacy geopotential pair is present.
    malformed_surface_pressure=0.0_real64
    off_config=config
    off_config%requested_mode=MODE_OFF
    off_config%maximum_outer_iterations=0
    CALL run_cloud_bal_pipeline(background,failed_candidate,failed_operational, &
      off_result,off_config,thermo_active,thermo_surface,0.8_real64,support, &
      reference_level,malformed_surface_pressure)
    CALL check(off_result%status==STATUS_OK .AND. &
      same_pipeline_state(background,failed_candidate) .AND. &
      same_pipeline_state(background,failed_operational) .AND. &
      .NOT.ALLOCATED(off_result%requested_surface_pressure) .AND. &
      zero_analysis_budget(off_result%geometry_budget), &
      'MODE_OFF ignores the pressure request as a strict no-op',failures)

    ! An explicit request requires both geopotential authorization arrays.
    CALL run_cloud_bal_pipeline(background,failed_candidate,failed_operational, &
      missing_geo_result,config,requested_surface_pressure=requested_surface_pressure)
    CALL check_requested_pressure_failure(background,failed_candidate,failed_operational, &
      missing_geo_result,failures,'missing geopotential pair')

    ! Every changed surface column needs full hydrostatic support.  Leave one
    ! column unsupported to verify transactional rollback before publication.
    unsupported_support=.TRUE.; unsupported_support(1,1,:)=.FALSE.
    CALL run_cloud_bal_pipeline(background,failed_candidate,failed_operational, &
      unsupported_result,config,thermo_active,thermo_surface,0.8_real64, &
      unsupported_support,reference_level,requested_surface_pressure)
    CALL check_requested_pressure_failure(background,failed_candidate,failed_operational, &
      unsupported_result,failures,'unsupported pressure geometry')

    ! A requested PSFC below the lowest represented pressure crosses the
    ! active-domain classification and must not be rounded into a commit.
    crossing_surface_pressure=94000.0_real64
    CALL run_cloud_bal_pipeline(background,failed_candidate,failed_operational, &
      crossing_result,config,thermo_active,thermo_surface,0.8_real64,support, &
      reference_level,crossing_surface_pressure)
    CALL check_requested_pressure_failure(background,failed_candidate,failed_operational, &
      crossing_result,failures,'crossing requested pressure')

    ! Wrong request shape is rejected before any candidate or receipt is
    ! published.
    CALL run_cloud_bal_pipeline(background,failed_candidate,failed_operational, &
      malformed_result,config,thermo_active,thermo_surface,0.8_real64,support, &
      reference_level,malformed_surface_pressure)
    CALL check_requested_pressure_failure(background,failed_candidate,failed_operational, &
      malformed_result,failures,'malformed requested pressure shape')
  END SUBROUTINE test_requested_surface_pressure

  SUBROUTINE check_requested_pressure_failure(background,candidate,operational,result, &
                                              failures,label)
    TYPE(cloud_bal_state_type), INTENT(IN) :: background,candidate,operational
    TYPE(cloud_bal_pipeline_result), INTENT(IN) :: result
    INTEGER, INTENT(INOUT) :: failures
    CHARACTER(LEN=*), INTENT(IN) :: label

    CALL check(result%status==STATUS_FAILED .AND. &
      same_pipeline_state(background,candidate) .AND. &
      same_pipeline_state(background,operational) .AND. &
      .NOT.ALLOCATED(result%requested_surface_pressure) .AND. &
      zero_analysis_budget(result%geometry_budget), &
      TRIM(label)//' rolls back without a pressure receipt or geometry budget',failures)
  END SUBROUTINE check_requested_pressure_failure

  SUBROUTINE add_surface_anchor_fields(state)
    TYPE(cloud_bal_state_type), INTENT(INOUT) :: state

    state%surface_pressure%value=100000.0_real32
    state%surface_pressure%valid=.TRUE.
    state%surface_pressure%quality=0_int32
    state%surface_pressure%source=SOURCE_BACKGROUND_MODEL
    state%surface_temperature%value=280.0_real32
    state%surface_temperature%valid=.TRUE.
    state%surface_temperature%quality=0_int32
    state%surface_temperature%source=SOURCE_BACKGROUND_MODEL
    state%surface_vapor%value=0.008_real32
    state%surface_vapor%valid=.TRUE.
    state%surface_vapor%quality=0_int32
    state%surface_vapor%source=SOURCE_BACKGROUND_MODEL
    state%surface_height%value=50.0_real32
    state%surface_height%valid=.TRUE.
    state%surface_height%quality=0_int32
    state%surface_height%source=SOURCE_BACKGROUND_MODEL
  END SUBROUTINE add_surface_anchor_fields

  SUBROUTINE make_geopotential_thermo_fixture(state,active,surface,support,reference_level,status)
    TYPE(cloud_bal_state_type), INTENT(OUT) :: state
    LOGICAL, INTENT(OUT) :: active(4,4,3),support(4,4,3)
    INTEGER, INTENT(OUT) :: surface(4,4,3),reference_level(4,4),status

    CALL make_state(state)
    CALL make_complete_water_fields(state)
    state%cloud_water%value(2,2,2)=0.002_real32
    CALL refresh_dry_air_mass_measure(state,status)
    IF (status/=STATUS_OK) RETURN
    CALL set_valid_monotonic_geopotential(state)
    active=.FALSE.; active(2,2,2)=.TRUE.
    surface=SATURATION_LIQUID
    support=.FALSE.; support(2,2,:)=.TRUE.
    reference_level=1
  END SUBROUTINE make_geopotential_thermo_fixture

  SUBROUTINE set_valid_monotonic_geopotential(state)
    TYPE(cloud_bal_state_type), INTENT(INOUT) :: state
    INTEGER :: k

    DO k=1,state%grid%nz
      state%geopotential%value(:,:,k)=1000.0_real32+500.0_real32*REAL(k-1,real32)
    END DO
    CALL valid_real(state%geopotential,SOURCE_BACKGROUND_MODEL)
  END SUBROUTINE set_valid_monotonic_geopotential

  SUBROUTINE make_outer_thermo_radar_fixture(state,active,surface,status)
    TYPE(cloud_bal_state_type), INTENT(OUT) :: state
    LOGICAL, INTENT(OUT) :: active(4,4,3)
    INTEGER, INTENT(OUT) :: surface(4,4,3),status

    CALL make_state(state)
    CALL make_complete_water_fields(state)
    state%cloud_water%value(2,2,2)=0.002_real32
    CALL refresh_dry_air_mass_measure(state,status)
    IF (status/=STATUS_OK) RETURN
    CALL add_radar_cell(state)
    active=.FALSE.; active(2,2,2)=.TRUE.
    surface=SATURATION_LIQUID
  END SUBROUTINE make_outer_thermo_radar_fixture

  LOGICAL FUNCTION same_feedback_fields(left,right)
    TYPE(cloud_bal_state_type), INTENT(IN) :: left,right
    INTEGER :: i,j,k

    same_feedback_fields=.FALSE.
    DO k=1,left%grid%nz; DO j=1,left%grid%ny; DO i=1,left%grid%nx
      IF (.NOT.left%above_ground(i,j,k)) CYCLE
      IF ((left%temperature%valid(i,j,k).NEQV.right%temperature%valid(i,j,k)) .OR. &
          (left%vapor%valid(i,j,k).NEQV.right%vapor%valid(i,j,k)) .OR. &
          (left%u%valid(i,j,k).NEQV.right%u%valid(i,j,k)) .OR. &
          (left%v%valid(i,j,k).NEQV.right%v%valid(i,j,k)) .OR. &
          (left%omega%valid(i,j,k).NEQV.right%omega%valid(i,j,k))) RETURN
      IF (.NOT.(left%temperature%valid(i,j,k) .AND. left%vapor%valid(i,j,k) .AND. &
          left%u%valid(i,j,k) .AND. left%v%valid(i,j,k) .AND. &
          left%omega%valid(i,j,k))) CYCLE
      IF (left%temperature%value(i,j,k)/=right%temperature%value(i,j,k) .OR. &
          left%vapor%value(i,j,k)/=right%vapor%value(i,j,k) .OR. &
          left%u%value(i,j,k)/=right%u%value(i,j,k) .OR. &
          left%v%value(i,j,k)/=right%v%value(i,j,k) .OR. &
          left%omega%value(i,j,k)/=right%omega%value(i,j,k)) RETURN
    END DO; END DO; END DO
    same_feedback_fields=.TRUE.
  END FUNCTION same_feedback_fields

  SUBROUTINE test_explicit_thermo_pipeline(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: background,candidate,operational
    TYPE(cloud_bal_pipeline_config) :: config
    TYPE(cloud_bal_pipeline_result) :: result
    LOGICAL :: active(4,4,3)
    INTEGER :: surface(4,4,3),status

    CALL make_state(background)
    CALL valid_real(background%cloud_water,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(background%cloud_ice,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(background%rain,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(background%snow,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(background%graupel,SOURCE_BACKGROUND_MODEL)
    background%cloud_water%value=0.0_real32; background%cloud_ice%value=0.0_real32
    background%rain%value=0.0_real32; background%snow%value=0.0_real32
    background%graupel%value=0.0_real32
    background%cloud_water%value(2,2,2)=0.002_real32
    CALL refresh_dry_air_mass_measure(background,status)
    CALL check(status==STATUS_OK,'thermo pipeline fixture mass',failures)
    active=.FALSE.; active(2,2,2)=.TRUE.; surface=SATURATION_LIQUID
    config%requested_mode=MODE_SHADOW
    CALL run_cloud_bal_pipeline(background,candidate,operational,result,config,active,surface,0.8_real64)
    CALL check(result%status==STATUS_OK .AND. result%overall%changed(2,2,2), &
      'explicit thermo reaches SHADOW candidate through the normal path',failures)
    CALL check(candidate%temperature%value(2,2,2)/=background%temperature%value(2,2,2) .AND. &
      candidate%vapor%value(2,2,2)/=background%vapor%value(2,2,2), &
      'thermo pipeline changes paired temperature and vapor',failures)
    CALL check(result%column%numerical%radar_analysis_increment==0.0_real64 .AND. &
      ANY(result%thermo_budget%species_change_kg/=0.0_real64), &
      'internal condensation is not a radar analysis increment',failures)
    CALL check(result%balance%numerical%solver_reason==SOLVER_NOT_RUN .AND. &
      ALL(candidate%balance_beta==0.0_real32) .AND. &
      ALL(candidate%u%value==background%u%value) .AND. &
      ALL(candidate%v%value==background%v%value) .AND. &
      ALL(candidate%omega%value==background%omega%value), &
      'thermodynamics alone grants no wind innovation',failures)
    CALL check(canonical_states_equal(operational,background), &
      'successful thermo pipeline preserves operational state',failures)

    config%horizontal_support_radius_m=-1.0_real64
    CALL run_cloud_bal_pipeline(background,candidate,operational,result,config,active,surface,0.8_real64)
    CALL check(result%status==STATUS_FAILED .AND. canonical_states_equal(candidate,background) .AND. &
      canonical_states_equal(operational,background) .AND. .NOT.ANY(result%column%changed) .AND. &
      zero_analysis_budget(result%analysis_budget) .AND. &
      ALL(result%thermo_budget%species_change_kg==0.0_real64) .AND. &
      result%thermo_budget%sensible_change_j==0.0_real64 .AND. &
      result%thermo_budget%phase_change_j==0.0_real64, &
      'post-thermo localization failure rolls back state and accepted budget',failures)
    config%horizontal_support_radius_m=12000.0_real64
    active(3,2,2)=.TRUE.; surface(3,2,2)=SATURATION_ICE
    CALL run_cloud_bal_pipeline(background,candidate,operational,result,config,active,surface,0.8_real64)
    CALL check(result%status==STATUS_FAILED .AND. canonical_states_equal(candidate,background) .AND. &
      canonical_states_equal(operational,background) .AND. &
      zero_analysis_budget(result%analysis_budget) .AND. &
      ALL(result%thermo_budget%species_change_kg==0.0_real64), &
      'later thermo failure preserves complete pipeline input',failures)

    config%requested_mode=MODE_OFF
    CALL run_cloud_bal_pipeline(background,candidate,operational,result,config,active,surface,0.8_real64)
    CALL check(result%status==STATUS_OK .AND. canonical_states_equal(candidate,background) .AND. &
      canonical_states_equal(operational,background) .AND. &
      zero_analysis_budget(result%analysis_budget) .AND. &
      ALL(result%thermo_budget%species_change_kg==0.0_real64), &
      'OFF remains a no-op with an explicit thermo request',failures)
    config%requested_mode=MODE_SHADOW
    background%temperature%source(2,2,2)=IOR(SOURCE_BACKGROUND_MODEL,SOURCE_COLUMN_PHYSICS)
    CALL run_cloud_bal_pipeline(background,candidate,operational,result,config)
    CALL check(result%status==STATUS_FAILED .AND. result%reason_code==REASON_AUTHORITY, &
      'generated temperature alone cannot bypass the pristine-background guard',failures)
  END SUBROUTINE test_explicit_thermo_pipeline

  SUBROUTINE test_analysis_budget_with_thermo(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: background,hydro_candidate,thermo_candidate,operational
    TYPE(cloud_bal_state_type) :: cold_background,cold_candidate,cold_operational
    TYPE(cloud_bal_pipeline_config) :: config
    TYPE(cloud_bal_pipeline_result) :: hydro_result,thermo_result,cold_result
    LOGICAL :: active(4,4,3)
    INTEGER :: surface(4,4,3),status

    CALL make_state(background)
    CALL make_complete_water_fields(background)
    background%cloud_water%value(2,2,2)=0.002_real32
    CALL refresh_dry_air_mass_measure(background,status)
    CALL check(status==STATUS_OK,'analysis budget thermo fixture mass',failures)
    CALL add_radar_cell(background)
    active=.FALSE.; active(2,2,2)=.TRUE.; surface=SATURATION_LIQUID
    config%requested_mode=MODE_SHADOW
    CALL run_cloud_bal_pipeline(background,hydro_candidate,operational,hydro_result,config)
    CALL check(hydro_result%status==STATUS_OK .AND. hydro_result%analysis_budget%accounted_cells>0_int64, &
      'no-thermo radar proposal commits an analysis budget',failures)
    CALL check(hydro_candidate%rain%value(2,2,3)>0.0_real32 .AND. &
      hydro_candidate%snow%value(2,2,3)==0.0_real32, &
      'warm radar fixture carries nonzero rain',failures)
    CALL check_analysis_budget(background,hydro_candidate,hydro_result%analysis_budget,failures, &
      'no-thermo comparison budget')

    CALL run_cloud_bal_pipeline(background,thermo_candidate,operational,thermo_result,config, &
      active,surface,0.8_real64)
    CALL check(thermo_result%status==STATUS_OK .AND. &
      ANY(thermo_result%thermo_budget%species_change_kg/=0.0_real64), &
      'thermo-enabled radar proposal commits internal phase change',failures)
    CALL check_analysis_budget(background,hydro_candidate,thermo_result%analysis_budget,failures, &
      'thermo pre-phase comparison budget')
    CALL check(analysis_budgets_equal(hydro_result%analysis_budget,thermo_result%analysis_budget), &
      'analysis budget is unchanged by internal thermo phase exchange',failures)
    CALL check_composite_enthalpy(background,thermo_candidate, &
      thermo_result%analysis_budget%enthalpy_change_j, &
      thermo_result%thermo_budget%enthalpy_error_j,failures, &
      'analysis plus internal thermo enthalpy composition')
    CALL check(ANY(ABS(thermo_candidate%vapor%value-hydro_candidate%vapor%value)>0.0_real32) .AND. &
      ANY(ABS(thermo_candidate%cloud_water%value-hydro_candidate%cloud_water%value)>0.0_real32), &
      'thermo changes stored phase fields after the analysis ledger',failures)

    CALL make_state(cold_background)
    CALL make_complete_water_fields(cold_background)
    cold_background%temperature%value(2,2,3)=250.0_real32
    cold_background%cloud_ice%value(2,2,3)=0.001_real32
    cold_background%snow%value(2,2,3)=0.0005_real32
    CALL refresh_dry_air_mass_measure(cold_background,status)
    CALL check(status==STATUS_OK,'cold analysis budget fixture mass',failures)
    CALL add_radar_cell(cold_background)
    CALL run_cloud_bal_pipeline(cold_background,cold_candidate,cold_operational,cold_result,config)
    CALL check(cold_result%status==STATUS_OK,'cold radar fixture succeeds',failures)
    CALL check(cold_candidate%cloud_ice%value(2,2,3)>0.0_real32, &
      'cold radar fixture retains nonzero ice',failures)
    CALL check(cold_candidate%snow%value(2,2,3)>0.0_real32 .AND. &
      cold_candidate%rain%value(2,2,3)==0.0_real32, &
      'cold radar fixture carries nonzero snow',failures)
    CALL check_analysis_budget(cold_background,cold_candidate,cold_result%analysis_budget,failures, &
      'cold ice-snow comparison budget')
    CALL check(ABS(cold_result%analysis_budget%enthalpy_change_j)>0.0_real64, &
      'cold ice-snow analysis enthalpy increment is nonzero',failures)
  END SUBROUTINE test_analysis_budget_with_thermo

  SUBROUTINE check_analysis_budget(background,candidate,actual,failures,label)
    TYPE(cloud_bal_state_type), INTENT(IN) :: background,candidate
    TYPE(pressure_analysis_budget), INTENT(IN) :: actual
    INTEGER, INTENT(INOUT) :: failures
    CHARACTER(LEN=*), INTENT(IN) :: label
    REAL(real64) :: expected_species(6),expected_mixing(6),expected_redistribution(6)
    REAL(real64) :: expected_dry,expected_total,expected_max,expected_enthalpy
    REAL(real64) :: enthalpy_scale,before(6),after(6),temperature_before,temperature_after
    REAL(real64) :: hb,ha,change(6),mb,ma,dm,geometry_mass,expected_mb,expected_ma
    REAL(real64) :: cell_scale,max_cell_scale,global_scale,residual_tolerance
    REAL(real64) :: cell_residual_tolerance
    INTEGER(int64) :: expected_accounted,expected_incomplete_background
    INTEGER(int64) :: expected_incomplete_candidate
    INTEGER :: i,j,k
    LOGICAL :: mass_oracle_ok

    expected_species=0.0_real64; expected_mixing=0.0_real64
    expected_redistribution=0.0_real64; expected_dry=0.0_real64; expected_max=0.0_real64
    expected_enthalpy=0.0_real64; enthalpy_scale=0.0_real64
    expected_accounted=0_int64; expected_incomplete_background=0_int64
    expected_incomplete_candidate=0_int64
    mass_oracle_ok=.TRUE.; max_cell_scale=0.0_real64; global_scale=0.0_real64
    DO k=1,background%grid%nz; DO j=1,background%grid%ny; DO i=1,background%grid%nx
      IF (.NOT.background%above_ground(i,j,k)) CYCLE
      expected_accounted=expected_accounted+1_int64
      before=raw_species(background,i,j,k); after=raw_species(candidate,i,j,k)
      mb=background%grid%dry_air_mass_measure(i,j,k)
      ma=candidate%grid%dry_air_mass_measure(i,j,k); dm=ma-mb
      geometry_mass=background%grid%pressure_mass_measure(i,j,k)
      expected_mb=geometry_mass/(1.0_real64+SUM(before))
      expected_ma=candidate%grid%pressure_mass_measure(i,j,k)/(1.0_real64+SUM(after))
      mass_oracle_ok=mass_oracle_ok .AND. close_scalar(mb,expected_mb) .AND. &
        close_scalar(ma,expected_ma)
      temperature_before=REAL(background%temperature%value(i,j,k),real64)
      temperature_after=REAL(candidate%temperature%value(i,j,k),real64)
      hb=raw_mixture_enthalpy(temperature_before,before)
      ha=raw_mixture_enthalpy(temperature_after,after)
      expected_enthalpy=expected_enthalpy+ma*ha-mb*hb
      enthalpy_scale=enthalpy_scale+ABS(ma*ha)+ABS(mb*hb)
      cell_scale=MAX(1.0_real64,geometry_mass,ABS(mb),ABS(ma))
      max_cell_scale=MAX(max_cell_scale,cell_scale); global_scale=global_scale+cell_scale
      change=ma*after-mb*before
      expected_species=expected_species+change
      expected_max=MAX(expected_max,ABS(dm+SUM(change)))
      expected_mixing=expected_mixing+mb*(after-before)
      expected_redistribution=expected_redistribution+dm*after
      expected_dry=expected_dry+dm
      IF (.NOT.ALL([background%vapor%valid(i,j,k),background%cloud_water%valid(i,j,k), &
          background%cloud_ice%valid(i,j,k),background%rain%valid(i,j,k), &
          background%snow%valid(i,j,k),background%graupel%valid(i,j,k)])) &
        expected_incomplete_background=expected_incomplete_background+1_int64
      IF (.NOT.ALL([candidate%vapor%valid(i,j,k),candidate%cloud_water%valid(i,j,k), &
          candidate%cloud_ice%valid(i,j,k),candidate%rain%valid(i,j,k), &
          candidate%snow%valid(i,j,k),candidate%graupel%valid(i,j,k)])) &
        expected_incomplete_candidate=expected_incomplete_candidate+1_int64
    END DO; END DO; END DO
    expected_total=expected_dry+SUM(expected_species)
    residual_tolerance=64.0_real64*EPSILON(1.0_real64)*MAX(1.0_real64,global_scale)
    cell_residual_tolerance=64.0_real64*EPSILON(1.0_real64)*MAX(1.0_real64,max_cell_scale)

    CALL check(actual%accounted_cells==expected_accounted, &
      TRIM(label)//' accounted-cell count',failures)
    CALL check(mass_oracle_ok,TRIM(label)//' pressure-geometry dry-mass oracle',failures)
    CALL check(actual%incomplete_background_cells==expected_incomplete_background .AND. &
      actual%incomplete_candidate_cells==expected_incomplete_candidate, &
      TRIM(label)//' incomplete-cell counts',failures)
    CALL check(close_vector(actual%species_change_kg,expected_species), &
      TRIM(label)//' species mass change',failures)
    CALL check(close_vector(actual%mixing_ratio_change_kg,expected_mixing), &
      TRIM(label)//' mixing-ratio contribution',failures)
    CALL check(close_vector(actual%dry_mass_redistribution_kg,expected_redistribution), &
      TRIM(label)//' dry-mass redistribution',failures)
    CALL check(close_scalar(actual%dry_air_change_kg,expected_dry), &
      TRIM(label)//' dry-air change',failures)
    CALL check(close_scaled_scalar(actual%enthalpy_change_j,expected_enthalpy,enthalpy_scale), &
      TRIM(label)//' signed BEFORE-thermo enthalpy increment',failures)
    CALL check(close_scalar(actual%total_mass_error_kg,expected_total), &
      TRIM(label)//' total mass error',failures)
    CALL check(close_scalar(actual%max_cell_mass_error_kg,expected_max), &
      TRIM(label)//' maximum raw-cell mass residual',failures)
    CALL check(close_vector(actual%species_change_kg, &
      actual%mixing_ratio_change_kg+actual%dry_mass_redistribution_kg), &
      TRIM(label)//' exact species decomposition',failures)
    CALL check(close_scalar(actual%total_mass_error_kg, &
      actual%dry_air_change_kg+SUM(actual%species_change_kg)), &
      TRIM(label)//' total closure',failures)
    CALL check(ABS(expected_total)<=residual_tolerance .AND. expected_max<=cell_residual_tolerance .AND. &
      ABS(actual%total_mass_error_kg)<=residual_tolerance .AND. &
      actual%max_cell_mass_error_kg<=cell_residual_tolerance, &
      TRIM(label)//' global and cell mass residuals are roundoff scale',failures)
  END SUBROUTINE check_analysis_budget

  PURE FUNCTION raw_mixture_enthalpy(temperature,species) RESULT(enthalpy)
    REAL(real64), INTENT(IN) :: temperature,species(6)
    REAL(real64) :: enthalpy
    enthalpy=(ORACLE_CPD+SUM(ORACLE_CP*species))*(temperature-ORACLE_T0)+ &
      SUM(ORACLE_H0*species)
  END FUNCTION raw_mixture_enthalpy

  SUBROUTINE check_composite_enthalpy(background,candidate,analysis_change,thermo_error, &
                                      failures,label)
    TYPE(cloud_bal_state_type), INTENT(IN) :: background,candidate
    REAL(real64), INTENT(IN) :: analysis_change,thermo_error
    INTEGER, INTENT(INOUT) :: failures
    CHARACTER(LEN=*), INTENT(IN) :: label
    REAL(real64) :: before(6),after(6),hb,ha,background_total,candidate_total
    REAL(real64) :: extensive_scale,mb,ma,temperature_before,temperature_after
    INTEGER :: i,j,k

    background_total=0.0_real64; candidate_total=0.0_real64
    extensive_scale=0.0_real64
    DO k=1,background%grid%nz; DO j=1,background%grid%ny; DO i=1,background%grid%nx
      IF (.NOT.background%above_ground(i,j,k)) CYCLE
      before=raw_species(background,i,j,k); after=raw_species(candidate,i,j,k)
      mb=background%grid%dry_air_mass_measure(i,j,k)
      ma=candidate%grid%dry_air_mass_measure(i,j,k)
      temperature_before=REAL(background%temperature%value(i,j,k),real64)
      temperature_after=REAL(candidate%temperature%value(i,j,k),real64)
      hb=raw_mixture_enthalpy(temperature_before,before)
      ha=raw_mixture_enthalpy(temperature_after,after)
      background_total=background_total+mb*hb
      candidate_total=candidate_total+ma*ha
      extensive_scale=extensive_scale+ABS(mb*hb)+ABS(ma*ha)
    END DO; END DO; END DO
    CALL check(close_scaled_scalar(candidate_total-background_total, &
      analysis_change+thermo_error,extensive_scale),TRIM(label),failures)
  END SUBROUTINE check_composite_enthalpy

  PURE FUNCTION raw_species(state,i,j,k) RESULT(species)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    INTEGER, INTENT(IN) :: i,j,k
    REAL(real64) :: species(6)
    species=0.0_real64
    species(1)=REAL(state%vapor%value(i,j,k),real64)
    ! Match the contract's usable-cell bits directly in this oracle.  Invalid
    ! hydrometeor values are deliberately omitted, never interpreted as zero
    ! observations; vapor is mandatory in a validated canonical state.
    IF (raw_water_usable(state%cloud_water%valid(i,j,k),state%cloud_water%quality(i,j,k), &
        state%cloud_water%source(i,j,k))) species(2)=REAL(state%cloud_water%value(i,j,k),real64)
    IF (raw_water_usable(state%cloud_ice%valid(i,j,k),state%cloud_ice%quality(i,j,k), &
        state%cloud_ice%source(i,j,k))) species(3)=REAL(state%cloud_ice%value(i,j,k),real64)
    IF (raw_water_usable(state%rain%valid(i,j,k),state%rain%quality(i,j,k), &
        state%rain%source(i,j,k))) species(4)=REAL(state%rain%value(i,j,k),real64)
    IF (raw_water_usable(state%snow%valid(i,j,k),state%snow%quality(i,j,k), &
        state%snow%source(i,j,k))) species(5)=REAL(state%snow%value(i,j,k),real64)
    IF (raw_water_usable(state%graupel%valid(i,j,k),state%graupel%quality(i,j,k), &
        state%graupel%source(i,j,k))) species(6)=REAL(state%graupel%value(i,j,k),real64)
  END FUNCTION raw_species

  PURE LOGICAL FUNCTION raw_water_usable(valid,quality,source)
    LOGICAL, INTENT(IN) :: valid
    INTEGER(int32), INTENT(IN) :: quality,source
    raw_water_usable=valid .AND. source>0_int32 .AND. &
      IAND(source,NOT(SOURCE_KNOWN_BITS))==0_int32 .AND. &
      IAND(quality,NOT(QUALITY_KNOWN_BITS))==0_int32 .AND. &
      IAND(quality,QUALITY_EXCLUDED_BITS)==0_int32
  END FUNCTION raw_water_usable

  PURE LOGICAL FUNCTION close_vector(left,right)
    REAL(real64), INTENT(IN) :: left(:),right(:)
    close_vector=SIZE(left)==SIZE(right) .AND. ALL(ABS(left-right)<=1.0e-7_real64+ &
      2.0e-12_real64*MAX(ABS(left),ABS(right)))
  END FUNCTION close_vector

  PURE LOGICAL FUNCTION close_scalar(left,right)
    REAL(real64), INTENT(IN) :: left,right
    close_scalar=ABS(left-right)<=1.0e-7_real64+2.0e-12_real64*MAX(ABS(left),ABS(right))
  END FUNCTION close_scalar

  PURE LOGICAL FUNCTION close_scaled_scalar(left,right,scale)
    REAL(real64), INTENT(IN) :: left,right,scale
    close_scaled_scalar=ABS(left-right)<=1.0e-7_real64+2.0e-12_real64*MAX(1.0_real64,scale)
  END FUNCTION close_scaled_scalar

  PURE LOGICAL FUNCTION analysis_budgets_equal(left,right)
    TYPE(pressure_analysis_budget), INTENT(IN) :: left,right
    analysis_budgets_equal=close_vector(left%species_change_kg,right%species_change_kg) .AND. &
      close_vector(left%mixing_ratio_change_kg,right%mixing_ratio_change_kg) .AND. &
      close_vector(left%dry_mass_redistribution_kg,right%dry_mass_redistribution_kg) .AND. &
      close_scalar(left%dry_air_change_kg,right%dry_air_change_kg) .AND. &
      close_scalar(left%enthalpy_change_j,right%enthalpy_change_j) .AND. &
      close_scalar(left%geometry_mass_change_kg,right%geometry_mass_change_kg) .AND. &
      close_scalar(left%enthalpy_composition_change_j,right%enthalpy_composition_change_j) .AND. &
      close_scalar(left%enthalpy_mass_metric_change_j,right%enthalpy_mass_metric_change_j) .AND. &
      close_scalar(left%total_mass_error_kg,right%total_mass_error_kg) .AND. &
      close_scalar(left%max_cell_mass_error_kg,right%max_cell_mass_error_kg) .AND. &
      left%accounted_cells==right%accounted_cells .AND. &
      left%incomplete_background_cells==right%incomplete_background_cells .AND. &
      left%incomplete_candidate_cells==right%incomplete_candidate_cells
  END FUNCTION analysis_budgets_equal

  PURE LOGICAL FUNCTION zero_analysis_budget(budget)
    TYPE(pressure_analysis_budget), INTENT(IN) :: budget
    zero_analysis_budget=ALL(budget%species_change_kg==0.0_real64) .AND. &
      ALL(budget%mixing_ratio_change_kg==0.0_real64) .AND. &
      ALL(budget%dry_mass_redistribution_kg==0.0_real64) .AND. &
      budget%dry_air_change_kg==0.0_real64 .AND. budget%enthalpy_change_j==0.0_real64 .AND. &
      budget%geometry_mass_change_kg==0.0_real64 .AND. &
      budget%enthalpy_composition_change_j==0.0_real64 .AND. &
      budget%enthalpy_mass_metric_change_j==0.0_real64 .AND. &
      budget%total_mass_error_kg==0.0_real64 .AND. &
      budget%max_cell_mass_error_kg==0.0_real64 .AND. &
      budget%accounted_cells==0_int64 .AND. budget%incomplete_background_cells==0_int64 .AND. &
      budget%incomplete_candidate_cells==0_int64
  END FUNCTION zero_analysis_budget

  PURE LOGICAL FUNCTION zero_thermo_budget(budget)
    TYPE(water_phase_budget), INTENT(IN) :: budget
    zero_thermo_budget=ALL(budget%species_change_kg==0.0_real64) .AND. &
      budget%sensible_change_j==0.0_real64 .AND. budget%phase_change_j==0.0_real64 .AND. &
      budget%water_error_kg==0.0_real64 .AND. budget%enthalpy_error_j==0.0_real64
  END FUNCTION zero_thermo_budget

  SUBROUTINE check(condition,message,count)
    LOGICAL,INTENT(IN) :: condition
    CHARACTER(LEN=*),INTENT(IN) :: message
    INTEGER,INTENT(INOUT) :: count
    IF (.NOT.condition) THEN
      count=count+1
      PRINT *,'FAIL: ',TRIM(message)
    END IF
  END SUBROUTINE check

  SUBROUTINE make_state(state,nz_requested)
    TYPE(cloud_bal_state_type),INTENT(OUT) :: state
    INTEGER, INTENT(IN), OPTIONAL :: nz_requested
    INTEGER :: i,j,k,status,nz
    REAL(real64) :: pressure_step
    nz=3
    IF (PRESENT(nz_requested)) nz=nz_requested
    pressure_step=15000.0_real64
    IF (nz>6) pressure_step=10000.0_real64
    CALL initialize_cloud_bal_state(state,4,4,nz,1788224400_int64,'pipeline-test',status)
    IF (status/=STATUS_OK) ERROR STOP 'state init'
    DO k=1,nz; DO j=1,4; DO i=1,4
      state%grid%dx(i,j)=2000.0_real64
      state%grid%dy(i,j)=2200.0_real64
      state%pressure%value(i,j,k)=REAL(95000.0_real64-pressure_step*REAL(k-1,real64),real32)
      state%temperature%value(i,j,k)=280.0_real32
      state%vapor%value(i,j,k)=0.008_real32
      state%u%value(i,j,k)=0.0_real32
      state%v%value(i,j,k)=0.0_real32
      state%omega%value(i,j,k)=0.0_real32
      state%geopotential%value(i,j,k)=1000.0_real32
      state%cloud_fraction%value(i,j,k)=0.0_real32
      state%cloud_type%value(i,j,k)=0_int32
    END DO; END DO; END DO
    CALL valid_real(state%pressure,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%temperature,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%vapor,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%u,SOURCE_ANALYZED_WIND)
    CALL valid_real(state%v,SOURCE_ANALYZED_WIND)
    CALL valid_real(state%omega,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%geopotential,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%cloud_fraction,SOURCE_CLOUD_ANALYSIS)
    state%cloud_type%valid=.TRUE.; state%cloud_type%quality=0_int32
    state%cloud_type%source=SOURCE_CLOUD_ANALYSIS
    state%surface_pressure%value=100000.0_real32
    state%surface_temperature%value=290.0_real32
    state%surface_pressure%valid=.TRUE.; state%surface_temperature%valid=.TRUE.
    state%surface_pressure%quality=0_int32; state%surface_temperature%quality=0_int32
    state%surface_pressure%source=SOURCE_BACKGROUND_MODEL
    state%surface_temperature%source=SOURCE_BACKGROUND_MODEL
    state%latitude%value=36.0_real32; state%latitude%valid=.TRUE.
    state%latitude%quality=0_int32; state%latitude%source=SOURCE_BACKGROUND_MODEL
    state%omega_top_boundary%value=0.0_real32
    state%omega_bottom_boundary%value=0.0_real32
    state%omega_top_boundary%valid=.TRUE.; state%omega_bottom_boundary%valid=.TRUE.
    state%omega_top_boundary%quality=0_int32; state%omega_bottom_boundary%quality=0_int32
    state%omega_top_boundary%source=SOURCE_BOUNDARY_CONDITION
    state%omega_bottom_boundary%source=SOURCE_BOUNDARY_CONDITION
    CALL configure_pressure_geometry(state,status)
    IF (status/=STATUS_OK) ERROR STOP 'pressure geometry initialization failed'
    CALL refresh_dry_air_mass_measure(state,status)
    IF (status/=STATUS_OK) ERROR STOP 'dry-air mass initialization failed'
  END SUBROUTINE make_state

  SUBROUTINE valid_real(field,source)
    TYPE(field3d),INTENT(INOUT) :: field
    INTEGER(int32),INTENT(IN) :: source
    field%valid=.TRUE.; field%quality=0_int32; field%source=source
  END SUBROUTINE valid_real

  SUBROUTINE make_complete_water_fields(state)
    TYPE(cloud_bal_state_type), INTENT(INOUT) :: state
    CALL valid_real(state%cloud_water,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%cloud_ice,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%rain,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%snow,SOURCE_BACKGROUND_MODEL)
    CALL valid_real(state%graupel,SOURCE_BACKGROUND_MODEL)
    state%cloud_water%value=0.0_real32
    state%cloud_ice%value=0.0_real32
    state%rain%value=0.0_real32
    state%snow%value=0.0_real32
    state%graupel%value=0.0_real32
  END SUBROUTINE make_complete_water_fields

  SUBROUTINE add_radar_cell(state)
    TYPE(cloud_bal_state_type),INTENT(INOUT) :: state
    state%radar_reflectivity%valid(2,2,3)=.TRUE.
    state%radar_reflectivity%quality(2,2,3)=0_int32
    state%radar_reflectivity%source(2,2,3)=SOURCE_RADAR_DBZ
    state%radar_reflectivity%value(2,2,3)=30.0_real32
  END SUBROUTINE add_radar_cell

  SUBROUTINE remove_cloud_analysis(state)
    TYPE(cloud_bal_state_type),INTENT(INOUT) :: state
    state%cloud_fraction%valid=.FALSE.
    state%cloud_fraction%quality=QUALITY_RAW_MISSING
    state%cloud_fraction%source=0_int32
    state%cloud_type%valid=.FALSE.
    state%cloud_type%quality=QUALITY_RAW_MISSING
    state%cloud_type%source=0_int32
  END SUBROUTINE remove_cloud_analysis

  SUBROUTINE remove_unused_surface_temperature(state)
    TYPE(cloud_bal_state_type),INTENT(INOUT) :: state
    state%surface_temperature%valid=.FALSE.
    state%surface_temperature%quality=QUALITY_RAW_MISSING
    state%surface_temperature%source=0_int32
  END SUBROUTINE remove_unused_surface_temperature

  SUBROUTINE invalidate_level(state,k)
    TYPE(cloud_bal_state_type),INTENT(INOUT) :: state
    INTEGER,INTENT(IN) :: k
    CALL invalidate_real_level(state%pressure,k)
    CALL invalidate_real_level(state%temperature,k)
    CALL invalidate_real_level(state%vapor,k)
    CALL invalidate_real_level(state%u,k)
    CALL invalidate_real_level(state%v,k)
    CALL invalidate_real_level(state%omega,k)
    CALL invalidate_real_level(state%geopotential,k)
  END SUBROUTINE invalidate_level

  SUBROUTINE invalidate_real_level(field,k)
    TYPE(field3d),INTENT(INOUT) :: field
    INTEGER,INTENT(IN) :: k
    field%valid(:,:,k)=.FALSE.
    field%quality(:,:,k)=QUALITY_RAW_MISSING
    field%source(:,:,k)=0_int32
  END SUBROUTINE invalidate_real_level

  LOGICAL FUNCTION same_pipeline_state(left,right)
    TYPE(cloud_bal_state_type),INTENT(IN) :: left,right
    INTEGER :: left_status,left_reason,right_status,right_reason
    same_pipeline_state=.FALSE.
    IF (left%radar_los%is_present .OR. right%radar_los%is_present) RETURN
    CALL validate_los_observations(left%radar_los,left%grid%nx,left%grid%ny, &
      left%grid%nz,left%pressure%valid_time,left_status,left_reason)
    CALL validate_los_observations(right%radar_los,right%grid%nx,right%grid%ny, &
      right%grid%nz,right%pressure%valid_time,right_status,right_reason)
    IF (left_status/=STATUS_OK .OR. right_status/=STATUS_OK .OR. &
        left_reason/=REASON_NONE .OR. right_reason/=REASON_NONE) RETURN
    same_pipeline_state=left%schema_version==right%schema_version .AND. &
      same_grid(left%grid,right%grid) .AND. &
      same_field(left%pressure,right%pressure) .AND. &
      same_field(left%temperature,right%temperature) .AND. &
      same_field(left%vapor,right%vapor) .AND. &
      same_field(left%u,right%u) .AND. same_field(left%v,right%v) .AND. &
      same_field(left%omega,right%omega) .AND. &
      same_field(left%omega_target,right%omega_target) .AND. &
      same_field(left%omega_target_sigma,right%omega_target_sigma) .AND. &
      same_field(left%geopotential,right%geopotential) .AND. &
      same_field(left%cloud_fraction,right%cloud_fraction) .AND. &
      same_field(left%radar_reflectivity,right%radar_reflectivity) .AND. &
      same_field(left%cloud_water,right%cloud_water) .AND. &
      same_field(left%cloud_ice,right%cloud_ice) .AND. &
      same_field(left%rain,right%rain) .AND. same_field(left%snow,right%snow) .AND. &
      same_field(left%graupel,right%graupel) .AND. &
      same_field(left%vt_z_mean,right%vt_z_mean) .AND. &
      same_field(left%vt_z_sigma,right%vt_z_sigma) .AND. &
      same_integer_field(left%cloud_type,right%cloud_type) .AND. &
      same_integer_field(left%precipitation_phase,right%precipitation_phase) .AND. &
      same_integer_field(left%lightning_support,right%lightning_support) .AND. &
      same_surface_field(left%surface_pressure,right%surface_pressure) .AND. &
      same_surface_field(left%surface_temperature,right%surface_temperature) .AND. &
      same_surface_field(left%latitude,right%latitude) .AND. &
      same_surface_field(left%omega_top_boundary,right%omega_top_boundary) .AND. &
      same_surface_field(left%omega_bottom_boundary,right%omega_bottom_boundary) .AND. &
      ALL(left%above_ground.EQV.right%above_ground) .AND. &
      ALL(left%obs_support==right%obs_support) .AND. &
      ALL(left%hydro_support==right%hydro_support) .AND. &
      same_real_values(left%balance_beta,right%balance_beta)
  END FUNCTION same_pipeline_state

  LOGICAL FUNCTION same_grid(left,right)
    TYPE(grid_spec),INTENT(IN) :: left,right
    INTEGER(int64),ALLOCATABLE :: a(:),b(:)
    same_grid=.FALSE.
    IF (left%nx/=right%nx .OR. left%ny/=right%ny .OR. left%nz/=right%nz .OR. &
        left%grid_id/=right%grid_id) RETURN
    a=TRANSFER(left%dx,[0_int64],SIZE(left%dx))
    b=TRANSFER(right%dx,[0_int64],SIZE(right%dx))
    IF (.NOT.ALL(a==b)) RETURN
    a=TRANSFER(left%dy,[0_int64],SIZE(left%dy))
    b=TRANSFER(right%dy,[0_int64],SIZE(right%dy))
    IF (.NOT.ALL(a==b)) RETURN
    a=TRANSFER(left%cell_dp,[0_int64],SIZE(left%cell_dp))
    b=TRANSFER(right%cell_dp,[0_int64],SIZE(right%cell_dp))
    IF (.NOT.ALL(a==b)) RETURN
    a=TRANSFER(left%pressure_interface,[0_int64],SIZE(left%pressure_interface))
    b=TRANSFER(right%pressure_interface,[0_int64],SIZE(right%pressure_interface))
    IF (.NOT.ALL(a==b)) RETURN
    a=TRANSFER(left%level_spacing_dp,[0_int64],SIZE(left%level_spacing_dp))
    b=TRANSFER(right%level_spacing_dp,[0_int64],SIZE(right%level_spacing_dp))
    IF (.NOT.ALL(a==b)) RETURN
    a=TRANSFER(left%pressure_mass_measure,[0_int64],SIZE(left%pressure_mass_measure))
    b=TRANSFER(right%pressure_mass_measure,[0_int64],SIZE(right%pressure_mass_measure))
    same_grid=ALL(a==b)
    IF (.NOT.same_grid) RETURN
    a=TRANSFER(left%dry_air_mass_measure,[0_int64],SIZE(left%dry_air_mass_measure))
    b=TRANSFER(right%dry_air_mass_measure,[0_int64],SIZE(right%dry_air_mass_measure))
    same_grid=ALL(a==b)
  END FUNCTION same_grid

  LOGICAL FUNCTION same_field(left,right)
    TYPE(field3d),INTENT(IN) :: left,right
    same_field=same_real_values(left%value,right%value) .AND. &
      ALL(left%valid.EQV.right%valid) .AND. &
      ALL(left%quality==right%quality) .AND. ALL(left%source==right%source) .AND. &
      left%valid_time==right%valid_time .AND. left%unit==right%unit
  END FUNCTION same_field

  LOGICAL FUNCTION same_surface_field(left,right)
    TYPE(field2d),INTENT(IN) :: left,right
    INTEGER(int32),ALLOCATABLE :: a(:),b(:)
    a=TRANSFER(left%value,[0_int32],SIZE(left%value))
    b=TRANSFER(right%value,[0_int32],SIZE(right%value))
    same_surface_field=ALL(a==b) .AND. ALL(left%valid.EQV.right%valid) .AND. &
      ALL(left%quality==right%quality) .AND. ALL(left%source==right%source) .AND. &
      left%valid_time==right%valid_time .AND. left%unit==right%unit
  END FUNCTION same_surface_field

  LOGICAL FUNCTION same_integer_field(left,right)
    TYPE(integer_field3d),INTENT(IN) :: left,right
    same_integer_field=ALL(left%value==right%value) .AND. &
      ALL(left%valid.EQV.right%valid) .AND. &
      ALL(left%quality==right%quality) .AND. ALL(left%source==right%source) .AND. &
      left%valid_time==right%valid_time .AND. left%code_table==right%code_table
  END FUNCTION same_integer_field

  LOGICAL FUNCTION same_real_values(left,right)
    REAL(real32),INTENT(IN) :: left(:,:,:),right(:,:,:)
    INTEGER(int32),ALLOCATABLE :: a(:),b(:)
    a=TRANSFER(left,[0_int32],SIZE(left))
    b=TRANSFER(right,[0_int32],SIZE(right))
    same_real_values=ALL(a==b)
  END FUNCTION same_real_values

END PROGRAM test_pipeline
