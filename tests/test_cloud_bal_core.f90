PROGRAM test_cloud_bal_core
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value, ieee_quiet_nan
  USE cloud_bal_field_contracts
  USE cloud_bal_moisture
  USE cloud_bal_cloud_profiles
  USE cloud_bal_localization
  USE cloud_bal_radar_downdraft
  USE cloud_bal_wind_modes
  IMPLICIT NONE

  INTEGER :: failures

  failures = 0
  CALL test_field_contract(failures)
  CALL test_moisture(failures)
  CALL test_cloud_profiles(failures)
  CALL test_localization(failures)
  CALL test_radar_downdraft(failures)
  CALL test_wind_modes(failures)

  IF (failures /= 0) THEN
    PRINT *, 'Cloud-BAL core unit tests failed:', failures
    ERROR STOP 1
  END IF
  PRINT *, 'Cloud-BAL core unit tests passed'

CONTAINS

  SUBROUTINE check(condition, message, failures)
    LOGICAL, INTENT(IN) :: condition
    CHARACTER(LEN=*), INTENT(IN) :: message
    INTEGER, INTENT(INOUT) :: failures

    IF (.NOT. condition) THEN
      failures = failures + 1
      PRINT *, 'FAIL: ', TRIM(message)
    END IF
  END SUBROUTINE check

  SUBROUTINE check_close(actual, expected, tolerance, message, failures)
    REAL, INTENT(IN) :: actual, expected, tolerance
    CHARACTER(LEN=*), INTENT(IN) :: message
    INTEGER, INTENT(INOUT) :: failures

    CALL check(ABS(actual-expected) <= tolerance, message, failures)
  END SUBROUTINE check_close

  SUBROUTINE test_field_contract(failures)
    INTEGER, INTENT(INOUT) :: failures
    TYPE(field_contract) :: field
    REAL :: values(2,2,2)
    REAL :: surface(2,2), levels(3)

    CALL initialize_field_contract(field, 'rain', '261230000', &
         'kg/meter**3', 2, 2, 2, SOURCE_RADAR_3D)
    CALL check(contract_metadata_ok(field, '261230000', 'kg/meter**3', &
         2, 2, 2), 'field metadata should match', failures)
    CALL check(.NOT. contract_metadata_ok(field, '261230100', &
         'kg/meter**3', 2, 2, 2), 'valid time mismatch must fail', failures)

    values = 0.5
    values(1,1,1) = -1.0
    values(2,1,1) = ieee_value(0.0, ieee_quiet_nan)
    values(1,2,1) = 1.0E37
    CALL capture_field_validity(field, values, 0, 0.0, 100.0, 1.0E37)
    CALL check(field%status == FIELD_DEGRADED, &
         'partial validity must be degraded', failures)
    CALL check(COUNT(field%valid) == 5, &
         'negative, NaN, and missing cells must be invalid', failures)
    CALL check_close(valid_fraction(field), 0.625, 1.0E-6, &
         'valid fraction should be cell based', failures)

    surface = 1.0
    surface(2,2) = -1.0
    CALL initialize_field_contract(field, 'snow_cover', '261230000', &
         '1', 2, 2, 1, SOURCE_MODEL)
    CALL capture_field_validity(field, surface, 0, 0.0, 1.0, 1.0E37)
    CALL check(field%status == FIELD_DEGRADED .AND. &
         COUNT(field%valid) == 3, '2-D validity mask', failures)

    levels = (/1000.0,850.0,700.0/)
    CALL initialize_field_contract(field, 'pressure', '261230000', &
         'hPa', 3, 1, 1, SOURCE_MODEL)
    CALL capture_field_validity(field, levels, 0, 1.0, 1100.0, 1.0E37)
    CALL check(field%status == FIELD_OK, '1-D validity mask', failures)

    field%valid = .TRUE.
    CALL refresh_field_status(field)
    CALL check(field%status == FIELD_OK, &
         'all-valid field must be OK', failures)
    field%valid = .FALSE.
    CALL refresh_field_status(field)
    CALL check(field%status == FIELD_FAILED, &
         'all-invalid field must fail', failures)
  END SUBROUTINE test_field_contract

  SUBROUTINE test_moisture(failures)
    INTEGER, INTENT(INOUT) :: failures
    INTEGER :: status
    REAL :: vapor, condensate, source, sink, before
    REAL :: rain, snow, graupel

    vapor = 0.010
    condensate = 0.005
    before = vapor + condensate
    CALL evaporate_to_target(vapor, condensate, 0.012, status)
    CALL check(status == 1, 'evaporation should succeed', failures)
    CALL check_close(vapor, 0.012, 1.0E-7, &
         'vapor should reach target', failures)
    CALL check_close(vapor+condensate, before, 1.0E-7, &
         'evaporation must conserve water', failures)

    source = 0.004
    sink = 0.002
    before = source + sink
    CALL transfer_excess(source, sink, 0.001, status)
    CALL check(status == 1, 'cap transfer should succeed', failures)
    CALL check_close(source, 0.001, 1.0E-7, &
         'source should be capped', failures)
    CALL check_close(source+sink, before, 1.0E-7, &
         'cap transfer must conserve water', failures)

    CALL allocate_precipitation(0.01, 268.15, 0, rain, snow, graupel, status)
    CALL check(status == 1, 'mixed precipitation allocation should succeed', &
         failures)
    CALL check_close(rain+snow+graupel, 0.01, 1.0E-7, &
         'precipitation phases must close', failures)
    CALL allocate_precipitation(0.01, 268.15, 99, rain, snow, graupel, status)
    CALL check(status == 0, 'unknown phase must fail', failures)
  END SUBROUTINE test_moisture

  SUBROUTINE test_cloud_profiles(failures)
    INTEGER, INTENT(INOUT) :: failures
    INTEGER :: cloud_type(10), bottom(10), top(10), n_layers, status, k
    REAL :: height(10), w(10), bad_height(10), missing
    REAL :: coarse_amplitude,fine_amplitude,capped_amplitude

    missing = 1.0E37
    cloud_type = (/0,3,3,0,4,4,4,4,0,2/)
    DO k = 1, 10
      height(k) = REAL(k-1) * 1000.0
    END DO

    CALL detect_cloud_layers(cloud_type, 10, n_layers, bottom, top, status)
    CALL check(status == 1 .AND. n_layers == 3, &
         'all cloud layers should be detected', failures)
    CALL check(bottom(3) == 10 .AND. top(3) == 10, &
         'top-boundary layer must close at nk', failures)

    CALL build_multilayer_w_profile(2.0, cloud_type, height, 0.01, 0.005, &
         0.05, missing, w, status)
    CALL check(status == 1, 'valid cloud profile should succeed', failures)
    CALL check(w(2) > 0.0 .AND. w(3) > 0.0, &
         'convective layer should ascend', failures)
    CALL check(w(6) < 0.0 .AND. w(7) > 0.0, &
         'precipitating layer should contain descent and ascent', failures)
    CALL check(w(1) > 0.99*missing .AND. w(9) > 0.99*missing, &
         'clear levels must retain the missing marker', failures)
    CALL check(w(10) > 0.0 .AND. w(10) < missing, &
         'single top-boundary cloud should receive a finite profile', failures)

    coarse_amplitude=scale_aware_cloud_amplitude(10000.0,10000.0, &
         0.5,1.0,1.0,5.0)
    fine_amplitude=scale_aware_cloud_amplitude(10000.0,2000.0, &
         0.5,1.0,1.0,5.0)
    capped_amplitude=scale_aware_cloud_amplitude(10000.0,250.0, &
         0.5,1.0,1.0,5.0)
    CALL check(fine_amplitude > coarse_amplitude, &
         'resolved cloud w should increase as grid spacing decreases',failures)
    CALL check_close(capped_amplitude,5.0,1.0E-6, &
         'scale-aware cloud w must respect its resolved cap',failures)

    bad_height = height
    bad_height(5) = bad_height(4)
    CALL build_multilayer_w_profile(2.0, cloud_type, bad_height, 0.01, &
         0.005, 0.05, missing, w, status)
    CALL check(status == 0, 'non-monotone height must fail', failures)
  END SUBROUTINE test_cloud_profiles

  SUBROUTINE test_localization(failures)
    INTEGER, INTENT(INOUT) :: failures
    LOGICAL :: source(7,7,3)
    REAL :: pressure(3), dx(7,7), dy(7,7), beta(7,7,3)
    INTEGER :: status

    source = .FALSE.
    source(4,4,2) = .TRUE.
    pressure = (/90000.0,75000.0,60000.0/)
    dx = 10000.0
    dy = 10000.0
    CALL build_compact_influence_3d(source,pressure,dx,dy,20000.0, &
         20000.0,beta,status)
    CALL check(status == 1, 'compact influence should succeed', failures)
    CALL check_close(beta(4,4,2),1.0,0.0, &
         'source influence must be exactly one',failures)
    CALL check(beta(5,4,2) > 0.0 .AND. beta(5,4,2) < 1.0, &
         'inside compact radius must be tapered',failures)
    CALL check_close(beta(6,4,2),0.0,0.0, &
         'outside compact radius must be exactly zero',failures)
    CALL check(wendland_c2(0.99) < 1.0E-6 .AND. &
         ABS(wendland_c2(1.0)) < TINY(1.0), &
         'C2 taper must approach its compact edge smoothly',failures)
    CALL check(beta(4,4,1) > 0.0 .AND. beta(4,4,1) < 1.0, &
         'pressure support must also be compact',failures)
    source = .FALSE.
    CALL build_compact_influence_3d(source,pressure,dx,dy,20000.0, &
         20000.0,beta,status)
    CALL check(status == 2 .AND. MAXVAL(ABS(beta)) < TINY(1.0), &
         'no observations must produce no influence',failures)
  END SUBROUTINE test_localization

  SUBROUTINE test_radar_downdraft(failures)
    INTEGER, INTENT(INOUT) :: failures
    INTEGER, PARAMETER :: nx=5,ny=5,nz=4
    REAL, PARAMETER :: missing=1.0E37
    REAL :: dbz(nx,ny,nz),tk(nx,ny,nz),rh(nx,ny,nz)
    REAL :: height(nx,ny,nz),pressure(nx,ny,nz),u(nx,ny,nz),v(nx,ny,nz)
    REAL :: rain(nx,ny,nz),snow(nx,ny,nz),graupel(nx,ny,nz)
    REAL :: rain2(nx,ny,nz),snow2(nx,ny,nz),graupel2(nx,ny,nz)
    REAL :: omega(nx,ny,nz),omega2(nx,ny,nz),rain_before(nx,ny,nz)
    REAL :: bad_pressure(nx,ny,nz),dbz2(nx,ny,nz),speed30,speed40
    INTEGER :: types(nx,ny,nz),types2(nx,ny,nz),bad_types(nx-1,ny,nz)
    INTEGER :: status,status2,i,j,k
    LOGICAL :: support(nx,ny,nz),support2(nx,ny,nz)
    TYPE(radar_downdraft_config) :: cfg

    dbz=missing; tk=275.0; rh=70.0; u=10.0; v=0.0
    rain=0.0; snow=0.0; graupel=0.0; omega=missing; types=0
    DO k=1,nz
      DO j=1,ny
        DO i=1,nx
          height(i,j,k)=1000.0*REAL(k-1)
          pressure(i,j,k)=100000.0-10000.0*REAL(k-1)
        END DO
      END DO
    END DO
    dbz(2,3,4)=35.0
    rain(2,3,4)=2.0E-4
    omega(2,3,4)=0.0
    types(2,3,4)=16+4
    rain_before=rain
    rain2=rain; snow2=snow; graupel2=graupel; omega2=omega

    CALL couple_radar_precipitation(dbz,tk,rh,height,pressure,u,v, &
         1000.0,1000.0,missing,types,.TRUE.,rain,snow,graupel,omega, &
         support,status)
    CALL check(status == 1 .OR. status == 2, &
         'radar downdraft should return a usable field',failures)
    CALL check_close(rain(2,3,4),rain_before(2,3,4),0.0, &
         'observed precipitation must remain immutable',failures)
    CALL check(SUM(rain(:,:,3)) > 0.0 .AND. rain(3,3,3) > 0.0, &
         'lower gap must follow the wind/fall characteristic',failures)
    CALL check(ABS(rain(1,1,3)) < TINY(1.0), &
         'off-trajectory precipitation must remain zero',failures)
    CALL check(ANY(omega > 0.0 .AND. omega < 100.0), &
         'downward air motion must map to positive omega',failures)
    CALL check(ANY(support), 'radar/hydrometeor support must be exposed', &
         failures)

    CALL couple_radar_precipitation(dbz,tk,rh,height,pressure,u,v, &
         1000.0,1000.0,missing,types,.TRUE.,rain2,snow2,graupel2,omega2, &
         support2,status2)
    CALL check(status2 == status .AND. &
         MAXVAL(ABS(rain2-rain)) < 1.0E-12 .AND. &
         MAXVAL(ABS(omega2-omega),MASK=omega < 100.0) < 1.0E-12, &
         'radar coupling must be deterministic',failures)

    speed30=phase_terminal_velocity(1,80000.0,273.15,30.0,status)
    speed40=phase_terminal_velocity(1,80000.0,273.15,40.0,status2)
    CALL check(status == 1 .AND. status2 == 1 .AND. speed40 > speed30, &
         'fall speed must use increasing linear reflectivity',failures)

    cfg%storm_motion_available=.TRUE.
    rain2=rain_before; snow2=0.0; graupel2=0.0; omega2=missing
    omega2(2,3,4)=0.0
    CALL couple_radar_precipitation(dbz,tk,rh,height,pressure,u,v, &
         1000.0,1000.0,missing,types,.TRUE.,rain2,snow2,graupel2,omega2, &
         support2,status2,cfg)
    CALL check(status2 == 2, &
         'missing trajectory omega must use an explicit degraded fallback', &
         failures)

    dbz2=missing; dbz2(2,3,4)=101.0
    rain2=rain_before; snow2=0.0; graupel2=0.0; omega2=missing
    omega2(2,3,4)=0.0
    CALL couple_radar_precipitation(dbz2,tk,rh,height,pressure,u,v, &
         1000.0,1000.0,missing,types,.TRUE.,rain2,snow2,graupel2,omega2, &
         support2,status2,cfg)
    CALL check(status2 == 2 .AND. .NOT. ANY(support2) .AND. &
         MAXVAL(ABS(rain2-rain_before)) < TINY(1.0), &
         'reflectivity above the physical ceiling must not create support', &
         failures)

    types2=types; types2(2,3,4)=96
    rain2=rain_before; snow2=0.0; graupel2=0.0; omega2=missing
    omega2(2,3,4)=0.0
    CALL couple_radar_precipitation(dbz,tk,rh,height,pressure,u,v, &
         1000.0,1000.0,missing,types2,.TRUE.,rain2,snow2,graupel2,omega2, &
         support2,status2,cfg)
    CALL check(status2 == 0 .AND. &
         MAXVAL(ABS(rain2-rain_before)) < TINY(1.0), &
         'out-of-range precipitation phase must reject unchanged',failures)

    bad_types=0
    rain2=rain_before; snow2=0.0; graupel2=0.0; omega2=missing
    omega2(2,3,4)=0.0
    CALL couple_radar_precipitation(dbz,tk,rh,height,pressure,u,v, &
         1000.0,1000.0,missing,bad_types,.TRUE.,rain2,snow2,graupel2,omega2, &
         support2,status2,cfg)
    CALL check(status2 == 0 .AND. &
         MAXVAL(ABS(rain2-rain_before)) < TINY(1.0), &
         'mismatched phase-array shape must reject unchanged',failures)

    bad_pressure=pressure
    bad_pressure(:,:,3)=bad_pressure(:,:,2)
    rain2=rain_before; snow2=0.0; graupel2=0.0; omega2=missing
    omega2(2,3,4)=0.0
    CALL couple_radar_precipitation(dbz,tk,rh,height,bad_pressure,u,v, &
         1000.0,1000.0,missing,types,.TRUE.,rain2,snow2,graupel2,omega2, &
         support2,status)
    CALL check(status == 0 .AND. &
         MAXVAL(ABS(rain2-rain_before)) < TINY(1.0), &
         'invalid coordinates must fail without publishing',failures)
  END SUBROUTINE test_radar_downdraft

  SUBROUTINE test_wind_modes(failures)
    INTEGER, INTENT(INOUT) :: failures
    INTEGER, PARAMETER :: nx=5,ny=5,nz=3
    REAL :: u0(nx,ny,nz),v0(nx,ny,nz),u1(nx,ny,nz),v1(nx,ny,nz)
    REAL :: beta(nx,ny,nz),dx(nx,ny),dy(nx,ny),divp(nz),vortp(nz)
    REAL :: divrms,vortrms,rough,a,smooth_rough
    INTEGER :: i,j,k,status

    a=1.0E-4
    u0=0.0; v0=0.0; u1=0.0; v1=0.0
    beta=1.0; dx=1.0; dy=1.0
    DO k=1,nz
      DO j=1,ny
        DO i=1,nx
          u1(i,j,k)=a*REAL(i-1)
          v1(i,j,k)=a*REAL(j-1)
        END DO
      END DO
    END DO
    CALL diagnose_wind_increment_modes(u0,v0,u1,v1,beta,dx,dy, &
         divrms,vortrms,rough,divp,vortp,status)
    CALL check(status==1 .AND. divrms>0.0 .AND. vortrms<1.0E-10, &
         'velocity-potential increment must diagnose as divergent',failures)
    smooth_rough=rough

    u1=0.0
    v1=0.0
    DO k=1,nz
      DO j=1,ny
        DO i=1,nx
          IF (k==2) THEN
            u1(i,j,k)=-a*REAL(j-1)
            v1(i,j,k)= a*REAL(i-1)
          END IF
        END DO
      END DO
    END DO
    CALL diagnose_wind_increment_modes(u0,v0,u1,v1,beta,dx,dy, &
         divrms,vortrms,rough,divp,vortp,status)
    CALL check(status==1 .AND. vortrms>0.0 .AND. divrms<1.0E-10, &
         'streamfunction increment must diagnose as rotational',failures)
    CALL check(ABS(vortp(2))>0.0 .AND. ABS(vortp(1))<1.0E-10 .AND. &
         ABS(vortp(3))<1.0E-10, &
         'rotational increment may be isolated to the cloud middle',failures)

    DO k=1,nz
      DO j=1,ny
        DO i=1,nx
          u1(i,j,k)=a*MERGE(1.0,-1.0,MOD(i+j,2)==0)
          v1(i,j,k)=0.0
        END DO
      END DO
    END DO
    CALL diagnose_wind_increment_modes(u0,v0,u1,v1,beta,dx,dy, &
         divrms,vortrms,rough,divp,vortp,status)
    CALL check(status==1 .AND. rough>smooth_rough, &
         'wave diagnostic must distinguish gridscale divergent noise',failures)
  END SUBROUTINE test_wind_modes

END PROGRAM test_cloud_bal_core
