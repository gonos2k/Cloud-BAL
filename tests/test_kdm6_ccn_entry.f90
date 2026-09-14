PROGRAM test_kdm6_ccn_entry
  USE module_mp_kdm6, ONLY: kdm6, kdm6init
  USE module_mp_radar, ONLY: xam_g
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  IMPLICIT NONE

  REAL, PARAMETER :: density_values(3) = [0.5, 1.0, 2.0]
  REAL, PARAMETER :: requested_ccn = 4.0e9
  REAL :: ccn_timestep1(3), ccn_timestep2(3)
  INTEGER :: case_index

  DO case_index = 1, SIZE(density_values)
    CALL run_case(density_values(case_index), ccn_timestep1(case_index), &
         ccn_timestep2(case_index))
  END DO

  WRITE(*,'(A)') 'KDM6 wrapper CCN entry regression passed'

CONTAINS

  SUBROUTINE run_case(density, ccn_timestep1, ccn_timestep2)
    REAL, INTENT(IN) :: density
    REAL, INTENT(OUT) :: ccn_timestep1, ccn_timestep2
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
    INTEGER :: itimestep
    REAL, PARAMETER :: halo_ccn = -777.0
    REAL, PARAMETER :: ccn0 = 2.0e8
    REAL, PARAMETER :: ccn_tolerance = 1.0e-5

    DO itimestep = 1, 2
      th = 273.15
      q = 0.0
      qc = 0.0
      qr = 0.0
      qi = 0.0
      qs = 0.0
      qg = 0.0
      nn = halo_ccn
      nn(1:3,1,0) = requested_ccn
      nc = 0.0
      ni = 0.0
      nr = 0.0
      ! A positive background graupel volume avoids the known zero-volume
      ! ProgB divide-by-zero while qg remains clear-air zero.
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

      ! kdm6init leaves the radar graupel mass coefficient to its caller.
      xam_g = ACOS(-1.0)*500.0/6.0
      CALL kdm6init(1.28, 1000.0, 100.0, 4190.0, 1846.4, ccn0, 0, .FALSE.)
      CALL kdm6(TH=th, Q=q, QC=qc, QR=qr, QI=qi, QS=qs, QG=qg, &
           NN=nn, NC=nc, NI=ni, NR=nr, BG=bg, DIAG_RHOG=diag_rhog, &
           DEN=den, PII=pii, P=p, DELZ=delz, DELT=1.0, G=9.81, &
           CPD=1004.5, CPV=1846.4, CCN0=ccn0, RD=287.04, RV=461.5, &
           T0C=273.15, EP1=0.608, EP2=0.622, QMIN=1.0e-12, &
           XLS=2.834e6, XLV0=2.5e6, XLF0=3.34e5, DEN0=1.28, DENR=1000.0, &
           SCALE_H=0.0, QNN_LAND_MULT=1.0, QNN_SEA_MULT=1.0, &
           NCMIN_LAND=10.0, NCMIN_SEA=10.0, CLIQ=4190.0, CICE=1846.4, &
           PSAT=610.78, XLAND=xland, RAIN=rain, RAINNCV=rainncv, &
           SNOW=snow, SNOWNCV=snowncv, SR=sr, REFL_10CM=refl_10cm, &
           DIAGFLAG=.FALSE., DO_RADAR_REF=0, GRAUPEL=graupel, &
           GRAUPELNCV=graupelncv, ITIMESTEP=itimestep, HAS_REQC=0, &
           HAS_REQI=0, HAS_REQS=0, RE_CLOUD=re_cloud, RE_ICE=re_ice, &
           RE_SNOW=re_snow, IDS=1, IDE=3, JDS=0, JDE=0, KDS=1, KDE=1, &
           IMS=0, IME=4, JMS=0, JME=0, KMS=1, KME=1, ITS=1, ITE=3, &
           JTS=0, JTE=0, KTS=1, KTE=1)

      IF (.NOT. ALL(ieee_is_finite(nn(1:3,1,0)))) ERROR STOP 1
      IF (MAXVAL(ABS(nn(1:3,1,0)-requested_ccn)) > &
          requested_ccn*ccn_tolerance) ERROR STOP 2
      ! Neither timestep may rewrite the non-interior storage halo.
      IF (nn(0,1,0) /= halo_ccn .OR. nn(4,1,0) /= halo_ccn) ERROR STOP 3

      IF (itimestep == 1) THEN
        ccn_timestep1 = nn(1,1,0)
      ELSE
        ccn_timestep2 = nn(1,1,0)
      END IF
    END DO

    IF (ABS(ccn_timestep1-ccn_timestep2) > requested_ccn*ccn_tolerance) &
         ERROR STOP 4
    WRITE(*,'(A,F4.1,A,ES12.4,A,ES12.4)') 'density=', density, &
         ' timestep1=', ccn_timestep1, ' timestep2=', ccn_timestep2
  END SUBROUTINE run_case

END PROGRAM test_kdm6_ccn_entry
