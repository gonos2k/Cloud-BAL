program test_qbal_nonlin
  use, intrinsic :: ieee_arithmetic, only: ieee_value, ieee_quiet_nan
  implicit none
  integer :: failures
  external :: nonlin, qbal_omega_face_delta

  failures=0
  call stencil_case(.false.,failures)
  call stencil_case(.true.,failures)
  call pressure_affine(failures)
  call vertical_cases(failures)
  call heterogeneous_case(failures)
  call invalid_cases(failures)
  if (failures /= 0) error stop 'QBAL nonlinear tests failed'
  print *,'QBAL nonlinear tests passed'

contains

  subroutine stencil_case(nonuniform,failures)
    logical, intent(in) :: nonuniform
    integer, intent(inout) :: failures
    real :: nu(4,4,4),nv(4,4,4),u(4,4,4),v(4,4,4)
    real :: ub(4,4,4),vb(4,4,4),om(4,4,4),omb(4,4,4)
    real :: dx(4,4),dy(4,4),dp(4),u0(4,4,4),v0(4,4,4)
    real :: ub0(4,4,4),vb0(4,4,4),om0(4,4,4),omb0(4,4,4)
    real :: dx0(4,4),dy0(4,4),dp0(4),expected_u,expected_v
    real :: bnd,rod,dt
    integer :: i,j,k,status

    do k=1,4; do j=1,4; do i=1,4
      u(i,j,k)=1.+i+2.*j+3.*k
      ub(i,j,k)=2.+4.*i-j+2.*k
      v(i,j,k)=-1.+2.*i-j+4.*k
      vb(i,j,k)=3.-i+3.*j-2.*k
      om(i,j,k)=5.+i+2.*j+k
      omb(i,j,k)=1.-i+j+2.*k
    end do; end do; end do
    dx=1.; dy=1.; dp=1.; bnd=1.e-30; rod=1.; dt=1.
    if (nonuniform) then
      dx(2,2)=2.; dy(2,2)=4.; dp=[1.,2.,6.,5.]
    end if
    u0=u; v0=v; ub0=ub; vb0=vb; om0=om; omb0=omb
    dx0=dx; dy0=dy; dp0=dp
    call nonlin(nu,nv,u,v,ub,vb,om,omb,4,4,4,dx,dy,dp,dt,bnd,rod,status)
    call check(status==1,'stencil status',failures)
    if (.not.nonuniform) then
      expected_u=28.; expected_v=38.5
    else
      expected_u=23.; expected_v=13.75
    end if
    call check(abs(nu(2,2,2)-expected_u)<1.e-5,'stencil U value',failures)
    call check(abs(nv(2,2,2)-expected_v)<1.e-5,'stencil V value',failures)
    call check(all(u==u0).and.all(v==v0).and.all(ub==ub0).and.all(vb==vb0) &
         .and.all(om==om0).and.all(omb==omb0).and.all(dx==dx0).and.all(dy==dy0) &
         .and.all(dp==dp0),'nonlin leaves input arrays unchanged',failures)
  end subroutine stencil_case

  subroutine pressure_affine(failures)
    integer, intent(inout) :: failures
    real :: nu(4,4,4),nv(4,4,4),u(4,4,4),v(4,4,4)
    real :: ub(4,4,4),vb(4,4,4),om(4,4,4),omb(4,4,4)
    real :: dx(4,4),dy(4,4),dp(4),p(4)
    integer :: grid,term,k,status
    do grid=1,2
      p=[100000.,90000.,80000.,70000.]
      if(grid==2) p=[100000.,90000.,85000.,70000.]
      do term=1,2
        call blank(u,v,ub,vb,om,omb,dx,dy,dp)
        dp(2:4)=p(1:3)-p(2:4)
        do k=1,4
          if(term==1) then
            u(:,:,k)=1.e-4*p(k)+2.
            v(:,:,k)=-2.e-4*p(k)+3.
          else
            ub(:,:,k)=1.e-4*p(k)+2.
            vb(:,:,k)=-2.e-4*p(k)+3.
          endif
        enddo
        om=0.5
        if(term==1) omb=om
        call nonlin(nu,nv,u,v,ub,vb,om,omb,4,4,4,dx,dy,dp, &
                    1.,1.e-30,1.,status)
        call check(status==1,'pressure affine status',failures)
        call check(abs(nu(2,2,2)-5.e-5)<1.e-9,'pressure affine U',failures)
        call check(abs(nv(2,2,2)+1.e-4)<1.e-9,'pressure affine V',failures)
      enddo
    enddo
  end subroutine pressure_affine

  subroutine vertical_cases(failures)
    integer, intent(inout) :: failures
    real :: nu(4,4,4),nv(4,4,4),u(4,4,4),v(4,4,4)
    real :: ub(4,4,4),vb(4,4,4),om(4,4,4),omb(4,4,4)
    real :: dx(4,4),dy(4,4),dp(4),bnd,rod,dt
    integer :: kind,status
    do kind=0,4
      u=0.; v=0.; ub=0.; vb=0.; om=0.; omb=0.
      dx=1.; dy=1.; dp=1.; bnd=1.e-30; rod=1.; dt=1.
      select case(kind)
      case(0); ub=3.; vb=-2.; omb=4.; om=omb; om=4.
      case(1); omb=2.; om=omb; om=2.; u(2,2,1)=1.; u(2,2,3)=3.
      case(2); om=2.; ub(2,2,1)=1.; ub(2,2,3)=3.
      case(3); omb=2.; om=omb; om=2.; v(2,2,1)=1.; v(2,2,3)=3.
      case(4); om=2.; vb(2,2,1)=1.; vb(2,2,3)=3.
      end select
      call nonlin(nu,nv,u,v,ub,vb,om,omb,4,4,4,dx,dy,dp,dt,bnd,rod,status)
      call check(status==1,'vertical status',failures)
      if (kind==0) then
        call check(abs(nu(2,2,2))+abs(nv(2,2,2))<1.e-6, &
             'zero perturbations with nonzero background',failures)
      else if (kind<=2) then
        call check(abs(nu(2,2,2)+2.)<1.e-6,'U vertical term sign/value',failures)
        call check(abs(nv(2,2,2))<1.e-6,'U vertical term isolates',failures)
      else
        call check(abs(nv(2,2,2)+2.)<1.e-6,'V vertical term sign/value',failures)
        call check(abs(nu(2,2,2))<1.e-6,'V vertical term isolates',failures)
      end if
    end do
  end subroutine vertical_cases

  subroutine heterogeneous_case(failures)
    integer, intent(inout) :: failures
    real :: total(2,2),background(2,2),delta,background_face
    real :: nu(4,4,4),nv(4,4,4),u(4,4,4),v(4,4,4)
    real :: ub(4,4,4),vb(4,4,4),om(4,4,4),omb(4,4,4)
    real :: dx(4,4),dy(4,4),dp(4),bnd,rod,dt
    integer :: status
    total=reshape([10.,20.,30.,40.],[2,2])
    background=reshape([1.,3.,5.,7.],[2,2])
    call qbal_omega_face_delta(total,background,delta,background_face,status)
    call check(status==1.and.abs(delta-21.)<1.e-6.and.abs(background_face-4.)<1.e-6, &
         'heterogeneous donor averages',failures)
    u=0.; v=0.; ub=0.; vb=0.; om=0.; omb=0.; dx=1.; dy=1.; dp=1.
    om(2,3,2:3)=[10.,30.]; om(3,3,2:3)=[20.,40.]
    omb(2,3,2:3)=[1.,5.]; omb(3,3,2:3)=[3.,7.]
    ub(2,2,1)=0.; ub(2,2,3)=2.; bnd=1.e-30; rod=1.; dt=1.
    call nonlin(nu,nv,u,v,ub,vb,om,omb,4,4,4,dx,dy,dp,dt,bnd,rod,status)
    call check(status==1.and.abs(nu(2,2,2)+21.)<1.e-6, &
         'heterogeneous donor reaches U term',failures)
  end subroutine heterogeneous_case

  subroutine invalid_cases(failures)
    integer, intent(inout) :: failures
    real :: nu(4,4,4),nv(4,4,4),u(4,4,4),v(4,4,4)
    real :: ub(4,4,4),vb(4,4,4),om(4,4,4),omb(4,4,4)
    real :: dx(4,4),dy(4,4),dp(4),bnd,rod,dt,nan_value
    integer :: status
    nan_value=ieee_value(0.,ieee_quiet_nan)
    bnd=1.e-30; rod=1.; dt=1.
    call blank(u,v,ub,vb,om,omb,dx,dy,dp)
    om(2,3,2)=nan_value
    call nonlin(nu,nv,u,v,ub,vb,om,omb,4,4,4,dx,dy,dp,dt,bnd,rod,status)
    call check(status==0,'NaN total U donor rejects',failures)
    call blank(u,v,ub,vb,om,omb,dx,dy,dp); omb(2,3,2)=nan_value
    call nonlin(nu,nv,u,v,ub,vb,om,omb,4,4,4,dx,dy,dp,dt,bnd,rod,status)
    call check(status==0,'NaN background U donor rejects',failures)
    call blank(u,v,ub,vb,om,omb,dx,dy,dp); om(3,2,2)=nan_value
    call nonlin(nu,nv,u,v,ub,vb,om,omb,4,4,4,dx,dy,dp,dt,bnd,rod,status)
    call check(status==0,'NaN total V donor rejects',failures)
    call blank(u,v,ub,vb,om,omb,dx,dy,dp); omb(3,2,2)=nan_value
    call nonlin(nu,nv,u,v,ub,vb,om,omb,4,4,4,dx,dy,dp,dt,bnd,rod,status)
    call check(status==0,'NaN background V donor rejects',failures)
    call blank(u,v,ub,vb,om,omb,dx,dy,dp); u=bnd; v=bnd; om(2,3,2)=nan_value
    call nonlin(nu,nv,u,v,ub,vb,om,omb,4,4,4,dx,dy,dp,dt,bnd,rod,status)
    call check(status==1,'U terrain sentinel permits skipped donor',failures)
    call blank(u,v,ub,vb,om,omb,dx,dy,dp); u=bnd; v=bnd; om(3,2,2)=nan_value
    call nonlin(nu,nv,u,v,ub,vb,om,omb,4,4,4,dx,dy,dp,dt,bnd,rod,status)
    call check(status==1,'V terrain sentinel permits skipped donor',failures)
  end subroutine invalid_cases

  subroutine blank(u,v,ub,vb,om,omb,dx,dy,dp)
    real, intent(out) :: u(4,4,4),v(4,4,4),ub(4,4,4),vb(4,4,4)
    real, intent(out) :: om(4,4,4),omb(4,4,4),dx(4,4),dy(4,4),dp(4)
    u=0.; v=0.; ub=0.; vb=0.; om=0.; omb=0.; dx=1.; dy=1.; dp=1.
  end subroutine blank

  subroutine check(condition,message,failures)
    logical, intent(in) :: condition
    character(len=*), intent(in) :: message
    integer, intent(inout) :: failures
    if (.not.condition) then
      failures=failures+1
      print *,'FAIL: ',trim(message)
    end if
  end subroutine check

end program test_qbal_nonlin
