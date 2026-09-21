program test_qbal_column_budget
  use iso_fortran_env, only: real64, int64
  use ieee_arithmetic, only: ieee_value,ieee_quiet_nan,ieee_is_nan
  use qbal_column_budget
  implicit none
  real(real64) :: xy(2,3),p0(3),p1(3),flux,rate,bound,nan,subtotal,residual
  real(real64) :: covered(3),missing(3),reversed_xy(2,3)
  integer, parameter :: directions(3)=[1,-1,1],bad_directions(3)=[1,0,1]
  logical, parameter :: all_known(3)=.true.,none_known(3)=.false.,first_known(3)=[.true.,.false.,.false.]
  integer :: checks
  logical :: ok,complete
  checks=0;nan=ieee_value(0._real64,ieee_quiet_nan)
  xy(:,1)=[100000._real64,200000._real64]
  xy(:,2)=xy(:,1)+[2000._real64,0._real64]
  xy(:,3)=xy(:,1)+[0._real64,3000._real64]
  p0=[98000._real64,99000._real64,100000._real64]
  p1=p0+7200*[.01_real64,-.02_real64,.04_real64]
  call evaluate(1000_int64,8200_int64,.true.)
  call check(ok.and.abs(flux-30000)<1.e-7_real64,'affine pressure tendency integrated over same triangle')
  call check(abs(flux-rate)<=bound,'surface flux equals finite volume rate')
  ! Raising the finite top leaves its time-independent contribution unchanged.
  call surface_pressure_flux(xy,p0,p1,20000._real64,1000_int64,8200_int64,.true.,flux,rate,bound,ok)
  call check(ok.and.abs(flux-30000)<1.e-7_real64,'fixed top does not add a second tendency')
  call surface_pressure_flux(xy,p1,p0,5000._real64,1000_int64,8200_int64,.true.,flux,rate,bound,ok)
  call check(ok.and.abs(flux+30000)<1.e-7_real64,'pressure reversal reverses surface flux')
  p1=p0
  call evaluate(1000_int64,8200_int64,.true.)
  call check(ok.and.flux==0.and.rate==0,'stationary volume zero normal flux')
  p1=p0+1.e-7_real64
  call evaluate(1000_int64,8200_int64,.true.)
  call check(ok.and.flux>0.and.abs(flux-rate)<=bound,'small tendency uses uncancelled volume scale')
  call evaluate(1000_int64,8200_int64,.false.)
  call check(.not.ok,'unavailable time pair rejected')
  call evaluate(1000_int64,1000_int64,.true.)
  call check(.not.ok,'zero interval rejected')
  call evaluate(8200_int64,1000_int64,.true.)
  call check(.not.ok,'backwards interval rejected')
  reversed_xy=xy(:,3:1:-1)
  call surface_pressure_flux(reversed_xy,p0,p1,5000._real64,1000_int64,8200_int64,.true.,flux,rate,bound,ok)
  call check(.not.ok,'invalid oriented cell rejected')
  p1(1)=nan
  call evaluate(1000_int64,8200_int64,.true.)
  call check(.not.ok,'NaN pressure rejected without arithmetic')
  p1(1)=4000
  call evaluate(1000_int64,8200_int64,.true.)
  call check(.not.ok,'surface below finite top rejected')

  covered=[7._real64,2._real64,1._real64];missing=[1._real64,2._real64,3._real64]
  call column_flux_budget(4._real64,covered,missing,directions,all_known, &
                          12._real64,.true.,subtotal,residual,complete,ok)
  call check(ok.and.complete.and.residual==0,'ground plus oriented full sides minus top')
  missing=nan
  call column_flux_budget(4._real64,covered,missing,directions,none_known, &
                          12._real64,.true.,subtotal,residual,complete,ok)
  call check(ok.and..not.complete.and.ieee_is_nan(residual),'unknown bottom strips cannot produce full residual')
  call check(subtotal==-2,'known partial sum retains finite top sign')
  call column_flux_budget(4._real64,covered,missing,directions,none_known, &
                          10._real64,.true.,subtotal,residual,complete,ok)
  call check(ok.and.subtotal==0.and..not.complete.and.ieee_is_nan(residual), &
             'zero known subtotal is not a complete zero residual')
  call column_flux_budget(4._real64,covered,missing,directions,none_known, &
                          nan,.false.,subtotal,residual,complete,ok)
  call check(ok.and..not.complete.and.subtotal==10,'unknown top excluded only from explicitly partial sum')
  call column_flux_budget(4._real64,covered,missing,directions,first_known, &
                          12._real64,.true.,subtotal,residual,complete,ok)
  call check(.not.ok.and.ieee_is_nan(residual),'NaN claimed known strip rejected')
  missing=0
  call column_flux_budget(4._real64,covered,missing,bad_directions,all_known, &
                          10._real64,.true.,subtotal,residual,complete,ok)
  call check(.not.ok,'missing side orientation rejected')
  print '(a,i0)', 'column budget checks passed: ',checks
contains
  subroutine evaluate(t0,t1,eligible)
    integer(int64), intent(in) :: t0,t1
    logical, intent(in) :: eligible
    call surface_pressure_flux(xy,p0,p1,5000._real64,t0,t1,eligible,flux,rate,bound,ok)
  end subroutine
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
