program test_qbal_physical_boundary
  use iso_fortran_env, only: real64,int64
  use ieee_arithmetic, only: ieee_value,ieee_quiet_nan
  use qbal_physical_boundary
  implicit none
  real(real64) :: p(4),op(4),spacing(3),part,h(3),w(4),dp(3)
  real(real64) :: total,lateral,ends,error,bound,tendency,nan
  integer :: status,q,failures
  failures=0; nan=ieee_value(0._real64,ieee_quiet_nan)
  p=[100000._real64,90000._real64,80000._real64,70000._real64]
  call legacy_pressure_geometry(p,op,spacing,status)
  call check(status==STATUS_OK.and.all(op==[95000._real64,85000._real64,75000._real64,70000._real64]),'stagger')
  call check(all(spacing==[10000._real64,10000._real64,5000._real64]),'finite top half width')
  call production_stagger_probe(p,op)
  call production_incidence_probe()
  call surface_layer(p,92000._real64,q,part,status)
  call check(status==STATUS_OK.and.q==2.and.part==7000,'partial thickness')
  call surface_layer(p,98000._real64,q,part,status)
  call check(status==STATUS_OK.and.q==2.and.part==13000,'surface above midpoint, no clipping')
  call surface_layer(p,90000._real64,q,part,status)
  call check(status==STATUS_OK.and.q==2.and.part==5000,'exact level equality')
  call surface_layer(p,70001._real64,q,part,status)
  call check(status==STATUS_OK.and.q==4.and.part==1._real64,'last interval lower endpoint')
  call surface_layer(p,75000._real64,q,part,status)
  call check(status==STATUS_OK.and.q==4.and.part==5000._real64,'last interval upper endpoint')
  call surface_layer(p,nan,q,part,status)
  call check(status/=STATUS_OK,'nan pressure refusal')
  p(2)=p(1)
  call legacy_pressure_geometry(p,op,spacing,status)
  call check(status/=STATUS_OK,'duplicate pressure refusal')
  h=[2.e-4_real64,-3.e-4_real64,1.e-4_real64]
  w=[1._real64,3._real64,-2._real64,4._real64]; dp=10000
  call column_telescope(h,w,dp,[.true.,.true.,.true.],total,lateral,ends,error,bound,status)
  call check(status==STATUS_OK.and.abs(error)<=bound,'full telescope')
  call check(abs(ends+3)<1.e-12_real64,'endpoint sign')
  call column_telescope(h,w,dp,[.true.,.false.,.true.],total,lateral,ends,error,bound,status)
  call check(status==STATUS_OK.and.abs(error)<=bound.and.abs(ends+8)<1.e-12_real64,'gap endpoints')
  call column_telescope(h,w,dp,[.false.,.false.,.false.],total,lateral,ends,error,bound,status)
  call check(status==STATUS_OK.and.total==0.and.ends==0,'empty coverage is reported')
  call pressure_secant(100000._real64,100072._real64,0_int64,7200_int64,.true.,tendency,status)
  call check(status==STATUS_OK.and.abs(tendency-.01_real64)<1.e-15_real64,'retrospective secant')
  call pressure_secant(100000._real64,100072._real64,0_int64,7200_int64,.false.,tendency,status)
  call check(status/=STATUS_OK,'unknown delivery refusal')
  call pressure_secant(nan,100072._real64,0_int64,7200_int64,.true.,tendency,status)
  call check(status/=STATUS_OK,'nan secant refusal')
  call check(abs(surface_residual(7._real64,2._real64,3._real64,1._real64,1._real64,2._real64))<1.e-12_real64, &
             'surface pressure advection')
  call check(abs(physical_column_residual(2._real64,5._real64,7._real64))<1.e-12_real64,'column top sign')
  if (failures/=0) error stop 'physical boundary diagnostic tests failed'
  print *, 'physical boundary diagnostic tests passed: 20 checks'
contains
  subroutine production_incidence_probe()
    real :: u(3,3,4),v(3,3,4),w(3,3,4),dx(3,3),dy(3,3),dp(4)
    real(real64),external :: qbal_divergence_value
    real(real64) :: lower,upper
    u=0; v=0; w=0; dx=1; dy=1; dp=1
    w(2,2,2)=1
    lower=qbal_divergence_value(u,v,w,3,3,4,dx,dy,dp,2,2,2)
    upper=qbal_divergence_value(u,v,w,3,3,4,dx,dy,dp,2,2,3)
    call check(lower==-1._real64.and.upper==1._real64,'production D incidence is minus/plus')
  end subroutine
  subroutine production_stagger_probe(pressure,expected)
    real(real64),intent(in)::pressure(4),expected(4)
    real :: a(3,3,4),omega(3,3,4),us(3,3,4),vs(3,3,4),phis(3,3,4)
    real :: ts(3,3,4),shs(3,3,4),oms(3,3,4),pp(4),ps(3,3)
    integer :: k
    external :: balstagger
    a=0; ps=110000; pp=real(pressure)
    do k=1,4
      omega(:,:,k)=pp(k)
    end do
    call balstagger(a,a,a,a,a,omega,us,vs,phis,ts,shs,oms,3,3,4,pp,ps,1)
    call check(all(real(oms(2,2,:),real64)==expected),'exact production affine omega placement')
  end subroutine
  subroutine check(ok,label)
    logical,intent(in)::ok
    character(*),intent(in)::label
    if (.not.ok) then
      print *, 'FAIL: ',label
      failures=failures+1
    end if
  end subroutine
end program
