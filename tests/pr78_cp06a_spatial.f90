PROGRAM pr78_cp06a_spatial
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32,int64
  USE cloud_bal_state
  USE cloud_bal_column_physics, ONLY: SATURATION_LIQUID
  USE cloud_bal_balance_operator, ONLY: balance_operator_type,build_diagnostic_balance_operator, &
    state_continuity_residual
  USE cloud_bal_pipeline
  USE cloud_bal_real_netcdf, ONLY: read_real_shadow_state,write_shadow_diagnostics
  IMPLICIT NONE

  TYPE(cloud_bal_state_type) :: background,operational,off_candidate,hydro_candidate, &
                                coupled_candidate,hydro_operational,coupled_operational
  TYPE(cloud_bal_pipeline_config) :: off_config,hydro_config,coupled_config
  TYPE(cloud_bal_pipeline_result) :: off_result,hydro_result,coupled_result
  TYPE(balance_operator_type) :: diagnostic_operator
  REAL(real32), ALLOCATABLE :: longitude(:,:)
  REAL(real64), ALLOCATABLE :: residual_before(:,:,:),residual_after(:,:,:)
  LOGICAL, ALLOCATABLE :: analysis_support(:,:,:),control_support(:,:,:), &
    validation_shell(:,:,:),thermo_active(:,:,:),geopotential_support(:,:,:)
  INTEGER, ALLOCATABLE :: geopotential_reference_level(:,:)
  CHARACTER(LEN=2048) :: arg(15),hydro_path,coupled_path
  INTEGER(int64) :: valid_time
  INTEGER :: io_status,status,reason,nx,ny,nz,center_i,center_j,i,j,k, &
             patch_cells,control_cells,shell_cells,thermo_cells,phi_cells, &
             off_status,hydro_status,coupled_status,bottom_level,top_level, &
             hydro_write_status,coupled_write_status

  IF (COMMAND_ARGUMENT_COUNT()/=15) ERROR STOP &
    'usage: pr78_cp06a_spatial FUA FSF LW3 VRZ VRT STATIC LT1 LQ3 LWC LSX LCP LTY EPOCH OUTPUT_DIR MODE'
  DO i=1,15
    CALL GET_COMMAND_ARGUMENT(i,arg(i))
  END DO
  READ(arg(13),*,IOSTAT=io_status) valid_time
  IF (io_status/=0 .OR. valid_time/=1786885200_int64) &
    ERROR STOP 'unexpected CP06-A valid time'
  hydro_path=TRIM(arg(14))//'/hydro.nc'
  coupled_path=TRIM(arg(14))//'/coupled.nc'
  hydro_write_status=STATUS_FAILED
  coupled_write_status=STATUS_FAILED

  CALL read_real_shadow_state(TRIM(arg(1)),TRIM(arg(2)),TRIM(arg(3)), &
    TRIM(arg(4)),TRIM(arg(5)),TRIM(arg(6)),valid_time,background,longitude,status,reason, &
    lt1_path=TRIM(arg(7)),lq3_path=TRIM(arg(8)),lwc_path=TRIM(arg(9)), &
    lsx_path=TRIM(arg(10)),lcp_path=TRIM(arg(11)),lty_path=TRIM(arg(12)))
  IF (status/=STATUS_OK) THEN
    WRITE(*,'(A,I0,A,I0)') 'reader_status=',status,',reason=',reason
    ERROR STOP 'retained CP06-A input reader failed'
  END IF

  nx=background%grid%nx; ny=background%grid%ny; nz=background%grid%nz
  ALLOCATE(analysis_support(nx,ny,nz),control_support(nx,ny,nz), &
    validation_shell(nx,ny,nz),thermo_active(nx,ny,nz), &
    geopotential_support(nx,ny,nz),geopotential_reference_level(nx,ny))
  analysis_support=.FALSE.; control_support=.FALSE.; validation_shell=.FALSE.
  thermo_active=.FALSE.; geopotential_support=.FALSE.
  geopotential_reference_level=0
  center_i=0; center_j=0

  ! Fix the first row-major 5x5 window whose columns each contain at least
  ! one positive observed liquid-water/usable-radar-echo cell and whose 7x7
  ! validation shell has complete usable background winds and omega.
  DO j=4,ny-3
    DO i=4,nx-3
      IF (.NOT.patch_observations_present(background,i,j)) CYCLE
      IF (.NOT.background_window_is_usable(background,i,j,3)) CYCLE
      center_i=i; center_j=j
      EXIT
    END DO
    IF (center_i/=0) EXIT
  END DO
  IF (center_i==0) ERROR STOP 'no pre-candidate 5x5 observation/background window'

  DO j=center_j-1,center_j+1
    DO i=center_i-1,center_i+1
      bottom_level=FINDLOC(background%above_ground(i,j,:),.TRUE.,DIM=1)
      top_level=FINDLOC(background%above_ground(i,j,:),.TRUE.,DIM=1,BACK=.TRUE.)
      geopotential_support(i,j,:)=background%above_ground(i,j,:)
      geopotential_reference_level(i,j)=bottom_level
      DO k=1,nz
        IF (.NOT.background%above_ground(i,j,k)) CYCLE
        IF (k<=bottom_level .OR. k>=top_level) CYCLE
        IF (.NOT.background_cell_is_usable(background,i,j,k)) CYCLE
        analysis_support(i,j,k)=.TRUE.
        control_support(i,j,k)=.TRUE.
        IF (background%cloud_water%value(i,j,k)>0.0_real32 .AND. &
            background%temperature%value(i,j,k)>273.15_real32 .AND. &
            background%cloud_fraction%value(i,j,k)>0.0_real32 .AND. &
            cell_is_usable(background%cloud_water%valid(i,j,k), &
              background%cloud_water%quality(i,j,k),background%cloud_water%source(i,j,k)) .AND. &
            cell_is_usable(background%cloud_fraction%valid(i,j,k), &
              background%cloud_fraction%quality(i,j,k),background%cloud_fraction%source(i,j,k)) .AND. &
            cell_is_usable(background%temperature%valid(i,j,k), &
              background%temperature%quality(i,j,k),background%temperature%source(i,j,k)) .AND. &
            radar_echo_cell(background%radar_reflectivity%value(i,j,k), &
              background%radar_reflectivity%valid(i,j,k), &
              background%radar_reflectivity%quality(i,j,k), &
              background%radar_reflectivity%source(i,j,k))) thermo_active(i,j,k)=.TRUE.
      END DO
    END DO
  END DO
  DO j=center_j-2,center_j+2
    DO i=center_i-2,center_i+2
      DO k=1,nz
        IF (.NOT.background%above_ground(i,j,k)) CYCLE
        IF (.NOT.background_cell_is_usable(background,i,j,k)) CYCLE
        control_support(i,j,k)=.TRUE.
      END DO
    END DO
  END DO
  DO j=center_j-3,center_j+3
    DO i=center_i-3,center_i+3
      DO k=1,nz
        IF (.NOT.background%above_ground(i,j,k)) CYCLE
        IF (.NOT.background_cell_is_usable(background,i,j,k)) &
          ERROR STOP 'selected validation shell has an unusable background cell'
        validation_shell(i,j,k)=.TRUE.
      END DO
    END DO
  END DO
  patch_cells=COUNT(analysis_support)
  control_cells=COUNT(control_support)
  shell_cells=COUNT(validation_shell)
  thermo_cells=COUNT(thermo_active)
  phi_cells=COUNT(geopotential_support)
  IF (thermo_cells<=0 .OR. patch_cells<=0 .OR. control_cells<=patch_cells .OR. &
      shell_cells<control_cells .OR. phi_cells<=patch_cells .OR. &
      ANY(analysis_support .AND. .NOT.control_support)) &
    ERROR STOP 'selected CP06-A support masks are empty or inconsistent'

  WRITE(*,'(A)') 'case=CP06A-20260816T130000Z-background-prior-v2'
  WRITE(*,'(A,I0)') 'valid_time=',valid_time
  WRITE(*,'(A,I0,A,I0)') 'selected_center_i=',center_i,',j=',center_j
  WRITE(*,'(A,I0,A,I0,A,I0,A,I0)') 'patch_i=',center_i-2,':',center_i+2, &
    ',patch_j=',center_j-2,':',center_j+2
  WRITE(*,'(A,I0,A,I0,A,I0,A,I0)') 'analysis_i=',center_i-1,':',center_i+1, &
    ',analysis_j=',center_j-1,':',center_j+1
  WRITE(*,'(A)') 'selection_rule=first-row-major-observed-5x5-with-usable-7x7-shell;3x3-interior-level-analysis;full-3x3-phi;5x5-balance-control'
  WRITE(*,'(A,I0)') 'analysis_support_cells=',patch_cells
  WRITE(*,'(A,I0)') 'background_control_support_cells=',control_cells
  WRITE(*,'(A,I0)') 'background_validation_shell_cells=',shell_cells
  WRITE(*,'(A,I0)') 'thermo_active_warm_liquid_observation_cells=',thermo_cells
  WRITE(*,'(A,I0)') 'geopotential_support_cells=',phi_cells
  WRITE(*,'(A,I0)') 'radar_echo_cells=',COUNT(background%radar_reflectivity%valid)
  WRITE(*,'(A,I0)') 'cloud_water_positive_cells=', &
    COUNT(background%cloud_water%valid .AND. background%cloud_water%value>0.0_real32)
  WRITE(*,'(A,I0)') 'cloud_fraction_valid_cells=',COUNT(background%cloud_fraction%valid)
  WRITE(*,'(A,I0)') 'omega_target_cells=',COUNT(background%omega_target%valid)
  WRITE(*,'(A,I0)') 'omega_target_sigma_cells=',COUNT(background%omega_target_sigma%valid)
  WRITE(*,'(A)') 'science_authority=NONE'
  CALL write_pre_candidate_support_masks(TRIM(arg(14)),nx,ny,nz,center_i,center_j, &
    analysis_support,geopotential_support,control_support,validation_shell,thermo_active)
  WRITE(*,'(A)') 'pre_candidate_support_masks_written=T'
  IF (TRIM(arg(15))=='preflight') STOP
  IF (TRIM(arg(15))/='run') ERROR STOP 'mode must be preflight or run'

  off_config%requested_mode=MODE_OFF
  off_config%maximum_outer_iterations=8
  off_config%column%transport_precipitation=.FALSE.
  CALL run_cloud_bal_pipeline(background,off_candidate,operational,off_result,off_config)
  off_status=off_result%status
  IF (off_status==STATUS_OK .AND. .NOT.canonical_states_equal(background,off_candidate)) &
    ERROR STOP 'OFF candidate changed the canonical background'
  IF (off_status==STATUS_OK .AND. .NOT.canonical_states_equal(background,operational)) &
    ERROR STOP 'OFF changed the operational state'
  WRITE(*,'(A,I0,A,I0,A,L1)') 'OFF_status=',off_status,',reason=', &
    off_result%reason_code,',exact_same_state=',canonical_states_equal(background,off_candidate)

  hydro_config%requested_mode=MODE_SHADOW
  hydro_config%maximum_outer_iterations=8
  hydro_config%column%transport_precipitation=.FALSE.
  CALL run_cloud_bal_pipeline(background,hydro_candidate,hydro_operational,hydro_result,hydro_config, &
    thermo_active=thermo_active,thermo_surface=liquid_surface_mask(),target_rh=1.0_real64, &
    geopotential_support=geopotential_support, &
    geopotential_reference_level=geopotential_reference_level,analysis_support=analysis_support)
  hydro_status=hydro_result%status
  WRITE(*,'(A,I0,A,I0,A,I0)') 'HYDRO_status=',hydro_status,',reason=', &
    hydro_result%reason_code,',outer_iterations=',hydro_result%outer_iterations
  WRITE(*,'(A,I0,A,I0,A,I0,A,I0)') 'HYDRO_column_changed=',COUNT(hydro_result%column%changed), &
    ',thermo_active=',thermo_cells,',geopotential_changed=',COUNT(hydro_result%geopotential%changed), &
    ',balance_changed=',COUNT(hydro_result%balance%changed)
  IF (hydro_status==STATUS_OK) THEN
    IF (.NOT.canonical_states_equal(background,hydro_operational)) &
      ERROR STOP 'HYDRO changed the operational state'
    IF (.NOT.same_omega_evidence(background,hydro_candidate)) &
      ERROR STOP 'HYDRO changed omega target or sigma values/metadata'
    WRITE(*,'(A)') 'HYDRO_omega_target_and_sigma_unchanged=T'
  END IF

  coupled_config%requested_mode=MODE_SHADOW
  coupled_config%maximum_outer_iterations=8
  coupled_config%background_continuity_prior=.TRUE.
  coupled_config%column%transport_precipitation=.FALSE.
  CALL run_cloud_bal_pipeline(background,coupled_candidate,coupled_operational,coupled_result,coupled_config, &
    thermo_active=thermo_active,thermo_surface=liquid_surface_mask(),target_rh=1.0_real64, &
    geopotential_support=geopotential_support, &
    geopotential_reference_level=geopotential_reference_level,analysis_support=analysis_support, &
    background_control_support=control_support,background_validation_shell=validation_shell)
  coupled_status=coupled_result%status
  WRITE(*,'(A,I0,A,I0,A,I0)') 'COUPLED_status=',coupled_status,',reason=', &
    coupled_result%reason_code,',outer_iterations=',coupled_result%outer_iterations
  WRITE(*,'(A,I0,A,I0,A,I0,A,I0)') 'COUPLED_column_changed=',COUNT(coupled_result%column%changed), &
    ',thermo_active=',thermo_cells,',geopotential_changed=',COUNT(coupled_result%geopotential%changed), &
    ',balance_changed=',COUNT(coupled_result%balance%changed)
  WRITE(*,'(A,I0)') 'COUPLED_solver_reason=',coupled_result%balance%numerical%solver_reason
  WRITE(*,'(A,I0,A,I0)') 'COUPLED_balance_status=',coupled_result%balance%status, &
    ',balance_reason=',coupled_result%balance%reason_code
  WRITE(*,'(A,I0)') 'COUPLED_solver_iterations=',coupled_result%balance%numerical%solver_iterations
  WRITE(*,'(A,ES24.16)') 'COUPLED_background_tendency_rms=', &
    coupled_result%balance%numerical%continuity_background_rms
  WRITE(*,'(A,ES24.16)') 'COUPLED_background_tendency_max=', &
    coupled_result%balance%numerical%continuity_background_max
  WRITE(*,'(A,ES24.16)') 'COUPLED_closure_rms=', &
    coupled_result%balance%numerical%continuity_candidate_rms
  WRITE(*,'(A,ES24.16)') 'COUPLED_closure_max=', &
    coupled_result%balance%numerical%continuity_candidate_max
  WRITE(*,'(A,ES24.16)') 'COUPLED_max_wind_increment_ms=', &
    coupled_result%balance%numerical%max_wind_increment
  WRITE(*,'(A,ES24.16)') 'COUPLED_max_omega_increment_pas=', &
    coupled_result%balance%numerical%max_omega_increment
  WRITE(*,'(A,ES24.16)') 'COUPLED_flux_ledger_error=',coupled_result%column%numerical%ledger_error
  IF (coupled_status==STATUS_OK) THEN
    IF (.NOT.canonical_states_equal(background,coupled_operational)) &
      ERROR STOP 'COUPLED changed the operational state'
    IF (.NOT.same_omega_evidence(background,coupled_candidate)) &
      ERROR STOP 'COUPLED changed omega target or sigma values/metadata'
    WRITE(*,'(A)') 'COUPLED_omega_target_and_sigma_unchanged=T'
    CALL build_diagnostic_balance_operator(background,diagnostic_operator,status,reason)
    IF (status/=STATUS_OK) ERROR STOP 'diagnostic continuity operator failed'
    ALLOCATE(residual_before(nx,ny,nz),residual_after(nx,ny,nz))
    CALL state_continuity_residual(diagnostic_operator,background,residual_before,status)
    IF (status/=STATUS_OK) ERROR STOP 'background residual readback preparation failed'
    CALL state_continuity_residual(diagnostic_operator,coupled_candidate,residual_after,status)
    IF (status/=STATUS_OK) ERROR STOP 'candidate residual readback preparation failed'
    CALL write_shadow_diagnostics(TRIM(coupled_path),background,coupled_candidate,longitude, &
      coupled_result,coupled_config,residual_before,residual_after,status,coupled_operational, &
      pressure_analysis_candidate=.TRUE.)
    coupled_write_status=status
    WRITE(*,'(A,I0)') 'COUPLED_diagnostic_write_status=',status
  END IF
  IF (hydro_status==STATUS_OK) THEN
    CALL build_diagnostic_balance_operator(background,diagnostic_operator,status,reason)
    IF (status/=STATUS_OK) ERROR STOP 'HYDRO diagnostic continuity operator failed'
    IF (.NOT.ALLOCATED(residual_before)) ALLOCATE(residual_before(nx,ny,nz),residual_after(nx,ny,nz))
    CALL state_continuity_residual(diagnostic_operator,background,residual_before,status)
    IF (status/=STATUS_OK) ERROR STOP 'HYDRO background residual preparation failed'
    CALL state_continuity_residual(diagnostic_operator,hydro_candidate,residual_after,status)
    IF (status/=STATUS_OK) ERROR STOP 'HYDRO candidate residual preparation failed'
    CALL write_shadow_diagnostics(TRIM(hydro_path),background,hydro_candidate,longitude, &
      hydro_result,hydro_config,residual_before,residual_after,status,hydro_operational, &
      pressure_analysis_candidate=.TRUE.)
    hydro_write_status=status
    WRITE(*,'(A,I0)') 'HYDRO_diagnostic_write_status=',status
  END IF
  IF (off_status/=STATUS_OK .OR. hydro_status/=STATUS_OK .OR. coupled_status/=STATUS_OK .OR. &
      hydro_write_status/=STATUS_OK .OR. coupled_write_status/=STATUS_OK) &
    WRITE(*,'(A)') 'producer_decision=REJECTED_OR_INCOMPLETE'
  IF (off_status==STATUS_OK .AND. hydro_status==STATUS_OK .AND. coupled_status==STATUS_OK .AND. &
      hydro_write_status==STATUS_OK .AND. coupled_write_status==STATUS_OK) &
    WRITE(*,'(A)') 'producer_decision=SCOPED_PRESSURE_CANDIDATE_WRITTEN'
  WRITE(*,'(A)') 'science_authority=NONE'
  WRITE(*,'(A)') 'native_validation=NOT_RUN'

CONTAINS

  SUBROUTINE write_pre_candidate_support_masks(output_dir,nx_in,ny_in,nz_in,i_center,j_center, &
      analysis_mask,phi_mask,control_mask,shell_mask,thermo_mask)
    CHARACTER(LEN=*), INTENT(IN) :: output_dir
    INTEGER, INTENT(IN) :: nx_in,ny_in,nz_in,i_center,j_center
    LOGICAL, INTENT(IN) :: analysis_mask(:,:,:),phi_mask(:,:,:),control_mask(:,:,:), &
                           shell_mask(:,:,:),thermo_mask(:,:,:)
    INTEGER(int32), ALLOCATABLE :: encoded(:,:,:)
    INTEGER :: unit_number,io
    OPEN(NEWUNIT=unit_number,FILE=TRIM(output_dir)//'/pre_candidate_support.bin', &
      ACCESS='STREAM',FORM='UNFORMATTED',STATUS='REPLACE',IOSTAT=io)
    IF (io/=0) ERROR STOP 'cannot create pre-candidate support mask receipt'
    WRITE(unit_number,IOSTAT=io) INT([nx_in,ny_in,nz_in,i_center,j_center],int32)
    IF (io/=0) ERROR STOP 'cannot write support receipt header'
    ALLOCATE(encoded(nx_in,ny_in,nz_in))
    encoded=0_int32
    WHERE(analysis_mask) encoded=1_int32
    WRITE(unit_number,IOSTAT=io) encoded
    IF (io/=0) ERROR STOP 'cannot write analysis support receipt'
    encoded=0_int32; WHERE(phi_mask) encoded=1_int32
    WRITE(unit_number,IOSTAT=io) encoded
    IF (io/=0) ERROR STOP 'cannot write geopotential support receipt'
    encoded=0_int32; WHERE(control_mask) encoded=1_int32
    WRITE(unit_number,IOSTAT=io) encoded
    IF (io/=0) ERROR STOP 'cannot write balance control receipt'
    encoded=0_int32; WHERE(shell_mask) encoded=1_int32
    WRITE(unit_number,IOSTAT=io) encoded
    IF (io/=0) ERROR STOP 'cannot write validation shell receipt'
    encoded=0_int32; WHERE(thermo_mask) encoded=1_int32
    WRITE(unit_number,IOSTAT=io) encoded
    IF (io/=0) ERROR STOP 'cannot write thermo support receipt'
    CLOSE(unit_number,IOSTAT=io)
    IF (io/=0) ERROR STOP 'cannot close pre-candidate support receipt'
  END SUBROUTINE write_pre_candidate_support_masks

  FUNCTION liquid_surface_mask() RESULT(surface)
    INTEGER, ALLOCATABLE :: surface(:,:,:)
    ALLOCATE(surface(nx,ny,nz))
    surface=SATURATION_LIQUID
  END FUNCTION liquid_surface_mask

  LOGICAL FUNCTION background_cell_is_usable(state,i,j,k)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    INTEGER, INTENT(IN) :: i,j,k
    background_cell_is_usable= &
      cell_is_usable(state%u%valid(i,j,k),state%u%quality(i,j,k),state%u%source(i,j,k)) .AND. &
      cell_is_usable(state%v%valid(i,j,k),state%v%quality(i,j,k),state%v%source(i,j,k)) .AND. &
      cell_is_usable(state%omega%valid(i,j,k),state%omega%quality(i,j,k),state%omega%source(i,j,k))
  END FUNCTION background_cell_is_usable

  LOGICAL FUNCTION same_omega_evidence(state_a,state_b)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state_a,state_b
    same_omega_evidence= &
      ALL(state_a%omega_target%value==state_b%omega_target%value) .AND. &
      ALL(state_a%omega_target%valid .EQV. state_b%omega_target%valid) .AND. &
      ALL(state_a%omega_target%quality==state_b%omega_target%quality) .AND. &
      ALL(state_a%omega_target%source==state_b%omega_target%source) .AND. &
      ALL(state_a%omega_target_sigma%value==state_b%omega_target_sigma%value) .AND. &
      ALL(state_a%omega_target_sigma%valid .EQV. state_b%omega_target_sigma%valid) .AND. &
      ALL(state_a%omega_target_sigma%quality==state_b%omega_target_sigma%quality) .AND. &
      ALL(state_a%omega_target_sigma%source==state_b%omega_target_sigma%source)
  END FUNCTION same_omega_evidence

  LOGICAL FUNCTION patch_observations_present(state,i_center,j_center)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    INTEGER, INTENT(IN) :: i_center,j_center
    INTEGER :: i,j,k
    LOGICAL :: column_has_pair
    patch_observations_present=.FALSE.
    DO j=j_center-2,j_center+2
      DO i=i_center-2,i_center+2
        column_has_pair=.FALSE.
        DO k=1,state%grid%nz
          IF (.NOT.state%above_ground(i,j,k)) CYCLE
          IF (.NOT.cell_is_usable(state%cloud_water%valid(i,j,k), &
              state%cloud_water%quality(i,j,k),state%cloud_water%source(i,j,k))) CYCLE
          IF (state%cloud_water%value(i,j,k)<=0.0_real32) CYCLE
          IF (.NOT.radar_echo_cell(state%radar_reflectivity%value(i,j,k), &
              state%radar_reflectivity%valid(i,j,k), &
              state%radar_reflectivity%quality(i,j,k), &
              state%radar_reflectivity%source(i,j,k))) CYCLE
          column_has_pair=.TRUE.
          EXIT
        END DO
        IF (.NOT.column_has_pair) RETURN
      END DO
    END DO
    patch_observations_present=.TRUE.
  END FUNCTION patch_observations_present

  LOGICAL FUNCTION background_window_is_usable(state,i_center,j_center,halo)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    INTEGER, INTENT(IN) :: i_center,j_center,halo
    INTEGER :: i,j,k
    background_window_is_usable=.FALSE.
    DO j=j_center-halo,j_center+halo
      DO i=i_center-halo,i_center+halo
        DO k=1,state%grid%nz
          IF (.NOT.state%above_ground(i,j,k)) CYCLE
          IF (.NOT.background_cell_is_usable(state,i,j,k)) RETURN
        END DO
      END DO
    END DO
    background_window_is_usable=.TRUE.
  END FUNCTION background_window_is_usable

END PROGRAM pr78_cp06a_spatial
