PROGRAM test_pipeline
  USE, INTRINSIC :: iso_fortran_env,ONLY: real32,real64,int32,int64
  USE cloud_bal_state
  USE cloud_bal_column_physics,ONLY: derive_column_physics
  USE cloud_bal_balance_operator,ONLY: TARGET_AUTHORITY_OBSERVATIONAL, &
    TARGET_AUTHORITY_MANUFACTURED_TEST
  USE cloud_bal_pipeline
  IMPLICIT NONE
  TYPE(cloud_bal_state_type) :: input,candidate,operational,column_candidate
  TYPE(cloud_bal_pipeline_config) :: config
  TYPE(cloud_bal_pipeline_result) :: result
  INTEGER :: failures,status
  REAL(real64) :: saved_minimum_target_response_ratio

  failures=0
  CALL make_state(input)
  config%requested_mode=MODE_OFF
  CALL run_cloud_bal_pipeline(input,candidate,operational,result,config)
  CALL check(result%status==STATUS_OK,'OFF must be a successful no-op',failures)
  CALL check(same_pipeline_state(input,operational), &
             'OFF must preserve operational state',failures)

  CALL add_radar_cell(input)
  config%requested_mode=MODE_SHADOW
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

  CALL make_state(input)
  CALL remove_cloud_analysis(input)
  CALL remove_unused_surface_temperature(input)
  CALL add_radar_cell(input)
  CALL run_cloud_bal_pipeline(input,candidate,operational,result,config)
  CALL check(result%status==STATUS_OK .AND. result%column%status==STATUS_OK .AND. &
             result%balance%numerical%solver_reason==SOLVER_NOT_RUN, &
             'radar-only input must remain a hydrometeor-only proposal',failures)
  CALL check(same_pipeline_state(input,operational), &
             'radar-only SHADOW must not change operational state',failures)

  CALL make_state(input)
  input%omega_target%value(2,2,3)=0.08_real32
  input%omega_target%valid(2,2,3)=.TRUE.
  input%omega_target%quality(2,2,3)=0_int32
  input%omega_target%source(2,2,3)= &
    IOR(SOURCE_CONVENTIONAL_OBS,SOURCE_DYNAMIC_TARGET)
  CALL run_cloud_bal_pipeline(input,candidate,operational,result,config)
  CALL check(result%status==STATUS_OK .AND. &
             result%balance%numerical%solver_reason==SOLVER_CONVERGED .AND. &
             ANY(candidate%balance_beta>0.0_real32), &
             'an explicit trusted dynamic target must reach the solver',failures)
  CALL check(same_pipeline_state(input,operational), &
             'trusted SHADOW target still cannot change operational state',failures)

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

  IF (failures/=0) THEN
    PRINT *,'Pipeline tests failed:',failures
    ERROR STOP 1
  END IF
  PRINT *,'Cloud-BAL pipeline authority tests passed'

CONTAINS

  SUBROUTINE check(condition,message,count)
    LOGICAL,INTENT(IN) :: condition
    CHARACTER(LEN=*),INTENT(IN) :: message
    INTEGER,INTENT(INOUT) :: count
    IF (.NOT.condition) THEN
      count=count+1
      PRINT *,'FAIL: ',TRIM(message)
    END IF
  END SUBROUTINE check

  SUBROUTINE make_state(state)
    TYPE(cloud_bal_state_type),INTENT(OUT) :: state
    INTEGER :: i,j,k,status
    CALL initialize_cloud_bal_state(state,4,4,3,1788224400_int64,'pipeline-test',status)
    IF (status/=STATUS_OK) ERROR STOP 'state init'
    DO k=1,3; DO j=1,4; DO i=1,4
      state%grid%dx(i,j)=2000.0_real64
      state%grid%dy(i,j)=2200.0_real64
      state%pressure%value(i,j,k)=REAL(95000-15000*(k-1),real32)
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
