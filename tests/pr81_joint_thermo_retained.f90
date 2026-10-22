PROGRAM pr81_joint_thermo_retained
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32,int64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite,ieee_value,ieee_quiet_nan
  USE netcdf
  USE cloud_bal_state
  USE cloud_bal_column_physics, ONLY: SATURATION_LIQUID,thermodynamic_density_prior_config
  USE cloud_bal_pipeline, ONLY: cloud_bal_pipeline_config,cloud_bal_pipeline_result, &
    run_cloud_bal_pipeline,MODE_SHADOW
  USE cloud_bal_balance_operator, ONLY: balance_operator_config,balance_operator_type, &
    balance_operator_snapshot,active_balance_cell_count,build_balance_operator, &
    build_diagnostic_balance_operator,snapshot_balance_operator, &
    state_continuity_residual,state_dry_air_mass_flux_divergence
  USE cloud_bal_real_netcdf, ONLY: read_real_shadow_state,write_shadow_diagnostics
  IMPLICIT NONE

  INTEGER(int64), PARAMETER :: VALID_TIME=1786885200_int64
  REAL(real64), PARAMETER :: TARGET_RH=1.0_real64
  TYPE(cloud_bal_state_type) :: background,candidate,operational,observation_check
  TYPE(cloud_bal_pipeline_config) :: config
  TYPE(cloud_bal_pipeline_result) :: result,rejected_result,bad_result
  TYPE(balance_operator_type) :: trial_operator,before_diagnostic_operator,after_diagnostic_operator
  TYPE(balance_operator_snapshot) :: after_diagnostic_snapshot
  REAL(real32), ALLOCATABLE :: longitude(:,:)
  REAL(real64), ALLOCATABLE :: residual_before(:,:,:),residual_after(:,:,:)
  REAL(real64), ALLOCATABLE :: background_flux(:,:,:),candidate_flux(:,:,:),shared_flux_residual(:,:,:)
  INTEGER(int32), ALLOCATABLE :: int3(:,:,:)
  INTEGER, ALLOCATABLE :: thermo_surface(:,:,:),phi_reference(:,:)
  LOGICAL, ALLOCATABLE :: analysis_support(:,:,:),thermo_support(:,:,:)
  LOGICAL, ALLOCATABLE :: phi_support(:,:,:),control(:,:,:),shell(:,:,:),force_support(:,:,:)
  CHARACTER(LEN=2048) :: arg(15),coupled_path,output_path,bad_output_path
  INTEGER :: i,j,k,nx,ny,nz,ncid,status,reason,observed_cells,writer_status,witness_index
  LOGICAL :: bad_output_exists
  REAL(real64) :: rms,max_abs,retrieval_delta,density_delta,phi_delta

  IF (COMMAND_ARGUMENT_COUNT()/=15) ERROR STOP &
    'usage: pr81-joint-thermo FUA FSF LW3 VRZ VRT STATIC LT1 LQ3 LWC LSX LCP LTY EPOCH COUPLED.nc OUTPUT.nc'
  DO i=1,15
    CALL GET_COMMAND_ARGUMENT(i,arg(i))
  END DO
  READ(arg(13),*) status
  IF (status/=VALID_TIME) ERROR STOP 'retained input epoch differs from pinned CP06-A'
  coupled_path=TRIM(arg(14))
  output_path=TRIM(arg(15))
  CALL read_real_shadow_state(TRIM(arg(1)),TRIM(arg(2)),TRIM(arg(3)),TRIM(arg(4)), &
    TRIM(arg(5)),TRIM(arg(6)),VALID_TIME,background,longitude,status,reason, &
    lt1_path=TRIM(arg(7)),lq3_path=TRIM(arg(8)),lwc_path=TRIM(arg(9)), &
    lsx_path=TRIM(arg(10)),lcp_path=TRIM(arg(11)),lty_path=TRIM(arg(12)))
  IF (status/=STATUS_OK) ERROR STOP 'template background reader failed'
  nx=background%grid%nx; ny=background%grid%ny; nz=background%grid%nz
  ALLOCATE(int3(nx,ny,nz),thermo_surface(nx,ny,nz),phi_reference(nx,ny), &
    analysis_support(nx,ny,nz),thermo_support(nx,ny,nz),phi_support(nx,ny,nz), &
    control(nx,ny,nz),shell(nx,ny,nz),force_support(nx,ny,nz), &
    residual_before(nx,ny,nz),residual_after(nx,ny,nz), &
    background_flux(nx,ny,nz),candidate_flux(nx,ny,nz),shared_flux_residual(nx,ny,nz))
  CALL nc_open_checked(coupled_path,ncid)
  CALL assert_dims(ncid,nx,ny,nz)
  CALL read_mask(ncid,'analysis_support',analysis_support,int3)
  CALL read_mask(ncid,'thermo_support',thermo_support,int3)
  CALL read_mask(ncid,'geopotential_support',phi_support,int3)
  CALL read_mask(ncid,'background_control_support',control,int3)
  CALL read_mask(ncid,'background_validation_shell',shell,int3)
  CALL read_mask(ncid,'geostrophic_validation_support',force_support,int3)
  CALL read_i3(ncid,'thermo_surface',thermo_surface)
  CALL read_i2(ncid,'geopotential_reference_level',phi_reference)
  CALL nc_close_checked(ncid)
  IF (COUNT(analysis_support)/=162 .OR. COUNT(thermo_support)/=69 .OR. &
      COUNT(phi_support)/=180 .OR. COUNT(control)/=500 .OR. COUNT(shell)/=980 .OR. &
      COUNT(force_support)/=900) &
    ERROR STOP 'retained observation and control supports changed'
  IF (ANY(thermo_surface/=SATURATION_LIQUID)) ERROR STOP 'retained thermo surface is not liquid'
  IF (ANY(thermo_support .AND. .NOT.analysis_support) .OR. &
      ANY(thermo_support .AND. .NOT.phi_support)) ERROR STOP 'thermo support is outside joint trial support'

  CALL configure_trial(config)
  CALL run_cloud_bal_pipeline(background,candidate,operational,result,config, &
    thermo_active=thermo_support,thermo_surface=thermo_surface,target_rh=TARGET_RH, &
    geopotential_support=phi_support,geopotential_reference_level=phi_reference, &
    analysis_support=analysis_support,background_control_support=control, &
    background_validation_shell=shell,force_support=force_support)
  IF (result%status/=STATUS_OK .OR. .NOT.result%thermo_density_prior_applied) THEN
    WRITE(*,'(A,I0,A,I0,A,I0,A,I0)') 'pipeline_status=',result%status, &
      ',reason=',result%reason_code,',column_status=',result%column%status, &
      ',column_reason=',result%column%reason_code
    WRITE(*,'(A,I0,A,I0,A,I0,A,I0)') 'balance_status=',result%balance%status, &
      ',balance_reason=',result%balance%reason_code,',solver_reason=', &
      result%balance%numerical%solver_reason,',solver_iterations=', &
      result%balance%numerical%solver_iterations
    IF (result%status==STATUS_DEGRADED .AND. result%reason_code==REASON_GATE .AND. &
        result%column%status==STATUS_OK .AND. result%force_prior%status==STATUS_DEGRADED .AND. &
        result%force_prior%reason==REASON_GATE .AND. .NOT.result%thermo_density_prior_applied) THEN
      IF (.NOT.canonical_states_equal(background,candidate) .OR. &
          .NOT.canonical_states_equal(background,operational)) &
        ERROR STOP 'force-gate rejected joint trial did not roll back atomically'
      IF (ALLOCATED(result%pre_density_temperature) .OR. ALLOCATED(result%pre_density_vapor) .OR. &
          ALLOCATED(result%pre_density_condensates) .OR. ALLOCATED(result%pre_density_dry_mass)) &
        ERROR STOP 'force-gate rejection retained prior snapshots'
      IF (result%thermo_analysis_budget%accounted_cells/=0_int64 .OR. &
          ANY(result%thermo_analysis_budget%species_change_kg/=0.0_real64) .OR. &
          result%thermo_budget%enthalpy_error_j/=0.0_real64) &
        ERROR STOP 'force-gate rejection retained thermodynamic ledgers'
      WRITE(*,'(A,I0)') 'force_prior_status=',result%force_prior%status
      WRITE(*,'(A,I0)') 'force_prior_reason=',result%force_prior%reason
      WRITE(*,'(A,ES24.16)') 'force_prior_input_geostrophic_rms=',result%force_prior%input_force_rms
      WRITE(*,'(A,ES24.16)') 'force_prior_candidate_geostrophic_rms=',result%force_prior%candidate_force_rms
      WRITE(*,'(A,ES24.16)') 'force_prior_input_objective=',result%force_prior%input_objective
      WRITE(*,'(A,ES24.16)') 'force_prior_candidate_objective=',result%force_prior%candidate_objective
      WRITE(*,'(A,ES24.16)') 'force_prior_shared_flux_candidate_rms=', &
        result%force_prior%continuity_candidate_rms
      WRITE(*,'(A,ES24.16)') 'force_prior_shared_flux_candidate_max=', &
        result%force_prior%continuity_candidate_max
      WRITE(*,'(A,ES24.16)') 'force_prior_input_stage_background_rms=', &
        result%balance%numerical%continuity_background_rms
      WRITE(*,'(A,ES24.16)') 'force_prior_input_stage_candidate_rms=', &
        result%balance%numerical%continuity_candidate_rms
      WRITE(*,'(A)') 'outcome=REJECTED_AT_FROZEN_FORCE_GATE'
      WRITE(*,'(A)') 'atomic_rollback=T'
      WRITE(*,'(A)') 'science_authority=NONE'
      ERROR STOP 'retained joint trial had no accepted stored-state force candidate'
    END IF
    ERROR STOP 'joint thermo-density/Phi/continuity pipeline failed'
  END IF
  IF (.NOT.result%force_prior_applied .OR. COUNT(result%force_prior_support)/=900) &
    ERROR STOP 'joint trial did not apply its frozen force-prior support'
  IF (result%force_prior%backtracking_steps<0 .OR. result%force_prior%backtracking_steps>20) &
    ERROR STOP 'retained stored-state force backtracking count is outside its frozen bound'
  IF (.NOT.ALLOCATED(result%pre_density_temperature) .OR. &
      .NOT.ALLOCATED(result%pre_density_vapor)) ERROR STOP 'pre-prior thermo receipt is missing'
  IF (.NOT.ALLOCATED(result%pre_density_condensates)) ERROR STOP 'pre-prior condensate witness is missing'
  IF (ANY(SHAPE(result%pre_density_condensates)/=[5,COUNT(analysis_support)])) &
    ERROR STOP 'pre-prior condensate witness shape differs from frozen analysis support'
  IF (.NOT.ALLOCATED(result%pre_density_dry_mass)) ERROR STOP 'pre-prior dry-mass witness is missing'
  IF (SIZE(result%pre_density_dry_mass)/=COUNT(analysis_support) .OR. &
      ANY(.NOT.ieee_is_finite(result%pre_density_dry_mass)) .OR. &
      ANY(result%pre_density_dry_mass<=0.0_real64)) &
    ERROR STOP 'pre-prior dry-mass witness is invalid'
  IF (COUNT(result%thermo_support)/=69 .OR. COUNT(result%analysis_support)/=162 .OR. &
      COUNT(result%geopotential_support)/=180) ERROR STOP 'pipeline changed a frozen support mask'
  IF (COUNT(candidate%obs_support>0_int32)==0) ERROR STOP 'retrieval produced no observation support signal'
  witness_index=0
  DO k=1,nz
    DO j=1,ny
      DO i=1,nx
        IF (.NOT.analysis_support(i,j,k)) CYCLE
        witness_index=witness_index+1
        IF (candidate%cloud_water%value(i,j,k)/=result%pre_density_condensates(1,witness_index) .OR. &
            candidate%cloud_ice%value(i,j,k)/=result%pre_density_condensates(2,witness_index) .OR. &
            candidate%rain%value(i,j,k)/=result%pre_density_condensates(3,witness_index) .OR. &
            candidate%snow%value(i,j,k)/=result%pre_density_condensates(4,witness_index) .OR. &
            candidate%graupel%value(i,j,k)/=result%pre_density_condensates(5,witness_index)) &
          ERROR STOP 'density prior changed a retained condensate on analysis support'
      END DO
    END DO
  END DO
  IF (witness_index/=COUNT(analysis_support)) ERROR STOP 'condensate witness packing count differs'
  IF (ANY(candidate%cloud_fraction%value/=background%cloud_fraction%value) .OR. &
      ANY(candidate%cloud_type%value/=background%cloud_type%value) .OR. &
      ANY(candidate%radar_reflectivity%value/=background%radar_reflectivity%value)) &
    ERROR STOP 'joint prior changed cloud or radar observation values'
  observation_check=candidate
  observation_check%temperature=background%temperature
  observation_check%vapor=background%vapor
  observation_check%geopotential=background%geopotential
  observation_check%cloud_water=background%cloud_water
  observation_check%cloud_ice=background%cloud_ice
  observation_check%grid%dry_air_mass_measure=background%grid%dry_air_mass_measure
  IF (.NOT.canonical_states_equal(background,observation_check,.TRUE.)) &
    ERROR STOP 'trial changed immutable observations or boundary metadata'

  retrieval_delta=MAXVAL(ABS(REAL(result%pre_density_temperature,real64)- &
    REAL(background%temperature%value,real64)),MASK=analysis_support)
  density_delta=MAXVAL(ABS(REAL(candidate%temperature%value,real64)- &
    REAL(result%pre_density_temperature,real64)),MASK=analysis_support)
  IF (retrieval_delta<=0.0_real64 .OR. density_delta<=0.0_real64) &
    ERROR STOP 'joint trial did not retain retrieval and density-prior temperature signals'
  IF (MAXVAL(ABS(REAL(candidate%temperature%value,real64)- &
      REAL(result%pre_density_temperature,real64)),MASK=analysis_support)> &
      config%thermo_density_prior%max_temperature_increment) &
    ERROR STOP 'density-prior temperature increment exceeded its declared cap'
  IF (MAXVAL(ABS(REAL(candidate%vapor%value,real64)- &
      REAL(result%pre_density_vapor,real64)),MASK=analysis_support)> &
      config%thermo_density_prior%max_vapor_increment) &
    ERROR STOP 'density-prior vapor increment exceeded its declared cap'
  phi_delta=MAXVAL(ABS(REAL(candidate%geopotential%value,real64)- &
    REAL(background%geopotential%value,real64)),MASK=phi_support)
  IF (phi_delta<=0.0_real64) ERROR STOP 'joint trial did not apply the authorized hydrostatic Phi correction'
  IF (ANY((candidate%geopotential%value/=background%geopotential%value) .AND. .NOT.phi_support)) &
    ERROR STOP 'joint trial changed Phi outside its fixed support'

  CALL build_balance_operator(candidate,config%balance,trial_operator,status,reason)
  IF (status/=STATUS_OK .OR. result%candidate_evaluation%operator_status/=STATUS_OK) &
    ERROR STOP 'final trial continuity operator was not rebuilt'
  IF (active_balance_cell_count(trial_operator)/=0_int64 .OR. &
      result%candidate_evaluation%balance_support_cells/=0_int64 .OR. &
      result%candidate_evaluation%continuity_assessed) &
    ERROR STOP 'observational continuity operator was incorrectly treated as resolved'
  CALL build_diagnostic_balance_operator(background,before_diagnostic_operator,status,reason)
  IF (status/=STATUS_OK) ERROR STOP 'background diagnostic operator could not be rebuilt'
  CALL state_continuity_residual(before_diagnostic_operator,background,residual_before,status)
  IF (status/=STATUS_OK) ERROR STOP 'background diagnostic continuity residual failed'
  CALL build_diagnostic_balance_operator(candidate,after_diagnostic_operator,status,reason)
  IF (status/=STATUS_OK) ERROR STOP 'candidate diagnostic operator could not be rebuilt'
  CALL snapshot_balance_operator(after_diagnostic_operator,after_diagnostic_snapshot,status)
  IF (status/=STATUS_OK) ERROR STOP 'candidate diagnostic operator snapshot failed'
  CALL state_continuity_residual(after_diagnostic_operator,candidate,residual_after,status)
  IF (status/=STATUS_OK) ERROR STOP 'candidate diagnostic continuity residual failed'
  CALL state_dry_air_mass_flux_divergence(after_diagnostic_operator,background,background_flux,status)
  IF (status/=STATUS_OK) ERROR STOP 'background shared-flux divergence failed'
  CALL state_dry_air_mass_flux_divergence(after_diagnostic_operator,candidate,candidate_flux,status)
  IF (status/=STATUS_OK) ERROR STOP 'candidate diagnostic continuity residual failed'
  WHERE(shell)
    shared_flux_residual=(candidate_flux-background_flux)/after_diagnostic_snapshot%volume
  ELSEWHERE
    shared_flux_residual=0.0_real64
  END WHERE
  CALL masked_norm(shell,shared_flux_residual,rms,max_abs)
  IF (rms/=result%balance%numerical%continuity_candidate_rms .OR. &
      max_abs/=result%balance%numerical%continuity_candidate_max) &
    ERROR STOP 'reconstructed shared-flux prior receipt differs from accepted continuity gate'
  WRITE(*,'(A,ES24.16)') 'shared_flux_continuity_rms=',rms
  WRITE(*,'(A,ES24.16)') 'shared_flux_continuity_max=',max_abs
  CALL write_shadow_diagnostics(TRIM(output_path),background,candidate,longitude,result,config, &
    residual_before,residual_after,writer_status,operational,pressure_analysis_candidate=.TRUE.)
  IF (writer_status/=STATUS_OK) ERROR STOP 'joint candidate writer rejected the receipt'
  bad_output_path=TRIM(output_path)//'.bad-energy.nc'
  INQUIRE(FILE=TRIM(bad_output_path),EXIST=bad_output_exists)
  IF (bad_output_exists) ERROR STOP 'stale invalid-energy output exists before writer rejection test'
  bad_result=result
  bad_result%thermo_analysis_budget%enthalpy_change_j=ieee_value(0.0_real64,ieee_quiet_nan)
  CALL write_shadow_diagnostics(TRIM(bad_output_path),background,candidate,longitude,bad_result,config, &
    residual_before,residual_after,writer_status,operational,pressure_analysis_candidate=.TRUE.)
  INQUIRE(FILE=TRIM(bad_output_path),EXIST=bad_output_exists)
  IF (writer_status==STATUS_OK .OR. bad_output_exists) &
    ERROR STOP 'writer accepted or emitted a nonfinite prior ledger'
  bad_output_path=TRIM(output_path)//'.bad-condensate.nc'
  INQUIRE(FILE=TRIM(bad_output_path),EXIST=bad_output_exists)
  IF (bad_output_exists) ERROR STOP 'stale invalid-condensate output exists before writer rejection test'
  bad_result=result
  bad_result%pre_density_condensates(1,1)=ieee_value(0.0_real32,ieee_quiet_nan)
  CALL write_shadow_diagnostics(TRIM(bad_output_path),background,candidate,longitude,bad_result,config, &
    residual_before,residual_after,writer_status,operational,pressure_analysis_candidate=.TRUE.)
  INQUIRE(FILE=TRIM(bad_output_path),EXIST=bad_output_exists)
  IF (writer_status==STATUS_OK .OR. bad_output_exists) &
    ERROR STOP 'writer accepted or emitted a nonfinite same-trial condensate witness'
  IF (result%thermo_analysis_budget%accounted_cells<=0_int64) &
    ERROR STOP 'separate thermo-density prior ledger has no covered cells'
  IF (ANY(result%thermo_analysis_budget%mixing_ratio_change_kg(2:6)/=0.0_real64)) &
    ERROR STOP 'thermodynamic density prior ledger includes a condensate mixing-ratio increment'
  observed_cells=COUNT(candidate%obs_support>0_int32)

  CALL configure_trial(config)
  config%thermo_density_prior%max_temperature_increment=1.0e-12_real64
  config%thermo_density_prior%max_vapor_increment=1.0e-12_real64
  CALL run_cloud_bal_pipeline(background,candidate,operational,rejected_result,config, &
    thermo_active=thermo_support,thermo_surface=thermo_surface,target_rh=TARGET_RH, &
    geopotential_support=phi_support,geopotential_reference_level=phi_reference, &
    analysis_support=analysis_support,background_control_support=control, &
    background_validation_shell=shell,force_support=force_support)
  IF (rejected_result%status==STATUS_OK .OR. rejected_result%thermo_density_prior_applied) &
    ERROR STOP 'over-cap joint trial was accepted'
  IF (.NOT.canonical_states_equal(background,candidate) .OR. &
      .NOT.canonical_states_equal(background,operational)) ERROR STOP 'rejected trial did not roll back atomically'
  IF (ALLOCATED(rejected_result%pre_density_temperature) .OR. &
      ALLOCATED(rejected_result%pre_density_vapor) .OR. &
      ALLOCATED(rejected_result%pre_density_condensates) .OR. &
      ALLOCATED(rejected_result%pre_density_dry_mass)) ERROR STOP 'rejected trial retained prior snapshots'
  IF (rejected_result%thermo_analysis_budget%accounted_cells/=0_int64 .OR. &
      rejected_result%thermo_analysis_budget%enthalpy_change_j/=0.0_real64 .OR. &
      ANY(rejected_result%thermo_analysis_budget%species_change_kg/=0.0_real64)) &
    ERROR STOP 'rejected trial retained its prior ledger'
  IF (ANY(rejected_result%thermo_budget%species_change_kg/=0.0_real64) .OR. &
      rejected_result%thermo_budget%enthalpy_error_j/=0.0_real64) &
    ERROR STOP 'rejected trial retained its phase ledger'
  WRITE(*,'(A,I0)') 'analysis_support_cells=',COUNT(analysis_support)
  WRITE(*,'(A,I0)') 'thermo_support_cells=',COUNT(thermo_support)
  WRITE(*,'(A,I0)') 'phi_support_cells=',COUNT(phi_support)
  WRITE(*,'(A,I0)') 'retrieval_observation_signal_cells=',observed_cells
  WRITE(*,'(A,ES24.16)') 'retrieval_temperature_delta_max_k=',retrieval_delta
  WRITE(*,'(A,ES24.16)') 'density_prior_temperature_delta_max_k=',density_delta
  WRITE(*,'(A,ES24.16)') 'joint_phi_delta_max_m2_s2=',phi_delta
  WRITE(*,'(A,ES24.16)') 'joint_candidate_continuity_rms=',rms
  WRITE(*,'(A,ES24.16)') 'force_prior_input_geostrophic_rms=',result%force_prior%input_force_rms
  WRITE(*,'(A,ES24.16)') 'force_prior_candidate_geostrophic_rms=',result%force_prior%candidate_force_rms
  WRITE(*,'(A,ES24.16)') 'force_prior_max_wind_increment=',result%force_prior%maximum_wind_increment
  WRITE(*,'(A,I0)') 'force_prior_backtracking_steps=',result%force_prior%backtracking_steps
  WRITE(*,'(A,ES24.16)') 'continuity_solver_residual_fraction=',config%balance%solver_residual_fraction
  WRITE(*,'(A)') 'observational_continuity_assessed=F'
  WRITE(*,'(A)') 'shared_flux_candidate_operator_rebuilt=T'
  WRITE(*,'(A)') 'writer_roundtrip=T'
  WRITE(*,'(A)') 'invalid_prior_ledger_rejected_without_output=T'
  WRITE(*,'(A)') 'invalid_condensate_witness_rejected_without_output=T'
  WRITE(*,'(A)') 'writer_producer_replay=T'
  WRITE(*,'(A)') 'density_prior_condensate_increment_zero=T'
  WRITE(*,'(A)') 'failed_trial_atomic_rollback=T'
  WRITE(*,'(A)') 'outcome=ACCEPTED_JOINT_THERMO_PHI_FORCE_CANDIDATE'
  WRITE(*,'(A)') 'science_authority=NONE'

CONTAINS

  SUBROUTINE masked_norm(mask,values,rms_value,max_value)
    LOGICAL,INTENT(IN)::mask(:,:,:)
    REAL(real64),INTENT(IN)::values(:,:,:)
    REAL(real64),INTENT(OUT)::rms_value,max_value
    REAL(real64)::sum_squares,value
    INTEGER::ii,jj,kk,sample_count
    sample_count=COUNT(mask)
    IF (sample_count<=0) ERROR STOP 'shared-flux continuity shell is empty'
    sum_squares=0.0_real64; max_value=0.0_real64
    DO kk=1,SIZE(values,3); DO jj=1,SIZE(values,2); DO ii=1,SIZE(values,1)
      IF (.NOT.mask(ii,jj,kk)) CYCLE
      value=ABS(values(ii,jj,kk))
      sum_squares=sum_squares+value*value
      max_value=MAX(max_value,value)
    END DO; END DO; END DO
    rms_value=SQRT(sum_squares/REAL(sample_count,real64))
  END SUBROUTINE masked_norm

  SUBROUTINE configure_trial(pipeline_config)
    TYPE(cloud_bal_pipeline_config), INTENT(OUT) :: pipeline_config
    CHARACTER(LEN=8) :: fixed_omega_policy
    INTEGER :: environment_status
    pipeline_config%requested_mode=MODE_SHADOW
    pipeline_config%maximum_outer_iterations=8
    pipeline_config%column%transport_precipitation=.FALSE.
    pipeline_config%background_continuity_prior=.TRUE.
    pipeline_config%balance%maximum_wind_increment=10.0_real64
    pipeline_config%balance%maximum_omega_increment=5.0_real64
    CALL GET_ENVIRONMENT_VARIABLE('CLOUD_BAL_FIXED_OMEGA_FOR_EXPORT', &
      fixed_omega_policy,STATUS=environment_status)
    pipeline_config%balance%fixed_omega_for_export= &
      environment_status==0 .AND. TRIM(fixed_omega_policy)=='1'
    pipeline_config%balance%increment_headroom=0.95_real64
    pipeline_config%balance%solver_residual_fraction=1.0e-3_real64
    pipeline_config%force_prior_enabled=.TRUE.
    pipeline_config%thermo_density_prior%enabled=.TRUE.
    pipeline_config%thermo_density_prior%background_weight=0.5_real64
    pipeline_config%thermo_density_prior%max_temperature_increment=5.0_real64
    pipeline_config%thermo_density_prior%max_vapor_increment=0.005_real64
  END SUBROUTINE configure_trial

  SUBROUTINE nc_open_checked(path,id)
    CHARACTER(LEN=*),INTENT(IN)::path
    INTEGER,INTENT(OUT)::id
    IF(nf90_open(TRIM(path),NF90_NOWRITE,id)/=NF90_NOERR) ERROR STOP 'cannot open retained coupled NetCDF'
  END SUBROUTINE nc_open_checked

  SUBROUTINE nc_close_checked(id)
    INTEGER,INTENT(IN)::id
    IF(nf90_close(id)/=NF90_NOERR) ERROR STOP 'cannot close retained coupled NetCDF'
  END SUBROUTINE nc_close_checked

  SUBROUTINE assert_dims(id,nx0,ny0,nz0)
    INTEGER,INTENT(IN)::id,nx0,ny0,nz0
    INTEGER::dimid,n
    IF(nf90_inq_dimid(id,'x',dimid)/=NF90_NOERR) ERROR STOP 'missing x dimension'
    IF(nf90_inquire_dimension(id,dimid,len=n)/=NF90_NOERR .OR. n/=nx0) ERROR STOP 'x dimension mismatch'
    IF(nf90_inq_dimid(id,'y',dimid)/=NF90_NOERR) ERROR STOP 'missing y dimension'
    IF(nf90_inquire_dimension(id,dimid,len=n)/=NF90_NOERR .OR. n/=ny0) ERROR STOP 'y dimension mismatch'
    IF(nf90_inq_dimid(id,'z',dimid)/=NF90_NOERR) ERROR STOP 'missing z dimension'
    IF(nf90_inquire_dimension(id,dimid,len=n)/=NF90_NOERR .OR. n/=nz0) ERROR STOP 'z dimension mismatch'
  END SUBROUTINE assert_dims

  INTEGER FUNCTION var_id(id,name)
    INTEGER,INTENT(IN)::id
    CHARACTER(LEN=*),INTENT(IN)::name
    IF(nf90_inq_varid(id,TRIM(name),var_id)/=NF90_NOERR) ERROR STOP 'missing retained variable'
  END FUNCTION var_id

  SUBROUTINE read_i3(id,name,data)
    INTEGER,INTENT(IN)::id
    CHARACTER(LEN=*),INTENT(IN)::name
    INTEGER(int32),INTENT(OUT)::data(:,:,:)
    INTEGER(int32),ALLOCATABLE::level(:,:,:)
    INTEGER::k,rc
    ALLOCATE(level(SIZE(data,1),SIZE(data,2),1))
    DO k=1,SIZE(data,3)
      rc=nf90_get_var(id,var_id(id,name),level,start=[1,1,k],count=[SIZE(data,1),SIZE(data,2),1])
      IF(rc/=NF90_NOERR) ERROR STOP 'failed retained integer read'
      data(:,:,k)=level(:,:,1)
    END DO
  END SUBROUTINE read_i3

  SUBROUTINE read_i2(id,name,data)
    INTEGER,INTENT(IN)::id
    CHARACTER(LEN=*),INTENT(IN)::name
    INTEGER,INTENT(OUT)::data(:,:)
    IF(nf90_get_var(id,var_id(id,name),data)/=NF90_NOERR) ERROR STOP 'failed retained integer 2d read'
  END SUBROUTINE read_i2

  SUBROUTINE read_mask(id,name,mask,integer_scratch)
    INTEGER,INTENT(IN)::id
    CHARACTER(LEN=*),INTENT(IN)::name
    LOGICAL,INTENT(OUT)::mask(:,:,:)
    INTEGER(int32),INTENT(INOUT)::integer_scratch(:,:,:)
    CALL read_i3(id,name,integer_scratch)
    IF(ANY((integer_scratch/=0_int32).AND.(integer_scratch/=1_int32))) &
      ERROR STOP 'retained support mask is not binary'
    mask=integer_scratch==1_int32
  END SUBROUTINE read_mask

END PROGRAM pr81_joint_thermo_retained
