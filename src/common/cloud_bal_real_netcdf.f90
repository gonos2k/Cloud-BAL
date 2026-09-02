! Thin NetCDF adapter for the prepared KLAPS real-data SHADOW cases.
!
! The adapter owns every legacy convention: file layout, fill values,
! specific-humidity conversion and the top-to-bottom file ordering.  Physics
! receives only the canonical bottom-to-top state from cloud_bal_state.
MODULE cloud_bal_real_netcdf
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32,int64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  USE netcdf
  USE cloud_bal_state
  USE cloud_bal_column_physics, ONLY: column_changed_mask,column_config_valid
  USE cloud_bal_balance_operator, ONLY: balance_beta_active,boundary_contract_valid
  IMPLICIT NONE
  PRIVATE

  INTEGER, PARAMETER :: NX=235,NY=283,NZ=22
  REAL(real64), PARAMETER :: GRAVITY=9.80665_real64
  REAL(real64), PARAMETER :: RD_AIR=287.05_real64
  REAL(real64), PARAMETER :: EPSILON_WATER=0.622_real64
  REAL(real32), PARAMETER :: RAW_MISSING_LIMIT=1.0e30_real32
  REAL(real32), PARAMETER :: MINIMUM_USABLE_DBZ=0.0_real32

  PUBLIC :: read_real_shadow_state
  PUBLIC :: write_shadow_diagnostics
  PUBLIC :: validate_shadow_write_contract

CONTAINS

  SUBROUTINE read_real_shadow_state(fua_path,fsf_path,lw3_path,vrz_path,vrt_path, &
                                    static_path,valid_time,state,longitude,status,reason)
    CHARACTER(LEN=*), INTENT(IN) :: fua_path,fsf_path,lw3_path,vrz_path,vrt_path
    CHARACTER(LEN=*), INTENT(IN) :: static_path
    INTEGER(int64), INTENT(IN) :: valid_time
    TYPE(cloud_bal_state_type), INTENT(OUT) :: state
    REAL(real32), ALLOCATABLE, INTENT(OUT) :: longitude(:,:)
    INTEGER, INTENT(OUT) :: status,reason
    REAL(real32), ALLOCATABLE :: raw(:,:,:),surface(:,:),tid(:,:,:),topography(:,:)
    LOGICAL, ALLOCATABLE :: raw_valid(:,:,:),surface_valid(:,:),terrain_domain(:,:,:)
    LOGICAL, ALLOCATABLE :: latitude_valid(:,:),longitude_valid(:,:),topography_valid(:,:)
    REAL(real64) :: levels(NZ),dx,dy
    INTEGER :: ncid,k,source_k,local_status

    status=STATUS_FAILED; reason=REASON_METADATA
    CALL initialize_cloud_bal_state(state,NX,NY,NZ,valid_time, &
                                    'NE57_LAPS_PRESSURE',local_status)
    IF (local_status/=STATUS_OK) RETURN
    ALLOCATE(raw(NX,NY,NZ),raw_valid(NX,NY,NZ),surface(NX,NY), &
             surface_valid(NX,NY),latitude_valid(NX,NY),longitude_valid(NX,NY), &
             topography_valid(NX,NY),terrain_domain(NX,NY,NZ), &
             tid(NX,NY,NZ),longitude(NX,NY), &
             topography(NX,NY))
    raw=0.0_real32; raw_valid=.FALSE.
    surface=0.0_real32; surface_valid=.FALSE.
    latitude_valid=.FALSE.; longitude_valid=.FALSE.; topography_valid=.FALSE.
    terrain_domain=.FALSE.; tid=0.0_real32
    longitude=0.0_real32; topography=0.0_real32

    ! Surface pressure and the pressure coordinate own the physical domain.
    ! Omega is a required field inside that domain, never the domain mask.
    CALL open_surface_file(fsf_path,valid_time,ncid,dx,dy,local_status)
    IF (local_status==STATUS_OK) CALL read_real2(ncid,'tsf','kelvins','k', &
                                                 surface,surface_valid,local_status)
    IF (local_status==STATUS_OK .AND. .NOT.ALL(surface_valid)) THEN
      CALL close_file(ncid,local_status)
      reason=REASON_REQUIRED_COVERAGE
      RETURN
    END IF
    IF (local_status==STATUS_OK) CALL assign_surface(surface,surface_valid, &
      state%surface_temperature,SOURCE_BACKGROUND_MODEL)
    IF (local_status==STATUS_OK) CALL read_real2(ncid,'psf','pascals','pa', &
                                                 surface,surface_valid,local_status)
    IF (local_status==STATUS_OK .AND. .NOT.ALL(surface_valid)) THEN
      CALL close_file(ncid,local_status)
      reason=REASON_REQUIRED_COVERAGE
      RETURN
    END IF
    IF (local_status==STATUS_OK) CALL assign_surface(surface,surface_valid, &
      state%surface_pressure,SOURCE_BACKGROUND_MODEL)
    CALL close_file(ncid,local_status)
    IF (local_status/=STATUS_OK) RETURN

    CALL open_case_file(lw3_path,NZ,valid_time,ncid,levels,dx,dy,local_status)
    IF (local_status/=STATUS_OK) RETURN
    CALL read_real3(ncid,'om','pascals/second','pa/s',raw,raw_valid,local_status)
    IF (local_status/=STATUS_OK) THEN; CALL close_file(ncid,local_status); RETURN; END IF
    state%grid%dx=dx; state%grid%dy=dy
    DO k=1,NZ
      source_k=NZ+1-k
      state%pressure%value(:,:,k)=REAL(100.0_real64*levels(source_k),real32)
      CALL mark_real_field(state%pressure,k,surface_valid,SOURCE_BACKGROUND_MODEL)
    END DO
    CALL configure_pressure_geometry(state,local_status)
    IF (local_status/=STATUS_OK) THEN
      CALL close_file(ncid,local_status)
      reason=REASON_REQUIRED_COVERAGE
      RETURN
    END IF
    IF (.NOT.vertical_domain_is_contiguous(state%above_ground)) THEN
      CALL close_file(ncid,local_status); reason=REASON_REQUIRED_COVERAGE; RETURN
    END IF
    CALL assign_reversed_core(raw,raw_valid,state%above_ground,state%omega, &
      SOURCE_ANALYZED_WIND,1.0_real64,local_status)
    IF (local_status/=STATUS_OK) THEN
      CALL close_file(ncid,local_status); reason=REASON_REQUIRED_COVERAGE; RETURN
    END IF
    CALL read_real3(ncid,'u3','meters/second','m/s',raw,raw_valid,local_status)
    IF (local_status/=STATUS_OK) THEN; CALL close_file(ncid,local_status); RETURN; END IF
    CALL assign_reversed_core(raw,raw_valid,state%above_ground,state%u, &
      SOURCE_ANALYZED_WIND,1.0_real64,local_status)
    IF (local_status/=STATUS_OK) THEN
      CALL close_file(ncid,local_status); reason=REASON_REQUIRED_COVERAGE; RETURN
    END IF
    CALL read_real3(ncid,'v3','meters/second','m/s',raw,raw_valid,local_status)
    IF (local_status/=STATUS_OK) THEN; CALL close_file(ncid,local_status); RETURN; END IF
    CALL assign_reversed_core(raw,raw_valid,state%above_ground,state%v, &
      SOURCE_ANALYZED_WIND,1.0_real64,local_status)
    IF (local_status/=STATUS_OK) reason=REASON_REQUIRED_COVERAGE
    CALL close_file(ncid,local_status)
    IF (local_status/=STATUS_OK) RETURN

    CALL open_case_file(fua_path,NZ,valid_time,ncid,levels,dx,dy,local_status)
    IF (local_status/=STATUS_OK) RETURN
    CALL read_real3(ncid,'t3','kelvins','k',raw,raw_valid,local_status)
    IF (local_status/=STATUS_OK) THEN; CALL close_file(ncid,local_status); RETURN; END IF
    CALL assign_reversed_core(raw,raw_valid,state%above_ground,state%temperature, &
      SOURCE_BACKGROUND_MODEL,1.0_real64,local_status)
    IF (local_status/=STATUS_OK) THEN
      CALL close_file(ncid,local_status); reason=REASON_REQUIRED_COVERAGE; RETURN
    END IF
    CALL read_real3(ncid,'sh','kg/kg','kgkg-1',raw,raw_valid,local_status)
    IF (local_status/=STATUS_OK) THEN; CALL close_file(ncid,local_status); RETURN; END IF
    IF (.NOT.reversed_coverage_is_complete(raw_valid,state%above_ground)) THEN
      CALL close_file(ncid,local_status); reason=REASON_REQUIRED_COVERAGE; RETURN
    END IF
    CALL assign_specific_humidity(raw,raw_valid,state,local_status)
    IF (local_status/=STATUS_OK) THEN
      CALL close_file(ncid,local_status); reason=REASON_RANGE; RETURN
    END IF
    CALL read_real3(ncid,'ht','meters','m',raw,raw_valid,local_status)
    IF (local_status/=STATUS_OK) THEN; CALL close_file(ncid,local_status); RETURN; END IF
    CALL assign_reversed_core(raw,raw_valid,state%above_ground,state%geopotential, &
      SOURCE_BACKGROUND_MODEL,GRAVITY,local_status)
    IF (local_status/=STATUS_OK) THEN
      CALL close_file(ncid,local_status); reason=REASON_REQUIRED_COVERAGE; RETURN
    END IF
    IF (local_status==STATUS_OK) CALL read_and_assign_hydrometeor(ncid,'lwc', &
      state,state%cloud_water,raw,raw_valid,local_status)
    IF (local_status==STATUS_OK) CALL read_and_assign_hydrometeor(ncid,'ice', &
      state,state%cloud_ice,raw,raw_valid,local_status)
    IF (local_status==STATUS_OK) CALL read_and_assign_hydrometeor(ncid,'rai', &
      state,state%rain,raw,raw_valid,local_status)
    IF (local_status==STATUS_OK) CALL read_and_assign_hydrometeor(ncid,'sno', &
      state,state%snow,raw,raw_valid,local_status)
    IF (local_status==STATUS_OK) CALL read_and_assign_hydrometeor(ncid,'pic', &
      state,state%graupel,raw,raw_valid,local_status)
    CALL close_file(ncid,local_status)
    IF (local_status/=STATUS_OK) RETURN

    CALL open_case_file(vrz_path,NZ,valid_time,ncid,levels,dx,dy,local_status)
    IF (local_status==STATUS_OK) CALL read_real3(ncid,'ref','dbz','dbz', &
                                                 raw,raw_valid,local_status)
    CALL close_file(ncid,local_status)
    IF (local_status/=STATUS_OK) RETURN
    DO k=1,NZ
      source_k=NZ+1-k
      state%radar_reflectivity%valid(:,:,k)=state%above_ground(:,:,k) .AND. &
        raw_valid(:,:,source_k) .AND. raw(:,:,source_k)>=MINIMUM_USABLE_DBZ .AND. &
        raw(:,:,source_k)<=100.0_real32
      IF (ANY(state%above_ground(:,:,k) .AND. raw_valid(:,:,source_k) .AND. &
          .NOT.(raw(:,:,source_k)==RADAR_NO_ECHO_DBZ .OR. &
                (raw(:,:,source_k)>=MINIMUM_USABLE_DBZ .AND. &
                 raw(:,:,source_k)<=100.0_real32)))) THEN
        reason=REASON_RANGE
        RETURN
      END IF
      WHERE(state%above_ground(:,:,k) .AND. raw_valid(:,:,source_k) .AND. &
            (state%radar_reflectivity%valid(:,:,k) .OR. &
             raw(:,:,source_k)==RADAR_NO_ECHO_DBZ))
        state%radar_reflectivity%value(:,:,k)=raw(:,:,source_k)
        state%radar_reflectivity%quality(:,:,k)=0_int32
        state%radar_reflectivity%source(:,:,k)=SOURCE_RADAR_DBZ
      END WHERE
    END DO

    CALL open_case_file(vrt_path,NZ,valid_time,ncid,levels,dx,dy,local_status)
    IF (local_status==STATUS_OK) CALL read_real3(ncid,'tid','nul','1', &
                                                 tid,raw_valid,local_status)
    CALL close_file(ncid,local_status)
    IF (local_status/=STATUS_OK) RETURN
    DO k=1,NZ
      source_k=NZ+1-k
      IF (ANY(state%above_ground(:,:,k) .AND. &
              .NOT.radar_tid_value_valid(tid(:,:,source_k), &
                                         raw_valid(:,:,source_k)))) THEN
        reason=REASON_RANGE
        RETURN
      END IF
      WHERE(state%radar_reflectivity%valid(:,:,k) .AND. &
            radar_tid_is_mixed(tid(:,:,source_k),raw_valid(:,:,source_k)))
        state%radar_reflectivity%quality(:,:,k)= &
          IOR(state%radar_reflectivity%quality(:,:,k),QUALITY_BRIGHT_BAND_OR_MIXED)
      END WHERE
    END DO

    CALL open_static_file(static_path,ncid,local_status)
    IF (local_status==STATUS_OK) CALL read_real2(ncid,'lat','degrees','degree_north', &
                                                 surface,latitude_valid,local_status)
    IF (local_status==STATUS_OK .AND. &
        ANY(latitude_valid .AND. (surface < -90.0_real32 .OR. &
                                  surface > 90.0_real32))) local_status=STATUS_FAILED
    IF (local_status==STATUS_OK) CALL assign_surface(surface,latitude_valid, &
      state%latitude,SOURCE_BACKGROUND_MODEL)
    IF (local_status==STATUS_OK) CALL read_real2(ncid,'lon','degrees','degree_east', &
                                                 longitude,longitude_valid,local_status)
    IF (local_status==STATUS_OK .AND. &
        ANY(longitude_valid .AND. (longitude < -180.0_real32 .OR. &
                                   longitude > 180.0_real32))) local_status=STATUS_FAILED
    IF (local_status==STATUS_OK) CALL read_real2(ncid,'avg','meters msl','m', &
      topography,topography_valid,local_status)
    IF (local_status==STATUS_OK .AND. &
        ANY(topography_valid .AND. (topography < -500.0_real32 .OR. &
                                    topography > 9000.0_real32))) &
      local_status=STATUS_FAILED
    CALL close_file(ncid,local_status)
    IF (local_status/=STATUS_OK .OR. .NOT.ALL(latitude_valid) .OR. &
        .NOT.ALL(longitude_valid) .OR. .NOT.ALL(topography_valid)) RETURN
    terrain_domain=state%above_ground .AND. state%geopotential%valid .AND. &
      ieee_is_finite(state%geopotential%value) .AND. &
      state%geopotential%value/REAL(GRAVITY,real32)>= &
        SPREAD(topography-128.0_real32*EPSILON(1.0_real32)* &
          MAX(1.0_real32,ABS(topography)),3,NZ)
    CALL configure_pressure_geometry(state,local_status,terrain_domain)
    IF (local_status/=STATUS_OK) THEN
      reason=REASON_REQUIRED_COVERAGE
      RETURN
    END IF
    CALL restrict_state_to_domain(state)
    IF (.NOT.terrain_mask_is_consistent(state,topography)) THEN
      reason=REASON_REQUIRED_COVERAGE
      RETURN
    END IF

    CALL set_copied_interior_omega_boundaries(state,local_status)
    IF (local_status/=STATUS_OK) RETURN
    CALL refresh_dry_air_mass_measure(state,local_status)
    IF (local_status/=STATUS_OK) RETURN
    IF (.NOT.real_radar_contract_valid(state)) THEN
      reason=REASON_RADAR_CONTRACT
      RETURN
    END IF
    CALL validate_canonical_state(state,.FALSE.,.TRUE.,local_status,reason,.TRUE.)
    IF (local_status/=STATUS_OK) RETURN
    status=STATUS_OK; reason=REASON_NONE
  END SUBROUTINE read_real_shadow_state

  SUBROUTINE write_shadow_diagnostics(path,state_in,candidate,longitude,result,config, &
                                      residual_before,residual_after,status,operational_state)
    USE cloud_bal_pipeline, ONLY: cloud_bal_pipeline_result,cloud_bal_pipeline_config
    CHARACTER(LEN=*), INTENT(IN) :: path
    TYPE(cloud_bal_state_type), INTENT(IN) :: state_in,candidate
    REAL(real32), INTENT(IN) :: longitude(:,:)
    TYPE(cloud_bal_pipeline_result), INTENT(IN) :: result
    TYPE(cloud_bal_pipeline_config), INTENT(IN) :: config
    REAL(real64), INTENT(IN) :: residual_before(:,:,:),residual_after(:,:,:)
    INTEGER, INTENT(OUT) :: status
    TYPE(cloud_bal_state_type), INTENT(IN) :: operational_state
    INTEGER :: ncid,xdim,ydim,zdim,zinterface_dim,zspacing_dim
    INTEGER :: level_var,lat_var,lon_var,interface_var,cell_dp_var,spacing_var
    INTEGER :: pressure_mass_var,dry_mass_var,surface_pressure_var
    INTEGER :: omega_top_var,omega_bottom_var,omega_top_valid_var,omega_bottom_valid_var
    INTEGER :: omega_top_quality_var,omega_top_source_var
    INTEGER :: omega_bottom_quality_var,omega_bottom_source_var
    INTEGER :: varid(36),rc,k,contract_reason,nx,ny,nz
    INTEGER(int32), ALLOCATABLE :: mask(:,:,:),boundary_mask(:,:)
    REAL(real32), ALLOCATABLE :: levels(:)
    CHARACTER(LEN=32), PARAMETER :: names(36)=[CHARACTER(LEN=32) :: &
      'radar_dbz','background_u','background_v','background_omega', &
      'candidate_u','candidate_v','candidate_omega','omega_target', &
      'background_cloud_water','background_cloud_ice','background_rain', &
      'background_snow','background_graupel','candidate_cloud_water', &
      'candidate_cloud_ice','candidate_rain','candidate_snow', &
      'candidate_graupel','balance_beta', &
      'continuity_background','continuity_candidate','above_ground', &
      'radar_valid','omega_target_valid','omega_target_quality', &
      'omega_target_source','omega_target_authority','candidate_balance_support', &
      'column_changed','balance_changed','overall_changed','obs_support','hydro_support', &
      'radar_coverage','radar_no_echo','radar_missing']
    CHARACTER(LEN=32), PARAMETER :: units(36)=[CHARACTER(LEN=32) :: &
      'dBZ','m s-1','m s-1','Pa s-1','m s-1','m s-1','Pa s-1','Pa s-1', &
      'kg kg-1 dryair','kg kg-1 dryair','kg kg-1 dryair','kg kg-1 dryair', &
      'kg kg-1 dryair','kg kg-1 dryair','kg kg-1 dryair','kg kg-1 dryair', &
      'kg kg-1 dryair','kg kg-1 dryair','1','s-1','s-1', &
      '1','1','1','1','1','1','1','1','1','1','1','1','1','1','1']

    status=STATUS_FAILED
    CALL validate_shadow_write_contract(state_in,candidate,operational_state, &
      result,config,status,contract_reason)
    IF (status/=STATUS_OK) RETURN
    status=STATUS_FAILED
    nx=state_in%grid%nx; ny=state_in%grid%ny; nz=state_in%grid%nz
    IF (ANY(SHAPE(longitude)/=(/nx,ny/)) .OR. &
        ANY(SHAPE(residual_before)/=(/nx,ny,nz/)) .OR. &
        ANY(SHAPE(residual_after)/=(/nx,ny,nz/))) RETURN
    IF (ANY(.NOT.ieee_is_finite(state_in%latitude%value)) .OR. &
        ANY(state_in%latitude%value < -90.0_real32) .OR. &
        ANY(state_in%latitude%value > 90.0_real32) .OR. &
        ANY(.NOT.ieee_is_finite(longitude)) .OR. &
        ANY(longitude < -180.0_real32) .OR. ANY(longitude > 180.0_real32) .OR. &
        ANY(.NOT.ieee_is_finite(residual_before)) .OR. &
        ANY(.NOT.ieee_is_finite(residual_after))) RETURN
    rc=nf90_create(TRIM(path),IOR(NF90_CLOBBER,NF90_NETCDF4),ncid)
    IF (rc/=NF90_NOERR) RETURN
    IF (.NOT.nc_ok(nf90_def_dim(ncid,'x',nx,xdim)) .OR. &
        .NOT.nc_ok(nf90_def_dim(ncid,'y',ny,ydim)) .OR. &
        .NOT.nc_ok(nf90_def_dim(ncid,'z',nz,zdim)) .OR. &
        .NOT.nc_ok(nf90_def_dim(ncid,'z_interface',nz+1,zinterface_dim)) .OR. &
        .NOT.nc_ok(nf90_def_dim(ncid,'z_spacing',nz-1,zspacing_dim))) GOTO 900
    IF (.NOT.nc_ok(nf90_def_var(ncid,'pressure',NF90_FLOAT,(/zdim/),level_var)) .OR. &
        .NOT.nc_ok(nf90_def_var(ncid,'latitude',NF90_FLOAT,(/xdim,ydim/),lat_var)) .OR. &
        .NOT.nc_ok(nf90_def_var(ncid,'longitude',NF90_FLOAT,(/xdim,ydim/),lon_var))) GOTO 900
    IF (.NOT.nc_ok(nf90_def_var(ncid,'pressure_interface',NF90_DOUBLE, &
          (/xdim,ydim,zinterface_dim/),interface_var)) .OR. &
        .NOT.nc_ok(nf90_def_var(ncid,'cell_dp',NF90_DOUBLE, &
          (/xdim,ydim,zdim/),cell_dp_var)) .OR. &
        .NOT.nc_ok(nf90_def_var(ncid,'level_spacing_dp',NF90_DOUBLE, &
          (/xdim,ydim,zspacing_dim/),spacing_var)) .OR. &
        .NOT.nc_ok(nf90_def_var(ncid,'pressure_mass_measure',NF90_DOUBLE, &
          (/xdim,ydim,zdim/),pressure_mass_var)) .OR. &
        .NOT.nc_ok(nf90_def_var(ncid,'dry_air_mass_measure',NF90_DOUBLE, &
          (/xdim,ydim,zdim/),dry_mass_var)) .OR. &
        .NOT.nc_ok(nf90_def_var(ncid,'surface_pressure',NF90_FLOAT, &
          (/xdim,ydim/),surface_pressure_var)) .OR. &
        .NOT.nc_ok(nf90_def_var(ncid,'omega_top_boundary',NF90_FLOAT, &
          (/xdim,ydim/),omega_top_var)) .OR. &
        .NOT.nc_ok(nf90_def_var(ncid,'omega_bottom_boundary',NF90_FLOAT, &
          (/xdim,ydim/),omega_bottom_var)) .OR. &
        .NOT.nc_ok(nf90_def_var(ncid,'omega_top_boundary_valid',NF90_INT, &
          (/xdim,ydim/),omega_top_valid_var)) .OR. &
        .NOT.nc_ok(nf90_def_var(ncid,'omega_bottom_boundary_valid',NF90_INT, &
          (/xdim,ydim/),omega_bottom_valid_var)) .OR. &
        .NOT.nc_ok(nf90_def_var(ncid,'omega_top_boundary_quality',NF90_INT, &
          (/xdim,ydim/),omega_top_quality_var)) .OR. &
        .NOT.nc_ok(nf90_def_var(ncid,'omega_top_boundary_source',NF90_INT, &
          (/xdim,ydim/),omega_top_source_var)) .OR. &
        .NOT.nc_ok(nf90_def_var(ncid,'omega_bottom_boundary_quality',NF90_INT, &
          (/xdim,ydim/),omega_bottom_quality_var)) .OR. &
        .NOT.nc_ok(nf90_def_var(ncid,'omega_bottom_boundary_source',NF90_INT, &
          (/xdim,ydim/),omega_bottom_source_var))) GOTO 900
    DO k=1,19
      IF (.NOT.nc_ok(nf90_def_var(ncid,TRIM(names(k)),NF90_FLOAT, &
                                  (/xdim,ydim,zdim/),varid(k)))) GOTO 900
    END DO
    DO k=20,21
      IF (.NOT.nc_ok(nf90_def_var(ncid,TRIM(names(k)),NF90_DOUBLE, &
                                  (/xdim,ydim,zdim/),varid(k)))) GOTO 900
    END DO
    DO k=22,36
      IF (.NOT.nc_ok(nf90_def_var(ncid,TRIM(names(k)),NF90_INT, &
                                  (/xdim,ydim,zdim/),varid(k)))) GOTO 900
    END DO
    DO k=1,36
      IF (.NOT.nc_ok(nf90_put_att(ncid,varid(k),'units',TRIM(units(k))))) GOTO 900
      IF (.NOT.nc_ok(nf90_def_var_deflate(ncid,varid(k),1,1,1))) GOTO 900
    END DO
    IF (.NOT.nc_ok(nf90_put_att(ncid,interface_var,'units','Pa')) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,cell_dp_var,'units','Pa')) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,spacing_var,'units','Pa')) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,pressure_mass_var,'units','kg')) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,dry_mass_var,'units','kg dryair')) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,surface_pressure_var,'units','Pa')) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,omega_top_var,'units','Pa s-1')) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,omega_bottom_var,'units','Pa s-1')) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,omega_top_valid_var,'units','1')) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,omega_bottom_valid_var,'units','1')) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,omega_top_quality_var,'units','1')) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,omega_top_source_var,'units','1')) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,omega_bottom_quality_var,'units','1')) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,omega_bottom_source_var,'units','1'))) GOTO 900
    IF (.NOT.nc_ok(nf90_put_att(ncid,varid(28),'long_name', &
      'candidate balance localization support')) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,varid(28),'legacy_name','balance_active'))) GOTO 900
    IF (.NOT.put_global_metadata(ncid,result,config,state_in%pressure%valid_time)) GOTO 900
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'grid_id', &
                                TRIM(state_in%grid%grid_id))) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'canonical_vertical_order', &
                                'bottom_to_top')) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'netcdf_variable_order', &
                                'z,y,x')) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'grid_dx_m', &
                                state_in%grid%dx(1,1))) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'grid_dy_m', &
                                state_in%grid%dy(1,1)))) GOTO 900
    IF (.NOT.nc_ok(nf90_put_att(ncid,level_var,'units','Pa')) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,lat_var,'units','degree_north')) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,lon_var,'units','degree_east'))) GOTO 900
    IF (.NOT.nc_ok(nf90_enddef(ncid))) GOTO 900
    ALLOCATE(levels(nz))
    DO k=1,nz
      levels(k)=state_in%pressure%value(1,1,k)
    END DO
    IF (.NOT.nc_ok(nf90_put_var(ncid,level_var,levels)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,lat_var,state_in%latitude%value)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,lon_var,longitude)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,interface_var, &
          state_in%grid%pressure_interface)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,cell_dp_var,state_in%grid%cell_dp)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,spacing_var, &
          state_in%grid%level_spacing_dp)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,pressure_mass_var, &
          state_in%grid%pressure_mass_measure)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,dry_mass_var, &
          state_in%grid%dry_air_mass_measure)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,surface_pressure_var, &
          state_in%surface_pressure%value)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,omega_top_var, &
          state_in%omega_top_boundary%value)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,omega_bottom_var, &
          state_in%omega_bottom_boundary%value)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,omega_top_quality_var, &
          state_in%omega_top_boundary%quality)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,omega_top_source_var, &
          state_in%omega_top_boundary%source)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,omega_bottom_quality_var, &
          state_in%omega_bottom_boundary%quality)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,omega_bottom_source_var, &
          state_in%omega_bottom_boundary%source))) GOTO 900
    ALLOCATE(boundary_mask(nx,ny))
    boundary_mask=MERGE(1_int32,0_int32,state_in%omega_top_boundary%valid)
    IF (.NOT.nc_ok(nf90_put_var(ncid,omega_top_valid_var,boundary_mask))) GOTO 900
    boundary_mask=MERGE(1_int32,0_int32,state_in%omega_bottom_boundary%valid)
    IF (.NOT.nc_ok(nf90_put_var(ncid,omega_bottom_valid_var,boundary_mask))) GOTO 900
    IF (.NOT.nc_ok(nf90_put_var(ncid,varid(1),state_in%radar_reflectivity%value)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,varid(2),state_in%u%value)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,varid(3),state_in%v%value)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,varid(4),state_in%omega%value)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,varid(5),candidate%u%value)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,varid(6),candidate%v%value)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,varid(7),candidate%omega%value)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,varid(8),candidate%omega_target%value)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,varid(9),state_in%cloud_water%value)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,varid(10),state_in%cloud_ice%value)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,varid(11),state_in%rain%value)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,varid(12),state_in%snow%value)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,varid(13),state_in%graupel%value)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,varid(14),candidate%cloud_water%value)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,varid(15),candidate%cloud_ice%value)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,varid(16),candidate%rain%value)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,varid(17),candidate%snow%value)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,varid(18),candidate%graupel%value)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,varid(19),candidate%balance_beta)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,varid(20),residual_before)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,varid(21),residual_after))) GOTO 900
    ALLOCATE(mask(nx,ny,nz))
    mask=MERGE(1_int32,0_int32,state_in%above_ground)
    IF (.NOT.nc_ok(nf90_put_var(ncid,varid(22),mask))) GOTO 900
    mask=MERGE(1_int32,0_int32,state_in%above_ground .AND. radar_echo_cell( &
      state_in%radar_reflectivity%value,state_in%radar_reflectivity%valid, &
      state_in%radar_reflectivity%quality,state_in%radar_reflectivity%source))
    IF (.NOT.nc_ok(nf90_put_var(ncid,varid(23),mask))) GOTO 900
    mask=MERGE(1_int32,0_int32,candidate%omega_target%valid)
    IF (.NOT.nc_ok(nf90_put_var(ncid,varid(24),mask))) GOTO 900
    IF (.NOT.nc_ok(nf90_put_var(ncid,varid(25),candidate%omega_target%quality))) GOTO 900
    IF (.NOT.nc_ok(nf90_put_var(ncid,varid(26),candidate%omega_target%source))) GOTO 900
    mask=MERGE(1_int32,0_int32,dynamic_target_has_authority( &
      candidate%omega_target%valid,candidate%omega_target%quality, &
      candidate%omega_target%source))
    IF (.NOT.nc_ok(nf90_put_var(ncid,varid(27),mask))) GOTO 900
    mask=MERGE(1_int32,0_int32,candidate%above_ground .AND. &
      balance_beta_active(candidate%balance_beta,config%balance%minimum_beta))
    IF (.NOT.nc_ok(nf90_put_var(ncid,varid(28),mask))) GOTO 900
    mask=MERGE(1_int32,0_int32,result%column%changed)
    IF (.NOT.nc_ok(nf90_put_var(ncid,varid(29),mask))) GOTO 900
    mask=MERGE(1_int32,0_int32,result%balance%changed)
    IF (.NOT.nc_ok(nf90_put_var(ncid,varid(30),mask))) GOTO 900
    mask=MERGE(1_int32,0_int32,result%overall%changed)
    IF (.NOT.nc_ok(nf90_put_var(ncid,varid(31),mask))) GOTO 900
    IF (.NOT.nc_ok(nf90_put_var(ncid,varid(32),candidate%obs_support))) GOTO 900
    IF (.NOT.nc_ok(nf90_put_var(ncid,varid(33),candidate%hydro_support))) GOTO 900
    mask=MERGE(1_int32,0_int32,state_in%above_ground .AND. &
      (radar_echo_cell(state_in%radar_reflectivity%value, &
         state_in%radar_reflectivity%valid,state_in%radar_reflectivity%quality, &
         state_in%radar_reflectivity%source) .OR. &
       radar_no_echo_cell(state_in%radar_reflectivity%value, &
         state_in%radar_reflectivity%valid,state_in%radar_reflectivity%quality, &
         state_in%radar_reflectivity%source)))
    IF (.NOT.nc_ok(nf90_put_var(ncid,varid(34),mask))) GOTO 900
    mask=MERGE(1_int32,0_int32,state_in%above_ground .AND. radar_no_echo_cell( &
      state_in%radar_reflectivity%value,state_in%radar_reflectivity%valid, &
      state_in%radar_reflectivity%quality,state_in%radar_reflectivity%source))
    IF (.NOT.nc_ok(nf90_put_var(ncid,varid(35),mask))) GOTO 900
    mask=MERGE(1_int32,0_int32,state_in%above_ground .AND. radar_missing_cell( &
      state_in%radar_reflectivity%value,state_in%radar_reflectivity%valid, &
      state_in%radar_reflectivity%quality,state_in%radar_reflectivity%source))
    IF (.NOT.nc_ok(nf90_put_var(ncid,varid(36),mask))) GOTO 900
    rc=nf90_close(ncid)
    IF (rc==NF90_NOERR) status=STATUS_OK
    RETURN
900 CONTINUE
    rc=nf90_close(ncid)
  END SUBROUTINE write_shadow_diagnostics

  SUBROUTINE validate_shadow_write_contract(state_in,candidate,operational_state, &
                                            result,config,status,reason)
    USE cloud_bal_pipeline, ONLY: cloud_bal_pipeline_result,cloud_bal_pipeline_config
    TYPE(cloud_bal_state_type), INTENT(IN) :: state_in,candidate,operational_state
    TYPE(cloud_bal_pipeline_result), INTENT(IN) :: result
    TYPE(cloud_bal_pipeline_config), INTENT(IN) :: config
    INTEGER, INTENT(OUT) :: status,reason
    INTEGER :: state_status,state_reason
    REAL(real64) :: flux_terms(7),flux_accounted,flux_error,flux_limit

    status=STATUS_FAILED; reason=REASON_AUTHORITY
    IF (config%requested_mode/=MODE_SHADOW .OR. &
        result%requested_mode/=MODE_SHADOW) RETURN
    IF (.NOT.column_config_valid(config%column)) THEN
      reason=REASON_RANGE
      RETURN
    END IF
    IF (.NOT.pipeline_result_is_coherent(result)) RETURN
    flux_terms=[result%column%numerical%flux_deposited, &
      result%column%numerical%flux_suspended, &
      result%column%numerical%flux_boundary_exit, &
      result%column%numerical%flux_terrain_intercept, &
      result%column%numerical%flux_observation_blocked, &
      result%column%numerical%flux_no_echo_blocked, &
      result%column%numerical%flux_microphysical_loss]
    IF (.NOT.ieee_is_finite(result%column%numerical%flux_input) .OR. &
        result%column%numerical%flux_input<0.0_real64 .OR. &
        ANY(.NOT.ieee_is_finite(flux_terms)) .OR. ANY(flux_terms<0.0_real64) .OR. &
        .NOT.ieee_is_finite(result%column%numerical%ledger_error) .OR. &
        result%column%numerical%ledger_error<0.0_real64) THEN
      reason=REASON_GATE
      RETURN
    END IF
    flux_accounted=SUM(flux_terms)
    flux_error=ABS(result%column%numerical%flux_input-flux_accounted)
    flux_limit=config%column%ledger_absolute_tolerance+ &
      config%column%ledger_relative_tolerance* &
      MAX(ABS(result%column%numerical%flux_input),ABS(flux_accounted))
    IF (flux_error>flux_limit .OR. &
        ABS(result%column%numerical%ledger_error-flux_error)> &
          64.0_real64*EPSILON(1.0_real64)*MAX(1.0_real64,flux_error) .OR. &
        result%column%numerical%transport_required_substeps<0 .OR. &
        result%column%numerical%transport_required_substeps> &
          config%column%maximum_transport_substeps) THEN
      reason=REASON_GATE
      RETURN
    END IF
    IF (.NOT.stage_masks_valid(result,state_in%grid%nx,state_in%grid%ny, &
                              state_in%grid%nz)) THEN
      reason=REASON_SHAPE
      RETURN
    END IF

    CALL validate_canonical_state(state_in,.FALSE.,.TRUE.,state_status,state_reason,.FALSE.)
    IF (state_status/=STATUS_OK) THEN
      reason=state_reason
      RETURN
    END IF
    IF (.NOT.writer_geometry_is_representable(state_in)) THEN
      reason=REASON_METADATA
      RETURN
    END IF
    IF (.NOT.copied_diagnostic_boundary_contract_valid(state_in) .OR. &
        .NOT.copied_diagnostic_boundary_contract_valid(candidate) .OR. &
        .NOT.copied_diagnostic_boundary_contract_valid(operational_state)) THEN
      reason=REASON_METADATA
      RETURN
    END IF
    IF (.NOT.real_radar_contract_valid(state_in) .OR. &
        .NOT.real_radar_contract_valid(candidate) .OR. &
        .NOT.real_radar_contract_valid(operational_state)) THEN
      reason=REASON_RADAR_CONTRACT
      RETURN
    END IF
    IF (.NOT.los_is_empty(state_in%radar_los) .OR. &
        .NOT.los_is_empty(candidate%radar_los) .OR. &
        .NOT.los_is_empty(operational_state%radar_los)) THEN
      reason=REASON_RADAR_CONTRACT
      RETURN
    END IF
    IF (.NOT.cloud_authority_is_absent(state_in) .OR. &
        .NOT.cloud_authority_is_absent(candidate) .OR. &
        .NOT.cloud_authority_is_absent(operational_state)) THEN
      reason=REASON_AUTHORITY
      RETURN
    END IF
    ! The SHADOW authority boundary is stricter than ordinary state validity:
    ! operational fields must be identical and candidate changes are limited to
    ! the explicitly permitted pipeline fields.  Radar/LOS contracts are checked
    ! first so their dedicated reason code is preserved.
    IF (.NOT.canonical_states_equal(state_in,operational_state)) RETURN
    IF (.NOT.canonical_states_equal(state_in,candidate,.TRUE.)) RETURN
    CALL validate_canonical_state(candidate,.FALSE.,.TRUE.,state_status,state_reason,.FALSE.)
    IF (state_status/=STATUS_OK) THEN
      reason=state_reason
      RETURN
    END IF
    CALL validate_canonical_state(operational_state,.FALSE.,.TRUE.,state_status, &
                                  state_reason,.FALSE.)
    IF (state_status/=STATUS_OK) THEN
      reason=state_reason
      RETURN
    END IF
    IF (.NOT.candidate_result_is_coherent(state_in,candidate,result)) RETURN

    status=STATUS_OK; reason=REASON_NONE
  END SUBROUTINE validate_shadow_write_contract

  LOGICAL FUNCTION pipeline_result_is_coherent(result)
    USE cloud_bal_pipeline, ONLY: cloud_bal_pipeline_result
    TYPE(cloud_bal_pipeline_result), INTENT(IN) :: result
    pipeline_result_is_coherent=.FALSE.
    IF (result%column%status/=STATUS_OK .OR. &
        result%column%reason_code/=REASON_NONE) RETURN
    SELECT CASE(result%status)
    CASE(STATUS_OK)
      IF (result%reason_code/=REASON_NONE .OR. &
          result%balance%status/=STATUS_OK .OR. &
          result%balance%reason_code/=REASON_NONE .OR. &
          result%overall%status/=STATUS_OK .OR. &
          result%overall%reason_code/=REASON_NONE) RETURN
    CASE(STATUS_DEGRADED)
      IF (result%reason_code/=REASON_GATE .OR. &
          result%balance%status/=STATUS_DEGRADED .OR. &
          result%balance%reason_code/=REASON_GATE .OR. &
          result%overall%status/=STATUS_DEGRADED .OR. &
          result%overall%reason_code/=REASON_GATE) RETURN
    CASE DEFAULT
      RETURN
    END SELECT
    pipeline_result_is_coherent=.TRUE.
  END FUNCTION pipeline_result_is_coherent

  LOGICAL FUNCTION cloud_authority_is_absent(state)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    INTEGER :: expected(3)
    cloud_authority_is_absent=.FALSE.
    expected=(/state%grid%nx,state%grid%ny,state%grid%nz/)
    IF (.NOT.ALLOCATED(state%cloud_fraction%valid) .OR. &
        .NOT.ALLOCATED(state%cloud_fraction%quality) .OR. &
        .NOT.ALLOCATED(state%cloud_fraction%source) .OR. &
        .NOT.ALLOCATED(state%cloud_type%valid) .OR. &
        .NOT.ALLOCATED(state%cloud_type%quality) .OR. &
        .NOT.ALLOCATED(state%cloud_type%source)) RETURN
    IF (ANY(SHAPE(state%cloud_fraction%valid)/=expected) .OR. &
        ANY(SHAPE(state%cloud_type%valid)/=expected)) RETURN
    cloud_authority_is_absent= &
      .NOT.ANY(cell_is_usable(state%cloud_fraction%valid, &
        state%cloud_fraction%quality,state%cloud_fraction%source)) .AND. &
      .NOT.ANY(cell_is_usable(state%cloud_type%valid, &
        state%cloud_type%quality,state%cloud_type%source))
  END FUNCTION cloud_authority_is_absent

  SUBROUTINE open_case_file(path,expected_z,valid_time,ncid,levels,dx,dy,status)
    CHARACTER(LEN=*), INTENT(IN) :: path
    INTEGER, INTENT(IN) :: expected_z
    INTEGER(int64), INTENT(IN) :: valid_time
    INTEGER, INTENT(OUT) :: ncid,status
    REAL(real64), INTENT(OUT) :: levels(NZ),dx,dy
    REAL(real64) :: file_time
    status=STATUS_FAILED; ncid=-1; levels=0.0_real64; dx=0.0_real64; dy=0.0_real64
    IF (.NOT.nc_ok(nf90_open(TRIM(path),NF90_NOWRITE,ncid))) THEN
      WRITE(*,'(A)') 'adapter_error=open:'//TRIM(path); RETURN
    END IF
    IF (.NOT.dimensions_are(ncid,expected_z)) THEN
      WRITE(*,'(A)') 'adapter_error=dimensions:'//TRIM(path); GOTO 900
    END IF
    IF (.NOT.read_scalar(ncid,'valtime',file_time)) THEN
      WRITE(*,'(A)') 'adapter_error=valtime-read:'//TRIM(path); GOTO 900
    END IF
    IF (ABS(file_time-REAL(valid_time,real64))>0.5_real64) THEN
      WRITE(*,'(A)') 'adapter_error=valtime-mismatch:'//TRIM(path); GOTO 900
    END IF
    IF (expected_z==NZ) THEN
      IF (.NOT.read_vector(ncid,'level',levels)) THEN
        WRITE(*,'(A)') 'adapter_error=level-read:'//TRIM(path); GOTO 900
      END IF
      IF (.NOT.levels_are_native(levels)) THEN
        WRITE(*,'(A)') 'adapter_error=level-order:'//TRIM(path); GOTO 900
      END IF
    END IF
    IF (.NOT.read_grid_spacing_m(ncid,'Dx',dx) .OR. &
        .NOT.read_grid_spacing_m(ncid,'Dy',dy)) THEN
      WRITE(*,'(A)') 'adapter_error=grid-spacing-read:'//TRIM(path); GOTO 900
    END IF
    IF (ABS(dx-5000.0_real64)>1.0e-6_real64 .OR. &
        ABS(dy-5000.0_real64)>1.0e-6_real64) THEN
      WRITE(*,'(A)') 'adapter_error=grid-spacing-value:'//TRIM(path); GOTO 900
    END IF
    status=STATUS_OK
    RETURN
900 CONTINUE
    CALL close_file(ncid,status)
  END SUBROUTINE open_case_file

  SUBROUTINE open_surface_file(path,valid_time,ncid,dx,dy,status)
    CHARACTER(LEN=*), INTENT(IN) :: path
    INTEGER(int64), INTENT(IN) :: valid_time
    INTEGER, INTENT(OUT) :: ncid,status
    REAL(real64), INTENT(OUT) :: dx,dy
    REAL(real64) :: unused_levels(NZ)
    CALL open_case_file(path,1,valid_time,ncid,unused_levels,dx,dy,status)
  END SUBROUTINE open_surface_file

  SUBROUTINE open_static_file(path,ncid,status)
    CHARACTER(LEN=*), INTENT(IN) :: path
    INTEGER, INTENT(OUT) :: ncid,status
    status=STATUS_FAILED; ncid=-1
    IF (.NOT.nc_ok(nf90_open(TRIM(path),NF90_NOWRITE,ncid))) RETURN
    IF (.NOT.dimensions_are(ncid,1)) THEN
      CALL close_file(ncid,status)
      RETURN
    END IF
    status=STATUS_OK
  END SUBROUTINE open_static_file

  SUBROUTINE close_file(ncid,status)
    INTEGER, INTENT(INOUT) :: ncid
    INTEGER, INTENT(INOUT), OPTIONAL :: status
    INTEGER :: close_status
    IF (ncid>=0) THEN
      close_status=nf90_close(ncid)
      IF (close_status/=NF90_NOERR .AND. PRESENT(status)) status=STATUS_FAILED
      ncid=-1
    END IF
  END SUBROUTINE close_file

  LOGICAL FUNCTION stage_masks_valid(result,nx,ny,nz)
    USE cloud_bal_pipeline, ONLY: cloud_bal_pipeline_result
    TYPE(cloud_bal_pipeline_result), INTENT(IN) :: result
    INTEGER, INTENT(IN) :: nx,ny,nz
    INTEGER :: expected(3)
    expected=(/nx,ny,nz/)
    stage_masks_valid=.FALSE.
    IF (.NOT.ALLOCATED(result%column%changed) .OR. &
        .NOT.ALLOCATED(result%balance%changed) .OR. &
        .NOT.ALLOCATED(result%overall%changed)) RETURN
    stage_masks_valid=ALL(SHAPE(result%column%changed)==expected) .AND. &
      ALL(SHAPE(result%balance%changed)==expected) .AND. &
      ALL(SHAPE(result%overall%changed)==expected)
  END FUNCTION stage_masks_valid

  LOGICAL FUNCTION real_radar_contract_valid(state)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    INTEGER :: expected(3)
    real_radar_contract_valid=.FALSE.
    expected=(/state%grid%nx,state%grid%ny,state%grid%nz/)
    IF (.NOT.ALLOCATED(state%radar_reflectivity%value) .OR. &
        .NOT.ALLOCATED(state%radar_reflectivity%valid) .OR. &
        .NOT.ALLOCATED(state%radar_reflectivity%quality) .OR. &
        .NOT.ALLOCATED(state%radar_reflectivity%source)) RETURN
    IF (ANY(SHAPE(state%radar_reflectivity%value)/=expected) .OR. &
        ANY(SHAPE(state%radar_reflectivity%valid)/=expected) .OR. &
        ANY(SHAPE(state%radar_reflectivity%quality)/=expected) .OR. &
        ANY(SHAPE(state%radar_reflectivity%source)/=expected)) RETURN
    IF (state%radar_reflectivity%valid_time/=state%pressure%valid_time .OR. &
        TRIM(state%radar_reflectivity%unit)/='dBZ') RETURN
    IF (ANY(state%radar_reflectivity%valid .AND. .NOT.state%above_ground) .OR. &
        ANY(state%radar_reflectivity%valid .AND. .NOT.radar_echo_cell( &
          state%radar_reflectivity%value,state%radar_reflectivity%valid, &
          state%radar_reflectivity%quality,state%radar_reflectivity%source))) RETURN
    IF (ANY(state%radar_reflectivity%valid .AND. &
            (.NOT.ieee_is_finite(state%radar_reflectivity%value) .OR. &
             state%radar_reflectivity%value<MINIMUM_USABLE_DBZ .OR. &
             state%radar_reflectivity%value>100.0_real32))) RETURN
    IF (ANY(.NOT.state%radar_reflectivity%valid .AND. &
        .NOT.((state%above_ground .AND. radar_no_echo_cell( &
          state%radar_reflectivity%value,state%radar_reflectivity%valid, &
          state%radar_reflectivity%quality,state%radar_reflectivity%source)) .OR. &
          radar_missing_cell(state%radar_reflectivity%value, &
            state%radar_reflectivity%valid,state%radar_reflectivity%quality, &
            state%radar_reflectivity%source)))) RETURN
    real_radar_contract_valid=.TRUE.
  END FUNCTION real_radar_contract_valid

  PURE ELEMENTAL LOGICAL FUNCTION radar_tid_value_valid(value,has_value)
    REAL(real32), INTENT(IN) :: value
    LOGICAL, INTENT(IN) :: has_value
    INTEGER :: code
    radar_tid_value_valid=.TRUE.
    IF (.NOT.has_value) RETURN
    IF (.NOT.ieee_is_finite(value) .OR. ABS(value)>10.5_real32) THEN
      radar_tid_value_valid=.FALSE.
      RETURN
    END IF
    code=NINT(value)
    radar_tid_value_valid=ABS(value-REAL(code,real32))<= &
      16.0_real32*EPSILON(1.0_real32) .AND. &
      (code==NINT(RADAR_NO_ECHO_DBZ) .OR. (code>=0 .AND. code<=2))
  END FUNCTION radar_tid_value_valid

  PURE ELEMENTAL LOGICAL FUNCTION radar_tid_is_mixed(value,has_value)
    REAL(real32), INTENT(IN) :: value
    LOGICAL, INTENT(IN) :: has_value
    radar_tid_is_mixed=.FALSE.
    IF (.NOT.radar_tid_value_valid(value,has_value) .OR. .NOT.has_value) RETURN
    radar_tid_is_mixed=NINT(value)==2
  END FUNCTION radar_tid_is_mixed

  LOGICAL FUNCTION candidate_result_is_coherent(background,candidate,result)
    USE cloud_bal_pipeline, ONLY: cloud_bal_pipeline_result
    TYPE(cloud_bal_state_type), INTENT(IN) :: background,candidate
    TYPE(cloud_bal_pipeline_result), INTENT(IN) :: result
    LOGICAL, ALLOCATABLE :: expected(:,:,:)
    INTEGER :: nx,ny,nz

    candidate_result_is_coherent=.FALSE.
    nx=background%grid%nx; ny=background%grid%ny; nz=background%grid%nz
    ALLOCATE(expected(nx,ny,nz))

    expected=real_value_changed(background%u%value,candidate%u%value) .OR. &
             real_value_changed(background%v%value,candidate%v%value) .OR. &
             real_value_changed(background%omega%value,candidate%omega%value)
    IF (ANY(expected .NEQV. result%balance%changed)) RETURN
    IF (.NOT.dynamic_field_is_coherent(background%u,candidate%u) .OR. &
        .NOT.dynamic_field_is_coherent(background%v,candidate%v) .OR. &
        .NOT.dynamic_field_is_coherent(background%omega,candidate%omega)) RETURN

    expected=column_changed_mask(background,candidate)
    IF (ANY(expected .NEQV. result%column%changed)) RETURN
    IF (ANY(expected .AND. radar_no_echo_cell( &
        background%radar_reflectivity%value, &
        background%radar_reflectivity%valid, &
        background%radar_reflectivity%quality, &
        background%radar_reflectivity%source))) RETURN
    IF (ANY((result%column%changed .OR. result%balance%changed) .NEQV. &
            result%overall%changed)) RETURN
    candidate_result_is_coherent=.TRUE.
  END FUNCTION candidate_result_is_coherent

  LOGICAL FUNCTION dynamic_field_is_coherent(background,candidate)
    TYPE(field3d), INTENT(IN) :: background,candidate
    LOGICAL, ALLOCATABLE :: changed(:,:,:)
    INTEGER(int32), ALLOCATABLE :: expected_source(:,:,:)

    dynamic_field_is_coherent=.FALSE.
    IF (background%valid_time/=candidate%valid_time .OR. &
        background%unit/=candidate%unit) RETURN
    IF (ANY(background%valid .NEQV. candidate%valid) .OR. &
        ANY(background%quality/=candidate%quality)) RETURN
    ALLOCATE(changed, SOURCE=real_value_changed(background%value,candidate%value))
    ALLOCATE(expected_source, SOURCE=background%source)
    WHERE(changed)
      expected_source=IOR(expected_source,SOURCE_BALANCE_OPERATOR)
    END WHERE
    IF (ANY(candidate%source/=expected_source)) RETURN
    dynamic_field_is_coherent=.TRUE.
  END FUNCTION dynamic_field_is_coherent

  PURE ELEMENTAL LOGICAL FUNCTION real_value_changed(left,right)
    REAL(real32), INTENT(IN) :: left,right
    real_value_changed=TRANSFER(left,0_int32)/=TRANSFER(right,0_int32)
  END FUNCTION real_value_changed

  LOGICAL FUNCTION writer_geometry_is_representable(state)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    INTEGER :: i,j,k
    writer_geometry_is_representable=.FALSE.
    DO j=1,state%grid%ny; DO i=1,state%grid%nx
      IF (TRANSFER(state%grid%dx(i,j),0_int64)/= &
          TRANSFER(state%grid%dx(1,1),0_int64) .OR. &
          TRANSFER(state%grid%dy(i,j),0_int64)/= &
          TRANSFER(state%grid%dy(1,1),0_int64)) RETURN
      DO k=1,state%grid%nz
        IF (TRANSFER(state%pressure%value(i,j,k),0_int32)/= &
            TRANSFER(state%pressure%value(1,1,k),0_int32)) RETURN
      END DO
    END DO; END DO
    writer_geometry_is_representable=.TRUE.
  END FUNCTION writer_geometry_is_representable

  LOGICAL FUNCTION los_is_empty(los)
    TYPE(radar_los_observation_set), INTENT(IN) :: los
    los_is_empty=.FALSE.
    IF (los%is_present .OR. los%nradar/=0 .OR. &
        los%vrad_representation/=0_int32 .OR. los%has_colocated_dbz .OR. &
        los%has_spectrum_width .OR. &
        los%vrad%valid_time/=0_int64 .OR. LEN_TRIM(los%vrad%unit)/=0 .OR. &
        los%nyquist%valid_time/=0_int64 .OR. LEN_TRIM(los%nyquist%unit)/=0 .OR. &
        los%sigma_vrad%valid_time/=0_int64 .OR. &
        LEN_TRIM(los%sigma_vrad%unit)/=0 .OR. &
        los%colocated_dbz%valid_time/=0_int64 .OR. &
        LEN_TRIM(los%colocated_dbz%unit)/=0 .OR. &
        los%spectrum_width%valid_time/=0_int64 .OR. &
        LEN_TRIM(los%spectrum_width%unit)/=0) RETURN
    IF (.NOT.field4d_is_empty(los%vrad) .OR. &
        .NOT.field4d_is_empty(los%nyquist) .OR. &
        .NOT.field4d_is_empty(los%sigma_vrad) .OR. &
        .NOT.field4d_is_empty(los%colocated_dbz) .OR. &
        .NOT.field4d_is_empty(los%spectrum_width)) RETURN
    IF (ALLOCATED(los%beam) .OR. ALLOCATED(los%observation_id_hi) .OR. &
        ALLOCATED(los%observation_id_lo) .OR. ALLOCATED(los%usage) .OR. &
        ALLOCATED(los%radar_id) .OR. ALLOCATED(los%observation_time) .OR. &
        ALLOCATED(los%site_lat) .OR. ALLOCATED(los%site_lon) .OR. &
        ALLOCATED(los%site_height) .OR. ALLOCATED(los%wavelength) .OR. &
        ALLOCATED(los%los_support) .OR. ALLOCATED(los%geometry_condition) .OR. &
        ALLOCATED(los%geometry_rank)) RETURN
    los_is_empty=.TRUE.
  END FUNCTION los_is_empty

  LOGICAL FUNCTION field4d_is_empty(field)
    TYPE(field4d), INTENT(IN) :: field
    field4d_is_empty=.NOT.ALLOCATED(field%value) .AND. &
      .NOT.ALLOCATED(field%valid) .AND. .NOT.ALLOCATED(field%quality) .AND. &
      .NOT.ALLOCATED(field%source)
  END FUNCTION field4d_is_empty

  SUBROUTINE read_real3(ncid,name,unit_a,unit_b,data,valid,status)
    INTEGER, INTENT(IN) :: ncid
    CHARACTER(LEN=*), INTENT(IN) :: name,unit_a,unit_b
    REAL(real32), INTENT(OUT) :: data(NX,NY,NZ)
    LOGICAL, INTENT(OUT) :: valid(NX,NY,NZ)
    INTEGER, INTENT(OUT) :: status
    REAL(real32), ALLOCATABLE :: work(:,:,:,:)
    INTEGER :: varid,rc
    status=STATUS_FAILED; data=0.0_real32; valid=.FALSE.
    rc=nf90_inq_varid(ncid,TRIM(name),varid)
    IF (.NOT.nc_ok(rc)) THEN
      WRITE(*,'(A)') 'adapter_error=missing-variable:'//TRIM(name); RETURN
    END IF
    IF (.NOT.variable_unit_is(ncid,varid,unit_a,unit_b)) THEN
      WRITE(*,'(A)') 'adapter_error=units:'//TRIM(name); RETURN
    END IF
    IF (.NOT.variable_layout_is(ncid,varid,NF90_FLOAT, &
        [CHARACTER(LEN=6) :: 'x','y','z','record'])) THEN
      WRITE(*,'(A)') 'adapter_error=layout:'//TRIM(name); RETURN
    END IF
    ALLOCATE(work(NX,NY,NZ,1))
    rc=nf90_get_var(ncid,varid,work)
    IF (.NOT.nc_ok(rc)) THEN
      WRITE(*,'(A)') 'adapter_error=read:'//TRIM(name)//':'//TRIM(nf90_strerror(rc)); RETURN
    END IF
    data=work(:,:,:,1)
    valid=ieee_is_finite(data) .AND. ABS(data)<RAW_MISSING_LIMIT
    status=STATUS_OK
  END SUBROUTINE read_real3

  SUBROUTINE read_real2(ncid,name,unit_a,unit_b,data,valid,status)
    INTEGER, INTENT(IN) :: ncid
    CHARACTER(LEN=*), INTENT(IN) :: name,unit_a,unit_b
    REAL(real32), INTENT(OUT) :: data(NX,NY)
    LOGICAL, INTENT(OUT) :: valid(NX,NY)
    INTEGER, INTENT(OUT) :: status
    REAL(real32), ALLOCATABLE :: work(:,:,:,:)
    INTEGER :: varid,rc
    status=STATUS_FAILED; data=0.0_real32; valid=.FALSE.
    rc=nf90_inq_varid(ncid,TRIM(name),varid)
    IF (.NOT.nc_ok(rc)) THEN
      WRITE(*,'(A)') 'adapter_error=missing-variable:'//TRIM(name); RETURN
    END IF
    IF (.NOT.variable_unit_is(ncid,varid,unit_a,unit_b)) THEN
      WRITE(*,'(A)') 'adapter_error=units:'//TRIM(name); RETURN
    END IF
    IF (.NOT.variable_layout_is(ncid,varid,NF90_FLOAT, &
        [CHARACTER(LEN=6) :: 'x','y','z','record'])) THEN
      WRITE(*,'(A)') 'adapter_error=layout:'//TRIM(name); RETURN
    END IF
    ALLOCATE(work(NX,NY,1,1))
    rc=nf90_get_var(ncid,varid,work)
    IF (.NOT.nc_ok(rc)) THEN
      WRITE(*,'(A)') 'adapter_error=read:'//TRIM(name)//':'//TRIM(nf90_strerror(rc)); RETURN
    END IF
    data=work(:,:,1,1)
    valid=ieee_is_finite(data) .AND. ABS(data)<RAW_MISSING_LIMIT
    status=STATUS_OK
  END SUBROUTINE read_real2

  SUBROUTINE assign_reversed_core(raw,raw_valid,domain,field,source,scale,status)
    REAL(real32), INTENT(IN) :: raw(NX,NY,NZ)
    LOGICAL, INTENT(IN) :: raw_valid(NX,NY,NZ),domain(NX,NY,NZ)
    TYPE(field3d), INTENT(INOUT) :: field
    INTEGER(int32), INTENT(IN) :: source
    REAL(real64), INTENT(IN) :: scale
    INTEGER, INTENT(OUT) :: status
    INTEGER :: k,source_k
    LOGICAL :: usable(NX,NY)
    status=STATUS_FAILED
    DO k=1,NZ
      source_k=NZ+1-k; usable=domain(:,:,k) .AND. raw_valid(:,:,source_k)
      IF (ANY(domain(:,:,k) .AND. .NOT.usable)) RETURN
      field%value(:,:,k)=MERGE(REAL(scale*REAL(raw(:,:,source_k),real64),real32), &
                               0.0_real32,usable)
      CALL mark_real_field(field,k,usable,source)
    END DO
    status=STATUS_OK
  END SUBROUTINE assign_reversed_core

  PURE LOGICAL FUNCTION reversed_coverage_is_complete(raw_valid,domain)
    LOGICAL, INTENT(IN) :: raw_valid(NX,NY,NZ),domain(NX,NY,NZ)
    INTEGER :: k,source_k
    reversed_coverage_is_complete=.FALSE.
    DO k=1,NZ
      source_k=NZ+1-k
      IF (ANY(domain(:,:,k) .AND. .NOT.raw_valid(:,:,source_k))) RETURN
    END DO
    reversed_coverage_is_complete=.TRUE.
  END FUNCTION reversed_coverage_is_complete

  SUBROUTINE assign_specific_humidity(raw,raw_valid,state,status)
    REAL(real32), INTENT(IN) :: raw(NX,NY,NZ)
    LOGICAL, INTENT(IN) :: raw_valid(NX,NY,NZ)
    TYPE(cloud_bal_state_type), INTENT(INOUT) :: state
    INTEGER, INTENT(OUT) :: status
    INTEGER :: k,source_k
    LOGICAL :: usable(NX,NY)
    REAL(real32) :: q(NX,NY)
    status=STATUS_FAILED
    DO k=1,NZ
      source_k=NZ+1-k; q=raw(:,:,source_k)
      usable=state%above_ground(:,:,k) .AND. raw_valid(:,:,source_k) .AND. &
             q>=0.0_real32 .AND. q<1.0_real32
      IF (ANY(state%above_ground(:,:,k) .AND. .NOT.usable)) RETURN
      WHERE(usable) state%vapor%value(:,:,k)=q/(1.0_real32-q)
      CALL mark_real_field(state%vapor,k,usable,SOURCE_BACKGROUND_MODEL)
    END DO
    status=STATUS_OK
  END SUBROUTINE assign_specific_humidity

  SUBROUTINE read_and_assign_hydrometeor(ncid,name,state,field,raw,raw_valid,status)
    INTEGER, INTENT(IN) :: ncid
    CHARACTER(LEN=*), INTENT(IN) :: name
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    TYPE(field3d), INTENT(INOUT) :: field
    REAL(real32), INTENT(INOUT) :: raw(NX,NY,NZ)
    LOGICAL, INTENT(INOUT) :: raw_valid(NX,NY,NZ)
    INTEGER, INTENT(OUT) :: status
    INTEGER :: k,source_k,i,j
    REAL(real64) :: rho_d
    LOGICAL :: usable(NX,NY)
    CALL read_real3(ncid,name,'kg/m**3','kgm-3',raw,raw_valid,status)
    IF (status/=STATUS_OK) RETURN
    DO k=1,NZ
      source_k=NZ+1-k
      usable=state%above_ground(:,:,k) .AND. raw_valid(:,:,source_k) .AND. &
             raw(:,:,source_k)>=0.0_real32
      IF (ANY(state%above_ground(:,:,k) .AND. .NOT.usable)) THEN
        status=STATUS_FAILED; RETURN
      END IF
      DO j=1,NY; DO i=1,NX
        IF (.NOT.usable(i,j)) CYCLE
        rho_d=dry_density(REAL(state%pressure%value(i,j,k),real64), &
          REAL(state%temperature%value(i,j,k),real64), &
          REAL(state%vapor%value(i,j,k),real64))
        IF (rho_d<=0.0_real64) THEN; status=STATUS_FAILED; RETURN; END IF
        field%value(i,j,k)=REAL(REAL(raw(i,j,source_k),real64)/rho_d,real32)
      END DO; END DO
      CALL mark_real_field(field,k,usable,SOURCE_BACKGROUND_MODEL)
    END DO
    status=STATUS_OK
  END SUBROUTINE read_and_assign_hydrometeor

  SUBROUTINE assign_surface(raw,valid,field,source)
    REAL(real32), INTENT(IN) :: raw(NX,NY)
    LOGICAL, INTENT(IN) :: valid(NX,NY)
    TYPE(field2d), INTENT(INOUT) :: field
    INTEGER(int32), INTENT(IN) :: source
    field%value=MERGE(raw,0.0_real32,valid)
    field%valid=valid
    field%quality=MERGE(0_int32,QUALITY_RAW_MISSING,valid)
    field%source=MERGE(source,0_int32,valid)
  END SUBROUTINE assign_surface

  SUBROUTINE mark_real_field(field,k,valid,source)
    TYPE(field3d), INTENT(INOUT) :: field
    INTEGER, INTENT(IN) :: k
    LOGICAL, INTENT(IN) :: valid(NX,NY)
    INTEGER(int32), INTENT(IN) :: source
    field%valid(:,:,k)=valid
    field%quality(:,:,k)=MERGE(0_int32,QUALITY_RAW_MISSING,valid)
    field%source(:,:,k)=MERGE(source,0_int32,valid)
  END SUBROUTINE mark_real_field

  SUBROUTINE restrict_state_to_domain(state)
    TYPE(cloud_bal_state_type), INTENT(INOUT) :: state
    CALL restrict_coordinate_field(state%pressure,state%above_ground)
    CALL restrict_real_field(state%temperature,state%above_ground)
    CALL restrict_real_field(state%vapor,state%above_ground)
    CALL restrict_real_field(state%u,state%above_ground)
    CALL restrict_real_field(state%v,state%above_ground)
    CALL restrict_real_field(state%omega,state%above_ground)
    CALL restrict_real_field(state%omega_target,state%above_ground)
    CALL restrict_real_field(state%geopotential,state%above_ground)
    CALL restrict_real_field(state%cloud_fraction,state%above_ground)
    CALL restrict_real_field(state%radar_reflectivity,state%above_ground)
    CALL restrict_real_field(state%cloud_water,state%above_ground)
    CALL restrict_real_field(state%cloud_ice,state%above_ground)
    CALL restrict_real_field(state%rain,state%above_ground)
    CALL restrict_real_field(state%snow,state%above_ground)
    CALL restrict_real_field(state%graupel,state%above_ground)
    CALL restrict_real_field(state%vt_z_mean,state%above_ground)
    CALL restrict_real_field(state%vt_z_sigma,state%above_ground)
    CALL restrict_integer_field(state%cloud_type,state%above_ground)
    CALL restrict_integer_field(state%precipitation_phase,state%above_ground)
    CALL restrict_integer_field(state%lightning_support,state%above_ground)
    WHERE(.NOT.state%above_ground)
      state%obs_support=0_int32
      state%hydro_support=0_int32
      state%balance_beta=0.0_real32
    END WHERE
  END SUBROUTINE restrict_state_to_domain

  SUBROUTINE restrict_coordinate_field(field,domain)
    TYPE(field3d), INTENT(INOUT) :: field
    LOGICAL, INTENT(IN) :: domain(:,:,:)
    WHERE(.NOT.domain)
      field%valid=.FALSE.
      field%quality=QUALITY_RAW_MISSING
      field%source=0_int32
    END WHERE
  END SUBROUTINE restrict_coordinate_field

  SUBROUTINE restrict_real_field(field,domain)
    TYPE(field3d), INTENT(INOUT) :: field
    LOGICAL, INTENT(IN) :: domain(:,:,:)
    WHERE(.NOT.domain)
      field%value=0.0_real32
      field%valid=.FALSE.
      field%quality=QUALITY_RAW_MISSING
      field%source=0_int32
    END WHERE
  END SUBROUTINE restrict_real_field

  SUBROUTINE restrict_integer_field(field,domain)
    TYPE(integer_field3d), INTENT(INOUT) :: field
    LOGICAL, INTENT(IN) :: domain(:,:,:)
    WHERE(.NOT.domain)
      field%value=0_int32
      field%valid=.FALSE.
      field%quality=QUALITY_RAW_MISSING
      field%source=0_int32
    END WHERE
  END SUBROUTINE restrict_integer_field

  SUBROUTINE set_copied_interior_omega_boundaries(state,status)
    TYPE(cloud_bal_state_type), INTENT(INOUT) :: state
    INTEGER, INTENT(OUT) :: status
    INTEGER :: i,j,k
    status=STATUS_FAILED
    DO j=1,NY; DO i=1,NX
      IF (.NOT.state%omega%valid(i,j,NZ)) RETURN
      state%omega_top_boundary%value(i,j)=state%omega%value(i,j,NZ)
      state%omega_top_boundary%valid(i,j)=.TRUE.
      state%omega_top_boundary%quality(i,j)=IOR(QUALITY_LEGACY_PROVENANCE, &
        QUALITY_BOUNDARY_INTERIOR_COPY)
      state%omega_top_boundary%source(i,j)=SOURCE_ANALYZED_WIND
      DO k=1,NZ
        IF (.NOT.state%above_ground(i,j,k)) CYCLE
        state%omega_bottom_boundary%value(i,j)=state%omega%value(i,j,k)
        state%omega_bottom_boundary%valid(i,j)=.TRUE.
        state%omega_bottom_boundary%quality(i,j)=IOR(QUALITY_LEGACY_PROVENANCE, &
          QUALITY_BOUNDARY_INTERIOR_COPY)
        state%omega_bottom_boundary%source(i,j)=SOURCE_ANALYZED_WIND
        EXIT
      END DO
      IF (.NOT.state%omega_bottom_boundary%valid(i,j)) RETURN
    END DO; END DO
    status=STATUS_OK
  END SUBROUTINE set_copied_interior_omega_boundaries

  LOGICAL FUNCTION dimensions_are(ncid,nz)
    INTEGER, INTENT(IN) :: ncid,nz
    dimensions_are=dimension_is(ncid,'x',NX) .AND. dimension_is(ncid,'y',NY) .AND. &
                   dimension_is(ncid,'z',nz) .AND. dimension_is(ncid,'record',1)
  END FUNCTION dimensions_are

  LOGICAL FUNCTION dimension_is(ncid,name,expected)
    INTEGER, INTENT(IN) :: ncid,expected
    CHARACTER(LEN=*), INTENT(IN) :: name
    INTEGER :: dimid,length
    dimension_is=.FALSE.
    IF (.NOT.nc_ok(nf90_inq_dimid(ncid,TRIM(name),dimid))) RETURN
    IF (.NOT.nc_ok(nf90_inquire_dimension(ncid,dimid,LEN=length))) RETURN
    dimension_is=length==expected
  END FUNCTION dimension_is

  LOGICAL FUNCTION read_scalar(ncid,name,value)
    INTEGER, INTENT(IN) :: ncid
    CHARACTER(LEN=*), INTENT(IN) :: name
    REAL(real64), INTENT(OUT) :: value
    INTEGER :: varid
    REAL(real64) :: work(1)
    read_scalar=.FALSE.; value=0.0_real64
    IF (.NOT.nc_ok(nf90_inq_varid(ncid,TRIM(name),varid))) RETURN
    SELECT CASE(TRIM(name))
    CASE('valtime')
      IF (.NOT.variable_layout_is(ncid,varid,NF90_DOUBLE, &
          [CHARACTER(LEN=6) :: 'record']) .OR. &
          .NOT.variable_unit_is(ncid,varid, &
            'seconds since (1970-1-1 00:00:00.0)', &
            'seconds since 1970-01-01 00:00:00')) RETURN
    CASE DEFAULT
      RETURN
    END SELECT
    IF (.NOT.nc_ok(nf90_get_var(ncid,varid,work))) RETURN
    value=work(1); read_scalar=ieee_is_finite(value)
  END FUNCTION read_scalar

  LOGICAL FUNCTION read_grid_spacing_m(ncid,name,value)
    INTEGER, INTENT(IN) :: ncid
    CHARACTER(LEN=*), INTENT(IN) :: name
    REAL(real64), INTENT(OUT) :: value
    REAL(real32) :: raw(1)
    INTEGER :: varid

    read_grid_spacing_m=.FALSE.; value=0.0_real64
    IF (TRIM(name)/='Dx' .AND. TRIM(name)/='Dy') RETURN
    IF (.NOT.nc_ok(nf90_inq_varid(ncid,TRIM(name),varid))) RETURN
    IF (.NOT.variable_layout_is(ncid,varid,NF90_FLOAT, &
        [CHARACTER(LEN=3) :: 'nav']) .OR. &
        .NOT.variable_unit_is(ncid,varid,'kilometers','km')) RETURN
    IF (.NOT.nc_ok(nf90_get_var(ncid,varid,raw))) RETURN
    IF (.NOT.ieee_is_finite(raw(1))) RETURN
    IF (ABS(raw(1)-5.0_real32)<=1.0e-6_real32) THEN
      value=1000.0_real64*REAL(raw(1),real64)
    ELSE IF (ABS(raw(1)-5000.0_real32)<=1.0e-3_real32) THEN
      ! The pinned legacy KLAPS files label numerical metres as kilometres.
      value=REAL(raw(1),real64)
    ELSE
      RETURN
    END IF
    read_grid_spacing_m=.TRUE.
  END FUNCTION read_grid_spacing_m

  LOGICAL FUNCTION read_vector(ncid,name,value)
    INTEGER, INTENT(IN) :: ncid
    CHARACTER(LEN=*), INTENT(IN) :: name
    REAL(real64), INTENT(OUT) :: value(:)
    INTEGER :: varid
    read_vector=.FALSE.; value=0.0_real64
    IF (.NOT.nc_ok(nf90_inq_varid(ncid,TRIM(name),varid))) RETURN
    IF (TRIM(name)/='level') RETURN
    IF (.NOT.variable_layout_is(ncid,varid,NF90_FLOAT, &
        [CHARACTER(LEN=1) :: 'z']) .OR. &
        .NOT.variable_unit_is(ncid,varid,'hectopascals','hpa')) RETURN
    IF (.NOT.nc_ok(nf90_get_var(ncid,varid,value))) RETURN
    read_vector=ALL(ieee_is_finite(value))
  END FUNCTION read_vector

  LOGICAL FUNCTION variable_layout_is(ncid,varid,expected_type,dimension_names)
    INTEGER, INTENT(IN) :: ncid,varid,expected_type
    CHARACTER(LEN=*), INTENT(IN) :: dimension_names(:)
    CHARACTER(LEN=NF90_MAX_NAME) :: actual_name
    INTEGER :: actual_type,ndims,dimids(NF90_MAX_VAR_DIMS),k
    variable_layout_is=.FALSE.
    IF (.NOT.nc_ok(nf90_inquire_variable(ncid,varid,XTYPE=actual_type, &
        NDIMS=ndims,DIMIDS=dimids))) RETURN
    IF (actual_type/=expected_type .OR. ndims/=SIZE(dimension_names)) RETURN
    DO k=1,ndims
      actual_name=''
      IF (.NOT.nc_ok(nf90_inquire_dimension(ncid,dimids(k),NAME=actual_name))) RETURN
      IF (TRIM(actual_name)/=TRIM(dimension_names(k))) RETURN
    END DO
    variable_layout_is=.TRUE.
  END FUNCTION variable_layout_is

  LOGICAL FUNCTION variable_unit_is(ncid,varid,unit_a,unit_b)
    INTEGER, INTENT(IN) :: ncid,varid
    CHARACTER(LEN=*), INTENT(IN) :: unit_a,unit_b
    CHARACTER(LEN=128) :: actual
    variable_unit_is=.FALSE.; actual=''
    IF (.NOT.nc_ok(nf90_get_att(ncid,varid,'units',actual))) RETURN
    variable_unit_is=normalize_unit(actual)==normalize_unit(unit_a) .OR. &
                     normalize_unit(actual)==normalize_unit(unit_b)
  END FUNCTION variable_unit_is

  PURE CHARACTER(LEN=128) FUNCTION normalize_unit(value)
    CHARACTER(LEN=*), INTENT(IN) :: value
    INTEGER :: i,n,code
    normalize_unit=''; n=0
    DO i=1,LEN_TRIM(value)
      IF (value(i:i)==' ' .OR. value(i:i)=='_' .OR. value(i:i)=='{'.OR. &
          value(i:i)=='}') CYCLE
      n=n+1; code=IACHAR(value(i:i))
      IF (code>=IACHAR('A') .AND. code<=IACHAR('Z')) code=code+32
      normalize_unit(n:n)=ACHAR(code)
    END DO
  END FUNCTION normalize_unit

  PURE LOGICAL FUNCTION levels_are_native(levels)
    REAL(real64), INTENT(IN) :: levels(NZ)
    INTEGER :: k
    levels_are_native=.TRUE.
    DO k=1,NZ
      IF (ABS(levels(k)-50.0_real64*REAL(k,real64))>1.0e-5_real64) THEN
        levels_are_native=.FALSE.; RETURN
      END IF
    END DO
  END FUNCTION levels_are_native

  PURE LOGICAL FUNCTION vertical_domain_is_contiguous(domain)
    LOGICAL, INTENT(IN) :: domain(NX,NY,NZ)
    INTEGER :: i,j,k
    vertical_domain_is_contiguous=.FALSE.
    DO j=1,NY; DO i=1,NX
      IF (.NOT.ANY(domain(i,j,:))) RETURN
      DO k=1,NZ-1
        IF (domain(i,j,k) .AND. .NOT.domain(i,j,k+1)) RETURN
      END DO
    END DO; END DO
    vertical_domain_is_contiguous=.TRUE.
  END FUNCTION vertical_domain_is_contiguous

  LOGICAL FUNCTION terrain_mask_is_consistent(state,topography)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    REAL(real32), INTENT(IN) :: topography(NX,NY)
    INTEGER :: i,j,k,bottom
    REAL(real64) :: height,tolerance
    terrain_mask_is_consistent=.FALSE.
    DO j=1,NY; DO i=1,NX
      bottom=0
      DO k=1,NZ
        IF (state%above_ground(i,j,k)) THEN
          bottom=k
          EXIT
        END IF
      END DO
      IF (bottom==0) RETURN
      tolerance=128.0_real64*REAL(EPSILON(1.0_real32),real64)* &
        MAX(1.0_real64,ABS(REAL(topography(i,j),real64)))
      DO k=bottom,NZ
        IF (.NOT.cell_is_usable(state%geopotential%valid(i,j,k), &
              state%geopotential%quality(i,j,k), &
              state%geopotential%source(i,j,k))) RETURN
        height=REAL(state%geopotential%value(i,j,k),real64)/GRAVITY
        IF (.NOT.ieee_is_finite(height) .OR. height < -1000.0_real64 .OR. &
            height > 50000.0_real64 .OR. &
            height<REAL(topography(i,j),real64)-tolerance) RETURN
        IF (k>bottom) THEN
          IF (state%geopotential%value(i,j,k)<= &
              state%geopotential%value(i,j,k-1)) RETURN
        END IF
      END DO
    END DO; END DO
    terrain_mask_is_consistent=.TRUE.
  END FUNCTION terrain_mask_is_consistent

  PURE LOGICAL FUNCTION copied_diagnostic_boundary_contract_valid(state)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    copied_diagnostic_boundary_contract_valid=boundary_contract_valid(state)
    IF (.NOT.copied_diagnostic_boundary_contract_valid) RETURN
    copied_diagnostic_boundary_contract_valid= &
      ALL(IAND(state%omega_top_boundary%quality, &
               QUALITY_BOUNDARY_INTERIOR_COPY)/=0_int32) .AND. &
      ALL(IAND(state%omega_bottom_boundary%quality, &
               QUALITY_BOUNDARY_INTERIOR_COPY)/=0_int32) .AND. &
      ALL(IAND(state%omega_top_boundary%source,SOURCE_ANALYZED_WIND)/=0_int32) .AND. &
      ALL(IAND(state%omega_bottom_boundary%source,SOURCE_ANALYZED_WIND)/=0_int32) .AND. &
      .NOT.ANY(IAND(state%omega_top_boundary%source, &
                    SOURCE_BOUNDARY_CONDITION)/=0_int32) .AND. &
      .NOT.ANY(IAND(state%omega_bottom_boundary%source, &
                    SOURCE_BOUNDARY_CONDITION)/=0_int32)
  END FUNCTION copied_diagnostic_boundary_contract_valid

  PURE REAL(real64) FUNCTION dry_density(pressure,temperature,vapor)
    REAL(real64), INTENT(IN) :: pressure,temperature,vapor
    dry_density=0.0_real64
    IF (.NOT.ieee_is_finite(pressure) .OR. .NOT.ieee_is_finite(temperature) .OR. &
        .NOT.ieee_is_finite(vapor) .OR. pressure<=0.0_real64 .OR. &
        temperature<=0.0_real64 .OR. vapor<0.0_real64) RETURN
    dry_density=pressure/(RD_AIR*temperature*(1.0_real64+vapor/EPSILON_WATER))
  END FUNCTION dry_density

  LOGICAL FUNCTION put_global_metadata(ncid,result,config,valid_time)
    USE cloud_bal_pipeline, ONLY: cloud_bal_pipeline_result,cloud_bal_pipeline_config
    INTEGER, INTENT(IN) :: ncid
    TYPE(cloud_bal_pipeline_result), INTENT(IN) :: result
    TYPE(cloud_bal_pipeline_config), INTENT(IN) :: config
    INTEGER(int64), INTENT(IN) :: valid_time
    put_global_metadata=.FALSE.
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'contract', &
                                'real_radar_only_shadow_v3'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'diagnostic_schema_version', &
                                5_int32))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'schema_extensions', &
      'verified_operational_identity_v1,radar_no_echo_masks_v1,'// &
      'pressure_geometry_v2,omega_boundary_contract_v2'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'cloud_bal_schema_version', &
                                CLOUD_BAL_SCHEMA_VERSION))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'evidence_class', &
                                'REAL_RADAR_ONLY_SHADOW_PROPOSAL'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'configuration_id', &
                                'real-radar-only-shadow-v3'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'result_authority', &
                                'DIAGNOSTIC_PROPOSAL_ONLY'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'requested_mode', &
                                config%requested_mode))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'science_assessed',0_int32))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'promotion_eligible',0_int32))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'operational_state_verified', &
                                1_int32))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'operational_state_changed',0_int32))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'cloud_analysis_present',0_int32))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'radar_los_used',0_int32))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'above_ground_mask_provenance', &
      'PSFC_PRESSURE_CENTER_AND_STATIC_TERRAIN_HEIGHT'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'grid_spacing_adapter_policy', &
      'KM_TO_M_OR_PINNED_LEGACY_NUMERIC_METERS'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'pressure_interface_semantics', &
      'SURFACE_CLIPPED_CONTROL_VOLUME_BOUNDARY'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'physical_continuity_assessed', &
      0_int32))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'omega_boundary_provenance', &
      'COPIED_INTERIOR_DIAGNOSTIC_ONLY'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'balance_support_variable', &
                                'candidate_balance_support'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'minimum_usable_dbz', &
                                MINIMUM_USABLE_DBZ))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'radar_no_echo_dbz', &
                                RADAR_NO_ECHO_DBZ))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'radar_no_echo_transport_policy', &
                                'DESTINATION_HARD_BLOCK_SEPARATE_LEDGER'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'radar_valid_semantics', &
                                'ECHO_ONLY'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL, &
                                'configured_assumed_radar_wavelength_m', &
                                config%column%radar_wavelength_m))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'radar_wavelength_provenance', &
                                'CONFIGURED_ASSUMPTION_NOT_OBSERVATION'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'trajectory_horizontal_frame', &
                                'INPUT_WIND_NATIVE_UNRESOLVED'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'storm_motion_provenance', &
                                'NOT_AVAILABLE_ZERO_TRANSLATION_ASSUMPTION'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'maximum_usable_dbz', &
                                config%column%maximum_dbz))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'reference_mass_concentration', &
                                config%column%reference_mass_concentration))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'minimum_relative_fall_speed', &
                                config%column%minimum_relative_fall_speed))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'maximum_horizontal_substep', &
                                config%column%maximum_horizontal_substep))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'maximum_transport_substeps', &
                                config%column%maximum_transport_substeps))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'precipitation_loading_efficiency', &
                                config%column%precipitation_loading_efficiency))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'maximum_downdraft_ms', &
                                config%column%maximum_downdraft_ms))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'maximum_downdraft_innovation_ms', &
                                config%column%maximum_downdraft_innovation_ms))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'ledger_relative_tolerance', &
                                config%column%ledger_relative_tolerance))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'ledger_absolute_tolerance', &
                                config%column%ledger_absolute_tolerance))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'horizontal_support_radius_m', &
                                config%horizontal_support_radius_m))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'pressure_support_radius_pa', &
                                config%pressure_support_radius_pa))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'minimum_balance_beta', &
                                config%balance%minimum_beta))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'kappa_u', &
                                config%balance%kappa_u))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'kappa_v', &
                                config%balance%kappa_v))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'kappa_omega', &
                                config%balance%kappa_omega))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'maximum_wind_increment_ms', &
                                config%balance%maximum_wind_increment))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'maximum_omega_increment_pas', &
                                config%balance%maximum_omega_increment))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'increment_headroom', &
                                config%balance%increment_headroom))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'solver_residual_fraction', &
                                config%balance%solver_residual_fraction))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'required_residual_fraction', &
                                config%balance%required_residual_fraction))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'minimum_target_response_ratio', &
                    config%balance%minimum_target_response_ratio))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'maximum_target_response_ratio', &
                    config%balance%maximum_target_response_ratio))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'minimum_trust_region_fraction', &
                    config%balance%minimum_trust_region_fraction))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'physical_residual_tolerance', &
                                config%balance%physical_residual_tolerance))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'maximum_physical_residual', &
                                config%balance%maximum_physical_residual))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'maximum_solver_iterations', &
                                config%balance%maximum_iterations))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'geostrophic_relative_tolerance', &
                                config%balance%geostrophic_relative_tolerance))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'geostrophic_absolute_tolerance', &
                                config%balance%geostrophic_absolute_tolerance))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'valid_time_epoch',valid_time))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'pipeline_status',result%status))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'pipeline_reason',result%reason_code))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'column_status',result%column%status))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'balance_status',result%balance%status))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'solver_reason', &
                                result%balance%numerical%solver_reason))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'solver_iterations', &
                                result%balance%numerical%solver_iterations))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'acceptance_failures', &
                                result%balance%numerical%acceptance_failures))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'continuity_background_rms', &
                       result%balance%numerical%continuity_background_rms))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'continuity_background_max', &
                       result%balance%numerical%continuity_background_max))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'continuity_proposed_increment_rms', &
                       result%balance%numerical%continuity_proposed_increment_rms))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'continuity_proposed_increment_max', &
                       result%balance%numerical%continuity_proposed_increment_max))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'continuity_projected_increment_rms', &
                       result%balance%numerical%continuity_projected_increment_rms))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'continuity_projected_increment_max', &
                       result%balance%numerical%continuity_projected_increment_max))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'continuity_candidate_rms', &
                       result%balance%numerical%continuity_candidate_rms))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'continuity_candidate_max', &
                       result%balance%numerical%continuity_candidate_max))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'continuity_operator_identity_max', &
              result%balance%numerical%continuity_operator_identity_max))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'operator_identity_tolerance', &
                       config%balance%solver_absolute_tolerance))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'geostrophic_background_rms', &
                       result%balance%numerical%geostrophic_background_rms))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'geostrophic_candidate_rms', &
                       result%balance%numerical%geostrophic_candidate_rms))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'max_wind_increment_ms', &
                       result%balance%numerical%max_wind_increment))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'max_omega_increment_pas', &
                       result%balance%numerical%max_omega_increment))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'trust_region_fraction', &
                       result%balance%numerical%trust_region_fraction))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'unscaled_max_wind_increment_ms', &
                       result%balance%numerical%unscaled_max_wind_increment))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'unscaled_max_omega_increment_pas', &
                       result%balance%numerical%unscaled_max_omega_increment))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'target_response_failure_fraction', &
              result%balance%numerical%target_response_failure_fraction))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'flux_ledger_error', &
                       result%column%numerical%ledger_error))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'transport_required_substeps', &
                       result%column%numerical%transport_required_substeps))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'flux_input', &
                       result%column%numerical%flux_input))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'flux_deposited', &
                       result%column%numerical%flux_deposited))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'flux_suspended', &
                       result%column%numerical%flux_suspended))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'flux_boundary_exit', &
                       result%column%numerical%flux_boundary_exit))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'flux_terrain_intercept', &
                       result%column%numerical%flux_terrain_intercept))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'flux_observation_blocked', &
                       result%column%numerical%flux_observation_blocked))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'flux_no_echo_blocked', &
                       result%column%numerical%flux_no_echo_blocked))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'flux_microphysical_loss', &
                       result%column%numerical%flux_microphysical_loss))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'lower_boundary_note', &
      'copied lowest resolved omega; diagnostic only, not terrain kinematic omega'))) RETURN
    put_global_metadata=.TRUE.
  END FUNCTION put_global_metadata

  PURE LOGICAL FUNCTION nc_ok(code)
    INTEGER, INTENT(IN) :: code
    nc_ok=code==NF90_NOERR
  END FUNCTION nc_ok

END MODULE cloud_bal_real_netcdf
