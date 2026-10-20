program candidate
  use iso_fortran_env, only: int32,int64,real32,real64
  use cloud_bal_joint_transport, only: joint_moment_store
  implicit none
  real(real64) :: q,b
  real(real32) :: sq,sb
  integer :: adjustment,stage
  logical :: valid
  q=transfer(int(z'371FB7DAF11AF1E8',int64),0.0_real64)
  b=transfer(int(z'368227465D101BF5',int64),0.0_real64)
  call joint_moment_store(q,b,1.0_real32,100.0_real64,900.0_real64,.true.,sq,sb, &
       adjustment,valid,allow_normal_q_adjustment=.true.,allow_joint_quantum_absence=.true., &
       strict_mass_ratio=.true.,failure_stage=stage)
  write(*,'(a,1x,l1,1x,i0,1x,i0,1x,z8.8,1x,z8.8)') 'DEFAULT',valid,stage,adjustment, &
       transfer(sq,0_int32),transfer(sb,0_int32)
  call joint_moment_store(q,b,1.0_real32,100.0_real64,900.0_real64,.true.,sq,sb, &
       adjustment,valid,allow_normal_q_adjustment=.true.,allow_joint_quantum_absence=.true., &
       strict_mass_ratio=.true.,failure_stage=stage,allow_bulk_volume_quantum_absence=.true.)
  write(*,'(a,1x,l1,1x,i0,1x,i0,1x,z8.8,1x,z8.8)') 'POLICY',valid,stage,adjustment, &
       transfer(sq,0_int32),transfer(sb,0_int32)
end program candidate
