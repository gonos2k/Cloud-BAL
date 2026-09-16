subroutine test_qbal_reverse_output()
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  implicit none
  integer, parameter :: nx=8,ny=8,nz=6
  real, parameter :: rd=287.04, t0=280., q0=1.e-3, om0=2., dx0=1.e4, a=1.e-3
  real, parameter :: du=0.35, dv=-0.45, dphi=125., dsh=0.004, domega=0.1
  real :: lu(nx,ny,nz),lv(nx,ny,nz),lp(nx,ny,nz),lt(nx,ny,nz),lh(nx,ny,nz),lo(nx,ny,nz)
  real :: u(nx,ny,nz),v(nx,ny,nz),phi(nx,ny,nz),t(nx,ny,nz),sh(nx,ny,nz),om(nx,ny,nz)
  real :: us(nx,ny,nz),vs(nx,ny,nz),phis(nx,ny,nz),ts(nx,ny,nz),shs(nx,ny,nz),oms(nx,ny,nz)
  real :: p(nz),ps(nx,ny),dx(nx,ny),dy(nx,ny),ur,vr,orr,pr,qr,rmax,rms
  real :: expected_residual,expected_rms
  integer :: i,j,k
  external :: balstagger, qbal_agrid_residual, report_qbal_agrid_residual

  p=[100000.,90000.,80000.,70000.,60000.,50000.]; ps=110000.; dx=dx0; dy=dx0
  do k=1,nz; do j=1,ny; do i=1,nx
    lu(i,j,k)=a*dx0*real(i-1); lv(i,j,k)=-a*dx0*real(j-1)
    lp(i,j,k)=rd*t0*alog(p(1)/p(k)); lt(i,j,k)=t0; lh(i,j,k)=q0; lo(i,j,k)=om0
  enddo; enddo; enddo
  call balstagger(lu,lv,lp,lt,lh,lo,us,vs,phis,ts,shs,oms,nx,ny,nz,p,ps,1)

  ! Keep the original A-grid fields as the in-place reverse input.  Modify
  ! only the finite staggered payload, so a reverse no-op leaves a measurable
  ! difference at every checked field.  Affine U/V and constant PHI/SH make
  ! the reverse averages exact: U=lu+du, V=lv+dv, PHI=lp+dphi, SH=lh+dsh.
  us=us+du; vs=vs+dv; phis=phis+dphi; shs=shs+dsh
  oms=oms+domega
  u=lu; v=lv; phi=lp; t=lt; sh=lh; om=lo
  call balstagger(u,v,phi,t,sh,om,us,vs,phis,ts,shs,oms,nx,ny,nz,p,ps,-1)
  if(any(.not.ieee_is_finite(u)).or.any(.not.ieee_is_finite(v)).or. &
     any(.not.ieee_is_finite(phi)).or.any(.not.ieee_is_finite(t)).or. &
     any(.not.ieee_is_finite(sh)).or.any(.not.ieee_is_finite(om))) &
    error stop 'reverse A-grid output is nonfinite'
  ur=maxval(abs(u(2:nx,2:ny,2:nz)-(lu(2:nx,2:ny,2:nz)+du)))
  vr=maxval(abs(v(2:nx,2:ny,2:nz)-(lv(2:nx,2:ny,2:nz)+dv)))
  orr=maxval(abs(om(2:nx,2:ny,2:nz)-(lo(2:nx,2:ny,2:nz)+domega)))
  pr=maxval(abs(phi(2:nx,2:ny,2:nz)-(lp(2:nx,2:ny,2:nz)+dphi)))
  qr=maxval(abs(sh(2:nx,2:ny,2:nz)-(lh(2:nx,2:ny,2:nz)+dsh)))
  if(ur>2.e-5.or.vr>2.e-5.or.orr>2.e-5.or.pr>5.e-3.or.qr>2.e-6) &
    error stop 'reverse A-grid manufactured oracle failed'
  call qbal_agrid_residual(u,v,om,nx,ny,nz,p,dx,dy,rmax,rms)
  ! The changed interior omega is constant, but level 1 remains the original
  ! A-grid background.  Only k=2 sees that interface in the centered stencil:
  ! rmax=domega/(p(1)-p(3)), and rms=rmax/sqrt(nz-2).
  expected_residual=domega/(p(1)-p(3))
  expected_rms=expected_residual/sqrt(real(nz-2))
  if(abs(rmax-expected_residual)>2.e-8.or.abs(rms-expected_rms)>2.e-8) &
    error stop 'A-grid centered manufactured residual oracle failed'
  call report_qbal_agrid_residual(u,v,om,nx,ny,nz,p,dx,dy)
  print *, 'Reverse balstagger manufactured A-grid oracle PASS: ',ur,vr,orr,pr,qr,rmax
end subroutine test_qbal_reverse_output

subroutine report_qbal_agrid_residual(lu,lv,lo,nx,ny,nz,p,dx,dy)
  implicit none
  integer, intent(in) :: nx,ny,nz
  real, intent(in) :: lu(nx,ny,nz),lv(nx,ny,nz),lo(nx,ny,nz),p(nz),dx(nx,ny),dy(nx,ny)
  real :: maxres,rms
  external :: qbal_agrid_residual
  call qbal_agrid_residual(lu,lv,lo,nx,ny,nz,p,dx,dy,maxres,rms)
  print *, 'A-grid centered divergence RMS/max (valid interior): ',rms,maxres
end subroutine report_qbal_agrid_residual

subroutine qbal_agrid_residual(lu,lv,lo,nx,ny,nz,p,dx,dy,maxres,rms)
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  implicit none
  integer, intent(in) :: nx,ny,nz
  real, intent(in) :: lu(nx,ny,nz),lv(nx,ny,nz),lo(nx,ny,nz),p(nz),dx(nx,ny),dy(nx,ny)
  real, intent(out) :: maxres,rms
  integer :: i,j,k,n
  real :: residual,dp2
  real(8) :: sum2
  ! This is an independent diagnostic for uniform Cartesian spacing and
  ! uniformly spaced pressure levels; it is not a general output operator.
  maxres=0.; rms=0.; sum2=0.d0; n=0
  ! Centered A-grid cells have i=2:nx-1, j=2:ny-1, k=2:nz-1.
  do k=2,nz-1; dp2=p(k-1)-p(k+1)
    if(.not.ieee_is_finite(dp2).or.dp2<=0.) error stop 'invalid A-grid pressure spacing'
    do j=2,ny-1; do i=2,nx-1
      if(.not.ieee_is_finite(dx(i,j)).or..not.ieee_is_finite(dy(i,j)).or. &
         dx(i,j)<=0..or.dy(i,j)<=0.)then
        error stop 'invalid A-grid horizontal spacing'
      endif
      residual=(lu(i+1,j,k)-lu(i-1,j,k))/(2.*dx(i,j)) &
       +(lv(i,j+1,k)-lv(i,j-1,k))/(2.*dy(i,j)) &
       +(lo(i,j,k-1)-lo(i,j,k+1))/dp2
      if(.not.ieee_is_finite(residual)) error stop 'nonfinite A-grid residual'
      maxres=max(maxres,abs(residual)); sum2=sum2+dble(residual)**2; n=n+1
    enddo; enddo
  enddo
  if(n>0) rms=real(sqrt(sum2/dble(n)))
end subroutine qbal_agrid_residual
