program test_qbal_stagger_nonlin
  implicit none
  integer, parameter :: nx=4, ny=4, nz=4
  integer :: failures
  real :: p(nz)
  external :: balstagger, nonlin

  failures=0
  p=[100000.,90000.,80000.,70000.]
  call pressure_case(p,failures)
  p=[100000.,90000.,85000.,70000.]
  call pressure_case(p,failures)
  if (failures /= 0) error stop 'QBAL stagger/nonlin tests failed'
  print *,'QBAL stagger/nonlin tests passed'

contains

  subroutine pressure_case(p,failures)
    real, intent(in) :: p(nz)
    integer, intent(inout) :: failures
    real :: u(nx,ny,nz),v(nx,ny,nz),om(nx,ny,nz)
    real :: ub(nx,ny,nz),vb(nx,ny,nz),omb(nx,ny,nz)
    real :: us(nx,ny,nz),vs(nx,ny,nz),oms(nx,ny,nz)
    real :: ubs(nx,ny,nz),vbs(nx,ny,nz),ombs(nx,ny,nz)
    real :: wind_p(nz-1),p0(nz),dx(nx,ny),dy(nx,ny),ps(nx,ny)
    real :: nu(nx,ny,nz),nv(nx,ny,nz)
    real :: bnd,dt,rod
    integer :: status,k

    dx=1.; dy=1.; ps=110000.; wind_p=p(2:nz); p0=p
    bnd=1.e-30; dt=1.; rod=1.

    ! Perturbation vertical advection: omega_b*ddu/dp and omega_b*ddv/dp.
    u=0.; v=0.; ub=0.; vb=0.; om=2.; omb=2.
    do k=1,nz
      u(:,:,k)=2.e-4*p(k)+1.
      v(:,:,k)=-3.e-4*p(k)+2.
    enddo
    call stage_fields(u,v,om,ub,vb,omb,us,vs,oms,ubs,vbs,ombs,p,ps)
    call nonlin(nu,nv,us,vs,ubs,vbs,oms,ombs,nx,ny,nz,dx,dy,wind_p, &
                dt,bnd,rod,status)
    call check(status==1,'perturbation pressure status',failures)
    do k=2,nz-1
      call check(abs(nu(2,2,k)-4.e-4)<2.e-8,'omega_b*ddu/dp',failures)
      call check(abs(nv(2,2,k)+6.e-4)<2.e-8,'omega_b*ddv/dp',failures)
    enddo
    call check(all(p==p0),'balstagger preserves original pressure',failures)

    ! Background vertical advection: domega*dub/dp and domega*dvb/dp.
    u=0.; v=0.; ub=0.; vb=0.; om=2.5; omb=2.
    do k=1,nz
      ub(:,:,k)=1.e-4*p(k)+3.
      vb(:,:,k)=-2.e-4*p(k)-4.
    enddo
    call stage_fields(u,v,om,ub,vb,omb,us,vs,oms,ubs,vbs,ombs,p,ps)
    call nonlin(nu,nv,us,vs,ubs,vbs,oms,ombs,nx,ny,nz,dx,dy,wind_p, &
                dt,bnd,rod,status)
    call check(status==1,'background pressure status',failures)
    do k=2,nz-1
      call check(abs(nu(2,2,k)-5.e-5)<2.e-8,'domega*dub/dp',failures)
      call check(abs(nv(2,2,k)+1.e-4)<2.e-8,'domega*dvb/dp',failures)
    enddo

    ! The nz wind plane is a duplicate.  Poisoning it must not alter active rows.
    u=0.; v=0.; ub=0.; vb=0.; om=2.; omb=2.
    call stage_fields(u,v,om,ub,vb,omb,us,vs,oms,ubs,vbs,ombs,p,ps)
    us(:,:,nz)=1.e6; vs(:,:,nz)=-1.e6
    ubs(:,:,nz)=-1.e6; vbs(:,:,nz)=1.e6
    call nonlin(nu,nv,us,vs,ubs,vbs,oms,ombs,nx,ny,nz,dx,dy,wind_p, &
                dt,bnd,rod,status)
    call check(status==1,'duplicate-top zero status',failures)
    do k=2,nz-1
      call check(abs(nu(2,2,k))+abs(nv(2,2,k))<2.e-8, &
                 'duplicate-top zero winds ignored',failures)
    enddo
  end subroutine pressure_case

  subroutine stage_fields(u,v,om,ub,vb,omb,us,vs,oms,ubs,vbs,ombs,p,ps)
    real, intent(in) :: u(nx,ny,nz),v(nx,ny,nz),om(nx,ny,nz)
    real, intent(in) :: ub(nx,ny,nz),vb(nx,ny,nz),omb(nx,ny,nz),p(nz)
    real, intent(in) :: ps(nx,ny)
    real, intent(out) :: us(nx,ny,nz),vs(nx,ny,nz),oms(nx,ny,nz)
    real, intent(out) :: ubs(nx,ny,nz),vbs(nx,ny,nz),ombs(nx,ny,nz)
    real :: phi(nx,ny,nz),t(nx,ny,nz),sh(nx,ny,nz)
    real :: phis(nx,ny,nz),ts(nx,ny,nz),shs(nx,ny,nz)
    real :: phib(nx,ny,nz),tb(nx,ny,nz),shb(nx,ny,nz)
    real :: phibs(nx,ny,nz),tbs(nx,ny,nz),shbs(nx,ny,nz)

    phi=0.; t=0.; sh=0.; phis=0.; ts=0.; shs=0.
    phib=0.; tb=0.; shb=0.
    call balstagger(u,v,phi,t,sh,om,us,vs,phis,ts,shs,oms, &
                    nx,ny,nz,p,ps,1)
    call balstagger(ub,vb,phib,tb,shb,omb,ubs,vbs,phibs,tbs,shbs,ombs, &
                    nx,ny,nz,p,ps,1)
  end subroutine stage_fields

  subroutine check(condition,message,failures)
    logical, intent(in) :: condition
    character(len=*), intent(in) :: message
    integer, intent(inout) :: failures
    if (.not.condition) then
      failures=failures+1
      print *,'FAIL: ',trim(message)
    endif
  end subroutine check

end program test_qbal_stagger_nonlin
