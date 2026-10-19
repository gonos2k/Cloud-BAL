subroutine pr90_rain_public_store_diagnostic(q_internal, nvol_internal, dry_density, pidnr, power, &
                                  lambda_min, lambda_max, q_public, n_specific, valid, &
                                  delta_q, delta_n, adjustment, failure_reason, diagnostic, stage, core_stage)
  use iso_fortran_env, only: real32, real64, int32, int64
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  use cloud_bal_joint_transport, only: joint_moment_store
  implicit none
    ! Convert the internal KDM6 volume number to public specific number, then store
    ! both moments under the exact source-derived R32 volume-number contract.
    real(real32), intent(in) :: q_internal, nvol_internal, dry_density
    real(real32), intent(in) :: pidnr, power, lambda_min, lambda_max
    real(real32), intent(out) :: q_public, n_specific
    logical, intent(out) :: valid
    real(real64), intent(out) :: delta_q, delta_n
    integer, intent(out) :: adjustment
    character(len=*), intent(out) :: failure_reason
    real(real64), intent(out) :: diagnostic(12)
    integer, intent(out) :: stage
    integer, intent(out) :: core_stage

    real(real64) :: q64, n64, rho64, pid64, power64, lambda_min64, lambda_max64
    real(real64) :: minimum_ratio, maximum_ratio, volume_bounds(2)
    real(real64) :: qstored, nstored
    real(real32) :: stored_q, stored_n
    integer :: jointstore_stage

    q_public = -1.0_real32
    n_specific = -1.0_real32
    valid = .false.
    delta_q = 0.0_real64
    delta_n = 0.0_real64
    adjustment = 0
    failure_reason = 'none'
    diagnostic = 0.0_real64
    diagnostic(3) = -huge(0.0_real64) ! Sentinel: no safe REAL32 Nspec conversion available.
    diagnostic(12) = -huge(0.0_real64) ! Sentinel: reconverted N-volume is unavailable.
    stage = 0
    core_stage = -1

    if (.not.all(ieee_is_finite([q_internal,nvol_internal,dry_density,pidnr,power, &
                                 lambda_min,lambda_max]))) then
      failure_reason = 'input_nonfinite'
      return
    end if
    stage = 1
    if (q_internal < 0.0_real32 .or. nvol_internal < 0.0_real32 .or. &
        dry_density <= 0.0_real32 .or. pidnr <= 0.0_real32 .or. &
        power <= 0.0_real32 .or. power > 8.0_real32 .or. &
        lambda_min <= 0.0_real32 .or. lambda_max < lambda_min) then
      failure_reason = 'input_range'
      return
    end if
    stage = 2

    rho64 = real(dry_density,real64)
    pid64 = real(pidnr,real64)
    power64 = real(power,real64)
    lambda_min64 = real(lambda_min,real64)
    lambda_max64 = real(lambda_max,real64)
    if (power64*log(lambda_min64) < log(real(tiny(0.0_real32),real64)) .or. &
        power64*log(lambda_max64) > log(real(huge(0.0_real32),real64))) then
      failure_reason = 'lambda_power_range'
      return
    end if

    volume_bounds(1) = (rho64*lambda_min64**power64)/pid64
    volume_bounds(2) = (rho64*lambda_max64**power64)/pid64
    minimum_ratio = pid64/(lambda_max64**power64)
    maximum_ratio = pid64/(lambda_min64**power64)
    if (.not.all(ieee_is_finite([volume_bounds,minimum_ratio,maximum_ratio])) .or. &
        volume_bounds(1) <= 0.0_real64 .or. volume_bounds(2) < volume_bounds(1) .or. &
        volume_bounds(2) > real(huge(0.0_real32),real64) .or. &
        maximum_ratio < minimum_ratio) then
      failure_reason = 'volume_bound_invalid'
      return
    end if
    stage = 3
    diagnostic(4:8) = [rho64,minimum_ratio,maximum_ratio,volume_bounds(1),volume_bounds(2)]

    q64 = real(q_internal,real64)
    diagnostic(1) = q64
    diagnostic(9:10) = [volume_bounds(1)*q64,volume_bounds(2)*q64]
    stage = 4
    if (real(nvol_internal,real64) < volume_bounds(1)*q64 .or. &
        real(nvol_internal,real64) > volume_bounds(2)*q64) then
      failure_reason = 'internal_volume_precheck'
      diagnostic(2) = real(nvol_internal,real64)/rho64
      if (ieee_is_finite(diagnostic(2))) then
        if (diagnostic(2) >= 0.0_real64 .and. &
            diagnostic(2) <= real(huge(0.0_real32),real64)) then
          diagnostic(3) = real(real(diagnostic(2),real32),real64)
          diagnostic(11) = diagnostic(3)*rho64
          if (ieee_is_finite(diagnostic(11))) then
            if (diagnostic(11) >= 0.0_real64 .and. &
                diagnostic(11) <= real(huge(0.0_real32),real64)) &
              diagnostic(12) = real(real(diagnostic(11),real32),real64)
          end if
        end if
      end if
      return
    end if
    n64 = real(nvol_internal,real64)/rho64
    diagnostic(2) = n64
    stage = 5
    if (.not.ieee_is_finite(n64)) then
      failure_reason = 'unit_division'
      return
    end if
    failure_reason = 'jointstore_failed'
    stage = 6
    jointstore_stage = -1
    call joint_moment_store(q64,n64,dry_density,minimum_ratio,maximum_ratio,.true., &
                            stored_q,stored_n,adjustment,valid, &
                            allow_normal_q_adjustment=.true., &
                            allow_joint_quantum_absence=.true., &
                            volume_number_bounds=volume_bounds, &
                            failure_stage=jointstore_stage)
    core_stage = jointstore_stage
    if (.not.valid) then
      adjustment = 0
      if (ieee_is_finite(n64)) then
        if (n64 >= 0.0_real64 .and. n64 <= real(huge(0.0_real32),real64)) then
          diagnostic(3) = real(real(n64,real32),real64)
          diagnostic(11) = diagnostic(3)*rho64
          if (ieee_is_finite(diagnostic(11))) then
            if (diagnostic(11) >= 0.0_real64 .and. &
                diagnostic(11) <= real(huge(0.0_real32),real64)) &
              diagnostic(12) = real(real(diagnostic(11),real32),real64)
          end if
        end if
      end if
      return
    end if

    q_public = stored_q
    n_specific = stored_n
    qstored = real(stored_q,real64)
    nstored = real(stored_n,real64)
    delta_q = qstored-q64
    delta_n = nstored-n64
    failure_reason = 'none'
    stage = 7
end subroutine pr90_rain_public_store_diagnostic

subroutine pr87_rain_public_store(q_internal, nvol_internal, dry_density, pidnr, power, &
                                  lambda_min, lambda_max, q_public, n_specific, valid, &
                                  delta_q, delta_n, adjustment)
  use iso_fortran_env, only: real32, real64, int32, int64
  implicit none
  real(real32), intent(in) :: q_internal, nvol_internal, dry_density
  real(real32), intent(in) :: pidnr, power, lambda_min, lambda_max
  real(real32), intent(out) :: q_public, n_specific
  logical, intent(out) :: valid
  real(real64), intent(out) :: delta_q, delta_n
  integer, intent(out) :: adjustment
  character(len=32) :: ignored_reason
  real(real64) :: diagnostic(12)
  integer :: diagnostic_stage
  integer :: diagnostic_core_stage
  logical, save :: failure_reported = .false.
  external :: pr90_rain_public_store_diagnostic

  call pr90_rain_public_store_diagnostic(q_internal,nvol_internal,dry_density,pidnr, &
      power,lambda_min,lambda_max,q_public,n_specific,valid,delta_q,delta_n, &
      adjustment,ignored_reason,diagnostic,diagnostic_stage,diagnostic_core_stage)
  if (.not.valid .and. .not.failure_reported) then
    write(*,'(A,I0,1X,I0,1X,A,1X,7(Z8.8,1X))') 'PR90_RAIN_FAILURE stages=', &
        diagnostic_stage,diagnostic_core_stage, &
        trim(ignored_reason),transfer(q_internal,0_int32),transfer(nvol_internal,0_int32), &
        transfer(dry_density,0_int32),transfer(pidnr,0_int32),transfer(power,0_int32), &
        transfer(lambda_min,0_int32),transfer(lambda_max,0_int32)
    write(*,'(A,12(Z16.16,1X))') 'PR90_RAIN_FAILURE_DERIVED_HEX ', &
        transfer(diagnostic(1),0_int64),transfer(diagnostic(2),0_int64), &
        transfer(diagnostic(3),0_int64),transfer(diagnostic(4),0_int64), &
        transfer(diagnostic(5),0_int64),transfer(diagnostic(6),0_int64), &
        transfer(diagnostic(7),0_int64),transfer(diagnostic(8),0_int64), &
        transfer(diagnostic(9),0_int64),transfer(diagnostic(10),0_int64), &
        transfer(diagnostic(11),0_int64),transfer(diagnostic(12),0_int64)
    failure_reported = .true.
  end if
end subroutine pr87_rain_public_store

subroutine pr87_number_volume_store(q_specific, n_specific, dry_density, pidnr, power, &
                                   lambda_min, lambda_max, q_stored, n_volume, valid, &
                                   delta_q, delta_nvolume, adjustment)
  use iso_fortran_env, only: real32, real64
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  use cloud_bal_joint_transport, only: joint_moment_store
  implicit none
    ! Keep the public specific-number input fixed. Round its volume product
    ! normally, and use the shared joint store only to choose a representable Q if
    ! that representation alone breaks the selected rain cone.
    real(real32), intent(in) :: q_specific, n_specific, dry_density
    real(real32), intent(in) :: pidnr, power, lambda_min, lambda_max
    real(real32), intent(out) :: q_stored, n_volume
    logical, intent(out) :: valid
    real(real64), intent(out) :: delta_q, delta_nvolume
    integer, intent(out) :: adjustment

    real(real64) :: q64, n64, rho64, pid64, power64, lambda_min64, lambda_max64
    real(real64) :: minimum_ratio, maximum_ratio, volume_bounds(2), nvolume64
    real(real64) :: stored_q64, stored_n64
    real(real32) :: stored_q, stored_n_specific

    q_stored = -1.0_real32
    n_volume = -1.0_real32
    valid = .false.
    delta_q = 0.0_real64
    delta_nvolume = 0.0_real64
    adjustment = 0

    if (.not.all(ieee_is_finite([q_specific,n_specific,dry_density,pidnr,power, &
                                 lambda_min,lambda_max]))) return
    if (q_specific < 0.0_real32 .or. n_specific < 0.0_real32 .or. &
        dry_density <= 0.0_real32 .or. pidnr <= 0.0_real32 .or. &
        power <= 0.0_real32 .or. power > 8.0_real32 .or. &
        lambda_min <= 0.0_real32 .or. lambda_max < lambda_min) return

    rho64 = real(dry_density,real64)
    pid64 = real(pidnr,real64)
    power64 = real(power,real64)
    lambda_min64 = real(lambda_min,real64)
    lambda_max64 = real(lambda_max,real64)
    if (power64*log(lambda_min64) < log(real(tiny(0.0_real32),real64)) .or. &
        power64*log(lambda_max64) > log(real(huge(0.0_real32),real64))) return

    volume_bounds(1) = (rho64*lambda_min64**power64)/pid64
    volume_bounds(2) = (rho64*lambda_max64**power64)/pid64
    minimum_ratio = pid64/(lambda_max64**power64)
    maximum_ratio = pid64/(lambda_min64**power64)
    if (.not.all(ieee_is_finite([volume_bounds,minimum_ratio,maximum_ratio])) .or. &
        volume_bounds(1) <= 0.0_real64 .or. volume_bounds(2) < volume_bounds(1) .or. &
        volume_bounds(2) > real(huge(0.0_real32),real64) .or. &
        maximum_ratio < minimum_ratio) return

    q64 = real(q_specific,real64)
    n64 = real(n_specific,real64)
    nvolume64 = n64*rho64
    if (.not.ieee_is_finite(nvolume64) .or. &
        nvolume64 > real(huge(0.0_real32),real64)) return

    call joint_moment_store(q64,n64,dry_density,minimum_ratio,maximum_ratio,.true., &
                            stored_q,stored_n_specific,adjustment,valid, &
                            allow_normal_q_adjustment=.true., &
                            volume_number_bounds=volume_bounds)
    if (.not.valid) then
      adjustment = 0
      return
    end if
    ! Npub is already REAL32, so the kernel's ordinary N store must preserve
    ! it exactly. The adapter emits only the ordinary REAL32 volume product.
    if (stored_n_specific /= n_specific) then
      valid = .false.
      adjustment = 0
      return
    end if

    n_volume = real(nvolume64,real32)
    q_stored = stored_q
    stored_q64 = real(stored_q,real64)
    stored_n64 = real(n_volume,real64)
    delta_q = stored_q64-q64
    delta_nvolume = stored_n64-nvolume64
end subroutine pr87_number_volume_store
