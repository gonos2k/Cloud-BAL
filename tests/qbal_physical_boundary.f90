! Read-only diagnostics of the legacy pressure layout; no state mutation.
module qbal_physical_boundary
  use iso_fortran_env, only: real64, int64
  use ieee_arithmetic, only: ieee_is_finite
  implicit none
  private
  integer, parameter, public :: STATUS_OK=0, STATUS_INVALID=1
  public :: legacy_pressure_geometry, surface_layer, column_telescope
  public :: pressure_secant, surface_residual, physical_column_residual
contains
  ! balstagger averages omega at adjacent original pressure levels; its top
  ! omega is the original finite-top value. U/V plane k is at p(k+1).
  subroutine legacy_pressure_geometry(p,omega_p,spacing,status)
    real(real64), intent(in) :: p(:)
    real(real64), intent(out) :: omega_p(:),spacing(:)
    integer, intent(out) :: status
    integer :: n
    status=STATUS_INVALID; omega_p=0; spacing=0; n=size(p)
    if (n<2) return
    if (size(omega_p)/=n.or.size(spacing)/=n-1) return
    if (.not.all(ieee_is_finite(p))) return
    if (any(p<=0).or.any(p>1.e9_real64)) return
    if (any(p(:n-1)<=p(2:))) return
    omega_p(:n-1)=0.5_real64*(p(:n-1)+p(2:))
    omega_p(n)=p(n)
    spacing=omega_p(:n-1)-omega_p(2:)
    status=STATUS_OK
  end subroutine

  ! First original pressure level at/above the surface, and thickness to its
  ! upper omega donor. This inventory does not authorize a surface flux or
  ! assert that the q-level horizontal donors survived terbnd.
  subroutine surface_layer(p,ps,q,partial_dp,status)
    real(real64), intent(in) :: p(:),ps
    integer, intent(out) :: q,status
    real(real64), intent(out) :: partial_dp
    real(real64) :: omega_p(size(p)),spacing(max(0,size(p)-1))
    integer :: k
    q=0; partial_dp=0; status=STATUS_INVALID
    if (.not.ieee_is_finite(ps)) return
    call legacy_pressure_geometry(p,omega_p,spacing,status)
    if (status/=STATUS_OK) return
    status=STATUS_INVALID
    if (ps>p(1).or.ps<=p(size(p))) return
    do k=1,size(p)
      if (p(k)>ps) cycle
      q=k; partial_dp=ps-omega_p(k)
      status=STATUS_OK
      return
    end do
  end subroutine

  ! Arrays represent rows 2:nz: horizontal divergence, dp and donor validity;
  ! omega contains their nz shared endpoints. Gaps start new column blocks.
  ! Both sides use legacy dp, not a claimed physical partial-cell thickness.
  subroutine column_telescope(horizontal,omega,dp,valid,total,lateral,ends, &
                              error,bound,status)
    real(real64), intent(in) :: horizontal(:),omega(:),dp(:)
    logical, intent(in) :: valid(:)
    real(real64), intent(out) :: total,lateral,ends,error,bound
    integer, intent(out) :: status
    integer :: k,n
    real(real64) :: term,scale
    total=0; lateral=0; ends=0; error=0; bound=0; status=STATUS_INVALID
    n=size(horizontal)
    if (n<1.or.size(omega)/=n+1.or.size(dp)/=n.or.size(valid)/=n) return
    if (.not.all(ieee_is_finite(horizontal))) return
    if (.not.all(ieee_is_finite(omega))) return
    if (.not.all(ieee_is_finite(dp))) return
    if (any(dp<=0)) return
    if (any(abs(horizontal)>1.e12_real64).or.any(abs(omega)>1.e12_real64)) return
    if (any(dp>1.e9_real64)) return
    scale=0
    do k=1,n
      if (.not.valid(k)) cycle
      term=horizontal(k)+(omega(k)-omega(k+1))/dp(k)
      total=total+dp(k)*term
      lateral=lateral+dp(k)*horizontal(k)
      scale=scale+dp(k)*abs(horizontal(k))+abs(omega(k))+abs(omega(k+1))
      if (k==1) then
        ends=ends+omega(k)
      else if (.not.valid(k-1)) then
        ends=ends+omega(k)
      end if
      if (k==n) then
        ends=ends-omega(k+1)
      else if (.not.valid(k+1)) then
        ends=ends-omega(k+1)
      end if
    end do
    error=total-lateral-ends
    ! Includes sequential summation depth; not a physical residual allowance.
    bound=16*real(n+1,real64)*epsilon(1._real64)*scale
    status=STATUS_OK
  end subroutine

  ! Caller supplies explicit delivery eligibility. Valid/reference epochs
  ! alone must not be used to invent operational availability.
  subroutine pressure_secant(p0,p1,t0,t1,eligible,tendency,status)
    real(real64), intent(in) :: p0,p1
    integer(int64), intent(in) :: t0,t1
    logical, intent(in) :: eligible
    real(real64), intent(out) :: tendency
    integer, intent(out) :: status
    real(real64) :: dt
    tendency=0; status=STATUS_INVALID
    if (.not.eligible) return
    if (.not.ieee_is_finite(p0).or..not.ieee_is_finite(p1)) return
    if (min(p0,p1)<=0.or.max(p0,p1)>1.e9_real64) return
    if (t1<=t0) return
    dt=real(t1,real64)-real(t0,real64)
    if (dt<=0) return
    tendency=(p1-p0)/dt
    status=STATUS_OK
  end subroutine

  pure real(real64) function surface_residual(omega,u,v,gx,gy,ps_t) result(r)
    real(real64), intent(in) :: omega,u,v,gx,gy,ps_t
    ! Inputs must be collocated at the physical surface in the same frame.
    r=omega-u*gx-v*gy-ps_t
  end function

  pure real(real64) function physical_column_residual(ps_t,div_q,omega_top) result(r)
    real(real64), intent(in) :: ps_t,div_q,omega_top
    ! div_q is divergence of the complete pressure-integrated transport,
    ! including the variable surface limit; not integral(div_p(v)) alone.
    r=ps_t+div_q-omega_top
  end function
end module
