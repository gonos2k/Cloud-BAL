PROGRAM test_qbal_ground_reference
  USE, INTRINSIC :: iso_fortran_env, ONLY: real64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite, ieee_is_nan, &
                                           ieee_quiet_nan, ieee_value
  USE qbal_ground_reference, ONLY: build_ground_reference
  IMPLICIT NONE

  INTEGER :: failures,checks

  failures=0
  checks=0
  CALL test_shared_surface_anchor()
  CALL test_state_swap()
  CALL test_zero_height_bracket()
  CALL test_pressure_bracket_rejection()
  CALL test_gap_rejection()
  CALL test_late_nan_transaction()
  CALL test_mixed_humidity_cancellation()
  CALL test_near_surface_pressure()

  IF (failures/=0) THEN
    PRINT '(A,I0)', 'Ground-reference tests failed: ',failures
    ERROR STOP 1
  END IF
  PRINT '(A,I0,A)', 'Ground-reference tests passed: ',checks,' assertions'

CONTAINS

  SUBROUTINE check(condition,message)
    LOGICAL, INTENT(IN) :: condition
    CHARACTER(LEN=*), INTENT(IN) :: message
    checks=checks+1
    IF (.NOT.condition) THEN
      failures=failures+1
      PRINT '(A)', 'FAIL: '//TRIM(message)
    END IF
  END SUBROUTINE check

  SUBROUTINE close_value(actual,expected,tolerance,message)
    REAL(real64), INTENT(IN) :: actual,expected,tolerance
    CHARACTER(LEN=*), INTENT(IN) :: message
    CALL check(ieee_is_finite(actual) .AND. ieee_is_finite(expected) .AND. &
      ABS(actual-expected)<=tolerance*MAX(1.0_real64,ABS(expected)),message)
  END SUBROUTINE close_value

  SUBROUTINE all_nan(values,message)
    REAL(real64), INTENT(IN) :: values(:)
    CHARACTER(LEN=*), INTENT(IN) :: message
    CALL check(ALL(ieee_is_nan(values)),message)
  END SUBROUTINE all_nan

  SUBROUTINE make_column(p,ps,p10,tv,terrain,ta,qa,tf,qf,valid)
    REAL(real64), INTENT(OUT) :: p(:),ps,p10,tv,terrain,ta(:),qa(:),tf(:),qf(:)
    LOGICAL, INTENT(OUT) :: valid(:)
    INTEGER :: k

    p=[100000.0_real64,90000.0_real64,80000.0_real64,60000.0_real64,5000.0_real64]
    ps=101000.0_real64
    p10=99500.0_real64
    tv=290.0_real64
    terrain=45.0_real64
    DO k=1,SIZE(p)
      ta(k)=280.0_real64
      qa(k)=0.010_real64
      tf(k)=ta(k)
      qf(k)=qa(k)
    END DO
    valid=.TRUE.
  END SUBROUTINE make_column

  SUBROUTINE test_shared_surface_anchor()
    REAL(real64) :: p(5),ps,p10,tv,terrain,ta(5),qa(5),tf(5),qf(5)
    REAL(real64) :: before(5),after(5),delta(3,5),bound(5),expected_surface
    REAL(real64) :: before_shift(5),after_shift(5),delta_shift(3,5),bound_shift(5)
    INTEGER :: first,first_shift
    LOGICAL :: valid(5),eligible,ok,eligible_shift,ok_shift
    REAL(real64), PARAMETER :: rd=287.05_real64,g0=9.80665_real64

    CALL make_column(p,ps,p10,tv,terrain,ta,qa,tf,qf,valid)
    CALL build_ground_reference(p,ps,p10,tv,terrain,ta,qa,tf,qf,valid, &
      before,after,delta,bound,first,eligible,ok)
    expected_surface=g0*terrain+rd*tv*LOG(ps/p(1))
    CALL check(ok .AND. eligible .AND. first==1,'eligible anchored column accepted')
    CALL close_value(before(1),expected_surface,2.0e-13_real64, &
      'stage Phi includes g0*AVG and the PS-to-first partial layer')
    CALL close_value(after(1),expected_surface,2.0e-13_real64, &
      'final Phi shares the same partial-layer surface datum')
    CALL close_value(after(1)-before(1),0.0_real64,2.0e-13_real64, &
      'shared partial layer cancels at the first regular level')
    CALL check(ALL(ieee_is_finite(before)) .AND. ALL(ieee_is_finite(after)) .AND. &
               ALL(ieee_is_finite(delta)) .AND. ALL(bound>=0.0_real64), &
      'supported absolute and relative outputs are finite')
    CALL check(MAXVAL(ABS(delta))==0.0_real64, &
      'unchanged stage and final states have zero relative change')

    terrain=terrain+125.0_real64
    CALL build_ground_reference(p,ps,p10,tv,terrain,ta,qa,tf,qf,valid, &
      before_shift,after_shift,delta_shift,bound_shift,first_shift,eligible_shift,ok_shift)
    CALL check(ok_shift .AND. eligible_shift .AND. first_shift==first, &
      'ground-shift case remains eligible')
    CALL close_value(before_shift(1)-before(1),g0*125.0_real64,2.0e-13_real64, &
      'common ground datum shift appears in stage Phi')
    CALL close_value(after_shift(5)-after(5),g0*125.0_real64,2.0e-13_real64, &
      'common ground datum shift appears in final Phi')
    CALL check(MAXVAL(ABS(delta_shift-delta))==0.0_real64, &
      'common ground datum shift cancels from relative Phi')
  END SUBROUTINE test_shared_surface_anchor

  SUBROUTINE test_state_swap()
    REAL(real64) :: p(5),ps,p10,tv,terrain,ta(5),qa(5),tf(5),qf(5)
    REAL(real64) :: before(5),after(5),delta(3,5),bound(5)
    REAL(real64) :: before_swap(5),after_swap(5),delta_swap(3,5),bound_swap(5)
    INTEGER :: first,first_swap
    LOGICAL :: valid(5),eligible,ok,eligible_swap,ok_swap

    CALL make_column(p,ps,p10,tv,terrain,ta,qa,tf,qf,valid)
    ta=[280.0_real64,278.0_real64,276.0_real64,274.0_real64,272.0_real64]
    qa=[0.010_real64,0.009_real64,0.008_real64,0.007_real64,0.006_real64]
    tf=[282.0_real64,277.0_real64,279.0_real64,271.0_real64,275.0_real64]
    qf=[0.013_real64,0.008_real64,0.011_real64,0.006_real64,0.009_real64]
    CALL build_ground_reference(p,ps,p10,tv,terrain,ta,qa,tf,qf,valid, &
      before,after,delta,bound,first,eligible,ok)
    CALL build_ground_reference(p,ps,p10,tv,terrain,tf,qf,ta,qa,valid, &
      before_swap,after_swap,delta_swap,bound_swap,first_swap,eligible_swap,ok_swap)
    CALL check(ok .AND. ok_swap .AND. eligible .AND. eligible_swap, &
      'state-swap columns accepted')
    CALL check(MAXVAL(ABS(before_swap-after))<2.0e-12_real64 .AND. &
               MAXVAL(ABS(after_swap-before))<2.0e-12_real64, &
      'state swap exchanges absolute stage and final Phi')
    CALL check(MAXVAL(ABS(delta_swap+delta))<2.0e-12_real64, &
      'state swap negates each relative Phi attribution')
    CALL check(MAXVAL(ABS(bound_swap-bound))<2.0e-12_real64, &
      'state swap preserves the arithmetic bound scale')
  END SUBROUTINE test_state_swap

  SUBROUTINE test_zero_height_bracket()
    REAL(real64) :: p(5),ps,p10,tv,terrain,ta(5),qa(5),tf(5),qf(5)
    REAL(real64) :: before(5),after(5),delta(3,5),bound(5)
    INTEGER :: first
    LOGICAL :: valid(5),eligible,ok

    CALL make_column(p,ps,p10,tv,terrain,ta,qa,tf,qf,valid)
    ps=p(1)
    p10=ps
    CALL build_ground_reference(p,ps,p10,tv,terrain,ta,qa,tf,qf,valid, &
      before,after,delta,bound,first,eligible,ok)
    CALL check(ok .AND. eligible .AND. first==1, &
      'zero-height p10=PS bracket is accepted')
    CALL close_value(before(1),9.80665_real64*terrain,2.0e-13_real64, &
      'zero-height bracket contributes no partial thickness')
    CALL check(MAXVAL(ABS(after-before))==0.0_real64, &
      'zero-change state has identical absolute Phi')
  END SUBROUTINE test_zero_height_bracket

  SUBROUTINE test_pressure_bracket_rejection()
    REAL(real64) :: p(5),ps,p10,tv,terrain,ta(5),qa(5),tf(5),qf(5)
    REAL(real64) :: before(5),after(5),delta(3,5),bound(5)
    INTEGER :: first
    LOGICAL :: valid(5),eligible,ok

    CALL make_column(p,ps,p10,tv,terrain,ta,qa,tf,qf,valid)
    p10=100001.0_real64
    CALL build_ground_reference(p,ps,p10,tv,terrain,ta,qa,tf,qf,valid, &
      before,after,delta,bound,first,eligible,ok)
    CALL check(ok .AND. .NOT.eligible .AND. first==0, &
      'p10 above the first regular pressure is unsupported')
    CALL all_nan(before,'unsupported pressure bracket leaves stage Phi NaN')
    CALL all_nan(after,'unsupported pressure bracket leaves final Phi NaN')
    CALL all_nan(RESHAPE(delta,[SIZE(delta)]), &
      'unsupported pressure bracket leaves relative Phi NaN')
    CALL all_nan(bound,'unsupported pressure bracket leaves bounds NaN')
  END SUBROUTINE test_pressure_bracket_rejection

  SUBROUTINE test_gap_rejection()
    REAL(real64) :: p(5),ps,p10,tv,terrain,ta(5),qa(5),tf(5),qf(5)
    REAL(real64) :: before(5),after(5),delta(3,5),bound(5)
    INTEGER :: first
    LOGICAL :: valid(5),eligible,ok

    CALL make_column(p,ps,p10,tv,terrain,ta,qa,tf,qf,valid)
    valid(3)=.FALSE.
    CALL build_ground_reference(p,ps,p10,tv,terrain,ta,qa,tf,qf,valid, &
      before,after,delta,bound,first,eligible,ok)
    CALL check(ok .AND. .NOT.eligible .AND. first==0, &
      'regular-level gap is unsupported and does not bridge')
    CALL all_nan(before,'gap leaves stage Phi NaN')
    CALL all_nan(after,'gap leaves final Phi NaN')
    CALL all_nan(RESHAPE(delta,[SIZE(delta)]),'gap leaves relative Phi NaN')
    CALL all_nan(bound,'gap leaves arithmetic bounds NaN')
  END SUBROUTINE test_gap_rejection

  SUBROUTINE test_late_nan_transaction()
    REAL(real64) :: p(5),ps,p10,tv,terrain,ta(5),qa(5),tf(5),qf(5)
    REAL(real64) :: before(5),after(5),delta(3,5),bound(5),nan
    INTEGER :: first
    LOGICAL :: valid(5),eligible,ok

    CALL make_column(p,ps,p10,tv,terrain,ta,qa,tf,qf,valid)
    nan=ieee_value(0.0_real64,ieee_quiet_nan)
    qf(5)=nan
    CALL build_ground_reference(p,ps,p10,tv,terrain,ta,qa,tf,qf,valid, &
      before,after,delta,bound,first,eligible,ok)
    CALL check(.NOT.ok .AND. .NOT.eligible .AND. first==0, &
      'late supported NaN is a malformed input')
    CALL all_nan(before,'late NaN transactionally clears stage Phi')
    CALL all_nan(after,'late NaN transactionally clears final Phi')
    CALL all_nan(RESHAPE(delta,[SIZE(delta)]), &
      'late NaN transactionally clears relative Phi')
    CALL all_nan(bound,'late NaN transactionally clears bounds')
  END SUBROUTINE test_late_nan_transaction

  SUBROUTINE test_mixed_humidity_cancellation()
    REAL(real64) :: p(5),ps,p10,tv,terrain,ta(5),qa(5),tf(5),qf(5)
    REAL(real64) :: before(5),after(5),delta(3,5),bound(5),error,b,psi
    INTEGER :: first,k
    LOGICAL :: valid(5),eligible,ok

    CALL make_column(p,ps,p10,tv,terrain,ta,qa,tf,qf,valid)
    ta=[260.0_real64,255.0_real64,250.0_real64,245.0_real64,240.0_real64]
    qa=[0.030_real64,0.024_real64,0.019_real64,0.014_real64,0.010_real64]
    tf=[275.0_real64,248.0_real64,265.0_real64,238.0_real64,252.0_real64]
    qf=[0.014_real64,0.033_real64,0.012_real64,0.021_real64,0.006_real64]
    CALL build_ground_reference(p,ps,p10,tv,terrain,ta,qa,tf,qf,valid, &
      before,after,delta,bound,first,eligible,ok)
    CALL check(ok .AND. eligible,'mixed temperature and humidity column accepted')
    b=after(SIZE(p))-before(SIZE(p))
    DO k=first,SIZE(p)
      error=delta(1,k)+delta(2,k)-delta(3,k)
      CALL check(ABS(error)<=bound(k), &
        'temperature and humidity relative Phi terms close to total')
    END DO
    CALL check(ABS(after(first)-before(first))<=bound(first), &
      'shared partial layer gives zero bottom delta within bound')
    DO k=first,SIZE(p)
      ! The API stores delta with the common surface partial cancelled and
      ! the first regular level gauged to zero.  Re-gauge it at 5000 Pa to
      ! recover PR42's psi: psi=delta-b.  Then b+psi must reproduce the
      ! absolute stage/final difference at every reachable level.
      CALL check(ABS((after(k)-before(k))-delta(3,k))<=bound(k), &
        'absolute Phi difference agrees with cumulative relative total')
      psi=delta(3,k)-b
      CALL check(ABS((after(k)-before(k))- &
        (b+psi))<=bound(k), &
        'ground b plus PR42 psi reproduces upper absolute differential')
    END DO
  END SUBROUTINE test_mixed_humidity_cancellation

  SUBROUTINE test_near_surface_pressure()
    REAL(real64) :: p(5),ps,p10,tv,terrain,ta(5),qa(5),tf(5),qf(5)
    REAL(real64) :: before(5),after(5),delta(3,5),bound(5),expected_partial
    INTEGER :: first
    LOGICAL :: valid(5),eligible,ok
    REAL(real64), PARAMETER :: rd=287.05_real64,g0=9.80665_real64
    REAL(real64), PARAMETER :: tiny_pressure=1.0e-9_real64

    CALL make_column(p,ps,p10,tv,terrain,ta,qa,tf,qf,valid)
    ps=p(1)+tiny_pressure
    p10=p(1)
    tv=300.0_real64
    terrain=0.0_real64
    ta=300.0_real64
    tf=ta
    qa=0.0_real64
    qf=qa
    CALL build_ground_reference(p,ps,p10,tv,terrain,ta,qa,tf,qf,valid, &
      before,after,delta,bound,first,eligible,ok)
    expected_partial=rd*tv*LOG(ps/p(1))
    CALL check(ok .AND. eligible .AND. first==1, &
      'near-surface pressure bracket is eligible')
    CALL check(ALL(ieee_is_finite(before)) .AND. ALL(ieee_is_finite(after)) .AND. &
               ALL(ieee_is_finite(delta)) .AND. ALL(ieee_is_finite(bound)), &
      'near-surface thin strip produces finite diagnostics')
    CALL close_value(before(1),expected_partial,2.0e-13_real64, &
      'near-surface partial layer uses the constant surface virtual temperature')
    CALL close_value(after(1)-before(1),0.0_real64,2.0e-13_real64, &
      'near-surface shared partial layer still cancels')
    CALL check(bound(1)>=64.0_real64*epsilon(1.0_real64)*rd*tv, &
      'near-surface bound retains Rd*Tv ratio-roundoff scale')
    CALL check(ABS(before(1)-g0*terrain-expected_partial)<=bound(1), &
      'near-surface anchor closes within its arithmetic bound')
  END SUBROUTINE test_near_surface_pressure

END PROGRAM test_qbal_ground_reference
