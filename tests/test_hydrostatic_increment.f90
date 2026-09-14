! Independent oracle for the column hydrostatic geopotential increment.
!
! This test covers only the represented column formula.  It does not assert
! native mass tendencies, stored-state conservation, or a full hydrostatic
! state update.
PROGRAM test_hydrostatic_increment
  USE, INTRINSIC :: iso_fortran_env, ONLY: real64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value, ieee_quiet_nan
  USE cloud_bal_state, ONLY: STATUS_OK, STATUS_FAILED
  USE cloud_bal_column_physics, ONLY: hydrostatic_geopotential_increment, &
    apply_water_phase_transfer
  IMPLICIT NONE

  INTEGER :: failures

  failures=0
  CALL test_dry_uniform_heating(failures)
  CALL test_moist_isothermal_change(failures)
  CALL test_condensate_loading(failures)
  CALL test_no_change_is_exact_zero(failures)
  CALL test_logp_linear_delta_a(failures)
  CALL test_nonlinear_grid_refinement(failures)
  CALL test_thermo_chain_regression(failures)
  CALL test_invalid_inputs_rollback(failures)
  CALL test_single_level_anchor(failures)
  CALL test_surface_pressure_dry_isothermal(failures)
  CALL test_surface_temperature_water_change(failures)
  CALL test_surface_no_change_is_exact_zero(failures)
  CALL test_surface_invalid_inputs_rollback(failures)

  IF (failures/=0) THEN
    PRINT *, 'Hydrostatic increment tests failed:', failures
    ERROR STOP 1
  END IF
  PRINT *, 'Hydrostatic increment tests passed'

CONTAINS

  SUBROUTINE check(condition,message,failures)
    LOGICAL, INTENT(IN) :: condition
    CHARACTER(LEN=*), INTENT(IN) :: message
    INTEGER, INTENT(INOUT) :: failures
    IF (.NOT.condition) THEN
      failures=failures+1
      PRINT *, 'FAIL: ',TRIM(message)
    END IF
  END SUBROUTINE check

  PURE REAL(real64) FUNCTION air_volume_factor(temperature,water)
    REAL(real64), INTENT(IN) :: temperature
    REAL(real64), INTENT(IN) :: water(6)
    REAL(real64), PARAMETER :: RD_AIR=287.05_real64
    REAL(real64), PARAMETER :: EPSILON_WATER=0.622_real64
    air_volume_factor=RD_AIR*temperature*(1.0_real64+water(1)/EPSILON_WATER)/ &
      (1.0_real64+SUM(water))
  END FUNCTION air_volume_factor

  SUBROUTINE expected_increment(pressure,temperature_before,water_before, &
                                temperature_after,water_after,expected)
    REAL(real64), INTENT(IN) :: pressure(:),temperature_before(:), &
      water_before(:,:),temperature_after(:),water_after(:,:)
    REAL(real64), INTENT(OUT) :: expected(:)
    REAL(real64) :: delta_a(SIZE(pressure))
    INTEGER :: k

    DO k=1,SIZE(pressure)
      delta_a(k)=air_volume_factor(temperature_after(k),water_after(:,k))- &
        air_volume_factor(temperature_before(k),water_before(:,k))
    END DO
    expected=0.0_real64
    DO k=1,SIZE(pressure)-1
      expected(k+1)=expected(k)+0.5_real64*(delta_a(k)+delta_a(k+1))* &
        LOG(pressure(k)/pressure(k+1))
    END DO
  END SUBROUTINE expected_increment

  SUBROUTINE expected_surface_increment(pressure,temperature_before,water_before, &
                                        temperature_after,water_after, &
                                        surface_pressure_before, &
                                        surface_temperature_before, &
                                        surface_water_before, &
                                        surface_pressure_after, &
                                        surface_temperature_after, &
                                        surface_water_after,expected)
    REAL(real64), INTENT(IN) :: pressure(:),temperature_before(:), &
      water_before(:,:),temperature_after(:),water_after(:,:)
    REAL(real64), INTENT(IN) :: surface_pressure_before, &
      surface_temperature_before,surface_water_before(:), &
      surface_pressure_after,surface_temperature_after,surface_water_after(:)
    REAL(real64), INTENT(OUT) :: expected(:)
    REAL(real64) :: center_expected(SIZE(pressure)),surface_delta

    CALL expected_increment(pressure,temperature_before,water_before, &
      temperature_after,water_after,center_expected)
    surface_delta=0.5_real64*( &
      air_volume_factor(surface_temperature_after,surface_water_after)+ &
      air_volume_factor(temperature_after(1),water_after(:,1)))* &
      LOG(surface_pressure_after/pressure(1))- &
      0.5_real64*( &
      air_volume_factor(surface_temperature_before,surface_water_before)+ &
      air_volume_factor(temperature_before(1),water_before(:,1)))* &
      LOG(surface_pressure_before/pressure(1))
    expected=center_expected+surface_delta
  END SUBROUTINE expected_surface_increment

  SUBROUTINE initialize_column(pressure,temperature_before,water_before, &
                                temperature_after,water_after)
    REAL(real64), INTENT(OUT) :: pressure(:),temperature_before(:), &
      water_before(:,:),temperature_after(:),water_after(:,:)
    INTEGER :: k

    DO k=1,SIZE(pressure)
      pressure(k)=100000.0_real64*EXP(-0.25_real64*REAL(k-1,real64))
      temperature_before(k)=280.0_real64
      temperature_after(k)=280.0_real64
    END DO
    water_before=0.0_real64
    water_after=0.0_real64
    water_before(1,:)=0.008_real64
    water_after(1,:)=0.008_real64
    water_before(2,:)=0.001_real64
    water_after(2,:)=0.001_real64
  END SUBROUTINE initialize_column

  SUBROUTINE close_vector(actual,expected,tolerance,message,failures)
    REAL(real64), INTENT(IN) :: actual(:),expected(:),tolerance
    CHARACTER(LEN=*), INTENT(IN) :: message
    INTEGER, INTENT(INOUT) :: failures
    CALL check(SIZE(actual)==SIZE(expected) .AND. &
      ALL(ABS(actual-expected)<=tolerance*MAX(1.0_real64,ABS(expected))), &
      message,failures)
  END SUBROUTINE close_vector

  SUBROUTINE test_dry_uniform_heating(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: pressure(4),tb(4),ta(4),wb(6,4),wa(6,4),delta(4),expected(4)
    REAL(real64), PARAMETER :: RD_AIR=287.05_real64
    INTEGER :: status

    CALL initialize_column(pressure,tb,wb,ta,wa)
    wb=0.0_real64; wa=0.0_real64
    tb=250.0_real64; ta=260.0_real64
    CALL hydrostatic_geopotential_increment(pressure,tb,wb,ta,wa,delta,status)
    expected=0.0_real64
    expected(2:)=RD_AIR*(ta(1)-tb(1))*LOG(pressure(1)/pressure(2:))
    CALL check(status==STATUS_OK,'dry uniform heating accepted',failures)
    CALL close_vector(delta,expected,1.0e-12_real64, &
      'dry uniform heating follows analytic pressure-log integral',failures)
  END SUBROUTINE test_dry_uniform_heating

  SUBROUTINE test_moist_isothermal_change(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: pressure(4),tb(4),ta(4),wb(6,4),wa(6,4),delta(4),expected(4)
    INTEGER :: status

    CALL initialize_column(pressure,tb,wb,ta,wa)
    tb=275.0_real64; ta=tb
    wb=0.0_real64; wa=0.0_real64
    wb(1,:)=0.004_real64; wa(1,:)=0.012_real64
    wb(2,:)=0.002_real64; wa(2,:)=0.002_real64
    CALL hydrostatic_geopotential_increment(pressure,tb,wb,ta,wa,delta,status)
    CALL expected_increment(pressure,tb,wb,ta,wa,expected)
    CALL check(status==STATUS_OK,'moist isothermal change accepted',failures)
    CALL close_vector(delta,expected,1.0e-12_real64, &
      'moist isothermal increment uses both vapor numerator and total-water denominator',failures)
    CALL check(delta(4)>0.0_real64,'moistening increases geopotential upward',failures)
  END SUBROUTINE test_moist_isothermal_change

  SUBROUTINE test_condensate_loading(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: pressure(4),tb(4),ta(4),wb(6,4),wa(6,4),delta(4),expected(4)
    INTEGER :: status

    CALL initialize_column(pressure,tb,wb,ta,wa)
    tb=ta; wb=0.0_real64; wa=0.0_real64
    wa(2,:)=0.01_real64
    CALL hydrostatic_geopotential_increment(pressure,tb,wb,ta,wa,delta,status)
    CALL expected_increment(pressure,tb,wb,ta,wa,expected)
    CALL check(status==STATUS_OK,'condensate loading accepted',failures)
    CALL close_vector(delta,expected,1.0e-12_real64, &
      'condensate loading follows mixture denominator',failures)
    CALL check(delta(2)<0.0_real64 .AND. delta(4)<0.0_real64, &
      'condensate loading gives a negative geopotential increment',failures)
  END SUBROUTINE test_condensate_loading

  SUBROUTINE test_no_change_is_exact_zero(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: pressure(4),tb(4),ta(4),wb(6,4),wa(6,4),delta(4)
    INTEGER :: status

    CALL initialize_column(pressure,tb,wb,ta,wa)
    ta=tb; wa=wb
    delta=[-3.0_real64,7.0_real64,-11.0_real64,19.0_real64]
    CALL hydrostatic_geopotential_increment(pressure,tb,wb,ta,wa,delta,status)
    CALL check(status==STATUS_OK,'unchanged column accepted',failures)
    CALL check(ALL(delta==0.0_real64),'no-change increment is exactly zero',failures)
  END SUBROUTINE test_no_change_is_exact_zero

  SUBROUTINE test_logp_linear_delta_a(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: pressure(5),tb(5),ta(5),wb(6,5),wa(6,5),delta(5),expected(5)
    REAL(real64), PARAMETER :: RD_AIR=287.05_real64, SLOPE=18.0_real64
    REAL(real64) :: x
    INTEGER :: k,status

    DO k=1,5
      x=0.35_real64*REAL(k-1,real64)
      pressure(k)=100000.0_real64*EXP(-x)
      tb(k)=240.0_real64
      ta(k)=tb(k)+SLOPE*x
    END DO
    wb=0.0_real64; wa=0.0_real64
    CALL hydrostatic_geopotential_increment(pressure,tb,wb,ta,wa,delta,status)
    expected=0.0_real64
    DO k=2,5
      x=0.35_real64*REAL(k-1,real64)
      expected(k)=0.5_real64*RD_AIR*SLOPE*x*x
    END DO
    CALL check(status==STATUS_OK,'log-pressure-linear delta-A profile accepted',failures)
    CALL close_vector(delta,expected,1.0e-12_real64, &
      'trapezoid is exact when delta-A is linear in log pressure',failures)
  END SUBROUTINE test_logp_linear_delta_a

  SUBROUTINE test_nonlinear_grid_refinement(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: coarse_p(3),fine_p(5),coarse_tb(3),fine_tb(5), &
      coarse_ta(3),fine_ta(5),coarse_wb(6,3),fine_wb(6,5), &
      coarse_wa(6,3),fine_wa(6,5),coarse_delta(3),fine_delta(5)
    REAL(real64), PARAMETER :: RD_AIR=287.05_real64, AMPLITUDE=30.0_real64
    REAL(real64), PARAMETER :: LOG_RANGE=LOG(10.0_real64)
    REAL(real64) :: coarse_error,fine_error,x
    INTEGER :: k,status_coarse,status_fine

    DO k=1,3
      x=LOG_RANGE*REAL(k-1,real64)/2.0_real64
      coarse_p(k)=100000.0_real64*EXP(-x)
      coarse_tb(k)=280.0_real64; coarse_ta(k)=280.0_real64+AMPLITUDE*SIN(x)
    END DO
    DO k=1,5
      x=LOG_RANGE*REAL(k-1,real64)/4.0_real64
      fine_p(k)=100000.0_real64*EXP(-x)
      fine_tb(k)=280.0_real64; fine_ta(k)=280.0_real64+AMPLITUDE*SIN(x)
    END DO
    coarse_wb=0.0_real64; coarse_wa=0.0_real64
    fine_wb=0.0_real64; fine_wa=0.0_real64
    CALL hydrostatic_geopotential_increment(coarse_p,coarse_tb,coarse_wb, &
      coarse_ta,coarse_wa,coarse_delta,status_coarse)
    CALL hydrostatic_geopotential_increment(fine_p,fine_tb,fine_wb, &
      fine_ta,fine_wa,fine_delta,status_fine)
    coarse_error=ABS(coarse_delta(3)-RD_AIR*AMPLITUDE*(1.0_real64-COS(LOG_RANGE)))
    fine_error=ABS(fine_delta(5)-RD_AIR*AMPLITUDE*(1.0_real64-COS(LOG_RANGE)))
    CALL check(status_coarse==STATUS_OK .AND. status_fine==STATUS_OK, &
      'nonlinear coarse and refined columns accepted',failures)
    CALL check(fine_error<coarse_error, &
      'nonlinear geopotential integral converges under log-pressure refinement',failures)
    CALL check(coarse_error>3.5_real64*fine_error .AND. &
      coarse_error<4.5_real64*fine_error, &
      'halving log-pressure spacing gives second-order convergence',failures)
  END SUBROUTINE test_nonlinear_grid_refinement

  SUBROUTINE test_thermo_chain_regression(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: pressure(4),tb(4),ta(4),wb(6,4),wa(6,4),delta_phi(4),expected(4)
    REAL(real64) :: phase_delta(6),species(6)
    INTEGER :: k,phase_status,status

    CALL initialize_column(pressure,tb,wb,ta,wa)
    tb=[265.0_real64,270.0_real64,275.0_real64,280.0_real64]
    wb=0.0_real64
    wb(1,:)=0.012_real64
    wb(2,:)=0.003_real64
    ta=tb
    wa=wb
    phase_delta=0.0_real64
    phase_delta(1)=-1.0e-3_real64
    phase_delta(2)=1.0e-3_real64
    DO k=1,4
      species=wa(:,k)
      CALL apply_water_phase_transfer(ta(k),species,phase_delta,phase_status)
      CALL check(phase_status==STATUS_OK,'thermodynamic phase transfer accepted',failures)
      IF (phase_status/=STATUS_OK) RETURN
      wa(:,k)=species
    END DO
    CALL check(ANY(ABS(ta-tb)>1.0e-8_real64) .AND. ANY(wa(1,:)/=wb(1,:)), &
      'thermo chain changes temperature and vapor before hydrostatic increment',failures)
    CALL hydrostatic_geopotential_increment(pressure,tb,wb,ta,wa,delta_phi,status)
    CALL expected_increment(pressure,tb,wb,ta,wa,expected)
    CALL check(status==STATUS_OK,'hydrostatic increment accepts thermo-chain output',failures)
    CALL close_vector(delta_phi,expected,1.0e-12_real64, &
      'hydrostatic increment matches independent p-alpha oracle after phase transfer',failures)
  END SUBROUTINE test_thermo_chain_regression

  SUBROUTINE expect_failure_unchanged(pressure,tb,wb,ta,wa,delta,status,failures,message)
    REAL(real64), INTENT(IN) :: pressure(:),tb(:),wb(:,:),ta(:),wa(:,:)
    REAL(real64), INTENT(INOUT) :: delta(:)
    INTEGER, INTENT(OUT) :: status
    INTEGER, INTENT(INOUT) :: failures
    CHARACTER(LEN=*), INTENT(IN) :: message
    REAL(real64) :: sentinel(SIZE(delta))

    sentinel=delta
    CALL hydrostatic_geopotential_increment(pressure,tb,wb,ta,wa,delta,status)
    CALL check(status==STATUS_FAILED .AND. ALL(delta==sentinel),message,failures)
  END SUBROUTINE expect_failure_unchanged

  SUBROUTINE test_invalid_inputs_rollback(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: pressure(4),tb(4),ta(4),wb(6,4),wa(6,4),delta(4)
    REAL(real64) :: short_ta(3),bad_pressure(4),bad_water(6,4)
    INTEGER :: status

    CALL initialize_column(pressure,tb,wb,ta,wa)
    delta=[31.0_real64,32.0_real64,33.0_real64,34.0_real64]

    bad_water=wb; bad_water(1,2)=-1.0e-6_real64
    CALL expect_failure_unchanged(pressure,tb,bad_water,ta,wa,delta,status,failures, &
      'negative water is rejected without changing delta')

    bad_water=wb; bad_water(1,2)=ieee_value(0.0_real64,ieee_quiet_nan)
    CALL expect_failure_unchanged(pressure,tb,bad_water,ta,wa,delta,status,failures, &
      'nonfinite water is rejected without changing delta')

    ta(2)=ieee_value(0.0_real64,ieee_quiet_nan)
    CALL expect_failure_unchanged(pressure,tb,wb,ta,wa,delta,status,failures, &
      'nonfinite temperature is rejected without changing delta')
    ta=tb; ta(2)=400.0_real64
    CALL expect_failure_unchanged(pressure,tb,wb,ta,wa,delta,status,failures, &
      'out-of-range temperature is rejected without changing delta')

    bad_pressure=pressure; bad_pressure(2)=bad_pressure(1)
    CALL expect_failure_unchanged(bad_pressure,tb,wb,ta,wa,delta,status,failures, &
      'duplicate pressure is rejected without changing delta')

    bad_pressure=pressure
    bad_pressure(2)=ieee_value(0.0_real64,ieee_quiet_nan)
    CALL expect_failure_unchanged(bad_pressure,tb,wb,ta,wa,delta,status,failures, &
      'nonfinite pressure is rejected without changing delta')

    short_ta=280.0_real64
    CALL expect_failure_unchanged(pressure,tb,wb,short_ta,wa,delta,status,failures, &
      'shape mismatch is rejected without changing delta')
  END SUBROUTINE test_invalid_inputs_rollback

  SUBROUTINE test_single_level_anchor(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: pressure(1),tb(1),ta(1),wb(6,1),wa(6,1),delta(1)
    INTEGER :: status

    pressure=[90000.0_real64]; tb=[220.0_real64]; ta=[340.0_real64]
    wb=0.0_real64; wa=0.0_real64; delta=[-99.0_real64]
    CALL hydrostatic_geopotential_increment(pressure,tb,wb,ta,wa,delta,status)
    CALL check(status==STATUS_OK .AND. delta(1)==0.0_real64, &
      'single represented level is a valid zero anchor',failures)
  END SUBROUTINE test_single_level_anchor

  SUBROUTINE test_surface_pressure_dry_isothermal(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: pressure(4),tb(4),ta(4),wb(6,4),wa(6,4),delta(4),expected(4)
    REAL(real64) :: surface_pressure_pair(2),surface_temperature_pair(2)
    REAL(real64) :: surface_water_pair(6,2)
    REAL(real64), PARAMETER :: RD_AIR=287.05_real64, TEMPERATURE=280.0_real64
    REAL(real64) :: expected_offset
    INTEGER :: status

    CALL initialize_column(pressure,tb,wb,ta,wa)
    tb=TEMPERATURE; ta=TEMPERATURE
    wb=0.0_real64; wa=0.0_real64
    surface_pressure_pair=[110000.0_real64,120000.0_real64]
    surface_temperature_pair=TEMPERATURE
    surface_water_pair=0.0_real64
    CALL hydrostatic_geopotential_increment(pressure,tb,wb,ta,wa,delta,status, &
      surface_pressure_pair=surface_pressure_pair, &
      surface_temperature_pair=surface_temperature_pair, &
      surface_water_pair=surface_water_pair)
    expected_offset=RD_AIR*TEMPERATURE*LOG(surface_pressure_pair(2)/surface_pressure_pair(1))
    expected=expected_offset
    CALL check(status==STATUS_OK,'dry isothermal surface-pressure increase accepted',failures)
    CALL close_vector(delta,expected,1.0e-12_real64, &
      'dry isothermal surface-pressure increase is one analytic offset at every level',failures)
    CALL check(ALL(delta/=0.0_real64) .AND. &
      ABS(delta(1)-expected_offset)<=1.0e-12_real64*MAX(1.0_real64,ABS(expected_offset)), &
      'dry surface-pressure boundary produces a nonzero first-center increment',failures)
  END SUBROUTINE test_surface_pressure_dry_isothermal

  SUBROUTINE test_surface_temperature_water_change(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: pressure(4),tb(4),ta(4),wb(6,4),wa(6,4),delta(4),expected(4)
    REAL(real64) :: surface_pressure_pair(2),surface_temperature_pair(2)
    REAL(real64) :: surface_water_pair(6,2)
    INTEGER :: status

    CALL initialize_column(pressure,tb,wb,ta,wa)
    tb=275.0_real64; ta=tb
    wb=0.0_real64; wa=0.0_real64
    surface_pressure_pair=[110000.0_real64,120000.0_real64]
    surface_temperature_pair=[270.0_real64,295.0_real64]
    surface_water_pair=0.0_real64
    surface_water_pair(1,:)=[0.004_real64,0.012_real64]
    surface_water_pair(2,:)=[0.001_real64,0.003_real64]
    CALL hydrostatic_geopotential_increment(pressure,tb,wb,ta,wa,delta,status, &
      surface_pressure_pair=surface_pressure_pair, &
      surface_temperature_pair=surface_temperature_pair, &
      surface_water_pair=surface_water_pair)
    CALL expected_surface_increment(pressure,tb,wb,ta,wa, &
      surface_pressure_pair(1),surface_temperature_pair(1),surface_water_pair(:,1), &
      surface_pressure_pair(2),surface_temperature_pair(2),surface_water_pair(:,2),expected)
    CALL check(status==STATUS_OK,'joint surface temperature/water change accepted',failures)
    CALL close_vector(delta,expected,1.0e-12_real64, &
      'joint surface temperature and water change uses the boundary p-alpha trapezoid',failures)
    CALL check(ABS(delta(1))>1.0e-8_real64, &
      'joint surface temperature and water change produces a boundary increment',failures)
  END SUBROUTINE test_surface_temperature_water_change

  SUBROUTINE test_surface_no_change_is_exact_zero(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: pressure(4),tb(4),ta(4),wb(6,4),wa(6,4),delta(4)
    REAL(real64) :: surface_pressure_pair(2),surface_temperature_pair(2)
    REAL(real64) :: surface_water_pair(6,2)
    INTEGER :: status

    CALL initialize_column(pressure,tb,wb,ta,wa)
    surface_pressure_pair=[110000.0_real64,110000.0_real64]
    surface_temperature_pair=[280.0_real64,280.0_real64]
    surface_water_pair=0.0_real64
    surface_water_pair(1,:)=[0.006_real64,0.006_real64]
    surface_water_pair(2,:)=[0.001_real64,0.001_real64]
    delta=[-3.0_real64,7.0_real64,-11.0_real64,19.0_real64]
    CALL hydrostatic_geopotential_increment(pressure,tb,wb,ta,wa,delta,status, &
      surface_pressure_pair=surface_pressure_pair, &
      surface_temperature_pair=surface_temperature_pair, &
      surface_water_pair=surface_water_pair)
    CALL check(status==STATUS_OK,'unchanged center and surface column accepted',failures)
    CALL check(ALL(delta==0.0_real64),'unchanged center and surface inputs are exactly zero',failures)
  END SUBROUTINE test_surface_no_change_is_exact_zero

  SUBROUTINE expect_surface_failure_unchanged(pressure,tb,wb,ta,wa,delta,status, &
      surface_pressure_pair,surface_temperature_pair,surface_water_pair,failures,message)
    REAL(real64), INTENT(IN) :: pressure(:),tb(:),wb(:,:),ta(:),wa(:,:)
    REAL(real64), INTENT(INOUT) :: delta(:)
    INTEGER, INTENT(OUT) :: status
    REAL(real64), INTENT(IN) :: surface_pressure_pair(:),surface_temperature_pair(:), &
      surface_water_pair(:,:)
    INTEGER, INTENT(INOUT) :: failures
    CHARACTER(LEN=*), INTENT(IN) :: message
    REAL(real64) :: sentinel(SIZE(delta))

    sentinel=delta
    CALL hydrostatic_geopotential_increment(pressure,tb,wb,ta,wa,delta,status, &
      surface_pressure_pair=surface_pressure_pair, &
      surface_temperature_pair=surface_temperature_pair, &
      surface_water_pair=surface_water_pair)
    CALL check(status==STATUS_FAILED .AND. ALL(delta==sentinel),message,failures)
  END SUBROUTINE expect_surface_failure_unchanged

  SUBROUTINE test_surface_invalid_inputs_rollback(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: pressure(4),tb(4),ta(4),wb(6,4),wa(6,4),delta(4)
    REAL(real64) :: surface_pressure_pair(2),surface_temperature_pair(2)
    REAL(real64) :: surface_water_pair(6,2),bad_surface_water(5,2)
    INTEGER :: status

    CALL initialize_column(pressure,tb,wb,ta,wa)
    surface_pressure_pair=[110000.0_real64,120000.0_real64]
    surface_temperature_pair=[280.0_real64,280.0_real64]
    surface_water_pair=0.0_real64
    delta=[41.0_real64,42.0_real64,43.0_real64,44.0_real64]

    ! All three arrays are required together; this deliberately omits water.
    CALL hydrostatic_geopotential_increment(pressure,tb,wb,ta,wa,delta,status, &
      surface_pressure_pair=surface_pressure_pair, &
      surface_temperature_pair=surface_temperature_pair)
    CALL check(status==STATUS_FAILED .AND. ALL(delta==[41.0_real64,42.0_real64,43.0_real64,44.0_real64]), &
      'missing surface-water argument is rejected without changing delta',failures)

    surface_pressure_pair(1)=ieee_value(0.0_real64,ieee_quiet_nan)
    CALL expect_surface_failure_unchanged(pressure,tb,wb,ta,wa,delta,status, &
      surface_pressure_pair,surface_temperature_pair,surface_water_pair,failures, &
      'nonfinite surface pressure is rejected without changing delta')

    surface_pressure_pair=[90000.0_real64,120000.0_real64]
    CALL expect_surface_failure_unchanged(pressure,tb,wb,ta,wa,delta,status, &
      surface_pressure_pair,surface_temperature_pair,surface_water_pair,failures, &
      'surface pressure below the first center is rejected without changing delta')

    surface_pressure_pair=[110000.0_real64,120000.0_real64]
    bad_surface_water=0.0_real64
    CALL expect_surface_failure_unchanged(pressure,tb,wb,ta,wa,delta,status, &
      surface_pressure_pair,surface_temperature_pair,bad_surface_water,failures, &
      'wrong surface-water dimension is rejected without changing delta')
  END SUBROUTINE test_surface_invalid_inputs_rollback

END PROGRAM test_hydrostatic_increment
