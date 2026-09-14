PROGRAM test_kdm6_number_wrapper
  USE module_mp_kdm6, ONLY: kdm6, kdm6init
  USE module_mp_radar, ONLY: xam_g
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  IMPLICIT NONE

#ifdef TEST_CANDIDATE
  LOGICAL, PARAMETER :: is_candidate = .TRUE.
  LOGICAL, PARAMETER :: is_unscaled_reference = .FALSE.
#elif defined(TEST_ORIGINAL_UNSCALED)
  LOGICAL, PARAMETER :: is_candidate = .FALSE.
  LOGICAL, PARAMETER :: is_unscaled_reference = .TRUE.
#else
  LOGICAL, PARAMETER :: is_candidate = .FALSE.
  LOGICAL, PARAMETER :: is_unscaled_reference = .FALSE.
#endif

  REAL, PARAMETER :: density_values(3) = [0.5, 1.0, 2.0]
  REAL, PARAMETER :: public_nn = 5.0e8
  REAL, PARAMETER :: public_nc = 5.0e8
  REAL, PARAMETER :: public_ni = 4.0e3
  REAL, PARAMETER :: public_nr = 1.0e7
  INTEGER :: case_index

  DO case_index = 1, SIZE(density_values)
    CALL run_case(density_values(case_index))
  END DO

  IF (is_candidate) THEN
    WRITE(*,'(A)') 'KDM6_NUMBER_WRAPPER CANDIDATE PASS'
  ELSE IF (is_unscaled_reference) THEN
    WRITE(*,'(A)') 'KDM6_NUMBER_WRAPPER ORIGINAL_UNSCALED PASS'
  ELSE
    WRITE(*,'(A)') 'KDM6_NUMBER_WRAPPER ORIGINAL_SCALED PASS'
  END IF

CONTAINS

  SUBROUTINE run_case(density)
    REAL, INTENT(IN) :: density
    REAL :: th(0:4,1:1,0:0), q(0:4,1:1,0:0)
    REAL :: qc(0:4,1:1,0:0), qr(0:4,1:1,0:0)
    REAL :: qi(0:4,1:1,0:0), qs(0:4,1:1,0:0)
    REAL :: qg(0:4,1:1,0:0), nn(0:4,1:1,0:0)
    REAL :: nc(0:4,1:1,0:0), ni(0:4,1:1,0:0)
    REAL :: nr(0:4,1:1,0:0), bg(0:4,1:1,0:0)
    REAL :: diag_rhog(0:4,1:1,0:0)
    REAL :: den(0:4,1:1,0:0), pii(0:4,1:1,0:0)
    REAL :: p(0:4,1:1,0:0), delz(0:4,1:1,0:0)
    REAL :: xland(0:4,0:0), rain(0:4,0:0), rainncv(0:4,0:0)
    REAL :: snow(0:4,0:0), snowncv(0:4,0:0)
    REAL :: sr(0:4,0:0), graupel(0:4,0:0), graupelncv(0:4,0:0)
    REAL :: refl_10cm(0:4,1:1,0:0)
    REAL :: re_cloud(0:4,1:1,0:0), re_ice(0:4,1:1,0:0)
    REAL :: re_snow(0:4,1:1,0:0)
    REAL :: number_scale, output_scale
    REAL :: values(23)
    INTEGER :: i

    IF (is_candidate .OR. is_unscaled_reference) THEN
      number_scale = 1.0
    ELSE
      number_scale = density
    END IF
    IF (is_candidate) THEN
      output_scale = 1.0
    ELSE
      output_scale = 1.0/density
    END IF

    th = 250.0
    ! A manufactured moist state exercises all three number channels.
    q = 1.0e-2
    qc = 0.0
    qi = 0.0
    qr = 0.0
    qs = 0.0
    qg = 0.0
    nc = -777.0
    ni = -777.0
    nr = -777.0
    nn = -777.0
    qc(1:3,1,0) = 2.0e-4
    qi(1:3,1,0) = 2.0e-5
    qr(1:3,1,0) = 1.0e-4
    nc(1:3,1,0) = public_nc*number_scale
    ni(1:3,1,0) = public_ni*number_scale
    nr(1:3,1,0) = public_nr*number_scale
    nn(1:3,1,0) = public_nn*number_scale
    ! Keep the graupel volume positive while its mass remains zero.  This
    ! avoids the unrelated clear-air ProgB zero-volume divide-by-zero path.
    bg = 1.0e-12
    diag_rhog = -777.0
    den = 999.0
    den(1:3,1,0) = density
    pii = 1.0
    p = 90000.0
    delz = 100.0
    xland = 1.0
    rain = 0.0
    rainncv = 0.0
    snow = 0.0
    snowncv = 0.0
    sr = 0.0
    graupel = 0.0
    graupelncv = 0.0
    refl_10cm = -777.0
    re_cloud = -777.0
    re_ice = -777.0
    re_snow = -777.0

    xam_g = ACOS(-1.0)*500.0/6.0
    CALL kdm6init(1.28, 1000.0, 100.0, 4190.0, 1846.4, 2.0e8, 0, .FALSE.)
    CALL kdm6(TH=th, Q=q, QC=qc, QR=qr, QI=qi, QS=qs, QG=qg, &
         NN=nn, NC=nc, NI=ni, NR=nr, BG=bg, DIAG_RHOG=diag_rhog, &
         DEN=den, PII=pii, P=p, DELZ=delz, DELT=1.0, G=9.81, &
         CPD=1004.5, CPV=1846.4, CCN0=2.0e8, RD=287.04, RV=461.5, &
         T0C=273.15, EP1=0.608, EP2=0.622, QMIN=1.0e-12, &
         XLS=2.834e6, XLV0=2.5e6, XLF0=3.34e5, DEN0=1.28, DENR=1000.0, &
         SCALE_H=0.0, QNN_LAND_MULT=1.0, QNN_SEA_MULT=1.0, &
         NCMIN_LAND=10.0, NCMIN_SEA=10.0, CLIQ=4190.0, CICE=1846.4, &
         PSAT=610.78, XLAND=xland, RAIN=rain, RAINNCV=rainncv, &
         SNOW=snow, SNOWNCV=snowncv, SR=sr, REFL_10CM=refl_10cm, &
         DIAGFLAG=.FALSE., DO_RADAR_REF=0, GRAUPEL=graupel, &
         GRAUPELNCV=graupelncv, ITIMESTEP=2, HAS_REQC=1, &
         HAS_REQI=1, HAS_REQS=1, RE_CLOUD=re_cloud, RE_ICE=re_ice, &
         RE_SNOW=re_snow, IDS=1, IDE=3, JDS=0, JDE=0, KDS=1, KDE=1, &
         IMS=0, IME=4, JMS=0, JME=0, KMS=1, KME=1, ITS=1, ITE=3, &
         JTS=0, JTE=0, KTS=1, KTE=1)

    IF (.NOT. ALL(ieee_is_finite(nc(1:3,1,0))) .OR. &
        .NOT. ALL(ieee_is_finite(ni(1:3,1,0))) .OR. &
        .NOT. ALL(ieee_is_finite(nr(1:3,1,0)))) ERROR STOP 11
    IF (ANY(nc(1:3,1,0) <= 0.0) .OR. ANY(ni(1:3,1,0) <= 0.0) .OR. &
        ANY(nr(1:3,1,0) <= 0.0) .OR. ANY(nn(1:3,1,0) <= 0.0)) THEN
      WRITE(*,*) 'INACTIVE_NUMBER', density, nc(1:3,1,0), ni(1:3,1,0), &
                 nr(1:3,1,0), nn(1:3,1,0)
      WRITE(*,*) 'STATE', th(1,1,0), q(1,1,0), qc(1,1,0), qi(1,1,0), qr(1,1,0)
      ERROR STOP 12
    END IF
    IF (nc(0,1,0) /= -777.0 .OR. nc(4,1,0) /= -777.0 .OR. &
        ni(0,1,0) /= -777.0 .OR. ni(4,1,0) /= -777.0 .OR. &
        nr(0,1,0) /= -777.0 .OR. nr(4,1,0) /= -777.0 .OR. &
        nn(0,1,0) /= -777.0 .OR. nn(4,1,0) /= -777.0) ERROR STOP 13

    values = [th(1,1,0), q(1,1,0), qc(1,1,0), qi(1,1,0), qr(1,1,0), &
         qs(1,1,0), qg(1,1,0), nn(1,1,0)*output_scale, &
         nc(1,1,0)*output_scale, ni(1,1,0)*output_scale, &
         nr(1,1,0)*output_scale, bg(1,1,0), diag_rhog(1,1,0), &
         re_cloud(1,1,0), re_ice(1,1,0), re_snow(1,1,0), &
         rain(1,0), rainncv(1,0), snow(1,0), snowncv(1,0), sr(1,0), &
         graupel(1,0), graupelncv(1,0)]
    IF (.NOT. ALL(ieee_is_finite(values))) ERROR STOP 14
    IF (ANY(re_cloud(1:3,1,0) <= 2.51e-6) .OR. &
        ANY(re_cloud(1:3,1,0) >= 50.0e-6)) ERROR STOP 15
    ! Ice radius can reach its physical routine's floor in this fixture.
    ! Number outputs, not agreement at that floor, carry the ice oracle.
    DO i=2,3
      IF (nc(i,1,0) /= nc(1,1,0) .OR. ni(i,1,0) /= ni(1,1,0) .OR. &
          nr(i,1,0) /= nr(1,1,0)) ERROR STOP 17
    END DO

    WRITE(*,'(A,1X,F3.1,1X,4(ES24.16,1X),23(ES24.16,1X))') &
         'INPUT', density, public_nn*number_scale, public_nc*number_scale, &
         public_ni*number_scale, public_nr*number_scale, values
  END SUBROUTINE run_case

END PROGRAM test_kdm6_number_wrapper
