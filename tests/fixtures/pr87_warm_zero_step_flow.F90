module pr87_warm_zero_step_flow_fixture
  ! Source-extracted control-flow fixture; this is not the full warm kernel.
  implicit none
contains
  subroutine run_warm_trial(status,alpha,pending,q_before,n_before,ccn_before, &
                            attempts,accepted,q_after,n_after,ccn_after)
    integer, intent(in) :: status
    real, intent(inout) :: alpha
    logical, intent(in) :: pending
    real, intent(in) :: q_before(5),n_before(3),ccn_before
    integer, intent(out) :: attempts
    logical, intent(out) :: accepted
    real, intent(out) :: q_after(5),n_after(3),ccn_after
    integer :: rain_warm_retry,i,k
    integer :: rain_warm_search_status
    real :: rain_warm_alpha,rain_warm_q_process(5),rain_warm_n_process(3)
    real :: rain_warm_q_after(5),rain_warm_n_after(3),rain_ccn3_after
    real :: rain_ccn3_before,rain_q_before(5),rain_n_before(3)
    logical :: rain_full_evap_pending(1,1),rain_warm_state_valid

    rain_warm_search_status=status
    rain_warm_alpha=alpha
    rain_q_before=q_before
    rain_n_before=n_before
    rain_ccn3_before=ccn_before
    rain_warm_q_process=1.0
    rain_warm_n_process=1.0
    rain_full_evap_pending(1,1)=pending
    i=1; k=1; attempts=0; accepted=.false.
    q_after=q_before; n_after=n_before; ccn_after=ccn_before
    rain_warm_q_after=rain_q_before
    rain_warm_n_after=rain_n_before
    rain_ccn3_after=rain_ccn3_before
    do rain_warm_retry=0,56
      if (rain_warm_retry.gt.0) rain_warm_alpha=nearest(rain_warm_alpha,-1.0)
      ! PR87_RETRY_ZERO_GUARD
      attempts=attempts+1
      rain_warm_q_after=rain_q_before+rain_warm_alpha*rain_warm_q_process
      rain_warm_n_after=rain_n_before+rain_warm_alpha*rain_warm_n_process
      rain_ccn3_after=rain_ccn3_before
      ! PR87_PENDING_CCN_TRANSFER
      rain_warm_state_valid=all(rain_warm_q_after.ge.0.0) .and. &
           all(rain_warm_n_after.ge.0.0) .and. rain_ccn3_after.ge.0.0
      if (rain_warm_state_valid) then
        accepted=.true.
        exit
      endif
    enddo
    alpha=rain_warm_alpha
    q_after=rain_warm_q_after
    n_after=rain_warm_n_after
    ccn_after=rain_ccn3_after
  end subroutine run_warm_trial
end module pr87_warm_zero_step_flow_fixture

program pr87_warm_zero_step_flow_test
  use pr87_warm_zero_step_flow_fixture
  implicit none
  real :: q0(5),n0(3),q1(5),n1(3),ccn
  real :: alpha,ccn1
  integer :: attempts
  logical :: accepted

  q0=0.0; n0=0.0; q0(3)=0.0; n0(3)=7.0; ccn=3.0
  alpha=0.0
  call run_warm_trial(1,alpha,.true.,q0,n0,ccn,attempts,accepted,q1,n1,ccn1)
  if (.not.accepted .or. attempts.ne.1 .or. alpha.ne.0.0) error stop 1
  if (q1(3).ne.0.0 .or. n1(3).ne.0.0 .or. ccn1.ne.10.0) error stop 2

  ! Zero alpha with any other search state remains an immediate exit.
  alpha=0.0
  call run_warm_trial(0,alpha,.false.,q0,n0,ccn,attempts,accepted,q1,n1,ccn1)
  if (accepted .or. attempts.ne.0) error stop 3
  if (any(q1.ne.q0) .or. any(n1.ne.n0) .or. ccn1.ne.ccn) error stop 6
  alpha=0.0
  call run_warm_trial(2,alpha,.true.,q0,n0,ccn,attempts,accepted,q1,n1,ccn1)
  if (accepted .or. attempts.ne.0) error stop 4
  if (any(q1.ne.q0) .or. any(n1.ne.n0) .or. ccn1.ne.ccn) error stop 7

  ! The status-1 control exception still cannot admit an invalid base.
  q0(3)=-1.0; n0(3)=7.0; alpha=0.0
  call run_warm_trial(1,alpha,.false.,q0,n0,ccn,attempts,accepted,q1,n1,ccn1)
  if (accepted .or. attempts.ne.1) error stop 8
  if (q1(3).ge.0.0) error stop 9

  ! A positive admitted endpoint still uses the normal trial body.
  q0(3)=1.0; n0(3)=7.0; alpha=0.25
  call run_warm_trial(0,alpha,.false.,q0,n0,ccn,attempts,accepted,q1,n1,ccn1)
  if (.not.accepted .or. attempts.ne.1 .or. alpha.ne.0.25) error stop 5
  print '(a)', 'PR87 warm zero-step flow PASS'
end program pr87_warm_zero_step_flow_test
