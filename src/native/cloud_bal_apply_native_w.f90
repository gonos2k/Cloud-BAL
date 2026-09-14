PROGRAM cloud_bal_apply_native_w
  USE cloud_bal_native_w_consumer, ONLY: apply_native_w_increment, NATIVE_W_CONSUMER_OK
  IMPLICIT NONE

  CHARACTER(LEN=1024) :: wrfin_path,candidate_path,expected_time,option
  LOGICAL :: enabled
  INTEGER :: status

  IF (COMMAND_ARGUMENT_COUNT()<3 .OR. COMMAND_ARGUMENT_COUNT()>4) THEN
    ERROR STOP 'usage: cloud_bal_apply_native_w STAGED_WRFINPUT PAYLOAD EXPECTED_TIME [--off]'
  END IF
  CALL GET_COMMAND_ARGUMENT(1,wrfin_path)
  CALL GET_COMMAND_ARGUMENT(2,candidate_path)
  CALL GET_COMMAND_ARGUMENT(3,expected_time)
  enabled=.TRUE.
  IF (COMMAND_ARGUMENT_COUNT()==4) THEN
    CALL GET_COMMAND_ARGUMENT(4,option)
    IF (TRIM(option)/='--off') ERROR STOP 'unknown option'
    enabled=.FALSE.
  END IF

  CALL apply_native_w_increment(TRIM(wrfin_path),TRIM(candidate_path), &
                                TRIM(expected_time),enabled,status)
  IF (status/=NATIVE_W_CONSUMER_OK .AND. enabled) ERROR STOP status
END PROGRAM cloud_bal_apply_native_w
