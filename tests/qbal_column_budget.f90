! Research-only integrated column terms; unknown fluxes remain unknown.
module qbal_column_budget
  use iso_fortran_env, only: real64, int64
  use ieee_arithmetic, only: ieee_is_finite, ieee_value, ieee_quiet_nan
  use qbal_physical_boundary, only: pressure_secant, STATUS_OK
  use qbal_sloping_geometry, only: sloping_column_faces
  implicit none
  private
  public :: surface_pressure_flux, column_flux_budget
contains
  ! Fixed horizontal triangle and finite top. This secant is an interval mean,
  ! not an instantaneous tendency or a certificate of operational availability.
  subroutine surface_pressure_flux(xy,ps0,ps1,pt,t0,t1,eligible,flux,volume_rate,bound,ok)
    real(real64), intent(in) :: xy(2,3),ps0(3),ps1(3),pt
    integer(int64), intent(in) :: t0,t1
    logical, intent(in) :: eligible
    real(real64), intent(out) :: flux,volume_rate,bound
    logical, intent(out) :: ok
    real(real64) :: m(3,5),moment(3,3,5),v0,v1,tendency(3),area,dt
    integer :: k,status
    flux=0;volume_rate=0;bound=0;ok=.false.
    do k=1,3
      call pressure_secant(ps0(k),ps1(k),t0,t1,eligible,tendency(k),status)
      if (status/=STATUS_OK) return
    end do
    call sloping_column_faces(xy,ps0,pt,m,moment,v0,ok)
    if (.not.ok) return
    area=m(3,1)
    call sloping_column_faces(xy,ps1,pt,m,moment,v1,ok)
    if (.not.ok) return
    dt=real(t1,real64)-real(t0,real64)
    flux=area*(sum(tendency)/3)
    volume_rate=(v1-v0)/dt
    ! Subtracting nearly equal volumes must use their pre-cancellation scale.
    bound=64*epsilon(flux)*((abs(v0)+abs(v1))/dt+abs(flux))
    ok=abs(flux-volume_rate)<=bound
  end subroutine

  ! Terms are integrated m2 Pa/s, not velocities. Side values have one global
  ! orientation; signs orient them out of this column. Top is positive omega.
  ! subtotal contains only known terms. residual is NaN unless all are known.
  subroutine column_flux_budget(ground,covered,missing,signs,missing_known,top,top_known, &
                                subtotal,residual,complete,ok)
    real(real64), intent(in) :: ground,covered(3),missing(3),top
    integer, intent(in) :: signs(3)
    logical, intent(in) :: missing_known(3),top_known
    real(real64), intent(out) :: subtotal,residual
    logical, intent(out) :: complete,ok
    real(real64) :: terms(8)
    integer :: k
    subtotal=ieee_value(0._real64,ieee_quiet_nan);residual=subtotal
    complete=.false.;ok=.false.;terms=0
    if (.not.ieee_is_finite(ground)) return
    if (.not.all(ieee_is_finite(covered))) return
    if (any(signs/=1.and.signs/=-1)) return
    terms(1)=ground;terms(2:4)=signs*covered
    do k=1,3
      if (.not.missing_known(k)) cycle
      if (.not.ieee_is_finite(missing(k))) return
      terms(k+4)=signs(k)*missing(k)
    end do
    if (top_known) then
      if (.not.ieee_is_finite(top)) return
      terms(8)=-top
    end if
    ! Research input envelope avoids overflow with trapped arithmetic.
    if (any(abs(terms)>1.e100_real64)) return
    subtotal=sum(terms)
    complete=all(missing_known).and.top_known
    if (complete) residual=subtotal
    ok=.true.
  end subroutine
end module
