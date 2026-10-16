program test_pr87_number_volume_store
  use iso_fortran_env, only: real32, real64
  implicit none

  real(real32) :: q, n_specific, rho, pidnr, power, lambda_min, lambda_max
  real(real32) :: q_stored, n_volume, ordinary_volume, q_before, n_before
  real(real64) :: delta_q, delta_nvolume, exact_volume
  integer :: adjustment, n_bits_before
  logical :: valid
  external :: pr87_number_volume_store

  ! A normal pair whose continuous upper bound is exact, while the ordinary
  ! R32 volume product rounds just above it. The adapter may move Q one ULP;
  ! it must retain the input specific-number bits and ordinary N-volume.
  q = 1.0_real32
  n_specific = 1.0000003576278687_real32
  rho = 1.2345670461654663_real32
  pidnr = 1.0_real32
  power = 1.0_real32
  lambda_min = n_specific/2.0_real32
  lambda_max = n_specific
  q_before = q
  n_before = n_specific
  n_bits_before = transfer(n_specific,0)
  exact_volume = real(n_specific,real64)*real(rho,real64)
  ordinary_volume = real(exact_volume,real32)

  call pr87_number_volume_store(q,n_specific,rho,pidnr,power,lambda_min,lambda_max, &
                              q_stored,n_volume,valid,delta_q,delta_nvolume,adjustment)
  if (.not.valid .or. adjustment /= 2 .or. q_stored <= q) &
    error stop 'strict volume crossing did not choose directed Q'
  if (n_specific /= n_before .or. transfer(n_specific,0) /= n_bits_before) &
    error stop 'directed Q storage changed public specific N'
  if (n_volume /= ordinary_volume) error stop 'volume N was not ordinary R32 product'
  if (delta_q /= real(q_stored,real64)-real(q_before,real64)) &
    error stop 'Q delta does not match stored representation'
  if (delta_nvolume /= real(ordinary_volume,real64)-exact_volume) &
    error stop 'volume N delta does not match ordinary rounding'

  ! Ordinary normal and subnormal pairs retain their independently rounded Q
  ! and N representations when both satisfy the selected strict volume cone.
  q = 1.0e-4_real32
  n_specific = 1.0e-3_real32
  rho = 1.2_real32
  pidnr = 1.0_real32
  power = 3.0_real32
  lambda_min = 1.0_real32
  lambda_max = 3.0_real32
  call pr87_number_volume_store(q,n_specific,rho,pidnr,power,lambda_min,lambda_max, &
                              q_stored,n_volume,valid,delta_q,delta_nvolume,adjustment)
  if (.not.valid .or. adjustment /= 0 .or. q_stored /= q .or. &
      n_volume /= real(real(n_specific,real64)*real(rho,real64),real32)) &
    error stop 'ordinary normal rain pair changed'

  q = 1.0e-40_real32
  n_specific = 1.0e-40_real32
  rho = 1.0_real32
  pidnr = 1.0_real32
  power = 3.0_real32
  lambda_min = 0.5_real32
  lambda_max = 2.0_real32
  call pr87_number_volume_store(q,n_specific,rho,pidnr,power,lambda_min,lambda_max, &
                              q_stored,n_volume,valid,delta_q,delta_nvolume,adjustment)
  if (.not.valid .or. adjustment /= 0 .or. q_stored /= q .or. n_volume /= n_specific) &
    error stop 'ordinary subnormal rain pair changed'

  ! True input absence is retained. The adapter has no option to erase a
  ! positive specific-number input to manufacture a paired absence.
  q = 0.0_real32
  n_specific = 0.0_real32
  call pr87_number_volume_store(q,n_specific,rho,pidnr,power,lambda_min,lambda_max, &
                              q_stored,n_volume,valid,delta_q,delta_nvolume,adjustment)
  if (.not.valid .or. adjustment /= 0 .or. q_stored /= 0.0_real32 .or. &
      n_volume /= 0.0_real32) error stop 'valid input absence was not preserved'

  ! Invalid continuous pairs and unrepresentable volume conversions reject
  ! atomically and return zero deltas.
  q = 1.0e-4_real32
  n_specific = 1.0e-1_real32
  call pr87_number_volume_store(q,n_specific,rho,pidnr,power,lambda_min,lambda_max, &
                              q_stored,n_volume,valid,delta_q,delta_nvolume,adjustment)
  if (valid .or. adjustment /= 0 .or. delta_q /= 0.0_real64 .or. &
      delta_nvolume /= 0.0_real64) error stop 'invalid continuous pair was repaired'
  if (q /= 1.0e-4_real32 .or. n_specific /= 1.0e-1_real32) &
    error stop 'invalid pair rejection mutated inputs'

  n_specific = huge(0.0_real32)
  rho = 2.0_real32
  call pr87_number_volume_store(q,n_specific,rho,pidnr,power,lambda_min,lambda_max, &
                              q_stored,n_volume,valid,delta_q,delta_nvolume,adjustment)
  if (valid .or. adjustment /= 0 .or. delta_q /= 0.0_real64 .or. &
      delta_nvolume /= 0.0_real64) error stop 'overflowing volume store was accepted'

  print *, 'PR87 rain specific-to-volume store cases PASS'
end program test_pr87_number_volume_store
