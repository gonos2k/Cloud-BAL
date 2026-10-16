module pr87_ice_sublimation_helpers
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  implicit none
  real, parameter :: PR85_ICE_NATIVE_INACTIVE_MAX=nearest(1.e-14,-1.0)
contains
    subroutine kdm6_rain_process_fraction(q_fixed,q_process,n_fixed,n_process, &
         bg_fixed,bg_process,t_fixed,t_process,rain_cleanup_pending,density,pidnr,qmin,ncmin, &
         qcrmin,dmr,lambda_min,lambda_max,rho_min,rho_max,pidnc,dmc, &
         lambda_c_min,lambda_c_max,pidni,dmi,lambda_i_min,lambda_i_max, &
         fraction,feasible,search_status,vapor_fixed,vapor_process,consumer_pair_only, &
         ice_transient_mass_limit,ice_sublimation_pending)
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
      logical, intent(in), optional :: ice_sublimation_pending
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
      logical :: pair_only,ice_sublimation_pending_value

      feasible=.false.
      fraction=0.0
      search_status=search_failure_status
      pair_only=.false.
      if (present(consumer_pair_only)) pair_only=consumer_pair_only
      ice_sublimation_pending_value=.false.
      if (present(ice_sublimation_pending)) &
        ice_sublimation_pending_value=ice_sublimation_pending
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
      call add_breakpoint(q0(5),dq(5),real(qcrmin,8))
      call add_breakpoint(bg0,dbg,real(1.0e-15,8))
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
        if (.not.pair_only) then
          if (no_storable_rain_interval(lower,upper)) cycle
        endif
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

      logical function no_storable_rain_interval(lo,hi)
        real(kind=8), intent(in) :: lo,hi
        real :: alpha_first,alpha_last,q_first,q_last,n_first,n_last
        real(kind=8) :: q_min_store,q_max_store,n_min_store,n_max_store
        real(kind=8) :: lower_number,upper_number

        no_storable_rain_interval=.false.
        if (.not.all(ieee_is_finite([lo,hi]))) return
        if (lo.gt.hi) return
        alpha_first=real(lo)
        if (.not.ieee_is_finite(alpha_first)) return
        if (real(alpha_first,8).lt.lo) alpha_first=nearest(alpha_first,1.0)
        alpha_last=real(hi)
        if (.not.ieee_is_finite(alpha_last)) return
        if (real(alpha_last,8).gt.hi) alpha_last=nearest(alpha_last,-1.0)
        if (.not.all(ieee_is_finite([alpha_first,alpha_last]))) return
        if (real(alpha_first,8).gt.hi .or. real(alpha_last,8).lt.lo .or. &
            alpha_first.gt.alpha_last) then
          no_storable_rain_interval=.true.
          return
        endif

        ! Rounded affine endpoint extrema enclose all stored REAL32 Q/N here.
        ! Requiring positive Q excludes exact absence from this rejection proof.
        q_first=q_fixed(3)+alpha_first*q_process(3)
        q_last=q_fixed(3)+alpha_last*q_process(3)
        n_first=n_fixed(3)+alpha_first*n_process(3)
        n_last=n_fixed(3)+alpha_last*n_process(3)
        if (.not.all(ieee_is_finite([q_first,q_last,n_first,n_last]))) return
        q_min_store=real(min(q_first,q_last),8)
        q_max_store=real(max(q_first,q_last),8)
        n_min_store=real(min(n_first,n_last),8)
        n_max_store=real(max(n_first,n_last),8)
        if (.not.all(ieee_is_finite([q_min_store,q_max_store,n_min_store,n_max_store]))) return
        if (q_min_store.le.0.0d0) return
        lower_number=rain_min*q_min_store
        upper_number=rain_max*q_max_store
        if (.not.all(ieee_is_finite([lower_number,upper_number]))) return
        no_storable_rain_interval=n_min_store.gt.upper_number .or. &
                                  n_max_store.lt.lower_number
      end function no_storable_rain_interval

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
            elseif (m.eq.2 .and. qm(m).eq.0.0d0 .and. nm(m).gt.0.0d0 .and. &
                    ice_sublimation_pending_value) then
              call clip(q0(m),dq(m),lo,hi,valid_interval)
              call clip(-q0(m),-dq(m),lo,hi,valid_interval)
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
        elseif (qm(2).eq.0.0d0 .and. nm(2).gt.0.0d0 .and. &
                ice_sublimation_pending_value) then
          call clip(q0(2),dq(2),lo,hi,valid_interval)
          call clip(-q0(2),-dq(2),lo,hi,valid_interval)
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
        if (qm(5).gt.0.0d0 .and. bm.gt.0.0d0 .and. &
            qm(5).le.real(qcrmin,8) .and. bm.le.real(1.0e-15,8)) &
          valid_interval=.false.
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
             lambda_i_max,is_valid,rain_cleanup_pending,pair_only, &
             ice_transient_mass_limit, &
             ice_sublimation_pending=ice_sublimation_pending_value)
      end subroutine validate_trial
    end subroutine kdm6_rain_process_fraction
subroutine kdm6_rain_process_state_valid(q,n,bg,temperature,density,pidnr,qmin,ncmin, &
         qcrmin,dmr,lambda_min,lambda_max,rho_min,rho_max,pidnc,dmc, &
         lambda_c_min,lambda_c_max,pidni,dmi,lambda_i_min,lambda_i_max,valid, &
         allow_rain_number_at_zero,consumer_pair_only,ice_transient_mass_limit, &
         failure_reason,ice_sublimation_pending)
      use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
      implicit none
      real, intent(in) :: q(5),n(3),bg,temperature,density,pidnr,qmin,ncmin,qcrmin,dmr
      real, intent(in) :: lambda_min,lambda_max,rho_min,rho_max,pidnc,dmc
      real, intent(in) :: lambda_c_min,lambda_c_max,pidni,dmi,lambda_i_min,lambda_i_max
      logical, intent(out) :: valid
      logical, intent(in), optional :: allow_rain_number_at_zero
      logical, intent(in), optional :: consumer_pair_only
      real, intent(in), optional :: ice_transient_mass_limit
      integer, intent(out), optional :: failure_reason
      logical, intent(in), optional :: ice_sublimation_pending
      real(kind=8) :: rain_min,rain_max,cloud_min,cloud_max,ice_min,ice_max,ice_transient_limit
      logical :: pair_only,ice_pending

      valid=.false.
      if (present(failure_reason)) failure_reason=0
      if (.not.all(ieee_is_finite([q,n,bg,temperature,density,pidnr,qmin,ncmin,qcrmin,dmr, &
          lambda_min,lambda_max,rho_min,rho_max,pidnc,dmc,lambda_c_min, &
          lambda_c_max,pidni,dmi,lambda_i_min,lambda_i_max]))) then
        if (present(failure_reason)) failure_reason=1
        return
      endif
      if (density.le.0.0 .or. pidnr.le.0.0 .or. pidnc.le.0.0 .or. pidni.le.0.0 .or. &
          qmin.lt.0.0 .or. qcrmin.lt.0.0 .or. lambda_min.le.0.0 .or. &
          lambda_max.lt.lambda_min .or. lambda_c_min.le.0.0 .or. &
          lambda_c_max.lt.lambda_c_min .or. lambda_i_min.le.0.0 .or. &
          lambda_i_max.lt.lambda_i_min .or. rho_min.le.0.0 .or. rho_max.lt.rho_min .or. &
          dmr.le.0.0 .or. dmc.le.0.0 .or. dmi.le.0.0 .or. &
          dmr.gt.8.0 .or. dmc.gt.8.0 .or. dmi.gt.8.0) then
        if (present(failure_reason)) failure_reason=1
        return
      endif
      ice_transient_limit=0.0d0
      if (present(ice_transient_mass_limit)) then
        if (.not.ieee_is_finite(ice_transient_mass_limit) .or. &
            ice_transient_mass_limit.lt.0.0 .or. ice_transient_mass_limit.gt.PR85_ICE_NATIVE_INACTIVE_MAX) then
          if (present(failure_reason)) failure_reason=1
          return
        endif
        ice_transient_limit=real(ice_transient_mass_limit,8)
      endif
      if (temperature.le.0.0) then
        if (present(failure_reason)) failure_reason=8
        return
      endif
      if (any(q.lt.0.0) .or. any(n.lt.0.0) .or. bg.lt.0.0) then
        if (present(failure_reason)) failure_reason=2
        return
      endif
      pair_only=.false.
      if (present(consumer_pair_only)) pair_only=consumer_pair_only
      ice_pending=.false.
      if (present(ice_sublimation_pending)) ice_pending=ice_sublimation_pending
      if (pair_only) then
        if (q(1).eq.0.0) then
          if (n(1).ne.0.0) then
            if (present(failure_reason)) failure_reason=3
            return
          endif
        elseif (n(1).le.0.0) then
          if (present(failure_reason)) failure_reason=3
          return
        endif
        if (q(2).eq.0.0) then
          if (n(2).ne.0.0 .and. .not.ice_pending) then
            if (present(failure_reason)) failure_reason=3
            return
          endif
        elseif (n(2).le.0.0) then
          if (present(failure_reason)) failure_reason=3
          return
        endif
        if (q(3).eq.0.0) then
          if (n(3).ne.0.0) then
            if (.not.present(allow_rain_number_at_zero)) then
              if (present(failure_reason)) failure_reason=3
              return
            endif
            if (.not.allow_rain_number_at_zero) then
              if (present(failure_reason)) failure_reason=3
              return
            endif
          endif
        elseif (n(3).le.0.0) then
          if (present(failure_reason)) failure_reason=3
          return
        endif
        if (q(5).eq.0.0) then
          if (bg.ne.0.0) then
            if (present(failure_reason)) failure_reason=3
            return
          endif
        else
          if (bg.le.0.0) then
            if (present(failure_reason)) failure_reason=9
            return
          endif
          if (real(q(5),8)/real(bg,8).lt.real(rho_min,8) .or. &
              real(q(5),8)/real(bg,8).gt.real(rho_max,8)) then
            if (present(failure_reason)) failure_reason=9
            return
          endif
          if (q(5).le.qcrmin .and. bg.le.1.0e-15) then
            if (present(failure_reason)) failure_reason=4
            return
          endif
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
      if (.not.all(ieee_is_finite([rain_min,rain_max,cloud_min,cloud_max,ice_min,ice_max]))) then
        if (present(failure_reason)) failure_reason=1
        return
      endif
      if (max(rain_max,cloud_max,ice_max).gt.real(huge(0.0),8)) then
        if (present(failure_reason)) failure_reason=1
        return
      endif
      if (q(1).eq.0.0) then
        if (n(1).ne.0.0) then
          if (present(failure_reason)) failure_reason=3
          return
        endif
      elseif (q(1).le.0.0 .or. n(1).le.0.0) then
        if (present(failure_reason)) failure_reason=3
        return
      elseif (real(n(1),8).lt.cloud_min*q(1) .or. real(n(1),8).gt.cloud_max*q(1)) then
        if (present(failure_reason)) failure_reason=5
        return
      endif
      if (q(2).eq.0.0) then
        if (n(2).ne.0.0 .and. .not.ice_pending) then
          if (present(failure_reason)) failure_reason=3
          return
        endif
      elseif (q(2).le.0.0 .or. n(2).le.0.0) then
        if (present(failure_reason)) failure_reason=3
        return
      elseif (q(2).gt.ice_transient_limit) then
        if (real(n(2),8).lt.ice_min*q(2) .or. real(n(2),8).gt.ice_max*q(2)) then
          if (present(failure_reason)) failure_reason=7
          return
        endif
      endif
      if (q(3).eq.0.0) then
        if (n(3).ne.0.0) then
          if (.not.present(allow_rain_number_at_zero)) then
              if (present(failure_reason)) failure_reason=3
              return
            endif
          if (.not.allow_rain_number_at_zero) then
            if (present(failure_reason)) failure_reason=3
            return
          endif
        endif
      elseif (q(3).le.0.0 .or. n(3).le.0.0) then
        if (present(failure_reason)) failure_reason=3
        return
      elseif (real(n(3),8).lt.rain_min*q(3) .or. real(n(3),8).gt.rain_max*q(3)) then
        if (present(failure_reason)) failure_reason=6
        return
      endif
      if (q(4).lt.0.0 .or. q(5).lt.0.0) then
        if (present(failure_reason)) failure_reason=2
        return
      endif
      if (q(5).gt.0.0 .or. bg.gt.0.0) then
        if (q(5).le.0.0 .or. bg.le.0.0) then
          if (present(failure_reason)) failure_reason=9
          return
        endif
        if (real(q(5),8)/real(bg,8).lt.real(rho_min,8) .or. &
            real(q(5),8)/real(bg,8).gt.real(rho_max,8)) then
          if (present(failure_reason)) failure_reason=9
          return
        endif
        if (q(5).le.qcrmin .and. bg.le.real(1.0e-15,8)) then
          if (present(failure_reason)) failure_reason=4
          return
        endif
      endif
      valid=.true.
      if (present(failure_reason)) failure_reason=0
    end subroutine kdm6_rain_process_state_valid
end module pr87_ice_sublimation_helpers
