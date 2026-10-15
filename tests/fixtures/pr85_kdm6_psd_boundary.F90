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

PROGRAM pr85_kdm6_psd_boundary_test
USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
IMPLICIT NONE
REAL :: native_number,directed_number,n_before
REAL(8) :: exact_min,exact_max
LOGICAL :: valid,legacy_available
INTEGER :: unit
EXTERNAL :: pr85_kdm6_psd_bound_number
REAL :: q,rho,lambda_min,lambda_max,pid,exponent

OPEN(NEWUNIT=unit,STATUS='scratch',ACTION='write')
! Captured post-ice-face cell: native R32 clamp is just below exact lambda_min.
q=8.6389809439424425e-6
rho=0.68017494678497314
lambda_min=9080.0
lambda_max=1.82e6
pid=1570.79638671875
exponent=3.0
n_before=2678.547119140625
CALL pr85_kdm6_psd_bound_number(q,rho,lambda_min,lambda_min,lambda_max,pid,exponent,1, &
     'ice','capture',148,46,17,n_before,legacy_available,.TRUE.,unit,native_number,directed_number, &
     exact_min,exact_max,valid)
IF (.NOT.valid .OR. .NOT.legacy_available) ERROR STOP 'captured lower-bound packet rejected'
IF (DBLE(native_number)>=exact_min) ERROR STOP 'fixture no longer reproduces native lower-bound miss'
IF (DBLE(directed_number)<exact_min .OR. DBLE(directed_number)>exact_max) &
  ERROR STOP 'directed lower-bound store is outside cone'
IF (directed_number<=native_number) ERROR STOP 'lower-bound store was not rounded upward'
IF (ABS(DBLE(directed_number)-DBLE(native_number))>2.0D0*DBLE(SPACING(native_number))) &
  ERROR STOP 'lower-bound storage correction exceeds two REAL32 steps'
WRITE(*,'(A,1X,ES24.16E3,1X,ES24.16E3)') 'CASE captured lower-bound reset corrected', &
     native_number,directed_number

! At the upper bound this exact R64 count rounds upward; store its lower neighbor.
q=0.03
rho=0.9
lambda_min=1.0
lambda_max=7.0
pid=11.0
n_before=0.5
CALL pr85_kdm6_psd_bound_number(q,rho,lambda_max,lambda_min,lambda_max,pid,3.0,2, &
     'cloud','upper',1,1,1,n_before,legacy_available,.FALSE.,unit,native_number,directed_number, &
     exact_min,exact_max,valid)
IF (.NOT.valid .OR. .NOT.legacy_available) ERROR STOP 'upper-bound packet rejected'
IF (DBLE(directed_number)<exact_min .OR. DBLE(directed_number)>exact_max) &
  ERROR STOP 'directed upper-bound store is outside cone'
IF (directed_number>=REAL(exact_max)) ERROR STOP 'upper-bound store was not rounded downward'
WRITE(*,'(A,1X,ES24.16E3)') 'CASE upper-bound reset rounds downward',directed_number

! If only the legacy REAL32 intermediate overflows, retain the safe directed count and flag it.
q=1.0e20
rho=1.0e20
lambda_min=9.9e9
lambda_max=1.01e10
pid=1.0e38
n_before=1.0e32
CALL pr85_kdm6_psd_bound_number(q,rho,lambda_min,lambda_min,lambda_max,pid,3.0,1, &
     'ice','legacy-unavailable',1,1,1,n_before,legacy_available,.FALSE.,unit,native_number,directed_number, &
     exact_min,exact_max,valid)
IF (.NOT.valid .OR. legacy_available) ERROR STOP 'safe bound with unsafe native intermediate not classified'
IF (DBLE(directed_number)<exact_min .OR. DBLE(directed_number)>exact_max) &
  ERROR STOP 'safe directed count is outside cone'
WRITE(*,'(A)') 'CASE unsafe legacy intermediate flagged without suppressing safe candidate'

! A finite but unrepresentable exact interval must fail atomically.
native_number=-17.0
directed_number=-19.0
exact_min=-23.0D0
exact_max=-29.0D0
legacy_available=.TRUE.
CALL pr85_kdm6_psd_bound_number(1.0e30,1.0e30,1.0e10,1.0,1.0e10,1.0,3.0,1, &
     'ice','invalid',1,1,1,31.0,legacy_available,.FALSE.,unit,native_number,directed_number, &
     exact_min,exact_max,valid)
IF (valid .OR. legacy_available) ERROR STOP 'unrepresentable bound accepted'
IF (native_number/=31.0 .OR. directed_number/=31.0) ERROR STOP 'invalid candidate changed number state'
WRITE(*,'(A)') 'CASE unrepresentable interval rejected atomically'
CLOSE(unit)
WRITE(*,'(A)') 'PR85 KDM6 PSD boundary cases PASS'
END PROGRAM pr85_kdm6_psd_boundary_test
