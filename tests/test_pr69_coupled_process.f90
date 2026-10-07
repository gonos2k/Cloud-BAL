program test_pr69_coupled_process
  use, intrinsic :: ieee_arithmetic, only: ieee_value,ieee_quiet_nan,ieee_positive_inf
  use pr69_helper, only: kdm6_mass_volume_rate,kdm6_rain_process_fraction, &
       kdm6_shared_pair_fraction
  implicit none
  real, parameter :: pi=3.14159265, dmr=3.0, rho_water=1000.0
  real, parameter :: pidnr=(pi*rho_water/6.0)*24.0
  real, parameter :: dmc=3.0,dmi=3.0
  real, parameter :: pidnc=(pi*1000.0/6.0),pidni=(pi*500.0/6.0)*6.0
  real, parameter :: qcrmin=1.0e-9, lambda_min=961.0, lambda_max=35000.0
  real, parameter :: qmin=1.0e-12,ncmin=10.0
  real, parameter :: lambda_c_min=12000.0,lambda_c_max=500000.0
  real, parameter :: lambda_i_min=9080.0,lambda_i_max=1820000.0
  real :: q_fixed(5),q_process(5),n_fixed(3),n_process(3)
  real :: density,nrain,fraction,fraction_dense,minimum_number,pair_fraction
  real :: bg_fixed,bg_process,t_fixed,t_process,volume_rate
  real :: q_before(5),q_after(5),n_after(3),bg_after,water_before
  real :: p_aut,p_ice,p_iacr,p_sacr,p_gacr,dt,latent_heat,cpm
  logical :: feasible,rate_feasible

  call kdm6_mass_volume_rate(0.0,0.0,volume_rate,rate_feasible)
  call require(rate_feasible .and. volume_rate.eq.0.0, &
       'exact zero mass rate does not require positive bulk density')
  call kdm6_mass_volume_rate(2.0,0.0,volume_rate,rate_feasible)
  call require(.not.rate_feasible, &
       'nonzero mass rate with zero bulk density is rejected')
  call kdm6_mass_volume_rate(3.0,6.0,volume_rate,rate_feasible)
  call require(rate_feasible .and. abs(volume_rate-0.5).le.1.0e-6, &
       'mass-to-volume rate uses the supplied source density')

  density=1.0
  dt=1.0
  q_fixed=0.0
  q_process=0.0
  n_fixed=0.0
  n_process=0.0
  q_fixed(3)=1.0e-5
  nrain=density*q_fixed(3)*5000.0**dmr/pidnr
  n_fixed(3)=nrain
  n_process(3)=-nrain
  call kdm6_rain_process_fraction(q_fixed,q_process,n_fixed,n_process, &
       0.0,0.0,270.0,0.0,density,pidnr,qmin,ncmin,qcrmin,dmr, &
       lambda_min,lambda_max,100.0,900.0,pidnc,dmc,lambda_c_min, &
       lambda_c_max,pidni,dmi,lambda_i_min,lambda_i_max,fraction,feasible)
  call require(feasible,'exact-zero trial has an admissible fraction')
  call require(fraction.gt.0.0 .and. fraction.lt.1.0, &
       'PSD boundary rejects the exact-zero number trial')
  minimum_number=density*q_fixed(3)*lambda_min**dmr/pidnr
  call require(abs(n_fixed(3)+fraction*n_process(3)-minimum_number) &
       .le.2.0e-5*minimum_number,'accepted number reaches the source lower bound')
  call require(q_fixed(3)+fraction*q_process(3).gt.0.0 .and. &
       n_fixed(3)+fraction*n_process(3).gt.0.0, &
       'accepted state retains positive rain mass and number')

  q_fixed(3)=1.0e-5
  q_process=0.0
  n_fixed(3)=nrain
  n_process(3)=-1.5*nrain
  call kdm6_rain_process_fraction(q_fixed,q_process,n_fixed,n_process, &
       0.0,0.0,270.0,0.0,2.0,pidnr,qmin,ncmin,qcrmin,dmr,lambda_min, &
       lambda_max,100.0,900.0,pidnc,dmc,lambda_c_min,lambda_c_max, &
       pidni,dmi,lambda_i_min,lambda_i_max,fraction_dense,feasible)
  call require(feasible .and. fraction_dense.lt.fraction, &
       'density changes the admitted process fraction')

  ! PR68 captured failed cell (169,59,17), using its cold trial/rates.
  ! DEN is not present in that record; this rain-only replay uses internal DEN=1.
  density=1.0
  q_fixed=0.0
  q_process=0.0
  n_fixed=0.0
  n_process=0.0
  q_fixed(3)=1.0172379552386701e-4
  n_fixed(3)=1669.6507568359375
  q_process(3)=(1.5890053646216984e-6+7.414185461129819e-7 &
       -5.253135260119279e-9-5.086189958092291e-6-6.731556823069695e-8)*20.0
  n_process(3)=(21.76652717590332-0.5572794675827026 &
       -69.67168426513672-34.586483001708984-0.43362346291542053)*20.0
  call kdm6_rain_process_fraction(q_fixed,q_process,n_fixed,n_process, &
       0.0,0.0,272.6404113769531,0.0,density,pidnr,qmin,ncmin,qcrmin,dmr, &
       lambda_min,lambda_max,100.0,900.0,pidnc,dmc,lambda_c_min, &
       lambda_c_max,pidni,dmi,lambda_i_min,lambda_i_max,fraction,feasible)
  call require(feasible .and. fraction.gt.0.99 .and. fraction.lt.1.0, &
       'captured rain-only failure trial is clipped to a source-admissible fraction')
  call require(q_fixed(3)+fraction*q_process(3).gt.qcrmin .and. &
       n_fixed(3)+fraction*n_process(3).gt.0.0, &
       'captured failed QR/NR endpoint retains both positive moments')

  pair_fraction=kdm6_shared_pair_fraction(10.0,4.0,20.0,10.0)
  call require(abs(pair_fraction-0.4).le.1.0e-6, &
       'paired mass and number rates use their more restrictive donor fraction')

  ! The selected source tendency vector conserves water across all phases.
  q_fixed=[2.0e-5,2.0e-5,1.0e-5,0.0,1.0e-5]
  q_process=0.0
  n_fixed=[density*q_fixed(1)*100000.0**dmc/pidnc, &
       density*q_fixed(2)*30000.0**dmi/pidni,nrain]
  n_process=0.0
  p_aut=1.0e-6
  p_ice=1.0e-6
  p_iacr=1.0e-6
  p_sacr=1.0e-6
  p_gacr=1.0e-6
  q_process(1)=-p_aut*dt
  q_process(2)=-p_ice*dt
  q_process(3)=(p_aut-p_iacr-p_sacr-p_gacr)*dt
  q_process(4)=0.0
  q_process(5)=(p_ice+p_iacr+p_sacr+p_gacr)*dt
  n_process(1)=-20.0*dt
  n_process(2)=-10.0*dt
  n_process(3)=-2.0*nrain
  bg_fixed=q_fixed(5)/400.0
  bg_process=(p_iacr/1000.0+p_ice/500.0+p_sacr/1000.0+p_gacr/1000.0)*dt
  latent_heat=3.34e5
  cpm=1004.0
  t_fixed=270.0
  t_process=latent_heat*(p_iacr+p_sacr+p_gacr)*dt/cpm
  call kdm6_rain_process_fraction(q_fixed,q_process,n_fixed,n_process, &
       bg_fixed,bg_process,t_fixed,t_process,density,pidnr,qmin,ncmin, &
       qcrmin,dmr,lambda_min,lambda_max,100.0,900.0,pidnc,dmc, &
       lambda_c_min,lambda_c_max,pidni,dmi,lambda_i_min,lambda_i_max, &
       fraction,feasible)
  call require(feasible,'coupled donor and receiver state has an admissible fraction')
  q_before=q_fixed
  water_before=sum(q_before)
  q_after=q_fixed+fraction*q_process
  n_after=n_fixed+fraction*n_process
  bg_after=bg_fixed+fraction*bg_process
  call require(abs(sum(q_after)-water_before).le.2.0e-10, &
       'same accepted process fraction conserves phase mass')
  call require(all(q_after.ge.0.0) .and. all(n_after.ge.0.0), &
       'accepted fraction preserves donor and receiver positivity')
  call require(abs((t_fixed+fraction*t_process-t_fixed) &
       -fraction*latent_heat*(p_iacr+p_sacr+p_gacr)*dt/cpm).le.2.0e-5, &
       'accepted latent heat uses the same process fraction')
  call require(bg_after.ge.q_after(5)/900.0 .and. &
       bg_after.le.q_after(5)/100.0,'accepted bulk volume stays within source density')

  q_fixed(3)=1.0e-5
  q_process=0.0
  n_fixed=0.0
  n_process=0.0
  bg_fixed=0.0
  bg_process=0.0
  call kdm6_rain_process_fraction(q_fixed,q_process,n_fixed,n_process, &
       bg_fixed,bg_process,270.0,0.0,density,pidnr,qmin,ncmin,qcrmin,dmr, &
       lambda_min,lambda_max,100.0,900.0,pidnc,dmc,lambda_c_min, &
       lambda_c_max,pidni,dmi,lambda_i_min,lambda_i_max,fraction,feasible)
  call require(.not.feasible,'positive rain mass with zero number is rejected')

  q_fixed=0.0
  q_fixed(1)=1.0e-5
  n_fixed=0.0
  call kdm6_rain_process_fraction(q_fixed,q_process,n_fixed,n_process, &
       0.0,0.0,270.0,0.0,density,pidnr,qmin,ncmin,qcrmin,dmr, &
       lambda_min,lambda_max,100.0,900.0,pidnc,dmc,lambda_c_min, &
       lambda_c_max,pidni,dmi,lambda_i_min,lambda_i_max,fraction,feasible)
  call require(.not.feasible,'positive cloud mass with zero number is rejected')

  q_fixed=0.0
  q_fixed(2)=1.0e-5
  call kdm6_rain_process_fraction(q_fixed,q_process,n_fixed,n_process, &
       0.0,0.0,270.0,0.0,density,pidnr,qmin,ncmin,qcrmin,dmr, &
       lambda_min,lambda_max,100.0,900.0,pidnc,dmc,lambda_c_min, &
       lambda_c_max,pidni,dmi,lambda_i_min,lambda_i_max,fraction,feasible)
  call require(.not.feasible,'positive ice mass with zero number is rejected')

  q_fixed=0.0
  q_fixed(1)=0.5*qmin
  n_fixed(1)=1.0
  call kdm6_rain_process_fraction(q_fixed,q_process,n_fixed,n_process, &
       0.0,0.0,270.0,0.0,density,pidnr,qmin,ncmin,qcrmin,dmr, &
       lambda_min,lambda_max,100.0,900.0,pidnc,dmc,lambda_c_min, &
       lambda_c_max,pidni,dmi,lambda_i_min,lambda_i_max,fraction,feasible)
  call require(.not.feasible,'subthreshold cloud mass is rejected before source cleanup')

  q_fixed=0.0
  q_fixed(2)=0.5*qmin
  n_fixed=0.0
  call kdm6_rain_process_fraction(q_fixed,q_process,n_fixed,n_process, &
       0.0,0.0,270.0,0.0,density,pidnr,qmin,ncmin,qcrmin,dmr, &
       lambda_min,lambda_max,100.0,900.0,pidnc,dmc,lambda_c_min, &
       lambda_c_max,pidni,dmi,lambda_i_min,lambda_i_max,fraction,feasible)
  call require(.not.feasible,'subthreshold ice mass is rejected before source cleanup')

  q_fixed=0.0
  q_process=0.0
  n_fixed=0.0
  n_process=0.0
  q_fixed(3)=-1.0e-6
  q_process(3)=-2.0e-6
  call kdm6_rain_process_fraction(q_fixed,q_process,n_fixed,n_process, &
       0.0,0.0,270.0,0.0,density,pidnr,qmin,ncmin,qcrmin,dmr, &
       lambda_min,lambda_max,100.0,900.0,pidnc,dmc,lambda_c_min, &
       lambda_c_max,pidni,dmi,lambda_i_min,lambda_i_max,fraction,feasible)
  call require(.not.feasible,'negative receiver mass trial is rejected')

  q_fixed=0.0
  q_process=0.0
  n_fixed=0.0
  n_process=0.0
  call kdm6_rain_process_fraction(q_fixed,q_process,n_fixed,n_process, &
       0.0,0.0,270.0,0.0,ieee_value(1.0,ieee_quiet_nan),pidnr, &
       qmin,ncmin,qcrmin,dmr,lambda_min,lambda_max,100.0,900.0, &
       pidnc,dmc,lambda_c_min,lambda_c_max,pidni,dmi,lambda_i_min, &
       lambda_i_max,fraction,feasible)
  call require(.not.feasible,'quiet NaN density returns infeasible without comparison')
  call kdm6_rain_process_fraction(q_fixed,q_process,n_fixed,n_process, &
       0.0,0.0,270.0,0.0,density,pidnr,qmin,ncmin,qcrmin,dmr, &
       ieee_value(1.0,ieee_quiet_nan),lambda_max,100.0,900.0,pidnc,dmc, &
       lambda_c_min,lambda_c_max,pidni,dmi,lambda_i_min,lambda_i_max, &
       fraction,feasible)
  call require(.not.feasible,'quiet NaN lambda returns infeasible without comparison')
  call kdm6_rain_process_fraction(q_fixed,q_process,n_fixed,n_process, &
       0.0,0.0,270.0,0.0,ieee_value(1.0,ieee_positive_inf),pidnr, &
       qmin,ncmin,qcrmin,dmr,lambda_min,lambda_max,100.0,900.0, &
       pidnc,dmc,lambda_c_min,lambda_c_max,pidni,dmi,lambda_i_min, &
       lambda_i_max,fraction,feasible)
  call require(.not.feasible,'infinite density returns infeasible without comparison')
  print '(A)','PR69 coupled rain process tests passed'

contains
  subroutine require(condition,message)
    logical, intent(in) :: condition
    character(len=*), intent(in) :: message
    if (.not.condition) then
      write(*,'(A)') trim(message)
      error stop 1
    endif
  end subroutine require
end program test_pr69_coupled_process
