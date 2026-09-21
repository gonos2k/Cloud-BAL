! Pressure-grid research kernel. No production caller or boundary authority.
module qbal_pressure_flux
  use iso_fortran_env, only: real64
  use ieee_arithmetic, only: ieee_is_finite
  use qbal_physical_boundary, only: legacy_pressure_geometry, surface_layer, STATUS_OK
  implicit none
  private
  public :: pressure_interfaces, integrate_pressure_profile
  public :: flux_divergence, multiplier_flux
contains
  ! Retain the declared legacy omega positions above the first usable level,
  ! replace the lower endpoint by PS, and retain the finite top p(n).
  ! These are new control volumes, not a relabelling of legacy D rows.
  subroutine pressure_interfaces(p,ps,interfaces,ok)
    real(real64), intent(in) :: p(:),ps
    real(real64), allocatable, intent(out) :: interfaces(:)
    logical, intent(out) :: ok
    real(real64) :: omega_p(size(p)),spacing(max(0,size(p)-1)),span
    integer :: q,status
    ok=.false.
    allocate(interfaces(0))
    call surface_layer(p,ps,q,span,status)
    if (status/=STATUS_OK) return
    call legacy_pressure_geometry(p,omega_p,spacing,status)
    if (status/=STATUS_OK) return
    interfaces=[ps,omega_p(q:)]
    ok=.true.
  end subroutine

  ! Integral from top to bottom of a declared piecewise-linear profile.
  ! No extrapolation, sentinel filling, or assumption that endpoint wind is
  ! a layer mean. The caller must supply valid collocated physical samples.
  subroutine integrate_pressure_profile(p,value,bottom,top,integral,ok)
    real(real64), intent(in) :: p(:),value(:),bottom,top
    real(real64), intent(out) :: integral
    logical, intent(out) :: ok
    real(real64) :: lo,hi,vlo,vhi
    integer :: k,n
    integral=0; ok=.false.; n=size(p)
    if (n<2.or.size(value)/=n) return
    if (.not.all(ieee_is_finite(p)).or..not.all(ieee_is_finite(value))) return
    if (.not.ieee_is_finite(bottom).or..not.ieee_is_finite(top)) return
    if (any(p<=0).or.any(p>1.e9_real64).or.any(abs(value)>1.e12_real64)) return
    if (any(p(:n-1)<=p(2:))) return
    if (top< p(n).or.bottom>p(1).or.bottom<top) return
    do k=1,n-1
      hi=min(bottom,p(k)); lo=max(top,p(k+1))
      if (hi<=lo) cycle
      vhi=value(k+1)+(value(k)-value(k+1))*((hi-p(k+1))/(p(k)-p(k+1)))
      vlo=value(k+1)+(value(k)-value(k+1))*((lo-p(k+1))/(p(k)-p(k+1)))
      integral=integral+(hi-lo)*(0.5_real64*vlo+0.5_real64*vhi)
    end do
    ok=.true.
  end subroutine

  ! Each integrated oriented face contributes +F to plus and -F to minus.
  ! Zero denotes exterior. Volumes are area*dp [m2 Pa], fluxes [m2 Pa/s].
  ! At the ground F must be the normal combination, not omega alone.
  subroutine flux_divergence(volume,plus,minus,flux,divergence,ok)
    real(real64), intent(in) :: volume(:),flux(:)
    integer, intent(in) :: plus(:),minus(:)
    real(real64), intent(out) :: divergence(:)
    logical, intent(out) :: ok
    integer :: f
    divergence=0; ok=.false.
    if (size(divergence)/=size(volume)) return
    if (.not.valid_faces(size(volume),plus,minus,size(flux))) return
    if (.not.all(ieee_is_finite(volume)).or..not.all(ieee_is_finite(flux))) return
    ! Research arithmetic envelope, not meteorological acceptance limits.
    if (any(volume<1.e-100_real64).or.any(volume>1.e100_real64)) return
    if (any(abs(flux)>1.e100_real64)) return
    do f=1,size(flux)
      if (plus(f)>0) divergence(plus(f))=divergence(plus(f))+flux(f)
      if (minus(f)>0) divergence(minus(f))=divergence(minus(f))-flux(f)
    end do
    divergence=divergence/volume
    ok=.true.
  end subroutine

  ! G=-K B^T: the adjoint uses cell inner product diag(volume), face Euclidean
  ! inner product. K=0 freezes a face. Exterior multiplier is zero ONLY for
  ! explicitly permitted boundary corrections; callers freeze all others.
  ! Form A by calling flux_divergence on this result, never another stencil.
  subroutine multiplier_flux(lambda,plus,minus,mobility,flux,ok)
    real(real64), intent(in) :: lambda(:),mobility(:)
    integer, intent(in) :: plus(:),minus(:)
    real(real64), intent(out) :: flux(:)
    logical, intent(out) :: ok
    real(real64) :: jump
    integer :: f
    flux=0; ok=.false.
    if (size(flux)/=size(mobility)) return
    if (.not.valid_faces(size(lambda),plus,minus,size(flux))) return
    if (.not.all(ieee_is_finite(lambda)).or..not.all(ieee_is_finite(mobility))) return
    if (any(abs(lambda)>1.e100_real64)) return
    if (any(mobility<0).or.any(mobility>1.e100_real64)) return
    do f=1,size(flux)
      jump=0
      if (plus(f)>0) jump=jump+lambda(plus(f))
      if (minus(f)>0) jump=jump-lambda(minus(f))
      flux(f)=-mobility(f)*jump
    end do
    ok=.true.
  end subroutine

  logical function valid_faces(n,plus,minus,nface) result(ok)
    integer, intent(in) :: n,nface,plus(:),minus(:)
    ok=.false.
    if (n<1.or.size(plus)/=nface.or.size(minus)/=nface) return
    if (any(plus<0).or.any(plus>n).or.any(minus<0).or.any(minus>n)) return
    if (any(plus==minus)) return
    ok=.true.
  end function
end module
