PROGRAM probe_cases
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  IMPLICIT NONE

  CALL run_case('missing-qib', 1.766538480296731e-4_real32, 0.0_real32, &
       400.0_real32, 1.766538480296731e-4_real32/400.0_real32)
  CALL run_case('zero-no-volume', 0.0_real32, 0.0_real32, 0.0_real32, &
       0.0_real32)
  CALL run_case('valid-density-200', 1.0e-4_real32, 5.0e-7_real32, &
       200.0_real32, 5.0e-7_real32)
  CALL run_case('valid-density-700', 1.4e-4_real32, 2.0e-7_real32, &
       700.0_real32, 2.0e-7_real32)

  WRITE(*,'(A)') 'ALL CASES PASS'

CONTAINS

  SUBROUTINE run_case(label, qg0, brs0, expected_rho, expected_brs)
    CHARACTER(LEN=*), INTENT(IN) :: label
    REAL(real32), INTENT(IN) :: qg0, brs0, expected_rho, expected_brs
    REAL(real32) :: qrs(1,1,3), brs(1,1), rhox(1,1), cmg(1,1), pidn0g(1,1)
    REAL(real32) :: avtg(1,1), pvtg(1,1), precg2(1,1)
    REAL(real32) :: bvtg(1,1), bvtg1(1,1), bvtg2(1,1), bvtg3(1,1), bvtg4(1,1)
    REAL(real32) :: rslopegbmax(1,1), g1pbg(1,1), g3pbg(1,1), g4pbg(1,1)
    REAL(real32) :: g5pbgo2(1,1), g1pdgbgmg(1,1), dgbgmug1(1,1)
    REAL(real32) :: pi, rho_tolerance, brs_tolerance

    qrs = 0.0_real32
    qrs(1,1,3) = qg0
    brs = brs0
    rhox = 0.0_real32
    cmg = 0.0_real32
    pidn0g = 0.0_real32
    avtg = 0.0_real32
    pvtg = 0.0_real32
    precg2 = 0.0_real32
    bvtg = 0.0_real32
    bvtg1 = 0.0_real32
    bvtg2 = 0.0_real32
    bvtg3 = 0.0_real32
    bvtg4 = 0.0_real32
    rslopegbmax = 0.0_real32
    g1pbg = 0.0_real32
    g3pbg = 0.0_real32
    g4pbg = 0.0_real32
    g5pbgo2 = 0.0_real32
    g1pdgbgmg = 0.0_real32
    dgbgmug1 = 0.0_real32
    pi = 4.0_real32*ATAN(1.0_real32)

    CALL ProgB_param(brs, qrs, rhox, 1, 1, 1, 1, 1, 1, 1.0e-9_real32, &
         3.0_real32, 0.0_real32, cmg, pi, pidn0g, 6.0_real32, 1.0_real32, &
         4.0e6_real32, avtg, pvtg, precg2, bvtg, bvtg1, bvtg2, bvtg3, bvtg4, &
         rslopegbmax, 1.0_real32/1.8e5_real32, g1pbg, g3pbg, g4pbg, g5pbgo2, &
         g1pdgbgmg, dgbgmug1)

    IF (.NOT.ALL(ieee_is_finite([brs(1,1), rhox(1,1), cmg(1,1), &
         pidn0g(1,1), avtg(1,1), pvtg(1,1), precg2(1,1), bvtg(1,1), &
         bvtg1(1,1), bvtg2(1,1), bvtg3(1,1), bvtg4(1,1), &
         rslopegbmax(1,1), g1pbg(1,1), g3pbg(1,1), g4pbg(1,1), &
         g5pbgo2(1,1), g1pdgbgmg(1,1), dgbgmug1(1,1)]))) STOP 10
    IF (qrs(1,1,3) /= qg0) STOP 11
    brs_tolerance = MAX(1.0e-12_real32, ABS(expected_brs)*1.0e-5_real32)
    IF (ABS(brs(1,1)-expected_brs) > brs_tolerance) STOP 12
    IF (expected_rho >= 0.0_real32) THEN
      rho_tolerance = MAX(5.0e-3_real32, ABS(expected_rho)*1.0e-4_real32)
      IF (ABS(rhox(1,1)-expected_rho) > rho_tolerance) STOP 13
    END IF

    WRITE(*,'(A,1X,A,1X,A,ES16.8,1X,A,ES16.8,1X,A,ES16.8)') &
         'PASS', TRIM(label), 'qg=', qrs(1,1,3), 'qib=', brs(1,1), &
         'rho=', rhox(1,1)
  END SUBROUTINE run_case

END PROGRAM probe_cases
