PROGRAM test_canonical_state
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32,int64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value,ieee_quiet_nan
  USE cloud_bal_state
  IMPLICIT NONE

  INTEGER :: failures
  failures=0
  CALL test_contract(failures)
  CALL test_transaction(failures)
  CALL test_vertical_conversion(failures)
  CALL test_los_contract(failures)
  IF (failures/=0) THEN
    PRINT *,'Canonical state tests failed:',failures
    ERROR STOP 1
  END IF
  PRINT *,'Canonical state tests passed'

CONTAINS

  SUBROUTINE check(condition,message,failures)
    LOGICAL, INTENT(IN) :: condition
    CHARACTER(LEN=*), INTENT(IN) :: message
    INTEGER, INTENT(INOUT) :: failures
    IF (.NOT.condition) THEN
      failures=failures+1
      PRINT *,'FAIL: ',TRIM(message)
    END IF
  END SUBROUTINE check

  SUBROUTINE make_valid_state(state)
    TYPE(cloud_bal_state_type), INTENT(OUT) :: state
    INTEGER :: status
    INTEGER(int64), PARAMETER :: analysis_time=1788224400_int64

    CALL initialize_cloud_bal_state(state,4,5,3,analysis_time,'NE57-test',status)
    IF (status/=STATUS_OK) ERROR STOP 'state initialization failed'
    state%grid%dx=2000.0_real64
    state%grid%dy=2500.0_real64
    state%grid%dp(:,:,1)=10000.0_real64
    state%grid%dp(:,:,2)=15000.0_real64
    state%grid%dp(:,:,3)=20000.0_real64
    state%grid%cell_measure=SPREAD(state%grid%dx*state%grid%dy,3,3)* &
      state%grid%dp/9.80665_real64
    CALL fill_real_field(state%pressure,80000.0_real32,SOURCE_BACKGROUND_MODEL)
    CALL fill_real_field(state%temperature,280.0_real32,SOURCE_BACKGROUND_MODEL)
    CALL fill_real_field(state%vapor,0.008_real32,SOURCE_BACKGROUND_MODEL)
    CALL fill_real_field(state%u,5.0_real32,SOURCE_ANALYZED_WIND)
    CALL fill_real_field(state%v,-2.0_real32,SOURCE_ANALYZED_WIND)
    CALL fill_real_field(state%omega,0.0_real32,SOURCE_BACKGROUND_MODEL)
    CALL fill_surface_field(state%surface_pressure,100000.0_real32)
    CALL fill_surface_field(state%surface_temperature,290.0_real32)
  END SUBROUTINE make_valid_state

  SUBROUTINE fill_real_field(field,value,source)
    TYPE(field3d), INTENT(INOUT) :: field
    REAL(real32), INTENT(IN) :: value
    INTEGER(int32), INTENT(IN) :: source
    field%value=value
    field%valid=.TRUE.
    field%quality=0_int32
    field%source=source
  END SUBROUTINE fill_real_field

  SUBROUTINE fill_surface_field(field,value)
    TYPE(field2d), INTENT(INOUT) :: field
    REAL(real32), INTENT(IN) :: value
    field%value=value
    field%valid=.TRUE.
    field%quality=0_int32
    field%source=SOURCE_BACKGROUND_MODEL
  END SUBROUTINE fill_surface_field

  SUBROUTINE test_contract(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: state,read_state
    TYPE(canonical_input_spec) :: spec
    TYPE(stage_result) :: result
    INTEGER :: status,reason

    CALL make_valid_state(state)
    CALL validate_canonical_state(state,.FALSE.,.FALSE.,status,reason)
    CALL check(status==STATUS_OK .AND. reason==REASON_NONE, &
               'complete canonical state must validate',failures)

    state%vapor%valid(1,1,1)=.FALSE.
    state%vapor%quality(1,1,1)=QUALITY_RAW_MISSING
    CALL validate_canonical_state(state,.FALSE.,.FALSE.,status,reason)
    CALL check(status==STATUS_DEGRADED, &
               'partial required coverage must be degraded',failures)
    state%vapor%valid(1,1,1)=.TRUE.
    state%vapor%quality(1,1,1)=0_int32

    state%pressure%unit='hPa'
    CALL validate_canonical_state(state,.FALSE.,.FALSE.,status,reason)
    CALL check(status==STATUS_FAILED .AND. reason==REASON_SHAPE, &
               'wrong canonical unit must fail before use',failures)
    state%pressure%unit='Pa'

    state%temperature%value(2,2,2)=ieee_value(0.0_real32,ieee_quiet_nan)
    CALL validate_canonical_state(state,.FALSE.,.FALSE.,status,reason)
    CALL check(status==STATUS_FAILED .AND. reason==REASON_NONFINITE, &
               'valid NaN must fail',failures)
    state%temperature%value(2,2,2)=280.0_real32

    ALLOCATE(spec%supplied_state)
    spec%supplied_state=state
    CALL read_canonical_state(spec,read_state,result)
    CALL check(result%status==STATUS_OK,'validated read must succeed',failures)
    spec%supplied_state%u%value=99.0_real32
    CALL check(ALL(TRANSFER(read_state%u%value,[0_int32],SIZE(read_state%u%value))== &
                   TRANSFER(5.0_real32,0_int32)), &
               'read must deep-copy the supplied state',failures)
  END SUBROUTINE test_contract

  SUBROUTINE test_transaction(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: original,candidate,published
    TYPE(stage_result) :: candidate_result,result

    CALL make_valid_state(original)
    candidate=original
    candidate%u%value(2,3,2)=8.0_real32
    CALL initialize_stage_result(candidate_result,4,5,3,STATUS_DEGRADED,REASON_GATE)
    candidate_result%changed(2,3,2)=.TRUE.
    CALL commit_candidate(original,candidate,candidate_result,published,result)
    CALL check(TRANSFER(published%u%value(2,3,2),0_int32)== &
               TRANSFER(original%u%value(2,3,2),0_int32), &
               'non-OK candidate must publish exact input',failures)

    candidate_result%status=STATUS_OK
    candidate_result%reason_code=REASON_NONE
    CALL commit_candidate(original,candidate,candidate_result,published,result)
    CALL check(TRANSFER(published%u%value(2,3,2),0_int32)== &
               TRANSFER(8.0_real32,0_int32), &
               'OK candidate must commit complete work state',failures)
  END SUBROUTINE test_transaction

  SUBROUTINE test_vertical_conversion(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real32) :: omega(2,1,1),pressure(2,1,1),temperature(2,1,1)
    REAL(real32) :: vapor(2,1,1),w(2,1,1),roundtrip(2,1,1)
    LOGICAL :: valid(2,1,1),w_valid(2,1,1),omega_valid(2,1,1)
    INTEGER :: status

    omega(:,1,1)=(/-1.0_real32,1.5_real32/)
    pressure=85000.0_real32; temperature=280.0_real32; vapor=0.01_real32
    valid=.TRUE.
    CALL omega_to_w(omega,pressure,temperature,vapor,valid,w,w_valid,status)
    CALL check(status==STATUS_OK .AND. ALL(w_valid), &
               'omega to w conversion must succeed',failures)
    CALL check(w(1,1,1)>0.0_real32 .AND. w(2,1,1)<0.0_real32, &
               'omega and geometric w signs must oppose',failures)
    CALL w_to_omega(w,pressure,temperature,vapor,w_valid,roundtrip,omega_valid,status)
    CALL check(status==STATUS_OK .AND. &
               MAXVAL(ABS(roundtrip-omega))<2.0e-6_real32, &
               'local rho*g conversion must round trip',failures)

    pressure(1,1,1)=0.0_real32
    CALL omega_to_w(omega,pressure,temperature,vapor,valid,w,w_valid,status)
    CALL check(status==STATUS_FAILED,'nonphysical pressure must fail',failures)
  END SUBROUTINE test_vertical_conversion

  SUBROUTINE test_los_contract(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(cloud_bal_state_type) :: state
    INTEGER :: status,reason,nx,ny,nz,nr
    INTEGER(int64) :: valid_time

    CALL make_valid_state(state)
    nx=state%grid%nx; ny=state%grid%ny; nz=state%grid%nz
    valid_time=state%pressure%valid_time
    CALL validate_los_observations(state%radar_los,nx,ny,nz,valid_time,status,reason)
    CALL check(status==STATUS_OK,'absent LOS record must be exact OK',failures)

    ALLOCATE(state%radar_los%beam(nx,ny,nz,1,3))
    state%radar_los%beam=0.0_real32
    CALL validate_los_observations(state%radar_los,nx,ny,nz,valid_time,status,reason)
    CALL check(status==STATUS_FAILED, &
               'absent LOS record with allocated payload must fail',failures)
    DEALLOCATE(state%radar_los%beam)

    nr=1
    state%radar_los%is_present=.TRUE.; state%radar_los%nradar=nr
    CALL initialize_field(state%radar_los%vrad,nx,ny,nz,nr,valid_time,'m s-1')
    CALL initialize_field(state%radar_los%nyquist,nx,ny,nz,nr,valid_time,'m s-1')
    CALL initialize_field(state%radar_los%sigma_vrad,nx,ny,nz,nr,valid_time,'m s-1')
    state%radar_los%vrad%value=3.0_real32
    state%radar_los%nyquist%value=15.0_real32
    state%radar_los%sigma_vrad%value=1.0_real32
    state%radar_los%vrad%valid=.TRUE.; state%radar_los%nyquist%valid=.TRUE.
    state%radar_los%sigma_vrad%valid=.TRUE.
    state%radar_los%vrad%quality=0; state%radar_los%nyquist%quality=0
    state%radar_los%sigma_vrad%quality=0
    state%radar_los%vrad%source=SOURCE_RADAR_VRAD
    state%radar_los%nyquist%source=SOURCE_RADAR_VRAD
    state%radar_los%sigma_vrad%source=SOURCE_RADAR_VRAD
    ALLOCATE(state%radar_los%beam(nx,ny,nz,nr,3), &
             state%radar_los%observation_id_hi(nx,ny,nz,nr), &
             state%radar_los%observation_id_lo(nx,ny,nz,nr), &
             state%radar_los%usage(nx,ny,nz,nr), &
             state%radar_los%los_support(nx,ny,nz,nr), &
             state%radar_los%radar_id(nr),state%radar_los%observation_time(nr), &
             state%radar_los%site_lat(nr),state%radar_los%site_lon(nr), &
             state%radar_los%site_height(nr),state%radar_los%wavelength(nr), &
             state%radar_los%geometry_condition(nx,ny,nz), &
             state%radar_los%geometry_rank(nx,ny,nz))
    state%radar_los%beam=0.0_real32; state%radar_los%beam(:,:,:,:,1)=1.0_real32
    state%radar_los%observation_id_hi=1_int64
    state%radar_los%observation_id_lo=2_int64
    state%radar_los%usage=LOS_HELD_OUT
    state%radar_los%los_support=1_int32
    state%radar_los%radar_id=100_int32
    state%radar_los%observation_time=valid_time
    state%radar_los%site_lat=36.0_real64; state%radar_los%site_lon=128.0_real64
    state%radar_los%site_height=100.0_real64; state%radar_los%wavelength=0.10_real64
    state%radar_los%geometry_condition=1.0_real32
    state%radar_los%geometry_rank=1_int32
    CALL validate_los_observations(state%radar_los,nx,ny,nz,valid_time,status,reason)
    CALL check(status==STATUS_OK,'complete post-QC LOS record must pass',failures)

    state%radar_los%nyquist%value(1,1,1,1)=-1.0_real32
    CALL validate_los_observations(state%radar_los,nx,ny,nz,valid_time,status,reason)
    CALL check(status==STATUS_FAILED .AND. reason==REASON_RANGE, &
               'bad Nyquist metadata must fail LOS contract',failures)
  END SUBROUTINE test_los_contract

END PROGRAM test_canonical_state
