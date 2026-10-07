program test_pr70_cutoff
  use pr70_helper, only: kdm6_rain_process_fraction,kdm6_rain_process_state_valid
  implicit none
  real, parameter :: pi=3.14159265, pidnr=(pi*1000.0/6.0)*24.0
  real, parameter :: dmr=3.0, qmin=1.e-12, qcut=1.e-9
  real, parameter :: dmc=3.0,dmi=3.0,pidnc=(pi*1000.0/6.0),pidni=(pi*500.0/6.0)*6.0
  real, parameter :: lmin=961.,lmax=35000.,lcmin=12000.,lcmax=500000.,limin=9080.,limax=1820000.
  real :: qf(5),qp(5),nf(3),np(3),alpha,bg,t,q_state(5),n_state(3)
  integer :: status
  logical :: feasible,valid,pending

  qf=0.; qp=0.; nf=0.; np=0.; bg=0.; t=270.; pending=.false.
  qf(3)=2.e-9
  nf(3)=qf(3)*5000.0**dmr/pidnr
  qp(3)=-1.5e-9
  np(3)=nf(3)*(-0.75)
  call search()
  call require(feasible .and. status.eq.0,'cutoff counterexample returns a feasible step')
  call require(alpha.gt.0.6 .and. alpha.lt.2.0/3.0,'search finds the upper active interval below qcut')
  call require(qf(3)+alpha*qp(3).gt.qcut,'accepted float32 endpoint remains strictly above qcrmin')
  call require(qf(3)+1.0*qp(3).le.qcut,'original alpha=1 endpoint remains invalid')

  ! A source-active branch can begin after the exact-zero initial state.
  qf=0.; qp=0.; nf=0.; np=0.
  qp(3)=2.e-9
  np(3)=qp(3)*5000.0**dmr/pidnr
  call search()
  call require(feasible .and. alpha.eq.1.0,'search admits a created rain state on a later active interval')

  ! Exact extinction is a valid isolated endpoint only when N also reaches zero.
  qf=0.; qp=0.; nf=0.; np=0.
  qf(3)=2.e-9; qp(3)=-2.e-9
  nf(3)=qf(3)*5000.0**dmr/pidnr; np(3)=-nf(3)
  call search()
  call require(feasible .and. alpha.eq.1.0,'exact q=N=0 breakpoint is checked independently')
  q_state=0.; n_state=[0.,0.,1.]
  call kdm6_rain_process_state_valid(q_state,n_state,0.,270.,1.,pidnr, &
       qmin,10.,qcut,dmr,lmin,lmax,100.,900.,pidnc,dmc,lcmin,lcmax, &
       pidni,dmi,limin,limax,valid)
  call require(.not.valid,'zero rain mass with orphan number is rejected')
  q_state=0.; n_state=0.
  call kdm6_rain_process_state_valid(q_state,n_state,0.,270.,1.,pidnr, &
       qmin,10.,qcut,dmr,lmin,lmax,100.,900.,pidnc,dmc,lcmin,lcmax, &
       pidni,dmi,limin,limax,valid)
  call require(valid,'exact q=N=0 state remains valid')

  ! Pending full evaporation transfers orphan rain number after the accepted update.
  qf=0.; qp=0.; nf=0.; np=0.; pending=.true.
  qf(3)=2.e-9; qp(3)=-2.e-9
  nf(3)=qf(3)*5000.0**dmr/pidnr
  call search()
  call require(feasible .and. alpha.eq.1.0,'pending cleanup permits exact-zero rain trial')
  call kdm6_rain_process_state_valid(qf+alpha*qp,nf+alpha*np,0.,270.,1.,pidnr, &
       qmin,10.,qcut,dmr,lmin,lmax,100.,900.,pidnc,dmc,lcmin,lcmax, &
       pidni,dmi,limin,limax,valid,pending)
  call require(valid,'pending exact-zero rain may carry number before source transfer')
  n_state=nf+alpha*np; n_state(3)=0.
  call kdm6_rain_process_state_valid(qf+alpha*qp,n_state,0.,270.,1.,pidnr, &
       qmin,10.,qcut,dmr,lmin,lmax,100.,900.,pidnc,dmc,lcmin,lcmax, &
       pidni,dmi,limin,limax,valid)
  call require(valid,'post-transfer exact stored state is valid without pending exception')
  pending=.false.

  ! No representable alpha satisfies an initial state exactly on the forbidden cutoff.
  qf=0.; qp=0.; nf=0.; np=0.
  qf(3)=qcut
  call search()
  call require(.not.feasible .and. status.eq.1,'cutoff-only path is NO_FEASIBLE_STEP')
  q_state=[0.,0.,1.e-5,0.,0.]; n_state=[0.,0.,1.e-5*5000.0**dmr/pidnr]
  call kdm6_rain_process_state_valid(q_state,n_state,0.,270.,1.,pidnr,qmin,10.,qcut,dmr, &
       lmin,lmax,100.,900.,pidnc,dmc,lcmin,lcmax,pidni,dmi,limin,limax,valid)
  call require(valid,'exact stored-state predicate accepts an independent valid endpoint')

  ! Kelvin positivity is a strict source-state bound, not a floor.
  qf=0.; qp=0.; nf=0.; np=0.; pending=.false.
  call search_with_temperature(-1.0,0.0)
  call require(.not.feasible .and. status.eq.1,'nonpositive temperature with zero direction has no feasible step')
  q_state=0.; n_state=0.
  call kdm6_rain_process_state_valid(q_state,n_state,0.,-1.,1.,pidnr, &
       qmin,10.,qcut,dmr,lmin,lmax,100.,900.,pidnc,dmc,lcmin,lcmax, &
       pidni,dmi,limin,limax,valid)
  call require(.not.valid,'stored-state predicate rejects finite negative Kelvin temperature')
  call search_with_temperature(-1.0,2.0)
  call require(feasible .and. alpha.eq.1.0,'temperature may cross above zero within the process interval')
  call search_with_temperature(1.0,-2.0)
  call require(feasible .and. alpha.lt.0.5 .and. 1.0+alpha*(-2.0).gt.0.0, &
       'temperature search returns the greatest representable positive endpoint')
  call require(1.0+0.5*(-2.0).eq.0.0,'temperature cutoff breakpoint is exactly zero')
  call kdm6_rain_process_state_valid(q_state,n_state,0.,0.,1.,pidnr, &
       qmin,10.,qcut,dmr,lmin,lmax,100.,900.,pidnc,dmc,lcmin,lcmax, &
       pidni,dmi,limin,limax,valid)
  call require(.not.valid,'exact stored zero Kelvin boundary is rejected')

  ! Invalid search parameters are SEARCH_FAILURE, distinct from no feasible step.
  call kdm6_rain_process_fraction(qf,qp,nf,np,0.,0.,270.,0.,.false.,1.,pidnr,qmin,10.,qcut,dmr, &
       -1.,lmax,100.,900.,pidnc,dmc,lcmin,lcmax,pidni,dmi,limin,limax,alpha,feasible,status)
  call require(.not.feasible .and. status.eq.2,'invalid search input is SEARCH_FAILURE')
  print '(A)','PR70 cutoff search tests passed'
contains
  subroutine search_with_temperature(initial_temperature,temperature_process)
    real,intent(in)::initial_temperature,temperature_process
    call kdm6_rain_process_fraction(qf,qp,nf,np,bg,0.,initial_temperature, &
         temperature_process,pending,1.,pidnr,qmin,10.,qcut,dmr,lmin,lmax, &
         100.,900.,pidnc,dmc,lcmin,lcmax,pidni,dmi,limin,limax,alpha,feasible,status)
  end subroutine search_with_temperature
  subroutine search()
    call kdm6_rain_process_fraction(qf,qp,nf,np,bg,0.,t,0.,pending,1.,pidnr,qmin,10.,qcut,dmr, &
         lmin,lmax,100.,900.,pidnc,dmc,lcmin,lcmax,pidni,dmi,limin,limax,alpha,feasible,status)
  end subroutine search
  subroutine require(ok,message)
    logical,intent(in)::ok
    character(len=*),intent(in)::message
    if (.not.ok) then
      print '(A,I0,A,ES14.6)',trim(message)//' status=',status,' alpha=',alpha
      error stop 1
    endif
  end subroutine require
end program test_pr70_cutoff
