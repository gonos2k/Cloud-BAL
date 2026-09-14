PROGRAM test_host_vapor_pressure
  USE, INTRINSIC :: iso_fortran_env, ONLY: int64,real64,real128
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite,ieee_positive_inf, &
    ieee_quiet_nan,ieee_value
  USE cloud_bal_wps_adapter, ONLY: host_vapor_pressure_column,solve_host_surface_pressure
  IMPLICIT NONE

  INTEGER :: failures
  REAL(real64), PARAMETER :: EXAMPLE_A=1.0_real64/220.0_real64
  REAL(real64), PARAMETER :: EXAMPLE_B=10.0_real64

  failures=0
  CALL test_literal_descending(failures)
  CALL test_reverse_levels(failures)
  CALL test_subterrain_and_equal_surface(failures)
  CALL test_surface_segment_threshold(failures)
  CALL test_zero_vapor(failures)
  CALL test_varying_q_and_temperature(failures)
  CALL test_no_above_top_tail(failures)
  CALL test_invalid_inputs(failures)
  CALL test_surface_pressure_solution(failures)
  CALL test_surface_pressure_humidity_compensation(failures)
  CALL test_surface_pressure_reverse_order(failures)
  CALL test_surface_pressure_nonunit_scale(failures)
  CALL test_surface_pressure_no_change(failures)
  CALL test_surface_pressure_coupled_response(failures)
  CALL test_surface_pressure_zero_response(failures)
  CALL test_surface_pressure_coupled_rejections(failures)
  CALL test_surface_pressure_rejections(failures)
  CALL test_surface_pressure_invalid_scalars(failures)
  CALL test_surface_pressure_invalid_size(failures)

  IF (failures/=0) THEN
    PRINT *, 'Host vapor pressure tests failed:',failures
    ERROR STOP 1
  END IF
  PRINT *, 'Host vapor pressure tests passed'

CONTAINS

  SUBROUTINE literal_column(pressure,temperature,vapor,height)
    REAL(real64), INTENT(OUT) :: pressure(:),temperature(:),vapor(:),height(:)

    pressure=(/1000.0_real64,800.0_real64,600.0_real64/)
    temperature=10.0_real64
    vapor=0.1_real64
    height=(/0.0_real64,10.0_real64,20.0_real64/)
  END SUBROUTINE literal_column

  SUBROUTINE test_surface_pressure_solution(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: pressure(3),temperature(3),vapor(3),height(3)
    REAL(real64) :: target,actual,desired
    LOGICAL :: ok

    CALL literal_column(pressure,temperature,vapor,height)
    desired=1020.0_real64
    ! target = native surface pressure - the complete represented vapor integral.
    target=(1.0_real64-EXAMPLE_A)*desired-EXAMPLE_B
    actual=-1.0_real64; ok=.FALSE.
    CALL solve_host_surface_pressure(pressure,temperature,vapor,height,100.0_real64,10.0_real64, &
      1.0_real64,target,30.0_real64,actual,ok)
    CALL check(ok,'surface-pressure solve accepted',failures)
    CALL check_near(actual,desired,1.0e-10_real64,1.0e-12_real64, &
      'surface-pressure analytic solution',failures)
  END SUBROUTINE test_surface_pressure_solution

  SUBROUTINE test_surface_pressure_humidity_compensation(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: pressure(3),temperature(3),vapor(3),height(3)
    REAL(real64) :: target,actual,desired
    LOGICAL :: ok

    CALL literal_column(pressure,temperature,vapor,height)
    vapor=0.2_real64
    target=1000.0_real64-160.0_real64/11.0_real64
    ! With q=.2, I(p_s)=p_s/120+55/3. The target is the baseline
    ! q=.1 dry pressure, so added vapor requires a compensating pressure rise.
    desired=(target+55.0_real64/3.0_real64)/(1.0_real64-1.0_real64/120.0_real64)
    actual=-1.0_real64; ok=.FALSE.
    CALL solve_host_surface_pressure(pressure,temperature,vapor,height,100.0_real64,10.0_real64, &
      1.0_real64,target,30.0_real64,actual,ok)
    CALL check(ok,'humidity-compensation surface-pressure solve accepted',failures)
    CALL check_near(actual,desired,1.0e-10_real64,1.0e-12_real64, &
      'humidity-compensation pressure solution',failures)
  END SUBROUTINE test_surface_pressure_humidity_compensation

  SUBROUTINE test_surface_pressure_reverse_order(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: pressure(3),temperature(3),vapor(3),height(3)
    REAL(real64) :: target,actual,desired
    LOGICAL :: ok

    pressure=(/1000.0_real64,600.0_real64,800.0_real64/)
    temperature=10.0_real64
    vapor=0.1_real64
    height=(/0.0_real64,20.0_real64,10.0_real64/)
    desired=1010.0_real64
    target=(1.0_real64-EXAMPLE_A)*desired-EXAMPLE_B
    actual=-1.0_real64; ok=.FALSE.
    CALL solve_host_surface_pressure(pressure,temperature,vapor,height,100.0_real64,10.0_real64, &
      1.0_real64,target,20.0_real64,actual,ok)
    CALL check(ok,'reverse-order surface-pressure solve accepted',failures)
    CALL check_near(actual,desired,1.0e-10_real64,1.0e-12_real64, &
      'reverse-order surface-pressure solution',failures)
  END SUBROUTINE test_surface_pressure_reverse_order

  SUBROUTINE test_surface_pressure_nonunit_scale(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: pressure(3),temperature(3),vapor(3),height(3)
    REAL(real64) :: target,actual,desired,scale
    LOGICAL :: ok

    CALL literal_column(pressure,temperature,vapor,height)
    scale=1.2_real64
    desired=1015.0_real64
    target=(scale-EXAMPLE_A)*desired-EXAMPLE_B
    actual=-1.0_real64; ok=.FALSE.
    CALL solve_host_surface_pressure(pressure,temperature,vapor,height,100.0_real64,10.0_real64, &
      scale,target,20.0_real64,actual,ok)
    CALL check(ok,'nonunit-scale surface-pressure solve accepted',failures)
    CALL check_near(actual,desired,1.0e-10_real64,1.0e-12_real64, &
      'nonunit-scale surface-pressure solution',failures)
  END SUBROUTINE test_surface_pressure_nonunit_scale

  SUBROUTINE test_surface_pressure_no_change(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: pressure(3),temperature(3),vapor(3),height(3)
    REAL(real64) :: target,actual
    LOGICAL :: ok

    CALL literal_column(pressure,temperature,vapor,height)
    ! Independent analytic baseline: I(1000)=160/11 Pa for the q=.1 column.
    target=REAL(REAL(pressure(1),real128)-REAL(160.0_real64/11.0_real64,real128),real64)
    actual=-1.0_real64; ok=.FALSE.
    CALL solve_host_surface_pressure(pressure,temperature,vapor,height,100.0_real64,10.0_real64, &
      1.0_real64,target,0.0_real64,actual,ok)
    CALL check(ok,'no-change surface-pressure solve accepted',failures)
    CALL check(same_scalar(actual,pressure(1)), &
      'no-change solve preserves the input pressure exactly',failures)
  END SUBROUTINE test_surface_pressure_no_change

  SUBROUTINE test_surface_pressure_coupled_response(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: pressure(3),temperature(3),vapor(3),height(3)
    REAL(real64) :: response(3),adjusted_height(3),expected_height(3)
    REAL(real64) :: truth,target,integral
    REAL(real64) :: actual
    LOGICAL :: ok,valid

    CALL coupled_fixture(pressure,temperature,vapor,height,response,truth,target)
    expected_height=height+response*LOG(truth/pressure(1))
    adjusted_height=(/-11.0_real64,-22.0_real64,-33.0_real64/)
    actual=-12345.0_real64; ok=.FALSE.
    CALL solve_host_surface_pressure(pressure,temperature,vapor,height,287.0_real64,9.81_real64, &
      1.0_real64,target,100.0_real64,actual,ok,response,adjusted_height)
    CALL check(ok,'coupled surface-pressure solve accepted',failures)
    CALL check_near(actual,truth,1.0e-7_real64,1.0e-13_real64, &
      'coupled surface-pressure solution',failures)
    CALL check(ALL(ieee_is_finite(adjusted_height)),'coupled heights are finite',failures)
    CALL check(ALL(ABS(adjusted_height-expected_height)<=1.0e-8_real64), &
      'coupled heights follow the logarithmic response',failures)
    CALL check(same_bits(height,(/0.0_real64,1000.0_real64,2000.0_real64/)), &
      'coupled solve preserves input heights',failures)

    pressure(1)=actual
    CALL host_vapor_pressure_column(pressure,temperature,vapor,adjusted_height, &
      287.0_real64,9.81_real64,integral,valid)
    CALL check(valid,'coupled solution profile remains physical',failures)
    CALL check_near(actual-integral,target,1.0e-7_real64,1.0e-13_real64, &
      'coupled solution closes the target equation',failures)
  END SUBROUTINE test_surface_pressure_coupled_response

  SUBROUTINE test_surface_pressure_zero_response(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: pressure(3),temperature(3),vapor(3),height(3)
    REAL(real64) :: response(3),adjusted_height(3)
    REAL(real64) :: target,old_actual,coupled_actual
    LOGICAL :: old_ok,coupled_ok

    CALL literal_column(pressure,temperature,vapor,height)
    target=(1.0_real64-EXAMPLE_A)*1020.0_real64-EXAMPLE_B
    response=0.0_real64
    adjusted_height=(/-101.0_real64,-202.0_real64,-303.0_real64/)
    old_actual=-1.0_real64; old_ok=.FALSE.
    coupled_actual=-1.0_real64; coupled_ok=.FALSE.
    CALL solve_host_surface_pressure(pressure,temperature,vapor,height,100.0_real64,10.0_real64, &
      1.0_real64,target,30.0_real64,old_actual,old_ok)
    CALL solve_host_surface_pressure(pressure,temperature,vapor,height,100.0_real64,10.0_real64, &
      1.0_real64,target,30.0_real64,coupled_actual,coupled_ok,response,adjusted_height)
    CALL check(old_ok .AND. coupled_ok,'zero-response solves accepted',failures)
    CALL check_near(coupled_actual,old_actual,1.0e-10_real64,1.0e-13_real64, &
      'zero-response pressure matches the existing solver',failures)
    CALL check(same_bits(adjusted_height,height), &
      'zero-response adjusted heights equal the original heights',failures)
  END SUBROUTINE test_surface_pressure_zero_response

  SUBROUTINE test_surface_pressure_coupled_rejections(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: pressure(3),temperature(3),vapor(3),height(3)
    REAL(real64) :: response(3),adjusted_height(3),adjusted_before(3)
    REAL(real64) :: response_short(2),nan_value
    REAL(real64) :: actual,target,truth,crossing_integral
    REAL(real64) :: pressure_crossing(3)
    REAL(real64) :: pressure4(4),temperature4(4),vapor4(4),height4(4)
    REAL(real64) :: response4(4),adjusted4(4),adjusted4_before(4)
    LOGICAL :: ok,valid

    CALL coupled_fixture(pressure,temperature,vapor,height,response,truth,target)

    ! The pressure cap excludes the manufactured root; neither output may commit.
    adjusted_height=(/-11.0_real64,-22.0_real64,-33.0_real64/)
    adjusted_before=adjusted_height
    actual=-12345.0_real64; ok=.TRUE.
    CALL solve_host_surface_pressure(pressure,temperature,vapor,height,287.0_real64,9.81_real64, &
      1.0_real64,target,10.0_real64,actual,ok,response,adjusted_height)
    CALL expect_coupled_rollback(pressure,actual,ok,adjusted_height,adjusted_before, &
      'pressure cap',failures)

    ! A response with the wrong length is malformed and must be transactional.
    response_short=(/0.0_real64,8000.0_real64/)
    adjusted_height=(/-44.0_real64,-55.0_real64,-66.0_real64/)
    adjusted_before=adjusted_height
    actual=-12345.0_real64; ok=.TRUE.
    CALL solve_host_surface_pressure(pressure,temperature,vapor,height,287.0_real64,9.81_real64, &
      1.0_real64,target,100.0_real64,actual,ok, &
      height_log_ps_response=response_short,adjusted_height=adjusted_height)
    CALL expect_coupled_rollback(pressure,actual,ok,adjusted_height,adjusted_before, &
      'malformed response length',failures)

    ! Surface response is required to be zero; all represented above-ground
    ! levels must carry the same nonnegative coefficient.
    response=(/1.0_real64,8000.0_real64,8000.0_real64/)
    adjusted_height=(/-77.0_real64,-88.0_real64,-99.0_real64/)
    adjusted_before=adjusted_height
    actual=-12345.0_real64; ok=.TRUE.
    CALL solve_host_surface_pressure(pressure,temperature,vapor,height,287.0_real64,9.81_real64, &
      1.0_real64,target,100.0_real64,actual,ok,response,adjusted_height)
    CALL expect_coupled_rollback(pressure,actual,ok,adjusted_height,adjusted_before, &
      'nonzero surface response',failures)

    response=(/0.0_real64,8000.0_real64,7000.0_real64/)
    adjusted_height=(/-111.0_real64,-222.0_real64,-333.0_real64/)
    adjusted_before=adjusted_height
    actual=-12345.0_real64; ok=.TRUE.
    CALL solve_host_surface_pressure(pressure,temperature,vapor,height,287.0_real64,9.81_real64, &
      1.0_real64,target,100.0_real64,actual,ok,response,adjusted_height)
    CALL expect_coupled_rollback(pressure,actual,ok,adjusted_height,adjusted_before, &
      'nonconstant above-ground response',failures)

    nan_value=ieee_value(0.0_real64,ieee_quiet_nan)
    response=(/0.0_real64,nan_value,8000.0_real64/)
    adjusted_height=(/-121.0_real64,-232.0_real64,-343.0_real64/)
    adjusted_before=adjusted_height
    actual=-12345.0_real64; ok=.TRUE.
    CALL solve_host_surface_pressure(pressure,temperature,vapor,height,287.0_real64,9.81_real64, &
      1.0_real64,target,100.0_real64,actual,ok,response,adjusted_height)
    CALL expect_coupled_rollback(pressure,actual,ok,adjusted_height,adjusted_before, &
      'nonfinite response',failures)

    ! A below-ground level may not carry a response coefficient.
    pressure4=(/100000.0_real64,120000.0_real64,80000.0_real64,60000.0_real64/)
    temperature4=(/280.0_real64,279.0_real64,275.0_real64,270.0_real64/)
    vapor4=0.01_real64
    height4=(/0.0_real64,-50.0_real64,1000.0_real64,2000.0_real64/)
    response4=(/0.0_real64,1.0_real64,8000.0_real64,8000.0_real64/)
    adjusted4=(/-1.0_real64,-2.0_real64,-3.0_real64,-4.0_real64/)
    adjusted4_before=adjusted4
    actual=-12345.0_real64; ok=.TRUE.
    CALL solve_host_surface_pressure(pressure4,temperature4,vapor4,height4, &
      287.0_real64,9.81_real64,1.0_real64,99900.0_real64,100.0_real64,actual,ok, &
      response4,adjusted4)
    CALL expect_coupled_rollback(pressure4,actual,ok,adjusted4,adjusted4_before, &
      'below-ground response',failures)

    ! Supplying only one of the coupled optional arguments is invalid.
    response=(/0.0_real64,8000.0_real64,8000.0_real64/)
    adjusted_height=(/-131.0_real64,-242.0_real64,-353.0_real64/)
    adjusted_before=adjusted_height
    actual=-12345.0_real64; ok=.TRUE.
    CALL solve_host_surface_pressure(pressure,temperature,vapor,height,287.0_real64,9.81_real64, &
      1.0_real64,target,100.0_real64,actual,ok, &
      height_log_ps_response=response)
    CALL expect_coupled_rollback(pressure,actual,ok,adjusted_height,adjusted_before, &
      'missing adjusted-height output',failures)

    adjusted_height=(/-141.0_real64,-252.0_real64,-363.0_real64/)
    adjusted_before=adjusted_height
    actual=-12345.0_real64; ok=.TRUE.
    CALL solve_host_surface_pressure(pressure,temperature,vapor,height,287.0_real64,9.81_real64, &
      1.0_real64,target,100.0_real64,actual,ok,adjusted_height=adjusted_height)
    CALL expect_coupled_rollback(pressure,actual,ok,adjusted_height,adjusted_before, &
      'missing height response',failures)

    ! A root outside the unchanged active-level interval is rejected.
    response=0.0_real64
    pressure_crossing=pressure; pressure_crossing(1)=70000.0_real64
    CALL host_vapor_pressure_column(pressure_crossing,temperature,vapor,height, &
      287.0_real64,9.81_real64,crossing_integral,valid)
    CALL check(valid,'classification-change target profile is valid',failures)
    target=70000.0_real64-crossing_integral
    adjusted_height=(/-151.0_real64,-262.0_real64,-373.0_real64/)
    adjusted_before=adjusted_height
    actual=-12345.0_real64; ok=.TRUE.
    CALL solve_host_surface_pressure(pressure,temperature,vapor,height,287.0_real64,9.81_real64, &
      1.0_real64,target,50000.0_real64,actual,ok,response,adjusted_height)
    CALL expect_coupled_rollback(pressure,actual,ok,adjusted_height,adjusted_before, &
      'active-level classification change',failures)
  END SUBROUTINE test_surface_pressure_coupled_rejections

  SUBROUTINE coupled_fixture(pressure,temperature,vapor,height,response,truth,target)
    REAL(real64), INTENT(OUT) :: pressure(:),temperature(:),vapor(:),height(:)
    REAL(real64), INTENT(OUT) :: response(:)
    REAL(real64), INTENT(OUT) :: truth,target
    REAL(real64) :: trial_pressure(SIZE(pressure)),trial_height(SIZE(height))

    pressure=(/100000.0_real64,80000.0_real64,60000.0_real64/)
    temperature=(/280.0_real64,275.0_real64,270.0_real64/)
    vapor=0.01_real64
    height=(/0.0_real64,1000.0_real64,2000.0_real64/)
    response=(/0.0_real64,8000.0_real64,8000.0_real64/)
    truth=pressure(1)+20.0_real64
    trial_pressure=pressure; trial_pressure(1)=truth
    trial_height=height+response*LOG(truth/pressure(1))
    target=truth-hand_three_level_integral(trial_pressure,temperature,vapor, &
      trial_height,287.0_real64,9.81_real64)
  END SUBROUTINE coupled_fixture

  PURE REAL(real64) FUNCTION hand_three_level_integral(pressure,temperature,vapor,height, &
      gas_constant,gravity)
    REAL(real64), INTENT(IN) :: pressure(:),temperature(:),vapor(:),height(:)
    REAL(real64), INTENT(IN) :: gas_constant,gravity
    REAL(real128) :: total,qbar,rhobar
    INTEGER :: k

    total=0.0_real128
    DO k=1,2
      qbar=0.5_real128*(REAL(vapor(k),real128)+REAL(vapor(k+1),real128))
      rhobar=0.5_real128*(REAL(pressure(k),real128)/ &
        (REAL(gas_constant,real128)*REAL(temperature(k),real128))+ &
        REAL(pressure(k+1),real128)/(REAL(gas_constant,real128)* &
        REAL(temperature(k+1),real128)))
      total=total+REAL(gravity,real128)*qbar/(1.0_real128+qbar)*rhobar* &
        REAL(height(k+1)-height(k),real128)
    END DO
    hand_three_level_integral=REAL(total,real64)
  END FUNCTION hand_three_level_integral

  SUBROUTINE expect_coupled_rollback(pressure,actual,ok,adjusted_height, &
      adjusted_before,label,failures)
    REAL(real64), INTENT(IN) :: pressure(:),actual,adjusted_height(:),adjusted_before(:)
    LOGICAL, INTENT(IN) :: ok
    CHARACTER(LEN=*), INTENT(IN) :: label
    INTEGER, INTENT(INOUT) :: failures

    CALL check(.NOT.ok,'rejected coupled solve: '//TRIM(label),failures)
    CALL check(same_scalar(actual,pressure(1)), &
      'coupled failure preserves input pressure for '//TRIM(label),failures)
    CALL check(same_bits(adjusted_height,adjusted_before), &
      'coupled failure preserves adjusted heights for '//TRIM(label),failures)
  END SUBROUTINE expect_coupled_rollback

  SUBROUTINE test_surface_pressure_rejections(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: pressure(3),temperature(3),vapor(3),height(3)

    CALL literal_column(pressure,temperature,vapor,height)
    CALL expect_solver_invalid(pressure,temperature,vapor,height,100.0_real64,10.0_real64, &
      1.0_real64,(1.0_real64-EXAMPLE_A)*1040.0_real64-EXAMPLE_B,30.0_real64, &
      'increment cap',failures)
    CALL expect_solver_invalid(pressure,temperature,vapor,height,100.0_real64,10.0_real64, &
      1.0_real64,(1.0_real64-EXAMPLE_A)*750.0_real64-EXAMPLE_B,1000.0_real64, &
      'crossing the 800 Pa level',failures)
    CALL expect_solver_invalid(pressure,temperature,vapor,height,100.0_real64,10.0_real64, &
      1.0_real64,(1.0_real64-EXAMPLE_A)*550.0_real64-EXAMPLE_B,1000.0_real64, &
      'crossing the 600 Pa level',failures)
    CALL expect_solver_invalid(pressure,temperature,vapor,height,100.0_real64,10.0_real64, &
      1.0e-6_real64,1.0_real64,1000.0_real64,'nonpositive affine slope',failures)
  END SUBROUTINE test_surface_pressure_rejections

  SUBROUTINE test_surface_pressure_invalid_scalars(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: pressure(3),temperature(3),vapor(3),height(3),nan_value
    REAL(real64) :: target

    CALL literal_column(pressure,temperature,vapor,height)
    target=(1.0_real64-EXAMPLE_A)*1020.0_real64-EXAMPLE_B
    nan_value=ieee_value(0.0_real64,ieee_quiet_nan)

    CALL expect_solver_invalid(pressure,temperature,vapor,height,-100.0_real64,10.0_real64, &
      1.0_real64,target,30.0_real64,'negative gas constant',failures)
    CALL expect_solver_invalid(pressure,temperature,vapor,height,100.0_real64,-10.0_real64, &
      1.0_real64,target,30.0_real64,'negative gravity',failures)
    CALL expect_solver_invalid(pressure,temperature,vapor,height,100.0_real64,10.0_real64, &
      -1.0_real64,target,30.0_real64,'negative surface scale',failures)
    CALL expect_solver_invalid(pressure,temperature,vapor,height,100.0_real64,10.0_real64, &
      1.0_real64,-1.0_real64,30.0_real64,'negative target dry pressure',failures)
    CALL expect_solver_invalid(pressure,temperature,vapor,height,100.0_real64,10.0_real64, &
      1.0_real64,target,-1.0_real64,'negative increment cap',failures)
    CALL expect_solver_invalid(pressure,temperature,vapor,height,nan_value,10.0_real64, &
      1.0_real64,target,30.0_real64,'NaN gas constant',failures)
    CALL expect_solver_invalid(pressure,temperature,vapor,height,100.0_real64,nan_value, &
      1.0_real64,target,30.0_real64,'NaN gravity',failures)
    CALL expect_solver_invalid(pressure,temperature,vapor,height,100.0_real64,10.0_real64, &
      nan_value,target,30.0_real64,'NaN surface scale',failures)
    CALL expect_solver_invalid(pressure,temperature,vapor,height,100.0_real64,10.0_real64, &
      1.0_real64,nan_value,30.0_real64,'NaN target dry pressure',failures)
    CALL expect_solver_invalid(pressure,temperature,vapor,height,100.0_real64,10.0_real64, &
      1.0_real64,target,nan_value,'NaN increment cap',failures)
    CALL expect_solver_invalid(pressure,temperature,vapor,height,100.0_real64,10.0_real64, &
      HUGE(1.0_real64),target,30.0_real64,'finite overflowing terrain scale',failures)
  END SUBROUTINE test_surface_pressure_invalid_scalars

  SUBROUTINE test_surface_pressure_invalid_size(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: pressure(2),temperature(2),vapor(2),height(2)
    REAL(real64) :: pressure_empty(0),temperature_empty(0),vapor_empty(0),height_empty(0)
    REAL(real64) :: actual
    LOGICAL :: ok

    pressure=(/1000.0_real64,800.0_real64/)
    temperature=10.0_real64; vapor=0.1_real64; height=(/0.0_real64,10.0_real64/)
    actual=-1.0_real64; ok=.TRUE.
    CALL solve_host_surface_pressure(pressure,temperature,vapor,height,100.0_real64,10.0_real64, &
      1.0_real64,900.0_real64,100.0_real64,actual,ok)
    CALL check(.NOT.ok,'fewer than three levels rejected by solve',failures)
    CALL check(same_scalar(actual,pressure(1)), &
      'short-column failure preserves the input pressure',failures)

    actual=-1.0_real64; ok=.TRUE.
    CALL solve_host_surface_pressure(pressure_empty,temperature_empty,vapor_empty,height_empty, &
      100.0_real64,10.0_real64,1.0_real64,900.0_real64,100.0_real64,actual,ok)
    CALL check(.NOT.ok,'empty column rejected by solve',failures)
    CALL check(actual==0.0_real64,'empty-column failure returns zero',failures)
  END SUBROUTINE test_surface_pressure_invalid_size

  SUBROUTINE expect_solver_invalid(pressure,temperature,vapor,height,gas_constant,gravity, &
      surface_scale,target,max_increment,label,failures)
    REAL(real64), INTENT(IN) :: pressure(:),temperature(:),vapor(:),height(:)
    REAL(real64), INTENT(IN) :: gas_constant,gravity,surface_scale
    REAL(real64), INTENT(IN) :: target,max_increment
    CHARACTER(LEN=*), INTENT(IN) :: label
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: actual
    LOGICAL :: ok

    actual=-12345.0_real64; ok=.TRUE.
    CALL solve_host_surface_pressure(pressure,temperature,vapor,height,gas_constant,gravity, &
      surface_scale,target,max_increment,actual,ok)
    CALL check(.NOT.ok,'rejected surface-pressure '//TRIM(label),failures)
    CALL check(same_scalar(actual,pressure(1)), &
      'failure preserves input pressure for '//TRIM(label),failures)
  END SUBROUTINE expect_solver_invalid

  SUBROUTINE test_literal_descending(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: pressure(3),temperature(3),vapor(3),height(3)

    pressure=(/1000.0_real64,800.0_real64,600.0_real64/)
    temperature=10.0_real64
    vapor=0.1_real64
    height=(/0.0_real64,10.0_real64,20.0_real64/)
    CALL expect_valid(pressure,temperature,vapor,height,100.0_real64,10.0_real64, &
      160.0_real64/11.0_real64,'literal descending WRF case',failures)
  END SUBROUTINE test_literal_descending

  SUBROUTINE test_reverse_levels(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: pressure(3),temperature(3),vapor(3),height(3)

    ! The surface remains at index one while the pressure levels are reversed.
    pressure=(/1000.0_real64,600.0_real64,800.0_real64/)
    temperature=10.0_real64
    vapor=0.1_real64
    height=(/0.0_real64,20.0_real64,10.0_real64/)
    CALL expect_valid(pressure,temperature,vapor,height,100.0_real64,10.0_real64, &
      160.0_real64/11.0_real64,'literal increasing pressure case',failures)

    ! Reverse the pressure-level records together with their thermodynamic and
    ! geometric fields; the physical column must retain the same integral.
    temperature=(/10.0_real64,40.0_real64,20.0_real64/)
    vapor=(/0.0_real64,0.4_real64,0.2_real64/)
    height=(/0.0_real64,25.0_real64,10.0_real64/)
    CALL expect_valid(pressure,temperature,vapor,height,100.0_real64,10.0_real64, &
      70.0_real64/11.0_real64+495.0_real64/52.0_real64, &
      'reversed varying pressure-level records',failures)
  END SUBROUTINE test_reverse_levels

  SUBROUTINE test_subterrain_and_equal_surface(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: pressure(4),temperature(4),vapor(4),height(4)

    pressure=(/1000.0_real64,1200.0_real64,800.0_real64,600.0_real64/)
    temperature=10.0_real64
    vapor=0.1_real64
    height=(/0.0_real64,-10.0_real64,10.0_real64,20.0_real64/)
    CALL expect_valid(pressure,temperature,vapor,height,100.0_real64,10.0_real64, &
      160.0_real64/11.0_real64,'subterrain level ignored',failures)

    pressure=(/1000.0_real64,1000.0_real64,800.0_real64,600.0_real64/)
    height=(/0.0_real64,5.0_real64,10.0_real64,20.0_real64/)
    CALL expect_valid(pressure,temperature,vapor,height,100.0_real64,10.0_real64, &
      160.0_real64/11.0_real64,'surface-pressure equality ignored',failures)
  END SUBROUTINE test_subterrain_and_equal_surface

  SUBROUTINE test_surface_segment_threshold(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: pressure(3),temperature(3),vapor(3),height(3)

    pressure=(/1000.0_real64,800.0_real64,600.0_real64/)
    temperature=10.0_real64
    vapor=0.1_real64
    height=(/0.0_real64,0.1_real64,10.0_real64/)
    ! WRF integ_moist excludes a surface segment unless dz is strictly > 0.1 m.
    CALL expect_valid(pressure,temperature,vapor,height,100.0_real64,10.0_real64, &
      69.3_real64/11.0_real64,'surface segment threshold',failures)
  END SUBROUTINE test_surface_segment_threshold

  SUBROUTINE test_zero_vapor(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: pressure(3),temperature(3),vapor(3),height(3)

    pressure=(/1000.0_real64,800.0_real64,600.0_real64/)
    temperature=(/280.0_real64,275.0_real64,270.0_real64/)
    vapor=0.0_real64
    height=(/0.0_real64,100.0_real64,250.0_real64/)
    CALL expect_valid(pressure,temperature,vapor,height,287.0_real64,9.81_real64, &
      0.0_real64,'zero vapor',failures)
  END SUBROUTINE test_zero_vapor

  SUBROUTINE test_varying_q_and_temperature(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: pressure(3),temperature(3),vapor(3),height(3)
    REAL(real64) :: expected

    pressure=(/1000.0_real64,800.0_real64,600.0_real64/)
    temperature=(/10.0_real64,20.0_real64,40.0_real64/)
    vapor=(/0.0_real64,0.2_real64,0.4_real64/)
    height=(/0.0_real64,10.0_real64,25.0_real64/)
    ! Surface layer: 70/11 Pa.  Upper layer: 495/52 Pa.
    expected=70.0_real64/11.0_real64+495.0_real64/52.0_real64
    CALL expect_valid(pressure,temperature,vapor,height,100.0_real64,10.0_real64, &
      expected,'varying vapor and temperature',failures)
  END SUBROUTINE test_varying_q_and_temperature

  SUBROUTINE test_no_above_top_tail(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: pressure(4),temperature(4),vapor(4),height(4)

    pressure=(/1000.0_real64,800.0_real64,600.0_real64,400.0_real64/)
    temperature=10.0_real64
    vapor=0.1_real64
    height=(/0.0_real64,10.0_real64,20.0_real64,30.0_real64/)
    CALL expect_valid(pressure,temperature,vapor,height,100.0_real64,10.0_real64, &
      210.0_real64/11.0_real64,'no above-top tail',failures)
  END SUBROUTINE test_no_above_top_tail

  SUBROUTINE test_invalid_inputs(failures)
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: pressure(3),temperature(3),vapor(3),height(3)
    REAL(real64) :: pressure4(4),temperature4(4),vapor4(4),height4(4)
    REAL(real64) :: pressure2(2),temperature2(2),vapor2(2),height2(2)
    REAL(real64) :: bad(3)
    REAL(real64) :: nan_value,inf_value

    pressure=(/1000.0_real64,800.0_real64,600.0_real64/)
    temperature=10.0_real64
    vapor=0.1_real64
    height=(/0.0_real64,10.0_real64,20.0_real64/)
    nan_value=ieee_value(0.0_real64,ieee_quiet_nan)
    inf_value=ieee_value(0.0_real64,ieee_positive_inf)

    bad=pressure; bad(2)=nan_value
    CALL expect_invalid(bad,temperature,vapor,height,100.0_real64,10.0_real64, &
      'NaN pressure',failures)
    bad=pressure; bad(2)=inf_value
    CALL expect_invalid(bad,temperature,vapor,height,100.0_real64,10.0_real64, &
      'infinite pressure',failures)
    bad=temperature; bad(2)=nan_value
    CALL expect_invalid(pressure,bad,vapor,height,100.0_real64,10.0_real64, &
      'NaN temperature',failures)
    bad=temperature; bad(2)=inf_value
    CALL expect_invalid(pressure,bad,vapor,height,100.0_real64,10.0_real64, &
      'infinite temperature',failures)
    bad=vapor; bad(2)=nan_value
    CALL expect_invalid(pressure,temperature,bad,height,100.0_real64,10.0_real64, &
      'NaN vapor',failures)
    bad=vapor; bad(2)=inf_value
    CALL expect_invalid(pressure,temperature,bad,height,100.0_real64,10.0_real64, &
      'infinite vapor',failures)
    bad=height; bad(2)=nan_value
    CALL expect_invalid(pressure,temperature,vapor,bad,100.0_real64,10.0_real64, &
      'NaN height',failures)
    bad=height; bad(2)=inf_value
    CALL expect_invalid(pressure,temperature,vapor,bad,100.0_real64,10.0_real64, &
      'infinite height',failures)
    CALL expect_invalid(pressure,temperature,vapor,height,nan_value,10.0_real64, &
      'NaN gas constant',failures)
    CALL expect_invalid(pressure,temperature,vapor,height,inf_value,10.0_real64, &
      'infinite gas constant',failures)
    CALL expect_invalid(pressure,temperature,vapor,height,100.0_real64,nan_value, &
      'NaN gravity',failures)
    CALL expect_invalid(pressure,temperature,vapor,height,100.0_real64,inf_value, &
      'infinite gravity',failures)

    bad=pressure; bad(2)=0.0_real64
    CALL expect_invalid(bad,temperature,vapor,height,100.0_real64,10.0_real64, &
      'zero pressure',failures)
    bad=temperature; bad(2)=0.0_real64
    CALL expect_invalid(pressure,bad,vapor,height,100.0_real64,10.0_real64, &
      'zero temperature',failures)
    CALL expect_invalid(pressure,temperature,vapor,height,0.0_real64,10.0_real64, &
      'zero gas constant',failures)
    CALL expect_invalid(pressure,temperature,vapor,height,100.0_real64,0.0_real64, &
      'zero gravity',failures)

    pressure4=(/1000.0_real64,800.0_real64,800.0_real64,600.0_real64/)
    temperature4=10.0_real64; vapor4=0.1_real64
    height4=(/0.0_real64,10.0_real64,20.0_real64,30.0_real64/)
    CALL expect_invalid(pressure4,temperature4,vapor4,height4,100.0_real64,10.0_real64, &
      'duplicate pressure',failures)

    pressure4=(/1000.0_real64,800.0_real64,900.0_real64,700.0_real64/)
    CALL expect_invalid(pressure4,temperature4,vapor4,height4,100.0_real64,10.0_real64, &
      'nonmonotonic pressure',failures)

    pressure4=(/1000.0_real64,1200.0_real64,1300.0_real64,1400.0_real64/)
    CALL expect_invalid(pressure4,temperature4,vapor4,height4,100.0_real64,10.0_real64, &
      'no above-ground level',failures)

    bad=height; bad(3)=9.0_real64
    CALL expect_invalid(pressure,temperature,vapor,bad,100.0_real64,10.0_real64, &
      'decreasing above-ground height',failures)

    pressure2=(/1000.0_real64,800.0_real64/)
    temperature2=10.0_real64; vapor2=0.1_real64; height2=(/0.0_real64,10.0_real64/)
    CALL expect_invalid(pressure2,temperature2,vapor2,height2,100.0_real64,10.0_real64, &
      'fewer than three levels',failures)
    CALL expect_invalid(pressure,temperature2,vapor,height,100.0_real64,10.0_real64, &
      'mismatched array lengths',failures)

    bad=vapor; bad(2)=-1.0e-3_real64
    CALL expect_invalid(pressure,temperature,bad,height,100.0_real64,10.0_real64, &
      'negative vapor',failures)
    bad=vapor; bad(2)=1.0_real64
    CALL expect_invalid(pressure,temperature,bad,height,100.0_real64,10.0_real64, &
      'vapor at one',failures)

    pressure4=(/1.0e300_real64,8.0e299_real64,6.0e299_real64,4.0e299_real64/)
    temperature4=1.0_real64; vapor4=0.5_real64
    height4=(/0.0_real64,1.0e100_real64,2.0e100_real64,3.0e100_real64/)
    CALL expect_invalid(pressure4,temperature4,vapor4,height4,1.0_real64,1.0e300_real64, &
      'finite inputs with overflowing result',failures)
  END SUBROUTINE test_invalid_inputs

  SUBROUTINE expect_valid(pressure,temperature,vapor,height,gas_constant,gravity, &
      expected,label,failures)
    REAL(real64), INTENT(IN) :: pressure(:),temperature(:),vapor(:),height(:)
    REAL(real64), INTENT(IN) :: gas_constant,gravity,expected
    CHARACTER(LEN=*), INTENT(IN) :: label
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: pressure_before(SIZE(pressure)),temperature_before(SIZE(temperature))
    REAL(real64) :: vapor_before(SIZE(vapor)),height_before(SIZE(height))
    REAL(real64) :: result,gas_before,gravity_before
    LOGICAL :: ok

    pressure_before=pressure; temperature_before=temperature
    vapor_before=vapor; height_before=height
    gas_before=gas_constant; gravity_before=gravity
    result=-HUGE(1.0_real64); ok=.FALSE.
    CALL host_vapor_pressure_column(pressure,temperature,vapor,height,gas_constant,gravity, &
      result,ok)
    CALL check(ok,'accepted '//TRIM(label),failures)
    CALL check(ieee_is_finite(result),'finite result for '//TRIM(label),failures)
    CALL check_near(result,expected,1.0e-11_real64,1.0e-12_real64,label,failures)
    CALL check(same_bits(pressure,pressure_before) .AND. &
      same_bits(temperature,temperature_before) .AND. same_bits(vapor,vapor_before) .AND. &
      same_bits(height,height_before) .AND. same_scalar(gas_constant,gas_before) .AND. &
      same_scalar(gravity,gravity_before),'inputs preserved for '//TRIM(label),failures)
  END SUBROUTINE expect_valid

  SUBROUTINE expect_invalid(pressure,temperature,vapor,height,gas_constant,gravity, &
      label,failures)
    REAL(real64), INTENT(IN) :: pressure(:),temperature(:),vapor(:),height(:)
    REAL(real64), INTENT(IN) :: gas_constant,gravity
    CHARACTER(LEN=*), INTENT(IN) :: label
    INTEGER, INTENT(INOUT) :: failures
    REAL(real64) :: pressure_before(SIZE(pressure)),temperature_before(SIZE(temperature))
    REAL(real64) :: vapor_before(SIZE(vapor)),height_before(SIZE(height))
    REAL(real64) :: result,gas_before,gravity_before
    LOGICAL :: ok

    pressure_before=pressure; temperature_before=temperature
    vapor_before=vapor; height_before=height
    gas_before=gas_constant; gravity_before=gravity
    result=-12345.0_real64; ok=.TRUE.
    CALL host_vapor_pressure_column(pressure,temperature,vapor,height,gas_constant,gravity, &
      result,ok)
    CALL check(.NOT.ok,'rejected '//TRIM(label),failures)
    CALL check(result==0.0_real64,'zero result for '//TRIM(label),failures)
    CALL check(same_bits(pressure,pressure_before) .AND. &
      same_bits(temperature,temperature_before) .AND. same_bits(vapor,vapor_before) .AND. &
      same_bits(height,height_before) .AND. same_scalar(gas_constant,gas_before) .AND. &
      same_scalar(gravity,gravity_before),'invalid inputs preserved for '//TRIM(label),failures)
  END SUBROUTINE expect_invalid

  SUBROUTINE check(condition,label,failures)
    LOGICAL, INTENT(IN) :: condition
    CHARACTER(LEN=*), INTENT(IN) :: label
    INTEGER, INTENT(INOUT) :: failures
    IF (.NOT.condition) THEN
      failures=failures+1
      PRINT *, 'FAIL: ',TRIM(label)
    END IF
  END SUBROUTINE check

  SUBROUTINE check_near(actual,expected,atol,rtol,label,failures)
    REAL(real64), INTENT(IN) :: actual,expected,atol,rtol
    CHARACTER(LEN=*), INTENT(IN) :: label
    INTEGER, INTENT(INOUT) :: failures
    IF (.NOT.ieee_is_finite(actual) .OR. ABS(actual-expected)>atol+ &
        rtol*MAX(ABS(actual),ABS(expected))) THEN
      failures=failures+1
      PRINT *, 'FAIL: ',TRIM(label),' actual=',actual,' expected=',expected
    END IF
  END SUBROUTINE check_near

  PURE LOGICAL FUNCTION same_bits(first,second)
    REAL(real64), INTENT(IN) :: first(:),second(:)
    IF (SIZE(first)/=SIZE(second)) THEN
      same_bits=.FALSE.
    ELSE
      same_bits=ALL(TRANSFER(first,0_int64,SIZE(first))== &
        TRANSFER(second,0_int64,SIZE(second)))
    END IF
  END FUNCTION same_bits

  PURE LOGICAL FUNCTION same_scalar(first,second)
    REAL(real64), INTENT(IN) :: first,second
    same_scalar=TRANSFER(first,0_int64)==TRANSFER(second,0_int64)
  END FUNCTION same_scalar

END PROGRAM test_host_vapor_pressure
