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
  USE cloud_bal_balance_operator, ONLY: balance_beta_active
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

CONTAINS

  SUBROUTINE read_real_shadow_state(fua_path,fsf_path,lw3_path,vrz_path,vrt_path, &
                                    static_path,valid_time,state,longitude,status,reason)
    CHARACTER(LEN=*), INTENT(IN) :: fua_path,fsf_path,lw3_path,vrz_path,vrt_path
    CHARACTER(LEN=*), INTENT(IN) :: static_path
    INTEGER(int64), INTENT(IN) :: valid_time
    TYPE(cloud_bal_state_type), INTENT(OUT) :: state
    REAL(real32), ALLOCATABLE, INTENT(OUT) :: longitude(:,:)
    INTEGER, INTENT(OUT) :: status,reason
    REAL(real32), ALLOCATABLE :: raw(:,:,:),surface(:,:),tid(:,:,:)
    LOGICAL, ALLOCATABLE :: raw_valid(:,:,:),surface_valid(:,:)
    LOGICAL, ALLOCATABLE :: latitude_valid(:,:),longitude_valid(:,:)
    REAL(real64) :: levels(NZ),dx,dy
    INTEGER :: ncid,k,source_k,local_status

    status=STATUS_FAILED; reason=REASON_METADATA
    CALL initialize_cloud_bal_state(state,NX,NY,NZ,valid_time, &
                                    'NE57_LAPS_PRESSURE',local_status)
    IF (local_status/=STATUS_OK) RETURN
    ALLOCATE(raw(NX,NY,NZ),raw_valid(NX,NY,NZ),surface(NX,NY), &
             surface_valid(NX,NY),latitude_valid(NX,NY),longitude_valid(NX,NY), &
             tid(NX,NY,NZ),longitude(NX,NY))

    CALL open_case_file(lw3_path,NZ,valid_time,ncid,levels,dx,dy,local_status)
    IF (local_status/=STATUS_OK) RETURN
    CALL read_real3(ncid,'om','pascals/second','pa/s',raw,raw_valid,local_status)
    IF (local_status/=STATUS_OK) THEN; CALL close_file(ncid); RETURN; END IF
    DO k=1,NZ
      source_k=NZ+1-k
      state%above_ground(:,:,k)=raw_valid(:,:,source_k)
      state%pressure%value(:,:,k)=REAL(100.0_real64*levels(source_k),real32)
      CALL mark_real_field(state%pressure,k,state%above_ground(:,:,k), &
                           SOURCE_BACKGROUND_MODEL)
      state%omega%value(:,:,k)=MERGE(raw(:,:,source_k),0.0_real32, &
                                     state%above_ground(:,:,k))
      CALL mark_real_field(state%omega,k,state%above_ground(:,:,k), &
                           SOURCE_ANALYZED_WIND)
    END DO
    IF (.NOT.vertical_domain_is_contiguous(state%above_ground)) THEN
      CALL close_file(ncid); reason=REASON_REQUIRED_COVERAGE; RETURN
    END IF
    CALL read_real3(ncid,'u3','meters/second','m/s',raw,raw_valid,local_status)
    IF (local_status==STATUS_OK) CALL assign_reversed_core(raw,raw_valid,state%above_ground, &
      state%u,SOURCE_ANALYZED_WIND,1.0_real64,local_status)
    IF (local_status==STATUS_OK) CALL read_real3(ncid,'v3','meters/second','m/s', &
                                                 raw,raw_valid,local_status)
    IF (local_status==STATUS_OK) CALL assign_reversed_core(raw,raw_valid,state%above_ground, &
      state%v,SOURCE_ANALYZED_WIND,1.0_real64,local_status)
    CALL close_file(ncid)
    IF (local_status/=STATUS_OK) RETURN

    state%grid%dx=dx; state%grid%dy=dy
    state%grid%dp=5000.0_real64
    state%grid%pressure_mass_measure=dx*dy*state%grid%dp/GRAVITY

    CALL open_case_file(fua_path,NZ,valid_time,ncid,levels,dx,dy,local_status)
    IF (local_status/=STATUS_OK) RETURN
    CALL read_real3(ncid,'t3','kelvins','k',raw,raw_valid,local_status)
    IF (local_status==STATUS_OK) CALL assign_reversed_core(raw,raw_valid,state%above_ground, &
      state%temperature,SOURCE_BACKGROUND_MODEL,1.0_real64,local_status)
    IF (local_status==STATUS_OK) CALL read_real3(ncid,'sh','kg/kg','kgkg-1', &
                                                 raw,raw_valid,local_status)
    IF (local_status==STATUS_OK) CALL assign_specific_humidity(raw,raw_valid,state,local_status)
    IF (local_status==STATUS_OK) CALL read_real3(ncid,'ht','meters','m', &
                                                 raw,raw_valid,local_status)
    IF (local_status==STATUS_OK) CALL assign_reversed_core(raw,raw_valid,state%above_ground, &
      state%geopotential,SOURCE_BACKGROUND_MODEL,GRAVITY,local_status)
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
    CALL close_file(ncid)
    IF (local_status/=STATUS_OK) RETURN

    CALL open_case_file(vrz_path,NZ,valid_time,ncid,levels,dx,dy,local_status)
    IF (local_status==STATUS_OK) CALL read_real3(ncid,'ref','dbz','dbz', &
                                                 raw,raw_valid,local_status)
    CALL close_file(ncid)
    IF (local_status/=STATUS_OK) RETURN
    DO k=1,NZ
      source_k=NZ+1-k
      state%radar_reflectivity%value(:,:,k)=raw(:,:,source_k)
      state%radar_reflectivity%valid(:,:,k)=state%above_ground(:,:,k) .AND. &
        raw_valid(:,:,source_k) .AND. raw(:,:,source_k)>=MINIMUM_USABLE_DBZ .AND. &
        raw(:,:,source_k)<=100.0_real32
      WHERE(state%radar_reflectivity%valid(:,:,k))
        state%radar_reflectivity%quality(:,:,k)=0_int32
        state%radar_reflectivity%source(:,:,k)=SOURCE_RADAR_DBZ
      END WHERE
    END DO

    CALL open_case_file(vrt_path,NZ,valid_time,ncid,levels,dx,dy,local_status)
    IF (local_status==STATUS_OK) CALL read_real3(ncid,'tid','nul','1', &
                                                 tid,raw_valid,local_status)
    CALL close_file(ncid)
    IF (local_status/=STATUS_OK) RETURN
    DO k=1,NZ
      source_k=NZ+1-k
      WHERE(state%radar_reflectivity%valid(:,:,k) .AND. &
            raw_valid(:,:,source_k) .AND. NINT(tid(:,:,source_k))==2)
        state%radar_reflectivity%quality(:,:,k)= &
          IOR(state%radar_reflectivity%quality(:,:,k),QUALITY_BRIGHT_BAND_OR_MIXED)
      END WHERE
    END DO

    CALL open_surface_file(fsf_path,valid_time,ncid,dx,dy,local_status)
    IF (local_status==STATUS_OK) CALL read_real2(ncid,'tsf','kelvins','k', &
                                                 surface,surface_valid,local_status)
    IF (local_status==STATUS_OK) CALL assign_surface(surface,surface_valid, &
      state%surface_temperature,SOURCE_BACKGROUND_MODEL)
    IF (local_status==STATUS_OK) CALL read_real2(ncid,'psf','pascals','pa', &
                                                 surface,surface_valid,local_status)
    IF (local_status==STATUS_OK) CALL assign_surface(surface,surface_valid, &
      state%surface_pressure,SOURCE_BACKGROUND_MODEL)
    CALL close_file(ncid)
    IF (local_status/=STATUS_OK) RETURN

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
    CALL close_file(ncid)
    IF (local_status/=STATUS_OK .OR. .NOT.ALL(latitude_valid) .OR. &
        .NOT.ALL(longitude_valid)) RETURN

    CALL set_resolved_omega_boundaries(state,local_status)
    IF (local_status/=STATUS_OK) RETURN
    CALL refresh_dry_air_mass_measure(state,local_status)
    IF (local_status/=STATUS_OK) RETURN
    status=STATUS_OK; reason=REASON_NONE
  END SUBROUTINE read_real_shadow_state

  SUBROUTINE write_shadow_diagnostics(path,state_in,candidate,longitude,result,config, &
                                      residual_before,residual_after,status)
    USE cloud_bal_pipeline, ONLY: cloud_bal_pipeline_result,cloud_bal_pipeline_config
    CHARACTER(LEN=*), INTENT(IN) :: path
    TYPE(cloud_bal_state_type), INTENT(IN) :: state_in,candidate
    REAL(real32), INTENT(IN) :: longitude(:,:)
    TYPE(cloud_bal_pipeline_result), INTENT(IN) :: result
    TYPE(cloud_bal_pipeline_config), INTENT(IN) :: config
    REAL(real64), INTENT(IN) :: residual_before(:,:,:),residual_after(:,:,:)
    INTEGER, INTENT(OUT) :: status
    INTEGER :: ncid,xdim,ydim,zdim,level_var,lat_var,lon_var
    INTEGER :: varid(33),rc,k
    INTEGER(int32), ALLOCATABLE :: mask(:,:,:)
    REAL(real32) :: levels(NZ)
    CHARACTER(LEN=32), PARAMETER :: names(33)=[CHARACTER(LEN=32) :: &
      'radar_dbz','background_u','background_v','background_omega', &
      'candidate_u','candidate_v','candidate_omega','omega_target', &
      'background_cloud_water','background_cloud_ice','background_rain', &
      'background_snow','background_graupel','candidate_cloud_water', &
      'candidate_cloud_ice','candidate_rain','candidate_snow', &
      'candidate_graupel','balance_beta', &
      'continuity_background','continuity_candidate','above_ground', &
      'radar_valid','omega_target_valid','omega_target_quality', &
      'omega_target_source','omega_target_authority','candidate_balance_support', &
      'column_changed','balance_changed','overall_changed','obs_support','hydro_support']
    CHARACTER(LEN=32), PARAMETER :: units(33)=[CHARACTER(LEN=32) :: &
      'dBZ','m s-1','m s-1','Pa s-1','m s-1','m s-1','Pa s-1','Pa s-1', &
      'kg kg-1 dryair','kg kg-1 dryair','kg kg-1 dryair','kg kg-1 dryair', &
      'kg kg-1 dryair','kg kg-1 dryair','kg kg-1 dryair','kg kg-1 dryair', &
      'kg kg-1 dryair','kg kg-1 dryair','1','s-1','s-1', &
      '1','1','1','1','1','1','1','1','1','1','1','1']

    status=STATUS_FAILED
    IF (ANY(SHAPE(longitude)/=(/NX,NY/)) .OR. &
        ANY(SHAPE(residual_before)/=(/NX,NY,NZ/)) .OR. &
        ANY(SHAPE(residual_after)/=(/NX,NY,NZ/))) RETURN
    IF (ANY(.NOT.ieee_is_finite(state_in%latitude%value)) .OR. &
        ANY(state_in%latitude%value < -90.0_real32) .OR. &
        ANY(state_in%latitude%value > 90.0_real32) .OR. &
        ANY(.NOT.ieee_is_finite(longitude)) .OR. &
        ANY(longitude < -180.0_real32) .OR. ANY(longitude > 180.0_real32)) RETURN
    rc=nf90_create(TRIM(path),IOR(NF90_CLOBBER,NF90_NETCDF4),ncid)
    IF (rc/=NF90_NOERR) RETURN
    IF (.NOT.nc_ok(nf90_def_dim(ncid,'x',NX,xdim)) .OR. &
        .NOT.nc_ok(nf90_def_dim(ncid,'y',NY,ydim)) .OR. &
        .NOT.nc_ok(nf90_def_dim(ncid,'z',NZ,zdim))) GOTO 900
    IF (.NOT.nc_ok(nf90_def_var(ncid,'pressure',NF90_FLOAT,(/zdim/),level_var)) .OR. &
        .NOT.nc_ok(nf90_def_var(ncid,'latitude',NF90_FLOAT,(/xdim,ydim/),lat_var)) .OR. &
        .NOT.nc_ok(nf90_def_var(ncid,'longitude',NF90_FLOAT,(/xdim,ydim/),lon_var))) GOTO 900
    DO k=1,19
      IF (.NOT.nc_ok(nf90_def_var(ncid,TRIM(names(k)),NF90_FLOAT, &
                                  (/xdim,ydim,zdim/),varid(k)))) GOTO 900
    END DO
    DO k=20,21
      IF (.NOT.nc_ok(nf90_def_var(ncid,TRIM(names(k)),NF90_DOUBLE, &
                                  (/xdim,ydim,zdim/),varid(k)))) GOTO 900
    END DO
    DO k=22,33
      IF (.NOT.nc_ok(nf90_def_var(ncid,TRIM(names(k)),NF90_INT, &
                                  (/xdim,ydim,zdim/),varid(k)))) GOTO 900
    END DO
    DO k=1,33
      IF (.NOT.nc_ok(nf90_put_att(ncid,varid(k),'units',TRIM(units(k))))) GOTO 900
      IF (.NOT.nc_ok(nf90_def_var_deflate(ncid,varid(k),1,1,1))) GOTO 900
    END DO
    IF (.NOT.put_global_metadata(ncid,result,config,state_in%pressure%valid_time)) GOTO 900
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'grid_dx_m', &
                                state_in%grid%dx(1,1))) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'grid_dy_m', &
                                state_in%grid%dy(1,1))) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'grid_dp_pa', &
                                state_in%grid%dp(1,1,1)))) GOTO 900
    IF (.NOT.nc_ok(nf90_put_att(ncid,level_var,'units','Pa')) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,lat_var,'units','degree_north')) .OR. &
        .NOT.nc_ok(nf90_put_att(ncid,lon_var,'units','degree_east'))) GOTO 900
    IF (.NOT.nc_ok(nf90_enddef(ncid))) GOTO 900
    DO k=1,NZ
      levels(k)=state_in%pressure%value(1,1,k)
    END DO
    IF (.NOT.nc_ok(nf90_put_var(ncid,level_var,levels)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,lat_var,state_in%latitude%value)) .OR. &
        .NOT.nc_ok(nf90_put_var(ncid,lon_var,longitude))) GOTO 900
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
    ALLOCATE(mask(NX,NY,NZ))
    mask=MERGE(1_int32,0_int32,state_in%above_ground)
    IF (.NOT.nc_ok(nf90_put_var(ncid,varid(22),mask))) GOTO 900
    mask=MERGE(1_int32,0_int32,state_in%radar_reflectivity%valid)
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
    rc=nf90_close(ncid)
    IF (rc==NF90_NOERR) status=STATUS_OK
    RETURN
900 CONTINUE
    rc=nf90_close(ncid)
  END SUBROUTINE write_shadow_diagnostics

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
      WRITE(*,'(A)') 'adapter_error=dimensions:'//TRIM(path); RETURN
    END IF
    IF (.NOT.read_scalar(ncid,'valtime',file_time)) THEN
      WRITE(*,'(A)') 'adapter_error=valtime-read:'//TRIM(path); RETURN
    END IF
    IF (ABS(file_time-REAL(valid_time,real64))>0.5_real64) THEN
      WRITE(*,'(A)') 'adapter_error=valtime-mismatch:'//TRIM(path); RETURN
    END IF
    IF (expected_z==NZ) THEN
      IF (.NOT.read_vector(ncid,'level',levels)) THEN
        WRITE(*,'(A)') 'adapter_error=level-read:'//TRIM(path); RETURN
      END IF
      IF (.NOT.levels_are_native(levels)) THEN
        WRITE(*,'(A)') 'adapter_error=level-order:'//TRIM(path); RETURN
      END IF
    END IF
    IF (.NOT.read_scalar(ncid,'Dx',dx) .OR. .NOT.read_scalar(ncid,'Dy',dy)) THEN
      WRITE(*,'(A)') 'adapter_error=grid-spacing-read:'//TRIM(path); RETURN
    END IF
    IF (ABS(dx-5000.0_real64)>1.0e-6_real64 .OR. &
        ABS(dy-5000.0_real64)>1.0e-6_real64) THEN
      WRITE(*,'(A)') 'adapter_error=grid-spacing-value:'//TRIM(path); RETURN
    END IF
    status=STATUS_OK
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
    IF (.NOT.dimensions_are(ncid,1)) RETURN
    status=STATUS_OK
  END SUBROUTINE open_static_file

  SUBROUTINE close_file(ncid)
    INTEGER, INTENT(IN) :: ncid
    INTEGER :: ignored
    IF (ncid>=0) ignored=nf90_close(ncid)
  END SUBROUTINE close_file

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

  SUBROUTINE set_resolved_omega_boundaries(state,status)
    TYPE(cloud_bal_state_type), INTENT(INOUT) :: state
    INTEGER, INTENT(OUT) :: status
    INTEGER :: i,j,k
    status=STATUS_FAILED
    DO j=1,NY; DO i=1,NX
      IF (.NOT.state%omega%valid(i,j,NZ)) RETURN
      state%omega_top_boundary%value(i,j)=state%omega%value(i,j,NZ)
      state%omega_top_boundary%valid(i,j)=.TRUE.
      state%omega_top_boundary%quality(i,j)=QUALITY_LEGACY_PROVENANCE
      state%omega_top_boundary%source(i,j)=SOURCE_ANALYZED_WIND
      DO k=1,NZ
        IF (.NOT.state%above_ground(i,j,k)) CYCLE
        state%omega_bottom_boundary%value(i,j)=state%omega%value(i,j,k)
        state%omega_bottom_boundary%valid(i,j)=.TRUE.
        state%omega_bottom_boundary%quality(i,j)=QUALITY_LEGACY_PROVENANCE
        state%omega_bottom_boundary%source(i,j)=SOURCE_ANALYZED_WIND
        EXIT
      END DO
      IF (.NOT.state%omega_bottom_boundary%valid(i,j)) RETURN
    END DO; END DO
    status=STATUS_OK
  END SUBROUTINE set_resolved_omega_boundaries

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
    IF (.NOT.nc_ok(nf90_get_var(ncid,varid,work))) RETURN
    value=work(1); read_scalar=ieee_is_finite(value)
  END FUNCTION read_scalar

  LOGICAL FUNCTION read_vector(ncid,name,value)
    INTEGER, INTENT(IN) :: ncid
    CHARACTER(LEN=*), INTENT(IN) :: name
    REAL(real64), INTENT(OUT) :: value(:)
    INTEGER :: varid
    read_vector=.FALSE.; value=0.0_real64
    IF (.NOT.nc_ok(nf90_inq_varid(ncid,TRIM(name),varid))) RETURN
    IF (.NOT.nc_ok(nf90_get_var(ncid,varid,value))) RETURN
    read_vector=ALL(ieee_is_finite(value))
  END FUNCTION read_vector

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
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'evidence_class', &
                                'REAL_RADAR_ONLY_SHADOW_PROPOSAL'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'configuration_id', &
                                'real-radar-only-shadow-v3'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'result_authority', &
                                'DIAGNOSTIC_PROPOSAL_ONLY'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'science_assessed',0_int32))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'promotion_eligible',0_int32))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'operational_state_changed',0_int32))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'cloud_analysis_present',0_int32))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'radar_los_used',0_int32))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'minimum_usable_dbz', &
                                MINIMUM_USABLE_DBZ))) RETURN
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
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'flux_microphysical_loss', &
                       result%column%numerical%flux_microphysical_loss))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'lower_boundary_note', &
                       'lowest resolved analyzed omega; not terrain kinematic omega'))) RETURN
    put_global_metadata=.TRUE.
  END FUNCTION put_global_metadata

  PURE LOGICAL FUNCTION nc_ok(code)
    INTEGER, INTENT(IN) :: code
    nc_ok=code==NF90_NOERR
  END FUNCTION nc_ok

END MODULE cloud_bal_real_netcdf
