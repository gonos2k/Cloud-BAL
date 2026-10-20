program replay_captured_freezing_base
  use, intrinsic :: iso_fortran_env, only: real32,real64,int32
  implicit none
  real(real32) :: qc,nc,qi,ni,rho,qca,nca,qia,nia,pidnc,pidni,pi,ice_limit
  real(real32), parameter :: lamdacmin=12000.0_real32, lamdacmax=500000.0_real32
  real(real32), parameter :: lamdaimin=9080.0_real32, lamdaimax=1820000.0_real32
  real(real32), parameter :: dmc=3.0_real32,dmi=3.0_real32
  real(real64) :: qreq,nreq,cmin,cmax,imin,imax,approvedq,approvedn,fraction
  logical :: base_valid,accepted
  integer(int32) :: qc_bits,nc_bits,qi_bits,ni_bits,rho_bits,cutoff_bits
  external :: pr85_kdm6_freezing_packet
  pi=4.0_real32*atan(1.0_real32)
  pidnc=(pi*1000.0_real32/6.0_real32)*gamma(2.0_real32)
  pidni=(pi*500.0_real32/6.0_real32)*gamma(4.0_real32)
  qc=transfer(int(z'376296F1',int32),0.0_real32)
  nc=transfer(int(z'4C22685A',int32),0.0_real32)
  qi=transfer(int(z'3623A538',int32),0.0_real32)
  ni=transfer(int(z'441BBBE7',int32),0.0_real32)
  rho=transfer(int(z'3F0938B8',int32),0.0_real32)
  ice_limit=nearest(1.0e-14_real32,-1.0_real32)
  qreq=2.1296498102647661e-13_real64
  nreq=5.0349597749963093e-01_real64
  cmin=real(pidnc,real64)/(real(lamdacmax,real64)**real(dmc,real64))
  cmax=real(pidnc,real64)/(real(lamdacmin,real64)**real(dmc,real64))
  imin=real(pidni,real64)/(real(lamdaimax,real64)**real(dmi,real64))
  imax=real(pidni,real64)/(real(lamdaimin,real64)**real(dmi,real64))
  call pr85_kdm6_freezing_packet(qc,nc,qi,ni,rho,real(ice_limit,real64), &
       qreq,nreq,cmin,cmax,imin,imax,qca,nca,qia,nia,approvedq,approvedn,fraction,base_valid,accepted)
  qc_bits=transfer(qc,qc_bits); nc_bits=transfer(nc,nc_bits)
  qi_bits=transfer(qi,qi_bits); ni_bits=transfer(ni,ni_bits); rho_bits=transfer(rho,rho_bits)
  cutoff_bits=transfer(ice_limit,cutoff_bits)
  print '(a,6(1x,z8.8))','INPUT_R32_BITS',qc_bits,nc_bits,qi_bits,ni_bits,rho_bits,cutoff_bits
  print '(a,1p,8e24.16)','BOUNDS',cmin,cmax,imin,imax,real(rho,real64)*real(qi,real64)/real(ni,real64), &
       real(8*spacing(real(imax,real32)),real64),real(pidnc,real64),real(pidni,real64)
  print '(a,1p,2e24.16)','PROPOSAL_R64',qreq,nreq
  print '(a,2(1x,l1),1p,3e24.16)','RESULT',base_valid,accepted,fraction,approvedq,approvedn
end program
