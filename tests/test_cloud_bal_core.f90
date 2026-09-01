PROGRAM test_cloud_bal_core
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value, ieee_quiet_nan
  USE cloud_bal_field_contracts
  USE cloud_bal_moisture
  USE cloud_bal_cloud_profiles
  IMPLICIT NONE

  INTEGER :: failures

  failures = 0
  CALL test_field_contract(failures)
  CALL test_moisture(failures)
  CALL test_cloud_profiles(failures)

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

    bad_height = height
    bad_height(5) = bad_height(4)
    CALL build_multilayer_w_profile(2.0, cloud_type, bad_height, 0.01, &
         0.005, 0.05, missing, w, status)
    CALL check(status == 0, 'non-monotone height must fail', failures)
  END SUBROUTINE test_cloud_profiles

END PROGRAM test_cloud_bal_core
