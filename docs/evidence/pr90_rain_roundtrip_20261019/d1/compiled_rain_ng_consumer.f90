pure subroutine kdm6_rain_ng_pair_valid(q,n,rain_min,rain_max, &
         allow_argument_present,allow_number_at_zero,valid,failure_reason)
      implicit none
      real, intent(in) :: q,n
      real(kind=8), intent(in) :: rain_min,rain_max
      logical, intent(in) :: allow_argument_present,allow_number_at_zero
      logical, intent(out) :: valid
      integer, intent(out) :: failure_reason
      valid=.false.
      failure_reason=0
      if (.not.ieee_is_finite(q) .or. .not.ieee_is_finite(n) .or. &
          .not.ieee_is_finite(rain_min) .or. .not.ieee_is_finite(rain_max)) then
        failure_reason=1
        return
      endif
      if (q.lt.0.0 .or. n.lt.0.0) then
        failure_reason=2
        return
      endif
      if (q.eq.0.0) then
        if (n.ne.0.0) then
          if (.not.allow_argument_present) then
            failure_reason=3
            return
          endif
          if (.not.allow_number_at_zero) then
            failure_reason=3
            return
          endif
        endif
      elseif (q.le.0.0 .or. n.le.0.0) then
        failure_reason=3
        return
      elseif (real(n,8).lt.rain_min*q .or. real(n,8).gt.rain_max*q) then
        failure_reason=6
        return
      endif
      valid=.true.
    end subroutine kdm6_rain_ng_pair_valid
