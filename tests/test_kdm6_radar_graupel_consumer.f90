PROGRAM test_kdm6_radar_graupel_consumer
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  USE module_mp_kdm6, ONLY: kdm6init, ProgB_param, refl10cm_kdm6, pi, &
       g1pdgmg, g1pmg, n0g, rslopegmax
  USE module_mp_radar, ONLY: global_xam_g=>xam_g
  IMPLICIT NONE

  INTEGER, PARAMETER :: ncolumn=3, nlevel=3
  REAL :: qrs(ncolumn,nlevel,3), brs(ncolumn,nlevel), rhox(ncolumn,nlevel)
  REAL :: cmg(ncolumn,nlevel), pidn0g(ncolumn,nlevel)
  REAL :: avtg(ncolumn,nlevel), pvtg(ncolumn,nlevel), precg2(ncolumn,nlevel)
  REAL :: bvtg(ncolumn,nlevel), bvtg1(ncolumn,nlevel), bvtg2(ncolumn,nlevel)
  REAL :: bvtg3(ncolumn,nlevel), bvtg4(ncolumn,nlevel)
  REAL :: rslopegbmax(ncolumn,nlevel), g1pbg(ncolumn,nlevel)
  REAL :: g3pbg(ncolumn,nlevel), g4pbg(ncolumn,nlevel), g5pbgo2(ncolumn,nlevel)
  REAL :: g1pdgbgmg(ncolumn,nlevel), dgbgmug1(ncolumn,nlevel)
  INTEGER :: progb_status(ncolumn,nlevel)
  REAL :: qv(nlevel), qr(nlevel), nr(nlevel), qs(nlevel), qg(nlevel)
  REAL :: n0so(nlevel), n0go(nlevel), temperature(nlevel), pressure(nlevel)
  REAL :: dbz(nlevel), wet_dbz(ncolumn), level_mass_coefficient(nlevel)
  REAL :: expected_a_200, expected_a_700
  INTEGER :: column

  qrs=0.0
  brs=0.0
  rhox=0.0
  cmg=0.0
  pidn0g=0.0
  avtg=0.0
  pvtg=0.0
  precg2=0.0
  bvtg=0.0
  bvtg1=0.0
  bvtg2=0.0
  bvtg3=0.0
  bvtg4=0.0
  rslopegbmax=0.0
  g1pbg=0.0
  g3pbg=0.0
  g4pbg=0.0
  g5pbgo2=0.0
  g1pdgbgmg=0.0
  dgbgmug1=0.0

  ! Use WRF's model constants and KDM6 initializer before generating state.
  IF (global_xam_g/=0.0) ERROR STOP 10
  CALL kdm6init(1.28,1000.0,100.0,4190.0,4.0*461.6,0.0,0,.TRUE.)
  IF (global_xam_g/=0.0) ERROR STOP 22
  CALL kdm6init(1.28,1000.0,100.0,4190.0,4.0*461.6,0.0,0,.TRUE.)
  IF (global_xam_g/=0.0) ERROR STOP 23

  ! Two real graupel states share QG but have different QG/BG densities.
  qrs(1:2,2,3)=1.0e-4
  qrs(1:2,3,3)=1.2e-4
  brs(1,2)=qrs(1,2,3)/200.0
  brs(2,2)=qrs(2,2,3)/700.0
  brs(1:2,3)=qrs(1:2,3,3)/400.0

  CALL ProgB_param(brs,qrs,rhox,1,ncolumn,1,1,1,nlevel,1.0e-9, &
       3.0,0.0,cmg,pi,pidn0g,g1pdgmg,g1pmg,n0g,avtg,pvtg,precg2, &
       bvtg,bvtg1,bvtg2,bvtg3,bvtg4,rslopegbmax,rslopegmax, &
       g1pbg,g3pbg,g4pbg,g5pbgo2,g1pdgbgmg,dgbgmug1,progb_status)

  expected_a_200=pi*200.0/6.0
  expected_a_700=pi*700.0/6.0
  IF (ABS(rhox(1,2)-200.0)>1.0e-3 .OR. ABS(rhox(2,2)-700.0)>1.0e-3) ERROR STOP 11
  IF (ABS(cmg(1,2)-expected_a_200)>1.0e-4 .OR. &
      ABS(cmg(2,2)-expected_a_700)>1.0e-4) ERROR STOP 12
  IF (ANY(cmg(3,:)/=0.0)) ERROR STOP 13

  ! KDM6 initialization leaves global graupel a_g unset; state-local cmg is used.
  IF (global_xam_g/=0.0) ERROR STOP 14

  qv=0.003
  qr=0.0
  nr=0.0
  qr(2)=1.0e-4
  nr(2)=1.0e6
  qs=0.0
  n0so=2.0e6
  n0go=4.0e6
  temperature=[270.0,275.0,270.0]
  pressure=80000.0
  DO column=1,ncolumn
    qg=qrs(column,:,3)
    level_mass_coefficient=cmg(column,:)
    CALL refl10cm_kdm6(qv,qr,nr,qs,qg,n0so,n0go,temperature,pressure, &
         dbz,1,nlevel,column,1,level_mass_coefficient)
    IF (.NOT.ALL(ieee_is_finite(dbz))) ERROR STOP 15
    IF (ANY(ABS(dbz)>200.0)) ERROR STOP 16
    wet_dbz(column)=dbz(2)
    IF (column==1) THEN
      IF (.NOT.ALL(ieee_is_finite(dbz))) ERROR STOP 18
      IF (ANY(ABS(level_mass_coefficient([2,3]))<1.0)) ERROR STOP 19
    END IF
  END DO

  IF (cmg(1,2)==cmg(2,2)) ERROR STOP 20
  IF (ABS(wet_dbz(1)-wet_dbz(2))<1.0e-3) ERROR STOP 21
  WRITE(*,'(A,2(1X,ES16.8),2(1X,ES16.8))') 'KDM6_RADAR_CONSUMER_PASS', &
       cmg(1,2),cmg(2,2),wet_dbz(1),wet_dbz(2)
END PROGRAM test_kdm6_radar_graupel_consumer
