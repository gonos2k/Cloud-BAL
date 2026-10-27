PROGRAM test_static_reader
  USE laps_static
  IMPLICIT NONE
  CHARACTER(LEN=512) :: root
  CHARACTER(LEN=32) :: expected
  CALL GET_COMMAND_ARGUMENT(1,root)
  CALL GET_COMMAND_ARGUMENT(2,expected)
  CALL get_horiz_grid_spec(TRIM(root))
  IF (ABS(dx-5.0) > 1.0E-6 .OR. ABS(dy-5.0) > 1.0E-6) STOP 2
  IF (SIZE(lats,1) <= 0 .OR. SIZE(lats,2) <= 0) STOP 3
  IF (SIZE(topo,1) /= SIZE(lats,1) .OR. SIZE(topo,2) /= SIZE(lats,2)) STOP 4
  IF (TRIM(expected) == 'synthetic') THEN
    IF (ABS(lats(3,2)-5.0) > 1.0E-6 .OR. ABS(lons(3,2)-5.0) > 1.0E-6) STOP 5
    IF (ABS(lats(2,1)-1.0) > 1.0E-6 .OR. ABS(lats(1,2)-3.0) > 1.0E-6) STOP 7
    IF (ABS(topo(3,2)-5.0) > 1.0E-6 .OR. TRIM(grid_type) /= 'lambert') STOP 6
  END IF
  PRINT '(A)', 'STATIC_READER_PASS'
END PROGRAM test_static_reader
