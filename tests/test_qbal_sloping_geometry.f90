program test_qbal_sloping_geometry
  use iso_fortran_env, only: real64
  use ieee_arithmetic, only: ieee_value,ieee_quiet_nan
  use qbal_sloping_geometry
  use qbal_pressure_flux, only: flux_divergence
  implicit none
  real(real64) :: xy(2,3),ps(3),m(3,5),moment(3,3,5),volume,identity(3,3),jac(3,3),moment_scale(3,3)
  real(real64) :: reverse_xy(2,3),reverse_ps(3),reverse_edge(2,2),reverse_surface(2),reverse_u(4,2)
  real(real64) :: coord(2),scale(2),moved(2),shift_scale(2),flux(5),div(1),constant(3),nan,p(4),u(4,2),v(4,2)
  real(real64) :: edge(2,2),surface(2),integral,missing,reversed,other_m(3,5),other_q(3,3,5),other_v
  logical :: ok
  integer :: k,f,checks
  checks=0;nan=ieee_value(0._real64,ieee_quiet_nan)
  call equal_area_point(.7_real64,2.2_real64,.6_real64,2._real64,6371000._real64,coord,scale,ok)
  call check(ok.and.abs(product(scale)-1)<1.e-15_real64,'equal-area velocity Jacobian')
  call check(abs(coord(1)-6371000._real64*cos(.6_real64)*.2_real64)<1.e-8_real64,'chart longitude metric')
  call equal_area_point(.7_real64+.1_real64*3/6371000, &
      2.2_real64+.1_real64*4/(6371000*cos(.7_real64)),.6_real64,2._real64,6371000._real64, &
      moved,shift_scale,ok)
  call check(ok.and.maxval(abs((moved-coord)/.1_real64-scale*[4._real64,3._real64]))<1.e-5_real64, &
             'chart rates match physical east north displacement')
  call equal_area_point(nan,2._real64,.6_real64,2._real64,6371000._real64,coord,scale,ok)
  call check(.not.ok,'NaN chart rejected')
  xy(:,1)=[0._real64,0._real64];xy(:,2)=[2000._real64,0._real64];xy(:,3)=[0._real64,3000._real64]
  ps=100000._real64+.2_real64*xy(1,:)-.15_real64*xy(2,:)
  call sloping_column_faces(xy,ps,5000._real64,m,moment,volume,ok)
  call check(ok,'sloping geometry built')
  call check(maxval(abs(m(:,1)-3.e6_real64*[-.2_real64,.15_real64,1._real64]))<1.e-6_real64, &
             'ground metric includes pressure slope')
  call check(abs(volume-3.e6_real64*(sum(ps)/3-5000))<1.e-3_real64,'independent wedge volume')
  call check(maxval(abs(sum(m,dim=2)))<1.e-6_real64,'each cell constant metric closure')
  identity=0
  do k=1,3
    identity(k,k)=volume
  end do
  moment_scale=sum(abs(moment),dim=3)+abs(identity)
  where (moment_scale==0) moment_scale=1
  call check(maxval(abs(sum(moment,dim=3)-identity)/moment_scale)<128*epsilon(volume), &
             'each cell affine geometric moments')
  constant=[4._real64,-2._real64,.03_real64]
  do f=1,5
    flux(f)=dot_product(constant,m(:,f))
  end do
  call flux_divergence([volume],[1,1,1,1,1],[0,0,0,0,0],flux,div,ok)
  call check(ok.and.abs(div(1))<1.e-17_real64,'constant field generated on actual faces')
  jac=reshape([1.e-5_real64,2.e-5_real64,3.e-5_real64, &
               4.e-5_real64,-2.e-5_real64,6.e-5_real64, &
               7.e-5_real64,8.e-5_real64,4.e-5_real64],[3,3])
  do f=1,5
    flux(f)=dot_product(constant,m(:,f))+sum(transpose(jac)*moment(:,:,f))
  end do
  call flux_divergence([volume],[1,1,1,1,1],[0,0,0,0,0],flux,div,ok)
  call check(ok.and.abs(div(1)-3.e-5_real64)<1.e-17_real64,'affine field generated on faces reproduces trace')
  xy(:,1)=[2000._real64,0._real64];xy(:,2)=[2000._real64,3000._real64];xy(:,3)=[0._real64,3000._real64]
  ps=100000._real64+.2_real64*xy(1,:)-.15_real64*xy(2,:)
  call sloping_column_faces(xy,ps,5000._real64,other_m,other_q,other_v,ok)
  call check(ok.and.maxval(abs(m(:,4)+other_m(:,5)))<1.e-6_real64,'two reconstructed cells share identical opposite metric')
  reverse_xy=xy(:,3:1:-1);reverse_ps=ps(3:1:-1)
  call sloping_column_faces(reverse_xy,reverse_ps,5000._real64,m,moment,volume,ok)
  call check(.not.ok,'clockwise cell rejected')
  p=[100000._real64,90000._real64,70000._real64,5000._real64]
  u(:,1)=1.e-4_real64*p;u(:,2)=2.e-4_real64*p;v=0
  edge(:,1)=[0._real64,0._real64];edge(:,2)=[0._real64,2._real64]
  surface=[95000._real64,75000._real64]
  call edge_wind_flux(edge,surface,5000._real64,p,u,v,integral,missing,ok)
  ! 2 * integral_0^1 .5e-4*(1+s)*((95000-20000s)^2-5000^2) ds.
  call check(ok.and.abs(integral-3170000._real64/3)<1.e-8_real64,'sloping edge profile polynomial crosses pressure knots')
  call check(missing==0,'full declared profile coverage')
  reverse_edge=edge(:,2:1:-1);reverse_surface=surface(2:1:-1);reverse_u=u(:,2:1:-1)
  call edge_wind_flux(reverse_edge,reverse_surface,5000._real64,p,reverse_u,v, &
                      reversed,missing,ok)
  call check(ok.and.abs(integral+reversed)<1.e-8_real64,'shared reconstructed wind flux reverses sign')
  call edge_wind_flux(edge,surface,5000._real64,p(2:),u(2:,:),v(2:,:),integral,missing,ok)
  call check(ok.and.abs(missing-625._real64)<1.e-10_real64,'uncovered triangular surface strip reported')
  call edge_wind_flux(edge,surface,5000._real64,p,0*u,0*v,integral,missing,ok)
  call check(ok.and.integral==0,'zero wind integrates zero')
  edge(:,2)=edge(:,1)
  call edge_wind_flux(edge,surface,5000._real64,p,u,v,integral,missing,ok)
  call check(.not.ok,'zero length edge rejected')
  print '(a,i0)', 'sloping geometry checks passed: ',checks
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
end program
