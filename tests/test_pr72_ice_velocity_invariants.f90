PROGRAM test_pr72_ice_velocity_invariants
  USE module_mp_kdm6, ONLY: kdm6init, slope_kdm6
  USE module_mp_radar, ONLY: xam_g
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  IMPLICIT NONE
  INTEGER, PARAMETER :: its=12, ite=14, kts=7, kte=9
  REAL, PARAMETER :: pi=ACOS(-1.0), qmin=1.0e-15
  REAL, PARAMETER :: lambda_cases(4)=[1.0e3,9.08e3,1.82e6,1.0e8]
  REAL, PARAMETER :: lambda_expected(4)=[1.0/9.08e3,1.0/9.08e3,1.0/1.82e6,1.0/1.82e6]
  REAL :: qrs(0:4,0:4,3), qci(0:4,0:4), nrs(0:4,0:4), nci(0:4,0:4)
  REAL :: den(0:4,0:4), denfac(0:4,0:4), t(0:4,0:4)
  REAL :: rslope(0:4,0:4,4), rslopeb(0:4,0:4,4)
  REAL :: rslope2(0:4,0:4,4), rslope3(0:4,0:4,4)
  REAL :: rsloped(0:4,0:4,4), pidn0g(0:4,0:4)
  REAL :: pvtg(0:4,0:4), bvtg(0:4,0:4), rslopegbmax(0:4,0:4)
  REAL(KIND=8) :: rslopemu(0:4,0:4,4), vt(0:4,0:4,4), vtn(0:4,0:4,2)
  INTEGER :: progb_status(0:4,0:4), case_index
  REAL :: expected_slope, ice_lambda, number_scale
  REAL(KIND=8), PARAMETER :: poison=-773.0_8

  xam_g=pi*500.0/6.0
  CALL kdm6init(1.28,1000.0,100.0,4190.0,1846.4,1.0e8,0,.FALSE.)
  qrs=0.0; qci=0.0; nrs=0.0; nci=0.0
  den=1.0; denfac=1.0; t=260.0
  pidn0g=0.0; pvtg=0.0; bvtg=0.0; rslopegbmax=0.0
  progb_status=0 ! PROGB_ABSENT is the source module's private value.

  ! Active ice remains valid under absent graupel and preserves the source coefficient relation.
  DO case_index=1,SIZE(lambda_cases)
    ice_lambda=lambda_cases(case_index)
    qci(2,2)=1.0e-3
    number_scale=(qci(2,2)*ice_lambda**3)/((pi*500.0/6.0)*6.0)
    nci(2,2)=number_scale
    CALL poison_outputs()
    CALL evaluate()
    expected_slope=MAX(MIN(1.0/ice_lambda,1.0/9.08e3),1.0/1.82e6)
    IF (ABS(rslope(2,2,4)-expected_slope)>2.0e-6*expected_slope) ERROR STOP 11
    IF (.NOT.ieee_is_finite(vt(2,2,4)) .OR. .NOT.ieee_is_finite(vtn(2,2,2))) ERROR STOP 12
    IF (vt(2,2,4)<=0.0_8 .OR. vtn(2,2,2)<=0.0_8) ERROR STOP 13
    IF (ABS(vt(2,2,4)-4.0_8*vtn(2,2,2))>1.0e-10_8) ERROR STOP 14
    CALL check_inactive_neighbors()
    CALL check_halos()
  END DO

  ! Transition the same active cell to absent ice after poisoning every output.
  qci(2,2)=0.0; nci(2,2)=0.0
  CALL poison_outputs()
  CALL evaluate()
  expected_slope=1.0/1.82e6
  IF (ANY(.NOT.ieee_is_finite(rslope(2,2,4:4)))) ERROR STOP 21
  IF (ABS(rslope(2,2,4)-expected_slope)>1.0e-12*expected_slope .OR. &
      ABS(rslopeb(2,2,4)-expected_slope)>1.0e-12*expected_slope) ERROR STOP 22
  IF (rslopemu(2,2,4)/=1.0_8) ERROR STOP 23
  IF (ABS(rslope2(2,2,4)-expected_slope**2)>1.0e-12*expected_slope**2 .OR. &
      ABS(rslope3(2,2,4)-expected_slope**3)>1.0e-12*expected_slope**3 .OR. &
      ABS(rsloped(2,2,4)-expected_slope**3)>1.0e-12*expected_slope**3) ERROR STOP 24
  IF (vt(2,2,4)/=0.0_8 .OR. vtn(2,2,2)/=0.0_8 .OR. vtn(2,2,1)/=0.0_8) ERROR STOP 25
  CALL check_halos()
  WRITE(*,'(A)') 'PR72_ICE_VELOCITY_INVARIANTS PASS'

CONTAINS

  SUBROUTINE poison_outputs()
    rslope=-777.0; rslopeb=-778.0; rslope2=-779.0; rslope3=-780.0
    rslopemu=-781.0_8; rsloped=-782.0; vt=-783.0_8; vtn=-784.0_8
  END SUBROUTINE poison_outputs

  SUBROUTINE evaluate()
    CALL slope_kdm6(qrs(1:3,1:3,:),qci(1:3,1:3),nrs(1:3,1:3),nci(1:3,1:3), &
         den(1:3,1:3),denfac(1:3,1:3),t(1:3,1:3),rslope(1:3,1:3,:), &
         rslopeb(1:3,1:3,:),rslope2(1:3,1:3,:),rslope3(1:3,1:3,:), &
         rslopemu(1:3,1:3,:),rsloped(1:3,1:3,:),vt(1:3,1:3,:),vtn(1:3,1:3,:), &
         its,ite,kts,kte,qmin,pidn0g(1:3,1:3),pvtg(1:3,1:3),bvtg(1:3,1:3), &
         rslopegbmax(1:3,1:3),progb_status(1:3,1:3))
  END SUBROUTINE evaluate

  SUBROUTINE check_halos()
    INTEGER :: i,j
    DO j=0,4
      DO i=0,4
        IF (i>=1 .AND. i<=3 .AND. j>=1 .AND. j<=3) CYCLE
        IF (ANY(rslope(i,j,:)/=-777.0) .OR. ANY(rslopeb(i,j,:)/=-778.0) .OR. &
            ANY(rslope2(i,j,:)/=-779.0) .OR. ANY(rslope3(i,j,:)/=-780.0) .OR. &
            ANY(rsloped(i,j,:)/=-782.0) .OR. ANY(rslopemu(i,j,:)/=-781.0_8) .OR. &
            ANY(vt(i,j,:)/=-783.0_8) .OR. ANY(vtn(i,j,:)/=-784.0_8)) ERROR STOP 31
      END DO
    END DO
  END SUBROUTINE check_halos

  SUBROUTINE check_inactive_neighbors()
    INTEGER :: i,j
    DO j=1,3
      DO i=1,3
        IF (i==2 .AND. j==2) CYCLE
        IF (rslope(i,j,4)/=1.0/1.82e6 .OR. rslopeb(i,j,4)/=1.0/1.82e6 .OR. &
            rslopemu(i,j,4)/=1.0_8 .OR. vt(i,j,4)/=0.0_8 .OR. &
            vtn(i,j,1)/=0.0_8 .OR. vtn(i,j,2)/=0.0_8) ERROR STOP 32
      END DO
    END DO
  END SUBROUTINE check_inactive_neighbors
END PROGRAM test_pr72_ice_velocity_invariants
