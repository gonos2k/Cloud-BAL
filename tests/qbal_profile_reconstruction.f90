! Bounded fixed-knot profile fusion research kernel.
! This helper has no physical or operational authority.
module qbal_profile_reconstruction
  use iso_fortran_env, only: real64
  use ieee_arithmetic, only: ieee_is_finite, ieee_value, ieee_quiet_nan
  implicit none
  private
  public :: fit_profile_sample
contains
  ! Fuse one scalar observation with a piecewise-linear profile.  The supplied
  ! variance is diagonal in knot space; no covariance or variance is inferred.
  ! A sample must lie in the finite knot domain, so this routine never
  ! extrapolates.  Failed calls return NaN outputs and ok=.false.
  subroutine fit_profile_sample(p,wind,variance,p_sample,wind_sample, &
      sample_variance,fitted,innovation,ok)
    real(real64), intent(in) :: p(:),wind(:),variance(:)
    real(real64), intent(in) :: p_sample,wind_sample,sample_variance
    real(real64), intent(out) :: fitted(:),innovation
    logical, intent(out) :: ok
    real(real64) :: nan,a(size(p)),scaled_variance(size(p))
    real(real64) :: pred,scale,denominator,weight
    real(real64) :: gain(size(p))
    integer :: n,k,interval

    nan=ieee_value(0._real64,ieee_quiet_nan)
    fitted=nan
    innovation=nan
    ok=.false.
    n=size(p)
    if (size(fitted)/=n .or. n<2) return
    if (size(wind)/=n .or. size(variance)/=n) return
    if (.not.all(ieee_is_finite(p)).or. &
        .not.all(ieee_is_finite(wind)).or. &
        .not.all(ieee_is_finite(variance))) return
    if (.not.all(ieee_is_finite([p_sample,wind_sample,sample_variance]))) return

    ! This finite arithmetic envelope protects the research calculation from
    ! overflow and underflow; it is not a physical bound or data authority.
    if (any(p<=0._real64).or.any(p>1.e9_real64)) return
    if (any(abs(wind)>1.e12_real64)) return
    if (any(variance<1.e-100_real64).or.any(variance>1.e100_real64)) return
    if (p_sample<=0._real64.or.p_sample>1.e9_real64) return
    if (abs(wind_sample)>1.e12_real64) return
    if (sample_variance<1.e-100_real64.or.sample_variance>1.e100_real64) return
    if (any(p(:n-1)<=p(2:n))) return
    if (p_sample<p(n).or.p_sample>p(1)) return

    ! The row has at most two nonzero weights.  At an exact knot the first
    ! matching interval gives that knot weight one, making the row continuous.
    a=0._real64
    interval=0
    do k=1,n-1
      if (p_sample<=p(k).and.p_sample>=p(k+1)) then
        weight=(p_sample-p(k+1))/(p(k)-p(k+1))
        if (weight<0._real64.or.weight>1._real64) return
        a(k)=weight
        a(k+1)=1._real64-weight
        interval=k
        exit
      end if
    end do
    if (interval==0) return

    pred=dot_product(a,wind)
    innovation=wind_sample-pred
    if (.not.ieee_is_finite(pred).or..not.ieee_is_finite(innovation)) then
      fitted=nan
      innovation=nan
      return
    end if

    ! Normalize before forming the denominator.  This preserves the formula
    ! while avoiding overflow from large finite variances and avoids dividing
    ! the innovation by a tiny unscaled denominator.
    scale=max(sample_variance,maxval(variance))
    if (.not.ieee_is_finite(scale).or.scale<=0._real64) then
      fitted=nan
      innovation=nan
      return
    end if
    scaled_variance=variance/scale
    denominator=sample_variance/scale+dot_product(a,scaled_variance*a)
    if (.not.ieee_is_finite(denominator).or.denominator<=0._real64) then
      fitted=nan
      innovation=nan
      return
    end if

    gain=(scaled_variance*a)/denominator
    fitted=wind+gain*innovation
    if (.not.all(ieee_is_finite(gain)).or..not.all(ieee_is_finite(fitted))) then
      fitted=nan
      innovation=nan
      return
    end if
    ok=.true.
  end subroutine fit_profile_sample
end module qbal_profile_reconstruction
