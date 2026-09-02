! One cloud/radar column-physics implementation.
!
! Radar evaporation is intentionally absent.  Reflectivity may add an
! explicitly diagnosed precipitation analysis increment and precipitation
! loading may affect the omega target, but cooling cannot affect the target
! until a paired water/temperature/enthalpy transfer is approved.
MODULE cloud_bal_column_physics
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32,int64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  USE cloud_bal_state
  IMPLICIT NONE
  PRIVATE

  INTEGER, PARAMETER, PUBLIC :: PHASE_UNKNOWN=0,PHASE_RAIN=1,PHASE_SNOW=2
  INTEGER, PARAMETER, PUBLIC :: PHASE_FREEZING_RAIN=3,PHASE_SLEET=4
  INTEGER, PARAMETER, PUBLIC :: PHASE_GRAUPEL=5
  INTEGER, PARAMETER :: REGIME_CLEAR=0,REGIME_STRATIFORM=1
  INTEGER, PARAMETER :: REGIME_PRECIPITATING=2,REGIME_CONVECTIVE=3
  REAL(real64), PARAMETER :: RD_AIR=287.05_real64
  REAL(real64), PARAMETER :: EPSILON_WATER=0.622_real64
  REAL(real64), PARAMETER :: GRAVITY=9.80665_real64
  REAL(real64), PARAMETER :: CP_DRY=1004.7_real64
  REAL(real64), PARAMETER :: LV=2.50e6_real64
  REAL(real64), PARAMETER :: LF=3.34e5_real64
  REAL(real64), PARAMETER :: LS=LV+LF
  REAL(real64), PARAMETER :: MISSING_PHASE_ALL_SNOW_K=268.15_real64
  REAL(real64), PARAMETER :: MISSING_PHASE_ALL_RAIN_K=275.15_real64

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
    REAL(real64) :: microphysical_loss=0.0_real64
    INTEGER :: maximum_required_substeps=0
  END TYPE precipitation_flux_ledger

  PUBLIC :: derive_column_physics
  PUBLIC :: column_changed_mask
  PUBLIC :: detect_cloud_sublayers
  PUBLIC :: terminal_velocity
  PUBLIC :: allocate_precipitation_phase
  PUBLIC :: missing_phase_partition
  PUBLIC :: transport_precipitation_flux
  PUBLIC :: dry_air_density
  PUBLIC :: saturation_adjust_cell
  PUBLIC :: reduced_moist_enthalpy
  PUBLIC :: flux_ledger_closes

CONTAINS

  SUBROUTINE derive_column_physics(state_in,state_out,result,config)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state_in
    TYPE(cloud_bal_state_type), INTENT(OUT) :: state_out
    TYPE(stage_result), INTENT(OUT) :: result
    TYPE(column_physics_config), INTENT(IN), OPTIONAL :: config
    TYPE(column_physics_config) :: cfg
    TYPE(cloud_bal_state_type) :: candidate
    TYPE(stage_result) :: candidate_result
    TYPE(precipitation_flux_ledger) :: ledger
    REAL(real32), ALLOCATABLE :: w_background(:,:,:),w_target(:,:,:)
    LOGICAL, ALLOCATABLE :: w_valid(:,:,:),radar_observed(:,:,:)
    LOGICAL, ALLOCATABLE :: transport_blocked(:,:,:),radar_derived(:,:,:)
    LOGICAL, ALLOCATABLE :: phase_uncertain(:,:,:)
    INTEGER, ALLOCATABLE :: phase(:,:,:)
    REAL(real64), ALLOCATABLE :: rain(:,:,:),snow(:,:,:),graupel(:,:,:)
    REAL(real64), ALLOCATABLE :: zlinear(:,:,:)
    REAL(real64) :: ledger_error,input_water,output_water
    INTEGER :: nx,ny,nz,status,reason
    LOGICAL :: cloud_available,has_cloud,has_radar,has_cloud_contradiction

    IF (PRESENT(config)) cfg=config
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
    IF (.NOT.has_cloud .AND. .NOT.has_radar) THEN
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
             radar_observed(nx,ny,nz),transport_blocked(nx,ny,nz), &
             radar_derived(nx,ny,nz),phase_uncertain(nx,ny,nz), &
             phase(nx,ny,nz),rain(nx,ny,nz), &
             snow(nx,ny,nz),graupel(nx,ny,nz),zlinear(nx,ny,nz))
    CALL omega_to_w(state_in%omega%value,state_in%pressure%value, &
      state_in%temperature%value,state_in%vapor%value, &
      state_in%above_ground .AND. &
      cell_is_usable(state_in%omega%valid,state_in%omega%quality,state_in%omega%source) .AND. &
      cell_is_usable(state_in%pressure%valid,state_in%pressure%quality, &
                     state_in%pressure%source) .AND. &
      cell_is_usable(state_in%temperature%valid,state_in%temperature%quality, &
                     state_in%temperature%source) .AND. &
      cell_is_usable(state_in%vapor%valid,state_in%vapor%quality,state_in%vapor%source), &
      w_background,w_valid,status)
    IF (status/=STATUS_OK) THEN
      CALL reject_candidate(state_in,state_out,result,STATUS_FAILED,REASON_NONFINITE)
      RETURN
    END IF
    w_target=w_background
    IF (has_cloud) THEN
      CALL build_cloud_targets(state_in,cfg,w_valid,w_target,status)
      IF (status/=STATUS_OK) THEN
        CALL reject_candidate(state_in,state_out,result,STATUS_FAILED,REASON_GATE)
        RETURN
      END IF
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
    radar_observed=.FALSE.; radar_derived=.FALSE.; phase_uncertain=.FALSE.
    transport_blocked=.FALSE.; phase=PHASE_UNKNOWN; zlinear=0.0_real64
    IF (has_radar) THEN
      CALL diagnose_radar_cells(state_in,cfg,radar_observed,phase,zlinear, &
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
      transport_blocked=radar_observed
      CALL transport_precipitation_flux(state_in%grid,state_in%pressure%value, &
        state_in%temperature%value,state_in%vapor%value,state_in%u%value, &
        state_in%v%value,w_background,w_valid,state_in%above_ground, &
        transport_blocked,phase,zlinear, &
        rain,snow,graupel,cfg,ledger,status)
      IF (status/=STATUS_OK .OR. .NOT.flux_ledger_closes(ledger,cfg)) THEN
        CALL reject_candidate(state_in,state_out,result,STATUS_FAILED,REASON_GATE)
        result%numerical%transport_required_substeps=ledger%maximum_required_substeps
        result%numerical%flux_input=ledger%input
        result%numerical%flux_deposited=ledger%deposited
        result%numerical%flux_suspended=ledger%suspended
        result%numerical%flux_boundary_exit=ledger%boundary_exit
        result%numerical%flux_terrain_intercept=ledger%terrain_intercept
        result%numerical%flux_observation_blocked=ledger%observation_blocked
        result%numerical%flux_microphysical_loss=ledger%microphysical_loss
        RETURN
      END IF
      CALL add_loading_downdraft(state_in,cfg,radar_observed,rain,snow,graupel, &
                                 w_background,w_target,status)
      IF (status/=STATUS_OK) THEN
        CALL reject_candidate(state_in,state_out,result,STATUS_FAILED,REASON_NONFINITE)
        RETURN
      END IF
    END IF

    radar_derived=radar_observed .OR. rain>0.0_real64 .OR. snow>0.0_real64 .OR. &
                  graupel>0.0_real64
    phase_uncertain=phase_uncertain .OR. (radar_derived .AND. .NOT.radar_observed) .OR. &
      (radar_derived .AND. phase==PHASE_UNKNOWN) .OR. &
      (MERGE(1,0,rain>0.0_real64)+MERGE(1,0,snow>0.0_real64)+ &
       MERGE(1,0,graupel>0.0_real64)>1)

    CALL publish_column_candidate(state_in,candidate,cfg,w_target,w_valid, &
      radar_observed,radar_derived,phase_uncertain,phase,zlinear,rain,snow,graupel,status)
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
    candidate_result%coverage%usable=COUNT(dynamic_target_has_authority( &
      candidate%omega_target%valid,candidate%omega_target%quality, &
      candidate%omega_target%source))
    candidate_result%coverage%excluded=candidate_result%coverage%required- &
                                       candidate_result%coverage%usable
    candidate_result%coverage%usable_fraction=REAL(candidate_result%coverage%usable,real64)/ &
                                              REAL(candidate_result%coverage%required,real64)
    ledger_error=ledger%input-(ledger%deposited+ledger%suspended+ &
      ledger%boundary_exit+ledger%terrain_intercept+ledger%observation_blocked+ &
      ledger%microphysical_loss)
    candidate_result%numerical%ledger_error=ABS(ledger_error)
    candidate_result%numerical%flux_input=ledger%input
    candidate_result%numerical%flux_deposited=ledger%deposited
    candidate_result%numerical%flux_suspended=ledger%suspended
    candidate_result%numerical%flux_boundary_exit=ledger%boundary_exit
    candidate_result%numerical%flux_terrain_intercept=ledger%terrain_intercept
    candidate_result%numerical%flux_observation_blocked=ledger%observation_blocked
    candidate_result%numerical%flux_microphysical_loss=ledger%microphysical_loss
    candidate_result%numerical%transport_required_substeps= &
      ledger%maximum_required_substeps
    input_water=hydrometeor_mass(state_in)
    output_water=hydrometeor_mass(candidate)
    candidate_result%numerical%radar_analysis_increment=output_water-input_water
    CALL commit_candidate(state_in,candidate,candidate_result,state_out,result)
  END SUBROUTINE derive_column_physics

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
    w_valid,domain,observed,phase,zlinear,rain,snow,graupel,cfg,ledger,status)
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
    INTEGER :: i,j,k,phase_code,nphase
    REAL(real64), ALLOCATABLE :: deposited_rate(:,:),deposited_zrate(:,:)
    REAL(real64), ALLOCATABLE :: phase_rate(:,:),phase_zrate(:,:)

    ledger=precipitation_flux_ledger(); status=STATUS_FAILED
    IF (.NOT.column_config_valid(cfg)) RETURN
    IF (.NOT.transport_shapes_valid(grid,pressure,temperature,vapor,u,v,w,w_valid,domain, &
                                    observed,phase,zlinear,rain,snow,graupel)) RETURN
    IF (.NOT.transport_values_valid(grid,pressure,temperature,vapor,u,v,w,domain, &
                                    phase,zlinear,rain,snow,graupel,cfg)) RETURN
    IF (ANY(observed .AND. .NOT.w_valid)) RETURN
    ALLOCATE(deposited_rate(grid%nx,grid%ny),deposited_zrate(grid%nx,grid%ny), &
             phase_rate(grid%nx,grid%ny),phase_zrate(grid%nx,grid%ny))
    DO k=grid%nz,2,-1
      deposited_rate=0.0_real64; deposited_zrate=0.0_real64
      DO phase_code=PHASE_RAIN,PHASE_GRAUPEL
        IF (phase_code==PHASE_FREEZING_RAIN .OR. phase_code==PHASE_SLEET) CYCLE
        SELECT CASE(phase_code)
        CASE(PHASE_RAIN)
          CALL transport_phase_level(grid,pressure,temperature,vapor,u,v,w,w_valid, &
            domain,observed,k,phase_code,zlinear,rain,cfg,ledger,phase_rate,phase_zrate,status)
        CASE(PHASE_SNOW)
          CALL transport_phase_level(grid,pressure,temperature,vapor,u,v,w,w_valid, &
            domain,observed,k,phase_code,zlinear,snow,cfg,ledger,phase_rate,phase_zrate,status)
        CASE(PHASE_GRAUPEL)
          CALL transport_phase_level(grid,pressure,temperature,vapor,u,v,w,w_valid, &
            domain,observed,k,phase_code,zlinear,graupel,cfg,ledger,phase_rate,phase_zrate,status)
        END SELECT
        IF (status/=STATUS_OK) RETURN
        deposited_rate=deposited_rate+phase_rate
        deposited_zrate=deposited_zrate+phase_zrate
      END DO
      DO j=1,grid%ny; DO i=1,grid%nx
        IF (deposited_rate(i,j)>0.0_real64 .AND. .NOT.observed(i,j,k-1)) THEN
          zlinear(i,j,k-1)=deposited_zrate(i,j)/deposited_rate(i,j)
          nphase=MERGE(1,0,rain(i,j,k-1)>0.0_real64)+ &
                 MERGE(1,0,snow(i,j,k-1)>0.0_real64)+ &
                 MERGE(1,0,graupel(i,j,k-1)>0.0_real64)
          IF (nphase/=1) THEN
            phase(i,j,k-1)=PHASE_UNKNOWN
          ELSE IF (rain(i,j,k-1)>0.0_real64) THEN
            phase(i,j,k-1)=PHASE_RAIN
          ELSE IF (snow(i,j,k-1)>0.0_real64) THEN
            phase(i,j,k-1)=PHASE_SNOW
          ELSE
            phase(i,j,k-1)=PHASE_GRAUPEL
          END IF
        END IF
      END DO; END DO
    END DO
    CALL account_bottom_flux(grid,pressure,temperature,vapor,w,w_valid,rain,snow, &
                             graupel,zlinear,cfg,ledger,status)
    IF (status/=STATUS_OK) RETURN
    IF (.NOT.flux_ledger_closes(ledger,cfg)) THEN
      status=STATUS_FAILED; RETURN
    END IF
    IF (.NOT.transport_values_valid(grid,pressure,temperature,vapor,u,v,w,domain, &
                                    phase,zlinear,rain,snow,graupel,cfg)) &
      status=STATUS_FAILED
  END SUBROUTINE transport_precipitation_flux

  SUBROUTINE transport_phase_level(grid,pressure,temperature,vapor,u,v,w,w_valid, &
    domain,observed,k,phase_code,zlinear,q,cfg,ledger,deposited_rate,deposited_zrate,status)
    TYPE(grid_spec), INTENT(IN) :: grid
    REAL(real32), INTENT(IN) :: pressure(:,:,:),temperature(:,:,:),vapor(:,:,:),u(:,:,:)
    REAL(real32), INTENT(IN) :: v(:,:,:),w(:,:,:)
    LOGICAL, INTENT(IN) :: w_valid(:,:,:),domain(:,:,:),observed(:,:,:)
    INTEGER, INTENT(IN) :: k,phase_code
    REAL(real64), INTENT(INOUT) :: zlinear(:,:,:),q(:,:,:)
    TYPE(column_physics_config), INTENT(IN) :: cfg
    TYPE(precipitation_flux_ledger), INTENT(INOUT) :: ledger
    REAL(real64), INTENT(OUT) :: deposited_rate(:,:),deposited_zrate(:,:)
    INTEGER, INTENT(OUT) :: status
    REAL(real64), ALLOCATABLE :: flux(:,:),zflux(:,:),next_flux(:,:),next_zflux(:,:)
    REAL(real64), ALLOCATABLE :: xstep(:,:),ystep(:,:),relative(:,:),target_relative(:,:)
    INTEGER :: i,j,substep,nsub,vt_status
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
      dz=layer_separation(grid,pressure,temperature,vapor,i,j,k)
      IF (dz<=0.0_real64) RETURN
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
    xstep=xstep/REAL(nsub,real64); ystep=ystep/REAL(nsub,real64)
    DO substep=1,nsub
      next_flux=0.0_real64; next_zflux=0.0_real64
      CALL scatter_flux(grid,flux,zflux,xstep,ystep,next_flux,next_zflux, &
                        ledger%boundary_exit,status)
      IF (status/=STATUS_OK) RETURN
      flux=next_flux; zflux=next_zflux
    END DO
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

  SUBROUTINE scatter_flux(grid,flux,zflux,xstep,ystep,out_flux,out_zflux, &
                          boundary_exit,status)
    TYPE(grid_spec), INTENT(IN) :: grid
    REAL(real64), INTENT(IN) :: flux(:,:),zflux(:,:),xstep(:,:),ystep(:,:)
    REAL(real64), INTENT(OUT) :: out_flux(:,:),out_zflux(:,:)
    REAL(real64), INTENT(INOUT) :: boundary_exit
    INTEGER, INTENT(OUT) :: status
    INTEGER :: i,j,ii,jj,di,dj
    REAL(real64) :: xtarget,ytarget,fx,fy,weight,accounted
    out_flux=0.0_real64; out_zflux=0.0_real64; status=STATUS_FAILED
    DO j=1,grid%ny; DO i=1,grid%nx
      IF (flux(i,j)<=0.0_real64) CYCLE
      xtarget=REAL(i,real64)+xstep(i,j); ytarget=REAL(j,real64)+ystep(i,j)
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
        dz=state%grid%dp(i,j,k)/(rho_d*GRAVITY)
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

  SUBROUTINE publish_column_candidate(input,candidate,cfg,w_target,w_valid, &
    observed,radar_derived,phase_uncertain,phase,zlinear,rain,snow,graupel,status)
    TYPE(cloud_bal_state_type), INTENT(IN) :: input
    TYPE(cloud_bal_state_type), INTENT(INOUT) :: candidate
    TYPE(column_physics_config), INTENT(IN) :: cfg
    REAL(real32), INTENT(IN) :: w_target(:,:,:)
    LOGICAL, INTENT(IN) :: w_valid(:,:,:),observed(:,:,:),radar_derived(:,:,:)
    LOGICAL, INTENT(IN) :: phase_uncertain(:,:,:)
    INTEGER, INTENT(IN) :: phase(:,:,:)
    REAL(real64), INTENT(IN) :: zlinear(:,:,:),rain(:,:,:),snow(:,:,:),graupel(:,:,:)
    INTEGER, INTENT(OUT) :: status
    LOGICAL, ALLOCATABLE :: omega_valid(:,:,:),target_derived(:,:,:)
    REAL(real32), ALLOCATABLE :: omega_target(:,:,:)
    INTEGER :: i,j,k,vt_status
    REAL(real64) :: total,vr,vs,vg,mean,variance,dbz

    ALLOCATE(omega_valid(input%grid%nx,input%grid%ny,input%grid%nz), &
             target_derived(input%grid%nx,input%grid%ny,input%grid%nz), &
             omega_target(input%grid%nx,input%grid%ny,input%grid%nz))
    CALL w_to_omega(w_target,input%pressure%value,input%temperature%value, &
      input%vapor%value,w_valid,omega_target,omega_valid,status)
    IF (status/=STATUS_OK) RETURN
    ! Transported descendants diagnose hydrometeors, not new wind evidence.
    ! Dynamic authority stays with a direct, non-bright-band radar echo.
    target_derived=omega_valid .AND. observed .AND. &
      IAND(input%radar_reflectivity%quality,QUALITY_BRIGHT_BAND_OR_MIXED)==0_int32 .AND. &
      .NOT.dynamic_target_has_authority(input%omega_target%valid, &
        input%omega_target%quality,input%omega_target%source) .AND. &
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
    DO k=1,input%grid%nz; DO j=1,input%grid%ny; DO i=1,input%grid%nx
      total=rain(i,j,k)+snow(i,j,k)+graupel(i,j,k)
      IF (total<=0.0_real64) CYCLE
      dbz=10.0_real64*LOG10(MAX(zlinear(i,j,k),10.0_real64**(0.1_real64*cfg%minimum_dbz)))
      vr=terminal_velocity(PHASE_RAIN,REAL(input%pressure%value(i,j,k),real64), &
        REAL(input%temperature%value(i,j,k),real64),dbz,vt_status)
      IF (vt_status/=STATUS_OK) RETURN
      vs=terminal_velocity(PHASE_SNOW,REAL(input%pressure%value(i,j,k),real64), &
        REAL(input%temperature%value(i,j,k),real64),dbz,vt_status)
      IF (vt_status/=STATUS_OK) RETURN
      vg=terminal_velocity(PHASE_GRAUPEL,REAL(input%pressure%value(i,j,k),real64), &
        REAL(input%temperature%value(i,j,k),real64),dbz,vt_status)
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
    IF (ANY(candidate%rain%valid .AND. .NOT.ieee_is_finite(candidate%rain%value)) .OR. &
        ANY(candidate%snow%valid .AND. .NOT.ieee_is_finite(candidate%snow%value)) .OR. &
        ANY(candidate%graupel%valid .AND. &
            .NOT.ieee_is_finite(candidate%graupel%value))) THEN
      status=STATUS_FAILED; RETURN
    END IF
    CALL refresh_dry_air_mass_measure(candidate,status)
    IF (status/=STATUS_OK) RETURN
    status=STATUS_OK
  END SUBROUTINE publish_column_candidate

  LOGICAL FUNCTION pristine_background(state)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    INTEGER(int32), PARAMETER :: GENERATED=IOR(SOURCE_COLUMN_PHYSICS,SOURCE_BALANCE_OPERATOR)
    ! A stage candidate is never a valid background snapshot: provenance alone
    ! cannot recover the background contribution from a generated total.
    pristine_background= &
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
    IF (pressure_pa<=100.0_real64 .OR. temperature_k<=150.0_real64 .OR. &
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

  SUBROUTINE saturation_adjust_cell(pressure,temperature,vapor,cloud_liquid, &
                                    cloud_ice,target_rh,status)
    REAL(real64), INTENT(IN) :: pressure,target_rh
    REAL(real64), INTENT(INOUT) :: temperature,vapor,cloud_liquid,cloud_ice
    INTEGER, INTENT(OUT) :: status
    REAL(real64) :: t_work,v_work,ql_work,qi_work,water_before,enthalpy_before
    REAL(real64) :: water_after,enthalpy_after,tolerance
    INTEGER :: phase_status

    status=STATUS_FAILED
    IF (.NOT.ieee_is_finite(pressure) .OR. pressure<=100.0_real64 .OR. &
        .NOT.ieee_is_finite(temperature) .OR. temperature<150.0_real64 .OR. &
        .NOT.ieee_is_finite(vapor) .OR. .NOT.ieee_is_finite(cloud_liquid) .OR. &
        .NOT.ieee_is_finite(cloud_ice) .OR. vapor<0.0_real64 .OR. &
        cloud_liquid<0.0_real64 .OR. cloud_ice<0.0_real64 .OR. &
        .NOT.ieee_is_finite(target_rh) .OR. target_rh<0.0_real64 .OR. &
        target_rh>1.0_real64) RETURN
    t_work=temperature; v_work=vapor; ql_work=cloud_liquid; qi_work=cloud_ice
    water_before=v_work+ql_work+qi_work
    enthalpy_before=reduced_moist_enthalpy(t_work,v_work,qi_work)
    IF (t_work>=273.15_real64) THEN
      CALL equilibrate_phase_bounded(pressure,t_work,v_work,ql_work, &
                                     target_rh,LV,.FALSE.,phase_status)
      IF (phase_status/=STATUS_OK) RETURN
      IF (v_work<target_rh*saturation_mixing_ratio(t_work,pressure,.FALSE.) .AND. &
          qi_work>0.0_real64) THEN
        CALL equilibrate_phase_bounded(pressure,t_work,v_work,qi_work, &
                                       target_rh,LS,.TRUE.,phase_status)
        IF (phase_status/=STATUS_OK) RETURN
      END IF
    ELSE
      CALL equilibrate_phase_bounded(pressure,t_work,v_work,qi_work, &
                                     target_rh,LS,.TRUE.,phase_status)
      IF (phase_status/=STATUS_OK) RETURN
      IF (v_work<target_rh*saturation_mixing_ratio(t_work,pressure,.TRUE.) .AND. &
          ql_work>0.0_real64) THEN
        CALL equilibrate_phase_bounded(pressure,t_work,v_work,ql_work, &
                                       target_rh,LV,.FALSE.,phase_status)
        IF (phase_status/=STATUS_OK) RETURN
      END IF
    END IF
    water_after=v_work+ql_work+qi_work
    enthalpy_after=reduced_moist_enthalpy(t_work,v_work,qi_work)
    tolerance=64.0_real64*EPSILON(1.0_real64)*MAX(1.0_real64,ABS(water_before))
    IF (.NOT.ieee_is_finite(t_work) .OR. t_work<150.0_real64 .OR. t_work>350.0_real64 .OR. &
        .NOT.ieee_is_finite(v_work) .OR. .NOT.ieee_is_finite(ql_work) .OR. &
        .NOT.ieee_is_finite(qi_work) .OR. v_work<0.0_real64 .OR. ql_work<0.0_real64 .OR. &
        qi_work<0.0_real64 .OR. ABS(water_after-water_before)>tolerance .OR. &
        ABS(enthalpy_after-enthalpy_before)> &
        256.0_real64*EPSILON(1.0_real64)*MAX(1.0_real64,ABS(enthalpy_before))) RETURN
    temperature=t_work; vapor=v_work; cloud_liquid=ql_work; cloud_ice=qi_work
    status=STATUS_OK
  END SUBROUTINE saturation_adjust_cell

  SUBROUTINE equilibrate_phase_bounded(pressure,temperature,vapor,condensate, &
                                       target_rh,latent,over_ice,status)
    REAL(real64), INTENT(IN) :: pressure,target_rh,latent
    REAL(real64), INTENT(INOUT) :: temperature,vapor,condensate
    LOGICAL, INTENT(IN) :: over_ice
    INTEGER, INTENT(OUT) :: status
    REAL(real64) :: lo,hi,mid,flo,fhi,fmid,initial_t,trial_t
    INTEGER :: iteration
    status=STATUS_FAILED; initial_t=temperature
    lo=-vapor; hi=condensate
    IF (MAX(ABS(lo),ABS(hi))>HUGE(1.0_real64)/(latent/CP_DRY)) RETURN
    trial_t=initial_t-latent*lo/CP_DRY
    IF (.NOT.ieee_is_finite(trial_t) .OR. trial_t<100.0_real64 .OR. &
        trial_t>400.0_real64) RETURN
    flo=vapor+lo-target_rh*saturation_mixing_ratio(trial_t,pressure,over_ice)
    trial_t=initial_t-latent*hi/CP_DRY
    IF (.NOT.ieee_is_finite(trial_t) .OR. trial_t<100.0_real64 .OR. &
        trial_t>400.0_real64) RETURN
    fhi=vapor+hi-target_rh*saturation_mixing_ratio(trial_t,pressure,over_ice)
    IF (flo>0.0_real64 .OR. fhi<0.0_real64) THEN
      mid=MERGE(lo,hi,flo>0.0_real64)
    ELSE
      DO iteration=1,80
        mid=0.5_real64*(lo+hi)
        trial_t=initial_t-latent*mid/CP_DRY
        IF (.NOT.ieee_is_finite(trial_t)) RETURN
        fmid=vapor+mid-target_rh*saturation_mixing_ratio(trial_t,pressure,over_ice)
        IF (fmid>0.0_real64) THEN
          hi=mid
        ELSE
          lo=mid
        END IF
        IF (hi-lo<=MAX(1.0e-14_real64, &
          1.0e-12_real64*MAX(vapor,condensate,1.0e-12_real64))) EXIT
      END DO
      mid=0.5_real64*(lo+hi)
    END IF
    trial_t=initial_t-latent*mid/CP_DRY
    IF (.NOT.ieee_is_finite(trial_t) .OR. vapor+mid<0.0_real64 .OR. &
        condensate-mid<0.0_real64) RETURN
    temperature=trial_t; vapor=vapor+mid; condensate=condensate-mid
    status=STATUS_OK
  END SUBROUTINE equilibrate_phase_bounded

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

  PURE REAL(real64) FUNCTION dry_air_density(pressure,temperature,vapor)
    REAL(real64), INTENT(IN) :: pressure,temperature,vapor
    dry_air_density=-1.0_real64
    IF (.NOT.ieee_is_finite(pressure) .OR. pressure<=0.0_real64 .OR. &
        .NOT.ieee_is_finite(temperature) .OR. temperature<=0.0_real64 .OR. &
        .NOT.ieee_is_finite(vapor) .OR. vapor<0.0_real64) RETURN
    dry_air_density=pressure/(RD_AIR*temperature*(1.0_real64+vapor/EPSILON_WATER))
  END FUNCTION dry_air_density

  PURE REAL(real64) FUNCTION reduced_moist_enthalpy(temperature,vapor,cloud_ice)
    REAL(real64), INTENT(IN) :: temperature,vapor,cloud_ice
    reduced_moist_enthalpy=CP_DRY*temperature+LV*vapor-LF*cloud_ice
  END FUNCTION reduced_moist_enthalpy

  PURE LOGICAL FUNCTION flux_ledger_closes(ledger,cfg)
    TYPE(precipitation_flux_ledger), INTENT(IN) :: ledger
    TYPE(column_physics_config), INTENT(IN) :: cfg
    REAL(real64) :: output,error
    output=ledger%deposited+ledger%suspended+ledger%boundary_exit+ &
           ledger%terrain_intercept+ledger%observation_blocked+ &
           ledger%microphysical_loss
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

  PURE REAL(real64) FUNCTION layer_separation(grid,pressure,temperature,vapor,i,j,k)
    TYPE(grid_spec), INTENT(IN) :: grid
    REAL(real32), INTENT(IN) :: pressure(:,:,:),temperature(:,:,:),vapor(:,:,:)
    INTEGER, INTENT(IN) :: i,j,k
    REAL(real64) :: rho
    rho=dry_air_density(REAL(pressure(i,j,k),real64), &
      REAL(temperature(i,j,k),real64),REAL(vapor(i,j,k),real64))
    layer_separation=0.5_real64*(grid%dp(i,j,k)+grid%dp(i,j,k-1))/(rho*GRAVITY)
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
    INTEGER :: target(3)
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
        .NOT.cell_is_usable(state%radar_reflectivity%valid, &
          state%radar_reflectivity%quality,state%radar_reflectivity%source)) .AND. &
      .NOT.ANY(state%radar_reflectivity%valid .AND. &
        IAND(state%radar_reflectivity%source,SOURCE_RADAR_DBZ)==0_int32) .AND. &
      .NOT.ANY(state%radar_reflectivity%valid .AND. .NOT.state%above_ground) .AND. &
      .NOT.ANY(state%radar_reflectivity%valid .AND. &
               .NOT.ieee_is_finite(state%radar_reflectivity%value))
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

  PURE FUNCTION column_changed_mask(input,candidate) RESULT(changed)
    TYPE(cloud_bal_state_type), INTENT(IN) :: input,candidate
    LOGICAL :: changed(input%grid%nx,input%grid%ny,input%grid%nz)
    changed=real32_bits(input%omega_target%value)/= &
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

    transport_values_valid=.FALSE.
    IF (grid%nx<1 .OR. grid%ny<1 .OR. grid%nz<2) RETURN
    IF (.NOT.ALLOCATED(grid%dx) .OR. .NOT.ALLOCATED(grid%dy) .OR. &
        .NOT.ALLOCATED(grid%dp)) RETURN
    IF (ANY(SHAPE(grid%dx)/=(/grid%nx,grid%ny/)) .OR. &
        ANY(SHAPE(grid%dy)/=(/grid%nx,grid%ny/)) .OR. &
        ANY(SHAPE(grid%dp)/=(/grid%nx,grid%ny,grid%nz/))) RETURN
    IF (ANY(.NOT.ieee_is_finite(grid%dx)) .OR. &
        ANY(.NOT.ieee_is_finite(grid%dy)) .OR. &
        ANY(.NOT.ieee_is_finite(grid%dp))) RETURN
    IF (ANY(grid%dx<1.0_real64) .OR. ANY(grid%dx>1.0e6_real64) .OR. &
        ANY(grid%dy<1.0_real64) .OR. ANY(grid%dy>1.0e6_real64) .OR. &
        ANY(grid%dp<=0.0_real64) .OR. ANY(grid%dp>120000.0_real64)) RETURN
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
    IF (ANY(domain .AND. (pressure<100.0_real32 .OR. pressure>120000.0_real32)) .OR. &
        ANY(domain .AND. (temperature<150.0_real32 .OR. &
                          temperature>350.0_real32)) .OR. &
        ANY(domain .AND. (vapor<0.0_real32 .OR. vapor>0.2_real32)) .OR. &
        ANY(domain .AND. (ABS(u)>200.0_real32 .OR. ABS(v)>200.0_real32 .OR. &
                          ABS(w)>200.0_real32))) RETURN
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
        cfg%maximum_dbz<=cfg%minimum_dbz .OR. cfg%maximum_dbz>100.0_real64 .OR. &
        cfg%reference_mass_concentration<=0.0_real64 .OR. &
        cfg%minimum_relative_fall_speed<=0.0_real64 .OR. &
        cfg%maximum_horizontal_substep<=0.0_real64 .OR. &
        cfg%maximum_transport_substeps<=0 .OR. &
        cfg%precipitation_loading_efficiency<0.0_real64 .OR. &
        cfg%precipitation_loading_efficiency>1.0_real64 .OR. &
        cfg%maximum_downdraft_ms<=0.0_real64 .OR. &
        cfg%maximum_downdraft_innovation_ms<=0.0_real64 .OR. &
        cfg%ledger_relative_tolerance<0.0_real64 .OR. &
        cfg%ledger_absolute_tolerance<0.0_real64) RETURN
    column_config_valid=.TRUE.
  END FUNCTION column_config_valid

END MODULE cloud_bal_column_physics
