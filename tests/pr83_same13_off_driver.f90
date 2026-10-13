PROGRAM pr83_same13_off_driver
  USE, INTRINSIC :: iso_fortran_env, ONLY: int64,real32
  USE cloud_bal_state, ONLY: cloud_bal_state_type,STATUS_OK,MODE_OFF,canonical_states_equal
  USE cloud_bal_pipeline, ONLY: cloud_bal_pipeline_config,cloud_bal_pipeline_result, &
    run_cloud_bal_pipeline
  USE cloud_bal_real_netcdf, ONLY: read_real_shadow_state
  USE pr83_off_candidate_wps_hook, ONLY: write_pr83_off_candidate_wps
  IMPLICIT NONE

  TYPE(cloud_bal_state_type) :: background,candidate,operational
  TYPE(cloud_bal_pipeline_config) :: config
  TYPE(cloud_bal_pipeline_result) :: result
  REAL(real32), ALLOCATABLE :: longitude(:,:)
  CHARACTER(LEN=2048) :: arg(15)
  INTEGER :: i,status,reason,write_status
  INTEGER(int64) :: valid_time

  IF (COMMAND_ARGUMENT_COUNT()/=15) ERROR STOP &
    'usage: pr83-same13-off FUA FSF LW3 VRZ VRT STATIC LT1 LQ3 LWC LSX LCP LTY EPOCH OUTPUT.wps WITNESS.raw'
  DO i=1,15
    CALL GET_COMMAND_ARGUMENT(i,arg(i))
  END DO
  READ(arg(13),*) valid_time
  IF (valid_time/=1786885200_int64) ERROR STOP 'OFF input epoch is not 2026-08-16 13 UTC'
  CALL read_real_shadow_state(TRIM(arg(1)),TRIM(arg(2)),TRIM(arg(3)),TRIM(arg(4)), &
    TRIM(arg(5)),TRIM(arg(6)),valid_time,background,longitude,status,reason, &
    lt1_path=TRIM(arg(7)),lq3_path=TRIM(arg(8)),lwc_path=TRIM(arg(9)), &
    lsx_path=TRIM(arg(10)),lcp_path=TRIM(arg(11)),lty_path=TRIM(arg(12)))
  IF (status/=STATUS_OK) ERROR STOP 'same13 frozen producer background reader failed'

  config%requested_mode=MODE_OFF
  CALL run_cloud_bal_pipeline(background,candidate,operational,result,config)
  IF (result%status/=STATUS_OK .OR. result%requested_mode/=MODE_OFF) &
    ERROR STOP 'same13 pipeline did not complete in explicit OFF mode'
  IF (.NOT.canonical_states_equal(background,candidate) .OR. &
      .NOT.canonical_states_equal(background,operational)) &
    ERROR STOP 'same13 OFF pipeline changed its canonical state'
  CALL write_pr83_off_candidate_wps(background,candidate,TRIM(arg(14)),TRIM(arg(15)),write_status)
  IF (write_status/=STATUS_OK) ERROR STOP 'same13 OFF state failed existing WPS mapper/writer'
  WRITE(*,'(A)') 'status=PASS_SCOPED_SAME13_OFF_MAPPER_WRITER_REPLAY'
  WRITE(*,'(A)') 'science_authority=NONE'
  WRITE(*,'(A)') 'candidate_promotion=NONE'
END PROGRAM pr83_same13_off_driver
