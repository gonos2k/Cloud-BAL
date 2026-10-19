module replay
 use iso_fortran_env, only: int32
 use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
 implicit none
 real, parameter :: PR85_ICE_NATIVE_INACTIVE_MAX = nearest(1.e-14,-1.0)
contains

    pure logical function kdm6_progb_density_pair_valid(q,b,rho_min,rho_max)
      real, intent(in) :: q,b,rho_min,rho_max
      real(kind=8) :: density

      kdm6_progb_density_pair_valid=.false.
      if (.not.all(ieee_is_finite([q,b,rho_min,rho_max]))) return
      if (rho_min.le.0.0 .or. rho_max.lt.rho_min) return
      if (q.eq.0.0 .and. b.eq.0.0) then
        kdm6_progb_density_pair_valid=.true.
        return
      endif
      if (q.le.0.0 .or. b.le.0.0) return
      density=real(q,8)/real(b,8)
      kdm6_progb_density_pair_valid=ieee_is_finite(density) .and. &
           density.ge.real(rho_min,8) .and. density.le.real(rho_max,8)
    end function kdm6_progb_density_pair_valid


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
        if (.not.kdm6_progb_density_pair_valid(q(5),bg,rho_min,rho_max)) then
          if (present(failure_reason)) failure_reason=9
          return
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
        if (.not.kdm6_progb_density_pair_valid(q(5),bg,rho_min,rho_max)) then
          if (present(failure_reason)) failure_reason=9
          return
        endif
      valid=.true.
      if (present(failure_reason)) failure_reason=0
    end subroutine kdm6_rain_process_state_valid

end module replay
program main
 use iso_fortran_env, only: int32
 use replay
 implicit none
 real :: q(5),n(3),bg,temp,rho
 logical :: ok
 integer :: reason
 q=[transfer(int(z'36CCE783',int32),0.0),transfer(int(z'328B8E77',int32),0.0), &
    transfer(int(z'2EA445FC',int32),0.0),transfer(int(z'33A266F0',int32),0.0), &
    transfer(int(z'300669B5',int32),0.0)]
 n=[transfer(int(z'4B847172',int32),0.0),transfer(int(z'46897685',int32),0.0), &
    transfer(int(z'3E2702A7',int32),0.0)]
 bg=transfer(int(z'2B19B507',int32),0.0)
 temp=transfer(int(z'4384C1BD',int32),0.0)
 rho=transfer(int(z'3F23D06F',int32),0.0)
 call kdm6_rain_process_state_valid(q,n,bg,temp,rho,12566.37109375,1.0000000036274937e-15,10., &
    9.9999997171806854e-10,3., &
    961.,35000.,100.,900.,523.5988,3.,12000.,500000.,1570.796,3.,9080.,1820000., &
    ok,failure_reason=reason,ice_transient_mass_limit=PR85_ICE_NATIVE_INACTIVE_MAX)
 print *, 'STATE_VALID_REASON',ok,reason
 print *, 'RAIN_N_OVER_MAX',real(n(3),8)/(real(rho,8)*35000.d0**3/12566.37109375d0*real(q(3),8))
end program main
