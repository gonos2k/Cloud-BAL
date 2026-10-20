module cloud_bal_joint_transport
  use iso_fortran_env, only: int32, real32, real64
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  implicit none
  private

  ! Exact binary32 minimum subnormal. Keep the REAL64 quantum normal and
  ! construct the REAL32 value by bits; converting a NEAREST result is not
  ! reliable with every pinned Intel code path.
  real(real64), parameter :: real32_quantum64 = scale(1.0_real64, -149)
  real(real32), parameter :: real32_quantum = transfer(1_int32, 0.0_real32)

  public :: joint_moment_is_valid, joint_moment_is_valid64, joint_moment_store, joint_qnb_update

contains

  logical function joint_moment_is_valid(q, n, dry_density, minimum_ratio, maximum_ratio, &
                                         inactive_mass_limit)
    ! Test one stored REAL32 pair with the same representation and endpoint
    ! tolerance used by the grouped candidate and its source-only diagnostic.
    real(real32), intent(in) :: q, n, dry_density
    real(real64), intent(in) :: minimum_ratio, maximum_ratio
    real(real64), intent(in), optional :: inactive_mass_limit
    joint_moment_is_valid = joint_moment_is_valid64(real(q,real64), real(n,real64), &
        dry_density, minimum_ratio, maximum_ratio, inactive_mass_limit)
  end function joint_moment_is_valid

  subroutine joint_moment_store(q64, n64, dry_density, minimum_ratio, maximum_ratio, &
                                allow_subnormal, stored_q, stored_n, adjustment, valid, &
                                allow_normal_q_adjustment, allow_joint_quantum_absence, &
                                volume_number_bounds, strict_mass_ratio, inactive_mass_limit, &
                                failure_stage, allow_inactive_q_quantum_adjustment, &
                                allow_bulk_volume_quantum_absence)
    ! Store an already valid continuous pair. Opt-in repairs preserve the
    ! continuous gate: subnormal Q underflow can store joint absence; legacy
    ! one-neighbor Q repair handles PSD rounding; strict-volume normal-Q repair
    ! selects from the dual-product and mean-mass interval with rounded N fixed.
    real(real64), intent(in) :: q64, n64, minimum_ratio, maximum_ratio
    real(real32), intent(in) :: dry_density
    logical, intent(in) :: allow_subnormal
    real(real32), intent(out) :: stored_q, stored_n
    integer, intent(out) :: adjustment
    logical, intent(out) :: valid
    logical, intent(in), optional :: allow_normal_q_adjustment
    logical, intent(in), optional :: allow_joint_quantum_absence
    real(real64), intent(in), optional :: volume_number_bounds(2)
    logical, intent(in), optional :: strict_mass_ratio
    real(real64), intent(in), optional :: inactive_mass_limit
    integer, intent(out), optional :: failure_stage
    logical, intent(in), optional :: allow_inactive_q_quantum_adjustment
    logical, intent(in), optional :: allow_bulk_volume_quantum_absence
    real(real32) :: rounded_q, rounded_n, adjusted_q, directed_q
    real(real64) :: ratio, minimum_number, maximum_number, inactive_number_quantum_limit
    real(real32) :: number_volume32
    logical :: allow_normal, allow_quantum_absence, use_volume_contract, volume_valid
    logical :: require_strict_mass, stored_mass_valid, use_inactive_mass_limit
    logical :: use_inactive_exact_store
    logical :: allow_inactive_q_quantum
    logical :: allow_bulk_absence
    logical :: need_q_up, need_q_down, directed_valid

    stored_q = -1.0_real32
    stored_n = -1.0_real32
    adjustment = 0
    valid = .false.
    if (present(failure_stage)) failure_stage = 1
    allow_normal = .false.
    allow_quantum_absence = .false.
    require_strict_mass = .false.
    use_inactive_exact_store = .false.
    allow_inactive_q_quantum = .false.
    allow_bulk_absence = .false.
    use_inactive_mass_limit = present(inactive_mass_limit)
    use_volume_contract = present(volume_number_bounds)
    if (present(allow_normal_q_adjustment)) allow_normal = allow_normal_q_adjustment
    if (present(allow_joint_quantum_absence)) allow_quantum_absence = allow_joint_quantum_absence
    if (present(strict_mass_ratio)) require_strict_mass = strict_mass_ratio
    if (present(allow_inactive_q_quantum_adjustment)) &
      allow_inactive_q_quantum = allow_inactive_q_quantum_adjustment
    if (present(allow_bulk_volume_quantum_absence)) &
      allow_bulk_absence = allow_bulk_volume_quantum_absence
    if (allow_bulk_absence .and. &
        (.not.allow_subnormal .or. .not.allow_quantum_absence .or. &
         .not.require_strict_mass .or. use_volume_contract)) return
    if (allow_inactive_q_quantum .and. &
        (.not.allow_subnormal .or. .not.use_inactive_mass_limit .or. &
         .not.allow_quantum_absence)) return
    if (use_inactive_mass_limit) then
      if (.not.ieee_is_finite(inactive_mass_limit)) return
      if (inactive_mass_limit<0.0_real64) return
      if (inactive_mass_limit>0.0_real64) then
        if (require_strict_mass .or. use_volume_contract .or. allow_bulk_absence) return
      end if
    end if
    ! A declared joint-absence store may represent a positive inactive pair
    ! when Q rounds to zero and N is bounded to one minimum-mass quantum.
    ! This narrow fallback precedes continuous N*rho representability, which
    ! is irrelevant once both stored moments are absent. Legacy-valid pairs
    ! continue through their original storage policy below.
    if (use_inactive_mass_limit) then
      if (inactive_mass_limit>0.0_real64 .and. allow_quantum_absence) then
        if (ieee_is_finite(q64) .and. ieee_is_finite(n64) .and. &
            ieee_is_finite(dry_density) .and. ieee_is_finite(minimum_ratio) .and. &
            ieee_is_finite(maximum_ratio)) then
          if (q64>0.0_real64 .and. n64>0.0_real64 .and. dry_density>0.0_real32 .and. &
              minimum_ratio>0.0_real64 .and. maximum_ratio>=minimum_ratio .and. &
              q64<=inactive_mass_limit .and. &
              q64<=real(huge(0.0_real32),real64) .and. &
              n64<=real(huge(0.0_real32),real64)) then
            if (.not.joint_moment_is_valid64(q64,n64,dry_density,minimum_ratio,maximum_ratio)) then
              inactive_number_quantum_limit=nearest( &
                  real32_quantum64/minimum_ratio,-1.0_real64)
              if (n64<=inactive_number_quantum_limit) then
                rounded_q=real(q64,real32)
                if (rounded_q==0.0_real32) then
                  stored_q=0.0_real32
                  stored_n=0.0_real32
                  adjustment=3
                  valid=.true.
                  if (present(failure_stage)) failure_stage=0
                  return
                end if
              end if
            end if
          end if
        end if
      end if
    end if
    if (present(failure_stage)) failure_stage = 2
    if (require_strict_mass) then
      if (.not. strict_mass_ratio_valid64(q64,n64,minimum_ratio,maximum_ratio)) return
      if (.not.ieee_is_finite(dry_density)) return
      if (dry_density<=0.0_real32) return
    else
      stored_mass_valid = joint_moment_is_valid64(q64,n64,dry_density,minimum_ratio,maximum_ratio)
      if (.not.stored_mass_valid) then
        if (.not.use_inactive_mass_limit) return
        if (inactive_mass_limit<=0.0_real64) return
        if (.not.joint_moment_is_valid64(q64,n64,dry_density,minimum_ratio,maximum_ratio, &
                                         inactive_mass_limit)) return
        use_inactive_exact_store = .true.
      end if
    end if
    if (present(failure_stage)) failure_stage = 3
    if (use_volume_contract) then
      if (.not. volume_number_contract_valid(q64,n64,dry_density,volume_number_bounds)) return
    end if
    if (present(failure_stage)) failure_stage = 4
    if (abs(q64) > real(huge(0.0_real32),real64) .or. &
        abs(n64) > real(huge(0.0_real32),real64)) return

    rounded_q = real(q64,real32)
    rounded_n = real(n64,real32)
    if (allow_bulk_absence) then
      if (q64>0.0_real64 .and. n64>0.0_real64 .and. rounded_n==0.0_real32) then
        if (bulk_volume_absence_is_valid(q64,n64,rounded_q,minimum_ratio,maximum_ratio)) then
          stored_q=0.0_real32
          stored_n=0.0_real32
          adjustment=5
          valid=.true.
          if (present(failure_stage)) failure_stage=0
          return
        end if
      end if
    end if
    if (use_inactive_exact_store) then
      if (rounded_n<=0.0_real32) return
      if (rounded_q<=0.0_real32) then
        if (.not.allow_inactive_q_quantum) return
        if (q64<=0.0_real64 .or. q64>=real32_quantum64 .or. &
            q64>inactive_mass_limit .or. real32_quantum>inactive_mass_limit) return
        if (.not.joint_moment_is_valid(real32_quantum,rounded_n,dry_density, &
                                       minimum_ratio,maximum_ratio,inactive_mass_limit)) return
        if (.not.stored_number_volume_is_representable(rounded_n,dry_density)) return
        stored_q=real32_quantum
        stored_n=rounded_n
        adjustment=4
        valid=.true.
        if (present(failure_stage)) failure_stage=0
        return
      end if
      if (.not.joint_moment_is_valid(rounded_q,rounded_n,dry_density,minimum_ratio, &
                                     maximum_ratio,inactive_mass_limit)) return
      if (.not.stored_number_volume_is_representable(rounded_n,dry_density)) return
      stored_q=rounded_q
      stored_n=rounded_n
      adjustment=0
      valid=.true.
      if (present(failure_stage)) failure_stage=0
      return
    end if
    volume_valid = .true.
    if (use_volume_contract) then
      volume_valid = volume_number_stored_contract_valid(rounded_q,rounded_n, &
          dry_density,volume_number_bounds)
    end if
    stored_mass_valid = joint_moment_is_valid(rounded_q,rounded_n,dry_density, &
                                               minimum_ratio,maximum_ratio)
    if (require_strict_mass) stored_mass_valid = &
        strict_mass_ratio_valid64(real(rounded_q,real64),real(rounded_n,real64), &
                                  minimum_ratio,maximum_ratio)
    if (stored_mass_valid .and. volume_valid) then
      stored_q = rounded_q
      stored_n = rounded_n
      valid = .true.
      if (present(failure_stage)) failure_stage=0
      return
    end if
    if ((use_volume_contract .or. require_strict_mass) .and. allow_normal .and. &
        q64 >= real(tiny(0.0_real32),real64) .and. rounded_n > 0.0_real32) then
      if (present(failure_stage)) failure_stage = 5
      if (use_volume_contract) then
        call store_directed_q(q64,rounded_n,dry_density,minimum_ratio,maximum_ratio, &
            volume_number_bounds,.true.,require_strict_mass,directed_q,directed_valid)
      else
        call store_directed_q(q64,rounded_n,dry_density,minimum_ratio,maximum_ratio, &
            [0.0_real64,0.0_real64],.false.,require_strict_mass,directed_q,directed_valid)
      end if
      if (directed_valid) then
        stored_q = directed_q
        stored_n = rounded_n
        adjustment = 2
        valid = .true.
        if (present(failure_stage)) failure_stage=0
        return
      end if
    end if
    if (require_strict_mass .and. q64 >= real(tiny(0.0_real32),real64)) return
    if (.not. allow_subnormal .and. .not. allow_normal) return
    if (q64 <= 0.0_real64) return
    if (.not. allow_normal .and. q64 >= real(tiny(0.0_real32),real64)) return

    if (present(failure_stage)) failure_stage = 6
    if (allow_subnormal .and. q64 < real(tiny(0.0_real32),real64) .and. &
        rounded_q == 0.0_real32 .and. rounded_n > 0.0_real32) then
      stored_q = 0.0_real32
      stored_n = 0.0_real32
      adjustment = 1
      valid = joint_moment_is_valid(stored_q, stored_n, dry_density, minimum_ratio, maximum_ratio)
      if (valid .and. use_volume_contract) valid = &
          volume_number_stored_contract_valid(stored_q,stored_n,dry_density,volume_number_bounds)
      if (.not.valid) then
        stored_q = -1.0_real32
        stored_n = -1.0_real32
        adjustment = 0
      end if
      if (valid .and. present(failure_stage)) failure_stage=0
      return
    end if

    if (rounded_q <= 0.0_real32 .or. rounded_n <= 0.0_real32) return
    ratio = real(rounded_q,real64)/real(rounded_n,real64)
    need_q_up = ratio < minimum_ratio
    need_q_down = ratio > maximum_ratio
    if (use_volume_contract) then
      minimum_number = volume_number_bounds(1)*real(rounded_q,real64)
      maximum_number = volume_number_bounds(2)*real(rounded_q,real64)
      ratio = real(rounded_n,real64)*real(dry_density,real64)
      if (.not.ieee_is_finite(ratio) .or. &
          ratio > real(huge(0.0_real32),real64)) return
      number_volume32 = real(ratio,real32)
      ! The strict cone applies to both products: REAL64(rho*N) and the
      ! actual REAL32 product consumed by the next native call.
      if (ratio < minimum_number .or. real(number_volume32,real64) < minimum_number) &
        need_q_down = .true.
      if (ratio > maximum_number .or. real(number_volume32,real64) > maximum_number) &
        need_q_up = .true.
    end if
    if (need_q_up .and. need_q_down) return
    if (need_q_up) then
      adjusted_q = nearest(rounded_q,1.0_real32)
    else if (need_q_down) then
      adjusted_q = nearest(rounded_q,-1.0_real32)
    else
      return
    end if
    if (use_volume_contract .and. adjusted_q == rounded_q) return
    volume_valid = .true.
    if (use_volume_contract) then
      volume_valid = volume_number_stored_contract_valid(adjusted_q,rounded_n, &
          dry_density,volume_number_bounds)
    end if
    stored_mass_valid = joint_moment_is_valid(adjusted_q,rounded_n,dry_density, &
                                               minimum_ratio,maximum_ratio)
    if (require_strict_mass) stored_mass_valid = &
        strict_mass_ratio_valid64(real(adjusted_q,real64),real(rounded_n,real64), &
                                  minimum_ratio,maximum_ratio)
    if (.not.stored_mass_valid .or. .not.volume_valid) then
      if (allow_quantum_absence .and. q64 > 0.0_real64 .and. &
          q64 < real32_quantum64) then
        if (joint_moment_is_valid(0.0_real32,0.0_real32,dry_density, &
                                  minimum_ratio,maximum_ratio)) then
          if (use_volume_contract) then
            volume_valid = volume_number_stored_contract_valid(0.0_real32,0.0_real32, &
                dry_density,volume_number_bounds)
          else
            volume_valid = .true.
          end if
          if (.not.volume_valid) return
          ! The full signed Q/N representation losses are reported by caller.
          stored_q = 0.0_real32
          stored_n = 0.0_real32
          adjustment = 3
          valid = .true.
          if (present(failure_stage)) failure_stage=0
          return
        end if
      end if
      return
    end if
    stored_q = adjusted_q
    stored_n = rounded_n
    adjustment = 2
    valid = .true.
    if (present(failure_stage)) failure_stage=0
  end subroutine joint_moment_store

  logical function bulk_volume_absence_is_valid(q64,b64,q32,minimum_ratio,maximum_ratio)
    integer, parameter :: real128 = selected_real_kind(33,4931)
    real(real64), intent(in) :: q64,b64,minimum_ratio,maximum_ratio
    real(real32), intent(in) :: q32
    real(real128) :: q128,b128,min128,max128,eta128,q_loss_budget

    bulk_volume_absence_is_valid=.false.
    if (.not.all(ieee_is_finite([q64,b64,minimum_ratio,maximum_ratio])) .or. &
        .not.ieee_is_finite(q32)) return
    if (q64<=0.0_real64 .or. b64<=0.0_real64) return
    if (minimum_ratio<=0.0_real64 .or. maximum_ratio<minimum_ratio) return
    q128=real(q64,real128); b128=real(b64,real128)
    min128=real(minimum_ratio,real128); max128=real(maximum_ratio,real128)
    eta128=real(real32_quantum64,real128)
    ! Joint absence spends at most half a B quantum and the corresponding
    ! maximum-density Q packet. The caller accumulates these signed losses.
    if (b128>=0.5_real128*eta128) return
    q_loss_budget=0.5_real128*max128*eta128
    if (q128>=q_loss_budget) return
    if (q128<min128*b128 .or. q128>max128*b128) return
    bulk_volume_absence_is_valid=.true.
  end function bulk_volume_absence_is_valid

  subroutine store_directed_q(q64,rounded_n,dry_density,minimum_ratio,maximum_ratio, &
                              bounds,has_volume_contract,strict_mass_ratio,stored_q,valid)
    real(real64), intent(in) :: q64,minimum_ratio,maximum_ratio,bounds(2)
    real(real32), intent(in) :: rounded_n,dry_density
    logical, intent(in) :: has_volume_contract,strict_mass_ratio
    real(real32), intent(out) :: stored_q
    logical, intent(out) :: valid
    real(real64) :: number_volume64,number_volume32,lower_q,upper_q,target,midpoint
    real(real32) :: candidate_q
    logical :: pair_valid,volume_valid
    integer :: attempt,direction

    stored_q = -1.0_real32
    valid = .false.
    if (.not.ieee_is_finite(q64) .or. q64 < real(tiny(0.0_real32),real64) .or. &
        .not.ieee_is_finite(rounded_n) .or. rounded_n <= 0.0_real32) return
    lower_q = real(rounded_n,real64)*minimum_ratio
    upper_q = real(rounded_n,real64)*maximum_ratio
    if (has_volume_contract) then
      if (.not.ieee_is_finite(dry_density) .or. dry_density <= 0.0_real32 .or. &
          .not.all(ieee_is_finite(bounds)) .or. bounds(1) <= 0.0_real64 .or. &
          bounds(2) < bounds(1)) return
      number_volume64 = real(rounded_n,real64)*real(dry_density,real64)
      if (.not.ieee_is_finite(number_volume64) .or. &
          number_volume64 > real(huge(0.0_real32),real64)) return
      number_volume32 = real(real(number_volume64,real32),real64)
      lower_q = max(lower_q,max(number_volume64,number_volume32)/bounds(2))
      upper_q = min(upper_q,min(number_volume64,number_volume32)/bounds(1))
    end if
    if (.not.all(ieee_is_finite([lower_q,upper_q])) .or. lower_q <= 0.0_real64 .or. &
        lower_q > upper_q .or. lower_q > real(huge(0.0_real32),real64)) return
    upper_q = min(upper_q,real(huge(0.0_real32),real64))
    target = min(max(q64,lower_q),upper_q)
    candidate_q = real(target,real32)
    if (.not.ieee_is_finite(candidate_q) .or. candidate_q <= 0.0_real32) return
    if (real(candidate_q,real64) < lower_q) then
      candidate_q = nearest(candidate_q,1.0_real32)
    else if (real(candidate_q,real64) > upper_q) then
      candidate_q = nearest(candidate_q,-1.0_real32)
    end if
    if (.not.ieee_is_finite(candidate_q) .or. &
        real(candidate_q,real64) < lower_q .or. real(candidate_q,real64) > upper_q) return

    midpoint = lower_q + 0.5_real64*(upper_q-lower_q)
    do attempt=1,2
      pair_valid = joint_moment_is_valid(candidate_q,rounded_n,dry_density, &
                                          minimum_ratio,maximum_ratio)
      if (strict_mass_ratio) pair_valid = strict_mass_ratio_valid64( &
          real(candidate_q,real64),real(rounded_n,real64),minimum_ratio,maximum_ratio)
      volume_valid = .true.
      if (has_volume_contract) volume_valid = volume_number_stored_contract_valid( &
          candidate_q,rounded_n,dry_density,bounds)
      if (pair_valid .and. volume_valid) then
        stored_q = candidate_q
        valid = .true.
        return
      end if
      if (attempt == 2) return
      if (real(candidate_q,real64) <= midpoint) then
        direction = 1
      else
        direction = -1
      end if
      if (direction > 0 .and. candidate_q >= huge(0.0_real32)) return
      candidate_q = nearest(candidate_q,real(direction,real32))
      if (.not.ieee_is_finite(candidate_q) .or. &
          real(candidate_q,real64) < lower_q .or. real(candidate_q,real64) > upper_q) return
    end do
  end subroutine store_directed_q

  logical function strict_mass_ratio_valid64(q64,n64,minimum_ratio,maximum_ratio)
    real(real64), intent(in) :: q64,n64,minimum_ratio,maximum_ratio
    real(real64) :: ratio

    strict_mass_ratio_valid64 = .false.
    if (.not.ieee_is_finite(q64) .or. .not.ieee_is_finite(n64) .or. &
        .not.ieee_is_finite(minimum_ratio) .or. .not.ieee_is_finite(maximum_ratio)) return
    if (q64<0.0_real64 .or. n64<0.0_real64 .or. minimum_ratio<=0.0_real64 .or. &
        maximum_ratio<minimum_ratio) return
    if (q64==0.0_real64 .and. n64==0.0_real64) then
      strict_mass_ratio_valid64 = .true.
      return
    end if
    if (q64<=0.0_real64 .or. n64<=0.0_real64) return
    ratio = q64/n64
    if (.not.ieee_is_finite(ratio)) return
    strict_mass_ratio_valid64 = ratio>=minimum_ratio .and. ratio<=maximum_ratio
  end function strict_mass_ratio_valid64

  logical function volume_number_contract_valid(q64,n64,dry_density,bounds)
    real(real64), intent(in) :: q64,n64,bounds(2)
    real(real32), intent(in) :: dry_density
    real(real64) :: number_volume, minimum_number, maximum_number

    volume_number_contract_valid = .false.
    if (.not.ieee_is_finite(q64) .or. .not.ieee_is_finite(n64) .or. &
        .not.ieee_is_finite(dry_density) .or. .not.all(ieee_is_finite(bounds))) return
    if (q64<0.0_real64 .or. n64<0.0_real64 .or. dry_density<=0.0_real32 .or. &
        bounds(1)<=0.0_real64 .or. bounds(2)<bounds(1)) return
    number_volume=n64*real(dry_density,real64)
    minimum_number=bounds(1)*q64
    maximum_number=bounds(2)*q64
    if (.not.all(ieee_is_finite([number_volume,minimum_number,maximum_number]))) return
    volume_number_contract_valid=number_volume>=minimum_number .and. &
                                number_volume<=maximum_number
  end function volume_number_contract_valid

  logical function volume_number_stored_contract_valid(q,n,dry_density,bounds)
    real(real32), intent(in) :: q,n,dry_density
    real(real64), intent(in) :: bounds(2)
    real(real64) :: number_volume64, minimum_number, maximum_number
    real(real32) :: number_volume32

    volume_number_stored_contract_valid = .false.
    if (.not.volume_number_contract_valid(real(q,real64),real(n,real64), &
            dry_density,bounds)) return
    number_volume64=real(n,real64)*real(dry_density,real64)
    if (.not.ieee_is_finite(number_volume64) .or. &
        number_volume64>real(huge(0.0_real32),real64)) return
    number_volume32=real(number_volume64,real32)
    minimum_number=bounds(1)*real(q,real64)
    maximum_number=bounds(2)*real(q,real64)
    if (.not.all(ieee_is_finite([minimum_number,maximum_number]))) return
    volume_number_stored_contract_valid=real(number_volume32,real64)>=minimum_number .and. &
                                        real(number_volume32,real64)<=maximum_number
  end function volume_number_stored_contract_valid

  logical function stored_number_volume_is_representable(n,dry_density)
    real(real32), intent(in) :: n,dry_density
    real(real64) :: number_volume64
    real(real32) :: number_volume32

    stored_number_volume_is_representable=.false.
    if (.not.ieee_is_finite(n) .or. .not.ieee_is_finite(dry_density)) return
    if (n<=0.0_real32 .or. dry_density<=0.0_real32) return
    number_volume64=real(n,real64)*real(dry_density,real64)
    if (.not.ieee_is_finite(number_volume64) .or. &
        number_volume64<=0.5_real64*real32_quantum64 .or. &
        number_volume64>real(huge(0.0_real32),real64)) return
    number_volume32=real(number_volume64,real32)
    stored_number_volume_is_representable=ieee_is_finite(number_volume32) .and. &
                                          number_volume32>0.0_real32
  end function stored_number_volume_is_representable

  logical function joint_moment_is_valid64(q64, n64, dry_density, minimum_ratio, maximum_ratio, &
                                           inactive_mass_limit)
    real(real64), intent(in) :: q64, n64, minimum_ratio, maximum_ratio
    real(real32), intent(in) :: dry_density
    real(real64), intent(in), optional :: inactive_mass_limit
    real(real64) :: pair_ratio, tolerance, moment_per_volume
    logical :: inactive_mass

    joint_moment_is_valid64 = .false.
    if (.not. ieee_is_finite(q64) .or. .not. ieee_is_finite(n64) .or. &
        .not. ieee_is_finite(dry_density) .or. &
        .not. ieee_is_finite(minimum_ratio) .or. .not. ieee_is_finite(maximum_ratio)) return
    if (dry_density <= 0.0_real32 .or. minimum_ratio <= 0.0_real64 .or. &
        maximum_ratio < minimum_ratio) return
    if (present(inactive_mass_limit)) then
      if (.not.ieee_is_finite(inactive_mass_limit)) return
      if (inactive_mass_limit<0.0_real64) return
    end if
    if (q64 < 0.0_real64 .or. n64 < 0.0_real64 .or. &
        q64 > real(huge(0.0_real32),real64) .or. &
        n64 > real(huge(0.0_real32),real64)) return
    if (n64 > 0.0_real64) then
      moment_per_volume = n64*real(dry_density,real64)
      if (.not. ieee_is_finite(moment_per_volume) .or. &
          moment_per_volume <= 0.5_real64*real32_quantum64 .or. &
          moment_per_volume > real(huge(0.0_real32),real64)) return
    end if
    if (q64 == 0.0_real64) then
      if (n64 /= 0.0_real64) return
    else
      if (n64 == 0.0_real64) return
      inactive_mass=.false.
      if (present(inactive_mass_limit)) inactive_mass=q64<=inactive_mass_limit
      if (inactive_mass) then
        joint_moment_is_valid64=.true.
        return
      end if
      pair_ratio = q64/n64
      tolerance = 8.0_real64*abs(real(spacing(real(minimum_ratio,real32)),real64))
      if (pair_ratio < minimum_ratio-tolerance) return
      tolerance = 8.0_real64*abs(real(spacing(real(maximum_ratio,real32)),real64))
      if (pair_ratio > maximum_ratio+tolerance) return
    end if
    joint_moment_is_valid64 = .true.
  end function joint_moment_is_valid64

  subroutine joint_qnb_update(q_base, n_base, q_stage, n_stage, q_source, n_source, &
                              q_transport, n_transport, carrier_old, carrier_new, dry_density, &
                              dt, min_particle_mass, max_particle_mass, theta, &
                              rejected_q, rejected_n, feasible, joint_subnormal_storage, &
                              storage_delta_q, storage_delta_n, storage_adjustments, &
                              joint_constrained_storage, q_source_rate64, n_source_rate64, &
                              q_transport_rate64, n_transport_rate64, joint_quantum_absence, &
                              strict_number_pair, volume_number_bounds, number_pair_bounds, &
                              strict_mass_pairs, inactive_mass_limits, &
                              inactive_q_quantum_adjustment_pairs, inactive_q_quantum_adjustments, &
                              bulk_volume_quantum_absence, bulk_volume_absences, bulk_volume_delta)
    ! Pair columns are QC/QNC, QI/QNI, QR/QNR, and QG/QIB. The first three
    ! ratios are mean particle masses; QG/QIB is graupel bulk density because
    ! QIB is rime-volume mixing ratio (m3 kg-dry-1), not a number moment.
    ! Cell rows are flattened active cells. One theta is committed to every
    ! member so a rejected transport increment cannot separate Q from N.
    real(real32), intent(in) :: q_base(:,:), n_base(:,:), q_source(:,:), n_source(:,:)
    real(real32), intent(inout) :: q_stage(:,:), n_stage(:,:)
    real(real32), intent(in) :: q_transport(:,:), n_transport(:,:)
    real(real32), intent(in) :: carrier_old(:), carrier_new(:), dry_density(:), dt
    real(real64), intent(in) :: min_particle_mass(:), max_particle_mass(:)
    real(real64), intent(out) :: theta, rejected_q(:), rejected_n(:)
    logical, intent(out) :: feasible
    logical, intent(in), optional :: joint_subnormal_storage
    real(real64), intent(out), optional :: storage_delta_q(:), storage_delta_n(:)
    integer, intent(out), optional :: storage_adjustments(:)
    logical, intent(in), optional :: joint_constrained_storage
    real(real64), intent(in), optional :: q_source_rate64(:,:), n_source_rate64(:,:)
    real(real64), intent(in), optional :: q_transport_rate64(:,:), n_transport_rate64(:,:)
    logical, intent(in), optional :: joint_quantum_absence
    integer, intent(in), optional :: strict_number_pair
    real(real64), intent(in), optional :: volume_number_bounds(:,:)
    ! Per-cell bounds are [lower,upper] for each pair; an all-zero pair slice
    ! opts that pair out of the strict volume-number contract.
    real(real64), intent(in), optional :: number_pair_bounds(:,:,:)
    logical, intent(in), optional :: strict_mass_pairs(:)
    ! Opt-in q<=limit transient branch for ordinary number pairs only.
    real(real64), intent(in), optional :: inactive_mass_limits(:)
    ! Opt-in bounded positive-Q representation for inactive underflow cells.
    logical, intent(in), optional :: inactive_q_quantum_adjustment_pairs(:)
    integer, intent(out), optional :: inactive_q_quantum_adjustments(:)
    logical, intent(in), optional :: bulk_volume_quantum_absence
    integer, intent(out), optional :: bulk_volume_absences
    real(real64), intent(out), optional :: bulk_volume_delta(2)

    real(real32), allocatable :: q_candidate(:,:), n_candidate(:,:)
    real(real64), allocatable :: local_delta_q(:), local_delta_n(:)
    integer, allocatable :: local_adjustments(:)
    integer, allocatable :: local_inactive_q_quantum_adjustments(:)
    real(real64), allocatable :: inactive_mass_limit_by_pair(:)
    real(real64) :: low, high, trial
    integer :: iteration, cell, pair, ncells, npairs, adjustment, use_strict_pair
    integer :: local_bulk_volume_absences
    real(real64) :: local_bulk_volume_delta(2)
    logical, allocatable :: pair_has_volume_bounds(:)
    logical, allocatable :: pair_has_strict_mass(:)
    logical, allocatable :: pair_has_inactive_mass_limit(:)
    logical, allocatable :: pair_allows_inactive_q_quantum(:)
    logical :: use_joint_storage, use_constrained_storage, use_quantum_absence, storage_valid
    logical :: use_bulk_volume_absence

    feasible = .false.
    theta = 0.0_real64
    rejected_q = 0.0_real64
    rejected_n = 0.0_real64
    if (present(storage_delta_q)) storage_delta_q = 0.0_real64
    if (present(storage_delta_n)) storage_delta_n = 0.0_real64
    if (present(storage_adjustments)) storage_adjustments = 0
    if (present(inactive_q_quantum_adjustments)) inactive_q_quantum_adjustments = 0
    if (present(bulk_volume_absences)) bulk_volume_absences = 0
    if (present(bulk_volume_delta)) bulk_volume_delta = 0.0_real64
    use_joint_storage = .false.
    use_constrained_storage = .false.
    use_quantum_absence = .false.
    use_bulk_volume_absence = .false.
    if (present(bulk_volume_quantum_absence)) &
      use_bulk_volume_absence = bulk_volume_quantum_absence
    if (use_bulk_volume_absence .and. &
        (.not.present(bulk_volume_absences) .or. .not.present(bulk_volume_delta))) return
    use_strict_pair = 0
    if (present(joint_subnormal_storage)) use_joint_storage = joint_subnormal_storage
    if (present(joint_constrained_storage)) use_constrained_storage = joint_constrained_storage
    if (present(joint_quantum_absence)) use_quantum_absence = joint_quantum_absence
    if (present(strict_number_pair) .neqv. present(volume_number_bounds)) return
    if (present(number_pair_bounds) .and. present(strict_number_pair)) return
    if (present(strict_number_pair)) then
      if (.not.use_constrained_storage) return
      use_strict_pair = strict_number_pair
    end if
    if (present(number_pair_bounds) .and. .not.use_constrained_storage) return
    if (use_joint_storage .and. use_constrained_storage) return
    if (use_quantum_absence .and. .not. use_constrained_storage) return
    use_joint_storage = use_joint_storage .or. use_constrained_storage
    if (use_joint_storage) then
      if (.not. present(storage_delta_q) .or. .not. present(storage_delta_n) .or. &
          .not. present(storage_adjustments)) return
      if (size(storage_delta_q) /= size(q_base,2) .or. &
          size(storage_delta_n) /= size(q_base,2) .or. &
          size(storage_adjustments) /= size(q_base,2)) return
      storage_delta_q = 0.0_real64
      storage_delta_n = 0.0_real64
      storage_adjustments = 0
    else if (present(storage_delta_q) .or. present(storage_delta_n) .or. &
             present(storage_adjustments)) then
      return
    end if
    if (use_constrained_storage) then
      if (.not. present(q_source_rate64) .or. .not. present(n_source_rate64) .or. &
          .not. present(q_transport_rate64) .or. .not. present(n_transport_rate64)) return
    else if (present(q_source_rate64) .or. present(n_source_rate64) .or. &
             present(q_transport_rate64) .or. present(n_transport_rate64)) then
      return
    end if
    ncells = size(q_base, 1)
    npairs = size(q_base, 2)
    allocate(pair_has_volume_bounds(npairs))
    allocate(pair_has_strict_mass(npairs))
    allocate(pair_has_inactive_mass_limit(npairs))
    allocate(pair_allows_inactive_q_quantum(npairs))
    pair_has_volume_bounds = .false.
    pair_has_strict_mass = .false.
    pair_has_inactive_mass_limit = .false.
    pair_allows_inactive_q_quantum = .false.
    allocate(inactive_mass_limit_by_pair(npairs))
    inactive_mass_limit_by_pair = 0.0_real64
    if (present(inactive_mass_limits)) then
      if (size(inactive_mass_limits)/=npairs) return
      if (any(.not.ieee_is_finite(inactive_mass_limits))) return
      if (any(inactive_mass_limits<0.0_real64)) return
      inactive_mass_limit_by_pair=inactive_mass_limits
      pair_has_inactive_mass_limit=inactive_mass_limits>0.0_real64
      if (any(pair_has_inactive_mass_limit) .and. .not.use_constrained_storage) return
      do pair=1,npairs
        if (pair_has_inactive_mass_limit(pair) .and. pair/=2) return
      end do
    end if
    if (present(inactive_q_quantum_adjustment_pairs)) then
      if (size(inactive_q_quantum_adjustment_pairs)/=npairs) return
      pair_allows_inactive_q_quantum=inactive_q_quantum_adjustment_pairs
      if (any(pair_allows_inactive_q_quantum)) then
        if (.not.present(inactive_mass_limits) .or. .not.use_quantum_absence .or. &
            .not.present(inactive_q_quantum_adjustments)) return
        if (any(pair_allows_inactive_q_quantum .and. .not.pair_has_inactive_mass_limit)) return
      end if
    else if (present(inactive_q_quantum_adjustments)) then
      return
    end if
    if (present(inactive_q_quantum_adjustments)) then
      if (size(inactive_q_quantum_adjustments)/=npairs) return
      inactive_q_quantum_adjustments=0
    end if
    if (present(strict_mass_pairs)) then
      if (size(strict_mass_pairs) /= npairs) return
      pair_has_strict_mass = strict_mass_pairs
      if (any(pair_has_strict_mass) .and. .not.use_constrained_storage) return
    end if
    if (present(strict_number_pair)) then
      if (use_strict_pair < 1 .or. use_strict_pair > npairs) return
      if (size(volume_number_bounds,1) /= ncells .or. size(volume_number_bounds,2) /= 2) return
      if (any(.not.ieee_is_finite(volume_number_bounds)) .or. &
          any(volume_number_bounds(:,1) <= 0.0_real64) .or. &
          any(volume_number_bounds(:,2) < volume_number_bounds(:,1))) return
      pair_has_volume_bounds(use_strict_pair) = .true.
    end if
    if (present(number_pair_bounds)) then
      if (size(number_pair_bounds,1) /= ncells .or. size(number_pair_bounds,2) /= 2 .or. &
          size(number_pair_bounds,3) /= npairs) return
      do pair = 1, npairs
        if (any(.not.ieee_is_finite(number_pair_bounds(:,:,pair)))) return
        if (all(number_pair_bounds(:,:,pair) == 0.0_real64)) cycle
        if (any(number_pair_bounds(:,1,pair) <= 0.0_real64) .or. &
            any(number_pair_bounds(:,2,pair) < number_pair_bounds(:,1,pair))) return
        pair_has_volume_bounds(pair) = .true.
      end do
    end if
    if (any(pair_has_inactive_mass_limit .and. &
            (pair_has_volume_bounds .or. pair_has_strict_mass))) return
    if (use_bulk_volume_absence) then
      if (.not.use_constrained_storage .or. .not.use_quantum_absence .or. npairs<4) return
      if (.not.present(strict_mass_pairs)) return
      if (.not.pair_has_strict_mass(4)) return
      if (pair_has_volume_bounds(4) .or. pair_has_inactive_mass_limit(4)) return
      if (pair_allows_inactive_q_quantum(4)) return
    end if
    if (npairs == 0 .or. ncells == 0) return
    if (size(n_base,1) /= ncells .or. size(q_stage,1) /= ncells .or. &
        size(n_stage,1) /= ncells .or. size(q_source,1) /= ncells .or. &
        size(n_source,1) /= ncells .or. size(q_transport,1) /= ncells .or. &
        size(n_transport,1) /= ncells .or. size(n_base,2) /= npairs .or. &
        size(q_stage,2) /= npairs .or. size(n_stage,2) /= npairs .or. &
        size(q_source,2) /= npairs .or. size(n_source,2) /= npairs .or. &
        size(q_transport,2) /= npairs .or. size(n_transport,2) /= npairs .or. &
        size(carrier_old) /= ncells .or. size(carrier_new) /= ncells .or. &
        size(dry_density) /= ncells .or. &
        size(min_particle_mass) /= npairs .or. size(max_particle_mass) /= npairs .or. &
        size(rejected_q) /= npairs .or. size(rejected_n) /= npairs) return
    if (use_constrained_storage) then
      if (size(q_source_rate64,1) /= ncells .or. size(n_source_rate64,1) /= ncells .or. &
          size(q_transport_rate64,1) /= ncells .or. size(n_transport_rate64,1) /= ncells .or. &
          size(q_source_rate64,2) /= npairs .or. size(n_source_rate64,2) /= npairs .or. &
          size(q_transport_rate64,2) /= npairs .or. size(n_transport_rate64,2) /= npairs) return
    end if
    if (any(min_particle_mass <= 0.0_real64) .or. &
        any(max_particle_mass < min_particle_mass)) return
    if (.not. ieee_is_finite(dt) .or. dt <= 0.0_real32 .or. &
        any(.not. ieee_is_finite(carrier_old)) .or. &
        any(.not. ieee_is_finite(carrier_new)) .or. &
        any(.not. ieee_is_finite(dry_density)) .or. &
        any(.not. ieee_is_finite(q_base)) .or. any(.not. ieee_is_finite(n_base))) return
    if (.not. use_constrained_storage) then
      if (any(.not. ieee_is_finite(q_source)) .or. any(.not. ieee_is_finite(n_source)) .or. &
          any(.not. ieee_is_finite(q_transport)) .or. any(.not. ieee_is_finite(n_transport))) return
    end if
    if (any(.not. ieee_is_finite(min_particle_mass)) .or. &
        any(.not. ieee_is_finite(max_particle_mass))) return
    if (use_constrained_storage) then
      if (any(.not. ieee_is_finite(q_source_rate64)) .or. &
          any(.not. ieee_is_finite(n_source_rate64)) .or. &
          any(.not. ieee_is_finite(q_transport_rate64)) .or. &
          any(.not. ieee_is_finite(n_transport_rate64))) return
    end if
    if (any(carrier_old <= 0.0_real32) .or. any(carrier_new <= 0.0_real32) .or. &
        any(dry_density <= 0.0_real32)) return

    allocate(q_candidate(ncells,npairs), n_candidate(ncells,npairs))
    if (use_joint_storage) then
      allocate(local_delta_q(npairs), local_delta_n(npairs), local_adjustments(npairs))
      allocate(local_inactive_q_quantum_adjustments(npairs))
      local_bulk_volume_absences = 0
      call form_candidate(1.0_real64)
      if (.not. candidate_is_feasible()) return
      theta = 1.0_real64
    else
      call form_candidate(1.0_real64)
      if (candidate_is_feasible()) then
        theta = 1.0_real64
      else
        call form_candidate(0.0_real64)
        if (.not. candidate_is_feasible()) return
        low = 0.0_real64
        high = 1.0_real64
        do iteration = 1, 40
          trial = 0.5_real64*(low+high)
          call form_candidate(trial)
          if (candidate_is_feasible()) then
            low = trial
          else
            high = trial
          end if
        end do
        theta = low
      end if
    end if

    call form_candidate(theta)
    if (.not. candidate_is_feasible()) return
    do pair = 1, npairs
      do cell = 1, ncells
        if (use_constrained_storage) then
          rejected_q(pair) = rejected_q(pair) + &
            real(dt,real64)*(1.0_real64-theta)*q_transport_rate64(cell,pair)
          rejected_n(pair) = rejected_n(pair) + &
            real(dt,real64)*(1.0_real64-theta)*n_transport_rate64(cell,pair)
        else
          rejected_q(pair) = rejected_q(pair) + &
            real(dt,real64)*(1.0_real64-theta)*real(q_transport(cell,pair),real64)
          rejected_n(pair) = rejected_n(pair) + &
            real(dt,real64)*(1.0_real64-theta)*real(n_transport(cell,pair),real64)
        end if
      end do
    end do
    q_stage = q_candidate
    n_stage = n_candidate
    if (use_joint_storage) then
      storage_delta_q = local_delta_q
      storage_delta_n = local_delta_n
      storage_adjustments = local_adjustments
      if (present(bulk_volume_absences)) bulk_volume_absences = local_bulk_volume_absences
      if (present(bulk_volume_delta)) bulk_volume_delta = local_bulk_volume_delta
      if (present(inactive_q_quantum_adjustments)) &
        inactive_q_quantum_adjustments = local_inactive_q_quantum_adjustments
    end if
    feasible = .true.

  contains

    subroutine form_candidate(scale)
      real(real64), intent(in) :: scale
      real(real64) :: q_value, n_value, source_rate_q, source_rate_n
      real(real64) :: transport_rate_q, transport_rate_n
      real(real64) :: cell_volume_bounds(2)
      integer :: i, p

      if (use_joint_storage) then
        local_delta_q = 0.0_real64
        local_delta_n = 0.0_real64
        local_adjustments = 0
        local_inactive_q_quantum_adjustments = 0
        local_bulk_volume_absences = 0
        local_bulk_volume_delta = 0.0_real64
      end if
      do p = 1, npairs
        do i = 1, ncells
          if (use_constrained_storage) then
            source_rate_q = q_source_rate64(i,p)
            source_rate_n = n_source_rate64(i,p)
            transport_rate_q = q_transport_rate64(i,p)
            transport_rate_n = n_transport_rate64(i,p)
          else
            source_rate_q = real(q_source(i,p),real64)
            source_rate_n = real(n_source(i,p),real64)
            transport_rate_q = real(q_transport(i,p),real64)
            transport_rate_n = real(n_transport(i,p),real64)
          end if
          q_value = (real(carrier_old(i),real64)*real(q_base(i,p),real64) + &
            real(dt,real64)*(source_rate_q + scale*transport_rate_q)) &
            / real(carrier_new(i),real64)
          n_value = (real(carrier_old(i),real64)*real(n_base(i,p),real64) + &
            real(dt,real64)*(source_rate_n + scale*transport_rate_n)) &
            / real(carrier_new(i),real64)
          if (use_joint_storage) then
            if (pair_has_volume_bounds(p)) then
              if (present(number_pair_bounds)) then
                cell_volume_bounds = number_pair_bounds(i,:,p)
              else
                cell_volume_bounds = volume_number_bounds(i,:)
              end if
              call joint_moment_store(q_value, n_value, dry_density(i), min_particle_mass(p), &
                                      max_particle_mass(p), .true., q_candidate(i,p), &
                                      n_candidate(i,p), adjustment, storage_valid, &
                                      allow_normal_q_adjustment=use_constrained_storage, &
                                      allow_joint_quantum_absence=use_quantum_absence, &
                                      volume_number_bounds=cell_volume_bounds, &
                                      strict_mass_ratio=pair_has_strict_mass(p))
            else if (pair_has_inactive_mass_limit(p)) then
              call joint_moment_store(q_value, n_value, dry_density(i), min_particle_mass(p), &
                                      max_particle_mass(p), .true., q_candidate(i,p), &
                                      n_candidate(i,p), adjustment, storage_valid, &
                                      allow_normal_q_adjustment=use_constrained_storage, &
                                      allow_joint_quantum_absence=use_quantum_absence, &
                                      strict_mass_ratio=pair_has_strict_mass(p), &
                                      inactive_mass_limit=inactive_mass_limit_by_pair(p), &
                                      allow_inactive_q_quantum_adjustment= &
                                          pair_allows_inactive_q_quantum(p))
            else
              call joint_moment_store(q_value, n_value, dry_density(i), min_particle_mass(p), &
                                      max_particle_mass(p), .true., q_candidate(i,p), &
                                      n_candidate(i,p), adjustment, storage_valid, &
                                      allow_normal_q_adjustment=use_constrained_storage, &
                                      allow_joint_quantum_absence=use_quantum_absence, &
                                      strict_mass_ratio=pair_has_strict_mass(p), &
                                      allow_bulk_volume_quantum_absence= &
                                          use_bulk_volume_absence .and. p==4)
            end if
            if (.not. storage_valid) then
              q_candidate(i,p) = -1.0_real32
              n_candidate(i,p) = -1.0_real32
            else if (adjustment /= 0) then
              local_delta_q(p) = local_delta_q(p) + real(carrier_new(i),real64)* &
                  (real(q_candidate(i,p),real64)-q_value)
              local_delta_n(p) = local_delta_n(p) + real(carrier_new(i),real64)* &
                  (real(n_candidate(i,p),real64)-n_value)
              local_adjustments(p) = local_adjustments(p) + 1
              if (adjustment == 4) &
                local_inactive_q_quantum_adjustments(p) = &
                    local_inactive_q_quantum_adjustments(p) + 1
              if (adjustment == 5) then
                local_bulk_volume_absences=local_bulk_volume_absences+1
                local_bulk_volume_delta(1)=local_bulk_volume_delta(1)+real(carrier_new(i),real64)* &
                    (real(q_candidate(i,p),real64)-q_value)
                local_bulk_volume_delta(2)=local_bulk_volume_delta(2)+real(carrier_new(i),real64)* &
                    (real(n_candidate(i,p),real64)-n_value)
              end if
            end if
          else if (.not. ieee_is_finite(q_value) .or. .not. ieee_is_finite(n_value) .or. &
              abs(q_value) > real(huge(0.0_real32),real64) .or. &
              abs(n_value) > real(huge(0.0_real32),real64)) then
            q_candidate(i,p) = -1.0_real32
            n_candidate(i,p) = -1.0_real32
          else
            q_candidate(i,p) = real(q_value,real32)
            n_candidate(i,p) = real(n_value,real32)
          end if
        end do
      end do
    end subroutine form_candidate

    logical function candidate_is_feasible()
      integer :: i, p
      real(real64) :: cell_volume_bounds(2)
      logical :: pair_valid

      candidate_is_feasible = .false.
      do p = 1, npairs
        do i = 1, ncells
          if (pair_has_inactive_mass_limit(p)) then
            pair_valid = joint_moment_is_valid(q_candidate(i,p),n_candidate(i,p),dry_density(i), &
                                               min_particle_mass(p),max_particle_mass(p), &
                                               inactive_mass_limit_by_pair(p))
          else
            pair_valid = joint_moment_is_valid(q_candidate(i,p),n_candidate(i,p),dry_density(i), &
                                               min_particle_mass(p),max_particle_mass(p))
          end if
          if (pair_has_strict_mass(p)) pair_valid = strict_mass_ratio_valid64( &
              real(q_candidate(i,p),real64),real(n_candidate(i,p),real64), &
              min_particle_mass(p),max_particle_mass(p))
          if (.not.pair_valid) return
          if (pair_has_volume_bounds(p)) then
            if (present(number_pair_bounds)) then
              cell_volume_bounds = number_pair_bounds(i,:,p)
            else
              cell_volume_bounds = volume_number_bounds(i,:)
            end if
            if (.not. volume_number_stored_contract_valid(q_candidate(i,p),n_candidate(i,p), &
                    dry_density(i),cell_volume_bounds)) return
          end if
        end do
      end do
      candidate_is_feasible = .true.
    end function candidate_is_feasible

  end subroutine joint_qnb_update

end module cloud_bal_joint_transport
