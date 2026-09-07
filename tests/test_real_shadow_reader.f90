PROGRAM test_real_shadow_reader
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,int32,int64
  USE cloud_bal_state
  USE cloud_bal_real_netcdf, ONLY: read_real_shadow_state
  IMPLICIT NONE

  TYPE(cloud_bal_state_type) :: state
  REAL(real32), ALLOCATABLE :: longitude(:,:)
  CHARACTER(LEN=1024) :: fua,fsf,lw3,vrz,vrt,static_file,time_text,mode
  INTEGER(int64) :: valid_time
  INTEGER :: status,reason,io_status,k,expected_reason
  LOGICAL, ALLOCATABLE :: no_echo(:,:,:),missing(:,:,:)
  LOGICAL :: expect_reject

  IF (COMMAND_ARGUMENT_COUNT()<7 .OR. COMMAND_ARGUMENT_COUNT()>8) ERROR STOP &
    'usage: reader-test FUA FSF LW3 VRZ VRT STATIC VALID_TIME_EPOCH [REJECT|REJECT_COVERAGE]'
  CALL GET_COMMAND_ARGUMENT(1,fua)
  CALL GET_COMMAND_ARGUMENT(2,fsf)
  CALL GET_COMMAND_ARGUMENT(3,lw3)
  CALL GET_COMMAND_ARGUMENT(4,vrz)
  CALL GET_COMMAND_ARGUMENT(5,vrt)
  CALL GET_COMMAND_ARGUMENT(6,static_file)
  CALL GET_COMMAND_ARGUMENT(7,time_text)
  expect_reject=.FALSE.; expected_reason=-1
  IF (COMMAND_ARGUMENT_COUNT()==8) THEN
    CALL GET_COMMAND_ARGUMENT(8,mode)
    expect_reject=TRIM(mode)=='REJECT' .OR. TRIM(mode)=='REJECT_COVERAGE'
    IF (TRIM(mode)=='REJECT_COVERAGE') expected_reason=REASON_REQUIRED_COVERAGE
    IF (.NOT.expect_reject) ERROR STOP 'invalid reader-test mode'
  END IF
  READ(time_text,*,IOSTAT=io_status) valid_time
  IF (io_status/=0) ERROR STOP 'invalid valid time'

  CALL read_real_shadow_state(TRIM(fua),TRIM(fsf),TRIM(lw3),TRIM(vrz),TRIM(vrt), &
                              TRIM(static_file),valid_time,state,longitude,status,reason)
  IF (expect_reject) THEN
    IF (status==STATUS_OK) ERROR STOP 'reader accepted malformed real input'
    IF (expected_reason>=0 .AND. reason/=expected_reason) &
      ERROR STOP 'reader returned the wrong rejection reason'
    PRINT *,'Malformed real SHADOW input rejected'
    STOP
  END IF
  IF (status/=STATUS_OK .OR. reason/=REASON_NONE) THEN
    WRITE(*,'(A,I0,A,I0)') 'reader_status=',status,' reason=',reason
    ERROR STOP 'reader rejected real case'
  END IF
  CALL validate_canonical_state(state,.FALSE.,.TRUE.,status,reason,.TRUE.)
  IF (status/=STATUS_OK .OR. reason/=REASON_NONE) ERROR STOP 'final state is not canonical'

  IF (ALL(state%above_ground) .OR. .NOT.ANY(state%above_ground)) &
    ERROR STOP 'real terrain mask is not represented'
  IF (ANY(state%pressure%valid .NEQV. state%above_ground) .OR. &
      ANY(state%temperature%valid .NEQV. state%above_ground) .OR. &
      ANY(state%u%valid .NEQV. state%above_ground) .OR. &
      ANY(state%v%valid .NEQV. state%above_ground) .OR. &
      ANY(state%omega%valid .NEQV. state%above_ground)) &
    ERROR STOP 'core validity does not match terrain domain'
  DO k=1,state%grid%nz-1
    IF (ANY(state%above_ground(:,:,k) .AND. .NOT.state%above_ground(:,:,k+1))) &
      ERROR STOP 'terrain mask is vertically disconnected'
  END DO

  ALLOCATE(no_echo(state%grid%nx,state%grid%ny,state%grid%nz), &
           missing(state%grid%nx,state%grid%ny,state%grid%nz))
  no_echo=state%above_ground .AND. radar_no_echo_cell( &
    state%radar_reflectivity%value,state%radar_reflectivity%valid, &
    state%radar_reflectivity%quality,state%radar_reflectivity%source)
  missing=radar_missing_cell(state%radar_reflectivity%value, &
    state%radar_reflectivity%valid,state%radar_reflectivity%quality, &
    state%radar_reflectivity%source)
  IF (.NOT.ANY(state%radar_reflectivity%valid) .OR. .NOT.ANY(no_echo)) &
    ERROR STOP 'echo/no-echo split is absent'
  IF (ANY(state%radar_reflectivity%valid .NEQV. radar_echo_cell( &
      state%radar_reflectivity%value,state%radar_reflectivity%valid, &
      state%radar_reflectivity%quality,state%radar_reflectivity%source))) &
    ERROR STOP 'radar echo mask does not use the canonical predicate'
  IF (ANY(state%radar_reflectivity%valid .AND. .NOT.state%above_ground)) &
    ERROR STOP 'below-ground echo gained authority'
  IF (ANY(state%radar_reflectivity%valid .AND. &
          (state%radar_reflectivity%value<0.0_real32 .OR. &
           state%radar_reflectivity%value>100.0_real32))) &
    ERROR STOP 'usable radar range is invalid'
  IF (ANY(.NOT.state%radar_reflectivity%valid .AND. .NOT.(no_echo .OR. missing))) &
    ERROR STOP 'no-echo and missing radar provenance are not distinct'

  WRITE(*,'(A,I0)') 'above_ground_cells=',COUNT(state%above_ground)
  WRITE(*,'(A,I0)') 'usable_radar_cells=',COUNT(state%radar_reflectivity%valid)
  WRITE(*,'(A,I0)') 'observed_no_echo_cells=',COUNT(no_echo)
  PRINT *,'Real SHADOW reader contract test passed'
END PROGRAM test_real_shadow_reader
