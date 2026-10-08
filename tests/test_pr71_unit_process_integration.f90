PROGRAM test_pr71_unit_process_integration
  USE module_mp_kdm6, ONLY: kdm6, kdm6init
  USE module_mp_kdm6, ONLY: fpvs
#ifdef TEST_CANDIDATE
  USE module_mp_kdm6, ONLY: moist_to_dry_density, specific_number_to_volume, volume_number_to_specific
#endif
  USE module_mp_radar, ONLY: xam_g
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
#ifdef TEST_CANDIDATE
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value, ieee_quiet_nan, ieee_next_after
#endif
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
#ifdef TEST_DIRECT_VOLUME
  LOGICAL, PARAMETER :: is_direct_volume = .TRUE.
#else
  LOGICAL, PARAMETER :: is_direct_volume = .FALSE.
#endif

#ifdef TEST_EOS_CONSISTENT
  REAL, PARAMETER :: density_values(1) = [1.0]
#elif defined(TEST_CANDIDATE) || defined(TEST_REFERENCE_O0) || defined(TEST_REFERENCE_ALL) || defined(TEST_DIRECT_VOLUME)
  REAL, PARAMETER :: density_values(4) = [0.25, 0.5, 1.0, 2.0]
#else
  REAL, PARAMETER :: density_values(3) = [0.5, 1.0, 2.0]
#endif
  REAL, PARAMETER :: pi = ACOS(-1.0)
  REAL, PARAMETER :: cloud_water = 2.0e-4, cloud_lambda = 1.0e5
  REAL, PARAMETER :: ice_water = 2.0e-5, ice_lambda = 2.0e4
  REAL, PARAMETER :: rain_water = 1.0e-4, rain_lambda = 5.0e3
  REAL, PARAMETER :: public_nn = 5.0e8
  REAL, PARAMETER :: public_nc = cloud_water*cloud_lambda**3/(pi*1000.0/6.0)
  REAL, PARAMETER :: public_ni = ice_water*ice_lambda**3/((pi*500.0/6.0)*6.0)
  ! The source rain intercept uses Gamma(1+dmr+mur) = Gamma(5) = 24.
  REAL, PARAMETER :: public_nr = rain_water*rain_lambda**3/((pi*1000.0/6.0)*24.0)
  INTEGER :: case_index

#ifdef TEST_CANDIDATE
  CALL check_unit_converter()
#endif

  DO case_index = 1, SIZE(density_values)
    CALL run_case(density_values(case_index))
  END DO

  IF (is_candidate) THEN
    WRITE(*,'(A)') 'KDM6_NUMBER_WRAPPER CANDIDATE PASS'
  ELSE IF (is_direct_volume) THEN
    WRITE(*,'(A)') 'KDM6_NUMBER_WRAPPER DIRECT_VOLUME PASS'
  ELSE IF (is_unscaled_reference) THEN
    WRITE(*,'(A)') 'KDM6_NUMBER_WRAPPER ORIGINAL_UNSCALED PASS'
  ELSE
    WRITE(*,'(A)') 'KDM6_NUMBER_WRAPPER ORIGINAL_SCALED PASS'
  END IF

CONTAINS

#ifdef TEST_CANDIDATE
  SUBROUTINE check_unit_converter()
    REAL :: per_m3, per_kg, nan_value, subnormal, dry_density
    INTEGER :: i
    LOGICAL :: valid

    nan_value = ieee_value(0.0, ieee_quiet_nan)
    CALL moist_to_dry_density(0.505, 0.01, dry_density, valid)
    IF (.NOT. valid .OR. dry_density /= 0.5) ERROR STOP 20
    CALL specific_number_to_volume(0.0, dry_density, per_m3, valid)
    IF (.NOT. valid .OR. per_m3 /= 0.0) ERROR STOP 21
    CALL volume_number_to_specific(0.0, dry_density, per_kg, valid)
    IF (.NOT. valid .OR. per_kg /= 0.0) ERROR STOP 22
    DO i=1,SIZE(density_values)
      CALL moist_to_dry_density(density_values(i)*1.01, 0.01, dry_density, valid)
      IF (.NOT. valid .OR. dry_density /= density_values(i)) ERROR STOP 23
      CALL specific_number_to_volume(public_nr, dry_density, per_m3, valid)
      IF (.NOT. valid .OR. per_m3 /= public_nr*density_values(i)) ERROR STOP 24
      CALL volume_number_to_specific(per_m3, dry_density, per_kg, valid)
      IF (.NOT. valid .OR. per_kg /= public_nr) ERROR STOP 25
    END DO
    CALL moist_to_dry_density(nan_value, 0.01, dry_density, valid)
    IF (valid) ERROR STOP 26
    CALL moist_to_dry_density(1.01, nan_value, dry_density, valid)
    IF (valid) ERROR STOP 27
    CALL specific_number_to_volume(nan_value, 1.0, per_m3, valid)
    IF (valid) ERROR STOP 28
    CALL specific_number_to_volume(public_nr, nan_value, per_m3, valid)
    IF (valid) ERROR STOP 29
    CALL specific_number_to_volume(HUGE(0.0), 2.0, per_m3, valid)
    IF (valid) ERROR STOP 30
    CALL volume_number_to_specific(HUGE(0.0), 0.25, per_kg, valid)
    IF (valid) ERROR STOP 31
    subnormal = ieee_next_after(0.0, 1.0)
    IF (subnormal <= 0.0) ERROR STOP 32
    CALL specific_number_to_volume(subnormal, 0.25, per_m3, valid)
    IF (valid) ERROR STOP 33
    CALL volume_number_to_specific(subnormal, 4.0, per_kg, valid)
    IF (valid) ERROR STOP 34
  END SUBROUTINE check_unit_converter
#endif

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
    REAL :: number_scale, output_scale, state_scale, dry_density, moist_density
    REAL :: saturation_pressure, vapor_saturation
    REAL, PARAMETER :: pressure_pa = 90000.0, temperature_k = 250.0
    REAL, PARAMETER :: gas_constant_dry = 287.04, epsilon_vapor = 0.622
    REAL :: values(23)
    INTEGER :: i

    state_scale = 1.0
#ifdef TEST_FIXED_VOLUME_STATE
    state_scale = 1.0/density
#endif
    IF (is_candidate .OR. is_unscaled_reference) THEN
      number_scale = state_scale
    ELSE
      number_scale = density*state_scale
    END IF
    IF (is_candidate) THEN
      output_scale = 1.0
    ELSE
      output_scale = 1.0/density
    END IF

    th = temperature_k
    ! A manufactured moist state exercises all three number channels.
    saturation_pressure = fpvs(temperature_k, 1, 287.04, 461.5, 1846.4, 4190.0, &
         1846.4, 2.5e6, 2.834e6, 610.78, 273.15)
#ifdef TEST_ABSENT_GRAUPEL
    ! Supersaturated vapor keeps the existing ice category active through its consumer.
    vapor_saturation = 1.2*epsilon_vapor*saturation_pressure/(pressure_pa-saturation_pressure)
#else
    vapor_saturation = 0.8*epsilon_vapor*saturation_pressure/(pressure_pa-saturation_pressure)
#endif
    q = vapor_saturation
#ifdef TEST_EOS_CONSISTENT
    ! Native DEN is moist gas density; derive dry carrier density from the same
    ! p/T/vapor state using rho_d=p/[Rd*T*(1+qv/epsilon)].
    dry_density = pressure_pa/(gas_constant_dry*temperature_k* &
         (1.0+vapor_saturation/epsilon_vapor))
#else
    dry_density = density
#endif
    moist_density = dry_density*(1.0+vapor_saturation)
#ifdef TEST_EOS_CONSISTENT
    IF (is_candidate .OR. is_unscaled_reference) THEN
      number_scale = state_scale
    ELSE
      number_scale = dry_density*state_scale
    END IF
    IF (is_candidate) THEN
      output_scale = 1.0
    ELSE
      output_scale = 1.0/dry_density
    END IF
#endif
    qc = 0.0
    qi = 0.0
    qr = 0.0
    qs = 0.0
    qg = 0.0
    bg = -777.0
    nc = -777.0
    ni = -777.0
    nr = -777.0
    nn = -777.0
    qc(1:3,1,0) = cloud_water*state_scale
    qi(1:3,1,0) = ice_water*state_scale
    qr(1:3,1,0) = rain_water*state_scale
    qs(1:3,1,0) = 2.0e-5*state_scale
    nc(1:3,1,0) = public_nc*number_scale
    ni(1:3,1,0) = public_ni*number_scale
    nr(1:3,1,0) = public_nr*number_scale
    nn(1:3,1,0) = public_nn*number_scale
#ifdef TEST_ABSENT_GRAUPEL
    ! Keep cloud/ice channels active, but avoid rain freezing to a new graupel pair.
    qr(1:3,1,0) = 0.0
    nr(1:3,1,0) = 0.0
    qg(1:3,1,0) = 0.0
    bg(1:3,1,0) = 0.0
#else
    ! Keep graupel mass and volume on the source 400 kg m-3 PSD interval.
    qg(1:3,1,0) = 2.0e-5*state_scale
    bg(1:3,1,0) = 5.0e-8*state_scale
#endif
    diag_rhog = -777.0
    den = 999.0
    den(1:3,1,0) = moist_density
    pii = 1.0
    p = pressure_pa
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

#ifndef TEST_ABSENT_GRAUPEL
    IF (.NOT. ALL(ieee_is_finite(nc(1:3,1,0))) .OR. &
        .NOT. ALL(ieee_is_finite(ni(1:3,1,0))) .OR. &
        .NOT. ALL(ieee_is_finite(nr(1:3,1,0)))) ERROR STOP 11
    IF (ANY(qc(1:3,1,0) > 0.0 .AND. nc(1:3,1,0) <= 0.0) .OR. &
        ANY(qi(1:3,1,0) > 0.0 .AND. ni(1:3,1,0) <= 0.0) .OR. &
        ANY(qr(1:3,1,0) > 0.0 .AND. nr(1:3,1,0) <= 0.0) .OR. &
        ANY(nn(1:3,1,0) <= 0.0)) THEN
      WRITE(*,*) 'INACTIVE_NUMBER', density, nc(1:3,1,0), ni(1:3,1,0), &
                 nr(1:3,1,0), nn(1:3,1,0)
      WRITE(*,*) 'STATE', th(1,1,0), q(1,1,0), qc(1,1,0), qi(1,1,0), qr(1,1,0)
      ERROR STOP 12
    END IF
#endif
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
#ifdef TEST_ABSENT_GRAUPEL
    IF (qg(1,1,0) /= 0.0 .OR. bg(1,1,0) /= 0.0 .OR. &
        diag_rhog(1,1,0) /= 0.0 .OR. graupel(1,0) /= 0.0 .OR. &
        graupelncv(1,0) /= 0.0 .OR. qr(1,1,0) /= 0.0 .OR. &
        nr(1,1,0) /= 0.0) ERROR STOP 40
#else
    IF (ABS(th(1,1,0)-temperature_k) <= 1.0e-4 .OR. &
        ABS(q(1,1,0)-vapor_saturation) <= 1.0e-7 .OR. &
        ABS(qc(1,1,0)-cloud_water*state_scale) <= 1.0e-7 .OR. &
        ABS(nr(1,1,0)*output_scale-public_nr*state_scale) <= 1.0e-3) ERROR STOP 36
    IF (ABS(bg(1,1,0)-5.0e-8*state_scale) <= 1.0e-10) ERROR STOP 38
#endif
    ! This integration oracle checks the returned state and units, not radii.
    WRITE(*,'(A,1X,ES24.16,1X,4(ES24.16,1X),23(ES24.16,1X))') &
         'INPUT', dry_density, public_nn*number_scale, public_nc*number_scale, &
         public_ni*number_scale, public_nr*number_scale, values
#ifdef TEST_EOS_CONSISTENT
    WRITE(*,'(A,1X,5(ES24.16,1X))') 'EOS_INPUT', pressure_pa, temperature_k, &
         vapor_saturation, dry_density, moist_density
#endif
  END SUBROUTINE run_case

END PROGRAM test_pr71_unit_process_integration
