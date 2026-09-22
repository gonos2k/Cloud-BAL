program test_qbal_lower_transport
  use iso_fortran_env, only: real64
  use ieee_arithmetic, only: ieee_is_nan, ieee_value, ieee_quiet_nan
  use qbal_lower_transport
  implicit none
  integer :: checks
  real(real64) :: p(6),height(6),bad(6),sample,nan,p_sample,expected
  real(real64) :: xy(2,2),reverse_xy(2,2),pedge(2),reverse_pedge(2),flux,reverse_flux
  real(real64) :: wind_sample(2,2),wind_cap(2,2),reverse_sample(2,2),reverse_cap(2,2)
  real(real64) :: wind_next(2,2)
  logical :: ok

  checks=0
  nan=ieee_value(0._real64,ieee_quiet_nan)
  p=[110000._real64,105000._real64,100000._real64,90000._real64,81000._real64,72900._real64]
  height=[-100._real64,-50._real64,0._real64,100._real64,200._real64,300._real64]

  call pressure_at_height(100000._real64,0._real64,p,height,0._real64,p_sample,ok)
  call check(ok.and.abs(p_sample-100000._real64)<1.e-10_real64,'surface anchor')
  sample=50._real64
  call pressure_at_height(100000._real64,0._real64,p,height,sample,p_sample,ok)
  expected=sqrt(100000._real64*90000._real64)
  call check(ok.and.abs(p_sample-expected)<1.e-10_real64,'log-pressure interpolation')
  sample=250._real64
  call pressure_at_height(100000._real64,0._real64,p,height,sample,p_sample,ok)
  expected=sqrt(81000._real64*72900._real64)
  call check(ok.and.abs(p_sample-expected)<1.e-10_real64,'upper supported interval')
  call pressure_at_height(100000._real64,0._real64,p,height,301._real64,p_sample,ok)
  call check(.not.ok.and.ieee_is_nan(p_sample),'height extrapolation rejected')
  call pressure_at_height(100000._real64,0._real64,p,height,-1._real64,p_sample,ok)
  call check(.not.ok.and.ieee_is_nan(p_sample),'negative AGL rejected')
  call pressure_at_height(100000._real64,0._real64,p,height,nan,p_sample,ok)
  call check(.not.ok.and.ieee_is_nan(p_sample),'NaN AGL rejected')

  bad=p;bad(4)=105000._real64
  call pressure_at_height(100000._real64,0._real64,bad,height,50._real64,p_sample,ok)
  call check(.not.ok.and.ieee_is_nan(p_sample),'pressure ordering rejected')
  bad=height;bad(4)=250._real64
  call pressure_at_height(100000._real64,0._real64,p,bad,50._real64,p_sample,ok)
  call check(.not.ok.and.ieee_is_nan(p_sample),'aboveground height ordering rejected')
  bad=height;bad(4)=-1._real64
  call pressure_at_height(100000._real64,0._real64,p,bad,50._real64,p_sample,ok)
  call check(.not.ok.and.ieee_is_nan(p_sample),'below-terrain aboveground level rejected')
  bad=height;bad(2)=10._real64
  call pressure_at_height(100000._real64,0._real64,p,bad,50._real64,p_sample,ok)
  call check(ok.and..not.ieee_is_nan(p_sample),'above-PS donor height ignored')
  bad=height;bad(1)=nan
  call pressure_at_height(100000._real64,0._real64,p,bad,50._real64,p_sample,ok)
  call check(ok,'belowground donor fill ignored')
  bad=height;bad(5)=nan
  call pressure_at_height(100000._real64,0._real64,p,bad,50._real64,p_sample,ok)
  call check(.not.ok.and.ieee_is_nan(p_sample),'NaN aboveground height rejected')
  bad=p;bad(5)=nan
  call pressure_at_height(100000._real64,0._real64,bad,height,50._real64,p_sample,ok)
  call check(.not.ok.and.ieee_is_nan(p_sample),'NaN pressure rejected')
  call pressure_at_height(100000._real64,0._real64,p(1:2),height(1:2),0._real64,p_sample,ok)
  call check(.not.ok.and.ieee_is_nan(p_sample),'no aboveground support rejected')
  call pressure_at_height(100000._real64,0._real64,p(4:6),height(4:6),50._real64,p_sample,ok)
  call check(ok,'first level aboveground supported')

  xy(:,1)=[0._real64,0._real64];xy(:,2)=[0._real64,2._real64]
  pedge=[100._real64,100._real64]
  wind_cap(:,1)=[4._real64,0._real64];wind_cap(:,2)=[4._real64,0._real64]
  wind_sample(:,1)=[6._real64,0._real64];wind_sample(:,2)=[6._real64,0._real64]
  call lower_strip_flux(xy,pedge,80._real64,wind_sample,wind_cap,flux,ok)
  call check(ok.and.abs(flux-200._real64)<1.e-12_real64,'constant strip and sign')
  reverse_xy=xy(:,2:1:-1)
  reverse_pedge=pedge(2:1:-1)
  reverse_sample=wind_sample(:,2:1:-1)
  reverse_cap=wind_cap(:,2:1:-1)
  call lower_strip_flux(reverse_xy,reverse_pedge,80._real64,reverse_sample,reverse_cap,reverse_flux,ok)
  call check(ok.and.abs(flux+reverse_flux)<1.e-12_real64,'reversed edge reverses sign')

  xy(:,1)=[0._real64,0._real64];xy(:,2)=[1._real64,0._real64]
  pedge=[100._real64,120._real64]
  wind_cap(:,1)=[0._real64,1._real64];wind_cap(:,2)=[0._real64,3._real64]
  wind_sample(:,1)=[0._real64,5._real64];wind_sample(:,2)=[0._real64,9._real64]
  call lower_strip_flux(xy,pedge,80._real64,wind_sample,wind_cap,flux,ok)
  call check(ok.and.abs(flux+140._real64)<1.e-12_real64,'affine endpoint polynomial')

  pedge=[80._real64,80._real64]
  call lower_strip_flux(xy,pedge,80._real64,wind_sample,wind_cap,flux,ok)
  call check(ok.and.abs(flux)<1.e-12_real64,'zero-width strip allowed')
  pedge=[80._real64,100._real64]
  wind_cap(:,1)=[0._real64,3._real64];wind_cap(:,2)=wind_cap(:,1)
  wind_sample(:,1)=[0._real64,7._real64];wind_sample(:,2)=wind_sample(:,1)
  call lower_strip_flux(xy,pedge,80._real64,wind_sample,wind_cap,flux,ok)
  call check(ok.and.abs(flux+50._real64)<1.e-12_real64,'one zero-width endpoint allowed')

  pedge=[79._real64,100._real64]
  call lower_strip_flux(xy,pedge,80._real64,wind_sample,wind_cap,flux,ok)
  call check(.not.ok.and.ieee_is_nan(flux),'pressure cap violation rejected')
  call lower_strip_flux(xy,pedge,nan,wind_sample,wind_cap,flux,ok)
  call check(.not.ok.and.ieee_is_nan(flux),'NaN pressure cap rejected')
  pedge=[100._real64,100._real64]
  wind_sample(1,1)=nan
  call lower_strip_flux(xy,pedge,80._real64,wind_sample,wind_cap,flux,ok)
  call check(.not.ok.and.ieee_is_nan(flux),'NaN wind rejected')
  wind_sample(1,1)=7._real64
  xy(:,2)=xy(:,1)
  call lower_strip_flux(xy,pedge,80._real64,wind_sample,wind_cap,flux,ok)
  call check(.not.ok.and.ieee_is_nan(flux),'zero-length edge rejected')
  xy(:,1)=[0._real64,0._real64];xy(:,2)=[0._real64,1._real64]
  pedge=95000._real64
  wind_sample=0;wind_cap=0;wind_next=0
  wind_sample(1,:)=4;wind_cap(1,:)=8;wind_next(1,:)=6
  call cap_switch_jump(xy,pedge,95000._real64,90000._real64,wind_sample,wind_cap,wind_next,flux,ok)
  call check(ok.and.abs(flux-10000._real64)<1.e-10_real64,'cap jump analytic mismatch')
  reverse_xy=xy(:,[2,1]);reverse_sample=wind_sample(:,[2,1]);reverse_cap=wind_cap(:,[2,1])
  wind_next=wind_next(:,[2,1])
  call cap_switch_jump(reverse_xy,pedge,95000._real64,90000._real64, &
                        reverse_sample,reverse_cap,wind_next,reverse_flux,ok)
  call check(ok.and.abs(reverse_flux+flux)<1.e-10_real64,'cap jump reverses with face')
  wind_sample=wind_cap
  call cap_switch_jump(xy,pedge,95000._real64,90000._real64,wind_sample,wind_cap,wind_next,flux,ok)
  call check(ok.and.abs(flux)<1.e-10_real64,'matching cap samples have no finite jump')
  pedge=95001._real64
  call cap_switch_jump(xy,pedge,95000._real64,90000._real64,wind_sample,wind_cap,wind_next,flux,ok)
  call check(.not.ok.and.ieee_is_nan(flux),'cap limit requires endpoint at crossing')
  pedge=95000._real64
  call cap_switch_jump(xy,pedge,nan,90000._real64,wind_sample,wind_cap,wind_next,flux,ok)
  call check(.not.ok.and.ieee_is_nan(flux),'cap limit NaN rejected')
  print '(a,i0)', 'lower transport checks passed: ',checks
contains
  subroutine check(condition,label)
    logical, intent(in) :: condition
    character(*), intent(in) :: label
    if (.not.condition) then
      print *, 'FAIL: ',label
      error stop 1
    end if
    checks=checks+1
  end subroutine check
end program test_qbal_lower_transport
