PROGRAM real_manufactured_balance_driver
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32,int64
  USE cloud_bal_state
  USE cloud_bal_column_physics
  USE cloud_bal_balance_operator
  USE cloud_bal_real_netcdf
  USE netcdf
  IMPLICIT NONE

  TYPE(cloud_bal_state_type) :: operational,operational_snapshot,work,candidate
  TYPE(column_physics_config) :: column_config
  TYPE(balance_operator_config) :: balance_config
  TYPE(balance_operator_type) :: diagnostic_operator
  TYPE(stage_result) :: column_result,balance_result
  REAL(real32), ALLOCATABLE :: longitude(:,:)
  REAL(real64), ALLOCATABLE :: residual_background(:,:,:)
  REAL(real64), ALLOCATABLE :: residual_candidate(:,:,:)
  REAL(real64), ALLOCATABLE :: residual_proposed(:,:,:)
  REAL(real64), ALLOCATABLE :: residual_projected(:,:,:)
  CHARACTER(LEN=1024) :: fua,fsf_before,fsf_center,fsf_after,lw3,vrz,vrt,static_file
  CHARACTER(LEN=1024) :: output
  CHARACTER(LEN=64) :: time_text
  INTEGER(int64) :: valid_time
  REAL(real64) :: kappa_omega
  INTEGER :: status,reason,io_status,seed_i,seed_j
  REAL(real64) :: boundary_min,boundary_max

  IF (COMMAND_ARGUMENT_COUNT()/=11) ERROR STOP &
    'usage: driver FUA FSF_BEFORE FSF_CENTER FSF_AFTER LW3 VRZ VRT STATIC OUTPUT VALID_TIME KAPPA_OMEGA'
  CALL GET_COMMAND_ARGUMENT(1,fua)
  CALL GET_COMMAND_ARGUMENT(2,fsf_before)
  CALL GET_COMMAND_ARGUMENT(3,fsf_center)
  CALL GET_COMMAND_ARGUMENT(4,fsf_after)
  CALL GET_COMMAND_ARGUMENT(5,lw3)
  CALL GET_COMMAND_ARGUMENT(6,vrz)
  CALL GET_COMMAND_ARGUMENT(7,vrt)
  CALL GET_COMMAND_ARGUMENT(8,static_file)
  CALL GET_COMMAND_ARGUMENT(9,output)
  CALL GET_COMMAND_ARGUMENT(10,time_text)
  READ(time_text,*,IOSTAT=io_status) valid_time
  IF (io_status/=0) ERROR STOP 'invalid valid-time epoch'
  CALL GET_COMMAND_ARGUMENT(11,time_text)
  READ(time_text,*,IOSTAT=io_status) kappa_omega
  IF (io_status/=0 .OR. kappa_omega<=0.0_real64) ERROR STOP 'invalid kappa omega'

  CALL read_real_shadow_state(TRIM(fua),TRIM(fsf_center),TRIM(lw3),TRIM(vrz), &
    TRIM(vrt),TRIM(static_file),valid_time,operational,longitude,status,reason)
  IF (status/=STATUS_OK) ERROR STOP 'real-state adapter failed'
  operational_snapshot=operational
  work=operational
  CALL set_real_numerical_test_boundaries(work,TRIM(fsf_before), &
    TRIM(fsf_center),TRIM(fsf_after),status,reason)
  IF (status/=STATUS_OK) ERROR STOP 'numerical-test boundary construction failed'
  IF (.NOT.manufactured_boundary_contract_valid(work)) &
    ERROR STOP 'numerical-test boundary contract failed'

  CALL derive_column_physics(work,candidate,column_result,column_config)
  IF (column_result%status/=STATUS_OK) ERROR STOP 'column proposal failed'
  work=candidate
  CALL install_manufactured_target(work,0.02_real64,seed_i,seed_j,status)
  IF (status/=STATUS_OK) ERROR STOP 'manufactured target installation failed'

  balance_config%target_authority=TARGET_AUTHORITY_MANUFACTURED_TEST
  balance_config%kappa_omega=kappa_omega
  balance_config%maximum_iterations=1200
  balance_config%solver_residual_fraction=0.05_real64
  balance_config%maximum_wind_increment=0.50_real64
  balance_config%maximum_omega_increment=0.05_real64
  balance_config%minimum_trust_region_fraction=0.25_real64
  balance_config%minimum_target_response_ratio=0.01_real64
  balance_config%maximum_target_response_failure_fraction=0.50_real64
  balance_config%maximum_physical_residual=10.0_real64
  balance_config%geostrophic_absolute_tolerance=0.01_real64
  CALL apply_localized_balance(work,candidate,balance_result,balance_config)
  CALL compute_residual_fields(work,candidate,balance_config,diagnostic_operator, &
    residual_background,residual_candidate,residual_proposed,residual_projected,status)
  IF (status/=STATUS_OK) ERROR STOP 'independent residual field calculation failed'
  CALL write_test_diagnostics(TRIM(output),operational,work,candidate,longitude, &
    balance_result,residual_background,residual_candidate,residual_proposed, &
    residual_projected,status)
  IF (status/=STATUS_OK) ERROR STOP 'test diagnostic write failed'

  boundary_min=MINVAL(REAL(work%omega_bottom_boundary%value,real64))
  boundary_max=MAXVAL(REAL(work%omega_bottom_boundary%value,real64))
  WRITE(*,'(A)') 'evidence_authority=NUMERICAL_REAL_GEOMETRY_ONLY'
  WRITE(*,'(A)') 'science_authority=NONE'
  WRITE(*,'(A)') 'balance_scope=TARGET_INCREMENT_PROJECTION_ONLY'
  WRITE(*,'(A)') 'target_kind=MANUFACTURED_TEST'
  WRITE(*,'(A)') 'boundary_authority=MANUFACTURED_TEST_ONLY'
  WRITE(*,'(A)') 'boundary_driver=MODEL_FSF_PS_TENDENCY_ADVECTION'
  WRITE(*,'(A)') 'surface_wind_frame=UNRESOLVED_NATIVE'
  WRITE(*,'(A,ES24.16)') 'target_amplitude_pas=',0.02_real64
  WRITE(*,'(A,ES24.16)') 'kappa_omega=',balance_config%kappa_omega
  WRITE(*,'(A,ES24.16)') 'minimum_beta=',balance_config%minimum_beta
  WRITE(*,'(A,ES24.16)') 'solver_residual_fraction=', &
    balance_config%solver_residual_fraction
  WRITE(*,'(A,ES24.16)') 'minimum_target_response_ratio=', &
    balance_config%minimum_target_response_ratio
  WRITE(*,'(A,ES24.16)') 'maximum_target_response_failure_fraction=', &
    balance_config%maximum_target_response_failure_fraction
  WRITE(*,'(A,I0)') 'seed_i=',seed_i
  WRITE(*,'(A,I0)') 'seed_j=',seed_j
  WRITE(*,'(A,I0)') 'target_cells=',COUNT(work%omega_target%valid)
  WRITE(*,'(A,I0)') 'beta_cells=',COUNT(work%balance_beta>0.0_real32)
  WRITE(*,'(A,ES24.16)') 'bottom_boundary_min_pas=',boundary_min
  WRITE(*,'(A,ES24.16)') 'bottom_boundary_max_pas=',boundary_max
  WRITE(*,'(A,I0)') 'bottom_boundary_nonzero_cells=', &
    COUNT(ABS(work%omega_bottom_boundary%value)>0.1_real32)
  WRITE(*,'(A,I0)') 'balance_status=',balance_result%status
  WRITE(*,'(A,I0)') 'balance_reason=',balance_result%reason_code
  WRITE(*,'(A,I0)') 'solver_reason=',balance_result%numerical%solver_reason
  WRITE(*,'(A,I0)') 'solver_iterations=',balance_result%numerical%solver_iterations
  WRITE(*,'(A,I0)') 'acceptance_failures=', &
    balance_result%numerical%acceptance_failures
  WRITE(*,'(A,ES24.16)') 'trust_region_fraction=', &
    balance_result%numerical%trust_region_fraction
  WRITE(*,'(A,ES24.16)') 'max_wind_increment_ms=', &
    balance_result%numerical%max_wind_increment
  WRITE(*,'(A,ES24.16)') 'max_omega_increment_pas=', &
    balance_result%numerical%max_omega_increment
  WRITE(*,'(A,ES24.16)') 'continuity_proposed_rms=', &
    balance_result%numerical%continuity_proposed_increment_rms
  WRITE(*,'(A,ES24.16)') 'continuity_proposed_max=', &
    balance_result%numerical%continuity_proposed_increment_max
  WRITE(*,'(A,ES24.16)') 'continuity_projected_rms=', &
    balance_result%numerical%continuity_projected_increment_rms
  WRITE(*,'(A,ES24.16)') 'continuity_projected_max=', &
    balance_result%numerical%continuity_projected_increment_max
  WRITE(*,'(A,ES24.16)') 'continuity_background_rms=', &
    balance_result%numerical%continuity_background_rms
  WRITE(*,'(A,ES24.16)') 'continuity_background_max=', &
    balance_result%numerical%continuity_background_max
  WRITE(*,'(A,ES24.16)') 'continuity_candidate_rms=', &
    balance_result%numerical%continuity_candidate_rms
  WRITE(*,'(A,ES24.16)') 'continuity_candidate_max=', &
    balance_result%numerical%continuity_candidate_max
  WRITE(*,'(A,ES24.16)') 'operator_identity_max=', &
    balance_result%numerical%continuity_operator_identity_max
  WRITE(*,'(A,ES24.16)') 'target_response_failure_fraction=', &
    balance_result%numerical%target_response_failure_fraction
  WRITE(*,'(A,ES24.16)') 'geostrophic_background_rms=', &
    balance_result%numerical%geostrophic_background_rms
  WRITE(*,'(A,ES24.16)') 'geostrophic_candidate_rms=', &
    balance_result%numerical%geostrophic_candidate_rms
  WRITE(*,'(A,ES24.16)') 'divergent_increment_rms=', &
    balance_result%numerical%divergent_rms
  WRITE(*,'(A,ES24.16)') 'rotational_increment_rms=', &
    balance_result%numerical%rotational_rms
  WRITE(*,'(A,I0)') 'changed_cells=',COUNT(balance_result%changed)
  WRITE(*,'(A,I0)') 'outside_support_changed_cells=', &
    outside_support_changes(work,candidate)
  WRITE(*,'(A,L1)') 'operational_state_unchanged=', &
    canonical_states_equal(operational,operational_snapshot)

  IF (balance_result%status/=STATUS_OK .OR. &
      balance_result%numerical%solver_reason/=SOLVER_CONVERGED .OR. &
      balance_result%numerical%solver_iterations<=0 .OR. &
      balance_result%numerical%max_omega_increment<1.0e-3_real64 .OR. &
      .NOT.ANY(balance_result%changed) .OR. outside_support_changes(work,candidate)/=0) &
    ERROR STOP 'real-geometry manufactured balance failed'
  IF (.NOT.canonical_states_equal(operational,operational_snapshot)) &
    ERROR STOP 'numerical test mutated the operational input'

CONTAINS

  SUBROUTINE install_manufactured_target(state,amplitude,seed_i,seed_j,status)
    TYPE(cloud_bal_state_type), INTENT(INOUT) :: state
    REAL(real64), INTENT(IN) :: amplitude
    INTEGER, INTENT(OUT) :: seed_i,seed_j,status
    INTEGER :: i,j,k,nx,ny,nz
    REAL(real64) :: distance,best_distance,radius,horizontal_weight,vertical_weight
    INTEGER :: k_bottom,nactive

    status=STATUS_FAILED
    nx=state%grid%nx; ny=state%grid%ny; nz=state%grid%nz
    seed_i=0; seed_j=0; best_distance=HUGE(1.0_real64)
    DO j=6,ny-5; DO i=6,nx-5
      IF (.NOT.ANY(state%hydro_support(i,j,:)>0_int32)) CYCLE
      IF (COUNT(state%above_ground(i,j,:))<6) CYCLE
      distance=REAL(i-(nx+1)/2,real64)**2+REAL(j-(ny+1)/2,real64)**2
      IF (distance<best_distance) THEN
        best_distance=distance; seed_i=i; seed_j=j
      END IF
    END DO; END DO
    IF (seed_i==0) RETURN

    state%omega_target%value=state%omega%value
    state%omega_target%valid=.FALSE.
    state%omega_target%quality=QUALITY_RAW_MISSING
    state%omega_target%source=0_int32
    state%balance_beta=0.0_real32
    DO j=MAX(1,seed_j-5),MIN(ny,seed_j+5)
      DO i=MAX(1,seed_i-5),MIN(nx,seed_i+5)
        radius=SQRT(REAL((i-seed_i)**2+(j-seed_j)**2,real64))/5.0_real64
        IF (radius>=1.0_real64) CYCLE
        horizontal_weight=(1.0_real64-radius)**4*(1.0_real64+4.0_real64*radius)
        WHERE(state%above_ground(i,j,:)) &
          state%balance_beta(i,j,:)=REAL(horizontal_weight,real32)
      END DO
    END DO
    i=seed_i; j=seed_j
    k_bottom=FINDLOC(state%above_ground(i,j,:),.TRUE.,DIM=1)
    nactive=COUNT(state%above_ground(i,j,:))
    IF (k_bottom==0 .OR. nactive<2) RETURN
    DO k=k_bottom,nz
      IF (.NOT.state%above_ground(i,j,k)) CYCLE
      vertical_weight=SIN(ACOS(-1.0_real64)* &
        (REAL(k-k_bottom,real64)+0.5_real64)/REAL(nactive,real64))
      IF (vertical_weight<0.25_real64) CYCLE
      state%omega_target%value(i,j,k)=REAL( &
        REAL(state%omega%value(i,j,k),real64)+amplitude*vertical_weight,real32)
      state%omega_target%valid(i,j,k)=.TRUE.
      state%omega_target%quality(i,j,k)=0_int32
      state%omega_target%source(i,j,k)= &
        IOR(SOURCE_DYNAMIC_TARGET,SOURCE_MANUFACTURED_TEST)
      state%balance_beta(i,j,k)=1.0_real32
    END DO
    status=STATUS_OK
  END SUBROUTINE install_manufactured_target

  SUBROUTINE compute_residual_fields( &
      background,balanced,config,op,r_background,r_candidate,r_proposed, &
      r_projected,status)
    TYPE(cloud_bal_state_type), INTENT(IN) :: background,balanced
    TYPE(balance_operator_config), INTENT(IN) :: config
    TYPE(balance_operator_type), INTENT(OUT) :: op
    REAL(real64), ALLOCATABLE, INTENT(OUT) :: r_background(:,:,:)
    REAL(real64), ALLOCATABLE, INTENT(OUT) :: r_candidate(:,:,:)
    REAL(real64), ALLOCATABLE, INTENT(OUT) :: r_proposed(:,:,:)
    REAL(real64), ALLOCATABLE, INTENT(OUT) :: r_projected(:,:,:)
    INTEGER, INTENT(OUT) :: status
    REAL(real64), ALLOCATABLE :: du(:,:,:),dv(:,:,:),domega(:,:,:),zero(:,:,:)
    INTEGER :: reason,nx,ny,nz

    status=STATUS_FAILED
    nx=background%grid%nx; ny=background%grid%ny; nz=background%grid%nz
    CALL build_balance_operator(background,config,op,status,reason)
    IF (status/=STATUS_OK) RETURN
    ALLOCATE(r_background(nx,ny,nz),r_candidate(nx,ny,nz), &
      r_proposed(nx,ny,nz),r_projected(nx,ny,nz),du(nx,ny,nz),dv(nx,ny,nz), &
      domega(nx,ny,nz),zero(nx,ny,nz))
    CALL state_continuity_residual(op,background,r_background,status)
    IF (status/=STATUS_OK) RETURN
    CALL state_continuity_residual(op,balanced,r_candidate,status)
    IF (status/=STATUS_OK) RETURN
    zero=0.0_real64; domega=0.0_real64
    WHERE(background%omega_target%valid)
      domega=REAL(background%omega_target%value,real64)- &
             REAL(background%omega%value,real64)
    END WHERE
    CALL apply_continuity_operator(op,zero,zero,domega,r_proposed,status)
    IF (status/=STATUS_OK) RETURN
    du=REAL(balanced%u%value,real64)-REAL(background%u%value,real64)
    dv=REAL(balanced%v%value,real64)-REAL(background%v%value,real64)
    domega=REAL(balanced%omega%value,real64)-REAL(background%omega%value,real64)
    CALL apply_continuity_operator(op,du,dv,domega,r_projected,status)
  END SUBROUTINE compute_residual_fields

  INTEGER FUNCTION outside_support_changes(background,balanced)
    TYPE(cloud_bal_state_type), INTENT(IN) :: background,balanced
    INTEGER :: i,j,k
    outside_support_changes=0
    DO k=1,background%grid%nz; DO j=1,background%grid%ny
      DO i=1,background%grid%nx
        IF (background%balance_beta(i,j,k)>0.0_real32) CYCLE
        IF (TRANSFER(background%u%value(i,j,k),0_int32)/= &
            TRANSFER(balanced%u%value(i,j,k),0_int32) .OR. &
            TRANSFER(background%v%value(i,j,k),0_int32)/= &
            TRANSFER(balanced%v%value(i,j,k),0_int32) .OR. &
            TRANSFER(background%omega%value(i,j,k),0_int32)/= &
            TRANSFER(balanced%omega%value(i,j,k),0_int32)) &
          outside_support_changes=outside_support_changes+1
      END DO
    END DO; END DO
  END FUNCTION outside_support_changes

  SUBROUTINE write_test_diagnostics( &
      path,original,background,balanced,longitude,result,r_background, &
      r_candidate,r_proposed,r_projected,status)
    CHARACTER(LEN=*), INTENT(IN) :: path
    TYPE(cloud_bal_state_type), INTENT(IN) :: original,background,balanced
    REAL(real32), INTENT(IN) :: longitude(:,:)
    TYPE(stage_result), INTENT(IN) :: result
    REAL(real64), INTENT(IN) :: r_background(:,:,:),r_candidate(:,:,:)
    REAL(real64), INTENT(IN) :: r_proposed(:,:,:),r_projected(:,:,:)
    INTEGER, INTENT(OUT) :: status
    INTEGER :: ncid,xdim,ydim,zdim,xy(2),xyz(3),rc
    INTEGER :: pressure_var,latitude_var,longitude_var,top_var,bottom_var
    INTEGER :: varid(18),i
    INTEGER :: residual_var(4)
    INTEGER(int32), ALLOCATABLE :: mask(:,:,:)
    REAL(real32), ALLOCATABLE :: original_hydrometeor(:,:,:)
    REAL(real32), ALLOCATABLE :: proposal_hydrometeor(:,:,:)
    CHARACTER(LEN=32), PARAMETER :: names(18)=[CHARACTER(LEN=32) :: &
      'background_u','background_v','background_omega', &
      'candidate_u','candidate_v','candidate_omega','omega_target', &
      'balance_beta','original_total_hydrometeor','proposal_total_hydrometeor', &
      'radar_dbz','original_dry_air_mass','proposal_dry_air_mass', &
      'above_ground','changed','omega_target_valid','hydro_support', &
      'omega_target_source']
    CHARACTER(LEN=16), PARAMETER :: units(18)=[CHARACTER(LEN=16) :: &
      'm s-1','m s-1','Pa s-1','m s-1','m s-1','Pa s-1','Pa s-1', &
      '1','kg kg-1 dryair','kg kg-1 dryair','dBZ','kg','kg','1','1','1','1','1']
    CHARACTER(LEN=32), PARAMETER :: residual_names(4)=[CHARACTER(LEN=32) :: &
      'continuity_background','continuity_candidate', &
      'continuity_proposed_increment','continuity_projected_increment']

    status=STATUS_FAILED
    ALLOCATE(mask(background%grid%nx,background%grid%ny,background%grid%nz), &
      original_hydrometeor(background%grid%nx,background%grid%ny,background%grid%nz), &
      proposal_hydrometeor(background%grid%nx,background%grid%ny,background%grid%nz))
    original_hydrometeor=original%cloud_water%value+original%cloud_ice%value+ &
      original%rain%value+original%snow%value+original%graupel%value
    proposal_hydrometeor=background%cloud_water%value+background%cloud_ice%value+ &
      background%rain%value+background%snow%value+background%graupel%value
    rc=nf90_create(TRIM(path),IOR(NF90_CLOBBER,NF90_64BIT_OFFSET),ncid)
    IF (rc/=NF90_NOERR) RETURN
    IF (nf90_def_dim(ncid,'x',background%grid%nx,xdim)/=NF90_NOERR .OR. &
        nf90_def_dim(ncid,'y',background%grid%ny,ydim)/=NF90_NOERR .OR. &
        nf90_def_dim(ncid,'z',background%grid%nz,zdim)/=NF90_NOERR) GOTO 900
    xy=[xdim,ydim]; xyz=[xdim,ydim,zdim]
    IF (nf90_def_var(ncid,'pressure',NF90_FLOAT,[zdim],pressure_var)/=NF90_NOERR .OR. &
        nf90_def_var(ncid,'latitude',NF90_FLOAT,xy,latitude_var)/=NF90_NOERR .OR. &
        nf90_def_var(ncid,'longitude',NF90_FLOAT,xy,longitude_var)/=NF90_NOERR .OR. &
        nf90_def_var(ncid,'omega_top_boundary',NF90_FLOAT,xy,top_var)/=NF90_NOERR .OR. &
        nf90_def_var(ncid,'omega_bottom_boundary',NF90_FLOAT,xy,bottom_var)/=NF90_NOERR) &
      GOTO 900
    IF (nf90_put_att(ncid,pressure_var,'units','Pa')/=NF90_NOERR .OR. &
        nf90_put_att(ncid,top_var,'units','Pa s-1')/=NF90_NOERR .OR. &
        nf90_put_att(ncid,bottom_var,'units','Pa s-1')/=NF90_NOERR) GOTO 900
    DO i=1,SIZE(names)
      IF (nf90_def_var(ncid,TRIM(names(i)), &
          MERGE(NF90_INT,NF90_FLOAT,i>=14),xyz,varid(i))/=NF90_NOERR) GOTO 900
      IF (nf90_put_att(ncid,varid(i),'units',TRIM(units(i)))/=NF90_NOERR) GOTO 900
    END DO
    DO i=1,SIZE(residual_names)
      IF (nf90_def_var(ncid,TRIM(residual_names(i)),NF90_FLOAT,xyz, &
          residual_var(i))/=NF90_NOERR .OR. &
          nf90_put_att(ncid,residual_var(i),'units','s-1')/=NF90_NOERR) GOTO 900
    END DO
    IF (nf90_put_att(ncid,NF90_GLOBAL,'evidence_authority', &
        'NUMERICAL_REAL_GEOMETRY_ONLY')/=NF90_NOERR .OR. &
        nf90_put_att(ncid,NF90_GLOBAL,'science_authority','NONE')/=NF90_NOERR .OR. &
        nf90_put_att(ncid,NF90_GLOBAL,'balance_scope', &
          'TARGET_INCREMENT_PROJECTION_ONLY')/=NF90_NOERR .OR. &
        nf90_put_att(ncid,NF90_GLOBAL,'target_kind','MANUFACTURED_TEST')/=NF90_NOERR .OR. &
        nf90_put_att(ncid,NF90_GLOBAL,'boundary_authority', &
          'MANUFACTURED_TEST_ONLY')/=NF90_NOERR .OR. &
        nf90_put_att(ncid,NF90_GLOBAL,'boundary_driver', &
          'MODEL_FSF_PS_TENDENCY_ADVECTION')/=NF90_NOERR .OR. &
        nf90_put_att(ncid,NF90_GLOBAL,'surface_wind_frame', &
          'UNRESOLVED_NATIVE')/=NF90_NOERR .OR. &
        nf90_put_att(ncid,NF90_GLOBAL,'target_amplitude_pas',0.02_real64)/=NF90_NOERR .OR. &
        nf90_put_att(ncid,NF90_GLOBAL,'kappa_omega', &
          balance_config%kappa_omega)/=NF90_NOERR .OR. &
        nf90_put_att(ncid,NF90_GLOBAL,'minimum_beta', &
          balance_config%minimum_beta)/=NF90_NOERR .OR. &
        nf90_put_att(ncid,NF90_GLOBAL,'solver_residual_fraction', &
          balance_config%solver_residual_fraction)/=NF90_NOERR .OR. &
        nf90_put_att(ncid,NF90_GLOBAL,'minimum_target_response_ratio', &
          balance_config%minimum_target_response_ratio)/=NF90_NOERR .OR. &
        nf90_put_att(ncid,NF90_GLOBAL,'maximum_target_response_failure_fraction', &
          balance_config%maximum_target_response_failure_fraction)/=NF90_NOERR .OR. &
        nf90_put_att(ncid,NF90_GLOBAL,'target_source_bits', &
          IOR(SOURCE_DYNAMIC_TARGET,SOURCE_MANUFACTURED_TEST))/=NF90_NOERR .OR. &
        nf90_put_att(ncid,NF90_GLOBAL,'target_quality_bits',0_int32)/=NF90_NOERR .OR. &
        nf90_put_att(ncid,NF90_GLOBAL,'boundary_source_bits', &
          IOR(SOURCE_BOUNDARY_CONDITION,SOURCE_MANUFACTURED_TEST))/=NF90_NOERR .OR. &
        nf90_put_att(ncid,NF90_GLOBAL,'boundary_quality_bits',0_int32)/=NF90_NOERR .OR. &
        nf90_put_att(ncid,NF90_GLOBAL,'forecast_wave_response_assessed',0)/=NF90_NOERR .OR. &
        nf90_put_att(ncid,NF90_GLOBAL,'wave_proxy_scope', &
          'NEIGHBOR_JUMP_ENGINEERING_GUARD_ONLY')/=NF90_NOERR .OR. &
        nf90_put_att(ncid,NF90_GLOBAL,'balance_status',result%status)/=NF90_NOERR .OR. &
        nf90_put_att(ncid,NF90_GLOBAL,'solver_iterations', &
                     result%numerical%solver_iterations)/=NF90_NOERR .OR. &
        nf90_put_att(ncid,NF90_GLOBAL,'acceptance_failures', &
                     result%numerical%acceptance_failures)/=NF90_NOERR) GOTO 900
    IF (nf90_enddef(ncid)/=NF90_NOERR) GOTO 900
    IF (nf90_put_var(ncid,pressure_var,background%pressure%value(1,1,:))/=NF90_NOERR .OR. &
        nf90_put_var(ncid,latitude_var,background%latitude%value)/=NF90_NOERR .OR. &
        nf90_put_var(ncid,longitude_var,longitude)/=NF90_NOERR .OR. &
        nf90_put_var(ncid,top_var,background%omega_top_boundary%value)/=NF90_NOERR .OR. &
        nf90_put_var(ncid,bottom_var,background%omega_bottom_boundary%value)/=NF90_NOERR) &
      GOTO 900
    IF (nf90_put_var(ncid,varid(1),background%u%value)/=NF90_NOERR .OR. &
        nf90_put_var(ncid,varid(2),background%v%value)/=NF90_NOERR .OR. &
        nf90_put_var(ncid,varid(3),background%omega%value)/=NF90_NOERR .OR. &
        nf90_put_var(ncid,varid(4),balanced%u%value)/=NF90_NOERR .OR. &
        nf90_put_var(ncid,varid(5),balanced%v%value)/=NF90_NOERR .OR. &
        nf90_put_var(ncid,varid(6),balanced%omega%value)/=NF90_NOERR .OR. &
        nf90_put_var(ncid,varid(7),background%omega_target%value)/=NF90_NOERR .OR. &
        nf90_put_var(ncid,varid(8),background%balance_beta)/=NF90_NOERR .OR. &
        nf90_put_var(ncid,varid(9),original_hydrometeor)/=NF90_NOERR .OR. &
        nf90_put_var(ncid,varid(10),proposal_hydrometeor)/=NF90_NOERR .OR. &
        nf90_put_var(ncid,varid(11),background%radar_reflectivity%value)/=NF90_NOERR .OR. &
        nf90_put_var(ncid,varid(12),original%grid%dry_air_mass_measure)/=NF90_NOERR .OR. &
        nf90_put_var(ncid,varid(13),background%grid%dry_air_mass_measure)/=NF90_NOERR) &
      GOTO 900
    mask=MERGE(1_int32,0_int32,background%above_ground)
    IF (nf90_put_var(ncid,varid(14),mask)/=NF90_NOERR) GOTO 900
    mask=MERGE(1_int32,0_int32,result%changed)
    IF (nf90_put_var(ncid,varid(15),mask)/=NF90_NOERR) GOTO 900
    mask=MERGE(1_int32,0_int32,background%omega_target%valid)
    IF (nf90_put_var(ncid,varid(16),mask)/=NF90_NOERR) GOTO 900
    IF (nf90_put_var(ncid,varid(17),background%hydro_support)/=NF90_NOERR .OR. &
        nf90_put_var(ncid,varid(18),background%omega_target%source)/=NF90_NOERR) GOTO 900
    IF (nf90_put_var(ncid,residual_var(1),r_background)/=NF90_NOERR .OR. &
        nf90_put_var(ncid,residual_var(2),r_candidate)/=NF90_NOERR .OR. &
        nf90_put_var(ncid,residual_var(3),r_proposed)/=NF90_NOERR .OR. &
        nf90_put_var(ncid,residual_var(4),r_projected)/=NF90_NOERR) GOTO 900
    IF (nf90_close(ncid)/=NF90_NOERR) RETURN
    status=STATUS_OK
    RETURN
900 CONTINUE
    rc=nf90_close(ncid)
  END SUBROUTINE write_test_diagnostics

END PROGRAM real_manufactured_balance_driver
