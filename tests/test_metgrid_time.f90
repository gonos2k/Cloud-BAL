PROGRAM test_metgrid_time
  USE date_pack, ONLY: geth_newdate, pack_metgrid_time
  IMPLICIT NONE

  CHARACTER(LEN=19), PARAMETER :: aligned_date = '2023-05-18_03:00:00'
  CHARACTER(LEN=19), PARAMETER :: minute_date = '2023-05-18_03:05:00'
  CHARACTER(LEN=19), PARAMETER :: second_date = '2023-05-18-03:05:07'
  CHARACTER(LEN=19), PARAMETER :: second_expected = '2023-05-18_03:05:07'
  CHARACTER(LEN=19), PARAMETER :: second_start = '2023-05-18-03:33:20'
  INTEGER, PARAMETER :: matrix_size = 24
  INTEGER :: intervals(matrix_size), i
  CHARACTER(LEN=19) :: dates(matrix_size), expected(matrix_size)
  CHARACTER(LEN=19) :: actual, valid_date
  CHARACTER(LEN=19), PARAMETER :: header_names(2) = [ &
    '2023-05-18_03:33:20', '2023-05-18_03:38:20' ]

  intervals = [ &
    86400, 21600, 3600, 1800, 900, 300, 60, 45, &
    86400, 21600, 3600, 1800, 900, 300, 60, 45, &
    86400, 21600, 3600, 1800, 900, 300, 60, 45 ]
  dates = [ &
    aligned_date, aligned_date, aligned_date, aligned_date, &
    aligned_date, aligned_date, aligned_date, aligned_date, &
    minute_date, minute_date, minute_date, minute_date, &
    minute_date, minute_date, minute_date, minute_date, &
    second_date, second_date, second_date, second_date, &
    second_date, second_date, second_date, second_date ]
  expected = [ CHARACTER(LEN=19) :: &
    '2023-05-18_03', '2023-05-18_03', '2023-05-18_03', &
    '2023-05-18_03:00', '2023-05-18_03:00', '2023-05-18_03:00', &
    '2023-05-18_03:00', '2023-05-18_03:00:00', &
    '2023-05-18_03:05', '2023-05-18_03:05', '2023-05-18_03:05', &
    '2023-05-18_03:05', '2023-05-18_03:05', '2023-05-18_03:05', &
    '2023-05-18_03:05', '2023-05-18_03:05:00', &
    second_expected, second_expected, second_expected, second_expected, &
    second_expected, second_expected, second_expected, second_expected ]

  DO i = 1, matrix_size
    CALL pack_metgrid_time(dates(i), intervals(i), actual)
    IF (actual /= expected(i)) THEN
      WRITE(*,'(A,I0,A,A,A,A)') 'MATRIX_FAIL case=', i, ' actual="', &
        TRIM(actual), '" expected="'//TRIM(expected(i))//'"'
      ERROR STOP 'metgrid time matrix mismatch'
    END IF
  END DO
  WRITE(*,'(A,I0,A)') 'MATRIX_PASS cases=', matrix_size, &
    ' aligned-hour/minute/second formatting'

  CALL geth_newdate(valid_date, second_start, 0)
  CALL pack_metgrid_time(valid_date, 300, actual)
  IF (actual /= header_names(1)) THEN
    WRITE(*,'(A,A,A,A)') 'HEADER_FAIL first actual=', TRIM(actual), &
      ' expected=', TRIM(header_names(1))
    ERROR STOP 'first exact 300-second header mismatch'
  END IF

  CALL geth_newdate(valid_date, second_start, 300)
  CALL pack_metgrid_time(valid_date, 300, actual)
  IF (actual /= header_names(2)) THEN
    WRITE(*,'(A,A,A,A)') 'HEADER_FAIL second actual=', TRIM(actual), &
      ' expected=', TRIM(header_names(2))
    ERROR STOP 'second exact 300-second header mismatch'
  END IF

  WRITE(*,'(A,A,A,A)') 'HEADER_LOOKUP_EXACT first=', TRIM(header_names(1)), &
    ' second=', TRIM(header_names(2))
  WRITE(*,'(A)') 'METGRID_TIME_TEST_PASS'
END PROGRAM test_metgrid_time
