PROGRAM test_pr64_actual_phase_candidate
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32,int64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  USE cloud_bal_state
  USE cloud_bal_column_physics, ONLY: SATURATION_LIQUID,evaluate_interior_hydrostatic_residual, &
    hydrostatic_constraint_summary
  USE cloud_bal_pipeline
  USE cloud_bal_balance_operator, ONLY: balance_operator_type,build_balance_operator, &
    state_continuity_residual
  USE cloud_bal_real_netcdf, ONLY: read_real_shadow_state,write_shadow_diagnostics, &
    pipeline_result_replays
  USE cloud_bal_pressure_analysis, ONLY: run_pressure_analysis_shadow
  IMPLICIT NONE

  TYPE(cloud_bal_state_type) :: background,analysis_input,candidate,operational
  TYPE(cloud_bal_state_type) :: baseline_candidate,baseline_operational
  TYPE(cloud_bal_pipeline_config) :: config,baseline_config
  TYPE(cloud_bal_pipeline_result) :: result,baseline_result
  TYPE(physical_joint_candidate_contract) :: contract
  TYPE(hydrostatic_constraint_summary) :: hydro_before_summary,hydro_after_summary
  TYPE(balance_operator_type) :: op
  TYPE(field3d), ALLOCATABLE :: retained_omega
  REAL(real32), ALLOCATABLE :: longitude(:,:)
  LOGICAL, ALLOCATABLE :: thermo_active(:,:,:)
  LOGICAL, ALLOCATABLE :: geopotential_support(:,:,:),hydro_requested(:,:,:)
  INTEGER, ALLOCATABLE :: thermo_surface(:,:,:)
  INTEGER, ALLOCATABLE :: geopotential_reference_level(:,:)
  REAL(real64), ALLOCATABLE :: residual_before(:,:,:),residual_after(:,:,:)
  REAL(real64), ALLOCATABLE :: hydro_residual_before(:,:,:),hydro_residual_after(:,:,:)
  LOGICAL, ALLOCATABLE :: hydro_assessable_before(:,:,:),hydro_assessable_after(:,:,:)
  INTEGER(int32), ALLOCATABLE :: hydro_reason_before(:,:,:),hydro_reason_after(:,:,:)
  CHARACTER(LEN=1024) :: fua,fsf,lw3,vrz,vrt,static_path,shadow_path
  INTEGER(int64) :: valid_time
  INTEGER :: status,reason,nx,ny,nz,i,j,k,c,writer_status,io_status,reference_k
  CHARACTER(LEN=64) :: time_text,candidate_mode_text
  REAL(real64) :: extent,initial_t,trial_t,mass,capacity,energy_roundoff,hydro_tolerance,hydro_delta_max
  REAL(real64) :: initial_species(6),trial_species(6),species_ulp(6),cp(6),latent,delta_cp
  REAL(real32) :: stored_t,stored_vapor,stored_cloud
  LOGICAL :: include_geopotential
  INTEGER :: cell(3)

  IF (COMMAND_ARGUMENT_COUNT()/=8 .AND. COMMAND_ARGUMENT_COUNT()/=9) ERROR STOP &
    'usage: actual-phase FUA FSF LW3 VRZ VRT STATIC VALID_TIME_EPOCH SHADOW_OUTPUT [phase_only|phase_phi]'
  CALL GET_COMMAND_ARGUMENT(1,fua)
  CALL GET_COMMAND_ARGUMENT(2,fsf)
  CALL GET_COMMAND_ARGUMENT(3,lw3)
  CALL GET_COMMAND_ARGUMENT(4,vrz)
  CALL GET_COMMAND_ARGUMENT(5,vrt)
  CALL GET_COMMAND_ARGUMENT(6,static_path)
  CALL GET_COMMAND_ARGUMENT(7,time_text)
  CALL GET_COMMAND_ARGUMENT(8,shadow_path)
  include_geopotential=.FALSE.
  IF (COMMAND_ARGUMENT_COUNT()==9) THEN
    CALL GET_COMMAND_ARGUMENT(9,candidate_mode_text)
    SELECT CASE(TRIM(candidate_mode_text))
    CASE('phase_only'); include_geopotential=.FALSE.
    CASE('phase_phi'); include_geopotential=.TRUE.
    CASE DEFAULT; ERROR STOP 'candidate mode must be phase_only or phase_phi'
    END SELECT
  END IF
  READ(time_text,*,IOSTAT=io_status) valid_time
  IF (io_status/=0) ERROR STOP 'invalid valid-time epoch'
  CALL read_real_shadow_state(TRIM(fua),TRIM(fsf),TRIM(lw3),TRIM(vrz),TRIM(vrt), &
    TRIM(static_path),valid_time,background,longitude,status,reason,retained_omega=retained_omega)
  IF (status/=STATUS_OK .OR. reason/=REASON_NONE) ERROR STOP 'actual NE57 reader failed'
  CALL validate_canonical_state(background,.FALSE.,.TRUE.,status,reason,.TRUE.)
  IF (status/=STATUS_OK .OR. reason/=REASON_NONE) ERROR STOP 'actual background is not canonical'
  CALL run_pressure_analysis_shadow(background,baseline_candidate,baseline_operational, &
    baseline_result,baseline_config,'OFF',status)
  IF (status/=STATUS_OK .OR. baseline_result%status/=STATUS_OK) &
    ERROR STOP 'actual OFF pressure-analysis path failed'

  ! Explicit scoped experiment: withhold radar and categorical cloud
  ! observations to prevent unrelated observation operators from mutating the
  ! thermodynamic candidate. The physical background arrays remain the prior.
  analysis_input=background
  analysis_input%radar_reflectivity%valid=.FALSE.
  analysis_input%radar_reflectivity%value=0.0_real32
  analysis_input%radar_reflectivity%quality=QUALITY_RAW_MISSING
  analysis_input%radar_reflectivity%source=0_int32
  analysis_input%radar_los=radar_los_observation_set()
  analysis_input%cloud_type%valid=.FALSE.
  analysis_input%cloud_type%quality=QUALITY_RAW_MISSING
  analysis_input%cloud_type%source=0_int32

  nx=background%grid%nx; ny=background%grid%ny; nz=background%grid%nz
  IF (nx/=235 .OR. ny/=283 .OR. nz/=22) ERROR STOP 'unexpected NE57 production dimensions'
  ! Frozen sample: max source liquid water among source levels warmer than 273.15 K.
  ! Source level 14 maps to bottom-to-top canonical level 9.
  cell=[143,191,9]
  i=cell(1); j=cell(2); k=cell(3)
  IF (.NOT.background%above_ground(i,j,k)) ERROR STOP 'predeclared NE57 sample is below ground'
  IF (.NOT.background%temperature%valid(i,j,k) .OR. &
      .NOT.background%vapor%valid(i,j,k) .OR. .NOT.background%cloud_water%valid(i,j,k)) &
    ERROR STOP 'predeclared NE57 sample lacks required thermodynamics'

  initial_t=REAL(background%temperature%value(i,j,k),real64)
  initial_species=[REAL(background%vapor%value(i,j,k),real64), &
    REAL(background%cloud_water%value(i,j,k),real64), &
    REAL(background%cloud_ice%value(i,j,k),real64),REAL(background%rain%value(i,j,k),real64), &
    REAL(background%snow%value(i,j,k),real64),REAL(background%graupel%value(i,j,k),real64)]
  extent=independent_liquid_phase_extent(REAL(background%pressure%value(i,j,k),real64), &
    initial_t,initial_species,1.0_real64)
  IF (.NOT.ieee_is_finite(extent) .OR. extent>=0.0_real64) &
    ERROR STOP 'predeclared liquid saturation sample has no condensation extent'

  trial_t=initial_t; trial_species=initial_species
  cp=[1846.4_real64,4190.0_real64,2106.0_real64,4190.0_real64,2106.0_real64,2106.0_real64]
  delta_cp=cp(1)-cp(2)
  latent=2.5e6_real64+delta_cp*(initial_t-273.15_real64)
  capacity=1004.5_real64+SUM(cp*initial_species)
  trial_t=initial_t-extent*latent/(capacity+extent*delta_cp)
  trial_species(1)=initial_species(1)+extent
  trial_species(2)=initial_species(2)-extent
  stored_t=REAL(trial_t,real32)
  stored_vapor=REAL(trial_species(1),real32)
  stored_cloud=REAL(trial_species(2),real32)

  ALLOCATE(contract%coverage(nx,ny,nz),contract%source_increment(8,nx,ny,nz), &
    contract%boundary_increment(8,nx,ny,nz),contract%phase_increment(8,nx,ny,nz), &
    contract%physical_tolerance(8,nx,ny,nz),thermo_active(nx,ny,nz),thermo_surface(nx,ny,nz), &
    geopotential_support(nx,ny,nz),geopotential_reference_level(nx,ny), &
    hydro_requested(nx,ny,nz-1),hydro_residual_before(nx,ny,nz-1), &
    hydro_residual_after(nx,ny,nz-1),hydro_assessable_before(nx,ny,nz-1), &
    hydro_assessable_after(nx,ny,nz-1),hydro_reason_before(nx,ny,nz-1), &
    hydro_reason_after(nx,ny,nz-1))
  contract%contract_identity='NE57-20260816T120000Z-cell143-191-9-liquid-rh1-v1'
  contract%adjustable_variables=IOR(PHYSICAL_ADJUST_TEMPERATURE, &
    IOR(PHYSICAL_ADJUST_VAPOR,PHYSICAL_ADJUST_CLOUD_WATER))
  IF (include_geopotential) THEN
    contract%contract_identity='NE57-20260816T120000Z-cell143-191-9-liquid-rh1-phi-lowest-center-v1'
    contract%adjustable_variables=IOR(contract%adjustable_variables,PHYSICAL_ADJUST_GEOPOTENTIAL)
  END IF
  contract%coverage=analysis_input%above_ground
  contract%source_increment=0.0_real64
  contract%boundary_increment=0.0_real64
  contract%phase_increment=0.0_real64
  contract%physical_tolerance=0.0_real64
  mass=analysis_input%grid%dry_air_mass_measure(i,j,k)
  contract%phase_increment(PHYSICAL_COMPONENT_VAPOR,i,j,k)=mass*extent
  contract%phase_increment(PHYSICAL_COMPONENT_CLOUD_WATER,i,j,k)=-mass*extent

  species_ulp(1)=REAL(SPACING(analysis_input%vapor%value(i,j,k)),real64)+REAL(SPACING(stored_vapor),real64)
  species_ulp(2)=REAL(SPACING(analysis_input%cloud_water%value(i,j,k)),real64)+REAL(SPACING(stored_cloud),real64)
  DO c=3,6
    SELECT CASE(c)
    CASE(3); species_ulp(c)=2.0_real64*REAL(SPACING(analysis_input%cloud_ice%value(i,j,k)),real64)
    CASE(4); species_ulp(c)=2.0_real64*REAL(SPACING(analysis_input%rain%value(i,j,k)),real64)
    CASE(5); species_ulp(c)=2.0_real64*REAL(SPACING(analysis_input%snow%value(i,j,k)),real64)
    CASE(6); species_ulp(c)=2.0_real64*REAL(SPACING(analysis_input%graupel%value(i,j,k)),real64)
    END SELECT
  END DO
  contract%physical_tolerance(PHYSICAL_COMPONENT_DRY_MASS_METRIC,i,j,k)= &
    2.0_real64*analysis_input%grid%pressure_mass_measure(i,j,k)*SUM(species_ulp)
  DO c=1,6
    contract%physical_tolerance(c+1,i,j,k)=2.0_real64*mass*species_ulp(c)
  END DO
  energy_roundoff=mass*((1004.5_real64+SUM(cp*trial_species))*ABS(REAL(SPACING(stored_t),real64))+ &
    SUM(ABS([2.50e6_real64,0.0_real64,-3.50e5_real64,0.0_real64,-3.50e5_real64,-3.50e5_real64]+ &
      cp*(initial_t-273.15_real64))*species_ulp)+ &
    SUM(cp*species_ulp)*ABS(REAL(SPACING(stored_t),real64)))
  contract%physical_tolerance(PHYSICAL_COMPONENT_ENTHALPY,i,j,k)=4.0_real64*energy_roundoff

  thermo_active=.FALSE.; thermo_active(i,j,k)=.TRUE.
  thermo_surface=SATURATION_LIQUID
  geopotential_support=.FALSE.; geopotential_reference_level=0; hydro_requested=.FALSE.
  IF (include_geopotential) THEN
    reference_k=FINDLOC(background%above_ground(i,j,:),.TRUE.,DIM=1)
    IF (reference_k<1 .OR. reference_k>=k) ERROR STOP 'no lower supported background Phi reference center'
    geopotential_support(i,j,:)=background%above_ground(i,j,:)
    geopotential_reference_level(i,j)=reference_k
    DO c=1,nz-1
      hydro_requested(i,j,c)=geopotential_support(i,j,c).AND.geopotential_support(i,j,c+1)
    END DO
    CALL evaluate_interior_hydrostatic_residual(analysis_input,hydro_requested, &
      hydro_residual_before,hydro_assessable_before,hydro_reason_before,hydro_before_summary)
    IF (hydro_before_summary%requested_layers<1_int64 .OR. &
        hydro_before_summary%assessable_layers/=hydro_before_summary%requested_layers) &
      ERROR STOP 'predeclared Phi column lacks complete hydrostatic support'
    hydro_tolerance=4.0_real64*MAXVAL(REAL(SPACING(analysis_input%geopotential%value(i,j,:)),real64), &
      MASK=geopotential_support(i,j,:))
  END IF
  config%requested_mode=MODE_SHADOW
  config%horizontal_support_radius_m=10000.0_real64
  config%pressure_support_radius_pa=20000.0_real64
  config%maximum_outer_iterations=1
  IF (include_geopotential) THEN
    CALL run_cloud_bal_pipeline(analysis_input,candidate,operational,result,config, &
      thermo_active=thermo_active,thermo_surface=thermo_surface,target_rh=1.0_real64, &
      geopotential_support=geopotential_support, &
      geopotential_reference_level=geopotential_reference_level,physical_contract=contract)
  ELSE
    CALL run_cloud_bal_pipeline(analysis_input,candidate,operational,result,config, &
      thermo_active=thermo_active,thermo_surface=thermo_surface,target_rh=1.0_real64, &
      physical_contract=contract)
  END IF
  IF (result%status/=STATUS_OK .OR. &
      result%candidate_evaluation%physical_feasibility_status/=PHYSICAL_FEASIBILITY_PASS) THEN
    PRINT '(A,I0,A,I0)', 'pipeline_status=',result%status,' reason=',result%reason_code
    PRINT '(A,I0,A,I0)', 'phase_status=',result%column%status,' phase_reason=',result%column%reason_code
    PRINT '(A,I0,A,I0)', 'feasibility_status=',result%candidate_evaluation%physical_feasibility_status, &
      ' feasibility_reason=',result%candidate_evaluation%physical_feasibility_reason
    PRINT '(A,3(I0,1X),A,I0)', 'failed_cell=',result%candidate_evaluation%physical_feasibility_failed_cell, &
      ' failed_component=',result%candidate_evaluation%physical_feasibility_failed_component
    PRINT '(A,ES24.16E3)', 'declared_extent=',extent
    PRINT '(A,ES24.16E3)', 'candidate_temperature=',REAL(candidate%temperature%value(i,j,k),real64)
    PRINT '(A,ES24.16E3)', 'candidate_vapor=',REAL(candidate%vapor%value(i,j,k),real64)
    PRINT '(A,ES24.16E3)', 'candidate_cloud_water=',REAL(candidate%cloud_water%value(i,j,k),real64)
    PRINT '(A,I0)', 'withheld_radar_cells=',COUNT(background%radar_reflectivity%valid)
    PRINT '(A,I0)', 'withheld_cloud_type_cells=',COUNT(background%cloud_type%valid)
    ERROR STOP 'actual NE57 candidate failed scoped phase feasibility'
  END IF
  IF (.NOT.canonical_states_equal(analysis_input,operational)) &
    ERROR STOP 'actual NE57 candidate changed operational state'
  IF (candidate%temperature%value(i,j,k)/=stored_t .OR. &
      candidate%vapor%value(i,j,k)/=stored_vapor .OR. &
      candidate%cloud_water%value(i,j,k)/=stored_cloud) &
      ERROR STOP 'pipeline endpoint differs from predeclared saturation solution'
  IF (include_geopotential) THEN
    CALL evaluate_interior_hydrostatic_residual(candidate,hydro_requested, &
      hydro_residual_after,hydro_assessable_after,hydro_reason_after,hydro_after_summary)
    IF (hydro_after_summary%assessable_layers/=hydro_before_summary%assessable_layers .OR. &
        ANY(hydro_requested .AND. .NOT.hydro_assessable_after)) &
      ERROR STOP 'candidate lost common hydrostatic support'
    IF (MAXVAL(ABS(hydro_residual_after-hydro_residual_before),MASK=hydro_requested)>hydro_tolerance .OR. &
        hydro_after_summary%residual_rms_m2_s2>hydro_before_summary%residual_rms_m2_s2+hydro_tolerance) &
      ERROR STOP 'candidate hydrostatic residual changed beyond predeclared Phi storage bound'
    hydro_delta_max=MAXVAL(ABS(hydro_residual_after-hydro_residual_before),MASK=hydro_requested)
  END IF
  IF (ANY(result%physical_contract%source_increment/=0.0_real64) .OR. &
      ANY(result%physical_contract%boundary_increment/=0.0_real64)) &
    ERROR STOP 'external source or boundary term was introduced'
  IF (.NOT.pipeline_result_replays(analysis_input,candidate,result,config)) &
    ERROR STOP 'actual NE57 candidate did not replay through the canonical pipeline'

  CALL build_balance_operator(analysis_input,config%balance,op,status,reason)
  IF (status/=STATUS_OK) ERROR STOP 'actual NE57 diagnostic operator failed'
  ALLOCATE(residual_before(nx,ny,nz),residual_after(nx,ny,nz))
  CALL state_continuity_residual(op,analysis_input,residual_before,status)
  IF (status/=STATUS_OK) ERROR STOP 'actual background continuity diagnostic failed'
  CALL state_continuity_residual(op,candidate,residual_after,status)
  IF (status/=STATUS_OK) ERROR STOP 'actual candidate continuity diagnostic failed'
  IF (include_geopotential) THEN
    CALL write_shadow_diagnostics(TRIM(shadow_path),analysis_input,candidate,longitude,result,config, &
      residual_before,residual_after,writer_status,operational,pressure_analysis_candidate=.TRUE.)
  ELSE
    CALL write_shadow_diagnostics(TRIM(shadow_path),analysis_input,candidate,longitude,result,config, &
      residual_before,residual_after,writer_status,operational)
  END IF
  IF (writer_status/=STATUS_OK) ERROR STOP 'actual NE57 SHADOW writer rejected candidate'

  PRINT '(A,I0,A,I0,A,I0)', 'actual_grid=',nx,'x',ny,'x',nz
  PRINT '(A,I0,A,I0,A,I0)', 'predeclared_cell=',i,',',j,',',k
  PRINT '(A,ES24.16E3)', 'phase_extent_kgkg=',extent
  PRINT '(A,ES24.16E3)', 'dry_air_mass_kg=',mass
  PRINT '(A,I0)', 'phase_feasibility_cells=',result%candidate_evaluation%physical_feasibility_cells
  PRINT '(A,I0)', 'withheld_radar_cells=',COUNT(background%radar_reflectivity%valid)
  PRINT '(A,I0)', 'withheld_cloud_type_cells=',COUNT(background%cloud_type%valid)
  PRINT '(A,ES24.16E3)', 'continuity_rms_candidate=',result%candidate_evaluation%continuity_rms
  IF (include_geopotential) THEN
    PRINT '(A,I0)', 'lowest_supported_reference_level=',reference_k
    PRINT '(A,I0)', 'hydrostatic_common_layers=',hydro_before_summary%assessable_layers
    PRINT '(A,ES24.16E3)', 'hydrostatic_background_rms=',hydro_before_summary%residual_rms_m2_s2
    PRINT '(A,ES24.16E3)', 'hydrostatic_candidate_rms=',hydro_after_summary%residual_rms_m2_s2
    PRINT '(A,ES24.16E3)', 'hydrostatic_storage_tolerance=',hydro_tolerance
    PRINT '(A,ES24.16E3)', 'hydrostatic_residual_max_change=',hydro_delta_max
    PRINT '(A,I0)', 'geopotential_changed_cells=',COUNT( &
      (candidate%geopotential%value/=analysis_input%geopotential%value).AND.geopotential_support)
    PRINT '(A)', 'candidate_scope=CONDITIONAL_THERMODYNAMIC_PHI_FEASIBILITY'
  ELSE
    PRINT '(A)', 'candidate_scope=CONDITIONAL_THERMODYNAMIC_FEASIBILITY'
  END IF
  PRINT '(A,A)', 'shadow_path=',TRIM(shadow_path)
  PRINT '(A)', 'source_boundary=PREDECLARED_ZERO'
  PRINT '(A)', 'wind_driver=UNAVAILABLE'
  PRINT '(A)', 'downstream_wps_real_handoff=UNAVAILABLE'

CONTAINS

  PURE REAL(real64) FUNCTION independent_liquid_phase_extent(pressure,temperature,species,target_rh)
    REAL(real64), INTENT(IN) :: pressure,temperature,species(6),target_rh
    REAL(real64) :: lo,hi,mid,capacity,delta_cp,latent,trial_t,value,tc,es,qsat
    REAL(real64) :: cp_values(6)
    INTEGER :: iteration
    cp_values=[1846.4_real64,4190.0_real64,2106.0_real64,4190.0_real64,2106.0_real64,2106.0_real64]
    capacity=1004.5_real64+SUM(cp_values*species)
    delta_cp=cp_values(1)-cp_values(2)
    latent=2.5e6_real64+delta_cp*(temperature-273.15_real64)
    lo=-species(1); hi=species(2)
    DO iteration=1,100
      mid=lo+0.5_real64*(hi-lo)
      trial_t=temperature-mid*latent/(capacity+mid*delta_cp)
      tc=trial_t-273.15_real64
      es=611.20_real64*EXP(17.67_real64*tc/(tc+243.5_real64))
      qsat=0.622_real64*es/(pressure-es)
      value=species(1)+mid-target_rh*qsat
      IF (value>0.0_real64) THEN
        hi=mid
      ELSE
        lo=mid
      END IF
    END DO
    independent_liquid_phase_extent=lo+0.5_real64*(hi-lo)
  END FUNCTION independent_liquid_phase_extent

END PROGRAM test_pr64_actual_phase_candidate
