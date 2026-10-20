program replay_source_stage
  use iso_fortran_env, only: real32,real64,int32
  use cloud_bal_joint_transport, only: joint_moment_store,joint_moment_is_valid
  implicit none
  real(real32), parameter :: q0=7.42170414014253765e-09_real32
  real(real32), parameter :: n0=1.77180112500000000e+06_real32
  real(real64), parameter :: rawq=8.05719553576000891e-12_real64
  real(real64), parameter :: rawn=1.92351489257812500e+03_real64
  real(real64), parameter :: dq=-1.52211236780719325e-17_real64
  real(real64), parameter :: dn=-4.95685467740258900e-04_real64
  real(real32), parameter :: rho=1.08871281147003174_real32
  real(real64), parameter :: rmin=4.18879052734374980e-15_real64
  real(real64), parameter :: rmax=3.03008574026602271e-10_real64
  real(real64), parameter :: bmin=3.59300991718620300e9_real64
  real(real64), parameter :: bmax=2.59911018314974187e14_real64
  real(real32) :: sq,sn, incq,incn, endq,endn
  real(real64) :: qcand,ncand,rrq,rrn
  integer :: adj,stage
  logical :: ok
  integer(int32) :: qbits,nbits
  qcand=real(q0,real64)+20.0_real64*(rawq+dq)
  ncand=real(n0,real64)+20.0_real64*(rawn+dn)
  call joint_moment_store(qcand,ncand,rho,rmin,rmax,.true.,sq,sn,adj,ok, &
       allow_normal_q_adjustment=.true.,allow_joint_quantum_absence=.true., &
       strict_mass_ratio=.true.,failure_stage=stage)
  qbits=transfer(sq,qbits); nbits=transfer(sn,nbits)
  write(*,'(a,1x,l1,1x,i0,1x,i0,2(1x,z8.8))') 'ADJUSTED_SOURCE',ok,stage,adj,qbits,nbits
  qcand=real(q0,real64)+20.0_real64*rawq
  ncand=real(n0,real64)+20.0_real64*rawn
  call joint_moment_store(qcand,ncand,rho,rmin,rmax,.true.,sq,sn,adj,ok, &
       allow_normal_q_adjustment=.true.,allow_joint_quantum_absence=.true., &
       strict_mass_ratio=.true.,failure_stage=stage)
  qbits=transfer(sq,qbits); nbits=transfer(sn,nbits)
  write(*,'(a,1x,l1,1x,i0,1x,i0,2(1x,z8.8))') 'RAW_SOURCE',ok,stage,adj,qbits,nbits
  incq=real(20.0_real64*(rawq+dq),real32); incn=real(20.0_real64*(rawn+dn),real32)
  endq=q0+incq; endn=n0+incn
  write(*,'(a,2(1x,z8.8),2(1x,es26.17))') 'R32_ENDPOINT',transfer(endq,qbits),transfer(endn,nbits), &
       real(endq,real64),real(endn,real64)
  rrq=real(endq,real64); rrn=real(endn,real64)
  call joint_moment_store(rrq,rrn,rho,rmin,rmax,.true.,sq,sn,adj,ok, &
       allow_normal_q_adjustment=.true.,allow_joint_quantum_absence=.true., &
       strict_mass_ratio=.true.,failure_stage=stage)
  qbits=transfer(sq,qbits); nbits=transfer(sn,nbits)
  write(*,'(a,1x,l1,1x,i0,1x,i0,2(1x,z8.8))') 'R32_AS_R64',ok,stage,adj,qbits,nbits
  write(*,'(a,1x,4(es26.17,1x))') 'STRICT_MASS_MARGINS', &
       (real(q0,real64)+20*(rawq+dq))/(real(n0,real64)+20*(rawn+dn))-rmin, &
       (real(q0,real64)+20*(rawq+dq))-rmin*(real(n0,real64)+20*(rawn+dn)), &
       (real(q0,real64)+20*rawq)/(real(n0,real64)+20*rawn)-rmin, &
       (real(q0,real64)+20*rawq)-rmin*(real(n0,real64)+20*rawn)
end program replay_source_stage
