! Test-only disabled adapter for the legacy main/status harness. The actual
! state-carrying adapter is exercised separately by full-ELF integration.
MODULE cloud_bal_deriv_adapter
  USE cloud_bal_state, ONLY: STATUS_OK
  IMPLICIT NONE
CONTAINS
  SUBROUTINE cloud_bal_deriv_entry(enabled,status)
    LOGICAL, INTENT(OUT) :: enabled
    INTEGER, INTENT(OUT) :: status
    enabled=.FALSE.
    status=STATUS_OK
  END SUBROUTINE cloud_bal_deriv_entry
END MODULE cloud_bal_deriv_adapter
