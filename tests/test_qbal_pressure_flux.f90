program test_qbal_pressure_flux
  use iso_fortran_env, only: real64
  use ieee_arithmetic, only: ieee_value,ieee_quiet_nan
  use qbal_pressure_flux
  use cloud_bal_grid_geometry, only: pressure_face_segment,partition_pressure_face
  implicit none
  real(real64) :: p(4),nan,integral
  real(real64), allocatable :: interfaces(:),neighbor(:)
  logical :: ok
  integer :: checks=0
  p=[100000._real64,90000._real64,75000._real64,5000._real64]
  nan=ieee_value(0._real64,ieee_quiet_nan)
  call pressure_interfaces(p,97000._real64,interfaces,ok)
  call check(ok,'interfaces accepted')
  call check(all(interfaces==[97000._real64,82500._real64,40000._real64,5000._real64]),'actual partial and finite top')
  call vertical_identity(interfaces)
  call balanced_profile(interfaces)
  call pressure_interfaces(p,6000._real64,neighbor,ok)
  call check(ok.and.size(neighbor)==2,'last interval is one cell')
  call check(all(neighbor==[6000._real64,5000._real64]),'last interval endpoints')
  call vertical_identity(neighbor)
  call pressure_interfaces(p,5000._real64,neighbor,ok)
  call check(.not.ok,'zero depth rejected')
  call pressure_interfaces(p,nan,neighbor,ok)
  call check(.not.ok,'NaN surface rejected')
  call integrate_pressure_profile(p,p,110000._real64,5000._real64,integral,ok)
  call check(.not.ok,'profile extrapolation rejected')
  call integrate_pressure_profile(p,[nan,0._real64,0._real64,0._real64],90000._real64,5000._real64,integral,ok)
  call check(.not.ok,'NaN profile rejected safely')
  call shared_faces()
  call adjoint_identity()
  call sloping_column()
  print '(a,i0)', 'pressure flux checks passed: ',checks
contains
  subroutine check(condition,label)
    logical, intent(in) :: condition
    character(*), intent(in) :: label
    if (.not.condition) then
      print *, 'FAIL: ',label
      error stop 1
    end if
    checks=checks+1
  end subroutine

  subroutine vertical_identity(ip)
    real(real64), intent(in) :: ip(:)
    real(real64) :: vol(size(ip)-1),flux(size(ip)),div(size(ip)-1)
    integer :: plus(size(ip)),minus(size(ip)),n,k
    n=size(ip)-1;vol=ip(:n)-ip(2:)
    plus=0;minus=0
    ! Omega is positive toward increasing pressure: lower plus, upper minus.
    do k=1,n
      plus(k)=k;minus(k+1)=k
    end do
    flux=1.e-4_real64*ip+2._real64
    call flux_divergence(vol,plus,minus,flux,div,ok)
    call check(ok.and.maxval(abs(div-1.e-4_real64))<1.e-18_real64,'affine omega on nonuniform full/partial/top cells')
  end subroutine

  subroutine balanced_profile(ip)
    real(real64), intent(in) :: ip(:)
    real(real64) :: lateral,vertical,endpoint_residual
    integer :: k
    do k=1,size(ip)-1
      call integrate_pressure_profile(p,1.e-9_real64*p,ip(k),ip(k+1),lateral,ok)
      vertical=-.5e-9_real64*(ip(k)**2-ip(k+1)**2)
      call check(ok.and.abs(lateral+vertical)<1.e-14_real64,'layer-integrated affine h balances quadratic omega')
    end do
    endpoint_residual=1.e-9_real64*ip(size(ip)) &
      -.5e-9_real64*(ip(size(ip)-1)+ip(size(ip)))
    call check(abs(endpoint_residual)>1.e-6_real64,'endpoint horizontal value is not the layer mean')
  end subroutine

  subroutine shared_faces()
    type(pressure_face_segment), allocatable :: seg(:)
    real(real64), allocatable :: l(:),r(:),vol(:),flux(:),div(:)
    integer, allocatable :: plus(:),minus(:)
    real(real64) :: bottom,top,transport
    integer :: nl,nr,s,a,b
    call pressure_interfaces(p,97000._real64,l,ok)
    call check(ok,'left shared column')
    call pressure_interfaces(p,79000._real64,r,ok)
    call check(ok,'right shared column')
    call partition_pressure_face(l,r,seg,ok)
    call check(ok.and.size(seg)==2,'existing overlap partitioner')
    nl=size(l)-1;nr=size(r)-1
    allocate(vol(nl+nr),div(nl+nr),flux(size(seg)),plus(size(seg)),minus(size(seg)))
    vol=[2._real64*(l(:nl)-l(2:)),3._real64*(r(:nr)-r(2:))]
    do s=1,size(seg)
      a=seg(s)%left_level;b=seg(s)%right_level
      bottom=min(l(a),r(b));top=max(l(a+1),r(b+1))
      call integrate_pressure_profile(p,2._real64+1.e-5_real64*p,bottom,top,transport,ok)
      call check(ok,'shared integrated wind profile')
      plus(s)=a;minus(s)=nl+b;flux(s)=4._real64*transport
    end do
    call flux_divergence(vol,plus,minus,flux,div,ok)
    call check(ok.and.abs(sum(vol*div))<1.e-9_real64,'one shared flux cancels on unequal cell volumes')
    ! Equal inflow/outflow on a uniform column creates no divergence.
    call flux_divergence([5000._real64],[1,0],[0,1],[35000._real64,35000._real64],div(:1),ok)
    call check(ok.and.div(1)==0,'constant horizontal wind uniform geometry')
  end subroutine

  subroutine adjoint_identity()
    integer :: plus(4),minus(4)
    real(real64) :: vol(3),x(3),y(3),mob(4),f(4),g(4),a(3),d(3),b(3,4),expected(3)
    plus=[1,1,2,3];minus=[0,2,3,0]
    vol=[2._real64,3._real64,7._real64];x=[1._real64,-2._real64,4._real64]
    mob=[0._real64,2._real64,3._real64,0._real64];f=[5._real64,-2._real64,7._real64,3._real64]
    b(:,1)=[1._real64,0._real64,0._real64]
    b(:,2)=[1._real64,-1._real64,0._real64]
    b(:,3)=[0._real64,1._real64,-1._real64]
    b(:,4)=[0._real64,0._real64,1._real64]
    call multiplier_flux(x,plus,minus,mob,g,ok)
    call check(ok.and.g(1)==0.and.g(4)==0,'unapproved boundary corrections frozen')
    call flux_divergence(vol,plus,minus,g,a,ok)
    expected=matmul(b,-mob*matmul(transpose(b),x))/vol
    call check(ok.and.maxval(abs(a-expected))<1.e-14_real64,'D(G) equals independent dense incidence normal operator')
    call check(abs(sum(x*vol*a)+sum(mob*matmul(transpose(b),x)**2))<1.e-12_real64,'weighted negative energy')
    call flux_divergence(vol,plus,minus,f,d,ok)
    call check(ok.and.abs(sum(x*vol*d)-sum(matmul(transpose(b),x)*f))<1.e-12_real64,'volume-weighted adjoint with exterior faces')
    y=1
    call multiplier_flux(y,plus,minus,mob,g,ok)
    call check(ok.and.all(g==0),'closed component constant gauge')
    call flux_divergence(vol,[4,1,2,3],minus,f,d,ok)
    call check(.not.ok.and.all(d==0),'invalid incident cell fails closed')
    call flux_divergence([nan,3._real64,7._real64],plus,minus,f,d,ok)
    call check(.not.ok.and.all(d==0),'NaN volume fails closed')
  end subroutine

  subroutine sloping_column()
    real(real64) :: area,ps_t,wind,gradient,omega_s,omega_t,lateral,flux(3),div(1)
    area=2;ps_t=.03_real64;wind=4;gradient=.02_real64
    omega_s=ps_t+wind*gradient;omega_t=omega_s
    ! Constant wind, PS linear in x: div(integral(v dp))=wind*grad(PS).
    lateral=area*wind*gradient
    flux=[area*ps_t,lateral,area*omega_t]
    call flux_divergence([area*90000._real64],[1,1,0],[0,0,1],flux,div,ok)
    call check(ok.and.abs(div(1))<1.e-20_real64,'sloping time-dependent surface normal and column budget')
    flux(1)=area*omega_s
    call flux_divergence([area*90000._real64],[1,1,0],[0,0,1],flux,div,ok)
    call check(ok.and.abs(div(1)-wind*gradient/90000._real64)<1.e-20_real64,'raw surface omega would double count advection')
  end subroutine
end program
