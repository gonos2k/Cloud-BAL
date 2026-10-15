PROGRAM test_pr85_kdm6_rain_freezing_packet
USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64
IMPLICIT NONE
REAL(real32) :: qr,nr,qg,bg,qr2,nr2,qg2,bg2
REAL(real64) :: ma,na,va,theta,amin,amax
LOGICAL :: base_valid,accepted
EXTERNAL :: pr85_kdm6_rain_freezing_packet
amin=1.0e-12_real64; amax=1.0e-6_real64

! An empty graupel category receiving frozen rain has source density 1000,
! outside the retained ProgB density range 100..900. Defer all four moments.
qr=1.0e-2_real32; nr=1.0e6_real32; qg=0.0_real32; bg=0.0_real32
CALL apply(1.0e-4_real64,1.0e4_real64,1.0e-7_real64)
IF (.NOT.base_valid .OR. accepted .OR. theta/=0.0_real64) ERROR STOP 'unsupported density not deferred'
IF (qr2/=qr .OR. nr2/=nr .OR. qg2/=qg .OR. bg2/=bg) ERROR STOP 'unsupported packet changed state'
PRINT '(a)', 'CASE empty graupel density=1000 packet deferred atomically'

! Existing density-500 graupel can accept the same source mixture, whose
! combined density falls inside the strict source-supported interval.
qg=1.0e-4_real32; bg=2.0e-7_real32
CALL apply(1.0e-4_real64,1.0e4_real64,1.0e-7_real64)
IF (.NOT.base_valid .OR. .NOT.accepted .OR. theta/=1.0_real64) ERROR STOP 'supported mixture not accepted'
IF (qr2>=qr .OR. nr2>=nr .OR. qg2<=qg .OR. bg2<=bg) ERROR STOP 'full packet not stored'
IF (ABS(REAL(qg2,real64)/REAL(bg2,real64)-666.6666666667_real64)>0.1_real64) &
  ERROR STOP 'mixture density incorrect'
PRINT '(a)', 'CASE supported graupel mixture accepts paired rain-freezing packet'

! A denser source packet is limited by the existing graupel density cone.
qg=1.0e-4_real32; bg=1.25e-7_real32
CALL apply(2.5e-4_real64,2.5e4_real64,2.5e-7_real64)
IF (.NOT.base_valid .OR. .NOT.accepted) ERROR STOP 'density-limited mixture rejected'
IF (theta<=0.49_real64 .OR. theta>0.5_real64) ERROR STOP 'density limiter fraction incorrect'
IF (REAL(qg2,real64)/REAL(bg2,real64)>900.0_real64) &
  ERROR STOP 'density limiter endpoint incorrect'
IF (qr2>=qr .OR. nr2>=nr .OR. qg2<=qg .OR. bg2<=bg) ERROR STOP 'density limited packet not paired'
PRINT '(a)', 'CASE existing graupel density limits shared packet fraction'

! Invalid pre-existing density must fail validation without mutation.
qg=1.0e-4_real32; bg=1.0e-7_real32
CALL apply(1.0e-4_real64,1.0e4_real64,1.0e-7_real64)
IF (base_valid .OR. accepted) ERROR STOP 'invalid base accepted'
IF (qr2/=qr .OR. nr2/=nr .OR. qg2/=qg .OR. bg2/=bg) ERROR STOP 'invalid base changed state'
PRINT '(a)', 'CASE invalid pre-existing graupel density rejected atomically'

! One missing paired request cannot proceed as a mass-only or number-only transfer.
qg=0.0_real32; bg=0.0_real32
CALL apply(1.0e-4_real64,0.0_real64,1.0e-7_real64)
IF (.NOT.base_valid .OR. accepted) ERROR STOP 'mass-only request accepted'
IF (qr2/=qr .OR. nr2/=nr .OR. qg2/=qg .OR. bg2/=bg) ERROR STOP 'mass-only state changed'
CALL apply(0.0_real64,1.0e4_real64,0.0_real64)
IF (.NOT.base_valid .OR. accepted) ERROR STOP 'number-only request accepted'
IF (qr2/=qr .OR. nr2/=nr .OR. qg2/=qg .OR. bg2/=bg) ERROR STOP 'number-only state changed'
PRINT '(a)', 'CASE unpaired proposals rejected atomically'

! Bad receiver volume ratio and nonfinite inputs are rejected atomically.
CALL apply(1.0e-4_real64,1.0e4_real64,0.0_real64)
IF (.NOT.base_valid .OR. accepted) ERROR STOP 'zero volume accepted'
CALL pr85_kdm6_rain_freezing_packet(qr,nr,qg,bg,0.0_real32, &
  1.0e-4_real64,1.0e4_real64,1.0e-7_real64,amin,amax,100.0_real64,900.0_real64, &
  qr2,nr2,qg2,bg2,ma,na,va,theta,base_valid,accepted)
IF (base_valid .OR. accepted) ERROR STOP 'invalid density accepted'
PRINT '(a)', 'CASE invalid carrier/volume rejected'
PRINT '(a)', 'PR85 KDM6 rain-freezing packet cases PASS'

CONTAINS
SUBROUTINE apply(mass,number,volume)
REAL(real64), INTENT(IN) :: mass,number,volume
CALL pr85_kdm6_rain_freezing_packet(qr,nr,qg,bg,1.0_real32, &
  mass,number,volume,amin,amax,100.0_real64,900.0_real64, &
  qr2,nr2,qg2,bg2,ma,na,va,theta,base_valid,accepted)
END SUBROUTINE apply
END PROGRAM test_pr85_kdm6_rain_freezing_packet
