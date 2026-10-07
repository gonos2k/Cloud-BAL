module pr70_helper
contains
subroutine kdm6_mass_volume_rate(mass_rate,density,volume_rate,feasible)
      use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
      implicit none
      real, intent(in) :: mass_rate,density
      real, intent(out) :: volume_rate
      logical, intent(out) :: feasible

      volume_rate=0.0
      feasible=.false.
      if (.not.all(ieee_is_finite([mass_rate,density]))) return
      if (mass_rate.eq.0.0) then
        feasible=.true.
        return
      endif
      if (density.le.0.0) return
      volume_rate=mass_rate/density
      feasible=ieee_is_finite(volume_rate)
      if (.not.feasible) volume_rate=0.0
    end subroutine kdm6_mass_volume_rate

subroutine kdm6_rain_process_fraction(q_fixed,q_process,n_fixed,n_process, &
         bg_fixed,bg_process,t_fixed,t_process,rain_cleanup_pending,density,pidnr,qmin,ncmin, &
         qcrmin,dmr,lambda_min,lambda_max,rho_min,rho_max,pidnc,dmc, &
         lambda_c_min,lambda_c_max,pidni,dmi,lambda_i_min,lambda_i_max, &
         fraction,feasible,search_status)
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
      ! 0=FEASIBLE, 1=NO_FEASIBLE_STEP, 2=SEARCH_FAILURE.
      integer, parameter :: feasible_status=0,no_step_status=1,search_failure_status=2
      real(kind=8) :: breaks(16),lower,upper,alpha,midpoint,best
      real(kind=8) :: rain_min,rain_max,cloud_min,cloud_max,ice_min,ice_max
      real(kind=8) :: q0(5),dq(5),n0(3),dn(3),bg0,dbg
      real :: q_trial(5),n_trial(3),bg_trial,t_trial,trial
      integer :: count_breaks,i,j,walks
      logical :: interval_valid,step_valid,search_failed

      feasible=.false.
      fraction=0.0
      search_status=search_failure_status
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
        if (i.le.2) then
          call add_breakpoint(q0(i),dq(i),real(qmin,8))
        else
          call add_breakpoint(q0(i),dq(i),real(qcrmin,8))
        endif
      enddo
      do i=1,3
        call add_breakpoint(n0(i),dn(i),0.0d0)
      enddo
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
        trial=real(lower)
        alpha=real(trial,8)
        if (trial.gt.0.0 .and. alpha.ge.lower .and. alpha.le.upper) then
          call validate_trial(trial,step_valid)
          if (step_valid) best=max(best,real(trial,8))
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
            exit
          endif
          trial=nearest(trial,-1.0)
          walks=walks+1
        enddo
      enddo

      if (search_failed) then
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
        if (.not.valid_interval) return

        if (qm(3).gt.real(qcrmin,8)) then
          call clip(q0(3)-real(qcrmin,8),dq(3),lo,hi,valid_interval)
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
        cloud_active=qm(1).gt.real(qmin,8) .and. nm(1).gt.0.0d0
        if (cloud_active) then
          call clip(q0(1)-real(qmin,8),dq(1),lo,hi,valid_interval)
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
        ice_active=qm(2).gt.real(qmin,8) .and. nm(2).gt.0.0d0
        if (ice_active) then
          call clip(q0(2)-real(qmin,8),dq(2),lo,hi,valid_interval)
          call clip(n0(2),dn(2),lo,hi,valid_interval)
          call clip(n0(2)-ice_min*q0(2),dn(2)-ice_min*dq(2),lo,hi,valid_interval)
          call clip(ice_max*q0(2)-n0(2),ice_max*dq(2)-dn(2),lo,hi,valid_interval)
        elseif (qm(2).eq.0.0d0 .and. nm(2).eq.0.0d0) then
          call clip(q0(2),dq(2),lo,hi,valid_interval)
          call clip(-q0(2),-dq(2),lo,hi,valid_interval)
          call clip(n0(2),dn(2),lo,hi,valid_interval)
          call clip(-n0(2),-dn(2),lo,hi,valid_interval)
        else
          valid_interval=.false.
        endif
        do m=4,5
          if (qm(m).gt.real(qcrmin,8)) then
            call clip(q0(m)-real(qcrmin,8),dq(m),lo,hi,valid_interval)
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
        is_valid=all(ieee_is_finite([q_trial,n_trial,bg_trial,t_trial]))
        if (.not.is_valid) return
        if (any(q_trial.lt.0.0) .or. any(n_trial.lt.0.0) .or. bg_trial.lt.0.0) then
          is_valid=.false.; return
        endif
        call kdm6_rain_process_state_valid(q_trial,n_trial,bg_trial,density,pidnr, &
             qmin,ncmin,qcrmin,dmr,lambda_min,lambda_max,rho_min,rho_max, &
             pidnc,dmc,lambda_c_min,lambda_c_max,pidni,dmi,lambda_i_min, &
             lambda_i_max,is_valid,rain_cleanup_pending)
      end subroutine validate_trial
    end subroutine kdm6_rain_process_fraction

subroutine kdm6_rain_process_state_valid(q,n,bg,density,pidnr,qmin,ncmin, &
         qcrmin,dmr,lambda_min,lambda_max,rho_min,rho_max,pidnc,dmc, &
         lambda_c_min,lambda_c_max,pidni,dmi,lambda_i_min,lambda_i_max,valid, &
         allow_rain_number_at_zero)
      use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
      implicit none
      real, intent(in) :: q(5),n(3),bg,density,pidnr,qmin,ncmin,qcrmin,dmr
      real, intent(in) :: lambda_min,lambda_max,rho_min,rho_max,pidnc,dmc
      real, intent(in) :: lambda_c_min,lambda_c_max,pidni,dmi,lambda_i_min,lambda_i_max
      logical, intent(out) :: valid
      logical, intent(in), optional :: allow_rain_number_at_zero
      real(kind=8) :: rain_min,rain_max,cloud_min,cloud_max,ice_min,ice_max

      valid=.false.
      if (.not.all(ieee_is_finite([q,n,bg,density,pidnr,qmin,ncmin,qcrmin,dmr, &
          lambda_min,lambda_max,rho_min,rho_max,pidnc,dmc,lambda_c_min, &
          lambda_c_max,pidni,dmi,lambda_i_min,lambda_i_max]))) return
      if (density.le.0.0 .or. pidnr.le.0.0 .or. pidnc.le.0.0 .or. pidni.le.0.0 .or. &
          qmin.lt.0.0 .or. qcrmin.lt.0.0 .or. lambda_min.le.0.0 .or. &
          lambda_max.lt.lambda_min .or. lambda_c_min.le.0.0 .or. &
          lambda_c_max.lt.lambda_c_min .or. lambda_i_min.le.0.0 .or. &
          lambda_i_max.lt.lambda_i_min .or. rho_min.le.0.0 .or. rho_max.lt.rho_min .or. &
          dmr.le.0.0 .or. dmc.le.0.0 .or. dmi.le.0.0 .or. &
          dmr.gt.8.0 .or. dmc.gt.8.0 .or. dmi.gt.8.0) return
      if (any(q.lt.0.0) .or. any(n.lt.0.0) .or. bg.lt.0.0) return
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
      elseif (q(1).le.qmin .or. n(1).le.0.0) then
        return
      elseif (real(n(1),8).lt.cloud_min*q(1) .or. real(n(1),8).gt.cloud_max*q(1)) then
        return
      endif
      if (q(2).eq.0.0) then
        if (n(2).ne.0.0) return
      elseif (q(2).le.qmin .or. n(2).le.0.0) then
        return
      elseif (real(n(2),8).lt.ice_min*q(2) .or. real(n(2),8).gt.ice_max*q(2)) then
        return
      endif
      if (q(3).eq.0.0) then
        if (n(3).ne.0.0) then
          if (.not.present(allow_rain_number_at_zero)) return
          if (.not.allow_rain_number_at_zero) return
        endif
      elseif (q(3).le.qcrmin .or. n(3).le.0.0) then
        return
      elseif (real(n(3),8).lt.rain_min*q(3) .or. real(n(3),8).gt.rain_max*q(3)) then
        return
      endif
      if ((q(4).ne.0.0 .and. q(4).le.qcrmin) .or. &
          (q(5).ne.0.0 .and. q(5).le.qcrmin)) return
      if (real(bg,8).lt.real(q(5),8)/real(rho_max,8) .or. &
          real(bg,8).gt.real(q(5),8)/real(rho_min,8)) return
      valid=.true.
    end subroutine kdm6_rain_process_state_valid

subroutine constrain_process_margin(margin_initial,margin_process, &
         alpha_min,alpha_max,feasible)
      implicit none
      real, intent(in) :: margin_initial,margin_process
      real, intent(inout) :: alpha_min,alpha_max
      logical, intent(inout) :: feasible
      real :: boundary

      if (.not.feasible) return
      if (margin_process.eq.0.0) then
        if (margin_initial.lt.0.0) feasible=.false.
      elseif (margin_process.gt.0.0) then
        boundary=-margin_initial/margin_process
        alpha_min=max(alpha_min,boundary)
      else
        boundary=-margin_initial/margin_process
        alpha_max=min(alpha_max,boundary)
      endif
    end subroutine constrain_process_margin

real function kdm6_shared_pair_fraction(mass_rate_start,mass_rate_limited, &
         number_rate_start,number_rate_limited)
      use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
      implicit none
      real, intent(in) :: mass_rate_start,mass_rate_limited
      real, intent(in) :: number_rate_start,number_rate_limited
      kdm6_shared_pair_fraction=1.0
      if (.not.all(ieee_is_finite([mass_rate_start,mass_rate_limited, &
          number_rate_start,number_rate_limited]))) then
        error stop 'KDM6 paired process limiter received a nonfinite rate'
      endif
      if (mass_rate_start.lt.0.0 .or. mass_rate_limited.lt.0.0 .or. &
          number_rate_start.lt.0.0 .or. number_rate_limited.lt.0.0 .or. &
          mass_rate_limited.gt.mass_rate_start .or. &
          number_rate_limited.gt.number_rate_start) then
        error stop 'KDM6 paired process limiter changed a nonnegative rate inconsistently'
      endif
      if (mass_rate_start.gt.0.0) then
        kdm6_shared_pair_fraction=min(kdm6_shared_pair_fraction, &
             mass_rate_limited/mass_rate_start)
      endif
      if (number_rate_start.gt.0.0) then
        kdm6_shared_pair_fraction=min(kdm6_shared_pair_fraction, &
             number_rate_limited/number_rate_start)
      endif
    end function kdm6_shared_pair_fraction
end module pr70_helper
