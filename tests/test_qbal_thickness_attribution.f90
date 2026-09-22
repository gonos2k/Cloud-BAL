PROGRAM test_qbal_thickness_attribution
  USE, INTRINSIC :: iso_fortran_env, ONLY: real64
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite, ieee_is_nan, &
                                           ieee_quiet_nan, ieee_value
  USE qbal_thickness_attribution, ONLY: thickness_change
  IMPLICIT NONE

  INTEGER :: failures

  failures=0
  CALL test_zero_change()
  CALL test_temperature_only()
  CALL test_humidity_only()
  CALL test_both_and_cross_term()
  CALL test_swap_states_negative()
  CALL test_layer_partition()
  CALL test_invalid_inputs_nan_transactionality()
  CALL test_near_cancellation_bound()

  IF (failures/=0) THEN
    PRINT '(A,I0)', 'Thickness attribution tests failed: ',failures
    ERROR STOP 1
  END IF
  PRINT '(A)', 'Thickness attribution tests passed'

CONTAINS

  SUBROUTINE check(condition,message)
    LOGICAL, INTENT(IN) :: condition
    CHARACTER(LEN=*), INTENT(IN) :: message
    IF (.NOT.condition) THEN
      failures=failures+1
      PRINT '(A)', 'FAIL: '//TRIM(message)
    END IF
  END SUBROUTINE check

  SUBROUTINE close_value(actual,expected,relative_tolerance,message)
    REAL(real64), INTENT(IN) :: actual,expected,relative_tolerance
    CHARACTER(LEN=*), INTENT(IN) :: message
    CALL check(ieee_is_finite(actual) .AND. &
      ABS(actual-expected)<=relative_tolerance*MAX(1.0_real64,ABS(expected)),message)
  END SUBROUTINE close_value

  SUBROUTINE all_nan(values,message)
    REAL(real64), INTENT(IN) :: values(:)
    CHARACTER(LEN=*), INTENT(IN) :: message
    CALL check(ALL(ieee_is_nan(values)),message)
  END SUBROUTINE all_nan

  SUBROUTINE evaluate(pb,pt,ta,qa,tf,qf,before,after,temp,moist,total,bound,ok)
    REAL(real64), INTENT(IN) :: pb,pt,ta(2),qa(2),tf(2),qf(2)
    REAL(real64), INTENT(OUT) :: before,after,temp,moist,total,bound
    LOGICAL, INTENT(OUT) :: ok
    CALL thickness_change(pb,pt,ta,qa,tf,qf,before,after,temp,moist,total,bound,ok)
  END SUBROUTINE evaluate

  SUBROUTINE expected_terms(pb,pt,ta,qa,tf,qf,before,after,temp,moist,total)
    REAL(real64), INTENT(IN) :: pb,pt,ta(2),qa(2),tf(2),qf(2)
    REAL(real64), INTENT(OUT) :: before,after,temp,moist,total
    REAL(real64), PARAMETER :: rd=287.05_real64,g0=9.80665_real64
    REAL(real64), PARAMETER :: alpha=1.0_real64/0.622_real64-1.0_real64
    REAL(real64) :: factor,tva(2),tvf(2),dtemp(2),dq(2)

    factor=rd/g0*LOG(pb/pt)
    tva=ta*(1.0_real64+alpha*qa)
    tvf=tf*(1.0_real64+alpha*qf)
    dtemp=(1.0_real64+alpha*(qf+qa)/2.0_real64)*(tf-ta)
    dq=alpha*(tf+ta)/2.0_real64*(qf-qa)
    before=factor*0.5_real64*SUM(tva)
    after=factor*0.5_real64*SUM(tvf)
    temp=factor*0.5_real64*SUM(dtemp)
    moist=factor*0.5_real64*SUM(dq)
    total=factor*0.5_real64*SUM(tvf-tva)
  END SUBROUTINE expected_terms

  SUBROUTINE test_zero_change()
    REAL(real64) :: ta(2),qa(2),tf(2),qf(2)
    REAL(real64) :: before,after,temp,moist,total,bound
    LOGICAL :: ok

    ta=[280.0_real64,270.0_real64]
    qa=[0.010_real64,0.004_real64]
    tf=ta
    qf=qa
    CALL evaluate(100000.0_real64,90000.0_real64,ta,qa,tf,qf, &
      before,after,temp,moist,total,bound,ok)
    CALL check(ok,'zero-change layer accepted')
    CALL close_value(before,after,2.0e-15_real64,'zero-change before equals after')
    CALL close_value(temp,0.0_real64,0.0_real64,'zero-change temperature term is zero')
    CALL close_value(moist,0.0_real64,0.0_real64,'zero-change humidity term is zero')
    CALL close_value(total,0.0_real64,0.0_real64,'zero-change total is zero')
    CALL check(bound>0.0_real64 .AND. ieee_is_finite(bound), &
      'zero-change arithmetic bound is finite and positive')
  END SUBROUTINE test_zero_change

  SUBROUTINE test_temperature_only()
    REAL(real64) :: ta(2),qa(2),tf(2),qf(2)
    REAL(real64) :: before,after,temp,moist,total,bound
    REAL(real64) :: eb,ea,et,em,etotal
    LOGICAL :: ok

    ta=[280.0_real64,270.0_real64]
    qa=[0.010_real64,0.004_real64]
    tf=ta+[4.0_real64,2.0_real64]
    qf=qa
    CALL evaluate(100000.0_real64,90000.0_real64,ta,qa,tf,qf, &
      before,after,temp,moist,total,bound,ok)
    CALL expected_terms(100000.0_real64,90000.0_real64,ta,qa,tf,qf,eb,ea,et,em,etotal)
    CALL check(ok,'temperature-only layer accepted')
    CALL close_value(before,eb,2.0e-15_real64,'temperature-only before integral')
    CALL close_value(after,ea,2.0e-15_real64,'temperature-only after integral')
    CALL close_value(temp,et,2.0e-15_real64,'temperature-only attribution')
    CALL close_value(moist,0.0_real64,0.0_real64,'temperature-only humidity term is zero')
    CALL close_value(total,etotal,2.0e-15_real64,'temperature-only total integral')
    CALL check(temp>0.0_real64 .AND. total>0.0_real64,'warming increases thickness')
  END SUBROUTINE test_temperature_only

  SUBROUTINE test_humidity_only()
    REAL(real64) :: ta(2),qa(2),tf(2),qf(2)
    REAL(real64) :: before,after,temp,moist,total,bound
    REAL(real64) :: eb,ea,et,em,etotal
    LOGICAL :: ok

    ta=[280.0_real64,270.0_real64]
    qa=[0.010_real64,0.004_real64]
    tf=ta
    qf=qa+[0.003_real64,0.002_real64]
    CALL evaluate(100000.0_real64,90000.0_real64,ta,qa,tf,qf, &
      before,after,temp,moist,total,bound,ok)
    CALL expected_terms(100000.0_real64,90000.0_real64,ta,qa,tf,qf,eb,ea,et,em,etotal)
    CALL check(ok,'humidity-only layer accepted')
    CALL close_value(temp,0.0_real64,0.0_real64,'humidity-only temperature term is zero')
    CALL close_value(moist,em,2.0e-15_real64,'humidity-only attribution')
    CALL close_value(total,etotal,2.0e-15_real64,'humidity-only total integral')
    CALL check(moist>0.0_real64 .AND. total>0.0_real64,'moistening increases thickness')
  END SUBROUTINE test_humidity_only

  SUBROUTINE test_both_and_cross_term()
    REAL(real64) :: ta(2),qa(2),tf(2),qf(2)
    REAL(real64) :: before,after,temp,moist,total,bound
    REAL(real64) :: eb,ea,et,em,etotal
    LOGICAL :: ok

    ta=[260.0_real64,240.0_real64]
    qa=[0.020_real64,0.012_real64]
    tf=[275.0_real64,250.0_real64]
    qf=[0.035_real64,0.018_real64]
    CALL evaluate(110000.0_real64,85000.0_real64,ta,qa,tf,qf, &
      before,after,temp,moist,total,bound,ok)
    CALL expected_terms(110000.0_real64,85000.0_real64,ta,qa,tf,qf,eb,ea,et,em,etotal)
    CALL check(ok,'temperature-and-humidity layer accepted')
    CALL close_value(temp,et,2.0e-15_real64,'both-change temperature attribution')
    CALL close_value(moist,em,2.0e-15_real64,'both-change humidity attribution')
    CALL close_value(total,etotal,2.0e-15_real64,'both-change direct total')
    CALL close_value(total,temp+moist,1.0e-14_real64,'both-change sum closure')
    CALL check(ABS(et)>0.0_real64 .AND. ABS(em)>0.0_real64, &
      'both-change terms include temperature and humidity effects')
  END SUBROUTINE test_both_and_cross_term

  SUBROUTINE test_swap_states_negative()
    REAL(real64) :: ta(2),qa(2),tf(2),qf(2)
    REAL(real64) :: b1,a1,t1,m1,x1,bound1
    REAL(real64) :: b2,a2,t2,m2,x2,bound2
    LOGICAL :: ok1,ok2

    ta=[280.0_real64,265.0_real64]
    qa=[0.011_real64,0.006_real64]
    tf=[275.0_real64,285.0_real64]
    qf=[0.018_real64,0.002_real64]
    CALL evaluate(100000.0_real64,80000.0_real64,ta,qa,tf,qf,b1,a1,t1,m1,x1,bound1,ok1)
    CALL evaluate(100000.0_real64,80000.0_real64,tf,qf,ta,qa,b2,a2,t2,m2,x2,bound2,ok2)
    CALL check(ok1 .AND. ok2,'state-swap layers accepted')
    CALL close_value(b2,a1,2.0e-15_real64,'state swap exchanges before and after')
    CALL close_value(a2,b1,2.0e-15_real64,'state swap exchanges after and before')
    CALL close_value(t2,-t1,2.0e-15_real64,'state swap negates temperature term')
    CALL close_value(m2,-m1,2.0e-15_real64,'state swap negates humidity term')
    CALL close_value(x2,-x1,2.0e-15_real64,'state swap negates total')
    CALL close_value(bound2,bound1,2.0e-15_real64,'state swap preserves bound scale')
  END SUBROUTINE test_swap_states_negative

  SUBROUTINE test_layer_partition()
    REAL(real64) :: ta(2),qa(2),tf(2),qf(2)
    REAL(real64) :: ta_lower(2),qa_lower(2),tf_lower(2),qf_lower(2)
    REAL(real64) :: ta_upper(2),qa_upper(2),tf_upper(2),qf_upper(2)
    REAL(real64) :: bwhole,awhole,twhole,mwhole,xwhole,boundwhole
    REAL(real64) :: b1,a1,t1,m1,x1,bound1,b2,a2,t2,m2,x2,bound2
    REAL(real64) :: pb,pm,pt
    LOGICAL :: okwhole,ok1,ok2

    pb=120000.0_real64
    pt=80000.0_real64
    pm=SQRT(pb*pt)
    ta=[280.0_real64,250.0_real64]
    ! Keep q vertically constant so Tv and both declared endpoint terms
    ! remain linear under the log-pressure partition used by this test.
    qa=[0.010_real64,0.010_real64]
    tf=[290.0_real64,260.0_real64]
    qf=[0.020_real64,0.020_real64]
    ta_lower=[ta(1),0.5_real64*(ta(1)+ta(2))]
    qa_lower=[qa(1),0.5_real64*(qa(1)+qa(2))]
    tf_lower=[tf(1),0.5_real64*(tf(1)+tf(2))]
    qf_lower=[qf(1),0.5_real64*(qf(1)+qf(2))]
    ta_upper=[ta_lower(2),ta(2)]
    qa_upper=[qa_lower(2),qa(2)]
    tf_upper=[tf_lower(2),tf(2)]
    qf_upper=[qf_lower(2),qf(2)]

    CALL evaluate(pb,pt,ta,qa,tf,qf,bwhole,awhole,twhole,mwhole,xwhole,boundwhole,okwhole)
    CALL evaluate(pb,pm,ta_lower,qa_lower,tf_lower,qf_lower,b1,a1,t1,m1,x1,bound1,ok1)
    CALL evaluate(pm,pt,ta_upper,qa_upper,tf_upper,qf_upper,b2,a2,t2,m2,x2,bound2,ok2)
    CALL check(okwhole .AND. ok1 .AND. ok2,'whole and partitioned layers accepted')
    CALL close_value(b1+b2,bwhole,2.0e-13_real64,'before integral is partition additive')
    CALL close_value(a1+a2,awhole,2.0e-13_real64,'after integral is partition additive')
    CALL close_value(t1+t2,twhole,2.0e-13_real64,'temperature contribution is partition additive')
    CALL close_value(m1+m2,mwhole,2.0e-13_real64,'humidity contribution is partition additive')
    CALL close_value(x1+x2,xwhole,2.0e-13_real64,'total contribution is partition additive')
  END SUBROUTINE test_layer_partition

  SUBROUTINE test_invalid_inputs_nan_transactionality()
    REAL(real64) :: ta(2),qa(2),tf(2),qf(2)
    REAL(real64) :: values(6),nan
    LOGICAL :: ok

    ta=[280.0_real64,270.0_real64]
    qa=[0.010_real64,0.004_real64]
    tf=[281.0_real64,271.0_real64]
    qf=[0.011_real64,0.005_real64]
    nan=ieee_value(0.0_real64,ieee_quiet_nan)

    values=1.0_real64
    CALL evaluate(nan,90000.0_real64,ta,qa,tf,qf,values(1),values(2),values(3), &
      values(4),values(5),values(6),ok)
    CALL check(.NOT.ok,'NaN pressure rejected')
    CALL all_nan(values,'NaN pressure leaves every output NaN')

    values=1.0_real64
    CALL evaluate(90000.0_real64,90000.0_real64,ta,qa,tf,qf,values(1),values(2),values(3), &
      values(4),values(5),values(6),ok)
    CALL check(.NOT.ok,'zero pressure span rejected')
    CALL all_nan(values,'invalid pressure span leaves every output NaN')

    values=1.0_real64
    tf(2)=500.0001_real64
    CALL evaluate(100000.0_real64,90000.0_real64,ta,qa,tf,qf,values(1),values(2),values(3), &
      values(4),values(5),values(6),ok)
    CALL check(.NOT.ok,'temperature outside research envelope rejected')
    CALL all_nan(values,'invalid temperature leaves every output NaN')
    tf(2)=271.0_real64

    values=1.0_real64
    qf(1)=1.0_real64
    CALL evaluate(100000.0_real64,90000.0_real64,ta,qa,tf,qf,values(1),values(2),values(3), &
      values(4),values(5),values(6),ok)
    CALL check(.NOT.ok,'humidity at one rejected')
    CALL all_nan(values,'invalid humidity leaves every output NaN')
    qf(1)=0.011_real64

    values=1.0_real64
    qa(1)=nan
    CALL evaluate(100000.0_real64,90000.0_real64,ta,qa,tf,qf,values(1),values(2),values(3), &
      values(4),values(5),values(6),ok)
    CALL check(.NOT.ok,'NaN endpoint humidity rejected')
    CALL all_nan(values,'NaN endpoint leaves every output NaN')
  END SUBROUTINE test_invalid_inputs_nan_transactionality

  SUBROUTINE test_near_cancellation_bound()
    REAL(real64) :: ta(2),qa(2),tf(2),qf(2)
    REAL(real64) :: before,after,temp,moist,total,bound
    REAL(real64) :: baseline_scale,closure
    LOGICAL :: ok

    ta=[300.0_real64,300.0_real64]
    qa=[0.200_real64,0.200_real64]
    ! The temperature and humidity changes are opposite at each endpoint;
    ! their individual thickness terms are large relative to the tiny total.
    tf=ta+[0.5_real64,0.5_real64]
    qf=(ta*(1.0_real64+(1.0_real64/0.622_real64-1.0_real64)*qa)/tf-1.0_real64)/ &
      (1.0_real64/0.622_real64-1.0_real64)
    CALL evaluate(120000.0_real64,100.0_real64,ta,qa,tf,qf,before,after,temp,moist,total,bound,ok)
    CALL check(ok,'near-cancellation layer accepted')
    baseline_scale=ABS(before)+ABS(after)+ABS(temp)+ABS(moist)
    closure=total-(temp+moist)
    CALL check(ABS(total)<0.01_real64,'near-cancellation total remains small')
    CALL check(bound>=128.0_real64*EPSILON(1.0_real64)*baseline_scale, &
      'bound uses uncancelled before/after and contribution scale')
    CALL check(ABS(closure)<=bound+1.0e-12_real64, &
      'near-cancellation closure is within arithmetic bound')
    CALL check(ABS(temp)>1.0_real64 .AND. ABS(moist)>1.0_real64, &
      'near-cancellation terms remain individually resolved')
  END SUBROUTINE test_near_cancellation_bound

END PROGRAM test_qbal_thickness_attribution
