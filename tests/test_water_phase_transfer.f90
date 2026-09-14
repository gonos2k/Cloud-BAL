! Independent oracle for explicit six-species water-phase transfers.
!
! Prescribed transfers and saturation share an independent mixture oracle.
! No expected-value calculation calls the production enthalpy routine.
PROGRAM test_water_phase_transfer
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite,ieee_value, &
    ieee_quiet_nan,ieee_positive_inf
  USE cloud_bal_state, ONLY: STATUS_OK,STATUS_FAILED
  USE cloud_bal_column_physics, ONLY: moist_species_enthalpy, &
    apply_water_phase_transfer,saturation_adjust_mixture_cell,SATURATION_LIQUID,SATURATION_ICE
  IMPLICIT NONE

  REAL(real64), PARAMETER :: T0=273.15_real64
  REAL(real64), PARAMETER :: CPD=1004.5_real64
  REAL(real64), PARAMETER :: CPV=1846.4_real64
  REAL(real64), PARAMETER :: CLIQ=4190.0_real64
  REAL(real64), PARAMETER :: CICE=2106.0_real64
  REAL(real64), PARAMETER :: LV0=2.5e6_real64
  REAL(real64), PARAMETER :: LF0=3.5e5_real64

  INTEGER :: failures

  failures=0
  CALL test_enthalpy_and_heat_capacity(failures)
  CALL test_explicit_transfers(failures)
  CALL test_temperature_crossings_and_noop(failures)
  CALL test_inverse_transfer(failures)
  CALL test_rejections_and_rollback(failures)
  CALL test_hydrometeor_storage_boundary(failures)
  CALL test_mixture_saturation(failures)
  IF (failures/=0) THEN
    PRINT *,'Water phase transfer tests failed:',failures
    ERROR STOP 1
  END IF
  PRINT *,'Water phase transfer tests passed'

CONTAINS

  SUBROUTINE check(condition,message,failures)
    LOGICAL, INTENT(IN) :: condition
    CHARACTER(LEN=*), INTENT(IN) :: message
    INTEGER, INTENT(INOUT) :: failures
    IF (.NOT.condition) THEN
      failures=failures+1
      PRINT *,'FAIL: ',TRIM(message)
    END IF
  END SUBROUTINE check

  SUBROUTINE check_close(value,reference,absolute,relative,message,failures)
    REAL(real64), INTENT(IN) :: value,reference,absolute,relative
    CHARACTER(LEN=*), INTENT(IN) :: message
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: tolerance
    tolerance=absolute+relative*MAX(1.0_real64,ABS(reference))
    CALL check(ieee_is_finite(value) .AND. ABS(value-reference)<=tolerance, &
               message,failures)
  END SUBROUTINE check_close

  PURE FUNCTION same_bits_scalar(a,b) RESULT(equal)
    REAL(real64), INTENT(IN) :: a,b
    LOGICAL :: equal
    equal=TRANSFER(a,0_int64)==TRANSFER(b,0_int64)
  END FUNCTION same_bits_scalar

  PURE FUNCTION same_bits_vector(a,b) RESULT(equal)
    REAL(real64), INTENT(IN) :: a(:),b(:)
    LOGICAL :: equal
    IF (SIZE(a)/=SIZE(b)) THEN
      equal=.FALSE.
    ELSE
      equal=ALL(TRANSFER(a,0_int64,SIZE(a))==TRANSFER(b,0_int64,SIZE(b)))
    END IF
  END FUNCTION same_bits_vector

  PURE FUNCTION oracle_species_enthalpy(temperature) RESULT(h)
    REAL(real64), INTENT(IN) :: temperature
    REAL(real64) :: h(6),dt
    dt=temperature-T0
    h(1)=LV0+CPV*dt
    h(2)=CLIQ*dt
    h(3)=-LF0+CICE*dt
    h(4)=CLIQ*dt
    h(5)=-LF0+CICE*dt
    h(6)=-LF0+CICE*dt
  END FUNCTION oracle_species_enthalpy

  PURE FUNCTION oracle_heat_capacity(r) RESULT(capacity)
    REAL(real64), INTENT(IN) :: r(6)
    REAL(real64) :: capacity
    capacity=CPD+CPV*r(1)+CLIQ*(r(2)+r(4))+CICE*(r(3)+r(5)+r(6))
  END FUNCTION oracle_heat_capacity

  PURE FUNCTION oracle_enthalpy(temperature,r) RESULT(enthalpy)
    REAL(real64), INTENT(IN) :: temperature,r(6)
    REAL(real64) :: enthalpy,dt
    dt=temperature-T0
    enthalpy=CPD*dt+r(1)*(LV0+CPV*dt)+ &
      (r(2)+r(4))*CLIQ*dt+(r(3)+r(5)+r(6))*(-LF0+CICE*dt)
  END FUNCTION oracle_enthalpy

  PURE FUNCTION oracle_temperature(temperature,r,delta) RESULT(new_temperature)
    REAL(real64), INTENT(IN) :: temperature,r(6),delta(6)
    REAL(real64) :: new_temperature
    REAL(real64) :: final_r(6)
    final_r=r+delta
    new_temperature=temperature-SUM(delta*oracle_species_enthalpy(temperature))/ &
      oracle_heat_capacity(final_r)
  END FUNCTION oracle_temperature

  SUBROUTINE test_enthalpy_and_heat_capacity(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64), PARAMETER :: temperatures(3)=(/150.01_real64, &
      273.15_real64,349.99_real64/)
    REAL(real64) :: r(6),temperature,dt,h,expected,measured_capacity
    REAL(real64) :: species_h(6)
    REAL(real64) :: latent_vl,latent_vi,latent_li
    INTEGER :: n

    r=(/0.017_real64,0.003_real64,0.004_real64,0.002_real64, &
        0.001_real64,0.005_real64/)
    dt=0.01_real64
    DO n=1,SIZE(temperatures)
      temperature=temperatures(n)
      expected=oracle_enthalpy(temperature,r)
      h=moist_species_enthalpy(temperature,r)
      species_h=oracle_species_enthalpy(temperature)
      CALL check_close(h,expected,5.0e-10_real64,2.0e-13_real64, &
                       'moist species enthalpy independent formula',failures)
      measured_capacity=(moist_species_enthalpy(temperature+dt,r)- &
        moist_species_enthalpy(temperature-dt,r))/(2.0_real64*dt)
      CALL check_close(measured_capacity,oracle_heat_capacity(r), &
                       5.0e-8_real64,2.0e-12_real64, &
                       'temperature derivative is independent moist heat capacity',failures)

      ! These are temperature-dependent latent differences derived directly
      ! from the independent species coefficients, not from h(T,r).
      latent_vl=LV0+(CPV-CLIQ)*(temperature-T0)
      latent_vi=LV0+LF0+(CPV-CICE)*(temperature-T0)
      latent_li=LF0+(CLIQ-CICE)*(temperature-T0)
      CALL check_close(species_h(1)-species_h(2),latent_vl,1.0e-10_real64, &
        1.0e-13_real64,'vapor-liquid latent coefficient varies with temperature',failures)
      CALL check_close(species_h(1)-species_h(3),latent_vi,1.0e-10_real64, &
        1.0e-13_real64,'vapor-ice latent coefficient varies with temperature',failures)
      CALL check_close(species_h(2)-species_h(3),latent_li,1.0e-10_real64, &
        1.0e-13_real64,'liquid-ice latent coefficient varies with temperature',failures)
    END DO
  END SUBROUTINE test_enthalpy_and_heat_capacity

  SUBROUTINE test_explicit_transfers(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: r(6),delta(6)

    ! Order is rv, rc, ri, rr, rs, rg.  Every case is an explicit transfer;
    ! no temperature switch or microphysical amount selection is permitted.
    r=(/0.010_real64,0.001_real64,0.0005_real64,0.002_real64, &
        0.001_real64,0.0005_real64/)
    delta=(/-0.002_real64,0.002_real64,0.0_real64,0.0_real64,0.0_real64,0.0_real64/)
    CALL check_transfer(270.0_real64,r,delta,'condensation',failures)

    r=(/0.010_real64,0.004_real64,0.0005_real64,0.002_real64, &
        0.001_real64,0.0005_real64/)
    delta=(/0.001_real64,-0.001_real64,0.0_real64,0.0_real64,0.0_real64,0.0_real64/)
    CALL check_transfer(280.0_real64,r,delta,'evaporation',failures)

    r=(/0.002_real64,0.001_real64,0.004_real64,0.002_real64, &
        0.001_real64,0.0005_real64/)
    delta=(/0.001_real64,0.0_real64,-0.001_real64,0.0_real64,0.0_real64,0.0_real64/)
    CALL check_transfer(255.0_real64,r,delta,'sublimation',failures)

    r=(/0.006_real64,0.001_real64,0.001_real64,0.002_real64, &
        0.001_real64,0.0005_real64/)
    delta=(/-0.001_real64,0.0_real64,0.001_real64,0.0_real64,0.0_real64,0.0_real64/)
    CALL check_transfer(255.0_real64,r,delta,'deposition',failures)

    r=(/0.002_real64,0.001_real64,0.004_real64,0.002_real64, &
        0.001_real64,0.0005_real64/)
    delta=(/0.0_real64,0.001_real64,-0.001_real64,0.0_real64,0.0_real64,0.0_real64/)
    CALL check_transfer(278.0_real64,r,delta,'melting',failures)

    r=(/0.002_real64,0.004_real64,0.001_real64,0.002_real64, &
        0.001_real64,0.0005_real64/)
    delta=(/0.0_real64,-0.001_real64,0.001_real64,0.0_real64,0.0_real64,0.0_real64/)
    CALL check_transfer(268.0_real64,r,delta,'freezing',failures)

    r=(/0.002_real64,0.001_real64,0.001_real64,0.004_real64, &
        0.001_real64,0.0005_real64/)
    delta=(/0.0_real64,0.0_real64,0.0_real64,-0.001_real64, &
           0.001_real64,0.0_real64/)
    CALL check_transfer(260.0_real64,r,delta,'rain-to-snow',failures)

    r=(/0.002_real64,0.001_real64,0.001_real64,0.001_real64, &
        0.004_real64,0.0005_real64/)
    delta=(/0.0_real64,0.0_real64,0.0_real64,0.001_real64, &
           -0.001_real64,0.0_real64/)
    CALL check_transfer(280.0_real64,r,delta,'snow-to-rain',failures)

    r=(/0.020_real64,0.010_real64,0.008_real64,0.006_real64, &
        0.004_real64,0.003_real64/)
    delta=0.0_real64
    delta(1)=-0.002_real64
    delta(2)=0.001_real64
    delta(3)=0.0005_real64
    delta(4)=0.0007_real64
    delta(5)=-0.0003_real64
    delta(6)=-SUM(delta(1:5))
    CALL check_transfer(274.0_real64,r,delta,'mixed simultaneous transfer',failures)
  END SUBROUTINE test_explicit_transfers

  SUBROUTINE check_transfer(initial_temperature,initial_r,delta,label,failures)
    REAL(real64), INTENT(IN) :: initial_temperature,initial_r(6),delta(6)
    CHARACTER(LEN=*), INTENT(IN) :: label
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: temperature,r(6),expected_r(6),expected_temperature
    REAL(real64) :: initial_h,final_h
    INTEGER :: status

    expected_r=initial_r+delta
    expected_temperature=oracle_temperature(initial_temperature,initial_r,delta)
    initial_h=oracle_enthalpy(initial_temperature,initial_r)
    temperature=initial_temperature; r=initial_r
    CALL apply_water_phase_transfer(temperature,r,delta,status)
    CALL check(status==STATUS_OK,TRIM(label)//' must succeed',failures)
    IF (status/=STATUS_OK) RETURN
    CALL check(ABS(SUM(delta))<=64.0_real64*EPSILON(1.0_real64)* &
      MAX(1.0_real64,MAXVAL(ABS(delta))),TRIM(label)//' oracle delta closes',failures)
    CALL check(ALL(ieee_is_finite(r)) .AND. ieee_is_finite(temperature), &
                TRIM(label)//' output finite',failures)
    CALL check_close(temperature,expected_temperature,5.0e-11_real64, &
                     5.0e-13_real64,TRIM(label)//' analytic temperature',failures)
    CALL check(ALL(ABS(r-expected_r)<=5.0e-14_real64+ &
      5.0e-13_real64*MAX(1.0_real64,ABS(expected_r))), &
      TRIM(label)//' all six species amounts',failures)
    final_h=oracle_enthalpy(temperature,r)
    CALL check_close(final_h,initial_h,5.0e-7_real64,5.0e-12_real64, &
                     TRIM(label)//' independent enthalpy closure',failures)
    CALL check_close(moist_species_enthalpy(temperature,r),initial_h, &
                     5.0e-7_real64,5.0e-12_real64, &
                     TRIM(label)//' production enthalpy reports closure',failures)
  END SUBROUTINE check_transfer

  SUBROUTINE test_temperature_crossings_and_noop(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: temperature,r(6),delta(6),saved_temperature,saved_r(6)
    INTEGER :: status

    ! Explicit condensation and evaporation may cross T0 in either direction.
    r=(/0.006_real64,0.0_real64,0.001_real64,0.001_real64, &
        0.001_real64,0.001_real64/)
    delta=(/-0.005_real64,0.005_real64,0.0_real64,0.0_real64,0.0_real64,0.0_real64/)
    temperature=272.0_real64
    CALL apply_water_phase_transfer(temperature,r,delta,status)
    CALL check(status==STATUS_OK .AND. temperature>T0, &
               'condensation explicitly crosses upward through T0',failures)

    r=(/0.006_real64,0.005_real64,0.001_real64,0.001_real64, &
        0.001_real64,0.001_real64/)
    delta=(/0.002_real64,-0.002_real64,0.0_real64,0.0_real64,0.0_real64,0.0_real64/)
    temperature=275.0_real64
    CALL apply_water_phase_transfer(temperature,r,delta,status)
    CALL check(status==STATUS_OK .AND. temperature<T0, &
               'evaporation explicitly crosses downward through T0',failures)

    ! Supercooled liquid is untouched when no transfer is prescribed.
    temperature=260.0_real64
    r=(/0.008_real64,0.012_real64,0.004_real64,0.002_real64, &
        0.001_real64,0.003_real64/)
    delta=0.0_real64
    saved_temperature=temperature; saved_r=r
    CALL apply_water_phase_transfer(temperature,r,delta,status)
    CALL check(status==STATUS_OK,'zero transfer in supercooled liquid succeeds',failures)
    CALL check(same_bits_scalar(temperature,saved_temperature) .AND. &
               same_bits_vector(r,saved_r), &
               'zero transfer leaves supercooled water bit unchanged',failures)
  END SUBROUTINE test_temperature_crossings_and_noop

  SUBROUTINE test_inverse_transfer(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: original_temperature,temperature,original_r(6),r(6)
    REAL(real64) :: delta(6),inverse(6)
    INTEGER :: status

    original_temperature=264.0_real64
    original_r=(/0.014_real64,0.003_real64,0.006_real64,0.002_real64, &
                 0.001_real64,0.004_real64/)
    delta=(/-0.002_real64,0.001_real64,0.0005_real64,0.0008_real64, &
           -0.0002_real64,0.0_real64/)
    delta(6)=-SUM(delta(1:5))
    inverse=-delta
    temperature=original_temperature; r=original_r
    CALL apply_water_phase_transfer(temperature,r,delta,status)
    CALL check(status==STATUS_OK,'forward transfer for inverse test',failures)
    IF (status/=STATUS_OK) RETURN
    CALL apply_water_phase_transfer(temperature,r,inverse,status)
    CALL check(status==STATUS_OK,'inverse transfer succeeds',failures)
    CALL check_close(temperature,original_temperature,2.0e-10_real64, &
                     2.0e-12_real64,'inverse transfer restores temperature',failures)
    CALL check(same_bits_vector(r,original_r) .OR. ALL(ABS(r-original_r)<1.0e-14_real64), &
               'inverse transfer restores all species',failures)
  END SUBROUTINE test_inverse_transfer

  SUBROUTINE expect_rejection(temperature,r,delta,label,failures)
    REAL(real64), INTENT(IN) :: temperature,r(6),delta(6)
    CHARACTER(LEN=*), INTENT(IN) :: label
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: candidate_temperature,candidate_r(6),saved_temperature,saved_r(6)
    INTEGER :: status

    candidate_temperature=temperature; candidate_r=r
    saved_temperature=candidate_temperature; saved_r=candidate_r
    status=123456
    CALL apply_water_phase_transfer(candidate_temperature,candidate_r,delta,status)
    CALL check(status==STATUS_FAILED,TRIM(label)//' must reject',failures)
    CALL check(same_bits_scalar(candidate_temperature,saved_temperature) .AND. &
               same_bits_vector(candidate_r,saved_r), &
               TRIM(label)//' must roll back exactly',failures)
  END SUBROUTINE expect_rejection

  SUBROUTINE test_rejections_and_rollback(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: temperature,r(6),delta(6),bad
    INTEGER :: n

    temperature=275.0_real64
    r=(/0.010_real64,0.004_real64,0.001_real64,0.002_real64, &
        0.001_real64,0.003_real64/)
    delta=(/-0.001_real64,0.001_real64,0.0_real64,0.0_real64,0.0_real64,0.0_real64/)

    bad=ieee_value(0.0_real64,ieee_quiet_nan)
    CALL expect_rejection(bad,r,delta,'nonfinite temperature',failures)
    bad=ieee_value(0.0_real64,ieee_positive_inf)
    CALL expect_rejection(bad,r,delta,'infinite temperature',failures)
    CALL expect_rejection(HUGE(1.0_real64),r,delta,'HUGE temperature',failures)

    DO n=1,6
      temperature=275.0_real64; r=(/0.010_real64,0.004_real64,0.001_real64, &
        0.002_real64,0.001_real64,0.003_real64/)
      r(n)=ieee_value(0.0_real64,ieee_quiet_nan)
      CALL expect_rejection(temperature,r,delta,'NaN species '//itoa(n),failures)
      temperature=275.0_real64; r=(/0.010_real64,0.004_real64,0.001_real64, &
        0.002_real64,0.001_real64,0.003_real64/)
      r(n)=ieee_value(0.0_real64,ieee_positive_inf)
      CALL expect_rejection(temperature,r,delta,'infinite species '//itoa(n),failures)
    END DO
    r=(/HUGE(1.0_real64),0.004_real64,0.001_real64,0.002_real64, &
        0.001_real64,0.003_real64/)
    CALL expect_rejection(275.0_real64,r,delta,'HUGE vapor species',failures)
    r=(/0.201_real64,0.004_real64,0.001_real64,0.002_real64, &
        0.001_real64,0.003_real64/)
    CALL expect_rejection(275.0_real64,r,delta,'vapor storage upper bound',failures)
    r=(/-1.0e-6_real64,0.004_real64,0.001_real64,0.002_real64, &
        0.001_real64,0.003_real64/)
    CALL expect_rejection(275.0_real64,r,delta,'negative vapor',failures)
    r=(/0.010_real64,-1.0e-6_real64,0.001_real64,0.002_real64, &
        0.001_real64,0.003_real64/)
    CALL expect_rejection(275.0_real64,r,delta,'negative cloud liquid',failures)

    r=(/0.010_real64,0.004_real64,0.001_real64,0.002_real64, &
        0.001_real64,0.003_real64/)
    delta=(/1.0e-4_real64,0.0_real64,0.0_real64,0.0_real64,0.0_real64,0.0_real64/)
    CALL expect_rejection(275.0_real64,r,delta,'external water addition',failures)
    delta=(/ieee_value(0.0_real64,ieee_quiet_nan),0.0_real64,0.0_real64, &
            0.0_real64,0.0_real64,0.0_real64/)
    CALL expect_rejection(275.0_real64,r,delta,'NaN transfer',failures)
    delta=(/ieee_value(0.0_real64,ieee_positive_inf),0.0_real64,0.0_real64, &
            0.0_real64,0.0_real64,0.0_real64/)
    CALL expect_rejection(275.0_real64,r,delta,'infinite transfer',failures)
    delta=(/HUGE(1.0_real64),0.0_real64,0.0_real64,0.0_real64,0.0_real64, &
            -HUGE(1.0_real64)/)
    CALL expect_rejection(275.0_real64,r,delta,'HUGE transfer',failures)

    delta=(/0.001_real64,-0.005_real64,0.0_real64,0.0_real64,0.0_real64, &
            0.004_real64/)
    CALL expect_rejection(275.0_real64,r,delta,'overdraw cloud liquid',failures)
    r=(/0.1995_real64,0.004_real64,0.001_real64,0.002_real64, &
        0.001_real64,0.003_real64/)
    delta=(/0.001_real64,-0.001_real64,0.0_real64,0.0_real64,0.0_real64,0.0_real64/)
    CALL expect_rejection(275.0_real64,r,delta,'output vapor storage upper bound',failures)

    r=(/0.100_real64,0.0_real64,0.001_real64,0.002_real64,0.001_real64,0.003_real64/)
    delta=(/-0.100_real64,0.100_real64,0.0_real64,0.0_real64,0.0_real64,0.0_real64/)
    CALL expect_rejection(349.0_real64,r,delta,'output temperature above 350 K',failures)
    r=(/0.001_real64,0.100_real64,0.001_real64,0.002_real64,0.001_real64,0.003_real64/)
    delta=(/0.100_real64,-0.100_real64,0.0_real64,0.0_real64,0.0_real64,0.0_real64/)
    CALL expect_rejection(151.0_real64,r,delta,'output temperature below 150 K',failures)
  END SUBROUTINE test_rejections_and_rollback

  SUBROUTINE test_hydrometeor_storage_boundary(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: temperature,r(6),delta(6),saved_r(6),saved_temperature
    REAL(real64) :: storage_limit
    INTEGER :: n,status

    ! Hydrometeors follow their REAL32 storage range, unlike vapor's 0.2 cap.
    storage_limit=REAL(HUGE(1.0_real32),real64)*0.5_real64
    DO n=2,6
      temperature=273.15_real64
      r=(/0.010_real64,0.001_real64,0.001_real64,0.001_real64, &
          0.001_real64,0.001_real64/)
      r(n)=storage_limit
      delta=0.0_real64
      saved_temperature=temperature; saved_r=r
      CALL apply_water_phase_transfer(temperature,r,delta,status)
      CALL check(status==STATUS_OK,'large finite hydrometeor storage is accepted',failures)
      CALL check(same_bits_scalar(temperature,saved_temperature) .AND. &
                 same_bits_vector(r,saved_r), &
                 'zero transfer preserves large hydrometeor storage',failures)
    END DO
  END SUBROUTINE test_hydrometeor_storage_boundary

  SUBROUTINE test_mixture_saturation(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: temperature,initial_t,target_t,es,rv_target,r(6),initial(6),expected(6),delta(6)
    REAL(real64) :: transfer,explicit_t,explicit_r(6)
    INTEGER :: surface,phase,status,n

    DO n=1,2
      surface=SATURATION_LIQUID; phase=2; target_t=300.0_real64; transfer=0.001_real64
      IF (n==2) THEN
        surface=SATURATION_ICE; phase=3; target_t=250.0_real64; transfer=-0.001_real64
      END IF
      IF (n==1) THEN
        es=611.20_real64*EXP(17.67_real64*(target_t-T0)/(target_t-29.65_real64))
      ELSE
        es=611.15_real64*EXP(22.452_real64*(target_t-T0)/(target_t-0.55_real64))
      END IF
      rv_target=0.8_real64*0.622_real64*es/(85000.0_real64-es)
      initial=[rv_target-transfer,0.004_real64,0.002_real64,0.02_real64,0.03_real64,0.04_real64]
      delta=0.0_real64; delta(1)=transfer; delta(phase)=-transfer
      expected=initial+delta
      ! Construct initial enthalpy from the known final state, independently.
      initial_t=T0+(oracle_enthalpy(target_t,expected)- &
        SUM(initial*oracle_species_enthalpy(T0)))/oracle_heat_capacity(initial)
      temperature=initial_t; r=initial
      CALL saturation_adjust_mixture_cell(85000.0_real64,temperature,r,0.8_real64,status,surface)
      CALL check(status==STATUS_OK,'six-species saturation root accepted',failures)
      CALL check_close(temperature,target_t,1.0e-8_real64,0.0_real64,'known mixture root T',failures)
      CALL check(MAXVAL(ABS(r-expected))<1.0e-11_real64,'known mixture root species',failures)
      CALL check(same_bits_vector(r(4:6),initial(4:6)),'precipitation is unchanged by saturation',failures)
      CALL check_close(oracle_enthalpy(temperature,r),oracle_enthalpy(initial_t,initial), &
        1.0e-8_real64,1.0e-12_real64,'saturation mixture enthalpy closes',failures)
      explicit_t=initial_t; explicit_r=initial
      CALL apply_water_phase_transfer(explicit_t,explicit_r,delta,status)
      CALL check(status==STATUS_OK,'equivalent prescribed transfer accepted',failures)
      CALL check_close(temperature,explicit_t,1.0e-8_real64,0.0_real64, &
        'saturation and prescribed transfer use one enthalpy law',failures)
    END DO

    ! No reservoir exhaustion at a vapor cap: reject instead of calling it equilibrium.
    temperature=350.0_real64
    r=[0.19_real64,0.1_real64,0.0_real64,0.0_real64,0.0_real64,0.0_real64]
    initial_t=temperature; initial=r
    CALL saturation_adjust_mixture_cell(20000.0_real64,temperature,r,1.0_real64,status,SATURATION_LIQUID)
    CALL check(status==STATUS_FAILED,'vapor cap is not reservoir exhaustion',failures)
    CALL check(same_bits_scalar(temperature,initial_t) .AND. same_bits_vector(r,initial), &
      'vapor-bound failure rolls back',failures)
  END SUBROUTINE test_mixture_saturation

  FUNCTION itoa(n) RESULT(text)
    INTEGER, INTENT(IN) :: n
    CHARACTER(LEN=4) :: text
    WRITE(text,'(I4)') n
  END FUNCTION itoa

END PROGRAM test_water_phase_transfer
