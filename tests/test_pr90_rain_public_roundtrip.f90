program test_pr90_rain_public_roundtrip
  use iso_fortran_env, only: real32, real64
  use cloud_bal_joint_transport, only: joint_moment_is_valid
  implicit none

  real(real32) :: q_internal, nvol_internal, rho, pidnr, power, lambda_min, lambda_max
  real(real32) :: q_public, n_specific, q_stored, n_volume
  real(real32) :: rho_up, rho_down
  real(real64) :: delta_q, delta_n, delta_q_back, delta_nvol
  integer :: adjustment, adjustment_back
  logical :: valid, valid_back
  character(len=32) :: failure_reason
  real(real64) :: diagnostic(12)
  integer :: stage, core_stage
  integer :: tries, side
  logical :: found_reconversion_overflow
  external :: pr90_rain_public_store_diagnostic, pr87_number_volume_store

  q_internal = 1.0e-4_real32
  nvol_internal = 1.0e-3_real32
  rho = 1.0_real32
  pidnr = 1.0_real32
  power = 3.0_real32
  lambda_min = 2.0_real32
  lambda_max = 3.0_real32

  call pr90_rain_public_store_diagnostic(q_internal,nvol_internal,rho,pidnr,power, &
      lambda_min,lambda_max,q_public,n_specific,valid,delta_q,delta_n, &
      adjustment,failure_reason,diagnostic,stage,core_stage)
  if (.not.valid .or. failure_reason /= 'none') error stop 'internal-to-public failed'
  call pr87_number_volume_store(q_public,n_specific,rho,pidnr,power, &
      lambda_min,lambda_max,q_stored,n_volume,valid_back,delta_q_back, &
      delta_nvol,adjustment_back)
  if (.not.valid_back) error stop 'public-to-volume failed'
  if (q_stored /= q_public .or. n_volume /= nvol_internal) &
      error stop 'public round trip changed the stored pair'
  if (.not.joint_moment_is_valid(q_stored,n_volume,rho, &
      real(pidnr,real64)/real(lambda_max,real64)**real(power,real64), &
      real(pidnr,real64)/real(lambda_min,real64)**real(power,real64))) &
      error stop 'consumer rejected round-tripped pair'

  nvol_internal = 3.0e-3_real32
  call pr90_rain_public_store_diagnostic(q_internal,nvol_internal,rho,pidnr,power, &
      lambda_min,lambda_max,q_public,n_specific,valid,delta_q,delta_n, &
      adjustment,failure_reason,diagnostic,stage,core_stage)
  if (valid .or. failure_reason /= 'internal_volume_precheck') &
      error stop 'invalid internal pair was not identified at precheck'

  q_internal = 3.0e38_real32
  nvol_internal = 4.0e9_real32
  rho = 1.0e-30_real32
  call pr90_rain_public_store_diagnostic(q_internal,nvol_internal,rho,pidnr,power, &
      lambda_min,lambda_max,q_public,n_specific,valid,delta_q,delta_n, &
      adjustment,failure_reason,diagnostic,stage,core_stage)
  if (valid .or. stage /= 6 .or. core_stage /= 2) &
      error stop 'over-range specific number did not fail safely in the joint store'
  if (diagnostic(2) <= real(huge(0.0_real32),real64)) &
      error stop 'overflow regression did not exceed REAL32 N range'
  if (diagnostic(3) /= -huge(0.0_real64)) &
      error stop 'overflow regression attempted or reported an unsafe REAL32 cast'

  q_internal = 3.0e37_real32
  nvol_internal = huge(0.0_real32)
  lambda_min = 1.0_real32
  lambda_max = 2.0_real32
  rho_up = 1.5_real32
  rho_down = rho_up
  found_reconversion_overflow = .false.
  do tries=1,128
    do side=1,2
      if (side == 1) then
        rho = rho_up
      else
        rho = rho_down
      end if
      call pr90_rain_public_store_diagnostic(q_internal,nvol_internal,rho,pidnr,power, &
          lambda_min,lambda_max,q_public,n_specific,valid,delta_q,delta_n, &
          adjustment,failure_reason,diagnostic,stage,core_stage)
      if (diagnostic(2) < real(huge(0.0_real32),real64) .and. &
          diagnostic(11) > real(huge(0.0_real32),real64)) then
        found_reconversion_overflow = .true.
        exit
      end if
    end do
    if (found_reconversion_overflow) exit
    rho_up = nearest(rho_up,1.0_real32)
    rho_down = nearest(rho_down,-1.0_real32)
  end do
  if (.not.found_reconversion_overflow) &
      error stop 'could not construct reconverted-product overflow case'
  if (diagnostic(12) /= -huge(0.0_real64)) &
      error stop 'reconverted-product overflow attempted an unsafe REAL32 cast'
  print *, 'PR90 rain public roundtrip cases PASS'
end program test_pr90_rain_public_roundtrip
