
program test_v39_aggregate_ice_extinction
  use pr87_ice_sublimation_helpers
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite, ieee_value, &
       ieee_quiet_nan, ieee_positive_inf
  implicit none
  call run_sequence(2.0**(-50),-2.0**(-52),-2.0**(-52),-2.0**(-51), &
       0.0,2,.true.,.true.,8.0)
  call run_sequence(2.0**(-50),-2.0**(-52),0.0,0.0, &
       -3.0*2.0**(-52),4,.true.,.true.,8.0)
  call run_sequence(2.0**(-50),-2.0**(-52),0.0,0.0, &
       0.0,0,.false.,.false.,8.0)
  call run_sequence(2.0**(-50),-2.0**(-50),0.0,0.0, &
       0.0,2,.true.,.false.,8.0,1.0,-2.0)
  call run_sequence(4.2936549e-15,-4.2936549e-15/4.0,-4.2936549e-15/4.0, &
       -4.2936549e-15/2.0,0.0,2,.true.,.true.,8.823875)
  call check_invalid_endpoint(-1.0,.false.)
  call check_invalid_endpoint(ieee_value(0.0,ieee_quiet_nan),.true.)
  call check_invalid_endpoint(ieee_value(0.0,ieee_positive_inf),.true.)
  call check_invalid_endpoint(8.0,.false.)
  call reject_invalid_base()
  print '(a)', 'PR87 V39 aggregate ice extinction cases PASS'
contains
  subroutine run_sequence(qin,ng1,ng2,ng3,gdelta,expected_cause,expected_pending, &
                          expect_zero,nin,vaporfixed,vaporprocess)
    real,intent(in)::qin,ng1,ng2,ng3,gdelta,nin
    integer,intent(in)::expected_cause
    logical,intent(in)::expected_pending,expect_zero
    real,intent(in),optional::vaporfixed,vaporprocess
    real::rain_q_before(5),rain_q_fixed(5),rain_ng_q_process(5),rain_g_q_process(5)
    real::rain_n_before(3),rain_n_fixed(3),rain_ng_n_process(3),rain_g_n_process(3)
    real::rain_bg_fixed,rain_bg_process,rain_t_fixed,rain_t_process
    real::rain_q_after(5),rain_n_after(3),alpha_ng,alpha_g
    real::pr87_ice_sublimation_n_preclear,pr87_ice_sublimation_dn
    logical::ice_full_sublimation_pending(1,1),rain_full_evap_pending(1,1), &
         rain_composite_valid,feasible
    integer::ice_extinction_cause(1,1),i,k,status,pr87_ice_sublimation_extinctions
    i=1;k=1
    rain_q_before=0.0;rain_q_before(2)=qin
    rain_ng_q_process=0.0
    rain_ng_q_process(2)=ng1+ng2+ng3
    rain_g_q_process=0.0;rain_g_q_process(2)=gdelta
    rain_n_before=0.0;rain_n_before(2)=nin
    rain_ng_n_process=0.0;rain_g_n_process=0.0
    rain_bg_fixed=0.0;rain_bg_process=0.0;rain_t_fixed=273.15;rain_t_process=0.0
    ice_full_sublimation_pending=.false.;ice_extinction_cause=0
                if (ieee_is_finite(rain_q_before(2))) then
              if (rain_q_before(2).gt.0.0) then
                if (ieee_is_finite(rain_ng_q_process(2))) then
                  if (rain_ng_q_process(2).lt.0.0) then
                    if (rain_ng_q_process(2).le.-rain_q_before(2)) then
                      ice_full_sublimation_pending(i,k)=.true.
                      ice_extinction_cause(i,k)=ior(ice_extinction_cause(i,k),2)
                    endif
                  endif
                endif
              endif
            endif

    rain_q_fixed=rain_q_before;rain_n_fixed=rain_n_before
    call fraction_check(rain_q_fixed,rain_ng_q_process,rain_n_fixed,rain_ng_n_process, &
         rain_bg_fixed,0.0,rain_t_fixed,0.0,ice_full_sublimation_pending(1,1), &
         alpha_ng,feasible,status,vaporfixed,vaporprocess)
    if (.not.feasible .or. status.ne.0) error stop 'NG fixture fraction rejected'
    rain_q_fixed=rain_q_fixed+alpha_ng*rain_ng_q_process
    rain_n_fixed=rain_n_fixed+alpha_ng*rain_ng_n_process
    ! G proposal is evaluated against the current fixed cloud-ice state.
                if (ieee_is_finite(rain_q_fixed(2))) then
              if (rain_q_fixed(2).gt.0.0) then
                if (ieee_is_finite(rain_g_q_process(2))) then
                  if (rain_g_q_process(2).lt.0.0) then
                    if (rain_g_q_process(2).le.-rain_q_fixed(2)) then
                      ice_full_sublimation_pending(i,k)=.true.
                      ice_extinction_cause(i,k)=ior(ice_extinction_cause(i,k),4)
                    endif
                  endif
                endif
              endif
            endif

    rain_q_after=rain_q_fixed;rain_n_after=rain_n_fixed
    alpha_g=0.0
    if (any(rain_g_q_process.ne.0.0)) then
      call fraction_check(rain_q_fixed,rain_g_q_process,rain_n_fixed,rain_g_n_process, &
           rain_bg_fixed,rain_bg_process,rain_t_fixed,rain_t_process, &
           ice_full_sublimation_pending(1,1),alpha_g,feasible,status)
      if (.not.feasible .or. status.ne.0) error stop 'G fixture fraction rejected'
      rain_q_after=rain_q_fixed+alpha_g*rain_g_q_process
      rain_n_after=rain_n_fixed+alpha_g*rain_g_n_process
    endif
    if (ice_extinction_cause(1,1).ne.expected_cause) then
      print *, 'cause,expected,Q,dNG,dG=',ice_extinction_cause(1,1),expected_cause, &
           qin,rain_ng_q_process(2),rain_g_q_process(2)
      error stop 'cold cause bits mismatch'
    endif
    if (ice_full_sublimation_pending(1,1) .neqv. expected_pending) error stop 'cold pending flag mismatch'
    rain_full_evap_pending=.false.
    rain_composite_valid=.true.
                pr87_ice_sublimation_extinctions=0
            pr87_ice_sublimation_n_preclear=rain_n_after(2)
            pr87_ice_sublimation_dn=0.0
            if (rain_composite_valid) then
              if (ieee_is_finite(rain_n_after(2))) then
                if (rain_n_after(2).ge.0.0) then
                  if (ice_full_sublimation_pending(i,k) .and. &
                      rain_q_after(2).eq.0.0) then
                    if (rain_n_after(2).gt.0.0) then
                      pr87_ice_sublimation_extinctions=1
                      pr87_ice_sublimation_dn=-rain_n_after(2)
                    endif
                    rain_n_after(2)=0.0
                  endif
                endif
              endif
            endif

    if (expect_zero) then
      if (rain_q_after(2).ne.0.0) error stop 'eligible endpoint missed exact zero Q'
      if (rain_n_after(2).ne.0.0) error stop 'exact zero Q did not clear number'
      if (pr87_ice_sublimation_dn.ne.-nin) error stop 'extinction number ledger mismatch'
    else
      if (rain_q_after(2).le.0.0) error stop 'partial process unexpectedly extinguished Q'
      if (rain_n_after(2).ne.nin) error stop 'positive Q did not preserve number'
      if (pr87_ice_sublimation_dn.ne.0.0) error stop 'partial process logged number extinction'
    endif
  end subroutine run_sequence

  subroutine check_invalid_endpoint(nin,composite_ok)
    real,intent(in)::nin
    logical,intent(in)::composite_ok
    real::rain_q_after(5),rain_n_after(3)
    real::pr87_ice_sublimation_n_preclear,pr87_ice_sublimation_dn
    logical::ice_full_sublimation_pending(1,1),rain_full_evap_pending(1,1),rain_composite_valid
    integer::pr87_ice_sublimation_extinctions,i,k
    i=1;k=1;rain_q_after=0.0;rain_n_after=0.0;rain_n_after(2)=nin
    rain_composite_valid=composite_ok
    ice_full_sublimation_pending=.true.;rain_full_evap_pending=.false.
                pr87_ice_sublimation_extinctions=0
            pr87_ice_sublimation_n_preclear=rain_n_after(2)
            pr87_ice_sublimation_dn=0.0
            if (rain_composite_valid) then
              if (ieee_is_finite(rain_n_after(2))) then
                if (rain_n_after(2).ge.0.0) then
                  if (ice_full_sublimation_pending(i,k) .and. &
                      rain_q_after(2).eq.0.0) then
                    if (rain_n_after(2).gt.0.0) then
                      pr87_ice_sublimation_extinctions=1
                      pr87_ice_sublimation_dn=-rain_n_after(2)
                    endif
                    rain_n_after(2)=0.0
                  endif
                endif
              endif
            endif

    if (ieee_is_finite(nin)) then
      if (rain_n_after(2).ne.nin) error stop 'invalid endpoint changed NI'
    else
      if (ieee_is_finite(rain_n_after(2))) error stop 'nonfinite endpoint changed NI'
    endif
    if (pr87_ice_sublimation_dn.ne.0.0) error stop 'invalid endpoint recorded extinction'
  end subroutine check_invalid_endpoint

  subroutine reject_invalid_base()
    real::rain_q_before(5),rain_ng_q_process(5)
    logical::ice_full_sublimation_pending(1,1)
    integer::ice_extinction_cause(1,1),i,k
    i=1;k=1;rain_q_before=0.0;rain_q_before(2)=-1.0
    rain_ng_q_process=0.0;rain_ng_q_process(2)=1.0
    ice_full_sublimation_pending=.false.;ice_extinction_cause=0
                if (ieee_is_finite(rain_q_before(2))) then
              if (rain_q_before(2).gt.0.0) then
                if (ieee_is_finite(rain_ng_q_process(2))) then
                  if (rain_ng_q_process(2).lt.0.0) then
                    if (rain_ng_q_process(2).le.-rain_q_before(2)) then
                      ice_full_sublimation_pending(i,k)=.true.
                      ice_extinction_cause(i,k)=ior(ice_extinction_cause(i,k),2)
                    endif
                  endif
                endif
              endif
            endif

    if (ice_full_sublimation_pending(1,1) .or. ice_extinction_cause(1,1).ne.0) &
      error stop 'negative base received cold extinction permission'
  end subroutine reject_invalid_base

  subroutine fraction_check(qfixed,qprocess,nfixed,nprocess,bgfixed,bgprocess, &
                            tfixed,tprocess,pending,a,ok,istat,vaporfixed,vaporprocess)
    real,intent(in)::qfixed(5),qprocess(5),nfixed(3),nprocess(3)
    real,intent(in)::bgfixed,bgprocess,tfixed,tprocess
    logical,intent(in)::pending
    real,intent(out)::a
    logical,intent(out)::ok
    integer,intent(out)::istat
    real,intent(in),optional::vaporfixed,vaporprocess
    call kdm6_rain_process_fraction(qfixed,qprocess,nfixed,nprocess, &
      bgfixed,bgprocess,tfixed,tprocess,.false.,1.0,1.0,0.0,0.0, &
      0.0,3.0,1.0,2.0,100.0,900.0,1.0,3.0,1.0,2.0, &
      1.0,3.0,1.0,2.0,a,ok,istat,consumer_pair_only=.false., &
      ice_transient_mass_limit=PR85_ICE_NATIVE_INACTIVE_MAX, &
      ice_sublimation_pending=pending,vapor_fixed=vaporfixed,vapor_process=vaporprocess)
  end subroutine fraction_check
end program test_v39_aggregate_ice_extinction
