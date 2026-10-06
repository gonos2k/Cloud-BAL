PROGRAM test_thermodynamic_constraints
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32,int64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value,ieee_quiet_nan,ieee_positive_inf
  USE cloud_bal_state
  USE cloud_bal_column_physics, ONLY: hydrostatic_pressure_alpha, &
    evaluate_interior_hydrostatic_residual,hydrostatic_constraint_summary, &
    HYDRO_REASON_MISSING_SUPPORT
  IMPLICIT NONE

  TYPE(cloud_bal_state_type) :: state
  TYPE(hydrostatic_constraint_summary) :: summary
  LOGICAL :: requested(1,1,2),assessable(1,1,2)
  REAL(real64) :: residual(1,1,2),alpha,water(6),pressure(3),expected
  INTEGER(int32) :: reason(1,1,2)
  INTEGER :: failures,k

  failures=0
  CALL test_pressure_alpha_nonfinite(failures)
  CALL make_state(state)
  requested=.TRUE.
  water=[0.008_real64,0.001_real64,0.0005_real64,0.0002_real64,0.0003_real64,0.0001_real64]
  pressure=[90000.0_real64,60000.0_real64,30000.0_real64]
  alpha=hydrostatic_pressure_alpha(pressure(1),280.0_real64,water)
  state%pressure%value(1,1,:)=REAL(pressure,real32)
  state%temperature%value=280.0_real32
  state%vapor%value=REAL(water(1),real32)
  state%cloud_water%value=REAL(water(2),real32)
  state%cloud_ice%value=REAL(water(3),real32)
  state%rain%value=REAL(water(4),real32)
  state%snow%value=REAL(water(5),real32)
  state%graupel%value=REAL(water(6),real32)
  state%geopotential%value(1,1,1)=0.0_real32
  DO k=1,2
    state%geopotential%value(1,1,k+1)=state%geopotential%value(1,1,k)+ &
      REAL(alpha*LOG(pressure(k)/pressure(k+1)),real32)
  END DO

  CALL evaluate_interior_hydrostatic_residual(state,requested,residual,assessable,reason,summary)
  CALL check(ALL(assessable),'manufactured interior layers are assessable',failures)
  CALL check(summary%assessable_layers==2_int64,'assessable count',failures)
  CALL check(MAXVAL(ABS(residual))<0.02_real64,'constant-alpha hydrostatic column closes',failures)
  CALL check(summary%residual_rms_m2_s2<0.02_real64,'RMS reports the residual',failures)

  state%geopotential%value(1,1,2)=state%geopotential%value(1,1,2)+12.0_real32
  CALL evaluate_interior_hydrostatic_residual(state,requested,residual,assessable,reason,summary)
  expected=REAL(state%geopotential%value(1,1,2),real64)- &
    0.5_real64*(hydrostatic_pressure_alpha(pressure(1),280.0_real64,water)+ &
                hydrostatic_pressure_alpha(pressure(2),280.0_real64,water))* &
      LOG(pressure(1)/pressure(2))
  CALL check(ALL(assessable),'perturbed layers remain assessable',failures)
  CALL check(ABS(residual(1,1,1)-expected)<0.02_real64 .AND. &
      residual(1,1,2)<-11.9_real64,'geopotential perturbation has expected signed residuals',failures)
  CALL check(summary%residual_max_abs_m2_s2>=11.9_real64,'maximum absolute residual reported',failures)

  state%geopotential%value(1,1,2)=ieee_value(0.0_real32,ieee_quiet_nan)
  CALL evaluate_interior_hydrostatic_residual(state,requested,residual,assessable,reason,summary)
  CALL check(.NOT.ANY(assessable) .AND. summary%nonfinite_layers==2_int64, &
      'nonfinite geopotential is rejected without range comparison',failures)
  state%geopotential%value(1,1,2)=12.0_real32

  state%snow%valid(1,1,2)=.FALSE.
  CALL evaluate_interior_hydrostatic_residual(state,requested,residual,assessable,reason,summary)
  CALL check(.NOT.ANY(assessable),'layers without six-species support are not assessed',failures)
  CALL check(ALL(IAND(reason,HYDRO_REASON_MISSING_SUPPORT)/=0_int32), &
      'missing species coverage reason returned',failures)
  CALL check(summary%missing_support_layers==2_int64 .AND. &
      summary%assessable_layers==0_int64,'missing support counts reported',failures)

  DEALLOCATE(state%snow%value,state%snow%valid,state%snow%quality,state%snow%source)
  CALL evaluate_interior_hydrostatic_residual(state,requested,residual,assessable,reason,summary)
  CALL check(.NOT.ANY(assessable) .AND. summary%missing_support_layers==2_int64, &
      'missing species storage is coverage, not zero',failures)

  IF (failures/=0) THEN
    PRINT *, 'Thermodynamic constraint tests failed:',failures
    ERROR STOP 1
  END IF
  PRINT *, 'Thermodynamic constraint tests passed'

CONTAINS

  SUBROUTINE check(condition,message,count)
    LOGICAL, INTENT(IN) :: condition
    CHARACTER(LEN=*), INTENT(IN) :: message
    INTEGER, INTENT(INOUT) :: count
    IF (.NOT.condition) THEN
      count=count+1
      PRINT *, 'FAIL: ',TRIM(message)
    END IF
  END SUBROUTINE check

  SUBROUTINE test_pressure_alpha_nonfinite(count)
    INTEGER, INTENT(INOUT) :: count
    REAL(real64) :: invalid,trial_water(6)
    INTEGER :: species
    trial_water=0.0_real64
    DO species=1,6
      invalid=ieee_value(0.0_real64,ieee_quiet_nan)
      trial_water(species)=invalid
      CALL check(hydrostatic_pressure_alpha(90000.0_real64,280.0_real64,trial_water)==-1.0_real64, &
        'quiet NaN rejected in water species',count)
      trial_water(species)=ieee_value(0.0_real64,ieee_positive_inf)
      CALL check(hydrostatic_pressure_alpha(90000.0_real64,280.0_real64,trial_water)==-1.0_real64, &
        'infinity rejected in water species',count)
      trial_water(species)=0.0_real64
    END DO
    trial_water(4)=HUGE(1.0_real64)
    CALL check(hydrostatic_pressure_alpha(90000.0_real64,280.0_real64,trial_water)==-1.0_real64, &
      'water beyond canonical real32 range rejected before summation',count)
  END SUBROUTINE test_pressure_alpha_nonfinite

  SUBROUTINE make_state(input)
    TYPE(cloud_bal_state_type), INTENT(OUT) :: input
    INTEGER(int32), PARAMETER :: source=SOURCE_BACKGROUND_MODEL
    input%grid%nx=1; input%grid%ny=1; input%grid%nz=3
    CALL initialize_field(input%pressure,1,1,3,10_int64,'Pa')
    CALL initialize_field(input%temperature,1,1,3,10_int64,'K')
    CALL initialize_field(input%geopotential,1,1,3,10_int64,'m2 s-2')
    CALL initialize_field(input%vapor,1,1,3,10_int64,'kg kg-1 dryair')
    CALL initialize_field(input%cloud_water,1,1,3,10_int64,'kg kg-1 dryair')
    CALL initialize_field(input%cloud_ice,1,1,3,10_int64,'kg kg-1 dryair')
    CALL initialize_field(input%rain,1,1,3,10_int64,'kg kg-1 dryair')
    CALL initialize_field(input%snow,1,1,3,10_int64,'kg kg-1 dryair')
    CALL initialize_field(input%graupel,1,1,3,10_int64,'kg kg-1 dryair')
    input%pressure%valid=.TRUE.; input%temperature%valid=.TRUE.
    input%geopotential%valid=.TRUE.; input%vapor%valid=.TRUE.
    input%cloud_water%valid=.TRUE.; input%cloud_ice%valid=.TRUE.
    input%rain%valid=.TRUE.; input%snow%valid=.TRUE.; input%graupel%valid=.TRUE.
    ALLOCATE(input%above_ground(1,1,3))
    input%above_ground=.TRUE.
    input%pressure%source=source; input%temperature%source=source
    input%geopotential%source=source; input%vapor%source=source
    input%cloud_water%source=source; input%cloud_ice%source=source
    input%rain%source=source; input%snow%source=source; input%graupel%source=source
    input%pressure%quality=0_int32; input%temperature%quality=0_int32
    input%geopotential%quality=0_int32; input%vapor%quality=0_int32
    input%cloud_water%quality=0_int32; input%cloud_ice%quality=0_int32
    input%rain%quality=0_int32; input%snow%quality=0_int32; input%graupel%quality=0_int32
    input%pressure%value=0.0_real32; input%temperature%value=280.0_real32
    input%geopotential%value=0.0_real32; input%vapor%value=0.0_real32
    input%cloud_water%value=0.0_real32; input%cloud_ice%value=0.0_real32
    input%rain%value=0.0_real32; input%snow%value=0.0_real32; input%graupel%value=0.0_real32
  END SUBROUTINE make_state

END PROGRAM test_thermodynamic_constraints
