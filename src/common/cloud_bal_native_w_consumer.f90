! Private staged consumer for a physically supplied native-W increment.
!
! The caller copies a real.exe wrfinput_d01 into a private staging path before
! calling this module.  This module opens that copy in place and writes only W;
! it does not copy files, rename outputs, infer boundaries, or publish them.
MODULE cloud_bal_native_w_consumer
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  USE netcdf
  USE cloud_bal_native_velocity, ONLY: map_pressure_omega_to_native_w, &
    map_surface_w_increment,NATIVE_VELOCITY_OK
  IMPLICIT NONE
  PRIVATE

  INTEGER, PARAMETER, PUBLIC :: NATIVE_W_CONSUMER_OK=0
  INTEGER, PARAMETER, PUBLIC :: NATIVE_W_CONSUMER_OFF=1
  INTEGER, PARAMETER, PUBLIC :: NATIVE_W_CONSUMER_ARGUMENT=2
  INTEGER, PARAMETER, PUBLIC :: NATIVE_W_CONSUMER_WRFINPUT=3
  INTEGER, PARAMETER, PUBLIC :: NATIVE_W_CONSUMER_CANDIDATE=4
  INTEGER, PARAMETER, PUBLIC :: NATIVE_W_CONSUMER_COVERAGE=5
  INTEGER, PARAMETER, PUBLIC :: NATIVE_W_CONSUMER_PHYSICS=6
  INTEGER, PARAMETER, PUBLIC :: NATIVE_W_CONSUMER_WRITE=7
  INTEGER, PARAMETER, PUBLIC :: NATIVE_W_CONSUMER_ROLLBACK=8

  CHARACTER(LEN=32), PARAMETER :: W_DIMS(4)=[CHARACTER(LEN=32) :: &
    'west_east','south_north','bottom_top_stag','Time']
  CHARACTER(LEN=32), PARAMETER :: XY_DIMS(3)=[CHARACTER(LEN=32) :: &
    'west_east','south_north','Time']
  CHARACTER(LEN=32), PARAMETER :: TIME_DIMS(2)=[CHARACTER(LEN=32) :: &
    'DateStrLen','Time']
  CHARACTER(LEN=32), PARAMETER :: SURFACE_U_DIMS(3)=[CHARACTER(LEN=32) :: &
    'west_east_stag','south_north','Time']
  CHARACTER(LEN=32), PARAMETER :: SURFACE_V_DIMS(3)=[CHARACTER(LEN=32) :: &
    'west_east','south_north_stag','Time']
  CHARACTER(LEN=*), PARAMETER :: INCREMENT_CONTRACT='native_w_increment_v1'
  CHARACTER(LEN=*), PARAMETER :: SURFACE_INCREMENT_CONTRACT='native_w_increment_surface_v2'
  CHARACTER(LEN=*), PARAMETER :: SURFACE_BOUNDARY_CONTRACT= &
    'NATIVE_CF123_NONPERIODIC_FIXED_GEOMETRY_ZERO_ETA_DOT'
  CHARACTER(LEN=*), PARAMETER :: REQUIRED_WIND_FRAME='GRID_RELATIVE'
  INTEGER, PARAMETER :: DATE_LENGTH=19

  PUBLIC :: apply_native_w_increment

CONTAINS

  SUBROUTINE apply_native_w_increment(wrfin_path,candidate_path,expected_time, &
                                      enabled,status)
    CHARACTER(LEN=*), INTENT(IN) :: wrfin_path,candidate_path,expected_time
    LOGICAL, INTENT(IN) :: enabled
    INTEGER, INTENT(OUT) :: status
    INTEGER :: nx,ny,nz,local_status
    CHARACTER(LEN=DATE_LENGTH) :: source_time
    REAL(real32), ALLOCATABLE :: seed_w(:,:,:,:)
    REAL(real64), ALLOCATABLE :: source_lat(:,:,:),source_lon(:,:,:)
    REAL(real64), ALLOCATABLE :: pressure(:,:,:,:),pressure_x(:,:,:,:), &
      pressure_y(:,:,:,:),pressure_eta(:,:,:,:),z(:,:,:,:),z_x(:,:,:,:), &
      z_y(:,:,:,:),z_eta(:,:,:,:),delta_u(:,:,:,:),delta_v(:,:,:,:), &
      delta_omega(:,:,:,:),delta_u_surface(:,:,:),delta_v_surface(:,:,:), &
      height(:,:,:),mapfac_x(:,:,:),mapfac_y(:,:,:),delta_w(:,:,:), &
      surface_delta_w(:,:),zero(:,:,:),new_w64(:,:,:)
    REAL(real64) :: dx,dy
    REAL(real32), ALLOCATABLE :: new_w(:,:,:,:)
    INTEGER(int32), ALLOCATABLE :: update_mask(:,:,:,:)
    LOGICAL :: surface_v2

    status=NATIVE_W_CONSUMER_OFF
    IF (.NOT.enabled) RETURN
    status=NATIVE_W_CONSUMER_ARGUMENT
    IF (LEN_TRIM(wrfin_path)==0 .OR. LEN_TRIM(candidate_path)==0 .OR. &
        LEN_TRIM(expected_time)/=DATE_LENGTH) RETURN

    CALL read_wrfinput(TRIM(wrfin_path),nx,ny,nz,seed_w,source_lat,source_lon, &
                       source_time,local_status)
    IF (local_status/=NATIVE_W_CONSUMER_OK) THEN
      status=local_status
      RETURN
    END IF
    IF (source_time/=expected_time) THEN
      status=NATIVE_W_CONSUMER_WRFINPUT
      RETURN
    END IF

    CALL read_increment(TRIM(candidate_path),nx,ny,nz,source_time,source_lat, &
                        source_lon,pressure,pressure_x,pressure_y,pressure_eta, &
                        z,z_x,z_y,z_eta,delta_u,delta_v,delta_omega, &
                        update_mask,surface_v2,delta_u_surface,delta_v_surface, &
                        local_status)
    IF (local_status/=NATIVE_W_CONSUMER_OK) THEN
      status=local_status
      RETURN
    END IF
    CALL validate_increment(pressure,pressure_x,pressure_y,pressure_eta,z,z_x, &
                            z_y,z_eta,delta_u,delta_v,delta_omega,update_mask, &
                            local_status)
    IF (local_status/=NATIVE_W_CONSUMER_OK) THEN
      status=local_status
      RETURN
    END IF
    IF (surface_v2) THEN
      CALL read_wrf_surface_geometry(TRIM(wrfin_path),nx,ny,height,mapfac_x, &
                                     mapfac_y,dx,dy,local_status)
      IF (local_status/=NATIVE_W_CONSUMER_OK) THEN
        status=local_status
        RETURN
      END IF
      CALL validate_surface_increment(delta_u_surface,delta_v_surface, &
          update_mask,local_status)
      IF (local_status/=NATIVE_W_CONSUMER_OK) THEN
        status=local_status
        RETURN
      END IF
    END IF

    ALLOCATE(zero(nx,ny,nz),delta_w(nx,ny,nz),new_w64(nx,ny,nz), &
             new_w(nx,ny,nz,1))
    zero=0.0_real64
    delta_u(:,:,:,1)=MERGE(delta_u(:,:,:,1),0.0_real64,update_mask(:,:,:,1)==1)
    delta_v(:,:,:,1)=MERGE(delta_v(:,:,:,1),0.0_real64,update_mask(:,:,:,1)==1)
    delta_omega(:,:,:,1)=MERGE(delta_omega(:,:,:,1),0.0_real64, &
                                update_mask(:,:,:,1)==1)
    CALL map_pressure_omega_to_native_w(pressure(:,:,:,1),zero,pressure_x(:,:,:,1), &
      pressure_y(:,:,:,1),pressure_eta(:,:,:,1),z(:,:,:,1),zero,z_x(:,:,:,1), &
      z_y(:,:,:,1),z_eta(:,:,:,1),delta_u(:,:,:,1),delta_v(:,:,:,1), &
      delta_omega(:,:,:,1),delta_w,local_status)
    IF (local_status/=NATIVE_VELOCITY_OK) THEN
      status=NATIVE_W_CONSUMER_PHYSICS
      RETURN
    END IF
    IF (surface_v2) THEN
      ALLOCATE(surface_delta_w(nx,ny))
      CALL map_surface_w_increment(height(:,:,1),mapfac_x(:,:,1),mapfac_y(:,:,1), &
          dx,dy,delta_u_surface(:,:,1),delta_v_surface(:,:,1),surface_delta_w, &
          local_status)
      IF (local_status/=NATIVE_VELOCITY_OK) THEN
        status=NATIVE_W_CONSUMER_PHYSICS
        RETURN
      END IF
      ! The host boundary operator owns only the bottom W level.  Interior
      ! levels retain the existing pointwise pressure/omega mapping.
      delta_w(:,:,1)=surface_delta_w
    END IF

    new_w=seed_w
    new_w64=REAL(seed_w(:,:,:,1),real64)+delta_w
    WHERE (update_mask(:,:,:,1)==0) new_w64=REAL(seed_w(:,:,:,1),real64)
    IF (ANY(.NOT.ieee_is_finite(new_w64))) THEN
      status=NATIVE_W_CONSUMER_PHYSICS
      RETURN
    END IF
    new_w(:,:,:,1)=REAL(new_w64,real32)
    IF (ANY(.NOT.ieee_is_finite(new_w))) THEN
      status=NATIVE_W_CONSUMER_PHYSICS
      RETURN
    END IF

    CALL write_wrfinput_w(TRIM(wrfin_path),seed_w,new_w,local_status)
    status=local_status
  END SUBROUTINE apply_native_w_increment

  SUBROUTINE read_wrfinput(path,nx,ny,nz,seed_w,latitude,longitude,timestamp,status)
    CHARACTER(LEN=*), INTENT(IN) :: path
    INTEGER, INTENT(OUT) :: nx,ny,nz,status
    REAL(real32), ALLOCATABLE, INTENT(OUT) :: seed_w(:,:,:,:)
    REAL(real64), ALLOCATABLE, INTENT(OUT) :: latitude(:,:,:),longitude(:,:,:)
    CHARACTER(LEN=DATE_LENGTH), INTENT(OUT) :: timestamp
    INTEGER :: ncid,local_status

    nx=0; ny=0; nz=0; timestamp=''; status=NATIVE_W_CONSUMER_WRFINPUT
    local_status=nf90_open(path,NF90_NOWRITE,ncid)
    IF (local_status/=NF90_NOERR) RETURN
    IF (.NOT.read_dimension(ncid,'west_east',nx)) GOTO 900
    IF (.NOT.read_dimension(ncid,'south_north',ny)) GOTO 900
    IF (.NOT.read_dimension(ncid,'bottom_top_stag',nz)) GOTO 900
    IF (.NOT.read_dimension(ncid,'Time',local_status)) GOTO 900
    IF (local_status/=1) GOTO 900
    IF (.NOT.read_dimension(ncid,'DateStrLen',local_status)) GOTO 900
    IF (local_status/=DATE_LENGTH) THEN
      CALL close_dataset(ncid)
      RETURN
    END IF
    ALLOCATE(seed_w(nx,ny,nz,1),latitude(nx,ny,1),longitude(nx,ny,1))
    IF (.NOT.read_w(ncid,seed_w)) GOTO 900
    IF (.NOT.read_real3(ncid,'XLAT',XY_DIMS,latitude,'degree_north')) GOTO 900
    IF (.NOT.read_real3(ncid,'XLONG',XY_DIMS,longitude,'degree_east')) GOTO 900
    IF (.NOT.read_times(ncid,timestamp)) GOTO 900
    IF (ANY(.NOT.ieee_is_finite(REAL(seed_w,real64))) .OR. &
        ANY(.NOT.ieee_is_finite(latitude)) .OR. ANY(.NOT.ieee_is_finite(longitude))) GOTO 900
    CALL close_dataset(ncid)
    status=NATIVE_W_CONSUMER_OK
    RETURN
900 CONTINUE
    CALL close_dataset(ncid)
  END SUBROUTINE read_wrfinput

  SUBROUTINE read_increment(path,nx,ny,nz,expected_time,source_lat,source_lon, &
      pressure,pressure_x,pressure_y,pressure_eta,z,z_x,z_y,z_eta,delta_u, &
      delta_v,delta_omega,update_mask,surface_v2,delta_u_surface, &
      delta_v_surface,status)
    CHARACTER(LEN=*), INTENT(IN) :: path,expected_time
    INTEGER, INTENT(IN) :: nx,ny,nz
    INTEGER, INTENT(OUT) :: status
    REAL(real64), INTENT(IN) :: source_lat(:,:,:),source_lon(:,:,:)
    REAL(real64), ALLOCATABLE, INTENT(OUT) :: pressure(:,:,:,:),pressure_x(:,:,:,:), &
      pressure_y(:,:,:,:),pressure_eta(:,:,:,:),z(:,:,:,:),z_x(:,:,:,:), &
      z_y(:,:,:,:),z_eta(:,:,:,:),delta_u(:,:,:,:),delta_v(:,:,:,:), &
      delta_omega(:,:,:,:)
    INTEGER(int32), ALLOCATABLE, INTENT(OUT) :: update_mask(:,:,:,:)
    LOGICAL, INTENT(OUT) :: surface_v2
    REAL(real64), ALLOCATABLE, INTENT(OUT) :: delta_u_surface(:,:,:), &
      delta_v_surface(:,:,:)
    INTEGER :: ncid,local_status
    REAL(real64), ALLOCATABLE :: candidate_lat(:,:,:),candidate_lon(:,:,:)
    CHARACTER(LEN=DATE_LENGTH) :: candidate_time

    status=NATIVE_W_CONSUMER_CANDIDATE
    surface_v2=.FALSE.
    IF (SIZE(source_lat,1)/=nx .OR. SIZE(source_lat,2)/=ny .OR. &
        SIZE(source_lat,3)/=1 .OR. SIZE(source_lon,1)/=nx .OR. &
        SIZE(source_lon,2)/=ny .OR. SIZE(source_lon,3)/=1) RETURN
    IF (nf90_open(path,NF90_NOWRITE,ncid)/=NF90_NOERR) RETURN
    IF (.NOT.read_dimension(ncid,'west_east',local_status)) GOTO 900
    IF (local_status/=nx) GOTO 900
    IF (.NOT.read_dimension(ncid,'south_north',local_status)) GOTO 900
    IF (local_status/=ny) GOTO 900
    IF (.NOT.read_dimension(ncid,'bottom_top_stag',local_status)) GOTO 900
    IF (local_status/=nz) GOTO 900
    IF (.NOT.read_dimension(ncid,'Time',local_status)) GOTO 900
    IF (local_status/=1) GOTO 900
    IF (.NOT.read_dimension(ncid,'DateStrLen',local_status)) GOTO 900
    IF (local_status/=DATE_LENGTH) GOTO 900
    IF (read_text_attribute(ncid,'contract',INCREMENT_CONTRACT)) THEN
      surface_v2=.FALSE.
    ELSE
      IF (.NOT.read_text_attribute(ncid,'contract',SURFACE_INCREMENT_CONTRACT)) GOTO 900
      surface_v2=.TRUE.
      IF (.NOT.read_text_attribute(ncid,'surface_boundary_contract', &
                                   SURFACE_BOUNDARY_CONTRACT)) GOTO 900
    END IF
    IF (.NOT.read_text_attribute(ncid,'wind_coordinate',REQUIRED_WIND_FRAME)) GOTO 900
    IF (.NOT.read_times(ncid,candidate_time)) GOTO 900
    IF (candidate_time/=expected_time) GOTO 900
    ALLOCATE(candidate_lat(nx,ny,1),candidate_lon(nx,ny,1))
    IF (.NOT.read_real3(ncid,'XLAT',XY_DIMS,candidate_lat,'degree_north')) GOTO 900
    IF (.NOT.read_real3(ncid,'XLONG',XY_DIMS,candidate_lon,'degree_east')) GOTO 900
    IF (ANY(candidate_lat/=source_lat) .OR. ANY(candidate_lon/=source_lon)) GOTO 900
    ALLOCATE(pressure(nx,ny,nz,1),pressure_x(nx,ny,nz,1), &
             pressure_y(nx,ny,nz,1),pressure_eta(nx,ny,nz,1),z(nx,ny,nz,1), &
             z_x(nx,ny,nz,1),z_y(nx,ny,nz,1),z_eta(nx,ny,nz,1), &
             delta_u(nx,ny,nz,1),delta_v(nx,ny,nz,1),delta_omega(nx,ny,nz,1), &
             update_mask(nx,ny,nz,1))
    IF (.NOT.read_real4(ncid,'P',W_DIMS,pressure,'Pa')) GOTO 900
    IF (.NOT.read_real4(ncid,'P_X',W_DIMS,pressure_x,'Pa m-1')) GOTO 900
    IF (.NOT.read_real4(ncid,'P_Y',W_DIMS,pressure_y,'Pa m-1')) GOTO 900
    IF (.NOT.read_real4(ncid,'P_ETA',W_DIMS,pressure_eta,'Pa')) GOTO 900
    IF (.NOT.read_real4(ncid,'Z',W_DIMS,z,'m')) GOTO 900
    IF (.NOT.read_real4(ncid,'Z_X',W_DIMS,z_x,'1')) GOTO 900
    IF (.NOT.read_real4(ncid,'Z_Y',W_DIMS,z_y,'1')) GOTO 900
    IF (.NOT.read_real4(ncid,'Z_ETA',W_DIMS,z_eta,'m')) GOTO 900
    IF (.NOT.read_real4(ncid,'DELTA_U',W_DIMS,delta_u,'m s-1')) GOTO 900
    IF (.NOT.read_real4(ncid,'DELTA_V',W_DIMS,delta_v,'m s-1')) GOTO 900
    IF (.NOT.read_real4(ncid,'DELTA_OMEGA',W_DIMS,delta_omega,'Pa s-1')) GOTO 900
    IF (.NOT.read_int4(ncid,'UPDATE_MASK',W_DIMS,update_mask)) GOTO 900
    IF (surface_v2) THEN
      ALLOCATE(delta_u_surface(nx+1,ny,1),delta_v_surface(nx,ny+1,1))
      IF (.NOT.read_float3(ncid,'DELTA_U_SURFACE',SURFACE_U_DIMS, &
                          delta_u_surface,'m s-1')) GOTO 900
      IF (.NOT.read_float3(ncid,'DELTA_V_SURFACE',SURFACE_V_DIMS, &
                          delta_v_surface,'m s-1')) GOTO 900
    END IF
    CALL close_dataset(ncid)
    status=NATIVE_W_CONSUMER_OK
    RETURN
900 CONTINUE
    CALL close_dataset(ncid)
  END SUBROUTINE read_increment

  SUBROUTINE read_wrf_surface_geometry(path,nx,ny,height,mapfac_x,mapfac_y, &
                                       dx,dy,status)
    CHARACTER(LEN=*), INTENT(IN) :: path
    INTEGER, INTENT(IN) :: nx,ny
    REAL(real64), ALLOCATABLE, INTENT(OUT) :: height(:,:,:),mapfac_x(:,:,:), &
      mapfac_y(:,:,:)
    REAL(real64), INTENT(OUT) :: dx,dy
    INTEGER, INTENT(OUT) :: status
    INTEGER :: ncid

    status=NATIVE_W_CONSUMER_WRFINPUT
    dx=0.0_real64; dy=0.0_real64
    IF (nf90_open(path,NF90_NOWRITE,ncid)/=NF90_NOERR) RETURN
    ALLOCATE(height(nx,ny,1),mapfac_x(nx,ny,1),mapfac_y(nx,ny,1))
    IF (.NOT.read_real3(ncid,'HGT',XY_DIMS,height,'m')) GOTO 900
    IF (.NOT.read_map_factor(ncid,'MAPFAC_MX',mapfac_x)) GOTO 900
    IF (.NOT.read_map_factor(ncid,'MAPFAC_MY',mapfac_y)) GOTO 900
    IF (nf90_get_att(ncid,NF90_GLOBAL,'DX',dx)/=NF90_NOERR) GOTO 900
    IF (nf90_get_att(ncid,NF90_GLOBAL,'DY',dy)/=NF90_NOERR) GOTO 900
    CALL close_dataset(ncid)
    status=NATIVE_W_CONSUMER_OK
    RETURN
900 CONTINUE
    CALL close_dataset(ncid)
  END SUBROUTINE read_wrf_surface_geometry

  LOGICAL FUNCTION read_map_factor(ncid,name,values)
    INTEGER, INTENT(IN) :: ncid
    CHARACTER(LEN=*), INTENT(IN) :: name
    REAL(real64), INTENT(OUT) :: values(:,:,:)
    INTEGER :: varid,rc
    CHARACTER(LEN=128) :: units

    read_map_factor=.FALSE.; values=0.0_real64; units=''
    IF (.NOT.real_variable_layout_is(ncid,name,XY_DIMS)) RETURN
    IF (nf90_inq_varid(ncid,TRIM(name),varid)/=NF90_NOERR) RETURN
    rc=nf90_get_var(ncid,varid,values)
    IF (rc/=NF90_NOERR) RETURN
    ! WRF's native MAPFAC fields carry an empty units attribute.  Accept the
    ! dimension/type contract and validate positivity below instead of
    ! inventing a units string for this dimensionless state.
    rc=nf90_get_att(ncid,varid,'units',units)
    IF (rc/=NF90_NOERR) RETURN
    ! Native WRF encodes its empty units string as one NUL character.
    read_map_factor=TRIM(units)=='' .OR. TRIM(units)==ACHAR(0) .OR. TRIM(units)=='1'
  END FUNCTION read_map_factor

  SUBROUTINE validate_surface_increment(delta_u_surface,delta_v_surface, &
      update_mask,status)
    REAL(real64), INTENT(IN) :: delta_u_surface(:,:,:),delta_v_surface(:,:,:)
    INTEGER(int32), INTENT(IN) :: update_mask(:,:,:,:)
    INTEGER, INTENT(OUT) :: status
    INTEGER :: nx,ny,nz

    status=NATIVE_W_CONSUMER_COVERAGE
    nx=SIZE(update_mask,1); ny=SIZE(update_mask,2); nz=SIZE(update_mask,3)
    IF (SIZE(update_mask,4)/=1 .OR. &
        SIZE(delta_u_surface,1)/=nx+1 .OR. SIZE(delta_u_surface,2)/=ny .OR. &
        SIZE(delta_u_surface,3)/=1 .OR. SIZE(delta_v_surface,1)/=nx .OR. &
        SIZE(delta_v_surface,2)/=ny+1 .OR. SIZE(delta_v_surface,3)/=1) RETURN
    IF (ANY(update_mask(:,:,1,1)/=1_int32) .OR. &
        ANY(update_mask(:,:,nz,1)/=0_int32)) RETURN
    IF (ANY(.NOT.ieee_is_finite(delta_u_surface)) .OR. &
        ANY(.NOT.ieee_is_finite(delta_v_surface))) RETURN
    status=NATIVE_W_CONSUMER_OK
  END SUBROUTINE validate_surface_increment

  SUBROUTINE validate_increment(pressure,pressure_x,pressure_y,pressure_eta,z, &
      z_x,z_y,z_eta,delta_u,delta_v,delta_omega,update_mask,status)
    REAL(real64), INTENT(IN) :: pressure(:,:,:,:),pressure_x(:,:,:,:), &
      pressure_y(:,:,:,:),pressure_eta(:,:,:,:),z(:,:,:,:),z_x(:,:,:,:), &
      z_y(:,:,:,:),z_eta(:,:,:,:),delta_u(:,:,:,:),delta_v(:,:,:,:), &
      delta_omega(:,:,:,:)
    INTEGER(int32), INTENT(IN) :: update_mask(:,:,:,:)
    INTEGER, INTENT(OUT) :: status
    INTEGER :: i,j,k
    LOGICAL :: active

    status=NATIVE_W_CONSUMER_COVERAGE
    IF (ANY((update_mask/=0_int32) .AND. (update_mask/=1_int32))) RETURN
    IF (ANY(.NOT.ieee_is_finite(pressure)) .OR. ANY(.NOT.ieee_is_finite(pressure_x)) .OR. &
        ANY(.NOT.ieee_is_finite(pressure_y)) .OR. ANY(.NOT.ieee_is_finite(pressure_eta)) .OR. &
        ANY(.NOT.ieee_is_finite(z)) .OR. ANY(.NOT.ieee_is_finite(z_x)) .OR. &
        ANY(.NOT.ieee_is_finite(z_y)) .OR. ANY(.NOT.ieee_is_finite(z_eta)) .OR. &
        ANY(pressure<=0.0_real64)) RETURN
    DO k=1,SIZE(update_mask,3)
      DO j=1,SIZE(update_mask,2)
        DO i=1,SIZE(update_mask,1)
          active=update_mask(i,j,k,1)==1
          IF (active) THEN
            IF (.NOT.ieee_is_finite(delta_u(i,j,k,1)) .OR. &
                .NOT.ieee_is_finite(delta_v(i,j,k,1)) .OR. &
                .NOT.ieee_is_finite(delta_omega(i,j,k,1))) RETURN
          END IF
        END DO
      END DO
    END DO
    status=NATIVE_W_CONSUMER_OK
  END SUBROUTINE validate_increment

  SUBROUTINE write_wrfinput_w(path,seed_w,new_w,status)
    CHARACTER(LEN=*), INTENT(IN) :: path
    REAL(real32), INTENT(IN) :: seed_w(:,:,:,:),new_w(:,:,:,:)
    INTEGER, INTENT(OUT) :: status
    INTEGER :: ncid,varid,rc
    REAL(real32), ALLOCATABLE :: current_w(:,:,:,:)

    status=NATIVE_W_CONSUMER_WRITE
    IF (ANY(SHAPE(seed_w)/=SHAPE(new_w))) RETURN
    IF (nf90_open(path,NF90_WRITE,ncid)/=NF90_NOERR) RETURN
    IF (.NOT.variable_layout_is(ncid,'W',W_DIMS,NF90_FLOAT) .OR. &
        nf90_inq_varid(ncid,'W',varid)/=NF90_NOERR) THEN
      CALL close_dataset(ncid)
      RETURN
    END IF
    ALLOCATE(current_w(SIZE(seed_w,1),SIZE(seed_w,2),SIZE(seed_w,3),SIZE(seed_w,4)))
    rc=nf90_get_var(ncid,varid,current_w)
    IF (rc/=NF90_NOERR) THEN
      CALL close_dataset(ncid)
      RETURN
    END IF
    IF (ANY(current_w/=seed_w)) THEN
      CALL close_dataset(ncid)
      status=NATIVE_W_CONSUMER_ROLLBACK
      RETURN
    END IF
    rc=nf90_put_var(ncid,varid,new_w)
    IF (rc/=NF90_NOERR) THEN
      rc=nf90_put_var(ncid,varid,seed_w)
      CALL close_dataset(ncid)
      IF (rc/=NF90_NOERR) THEN
        status=NATIVE_W_CONSUMER_ROLLBACK
      END IF
      RETURN
    END IF
    rc=nf90_close(ncid)
    IF (rc/=NF90_NOERR) THEN
      IF (.NOT.restore_seed_w(path,seed_w)) status=NATIVE_W_CONSUMER_ROLLBACK
      RETURN
    END IF
    IF (.NOT.verify_written_w(path,new_w)) THEN
      IF (.NOT.restore_seed_w(path,seed_w)) THEN
        status=NATIVE_W_CONSUMER_ROLLBACK
      ELSE
        status=NATIVE_W_CONSUMER_WRITE
      END IF
      RETURN
    END IF
    status=NATIVE_W_CONSUMER_OK
  END SUBROUTINE write_wrfinput_w

  LOGICAL FUNCTION restore_seed_w(path,seed_w)
    CHARACTER(LEN=*), INTENT(IN) :: path
    REAL(real32), INTENT(IN) :: seed_w(:,:,:,:)
    INTEGER :: ncid,varid,rc

    restore_seed_w=.FALSE.
    IF (nf90_open(path,NF90_WRITE,ncid)/=NF90_NOERR) RETURN
    IF (.NOT.variable_layout_is(ncid,'W',W_DIMS,NF90_FLOAT) .OR. &
        nf90_inq_varid(ncid,'W',varid)/=NF90_NOERR) THEN
      CALL close_dataset(ncid)
      RETURN
    END IF
    rc=nf90_put_var(ncid,varid,seed_w)
    IF (nf90_close(ncid)/=NF90_NOERR) RETURN
    restore_seed_w=rc==NF90_NOERR
  END FUNCTION restore_seed_w

  LOGICAL FUNCTION verify_written_w(path,expected_w)
    CHARACTER(LEN=*), INTENT(IN) :: path
    REAL(real32), INTENT(IN) :: expected_w(:,:,:,:)
    INTEGER :: ncid,varid,rc
    REAL(real32), ALLOCATABLE :: actual_w(:,:,:,:)

    verify_written_w=.FALSE.
    IF (nf90_open(path,NF90_NOWRITE,ncid)/=NF90_NOERR) RETURN
    IF (.NOT.variable_layout_is(ncid,'W',W_DIMS,NF90_FLOAT) .OR. &
        nf90_inq_varid(ncid,'W',varid)/=NF90_NOERR) THEN
      CALL close_dataset(ncid)
      RETURN
    END IF
    ALLOCATE(actual_w(SIZE(expected_w,1),SIZE(expected_w,2), &
      SIZE(expected_w,3),SIZE(expected_w,4)))
    rc=nf90_get_var(ncid,varid,actual_w)
    CALL close_dataset(ncid)
    IF (rc/=NF90_NOERR) RETURN
    verify_written_w=ALL(actual_w==expected_w)
  END FUNCTION verify_written_w

  LOGICAL FUNCTION read_dimension(ncid,name,length)
    INTEGER, INTENT(IN) :: ncid
    CHARACTER(LEN=*), INTENT(IN) :: name
    INTEGER, INTENT(OUT) :: length
    INTEGER :: dimid,rc

    length=0
    rc=nf90_inq_dimid(ncid,TRIM(name),dimid)
    IF (rc/=NF90_NOERR) THEN
      read_dimension=.FALSE.
      RETURN
    END IF
    rc=nf90_inquire_dimension(ncid,dimid,LEN=length)
    read_dimension=rc==NF90_NOERR
  END FUNCTION read_dimension

  LOGICAL FUNCTION variable_layout_is(ncid,name,dimension_names,expected_type)
    INTEGER, INTENT(IN) :: ncid,expected_type
    CHARACTER(LEN=*), INTENT(IN) :: name
    CHARACTER(LEN=*), INTENT(IN) :: dimension_names(:)
    INTEGER :: varid,actual_type,ndims,dimids(NF90_MAX_VAR_DIMS),k,rc
    CHARACTER(LEN=NF90_MAX_NAME) :: actual_name

    variable_layout_is=.FALSE.
    IF (nf90_inq_varid(ncid,TRIM(name),varid)/=NF90_NOERR) RETURN
    rc=nf90_inquire_variable(ncid,varid,XTYPE=actual_type,NDIMS=ndims,DIMIDS=dimids)
    IF (rc/=NF90_NOERR .OR. actual_type/=expected_type .OR. &
        ndims/=SIZE(dimension_names)) RETURN
    DO k=1,ndims
      actual_name=''
      IF (nf90_inquire_dimension(ncid,dimids(k),NAME=actual_name)/=NF90_NOERR) RETURN
      IF (TRIM(actual_name)/=TRIM(dimension_names(k))) RETURN
    END DO
    variable_layout_is=.TRUE.
  END FUNCTION variable_layout_is

  LOGICAL FUNCTION real_variable_layout_is(ncid,name,dimension_names)
    INTEGER, INTENT(IN) :: ncid
    CHARACTER(LEN=*), INTENT(IN) :: name
    CHARACTER(LEN=*), INTENT(IN) :: dimension_names(:)
    INTEGER :: varid,actual_type

    real_variable_layout_is=.FALSE.
    IF (nf90_inq_varid(ncid,TRIM(name),varid)/=NF90_NOERR) RETURN
    IF (nf90_inquire_variable(ncid,varid,XTYPE=actual_type)/=NF90_NOERR) RETURN
    IF (actual_type/=NF90_FLOAT .AND. actual_type/=NF90_DOUBLE) RETURN
    real_variable_layout_is=variable_layout_is(ncid,name,dimension_names,actual_type)
  END FUNCTION real_variable_layout_is

  LOGICAL FUNCTION has_units(ncid,name,expected)
    INTEGER, INTENT(IN) :: ncid
    CHARACTER(LEN=*), INTENT(IN) :: name,expected
    INTEGER :: varid,rc
    CHARACTER(LEN=128) :: actual

    has_units=.FALSE.; actual=''
    IF (nf90_inq_varid(ncid,TRIM(name),varid)/=NF90_NOERR) RETURN
    rc=nf90_get_att(ncid,varid,'units',actual)
    IF (rc/=NF90_NOERR) RETURN
    has_units=TRIM(actual)==TRIM(expected)
  END FUNCTION has_units

  LOGICAL FUNCTION read_w(ncid,values)
    INTEGER, INTENT(IN) :: ncid
    REAL(real32), INTENT(OUT) :: values(:,:,:,:)
    INTEGER :: varid,rc

    read_w=.FALSE.; values=0.0_real32
    IF (.NOT.variable_layout_is(ncid,'W',W_DIMS,NF90_FLOAT)) RETURN
    IF (.NOT.has_units(ncid,'W','m s-1')) RETURN
    IF (nf90_inq_varid(ncid,'W',varid)/=NF90_NOERR) RETURN
    rc=nf90_get_var(ncid,varid,values)
    read_w=rc==NF90_NOERR
  END FUNCTION read_w

  LOGICAL FUNCTION read_real4(ncid,name,dimension_names,values,units)
    INTEGER, INTENT(IN) :: ncid
    CHARACTER(LEN=*), INTENT(IN) :: name,units
    CHARACTER(LEN=*), INTENT(IN) :: dimension_names(:)
    REAL(real64), INTENT(OUT) :: values(:,:,:,:)
    INTEGER :: varid,rc

    read_real4=.FALSE.; values=0.0_real64
    IF (.NOT.real_variable_layout_is(ncid,name,dimension_names)) RETURN
    IF (.NOT.has_units(ncid,name,units)) RETURN
    IF (nf90_inq_varid(ncid,TRIM(name),varid)/=NF90_NOERR) RETURN
    rc=nf90_get_var(ncid,varid,values)
    read_real4=rc==NF90_NOERR
  END FUNCTION read_real4

  LOGICAL FUNCTION read_real3(ncid,name,dimension_names,values,units)
    INTEGER, INTENT(IN) :: ncid
    CHARACTER(LEN=*), INTENT(IN) :: name,units
    CHARACTER(LEN=*), INTENT(IN) :: dimension_names(:)
    REAL(real64), INTENT(OUT) :: values(:,:,:)
    INTEGER :: varid,rc

    read_real3=.FALSE.; values=0.0_real64
    IF (.NOT.real_variable_layout_is(ncid,name,dimension_names)) RETURN
    IF (.NOT.has_units(ncid,name,units)) RETURN
    IF (nf90_inq_varid(ncid,TRIM(name),varid)/=NF90_NOERR) RETURN
    rc=nf90_get_var(ncid,varid,values)
    read_real3=rc==NF90_NOERR
  END FUNCTION read_real3

  LOGICAL FUNCTION read_float3(ncid,name,dimension_names,values,units)
    INTEGER, INTENT(IN) :: ncid
    CHARACTER(LEN=*), INTENT(IN) :: name,units
    CHARACTER(LEN=*), INTENT(IN) :: dimension_names(:)
    REAL(real64), INTENT(OUT) :: values(:,:,:)
    INTEGER :: varid,rc

    read_float3=.FALSE.; values=0.0_real64
    IF (.NOT.variable_layout_is(ncid,name,dimension_names,NF90_FLOAT)) RETURN
    IF (.NOT.has_units(ncid,name,units)) RETURN
    IF (nf90_inq_varid(ncid,TRIM(name),varid)/=NF90_NOERR) RETURN
    rc=nf90_get_var(ncid,varid,values)
    read_float3=rc==NF90_NOERR
  END FUNCTION read_float3

  LOGICAL FUNCTION read_int4(ncid,name,dimension_names,values)
    INTEGER, INTENT(IN) :: ncid
    CHARACTER(LEN=*), INTENT(IN) :: name
    CHARACTER(LEN=*), INTENT(IN) :: dimension_names(:)
    INTEGER(int32), INTENT(OUT) :: values(:,:,:,:)
    INTEGER :: varid,rc

    read_int4=.FALSE.; values=0_int32
    IF (.NOT.variable_layout_is(ncid,name,dimension_names,NF90_INT)) RETURN
    IF (.NOT.has_units(ncid,name,'1')) RETURN
    IF (nf90_inq_varid(ncid,TRIM(name),varid)/=NF90_NOERR) RETURN
    rc=nf90_get_var(ncid,varid,values)
    read_int4=rc==NF90_NOERR
  END FUNCTION read_int4

  LOGICAL FUNCTION read_times(ncid,timestamp)
    INTEGER, INTENT(IN) :: ncid
    CHARACTER(LEN=DATE_LENGTH), INTENT(OUT) :: timestamp
    CHARACTER(LEN=DATE_LENGTH) :: value(1)
    INTEGER :: varid,rc

    timestamp=''; value=''; read_times=.FALSE.
    IF (.NOT.variable_layout_is(ncid,'Times',TIME_DIMS,NF90_CHAR)) RETURN
    IF (nf90_inq_varid(ncid,'Times',varid)/=NF90_NOERR) RETURN
    rc=nf90_get_var(ncid,varid,value)
    IF (rc/=NF90_NOERR) RETURN
    timestamp=value(1)
    read_times=.TRUE.
  END FUNCTION read_times

  LOGICAL FUNCTION read_text_attribute(ncid,name,expected)
    INTEGER, INTENT(IN) :: ncid
    CHARACTER(LEN=*), INTENT(IN) :: name,expected
    CHARACTER(LEN=128) :: actual

    actual=''
    IF (nf90_get_att(ncid,NF90_GLOBAL,TRIM(name),actual)/=NF90_NOERR) THEN
      read_text_attribute=.FALSE.
      RETURN
    END IF
    read_text_attribute=TRIM(actual)==TRIM(expected)
  END FUNCTION read_text_attribute

  SUBROUTINE close_dataset(ncid)
    INTEGER, INTENT(INOUT) :: ncid
    IF (ncid>=0) ncid=nf90_close(ncid)
  END SUBROUTINE close_dataset

END MODULE cloud_bal_native_w_consumer
