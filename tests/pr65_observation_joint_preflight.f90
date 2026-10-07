PROGRAM pr65_observation_joint_preflight
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32,int64
  USE cloud_bal_state
  USE cloud_bal_column_physics, ONLY: column_physics_config,derive_column_physics, &
    pressure_analysis_budget,hydrostatic_constraint_summary,column_changed_mask, &
    apply_pressure_hydrostatic_increment,evaluate_interior_hydrostatic_residual
  USE cloud_bal_real_netcdf, ONLY: read_real_shadow_state
  IMPLICIT NONE

  TYPE(cloud_bal_state_type) :: background,radar_candidate,radar_phi_candidate
  TYPE(stage_result) :: radar_stage,phi_stage
  TYPE(pressure_analysis_budget) :: radar_budget
  TYPE(hydrostatic_constraint_summary) :: hydro_before,hydro_after
  TYPE(column_physics_config) :: column_config
  TYPE(field3d), ALLOCATABLE :: retained_omega
  REAL(real32), ALLOCATABLE :: longitude(:,:)
  LOGICAL, ALLOCATABLE :: authorized_target(:,:,:)
  LOGICAL, ALLOCATABLE :: hydro_support(:,:,:),hydro_requested(:,:,:)
  LOGICAL, ALLOCATABLE :: hydro_assessable_before(:,:,:),hydro_assessable_after(:,:,:)
  REAL(real64), ALLOCATABLE :: hydro_residual_before(:,:,:),hydro_residual_after(:,:,:)
  INTEGER(int32), ALLOCATABLE :: hydro_reason_before(:,:,:),hydro_reason_after(:,:,:)
  INTEGER, ALLOCATABLE :: geopotential_reference_level(:,:)
  CHARACTER(LEN=1024) :: fua,fsf,lw3,vrz,vrt,static_path,time_text
  INTEGER(int64) :: valid_time
  INTEGER :: status,reason,io_status,nx,ny,nz,layer
  INTEGER(int64) :: radar_cells,cloud_cells,target_cells,sigma_cells,authorized_cells
  INTEGER(int64) :: producer_target_cells,producer_sigma_cells,producer_authorized_cells
  INTEGER(int64) :: radar_changed_cells,rain_changed_cells,snow_changed_cells,graupel_changed_cells

  IF (COMMAND_ARGUMENT_COUNT()/=7) ERROR STOP &
    'usage: pr65-preflight FUA FSF LW3 VRZ VRT STATIC VALID_TIME_EPOCH'
  CALL GET_COMMAND_ARGUMENT(1,fua)
  CALL GET_COMMAND_ARGUMENT(2,fsf)
  CALL GET_COMMAND_ARGUMENT(3,lw3)
  CALL GET_COMMAND_ARGUMENT(4,vrz)
  CALL GET_COMMAND_ARGUMENT(5,vrt)
  CALL GET_COMMAND_ARGUMENT(6,static_path)
  CALL GET_COMMAND_ARGUMENT(7,time_text)
  READ(time_text,*,IOSTAT=io_status) valid_time
  IF (io_status/=0) ERROR STOP 'invalid valid-time epoch'

  CALL read_real_shadow_state(TRIM(fua),TRIM(fsf),TRIM(lw3),TRIM(vrz),TRIM(vrt), &
    TRIM(static_path),valid_time,background,longitude,status,reason,retained_omega=retained_omega)
  IF (status/=STATUS_OK .OR. reason/=REASON_NONE) THEN
    PRINT '(A,I0,A,I0)', 'input_status=',status,' input_reason=',reason
    ERROR STOP 'actual NE57 reader failed'
  END IF
  nx=background%grid%nx; ny=background%grid%ny; nz=background%grid%nz
  radar_cells=COUNT(background%above_ground .AND. background%radar_reflectivity%valid .AND. &
    radar_echo_cell(background%radar_reflectivity%value,background%radar_reflectivity%valid, &
    background%radar_reflectivity%quality,background%radar_reflectivity%source),KIND=int64)
  cloud_cells=COUNT(background%above_ground .AND. &
      cell_is_usable(background%cloud_fraction%valid,background%cloud_fraction%quality, &
        background%cloud_fraction%source) .AND. &
      cell_is_usable(background%cloud_type%valid,background%cloud_type%quality, &
        background%cloud_type%source) .AND. &
      background%cloud_fraction%value>=REAL(column_config%cloud_fraction_threshold,real32) .AND. &
      background%cloud_type%value>0_int32,KIND=int64)
  target_cells=COUNT(background%omega_target%valid .AND. background%above_ground,KIND=int64)
  sigma_cells=COUNT(background%omega_target_sigma%valid .AND. background%above_ground,KIND=int64)
  authorized_target=observational_target_has_authority(background)
  authorized_cells=COUNT(authorized_target,KIND=int64)

  PRINT '(A,I0,A,I0,A,I0)', 'actual_grid=',nx,'x',ny,'x',nz
  PRINT '(A,I0)', 'retained_radar_echo_cells=',radar_cells
  PRINT '(A,I0)', 'valid_cloud_fraction_cells=',COUNT(background%cloud_fraction%valid,KIND=int64)
  PRINT '(A,I0)', 'valid_cloud_type_cells=',COUNT(background%cloud_type%valid,KIND=int64)
  PRINT '(A,I0)', 'quality_usable_cloud_pairs_above_threshold=',cloud_cells
  PRINT '(A,I0)', 'input_omega_target_cells=',target_cells
  PRINT '(A,I0)', 'input_omega_target_sigma_cells=',sigma_cells
  PRINT '(A,I0)', 'observationally_authorized_target_sigma_overlap_cells=',authorized_cells
  PRINT '(A,L1,A,I0)', 'radar_los_present=',background%radar_los%is_present, &
    ' radar_count=',background%radar_los%nradar
  IF (ALLOCATED(background%radar_los%usage)) THEN
    PRINT '(A,I0)', 'radar_los_assimilated_samples=',COUNT( &
      background%radar_los%usage==LOS_ASSIMILATED,KIND=int64)
    PRINT '(A,I0)', 'radar_los_held_out_samples=',COUNT( &
      background%radar_los%usage==LOS_HELD_OUT,KIND=int64)
  ELSE
    PRINT '(A)', 'radar_los_usage_samples=UNAVAILABLE'
  END IF

  ! This is an independent observation-producer stage on the immutable input.
  ! It intentionally excludes thermodynamic phase adjustment and balance.
  CALL derive_column_physics(background,radar_candidate,radar_stage,column_config, &
    analysis_budget=radar_budget)
  PRINT '(A,I0,A,I0)', 'retained_observation_stage_status=',radar_stage%status, &
    ' reason=',radar_stage%reason_code
  IF (radar_stage%status/=STATUS_OK) THEN
    PRINT '(A)', 'preflight_status=BLOCKED'
    PRINT '(A)', 'blocked_stage=existing full-observation column producer rejected the actual input'
    PRINT '(A)', 'physical_contract_status=NOT_RUN'
    PRINT '(A)', 'wind_authority=NOT_ESTABLISHED: observational omega-target path has no '// &
      'source-matched target/sigma cells; no alternative model-target/background-prior '// &
      'authority was declared by this preflight'
    PRINT '(A)', 'analysis_admission=BLOCKED: the producer failed before a radar analysis candidate was produced; '// &
      'this preflight has no independently admitted per-cell source_increment declaration'
    PRINT '(A)', 'moment_policy=BLOCKED: no authorized common-air QC/NC moment source policy is present in this interface'
    STOP
  END IF

  radar_changed_cells=COUNT(column_changed_mask(background,radar_candidate),KIND=int64)
  rain_changed_cells=COUNT(radar_candidate%rain%value/=background%rain%value,KIND=int64)
  snow_changed_cells=COUNT(radar_candidate%snow%value/=background%snow%value,KIND=int64)
  graupel_changed_cells=COUNT(radar_candidate%graupel%value/=background%graupel%value,KIND=int64)
  PRINT '(A,I0)', 'radar_producer_changed_cells=',radar_changed_cells
  PRINT '(A,I0)', 'radar_producer_rain_changed_cells=',rain_changed_cells
  PRINT '(A,I0)', 'radar_producer_snow_changed_cells=',snow_changed_cells
  PRINT '(A,I0)', 'radar_producer_graupel_changed_cells=',graupel_changed_cells
  producer_target_cells=COUNT(radar_candidate%omega_target%valid .AND. &
    radar_candidate%above_ground,KIND=int64)
  producer_sigma_cells=COUNT(radar_candidate%omega_target_sigma%valid .AND. &
    radar_candidate%above_ground,KIND=int64)
  authorized_target=observational_target_has_authority(radar_candidate)
  producer_authorized_cells=COUNT(authorized_target,KIND=int64)
  PRINT '(A,I0)', 'producer_omega_target_cells=',producer_target_cells
  PRINT '(A,I0)', 'producer_omega_target_sigma_cells=',producer_sigma_cells
  PRINT '(A,I0)', 'producer_authorized_target_sigma_overlap_cells=',producer_authorized_cells
  PRINT '(A,ES24.16E3)', 'radar_stage_species_change_kg_vapor=',radar_budget%species_change_kg(1)
  PRINT '(A,ES24.16E3)', 'radar_stage_species_change_kg_cloud_liquid=',radar_budget%species_change_kg(2)
  PRINT '(A,ES24.16E3)', 'radar_stage_species_change_kg_cloud_ice=',radar_budget%species_change_kg(3)
  PRINT '(A,ES24.16E3)', 'radar_stage_species_change_kg_rain=',radar_budget%species_change_kg(4)
  PRINT '(A,ES24.16E3)', 'radar_stage_species_change_kg_snow=',radar_budget%species_change_kg(5)
  PRINT '(A,ES24.16E3)', 'radar_stage_species_change_kg_graupel=',radar_budget%species_change_kg(6)
  PRINT '(A,ES24.16E3)', 'radar_stage_hydrometeor_mass_increment_kg=', &
    radar_stage%numerical%radar_analysis_increment

  ! Research-only postanalysis: use the existing hydrostatic Phi operator on
  ! one predeclared column after the full-observation producer stage.
  ALLOCATE(hydro_support(nx,ny,nz),geopotential_reference_level(nx,ny), &
    hydro_requested(nx,ny,nz-1),hydro_residual_before(nx,ny,nz-1), &
    hydro_residual_after(nx,ny,nz-1),hydro_assessable_before(nx,ny,nz-1), &
    hydro_assessable_after(nx,ny,nz-1),hydro_reason_before(nx,ny,nz-1), &
    hydro_reason_after(nx,ny,nz-1))
  hydro_support=.FALSE.; geopotential_reference_level=0; hydro_requested=.FALSE.
  IF (nx>=143 .AND. ny>=191 .AND. nz>=2) THEN
    hydro_support(143,191,:)=radar_candidate%above_ground(143,191,:)
    geopotential_reference_level(143,191)=FINDLOC(hydro_support(143,191,:),.TRUE.,DIM=1)
  END IF
  DO layer=1,nz-1
    hydro_requested(:,:,layer)=hydro_support(:,:,layer).AND.hydro_support(:,:,layer+1)
  END DO
  CALL evaluate_interior_hydrostatic_residual(radar_candidate,hydro_requested, &
    hydro_residual_before,hydro_assessable_before,hydro_reason_before,hydro_before)
  PRINT '(A,I0,A,I0)', 'phi_preanalysis_requested_layers=',hydro_before%requested_layers, &
    ' assessable_layers=',hydro_before%assessable_layers
  IF (hydro_before%requested_layers>0_int64 .AND. &
      hydro_before%assessable_layers==hydro_before%requested_layers) THEN
    CALL apply_pressure_hydrostatic_increment(background,radar_candidate,radar_phi_candidate, &
      phi_stage,hydro_support,geopotential_reference_level)
    PRINT '(A,I0,A,I0)', 'phi_postanalysis_status=',phi_stage%status,' reason=',phi_stage%reason_code
    IF (phi_stage%status==STATUS_OK) THEN
      CALL evaluate_interior_hydrostatic_residual(radar_phi_candidate,hydro_requested, &
        hydro_residual_after,hydro_assessable_after,hydro_reason_after,hydro_after)
      PRINT '(A,I0)', 'phi_changed_cells=',COUNT( &
        radar_phi_candidate%geopotential%value/=radar_candidate%geopotential%value,KIND=int64)
      PRINT '(A,ES24.16E3)', 'phi_hydrostatic_rms_before_m2_s2=', &
        hydro_before%residual_rms_m2_s2
      PRINT '(A,ES24.16E3)', 'phi_hydrostatic_rms_after_m2_s2=', &
        hydro_after%residual_rms_m2_s2
    END IF
  ELSE
    PRINT '(A)', 'phi_postanalysis_status=BLOCKED: selected column lacks complete hydrostatic support'
  END IF

  PRINT '(A)', 'preflight_status=BLOCKED'
  PRINT '(A)', 'physical_contract_status=NOT_RUN: source_increment and boundary_increment '// &
    'require an authorized declaration; this preflight does not infer them from an endpoint'
  IF (authorized_cells==0_int64) THEN
    PRINT '(A)', 'wind_authority=NOT_ESTABLISHED: observational omega-target path has no '// &
      'source-matched target/sigma cells; no alternative model-target/background-prior '// &
      'authority was declared by this preflight'
  ELSE
    PRINT '(A,I0,A)', 'wind_authority=PARTIAL: ',authorized_cells, &
      ' cells have target/sigma authority; wind/background changes still require an '// &
      'explicitly admitted region and covariance'
  END IF
  PRINT '(A)', 'analysis_admission=BLOCKED: independent per-cell radar analysis values, '// &
    'error bounds, and provenance were not admitted. physical_joint_candidate_contract%source_increment '// &
    'is the existing external analysis A term; aggregate pressure_analysis_budget totals do not '// &
    'authorize its per-cell values'
  PRINT '(A)', 'moment_policy=BLOCKED: no admitted common-air QC/NC mass and number state with '// &
    'matched donor-face, boundary, limiter, and RK carrier/time terms is present'
  PRINT '(A)', 'next_required_inputs=independently admitted per-cell radar analysis values, '// &
    'error bounds, and provenance for source_increment; source/boundary authority; '// &
    'common-air QC/NC mass and number policy; if wind corrections are sought, a declared '// &
    'authorized wind/background uncertainty path (observational target/sigma or model-target authority)'
  PRINT '(A)', 'candidate_approval=FAIL_OPEN: full-observation column and optional Phi research baseline only; '// &
    'phase, wind fit, joint mass/energy contract, and physical authority were not asserted'
END PROGRAM pr65_observation_joint_preflight
