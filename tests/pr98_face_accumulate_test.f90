PROGRAM pr98_face_accumulate_test
  USE, INTRINSIC :: iso_fortran_env, ONLY: real64
  USE pr98_budget_face_observer, ONLY: pr98_accumulate
  IMPLICIT NONE
  REAL(real64) :: total, compensation, exact_sum

  total = 0.0_real64
  compensation = 0.0_real64
  CALL pr98_accumulate(total, compensation, 2.0_real64**60)
  CALL pr98_accumulate(total, compensation, 1.0_real64)
  CALL pr98_accumulate(total, compensation, -(2.0_real64**60))
  exact_sum = total + compensation
  IF (exact_sum /= 1.0_real64) ERROR STOP 'Neumaier cancellation reference failed'
  WRITE(*,'(a,1p,es24.16)') 'PR98_ACCUMULATE_EXACT_SUM ', exact_sum
END PROGRAM pr98_face_accumulate_test
