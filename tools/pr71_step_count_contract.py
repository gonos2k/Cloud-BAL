#!/usr/bin/env python3
"""Apply the PR71 checked integer substep-count transform to one frozen source."""

from __future__ import annotations

import argparse
import difflib
import hashlib
from pathlib import Path


SOURCE_SHA256 = "5de1884ab59e3de30a3e4ef1d8317405f1ba0591cf7ed9aa6fbca574d5233f41"

HELPER = """    ! PR71_STEP_COUNT_CONTRACT_BEGIN
    pure subroutine checked_substep_count(rate, timestep, count, valid)
      double precision, intent(in) :: rate
      real, intent(in) :: timestep
      integer, intent(out) :: count
      logical, intent(out) :: valid
      double precision :: dt64, scaled_argument

      count = 0
      valid = .false.
      if (.not. ieee_is_finite(rate)) return
      if (.not. ieee_is_finite(timestep)) return
      if (timestep <= 0.0) return
      dt64 = real(timestep, kind=kind(rate))
      if (dt64 > 1.0d0) then
        if (abs(rate) > huge(rate) / dt64) return
      end if
      scaled_argument = rate * dt64 + 0.5d0
      if (.not. (scaled_argument < real(huge(count), kind=kind(rate)) + 0.5d0)) return
      if (.not. (scaled_argument > real(-huge(count) - 1, kind=kind(rate)) - 0.5d0)) return

      ! Keep the original expression and minimum-one rule on valid inputs.
      count = max(nint(rate * timestep + .5), 1)
      valid = .true.
    end subroutine checked_substep_count
    ! PR71_STEP_COUNT_CONTRACT_END
"""


OLD_COUNTS = (
    "          numdt(i)=max(nint(max(mass_velocity_rate(i,k,1),number_velocity_rate(i,k,1),mass_velocity_rate(i,k,2),mass_velocity_rate(i,k,3))*dtcld+.5),1)",
    "          numdt_i(i) = max(nint(max(mass_velocity_rate(i,k,4),number_velocity_rate(i,k,2))*dtcld+.5),1)",
)
NEW_COUNTS = """          step_rate = max(mass_velocity_rate(i,k,1),number_velocity_rate(i,k,1), &
                          mass_velocity_rate(i,k,2),mass_velocity_rate(i,k,3))
          call checked_substep_count(step_rate, dtcld, numdt(i), step_count_valid)
          if (.not. step_count_valid) then
            write(*,*) 'PR71_STEP_COUNT_REJECT i,k,rate,dt=', i, k, step_rate, dtcld
            error stop 'invalid PR71 KDM6 substep count'
          endif
          step_rate = max(mass_velocity_rate(i,k,4),number_velocity_rate(i,k,2))
          call checked_substep_count(step_rate, dtcld, numdt_i(i), step_count_valid)
          if (.not. step_count_valid) then
            write(*,*) 'PR71_STEP_COUNT_REJECT_ICE i,k,rate,dt=', i, k, step_rate, dtcld
            error stop 'invalid PR71 KDM6 ice substep count'
          endif"""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def transform(source: str) -> str:
    contains_anchor = "    contains\n\n    pure elemental subroutine moist_to_dry_density"
    if source.count(contains_anchor) != 1:
        raise ValueError("expected unique KDM6 module CONTAINS anchor")
    if source.count(OLD_COUNTS[0]) != 1 or source.count(OLD_COUNTS[1]) != 1:
        raise ValueError("expected both exact numdt source expressions once")
    if "integer :: step_count_valid" in source or "logical :: step_count_valid" in source:
        raise ValueError("step-count locals already exist")
    updated = source.replace(
        contains_anchor,
        "    contains\n\n" + HELPER + "\n    pure elemental subroutine moist_to_dry_density",
        1,
    )
    updated = updated.replace(
        "   logical :: carrier_valid\n",
        "   logical :: carrier_valid, step_count_valid\n",
        1,
    )
    declaration = "   double precision :: step_rate\n"
    anchor = "   double precision, dimension(its:ite,kts:kte,2) :: number_velocity_rate\n"
    if updated.count(anchor) != 1:
        raise ValueError("missing unique KDM6 velocity-rate declaration")
    updated = updated.replace(anchor, anchor + declaration, 1)
    updated = updated.replace("\n".join(OLD_COUNTS), NEW_COUNTS, 1)
    if any(updated.count(expression) for expression in OLD_COUNTS):
        raise ValueError("old unguarded step-count expressions remain")
    if updated.count("call checked_substep_count(") != 2:
        raise ValueError("expected guarded warm-rain and ice step-count calls")
    return updated


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--patch-out", required=True, type=Path)
    parser.add_argument("--harness-out", required=True, type=Path)
    args = parser.parse_args()
    if args.source.is_symlink() or not args.source.is_file():
        raise SystemExit("frozen source must be a regular non-symlink file")
    named_paths = (args.source, args.output, args.patch_out, args.harness_out)
    resolved = [path.resolve(strict=False) for path in named_paths]
    if len(set(resolved)) != len(resolved):
        raise SystemExit("source, candidate, patch, and harness paths must be distinct")
    source_bytes = args.source.read_bytes()
    actual = sha256(source_bytes)
    if actual != SOURCE_SHA256:
        raise SystemExit(f"frozen source SHA mismatch: {actual}")
    original = source_bytes.decode("latin-1")
    candidate = transform(original)
    output_bytes = candidate.encode("latin-1")
    diff = difflib.unified_diff(
        original.splitlines(keepends=True), candidate.splitlines(keepends=True),
        fromfile="frozen_base.F", tofile="checked_step_count.F",
    )
    patch_bytes = "".join(diff).encode("latin-1")
    helper = candidate.split("    ! PR71_STEP_COUNT_CONTRACT_BEGIN\n", 1)[1].split(
        "    ! PR71_STEP_COUNT_CONTRACT_END\n", 1
    )[0]
    program = """program pr71_step_count_contract_test
  use, intrinsic :: ieee_arithmetic, only : ieee_is_finite, ieee_value, ieee_quiet_nan, ieee_positive_inf
  implicit none
  integer :: count
  logical :: valid
  double precision :: rate, nan_value, inf_value
  real :: timestep

  if (bit_size(count) /= 32 .or. huge(count) /= 2147483647) then
    print *, 'unexpected default integer model'
    error stop 3
  endif

  call expect(2147483645.5d0, 1.0, .true., 2147483646, 'below int bound')
  call expect(2147483646.5d0, 1.0, .true., 2147483647, 'highest integer')
  call expect(2147483647.0d0, 1.0, .false., 0, 'at upper nint overflow threshold')
  call expect(2147483647.25d0, 1.0, .false., 0, 'above upper nint overflow threshold')
  call expect(2147483648.0d0, 1.0, .false., 0, 'above int bound')
  call expect(0.0d0, 1.0, .true., 1, 'zero rate retains minimum one')
  call expect(2.0d0, 0.25, .true., 1, 'ordinary valid rate')
  call expect(-1.0d0, 1.0, .true., 1, 'ordinary negative rate retains minimum one')
  call expect(-2147483648.75d0, 1.0, .true., 1, 'above lower nint overflow threshold')
  call expect(-2147483649.0d0, 1.0, .false., 0, 'at lower nint overflow threshold')
  call expect(-2147483649.25d0, 1.0, .false., 0, 'below lower nint overflow threshold')

  nan_value = ieee_value(0.0d0, ieee_quiet_nan)
  inf_value = ieee_value(0.0d0, ieee_positive_inf)
  call expect(nan_value, 1.0, .false., 0, 'nan rate')
  call expect(inf_value, 1.0, .false., 0, 'infinite rate')
  call expect(1.0d0, 0.0, .false., 0, 'zero timestep')
  call expect(1.0d0, -1.0, .false., 0, 'negative timestep')
  call expect(1.0d0, ieee_value(0.0, ieee_quiet_nan), .false., 0, 'nan timestep')
  call expect(huge(1.0d0), 2.0, .false., 0, 'binary64 product overflow')
  print *, 'PR71_STEP_COUNT_CONTRACT_PASS'

contains
  subroutine expect(input_rate, input_dt, expected_valid, expected_count, label)
    double precision, intent(in) :: input_rate
    real, intent(in) :: input_dt
    logical, intent(in) :: expected_valid
    integer, intent(in) :: expected_count
    character(*), intent(in) :: label
    call checked_substep_count(input_rate, input_dt, count, valid)
    if (valid .neqv. expected_valid) then
      print *, 'validity mismatch: ', label
      error stop 1
    endif
    if (count /= expected_count) then
      print *, 'count mismatch: ', label, count, expected_count
      error stop 2
    endif
  end subroutine expect

""" + helper + "\nend program pr71_step_count_contract_test\n"
    artifacts = (
        (args.output, output_bytes),
        (args.patch_out, patch_bytes),
        (args.harness_out, program.encode("ascii")),
    )
    for path, payload in artifacts:
        if path.is_symlink():
            raise SystemExit(f"refusing symlink artifact path: {path}")
        if path.exists() and (not path.is_file() or path.read_bytes() != payload):
            raise SystemExit(f"refusing to overwrite different artifact: {path}")
    for path, _ in artifacts:
        path.parent.mkdir(parents=True, exist_ok=True)
    for path, payload in artifacts:
        if not path.exists():
            with path.open("xb") as stream:
                stream.write(payload)
    print(f"BASE_SHA256 {actual}")
    print(f"SOURCE_SHA256 {sha256(output_bytes)}")
    print(f"PATCH_SHA256 {sha256(patch_bytes)}")
    print(f"HARNESS_SHA256 {sha256(args.harness_out.read_bytes())}")


if __name__ == "__main__":
    main()
