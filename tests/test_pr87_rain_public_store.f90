program test_pr87_rain_public_store
  use iso_fortran_env, only: real32, real64
  implicit none

  real(real32) :: q_internal, nvol_internal, rho, pidnr, power, lambda_min, lambda_max
  real(real32) :: q_public, n_specific, q_before, nvol_before
  real(real64) :: delta_q, delta_n
  integer :: adjustment
  logical :: valid
  external :: pr87_rain_public_store

  q_internal = 1.0e-4_real32
  nvol_internal = 1.0e-3_real32
  rho = 1.0_real32
  pidnr = 1.0_real32
  power = 3.0_real32
  lambda_min = 2.0_real32
  lambda_max = 3.0_real32
  q_before = q_internal
  nvol_before = nvol_internal

  call pr87_rain_public_store(q_internal,nvol_internal,rho,pidnr,power, &
                                   lambda_min,lambda_max,q_public,n_specific,valid, &
                                   delta_q,delta_n,adjustment)
  if (.not.valid .or. adjustment /= 0 .or. q_public /= q_internal .or. &
      n_specific /= nvol_internal) error stop 'valid public rain pair did not round-trip'
  if (delta_q /= 0.0_real64 .or. delta_n /= 0.0_real64) &
    error stop 'ordinary public rain storage reported a nonzero delta'
  if (q_internal /= q_before .or. nvol_internal /= nvol_before) &
    error stop 'public rain conversion mutated its input state'

  nvol_internal = 3.0e-3_real32
  nvol_before = nvol_internal
  call pr87_rain_public_store(q_internal,nvol_internal,rho,pidnr,power, &
                                   lambda_min,lambda_max,q_public,n_specific,valid, &
                                   delta_q,delta_n,adjustment)
  if (valid .or. adjustment /= 0 .or. delta_q /= 0.0_real64 .or. &
      delta_n /= 0.0_real64) error stop 'invalid continuous public rain pair was repaired'
  if (q_internal /= q_before .or. nvol_internal /= nvol_before) &
    error stop 'rejected public rain conversion mutated its input state'
  print *, 'PR87 rain public store cases PASS'
end program test_pr87_rain_public_store
