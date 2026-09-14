PROGRAM test_real_shadow_reader
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,int32,int64
  USE cloud_bal_state
  USE cloud_bal_real_netcdf, ONLY: read_real_shadow_state
  IMPLICIT NONE

  TYPE(cloud_bal_state_type) :: state,baseline
  TYPE(field3d), ALLOCATABLE :: retained_omega
  REAL(real32), ALLOCATABLE :: longitude(:,:)
  CHARACTER(LEN=1024) :: fua,fsf,lw3,vrz,vrt,static_file,time_text,mode
  INTEGER(int64) :: valid_time
  INTEGER :: status,reason,io_status,k,expected_reason
  LOGICAL, ALLOCATABLE :: no_echo(:,:,:),missing(:,:,:)
  LOGICAL :: expect_reject,expect_retained,retained_reject

  IF (COMMAND_ARGUMENT_COUNT()<7 .OR. COMMAND_ARGUMENT_COUNT()>8) ERROR STOP &
    'usage: reader-test FUA FSF LW3 VRZ VRT STATIC VALID_TIME_EPOCH '&
    '[REJECT|REJECT_COVERAGE|RETAINED|RETAINED_REJECT]'
  CALL GET_COMMAND_ARGUMENT(1,fua)
  CALL GET_COMMAND_ARGUMENT(2,fsf)
  CALL GET_COMMAND_ARGUMENT(3,lw3)
  CALL GET_COMMAND_ARGUMENT(4,vrz)
  CALL GET_COMMAND_ARGUMENT(5,vrt)
  CALL GET_COMMAND_ARGUMENT(6,static_file)
  CALL GET_COMMAND_ARGUMENT(7,time_text)
  expect_reject=.FALSE.; expect_retained=.FALSE.; retained_reject=.FALSE.; expected_reason=-1
  IF (COMMAND_ARGUMENT_COUNT()==8) THEN
    CALL GET_COMMAND_ARGUMENT(8,mode)
    expect_retained=TRIM(mode)=='RETAINED'
    retained_reject=TRIM(mode)=='RETAINED_REJECT'
    expect_reject=TRIM(mode)=='REJECT' .OR. TRIM(mode)=='REJECT_COVERAGE' .OR. retained_reject
    IF (TRIM(mode)=='REJECT_COVERAGE') expected_reason=REASON_REQUIRED_COVERAGE
    IF (.NOT.expect_reject .AND. .NOT.expect_retained) ERROR STOP 'invalid reader-test mode'
  END IF
  READ(time_text,*,IOSTAT=io_status) valid_time
  IF (io_status/=0) ERROR STOP 'invalid valid time'

  IF (retained_reject) THEN
    ALLOCATE(retained_omega)
    CALL initialize_field(retained_omega,1,1,1,valid_time,'stale')
    CALL read_real_shadow_state(TRIM(fua),TRIM(fsf),TRIM(lw3),TRIM(vrz),TRIM(vrt), &
                                TRIM(static_file),valid_time,state,longitude,status,reason, &
                                retained_omega=retained_omega)
    IF (status==STATUS_OK) ERROR STOP 'reader accepted malformed real input'
    IF (ALLOCATED(retained_omega)) ERROR STOP 'retained omega survived late reader failure'
    IF (expected_reason>=0 .AND. reason/=expected_reason) &
      ERROR STOP 'reader returned the wrong rejection reason'
    PRINT *,'Malformed real SHADOW input rejected with unallocated retained omega'
    STOP
  ELSE IF (expect_retained) THEN
    CALL read_real_shadow_state(TRIM(fua),TRIM(fsf),TRIM(lw3),TRIM(vrz),TRIM(vrt), &
                                TRIM(static_file),valid_time,baseline,longitude,status,reason)
    IF (status/=STATUS_OK .OR. reason/=REASON_NONE) ERROR STOP 'baseline reader rejected real case'
    CALL read_real_shadow_state(TRIM(fua),TRIM(fsf),TRIM(lw3),TRIM(vrz),TRIM(vrt), &
                                TRIM(static_file),valid_time,state,longitude,status,reason, &
                                retained_omega=retained_omega)
    IF (status/=STATUS_OK .OR. reason/=REASON_NONE) ERROR STOP 'retained reader rejected real case'
    IF (.NOT.canonical_states_equal(state,baseline)) &
      ERROR STOP 'optional retained omega changed canonical state'
    CALL check_retained_omega(state,retained_omega,valid_time)
  ELSE
    CALL read_real_shadow_state(TRIM(fua),TRIM(fsf),TRIM(lw3),TRIM(vrz),TRIM(vrt), &
                                TRIM(static_file),valid_time,state,longitude,status,reason)
  END IF
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
  IF (.NOT.ALL(state%surface_height%valid) .OR. &
      state%surface_height%unit/='m' .OR. &
      ANY(IAND(state%surface_height%source,SOURCE_BACKGROUND_MODEL)==0_int32)) &
    ERROR STOP 'static average was not retained as background surface height'
  ! The pinned FSF schema has no MR variable.  The reader must preserve that
  ! legacy diagnostic behavior instead of deriving vapor from RH or dewpoint.
  IF (ANY(state%surface_vapor%valid)) ERROR STOP 'FSF vapor was fabricated'
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
  WRITE(*,'(A,A)') 'surface_height_unit=',TRIM(state%surface_height%unit)
  WRITE(*,'(A,I0)') 'surface_vapor_valid_cells=',COUNT(state%surface_vapor%valid)
  PRINT *,'Real SHADOW reader contract test passed'

CONTAINS

  SUBROUTINE check_retained_omega(state,field,expected_time)
    TYPE(cloud_bal_state_type), INTENT(IN) :: state
    TYPE(field3d), ALLOCATABLE, INTENT(IN) :: field
    INTEGER(int64), INTENT(IN) :: expected_time
    INTEGER :: i,j,k,marker_i,marker_j
    LOGICAL :: found_valid

    IF (.NOT.ALLOCATED(field)) ERROR STOP 'retained omega was not published on success'
    IF (.NOT.ALLOCATED(field%value) .OR. .NOT.ALLOCATED(field%valid) .OR. &
        .NOT.ALLOCATED(field%quality) .OR. .NOT.ALLOCATED(field%source)) &
      ERROR STOP 'retained omega arrays are incomplete'
    IF (ANY(SHAPE(field%value)/=(/state%grid%nx,state%grid%ny,state%grid%nz/)) .OR. &
        ANY(SHAPE(field%valid)/=(/state%grid%nx,state%grid%ny,state%grid%nz/)) .OR. &
        ANY(SHAPE(field%quality)/=(/state%grid%nx,state%grid%ny,state%grid%nz/)) .OR. &
        ANY(SHAPE(field%source)/=(/state%grid%nx,state%grid%ny,state%grid%nz/))) &
      ERROR STOP 'retained omega shape mismatch'
    IF (field%valid_time/=expected_time .OR. TRIM(field%unit)/='Pa s-1') &
      ERROR STOP 'retained omega metadata mismatch'

    DO k=1,state%grid%nz; DO j=1,state%grid%ny; DO i=1,state%grid%nx
      IF (.NOT.state%above_ground(i,j,k)) CYCLE
      IF (field%value(i,j,k)/=state%omega%value(i,j,k) .OR. &
          (field%valid(i,j,k).NEQV.state%omega%valid(i,j,k)) .OR. &
          field%quality(i,j,k)/=state%omega%quality(i,j,k) .OR. &
          field%source(i,j,k)/=state%omega%source(i,j,k)) &
        ERROR STOP 'retained omega differs on the canonical active domain'
    END DO; END DO; END DO

    found_valid=.FALSE.; marker_i=0; marker_j=0
    DO k=1,state%grid%nz; DO j=1,state%grid%ny; DO i=1,state%grid%nx
      IF (state%above_ground(i,j,k)) CYCLE
      IF (ABS(field%value(i,j,k)-17.25_real32)<1.0e-5_real32) THEN
        IF (k/=1 .OR. .NOT.field%valid(i,j,k) .OR. &
            field%quality(i,j,k)/=0_int32 .OR. &
            field%source(i,j,k)/=SOURCE_ANALYZED_WIND) &
          ERROR STOP 'valid retained omega was not reversed or tagged'
        found_valid=.TRUE.
        marker_i=i; marker_j=j
      END IF
    END DO; END DO; END DO
    IF (.NOT.found_valid) ERROR STOP 'valid retained omega fixture marker is absent outside domain'
    IF (field%valid(marker_i,marker_j,2) .OR. &
        field%value(marker_i,marker_j,2)/=0.0_real32 .OR. &
        field%quality(marker_i,marker_j,2)/=QUALITY_RAW_MISSING .OR. &
        field%source(marker_i,marker_j,2)/=0_int32) &
      ERROR STOP 'missing retained omega was not reversed or tagged'
    IF (field%valid(marker_i,marker_j,3) .OR. &
        ABS(field%value(marker_i,marker_j,3)-125.0_real32)>1.0e-5_real32 .OR. &
        field%quality(marker_i,marker_j,3)/=QUALITY_QC_REJECTED .OR. &
        field%source(marker_i,marker_j,3)/=0_int32) &
      ERROR STOP 'out-of-range retained omega was not rejected'
  END SUBROUTINE check_retained_omega
END PROGRAM test_real_shadow_reader
