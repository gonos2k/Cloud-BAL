program test_pr87_cloud_public_store
  use iso_fortran_env, only: real32,real64
  implicit none
  real(real32), parameter :: pidnc=523.59881591796875_real32
  real(real32), parameter :: power=3.0_real32
  real(real32), parameter :: lambda_min=12000.0_real32,lambda_max=500000.0_real32
  real(real32) :: q_internal,nvol_internal,rho,q_public,n_specific
  real(real32) :: ordinary_n,ordinary_volume,q_before,nvol_before,nvol_adjacent
  real(real64) :: delta_q,delta_n,rho64,pid64,volume_min,volume_max
  real(real64) :: ratio_min,ratio_max,n64
  integer :: adjustment
  logical :: valid
  external :: pr87_rain_public_store

  ! This source-valid pair is one REAL32 public-volume quantum below the
  ! cloud lambda-max bound. Ordinary Nvolume/rho, then Nspecific*rho, crosses
  ! the strict upper cone after independent REAL32 rounding.
  rho=0.5512762665748596_real32
  q_internal=3.907963751453348e-20_real32
  nvol_internal=5.143173439137172e-6_real32
  q_before=q_internal; nvol_before=nvol_internal
  rho64=real(rho,real64); pid64=real(pidnc,real64)
  volume_min=rho64*real(lambda_min,real64)**3/pid64
  volume_max=rho64*real(lambda_max,real64)**3/pid64
  ratio_min=pid64/real(lambda_max,real64)**3
  ratio_max=pid64/real(lambda_min,real64)**3
  n64=real(nvol_internal,real64)/rho64
  ordinary_n=nvol_internal/rho
  ordinary_volume=ordinary_n*rho
  if (n64* rho64<volume_min*q_internal .or. n64*rho64>volume_max*q_internal) &
    error stop 'cloud public input is not continuously source-valid'
  if (real(q_internal,real64)/n64<ratio_min .or. &
      real(q_internal,real64)/n64>ratio_max) &
    error stop 'cloud public input violates continuous Q/N bounds'
  if (real(ordinary_volume,real64)<=volume_max*real(q_internal,real64)) &
    error stop 'ordinary REAL32 public division did not cross the upper cone'

  call pr87_rain_public_store(q_internal,nvol_internal,rho,pidnc,power, &
       lambda_min,lambda_max,q_public,n_specific,valid,delta_q,delta_n,adjustment)
  if (.not.valid .or. adjustment/=2 .or. q_public<=q_internal) &
    error stop 'cloud public store did not select an interior Q representation'
  if (n_specific/=ordinary_n) error stop 'cloud public store changed ordinary Nspecific'
  if (real(n_specific,real64)*rho64<volume_min*real(q_public,real64) .or. &
      real(n_specific,real64)*rho64>volume_max*real(q_public,real64)) &
    error stop 'cloud public output violates continuous volume bounds'
  if (real(n_specific*rho,real64)<volume_min*real(q_public,real64) .or. &
      real(n_specific*rho,real64)>volume_max*real(q_public,real64)) &
    error stop 'cloud public output violates REAL32 volume bounds'
  if (real(q_public,real64)/real(n_specific,real64)<ratio_min .or. &
      real(q_public,real64)/real(n_specific,real64)>ratio_max) &
    error stop 'cloud public output violates continuous Q/N bounds'
  if (delta_q/=real(q_public,real64)-real(q_internal,real64) .or. &
      delta_n/=real(n_specific,real64)-n64) &
    error stop 'cloud public storage ledger deltas are inconsistent'
  if (q_internal/=q_before .or. nvol_internal/=nvol_before) &
    error stop 'cloud public storage mutated its internal inputs'

  ! One REAL32 number step beyond the exact internal volume bound is rejected
  ! before division, even if divide/re-multiply could obscure that excess.
  nvol_adjacent=nearest(real(volume_max*real(q_internal,real64),real32),1.0_real32)
  if (real(nvol_adjacent,real64)<=volume_max*real(q_internal,real64)) &
    error stop 'adjacent cloud input did not exceed the exact volume bound'
  nvol_internal=nvol_adjacent
  nvol_before=nvol_internal
  call pr87_rain_public_store(q_internal,nvol_internal,rho,pidnc,power, &
       lambda_min,lambda_max,q_public,n_specific,valid,delta_q,delta_n,adjustment)
  if (valid .or. adjustment/=0 .or. delta_q/=0.0_real64 .or. delta_n/=0.0_real64) &
    error stop 'adjacent continuous-invalid cloud input was repaired'
  if (q_internal/=q_before .or. nvol_internal/=nvol_before) &
    error stop 'adjacent rejected cloud input was mutated'

  ! A more distant continuous-invalid input is also never repaired.
  nvol_internal=real(volume_max*real(q_internal,real64)*1.0001_real64,real32)
  nvol_before=nvol_internal
  call pr87_rain_public_store(q_internal,nvol_internal,rho,pidnc,power, &
       lambda_min,lambda_max,q_public,n_specific,valid,delta_q,delta_n,adjustment)
  if (valid .or. adjustment/=0 .or. delta_q/=0.0_real64 .or. delta_n/=0.0_real64) &
    error stop 'continuous-invalid cloud public input was repaired'
  if (q_internal/=q_before .or. nvol_internal/=nvol_before) &
    error stop 'rejected cloud public input was mutated'

  write(*,'(a)') 'PR87 cloud public-store strict crossing cases PASS'
end program test_pr87_cloud_public_store
