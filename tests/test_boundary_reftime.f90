PROGRAM test_boundary_reftime
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,int32,int64
  USE cloud_bal_state
  USE cloud_bal_real_netcdf, ONLY: read_real_shadow_state, &
                                    set_real_numerical_test_boundaries
  USE cloud_bal_balance_operator, ONLY: manufactured_boundary_contract_valid
  IMPLICIT NONE

  TYPE(cloud_bal_state_type) :: state,work,before_state
  REAL(real32), ALLOCATABLE :: longitude(:,:)
  CHARACTER(LEN=1024) :: fua,fsf_reader_center,fsf_before,fsf_center,fsf_after
  CHARACTER(LEN=1024) :: lw3,vrz,vrt,static_file,mode
  CHARACTER(LEN=64) :: time_text
  INTEGER(int64) :: valid_time
  INTEGER :: status,reason,io_status

  IF (COMMAND_ARGUMENT_COUNT()/=11) ERROR STOP &
    'usage: test FUA FSF_READER_CENTER FSF_BEFORE FSF_CENTER FSF_AFTER LW3 VRZ VRT STATIC VALID_TIME MODE'
  CALL GET_COMMAND_ARGUMENT(1,fua)
  CALL GET_COMMAND_ARGUMENT(2,fsf_reader_center)
  CALL GET_COMMAND_ARGUMENT(3,fsf_before)
  CALL GET_COMMAND_ARGUMENT(4,fsf_center)
  CALL GET_COMMAND_ARGUMENT(5,fsf_after)
  CALL GET_COMMAND_ARGUMENT(6,lw3)
  CALL GET_COMMAND_ARGUMENT(7,vrz)
  CALL GET_COMMAND_ARGUMENT(8,vrt)
  CALL GET_COMMAND_ARGUMENT(9,static_file)
  CALL GET_COMMAND_ARGUMENT(10,time_text)
  CALL GET_COMMAND_ARGUMENT(11,mode)
  READ(time_text,*,IOSTAT=io_status) valid_time
  IF (io_status/=0) ERROR STOP 'invalid valid time'

  ! The public reader supplies the canonical state; this test never constructs
  ! a state by hand and never calls an internal NetCDF helper.
  CALL read_real_shadow_state(TRIM(fua),TRIM(fsf_reader_center),TRIM(lw3),TRIM(vrz), &
                              TRIM(vrt),TRIM(static_file),valid_time,state, &
                              longitude,status,reason)
  IF (status/=STATUS_OK .OR. reason/=REASON_NONE) ERROR STOP &
    'public real reader rejected the 13 UTC state'

  IF (TRIM(mode)=='POSITIVE') THEN
    work=state
    CALL set_real_numerical_test_boundaries(work,TRIM(fsf_before), &
      TRIM(fsf_center),TRIM(fsf_after),status,reason)
    IF (status/=STATUS_OK .OR. reason/=REASON_NONE) ERROR STOP &
      'matched manufactured boundary setup failed'
    IF (.NOT.manufactured_boundary_contract_valid(work)) ERROR STOP &
      'positive boundary contract did not validate'
    IF (.NOT.ALL(work%omega_top_boundary%valid) .OR. &
        .NOT.ALL(work%omega_bottom_boundary%valid) .OR. &
        ANY(IAND(work%omega_top_boundary%source,SOURCE_MANUFACTURED_TEST)==0_int32) .OR. &
        ANY(IAND(work%omega_bottom_boundary%source,SOURCE_MANUFACTURED_TEST)==0_int32)) &
      ERROR STOP 'positive setup did not retain manufactured provenance'
    WRITE(*,'(A)') 'POSITIVE_MANUFACTURED_BOUNDARY STATUS_OK REASON_NONE'
    WRITE(*,'(A)') 'BOUNDARY_AUTHORITY=MANUFACTURED_TEST_ONLY'
    WRITE(*,'(A)') 'PHYSICAL_AUTHORITY=NONE'
  ELSE IF (TRIM(mode)=='NEGATIVE') THEN
    before_state=state
    work=state
    CALL set_real_numerical_test_boundaries(work,TRIM(fsf_before), &
      TRIM(fsf_center),TRIM(fsf_after),status,reason)
    IF (status/=STATUS_FAILED .OR. reason/=REASON_METADATA) ERROR STOP &
      'reftime mutation did not return STATUS_FAILED/REASON_METADATA'
    IF (.NOT.canonical_states_equal(work,before_state)) ERROR STOP &
      'failed boundary setter mutated canonical state'
    WRITE(*,'(A)') 'NEGATIVE_REFTIME STATUS_FAILED REASON_METADATA STATE_UNCHANGED'
  ELSE
    ERROR STOP 'mode must be POSITIVE or NEGATIVE'
  END IF
END PROGRAM test_boundary_reftime
