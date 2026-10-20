
program test_t2_intermediate_mean
  use iso_fortran_env, only: real32, real64, int32
  use cloud_bal_joint_transport, only: joint_moment_store
  implicit none
  real(real32) :: q1,n1,rho,qout,nout,qbad,nbad,qstage,nstage
  real(real64) :: q,n,rateq,raten,mmin,mmax,bmin,bmax,dt
  integer :: adjustment,stage,final_adjustment,final_stage
  logical :: valid,final_valid
  integer(int32) :: qb,nb,qstageb,nstageb,qfinalb,nfinalb
  real(real64) :: upper64
  q1=2.31259036809206009e-7_real64; n1=5.52090240000000000e+07_real64
  rateq=-5.73329534876483977e-13_real64; raten=-1.36871687786769883e+02_real64
  q=2.31247570218508490e-7_real64; n=5.52062865662442669e+07_real64
  rho=1.14675259590148926_real64
  mmin=4.18879052734374980e-15_real64; mmax=3.03008574026602271e-10_real64
  bmin=3.78455494068234348e+09_real64; bmax=2.73766995130377844e+14_real64
  dt=2.0e+01_real64
  qstage=q1+real(real(dt,real64)*rateq,real32)
  nstage=n1+real(real(dt,real64)*raten,real32)
  call joint_moment_store(q,n,rho,mmin,mmax,.true.,qout,nout,adjustment,valid, &
       allow_normal_q_adjustment=.true.,allow_joint_quantum_absence=.true., &
       strict_mass_ratio=.true.,failure_stage=stage)
  if (.not.valid.or.stage/=0.or.adjustment/=2) stop 1
  qb=transfer(qout,qb); nb=transfer(nout,nb)
  qstageb=transfer(qstage,qstageb); nstageb=transfer(nstage,nstageb)
  if (qb/=int(z'34784CDA',int32).or.nb/=int(z'4C529864',int32)) stop 2
  if (qstageb/=int(z'34784CD9',int32).or.nstageb/=nb) stop 3
  call joint_moment_store(q,n,rho,mmin,mmax,.true.,qbad,nbad,adjustment,valid, &
       allow_normal_q_adjustment=.true.,allow_joint_quantum_absence=.true., &
       strict_mass_ratio=.true.,volume_number_bounds=[bmin,bmax],failure_stage=stage)
  if (valid.or.stage/=3) stop 4
  upper64=bmax*real(qout,real64)
  if (real(real(nout*rho,real32),real64)<=upper64) stop 5
  call joint_moment_store(real(qout,real64),real(nout,real64),rho,mmin,mmax,.true., &
       qbad,nbad,final_adjustment,final_valid,allow_normal_q_adjustment=.true., &
       allow_joint_quantum_absence=.true.,strict_mass_ratio=.true., &
       volume_number_bounds=[bmin,bmax],failure_stage=final_stage)
  if (.not.final_valid.or.final_stage/=0.or.final_adjustment/=2) stop 6
  qfinalb=transfer(qbad,qfinalb); nfinalb=transfer(nbad,nfinalb)
  if (qfinalb/=int(z'34784CDB',int32).or.nfinalb/=int(z'4C529864',int32)) stop 7
  if (q/n/=mmin) stop 8
  if (real(n,real64)*real(rho,real64)<=bmax*real(q,real64)) stop 9
  print '(a,1x,i0,1x,i0,2(1x,z8.8))','FINAL_VOLUME_STORE',final_stage,final_adjustment,qfinalb,nfinalb
  print '(a,2(1x,z8.8))','SOURCE_STAGE_R32',qstageb,nstageb
  print '(a,2(1x,z8.8))','D3_MASS_ONLY_INTERMEDIATE',qb,nb
  print '(a,1x,i0)','C8_SOURCE_VOLUME_STAGE',stage
  print '(a,1x,i0)','RETURNED_R32_FINAL_VOLUME_STAGE',final_stage
  print '(a)','PR91_C10_T2_PENDING_MEAN_PASS'
end program test_t2_intermediate_mean
