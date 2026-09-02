PROGRAM test_qbal_acceptance
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value, ieee_quiet_nan
  IMPLICIT NONE
  INTEGER, PARAMETER :: nx=2,ny=2,nz=1
  INTEGER :: failures,status
  EXTERNAL :: qbal_increment_maxima,qbal_candidate_acceptance,qbal_mark_valid_omega
  LOGICAL, EXTERNAL :: background_omega_complete
  REAL :: u0(nx,ny,nz),v0(nx,ny,nz),om0(nx,ny,nz)
  REAL :: u1(nx,ny,nz),v1(nx,ny,nz),om1(nx,ny,nz)
  REAL :: influence(nx,ny,nz),maxwind,maxomega,nan_value
  REAL :: omega_values(nx,ny,nz)
  REAL :: ps(nx,ny),p(nz)
  LOGICAL :: om_valid(nx,ny,nz),marked_valid(nx,ny,nz)

  failures=0
  u0=0.0; v0=0.0; om0=0.0
  u1=0.0; v1=0.0; om1=0.0
  influence=1.0
  u1(1,1,1)=8.0
  v1(1,1,1)=8.0
  om1(1,1,1)=4.0
  CALL qbal_increment_maxima(u0,v0,om0,u1,v1,om1,influence, &
       nx,ny,nz,maxwind,maxomega,status)
  CALL check(status==1 .AND. ABS(maxwind-SQRT(128.0))<1.0E-6, &
       'wind maximum must use horizontal vector magnitude',failures)
  CALL check(ABS(maxomega-4.0)<1.0E-6, &
       'omega maximum must be evaluated independently',failures)

  CALL accept(9.0,4.0,1.0E-4,2.0E-4,4.0E-4,8.0E-4, &
       8.0E-5,1.5E-4,1.0E-2,1.05E-2,status)
  CALL check(status==1,'candidate satisfying every gate must pass',failures)

  CALL accept(maxwind,4.0,1.0E-4,2.0E-4,4.0E-4,8.0E-4, &
       8.0E-5,1.5E-4,1.0E-2,1.05E-2,status)
  CALL check(status==0, &
       'diagonal increment above 10 m/s must fail',failures)

  CALL accept(9.0,5.1,1.0E-4,2.0E-4,4.0E-4,8.0E-4, &
       8.0E-5,1.5E-4,1.0E-2,1.05E-2,status)
  CALL check(status==0,'omega increment above 5 Pa/s must fail',failures)

  CALL accept(9.0,4.0,1.0E-3,1.0E-3,4.0E-4,8.0E-4, &
       1.1E-4,1.9E-4,1.0E-2,1.05E-2,status)
  CALL check(status==0, &
       'final continuity must reduce forced residual by 75 percent',failures)

  CALL accept(9.0,4.0,1.0E-5,2.0E-5,4.0E-4,8.0E-4, &
       2.0E-5,3.0E-5,1.0E-2,1.05E-2,status)
  CALL check(status==0, &
       'final continuity must not worsen background residual',failures)

  CALL accept(9.0,4.0,1.0E-4,2.0E-4,4.0E-4,8.0E-4, &
       8.0E-5,1.5E-4,1.0E-2,1.2E-2,status)
  CALL check(status==0,'geostrophic degradation must fail',failures)

  nan_value=ieee_value(0.0,ieee_quiet_nan)
  CALL accept(9.0,4.0,1.0E-4,2.0E-4,4.0E-4,8.0E-4, &
       nan_value,1.5E-4,1.0E-2,1.05E-2,status)
  CALL check(status==0,'non-finite metric must fail closed',failures)

  ps=90000.0; p=80000.0; om_valid=.TRUE.
  CALL check(background_omega_complete(om_valid,ps,p,nx,ny,nz), &
       'complete above-ground background omega must pass',failures)
  om_valid(1,1,1)=.FALSE.
  CALL check(.NOT.background_omega_complete(om_valid,ps,p,nx,ny,nz), &
       'missing above-ground background omega must fail',failures)
  p=100000.0
  CALL check(background_omega_complete(om_valid,ps,p,nx,ny,nz), &
       'below-ground background omega may remain invalid',failures)
  ps(1,1)=nan_value
  CALL check(.NOT.background_omega_complete(om_valid,ps,p,nx,ny,nz), &
       'non-finite surface pressure must fail the omega domain',failures)
  ps=90000.0; ps(1,1)=130000.0
  CALL check(.NOT.background_omega_complete(om_valid,ps,p,nx,ny,nz), &
       'out-of-range surface pressure must fail the omega domain',failures)

  omega_values=0.0; omega_values(1,1,1)=nan_value
  CALL qbal_mark_valid_omega(omega_values,marked_valid,nx,ny,nz)
  CALL check(.NOT.marked_valid(1,1,1) .AND. COUNT(marked_valid)==nx*ny*nz-1, &
       'omega validity conversion must reject NaN without FPE',failures)
  ps=90000.0; p=80000.0
  CALL check(.NOT.background_omega_complete(marked_valid,ps,p,nx,ny,nz), &
       'target-time omega refresh must reject newly missing OM',failures)

  IF (failures/=0) THEN
    PRINT *,'QBAL acceptance tests failed:',failures
    ERROR STOP 1
  END IF
  PRINT *,'QBAL acceptance tests passed'

CONTAINS

  SUBROUTINE accept(wind,omega,cb,cbmax,cf,cfmax,ci,cimax, &
                    gforced,gfinal,status)
    REAL, INTENT(IN) :: wind,omega,cb,cbmax,cf,cfmax,ci,cimax
    REAL, INTENT(IN) :: gforced,gfinal
    INTEGER, INTENT(OUT) :: status
    CALL qbal_candidate_acceptance(wind,omega,cb,cbmax,cf,cfmax, &
         ci,cimax,gforced,gfinal,status)
  END SUBROUTINE accept

  SUBROUTINE check(condition,message,failures)
    LOGICAL, INTENT(IN) :: condition
    CHARACTER(LEN=*), INTENT(IN) :: message
    INTEGER, INTENT(INOUT) :: failures
    IF (.NOT.condition) THEN
      failures=failures+1
      PRINT *,'FAIL: ',TRIM(message)
    END IF
  END SUBROUTINE check

END PROGRAM test_qbal_acceptance
