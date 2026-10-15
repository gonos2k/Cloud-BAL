module cloud_bal_joint_transport
  use iso_fortran_env, only: real32, real64
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  implicit none
  private

  public :: joint_moment_is_valid, joint_qnb_update

contains

  logical function joint_moment_is_valid(q, n, dry_density, minimum_ratio, maximum_ratio)
    ! Test one stored REAL32 pair with the same representation and endpoint
    ! tolerance used by the grouped candidate and its source-only diagnostic.
    real(real32), intent(in) :: q, n, dry_density
    real(real64), intent(in) :: minimum_ratio, maximum_ratio
    real(real64) :: q64, n64, pair_ratio, tolerance, moment_per_volume

    joint_moment_is_valid = .false.
    if (.not. ieee_is_finite(q) .or. .not. ieee_is_finite(n) .or. &
        .not. ieee_is_finite(dry_density) .or. &
        .not. ieee_is_finite(minimum_ratio) .or. .not. ieee_is_finite(maximum_ratio)) return
    if (dry_density <= 0.0_real32 .or. minimum_ratio <= 0.0_real64 .or. &
        maximum_ratio < minimum_ratio) return

    q64 = real(q,real64)
    n64 = real(n,real64)
    if (q64 < 0.0_real64 .or. n64 < 0.0_real64) return
    if (n64 > 0.0_real64) then
      moment_per_volume = n64*real(dry_density,real64)
      if (.not. ieee_is_finite(moment_per_volume) .or. &
          moment_per_volume <= 0.5_real64*real(nearest(0.0_real32,1.0_real32),real64) .or. &
          moment_per_volume > real(huge(0.0_real32),real64)) return
    end if
    if (q64 == 0.0_real64) then
      if (n64 /= 0.0_real64) return
    else
      if (n64 == 0.0_real64) return
      pair_ratio = q64/n64
      tolerance = 8.0_real64*abs(real(spacing(real(minimum_ratio,real32)),real64))
      if (pair_ratio < minimum_ratio-tolerance) return
      tolerance = 8.0_real64*abs(real(spacing(real(maximum_ratio,real32)),real64))
      if (pair_ratio > maximum_ratio+tolerance) return
    end if
    joint_moment_is_valid = .true.
  end function joint_moment_is_valid

  subroutine joint_qnb_update(q_base, n_base, q_stage, n_stage, q_source, n_source, &
                              q_transport, n_transport, carrier_old, carrier_new, dry_density, &
                              dt, min_particle_mass, max_particle_mass, theta, &
                              rejected_q, rejected_n, feasible)
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

    real(real32), allocatable :: q_candidate(:,:), n_candidate(:,:)
    real(real64) :: low, high, trial
    integer :: iteration, cell, pair, ncells, npairs

    feasible = .false.
    theta = 0.0_real64
    rejected_q = 0.0_real64
    rejected_n = 0.0_real64
    ncells = size(q_base, 1)
    npairs = size(q_base, 2)
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
    if (any(min_particle_mass <= 0.0_real64) .or. &
        any(max_particle_mass < min_particle_mass)) return
    if (.not. ieee_is_finite(dt) .or. dt <= 0.0_real32 .or. &
        any(.not. ieee_is_finite(carrier_old)) .or. &
        any(.not. ieee_is_finite(carrier_new)) .or. &
        any(.not. ieee_is_finite(dry_density)) .or. &
        any(.not. ieee_is_finite(q_base)) .or. any(.not. ieee_is_finite(n_base)) .or. &
        any(.not. ieee_is_finite(q_source)) .or. any(.not. ieee_is_finite(n_source)) .or. &
        any(.not. ieee_is_finite(q_transport)) .or. any(.not. ieee_is_finite(n_transport))) return
    if (any(.not. ieee_is_finite(min_particle_mass)) .or. &
        any(.not. ieee_is_finite(max_particle_mass))) return
    if (any(carrier_old <= 0.0_real32) .or. any(carrier_new <= 0.0_real32) .or. &
        any(dry_density <= 0.0_real32)) return

    allocate(q_candidate(ncells,npairs), n_candidate(ncells,npairs))
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

    call form_candidate(theta)
    if (.not. candidate_is_feasible()) return
    do pair = 1, npairs
      do cell = 1, ncells
        rejected_q(pair) = rejected_q(pair) + &
          real(dt,real64)*(1.0_real64-theta)*real(q_transport(cell,pair),real64)
        rejected_n(pair) = rejected_n(pair) + &
          real(dt,real64)*(1.0_real64-theta)*real(n_transport(cell,pair),real64)
      end do
    end do
    q_stage = q_candidate
    n_stage = n_candidate
    feasible = .true.

  contains

    subroutine form_candidate(scale)
      real(real64), intent(in) :: scale
      real(real64) :: q_value, n_value
      integer :: i, p

      do p = 1, npairs
        do i = 1, ncells
          q_value = (real(carrier_old(i),real64)*real(q_base(i,p),real64) + &
            real(dt,real64)*(real(q_source(i,p),real64) + scale*real(q_transport(i,p),real64))) &
            / real(carrier_new(i),real64)
          n_value = (real(carrier_old(i),real64)*real(n_base(i,p),real64) + &
            real(dt,real64)*(real(n_source(i,p),real64) + scale*real(n_transport(i,p),real64))) &
            / real(carrier_new(i),real64)
          if (.not. ieee_is_finite(q_value) .or. .not. ieee_is_finite(n_value) .or. &
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

      candidate_is_feasible = .false.
      do p = 1, npairs
        do i = 1, ncells
          if (.not. joint_moment_is_valid(q_candidate(i,p), n_candidate(i,p), dry_density(i), &
                                           min_particle_mass(p), max_particle_mass(p))) return
        end do
      end do
      candidate_is_feasible = .true.
    end function candidate_is_feasible

  end subroutine joint_qnb_update

end module cloud_bal_joint_transport
