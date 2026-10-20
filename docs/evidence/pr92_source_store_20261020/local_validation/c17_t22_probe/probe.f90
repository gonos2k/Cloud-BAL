program c17_t22_probe
  use iso_fortran_env, only: int32,int64,real32,real64
  use cloud_bal_joint_transport, only: joint_moment_store
  implicit none
  real(real64) :: q,b,feasible_q,feasible_b
  real(real32) :: sq,sb
  integer :: adjustment,stage
  logical :: valid
  q=transfer(int(z'374237F3DE250AFA',int64),0.0_real64)
  b=transfer(int(z'36A6E0DE5EEF31AA',int64),0.0_real64)
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
  feasible_q=900.0_real64*scale(1.0_real64,-149)
  feasible_b=scale(1.0_real64,-149)
  call joint_moment_store(feasible_q,feasible_b,1.0_real32,100.0_real64,900.0_real64,.true., &
       sq,sb,adjustment,valid,allow_normal_q_adjustment=.true.,allow_joint_quantum_absence=.true., &
       strict_mass_ratio=.true.,failure_stage=stage)
  write(*,'(a,1x,l1,1x,i0,1x,i0,1x,z8.8,1x,z8.8)') 'POSITIVE_BOUNDARY_PAIR',valid,stage,adjustment, &
       transfer(sq,0_int32),transfer(sb,0_int32)
end program c17_t22_probe
