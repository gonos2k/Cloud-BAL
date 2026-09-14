! One cloud/radar column-physics implementation.
!
! Radar evaporation is intentionally absent.  Reflectivity may add an
! explicitly diagnosed precipitation analysis increment and precipitation
! loading may affect the omega target, but cooling cannot affect the target
! until a paired water/temperature/enthalpy transfer is approved.
MODULE cloud_bal_column_physics
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,real128,int32,int64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  USE cloud_bal_state
  IMPLICIT NONE
  PRIVATE

  INTEGER, PARAMETER, PUBLIC :: PHASE_UNKNOWN=0,PHASE_RAIN=1,PHASE_SNOW=2
  INTEGER, PARAMETER, PUBLIC :: PHASE_FREEZING_RAIN=3,PHASE_SLEET=4
  INTEGER, PARAMETER, PUBLIC :: PHASE_GRAUPEL=5
  INTEGER, PARAMETER, PUBLIC :: SATURATION_LIQUID=1,SATURATION_ICE=2
  INTEGER, PARAMETER :: REGIME_CLEAR=0,REGIME_STRATIFORM=1
  INTEGER, PARAMETER :: REGIME_PRECIPITATING=2,REGIME_CONVECTIVE=3
  REAL(real64), PARAMETER :: EPSILON_WATER=0.622_real64
  REAL(real64), PARAMETER :: GRAVITY=9.80665_real64
  ! Dry-air mixture enthalpy convention; constants traced to the accessible
  ! KIM KDM6 driver, not a claim of identical KDM6 kinetics or native energy.
  REAL(real64), PARAMETER :: THERMO_T0=273.15_real64,THERMO_CP_DRY=1004.5_real64
  REAL(real64), PARAMETER :: SPECIES_CP(6)=[1846.4_real64,4190.0_real64,2106.0_real64, &
                                          4190.0_real64,2106.0_real64,2106.0_real64]
  REAL(real64), PARAMETER :: SPECIES_H0(6)=[2.50e6_real64,0.0_real64,-3.50e5_real64, &
                                          0.0_real64,-3.50e5_real64,-3.50e5_real64]
  REAL(real64), PARAMETER :: MISSING_PHASE_ALL_SNOW_K=268.15_real64
  REAL(real64), PARAMETER :: MISSING_PHASE_ALL_RAIN_K=275.15_real64
  INTEGER, PARAMETER :: MAX_ALLOWED_TRANSPORT_SUBSTEPS=256
  REAL(real64), PARAMETER :: MAX_LEDGER_TOLERANCE=1.0e-6_real64
  INTEGER(int32), PARAMETER :: PHASE_EVIDENCE_BITS= &
    SOURCE_RADAR_DBZ+SOURCE_CLOUD_ANALYSIS

  TYPE, PUBLIC :: column_physics_config
    REAL(real64) :: cloud_fraction_threshold=0.01_real64
    REAL(real64) :: radar_wavelength_m=0.10_real64
    REAL(real64) :: minimum_dbz=0.0_real64
    REAL(real64) :: maximum_dbz=80.0_real64
    REAL(real64) :: reference_mass_concentration=1.0e-4_real64
    REAL(real64) :: minimum_relative_fall_speed=0.30_real64
    REAL(real64) :: maximum_horizontal_substep=0.75_real64
    INTEGER :: maximum_transport_substeps=64
    REAL(real64) :: precipitation_loading_efficiency=0.08_real64
    REAL(real64) :: maximum_downdraft_ms=3.0_real64
    REAL(real64) :: maximum_downdraft_innovation_ms=2.0_real64
    REAL(real64) :: ledger_relative_tolerance=1.0e-11_real64
    REAL(real64) :: ledger_absolute_tolerance=1.0e-13_real64
  END TYPE column_physics_config

  TYPE, PUBLIC :: precipitation_flux_ledger
    REAL(real64) :: input=0.0_real64
    REAL(real64) :: deposited=0.0_real64
    REAL(real64) :: suspended=0.0_real64
    REAL(real64) :: boundary_exit=0.0_real64
    REAL(real64) :: terrain_intercept=0.0_real64
    REAL(real64) :: observation_blocked=0.0_real64
    REAL(real64) :: no_echo_blocked=0.0_real64
    REAL(real64) :: microphysical_loss=0.0_real64
    INTEGER :: maximum_required_substeps=0
  END TYPE precipitation_flux_ledger

  ! Internal cloud phase changes only, at an explicitly fixed dry-air mass.
  ! Three-species specialization of the mixture budget, not native energy.
  ! Latent change is phase enthalpy at the initial temperature, not heating.
  TYPE, PUBLIC :: cloud_thermo_budget
    REAL(real64) :: vapor_change_kg=0.0_real64
    REAL(real64) :: liquid_change_kg=0.0_real64
    REAL(real64) :: ice_change_kg=0.0_real64
    REAL(real64) :: sensible_heat_change_j=0.0_real64
    REAL(real64) :: latent_heat_change_j=0.0_real64
    REAL(real64) :: water_error_kg=0.0_real64
    REAL(real64) :: enthalpy_error_j=0.0_real64
  END TYPE cloud_thermo_budget

  TYPE, PUBLIC :: water_phase_budget
    ! Species order: vapor, cloud liquid, cloud ice, rain, snow, graupel.
    REAL(real64) :: species_change_kg(6)=0.0_real64
    REAL(real64) :: sensible_change_j=0.0_real64
    REAL(real64) :: phase_change_j=0.0_real64
    REAL(real64) :: water_error_kg=0.0_real64
    REAL(real64) :: enthalpy_error_j=0.0_real64
  END TYPE water_phase_budget

  TYPE, PUBLIC :: pressure_analysis_budget
    ! Represented mass changes between the caller's explicit stage endpoints.
    ! The pipeline keeps pre-thermo analysis and post-thermo geometry separate.
    ! Geometry changes require explicit opt-in to account_pressure_analysis.
    ! Species: vapor, cloud liquid, cloud ice, rain, snow, graupel.
    ! This is analysis bookkeeping, not conserved native dry mass or transport.
    REAL(real64) :: species_change_kg(6)=0.0_real64
    REAL(real64) :: mixing_ratio_change_kg(6)=0.0_real64
    REAL(real64) :: dry_mass_redistribution_kg(6)=0.0_real64
    REAL(real64) :: dry_air_change_kg=0.0_real64
    ! External represented-mixture enthalpy increment, not latent heating.
    REAL(real64) :: enthalpy_change_j=0.0_real64
    REAL(real64) :: geometry_mass_change_kg=0.0_real64
    ! Algebraic product split: mb*(ha-hb) + (ma-mb)*ha. The first
    ! term includes T/species changes; the second includes EVERY dry-mass
    ! change, including water-denominator changes at fixed pressure geometry.
    ! Neither term is a separately conserved process or a pure PSFC effect.
    REAL(real64) :: enthalpy_composition_change_j=0.0_real64
    REAL(real64) :: enthalpy_mass_metric_change_j=0.0_real64
    REAL(real64) :: total_mass_error_kg=0.0_real64
    REAL(real64) :: max_cell_mass_error_kg=0.0_real64
    INTEGER(int64) :: accounted_cells=0_int64
    INTEGER(int64) :: incomplete_background_cells=0_int64
    INTEGER(int64) :: incomplete_candidate_cells=0_int64
  END TYPE pressure_analysis_budget

  PUBLIC :: validate_optional_cloud_pair,precipitation_phase_contract_valid
  PUBLIC :: derive_column_physics
  PUBLIC :: account_pressure_analysis
  PUBLIC :: apply_pressure_domain_transition
  PUBLIC :: rebase_pressure_transition_prior
  PUBLIC :: column_changed_mask
  PUBLIC :: detect_cloud_sublayers
  PUBLIC :: terminal_velocity
  PUBLIC :: allocate_precipitation_phase
  PUBLIC :: missing_phase_partition
  PUBLIC :: transport_precipitation_flux
  PUBLIC :: dry_air_density
  PUBLIC :: saturation_adjust_cell
  PUBLIC :: saturation_adjust_column
  PUBLIC :: saturation_adjust_pressure_state
  PUBLIC :: moist_species_enthalpy,apply_water_phase_transfer,apply_pressure_phase_transfer
  PUBLIC :: saturation_adjust_mixture_cell
  PUBLIC :: hydrostatic_geopotential_increment
  PUBLIC :: apply_pressure_hydrostatic_increment
  PUBLIC :: remap_pressure_column
  PUBLIC :: flux_ledger_closes
  PUBLIC :: column_config_valid

CONTAINS

  SUBROUTINE derive_column_physics(state_in,state_out,result,config, &
                                   thermo_active,thermo_surface,target_rh,thermo_budget,analysis_budget,evaluation_state, &
                                   model_dynamics_target)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state_in
    TYPE(cloud_bal_state_type), INTENT(OUT) :: state_out
    TYPE(stage_result), INTENT(OUT) :: result
    TYPE(column_physics_config), INTENT(IN), OPTIONAL :: config
    LOGICAL, INTENT(IN), OPTIONAL :: thermo_active(:,:,:)
    INTEGER, INTENT(IN), OPTIONAL :: thermo_surface(:,:,:)
    REAL(real64), INTENT(IN), OPTIONAL :: target_rh
    TYPE(water_phase_budget), INTENT(OUT), OPTIONAL :: thermo_budget
    TYPE(pressure_analysis_budget), INTENT(OUT), OPTIONAL :: analysis_budget
    TYPE(cloud_bal_state_type), INTENT(IN), OPTIONAL :: evaluation_state
    LOGICAL, INTENT(IN), OPTIONAL :: model_dynamics_target
    TYPE(pressure_analysis_budget) :: proposal_budget
    TYPE(water_phase_budget) :: internal_budget
    TYPE(cloud_bal_state_type) :: thermo_candidate
    TYPE(stage_result) :: thermo_result
    TYPE(column_physics_config) :: cfg
    TYPE(cloud_bal_state_type) :: candidate,evaluation
    TYPE(stage_result) :: candidate_result
    TYPE(precipitation_flux_ledger) :: ledger
    REAL(real32), ALLOCATABLE :: w_background(:,:,:),w_target(:,:,:)
    LOGICAL, ALLOCATABLE :: w_valid(:,:,:),radar_observed(:,:,:)
    LOGICAL, ALLOCATABLE :: radar_no_echo(:,:,:),radar_derived(:,:,:)
    LOGICAL, ALLOCATABLE :: phase_uncertain(:,:,:)
    INTEGER, ALLOCATABLE :: phase(:,:,:)
    REAL(real64), ALLOCATABLE :: rain(:,:,:),snow(:,:,:),graupel(:,:,:)
    REAL(real64), ALLOCATABLE :: zlinear(:,:,:)
    REAL(real64) :: ledger_error,input_water,output_water
    INTEGER :: nx,ny,nz,status,reason
    LOGICAL :: cloud_available,has_cloud,has_radar,has_cloud_contradiction,thermo_requested
    LOGICAL :: use_model_dynamic_target

    IF (PRESENT(config)) cfg=config
    use_model_dynamic_target=.FALSE.
    IF (PRESENT(model_dynamics_target)) use_model_dynamic_target=model_dynamics_target
    internal_budget=water_phase_budget()
    IF (PRESENT(thermo_budget)) thermo_budget=internal_budget
    IF (PRESENT(analysis_budget)) analysis_budget=pressure_analysis_budget()
    thermo_requested=PRESENT(thermo_active) .OR. PRESENT(thermo_surface) .OR. PRESENT(target_rh)
    IF (thermo_requested) THEN
      IF (.NOT.PRESENT(thermo_active) .OR. .NOT.PRESENT(thermo_surface) .OR. .NOT.PRESENT(target_rh)) THEN
        CALL reject_candidate(state_in,state_out,result,STATUS_FAILED,REASON_SHAPE)
        RETURN
      END IF
      IF (ANY(SHAPE(thermo_active)/=[state_in%grid%nx,state_in%grid%ny,state_in%grid%nz]) .OR. &
          ANY(SHAPE(thermo_surface)/=SHAPE(thermo_active))) THEN
        CALL reject_candidate(state_in,state_out,result,STATUS_FAILED,REASON_SHAPE)
        RETURN
      END IF
      IF (.NOT.ieee_is_finite(target_rh)) THEN
        CALL reject_candidate(state_in,state_out,result,STATUS_FAILED,REASON_RANGE)
        RETURN
      END IF
      IF (target_rh<0.0_real64 .OR. target_rh>1.0_real64 .OR. &
          ANY(thermo_active .AND. thermo_surface/=SATURATION_LIQUID .AND. thermo_surface/=SATURATION_ICE)) THEN
        CALL reject_candidate(state_in,state_out,result,STATUS_FAILED,REASON_RANGE)
        RETURN
      END IF
      thermo_requested=ANY(thermo_active)
    END IF
    ! Surface fields are optional here because no column equation uses them.
    CALL validate_canonical_state(state_in,.FALSE.,.FALSE.,status,reason,.FALSE.)
    IF (status/=STATUS_OK) THEN
      CALL reject_candidate(state_in,state_out,result,status,reason)
      RETURN
    END IF
    IF (.NOT.column_config_valid(cfg)) THEN
      CALL reject_candidate(state_in,state_out,result,STATUS_FAILED,REASON_RANGE)
      RETURN
    END IF
    CALL validate_optional_cloud_pair(state_in,cloud_available,status,reason)
    IF (status/=STATUS_OK) THEN
      CALL reject_candidate(state_in,state_out,result,status,reason)
      RETURN
    END IF
    nx=state_in%grid%nx; ny=state_in%grid%ny; nz=state_in%grid%nz
    IF (.NOT.radar_field_contract_valid(state_in) .OR. &
        .NOT.precipitation_phase_contract_valid(state_in)) THEN
      CALL reject_candidate(state_in,state_out,result,STATUS_FAILED,REASON_RADAR_CONTRACT)
      RETURN
    END IF
    IF (.NOT.optional_hydrometeor_contract_valid(state_in) .OR. &
        .NOT.velocity_diagnostic_contract_valid(state_in)) THEN
      CALL reject_candidate(state_in,state_out,result,STATUS_FAILED,REASON_METADATA)
      RETURN
    END IF
    IF (.NOT.pristine_background(state_in)) THEN
      CALL reject_candidate(state_in,state_out,result,STATUS_FAILED,REASON_AUTHORITY)
      RETURN
    END IF
    ! A nonlinear trial supplies coefficients, never a new background or new
    ! observations. Rebuilding from state_in prevents repeated analysis increments.
    evaluation=state_in
    IF (PRESENT(evaluation_state)) THEN
      CALL validate_canonical_state(evaluation_state,.FALSE.,.FALSE.,status,reason,.FALSE.)
      IF (status/=STATUS_OK) THEN
        CALL reject_candidate(state_in,state_out,result,status,reason)
        RETURN
      END IF
      evaluation=evaluation_state
      evaluation%temperature=state_in%temperature
      evaluation%vapor=state_in%vapor
      evaluation%cloud_water=state_in%cloud_water
      evaluation%cloud_ice=state_in%cloud_ice
      IF (.NOT.canonical_states_equal(state_in,evaluation,.TRUE.)) THEN
        CALL reject_candidate(state_in,state_out,result,STATUS_FAILED,REASON_METADATA)
        RETURN
      END IF
      evaluation=state_in
      evaluation%temperature=evaluation_state%temperature
      evaluation%vapor=evaluation_state%vapor
      evaluation%u=evaluation_state%u
      evaluation%v=evaluation_state%v
      evaluation%omega=evaluation_state%omega
      CALL refresh_dry_air_mass_measure(evaluation,status)
      IF (status/=STATUS_OK) THEN
        CALL reject_candidate(state_in,state_out,result,status,REASON_RANGE)
        RETURN
      END IF
    END IF
    has_cloud=cloud_available .AND. ANY(state_in%above_ground .AND. &
      cell_is_usable(state_in%cloud_fraction%valid, &
      state_in%cloud_fraction%quality,state_in%cloud_fraction%source) .AND. &
      cell_is_usable(state_in%cloud_type%valid,state_in%cloud_type%quality, &
      state_in%cloud_type%source) .AND. &
      state_in%cloud_fraction%value>=REAL(cfg%cloud_fraction_threshold,real32) .AND. &
      state_in%cloud_type%value>0_int32)
    has_cloud_contradiction=cloud_available .AND. ANY(state_in%above_ground .AND. &
      cell_is_usable(state_in%cloud_fraction%valid, &
      state_in%cloud_fraction%quality,state_in%cloud_fraction%source) .AND. &
      cell_is_usable(state_in%cloud_type%valid,state_in%cloud_type%quality, &
      state_in%cloud_type%source) .AND. state_in%cloud_type%value>0_int32 .AND. &
      state_in%cloud_fraction%value<REAL(cfg%cloud_fraction_threshold,real32))
    has_radar=ANY(state_in%above_ground .AND. &
      cell_is_usable(state_in%radar_reflectivity%valid, &
      state_in%radar_reflectivity%quality,state_in%radar_reflectivity%source))
    IF (.NOT.has_cloud .AND. .NOT.has_radar .AND. .NOT.thermo_requested) THEN
      IF (has_cloud_contradiction) THEN
        CALL reject_candidate(state_in,state_out,result,STATUS_DEGRADED,REASON_REQUIRED_COVERAGE)
        RETURN
      END IF
      state_out=state_in
      CALL initialize_stage_result(result,nx,ny,nz,STATUS_OK,REASON_NONE)
      RETURN
    END IF
    IF (has_radar .AND. ANY(state_in%radar_reflectivity%valid .AND. &
        (REAL(state_in%radar_reflectivity%value,real64)<cfg%minimum_dbz .OR. &
         REAL(state_in%radar_reflectivity%value,real64)>cfg%maximum_dbz))) THEN
      CALL reject_candidate(state_in,state_out,result,STATUS_FAILED,REASON_RANGE)
      RETURN
    END IF

    ALLOCATE(w_background(nx,ny,nz),w_target(nx,ny,nz),w_valid(nx,ny,nz), &
             radar_observed(nx,ny,nz),radar_no_echo(nx,ny,nz), &
             radar_derived(nx,ny,nz),phase_uncertain(nx,ny,nz), &
             phase(nx,ny,nz),rain(nx,ny,nz), &
             snow(nx,ny,nz),graupel(nx,ny,nz),zlinear(nx,ny,nz))
    CALL omega_to_w(evaluation%omega%value,evaluation%pressure%value, &
      evaluation%temperature%value,evaluation%vapor%value, &
      evaluation%above_ground .AND. &
      cell_is_usable(evaluation%omega%valid,evaluation%omega%quality,evaluation%omega%source) .AND. &
      cell_is_usable(evaluation%pressure%valid,evaluation%pressure%quality, &
                     evaluation%pressure%source) .AND. &
      cell_is_usable(evaluation%temperature%valid,evaluation%temperature%quality, &
                     evaluation%temperature%source) .AND. &
      cell_is_usable(evaluation%vapor%valid,evaluation%vapor%quality,evaluation%vapor%source), &
      w_background,w_valid,status)
    IF (status/=STATUS_OK) THEN
      CALL reject_candidate(state_in,state_out,result,STATUS_FAILED,REASON_NONFINITE)
      RETURN
    END IF
    candidate=state_in
    candidate%obs_support=0_int32
    candidate%hydro_support=0_int32
    WHERE(state_in%cloud_fraction%valid .AND. state_in%cloud_type%valid .AND. &
          state_in%cloud_type%value>0_int32 .AND. &
          state_in%cloud_fraction%value<REAL(cfg%cloud_fraction_threshold,real32))
      candidate%cloud_fraction%quality= &
        IOR(candidate%cloud_fraction%quality,QUALITY_QC_REJECTED)
      candidate%cloud_type%quality=IOR(candidate%cloud_type%quality,QUALITY_QC_REJECTED)
    END WHERE
    ! Radar work is separate from immutable background hydrometeors.  A radar
    ! observation elsewhere in the domain must never transport an unrelated
    ! background precipitation field.
    rain=0.0_real64; snow=0.0_real64; graupel=0.0_real64
    radar_observed=.FALSE.; radar_no_echo=.FALSE.
    radar_derived=.FALSE.; phase_uncertain=.FALSE.
    phase=PHASE_UNKNOWN; zlinear=0.0_real64
    IF (has_radar) THEN
      CALL diagnose_radar_cells(evaluation,cfg,radar_observed,phase,zlinear, &
        rain,snow,graupel,phase_uncertain,status)
      IF (status/=STATUS_OK) THEN
        CALL reject_candidate(state_in,state_out,result,STATUS_FAILED,REASON_RADAR_CONTRACT)
        RETURN
      END IF
      IF (ANY(radar_observed .AND. .NOT.w_valid)) THEN
        ! Missing air motion is never inserted into trajectory arithmetic.
        CALL reject_candidate(state_in,state_out,result,STATUS_DEGRADED, &
                              REASON_REQUIRED_COVERAGE)
        RETURN
      END IF
      radar_no_echo=state_in%above_ground .AND. radar_no_echo_cell( &
        state_in%radar_reflectivity%value,state_in%radar_reflectivity%valid, &
        state_in%radar_reflectivity%quality,state_in%radar_reflectivity%source)
      CALL transport_precipitation_flux(evaluation%grid,evaluation%pressure%value, &
        evaluation%temperature%value,evaluation%vapor%value,evaluation%u%value, &
        evaluation%v%value,w_background,w_valid,state_in%above_ground, &
        radar_observed,phase,zlinear,rain,snow,graupel,cfg,ledger,status, &
        radar_no_echo)
      IF (status/=STATUS_OK .OR. .NOT.flux_ledger_closes(ledger,cfg)) THEN
        CALL reject_candidate(state_in,state_out,result,STATUS_FAILED,REASON_GATE)
        result%numerical%transport_required_substeps=ledger%maximum_required_substeps
        result%numerical%flux_input=ledger%input
        result%numerical%flux_deposited=ledger%deposited
        result%numerical%flux_suspended=ledger%suspended
        result%numerical%flux_boundary_exit=ledger%boundary_exit
        result%numerical%flux_terrain_intercept=ledger%terrain_intercept
        result%numerical%flux_observation_blocked=ledger%observation_blocked
        result%numerical%flux_no_echo_blocked=ledger%no_echo_blocked
        result%numerical%flux_microphysical_loss=ledger%microphysical_loss
        RETURN
      END IF
    END IF

    radar_derived=radar_observed .OR. rain>0.0_real64 .OR. snow>0.0_real64 .OR. &
                  graupel>0.0_real64
    phase_uncertain=phase_uncertain .OR. (radar_derived .AND. .NOT.radar_observed) .OR. &
      (radar_derived .AND. phase==PHASE_UNKNOWN) .OR. &
      (MERGE(1,0,rain>0.0_real64)+MERGE(1,0,snow>0.0_real64)+ &
       MERGE(1,0,graupel>0.0_real64)>1)

    CALL publish_hydrometeor_candidate(state_in,candidate,cfg, &
      radar_observed,radar_derived,phase_uncertain,phase,rain,snow,graupel,status)
    IF (status/=STATUS_OK) THEN
      CALL reject_candidate(state_in,state_out,result,STATUS_FAILED,REASON_NONFINITE)
      RETURN
    END IF
    ! Freeze the analysis ledger BEFORE internal phase exchange. Condensation
    ! cannot be counted as a new radar water increment. The retrieval remains
    ! a pressure-fixed diagnostic, not native dry-mass/pressure closure.
    input_water=hydrometeor_mass(state_in)
    output_water=hydrometeor_mass(candidate)
    CALL account_pressure_analysis(state_in,candidate,proposal_budget,status)
    IF (status/=STATUS_OK) THEN
      CALL reject_candidate(state_in,state_out,result,STATUS_FAILED,REASON_NONFINITE)
      RETURN
    END IF
    IF (thermo_requested) THEN
      CALL saturation_adjust_pressure_state(candidate,thermo_candidate,thermo_result, &
        thermo_active,target_rh,internal_budget,thermo_surface)
      IF (thermo_result%status/=STATUS_OK) THEN
        CALL reject_candidate(state_in,state_out,result,thermo_result%status,thermo_result%reason_code)
        RETURN
      END IF
      candidate=thermo_candidate
    END IF
    ! Diagnostics consume final stored thermodynamics and precipitation, while
    ! observed/zlinear retain the original reconstruction lineage. This is one
    ! ordered pass, not a converged thermo/trajectory/balance outer iteration.
    CALL omega_to_w(candidate%omega%value,candidate%pressure%value, &
      candidate%temperature%value,candidate%vapor%value,candidate%above_ground, &
      w_background,w_valid,status)
    IF (status/=STATUS_OK) THEN
      CALL reject_candidate(state_in,state_out,result,STATUS_FAILED,REASON_NONFINITE)
      RETURN
    END IF
    w_target=w_background
    IF (has_cloud) THEN
      CALL build_cloud_targets(candidate,cfg,w_valid,w_target,status)
      IF (status/=STATUS_OK) THEN
        CALL reject_candidate(state_in,state_out,result,STATUS_FAILED,REASON_GATE)
        RETURN
      END IF
    END IF
    ! Only direct echo cells feed loading, as before. Background precipitation
    ! outside that observation support never becomes a wind constraint.
    WHERE(radar_derived)
      rain=REAL(candidate%rain%value,real64)
      snow=REAL(candidate%snow%value,real64)
      graupel=REAL(candidate%graupel%value,real64)
    END WHERE
    IF (has_radar .AND. .NOT.use_model_dynamic_target) THEN
      CALL add_loading_downdraft(candidate,cfg,radar_observed,rain,snow,graupel, &
        w_background,w_target,status)
      IF (status/=STATUS_OK) THEN
        CALL reject_candidate(state_in,state_out,result,STATUS_FAILED,REASON_NONFINITE)
        RETURN
      END IF
    END IF
    CALL publish_column_diagnostics(state_in,candidate,cfg,w_target,w_valid, &
      radar_observed,radar_derived,phase_uncertain,zlinear,rain,snow,graupel, &
      use_model_dynamic_target,status)
    IF (status/=STATUS_OK) THEN
      CALL reject_candidate(state_in,state_out,result,STATUS_FAILED,REASON_NONFINITE)
      RETURN
    END IF
    CALL validate_canonical_state(candidate,.FALSE.,.FALSE.,status,reason,.FALSE.)
    IF (status/=STATUS_OK) THEN
      CALL reject_candidate(state_in,state_out,result,status,reason)
      RETURN
    END IF
    CALL initialize_stage_result(candidate_result,nx,ny,nz,STATUS_OK,REASON_NONE)
    candidate_result%changed=column_changed_mask(state_in,candidate)
    candidate_result%coverage%required=SIZE(candidate_result%changed)
    IF (use_model_dynamic_target) THEN
      candidate_result%coverage%usable=COUNT(model_dynamic_target_is_resolved( &
        candidate%omega_target%value,candidate%omega_target%valid, &
        candidate%omega_target%quality,candidate%omega_target%source))
    ELSE
      candidate_result%coverage%usable=COUNT(observational_target_is_resolved(candidate))
    END IF
    candidate_result%coverage%excluded=candidate_result%coverage%required- &
                                       candidate_result%coverage%usable
    candidate_result%coverage%usable_fraction=REAL(candidate_result%coverage%usable,real64)/ &
                                              REAL(candidate_result%coverage%required,real64)
    ledger_error=ledger%input-(ledger%deposited+ledger%suspended+ &
      ledger%boundary_exit+ledger%terrain_intercept+ledger%observation_blocked+ &
      ledger%no_echo_blocked+ledger%microphysical_loss)
    candidate_result%numerical%ledger_error=ABS(ledger_error)
    candidate_result%numerical%flux_input=ledger%input
    candidate_result%numerical%flux_deposited=ledger%deposited
    candidate_result%numerical%flux_suspended=ledger%suspended
    candidate_result%numerical%flux_boundary_exit=ledger%boundary_exit
    candidate_result%numerical%flux_terrain_intercept=ledger%terrain_intercept
    candidate_result%numerical%flux_observation_blocked=ledger%observation_blocked
    candidate_result%numerical%flux_no_echo_blocked=ledger%no_echo_blocked
    candidate_result%numerical%flux_microphysical_loss=ledger%microphysical_loss
    candidate_result%numerical%transport_required_substeps= &
      ledger%maximum_required_substeps
    candidate_result%numerical%enthalpy_error=internal_budget%enthalpy_error_j
    candidate_result%numerical%radar_analysis_increment=output_water-input_water
    ! Only this stage can publish the candidate after all column gates pass.
    state_out=candidate
    result=candidate_result
    IF (PRESENT(thermo_budget)) thermo_budget=internal_budget
    IF (PRESENT(analysis_budget)) analysis_budget=proposal_budget
  END SUBROUTINE derive_column_physics

  SUBROUTINE account_pressure_analysis(background,candidate,budget,status,allow_geometry_change,allow_domain_change)
    ! Caller contract: validated states with identical pressure centers;
    ! background validated and candidate dry mass refreshed before this call.
    ! Geometry is unchanged by the hydrometeor proposal unless explicitly
    ! accounted as an external pressure-mass increment. Include vapor: even
    ! unchanged r_v has a mass increment when the dry-mass denominator changes.
    ! Opt-in permits bookkeeping only: application/source authority belongs
    ! to the staged candidate producer, and neither input is mutated here.
    TYPE(cloud_bal_state_type), INTENT(IN) :: background,candidate
    TYPE(pressure_analysis_budget), INTENT(OUT) :: budget
    INTEGER, INTENT(OUT) :: status
    LOGICAL, INTENT(IN), OPTIONAL :: allow_geometry_change,allow_domain_change
    TYPE(pressure_analysis_budget) :: work
    REAL(real64) :: before(6),after(6),change(6),mb,ma,dm,term_limit,hb,ha,geometry_change
    LOGICAL :: geometry_allowed,domain_allowed,present_before,present_after
    INTEGER :: i,j,k
    budget=pressure_analysis_budget(); work=pressure_analysis_budget(); status=STATUS_FAILED
    geometry_allowed=.FALSE.
    IF (PRESENT(allow_geometry_change)) geometry_allowed=allow_geometry_change
    domain_allowed=.FALSE.
    IF (PRESENT(allow_domain_change)) domain_allowed=allow_domain_change
    IF (domain_allowed .AND. .NOT.geometry_allowed) RETURN
    IF (background%grid%nx/=candidate%grid%nx .OR. background%grid%ny/=candidate%grid%ny .OR. &
        background%grid%nz/=candidate%grid%nz) RETURN
    IF (.NOT.domain_allowed) THEN
      IF (ANY(background%above_ground .NEQV. candidate%above_ground)) RETURN
    END IF
    IF (background%pressure%valid_time/=candidate%pressure%valid_time) RETURN
    IF (ANY(background%pressure%value/=candidate%pressure%value)) RETURN
    IF (ANY(background%grid%dx/=candidate%grid%dx) .OR. &
        ANY(background%grid%dy/=candidate%grid%dy)) RETURN
    IF (ANY(background%grid%level_spacing_dp/=candidate%grid%level_spacing_dp)) RETURN
    IF (.NOT.geometry_allowed) THEN
      IF (ANY(background%surface_pressure%value/=candidate%surface_pressure%value) .OR. &
          ANY(background%grid%pressure_interface/=candidate%grid%pressure_interface) .OR. &
          ANY(background%grid%cell_dp/=candidate%grid%cell_dp) .OR. &
          ANY(background%grid%pressure_mass_measure/=candidate%grid%pressure_mass_measure)) RETURN
    END IF
    term_limit=HUGE(1.0_real64)/(64.0_real64* &
      REAL(MAX(1_int64,COUNT(background%above_ground .OR. candidate%above_ground,KIND=int64)),real64))
    DO k=1,background%grid%nz; DO j=1,background%grid%ny; DO i=1,background%grid%nx
      present_before=background%above_ground(i,j,k)
      present_after=candidate%above_ground(i,j,k)
      IF (.NOT.(present_before .OR. present_after)) CYCLE
      work%accounted_cells=work%accounted_cells+1_int64
      ! An absent control volume has zero extensive content, not observed
      ! zero T or mixing ratio. Never read its missing thermodynamic fields.
      ! This union-domain budget records the supplied endpoint difference;
      ! it does not authorize reconstruction or certify boundary conservation.
      before=0.0_real64; after=0.0_real64
      mb=0.0_real64; ma=0.0_real64; hb=0.0_real64; ha=0.0_real64
      IF (present_before) THEN
        before=represented_water_species(background,i,j,k)
        mb=background%grid%dry_air_mass_measure(i,j,k)
        hb=moist_species_enthalpy(REAL(background%temperature%value(i,j,k),real64),before)
      END IF
      IF (present_after) THEN
        after=represented_water_species(candidate,i,j,k)
        ma=candidate%grid%dry_air_mass_measure(i,j,k)
        ha=moist_species_enthalpy(REAL(candidate%temperature%value(i,j,k),real64),after)
      END IF
      IF (MAX(mb,ma)>term_limit/MAX(1.0_real64,MAXVAL(before),MAXVAL(after),ABS(hb),ABS(ha))) RETURN
      dm=ma-mb
      change=ma*after-mb*before
      geometry_change=candidate%grid%pressure_mass_measure(i,j,k)- &
        background%grid%pressure_mass_measure(i,j,k)
      work%geometry_mass_change_kg=work%geometry_mass_change_kg+geometry_change
      work%species_change_kg=work%species_change_kg+change
      work%max_cell_mass_error_kg=MAX(work%max_cell_mass_error_kg,ABS(dm+SUM(change)-geometry_change))
      ! Exact split: ma*ra-mb*rb = mb*(ra-rb)+(ma-mb)*ra.
      work%mixing_ratio_change_kg=work%mixing_ratio_change_kg+mb*(after-before)
      work%dry_mass_redistribution_kg=work%dry_mass_redistribution_kg+dm*after
      work%dry_air_change_kg=work%dry_air_change_kg+dm
      ! Includes the dry-air contribution: using only condensate latent heat
      ! would miss both vapor and the pressure-fixed denominator change.
      work%enthalpy_change_j=work%enthalpy_change_j+(ma*ha-mb*hb)
      work%enthalpy_composition_change_j=work%enthalpy_composition_change_j+mb*(ha-hb)
      work%enthalpy_mass_metric_change_j=work%enthalpy_mass_metric_change_j+dm*ha
      IF (present_before .AND. .NOT.ALL([background%vapor%valid(i,j,k),background%cloud_water%valid(i,j,k), &
          background%cloud_ice%valid(i,j,k),background%rain%valid(i,j,k), &
          background%snow%valid(i,j,k),background%graupel%valid(i,j,k)])) &
        work%incomplete_background_cells=work%incomplete_background_cells+1_int64
      IF (present_after .AND. .NOT.ALL([candidate%vapor%valid(i,j,k),candidate%cloud_water%valid(i,j,k), &
          candidate%cloud_ice%valid(i,j,k),candidate%rain%valid(i,j,k), &
          candidate%snow%valid(i,j,k),candidate%graupel%valid(i,j,k)])) &
        work%incomplete_candidate_cells=work%incomplete_candidate_cells+1_int64
    END DO; END DO; END DO
    ! Domain-transition accounting must not turn an unrepresented species
    ! into a zero-mass reconstruction. Legacy same-domain diagnostics retain
    ! their explicit incomplete-coverage counters.
    IF (domain_allowed) THEN
      IF (work%incomplete_background_cells>0_int64 .OR. work%incomplete_candidate_cells>0_int64) RETURN
    END IF
    work%total_mass_error_kg=work%dry_air_change_kg+SUM(work%species_change_kg)-work%geometry_mass_change_kg
    budget=work; status=STATUS_OK
  END SUBROUTINE account_pressure_analysis

  SUBROUTINE apply_pressure_domain_transition(background,prior,candidate,result,budget)
    ! Apply the first supported pressure-domain transition: a positive PS
    ! increment that activates exactly the next lower pressure center.  The
    ! explicitly supplied prior is reconstruction input, never observation
    ! authority.  Every edit is staged in work and candidate remains the
    ! unchanged background when any gate fails.
    TYPE(cloud_bal_state_type), INTENT(IN) :: background,prior
    TYPE(cloud_bal_state_type), INTENT(OUT) :: candidate
    TYPE(stage_result), INTENT(OUT) :: result
    TYPE(pressure_analysis_budget), INTENT(OUT) :: budget
    TYPE(cloud_bal_state_type) :: work
    TYPE(pressure_analysis_budget) :: staged_budget
    REAL(real64), ALLOCATABLE :: old_interfaces(:),new_interfaces(:)
    REAL(real64), ALLOCATABLE :: old_mass(:),new_mass(:),old_temperature(:),new_temperature(:),pressure_defect(:)
    REAL(real64), ALLOCATABLE :: old_species(:,:),new_species(:,:)
    REAL(real64), ALLOCATABLE :: h_background(:),h_prior(:),h_final(:)
    LOGICAL, ALLOCATABLE :: transition(:,:),changed(:,:,:)
    REAL(real64) :: old_ps,new_ps,delta_ps,area,boundary_mass,water_sum
    REAL(real64) :: expected_mass,actual_mass,mass_bound,round_slack,overlap,donor_defect
    REAL(real64) :: expected_enthalpy,actual_enthalpy,enthalpy_bound
    REAL(real64) :: expected_specific_enthalpy,actual_specific_enthalpy
    REAL(real64) :: temperature_error,species_error(6)
    REAL(real64) :: stored_species(6)
    REAL(real64) :: new_phi,phi_tolerance
    INTEGER :: nx,ny,nz,i,j,k,bottom,prior_bottom,nold,nnew,n,s,d,status,reason
    INTEGER :: allocation_status,remap_status,profile_status
    LOGICAL :: any_transition

    nx=MAX(0,background%grid%nx)
    ny=MAX(0,background%grid%ny)
    nz=MAX(0,background%grid%nz)
    candidate=background
    budget=pressure_analysis_budget()
    CALL initialize_stage_result(result,nx,ny,nz,STATUS_FAILED,REASON_SHAPE)
    IF (nx<1 .OR. ny<1 .OR. nz<2) RETURN
    IF (prior%grid%nx/=nx .OR. prior%grid%ny/=ny .OR. prior%grid%nz/=nz) RETURN

    CALL validate_canonical_state(background,.FALSE.,.FALSE.,status,reason,.FALSE.)
    IF (status==STATUS_FAILED) THEN
      result%reason_code=reason
      RETURN
    END IF
    CALL validate_canonical_state(prior,.FALSE.,.FALSE.,status,reason,.FALSE.)
    IF (status==STATUS_FAILED) THEN
      result%reason_code=reason
      RETURN
    END IF
    IF (background%pressure%valid_time/=prior%pressure%valid_time .OR. &
        ANY(background%pressure%value/=prior%pressure%value) .OR. &
        ANY(background%grid%dx/=prior%grid%dx) .OR. ANY(background%grid%dy/=prior%grid%dy) .OR. &
        background%grid%grid_id/=prior%grid%grid_id) THEN
      result%reason_code=REASON_METADATA
      RETURN
    END IF

    ALLOCATE(transition(nx,ny),changed(nx,ny,nz),STAT=allocation_status)
    IF (allocation_status/=0) RETURN
    transition=.FALSE.; changed=.FALSE.; any_transition=.FALSE.
    DO j=1,ny; DO i=1,nx
      bottom=FINDLOC(background%above_ground(i,j,:),.TRUE.,DIM=1)
      prior_bottom=FINDLOC(prior%above_ground(i,j,:),.TRUE.,DIM=1)
      IF (bottom<1 .OR. prior_bottom<1) THEN
        result%reason_code=REASON_SHAPE
        RETURN
      END IF
      old_ps=REAL(background%surface_pressure%value(i,j),real64)
      new_ps=REAL(prior%surface_pressure%value(i,j),real64)
      IF (new_ps<old_ps) THEN
        result%reason_code=REASON_RANGE
        RETURN
      END IF
      IF (new_ps==old_ps) THEN
        IF (prior_bottom/=bottom .OR. &
            ANY(prior%above_ground(i,j,:).NEQV.background%above_ground(i,j,:)) .OR. &
            ANY(prior%grid%pressure_interface(i,j,:)/=background%grid%pressure_interface(i,j,:)) .OR. &
            ANY(prior%grid%cell_dp(i,j,:)/=background%grid%cell_dp(i,j,:)) .OR. &
            ANY(prior%grid%pressure_mass_measure(i,j,:)/= &
                background%grid%pressure_mass_measure(i,j,:))) THEN
          result%reason_code=REASON_METADATA
          RETURN
        END IF
        CYCLE
      END IF
      ! A positive PS increment either thickens the existing bottom cell or
      ! activates exactly the next lower center.  The former has no new-cell
      ! authority; the latter is the explicit one-center transition.
      IF (prior_bottom==bottom) THEN
        IF (bottom>1) THEN
          IF (old_ps<REAL(background%pressure%value(i,j,bottom-1),real64) .AND. &
              new_ps>=REAL(background%pressure%value(i,j,bottom-1),real64)) THEN
            result%reason_code=REASON_RANGE
            RETURN
          END IF
        END IF
        IF (ANY(prior%above_ground(i,j,:).NEQV.background%above_ground(i,j,:))) THEN
          result%reason_code=REASON_RANGE
          RETURN
        END IF
      ELSE IF (prior_bottom==bottom-1) THEN
        IF (bottom<=1) THEN
          result%reason_code=REASON_RANGE
          RETURN
        END IF
        DO k=1,nz
          IF (k==bottom-1) THEN
            IF (.NOT.prior%above_ground(i,j,k)) THEN
              result%reason_code=REASON_RANGE
              RETURN
            END IF
          ELSE IF (prior%above_ground(i,j,k).NEQV.background%above_ground(i,j,k)) THEN
            result%reason_code=REASON_RANGE
            RETURN
          END IF
        END DO
        IF (.NOT.prior%above_ground(i,j,prior_bottom) .OR. &
            REAL(prior%pressure%value(i,j,prior_bottom),real64)>new_ps) THEN
          result%reason_code=REASON_RANGE
          RETURN
        END IF
      ELSE
        result%reason_code=REASON_RANGE
        RETURN
      END IF
      transition(i,j)=.TRUE.; any_transition=.TRUE.
    END DO; END DO

    ! An explicit prior is not permission to replace a state.  A genuine
    ! no-op therefore requires the supplied prior to be exactly the background.
    IF (.NOT.any_transition) THEN
      IF (.NOT.canonical_states_equal(background,prior,.FALSE.)) THEN
        result%reason_code=REASON_METADATA
        RETURN
      END IF
      result%status=STATUS_OK; result%reason_code=REASON_NONE
      RETURN
    END IF

    ! The transition needs a complete six-species/thermodynamic/wind shell in
    ! the changed columns.  No missing value is promoted to a zero donor.
    IF (.NOT.field3d_shape_metadata_ok(background%geopotential,nx,ny,nz, &
        background%pressure%valid_time,'m2 s-2') .OR. &
        .NOT.field3d_shape_metadata_ok(prior%geopotential,nx,ny,nz, &
        prior%pressure%valid_time,'m2 s-2')) THEN
      result%reason_code=REASON_METADATA
      RETURN
    END IF
    IF (.NOT.hydrostatic_fields_available(background) .OR. &
        .NOT.hydrostatic_fields_available(prior)) THEN
      result%reason_code=REASON_METADATA
      RETURN
    END IF
    DO j=1,ny; DO i=1,nx
      IF (.NOT.transition(i,j)) CYCLE
      bottom=FINDLOC(background%above_ground(i,j,:),.TRUE.,DIM=1)
      prior_bottom=FINDLOC(prior%above_ground(i,j,:),.TRUE.,DIM=1)
      IF (.NOT.surface_anchor_fields_available(background,i,j) .OR. &
          .NOT.surface_anchor_fields_available(prior,i,j)) THEN
        result%reason_code=REASON_REQUIRED_COVERAGE
        RETURN
      END IF
      ! Only PS and the newly active reconstruction may differ explicitly;
      ! surface thermodynamics and the terrain anchor remain fixed.
      IF (prior%surface_temperature%value(i,j)/=background%surface_temperature%value(i,j) .OR. &
          prior%surface_vapor%value(i,j)/=background%surface_vapor%value(i,j) .OR. &
          prior%surface_height%value(i,j)/=background%surface_height%value(i,j)) THEN
        result%reason_code=REASON_METADATA
        RETURN
      END IF
      DO k=bottom,nz
        IF (.NOT.hydrostatic_cell_available(background,i,j,k) .OR. &
            .NOT.hydrostatic_cell_available(prior,i,j,k)) THEN
          result%reason_code=REASON_REQUIRED_COVERAGE
          RETURN
        END IF
        IF (prior%temperature%value(i,j,k)/=background%temperature%value(i,j,k) .OR. &
            ANY(represented_water_species(prior,i,j,k)/=represented_water_species(background,i,j,k)) .OR. &
            prior%u%value(i,j,k)/=background%u%value(i,j,k) .OR. &
            prior%v%value(i,j,k)/=background%v%value(i,j,k) .OR. &
            prior%omega%value(i,j,k)/=background%omega%value(i,j,k) .OR. &
            prior%geopotential%value(i,j,k)/=background%geopotential%value(i,j,k) .OR. &
            (prior%geopotential%valid(i,j,k).NEQV.background%geopotential%valid(i,j,k)) .OR. &
            prior%geopotential%quality(i,j,k)/=background%geopotential%quality(i,j,k) .OR. &
            prior%geopotential%source(i,j,k)/=background%geopotential%source(i,j,k)) THEN
          result%reason_code=REASON_METADATA
          RETURN
        END IF
      END DO
      IF (.NOT.hydrostatic_cell_available(prior,i,j,prior_bottom)) THEN
        result%reason_code=REASON_REQUIRED_COVERAGE
        RETURN
      END IF
      IF (prior_bottom<bottom) THEN
        IF (prior%omega_target%valid(i,j,prior_bottom) .OR. &
            prior%obs_support(i,j,prior_bottom)/=0_int32 .OR. &
            IAND(IOR(IOR(prior%u%source(i,j,prior_bottom),prior%v%source(i,j,prior_bottom)), &
              prior%omega%source(i,j,prior_bottom)), &
              IOR(SOURCE_DYNAMIC_TARGET,SOURCE_MANUFACTURED_TEST))/=0_int32) THEN
          result%reason_code=REASON_AUTHORITY
          RETURN
        END IF
      END IF
      IF (.NOT. ieee_is_finite(prior%surface_temperature%value(i,j)) .OR. &
          .NOT. ieee_is_finite(prior%surface_vapor%value(i,j)) .OR. &
          .NOT. ieee_is_finite(prior%surface_height%value(i,j))) THEN
        result%reason_code=REASON_NONFINITE
        RETURN
      END IF
    END DO; END DO

    ALLOCATE(old_interfaces(nz+2),new_interfaces(nz+1),old_mass(nz+1), &
             new_mass(nz),old_temperature(nz+1),new_temperature(nz), &
             old_species(6,nz+1),pressure_defect(nz+1),new_species(6,nz),h_background(nz), &
             h_prior(nz),h_final(nz),STAT=allocation_status)
    IF (allocation_status/=0) RETURN
    work=background

    DO j=1,ny; DO i=1,nx
      IF (.NOT.transition(i,j)) CYCLE
      bottom=FINDLOC(background%above_ground(i,j,:),.TRUE.,DIM=1)
      prior_bottom=FINDLOC(prior%above_ground(i,j,:),.TRUE.,DIM=1)
      nold=nz-bottom+1
      nnew=nz-prior_bottom+1
      n=nold+1
      old_ps=REAL(background%surface_pressure%value(i,j),real64)
      new_ps=REAL(prior%surface_pressure%value(i,j),real64)
      delta_ps=new_ps-old_ps
      ! Match the existing host pressure-request guard for this first
      ! transition implementation; larger jumps need a separately reviewed
      ! multi-cell/domain contract.
      IF (delta_ps>100.0_real64) THEN
        result%reason_code=REASON_RANGE
        RETURN
      END IF
      area=prior%grid%dx(i,j)*prior%grid%dy(i,j)
      water_sum=SUM(represented_water_species(prior,i,j,prior_bottom))
      boundary_mass=area*delta_ps/GRAVITY/(1.0_real64+water_sum)
      IF (.NOT.ieee_is_finite(boundary_mass) .OR. boundary_mass<=0.0_real64) THEN
        result%reason_code=REASON_RANGE
        RETURN
      END IF

      ! In pressure order the explicitly reconstructed boundary strip is the
      ! first donor, followed by the old active column.  Its expected
      ! extensive mass is checked separately; this is not a native closure
      ! claim for the final canonical state after float32 storage.
      old_interfaces=0.0_real64; old_mass=0.0_real64; old_temperature=0.0_real64
      old_species=0.0_real64; new_interfaces=0.0_real64; new_mass=0.0_real64
      new_temperature=0.0_real64; new_species=0.0_real64
      old_interfaces(1)=new_ps
      old_interfaces(2)=old_ps
      old_interfaces(2:nold+2)=background%grid%pressure_interface(i,j,bottom:nz+1)
      old_mass(1)=boundary_mass
      old_temperature(1)=REAL(prior%temperature%value(i,j,prior_bottom),real64)
      old_species(:,1)=represented_water_species(prior,i,j,prior_bottom)
      expected_mass=area*delta_ps/GRAVITY
      pressure_defect(1)=ABS(old_mass(1)*(1.0_real64+SUM(old_species(:,1)))-expected_mass)
      IF (ABS(old_mass(1)*(1.0_real64+SUM(old_species(:,1)))-expected_mass)> &
          256.0_real64*EPSILON(1.0_real64)*MAX(1.0_real64,ABS(expected_mass))) THEN
        result%reason_code=REASON_RANGE
        RETURN
      END IF
      DO k=1,nold
        old_mass(k+1)=background%grid%dry_air_mass_measure(i,j,bottom+k-1)
        old_temperature(k+1)=REAL(background%temperature%value(i,j,bottom+k-1),real64)
        old_species(:,k+1)=represented_water_species(background,i,j,bottom+k-1)
        expected_mass=background%grid%pressure_mass_measure(i,j,bottom+k-1)
        pressure_defect(k+1)=ABS(old_mass(k+1)*(1.0_real64+SUM(old_species(:,k+1)))-expected_mass)
        ! A previous conservative phase step retains dry mass while species
        ! are stored as float32. Account for that bounded denominator defect;
        ! do not silently normalize the immutable donor before remapping it.
        mass_bound=4.0_real64*old_mass(k+1)*SUM(real32_round_error_bound(old_species(:,k+1)))+ &
          256.0_real64*EPSILON(1.0_real64)*MAX(1.0_real64,ABS(expected_mass))
        IF (old_mass(k+1)<=0.0_real64 .OR. expected_mass<=0.0_real64 .OR. &
            pressure_defect(k+1)>mass_bound) THEN
          result%reason_code=REASON_METADATA
          RETURN
        END IF
      END DO
      DO k=1,nnew+1
        new_interfaces(k)=prior%grid%pressure_interface(i,j,prior_bottom+k-1)
      END DO
      IF (old_interfaces(n+1)/=new_interfaces(nnew+1)) THEN
        result%reason_code=REASON_METADATA
        RETURN
      END IF
      CALL remap_pressure_column(old_interfaces(:n+1),old_mass(:n),old_temperature(:n), &
        old_species(:,:n),new_interfaces(:nnew+1),new_mass(:nnew), &
        new_temperature(:nnew),new_species(:,:nnew),remap_status)
      IF (remap_status/=STATUS_OK) THEN
        result%reason_code=REASON_RANGE
        RETURN
      END IF
      DO k=1,nnew
        IF (.NOT.ieee_is_finite(new_temperature(k)) .OR. &
            ANY(.NOT.ieee_is_finite(new_species(:,k))) .OR. &
            ANY(new_species(:,k)<0.0_real64) .OR. new_species(1,k)>0.2_real64) THEN
          result%reason_code=REASON_RANGE
          RETURN
        END IF
      END DO

      ! The final geometry is the prior geometry in this changed column.
      work%above_ground(i,j,:)=prior%above_ground(i,j,:)
      work%grid%pressure_interface(i,j,:)=prior%grid%pressure_interface(i,j,:)
      work%grid%cell_dp(i,j,:)=prior%grid%cell_dp(i,j,:)
      work%grid%level_spacing_dp(i,j,:)=prior%grid%level_spacing_dp(i,j,:)
      work%grid%pressure_mass_measure(i,j,:)=prior%grid%pressure_mass_measure(i,j,:)
      work%surface_pressure%value(i,j)=prior%surface_pressure%value(i,j)
      work%surface_pressure%valid(i,j)=prior%surface_pressure%valid(i,j)
      work%surface_pressure%quality(i,j)=IOR(prior%surface_pressure%quality(i,j),0_int32)
      work%surface_pressure%source(i,j)=IOR(prior%surface_pressure%source(i,j),SOURCE_COLUMN_PHYSICS)

      DO k=1,nnew
        n=prior_bottom+k-1
        work%temperature%value(i,j,n)=REAL(new_temperature(k),real32)
        work%vapor%value(i,j,n)=REAL(new_species(1,k),real32)
        work%cloud_water%value(i,j,n)=REAL(new_species(2,k),real32)
        work%cloud_ice%value(i,j,n)=REAL(new_species(3,k),real32)
        work%rain%value(i,j,n)=REAL(new_species(4,k),real32)
        work%snow%value(i,j,n)=REAL(new_species(5,k),real32)
        work%graupel%value(i,j,n)=REAL(new_species(6,k),real32)
        IF (prior_bottom<bottom .AND. k==1) THEN
          ! Real readers retain pressure values but mask coordinate metadata
          ! below the old domain. Promote only the newly represented center.
          work%pressure%valid(i,j,n)=prior%pressure%valid(i,j,n)
          work%pressure%quality(i,j,n)=prior%pressure%quality(i,j,n)
          work%pressure%source(i,j,n)=IOR(prior%pressure%source(i,j,n),SOURCE_COLUMN_PHYSICS)
          work%temperature%valid(i,j,n)=.TRUE.; work%vapor%valid(i,j,n)=.TRUE.
          work%cloud_water%valid(i,j,n)=.TRUE.; work%cloud_ice%valid(i,j,n)=.TRUE.
          work%rain%valid(i,j,n)=.TRUE.; work%snow%valid(i,j,n)=.TRUE.; work%graupel%valid(i,j,n)=.TRUE.
          work%temperature%quality(i,j,n)=IOR(prior%temperature%quality(i,j,n),background%temperature%quality(i,j,bottom))
          work%vapor%quality(i,j,n)=IOR(prior%vapor%quality(i,j,n),background%vapor%quality(i,j,bottom))
          work%cloud_water%quality(i,j,n)=IOR(prior%cloud_water%quality(i,j,n),background%cloud_water%quality(i,j,bottom))
          work%cloud_ice%quality(i,j,n)=IOR(prior%cloud_ice%quality(i,j,n),background%cloud_ice%quality(i,j,bottom))
          work%rain%quality(i,j,n)=IOR(prior%rain%quality(i,j,n),background%rain%quality(i,j,bottom))
          work%snow%quality(i,j,n)=IOR(prior%snow%quality(i,j,n),background%snow%quality(i,j,bottom))
          work%graupel%quality(i,j,n)=IOR(prior%graupel%quality(i,j,n),background%graupel%quality(i,j,bottom))
          work%temperature%source(i,j,n)=SOURCE_COLUMN_PHYSICS; work%vapor%source(i,j,n)=SOURCE_COLUMN_PHYSICS
          work%cloud_water%source(i,j,n)=SOURCE_COLUMN_PHYSICS; work%cloud_ice%source(i,j,n)=SOURCE_COLUMN_PHYSICS
          work%rain%source(i,j,n)=SOURCE_COLUMN_PHYSICS; work%snow%source(i,j,n)=SOURCE_COLUMN_PHYSICS
          work%graupel%source(i,j,n)=SOURCE_COLUMN_PHYSICS
          work%u%value(i,j,n)=prior%u%value(i,j,n); work%v%value(i,j,n)=prior%v%value(i,j,n)
          work%omega%value(i,j,n)=prior%omega%value(i,j,n)
          work%u%valid(i,j,n)=.TRUE.; work%v%valid(i,j,n)=.TRUE.; work%omega%valid(i,j,n)=.TRUE.
          work%u%quality(i,j,n)=prior%u%quality(i,j,n)
          work%v%quality(i,j,n)=prior%v%quality(i,j,n)
          work%omega%quality(i,j,n)=prior%omega%quality(i,j,n)
          work%u%source(i,j,n)=SOURCE_COLUMN_PHYSICS; work%v%source(i,j,n)=SOURCE_COLUMN_PHYSICS
          work%omega%source(i,j,n)=SOURCE_COLUMN_PHYSICS
          work%omega_target%valid(i,j,n)=.FALSE.; work%omega_target%quality(i,j,n)=QUALITY_RAW_MISSING
          work%omega_target%source(i,j,n)=0_int32
          work%omega_target_sigma%valid(i,j,n)=.FALSE.; work%omega_target_sigma%quality(i,j,n)=QUALITY_RAW_MISSING
          work%omega_target_sigma%source(i,j,n)=0_int32
          work%obs_support(i,j,n)=0_int32; work%hydro_support(i,j,n)=0_int32
        ELSE
          IF (work%temperature%value(i,j,n)/=background%temperature%value(i,j,n)) &
            work%temperature%source(i,j,n)=IOR(work%temperature%source(i,j,n),SOURCE_COLUMN_PHYSICS)
          IF (work%vapor%value(i,j,n)/=background%vapor%value(i,j,n)) &
            work%vapor%source(i,j,n)=IOR(work%vapor%source(i,j,n),SOURCE_COLUMN_PHYSICS)
          IF (work%cloud_water%value(i,j,n)/=background%cloud_water%value(i,j,n)) &
            work%cloud_water%source(i,j,n)=IOR(work%cloud_water%source(i,j,n),SOURCE_COLUMN_PHYSICS)
          IF (work%cloud_ice%value(i,j,n)/=background%cloud_ice%value(i,j,n)) &
            work%cloud_ice%source(i,j,n)=IOR(work%cloud_ice%source(i,j,n),SOURCE_COLUMN_PHYSICS)
          IF (work%rain%value(i,j,n)/=background%rain%value(i,j,n)) &
            work%rain%source(i,j,n)=IOR(work%rain%source(i,j,n),SOURCE_COLUMN_PHYSICS)
          IF (work%snow%value(i,j,n)/=background%snow%value(i,j,n)) &
            work%snow%source(i,j,n)=IOR(work%snow%source(i,j,n),SOURCE_COLUMN_PHYSICS)
          IF (work%graupel%value(i,j,n)/=background%graupel%value(i,j,n)) &
            work%graupel%source(i,j,n)=IOR(work%graupel%source(i,j,n),SOURCE_COLUMN_PHYSICS)
        END IF
      END DO
      ! Check every public float32 cast against its donor value and verify all
      ! six extensive species after the pressure-mass basis conversion.
      DO k=1,nnew
        n=prior_bottom+k-1
        IF (ABS(REAL(work%temperature%value(i,j,n),real64)-new_temperature(k)) > &
            2.0_real64*real32_round_error_bound(new_temperature(k))) THEN
          result%reason_code=REASON_RANGE
          RETURN
        END IF
        expected_mass=new_mass(k)
        stored_species=[REAL(work%vapor%value(i,j,n),real64), &
          REAL(work%cloud_water%value(i,j,n),real64),REAL(work%cloud_ice%value(i,j,n),real64), &
          REAL(work%rain%value(i,j,n),real64),REAL(work%snow%value(i,j,n),real64), &
          REAL(work%graupel%value(i,j,n),real64)]
        actual_mass=work%grid%pressure_mass_measure(i,j,n)/(1.0_real64+SUM(stored_species))
        species_error=real32_round_error_bound(new_species(:,k))
        donor_defect=0.0_real64
        DO d=1,nold+1
          overlap=MAX(0.0_real64,MIN(old_interfaces(d),new_interfaces(k))- &
            MAX(old_interfaces(d+1),new_interfaces(k+1)))
          donor_defect=donor_defect+pressure_defect(d)*overlap/(old_interfaces(d)-old_interfaces(d+1))
        END DO
        round_slack=256.0_real64*EPSILON(1.0_real64)*MAX(1.0_real64,ABS(expected_mass))
        mass_bound=work%grid%pressure_mass_measure(i,j,n)*SUM(species_error)/ &
          ((1.0_real64+SUM(new_species(:,k)))*(1.0_real64+SUM(stored_species)))+ &
          donor_defect/(1.0_real64+SUM(stored_species))+round_slack
        IF (ABS(actual_mass-expected_mass)>mass_bound) THEN
          result%reason_code=REASON_RANGE
          RETURN
        END IF
        DO s=1,6
          expected_enthalpy=expected_mass*new_species(s,k)
          actual_enthalpy=actual_mass*stored_species(s)
          enthalpy_bound=ABS(expected_mass)*species_error(s)+ &
            mass_bound*ABS(stored_species(s))+ &
            256.0_real64*EPSILON(1.0_real64)*MAX(1.0_real64,ABS(expected_enthalpy))
          IF (ABS(actual_enthalpy-expected_enthalpy)>enthalpy_bound) THEN
            result%reason_code=REASON_RANGE
            RETURN
          END IF
        END DO
        temperature_error=real32_round_error_bound(new_temperature(k))
        expected_specific_enthalpy=moist_species_enthalpy(new_temperature(k),new_species(:,k))
        actual_specific_enthalpy=moist_species_enthalpy( &
          REAL(work%temperature%value(i,j,n),real64),stored_species)
        expected_enthalpy=expected_mass*expected_specific_enthalpy
        actual_enthalpy=actual_mass*actual_specific_enthalpy
        enthalpy_bound=ABS(expected_mass)*((THERMO_CP_DRY+SUM(SPECIES_CP*stored_species))* &
          temperature_error+SUM(species_error*ABS(SPECIES_H0+SPECIES_CP* &
          (new_temperature(k)-THERMO_T0))))+mass_bound*ABS(actual_specific_enthalpy)+ &
          256.0_real64*EPSILON(1.0_real64)*MAX(1.0_real64,ABS(expected_enthalpy), &
            ABS(expected_mass)*(THERMO_CP_DRY+SUM(SPECIES_CP*new_species(:,k)))*ABS(new_temperature(k)))
        IF (ABS(actual_enthalpy-expected_enthalpy)>enthalpy_bound) THEN
          result%reason_code=REASON_RANGE
          RETURN
        END IF
      END DO
    END DO; END DO

    CALL refresh_dry_air_mass_measure(work,status)
    IF (status/=STATUS_OK) THEN
      result%reason_code=REASON_METADATA
      RETURN
    END IF
    ! Restore untouched columns bit-for-bit after the candidate-wide dry-mass
    ! refresh.  This keeps the prior scoped to the changed columns only.
    DO j=1,ny; DO i=1,nx
      IF (transition(i,j)) CYCLE
      work%grid%dry_air_mass_measure(i,j,:)=background%grid%dry_air_mass_measure(i,j,:)
    END DO; END DO

    ! Store Phi using full-mixture, surface-anchored profiles.  The profile
    ! difference preserves each source state's hydrostatic residual instead of
    ! replacing it with an absolute reinitialization.
    DO j=1,ny; DO i=1,nx
      IF (.NOT.transition(i,j)) CYCLE
      bottom=FINDLOC(background%above_ground(i,j,:),.TRUE.,DIM=1)
      prior_bottom=FINDLOC(prior%above_ground(i,j,:),.TRUE.,DIM=1)
      CALL pressure_column_profile(background,i,j,bottom,h_background,profile_status)
      IF (profile_status/=STATUS_OK) THEN
        result%reason_code=REASON_REQUIRED_COVERAGE
        RETURN
      END IF
      CALL pressure_column_profile(prior,i,j,prior_bottom,h_prior,profile_status)
      IF (profile_status/=STATUS_OK) THEN
        result%reason_code=REASON_REQUIRED_COVERAGE
        RETURN
      END IF
      CALL pressure_column_profile(work,i,j,prior_bottom,h_final,profile_status)
      IF (profile_status/=STATUS_OK) THEN
        result%reason_code=REASON_REQUIRED_COVERAGE
        RETURN
      END IF
      DO k=bottom,nz
        new_phi=REAL(background%geopotential%value(i,j,k),real64)+h_final(k)-h_background(k)
        IF (.NOT.ieee_is_finite(new_phi) .OR. ABS(new_phi)>REAL(HUGE(1.0_real32),real64)) THEN
          result%reason_code=REASON_RANGE
          RETURN
        END IF
        work%geopotential%value(i,j,k)=REAL(new_phi,real32)
        IF (work%geopotential%value(i,j,k)/=background%geopotential%value(i,j,k)) &
          work%geopotential%source(i,j,k)=IOR(background%geopotential%source(i,j,k),SOURCE_COLUMN_PHYSICS)
      END DO
      IF (prior_bottom<bottom) THEN
        new_phi=REAL(prior%geopotential%value(i,j,prior_bottom),real64)+ &
          h_final(prior_bottom)-h_prior(prior_bottom)
        IF (.NOT.ieee_is_finite(new_phi) .OR. ABS(new_phi)>REAL(HUGE(1.0_real32),real64)) THEN
          result%reason_code=REASON_RANGE
          RETURN
        END IF
        work%geopotential%value(i,j,prior_bottom)=REAL(new_phi,real32)
        work%geopotential%valid(i,j,prior_bottom)=.TRUE.
        work%geopotential%quality(i,j,prior_bottom)=prior%geopotential%quality(i,j,prior_bottom)
        work%geopotential%source(i,j,prior_bottom)=SOURCE_COLUMN_PHYSICS
        phi_tolerance=256.0_real64*REAL(EPSILON(1.0_real32),real64)* &
          MAX(1.0_real64,ABS(REAL(work%surface_height%value(i,j),real64)))
        IF (REAL(work%geopotential%value(i,j,prior_bottom),real64)/GRAVITY < &
            REAL(work%surface_height%value(i,j),real64)-phi_tolerance) THEN
          result%reason_code=REASON_RANGE
          RETURN
        END IF
      END IF
      IF (prior_bottom<nz) THEN
        IF (ANY(work%geopotential%value(i,j,prior_bottom+1:nz)<= &
            work%geopotential%value(i,j,prior_bottom:nz-1))) THEN
          result%reason_code=REASON_RANGE
          RETURN
        END IF
      END IF
      changed(i,j,bottom:nz)=.TRUE.
      changed(i,j,prior_bottom)=.TRUE.
    END DO; END DO

    CALL validate_canonical_state(work,.FALSE.,.FALSE.,status,reason,.FALSE.)
    IF (status==STATUS_FAILED) THEN
      result%reason_code=reason
      RETURN
    END IF
    CALL account_pressure_analysis(background,work,staged_budget,status,.TRUE.,.TRUE.)
    IF (status/=STATUS_OK) THEN
      result%reason_code=REASON_GATE
      RETURN
    END IF
    budget=staged_budget
    candidate=work
    result%changed=changed
    result%coverage%required=COUNT(changed,KIND=int64)
    result%coverage%usable=result%coverage%required
    result%coverage%excluded=0_int64
    IF (result%coverage%required>0_int64) result%coverage%usable_fraction=1.0_real64
    result%status=STATUS_OK; result%reason_code=REASON_NONE
  END SUBROUTINE apply_pressure_domain_transition

  SUBROUTINE rebase_pressure_transition_prior(background,seed,prior,status,selected_columns)
    ! Rebase a constructor prior onto the state that actually precedes the
    ! domain transition.  The seed may have been built from the immutable
    ! reader background, while BACKGROUND already contains the accepted
    ! thermodynamic and no-request Phi stages.  Only the newly exposed center
    ! is taken from SEED; all old active payload and metadata remain from
    ! BACKGROUND.  Every edit is staged until the final canonical validation.
    TYPE(cloud_bal_state_type), INTENT(IN) :: background,seed
    TYPE(cloud_bal_state_type), INTENT(OUT) :: prior
    INTEGER, INTENT(OUT) :: status
    LOGICAL, INTENT(IN), OPTIONAL :: selected_columns(:,:)
    TYPE(cloud_bal_state_type) :: work
    LOGICAL, ALLOCATABLE :: transition(:,:),newcell(:,:,:)
    INTEGER :: nx,ny,nz,i,j,k,bottom,seed_bottom,local_status,reason
    INTEGER :: allocation_status
    REAL(real64) :: old_ps,new_ps

    prior=background
    status=STATUS_FAILED
    nx=background%grid%nx; ny=background%grid%ny; nz=background%grid%nz
    IF (nx<1 .OR. ny<1 .OR. nz<2) RETURN
    IF (seed%grid%nx/=nx .OR. seed%grid%ny/=ny .OR. seed%grid%nz/=nz) RETURN

    CALL validate_canonical_state(background,.FALSE.,.TRUE.,local_status,reason,.TRUE.)
    IF (local_status/=STATUS_OK) RETURN
    CALL validate_canonical_state(seed,.FALSE.,.TRUE.,local_status,reason,.TRUE.)
    IF (local_status/=STATUS_OK) RETURN
    IF (.NOT.field3d_shape_metadata_ok(background%geopotential,nx,ny,nz, &
        background%pressure%valid_time,'m2 s-2')) RETURN
    IF (.NOT.field3d_shape_metadata_ok(seed%geopotential,nx,ny,nz, &
        background%pressure%valid_time,'m2 s-2')) RETURN
    IF (background%pressure%valid_time/=seed%pressure%valid_time .OR. &
        TRIM(background%grid%grid_id)/=TRIM(seed%grid%grid_id) .OR. &
        ANY(background%grid%dx/=seed%grid%dx) .OR. ANY(background%grid%dy/=seed%grid%dy) .OR. &
        ANY(background%pressure%value/=seed%pressure%value)) RETURN
    ! A transition prior may not replace the accepted surface thermodynamics
    ! or terrain anchor from the post-analysis state.
    IF (ANY(background%surface_temperature%value/=seed%surface_temperature%value) .OR. &
        ANY(background%surface_temperature%valid .NEQV.seed%surface_temperature%valid) .OR. &
        ANY(background%surface_temperature%quality/=seed%surface_temperature%quality) .OR. &
        ANY(background%surface_temperature%source/=seed%surface_temperature%source) .OR. &
        ANY(background%surface_vapor%value/=seed%surface_vapor%value) .OR. &
        ANY(background%surface_vapor%valid .NEQV.seed%surface_vapor%valid) .OR. &
        ANY(background%surface_vapor%quality/=seed%surface_vapor%quality) .OR. &
        ANY(background%surface_vapor%source/=seed%surface_vapor%source) .OR. &
        ANY(background%surface_height%value/=seed%surface_height%value) .OR. &
        ANY(background%surface_height%valid .NEQV.seed%surface_height%valid) .OR. &
        ANY(background%surface_height%quality/=seed%surface_height%quality) .OR. &
        ANY(background%surface_height%source/=seed%surface_height%source)) RETURN
    IF (PRESENT(selected_columns)) THEN
      IF (ANY(SHAPE(selected_columns)/=[nx,ny])) RETURN
    END IF

    ALLOCATE(transition(nx,ny),newcell(nx,ny,nz),STAT=allocation_status)
    IF (allocation_status/=0) RETURN
    transition=.FALSE.; newcell=.FALSE.
    DO j=1,ny; DO i=1,nx
      IF (PRESENT(selected_columns)) THEN
        IF (.NOT.selected_columns(i,j)) CYCLE
      END IF
      bottom=FINDLOC(background%above_ground(i,j,:),.TRUE.,DIM=1)
      seed_bottom=FINDLOC(seed%above_ground(i,j,:),.TRUE.,DIM=1)
      IF (bottom<1 .OR. seed_bottom<1) RETURN
      old_ps=REAL(background%surface_pressure%value(i,j),real64)
      new_ps=REAL(seed%surface_pressure%value(i,j),real64)
      IF (new_ps==old_ps) THEN
        IF (seed_bottom/=bottom .OR. &
            ANY(seed%above_ground(i,j,:).NEQV.background%above_ground(i,j,:)) .OR. &
            ANY(seed%grid%pressure_interface(i,j,:)/=background%grid%pressure_interface(i,j,:)) .OR. &
            ANY(seed%grid%cell_dp(i,j,:)/=background%grid%cell_dp(i,j,:)) .OR. &
            ANY(seed%grid%level_spacing_dp(i,j,:)/=background%grid%level_spacing_dp(i,j,:)) .OR. &
            ANY(seed%grid%pressure_mass_measure(i,j,:)/= &
                background%grid%pressure_mass_measure(i,j,:)) .OR. &
            (seed%surface_pressure%valid(i,j).NEQV.background%surface_pressure%valid(i,j)) .OR. &
            seed%surface_pressure%quality(i,j)/=background%surface_pressure%quality(i,j) .OR. &
            seed%surface_pressure%source(i,j)/=background%surface_pressure%source(i,j)) RETURN
        CYCLE
      END IF
      IF (new_ps<old_ps .OR. new_ps-old_ps>100.0_real64) RETURN
      IF (seed_bottom==bottom) THEN
        IF (bottom>1) THEN
          IF (old_ps<REAL(background%pressure%value(i,j,bottom-1),real64) .AND. &
              new_ps>=REAL(background%pressure%value(i,j,bottom-1),real64)) RETURN
        END IF
        IF (ANY(seed%above_ground(i,j,:).NEQV.background%above_ground(i,j,:))) RETURN
      ELSE IF (seed_bottom==bottom-1) THEN
        IF (bottom<=1) RETURN
        k=bottom-1
        IF (old_ps>=REAL(background%pressure%value(i,j,k),real64) .OR. &
            new_ps<REAL(background%pressure%value(i,j,k),real64)) RETURN
        IF (k>1) THEN
          IF (new_ps>=REAL(background%pressure%value(i,j,k-1),real64)) RETURN
        END IF
        DO k=1,nz
          IF (k==bottom-1) THEN
            IF (.NOT.seed%above_ground(i,j,k)) RETURN
          ELSE IF (seed%above_ground(i,j,k).NEQV.background%above_ground(i,j,k)) THEN
            RETURN
          END IF
        END DO
        newcell(i,j,bottom-1)=.TRUE.
      ELSE
        RETURN
      END IF
      transition(i,j)=.TRUE.
    END DO; END DO

    work=background
    DO j=1,ny; DO i=1,nx
      IF (.NOT.transition(i,j)) CYCLE
      work%above_ground(i,j,:)=seed%above_ground(i,j,:)
      work%grid%pressure_interface(i,j,:)=seed%grid%pressure_interface(i,j,:)
      work%grid%cell_dp(i,j,:)=seed%grid%cell_dp(i,j,:)
      work%grid%level_spacing_dp(i,j,:)=seed%grid%level_spacing_dp(i,j,:)
      work%grid%pressure_mass_measure(i,j,:)=seed%grid%pressure_mass_measure(i,j,:)
      work%surface_pressure%value(i,j)=seed%surface_pressure%value(i,j)
      work%surface_pressure%valid(i,j)=seed%surface_pressure%valid(i,j)
      work%surface_pressure%quality(i,j)=seed%surface_pressure%quality(i,j)
      work%surface_pressure%source(i,j)=seed%surface_pressure%source(i,j)
    END DO; END DO

    CALL copy_new_field(work%pressure,seed%pressure,newcell)
    CALL copy_new_field(work%temperature,seed%temperature,newcell)
    CALL copy_new_field(work%vapor,seed%vapor,newcell)
    CALL copy_new_field(work%cloud_water,seed%cloud_water,newcell)
    CALL copy_new_field(work%cloud_ice,seed%cloud_ice,newcell)
    CALL copy_new_field(work%rain,seed%rain,newcell)
    CALL copy_new_field(work%snow,seed%snow,newcell)
    CALL copy_new_field(work%graupel,seed%graupel,newcell)
    CALL copy_new_field(work%u,seed%u,newcell)
    CALL copy_new_field(work%v,seed%v,newcell)
    CALL copy_new_field(work%omega,seed%omega,newcell)
    CALL copy_new_field(work%geopotential,seed%geopotential,newcell)
    WHERE (newcell)
      work%obs_support=0_int32
      work%hydro_support=0_int32
      work%balance_beta=0.0_real32
      work%omega_target%valid=.FALSE.
      work%omega_target%quality=QUALITY_RAW_MISSING
      work%omega_target%source=0_int32
      work%omega_target_sigma%valid=.FALSE.
      work%omega_target_sigma%quality=QUALITY_RAW_MISSING
      work%omega_target_sigma%source=0_int32
    END WHERE
    CALL refresh_dry_air_mass_measure(work,local_status)
    IF (local_status/=STATUS_OK) RETURN
    WHERE (work%grid%pressure_mass_measure==background%grid%pressure_mass_measure)
      work%grid%dry_air_mass_measure=background%grid%dry_air_mass_measure
    END WHERE
    CALL validate_canonical_state(work,.FALSE.,.TRUE.,local_status,reason,.TRUE.)
    IF (local_status/=STATUS_OK) RETURN
    prior=work
    status=STATUS_OK
  CONTAINS
    SUBROUTINE copy_new_field(destination,source,mask)
      TYPE(field3d), INTENT(INOUT) :: destination
      TYPE(field3d), INTENT(IN) :: source
      LOGICAL, INTENT(IN) :: mask(:,:,:)
      WHERE(mask)
        destination%value=source%value
        destination%valid=source%valid
        destination%quality=source%quality
        destination%source=source%source
      END WHERE
    END SUBROUTINE copy_new_field
  END SUBROUTINE rebase_pressure_transition_prior

  PURE ELEMENTAL REAL(real64) FUNCTION real32_round_error_bound(value)
    REAL(real64), INTENT(IN) :: value
    ! Normal relative rounding plus the subnormal absolute rounding floor.
    real32_round_error_bound=MAX(0.5_real64*REAL(EPSILON(1.0_real32),real64)*ABS(value), &
      0.5_real64*REAL(NEAREST(0.0_real32,1.0_real32),real64))
  END FUNCTION real32_round_error_bound

  SUBROUTINE pressure_column_profile(state,i,j,bottom,profile,status)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    INTEGER, INTENT(IN) :: i,j,bottom
    REAL(real64), INTENT(OUT) :: profile(:)
    INTEGER, INTENT(OUT) :: status
    REAL(real64) :: pressure_bottom,pressure_above,rho_bottom,rho_above
    REAL(real64) :: rho_surface,alpha_surface,alpha_bottom,alpha_above
    REAL(real64) :: species(6),surface_pressure,surface_temperature,surface_vapor
    INTEGER :: k,nz

    status=STATUS_FAILED
    nz=state%grid%nz
    profile=0.0_real64
    IF (SIZE(profile)/=nz .OR. bottom<1 .OR. bottom>nz) RETURN
    IF (.NOT.surface_anchor_fields_available(state,i,j)) RETURN
    surface_pressure=REAL(state%surface_pressure%value(i,j),real64)
    surface_temperature=REAL(state%surface_temperature%value(i,j),real64)
    surface_vapor=REAL(state%surface_vapor%value(i,j),real64)
    rho_surface=dry_air_density(surface_pressure,surface_temperature,surface_vapor)
    IF (rho_surface<=0.0_real64) RETURN
    rho_surface=rho_surface*(1.0_real64+surface_vapor)
    alpha_surface=surface_pressure/rho_surface
    pressure_bottom=REAL(state%pressure%value(i,j,bottom),real64)
    species=represented_water_species(state,i,j,bottom)
    rho_bottom=dry_air_density(pressure_bottom,REAL(state%temperature%value(i,j,bottom),real64),species(1))
    IF (rho_bottom<=0.0_real64) RETURN
    rho_bottom=rho_bottom*(1.0_real64+SUM(species))
    alpha_bottom=pressure_bottom/rho_bottom
    IF (surface_pressure<pressure_bottom .OR. .NOT.ieee_is_finite(alpha_bottom)) RETURN
    profile(bottom)=GRAVITY*REAL(state%surface_height%value(i,j),real64)+ &
      0.5_real64*(alpha_surface+alpha_bottom)*LOG(surface_pressure/pressure_bottom)
    DO k=bottom+1,nz
      pressure_above=REAL(state%pressure%value(i,j,k),real64)
      species=represented_water_species(state,i,j,k-1)
      rho_bottom=dry_air_density(REAL(state%pressure%value(i,j,k-1),real64), &
        REAL(state%temperature%value(i,j,k-1),real64),species(1))
      species=represented_water_species(state,i,j,k)
      rho_above=dry_air_density(pressure_above,REAL(state%temperature%value(i,j,k),real64),species(1))
      IF (rho_bottom<=0.0_real64 .OR. rho_above<=0.0_real64) RETURN
      rho_bottom=rho_bottom*(1.0_real64+SUM(represented_water_species(state,i,j,k-1)))
      rho_above=rho_above*(1.0_real64+SUM(species))
      alpha_bottom=REAL(state%pressure%value(i,j,k-1),real64)/rho_bottom
      alpha_above=pressure_above/rho_above
      IF (pressure_above>=REAL(state%pressure%value(i,j,k-1),real64) .OR. &
          .NOT.ieee_is_finite(alpha_bottom) .OR. .NOT.ieee_is_finite(alpha_above)) RETURN
      profile(k)=profile(k-1)+0.5_real64*(alpha_bottom+alpha_above)* &
        LOG(REAL(state%pressure%value(i,j,k-1),real64)/pressure_above)
    END DO
    IF (ANY(.NOT.ieee_is_finite(profile))) RETURN
    status=STATUS_OK
  END SUBROUTINE pressure_column_profile

  SUBROUTINE detect_cloud_sublayers(cloud_type,cloud_fraction,valid,threshold, &
                                    max_layers,nlayers,bottom,top,regime,status, &
                                    precipitation_phase)
    INTEGER(int32), INTENT(IN) :: cloud_type(:)
    REAL(real32), INTENT(IN) :: cloud_fraction(:)
    LOGICAL, INTENT(IN) :: valid(:)
    REAL(real64), INTENT(IN) :: threshold
    INTEGER, INTENT(IN) :: max_layers
    INTEGER, INTENT(OUT) :: nlayers,bottom(max_layers),top(max_layers)
    INTEGER, INTENT(OUT) :: regime(max_layers),status
    INTEGER, INTENT(IN), OPTIONAL :: precipitation_phase(:)
    INTEGER :: k,current_regime,current_phase,incoming_phase
    LOGICAL :: cloudy,in_layer

    nlayers=0; bottom=0; top=0; regime=REGIME_CLEAR; status=STATUS_FAILED
    IF (SIZE(cloud_type)/=SIZE(cloud_fraction) .OR. SIZE(valid)/=SIZE(cloud_type) .OR. &
        max_layers<1 .OR. .NOT.ieee_is_finite(threshold) .OR. threshold<0.0_real64) RETURN
    IF (PRESENT(precipitation_phase)) THEN
      IF (SIZE(precipitation_phase)/=SIZE(cloud_type)) RETURN
      IF (ANY(precipitation_phase<PHASE_UNKNOWN) .OR. &
          ANY(precipitation_phase>PHASE_GRAUPEL)) RETURN
    END IF
    in_layer=.FALSE.; current_regime=REGIME_CLEAR; current_phase=PHASE_UNKNOWN
    DO k=1,SIZE(cloud_type)
      cloudy=valid(k) .AND. ieee_is_finite(cloud_fraction(k)) .AND. &
             cloud_fraction(k)>=REAL(threshold,real32) .AND. cloud_type(k)>0
      IF (cloudy) THEN
        incoming_phase=PHASE_UNKNOWN
        IF (PRESENT(precipitation_phase)) incoming_phase=precipitation_phase(k)
        IF (.NOT.in_layer .OR. cloud_regime(cloud_type(k))/=current_regime .OR. &
            (incoming_phase>PHASE_UNKNOWN .AND. current_phase>PHASE_UNKNOWN .AND. &
             incoming_phase/=current_phase)) THEN
          IF (in_layer) top(nlayers)=k-1
          IF (nlayers>=max_layers) RETURN
          nlayers=nlayers+1; bottom(nlayers)=k
          current_regime=cloud_regime(cloud_type(k)); regime(nlayers)=current_regime
          current_phase=incoming_phase
          in_layer=.TRUE.
        ELSE IF (current_phase==PHASE_UNKNOWN .AND. incoming_phase>PHASE_UNKNOWN) THEN
          current_phase=incoming_phase
        END IF
      ELSE IF (in_layer) THEN
        top(nlayers)=k-1; in_layer=.FALSE.; current_regime=REGIME_CLEAR
        current_phase=PHASE_UNKNOWN
      END IF
    END DO
    IF (in_layer) top(nlayers)=SIZE(cloud_type)
    status=STATUS_OK
  END SUBROUTINE detect_cloud_sublayers

  SUBROUTINE build_cloud_targets(state,cfg,w_valid,w_target,status)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    TYPE(column_physics_config), INTENT(IN) :: cfg
    LOGICAL, INTENT(IN) :: w_valid(:,:,:)
    REAL(real32), INTENT(INOUT) :: w_target(:,:,:)
    INTEGER, INTENT(OUT) :: status
    INTEGER :: i,j,layer,nlayers,bottom(state%grid%nz),top(state%grid%nz)
    INTEGER :: regimes(state%grid%nz),layer_status
    LOGICAL :: column_valid(state%grid%nz)
    INTEGER :: column_phase(state%grid%nz)

    status=STATUS_FAILED
    IF (ANY(SHAPE(w_valid)/=(/state%grid%nx,state%grid%ny,state%grid%nz/)) .OR. &
        ANY(SHAPE(w_target)/=(/state%grid%nx,state%grid%ny,state%grid%nz/))) RETURN
    DO j=1,state%grid%ny; DO i=1,state%grid%nx
      column_valid=state%above_ground(i,j,:) .AND. &
                   cell_is_usable(state%cloud_type%valid(i,j,:), &
                   state%cloud_type%quality(i,j,:),state%cloud_type%source(i,j,:)) .AND. &
                   cell_is_usable(state%cloud_fraction%valid(i,j,:), &
                   state%cloud_fraction%quality(i,j,:),state%cloud_fraction%source(i,j,:))
      column_phase=MERGE(state%precipitation_phase%value(i,j,:),PHASE_UNKNOWN, &
                         state%precipitation_phase%valid(i,j,:))
      CALL detect_cloud_sublayers(state%cloud_type%value(i,j,:), &
        state%cloud_fraction%value(i,j,:),column_valid, &
        cfg%cloud_fraction_threshold,state%grid%nz,nlayers,bottom,top,regimes, &
        layer_status,column_phase)
      IF (layer_status/=STATUS_OK) RETURN
      DO layer=1,nlayers
        ! Cloud regime alone defines support and a prior family, not a grid-
        ! mean air velocity.  Observed Sc has near-zero ensemble mean, while
        ! Cu amplitude depends on area/width, buoyancy, pressure and
        ! entrainment.  Until a separately valid dynamic driver and R_w are in
        ! the state contract, retain the background w exactly.
        IF (bottom(layer)<1 .OR. top(layer)<bottom(layer) .OR. &
            regimes(layer)==REGIME_CLEAR) RETURN
      END DO
    END DO; END DO
    IF (ANY(.NOT.ieee_is_finite(w_target))) RETURN
    status=STATUS_OK
  END SUBROUTINE build_cloud_targets

  SUBROUTINE diagnose_radar_cells(state,cfg,observed,phase,zlinear,rain,snow, &
                                  graupel,phase_uncertain,status)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    TYPE(column_physics_config), INTENT(IN) :: cfg
    LOGICAL, INTENT(OUT) :: observed(:,:,:)
    INTEGER, INTENT(OUT) :: phase(:,:,:)
    REAL(real64), INTENT(OUT) :: zlinear(:,:,:)
    REAL(real64), INTENT(INOUT) :: rain(:,:,:),snow(:,:,:),graupel(:,:,:)
    LOGICAL, INTENT(OUT) :: phase_uncertain(:,:,:)
    INTEGER, INTENT(OUT) :: status
    INTEGER :: i,j,k,allocation_status
    REAL(real64) :: total,new_rain,new_snow,new_graupel,rho_d

    observed=state%above_ground .AND. &
      cell_is_usable(state%radar_reflectivity%valid, &
      state%radar_reflectivity%quality,state%radar_reflectivity%source) .AND. &
      ieee_is_finite(state%radar_reflectivity%value) .AND. &
      REAL(state%radar_reflectivity%value,real64)>=cfg%minimum_dbz .AND. &
      REAL(state%radar_reflectivity%value,real64)<=cfg%maximum_dbz
    phase=PHASE_UNKNOWN; phase_uncertain=.FALSE.
    zlinear=0.0_real64
    status=STATUS_FAILED
    DO k=1,state%grid%nz; DO j=1,state%grid%ny; DO i=1,state%grid%nx
      IF (.NOT.observed(i,j,k)) CYCLE
      zlinear(i,j,k)=10.0_real64**(0.1_real64* &
        REAL(state%radar_reflectivity%value(i,j,k),real64))
      IF (cell_is_usable(state%precipitation_phase%valid(i,j,k), &
          state%precipitation_phase%quality(i,j,k), &
          state%precipitation_phase%source(i,j,k))) THEN
        phase(i,j,k)=state%precipitation_phase%value(i,j,k)
        phase_uncertain(i,j,k)=IAND(state%precipitation_phase%quality(i,j,k), &
          IOR(QUALITY_PHASE_UNCERTAIN,QUALITY_BRIGHT_BAND_OR_MIXED))/=0_int32
      ELSE
        ! Temperature supplies a continuous uncertain partition below; it is
        ! not an observed phase code and must remain explicitly unknown.
        phase(i,j,k)=PHASE_UNKNOWN
        phase_uncertain(i,j,k)=.TRUE.
      END IF
      rho_d=dry_air_density(REAL(state%pressure%value(i,j,k),real64), &
        REAL(state%temperature%value(i,j,k),real64), &
        REAL(state%vapor%value(i,j,k),real64))
      IF (rho_d<=0.0_real64) RETURN
      ! The fixed S-band contract is validated separately.  Equivalent
      ! reflectivity does not justify an uncalibrated wavelength multiplier.
      total=cfg%reference_mass_concentration* &
            (zlinear(i,j,k)/1000.0_real64)**0.55_real64/rho_d
      total=MIN(0.02_real64/rho_d,MAX(0.0_real64,total))
      CALL allocate_precipitation_phase(total,REAL(state%temperature%value(i,j,k),real64), &
        phase(i,j,k),new_rain,new_snow,new_graupel,allocation_status)
      IF (allocation_status/=STATUS_OK) RETURN
      rain(i,j,k)=new_rain; snow(i,j,k)=new_snow; graupel(i,j,k)=new_graupel
    END DO; END DO; END DO
    status=STATUS_OK
  END SUBROUTINE diagnose_radar_cells

  SUBROUTINE transport_precipitation_flux(grid,pressure,temperature,vapor,u,v,w, &
    w_valid,domain,observed,phase,zlinear,rain,snow,graupel,cfg,ledger,status, &
    no_echo)
    ! One-shot kernel: the hydrometeors are fresh radar-work arrays, consumed
    ! exactly once by derive_column_physics and never reused as background.
    TYPE(grid_spec), INTENT(IN) :: grid
    REAL(real32), INTENT(IN) :: pressure(:,:,:),temperature(:,:,:),vapor(:,:,:)
    REAL(real32), INTENT(IN) :: u(:,:,:),v(:,:,:),w(:,:,:)
    LOGICAL, INTENT(IN) :: w_valid(:,:,:),domain(:,:,:),observed(:,:,:)
    INTEGER, INTENT(INOUT) :: phase(:,:,:)
    REAL(real64), INTENT(INOUT) :: zlinear(:,:,:),rain(:,:,:),snow(:,:,:),graupel(:,:,:)
    TYPE(column_physics_config), INTENT(IN) :: cfg
    TYPE(precipitation_flux_ledger), INTENT(OUT) :: ledger
    INTEGER, INTENT(OUT) :: status
    LOGICAL, INTENT(IN) :: no_echo(:,:,:)
    INTEGER :: i,j,k,phase_code,nphase
    INTEGER, ALLOCATABLE :: phase_work(:,:,:)
    REAL(real64), ALLOCATABLE :: deposited_rate(:,:),deposited_zrate(:,:)
    REAL(real64), ALLOCATABLE :: phase_rate(:,:),phase_zrate(:,:)
    REAL(real64), ALLOCATABLE :: zlinear_work(:,:,:),rain_work(:,:,:)
    REAL(real64), ALLOCATABLE :: snow_work(:,:,:),graupel_work(:,:,:)

    ledger=precipitation_flux_ledger(); status=STATUS_FAILED
    IF (.NOT.column_config_valid(cfg)) RETURN
    IF (.NOT.transport_shapes_valid(grid,pressure,temperature,vapor,u,v,w,w_valid,domain, &
                                    observed,phase,zlinear,rain,snow,graupel)) RETURN
    IF (.NOT.transport_values_valid(grid,pressure,temperature,vapor,u,v,w,domain, &
                                    phase,zlinear,rain,snow,graupel,cfg)) RETURN
    IF (ANY(observed .AND. .NOT.w_valid)) RETURN
    IF (ANY(SHAPE(no_echo)/=(/grid%nx,grid%ny,grid%nz/))) RETURN
    IF (ANY(no_echo .AND. observed) .OR. ANY(no_echo .AND. .NOT.domain)) RETURN
    IF (ANY(no_echo .AND. (zlinear>0.0_real64 .OR. rain>0.0_real64 .OR. &
        snow>0.0_real64 .OR. graupel>0.0_real64))) RETURN
    ALLOCATE(phase_work(grid%nx,grid%ny,grid%nz), &
             zlinear_work(grid%nx,grid%ny,grid%nz), &
             rain_work(grid%nx,grid%ny,grid%nz), &
             snow_work(grid%nx,grid%ny,grid%nz), &
             graupel_work(grid%nx,grid%ny,grid%nz), &
             deposited_rate(grid%nx,grid%ny),deposited_zrate(grid%nx,grid%ny), &
             phase_rate(grid%nx,grid%ny),phase_zrate(grid%nx,grid%ny))
    phase_work=phase; zlinear_work=zlinear
    rain_work=rain; snow_work=snow; graupel_work=graupel
    DO k=grid%nz,2,-1
      deposited_rate=0.0_real64; deposited_zrate=0.0_real64
      DO phase_code=PHASE_RAIN,PHASE_GRAUPEL
        IF (phase_code==PHASE_FREEZING_RAIN .OR. phase_code==PHASE_SLEET) CYCLE
        SELECT CASE(phase_code)
        CASE(PHASE_RAIN)
          CALL transport_phase_level(grid,pressure,temperature,vapor,u,v,w,w_valid, &
            domain,observed,no_echo,k,phase_code,zlinear_work,rain_work,cfg,ledger, &
            phase_rate,phase_zrate,status)
        CASE(PHASE_SNOW)
          CALL transport_phase_level(grid,pressure,temperature,vapor,u,v,w,w_valid, &
            domain,observed,no_echo,k,phase_code,zlinear_work,snow_work,cfg,ledger, &
            phase_rate,phase_zrate,status)
        CASE(PHASE_GRAUPEL)
          CALL transport_phase_level(grid,pressure,temperature,vapor,u,v,w,w_valid, &
            domain,observed,no_echo,k,phase_code,zlinear_work,graupel_work,cfg,ledger, &
            phase_rate,phase_zrate,status)
        END SELECT
        IF (status/=STATUS_OK) RETURN
        deposited_rate=deposited_rate+phase_rate
        deposited_zrate=deposited_zrate+phase_zrate
      END DO
      DO j=1,grid%ny; DO i=1,grid%nx
        IF (deposited_rate(i,j)>0.0_real64 .AND. .NOT.observed(i,j,k-1)) THEN
          zlinear_work(i,j,k-1)=deposited_zrate(i,j)/deposited_rate(i,j)
          nphase=MERGE(1,0,rain_work(i,j,k-1)>0.0_real64)+ &
                 MERGE(1,0,snow_work(i,j,k-1)>0.0_real64)+ &
                 MERGE(1,0,graupel_work(i,j,k-1)>0.0_real64)
          IF (nphase/=1) THEN
            phase_work(i,j,k-1)=PHASE_UNKNOWN
          ELSE IF (rain_work(i,j,k-1)>0.0_real64) THEN
            phase_work(i,j,k-1)=PHASE_RAIN
          ELSE IF (snow_work(i,j,k-1)>0.0_real64) THEN
            phase_work(i,j,k-1)=PHASE_SNOW
          ELSE
            phase_work(i,j,k-1)=PHASE_GRAUPEL
          END IF
        END IF
      END DO; END DO
    END DO
    CALL account_bottom_flux(grid,pressure,temperature,vapor,w,w_valid,rain_work, &
                             snow_work,graupel_work,zlinear_work,cfg,ledger,status)
    IF (status/=STATUS_OK) RETURN
    IF (.NOT.flux_ledger_closes(ledger,cfg)) THEN
      status=STATUS_FAILED; RETURN
    END IF
    IF (.NOT.transport_values_valid(grid,pressure,temperature,vapor,u,v,w,domain, &
                                    phase_work,zlinear_work,rain_work,snow_work, &
                                    graupel_work,cfg)) THEN
      status=STATUS_FAILED; RETURN
    END IF
    phase=phase_work; zlinear=zlinear_work
    rain=rain_work; snow=snow_work; graupel=graupel_work
  END SUBROUTINE transport_precipitation_flux

  SUBROUTINE transport_phase_level(grid,pressure,temperature,vapor,u,v,w,w_valid, &
    domain,observed,no_echo,k,phase_code,zlinear,q,cfg,ledger,deposited_rate, &
    deposited_zrate,status)
    TYPE(grid_spec), INTENT(IN) :: grid
    REAL(real32), INTENT(IN) :: pressure(:,:,:),temperature(:,:,:),vapor(:,:,:),u(:,:,:)
    REAL(real32), INTENT(IN) :: v(:,:,:),w(:,:,:)
    LOGICAL, INTENT(IN) :: w_valid(:,:,:),domain(:,:,:),observed(:,:,:)
    LOGICAL, INTENT(IN) :: no_echo(:,:,:)
    INTEGER, INTENT(IN) :: k,phase_code
    REAL(real64), INTENT(INOUT) :: zlinear(:,:,:),q(:,:,:)
    TYPE(column_physics_config), INTENT(IN) :: cfg
    TYPE(precipitation_flux_ledger), INTENT(INOUT) :: ledger
    REAL(real64), INTENT(OUT) :: deposited_rate(:,:),deposited_zrate(:,:)
    INTEGER, INTENT(OUT) :: status
    REAL(real64), ALLOCATABLE :: flux(:,:),zflux(:,:),next_flux(:,:),next_zflux(:,:)
    REAL(real64), ALLOCATABLE :: xstep(:,:),ystep(:,:),relative(:,:),target_relative(:,:)
    INTEGER :: i,j,nsub,vt_status
    REAL(real64) :: vt,dz,dt,max_displacement,input_level,rho_source,rho_target

    ALLOCATE(flux(grid%nx,grid%ny),zflux(grid%nx,grid%ny), &
      next_flux(grid%nx,grid%ny),next_zflux(grid%nx,grid%ny), &
      xstep(grid%nx,grid%ny),ystep(grid%nx,grid%ny), &
      relative(grid%nx,grid%ny),target_relative(grid%nx,grid%ny))
    flux=0.0_real64; zflux=0.0_real64; xstep=0.0_real64; ystep=0.0_real64
    deposited_rate=0.0_real64; deposited_zrate=0.0_real64
    relative=0.0_real64; target_relative=0.0_real64; status=STATUS_FAILED
    max_displacement=0.0_real64
    DO j=1,grid%ny; DO i=1,grid%nx
      IF (q(i,j,k)<=0.0_real64) CYCLE
      IF (.NOT.w_valid(i,j,k)) RETURN
      rho_source=dry_air_density(REAL(pressure(i,j,k),real64), &
        REAL(temperature(i,j,k),real64),REAL(vapor(i,j,k),real64))
      IF (rho_source<=0.0_real64) RETURN
      vt=terminal_velocity(phase_code,REAL(pressure(i,j,k),real64), &
        REAL(temperature(i,j,k),real64),MAX(cfg%minimum_dbz, &
        10.0_real64*LOG10(MAX(zlinear(i,j,k),1.0e-12_real64))),vt_status)
      IF (vt_status/=STATUS_OK) RETURN
      relative(i,j)=vt-REAL(w(i,j,k),real64)
      IF (relative(i,j)<=cfg%minimum_relative_fall_speed) THEN
        ledger%input=ledger%input+rho_source*q(i,j,k)*MAX(relative(i,j),0.0_real64)* &
                     grid%dx(i,j)*grid%dy(i,j)
        ledger%suspended=ledger%suspended+ &
                         rho_source*q(i,j,k)*MAX(relative(i,j),0.0_real64)* &
                         grid%dx(i,j)*grid%dy(i,j)
        CYCLE
      END IF
      dz=layer_separation(grid,pressure,temperature,vapor,i,j,k,domain(i,j,k-1))
      ! A pressure-level centre may lie exactly on the lower boundary.  Its
      ! precipitation exits to terrain without horizontal travel (dt=0).
      IF (dz<0.0_real64) RETURN
      dt=dz/relative(i,j)
      xstep(i,j)=REAL(u(i,j,k),real64)*dt/grid%dx(i,j)
      ystep(i,j)=REAL(v(i,j,k),real64)*dt/grid%dy(i,j)
      max_displacement=MAX(max_displacement,ABS(xstep(i,j)),ABS(ystep(i,j)))
      ! ``flux`` is an integrated cell rate (kg s-1), not a flux density.
      ! Transporting the rate and dividing by the destination area is required
      ! for conservation when dx*dy varies across the grid.
      flux(i,j)=rho_source*q(i,j,k)*relative(i,j)*grid%dx(i,j)*grid%dy(i,j)
      zflux(i,j)=flux(i,j)*MAX(zlinear(i,j,k),1.0e-12_real64)
    END DO; END DO
    input_level=SUM(flux); ledger%input=ledger%input+input_level
    IF (input_level<=0.0_real64) THEN; status=STATUS_OK; RETURN; END IF
    IF (.NOT.ieee_is_finite(max_displacement)) RETURN
    IF (max_displacement>cfg%maximum_horizontal_substep* &
                         REAL(cfg%maximum_transport_substeps,real64)) RETURN
    nsub=MAX(1,CEILING(max_displacement/cfg%maximum_horizontal_substep))
    ledger%maximum_required_substeps=MAX(ledger%maximum_required_substeps,nsub)
    IF (nsub>cfg%maximum_transport_substeps) RETURN
    ! A layer segment freezes each source's velocity and transit time. Keep
    ! its continuous trajectory until deposition; intermediate grid remapping
    ! loses motion in empty cells and mixes crossing source trajectories.
    CALL scatter_flux(grid,flux,zflux,xstep,ystep,nsub,next_flux,next_zflux, &
                      ledger%boundary_exit,status)
    IF (status/=STATUS_OK) RETURN
    flux=next_flux; zflux=next_zflux
    DO j=1,grid%ny; DO i=1,grid%nx
      IF (flux(i,j)<=0.0_real64) CYCLE
      IF (.NOT.domain(i,j,k-1)) THEN
        ledger%terrain_intercept=ledger%terrain_intercept+flux(i,j)
        CYCLE
      END IF
      IF (observed(i,j,k-1)) THEN
        ledger%observation_blocked=ledger%observation_blocked+flux(i,j)
        CYCLE
      END IF
      IF (no_echo(i,j,k-1)) THEN
        ledger%no_echo_blocked=ledger%no_echo_blocked+flux(i,j)
        CYCLE
      END IF
      vt=terminal_velocity(phase_code,REAL(pressure(i,j,k-1),real64), &
        REAL(temperature(i,j,k-1),real64),10.0_real64*LOG10(MAX( &
        zflux(i,j)/flux(i,j),1.0e-12_real64)),vt_status)
      IF (vt_status/=STATUS_OK .OR. .NOT.w_valid(i,j,k-1)) RETURN
      rho_target=dry_air_density(REAL(pressure(i,j,k-1),real64), &
        REAL(temperature(i,j,k-1),real64),REAL(vapor(i,j,k-1),real64))
      IF (rho_target<=0.0_real64) RETURN
      target_relative(i,j)=vt-REAL(w(i,j,k-1),real64)
      IF (target_relative(i,j)<=cfg%minimum_relative_fall_speed) THEN
        ledger%suspended=ledger%suspended+flux(i,j)
      ELSE
        q(i,j,k-1)=q(i,j,k-1)+flux(i,j)/(grid%dx(i,j)*grid%dy(i,j)* &
          rho_target*target_relative(i,j))
        deposited_rate(i,j)=deposited_rate(i,j)+flux(i,j)
        deposited_zrate(i,j)=deposited_zrate(i,j)+zflux(i,j)
        ledger%deposited=ledger%deposited+flux(i,j)
      END IF
    END DO; END DO
    status=STATUS_OK
  END SUBROUTINE transport_phase_level

  SUBROUTINE scatter_flux(grid,flux,zflux,xstep,ystep,nsub,out_flux,out_zflux, &
                          boundary_exit,status)
    TYPE(grid_spec), INTENT(IN) :: grid
    REAL(real64), INTENT(IN) :: flux(:,:),zflux(:,:),xstep(:,:),ystep(:,:)
    INTEGER, INTENT(IN) :: nsub
    REAL(real64), INTENT(OUT) :: out_flux(:,:),out_zflux(:,:)
    REAL(real64), INTENT(INOUT) :: boundary_exit
    INTEGER, INTENT(OUT) :: status
    INTEGER :: i,j,ii,jj,di,dj,substep
    REAL(real64) :: xtarget,ytarget,fx,fy,weight,accounted
    out_flux=0.0_real64; out_zflux=0.0_real64; status=STATUS_FAILED
    DO j=1,grid%ny; DO i=1,grid%nx
      IF (flux(i,j)<=0.0_real64) CYCLE
      xtarget=REAL(i,real64); ytarget=REAL(j,real64)
      DO substep=1,nsub
        xtarget=xtarget+xstep(i,j)/REAL(nsub,real64)
        ytarget=ytarget+ystep(i,j)/REAL(nsub,real64)
      END DO
      ii=FLOOR(xtarget); jj=FLOOR(ytarget)
      fx=xtarget-REAL(ii,real64); fy=ytarget-REAL(jj,real64); accounted=0.0_real64
      DO dj=0,1; DO di=0,1
        weight=MERGE(1.0_real64-fx,fx,di==0)*MERGE(1.0_real64-fy,fy,dj==0)
        IF (ii+di<1 .OR. ii+di>grid%nx .OR. jj+dj<1 .OR. jj+dj>grid%ny) THEN
          boundary_exit=boundary_exit+weight*flux(i,j)
        ELSE
          out_flux(ii+di,jj+dj)=out_flux(ii+di,jj+dj)+weight*flux(i,j)
          out_zflux(ii+di,jj+dj)=out_zflux(ii+di,jj+dj)+weight*zflux(i,j)
        END IF
        accounted=accounted+weight
      END DO; END DO
      IF (ABS(accounted-1.0_real64)>32.0_real64*EPSILON(1.0_real64)) RETURN
    END DO; END DO
    status=STATUS_OK
  END SUBROUTINE scatter_flux

  SUBROUTINE account_bottom_flux(grid,pressure,temperature,vapor,w,w_valid,rain,snow, &
                                 graupel,zlinear,cfg,ledger,status)
    TYPE(grid_spec), INTENT(IN) :: grid
    REAL(real32), INTENT(IN) :: pressure(:,:,:),temperature(:,:,:),vapor(:,:,:),w(:,:,:)
    LOGICAL, INTENT(IN) :: w_valid(:,:,:)
    REAL(real64), INTENT(IN) :: rain(:,:,:),snow(:,:,:),graupel(:,:,:),zlinear(:,:,:)
    TYPE(column_physics_config), INTENT(IN) :: cfg
    TYPE(precipitation_flux_ledger), INTENT(INOUT) :: ledger
    INTEGER, INTENT(OUT) :: status
    INTEGER :: i,j,phase_code,vt_status
    REAL(real64) :: q,vt,relative,dbz,flux,rho_d
    status=STATUS_FAILED
    DO j=1,grid%ny; DO i=1,grid%nx
      DO phase_code=PHASE_RAIN,PHASE_GRAUPEL
        IF (phase_code==PHASE_FREEZING_RAIN .OR. phase_code==PHASE_SLEET) CYCLE
        SELECT CASE(phase_code)
        CASE(PHASE_RAIN); q=rain(i,j,1)
        CASE(PHASE_SNOW); q=snow(i,j,1)
        CASE(PHASE_GRAUPEL); q=graupel(i,j,1)
        END SELECT
        IF (q<=0.0_real64) CYCLE
        IF (.NOT.w_valid(i,j,1)) RETURN
        rho_d=dry_air_density(REAL(pressure(i,j,1),real64), &
          REAL(temperature(i,j,1),real64),REAL(vapor(i,j,1),real64))
        IF (rho_d<=0.0_real64) RETURN
        dbz=10.0_real64*LOG10(MAX(zlinear(i,j,1),10.0_real64**(0.1_real64*cfg%minimum_dbz)))
        vt=terminal_velocity(phase_code,REAL(pressure(i,j,1),real64), &
          REAL(temperature(i,j,1),real64),dbz,vt_status)
        IF (vt_status/=STATUS_OK) RETURN
        relative=vt-REAL(w(i,j,1),real64)
        flux=rho_d*q*MAX(relative,0.0_real64)*grid%dx(i,j)*grid%dy(i,j)
        ledger%input=ledger%input+flux
        IF (relative<=cfg%minimum_relative_fall_speed) THEN
          ledger%suspended=ledger%suspended+flux
        ELSE
          ledger%boundary_exit=ledger%boundary_exit+flux
        END IF
      END DO
    END DO; END DO
    status=STATUS_OK
  END SUBROUTINE account_bottom_flux

  SUBROUTINE add_loading_downdraft(state,cfg,observed,rain,snow,graupel, &
                                   w_background,w_target,status)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    TYPE(column_physics_config), INTENT(IN) :: cfg
    LOGICAL, INTENT(IN) :: observed(:,:,:)
    REAL(real64), INTENT(IN) :: rain(:,:,:),snow(:,:,:),graupel(:,:,:)
    REAL(real32), INTENT(IN) :: w_background(:,:,:)
    REAL(real32), INTENT(INOUT) :: w_target(:,:,:)
    INTEGER, INTENT(OUT) :: status
    INTEGER :: i,j,k
    REAL(real64) :: rho_d,qprecip,dz,energy,wdown,innovation
    status=STATUS_FAILED
    IF (ANY(SHAPE(observed)/=(/state%grid%nx,state%grid%ny,state%grid%nz/)) .OR. &
        ANY(SHAPE(rain)/=SHAPE(observed)) .OR. &
        ANY(SHAPE(snow)/=SHAPE(rain)) .OR. ANY(SHAPE(graupel)/=SHAPE(rain))) RETURN
    DO j=1,state%grid%ny; DO i=1,state%grid%nx
      energy=0.0_real64
      DO k=state%grid%nz,1,-1
        ! Transported descendants reconstruct hydrometeors only; they cannot
        ! amplify the loading pseudo-observation used by the wind experiment.
        IF (.NOT.observed(i,j,k)) CYCLE
        IF (rain(i,j,k)+snow(i,j,k)+graupel(i,j,k)<=0.0_real64) CYCLE
        rho_d=dry_air_density(REAL(state%pressure%value(i,j,k),real64), &
          REAL(state%temperature%value(i,j,k),real64), &
          REAL(state%vapor%value(i,j,k),real64))
        IF (rho_d<=0.0_real64) RETURN
        qprecip=rain(i,j,k)+snow(i,j,k)+graupel(i,j,k)
        ! Gas-only pressure thickness, consistent with omega <-> w. The
        ! dry density above still converts dry-basis hydrometeor mass.
        dz=state%grid%cell_dp(i,j,k)/ &
          (rho_d*(1.0_real64+REAL(state%vapor%value(i,j,k),real64))*GRAVITY)
        energy=energy+GRAVITY*cfg%precipitation_loading_efficiency*qprecip*dz
        wdown=-MIN(cfg%maximum_downdraft_ms,SQRT(MAX(0.0_real64,2.0_real64*energy)))
        innovation=MAX(-cfg%maximum_downdraft_innovation_ms, &
                       wdown-REAL(w_background(i,j,k),real64))
        IF (cell_is_usable(state%cloud_type%valid(i,j,k), &
              state%cloud_type%quality(i,j,k),state%cloud_type%source(i,j,k)) .AND. &
            cell_is_usable(state%cloud_fraction%valid(i,j,k), &
              state%cloud_fraction%quality(i,j,k),state%cloud_fraction%source(i,j,k)) .AND. &
            state%cloud_fraction%value(i,j,k)>=REAL(cfg%cloud_fraction_threshold,real32) .AND. &
            is_convective_type(state%cloud_type%value(i,j,k)) .AND. &
            w_background(i,j,k)>0.0_real32) CYCLE
        w_target(i,j,k)=REAL(MIN(REAL(w_target(i,j,k),real64), &
                                 REAL(w_background(i,j,k),real64)+innovation),real32)
      END DO
    END DO; END DO
    IF (ANY(.NOT.ieee_is_finite(w_target))) RETURN
    status=STATUS_OK
  END SUBROUTINE add_loading_downdraft

  SUBROUTINE publish_hydrometeor_candidate(input,candidate,cfg, &
    observed,radar_derived,phase_uncertain,phase,rain,snow,graupel,status)
    TYPE(cloud_bal_state_type), INTENT(IN) :: input
    TYPE(cloud_bal_state_type), INTENT(INOUT) :: candidate
    TYPE(column_physics_config), INTENT(IN) :: cfg
    LOGICAL, INTENT(IN) :: observed(:,:,:),radar_derived(:,:,:),phase_uncertain(:,:,:)
    INTEGER, INTENT(IN) :: phase(:,:,:)
    REAL(real64), INTENT(IN) :: rain(:,:,:),snow(:,:,:),graupel(:,:,:)
    INTEGER, INTENT(OUT) :: status
    WHERE(radar_derived)
      ! A valid echo diagnoses total precipitation at the observed cell.
      ! Descendants add the transported radar increment to their background.
      candidate%rain%value=REAL(rain+MERGE(REAL(input%rain%value,real64), &
        0.0_real64,.NOT.observed .AND. input%rain%valid),real32)
      candidate%snow%value=REAL(snow+MERGE(REAL(input%snow%value,real64), &
        0.0_real64,.NOT.observed .AND. input%snow%valid),real32)
      candidate%graupel%value=REAL(graupel+MERGE(REAL(input%graupel%value,real64), &
        0.0_real64,.NOT.observed .AND. input%graupel%valid),real32)
      candidate%rain%valid=.TRUE.; candidate%snow%valid=.TRUE.
      candidate%graupel%valid=.TRUE.
      candidate%rain%quality=MERGE( &
        IOR(input%rain%quality,MERGE(QUALITY_PHASE_UNCERTAIN,0_int32,phase_uncertain)), &
        MERGE(QUALITY_PHASE_UNCERTAIN,0_int32,phase_uncertain), &
        .NOT.observed .AND. input%rain%valid)
      candidate%snow%quality=MERGE( &
        IOR(input%snow%quality,MERGE(QUALITY_PHASE_UNCERTAIN,0_int32,phase_uncertain)), &
        MERGE(QUALITY_PHASE_UNCERTAIN,0_int32,phase_uncertain), &
        .NOT.observed .AND. input%snow%valid)
      candidate%graupel%quality=MERGE( &
        IOR(input%graupel%quality,MERGE(QUALITY_PHASE_UNCERTAIN,0_int32,phase_uncertain)), &
        MERGE(QUALITY_PHASE_UNCERTAIN,0_int32,phase_uncertain), &
        .NOT.observed .AND. input%graupel%valid)
      candidate%rain%source=MERGE(IOR(SOURCE_RADAR_DBZ,SOURCE_COLUMN_PHYSICS), &
        IOR(candidate%rain%source,IOR(SOURCE_RADAR_DBZ,SOURCE_COLUMN_PHYSICS)),observed)
      candidate%snow%source=MERGE(IOR(SOURCE_RADAR_DBZ,SOURCE_COLUMN_PHYSICS), &
        IOR(candidate%snow%source,IOR(SOURCE_RADAR_DBZ,SOURCE_COLUMN_PHYSICS)),observed)
      candidate%graupel%source=MERGE(IOR(SOURCE_RADAR_DBZ,SOURCE_COLUMN_PHYSICS), &
        IOR(candidate%graupel%source,IOR(SOURCE_RADAR_DBZ,SOURCE_COLUMN_PHYSICS)),observed)
      candidate%precipitation_phase%value=phase
      candidate%precipitation_phase%valid=.TRUE.
      candidate%precipitation_phase%quality=MERGE( &
        IOR(input%precipitation_phase%quality, &
            MERGE(QUALITY_PHASE_UNCERTAIN,0_int32,phase_uncertain)), &
        MERGE(QUALITY_PHASE_UNCERTAIN,0_int32,phase_uncertain), &
        .NOT.observed .AND. input%precipitation_phase%valid)
      candidate%precipitation_phase%source=MERGE( &
        IOR(SOURCE_RADAR_DBZ,SOURCE_COLUMN_PHYSICS), &
        IOR(candidate%precipitation_phase%source, &
            IOR(SOURCE_RADAR_DBZ,SOURCE_COLUMN_PHYSICS)),observed)
    END WHERE
    WHERE(observed .OR. &
      (cell_is_usable(input%cloud_fraction%valid,input%cloud_fraction%quality, &
                      input%cloud_fraction%source) .AND. &
       cell_is_usable(input%cloud_type%valid,input%cloud_type%quality, &
                      input%cloud_type%source) .AND. &
       input%cloud_fraction%value>=REAL(cfg%cloud_fraction_threshold,real32) .AND. &
       input%cloud_type%value>0_int32)) candidate%obs_support=1_int32
    WHERE(radar_derived) candidate%hydro_support=1_int32
    IF (ANY(candidate%rain%valid .AND. .NOT.ieee_is_finite(candidate%rain%value)) .OR. &
        ANY(candidate%snow%valid .AND. .NOT.ieee_is_finite(candidate%snow%value)) .OR. &
        ANY(candidate%graupel%valid .AND. &
            .NOT.ieee_is_finite(candidate%graupel%value))) THEN
      status=STATUS_FAILED; RETURN
    END IF
    CALL refresh_dry_air_mass_measure(candidate,status)
    IF (status/=STATUS_OK) RETURN
    status=STATUS_OK
  END SUBROUTINE publish_hydrometeor_candidate

  SUBROUTINE publish_column_diagnostics(input,candidate,cfg,w_target,w_valid, &
    observed,radar_derived,phase_uncertain,zlinear,rain,snow,graupel, &
    preserve_omega_target,status)
    TYPE(cloud_bal_state_type), INTENT(IN) :: input
    TYPE(cloud_bal_state_type), INTENT(INOUT) :: candidate
    TYPE(column_physics_config), INTENT(IN) :: cfg
    REAL(real32), INTENT(IN) :: w_target(:,:,:)
    LOGICAL, INTENT(IN) :: w_valid(:,:,:),observed(:,:,:),radar_derived(:,:,:),phase_uncertain(:,:,:)
    REAL(real64), INTENT(IN) :: zlinear(:,:,:),rain(:,:,:),snow(:,:,:),graupel(:,:,:)
    LOGICAL, INTENT(IN) :: preserve_omega_target
    INTEGER, INTENT(OUT) :: status
    LOGICAL, ALLOCATABLE :: omega_valid(:,:,:),target_derived(:,:,:)
    REAL(real32), ALLOCATABLE :: omega_target(:,:,:)
    INTEGER :: i,j,k,vt_status
    REAL(real64) :: total,vr,vs,vg,mean,variance,dbz
    status=STATUS_FAILED
    ! A supplied model target includes its missing/valid mask.  Do not append
    ! empirical diagnostics to that field outside the authorized target cells.
    IF (.NOT.preserve_omega_target) THEN
      ALLOCATE(omega_valid(input%grid%nx,input%grid%ny,input%grid%nz), &
               target_derived(input%grid%nx,input%grid%ny,input%grid%nz), &
               omega_target(input%grid%nx,input%grid%ny,input%grid%nz))
      CALL w_to_omega(w_target,candidate%pressure%value,candidate%temperature%value, &
        candidate%vapor%value,w_valid,omega_target,omega_valid,status)
      IF (status/=STATUS_OK) RETURN
      status=STATUS_FAILED
      ! Transported descendants diagnose hydrometeors, not new wind evidence.
      ! Direct, non-bright-band echo permits a diagnostic target, not wind authority.
      target_derived=omega_valid .AND. observed .AND. &
        IAND(input%radar_reflectivity%quality,QUALITY_BRIGHT_BAND_OR_MIXED)==0_int32 .AND. &
        .NOT.(dynamic_target_has_authority(input%omega_target%valid, &
          input%omega_target%quality,input%omega_target%source) .OR. &
          model_dynamic_target_has_authority(input%omega_target%valid, &
          input%omega_target%quality,input%omega_target%source)) .AND. &
        (ABS(omega_target-input%omega%value)> &
         16.0_real32*EPSILON(1.0_real32)*MAX(1.0_real32,ABS(input%omega%value)))
      WHERE(target_derived)
        candidate%omega_target%value=omega_target
        candidate%omega_target%valid=.TRUE.
        candidate%omega_target%quality=IOR(input%radar_reflectivity%quality, &
          IOR(QUALITY_FALL_SPEED_UNCERTAIN, &
              MERGE(QUALITY_PHASE_UNCERTAIN,0_int32,phase_uncertain)))
        candidate%omega_target%source=IOR(SOURCE_RADAR_DBZ,SOURCE_COLUMN_PHYSICS)
      END WHERE
    END IF
    DO k=1,input%grid%nz; DO j=1,input%grid%ny; DO i=1,input%grid%nx
      IF (.NOT.radar_derived(i,j,k)) CYCLE
      total=rain(i,j,k)+snow(i,j,k)+graupel(i,j,k)
      IF (total<=0.0_real64) CYCLE
      dbz=10.0_real64*LOG10(MAX(zlinear(i,j,k),10.0_real64**(0.1_real64*cfg%minimum_dbz)))
      vr=terminal_velocity(PHASE_RAIN,REAL(candidate%pressure%value(i,j,k),real64), &
        REAL(candidate%temperature%value(i,j,k),real64),dbz,vt_status)
      IF (vt_status/=STATUS_OK) RETURN
      vs=terminal_velocity(PHASE_SNOW,REAL(candidate%pressure%value(i,j,k),real64), &
        REAL(candidate%temperature%value(i,j,k),real64),dbz,vt_status)
      IF (vt_status/=STATUS_OK) RETURN
      vg=terminal_velocity(PHASE_GRAUPEL,REAL(candidate%pressure%value(i,j,k),real64), &
        REAL(candidate%temperature%value(i,j,k),real64),dbz,vt_status)
      IF (vt_status/=STATUS_OK) RETURN
      mean=(rain(i,j,k)*vr+snow(i,j,k)*vs+graupel(i,j,k)*vg)/total
      variance=(rain(i,j,k)*(vr-mean)**2+snow(i,j,k)*(vs-mean)**2+ &
                graupel(i,j,k)*(vg-mean)**2)/total
      candidate%vt_z_mean%value(i,j,k)=REAL(mean,real32)
      candidate%vt_z_sigma%value(i,j,k)=REAL(SQRT(MAX(0.0_real64,variance)),real32)
      candidate%vt_z_mean%valid(i,j,k)=.TRUE.; candidate%vt_z_sigma%valid(i,j,k)=.TRUE.
      candidate%vt_z_mean%quality(i,j,k)=IOR(QUALITY_FALL_SPEED_UNCERTAIN, &
        MERGE(QUALITY_PHASE_UNCERTAIN,0_int32,phase_uncertain(i,j,k)))
      candidate%vt_z_sigma%quality(i,j,k)=candidate%vt_z_mean%quality(i,j,k)
      candidate%vt_z_mean%source(i,j,k)=IOR(SOURCE_RADAR_DBZ,SOURCE_COLUMN_PHYSICS)
      candidate%vt_z_sigma%source(i,j,k)=IOR(SOURCE_RADAR_DBZ,SOURCE_COLUMN_PHYSICS)
    END DO; END DO; END DO
    status=STATUS_OK
  END SUBROUTINE publish_column_diagnostics

  LOGICAL FUNCTION pristine_background(state)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    INTEGER(int32), PARAMETER :: GENERATED=IOR(SOURCE_COLUMN_PHYSICS,SOURCE_BALANCE_OPERATOR)
    ! A stage candidate is never a valid background snapshot: provenance alone
    ! cannot recover the background contribution from a generated total.
    pristine_background= &
      .NOT.ANY(IAND(state%temperature%source,GENERATED)/=0_int32) .AND. &
      .NOT.ANY(IAND(state%vapor%source,GENERATED)/=0_int32) .AND. &
      .NOT.ANY(IAND(state%u%source,GENERATED)/=0_int32) .AND. &
      .NOT.ANY(IAND(state%v%source,GENERATED)/=0_int32) .AND. &
      .NOT.ANY(IAND(state%omega%source,GENERATED)/=0_int32) .AND. &
      .NOT.ANY(IAND(state%omega_target%source,GENERATED)/=0_int32) .AND. &
      .NOT.ANY(IAND(state%cloud_water%source,GENERATED)/=0_int32) .AND. &
      .NOT.ANY(IAND(state%cloud_ice%source,GENERATED)/=0_int32) .AND. &
      .NOT.ANY(IAND(state%rain%source,GENERATED)/=0_int32) .AND. &
      .NOT.ANY(IAND(state%snow%source,GENERATED)/=0_int32) .AND. &
      .NOT.ANY(IAND(state%graupel%source,GENERATED)/=0_int32) .AND. &
      .NOT.ANY(IAND(state%precipitation_phase%source,GENERATED)/=0_int32) .AND. &
      .NOT.ANY(IAND(state%vt_z_mean%source,GENERATED)/=0_int32) .AND. &
      .NOT.ANY(IAND(state%vt_z_sigma%source,GENERATED)/=0_int32)
  END FUNCTION pristine_background

  SUBROUTINE allocate_precipitation_phase(total,temperature,phase,rain,snow, &
                                           graupel,status)
    REAL(real64), INTENT(IN) :: total,temperature
    INTEGER, INTENT(IN) :: phase
    REAL(real64), INTENT(OUT) :: rain,snow,graupel
    INTEGER, INTENT(OUT) :: status
    REAL(real64) :: rain_fraction,snow_fraction,graupel_fraction
    INTEGER :: partition_status
    rain=0.0_real64; snow=0.0_real64; graupel=0.0_real64; status=STATUS_FAILED
    IF (.NOT.ieee_is_finite(total) .OR. .NOT.ieee_is_finite(temperature)) RETURN
    IF (total<0.0_real64 .OR. temperature<150.0_real64 .OR. &
        temperature>350.0_real64) RETURN
    SELECT CASE(phase)
    CASE(PHASE_RAIN); rain=total
    CASE(PHASE_SNOW); snow=total
    CASE(PHASE_FREEZING_RAIN); rain=0.75_real64*total; graupel=total-rain
    CASE(PHASE_SLEET); snow=0.50_real64*total; graupel=total-snow
    CASE(PHASE_GRAUPEL); graupel=total
    CASE(PHASE_UNKNOWN)
      CALL missing_phase_partition(temperature,rain_fraction,snow_fraction, &
                                   graupel_fraction,partition_status)
      IF (partition_status/=STATUS_OK) RETURN
      rain=rain_fraction*total
      graupel=graupel_fraction*total
      snow=total-rain-graupel
    CASE DEFAULT
      RETURN
    END SELECT
    IF (ABS((rain+snow+graupel)-total)> &
        16.0_real64*EPSILON(1.0_real64)*MAX(total,TINY(1.0_real64))) RETURN
    status=STATUS_OK
  END SUBROUTINE allocate_precipitation_phase

  PURE SUBROUTINE missing_phase_partition(temperature,rain_fraction,snow_fraction, &
                                          graupel_fraction,status)
    REAL(real64), INTENT(IN) :: temperature
    REAL(real64), INTENT(OUT) :: rain_fraction,snow_fraction,graupel_fraction
    INTEGER, INTENT(OUT) :: status
    REAL(real64) :: scaled,liquid

    rain_fraction=0.0_real64
    snow_fraction=0.0_real64
    graupel_fraction=0.0_real64
    status=STATUS_FAILED
    IF (.NOT.ieee_is_finite(temperature)) RETURN
    IF (temperature<150.0_real64 .OR. temperature>350.0_real64) RETURN

    ! Missing phase remains an uncertain thermodynamic fallback.  The former
    ! all-snow and all-rain bounds define one C1-continuous transition; the
    ! smoothstep avoids a trajectory jump at either bound.  Temperature alone
    ! provides no evidence for riming, so it cannot manufacture graupel.
    scaled=MIN(1.0_real64,MAX(0.0_real64, &
      (temperature-MISSING_PHASE_ALL_SNOW_K)/ &
      (MISSING_PHASE_ALL_RAIN_K-MISSING_PHASE_ALL_SNOW_K)))
    liquid=scaled*scaled*(3.0_real64-2.0_real64*scaled)
    rain_fraction=liquid
    snow_fraction=1.0_real64-liquid
    status=STATUS_OK
  END SUBROUTINE missing_phase_partition

  REAL(real64) FUNCTION terminal_velocity(phase,pressure_pa,temperature_k,dbz,status)
    INTEGER, INTENT(IN) :: phase
    REAL(real64), INTENT(IN) :: pressure_pa,temperature_k,dbz
    INTEGER, INTENT(OUT) :: status
    REAL(real64) :: z,density_ratio,rain_speed,snow_speed,graupel_speed
    REAL(real64) :: rain_fraction,snow_fraction,graupel_fraction
    INTEGER :: partition_status
    status=STATUS_FAILED; terminal_velocity=0.0_real64
    IF (.NOT.ieee_is_finite(pressure_pa) .OR. &
        .NOT.ieee_is_finite(temperature_k) .OR. .NOT.ieee_is_finite(dbz)) RETURN
    IF (pressure_pa<MIN_PRESSURE_PA .OR. pressure_pa>MAX_PRESSURE_PA .OR. &
        temperature_k<=150.0_real64 .OR. &
        temperature_k>350.0_real64 .OR. dbz< -100.0_real64 .OR. &
        dbz>100.0_real64) RETURN
    z=10.0_real64**(0.1_real64*dbz)
    density_ratio=(pressure_pa/101300.0_real64)*(273.15_real64/temperature_k)
    rain_speed=bounded_terminal_speed( &
      4.32_real64*z**(1.0_real64/14.0_real64),density_ratio)
    snow_speed=bounded_terminal_speed( &
      MIN(2.5_real64,0.80_real64+0.12_real64*z**0.10_real64),density_ratio)
    graupel_speed=bounded_terminal_speed( &
      MIN(15.0_real64,7.0_real64+0.30_real64*z**0.08_real64),density_ratio)
    SELECT CASE(phase)
    CASE(PHASE_RAIN,PHASE_FREEZING_RAIN,PHASE_SLEET)
      terminal_velocity=rain_speed
    CASE(PHASE_SNOW)
      terminal_velocity=snow_speed
    CASE(PHASE_GRAUPEL)
      terminal_velocity=graupel_speed
    CASE(PHASE_UNKNOWN)
      CALL missing_phase_partition(temperature_k,rain_fraction,snow_fraction, &
                                   graupel_fraction,partition_status)
      IF (partition_status/=STATUS_OK) RETURN
      terminal_velocity=rain_fraction*rain_speed+snow_fraction*snow_speed+ &
                        graupel_fraction*graupel_speed
    CASE DEFAULT
      RETURN
    END SELECT
    IF (.NOT.ieee_is_finite(terminal_velocity)) THEN
      terminal_velocity=0.0_real64; RETURN
    END IF
    status=STATUS_OK
  END FUNCTION terminal_velocity

  PURE REAL(real64) FUNCTION bounded_terminal_speed(base,density_ratio)
    REAL(real64), INTENT(IN) :: base,density_ratio
    bounded_terminal_speed=MIN(20.0_real64,MAX(0.1_real64, &
      base/SQRT(MAX(density_ratio,1.0e-4_real64))))
  END FUNCTION bounded_terminal_speed

  PURE SUBROUTINE hydrostatic_geopotential_increment(pressure,temperature_before,water_before, &
      temperature_after,water_after,delta_geopotential,status, &
      surface_pressure_pair,surface_temperature_pair,surface_water_pair)
    REAL(real64), INTENT(IN) :: pressure(:),temperature_before(:),water_before(:,:)
    REAL(real64), INTENT(IN) :: temperature_after(:),water_after(:,:)
    REAL(real64), INTENT(INOUT) :: delta_geopotential(:)
    INTEGER, INTENT(OUT) :: status
    ! Optional before/after surface states at the same fixed terrain height.
    ! All three arrays are required together; no boundary humidity is inferred.
    REAL(real64), INTENT(IN), OPTIONAL :: surface_pressure_pair(:),surface_temperature_pair(:)
    REAL(real64), INTENT(IN), OPTIONAL :: surface_water_pair(:,:)
    REAL(real64) :: delta_p_alpha(SIZE(pressure)),work(SIZE(pressure))
    REAL(real64) :: rho_before,rho_after,alpha_bottom(2),alpha_surface(2),rho
    LOGICAL :: surface_anchor
    INTEGER :: n,k

    ! Pressure-level hydrostatic INCREMENT, not the native dry-pressure metric.
    ! p/rho_total = Rd*T*(1+rv/epsilon)/(1+sum(r)); all six r are kg/kg dry air.
    ! Integrate its change in log(p), retaining the original hydrostatic residual.
    ! Without surface states, the lowest pressure center has delta Phi=0: an explicit
    ! reference-level anchor, not a measured surface/top boundary or authority.
    ! Callers must authorize the entire resulting vertical increment support.
    status=STATUS_FAILED
    n=SIZE(pressure)
    IF (n<1) RETURN
    surface_anchor=PRESENT(surface_pressure_pair) .OR. PRESENT(surface_temperature_pair) .OR. &
      PRESENT(surface_water_pair)
    IF (surface_anchor) THEN
      IF (.NOT.PRESENT(surface_pressure_pair) .OR. .NOT.PRESENT(surface_temperature_pair) .OR. &
          .NOT.PRESENT(surface_water_pair)) RETURN
      IF (SIZE(surface_pressure_pair)/=2 .OR. SIZE(surface_temperature_pair)/=2) RETURN
      IF (ANY(SHAPE(surface_water_pair)/=[6,2])) RETURN
      IF (ANY(.NOT.ieee_is_finite(surface_pressure_pair)) .OR. &
          ANY(.NOT.ieee_is_finite(surface_temperature_pair)) .OR. &
          ANY(.NOT.ieee_is_finite(surface_water_pair))) RETURN
      IF (ANY(surface_water_pair<0.0_real64) .OR. &
          ANY(surface_water_pair>REAL(HUGE(1.0_real32),real64))) RETURN
    END IF
    IF (SIZE(temperature_before)/=n .OR. SIZE(temperature_after)/=n .OR. &
        SIZE(delta_geopotential)/=n) RETURN
    IF (ANY(SHAPE(water_before)/=[6,n]) .OR. ANY(SHAPE(water_after)/=[6,n])) RETURN
    IF (ANY(.NOT.ieee_is_finite(pressure)) .OR. &
        ANY(.NOT.ieee_is_finite(temperature_before)) .OR. &
        ANY(.NOT.ieee_is_finite(temperature_after)) .OR. &
        ANY(.NOT.ieee_is_finite(water_before)) .OR. &
        ANY(.NOT.ieee_is_finite(water_after))) RETURN
    IF (ANY(water_before<0.0_real64) .OR. ANY(water_after<0.0_real64)) RETURN
    IF (ANY(water_before>REAL(HUGE(1.0_real32),real64)) .OR. &
        ANY(water_after>REAL(HUGE(1.0_real32),real64))) RETURN
    DO k=1,n-1
      IF (pressure(k)<=pressure(k+1)) RETURN
    END DO
    DO k=1,n
      rho_before=dry_air_density(pressure(k),temperature_before(k),water_before(1,k))
      rho_after=dry_air_density(pressure(k),temperature_after(k),water_after(1,k))
      IF (rho_before<=0.0_real64 .OR. rho_after<=0.0_real64) RETURN
      rho_before=rho_before*(1.0_real64+SUM(water_before(:,k)))
      rho_after=rho_after*(1.0_real64+SUM(water_after(:,k)))
      IF (k==1) alpha_bottom=[pressure(k)/rho_before,pressure(k)/rho_after]
      delta_p_alpha(k)=pressure(k)/rho_after-pressure(k)/rho_before
    END DO
    work(1)=0.0_real64
    IF (surface_anchor) THEN
      IF (ANY(surface_pressure_pair<pressure(1))) RETURN
      DO k=1,2
        rho=dry_air_density(surface_pressure_pair(k),surface_temperature_pair(k),surface_water_pair(1,k))
        IF (rho<=0.0_real64) RETURN
        rho=rho*(1.0_real64+SUM(surface_water_pair(:,k)))
        alpha_surface(k)=surface_pressure_pair(k)/rho
      END DO
      ! Retain the original column residual; change only its hydrostatic
      ! surface-to-center thickness, with the source terrain held fixed.
      work(1)=0.5_real64*(alpha_surface(2)+alpha_bottom(2))* &
        LOG(surface_pressure_pair(2)/pressure(1))- &
        0.5_real64*(alpha_surface(1)+alpha_bottom(1))*LOG(surface_pressure_pair(1)/pressure(1))
    END IF
    DO k=1,n-1
      work(k+1)=work(k)+0.5_real64*(delta_p_alpha(k)+delta_p_alpha(k+1))* &
        LOG(pressure(k)/pressure(k+1))
    END DO
    IF (ANY(.NOT.ieee_is_finite(work))) RETURN
    delta_geopotential=work
    status=STATUS_OK
  END SUBROUTINE hydrostatic_geopotential_increment

  SUBROUTINE apply_pressure_hydrostatic_increment(background,proposal,candidate,result,support,reference_level, &
      requested_surface_pressure,geometry_budget)
    TYPE(cloud_bal_state_type), INTENT(IN) :: background,proposal
    TYPE(cloud_bal_state_type), INTENT(OUT) :: candidate
    TYPE(stage_result), INTENT(OUT) :: result
    LOGICAL, INTENT(IN) :: support(:,:,:)
    INTEGER, INTENT(IN) :: reference_level(:,:)
    REAL(real64), INTENT(IN), OPTIONAL :: requested_surface_pressure(:,:)
    TYPE(pressure_analysis_budget), INTENT(OUT), OPTIONAL :: geometry_budget
    TYPE(pressure_analysis_budget) :: staged_budget
    TYPE(cloud_bal_state_type) :: work
    LOGICAL, ALLOCATABLE :: changed(:,:,:)
    REAL(real64), ALLOCATABLE :: before(:,:),after(:,:),delta(:)
    REAL(real64) :: new_phi,surface_height_before,surface_height_after
    REAL(real64) :: lowest_background_height,surface_tolerance
    REAL(real64) :: surface_pressure_pair(2),surface_temperature_pair(2)
    REAL(real64) :: surface_water_pair(6,2)
    LOGICAL :: surface_anchor,update_pressure
    INTEGER :: nx,ny,nz,i,j,k,bottom,status,reason

    ! Apply only a caller-authorized pressure-level increment. A positive
    ! reference level retains the represented-center anchor; reference level
    ! zero authorizes a fixed-terrain surface anchor. Optional requested PSFC
    ! and its paired budget stage geometry/dry mass/Phi in the same transaction.
    ! Without them, pressure geometry is unchanged. Work from the same background; never
    ! add a correction to an adjusted Phi.
    CALL reject_candidate(proposal,candidate,result,STATUS_FAILED,REASON_SHAPE)
    staged_budget=pressure_analysis_budget()
    IF (PRESENT(geometry_budget)) geometry_budget=staged_budget
    update_pressure=PRESENT(requested_surface_pressure)
    IF (update_pressure .NEQV. PRESENT(geometry_budget)) RETURN
    nx=proposal%grid%nx; ny=proposal%grid%ny; nz=proposal%grid%nz
    IF (ANY(SHAPE(support)/=[nx,ny,nz]) .OR. ANY(SHAPE(reference_level)/=[nx,ny])) RETURN
    IF (background%grid%nx/=nx .OR. background%grid%ny/=ny .OR. background%grid%nz/=nz) RETURN
    IF (update_pressure) THEN
      IF (ANY(SHAPE(requested_surface_pressure)/=[nx,ny])) RETURN
      IF (.NOT.ALL(ieee_is_finite(requested_surface_pressure))) RETURN
      IF (ANY(requested_surface_pressure<MIN_PRESSURE_PA) .OR. &
          ANY(requested_surface_pressure>MAX_PRESSURE_PA)) RETURN
    END IF
    CALL validate_canonical_state(background,.FALSE.,.FALSE.,status,reason,.FALSE.)
    IF (status/=STATUS_OK) THEN
      result%reason_code=reason; RETURN
    END IF
    CALL validate_canonical_state(proposal,.FALSE.,.FALSE.,status,reason,.FALSE.)
    IF (status/=STATUS_OK) THEN
      result%reason_code=reason; RETURN
    END IF
    result%reason_code=REASON_METADATA
    IF (ANY(background%above_ground.NEQV.proposal%above_ground)) RETURN
    IF (ANY(background%grid%pressure_interface/=proposal%grid%pressure_interface) .OR. &
        ANY(background%grid%cell_dp/=proposal%grid%cell_dp) .OR. &
        ANY(background%grid%level_spacing_dp/=proposal%grid%level_spacing_dp) .OR. &
        ANY(background%grid%pressure_mass_measure/=proposal%grid%pressure_mass_measure) .OR. &
        ANY(background%grid%dx/=proposal%grid%dx) .OR. &
        ANY(background%grid%dy/=proposal%grid%dy)) RETURN
    ! The incoming proposal still owns the original geometry; pressure changes
    ! must enter through the explicit request, never through a stale metric.
    IF (ANY(background%surface_pressure%value/=proposal%surface_pressure%value)) RETURN
    DO k=1,nz; DO j=1,ny; DO i=1,nx
      IF (.NOT.proposal%above_ground(i,j,k)) CYCLE
      IF (background%pressure%value(i,j,k)/=proposal%pressure%value(i,j,k)) RETURN
    END DO; END DO; END DO
    IF (background%pressure%valid_time/=proposal%pressure%valid_time) RETURN
    IF (.NOT.ANY(support)) THEN
      IF (update_pressure) THEN
        IF (ANY(requested_surface_pressure/=REAL(proposal%surface_pressure%value,real64))) RETURN
      END IF
      result%status=STATUS_OK; result%reason_code=REASON_NONE; RETURN
    END IF
    IF (.NOT.hydrostatic_fields_available(background) .OR. &
        .NOT.hydrostatic_fields_available(proposal)) RETURN
    result%reason_code=REASON_AUTHORITY
    IF (ANY(support .AND. .NOT.proposal%above_ground)) RETURN
    work=proposal
    ALLOCATE(changed(nx,ny,nz),before(6,nz),after(6,nz),delta(nz))
    changed=.FALSE.
    IF (update_pressure) THEN
      DO j=1,ny; DO i=1,nx
        IF (requested_surface_pressure(i,j)==REAL(proposal%surface_pressure%value(i,j),real64)) CYCLE
        IF (reference_level(i,j)/=0 .OR. .NOT.ANY(support(i,j,:))) RETURN
        IF (ANY(proposal%above_ground(i,j,:) .AND. .NOT.support(i,j,:))) RETURN
        ! Check the mathematical request before storage rounding can hide an
        ! unauthorized change, then check the actual stored classification.
        IF (ANY((REAL(proposal%pressure%value(i,j,:),real64)<=requested_surface_pressure(i,j)) .NEQV. &
            (proposal%pressure%value(i,j,:)<=proposal%surface_pressure%value(i,j)))) RETURN
        work%surface_pressure%value(i,j)=REAL(requested_surface_pressure(i,j),real32)
        IF (ANY((work%pressure%value(i,j,:)<=work%surface_pressure%value(i,j)) .NEQV. &
            (proposal%pressure%value(i,j,:)<=proposal%surface_pressure%value(i,j)))) RETURN
        IF (work%surface_pressure%value(i,j)/=proposal%surface_pressure%value(i,j)) THEN
          work%surface_pressure%source(i,j)=IOR(work%surface_pressure%source(i,j),SOURCE_COLUMN_PHYSICS)
          changed(i,j,:)=proposal%above_ground(i,j,:)
        END IF
      END DO; END DO
      ! Geometry uses retained pressure coordinates even below the domain.
      ! Keep this temporary coordinate availability out of the final state.
      work%pressure%valid=.TRUE.; work%pressure%quality=0_int32
      work%pressure%source=SOURCE_COLUMN_PHYSICS
      CALL configure_pressure_geometry(work,status,proposal%above_ground)
      work%pressure=proposal%pressure
      IF (status/=STATUS_OK) RETURN
      IF (ANY(work%above_ground .NEQV. proposal%above_ground)) RETURN
      CALL refresh_dry_air_mass_measure(work,status)
      IF (status/=STATUS_OK) RETURN
      ! Rebuilding the domain may normalize valid rounded metrics elsewhere.
      ! Keep every untouched column bitwise identical to the supplied proposal.
      DO j=1,ny; DO i=1,nx
        IF (work%surface_pressure%value(i,j)/=proposal%surface_pressure%value(i,j)) CYCLE
        work%grid%pressure_interface(i,j,:)=proposal%grid%pressure_interface(i,j,:)
        work%grid%cell_dp(i,j,:)=proposal%grid%cell_dp(i,j,:)
        work%grid%level_spacing_dp(i,j,:)=proposal%grid%level_spacing_dp(i,j,:)
        work%grid%pressure_mass_measure(i,j,:)=proposal%grid%pressure_mass_measure(i,j,:)
        work%grid%dry_air_mass_measure(i,j,:)=proposal%grid%dry_air_mass_measure(i,j,:)
      END DO; END DO
    END IF
    DO j=1,ny; DO i=1,nx
      IF (.NOT.ANY(support(i,j,:))) CYCLE
      bottom=FINDLOC(proposal%above_ground(i,j,:),.TRUE.,DIM=1)
      result%reason_code=REASON_AUTHORITY
      IF (reference_level(i,j)<0 .OR. reference_level(i,j)>bottom) RETURN
      surface_anchor=reference_level(i,j)==0
      IF (.NOT.surface_anchor .AND. reference_level(i,j)/=bottom) RETURN
      result%reason_code=REASON_REQUIRED_COVERAGE
      DO k=bottom,nz
        IF (.NOT.hydrostatic_cell_available(background,i,j,k) .OR. &
            .NOT.hydrostatic_cell_available(proposal,i,j,k)) RETURN
        before(:,k)=represented_water_species(background,i,j,k)
        after(:,k)=represented_water_species(proposal,i,j,k)
      END DO
      result%reason_code=REASON_METADATA
      IF (ANY(proposal%geopotential%value(i,j,bottom:)/= &
              background%geopotential%value(i,j,bottom:)) .OR. &
          ANY(proposal%geopotential%valid(i,j,bottom:).NEQV. &
              background%geopotential%valid(i,j,bottom:)) .OR. &
          ANY(proposal%geopotential%quality(i,j,bottom:)/= &
              background%geopotential%quality(i,j,bottom:)) .OR. &
          ANY(proposal%geopotential%source(i,j,bottom:)/= &
              background%geopotential%source(i,j,bottom:))) RETURN
      IF (surface_anchor) THEN
        ! A surface anchor needs supplied, non-manufactured p/T/qv/terrain in
        ! both states. The terrain is fixed; PSFC remains geometry-owned.
        result%reason_code=REASON_REQUIRED_COVERAGE
        IF (.NOT.surface_anchor_fields_available(background,i,j) .OR. &
            .NOT.surface_anchor_fields_available(work,i,j)) RETURN
        surface_height_before=REAL(background%surface_height%value(i,j),real64)
        surface_height_after=REAL(proposal%surface_height%value(i,j),real64)
        result%reason_code=REASON_METADATA
        IF (surface_height_after/=surface_height_before) RETURN
        surface_tolerance=128.0_real64*REAL(EPSILON(1.0_real32),real64)* &
          MAX(1.0_real64,ABS(surface_height_before))
        lowest_background_height=REAL(background%geopotential%value(i,j,bottom),real64)/GRAVITY
        result%reason_code=REASON_RANGE
        IF (surface_height_before>lowest_background_height+surface_tolerance .OR. &
            surface_height_after>lowest_background_height+surface_tolerance) RETURN
        surface_pressure_pair=[REAL(background%surface_pressure%value(i,j),real64), &
          REAL(work%surface_pressure%value(i,j),real64)]
        surface_temperature_pair=[REAL(background%surface_temperature%value(i,j),real64), &
          REAL(proposal%surface_temperature%value(i,j),real64)]
        surface_water_pair=0.0_real64
        ! WPS_SURFACE_ZERO_CONDENSATE: qv is supplied at the surface and all
        ! condensate components are explicit zeros, not measured-zero values.
        surface_water_pair(1,:)=[REAL(background%surface_vapor%value(i,j),real64), &
          REAL(proposal%surface_vapor%value(i,j),real64)]
      END IF
      delta=0.0_real64
      IF (surface_anchor) THEN
        CALL hydrostatic_geopotential_increment( &
          REAL(proposal%pressure%value(i,j,bottom:),real64), &
          REAL(background%temperature%value(i,j,bottom:),real64),before(:,bottom:), &
          REAL(proposal%temperature%value(i,j,bottom:),real64),after(:,bottom:),delta(bottom:),status, &
          surface_pressure_pair=surface_pressure_pair, &
          surface_temperature_pair=surface_temperature_pair, &
          surface_water_pair=surface_water_pair)
      ELSE
        CALL hydrostatic_geopotential_increment( &
          REAL(proposal%pressure%value(i,j,bottom:),real64), &
          REAL(background%temperature%value(i,j,bottom:),real64),before(:,bottom:), &
          REAL(proposal%temperature%value(i,j,bottom:),real64),after(:,bottom:),delta(bottom:),status)
      END IF
      result%reason_code=REASON_RANGE
      IF (status/=STATUS_OK) RETURN
      DO k=bottom,nz
        ! Test mathematical support before float32 rounding can hide a change.
        result%reason_code=REASON_AUTHORITY
        IF (delta(k)/=0.0_real64 .AND. .NOT.support(i,j,k)) RETURN
        new_phi=REAL(background%geopotential%value(i,j,k),real64)+delta(k)
        result%reason_code=REASON_RANGE
        IF (ABS(new_phi)>REAL(HUGE(1.0_real32),real64)) RETURN
        work%geopotential%value(i,j,k)=REAL(new_phi,real32)
        IF (surface_anchor .AND. k==bottom) THEN
          IF (REAL(work%geopotential%value(i,j,k),real64)/GRAVITY< &
              surface_height_after-surface_tolerance) RETURN
        END IF
        changed(i,j,k)=changed(i,j,k) .OR. work%geopotential%value(i,j,k)/=proposal%geopotential%value(i,j,k)
        IF (work%geopotential%value(i,j,k)/=proposal%geopotential%value(i,j,k)) work%geopotential%source(i,j,k)= &
          IOR(work%geopotential%source(i,j,k),SOURCE_COLUMN_PHYSICS)
        IF (k>bottom) THEN
          IF (work%geopotential%value(i,j,k)<=work%geopotential%value(i,j,k-1)) RETURN
        END IF
      END DO
    END DO; END DO
    IF (update_pressure) THEN
      CALL validate_canonical_state(work,.FALSE.,.FALSE.,status,reason,.FALSE.)
      IF (status/=STATUS_OK) THEN
        result%reason_code=reason; RETURN
      END IF
      CALL account_pressure_analysis(proposal,work,staged_budget,status,.TRUE.)
      IF (status/=STATUS_OK) RETURN
      geometry_budget=staged_budget
    END IF
    candidate=work
    result%changed=changed
    result%coverage%required=COUNT(support,KIND=int64)
    result%coverage%usable=result%coverage%required
    result%coverage%usable_fraction=1.0_real64
    result%status=STATUS_OK; result%reason_code=REASON_NONE
  END SUBROUTINE apply_pressure_hydrostatic_increment

  PURE LOGICAL FUNCTION surface_anchor_fields_available(state,i,j) RESULT(ok)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    INTEGER, INTENT(IN) :: i,j
    ok=.FALSE.
    IF (.NOT.field2d_shape_metadata_ok(state%surface_pressure,state%grid%nx,state%grid%ny, &
        state%pressure%valid_time,'Pa')) RETURN
    IF (.NOT.field2d_shape_metadata_ok(state%surface_temperature,state%grid%nx,state%grid%ny, &
        state%pressure%valid_time,'K')) RETURN
    IF (.NOT.field2d_shape_metadata_ok(state%surface_vapor,state%grid%nx,state%grid%ny, &
        state%pressure%valid_time,'kg kg-1 dryair')) RETURN
    IF (.NOT.field2d_shape_metadata_ok(state%surface_height,state%grid%nx,state%grid%ny, &
        state%pressure%valid_time,'m')) RETURN
    IF (.NOT.cell_is_usable(state%surface_pressure%valid(i,j), &
        state%surface_pressure%quality(i,j),state%surface_pressure%source(i,j)) .OR. &
        .NOT.cell_is_usable(state%surface_temperature%valid(i,j), &
        state%surface_temperature%quality(i,j),state%surface_temperature%source(i,j)) .OR. &
        .NOT.cell_is_usable(state%surface_vapor%valid(i,j), &
        state%surface_vapor%quality(i,j),state%surface_vapor%source(i,j)) .OR. &
        .NOT.cell_is_usable(state%surface_height%valid(i,j), &
        state%surface_height%quality(i,j),state%surface_height%source(i,j))) RETURN
    IF (IAND(state%surface_pressure%source(i,j),SOURCE_MANUFACTURED_TEST)/=0_int32 .OR. &
        IAND(state%surface_temperature%source(i,j),SOURCE_MANUFACTURED_TEST)/=0_int32 .OR. &
        IAND(state%surface_vapor%source(i,j),SOURCE_MANUFACTURED_TEST)/=0_int32 .OR. &
        IAND(state%surface_height%source(i,j),SOURCE_MANUFACTURED_TEST)/=0_int32) RETURN
    IF (.NOT.ieee_is_finite(state%surface_pressure%value(i,j)) .OR. &
        .NOT.ieee_is_finite(state%surface_temperature%value(i,j)) .OR. &
        .NOT.ieee_is_finite(state%surface_vapor%value(i,j)) .OR. &
        .NOT.ieee_is_finite(state%surface_height%value(i,j))) RETURN
    IF (REAL(state%surface_pressure%value(i,j),real64)<MIN_PRESSURE_PA .OR. &
        REAL(state%surface_pressure%value(i,j),real64)>MAX_PRESSURE_PA .OR. &
        REAL(state%surface_temperature%value(i,j),real64)<150.0_real64 .OR. &
        REAL(state%surface_temperature%value(i,j),real64)>350.0_real64 .OR. &
        REAL(state%surface_vapor%value(i,j),real64)<0.0_real64 .OR. &
        REAL(state%surface_vapor%value(i,j),real64)>REAL(0.1_real32,real64) .OR. &
        REAL(state%surface_height%value(i,j),real64)<-500.0_real64 .OR. &
        REAL(state%surface_height%value(i,j),real64)>9000.0_real64) RETURN
    ok=.TRUE.
  END FUNCTION surface_anchor_fields_available

  PURE LOGICAL FUNCTION hydrostatic_fields_available(state) RESULT(ok)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    INTEGER :: nx,ny,nz
    INTEGER(int64) :: time
    nx=state%grid%nx; ny=state%grid%ny; nz=state%grid%nz; time=state%pressure%valid_time
    ok=field3d_shape_metadata_ok(state%geopotential,nx,ny,nz,time,'m2 s-2') .AND. &
       field3d_shape_metadata_ok(state%cloud_water,nx,ny,nz,time,'kg kg-1 dryair') .AND. &
       field3d_shape_metadata_ok(state%cloud_ice,nx,ny,nz,time,'kg kg-1 dryair') .AND. &
       field3d_shape_metadata_ok(state%rain,nx,ny,nz,time,'kg kg-1 dryair') .AND. &
       field3d_shape_metadata_ok(state%snow,nx,ny,nz,time,'kg kg-1 dryair') .AND. &
       field3d_shape_metadata_ok(state%graupel,nx,ny,nz,time,'kg kg-1 dryair')
  END FUNCTION hydrostatic_fields_available

  PURE LOGICAL FUNCTION hydrostatic_cell_available(state,i,j,k) RESULT(ok)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    INTEGER, INTENT(IN) :: i,j,k
    ok=cell_is_usable(state%geopotential%valid(i,j,k),state%geopotential%quality(i,j,k), &
          state%geopotential%source(i,j,k)) .AND. &
       cell_is_usable(state%cloud_water%valid(i,j,k),state%cloud_water%quality(i,j,k),state%cloud_water%source(i,j,k)) .AND. &
       cell_is_usable(state%cloud_ice%valid(i,j,k),state%cloud_ice%quality(i,j,k),state%cloud_ice%source(i,j,k)) .AND. &
       cell_is_usable(state%rain%valid(i,j,k),state%rain%quality(i,j,k),state%rain%source(i,j,k)) .AND. &
       cell_is_usable(state%snow%valid(i,j,k),state%snow%quality(i,j,k),state%snow%source(i,j,k)) .AND. &
       cell_is_usable(state%graupel%valid(i,j,k),state%graupel%quality(i,j,k),state%graupel%source(i,j,k))
    IF (.NOT.ok) RETURN
    ok=ieee_is_finite(state%geopotential%value(i,j,k))
  END FUNCTION hydrostatic_cell_available

  PURE REAL(real64) FUNCTION moist_species_enthalpy(temperature,species)
    REAL(real64), INTENT(IN) :: temperature,species(6)
    ! J / kg dry air; liquid and dry-air enthalpy are zero at THERMO_T0.
    ! Pure diagnostic for finite canonical-range inputs, validated by callers.
    moist_species_enthalpy=(THERMO_CP_DRY+SUM(SPECIES_CP*species))* &
      (temperature-THERMO_T0)+SUM(SPECIES_H0*species)
  END FUNCTION moist_species_enthalpy

  PURE SUBROUTINE remap_pressure_column(old_interfaces,old_dry_mass,old_temperature,old_species, &
      new_interfaces,new_dry_mass,new_temperature,new_species,status)
    REAL(real64), INTENT(IN) :: old_interfaces(:),old_dry_mass(:),old_temperature(:),old_species(:,:)
    REAL(real64), INTENT(IN) :: new_interfaces(:)
    REAL(real64), INTENT(INOUT) :: new_dry_mass(:),new_temperature(:),new_species(:,:)
    INTEGER, INTENT(OUT) :: status
    REAL(real64), ALLOCATABLE :: mass(:),temperature(:),species(:,:)
    REAL(real128) :: width,overlap,weight,donor_mass,cell_mass,water_mass(6)
    REAL(real128) :: capacity,temperature_moment,cell_temperature
    REAL(real128) :: old_total(8),new_total(8),scale(8),amount(8),tolerance
    INTEGER :: n,m,j,k,donors,donor

    ! Conservative repartition, NOT an analysis increment or a phase change.
    ! Assume piecewise-constant extensive density per Pa in each donor cell.
    ! Changing the column endpoints needs a separate, explicit boundary budget.
    ! All six species are kg/kg dry air. The heat-capacity moment conserves
    ! the existing linear mixture enthalpy; it is not compressible total energy.
    ! Callers supply usable positive-width donor cells and validate their
    ! md*(1+sum(r)) against A*dp/g. Missing cells are not zero-valued donors.
    ! Canonical float32 storage needs its own mass/enthalpy closure check;
    ! success here only certifies these float64 arrays, not a native state.
    status=STATUS_FAILED
    n=SIZE(old_dry_mass); m=SIZE(new_dry_mass)
    IF (n<1 .OR. m<1) RETURN
    IF (SIZE(old_interfaces)/=n+1 .OR. SIZE(new_interfaces)/=m+1 .OR. &
        SIZE(old_temperature)/=n .OR. SIZE(new_temperature)/=m .OR. &
        ANY(SHAPE(old_species)/=[6,n]) .OR. ANY(SHAPE(new_species)/=[6,m])) RETURN
    IF (ANY(.NOT.ieee_is_finite(old_interfaces)) .OR. ANY(.NOT.ieee_is_finite(new_interfaces)) .OR. &
        ANY(.NOT.ieee_is_finite(old_dry_mass)) .OR. ANY(.NOT.ieee_is_finite(old_temperature)) .OR. &
        ANY(.NOT.ieee_is_finite(old_species))) RETURN
    IF (ANY(old_interfaces<=0.0_real64) .OR. ANY(new_interfaces<=0.0_real64) .OR. &
        ANY(old_dry_mass<=0.0_real64) .OR. ANY(old_temperature<150.0_real64) .OR. &
        ANY(old_temperature>350.0_real64) .OR. ANY(old_species<0.0_real64) .OR. &
        ANY(old_species>REAL(HUGE(1.0_real32),real64)) .OR. &
        ANY(old_species(1,:)>REAL(0.2_real32,real64))) RETURN
    IF (ANY(old_interfaces(:n)<=old_interfaces(2:)) .OR. &
        ANY(new_interfaces(:m)<=new_interfaces(2:))) RETURN
    IF (old_interfaces(1)/=new_interfaces(1) .OR. old_interfaces(n+1)/=new_interfaces(m+1)) RETURN
    IF (n==m) THEN
      IF (ALL(old_interfaces==new_interfaces)) THEN
        new_dry_mass=old_dry_mass; new_temperature=old_temperature; new_species=old_species
        status=STATUS_OK
        RETURN
      END IF
    END IF

    ALLOCATE(mass(m),temperature(m),species(6,m))
    DO j=1,m
      cell_mass=0.0_real128; water_mass=0.0_real128; temperature_moment=0.0_real128
      donors=0; donor=0
      DO k=1,n
        overlap=MIN(REAL(old_interfaces(k),real128),REAL(new_interfaces(j),real128))- &
          MAX(REAL(old_interfaces(k+1),real128),REAL(new_interfaces(j+1),real128))
        IF (overlap<=0.0_real128) CYCLE
        width=REAL(old_interfaces(k),real128)-REAL(old_interfaces(k+1),real128)
        weight=overlap/width
        donor_mass=weight*REAL(old_dry_mass(k),real128)
        cell_mass=cell_mass+donor_mass
        water_mass=water_mass+donor_mass*REAL(old_species(:,k),real128)
        capacity=REAL(THERMO_CP_DRY,real128)+ &
          SUM(REAL(SPECIES_CP,real128)*REAL(old_species(:,k),real128))
        temperature_moment=temperature_moment+donor_mass*capacity*REAL(old_temperature(k),real128)
        donors=donors+1; donor=k
      END DO
      ! Wide accumulation permits a clean rejection of unrepresentable totals
      ! under the checked compiler's overflow traps. Public arrays stay float64.
      IF (donors==0 .OR. cell_mass<REAL(TINY(1.0_real64),real128) .OR. &
          cell_mass>REAL(HUGE(1.0_real64),real128)) RETURN
      mass(j)=REAL(cell_mass,real64)
      IF (donors==1) THEN
        ! Exact identity for untouched layers, and no artificial mixing when
        ! one donor is split into smaller cells.
        temperature(j)=old_temperature(donor); species(:,j)=old_species(:,donor)
      ELSE
        species(:,j)=REAL(water_mass/cell_mass,real64)
        capacity=REAL(THERMO_CP_DRY,real128)*cell_mass+SUM(REAL(SPECIES_CP,real128)*water_mass)
        cell_temperature=temperature_moment/capacity
        temperature(j)=REAL(cell_temperature,real64)
      END IF
    END DO

    ! Recompute all extensive totals from the actual public-precision result.
    ! Use absolute contributions for the signed enthalpy cancellation scale.
    old_total=0.0_real128; new_total=0.0_real128; scale=0.0_real128
    DO k=1,n
      amount(1)=REAL(old_dry_mass(k),real128)
      amount(2:7)=amount(1)*REAL(old_species(:,k),real128)
      amount(8)=amount(1)*REAL(moist_species_enthalpy(old_temperature(k),old_species(:,k)),real128)
      old_total=old_total+amount; scale=scale+ABS(amount)
    END DO
    DO j=1,m
      amount(1)=REAL(mass(j),real128)
      amount(2:7)=amount(1)*REAL(species(:,j),real128)
      amount(8)=amount(1)*REAL(moist_species_enthalpy(temperature(j),species(:,j)),real128)
      new_total=new_total+amount; scale=scale+ABS(amount)
    END DO
    tolerance=128.0_real128*REAL(EPSILON(1.0_real64),real128)
    IF (ANY(ABS(new_total-old_total)>tolerance*scale)) RETURN
    new_dry_mass=mass; new_temperature=temperature; new_species=species
    status=STATUS_OK
  END SUBROUTINE remap_pressure_column

  PURE SUBROUTINE apply_water_phase_transfer(temperature,species,delta,status)
    REAL(real64), INTENT(INOUT) :: temperature,species(6)
    REAL(real64), INTENT(IN) :: delta(6)
    INTEGER, INTENT(OUT) :: status
    REAL(real64) :: proposed(6),new_temperature,phase_change,capacity,water_tolerance
    REAL(real64) :: sensible,energy_scale

    ! The caller supplies internal phase transfers, NOT analysis increments.
    ! No phase/rate is selected by temperature; supercooled water is permitted.
    ! A kinetic/observation caller must separately justify the proposed amounts.
    status=STATUS_FAILED
    IF (.NOT.ieee_is_finite(temperature) .OR. ANY(.NOT.ieee_is_finite(species)) .OR. &
        ANY(.NOT.ieee_is_finite(delta))) RETURN
    IF (temperature<150.0_real64 .OR. temperature>350.0_real64 .OR. &
        ANY(species<0.0_real64) .OR. &
        ANY(species>REAL(HUGE(1.0_real32),real64)) .OR. &
        species(1)>REAL(0.2_real32,real64) .OR. &
        ANY(ABS(delta)>REAL(HUGE(1.0_real32),real64))) RETURN
    water_tolerance=64.0_real64*EPSILON(1.0_real64)*SUM(ABS(delta))
    IF (ABS(SUM(delta))>water_tolerance) RETURN
    proposed=species+delta
    IF (ANY(proposed<0.0_real64) .OR. ANY(proposed>REAL(HUGE(1.0_real32),real64)) .OR. &
        proposed(1)>REAL(0.2_real32,real64)) RETURN
    capacity=THERMO_CP_DRY+SUM(SPECIES_CP*proposed)
    ! Exact finite-transfer enthalpy equation, including all water heat
    ! capacities and temperature-dependent latent enthalpy differences.
    phase_change=SUM(delta*(SPECIES_H0+SPECIES_CP*(temperature-THERMO_T0)))
    new_temperature=temperature-phase_change/capacity
    IF (new_temperature<150.0_real64 .OR. new_temperature>350.0_real64) RETURN
    ! Recheck actual stored float64 changes, not just the requested delta.
    phase_change=SUM((proposed-species)*(SPECIES_H0+SPECIES_CP*(temperature-THERMO_T0)))
    sensible=capacity*(new_temperature-temperature)
    energy_scale=capacity*MAX(ABS(new_temperature),ABS(temperature))+ABS(phase_change)
    IF (ABS(sensible+phase_change)>256.0_real64*EPSILON(1.0_real64)*energy_scale) RETURN
    IF (ABS(SUM(proposed-species))>64.0_real64*EPSILON(1.0_real64)* &
        MAX(SUM(ABS(species)),SUM(ABS(delta)))) RETURN
    temperature=new_temperature; species=proposed
    status=STATUS_OK
  END SUBROUTINE apply_water_phase_transfer

  SUBROUTINE apply_pressure_phase_transfer(state_in,state_out,result,active,delta,budget)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state_in
    TYPE(cloud_bal_state_type), INTENT(OUT) :: state_out
    TYPE(stage_result), INTENT(OUT) :: result
    LOGICAL, INTENT(IN) :: active(:,:,:)
    REAL(real64), INTENT(IN) :: delta(:,:,:,:)
    TYPE(water_phase_budget), INTENT(OUT) :: budget
    CALL pressure_thermo_candidate(state_in,state_out,result,active,budget,delta=delta)
  END SUBROUTINE apply_pressure_phase_transfer

  SUBROUTINE saturation_adjust_pressure_state(state_in,state_out,result,active,target_rh,budget,surface)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state_in
    TYPE(cloud_bal_state_type), INTENT(OUT) :: state_out
    TYPE(stage_result), INTENT(OUT) :: result
    LOGICAL, INTENT(IN) :: active(:,:,:)
    REAL(real64), INTENT(IN) :: target_rh
    TYPE(water_phase_budget), INTENT(OUT) :: budget
    INTEGER, INTENT(IN) :: surface(:,:,:)
    CALL pressure_thermo_candidate(state_in,state_out,result,active,budget,target_rh=target_rh,surface=surface)
  END SUBROUTINE saturation_adjust_pressure_state

  SUBROUTINE pressure_thermo_candidate(state_in,state_out,result,active,budget,delta,target_rh,surface)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state_in
    TYPE(cloud_bal_state_type), INTENT(OUT) :: state_out
    TYPE(stage_result), INTENT(OUT) :: result
    LOGICAL, INTENT(IN) :: active(:,:,:)
    REAL(real64), INTENT(IN), OPTIONAL :: delta(:,:,:,:),target_rh
    INTEGER, INTENT(IN), OPTIONAL :: surface(:,:,:)
    TYPE(water_phase_budget), INTENT(OUT) :: budget
    TYPE(cloud_bal_state_type) :: candidate
    TYPE(stage_result) :: candidate_result
    TYPE(water_phase_budget) :: candidate_budget
    REAL(real64) :: before(6),after(6),change(6),temperature,initial_t,stored_t
    REAL(real64) :: capacity,phase_change,sensible,mass,term_limit,scale,storage_epsilon
    REAL(real32) :: stored(6)
    INTEGER :: nx,ny,nz,i,j,k,status,reason
    INTEGER(int64) :: selected

    ! One storage, budget and rollback path for both internal phase operations.
    ! Fixed dry mass/geometry; no analysis increments or authority grant.
    ! Copied targets and fall speeds are stale until a coupled caller refreshes
    ! dependent diagnostics; derive_column_physics does so for explicit requests.
    CALL reject_candidate(state_in,state_out,result,STATUS_FAILED,REASON_SHAPE)
    budget=water_phase_budget()
    nx=state_in%grid%nx; ny=state_in%grid%ny; nz=state_in%grid%nz
    IF (ANY(SHAPE(active)/=[nx,ny,nz])) RETURN
    IF (PRESENT(delta)) THEN
      IF (ANY(SHAPE(delta)/=[nx,ny,nz,6])) RETURN
    ELSE
      IF (.NOT.PRESENT(surface) .OR. .NOT.PRESENT(target_rh)) RETURN
      IF (ANY(SHAPE(surface)/=[nx,ny,nz])) RETURN
      result%reason_code=REASON_RANGE
      IF (.NOT.ieee_is_finite(target_rh)) RETURN
      IF (target_rh<0.0_real64 .OR. target_rh>1.0_real64) RETURN
      IF (ANY(active .AND. (surface/=SATURATION_LIQUID) .AND. &
          (surface/=SATURATION_ICE))) RETURN
    END IF
    CALL validate_canonical_state(state_in,.FALSE.,.FALSE.,status,reason,.FALSE.)
    IF (status/=STATUS_OK) THEN
      result%status=status; result%reason_code=reason
      RETURN
    END IF
    result%reason_code=REASON_RANGE
    IF (ANY(active .AND. .NOT.state_in%above_ground)) RETURN
    selected=COUNT(active,KIND=int64)
    IF (selected==0_int64) THEN
      result%status=STATUS_OK; result%reason_code=REASON_NONE
      RETURN
    END IF
    result%reason_code=REASON_REQUIRED_COVERAGE
    IF (ANY(active .AND. .NOT.( &
      cell_is_usable(state_in%cloud_water%valid,state_in%cloud_water%quality,state_in%cloud_water%source) .AND. &
      cell_is_usable(state_in%cloud_ice%valid,state_in%cloud_ice%quality,state_in%cloud_ice%source) .AND. &
      cell_is_usable(state_in%rain%valid,state_in%rain%quality,state_in%rain%source) .AND. &
      cell_is_usable(state_in%snow%valid,state_in%snow%quality,state_in%snow%source) .AND. &
      cell_is_usable(state_in%graupel%valid,state_in%graupel%quality,state_in%graupel%source)))) RETURN
    candidate=state_in
    CALL initialize_stage_result(candidate_result,nx,ny,nz,STATUS_OK,REASON_NONE)
    candidate_budget=water_phase_budget()
    term_limit=HUGE(1.0_real64)/(32.0_real64*REAL(selected,real64))
    storage_epsilon=REAL(EPSILON(1.0_real32),real64)
    DO k=1,nz; DO j=1,ny; DO i=1,nx
      IF (.NOT.active(i,j,k)) CYCLE
      initial_t=REAL(state_in%temperature%value(i,j,k),real64)
      before=REAL([state_in%vapor%value(i,j,k),state_in%cloud_water%value(i,j,k), &
        state_in%cloud_ice%value(i,j,k),state_in%rain%value(i,j,k), &
        state_in%snow%value(i,j,k),state_in%graupel%value(i,j,k)],real64)
      temperature=initial_t; after=before
      IF (PRESENT(delta)) THEN
        change=delta(i,j,k,:)
        CALL apply_water_phase_transfer(temperature,after,change,status)
      ELSE
        CALL saturation_adjust_mixture_cell(REAL(state_in%pressure%value(i,j,k),real64), &
          temperature,after,target_rh,status,surface(i,j,k))
      END IF
      result%reason_code=REASON_SOLVER
      IF (status/=STATUS_OK) RETURN
      stored=REAL(after,real32); stored_t=REAL(REAL(temperature,real32),real64)
      after=REAL(stored,real64); change=after-before
      result%reason_code=REASON_GATE
      IF (.NOT.PRESENT(delta)) THEN
        IF (.NOT.saturation_is_closed(REAL(state_in%pressure%value(i,j,k),real64), &
          stored_t,after,target_rh,surface(i,j,k),storage_epsilon)) RETURN
      END IF
      capacity=THERMO_CP_DRY+SUM(SPECIES_CP*after)
      sensible=capacity*(stored_t-initial_t)
      phase_change=SUM(change*(SPECIES_H0+SPECIES_CP*(initial_t-THERMO_T0)))
      result%reason_code=REASON_GATE
      IF (ABS(SUM(change))>4.0_real64*storage_epsilon*SUM(ABS(before))) RETURN
      scale=capacity*ABS(initial_t)+SUM(ABS(before*(SPECIES_H0+ &
        SPECIES_CP*(initial_t-THERMO_T0))))
      IF (ABS(sensible+phase_change)>4.0_real64*storage_epsilon*scale) RETURN
      mass=state_in%grid%dry_air_mass_measure(i,j,k)
      scale=MAX(MAXVAL(ABS(change)),ABS(sensible),ABS(phase_change))
      IF (mass>1.0_real64) THEN
        IF (scale>term_limit/mass) RETURN
      ELSE
        IF (scale>term_limit) RETURN
      END IF
      candidate_budget%species_change_kg=candidate_budget%species_change_kg+mass*change
      candidate_budget%sensible_change_j=candidate_budget%sensible_change_j+mass*sensible
      candidate_budget%phase_change_j=candidate_budget%phase_change_j+mass*phase_change
      candidate_result%changed(i,j,k)=stored_t/=initial_t .OR. ANY(change/=0.0_real64)
      CALL store_thermo_value(candidate%temperature,i,j,k,REAL(stored_t,real32))
      CALL store_thermo_value(candidate%vapor,i,j,k,stored(1))
      CALL store_thermo_value(candidate%cloud_water,i,j,k,stored(2))
      CALL store_thermo_value(candidate%cloud_ice,i,j,k,stored(3))
      CALL store_thermo_value(candidate%rain,i,j,k,stored(4))
      CALL store_thermo_value(candidate%snow,i,j,k,stored(5))
      CALL store_thermo_value(candidate%graupel,i,j,k,stored(6))
    END DO; END DO; END DO
    CALL validate_canonical_state(candidate,.FALSE.,.FALSE.,status,reason,.FALSE.)
    IF (status/=STATUS_OK) THEN
      result%status=status; result%reason_code=reason
      RETURN
    END IF
    candidate_budget%water_error_kg=SUM(candidate_budget%species_change_kg)
    candidate_budget%enthalpy_error_j=candidate_budget%sensible_change_j+candidate_budget%phase_change_j
    candidate_result%coverage%required=selected; candidate_result%coverage%usable=selected
    candidate_result%coverage%usable_fraction=1.0_real64
    candidate_result%numerical%ledger_error=candidate_budget%water_error_kg
    candidate_result%numerical%enthalpy_error=candidate_budget%enthalpy_error_j
    state_out=candidate; result=candidate_result; budget=candidate_budget
  END SUBROUTINE pressure_thermo_candidate

  SUBROUTINE store_thermo_value(field,i,j,k,value)
    TYPE(field3d), INTENT(INOUT) :: field
    INTEGER, INTENT(IN) :: i,j,k
    REAL(real32), INTENT(IN) :: value
    IF (value==field%value(i,j,k)) RETURN
    field%value(i,j,k)=value
    field%source(i,j,k)=IOR(field%source(i,j,k),SOURCE_COLUMN_PHYSICS)
  END SUBROUTINE store_thermo_value

  SUBROUTINE saturation_adjust_column(pressure,dry_mass,active,target_rh, &
                                      temperature,vapor,cloud_liquid,cloud_ice,budget,status,surface)
    REAL(real64), INTENT(IN) :: pressure(:),dry_mass(:),target_rh
    LOGICAL, INTENT(IN) :: active(:)
    REAL(real64), INTENT(INOUT) :: temperature(:),vapor(:),cloud_liquid(:),cloud_ice(:)
    TYPE(cloud_thermo_budget), INTENT(OUT) :: budget
    INTEGER, INTENT(OUT) :: status
    INTEGER, INTENT(IN) :: surface(:)
    TYPE(cloud_thermo_budget) :: candidate_budget
    REAL(real64), ALLOCATABLE :: work(:,:)
    REAL(real64) :: dv,dl,di,sensible,latent,scale,term_limit,before(6),after(6)
    INTEGER :: n,k,cell_status,allocation_status

    ! A standalone numerical transaction, not an authority-granting pipeline
    ! stage. The caller supplies fixed kg dry air per cell; pressure is input
    ! to saturation only. No mass-coordinate/EOS reconstruction is implied.
    ! Units: pressure Pa, temperature K, species kg / kg dry air, budget kg/J.
    status=STATUS_FAILED; budget=cloud_thermo_budget()
    n=SIZE(active)
    IF (SIZE(pressure)/=n .OR. SIZE(dry_mass)/=n .OR. SIZE(temperature)/=n .OR. &
        SIZE(vapor)/=n .OR. SIZE(cloud_liquid)/=n .OR. SIZE(cloud_ice)/=n .OR. &
        SIZE(surface)/=n) RETURN
    IF (.NOT.ieee_is_finite(target_rh)) RETURN
    IF (target_rh<0.0_real64 .OR. target_rh>1.0_real64) RETURN
    IF (.NOT.ANY(active)) THEN
      status=STATUS_OK
      RETURN
    END IF
    IF (ANY(active .AND. (surface/=SATURATION_LIQUID) .AND. &
        (surface/=SATURATION_ICE))) RETURN
    ALLOCATE(work(n,4),STAT=allocation_status)
    IF (allocation_status/=0) RETURN
    candidate_budget=cloud_thermo_budget()
    ! Leave headroom for weighted terms, their sums and residuals under fpe0.
    term_limit=HUGE(1.0_real64)/(16.0_real64*REAL(COUNT(active),real64))
    DO k=1,n
      IF (.NOT.active(k)) CYCLE
      IF (.NOT.ieee_is_finite(dry_mass(k))) RETURN
      IF (dry_mass(k)<=0.0_real64) RETURN
      work(k,:)=[temperature(k),vapor(k),cloud_liquid(k),cloud_ice(k)]
      CALL saturation_adjust_cell(pressure(k),work(k,1),work(k,2),work(k,3),work(k,4), &
                                  target_rh,cell_status,surface(k))
      IF (cell_status/=STATUS_OK) RETURN
      dv=work(k,2)-vapor(k); dl=work(k,3)-cloud_liquid(k); di=work(k,4)-cloud_ice(k)
      ! Use state increments, avoiding subtraction of large total enthalpies.
      before=[vapor(k),cloud_liquid(k),cloud_ice(k),0.0_real64,0.0_real64,0.0_real64]
      after=[work(k,2:4),0.0_real64,0.0_real64,0.0_real64]
      sensible=(THERMO_CP_DRY+SUM(SPECIES_CP*after))*(work(k,1)-temperature(k))
      latent=SUM((after-before)*(SPECIES_H0+SPECIES_CP*(temperature(k)-THERMO_T0)))
      scale=MAX(ABS(dv),ABS(dl),ABS(di),ABS(sensible),ABS(latent))
      IF (dry_mass(k)>1.0_real64) THEN
        IF (scale>term_limit/dry_mass(k)) RETURN
      ELSE
        IF (scale>term_limit) RETURN
      END IF
      candidate_budget%vapor_change_kg=candidate_budget%vapor_change_kg+dry_mass(k)*dv
      candidate_budget%liquid_change_kg=candidate_budget%liquid_change_kg+dry_mass(k)*dl
      candidate_budget%ice_change_kg=candidate_budget%ice_change_kg+dry_mass(k)*di
      candidate_budget%sensible_heat_change_j=candidate_budget%sensible_heat_change_j+dry_mass(k)*sensible
      candidate_budget%latent_heat_change_j=candidate_budget%latent_heat_change_j+dry_mass(k)*latent
    END DO
    candidate_budget%water_error_kg=candidate_budget%vapor_change_kg+ &
      candidate_budget%liquid_change_kg+candidate_budget%ice_change_kg
    candidate_budget%enthalpy_error_j=candidate_budget%sensible_heat_change_j+ &
      candidate_budget%latent_heat_change_j
    ! Commit only after every selected cell and weighted budget succeeded.
    DO k=1,n
      IF (.NOT.active(k)) CYCLE
      temperature(k)=work(k,1); vapor(k)=work(k,2)
      cloud_liquid(k)=work(k,3); cloud_ice(k)=work(k,4)
    END DO
    budget=candidate_budget
    status=STATUS_OK
  END SUBROUTINE saturation_adjust_column

  SUBROUTINE saturation_adjust_cell(pressure,temperature,vapor,cloud_liquid, &
                                    cloud_ice,target_rh,status,surface)
    REAL(real64), INTENT(IN) :: pressure,target_rh
    REAL(real64), INTENT(INOUT) :: temperature,vapor,cloud_liquid,cloud_ice
    INTEGER, INTENT(OUT) :: status
    INTEGER, INTENT(IN) :: surface
    REAL(real64) :: species(6)
    ! Cloud-only specialization: exactly the same mixture law, with no precip.
    species=[vapor,cloud_liquid,cloud_ice,0.0_real64,0.0_real64,0.0_real64]
    CALL saturation_adjust_mixture_cell(pressure,temperature,species,target_rh,status,surface)
    IF (status/=STATUS_OK) RETURN
    vapor=species(1); cloud_liquid=species(2); cloud_ice=species(3)
  END SUBROUTINE saturation_adjust_cell

  PURE SUBROUTINE saturation_adjust_mixture_cell(pressure,temperature,species,target_rh,status,surface)
    REAL(real64), INTENT(IN) :: pressure,target_rh
    REAL(real64), INTENT(INOUT) :: temperature,species(6)
    INTEGER, INTENT(OUT) :: status
    INTEGER, INTENT(IN) :: surface
    REAL(real64) :: initial_t,trial_t,work(6),delta(6),capacity,latent,delta_cp,maximum_t
    REAL(real64) :: lo,hi,mid,flo,fhi,fmid,offset
    REAL(real64) :: lower_t,upper_t,lower_species(6),upper_species(6)
    INTEGER :: phase,iteration,transfer_status

    status=STATUS_FAILED
    IF (surface/=SATURATION_LIQUID .AND. surface/=SATURATION_ICE) RETURN
    IF (.NOT.ieee_is_finite(pressure) .OR. .NOT.ieee_is_finite(target_rh)) RETURN
    IF (pressure<MIN_PRESSURE_PA .OR. pressure>MAX_PRESSURE_PA .OR. &
        target_rh<0.0_real64 .OR. target_rh>1.0_real64) RETURN
    ! Reuse the transfer kernel's finite-input, range and positivity contract.
    initial_t=temperature; work=species; delta=0.0_real64
    CALL apply_water_phase_transfer(initial_t,work,delta,transfer_status)
    IF (transfer_status/=STATUS_OK) RETURN
    phase=2; maximum_t=350.0_real64
    IF (surface==SATURATION_ICE) THEN
      phase=3; maximum_t=THERMO_T0
      IF (initial_t>maximum_t) RETURN
    END IF
    capacity=THERMO_CP_DRY+SUM(SPECIES_CP*species)
    delta_cp=SPECIES_CP(1)-SPECIES_CP(phase)
    latent=SPECIES_H0(1)-SPECIES_H0(phase)+delta_cp*(initial_t-THERMO_T0)
    ! Exact enthalpy: T(e)=Ti-e*L(Ti)/(Cp(initial)+e*delta_cp).
    ! Intersect vapor/condensate availability with temperature and vapor bounds.
    ! All other species stay fixed but contribute to the heat capacity.
    offset=initial_t-maximum_t
    lo=MAX(-species(1),offset*capacity/(latent-offset*delta_cp))
    offset=initial_t-150.0_real64
    hi=MIN(species(phase),REAL(0.2_real32,real64)-species(1), &
      offset*capacity/(latent-offset*delta_cp))
    IF (lo>hi) RETURN
    trial_t=initial_t-lo*latent/(capacity+lo*delta_cp)
    flo=species(1)+lo-target_rh*saturation_mixing_ratio(trial_t,pressure,surface==SATURATION_ICE)
    trial_t=initial_t-hi*latent/(capacity+hi*delta_cp)
    fhi=species(1)+hi-target_rh*saturation_mixing_ratio(trial_t,pressure,surface==SATURATION_ICE)
    IF (flo>0.0_real64) THEN
      RETURN
    ELSE IF (fhi<0.0_real64) THEN
      ! Exhaustion can leave subsaturation; a temperature/vapor cap cannot.
      IF (hi<species(phase)) RETURN
      mid=hi
    ELSE
      DO iteration=1,80
        mid=lo+0.5_real64*(hi-lo)
        trial_t=initial_t-mid*latent/(capacity+mid*delta_cp)
        fmid=species(1)+mid-target_rh*saturation_mixing_ratio(trial_t,pressure,surface==SATURATION_ICE)
        ! Resolve the transfer before float32 storage: a small residual alone
        ! can still select the adjacent stored condensate value.
        IF (mid==lo .OR. mid==hi .OR. fmid==0.0_real64) EXIT
        IF (fmid>0.0_real64) THEN
          hi=mid
        ELSE
          lo=mid
        END IF
        IF (hi-lo<=MAX(1.0e-14_real64, &
          1.0e-12_real64*MAX(ABS(lo),ABS(hi),1.0e-12_real64)) .AND. &
          ABS(fmid)<=1.0e-11_real64) THEN
          ! Near-zero transfers need not reach identical float64 endpoints
          ! when the entire bracket already gives one canonical stored state.
          lower_t=initial_t; lower_species=species
          delta=0.0_real64; delta(1)=lo; delta(phase)=-lo
          CALL apply_water_phase_transfer(lower_t,lower_species,delta,transfer_status)
          IF (transfer_status/=STATUS_OK) RETURN
          upper_t=initial_t; upper_species=species
          delta=0.0_real64; delta(1)=hi; delta(phase)=-hi
          CALL apply_water_phase_transfer(upper_t,upper_species,delta,transfer_status)
          IF (transfer_status/=STATUS_OK) RETURN
          IF (REAL(lower_t,real32)==REAL(upper_t,real32) .AND. &
              ALL(REAL(lower_species,real32)==REAL(upper_species,real32))) EXIT
        END IF
      END DO
      IF (iteration>80) RETURN
    END IF
    delta=0.0_real64; delta(1)=mid; delta(phase)=-mid
    trial_t=initial_t; work=species
    CALL apply_water_phase_transfer(trial_t,work,delta,transfer_status)
    IF (transfer_status/=STATUS_OK) RETURN
    IF (trial_t>maximum_t) RETURN
    IF (.NOT.saturation_is_closed(pressure,trial_t,work,target_rh,surface,0.0_real64)) RETURN
    temperature=trial_t; species=work; status=STATUS_OK
  END SUBROUTINE saturation_adjust_mixture_cell

  PURE LOGICAL FUNCTION saturation_is_closed(pressure,temperature,species,target_rh,surface,roundoff)
    REAL(real64), INTENT(IN) :: pressure,temperature,species(6),target_rh,roundoff
    INTEGER, INTENT(IN) :: surface
    REAL(real64) :: lower,upper,temperature_error,vapor_error
    INTEGER :: phase
    LOGICAL :: over_ice
    over_ice=surface==SATURATION_ICE
    phase=2
    IF (over_ice) phase=3
    ! Monotone saturation bounds separate root accuracy from float32 storage.
    ! Subsaturation is permitted only when the selected reservoir is exhausted.
    temperature_error=roundoff*ABS(temperature)
    vapor_error=1.0e-11_real64+roundoff*ABS(species(1))
    lower=target_rh*saturation_mixing_ratio(temperature-temperature_error,pressure,over_ice)
    upper=target_rh*saturation_mixing_ratio(temperature+temperature_error,pressure,over_ice)
    saturation_is_closed=species(1)<=upper+vapor_error .AND. &
      (species(phase)==0.0_real64 .OR. species(1)>=lower-vapor_error)
  END FUNCTION saturation_is_closed

  PURE REAL(real64) FUNCTION saturation_mixing_ratio(temperature,pressure,over_ice)
    REAL(real64), INTENT(IN) :: temperature,pressure
    LOGICAL, INTENT(IN) :: over_ice
    REAL(real64) :: es,tc
    tc=temperature-273.15_real64
    IF (over_ice) THEN
      es=611.15_real64*EXP(22.452_real64*tc/(temperature-0.55_real64))
    ELSE
      es=611.20_real64*EXP(17.67_real64*tc/(tc+243.5_real64))
    END IF
    es=MIN(0.99_real64*pressure,MAX(0.0_real64,es))
    saturation_mixing_ratio=EPSILON_WATER*es/(pressure-es)
  END FUNCTION saturation_mixing_ratio

  PURE LOGICAL FUNCTION flux_ledger_closes(ledger,cfg)
    TYPE(precipitation_flux_ledger), INTENT(IN) :: ledger
    TYPE(column_physics_config), INTENT(IN) :: cfg
    REAL(real64) :: output,error
    flux_ledger_closes=.FALSE.
    IF (.NOT.column_config_valid(cfg)) RETURN
    IF (.NOT.ieee_is_finite(ledger%input) .OR. &
        .NOT.ieee_is_finite(ledger%deposited) .OR. &
        .NOT.ieee_is_finite(ledger%suspended) .OR. &
        .NOT.ieee_is_finite(ledger%boundary_exit) .OR. &
        .NOT.ieee_is_finite(ledger%terrain_intercept) .OR. &
        .NOT.ieee_is_finite(ledger%observation_blocked) .OR. &
        .NOT.ieee_is_finite(ledger%no_echo_blocked) .OR. &
        .NOT.ieee_is_finite(ledger%microphysical_loss)) RETURN
    IF (ledger%input<0.0_real64 .OR. ledger%deposited<0.0_real64 .OR. &
        ledger%suspended<0.0_real64 .OR. ledger%boundary_exit<0.0_real64 .OR. &
        ledger%terrain_intercept<0.0_real64 .OR. &
        ledger%observation_blocked<0.0_real64 .OR. &
        ledger%no_echo_blocked<0.0_real64 .OR. &
        ledger%microphysical_loss<0.0_real64) RETURN
    output=ledger%deposited+ledger%suspended+ledger%boundary_exit+ &
           ledger%terrain_intercept+ledger%observation_blocked+ &
           ledger%no_echo_blocked+ledger%microphysical_loss
    error=ABS(ledger%input-output)
    flux_ledger_closes=ieee_is_finite(error) .AND. error<= &
      cfg%ledger_absolute_tolerance+cfg%ledger_relative_tolerance* &
      MAX(ABS(ledger%input),ABS(output))
  END FUNCTION flux_ledger_closes

  PURE REAL(real64) FUNCTION hydrometeor_mass(state)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    REAL(real64), ALLOCATABLE :: total(:,:,:)
    ALLOCATE(total(state%grid%nx,state%grid%ny,state%grid%nz))
    total=0.0_real64
    WHERE(cell_is_usable(state%cloud_water%valid,state%cloud_water%quality, &
                         state%cloud_water%source))
      total=total+REAL(state%cloud_water%value,real64)
    END WHERE
    WHERE(cell_is_usable(state%cloud_ice%valid,state%cloud_ice%quality, &
                         state%cloud_ice%source))
      total=total+REAL(state%cloud_ice%value,real64)
    END WHERE
    WHERE(cell_is_usable(state%rain%valid,state%rain%quality,state%rain%source)) &
      total=total+REAL(state%rain%value,real64)
    WHERE(cell_is_usable(state%snow%valid,state%snow%quality,state%snow%source)) &
      total=total+REAL(state%snow%value,real64)
    WHERE(cell_is_usable(state%graupel%valid,state%graupel%quality, &
                         state%graupel%source)) &
      total=total+REAL(state%graupel%value,real64)
    hydrometeor_mass=SUM(total*state%grid%dry_air_mass_measure, &
                         MASK=state%above_ground)
  END FUNCTION hydrometeor_mass

  PURE REAL(real64) FUNCTION layer_separation(grid,pressure,temperature,vapor,i,j,k, &
                                               lower_cell_active)
    TYPE(grid_spec), INTENT(IN) :: grid
    REAL(real32), INTENT(IN) :: pressure(:,:,:),temperature(:,:,:),vapor(:,:,:)
    INTEGER, INTENT(IN) :: i,j,k
    LOGICAL, INTENT(IN) :: lower_cell_active
    REAL(real64) :: rho,pressure_separation
    ! Pressure thickness uses moist gas mass, not just the dry-air mass
    ! used by the species flux ledger. Condensate loading remains excluded.
    rho=moist_gas_density(REAL(pressure(i,j,k),real64), &
      REAL(temperature(i,j,k),real64),REAL(vapor(i,j,k),real64))
    layer_separation=-1.0_real64
    IF (rho<=0.0_real64) RETURN
    IF (lower_cell_active) THEN
      pressure_separation=grid%level_spacing_dp(i,j,k-1)
    ELSE
      pressure_separation=grid%pressure_interface(i,j,k)- &
                          REAL(pressure(i,j,k),real64)
    END IF
    layer_separation=pressure_separation/(rho*GRAVITY)
  END FUNCTION layer_separation

  PURE INTEGER FUNCTION cloud_regime(cloud_type)
    INTEGER(int32), INTENT(IN) :: cloud_type
    IF (is_convective_type(cloud_type)) THEN
      cloud_regime=REGIME_CONVECTIVE
    ELSE IF (cloud_type==4_int32) THEN
      cloud_regime=REGIME_PRECIPITATING
    ELSE IF (cloud_type>0_int32) THEN
      cloud_regime=REGIME_STRATIFORM
    ELSE
      cloud_regime=REGIME_CLEAR
    END IF
  END FUNCTION cloud_regime

  PURE LOGICAL FUNCTION is_convective_type(cloud_type)
    INTEGER(int32), INTENT(IN) :: cloud_type
    is_convective_type=cloud_type==3_int32 .OR. cloud_type==10_int32 .OR. &
                       cloud_type==11_int32
  END FUNCTION is_convective_type

  SUBROUTINE validate_optional_cloud_pair(state,present,status,reason)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    LOGICAL, INTENT(OUT) :: present
    INTEGER, INTENT(OUT) :: status,reason
    INTEGER :: target(3)
    LOGICAL, ALLOCATABLE :: fraction_usable(:,:,:),type_usable(:,:,:)

    present=.FALSE.; status=STATUS_FAILED; reason=REASON_METADATA
    target=(/state%grid%nx,state%grid%ny,state%grid%nz/)
    IF (.NOT.ALLOCATED(state%cloud_fraction%value) .OR. &
        .NOT.ALLOCATED(state%cloud_fraction%valid) .OR. &
        .NOT.ALLOCATED(state%cloud_fraction%quality) .OR. &
        .NOT.ALLOCATED(state%cloud_fraction%source) .OR. &
        .NOT.ALLOCATED(state%cloud_type%value) .OR. &
        .NOT.ALLOCATED(state%cloud_type%valid) .OR. &
        .NOT.ALLOCATED(state%cloud_type%quality) .OR. &
        .NOT.ALLOCATED(state%cloud_type%source)) RETURN
    IF (ANY(SHAPE(state%cloud_fraction%value)/=target) .OR. &
        ANY(SHAPE(state%cloud_fraction%valid)/=target) .OR. &
        ANY(SHAPE(state%cloud_fraction%quality)/=target) .OR. &
        ANY(SHAPE(state%cloud_fraction%source)/=target) .OR. &
        ANY(SHAPE(state%cloud_type%value)/=target) .OR. &
        ANY(SHAPE(state%cloud_type%valid)/=target) .OR. &
        ANY(SHAPE(state%cloud_type%quality)/=target) .OR. &
        ANY(SHAPE(state%cloud_type%source)/=target)) RETURN
    IF (TRIM(state%cloud_fraction%unit)/='1' .OR. &
        TRIM(state%cloud_type%code_table)/='cloud_type_v1' .OR. &
        state%cloud_fraction%valid_time/=state%pressure%valid_time .OR. &
        state%cloud_type%valid_time/=state%pressure%valid_time) RETURN
    IF (ANY(state%cloud_fraction%quality<0_int32) .OR. &
        ANY(state%cloud_fraction%source<0_int32) .OR. &
        ANY(state%cloud_type%quality<0_int32) .OR. &
        ANY(state%cloud_type%source<0_int32)) THEN
      reason=REASON_RANGE; RETURN
    END IF
    ALLOCATE(fraction_usable(target(1),target(2),target(3)), &
             type_usable(target(1),target(2),target(3)))
    fraction_usable=cell_is_usable(state%cloud_fraction%valid, &
      state%cloud_fraction%quality,state%cloud_fraction%source)
    type_usable=cell_is_usable(state%cloud_type%valid, &
      state%cloud_type%quality,state%cloud_type%source)
    IF (ANY(state%cloud_fraction%valid .AND. .NOT.fraction_usable) .OR. &
        ANY(state%cloud_type%valid .AND. .NOT.type_usable)) RETURN
    IF (.NOT.ANY(fraction_usable) .AND. .NOT.ANY(type_usable)) THEN
      status=STATUS_OK; reason=REASON_NONE; RETURN
    END IF
    IF (ANY(fraction_usable .AND. &
        (.NOT.ieee_is_finite(state%cloud_fraction%value) .OR. &
         state%cloud_fraction%value<0.0_real32 .OR. &
         state%cloud_fraction%value>1.0_real32)) .OR. &
        ANY(type_usable .AND. (state%cloud_type%value<0_int32 .OR. &
                               state%cloud_type%value>11_int32))) THEN
      reason=REASON_RANGE; RETURN
    END IF
    ! Cloud metadata is optional and cellwise.  A missing mate excludes only
    ! that cell; paired usable cells remain available to the layer detector.
    present=ANY(state%above_ground .AND. fraction_usable .AND. type_usable)
    status=STATUS_OK; reason=REASON_NONE
  END SUBROUTINE validate_optional_cloud_pair

  PURE LOGICAL FUNCTION radar_field_contract_valid(state)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    INTEGER :: target(3),i,j,k
    target=(/state%grid%nx,state%grid%ny,state%grid%nz/)
    radar_field_contract_valid=ALLOCATED(state%radar_reflectivity%value) .AND. &
      ALLOCATED(state%radar_reflectivity%valid) .AND. &
      ALLOCATED(state%radar_reflectivity%quality) .AND. &
      ALLOCATED(state%radar_reflectivity%source)
    IF (.NOT.radar_field_contract_valid) RETURN
    radar_field_contract_valid= &
      ALL(SHAPE(state%radar_reflectivity%value)==target) .AND. &
      ALL(SHAPE(state%radar_reflectivity%valid)==target) .AND. &
      ALL(SHAPE(state%radar_reflectivity%quality)==target) .AND. &
      ALL(SHAPE(state%radar_reflectivity%source)==target) .AND. &
      TRIM(state%radar_reflectivity%unit)=='dBZ' .AND. &
      state%radar_reflectivity%valid_time==state%pressure%valid_time
    IF (.NOT.radar_field_contract_valid) RETURN
    radar_field_contract_valid=ALL(state%radar_reflectivity%quality>=0_int32) .AND. &
      ALL(state%radar_reflectivity%source>=0_int32) .AND. &
      .NOT.ANY(state%radar_reflectivity%valid .AND. &
        .NOT.radar_echo_cell(state%radar_reflectivity%value, &
          state%radar_reflectivity%valid,state%radar_reflectivity%quality, &
          state%radar_reflectivity%source)) .AND. &
      .NOT.ANY(state%radar_reflectivity%valid .AND. .NOT.state%above_ground) .AND. &
      .NOT.ANY(state%radar_reflectivity%valid .AND. &
               .NOT.ieee_is_finite(state%radar_reflectivity%value))
    IF (.NOT.radar_field_contract_valid) RETURN
    DO k=1,state%grid%nz; DO j=1,state%grid%ny; DO i=1,state%grid%nx
      IF (state%above_ground(i,j,k) .AND. .NOT.( &
                radar_echo_cell(state%radar_reflectivity%value(i,j,k), &
                                state%radar_reflectivity%valid(i,j,k), &
                                state%radar_reflectivity%quality(i,j,k), &
                                state%radar_reflectivity%source(i,j,k)) .OR. &
                radar_no_echo_cell(state%radar_reflectivity%value(i,j,k), &
                                   state%radar_reflectivity%valid(i,j,k), &
                                   state%radar_reflectivity%quality(i,j,k), &
                                   state%radar_reflectivity%source(i,j,k)) .OR. &
                radar_missing_cell(state%radar_reflectivity%value(i,j,k), &
                                   state%radar_reflectivity%valid(i,j,k), &
                                   state%radar_reflectivity%quality(i,j,k), &
                                   state%radar_reflectivity%source(i,j,k)))) THEN
        radar_field_contract_valid=.FALSE.
        RETURN
      END IF
      IF (.NOT.state%above_ground(i,j,k) .AND. &
          .NOT.radar_missing_cell(state%radar_reflectivity%value(i,j,k), &
                                  state%radar_reflectivity%valid(i,j,k), &
                                  state%radar_reflectivity%quality(i,j,k), &
                                  state%radar_reflectivity%source(i,j,k))) THEN
        radar_field_contract_valid=.FALSE.
        RETURN
      END IF
    END DO; END DO; END DO
  END FUNCTION radar_field_contract_valid

  PURE LOGICAL FUNCTION precipitation_phase_contract_valid(state)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    INTEGER :: target(3)
    target=(/state%grid%nx,state%grid%ny,state%grid%nz/)
    precipitation_phase_contract_valid= &
      ALLOCATED(state%precipitation_phase%value) .AND. &
      ALLOCATED(state%precipitation_phase%valid) .AND. &
      ALLOCATED(state%precipitation_phase%quality) .AND. &
      ALLOCATED(state%precipitation_phase%source)
    IF (.NOT.precipitation_phase_contract_valid) RETURN
    precipitation_phase_contract_valid= &
      ALL(SHAPE(state%precipitation_phase%value)==target) .AND. &
      ALL(SHAPE(state%precipitation_phase%valid)==target) .AND. &
      ALL(SHAPE(state%precipitation_phase%quality)==target) .AND. &
      ALL(SHAPE(state%precipitation_phase%source)==target) .AND. &
      state%precipitation_phase%valid_time==state%pressure%valid_time .AND. &
      TRIM(state%precipitation_phase%code_table)=='precipitation_phase_v1'
    IF (.NOT.precipitation_phase_contract_valid) RETURN
    precipitation_phase_contract_valid= &
      ALL(state%precipitation_phase%quality>=0_int32) .AND. &
      ALL(state%precipitation_phase%source>=0_int32) .AND. &
      .NOT.ANY(state%precipitation_phase%valid .AND. &
        .NOT.cell_is_usable(state%precipitation_phase%valid, &
          state%precipitation_phase%quality,state%precipitation_phase%source)) .AND. &
      .NOT.ANY(state%precipitation_phase%valid .AND. &
        IAND(state%precipitation_phase%source,PHASE_EVIDENCE_BITS)==0_int32) .AND. &
      .NOT.ANY(state%precipitation_phase%valid .AND. &
        (state%precipitation_phase%value<PHASE_UNKNOWN .OR. &
         state%precipitation_phase%value>PHASE_GRAUPEL))
  END FUNCTION precipitation_phase_contract_valid

  PURE LOGICAL FUNCTION optional_hydrometeor_contract_valid(state)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    INTEGER :: target(3)
    target=(/state%grid%nx,state%grid%ny,state%grid%nz/)
    optional_hydrometeor_contract_valid= &
      optional_hydrometeor_field_valid(state%cloud_water,target,state%pressure%valid_time) .AND. &
      optional_hydrometeor_field_valid(state%cloud_ice,target,state%pressure%valid_time) .AND. &
      optional_hydrometeor_field_valid(state%rain,target,state%pressure%valid_time) .AND. &
      optional_hydrometeor_field_valid(state%snow,target,state%pressure%valid_time) .AND. &
      optional_hydrometeor_field_valid(state%graupel,target,state%pressure%valid_time)
  END FUNCTION optional_hydrometeor_contract_valid

  PURE LOGICAL FUNCTION optional_hydrometeor_field_valid(field,target,valid_time)
    TYPE(field3d), INTENT(IN) :: field
    INTEGER, INTENT(IN) :: target(3)
    INTEGER(int64), INTENT(IN) :: valid_time
    optional_hydrometeor_field_valid=ALLOCATED(field%value) .AND. &
      ALLOCATED(field%valid) .AND. ALLOCATED(field%quality) .AND. &
      ALLOCATED(field%source)
    IF (.NOT.optional_hydrometeor_field_valid) RETURN
    optional_hydrometeor_field_valid=ALL(SHAPE(field%value)==target) .AND. &
      ALL(SHAPE(field%valid)==target) .AND. ALL(SHAPE(field%quality)==target) .AND. &
      ALL(SHAPE(field%source)==target) .AND. field%valid_time==valid_time .AND. &
      TRIM(field%unit)=='kg kg-1 dryair'
    IF (.NOT.optional_hydrometeor_field_valid) RETURN
    optional_hydrometeor_field_valid=ALL(field%quality>=0_int32) .AND. &
      ALL(field%source>=0_int32) .AND. &
      .NOT.ANY(field%valid .AND. &
        .NOT.cell_is_usable(field%valid,field%quality,field%source)) .AND. &
      .NOT.ANY(field%valid .AND. &
        (.NOT.ieee_is_finite(field%value) .OR. field%value<0.0_real32))
  END FUNCTION optional_hydrometeor_field_valid

  PURE LOGICAL FUNCTION velocity_diagnostic_contract_valid(state)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    INTEGER :: target(3)
    target=(/state%grid%nx,state%grid%ny,state%grid%nz/)
    velocity_diagnostic_contract_valid= &
      velocity_diagnostic_field_valid(state%vt_z_mean,target,state%pressure%valid_time) .AND. &
      velocity_diagnostic_field_valid(state%vt_z_sigma,target,state%pressure%valid_time)
  END FUNCTION velocity_diagnostic_contract_valid

  PURE LOGICAL FUNCTION velocity_diagnostic_field_valid(field,target,valid_time)
    TYPE(field3d), INTENT(IN) :: field
    INTEGER, INTENT(IN) :: target(3)
    INTEGER(int64), INTENT(IN) :: valid_time
    velocity_diagnostic_field_valid=ALLOCATED(field%value) .AND. &
      ALLOCATED(field%valid) .AND. ALLOCATED(field%quality) .AND. &
      ALLOCATED(field%source)
    IF (.NOT.velocity_diagnostic_field_valid) RETURN
    velocity_diagnostic_field_valid=ALL(SHAPE(field%value)==target) .AND. &
      ALL(SHAPE(field%valid)==target) .AND. ALL(SHAPE(field%quality)==target) .AND. &
      ALL(SHAPE(field%source)==target) .AND. field%valid_time==valid_time .AND. &
      TRIM(field%unit)=='m s-1'
    IF (.NOT.velocity_diagnostic_field_valid) RETURN
    velocity_diagnostic_field_valid=ALL(field%quality>=0_int32) .AND. &
      ALL(field%source>=0_int32) .AND. &
      .NOT.ANY(field%valid .AND. &
        .NOT.cell_is_usable(field%valid,field%quality,field%source)) .AND. &
      .NOT.ANY(field%valid .AND. &
      (.NOT.ieee_is_finite(field%value) .OR. field%value<0.0_real32 .OR. &
       field%value>100.0_real32))
  END FUNCTION velocity_diagnostic_field_valid

  PURE FUNCTION column_changed_mask(input,candidate,include_thermo) RESULT(changed)
    TYPE(cloud_bal_state_type), INTENT(IN) :: input,candidate
    LOGICAL, INTENT(IN), OPTIONAL :: include_thermo
    LOGICAL :: changed(input%grid%nx,input%grid%ny,input%grid%nz)
    changed=real32_bits(input%vt_z_mean%value)/=real32_bits(candidate%vt_z_mean%value) .OR. &
            real32_bits(input%vt_z_sigma%value)/=real32_bits(candidate%vt_z_sigma%value) .OR. &
            input%vt_z_mean%source/=candidate%vt_z_mean%source .OR. &
            input%vt_z_sigma%source/=candidate%vt_z_sigma%source .OR. &
            (input%vt_z_mean%valid.NEQV.candidate%vt_z_mean%valid) .OR. &
            (input%vt_z_sigma%valid.NEQV.candidate%vt_z_sigma%valid) .OR. &
            input%vt_z_mean%quality/=candidate%vt_z_mean%quality .OR. &
            input%vt_z_sigma%quality/=candidate%vt_z_sigma%quality .OR. &
            real32_bits(input%omega_target%value)/= &
            real32_bits(candidate%omega_target%value) .OR. &
            (input%omega_target%valid.NEQV.candidate%omega_target%valid) .OR. &
            input%omega_target%quality/=candidate%omega_target%quality .OR. &
            input%omega_target%source/=candidate%omega_target%source .OR. &
            real32_bits(input%rain%value)/=real32_bits(candidate%rain%value) .OR. &
            (input%rain%valid.NEQV.candidate%rain%valid) .OR. &
            input%rain%quality/=candidate%rain%quality .OR. &
            input%rain%source/=candidate%rain%source .OR. &
            real32_bits(input%snow%value)/=real32_bits(candidate%snow%value) .OR. &
            (input%snow%valid.NEQV.candidate%snow%valid) .OR. &
            input%snow%quality/=candidate%snow%quality .OR. &
            input%snow%source/=candidate%snow%source .OR. &
            real32_bits(input%graupel%value)/=real32_bits(candidate%graupel%value) .OR. &
            (input%graupel%valid.NEQV.candidate%graupel%valid) .OR. &
            input%graupel%quality/=candidate%graupel%quality .OR. &
            input%graupel%source/=candidate%graupel%source .OR. &
            input%precipitation_phase%value/=candidate%precipitation_phase%value .OR. &
            (input%precipitation_phase%valid.NEQV. &
             candidate%precipitation_phase%valid) .OR. &
            input%precipitation_phase%quality/=candidate%precipitation_phase%quality .OR. &
            input%precipitation_phase%source/=candidate%precipitation_phase%source .OR. &
            input%cloud_fraction%quality/=candidate%cloud_fraction%quality .OR. &
            input%cloud_type%quality/=candidate%cloud_type%quality .OR. &
            input%obs_support/=candidate%obs_support .OR. &
            input%hydro_support/=candidate%hydro_support
    IF (PRESENT(include_thermo)) THEN
      IF (.NOT.include_thermo) RETURN
    END IF
    changed=changed .OR. &
      real32_bits(input%temperature%value)/=real32_bits(candidate%temperature%value) .OR. &
      input%temperature%source/=candidate%temperature%source .OR. &
      real32_bits(input%vapor%value)/=real32_bits(candidate%vapor%value) .OR. &
      input%vapor%source/=candidate%vapor%source .OR. &
      real32_bits(input%cloud_water%value)/=real32_bits(candidate%cloud_water%value) .OR. &
      input%cloud_water%source/=candidate%cloud_water%source .OR. &
      real32_bits(input%cloud_ice%value)/=real32_bits(candidate%cloud_ice%value) .OR. &
      input%cloud_ice%source/=candidate%cloud_ice%source
  END FUNCTION column_changed_mask

  PURE ELEMENTAL INTEGER(int32) FUNCTION real32_bits(value)
    REAL(real32), INTENT(IN) :: value
    real32_bits=TRANSFER(value,real32_bits)
  END FUNCTION real32_bits

  PURE LOGICAL FUNCTION transport_shapes_valid(grid,pressure,temperature,vapor,u,v,w, &
    w_valid,domain,observed,phase,zlinear,rain,snow,graupel)
    TYPE(grid_spec), INTENT(IN) :: grid
    REAL(real32), INTENT(IN) :: pressure(:,:,:),temperature(:,:,:),vapor(:,:,:)
    REAL(real32), INTENT(IN) :: u(:,:,:),v(:,:,:),w(:,:,:)
    LOGICAL, INTENT(IN) :: w_valid(:,:,:),domain(:,:,:),observed(:,:,:)
    INTEGER, INTENT(IN) :: phase(:,:,:)
    REAL(real64), INTENT(IN) :: zlinear(:,:,:),rain(:,:,:),snow(:,:,:),graupel(:,:,:)
    INTEGER :: target(3)
    transport_shapes_valid=.FALSE.
    IF (grid%nx<1 .OR. grid%ny<1 .OR. grid%nz<2) RETURN
    target=(/grid%nx,grid%ny,grid%nz/)
    transport_shapes_valid=ALL(SHAPE(pressure)==target) .AND. &
      ALL(SHAPE(temperature)==target) .AND. ALL(SHAPE(vapor)==target) .AND. &
      ALL(SHAPE(u)==target) .AND. ALL(SHAPE(v)==target) .AND. ALL(SHAPE(w)==target) .AND. &
      ALL(SHAPE(w_valid)==target) .AND. ALL(SHAPE(domain)==target) .AND. &
      ALL(SHAPE(observed)==target) .AND. &
      ALL(SHAPE(phase)==target) .AND. ALL(SHAPE(zlinear)==target) .AND. &
      ALL(SHAPE(rain)==target) .AND. ALL(SHAPE(snow)==target) .AND. &
      ALL(SHAPE(graupel)==target)
  END FUNCTION transport_shapes_valid

  PURE LOGICAL FUNCTION transport_values_valid(grid,pressure,temperature,vapor,u,v,w, &
    domain,phase,zlinear,rain,snow,graupel,cfg)
    TYPE(grid_spec), INTENT(IN) :: grid
    REAL(real32), INTENT(IN) :: pressure(:,:,:),temperature(:,:,:),vapor(:,:,:)
    REAL(real32), INTENT(IN) :: u(:,:,:),v(:,:,:),w(:,:,:)
    LOGICAL, INTENT(IN) :: domain(:,:,:)
    INTEGER, INTENT(IN) :: phase(:,:,:)
    REAL(real64), INTENT(IN) :: zlinear(:,:,:),rain(:,:,:),snow(:,:,:),graupel(:,:,:)
    TYPE(column_physics_config), INTENT(IN) :: cfg
    REAL(real64) :: dx_tolerance,dy_tolerance,maximum_zlinear
    INTEGER :: k

    transport_values_valid=.FALSE.
    IF (grid%nx<1 .OR. grid%ny<1 .OR. grid%nz<2) RETURN
    IF (.NOT.ALLOCATED(grid%dx) .OR. .NOT.ALLOCATED(grid%dy) .OR. &
        .NOT.ALLOCATED(grid%pressure_interface) .OR. &
        .NOT.ALLOCATED(grid%cell_dp) .OR. &
        .NOT.ALLOCATED(grid%level_spacing_dp)) RETURN
    IF (ANY(SHAPE(grid%dx)/=(/grid%nx,grid%ny/)) .OR. &
        ANY(SHAPE(grid%dy)/=(/grid%nx,grid%ny/)) .OR. &
        ANY(SHAPE(grid%pressure_interface)/=(/grid%nx,grid%ny,grid%nz+1/)) .OR. &
        ANY(SHAPE(grid%cell_dp)/=(/grid%nx,grid%ny,grid%nz/)) .OR. &
        ANY(SHAPE(grid%level_spacing_dp)/=(/grid%nx,grid%ny,grid%nz-1/))) RETURN
    IF (ANY(.NOT.ieee_is_finite(grid%dx)) .OR. &
        ANY(.NOT.ieee_is_finite(grid%dy)) .OR. &
        ANY(.NOT.ieee_is_finite(grid%pressure_interface)) .OR. &
        ANY(.NOT.ieee_is_finite(grid%cell_dp)) .OR. &
        ANY(.NOT.ieee_is_finite(grid%level_spacing_dp))) RETURN
    IF (.NOT.ANY(domain)) RETURN
    DO k=1,grid%nz-1
      IF (ANY(domain(:,:,k) .AND. .NOT.domain(:,:,k+1))) RETURN
    END DO
    IF (ANY(domain .AND. grid%cell_dp<=0.0_real64)) RETURN
    IF (ANY(grid%dx<1.0_real64) .OR. ANY(grid%dx>1.0e6_real64) .OR. &
        ANY(grid%dy<1.0_real64) .OR. ANY(grid%dy>1.0e6_real64) .OR. &
        ANY(grid%cell_dp<0.0_real64) .OR. ANY(grid%cell_dp>MAX_PRESSURE_PA) .OR. &
        ANY(grid%level_spacing_dp<=0.0_real64) .OR. &
        ANY(grid%level_spacing_dp>MAX_PRESSURE_PA)) RETURN
    dx_tolerance=64.0_real64*EPSILON(1.0_real64)*ABS(grid%dx(1,1))
    dy_tolerance=64.0_real64*EPSILON(1.0_real64)*ABS(grid%dy(1,1))
    ! The trajectory kernel advances in grid-index coordinates.  Reject a
    ! nonuniform mesh until transport is implemented in physical coordinates.
    IF (ANY(ABS(grid%dx-grid%dx(1,1))>dx_tolerance) .OR. &
        ANY(ABS(grid%dy-grid%dy(1,1))>dy_tolerance)) RETURN
    IF (ANY(.NOT.ieee_is_finite(pressure)) .OR. &
        ANY(.NOT.ieee_is_finite(temperature)) .OR. &
        ANY(.NOT.ieee_is_finite(vapor)) .OR. ANY(.NOT.ieee_is_finite(u)) .OR. &
        ANY(.NOT.ieee_is_finite(v)) .OR. ANY(.NOT.ieee_is_finite(w))) RETURN
    IF (ANY(domain .AND. (REAL(pressure,real64)<MIN_PRESSURE_PA .OR. &
                          REAL(pressure,real64)>MAX_PRESSURE_PA)) .OR. &
        ANY(domain .AND. (temperature<150.0_real32 .OR. &
                          temperature>350.0_real32)) .OR. &
        ANY(domain .AND. (vapor<0.0_real32 .OR. vapor>0.2_real32)) .OR. &
        ANY(domain .AND. (ABS(u)>200.0_real32 .OR. ABS(v)>200.0_real32 .OR. &
                          ABS(w)>200.0_real32))) RETURN
    IF (ANY(pressure(:,:,1:grid%nz-1)<=pressure(:,:,2:grid%nz))) RETURN
    IF (ANY(.NOT.ieee_is_finite(zlinear)) .OR. &
        ANY(.NOT.ieee_is_finite(rain)) .OR. &
        ANY(.NOT.ieee_is_finite(snow)) .OR. &
        ANY(.NOT.ieee_is_finite(graupel))) RETURN
    maximum_zlinear=10.0_real64**(0.1_real64*cfg%maximum_dbz)
    IF (ANY(zlinear<0.0_real64) .OR. &
        ANY(zlinear>maximum_zlinear*(1.0_real64+64.0_real64*EPSILON(1.0_real64))) .OR. &
        ANY(rain<0.0_real64) .OR. ANY(rain>1.0_real64) .OR. &
        ANY(snow<0.0_real64) .OR. ANY(snow>1.0_real64) .OR. &
        ANY(graupel<0.0_real64) .OR. ANY(graupel>1.0_real64)) RETURN
    IF (ANY(.NOT.domain .AND. &
        (rain>0.0_real64 .OR. snow>0.0_real64 .OR. graupel>0.0_real64))) RETURN
    IF (ANY(phase<PHASE_UNKNOWN) .OR. ANY(phase>PHASE_GRAUPEL)) RETURN
    IF (ANY(phase==PHASE_RAIN .AND. &
            (snow>0.0_real64 .OR. graupel>0.0_real64)) .OR. &
        ANY(phase==PHASE_SNOW .AND. &
            (rain>0.0_real64 .OR. graupel>0.0_real64)) .OR. &
        ANY(phase==PHASE_FREEZING_RAIN .AND. &
            rain+snow+graupel>0.0_real64 .AND. &
            (snow>0.0_real64 .OR. rain<=0.0_real64 .OR. &
             graupel<=0.0_real64)) .OR. &
        ANY(phase==PHASE_SLEET .AND. &
            rain+snow+graupel>0.0_real64 .AND. &
            (rain>0.0_real64 .OR. snow<=0.0_real64 .OR. &
             graupel<=0.0_real64)) .OR. &
        ANY(phase==PHASE_GRAUPEL .AND. &
            (rain>0.0_real64 .OR. snow>0.0_real64))) RETURN
    transport_values_valid=.TRUE.
  END FUNCTION transport_values_valid

  PURE LOGICAL FUNCTION column_config_valid(cfg)
    TYPE(column_physics_config), INTENT(IN) :: cfg
    column_config_valid=.FALSE.
    IF (.NOT.ieee_is_finite(cfg%cloud_fraction_threshold) .OR. &
        .NOT.ieee_is_finite(cfg%radar_wavelength_m) .OR. &
        .NOT.ieee_is_finite(cfg%minimum_dbz) .OR. &
        .NOT.ieee_is_finite(cfg%maximum_dbz) .OR. &
        .NOT.ieee_is_finite(cfg%reference_mass_concentration) .OR. &
        .NOT.ieee_is_finite(cfg%minimum_relative_fall_speed) .OR. &
        .NOT.ieee_is_finite(cfg%maximum_horizontal_substep) .OR. &
        .NOT.ieee_is_finite(cfg%precipitation_loading_efficiency) .OR. &
        .NOT.ieee_is_finite(cfg%maximum_downdraft_ms) .OR. &
        .NOT.ieee_is_finite(cfg%maximum_downdraft_innovation_ms) .OR. &
        .NOT.ieee_is_finite(cfg%ledger_relative_tolerance) .OR. &
        .NOT.ieee_is_finite(cfg%ledger_absolute_tolerance)) RETURN
    IF (cfg%cloud_fraction_threshold<0.0_real64 .OR. &
        cfg%cloud_fraction_threshold>1.0_real64 .OR. &
        cfg%radar_wavelength_m<0.08_real64 .OR. &
        cfg%radar_wavelength_m>0.12_real64 .OR. &
        cfg%minimum_dbz< -100.0_real64 .OR. &
        cfg%maximum_dbz<=cfg%minimum_dbz .OR. cfg%maximum_dbz>100.0_real64 .OR. &
        cfg%reference_mass_concentration<=0.0_real64 .OR. &
        cfg%minimum_relative_fall_speed<=0.0_real64 .OR. &
        cfg%maximum_horizontal_substep<=0.0_real64 .OR. &
        cfg%maximum_horizontal_substep>1.0_real64 .OR. &
        cfg%maximum_transport_substeps<=0 .OR. &
        cfg%maximum_transport_substeps>MAX_ALLOWED_TRANSPORT_SUBSTEPS .OR. &
        cfg%precipitation_loading_efficiency<0.0_real64 .OR. &
        cfg%precipitation_loading_efficiency>1.0_real64 .OR. &
        cfg%maximum_downdraft_ms<=0.0_real64 .OR. &
        cfg%maximum_downdraft_innovation_ms<=0.0_real64 .OR. &
        cfg%ledger_relative_tolerance<0.0_real64 .OR. &
        cfg%ledger_relative_tolerance>MAX_LEDGER_TOLERANCE .OR. &
        cfg%ledger_absolute_tolerance<0.0_real64 .OR. &
        cfg%ledger_absolute_tolerance>MAX_LEDGER_TOLERANCE) RETURN
    column_config_valid=.TRUE.
  END FUNCTION column_config_valid

END MODULE cloud_bal_column_physics
