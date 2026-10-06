! Single authority boundary for the canonical Cloud-BAL pipeline.
MODULE cloud_bal_pipeline
  USE, INTRINSIC :: iso_fortran_env,ONLY: int32,int64,real32,real64
  USE, INTRINSIC :: ieee_arithmetic,ONLY: ieee_is_finite
  USE cloud_bal_state
  USE cloud_bal_column_physics
  USE cloud_bal_balance_operator
  USE cloud_bal_grid_geometry,ONLY: bounded_grid_radius,cumulative_horizontal_distance
  IMPLICIT NONE
  PRIVATE

  ! Separate reason namespace for the changed-domain receipt extension.
  INTEGER, PUBLIC, PARAMETER :: DIAGNOSTIC_REASON_NO_CHANGED_DOMAIN=10

  INTEGER, PUBLIC, PARAMETER :: PHYSICAL_FEASIBILITY_FAILED=-1
  INTEGER, PUBLIC, PARAMETER :: PHYSICAL_FEASIBILITY_UNSUPPORTED=0
  ! PASS means only that the declared local component increments are feasible.
  INTEGER, PUBLIC, PARAMETER :: PHYSICAL_FEASIBILITY_PASS=1
  INTEGER, PUBLIC, PARAMETER :: PHYSICAL_COMPONENT_DRY_MASS_METRIC=1
  INTEGER, PUBLIC, PARAMETER :: PHYSICAL_COMPONENT_VAPOR=2
  INTEGER, PUBLIC, PARAMETER :: PHYSICAL_COMPONENT_CLOUD_WATER=3
  INTEGER, PUBLIC, PARAMETER :: PHYSICAL_COMPONENT_CLOUD_ICE=4
  INTEGER, PUBLIC, PARAMETER :: PHYSICAL_COMPONENT_RAIN=5
  INTEGER, PUBLIC, PARAMETER :: PHYSICAL_COMPONENT_SNOW=6
  INTEGER, PUBLIC, PARAMETER :: PHYSICAL_COMPONENT_GRAUPEL=7
  INTEGER, PUBLIC, PARAMETER :: PHYSICAL_COMPONENT_ENTHALPY=8
  INTEGER, PUBLIC, PARAMETER :: PHYSICAL_COMPONENT_TOTAL_MASS=0
  INTEGER, PUBLIC, PARAMETER :: PHYSICAL_ADJUST_TEMPERATURE=ISHFT(1,0)
  INTEGER, PUBLIC, PARAMETER :: PHYSICAL_ADJUST_VAPOR=ISHFT(1,1)
  INTEGER, PUBLIC, PARAMETER :: PHYSICAL_ADJUST_CLOUD_WATER=ISHFT(1,2)
  INTEGER, PUBLIC, PARAMETER :: PHYSICAL_ADJUST_CLOUD_ICE=ISHFT(1,3)
  INTEGER, PUBLIC, PARAMETER :: PHYSICAL_ADJUST_RAIN=ISHFT(1,4)
  INTEGER, PUBLIC, PARAMETER :: PHYSICAL_ADJUST_SNOW=ISHFT(1,5)
  INTEGER, PUBLIC, PARAMETER :: PHYSICAL_ADJUST_GRAUPEL=ISHFT(1,6)
  INTEGER, PUBLIC, PARAMETER :: PHYSICAL_ADJUST_U=ISHFT(1,7)
  INTEGER, PUBLIC, PARAMETER :: PHYSICAL_ADJUST_V=ISHFT(1,8)
  INTEGER, PUBLIC, PARAMETER :: PHYSICAL_ADJUST_OMEGA=ISHFT(1,9)
  INTEGER, PUBLIC, PARAMETER :: PHYSICAL_ADJUST_GEOPOTENTIAL=ISHFT(1,10)

  TYPE, PUBLIC :: physical_joint_candidate_contract
    ! Caller-prescribed per-cell source and boundary increments in kg
    ! (components 1:7) and J (component 8), plus physical tolerances in those
    ! units. Component 1 is the canonical dry-mass metric, not physical gas
    ! source authority. Component 8 is represented mixture enthalpy only.
    ! Components 1:7 must have zero net total-mass increment per covered cell
    ! when pressure geometry is fixed. Only source+boundary net is compared;
    ! their separate attribution,
    ! observation fit, optimality and native conservation remain unassessed.
    INTEGER :: adjustable_variables=0
    LOGICAL, ALLOCATABLE :: coverage(:,:,:)
    REAL(real64), ALLOCATABLE :: source_increment(:,:,:,:)
    REAL(real64), ALLOCATABLE :: boundary_increment(:,:,:,:)
    REAL(real64), ALLOCATABLE :: physical_tolerance(:,:,:,:)
  END TYPE physical_joint_candidate_contract

  TYPE, PUBLIC :: cloud_bal_pipeline_config
    INTEGER :: requested_mode=MODE_OFF
    REAL(real64) :: horizontal_support_radius_m=12000.0_real64
    REAL(real64) :: pressure_support_radius_pa=30000.0_real64
    TYPE(column_physics_config) :: column
    TYPE(balance_operator_config) :: balance
    ! One preserves the legacy single pass; larger values request a fixed point.
    INTEGER :: maximum_outer_iterations=1
  END TYPE cloud_bal_pipeline_config

  TYPE, PUBLIC :: joint_candidate_evaluation
    ! Diagnostics recomputed from one final state. Neither an external source
    ! nor an observational/physical approval is inferred from these numbers.
    LOGICAL :: canonical_accounting_assessed=.FALSE.
    LOGICAL :: continuity_assessed=.FALSE.
    LOGICAL :: geostrophic_assessed=.FALSE.
    LOGICAL :: source_boundary_assessed=.FALSE.
    LOGICAL :: observation_fit_assessed=.FALSE.
    LOGICAL :: optimality_assessed=.FALSE.
    LOGICAL :: native_conservation_assessed=.FALSE.
    INTEGER :: physical_feasibility_status=PHYSICAL_FEASIBILITY_UNSUPPORTED
    INTEGER :: physical_feasibility_reason=REASON_NONE
    INTEGER :: physical_feasibility_failed_cell(3)=0
    INTEGER :: physical_feasibility_failed_component=0
    REAL(real64) :: physical_feasibility_residual_scaled=0.0_real64
    INTEGER(int64) :: physical_feasibility_cells=0_int64
    INTEGER(int64) :: balance_support_cells=0_int64
    INTEGER :: operator_status=STATUS_FAILED
    INTEGER :: operator_reason=REASON_NONE
    INTEGER :: continuity_status=STATUS_FAILED
    INTEGER :: geostrophic_status=STATUS_FAILED
    REAL(real64) :: continuity_rms=0.0_real64
    REAL(real64) :: continuity_max_abs=0.0_real64
    REAL(real64) :: geostrophic_rms=0.0_real64
    ! Separate changed-domain receipt; the legacy fields above retain their
    ! balance-control-support meaning and schema.
    INTEGER(int64) :: diagnostic_changed_cells=0_int64
    INTEGER(int64) :: diagnostic_requested_cells=0_int64
    INTEGER(int64) :: continuity_assessable_cells=0_int64
    INTEGER(int64) :: geostrophic_assessable_cells=0_int64
    LOGICAL :: diagnostic_continuity_assessed=.FALSE.
    LOGICAL :: diagnostic_geostrophic_assessed=.FALSE.
    INTEGER :: diagnostic_continuity_status=STATUS_FAILED
    INTEGER :: diagnostic_geostrophic_status=STATUS_FAILED
    INTEGER :: diagnostic_continuity_reason=REASON_NONE
    INTEGER :: diagnostic_geostrophic_reason=REASON_NONE
    INTEGER :: diagnostic_operator_status=STATUS_FAILED
    INTEGER :: diagnostic_operator_reason=REASON_NONE
    REAL(real64) :: diagnostic_continuity_rms=0.0_real64
    REAL(real64) :: diagnostic_continuity_max_abs=0.0_real64
    REAL(real64) :: diagnostic_geostrophic_rms=0.0_real64
    ! Exact receipt masks for changed, requested and independently assessable
    ! cells. These describe this evaluation only; they do not establish a
    ! reconstruction from external WPS background products.
    LOGICAL, ALLOCATABLE :: diagnostic_changed_mask(:,:,:)
    LOGICAL, ALLOCATABLE :: diagnostic_requested_mask(:,:,:)
    LOGICAL, ALLOCATABLE :: diagnostic_continuity_assessable_mask(:,:,:)
    LOGICAL, ALLOCATABLE :: diagnostic_geostrophic_assessable_mask(:,:,:)
    LOGICAL :: diagnostic_masks_assessed=.FALSE.
    TYPE(hydrostatic_constraint_summary) :: interior_hydrostatic_summary
    LOGICAL, ALLOCATABLE :: interior_hydrostatic_requested(:,:,:)
    LOGICAL, ALLOCATABLE :: interior_hydrostatic_assessable(:,:,:)
    INTEGER(int32), ALLOCATABLE :: interior_hydrostatic_reason(:,:,:)
    REAL(real64), ALLOCATABLE :: interior_hydrostatic_residual(:,:,:)
  END TYPE joint_candidate_evaluation

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
    ! Endpoint accounting for the one final candidate, including all stages.
    ! This is not a physical boundary-flux or native energy closure claim.
    TYPE(pressure_analysis_budget) :: candidate_budget
    TYPE(joint_candidate_evaluation) :: candidate_evaluation
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
  PUBLIC :: account_candidate_endpoint
  PUBLIC :: evaluate_joint_candidate
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
                                    pressure_transition_seed,physical_contract)
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
    TYPE(physical_joint_candidate_contract), INTENT(IN), OPTIONAL :: physical_contract
    TYPE(cloud_bal_state_type) :: column_candidate,geopotential_candidate,balance_candidate,evaluation
    TYPE(cloud_bal_state_type) :: transition_prior,transition_candidate
    TYPE(stage_result) :: transition_result
    TYPE(pressure_analysis_budget) :: proposal_budget,geometry_budget,trial_budget
    TYPE(joint_candidate_evaluation) :: trial_evaluation
    REAL(real64), ALLOCATABLE :: first_stage_pressure(:,:)
    INTEGER :: nx,ny,nz,localization_status,shape3(3),iteration,i,j,k,validation_reason

    nx=state_in%grid%nx; ny=state_in%grid%ny; nz=state_in%grid%nz
    shape3=(/nx,ny,nz/)
    candidate_out=state_in; operational_out=state_in
    result%requested_mode=config%requested_mode
    result%outer_iterations=0; result%outer_converged=.FALSE.
    result%outer_max_abs_delta=0.0_real64
    result%thermo_budget=water_phase_budget()
    result%analysis_budget=pressure_analysis_budget()
    result%geometry_budget=pressure_analysis_budget()
    result%candidate_budget=pressure_analysis_budget()
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
    IF (PRESENT(physical_contract) .AND. .NOT.PRESENT(requested_surface_pressure)) THEN
      CALL preflight_physical_mass_contract(state_in,physical_contract,trial_evaluation)
      IF (trial_evaluation%physical_feasibility_status==PHYSICAL_FEASIBILITY_FAILED) THEN
        result%candidate_evaluation=trial_evaluation
        result%status=STATUS_FAILED
        result%reason_code=REASON_GATE
        CALL initialize_stage_result(result%overall,nx,ny,nz,STATUS_FAILED,REASON_GATE)
        RETURN
      END IF
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
      CALL evaluate_joint_candidate(state_in,balance_candidate,config%balance, &
        trial_budget,trial_evaluation,localization_status,validation_reason,physical_contract)
      IF (localization_status/=STATUS_OK .OR. &
          (PRESENT(physical_contract) .AND. &
           trial_evaluation%physical_feasibility_status/=PHYSICAL_FEASIBILITY_PASS)) THEN
        candidate_out=state_in; operational_out=state_in
        result%thermo_budget=water_phase_budget()
        result%candidate_budget=pressure_analysis_budget()
        result%candidate_evaluation=trial_evaluation
        result%column%changed=.FALSE.; result%balance%changed=.FALSE.
        result%geopotential%changed=.FALSE.
        result%status=STATUS_FAILED
        result%reason_code=validation_reason
        IF (localization_status==STATUS_OK) result%reason_code=REASON_GATE
        CALL initialize_stage_result(result%overall,nx,ny,nz,STATUS_FAILED,result%reason_code)
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
      result%candidate_budget=pressure_analysis_budget()
      result%candidate_evaluation=joint_candidate_evaluation()
      result%column%changed=.FALSE.; result%balance%changed=.FALSE.
      result%geopotential%changed=.FALSE.
      result%status=STATUS_FAILED; result%reason_code=REASON_SOLVER
      CALL initialize_stage_result(result%overall,nx,ny,nz,STATUS_FAILED,REASON_SOLVER)
      RETURN
    END IF
    ! The last successful block trial was re-evaluated before acceptance.
    candidate_out=balance_candidate
    result%candidate_budget=trial_budget
    result%candidate_evaluation=trial_evaluation
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

  SUBROUTINE account_candidate_endpoint(background,candidate,budget,status,reason)
    ! Signed whole-state endpoint difference. It does not assign an external
    ! mass or energy source, a boundary flux, or native conservation authority.
    ! The caller supplies a validated immutable background.
    TYPE(cloud_bal_state_type), INTENT(IN) :: background,candidate
    TYPE(pressure_analysis_budget), INTENT(OUT) :: budget
    INTEGER, INTENT(OUT) :: status,reason
    LOGICAL :: domain_changed,geometry_changed

    budget=pressure_analysis_budget()
    reason=REASON_GATE
    CALL validate_canonical_state(candidate,.FALSE.,.FALSE.,status,reason,.FALSE.)
    IF (status/=STATUS_OK) RETURN
    domain_changed=ANY(background%above_ground .NEQV. candidate%above_ground)
    geometry_changed=domain_changed .OR. &
      ANY(background%surface_pressure%value/=candidate%surface_pressure%value) .OR. &
      ANY(background%grid%pressure_interface/=candidate%grid%pressure_interface)
    CALL account_pressure_analysis(background,candidate,budget,status,geometry_changed,domain_changed)
    IF (status/=STATUS_OK) THEN
      budget=pressure_analysis_budget()
      reason=REASON_GATE
    ELSE
      reason=REASON_NONE
    END IF
  END SUBROUTINE account_candidate_endpoint

  SUBROUTINE evaluate_joint_candidate(background,candidate,balance_config,budget,evaluation,status,reason, &
                                      physical_contract)
    ! Re-evaluate the existing pressure-grid diagnostics on the same final
    ! candidate used for the endpoint ledger. Missing physical-time sources,
    ! boundary fluxes and independent observation operators remain unassessed.
    TYPE(cloud_bal_state_type), INTENT(IN) :: background,candidate
    TYPE(balance_operator_config), INTENT(IN) :: balance_config
    TYPE(pressure_analysis_budget), INTENT(OUT) :: budget
    TYPE(joint_candidate_evaluation), INTENT(OUT) :: evaluation
    INTEGER, INTENT(OUT) :: status,reason
    TYPE(physical_joint_candidate_contract), INTENT(IN), OPTIONAL :: physical_contract
    TYPE(balance_operator_type) :: op,diagnostic_op
    REAL(real64), ALLOCATABLE :: continuity(:,:,:)
    LOGICAL, ALLOCATABLE :: changed_domain(:,:,:),requested_domain(:,:,:),domain_union(:,:,:)
    LOGICAL, ALLOCATABLE :: continuity_support(:,:,:),geostrophic_support(:,:,:)
    INTEGER :: domain_status,domain_reason

    evaluation=joint_candidate_evaluation()
    IF (background%grid%grid_id/=candidate%grid%grid_id .OR. &
        .NOT.optional_field2d_identity_equal(background%latitude,candidate%latitude)) THEN
      status=STATUS_FAILED; reason=REASON_METADATA
      RETURN
    END IF
    ! The returned status/reason cover canonical endpoint accounting only.
    ! Each balance diagnostic has its own status and may remain unassessed.
    CALL account_candidate_endpoint(background,candidate,budget,status,reason)
    IF (status/=STATUS_OK) RETURN
    IF (PRESENT(physical_contract)) &
      CALL assess_physical_joint_candidate(background,candidate,physical_contract,evaluation)
    ALLOCATE(evaluation%diagnostic_changed_mask(candidate%grid%nx,candidate%grid%ny,candidate%grid%nz), &
      evaluation%diagnostic_requested_mask(candidate%grid%nx,candidate%grid%ny,candidate%grid%nz), &
      evaluation%diagnostic_continuity_assessable_mask(candidate%grid%nx,candidate%grid%ny,candidate%grid%nz), &
      evaluation%diagnostic_geostrophic_assessable_mask(candidate%grid%nx,candidate%grid%ny,candidate%grid%nz))
    evaluation%diagnostic_changed_mask=.FALSE.
    evaluation%diagnostic_requested_mask=.FALSE.
    evaluation%diagnostic_continuity_assessable_mask=.FALSE.
    evaluation%diagnostic_geostrophic_assessable_mask=.FALSE.
    evaluation%canonical_accounting_assessed=.TRUE.

    CALL build_balance_operator(candidate,balance_config,op,evaluation%operator_status, &
      evaluation%operator_reason)
    IF (evaluation%operator_status==STATUS_OK) THEN
      evaluation%balance_support_cells=active_balance_cell_count(op)
      IF (evaluation%balance_support_cells>0_int64) THEN
        IF (.NOT.ALLOCATED(continuity)) &
          ALLOCATE(continuity(candidate%grid%nx,candidate%grid%ny,candidate%grid%nz))
        CALL state_continuity_residual(op,candidate,continuity,evaluation%continuity_status)
        IF (evaluation%continuity_status==STATUS_OK) THEN
          CALL continuity_norms(op,continuity,evaluation%continuity_rms,evaluation%continuity_max_abs)
          evaluation%continuity_assessed=ieee_is_finite(evaluation%continuity_rms) .AND. &
            evaluation%continuity_rms<HUGE(1.0_real64) .AND. &
            ieee_is_finite(evaluation%continuity_max_abs) .AND. &
            evaluation%continuity_max_abs<HUGE(1.0_real64)
        END IF
        IF (.NOT.evaluation%continuity_assessed) THEN
          evaluation%continuity_status=STATUS_FAILED
          evaluation%continuity_rms=0.0_real64
          evaluation%continuity_max_abs=0.0_real64
        END IF
        CALL geostrophic_residual(candidate,op,evaluation%geostrophic_rms,evaluation%geostrophic_status)
        evaluation%geostrophic_assessed=evaluation%geostrophic_status==STATUS_OK .AND. &
          ieee_is_finite(evaluation%geostrophic_rms) .AND. &
          evaluation%geostrophic_rms<HUGE(1.0_real64)
        IF (.NOT.evaluation%geostrophic_assessed) THEN
          evaluation%geostrophic_status=STATUS_FAILED
          evaluation%geostrophic_rms=0.0_real64
        END IF
      END IF
    END IF

    CALL build_diagnostic_balance_operator(candidate,diagnostic_op, &
      evaluation%diagnostic_operator_status,evaluation%diagnostic_operator_reason)
    IF (evaluation%diagnostic_operator_status/=STATUS_OK) THEN
      evaluation%diagnostic_continuity_reason=evaluation%diagnostic_operator_reason
      evaluation%diagnostic_geostrophic_reason=evaluation%diagnostic_operator_reason
      RETURN
    END IF

    ALLOCATE(changed_domain(candidate%grid%nx,candidate%grid%ny,candidate%grid%nz), &
      requested_domain(candidate%grid%nx,candidate%grid%ny,candidate%grid%nz), &
      domain_union(candidate%grid%nx,candidate%grid%ny,candidate%grid%nz), &
      continuity_support(candidate%grid%nx,candidate%grid%ny,candidate%grid%nz), &
      geostrophic_support(candidate%grid%nx,candidate%grid%ny,candidate%grid%nz))
    CALL build_candidate_evaluation_domain(background,candidate,changed_domain, &
      requested_domain,domain_status,domain_reason)
    IF (domain_status/=STATUS_OK) THEN
      evaluation%diagnostic_continuity_reason=domain_reason
      evaluation%diagnostic_geostrophic_reason=domain_reason
      RETURN
    END IF
    domain_union=background%above_ground .OR. candidate%above_ground
    CALL include_lateral_face_stencil(diagnostic_op,changed_domain,domain_union,requested_domain,domain_status)
    IF (domain_status/=STATUS_OK) THEN
      evaluation%diagnostic_continuity_reason=REASON_REQUIRED_COVERAGE
      evaluation%diagnostic_geostrophic_reason=REASON_REQUIRED_COVERAGE
      RETURN
    END IF
    evaluation%diagnostic_changed_cells=COUNT(changed_domain,KIND=int64)
    evaluation%diagnostic_requested_cells=COUNT(requested_domain,KIND=int64)
    evaluation%diagnostic_changed_mask=changed_domain
    evaluation%diagnostic_requested_mask=requested_domain
    ! Each required center requests both adjacent thickness relations. Keep
    ! old-only atmospheric endpoints requested: missing candidate support is
    ! reported by the layer evaluator rather than dropped from the domain.
    ALLOCATE(evaluation%interior_hydrostatic_requested(candidate%grid%nx,candidate%grid%ny, &
        candidate%grid%nz-1), &
      evaluation%interior_hydrostatic_assessable(candidate%grid%nx,candidate%grid%ny,candidate%grid%nz-1), &
      evaluation%interior_hydrostatic_reason(candidate%grid%nx,candidate%grid%ny,candidate%grid%nz-1), &
      evaluation%interior_hydrostatic_residual(candidate%grid%nx,candidate%grid%ny,candidate%grid%nz-1))
    evaluation%interior_hydrostatic_requested= &
      requested_domain(:,:,1:candidate%grid%nz-1) .OR. requested_domain(:,:,2:candidate%grid%nz)
    CALL evaluate_interior_hydrostatic_residual(candidate,evaluation%interior_hydrostatic_requested, &
      evaluation%interior_hydrostatic_residual,evaluation%interior_hydrostatic_assessable, &
      evaluation%interior_hydrostatic_reason,evaluation%interior_hydrostatic_summary)
    CALL diagnostic_domain_assessable(candidate,diagnostic_op,requested_domain,continuity_support, &
      geostrophic_support,domain_status)
    IF (domain_status/=STATUS_OK) THEN
      evaluation%diagnostic_continuity_status=STATUS_FAILED
      evaluation%diagnostic_geostrophic_status=STATUS_FAILED
      evaluation%diagnostic_continuity_reason=REASON_REQUIRED_COVERAGE
      evaluation%diagnostic_geostrophic_reason=REASON_REQUIRED_COVERAGE
      RETURN
    END IF
    evaluation%continuity_assessable_cells=COUNT(continuity_support,KIND=int64)
    evaluation%geostrophic_assessable_cells=COUNT(geostrophic_support,KIND=int64)
    evaluation%diagnostic_continuity_assessable_mask=continuity_support
    evaluation%diagnostic_geostrophic_assessable_mask=geostrophic_support
    evaluation%diagnostic_masks_assessed=.TRUE.
    IF (evaluation%diagnostic_requested_cells==0_int64) THEN
      evaluation%diagnostic_continuity_status=STATUS_DEGRADED
      evaluation%diagnostic_geostrophic_status=STATUS_DEGRADED
      evaluation%diagnostic_continuity_reason=DIAGNOSTIC_REASON_NO_CHANGED_DOMAIN
      evaluation%diagnostic_geostrophic_reason=DIAGNOSTIC_REASON_NO_CHANGED_DOMAIN
      RETURN
    END IF
    IF (evaluation%continuity_assessable_cells/=evaluation%diagnostic_requested_cells) THEN
      evaluation%diagnostic_continuity_status=STATUS_DEGRADED
      evaluation%diagnostic_continuity_reason=REASON_REQUIRED_COVERAGE
    ELSE
      IF (.NOT.ALLOCATED(continuity)) &
        ALLOCATE(continuity(candidate%grid%nx,candidate%grid%ny,candidate%grid%nz))
      CALL state_continuity_residual(diagnostic_op,candidate,continuity, &
        evaluation%diagnostic_continuity_status,evaluation_mask=requested_domain)
      IF (evaluation%diagnostic_continuity_status==STATUS_OK) THEN
        CALL continuity_norms(diagnostic_op,continuity,evaluation%diagnostic_continuity_rms, &
          evaluation%diagnostic_continuity_max_abs,requested_domain)
        evaluation%diagnostic_continuity_assessed= &
          ieee_is_finite(evaluation%diagnostic_continuity_rms) .AND. &
          evaluation%diagnostic_continuity_rms<HUGE(1.0_real64) .AND. &
          ieee_is_finite(evaluation%diagnostic_continuity_max_abs) .AND. &
          evaluation%diagnostic_continuity_max_abs<HUGE(1.0_real64)
      END IF
      IF (.NOT.evaluation%diagnostic_continuity_assessed) THEN
        evaluation%diagnostic_continuity_status=STATUS_FAILED
        evaluation%diagnostic_continuity_reason=REASON_NONFINITE
        evaluation%diagnostic_continuity_rms=0.0_real64
        evaluation%diagnostic_continuity_max_abs=0.0_real64
      END IF
    END IF
    IF (evaluation%geostrophic_assessable_cells/=evaluation%diagnostic_requested_cells) THEN
      evaluation%diagnostic_geostrophic_status=STATUS_DEGRADED
      evaluation%diagnostic_geostrophic_reason=REASON_REQUIRED_COVERAGE
    ELSE
      CALL geostrophic_residual(candidate,diagnostic_op,evaluation%diagnostic_geostrophic_rms, &
        evaluation%diagnostic_geostrophic_status,requested_domain, &
        evaluation%diagnostic_geostrophic_reason)
      evaluation%diagnostic_geostrophic_assessed= &
        evaluation%diagnostic_geostrophic_status==STATUS_OK .AND. &
        ieee_is_finite(evaluation%diagnostic_geostrophic_rms) .AND. &
        evaluation%diagnostic_geostrophic_rms<HUGE(1.0_real64)
      IF (.NOT.evaluation%diagnostic_geostrophic_assessed) THEN
        evaluation%diagnostic_geostrophic_status=STATUS_FAILED
        IF (evaluation%diagnostic_geostrophic_reason==REASON_NONE) &
          evaluation%diagnostic_geostrophic_reason=REASON_NONFINITE
        evaluation%diagnostic_geostrophic_rms=0.0_real64
      END IF
    END IF
  END SUBROUTINE evaluate_joint_candidate

  SUBROUTINE assess_physical_joint_candidate(background,candidate,contract,evaluation)
    TYPE(cloud_bal_state_type), INTENT(IN) :: background,candidate
    TYPE(physical_joint_candidate_contract), INTENT(IN) :: contract
    TYPE(joint_candidate_evaluation), INTENT(INOUT) :: evaluation
    REAL(real64) :: source,boundary,after_term,before_term
    REAL(real64) :: before_mass,after_mass,before_enthalpy,after_enthalpy,species_before(6),species_after(6)
    REAL(real64) :: scaled_residual
    INTEGER :: nx,ny,nz,i,j,k,c,shape3(3)
    LOGICAL, ALLOCATABLE :: domain(:,:,:)

    evaluation%physical_feasibility_status=PHYSICAL_FEASIBILITY_FAILED
    evaluation%physical_feasibility_reason=REASON_GATE
    evaluation%physical_feasibility_failed_cell=0
    evaluation%physical_feasibility_failed_component=0
    evaluation%physical_feasibility_residual_scaled=0.0_real64
    nx=candidate%grid%nx; ny=candidate%grid%ny; nz=candidate%grid%nz
    shape3=(/nx,ny,nz/)
    IF (.NOT.ALLOCATED(contract%coverage) .OR. .NOT.ALLOCATED(contract%source_increment) .OR. &
        .NOT.ALLOCATED(contract%boundary_increment) .OR. .NOT.ALLOCATED(contract%physical_tolerance)) THEN
      evaluation%physical_feasibility_reason=REASON_REQUIRED_COVERAGE
      RETURN
    END IF
    IF (ANY(SHAPE(contract%coverage)/=(/nx,ny,nz/)) .OR. &
        ANY(SHAPE(contract%source_increment)/=(/8,nx,ny,nz/)) .OR. &
        ANY(SHAPE(contract%boundary_increment)/=(/8,nx,ny,nz/)) .OR. &
        ANY(SHAPE(contract%physical_tolerance)/=(/8,nx,ny,nz/))) THEN
      evaluation%physical_feasibility_reason=REASON_SHAPE
      RETURN
    END IF
    IF (ANY(background%above_ground .NEQV. candidate%above_ground) .OR. &
        ANY(background%surface_pressure%value/=candidate%surface_pressure%value) .OR. &
        ANY(background%grid%pressure_interface/=candidate%grid%pressure_interface) .OR. &
        ANY(background%grid%pressure_mass_measure/=candidate%grid%pressure_mass_measure)) THEN
      evaluation%physical_feasibility_status=PHYSICAL_FEASIBILITY_UNSUPPORTED
      evaluation%physical_feasibility_reason=REASON_AUTHORITY
      RETURN
    END IF
    IF (.NOT.optional_field2d_identity_equal(background%surface_pressure,candidate%surface_pressure) .OR. &
        .NOT.optional_field2d_identity_equal(background%surface_temperature,candidate%surface_temperature) .OR. &
        .NOT.optional_field2d_identity_equal(background%surface_vapor,candidate%surface_vapor) .OR. &
        .NOT.optional_field2d_identity_equal(background%surface_height,candidate%surface_height) .OR. &
        .NOT.optional_field2d_identity_equal(background%omega_top_boundary,candidate%omega_top_boundary) .OR. &
        .NOT.optional_field2d_identity_equal(background%omega_bottom_boundary,candidate%omega_bottom_boundary)) THEN
      evaluation%physical_feasibility_status=PHYSICAL_FEASIBILITY_UNSUPPORTED
      evaluation%physical_feasibility_reason=REASON_AUTHORITY
      RETURN
    END IF
    IF (.NOT.field3d_identity_metadata_equal(background%pressure,candidate%pressure,shape3)) THEN
      evaluation%physical_feasibility_status=PHYSICAL_FEASIBILITY_UNSUPPORTED
      evaluation%physical_feasibility_reason=REASON_AUTHORITY
      RETURN
    END IF
    IF (.NOT.optional_field3d_identity_equal(background%omega_target,candidate%omega_target,shape3) .OR. &
        .NOT.optional_field3d_identity_equal(background%omega_target_sigma,candidate%omega_target_sigma,shape3) .OR. &
        .NOT.optional_field3d_identity_equal(background%cloud_fraction,candidate%cloud_fraction,shape3) .OR. &
        .NOT.optional_field3d_identity_equal(background%radar_reflectivity,candidate%radar_reflectivity,shape3)) THEN
      evaluation%physical_feasibility_status=PHYSICAL_FEASIBILITY_UNSUPPORTED
      evaluation%physical_feasibility_reason=REASON_AUTHORITY
      RETURN
    END IF
    IF (ANY((background%above_ground .OR. candidate%above_ground) .AND. .NOT.contract%coverage)) THEN
      evaluation%physical_feasibility_reason=REASON_REQUIRED_COVERAGE
      RETURN
    END IF
    IF (ANY(.NOT.ieee_is_finite(contract%source_increment)) .OR. &
        ANY(.NOT.ieee_is_finite(contract%boundary_increment)) .OR. &
        ANY(.NOT.ieee_is_finite(contract%physical_tolerance))) THEN
      evaluation%physical_feasibility_reason=REASON_NONFINITE
      RETURN
    END IF
    IF (ANY(contract%physical_tolerance<0.0_real64)) THEN
      evaluation%physical_feasibility_reason=REASON_RANGE
      RETURN
    END IF
    IF (IAND(contract%adjustable_variables,NOT(ISHFT(1,11)-1))/=0) THEN
      evaluation%physical_feasibility_reason=REASON_AUTHORITY
      RETURN
    END IF
    IF (.NOT.field_arrays_match(background%temperature,shape3) .OR. &
        .NOT.field_arrays_match(candidate%temperature,shape3) .OR. &
        .NOT.field_arrays_match(background%vapor,shape3) .OR. &
        .NOT.field_arrays_match(candidate%vapor,shape3) .OR. &
        .NOT.field_arrays_match(background%cloud_water,shape3) .OR. &
        .NOT.field_arrays_match(candidate%cloud_water,shape3) .OR. &
        .NOT.field_arrays_match(background%cloud_ice,shape3) .OR. &
        .NOT.field_arrays_match(candidate%cloud_ice,shape3) .OR. &
        .NOT.field_arrays_match(background%rain,shape3) .OR. &
        .NOT.field_arrays_match(candidate%rain,shape3) .OR. &
        .NOT.field_arrays_match(background%snow,shape3) .OR. &
        .NOT.field_arrays_match(candidate%snow,shape3) .OR. &
        .NOT.field_arrays_match(background%graupel,shape3) .OR. &
        .NOT.field_arrays_match(candidate%graupel,shape3)) THEN
      evaluation%physical_feasibility_status=PHYSICAL_FEASIBILITY_UNSUPPORTED
      evaluation%physical_feasibility_reason=REASON_REQUIRED_COVERAGE
      RETURN
    END IF
    IF (.NOT.adjusted_field_allowed(background%temperature,candidate%temperature,shape3, &
        contract%adjustable_variables,PHYSICAL_ADJUST_TEMPERATURE) .OR. &
        .NOT.adjusted_field_allowed(background%vapor,candidate%vapor,shape3, &
        contract%adjustable_variables,PHYSICAL_ADJUST_VAPOR) .OR. &
        .NOT.adjusted_field_allowed(background%cloud_water,candidate%cloud_water,shape3, &
        contract%adjustable_variables,PHYSICAL_ADJUST_CLOUD_WATER) .OR. &
        .NOT.adjusted_field_allowed(background%cloud_ice,candidate%cloud_ice,shape3, &
        contract%adjustable_variables,PHYSICAL_ADJUST_CLOUD_ICE) .OR. &
        .NOT.adjusted_field_allowed(background%rain,candidate%rain,shape3, &
        contract%adjustable_variables,PHYSICAL_ADJUST_RAIN) .OR. &
        .NOT.adjusted_field_allowed(background%snow,candidate%snow,shape3, &
        contract%adjustable_variables,PHYSICAL_ADJUST_SNOW) .OR. &
        .NOT.adjusted_field_allowed(background%graupel,candidate%graupel,shape3, &
        contract%adjustable_variables,PHYSICAL_ADJUST_GRAUPEL) .OR. &
        .NOT.adjusted_field_allowed(background%u,candidate%u,shape3, &
        contract%adjustable_variables,PHYSICAL_ADJUST_U) .OR. &
        .NOT.adjusted_field_allowed(background%v,candidate%v,shape3, &
        contract%adjustable_variables,PHYSICAL_ADJUST_V) .OR. &
        .NOT.adjusted_field_allowed(background%omega,candidate%omega,shape3, &
        contract%adjustable_variables,PHYSICAL_ADJUST_OMEGA) .OR. &
        .NOT.adjusted_field_allowed(background%geopotential,candidate%geopotential,shape3, &
        contract%adjustable_variables,PHYSICAL_ADJUST_GEOPOTENTIAL)) THEN
      evaluation%physical_feasibility_reason=REASON_AUTHORITY
      RETURN
    END IF

    ALLOCATE(domain(nx,ny,nz))
    domain=background%above_ground .OR. candidate%above_ground
    DO k=1,nz; DO j=1,ny; DO i=1,nx
      IF (.NOT.domain(i,j,k)) CYCLE
      IF (.NOT.physical_cell_covered(background,i,j,k) .OR. &
          .NOT.physical_cell_covered(candidate,i,j,k)) THEN
        evaluation%physical_feasibility_reason=REASON_REQUIRED_COVERAGE
        evaluation%physical_feasibility_failed_cell=[i,j,k]
        RETURN
      END IF
      before_mass=background%grid%dry_air_mass_measure(i,j,k)
      after_mass=candidate%grid%dry_air_mass_measure(i,j,k)
      species_before=represented_water_species(background,i,j,k)
      species_after=represented_water_species(candidate,i,j,k)
      before_enthalpy=moist_species_enthalpy(REAL(background%temperature%value(i,j,k),real64),species_before)
      after_enthalpy=moist_species_enthalpy(REAL(candidate%temperature%value(i,j,k),real64),species_after)
      DO c=1,8
        source=contract%source_increment(c,i,j,k)
        boundary=contract%boundary_increment(c,i,j,k)
        IF (c==PHYSICAL_COMPONENT_DRY_MASS_METRIC) THEN
          after_term=after_mass; before_term=before_mass
        ELSE IF (c==PHYSICAL_COMPONENT_ENTHALPY) THEN
          after_term=after_mass*after_enthalpy; before_term=before_mass*before_enthalpy
        ELSE
          after_term=after_mass*species_after(c-1)
          before_term=before_mass*species_before(c-1)
        END IF
        IF (.NOT.increment_matches(after_term,before_term,source,boundary, &
            contract%physical_tolerance(c,i,j,k),scaled_residual)) THEN
          CALL record_physical_failure(evaluation,i,j,k,c,scaled_residual)
          RETURN
        END IF
      END DO
    END DO; END DO; END DO
    evaluation%physical_feasibility_cells=COUNT(domain,KIND=int64)
    evaluation%physical_feasibility_status=PHYSICAL_FEASIBILITY_PASS
    evaluation%physical_feasibility_reason=REASON_NONE
  END SUBROUTINE assess_physical_joint_candidate

  SUBROUTINE preflight_physical_mass_contract(state,contract,evaluation)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    TYPE(physical_joint_candidate_contract), INTENT(IN) :: contract
    TYPE(joint_candidate_evaluation), INTENT(OUT) :: evaluation
    REAL(real64) :: scale,residual_scaled,tolerance_scaled,arithmetic_scaled,pressure_mass
    REAL(real64) :: source(7),boundary(7),tolerance(7)
    INTEGER :: i,j,k,nx,ny,nz

    evaluation%physical_feasibility_status=PHYSICAL_FEASIBILITY_UNSUPPORTED
    evaluation%physical_feasibility_reason=REASON_NONE
    IF (.NOT.ALLOCATED(state%above_ground) .OR. .NOT.ALLOCATED(state%grid%pressure_mass_measure)) RETURN
    IF (.NOT.ALLOCATED(contract%coverage) .OR. .NOT.ALLOCATED(contract%source_increment) .OR. &
        .NOT.ALLOCATED(contract%boundary_increment) .OR. .NOT.ALLOCATED(contract%physical_tolerance)) RETURN
    nx=state%grid%nx; ny=state%grid%ny; nz=state%grid%nz
    IF (ANY(SHAPE(state%above_ground)/=(/nx,ny,nz/)) .OR. &
        ANY(SHAPE(state%grid%pressure_mass_measure)/=(/nx,ny,nz/))) RETURN
    IF (ANY(SHAPE(contract%coverage)/=(/nx,ny,nz/)) .OR. &
        ANY(SHAPE(contract%source_increment)/=(/8,nx,ny,nz/)) .OR. &
        ANY(SHAPE(contract%boundary_increment)/=(/8,nx,ny,nz/)) .OR. &
        ANY(SHAPE(contract%physical_tolerance)/=(/8,nx,ny,nz/))) RETURN
    IF (ANY(.NOT.ieee_is_finite(contract%source_increment(1:7,:,:,:))) .OR. &
        ANY(.NOT.ieee_is_finite(contract%boundary_increment(1:7,:,:,:))) .OR. &
        ANY(.NOT.ieee_is_finite(contract%physical_tolerance(1:7,:,:,:)))) THEN
      evaluation%physical_feasibility_status=PHYSICAL_FEASIBILITY_FAILED
      evaluation%physical_feasibility_reason=REASON_NONFINITE
      RETURN
    END IF
    IF (ANY(contract%physical_tolerance(1:7,:,:,:)<0.0_real64)) THEN
      evaluation%physical_feasibility_status=PHYSICAL_FEASIBILITY_FAILED
      evaluation%physical_feasibility_reason=REASON_RANGE
      RETURN
    END IF
    evaluation%physical_feasibility_status=PHYSICAL_FEASIBILITY_PASS
    DO k=1,nz; DO j=1,ny; DO i=1,nx
      IF (.NOT.state%above_ground(i,j,k) .OR. .NOT.contract%coverage(i,j,k)) CYCLE
      source=contract%source_increment(1:7,i,j,k)
      boundary=contract%boundary_increment(1:7,i,j,k)
      tolerance=contract%physical_tolerance(1:7,i,j,k)
      pressure_mass=state%grid%pressure_mass_measure(i,j,k)
      IF (.NOT.ieee_is_finite(pressure_mass)) THEN
        evaluation%physical_feasibility_status=PHYSICAL_FEASIBILITY_FAILED
        evaluation%physical_feasibility_reason=REASON_NONFINITE
        evaluation%physical_feasibility_failed_cell=[i,j,k]
        evaluation%physical_feasibility_failed_component=PHYSICAL_COMPONENT_TOTAL_MASS
        RETURN
      END IF
      IF (pressure_mass<=0.0_real64) THEN
        evaluation%physical_feasibility_status=PHYSICAL_FEASIBILITY_FAILED
        evaluation%physical_feasibility_reason=REASON_RANGE
        evaluation%physical_feasibility_failed_cell=[i,j,k]
        evaluation%physical_feasibility_failed_component=PHYSICAL_COMPONENT_TOTAL_MASS
        RETURN
      END IF
      scale=MAX(ABS(pressure_mass),MAXVAL(ABS(source)),MAXVAL(ABS(boundary)),MAXVAL(tolerance))
      IF (scale==0.0_real64) CYCLE
      residual_scaled=SUM(source/scale+boundary/scale)
      tolerance_scaled=SUM(tolerance/scale)
      arithmetic_scaled=64.0_real64*EPSILON(1.0_real64)* &
        (ABS(pressure_mass/scale)+SUM(ABS(source/scale))+SUM(ABS(boundary/scale)))
      IF (ABS(residual_scaled)>tolerance_scaled+arithmetic_scaled) THEN
        evaluation%physical_feasibility_status=PHYSICAL_FEASIBILITY_FAILED
        evaluation%physical_feasibility_reason=REASON_GATE
        evaluation%physical_feasibility_failed_cell=[i,j,k]
        evaluation%physical_feasibility_failed_component=PHYSICAL_COMPONENT_TOTAL_MASS
        evaluation%physical_feasibility_residual_scaled=residual_scaled
        RETURN
      END IF
    END DO; END DO; END DO
  END SUBROUTINE preflight_physical_mass_contract

  LOGICAL FUNCTION adjusted_field_allowed(background,candidate,expected_shape,adjustable_variables,variable_bit)
    TYPE(field3d), INTENT(IN) :: background,candidate
    INTEGER, INTENT(IN) :: expected_shape(3),adjustable_variables,variable_bit
    LOGICAL :: background_present,candidate_present
    INTEGER(int32), PARAMETER :: stage_sources=IOR(SOURCE_COLUMN_PHYSICS,SOURCE_BALANCE_OPERATOR)
    INTEGER(int32), PARAMETER :: allowed_source_additions=IOR(stage_sources, &
      IOR(SOURCE_RADAR_DBZ,SOURCE_CLOUD_ANALYSIS))
    adjusted_field_allowed=.FALSE.
    background_present=field3d_any_allocated(background)
    candidate_present=field3d_any_allocated(candidate)
    IF (.NOT.background_present .AND. .NOT.candidate_present) THEN
      adjusted_field_allowed=.TRUE.
      RETURN
    END IF
    IF (background_present .NEQV. candidate_present) THEN
      RETURN
    END IF
    IF (.NOT.field_arrays_match(background,expected_shape) .OR. &
        .NOT.field_arrays_match(candidate,expected_shape)) RETURN
    IF (background%unit/=candidate%unit .OR. background%valid_time/=candidate%valid_time .OR. &
        ANY(background%valid .NEQV. candidate%valid) .OR. &
        ANY(background%quality/=candidate%quality)) RETURN
    IF (.NOT.valid_values_equal(background%value,candidate%value,background%valid) .OR. &
        ANY(background%source/=candidate%source)) THEN
      IF (IAND(adjustable_variables,variable_bit)==0) RETURN
      IF (ANY(IAND(candidate%source,NOT(SOURCE_KNOWN_BITS))/=0_int32) .OR. &
          ANY(IAND(candidate%source,SOURCE_MANUFACTURED_TEST)/=0_int32)) RETURN
      IF (ANY(IAND(IAND(candidate%source,NOT(background%source)), &
          NOT(allowed_source_additions))/=0_int32)) RETURN
      IF (valid_value_changed_without_stage(background%value,candidate%value,background%valid, &
          candidate%source,stage_sources) .OR. &
          ANY((background%source/=candidate%source) .AND. IAND(candidate%source,stage_sources)==0_int32)) RETURN
    END IF
    adjusted_field_allowed=.TRUE.
  END FUNCTION adjusted_field_allowed

  LOGICAL FUNCTION field3d_identity_metadata_equal(background,candidate,expected_shape)
    TYPE(field3d), INTENT(IN) :: background,candidate
    INTEGER, INTENT(IN) :: expected_shape(3)
    field3d_identity_metadata_equal=.FALSE.
    IF (.NOT.field_arrays_match(background,expected_shape) .OR. &
        .NOT.field_arrays_match(candidate,expected_shape)) RETURN
    IF (background%unit/=candidate%unit .OR. background%valid_time/=candidate%valid_time) RETURN
    IF (ANY(background%valid .NEQV. candidate%valid)) RETURN
    IF (.NOT.valid_values_equal(background%value,candidate%value,background%valid)) RETURN
    field3d_identity_metadata_equal=ALL(background%quality==candidate%quality) .AND. &
      ALL(background%source==candidate%source)
  END FUNCTION field3d_identity_metadata_equal

  LOGICAL FUNCTION valid_values_equal(left,right,valid)
    REAL(real32), INTENT(IN) :: left(:,:,:),right(:,:,:)
    LOGICAL, INTENT(IN) :: valid(:,:,:)
    INTEGER :: i,j,k
    valid_values_equal=.FALSE.
    DO k=1,SIZE(valid,3); DO j=1,SIZE(valid,2); DO i=1,SIZE(valid,1)
      IF (.NOT.valid(i,j,k)) CYCLE
      IF (.NOT.ieee_is_finite(left(i,j,k)) .OR. .NOT.ieee_is_finite(right(i,j,k))) RETURN
      IF (left(i,j,k)/=right(i,j,k)) RETURN
    END DO; END DO; END DO
    valid_values_equal=.TRUE.
  END FUNCTION valid_values_equal

  LOGICAL FUNCTION valid_value_changed_without_stage(left,right,valid,source,stage_sources)
    REAL(real32), INTENT(IN) :: left(:,:,:),right(:,:,:)
    LOGICAL, INTENT(IN) :: valid(:,:,:)
    INTEGER(int32), INTENT(IN) :: source(:,:,:),stage_sources
    INTEGER :: i,j,k
    valid_value_changed_without_stage=.FALSE.
    DO k=1,SIZE(valid,3); DO j=1,SIZE(valid,2); DO i=1,SIZE(valid,1)
      IF (.NOT.valid(i,j,k)) CYCLE
      IF (.NOT.ieee_is_finite(left(i,j,k)) .OR. .NOT.ieee_is_finite(right(i,j,k))) THEN
        valid_value_changed_without_stage=.TRUE.
        RETURN
      END IF
      IF (left(i,j,k)/=right(i,j,k) .AND. IAND(source(i,j,k),stage_sources)==0_int32) THEN
        valid_value_changed_without_stage=.TRUE.
        RETURN
      END IF
    END DO; END DO; END DO
  END FUNCTION valid_value_changed_without_stage

  LOGICAL FUNCTION optional_field3d_identity_equal(background,candidate,expected_shape)
    TYPE(field3d), INTENT(IN) :: background,candidate
    INTEGER, INTENT(IN) :: expected_shape(3)
    LOGICAL :: background_present,candidate_present
    background_present=field3d_any_allocated(background)
    candidate_present=field3d_any_allocated(candidate)
    optional_field3d_identity_equal=.FALSE.
    IF (.NOT.background_present .AND. .NOT.candidate_present) THEN
      optional_field3d_identity_equal=.TRUE.
    ELSE IF (background_present .AND. candidate_present) THEN
      optional_field3d_identity_equal=field3d_identity_metadata_equal(background,candidate,expected_shape)
    END IF
  END FUNCTION optional_field3d_identity_equal

  LOGICAL FUNCTION physical_cell_covered(state,i,j,k)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    INTEGER, INTENT(IN) :: i,j,k
    physical_cell_covered=cell_is_usable(state%temperature%valid(i,j,k),state%temperature%quality(i,j,k), &
      state%temperature%source(i,j,k),state%temperature%valid_time,state%pressure%valid_time) .AND. &
      cell_is_usable(state%vapor%valid(i,j,k),state%vapor%quality(i,j,k),state%vapor%source(i,j,k), &
      state%vapor%valid_time,state%pressure%valid_time) .AND. &
      cell_is_usable(state%cloud_water%valid(i,j,k),state%cloud_water%quality(i,j,k), &
      state%cloud_water%source(i,j,k),state%cloud_water%valid_time,state%pressure%valid_time) .AND. &
      cell_is_usable(state%cloud_ice%valid(i,j,k),state%cloud_ice%quality(i,j,k), &
      state%cloud_ice%source(i,j,k),state%cloud_ice%valid_time,state%pressure%valid_time) .AND. &
      cell_is_usable(state%rain%valid(i,j,k),state%rain%quality(i,j,k),state%rain%source(i,j,k), &
      state%rain%valid_time,state%pressure%valid_time) .AND. &
      cell_is_usable(state%snow%valid(i,j,k),state%snow%quality(i,j,k),state%snow%source(i,j,k), &
      state%snow%valid_time,state%pressure%valid_time) .AND. &
      cell_is_usable(state%graupel%valid(i,j,k),state%graupel%quality(i,j,k), &
      state%graupel%source(i,j,k),state%graupel%valid_time,state%pressure%valid_time)
  END FUNCTION physical_cell_covered

  SUBROUTINE record_physical_failure(evaluation,i,j,k,component,residual_scaled)
    TYPE(joint_candidate_evaluation), INTENT(INOUT) :: evaluation
    INTEGER, INTENT(IN) :: i,j,k,component
    REAL(real64), INTENT(IN) :: residual_scaled
    evaluation%physical_feasibility_status=PHYSICAL_FEASIBILITY_FAILED
    evaluation%physical_feasibility_reason=REASON_GATE
    evaluation%physical_feasibility_failed_cell=[i,j,k]
    evaluation%physical_feasibility_failed_component=component
    evaluation%physical_feasibility_residual_scaled=residual_scaled
  END SUBROUTINE record_physical_failure

  LOGICAL FUNCTION increment_matches(after_term,before_term,source,boundary,physical_tolerance,residual_scaled)
    REAL(real64), INTENT(IN) :: after_term,before_term,source,boundary,physical_tolerance
    REAL(real64), INTENT(OUT) :: residual_scaled
    REAL(real64) :: scale,tolerance_scaled
    increment_matches=.FALSE.
    residual_scaled=0.0_real64
    IF (ANY(.NOT.ieee_is_finite([after_term,before_term,source,boundary,physical_tolerance]))) RETURN
    IF (physical_tolerance<0.0_real64) RETURN
    scale=MAX(ABS(after_term),ABS(before_term),ABS(source),ABS(boundary),physical_tolerance)
    IF (scale==0.0_real64) THEN
      increment_matches=.TRUE.
      RETURN
    END IF
    residual_scaled=after_term/scale-before_term/scale-source/scale-boundary/scale
    tolerance_scaled=physical_tolerance/scale+64.0_real64*EPSILON(1.0_real64)* &
      (ABS(source/scale)+ABS(boundary/scale)+ABS(after_term/scale)+ABS(before_term/scale))
    increment_matches=ABS(residual_scaled)<=tolerance_scaled
  END FUNCTION increment_matches

  SUBROUTINE build_candidate_evaluation_domain(background,candidate,changed,requested,status,reason)
    TYPE(cloud_bal_state_type), INTENT(IN) :: background,candidate
    LOGICAL, INTENT(OUT) :: changed(:,:,:),requested(:,:,:)
    INTEGER, INTENT(OUT) :: status,reason
    LOGICAL, ALLOCATABLE :: geometry_changed(:,:),domain_union(:,:,:),pressure_change(:,:,:)
    LOGICAL, ALLOCATABLE :: surface_pressure_change(:,:),surface_thermo_change(:,:)
    LOGICAL, ALLOCATABLE :: surface_height_change(:,:)
    INTEGER :: nx,ny,nz,i,j,k,allocation_status

    status=STATUS_FAILED; reason=REASON_SHAPE
    nx=background%grid%nx; ny=background%grid%ny; nz=background%grid%nz
    changed=.FALSE.; requested=.FALSE.
    IF (nx<1 .OR. ny<1 .OR. nz<2) RETURN
    IF (candidate%grid%nx/=nx .OR. candidate%grid%ny/=ny .OR. &
        candidate%grid%nz/=nz) RETURN
    IF (ANY(SHAPE(changed)/=(/nx,ny,nz/)) .OR. &
        ANY(SHAPE(requested)/=(/nx,ny,nz/))) RETURN
    IF (.NOT.ALLOCATED(background%above_ground) .OR. &
        .NOT.ALLOCATED(candidate%above_ground) .OR. &
        .NOT.ALLOCATED(background%grid%pressure_interface) .OR. &
        .NOT.ALLOCATED(candidate%grid%pressure_interface)) RETURN
    IF (ANY(SHAPE(background%above_ground)/=(/nx,ny,nz/)) .OR. &
        ANY(SHAPE(candidate%above_ground)/=(/nx,ny,nz/)) .OR. &
        ANY(SHAPE(background%grid%pressure_interface)/=(/nx,ny,nz+1/)) .OR. &
        ANY(SHAPE(candidate%grid%pressure_interface)/=(/nx,ny,nz+1/))) RETURN
    IF (.NOT.candidate_evaluation_inputs_valid(background,candidate,nx,ny,nz)) RETURN
    ALLOCATE(geometry_changed(nx,ny),domain_union(nx,ny,nz),pressure_change(nx,ny,nz), &
      surface_pressure_change(nx,ny),surface_thermo_change(nx,ny), &
      surface_height_change(nx,ny), &
      STAT=allocation_status)
    IF (allocation_status/=0) THEN
      reason=REASON_RANGE
      RETURN
    END IF
    domain_union=background%above_ground .OR. candidate%above_ground
    geometry_changed=.FALSE.
    DO j=1,ny; DO i=1,nx
      geometry_changed(i,j)=ANY(background%above_ground(i,j,:) .NEQV. &
        candidate%above_ground(i,j,:)) .OR. &
        ANY(background%grid%pressure_interface(i,j,:) /= &
            candidate%grid%pressure_interface(i,j,:))
    END DO; END DO
    surface_pressure_change=field2d_change_vector(background%surface_pressure, &
      candidate%surface_pressure)
    geometry_changed=geometry_changed .OR. surface_pressure_change
    surface_height_change=field2d_change_vector(background%surface_height,candidate%surface_height)
    geometry_changed=geometry_changed .OR. surface_height_change
    surface_thermo_change=field2d_change_vector(background%surface_temperature, &
      candidate%surface_temperature) .OR. &
      field2d_change_vector(background%surface_vapor,candidate%surface_vapor)

    CALL add_field_change(background%temperature,candidate%temperature,changed)
    CALL add_field_change(background%vapor,candidate%vapor,changed)
    CALL add_field_change(background%cloud_water,candidate%cloud_water,changed)
    CALL add_field_change(background%cloud_ice,candidate%cloud_ice,changed)
    CALL add_field_change(background%rain,candidate%rain,changed)
    CALL add_field_change(background%snow,candidate%snow,changed)
    CALL add_field_change(background%graupel,candidate%graupel,changed)
    CALL add_field_change(background%u,candidate%u,changed)
    CALL add_field_change(background%v,candidate%v,changed)
    CALL add_field_change(background%omega,candidate%omega,changed)
    CALL add_optional_field_change(background%geopotential,candidate%geopotential, &
      changed,domain_union)
    pressure_change=field_change_vector(background%pressure,candidate%pressure)
    changed=changed .OR. pressure_change
    DO j=1,ny; DO i=1,nx
      IF (ANY(pressure_change(i,j,:))) geometry_changed(i,j)=.TRUE.
      IF (geometry_changed(i,j)) changed(i,j,:)=changed(i,j,:) .OR. domain_union(i,j,:)
      IF (surface_thermo_change(i,j)) THEN
        DO k=1,nz
          IF (domain_union(i,j,k)) THEN
            changed(i,j,k)=.TRUE.
            EXIT
          END IF
        END DO
      END IF
    END DO; END DO

    changed=changed .AND. domain_union
    requested=changed
    DO k=1,nz; DO j=1,ny; DO i=1,nx
      IF (.NOT.changed(i,j,k)) CYCLE
      IF (i>1) requested(i-1,j,k)=.TRUE.
      IF (i<nx) requested(i+1,j,k)=.TRUE.
      IF (j>1) requested(i,j-1,k)=.TRUE.
      IF (j<ny) requested(i,j+1,k)=.TRUE.
      IF (k>1) requested(i,j,k-1)=.TRUE.
      IF (k<nz) requested(i,j,k+1)=.TRUE.
    END DO; END DO; END DO
    requested=requested .AND. domain_union
    status=STATUS_OK; reason=REASON_NONE
  END SUBROUTINE build_candidate_evaluation_domain

  SUBROUTINE add_field_change(background,candidate,mask)
    TYPE(field3d), INTENT(IN) :: background,candidate
    LOGICAL, INTENT(INOUT) :: mask(:,:,:)
    mask=mask .OR. field_change_vector(background,candidate)
  END SUBROUTINE add_field_change

  SUBROUTINE add_optional_field_change(background,candidate,mask,domain_union)
    TYPE(field3d), INTENT(IN) :: background,candidate
    LOGICAL, INTENT(INOUT) :: mask(:,:,:)
    LOGICAL, INTENT(IN) :: domain_union(:,:,:)
    LOGICAL :: background_present,candidate_present
    background_present=field3d_any_allocated(background)
    candidate_present=field3d_any_allocated(candidate)
    IF (.NOT.background_present .AND. .NOT.candidate_present) RETURN
    IF (background_present .AND. candidate_present) THEN
      CALL add_field_change(background,candidate,mask)
    ELSE
      mask=mask .OR. domain_union
    END IF
  END SUBROUTINE add_optional_field_change

  LOGICAL FUNCTION field3d_any_allocated(field)
    TYPE(field3d), INTENT(IN) :: field
    field3d_any_allocated=ALLOCATED(field%value) .OR. ALLOCATED(field%valid) .OR. &
      ALLOCATED(field%quality) .OR. ALLOCATED(field%source)
  END FUNCTION field3d_any_allocated

  LOGICAL FUNCTION field2d_any_allocated(field)
    TYPE(field2d), INTENT(IN) :: field
    field2d_any_allocated=ALLOCATED(field%value) .OR. ALLOCATED(field%valid) .OR. &
      ALLOCATED(field%quality) .OR. ALLOCATED(field%source)
  END FUNCTION field2d_any_allocated

  LOGICAL FUNCTION optional_field3d_pair_valid(background,candidate,expected_shape)
    TYPE(field3d), INTENT(IN) :: background,candidate
    INTEGER, INTENT(IN) :: expected_shape(3)
    LOGICAL :: background_present,candidate_present
    optional_field3d_pair_valid=.FALSE.
    background_present=field3d_any_allocated(background)
    candidate_present=field3d_any_allocated(candidate)
    IF (.NOT.background_present .AND. .NOT.candidate_present) THEN
      optional_field3d_pair_valid=.TRUE.
      RETURN
    END IF
    optional_field3d_pair_valid=.TRUE.
    IF (background_present) &
      optional_field3d_pair_valid=optional_field3d_pair_valid .AND. &
        field_arrays_match(background,expected_shape)
    IF (candidate_present) &
      optional_field3d_pair_valid=optional_field3d_pair_valid .AND. &
        field_arrays_match(candidate,expected_shape)
  END FUNCTION optional_field3d_pair_valid

  LOGICAL FUNCTION optional_field2d_identity_equal(background,candidate)
    TYPE(field2d), INTENT(IN) :: background,candidate
    LOGICAL :: background_present,candidate_present
    background_present=field2d_any_allocated(background)
    candidate_present=field2d_any_allocated(candidate)
    optional_field2d_identity_equal=.FALSE.
    IF (.NOT.background_present .AND. .NOT.candidate_present) THEN
      optional_field2d_identity_equal=.TRUE.
    ELSE IF (background_present .AND. candidate_present) THEN
      optional_field2d_identity_equal=safe_field2d_identity_equal(background,candidate)
    END IF
  END FUNCTION optional_field2d_identity_equal

  LOGICAL FUNCTION safe_field2d_identity_equal(left,right)
    TYPE(field2d), INTENT(IN) :: left,right
    INTEGER :: i,j
    safe_field2d_identity_equal=.FALSE.
    IF (left%valid_time/=right%valid_time .OR. left%unit/=right%unit) RETURN
    IF (.NOT.allocated(left%value) .OR. .NOT.allocated(right%value) .OR. &
        .NOT.allocated(left%valid) .OR. .NOT.allocated(right%valid) .OR. &
        .NOT.allocated(left%quality) .OR. .NOT.allocated(right%quality) .OR. &
        .NOT.allocated(left%source) .OR. .NOT.allocated(right%source)) RETURN
    IF (ANY(SHAPE(left%value)/=SHAPE(right%value)) .OR. &
        ANY(SHAPE(left%valid)/=SHAPE(right%valid)) .OR. &
        ANY(SHAPE(left%quality)/=SHAPE(right%quality)) .OR. &
        ANY(SHAPE(left%source)/=SHAPE(right%source))) RETURN
    IF (ANY(left%valid .NEQV. right%valid)) RETURN
    IF (ANY(left%quality/=right%quality) .OR. ANY(left%source/=right%source)) RETURN
    DO j=1,SIZE(left%valid,2); DO i=1,SIZE(left%valid,1)
      IF (.NOT.left%valid(i,j)) CYCLE
      IF (.NOT.ieee_is_finite(left%value(i,j)) .OR. .NOT.ieee_is_finite(right%value(i,j))) RETURN
      IF (left%value(i,j)/=right%value(i,j)) RETURN
    END DO; END DO
    safe_field2d_identity_equal=.TRUE.
  END FUNCTION safe_field2d_identity_equal

  FUNCTION field_change_vector(background,candidate) RESULT(changed)
    TYPE(field3d), INTENT(IN) :: background,candidate
    LOGICAL, ALLOCATABLE :: changed(:,:,:)
    INTEGER :: nx,ny,nz
    nx=SIZE(background%value,1); ny=SIZE(background%value,2); nz=SIZE(background%value,3)
    ALLOCATE(changed(nx,ny,nz))
    changed=(background%valid .NEQV. candidate%valid) .OR. &
      (background%quality/=candidate%quality) .OR. &
      (background%source/=candidate%source)
    BLOCK
      INTEGER :: i,j,k
      DO k=1,nz; DO j=1,ny; DO i=1,nx
        IF (.NOT.background%valid(i,j,k) .AND. .NOT.candidate%valid(i,j,k)) CYCLE
        IF (.NOT.background%valid(i,j,k) .OR. .NOT.candidate%valid(i,j,k)) CYCLE
        IF (.NOT.ieee_is_finite(background%value(i,j,k)) .OR. &
            .NOT.ieee_is_finite(candidate%value(i,j,k))) THEN
          changed(i,j,k)=.TRUE.
        ELSE
          changed(i,j,k)=changed(i,j,k) .OR. background%value(i,j,k)/=candidate%value(i,j,k)
        END IF
      END DO; END DO; END DO
    END BLOCK
  END FUNCTION field_change_vector

  FUNCTION field2d_change_vector(background,candidate) RESULT(changed)
    TYPE(field2d), INTENT(IN) :: background,candidate
    LOGICAL, ALLOCATABLE :: changed(:,:)
    INTEGER :: nx,ny
    ! Callers validate both complete field allocations and shapes before this
    ! private comparison helper is reached.
    nx=SIZE(background%value,1); ny=SIZE(background%value,2)
    ALLOCATE(changed(nx,ny))
    changed=(background%value/=candidate%value) .OR. &
      (background%valid .NEQV. candidate%valid) .OR. &
      (background%quality/=candidate%quality) .OR. &
      (background%source/=candidate%source)
  END FUNCTION field2d_change_vector

  LOGICAL FUNCTION candidate_evaluation_inputs_valid(background,candidate,nx,ny,nz)
    TYPE(cloud_bal_state_type), INTENT(IN) :: background,candidate
    INTEGER, INTENT(IN) :: nx,ny,nz
    INTEGER :: shape3(3),shape2(2)
    shape3=(/nx,ny,nz/); shape2=(/nx,ny/)
    candidate_evaluation_inputs_valid=.FALSE.
    IF (.NOT.field_arrays_match(background%temperature,shape3) .OR. &
        .NOT.field_arrays_match(candidate%temperature,shape3) .OR. &
        .NOT.field_arrays_match(background%vapor,shape3) .OR. &
        .NOT.field_arrays_match(candidate%vapor,shape3) .OR. &
        .NOT.field_arrays_match(background%cloud_water,shape3) .OR. &
        .NOT.field_arrays_match(candidate%cloud_water,shape3) .OR. &
        .NOT.field_arrays_match(background%cloud_ice,shape3) .OR. &
        .NOT.field_arrays_match(candidate%cloud_ice,shape3) .OR. &
        .NOT.field_arrays_match(background%rain,shape3) .OR. &
        .NOT.field_arrays_match(candidate%rain,shape3) .OR. &
        .NOT.field_arrays_match(background%snow,shape3) .OR. &
        .NOT.field_arrays_match(candidate%snow,shape3) .OR. &
        .NOT.field_arrays_match(background%graupel,shape3) .OR. &
        .NOT.field_arrays_match(candidate%graupel,shape3) .OR. &
        .NOT.field_arrays_match(background%u,shape3) .OR. &
        .NOT.field_arrays_match(candidate%u,shape3) .OR. &
        .NOT.field_arrays_match(background%v,shape3) .OR. &
        .NOT.field_arrays_match(candidate%v,shape3) .OR. &
        .NOT.field_arrays_match(background%omega,shape3) .OR. &
        .NOT.field_arrays_match(candidate%omega,shape3) .OR. &
        .NOT.field_arrays_match(background%pressure,shape3) .OR. &
        .NOT.field_arrays_match(candidate%pressure,shape3)) RETURN
    IF (.NOT.optional_field3d_pair_valid(background%geopotential,candidate%geopotential, &
        shape3)) RETURN
    IF (.NOT.field2d_arrays_match(background%surface_pressure,shape2) .OR. &
        .NOT.field2d_arrays_match(candidate%surface_pressure,shape2)) RETURN
    IF (.NOT.field2d_arrays_match(background%surface_temperature,shape2) .OR. &
        .NOT.field2d_arrays_match(candidate%surface_temperature,shape2) .OR. &
        .NOT.field2d_arrays_match(background%surface_vapor,shape2) .OR. &
        .NOT.field2d_arrays_match(candidate%surface_vapor,shape2) .OR. &
        .NOT.field2d_arrays_match(background%surface_height,shape2) .OR. &
        .NOT.field2d_arrays_match(candidate%surface_height,shape2)) RETURN
    IF (.NOT.optional_field2d_identity_equal(background%latitude,candidate%latitude)) RETURN
    candidate_evaluation_inputs_valid=.TRUE.
  END FUNCTION candidate_evaluation_inputs_valid

  PURE LOGICAL FUNCTION field2d_arrays_match(field,expected_shape)
    TYPE(field2d), INTENT(IN) :: field
    INTEGER, INTENT(IN) :: expected_shape(2)
    field2d_arrays_match=.FALSE.
    IF (.NOT.ALLOCATED(field%value) .OR. .NOT.ALLOCATED(field%valid) .OR. &
        .NOT.ALLOCATED(field%quality) .OR. .NOT.ALLOCATED(field%source)) RETURN
    IF (ANY(SHAPE(field%value)/=expected_shape) .OR. &
        ANY(SHAPE(field%valid)/=expected_shape) .OR. &
        ANY(SHAPE(field%quality)/=expected_shape) .OR. &
        ANY(SHAPE(field%source)/=expected_shape)) RETURN
    field2d_arrays_match=.TRUE.
  END FUNCTION field2d_arrays_match

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
