program test_pr99_group_failure_core
  use iso_fortran_env, only: real32,real64,int32,int64
  use cloud_bal_joint_transport, only: joint_qnb_update
  implicit none
  real(real32) :: qb(1,1),nb(1,1),qs(1,1),ns(1,1),qa(1,1),na(1,1)
  real(real32) :: qc(1,1),nc(1,1),oldc(1),newc(1),rho(1),dt
  real(real64) :: qsr(1,1),nsr(1,1),qar(1,1),nar(1,1),minmass(1),maxmass(1)
  real(real64) :: theta,rq(1),rn(1),dq(1),dn(1),candidate64(2)
  real(real32) :: stored32(2)
  integer :: adjustments(1),cell,pair,predicate,store_stage
  logical :: feasible

  qb=1.0e-3_real32; nb=1.0e3_real32
  qs=0.0_real32; ns=0.0_real32; qa=0.0_real32; na=0.0_real32
  qsr=0.0_real64; nsr=0.0_real64; qar=0.0_real64; nar=0.0_real64
  qc=2.0e-4_real32; nc=4.0e2_real32
  oldc=1.0_real32; newc=1.0_real32; rho=1.0_real32; dt=1.0_real32
  minmass=1.0e-10_real64; maxmass=1.0e-8_real64

  call joint_qnb_update(qb,nb,qc,nc,qs,ns,qa,na,oldc,newc,rho,dt,minmass,maxmass, &
       theta,rq,rn,feasible,joint_constrained_storage=.true., &
       storage_delta_q=dq,storage_delta_n=dn,storage_adjustments=adjustments, &
       q_source_rate64=qsr,n_source_rate64=nsr,q_transport_rate64=qar,n_transport_rate64=nar, &
       joint_quantum_absence=.true.,strict_mass_pairs=[.false.],inactive_mass_limits=[0.0_real64], &
       group_failure_cell=cell,group_failure_pair=pair,group_failure_predicate=predicate, &
       group_failure_store_stage=store_stage,group_failure_candidate64=candidate64, &
       group_failure_stored32=stored32,group_failure_enabled=.true.)
  if (feasible.or.cell/=1.or.pair/=1.or.predicate/=1.or.store_stage/=2) error stop 1
  if (transfer(candidate64(1),0_int64)/=transfer(real(1.0e-3_real32,real64),0_int64)) error stop 2
  if (transfer(candidate64(2),0_int64)/=transfer(real(1.0e3_real32,real64),0_int64)) error stop 3
  if (transfer(stored32(1),0_int32)/=transfer(-1.0_real32,0_int32).or. &
      transfer(stored32(2),0_int32)/=transfer(-1.0_real32,0_int32)) error stop 6
  if (qc(1,1)/=2.0e-4_real32.or.nc(1,1)/=4.0e2_real32) error stop 4

  qb=1.0e-6_real32; nb=1.0e3_real32
  minmass=1.0e-10_real64; maxmass=1.0e-8_real64
  call joint_qnb_update(qb,nb,qc,nc,qs,ns,qa,na,oldc,newc,rho,dt,minmass,maxmass, &
       theta,rq,rn,feasible,joint_constrained_storage=.true., &
       storage_delta_q=dq,storage_delta_n=dn,storage_adjustments=adjustments, &
       q_source_rate64=qsr,n_source_rate64=nsr,q_transport_rate64=qar,n_transport_rate64=nar, &
       joint_quantum_absence=.true.,strict_mass_pairs=[.false.],inactive_mass_limits=[0.0_real64], &
       group_failure_cell=cell,group_failure_pair=pair,group_failure_predicate=predicate, &
       group_failure_store_stage=store_stage,group_failure_candidate64=candidate64, &
       group_failure_stored32=stored32,group_failure_enabled=.true.)
  if (.not.feasible.or.cell/=0.or.pair/=0.or.predicate/=0.or.store_stage/=0) error stop 5
  print '(a)', 'PR99_GROUP_FAILURE_CORE_PASS'
end program test_pr99_group_failure_core
