MODULE pr101_upper_wind_capture
  USE, INTRINSIC :: iso_fortran_env, ONLY: int32
  IMPLICIT NONE
  PRIVATE
  PUBLIC :: pr101_capture_upper_wind

CONTAINS

  SUBROUTINE pr101_capture_upper_wind(component, phase, rk_step, time_step, field, tendency, mut, c1, c2, &
       msfux, msfuy, msfvx, msfvx_inv, msfvy, msftx, msfty, xkmhd, khdif, rdx, rdy, &
       diff_opt, km_opt, diff_6th_opt, open_xs, open_xe, open_ys, open_ye, &
       specified, nested, periodic_x, polar, ids, ide, jds, jde, kds, kde, &
       ims, ime, jms, jme, kms, kme, its, ite, jts, jte, kts, kte)
    CHARACTER(LEN=1), INTENT(IN) :: component
    INTEGER, INTENT(IN) :: phase, rk_step, time_step, diff_opt, km_opt, diff_6th_opt
    INTEGER, INTENT(IN) :: ids, ide, jds, jde, kds, kde
    INTEGER, INTENT(IN) :: ims, ime, jms, jme, kms, kme, its, ite, jts, jte, kts, kte
    LOGICAL, INTENT(IN) :: open_xs, open_xe, open_ys, open_ye
    LOGICAL, INTENT(IN) :: specified, nested, periodic_x, polar
    REAL, INTENT(IN) :: field(ims:ime,kms:kme,jms:jme)
    REAL, INTENT(IN) :: mut(ims:ime,jms:jme), c1(kms:kme), c2(kms:kme)
    REAL, INTENT(IN) :: msfux(ims:ime,jms:jme), msfuy(ims:ime,jms:jme)
    REAL, INTENT(IN) :: msfvx(ims:ime,jms:jme), msfvx_inv(ims:ime,jms:jme)
    REAL, INTENT(IN) :: msfvy(ims:ime,jms:jme), msftx(ims:ime,jms:jme), msfty(ims:ime,jms:jme)
    REAL, INTENT(IN) :: xkmhd(ims:ime,kms:kme,jms:jme), khdif, rdx, rdy
    REAL, INTENT(IN) :: tendency(ims:ime,kms:kme,jms:jme)

    INTEGER, PARAMETER :: first_k=37, last_k=39, magic=int(Z'50573130',int32)
    INTEGER :: unit, face_i, face_j, i, j, k, component_id
    INTEGER(int32) :: header(29)
    LOGICAL :: in_tile

    IF (component == 'u') THEN
      component_id=1; face_i=136; face_j=16
    ELSE IF (component == 'v') THEN
      component_id=2; face_i=135; face_j=17
    ELSE
      RETURN
    END IF
    in_tile = face_i >= its .AND. face_i <= ite .AND. face_j >= jts .AND. face_j <= jte
    IF (.NOT.in_tile) RETURN
    IF (first_k < kms .OR. last_k > kme) RETURN
    IF (face_i-1 < ims .OR. face_i+1 > ime .OR. face_j-1 < jms .OR. face_j+1 > jme) RETURN

    header = [INT(magic,int32), 1_int32, INT(component_id,int32), INT(phase,int32), &
      INT(rk_step,int32), INT(time_step,int32), &
      INT(face_i,int32), INT(face_j,int32), INT(ids,int32), INT(ide,int32), &
      INT(jds,int32), INT(jde,int32), INT(kds,int32), INT(kde,int32), &
      INT(ims,int32), INT(ime,int32), INT(jms,int32), INT(jme,int32), &
      INT(kms,int32), INT(kme,int32), INT(its,int32), INT(ite,int32), &
      INT(jts,int32), INT(jte,int32), INT(kts,int32), INT(kte,int32), &
      INT(diff_opt,int32), INT(km_opt,int32), INT(diff_6th_opt,int32)]
    OPEN(NEWUNIT=unit, FILE='pr101_upper_wind.raw', STATUS='UNKNOWN', &
         ACCESS='STREAM', FORM='UNFORMATTED', POSITION='APPEND', ACTION='WRITE', &
         CONVERT='BIG_ENDIAN')
    WRITE(unit) header
    WRITE(unit) INT(MERGE(1,0,open_xs),int32), INT(MERGE(1,0,open_xe),int32), &
      INT(MERGE(1,0,open_ys),int32), INT(MERGE(1,0,open_ye),int32), &
      INT(MERGE(1,0,specified),int32), INT(MERGE(1,0,nested),int32), &
      INT(MERGE(1,0,periodic_x),int32), INT(MERGE(1,0,polar),int32)
    WRITE(unit) khdif, rdx, rdy
    DO k=first_k,last_k
      WRITE(unit) c1(k), c2(k)
      DO j=face_j-1,face_j+1
        DO i=face_i-1,face_i+1
          WRITE(unit) field(i,k,j), xkmhd(i,k,j)
        END DO
      END DO
      WRITE(unit) tendency(face_i,k,face_j)
    END DO
    DO j=face_j-1,face_j+1
      DO i=face_i-1,face_i+1
        WRITE(unit) i, j, mut(i,j), msfux(i,j), msfuy(i,j), msfvx(i,j), &
          msfvx_inv(i,j), msfvy(i,j), msftx(i,j), msfty(i,j)
      END DO
    END DO
    CLOSE(unit)

  END SUBROUTINE pr101_capture_upper_wind
END MODULE pr101_upper_wind_capture
