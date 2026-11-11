PROGRAM test_phase_consumer_native
  USE native_slope_test
  IMPLICIT NONE
  REAL :: q(1,1),n(1,1),den(1,1),denfac(1,1),t(1,1),rs(1,1),rb(1,1),r2(1,1),r3(1,1),rd(1,1)
  DOUBLE PRECISION :: rm(1,1),vt(1,1),vtn(1,1)
  REAL :: number
  q=1.1e-9; den=0.8; denfac=1.; t=280.
  number=den(1,1)*q(1,1)*5000.**3/pidnr
  n=number
  IF (number<=0. .OR. number>nrmin .OR. q(1,1)<=qcrmin) ERROR STOP 'witness setup'
  CALL run_slope()
  IF (rs(1,1)/=rslopermax .OR. n(1,1)/=number) ERROR STOP 'witness fallback'
  n=nrmin
  CALL run_slope()
  IF (rs(1,1)/=rslopermax .OR. n(1,1)/=nrmin) ERROR STOP 'number equality fallback'
  n=NEAREST(nrmin,1.0)
  CALL run_slope()
  IF (rs(1,1)==rslopermax .OR. n(1,1)/=NEAREST(nrmin,1.0)) ERROR STOP 'number active'
  q=qcrmin
  CALL run_slope()
  IF (rs(1,1)/=rslopermax) ERROR STOP 'mass equality fallback'
  q=NEAREST(qcrmin,1.0)
  CALL run_slope()
  IF (rs(1,1)==rslopermax) ERROR STOP 'mass active'
  PRINT *, 'native slope witness number m-3:',number,' fallback lambda:',1./rslopermax
  PRINT *, 'native slope equality and active branches: PASS'
CONTAINS
  SUBROUTINE run_slope()
    CALL slope_rain(q,n,den,denfac,t,rs,rb,r2,r3,rd,rm,vt,vtn,1,1,1,1)
  END SUBROUTINE run_slope
END PROGRAM test_phase_consumer_native
