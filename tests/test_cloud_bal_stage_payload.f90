PROGRAM test_cloud_bal_stage_payload
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32,int64
  USE netcdf
  USE cloud_bal_state, ONLY: cloud_bal_state_type,field3d,field2d,integer_field3d, &
    initialize_cloud_bal_state,initialize_field,configure_pressure_geometry, &
    refresh_dry_air_mass_measure,canonical_states_equal,STATUS_FAILED,STATUS_OK, &
    REASON_METADATA,REASON_NONE,REASON_RADAR_CONTRACT,SOURCE_BACKGROUND_MODEL,SOURCE_CLOUD_ANALYSIS, &
    QUALITY_RAW_MISSING
  USE cloud_bal_stage_payload, ONLY: cloud_bal_stage_payload_type,stage_payload_identity, &
    write_cloud_bal_stage_payload,read_cloud_bal_stage_payload, &
    CLOUD_BAL_PAYLOAD_EXCHANGE_VERSION
  IMPLICIT NONE
  INTEGER, PARAMETER :: nx=3,ny=2,nz=3
  INTEGER(int64), PARAMETER :: valid_time=1788224400_int64
  CHARACTER(LEN=512) :: path
  TYPE(cloud_bal_stage_payload_type) :: sent,received
  TYPE(cloud_bal_state_type) :: state
  TYPE(stage_payload_identity) :: expected
  INTEGER :: status,reason

  CALL get_command_argument(1,path)
  IF (LEN_TRIM(path)==0) ERROR STOP 'payload path is required'
  CALL make_fixture(state,sent%longitude,sent%cloud_omega_evidence,expected,status)
  IF (status/=STATUS_OK) ERROR STOP 'fixture construction failed'
  sent%state=state
  sent%identity=expected
  CALL write_cloud_bal_stage_payload(TRIM(path),sent,status,reason)
  CALL assert_true(status==STATUS_OK .AND. reason==REASON_NONE,'write accepted fixture')
  CALL assert_mask_metadata(TRIM(path),status)
  CALL assert_true(status==STATUS_OK,'valid and bitmask metadata are distinct')
  CALL read_cloud_bal_stage_payload(TRIM(path),expected,received,status,reason)
  CALL assert_true(status==STATUS_OK .AND. reason==REASON_NONE,'read accepted fixture')
  CALL assert_true(canonical_states_equal(state,received%state),'canonical state exact round-trip')
  CALL assert_true(ALL(sent%longitude==received%longitude),'longitude exact round-trip')
  CALL assert_true(ALL(sent%cloud_omega_evidence%value==received%cloud_omega_evidence%value) .AND. &
                   ALL(sent%cloud_omega_evidence%valid .EQV. received%cloud_omega_evidence%valid) .AND. &
                   ALL(sent%cloud_omega_evidence%quality==received%cloud_omega_evidence%quality) .AND. &
                   ALL(sent%cloud_omega_evidence%source==received%cloud_omega_evidence%source), &
                   'COM evidence exact round-trip')
  CALL assert_true(ALL(.NOT.received%state%omega_target%valid) .AND. &
                   ALL(received%state%omega_target%value==-1234.5_real32) .AND. &
                   ALL(.NOT.received%state%omega_target_sigma%valid) .AND. &
                   ALL(received%state%omega_target_sigma%value==-5678.5_real32), &
                   'invalid target values and masks remain opaque')
  CALL assert_true(.NOT.received%state%above_ground(1,1,1) .AND. &
                   .NOT.received%state%temperature%valid(1,1,1) .AND. &
                   received%state%temperature%value(1,1,1)==-777.25_real32 .AND. &
                   IAND(received%state%temperature%quality(1,1,1),QUALITY_RAW_MISSING)/=0_int32, &
                   'below-ground missing value and mask remain exact')

  expected%valid_time=expected%valid_time+60_int64
  CALL read_cloud_bal_stage_payload(TRIM(path),expected,received,status,reason)
  CALL assert_true(status==STATUS_FAILED .AND. reason==REASON_METADATA,'stale time rejected')
  expected%valid_time=valid_time
  expected%grid_id='wrong-grid'
  CALL read_cloud_bal_stage_payload(TRIM(path),expected,received,status,reason)
  CALL assert_true(status==STATUS_FAILED .AND. reason==REASON_METADATA,'wrong grid rejected')
  expected=sent%identity
  expected%vertical_order='top_to_bottom'
  CALL read_cloud_bal_stage_payload(TRIM(path),expected,received,status,reason)
  CALL assert_true(status==STATUS_FAILED .AND. reason==REASON_METADATA,'wrong vertical order rejected')
  expected=sent%identity
  expected%wind_coordinate='EARTH_RELATIVE'
  CALL read_cloud_bal_stage_payload(TRIM(path),expected,received,status,reason)
  CALL assert_true(status==STATUS_FAILED .AND. reason==REASON_METADATA,'wrong wind frame rejected')
  expected=sent%identity
  expected%exchange_version=CLOUD_BAL_PAYLOAD_EXCHANGE_VERSION+1_int32
  CALL read_cloud_bal_stage_payload(TRIM(path),expected,received,status,reason)
  CALL assert_true(status==STATUS_FAILED .AND. reason==REASON_METADATA,'wrong exchange version rejected')
  expected=sent%identity
  expected%producer_binary_sha256(1:1)='0'
  CALL read_cloud_bal_stage_payload(TRIM(path),expected,received,status,reason)
  CALL assert_true(status==STATUS_FAILED .AND. reason==REASON_METADATA,'wrong lineage digest rejected')
  expected=sent%identity

  CALL mutate_units(TRIM(path),status)
  CALL assert_true(status==STATUS_OK,'unit mutation fixture')
  CALL read_cloud_bal_stage_payload(TRIM(path),expected,received,status,reason)
  CALL assert_true(status==STATUS_FAILED,'wrong units rejected')
  CALL remove_file(TRIM(path))
  CALL write_cloud_bal_stage_payload(TRIM(path),sent,status,reason)
  CALL assert_true(status==STATUS_OK,'rewrite after unit case')

  CALL mutate_valid_mask(TRIM(path),status)
  CALL assert_true(status==STATUS_OK,'mask mutation fixture')
  CALL read_cloud_bal_stage_payload(TRIM(path),expected,received,status,reason)
  CALL assert_true(status==STATUS_FAILED,'non-binary valid mask rejected')
  CALL remove_file(TRIM(path))
  CALL write_cloud_bal_stage_payload(TRIM(path),sent,status,reason)
  CALL assert_true(status==STATUS_OK,'rewrite after mask case')

  CALL write_cloud_bal_stage_payload(TRIM(path),sent,status,reason)
  CALL assert_true(status==STATUS_FAILED .AND. reason==REASON_METADATA,'no-clobber enforced')
  sent%identity%dynamic_target_authorized=.TRUE.
  CALL write_cloud_bal_stage_payload(TRIM(path)//'.dynamic',sent,status,reason)
  CALL assert_true(status==STATUS_FAILED .AND. reason==REASON_METADATA,'dynamic target authority rejected')
  sent%identity=expected
  sent%state%radar_los%is_present=.TRUE.
  CALL write_cloud_bal_stage_payload(TRIM(path)//'.radar',sent,status,reason)
  CALL assert_true(status==STATUS_FAILED .AND. reason==REASON_RADAR_CONTRACT,'radar LOS omission is explicit')
  WRITE(*,'(A)') 'cloud_bal_stage_payload: PASS'

CONTAINS

  SUBROUTINE make_fixture(state,longitude,evidence,identity,status)
    TYPE(cloud_bal_state_type), INTENT(OUT) :: state
    REAL(real32), ALLOCATABLE, INTENT(OUT) :: longitude(:,:)
    TYPE(field3d), INTENT(OUT) :: evidence
    TYPE(stage_payload_identity), INTENT(OUT) :: identity
    INTEGER, INTENT(OUT) :: status
    INTEGER :: i,j,k,local_status
    CALL initialize_cloud_bal_state(state,nx,ny,nz,valid_time,'NE57-PAYLOAD',status)
    IF (status/=STATUS_OK) RETURN
    state%grid%dx=1000.0_real64; state%grid%dy=1000.0_real64
    state%pressure%value(:,:,1)=95000.0_real32
    state%pressure%value(:,:,2)=80000.0_real32
    state%pressure%value(:,:,3)=60000.0_real32
    state%pressure%valid=.TRUE.; state%pressure%quality=0_int32
    state%pressure%source=SOURCE_BACKGROUND_MODEL
    state%surface_pressure%value=100000.0_real32
    state%surface_pressure%value(1,1)=85000.0_real32
    state%surface_pressure%valid=.TRUE.; state%surface_pressure%quality=0_int32
    state%surface_pressure%source=SOURCE_BACKGROUND_MODEL
    CALL configure_pressure_geometry(state,local_status)
    IF (local_status/=STATUS_OK) THEN; status=STATUS_FAILED; RETURN; END IF

    CALL set_real3d(state%temperature,280.0_real32,state%above_ground)
    CALL set_real3d(state%vapor,0.008_real32,state%above_ground)
    CALL set_real3d(state%u,4.0_real32,state%above_ground)
    CALL set_real3d(state%v,-2.0_real32,state%above_ground)
    CALL set_real3d(state%omega,0.5_real32,state%above_ground)
    CALL set_real3d(state%geopotential,100.0_real32,state%above_ground)
    CALL set_real3d(state%cloud_fraction,0.2_real32,state%above_ground)
    CALL set_real3d(state%radar_reflectivity,12.0_real32,state%above_ground)
    CALL set_real3d(state%cloud_water,0.001_real32,state%above_ground)
    CALL set_real3d(state%cloud_ice,0.0005_real32,state%above_ground)
    CALL set_real3d(state%rain,0.0002_real32,state%above_ground)
    CALL set_real3d(state%snow,0.0001_real32,state%above_ground)
    CALL set_real3d(state%graupel,0.0001_real32,state%above_ground)
    CALL set_real3d(state%vt_z_mean,0.5_real32,state%above_ground)
    CALL set_real3d(state%vt_z_sigma,0.1_real32,state%above_ground)
    state%omega_target%value=-1234.5_real32; state%omega_target%valid=.FALSE.
    state%omega_target%quality=QUALITY_RAW_MISSING; state%omega_target%source=0_int32
    state%omega_target_sigma%value=-5678.5_real32; state%omega_target_sigma%valid=.FALSE.
    state%omega_target_sigma%quality=QUALITY_RAW_MISSING; state%omega_target_sigma%source=0_int32
    CALL set_integer3d(state%cloud_type,1_int32,state%above_ground)
    CALL set_integer3d(state%precipitation_phase,2_int32,state%above_ground)
    CALL set_integer3d(state%lightning_support,0_int32,state%above_ground)
    CALL set_real2d(state%surface_temperature,280.0_real32)
    CALL set_real2d(state%surface_vapor,0.008_real32)
    CALL set_real2d(state%surface_height,10.0_real32)
    CALL set_real2d(state%latitude,35.0_real32)
    CALL set_real2d(state%omega_top_boundary,0.0_real32)
    CALL set_real2d(state%omega_bottom_boundary,0.0_real32)
    state%obs_support=0_int32; state%hydro_support=0_int32
    state%balance_beta=MERGE(0.25_real32,0.0_real32,state%above_ground)
    CALL refresh_dry_air_mass_measure(state,local_status)
    IF (local_status/=STATUS_OK) THEN; status=STATUS_FAILED; RETURN; END IF
    ALLOCATE(longitude(nx,ny))
    DO j=1,ny; DO i=1,nx
      longitude(i,j)=-120.0_real32+REAL(i+3*j,real32)
    END DO; END DO
    CALL initialize_field(evidence,nx,ny,nz,valid_time,'Pa s-1')
    evidence%value=0.0_real32; evidence%valid=state%above_ground
    evidence%quality=MERGE(0_int32,QUALITY_RAW_MISSING,evidence%valid)
    evidence%source=MERGE(SOURCE_CLOUD_ANALYSIS,0_int32,evidence%valid)
    DO k=1,nz; DO j=1,ny; DO i=1,nx
      IF (evidence%valid(i,j,k)) evidence%value(i,j,k)=REAL(i+10*j+k,real32)
    END DO; END DO; END DO
    identity%exchange_version=CLOUD_BAL_PAYLOAD_EXCHANGE_VERSION
    identity%schema_version=state%schema_version
    identity%stage='deriv_off'
    identity%generation_id='payload-test-generation'
    identity%valid_time=valid_time; identity%reference_time=valid_time-3600_int64
    identity%grid_id=state%grid%grid_id
    identity%vertical_order='bottom_to_top'; identity%wind_coordinate='GRID_RELATIVE'
    identity%producer_source_sha256=REPEAT('a',64)
    identity%producer_binary_sha256=REPEAT('b',64)
    identity%configuration_sha256=REPEAT('c',64)
    identity%input_manifest_sha256=REPEAT('d',64)
    identity%dynamic_target_authorized=.FALSE.
    status=STATUS_OK
  END SUBROUTINE make_fixture

  SUBROUTINE set_real3d(field,base,domain)
    TYPE(field3d), INTENT(INOUT) :: field
    REAL(real32), INTENT(IN) :: base
    LOGICAL, INTENT(IN) :: domain(:,:,:)
    INTEGER :: i,j,k
    DO k=1,SIZE(domain,3); DO j=1,SIZE(domain,2); DO i=1,SIZE(domain,1)
      field%value(i,j,k)=base+REAL(i+j+k,real32)*0.01_real32
    END DO; END DO; END DO
    field%valid=domain
    field%quality=MERGE(0_int32,QUALITY_RAW_MISSING,domain)
    field%source=MERGE(SOURCE_BACKGROUND_MODEL,0_int32,domain)
    DO k=1,SIZE(domain,3); DO j=1,SIZE(domain,2); DO i=1,SIZE(domain,1)
      IF (.NOT.domain(i,j,k)) field%value(i,j,k)=-777.25_real32
    END DO; END DO; END DO
  END SUBROUTINE set_real3d

  SUBROUTINE set_integer3d(field,base,domain)
    TYPE(integer_field3d), INTENT(INOUT) :: field
    INTEGER(int32), INTENT(IN) :: base
    LOGICAL, INTENT(IN) :: domain(:,:,:)
    field%value=base; field%valid=domain
    field%quality=MERGE(0_int32,QUALITY_RAW_MISSING,domain)
    field%source=MERGE(SOURCE_BACKGROUND_MODEL,0_int32,domain)
    WHERE (.NOT.domain) field%value=-9_int32
  END SUBROUTINE set_integer3d

  SUBROUTINE set_real2d(field,base)
    TYPE(field2d), INTENT(INOUT) :: field
    REAL(real32), INTENT(IN) :: base
    field%value=base; field%valid=.TRUE.; field%quality=0_int32; field%source=SOURCE_BACKGROUND_MODEL
  END SUBROUTINE set_real2d

  SUBROUTINE mutate_units(path,status)
    CHARACTER(LEN=*), INTENT(IN) :: path
    INTEGER, INTENT(OUT) :: status
    INTEGER :: ncid,varid,rc
    status=STATUS_FAILED
    rc=nf90_open(path,NF90_WRITE,ncid); IF (rc/=NF90_NOERR) RETURN
    rc=nf90_inq_varid(ncid,'temperature',varid)
    IF (rc==NF90_NOERR) rc=nf90_put_att(ncid,varid,'units','KELVIN')
    IF (rc==NF90_NOERR) status=STATUS_OK
    rc=nf90_close(ncid)
  END SUBROUTINE mutate_units

  SUBROUTINE assert_mask_metadata(path,status)
    CHARACTER(LEN=*), INTENT(IN) :: path
    INTEGER, INTENT(OUT) :: status
    INTEGER :: ncid,valid_id,quality_id,source_id,above_id,rc
    CHARACTER(LEN=128) :: valid_encoding,quality_encoding,source_encoding,above_encoding
    status=STATUS_FAILED; valid_encoding=''; quality_encoding=''; source_encoding=''; above_encoding=''
    rc=nf90_open(path,NF90_NOWRITE,ncid); IF (rc/=NF90_NOERR) RETURN
    rc=nf90_inq_varid(ncid,'temperature_valid',valid_id)
    IF (rc==NF90_NOERR) rc=nf90_inq_varid(ncid,'temperature_quality',quality_id)
    IF (rc==NF90_NOERR) rc=nf90_inq_varid(ncid,'temperature_source',source_id)
    IF (rc==NF90_NOERR) rc=nf90_inq_varid(ncid,'above_ground',above_id)
    IF (rc==NF90_NOERR) rc=nf90_get_att(ncid,valid_id,'mask_encoding',valid_encoding)
    IF (rc==NF90_NOERR) rc=nf90_get_att(ncid,quality_id,'mask_encoding',quality_encoding)
    IF (rc==NF90_NOERR) rc=nf90_get_att(ncid,source_id,'mask_encoding',source_encoding)
    IF (rc==NF90_NOERR) rc=nf90_get_att(ncid,above_id,'mask_encoding',above_encoding)
    IF (rc==NF90_NOERR .AND. TRIM(valid_encoding)=='0=invalid,1=valid' .AND. &
        TRIM(quality_encoding)=='canonical_quality_bits_v1' .AND. &
        TRIM(source_encoding)=='canonical_source_bits_v1' .AND. &
        TRIM(above_encoding)=='0=below_ground,1=above_ground') status=STATUS_OK
    rc=nf90_close(ncid)
  END SUBROUTINE assert_mask_metadata

  SUBROUTINE mutate_valid_mask(path,status)
    CHARACTER(LEN=*), INTENT(IN) :: path
    INTEGER, INTENT(OUT) :: status
    INTEGER :: ncid,varid,rc
    INTEGER(int32) :: mask(nx,ny,nz,1)
    status=STATUS_FAILED
    rc=nf90_open(path,NF90_WRITE,ncid); IF (rc/=NF90_NOERR) RETURN
    rc=nf90_inq_varid(ncid,'temperature_valid',varid)
    IF (rc==NF90_NOERR) rc=nf90_get_var(ncid,varid,mask)
    IF (rc==NF90_NOERR) THEN
      mask(1,1,1,1)=2_int32
      rc=nf90_put_var(ncid,varid,mask)
    END IF
    IF (rc==NF90_NOERR) status=STATUS_OK
    rc=nf90_close(ncid)
  END SUBROUTINE mutate_valid_mask

  SUBROUTINE remove_file(file_path)
    CHARACTER(LEN=*), INTENT(IN) :: file_path
    INTEGER :: unit,local_ios
    OPEN(NEWUNIT=unit,FILE=TRIM(file_path),STATUS='OLD',IOSTAT=local_ios)
    IF (local_ios==0) CLOSE(unit,STATUS='DELETE',IOSTAT=local_ios)
  END SUBROUTINE remove_file

  SUBROUTINE assert_true(condition,message)
    LOGICAL, INTENT(IN) :: condition
    CHARACTER(LEN=*), INTENT(IN) :: message
    IF (.NOT.condition) THEN
      WRITE(*,'(A)') 'FAIL: '//TRIM(message)
      STOP 1
    END IF
  END SUBROUTINE assert_true

END PROGRAM test_cloud_bal_stage_payload
