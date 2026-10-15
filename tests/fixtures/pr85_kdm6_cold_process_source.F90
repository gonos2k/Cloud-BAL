! Exact procedure bodies extracted from the immutable applied KDM6 source.
MODULE pr85_kdm6_cold_process_source
  IMPLICIT NONE
  REAL, PARAMETER :: PR85_ICE_NATIVE_INACTIVE_MAX = NEAREST(1.e-14,-1.0)
CONTAINS

    subroutine kdm6_rain_process_fraction(q_fixed,q_process,n_fixed,n_process, &
         bg_fixed,bg_process,t_fixed,t_process,rain_cleanup_pending,density,pidnr,qmin,ncmin, &
         qcrmin,dmr,lambda_min,lambda_max,rho_min,rho_max,pidnc,dmc, &
         lambda_c_min,lambda_c_max,pidni,dmi,lambda_i_min,lambda_i_max, &
         fraction,feasible,search_status,vapor_fixed,vapor_process,consumer_pair_only, &
         ice_transient_mass_limit)
      use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
      implicit none
      real, intent(in) :: q_fixed(5),q_process(5),n_fixed(3),n_process(3)
      real, intent(in) :: bg_fixed,bg_process,t_fixed,t_process,density,pidnr
      logical, intent(in) :: rain_cleanup_pending
      real, intent(in) :: qmin,ncmin,qcrmin,dmr,lambda_min,lambda_max,rho_min,rho_max
      real, intent(in) :: pidnc,dmc,lambda_c_min,lambda_c_max
      real, intent(in) :: pidni,dmi,lambda_i_min,lambda_i_max
      real, intent(out) :: fraction
      logical, intent(out) :: feasible
      integer, intent(out) :: search_status
      real, intent(in), optional :: vapor_fixed,vapor_process
      logical, intent(in), optional :: consumer_pair_only
      real, intent(in), optional :: ice_transient_mass_limit
      ! 0=FEASIBLE, 1=NO_FEASIBLE_STEP, 2=SEARCH_FAILURE.
      integer, parameter :: feasible_status=0,no_step_status=1,search_failure_status=2
      real(kind=8) :: breaks(16),lower,upper,alpha,midpoint,best
      real(kind=8) :: valid_alpha,invalid_alpha,bracket_midpoint,probe_alpha
      real(kind=8) :: midpoint_invalid_alpha,upper_invalid_alpha
      real(kind=8) :: rain_min,rain_max,cloud_min,cloud_max,ice_min,ice_max
      real(kind=8) :: ice_transient_limit
      real(kind=8) :: q0(5),dq(5),n0(3),dn(3),bg0,dbg,qv0,dqv
      real :: q_trial(5),n_trial(3),bg_trial,t_trial,qv_trial,trial
      integer :: count_breaks,i,j,walks
      logical :: interval_valid,step_valid,search_failed,interval_mid_valid
      logical :: interval_lower_valid,midpoint_tested_invalid,probe_valid
      logical :: pair_only

      feasible=.false.
      fraction=0.0
      search_status=search_failure_status
      pair_only=.false.
      if (present(consumer_pair_only)) pair_only=consumer_pair_only
      if (.not.all(ieee_is_finite([q_fixed,q_process,n_fixed,n_process, &
          bg_fixed,bg_process,t_fixed,t_process,density,pidnr,pidnc,pidni, &
          qmin,ncmin,qcrmin,dmr,dmc,dmi,lambda_min,lambda_max, &
          lambda_c_min,lambda_c_max,lambda_i_min,lambda_i_max,rho_min,rho_max]))) return
      if (density.le.0.0 .or. pidnr.le.0.0 .or. pidnc.le.0.0 .or. pidni.le.0.0 .or. &
          lambda_min.le.0.0 .or. lambda_max.lt.lambda_min .or. &
          lambda_c_min.le.0.0 .or. lambda_c_max.lt.lambda_c_min .or. &
          lambda_i_min.le.0.0 .or. lambda_i_max.lt.lambda_i_min .or. &
          rho_min.le.0.0 .or. rho_max.lt.rho_min .or. &
          qmin.lt.0.0 .or. ncmin.lt.0.0 .or. qcrmin.lt.0.0 .or. &
          dmr.le.0.0 .or. dmc.le.0.0 .or. dmi.le.0.0 .or. &
          dmr.gt.8.0 .or. dmc.gt.8.0 .or. dmi.gt.8.0) return
      if (present(vapor_fixed) .neqv. present(vapor_process)) return
      ice_transient_limit=0.0d0
      if (present(ice_transient_mass_limit)) then
        if (.not.ieee_is_finite(ice_transient_mass_limit) .or. &
            ice_transient_mass_limit.lt.0.0 .or. &
            ice_transient_mass_limit.gt.PR85_ICE_NATIVE_INACTIVE_MAX) return
        ice_transient_limit=real(ice_transient_mass_limit,8)
      endif
      qv0=0.0d0; dqv=0.0d0
      if (present(vapor_fixed)) then
        if (.not.all(ieee_is_finite([vapor_fixed,vapor_process]))) return
        if (vapor_fixed.lt.0.0) return
        qv0=real(vapor_fixed,8); dqv=real(vapor_process,8)
      endif

      rain_min=real(density,8)*real(lambda_min,8)**real(dmr,8)/real(pidnr,8)
      rain_max=real(density,8)*real(lambda_max,8)**real(dmr,8)/real(pidnr,8)
      cloud_min=real(density,8)*real(lambda_c_min,8)**real(dmc,8)/real(pidnc,8)
      cloud_max=real(density,8)*real(lambda_c_max,8)**real(dmc,8)/real(pidnc,8)
      ice_min=real(density,8)*real(lambda_i_min,8)**real(dmi,8)/real(pidni,8)
      ice_max=real(density,8)*real(lambda_i_max,8)**real(dmi,8)/real(pidni,8)
      if (.not.all(ieee_is_finite([rain_min,rain_max,cloud_min,cloud_max,ice_min,ice_max]))) return
      if (rain_min.le.0.0d0 .or. cloud_min.le.0.0d0 .or. ice_min.le.0.0d0) return
      if (max(rain_max,cloud_max,ice_max).gt.real(huge(0.0),8)) return
      q0=real(q_fixed,8); dq=real(q_process,8)
      n0=real(n_fixed,8); dn=real(n_process,8)
      bg0=real(bg_fixed,8); dbg=real(bg_process,8)

      count_breaks=2
      search_failed=.false.
      breaks(1)=0.0d0; breaks(2)=1.0d0
      do i=1,5
        call add_breakpoint(q0(i),dq(i),0.0d0)
      enddo
      do i=1,3
        call add_breakpoint(n0(i),dn(i),0.0d0)
      enddo
      if (present(ice_transient_mass_limit)) &
        call add_breakpoint(q0(2),dq(2),ice_transient_limit)
      call add_breakpoint(real(t_fixed,8),real(t_process,8),0.0d0)
      if (present(vapor_fixed)) call add_breakpoint(qv0,dqv,0.0d0)
      if (pair_only) then
        call add_breakpoint(q0(5),dq(5),real(qcrmin,8))
        call add_breakpoint(bg0,dbg,real(1.0e-15,8))
      endif
      call sort_breakpoints()

      best=0.0d0
      do i=1,count_breaks
        alpha=breaks(i)
        if (alpha.le.0.0d0) cycle
        trial=real(alpha)
        call validate_trial(trial,step_valid)
        if (step_valid) best=max(best,real(trial,8))
      enddo

      do i=count_breaks-1,1,-1
        lower=breaks(i); upper=breaks(i+1)
        if (upper.le.lower) cycle
        midpoint=lower+(upper-lower)/2.0d0
        call interval_constraints(midpoint,lower,upper,interval_valid)
        if (.not.interval_valid) cycle
        interval_mid_valid=.false.
        interval_lower_valid=.false.
        midpoint_tested_invalid=.false.
        midpoint=lower+(upper-lower)/2.0d0
        trial=real(midpoint)
        alpha=real(trial,8)
        if (trial.gt.0.0 .and. alpha.ge.lower .and. alpha.le.upper) then
          call validate_trial(trial,step_valid)
          if (step_valid) then
            best=max(best,real(trial,8))
            valid_alpha=real(trial,8)
            interval_mid_valid=.true.
          else
            midpoint_invalid_alpha=real(trial,8)
            midpoint_tested_invalid=.true.
          endif
        endif
        trial=real(lower)
        alpha=real(trial,8)
        if (trial.gt.0.0 .and. alpha.ge.lower .and. alpha.le.upper) then
          call validate_trial(trial,step_valid)
          if (step_valid) then
            best=max(best,real(trial,8))
            interval_lower_valid=.true.
            if (.not.interval_mid_valid) valid_alpha=real(trial,8)
          endif
        endif
        trial=real(upper)
        alpha=real(trial,8)
        if (alpha.gt.upper) then
          trial=nearest(trial,-1.0)
          alpha=real(trial,8)
        endif
        if (alpha.lt.lower) cycle
        walks=0
        do
          if (trial.le.0.0) exit
          call validate_trial(trial,step_valid)
          if (step_valid) then
            best=max(best,real(trial,8))
            exit
          endif
          if (real(trial,8).le.lower) exit
          if (walks.ge.32) then
            search_failed=.true.
            upper_invalid_alpha=real(trial,8)
            if (interval_mid_valid) then
              invalid_alpha=upper_invalid_alpha
              call refine_valid_interval(valid_alpha,invalid_alpha)
            else
              if (interval_lower_valid) then
                if (midpoint_tested_invalid) then
                  invalid_alpha=midpoint_invalid_alpha
                else
                  invalid_alpha=upper_invalid_alpha
                endif
                call refine_valid_interval(valid_alpha,invalid_alpha)
              else
                ! Stored REAL32 rounding may reject the interval midpoint even
                ! when smaller positive fractions still preserve a valid state.
                ! Probe toward the lower edge; any refinement starts from a
                ! trial that passed the exact stored-state validator.
                probe_valid=.false.
                if (midpoint_tested_invalid) then
                  probe_alpha=midpoint_invalid_alpha
                else
                  probe_alpha=upper_invalid_alpha
                endif
                invalid_alpha=probe_alpha
                do j=1,32
                  probe_alpha=lower+(probe_alpha-lower)/2.0d0
                  trial=real(probe_alpha)
                  alpha=real(trial,8)
                  if (trial.le.0.0 .or. alpha.le.lower .or. alpha.ge.invalid_alpha) exit
                  call validate_trial(trial,step_valid)
                  if (step_valid) then
                    valid_alpha=alpha
                    best=max(best,alpha)
                    probe_valid=.true.
                    exit
                  endif
                  invalid_alpha=alpha
                enddo
                if (.not.probe_valid) then
                  trial=nearest(real(lower),1.0)
                  alpha=real(trial,8)
                  if (trial.gt.0.0 .and. alpha.gt.lower .and. alpha.lt.upper) then
                    call validate_trial(trial,step_valid)
                    if (step_valid) then
                      valid_alpha=alpha
                      best=max(best,alpha)
                      probe_valid=.true.
                    endif
                  endif
                endif
                if (probe_valid) call refine_valid_interval(valid_alpha,invalid_alpha)
              endif
            endif
            exit
          endif
          trial=nearest(trial,-1.0)
          walks=walks+1
        enddo
      enddo

      if (search_failed .and. best.le.0.0d0) then
        search_status=search_failure_status
        return
      endif
      if (best.le.0.0d0) then
        search_status=no_step_status
        return
      endif
      fraction=real(best)
      call validate_trial(fraction,step_valid)
      if (.not.step_valid) then
        fraction=0.0
        search_status=search_failure_status
        return
      endif
      feasible=.true.
      search_status=feasible_status

    contains
      subroutine refine_valid_interval(valid,invalid)
        real(kind=8), intent(inout) :: valid,invalid
        real(kind=8) :: candidate
        integer :: refinement
        do refinement=1,32
          bracket_midpoint=valid+(invalid-valid)/2.0d0
          trial=real(bracket_midpoint)
          candidate=real(trial,8)
          if (candidate.le.valid .or. candidate.ge.invalid) exit
          call validate_trial(trial,step_valid)
          if (step_valid) then
            valid=candidate
            best=max(best,candidate)
          else
            invalid=candidate
          endif
        enddo
      end subroutine refine_valid_interval

      subroutine add_breakpoint(initial,slope,cutoff)
        real(kind=8), intent(in) :: initial,slope,cutoff
        real(kind=8) :: root
        if (slope.eq.0.0d0) return
        root=(cutoff-initial)/slope
        if (.not.ieee_is_finite(root)) then
          search_failed=.true.
          return
        endif
        if (root.gt.0.0d0 .and. root.lt.1.0d0 .and. count_breaks.lt.size(breaks)) then
          count_breaks=count_breaks+1
          breaks(count_breaks)=root
        endif
      end subroutine add_breakpoint

      subroutine sort_breakpoints()
        real(kind=8) :: value
        integer :: left,right
        do left=2,count_breaks
          value=breaks(left); right=left-1
          do while (right.ge.1)
            if (breaks(right).le.value) exit
            breaks(right+1)=breaks(right); right=right-1
          enddo
          breaks(right+1)=value
        enddo
        j=1
        do left=2,count_breaks
          if (breaks(left).eq.breaks(j)) cycle
          j=j+1; breaks(j)=breaks(left)
        enddo
        count_breaks=j
      end subroutine sort_breakpoints

      subroutine interval_constraints(sample,lo,hi,valid_interval)
        real(kind=8), intent(in) :: sample
        real(kind=8), intent(inout) :: lo,hi
        logical, intent(out) :: valid_interval
        real(kind=8) :: qm(5),nm(3),bm
        integer :: m
        logical :: rain_active,cloud_active,ice_active
        qm=q0+sample*dq; nm=n0+sample*dn; bm=bg0+sample*dbg
        valid_interval=.true.
        do m=1,5
          call clip(q0(m),dq(m),lo,hi,valid_interval)
        enddo
        do m=1,3
          call clip(n0(m),dn(m),lo,hi,valid_interval)
        enddo
        call clip(bg0,dbg,lo,hi,valid_interval)
        call clip(real(t_fixed,8),real(t_process,8),lo,hi,valid_interval)
        if (present(vapor_fixed)) call clip(qv0,dqv,lo,hi,valid_interval)
        if (.not.valid_interval) return

        if (pair_only) then
          do m=1,3
            if (qm(m).gt.0.0d0 .and. nm(m).gt.0.0d0) then
              call clip(q0(m),dq(m),lo,hi,valid_interval)
              call clip(n0(m),dn(m),lo,hi,valid_interval)
            elseif (m.eq.3 .and. qm(m).eq.0.0d0 .and. nm(m).gt.0.0d0 .and. &
                    rain_cleanup_pending) then
              call clip(q0(m),dq(m),lo,hi,valid_interval)
              call clip(n0(m),dn(m),lo,hi,valid_interval)
            elseif (qm(m).eq.0.0d0 .and. nm(m).eq.0.0d0) then
              call clip(q0(m),dq(m),lo,hi,valid_interval)
              call clip(-q0(m),-dq(m),lo,hi,valid_interval)
              call clip(n0(m),dn(m),lo,hi,valid_interval)
              call clip(-n0(m),-dn(m),lo,hi,valid_interval)
            else
              valid_interval=.false.
            endif
          enddo
          call clip(q0(4),dq(4),lo,hi,valid_interval)
          if (qm(5).gt.0.0d0 .and. bm.gt.0.0d0) then
            call clip(q0(5),dq(5),lo,hi,valid_interval)
            call clip(bg0-q0(5)/real(rho_max,8),dbg-dq(5)/real(rho_max,8),lo,hi,valid_interval)
            call clip(q0(5)/real(rho_min,8)-bg0,dq(5)/real(rho_min,8)-dbg,lo,hi,valid_interval)
            if (qm(5).le.real(qcrmin,8) .and. bm.le.real(1.0e-15,8)) valid_interval=.false.
          elseif (qm(5).eq.0.0d0 .and. bm.eq.0.0d0) then
            call clip(q0(5),dq(5),lo,hi,valid_interval)
            call clip(-q0(5),-dq(5),lo,hi,valid_interval)
            call clip(bg0,dbg,lo,hi,valid_interval)
            call clip(-bg0,-dbg,lo,hi,valid_interval)
          else
            valid_interval=.false.
          endif
          if (lo.gt.hi) valid_interval=.false.
          if (.not.ieee_is_finite(bm)) valid_interval=.false.
          return
        endif

        if (qm(3).gt.0.0d0 .and. nm(3).gt.0.0d0) then
          call clip(q0(3),dq(3),lo,hi,valid_interval)
          call clip(n0(3)-rain_min*q0(3),dn(3)-rain_min*dq(3),lo,hi,valid_interval)
          call clip(rain_max*q0(3)-n0(3),rain_max*dq(3)-dn(3),lo,hi,valid_interval)
        elseif (qm(3).eq.0.0d0) then
          call clip(q0(3),dq(3),lo,hi,valid_interval)
          call clip(-q0(3),-dq(3),lo,hi,valid_interval)
          if (.not.rain_cleanup_pending) then
            call clip(n0(3),dn(3),lo,hi,valid_interval)
            call clip(-n0(3),-dn(3),lo,hi,valid_interval)
          endif
        else
          valid_interval=.false.
        endif
        cloud_active=qm(1).gt.0.0d0 .and. nm(1).gt.0.0d0
        if (cloud_active) then
          call clip(q0(1),dq(1),lo,hi,valid_interval)
          call clip(n0(1),dn(1),lo,hi,valid_interval)
          call clip(n0(1)-cloud_min*q0(1),dn(1)-cloud_min*dq(1),lo,hi,valid_interval)
          call clip(cloud_max*q0(1)-n0(1),cloud_max*dq(1)-dn(1),lo,hi,valid_interval)
        elseif (qm(1).eq.0.0d0 .and. nm(1).eq.0.0d0) then
          call clip(q0(1),dq(1),lo,hi,valid_interval)
          call clip(-q0(1),-dq(1),lo,hi,valid_interval)
          call clip(n0(1),dn(1),lo,hi,valid_interval)
          call clip(-n0(1),-dn(1),lo,hi,valid_interval)
        else
          valid_interval=.false.
        endif
        ice_active=qm(2).gt.0.0d0 .and. nm(2).gt.0.0d0
        if (ice_active) then
          call clip(q0(2),dq(2),lo,hi,valid_interval)
          call clip(n0(2),dn(2),lo,hi,valid_interval)
          if (.not.present(ice_transient_mass_limit) .or. &
              qm(2).gt.ice_transient_limit) then
            call clip(n0(2)-ice_min*q0(2),dn(2)-ice_min*dq(2),lo,hi,valid_interval)
            call clip(ice_max*q0(2)-n0(2),ice_max*dq(2)-dn(2),lo,hi,valid_interval)
          endif
        elseif (qm(2).eq.0.0d0 .and. nm(2).eq.0.0d0) then
          call clip(q0(2),dq(2),lo,hi,valid_interval)
          call clip(-q0(2),-dq(2),lo,hi,valid_interval)
          call clip(n0(2),dn(2),lo,hi,valid_interval)
          call clip(-n0(2),-dn(2),lo,hi,valid_interval)
        else
          valid_interval=.false.
        endif
        do m=4,5
          if (qm(m).gt.0.0d0) then
            call clip(q0(m),dq(m),lo,hi,valid_interval)
          elseif (qm(m).eq.0.0d0) then
            call clip(q0(m),dq(m),lo,hi,valid_interval)
            call clip(-q0(m),-dq(m),lo,hi,valid_interval)
          else
            valid_interval=.false.
          endif
        enddo
        call clip(bg0-q0(5)/real(rho_max,8),dbg-dq(5)/real(rho_max,8),lo,hi,valid_interval)
        call clip(q0(5)/real(rho_min,8)-bg0,dq(5)/real(rho_min,8)-dbg,lo,hi,valid_interval)
        if (lo.gt.hi) valid_interval=.false.
        if (.not.ieee_is_finite(bm)) valid_interval=.false.
      end subroutine interval_constraints

      subroutine clip(initial,slope,lo,hi,valid_interval)
        real(kind=8), intent(in) :: initial,slope
        real(kind=8), intent(inout) :: lo,hi
        logical, intent(inout) :: valid_interval
        real(kind=8) :: boundary
        if (.not.valid_interval) return
        if (slope.eq.0.0d0) then
          if (initial.lt.0.0d0) valid_interval=.false.
        elseif (slope.gt.0.0d0) then
          boundary=-initial/slope
          if (.not.ieee_is_finite(boundary)) search_failed=.true.
          lo=max(lo,boundary)
        else
          boundary=-initial/slope
          if (.not.ieee_is_finite(boundary)) search_failed=.true.
          hi=min(hi,boundary)
        endif
        if (.not.ieee_is_finite(lo) .or. .not.ieee_is_finite(hi)) then
          valid_interval=.false.
          search_failed=.true.
        endif
        if (lo.gt.hi) valid_interval=.false.
      end subroutine clip

      subroutine validate_trial(a,is_valid)
        real, intent(in) :: a
        logical, intent(out) :: is_valid
        integer :: m
        q_trial=q_fixed+a*q_process
        n_trial=n_fixed+a*n_process
        bg_trial=bg_fixed+a*bg_process
        t_trial=t_fixed+a*t_process
        if (present(vapor_fixed)) qv_trial=vapor_fixed+a*vapor_process
        is_valid=all(ieee_is_finite([q_trial,n_trial,bg_trial,t_trial]))
        if (present(vapor_fixed)) is_valid=is_valid.and.ieee_is_finite(qv_trial)
        if (.not.is_valid) return
        if (any(q_trial.lt.0.0) .or. any(n_trial.lt.0.0) .or. bg_trial.lt.0.0) then
          is_valid=.false.; return
        endif
        if (present(vapor_fixed)) then
          if (qv_trial.lt.0.0) then
            is_valid=.false.; return
          endif
        endif
        if (t_trial.le.0.0) then
          is_valid=.false.
          return
        endif
        call kdm6_rain_process_state_valid(q_trial,n_trial,bg_trial,t_trial,density,pidnr, &
             qmin,ncmin,qcrmin,dmr,lambda_min,lambda_max,rho_min,rho_max, &
             pidnc,dmc,lambda_c_min,lambda_c_max,pidni,dmi,lambda_i_min, &
             lambda_i_max,is_valid,rain_cleanup_pending,pair_only,ice_transient_mass_limit)
      end subroutine validate_trial
    end subroutine kdm6_rain_process_fraction

subroutine kdm6_rain_process_state_valid(q,n,bg,temperature,density,pidnr,qmin,ncmin, &
         qcrmin,dmr,lambda_min,lambda_max,rho_min,rho_max,pidnc,dmc, &
         lambda_c_min,lambda_c_max,pidni,dmi,lambda_i_min,lambda_i_max,valid, &
         allow_rain_number_at_zero,consumer_pair_only,ice_transient_mass_limit)
      use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
      implicit none
      real, intent(in) :: q(5),n(3),bg,temperature,density,pidnr,qmin,ncmin,qcrmin,dmr
      real, intent(in) :: lambda_min,lambda_max,rho_min,rho_max,pidnc,dmc
      real, intent(in) :: lambda_c_min,lambda_c_max,pidni,dmi,lambda_i_min,lambda_i_max
      logical, intent(out) :: valid
      logical, intent(in), optional :: allow_rain_number_at_zero
      logical, intent(in), optional :: consumer_pair_only
      real, intent(in), optional :: ice_transient_mass_limit
      real(kind=8) :: rain_min,rain_max,cloud_min,cloud_max,ice_min,ice_max,ice_transient_limit
      logical :: pair_only

      valid=.false.
      if (.not.all(ieee_is_finite([q,n,bg,temperature,density,pidnr,qmin,ncmin,qcrmin,dmr, &
          lambda_min,lambda_max,rho_min,rho_max,pidnc,dmc,lambda_c_min, &
          lambda_c_max,pidni,dmi,lambda_i_min,lambda_i_max]))) return
      if (density.le.0.0 .or. pidnr.le.0.0 .or. pidnc.le.0.0 .or. pidni.le.0.0 .or. &
          qmin.lt.0.0 .or. qcrmin.lt.0.0 .or. lambda_min.le.0.0 .or. &
          lambda_max.lt.lambda_min .or. lambda_c_min.le.0.0 .or. &
          lambda_c_max.lt.lambda_c_min .or. lambda_i_min.le.0.0 .or. &
          lambda_i_max.lt.lambda_i_min .or. rho_min.le.0.0 .or. rho_max.lt.rho_min .or. &
          dmr.le.0.0 .or. dmc.le.0.0 .or. dmi.le.0.0 .or. &
          dmr.gt.8.0 .or. dmc.gt.8.0 .or. dmi.gt.8.0) return
      ice_transient_limit=0.0d0
      if (present(ice_transient_mass_limit)) then
        if (.not.ieee_is_finite(ice_transient_mass_limit) .or. &
            ice_transient_mass_limit.lt.0.0 .or. ice_transient_mass_limit.gt.PR85_ICE_NATIVE_INACTIVE_MAX) return
        ice_transient_limit=real(ice_transient_mass_limit,8)
      endif
      if (temperature.le.0.0) return
      if (any(q.lt.0.0) .or. any(n.lt.0.0) .or. bg.lt.0.0) return
      pair_only=.false.
      if (present(consumer_pair_only)) pair_only=consumer_pair_only
      if (pair_only) then
        if (q(1).eq.0.0) then
          if (n(1).ne.0.0) return
        elseif (n(1).le.0.0) then
          return
        endif
        if (q(2).eq.0.0) then
          if (n(2).ne.0.0) return
        elseif (n(2).le.0.0) then
          return
        endif
        if (q(3).eq.0.0) then
          if (n(3).ne.0.0) then
            if (.not.present(allow_rain_number_at_zero)) return
            if (.not.allow_rain_number_at_zero) return
          endif
        elseif (n(3).le.0.0) then
          return
        endif
        if (q(5).eq.0.0) then
          if (bg.ne.0.0) return
        else
          if (bg.le.0.0) return
          if (real(q(5),8)/real(bg,8).lt.real(rho_min,8) .or. &
              real(q(5),8)/real(bg,8).gt.real(rho_max,8)) return
          if (q(5).le.qcrmin .and. bg.le.1.0e-15) return
        endif
        valid=.true.
        return
      endif
      rain_min=real(density,8)*real(lambda_min,8)**real(dmr,8)/real(pidnr,8)
      rain_max=real(density,8)*real(lambda_max,8)**real(dmr,8)/real(pidnr,8)
      cloud_min=real(density,8)*real(lambda_c_min,8)**real(dmc,8)/real(pidnc,8)
      cloud_max=real(density,8)*real(lambda_c_max,8)**real(dmc,8)/real(pidnc,8)
      ice_min=real(density,8)*real(lambda_i_min,8)**real(dmi,8)/real(pidni,8)
      ice_max=real(density,8)*real(lambda_i_max,8)**real(dmi,8)/real(pidni,8)
      if (.not.all(ieee_is_finite([rain_min,rain_max,cloud_min,cloud_max,ice_min,ice_max]))) return
      if (max(rain_max,cloud_max,ice_max).gt.real(huge(0.0),8)) return
      if (q(1).eq.0.0) then
        if (n(1).ne.0.0) return
      elseif (q(1).le.0.0 .or. n(1).le.0.0) then
        return
      elseif (real(n(1),8).lt.cloud_min*q(1) .or. real(n(1),8).gt.cloud_max*q(1)) then
        return
      endif
      if (q(2).eq.0.0) then
        if (n(2).ne.0.0) return
      elseif (q(2).le.0.0 .or. n(2).le.0.0) then
        return
      elseif (q(2).gt.ice_transient_limit) then
        if (real(n(2),8).lt.ice_min*q(2) .or. real(n(2),8).gt.ice_max*q(2)) return
      endif
      if (q(3).eq.0.0) then
        if (n(3).ne.0.0) then
          if (.not.present(allow_rain_number_at_zero)) return
          if (.not.allow_rain_number_at_zero) return
        endif
      elseif (q(3).le.0.0 .or. n(3).le.0.0) then
        return
      elseif (real(n(3),8).lt.rain_min*q(3) .or. real(n(3),8).gt.rain_max*q(3)) then
        return
      endif
      if (q(4).lt.0.0 .or. q(5).lt.0.0) return
      if (real(bg,8).lt.real(q(5),8)/real(rho_max,8) .or. &
          real(bg,8).gt.real(q(5),8)/real(rho_min,8)) return
      valid=.true.
    end subroutine kdm6_rain_process_state_valid
END MODULE pr85_kdm6_cold_process_source

PROGRAM test_pr85_kdm6_cold_process
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64,int32
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_value,ieee_quiet_nan
  USE pr85_kdm6_cold_process_source, ONLY: kdm6_rain_process_fraction, &
       kdm6_rain_process_state_valid,PR85_ICE_NATIVE_INACTIVE_MAX
  IMPLICIT NONE
  REAL(real32), PARAMETER :: rho=1.0_real32, qmin=1.0e-15_real32, &
       qcrmin=1.0e-9_real32, ncmin=0.0_real32, t0=273.15_real32
  REAL(real32), PARAMETER :: pidnr=1.0_real32, pidnc=1.0_real32, pidni=1.0_real32
  REAL(real32), PARAMETER :: dmr=3.0_real32, dmc=3.0_real32, dmi=3.0_real32
  REAL(real32), PARAMETER :: lmin=1.0_real32, lmax=2.0_real32
  REAL(real32), PARAMETER :: lcmin=1.0_real32, lcmax=2.0_real32
  REAL(real32), PARAMETER :: limin=1.0_real32, limax=2.0_real32
  REAL(real32), PARAMETER :: rhomin=100.0_real32, rhomax=900.0_real32
  REAL(real32), PARAMETER :: rho_actual=0.626187264919281006_real32
  REAL(real32), PARAMETER :: pidni_actual=1570.79638671875_real32
  REAL(real32), PARAMETER :: lambda_imin_actual=9080.0_real32
  REAL(real32), PARAMETER :: lambda_imax_actual=1820000.0_real32
  REAL(real32), PARAMETER :: q_initial=1.63666927255690098e-3_real32
  REAL(real32), PARAMETER :: n_initial=6.91226437500000000e5_real32
  REAL(real32), PARAMETER :: q_staged=1.78378447890281677e-3_real32
  REAL(real32), PARAMETER :: n_staged=5.32334125000000000e5_real32
  REAL(real32), PARAMETER :: dt=20.0_real32
  REAL(real32), PARAMETER :: rate_psaut=6.50967740511987358e-6_real32
  REAL(real32), PARAMETER :: rate_psaci=1.49579033603686185e-8_real32
  REAL(real32), PARAMETER :: rate_pidep=5.15952763180393958e-7_real32
  REAL(real32), PARAMETER :: rate_piacw=1.33644271045341156e-5_real32
  REAL(real32), PARAMETER :: rate_pmulcs=1.32632238525332014e-11_real32
  REAL(real32), PARAMETER :: rate_nsaut=7971.95703125_real32
  REAL(real32), PARAMETER :: rate_nsaci=4.3842778205871582_real32
  REAL(real32), PARAMETER :: rate_nmulcs=31.7237606048583984_real32
  REAL(real32), PARAMETER :: ice_qmin=1.0e-15_real32
  REAL(real32), PARAMETER :: ice_qcrmin=1.0e-9_real32
  REAL(real64), PARAMETER :: r64=1.0_real64
  REAL(real64) :: cloud_ratio_min,cloud_ratio_max
  REAL(real64) :: mean_mass_min,mean_mass_max,mean_mass_mid
  REAL(real32) :: q(5),n(3),bg
  REAL(real32) :: qf(5),qp(5),nf(3),np(3),fraction
  REAL(real32) :: qv_process_q(5),qv_process_n(3)
  LOGICAL :: feasible
  INTEGER :: status
  REAL(real64) :: computed_mean
  INTEGER :: d2,d3
  REAL(real64) :: qdelta(5), bga, bgr, bgi, bpraci, bpsacr, bpgacr
  REAL(real64) :: pa, pracs, piacr, praci, psacr, pgacr
  REAL(real64), PARAMETER :: denr=1000.0_real64, dens=100.0_real64, deni=917.0_real64
  REAL(real64), PARAMETER :: cpm_test=1004.0_real64, xls_test=2.834e6_real64
  REAL(real32) :: nan_value

  ! Independently derive number-per-mass and mean-mass bounds from the
  ! PSD parameterization, rather than reading limits out of the predicate.
  cloud_ratio_min=REAL(rho,real64)*REAL(lcmin,real64)**REAL(dmc,real64)/REAL(pidnc,real64)
  cloud_ratio_max=REAL(rho,real64)*REAL(lcmax,real64)**REAL(dmc,real64)/REAL(pidnc,real64)
  mean_mass_min=REAL(rho,real64)/cloud_ratio_max
  mean_mass_max=REAL(rho,real64)/cloud_ratio_min
  mean_mass_mid=0.5_real64*(mean_mass_min+mean_mass_max)
  q=0.0_real32; n=0.0_real32; bg=0.0_real32
  q(1)=0.5_real32*qmin
  n(1)=REAL(r64*REAL(q(1),real64)/mean_mass_mid,real32)
  computed_mean=r64*REAL(q(1),real64)/REAL(n(1),real64)
  CALL check_mean('positive cloud below qmin',computed_mean)
  CALL expect_state('positive in-cone QC below qmin',q,n,bg,.TRUE.)

  q(1)=qmin
  n(1)=REAL(r64*REAL(q(1),real64)/mean_mass_mid,real32)
  computed_mean=r64*REAL(q(1),real64)/REAL(n(1),real64)
  CALL check_mean('cloud at qmin',computed_mean)
  CALL expect_state('QC exactly qmin remains represented',q,n,bg,.TRUE.)

  q=0.0_real32; n=0.0_real32
  q(3)=0.5_real32*qcrmin
  n(3)=REAL(r64*REAL(q(3),real64)/mean_mass_mid,real32)
  computed_mean=r64*REAL(q(3),real64)/REAL(n(3),real64)
  CALL check_mean('positive rain below qcrmin',computed_mean)
  CALL expect_state('positive in-cone QR below qcrmin with cleanup pending', &
       q,n,bg,.TRUE.,.TRUE.)
  q(3)=qcrmin
  n(3)=REAL(r64*REAL(q(3),real64)/mean_mass_mid,real32)
  computed_mean=r64*REAL(q(3),real64)/REAL(n(3),real64)
  CALL check_mean('rain at qcrmin',computed_mean)
  CALL expect_state('QR exactly qcrmin remains represented',q,n,bg,.TRUE.)

  q=0.0_real32; n=0.0_real32
  q(5)=0.5_real32*qcrmin
  bg=q(5)/500.0_real32
  CALL expect_state('positive graupel below qcrmin with matching volume',q,n,bg,.TRUE.)
  q(5)=qcrmin
  bg=q(5)/500.0_real32
  CALL expect_state('graupel exactly qcrmin with matching volume',q,n,bg,.TRUE.)

  q=0.0_real32; n=0.0_real32; bg=0.0_real32
  n(1)=1.0e-6_real32
  CALL expect_state('number-only cloud rejected',q,n,bg,.FALSE.)
  q(1)=1.0e-6_real32
  n(1)=REAL(r64*REAL(q(1),real64)/(0.5_real64*mean_mass_min),real32)
  CALL expect_state('positive cloud outside mass-per-particle cone rejected',q,n,bg,.FALSE.)
  q(1)=-1.0e-6_real32; n(1)=0.0_real32
  CALL expect_state('negative cloud rejected',q,n,bg,.FALSE.)
  PRINT '(a)', 'CASE tiny positive pairs and exact cutoffs accepted only inside the physical cone'

  ! A paired low-Q source from zero is admitted at full fraction when its
  ! independently computed mass per particle lies inside the source cone.
  qf=0.0_real32; nf=0.0_real32; qp=0.0_real32; np=0.0_real32
  qp(1)=0.5_real32*qmin
  np(1)=REAL(r64*REAL(qp(1),real64)/mean_mass_mid,real32)
  CALL apply_fraction('tiny paired cloud source',qf,qp,nf,np,0.0_real32,0.0_real32, &
       fraction,feasible,status)
  IF (.NOT.feasible .OR. status/=0 .OR. fraction/=1.0_real32) &
       ERROR STOP 'valid subthreshold pair was not fully admitted'
  PRINT '(a)', 'CASE positive subthreshold cloud source admitted with shared fraction 1'

  ! Autoconversion control: an in-cone cloud-to-rain pair conserves total Q
  ! and number and admits fully.
  qf=0.0_real32; nf=0.0_real32; qp=0.0_real32; np=0.0_real32
  qf(1)=1.0e-4_real32
  nf(1)=REAL(r64*REAL(qf(1),real64)/mean_mass_mid,real32)
  qp(1)=-1.0e-5_real32; qp(3)=1.0e-5_real32
  np(1)=REAL(-r64*REAL(1.0e-5_real32,real64)/mean_mass_mid,real32)
  np(3)=-np(1)
  CALL apply_fraction('in-cone autoconversion',qf,qp,nf,np,0.0_real32,0.0_real32, &
       fraction,feasible,status)
  IF (.NOT.feasible .OR. status/=0 .OR. fraction/=1.0_real32) &
       ERROR STOP 'in-cone autoconversion not accepted'
  IF (ABS(SUM(REAL(qf,real64)+REAL(qp,real64))-SUM(REAL(qf,real64)))>1.0e-12_real64) &
       ERROR STOP 'autoconversion mass source did not sum to zero'
  IF (ABS(SUM(REAL(np,real64)))>1.0e-12_real64) ERROR STOP 'autoconversion number source did not sum to zero'

  ! A paired source whose receiver's number/mass ratio is below the physical
  ! lower bound has no positive feasible alpha, although the fixed base is valid.
  qf=0.0_real32; nf=0.0_real32; qp=0.0_real32; np=0.0_real32
  qf(1)=1.0e-4_real32
  nf(1)=REAL(r64*REAL(qf(1),real64)/mean_mass_mid,real32)
  qp(1)=-1.0e-5_real32; qp(3)=1.0e-5_real32
  np(1)=-1.0e-3_real32; np(3)=1.0e-3_real32
  CALL expect_state('autoconversion fixed base',qf,nf,0.0_real32,.TRUE.)
  CALL apply_fraction('autoconversion receiver outside cone',qf,qp,nf,np,0.0_real32,0.0_real32, &
       fraction,feasible,status)
  IF (feasible .OR. status/=1 .OR. fraction/=0.0_real32) &
       ERROR STOP 'no-positive autoconversion packet status/base contract failed'
  CALL expect_state('autoconversion unchanged valid base',qf,nf,0.0_real32,.TRUE.)
  PRINT '(a)', 'CASE isolated autoconversion bounded; no positive step returns status 1 and alpha 0'

  ! Vapor is a shared budget across sequential source groups. A later group
  ! must use the vapor left by the earlier accepted group.
  qf=0.0_real32; nf=0.0_real32; qp=0.0_real32; np=0.0_real32
  qp(2)=0.75_real32
  np(2)=REAL(r64*REAL(qp(2),real64)/mean_mass_mid,real32)
  qv_process_q=0.0_real32; qv_process_n=0.0_real32
  qv_process_q(5)=0.75_real32
  CALL apply_fraction('NG vapor transfer',qf,qp,nf,np,0.0_real32,0.0_real32, &
       fraction,feasible,status,1.0_real32,-0.75_real32)
  IF (.NOT.feasible .OR. status/=0 .OR. fraction/=1.0_real32) &
       ERROR STOP 'NG vapor transfer was not fully admitted'
  qf=qf+fraction*qp; nf=nf+fraction*np
  computed_mean=REAL(qf(2),real64)/REAL(nf(2),real64)
  IF (computed_mean<mean_mass_min .OR. computed_mean>mean_mass_max) &
       ERROR STOP 'NG receiver pair left the independently derived ice cone'
  nan_value=ieee_value(0.0_real32,ieee_quiet_nan)
  CALL apply_fraction('G vapor transfer uses remaining vapor',qf,qv_process_q,nf, &
       qv_process_n,0.0_real32,0.75_real32/500.0_real32, &
       fraction,feasible,status,0.25_real32,-0.75_real32)
  IF (.NOT.feasible .OR. status/=0 .OR. fraction>1.0_real32/3.0_real32 .OR. &
      fraction<0.3333_real32) ERROR STOP 'G did not respect sequential remaining-vapor cap'
  IF (0.25_real32+fraction*(-0.75_real32)<0.0_real32) &
       ERROR STOP 'sequential G update made vapor negative'
  qv_process_q=0.0_real32; qv_process_n=0.0_real32
  CALL apply_fraction('nonfinite vapor rejected',qf,qp,nf,np,0.0_real32,0.0_real32, &
       fraction,feasible,status,nan_value,0.0_real32)
  IF (feasible .OR. status/=2 .OR. fraction/=0.0_real32) &
       ERROR STOP 'nonfinite vapor did not fail closed'
  CALL apply_fraction('QV reaches exact zero',qf,qv_process_q,nf,qv_process_n, &
       0.0_real32,0.0_real32,fraction,feasible,status,0.25_real32,-0.25_real32)
  IF (.NOT.feasible .OR. status/=0 .OR. fraction/=1.0_real32) &
       ERROR STOP 'valid exact-zero QV endpoint was not admitted'
  CALL check_vapor_option_pair()
  PRINT '(a)', 'CASE NG then G shares sequential QV budget; nonfinite QV rejects'

  CALL check_full_breakpoint_capacity(mean_mass_mid)
  CALL check_group_water_and_heat_ledger()
  CALL check_native_order_composite_retry()
  CALL check_subnormal_ice_interior_retry()
  CALL check_captured_ng_search_rounding()
  CALL check_explicit_ice_transient_policy()

  ! Exercise every delta2/delta3 routing corner and check mass + volume ledgers.
  pa=0.3_real64; pracs=0.7_real64; piacr=0.5_real64; praci=0.4_real64
  psacr=0.2_real64; pgacr=0.6_real64
  DO d2=0,1
    DO d3=0,1
      CALL check_delta_routing(d2,d3,pa,pracs,piacr,praci,psacr,pgacr)
    END DO
  END DO
  PRINT '(a)', 'CASE delta2/delta3 routing conserves Q and matches each graupel volume source'
  PRINT '(a)', 'PR85 KDM6 cold process cases PASS'

CONTAINS
  SUBROUTINE expect_state(label,qx,nx,bx,want,cleanup_pending)
    CHARACTER(len=*), INTENT(IN) :: label
    REAL(real32), INTENT(IN) :: qx(5),nx(3),bx
    LOGICAL, INTENT(IN) :: want
    LOGICAL, INTENT(IN), OPTIONAL :: cleanup_pending
    LOGICAL :: got
    IF (PRESENT(cleanup_pending)) THEN
      CALL kdm6_rain_process_state_valid(qx,nx,bx,t0,rho,pidnr,qmin,ncmin,qcrmin,dmr, &
           lmin,lmax,rhomin,rhomax,pidnc,dmc,lcmin,lcmax,pidni,dmi,limin,limax,got,cleanup_pending)
    ELSE
      CALL kdm6_rain_process_state_valid(qx,nx,bx,t0,rho,pidnr,qmin,ncmin,qcrmin,dmr, &
           lmin,lmax,rhomin,rhomax,pidnc,dmc,lcmin,lcmax,pidni,dmi,limin,limax,got)
    ENDIF
    IF (got.NEQV.want) THEN
      PRINT *, 'state mismatch: ',TRIM(label),' expected=',want,' got=',got
      ERROR STOP 'state predicate result mismatch'
    ENDIF
  END SUBROUTINE expect_state

  SUBROUTINE check_native_order_composite_retry()
    REAL(real32) :: gamma,q_candidate,n_candidate
    REAL(real32) :: q_before(5),n_before(3),q_trial(5),n_trial(3),model_q(5),model_n(3)
    LOGICAL :: candidate_valid
    REAL(real64) :: ice_lower,edge_residual

    q_before=0.0_real32; n_before=0.0_real32
    q_before(2)=q_initial; n_before(2)=n_initial
    model_q=q_before; model_n=n_before
    ice_lower=REAL(rho_actual,real64)*REAL(lambda_imin_actual,real64)**3 / &
         REAL(pidni_actual,real64)
    edge_residual=REAL(532334.0625_real32,real64)- &
         ice_lower*REAL(q_staged,real64)
    IF (ABS(edge_residual+8.93851020373404026e-3_real64)>2.0e-5_real64) &
         ERROR STOP 'captured native-order ice endpoint witness changed'

    ! The staged sequential endpoint is valid, but the exact native-order
    ! REAL32 QI/NI assignments differ by one NI ulp and fail the ice lower edge.
    q_trial=q_before; n_trial=n_before
    q_trial(2)=q_staged; n_trial(2)=n_staged
    CALL native_state_valid(q_trial,n_trial,candidate_valid)
    IF (.NOT.candidate_valid) ERROR STOP 'sequential staged witness is not in the ice cone'

    gamma=1.0_real32
    CALL native_trial(gamma,q_candidate,n_candidate)
    IF (q_candidate/=q_staged .OR. n_candidate/=532334.0625_real32) &
         ERROR STOP 'native-order REAL32 candidate no longer reproduces the saved endpoint'
    q_trial=q_before; n_trial=n_before
    q_trial(2)=q_candidate; n_trial(2)=n_candidate
    CALL native_state_valid(q_trial,n_trial,candidate_valid)
    IF (candidate_valid) ERROR STOP 'native-order one-ulp candidate unexpectedly passed PSD'
    IF (ANY(model_q/=q_before) .OR. ANY(model_n/=n_before)) &
         ERROR STOP 'rejected composite trial modified committed model state'

    gamma=0.5_real32
    CALL native_trial(gamma,q_candidate,n_candidate)
    q_trial=q_before; n_trial=n_before
    q_trial(2)=q_candidate; n_trial(2)=n_candidate
    CALL native_state_valid(q_trial,n_trial,candidate_valid)
    IF (.NOT.candidate_valid) ERROR STOP 'common-gamma backtracking found no feasible retry'
    model_q=q_trial; model_n=n_trial
    IF (model_q(2)/=q_candidate .OR. model_n(2)/=n_candidate) &
         ERROR STOP 'validated composite candidate did not commit atomically'
    PRINT '(a,1x,es14.6,1x,a,1x,es14.6)', &
         'COMPOSITE_RETRY gamma=',gamma,'lower_edge_residual=',edge_residual
  END SUBROUTINE check_native_order_composite_retry

  SUBROUTINE check_subnormal_ice_interior_retry()
    REAL(real32), PARAMETER :: rho_subnormal=0.208079591393470764_real32
    REAL(real32) :: q_fixed(5),q_process(5),n_fixed(3),n_process(3)
    REAL(real32) :: fraction,q_after(5),n_after(3),qv_after
    LOGICAL :: feasible,valid
    INTEGER :: result_status
    REAL(real64) :: ice_ratio_max,q_zero_root,ice_upper_root

    q_fixed=0.0_real32; q_process=0.0_real32
    n_fixed=0.0_real32; n_process=0.0_real32
    q_fixed(2)=2.802596928649634e-44_real32
    q_process(2)=-1.0e-15_real32
    n_fixed(2)=3.602887200616686e-34_real32
    q_zero_root=-REAL(q_fixed(2),real64)/REAL(q_process(2),real64)
    ice_ratio_max=REAL(rho_subnormal,real64)*REAL(lambda_imax_actual,real64)**3/ &
         REAL(pidni_actual,real64)
    ice_upper_root=(REAL(q_fixed(2),real64)-REAL(n_fixed(2),real64)/ice_ratio_max)/ &
         ABS(REAL(q_process(2),real64))
    IF (.NOT.(0.0_real64<ice_upper_root .AND. ice_upper_root<q_zero_root)) &
         ERROR STOP 'independent ice-cone interval roots are not ordered'
    CALL kdm6_rain_process_fraction(q_fixed,q_process,n_fixed,n_process,0.0_real32,0.0_real32, &
         206.614_real32,-2.837185e-12_real32,.FALSE.,rho_subnormal, &
         1.0_real32,1.0e-15_real32,0.0_real32,1.0e-9_real32,3.0_real32, &
         961.0_real32,35000.0_real32,100.0_real32,900.0_real32, &
         1.0_real32,3.0_real32,12000.0_real32,500000.0_real32, &
         pidni_actual,3.0_real32,lambda_imin_actual,lambda_imax_actual, &
         fraction,feasible,result_status,2.0001478e-5_real32,1.0e-15_real32)
    IF (.NOT.feasible .OR. result_status/=0 .OR. fraction<=0.0_real32 .OR. &
        REAL(fraction,real64)>=ice_upper_root) &
         ERROR STOP 'valid subnormal ice donor was misclassified as search failure/no step'
    q_after=q_fixed+fraction*q_process
    n_after=n_fixed+fraction*n_process
    qv_after=2.0001478e-5_real32+fraction*1.0e-15_real32
    IF (q_after(2)<=0.0_real32 .OR. q_after(2)>=q_fixed(2) .OR. n_after(2)/=n_fixed(2) .OR. &
        qv_after<=0.0_real32) ERROR STOP 'interior retry did not preserve the paired source state'
    CALL kdm6_rain_process_state_valid(q_after,n_after,0.0_real32,206.614_real32, &
         rho_subnormal,1.0_real32,1.0e-15_real32,0.0_real32,1.0e-9_real32, &
         3.0_real32,961.0_real32,35000.0_real32,100.0_real32,900.0_real32, &
         1.0_real32,3.0_real32,12000.0_real32,500000.0_real32, &
         pidni_actual,3.0_real32,lambda_imin_actual,lambda_imax_actual,valid)
    IF (.NOT.valid) ERROR STOP 'accepted subnormal interior is outside the stored PSD cone'
    PRINT '(a,1x,es14.6,1x,a,1x,es14.6,1x,a,1x,es14.6,1x,a,1x,es14.6)', &
         'SUBNORMAL_ICE_RETRY alpha=',fraction,'q_after=',q_after(2), &
         'ice_upper_root=',ice_upper_root,'q_zero_root=',q_zero_root
  END SUBROUTINE check_subnormal_ice_interior_retry

  SUBROUTINE check_captured_ng_search_rounding()
    REAL(real32) :: qf(5),qp(5),nf(3),np(3),frac,qafter(5),nafter(3),bgafter,tafter,qvafter
    REAL(real32) :: rho_case,pidnr_case,qmin_case,ncmin_case,qcrmin_case,dmr_case
    REAL(real32) :: lmin_case,lmax_case,rhomin_case,rhomax_case,pidnc_case,dmc_case
    REAL(real32) :: lcmin_case,lcmax_case,pidni_case,dmi_case,limin_case,limax_case
    LOGICAL :: feasible,valid
    INTEGER :: result_status

    qf=[r32bits('3B438213'),r32bits('37826E76'),r32bits('390EF350'), &
        r32bits('3AAD1A62'),r32bits('00000000')]
    qp=[r32bits('B8062203'),r32bits('B5DF0F39'),r32bits('3803C1FE'), &
        r32bits('B4BFE80D'),r32bits('00000000')]
    nf=[r32bits('4E09DDA0'),r32bits('459D4FB0'),r32bits('44BF34B9')]
    np=[r32bits('CAEC864A'),r32bits('C4FB2925'),r32bits('C1832A6E')]
    rho_case=r32bits('3F2DE873')
    pidnr_case=r32bits('4644597C'); qmin_case=r32bits('26901D7D')
    ncmin_case=r32bits('41200000'); qcrmin_case=r32bits('3089705F')
    dmr_case=r32bits('40400000'); lmin_case=r32bits('44704000')
    lmax_case=r32bits('4708B800'); rhomin_case=r32bits('42C80000')
    rhomax_case=r32bits('44610000'); pidnc_case=r32bits('4402E653')
    dmc_case=r32bits('40400000'); lcmin_case=r32bits('463B8000')
    lcmax_case=r32bits('48F42400'); pidni_case=r32bits('44C4597C')
    dmi_case=r32bits('40400000'); limin_case=r32bits('460DE000')
    limax_case=r32bits('49DE2B00')

    CALL kdm6_rain_process_state_valid(qf,nf,0.0_real32,r32bits('43884E9A'), &
         rho_case,pidnr_case,qmin_case,ncmin_case,qcrmin_case,dmr_case, &
         lmin_case,lmax_case,rhomin_case,rhomax_case,pidnc_case,dmc_case, &
         lcmin_case,lcmax_case,pidni_case,dmi_case,limin_case,limax_case,valid)
    IF (.NOT.valid) ERROR STOP 'captured SEARCH_FAILURE base is not valid'

    CALL kdm6_rain_process_fraction(qf,qp,nf,np,0.0_real32,0.0_real32, &
         r32bits('43884E9A'),r32bits('BBE8A4E4'),.FALSE.,rho_case,pidnr_case, &
         qmin_case,ncmin_case,qcrmin_case,dmr_case,lmin_case,lmax_case, &
         rhomin_case,rhomax_case,pidnc_case,dmc_case,lcmin_case,lcmax_case, &
         pidni_case,dmi_case,limin_case,limax_case,frac,feasible,result_status, &
         r32bits('3BDAC37A'),r32bits('362D84EE'))
    IF (.NOT.feasible .OR. result_status/=0 .OR. frac<=0.0_real32) &
         ERROR STOP 'valid interior of captured cold-process interval was not found'

    qafter=qf+frac*qp; nafter=nf+frac*np
    bgafter=0.0_real32; tafter=r32bits('43884E9A')+frac*r32bits('BBE8A4E4')
    qvafter=r32bits('3BDAC37A')+frac*r32bits('362D84EE')
    CALL kdm6_rain_process_state_valid(qafter,nafter,bgafter,tafter,rho_case, &
         pidnr_case,qmin_case,ncmin_case,qcrmin_case,dmr_case,lmin_case,lmax_case, &
         rhomin_case,rhomax_case,pidnc_case,dmc_case,lcmin_case,lcmax_case, &
         pidni_case,dmi_case,limin_case,limax_case,valid)
    IF (.NOT.valid .OR. qafter(2)<=0.0_real32 .OR. nafter(2)<=0.0_real32) &
         ERROR STOP 'accepted captured fraction failed exact REAL32 state validation'
    PRINT '(a,1x,es14.6,1x,a,1x,es14.6,1x,a,1x,es14.6)', &
         'CAPTURED_NG_RETRY alpha=',frac,'QI_after=',qafter(2),'NI_after=',nafter(2)
  END SUBROUTINE check_captured_ng_search_rounding

  PURE FUNCTION r32bits(hex) RESULT(value)
    CHARACTER(len=8), INTENT(IN) :: hex
    REAL(real32) :: value
    INTEGER(int32) :: bits
    READ(hex,'(z8)') bits
    value=TRANSFER(bits,value)
  END FUNCTION r32bits

  SUBROUTINE native_trial(common_gamma,q_after,n_after)
    REAL(real32), INTENT(IN) :: common_gamma
    REAL(real32), INTENT(OUT) :: q_after,n_after
    REAL(real32) :: psaut,praci,psaci,pgaci,pinud,pidep,piacw,pmulcs,pmulcg,pmulrs,pmulrg
    REAL(real32) :: nraci,nsaci,ngaci,niacr,ninud,nmulcs,nmulcg,nmulrs,nmulrg,nsaut
    psaut=rate_psaut*common_gamma; praci=0.0_real32
    psaci=rate_psaci*common_gamma; pgaci=0.0_real32; pinud=0.0_real32
    pidep=rate_pidep*common_gamma; piacw=rate_piacw*common_gamma
    pmulcs=rate_pmulcs*common_gamma; pmulcg=0.0_real32
    pmulrs=0.0_real32; pmulrg=0.0_real32
    nraci=0.0_real32; nsaci=rate_nsaci*common_gamma; ngaci=0.0_real32; niacr=0.0_real32
    ninud=0.0_real32; nmulcs=rate_nmulcs*common_gamma
    nmulcg=0.0_real32; nmulrs=0.0_real32; nmulrg=0.0_real32
    nsaut=rate_nsaut*common_gamma
    q_after=q_initial-(psaut+praci+psaci+pgaci-pinud-pidep-piacw-pmulcs-pmulcg &
         -pmulrs-pmulrg)*dt
    n_after=n_initial+(-nraci-nsaci-ngaci-niacr+ninud+nmulcs+nmulcg+nmulrs+nmulrg &
         -nsaut)*dt
  END SUBROUTINE native_trial

  SUBROUTINE native_state_valid(qx,nx,valid)
    REAL(real32), INTENT(IN) :: qx(5),nx(3)
    LOGICAL, INTENT(OUT) :: valid
    CALL kdm6_rain_process_state_valid(qx,nx,0.0_real32,269.814453125_real32, &
         rho_actual,1.0_real32,ice_qmin,0.0_real32,ice_qcrmin,3.0_real32, &
         1.0_real32,2.0_real32,100.0_real32,900.0_real32,1.0_real32,3.0_real32, &
         1.0_real32,2.0_real32,pidni_actual,3.0_real32,lambda_imin_actual, &
         lambda_imax_actual,valid)
  END SUBROUTINE native_state_valid

  SUBROUTINE check_mean(label,mean)
    CHARACTER(len=*), INTENT(IN) :: label
    REAL(real64), INTENT(IN) :: mean
    IF (.NOT.(mean>=mean_mass_min .AND. mean<=mean_mass_max)) &
         ERROR STOP 'independent mean mass outside cone'
    PRINT '(a,1x,a,1x,es14.6,1x,a,1x,es14.6,1x,es14.6)', &
         'MEAN_MASS',TRIM(label),mean,'BOUNDS',mean_mass_min,mean_mass_max
  END SUBROUTINE check_mean

  SUBROUTINE apply_fraction(label,qfixed,qprocess,nfixed,nprocess,bfixed,bprocess, &
       result_fraction,result_feasible,result_status,qvfixed,qvprocess)
    CHARACTER(len=*), INTENT(IN) :: label
    REAL(real32), INTENT(IN) :: qfixed(5),qprocess(5),nfixed(3),nprocess(3)
    REAL(real32), INTENT(IN) :: bfixed,bprocess
    REAL(real32), INTENT(OUT) :: result_fraction
    LOGICAL, INTENT(OUT) :: result_feasible
    INTEGER, INTENT(OUT) :: result_status
    REAL(real32), INTENT(IN), OPTIONAL :: qvfixed,qvprocess
    CALL kdm6_rain_process_fraction(qfixed,qprocess,nfixed,nprocess,bfixed,bprocess, &
         t0,0.0_real32,.FALSE.,rho,pidnr,qmin,ncmin,qcrmin,dmr,lmin,lmax, &
         rhomin,rhomax,pidnc,dmc,lcmin,lcmax,pidni,dmi,limin,limax, &
         result_fraction,result_feasible,result_status,qvfixed,qvprocess)
    PRINT '(a,1x,a,1x,a,1x,l1,1x,a,1x,i0,1x,a,1x,es14.6)', &
         'FRACTION',TRIM(label),'FEASIBLE',result_feasible,'STATUS',result_status, &
         'ALPHA',result_fraction
  END SUBROUTINE apply_fraction

  SUBROUTINE check_full_breakpoint_capacity(mean_mass)
    REAL(real64), INTENT(IN) :: mean_mass
    REAL(real32) :: qbase(5),qprocess(5),nbase(3),nprocess(3),bbase,bprocess
    REAL(real32) :: fraction_local
    LOGICAL :: feasible_local
    INTEGER :: status_local,m
    REAL(real64), PARAMETER :: qroots(5)=[0.60_real64,0.65_real64,0.70_real64, &
         0.75_real64,0.80_real64], nroots(3)=[0.82_real64,0.84_real64,0.86_real64]
    qbase=[1.0e-4_real32,1.2e-4_real32,1.4e-4_real32,1.6e-4_real32,1.8e-4_real32]
    nbase(1)=REAL(REAL(qbase(1),real64)/mean_mass,real32)
    nbase(2)=REAL(REAL(qbase(2),real64)/mean_mass,real32)
    nbase(3)=REAL(REAL(qbase(3),real64)/mean_mass,real32)
    qprocess=0.0_real32; nprocess=0.0_real32
    DO m=1,5
      qprocess(m)=-REAL(REAL(qbase(m),real64)/qroots(m),real32)
    END DO
    DO m=1,3
      nprocess(m)=-REAL(REAL(nbase(m),real64)/nroots(m),real32)
    END DO
    bbase=qbase(5)/500.0_real32
    bprocess=-bbase/0.80_real32
    CALL apply_fraction('all 12 distinct breakpoints',qbase,qprocess,nbase,nprocess, &
         bbase,bprocess,fraction_local,feasible_local,status_local,1.0_real32, &
         -1.0_real32/0.95_real32)
    IF (.NOT.feasible_local .OR. status_local/=0 .OR. fraction_local<=0.0_real32) &
         ERROR STOP '12-breakpoint search failed or found no feasible positive step'
    IF (1.0_real32+fraction_local*(-1.0_real32/0.95_real32)<0.0_real32) &
         ERROR STOP '12-breakpoint accepted step violated QV endpoint'
    PRINT '(a,1x,es14.6)', 'CASE all 12 search breakpoints exercised; alpha=',fraction_local
  END SUBROUTINE check_full_breakpoint_capacity

  SUBROUTINE check_group_water_and_heat_ledger()
    REAL(real64), PARAMETER :: factors(3)=[0.25_real64,0.50_real64,0.75_real64]
    REAL(real64) :: group_q(5,3),group_qv(3),group_t(3),before_water,after_water
    REAL(real64) :: qv, qstate(5),temperature,expected_t
    INTEGER :: group
    group_q=0.0_real64; group_qv=0.0_real64; group_t=0.0_real64
    ! NG ice deposition, AUT cloud-to-rain conversion, and G vapor deposition.
    group_q(2,1)=0.00060_real64; group_qv(1)=-0.00060_real64
    group_t(1)=xls_test*0.00060_real64/cpm_test
    group_q(1,2)=-0.00040_real64; group_q(3,2)=0.00040_real64
    group_q(5,3)=0.00020_real64; group_qv(3)=-0.00020_real64
    group_t(3)=xls_test*0.00020_real64/cpm_test
    qv=1.0_real64; qstate=0.0_real64; temperature=273.15_real64
    before_water=qv+SUM(qstate)
    DO group=1,3
      IF (ABS(group_qv(group)+SUM(group_q(:,group)))>1.0e-14_real64) &
           ERROR STOP 'unscaled process water ledger is not closed'
      qv=qv+factors(group)*group_qv(group)
      qstate=qstate+factors(group)*group_q(:,group)
      temperature=temperature+factors(group)*group_t(group)
    END DO
    after_water=qv+SUM(qstate)
    IF (ABS(after_water-before_water)>1.0e-14_real64) &
         ERROR STOP 'independently scaled NG/AUT/G water ledger is not closed'
    expected_t=factors(1)*xls_test*0.00060_real64/cpm_test &
         +factors(3)*xls_test*0.00020_real64/cpm_test
    IF (ABS((temperature-273.15_real64)-expected_t)>1.0e-12_real64) &
         ERROR STOP 'NG/G latent heat scaling does not match source stoichiometry'
    PRINT '(a,1x,es14.6,1x,a,1x,es14.6)', &
         'CASE scaled source water residual=',after_water-before_water, &
         'latent delta T=',temperature-273.15_real64
  END SUBROUTINE check_group_water_and_heat_ledger

  SUBROUTINE check_vapor_option_pair()
    REAL(real32) :: qzero(5),nzero(3),frac
    LOGICAL :: accepted
    INTEGER :: result
    qzero=0.0_real32; nzero=0.0_real32
    CALL kdm6_rain_process_fraction(qzero,qzero,nzero,nzero,0.0_real32,0.0_real32, &
         t0,0.0_real32,.FALSE.,rho,pidnr,qmin,ncmin,qcrmin,dmr,lmin,lmax, &
         rhomin,rhomax,pidnc,dmc,lcmin,lcmax,pidni,dmi,limin,limax, &
         frac,accepted,result,vapor_fixed=0.0_real32)
    IF (accepted .OR. result/=2 .OR. frac/=0.0_real32) &
         ERROR STOP 'unpaired optional vapor arguments did not fail closed'
  END SUBROUTINE check_vapor_option_pair

  SUBROUTINE check_delta_routing(d2,d3,pa,pracs,piacr,praci,psacr,pgacr)
    INTEGER, INTENT(IN) :: d2,d3
    REAL(real64), INTENT(IN) :: pa,pracs,piacr,praci,psacr,pgacr
    REAL(real64) :: delta2,delta3, ledger, qgraupel
    delta2=REAL(d2,real64); delta3=REAL(d3,real64)
    qdelta=0.0_real64
    qdelta(1)=-2.0_real64*pa
    qdelta(2)=-praci
    qdelta(3)=-piacr-psacr-pgacr
    qdelta(4)=piacr*delta3+praci*delta3+psacr*delta2-pracs*(1.0_real64-delta2)+pa
    qdelta(5)=piacr*(1.0_real64-delta3)+praci*(1.0_real64-delta3) &
         +psacr*(1.0_real64-delta2)+pgacr+pracs*(1.0_real64-delta2)+pa
    ledger=SUM(qdelta)
    IF (ABS(ledger)>1.0e-14_real64) ERROR STOP 'delta routing does not conserve total Q'
    bga=pa/denr
    bgr=pracs*(1.0_real64-delta2)/dens
    bgi=piacr*(1.0_real64-delta3)/denr
    bpraci=praci*(1.0_real64-delta3)/deni
    bpsacr=psacr*(1.0_real64-delta2)/denr
    bpgacr=pgacr/denr
    qgraupel=pa+pracs*(1.0_real64-delta2)+piacr*(1.0_real64-delta3) &
         +praci*(1.0_real64-delta3)+psacr*(1.0_real64-delta2)+pgacr
    IF (ABS((denr*bga-pa))>1.0e-14_real64 .OR. &
        ABS((dens*bgr-pracs*(1.0_real64-delta2)))>1.0e-14_real64 .OR. &
        ABS((denr*bgi-piacr*(1.0_real64-delta3)))>1.0e-14_real64 .OR. &
        ABS((deni*bpraci-praci*(1.0_real64-delta3)))>1.0e-14_real64 .OR. &
        ABS((denr*bpsacr-psacr*(1.0_real64-delta2)))>1.0e-14_real64 .OR. &
        ABS((denr*bpgacr-pgacr))>1.0e-14_real64) &
      ERROR STOP 'graupel branch volume disagrees with routed mass'
    IF (ABS(qgraupel-(denr*bga+dens*bgr+denr*bgi+deni*bpraci &
         +denr*bpsacr+denr*bpgacr))>1.0e-14_real64) &
      ERROR STOP 'graupel total source mass/volume ledger mismatch'
    PRINT '(a,2i2,1x,es14.6)', 'DELTA_ROUTING',d2,d3,ledger
  END SUBROUTINE check_delta_routing

  SUBROUTINE check_explicit_ice_transient_policy()
    REAL(real32), PARAMETER :: rho_transient=0.77121818_real32
    REAL(real32), PARAMETER :: qi_capture=1.241258386e-15_real32
    REAL(real32), PARAMETER :: ni_capture=2.341769516e-7_real32
    REAL(real32), PARAMETER :: pidni_k6=1570.79638671875_real32
    REAL(real32), PARAMETER :: lmin_i_k6=9080.0_real32,lmax_i_k6=1820000.0_real32
    REAL(real32) :: qx(5),nx(3),qproc(5),nproc(3),frac,qi_above
    REAL(real64) :: mean_min,mean_max,mean_mid
    LOGICAL :: feasible
    INTEGER :: search_status

    mean_min=REAL(pidni_k6,real64)/REAL(lmax_i_k6,real64)**3
    mean_max=REAL(pidni_k6,real64)/REAL(lmin_i_k6,real64)**3
    mean_mid=(mean_min+mean_max)/2.0_real64

    ! Captured paired base is below qmin but outside the active ice PSD cone.
    qx=0.0_real32; nx=0.0_real32
    qx(2)=qi_capture; nx(2)=ni_capture
    CALL check_actual_state('captured transient defaults strict',qx,nx,.FALSE.,.FALSE., &
         rho_transient,pidni_k6,lmin_i_k6,lmax_i_k6)
    CALL check_actual_state('captured transient explicit opt-in',qx,nx,.TRUE.,.TRUE., &
         rho_transient,pidni_k6,lmin_i_k6,lmax_i_k6)

    ! The inclusive transient edge is the greatest R32 below 1.e-14. At the
    ! native 1.e-14 cutoff, active-ice PSD bounds apply even with the option.
    qx(2)=PR85_ICE_NATIVE_INACTIVE_MAX
    CALL check_actual_state('ice exactly native inactive maximum',qx,nx,.TRUE.,.TRUE., &
         rho_transient,pidni_k6,lmin_i_k6,lmax_i_k6)
    qx(2)=1.0e-14_real32
    CALL check_actual_state('ice at native activation cutoff remains strict',qx,nx,.FALSE.,.TRUE., &
         rho_transient,pidni_k6,lmin_i_k6,lmax_i_k6)

    ! Ordinary active in-cone ice stays valid with the default strict contract.
    qx=0.0_real32; nx=0.0_real32
    qx(2)=1.0e-4_real32
    nx(2)=REAL(REAL(rho_transient,real64)*REAL(qx(2),real64)/mean_mid,real32)
    CALL check_actual_state('active ice in cone default',qx,nx,.TRUE.,.FALSE., &
         rho_transient,pidni_k6,lmin_i_k6,lmax_i_k6)

    ! The explicit exception does not permit either unpaired ice endpoint.
    qx=0.0_real32; nx=0.0_real32
    qx(2)=0.5_real32*qmin
    CALL check_actual_state('ice mass only rejected',qx,nx,.FALSE.,.TRUE., &
         rho_transient,pidni_k6,lmin_i_k6,lmax_i_k6)
    qx(2)=0.0_real32; nx(2)=1.0e-20_real32
    CALL check_actual_state('ice number only rejected',qx,nx,.FALSE.,.TRUE., &
         rho_transient,pidni_k6,lmin_i_k6,lmax_i_k6)

    ! The exception is ice-only: invalid cloud, rain, and graupel states remain rejected.
    qx=0.0_real32; nx=0.0_real32
    qx(2)=qi_capture; nx(2)=ni_capture
    qx(1)=1.0e-4_real32; nx(1)=0.1_real32
    CALL check_actual_state('transient ice does not relax cloud cone',qx,nx,.FALSE.,.TRUE., &
         rho_transient,pidni_k6,lmin_i_k6,lmax_i_k6)
    qx=0.0_real32; nx=0.0_real32
    qx(2)=qi_capture; nx(2)=ni_capture
    qx(3)=1.0e-4_real32; nx(3)=0.1_real32
    CALL check_actual_state('transient ice does not relax rain cone',qx,nx,.FALSE.,.TRUE., &
         rho_transient,pidni_k6,lmin_i_k6,lmax_i_k6)
    qx=0.0_real32; nx=0.0_real32
    qx(2)=qi_capture; nx(2)=ni_capture
    qx(5)=1.0e-4_real32
    CALL check_actual_state('transient ice does not relax graupel density',qx,nx,.FALSE.,.TRUE., &
         rho_transient,pidni_k6,lmin_i_k6,lmax_i_k6,graupel_ratio=50.0_real32)

    ! The captured base with synthetic zero increments is an identity proposal.
    ! It is accepted only by the explicit native-inactive contract; this does
    ! not claim the native PFRZ packet had these zero increments.
    qx=0.0_real32; nx=0.0_real32
    qx(2)=qi_capture; nx(2)=ni_capture
    qproc=0.0_real32; nproc=0.0_real32
    CALL kdm6_rain_process_fraction(qx,qproc,nx,nproc,0.0_real32,0.0_real32, &
         t0,0.0_real32,.FALSE.,rho_transient,1.0_real32,qmin,ncmin,qcrmin,3.0_real32, &
         1.0_real32,2.0_real32,100.0_real32,900.0_real32,1.0_real32,3.0_real32, &
         1.0_real32,2.0_real32,pidni_k6,3.0_real32,lmin_i_k6,lmax_i_k6, &
         frac,feasible,search_status,ice_transient_mass_limit=PR85_ICE_NATIVE_INACTIVE_MAX)
    IF (.NOT.feasible .OR. search_status/=0 .OR. frac/=1.0_real32) &
         ERROR STOP 'explicit transient zero/noop packet was not accepted'
    IF (ANY(qx+frac*qproc/=qx) .OR. ANY(nx+frac*nproc/=nx)) &
         ERROR STOP 'zero/noop packet changed stored state'
    CALL kdm6_rain_process_fraction(qx,qproc,nx,nproc,0.0_real32,0.0_real32, &
         t0,0.0_real32,.FALSE.,rho_transient,1.0_real32,qmin,ncmin,qcrmin,3.0_real32, &
         1.0_real32,2.0_real32,100.0_real32,900.0_real32,1.0_real32,3.0_real32, &
         1.0_real32,2.0_real32,pidni_k6,3.0_real32,lmin_i_k6,lmax_i_k6, &
         frac,feasible,search_status)
    IF (feasible .OR. frac/=0.0_real32) &
         ERROR STOP 'default strict no-op accepted transient out-of-cone ice'

    ! A synthetic packet crossing the native inactive boundary is capped at
    ! the inclusive transient edge; the next stored value uses active PSD.
    qx=0.0_real32; nx=0.0_real32
    qx(2)=0.5_real32*PR85_ICE_NATIVE_INACTIVE_MAX; nx(2)=ni_capture
    qproc=0.0_real32; nproc=0.0_real32
    qproc(2)=PR85_ICE_NATIVE_INACTIVE_MAX
    CALL kdm6_rain_process_fraction(qx,qproc,nx,nproc,0.0_real32,0.0_real32, &
         t0,0.0_real32,.FALSE.,rho_transient,1.0_real32,qmin,ncmin,qcrmin,3.0_real32, &
         1.0_real32,2.0_real32,100.0_real32,900.0_real32,1.0_real32,3.0_real32, &
         1.0_real32,2.0_real32,pidni_k6,3.0_real32,lmin_i_k6,lmax_i_k6, &
         frac,feasible,search_status,ice_transient_mass_limit=PR85_ICE_NATIVE_INACTIVE_MAX)
    IF (.NOT.feasible .OR. search_status/=0 .OR. frac<=0.0_real32) &
         ERROR STOP 'valid threshold-capped transient step was not found'
    qi_above=qx(2)+frac*qproc(2)
    IF (qi_above>PR85_ICE_NATIVE_INACTIVE_MAX) &
      ERROR STOP 'transient trial crossed native inactive limit'
    qx(2)=NEAREST(PR85_ICE_NATIVE_INACTIVE_MAX,1.0_real32)
    CALL check_actual_state('first representable active value strict',qx,nx,.FALSE.,.TRUE., &
         rho_transient,pidni_k6,lmin_i_k6,lmax_i_k6)
    PRINT '(a,1x,es14.6,1x,a,1x,es14.6)', &
         'TRANSIENT_CAPTURE accepted QI=',qi_capture,'capped_trial_QI=',qi_above
    PRINT '(a)', 'CASE explicit native-inactive ice is bounded below 1.e-14; other PSD cones and pairing stay strict'
  END SUBROUTINE check_explicit_ice_transient_policy

  SUBROUTINE check_actual_state(label,qx,nx,want,transient,rho_value,pidni_value,li_min,li_max,graupel_ratio)
    CHARACTER(len=*), INTENT(IN) :: label
    REAL(real32), INTENT(IN) :: qx(5),nx(3),rho_value,pidni_value,li_min,li_max
    LOGICAL, INTENT(IN) :: want,transient
    REAL(real32), INTENT(IN), OPTIONAL :: graupel_ratio
    REAL(real32) :: bvalue
    LOGICAL :: got
    bvalue=0.0_real32
    IF (PRESENT(graupel_ratio)) bvalue=qx(5)/graupel_ratio
    IF (transient) THEN
      CALL kdm6_rain_process_state_valid(qx,nx,bvalue,t0,rho_value,1.0_real32,qmin,ncmin, &
           qcrmin,3.0_real32,1.0_real32,2.0_real32,100.0_real32,900.0_real32, &
           1.0_real32,3.0_real32,1.0_real32,2.0_real32,pidni_value,3.0_real32, &
         li_min,li_max,got,ice_transient_mass_limit=PR85_ICE_NATIVE_INACTIVE_MAX)
    ELSE
      CALL kdm6_rain_process_state_valid(qx,nx,bvalue,t0,rho_value,1.0_real32,qmin,ncmin, &
           qcrmin,3.0_real32,1.0_real32,2.0_real32,100.0_real32,900.0_real32, &
           1.0_real32,3.0_real32,1.0_real32,2.0_real32,pidni_value,3.0_real32, &
           li_min,li_max,got)
    ENDIF
    IF (got.NEQV.want) THEN
      PRINT *, 'transient predicate mismatch: ',TRIM(label),' expected=',want,' got=',got
      ERROR STOP 'explicit transient ice state result mismatch'
    ENDIF
  END SUBROUTINE check_actual_state

END PROGRAM test_pr85_kdm6_cold_process
