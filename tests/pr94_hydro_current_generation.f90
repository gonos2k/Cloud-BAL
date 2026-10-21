PROGRAM pr94_hydro_current_generation
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32,int64
  USE netcdf
  USE cloud_bal_state
  USE cloud_bal_column_physics, ONLY: SATURATION_LIQUID
  USE cloud_bal_pipeline, ONLY: cloud_bal_pipeline_config,cloud_bal_pipeline_result, &
    run_cloud_bal_pipeline,MODE_SHADOW
  USE cloud_bal_balance_operator, ONLY: balance_operator_type,build_diagnostic_balance_operator, &
    state_continuity_residual
  USE cloud_bal_real_netcdf, ONLY: read_real_shadow_state,write_shadow_diagnostics
  IMPLICIT NONE

  INTEGER(int64), PARAMETER :: VALID_TIME=1786885200_int64
  REAL(real64), PARAMETER :: TARGET_RH=1.0_real64
  TYPE(cloud_bal_state_type) :: background,candidate,operational
  TYPE(cloud_bal_pipeline_config) :: config
  TYPE(cloud_bal_pipeline_result) :: result
  TYPE(balance_operator_type) :: operator_before,operator_after
  REAL(real32), ALLOCATABLE :: longitude(:,:)
  REAL(real64), ALLOCATABLE :: residual_before(:,:,:),residual_after(:,:,:)
  INTEGER(int32), ALLOCATABLE :: int3(:,:,:)
  INTEGER, ALLOCATABLE :: thermo_surface(:,:,:),phi_reference(:,:)
  LOGICAL, ALLOCATABLE :: analysis_support(:,:,:),thermo_support(:,:,:),phi_support(:,:,:)
  CHARACTER(LEN=2048) :: arg(15)
  INTEGER :: i,nx,ny,nz,ncid,status,reason,writer_status

  IF (COMMAND_ARGUMENT_COUNT()/=15) ERROR STOP &
    'usage: pr94-hydro-current FUA FSF LW3 VRZ VRT STATIC LT1 LQ3 LWC LSX LCP LTY EPOCH COUPLED.nc OUTPUT.nc'
  DO i=1,15
    CALL GET_COMMAND_ARGUMENT(i,arg(i))
  END DO
  READ(arg(13),*) status
  IF (status/=VALID_TIME) ERROR STOP 'retained input epoch differs from pinned PR81 input'
  CALL read_real_shadow_state(TRIM(arg(1)),TRIM(arg(2)),TRIM(arg(3)),TRIM(arg(4)), &
    TRIM(arg(5)),TRIM(arg(6)),VALID_TIME,background,longitude,status,reason, &
    lt1_path=TRIM(arg(7)),lq3_path=TRIM(arg(8)),lwc_path=TRIM(arg(9)), &
    lsx_path=TRIM(arg(10)),lcp_path=TRIM(arg(11)),lty_path=TRIM(arg(12)))
  IF (status/=STATUS_OK) ERROR STOP 'same13 pinned producer background reader failed'
  nx=background%grid%nx; ny=background%grid%ny; nz=background%grid%nz
  ALLOCATE(int3(nx,ny,nz),thermo_surface(nx,ny,nz),phi_reference(nx,ny), &
    analysis_support(nx,ny,nz),thermo_support(nx,ny,nz),phi_support(nx,ny,nz), &
    residual_before(nx,ny,nz),residual_after(nx,ny,nz))
  CALL nc_open_checked(TRIM(arg(14)),ncid)
  CALL read_mask(ncid,'analysis_support',analysis_support,int3)
  CALL read_mask(ncid,'thermo_support',thermo_support,int3)
  CALL read_mask(ncid,'geopotential_support',phi_support,int3)
  CALL read_i3(ncid,'thermo_surface',thermo_surface)
  CALL read_i2(ncid,'geopotential_reference_level',phi_reference)
  IF (nf90_close(ncid)/=NF90_NOERR) ERROR STOP 'cannot close retained PR81 source candidate'
  IF (COUNT(analysis_support)/=162 .OR. COUNT(thermo_support)/=69 .OR. &
      COUNT(phi_support)/=180) ERROR STOP 'retained PR81 analysis support changed'
  IF (ANY(thermo_surface/=SATURATION_LIQUID)) ERROR STOP 'retained thermo surface is not liquid'
  IF (ANY(thermo_support .AND. .NOT.analysis_support) .OR. &
      ANY(thermo_support .AND. .NOT.phi_support)) ERROR STOP 'thermo support differs from PR81 contract'

  CALL configure_hydro(config)
  CALL run_cloud_bal_pipeline(background,candidate,operational,result,config, &
    thermo_active=thermo_support,thermo_surface=thermo_surface,target_rh=TARGET_RH, &
    geopotential_support=phi_support,geopotential_reference_level=phi_reference, &
    analysis_support=analysis_support)
  IF (result%status/=STATUS_OK .OR. .NOT.result%thermo_density_prior_applied) THEN
    WRITE(*,'(A,I0,A,I0)') 'pipeline_status=',result%status,',reason=',result%reason_code
    ERROR STOP 'current-generation HYDRO pipeline failed'
  END IF
  IF (result%force_prior_applied .OR. config%force_prior_enabled .OR. &
      config%background_continuity_prior) ERROR STOP 'HYDRO mode unexpectedly enabled a wind prior'
  IF (ANY(candidate%u%value/=background%u%value) .OR. &
      ANY(candidate%v%value/=background%v%value) .OR. &
      ANY(candidate%omega%value/=background%omega%value)) &
    ERROR STOP 'current-generation HYDRO changed U, V, or omega'
  IF (COUNT(result%thermo_support)/=69 .OR. COUNT(result%geopotential_support)/=180) &
    ERROR STOP 'current-generation HYDRO changed the frozen thermo/Phi supports'
  IF (result%force_prior%status/=STATUS_FAILED .OR. result%force_prior_applied) &
    ERROR STOP 'current-generation HYDRO force stage did not remain disabled'

  CALL build_diagnostic_balance_operator(background,operator_before,status,reason)
  IF (status/=STATUS_OK) ERROR STOP 'background diagnostic operator failed'
  CALL state_continuity_residual(operator_before,background,residual_before,status)
  IF (status/=STATUS_OK) ERROR STOP 'background continuity diagnostic failed'
  CALL build_diagnostic_balance_operator(candidate,operator_after,status,reason)
  IF (status/=STATUS_OK) ERROR STOP 'candidate diagnostic operator failed'
  CALL state_continuity_residual(operator_after,candidate,residual_after,status)
  IF (status/=STATUS_OK) ERROR STOP 'candidate continuity diagnostic failed'
  CALL write_shadow_diagnostics(TRIM(arg(15)),background,candidate,longitude,result,config, &
    residual_before,residual_after,writer_status,operational,pressure_analysis_candidate=.TRUE.)
  IF (writer_status/=STATUS_OK) ERROR STOP 'current-generation HYDRO candidate writer failed'
  WRITE(*,'(A)') 'status=PASS_PR94_CURRENT_GENERATION_HYDRO'
  WRITE(*,'(A)') 'generation=PR81 joint thermo/density/Phi producer; balance and force stages disabled'
  WRITE(*,'(A)') 'wind_state_unchanged=T'
  WRITE(*,'(A)') 'science_authority=NONE'

CONTAINS

  SUBROUTINE configure_hydro(pipeline_config)
    TYPE(cloud_bal_pipeline_config), INTENT(OUT) :: pipeline_config
    pipeline_config%requested_mode=MODE_SHADOW
    pipeline_config%maximum_outer_iterations=8
    pipeline_config%column%transport_precipitation=.FALSE.
    pipeline_config%background_continuity_prior=.FALSE.
    pipeline_config%balance%maximum_wind_increment=10.0_real64
    pipeline_config%balance%maximum_omega_increment=5.0_real64
    pipeline_config%balance%increment_headroom=0.95_real64
    pipeline_config%balance%solver_residual_fraction=1.0e-3_real64
    pipeline_config%force_prior_enabled=.FALSE.
    pipeline_config%thermo_density_prior%enabled=.TRUE.
    pipeline_config%thermo_density_prior%background_weight=0.5_real64
    pipeline_config%thermo_density_prior%max_temperature_increment=5.0_real64
    pipeline_config%thermo_density_prior%max_vapor_increment=0.005_real64
  END SUBROUTINE configure_hydro

  SUBROUTINE nc_open_checked(path,id)
    CHARACTER(LEN=*),INTENT(IN)::path
    INTEGER,INTENT(OUT)::id
    IF(nf90_open(TRIM(path),NF90_NOWRITE,id)/=NF90_NOERR) ERROR STOP 'cannot open retained PR81 source candidate'
  END SUBROUTINE nc_open_checked

  INTEGER FUNCTION var_id(id,name)
    INTEGER,INTENT(IN)::id
    CHARACTER(LEN=*),INTENT(IN)::name
    IF(nf90_inq_varid(id,TRIM(name),var_id)/=NF90_NOERR) ERROR STOP 'missing PR81 support variable'
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
      IF(rc/=NF90_NOERR) ERROR STOP 'failed retained PR81 support read'
      data(:,:,k)=level(:,:,1)
    END DO
  END SUBROUTINE read_i3

  SUBROUTINE read_i2(id,name,data)
    INTEGER,INTENT(IN)::id
    CHARACTER(LEN=*),INTENT(IN)::name
    INTEGER,INTENT(OUT)::data(:,:)
    IF(nf90_get_var(id,var_id(id,name),data)/=NF90_NOERR) ERROR STOP 'failed PR81 2D support read'
  END SUBROUTINE read_i2

  SUBROUTINE read_mask(id,name,mask,integer_scratch)
    INTEGER,INTENT(IN)::id
    CHARACTER(LEN=*),INTENT(IN)::name
    LOGICAL,INTENT(OUT)::mask(:,:,:)
    INTEGER(int32),INTENT(INOUT)::integer_scratch(:,:,:)
    CALL read_i3(id,name,integer_scratch)
    IF(ANY((integer_scratch/=0_int32).AND.(integer_scratch/=1_int32))) &
      ERROR STOP 'PR81 support mask is not binary'
    mask=integer_scratch==1_int32
  END SUBROUTINE read_mask

END PROGRAM pr94_hydro_current_generation
