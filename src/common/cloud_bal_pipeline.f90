! Single authority boundary for the canonical Cloud-BAL pipeline.
MODULE cloud_bal_pipeline
  USE, INTRINSIC :: iso_fortran_env,ONLY: int64,real32,real64
  USE, INTRINSIC :: ieee_arithmetic,ONLY: ieee_is_finite
  USE cloud_bal_state
  USE cloud_bal_column_physics
  USE cloud_bal_balance_operator
  USE cloud_bal_grid_geometry,ONLY: bounded_grid_radius,cumulative_horizontal_distance
  IMPLICIT NONE
  PRIVATE

  TYPE, PUBLIC :: cloud_bal_pipeline_config
    INTEGER :: requested_mode=MODE_OFF
    REAL(real64) :: horizontal_support_radius_m=12000.0_real64
    REAL(real64) :: pressure_support_radius_pa=30000.0_real64
    TYPE(column_physics_config) :: column
    TYPE(balance_operator_config) :: balance
    ! One preserves the legacy single pass; larger values request a fixed point.
    INTEGER :: maximum_outer_iterations=1
  END TYPE cloud_bal_pipeline_config

  TYPE, PUBLIC :: cloud_bal_pipeline_result
    INTEGER :: status=STATUS_FAILED
    INTEGER :: reason_code=REASON_NONE
    INTEGER :: requested_mode=MODE_OFF
    TYPE(stage_result) :: column
    TYPE(stage_result) :: geopotential
    TYPE(stage_result) :: balance
    TYPE(stage_result) :: overall
    TYPE(water_phase_budget) :: thermo_budget
    TYPE(pressure_analysis_budget) :: analysis_budget
    TYPE(pressure_analysis_budget) :: geometry_budget
    REAL(real64), ALLOCATABLE :: requested_surface_pressure(:,:)
    TYPE(cloud_bal_state_type), ALLOCATABLE :: pressure_transition_seed
    LOGICAL, ALLOCATABLE :: thermo_support(:,:,:)
    INTEGER, ALLOCATABLE :: thermo_surface(:,:,:)
    LOGICAL, ALLOCATABLE :: geopotential_support(:,:,:)
    INTEGER, ALLOCATABLE :: geopotential_reference_level(:,:)
    REAL(real64) :: thermo_target_rh=1.0_real64
    INTEGER :: outer_iterations=0
    LOGICAL :: outer_converged=.FALSE.
    ! Per-trial max absolute changes: T, rv, u, v, omega (not a mixed-unit norm).
    REAL(real64) :: outer_max_abs_delta(5,32)=0.0_real64
  END TYPE cloud_bal_pipeline_result

  PUBLIC :: run_cloud_bal_pipeline
  PUBLIC :: build_compact_balance_beta
  PUBLIC :: restore_pre_balance_winds

CONTAINS

  SUBROUTINE restore_pre_balance_winds(candidate,original,state_out,status,transition_seed)
    ! Build only the wind payload that existed immediately before balance.
    ! Candidate owns the final geometry/support and every non-wind field.
    ! This is a diagnostic snapshot; it never publishes authority metadata.
    TYPE(cloud_bal_state_type), INTENT(IN) :: candidate,original
    TYPE(cloud_bal_state_type), INTENT(OUT) :: state_out
    INTEGER, INTENT(OUT) :: status
    TYPE(cloud_bal_state_type), INTENT(IN), OPTIONAL :: transition_seed
    LOGICAL, ALLOCATABLE :: old_active(:,:,:),new_active(:,:,:)
    INTEGER :: nx,ny,nz,allocation_status,shape3(3)

    ! Preserve the atomic failure contract even for malformed input states.
    state_out=candidate
    status=STATUS_FAILED
    nx=candidate%grid%nx; ny=candidate%grid%ny; nz=candidate%grid%nz
    shape3=(/nx,ny,nz/)
    IF (nx<1 .OR. ny<1 .OR. nz<1) RETURN
    IF (original%grid%nx/=nx .OR. original%grid%ny/=ny .OR. original%grid%nz/=nz) RETURN
    IF (.NOT.ALLOCATED(candidate%above_ground) .OR. .NOT.ALLOCATED(original%above_ground)) RETURN
    IF (ANY(SHAPE(candidate%above_ground)/=(/nx,ny,nz/)) .OR. &
        ANY(SHAPE(original%above_ground)/=(/nx,ny,nz/))) RETURN
    IF (.NOT.field_arrays_match(candidate%u,shape3) .OR. &
        .NOT.field_arrays_match(candidate%v,shape3) .OR. &
        .NOT.field_arrays_match(candidate%omega,shape3) .OR. &
        .NOT.field_arrays_match(original%u,shape3) .OR. &
        .NOT.field_arrays_match(original%v,shape3) .OR. &
        .NOT.field_arrays_match(original%omega,shape3)) RETURN
    ! A transition may expose cells, but it may not remove an old active cell.
    IF (ANY(original%above_ground .AND. .NOT.candidate%above_ground)) RETURN

    ALLOCATE(old_active(nx,ny,nz),new_active(nx,ny,nz),STAT=allocation_status)
    IF (allocation_status/=0) RETURN
    old_active=candidate%above_ground .AND. original%above_ground
    new_active=candidate%above_ground .AND. .NOT.original%above_ground

    IF (ANY(old_active .AND. (.NOT.ieee_is_finite(original%u%value) .OR. &
        .NOT.ieee_is_finite(original%v%value) .OR. &
        .NOT.ieee_is_finite(original%omega%value)))) RETURN
    IF (ANY(new_active)) THEN
      IF (.NOT.PRESENT(transition_seed)) RETURN
      IF (.NOT.ALLOCATED(transition_seed%above_ground)) RETURN
      IF (ANY(SHAPE(transition_seed%above_ground)/=shape3)) RETURN
      IF (.NOT.field_arrays_match(transition_seed%u,shape3) .OR. &
          .NOT.field_arrays_match(transition_seed%v,shape3) .OR. &
          .NOT.field_arrays_match(transition_seed%omega,shape3)) RETURN
      IF (ANY(new_active .AND. .NOT.transition_seed%above_ground)) RETURN
      IF (ANY(new_active .AND. .NOT.cell_is_usable(transition_seed%u%valid, &
          transition_seed%u%quality,transition_seed%u%source))) RETURN
      IF (ANY(new_active .AND. .NOT.cell_is_usable(transition_seed%v%valid, &
          transition_seed%v%quality,transition_seed%v%source))) RETURN
      IF (ANY(new_active .AND. .NOT.cell_is_usable(transition_seed%omega%valid, &
          transition_seed%omega%quality,transition_seed%omega%source))) RETURN
      IF (ANY(new_active .AND. (.NOT.ieee_is_finite(transition_seed%u%value) .OR. &
          .NOT.ieee_is_finite(transition_seed%v%value) .OR. &
          .NOT.ieee_is_finite(transition_seed%omega%value)))) RETURN
    END IF

    ! Copy values only.  Candidate metadata remains authoritative for the
    ! diagnostic operator, so this cannot grant observed or target authority.
    WHERE(old_active)
      state_out%u%value=original%u%value
      state_out%v%value=original%v%value
      state_out%omega%value=original%omega%value
    END WHERE
    IF (ANY(new_active)) THEN
      WHERE(new_active)
        state_out%u%value=transition_seed%u%value
        state_out%v%value=transition_seed%v%value
        state_out%omega%value=transition_seed%omega%value
      END WHERE
    END IF
    status=STATUS_OK
  END SUBROUTINE restore_pre_balance_winds

  SUBROUTINE run_cloud_bal_pipeline(state_in,candidate_out,operational_out, &
                                    result,config,thermo_active,thermo_surface,target_rh, &
                                    geopotential_support,geopotential_reference_level,requested_surface_pressure, &
                                    pressure_transition_seed)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state_in
    TYPE(cloud_bal_state_type), INTENT(OUT) :: candidate_out,operational_out
    TYPE(cloud_bal_pipeline_result), INTENT(OUT) :: result
    TYPE(cloud_bal_pipeline_config), INTENT(IN) :: config
    LOGICAL, INTENT(IN), OPTIONAL :: thermo_active(:,:,:)
    INTEGER, INTENT(IN), OPTIONAL :: thermo_surface(:,:,:)
    REAL(real64), INTENT(IN), OPTIONAL :: target_rh
    LOGICAL, INTENT(IN), OPTIONAL :: geopotential_support(:,:,:)
    INTEGER, INTENT(IN), OPTIONAL :: geopotential_reference_level(:,:)
    ! Explicit prescribed-pressure research step, not an observational target
    ! or a solved native mass constraint. The caller owns its target contract.
    REAL(real64), INTENT(IN), OPTIONAL :: requested_surface_pressure(:,:)
    TYPE(cloud_bal_state_type), INTENT(IN), OPTIONAL :: pressure_transition_seed
    TYPE(cloud_bal_state_type) :: column_candidate,geopotential_candidate,balance_candidate,evaluation
    TYPE(cloud_bal_state_type) :: transition_prior,transition_candidate
    TYPE(stage_result) :: transition_result
    TYPE(pressure_analysis_budget) :: proposal_budget,geometry_budget
    REAL(real64), ALLOCATABLE :: first_stage_pressure(:,:)
    INTEGER :: nx,ny,nz,localization_status,shape3(3),iteration,i,j,k

    nx=state_in%grid%nx; ny=state_in%grid%ny; nz=state_in%grid%nz
    shape3=(/nx,ny,nz/)
    candidate_out=state_in; operational_out=state_in
    result%requested_mode=config%requested_mode
    result%outer_iterations=0; result%outer_converged=.FALSE.
    result%outer_max_abs_delta=0.0_real64
    result%thermo_budget=water_phase_budget()
    result%analysis_budget=pressure_analysis_budget()
    result%geometry_budget=pressure_analysis_budget()
    CALL initialize_stage_result(result%column,MAX(0,nx),MAX(0,ny),MAX(0,nz), &
                                 STATUS_OK,REASON_NONE)
    CALL initialize_stage_result(result%geopotential,MAX(0,nx),MAX(0,ny),MAX(0,nz), &
                                 STATUS_OK,REASON_NONE)
    CALL initialize_stage_result(result%balance,MAX(0,nx),MAX(0,ny),MAX(0,nz), &
                                 STATUS_OK,REASON_NONE)
    CALL initialize_stage_result(result%overall,MAX(0,nx),MAX(0,ny),MAX(0,nz), &
                                 STATUS_FAILED,REASON_AUTHORITY)

    IF (.NOT.pipeline_mode_valid(config%requested_mode)) THEN
      result%status=STATUS_FAILED; result%reason_code=REASON_AUTHORITY
      RETURN
    END IF
    ! OFF is an exact no-op.  In particular it never inspects or interprets a
    ! target driver, so enabling this branch cannot alter legacy OFF behavior.
    IF (config%requested_mode==MODE_OFF) THEN
      CALL initialize_stage_result(result%overall,MAX(0,nx),MAX(0,ny),MAX(0,nz), &
                                   STATUS_OK,REASON_NONE)
      result%status=STATUS_OK; result%reason_code=REASON_NONE
      RETURN
    END IF
    ! Manufactured targets are a direct operator test capability.  They may
    ! never enter the normal OFF/SHADOW science pipeline.
    IF (config%balance%target_authority/=TARGET_AUTHORITY_OBSERVATIONAL .AND. &
        config%balance%target_authority/=TARGET_AUTHORITY_MODEL_DYNAMICS) THEN
      result%status=STATUS_FAILED; result%reason_code=REASON_AUTHORITY
      RETURN
    END IF
    IF (ALLOCATED(state_in%omega_target%valid) .OR. &
        ALLOCATED(state_in%omega_target%source)) THEN
      IF (.NOT.field_arrays_match(state_in%omega_target,shape3)) THEN
        result%status=STATUS_FAILED; result%reason_code=REASON_SHAPE
        RETURN
      END IF
      IF (ANY(IAND(state_in%omega_target%source, &
          SOURCE_MANUFACTURED_TEST)/=0)) THEN
        result%status=STATUS_FAILED; result%reason_code=REASON_AUTHORITY
        RETURN
      END IF
    END IF
    IF (ALLOCATED(state_in%omega_target_sigma%valid) .OR. &
        ALLOCATED(state_in%omega_target_sigma%source)) THEN
      IF (.NOT.field_arrays_match(state_in%omega_target_sigma,shape3)) THEN
        result%status=STATUS_FAILED; result%reason_code=REASON_SHAPE
        RETURN
      END IF
      IF (config%balance%target_authority==TARGET_AUTHORITY_OBSERVATIONAL .AND. &
          ANY(IAND(state_in%omega_target_sigma%source,SOURCE_MANUFACTURED_TEST)/=0)) THEN
        result%status=STATUS_FAILED; result%reason_code=REASON_AUTHORITY
        RETURN
      END IF
    END IF
    IF (boundary_has_manufactured_source(state_in)) THEN
      result%status=STATUS_FAILED; result%reason_code=REASON_AUTHORITY
      RETURN
    END IF

    IF (config%balance%target_authority==TARGET_AUTHORITY_MODEL_DYNAMICS) THEN
      ! The paired model driver must have installed an absolute target before
      ! the physical pipeline starts.  A missing or contaminated target is a
      ! hard authority failure, never an implicit zero innovation.
      IF (.NOT.ANY(target_is_resolved(state_in,TARGET_AUTHORITY_MODEL_DYNAMICS))) THEN
        result%status=STATUS_FAILED; result%reason_code=REASON_AUTHORITY
        CALL initialize_stage_result(result%overall,nx,ny,nz,STATUS_FAILED,REASON_AUTHORITY)
        RETURN
      END IF
    END IF

    IF (PRESENT(geopotential_support).NEQV.PRESENT(geopotential_reference_level)) THEN
      result%status=STATUS_FAILED; result%reason_code=REASON_AUTHORITY
      CALL initialize_stage_result(result%overall,nx,ny,nz,STATUS_FAILED,REASON_AUTHORITY)
      RETURN
    END IF
    IF (PRESENT(pressure_transition_seed)) THEN
      IF (.NOT.PRESENT(requested_surface_pressure)) THEN
        result%status=STATUS_FAILED; result%reason_code=REASON_AUTHORITY
        CALL initialize_stage_result(result%overall,nx,ny,nz,STATUS_FAILED,REASON_AUTHORITY)
        RETURN
      END IF
      IF (ANY(SHAPE(requested_surface_pressure)/=[nx,ny])) THEN
        result%status=STATUS_FAILED; result%reason_code=REASON_SHAPE
        CALL initialize_stage_result(result%overall,nx,ny,nz,STATUS_FAILED,REASON_SHAPE)
        RETURN
      END IF
      IF (.NOT.field2d_shape_metadata_ok(state_in%surface_pressure,nx,ny, &
          state_in%pressure%valid_time,'Pa')) THEN
        result%status=STATUS_FAILED; result%reason_code=REASON_METADATA
        CALL initialize_stage_result(result%overall,nx,ny,nz,STATUS_FAILED,REASON_METADATA)
        RETURN
      END IF
      IF (ANY(.NOT.ieee_is_finite(requested_surface_pressure)) .OR. &
          ANY(requested_surface_pressure<100.0_real64) .OR. &
          ANY(requested_surface_pressure>120000.0_real64) .OR. &
          ANY(ABS(requested_surface_pressure-REAL(state_in%surface_pressure%value,real64))>100.0_real64)) THEN
        result%status=STATUS_FAILED; result%reason_code=REASON_RANGE
        CALL initialize_stage_result(result%overall,nx,ny,nz,STATUS_FAILED,REASON_RANGE)
        RETURN
      END IF
    END IF
    IF (PRESENT(requested_surface_pressure)) THEN
      IF (.NOT.PRESENT(geopotential_support) .OR. config%maximum_outer_iterations/=1) THEN
        ! The existing outer feedback contract contains five fields, not
        ! pressure geometry. Do not label that loop a variable-geometry solve.
        result%status=STATUS_FAILED; result%reason_code=REASON_AUTHORITY
        CALL initialize_stage_result(result%overall,nx,ny,nz,STATUS_FAILED,REASON_AUTHORITY)
        RETURN
      END IF
    END IF
    IF (config%maximum_outer_iterations<1 .OR. config%maximum_outer_iterations>32) THEN
      result%status=STATUS_FAILED; result%reason_code=REASON_RANGE
      CALL initialize_stage_result(result%overall,nx,ny,nz,STATUS_FAILED,REASON_RANGE)
      RETURN
    END IF
    evaluation=state_in
    DO iteration=1,config%maximum_outer_iterations
      result%outer_iterations=iteration
      candidate_out=state_in
      result%geopotential%changed=.FALSE.
      geometry_budget=pressure_analysis_budget()
      ! Every trial is a fresh analysis of the SAME immutable background. Only
      ! coefficient evaluation feeds back; analysis and wind increments never sum.
      IF (config%maximum_outer_iterations==1) THEN
        CALL derive_column_physics(state_in,column_candidate,result%column, &
          config%column,thermo_active,thermo_surface,target_rh,result%thermo_budget,proposal_budget, &
          model_dynamics_target=config%balance%target_authority==TARGET_AUTHORITY_MODEL_DYNAMICS)
      ELSE
        CALL derive_column_physics(state_in,column_candidate,result%column, &
          config%column,thermo_active,thermo_surface,target_rh,result%thermo_budget,proposal_budget,evaluation, &
          model_dynamics_target=config%balance%target_authority==TARGET_AUTHORITY_MODEL_DYNAMICS)
      END IF
      IF (result%column%status/=STATUS_OK) THEN
        result%column%changed=.FALSE.
        result%balance%changed=.FALSE.
        result%thermo_budget=water_phase_budget()
        result%status=result%column%status
        result%reason_code=result%column%reason_code
        result%overall=result%column
        RETURN
      END IF
      candidate_out=column_candidate

      IF (PRESENT(geopotential_support)) THEN
        IF (PRESENT(pressure_transition_seed)) THEN
          ! Preserve the thermo Phi correction and handle same-domain pressure
          ! decreases with the existing hydrostatic step. Positive columns
          ! remain at old PS until their conservative transition below.
          IF (ANY(requested_surface_pressure<REAL(state_in%surface_pressure%value,real64))) THEN
            first_stage_pressure=MIN(requested_surface_pressure,REAL(state_in%surface_pressure%value,real64))
            CALL apply_pressure_hydrostatic_increment(state_in,column_candidate,geopotential_candidate, &
              result%geopotential,geopotential_support,geopotential_reference_level,first_stage_pressure,geometry_budget)
          ELSE
            CALL apply_pressure_hydrostatic_increment(state_in,column_candidate,geopotential_candidate, &
              result%geopotential,geopotential_support,geopotential_reference_level)
          END IF
          IF (result%geopotential%status==STATUS_OK) THEN
            CALL rebase_pressure_transition_prior(geopotential_candidate,pressure_transition_seed, &
              transition_prior,localization_status, &
              requested_surface_pressure>REAL(state_in%surface_pressure%value,real64))
            IF (localization_status==STATUS_OK) THEN
              ! The explicit seed may only change fully approved surface-
              ! anchored columns, and must represent the requested PS itself.
              IF (ANY(REAL(requested_surface_pressure,real32)/=transition_prior%surface_pressure%value)) THEN
                localization_status=STATUS_FAILED
              END IF
            END IF
            IF (localization_status==STATUS_OK) THEN
              DO j=1,ny; DO i=1,nx
                IF (transition_prior%surface_pressure%value(i,j)==state_in%surface_pressure%value(i,j)) CYCLE
                IF (geopotential_reference_level(i,j)/=0 .OR. &
                    ANY(state_in%above_ground(i,j,:) .AND. .NOT.geopotential_support(i,j,:))) &
                  localization_status=STATUS_FAILED
                IF (.NOT.ANY(transition_prior%above_ground(i,j,:) .AND. &
                    .NOT.state_in%above_ground(i,j,:))) CYCLE
                k=FINDLOC(transition_prior%above_ground(i,j,:),.TRUE.,DIM=1)
                IF (requested_surface_pressure(i,j)<REAL(state_in%pressure%value(i,j,k),real64)) &
                  localization_status=STATUS_FAILED
                IF (k>1) THEN
                  IF (requested_surface_pressure(i,j)>=REAL(state_in%pressure%value(i,j,k-1),real64)) &
                    localization_status=STATUS_FAILED
                END IF
              END DO; END DO
            END IF
            IF (localization_status/=STATUS_OK) THEN
              CALL initialize_stage_result(result%geopotential,nx,ny,nz,STATUS_FAILED,REASON_METADATA)
            ELSE
              CALL apply_pressure_domain_transition(geopotential_candidate,transition_prior,transition_candidate, &
                transition_result,geometry_budget)
              IF (transition_result%status/=STATUS_OK) THEN
                result%geopotential=transition_result
              ELSE
                ! Include any dry-mass storage refresh in the preceding Phi
                ! step as well as the domain transition in the endpoint ledger.
                CALL account_pressure_analysis(column_candidate,transition_candidate,geometry_budget, &
                  localization_status,.TRUE.,.TRUE.)
                IF (localization_status/=STATUS_OK) THEN
                  CALL initialize_stage_result(result%geopotential,nx,ny,nz,STATUS_FAILED,REASON_GATE)
                ELSE
                  result%geopotential%changed=result%geopotential%changed .OR. transition_result%changed
                  result%geopotential%coverage%required= &
                    COUNT(geopotential_support .OR. transition_result%changed,KIND=int64)
                  result%geopotential%coverage%usable=result%geopotential%coverage%required
                  result%geopotential%coverage%excluded=0_int64
                  IF (result%geopotential%coverage%required>0_int64) &
                    result%geopotential%coverage%usable_fraction=1.0_real64
                  geopotential_candidate=transition_candidate
                END IF
              END IF
            END IF
          END IF
        ELSE IF (PRESENT(requested_surface_pressure)) THEN
          CALL apply_pressure_hydrostatic_increment(state_in,column_candidate,geopotential_candidate, &
            result%geopotential,geopotential_support,geopotential_reference_level, &
            requested_surface_pressure,geometry_budget)
        ELSE
          CALL apply_pressure_hydrostatic_increment(state_in,column_candidate,geopotential_candidate, &
            result%geopotential,geopotential_support,geopotential_reference_level)
        END IF
        IF (result%geopotential%status/=STATUS_OK) THEN
          candidate_out=state_in
          result%thermo_budget=water_phase_budget()
          result%column%changed=.FALSE.; result%balance%changed=.FALSE.
          result%status=result%geopotential%status
          result%reason_code=result%geopotential%reason_code
          result%overall=result%geopotential
          RETURN
        END IF
        column_candidate=geopotential_candidate
      END IF

      CALL build_compact_balance_beta(column_candidate,config%horizontal_support_radius_m, &
                                      config%pressure_support_radius_pa,localization_status, &
                                      config%balance%target_authority)
      IF (localization_status/=STATUS_OK) THEN
        candidate_out=state_in; operational_out=state_in
        result%thermo_budget=water_phase_budget()
        result%column%changed=.FALSE.
        result%balance%changed=.FALSE.
        result%geopotential%changed=.FALSE.
        result%status=STATUS_FAILED; result%reason_code=REASON_RANGE
        CALL initialize_stage_result(result%overall,nx,ny,nz,STATUS_FAILED,REASON_RANGE)
        RETURN
      END IF

      CALL apply_localized_balance(column_candidate,balance_candidate, &
                                   result%balance,config%balance)
      IF (result%balance%status/=STATUS_OK) THEN
        candidate_out=state_in; operational_out=state_in
        result%thermo_budget=water_phase_budget()
        result%column%changed=.FALSE.
        result%balance%changed=.FALSE.
        result%geopotential%changed=.FALSE.
        result%status=result%balance%status
        result%reason_code=result%balance%reason_code
        result%overall=result%balance
        result%overall%changed=.FALSE.
        RETURN
      END IF
      IF (config%maximum_outer_iterations==1) EXIT
      result%outer_max_abs_delta(:,iteration)=pressure_feedback_delta(evaluation,balance_candidate)
      result%outer_converged=ALL(result%outer_max_abs_delta(:,iteration)==0.0_real64)
      IF (result%outer_converged) EXIT
      ! Keep original observation metadata even if a stage diagnoses a cloud
      ! contradiction. Only the five numerical feedback fields enter the trial.
      evaluation%temperature=balance_candidate%temperature
      evaluation%vapor=balance_candidate%vapor
      evaluation%u=balance_candidate%u
      evaluation%v=balance_candidate%v
      evaluation%omega=balance_candidate%omega
      CALL refresh_dry_air_mass_measure(evaluation,localization_status)
      IF (localization_status/=STATUS_OK) THEN
        candidate_out=state_in
        result%thermo_budget=water_phase_budget()
        result%column%changed=.FALSE.; result%balance%changed=.FALSE.
        result%geopotential%changed=.FALSE.
        result%status=STATUS_FAILED; result%reason_code=REASON_RANGE
        CALL initialize_stage_result(result%overall,nx,ny,nz,STATUS_FAILED,REASON_RANGE)
        RETURN
      END IF
    END DO
    IF (config%maximum_outer_iterations>1 .AND. .NOT.result%outer_converged) THEN
      candidate_out=state_in
      result%thermo_budget=water_phase_budget()
      result%column%changed=.FALSE.; result%balance%changed=.FALSE.
      result%geopotential%changed=.FALSE.
      result%status=STATUS_FAILED; result%reason_code=REASON_SOLVER
      CALL initialize_stage_result(result%overall,nx,ny,nz,STATUS_FAILED,REASON_SOLVER)
      RETURN
    END IF
    candidate_out=balance_candidate
    result%analysis_budget=proposal_budget
    result%geometry_budget=geometry_budget
    result%overall=result%balance
    result%overall%changed=result%column%changed .OR. result%balance%changed .OR. result%geopotential%changed
    result%status=STATUS_OK; result%reason_code=REASON_NONE

    ! Persist only an accepted explicit request; failures retain no permission
    ! for a downstream writer to serialize thermodynamic changes.
    IF (PRESENT(thermo_active)) THEN
      IF (ANY(thermo_active)) THEN
        result%thermo_support=thermo_active
        result%thermo_surface=thermo_surface
        result%thermo_target_rh=target_rh
      END IF
    END IF
    IF (PRESENT(geopotential_support)) THEN
      IF (ANY(geopotential_support)) THEN
        result%geopotential_support=geopotential_support
        IF (PRESENT(pressure_transition_seed)) result%geopotential_support= &
          result%geopotential_support .OR. (candidate_out%above_ground .AND. .NOT.state_in%above_ground)
        result%geopotential_reference_level=geopotential_reference_level
      END IF
    END IF
    operational_out=state_in
    IF (PRESENT(requested_surface_pressure)) result%requested_surface_pressure=requested_surface_pressure
    IF (PRESENT(pressure_transition_seed)) result%pressure_transition_seed=pressure_transition_seed
  END SUBROUTINE run_cloud_bal_pipeline

  FUNCTION pressure_feedback_delta(left,right) RESULT(delta)
    TYPE(cloud_bal_state_type), INTENT(IN) :: left,right
    REAL(real64) :: delta(5),cell_delta(5)
    INTEGER :: i,j,k
    ! Exact stored-value fixed point of the five inputs consumed by the next
    ! trial. No tolerance tuning, damped-state acceptance or native closure claim.
    ! Both candidates have already passed canonical and stage validation.
    delta=0.0_real64
    DO k=1,left%grid%nz; DO j=1,left%grid%ny; DO i=1,left%grid%nx
      IF (.NOT.left%above_ground(i,j,k)) CYCLE
      cell_delta=ABS(REAL([left%temperature%value(i,j,k),left%vapor%value(i,j,k), &
        left%u%value(i,j,k),left%v%value(i,j,k),left%omega%value(i,j,k)],real64)- &
        REAL([right%temperature%value(i,j,k),right%vapor%value(i,j,k), &
        right%u%value(i,j,k),right%v%value(i,j,k),right%omega%value(i,j,k)],real64))
      delta=MAX(delta,cell_delta)
    END DO; END DO; END DO
  END FUNCTION pressure_feedback_delta

  SUBROUTINE build_compact_balance_beta(state,horizontal_radius,pressure_radius,status,authority)
    TYPE(cloud_bal_state_type), INTENT(INOUT) :: state
    REAL(real64), INTENT(IN) :: horizontal_radius,pressure_radius
    INTEGER, INTENT(OUT) :: status
    INTEGER, INTENT(IN), OPTIONAL :: authority
    INTEGER :: i,j,k,is,js,ks,nx,ny,nz,iradius,jradius
    INTEGER :: target_authority
    REAL(real64) :: minimum_dx,minimum_dy,hdistance,pdistance,radius,kernel
    LOGICAL, ALLOCATABLE :: source(:,:,:)
    REAL(real32), ALLOCATABLE :: beta_work(:,:,:)
    LOGICAL :: distance_ok,radius_ok

    status=STATUS_FAILED
    target_authority=TARGET_AUTHORITY_OBSERVATIONAL
    IF (PRESENT(authority)) target_authority=authority
    IF (target_authority/=TARGET_AUTHORITY_OBSERVATIONAL .AND. &
        target_authority/=TARGET_AUTHORITY_MODEL_DYNAMICS) RETURN
    IF (.NOT.ieee_is_finite(horizontal_radius) .OR. horizontal_radius<=0.0_real64 .OR. &
        .NOT.ieee_is_finite(pressure_radius) .OR. pressure_radius<=0.0_real64) RETURN
    nx=state%grid%nx; ny=state%grid%ny; nz=state%grid%nz
    IF (.NOT.localization_inputs_valid(state,nx,ny,nz)) RETURN
    IF (target_authority==TARGET_AUTHORITY_MODEL_DYNAMICS .AND. &
        .NOT.model_target_coverage_contract_valid(state)) RETURN
    IF (ANY(.NOT.ieee_is_finite(state%pressure%value)) .OR. &
        ANY(.NOT.ieee_is_finite(state%grid%dx)) .OR. &
        ANY(.NOT.ieee_is_finite(state%grid%dy)) .OR. &
        ANY(state%grid%dx<=0.0_real64) .OR. ANY(state%grid%dy<=0.0_real64)) RETURN
    ALLOCATE(source(nx,ny,nz),beta_work(nx,ny,nz))
    beta_work=0.0_real32
    ! Only an explicit dynamic proposal grants wind-adjustment authority.
    ! Cloud and hydrometeor presence remain provenance, never solver seeds.
    source=state%above_ground .AND. &
           target_is_resolved(state,target_authority) .AND. &
           cell_is_usable(state%omega%valid,state%omega%quality,state%omega%source)
    IF (target_authority==TARGET_AUTHORITY_MODEL_DYNAMICS) THEN
      source=source .AND. state%model_target_coverage
      DO ks=1,nz; DO js=1,ny; DO is=1,nx
        IF (source(is,js,ks) .AND. &
            .NOT.model_target_level_is_interior(state,is,js,ks)) &
          source(is,js,ks)=.FALSE.
      END DO; END DO; END DO
    END IF
    IF (.NOT.ANY(source)) THEN
      state%balance_beta=beta_work
      status=STATUS_OK
      RETURN
    END IF
    minimum_dx=MINVAL(state%grid%dx); minimum_dy=MINVAL(state%grid%dy)
    CALL bounded_grid_radius(horizontal_radius,minimum_dx,nx-1,iradius,radius_ok)
    IF (.NOT.radius_ok) RETURN
    CALL bounded_grid_radius(horizontal_radius,minimum_dy,ny-1,jradius,radius_ok)
    IF (.NOT.radius_ok) RETURN
    DO ks=1,nz; DO js=1,ny; DO is=1,nx
      IF (.NOT.source(is,js,ks)) CYCLE
      DO k=1,nz
        DO j=MAX(1,js-jradius),MIN(ny,js+jradius)
          DO i=MAX(1,is-iradius),MIN(nx,is+iradius)
            IF (.NOT.state%above_ground(i,j,k)) CYCLE
            pdistance=ABS(REAL(state%pressure%value(is,js,ks),real64)- &
                          REAL(state%pressure%value(i,j,k),real64))
            IF (pdistance>=pressure_radius) CYCLE
            CALL cumulative_horizontal_distance(state%grid%dx,state%grid%dy, &
                                                i,j,is,js,hdistance,distance_ok)
            IF (.NOT.distance_ok) RETURN
            radius=SQRT((hdistance/horizontal_radius)**2+ &
                        (pdistance/pressure_radius)**2)
            IF (radius>=1.0_real64) CYCLE
            kernel=(1.0_real64-radius)**4*(1.0_real64+4.0_real64*radius)
            beta_work(i,j,k)=MAX(beta_work(i,j,k),REAL(kernel,real32))
          END DO
        END DO
      END DO
    END DO; END DO; END DO
    IF (target_authority==TARGET_AUTHORITY_MODEL_DYNAMICS) THEN
      ! The driver marks the native target domain and its closed halo. The
      ! omega target validity remains the distinct target-vs-halo contract.
      WHERE(.NOT.state%model_target_coverage) beta_work=0.0_real32
    END IF
    WHERE(source) beta_work=1.0_real32
    IF (ANY(.NOT.ieee_is_finite(beta_work)) .OR. &
        ANY(beta_work<0.0_real32) .OR. ANY(beta_work>1.0_real32)) RETURN
    state%balance_beta=beta_work
    status=STATUS_OK
  END SUBROUTINE build_compact_balance_beta

  LOGICAL FUNCTION localization_inputs_valid(state,nx,ny,nz)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    INTEGER, INTENT(IN) :: nx,ny,nz
    INTEGER :: shape2(2),shape3(3)

    localization_inputs_valid=.FALSE.
    IF (nx<1 .OR. ny<1 .OR. nz<2) RETURN
    shape2=(/nx,ny/); shape3=(/nx,ny,nz/)
    IF (.NOT.ALLOCATED(state%grid%dx) .OR. .NOT.ALLOCATED(state%grid%dy) .OR. &
        .NOT.ALLOCATED(state%above_ground) .OR. &
        .NOT.ALLOCATED(state%balance_beta)) RETURN
    IF (ANY(SHAPE(state%grid%dx)/=shape2) .OR. &
        ANY(SHAPE(state%grid%dy)/=shape2) .OR. &
        ANY(SHAPE(state%above_ground)/=shape3) .OR. &
        ANY(SHAPE(state%balance_beta)/=shape3)) RETURN
    IF (.NOT.field_arrays_match(state%pressure,shape3) .OR. &
        .NOT.field_arrays_match(state%omega,shape3) .OR. &
        .NOT.field_arrays_match(state%omega_target,shape3)) RETURN
    localization_inputs_valid=.TRUE.
  END FUNCTION localization_inputs_valid

  LOGICAL FUNCTION field_arrays_match(field,shape3)
    TYPE(field3d), INTENT(IN) :: field
    INTEGER, INTENT(IN) :: shape3(3)

    field_arrays_match=.FALSE.
    IF (.NOT.ALLOCATED(field%value) .OR. .NOT.ALLOCATED(field%valid) .OR. &
        .NOT.ALLOCATED(field%quality) .OR. .NOT.ALLOCATED(field%source)) RETURN
    IF (ANY(SHAPE(field%value)/=shape3) .OR. ANY(SHAPE(field%valid)/=shape3) .OR. &
        ANY(SHAPE(field%quality)/=shape3) .OR. ANY(SHAPE(field%source)/=shape3)) RETURN
    field_arrays_match=.TRUE.
  END FUNCTION field_arrays_match

  LOGICAL FUNCTION boundary_has_manufactured_source(state)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    boundary_has_manufactured_source=.FALSE.
    IF (.NOT.ALLOCATED(state%omega_top_boundary%source) .OR. &
        .NOT.ALLOCATED(state%omega_bottom_boundary%source)) RETURN
    boundary_has_manufactured_source= &
      ANY(IAND(state%omega_top_boundary%source,SOURCE_MANUFACTURED_TEST)/=0) .OR. &
      ANY(IAND(state%omega_bottom_boundary%source,SOURCE_MANUFACTURED_TEST)/=0)
  END FUNCTION boundary_has_manufactured_source

END MODULE cloud_bal_pipeline
