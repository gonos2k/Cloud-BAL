! Diagnostic-only link stub for the serial wrapper fixture.
! Radar is disabled; unexpected diagnostic calls fail rather than disappear.
SUBROUTINE wrf_debug(level, message)
  IMPLICIT NONE
  INTEGER, INTENT(IN) :: level
  CHARACTER(*), INTENT(IN) :: message
  WRITE(*,*) level, message
  ERROR STOP "unexpected wrf_debug call in isolated wrapper fixture"
END SUBROUTINE wrf_debug
