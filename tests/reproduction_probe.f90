PROGRAM reproduction_probe
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32,int64
  USE cloud_bal_state
  USE cloud_bal_balance_operator, ONLY: balance_beta_active
  USE cloud_bal_pipeline
  IMPLICIT NONE

  TYPE(cloud_bal_state_type) :: input,candidate,operational
  TYPE(cloud_bal_pipeline_config) :: config
  TYPE(cloud_bal_pipeline_result) :: result
  INTEGER :: failures,off_candidate_differences,off_operational_differences

  failures=0
  WRITE(*,'(A)') 'experiment=cloud_bal_reproduction_v2'
  WRITE(*,'(A)') 'fixture=synthetic_4x4x3_sband_reflectivity_no_radar_los'

  CALL make_state(input)
  config%requested_mode=MODE_OFF
  CALL run_cloud_bal_pipeline(input,candidate,operational,result,config)
  off_candidate_differences=core_value_differences(input,candidate)
  off_operational_differences=core_value_differences(input,operational)
  CALL metric_integer('off_status',result%status)
  CALL metric_integer('off_candidate_core_value_differences', &
                      off_candidate_differences)
  CALL metric_integer('off_operational_core_value_differences', &
                      off_operational_differences)
  CALL require(result%status==STATUS_OK,'OFF status',failures)
  CALL require(off_candidate_differences==0 .AND. &
               off_operational_differences==0,'OFF core-value no-op',failures)

  CALL add_radar_cell(input)
  config%requested_mode=MODE_SHADOW
  config%horizontal_support_radius_m=5000.0_real64
  config%balance%required_residual_fraction=0.50_real64
  config%balance%minimum_target_response_ratio=0.0_real64
  config%balance%maximum_target_response_ratio=100.0_real64
  config%balance%geostrophic_absolute_tolerance=1.0_real64
  CALL run_cloud_bal_pipeline(input,candidate,operational,result,config)
  CALL report_shadow(input,candidate,operational,result,config,failures)

  CALL metric_integer('failure_count',failures)
  IF (failures/=0) ERROR STOP 1

CONTAINS

  SUBROUTINE report_shadow(background,shadow,operational,pipeline,settings, &
                           failure_count)
    TYPE(cloud_bal_state_type), INTENT(IN) :: background,shadow,operational
    TYPE(cloud_bal_pipeline_result), INTENT(IN) :: pipeline
    TYPE(cloud_bal_pipeline_config), INTENT(IN) :: settings
    INTEGER, INTENT(INOUT) :: failure_count
    REAL(real64) :: outside_wind,outside_omega,residual_ratio
    INTEGER :: candidate_differences,operational_differences

    candidate_differences=core_value_differences(background,shadow)
    operational_differences=core_value_differences(background,operational)
    outside_wind=maximum_outside_wind_increment(background,shadow, &
      settings%balance%minimum_beta)
    outside_omega=maximum_outside_omega_increment(background,shadow, &
      settings%balance%minimum_beta)
    residual_ratio=0.0_real64
    IF (pipeline%balance%numerical%continuity_proposed_increment_rms>0.0_real64) &
      residual_ratio=pipeline%balance%numerical%continuity_projected_increment_rms/ &
                     pipeline%balance%numerical%continuity_proposed_increment_rms

    CALL metric_integer('shadow_status',pipeline%status)
    CALL metric_integer('shadow_column_status',pipeline%column%status)
    CALL metric_integer('shadow_balance_status',pipeline%balance%status)
    CALL metric_integer('shadow_acceptance_failures', &
                        pipeline%balance%numerical%acceptance_failures)
    CALL metric_integer('shadow_operational_core_value_differences', &
                        operational_differences)
    CALL metric_integer('shadow_candidate_core_value_differences', &
                        candidate_differences)
    CALL metric_integer('shadow_changed_cells',COUNT(pipeline%overall%changed))
    CALL metric_integer('shadow_positive_beta_cells', &
                        COUNT(shadow%balance_beta>0.0_real32))
    CALL metric_integer('shadow_active_support_cells',COUNT(balance_beta_active( &
      shadow%balance_beta,settings%balance%minimum_beta)))
    CALL metric_integer('shadow_hydrometeor_cells', &
                        COUNT(shadow%hydro_support==1_int32))
    CALL metric_real('shadow_max_horizontal_wind_increment_ms', &
                     pipeline%balance%numerical%max_wind_increment)
    CALL metric_real('shadow_max_omega_increment_pas', &
                     pipeline%balance%numerical%max_omega_increment)
    CALL metric_real('shadow_target_response_failure_fraction', &
                     pipeline%balance%numerical%target_response_failure_fraction)
    CALL metric_real('shadow_outside_active_support_wind_increment_ms',outside_wind)
    CALL metric_real('shadow_outside_active_support_omega_increment_pas',outside_omega)
    CALL metric_real('active_support_internal_face_continuity_background_rms', &
                     pipeline%balance%numerical%continuity_background_rms)
    CALL metric_real('proposed_increment_continuity_rms', &
                     pipeline%balance%numerical%continuity_proposed_increment_rms)
    CALL metric_real('projected_increment_continuity_rms', &
                     pipeline%balance%numerical%continuity_projected_increment_rms)
    CALL metric_real( &
      'active_support_internal_face_continuity_final_to_forced_ratio', &
      residual_ratio)
    CALL metric_real('radar_interface_flux_input', &
                     pipeline%column%numerical%flux_input)
    CALL metric_real('radar_interface_flux_deposited', &
                     pipeline%column%numerical%flux_deposited)
    CALL metric_real('radar_interface_flux_boundary_exit', &
                     pipeline%column%numerical%flux_boundary_exit)
    CALL metric_real('radar_interface_flux_ledger_error', &
                     pipeline%column%numerical%ledger_error)

    CALL require(pipeline%status==STATUS_OK .AND. &
      pipeline%balance%numerical%solver_reason==SOLVER_NOT_RUN, &
      'uncertain radar target has no wind authority',failure_count)
    CALL require(operational_differences==0,'SHADOW operational core values', &
                 failure_count)
    CALL require(candidate_differences>0,'SHADOW hydrometeor proposal calculation', &
                 failure_count)
    CALL require(.NOT.ANY(shadow%balance_beta>0.0_real32), &
                 'uncertain target has zero balance support',failure_count)
    CALL require(outside_wind<=TINY(1.0_real64) .AND. &
                 outside_omega<=TINY(1.0_real64), &
                 'SHADOW active-support localization',failure_count)
    CALL require(pipeline%column%numerical%ledger_error<= &
      settings%column%ledger_absolute_tolerance+ &
      settings%column%ledger_relative_tolerance* &
      pipeline%column%numerical%flux_input,'radar ledger closure',failure_count)
  END SUBROUTINE report_shadow

  SUBROUTINE make_state(state)
    TYPE(cloud_bal_state_type), INTENT(OUT) :: state
    INTEGER :: i,j,k,status

    CALL initialize_cloud_bal_state(state,4,4,3,1788224400_int64, &
                                    'reproduction-grid',status)
    IF (status/=STATUS_OK) ERROR STOP 'state initialization failed'
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
    CALL make_valid(state%pressure,SOURCE_BACKGROUND_MODEL)
    CALL make_valid(state%temperature,SOURCE_BACKGROUND_MODEL)
    CALL make_valid(state%vapor,SOURCE_BACKGROUND_MODEL)
    CALL make_valid(state%u,SOURCE_ANALYZED_WIND)
    CALL make_valid(state%v,SOURCE_ANALYZED_WIND)
    CALL make_valid(state%omega,SOURCE_BACKGROUND_MODEL)
    CALL make_valid(state%geopotential,SOURCE_BACKGROUND_MODEL)
    CALL make_valid(state%cloud_fraction,SOURCE_CLOUD_ANALYSIS)
    state%cloud_type%valid=.TRUE.; state%cloud_type%quality=0_int32
    state%cloud_type%source=SOURCE_CLOUD_ANALYSIS
    state%surface_pressure%value=100000.0_real32
    state%surface_temperature%value=290.0_real32
    state%surface_pressure%valid=.TRUE.; state%surface_temperature%valid=.TRUE.
    state%surface_pressure%quality=0_int32
    state%surface_temperature%quality=0_int32
    state%surface_pressure%source=SOURCE_BACKGROUND_MODEL
    state%surface_temperature%source=SOURCE_BACKGROUND_MODEL
    state%latitude%value=36.0_real32; state%latitude%valid=.TRUE.
    state%latitude%quality=0_int32; state%latitude%source=SOURCE_BACKGROUND_MODEL
    state%omega_top_boundary%value=0.0_real32
    state%omega_bottom_boundary%value=0.0_real32
    state%omega_top_boundary%valid=.TRUE.
    state%omega_bottom_boundary%valid=.TRUE.
    state%omega_top_boundary%quality=0_int32
    state%omega_bottom_boundary%quality=0_int32
    state%omega_top_boundary%source=SOURCE_BOUNDARY_CONDITION
    state%omega_bottom_boundary%source=SOURCE_BOUNDARY_CONDITION
    CALL configure_pressure_geometry(state,status)
    IF (status/=STATUS_OK) ERROR STOP 'pressure geometry initialization failed'
    CALL refresh_dry_air_mass_measure(state,status)
    IF (status/=STATUS_OK) ERROR STOP 'dry-air mass initialization failed'
  END SUBROUTINE make_state

  SUBROUTINE make_valid(field,source)
    TYPE(field3d), INTENT(INOUT) :: field
    INTEGER(int32), INTENT(IN) :: source
    field%valid=.TRUE.; field%quality=0_int32; field%source=source
  END SUBROUTINE make_valid

  SUBROUTINE add_radar_cell(state)
    TYPE(cloud_bal_state_type), INTENT(INOUT) :: state
    state%radar_reflectivity%valid(2,2,3)=.TRUE.
    state%radar_reflectivity%quality(2,2,3)=0_int32
    state%radar_reflectivity%source(2,2,3)=SOURCE_RADAR_DBZ
    state%radar_reflectivity%value(2,2,3)=30.0_real32
  END SUBROUTINE add_radar_cell

  INTEGER FUNCTION core_value_differences(left,right)
    TYPE(cloud_bal_state_type), INTENT(IN) :: left,right
    core_value_differences=real_value_differences(left%u%value,right%u%value)+ &
      real_value_differences(left%v%value,right%v%value)+ &
      real_value_differences(left%omega%value,right%omega%value)+ &
      real_value_differences(left%rain%value,right%rain%value)+ &
      real_value_differences(left%snow%value,right%snow%value)+ &
      real_value_differences(left%graupel%value,right%graupel%value)
  END FUNCTION core_value_differences

  INTEGER FUNCTION real_value_differences(left,right)
    REAL(real32), INTENT(IN) :: left(:,:,:),right(:,:,:)
    INTEGER(int32), ALLOCATABLE :: left_bits(:),right_bits(:)
    left_bits=TRANSFER(left,[0_int32],SIZE(left))
    right_bits=TRANSFER(right,[0_int32],SIZE(right))
    real_value_differences=COUNT(left_bits/=right_bits)
  END FUNCTION real_value_differences

  REAL(real64) FUNCTION maximum_outside_wind_increment(background,shadow, &
                                                        minimum_beta)
    TYPE(cloud_bal_state_type), INTENT(IN) :: background,shadow
    REAL(real64), INTENT(IN) :: minimum_beta
    LOGICAL :: outside(background%grid%nx,background%grid%ny,background%grid%nz)
    outside=.NOT.balance_beta_active(shadow%balance_beta,minimum_beta)
    maximum_outside_wind_increment=0.0_real64
    IF (ANY(outside)) maximum_outside_wind_increment=MAX( &
      MAXVAL(ABS(REAL(shadow%u%value,real64)-REAL(background%u%value,real64)), &
             MASK=outside), &
      MAXVAL(ABS(REAL(shadow%v%value,real64)-REAL(background%v%value,real64)), &
             MASK=outside))
  END FUNCTION maximum_outside_wind_increment

  REAL(real64) FUNCTION maximum_outside_omega_increment(background,shadow, &
                                                         minimum_beta)
    TYPE(cloud_bal_state_type), INTENT(IN) :: background,shadow
    REAL(real64), INTENT(IN) :: minimum_beta
    LOGICAL :: outside(background%grid%nx,background%grid%ny,background%grid%nz)
    outside=.NOT.balance_beta_active(shadow%balance_beta,minimum_beta)
    maximum_outside_omega_increment=0.0_real64
    IF (ANY(outside)) maximum_outside_omega_increment=MAXVAL(ABS( &
      REAL(shadow%omega%value,real64)-REAL(background%omega%value,real64)), &
      MASK=outside)
  END FUNCTION maximum_outside_omega_increment

  SUBROUTINE require(condition,label,failure_count)
    LOGICAL, INTENT(IN) :: condition
    CHARACTER(LEN=*), INTENT(IN) :: label
    INTEGER, INTENT(INOUT) :: failure_count
    IF (.NOT.condition) THEN
      failure_count=failure_count+1
      WRITE(*,'(A)') 'failed_check='//TRIM(label)
    END IF
  END SUBROUTINE require

  SUBROUTINE metric_integer(name,value)
    CHARACTER(LEN=*), INTENT(IN) :: name
    INTEGER, INTENT(IN) :: value
    WRITE(*,'(A,"=",I0)') TRIM(name),value
  END SUBROUTINE metric_integer

  SUBROUTINE metric_real(name,value)
    CHARACTER(LEN=*), INTENT(IN) :: name
    REAL(real64), INTENT(IN) :: value
    WRITE(*,'(A,"=",ES24.16E3)') TRIM(name),value
  END SUBROUTINE metric_real

END PROGRAM reproduction_probe
