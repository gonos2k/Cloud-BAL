module cloud_bal_joint_transport
  use iso_fortran_env, only: int32, int64, real32, real64
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  implicit none
  private

  ! Exact binary32 minimum subnormal. Keep the REAL64 quantum normal and
  ! construct the REAL32 value by bits; converting a NEAREST result is not
  ! reliable with every pinned Intel code path.
  real(real64), parameter :: real32_quantum64 = scale(1.0_real64, -149)
  real(real32), parameter :: real32_quantum = transfer(1_int32, 0.0_real32)

  public :: joint_moment_is_valid, joint_moment_is_valid64, joint_moment_store, joint_qnb_update
  public :: joint_bulk_candidate_absence_is_valid

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
                                allow_bulk_volume_quantum_storage)
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
    logical, intent(in), optional :: allow_bulk_volume_quantum_storage
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
    if (present(allow_bulk_volume_quantum_storage)) &
      allow_bulk_absence = allow_bulk_volume_quantum_storage
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
    ! Under the explicit bulk policy, a subnormal Q with positive rounded B
    ! may use the same directed projection as normal Q. Bound both signed
    ! event losses before accepting it; this is adjustment 2, not absence.
    if (allow_bulk_absence .and. require_strict_mass .and. .not.use_volume_contract .and. &
        q64 > 0.0_real64 .and. q64 < real(tiny(0.0_real32),real64) .and. &
        rounded_n > 0.0_real32) then
      if (present(failure_stage)) failure_stage=5
      call store_directed_q(q64,rounded_n,dry_density,minimum_ratio,maximum_ratio, &
          [0.0_real64,0.0_real64],.false.,.true.,directed_q,directed_valid, &
          allow_subnormal_q=.true.)
      if (directed_valid .and. &
          bulk_volume_loss_is_bounded(q64,n64,directed_q,rounded_n,maximum_ratio)) then
        stored_q=directed_q
        stored_n=rounded_n
        adjustment=2
        valid=.true.
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
    real(real128) :: q128,b128,min128,max128,eta128

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
    if (q128<min128*b128 .or. q128>max128*b128) return
    if (.not.bulk_volume_loss_is_bounded(q64,b64,0.0_real32,0.0_real32,maximum_ratio)) return
    bulk_volume_absence_is_valid=.true.
  end function bulk_volume_absence_is_valid

  logical function bulk_volume_loss_is_bounded(q64,b64,q32,b32,maximum_ratio)
    integer, parameter :: real128 = selected_real_kind(33,4931)
    real(real64), intent(in) :: q64,b64,maximum_ratio
    real(real32), intent(in) :: q32,b32
    real(real128) :: eta128,q_loss_budget,q_error,b_error

    bulk_volume_loss_is_bounded=.false.
    if (.not.all(ieee_is_finite([q64,b64,maximum_ratio])) .or. &
        .not.all(ieee_is_finite([q32,b32]))) return
    if (maximum_ratio<=0.0_real64) return
    eta128=real(real32_quantum64,real128)
    q_loss_budget=0.5_real128*real(maximum_ratio,real128)*eta128
    q_error=abs(real(q32,real128)-real(q64,real128))
    b_error=abs(real(b32,real128)-real(b64,real128))
    if (q_error>=q_loss_budget .or. b_error>=0.5_real128*eta128) return
    bulk_volume_loss_is_bounded=.true.
  end function bulk_volume_loss_is_bounded

  logical function joint_bulk_candidate_absence_is_valid(base_q,base_b,old_carrier,new_carrier,dt, &
      dry_density,source_q,source_b,transport_q,transport_b,trial_scale,minimum_ratio,maximum_ratio, &
      reference_q,reference_b)
    integer, parameter :: real128=selected_real_kind(33,4931)
    real(real32), intent(in) :: base_q,base_b,old_carrier,new_carrier,dt,dry_density
    real(real64), intent(in) :: source_q,source_b,transport_q,transport_b,trial_scale
    real(real64), intent(in) :: minimum_ratio,maximum_ratio,reference_q,reference_b
    real(real64) :: regenerated_q,regenerated_b
    real(real128) :: theta,dt128,old128,new128,min128,max128,eta128
    real(real128) :: source_q_lo,source_q_hi,source_b_lo,source_b_hi
    real(real128) :: transport_q_lo,transport_q_hi,transport_b_lo,transport_b_hi
    real(real128) :: amount_q_lo,amount_q_hi,amount_b_lo,amount_b_hi
    real(real128) :: base_q128,base_b128,numer_q_lo,numer_q_hi,numer_b_lo,numer_b_hi
    real(real128) :: lower_cone,upper_cone,b_budget,q_budget,source_abs,amount_abs
    real(real128) :: scaled_q_lo,scaled_q_hi,scaled_b_lo,scaled_b_hi
    real(real128) :: safe_r64_limit, safe_candidate_limit, safe_r32_limit

    joint_bulk_candidate_absence_is_valid=.false.
    if (.not.all(ieee_is_finite([source_q,source_b,transport_q,transport_b,trial_scale, &
        minimum_ratio,maximum_ratio,reference_q,reference_b]))) return
    if (.not.all(ieee_is_finite([base_q,base_b,old_carrier,new_carrier,dt,dry_density]))) return
    if (trial_scale<0.0_real64 .or. trial_scale>1.0_real64 .or. dt<=0.0_real32) return
    if (old_carrier<=0.0_real32 .or. new_carrier<=0.0_real32 .or. dry_density<=0.0_real32) return
    if (minimum_ratio<=0.0_real64 .or. maximum_ratio<minimum_ratio) return
    if (base_q<0.0_real32 .or. base_b<0.0_real32) return
    if (reference_q<=0.0_real64 .or. reference_b<=0.0_real64) return
    safe_r32_limit=real(huge(0.0_real32),real128)
    if (reference_q>real(huge(0.0_real32),real64) .or. &
        reference_b>real(huge(0.0_real32),real64)) return
    if (.not.bulk_volume_loss_is_bounded(reference_q,reference_b,0.0_real32,0.0_real32,maximum_ratio)) return

    theta=real(trial_scale,real128); dt128=real(dt,real128)
    old128=real(old_carrier,real128); new128=real(new_carrier,real128)
    min128=real(minimum_ratio,real128); max128=real(maximum_ratio,real128)
    eta128=real(real32_quantum64,real128)

    ! Prove the ordered R64 reference expression cannot overflow before
    ! recomputing it. The bounds are widened outward and are deliberately
    ! conservative in cancellation cases.
    ! Factor-four headroom keeps a few R64 roundings below overflow even
    ! when the exact magnitudes approach HUGE; it only narrows this fallback.
    safe_r64_limit=0.25_real128*real(huge(0.0_real64),real128)
    source_abs=interval_abs_sum(real(source_q,real128),theta,real(transport_q,real128))
    if (.not.ieee_is_finite(source_abs) .or. source_abs>=safe_r64_limit) return
    amount_abs=interval_abs_sum(real(base_q,real128)*old128,dt128,source_abs)
    if (.not.ieee_is_finite(amount_abs)) return
    safe_candidate_limit=safe_r64_limit*min(1.0_real128,new128)
    if (amount_abs>=safe_candidate_limit) return
    source_abs=interval_abs_sum(real(source_b,real128),theta,real(transport_b,real128))
    if (.not.ieee_is_finite(source_abs) .or. source_abs>=safe_r64_limit) return
    amount_abs=interval_abs_sum(real(base_b,real128)*old128,dt128,source_abs)
    if (.not.ieee_is_finite(amount_abs)) return
    if (amount_abs>=safe_candidate_limit) return

    regenerated_q=(real(old_carrier,real64)*real(base_q,real64)+ &
        real(dt,real64)*(source_q+trial_scale*transport_q))/real(new_carrier,real64)
    regenerated_b=(real(old_carrier,real64)*real(base_b,real64)+ &
        real(dt,real64)*(source_b+trial_scale*transport_b))/real(new_carrier,real64)
    if (.not.all(ieee_is_finite([regenerated_q,regenerated_b]))) return
    if (transfer(regenerated_q,0_int64)/=transfer(reference_q,0_int64) .or. &
        transfer(regenerated_b,0_int64)/=transfer(reference_b,0_int64)) return
    ! Enclose the complete extensive endpoint before division by the carrier.
    ! Two binary32 significands multiply exactly in binary128 (at most 48 bits).
    call interval_point(real(source_q,real128),source_q_lo,source_q_hi)
    call interval_product_nonnegative(real(trial_scale,real128), &
        real(transport_q,real128),transport_q_lo,transport_q_hi)
    call interval_add(source_q_lo,source_q_hi,transport_q_lo,transport_q_hi,amount_q_lo,amount_q_hi)
    call interval_scale_nonnegative(amount_q_lo,amount_q_hi,dt128,scaled_q_lo,scaled_q_hi)
    base_q128=old128*real(base_q,real128)
    call interval_add(base_q128,base_q128,scaled_q_lo,scaled_q_hi,numer_q_lo,numer_q_hi)

    call interval_point(real(source_b,real128),source_b_lo,source_b_hi)
    call interval_product_nonnegative(real(trial_scale,real128), &
        real(transport_b,real128),transport_b_lo,transport_b_hi)
    call interval_add(source_b_lo,source_b_hi,transport_b_lo,transport_b_hi,amount_b_lo,amount_b_hi)
    call interval_scale_nonnegative(amount_b_lo,amount_b_hi,dt128,scaled_b_lo,scaled_b_hi)
    base_b128=old128*real(base_b,real128)
    call interval_add(base_b128,base_b128,scaled_b_lo,scaled_b_hi,numer_b_lo,numer_b_hi)

    if (numer_q_lo<=0.0_real128 .or. numer_b_lo<=0.0_real128) return
    ! The pre-existing storage path rejects REAL64 references above REAL32
    ! range. Preserve that gate for the entire certified endpoint interval.
    safe_candidate_limit=nearest(safe_r32_limit*new128,-1.0_real128)
    if (numer_q_hi>safe_candidate_limit .or. numer_b_hi>safe_candidate_limit) return
    call interval_scale_nonnegative(numer_b_lo,numer_b_hi,min128,lower_cone,upper_cone)
    if (numer_q_lo<upper_cone) return
    call interval_scale_nonnegative(numer_b_lo,numer_b_hi,max128,lower_cone,upper_cone)
    if (numer_q_hi>lower_cone) return

    ! The budget products have at most 77 significand bits; one outward step
    ! makes each stored-endpoint ceiling conservative.
    b_budget=nearest(0.5_real128*eta128*new128,-1.0_real128)
    q_budget=nearest(0.5_real128*max128*eta128*new128,-1.0_real128)
    if (numer_b_hi>=b_budget .or. numer_q_hi>=q_budget) return
    joint_bulk_candidate_absence_is_valid=.true.
  end function joint_bulk_candidate_absence_is_valid

  subroutine interval_point(value,lower,upper)
    integer, parameter :: real128=selected_real_kind(33,4931)
    real(real128), intent(in) :: value
    real(real128), intent(out) :: lower,upper
    lower=nearest(value,-1.0_real128)
    upper=nearest(value,1.0_real128)
  end subroutine interval_point

  subroutine interval_product_nonnegative(factor,value,lower,upper)
    integer, parameter :: real128=selected_real_kind(33,4931)
    real(real128), intent(in) :: factor,value
    real(real128), intent(out) :: lower,upper
    real(real128) :: lo,hi
    call interval_point(value,lo,hi)
    lower=nearest(factor*lo,-1.0_real128)
    upper=nearest(factor*hi,1.0_real128)
  end subroutine interval_product_nonnegative

  subroutine interval_scale_nonnegative(lower_in,upper_in,factor,lower,upper)
    integer, parameter :: real128=selected_real_kind(33,4931)
    real(real128), intent(in) :: lower_in,upper_in,factor
    real(real128), intent(out) :: lower,upper
    lower=nearest(factor*lower_in,-1.0_real128)
    upper=nearest(factor*upper_in,1.0_real128)
  end subroutine interval_scale_nonnegative

  subroutine interval_add(a_lo,a_hi,b_lo,b_hi,lower,upper)
    integer, parameter :: real128=selected_real_kind(33,4931)
    real(real128), intent(in) :: a_lo,a_hi,b_lo,b_hi
    real(real128), intent(out) :: lower,upper
    lower=nearest(a_lo+b_lo,-1.0_real128)
    upper=nearest(a_hi+b_hi,1.0_real128)
  end subroutine interval_add

  real(selected_real_kind(33,4931)) function interval_abs_sum(a,factor,b)
    integer, parameter :: real128=selected_real_kind(33,4931)
    real(real128), intent(in) :: a,factor,b
    interval_abs_sum=nearest(abs(a)+nearest(factor*abs(b),1.0_real128),1.0_real128)
  end function interval_abs_sum

  subroutine store_directed_q(q64,rounded_n,dry_density,minimum_ratio,maximum_ratio, &
                              bounds,has_volume_contract,strict_mass_ratio,stored_q,valid, &
                              allow_subnormal_q)
    real(real64), intent(in) :: q64,minimum_ratio,maximum_ratio,bounds(2)
    real(real32), intent(in) :: rounded_n,dry_density
    logical, intent(in) :: has_volume_contract,strict_mass_ratio
    real(real32), intent(out) :: stored_q
    logical, intent(out) :: valid
    logical, intent(in), optional :: allow_subnormal_q
    real(real64) :: number_volume64,number_volume32,lower_q,upper_q,target,midpoint
    real(real32) :: candidate_q
    logical :: pair_valid,volume_valid
    integer :: attempt,direction
    logical :: permit_subnormal_q

    stored_q = -1.0_real32
    valid = .false.
    permit_subnormal_q=.false.
    if (present(allow_subnormal_q)) permit_subnormal_q=allow_subnormal_q
    if (.not.ieee_is_finite(q64) .or. q64<=0.0_real64 .or. &
        (q64 < real(tiny(0.0_real32),real64) .and. .not.permit_subnormal_q) .or. &
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
                              bulk_volume_quantum_storage, bulk_volume_absences, bulk_volume_delta, &
                              diagnostic_stage, diagnostic_candidate, diagnostic_stored, &
                              diagnostic_adjustment, diagnostic_scale, diagnostic_cells, &
                              group_failure_cell, group_failure_pair, group_failure_predicate, &
                              group_failure_store_stage, group_failure_candidate64, &
                              group_failure_stored32, group_failure_enabled)
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
    logical, intent(in), optional :: bulk_volume_quantum_storage
    integer, intent(out), optional :: bulk_volume_absences
    real(real64), intent(out), optional :: bulk_volume_delta(2)
    integer, intent(out), optional :: diagnostic_stage(:,:)
    real(real64), intent(out), optional :: diagnostic_candidate(:,:,:)
    real(real32), intent(out), optional :: diagnostic_stored(:,:,:)
    integer, intent(out), optional :: diagnostic_adjustment(:,:)
    real(real64), intent(out), optional :: diagnostic_scale(:,:)
    integer, intent(in), optional :: diagnostic_cells(:)
    integer, intent(out), optional :: group_failure_cell, group_failure_pair
    integer, intent(out), optional :: group_failure_predicate, group_failure_store_stage
    real(real64), intent(out), optional :: group_failure_candidate64(2)
    real(real32), intent(out), optional :: group_failure_stored32(2)
    logical, intent(in), optional :: group_failure_enabled

    real(real32), allocatable :: q_candidate(:,:), n_candidate(:,:)
    real(real64), allocatable :: local_delta_q(:), local_delta_n(:)
    integer, allocatable :: local_adjustments(:)
    integer, allocatable :: local_inactive_q_quantum_adjustments(:)
    integer, allocatable :: local_failure_stage(:,:)
    real(real64) :: failure_q64, failure_n64
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
    logical :: use_bulk_volume_absence, capture_group_failure
    integer :: local_store_stage

    feasible = .false.
    if (present(group_failure_cell)) group_failure_cell=0
    if (present(group_failure_pair)) group_failure_pair=0
    if (present(group_failure_predicate)) group_failure_predicate=0
    if (present(group_failure_store_stage)) group_failure_store_stage=0
    if (present(group_failure_candidate64)) group_failure_candidate64=0.0_real64
    if (present(group_failure_stored32)) group_failure_stored32=0.0_real32
    capture_group_failure=.false.
    if (present(group_failure_enabled)) capture_group_failure=group_failure_enabled
    if (present(diagnostic_stage)) diagnostic_stage = 0
    if (present(diagnostic_candidate)) diagnostic_candidate = 0.0_real64
    if (present(diagnostic_stored)) diagnostic_stored = 0.0_real32
    if (present(diagnostic_adjustment)) diagnostic_adjustment = 0
    if (present(diagnostic_scale)) diagnostic_scale = 0.0_real64
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
    if (present(bulk_volume_quantum_storage)) &
      use_bulk_volume_absence = bulk_volume_quantum_storage
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
    if (present(diagnostic_cells)) then
      if (.not.present(diagnostic_stage) .or. .not.present(diagnostic_candidate) .or. &
          .not.present(diagnostic_stored) .or. .not.present(diagnostic_adjustment) .or. &
          .not.present(diagnostic_scale)) return
      if (size(diagnostic_stage,1)/=size(diagnostic_cells) .or. &
          size(diagnostic_candidate,1)/=size(diagnostic_cells) .or. &
          size(diagnostic_candidate,2)/=2 .or. size(diagnostic_candidate,3)/=npairs .or. &
          size(diagnostic_stored,1)/=size(diagnostic_cells) .or. &
          size(diagnostic_stored,2)/=2 .or. size(diagnostic_stored,3)/=npairs .or. &
          size(diagnostic_adjustment,1)/=size(diagnostic_cells) .or. &
          size(diagnostic_scale,1)/=size(diagnostic_cells)) return
    end if
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
    if (present(group_failure_cell) .and. capture_group_failure) then
      if (.not.present(group_failure_pair) .or. .not.present(group_failure_predicate) .or. &
          .not.present(group_failure_store_stage) .or. .not.present(group_failure_candidate64) .or. &
          .not.present(group_failure_stored32)) return
      allocate(local_failure_stage(ncells,npairs)); local_failure_stage=0
    end if
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
      integer :: i, p, trace_cell

      if (present(diagnostic_stage)) diagnostic_stage = 0
      if (present(diagnostic_candidate)) diagnostic_candidate = 0.0_real64
      if (present(diagnostic_stored)) diagnostic_stored = 0.0_real32
      if (present(diagnostic_adjustment)) diagnostic_adjustment = 0
      if (present(diagnostic_scale)) diagnostic_scale = 0.0_real64
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
                                      strict_mass_ratio=pair_has_strict_mass(p), &
                                      failure_stage=local_store_stage)
            else if (pair_has_inactive_mass_limit(p)) then
              call joint_moment_store(q_value, n_value, dry_density(i), min_particle_mass(p), &
                                      max_particle_mass(p), .true., q_candidate(i,p), &
                                      n_candidate(i,p), adjustment, storage_valid, &
                                      allow_normal_q_adjustment=use_constrained_storage, &
                                      allow_joint_quantum_absence=use_quantum_absence, &
                                      strict_mass_ratio=pair_has_strict_mass(p), &
                                      inactive_mass_limit=inactive_mass_limit_by_pair(p), &
                                      allow_inactive_q_quantum_adjustment= &
                                          pair_allows_inactive_q_quantum(p), &
                                      failure_stage=local_store_stage)
            else
              call joint_moment_store(q_value, n_value, dry_density(i), min_particle_mass(p), &
                                      max_particle_mass(p), .true., q_candidate(i,p), &
                                      n_candidate(i,p), adjustment, storage_valid, &
                                      allow_normal_q_adjustment=use_constrained_storage, &
                                      allow_joint_quantum_absence=use_quantum_absence, &
                                      strict_mass_ratio=pair_has_strict_mass(p), &
                                      allow_bulk_volume_quantum_storage= &
                                          use_bulk_volume_absence .and. p==4, &
                                      failure_stage=local_store_stage)
              if (.not.storage_valid .and. use_bulk_volume_absence .and. p==4 .and. &
                  pair_has_strict_mass(p) .and. .not.pair_has_volume_bounds(p) .and. &
                  .not.pair_has_inactive_mass_limit(p)) then
                if (joint_bulk_candidate_absence_is_valid(q_base(i,p),n_base(i,p), &
                    carrier_old(i),carrier_new(i),dt,dry_density(i),source_rate_q,source_rate_n, &
                    transport_rate_q,transport_rate_n,scale,min_particle_mass(p),max_particle_mass(p), &
                    q_value,n_value)) then
                  q_candidate(i,p)=0.0_real32
                  n_candidate(i,p)=0.0_real32
                  adjustment=5
                  storage_valid=.true.
                end if
              end if
            end if
            if (.not. storage_valid) then
              if (allocated(local_failure_stage)) local_failure_stage(i,p)=local_store_stage
              if (present(diagnostic_cells)) then
                do trace_cell = 1, size(diagnostic_cells)
                  if (diagnostic_cells(trace_cell) /= i) cycle
                  if (present(diagnostic_stage)) diagnostic_stage(trace_cell,p) = local_store_stage
                  if (present(diagnostic_candidate)) then
                    diagnostic_candidate(trace_cell,1,p) = q_value
                    diagnostic_candidate(trace_cell,2,p) = n_value
                  end if
                  if (present(diagnostic_stored)) then
                    diagnostic_stored(trace_cell,1,p) = q_candidate(i,p)
                    diagnostic_stored(trace_cell,2,p) = n_candidate(i,p)
                  end if
                  if (present(diagnostic_adjustment)) diagnostic_adjustment(trace_cell,p) = adjustment
                  if (present(diagnostic_scale)) diagnostic_scale(trace_cell,p) = scale
                end do
              end if
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

    subroutine record_group_failure(i,p,predicate)
      integer, intent(in) :: i,p,predicate
      if (.not.present(group_failure_cell) .or. .not.capture_group_failure) return
      if (group_failure_cell/=0) return
      group_failure_cell=i; group_failure_pair=p; group_failure_predicate=predicate
      if (allocated(local_failure_stage)) group_failure_store_stage=local_failure_stage(i,p)
      group_failure_stored32=[q_candidate(i,p),n_candidate(i,p)]
      if (use_constrained_storage) then
        failure_q64=(real(carrier_old(i),real64)*real(q_base(i,p),real64)+ &
          real(dt,real64)*(q_source_rate64(i,p)+q_transport_rate64(i,p)))/real(carrier_new(i),real64)
        failure_n64=(real(carrier_old(i),real64)*real(n_base(i,p),real64)+ &
          real(dt,real64)*(n_source_rate64(i,p)+n_transport_rate64(i,p)))/real(carrier_new(i),real64)
      else
        failure_q64=real(q_candidate(i,p),real64); failure_n64=real(n_candidate(i,p),real64)
      end if
      group_failure_candidate64=[failure_q64,failure_n64]
    end subroutine record_group_failure

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
          if (.not.pair_valid) then
            call record_group_failure(i,p,1)
            return
          end if
          if (pair_has_volume_bounds(p)) then
            if (present(number_pair_bounds)) then
              cell_volume_bounds = number_pair_bounds(i,:,p)
            else
              cell_volume_bounds = volume_number_bounds(i,:)
            end if
            if (.not. volume_number_stored_contract_valid(q_candidate(i,p),n_candidate(i,p), &
                    dry_density(i),cell_volume_bounds)) then
              call record_group_failure(i,p,2)
              return
            end if
          end if
        end do
      end do
      candidate_is_feasible = .true.
    end function candidate_is_feasible

  end subroutine joint_qnb_update

end module cloud_bal_joint_transport



!WRF:MODEL_LAYER:DYNAMICS
!

MODULE pr87_horizontal_diffusion64
  USE iso_fortran_env, ONLY: real32, real64, real128
  IMPLICIT NONE
  PRIVATE
  PUBLIC :: horizontal_diffusion64

CONTAINS

  SUBROUTINE horizontal_diffusion64(field,mut,c1,c2,msfux,msfuy,msfvx_inv,msfvy, &
                                    msftx,msfty,xkmhd,rdx,rdy, &
                                    ims,ime,kms,kme,jms,jme,il,ih,jl,jh,kl,kh,increment)
    INTEGER,INTENT(IN) :: ims,ime,kms,kme,jms,jme,il,ih,jl,jh,kl,kh
    REAL(real32),INTENT(IN) :: field(ims:ime,kms:kme,jms:jme)
    REAL(real32),INTENT(IN) :: xkmhd(ims:ime,kms:kme,jms:jme)
    REAL(real32),INTENT(IN) :: mut(ims:ime,jms:jme)
    REAL(real32),INTENT(IN) :: c1(kms:kme),c2(kms:kme)
    REAL(real32),INTENT(IN) :: msfux(ims:ime,jms:jme),msfuy(ims:ime,jms:jme)
    REAL(real32),INTENT(IN) :: msfvx_inv(ims:ime,jms:jme),msfvy(ims:ime,jms:jme)
    REAL(real32),INTENT(IN) :: msftx(ims:ime,jms:jme),msfty(ims:ime,jms:jme)
    REAL(real32),INTENT(IN) :: rdx,rdy
    REAL(real64),INTENT(OUT) :: increment(ims:ime,kms:kme,jms:jme)
    REAL(real128) :: increment128
    INTEGER :: i,j,k
    REAL(real128) :: mrdx,mrdy,mkrdxm,mkrdxp,mkrdym,mkrdyp
    REAL(real128) :: mut_i,mut_im,mut_ip,mut_jm,mut_jp
    REAL(real128) :: x_i,x_im,x_ip,x_jm,x_jp

    increment=0.0_real64
    IF (il>ih.OR.jl>jh.OR.kl>kh) RETURN
    IF (il<ims+1.OR.ih>ime-1.OR.jl<jms+1.OR.jh>jme-1.OR.kl<kms.OR.kh>kme) &
      ERROR STOP 'horizontal_diffusion64 active bounds exceed stencil storage'

    DO j=jl,jh
      DO k=kl,kh
        DO i=il,ih
          mut_i=REAL(c1(k),real128)*REAL(mut(i,j),real128)+REAL(c2(k),real128)
          mut_im=REAL(c1(k),real128)*REAL(mut(i-1,j),real128)+REAL(c2(k),real128)
          mut_ip=REAL(c1(k),real128)*REAL(mut(i+1,j),real128)+REAL(c2(k),real128)
          mut_jm=REAL(c1(k),real128)*REAL(mut(i,j-1),real128)+REAL(c2(k),real128)
          mut_jp=REAL(c1(k),real128)*REAL(mut(i,j+1),real128)+REAL(c2(k),real128)
          x_i=REAL(xkmhd(i,k,j),real128)
          x_im=REAL(xkmhd(i-1,k,j),real128)
          x_ip=REAL(xkmhd(i+1,k,j),real128)
          x_jm=REAL(xkmhd(i,k,j-1),real128)
          x_jp=REAL(xkmhd(i,k,j+1),real128)

          ! This is the `name='m'` face stencil in horizontal_diffusion.
          mkrdxm=(REAL(msfux(i,j),real128)/REAL(msfuy(i,j),real128))* &
            0.5_real128*(x_i+x_im)*0.5_real128*(mut_i+mut_im)*REAL(rdx,real128)
          mkrdxp=(REAL(msfux(i+1,j),real128)/REAL(msfuy(i+1,j),real128))* &
            0.5_real128*(x_ip+x_i)*0.5_real128*(mut_ip+mut_i)*REAL(rdx,real128)
          mrdx=REAL(msftx(i,j),real128)*REAL(msfty(i,j),real128)*REAL(rdx,real128)
          mkrdym=(REAL(msfvy(i,j),real128)*REAL(msfvx_inv(i,j),real128))* &
            0.5_real128*(x_i+x_jm)*0.5_real128*(mut_i+mut_jm)*REAL(rdy,real128)
          mkrdyp=(REAL(msfvy(i,j+1),real128)*REAL(msfvx_inv(i,j+1),real128))* &
            0.5_real128*(x_jp+x_i)*0.5_real128*(mut_jp+mut_i)*REAL(rdy,real128)
          mrdy=REAL(msftx(i,j),real128)*REAL(msfty(i,j),real128)*REAL(rdy,real128)

          increment128= &
            mrdx*(mkrdxp*(REAL(field(i+1,k,j),real128)-REAL(field(i,k,j),real128))- &
                  mkrdxm*(REAL(field(i,k,j),real128)-REAL(field(i-1,k,j),real128)))+ &
            mrdy*(mkrdyp*(REAL(field(i,k,j+1),real128)-REAL(field(i,k,j),real128))- &
                  mkrdym*(REAL(field(i,k,j),real128)-REAL(field(i,k,j-1),real128)))
          increment(i,k,j)=REAL(increment128,real64)
        END DO
      END DO
    END DO
  END SUBROUTINE horizontal_diffusion64

END MODULE pr87_horizontal_diffusion64

MODULE module_em
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite

   USE, INTRINSIC :: iso_fortran_env, ONLY: real64
   USE pr87_horizontal_diffusion64, ONLY: horizontal_diffusion64
   USE module_model_constants
   
   USE module_advect_em, only: advect_u, advect_v, advect_w, advect_scalar, advect_scalar_pd, advect_scalar_mono, &
        advect_weno_u, advect_weno_v, advect_weno_w, advect_scalar_weno,  advect_scalar_wenopd
   
   USE module_big_step_utilities_em, only: grid_config_rec_type, calculate_full, couple_momentum, calc_mu_uv, calc_mu_uv_1, &
        calc_ww_cp, calc_cq, calc_alt, calc_php, set_tend, rhs_ph, horizontal_pressure_gradient, pg_buoy_w, w_damp, &
        perturbation_coriolis, coriolis, curvature, horizontal_diffusion, horizontal_diffusion_3dmp, &
        vertical_diffusion_u, vertical_diffusion_v, vertical_diffusion, vertical_diffusion_3dmp, sixth_order_diffusion, & 
        rk_rayleigh_damp, theta_relaxation, vertical_diffusion_mp, zero_tend, zero_tend2d

  USE module_ieva_em, only: advect_u_implicit, advect_v_implicit, advect_w_implicit, advect_s_implicit, advect_ph_implicit, &
                            chk_ieva, ww_split, calc_mut_new
  USE module_state_description, only: param_first_scalar, p_qr, p_qv, p_qc, p_qg, p_qi, p_qs, p_qnr, p_qnc, p_qni, p_qib, tiedtkescheme,ntiedtkescheme, heldsuarez, &
        positivedef, gdscheme, g3scheme, gfscheme, kfetascheme, mskfscheme, monotonic, wenopd_scalar, weno_scalar, weno_mom

   USE module_damping_em, only: held_suarez_damp

   USE module_dm

   USE module_llxy

   USE module_domain, ONLY : domain, get_ijk_from_grid

   USE module_configure, ONLY: grid_config_rec_type, model_config_rec, model_to_grid_config_rec

CONTAINS

!------------------------------------------------------------------------

SUBROUTINE rk_step_prep  ( config_flags, rk_step,           &
                           u, v, w, t, ph, mu,              &
                           c1h, c2h, c1f, c2f, moist,       &
                           ru, rv, rw, ww, php, alt,        &
                           muu, muv,                        &
                           mub, mut, phb, pb, p, al, alb,   &
                           cqu, cqv, cqw,                   &
                           msfux, msfuy,                    &
                           msfvx, msfvx_inv, msfvy,         &
                           msftx, msfty,                    &
                           fnm, fnp, dnw, rdx, rdy,         &
                           n_moist,                         &
                           ids, ide, jds, jde, kds, kde,    &
                           ims, ime, jms, jme, kms, kme,    &
                           its, ite, jts, jte, kts, kte    )

   IMPLICIT NONE


   !  Input data.

   TYPE(grid_config_rec_type   ) ,   INTENT(IN   ) :: config_flags

   INTEGER ,       INTENT(IN   ) :: ids, ide, jds, jde, kds, kde, &
                                    ims, ime, jms, jme, kms, kme, &
                                    its, ite, jts, jte, kts, kte

   INTEGER ,       INTENT(IN   ) :: n_moist, rk_step

   REAL ,          INTENT(IN   ) :: rdx, rdy

   REAL , DIMENSION(  ims:ime , kms:kme, jms:jme ) ,                      &
                                               INTENT(IN   ) ::  u,       &
                                                                 v,       &
                                                                 w,       &
                                                                 t,       &
                                                                 ph,      &
                                                                 phb,     &
                                                                 pb,      &
                                                                 al,      &
                                                                 alb

   REAL , DIMENSION( ims:ime , kms:kme , jms:jme  ) ,                     &
                                               INTENT(  OUT) ::  ru,      &
                                                                 rv,      &
                                                                 rw,      &
                                                                 ww,      &
                                                                 php,     &
                                                                 cqu,     &
                                                                 cqv,     &
                                                                 cqw,     &
                                                                 alt

   REAL , DIMENSION(  ims:ime , kms:kme, jms:jme ) ,                      &
                                               INTENT(IN   ) ::  p
                                                                 



   REAL , DIMENSION( ims:ime, kms:kme, jms:jme, n_moist ), INTENT(   IN) :: &
                                                           moist

   REAL , DIMENSION( ims:ime , jms:jme ) ,    INTENT(IN   ) :: msftx,     &
                                                               msfty,     &
                                                               msfux,     &
                                                               msfuy,     &
                                                               msfvx,     &
                                                               msfvx_inv, &
                                                               msfvy,     &
                                                               mu,        &
                                                               mub

   REAL , DIMENSION( ims:ime , jms:jme ) ,    INTENT(  OUT) :: muu,    &
                                                               muv,    &
                                                               mut

   REAL , DIMENSION( kms:kme ) ,    INTENT(IN   ) :: fnm, fnp, dnw
   REAL , DIMENSION( kms:kme ) ,    INTENT(IN   ) :: c1h, c2h, c1f, c2f

   integer :: k


!<DESCRIPTION>
!
!  rk_step_prep prepares a number of diagnostic quantities
!  in preperation for a Runge-Kutta timestep.  subroutines called
!  by rk_step_prep calculate
!
!  (1) total column dry air mass (mut, call to calculate_full)
!
!  (2) total column dry air mass at u and v points
!      (muu, muv, call to calculate_mu_uv)
!
!  (3) mass-coupled velocities for advection
!      (ru, rv, and rw, call to couple_momentum)
!
!  (4) omega (call to calc_ww_cp)
!
!  (5) moisture coefficients (cqu, cqv, cqw, call to calc_cq)
!
!  (6) inverse density (alt, call to calc_alt)
!
!  (7) geopotential at pressure points (php, call to calc_php)
!
!</DESCRIPTION>

   CALL calculate_full( mut, mub, mu,             &
                        ids, ide, jds, jde, 1, 2, &
                        ims, ime, jms, jme, 1, 1, &
                        its, ite, jts, jte, 1, 1 )

   CALL calc_mu_uv ( config_flags,                  &
                     mu, mub, muu, muv,             &
                     ids, ide, jds, jde, kds, kde,  &
                     ims, ime, jms, jme, kms, kme,  &
                     its, ite, jts, jte, kts, kte  )

   CALL couple_momentum( muu, ru, u, msfuy,             &
                         muv, rv, v, msfvx, msfvx_inv,  &
                         mut, rw, w, msfty,             &
                         c1h, c2h, c1f, c2f,            &
                         ids, ide, jds, jde, kds, kde,  &
                         ims, ime, jms, jme, kms, kme,  &
                         its, ite, jts, jte, kts, kte  )

!  new call, couples V with mu, also has correct map factors.  WCS, 3 june 2001
   CALL calc_ww_cp ( u, v, mu, mub, c1h, c2h, ww,     &
                     rdx, rdy, msftx, msfty,          &
                     msfux, msfuy, msfvx, msfvx_inv,  &
                     msfvy, dnw,                      &
                     ids, ide, jds, jde, kds, kde,    &
                     ims, ime, jms, jme, kms, kme,    &
                     its, ite, jts, jte, kts, kte    )

   CALL calc_cq ( moist, cqu, cqv, cqw, n_moist, &
                  ids, ide, jds, jde, kds, kde,  &
                  ims, ime, jms, jme, kms, kme,  &
                  its, ite, jts, jte, kts, kte  )

   CALL calc_alt ( alt, al, alb,                 &
                   ids, ide, jds, jde, kds, kde, &
                   ims, ime, jms, jme, kms, kme, &
                   its, ite, jts, jte, kts, kte )

   CALL calc_php ( php, ph, phb,                 &
                   ids, ide, jds, jde, kds, kde, &
                   ims, ime, jms, jme, kms, kme, &
                   its, ite, jts, jte, kts, kte )

END SUBROUTINE rk_step_prep

!-------------------------------------------------------------------------------

SUBROUTINE rk_tendency ( config_flags, rk_step,                           &
                         ru_tend, rv_tend, rw_tend, ph_tend, t_tend,      &
                         ru_tendf, rv_tendf, rw_tendf, ph_tendf, t_tendf, &
                         mu_tend, u_save, v_save, w_save, ph_save,        &
                         t_save, mu_save, RTHFTEN,                        &
                         ru, rv, rw, ww, wwE, wwI,                        &
                         u, v, w, t, ph,                                  &
                         u_old, v_old, w_old, t_old, ph_old,              &
                         h_diabatic, phb,t_init,                          &
                         mu_old, mu, mut, muu, muv, mub,                  &
                         c1h, c2h, c1f, c2f,                              &
                         al, ht, alt, p, pb, php, cqu, cqv, cqw,          &
                         u_base, v_base, t_base, qv_base, z_base,         &
                         msfux, msfuy, msfvx, msfvx_inv,                  &
                         msfvy, msftx, msfty,                             &
                         clat, f, e, sina, cosa,                          &
                         fnm, fnp, rdn, rdnw,                             &
                         dt, rdx, rdy, khdif, kvdif, xkmhd, xkhh,         &
                         diff_6th_opt, diff_6th_factor,                   &
                         adv_opt,                                         &
                         dampcoef,zdamp,damp_opt,rad_nudge,               &
                         cf1, cf2, cf3, cfn, cfn1, n_moist,               &
                         non_hydrostatic, top_lid,                        &
                         u_frame, v_frame,                                &
                         ids, ide, jds, jde, kds, kde,                    &
                         ims, ime, jms, jme, kms, kme,                    &
                         its, ite, jts, jte, kts, kte,                    &
                         max_vert_cfl, max_horiz_cfl)

   IMPLICIT NONE

   !  Input data.

   TYPE(grid_config_rec_type)    ,           INTENT(IN   ) :: config_flags

   INTEGER ,               INTENT(IN   ) :: ids, ide, jds, jde, kds, kde, &
                                            ims, ime, jms, jme, kms, kme, &
                                            its, ite, jts, jte, kts, kte

   LOGICAL ,               INTENT(IN   ) :: non_hydrostatic, top_lid

   INTEGER ,               INTENT(IN   ) :: n_moist, rk_step

   REAL , DIMENSION( ims:ime , kms:kme, jms:jme  ) ,              &
                                        INTENT(IN   ) :: ru,      &
                                                         rv,      &
                                                         rw,      &
                                                         ww,      &
                                                         u,       &
                                                         v,       &
                                                         w,       &
                                                         t,       &
                                                         ph,      &
                                                         u_old,   &
                                                         v_old,   &
                                                         w_old,   &
                                                         t_old,   &
                                                         ph_old,  &
                                                         phb,     &
                                                         al,      &
                                                         alt,     &
                                                         p,       &
                                                         pb,      &
                                                         php,     &
                                                         cqu,     &
                                                         cqv,     &
                                                         t_init,  &
                                                         xkmhd,   &
                                                         xkhh,    &
                                                         h_diabatic

   REAL , DIMENSION( ims:ime , kms:kme, jms:jme  ) ,              &
                                        INTENT(OUT  ) :: ru_tend, &
                                                         rv_tend, &
                                                         rw_tend, &
                                                         t_tend,  &
                                                         ph_tend, &
                                                         RTHFTEN, &
                                                          u_save, &
                                                          v_save, &
                                                          w_save, &
                                                         ph_save, &
                                                          t_save

   REAL , DIMENSION( ims:ime , kms:kme, jms:jme  ) ,               &
                                        INTENT(INOUT) :: ru_tendf, &
                                                         rv_tendf, &
                                                         rw_tendf, &
                                                         t_tendf,  &
                                                         ph_tendf, &
                                                         cqw

   REAL , DIMENSION( ims:ime , jms:jme ) ,         INTENT(  OUT) :: mu_tend, &
                                                                    mu_save

   REAL , DIMENSION( ims:ime , jms:jme ) ,         INTENT(IN   ) :: msfux,   &
                                                                    msfuy,   &
                                                                    msfvx,   &
                                                                    msfvx_inv,   &
                                                                    msfvy,   &
                                                                    msftx,   &
                                                                    msfty,   &
                                                                    clat,    &
                                                                    f,       &
                                                                    e,       &
                                                                    sina,    &
                                                                    cosa,    &
                                                                    mu_old,  &
                                                                    mu,      &
                                                                    mut,     &
                                                                    mub,     &
                                                                    muu,     &
                                                                    muv,     &
                                                                    ht             

   REAL , DIMENSION( kms:kme ) ,                 INTENT(IN   ) :: fnm,     &
                                                                  fnp,     &
                                                                  rdn,     &
                                                                  rdnw,    &
                                                                  u_base,  &
                                                                  v_base,  &
                                                                  t_base,  &
                                                                  qv_base, &
                                                                  z_base,  &
                                                                  c1h,     &
                                                                  c2h,     &
                                                                  c1f,     &
                                                                  c2f

   REAL ,                                      INTENT(IN   ) :: rdx,     &
                                                                rdy,     &
                                                                dt,      &
                                                                u_frame, &
                                                                v_frame, &
                                                                khdif,   &
                                                                kvdif
   INTEGER, INTENT( IN ) :: diff_6th_opt
   REAL,    INTENT( IN ) :: diff_6th_factor
   INTEGER, INTENT( IN ) :: adv_opt

   INTEGER, INTENT( IN ) :: damp_opt, rad_nudge

   REAL, INTENT( IN ) :: zdamp, dampcoef

   REAL, INTENT( OUT ) :: max_horiz_cfl
   REAL, INTENT( OUT ) :: max_vert_cfl

   REAL    :: kdift, khdq, kvdq, cfn, cfn1, cf1, cf2, cf3
   INTEGER :: i,j,k
   INTEGER :: time_step
   INTEGER :: rk_order
   REAL    :: dt_step

! IEVA declarations
   REAL , DIMENSION( ims:ime, kms:kme, jms:jme ) :: wwE, wwI  
   REAL , DIMENSION( ims:ime , jms:jme )         :: mut_old, mut_new                                                              
   REAL , DIMENSION( ims:ime , jms:jme )         :: muu_old, muu_new                                                              
   REAL , DIMENSION( ims:ime , jms:jme )         :: muv_old, muv_new                                                              
   LOGICAL                                       :: ieva
   
!<DESCRIPTION>
!
!  rk_tendency computes the large-timestep tendency terms in the
!  momentum, thermodynamic (theta), and geopotential equations.  
!  These terms include:
!
!  (1) advection (for u, v, w, theta - calls to advect_u, advect_v,
!                 advect_w, and advact_scalar).
!
!  (2) geopotential equation terms (advection and "gw" - call to rhs_ph).
!
!  (3) buoyancy term in vertical momentum equation (call to pg_buoy_w).
!
!  (4) Coriolis and curvature terms in u,v,w momentum equations
!      (calls to subroutines coriolis, curvature)
!
!  (5) 3D diffusion on coordinate surfaces.
!
!</DESCRIPTION>

   CALL zero_tend ( ru_tend,                      &
                    ids, ide, jds, jde, kds, kde, &
                    ims, ime, jms, jme, kms, kme, &
                    its, ite, jts, jte, kts, kte )

   CALL zero_tend ( rv_tend,                      &
                    ids, ide, jds, jde, kds, kde, &
                    ims, ime, jms, jme, kms, kme, &
                    its, ite, jts, jte, kts, kte )

   CALL zero_tend ( rw_tend,                      &
                    ids, ide, jds, jde, kds, kde, &
                    ims, ime, jms, jme, kms, kme, &
                    its, ite, jts, jte, kts, kte )

   CALL zero_tend ( t_tend,                       &
                    ids, ide, jds, jde, kds, kde, &
                    ims, ime, jms, jme, kms, kme, &
                    its, ite, jts, jte, kts, kte )

   CALL zero_tend ( ph_tend,                      &
                    ids, ide, jds, jde, kds, kde, &
                    ims, ime, jms, jme, kms, kme, &
                    its, ite, jts, jte, kts, kte )

   CALL zero_tend ( u_save,                       &
                    ids, ide, jds, jde, kds, kde, &
                    ims, ime, jms, jme, kms, kme, &
                    its, ite, jts, jte, kts, kte )

   CALL zero_tend ( v_save,                       &
                    ids, ide, jds, jde, kds, kde, &
                    ims, ime, jms, jme, kms, kme, &
                    its, ite, jts, jte, kts, kte )

   CALL zero_tend ( w_save,                       &
                    ids, ide, jds, jde, kds, kde, &
                    ims, ime, jms, jme, kms, kme, &
                    its, ite, jts, jte, kts, kte )

   CALL zero_tend ( ph_save,                       &
                    ids, ide, jds, jde, kds, kde, &
                    ims, ime, jms, jme, kms, kme, &
                    its, ite, jts, jte, kts, kte )

   CALL zero_tend ( t_save,                       &
                    ids, ide, jds, jde, kds, kde, &
                    ims, ime, jms, jme, kms, kme, &
                    its, ite, jts, jte, kts, kte )

   CALL zero_tend2d( mu_tend,                  &
                    ids, ide, jds, jde, 1, 1, &
                    ims, ime, jms, jme, 1, 1, &
                    its, ite, jts, jte, 1, 1 )

   CALL zero_tend2d( mu_save,                  &
                    ids, ide, jds, jde, 1, 1, &
                    ims, ime, jms, jme, 1, 1, &
                    its, ite, jts, jte, 1, 1 )

   CALL nl_get_time_step ( 1, time_step )

   rk_order = config_flags%rk_ord
   dt_step  = dt / (rk_order - rk_step + 1)   ! needed for calculations using sub-rk step

                        
! Code for splitting vertical velocity into ex/im parts

   CALL WW_SPLIT(wwE, wwI,                         &
                 u,  v,  ww,                       &
                 mut, rdnw, msfty,                 &
                 c1f, c2f,                         &
                 rdx, rdy, msfux, msfuy,           &
                 msfvx, msfvy, dt,                 &
                 config_flags, rk_step,            &
                 ids, ide, jds, jde, kds, kde,     &
                 ims, ime, jms, jme, kms, kme,     &
                 its, ite, jts, jte, kts, kte )              

! IEVA ON/OFF
   
   ieva = CHK_IEVA( config_flags, rk_step ) 

   IF( ieva ) THEN
   
! Need an estimate of the mut at the original ('n') time level...

   CALL calculate_full( mut_old,  mub, mu_old,     &
                        ids, ide, jds, jde, 1, 2,  &
                        ims, ime, jms, jme, 1, 1,  &
                        its, ite, jts, jte, 1, 1 )

! Estimate new temporary column mass
                        
   CALL calc_mut_new ( u, v, c1h, c2h,                      &
                       mut_old, muu, muv, mut_new,          &
                       dt, rdx, rdy, msftx, msfty,          &
                       msfux, msfuy, msfvx, msfvx_inv,      &
                       msfvy, rdnw,                         &
                       ids, ide, jds, jde, kds, kde,        &
                       ims, ime, jms, jme, kms, kme,        &
                       its, ite, jts, jte, kts, kte    )
                         
! Create staggered mass values for u and v points

   CALL calc_mu_uv_1 ( config_flags,                 &
                       mut_old, muu_old, muv_old,    &
                       ids, ide, jds, jde, kds, kde, &
                       ims, ime, jms, jme, kms, kme, &
                       its, ite, jts, jte, kts, kte )
                      
   CALL calc_mu_uv_1 ( config_flags,                 &
                       mut_new, muu_new, muv_new,    &
                       ids, ide, jds, jde, kds, kde, &
                       ims, ime, jms, jme, kms, kme, &
                       its, ite, jts, jte, kts, kte )

   ENDIF

! Okay do normal advection now....using the wwE array

   IF( (rk_step == rk_order) .and. ( adv_opt == WENO_MOM ) ) THEN

      CALL pr98_dump2('geom_msfuy',msfuy,ims,ime,jms,jme,its,ite,jts,jte)
      CALL pr98_dump2('geom_msfvx_inv',msfvx_inv,ims,ime,jms,jme,its,ite,jts,jte)
      CALL pr98_dump2('geom_msfty',msfty,ims,ime,jms,jme,its,ite,jts,jte)
      CALL pr98_dump2('geom_msfux',msfux,ims,ime,jms,jme,its,ite,jts,jte)
      CALL pr98_dump2('geom_msfvx',msfvx,ims,ime,jms,jme,its,ite,jts,jte)
      CALL pr98_dump2('geom_msfvy',msfvy,ims,ime,jms,jme,its,ite,jts,jte)
      CALL pr98_dump2('geom_msftx',msftx,ims,ime,jms,jme,its,ite,jts,jte)
      CALL pr98_dump2('geom_mut',mut,ims,ime,jms,jme,its,ite,jts,jte)
      CALL pr98_dump2('geom_mu',mu,ims,ime,jms,jme,its,ite,jts,jte)
      CALL pr98_dump2('geom_muu',muu,ims,ime,jms,jme,its,ite,jts,jte)
      CALL pr98_dump2('geom_muv',muv,ims,ime,jms,jme,its,ite,jts,jte)
      CALL pr98_dump1('geom_c1h',c1h,kms,kme,kts,kte)
      CALL pr98_dump1('geom_c2h',c2h,kms,kme,kts,kte)
      CALL pr98_dump3('advu_ru_tend_in',ru_tend,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)
      
     CALL advect_weno_u ( u, u , ru_tend, ru, rv, wwE,  &
                          c1h, c2h,                     &
                          mut, time_step, config_flags, &
                          msfux, msfuy, msfvx, msfvy,   &
                          msftx, msfty,                 &
                          fnm, fnp, rdx, rdy, rdnw,     &
                          ids, ide, jds, jde, kds, kde, &
                          ims, ime, jms, jme, kms, kme, &
                          its, ite, jts, jte, kts, kte )
      CALL pr98_dump3('advu_ru_tend_out',ru_tend,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)

   ELSE

      CALL pr98_dump2('geom_msfuy',msfuy,ims,ime,jms,jme,its,ite,jts,jte)
      CALL pr98_dump2('geom_msfvx_inv',msfvx_inv,ims,ime,jms,jme,its,ite,jts,jte)
      CALL pr98_dump2('geom_msfty',msfty,ims,ime,jms,jme,its,ite,jts,jte)
      CALL pr98_dump2('geom_msfux',msfux,ims,ime,jms,jme,its,ite,jts,jte)
      CALL pr98_dump2('geom_msfvx',msfvx,ims,ime,jms,jme,its,ite,jts,jte)
      CALL pr98_dump2('geom_msfvy',msfvy,ims,ime,jms,jme,its,ite,jts,jte)
      CALL pr98_dump2('geom_msftx',msftx,ims,ime,jms,jme,its,ite,jts,jte)
      CALL pr98_dump2('geom_mut',mut,ims,ime,jms,jme,its,ite,jts,jte)
      CALL pr98_dump2('geom_mu',mu,ims,ime,jms,jme,its,ite,jts,jte)
      CALL pr98_dump2('geom_muu',muu,ims,ime,jms,jme,its,ite,jts,jte)
      CALL pr98_dump2('geom_muv',muv,ims,ime,jms,jme,its,ite,jts,jte)
      CALL pr98_dump1('geom_c1h',c1h,kms,kme,kts,kte)
      CALL pr98_dump1('geom_c2h',c2h,kms,kme,kts,kte)
      CALL pr98_dump3('advu_ru_tend_in',ru_tend,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)
      
     CALL advect_u ( u, u , ru_tend, ru, rv, wwE,  &
                     c1h, c2h,                     &
                     mut, time_step, config_flags, &
                     msfux, msfuy, msfvx, msfvy,   &
                     msftx, msfty,                 &
                     fnm, fnp, rdx, rdy, rdnw,     &
                     ids, ide, jds, jde, kds, kde, &
                     ims, ime, jms, jme, kms, kme, &
                     its, ite, jts, jte, kts, kte )
      CALL pr98_dump3('advu_ru_tend_out',ru_tend,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)
   ENDIF

   IF( ieva ) THEN

     CALL advect_u_implicit ( u, u_old, ru_tend, ru, rv, wwI,  &
                              c1h, c2h,                        &
                              muu_old, muu, muu_new,           &
                              config_flags,                    &
                              msfux, msfuy, msfvx, msfvy,      &
                              msftx, msfty,                    &
                              fnm, fnp,                        &
                              dt_step,                         &
                              rdx, rdy, rdnw,                  &
                              ids, ide, jds, jde, kds, kde,    &
                              ims, ime, jms, jme, kms, kme,    &
                              its, ite, jts, jte, kts, kte )
   ENDIF

   IF( (rk_step == rk_order) .and. ( adv_opt == WENO_MOM ) ) THEN

      CALL pr98_dump3('advv_rv_tend_in',rv_tend,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)
      
      CALL advect_weno_v ( v, v , rv_tend, ru, rv, wwE,  &
                           c1h, c2h,                     &
                           mut, time_step, config_flags, &
                           msfux, msfuy, msfvx, msfvy,   &
                           msftx, msfty,                 &
                           fnm, fnp, rdx, rdy, rdnw,     &
                           ids, ide, jds, jde, kds, kde, &
                           ims, ime, jms, jme, kms, kme, &
                           its, ite, jts, jte, kts, kte )
      CALL pr98_dump3('advv_rv_tend_out',rv_tend,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)

   ELSE

      CALL pr98_dump3('advv_rv_tend_in',rv_tend,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)
      
     CALL advect_v ( v, v , rv_tend, ru, rv, wwE,  &
                     c1h, c2h,                     &
                     mut, time_step, config_flags, &
                     msfux, msfuy, msfvx, msfvy,   &
                     msftx, msfty,                 &
                     fnm, fnp, rdx, rdy, rdnw,     &
                     ids, ide, jds, jde, kds, kde, &
                     ims, ime, jms, jme, kms, kme, &
                     its, ite, jts, jte, kts, kte )
      CALL pr98_dump3('advv_rv_tend_out',rv_tend,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)
   ENDIF

   IF( ieva ) THEN
     
     CALL advect_v_implicit ( v, v_old, rv_tend, ru, rv, wwI,  &
                              c1h, c2h,                        &
                              muv_old, muv, muv_new,           &
                              config_flags,                    &
                              msfux, msfuy, msfvx, msfvy,      &
                              msftx, msfty,                    &
                              fnm, fnp,                        &
                              dt_step,                         &
                              rdx, rdy, rdnw,                  &
                              ids, ide, jds, jde, kds, kde,    &
                              ims, ime, jms, jme, kms, kme,    &
                              its, ite, jts, jte, kts, kte )
   ENDIF

   IF (non_hydrostatic) THEN

     IF( (rk_step == rk_order) .and. ( adv_opt == WENO_MOM ) ) THEN

      CALL pr98_dump3('advw_rw_tend_in',rw_tend,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)
      
       CALL advect_weno_w ( w, w, rw_tend, ru, rv, wwE,   &
                            c1h, c2h,                     &
                            mut, time_step, config_flags, &
                            msfux, msfuy, msfvx, msfvy,   &
                            msftx, msfty,                 &
                            fnm, fnp, rdx, rdy, rdn,      &
                            ids, ide, jds, jde, kds, kde, &
                            ims, ime, jms, jme, kms, kme, &
                            its, ite, jts, jte, kts, kte )
      CALL pr98_dump3('advw_rw_tend_out',rw_tend,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)

     ELSE

      CALL pr98_dump3('advw_rw_tend_in',rw_tend,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)
           
       CALL advect_w ( w, w, rw_tend, ru, rv, wwE,   &
                       c1h, c2h,                     &
                       mut, time_step, config_flags, &
                       msfux, msfuy, msfvx, msfvy,   &
                       msftx, msfty,                 &
                       fnm, fnp, rdx, rdy, rdn,      &
                       ids, ide, jds, jde, kds, kde, &
                       ims, ime, jms, jme, kms, kme, &
                       its, ite, jts, jte, kts, kte )
      CALL pr98_dump3('advw_rw_tend_out',rw_tend,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)
     ENDIF

   ENDIF  ! non-hydrostatic

!  theta flux divergence

! 11/2016 ERM: Use WENO for theta flux on 3rd RK step if using WENO_SCALAR or WENOPD_SCALAR
! to be consistent with other scalar fluxes
   IF(  ( config_flags%scalar_adv_opt == WENO_SCALAR      &
     .or. config_flags%scalar_adv_opt == WENOPD_SCALAR    &
     .or. config_flags%moist_adv_opt == WENO_SCALAR       &
     .or. config_flags%moist_adv_opt == WENOPD_SCALAR )   &
     .and. (rk_step == rk_order) ) THEN
     
! also use weno for monotonic scalar option so that the h_ and z_tendency arrays are not needed

     CALL advect_scalar_weno ( t, t, t_tend, ru, rv, wwE,     &
                               c1h, c2h, mut, time_step,      &
                               config_flags,                  &
                               msfux, msfuy, msfvx, msfvy,    &
                               msftx, msfty, fnm, fnp,        &
                               rdx, rdy, rdnw,                &
                               ids, ide, jds, jde, kds, kde,  &
                               ims, ime, jms, jme, kms, kme,  &
                               its, ite, jts, jte, kts, kte  )
   ELSE

     CALL advect_scalar ( t, t, t_tend, ru, rv, wwE,    &
                          c1h, c2h,                     &
                          mut, time_step, config_flags, &
                          msfux, msfuy, msfvx, msfvy,   &
                          msftx, msfty, fnm, fnp,       &
                          rdx, rdy, rdnw,               &
                          ids, ide, jds, jde, kds, kde, &
                          ims, ime, jms, jme, kms, kme, &
                          its, ite, jts, jte, kts, kte )

   ENDIF

   IF( ieva ) THEN
      
     CALL advect_s_implicit ( t, t_old, t_tend, ru, rv, wwI,  &
                              c1h, c2h,                       &
                              mut_old, mut, mut_new,          &
                              config_flags,                   &
                              msfux, msfuy, msfvx, msfvy,     &
                              msftx, msfty,                   &
                              fnm, fnp,                       &
                              dt_step,                        &
                              rdx, rdy, rdnw,                 &
                              ids, ide, jds, jde, kds, kde,   &
                              ims, ime, jms, jme, kms, kme,   &
                              its, ite, jts, jte, kts, kte )

   ENDIF
     
   IF ( config_flags%cu_physics == GDSCHEME  .OR.     &
        config_flags%cu_physics == GFSCHEME  .OR.     &
        config_flags%cu_physics == G3SCHEME  .OR.     &
        config_flags%cu_physics == NTIEDTKESCHEME )  THEN     ! NTiedtke

     ! theta advection only:

     CALL set_tend( RTHFTEN, t_tend, msfty,          &
                    ids, ide, jds, jde, kds, kde,    &
                    ims, ime, jms, jme, kms, kme,    &
                    its, ite, jts, jte, kts, kte     )

   END IF

   CALL rhs_ph( ph_tend, u, v, wwE, ph, ph, phb, w, &
                mut, muu, muv,                     &
                c1f, c2f,                          &
                fnm, fnp,                          &
                rdnw, cfn, cfn1, rdx, rdy,         &
                msfux, msfuy, msfvx,               &
                msfvx_inv, msfvy,                  &
                msftx, msfty,                      &
                non_hydrostatic,                   &
                config_flags,                      &
                ids, ide, jds, jde, kds, kde,      &
                ims, ime, jms, jme, kms, kme,      &
                its, ite, jts, jte, kts, kte      )

    IF( ieva ) THEN
      
        CALL advect_ph_implicit ( ph, ph_old, ph_tend, phb,       &
                                  ru, rv, wwE, wwI, w,            & 
                                  c1f, c2f,                       &
                                  mut, config_flags,              &
                                  msfux, msfuy, msfvx, msfvy,     &
                                  msftx, msfty,                   &
                                  fnm, fnp,                       &
                                  dt_step,                        &
                                  rdx, rdy, rdnw,                 &
                                  ids, ide, jds, jde, kds, kde,   &
                                  ims, ime, jms, jme, kms, kme,   &
                                  its, ite, jts, jte, kts, kte )

     IF (non_hydrostatic) THEN
      
       CALL advect_w_implicit ( w, w_old, rw_tend,              &
                                ru_tend, rv_tend, ht, wwI,      &
                                ph, ph_old, ph_tend,            &
                                c1f, c2f, cf1, cf2, cf3,        &
                                mut_old, mut, mut_new,          &
                                config_flags,                   &
                                msfux, msfuy, msfvx, msfvy,     &
                                msftx, msfty,                   &
                                fnm, fnp,                       &
                                dt_step,                        &
                                rdx, rdy, rdn,                  &
                                ids, ide, jds, jde, kds, kde,   &
                                ims, ime, jms, jme, kms, kme,   &
                                its, ite, jts, jte, kts, kte )
     ENDIF
     
   ENDIF  ! IEVA

      CALL pr98_dump3('pgrad_ru_tend_in',ru_tend,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)
      CALL pr98_dump3('pgrad_rv_tend_in',rv_tend,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)
      
   CALL horizontal_pressure_gradient( ru_tend,rv_tend,                 &
                                       ph,alt,p,pb,al,php,cqu,cqv,     &
                                       muu,muv,mu,c1h,c2h,fnm,fnp,rdnw,&
                                       cf1,cf2,cf3,cfn,cfn1,           &
                                       rdx,rdy,msfux,msfuy,            &
                                       msfvx,msfvy,msftx,msfty,        &
                                       config_flags, non_hydrostatic,  &
                                       top_lid,                        &
                                       ids, ide, jds, jde, kds, kde,   &
                                       ims, ime, jms, jme, kms, kme,   &
                                       its, ite, jts, jte, kts, kte   )
      CALL pr98_dump3('pgrad_ru_tend_out',ru_tend,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)
      CALL pr98_dump3('pgrad_rv_tend_out',rv_tend,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)

   IF (non_hydrostatic) THEN
        CALL pg_buoy_w( rw_tend, p, cqw, mu, mub,       &
                        c1f,c2f,                        &
                        rdnw, rdn, g, msftx, msfty,     &
                        ids, ide, jds, jde, kds, kde,   &
                        ims, ime, jms, jme, kms, kme,   &
                        its, ite, jts, jte, kts, kte   )
   ENDIF

   CALL w_damp   ( rw_tend, max_vert_cfl,             &
                    max_horiz_cfl,                    &
                    u, v, ww, w, mut, c1f, c2f, rdnw, &
                    rdx, rdy, msfux, msfuy, msfvx,    &
                    msfvy, dt, config_flags,          &
                    ids, ide, jds, jde, kds, kde,     &
                    ims, ime, jms, jme, kms, kme,     &
                    its, ite, jts, jte, kts, kte     )

   IF(config_flags%pert_coriolis) THEN

      CALL pr98_dump3('coriolis_ru_tend_in',ru_tend,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)
      CALL pr98_dump3('coriolis_rv_tend_in',rv_tend,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)
      CALL pr98_dump3('coriolis_rw_tend_in',rw_tend,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)
      
        CALL perturbation_coriolis ( ru, rv, rw,                   &
                                     ru_tend,  rv_tend,  rw_tend,  &
                                     config_flags,                 &
                                     u_base, v_base, z_base,       &
                                     muu, muv, c1h, c2h, phb, ph,  &
                                     msftx, msfty, msfux, msfuy,   &
                                     msfvx, msfvy,                 &
                                     f, e, sina, cosa, fnm, fnp,   &
                                     ids, ide, jds, jde, kds, kde, &
                                     ims, ime, jms, jme, kms, kme, &
                                     its, ite, jts, jte, kts, kte )
      CALL pr98_dump3('coriolis_ru_tend_out',ru_tend,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)
      CALL pr98_dump3('coriolis_rv_tend_out',rv_tend,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)
      CALL pr98_dump3('coriolis_rw_tend_out',rw_tend,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)
   ELSE

      CALL pr98_dump3('coriolis_ru_tend_in',ru_tend,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)
      CALL pr98_dump3('coriolis_rv_tend_in',rv_tend,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)
      CALL pr98_dump3('coriolis_rw_tend_in',rw_tend,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)
              CALL coriolis ( ru, rv, rw,                   &
                        ru_tend,  rv_tend,  rw_tend,  &
                        config_flags,                 &
                        msftx, msfty, msfux, msfuy,   &
                        msfvx, msfvy,                 &
                        f, e, sina, cosa, fnm, fnp,   &
                        ids, ide, jds, jde, kds, kde, &
                        ims, ime, jms, jme, kms, kme, &
                        its, ite, jts, jte, kts, kte )
      CALL pr98_dump3('coriolis_ru_tend_out',ru_tend,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)
      CALL pr98_dump3('coriolis_rv_tend_out',rv_tend,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)
      CALL pr98_dump3('coriolis_rw_tend_out',rw_tend,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)

   END IF

      CALL pr98_dump3('curvature_ru_tend_in',ru_tend,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)
      CALL pr98_dump3('curvature_rv_tend_in',rv_tend,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)
      CALL pr98_dump3('curvature_rw_tend_in',rw_tend,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)
      
   CALL curvature ( ru, rv, rw, u, v, w,            &
                     ru_tend,  rv_tend,  rw_tend,    &
                     config_flags,                   &
                     msfux, msfuy, msfvx, msfvy,     &
                     msftx, msfty,                   &
                     clat, fnm, fnp, rdx, rdy,       &
                     ids, ide, jds, jde, kds, kde,   &
                     ims, ime, jms, jme, kms, kme,   &
                     its, ite, jts, jte, kts, kte   )
      CALL pr98_dump3('curvature_ru_tend_out',ru_tend,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)
      CALL pr98_dump3('curvature_rv_tend_out',rv_tend,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)
      CALL pr98_dump3('curvature_rw_tend_out',rw_tend,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)

! Damping option added for Held-Suarez test (also uses lw option HELDSUAREZ)

    IF (config_flags%ra_lw_physics == HELDSUAREZ) THEN
       CALL held_suarez_damp ( ru_tend, rv_tend,               &   
                               ru,rv,p,pb,                     &
                               ids, ide, jds, jde, kds, kde,   &
                               ims, ime, jms, jme, kms, kme,   &
                               its, ite, jts, jte, kts, kte   )
    END IF

!**************************************************************
!
!  Next, the terms that we integrate only with forward-in-time
!  (evaluate with time t variables).
!
!**************************************************************

  forward_step: IF( rk_step == 1 ) THEN

    diff_opt1 : IF (config_flags%diff_opt .eq. 1) THEN

      CALL pr98_dump3('hdifu_ru_tendf_in',ru_tendf,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)
         
        CALL horizontal_diffusion ('u', u, ru_tendf, mut,               &
                                        c1h, c2h, config_flags,         &
                                        msfux, msfuy, msfvx, msfvx_inv, &
                                        msfvy,msftx, msfty,             &
                                        khdif, xkmhd, rdx, rdy,         &
                                        ids, ide, jds, jde, kds, kde,   &
                                        ims, ime, jms, jme, kms, kme,   &
                                        its, ite, jts, jte, kts, kte   )
      CALL pr98_dump3('hdifu_ru_tendf_out',ru_tendf,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)

      CALL pr98_dump3('hdifv_rv_tendf_in',rv_tendf,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)
      
        CALL horizontal_diffusion ('v', v, rv_tendf, mut,               &
                                        c1h, c2h, config_flags,         &
                                        msfux, msfuy, msfvx, msfvx_inv, &
                                        msfvy,msftx, msfty,             &
                                        khdif, xkmhd, rdx, rdy,         &
                                        ids, ide, jds, jde, kds, kde,   &
                                        ims, ime, jms, jme, kms, kme,   &
                                        its, ite, jts, jte, kts, kte   )
      CALL pr98_dump3('hdifv_rv_tendf_out',rv_tendf,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)

      CALL pr98_dump3('hdifw_rw_tendf_in',rw_tendf,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)
      
        CALL horizontal_diffusion ('w', w, rw_tendf, mut,               &
                                        c1f, c2f, config_flags,         &
                                        msfux, msfuy, msfvx, msfvx_inv, &
                                        msfvy,msftx, msfty,             &
                                        khdif, xkmhd, rdx, rdy,         &
                                        ids, ide, jds, jde, kds, kde,   &
                                        ims, ime, jms, jme, kms, kme,   &
                                        its, ite, jts, jte, kts, kte   )
      CALL pr98_dump3('hdifw_rw_tendf_out',rw_tendf,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)

        khdq = 3.*khdif
        CALL horizontal_diffusion_3dmp ( 'm', t, t_tendf, mut,            &
                                         c1h, c2h,                        &
                                         config_flags, t_init,            &
                                         msfux, msfuy, msfvx, msfvx_inv,  &
                                         msfvy, msftx, msfty,             &
                                         khdq , xkhh, rdx, rdy,           &
                                         ids, ide, jds, jde, kds, kde,    &
                                         ims, ime, jms, jme, kms, kme,    &
                                         its, ite, jts, jte, kts, kte    )

        pbl_test : IF (config_flags%bl_pbl_physics .eq. 0) THEN

      CALL pr98_dump3('vdifu_ru_tendf_in',ru_tendf,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)
      
          CALL vertical_diffusion_u ( u, ru_tendf, config_flags,      &
                                      u_base, c1h, c2h,               &
                                      alt, muu, rdn, rdnw, kvdif,     &
                                      ids, ide, jds, jde, kds, kde,   &
                                      ims, ime, jms, jme, kms, kme,   &
                                      its, ite, jts, jte, kts, kte   )
      CALL pr98_dump3('vdifu_ru_tendf_out',ru_tendf,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)

      CALL pr98_dump3('vdifv_rv_tendf_in',rv_tendf,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)
      
          CALL vertical_diffusion_v ( v, rv_tendf, config_flags,      &
                                      v_base, c1h, c2h,               &
                                      alt, muv, rdn, rdnw, kvdif,     &
                                      ids, ide, jds, jde, kds, kde,   &
                                      ims, ime, jms, jme, kms, kme,   &
                                      its, ite, jts, jte, kts, kte   )
      CALL pr98_dump3('vdifv_rv_tendf_out',rv_tendf,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)

          IF (non_hydrostatic)                                           &
          CALL vertical_diffusion ( 'w', w, rw_tendf, config_flags,      &
                                    c1f, c2f,                            &
                                    alt, mut, rdn, rdnw, kvdif,          &
                                    ids, ide, jds, jde, kds, kde,        &
                                    ims, ime, jms, jme, kms, kme,        &
                                    its, ite, jts, jte, kts, kte        )

          kvdq = 3.*kvdif
          CALL vertical_diffusion_3dmp ( t, t_tendf, config_flags, t_init,     &
                                         c1h, c2h,                             &
                                         alt, mut, rdn, rdnw, kvdq ,           &
                                         ids, ide, jds, jde, kds, kde,         &
                                         ims, ime, jms, jme, kms, kme,         &
                                         its, ite, jts, jte, kts, kte         )

        ENDIF pbl_test

   !  Theta tendency computations.

    END IF diff_opt1

    IF ( diff_6th_opt .NE. 0 ) THEN

      CALL sixth_order_diffusion( 'u', u, ru_tendf, mut, dt,          &
                                       config_flags, c1h, c2h,        &
                                       diff_6th_opt, diff_6th_factor, &
                                       phb, ph,                       &
                                       rdx, rdy,                      &
                                       msftx, msfty,                  &
                                       msfux, msfuy,                  &
                                       msfvx, msfvy,                  &
                                       ids, ide, jds, jde, kds, kde,  &
                                       ims, ime, jms, jme, kms, kme,  &
                                       its, ite, jts, jte, kts, kte )

      CALL sixth_order_diffusion( 'v', v, rv_tendf, mut, dt,          &
                                       config_flags, c1h, c2h,        &
                                       diff_6th_opt, diff_6th_factor, &
                                       phb, ph,                       &
                                       rdx, rdy,                      &
                                       msftx, msfty,                  &
                                       msfux, msfuy,                  &
                                       msfvx, msfvy,                  &
                                       ids, ide, jds, jde, kds, kde,  &
                                       ims, ime, jms, jme, kms, kme,  &
                                       its, ite, jts, jte, kts, kte )

      IF (non_hydrostatic)                                            &
      CALL sixth_order_diffusion( 'w', w, rw_tendf, mut, dt,          &
                                       config_flags, c1f, c2f,        &
                                       diff_6th_opt, diff_6th_factor, &
                                       phb, ph,                       &
                                       rdx, rdy,                      &
                                       msftx, msfty,                  &
                                       msfux, msfuy,                  &
                                       msfvx, msfvy,                  &
                                       ids, ide, jds, jde, kds, kde,  &
                                       ims, ime, jms, jme, kms, kme,  &
                                       its, ite, jts, jte, kts, kte )

      CALL sixth_order_diffusion( 'm', t,  t_tendf, mut, dt,          &
                                       config_flags, c1h, c2h,        &
                                       diff_6th_opt, diff_6th_factor, &
                                       phb, ph,                       &
                                       rdx, rdy,                      &
                                       msftx, msfty,                  &
                                       msfux, msfuy,                  &
                                       msfvx, msfvy,                  &
                                       ids, ide, jds, jde, kds, kde,  &
                                       ims, ime, jms, jme, kms, kme,  &
                                       its, ite, jts, jte, kts, kte )

    ENDIF

    IF( damp_opt .eq. 2 )                                      &
       CALL rk_rayleigh_damp( ru_tendf, rv_tendf,              &
                              rw_tendf, t_tendf,               &
                              u, v, w, t, t_init,              &
                              c1h, c2h, c1f, c2f,              &
                              mut, muu, muv, ph, phb,          &
                              u_base, v_base, t_base, z_base,  &
                              dampcoef, zdamp,                 &
                              ids, ide, jds, jde, kds, kde,    &
                              ims, ime, jms, jme, kms, kme,    &
                              its, ite, jts, jte, kts, kte   )

    IF( rad_nudge .eq. 1 )                                     &
       CALL theta_relaxation( t_tendf, t, t_init,              &
                              mut, c1h, c2h, ph, phb,          &
                              t_base, z_base,                  &
                              ids, ide, jds, jde, kds, kde,    &
                              ims, ime, jms, jme, kms, kme,    &
                              its, ite, jts, jte, kts, kte   )

  END IF forward_step


   CALL pr98_dump3('dyn_ru_final',ru_tend,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)
   CALL pr98_dump3('dyn_rv_final',rv_tend,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)
   CALL pr98_dump3('dyn_rw_final',rw_tend,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)
END SUBROUTINE rk_tendency

!-------------------------------------------------------------------------------

SUBROUTINE rk_addtend_dry ( ru_tend, rv_tend, rw_tend, ph_tend, t_tend,      &
                            ru_tendf, rv_tendf, rw_tendf, ph_tendf, t_tendf, &
                            u_save, v_save, w_save, ph_save, t_save,         &
                            mu_tend, mu_tendf, rk_step, c1, c2,              &
                            h_diabatic, mut, msftx, msfty, msfux, msfuy,     &
                            msfvx, msfvx_inv, msfvy,                         &
                            ids,ide, jds,jde, kds,kde,                       &
                            ims,ime, jms,jme, kms,kme,                       &
                            ips,ipe, jps,jpe, kps,kpe,                       &
                            its,ite, jts,jte, kts,kte                       )

   IMPLICIT NONE

   !  Input data.

   INTEGER ,               INTENT(IN   ) :: ids, ide, jds, jde, kds, kde, &
                                            ims, ime, jms, jme, kms, kme, &
                                            ips, ipe, jps, jpe, kps, kpe, &
                                            its, ite, jts, jte, kts, kte
   INTEGER ,               INTENT(IN   ) :: rk_step

   REAL , DIMENSION( ims:ime , kms:kme, jms:jme  ) , INTENT(INOUT) :: ru_tend, &
                                                                      rv_tend, &
                                                                      rw_tend, &
                                                                      ph_tend, &
                                                                      t_tend,  &
                                                                      ru_tendf, &
                                                                      rv_tendf, &
                                                                      rw_tendf, &
                                                                      ph_tendf, &
                                                                      t_tendf

   REAL , DIMENSION( ims:ime , jms:jme  ) , INTENT(INOUT) :: mu_tend, &
                                                             mu_tendf

   REAL , DIMENSION( ims:ime , kms:kme, jms:jme  ) , INTENT(IN   ) ::  u_save,  &
                                                                       v_save,  &
                                                                       w_save,  &
                                                                      ph_save,  &
                                                                       t_save,  &
                                                                      h_diabatic

   REAL , DIMENSION( ims:ime , jms:jme ) ,         INTENT(IN   ) :: mut,       &
                                                                    msftx,     &
                                                                    msfty,     &
                                                                    msfux,     &
                                                                    msfuy,     &
                                                                    msfvx,     &
                                                                    msfvx_inv, &
                                                                    msfvy

   REAL , DIMENSION( kms:kme ) ,         INTENT(IN   ) :: c1, c2

! Local
   INTEGER :: i, j, k

!<DESCRIPTION>
!
! rk_addtend_dry constructs the full large-timestep tendency terms for
! momentum (u,v,w), theta and geopotential equations.   This is accomplished
! by combining the physics tendencies (in *tendf; these are computed
! the first RK substep, held fixed thereafter) with the RK tendencies
! (in *tend, these include advection, pressure gradient, etc;
! these change each rk substep).  Output is in *tend.
!
!</DESCRIPTION>

!  Finally, add the forward-step tendency to the rk_tendency

! u/v/w/save contain bc tendency that needs to be multiplied by msf
! (u by msfuy, v by msfvx)
!  before adding it to physics tendency (*tendf)
! For momentum we need the final tendency to include an inverse msf
! physics/bc tendency needs to be divided, advection tendency already has it

! For scalars we need the final tendency to include an inverse msf (msfty)
! advection tendency is OK, physics/bc tendency needs to be divided by msf

   DO j = jts,MIN(jte,jde-1)
   DO k = kts,kte-1
   DO i = its,ite
     ! multiply by my to uncouple u
     IF(rk_step == 1)ru_tendf(i,k,j) = ru_tendf(i,k,j) +  u_save(i,k,j)*msfuy(i,j)
     ! divide by my to couple u
     ru_tend(i,k,j) = ru_tend(i,k,j) + ru_tendf(i,k,j)/msfuy(i,j)
   ENDDO
   ENDDO
   ENDDO

   DO j = jts,jte
   DO k = kts,kte-1
   DO i = its,MIN(ite,ide-1)
     ! multiply by mx to uncouple v
     IF(rk_step == 1)rv_tendf(i,k,j) = rv_tendf(i,k,j) +  v_save(i,k,j)*msfvx(i,j)
     ! divide by mx to couple v
     rv_tend(i,k,j) = rv_tend(i,k,j) + rv_tendf(i,k,j)*msfvx_inv(i,j)
   ENDDO
   ENDDO
   ENDDO

   DO j = jts,MIN(jte,jde-1)
   DO k = kts,kte
   DO i = its,MIN(ite,ide-1)
     ! multiply by my to uncouple w
     IF(rk_step == 1)rw_tendf(i,k,j) = rw_tendf(i,k,j) +  w_save(i,k,j)*msfty(i,j)
     ! divide by my to couple w
     rw_tend(i,k,j) = rw_tend(i,k,j) + rw_tendf(i,k,j)/msfty(i,j)
     IF(rk_step == 1)ph_tendf(i,k,j) = ph_tendf(i,k,j) +  ph_save(i,k,j)
     ! divide by my to couple scalar
     ph_tend(i,k,j) = ph_tend(i,k,j) + ph_tendf(i,k,j)/msfty(i,j)
   ENDDO
   ENDDO
   ENDDO

   DO j = jts,MIN(jte,jde-1)
   DO k = kts,kte-1
   DO i = its,MIN(ite,ide-1)
     IF(rk_step == 1)t_tendf(i,k,j) = t_tendf(i,k,j) +  t_save(i,k,j)
     ! divide by my to couple theta
      t_tend(i,k,j) =  t_tend(i,k,j) +  t_tendf(i,k,j)/msfty(i,j)  &
                                     +  (c1(k)*mut(i,j)+c2(k))*h_diabatic(i,k,j)/msfty(i,j)
     ! divide by my to couple heating
   ENDDO
   ENDDO
   ENDDO

   DO j = jts,MIN(jte,jde-1)
   DO i = its,MIN(ite,ide-1)
! mu tendencies not coupled with 1/msf
      MU_TEND(i,j) =  MU_TEND(i,j) +  MU_TENDF(i,j)
   ENDDO
   ENDDO

END SUBROUTINE rk_addtend_dry

!-------------------------------------------------------------------------------

SUBROUTINE rk_scalar_tend ( scs, sce, config_flags,          &
                            tenddec,                         &
                            rk_step, dt_step,                &
                            ru, rv, ww, wwE, wwI,            &  
                            u_old, v_old,                    &  
                            mut, mub, mu_old,                &
                            c1h, c2h, c1f, c2f, alt,         &
                            scalar_old, scalar,              &
                            scalar_tends, advect_tend,       &
                            h_tendency, z_tendency,          &
                            RQVFTEN,                         &
                            base, moist_step, fnm, fnp,      &
                            msfux, msfuy, msfvx, msfvx_inv,  &
                            msfvy, msftx, msfty,             &
                            rdx, rdy, rdn, rdnw,             &
                            khdif, kvdif, xkmhd,             &
                            diff_6th_opt, diff_6th_factor,   &
                            adv_opt,                         &
                            phb, ph,                         &
                            mix2_off, mix6_off,              &
                            ids, ide, jds, jde, kds, kde,    &
                            ims, ime, jms, jme, kms, kme,    &
                            its, ite, jts, jte, kts, kte, all_pair_diffusion_delta, &
                            all_pair_diffusion_old, all_pair_diffusion_tendency32, &
                            all_pair_diffusion_identity, &
                            all_pair_diffusion_valid )

   IMPLICIT NONE

   !  Input data.

   TYPE(grid_config_rec_type   ) ,   INTENT(IN   ) :: config_flags

   LOGICAL ,                INTENT(IN   ) :: tenddec ! tendency term

   INTEGER ,                INTENT(IN   ) :: rk_step, scs, sce
   INTEGER ,                INTENT(IN   ) :: ids, ide, jds, jde, kds, kde, &
                                             ims, ime, jms, jme, kms, kme, &
                                             its, ite, jts, jte, kts, kte
   REAL(real64), OPTIONAL, INTENT(INOUT) :: &
      all_pair_diffusion_delta(ims:ime,kms:kme,jms:jme,8), &
      all_pair_diffusion_old(ims:ime,kms:kme,jms:jme,4)
   REAL, OPTIONAL, INTENT(INOUT) :: &
      all_pair_diffusion_tendency32(ims:ime,kms:kme,jms:jme,8)
   INTEGER, OPTIONAL, INTENT(INOUT) :: all_pair_diffusion_identity(8), &
      all_pair_diffusion_valid(8)

   LOGICAL , INTENT(IN   ) :: moist_step

   REAL, DIMENSION(ims:ime, kms:kme, jms:jme , scs:sce ),                &
                                         INTENT(IN   )  :: scalar, scalar_old

   REAL, DIMENSION(ims:ime, kms:kme, jms:jme , scs:sce ),                      &
                                         INTENT(INOUT)  :: scalar_tends
                                                    
   REAL, DIMENSION(ims:ime, kms:kme, jms:jme  ), INTENT(INOUT) :: advect_tend
   REAL, DIMENSION(ims:ime, kms:kme, jms:jme  ), INTENT(  OUT) :: h_tendency, z_tendency

   REAL, DIMENSION(ims:ime, kms:kme, jms:jme  ), INTENT(OUT  ) :: RQVFTEN

   REAL, DIMENSION(ims:ime, kms:kme, jms:jme  ), INTENT(IN   ) ::     ru,     &
                                                                      rv,     &
                                                                      ww,     &
                                                                      u_old,  &
                                                                      v_old,  &
                                                                      xkmhd,  &
                                                                      alt,    &
                                                                      phb,    &
                                                                      ph

   REAL , DIMENSION( kms:kme ) ,                 INTENT(IN   ) :: fnm,  &
                                                                  fnp,  &
                                                                  rdn,  &
                                                                  rdnw, &
                                                                  base

   REAL , DIMENSION( kms:kme ) ,                 INTENT(IN   ) :: c1h, c2h
   REAL , DIMENSION( kms:kme ) ,                 INTENT(IN   ) :: c1f, c2f

   REAL , DIMENSION( ims:ime , jms:jme ) ,       INTENT(IN   ) :: msfux,    &
                                                                  msfuy,    &
                                                                  msfvx,    &
                                                                  msfvx_inv,    &
                                                                  msfvy,    &
                                                                  msftx,    &
                                                                  msfty,    &
                                                                  mub,     &
                                                                  mut,     &
                                                                  mu_old

   REAL ,                                        INTENT(IN   ) :: rdx,     &
                                                                  rdy,     &
                                                                  khdif,   &
                                                                  kvdif

   INTEGER, INTENT( IN ) :: diff_6th_opt
   REAL,    INTENT( IN ) :: diff_6th_factor

   REAL,    INTENT(IN   ) :: dt_step    ! This is the local dt for each RK sub-step

   INTEGER, INTENT(IN   ) :: adv_opt          
   LOGICAL, INTENT(IN   ) :: mix2_off, mix6_off

   ! Local data
  
   INTEGER :: im, i,j,k
   REAL, ALLOCATABLE :: pr87_rain_tendency_before(:,:,:)
   REAL(real64), ALLOCATABLE :: pr87_rain_diffusion_increment(:,:,:)
   INTEGER :: pr87_diff_i_start, pr87_diff_i_end, pr87_diff_j_start, pr87_diff_j_end
   INTEGER :: pr87_diff_k_end, pr87_diff_i, pr87_diff_j, pr87_diff_k, pr87_diff_channel
   LOGICAL :: pr87_diff_specified, pr87_capture_rain_diffusion
   INTEGER :: pr92_u,pr92_target,pr92_i,pr92_j,pr92_k,pr92_dx,pr92_dy
   INTEGER,PARAMETER :: pr92_targets(3,12)=RESHAPE([ &
       127,5,22, &
       170,42,23, &
       171,43,23, &
       163,44,20, &
       158,47,20, &
       232,203,20, &
       203,213,21, &
       11,216,21, &
       2,218,13, &
       22,228,21, &
       41,229,14, &
       43,239,19], [3,12])
   INTEGER :: time_step
   INTEGER :: rk_order
   REAL    :: dt         ! This is the large time step computed below

   REAL    :: khdq, kvdq, tendency

! IEVA variables
   REAL, DIMENSION( ims:ime, kms:kme, jms:jme ) :: wwE, wwI  
   REAL, DIMENSION( ims:ime, jms:jme )          :: mut_old  
   LOGICAL                                      :: ieva

!<DESCRIPTION>
!
! rk_scalar_tend calls routines that computes scalar tendency from advection
! and 3D mixing (TKE or fixed eddy viscosities).
!
!</DESCRIPTION>

   khdq = khdif/prandtl
   kvdq = kvdif/prandtl

   rk_order = config_flags%rk_ord
   dt       = dt_step * (rk_order - rk_step + 1)    ! need large time step

! IEVA
                         
   ieva = CHK_IEVA( config_flags, rk_step )

! Code for splitting vertical velocity into ex/im parts

   CALL WW_SPLIT(wwE, wwI,                         &
                 u_old,   v_old,    ww,            &
                 mut, rdnw, msfty,                 &
                 c1f, c2f,                         &
                 rdx, rdy, msfux, msfuy,           &
                 msfvx, msfvy, dt,                 &
                 config_flags, rk_step,            &
                 ids, ide, jds, jde, kds, kde,     &
                 ims, ime, jms, jme, kms, kme,     &
                 its, ite, jts, jte, kts, kte )
                 
                 
   IF( ieva ) THEN
   
! Need an estimate of the mut at the original ('n') time level...

    CALL calculate_full( mut_old,  mub, mu_old,     &
                         ids, ide, jds, jde, 1, 2,  &
                         ims, ime, jms, jme, 1, 1,  &
                         its, ite, jts, jte, 1, 1 )
   ENDIF
   
   CALL nl_get_time_step ( 1, time_step )

   scalar_loop : DO im = scs, sce

     CALL zero_tend ( advect_tend(ims,kms,jms),     &
                      ids, ide, jds, jde, kds, kde, &
                      ims, ime, jms, jme, kms, kme, &
                      its, ite, jts, jte, kts, kte )

     CALL zero_tend ( h_tendency(ims,kms,jms),      &
                      ids, ide, jds, jde, kds, kde, &
                      ims, ime, jms, jme, kms, kme, &
                      its, ite, jts, jte, kts, kte )

     CALL zero_tend ( z_tendency(ims,kms,jms),      &
                      ids, ide, jds, jde, kds, kde, &
                      ims, ime, jms, jme, kms, kme, &
                      its, ite, jts, jte, kts, kte )

     CALL nl_get_time_step ( 1, time_step )

      IF( (rk_step == rk_order) .and. (adv_opt == POSITIVEDEF) ) THEN

        CALL advect_scalar_pd       ( scalar(ims,kms,jms,im),             &
                                      scalar_old(ims,kms,jms,im),         &
                                      advect_tend(ims,kms,jms),           &
                                      h_tendency(ims,kms,jms),            &
                                      z_tendency(ims,kms,jms),            &
                                      ru, rv, wwE, c1h, c2h,              &
                                      mut, mub, mu_old,                   &
                                      time_step, config_flags, tenddec,   &
                                      msfux, msfuy, msfvx, msfvy,         &
                                      msftx, msfty, fnm, fnp,             &
                                      rdx, rdy, rdnw, dt_step,            &  
                                      ids, ide, jds, jde, kds, kde,       &
                                      ims, ime, jms, jme, kms, kme,       &
                                      its, ite, jts, jte, kts, kte     )

      ELSE IF( (rk_step == rk_order) .and. (adv_opt == MONOTONIC) ) THEN

        CALL advect_scalar_mono       ( scalar(ims,kms,jms,im),             &
                                        scalar_old(ims,kms,jms,im),         &
                                        advect_tend(ims,kms,jms),           &
                                        h_tendency(ims,kms,jms),            &
                                        z_tendency(ims,kms,jms),            &
                                        ru, rv, wwE, wwI, c1h, c2h,         &
                                        mut, mub, mu_old,                   &
                                        config_flags, tenddec,              &
                                        msfux, msfuy, msfvx, msfvy,         &
                                        msftx, msfty, fnm, fnp,             &
                                        rdx, rdy, rdnw, dt_step,            &
                                        ids, ide, jds, jde, kds, kde,       &
                                        ims, ime, jms, jme, kms, kme,       &
                                        its, ite, jts, jte, kts, kte     )

      ELSE IF( (rk_step == rk_order) .and. (adv_opt == WENO_SCALAR) ) THEN

        CALL advect_scalar_weno ( scalar(ims,kms,jms,im),        &
                                  scalar(ims,kms,jms,im),        &
                                  advect_tend(ims,kms,jms),      &
                                  ru, rv, wwE, c1h, c2h,         &
                                  mut, time_step,                &
                                  config_flags,                  &
                                  msfux, msfuy, msfvx, msfvy,    &
                                  msftx, msfty, fnm, fnp,        &
                                  rdx, rdy, rdnw,                &
                                  ids, ide, jds, jde, kds, kde,  &
                                  ims, ime, jms, jme, kms, kme,  &
                                  its, ite, jts, jte, kts, kte  )

      ELSEIF( (rk_step == rk_order) .and. (adv_opt == WENOPD_SCALAR) ) THEN

        CALL advect_scalar_wenopd   ( scalar(ims,kms,jms,im),             &
                                      scalar_old(ims,kms,jms,im),         &
                                      advect_tend(ims,kms,jms),           &
                                      ru, rv, wwE, c1h, c2h,              &
                                      mut, mub, mu_old,                   &
                                      time_step, config_flags,            &
                                      msfux, msfuy, msfvx, msfvy,         &
                                      msftx, msfty, fnm, fnp,             &
                                      rdx, rdy, rdnw, dt_step,            &  ! dt_step == dt
                                      ids, ide, jds, jde, kds, kde,       &
                                      ims, ime, jms, jme, kms, kme,       &
                                      its, ite, jts, jte, kts, kte     )

      ELSE

        CALL advect_scalar     ( scalar(ims,kms,jms,im),        &
                                 scalar(ims,kms,jms,im),        &
                                 advect_tend(ims,kms,jms),      &
                                 ru, rv, wwE, c1h, c2h,         &
                                 mut, time_step,                &
                                 config_flags,                  &
                                 msfux, msfuy, msfvx, msfvy,    &
                                 msftx, msfty, fnm, fnp,        &
                                 rdx, rdy, rdnw,                &
                                 ids, ide, jds, jde, kds, kde,  &
                                 ims, ime, jms, jme, kms, kme,  &
                                 its, ite, jts, jte, kts, kte  )

      END IF

      IF( ieva ) THEN
     
       CALL advect_s_implicit ( scalar(ims,kms,jms,im),         &
                                scalar_old(ims,kms,jms,im),     &
                                advect_tend(ims,kms,jms),       &
                                ru, rv, wwI,                    &
                                c1h, c2h,                       &
                                mut_old, mut, mut,              &
                                config_flags,                   &
                                msfux, msfuy, msfvx, msfvy,     &
                                msftx, msfty,                   &
                                fnm, fnp,                       &
                                dt_step,                        &
                                rdx, rdy, rdnw,                 &
                                ids, ide, jds, jde, kds, kde,   &
                                ims, ime, jms, jme, kms, kme,   &
                                its, ite, jts, jte, kts, kte )
                               
     ENDIF
    
     IF((config_flags%cu_physics == GDSCHEME .OR. config_flags%cu_physics == G3SCHEME .OR. &
         config_flags%cu_physics == GFSCHEME .OR.    &
         config_flags%cu_physics == KFETASCHEME .OR. config_flags%cu_physics == MSKFSCHEME .OR. &
         config_flags%cu_physics == TIEDTKESCHEME .OR. config_flags%cu_physics == NTIEDTKESCHEME  ) &      ! Tiedtke
                     .and. moist_step .and. ( im == P_QV) ) THEN

        CALL set_tend( RQVFTEN, advect_tend, msfty,    &
                       ids, ide, jds, jde, kds, kde,   &
                       ims, ime, jms, jme, kms, kme,   &
                       its, ite, jts, jte, kts, kte      )
     ENDIF

     rk_step_1: IF( rk_step == 1 ) THEN

       diff_opt1 : IF (config_flags%diff_opt .eq. 1) THEN

         IF (.not. mix2_off) THEN
         pr87_capture_rain_diffusion = .FALSE.
         pr87_diff_channel = 0
         IF (PRESENT(all_pair_diffusion_delta) .AND. rk_step == 1 .AND. &
             config_flags%mp_physics == 37 .AND. config_flags%diff_opt == 1 .AND. &
             .NOT. mix2_off) THEN
           IF (moist_step .AND. im == P_QC) THEN
             pr87_capture_rain_diffusion = .TRUE.
             pr87_diff_channel = 1
           ELSE IF (.NOT. moist_step .AND. im == P_QNC) THEN
             pr87_capture_rain_diffusion = .TRUE.
             pr87_diff_channel = 2
           ELSE IF (moist_step .AND. im == P_QI) THEN
             pr87_capture_rain_diffusion = .TRUE.
             pr87_diff_channel = 3
           ELSE IF (.NOT. moist_step .AND. im == P_QNI) THEN
             pr87_capture_rain_diffusion = .TRUE.
             pr87_diff_channel = 4
           ELSE IF (moist_step .AND. im == P_QR) THEN
             pr87_capture_rain_diffusion = .TRUE.
             pr87_diff_channel = 5
           ELSE IF (.NOT. moist_step .AND. im == P_QNR) THEN
             pr87_capture_rain_diffusion = .TRUE.
             pr87_diff_channel = 6
           ELSE IF (moist_step .AND. im == P_QG) THEN
             pr87_capture_rain_diffusion = .TRUE.
             pr87_diff_channel = 7
           ELSE IF (.NOT. moist_step .AND. im == P_QIB) THEN
             pr87_capture_rain_diffusion = .TRUE.
             pr87_diff_channel = 8
           END IF
         END IF
         IF (pr87_capture_rain_diffusion) THEN
           ALLOCATE(pr87_rain_tendency_before(ims:ime,kms:kme,jms:jme), &
                    pr87_rain_diffusion_increment(ims:ime,kms:kme,jms:jme))
           pr87_rain_tendency_before = scalar_tends(:,:,:,im)
         END IF
           IF (rk_step == 1 .AND. config_flags%mp_physics == 37 .AND. &
               config_flags%diff_opt == 1 .AND. &
               (im == P_QC .OR. im == P_QNC) .AND. &
               90 >= its .AND. 90 <= ite .AND. 14 >= jts .AND. 14 <= jte .AND. &
               11 >= kts .AND. 11 <= kte .AND. 90 > ims .AND. 91 < ime .AND. &
               14 > jms .AND. 15 < jme) THEN
             WRITE(*,'(A,1X,5(I0,1X),2(L1,1X),*(1X,ES25.17E3))') &
                 'PR87_CLOUD_DIFFUSION_PRE', rk_step, im, 90, 14, 11, &
                 moist_step, mix2_off, &
                 dt_step, khdq, &
                 scalar_tends(90,11,14,im), scalar(90,11,14,im), &
                 scalar(89,11,14,im), scalar(91,11,14,im), &
                 scalar(90,11,13,im), scalar(90,11,15,im), &
                 mut(90,14), mut(89,14), mut(91,14), mut(90,13), mut(90,15), &
                 c1h(11), c2h(11), &
                 xkmhd(90,11,14), xkmhd(89,11,14), xkmhd(91,11,14), &
                 xkmhd(90,11,13), xkmhd(90,11,15), &
                 msfux(89,14), msfux(90,14), msfux(91,14), &
                 msfuy(89,14), msfuy(90,14), msfuy(91,14), &
                 msfvx_inv(90,14), msfvx_inv(90,15), msfvy(90,14), msfvy(90,15), &
                 msftx(90,14), msfty(90,14), rdx, rdy
           END IF
CALL horizontal_diffusion ( 'm', scalar(ims,kms,jms,im),            &
                                            scalar_tends(ims,kms,jms,im), mut, &
                                            c1h, c2h, config_flags,            &
                                            msfux, msfuy, msfvx, msfvx_inv,    &
                                            msfvy, msftx, msfty,               &
                                            khdq , xkmhd, rdx, rdy,            &
                                            ids, ide, jds, jde, kds, kde,      &
                                            ims, ime, jms, jme, kms, kme,      &
                                            its, ite, jts, jte, kts, kte      )
           IF (rk_step == 1 .AND. config_flags%mp_physics == 37 .AND. &
               config_flags%diff_opt == 1 .AND. &
               (im == P_QC .OR. im == P_QNC) .AND. &
               90 >= its .AND. 90 <= ite .AND. 14 >= jts .AND. 14 <= jte .AND. &
               11 >= kts .AND. 11 <= kte .AND. 90 > ims .AND. 91 < ime .AND. &
               14 > jms .AND. 15 < jme) THEN
             WRITE(*,'(A,1X,5(I0,1X),2(L1,1X),*(1X,ES25.17E3))') &
                 'PR87_CLOUD_DIFFUSION_POST', rk_step, im, 90, 14, 11, &
                 moist_step, mix2_off, &
                 dt_step, khdq, &
                 scalar_tends(90,11,14,im), scalar(90,11,14,im), &
                 scalar(89,11,14,im), scalar(91,11,14,im), &
                 scalar(90,11,13,im), scalar(90,11,15,im), &
                 mut(90,14), mut(89,14), mut(91,14), mut(90,13), mut(90,15), &
                 c1h(11), c2h(11), &
                 xkmhd(90,11,14), xkmhd(89,11,14), xkmhd(91,11,14), &
                 xkmhd(90,11,13), xkmhd(90,11,15), &
                 msfux(89,14), msfux(90,14), msfux(91,14), &
                 msfuy(89,14), msfuy(90,14), msfuy(91,14), &
                 msfvx_inv(90,14), msfvx_inv(90,15), msfvy(90,14), msfvy(90,15), &
                 msftx(90,14), msfty(90,14), rdx, rdy
           END IF

         IF (pr87_capture_rain_diffusion) THEN
           pr87_diff_specified = config_flags%specified .OR. config_flags%nested
           pr87_diff_i_start = its
           pr87_diff_i_end = MIN(ite,ide-1)
           pr87_diff_j_start = jts
           pr87_diff_j_end = MIN(jte,jde-1)
           IF (config_flags%open_xs .OR. pr87_diff_specified) &
             pr87_diff_i_start = MAX(ids+1,its)
           IF (config_flags%open_xe .OR. pr87_diff_specified) &
             pr87_diff_i_end = MIN(ide-2,ite)
           IF (config_flags%open_ys .OR. pr87_diff_specified) &
             pr87_diff_j_start = MAX(jds+1,jts)
           IF (config_flags%open_ye .OR. pr87_diff_specified) &
             pr87_diff_j_end = MIN(jde-2,jte)
           IF (config_flags%periodic_x) pr87_diff_i_start = its
           IF (config_flags%periodic_x) pr87_diff_i_end = MIN(ite,ide-1)
           pr87_diff_k_end = MIN(kte,kde-1)
           IF ((PRESENT(all_pair_diffusion_old) .NEQV. &
                PRESENT(all_pair_diffusion_identity)).OR. &
               (PRESENT(all_pair_diffusion_old) .NEQV. &
                PRESENT(all_pair_diffusion_valid)).OR. &
               (PRESENT(all_pair_diffusion_old) .NEQV. &
                PRESENT(all_pair_diffusion_tendency32))) &
             CALL wrf_error_fatal('PR91 incomplete source diffusion cache')
           IF (PRESENT(all_pair_diffusion_old)) THEN
             IF (ANY(all_pair_diffusion_valid/=0).AND. &
                 ANY(all_pair_diffusion_identity(2:8)/=[rk_step,pr87_diff_i_start, &
                     pr87_diff_i_end,pr87_diff_j_start,pr87_diff_j_end,kts,pr87_diff_k_end])) &
               CALL wrf_error_fatal('PR91 producer diffusion bounds changed within RK1')
             all_pair_diffusion_identity(2:8) = [rk_step,pr87_diff_i_start, &
                 pr87_diff_i_end,pr87_diff_j_start,pr87_diff_j_end,kts,pr87_diff_k_end]
           END IF
           CALL horizontal_diffusion64( &
               scalar(ims,kms,jms,im), mut, c1h, c2h, &
               msfux, msfuy, msfvx_inv, msfvy, msftx, msfty, xkmhd, &
               rdx, rdy, ims, ime, kms, kme, jms, jme, &
               pr87_diff_i_start, pr87_diff_i_end, &
               pr87_diff_j_start, pr87_diff_j_end, kts, pr87_diff_k_end, &
               pr87_rain_diffusion_increment)
           ! Coordinate selection controls diagnostic I/O only, never a physical update.
           IF (pr87_diff_channel>=7.AND.PRESENT(all_pair_diffusion_identity)) THEN
             IF (all_pair_diffusion_identity(1)==15) THEN
               OPEN(NEWUNIT=pr92_u,FILE='pr92_diffusion_producer.raw', &
                    STATUS='UNKNOWN',POSITION='APPEND')
               DO pr92_target=1,SIZE(pr92_targets,2)
                 pr92_i=pr92_targets(1,pr92_target)
                 pr92_j=pr92_targets(2,pr92_target)
                 pr92_k=pr92_targets(3,pr92_target)
                 IF (pr92_i<pr87_diff_i_start.OR.pr92_i>pr87_diff_i_end.OR. &
                     pr92_j<pr87_diff_j_start.OR.pr92_j>pr87_diff_j_end.OR. &
                     pr92_k<kts.OR.pr92_k>pr87_diff_k_end) CYCLE
                 WRITE(pr92_u,'(A,7(1X,I0))') 'PR92_PRODUCER', &
                   all_pair_diffusion_identity(1),rk_step,pr87_diff_channel,im,pr92_i,pr92_j,pr92_k
                 WRITE(pr92_u,'(A,8(1X,I0))') 'PR92_PRODUCER_BOUNDS',all_pair_diffusion_identity
                 WRITE(pr92_u,'(A,2(1X,Z8.8),1X,Z16.16)') 'PR92_TENDENCY', &
                   TRANSFER(pr87_rain_tendency_before(pr92_i,pr92_k,pr92_j),0_4), &
                   TRANSFER(scalar_tends(pr92_i,pr92_k,pr92_j,im),0_4), &
                   TRANSFER(pr87_rain_diffusion_increment(pr92_i,pr92_k,pr92_j),0_8)
                 WRITE(pr92_u,'(A,4(1X,Z8.8))') 'PR92_PRODUCER_SCALE', &
                   TRANSFER(c1h(pr92_k),0_4),TRANSFER(c2h(pr92_k),0_4), &
                   TRANSFER(rdx,0_4),TRANSFER(rdy,0_4)
                 DO pr92_dy=-1,1
                   WRITE(pr92_u,'(A,1X,I0,9(1X,Z8.8))') 'PR92_PRODUCER_STENCIL',pr92_dy, &
                     (TRANSFER(scalar(pr92_i+pr92_dx,pr92_k,pr92_j+pr92_dy,im),0_4),pr92_dx=-1,1), &
                     (TRANSFER(xkmhd(pr92_i+pr92_dx,pr92_k,pr92_j+pr92_dy),0_4),pr92_dx=-1,1), &
                     (TRANSFER(mut(pr92_i+pr92_dx,pr92_j+pr92_dy),0_4),pr92_dx=-1,1)
                 END DO
                 WRITE(pr92_u,'(A,10(1X,Z8.8))') 'PR92_PRODUCER_METRICS', &
                   TRANSFER(msfux(pr92_i,pr92_j),0_4),TRANSFER(msfux(pr92_i+1,pr92_j),0_4), &
                   TRANSFER(msfuy(pr92_i,pr92_j),0_4),TRANSFER(msfuy(pr92_i+1,pr92_j),0_4), &
                   TRANSFER(msfvx_inv(pr92_i,pr92_j),0_4),TRANSFER(msfvx_inv(pr92_i,pr92_j+1),0_4), &
                   TRANSFER(msfvy(pr92_i,pr92_j),0_4),TRANSFER(msfvy(pr92_i,pr92_j+1),0_4), &
                   TRANSFER(msftx(pr92_i,pr92_j),0_4),TRANSFER(msfty(pr92_i,pr92_j),0_4)
                 WRITE(pr92_u,'(A)') 'PR92_PRODUCER_END'
               END DO
               CLOSE(pr92_u)
             END IF
           END IF
           IF (PRESENT(all_pair_diffusion_tendency32).AND.pr87_diff_channel<=4) THEN
             all_pair_diffusion_tendency32(:,:,:,pr87_diff_channel)=pr87_rain_tendency_before
             all_pair_diffusion_tendency32(:,:,:,pr87_diff_channel+4)=scalar_tends(:,:,:,im)
           END IF
           DO pr87_diff_j = pr87_diff_j_start, pr87_diff_j_end
             DO pr87_diff_k = kts, pr87_diff_k_end
               DO pr87_diff_i = pr87_diff_i_start, pr87_diff_i_end
                 all_pair_diffusion_delta(pr87_diff_i,pr87_diff_k,pr87_diff_j, &
                                      pr87_diff_channel) = &
                      REAL(pr87_rain_tendency_before(pr87_diff_i,pr87_diff_k,pr87_diff_j),real64) + &
                      pr87_rain_diffusion_increment(pr87_diff_i,pr87_diff_k,pr87_diff_j) - &
                      REAL(scalar_tends(pr87_diff_i,pr87_diff_k,pr87_diff_j,im),real64)
                 IF (PRESENT(all_pair_diffusion_old).AND.pr87_diff_channel<=4) &
                   all_pair_diffusion_old(pr87_diff_i,pr87_diff_k,pr87_diff_j, &
                                          pr87_diff_channel) = &
                        pr87_rain_diffusion_increment(pr87_diff_i,pr87_diff_k,pr87_diff_j)
                 ! Cache validity is set after all old and REAL32 fields are captured.
               END DO
             END DO
           END DO
           IF (PRESENT(all_pair_diffusion_valid).AND.pr87_diff_channel<=4) THEN
             IF (.NOT.ALL(ieee_is_finite(all_pair_diffusion_old(pr87_diff_i_start:pr87_diff_i_end, &
                 kts:pr87_diff_k_end,pr87_diff_j_start:pr87_diff_j_end,pr87_diff_channel)))) &
               CALL wrf_error_fatal('PR91 nonfinite old diffusion cache')
             IF (.NOT.ALL(ieee_is_finite(all_pair_diffusion_tendency32(pr87_diff_i_start:pr87_diff_i_end, &
                 kts:pr87_diff_k_end,pr87_diff_j_start:pr87_diff_j_end,pr87_diff_channel))).OR. &
                 .NOT.ALL(ieee_is_finite(all_pair_diffusion_tendency32(pr87_diff_i_start:pr87_diff_i_end, &
                 kts:pr87_diff_k_end,pr87_diff_j_start:pr87_diff_j_end,pr87_diff_channel+4)))) &
               CALL wrf_error_fatal('PR91 nonfinite before/after tendency cache')
             all_pair_diffusion_valid(pr87_diff_channel)=1
           END IF
           DEALLOCATE(pr87_rain_tendency_before,pr87_rain_diffusion_increment)
         END IF

         END IF

         pbl_test : IF (config_flags%bl_pbl_physics .eq. 0) THEN

           IF( (moist_step) .and. ( im == P_QV)) THEN

              CALL vertical_diffusion_mp ( scalar(ims,kms,jms,im),       &
                                           scalar_tends(ims,kms,jms,im), &
                                           config_flags, base, c1h, c2h, &
                                           alt, mut, rdn, rdnw, kvdq ,   &
                                           ids, ide, jds, jde, kds, kde, &
                                           ims, ime, jms, jme, kms, kme, &
                                           its, ite, jts, jte, kts, kte )

           ELSE

              CALL vertical_diffusion (  'm', scalar(ims,kms,jms,im),       &
                                              scalar_tends(ims,kms,jms,im), &
                                              config_flags, c1h, c2h,       &
                                              alt, mut, rdn, rdnw, kvdq,    &
                                              ids, ide, jds, jde, kds, kde, &
                                              ims, ime, jms, jme, kms, kme, &
                                              its, ite, jts, jte, kts, kte )

           END IF

         ENDIF pbl_test

       ENDIF diff_opt1

       IF ( (diff_6th_opt .NE. 0) .and. (.not. mix6_off) ) THEN

         CALL sixth_order_diffusion( 'm', scalar(ims,kms,jms,im),        &
                                          scalar_tends(ims,kms,jms,im),  &
                                          mut, dt_step,                  &
                                          config_flags, c1h, c2h,        &
                                          diff_6th_opt, diff_6th_factor, &
                                          phb, ph,                       &
                                          rdx, rdy,                      &
                                          msftx, msfty,                  &
                                          msfux, msfuy,                  &
                                          msfvx, msfvy,                  &
                                          ids, ide, jds, jde, kds, kde,  &
                                          ims, ime, jms, jme, kms, kme,  &
                                          its, ite, jts, jte, kts, kte )
       ENDIF
       
     ENDIF rk_step_1

   END DO scalar_loop

END SUBROUTINE rk_scalar_tend

!-------------------------------------------------------------------------------

SUBROUTINE q_diabatic_add ( scs, sce,                        &
                            dt, mut, c1, c2,                 &
                            qv_diabatic, qc_diabatic,        &
                            scalar_tends,                    &
                            ids, ide, jds, jde, kds, kde,    &
                            ims, ime, jms, jme, kms, kme,    &
                            its, ite, jts, jte, kts, kte    )

   IMPLICIT NONE

   !  Input data.

   INTEGER ,                INTENT(IN   ) :: scs, sce
   INTEGER ,                INTENT(IN   ) :: ids, ide, jds, jde, kds, kde, &
                                             ims, ime, jms, jme, kms, kme, &
                                             its, ite, jts, jte, kts, kte

   REAL,     DIMENSION( ims:ime, jms:jme )                        , &
             INTENT(IN   )   ::                                 mut

   REAL , DIMENSION( kms:kme ) , INTENT(IN   ) :: c1, c2

   REAL, DIMENSION(ims:ime, kms:kme, jms:jme ),                &
                                         INTENT(IN   )  :: qv_diabatic, qc_diabatic

   REAL, DIMENSION(ims:ime, kms:kme, jms:jme , scs:sce ),                &
                                         INTENT(INOUT)  :: scalar_tends

   REAL ,                                        INTENT(IN   ) :: dt

   ! Local data
  
   INTEGER :: im, i,j,k

!<DESCRIPTION>
!
!</DESCRIPTION>

!!!       print *,'  q_diab add: '
!!!       print *,its,MIN(ite,ide-1)
!!!       print *,jts,MIN(jte,jde-1)
!!!       print *,kts,kte-1

   scalar_loop : DO im = scs, sce

     IF( im.eq.p_qv )THEN
!!!       print *,'  qv '
       DO j = jts,MIN(jte,jde-1)
       DO k = kts,kte-1
       DO i = its,MIN(ite,ide-1)
         scalar_tends(i,k,j,im) = scalar_tends(i,k,j,im) + qv_diabatic(i,k,j)*(c1(k)*mut(I,J)+c2(k))
       ENDDO
       ENDDO
       ENDDO
     ENDIF
     IF( im.eq.p_qc )THEN
!!!       print *,'  qc '
       DO j = jts,MIN(jte,jde-1)
       DO k = kts,kte-1
       DO i = its,MIN(ite,ide-1)
         scalar_tends(i,k,j,im) = scalar_tends(i,k,j,im) + qc_diabatic(i,k,j)*(c1(k)*mut(I,J)+c2(k))
       ENDDO
       ENDDO
       ENDDO
     ENDIF

   END DO scalar_loop

END SUBROUTINE q_diabatic_add

!-------------------------------------------------------------------------------

SUBROUTINE q_diabatic_subtr( scs, sce,                       &
                            dt,                     &
                            qv_diabatic, qc_diabatic,        &
                            scalar,              &
                            ids, ide, jds, jde, kds, kde,    &
                            ims, ime, jms, jme, kms, kme,    &
                            its, ite, jts, jte, kts, kte    )

   IMPLICIT NONE

   !  Input data.

   INTEGER ,                INTENT(IN   ) :: scs, sce
   INTEGER ,                INTENT(IN   ) :: ids, ide, jds, jde, kds, kde, &
                                             ims, ime, jms, jme, kms, kme, &
                                             its, ite, jts, jte, kts, kte

   REAL, DIMENSION(ims:ime, kms:kme, jms:jme ),                &
                                         INTENT(IN   )  :: qv_diabatic, qc_diabatic

   REAL, DIMENSION(ims:ime, kms:kme, jms:jme , scs:sce ),                &
                                         INTENT(INOUT)  :: scalar

   REAL ,                                        INTENT(IN   ) :: dt

   ! Local data
  
   INTEGER :: im, i,j,k

!<DESCRIPTION>
!
!</DESCRIPTION>


!!!       print *,'  q_diab subtr, dt = : ',dt
!!!       print *,its,MIN(ite,ide-1)
!!!       print *,jts,MIN(jte,jde-1)
!!!       print *,kts,kte-1

   scalar_loop : DO im = scs, sce

     IF( im.eq.p_qv )THEN
!!!       print *,'  qv '
       DO j = jts,MIN(jte,jde-1)
       DO k = kts,kte-1
       DO i = its,MIN(ite,ide-1)
         scalar(i,k,j,im) = scalar(i,k,j,im) - dt*qv_diabatic(i,k,j)
       ENDDO
       ENDDO
       ENDDO
     ENDIF
     IF( im.eq.p_qc )THEN
!!!       print *,'  qc '
       DO j = jts,MIN(jte,jde-1)
       DO k = kts,kte-1
       DO i = its,MIN(ite,ide-1)
         scalar(i,k,j,im) = scalar(i,k,j,im) - dt*qc_diabatic(i,k,j)
       ENDDO
       ENDDO
       ENDDO
     ENDIF

   END DO scalar_loop

END SUBROUTINE q_diabatic_subtr


!-------------------------------------------------------------------------------

SUBROUTINE rk_update_scalar( scs, sce,                      &
                             scalar_1, scalar_2, sc_tend,   &
                             advh_t, advz_t,                &
                             advect_tend,                   &
                             h_tendency, z_tendency,        &
                             msftx, msfty, c1, c2,          &
                             mu_old, mu_new, mu_base,       &
                             rk_step, dt, spec_zone,        &
                             config_flags,                  &
                             tenddec,                      &
                             ids, ide, jds, jde, kds, kde,  &
                             ims, ime, jms, jme, kms, kme,  &
                             its, ite, jts, jte, kts, kte  )

   IMPLICIT NONE

   !  Input data.

   TYPE(grid_config_rec_type   ) ,   INTENT(IN   ) :: config_flags

   LOGICAL ,                INTENT(IN   ) :: tenddec

   INTEGER ,                INTENT(IN   ) :: scs, sce, rk_step, spec_zone
   INTEGER ,                INTENT(IN   ) :: ids, ide, jds, jde, kds, kde, &
                                             ims, ime, jms, jme, kms, kme, &
                                             its, ite, jts, jte, kts, kte

   REAL,                    INTENT(IN   ) :: dt

   REAL, DIMENSION(ims:ime, kms:kme, jms:jme , scs:sce),                &
         INTENT(INOUT)                                  :: scalar_1,    &
                                                           scalar_2

   REAL, DIMENSION(ims:ime, kms:kme, jms:jme , scs:sce),                &
         INTENT(IN)                                     :: sc_tend

   REAL, DIMENSION(ims:ime, kms:kme, jms:jme ),                &
         INTENT(IN)                                  :: advect_tend

   REAL, DIMENSION(ims:ime, kms:kme, jms:jme ), INTENT(INOUT) , OPTIONAL :: advh_t,  advz_t ! accumulating for output
   REAL, DIMENSION(ims:ime, kms:kme, jms:jme ), INTENT(IN   ) :: h_tendency, z_tendency ! from rk_scalar_tend

   REAL, DIMENSION(ims:ime, jms:jme  ), INTENT(IN   ) ::  mu_old,  &
                                                          mu_new,  &
                                                          mu_base, &
                                                          msftx,   &
                                                          msfty

   REAL, DIMENSION(kms:kme ), INTENT(IN   ) ::  c1, c2

   INTEGER :: i,j,k,im
   REAL    :: sc_middle, msfsq
   REAL, DIMENSION(its:ite) :: muold, munew

   REAL, DIMENSION(its:ite, kts:kte, jts:jte  ) :: tendency

   INTEGER :: i_start,i_end,j_start,j_end,k_start,k_end
   INTEGER :: i_start_spc,i_end_spc,j_start_spc,j_end_spc,k_start_spc,k_end_spc

!<DESCRIPTION>
!
!  rk_scalar_update advances the scalar equation given the time t value
!  of the scalar and the scalar tendency.  
!
!</DESCRIPTION>


!
!  set loop limits.

      i_start = its
      i_end   = min(ite,ide-1)
      j_start = jts
      j_end   = min(jte,jde-1)
      k_start = kts
      k_end   = kte-1

      i_start_spc = i_start
      i_end_spc   = i_end
      j_start_spc = j_start
      j_end_spc   = j_end
      k_start_spc = k_start
      k_end_spc   = k_end

    IF( config_flags%nested .or. config_flags%specified ) THEN
      IF( .NOT. config_flags%periodic_x)i_start = max( its,ids+spec_zone )
      IF( .NOT. config_flags%periodic_x)i_end   = min( ite,ide-spec_zone-1 )
      j_start = max( jts,jds+spec_zone )
      j_end   = min( jte,jde-spec_zone-1 )
      k_start = kts
      k_end   = min( kte, kde-1 )
    ENDIF

    IF ( rk_step == 1 ) THEN

      !  replace t-dt values (in scalar_1) with t values scalar_2,
      !  then compute new values by adding tendency to values at t

      DO  im = scs,sce

       DO  j = jts, min(jte,jde-1)
       DO  k = kts, min(kte,kde-1)
       DO  i = its, min(ite,ide-1)
           tendency(i,k,j) = 0.
       ENDDO
       ENDDO
       ENDDO
   
       DO  j = j_start,j_end
       DO  k = k_start,k_end
       DO  i = i_start,i_end
          ! scalar was coupled with my
           tendency(i,k,j) = advect_tend(i,k,j) * msfty(i,j)
       ENDDO
       ENDDO
       ENDDO
   
       DO  j = j_start_spc,j_end_spc
       DO  k = k_start_spc,k_end_spc
       DO  i = i_start_spc,i_end_spc
           tendency(i,k,j) = tendency(i,k,j) + sc_tend(i,k,j,im)
       ENDDO
       ENDDO
       ENDDO
   
      DO  j = jts, min(jte,jde-1)

      DO  i = its, min(ite,ide-1)
        MUOLD(i) = MU_OLD(i,j) + MU_BASE(i,j)
        MUNEW(i) = MU_NEW(i,j) + MU_BASE(i,j)
      ENDDO

      DO  k = kts, min(kte,kde-1)
      DO  i = its, min(ite,ide-1)

        scalar_1(i,k,j,im) = scalar_2(i,k,j,im)
        scalar_2(i,k,j,im) = ((c1(k)*muold(i)+c2(k))*scalar_1(i,k,j,im)   &
                             + dt*tendency(i,k,j))/(c1(k)*munew(i)+c2(k))

      ENDDO
      ENDDO
      ENDDO

      ENDDO

    ELSE

      !  just compute new values, scalar_1 already at time t.

      DO  im = scs, sce

       DO  j = jts, min(jte,jde-1)
       DO  k = kts, min(kte,kde-1)
       DO  i = its, min(ite,ide-1)
           tendency(i,k,j) = 0.
       ENDDO
       ENDDO
       ENDDO
   
       DO  j = j_start,j_end
       DO  k = k_start,k_end
       DO  i = i_start,i_end
           ! scalar was coupled with my
           tendency(i,k,j) = advect_tend(i,k,j) * msfty(i,j)
       ENDDO
       ENDDO
       ENDDO
   
       DO  j = j_start_spc,j_end_spc
       DO  k = k_start_spc,k_end_spc
       DO  i = i_start_spc,i_end_spc
           tendency(i,k,j) = tendency(i,k,j) + sc_tend(i,k,j,im)
       ENDDO
       ENDDO
       ENDDO

      DO  j = jts, min(jte,jde-1)

      DO  i = its, min(ite,ide-1)
        MUOLD(i) = MU_OLD(i,j) + MU_BASE(i,j)
        MUNEW(i) = MU_NEW(i,j) + MU_BASE(i,j)
      ENDDO

      DO  k = kts, min(kte,kde-1)
      DO  i = its, min(ite,ide-1)

        scalar_2(i,k,j,im) = ((c1(k)*muold(i)+c2(k))*scalar_1(i,k,j,im)   &
                             + dt*tendency(i,k,j))/(c1(k)*munew(i)+c2(k))

      ENDDO
      ENDDO

      ! This is separated from the k/i-loop above for better performance
      IF ( PRESENT(advh_t) .AND. PRESENT(advz_t) ) THEN
        IF(tenddec.and.rk_step.eq.config_flags%rk_ord) THEN
          DO  k = kts, min(kte,kde-1)
          DO  i = its, min(ite,ide-1)

            advh_t(i,k,j) = advh_t(i,k,j) + (dt*h_tendency(i,k,j)* msfty(i,j))/(c1(k)*munew(i)+c2(k))
            advz_t(i,k,j) = advz_t(i,k,j) + (dt*z_tendency(i,k,j)* msfty(i,j))/(c1(k)*munew(i)+c2(k))

          ENDDO
          ENDDO
        END IF
      END IF
      
      ENDDO

      ENDDO

    END IF

END SUBROUTINE rk_update_scalar

!-------------------------------------------------------------------------------

SUBROUTINE rk_update_scalar_pd( scs, sce,                      &
                                scalar, sc_tend,               &
                                c1, c2,                        &
                                mu_old, mu_new, mu_base,       &
                                rk_step, dt, spec_zone,        &
                                config_flags,                  &
                                ids, ide, jds, jde, kds, kde,  &
                                ims, ime, jms, jme, kms, kme,  &
                                its, ite, jts, jte, kts, kte  )

   IMPLICIT NONE

   !  Input data.

   TYPE(grid_config_rec_type   ) ,   INTENT(IN   ) :: config_flags

   INTEGER ,                INTENT(IN   ) :: scs, sce, rk_step, spec_zone
   INTEGER ,                INTENT(IN   ) :: ids, ide, jds, jde, kds, kde, &
                                             ims, ime, jms, jme, kms, kme, &
                                             its, ite, jts, jte, kts, kte

   REAL,                    INTENT(IN   ) :: dt

   REAL, DIMENSION(ims:ime, kms:kme, jms:jme , scs:sce),                &
         INTENT(INOUT)                                  :: scalar,      &
                                                           sc_tend

   REAL, DIMENSION(ims:ime, jms:jme  ), INTENT(IN   ) ::  mu_old,  &
                                                          mu_new,  &
                                                          mu_base

   REAL, DIMENSION(kms:kme ), INTENT(IN   ) ::  c1, c2

   INTEGER :: i,j,k,im
   REAL    :: sc_middle, msfsq
   REAL, DIMENSION(its:ite) :: muold, munew

   REAL, DIMENSION(its:ite, kts:kte, jts:jte  ) :: tendency

   INTEGER :: i_start,i_end,j_start,j_end,k_start,k_end
   INTEGER :: i_start_spc,i_end_spc,j_start_spc,j_end_spc,k_start_spc,k_end_spc

!<DESCRIPTION>
!
!  rk_scalar_update advances the scalar equation given the time t value
!  of the scalar and the scalar tendency.  
!
!</DESCRIPTION>


!
!  set loop limits.

      i_start = its
      i_end   = min(ite,ide-1)
      j_start = jts
      j_end   = min(jte,jde-1)
      k_start = kts
      k_end   = kte-1

      i_start_spc = i_start
      i_end_spc   = i_end
      j_start_spc = j_start
      j_end_spc   = j_end
      k_start_spc = k_start
      k_end_spc   = k_end

    IF( config_flags%nested .or. config_flags%specified ) THEN
      IF( .NOT. config_flags%periodic_x)i_start = max( its,ids+spec_zone )
      IF( .NOT. config_flags%periodic_x)i_end   = min( ite,ide-spec_zone-1 )
      j_start = max( jts,jds+spec_zone )
      j_end   = min( jte,jde-spec_zone-1 )
      k_start = kts
      k_end   = min( kte, kde-1 )
    ENDIF

      DO  im = scs, sce

       DO  j = jts, min(jte,jde-1)
       DO  k = kts, min(kte,kde-1)
       DO  i = its, min(ite,ide-1)
           tendency(i,k,j) = 0.
       ENDDO
       ENDDO
       ENDDO
   
       DO  j = j_start_spc,j_end_spc
       DO  k = k_start_spc,k_end_spc
       DO  i = i_start_spc,i_end_spc
           tendency(i,k,j) = tendency(i,k,j) + sc_tend(i,k,j,im)
           sc_tend(i,k,j,im) = 0.
       ENDDO
       ENDDO
       ENDDO

      DO  j = jts, min(jte,jde-1)

      DO  i = its, min(ite,ide-1)
        MUOLD(i) = MU_OLD(i,j) + MU_BASE(i,j)
        MUNEW(i) = MU_NEW(i,j) + MU_BASE(i,j)
      ENDDO

      DO  k = kts, min(kte,kde-1)
      DO  i = its, min(ite,ide-1)

        scalar(i,k,j,im) = ((c1(k)*muold(i)+c2(k))*scalar(i,k,j,im)   &
                             + dt*tendency(i,k,j))/(c1(k)*munew(i)+c2(k))
      ENDDO
      ENDDO
      ENDDO

      ENDDO

END SUBROUTINE rk_update_scalar_pd

!------------------------------------------------------------

SUBROUTINE init_zero_tendency(ru_tendf, rv_tendf, rw_tendf, ph_tendf,  &
                              t_tendf,  tke_tendf, mu_tendf,           &
                              moist_tendf,chem_tendf,scalar_tendf,     &
                              tracer_tendf,n_tracer,                   &
                              n_moist,n_chem,n_scalar,rk_step,         &
                              ids, ide, jds, jde, kds, kde,            &
                              ims, ime, jms, jme, kms, kme,            &
                              its, ite, jts, jte, kts, kte             )
!-----------------------------------------------------------------------
   IMPLICIT NONE
!-----------------------------------------------------------------------

   INTEGER ,       INTENT(IN   ) :: ids, ide, jds, jde, kds, kde, &
                                    ims, ime, jms, jme, kms, kme, &
                                    its, ite, jts, jte, kts, kte

   INTEGER ,       INTENT(IN   ) :: n_moist,n_chem,n_scalar,n_tracer,rk_step

   REAL , DIMENSION( ims:ime , kms:kme, jms:jme  ) , INTENT(INOUT) ::  &
                                                             ru_tendf, &
                                                             rv_tendf, &
                                                             rw_tendf, &
                                                             ph_tendf, &
                                                              t_tendf, &
                                                            tke_tendf

   REAL , DIMENSION( ims:ime , jms:jme  ) , INTENT(INOUT) ::  mu_tendf

   REAL , DIMENSION(ims:ime, kms:kme, jms:jme, n_moist),INTENT(INOUT)::&
                                                          moist_tendf

   REAL , DIMENSION(ims:ime, kms:kme, jms:jme, n_chem ),INTENT(INOUT)::&
                                                          chem_tendf
   REAL , DIMENSION(ims:ime, kms:kme, jms:jme, n_tracer ),INTENT(INOUT)::&
                                                          tracer_tendf

   REAL , DIMENSION(ims:ime, kms:kme, jms:jme, n_scalar ),INTENT(INOUT)::&
                                                          scalar_tendf

! LOCAL VARS

   INTEGER :: im, ic, is

!<DESCRIPTION>
!
! init_zero_tendency
! sets tendency arrays to zero for all prognostic variables.
!
!</DESCRIPTION>


   CALL zero_tend ( ru_tendf,                        &
                    ids, ide, jds, jde, kds, kde,    &
                    ims, ime, jms, jme, kms, kme,    &
                    its, ite, jts, jte, kts, kte     )

   CALL zero_tend ( rv_tendf,                        &
                    ids, ide, jds, jde, kds, kde,    &
                    ims, ime, jms, jme, kms, kme,    &
                    its, ite, jts, jte, kts, kte     )

   CALL zero_tend ( rw_tendf,                        &
                    ids, ide, jds, jde, kds, kde,    &
                    ims, ime, jms, jme, kms, kme,    &
                    its, ite, jts, jte, kts, kte     )

   CALL zero_tend ( ph_tendf,                        &
                    ids, ide, jds, jde, kds, kde,    &
                    ims, ime, jms, jme, kms, kme,    &
                    its, ite, jts, jte, kts, kte     )

   CALL zero_tend ( t_tendf,                         &
                    ids, ide, jds, jde, kds, kde,    &
                    ims, ime, jms, jme, kms, kme,    &
                    its, ite, jts, jte, kts, kte     )

   CALL zero_tend ( tke_tendf,                       &
                    ids, ide, jds, jde, kds, kde,    &
                    ims, ime, jms, jme, kms, kme,    &
                    its, ite, jts, jte, kts, kte     )

   CALL zero_tend2d( mu_tendf,                        &
                    ids, ide, jds, jde, kds, kds,    &
                    ims, ime, jms, jme, kms, kms,    &
                    its, ite, jts, jte, kts, kts     )

!   DO im=PARAM_FIRST_SCALAR,n_moist
   DO im=1,n_moist                      ! make sure first one is zero too
      CALL zero_tend ( moist_tendf(ims,kms,jms,im),  &
                       ids, ide, jds, jde, kds, kde, &
                       ims, ime, jms, jme, kms, kme, &
                       its, ite, jts, jte, kts, kte  )
   ENDDO

!   DO ic=PARAM_FIRST_SCALAR,n_chem
   DO ic=1,n_chem                       ! make sure first one is zero too
      CALL zero_tend ( chem_tendf(ims,kms,jms,ic),   &
                       ids, ide, jds, jde, kds, kde, &
                       ims, ime, jms, jme, kms, kme, &
                       its, ite, jts, jte, kts, kte  )
   ENDDO

!   DO ic=PARAM_FIRST_SCALAR,n_tracer
   DO ic=1,n_tracer                     ! make sure first one is zero too
      CALL zero_tend ( tracer_tendf(ims,kms,jms,ic), &
                       ids, ide, jds, jde, kds, kde, &
                       ims, ime, jms, jme, kms, kme, &
                       its, ite, jts, jte, kts, kte  )
   ENDDO

!   DO ic=PARAM_FIRST_SCALAR,n_scalar
   DO ic=1,n_scalar                       ! make sure first one is zero too
      CALL zero_tend ( scalar_tendf(ims,kms,jms,ic),   &
                       ids, ide, jds, jde, kds, kde, &
                       ims, ime, jms, jme, kms, kme, &
                       its, ite, jts, jte, kts, kte  )
   ENDDO

END SUBROUTINE init_zero_tendency

!===================================================================


SUBROUTINE dump_data( a, field, io_unit,            &
                      ims, ime, jms, jme, kms, kme, &
                      ids, ide, jds, jde, kds, kde )
implicit none
integer ::  ims, ime, jms, jme, kms, kme, &
            ids, ide, jds, jde, kds, kde
real, dimension(ims:ime, kms:kme, jds:jde) :: a
character :: field
integer :: io_unit

integer :: is,ie,js,je,ks,ke

!<DESCRIPTION
!
! quick and dirty debug io utility
!
!</DESCRIPTION

is = ids
ie = ide-1
js = jds
je = jde-1
ks = kds
ke = kde-1

if(field == 'u') ie = ide
if(field == 'v') je = jde
if(field == 'w') ke = kde

write(io_unit) is,ie,ks,ke,js,je
write(io_unit) a(is:ie, ks:ke, js:je)

end subroutine dump_data

!-----------------------------------------------------------------------

SUBROUTINE calculate_phy_tend (config_flags,c1,c2,                     &
                     mut,muu,muv,pi3d,                                 &
                     RTHRATEN,                                         &
                     RUBLTEN,RVBLTEN,RTHBLTEN,                         &
                     RQVBLTEN,RQCBLTEN,RQIBLTEN,                       &
                     RUCUTEN,RVCUTEN,RTHCUTEN,                         &
                     RQVCUTEN,RQCCUTEN,RQRCUTEN,                       &
                     RQICUTEN,RQSCUTEN,                                &
                     RUSHTEN,RVSHTEN,RTHSHTEN,                         &
                     RQVSHTEN,RQCSHTEN,RQRSHTEN,                       &
                     RQISHTEN,RQSSHTEN,RQGSHTEN,                       &
                     RUNDGDTEN,RVNDGDTEN,RTHNDGDTEN,RQVNDGDTEN,        &
                     RMUNDGDTEN,                                       &
                     scalar, scalar_tend, num_scalar,                  &
                     tracer, tracer_tend, num_tracer,                  &
                     ids,ide, jds,jde, kds,kde,                        &
                     ims,ime, jms,jme, kms,kme,                        &
                     its,ite, jts,jte, kts,kte                         )
!-----------------------------------------------------------------------
      IMPLICIT NONE

      TYPE(grid_config_rec_type), INTENT(IN)     ::      config_flags

      INTEGER,  INTENT(IN   )   ::          num_scalar, num_tracer
      INTEGER,  INTENT(IN   )   ::          ids,ide, jds,jde, kds,kde, &
                                            ims,ime, jms,jme, kms,kme, &
                                            its,ite, jts,jte, kts,kte

      REAL,     DIMENSION( ims:ime, kms:kme, jms:jme )               , &
                INTENT(IN   )   ::                               pi3d

      REAL,     DIMENSION( kms:kme )                                 , &
                INTENT(IN   )   ::                               c1, c2
                                                                 
      REAL,     DIMENSION( ims:ime, jms:jme )                        , &
                INTENT(IN   )   ::                                mut, &
                                                                  muu, &
                                                                  muv
      
                                                           
! radiation

      REAL,     DIMENSION( ims:ime, kms:kme, jms:jme ),                &
                INTENT(INOUT)   ::                           RTHRATEN

! cumulus

      REAL,     DIMENSION( ims:ime , kms:kme , jms:jme ),              &
                INTENT(INOUT)   ::                                     &
                                                              RUCUTEN, &
                                                              RVCUTEN, &
                                                             RTHCUTEN, &
                                                             RQVCUTEN, &
                                                             RQCCUTEN, &
                                                             RQRCUTEN, &
                                                             RQICUTEN, &
                                                             RQSCUTEN, &
                                                              RUSHTEN, &
                                                              RVSHTEN, &
                                                             RTHSHTEN, &
                                                             RQVSHTEN, &
                                                             RQCSHTEN, &
                                                             RQRSHTEN, &
                                                             RQISHTEN, &
                                                             RQSSHTEN, &
                                                             RQGSHTEN

! pbl

      REAL,     DIMENSION( ims:ime, kms:kme, jms:jme )               , &
                INTENT(INOUT)   ::                            RUBLTEN, &
                                                              RVBLTEN, &
                                                             RTHBLTEN, &
                                                             RQVBLTEN, &
                                                             RQCBLTEN, &
                                                             RQIBLTEN

! fdda

      REAL,     DIMENSION( ims:ime, kms:kme, jms:jme )               , &
                INTENT(INOUT)   ::                            RUNDGDTEN, &
                                                              RVNDGDTEN, &
                                                             RTHNDGDTEN, &
                                                             RQVNDGDTEN
      REAL,     DIMENSION( ims:ime, jms:jme )               , &
                INTENT(INOUT)   ::                           RMUNDGDTEN

! 4d arrays

    REAL    ,DIMENSION(ims:ime,kms:kme,jms:jme,num_tracer),INTENT(INOUT)   :: tracer
    REAL    ,DIMENSION(ims:ime,kms:kme,jms:jme,num_tracer),INTENT(INOUT)   :: tracer_tend
    REAL    ,DIMENSION(ims:ime,kms:kme,jms:jme,num_scalar),INTENT(INOUT)   :: scalar
    REAL    ,DIMENSION(ims:ime,kms:kme,jms:jme,num_scalar),INTENT(INOUT)   :: scalar_tend

      INTEGER :: i,k,j, im
      INTEGER :: itf,ktf,jtf,itsu,jtsv

!-----------------------------------------------------------------------

!<DESCRIPTION>
!
!  calculate_phy_tend couples the physics tendencies to the column mass (mu),
!  because prognostic equations are in flux form, but physics tendencies are
!  computed for uncoupled variables.
!
!</DESCRIPTION>

      itf=MIN(ite,ide-1)
      jtf=MIN(jte,jde-1)
      ktf=MIN(kte,kde-1)
      itsu=MAX(its,ids+1)
      jtsv=MAX(jts,jds+1)

! radiation

   IF (config_flags%ra_lw_physics .gt. 0 .or. config_flags%ra_sw_physics .gt. 0) THEN

      DO J=jts,jtf
      DO K=kts,ktf
      DO I=its,itf
         RTHRATEN(I,K,J)=(c1(k)*mut(I,J)+c2(k))*RTHRATEN(I,K,J)
      ENDDO
      ENDDO
      ENDDO

   ENDIF

! cumulus

   IF (config_flags%cu_physics .gt. 0) THEN

      DO J=jts,jtf
      DO K=kts,ktf
      DO I=its,itf
         RUCUTEN(I,K,J) =(c1(k)*mut(I,J)+c2(k))*RUCUTEN(I,K,J)
         RVCUTEN(I,K,J) =(c1(k)*mut(I,J)+c2(k))*RVCUTEN(I,K,J)
         RTHCUTEN(I,K,J)=(c1(k)*mut(I,J)+c2(k))*RTHCUTEN(I,K,J)
         RQVCUTEN(I,K,J)=(c1(k)*mut(I,J)+c2(k))*RQVCUTEN(I,K,J)
      ENDDO
      ENDDO
      ENDDO

      IF (P_QC .ge. PARAM_FIRST_SCALAR)THEN
         DO J=jts,jtf
         DO K=kts,ktf
         DO I=its,itf
            RQCCUTEN(I,K,J)=(c1(k)*mut(I,J)+c2(k))*RQCCUTEN(I,K,J)
         ENDDO
         ENDDO
         ENDDO
      ENDIF

      IF (P_QR .ge. PARAM_FIRST_SCALAR)THEN
         DO J=jts,jtf
         DO K=kts,ktf
         DO I=its,itf
            RQRCUTEN(I,K,J)=(c1(k)*mut(I,J)+c2(k))*RQRCUTEN(I,K,J)
         ENDDO
         ENDDO
         ENDDO
      ENDIF

      IF (P_QI .ge. PARAM_FIRST_SCALAR)THEN
         DO J=jts,jtf
         DO K=kts,ktf
         DO I=its,itf
            RQICUTEN(I,K,J)=(c1(k)*mut(I,J)+c2(k))*RQICUTEN(I,K,J)
         ENDDO
         ENDDO
         ENDDO
      ENDIF

      IF(P_QS .ge. PARAM_FIRST_SCALAR)THEN
         DO J=jts,jtf
         DO K=kts,ktf
         DO I=its,itf
            RQSCUTEN(I,K,J)=(c1(k)*mut(I,J)+c2(k))*RQSCUTEN(I,K,J)
         ENDDO
         ENDDO
         ENDDO
      ENDIF

   ENDIF

! shallow cumulus

   IF (config_flags%shcu_physics .gt. 0) THEN

      DO J=jts,jtf
      DO K=kts,ktf
      DO I=its,itf
         RUSHTEN(I,K,J) =(c1(k)*mut(I,J)+c2(k))*RUSHTEN(I,K,J)
         RVSHTEN(I,K,J) =(c1(k)*mut(I,J)+c2(k))*RVSHTEN(I,K,J)
         RTHSHTEN(I,K,J)=(c1(k)*mut(I,J)+c2(k))*RTHSHTEN(I,K,J)
         RQVSHTEN(I,K,J)=(c1(k)*mut(I,J)+c2(k))*RQVSHTEN(I,K,J)
      ENDDO
      ENDDO
      ENDDO

      IF (P_QC .ge. PARAM_FIRST_SCALAR)THEN
         DO J=jts,jtf
         DO K=kts,ktf
         DO I=its,itf
            RQCSHTEN(I,K,J)=(c1(k)*mut(I,J)+c2(k))*RQCSHTEN(I,K,J)
         ENDDO
         ENDDO
         ENDDO
      ENDIF

      IF (P_QR .ge. PARAM_FIRST_SCALAR)THEN
         DO J=jts,jtf
         DO K=kts,ktf
         DO I=its,itf
            RQRSHTEN(I,K,J)=(c1(k)*mut(I,J)+c2(k))*RQRSHTEN(I,K,J)
         ENDDO
         ENDDO
         ENDDO
      ENDIF

      IF (P_QI .ge. PARAM_FIRST_SCALAR)THEN
         DO J=jts,jtf
         DO K=kts,ktf
         DO I=its,itf
            RQISHTEN(I,K,J)=(c1(k)*mut(I,J)+c2(k))*RQISHTEN(I,K,J)
         ENDDO
         ENDDO
         ENDDO
      ENDIF

      IF(P_QS .ge. PARAM_FIRST_SCALAR)THEN
         DO J=jts,jtf
         DO K=kts,ktf
         DO I=its,itf
            RQSSHTEN(I,K,J)=(c1(k)*mut(I,J)+c2(k))*RQSSHTEN(I,K,J)
         ENDDO
         ENDDO
         ENDDO
      ENDIF

      IF(P_QG .ge. PARAM_FIRST_SCALAR)THEN
         DO J=jts,jtf
         DO K=kts,ktf
         DO I=its,itf
            RQGSHTEN(I,K,J)=(c1(k)*mut(I,J)+c2(k))*RQGSHTEN(I,K,J)
         ENDDO
         ENDDO
         ENDDO
      ENDIF

   ENDIF

! pbl

   IF (config_flags%bl_pbl_physics .gt. 0) THEN

      DO J=jts,jtf
      DO K=kts,ktf
      DO I=its,itf
         RUBLTEN(I,K,J) =(c1(k)*mut(I,J)+c2(k))*RUBLTEN(I,K,J)
         RVBLTEN(I,K,J) =(c1(k)*mut(I,J)+c2(k))*RVBLTEN(I,K,J)
         RTHBLTEN(I,K,J)=(c1(k)*mut(I,J)+c2(k))*RTHBLTEN(I,K,J)
      ENDDO
      ENDDO
      ENDDO

      IF (P_QV .ge. PARAM_FIRST_SCALAR) THEN
         DO J=jts,jtf
         DO K=kts,ktf
         DO I=its,itf
            RQVBLTEN(I,K,J)=(c1(k)*mut(I,J)+c2(k))*RQVBLTEN(I,K,J)
         ENDDO
         ENDDO
         ENDDO
      ENDIF

      IF (P_QC .ge. PARAM_FIRST_SCALAR) THEN
         DO J=jts,jtf
         DO K=kts,ktf
         DO I=its,itf
           RQCBLTEN(I,K,J)=(c1(k)*mut(I,J)+c2(k))*RQCBLTEN(I,K,J)
         ENDDO
         ENDDO
         ENDDO
      ENDIF

      IF (P_QI .ge. PARAM_FIRST_SCALAR) THEN
         DO J=jts,jtf
         DO K=kts,ktf
         DO I=its,itf
            RQIBLTEN(I,K,J)=(c1(k)*mut(I,J)+c2(k))*RQIBLTEN(I,K,J)
         ENDDO
         ENDDO
         ENDDO
      ENDIF

    ENDIF

! fdda
! note fdda u and v tendencies are staggered, also only interior points have muu/muv,
!   so only couple those

   IF (config_flags%grid_fdda .gt. 0) THEN

      DO J=jts,jtf
      DO K=kts,ktf
      DO I=itsu,itf
!     if( i == itf/2 .AND. j == jtf/2 .AND. k == ktf/2 ) &
!     write(*,'(a,3i6,e15.5)') 'u_ten before=',i,k,j, RUNDGDTEN(i,k,j)
         RUNDGDTEN(I,K,J) =(c1(k)*muu(I,J)+c2(k))*RUNDGDTEN(I,K,J)
!        if( i == itf/2 .AND. j == jtf/2 .AND. k==ktf/2 ) &
!          write(*,'(a,2f15.5)') 'mu, muu=',(c1(k)*mut(I,J)+c2(k)), (c1(k)*muu(i,j)+c2(k))
!     if( i == itf/2 .AND. j == jtf/2 .AND. k == ktf/2 ) &
!     write(*,'(a,3i6,e15.5)') 'u_ten after=',i,k,j, RUNDGDTEN(i,k,j)
!     if( RUNDGDTEN(i,k,j) > 30.0 ) write(*,*) 'IKJ=',i,k,j
      ENDDO
      ENDDO
      ENDDO
!     write(*,'(a,e15.5)') 'u_ten MAXIMUM after=', maxval(RUNDGDTEN)
      DO J=jtsv,jtf
      DO K=kts,ktf
      DO I=its,itf
         RVNDGDTEN(I,K,J) =(c1(k)*muv(I,J)+c2(k))*RVNDGDTEN(I,K,J)
      ENDDO
      ENDDO
      ENDDO
      DO J=jts,jtf
      DO K=kts,ktf
      DO I=its,itf
!     if( i == itf/2 .AND. j == jtf/2 .AND. k == ktf/2 ) &
!     write(*,'(a,3i6,e15.5)') 'th before=',i,k,j, RTHNDGDTEN(I,K,J)
         RTHNDGDTEN(I,K,J)=(c1(k)*mut(I,J)+c2(k))*RTHNDGDTEN(I,K,J)
!        RMUNDGDTEN(I,J) - no coupling
!     if( i == itf/2 .AND. j == jtf/2 .AND. k == ktf/2 ) &
!     write(*,'(a,3i6,e15.5)') 'th after=',i,k,j, RTHNDGDTEN(I,K,J)
      ENDDO
      ENDDO
      ENDDO

      IF (P_QV .ge. PARAM_FIRST_SCALAR) THEN
         DO J=jts,jtf
         DO K=kts,ktf
         DO I=its,itf
            RQVNDGDTEN(I,K,J)=(c1(k)*mut(I,J)+c2(k))*RQVNDGDTEN(I,K,J)
         ENDDO
         ENDDO
         ENDDO
      ENDIF

    ENDIF

! 4d couple scalar tendencies that have only uncoupled physics tendencies at this point

   DO im = PARAM_FIRST_SCALAR,num_scalar
         DO J=jts,jtf
         DO K=kts,ktf
         DO I=its,itf
            scalar_tend(I,K,J,im)=(c1(k)*mut(I,J)+c2(k))*scalar_tend(I,K,J,im)
         ENDDO
         ENDDO
         ENDDO
   ENDDO

   DO im = PARAM_FIRST_SCALAR,num_tracer
         DO J=jts,jtf
         DO K=kts,ktf
         DO I=its,itf
            tracer_tend(I,K,J,im)=(c1(k)*mut(I,J)+c2(k))*tracer_tend(I,K,J,im)
         ENDDO
         ENDDO
         ENDDO
   ENDDO


END SUBROUTINE calculate_phy_tend

!-----------------------------------------------------------------------

SUBROUTINE positive_definite_filter ( a,                          &
                                      ids,ide, jds,jde, kds,kde,  &
                                      ims,ime, jms,jme, kms,kme,  &
                                      its,ite, jts,jte, kts,kte  )

  IMPLICIT NONE

  INTEGER,  INTENT(IN   )   ::          ids,ide, jds,jde, kds,kde, &
                                        ims,ime, jms,jme, kms,kme, &
                                        its,ite, jts,jte, kts,kte

  REAL, DIMENSION( ims:ime , kms:kme , jms:jme  ), INTENT(INOUT) :: a

  INTEGER :: i,k,j

!<DESCRIPTION>
!
! debug and testing code for bounding a variable
!
!</DESCRIPTION>

  DO j=jts,min(jte,jde-1)
  DO k=kts,kte-1
  DO i=its,min(ite,ide-1)
!    a(i,k,j) = max(a(i,k,j),0.)
    a(i,k,j) = min(1000.,max(a(i,k,j),0.))
  ENDDO
  ENDDO
  ENDDO

  END SUBROUTINE positive_definite_filter

!-----------------------------------------------------------------------

SUBROUTINE bound_tke ( tke, tke_upper_bound,       &
                       ids,ide, jds,jde, kds,kde,  &
                       ims,ime, jms,jme, kms,kme,  &
                       its,ite, jts,jte, kts,kte  )

  IMPLICIT NONE

  INTEGER,  INTENT(IN   )   ::          ids,ide, jds,jde, kds,kde, &
                                        ims,ime, jms,jme, kms,kme, &
                                        its,ite, jts,jte, kts,kte

  REAL, DIMENSION( ims:ime , kms:kme , jms:jme  ), INTENT(INOUT) :: tke
  REAL, INTENT(   IN) :: tke_upper_bound

  INTEGER :: i,k,j

!<DESCRIPTION>
!
! bounds tke between zero and tke_upper_bound.
!
!</DESCRIPTION>

  DO j=jts,min(jte,jde-1)
  DO k=kts,kte-1
  DO i=its,min(ite,ide-1)
    tke(i,k,j) = min(tke_upper_bound,max(tke(i,k,j),0.))
  ENDDO
  ENDDO
  ENDDO

  END SUBROUTINE bound_tke

!-----------------------------------------------------------------------

SUBROUTINE bound_qna ( qna,                        &
                       ids,ide, jds,jde, kds,kde,  &
                       ims,ime, jms,jme, kms,kme,  &
                       its,ite, jts,jte, kts,kte  )

  IMPLICIT NONE

  INTEGER,  INTENT(IN   )   ::          ids,ide, jds,jde, kds,kde, &
                                        ims,ime, jms,jme, kms,kme, &
                                        its,ite, jts,jte, kts,kte

  REAL, DIMENSION( ims:ime , kms:kme , jms:jme  ), INTENT(INOUT) :: qna

  INTEGER :: i,k,j

!<DESCRIPTION>
!
! bounds aerosol between zero and current value
!
!</DESCRIPTION>

  DO j=jts,min(jte,jde-1)
  DO k=kts,kte-1
  DO i=its,min(ite,ide-1)
    qna(i,k,j) = max(qna(i,k,j),0.)
  ENDDO
  ENDDO
  ENDDO

  END SUBROUTINE bound_qna

!----------------------------------------------------------------------------------
!cyl: Implement the forward Lagrangian trajectory calculation in WRF
!Chiaying Lee RSMAS/UM
!----------------------------------------------------------------------------------
subroutine trajectory (     grid,config_flags,               &
                            dt,itimestep,ru_m, rv_m, ww_m,   &
                            mut,muu,muv,c1h,c2h,c1f,c2f,     &
                            rdx, rdy, rdn, rdnw,rdzw,        &
                            traj_i,traj_j,traj_k,            &
                            traj_long,traj_lat,              &
                            xlong,xlat,                      &
                            msft,msfu,msfv,                  &
                            ids, ide, jds, jde, kds, kde,    &
                            ims, ime, jms, jme, kms, kme,    &
                            its, ite, jts, jte, kts, kte    )

!---------------------------------------------------------------------------------------------------

  use module_date_time
  use module_utility
  use module_domain, only  : domain_clock_get
  use module_trajectory, only  : traject, traj_cnt

  implicit none
!---------------------------------------------------------------------------------------------------
! Subroutine trajectory calculates forward Lagrangian trajectory  
! of the selecting points. The trajectory of each point is subjected to u, v, and w.
! (Lee and Chen 2013, MWR).     
!
! The trajectories is initialized with given longitude (degree), latitude (degree), and height(eta level).
!
!--traj_i grid number in x direction (on mass grid), float
!--traj_j grid number in y direction (on mass grid), float
!--traj_k grid number in z direction (on mass grid), float
!--traj_long longitude of trajectories, float
!--traj_lat longitude of trajectories, float
!
!--------------------------------------------------------------------------------------------------
  TYPE(proj_info) :: proj
  TYPE(domain), INTENT(IN) :: grid
  TYPE (grid_config_rec_type) , INTENT(IN)          :: config_flags
  INTEGER ,                INTENT(IN   ) :: ids, ide, jds, jde, kds, kde, &
                                             ims, ime, jms, jme, kms, kme, &
                                             its, ite, jts, jte, kts, kte
   INTEGER ,                                      INTENT(IN   ) :: itimestep
   REAL ,                                      INTENT(IN   ) :: rdx,     &
                                                                rdy,     &
                                                                dt
   REAL , DIMENSION( kms:kme ) ,               INTENT(IN   ) :: rdn,     &
                                                                rdnw

   REAL , DIMENSION( kms:kme ) ,               INTENT(IN   ) :: c1h, c2h, c1f, c2f

   REAL , DIMENSION( ims:ime , kms:kme, jms:jme  ) ,              &
                                        INTENT(IN   ) :: ru_m,     &
                                                         rv_m,     &
                                                         ww_m
   REAL , DIMENSION( ims:ime , jms:jme  ) ,              &
                                        INTENT(IN   ) ::xlong, xlat

  real, dimension(1:config_flags%num_traj), intent(inout) :: traj_i,traj_j,traj_k
  real, dimension(1:config_flags%num_traj), intent(inout) :: traj_long,traj_lat
  real, dimension(ims:ime,kms:kme,jms:jme),intent(in) :: rdzw
  real, dimension(ims:ime,kms:kme,jms:jme)::u,v,w
  real, dimension(ims:ime,jms:jme),intent(in)::msft,msfu,msfv
  real, dimension(ims:ime,jms:jme),intent(in)::muu,muv,mut
  integer :: j,k
  integer :: i_beg,i_end
  integer :: i_traj,j_traj,k_traj,tjk
  integer :: dm
  real :: traj_u,traj_v,traj_w
  real :: rdx_grid,rdy_grid,rdz_grid
  real :: deltx, delty, deltz,ax
  real :: const1
  real :: temp_i,temp_j
  integer :: i_u,j_v,k_w
  real :: u_a,u_b,u_c,u_d,v_a,v_b,v_c,v_d,w_a,w_b,w_c,w_d
  real :: d_a,d_b,d_c,d_d
  real :: u_temp_upper,u_temp_lower
  real :: v_temp_upper,v_temp_lower
  real :: w_temp_upper,w_temp_lower
  real :: eta_old, eta_new
  integer :: keta, keta_temp
  character(len=19)  :: current_timestr, next_timestr, wrk_timestr
  character(len=256) :: dbg_mes
  logical :: has_proj_map
! varalbe for map projectory
  real:: known_lat, known_lon
  TYPE (grid_config_rec_type) :: config_flags_temp
  TYPE(WRFU_Time) :: current_time, next_time
  TYPE(WRFU_Time) :: start_time, stop_time

  config_flags_temp = config_flags
  call trajmapproj(grid, config_flags_temp,proj)


! convert ru_m, rv_m and ww_m in u,v,w
   const1=1.0/2.0/sqrt(2.0)

   dm = grid%id

   write(dbg_mes,'(''trajectory('',i2.2,''): Entering trajectory'')') dm
   call wrf_debug(200,trim(dbg_mes) )

   i_beg = max( 1,its-1 )
   i_end = min( ite+2,ide-1 )
   do j=max(1,jts-1),min(jte+2,jde-1)
     do k=kms,kme-1
       u(its:i_end,k,j)=ru_m(its:i_end,k,j)/(c1h(k)*MUU(its:i_end,j)+c2h(k))*msfu(its:i_end,j)
       v(its:i_end,k,j)=rv_m(its:i_end,k,j)/(c1h(k)*MUV(its:i_end,j)+c2h(k))*msfv(its:i_end,j)
     enddo
     do k=kms,kme
       w(its:i_end,k,j)=ww_m(its:i_end,k,j)/(c1f(k)*MUT(its:i_end,j)+c2f(k))*msft(its:i_end,j)
     enddo
   enddo
          has_proj_map  = &
           ( proj%code .EQ. PROJ_LC           ) .OR. &
           ( proj%code .EQ. PROJ_PS_WGS84     ) .OR. &
           ( proj%code .EQ. PROJ_ALBERS_NAD83 ) .OR. &
           ( proj%code .EQ. PROJ_MERC         ) .OR. &
           ( proj%code .EQ. PROJ_LATLON       ) .OR. &
           ( proj%code .EQ. PROJ_CYL          ) .OR. &
           ( proj%code .EQ. PROJ_CASSINI      ) .OR. &
           ( proj%code .EQ. PROJ_GAUSS        ) .OR. &
           ( proj%code .EQ. PROJ_ROTLL        )

traj_loop: &
do tjk = 1,traj_cnt(dm)
!do tjk = 1,config_flags%num_traj
traj_is_active: &
    if (traj_i(tjk) .ne. -9999.0) then
      eta_old = 0.0
      eta_new = 0.0
      keta      = 0
      keta_temp = 0
      if( has_proj_map ) then
        call latlon_to_ij (proj, &
traj_lat(tjk),traj_long(tjk),traj_i(tjk),traj_j(tjk))
      end if

      i_traj = floor(traj_i(tjk)) ! find the lower_left_bottom corner for
!trajectory
      j_traj = floor(traj_j(tjk)) !
      k_traj = floor(traj_k(tjk)) !
traj_in_domain: &
      if ((i_traj .ge. its .and. i_traj .le. ite .and. i_traj .lt. ide) .and. &
          (j_traj .ge. jts .and. j_traj .le. jte .and. j_traj .lt. jde) .and. &
          (k_traj .le. kte .and. k_traj .lt. kde)) then
!-----------------------------------------------------------------------------
!  is trajectory in time interval?
!-----------------------------------------------------------------------------
         call domain_clock_get( grid, current_time=current_time, &
current_timestr=current_timestr)
         call geth_newdate( next_timestr, current_timestr, int(grid%dt) )
         call wrf_atotime( next_timestr, next_time )
         wrk_timestr(1:19) = traject(tjk,dm)%start_time(1:19)
!        write(*,*) ' '
!        write(*,*) traject(tjk,dm)
!        write(dbg_mes,'(''trajectory('',i2,2,''): tjk,start_time = '',i3,1x,a)') &
!                     dm,tjk,wrk_timestr
!        call wrf_debug( 200,trim(dbg_mes) )
         call wrf_atotime( wrk_timestr(1:19), start_time )
         wrk_timestr(1:19) = traject(tjk,dm)%stop_time(1:19)
         call wrf_atotime( wrk_timestr(1:19), stop_time )
is_in_time_interval: &
         if( next_time .ge. start_time .and. next_time .le. stop_time &
                                       .and. .not. traject(tjk,dm)%is_stationary ) then
! for u : check x stagger
        if (traj_i(tjk)-real(floor(traj_i(tjk))) .ge. 0.5 ) then
          i_u=floor(traj_i(tjk)) + 1
        else
          i_u=floor(traj_i(tjk))
        endif
! for layer k_traj
      if (k_traj .ge. 1 ) then
        u_a=u(i_u  ,k_traj,j_traj+1)
        u_b=u(i_u  ,k_traj,j_traj  )
        u_c=u(i_u+1,k_traj,j_traj  )
        u_d=u(i_u+1,k_traj,j_traj+1)
      else
        u_a=0.0
        u_b=0.0
        u_c=0.0
        u_d=0.0
      endif
        d_a=abs((real(i_u+1)-(traj_i(tjk)+0.5))*(real(j_traj  )-traj_j(tjk)))
        d_b=abs((real(i_u+1)-(traj_i(tjk)+0.5))*(real(j_traj+1)-traj_j(tjk)))
        d_c=abs((real(i_u  )-(traj_i(tjk)+0.5))*(real(j_traj+1)-traj_j(tjk)))
        d_d=abs((real(i_u  )-(traj_i(tjk)+0.5))*(real(j_traj  )-traj_j(tjk)))
        u_temp_lower=(u_a*d_a+u_b*d_b+u_c*d_c+u_d*d_d)/(d_a+d_b+d_c+d_d)

!for layer k_traj+1
        u_a=u(i_u  ,k_traj+1,j_traj+1)
        u_b=u(i_u  ,k_traj+1,j_traj  )
        u_c=u(i_u+1,k_traj+1,j_traj  )
        u_d=u(i_u+1,k_traj+1,j_traj+1)
        d_a=abs((real(i_u+1)-(traj_i(tjk)+0.5))*(real(j_traj  )-traj_j(tjk)))
        d_b=abs((real(i_u+1)-(traj_i(tjk)+0.5))*(real(j_traj+1)-traj_j(tjk)))
        d_c=abs((real(i_u  )-(traj_i(tjk)+0.5))*(real(j_traj+1)-traj_j(tjk)))
        d_d=abs((real(i_u  )-(traj_i(tjk)+0.5))*(real(j_traj  )-traj_j(tjk)))
        u_temp_upper=(u_a*d_a+u_b*d_b+u_c*d_c+u_d*d_d)/(d_a+d_b+d_c+d_d)

        traj_u=u_temp_upper*abs(real(k_traj)-traj_k(tjk))+u_temp_lower*abs(real(k_traj+1)-traj_k(tjk))

! for v: check y-stagger
        if (traj_j(tjk)-real(floor(traj_j(tjk))) .ge. 0.5 ) then
          j_v=floor(traj_j(tjk)) + 1
        else
          j_v=floor(traj_j(tjk))
        endif
! for layer k_traj
      if (k_traj .ge. 1 ) then
        v_a=v(i_traj  ,k_traj,j_v+1)
        v_b=v(i_traj  ,k_traj,j_v  )
        v_c=v(i_traj+1,k_traj,j_v  )
        v_d=v(i_traj+1,k_traj,j_v+1)
      else
        v_a=0.0
        v_b=0.0
        v_c=0.0
        v_d=0.0
      endif
        d_a=abs((real(i_traj+1)-traj_i(tjk))*(real(j_v  )-(traj_j(tjk)+0.5)))
        d_b=abs((real(i_traj+1)-traj_i(tjk))*(real(j_v+1)-(traj_j(tjk)+0.5)))
        d_c=abs((real(i_traj  )-traj_i(tjk))*(real(j_v+1)-(traj_j(tjk)+0.5)))
        d_d=abs((real(i_traj  )-traj_i(tjk))*(real(j_v  )-(traj_j(tjk)+0.5)))
        v_temp_lower=(v_a*d_a+v_b*d_b+v_c*d_c+v_d*d_d)/(d_a+d_b+d_c+d_d)
!for layer k_traj+1
        v_a=v(i_traj  ,k_traj+1,j_v+1)
        v_b=v(i_traj  ,k_traj+1,j_v  )
        v_c=v(i_traj+1,k_traj+1,j_v  )
        v_d=v(i_traj+1,k_traj+1,j_v+1)
        d_a=abs((real(i_traj+1)-traj_i(tjk))*(real(j_v  )-(traj_j(tjk)+0.5)))
        d_b=abs((real(i_traj+1)-traj_i(tjk))*(real(j_v+1)-(traj_j(tjk)+0.5)))
        d_c=abs((real(i_traj  )-traj_i(tjk))*(real(j_v+1)-(traj_j(tjk)+0.5)))
        d_d=abs((real(i_traj  )-traj_i(tjk))*(real(j_v  )-(traj_j(tjk)+0.5)))
        v_temp_upper=(v_a*d_a+v_b*d_b+v_c*d_c+v_d*d_d)/(d_a+d_b+d_c+d_d)

        traj_v=v_temp_upper*abs(real(k_traj)-traj_k(tjk))+v_temp_lower*abs(real(k_traj+1)-traj_k(tjk))


!for w: check for z-stagger
        if (traj_k(tjk)-real(floor(traj_k(tjk))) .ge. 0.5 ) then
          k_w=floor(traj_k(tjk)) + 1
        else
          k_w=floor(traj_k(tjk))
        endif
!for layer j_traj
        if (k_w .ge. 1) then
          w_b=w(i_traj  ,k_w  ,j_traj)
          w_c=w(i_traj+1,k_w  ,j_traj)
        else
          w_b=0.0
          w_c=0.0
        endif
        w_a=w(i_traj  ,k_w+1,j_traj)
        w_d=w(i_traj+1,k_w+1,j_traj)
        d_a=abs((real(i_traj+1)-traj_i(tjk))*(real(k_w  )-(traj_k(tjk)+0.5)))
        d_b=abs((real(i_traj+1)-traj_i(tjk))*(real(k_w+1)-(traj_k(tjk)+0.5)))
        d_c=abs((real(i_traj  )-traj_i(tjk))*(real(k_w+1)-(traj_k(tjk)+0.5)))
        d_d=abs((real(i_traj  )-traj_i(tjk))*(real(k_w  )-(traj_k(tjk)+0.5)))
        w_temp_lower=(w_a*d_a+w_b*d_b+w_c*d_c+w_d*d_d)/(d_a+d_b+d_c+d_d)
!for layer j_traj+1
        if (k_w .ge. 1) then
          w_b=w(i_traj  ,k_w  ,j_traj+1)
          w_c=w(i_traj+1,k_w  ,j_traj+1)
        else
          w_b=0.0
          w_c=0.0
        endif
        w_a=w(i_traj  ,k_w+1,j_traj+1)
        w_d=w(i_traj+1,k_w+1,j_traj+1)
        d_a=abs((real(i_traj+1)-traj_i(tjk))*(real(k_w  )-(traj_k(tjk)+0.5)))
        d_b=abs((real(i_traj+1)-traj_i(tjk))*(real(k_w+1)-(traj_k(tjk)+0.5)))
        d_c=abs((real(i_traj  )-traj_i(tjk))*(real(k_w+1)-(traj_k(tjk)+0.5)))
        d_d=abs((real(i_traj  )-traj_i(tjk))*(real(k_w  )-(traj_k(tjk)+0.5)))
        w_temp_upper=(w_a*d_a+w_b*d_b+w_c*d_c+w_d*d_d)/(d_a+d_b+d_c+d_d)

        traj_w=w_temp_upper*abs(real(j_traj)-traj_j(tjk))+w_temp_lower*abs(real(j_traj+1)-traj_j(tjk))
!get old eta
        eta_old=grid%znw(k_w+1)*abs(traj_k(tjk)+0.5-real(k_w))+grid%znw(k_w)*abs(traj_k(tjk)+0.5-real(k_w+1))

        rdx_grid=rdx*msft(i_traj,j_traj)! 1/(dx/msft)
        rdy_grid=rdy*msft(i_traj,j_traj)
        rdz_grid=rdnw(k_traj)
        deltx=traj_u*DT
        delty=traj_v*DT
        deltz=traj_w*DT
        traj_i(tjk)=traj_i(tjk)+deltx*rdx_grid
        traj_j(tjk)=traj_j(tjk)+delty*rdy_grid
        eta_new=eta_old+deltz
! get new traj_k(tjk)
        keta_temp = 0
        do keta=1, kme-1
          if (eta_new .le. grid%znw(keta) .and. eta_new .gt. grid%znw(keta+1)) then
           keta_temp=keta
          endif
        enddo
        if (keta_temp .eq. 0)  then
            traj_k(tjk) = traj_k(tjk)
        else
            traj_k(tjk) = (real(keta_temp)*abs(eta_new-grid%znw(keta_temp+1))+ &
                           real(keta_temp+1)*abs(eta_new-grid%znw(keta_temp))) &
                           /(grid%znw(keta_temp)-grid%znw(keta_temp+1))
            traj_k(tjk) = traj_k(tjk)-0.5
        endif
!! convert i,j,k into lon, lat
        if( has_proj_map ) then
          call ij_to_latlon (proj, traj_i(tjk), &
                             traj_j(tjk),traj_lat(tjk),traj_long(tjk))
        endif
      endif is_in_time_interval
     else traj_in_domain
        traj_i(tjk) = -9999.0
        traj_j(tjk) = -9999.0
        traj_k(tjk) = -9999.0
        traj_long(tjk) = -9999.0
        traj_lat(tjk) = -9999.0
     endif traj_in_domain
 endif traj_is_active
     traj_i(tjk) = wrf_dm_max_real(traj_i(tjk))
     traj_j(tjk) = wrf_dm_max_real(traj_j(tjk))
     traj_k(tjk) = wrf_dm_max_real(traj_k(tjk))
     traj_long(tjk) = wrf_dm_max_real(traj_long(tjk))
     traj_lat(tjk)  = wrf_dm_max_real(traj_lat(tjk))
enddo traj_loop
!end trajectory

END SUBROUTINE trajectory
!------------------------------------------------------------------------
!cyl:Implement the map prpjection code for trajectory calculation
!                                    Chiaying Lee  RSMAS/UM        
!------------------------------------------------------------------------
subroutine trajmapproj (grid,config_flags,ts_proj)
!------------------------------------------------------------------------
!!! This code calculates map-projection of trajectories. It is from share/wrf_timeseries.F
!------------------------------------------------------------------------

   IMPLICIT NONE


   ! Arguments
   TYPE (domain), INTENT(IN) :: grid
   TYPE (grid_config_rec_type) , INTENT(IN)  :: config_flags
   ! Externals
   LOGICAL, EXTERNAL :: wrf_dm_on_monitor
   INTEGER, EXTERNAL :: get_unused_unit


   ! Local variables
   INTEGER :: ntsloc_temp
   INTEGER :: i, k, iunit
   REAL :: ts_rx, ts_ry, ts_xlat, ts_xlong, ts_hgt
   REAL :: known_lat, known_lon
   CHARACTER (LEN=132) :: message
   TYPE (PROJ_INFO), INTENT(out) :: ts_proj


   INTEGER :: ids, ide, jds, jde, kds, kde,        &
              ims, ime, jms, jme, kms, kme,        &
              ips, ipe, jps, jpe, kps, kpe,        &
              imsx, imex, jmsx, jmex, kmsx, kmex,  &
              ipsx, ipex, jpsx, jpex, kpsx, kpex,  &
              imsy, imey, jmsy, jmey, kmsy, kmey,  &
              ipsy, ipey, jpsy, jpey, kpsy, kpey
   TYPE (grid_config_rec_type)               :: config_flags_temp


   config_flags_temp = config_flags

     CALL get_ijk_from_grid ( grid ,                               &
                               ids, ide, jds, jde, kds, kde,        &
                               ims, ime, jms, jme, kms, kme,        &
                               ips, ipe, jps, jpe, kps, kpe,        &
                               imsx, imex, jmsx, jmex, kmsx, kmex,  &
                               ipsx, ipex, jpsx, jpex, kpsx, kpex,  &
                               imsy, imey, jmsy, jmey, kmsy, kmey,  &
                               ipsy, ipey, jpsy, jpey, kpsy, kpey )

     CALL model_to_grid_config_rec ( grid%id , model_config_rec , config_flags_temp )


      ! Set up map transformation structure
      CALL map_init(ts_proj)


      IF (ips <= 1 .AND. 1 <= ipe .AND. &
          jps <= 1 .AND. 1 <= jpe) THEN
         known_lat = grid%xlat(1,1)
         known_lon = grid%xlong(1,1)
      ELSE
         known_lat = 9999.
         known_lon = 9999.
      END IF
      known_lat = wrf_dm_min_real(known_lat)
      known_lon = wrf_dm_min_real(known_lon)


      ! Mercator
      IF (config_flags%map_proj == PROJ_MERC) THEN
         CALL map_set(PROJ_MERC, ts_proj,               &
                      truelat1 = config_flags%truelat1, &
                      lat1     = known_lat,             &
                      lon1     = known_lon,             &
                      knowni   = 1.,                    &
                      knownj   = 1.,                    &
                      dx       = config_flags%dx)
      ! Lambert conformal
      ELSE IF (config_flags%map_proj == PROJ_LC) THEN
      CALL map_set(PROJ_LC, ts_proj,                  &
                      truelat1 = config_flags%truelat1,  &
                      truelat2 = config_flags%truelat2,  &
                      stdlon   = config_flags%stand_lon, &
                      lat1     = known_lat,              &
                      lon1     = known_lon,              &
                      knowni   = 1.,                     &
                      knownj   = 1.,                     &
                      dx       = config_flags%dx)
      ! Polar stereographic
      ELSE IF (config_flags%map_proj == PROJ_PS) THEN
         CALL map_set(PROJ_PS, ts_proj,                  &
                      truelat1 = config_flags%truelat1,  &
                      stdlon   = config_flags%stand_lon, &
                      lat1     = known_lat,              &
                      lon1     = known_lon,              &
                      knowni   = 1.,                     &
                      knownj   = 1.,                     &
                      dx       = config_flags%dx)


      ! Cassini (global ARW)
      ELSE IF (config_flags%map_proj == PROJ_CASSINI) THEN
         CALL map_set(PROJ_CASSINI, ts_proj,                            &
                      latinc   = grid%dy*360.0/(2.0*EARTH_RADIUS_M*PI), &
                      loninc   = grid%dx*360.0/(2.0*EARTH_RADIUS_M*PI), &
                      lat1     = known_lat,                             &
                      lon1     = known_lon,                             &
! We still need to get POLE_LAT and POLE_LON metadata variables before
!   this will work for rotated poles.
                      lat0     = 90.0,                                  &
                      lon0     = 0.0,                                   &
                      knowni   = 1.,                                    &
                      knownj   = 1.,                                    &
                      stdlon   = config_flags%stand_lon)


      ! Rotated latitude-longitude
      ELSE IF (config_flags%map_proj == PROJ_ROTLL) THEN
         CALL map_set(PROJ_ROTLL, ts_proj,                      &
! I have no idea how this should work for NMM nested domains
                      ixdim    = grid%e_we-1,                   &
                      jydim    = grid%e_sn-1,                   &
                      phi      = real(grid%e_sn-2)*grid%dy/2.0, &
                      lambda   = real(grid%e_we-2)*grid%dx,     &
                      lat1     = config_flags%cen_lat,          &
                      lon1     = config_flags%cen_lon,          &
                      latinc   = grid%dy,                       &
                      loninc   = grid%dx,                       &
                      stagger  = HH)


      END IF


end subroutine trajmapproj
! Contained procedure inserted into the retained module_em research copy.
SUBROUTINE rk_update_joint_moments(q1,q2,n1,n2,qt,nt,nmoist,nscalar,qindex,nindex,qsindex,nnindex, &
     ru,rv,ww,muold,munew,mub,c1,c2,msftx,msfty,rdx,rdy,rdnw,al,alb,dt,rk,itimestep,spec_zone, &
     ids,ide,jds,jde,kds,kde,ims,ime,jms,jme,kms,kme,its,ite,jts,jte,kts,kte, &
     pr87_raw_qsrc,pr87_raw_nsrc,pr87_coupled_qsrc,pr87_coupled_nsrc, &
     pr87_source_carrier,pr87_source_step,pr87_later_qsrc,pr87_later_nsrc, &
     pr87_all_pair_diffusion_delta,pr87_all_pair_diffusion_step,pr87_pbl_tendency_delta64,pr87_pbl_tendency_step,pr87_pbl_tendency_phase, &
     mut_diff,xkmhd_diff,msfux_diff,msfuy_diff,msfvx_inv_diff,msfvy_diff, &
     pr87_all_pair_diffusion_old,pr87_all_pair_diffusion_tendency32, &
     pr87_all_pair_diffusion_identity,pr87_all_pair_diffusion_valid, &
     pr87_all_pair_diffusion_nonD64) ! PR91_SOURCE_DIFFUSION_C12
  USE iso_fortran_env, ONLY: int32,int64,real32,real64
  USE cloud_bal_joint_transport, ONLY: joint_moment_is_valid, joint_moment_is_valid64, &
       joint_moment_store, joint_qnb_update, joint_bulk_candidate_absence_is_valid
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  USE pr87_horizontal_diffusion64, ONLY: horizontal_diffusion64
  IMPLICIT NONE
  INTEGER,INTENT(IN) :: nmoist,nscalar,qindex(4),nindex(4),rk,itimestep,spec_zone
  INTEGER,INTENT(IN) :: qsindex,nnindex
  INTEGER,INTENT(IN) :: ids,ide,jds,jde,kds,kde,ims,ime,jms,jme,kms,kme
  INTEGER,INTENT(IN) :: its,ite,jts,jte,kts,kte,pr87_source_step
  REAL,INTENT(IN) :: pr87_raw_qsrc(ims:ime,kms:kme,jms:jme,2)
  REAL,INTENT(IN) :: pr87_raw_nsrc(ims:ime,kms:kme,jms:jme,2)
  REAL,INTENT(IN) :: pr87_coupled_qsrc(ims:ime,kms:kme,jms:jme,2)
  REAL,INTENT(IN) :: pr87_coupled_nsrc(ims:ime,kms:kme,jms:jme,2)
  REAL,INTENT(IN) :: pr87_source_carrier(ims:ime,kms:kme,jms:jme)
  REAL(real64),INTENT(IN) :: pr87_later_qsrc(ims:ime,kms:kme,jms:jme,2)
  REAL(real64),INTENT(IN) :: pr87_later_nsrc(ims:ime,kms:kme,jms:jme,2)
  REAL(real64),INTENT(IN),OPTIONAL :: &
       pr87_all_pair_diffusion_delta(ims:ime,kms:kme,jms:jme,8)
  REAL(real64),INTENT(IN),OPTIONAL :: &
       pr87_all_pair_diffusion_old(ims:ime,kms:kme,jms:jme,4)
  REAL,INTENT(IN),OPTIONAL :: &
       pr87_all_pair_diffusion_tendency32(ims:ime,kms:kme,jms:jme,8)
  REAL(real64),INTENT(IN),OPTIONAL :: &
       pr87_all_pair_diffusion_nonD64(ims:ime,kms:kme,jms:jme,4)
  INTEGER,INTENT(IN),OPTIONAL :: pr87_all_pair_diffusion_identity(8), &
       pr87_all_pair_diffusion_valid(8)
  INTEGER,INTENT(IN),OPTIONAL :: pr87_all_pair_diffusion_step
  REAL(real64),INTENT(IN) :: pr87_pbl_tendency_delta64(ims:ime,kms:kme,jms:jme,4)
  INTEGER,INTENT(IN) :: pr87_pbl_tendency_step,pr87_pbl_tendency_phase
  REAL,INTENT(INOUT) :: q1(ims:ime,kms:kme,jms:jme,nmoist),q2(ims:ime,kms:kme,jms:jme,nmoist)
  REAL,INTENT(INOUT) :: n1(ims:ime,kms:kme,jms:jme,nscalar),n2(ims:ime,kms:kme,jms:jme,nscalar)
  REAL,INTENT(IN) :: qt(ims:ime,kms:kme,jms:jme,nmoist),nt(ims:ime,kms:kme,jms:jme,nscalar)
  REAL,INTENT(IN) :: ru(ims:ime,kms:kme,jms:jme),rv(ims:ime,kms:kme,jms:jme)
  REAL,INTENT(IN) :: ww(ims:ime,kms:kme,jms:jme)
  REAL,INTENT(IN) :: al(ims:ime,kms:kme,jms:jme),alb(ims:ime,kms:kme,jms:jme)
  REAL,INTENT(IN) :: muold(ims:ime,jms:jme),munew(ims:ime,jms:jme),mub(ims:ime,jms:jme)
  REAL,INTENT(IN) :: msftx(ims:ime,jms:jme),msfty(ims:ime,jms:jme)
  REAL,INTENT(IN) :: mut_diff(ims:ime,jms:jme)
  REAL,INTENT(IN) :: xkmhd_diff(ims:ime,kms:kme,jms:jme)
  REAL,INTENT(IN) :: msfux_diff(ims:ime,jms:jme),msfuy_diff(ims:ime,jms:jme)
  REAL,INTENT(IN) :: msfvx_inv_diff(ims:ime,jms:jme),msfvy_diff(ims:ime,jms:jme)
  REAL,INTENT(IN) :: c1(kms:kme),c2(kms:kme),rdnw(kms:kme),rdx,rdy,dt
  REAL(real32),ALLOCATABLE :: qb(:,:),nb(:,:),qc(:,:),nc(:,:),qs(:,:),ns(:,:),qa(:,:),na(:,:)
  REAL(real32),ALLOCATABLE :: oldcarrier(:),newcarrier(:),drydensity(:)
  REAL(real64),ALLOCATABLE :: number_bounds(:,:,:)
  ! Default-REAL coefficients of the hash-bound selected KDM6 source.
  REAL(real32),PARAMETER :: rain_pidn=12566.37109375_real32,rain_power=3.0_real32
  REAL(real32),PARAMETER :: rain_lambda_min=961.0_real32,rain_lambda_max=35000.0_real32
  REAL(real32),PARAMETER :: cloud_pidn=523.59881591796875_real32,cloud_power=3.0_real32
  REAL(real32),PARAMETER :: cloud_lambda_min=12000.0_real32,cloud_lambda_max=500000.0_real32
  REAL(real32),ALLOCATABLE :: snow_candidate(:),ccn_candidate(:)
  REAL(real64),ALLOCATABLE :: donor_q(:,:,:,:),donor_n(:,:,:,:)
  REAL,ALLOCATABLE :: prepared_q(:,:,:,:),prepared_n(:,:,:,:)
  REAL(real64),ALLOCATABLE :: prepared_diffusion(:,:,:),prepared_n_diffusion(:,:,:)
  REAL(real64) :: source_diff_delta(2),source_diff_sum(2),source_diff_l1(2),source_diff_max(2)
  REAL(real64) :: source_nond_diffusion(2)
  INTEGER :: source_diff_cells,source_diff_u
  INTEGER :: stage_diag_u,stage_diag_dx,stage_diag_dy
  INTEGER :: pr92_full_store_stage
  REAL(real64) :: stage_diag_qdiff,stage_diag_ndiff
  REAL(real64),ALLOCATABLE :: qs64(:,:),ns64(:,:),qa64(:,:),na64(:,:)
  REAL(real64) :: theta,rejected_q(4),rejected_n(4),minmass(4),maxmass(4),rate(2)
  REAL(real64) :: outflow,cfl,maxcfl,source_candidate(2),source_sum64(2),source_rate64(2),pbl_source_correction_sum(4),pbl_source_correction_l1(4), &
       pbl_source_correction_max(4),pbl_carrier_min,pbl_carrier_max,pbl_delta
  INTEGER :: pbl_ledger_unit,pbl_ledger_cells,pbl_channel
  REAL(real64) :: diffusion_delta_sum(8),diffusion_delta_l1(8),diffusion_delta_max(8)
  REAL(real32) :: source_stored(2),full_stored(2),source_check_stored(2)
  REAL(real32) :: source_increment32(2),source_endpoint32(2)
  REAL(real64) :: storage_delta_q(4),storage_delta_n(4)
  INTEGER :: storage_adjustments(4),adjustment,full_failures
  INTEGER :: inactive_q_quantum_adjustments(4),bulk_volume_absences
  REAL(real64) :: bulk_volume_delta(2)
  LOGICAL :: full_valid,baseline_feasible,source_first_pair(4),failed_pairs(4),source_valid
  INTEGER :: il,ih,jl,jh,kl,kh,i,j,k,p,cell,cells,u,iq,in,source_failures
  LOGICAL :: feasible,density_valid
  EXTERNAL :: pr85_pbl_tendency_dump,pr85_dry_density_from_al_alb

  IF (PRESENT(pr87_all_pair_diffusion_delta) .NEQV. &
      PRESENT(pr87_all_pair_diffusion_step)) &
    CALL wrf_error_fatal('PR87 rain diffusion delta/step must be supplied together')
  IF (PRESENT(pr87_all_pair_diffusion_delta)) THEN
    IF (pr87_all_pair_diffusion_step /= itimestep) &
      CALL wrf_error_fatal('PR87 rain diffusion timestep mismatch')
  END IF
  IF ((PRESENT(pr87_all_pair_diffusion_old) .NEQV. &
       PRESENT(pr87_all_pair_diffusion_identity)).OR. &
      (PRESENT(pr87_all_pair_diffusion_old) .NEQV. &
       PRESENT(pr87_all_pair_diffusion_valid)).OR. &
      (PRESENT(pr87_all_pair_diffusion_old) .NEQV. &
       PRESENT(pr87_all_pair_diffusion_tendency32)).OR. &
      (PRESENT(pr87_all_pair_diffusion_old) .NEQV. &
       PRESENT(pr87_all_pair_diffusion_nonD64))) &
    CALL wrf_error_fatal('PR91 incomplete source diffusion cache')
  IF (PRESENT(pr87_all_pair_diffusion_old)) THEN
    IF (pr87_all_pair_diffusion_identity(1)/=itimestep.OR. &
        pr87_all_pair_diffusion_identity(2)/=1.OR. &
        pr87_all_pair_diffusion_identity(3)<ims+1.OR. &
        pr87_all_pair_diffusion_identity(4)>ime-1.OR. &
        pr87_all_pair_diffusion_identity(5)<jms+1.OR. &
        pr87_all_pair_diffusion_identity(6)>jme-1.OR. &
        pr87_all_pair_diffusion_identity(7)<kms.OR. &
        pr87_all_pair_diffusion_identity(8)>kme) &
      CALL wrf_error_fatal('PR91 source diffusion cache identity mismatch')
    IF (ANY(pr87_all_pair_diffusion_valid(1:4)/=1)) &
      CALL wrf_error_fatal('PR91 incomplete RK1 before/after diffusion cache')
    IF (.NOT.ALL(ieee_is_finite(pr87_all_pair_diffusion_nonD64))) &
      CALL wrf_error_fatal('PR91 nonfinite separated non-diffusion source cache')
  END IF
  diffusion_delta_sum=0.0_real64
  diffusion_delta_l1=0.0_real64
  diffusion_delta_max=0.0_real64
  ! Current experiment: one specified domain, one tile, no implicit vertical advection.
  ! The outer donor ring remains available; only the first native consumer overlap changes.
  il=MAX(its,ids+1); ih=MIN(ite,ide-2)
  jl=MAX(jts,jds+1); jh=MIN(jte,jde-2)
  kl=MAX(kts,kds); kh=MIN(kte,kde-1)
  IF (ANY(qindex<1).OR.ANY(qindex>nmoist).OR.ANY(nindex<1).OR.ANY(nindex>nscalar)) &
    CALL wrf_error_fatal('PR85 invalid grouped scalar registry slots')
  IF (qsindex<1.OR.qsindex>nmoist.OR.nnindex<1.OR.nnindex>nscalar) &
    CALL wrf_error_fatal('PR85 invalid unpaired scalar registry slots')
  IF (spec_zone/=1.OR.il>ih.OR.jl>jh.OR.kl>kh) &
    CALL wrf_error_fatal('PR85 joint update unsupported domain footprint')
  IF (PRESENT(pr87_all_pair_diffusion_identity)) THEN
    IF (pr87_all_pair_diffusion_identity(3)<il.OR.pr87_all_pair_diffusion_identity(4)>ih.OR. &
        pr87_all_pair_diffusion_identity(5)<jl.OR.pr87_all_pair_diffusion_identity(6)>jh.OR. &
        pr87_all_pair_diffusion_identity(7)<kl.OR.pr87_all_pair_diffusion_identity(8)>kh) &
      CALL wrf_error_fatal('PR91 diffusion bounds differ from prepared source footprint')
  END IF
  IF (pr87_source_step/=itimestep.OR.pr87_pbl_tendency_step/=itimestep.OR. &
      pr87_pbl_tendency_phase/=1) &
    CALL wrf_error_fatal('PR87 PBL/source payload epoch mismatch')
  pbl_source_correction_sum=0.0_real64; pbl_source_correction_l1=0.0_real64; &
       pbl_source_correction_max=0.0_real64
  pbl_carrier_min=HUGE(0.0_real64); pbl_carrier_max=-HUGE(0.0_real64); pbl_ledger_cells=0
  DO j=jl,jh
  DO k=kl,kh
  DO i=il,ih
    IF (.NOT.ALL(ieee_is_finite(pr87_pbl_tendency_delta64(i,k,j,:)))) &
      CALL wrf_error_fatal('PR87 nonfinite PBL tendency correction')
    IF (.NOT.ieee_is_finite(pr87_source_carrier(i,k,j)).OR. &
        pr87_source_carrier(i,k,j)<=0.0_real64) &
      CALL wrf_error_fatal('PR87 invalid captured PBL source carrier')
    IF (pr87_coupled_qsrc(i,k,j,1)/=qt(i,k,j,qindex(1)).OR. &
        pr87_coupled_qsrc(i,k,j,2)/=qt(i,k,j,qindex(2)).OR. &
        pr87_coupled_nsrc(i,k,j,1)/=nt(i,k,j,nindex(1)).OR. &
        pr87_coupled_nsrc(i,k,j,2)/=nt(i,k,j,nindex(2))) &
      CALL wrf_error_fatal('PR87 PBL source reference mismatch')
    pbl_ledger_cells=pbl_ledger_cells+1
    pbl_carrier_min=MIN(pbl_carrier_min,pr87_source_carrier(i,k,j))
    pbl_carrier_max=MAX(pbl_carrier_max,pr87_source_carrier(i,k,j))
    DO pbl_channel=1,4
      pbl_delta=REAL(dt,real64)*pr87_source_carrier(i,k,j)* &
                  pr87_pbl_tendency_delta64(i,k,j,pbl_channel)
      pbl_source_correction_sum(pbl_channel)= &
          pbl_source_correction_sum(pbl_channel)+pbl_delta
      pbl_source_correction_l1(pbl_channel)= &
          pbl_source_correction_l1(pbl_channel)+ABS(pbl_delta)
      pbl_source_correction_max(pbl_channel)= &
          MAX(pbl_source_correction_max(pbl_channel),ABS(pbl_delta))
    END DO
  END DO
  END DO
  END DO
  OPEN(NEWUNIT=pbl_ledger_unit,FILE='pr87_pbl_source_correction.raw', &
       STATUS='UNKNOWN',POSITION='APPEND')
  WRITE(pbl_ledger_unit,'(A,1X,I0,1X,I0,1X,ES24.16,1X,I0,1X,I0, &
       & 2(1X,ES24.16),12(1X,ES24.16))') 'PR87_PBL_SOURCE_CORRECTION_RK', &
       itimestep,rk,dt,pr87_pbl_tendency_phase,pbl_ledger_cells, &
       pbl_carrier_min,pbl_carrier_max,pbl_source_correction_sum, &
       pbl_source_correction_l1,pbl_source_correction_max
  CLOSE(pbl_ledger_unit)
  IF (rk==1) CALL pr85_pbl_tendency_dump('PRE_GROUPED_PHYSICS_TEND',itimestep,0, &
      ims,ime,jms,jme,kms,kme,il,ih,jl,jh,kl,kh, &
      qt(ims,kms,jms,P_QV),qt(ims,kms,jms,qindex(1)),qt(ims,kms,jms,qindex(2)), &
      nt(ims,kms,jms,nindex(1)),nt(ims,kms,jms,nindex(2)))
  IF (rk==1) THEN
    DO p=1,4
      q1(:,:,:,qindex(p))=q2(:,:,:,qindex(p))
      n1(:,:,:,nindex(p))=n2(:,:,:,nindex(p))
    END DO
    q1(:,:,:,qsindex)=q2(:,:,:,qsindex)
    n1(:,:,:,nnindex)=n2(:,:,:,nnindex)
  END IF
  cells=(ih-il+1)*(jh-jl+1)*(kh-kl+1)
  ALLOCATE(qb(cells,4),nb(cells,4),qc(cells,4),nc(cells,4),qs(cells,4),ns(cells,4), &
           qa(cells,4),na(cells,4),oldcarrier(cells),newcarrier(cells),drydensity(cells))
  ALLOCATE(snow_candidate(cells),ccn_candidate(cells))
  ! Q/N mean particle mass; Q/B is graupel bulk density in kg m-3.
  minmass=[REAL(cloud_pidn,real64)/REAL(cloud_lambda_max,real64)**REAL(cloud_power,real64), &
           1570.79638671875_real64/1820000.0_real64**3, &
           REAL(rain_pidn,real64)/REAL(rain_lambda_max,real64)**REAL(rain_power,real64),100.0_real64]
  maxmass=[REAL(cloud_pidn,real64)/REAL(cloud_lambda_min,real64)**REAL(cloud_power,real64), &
           1570.79638671875_real64/9080.0_real64**3, &
           REAL(rain_pidn,real64)/REAL(rain_lambda_min,real64)**REAL(rain_power,real64),900.0_real64]
  ALLOCATE(qs64(cells,4),ns64(cells,4),qa64(cells,4),na64(cells,4),number_bounds(cells,2,4))
  number_bounds=0.0_real64
  source_first_pair=.FALSE.; failed_pairs=.FALSE.
  cell=0; maxcfl=0.0_real64
  DO j=jl,jh
  DO k=kl,kh
  DO i=il,ih
    cell=cell+1
    oldcarrier(cell)=c1(k)*(muold(i,j)+mub(i,j))+c2(k)
    newcarrier(cell)=c1(k)*(munew(i,j)+mub(i,j))+c2(k)
    CALL pr85_dry_density_from_al_alb(al(i,k,j),alb(i,k,j), &
                                      drydensity(cell),density_valid)
    IF (.NOT.density_valid) CALL wrf_error_fatal('PR85 invalid AL+ALB dry density')
    number_bounds(cell,1,1)=REAL(drydensity(cell),real64)* &
        REAL(cloud_lambda_min,real64)**REAL(cloud_power,real64)/REAL(cloud_pidn,real64)
    number_bounds(cell,2,1)=REAL(drydensity(cell),real64)* &
        REAL(cloud_lambda_max,real64)**REAL(cloud_power,real64)/REAL(cloud_pidn,real64)
    number_bounds(cell,1,3)=REAL(drydensity(cell),real64)* &
        REAL(rain_lambda_min,real64)**REAL(rain_power,real64)/REAL(rain_pidn,real64)
    number_bounds(cell,2,3)=REAL(drydensity(cell),real64)* &
        REAL(rain_lambda_max,real64)**REAL(rain_power,real64)/REAL(rain_pidn,real64)
    IF (.NOT.ieee_is_finite(oldcarrier(cell)).OR.oldcarrier(cell)<=0.0) &
      CALL wrf_error_fatal('PR85 nonpositive old dry carrier')
    outflow=REAL(msftx(i,j)*msfty(i,j)*rdx,real64)* &
      (MAX(REAL(ru(i+1,k,j),real64),0.0_real64)+MAX(-REAL(ru(i,k,j),real64),0.0_real64)) &
      +REAL(msftx(i,j)*msfty(i,j)*rdy,real64)* &
      (MAX(REAL(rv(i,k,j+1),real64),0.0_real64)+MAX(-REAL(rv(i,k,j),real64),0.0_real64))
    ! eta decreases upwards: a positive ww at k+1 enters cell k from above.
    IF (k>kl) outflow=outflow+REAL(msfty(i,j)*(-rdnw(k)),real64)* &
      MAX(REAL(ww(i,k,j),real64),0.0_real64)
    IF (k<kh) outflow=outflow+REAL(msfty(i,j)*(-rdnw(k)),real64)* &
      MAX(-REAL(ww(i,k+1,j),real64),0.0_real64)
    cfl=REAL(dt,real64)*outflow/REAL(oldcarrier(cell),real64)
    maxcfl=MAX(maxcfl,cfl)
    DO p=1,4
      iq=qindex(p); in=nindex(p)
      qb(cell,p)=q1(i,k,j,iq); nb(cell,p)=n1(i,k,j,in)
      qc(cell,p)=q2(i,k,j,iq); nc(cell,p)=n2(i,k,j,in)
      qs(cell,p)=qt(i,k,j,iq); ns(cell,p)=nt(i,k,j,in)
      ! Use one old-time upwind donor map for both moments, not centered scalar fluxes.
      rate=air_tendency(q1(:,:,:,iq),n1(:,:,:,in),i,k,j,p)
      ! Keep the shared-face proposal in its calculation precision.
      ! The REAL32 arrays remain diagnostic/API arguments only.
      IF (.NOT.ALL(ieee_is_finite(rate))) &
        CALL wrf_error_fatal('PR87 nonfinite joint air rate')
      IF (ANY(ABS(rate)>REAL(HUGE(0.0_real32),real64))) &
        CALL wrf_error_fatal('PR87 joint air diagnostic rate overflow')
      qa(cell,p)=REAL(rate(1),real32); na(cell,p)=REAL(rate(2),real32)
      IF (p<=2) THEN
        IF (p==1) THEN
          qs64(cell,p)=(REAL(pr87_raw_qsrc(i,k,j,p),real64)+ &
              pr87_pbl_tendency_delta64(i,k,j,1))*REAL(pr87_source_carrier(i,k,j),real64)+ &
              pr87_later_qsrc(i,k,j,p)
          ns64(cell,p)=(REAL(pr87_raw_nsrc(i,k,j,p),real64)+ &
              pr87_pbl_tendency_delta64(i,k,j,2))*REAL(pr87_source_carrier(i,k,j),real64)+ &
              pr87_later_nsrc(i,k,j,p)
        ELSE
          qs64(cell,p)=(REAL(pr87_raw_qsrc(i,k,j,p),real64)+ &
              pr87_pbl_tendency_delta64(i,k,j,3))*REAL(pr87_source_carrier(i,k,j),real64)+ &
              pr87_later_qsrc(i,k,j,p)
          ns64(cell,p)=(REAL(pr87_raw_nsrc(i,k,j,p),real64)+ &
              pr87_pbl_tendency_delta64(i,k,j,4))*REAL(pr87_source_carrier(i,k,j),real64)+ &
              pr87_later_nsrc(i,k,j,p)
        END IF
      ELSE
        qs64(cell,p)=REAL(qs(cell,p),real64); ns64(cell,p)=REAL(ns(cell,p),real64)
      END IF
      IF (p>=1.AND.p<=4.AND.PRESENT(pr87_all_pair_diffusion_delta)) THEN
        IF (.NOT.ALL(ieee_is_finite(pr87_all_pair_diffusion_delta(i,k,j,2*p-1:2*p)))) &
          CALL wrf_error_fatal('PR87 nonfinite paired diffusion correction')
        qs64(cell,p)=qs64(cell,p)+pr87_all_pair_diffusion_delta(i,k,j,2*p-1)
        ns64(cell,p)=ns64(cell,p)+pr87_all_pair_diffusion_delta(i,k,j,2*p)
      END IF
      qa64(cell,p)=rate(1); na64(cell,p)=rate(2)
    END DO
    rate=air_tendency(q1(:,:,:,qsindex),q1(:,:,:,qsindex),i,k,j)
    snow_candidate(cell)=singleton_candidate(q1(i,k,j,qsindex),qt(i,k,j,qsindex),rate(1), &
                                             oldcarrier(cell),newcarrier(cell),drydensity(cell),.FALSE.)
    rate=air_tendency(n1(:,:,:,nnindex),n1(:,:,:,nnindex),i,k,j)
    ccn_candidate(cell)=singleton_candidate(n1(i,k,j,nnindex),nt(i,k,j,nnindex),rate(1), &
                                            oldcarrier(cell),newcarrier(cell),drydensity(cell),.TRUE.)
  END DO
  END DO
  END DO
  IF (.NOT.ieee_is_finite(maxcfl).OR.maxcfl>1.0_real64) &
    CALL wrf_error_fatal('PR85 common donor-cell carrier CFL exceeded')
  IF (.NOT.ALL(ieee_is_finite(newcarrier))) &
    CALL wrf_error_fatal('PR87 nonfinite new dry carrier')
  IF (ANY(newcarrier<=0.0_real32)) CALL wrf_error_fatal('PR87 nonpositive new dry carrier')
  IF (.NOT.ieee_is_finite(dt)) CALL wrf_error_fatal('PR87 nonfinite grouped timestep')
  IF (dt<=0.0_real32) CALL wrf_error_fatal('PR87 nonpositive grouped timestep')
  IF (ANY(.NOT.ieee_is_finite(qb)).OR.ANY(.NOT.ieee_is_finite(nb)).OR. &
      ANY(.NOT.ieee_is_finite(qc)).OR.ANY(.NOT.ieee_is_finite(nc)).OR. &
      ANY(.NOT.ieee_is_finite(qs64)).OR.ANY(.NOT.ieee_is_finite(ns64)).OR. &
      ANY(.NOT.ieee_is_finite(qa64)).OR.ANY(.NOT.ieee_is_finite(na64))) &
    CALL wrf_error_fatal('PR87 nonfinite grouped state/source/transport operand')
  CALL evaluate_joint_candidate()
  baseline_feasible=feasible
  IF (.NOT.feasible.AND.rk==3) THEN
    CALL find_failed_baseline_pairs()
    CALL probe_failed_graupel_pair()
    ! One operator is chosen for the entire pair support, never for individual cells.
    IF (.NOT.ANY(failed_pairs(3:4))) THEN
      source_first_pair(1:2)=failed_pairs(1:2)
      IF (ANY(source_first_pair)) THEN
        CALL prepare_source_first_rates()
        CALL evaluate_joint_candidate()
      END IF
    END IF
  END IF
  OPEN(NEWUNIT=u,FILE='pr85_joint_transport_budget.raw',STATUS='UNKNOWN',POSITION='APPEND')
  WRITE(u,*) 'BASELINE_JOINT_FEASIBLE',itimestep,rk,baseline_feasible
  WRITE(u,*) 'SOURCE_FIRST_PAIR_FALLBACK',itimestep,rk,source_first_pair
  WRITE(u,*) 'JOINT_RK',rk,cells,maxcfl,theta,feasible
  WRITE(u,*) 'REJECTED_PRESSURE_COORDINATE_Q',rejected_q
  WRITE(u,*) 'REJECTED_PRESSURE_COORDINATE_MOMENT',rejected_n
  CLOSE(u)
  IF (PRESENT(pr87_all_pair_diffusion_delta)) THEN
    diffusion_delta_sum=0.0_real64
    diffusion_delta_l1=0.0_real64
    diffusion_delta_max=0.0_real64
    DO j=jl,jh
      DO k=kl,kh
        DO i=il,ih
          diffusion_delta_sum=diffusion_delta_sum+REAL(dt,real64)* &
               pr87_all_pair_diffusion_delta(i,k,j,:)
          diffusion_delta_l1=diffusion_delta_l1+REAL(dt,real64)* &
               ABS(pr87_all_pair_diffusion_delta(i,k,j,:))
          diffusion_delta_max=MAX(diffusion_delta_max,REAL(dt,real64)* &
               ABS(pr87_all_pair_diffusion_delta(i,k,j,:)))
        END DO
      END DO
    END DO
    OPEN(NEWUNIT=u,FILE='pr87_all_pair_diffusion_precision.raw',STATUS='UNKNOWN', &
         POSITION='APPEND',ACTION='WRITE')
    WRITE(u,*) 'ALL_PAIR_DIFFUSION_RK_CORRECTION',itimestep,rk,cells
    WRITE(u,*) 'DT_SUM_PRESSURE_QN_CHANNELS',diffusion_delta_sum
    WRITE(u,*) 'DT_L1_PRESSURE_QN_CHANNELS',diffusion_delta_l1
    WRITE(u,*) 'DT_MAXABS_PRESSURE_QN_CHANNELS',diffusion_delta_max
    CLOSE(u)
  END IF
  IF (.NOT.feasible) THEN
    OPEN(NEWUNIT=u,FILE='pr85_joint_source_failure.raw',STATUS='UNKNOWN',POSITION='APPEND')
    cell=0; source_failures=0; full_failures=0
    DO j=jl,jh
    DO k=kl,kh
    DO i=il,ih
      cell=cell+1
      DO p=1,4
        IF (.NOT.ieee_is_finite(oldcarrier(cell)).OR.oldcarrier(cell)<=0.0_real32.OR. &
            .NOT.ieee_is_finite(newcarrier(cell)).OR.newcarrier(cell)<=0.0_real32.OR. &
            .NOT.ieee_is_finite(qb(cell,p)).OR..NOT.ieee_is_finite(nb(cell,p)).OR. &
            .NOT.ieee_is_finite(qs(cell,p)).OR..NOT.ieee_is_finite(ns(cell,p)).OR. &
            .NOT.ieee_is_finite(dt)) THEN
          source_failures=source_failures+1
          WRITE(u,*) 'SOURCE_INVALID_OPERAND',rk,p,i,j,k,oldcarrier(cell),newcarrier(cell), &
              qb(cell,p),nb(cell,p),qs(cell,p),ns(cell,p),drydensity(cell),dt
          CYCLE
        END IF
        ! Inspect the full proposed update separately from the source-only diagnostic.
        source_candidate=(REAL(oldcarrier(cell),real64)* &
          [REAL(qb(cell,p),real64),REAL(nb(cell,p),real64)]+REAL(dt,real64)* &
          [qs64(cell,p)+qa64(cell,p),ns64(cell,p)+na64(cell,p)])/REAL(newcarrier(cell),real64)
        IF (p==1.OR.p==3) THEN
        CALL joint_moment_store(source_candidate(1),source_candidate(2),drydensity(cell), &
             minmass(p),maxmass(p),.TRUE.,full_stored(1),full_stored(2),adjustment,full_valid, &
             allow_normal_q_adjustment=.TRUE.,allow_joint_quantum_absence=.TRUE., &
             volume_number_bounds=number_bounds(cell,:,p))
        ELSE
        CALL joint_moment_store(source_candidate(1),source_candidate(2),drydensity(cell), &
             minmass(p),maxmass(p),.TRUE.,full_stored(1),full_stored(2),adjustment,full_valid, &
             allow_normal_q_adjustment=.TRUE.,allow_joint_quantum_absence=.TRUE., &
             strict_mass_ratio=(p==4), &
             inactive_mass_limit=MERGE(REAL(NEAREST(1.e-14,-1.0),real64),0.0_real64,p==2), &
                 allow_inactive_q_quantum_adjustment=(p==2),failure_stage=pr92_full_store_stage)
        END IF
        IF (.NOT.full_valid) THEN
          IF (p==4) CALL write_pr92_store_failure_capture('FULL',pr92_full_store_stage, &
              cell,i,k,j,source_candidate(1),source_candidate(2),qs64(cell,4),ns64(cell,4), &
              qa64(cell,4),na64(cell,4),drydensity(cell),minmass(4),maxmass(4), &
              oldcarrier(cell),newcarrier(cell),qb(cell,4),nb(cell,4))
          full_failures=full_failures+1
          WRITE(u,*) 'FULL',itimestep,rk,p,i,j,k,oldcarrier(cell),newcarrier(cell), &
              qb(cell,p),nb(cell,p),qs64(cell,p),ns64(cell,p),qa64(cell,p),na64(cell,p), &
              source_candidate,full_stored,drydensity(cell),dt
        END IF
        source_candidate=(REAL(oldcarrier(cell),real64)* &
          [REAL(qb(cell,p),real64),REAL(nb(cell,p),real64)]+REAL(dt,real64)* &
          [qs64(cell,p),ns64(cell,p)])/REAL(newcarrier(cell),real64)
        IF (ANY(.NOT.ieee_is_finite(source_candidate)).OR. &
            ANY(ABS(source_candidate)>REAL(HUGE(0.0_real32),real64))) THEN
          source_failures=source_failures+1
          WRITE(u,*) 'SOURCE_NOT_STORABLE_R32',rk,p,i,j,k,oldcarrier(cell),newcarrier(cell), &
              qb(cell,p),nb(cell,p),qs64(cell,p),ns64(cell,p),source_candidate,drydensity(cell)
          CYCLE
        END IF
        source_stored=REAL(source_candidate,real32)
        IF (p==4) THEN
          CALL joint_moment_store(source_candidate(1),source_candidate(2),drydensity(cell), &
               minmass(p),maxmass(p),.TRUE.,source_check_stored(1),source_check_stored(2), &
               adjustment,source_valid,allow_normal_q_adjustment=.TRUE., &
               allow_joint_quantum_absence=.TRUE.,strict_mass_ratio=.TRUE.)
        ELSE
          source_valid=joint_moment_is_valid(source_stored(1),source_stored(2),drydensity(cell), &
                                           minmass(p),maxmass(p),MERGE(REAL(NEAREST(1.e-14,-1.0),real64),0.0_real64,p==2))
        END IF
        IF (.NOT.source_valid) THEN
          source_failures=source_failures+1
          WRITE(u,*) 'SOURCE',rk,p,i,j,k,oldcarrier(cell),newcarrier(cell), &
              qb(cell,p),nb(cell,p),qs64(cell,p),ns64(cell,p),source_candidate,source_stored,drydensity(cell)
        END IF
      END DO
    END DO
    END DO
    END DO
    WRITE(u,*) 'SOURCE_FAILURE_COUNT',source_failures
    WRITE(u,*) 'FULL_FAILURE_COUNT',full_failures
    CLOSE(u)
    CALL wrf_error_fatal('PR87 full joint moment candidate infeasible; see source/full diagnostics')
  END IF
  IF (theta<=0.0_real64) CALL wrf_error_fatal('PR85 refusing zero common air transport')
  IF (theta/=1.0_real64) &
    CALL wrf_error_fatal('PR85 low-order donor map requires a conservative face limiter')
  IF (ANY(source_first_pair)) CALL write_source_representation()
  ! Additional joint storage rounding is a numerical term, not a physical source.
  ! Signed aggregate deltas have pressure-coordinate units; no kg/energy closure is claimed.
  OPEN(NEWUNIT=u,FILE='pr87_joint_storage.raw',STATUS='UNKNOWN',POSITION='APPEND')
  WRITE(u,*) 'JOINT_STORAGE',itimestep,rk,cells,storage_adjustments
  WRITE(u,*) 'INACTIVE_Q_QUANTUM_ADJUSTMENTS',inactive_q_quantum_adjustments
  WRITE(u,'(A,3(1X,I0),2(1X,ES26.17))') &
    'BULK_VOLUME_ABSENCE',itimestep,rk,bulk_volume_absences,bulk_volume_delta
  WRITE(u,*) 'STORAGE_DELTA_PRESSURE_Q',storage_delta_q
  WRITE(u,*) 'STORAGE_DELTA_PRESSURE_MOMENT',storage_delta_n
  IF (ANY(storage_adjustments>0)) THEN
    cell=0
    DO j=jl,jh
    DO k=kl,kh
    DO i=il,ih
      cell=cell+1
      DO p=1,4
        source_candidate=(REAL(oldcarrier(cell),real64)* &
          [REAL(qb(cell,p),real64),REAL(nb(cell,p),real64)]+REAL(dt,real64)* &
          [qs64(cell,p)+theta*qa64(cell,p),ns64(cell,p)+theta*na64(cell,p)])/REAL(newcarrier(cell),real64)
        source_stored=REAL(source_candidate,real32)
        IF (qc(cell,p)/=source_stored(1).OR.nc(cell,p)/=source_stored(2)) &
          WRITE(u,*) 'STORED_PAIR',itimestep,rk,p,i,j,k,oldcarrier(cell),newcarrier(cell), &
              source_candidate,qc(cell,p),nc(cell,p),drydensity(cell), &
              rdnw(k),msftx(i,j),msfty(i,j),rdx,rdy
      END DO
    END DO
    END DO
    END DO
  END IF
  CLOSE(u)
  ! Commit the complete candidate only after all four pair columns pass.
  cell=0
  DO j=jl,jh
  DO k=kl,kh
  DO i=il,ih
    cell=cell+1
    DO p=1,4
      q2(i,k,j,qindex(p))=qc(cell,p)
      n2(i,k,j,nindex(p))=nc(cell,p)
    END DO
    q2(i,k,j,qsindex)=snow_candidate(cell)
    n2(i,k,j,nnindex)=ccn_candidate(cell)
  END DO
  END DO
  END DO
CONTAINS
  SUBROUTINE evaluate_joint_candidate()
    INTEGER :: pr91_stage(6,4),pr91_adjustment(6,4),pr91_cells(6)
    INTEGER :: pr99_cell,pr99_pair,pr99_predicate,pr99_stage
    REAL(real64) :: pr99_candidate64(2)
    REAL(real32) :: pr99_stored32(2)
    INTEGER :: pr91_target_i(6),pr91_target_j(6),pr91_target_k(6),c,i,j,k,t
    REAL(real64) :: pr91_scale(6,4)
    REAL(real64) :: pr91_candidate(6,2,4)
    REAL(real32) :: pr91_stored(6,2,4)
    pr91_target_i=[130,194,132,196,168,231]
    pr91_target_j=[182,80,201,211,225,240]
    pr91_target_k=[2,22,19,16,20,20]
    pr91_cells=0; c=0
    DO j=jl,jh
    DO k=kl,kh
    DO i=il,ih
      c=c+1
      DO t=1,6
        IF (i==pr91_target_i(t).AND.j==pr91_target_j(t).AND.k==pr91_target_k(t)) &
          pr91_cells(t)=c
      END DO
    END DO
    END DO
    END DO
    CALL joint_qnb_update(qb,nb,qc,nc,qs,ns,qa,na,oldcarrier,newcarrier,drydensity, &
                         dt,minmass,maxmass,theta,rejected_q,rejected_n,feasible, &
                         joint_constrained_storage=.TRUE.,storage_delta_q=storage_delta_q, &
                         storage_delta_n=storage_delta_n,storage_adjustments=storage_adjustments, &
                         q_source_rate64=qs64,n_source_rate64=ns64, &
                         q_transport_rate64=qa64,n_transport_rate64=na64,joint_quantum_absence=.TRUE., &
                         number_pair_bounds=number_bounds, &
                         strict_mass_pairs=[.FALSE.,.FALSE.,.FALSE.,.TRUE.], &
                         inactive_mass_limits=[0.0_real64,REAL(NEAREST(1.e-14,-1.0),real64), &
                         0.0_real64,0.0_real64], &
                         inactive_q_quantum_adjustment_pairs=[.FALSE.,.TRUE.,.FALSE.,.FALSE.], &
                         inactive_q_quantum_adjustments=inactive_q_quantum_adjustments, &
                         bulk_volume_quantum_storage=.TRUE., &
                         bulk_volume_absences=bulk_volume_absences, &
                         bulk_volume_delta=bulk_volume_delta, &
                         diagnostic_stage=pr91_stage, diagnostic_candidate=pr91_candidate, &
                         diagnostic_stored=pr91_stored, diagnostic_adjustment=pr91_adjustment, &
                         diagnostic_scale=pr91_scale, diagnostic_cells=pr91_cells, &
                         group_failure_cell=pr99_cell, group_failure_pair=pr99_pair, &
                         group_failure_predicate=pr99_predicate, &
                         group_failure_store_stage=pr99_stage, &
                         group_failure_candidate64=pr99_candidate64, &
                         group_failure_stored32=pr99_stored32, &
                         group_failure_enabled=itimestep==32)
    IF (.NOT.feasible .AND. itimestep==32 .AND. pr99_cell>0) &
      CALL write_pr99_group_failure(pr99_cell,pr99_pair,pr99_predicate,pr99_stage, &
        pr99_candidate64,pr99_stored32,ANY(source_first_pair))
    IF (.NOT.feasible) CALL write_pr91_actual_store_failures( &
      pr91_stage,pr91_candidate,pr91_stored,pr91_adjustment,pr91_scale, &
      pr91_cells,pr91_target_i,pr91_target_j,pr91_target_k)
    IF (.NOT.feasible) CALL try_graupel_mixture_trial()
    IF (itimestep==32 .AND. pr99_cell>0) &
      CALL write_pr99_group_retry_result(pr99_cell,pr99_pair,pr99_predicate,feasible)
  END SUBROUTINE evaluate_joint_candidate

  SUBROUTINE write_pr91_actual_store_failures(pr91_stage,pr91_candidate,pr91_stored, &
      pr91_adjustment,pr91_scale,pr91_cells,pr91_target_i,pr91_target_j,pr91_target_k)
    INTEGER,INTENT(IN) :: pr91_stage(6,4),pr91_adjustment(6,4),pr91_cells(6)
    INTEGER,INTENT(IN) :: pr91_target_i(6),pr91_target_j(6),pr91_target_k(6)
    REAL(real64),INTENT(IN) :: pr91_candidate(6,2,4),pr91_scale(6,4)
    REAL(real32),INTENT(IN) :: pr91_stored(6,2,4)
    CHARACTER(LEN=64) :: run_id
    INTEGER :: u,ios,c,i,k,j,p,t
    OPEN(NEWUNIT=u,FILE='pr91_actual_store_failures.raw',STATUS='UNKNOWN', &
         POSITION='APPEND',ACTION='WRITE',IOSTAT=ios)
    IF (ios/=0) CALL wrf_error_fatal('PR91 trace open failed')
    CALL get_environment_variable('PR91_RUN_ID',run_id,STATUS=ios)
    IF (ios/=0.OR.LEN_TRIM(run_id)==0) CALL wrf_error_fatal('PR91_RUN_ID is required')
    WRITE(u,*) 'PR91_HOST_STORE_TRACE_V1',TRIM(run_id)
    WRITE(u,*) 'META: attempt_id,timestep,rk,pair,i,j,k,attempted_scale,dt'
    WRITE(u,*) 'R64: carriers,base,source,transport,candidate,density,mass_bounds,number_bounds,stored'
    WRITE(u,*) 'HEX64: candidate,source,transport,mass_bounds,number_bounds'
    WRITE(u,*) 'HEX32: stored,density,carriers,base,dt; tail:failure_stage,adjustment'
    WRITE(u,*) 'OPTIONS: run_id,attempt,timestep,rk,pair,i,j,k,subnormal,normal_adjust'
    WRITE(u,*) 'OPTIONS2: quantum_absence,strict_mass,inactive_limit,volume_bounds'
    WRITE(u,*) 'OPTIONS3: number_pair_bounds,strict_number_pair,inactive_value'
    DO t=1,6
      c=pr91_cells(t)
      IF (c<=0) CYCLE
      i=pr91_target_i(t); j=pr91_target_j(t); k=pr91_target_k(t)
      DO p=1,4
        IF (pr91_stage(t,p)<=0) CYCLE
        WRITE(u,'(a,1x,a,7i10,1p,19es26.17,10(1x,z16.16),8(1x,z8.8),2i6)') &
          'ACTUAL_STORE_FAILURE',TRIM(run_id),MERGE(1,0,ANY(source_first_pair)), &
          itimestep,rk,p,i,j,k,pr91_scale(t,p),dt,oldcarrier(c),newcarrier(c), &
          qb(c,p),nb(c,p),qs64(c,p),ns64(c,p),qa64(c,p),na64(c,p), &
          pr91_candidate(t,1,p),pr91_candidate(t,2,p),drydensity(c),minmass(p),maxmass(p), &
          number_bounds(c,1,p),number_bounds(c,2,p),pr91_stored(t,1,p),pr91_stored(t,2,p), &
          TRANSFER(pr91_candidate(t,1,p),0_8),TRANSFER(pr91_candidate(t,2,p),0_8), &
          TRANSFER(qs64(c,p),0_8),TRANSFER(ns64(c,p),0_8), &
          TRANSFER(qa64(c,p),0_8),TRANSFER(na64(c,p),0_8), &
          TRANSFER(minmass(p),0_8),TRANSFER(maxmass(p),0_8), &
          TRANSFER(number_bounds(c,1,p),0_8),TRANSFER(number_bounds(c,2,p),0_8), &
          TRANSFER(pr91_stored(t,1,p),0_4),TRANSFER(pr91_stored(t,2,p),0_4), &
          TRANSFER(drydensity(c),0_4),TRANSFER(oldcarrier(c),0_4),TRANSFER(newcarrier(c),0_4), &
          TRANSFER(qb(c,p),0_4),TRANSFER(nb(c,p),0_4),TRANSFER(dt,0_4), &
          pr91_stage(t,p),pr91_adjustment(t,p)
        WRITE(u,'(A,1X,A,1X,A,6(1X,I0),8(1X,L1),1X,ES26.17)') &
          'ACTUAL_STORE_OPTIONS',TRIM(run_id), &
          MERGE('SOURCE_FIRST_FALLBACK','BASELINE             ',ANY(source_first_pair)), &
          itimestep,rk,p,i,j,k,.TRUE.,.TRUE.,.TRUE.,p==4,p==2, &
          (p==1.OR.p==3).AND.ANY(number_bounds(c,:,p)/=0.0_real64),.TRUE.,.FALSE., &
          MERGE(REAL(NEAREST(1.e-14,-1.0),real64),0.0_real64,p==2)
      END DO
    END DO
    CLOSE(u)
  END SUBROUTINE write_pr91_actual_store_failures

  SUBROUTINE write_pr99_group_failure(cell,pair,predicate,store_stage,candidate64,stored32,source_first)
    INTEGER,INTENT(IN) :: cell,pair,predicate,store_stage
    LOGICAL,INTENT(IN) :: source_first
    REAL(real64),INTENT(IN) :: candidate64(2)
    REAL(real32),INTENT(IN) :: stored32(2)
    CHARACTER(LEN=64) :: run_id
    INTEGER :: u,c,i,j,k,env_status
    c=0; i=0; j=0; k=0
    DO j=jl,jh; DO k=kl,kh; DO i=il,ih
      c=c+1; IF (c==cell) EXIT
    END DO; IF (c==cell) EXIT; END DO; IF (c==cell) EXIT; END DO
    CALL GET_ENVIRONMENT_VARIABLE('PR91_RUN_ID',run_id,STATUS=env_status)
    IF (env_status/=0.OR.LEN_TRIM(run_id)==0) CALL wrf_error_fatal('PR99 run id missing')
    OPEN(NEWUNIT=u,FILE='pr99_group_failure.raw',STATUS='UNKNOWN',POSITION='APPEND')
    WRITE(u,*) 'PR99_GROUP_FAILURE_V1',TRIM(run_id),MERGE('SOURCE_FIRST','BASELINE    ',source_first), &
      itimestep,rk,cell,pair,i,j,k,predicate,store_stage,store_stage==0
    WRITE(u,*) 'R64_CANDIDATE',candidate64
    WRITE(u,*) 'R32_STORED',stored32
    WRITE(u,*) 'R32_CARRIERS',oldcarrier(cell),newcarrier(cell),drydensity(cell),dt
    WRITE(u,*) 'R32_BASE',qb(cell,pair),nb(cell,pair)
    WRITE(u,*) 'R64_SOURCE_RATE',qs64(cell,pair),ns64(cell,pair)
    WRITE(u,*) 'R64_TRANSPORT_RATE',qa64(cell,pair),na64(cell,pair)
    WRITE(u,*) 'R64_MASS_BOUNDS',minmass(pair),maxmass(pair)
    WRITE(u,*) 'R64_NUMBER_BOUNDS',number_bounds(cell,:,pair)
    WRITE(u,*) 'CELLS_AND_PAIRS',SIZE(qb,1),SIZE(qb,2)
    WRITE(u,*) 'OPT_joint_constrained_storage',.TRUE.
    WRITE(u,*) 'OPT_joint_quantum_absence',.TRUE.
    WRITE(u,*) 'OPT_normal_q_adjustment',.TRUE.
    WRITE(u,*) 'OPT_strict_mass_pair',pair==4
    WRITE(u,*) 'OPT_inactive_mass_pair',pair==2
    WRITE(u,*) 'OPT_inactive_q_quantum_pair',pair==2
    WRITE(u,*) 'OPT_bulk_volume_quantum_storage',.TRUE.
    WRITE(u,*) 'OPT_number_pair_bounds',.TRUE.
    WRITE(u,*) 'OPT_source_first_fallback',source_first
    WRITE(u,*) 'R64_INACTIVE_MASS_LIMIT', &
      MERGE(REAL(NEAREST(1.e-14,-1.0),real64),0.0_real64,pair==2)
    WRITE(u,'(A,Z16.16)') 'HEX64_INACTIVE_MASS_LIMIT ', &
      TRANSFER(MERGE(REAL(NEAREST(1.e-14,-1.0),real64),0.0_real64,pair==2),0_int64)
    WRITE(u,'(A,2(1X,Z16.16))') 'HEX64_CANDIDATE',TRANSFER(candidate64,0_int64,2)
    WRITE(u,'(A,2(1X,Z8.8))') 'HEX32_STORED',TRANSFER(stored32,0_int32,2)
    WRITE(u,'(A,4(1X,Z8.8))') 'HEX32_CARRIERS_DT', &
      TRANSFER(oldcarrier(cell),0_int32),TRANSFER(newcarrier(cell),0_int32), &
      TRANSFER(drydensity(cell),0_int32),TRANSFER(dt,0_int32)
    WRITE(u,'(A,2(1X,Z8.8))') 'HEX32_BASE',TRANSFER(qb(cell,pair),0_int32), &
      TRANSFER(nb(cell,pair),0_int32)
    WRITE(u,'(A,2(1X,Z16.16))') 'HEX64_SOURCE_RATE',TRANSFER(qs64(cell,pair),0_int64), &
      TRANSFER(ns64(cell,pair),0_int64)
    WRITE(u,'(A,2(1X,Z16.16))') 'HEX64_TRANSPORT_RATE',TRANSFER(qa64(cell,pair),0_int64), &
      TRANSFER(na64(cell,pair),0_int64)
    WRITE(u,'(A,2(1X,Z16.16))') 'HEX64_MASS_BOUNDS',TRANSFER(minmass(pair),0_int64), &
      TRANSFER(maxmass(pair),0_int64)
    WRITE(u,'(A,2(1X,Z16.16))') 'HEX64_NUMBER_BOUNDS', &
      TRANSFER(number_bounds(cell,1,pair),0_int64), &
      TRANSFER(number_bounds(cell,2,pair),0_int64)
    CLOSE(u)
  END SUBROUTINE write_pr99_group_failure

  SUBROUTINE write_pr99_group_retry_result(cell,pair,predicate,retry_feasible)
    INTEGER,INTENT(IN) :: cell,pair,predicate
    LOGICAL,INTENT(IN) :: retry_feasible
    CHARACTER(LEN=64) :: run_id
    INTEGER :: u,env_status
    CALL GET_ENVIRONMENT_VARIABLE('PR91_RUN_ID',run_id,STATUS=env_status)
    IF (env_status/=0.OR.LEN_TRIM(run_id)==0) CALL wrf_error_fatal('PR99 run id missing')
    OPEN(NEWUNIT=u,FILE='pr99_group_failure.raw',STATUS='OLD',POSITION='APPEND')
    WRITE(u,*) 'PR99_GROUP_POST_RETRY_V1',TRIM(run_id),itimestep,rk,cell,pair,predicate,retry_feasible
    CLOSE(u)
  END SUBROUTINE write_pr99_group_retry_result

  SUBROUTINE try_graupel_mixture_trial()
    REAL(real32),ALLOCATABLE :: q_trial(:,:),n_trial(:,:)
    REAL(real64) :: trial_delta_q(4),trial_delta_n(4)
    INTEGER :: trial_adjustments(4),fallback_count,witness_i,witness_j,witness_k,tiny_bg_count
    INTEGER :: trial_inactive_q_quantum_adjustments(4),trial_bulk_volume_absences
    REAL(real64) :: trial_bulk_volume_delta(2)
    INTEGER :: tiny_bg_i,tiny_bg_j,tiny_bg_k
    INTEGER :: reject_reason,reject_pair,reject_i,reject_j,reject_k
    INTEGER(int32) :: witness_q32,witness_n32
    INTEGER(int64) :: witness_q64,witness_n64,reject_bits(6),tiny_bg_bits,tiny_bg_rho_bits
    LOGICAL :: witness_canonical_valid,witness_stored_valid,valid
    ALLOCATE(q_trial(cells,4),n_trial(cells,4))
    q_trial=qc; n_trial=nc
    trial_delta_q=0.0_real64; trial_delta_n=0.0_real64; trial_adjustments=0
    trial_inactive_q_quantum_adjustments=0
    trial_bulk_volume_absences=0; trial_bulk_volume_delta=0.0_real64
    CALL certify_graupel_storage(q_trial,n_trial,trial_delta_q,trial_delta_n, &
                                 trial_adjustments,valid,fallback_count,witness_i,witness_j,witness_k, &
                                 witness_q64,witness_n64,witness_q32,witness_n32, &
                                 witness_canonical_valid,witness_stored_valid, &
                                 reject_reason,reject_pair,reject_i,reject_j,reject_k,reject_bits, &
                                 tiny_bg_count,tiny_bg_i,tiny_bg_j,tiny_bg_k,tiny_bg_bits,tiny_bg_rho_bits, &
                                 inactive_q_quantum_adjustments= &
                                     trial_inactive_q_quantum_adjustments, &
                                 allow_bulk_absence=.TRUE., &
                                 bulk_absences=trial_bulk_volume_absences, &
                                 bulk_delta=trial_bulk_volume_delta)
    IF (.NOT.valid) THEN
      feasible=.FALSE.; theta=0.0_real64; rejected_q=0.0_real64; rejected_n=0.0_real64
      IF (reject_reason>0) WRITE(*,'(A,7(1X,I0))') &
        'PR91_GRAUPEL_TRIAL_REJECT_CONTEXT',itimestep,rk,reject_reason,reject_pair, &
        reject_i,reject_j,reject_k
      IF (reject_reason>0) WRITE(*,'(A,5(1X,I0),6(1X,Z16.16))') &
        'PR87_GRAUPEL_TRIAL_REJECT',reject_reason,reject_pair,reject_i,reject_j,reject_k,reject_bits
      DEALLOCATE(q_trial,n_trial); RETURN
    END IF
    qc=q_trial; nc=n_trial
    storage_delta_q=trial_delta_q; storage_delta_n=trial_delta_n
    storage_adjustments=trial_adjustments
    inactive_q_quantum_adjustments=trial_inactive_q_quantum_adjustments
    bulk_volume_absences=trial_bulk_volume_absences
    bulk_volume_delta=trial_bulk_volume_delta
    theta=1.0_real64; rejected_q=0.0_real64; rejected_n=0.0_real64
    feasible=.TRUE.
    IF (fallback_count>0) WRITE(*,'(A,6(1X,I0),2(1X,Z16.16),2(1X,Z8.8),2(1X,L1))') &
      'PR87_GRAUPEL_MIXTURE',itimestep,rk,fallback_count,witness_i,witness_j,witness_k, &
      witness_q64,witness_n64,witness_q32,witness_n32,witness_canonical_valid,witness_stored_valid
    IF (tiny_bg_count>0) WRITE(*,'(A,6(1X,I0),2(1X,Z16.16))') &
      'PR87_GRAUPEL_TINY_BG_ROLE',itimestep,rk,tiny_bg_count,tiny_bg_i,tiny_bg_j,tiny_bg_k, &
      tiny_bg_bits,tiny_bg_rho_bits
    DEALLOCATE(q_trial,n_trial)
  END SUBROUTINE try_graupel_mixture_trial

  SUBROUTINE probe_failed_graupel_pair()
    REAL(real32),ALLOCATABLE :: q_probe(:,:),n_probe(:,:)
    REAL(real64) :: probe_delta_q(4),probe_delta_n(4)
    INTEGER :: probe_adjustments(4),fallback_count,witness_i,witness_j,witness_k,tiny_bg_count
    INTEGER :: probe_bulk_absences
    REAL(real64) :: probe_bulk_delta(2)
    INTEGER :: tiny_bg_i,tiny_bg_j,tiny_bg_k
    INTEGER :: reject_reason,reject_pair,reject_i,reject_j,reject_k
    INTEGER(int32) :: witness_q32,witness_n32
    INTEGER(int64) :: witness_q64,witness_n64,reject_bits(6),tiny_bg_bits,tiny_bg_rho_bits
    LOGICAL :: witness_canonical_valid,witness_stored_valid,valid
    CHARACTER(LEN=64) :: pr91_run_id
    INTEGER :: pr91_env_status
    IF (.NOT.failed_pairs(4)) RETURN
    ALLOCATE(q_probe(cells,4),n_probe(cells,4))
    q_probe=qc; n_probe=nc
    probe_delta_q=0.0_real64; probe_delta_n=0.0_real64; probe_adjustments=0
    CALL certify_graupel_storage(q_probe,n_probe,probe_delta_q,probe_delta_n,probe_adjustments, &
        valid,fallback_count,witness_i,witness_j,witness_k,witness_q64,witness_n64, &
        witness_q32,witness_n32,witness_canonical_valid,witness_stored_valid, &
        reject_reason,reject_pair,reject_i,reject_j,reject_k,reject_bits, &
        tiny_bg_count,tiny_bg_i,tiny_bg_j,tiny_bg_k,tiny_bg_bits,tiny_bg_rho_bits,.TRUE., &
        allow_bulk_absence=.TRUE.,bulk_absences=probe_bulk_absences, &
        bulk_delta=probe_bulk_delta)
    IF (.NOT.valid.AND.reject_reason>0) THEN
      CALL get_environment_variable('PR91_RUN_ID',pr91_run_id,STATUS=pr91_env_status)
      IF (pr91_env_status/=0.OR.LEN_TRIM(pr91_run_id)==0) &
        CALL wrf_error_fatal('PR91_RUN_ID is required for probe trace')
      WRITE(*,'(A,1X,A,7(1X,I0),6(1X,Z16.16))') 'PROBE_GRAUPEL_REJECT', &
        TRIM(pr91_run_id),itimestep,rk,reject_reason,reject_pair,reject_i,reject_j,reject_k,reject_bits
    END IF
    IF (valid) failed_pairs(4)=.FALSE.
    DEALLOCATE(q_probe,n_probe)
  END SUBROUTINE probe_failed_graupel_pair

  SUBROUTINE certify_graupel_storage(q_trial,n_trial,delta_q_by_pair,delta_n_by_pair, &
      adjustments_by_pair,valid,fallback_count,witness_i,witness_j,witness_k, &
      witness_q64,witness_n64,witness_q32,witness_n32,witness_canonical_valid,witness_stored_valid, &
      reject_reason,reject_pair,reject_i,reject_j,reject_k,reject_bits, &
      tiny_bg_count,tiny_bg_i,tiny_bg_j,tiny_bg_k,tiny_bg_bits,tiny_bg_rho_bits,graupel_only, &
      inactive_q_quantum_adjustments,allow_bulk_absence,bulk_absences,bulk_delta)
    REAL(real32),INTENT(INOUT) :: q_trial(cells,4),n_trial(cells,4)
    REAL(real64),INTENT(INOUT) :: delta_q_by_pair(4),delta_n_by_pair(4)
    INTEGER,INTENT(INOUT) :: adjustments_by_pair(4)
    INTEGER,INTENT(OUT) :: fallback_count,witness_i,witness_j,witness_k
    INTEGER,INTENT(OUT) :: reject_reason,reject_pair,reject_i,reject_j,reject_k
    INTEGER,INTENT(OUT) :: tiny_bg_count,tiny_bg_i,tiny_bg_j,tiny_bg_k
    INTEGER(int32),INTENT(OUT) :: witness_q32,witness_n32
    INTEGER(int64),INTENT(OUT) :: witness_q64,witness_n64,reject_bits(6)
    INTEGER(int64),INTENT(OUT) :: tiny_bg_bits,tiny_bg_rho_bits
    LOGICAL,INTENT(OUT) :: witness_canonical_valid,witness_stored_valid,valid
    LOGICAL,INTENT(IN),OPTIONAL :: graupel_only
    INTEGER,INTENT(OUT),OPTIONAL :: inactive_q_quantum_adjustments(4)
    LOGICAL,INTENT(IN),OPTIONAL :: allow_bulk_absence
    INTEGER,INTENT(OUT),OPTIONAL :: bulk_absences
    REAL(real64),INTENT(OUT),OPTIONAL :: bulk_delta(2)
    LOGICAL :: use_bulk_absence
    INTEGER :: c,i,k,j,p,adjustment,first_pair,last_pair
    INTEGER :: pr92_store_failure_stage
    REAL(real64) :: value_q,value_n,weights(7),delta_q,delta_n,replay_rates(2)
    REAL(real32) :: q_terms(7),n_terms(7),stored_q,stored_n
    REAL(real64) :: minimum_positive32
    LOGICAL :: store_valid,mixture_valid,fallback_used
    delta_q_by_pair=0.0_real64; delta_n_by_pair=0.0_real64
    adjustments_by_pair=0
    IF (PRESENT(inactive_q_quantum_adjustments)) inactive_q_quantum_adjustments=0
    IF (PRESENT(bulk_absences)) bulk_absences=0
    IF (PRESENT(bulk_delta)) bulk_delta=0.0_real64
    use_bulk_absence=.FALSE.
    IF (PRESENT(allow_bulk_absence)) use_bulk_absence=allow_bulk_absence
    fallback_count=0; witness_i=0; witness_j=0; witness_k=0
    witness_q64=0_int64; witness_n64=0_int64; witness_q32=0_int32; witness_n32=0_int32
    witness_canonical_valid=.FALSE.; witness_stored_valid=.FALSE.
    reject_reason=0; reject_pair=0; reject_i=0; reject_j=0; reject_k=0; reject_bits=0_int64
    tiny_bg_count=0; tiny_bg_i=0; tiny_bg_j=0; tiny_bg_k=0
    tiny_bg_bits=0_int64; tiny_bg_rho_bits=0_int64
    first_pair=1; last_pair=4
    IF (PRESENT(graupel_only)) THEN
      IF (graupel_only) first_pair=4
    END IF
    minimum_positive32=REAL(NEAREST(0.0_real32,1.0_real32),real64)
    valid=.FALSE.
    IF (use_bulk_absence.AND.(.NOT.PRESENT(bulk_absences).OR. &
        .NOT.PRESENT(bulk_delta))) RETURN
    DO p=first_pair,last_pair
      c=0
      DO j=jl,jh
        DO k=kl,kh
          DO i=il,ih
            c=c+1
            value_q=(REAL(oldcarrier(c),real64)*REAL(qb(c,p),real64)+ &
                REAL(dt,real64)*(qs64(c,p)+qa64(c,p)))/REAL(newcarrier(c),real64)
            value_n=(REAL(oldcarrier(c),real64)*REAL(nb(c,p),real64)+ &
                REAL(dt,real64)*(ns64(c,p)+na64(c,p)))/REAL(newcarrier(c),real64)
            delta_q=0.0_real64; delta_n=0.0_real64; adjustment=0; fallback_used=.FALSE.
            IF (p==1.OR.p==3) THEN
              IF (ANY(number_bounds(c,:,p)/=0.0_real64)) THEN
                CALL joint_moment_store(value_q,value_n,drydensity(c),minmass(p),maxmass(p), &
                    .TRUE.,stored_q,stored_n,adjustment,store_valid, &
                    allow_normal_q_adjustment=.TRUE.,allow_joint_quantum_absence=.TRUE., &
                    volume_number_bounds=number_bounds(c,:,p))
              ELSE
                CALL joint_moment_store(value_q,value_n,drydensity(c),minmass(p),maxmass(p), &
                    .TRUE.,stored_q,stored_n,adjustment,store_valid, &
                    allow_normal_q_adjustment=.TRUE.,allow_joint_quantum_absence=.TRUE.)
              END IF
            ELSE IF (p==4) THEN
              CALL joint_moment_store(value_q,value_n,drydensity(c),minmass(p),maxmass(p), &
                  .TRUE.,stored_q,stored_n,adjustment,store_valid, &
                  allow_normal_q_adjustment=.TRUE.,allow_joint_quantum_absence=.TRUE., &
                  strict_mass_ratio=.TRUE.,failure_stage=pr92_store_failure_stage, &
                  allow_bulk_volume_quantum_storage=use_bulk_absence)
              IF (.NOT.store_valid.AND.use_bulk_absence) THEN
                IF (joint_bulk_candidate_absence_is_valid(qb(c,4),nb(c,4), &
                    oldcarrier(c),newcarrier(c),dt,drydensity(c),qs64(c,4),ns64(c,4), &
                    qa64(c,4),na64(c,4),1.0_real64,minmass(4),maxmass(4),value_q,value_n)) THEN
                  stored_q=0.0_real32; stored_n=0.0_real32
                  adjustment=5; store_valid=.TRUE.
                END IF
              END IF
              IF (store_valid.AND.value_n>0.0_real64) THEN
                IF (REAL(drydensity(c),real64)*value_n<=0.5_real64*minimum_positive32) THEN
                  tiny_bg_count=tiny_bg_count+1
                  IF (tiny_bg_count==1) THEN
                    tiny_bg_i=i; tiny_bg_j=j; tiny_bg_k=k
                    tiny_bg_bits=TRANSFER(value_n,tiny_bg_bits)
                    tiny_bg_rho_bits=TRANSFER(drydensity(c),tiny_bg_rho_bits)
                  END IF
                END IF
              END IF
            ELSE
              CALL joint_moment_store(value_q,value_n,drydensity(c),minmass(p),maxmass(p), &
                  .TRUE.,stored_q,stored_n,adjustment,store_valid, &
                  allow_normal_q_adjustment=.TRUE.,allow_joint_quantum_absence=.TRUE., &
                  inactive_mass_limit=REAL(NEAREST(1.e-14,-1.0),real64), &
                  allow_inactive_q_quantum_adjustment=(p==2))
            END IF
            IF (store_valid.AND.PRESENT(inactive_q_quantum_adjustments).AND.adjustment==4) &
              inactive_q_quantum_adjustments(p)=inactive_q_quantum_adjustments(p)+1
            IF (.NOT.store_valid) THEN
              IF (p==4) THEN
                CALL write_pr92_store_failure_capture('CERTIFIER',pr92_store_failure_stage,c,i,k,j, &
                    value_q,value_n,qs64(c,4),ns64(c,4),qa64(c,4),na64(c,4), &
                    drydensity(c),minmass(4),maxmass(4),oldcarrier(c),newcarrier(c), &
                    qb(c,4),nb(c,4))
              END IF
              IF (p/=4) THEN
                reject_reason=1
                reject_bits=[TRANSFER(value_q,0_int64),TRANSFER(value_n,0_int64), &
                    TRANSFER(qs64(c,p),0_int64),TRANSFER(ns64(c,p),0_int64), &
                    TRANSFER(qa64(c,p),0_int64),TRANSFER(na64(c,p),0_int64)]
                reject_pair=p; reject_i=i; reject_j=j; reject_k=k
                RETURN
              END IF
              replay_rates=air_tendency(q1(:,:,:,qindex(4)),n1(:,:,:,nindex(4)),i,k,j,4)
              IF (TRANSFER(qb(c,4),0_int32)/=TRANSFER(q1(i,k,j,qindex(4)),0_int32).OR. &
                  TRANSFER(nb(c,4),0_int32)/=TRANSFER(n1(i,k,j,nindex(4)),0_int32).OR. &
                  TRANSFER(qa64(c,4),0_int64)/=TRANSFER(replay_rates(1),0_int64).OR. &
                  TRANSFER(na64(c,4),0_int64)/=TRANSFER(replay_rates(2),0_int64)) THEN
                reject_reason=5
                reject_bits=[TRANSFER(value_q,0_int64),TRANSFER(value_n,0_int64), &
                    TRANSFER(qa64(c,4),0_int64),TRANSFER(na64(c,4),0_int64), &
                    TRANSFER(replay_rates(1),0_int64),TRANSFER(replay_rates(2),0_int64)]
                reject_pair=p; reject_i=i; reject_j=j; reject_k=k
                RETURN
              END IF
              CALL graupel_transport_mixture(c,i,k,j,weights,q_terms,n_terms,mixture_valid)
              IF (.NOT.mixture_valid) THEN
                reject_reason=3
                reject_bits=[TRANSFER(value_q,0_int64),TRANSFER(value_n,0_int64), &
                    TRANSFER(qs64(c,p),0_int64),TRANSFER(ns64(c,p),0_int64), &
                    TRANSFER(qa64(c,p),0_int64),TRANSFER(na64(c,p),0_int64)]
                reject_pair=p; reject_i=i; reject_j=j; reject_k=k
                RETURN
              END IF
              CALL add_graupel_diffusion_mixture(c,i,k,j,weights,q_terms,n_terms,mixture_valid)
              IF (.NOT.mixture_valid) THEN
                reject_reason=6
                reject_bits=[TRANSFER(value_q,0_int64),TRANSFER(value_n,0_int64), &
                    TRANSFER(qs64(c,p),0_int64),TRANSFER(ns64(c,p),0_int64), &
                    TRANSFER(qa64(c,p),0_int64),TRANSFER(na64(c,p),0_int64)]
                reject_pair=p; reject_i=i; reject_j=j; reject_k=k
                RETURN
              END IF
              CALL store_graupel_mixture(weights,q_terms,n_terms,newcarrier(c),minmass(4), &
                  maxmass(4),value_q,value_n,stored_q,stored_n,delta_q,delta_n,mixture_valid)
              IF (.NOT.mixture_valid) THEN
                reject_reason=4
                reject_bits=[TRANSFER(value_q,0_int64),TRANSFER(value_n,0_int64), &
                    TRANSFER(qs64(c,p),0_int64),TRANSFER(ns64(c,p),0_int64), &
                    TRANSFER(qa64(c,p),0_int64),TRANSFER(na64(c,p),0_int64)]
                reject_pair=p; reject_i=i; reject_j=j; reject_k=k
                CALL write_pr91_mixture_store_reject(itimestep,rk,p,i,k,j,c,dt,newcarrier(c), &
                    weights,q_terms,n_terms)
                RETURN
              END IF
              IF (itimestep==15) CALL write_pr92_valid_mixture(c,i,k,j,weights, &
                  q_terms,n_terms,value_q,value_n,stored_q,stored_n,delta_q,delta_n)
              fallback_used=.TRUE.; fallback_count=fallback_count+1; adjustment=1
              IF (fallback_count==1) THEN
                witness_i=i; witness_j=j; witness_k=k
                witness_q64=TRANSFER(value_q,witness_q64)
                witness_n64=TRANSFER(value_n,witness_n64)
                witness_q32=TRANSFER(stored_q,witness_q32)
                witness_n32=TRANSFER(stored_n,witness_n32)
                witness_canonical_valid=strict_graupel_pair(value_q,value_n,minmass(4),maxmass(4))
                witness_stored_valid=strict_graupel_pair(REAL(stored_q,real64), &
                    REAL(stored_n,real64),minmass(4),maxmass(4))
              END IF
            ELSE IF (adjustment/=0) THEN
              delta_q=REAL(newcarrier(c),real64)*(REAL(stored_q,real64)-value_q)
              delta_n=REAL(newcarrier(c),real64)*(REAL(stored_n,real64)-value_n)
            END IF
            IF (use_bulk_absence.AND.p==4.AND.adjustment==5) THEN
              bulk_absences=bulk_absences+1
              bulk_delta=bulk_delta+[delta_q,delta_n]
            END IF
            q_trial(c,p)=stored_q; n_trial(c,p)=stored_n
            delta_q_by_pair(p)=delta_q_by_pair(p)+delta_q
            delta_n_by_pair(p)=delta_n_by_pair(p)+delta_n
            IF (fallback_used.OR.adjustment/=0) adjustments_by_pair(p)=adjustments_by_pair(p)+1
          END DO
        END DO
      END DO
    END DO
    valid=.TRUE.
  END SUBROUTINE certify_graupel_storage

  SUBROUTINE write_pr92_valid_mixture(c,i,k,j,weights,q_terms,b_terms, &
      candidate_q,candidate_b,stored_q,stored_b,delta_q,delta_b)
    INTEGER,INTENT(IN) :: c,i,k,j
    REAL(real64),INTENT(IN) :: weights(7),candidate_q,candidate_b,delta_q,delta_b
    REAL(real32),INTENT(IN) :: q_terms(7),b_terms(7),stored_q,stored_b
    INTEGER :: u
    INTEGER,PARAMETER :: targets(3,12)=RESHAPE([ &
        127,5,22, &
        170,42,23, &
        171,43,23, &
        163,44,20, &
        158,47,20, &
        232,203,20, &
        203,213,21, &
        11,216,21, &
        2,218,13, &
        22,228,21, &
        41,229,14, &
        43,239,19], [3,12])
    ! Coordinate selection bounds diagnostic I/O only; it never changes a trial.
    IF (itimestep/=15.OR.rk/=1) RETURN
    IF (.NOT.ANY(targets(1,:)==i.AND.targets(2,:)==j.AND.targets(3,:)==k)) RETURN
    ! This witnesses a valid local trial, not its later transaction commit.
    OPEN(NEWUNIT=u,FILE='pr92_valid_mixture.raw',STATUS='UNKNOWN',POSITION='APPEND')
    WRITE(u,'(A,7(1X,I0))') 'PR92_MIXTURE_TRIAL',itimestep,rk,i,j,k,c, &
        MERGE(1,0,ANY(source_first_pair))
    WRITE(u,'(A,7(1X,Z16.16))') 'PR92_MIXTURE_WEIGHTS64',TRANSFER(weights,0_int64,7)
    WRITE(u,'(A,14(1X,Z8.8))') 'PR92_MIXTURE_TERMS32', &
        TRANSFER(q_terms,0_int32,7),TRANSFER(b_terms,0_int32,7)
    WRITE(u,'(A,11(1X,Z16.16))') 'PR92_MIXTURE_VALUES64', &
        TRANSFER(candidate_q,0_int64),TRANSFER(candidate_b,0_int64), &
        TRANSFER(delta_q,0_int64),TRANSFER(delta_b,0_int64), &
        TRANSFER(qs64(c,4),0_int64),TRANSFER(ns64(c,4),0_int64), &
        TRANSFER(qa64(c,4),0_int64),TRANSFER(na64(c,4),0_int64), &
        TRANSFER(minmass(4),0_int64),TRANSFER(maxmass(4),0_int64), &
        TRANSFER(REAL(newcarrier(c),real64),0_int64)
    WRITE(u,'(A,8(1X,Z8.8))') 'PR92_MIXTURE_VALUES32', &
        TRANSFER(stored_q,0_int32),TRANSFER(stored_b,0_int32), &
        TRANSFER(dt,0_int32),TRANSFER(oldcarrier(c),0_int32),TRANSFER(newcarrier(c),0_int32), &
        TRANSFER(drydensity(c),0_int32),TRANSFER(qb(c,4),0_int32),TRANSFER(nb(c,4),0_int32)
    WRITE(u,'(A)') 'PR92_MIXTURE_END'
    CLOSE(u)
  END SUBROUTINE write_pr92_valid_mixture

  SUBROUTINE write_pr92_store_failure_capture(context,stage,c,i,k,j,value_q,value_n,qs,nsource,qa,na, &
                                               rho,minmass_value,maxmass_value,oldmass,newmass,qbase,nbase)
    USE iso_fortran_env, ONLY: int64,real64
    CHARACTER(LEN=*),INTENT(IN) :: context
    INTEGER,INTENT(IN) :: stage,c,i,k,j
    REAL(real64),INTENT(IN) :: value_q,value_n,qs,nsource,qa,na
    REAL(real32),INTENT(IN) :: rho,oldmass,newmass,qbase,nbase
    REAL(real64),INTENT(IN) :: minmass_value,maxmass_value
    INTEGER :: u
    OPEN(NEWUNIT=u,FILE='pr92_graupel_source_capture.raw',STATUS='UNKNOWN',POSITION='APPEND')
    WRITE(u,'(A,7(1X,I0),13(1X,Z16.16))') 'PR92_STORE_FAIL_'//TRIM(context), &
      itimestep,rk,i,j,k,c,stage, &
      TRANSFER(value_q,0_int64),TRANSFER(value_n,0_int64), &
      TRANSFER(qs,0_int64),TRANSFER(nsource,0_int64),TRANSFER(qa,0_int64),TRANSFER(na,0_int64), &
      TRANSFER(REAL(rho,real64),0_int64),TRANSFER(minmass_value,0_int64), &
      TRANSFER(maxmass_value,0_int64),TRANSFER(REAL(oldmass,real64),0_int64), &
      TRANSFER(REAL(newmass,real64),0_int64),TRANSFER(REAL(qbase,real64),0_int64), &
      TRANSFER(REAL(nbase,real64),0_int64)
    WRITE(u,'(A,6(1X,Z8.8))') 'PR92_STORE_R32',TRANSFER(dt,0_int32), &
      TRANSFER(oldmass,0_int32),TRANSFER(newmass,0_int32),TRANSFER(rho,0_int32), &
      TRANSFER(qbase,0_int32),TRANSFER(nbase,0_int32)
    CLOSE(u)
  END SUBROUTINE write_pr92_store_failure_capture

  SUBROUTINE write_pr91_mixture_store_reject(timestep,rk,pair,i,k,j,cell,dt,denominator, &
      weights,q_terms,n_terms)
    INTEGER,INTENT(IN) :: timestep,rk,pair,i,k,j,cell
    REAL(real32),INTENT(IN) :: dt,denominator,q_terms(7),n_terms(7)
    REAL(real64),INTENT(IN) :: weights(7)
    CHARACTER(LEN=64) :: run_id
    INTEGER :: env_status
    CALL get_environment_variable('PR91_RUN_ID',run_id,STATUS=env_status)
    IF (env_status/=0.OR.LEN_TRIM(run_id)==0) &
      CALL wrf_error_fatal('PR91_RUN_ID is required for mixture trace')
    WRITE(*,'(A,1X,A,8(1X,I0),1X,A,1X,Z8.8)') 'PR91_MIXTURE_STORE_REJECT',TRIM(run_id), &
      timestep,rk,4,pair,i,j,k,cell,'PR87_GRAUPEL_DONOR_ORDER_V1',TRANSFER(denominator,0_int32)
    WRITE(*,'(A,1X,A,7(1X,Z16.16))') 'PR91_MIXTURE_WEIGHTS64',TRIM(run_id), &
      TRANSFER(weights,0_int64,7)
    WRITE(*,'(A,1X,A,14(1X,Z8.8))') 'PR91_MIXTURE_TERMS32',TRIM(run_id), &
      TRANSFER(q_terms,0_int32,7),TRANSFER(n_terms,0_int32,7)
    WRITE(*,'(A,1X,A,1X,Z8.8)') 'PR91_MIXTURE_DT32',TRIM(run_id),TRANSFER(dt,0_int32)
  END SUBROUTINE write_pr91_mixture_store_reject

  SUBROUTINE graupel_transport_mixture(c,i,k,j,weights,q_terms,n_terms,valid)
    INTEGER,INTENT(IN) :: c,i,k,j
    REAL(real64),INTENT(OUT) :: weights(7)
    REAL(real32),INTENT(OUT) :: q_terms(7),n_terms(7)
    LOGICAL,INTENT(OUT) :: valid
    REAL(real64) :: xscale,yscale,zscale,outflow,edge,base_weight
    weights=0.0_real64; q_terms=0.0_real32; n_terms=0.0_real32; valid=.FALSE.
    xscale=REAL(msfty(i,j),real64)*REAL(msftx(i,j)*rdx,real64)
    yscale=REAL(msfty(i,j),real64)*REAL(msftx(i,j)*rdy,real64)
    zscale=REAL(msfty(i,j),real64)*REAL(-rdnw(k),real64)
    IF (.NOT.ALL(ieee_is_finite([xscale,yscale,zscale]))) RETURN
    IF (MIN(xscale,yscale,zscale)<0.0_real64) RETURN
    outflow=xscale*(MAX(REAL(ru(i+1,k,j),real64),0.0_real64)+ &
                    MAX(-REAL(ru(i,k,j),real64),0.0_real64))+ &
            yscale*(MAX(REAL(rv(i,k,j+1),real64),0.0_real64)+ &
                    MAX(-REAL(rv(i,k,j),real64),0.0_real64))
    IF (k>kl) outflow=outflow+zscale*MAX(REAL(ww(i,k,j),real64),0.0_real64)
    IF (k<kh) outflow=outflow+zscale*MAX(-REAL(ww(i,k+1,j),real64),0.0_real64)
    base_weight=REAL(oldcarrier(c),real64)-REAL(dt,real64)*outflow
    IF (.NOT.ieee_is_finite(base_weight)) RETURN
    IF (base_weight<0.0_real64) RETURN
    weights(1)=base_weight
    q_terms(1)=q1(i,k,j,qindex(4)); n_terms(1)=n1(i,k,j,nindex(4))

    edge=REAL(ru(i+1,k,j),real64)
    IF (edge<0.0_real64) THEN
      weights(2)=REAL(dt,real64)*xscale*(-edge)
      q_terms(2)=q1(i+1,k,j,qindex(4)); n_terms(2)=n1(i+1,k,j,nindex(4))
    END IF
    edge=REAL(ru(i,k,j),real64)
    IF (edge>0.0_real64) THEN
      weights(3)=REAL(dt,real64)*xscale*edge
      q_terms(3)=q1(i-1,k,j,qindex(4)); n_terms(3)=n1(i-1,k,j,nindex(4))
    END IF
    edge=REAL(rv(i,k,j+1),real64)
    IF (edge<0.0_real64) THEN
      weights(4)=REAL(dt,real64)*yscale*(-edge)
      q_terms(4)=q1(i,k,j+1,qindex(4)); n_terms(4)=n1(i,k,j+1,nindex(4))
    END IF
    edge=REAL(rv(i,k,j),real64)
    IF (edge>0.0_real64) THEN
      weights(5)=REAL(dt,real64)*yscale*edge
      q_terms(5)=q1(i,k,j-1,qindex(4)); n_terms(5)=n1(i,k,j-1,nindex(4))
    END IF
    IF (k<kh) THEN
      edge=REAL(ww(i,k+1,j),real64)
      IF (edge>0.0_real64) THEN
        weights(6)=REAL(dt,real64)*zscale*edge
        q_terms(6)=q1(i,k+1,j,qindex(4)); n_terms(6)=n1(i,k+1,j,nindex(4))
      END IF
    END IF
    IF (k>kl) THEN
      edge=REAL(ww(i,k,j),real64)
      IF (edge<0.0_real64) THEN
        weights(7)=REAL(dt,real64)*zscale*(-edge)
        q_terms(7)=q1(i,k-1,j,qindex(4)); n_terms(7)=n1(i,k-1,j,nindex(4))
      END IF
    END IF
    IF (.NOT.ALL(ieee_is_finite(weights))) RETURN
    IF (ANY(weights<0.0_real64)) RETURN
    valid=.TRUE.
  END SUBROUTINE graupel_transport_mixture

  SUBROUTINE add_graupel_diffusion_mixture(c,i,k,j,weights,q_terms,n_terms,valid)
    INTEGER,INTENT(IN) :: c,i,k,j
    REAL(real64),INTENT(INOUT) :: weights(7)
    REAL(real32),INTENT(INOUT) :: q_terms(7),n_terms(7)
    LOGICAL,INTENT(OUT) :: valid
    INTEGER,PARAMETER :: real128=SELECTED_REAL_KIND(33,4931)
    REAL(real64) :: qdiff,ndiff
    REAL(real128) :: qface(4),nface(4),amount(4),base_weight,face_weight
    INTEGER :: face,slot
    valid=.FALSE.
    IF (.NOT.ALL(ieee_is_finite([qs64(c,4),ns64(c,4)]))) RETURN
    IF (qs64(c,4)==0.0_real64.AND.ns64(c,4)==0.0_real64) THEN
      valid=.TRUE.; RETURN
    END IF
    CALL graupel_diffusion_point(q1(:,:,:,qindex(4)),i,k,j,qdiff,qface,valid)
    IF (.NOT.valid) RETURN
    CALL graupel_diffusion_point(n1(:,:,:,nindex(4)),i,k,j,ndiff,nface,valid)
    IF (.NOT.valid) RETURN
    valid=.FALSE.
    IF (TRANSFER(qs64(c,4),0_int64)/=TRANSFER(qdiff,0_int64).OR. &
        TRANSFER(ns64(c,4),0_int64)/=TRANSFER(ndiff,0_int64)) THEN
      CALL write_pr92_graupel_source_capture(c,i,k,j,weights,q_terms,n_terms, &
          qdiff,ndiff,qface,nface)
      valid=.FALSE.; RETURN
    END IF
    IF (ANY(qface/=nface).OR.ANY(qface<0.0_real128)) THEN
      valid=.FALSE.; RETURN
    END IF
    amount=REAL(dt,real128)*qface
    IF (.NOT.ALL(ieee_is_finite(amount))) THEN
      valid=.FALSE.; RETURN
    END IF
    base_weight=REAL(weights(1),real128)-SUM(amount)
    IF (.NOT.ieee_is_finite(base_weight)) THEN
      valid=.FALSE.; RETURN
    END IF
    IF (base_weight<0.0_real128.OR.base_weight>REAL(HUGE(0.0_real64),real128)) THEN
      valid=.FALSE.; RETURN
    END IF
    weights(1)=REAL(base_weight,real64)
    IF (base_weight>0.0_real128.AND.weights(1)==0.0_real64) THEN
      valid=.FALSE.; RETURN
    END IF
    q_terms(2)=q1(i+1,k,j,qindex(4)); n_terms(2)=n1(i+1,k,j,nindex(4))
    q_terms(3)=q1(i-1,k,j,qindex(4)); n_terms(3)=n1(i-1,k,j,nindex(4))
    q_terms(4)=q1(i,k,j+1,qindex(4)); n_terms(4)=n1(i,k,j+1,nindex(4))
    q_terms(5)=q1(i,k,j-1,qindex(4)); n_terms(5)=n1(i,k,j-1,nindex(4))
    DO face=1,4
      slot=face+1
      face_weight=REAL(weights(slot),real128)+amount(face)
      IF (.NOT.ieee_is_finite(face_weight)) THEN
        valid=.FALSE.; RETURN
      END IF
      IF (face_weight<0.0_real128.OR.face_weight>REAL(HUGE(0.0_real64),real128)) THEN
        valid=.FALSE.; RETURN
      END IF
      weights(slot)=REAL(face_weight,real64)
      IF (face_weight>0.0_real128.AND.weights(slot)==0.0_real64) THEN
        valid=.FALSE.; RETURN
      END IF
    END DO
    IF (.NOT.ALL(ieee_is_finite(weights))) RETURN
    IF (ANY(weights<0.0_real64)) RETURN
    valid=.TRUE.
  END SUBROUTINE add_graupel_diffusion_mixture

  SUBROUTINE write_pr92_graupel_source_capture(c,i,k,j,weights,q_terms,n_terms, &
                                               qdiff,ndiff,qface,nface)
    USE iso_fortran_env, ONLY: int32,int64,real32,real64
    INTEGER,INTENT(IN) :: c,i,k,j
    REAL(real64),INTENT(IN) :: weights(7),qdiff,ndiff
    REAL(real32),INTENT(IN) :: q_terms(7),n_terms(7)
    INTEGER,PARAMETER :: real128=SELECTED_REAL_KIND(33,4931)
    REAL(real128),INTENT(IN) :: qface(4),nface(4)
    INTEGER :: u,dx,dy
    OPEN(NEWUNIT=u,FILE='pr92_graupel_source_capture.raw',STATUS='UNKNOWN',POSITION='APPEND')
    WRITE(u,'(A,5(1X,I0),1X,I0)') 'PR92_FAIL',itimestep,rk,i,j,k,c
    IF (PRESENT(pr87_all_pair_diffusion_identity)) THEN
      WRITE(u,'(A,1X,8(I0,1X))') 'PR92_PRODUCER_IDENTITY', &
        pr87_all_pair_diffusion_identity
    ELSE
      WRITE(u,'(A)') 'PR92_PRODUCER_IDENTITY UNAVAILABLE'
    END IF
    WRITE(u,'(A,8(1X,Z8.8))') 'PR92_R32',TRANSFER(dt,0_int32), &
      TRANSFER(oldcarrier(c),0_int32),TRANSFER(newcarrier(c),0_int32), &
      TRANSFER(drydensity(c),0_int32),TRANSFER(qt(i,k,j,qindex(4)),0_int32), &
      TRANSFER(nt(i,k,j,nindex(4)),0_int32),TRANSFER(q1(i,k,j,qindex(4)),0_int32), &
      TRANSFER(n1(i,k,j,nindex(4)),0_int32)
    WRITE(u,'(A,12(1X,Z16.16))') 'PR92_R64', &
      TRANSFER(qs64(c,4),0_int64),TRANSFER(ns64(c,4),0_int64), &
      TRANSFER(qdiff,0_int64),TRANSFER(ndiff,0_int64), &
      TRANSFER(REAL(qt(i,k,j,qindex(4)),real64),0_int64), &
      TRANSFER(REAL(nt(i,k,j,nindex(4)),real64),0_int64), &
      TRANSFER(REAL(mut_diff(i,j),real64),0_int64), &
      TRANSFER(REAL(c1(k),real64),0_int64),TRANSFER(REAL(c2(k),real64),0_int64), &
      TRANSFER(REAL(rdx,real64),0_int64),TRANSFER(REAL(rdy,real64),0_int64), &
      TRANSFER(REAL(xkmhd_diff(i,k,j),real64),0_int64)
    DO dy=-1,1
      WRITE(u,'(A,1X,I0,12(1X,Z8.8))') 'PR92_STENCIL',dy, &
        TRANSFER(q1(i-1,k,j+dy,qindex(4)),0_int32), &
        TRANSFER(q1(i,k,j+dy,qindex(4)),0_int32), &
        TRANSFER(q1(i+1,k,j+dy,qindex(4)),0_int32), &
        TRANSFER(n1(i-1,k,j+dy,nindex(4)),0_int32), &
        TRANSFER(n1(i,k,j+dy,nindex(4)),0_int32), &
        TRANSFER(n1(i+1,k,j+dy,nindex(4)),0_int32), &
        TRANSFER(xkmhd_diff(i-1,k,j+dy),0_int32), &
        TRANSFER(xkmhd_diff(i,k,j+dy),0_int32), &
        TRANSFER(xkmhd_diff(i+1,k,j+dy),0_int32), &
        TRANSFER(mut_diff(i-1,j+dy),0_int32),TRANSFER(mut_diff(i,j+dy),0_int32), &
        TRANSFER(mut_diff(i+1,j+dy),0_int32)
    END DO
    WRITE(u,'(A,10(1X,Z8.8))') 'PR92_METRICS', &
      TRANSFER(msfux_diff(i,j),0_int32),TRANSFER(msfux_diff(i+1,j),0_int32), &
      TRANSFER(msfuy_diff(i,j),0_int32),TRANSFER(msfuy_diff(i+1,j),0_int32), &
      TRANSFER(msfvx_inv_diff(i,j),0_int32),TRANSFER(msfvx_inv_diff(i,j+1),0_int32), &
      TRANSFER(msfvy_diff(i,j),0_int32),TRANSFER(msfvy_diff(i,j+1),0_int32), &
      TRANSFER(msftx(i,j),0_int32),TRANSFER(msfty(i,j),0_int32)
    WRITE(u,'(A,7(1X,Z16.16))') 'PR92_WEIGHTS',TRANSFER(weights,0_int64,7)
    WRITE(u,'(A,14(1X,Z8.8))') 'PR92_DONOR_TERMS', &
      TRANSFER(q_terms,0_int32,7),TRANSFER(n_terms,0_int32,7)
    WRITE(u,'(A,16(1X,Z16.16))') 'PR92_FACE_COEFFICIENTS', &
      TRANSFER(qface,0_int64,8),TRANSFER(nface,0_int64,8)
    IF (PRESENT(pr87_all_pair_diffusion_delta)) THEN
      WRITE(u,'(A,2(1X,Z16.16))') 'PR92_CACHE_DELTA', &
        TRANSFER(pr87_all_pair_diffusion_delta(i,k,j,7),0_int64), &
        TRANSFER(pr87_all_pair_diffusion_delta(i,k,j,8),0_int64)
    ELSE
      WRITE(u,'(A)') 'PR92_CACHE_DELTA UNAVAILABLE'
    END IF
    CLOSE(u)
  END SUBROUTINE write_pr92_graupel_source_capture

  SUBROUTINE graupel_diffusion_point(field,i,k,j,increment,face_coefficients,valid)
    INTEGER,INTENT(IN) :: i,k,j
    REAL(real32),INTENT(IN) :: field(ims:ime,kms:kme,jms:jme)
    REAL(real64),INTENT(OUT) :: increment
    INTEGER,PARAMETER :: real128=SELECTED_REAL_KIND(33,4931)
    REAL(real128),INTENT(OUT) :: face_coefficients(4)
    LOGICAL,INTENT(OUT) :: valid
    REAL(real128) :: increment128,mrdx,mrdy,mkrdxm,mkrdxp,mkrdym,mkrdyp
    REAL(real128) :: mut_i,mut_im,mut_ip,mut_jm,mut_jp
    REAL(real128) :: x_i,x_im,x_ip,x_jm,x_jp
    increment=0.0_real64; face_coefficients=0.0_real128; valid=.FALSE.
    IF (i<ims+1.OR.i>ime-1.OR.j<jms+1.OR.j>jme-1.OR.k<kms.OR.k>kme) RETURN
    IF (.NOT.ALL(ieee_is_finite([field(i,k,j),field(i-1,k,j),field(i+1,k,j), &
        field(i,k,j-1),field(i,k,j+1),mut_diff(i,j),mut_diff(i-1,j),mut_diff(i+1,j), &
        mut_diff(i,j-1),mut_diff(i,j+1),xkmhd_diff(i,k,j),xkmhd_diff(i-1,k,j), &
        xkmhd_diff(i+1,k,j),xkmhd_diff(i,k,j-1),xkmhd_diff(i,k,j+1), &
        msfux_diff(i,j),msfuy_diff(i,j),msfux_diff(i+1,j),msfuy_diff(i+1,j), &
        msfvx_inv_diff(i,j),msfvy_diff(i,j),msfvx_inv_diff(i,j+1),msfvy_diff(i,j+1), &
        msftx(i,j),msfty(i,j),c1(k),c2(k),rdx,rdy]))) RETURN
    IF (msfuy_diff(i,j)==0.0.OR.msfuy_diff(i+1,j)==0.0) RETURN
    mut_i=REAL(c1(k),real128)*REAL(mut_diff(i,j),real128)+REAL(c2(k),real128)
    mut_im=REAL(c1(k),real128)*REAL(mut_diff(i-1,j),real128)+REAL(c2(k),real128)
    mut_ip=REAL(c1(k),real128)*REAL(mut_diff(i+1,j),real128)+REAL(c2(k),real128)
    mut_jm=REAL(c1(k),real128)*REAL(mut_diff(i,j-1),real128)+REAL(c2(k),real128)
    mut_jp=REAL(c1(k),real128)*REAL(mut_diff(i,j+1),real128)+REAL(c2(k),real128)
    x_i=REAL(xkmhd_diff(i,k,j),real128); x_im=REAL(xkmhd_diff(i-1,k,j),real128)
    x_ip=REAL(xkmhd_diff(i+1,k,j),real128); x_jm=REAL(xkmhd_diff(i,k,j-1),real128)
    x_jp=REAL(xkmhd_diff(i,k,j+1),real128)
    mkrdxm=(REAL(msfux_diff(i,j),real128)/REAL(msfuy_diff(i,j),real128))* &
      0.5_real128*(x_i+x_im)*0.5_real128*(mut_i+mut_im)*REAL(rdx,real128)
    mkrdxp=(REAL(msfux_diff(i+1,j),real128)/REAL(msfuy_diff(i+1,j),real128))* &
      0.5_real128*(x_ip+x_i)*0.5_real128*(mut_ip+mut_i)*REAL(rdx,real128)
    mrdx=REAL(msftx(i,j),real128)*REAL(msfty(i,j),real128)*REAL(rdx,real128)
    mkrdym=(REAL(msfvy_diff(i,j),real128)*REAL(msfvx_inv_diff(i,j),real128))* &
      0.5_real128*(x_i+x_jm)*0.5_real128*(mut_i+mut_jm)*REAL(rdy,real128)
    mkrdyp=(REAL(msfvy_diff(i,j+1),real128)*REAL(msfvx_inv_diff(i,j+1),real128))* &
      0.5_real128*(x_jp+x_i)*0.5_real128*(mut_jp+mut_i)*REAL(rdy,real128)
    mrdy=REAL(msftx(i,j),real128)*REAL(msfty(i,j),real128)*REAL(rdy,real128)
    face_coefficients=[mrdx*mkrdxp,mrdx*mkrdxm,mrdy*mkrdyp,mrdy*mkrdym]
    IF (.NOT.ALL(ieee_is_finite(face_coefficients))) RETURN
    IF (ANY(face_coefficients<0.0_real128)) RETURN
    increment128= &
      mrdx*(mkrdxp*(REAL(field(i+1,k,j),real128)-REAL(field(i,k,j),real128))- &
            mkrdxm*(REAL(field(i,k,j),real128)-REAL(field(i-1,k,j),real128)))+ &
      mrdy*(mkrdyp*(REAL(field(i,k,j+1),real128)-REAL(field(i,k,j),real128))- &
            mkrdym*(REAL(field(i,k,j),real128)-REAL(field(i,k,j-1),real128)))
    increment=REAL(increment128,real64)
    IF (.NOT.ieee_is_finite(increment)) RETURN
    valid=.TRUE.
  END SUBROUTINE graupel_diffusion_point

  PURE LOGICAL FUNCTION strict_graupel_pair(q,n,minimum_ratio,maximum_ratio)
    REAL(real64),INTENT(IN) :: q,n,minimum_ratio,maximum_ratio
    INTEGER,PARAMETER :: real128=SELECTED_REAL_KIND(33,4931)
    REAL(real128) :: q128,n128
    strict_graupel_pair=.FALSE.
    IF (.NOT.ALL(ieee_is_finite([q,n,minimum_ratio,maximum_ratio]))) RETURN
    IF (q<0.0_real64.OR.n<0.0_real64.OR.minimum_ratio<=0.0_real64.OR. &
        maximum_ratio<minimum_ratio) RETURN
    IF (q==0.0_real64.AND.n==0.0_real64) THEN
      strict_graupel_pair=.TRUE.; RETURN
    END IF
    IF (q<=0.0_real64.OR.n<=0.0_real64) RETURN
    q128=REAL(q,real128); n128=REAL(n,real128)
    strict_graupel_pair=q128>=REAL(minimum_ratio,real128)*n128.AND. &
                        q128<=REAL(maximum_ratio,real128)*n128
  END FUNCTION strict_graupel_pair

  SUBROUTINE store_graupel_mixture(weights,q_terms,n_terms,denominator,minimum_ratio, &
      maximum_ratio,reference_q,reference_n,stored_q,stored_n,delta_q,delta_n,valid)
    REAL(real64),INTENT(IN) :: weights(7),minimum_ratio,maximum_ratio,reference_q,reference_n
    REAL(real32),INTENT(IN) :: q_terms(7),n_terms(7),denominator
    REAL(real32),INTENT(OUT) :: stored_q,stored_n
    REAL(real64),INTENT(OUT) :: delta_q,delta_n
    LOGICAL,INTENT(OUT) :: valid
    INTEGER,PARAMETER :: real128=SELECTED_REAL_KIND(33,4931)
    REAL(real128) :: qsum,nsum,qvalue,nvalue,qcheck,ncheck
    INTEGER :: term,attempt
    stored_q=-1.0_real32; stored_n=-1.0_real32
    delta_q=0.0_real64; delta_n=0.0_real64; valid=.FALSE.
    IF (.NOT.ALL(ieee_is_finite(weights))) RETURN
    IF (ANY(weights<0.0_real64)) RETURN
    IF (.NOT.ALL(ieee_is_finite(q_terms))) RETURN
    IF (.NOT.ALL(ieee_is_finite(n_terms))) RETURN
    IF (.NOT.ieee_is_finite(denominator)) RETURN
    IF (denominator<=0.0_real32) RETURN
    IF (.NOT.ieee_is_finite(reference_q).OR..NOT.ieee_is_finite(reference_n)) RETURN
    qsum=0.0_real128; nsum=0.0_real128
    DO term=1,7
      IF (weights(term)==0.0_real64) CYCLE
      IF (.NOT.strict_graupel_pair(REAL(q_terms(term),real64),REAL(n_terms(term),real64), &
                                   minimum_ratio,maximum_ratio)) RETURN
      qsum=qsum+REAL(weights(term),real128)*REAL(q_terms(term),real128)
      nsum=nsum+REAL(weights(term),real128)*REAL(n_terms(term),real128)
    END DO
    qvalue=qsum/REAL(denominator,real128); nvalue=nsum/REAL(denominator,real128)
    IF (.NOT.ieee_is_finite(qvalue).OR..NOT.ieee_is_finite(nvalue)) RETURN
    IF (qvalue>REAL(HUGE(0.0_real32),real128).OR.nvalue>REAL(HUGE(0.0_real32),real128)) RETURN
    stored_q=REAL(qvalue,real32); stored_n=REAL(nvalue,real32)
    IF (.NOT.ieee_is_finite(stored_q).OR..NOT.ieee_is_finite(stored_n)) RETURN
    DO attempt=1,4
      IF (strict_graupel_pair(REAL(stored_q,real64),REAL(stored_n,real64), &
                              minimum_ratio,maximum_ratio)) EXIT
      qcheck=REAL(stored_q,real128); ncheck=REAL(stored_n,real128)
      IF (stored_q<=0.0_real32.OR.stored_n<=0.0_real32) RETURN
      IF (qcheck<REAL(minimum_ratio,real128)*ncheck) THEN
        stored_q=NEAREST(stored_q,1.0_real32)
      ELSE IF (qcheck>REAL(maximum_ratio,real128)*ncheck) THEN
        stored_q=NEAREST(stored_q,-1.0_real32)
      ELSE
        RETURN
      END IF
    END DO
    IF (.NOT.strict_graupel_pair(REAL(stored_q,real64),REAL(stored_n,real64), &
                                 minimum_ratio,maximum_ratio)) RETURN
    delta_q=REAL(denominator,real64)*(REAL(stored_q,real64)-reference_q)
    delta_n=REAL(denominator,real64)*(REAL(stored_n,real64)-reference_n)
    IF (.NOT.ALL(ieee_is_finite([delta_q,delta_n]))) RETURN
    valid=.TRUE.
  END SUBROUTINE store_graupel_mixture

  SUBROUTINE find_failed_baseline_pairs()
    INTEGER :: c,pair,local_adjustment
    REAL(real64) :: value(2)
    REAL(real32) :: stored(2)
    LOGICAL :: local_valid
    failed_pairs=.FALSE.
    DO pair=1,4
      DO c=1,cells
        ! These are the exact operands of the initial theta=1 kernel candidate.
        value=(REAL(oldcarrier(c),real64)*[REAL(qb(c,pair),real64),REAL(nb(c,pair),real64)]+ &
               REAL(dt,real64)*[qs64(c,pair)+qa64(c,pair),ns64(c,pair)+na64(c,pair)])/ &
               REAL(newcarrier(c),real64)
        IF (pair==1.OR.pair==3) THEN
        CALL joint_moment_store(value(1),value(2),drydensity(c),minmass(pair),maxmass(pair), &
             .TRUE.,stored(1),stored(2),local_adjustment,local_valid, &
             allow_normal_q_adjustment=.TRUE.,allow_joint_quantum_absence=.TRUE., &
             volume_number_bounds=number_bounds(c,:,pair))
        ELSE
        CALL joint_moment_store(value(1),value(2),drydensity(c),minmass(pair),maxmass(pair), &
             .TRUE.,stored(1),stored(2),local_adjustment,local_valid, &
             allow_normal_q_adjustment=.TRUE.,allow_joint_quantum_absence=.TRUE., &
             strict_mass_ratio=(pair==4), &
             inactive_mass_limit=MERGE(REAL(NEAREST(1.e-14,-1.0),real64),0.0_real64,pair==2), &
                 allow_inactive_q_quantum_adjustment=(pair==2))
        END IF
        IF (.NOT.local_valid) failed_pairs(pair)=.TRUE.
      END DO
    END DO
  END SUBROUTINE find_failed_baseline_pairs

  SUBROUTINE prepare_source_first_rates()
    IF (pr87_source_step/=itimestep) &
      CALL wrf_error_fatal('PR87 intensive source payload is not current or changed after capture')
    ALLOCATE(donor_q(ims:ime,kms:kme,jms:jme,2),donor_n(ims:ime,kms:kme,jms:jme,2))
    ALLOCATE(prepared_q(ims:ime,kms:kme,jms:jme,2), &
             prepared_n(ims:ime,kms:kme,jms:jme,2), &
             prepared_diffusion(ims:ime,kms:kme,jms:jme), &
             prepared_n_diffusion(ims:ime,kms:kme,jms:jme))
    DO p=1,2
      prepared_q(:,:,:,p)=q1(:,:,:,qindex(p))
      prepared_n(:,:,:,p)=n1(:,:,:,nindex(p))
      IF (.NOT.source_first_pair(p)) CYCLE
      donor_q(:,:,:,p)=REAL(q1(:,:,:,qindex(p)),real64)
      donor_n(:,:,:,p)=REAL(n1(:,:,:,nindex(p)),real64)
    END DO
    ! Capture comes before the host's R32 carrier coupling, with explicit step identity.
    ! The source stage is virtual: only the complete source/air endpoint is committed.
    cell=0
    DO j=jl,jh
    DO k=kl,kh
    DO i=il,ih
      cell=cell+1
      IF (pr87_source_carrier(i,k,j)/=oldcarrier(cell)) THEN
        WRITE(*,*) 'PR87_SOURCE_CARRIER_REJECT',itimestep,rk,i,j,k, &
                    pr87_source_carrier(i,k,j),oldcarrier(cell)
        CALL wrf_error_fatal('PR87 physical source and old state use different dry carriers')
      ENDIF
      DO p=1,2
        IF (.NOT.source_first_pair(p)) CYCLE
        IF (qs(cell,p)/=pr87_coupled_qsrc(i,k,j,p).OR. &
            ns(cell,p)/=pr87_coupled_nsrc(i,k,j,p)) &
          CALL wrf_error_fatal('PR87 coupled source changed since its intensive capture')
        source_rate64=[REAL(pr87_raw_qsrc(i,k,j,p),real64), &
                        REAL(pr87_raw_nsrc(i,k,j,p),real64)]
        IF (p==1) source_rate64=source_rate64+ &
             [pr87_pbl_tendency_delta64(i,k,j,1),pr87_pbl_tendency_delta64(i,k,j,2)]
        IF (p==2) source_rate64=source_rate64+ &
             [pr87_pbl_tendency_delta64(i,k,j,3),pr87_pbl_tendency_delta64(i,k,j,4)]
        IF (.NOT.ALL(ieee_is_finite(source_rate64))) &
          CALL wrf_error_fatal('PR87 nonfinite intensive source payload')
        source_candidate=[REAL(q1(i,k,j,qindex(p)),real64), &
                          REAL(n1(i,k,j,nindex(p)),real64)]+REAL(dt,real64)*source_rate64
        IF (.NOT.prepared_donor_is_safe(source_candidate(1),source_candidate(2),drydensity(cell))) &
          CALL wrf_error_fatal('PR87 unsafe continuous intensive source donor')
        ! Preserve the explicit intensive R32 integration order, not a division of a rounded W*S.
        source_sum64=REAL(dt,real64)*source_rate64
        IF (ANY(ABS(source_sum64)>REAL(HUGE(0.0_real32),real64))) &
          CALL wrf_error_fatal('PR87 intensive source increment exceeds REAL32 range')
        source_increment32=REAL(REAL(dt,real64)*source_rate64,real32)
        source_sum64=[REAL(q1(i,k,j,qindex(p)),real64),REAL(n1(i,k,j,nindex(p)),real64)]+ &
                      REAL(source_increment32,real64)
        IF (ANY(source_sum64<0.0_real64).OR.ANY(source_sum64>REAL(HUGE(0.0_real32),real64))) &
          CALL wrf_error_fatal('PR87 staged intensive source exceeds nonnegative REAL32 range')
        source_endpoint32=[q1(i,k,j,qindex(p)),n1(i,k,j,nindex(p))]+source_increment32
        IF (p==1) THEN
          CALL joint_moment_store(source_candidate(1),source_candidate(2),drydensity(cell), &
               minmass(p),maxmass(p),.TRUE.,source_endpoint32(1),source_endpoint32(2), &
               adjustment,full_valid,allow_normal_q_adjustment=.TRUE., &
               allow_joint_quantum_absence=.TRUE.,strict_mass_ratio=.TRUE.)
        ELSE
          CALL joint_moment_store(source_candidate(1),source_candidate(2),drydensity(cell), &
               minmass(p),maxmass(p),.TRUE.,source_endpoint32(1),source_endpoint32(2), &
               adjustment,full_valid,allow_normal_q_adjustment=.TRUE., &
               allow_joint_quantum_absence=.TRUE., &
               inactive_mass_limit=MERGE(REAL(NEAREST(1.e-14,-1.0),real64),0.0_real64,p==2), &
                 allow_inactive_q_quantum_adjustment=(p==2))
        END IF
        IF (.NOT.full_valid) THEN
          OPEN(NEWUNIT=u,FILE='pr85_joint_source_failure.raw',STATUS='UNKNOWN',POSITION='APPEND')
          WRITE(u,'(a,6i10,1p,20es26.17)') 'SOURCE_STAGE',itimestep,rk,p,i,j,k, &
            REAL(q1(i,k,j,qindex(p)),real64),REAL(n1(i,k,j,nindex(p)),real64), &
            source_rate64,source_candidate,REAL(drydensity(cell),real64), &
            minmass(p),maxmass(p),number_bounds(cell,:,p),REAL(dt,real64), &
            REAL(pr87_raw_qsrc(i,k,j,p),real64),REAL(pr87_raw_nsrc(i,k,j,p),real64), &
            pr87_pbl_tendency_delta64(i,k,j,:),REAL(oldcarrier(cell),real64),REAL(newcarrier(cell),real64)
          CLOSE(u)
          CALL wrf_error_fatal('PR87 corrected source-stage pair fails strict storage validation')
        END IF
        IF (.NOT.prepared_donor_is_safe(REAL(source_endpoint32(1),real64), &
                                       REAL(source_endpoint32(2),real64),drydensity(cell)).OR. &
            (ALL(source_endpoint32==0.0_real32).AND.ANY(source_candidate>0.0_real64))) THEN
          ! Existing bounded joint representation policy; continuously invalid pairs stay rejected.
          CALL joint_moment_store(source_candidate(1),source_candidate(2),drydensity(cell), &
               minmass(p),maxmass(p),.TRUE.,source_endpoint32(1),source_endpoint32(2),adjustment,full_valid, &
               allow_normal_q_adjustment=.TRUE.,allow_joint_quantum_absence=.TRUE., &
                 inactive_mass_limit=MERGE(REAL(NEAREST(1.e-14,-1.0),real64),0.0_real64,p==2), &
                 allow_inactive_q_quantum_adjustment=(p==2))
          IF (.NOT.full_valid) CALL wrf_error_fatal('PR87 intensive source pair is not jointly representable')
        ENDIF
        prepared_q(i,k,j,p)=source_endpoint32(1)
        prepared_n(i,k,j,p)=source_endpoint32(2)
        ! RK1 adds weighted diffusion/diabatic/boundary tendencies after physics coupling.
        ! They remain explicit source amounts; PD advection is not part of this payload.
        qs64(cell,p)=pr87_later_qsrc(i,k,j,p)
        ns64(cell,p)=pr87_later_nsrc(i,k,j,p)
        IF (p>=1.AND.p<=2.AND.PRESENT(pr87_all_pair_diffusion_delta)) THEN
          IF (.NOT.ALL(ieee_is_finite(pr87_all_pair_diffusion_delta(i,k,j,2*p-1:2*p)))) &
            CALL wrf_error_fatal('PR87 nonfinite later paired diffusion correction')
          qs64(cell,p)=qs64(cell,p)+pr87_all_pair_diffusion_delta(i,k,j,2*p-1)
          ns64(cell,p)=ns64(cell,p)+pr87_all_pair_diffusion_delta(i,k,j,2*p)
        END IF
        IF (.NOT.ALL(ieee_is_finite([qs64(cell,p),ns64(cell,p)]))) &
          CALL wrf_error_fatal('PR87 nonfinite later non-air source payload')
        ! Virtual donors are formed after the prepared-field diffusion pass.
        ! Physics enters through the local stage once; later sources enter through qs64/ns64 once.
        qb(cell,p)=source_endpoint32(1); nb(cell,p)=source_endpoint32(2)
      END DO
    END DO
    END DO
    END DO
    ! The unchanged boundary donor ring remains a completed physical state.
    DO j=jl-1,jh+1
    DO k=kl,kh
    DO i=il-1,ih+1
      IF (i>=il.AND.i<=ih.AND.j>=jl.AND.j<=jh) CYCLE
      CALL pr85_dry_density_from_al_alb(al(i,k,j),alb(i,k,j),source_stored(1),density_valid)
      IF (.NOT.density_valid) CALL wrf_error_fatal('PR87 invalid donor-ring density')
      DO p=1,2
        IF (.NOT.source_first_pair(p)) CYCLE
        IF (.NOT.joint_moment_is_valid64(donor_q(i,k,j,p),donor_n(i,k,j,p), &
                                        source_stored(1),minmass(p),maxmass(p))) &
          CALL wrf_error_fatal('PR87 unchanged boundary donor pair infeasible')
      END DO
    END DO
    END DO
    END DO
    source_diff_sum=0.0_real64; source_diff_l1=0.0_real64; source_diff_max=0.0_real64
    source_diff_cells=0
    DO p=1,2
      IF (.NOT.source_first_pair(p)) CYCLE
      source_diff_sum=0.0_real64; source_diff_l1=0.0_real64; source_diff_max=0.0_real64
      source_diff_cells=0
      IF (.NOT.PRESENT(pr87_all_pair_diffusion_old)) &
        CALL wrf_error_fatal('PR91 source-first diffusion requires producer cache')
      IF (ANY(pr87_all_pair_diffusion_valid(2*p-1:2*p)==0)) &
        CALL wrf_error_fatal('PR91 missing paired old diffusion cache channel')
      CALL horizontal_diffusion64(prepared_q(:,:,:,p),mut_diff,c1,c2, &
           msfux_diff,msfuy_diff,msfvx_inv_diff,msfvy_diff,msftx,msfty,xkmhd_diff, &
           rdx,rdy,ims,ime,kms,kme,jms,jme, &
           pr87_all_pair_diffusion_identity(3),pr87_all_pair_diffusion_identity(4), &
           pr87_all_pair_diffusion_identity(5),pr87_all_pair_diffusion_identity(6), &
           pr87_all_pair_diffusion_identity(7),pr87_all_pair_diffusion_identity(8),prepared_diffusion)
      CALL horizontal_diffusion64(prepared_n(:,:,:,p),mut_diff,c1,c2, &
           msfux_diff,msfuy_diff,msfvx_inv_diff,msfvy_diff,msftx,msfty,xkmhd_diff, &
           rdx,rdy,ims,ime,kms,kme,jms,jme, &
           pr87_all_pair_diffusion_identity(3),pr87_all_pair_diffusion_identity(4), &
           pr87_all_pair_diffusion_identity(5),pr87_all_pair_diffusion_identity(6), &
           pr87_all_pair_diffusion_identity(7),pr87_all_pair_diffusion_identity(8),prepared_n_diffusion)
      cell=0
      DO j=jl,jh
      DO k=kl,kh
      DO i=il,ih
        cell=cell+1
        IF (i<pr87_all_pair_diffusion_identity(3).OR.i>pr87_all_pair_diffusion_identity(4).OR. &
            j<pr87_all_pair_diffusion_identity(5).OR.j>pr87_all_pair_diffusion_identity(6).OR. &
            k<pr87_all_pair_diffusion_identity(7).OR.k>pr87_all_pair_diffusion_identity(8)) CYCLE
        qs64(cell,p)=pr87_all_pair_diffusion_nonD64(i,k,j,2*p-1)
        ns64(cell,p)=pr87_all_pair_diffusion_nonD64(i,k,j,2*p)
        source_diff_delta=[prepared_diffusion(i,k,j)-pr87_all_pair_diffusion_old(i,k,j,2*p-1), &
                           prepared_n_diffusion(i,k,j)-pr87_all_pair_diffusion_old(i,k,j,2*p)]
        IF (.NOT.ALL(ieee_is_finite(source_diff_delta))) &
          CALL wrf_error_fatal('PR91 nonfinite source-prepared diffusion delta')
        qs64(cell,p)=qs64(cell,p)+prepared_diffusion(i,k,j)
        ns64(cell,p)=ns64(cell,p)+prepared_n_diffusion(i,k,j)
        source_diff_sum=source_diff_sum+REAL(dt,real64)*source_diff_delta
        source_diff_l1=source_diff_l1+REAL(dt,real64)*ABS(source_diff_delta)
        source_diff_max=MAX(source_diff_max,REAL(dt,real64)*ABS(source_diff_delta))
        source_diff_cells=source_diff_cells+1
      END DO
      END DO
      END DO
      OPEN(NEWUNIT=source_diff_u,FILE='pr85_joint_source_diffusion.raw',STATUS='UNKNOWN',POSITION='APPEND')
      WRITE(source_diff_u,'(a,9i10,1p,6es26.17,i12)') 'SOURCE_DIFFUSION_DELTA_DT_PRESSURE', &
           itimestep,rk,p,pr87_all_pair_diffusion_identity(3:8), &
           source_diff_sum,source_diff_l1,source_diff_max,source_diff_cells
      CLOSE(source_diff_u)
    END DO
    cell=0
    DO j=jl,jh
    DO k=kl,kh
    DO i=il,ih
      cell=cell+1
      DO p=1,2
        IF (.NOT.source_first_pair(p)) CYCLE
        source_sum64=(REAL(oldcarrier(cell),real64)*REAL([qb(cell,p),nb(cell,p)],real64)+ &
                      REAL(dt,real64)*[qs64(cell,p),ns64(cell,p)])/REAL(oldcarrier(cell),real64)
        IF (.NOT.prepared_donor_is_safe(source_sum64(1),source_sum64(2),drydensity(cell))) THEN
          ! Failed-call-only C11 capture. Recompute Dprepared for this exact pair/cell;
          ! the full-field workspace may currently belong to the other selected pair.
          CALL horizontal_diffusion64(prepared_q(:,:,:,p),mut_diff,c1,c2, &
               msfux_diff,msfuy_diff,msfvx_inv_diff,msfvy_diff,msftx,msfty,xkmhd_diff, &
               rdx,rdy,ims,ime,kms,kme,jms,jme,i,i,j,j,k,k,prepared_diffusion)
          CALL horizontal_diffusion64(prepared_n(:,:,:,p),mut_diff,c1,c2, &
               msfux_diff,msfuy_diff,msfvx_inv_diff,msfvy_diff,msftx,msfty,xkmhd_diff, &
               rdx,rdy,ims,ime,kms,kme,jms,jme,i,i,j,j,k,k,prepared_n_diffusion)
          stage_diag_qdiff=prepared_diffusion(i,k,j)
          stage_diag_ndiff=prepared_n_diffusion(i,k,j)
          OPEN(NEWUNIT=stage_diag_u,FILE='pr85_joint_source_failure.raw', &
               STATUS='UNKNOWN',POSITION='APPEND')
          WRITE(stage_diag_u,'(a,1x,6(i10,1x),2(z16.16,1x))') 'VIRTUAL_DONOR_STAGE',itimestep,rk,p,i,j,k, &
               TRANSFER(source_sum64(1),0_int64),TRANSFER(source_sum64(2),0_int64)
          WRITE(stage_diag_u,'(a,1x,6(z8.8,1x))') 'VDS_OPERANDS_R32', &
               TRANSFER(qb(cell,p),0_int32),TRANSFER(nb(cell,p),0_int32), &
               TRANSFER(oldcarrier(cell),0_int32),TRANSFER(newcarrier(cell),0_int32), &
               TRANSFER(drydensity(cell),0_int32),TRANSFER(dt,0_int32)
          WRITE(stage_diag_u,'(a,1x,2(z16.16,1x))') 'VDS_OPERANDS_R64', &
               TRANSFER(qs64(cell,p),0_int64),TRANSFER(ns64(cell,p),0_int64)
          WRITE(stage_diag_u,'(a,1x,12(z16.16,1x))') 'VDS_SOURCE_DIFFUSION', &
               TRANSFER(pr87_later_qsrc(i,k,j,p),0_int64), &
               TRANSFER(pr87_later_nsrc(i,k,j,p),0_int64), &
               TRANSFER(pr87_all_pair_diffusion_delta(i,k,j,2*p-1),0_int64), &
               TRANSFER(pr87_all_pair_diffusion_delta(i,k,j,2*p),0_int64), &
               TRANSFER(pr87_all_pair_diffusion_old(i,k,j,2*p-1),0_int64), &
               TRANSFER(pr87_all_pair_diffusion_old(i,k,j,2*p),0_int64), &
               TRANSFER(stage_diag_qdiff,0_int64),TRANSFER(stage_diag_ndiff,0_int64), &
               TRANSFER(minmass(p),0_int64),TRANSFER(maxmass(p),0_int64), &
               TRANSFER(number_bounds(cell,1,p),0_int64),TRANSFER(number_bounds(cell,2,p),0_int64)
          ! 3x3 prepared REAL32 stencil, same k; each row is dx=-1,0,+1 and dy.
          DO stage_diag_dy=-1,1
            WRITE(stage_diag_u,'(a,1x,3(i10,1x),3(z8.8,1x))') 'VDS_Q_STENCIL',itimestep,p,stage_diag_dy, &
              (TRANSFER(prepared_q(i+stage_diag_dx,k,j+stage_diag_dy,p),0_int32), &
               stage_diag_dx=-1,1)
            WRITE(stage_diag_u,'(a,1x,3(i10,1x),3(z8.8,1x))') 'VDS_N_STENCIL',itimestep,p,stage_diag_dy, &
              (TRANSFER(prepared_n(i+stage_diag_dx,k,j+stage_diag_dy,p),0_int32), &
               stage_diag_dx=-1,1)
          END DO
          WRITE(stage_diag_u,'(a,1x,3(z8.8,1x))') 'VDS_DIFFUSIVITY', &
               TRANSFER(mut_diff(i,j),0_int32),TRANSFER(c1(k),0_int32),TRANSFER(c2(k),0_int32)
          DO stage_diag_dy=-1,1
            WRITE(stage_diag_u,'(a,1x,3(i10,1x),6(z8.8,1x))') 'VDS_GEOMETRY_X',itimestep,p,stage_diag_dy, &
              (TRANSFER(xkmhd_diff(i+stage_diag_dx,k,j+stage_diag_dy),0_int32), &
               stage_diag_dx=-1,1), &
              (TRANSFER(mut_diff(i+stage_diag_dx,j+stage_diag_dy),0_int32),stage_diag_dx=-1,1)
          END DO
          WRITE(stage_diag_u,'(a,1x,10(z8.8,1x))') 'VDS_GEOMETRY_FACE', &
               TRANSFER(msfux_diff(i,j),0_int32),TRANSFER(msfux_diff(i+1,j),0_int32), &
               TRANSFER(msfuy_diff(i,j),0_int32),TRANSFER(msfuy_diff(i+1,j),0_int32), &
               TRANSFER(msfvx_inv_diff(i,j-1),0_int32),TRANSFER(msfvx_inv_diff(i,j),0_int32), &
               TRANSFER(msfvx_inv_diff(i,j+1),0_int32), &
               TRANSFER(msfvy_diff(i,j),0_int32),TRANSFER(msfvy_diff(i,j+1),0_int32)
          WRITE(stage_diag_u,'(a,1x,6(z8.8,1x))') 'VDS_GEOMETRY_Y', &
               TRANSFER(msfvy_diff(i,j-1),0_int32),TRANSFER(msfvy_diff(i,j),0_int32), &
               TRANSFER(msfvy_diff(i,j+1),0_int32),TRANSFER(msftx(i,j),0_int32), &
               TRANSFER(msfty(i,j),0_int32),TRANSFER(rdx,0_int32)
          WRITE(stage_diag_u,'(a,1x,z8.8,1x)') 'VDS_RDY',TRANSFER(rdy,0_int32)
          WRITE(stage_diag_u,'(a,1x,4(z8.8,1x))') 'VDS_C12_BEFORE_AFTER32', &
               TRANSFER(pr87_all_pair_diffusion_tendency32(i,k,j,2*p-1),0_int32), &
               TRANSFER(pr87_all_pair_diffusion_tendency32(i,k,j,2*p),0_int32), &
               TRANSFER(pr87_all_pair_diffusion_tendency32(i,k,j,2*p+3),0_int32), &
               TRANSFER(pr87_all_pair_diffusion_tendency32(i,k,j,2*p+4),0_int32)
          WRITE(stage_diag_u,'(a,1x,6(z16.16,1x))') 'VDS_C12_SOURCE_COMPONENTS', &
               TRANSFER(pr87_all_pair_diffusion_nonD64(i,k,j,2*p-1),0_int64), &
               TRANSFER(pr87_all_pair_diffusion_nonD64(i,k,j,2*p),0_int64), &
               TRANSFER(prepared_diffusion(i,k,j),0_int64), &
               TRANSFER(prepared_n_diffusion(i,k,j),0_int64), &
               TRANSFER(pr87_all_pair_diffusion_old(i,k,j,2*p-1),0_int64), &
               TRANSFER(pr87_all_pair_diffusion_old(i,k,j,2*p),0_int64)
          WRITE(stage_diag_u,'(a,1x,6(z16.16,1x))') 'VDS_C12_RAW_PROVENANCE', &
               TRANSFER(pr87_raw_qsrc(i,k,j,p),0_int64),TRANSFER(pr87_raw_nsrc(i,k,j,p),0_int64), &
               TRANSFER(pr87_later_qsrc(i,k,j,p),0_int64),TRANSFER(pr87_later_nsrc(i,k,j,p),0_int64), &
               TRANSFER(pr87_all_pair_diffusion_delta(i,k,j,2*p-1),0_int64), &
               TRANSFER(pr87_all_pair_diffusion_delta(i,k,j,2*p),0_int64)
          CLOSE(stage_diag_u)
          CALL wrf_error_fatal('PR87 unsafe complete source-prepared virtual donor')
        END IF
        donor_q(i,k,j,p)=source_sum64(1); donor_n(i,k,j,p)=source_sum64(2)
      END DO
    END DO
    END DO
    END DO
    cell=0
    DO j=jl,jh
    DO k=kl,kh
    DO i=il,ih
      cell=cell+1
      DO p=1,2
        IF (.NOT.source_first_pair(p)) CYCLE
        rate=air_tendency(q1(:,:,:,qindex(p)),n1(:,:,:,nindex(p)),i,k,j,p)
        qa64(cell,p)=rate(1); na64(cell,p)=rate(2)
      END DO
    END DO
    END DO
    END DO
    DEALLOCATE(prepared_q,prepared_n,prepared_diffusion,prepared_n_diffusion)
  END SUBROUTINE prepare_source_first_rates

  SUBROUTINE write_source_representation()
    ! W has pressure-carrier units. These amounts are NOT kg, energy, or physical phase transfers.
    REAL(real64) :: column(2,5),total(2,5),proposal(2),represented(2),delta(2)
    REAL(real64) :: later_amount(2),later_total(2),identity_max(2),physical_delta(2)
    INTEGER :: pair,x,y,z,c,unit,ios,changed,column_changed,maximum_k(2)
    OPEN(NEWUNIT=unit,FILE='pr87_source_representation.raw',STATUS='UNKNOWN', &
         POSITION='APPEND',ACTION='WRITE',IOSTAT=ios)
    IF (ios/=0) CALL wrf_error_fatal('PR87 source representation ledger open failed')
    WRITE(unit,*,IOSTAT=ios) 'SOURCE_REPRESENTATION_META',itimestep,rk, &
       'pressure amounts: dt*total_source, W*(physics_stage-old)+dt*later_source, delta, L1, max; Q,N'
    IF (ios/=0) CALL wrf_error_fatal('PR87 source representation metadata write failed')
    DO pair=1,2
      IF (.NOT.source_first_pair(pair)) CYCLE
      total=0.0_real64; changed=0; later_total=0.0_real64; identity_max=0.0_real64
      DO y=jl,jh
      DO x=il,ih
        column=0.0_real64; column_changed=0; maximum_k=0
        DO z=kl,kh
          c=((y-jl)*(kh-kl+1)+(z-kl))*(ih-il+1)+(x-il)+1
          proposal=REAL(dt,real64)*[REAL(qs(c,pair),real64),REAL(ns(c,pair),real64)]
          represented=REAL(oldcarrier(c),real64)* &
             ([REAL(qb(c,pair),real64),REAL(nb(c,pair),real64)]- &
              [REAL(q1(x,z,y,qindex(pair)),real64),REAL(n1(x,z,y,nindex(pair)),real64)])+ &
             REAL(dt,real64)*[qs64(c,pair),ns64(c,pair)]
          delta=represented-proposal
          later_amount=REAL(dt,real64)*[qs64(c,pair),ns64(c,pair)]
          later_total=later_total+later_amount
          physical_delta=(represented-later_amount)-REAL(dt,real64)* &
             ([REAL(qs(c,pair),real64),REAL(ns(c,pair),real64)]-[qs64(c,pair),ns64(c,pair)])
          identity_max=MAX(identity_max,ABS(delta-physical_delta))
          IF (.NOT.ALL(ieee_is_finite(delta))) &
            CALL wrf_error_fatal('PR87 nonfinite source representation ledger')
          IF (ANY(delta/=0.0_real64)) column_changed=column_changed+1
          WHERE (ABS(delta)>column(:,5)) maximum_k=z
          column(:,1)=column(:,1)+proposal; column(:,2)=column(:,2)+represented
          column(:,3)=column(:,3)+delta; column(:,4)=column(:,4)+ABS(delta)
          column(:,5)=MAX(column(:,5),ABS(delta))
        END DO
        IF (column_changed>0) THEN
          WRITE(unit,*,IOSTAT=ios) 'SOURCE_COLUMN',itimestep,rk,pair,x,y,column_changed,maximum_k,column
          IF (ios/=0) CALL wrf_error_fatal('PR87 source column ledger write failed')
        ENDIF
        changed=changed+column_changed
        total(:,1:4)=total(:,1:4)+column(:,1:4)
        total(:,5)=MAX(total(:,5),column(:,5))
      END DO
      END DO
      IF (.NOT.ALL(ieee_is_finite(total))) &
        CALL wrf_error_fatal('PR87 nonfinite source representation aggregate')
      WRITE(unit,*,IOSTAT=ios) 'SOURCE_TOTAL',itimestep,rk,pair,cells,changed,total
      IF (ios/=0) CALL wrf_error_fatal('PR87 source aggregate ledger write failed')
      IF (.NOT.ALL(ieee_is_finite(later_total)).OR..NOT.ALL(ieee_is_finite(identity_max))) &
        CALL wrf_error_fatal('PR87 nonfinite later source ledger')
      WRITE(unit,*,IOSTAT=ios) 'SOURCE_LATER_TOTAL',itimestep,rk,pair,later_total,identity_max
      IF (ios/=0) CALL wrf_error_fatal('PR87 later source ledger write failed')
    END DO
    CLOSE(unit,IOSTAT=ios)
    IF (ios/=0) CALL wrf_error_fatal('PR87 source representation ledger close failed')
  END SUBROUTINE write_source_representation

  LOGICAL FUNCTION prepared_donor_is_safe(q,n,density) RESULT(valid)
    REAL(real64),INTENT(IN) :: q,n
    REAL(real32),INTENT(IN) :: density
    REAL(real64) :: number_volume
    valid=.FALSE.
    IF (.NOT.ieee_is_finite(q).OR..NOT.ieee_is_finite(n)) RETURN
    IF (.NOT.ieee_is_finite(density)) RETURN
    IF (density<=0.0_real32) RETURN
    IF (q<0.0_real64.OR.n<0.0_real64) RETURN
    IF (q>REAL(HUGE(0.0_real32),real64).OR.n>REAL(HUGE(0.0_real32),real64)) RETURN
    IF ((q==0.0_real64).NEQV.(n==0.0_real64)) RETURN
    IF (n>0.0_real64) THEN
      number_volume=n*REAL(density,real64)
      IF (.NOT.ieee_is_finite(number_volume)) RETURN
      IF (number_volume<=0.5_real64*REAL(NEAREST(0.0_real32,1.0_real32),real64).OR. &
          number_volume>REAL(HUGE(0.0_real32),real64)) RETURN
    ENDIF
    valid=.TRUE.
  END FUNCTION prepared_donor_is_safe

  FUNCTION singleton_candidate(base,source,transport,oldmass,newmass,density,isnumber) RESULT(stored)
    REAL,INTENT(IN) :: base,source,oldmass,newmass,density
    REAL(real64),INTENT(IN) :: transport
    LOGICAL,INTENT(IN) :: isnumber
    REAL :: stored
    REAL(real64) :: value,product
    IF (.NOT.ieee_is_finite(base).OR..NOT.ieee_is_finite(source).OR. &
        .NOT.ieee_is_finite(newmass).OR.newmass<=0.0) &
      CALL wrf_error_fatal('PR85 invalid unpaired source or dry carrier')
    value=(REAL(oldmass,real64)*REAL(base,real64)+ &
           REAL(dt,real64)*(REAL(source,real64)+transport))/REAL(newmass,real64)
    IF (.NOT.ieee_is_finite(value).OR.value<0.0_real64.OR.value>REAL(HUGE(stored),real64)) &
      CALL wrf_error_fatal('PR85 unpaired completed source/transport state infeasible')
    stored=REAL(value,real32)
    IF (isnumber.AND.stored>0.0) THEN
      product=REAL(stored,real64)*REAL(density,real64)
      IF (.NOT.ieee_is_finite(product).OR.product>REAL(HUGE(stored),real64).OR. &
          product<=0.5_real64*2.0_real64**(-149)) &
        CALL wrf_error_fatal('PR85 ambient number density conversion infeasible')
    END IF
  END FUNCTION singleton_candidate
  FUNCTION air_tendency(mass,moment,i,k,j,pair) RESULT(value)
    REAL,INTENT(IN) :: mass(ims:ime,kms:kme,jms:jme),moment(ims:ime,kms:kme,jms:jme)
    INTEGER,INTENT(IN) :: i,k,j
    INTEGER,INTENT(IN),OPTIONAL :: pair
    REAL(real64) :: value(2),east(2),west(2),north(2),south(2),upper(2),lower(2)
    INTEGER :: donor
    donor=MERGE(i,i+1,ru(i+1,k,j)>=0.0)
    east=REAL(ru(i+1,k,j),real64)*donor_values(mass,moment,donor,k,j,pair)
    donor=MERGE(i-1,i,ru(i,k,j)>=0.0)
    west=REAL(ru(i,k,j),real64)*donor_values(mass,moment,donor,k,j,pair)
    donor=MERGE(j,j+1,rv(i,k,j+1)>=0.0)
    north=REAL(rv(i,k,j+1),real64)*donor_values(mass,moment,i,k,donor,pair)
    donor=MERGE(j-1,j,rv(i,k,j)>=0.0)
    south=REAL(rv(i,k,j),real64)*donor_values(mass,moment,i,k,donor,pair)
    upper=0.0_real64; lower=0.0_real64
    IF (k<kh) THEN
      donor=MERGE(k+1,k,ww(i,k+1,j)>=0.0)
      upper=REAL(ww(i,k+1,j),real64)*donor_values(mass,moment,i,donor,j,pair)
    END IF
    IF (k>kl) THEN
      donor=MERGE(k,k-1,ww(i,k,j)>=0.0)
      lower=REAL(ww(i,k,j),real64)*donor_values(mass,moment,i,donor,j,pair)
    END IF
    value=-REAL(msfty(i,j),real64)*( &
      REAL(msftx(i,j)*rdx,real64)*(east-west)+ &
      REAL(msftx(i,j)*rdy,real64)*(north-south)+REAL(rdnw(k),real64)*(upper-lower))
  END FUNCTION air_tendency

  FUNCTION donor_values(mass,moment,i,k,j,pair) RESULT(value)
    REAL,INTENT(IN) :: mass(ims:ime,kms:kme,jms:jme),moment(ims:ime,kms:kme,jms:jme)
    INTEGER,INTENT(IN) :: i,k,j
    INTEGER,INTENT(IN),OPTIONAL :: pair
    REAL(real64) :: value(2)
    value=[REAL(mass(i,k,j),real64),REAL(moment(i,k,j),real64)]
    IF (rk/=3) RETURN
    IF (.NOT.PRESENT(pair)) RETURN
    IF (pair>2) RETURN
    IF (.NOT.source_first_pair(pair)) RETURN
    value=[donor_q(i,k,j,pair),donor_n(i,k,j,pair)]
  END FUNCTION donor_values


END SUBROUTINE rk_update_joint_moments
END MODULE module_em

! Read-only cloud-pair summaries at completed state boundaries.
subroutine pr87_cloud_cycle(label, step, ims, ime, jms, jme, kms, kme, &
                           its, ite, jts, jte, kts, kte, qc, nc)
  use, intrinsic :: iso_fortran_env, only: real64, int32
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  implicit none
  character(*), intent(in) :: label
  integer, intent(in) :: step, ims, ime, jms, jme, kms, kme
  integer, intent(in) :: its, ite, jts, jte, kts, kte
  real, intent(in) :: qc(ims:ime,kms:kme,jms:jme), nc(ims:ime,kms:kme,jms:jme)
  integer :: i, j, k, unit, status, nonfinite, negative, mass_only, number_only
  integer :: first(3), probe(3)
  character(80) :: text
  real(real64) :: first_q, first_n

  nonfinite=0; negative=0; mass_only=0; number_only=0
  first=0; first_q=0; first_n=0
  do j=jts,jte
    do i=its,ite
      do k=kts,kte
        if (.not.ieee_is_finite(qc(i,k,j)) .or. .not.ieee_is_finite(nc(i,k,j))) then
          nonfinite=nonfinite+1
          cycle
        endif
        if (qc(i,k,j)<0 .or. nc(i,k,j)<0) negative=negative+1
        if (qc(i,k,j)>0 .and. nc(i,k,j)==0) mass_only=mass_only+1
        if (qc(i,k,j)==0 .and. nc(i,k,j)>0) number_only=number_only+1
        if (all(first==0)) then
          if ((qc(i,k,j)>0 .and. nc(i,k,j)==0) .or. &
              (qc(i,k,j)==0 .and. nc(i,k,j)>0)) then
            first=(/i,j,k/)
            first_q=real(qc(i,k,j),real64); first_n=real(nc(i,k,j),real64)
          endif
        endif
      enddo
    enddo
  enddo
  open(newunit=unit,file='pr87_cloud_cycle.log',status='unknown',position='append',iostat=status)
  if (status/=0) error stop 'PR87 cycle log open failed'
  write(unit,'(a,1x,a,11(1x,i0),2(1x,es24.16))') 'PR87_CLOUD',trim(label), &
       step,its,ite,jts,jte,kts,kte,nonfinite,negative,mass_only,number_only,first_q,first_n
  write(unit,'(a,1x,a,4(1x,i0),2(1x,es24.16))') 'PR87_FIRST',trim(label), &
       step,first,first_q,first_n
  call get_environment_variable('PR87_PROBE',text,status=status)
  if (status==0) then
    read(text,*,iostat=status) probe
    if (status/=0) error stop 'PR87 invalid probe coordinates'
    i=probe(1); j=probe(2); k=probe(3)
    if (i>=its .and. i<=ite .and. j>=jts .and. j<=jte .and. k>=kts .and. k<=kte) then
      write(unit,'(a,1x,a,4(1x,i0),2(1x,es24.16),2(1x,z8.8))') &
           'PR87_PROBE',trim(label),step,probe,real(qc(i,k,j),real64),real(nc(i,k,j),real64), &
           transfer(qc(i,k,j),0_int32),transfer(nc(i,k,j),0_int32)
    endif
  endif
  close(unit,iostat=status)
  if (status/=0) error stop 'PR87 cycle log close failed'
end subroutine pr87_cloud_cycle

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

subroutine pr87_number_public_store(q_internal, nvol_internal, dry_density, pidnr, power, &
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
end subroutine pr87_number_public_store

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

subroutine pr87_rain_density_store(itimestep,rk_step,ims,ime,kms,kme,jms,jme, &
     its,ite,jts,jte,kts,kte,al,alb,qrain,nrain,pidnr,power,lambda_min,lambda_max,valid)
  use iso_fortran_env, only: real32, real64
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  implicit none
  integer, intent(in) :: itimestep,rk_step,ims,ime,kms,kme,jms,jme
  integer, intent(in) :: its,ite,jts,jte,kts,kte
  real(real32), intent(in) :: al(ims:ime,kms:kme,jms:jme)
  real(real32), intent(in) :: alb(ims:ime,kms:kme,jms:jme)
  real(real32), intent(inout) :: qrain(ims:ime,kms:kme,jms:jme)
  real(real32), intent(in) :: nrain(ims:ime,kms:kme,jms:jme)
  real(real32), intent(in) :: pidnr,power,lambda_min,lambda_max
  logical, intent(out) :: valid
  interface
    subroutine pr85_dry_density_from_al_alb(al,alb,dry_density,valid)
      use iso_fortran_env, only: real32
      real, intent(in) :: al,alb
      real(real32), intent(out) :: dry_density
      logical, intent(out) :: valid
    end subroutine pr85_dry_density_from_al_alb
    subroutine pr87_number_volume_store(q_specific,n_specific,dry_density,pidnr,power, &
         lambda_min,lambda_max,q_stored,n_volume,valid,delta_q,delta_nvolume,adjustment)
      use iso_fortran_env, only: real32,real64
      real(real32), intent(in) :: q_specific,n_specific,dry_density,pidnr,power
      real(real32), intent(in) :: lambda_min,lambda_max
      real(real32), intent(out) :: q_stored,n_volume
      logical, intent(out) :: valid
      real(real64), intent(out) :: delta_q,delta_nvolume
      integer, intent(out) :: adjustment
    end subroutine pr87_number_volume_store
  end interface

  character(len=*), parameter :: ledger_name='pr87_rain_density_storage.raw'
  real(real32), allocatable :: q_candidate(:,:,:),rho_values(:,:,:),n_volume(:,:,:)
  real(real64), allocatable :: delta_q(:,:,:),delta_nvolume(:,:,:)
  real(real32) :: rho,q_stored,n_volume_stored
  real(real64) :: sum_delta_q,l1_delta_q,max_delta_q
  real(real64) :: sum_delta_nvolume,l1_delta_nvolume,max_delta_nvolume
  integer :: i,j,k,io_status,ledger_unit,processed,q_changed,nvolume_rounded
  integer :: failure_stage
  integer :: adjustment
  integer(kind=8) :: ledger_size
  logical :: density_valid,cell_valid,ledger_exists

  valid=.false.
  if (itimestep<1 .or. rk_step<1 .or. rk_step>3) return
  if (ims>ime .or. kms>kme .or. jms>jme .or. its<ims .or. ite>ime .or. &
      kts<kms .or. kte>kme .or. jts<jms .or. jte>jme .or. &
      its>ite .or. kts>kte .or. jts>jte) return
  if (.not.all(ieee_is_finite([pidnr,power,lambda_min,lambda_max]))) return
  if (pidnr<=0.0_real32 .or. power<=0.0_real32 .or. power>8.0_real32 .or. &
      lambda_min<=0.0_real32 .or. lambda_max<lambda_min) return

  allocate(q_candidate(its:ite,kts:kte,jts:jte), &
           rho_values(its:ite,kts:kte,jts:jte), &
           n_volume(its:ite,kts:kte,jts:jte), &
           delta_q(its:ite,kts:kte,jts:jte), &
           delta_nvolume(its:ite,kts:kte,jts:jte))
  sum_delta_q=0.0_real64; l1_delta_q=0.0_real64; max_delta_q=0.0_real64
  sum_delta_nvolume=0.0_real64; l1_delta_nvolume=0.0_real64; max_delta_nvolume=0.0_real64
  processed=0; q_changed=0; nvolume_rounded=0

  ! Validate every cell and stage all Q changes before touching model state.
  do j=jts,jte
    do k=kts,kte
      do i=its,ite
        rho=0.0_real32
        call pr85_dry_density_from_al_alb(al(i,k,j),alb(i,k,j),rho,density_valid)
        if (.not.density_valid) then
          failure_stage=1
          write(*,*) 'PR87_RAIN_DENSITY_REJECT',itimestep,rk_step,i,j,k, &
               failure_stage,qrain(i,k,j),nrain(i,k,j),rho
          goto 900
        end if
        call pr87_number_volume_store(qrain(i,k,j),nrain(i,k,j),rho,pidnr,power, &
             lambda_min,lambda_max,q_stored,n_volume_stored,cell_valid, &
             delta_q(i,k,j),delta_nvolume(i,k,j),adjustment)
        if (.not.cell_valid) then
          failure_stage=2
          write(*,*) 'PR87_RAIN_DENSITY_REJECT',itimestep,rk_step,i,j,k, &
               failure_stage,qrain(i,k,j),nrain(i,k,j),rho
          goto 900
        end if
        if (.not.ieee_is_finite(delta_q(i,k,j)) .or. &
            .not.ieee_is_finite(delta_nvolume(i,k,j)) .or. &
            .not.ieee_is_finite(q_stored) .or. .not.ieee_is_finite(n_volume_stored)) then
          failure_stage=3
          write(*,*) 'PR87_RAIN_DENSITY_REJECT',itimestep,rk_step,i,j,k, &
               failure_stage,qrain(i,k,j),nrain(i,k,j),rho
          goto 900
        end if
        q_candidate(i,k,j)=q_stored
        rho_values(i,k,j)=rho
        n_volume(i,k,j)=n_volume_stored
        processed=processed+1
        sum_delta_q=sum_delta_q+delta_q(i,k,j)
        l1_delta_q=l1_delta_q+abs(delta_q(i,k,j))
        max_delta_q=max(max_delta_q,abs(delta_q(i,k,j)))
        sum_delta_nvolume=sum_delta_nvolume+delta_nvolume(i,k,j)
        l1_delta_nvolume=l1_delta_nvolume+abs(delta_nvolume(i,k,j))
        max_delta_nvolume=max(max_delta_nvolume,abs(delta_nvolume(i,k,j)))
        if (delta_q(i,k,j)/=0.0_real64) q_changed=q_changed+1
        if (delta_nvolume(i,k,j)/=0.0_real64) nvolume_rounded=nvolume_rounded+1
      end do
    end do
  end do

  inquire(file=ledger_name,exist=ledger_exists,size=ledger_size,iostat=io_status)
  if (io_status/=0) goto 900
  open(newunit=ledger_unit,file=ledger_name,status='unknown',position='append', &
       action='write',iostat=io_status)
  if (io_status/=0) goto 900
  if (.not.ledger_exists .or. ledger_size==0_8) then
    write(ledger_unit,'(a)',iostat=io_status) &
      '# PR87_RAIN_DENSITY_SUM time,rk,i0,i1,j0,j1,k0,k1,cells,Q_changed,prospective_Nvol_rounding_nonzero,'// &
      'sum_delta_Q_specific,L1_delta_Q_specific,max_abs_delta_Q_specific,'// &
      'sum_prospective_delta_Nvolume,L1_prospective_delta_Nvolume,max_abs_prospective_delta_Nvolume; '// &
      'N_specific and AL/ALB are unchanged; Nvolume deltas are predicted ordinary REAL32 conversion rounding, '// &
      'not committed N or spatially/area/time weighted totals. Sparse CELL rows report actual Q changes only.'
    if (io_status/=0) then
      close(ledger_unit)
      goto 900
    end if
  end if
  do j=jts,jte
    do k=kts,kte
      do i=its,ite
        if (delta_q(i,k,j)/=0.0_real64) then
          write(ledger_unit,'(a,5i10,1p,7e24.16)',iostat=io_status) &
            'PR87_RAIN_DENSITY_CELL',itimestep,rk_step,i,j,k, &
            real(rho_values(i,k,j),real64),real(qrain(i,k,j),real64), &
            real(q_candidate(i,k,j),real64),real(nrain(i,k,j),real64), &
            real(n_volume(i,k,j),real64),delta_q(i,k,j),delta_nvolume(i,k,j)
          if (io_status/=0) then
            close(ledger_unit)
            goto 900
          end if
        end if
      end do
    end do
  end do
  write(ledger_unit,'(a,11i10,1p,6e24.16)',iostat=io_status) &
    'PR87_RAIN_DENSITY_SUM',itimestep,rk_step,its,ite,jts,jte,kts,kte, &
    processed,q_changed,nvolume_rounded,sum_delta_q,l1_delta_q,max_delta_q, &
    sum_delta_nvolume,l1_delta_nvolume,max_delta_nvolume
  if (io_status/=0) then
    close(ledger_unit)
    goto 900
  end if
  close(ledger_unit,iostat=io_status)
  if (io_status/=0) goto 900

  do j=jts,jte
    do k=kts,kte
      do i=its,ite
        qrain(i,k,j)=q_candidate(i,k,j)
      end do
    end do
  end do
  valid=.true.
900 continue
  deallocate(q_candidate,rho_values,n_volume,delta_q,delta_nvolume)
end subroutine pr87_rain_density_store

subroutine pr87_qn_density_store(itimestep,rk_step,ims,ime,kms,kme,jms,jme, &
     its,ite,jts,jte,kts,kte,al,alb,qcloud,ncloud,qrain,nrain, &
     cloud_pidn,cloud_power,cloud_lambda_min,cloud_lambda_max, &
     rain_pidn,rain_power,rain_lambda_min,rain_lambda_max,valid)
  use iso_fortran_env, only: real32,real64
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  implicit none
  integer, intent(in) :: itimestep,rk_step,ims,ime,kms,kme,jms,jme
  integer, intent(in) :: its,ite,jts,jte,kts,kte
  real(real32), intent(in) :: al(ims:ime,kms:kme,jms:jme)
  real(real32), intent(in) :: alb(ims:ime,kms:kme,jms:jme)
  real(real32), intent(inout) :: qcloud(ims:ime,kms:kme,jms:jme)
  real(real32), intent(in) :: ncloud(ims:ime,kms:kme,jms:jme)
  real(real32), intent(inout) :: qrain(ims:ime,kms:kme,jms:jme)
  real(real32), intent(in) :: nrain(ims:ime,kms:kme,jms:jme)
  real(real32), intent(in) :: cloud_pidn,cloud_power,cloud_lambda_min,cloud_lambda_max
  real(real32), intent(in) :: rain_pidn,rain_power,rain_lambda_min,rain_lambda_max
  logical, intent(out) :: valid

  interface
    subroutine pr85_dry_density_from_al_alb(al,alb,dry_density,valid)
      use iso_fortran_env, only: real32
      real, intent(in) :: al,alb
      real(real32), intent(out) :: dry_density
      logical, intent(out) :: valid
    end subroutine pr85_dry_density_from_al_alb
    subroutine pr87_number_volume_store(q_specific,n_specific,dry_density,pidnr,power, &
         lambda_min,lambda_max,q_stored,n_volume,valid,delta_q,delta_nvolume,adjustment)
      use iso_fortran_env, only: real32,real64
      real(real32), intent(in) :: q_specific,n_specific,dry_density,pidnr,power
      real(real32), intent(in) :: lambda_min,lambda_max
      real(real32), intent(out) :: q_stored,n_volume
      logical, intent(out) :: valid
      real(real64), intent(out) :: delta_q,delta_nvolume
      integer, intent(out) :: adjustment
    end subroutine pr87_number_volume_store
  end interface

  character(len=*), parameter :: ledger_name='pr87_qn_density_storage.raw'
  real(real32), allocatable :: qcloud_candidate(:,:,:),qrain_candidate(:,:,:)
  real(real32), allocatable :: rho_values(:,:,:),ncloud_volume(:,:,:),nrain_volume(:,:,:)
  real(real64), allocatable :: dqcloud(:,:,:),dqrain(:,:,:)
  real(real64), allocatable :: dncloud_volume(:,:,:),dnrain_volume(:,:,:)
  real(real32) :: rho,q_stored,n_volume_stored
  real(real64) :: sum_dqc,l1_dqc,max_dqc,sum_dqr,l1_dqr,max_dqr
  real(real64) :: sum_dncvol,l1_dncvol,max_dncvol,sum_dnrvol,l1_dnrvol,max_dnrvol
  integer :: i,j,k,io_status,ledger_unit,processed,alloc_status,failure_stage
  integer :: qcloud_changed,qrain_changed,ncloud_rounding,nrain_rounding
  integer :: cloud_adjustment,rain_adjustment
  integer(kind=8) :: ledger_size
  logical :: density_valid,cell_valid,ledger_exists

  valid=.false.
  if (itimestep<1 .or. rk_step<1 .or. rk_step>3) return
  if (ims>ime .or. kms>kme .or. jms>jme .or. its<ims .or. ite>ime .or. &
      kts<kms .or. kte>kme .or. jts<jms .or. jte>jme .or. &
      its>ite .or. kts>kte .or. jts>jte) return
  if (.not.all(ieee_is_finite([cloud_pidn,cloud_power,cloud_lambda_min, &
      cloud_lambda_max,rain_pidn,rain_power,rain_lambda_min,rain_lambda_max]))) return

  allocate(qcloud_candidate(its:ite,kts:kte,jts:jte), &
           qrain_candidate(its:ite,kts:kte,jts:jte), &
           rho_values(its:ite,kts:kte,jts:jte), &
           ncloud_volume(its:ite,kts:kte,jts:jte), &
           nrain_volume(its:ite,kts:kte,jts:jte), &
           dqcloud(its:ite,kts:kte,jts:jte),dqrain(its:ite,kts:kte,jts:jte), &
           dncloud_volume(its:ite,kts:kte,jts:jte), &
           dnrain_volume(its:ite,kts:kte,jts:jte),stat=alloc_status)
  if (alloc_status/=0) then
    if (allocated(qcloud_candidate)) deallocate(qcloud_candidate)
    if (allocated(qrain_candidate)) deallocate(qrain_candidate)
    if (allocated(rho_values)) deallocate(rho_values)
    if (allocated(ncloud_volume)) deallocate(ncloud_volume)
    if (allocated(nrain_volume)) deallocate(nrain_volume)
    if (allocated(dqcloud)) deallocate(dqcloud)
    if (allocated(dqrain)) deallocate(dqrain)
    if (allocated(dncloud_volume)) deallocate(dncloud_volume)
    if (allocated(dnrain_volume)) deallocate(dnrain_volume)
    return
  end if

  sum_dqc=0.0_real64; l1_dqc=0.0_real64; max_dqc=0.0_real64
  sum_dqr=0.0_real64; l1_dqr=0.0_real64; max_dqr=0.0_real64
  sum_dncvol=0.0_real64; l1_dncvol=0.0_real64; max_dncvol=0.0_real64
  sum_dnrvol=0.0_real64; l1_dnrvol=0.0_real64; max_dnrvol=0.0_real64
  processed=0; qcloud_changed=0; qrain_changed=0
  ncloud_rounding=0; nrain_rounding=0

  ! Stage and validate both species for every tile cell before writing or commit.
  do j=jts,jte
    do k=kts,kte
      do i=its,ite
        rho=0.0_real32
        call pr85_dry_density_from_al_alb(al(i,k,j),alb(i,k,j),rho,density_valid)
        if (.not.density_valid) then
          failure_stage=1
          write(*,*) 'PR87_QN_DENSITY_REJECT',itimestep,rk_step,1,i,j,k, &
               failure_stage,qcloud(i,k,j),ncloud(i,k,j),qrain(i,k,j),nrain(i,k,j),rho
          goto 900
        end if

        call pr87_number_volume_store(qcloud(i,k,j),ncloud(i,k,j),rho, &
             cloud_pidn,cloud_power,cloud_lambda_min,cloud_lambda_max, &
             q_stored,n_volume_stored,cell_valid,dqcloud(i,k,j), &
             dncloud_volume(i,k,j),cloud_adjustment)
        if (.not.cell_valid .or. .not.ieee_is_finite(q_stored) .or. &
            .not.ieee_is_finite(n_volume_stored) .or. &
            .not.ieee_is_finite(dqcloud(i,k,j)) .or. &
            .not.ieee_is_finite(dncloud_volume(i,k,j))) then
          failure_stage=2
          write(*,*) 'PR87_QN_DENSITY_REJECT',itimestep,rk_step,1,i,j,k, &
               failure_stage,qcloud(i,k,j),ncloud(i,k,j),qrain(i,k,j),nrain(i,k,j),rho
          goto 900
        end if
        qcloud_candidate(i,k,j)=q_stored
        ncloud_volume(i,k,j)=n_volume_stored

        call pr87_number_volume_store(qrain(i,k,j),nrain(i,k,j),rho, &
             rain_pidn,rain_power,rain_lambda_min,rain_lambda_max, &
             q_stored,n_volume_stored,cell_valid,dqrain(i,k,j), &
             dnrain_volume(i,k,j),rain_adjustment)
        if (.not.cell_valid .or. .not.ieee_is_finite(q_stored) .or. &
            .not.ieee_is_finite(n_volume_stored) .or. &
            .not.ieee_is_finite(dqrain(i,k,j)) .or. &
            .not.ieee_is_finite(dnrain_volume(i,k,j))) then
          failure_stage=3
          write(*,*) 'PR87_QN_DENSITY_REJECT',itimestep,rk_step,2,i,j,k, &
               failure_stage,qcloud(i,k,j),ncloud(i,k,j),qrain(i,k,j),nrain(i,k,j),rho
          goto 900
        end if
        qrain_candidate(i,k,j)=q_stored
        nrain_volume(i,k,j)=n_volume_stored
        rho_values(i,k,j)=rho

        processed=processed+1
        sum_dqc=sum_dqc+dqcloud(i,k,j); l1_dqc=l1_dqc+abs(dqcloud(i,k,j))
        max_dqc=max(max_dqc,abs(dqcloud(i,k,j)))
        sum_dqr=sum_dqr+dqrain(i,k,j); l1_dqr=l1_dqr+abs(dqrain(i,k,j))
        max_dqr=max(max_dqr,abs(dqrain(i,k,j)))
        sum_dncvol=sum_dncvol+dncloud_volume(i,k,j)
        l1_dncvol=l1_dncvol+abs(dncloud_volume(i,k,j))
        max_dncvol=max(max_dncvol,abs(dncloud_volume(i,k,j)))
        sum_dnrvol=sum_dnrvol+dnrain_volume(i,k,j)
        l1_dnrvol=l1_dnrvol+abs(dnrain_volume(i,k,j))
        max_dnrvol=max(max_dnrvol,abs(dnrain_volume(i,k,j)))
        if (dqcloud(i,k,j)/=0.0_real64) qcloud_changed=qcloud_changed+1
        if (dqrain(i,k,j)/=0.0_real64) qrain_changed=qrain_changed+1
        if (dncloud_volume(i,k,j)/=0.0_real64) ncloud_rounding=ncloud_rounding+1
        if (dnrain_volume(i,k,j)/=0.0_real64) nrain_rounding=nrain_rounding+1
      end do
    end do
  end do

  inquire(file=ledger_name,exist=ledger_exists,size=ledger_size,iostat=io_status)
  if (io_status/=0) then
    write(*,*) 'PR87_QN_DENSITY_IO_REJECT',itimestep,rk_step,1,io_status
    goto 900
  end if
  open(newunit=ledger_unit,file=ledger_name,status='unknown',position='append', &
       action='write',iostat=io_status)
  if (io_status/=0) then
    write(*,*) 'PR87_QN_DENSITY_IO_REJECT',itimestep,rk_step,2,io_status
    goto 900
  end if
  if (.not.ledger_exists .or. ledger_size==0_8) then
    write(ledger_unit,'(a)',iostat=io_status) &
      '# PR87_QN_DENSITY_CELL time,rk,species_id,i,j,k,rho[kg/m3],Qbefore[kg/kg],Qafter[kg/kg],'// &
      'Nspecific[number/kg],Nvolume_predicted[number/m3],dQ_specific[kg/kg],dNvolume_predicted[number/m3]; '// &
      'prospective Nvolume is ordinary R32 conversion, not committed N.'
    if (io_status/=0) then
      close(ledger_unit)
      write(*,*) 'PR87_QN_DENSITY_IO_REJECT',itimestep,rk_step,3,io_status
      goto 900
    end if
    write(ledger_unit,'(a)',iostat=io_status) &
      '# PR87_QN_DENSITY_SUM time,rk,i0,i1,j0,j1,k0,k1,cells,Qcloud_changed,Qrain_changed,'// &
      'Ncloud_volume_rounding_nonzero,Nrain_volume_rounding_nonzero,'// &
      'sum_dQcloud,L1_dQcloud,max_abs_dQcloud,sum_dQrain,L1_dQrain,max_abs_dQrain,'// &
      'sum_prospective_dNcloudvol,L1_prospective_dNcloudvol,max_abs_prospective_dNcloudvol,'// &
      'sum_prospective_dNrainvol,L1_prospective_dNrainvol,max_abs_prospective_dNrainvol; '// &
      'unweighted diagnostics; prospective Nvolume deltas are not committed or conserved totals.'
    if (io_status/=0) then
      close(ledger_unit)
      write(*,*) 'PR87_QN_DENSITY_IO_REJECT',itimestep,rk_step,4,io_status
      goto 900
    end if
  end if

  do j=jts,jte
    do k=kts,kte
      do i=its,ite
        if (dqcloud(i,k,j)/=0.0_real64) then
          write(ledger_unit,'(a,6i10,1p,7e24.16)',iostat=io_status) &
            'PR87_QN_DENSITY_CELL',itimestep,rk_step,1,i,j,k, &
            real(rho_values(i,k,j),real64),real(qcloud(i,k,j),real64), &
            real(qcloud_candidate(i,k,j),real64),real(ncloud(i,k,j),real64), &
            real(ncloud_volume(i,k,j),real64),dqcloud(i,k,j),dncloud_volume(i,k,j)
          if (io_status/=0) then
            close(ledger_unit)
            write(*,*) 'PR87_QN_DENSITY_IO_REJECT',itimestep,rk_step,5,io_status
            goto 900
          end if
        end if
        if (dqrain(i,k,j)/=0.0_real64) then
          write(ledger_unit,'(a,6i10,1p,7e24.16)',iostat=io_status) &
            'PR87_QN_DENSITY_CELL',itimestep,rk_step,2,i,j,k, &
            real(rho_values(i,k,j),real64),real(qrain(i,k,j),real64), &
            real(qrain_candidate(i,k,j),real64),real(nrain(i,k,j),real64), &
            real(nrain_volume(i,k,j),real64),dqrain(i,k,j),dnrain_volume(i,k,j)
          if (io_status/=0) then
            close(ledger_unit)
            write(*,*) 'PR87_QN_DENSITY_IO_REJECT',itimestep,rk_step,6,io_status
            goto 900
          end if
        end if
      end do
    end do
  end do
  write(ledger_unit,'(a,13i10,1p,12e24.16)',iostat=io_status) &
    'PR87_QN_DENSITY_SUM',itimestep,rk_step,its,ite,jts,jte,kts,kte,processed, &
    qcloud_changed,qrain_changed,ncloud_rounding,nrain_rounding, &
    sum_dqc,l1_dqc,max_dqc,sum_dqr,l1_dqr,max_dqr, &
    sum_dncvol,l1_dncvol,max_dncvol,sum_dnrvol,l1_dnrvol,max_dnrvol
  if (io_status/=0) then
    close(ledger_unit)
    write(*,*) 'PR87_QN_DENSITY_IO_REJECT',itimestep,rk_step,7,io_status
    goto 900
  end if
  close(ledger_unit,iostat=io_status)
  if (io_status/=0) then
    write(*,*) 'PR87_QN_DENSITY_IO_REJECT',itimestep,rk_step,8,io_status
    goto 900
  end if

  ! The tile commit is the only mutation point; both Q species move together.
  do j=jts,jte
    do k=kts,kte
      do i=its,ite
        qcloud(i,k,j)=qcloud_candidate(i,k,j)
        qrain(i,k,j)=qrain_candidate(i,k,j)
      end do
    end do
  end do
  valid=.true.
900 continue
  deallocate(qcloud_candidate,qrain_candidate,rho_values,ncloud_volume,nrain_volume, &
             dqcloud,dqrain,dncloud_volume,dnrain_volume)
end subroutine pr87_qn_density_store

SUBROUTINE pr98_dump3(tag,a,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte)
  IMPLICIT NONE
  CHARACTER(*), INTENT(IN) :: tag
  INTEGER, INTENT(IN) :: ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte
  REAL, INTENT(IN) :: a(ims:ime,kms:kme,jms:jme)
  CHARACTER(160), SAVE :: seen(512)
  INTEGER, SAVE :: nseen=0
  CHARACTER(160) :: key
  CHARACTER(32) :: tile
  INTEGER :: unit, q
  WRITE(tile,'(6(I0,"_"))') its,ite,jts,jte,kts,kte
  key=TRIM(tag)//'_'//TRIM(tile)
  DO q=1,nseen
    IF (TRIM(seen(q)) == TRIM(key)) RETURN
  END DO
  IF (nseen >= SIZE(seen)) RETURN
  nseen=nseen+1
  seen(nseen)=key
  OPEN(NEWUNIT=unit,FILE='pr98_'//TRIM(key)//'.bin',STATUS='replace', &
       ACCESS='stream',FORM='unformatted',ACTION='write')
  WRITE(unit) ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte
  WRITE(unit) a
  CLOSE(unit)
END SUBROUTINE pr98_dump3

SUBROUTINE pr98_dump2(tag,a,ims,ime,jms,jme,its,ite,jts,jte)
  IMPLICIT NONE
  CHARACTER(*), INTENT(IN) :: tag
  INTEGER, INTENT(IN) :: ims,ime,jms,jme,its,ite,jts,jte
  REAL, INTENT(IN) :: a(ims:ime,jms:jme)
  CHARACTER(160), SAVE :: seen(512)
  INTEGER, SAVE :: nseen=0
  CHARACTER(160) :: key
  CHARACTER(32) :: tile
  INTEGER :: unit, q
  WRITE(tile,'(4(I0,"_"))') its,ite,jts,jte
  key=TRIM(tag)//'_'//TRIM(tile)
  DO q=1,nseen
    IF (TRIM(seen(q)) == TRIM(key)) RETURN
  END DO
  IF (nseen >= SIZE(seen)) RETURN
  nseen=nseen+1
  seen(nseen)=key
  OPEN(NEWUNIT=unit,FILE='pr98_'//TRIM(key)//'.bin',STATUS='replace', &
       ACCESS='stream',FORM='unformatted',ACTION='write')
  WRITE(unit) ims,ime,jms,jme,its,ite,jts,jte
  WRITE(unit) a
  CLOSE(unit)
END SUBROUTINE pr98_dump2

SUBROUTINE pr98_dump1(tag,a,kms,kme,kts,kte)
  IMPLICIT NONE
  CHARACTER(*), INTENT(IN) :: tag
  INTEGER, INTENT(IN) :: kms,kme,kts,kte
  REAL, INTENT(IN) :: a(kms:kme)
  INTEGER :: unit
  OPEN(NEWUNIT=unit,FILE='pr98_'//TRIM(tag)//'.bin',STATUS='replace', &
       ACCESS='stream',FORM='unformatted',ACTION='write')
  WRITE(unit) kms,kme,kts,kte
  WRITE(unit) a
  CLOSE(unit)
END SUBROUTINE pr98_dump1

SUBROUTINE pr98_dump0(tag,value)
  IMPLICIT NONE
  CHARACTER(*), INTENT(IN) :: tag
  REAL, INTENT(IN) :: value
  LOGICAL, SAVE :: done=.FALSE.
  INTEGER :: unit
  IF (done) RETURN
  done=.TRUE.
  OPEN(NEWUNIT=unit,FILE='pr98_'//TRIM(tag)//'.bin',STATUS='replace', &
       ACCESS='stream',FORM='unformatted',ACTION='write')
  WRITE(unit) value
  CLOSE(unit)
END SUBROUTINE pr98_dump0

