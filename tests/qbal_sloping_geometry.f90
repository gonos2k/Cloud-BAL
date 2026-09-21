! Read-only research geometry: an equal-area spherical chart and planar PS.
module qbal_sloping_geometry
  use iso_fortran_env, only: real64
  use ieee_arithmetic, only: ieee_is_finite
  use qbal_pressure_flux, only: integrate_pressure_profile
  implicit none
  private
  public :: equal_area_point, sloping_column_faces, edge_wind_flux
contains
  ! Angles in radians. x/y preserve sphere area; velocity scales map true
  ! east/north m/s into dx/dt,dy/dt. Neither scale is a wind-frame rotation.
  subroutine equal_area_point(lat,lon,lat0,lon0,radius,xy,velocity_scale,ok)
    real(real64), intent(in) :: lat,lon,lat0,lon0,radius
    real(real64), intent(out) :: xy(2),velocity_scale(2)
    logical, intent(out) :: ok
    real(real64) :: c,c0
    xy=0;velocity_scale=0;ok=.false.
    if (.not.all(ieee_is_finite([lat,lon,lat0,lon0,radius]))) return
    if (abs(lat)>=1.55_real64.or.abs(lat0)>=1.55_real64) return
    if (abs(lon-lon0)>acos(-1._real64).or.radius<=0.or.radius>1.e8_real64) return
    c=cos(lat);c0=cos(lat0)
    xy=[radius*c0*(lon-lon0),radius*(sin(lat)-sin(lat0))/c0]
    velocity_scale=[c0/c,c/c0]
    ok=.true.
  end subroutine

  ! xy vertices must be CCW. Face order: ground, finite top, edges 12/23/31.
  ! moment(a,b,f)=integral(position_a * outward_metric_b) on face f,
  ! using positions relative to [xy(:,1),pt] to reduce cancellation.
  ! Each triangle defines PS linearly, not an impermeable staircase wall.
  subroutine sloping_column_faces(xy,ps,pt,metric,moment,volume,ok)
    real(real64), intent(in) :: xy(2,3),ps(3),pt
    real(real64), intent(out) :: metric(3,5),moment(3,3,5),volume
    logical, intent(out) :: ok
    real(real64) :: bottom(3,3),top(3,3),area2
    integer :: a,b
    metric=0;moment=0;volume=0;ok=.false.
    if (.not.all(ieee_is_finite(xy)).or..not.all(ieee_is_finite(ps))) return
    if (.not.ieee_is_finite(pt)) return
    if (any(abs(xy)>1.e9_real64).or.pt<=0.or.any(ps>1.e9_real64).or.any(ps<=pt)) return
    bottom(1:2,:)=xy-spread(xy(:,1),2,3);bottom(3,:)=ps-pt
    top=bottom;top(3,:)=0
    area2=bottom(1,2)*bottom(2,3)-bottom(2,2)*bottom(1,3)
    if (area2<=0) return
    call triangle(bottom(:,1),bottom(:,2),bottom(:,3),metric(:,1),moment(:,:,1))
    call triangle(top(:,3),top(:,2),top(:,1),metric(:,2),moment(:,:,2))
    do a=1,3
      b=mod(a,3)+1
      call triangle(bottom(:,a),top(:,a),top(:,b),metric(:,a+2),moment(:,:,a+2))
      call triangle(bottom(:,a),top(:,b),bottom(:,b),metric(:,a+2),moment(:,:,a+2))
    end do
    volume=(area2/2)*(sum(bottom(3,:))/3)
    if (volume<=0) then
      metric=0;moment=0;return
    end if
    ok=.true.
  end subroutine

  subroutine triangle(a,b,c,metric,moment)
    real(real64), intent(in) :: a(3),b(3),c(3)
    real(real64), intent(inout) :: metric(3),moment(3,3)
    real(real64) :: u(3),v(3),normal(3),center(3)
    integer :: k
    u=b-a;v=c-a
    normal=.5_real64*[u(2)*v(3)-u(3)*v(2),u(3)*v(1)-u(1)*v(3),u(1)*v(2)-u(2)*v(1)]
    center=(a+b+c)/3
    metric=metric+normal
    do k=1,3
      moment(:,k)=moment(:,k)+center*normal(k)
    end do
  end subroutine

  ! CCW horizontal edge: outward horizontal metric is [dy,-dx].
  ! Profiles are chart velocities, linearly interpolated along the edge.
  ! Pressure integration is exact for the declared piecewise-linear profile.
  ! Integrate only the covered region p<=p(1); report the omitted pressure
  ! interval integral explicitly. No extrapolation supplies the ground wind.
  subroutine edge_wind_flux(xy,ps,pt,p,u,v,flux,uncovered,ok)
    real(real64), intent(in) :: xy(2,2),ps(2),pt,p(:),u(:,:),v(:,:)
    real(real64), intent(out) :: flux,uncovered
    logical, intent(out) :: ok
    real(real64) :: knots(size(p)+2),s,t,a,b,mid,half,bottom,iu(2),iv(2),part
    real(real64) :: normal(2),velocity(2),gauss(2),temp
    integer :: nk,k,j,g
    logical :: valid
    flux=0;uncovered=0;ok=.false.
    if (size(p)<2.or.any(shape(u)/=[size(p),2]).or.any(shape(v)/=[size(p),2])) return
    if (.not.all(ieee_is_finite(xy)).or..not.all(ieee_is_finite(ps))) return
    if (.not.ieee_is_finite(pt)) return
    if (any(abs(xy)>1.e9_real64).or.pt<=0.or.any(ps<=pt).or.any(ps>1.e9_real64)) return
    if (all(xy(:,1)==xy(:,2))) return
    ! Validate both complete supplied profiles before accumulating any result.
    do j=1,2
      call integrate_pressure_profile(p,u(:,j),pt,pt,part,valid)
      if (.not.valid) return
      call integrate_pressure_profile(p,v(:,j),pt,pt,part,valid)
      if (.not.valid) return
    end do
    knots(1:2)=[0._real64,1._real64];nk=2
    if (ps(1)/=ps(2)) then
      do k=1,size(p)
        if (p(k)<=minval(ps).or.p(k)>=maxval(ps)) cycle
        s=(p(k)-ps(1))/(ps(2)-ps(1))
        if (s<=0.or.s>=1) cycle
        nk=nk+1;knots(nk)=s
      end do
    end if
    do k=2,nk
      temp=knots(k);j=k-1
      do while (j>=1)
        if (knots(j)<=temp) exit
        knots(j+1)=knots(j);j=j-1
      end do
      knots(j+1)=temp
    end do
    normal=[xy(2,2)-xy(2,1),xy(1,1)-xy(1,2)]
    gauss=[-1._real64,1._real64]/sqrt(3._real64)
    do k=1,nk-1
      a=knots(k);b=knots(k+1);mid=(a+b)/2;half=(b-a)/2
      do g=1,2
        s=mid+half*gauss(g);t=(1-s)*ps(1)+s*ps(2)
        bottom=min(t,p(1))
        do j=1,2
          call integrate_pressure_profile(p,u(:,j),bottom,pt,iu(j),valid)
          if (.not.valid) then
            flux=0;uncovered=0;return
          end if
          call integrate_pressure_profile(p,v(:,j),bottom,pt,iv(j),valid)
          if (.not.valid) then
            flux=0;uncovered=0;return
          end if
        end do
        velocity=[(1-s)*iu(1)+s*iu(2),(1-s)*iv(1)+s*iv(2)]
        flux=flux+half*dot_product(normal,velocity)
        uncovered=uncovered+half*max(0._real64,t-p(1))
      end do
    end do
    ok=.true.
  end subroutine
end module
