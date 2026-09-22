! Conditional endpoint reconstruction on one shared pressure face.
module qbal_profile_face
  use iso_fortran_env, only: real64
  use ieee_arithmetic, only: ieee_is_finite, ieee_value, ieee_quiet_nan
  use qbal_profile_reconstruction, only: fit_profile_sample
  use qbal_sloping_geometry, only: edge_wind_flux
  implicit none
  private
  public :: fit_edge_transport
contains
  ! wind/variance/fitted dimensions: pressure knot, chart U/V, endpoint.
  ! Fit each endpoint once, then interpolate those profiles along the face.
  ! All knots must be above both ground endpoints. No new lower prior is made.
  ! uncovered is mean ground-to-sample pressure span, NOT a flux or its error.
  ! ok denotes computational support only, not physical boundary authority.
  subroutine fit_edge_transport(xy,ps,pt,p,wind,variance,p_sample,sample_wind, &
      sample_variance,fitted,innovation,flux,uncovered,ok)
    real(real64), intent(in) :: xy(2,2),ps(2),pt,p(:),wind(:,:,:),variance(:,:,:)
    real(real64), intent(in) :: p_sample(2),sample_wind(2,2),sample_variance(2,2)
    real(real64), intent(out) :: fitted(:,:,:),innovation(2,2),flux,uncovered
    logical, intent(out) :: ok
    real(real64) :: trial(size(p),2,2),difference(2,2),u(size(p),2),v(size(p),2)
    real(real64) :: nan,transport,omitted
    integer :: n,endpoint,component
    logical :: valid

    nan=ieee_value(0._real64,ieee_quiet_nan)
    fitted=nan;innovation=nan;flux=nan;uncovered=nan;ok=.false.
    n=size(p)
    if (n<2) return
    if (any(shape(wind)/=[n,2,2]).or.any(shape(variance)/=[n,2,2])) return
    if (any(shape(fitted)/=[n,2,2])) return
    if (.not.all(ieee_is_finite(xy)).or..not.all(ieee_is_finite(ps))) return
    if (.not.all(ieee_is_finite(p)).or..not.all(ieee_is_finite(p_sample))) return
    if (.not.ieee_is_finite(pt)) return
    if (any(abs(xy)>1.e9_real64).or.any(ps>1.e9_real64)) return
    if (all(xy(:,1)==xy(:,2))) return
    if (pt<=0.or.pt<p(n).or.pt>p(1)) return
    if (p(1)>minval(ps).or.any(p_sample>ps)) return
    if (any(p_sample<=pt).or.any(p_sample>p(1))) return

    do endpoint=1,2
      do component=1,2
        call fit_profile_sample(p,wind(:,component,endpoint),variance(:,component,endpoint), &
          p_sample(endpoint),sample_wind(component,endpoint),sample_variance(component,endpoint), &
          trial(:,component,endpoint),difference(component,endpoint),valid)
        if (.not.valid) return
      end do
    end do
    u=trial(:,1,:);v=trial(:,2,:)
    call edge_wind_flux(xy,p_sample,pt,p,u,v,transport,omitted,valid)
    if (.not.valid) return
    if (.not.ieee_is_finite(transport).or..not.ieee_is_finite(omitted)) return
    if (omitted/=0._real64) return
    ! Commit outputs only after the entire face succeeds.
    fitted=trial;innovation=difference;flux=transport
    uncovered=sum(ps-p_sample)/2
    ok=.true.
  end subroutine fit_edge_transport
end module qbal_profile_face
