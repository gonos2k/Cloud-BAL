program pr70_temperature_repro_before_fix
  use pr70_helper, only: kdm6_rain_process_fraction
  implicit none
  real, parameter :: pi=3.14159265,pidnr=(pi*1000.0/6.0)*24.0
  real, parameter :: pidnc=(pi*1000.0/6.0),pidni=(pi*500.0/6.0)*6.0
  real, parameter :: qmin=1.e-12,qcut=1.e-9,dmr=3.,dmc=3.,dmi=3.
  real, parameter :: lmin=961.,lmax=35000.,lcmin=12000.,lcmax=500000.,limin=9080.,limax=1820000.
  real :: q(5),dq(5),n(3),dn(3),fraction
  integer :: status
  logical :: feasible
  q=0.; dq=0.; n=0.; dn=0.
  call kdm6_rain_process_fraction(q,dq,n,dn,0.,0.,-1.,0.,.false.,1.,pidnr, &
       qmin,10.,qcut,dmr,lmin,lmax,100.,900.,pidnc,dmc,lcmin,lcmax, &
       pidni,dmi,limin,limax,fraction,feasible,status)
  print '(A,L1,A,I0,A,ES12.4)','finite-only prior gate result: feasible=',feasible, &
       ' status=',status,' alpha=',fraction
  if (.not.feasible .or. status.ne.0 .or. fraction.ne.1.0) error stop 1
end program
