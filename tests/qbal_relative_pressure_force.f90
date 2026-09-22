! Bounded research kernel for relative pressure-surface geopotential force.
!
! The first routine turns PR41's temperature, moisture, and total layer
! thickness changes (metres) into a relative geopotential.  Levels are in
! descending pressure order: layer k joins level k to level k+1.  The caller
! chooses the common reference level, whose relative geopotential is the
! declared gauge zero.
!
! The second routine differentiates an affine geopotential over the supplied
! projected triangle.  Its inputs are three values at one pressure surface;
! no vertical interpolation or Earth-radius conversion is done here.
module qbal_relative_pressure_force
  use, intrinsic :: iso_fortran_env, only: real64
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite, ieee_quiet_nan, &
                                           ieee_value
  implicit none
  private

  real(real64), parameter :: G0=9.80665_real64
  real(real64), parameter :: MAX_PROJECTED_COORDINATE=1.0e12_real64
  real(real64), parameter :: MAX_LAYER_THICKNESS=1.0e12_real64
  real(real64), parameter :: MAX_GEOPOTENTIAL=1.0e15_real64
  real(real64), parameter :: MAX_LATITUDE=1.55_real64
  real(real64), parameter :: GEOMETRY_EPSILON_FACTOR=64.0_real64

  public :: build_relative_geopotential
  public :: triangle_pressure_force

contains

  ! delta_z(component,k) is a PR41 thickness contribution in metres for the
  ! layer between descending-pressure levels k and k+1.  Components are
  ! temperature, moisture, and total, respectively.  Unsupported layers may
  ! contain NaN because their values are not consumed.  A supported layer must
  ! have finite values for every component.
  !
  ! A valid reference alone is a successful, isolated gauge.  A missing level
  ! or layer stops propagation in that direction and cannot be crossed later.
  ! Thus ok reports valid inputs and a valid reference; reachable reports the
  ! connected output support.
  subroutine build_relative_geopotential(delta_z,level_valid,layer_supported, &
                                         reference_level,delta_phi,reachable,ok)
    real(real64), intent(in) :: delta_z(:,:)
    logical, intent(in) :: level_valid(:),layer_supported(:)
    integer, intent(in) :: reference_level
    real(real64), intent(out) :: delta_phi(:,:)
    logical, intent(out) :: reachable(:)
    logical, intent(out) :: ok
    real(real64) :: nan
    real(real64) :: candidate(3)
    integer :: nlevel,k

    nan=ieee_value(0.0_real64,ieee_quiet_nan)
    delta_phi=nan
    reachable=.false.
    ok=.false.

    nlevel=size(level_valid)
    if (nlevel<1) return
    if (size(delta_z,1)/=3 .or. size(delta_z,2)/=max(0,nlevel-1)) return
    if (size(layer_supported)/=max(0,nlevel-1)) return
    if (size(delta_phi,1)/=3 .or. size(delta_phi,2)/=nlevel) return
    if (size(reachable)/=nlevel) return
    if (reference_level<1 .or. reference_level>nlevel) return
    if (.not.level_valid(reference_level)) return

    ! Validate only data declared supported.  Missing data outside support is
    ! intentionally represented by the NaN outputs rather than guessed across.
    do k=1,nlevel-1
      if (layer_supported(k)) then
        if (.not.level_valid(k) .or. .not.level_valid(k+1)) return
        if (.not.all(ieee_is_finite(delta_z(:,k)))) return
        if (any(abs(delta_z(:,k))>MAX_LAYER_THICKNESS)) return
      end if
    end do

    delta_phi(:,reference_level)=0.0_real64
    reachable(reference_level)=.true.

    ! Descending pressure: lower levels are reached through k-1, so
    ! phi(k)=phi(k+1)-g0*delta_z(:,k).
    do k=reference_level-1,1,-1
      if (.not.level_valid(k) .or. .not.layer_supported(k)) exit
      candidate=delta_phi(:,k+1)-G0*delta_z(:,k)
      if (.not.all(ieee_is_finite(candidate)) .or. &
          any(abs(candidate)>MAX_GEOPOTENTIAL)) then
        delta_phi=nan
        reachable=.false.
        return
      end if
      delta_phi(:,k)=candidate
      reachable(k)=.true.
    end do

    ! Above the reference, phi(k)=phi(k-1)+g0*delta_z(:,k-1).
    do k=reference_level+1,nlevel
      if (.not.level_valid(k) .or. .not.layer_supported(k-1)) exit
      candidate=delta_phi(:,k-1)+G0*delta_z(:,k-1)
      if (.not.all(ieee_is_finite(candidate)) .or. &
          any(abs(candidate)>MAX_GEOPOTENTIAL)) then
        delta_phi=nan
        reachable=.false.
        return
      end if
      delta_phi(:,k)=candidate
      reachable(k)=.true.
    end do

    ok=.true.
  end subroutine build_relative_geopotential

  ! Fit phi(x,y)=c+gx*x+gy*y on the supplied triangle and convert chart
  ! gradients to physical east/north acceleration.  latitude is the explicit
  ! evaluation latitude and latitude0 is the equal-area chart latitude:
  !
  !   a_east  = -cos(latitude0)/cos(latitude)  * gx
  !   a_north = -cos(latitude)/cos(latitude0)  * gy
  !
  ! xy is already projected in metres.  In particular, no radius or degree
  ! conversion belongs in this routine.
  subroutine triangle_pressure_force(xy,phi_nodes,latitude,latitude0, &
                                     gradient_xy,acceleration_en,ok)
    real(real64), intent(in) :: xy(2,3),phi_nodes(3)
    real(real64), intent(in) :: latitude,latitude0
    real(real64), intent(out) :: gradient_xy(2),acceleration_en(2)
    logical, intent(out) :: ok
    real(real64) :: nan
    real(real64) :: dx21,dy21,dx31,dy31,rhs21,rhs31,det,scale
    real(real64) :: gx,gy,c,c0
    real(real64) :: acceleration_work(2)

    nan=ieee_value(0.0_real64,ieee_quiet_nan)
    gradient_xy=nan
    acceleration_en=nan
    ok=.false.

    if (.not.all(ieee_is_finite(xy)) .or. &
        .not.all(ieee_is_finite(phi_nodes)) .or. &
        .not.ieee_is_finite(latitude) .or. .not.ieee_is_finite(latitude0)) return
    if (any(abs(xy)>MAX_PROJECTED_COORDINATE)) return
    if (any(abs(phi_nodes)>MAX_GEOPOTENTIAL)) return
    if (abs(latitude)>=MAX_LATITUDE .or. abs(latitude0)>=MAX_LATITUDE) return

    dx21=xy(1,2)-xy(1,1)
    dy21=xy(2,2)-xy(2,1)
    dx31=xy(1,3)-xy(1,1)
    dy31=xy(2,3)-xy(2,1)
    if (.not.all(ieee_is_finite([dx21,dy21,dx31,dy31]))) return
    det=dx21*dy31-dx31*dy21
    scale=max(abs(dx21),abs(dy21),abs(dx31),abs(dy31))
    if (.not.ieee_is_finite(det) .or. .not.ieee_is_finite(scale) .or. scale<=0.0_real64) return
    if (abs(det)<=GEOMETRY_EPSILON_FACTOR*epsilon(1.0_real64)*scale*scale) return

    rhs21=phi_nodes(2)-phi_nodes(1)
    rhs31=phi_nodes(3)-phi_nodes(1)
    if (.not.all(ieee_is_finite([rhs21,rhs31]))) return
    gx=(rhs21*dy31-rhs31*dy21)/det
    gy=(dx21*rhs31-dx31*rhs21)/det
    if (.not.all(ieee_is_finite([gx,gy]))) return

    c=cos(latitude)
    c0=cos(latitude0)
    if (.not.all(ieee_is_finite([c,c0])) .or. c<=0.0_real64 .or. c0<=0.0_real64) return
    acceleration_work=[-c0/c*gx,-c/c0*gy]
    if (.not.all(ieee_is_finite(acceleration_work))) return

    gradient_xy=[gx,gy]
    acceleration_en=acceleration_work
    ok=.true.
  end subroutine triangle_pressure_force

end module qbal_relative_pressure_force
