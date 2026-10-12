PROGRAM pr80_force_retained
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32,int64
  USE netcdf
  USE cloud_bal_state
  USE cloud_bal_column_physics, ONLY: SATURATION_LIQUID
  USE cloud_bal_pipeline, ONLY: cloud_bal_pipeline_config,cloud_bal_pipeline_result, &
    run_cloud_bal_pipeline,MODE_SHADOW
  USE cloud_bal_balance_operator, ONLY: balance_operator_config,force_prior_diagnostics, &
    apply_background_force_prior_refinement,state_dry_air_mass_flux_divergence, &
    build_diagnostic_balance_operator,balance_operator_type,geostrophic_residual, &
    state_continuity_residual
  USE cloud_bal_real_netcdf, ONLY: read_real_shadow_state,write_shadow_diagnostics, &
    pipeline_result_replays
  IMPLICIT NONE

  REAL(real64), PARAMETER :: ORIGINAL_RMS=1.0152186264544263e-7_real64
  REAL(real64), PARAMETER :: ORIGINAL_MAX=7.2467128524046317e-7_real64
  INTEGER(int64), PARAMETER :: VALID_TIME=1786885200_int64
  TYPE(cloud_bal_state_type) :: background,input,refined
  TYPE(cloud_bal_state_type) :: pipeline_candidate,pipeline_operational
  TYPE(balance_operator_config) :: config
  TYPE(cloud_bal_pipeline_config) :: pipeline_config
  TYPE(cloud_bal_pipeline_result) :: pipeline_result
  TYPE(force_prior_diagnostics) :: diag
  TYPE(balance_operator_type) :: diagnostic_op
  REAL(real32), ALLOCATABLE :: longitude(:,:),real3(:,:,:),real2(:,:),pressure_1d(:)
  REAL(real64), ALLOCATABLE :: real64_3(:,:,:),flux_bg(:,:,:),flux_in(:,:,:),flux_refined(:,:,:)
  REAL(real64), ALLOCATABLE :: residual_before(:,:,:),residual_after(:,:,:)
  INTEGER(int32), ALLOCATABLE :: int3(:,:,:)
  LOGICAL, ALLOCATABLE :: control(:,:,:),shell(:,:,:),force(:,:,:),geometry_mask(:,:,:)
  LOGICAL, ALLOCATABLE :: material_support(:,:,:),phi_support(:,:,:)
  LOGICAL, ALLOCATABLE :: thermo_support(:,:,:)
  INTEGER, ALLOCATABLE :: thermo_surface(:,:,:),geopotential_reference_level(:,:)
  CHARACTER(LEN=2048) :: arg(15),nc_path,output_path,summary_path,pipeline_nc_path
  INTEGER :: i,j,bottom,ncid,status,reason,nx,ny,nz,ios,writer_status
  REAL(real64) :: original_rms_nc,original_max_nc,force_before_dry_rms,force_after_dry_rms
  REAL(real64) :: dry_increment_rms,dry_increment_max,geo_before_rms,geo_after_rms
  REAL(real64) :: refined_dry_rms,refined_dry_max,geo_refined_rms
  REAL(real64) :: wind_before_max,omega_before_max
  INTEGER :: changed_u,changed_v,geo_status

  IF (COMMAND_ARGUMENT_COUNT()/=15) ERROR STOP &
    'usage: pr80-force-retained FUA FSF LW3 VRZ VRT STATIC LT1 LQ3 LWC LSX LCP LTY EPOCH COUPLED.nc OUTPUT_PREFIX'
  DO i=1,15
    CALL GET_COMMAND_ARGUMENT(i,arg(i))
  END DO
  READ(arg(13),*) status
  IF (status/=VALID_TIME) ERROR STOP 'retained input epoch differs from pinned CP06-A'
  nc_path=TRIM(arg(14)); output_path=TRIM(arg(15))
  summary_path=TRIM(arg(15))//'.summary.txt'
  pipeline_nc_path=TRIM(arg(15))//'.pipeline.nc'

  CALL read_real_shadow_state(TRIM(arg(1)),TRIM(arg(2)),TRIM(arg(3)),TRIM(arg(4)), &
    TRIM(arg(5)),TRIM(arg(6)),VALID_TIME,background,longitude,status,reason, &
    lt1_path=TRIM(arg(7)),lq3_path=TRIM(arg(8)),lwc_path=TRIM(arg(9)), &
    lsx_path=TRIM(arg(10)),lcp_path=TRIM(arg(11)),lty_path=TRIM(arg(12)))
  IF (status/=STATUS_OK) THEN
    WRITE(*,'(A,I0,A,I0)') 'reader_status=',status,',reason=',reason
    ERROR STOP 'template background reader failed'
  END IF
  nx=background%grid%nx; ny=background%grid%ny; nz=background%grid%nz
  ALLOCATE(real3(nx,ny,nz),real64_3(nx,ny,nz),int3(nx,ny,nz),real2(nx,ny), &
    control(nx,ny,nz),shell(nx,ny,nz),force(nx,ny,nz),geometry_mask(nx,ny,nz), &
    material_support(nx,ny,nz),phi_support(nx,ny,nz),thermo_support(nx,ny,nz), &
    thermo_surface(nx,ny,nz),geopotential_reference_level(nx,ny),pressure_1d(nz), &
    flux_bg(nx,ny,nz),flux_in(nx,ny,nz),flux_refined(nx,ny,nz), &
    residual_before(nx,ny,nz),residual_after(nx,ny,nz))
  CALL nc_open_checked(TRIM(nc_path),ncid)
  CALL assert_dims(ncid,nx,ny,nz)
  CALL compare_r3(ncid,'background_u','m s-1',background%u%value)
  CALL compare_r3(ncid,'background_v','m s-1',background%v%value)
  CALL compare_r3(ncid,'background_omega','Pa s-1',background%omega%value)
  CALL compare_r3(ncid,'background_temperature','K',background%temperature%value)
  CALL compare_r3(ncid,'background_vapor','kg kg-1 dryair',background%vapor%value)
  CALL compare_r3(ncid,'background_cloud_water','kg kg-1 dryair',background%cloud_water%value)
  CALL compare_r3(ncid,'background_cloud_ice','kg kg-1 dryair',background%cloud_ice%value)
  CALL compare_r3(ncid,'background_rain','kg kg-1 dryair',background%rain%value)
  CALL compare_r3(ncid,'background_snow','kg kg-1 dryair',background%snow%value)
  CALL compare_r3(ncid,'background_graupel','kg kg-1 dryair',background%graupel%value)
  CALL compare_r3(ncid,'background_geopotential','m2 s-2',background%geopotential%value)
  CALL compare_pressure(ncid,background%pressure%value)
  CALL compare_r2(ncid,'latitude','degree_north',background%latitude%value)
  CALL compare_r2(ncid,'longitude','degree_east',longitude)
  CALL compare_r2(ncid,'surface_pressure','Pa',background%surface_pressure%value)
  CALL compare_i3(ncid,'above_ground',background%above_ground)
  CALL compare_r64_3(ncid,'pressure_mass_measure',background%grid%pressure_mass_measure)
  CALL compare_r64_3(ncid,'dry_air_mass_measure',background%grid%dry_air_mass_measure)
  CALL compare_r64_3(ncid,'cell_dp',background%grid%cell_dp)
  CALL compare_r64_3(ncid,'pressure_interface',background%grid%pressure_interface)
  CALL compare_r64_3(ncid,'level_spacing_dp',background%grid%level_spacing_dp)
  CALL compare_field3_metadata(ncid,'background_temperature',background%temperature)
  CALL compare_field3_metadata(ncid,'background_vapor',background%vapor)
  CALL compare_field3_metadata(ncid,'background_cloud_water',background%cloud_water)
  CALL compare_field3_metadata(ncid,'background_cloud_ice',background%cloud_ice)
  CALL compare_field3_metadata(ncid,'background_rain',background%rain)
  CALL compare_field3_metadata(ncid,'background_snow',background%snow)
  CALL compare_field3_metadata(ncid,'background_graupel',background%graupel)
  CALL compare_field3_metadata(ncid,'background_geopotential',background%geopotential)

  CALL read_global_real(ncid,'continuity_background_rms',original_rms_nc)
  CALL read_global_real(ncid,'continuity_background_max',original_max_nc)
  IF (original_rms_nc/=ORIGINAL_RMS .OR. original_max_nc/=ORIGINAL_MAX) &
    ERROR STOP 'frozen original continuity gate differs from retained candidate attributes'
  CALL read_mask(ncid,'background_control_support',control)
  CALL read_mask(ncid,'background_validation_shell',shell)
  CALL read_mask(ncid,'geostrophic_validation_support',force)
  CALL read_mask(ncid,'analysis_support',material_support)
  CALL read_mask(ncid,'geopotential_support',phi_support)
  CALL read_mask(ncid,'thermo_support',thermo_support)
  CALL read_i3(ncid,'thermo_surface',int3)
  thermo_surface=INT(int3)
  CALL read_i2(ncid,'geopotential_reference_level',geopotential_reference_level)
  IF (COUNT(control)/=500 .OR. COUNT(shell)/=980 .OR. COUNT(material_support)/=162 .OR. &
      COUNT(phi_support)/=180 .OR. COUNT(force)/=900 .OR. COUNT(thermo_support)/=69) &
    ERROR STOP 'retained control/shell/force mask counts changed'
  IF (ANY(thermo_surface/=SATURATION_LIQUID)) ERROR STOP 'retained thermo surface is not liquid saturation'
  DO j=1,ny; DO i=1,nx
    bottom=FINDLOC(background%above_ground(i,j,:),.TRUE.,DIM=1)
    IF (ANY(phi_support(i,j,:))) THEN
      IF (geopotential_reference_level(i,j)/=bottom) &
        ERROR STOP 'geopotential reference level differs from original first above-ground level'
    ELSE IF (geopotential_reference_level(i,j)/=0) THEN
      ERROR STOP 'unrequested geopotential column has a reference level'
    END IF
  END DO; END DO

  input=background
  ! The retained NetCDF writer exports wind values but omits their field
  ! validity/quality/source arrays. Reconstruct only the producer's explicit
  ! SOURCE_BALANCE_OPERATOR bit where a serialized U/V/omega value differs
  ! from the exact template background; all other field metadata remains
  ! reader-bound. This is source-derived lineage, not a NetCDF-authenticated
  ! metadata export.
  CALL read_r3(ncid,'candidate_u','m s-1',real3); input%u%value=real3
  WHERE(input%u%value/=background%u%value)
    input%u%source=IOR(background%u%source,SOURCE_BALANCE_OPERATOR)
  END WHERE
  CALL read_r3(ncid,'candidate_v','m s-1',real3); input%v%value=real3
  WHERE(input%v%value/=background%v%value)
    input%v%source=IOR(background%v%source,SOURCE_BALANCE_OPERATOR)
  END WHERE
  CALL read_r3(ncid,'candidate_omega','Pa s-1',real3); input%omega%value=real3
  WHERE(input%omega%value/=background%omega%value)
    input%omega%source=IOR(background%omega%source,SOURCE_BALANCE_OPERATOR)
  END WHERE
  CALL overlay_field(ncid,'candidate_temperature','K',input%temperature)
  CALL overlay_field(ncid,'candidate_vapor','kg kg-1 dryair',input%vapor)
  CALL overlay_field(ncid,'candidate_cloud_water','kg kg-1 dryair',input%cloud_water)
  CALL overlay_field(ncid,'candidate_cloud_ice','kg kg-1 dryair',input%cloud_ice)
  CALL overlay_field(ncid,'candidate_rain','kg kg-1 dryair',input%rain)
  CALL overlay_field(ncid,'candidate_snow','kg kg-1 dryair',input%snow)
  CALL overlay_field(ncid,'candidate_graupel','kg kg-1 dryair',input%graupel)
  CALL overlay_field(ncid,'candidate_geopotential','m2 s-2',input%geopotential)
  CALL read_r64_3(ncid,'candidate_dry_air_mass_measure',real64_3)
  input%grid%dry_air_mass_measure=real64_3
  CALL compare_r2(ncid,'candidate_surface_pressure','Pa',background%surface_pressure%value)
  CALL compare_r3(ncid,'omega_target','Pa s-1',background%omega_target%value)
  CALL compare_field3_metadata(ncid,'omega_target',background%omega_target)
  CALL compare_r3(ncid,'omega_target_sigma','Pa s-1',background%omega_target_sigma%value)
  CALL compare_field3_metadata(ncid,'omega_target_sigma',background%omega_target_sigma)
  CALL read_mask(ncid,'above_ground',geometry_mask)
  IF (ANY(geometry_mask .NEQV. background%above_ground)) ERROR STOP 'candidate geometry mask changed'
  CALL nc_close_checked(ncid)
  CALL validate_canonical_state(input,.FALSE.,.FALSE.,status,reason,.FALSE.)
  IF (status/=STATUS_OK) THEN
    WRITE(*,'(A,I0,A,I0)') 'candidate_validation_status=',status,',reason=',reason
    ERROR STOP 'overlaid retained candidate is not canonical'
  END IF

  config%maximum_wind_increment=10.0_real64
  config%maximum_omega_increment=5.0_real64
  config%increment_headroom=0.95_real64
  CALL build_diagnostic_balance_operator(background,diagnostic_op,status,reason)
  IF (status/=STATUS_OK) ERROR STOP 'force diagnostic operator could not be built'
  CALL state_dry_air_mass_flux_divergence(diagnostic_op,background,flux_bg,status)
  IF (status/=STATUS_OK) ERROR STOP 'background dry-flux divergence failed'
  CALL state_dry_air_mass_flux_divergence(diagnostic_op,input,flux_in,status)
  IF (status/=STATUS_OK) ERROR STOP 'input dry-flux divergence failed'
  CALL dry_flux_rms(flux_bg,background%grid%pressure_mass_measure,force,force_before_dry_rms)
  CALL dry_flux_rms(flux_in,background%grid%pressure_mass_measure,force,force_after_dry_rms)
  CALL dry_flux_increment_norm(flux_in,flux_bg,background%grid%pressure_mass_measure, &
    shell,dry_increment_rms,dry_increment_max)
  CALL geostrophic_residual(background,diagnostic_op,geo_before_rms,geo_status,force)
  IF (geo_status/=STATUS_OK) ERROR STOP 'background geostrophic diagnostic failed'
  CALL geostrophic_residual(input,diagnostic_op,geo_after_rms,geo_status,force)
  IF (geo_status/=STATUS_OK) ERROR STOP 'candidate geostrophic diagnostic failed'
  wind_before_max=MAXVAL(SQRT((REAL(input%u%value,real64)-REAL(background%u%value,real64))**2+ &
    (REAL(input%v%value,real64)-REAL(background%v%value,real64))**2),MASK=control)
  omega_before_max=MAXVAL(ABS(REAL(input%omega%value,real64)-REAL(background%omega%value,real64)))
  CALL apply_background_force_prior_refinement(background,input,refined,config,control,shell,force, &
    ORIGINAL_RMS,ORIGINAL_MAX,diag)
  WRITE(*,'(A,I0,A,I0)') 'refinement_status=',diag%status,',reason=',diag%reason
  WRITE(*,'(A,ES24.16)') 'input_objective=',diag%input_objective
  WRITE(*,'(A,ES24.16)') 'candidate_objective=',diag%candidate_objective
  WRITE(*,'(A,ES24.16)') 'background_force_rms=',diag%background_force_rms
  WRITE(*,'(A,ES24.16)') 'input_force_rms=',diag%input_force_rms
  WRITE(*,'(A,ES24.16)') 'candidate_force_rms=',diag%candidate_force_rms
  WRITE(*,'(A,ES24.16)') 'input_normalized_force_rms=',diag%input_normalized_force_rms
  WRITE(*,'(A,ES24.16)') 'candidate_normalized_force_rms=',diag%candidate_normalized_force_rms
  WRITE(*,'(A,ES24.16)') 'input_dry_flux_divergence_rms=',force_after_dry_rms
  WRITE(*,'(A,ES24.16)') 'background_dry_flux_divergence_rms=',force_before_dry_rms
  WRITE(*,'(A,ES24.16)') 'input_minus_background_dry_flux_rms_on_shell=',dry_increment_rms
  WRITE(*,'(A,ES24.16)') 'input_minus_background_dry_flux_max_on_shell=',dry_increment_max
  WRITE(*,'(A,ES24.16)') 'absolute_geostrophic_rms_before_on_900=',geo_after_rms
  WRITE(*,'(A,ES24.16)') 'absolute_geostrophic_rms_background_on_900=',geo_before_rms
  WRITE(*,'(A,ES24.16)') 'existing_wind_increment_max_ms_on_500=',wind_before_max
  WRITE(*,'(A,ES24.16)') 'existing_omega_increment_max_pas=',omega_before_max
  WRITE(*,'(A,ES24.16)') 'continuity_candidate_rms=',diag%continuity_candidate_rms
  WRITE(*,'(A,ES24.16)') 'continuity_candidate_max=',diag%continuity_candidate_max
  WRITE(*,'(A,ES24.16)') 'projected_increment_rms=',diag%projected_increment_rms
  WRITE(*,'(A,ES24.16)') 'projected_increment_max=',diag%projected_increment_max
  WRITE(*,'(A,ES24.16)') 'maximum_wind_increment_ms=',diag%maximum_wind_increment
    WRITE(*,'(A,ES24.16)') 'wind_cap_ms=',0.95_real64*MIN(10.0_real64,config%maximum_wind_increment)
  WRITE(*,'(A,ES24.16)') 'maximum_omega_increment_pas=',diag%maximum_omega_increment
  WRITE(*,'(A,I0)') 'projector_solver_iterations=',diag%solver_iterations
  WRITE(*,'(A,I0)') 'control_cells=',COUNT(control)
  WRITE(*,'(A,I0)') 'validation_shell_cells=',COUNT(shell)
  WRITE(*,'(A,I0)') 'material_support_cells=',COUNT(material_support)
  WRITE(*,'(A,I0)') 'geopotential_support_cells=',COUNT(phi_support)
  WRITE(*,'(A,I0)') 'force_support_cells=',COUNT(force)
  WRITE(*,'(A)') 'science_authority=NONE'
  WRITE(*,'(A)') 'artifact_scope=wind_component_probe_plus_full_producer_writer_roundtrip; diagnostic_only'

  IF (diag%status==STATUS_OK) THEN
    CALL assert_frozen_fields(input,refined)
    IF (ANY(refined%u%value .NE. input%u%value .AND. .NOT.control) .OR. &
        ANY(refined%v%value .NE. input%v%value .AND. .NOT.control)) &
      ERROR STOP 'force refinement changed wind outside control support'
    CALL assert_source_balance_bits(input,refined)
    CALL state_dry_air_mass_flux_divergence(diagnostic_op,refined,flux_refined,status)
    IF (status/=STATUS_OK) ERROR STOP 'refined-state dry-flux divergence failed'
    CALL dry_flux_increment_norm(flux_refined,flux_bg,background%grid%pressure_mass_measure, &
      shell,refined_dry_rms,refined_dry_max)
    CALL geostrophic_residual(refined,diagnostic_op,geo_refined_rms,geo_status,force)
    IF (geo_status/=STATUS_OK) ERROR STOP 'refined-state geostrophic diagnostic failed'
    changed_u=COUNT(refined%u%value/=input%u%value)
    changed_v=COUNT(refined%v%value/=input%v%value)
    CALL write_wind_artifact(TRIM(output_path),refined,diag)
    WRITE(*,'(A,I0,A,I0)') 'changed_u_cells=',changed_u,',changed_v_cells=',changed_v
    WRITE(*,'(A,ES24.16)') 'absolute_geostrophic_rms_after_on_900=',geo_refined_rms
    WRITE(*,'(A,ES24.16)') 'refined_minus_background_dry_flux_rms_on_shell=',refined_dry_rms
    WRITE(*,'(A,ES24.16)') 'refined_minus_background_dry_flux_max_on_shell=',refined_dry_max
    WRITE(*,'(A)') 'wind_artifact_written=T'
    CALL run_retained_full_pipeline()
  ELSE
    WRITE(*,'(A)') 'wind_artifact_written=F'
  END IF
  CALL write_summary(TRIM(summary_path),diag,force_before_dry_rms,force_after_dry_rms, &
    dry_increment_rms,dry_increment_max,geo_before_rms,geo_after_rms,wind_before_max,omega_before_max)
  WRITE(*,'(A)') 'schema=stream-v1; int32[nx,ny,nz]; real32 U(nx,ny,nz),V(nx,ny,nz); trailing real64 diagnostics'
  WRITE(*,'(A)') 'array_order=Fortran x-fastest stream order; nx=235,ny=283,nz=22'

CONTAINS

  SUBROUTINE nc_open_checked(path,id)
    CHARACTER(LEN=*),INTENT(IN)::path
    INTEGER,INTENT(OUT)::id
    INTEGER::rc
    rc=nf90_open(TRIM(path),NF90_NOWRITE,id)
    IF(rc/=NF90_NOERR) ERROR STOP 'cannot open retained coupled NetCDF'
  END SUBROUTINE
  SUBROUTINE nc_close_checked(id)
    INTEGER,INTENT(IN)::id
    IF(nf90_close(id)/=NF90_NOERR) ERROR STOP 'cannot close retained coupled NetCDF'
  END SUBROUTINE
  SUBROUTINE assert_dims(id,nx0,ny0,nz0)
    INTEGER,INTENT(IN)::id,nx0,ny0,nz0
    INTEGER::dimid,n
    IF(nf90_inq_dimid(id,'x',dimid)/=NF90_NOERR) ERROR STOP 'missing x dimension'
    IF(nf90_inquire_dimension(id,dimid,len=n)/=NF90_NOERR .OR. n/=nx0) ERROR STOP 'x dimension mismatch'
    IF(nf90_inq_dimid(id,'y',dimid)/=NF90_NOERR) ERROR STOP 'missing y dimension'
    IF(nf90_inquire_dimension(id,dimid,len=n)/=NF90_NOERR .OR. n/=ny0) ERROR STOP 'y dimension mismatch'
    IF(nf90_inq_dimid(id,'z',dimid)/=NF90_NOERR) ERROR STOP 'missing z dimension'
    IF(nf90_inquire_dimension(id,dimid,len=n)/=NF90_NOERR .OR. n/=nz0) ERROR STOP 'z dimension mismatch'
  END SUBROUTINE
  INTEGER FUNCTION var_id(id,name)
    INTEGER,INTENT(IN)::id
    CHARACTER(LEN=*),INTENT(IN)::name
    IF(nf90_inq_varid(id,TRIM(name),var_id)/=NF90_NOERR) ERROR STOP 'missing retained variable'
  END FUNCTION
  SUBROUTINE read_r3(id,name,units,data)
    INTEGER,INTENT(IN)::id
    CHARACTER(LEN=*),INTENT(IN)::name,units
    REAL(real32),INTENT(OUT)::data(:,:,:)
    INTEGER::vid,rc
    vid=var_id(id,name)
    CALL assert_units(id,vid,units)
    rc=nf90_get_var(id,vid,data)
    IF(rc/=NF90_NOERR) ERROR STOP 'failed retained real32 read'
  END SUBROUTINE
  SUBROUTINE read_r2(id,name,units,data)
    INTEGER,INTENT(IN)::id
    CHARACTER(LEN=*),INTENT(IN)::name,units
    REAL(real32),INTENT(OUT)::data(:,:)
    INTEGER::vid,rc
    vid=var_id(id,name)
    CALL assert_units(id,vid,units)
    rc=nf90_get_var(id,vid,data)
    IF(rc/=NF90_NOERR) ERROR STOP 'failed retained real32 2d read'
  END SUBROUTINE
  SUBROUTINE read_r64_3(id,name,data)
    INTEGER,INTENT(IN)::id
    CHARACTER(LEN=*),INTENT(IN)::name
    REAL(real64),INTENT(OUT)::data(:,:,:)
    IF(nf90_get_var(id,var_id(id,name),data)/=NF90_NOERR) ERROR STOP 'failed retained real64 read'
  END SUBROUTINE
  SUBROUTINE read_i3(id,name,data)
    INTEGER,INTENT(IN)::id
    CHARACTER(LEN=*),INTENT(IN)::name
    INTEGER(int32),INTENT(OUT)::data(:,:,:)
    INTEGER(int32),ALLOCATABLE::level(:,:,:)
    INTEGER::vid,k,rc
    vid=var_id(id,name)
    ALLOCATE(level(SIZE(data,1),SIZE(data,2),1))
    DO k=1,SIZE(data,3)
      rc=nf90_get_var(id,vid,level,start=[1,1,k],count=[SIZE(data,1),SIZE(data,2),1])
      IF(rc/=NF90_NOERR) ERROR STOP 'failed retained integer read'
      data(:,:,k)=level(:,:,1)
    END DO
  END SUBROUTINE
  SUBROUTINE read_i2(id,name,data)
    INTEGER,INTENT(IN)::id
    CHARACTER(LEN=*),INTENT(IN)::name
    INTEGER,INTENT(OUT)::data(:,:)
    IF(nf90_get_var(id,var_id(id,name),data)/=NF90_NOERR) &
      ERROR STOP 'failed retained integer 2d read'
  END SUBROUTINE
  SUBROUTINE assert_units(id,vid,units)
    INTEGER,INTENT(IN)::id,vid
    CHARACTER(LEN=*),INTENT(IN)::units
    CHARACTER(LEN=128)::found
    IF(nf90_get_att(id,vid,'units',found)/=NF90_NOERR) ERROR STOP 'retained units attribute missing'
    IF(TRIM(found)/=TRIM(units)) ERROR STOP 'retained units attribute mismatch'
  END SUBROUTINE
  SUBROUTINE compare_r3(id,name,units,expected)
    INTEGER,INTENT(IN)::id
    CHARACTER(LEN=*),INTENT(IN)::name,units
    REAL(real32),INTENT(IN)::expected(:,:,:)
    CALL read_r3(id,name,units,real3)
    IF(ANY(real3/=expected)) ERROR STOP 'retained background field differs from exact template input'
  END SUBROUTINE
  SUBROUTINE compare_pressure(id,expected)
    INTEGER,INTENT(IN)::id
    REAL(real32),INTENT(IN)::expected(:,:,:)
    INTEGER::vid
    vid=var_id(id,'pressure'); CALL assert_units(id,vid,'Pa')
    IF(nf90_get_var(id,vid,pressure_1d)/=NF90_NOERR) ERROR STOP 'failed retained pressure read'
    DO i=1,nz
      IF(ANY(expected(:,:,i)/=pressure_1d(i))) ERROR STOP 'pressure differs from exact reader background'
    END DO
  END SUBROUTINE
  SUBROUTINE compare_r2(id,name,units,expected)
    INTEGER,INTENT(IN)::id
    CHARACTER(LEN=*),INTENT(IN)::name,units
    REAL(real32),INTENT(IN)::expected(:,:)
    CALL read_r2(id,name,units,real2)
    IF(ANY(real2/=expected)) ERROR STOP 'retained background 2d field differs from exact template input'
  END SUBROUTINE
  SUBROUTINE compare_i3(id,name,expected)
    INTEGER,INTENT(IN)::id
    CHARACTER(LEN=*),INTENT(IN)::name
    LOGICAL,INTENT(IN)::expected(:,:,:)
    CALL read_i3(id,name,int3)
    IF(ANY((int3/=0_int32).NEQV.expected)) ERROR STOP 'retained mask differs from exact template input'
  END SUBROUTINE
  SUBROUTINE compare_r64_3(id,name,expected)
    INTEGER,INTENT(IN)::id
    CHARACTER(LEN=*),INTENT(IN)::name
    REAL(real64),INTENT(IN)::expected(:,:,:)
    REAL(real64),ALLOCATABLE::actual(:,:,:)
    ALLOCATE(actual(SIZE(expected,1),SIZE(expected,2),SIZE(expected,3)))
    CALL read_r64_3(id,name,actual)
    IF(ANY(actual/=expected)) ERROR STOP 'retained geometry differs from exact template input'
  END SUBROUTINE
  SUBROUTINE compare_field3_metadata(id,prefix,field)
    INTEGER,INTENT(IN)::id
    CHARACTER(LEN=*),INTENT(IN)::prefix
    TYPE(field3d),INTENT(IN)::field
    CALL read_i3(id,TRIM(prefix)//'_valid',int3)
    IF(ANY((int3/=0_int32).NEQV.field%valid)) ERROR STOP 'template validity metadata mismatch'
    CALL read_i3(id,TRIM(prefix)//'_quality',int3)
    IF(ANY(int3/=field%quality)) ERROR STOP 'template quality metadata mismatch'
    CALL read_i3(id,TRIM(prefix)//'_source',int3)
    IF(ANY(int3/=field%source)) ERROR STOP 'template source metadata mismatch'
  END SUBROUTINE
  SUBROUTINE read_global_real(id,name,value)
    INTEGER,INTENT(IN)::id
    CHARACTER(LEN=*),INTENT(IN)::name
    REAL(real64),INTENT(OUT)::value
    IF(nf90_get_att(id,NF90_GLOBAL,TRIM(name),value)/=NF90_NOERR) ERROR STOP 'missing frozen balance gate attribute'
  END SUBROUTINE
  SUBROUTINE read_mask(id,name,mask)
    INTEGER,INTENT(IN)::id
    CHARACTER(LEN=*),INTENT(IN)::name
    LOGICAL,INTENT(OUT)::mask(:,:,:)
    CALL read_i3(id,name,int3)
    IF(ANY((int3/=0_int32).AND.(int3/=1_int32))) ERROR STOP 'retained support mask is not binary'
    mask=int3==1_int32
  END SUBROUTINE
  SUBROUTINE overlay_field(id,name,units,field)
    INTEGER,INTENT(IN)::id
    CHARACTER(LEN=*),INTENT(IN)::name,units
    TYPE(field3d),INTENT(INOUT)::field
    CALL read_r3(id,name,units,real3); field%value=real3
    CALL read_i3(id,TRIM(name)//'_valid',int3); field%valid=int3/=0_int32
    CALL read_i3(id,TRIM(name)//'_quality',field%quality)
    CALL read_i3(id,TRIM(name)//'_source',field%source)
  END SUBROUTINE
  SUBROUTINE dry_flux_rms(flux,volume,mask,rms)
    REAL(real64),INTENT(IN)::flux(:,:,:),volume(:,:,:)
    LOGICAL,INTENT(IN)::mask(:,:,:)
    REAL(real64),INTENT(OUT)::rms
    REAL(real64)::total,count_cells
    INTEGER::ii,jj,kk
    total=0.0_real64; count_cells=0.0_real64
    DO kk=1,SIZE(mask,3); DO jj=1,SIZE(mask,2); DO ii=1,SIZE(mask,1)
      IF (.NOT.mask(ii,jj,kk)) CYCLE
      total=total+(flux(ii,jj,kk)/volume(ii,jj,kk))**2
      count_cells=count_cells+1.0_real64
    END DO; END DO; END DO
    IF(count_cells<=0.0_real64) ERROR STOP 'empty force support for dry-flux diagnostic'
    rms=SQRT(total/count_cells)
  END SUBROUTINE
  SUBROUTINE dry_flux_increment_norm(candidate_flux,reference_flux,volume,mask,rms,maxabs)
    REAL(real64),INTENT(IN)::candidate_flux(:,:,:),reference_flux(:,:,:),volume(:,:,:)
    LOGICAL,INTENT(IN)::mask(:,:,:)
    REAL(real64),INTENT(OUT)::rms,maxabs
    REAL(real64)::total,count_cells,value
    INTEGER::ii,jj,kk
    total=0.0_real64; count_cells=0.0_real64; maxabs=0.0_real64
    DO kk=1,SIZE(mask,3); DO jj=1,SIZE(mask,2); DO ii=1,SIZE(mask,1)
      IF(.NOT.mask(ii,jj,kk)) CYCLE
      value=(candidate_flux(ii,jj,kk)-reference_flux(ii,jj,kk))/volume(ii,jj,kk)
      total=total+value*value; maxabs=MAX(maxabs,ABS(value)); count_cells=count_cells+1.0_real64
    END DO; END DO; END DO
    IF(count_cells<=0.0_real64) ERROR STOP 'empty validation shell for dry-flux increment diagnostic'
    rms=SQRT(total/count_cells)
  END SUBROUTINE
  SUBROUTINE assert_frozen_fields(a,b)
    TYPE(cloud_bal_state_type),INTENT(IN)::a,b
    TYPE(cloud_bal_state_type)::wind_only_reference
    wind_only_reference=b
    wind_only_reference%u=a%u
    wind_only_reference%v=a%v
    IF(.NOT.canonical_states_equal(a,wind_only_reference)) &
      ERROR STOP 'refinement changed non-wind state, geometry, or observation evidence'
    CALL assert_field_equal(a%temperature,b%temperature,'temperature')
    CALL assert_field_equal(a%vapor,b%vapor,'vapor')
    CALL assert_field_equal(a%geopotential,b%geopotential,'geopotential')
    CALL assert_field_equal(a%omega,b%omega,'omega')
    CALL assert_field_equal(a%omega_target,b%omega_target,'omega_target')
    CALL assert_field_equal(a%omega_target_sigma,b%omega_target_sigma,'omega_target_sigma')
    CALL assert_field_equal(a%cloud_water,b%cloud_water,'cloud_water')
    CALL assert_field_equal(a%cloud_ice,b%cloud_ice,'cloud_ice')
    CALL assert_field_equal(a%rain,b%rain,'rain')
    CALL assert_field_equal(a%snow,b%snow,'snow')
    CALL assert_field_equal(a%graupel,b%graupel,'graupel')
    IF(ANY(a%pressure%value/=b%pressure%value).OR. &
      ANY(a%grid%dry_air_mass_measure/=b%grid%dry_air_mass_measure)) &
      ERROR STOP 'refinement changed pressure or dry-air mass geometry'
    IF(ANY(a%grid%pressure_interface/=b%grid%pressure_interface).OR. &
      ANY(a%grid%cell_dp/=b%grid%cell_dp).OR. &
      ANY(a%grid%pressure_mass_measure/=b%grid%pressure_mass_measure).OR. &
      ANY(a%above_ground.NEQV.b%above_ground)) ERROR STOP 'refinement changed fixed geometry'
    IF(ANY(a%surface_pressure%value/=b%surface_pressure%value).OR. &
      ANY(a%surface_pressure%valid.NEQV.b%surface_pressure%valid).OR. &
      ANY(a%surface_pressure%quality/=b%surface_pressure%quality).OR. &
      ANY(a%surface_pressure%source/=b%surface_pressure%source)) &
      ERROR STOP 'refinement changed surface pressure or its provenance'
    IF(ANY(a%omega_top_boundary%value/=b%omega_top_boundary%value).OR. &
      ANY(a%omega_bottom_boundary%value/=b%omega_bottom_boundary%value)) &
      ERROR STOP 'refinement changed omega boundary values'
  END SUBROUTINE
  SUBROUTINE assert_field_equal(a,b,label)
    TYPE(field3d),INTENT(IN)::a,b
    CHARACTER(LEN=*),INTENT(IN)::label
    IF(a%valid_time/=b%valid_time.OR.a%unit/=b%unit.OR. &
      ANY(a%value/=b%value).OR.ANY(a%valid.NEQV.b%valid).OR. &
      ANY(a%quality/=b%quality).OR.ANY(a%source/=b%source)) THEN
      WRITE(*,'(A)') 'frozen_field_changed='//TRIM(label)
      WRITE(*,'(A,I0,A,I0,A,I0,A,I0)') 'value_mismatches=',COUNT(a%value/=b%value), &
        ',valid_mismatches=',COUNT(a%valid .NEQV. b%valid), &
        ',quality_mismatches=',COUNT(a%quality/=b%quality), &
        ',source_mismatches=',COUNT(a%source/=b%source)
      WRITE(*,'(A,I0,A,I0,A,A,A,A)') 'valid_time_a=',a%valid_time,',valid_time_b=', &
        b%valid_time,',units=',TRIM(a%unit)//'/'//TRIM(b%unit)
      ERROR STOP 'refinement changed a frozen field or provenance'
    END IF
  END SUBROUTINE
  SUBROUTINE report_unexported_field(name,a,b)
    CHARACTER(LEN=*),INTENT(IN)::name
    TYPE(field3d),INTENT(IN)::a,b
    WRITE(*,'(A,A,A,I0,A,I0,A,I0,A,I0,A,I0,A,I0)') 'retained_writer_unexported=',TRIM(name), &
      ',value_diff_cells=',COUNT(a%value/=b%value),',valid_diff_cells=',COUNT(a%valid .NEQV. b%valid), &
      ',quality_diff_cells=',COUNT(a%quality/=b%quality),',source_diff_cells=',COUNT(a%source/=b%source), &
      ',time_equal=',MERGE(1,0,a%valid_time==b%valid_time),',unit_equal=',MERGE(1,0,a%unit==b%unit)
  END SUBROUTINE
  SUBROUTINE assert_source_balance_bits(a,b)
    TYPE(cloud_bal_state_type),INTENT(IN)::a,b
    IF(ANY((b%u%value==a%u%value).AND.(b%u%source/=a%u%source))) &
      ERROR STOP 'refinement changed U provenance without changing U values'
    IF(ANY((b%v%value==a%v%value).AND.(b%v%source/=a%v%source))) &
      ERROR STOP 'refinement changed V provenance without changing V values'
    IF(ANY((b%u%value/=a%u%value).AND. &
      (IAND(b%u%source, SOURCE_BALANCE_OPERATOR)==0_int32))) ERROR STOP 'changed U lacks balance provenance'
    IF(ANY((b%v%value/=a%v%value).AND. &
      (IAND(b%v%source, SOURCE_BALANCE_OPERATOR)==0_int32))) ERROR STOP 'changed V lacks balance provenance'
  END SUBROUTINE
  SUBROUTINE write_wind_artifact(path,state,diagnostics)
    CHARACTER(LEN=*),INTENT(IN)::path
    TYPE(cloud_bal_state_type),INTENT(IN)::state
    TYPE(force_prior_diagnostics),INTENT(IN)::diagnostics
    INTEGER::out
    OPEN(NEWUNIT=out,FILE=TRIM(path),ACCESS='STREAM',FORM='UNFORMATTED',STATUS='REPLACE',IOSTAT=ios)
    IF(ios/=0) ERROR STOP 'cannot create retained wind artifact'
    WRITE(out) INT([1,nx,ny,nz],int32)
    WRITE(out) state%u%value
    WRITE(out) state%v%value
    WRITE(out) [diagnostics%input_objective,diagnostics%candidate_objective, &
      diagnostics%input_force_rms,diagnostics%candidate_force_rms, &
      diagnostics%input_normalized_force_rms,diagnostics%candidate_normalized_force_rms, &
      diagnostics%continuity_candidate_rms,diagnostics%continuity_candidate_max, &
      diagnostics%maximum_wind_increment,diagnostics%projected_increment_rms, &
      diagnostics%projected_increment_max]
    CLOSE(out)
  END SUBROUTINE
  SUBROUTINE write_summary(path,diagnostics,dry_before,dry_after,dry_increment,dry_increment_maximum, &
      geo_background,geo_input,wind_increment,omega_increment)
    CHARACTER(LEN=*),INTENT(IN)::path
    TYPE(force_prior_diagnostics),INTENT(IN)::diagnostics
    REAL(real64),INTENT(IN)::dry_before,dry_after,dry_increment,dry_increment_maximum
    REAL(real64),INTENT(IN)::geo_background,geo_input,wind_increment,omega_increment
    INTEGER::out
    OPEN(NEWUNIT=out,FILE=TRIM(path),STATUS='REPLACE',ACTION='WRITE',IOSTAT=ios)
    IF(ios/=0) ERROR STOP 'cannot create retained probe summary'
    WRITE(out,'(A)') 'contract=background_force_prior_refinement_v1'
    WRITE(out,'(A)') 'reference=nonzero_r_g(background); force_sigma=abs(f)*4m/s; wind_sigma=4m/s'
    WRITE(out,'(A,I0)') 'status=',diagnostics%status
    WRITE(out,'(A,I0)') 'reason=',diagnostics%reason
    WRITE(out,'(A,ES24.16)') 'input_objective=',diagnostics%input_objective
    WRITE(out,'(A,ES24.16)') 'candidate_objective=',diagnostics%candidate_objective
    WRITE(out,'(A,ES24.16)') 'background_force_rms=',diagnostics%background_force_rms
    WRITE(out,'(A,ES24.16)') 'input_force_rms=',diagnostics%input_force_rms
    WRITE(out,'(A,ES24.16)') 'candidate_force_rms=',diagnostics%candidate_force_rms
    WRITE(out,'(A,ES24.16)') 'dry_flux_divergence_bg_rms_force_support=',dry_before
    WRITE(out,'(A,ES24.16)') 'dry_flux_divergence_input_rms_force_support=',dry_after
    WRITE(out,'(A,ES24.16)') 'dry_flux_increment_rms_validation_shell=',dry_increment
    WRITE(out,'(A,ES24.16)') 'dry_flux_increment_max_validation_shell=',dry_increment_maximum
    WRITE(out,'(A,ES24.16)') 'absolute_geostrophic_rms_background_force_support=',geo_background
    WRITE(out,'(A,ES24.16)') 'absolute_geostrophic_rms_input_force_support=',geo_input
    WRITE(out,'(A,ES24.16)') 'input_wind_increment_max_control_ms=',wind_increment
    WRITE(out,'(A,ES24.16)') 'input_omega_increment_max_pas=',omega_increment
    WRITE(out,'(A,ES24.16)') 'hard_wind_increment_cap_ms=',10.0_real64
    WRITE(out,'(A,ES24.16)') 'hard_omega_increment_cap_pas=',5.0_real64
    WRITE(out,'(A,ES24.16)') 'analytic_headroom_fraction=',0.95_real64
    WRITE(out,'(A,ES24.16)') 'candidate_continuity_rms=',diagnostics%continuity_candidate_rms
    WRITE(out,'(A,ES24.16)') 'candidate_continuity_max=',diagnostics%continuity_candidate_max
    WRITE(out,'(A,ES24.16)') 'candidate_wind_increment_max_control_ms=',diagnostics%maximum_wind_increment
    WRITE(out,'(A,ES24.16)') 'candidate_omega_increment_max_pas=',diagnostics%maximum_omega_increment
    WRITE(out,'(A,I0)') 'projector_solver_iterations=',diagnostics%solver_iterations
    WRITE(out,'(A)') 'decision=diagnostic probe only; science authority NONE'
    CLOSE(out)
  END SUBROUTINE
  SUBROUTINE run_retained_full_pipeline()
    INTEGER :: pipeline_status
    pipeline_config%requested_mode=MODE_SHADOW
    pipeline_config%maximum_outer_iterations=8
    pipeline_config%column%transport_precipitation=.FALSE.
    pipeline_config%background_continuity_prior=.TRUE.
    pipeline_config%force_prior_enabled=.TRUE.
    pipeline_config%balance%maximum_wind_increment=10.0_real64
    pipeline_config%balance%maximum_omega_increment=5.0_real64
    pipeline_config%balance%increment_headroom=0.95_real64
    CALL run_cloud_bal_pipeline(background,pipeline_candidate,pipeline_operational,pipeline_result, &
      pipeline_config,thermo_active=thermo_support,thermo_surface=thermo_surface, &
      target_rh=1.0_real64,geopotential_support=phi_support, &
      geopotential_reference_level=geopotential_reference_level,analysis_support=material_support, &
      background_control_support=control,background_validation_shell=shell,force_support=force)
    WRITE(*,'(A,I0,A,I0)') 'full_pipeline_status=',pipeline_result%status, &
      ',reason=',pipeline_result%reason_code
    IF (pipeline_result%status/=STATUS_OK .OR. .NOT.pipeline_result%force_prior_applied .OR. &
        pipeline_result%force_prior%status/=STATUS_OK) &
      ERROR STOP 'full retained pipeline did not apply the force-prior stage'
    IF (.NOT.canonical_states_equal(background,pipeline_operational)) &
      ERROR STOP 'full retained pipeline changed its operational state'
    IF (.NOT.ALLOCATED(pipeline_result%pre_force_u) .OR. &
        .NOT.ALLOCATED(pipeline_result%pre_force_v) .OR. &
        .NOT.ALLOCATED(pipeline_result%pre_force_omega)) &
      ERROR STOP 'full retained pipeline omitted pre-force state'
    IF (ANY(pipeline_result%pre_force_u/=input%u%value) .OR. &
        ANY(pipeline_result%pre_force_v/=input%v%value) .OR. &
        ANY(pipeline_result%pre_force_omega/=input%omega%value)) &
      ERROR STOP 'full pipeline pre-force winds/omega differ from retained coupled candidate'
    IF (ANY(pipeline_candidate%u%value/=refined%u%value) .OR. &
        ANY(pipeline_candidate%v%value/=refined%v%value) .OR. &
        ANY(pipeline_candidate%omega%value/=refined%omega%value)) &
      ERROR STOP 'full pipeline final winds/omega differ from component force probe'
    CALL assert_field_equal(pipeline_candidate%u,refined%u,'pipeline/component U')
    CALL assert_field_equal(pipeline_candidate%v,refined%v,'pipeline/component V')
    CALL assert_field_equal(pipeline_candidate%omega,refined%omega,'pipeline/component omega')
    CALL assert_field_equal(pipeline_candidate%omega_target,refined%omega_target,'pipeline/component omega_target')
    CALL assert_field_equal(pipeline_candidate%rain,refined%rain,'pipeline/component rain')
    CALL assert_field_equal(pipeline_candidate%snow,refined%snow,'pipeline/component snow')
    CALL assert_field_equal(pipeline_candidate%graupel,refined%graupel,'pipeline/component graupel')
    IF (.NOT.canonical_states_equal(pipeline_candidate,refined,.TRUE.)) &
      ERROR STOP 'full pipeline and component differ in candidate-scope serialized state'
    CALL report_unexported_field('vt_z_mean',pipeline_candidate%vt_z_mean,refined%vt_z_mean)
    CALL report_unexported_field('vt_z_sigma',pipeline_candidate%vt_z_sigma,refined%vt_z_sigma)
    WRITE(*,'(A)') 'component_vs_full_pipeline=serialized physical fields, geometry, and wind metadata only'
    WRITE(*,'(A)') 'component_retention_limit=vt_z_mean,vt_z_sigma,precipitation_phase not exported by retained NetCDF'
    IF (ANY(pipeline_candidate%grid%dry_air_mass_measure/=input%grid%dry_air_mass_measure)) &
      ERROR STOP 'full pipeline changed the retained candidate dry-air mass geometry'
    CALL state_continuity_residual(diagnostic_op,background,residual_before,pipeline_status)
    IF (pipeline_status/=STATUS_OK) ERROR STOP 'could not prepare writer background residual'
    CALL state_continuity_residual(diagnostic_op,pipeline_candidate,residual_after,pipeline_status)
    IF (pipeline_status/=STATUS_OK) ERROR STOP 'could not prepare writer candidate residual'
    CALL write_shadow_diagnostics(TRIM(pipeline_nc_path),background,pipeline_candidate,longitude, &
      pipeline_result,pipeline_config,residual_before,residual_after,writer_status,pipeline_operational, &
      pressure_analysis_candidate=.TRUE.)
    WRITE(*,'(A,I0)') 'full_pipeline_writer_status=',writer_status
    IF (writer_status/=STATUS_OK) ERROR STOP 'full pipeline shadow writer rejected retained candidate'
    IF (.NOT.pipeline_result_replays(background,pipeline_candidate,pipeline_result,pipeline_config)) &
      ERROR STOP 'full pipeline producer replay did not reproduce the retained candidate receipt'
    WRITE(*,'(A)') 'full_pipeline_producer_replay=T'
    WRITE(*,'(A)') 'full_pipeline_writer_roundtrip=T'
    WRITE(*,'(A)') 'full_pipeline_science_authority=NONE'
  END SUBROUTINE run_retained_full_pipeline
END PROGRAM pr80_force_retained
