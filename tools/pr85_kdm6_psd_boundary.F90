SUBROUTINE pr85_kdm6_psd_bound_number(q,rho,lambda,lambda_min,lambda_max,pid,exponent,side, &
species,stage,cell_i,lat,k,number_before,legacy_available,trace,ledger_unit,native_number,directed_number, &
exact_min,exact_max,valid)
USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
IMPLICIT NONE
REAL, INTENT(IN) :: q,rho,lambda,lambda_min,lambda_max,pid,exponent,number_before
INTEGER, INTENT(IN) :: side,cell_i,lat,k,ledger_unit
CHARACTER(*), INTENT(IN) :: species,stage
LOGICAL, INTENT(OUT) :: legacy_available
LOGICAL, INTENT(IN) :: trace
REAL, INTENT(OUT) :: native_number,directed_number
REAL(8), INTENT(OUT) :: exact_min,exact_max
LOGICAL, INTENT(OUT) :: valid
REAL(8) :: q64,rho64,lambda64,lmin64,lmax64,pid64,exp64
REAL(8) :: native_product,native_power,native_predivide,native_exact
REAL(8) :: huge32_safe,storage_correction,native_delta
REAL :: rounded_bound
INTEGER :: io_status

valid=.FALSE.
legacy_available=.FALSE.
native_number=number_before
directed_number=number_before
exact_min=0.0D0
exact_max=0.0D0
IF (.NOT.ALL(ieee_is_finite([q,rho,lambda,lambda_min,lambda_max,pid,exponent,number_before]))) RETURN
IF (q<=0.0 .OR. rho<=0.0 .OR. lambda<=0.0 .OR. lambda_min<=0.0 .OR. &
    lambda_max<lambda_min .OR. pid<=0.0 .OR. exponent/=3.0 .OR. (side/=1 .AND. side/=2)) RETURN
IF (side==1 .AND. lambda/=lambda_min) RETURN
IF (side==2 .AND. lambda/=lambda_max) RETURN
q64=DBLE(q); rho64=DBLE(rho); lambda64=DBLE(lambda)
lmin64=DBLE(lambda_min); lmax64=DBLE(lambda_max); pid64=DBLE(pid); exp64=DBLE(exponent)
! This operation order matches state_valid's R64 lambda-bound predicate.
exact_min=(rho64*lmin64**3)/pid64*q64
exact_max=(rho64*lmax64**3)/pid64*q64
IF (.NOT.ALL(ieee_is_finite([exact_min,exact_max]))) RETURN
IF (exact_min<=0.0D0 .OR. exact_max<exact_min) RETURN
IF (exact_min>DBLE(HUGE(1.0)) .OR. exact_max>DBLE(HUGE(1.0))) RETURN
rounded_bound=REAL(MERGE(exact_min,exact_max,side==1))
IF (.NOT.ieee_is_finite(rounded_bound) .OR. rounded_bound<=0.0) RETURN
IF (side==1) THEN
  IF (DBLE(rounded_bound)<exact_min) rounded_bound=NEAREST(rounded_bound,1.0)
ELSE
  IF (DBLE(rounded_bound)>exact_max) rounded_bound=NEAREST(rounded_bound,-1.0)
ENDIF
IF (.NOT.ieee_is_finite(rounded_bound) .OR. rounded_bound<=0.0) RETURN
IF (DBLE(rounded_bound)<exact_min .OR. DBLE(rounded_bound)>exact_max) RETURN
! Preflight every REAL32 intermediate in the legacy source formula before evaluating it.
! If this reset cannot be represented by the existing REAL32 expression, fail closed.
native_product=rho64*q64
native_power=lambda64**exp64
native_predivide=native_product*native_power
native_exact=native_predivide/pid64
huge32_safe=DBLE(NEAREST(HUGE(1.0),-1.0))
directed_number=rounded_bound
IF (ALL(ieee_is_finite([native_product,native_power,native_predivide,native_exact])) .AND. &
    native_product<=huge32_safe .AND. native_power<=huge32_safe .AND. &
    native_predivide<=huge32_safe .AND. native_exact<=huge32_safe) THEN
  native_number=rho*q*lambda**exponent/pid
  legacy_available=.TRUE.
  storage_correction=DBLE(directed_number)-DBLE(native_number)
  native_delta=DBLE(native_number)-DBLE(number_before)
ELSE
  native_number=0.0
  storage_correction=0.0D0
  native_delta=0.0D0
ENDIF
valid=.TRUE.
IF (trace) THEN
  WRITE(ledger_unit,'(A,",",A,",",A,4(",",I0),1P,11(",",ES24.16E3),",",L1)',IOSTAT=io_status) &
       'PR85_KDM6_PSD_BOUNDARY',species,stage,cell_i,lat,k,side, &
       q,rho,lambda_min,lambda_max,number_before,native_number,directed_number, &
       native_delta,storage_correction,exact_min,exact_max,legacy_available
  IF (io_status/=0) ERROR STOP 'PR85 PSD boundary ledger write failed'
ENDIF
END SUBROUTINE pr85_kdm6_psd_bound_number
