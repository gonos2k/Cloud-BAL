! Versioned canonical state exchange for separate Cloud-BAL stages.
!
! This module owns serialization of a complete cloud_bal_state_type plus the
! longitude grid and explicitly separated COM evidence.  It does not compute
! a byte hash.  The caller must pass a detached input whose bytes and source
! manifest have already been verified by the publication/coordinator layer.
! Every value field has a 0/1 validity mask and independent canonical quality
! and source bitmask variables; those encodings are intentionally distinct.
MODULE cloud_bal_stage_payload
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,int32,int64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  USE netcdf
  USE cloud_bal_state, ONLY: CLOUD_BAL_SCHEMA_VERSION,STATUS_FAILED,STATUS_OK, &
    REASON_METADATA,REASON_SHAPE,REASON_RANGE,REASON_NONFINITE, &
    cloud_bal_state_type,field3d,field2d,field4d,integer_field3d, &
    initialize_cloud_bal_state,initialize_field,validate_canonical_state, &
    field3d_shape_metadata_ok,source_bits_known,quality_bits_known, &
    REASON_NONE
  IMPLICIT NONE
  PRIVATE

  INTEGER(int32), PARAMETER, PUBLIC :: CLOUD_BAL_PAYLOAD_EXCHANGE_VERSION=1_int32

  TYPE, PUBLIC :: stage_payload_identity
    INTEGER(int32) :: exchange_version=CLOUD_BAL_PAYLOAD_EXCHANGE_VERSION
    INTEGER(int32) :: schema_version=CLOUD_BAL_SCHEMA_VERSION
    CHARACTER(LEN=32) :: stage=''
    CHARACTER(LEN=64) :: generation_id=''
    INTEGER(int64) :: valid_time=0_int64
    INTEGER(int64) :: reference_time=0_int64
    CHARACTER(LEN=64) :: grid_id=''
    CHARACTER(LEN=16) :: vertical_order=''
    CHARACTER(LEN=16) :: wind_coordinate=''
    CHARACTER(LEN=64) :: producer_source_sha256=''
    CHARACTER(LEN=64) :: producer_binary_sha256=''
    CHARACTER(LEN=64) :: configuration_sha256=''
    CHARACTER(LEN=64) :: input_manifest_sha256=''
    LOGICAL :: dynamic_target_authorized=.FALSE.
  END TYPE stage_payload_identity

  TYPE, PUBLIC :: cloud_bal_stage_payload_type
    TYPE(cloud_bal_state_type) :: state
    REAL(real32), ALLOCATABLE :: longitude(:,:)
    TYPE(field3d) :: cloud_omega_evidence
    TYPE(stage_payload_identity) :: identity
  END TYPE cloud_bal_stage_payload_type

  PUBLIC :: write_cloud_bal_stage_payload
  PUBLIC :: read_cloud_bal_stage_payload

  TYPE :: field3d_ids
    INTEGER :: value_id=-1,valid_id=-1,quality_id=-1,source_id=-1
  END TYPE field3d_ids
  TYPE :: field2d_ids
    INTEGER :: value_id=-1,valid_id=-1,quality_id=-1,source_id=-1
  END TYPE field2d_ids
  TYPE :: integer3d_ids
    INTEGER :: value_id=-1,valid_id=-1,quality_id=-1,source_id=-1
  END TYPE integer3d_ids

CONTAINS

  SUBROUTINE write_cloud_bal_stage_payload(path,payload,status,reason)
    CHARACTER(LEN=*), INTENT(IN) :: path
    TYPE(cloud_bal_stage_payload_type), INTENT(IN) :: payload
    INTEGER, INTENT(OUT) :: status,reason
    INTEGER :: ncid,rc,xdim,ydim,zdim,interface_dim,spacing_dim,record_dim
    INTEGER :: longitude_id,dx_id,dy_id,interface_id,cell_dp_id,spacing_id
    INTEGER :: pressure_mass_id,dry_mass_id,above_ground_id,obs_support_id
    INTEGER :: hydro_support_id,beta_id
    TYPE(field3d_ids) :: f3(19)
    TYPE(field2d_ids) :: f2(7)
    TYPE(integer3d_ids) :: fi(3)
    LOGICAL :: ok,created

    status=STATUS_FAILED; reason=REASON_METADATA; created=.FALSE.
    CALL validate_payload(payload,status,reason)
    IF (status/=STATUS_OK) RETURN
    ! Validation is complete; all subsequent exits must remain failure until
    ! the file has closed successfully and can be published by the caller.
    status=STATUS_FAILED; reason=REASON_METADATA

    rc=nf90_create(TRIM(path),IOR(NF90_NOCLOBBER,NF90_NETCDF4),ncid)
    IF (rc/=NF90_NOERR) RETURN
    created=.TRUE.
    ok=nc_ok(nf90_def_dim(ncid,'x',payload%state%grid%nx,xdim)) .AND. &
       nc_ok(nf90_def_dim(ncid,'y',payload%state%grid%ny,ydim)) .AND. &
       nc_ok(nf90_def_dim(ncid,'z',payload%state%grid%nz,zdim)) .AND. &
       nc_ok(nf90_def_dim(ncid,'z_interface',payload%state%grid%nz+1,interface_dim)) .AND. &
       nc_ok(nf90_def_dim(ncid,'z_spacing',MAX(1,payload%state%grid%nz-1),spacing_dim)) .AND. &
       nc_ok(nf90_def_dim(ncid,'record',1,record_dim))
    IF (.NOT.ok) GOTO 900

    ok=define_scalar_vars(ncid,xdim,ydim,zdim,interface_dim,spacing_dim,record_dim, &
      longitude_id,dx_id,dy_id,interface_id,cell_dp_id,spacing_id,pressure_mass_id, &
      dry_mass_id,above_ground_id,obs_support_id,hydro_support_id,beta_id)
    IF (.NOT.ok) GOTO 900
    ok=define_all_fields(ncid,xdim,ydim,zdim,record_dim,payload,f3,f2,fi)
    IF (.NOT.ok) GOTO 900
    IF (.NOT.put_global_identity(ncid,payload%identity,payload%state%grid%nx, &
      payload%state%grid%ny,payload%state%grid%nz)) GOTO 900
    IF (.NOT.nc_ok(nf90_enddef(ncid))) GOTO 900

    ok=nc_ok(nf90_put_var(ncid,longitude_id,payload%longitude)) .AND. &
       nc_ok(nf90_put_var(ncid,dx_id,payload%state%grid%dx)) .AND. &
       nc_ok(nf90_put_var(ncid,dy_id,payload%state%grid%dy)) .AND. &
       nc_ok(nf90_put_var(ncid,interface_id,payload%state%grid%pressure_interface)) .AND. &
       nc_ok(nf90_put_var(ncid,cell_dp_id,payload%state%grid%cell_dp)) .AND. &
       nc_ok(nf90_put_var(ncid,spacing_id,payload%state%grid%level_spacing_dp)) .AND. &
       nc_ok(nf90_put_var(ncid,pressure_mass_id,payload%state%grid%pressure_mass_measure)) .AND. &
       nc_ok(nf90_put_var(ncid,dry_mass_id,payload%state%grid%dry_air_mass_measure)) .AND. &
       nc_ok(put_mask3d(ncid,above_ground_id,payload%state%above_ground)) .AND. &
       nc_ok(put_record_i32(ncid,obs_support_id,payload%state%obs_support)) .AND. &
       nc_ok(put_record_i32(ncid,hydro_support_id,payload%state%hydro_support)) .AND. &
       nc_ok(put_record_real32(ncid,beta_id,payload%state%balance_beta))
    IF (.NOT.ok) GOTO 900
    IF (.NOT.write_all_fields(ncid,payload,f3,f2,fi)) GOTO 900
    rc=nf90_close(ncid)
    IF (rc/=NF90_NOERR) THEN
      CALL delete_file_if_created(path,created)
      RETURN
    END IF
    status=STATUS_OK; reason=REASON_NONE
    RETURN

900 CONTINUE
    IF (created) THEN
      rc=nf90_close(ncid)
      CALL delete_file_if_created(path,.TRUE.)
    END IF
    status=STATUS_FAILED
    IF (reason==0) reason=REASON_METADATA
  END SUBROUTINE write_cloud_bal_stage_payload

  SUBROUTINE read_cloud_bal_stage_payload(path,expected,payload,status,reason)
    CHARACTER(LEN=*), INTENT(IN) :: path
    TYPE(stage_payload_identity), INTENT(IN) :: expected
    TYPE(cloud_bal_stage_payload_type), INTENT(OUT) :: payload
    INTEGER, INTENT(OUT) :: status,reason
    TYPE(cloud_bal_stage_payload_type) :: work
    INTEGER :: ncid,rc,nx,ny,nz,xdim,ydim,zdim,interface_dim,spacing_dim,record_dim
    INTEGER :: longitude_id,dx_id,dy_id,interface_id,cell_dp_id,spacing_id
    INTEGER :: pressure_mass_id,dry_mass_id,above_ground_id,obs_support_id
    INTEGER :: hydro_support_id,beta_id,local_status,local_reason
    TYPE(field3d_ids) :: f3(19)
    TYPE(field2d_ids) :: f2(7)
    TYPE(integer3d_ids) :: fi(3)
    LOGICAL :: ok

    status=STATUS_FAILED; reason=REASON_METADATA
    rc=nf90_open(TRIM(path),NF90_NOWRITE,ncid)
    IF (rc/=NF90_NOERR) RETURN
    ok=get_dim(ncid,'x',xdim) .AND. get_dim(ncid,'y',ydim) .AND. &
       get_dim(ncid,'z',zdim) .AND. get_dim(ncid,'z_interface',interface_dim) .AND. &
       get_dim(ncid,'z_spacing',spacing_dim) .AND. get_dim(ncid,'record',record_dim)
    IF (.NOT.ok .OR. record_dim/=1 .OR. interface_dim/=zdim+1 .OR. &
        spacing_dim/=MAX(1,zdim-1)) THEN
      rc=nf90_close(ncid); reason=REASON_SHAPE; RETURN
    END IF
    IF (.NOT.read_global_identity(ncid,work%identity)) THEN
      rc=nf90_close(ncid); RETURN
    END IF
    IF (.NOT.global_contract_ok(ncid)) THEN
      rc=nf90_close(ncid); reason=REASON_METADATA; RETURN
    END IF
    IF (.NOT.identity_matches_expected(work%identity,expected)) THEN
      rc=nf90_close(ncid); reason=REASON_METADATA; RETURN
    END IF
    nx=xdim; ny=ydim; nz=zdim
    CALL initialize_cloud_bal_state(work%state,nx,ny,nz,work%identity%valid_time, &
                                    work%identity%grid_id,local_status)
    IF (local_status/=STATUS_OK) THEN
      rc=nf90_close(ncid); reason=REASON_SHAPE; RETURN
    END IF
    CALL initialize_field(work%cloud_omega_evidence,nx,ny,nz,work%identity%valid_time,'Pa s-1')
    ALLOCATE(work%longitude(nx,ny))

    ok=inq_scalar_vars(ncid,longitude_id,dx_id,dy_id,interface_id,cell_dp_id,spacing_id, &
      pressure_mass_id,dry_mass_id,above_ground_id,obs_support_id,hydro_support_id,beta_id)
    IF (.NOT.ok) GOTO 900
    IF (.NOT.scalar_metadata_ok(ncid,xdim,ydim,zdim,interface_dim,spacing_dim,record_dim, &
        longitude_id,dx_id,dy_id,interface_id,cell_dp_id,spacing_id,pressure_mass_id, &
        dry_mass_id,above_ground_id,obs_support_id,hydro_support_id,beta_id)) THEN
      GOTO 900
    END IF
    IF (.NOT.read_all_fields(ncid,work,f3,f2,fi)) THEN
      GOTO 900
    END IF
    ok=nc_ok(nf90_get_var(ncid,longitude_id,work%longitude)) .AND. &
       nc_ok(nf90_get_var(ncid,dx_id,work%state%grid%dx)) .AND. &
       nc_ok(nf90_get_var(ncid,dy_id,work%state%grid%dy)) .AND. &
       nc_ok(nf90_get_var(ncid,interface_id,work%state%grid%pressure_interface)) .AND. &
       nc_ok(nf90_get_var(ncid,cell_dp_id,work%state%grid%cell_dp)) .AND. &
       nc_ok(nf90_get_var(ncid,spacing_id,work%state%grid%level_spacing_dp)) .AND. &
       nc_ok(nf90_get_var(ncid,pressure_mass_id,work%state%grid%pressure_mass_measure)) .AND. &
       nc_ok(nf90_get_var(ncid,dry_mass_id,work%state%grid%dry_air_mass_measure)) .AND. &
       nc_ok(get_mask3d(ncid,above_ground_id,work%state%above_ground)) .AND. &
       nc_ok(get_record_i32(ncid,obs_support_id,work%state%obs_support)) .AND. &
       nc_ok(get_record_i32(ncid,hydro_support_id,work%state%hydro_support)) .AND. &
       nc_ok(get_record_real32(ncid,beta_id,work%state%balance_beta))
    IF (.NOT.ok) GOTO 900
    IF (.NOT.read_radar_presence(ncid)) THEN
      reason=REASON_METADATA; GOTO 900
    END IF
    CALL validate_payload(work,local_status,local_reason)
    IF (local_status/=STATUS_OK) THEN
      status=local_status; reason=local_reason; GOTO 900
    END IF
    rc=nf90_close(ncid)
    IF (rc/=NF90_NOERR) THEN
      reason=REASON_METADATA; RETURN
    END IF
    payload=work
    status=STATUS_OK; reason=REASON_NONE
    RETURN

900 CONTINUE
    rc=nf90_close(ncid)
    IF (reason==0) reason=REASON_METADATA
    status=STATUS_FAILED
  END SUBROUTINE read_cloud_bal_stage_payload

  SUBROUTINE validate_payload(payload,status,reason)
    TYPE(cloud_bal_stage_payload_type), INTENT(IN) :: payload
    INTEGER, INTENT(OUT) :: status,reason
    INTEGER :: state_status,state_reason,nx,ny,nz
    status=STATUS_FAILED; reason=REASON_METADATA
    nx=payload%state%grid%nx; ny=payload%state%grid%ny; nz=payload%state%grid%nz
    CALL validate_canonical_state(payload%state,.FALSE.,.FALSE.,state_status,state_reason,.TRUE.)
    IF (state_status==STATUS_FAILED) THEN
      reason=state_reason; RETURN
    END IF
    IF (.NOT.identity_matches_state(payload%identity,payload%state)) RETURN
    IF (.NOT.ALLOCATED(payload%longitude)) THEN
      reason=REASON_SHAPE; RETURN
    END IF
    IF (ANY(SHAPE(payload%longitude)/=(/nx,ny/))) THEN
      reason=REASON_SHAPE; RETURN
    END IF
    IF (ANY(.NOT.ieee_is_finite(payload%longitude)) .OR. &
        ANY(payload%longitude < -180.0_real32) .OR. &
        ANY(payload%longitude > 180.0_real32)) THEN
      reason=REASON_RANGE; RETURN
    END IF
    IF (.NOT.field3d_shape_metadata_ok(payload%cloud_omega_evidence,nx,ny,nz, &
        payload%identity%valid_time,'Pa s-1')) THEN
      reason=REASON_METADATA; RETURN
    END IF
    IF (ANY(payload%cloud_omega_evidence%valid .AND. &
        .NOT.ieee_is_finite(payload%cloud_omega_evidence%value))) THEN
      reason=REASON_NONFINITE; RETURN
    END IF
    IF (ANY(.NOT.source_bits_known(payload%cloud_omega_evidence%source)) .OR. &
        ANY(.NOT.quality_bits_known(payload%cloud_omega_evidence%quality))) THEN
      reason=REASON_METADATA; RETURN
    END IF
    IF (.NOT.radar_los_is_absent(payload%state%radar_los)) THEN
      reason=REASON_METADATA; RETURN
    END IF
    IF (payload%identity%dynamic_target_authorized) THEN
      ! This first exchange has no authority registry.  It cannot grant one.
      reason=REASON_METADATA; RETURN
    END IF
    status=STATUS_OK; reason=REASON_NONE
  END SUBROUTINE validate_payload

  LOGICAL FUNCTION identity_matches_state(identity,state)
    TYPE(stage_payload_identity), INTENT(IN) :: identity
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    identity_matches_state=.FALSE.
    IF (identity%exchange_version/=CLOUD_BAL_PAYLOAD_EXCHANGE_VERSION .OR. &
        identity%schema_version/=CLOUD_BAL_SCHEMA_VERSION) RETURN
    IF (LEN_TRIM(identity%stage)==0 .OR. LEN_TRIM(identity%generation_id)==0 .OR. &
        LEN_TRIM(identity%grid_id)==0 .OR. LEN_TRIM(identity%vertical_order)==0 .OR. &
        LEN_TRIM(identity%wind_coordinate)==0) RETURN
    IF (identity%valid_time/=state%pressure%valid_time .OR. &
        identity%grid_id/=state%grid%grid_id .OR. &
        TRIM(identity%vertical_order)/='bottom_to_top' .OR. &
        TRIM(identity%wind_coordinate)/='GRID_RELATIVE') RETURN
    IF (.NOT.digest_text_valid(identity%producer_source_sha256) .OR. &
        .NOT.digest_text_valid(identity%producer_binary_sha256) .OR. &
        .NOT.digest_text_valid(identity%configuration_sha256) .OR. &
        .NOT.digest_text_valid(identity%input_manifest_sha256)) RETURN
    identity_matches_state=.TRUE.
  END FUNCTION identity_matches_state

  LOGICAL FUNCTION identity_matches_expected(actual,expected)
    TYPE(stage_payload_identity), INTENT(IN) :: actual,expected
    identity_matches_expected=identity_matches_state_metadata(actual,expected)
  END FUNCTION identity_matches_expected

  LOGICAL FUNCTION identity_matches_state_metadata(actual,expected)
    TYPE(stage_payload_identity), INTENT(IN) :: actual,expected
    identity_matches_state_metadata=.FALSE.
    IF (actual%exchange_version/=expected%exchange_version) RETURN
    IF (actual%schema_version/=expected%schema_version) RETURN
    IF (actual%stage/=expected%stage) RETURN
    IF (actual%generation_id/=expected%generation_id) RETURN
    IF (actual%valid_time/=expected%valid_time) RETURN
    IF (actual%reference_time/=expected%reference_time) RETURN
    IF (actual%grid_id/=expected%grid_id) RETURN
    IF (actual%vertical_order/=expected%vertical_order) RETURN
    IF (actual%wind_coordinate/=expected%wind_coordinate) RETURN
    IF (actual%producer_source_sha256/=expected%producer_source_sha256) RETURN
    IF (actual%producer_binary_sha256/=expected%producer_binary_sha256) RETURN
    IF (actual%configuration_sha256/=expected%configuration_sha256) RETURN
    IF (actual%input_manifest_sha256/=expected%input_manifest_sha256) RETURN
    IF (actual%dynamic_target_authorized .NEQV. expected%dynamic_target_authorized) RETURN
    identity_matches_state_metadata=.TRUE.
  END FUNCTION identity_matches_state_metadata

  LOGICAL FUNCTION digest_text_valid(value)
    CHARACTER(LEN=*), INTENT(IN) :: value
    INTEGER :: i,c
    digest_text_valid=LEN_TRIM(value)==64
    IF (.NOT.digest_text_valid) RETURN
    DO i=1,64
      c=IACHAR(value(i:i))
      IF (.NOT.((c>=IACHAR('0') .AND. c<=IACHAR('9')) .OR. &
                (c>=IACHAR('a') .AND. c<=IACHAR('f')) .OR. &
                (c>=IACHAR('A') .AND. c<=IACHAR('F')))) THEN
        digest_text_valid=.FALSE.; RETURN
      END IF
    END DO
  END FUNCTION digest_text_valid

  LOGICAL FUNCTION radar_los_is_absent(los)
    USE cloud_bal_state, ONLY: radar_los_observation_set
    TYPE(radar_los_observation_set), INTENT(IN) :: los
    radar_los_is_absent=.NOT.los%is_present .AND. los%nradar==0 .AND. &
      los%vrad_representation==0_int32 .AND. .NOT.los%has_colocated_dbz .AND. &
      .NOT.los%has_spectrum_width .AND. &
      .NOT.ANY([ALLOCATED(los%beam),ALLOCATED(los%observation_id_hi), &
               ALLOCATED(los%observation_id_lo),ALLOCATED(los%usage), &
               ALLOCATED(los%radar_id),ALLOCATED(los%observation_time), &
               ALLOCATED(los%site_lat),ALLOCATED(los%site_lon), &
               ALLOCATED(los%site_height),ALLOCATED(los%wavelength), &
               ALLOCATED(los%los_support),ALLOCATED(los%geometry_condition), &
               ALLOCATED(los%geometry_rank)])
    IF (field4d_storage_allocated(los%vrad) .OR. &
        field4d_storage_allocated(los%nyquist) .OR. &
        field4d_storage_allocated(los%sigma_vrad) .OR. &
        field4d_storage_allocated(los%colocated_dbz) .OR. &
        field4d_storage_allocated(los%spectrum_width)) radar_los_is_absent=.FALSE.
  END FUNCTION radar_los_is_absent

  LOGICAL FUNCTION field4d_storage_allocated(field)
    TYPE(field4d), INTENT(IN) :: field
    field4d_storage_allocated=ALLOCATED(field%value) .OR. ALLOCATED(field%valid) .OR. &
      ALLOCATED(field%quality) .OR. ALLOCATED(field%source)
  END FUNCTION field4d_storage_allocated

  LOGICAL FUNCTION nc_ok(rc)
    INTEGER, INTENT(IN) :: rc
    nc_ok=rc==NF90_NOERR
  END FUNCTION nc_ok

  ! The dimensions are deliberately named and ordered here.  Fortran arrays
  ! are held as (x,y,z[,record]); the exchange contract records the logical
  ! on-disk order as record,z,y,x in a global attribute below.
  LOGICAL FUNCTION define_scalar_vars(ncid,xdim,ydim,zdim,interface_dim, &
                                      spacing_dim,record_dim,longitude_id,dx_id,dy_id, &
                                      interface_id,cell_dp_id,spacing_id,pressure_mass_id, &
                                      dry_mass_id,above_ground_id,obs_support_id, &
                                      hydro_support_id,beta_id)
    INTEGER, INTENT(IN) :: ncid,xdim,ydim,zdim,interface_dim,spacing_dim,record_dim
    INTEGER, INTENT(OUT) :: longitude_id,dx_id,dy_id,interface_id,cell_dp_id,spacing_id
    INTEGER, INTENT(OUT) :: pressure_mass_id,dry_mass_id,above_ground_id,obs_support_id
    INTEGER, INTENT(OUT) :: hydro_support_id,beta_id
    INTEGER :: d2(2),d3(3),d4(4)
    define_scalar_vars=.FALSE.
    d2=(/xdim,ydim/); d3=(/xdim,ydim,zdim/); d4=(/xdim,ydim,zdim,record_dim/)
    IF (.NOT.nc_ok(nf90_def_var(ncid,'longitude',NF90_FLOAT,d2,longitude_id))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,longitude_id,'units','degree_east'))) RETURN
    IF (.NOT.nc_ok(nf90_def_var(ncid,'grid_dx',NF90_DOUBLE,d2,dx_id))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,dx_id,'units','m'))) RETURN
    IF (.NOT.nc_ok(nf90_def_var(ncid,'grid_dy',NF90_DOUBLE,d2,dy_id))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,dy_id,'units','m'))) RETURN
    IF (.NOT.nc_ok(nf90_def_var(ncid,'pressure_interface',NF90_DOUBLE, &
        (/xdim,ydim,interface_dim/),interface_id))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,interface_id,'units','Pa'))) RETURN
    IF (.NOT.nc_ok(nf90_def_var(ncid,'cell_dp',NF90_DOUBLE,d3,cell_dp_id))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,cell_dp_id,'units','Pa'))) RETURN
    IF (.NOT.nc_ok(nf90_def_var(ncid,'level_spacing_dp',NF90_DOUBLE, &
        (/xdim,ydim,spacing_dim/),spacing_id))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,spacing_id,'units','Pa'))) RETURN
    IF (.NOT.nc_ok(nf90_def_var(ncid,'pressure_mass_measure',NF90_DOUBLE, &
        d3,pressure_mass_id))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,pressure_mass_id,'units','kg'))) RETURN
    IF (.NOT.nc_ok(nf90_def_var(ncid,'dry_air_mass_measure',NF90_DOUBLE, &
        d3,dry_mass_id))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,dry_mass_id,'units','kg dryair'))) RETURN
    IF (.NOT.nc_ok(nf90_def_var(ncid,'above_ground',NF90_INT,d4,above_ground_id))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,above_ground_id,'mask_encoding','0=below_ground,1=above_ground'))) RETURN
    IF (.NOT.nc_ok(nf90_def_var(ncid,'obs_support',NF90_INT,d4,obs_support_id))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,obs_support_id,'units','1'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,obs_support_id,'support_encoding','canonical_source_bits'))) RETURN
    IF (.NOT.nc_ok(nf90_def_var(ncid,'hydro_support',NF90_INT,d4,hydro_support_id))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,hydro_support_id,'units','1'))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,hydro_support_id,'support_encoding','canonical_source_bits'))) RETURN
    IF (.NOT.nc_ok(nf90_def_var(ncid,'balance_beta',NF90_FLOAT,d4,beta_id))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,beta_id,'units','1'))) RETURN
    define_scalar_vars=.TRUE.
  END FUNCTION define_scalar_vars

  LOGICAL FUNCTION define_all_fields(ncid,xdim,ydim,zdim,record_dim,payload,f3,f2,fi)
    INTEGER, INTENT(IN) :: ncid,xdim,ydim,zdim,record_dim
    TYPE(cloud_bal_stage_payload_type), INTENT(IN) :: payload
    TYPE(field3d_ids), INTENT(OUT) :: f3(19)
    TYPE(field2d_ids), INTENT(OUT) :: f2(7)
    TYPE(integer3d_ids), INTENT(OUT) :: fi(3)
    define_all_fields=.FALSE.
    IF (.NOT.define_field3d(ncid,'pressure',xdim,ydim,zdim,record_dim,payload%state%pressure,f3(1))) RETURN
    IF (.NOT.define_field3d(ncid,'temperature',xdim,ydim,zdim,record_dim,payload%state%temperature,f3(2))) RETURN
    IF (.NOT.define_field3d(ncid,'vapor',xdim,ydim,zdim,record_dim,payload%state%vapor,f3(3))) RETURN
    IF (.NOT.define_field3d(ncid,'u',xdim,ydim,zdim,record_dim,payload%state%u,f3(4))) RETURN
    IF (.NOT.define_field3d(ncid,'v',xdim,ydim,zdim,record_dim,payload%state%v,f3(5))) RETURN
    IF (.NOT.define_field3d(ncid,'omega',xdim,ydim,zdim,record_dim,payload%state%omega,f3(6))) RETURN
    IF (.NOT.define_field3d(ncid,'omega_target',xdim,ydim,zdim,record_dim,payload%state%omega_target,f3(7))) RETURN
    IF (.NOT.define_field3d(ncid,'omega_target_sigma',xdim,ydim,zdim,record_dim,payload%state%omega_target_sigma,f3(8))) RETURN
    IF (.NOT.define_field3d(ncid,'geopotential',xdim,ydim,zdim,record_dim,payload%state%geopotential,f3(9))) RETURN
    IF (.NOT.define_field3d(ncid,'cloud_fraction',xdim,ydim,zdim,record_dim,payload%state%cloud_fraction,f3(10))) RETURN
    IF (.NOT.define_field3d(ncid,'radar_reflectivity',xdim,ydim,zdim,record_dim,payload%state%radar_reflectivity,f3(11))) RETURN
    IF (.NOT.define_field3d(ncid,'cloud_water',xdim,ydim,zdim,record_dim,payload%state%cloud_water,f3(12))) RETURN
    IF (.NOT.define_field3d(ncid,'cloud_ice',xdim,ydim,zdim,record_dim,payload%state%cloud_ice,f3(13))) RETURN
    IF (.NOT.define_field3d(ncid,'rain',xdim,ydim,zdim,record_dim,payload%state%rain,f3(14))) RETURN
    IF (.NOT.define_field3d(ncid,'snow',xdim,ydim,zdim,record_dim,payload%state%snow,f3(15))) RETURN
    IF (.NOT.define_field3d(ncid,'graupel',xdim,ydim,zdim,record_dim,payload%state%graupel,f3(16))) RETURN
    IF (.NOT.define_field3d(ncid,'vt_z_mean',xdim,ydim,zdim,record_dim,payload%state%vt_z_mean,f3(17))) RETURN
    IF (.NOT.define_field3d(ncid,'vt_z_sigma',xdim,ydim,zdim,record_dim,payload%state%vt_z_sigma,f3(18))) RETURN
    IF (.NOT.define_field3d(ncid,'cloud_omega_evidence',xdim,ydim,zdim,record_dim, &
        payload%cloud_omega_evidence,f3(19))) RETURN
    IF (.NOT.define_field2d(ncid,'surface_pressure',xdim,ydim,record_dim,payload%state%surface_pressure,f2(1))) RETURN
    IF (.NOT.define_field2d(ncid,'surface_temperature',xdim,ydim,record_dim,payload%state%surface_temperature,f2(2))) RETURN
    IF (.NOT.define_field2d(ncid,'surface_vapor',xdim,ydim,record_dim,payload%state%surface_vapor,f2(3))) RETURN
    IF (.NOT.define_field2d(ncid,'surface_height',xdim,ydim,record_dim,payload%state%surface_height,f2(4))) RETURN
    IF (.NOT.define_field2d(ncid,'latitude',xdim,ydim,record_dim,payload%state%latitude,f2(5))) RETURN
    IF (.NOT.define_field2d(ncid,'omega_top_boundary',xdim,ydim,record_dim, &
        payload%state%omega_top_boundary,f2(6))) RETURN
    IF (.NOT.define_field2d(ncid,'omega_bottom_boundary',xdim,ydim,record_dim, &
        payload%state%omega_bottom_boundary,f2(7))) RETURN
    IF (.NOT.define_integer3d(ncid,'cloud_type',xdim,ydim,zdim,record_dim,payload%state%cloud_type,fi(1))) RETURN
    IF (.NOT.define_integer3d(ncid,'precipitation_phase',xdim,ydim,zdim,record_dim, &
        payload%state%precipitation_phase,fi(2))) RETURN
    IF (.NOT.define_integer3d(ncid,'lightning_support',xdim,ydim,zdim,record_dim, &
        payload%state%lightning_support,fi(3))) RETURN
    define_all_fields=.TRUE.
  END FUNCTION define_all_fields

  LOGICAL FUNCTION define_field3d(ncid,name,xdim,ydim,zdim,record_dim,field,ids)
    INTEGER, INTENT(IN) :: ncid,xdim,ydim,zdim,record_dim
    CHARACTER(LEN=*), INTENT(IN) :: name
    TYPE(field3d), INTENT(IN) :: field
    TYPE(field3d_ids), INTENT(OUT) :: ids
    INTEGER :: dims(4)
    define_field3d=.FALSE.; dims=(/xdim,ydim,zdim,record_dim/)
    IF (.NOT.nc_ok(nf90_def_var(ncid,TRIM(name),NF90_FLOAT,dims,ids%value_id))) RETURN
    IF (.NOT.nc_ok(nf90_def_var(ncid,TRIM(name)//'_valid',NF90_INT,dims,ids%valid_id))) RETURN
    IF (.NOT.nc_ok(nf90_def_var(ncid,TRIM(name)//'_quality',NF90_INT,dims,ids%quality_id))) RETURN
    IF (.NOT.nc_ok(nf90_def_var(ncid,TRIM(name)//'_source',NF90_INT,dims,ids%source_id))) RETURN
    IF (.NOT.field_value_attributes(ncid,ids%value_id,field%unit,field%valid_time,'continuous')) RETURN
    IF (.NOT.mask_attributes(ncid,ids%valid_id)) RETURN
    IF (.NOT.bitmask_attributes(ncid,ids%quality_id,'canonical_quality_bits_v1')) RETURN
    IF (.NOT.bitmask_attributes(ncid,ids%source_id,'canonical_source_bits_v1')) RETURN
    define_field3d=.TRUE.
  END FUNCTION define_field3d

  LOGICAL FUNCTION define_field2d(ncid,name,xdim,ydim,record_dim,field,ids)
    INTEGER, INTENT(IN) :: ncid,xdim,ydim,record_dim
    CHARACTER(LEN=*), INTENT(IN) :: name
    TYPE(field2d), INTENT(IN) :: field
    TYPE(field2d_ids), INTENT(OUT) :: ids
    INTEGER :: dims(3)
    define_field2d=.FALSE.; dims=(/xdim,ydim,record_dim/)
    IF (.NOT.nc_ok(nf90_def_var(ncid,TRIM(name),NF90_FLOAT,dims,ids%value_id))) RETURN
    IF (.NOT.nc_ok(nf90_def_var(ncid,TRIM(name)//'_valid',NF90_INT,dims,ids%valid_id))) RETURN
    IF (.NOT.nc_ok(nf90_def_var(ncid,TRIM(name)//'_quality',NF90_INT,dims,ids%quality_id))) RETURN
    IF (.NOT.nc_ok(nf90_def_var(ncid,TRIM(name)//'_source',NF90_INT,dims,ids%source_id))) RETURN
    IF (.NOT.field_value_attributes(ncid,ids%value_id,field%unit,field%valid_time,'continuous')) RETURN
    IF (.NOT.mask_attributes(ncid,ids%valid_id)) RETURN
    IF (.NOT.bitmask_attributes(ncid,ids%quality_id,'canonical_quality_bits_v1')) RETURN
    IF (.NOT.bitmask_attributes(ncid,ids%source_id,'canonical_source_bits_v1')) RETURN
    define_field2d=.TRUE.
  END FUNCTION define_field2d

  LOGICAL FUNCTION define_integer3d(ncid,name,xdim,ydim,zdim,record_dim,field,ids)
    INTEGER, INTENT(IN) :: ncid,xdim,ydim,zdim,record_dim
    CHARACTER(LEN=*), INTENT(IN) :: name
    TYPE(integer_field3d), INTENT(IN) :: field
    TYPE(integer3d_ids), INTENT(OUT) :: ids
    INTEGER :: dims(4)
    define_integer3d=.FALSE.; dims=(/xdim,ydim,zdim,record_dim/)
    IF (.NOT.nc_ok(nf90_def_var(ncid,TRIM(name),NF90_INT,dims,ids%value_id))) RETURN
    IF (.NOT.nc_ok(nf90_def_var(ncid,TRIM(name)//'_valid',NF90_INT,dims,ids%valid_id))) RETURN
    IF (.NOT.nc_ok(nf90_def_var(ncid,TRIM(name)//'_quality',NF90_INT,dims,ids%quality_id))) RETURN
    IF (.NOT.nc_ok(nf90_def_var(ncid,TRIM(name)//'_source',NF90_INT,dims,ids%source_id))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,ids%value_id,'code_table',TRIM(field%code_table)))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,ids%value_id,'valid_time',field%valid_time))) RETURN
    IF (.NOT.nc_ok(nf90_put_att(ncid,ids%value_id,'field_kind','categorical'))) RETURN
    IF (.NOT.mask_attributes(ncid,ids%valid_id)) RETURN
    IF (.NOT.bitmask_attributes(ncid,ids%quality_id,'canonical_quality_bits_v1')) RETURN
    IF (.NOT.bitmask_attributes(ncid,ids%source_id,'canonical_source_bits_v1')) RETURN
    define_integer3d=.TRUE.
  END FUNCTION define_integer3d

  LOGICAL FUNCTION field_value_attributes(ncid,varid,unit,valid_time,kind)
    INTEGER, INTENT(IN) :: ncid,varid
    CHARACTER(LEN=*), INTENT(IN) :: unit,kind
    INTEGER(int64), INTENT(IN) :: valid_time
    field_value_attributes=nc_ok(nf90_put_att(ncid,varid,'units',TRIM(unit))) .AND. &
      nc_ok(nf90_put_att(ncid,varid,'valid_time',valid_time)) .AND. &
      nc_ok(nf90_put_att(ncid,varid,'field_kind',TRIM(kind)))
  END FUNCTION field_value_attributes

  LOGICAL FUNCTION mask_attributes(ncid,varid)
    INTEGER, INTENT(IN) :: ncid,varid
    mask_attributes=nc_ok(nf90_put_att(ncid,varid,'mask_encoding','0=invalid,1=valid'))
  END FUNCTION mask_attributes

  LOGICAL FUNCTION bitmask_attributes(ncid,varid,encoding)
    INTEGER, INTENT(IN) :: ncid,varid
    CHARACTER(LEN=*), INTENT(IN) :: encoding
    bitmask_attributes=nc_ok(nf90_put_att(ncid,varid,'mask_encoding',TRIM(encoding)))
  END FUNCTION bitmask_attributes

  LOGICAL FUNCTION write_all_fields(ncid,payload,f3,f2,fi)
    INTEGER, INTENT(IN) :: ncid
    TYPE(cloud_bal_stage_payload_type), INTENT(IN) :: payload
    TYPE(field3d_ids), INTENT(IN) :: f3(19)
    TYPE(field2d_ids), INTENT(IN) :: f2(7)
    TYPE(integer3d_ids), INTENT(IN) :: fi(3)
    write_all_fields=.FALSE.
    IF (put_field3d(ncid,f3(1),payload%state%pressure)/=NF90_NOERR) RETURN
    IF (put_field3d(ncid,f3(2),payload%state%temperature)/=NF90_NOERR) RETURN
    IF (put_field3d(ncid,f3(3),payload%state%vapor)/=NF90_NOERR) RETURN
    IF (put_field3d(ncid,f3(4),payload%state%u)/=NF90_NOERR) RETURN
    IF (put_field3d(ncid,f3(5),payload%state%v)/=NF90_NOERR) RETURN
    IF (put_field3d(ncid,f3(6),payload%state%omega)/=NF90_NOERR) RETURN
    IF (put_field3d(ncid,f3(7),payload%state%omega_target)/=NF90_NOERR) RETURN
    IF (put_field3d(ncid,f3(8),payload%state%omega_target_sigma)/=NF90_NOERR) RETURN
    IF (put_field3d(ncid,f3(9),payload%state%geopotential)/=NF90_NOERR) RETURN
    IF (put_field3d(ncid,f3(10),payload%state%cloud_fraction)/=NF90_NOERR) RETURN
    IF (put_field3d(ncid,f3(11),payload%state%radar_reflectivity)/=NF90_NOERR) RETURN
    IF (put_field3d(ncid,f3(12),payload%state%cloud_water)/=NF90_NOERR) RETURN
    IF (put_field3d(ncid,f3(13),payload%state%cloud_ice)/=NF90_NOERR) RETURN
    IF (put_field3d(ncid,f3(14),payload%state%rain)/=NF90_NOERR) RETURN
    IF (put_field3d(ncid,f3(15),payload%state%snow)/=NF90_NOERR) RETURN
    IF (put_field3d(ncid,f3(16),payload%state%graupel)/=NF90_NOERR) RETURN
    IF (put_field3d(ncid,f3(17),payload%state%vt_z_mean)/=NF90_NOERR) RETURN
    IF (put_field3d(ncid,f3(18),payload%state%vt_z_sigma)/=NF90_NOERR) RETURN
    IF (put_field3d(ncid,f3(19),payload%cloud_omega_evidence)/=NF90_NOERR) RETURN
    IF (put_field2d(ncid,f2(1),payload%state%surface_pressure)/=NF90_NOERR) RETURN
    IF (put_field2d(ncid,f2(2),payload%state%surface_temperature)/=NF90_NOERR) RETURN
    IF (put_field2d(ncid,f2(3),payload%state%surface_vapor)/=NF90_NOERR) RETURN
    IF (put_field2d(ncid,f2(4),payload%state%surface_height)/=NF90_NOERR) RETURN
    IF (put_field2d(ncid,f2(5),payload%state%latitude)/=NF90_NOERR) RETURN
    IF (put_field2d(ncid,f2(6),payload%state%omega_top_boundary)/=NF90_NOERR) RETURN
    IF (put_field2d(ncid,f2(7),payload%state%omega_bottom_boundary)/=NF90_NOERR) RETURN
    IF (put_integer3d(ncid,fi(1),payload%state%cloud_type)/=NF90_NOERR) RETURN
    IF (put_integer3d(ncid,fi(2),payload%state%precipitation_phase)/=NF90_NOERR) RETURN
    IF (put_integer3d(ncid,fi(3),payload%state%lightning_support)/=NF90_NOERR) RETURN
    write_all_fields=.TRUE.
  END FUNCTION write_all_fields

  INTEGER FUNCTION put_field3d(ncid,ids,field)
    INTEGER, INTENT(IN) :: ncid
    TYPE(field3d_ids), INTENT(IN) :: ids
    TYPE(field3d), INTENT(IN) :: field
    INTEGER(int32), ALLOCATABLE :: valid(:,:,:,:),quality4(:,:,:,:),source4(:,:,:,:)
    REAL(real32), ALLOCATABLE :: value(:,:,:,:)
    INTEGER :: nx,ny,nz
    nx=SIZE(field%value,1); ny=SIZE(field%value,2); nz=SIZE(field%value,3)
    ALLOCATE(value(nx,ny,nz,1),valid(nx,ny,nz,1),quality4(nx,ny,nz,1),source4(nx,ny,nz,1))
    value(:,:,:,1)=field%value
    valid(:,:,:,1)=MERGE(1_int32,0_int32,field%valid)
    quality4(:,:,:,1)=field%quality; source4(:,:,:,1)=field%source
    put_field3d=nf90_put_var(ncid,ids%value_id,value)
    IF (put_field3d/=NF90_NOERR) RETURN
    put_field3d=nf90_put_var(ncid,ids%valid_id,valid)
    IF (put_field3d/=NF90_NOERR) RETURN
    put_field3d=nf90_put_var(ncid,ids%quality_id,quality4)
    IF (put_field3d/=NF90_NOERR) RETURN
    put_field3d=nf90_put_var(ncid,ids%source_id,source4)
  END FUNCTION put_field3d

  INTEGER FUNCTION put_field2d(ncid,ids,field)
    INTEGER, INTENT(IN) :: ncid
    TYPE(field2d_ids), INTENT(IN) :: ids
    TYPE(field2d), INTENT(IN) :: field
    INTEGER(int32), ALLOCATABLE :: valid(:,:,:),quality(:,:,:),source(:,:,:)
    REAL(real32), ALLOCATABLE :: value(:,:,:)
    INTEGER :: nx,ny
    nx=SIZE(field%value,1); ny=SIZE(field%value,2)
    ALLOCATE(value(nx,ny,1),valid(nx,ny,1),quality(nx,ny,1),source(nx,ny,1))
    value(:,:,1)=field%value; valid(:,:,1)=MERGE(1_int32,0_int32,field%valid)
    quality(:,:,1)=field%quality; source(:,:,1)=field%source
    put_field2d=nf90_put_var(ncid,ids%value_id,value)
    IF (put_field2d/=NF90_NOERR) RETURN
    put_field2d=nf90_put_var(ncid,ids%valid_id,valid)
    IF (put_field2d/=NF90_NOERR) RETURN
    put_field2d=nf90_put_var(ncid,ids%quality_id,quality)
    IF (put_field2d/=NF90_NOERR) RETURN
    put_field2d=nf90_put_var(ncid,ids%source_id,source)
  END FUNCTION put_field2d

  INTEGER FUNCTION put_integer3d(ncid,ids,field)
    INTEGER, INTENT(IN) :: ncid
    TYPE(integer3d_ids), INTENT(IN) :: ids
    TYPE(integer_field3d), INTENT(IN) :: field
    INTEGER(int32), ALLOCATABLE :: value(:,:,:,:),valid(:,:,:,:),quality(:,:,:,:),source(:,:,:,:)
    INTEGER :: nx,ny,nz
    nx=SIZE(field%value,1); ny=SIZE(field%value,2); nz=SIZE(field%value,3)
    ALLOCATE(value(nx,ny,nz,1),valid(nx,ny,nz,1),quality(nx,ny,nz,1),source(nx,ny,nz,1))
    value(:,:,:,1)=field%value; valid(:,:,:,1)=MERGE(1_int32,0_int32,field%valid)
    quality(:,:,:,1)=field%quality; source(:,:,:,1)=field%source
    put_integer3d=nf90_put_var(ncid,ids%value_id,value)
    IF (put_integer3d/=NF90_NOERR) RETURN
    put_integer3d=nf90_put_var(ncid,ids%valid_id,valid)
    IF (put_integer3d/=NF90_NOERR) RETURN
    put_integer3d=nf90_put_var(ncid,ids%quality_id,quality)
    IF (put_integer3d/=NF90_NOERR) RETURN
    put_integer3d=nf90_put_var(ncid,ids%source_id,source)
  END FUNCTION put_integer3d

  INTEGER FUNCTION put_mask3d(ncid,varid,mask)
    INTEGER, INTENT(IN) :: ncid,varid
    LOGICAL, INTENT(IN) :: mask(:,:,:)
    INTEGER(int32), ALLOCATABLE :: tmp(:,:,:,:)
    ALLOCATE(tmp(SIZE(mask,1),SIZE(mask,2),SIZE(mask,3),1))
    tmp(:,:,:,1)=MERGE(1_int32,0_int32,mask)
    put_mask3d=nf90_put_var(ncid,varid,tmp)
  END FUNCTION put_mask3d

  INTEGER FUNCTION put_record_i32(ncid,varid,values)
    INTEGER, INTENT(IN) :: ncid,varid
    INTEGER(int32), INTENT(IN) :: values(:,:,:)
    INTEGER(int32), ALLOCATABLE :: tmp(:,:,:,:)
    ALLOCATE(tmp(SIZE(values,1),SIZE(values,2),SIZE(values,3),1))
    tmp(:,:,:,1)=values
    put_record_i32=nf90_put_var(ncid,varid,tmp)
  END FUNCTION put_record_i32

  INTEGER FUNCTION put_record_real32(ncid,varid,values)
    INTEGER, INTENT(IN) :: ncid,varid
    REAL(real32), INTENT(IN) :: values(:,:,:)
    REAL(real32), ALLOCATABLE :: tmp(:,:,:,:)
    ALLOCATE(tmp(SIZE(values,1),SIZE(values,2),SIZE(values,3),1))
    tmp(:,:,:,1)=values
    put_record_real32=nf90_put_var(ncid,varid,tmp)
  END FUNCTION put_record_real32

  LOGICAL FUNCTION inq_scalar_vars(ncid,longitude_id,dx_id,dy_id,interface_id,cell_dp_id, &
                                   spacing_id,pressure_mass_id,dry_mass_id,above_ground_id, &
                                   obs_support_id,hydro_support_id,beta_id)
    INTEGER, INTENT(IN) :: ncid
    INTEGER, INTENT(OUT) :: longitude_id,dx_id,dy_id,interface_id,cell_dp_id,spacing_id
    INTEGER, INTENT(OUT) :: pressure_mass_id,dry_mass_id,above_ground_id,obs_support_id
    INTEGER, INTENT(OUT) :: hydro_support_id,beta_id
    inq_scalar_vars=.FALSE.
    IF (.NOT.nc_ok(nf90_inq_varid(ncid,'longitude',longitude_id))) RETURN
    IF (.NOT.nc_ok(nf90_inq_varid(ncid,'grid_dx',dx_id))) RETURN
    IF (.NOT.nc_ok(nf90_inq_varid(ncid,'grid_dy',dy_id))) RETURN
    IF (.NOT.nc_ok(nf90_inq_varid(ncid,'pressure_interface',interface_id))) RETURN
    IF (.NOT.nc_ok(nf90_inq_varid(ncid,'cell_dp',cell_dp_id))) RETURN
    IF (.NOT.nc_ok(nf90_inq_varid(ncid,'level_spacing_dp',spacing_id))) RETURN
    IF (.NOT.nc_ok(nf90_inq_varid(ncid,'pressure_mass_measure',pressure_mass_id))) RETURN
    IF (.NOT.nc_ok(nf90_inq_varid(ncid,'dry_air_mass_measure',dry_mass_id))) RETURN
    IF (.NOT.nc_ok(nf90_inq_varid(ncid,'above_ground',above_ground_id))) RETURN
    IF (.NOT.nc_ok(nf90_inq_varid(ncid,'obs_support',obs_support_id))) RETURN
    IF (.NOT.nc_ok(nf90_inq_varid(ncid,'hydro_support',hydro_support_id))) RETURN
    IF (.NOT.nc_ok(nf90_inq_varid(ncid,'balance_beta',beta_id))) RETURN
    inq_scalar_vars=.TRUE.
  END FUNCTION inq_scalar_vars

  LOGICAL FUNCTION scalar_metadata_ok(ncid,xdim,ydim,zdim,interface_dim,spacing_dim,record_dim, &
                                      longitude_id,dx_id,dy_id,interface_id,cell_dp_id,spacing_id, &
                                      pressure_mass_id,dry_mass_id,above_ground_id,obs_support_id, &
                                      hydro_support_id,beta_id)
    INTEGER, INTENT(IN) :: ncid,xdim,ydim,zdim,interface_dim,spacing_dim,record_dim
    INTEGER, INTENT(IN) :: longitude_id,dx_id,dy_id,interface_id,cell_dp_id,spacing_id
    INTEGER, INTENT(IN) :: pressure_mass_id,dry_mass_id,above_ground_id,obs_support_id
    INTEGER, INTENT(IN) :: hydro_support_id,beta_id
    scalar_metadata_ok=.FALSE.
    IF (.NOT.variable_layout_is(ncid,longitude_id,NF90_FLOAT, &
        [CHARACTER(LEN=16) :: 'x','y']) .OR. .NOT.variable_unit_is(ncid,longitude_id,'degree_east')) RETURN
    IF (.NOT.variable_layout_is(ncid,dx_id,NF90_DOUBLE, &
        [CHARACTER(LEN=16) :: 'x','y']) .OR. .NOT.variable_unit_is(ncid,dx_id,'m')) RETURN
    IF (.NOT.variable_layout_is(ncid,dy_id,NF90_DOUBLE, &
        [CHARACTER(LEN=16) :: 'x','y']) .OR. .NOT.variable_unit_is(ncid,dy_id,'m')) RETURN
    IF (.NOT.variable_layout_is(ncid,interface_id,NF90_DOUBLE, &
        [CHARACTER(LEN=16) :: 'x','y','z_interface']) .OR. .NOT.variable_unit_is(ncid,interface_id,'Pa')) RETURN
    IF (.NOT.variable_layout_is(ncid,cell_dp_id,NF90_DOUBLE, &
        [CHARACTER(LEN=16) :: 'x','y','z']) .OR. .NOT.variable_unit_is(ncid,cell_dp_id,'Pa')) RETURN
    IF (.NOT.variable_layout_is(ncid,spacing_id,NF90_DOUBLE, &
        [CHARACTER(LEN=16) :: 'x','y','z_spacing']) .OR. .NOT.variable_unit_is(ncid,spacing_id,'Pa')) RETURN
    IF (.NOT.variable_layout_is(ncid,pressure_mass_id,NF90_DOUBLE, &
        [CHARACTER(LEN=16) :: 'x','y','z']) .OR. .NOT.variable_unit_is(ncid,pressure_mass_id,'kg')) RETURN
    IF (.NOT.variable_layout_is(ncid,dry_mass_id,NF90_DOUBLE, &
        [CHARACTER(LEN=16) :: 'x','y','z']) .OR. .NOT.variable_unit_is(ncid,dry_mass_id,'kg dryair')) RETURN
    IF (.NOT.variable_layout_is(ncid,above_ground_id,NF90_INT, &
        [CHARACTER(LEN=16) :: 'x','y','z','record']) .OR. &
        .NOT.above_ground_encoding_ok(ncid,above_ground_id)) RETURN
    IF (.NOT.variable_layout_is(ncid,obs_support_id,NF90_INT, &
        [CHARACTER(LEN=16) :: 'x','y','z','record']) .OR. &
        .NOT.variable_unit_is(ncid,obs_support_id,'1') .OR. &
        .NOT.support_encoding_ok(ncid,obs_support_id)) RETURN
    IF (.NOT.variable_layout_is(ncid,hydro_support_id,NF90_INT, &
        [CHARACTER(LEN=16) :: 'x','y','z','record']) .OR. &
        .NOT.variable_unit_is(ncid,hydro_support_id,'1') .OR. &
        .NOT.support_encoding_ok(ncid,hydro_support_id)) RETURN
    IF (.NOT.variable_layout_is(ncid,beta_id,NF90_FLOAT, &
        [CHARACTER(LEN=16) :: 'x','y','z','record']) .OR. .NOT.variable_unit_is(ncid,beta_id,'1')) RETURN
    ! Keep these arguments in the interface so a future implementation can
    ! bind dimensions by ID; the named layout checks above are authoritative.
    IF (xdim<1 .OR. ydim<1 .OR. zdim<2 .OR. interface_dim/=zdim+1 .OR. &
        spacing_dim/=MAX(1,zdim-1) .OR. record_dim/=1) RETURN
    scalar_metadata_ok=.TRUE.
  END FUNCTION scalar_metadata_ok

  LOGICAL FUNCTION read_all_fields(ncid,payload,f3,f2,fi)
    INTEGER, INTENT(IN) :: ncid
    TYPE(cloud_bal_stage_payload_type), INTENT(INOUT) :: payload
    TYPE(field3d_ids), INTENT(OUT) :: f3(19)
    TYPE(field2d_ids), INTENT(OUT) :: f2(7)
    TYPE(integer3d_ids), INTENT(OUT) :: fi(3)
    read_all_fields=.FALSE.
    IF (.NOT.read_field3d(ncid,'pressure',f3(1),payload%state%pressure)) RETURN
    IF (.NOT.read_field3d(ncid,'temperature',f3(2),payload%state%temperature)) RETURN
    IF (.NOT.read_field3d(ncid,'vapor',f3(3),payload%state%vapor)) RETURN
    IF (.NOT.read_field3d(ncid,'u',f3(4),payload%state%u)) RETURN
    IF (.NOT.read_field3d(ncid,'v',f3(5),payload%state%v)) RETURN
    IF (.NOT.read_field3d(ncid,'omega',f3(6),payload%state%omega)) RETURN
    IF (.NOT.read_field3d(ncid,'omega_target',f3(7),payload%state%omega_target)) RETURN
    IF (.NOT.read_field3d(ncid,'omega_target_sigma',f3(8),payload%state%omega_target_sigma)) RETURN
    IF (.NOT.read_field3d(ncid,'geopotential',f3(9),payload%state%geopotential)) RETURN
    IF (.NOT.read_field3d(ncid,'cloud_fraction',f3(10),payload%state%cloud_fraction)) RETURN
    IF (.NOT.read_field3d(ncid,'radar_reflectivity',f3(11),payload%state%radar_reflectivity)) RETURN
    IF (.NOT.read_field3d(ncid,'cloud_water',f3(12),payload%state%cloud_water)) RETURN
    IF (.NOT.read_field3d(ncid,'cloud_ice',f3(13),payload%state%cloud_ice)) RETURN
    IF (.NOT.read_field3d(ncid,'rain',f3(14),payload%state%rain)) RETURN
    IF (.NOT.read_field3d(ncid,'snow',f3(15),payload%state%snow)) RETURN
    IF (.NOT.read_field3d(ncid,'graupel',f3(16),payload%state%graupel)) RETURN
    IF (.NOT.read_field3d(ncid,'vt_z_mean',f3(17),payload%state%vt_z_mean)) RETURN
    IF (.NOT.read_field3d(ncid,'vt_z_sigma',f3(18),payload%state%vt_z_sigma)) RETURN
    IF (.NOT.read_field3d(ncid,'cloud_omega_evidence',f3(19),payload%cloud_omega_evidence)) RETURN
    IF (.NOT.read_field2d(ncid,'surface_pressure',f2(1),payload%state%surface_pressure)) RETURN
    IF (.NOT.read_field2d(ncid,'surface_temperature',f2(2),payload%state%surface_temperature)) RETURN
    IF (.NOT.read_field2d(ncid,'surface_vapor',f2(3),payload%state%surface_vapor)) RETURN
    IF (.NOT.read_field2d(ncid,'surface_height',f2(4),payload%state%surface_height)) RETURN
    IF (.NOT.read_field2d(ncid,'latitude',f2(5),payload%state%latitude)) RETURN
    IF (.NOT.read_field2d(ncid,'omega_top_boundary',f2(6),payload%state%omega_top_boundary)) RETURN
    IF (.NOT.read_field2d(ncid,'omega_bottom_boundary',f2(7),payload%state%omega_bottom_boundary)) RETURN
    IF (.NOT.read_integer3d(ncid,'cloud_type',fi(1),payload%state%cloud_type)) RETURN
    IF (.NOT.read_integer3d(ncid,'precipitation_phase',fi(2),payload%state%precipitation_phase)) RETURN
    IF (.NOT.read_integer3d(ncid,'lightning_support',fi(3),payload%state%lightning_support)) RETURN
    read_all_fields=.TRUE.
  END FUNCTION read_all_fields

  LOGICAL FUNCTION read_field3d(ncid,name,ids,field)
    INTEGER, INTENT(IN) :: ncid
    CHARACTER(LEN=*), INTENT(IN) :: name
    TYPE(field3d_ids), INTENT(OUT) :: ids
    TYPE(field3d), INTENT(INOUT) :: field
    INTEGER(int32), ALLOCATABLE :: valid(:,:,:),quality(:,:,:),source(:,:,:)
    REAL(real32), ALLOCATABLE :: value(:,:,:,:)
    INTEGER :: nx,ny,nz
    read_field3d=.FALSE.
    IF (.NOT.inq_field3d(ncid,name,ids)) RETURN
    IF (.NOT.field_layout_ok(ncid,ids%value_id,NF90_FLOAT,4)) RETURN
    IF (.NOT.field_layout_ok(ncid,ids%valid_id,NF90_INT,4)) RETURN
    IF (.NOT.field_layout_ok(ncid,ids%quality_id,NF90_INT,4)) RETURN
    IF (.NOT.field_layout_ok(ncid,ids%source_id,NF90_INT,4)) RETURN
    IF (.NOT.field_attrs_ok(ncid,ids%value_id,field%unit,field%valid_time)) RETURN
    IF (.NOT.mask_encoding_ok(ncid,ids%valid_id)) RETURN
    IF (.NOT.bitmask_encoding_ok(ncid,ids%quality_id,'canonical_quality_bits_v1')) RETURN
    IF (.NOT.bitmask_encoding_ok(ncid,ids%source_id,'canonical_source_bits_v1')) RETURN
    nx=SIZE(field%value,1); ny=SIZE(field%value,2); nz=SIZE(field%value,3)
    ALLOCATE(value(nx,ny,nz,1),valid(nx,ny,nz),quality(nx,ny,nz),source(nx,ny,nz))
    IF (.NOT.nc_ok(nf90_get_var(ncid,ids%value_id,value))) RETURN
    IF (.NOT.nc_ok(get_i32_3d_record(ncid,ids%valid_id,valid))) RETURN
    IF (.NOT.nc_ok(get_i32_3d_record(ncid,ids%quality_id,quality))) RETURN
    IF (.NOT.nc_ok(get_i32_3d_record(ncid,ids%source_id,source))) RETURN
    IF (ANY(valid<0_int32) .OR. ANY(valid>1_int32)) RETURN
    field%value=value(:,:,:,1)
    field%valid=valid==1_int32
    field%quality=quality
    field%source=source
    read_field3d=.TRUE.
  END FUNCTION read_field3d

  LOGICAL FUNCTION read_field2d(ncid,name,ids,field)
    INTEGER, INTENT(IN) :: ncid
    CHARACTER(LEN=*), INTENT(IN) :: name
    TYPE(field2d_ids), INTENT(OUT) :: ids
    TYPE(field2d), INTENT(INOUT) :: field
    INTEGER(int32), ALLOCATABLE :: valid(:,:),quality(:,:),source(:,:)
    REAL(real32), ALLOCATABLE :: value(:,:,:)
    INTEGER :: nx,ny
    read_field2d=.FALSE.
    IF (.NOT.inq_field2d(ncid,name,ids)) RETURN
    IF (.NOT.field_layout_ok(ncid,ids%value_id,NF90_FLOAT,3)) RETURN
    IF (.NOT.field_layout_ok(ncid,ids%valid_id,NF90_INT,3)) RETURN
    IF (.NOT.field_layout_ok(ncid,ids%quality_id,NF90_INT,3)) RETURN
    IF (.NOT.field_layout_ok(ncid,ids%source_id,NF90_INT,3)) RETURN
    IF (.NOT.field_attrs_ok(ncid,ids%value_id,field%unit,field%valid_time)) RETURN
    IF (.NOT.mask_encoding_ok(ncid,ids%valid_id)) RETURN
    IF (.NOT.bitmask_encoding_ok(ncid,ids%quality_id,'canonical_quality_bits_v1')) RETURN
    IF (.NOT.bitmask_encoding_ok(ncid,ids%source_id,'canonical_source_bits_v1')) RETURN
    nx=SIZE(field%value,1); ny=SIZE(field%value,2)
    ALLOCATE(value(nx,ny,1),valid(nx,ny),quality(nx,ny),source(nx,ny))
    IF (.NOT.nc_ok(nf90_get_var(ncid,ids%value_id,value))) RETURN
    IF (.NOT.nc_ok(get_i32_2d_record(ncid,ids%valid_id,valid))) RETURN
    IF (.NOT.nc_ok(get_i32_2d_record(ncid,ids%quality_id,quality))) RETURN
    IF (.NOT.nc_ok(get_i32_2d_record(ncid,ids%source_id,source))) RETURN
    IF (ANY(valid<0_int32) .OR. ANY(valid>1_int32)) RETURN
    field%value=value(:,:,1)
    field%valid=valid==1_int32
    field%quality=quality
    field%source=source
    read_field2d=.TRUE.
  END FUNCTION read_field2d

  LOGICAL FUNCTION read_integer3d(ncid,name,ids,field)
    INTEGER, INTENT(IN) :: ncid
    CHARACTER(LEN=*), INTENT(IN) :: name
    TYPE(integer3d_ids), INTENT(OUT) :: ids
    TYPE(integer_field3d), INTENT(INOUT) :: field
    INTEGER(int32), ALLOCATABLE :: value(:,:,:),valid(:,:,:),quality(:,:,:),source(:,:,:)
    CHARACTER(LEN=64) :: code_table
    INTEGER(int64) :: valid_time
    INTEGER :: nx,ny,nz
    read_integer3d=.FALSE.
    IF (.NOT.inq_integer3d(ncid,name,ids)) RETURN
    IF (.NOT.field_layout_ok(ncid,ids%value_id,NF90_INT,4)) RETURN
    IF (.NOT.field_layout_ok(ncid,ids%valid_id,NF90_INT,4)) RETURN
    IF (.NOT.field_layout_ok(ncid,ids%quality_id,NF90_INT,4)) RETURN
    IF (.NOT.field_layout_ok(ncid,ids%source_id,NF90_INT,4)) RETURN
    IF (.NOT.get_var_string(ncid,ids%value_id,'code_table',code_table)) RETURN
    IF (TRIM(code_table)/=TRIM(field%code_table)) RETURN
    IF (.NOT.get_var_i64(ncid,ids%value_id,'valid_time',valid_time)) RETURN
    IF (valid_time/=field%valid_time) RETURN
    IF (.NOT.mask_encoding_ok(ncid,ids%valid_id)) RETURN
    IF (.NOT.bitmask_encoding_ok(ncid,ids%quality_id,'canonical_quality_bits_v1')) RETURN
    IF (.NOT.bitmask_encoding_ok(ncid,ids%source_id,'canonical_source_bits_v1')) RETURN
    nx=SIZE(field%value,1); ny=SIZE(field%value,2); nz=SIZE(field%value,3)
    ALLOCATE(value(nx,ny,nz),valid(nx,ny,nz),quality(nx,ny,nz),source(nx,ny,nz))
    IF (.NOT.nc_ok(get_i32_3d_record(ncid,ids%value_id,value))) RETURN
    IF (.NOT.nc_ok(get_i32_3d_record(ncid,ids%valid_id,valid))) RETURN
    IF (.NOT.nc_ok(get_i32_3d_record(ncid,ids%quality_id,quality))) RETURN
    IF (.NOT.nc_ok(get_i32_3d_record(ncid,ids%source_id,source))) RETURN
    IF (ANY(valid<0_int32) .OR. ANY(valid>1_int32)) RETURN
    field%value=value
    field%valid=valid==1_int32
    field%quality=quality
    field%source=source
    read_integer3d=.TRUE.
  END FUNCTION read_integer3d

  LOGICAL FUNCTION inq_field3d(ncid,name,ids)
    INTEGER, INTENT(IN) :: ncid
    CHARACTER(LEN=*), INTENT(IN) :: name
    TYPE(field3d_ids), INTENT(OUT) :: ids
    inq_field3d=nc_ok(nf90_inq_varid(ncid,TRIM(name),ids%value_id)) .AND. &
      nc_ok(nf90_inq_varid(ncid,TRIM(name)//'_valid',ids%valid_id)) .AND. &
      nc_ok(nf90_inq_varid(ncid,TRIM(name)//'_quality',ids%quality_id)) .AND. &
      nc_ok(nf90_inq_varid(ncid,TRIM(name)//'_source',ids%source_id))
  END FUNCTION inq_field3d

  LOGICAL FUNCTION inq_field2d(ncid,name,ids)
    INTEGER, INTENT(IN) :: ncid
    CHARACTER(LEN=*), INTENT(IN) :: name
    TYPE(field2d_ids), INTENT(OUT) :: ids
    inq_field2d=nc_ok(nf90_inq_varid(ncid,TRIM(name),ids%value_id)) .AND. &
      nc_ok(nf90_inq_varid(ncid,TRIM(name)//'_valid',ids%valid_id)) .AND. &
      nc_ok(nf90_inq_varid(ncid,TRIM(name)//'_quality',ids%quality_id)) .AND. &
      nc_ok(nf90_inq_varid(ncid,TRIM(name)//'_source',ids%source_id))
  END FUNCTION inq_field2d

  LOGICAL FUNCTION inq_integer3d(ncid,name,ids)
    INTEGER, INTENT(IN) :: ncid
    CHARACTER(LEN=*), INTENT(IN) :: name
    TYPE(integer3d_ids), INTENT(OUT) :: ids
    inq_integer3d=nc_ok(nf90_inq_varid(ncid,TRIM(name),ids%value_id)) .AND. &
      nc_ok(nf90_inq_varid(ncid,TRIM(name)//'_valid',ids%valid_id)) .AND. &
      nc_ok(nf90_inq_varid(ncid,TRIM(name)//'_quality',ids%quality_id)) .AND. &
      nc_ok(nf90_inq_varid(ncid,TRIM(name)//'_source',ids%source_id))
  END FUNCTION inq_integer3d

  LOGICAL FUNCTION field_layout_ok(ncid,varid,expected_type,expected_rank)
    INTEGER, INTENT(IN) :: ncid,varid,expected_type,expected_rank
    INTEGER :: ndims,xtype,dimids(NF90_MAX_VAR_DIMS),k
    CHARACTER(LEN=NF90_MAX_NAME) :: dim_name
    CHARACTER(LEN=16) :: expected(4)
    field_layout_ok=.FALSE.
    IF (expected_rank==3) THEN
      expected=(/'x               ','y               ','record          ','                '/)
    ELSE
      expected=(/'x               ','y               ','z               ','record          '/)
    END IF
    IF (.NOT.nc_ok(nf90_inquire_variable(ncid,varid,XTYPE=xtype,NDIMS=ndims,DIMIDS=dimids))) RETURN
    IF (xtype/=expected_type .OR. ndims/=expected_rank) THEN
      RETURN
    END IF
    DO k=1,expected_rank
      dim_name=''
      IF (.NOT.nc_ok(nf90_inquire_dimension(ncid,dimids(k),NAME=dim_name))) RETURN
      IF (TRIM(dim_name)/=TRIM(expected(k))) THEN
        RETURN
      END IF
    END DO
    field_layout_ok=.TRUE.
  END FUNCTION field_layout_ok

  LOGICAL FUNCTION variable_layout_is(ncid,varid,expected_type,dimension_names)
    INTEGER, INTENT(IN) :: ncid,varid,expected_type
    CHARACTER(LEN=*), INTENT(IN) :: dimension_names(:)
    INTEGER :: ndims,xtype,dimids(NF90_MAX_VAR_DIMS),k
    CHARACTER(LEN=NF90_MAX_NAME) :: dim_name
    variable_layout_is=.FALSE.
    IF (.NOT.nc_ok(nf90_inquire_variable(ncid,varid,XTYPE=xtype,NDIMS=ndims,DIMIDS=dimids))) RETURN
    IF (xtype/=expected_type .OR. ndims/=SIZE(dimension_names)) THEN
      RETURN
    END IF
    DO k=1,ndims
      dim_name=''
      IF (.NOT.nc_ok(nf90_inquire_dimension(ncid,dimids(k),NAME=dim_name))) RETURN
      IF (TRIM(dim_name)/=TRIM(dimension_names(k))) THEN
        RETURN
      END IF
    END DO
    variable_layout_is=.TRUE.
  END FUNCTION variable_layout_is

  LOGICAL FUNCTION field_attrs_ok(ncid,varid,unit,valid_time)
    INTEGER, INTENT(IN) :: ncid,varid
    CHARACTER(LEN=*), INTENT(IN) :: unit
    INTEGER(int64), INTENT(IN) :: valid_time
    CHARACTER(LEN=256) :: actual_unit
    INTEGER(int64) :: actual_time
    field_attrs_ok=.FALSE.
    IF (.NOT.get_var_string(ncid,varid,'units',actual_unit)) RETURN
    IF (TRIM(actual_unit)/=TRIM(unit)) RETURN
    IF (.NOT.get_var_i64(ncid,varid,'valid_time',actual_time)) RETURN
    IF (actual_time/=valid_time) RETURN
    field_attrs_ok=.TRUE.
  END FUNCTION field_attrs_ok

  LOGICAL FUNCTION variable_unit_is(ncid,varid,expected)
    INTEGER, INTENT(IN) :: ncid,varid
    CHARACTER(LEN=*), INTENT(IN) :: expected
    CHARACTER(LEN=256) :: actual
    variable_unit_is=.FALSE.
    IF (.NOT.get_var_string(ncid,varid,'units',actual)) RETURN
    variable_unit_is=TRIM(actual)==TRIM(expected)
  END FUNCTION variable_unit_is

  LOGICAL FUNCTION mask_encoding_ok(ncid,varid)
    INTEGER, INTENT(IN) :: ncid,varid
    CHARACTER(LEN=256) :: encoding
    mask_encoding_ok=.FALSE.
    IF (.NOT.get_var_string(ncid,varid,'mask_encoding',encoding)) RETURN
    mask_encoding_ok=TRIM(encoding)=='0=invalid,1=valid'
  END FUNCTION mask_encoding_ok

  LOGICAL FUNCTION above_ground_encoding_ok(ncid,varid)
    INTEGER, INTENT(IN) :: ncid,varid
    CHARACTER(LEN=256) :: encoding
    above_ground_encoding_ok=.FALSE.
    IF (.NOT.get_var_string(ncid,varid,'mask_encoding',encoding)) RETURN
    above_ground_encoding_ok=TRIM(encoding)=='0=below_ground,1=above_ground'
  END FUNCTION above_ground_encoding_ok

  LOGICAL FUNCTION bitmask_encoding_ok(ncid,varid,expected)
    INTEGER, INTENT(IN) :: ncid,varid
    CHARACTER(LEN=*), INTENT(IN) :: expected
    CHARACTER(LEN=256) :: encoding
    bitmask_encoding_ok=.FALSE.
    IF (.NOT.get_var_string(ncid,varid,'mask_encoding',encoding)) RETURN
    bitmask_encoding_ok=TRIM(encoding)==TRIM(expected)
  END FUNCTION bitmask_encoding_ok

  LOGICAL FUNCTION support_encoding_ok(ncid,varid)
    INTEGER, INTENT(IN) :: ncid,varid
    CHARACTER(LEN=256) :: encoding
    support_encoding_ok=.FALSE.
    IF (.NOT.get_var_string(ncid,varid,'support_encoding',encoding)) RETURN
    support_encoding_ok=TRIM(encoding)=='canonical_source_bits'
  END FUNCTION support_encoding_ok

  INTEGER FUNCTION get_i32_3d_record(ncid,varid,values)
    INTEGER, INTENT(IN) :: ncid,varid
    INTEGER(int32), INTENT(OUT) :: values(:,:,:)
    INTEGER(int32), ALLOCATABLE :: flat(:)
    INTEGER :: nx,ny,nz,k
    nx=SIZE(values,1); ny=SIZE(values,2); nz=SIZE(values,3)
    ALLOCATE(flat(nx*ny))
    get_i32_3d_record=NF90_NOERR
    DO k=1,nz
      get_i32_3d_record=nf90_get_var(ncid,varid,flat, &
        start=(/1,1,k,1/),count=(/nx,ny,1,1/))
      IF (get_i32_3d_record/=NF90_NOERR) RETURN
      values(:,:,k)=RESHAPE(flat,(/nx,ny/))
    END DO
  END FUNCTION get_i32_3d_record

  INTEGER FUNCTION get_i32_2d_record(ncid,varid,values)
    INTEGER, INTENT(IN) :: ncid,varid
    INTEGER(int32), INTENT(OUT) :: values(:,:)
    INTEGER(int32), ALLOCATABLE :: flat(:)
    INTEGER :: nx,ny
    nx=SIZE(values,1); ny=SIZE(values,2)
    ALLOCATE(flat(nx*ny))
    get_i32_2d_record=nf90_get_var(ncid,varid,flat, &
      start=(/1,1,1/),count=(/nx,ny,1/))
    IF (get_i32_2d_record==NF90_NOERR) values=RESHAPE(flat,(/nx,ny/))
  END FUNCTION get_i32_2d_record

  INTEGER FUNCTION get_mask3d(ncid,varid,mask)
    INTEGER, INTENT(IN) :: ncid,varid
    LOGICAL, INTENT(OUT) :: mask(:,:,:)
    INTEGER(int32), ALLOCATABLE :: tmp(:,:,:)
    ALLOCATE(tmp(SIZE(mask,1),SIZE(mask,2),SIZE(mask,3)))
    get_mask3d=get_i32_3d_record(ncid,varid,tmp)
    IF (get_mask3d/=NF90_NOERR) RETURN
    IF (ANY(tmp<0_int32) .OR. ANY(tmp>1_int32)) THEN
      get_mask3d=NF90_EBADTYPE
      RETURN
    END IF
    mask=tmp==1_int32
  END FUNCTION get_mask3d

  INTEGER FUNCTION get_record_i32(ncid,varid,values)
    INTEGER, INTENT(IN) :: ncid,varid
    INTEGER(int32), INTENT(OUT) :: values(:,:,:)
    get_record_i32=get_i32_3d_record(ncid,varid,values)
  END FUNCTION get_record_i32

  INTEGER FUNCTION get_record_real32(ncid,varid,values)
    INTEGER, INTENT(IN) :: ncid,varid
    REAL(real32), INTENT(OUT) :: values(:,:,:)
    REAL(real32), ALLOCATABLE :: tmp(:,:,:,:)
    ALLOCATE(tmp(SIZE(values,1),SIZE(values,2),SIZE(values,3),1))
    get_record_real32=nf90_get_var(ncid,varid,tmp)
    IF (get_record_real32==NF90_NOERR) values=tmp(:,:,:,1)
  END FUNCTION get_record_real32

  LOGICAL FUNCTION put_global_identity(ncid,identity,nx,ny,nz)
    INTEGER, INTENT(IN) :: ncid,nx,ny,nz
    TYPE(stage_payload_identity), INTENT(IN) :: identity
    INTEGER(int32) :: dynamic_authorized,radar_present
    dynamic_authorized=MERGE(1_int32,0_int32,identity%dynamic_target_authorized)
    radar_present=0_int32
    put_global_identity=nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'cloud_bal_exchange_version', &
        identity%exchange_version))
    IF (.NOT.put_global_identity) RETURN
    put_global_identity=nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'cloud_bal_schema_version',identity%schema_version))
    IF (.NOT.put_global_identity) RETURN
    put_global_identity=nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'stage',TRIM(identity%stage)))
    IF (.NOT.put_global_identity) RETURN
    put_global_identity=nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'generation_id',TRIM(identity%generation_id)))
    IF (.NOT.put_global_identity) RETURN
    put_global_identity=nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'valid_time',identity%valid_time))
    IF (.NOT.put_global_identity) RETURN
    put_global_identity=nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'reference_time',identity%reference_time))
    IF (.NOT.put_global_identity) RETURN
    put_global_identity=nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'grid_id',TRIM(identity%grid_id)))
    IF (.NOT.put_global_identity) RETURN
    put_global_identity=nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'canonical_vertical_order',TRIM(identity%vertical_order)))
    IF (.NOT.put_global_identity) RETURN
    put_global_identity=nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'wind_coordinate',TRIM(identity%wind_coordinate)))
    IF (.NOT.put_global_identity) RETURN
    put_global_identity=nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'producer_source_sha256',TRIM(identity%producer_source_sha256)))
    IF (.NOT.put_global_identity) RETURN
    put_global_identity=nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'producer_binary_sha256',TRIM(identity%producer_binary_sha256)))
    IF (.NOT.put_global_identity) RETURN
    put_global_identity=nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'configuration_sha256',TRIM(identity%configuration_sha256)))
    IF (.NOT.put_global_identity) RETURN
    put_global_identity=nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'input_manifest_sha256',TRIM(identity%input_manifest_sha256)))
    IF (.NOT.put_global_identity) RETURN
    put_global_identity=nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'dynamic_target_authorized',dynamic_authorized))
    IF (.NOT.put_global_identity) RETURN
    put_global_identity=nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'radar_los_present',radar_present))
    IF (.NOT.put_global_identity) RETURN
    put_global_identity=nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'netcdf_variable_order','record,z,y,x'))
    IF (.NOT.put_global_identity) RETURN
    put_global_identity=nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'longitude_units','degree_east'))
    IF (.NOT.put_global_identity) RETURN
    put_global_identity=nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'canonical_nx',nx))
    IF (.NOT.put_global_identity) RETURN
    put_global_identity=nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'canonical_ny',ny))
    IF (.NOT.put_global_identity) RETURN
    put_global_identity=nc_ok(nf90_put_att(ncid,NF90_GLOBAL,'canonical_nz',nz))
    ! The four SHA-256 values are lineage claims copied from the coordinator's
    ! detached manifest.  This Fortran exchange layer deliberately does not
    ! claim to hash or authenticate the bytes it writes.
  END FUNCTION put_global_identity

  LOGICAL FUNCTION read_global_identity(ncid,identity)
    INTEGER, INTENT(IN) :: ncid
    TYPE(stage_payload_identity), INTENT(OUT) :: identity
    INTEGER(int32) :: dynamic_authorized
    read_global_identity=.FALSE.
    IF (.NOT.get_att_i32(ncid,'cloud_bal_exchange_version',identity%exchange_version)) RETURN
    IF (.NOT.get_att_i32(ncid,'cloud_bal_schema_version',identity%schema_version)) RETURN
    IF (.NOT.get_att_string(ncid,'stage',identity%stage)) RETURN
    IF (.NOT.get_att_string(ncid,'generation_id',identity%generation_id)) RETURN
    IF (.NOT.get_att_i64(ncid,'valid_time',identity%valid_time)) RETURN
    IF (.NOT.get_att_i64(ncid,'reference_time',identity%reference_time)) RETURN
    IF (.NOT.get_att_string(ncid,'grid_id',identity%grid_id)) RETURN
    IF (.NOT.get_att_string(ncid,'canonical_vertical_order',identity%vertical_order)) RETURN
    IF (.NOT.get_att_string(ncid,'wind_coordinate',identity%wind_coordinate)) RETURN
    IF (.NOT.get_att_string(ncid,'producer_source_sha256',identity%producer_source_sha256)) RETURN
    IF (.NOT.get_att_string(ncid,'producer_binary_sha256',identity%producer_binary_sha256)) RETURN
    IF (.NOT.get_att_string(ncid,'configuration_sha256',identity%configuration_sha256)) RETURN
    IF (.NOT.get_att_string(ncid,'input_manifest_sha256',identity%input_manifest_sha256)) RETURN
    IF (.NOT.get_att_i32(ncid,'dynamic_target_authorized',dynamic_authorized)) RETURN
    IF (dynamic_authorized<0_int32 .OR. dynamic_authorized>1_int32) RETURN
    identity%dynamic_target_authorized=dynamic_authorized==1_int32
    read_global_identity=.TRUE.
  END FUNCTION read_global_identity

  LOGICAL FUNCTION read_radar_presence(ncid)
    INTEGER, INTENT(IN) :: ncid
    INTEGER(int32) :: present
    read_radar_presence=.FALSE.
    IF (.NOT.get_att_i32(ncid,'radar_los_present',present)) RETURN
    read_radar_presence=present==0_int32
  END FUNCTION read_radar_presence

  LOGICAL FUNCTION global_contract_ok(ncid)
    INTEGER, INTENT(IN) :: ncid
    CHARACTER(LEN=256) :: order,longitude_units
    global_contract_ok=.FALSE.
    IF (.NOT.get_att_string(ncid,'netcdf_variable_order',order)) RETURN
    IF (.NOT.get_att_string(ncid,'longitude_units',longitude_units)) RETURN
    IF (TRIM(order)/='record,z,y,x' .OR. TRIM(longitude_units)/='degree_east') RETURN
    global_contract_ok=.TRUE.
  END FUNCTION global_contract_ok

  LOGICAL FUNCTION get_dim(ncid,name,length)
    INTEGER, INTENT(IN) :: ncid
    CHARACTER(LEN=*), INTENT(IN) :: name
    INTEGER, INTENT(OUT) :: length
    INTEGER :: dimid
    get_dim=.FALSE.; length=0
    IF (.NOT.nc_ok(nf90_inq_dimid(ncid,TRIM(name),dimid))) RETURN
    IF (.NOT.nc_ok(nf90_inquire_dimension(ncid,dimid,LEN=length))) RETURN
    get_dim=.TRUE.
  END FUNCTION get_dim

  LOGICAL FUNCTION get_att_string(ncid,name,value)
    INTEGER, INTENT(IN) :: ncid
    CHARACTER(LEN=*), INTENT(IN) :: name
    CHARACTER(LEN=*), INTENT(OUT) :: value
    value=''
    get_att_string=nc_ok(nf90_get_att(ncid,NF90_GLOBAL,TRIM(name),value))
  END FUNCTION get_att_string

  LOGICAL FUNCTION get_att_i32(ncid,name,value)
    INTEGER, INTENT(IN) :: ncid
    CHARACTER(LEN=*), INTENT(IN) :: name
    INTEGER(int32), INTENT(OUT) :: value
    value=0_int32
    get_att_i32=nc_ok(nf90_get_att(ncid,NF90_GLOBAL,TRIM(name),value))
  END FUNCTION get_att_i32

  LOGICAL FUNCTION get_att_i64(ncid,name,value)
    INTEGER, INTENT(IN) :: ncid
    CHARACTER(LEN=*), INTENT(IN) :: name
    INTEGER(int64), INTENT(OUT) :: value
    value=0_int64
    get_att_i64=nc_ok(nf90_get_att(ncid,NF90_GLOBAL,TRIM(name),value))
  END FUNCTION get_att_i64

  LOGICAL FUNCTION get_var_string(ncid,varid,name,value)
    INTEGER, INTENT(IN) :: ncid,varid
    CHARACTER(LEN=*), INTENT(IN) :: name
    CHARACTER(LEN=*), INTENT(OUT) :: value
    value=''
    get_var_string=nc_ok(nf90_get_att(ncid,varid,TRIM(name),value))
  END FUNCTION get_var_string

  LOGICAL FUNCTION get_var_i64(ncid,varid,name,value)
    INTEGER, INTENT(IN) :: ncid,varid
    CHARACTER(LEN=*), INTENT(IN) :: name
    INTEGER(int64), INTENT(OUT) :: value
    value=0_int64
    get_var_i64=nc_ok(nf90_get_att(ncid,varid,TRIM(name),value))
  END FUNCTION get_var_i64

  SUBROUTINE delete_file_if_created(path,created)
    CHARACTER(LEN=*), INTENT(IN) :: path
    LOGICAL, INTENT(IN) :: created
    INTEGER :: unit,ios
    IF (.NOT.created) RETURN
    OPEN(NEWUNIT=unit,FILE=TRIM(path),STATUS='OLD',ACTION='WRITE',IOSTAT=ios)
    IF (ios/=0) RETURN
    CLOSE(unit,STATUS='DELETE',IOSTAT=ios)
  END SUBROUTINE delete_file_if_created

END MODULE cloud_bal_stage_payload
