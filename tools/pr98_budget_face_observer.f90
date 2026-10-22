MODULE pr98_budget_face_observer
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32, real64
  IMPLICIT NONE
  PRIVATE
  PUBLIC :: pr98_face_record, pr98_accumulate
CONTAINS
  PURE SUBROUTINE pr98_accumulate(total, compensation, value)
    REAL(real64), INTENT(INOUT) :: total, compensation
    REAL(real64), INTENT(IN) :: value
    REAL(real64) :: high, low

    high = total + value
    IF (ABS(total) >= ABS(value)) THEN
      low = (total - high) + value
    ELSE
      low = (value - high) + total
    ENDIF
    compensation = compensation + low
    total = high
  END SUBROUTINE pr98_accumulate

  SUBROUTINE pr98_face_record(cell_i, lat, substep, mode, donor, receiver, has_receiver, &
                              theta, proposed_q, donor_before, donor_after, donor_density, donor_dz, &
                              receiver_before, receiver_after, receiver_density, receiver_dz)
    INTEGER, INTENT(IN) :: cell_i, lat, substep, mode, donor, receiver
    LOGICAL, INTENT(IN) :: has_receiver
    REAL(real64), INTENT(IN) :: theta, proposed_q
    REAL(real32), INTENT(IN) :: donor_before, donor_after, donor_density, donor_dz
    REAL(real32), INTENT(IN) :: receiver_before, receiver_after, receiver_density, receiver_dz
    INTEGER :: unit, io_status, receiver_flag

    IF (.NOT. ((cell_i == 208 .AND. lat == 79) .OR. &
               (cell_i == 184 .AND. lat == 147))) RETURN
    receiver_flag = MERGE(1, 0, has_receiver)
    OPEN(NEWUNIT=unit, FILE='pr98_sed_face.raw', FORM='FORMATTED', STATUS='UNKNOWN', &
         POSITION='APPEND', ACTION='WRITE', IOSTAT=io_status)
    IF (io_status /= 0) ERROR STOP 'PR98 face observer open failed'
    WRITE(unit,'(a,7i8,1p,10es26.17)',IOSTAT=io_status) &
      'PR98_SED_FACE',cell_i,lat,substep,mode,donor,receiver,receiver_flag, &
      theta,proposed_q,REAL(donor_before,real64),REAL(donor_after,real64), &
      REAL(donor_density,real64),REAL(donor_dz,real64), &
      REAL(receiver_before,real64),REAL(receiver_after,real64), &
      REAL(receiver_density,real64),REAL(receiver_dz,real64)
    CLOSE(unit)
    IF (io_status /= 0) ERROR STOP 'PR98 face observer write failed'
  END SUBROUTINE pr98_face_record
END MODULE pr98_budget_face_observer
