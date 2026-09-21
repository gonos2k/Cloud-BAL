! Small pressure-height and lower-strip transport research kernels.
module qbal_lower_transport
  use iso_fortran_env, only: real64
  use ieee_arithmetic, only: ieee_is_finite, ieee_value, ieee_quiet_nan
  implicit none
  private
  public :: pressure_at_height, lower_strip_flux
contains

  ! Interpolate log(p) in the supplied vertical coordinate.  The caller is
  ! responsible for declaring geometric versus geopotential datum and for
  ! supplying terrain and aboveground heights consistently; this kernel does
  ! not identify or certify that datum and performs no datum conversion.
  subroutine pressure_at_height(ps,terrain,p,height,sample_height_agl,p_sample,ok)
    real(real64), intent(in) :: ps,terrain,p(:),height(:),sample_height_agl
    real(real64), intent(out) :: p_sample
    logical, intent(out) :: ok
    real(real64) :: nan,target,lower_height,lower_log,log_value,fraction
    integer :: i,n,first_above,n_above

    nan=ieee_value(0._real64,ieee_quiet_nan)
    p_sample=nan
    ok=.false.
    n=size(p)
    if (n<1.or.size(height)/=n) return
    if (.not.all(ieee_is_finite([ps,terrain,sample_height_agl]))) return
    if (.not.all(ieee_is_finite(p))) return
    if (ps<=0._real64) return
    if (ps>1.e9_real64) return
    if (abs(terrain)>1.e9_real64) return
    if (sample_height_agl<0._real64) return
    if (sample_height_agl>1.e9_real64) return
    if (any(p<=0._real64)) return
    if (any(p>1.e9_real64)) return
    do i=1,n-1
      if (p(i)<=p(i+1)) return
    end do

    ! A level with p < PS is the aboveground support.  Every such level must
    ! be above terrain and finite; donor levels at/above PS are ignored, so
    ! their height entries may be caller-provided fill values.
    first_above=0
    n_above=0
    do i=1,n
      if (p(i)<ps) then
        if (first_above==0) first_above=i
        n_above=n_above+1
        if (.not.ieee_is_finite(height(i))) return
        if (abs(height(i))>1.e9_real64) return
        if (height(i)<=terrain) return
        if (i>first_above) then
          if (height(i)<=height(i-1)) return
        end if
      end if
    end do
    if (n_above<1) return

    target=terrain+sample_height_agl
    if (.not.ieee_is_finite(target)) return
    if (target<terrain) return
    lower_height=terrain
    lower_log=log(ps)
    do i=first_above,n
      if (target<=height(i)) then
        fraction=(target-lower_height)/(height(i)-lower_height)
        log_value=lower_log+fraction*(log(p(i))-lower_log)
        p_sample=exp(log_value)
        if (.not.ieee_is_finite(p_sample)) then
          p_sample=nan
          return
        end if
        if (p_sample<=0._real64) then
          p_sample=nan
          return
        end if
        ok=.true.
        return
      end if
      lower_height=height(i)
      lower_log=log(p(i))
    end do
    ! The requested height is above the highest supported level.
    p_sample=nan
  end subroutine pressure_at_height

  ! Integrate the pressure strip exactly.  With s in [0,1], p_sample and
  ! both endpoint winds are linear in s, so the pressure-integrated velocity
  ! is 0.5*(p_sample(s)-p_cap)*(wind_cap(s)+wind_sample(s)), a quadratic.
  ! The outward metric for the directed edge is [dy,-dx].
  subroutine lower_strip_flux(xy,p_sample,p_cap,wind_sample,wind_cap,flux,ok)
    real(real64), intent(in) :: xy(2,2),p_sample(2),p_cap
    real(real64), intent(in) :: wind_sample(2,2),wind_cap(2,2)
    real(real64), intent(out) :: flux
    logical, intent(out) :: ok
    real(real64) :: nan,dxy(2),normal(2),width0,width1
    real(real64) :: wind_sum0(2),wind_sum1(2),integrated(2)

    nan=ieee_value(0._real64,ieee_quiet_nan)
    flux=nan
    ok=.false.
    if (.not.all(ieee_is_finite(xy)).or..not.all(ieee_is_finite(p_sample))) return
    if (.not.all(ieee_is_finite(wind_sample)).or..not.all(ieee_is_finite(wind_cap))) return
    if (.not.ieee_is_finite(p_cap)) return
    if (p_cap<=0._real64) return
    if (any(p_sample<=0._real64)) return
    if (any(p_sample<p_cap)) return
    if (any(abs(xy)>1.e9_real64)) return
    if (any(abs(p_sample)>1.e9_real64)) return
    if (p_cap>1.e9_real64) return
    if (any(abs(wind_sample)>1.e12_real64)) return
    if (any(abs(wind_cap)>1.e12_real64)) return
    dxy=xy(:,2)-xy(:,1)
    if (all(dxy==0._real64)) return
    normal=[dxy(2),-dxy(1)]

    width0=p_sample(1)-p_cap
    width1=p_sample(2)-p_sample(1)
    wind_sum0=wind_cap(:,1)+wind_sample(:,1)
    wind_sum1=wind_cap(:,2)+wind_sample(:,2)-wind_sum0
    integrated=width0*wind_sum0 + 0.5_real64*(width0*wind_sum1+width1*wind_sum0) &
      + (width1/3._real64)*wind_sum1
    flux=0.5_real64*dot_product(normal,integrated)
    if (.not.ieee_is_finite(flux)) then
      flux=nan
      return
    end if
    ok=.true.
  end subroutine lower_strip_flux
end module qbal_lower_transport
