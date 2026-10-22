program bulk_absence_harness
  use iso_fortran_env, only: int32,int64,real32,real64
  use cloud_bal_joint_transport, only: joint_bulk_candidate_absence_is_valid
  implicit none
  integer :: c
  logical :: accepted
  c=1; accepted=joint_bulk_candidate_absence_is_valid(transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'47a09016',int32),0.0_real32), &
      transfer(int(z'47a08d94',int32),0.0_real32), &
      transfer(int(z'40d55555',int32),0.0_real32), &
      transfer(int(z'3f53b32d',int32),0.0_real32), &
      transfer(int(z'3753214b46a3bc21',int64),0.0_real64), &
      transfer(int(z'36b5c40847451a51',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'3fea7665a0000000',int64),0.0_real64), &
      transfer(int(z'4059000000000000',int64),0.0_real64), &
      transfer(int(z'408c200000000000',int64),0.0_real64), &
      transfer(int(z'36796b3ba65c1be8',int64),0.0_real64), &
      transfer(int(z'35dcebc8fcfefc7a',int64),0.0_real64))
  write(*,'(i0,1x,l1)') c,accepted
  c=2; accepted=joint_bulk_candidate_absence_is_valid(transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'36e9000000000000',int64),0.0_real64), &
      transfer(int(z'3680000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'4059000000000000',int64),0.0_real64), &
      transfer(int(z'408c200000000000',int64),0.0_real64), &
      transfer(int(z'36e9000000000000',int64),0.0_real64), &
      transfer(int(z'3680000000000000',int64),0.0_real64))
  write(*,'(i0,1x,l1)') c,accepted
  c=3; accepted=joint_bulk_candidate_absence_is_valid(transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'36e9000000000001',int64),0.0_real64), &
      transfer(int(z'3680000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'4059000000000000',int64),0.0_real64), &
      transfer(int(z'408c200000000000',int64),0.0_real64), &
      transfer(int(z'36e9000000000001',int64),0.0_real64), &
      transfer(int(z'3680000000000000',int64),0.0_real64))
  write(*,'(i0,1x,l1)') c,accepted
  c=4; accepted=joint_bulk_candidate_absence_is_valid(transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'370f400000000000',int64),0.0_real64), &
      transfer(int(z'3680000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'4059000000000000',int64),0.0_real64), &
      transfer(int(z'408c200000000000',int64),0.0_real64), &
      transfer(int(z'370f400000000000',int64),0.0_real64), &
      transfer(int(z'3680000000000000',int64),0.0_real64))
  write(*,'(i0,1x,l1)') c,accepted
  c=5; accepted=joint_bulk_candidate_absence_is_valid(transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'371c1fffffffffff',int64),0.0_real64), &
      transfer(int(z'3680000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'4059000000000000',int64),0.0_real64), &
      transfer(int(z'408c200000000000',int64),0.0_real64), &
      transfer(int(z'371c1fffffffffff',int64),0.0_real64), &
      transfer(int(z'3680000000000000',int64),0.0_real64))
  write(*,'(i0,1x,l1)') c,accepted
  c=6; accepted=joint_bulk_candidate_absence_is_valid(transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'371c200000000000',int64),0.0_real64), &
      transfer(int(z'3680000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'4059000000000000',int64),0.0_real64), &
      transfer(int(z'408c200000000000',int64),0.0_real64), &
      transfer(int(z'371c200000000000',int64),0.0_real64), &
      transfer(int(z'3680000000000000',int64),0.0_real64))
  write(*,'(i0,1x,l1)') c,accepted
  c=7; accepted=joint_bulk_candidate_absence_is_valid(transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'36e8ffffffffffff',int64),0.0_real64), &
      transfer(int(z'3680000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'4059000000000000',int64),0.0_real64), &
      transfer(int(z'408c200000000000',int64),0.0_real64), &
      transfer(int(z'36e8ffffffffffff',int64),0.0_real64), &
      transfer(int(z'3680000000000000',int64),0.0_real64))
  write(*,'(i0,1x,l1)') c,accepted
  c=8; accepted=joint_bulk_candidate_absence_is_valid(transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'36e9000000000000',int64),0.0_real64), &
      transfer(int(z'3680000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'4059000000000000',int64),0.0_real64), &
      transfer(int(z'408c200000000000',int64),0.0_real64), &
      transfer(int(z'36e9000000000000',int64),0.0_real64), &
      transfer(int(z'3680000000000000',int64),0.0_real64))
  write(*,'(i0,1x,l1)') c,accepted
  c=9; accepted=joint_bulk_candidate_absence_is_valid(transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'36e9000000000001',int64),0.0_real64), &
      transfer(int(z'3680000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'4059000000000000',int64),0.0_real64), &
      transfer(int(z'408c200000000000',int64),0.0_real64), &
      transfer(int(z'36e9000000000001',int64),0.0_real64), &
      transfer(int(z'3680000000000000',int64),0.0_real64))
  write(*,'(i0,1x,l1)') c,accepted
  c=10; accepted=joint_bulk_candidate_absence_is_valid(transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'371c1fffffffffff',int64),0.0_real64), &
      transfer(int(z'3680000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'4059000000000000',int64),0.0_real64), &
      transfer(int(z'408c200000000000',int64),0.0_real64), &
      transfer(int(z'371c1fffffffffff',int64),0.0_real64), &
      transfer(int(z'3680000000000000',int64),0.0_real64))
  write(*,'(i0,1x,l1)') c,accepted
  c=11; accepted=joint_bulk_candidate_absence_is_valid(transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'371c200000000000',int64),0.0_real64), &
      transfer(int(z'3680000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'4059000000000000',int64),0.0_real64), &
      transfer(int(z'408c200000000000',int64),0.0_real64), &
      transfer(int(z'371c200000000000',int64),0.0_real64), &
      transfer(int(z'3680000000000000',int64),0.0_real64))
  write(*,'(i0,1x,l1)') c,accepted
  c=12; accepted=joint_bulk_candidate_absence_is_valid(transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'371c200000000001',int64),0.0_real64), &
      transfer(int(z'3680000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'4059000000000000',int64),0.0_real64), &
      transfer(int(z'408c200000000000',int64),0.0_real64), &
      transfer(int(z'371c200000000001',int64),0.0_real64), &
      transfer(int(z'3680000000000000',int64),0.0_real64))
  write(*,'(i0,1x,l1)') c,accepted
  c=13; accepted=joint_bulk_candidate_absence_is_valid(transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'370f400000000000',int64),0.0_real64), &
      transfer(int(z'3680000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'4059000000000000',int64),0.0_real64), &
      transfer(int(z'408c200000000000',int64),0.0_real64), &
      transfer(int(z'370f400000000000',int64),0.0_real64), &
      transfer(int(z'3680000000000000',int64),0.0_real64))
  write(*,'(i0,1x,l1)') c,accepted
  c=14; accepted=joint_bulk_candidate_absence_is_valid(transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'371b580000000000',int64),0.0_real64), &
      transfer(int(z'368c000000000000',int64),0.0_real64), &
      transfer(int(z'b717700000000000',int64),0.0_real64), &
      transfer(int(z'b688000000000000',int64),0.0_real64), &
      transfer(int(z'3fe0000000000000',int64),0.0_real64), &
      transfer(int(z'4059000000000000',int64),0.0_real64), &
      transfer(int(z'408c200000000000',int64),0.0_real64), &
      transfer(int(z'370f400000000000',int64),0.0_real64), &
      transfer(int(z'3680000000000000',int64),0.0_real64))
  write(*,'(i0,1x,l1)') c,accepted
  c=15; accepted=joint_bulk_candidate_absence_is_valid(transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'371b580000000000',int64),0.0_real64), &
      transfer(int(z'368c000000000000',int64),0.0_real64), &
      transfer(int(z'b70f400000000000',int64),0.0_real64), &
      transfer(int(z'b680000000000000',int64),0.0_real64), &
      transfer(int(z'3fe8000000000000',int64),0.0_real64), &
      transfer(int(z'4059000000000000',int64),0.0_real64), &
      transfer(int(z'408c200000000000',int64),0.0_real64), &
      transfer(int(z'370f400000000000',int64),0.0_real64), &
      transfer(int(z'3680000000000000',int64),0.0_real64))
  write(*,'(i0,1x,l1)') c,accepted
  c=16; accepted=joint_bulk_candidate_absence_is_valid(transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'371b580000000000',int64),0.0_real64), &
      transfer(int(z'368c000000000000',int64),0.0_real64), &
      transfer(int(z'b707700000000000',int64),0.0_real64), &
      transfer(int(z'b678000000000000',int64),0.0_real64), &
      transfer(int(z'3ff0000000000000',int64),0.0_real64), &
      transfer(int(z'4059000000000000',int64),0.0_real64), &
      transfer(int(z'408c200000000000',int64),0.0_real64), &
      transfer(int(z'370f400000000000',int64),0.0_real64), &
      transfer(int(z'3680000000000000',int64),0.0_real64))
  write(*,'(i0,1x,l1)') c,accepted
  c=17; accepted=joint_bulk_candidate_absence_is_valid(transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'71800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'36f7400000000000',int64),0.0_real64), &
      transfer(int(z'3667ced916872b02',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'4059000000000000',int64),0.0_real64), &
      transfer(int(z'408c200000000000',int64),0.0_real64), &
      transfer(int(z'36f7400000000000',int64),0.0_real64), &
      transfer(int(z'3667ced916872b02',int64),0.0_real64))
  write(*,'(i0,1x,l1)') c,accepted
  c=18; accepted=joint_bulk_candidate_absence_is_valid(transfer(int(z'30800000',int32),0.0_real32), &
      transfer(int(z'2c03126f',int32),0.0_real32), &
      transfer(int(z'0d800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'b7cfff0600000000',int64),0.0_real64), &
      transfer(int(z'b74061cdd2f1a9fc',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'4059000000000000',int64),0.0_real64), &
      transfer(int(z'408c200000000000',int64),0.0_real64), &
      transfer(int(z'36ff400000000000',int64),0.0_real64), &
      transfer(int(z'367001a1cac08000',int64),0.0_real64))
  write(*,'(i0,1x,l1)') c,accepted
  c=19; accepted=joint_bulk_candidate_absence_is_valid(transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'371f3fffffffffff',int64),0.0_real64), &
      transfer(int(z'368fffffffffffff',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'4059000000000000',int64),0.0_real64), &
      transfer(int(z'408c200000000000',int64),0.0_real64), &
      transfer(int(z'371f3fffffffffff',int64),0.0_real64), &
      transfer(int(z'368fffffffffffff',int64),0.0_real64))
  write(*,'(i0,1x,l1)') c,accepted
  c=20; accepted=joint_bulk_candidate_absence_is_valid(transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'371f400000000000',int64),0.0_real64), &
      transfer(int(z'3690000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'4059000000000000',int64),0.0_real64), &
      transfer(int(z'408c200000000000',int64),0.0_real64), &
      transfer(int(z'371f400000000000',int64),0.0_real64), &
      transfer(int(z'3690000000000000',int64),0.0_real64))
  write(*,'(i0,1x,l1)') c,accepted
  c=21; accepted=joint_bulk_candidate_absence_is_valid(transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'371f400000000002',int64),0.0_real64), &
      transfer(int(z'3690000000000001',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'4059000000000000',int64),0.0_real64), &
      transfer(int(z'408c200000000000',int64),0.0_real64), &
      transfer(int(z'371f400000000002',int64),0.0_real64), &
      transfer(int(z'3690000000000001',int64),0.0_real64))
  write(*,'(i0,1x,l1)') c,accepted
  c=22; accepted=joint_bulk_candidate_absence_is_valid(transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'372c1fffffffffff',int64),0.0_real64), &
      transfer(int(z'368fffffffffffff',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'4059000000000000',int64),0.0_real64), &
      transfer(int(z'408c200000000000',int64),0.0_real64), &
      transfer(int(z'372c1fffffffffff',int64),0.0_real64), &
      transfer(int(z'368fffffffffffff',int64),0.0_real64))
  write(*,'(i0,1x,l1)') c,accepted
  c=23; accepted=joint_bulk_candidate_absence_is_valid(transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'372c200000000000',int64),0.0_real64), &
      transfer(int(z'3690000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'4059000000000000',int64),0.0_real64), &
      transfer(int(z'408c200000000000',int64),0.0_real64), &
      transfer(int(z'372c200000000000',int64),0.0_real64), &
      transfer(int(z'3690000000000000',int64),0.0_real64))
  write(*,'(i0,1x,l1)') c,accepted
  c=24; accepted=joint_bulk_candidate_absence_is_valid(transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'372c200000000001',int64),0.0_real64), &
      transfer(int(z'3690000000000001',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'4059000000000000',int64),0.0_real64), &
      transfer(int(z'408c200000000000',int64),0.0_real64), &
      transfer(int(z'372c200000000001',int64),0.0_real64), &
      transfer(int(z'3690000000000001',int64),0.0_real64))
  write(*,'(i0,1x,l1)') c,accepted
  c=25; accepted=joint_bulk_candidate_absence_is_valid(transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'36e9000000000000',int64),0.0_real64), &
      transfer(int(z'3680000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'4059000000000000',int64),0.0_real64), &
      transfer(int(z'408c200000000000',int64),0.0_real64), &
      transfer(int(z'36e9000000000001',int64),0.0_real64), &
      transfer(int(z'3680000000000000',int64),0.0_real64))
  write(*,'(i0,1x,l1)') c,accepted
  c=26; accepted=joint_bulk_candidate_absence_is_valid(transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3670000000000000',int64),0.0_real64), &
      transfer(int(z'3600624dd2f1a9fc',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'4059000000000000',int64),0.0_real64), &
      transfer(int(z'408c200000000000',int64),0.0_real64), &
      transfer(int(z'3670000000000000',int64),0.0_real64), &
      transfer(int(z'3600624dd2f1a9fc',int64),0.0_real64))
  write(*,'(i0,1x,l1)') c,accepted
  c=27; accepted=joint_bulk_candidate_absence_is_valid(transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'bf800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3670000000000000',int64),0.0_real64), &
      transfer(int(z'3600624dd2f1a9fc',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'4059000000000000',int64),0.0_real64), &
      transfer(int(z'408c200000000000',int64),0.0_real64), &
      transfer(int(z'b670000000000000',int64),0.0_real64), &
      transfer(int(z'b600624dd2f1a9fc',int64),0.0_real64))
  write(*,'(i0,1x,l1)') c,accepted
  c=28; accepted=joint_bulk_candidate_absence_is_valid(transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'3670000000000000',int64),0.0_real64), &
      transfer(int(z'3600624dd2f1a9fc',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'4059000000000000',int64),0.0_real64), &
      transfer(int(z'408c200000000000',int64),0.0_real64), &
      transfer(int(z'3670000000000000',int64),0.0_real64), &
      transfer(int(z'3600624dd2f1a9fc',int64),0.0_real64))
  write(*,'(i0,1x,l1)') c,accepted
  c=29; accepted=joint_bulk_candidate_absence_is_valid(transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3670000000000000',int64),0.0_real64), &
      transfer(int(z'3600624dd2f1a9fc',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'bfd0000000000000',int64),0.0_real64), &
      transfer(int(z'4059000000000000',int64),0.0_real64), &
      transfer(int(z'408c200000000000',int64),0.0_real64), &
      transfer(int(z'3670000000000000',int64),0.0_real64), &
      transfer(int(z'3600624dd2f1a9fc',int64),0.0_real64))
  write(*,'(i0,1x,l1)') c,accepted
  c=30; accepted=joint_bulk_candidate_absence_is_valid(transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3670000000000000',int64),0.0_real64), &
      transfer(int(z'3600624dd2f1a9fc',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'3ff4000000000000',int64),0.0_real64), &
      transfer(int(z'4059000000000000',int64),0.0_real64), &
      transfer(int(z'408c200000000000',int64),0.0_real64), &
      transfer(int(z'3670000000000000',int64),0.0_real64), &
      transfer(int(z'3600624dd2f1a9fc',int64),0.0_real64))
  write(*,'(i0,1x,l1)') c,accepted
  c=31; accepted=joint_bulk_candidate_absence_is_valid(transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'bf800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3670000000000000',int64),0.0_real64), &
      transfer(int(z'3600624dd2f1a9fc',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'4059000000000000',int64),0.0_real64), &
      transfer(int(z'408c200000000000',int64),0.0_real64), &
      transfer(int(z'b670000000000000',int64),0.0_real64), &
      transfer(int(z'b600624dd2f1a9fc',int64),0.0_real64))
  write(*,'(i0,1x,l1)') c,accepted
  c=32; accepted=joint_bulk_candidate_absence_is_valid(transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'7f61b1e6',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'7fe1ccf385ebc8a0',int64),0.0_real64), &
      transfer(int(z'7fe1ccf385ebc8a0',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'3ff0000000000000',int64),0.0_real64), &
      transfer(int(z'4059000000000000',int64),0.0_real64), &
      transfer(int(z'408c200000000000',int64),0.0_real64), &
      transfer(int(z'7ff0000000000000',int64),0.0_real64), &
      transfer(int(z'7ff0000000000000',int64),0.0_real64))
  write(*,'(i0,1x,l1)') c,accepted
  c=33; accepted=joint_bulk_candidate_absence_is_valid(transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'7ff8000000000000',int64),0.0_real64), &
      transfer(int(z'3680000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'4059000000000000',int64),0.0_real64), &
      transfer(int(z'408c200000000000',int64),0.0_real64), &
      transfer(int(z'36e9000000000000',int64),0.0_real64), &
      transfer(int(z'3680000000000000',int64),0.0_real64))
  write(*,'(i0,1x,l1)') c,accepted
  c=34; accepted=joint_bulk_candidate_absence_is_valid(transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3bc79ca10c924223',int64),0.0_real64), &
      transfer(int(z'00000000000007e8',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'7e031cfd3999f7b0',int64),0.0_real64), &
      transfer(int(z'7e37e43c8800759c',int64),0.0_real64), &
      transfer(int(z'3bc79ca10c924223',int64),0.0_real64), &
      transfer(int(z'00000000000007e8',int64),0.0_real64))
  write(*,'(i0,1x,l1)') c,accepted
  c=35; accepted=joint_bulk_candidate_absence_is_valid(transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'483d6329f1c35ca5',int64),0.0_real64), &
      transfer(int(z'09f3ae3591f5b4d9',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'7e37e43c8800759c',int64),0.0_real64), &
      transfer(int(z'7e37e43c8800759c',int64),0.0_real64), &
      transfer(int(z'483d6329f1c35ca5',int64),0.0_real64), &
      transfer(int(z'09f3ae3591f5b4d9',int64),0.0_real64))
  write(*,'(i0,1x,l1)') c,accepted
  c=36; accepted=joint_bulk_candidate_absence_is_valid(transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'36ff400000000000',int64),0.0_real64), &
      transfer(int(z'3670000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'4059000000000000',int64),0.0_real64), &
      transfer(int(z'408c200000000000',int64),0.0_real64), &
      transfer(int(z'36ff400000000000',int64),0.0_real64), &
      transfer(int(z'3670000000000000',int64),0.0_real64))
  write(*,'(i0,1x,l1)') c,accepted
  c=37; accepted=joint_bulk_candidate_absence_is_valid(transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'03800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'2f7f400000000000',int64),0.0_real64), &
      transfer(int(z'2ef0000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'4059000000000000',int64),0.0_real64), &
      transfer(int(z'408c200000000000',int64),0.0_real64), &
      transfer(int(z'36ff400000000000',int64),0.0_real64), &
      transfer(int(z'3670000000000000',int64),0.0_real64))
  write(*,'(i0,1x,l1)') c,accepted
  c=38; accepted=joint_bulk_candidate_absence_is_valid(transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'7fc55c576d815726',int64),0.0_real64), &
      transfer(int(z'7fc55c576d815726',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'4059000000000000',int64),0.0_real64), &
      transfer(int(z'408c200000000000',int64),0.0_real64), &
      transfer(int(z'7fc55c576d815726',int64),0.0_real64), &
      transfer(int(z'7fc55c576d815726',int64),0.0_real64))
  write(*,'(i0,1x,l1)') c,accepted
  c=39; accepted=joint_bulk_candidate_absence_is_valid(transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'7fc55c576d815726',int64),0.0_real64), &
      transfer(int(z'7fc55c576d815726',int64),0.0_real64), &
      transfer(int(z'ffc55c576d815726',int64),0.0_real64), &
      transfer(int(z'ffc55c576d815726',int64),0.0_real64), &
      transfer(int(z'3ff0000000000000',int64),0.0_real64), &
      transfer(int(z'4059000000000000',int64),0.0_real64), &
      transfer(int(z'408c200000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64), &
      transfer(int(z'0000000000000000',int64),0.0_real64))
  write(*,'(i0,1x,l1)') c,accepted
  c=40; accepted=joint_bulk_candidate_absence_is_valid(transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'00000000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'3f800000',int32),0.0_real32), &
      transfer(int(z'370b580000000000',int64),0.0_real64), &
      transfer(int(z'367c000000000000',int64),0.0_real64), &
      transfer(int(z'b6f7700000000000',int64),0.0_real64), &
      transfer(int(z'b668000000000000',int64),0.0_real64), &
      transfer(int(z'3ff0000000000000',int64),0.0_real64), &
      transfer(int(z'4059000000000000',int64),0.0_real64), &
      transfer(int(z'408c200000000000',int64),0.0_real64), &
      transfer(int(z'36ff400000000000',int64),0.0_real64), &
      transfer(int(z'3670000000000000',int64),0.0_real64))
  write(*,'(i0,1x,l1)') c,accepted
end program bulk_absence_harness
