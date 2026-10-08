#!/usr/bin/env python3
"""Validate paired hydrometeor state before PSD work and rebuild intercepts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

EXPECTED_INPUT_SHA256 = "f396c9270791addcd4aed9fdc59f5a6d3f9287f1af8f759d3a0cbc36b1e78f85"

STATE_CONSTANTS = """   integer, parameter, private :: SPECIES_ABSENT = 0
   integer, parameter, private :: SPECIES_MASS_ONLY = 1
   integer, parameter, private :: SPECIES_NUMBER_ONLY = 2
   integer, parameter, private :: SPECIES_ACTIVE = 3
   integer, parameter, private :: SPECIES_INVALID = 4
"""

STATE_PROCEDURES = """    pure integer function classify_species_state(mass, number) result(state)
      real, intent(in) :: mass, number
      if (.not.ieee_is_finite(mass) .or. .not.ieee_is_finite(number)) then
        state = SPECIES_INVALID
      elseif (mass < 0.0 .or. number < 0.0) then
        state = SPECIES_INVALID
      elseif (mass == 0.0 .and. number == 0.0) then
        state = SPECIES_ABSENT
      elseif (mass > 0.0 .and. number == 0.0) then
        state = SPECIES_MASS_ONLY
      elseif (mass == 0.0 .and. number > 0.0) then
        state = SPECIES_NUMBER_ONLY
      else
        state = SPECIES_ACTIVE
      endif
    end function classify_species_state

    subroutine validate_kdm6_species_states(qci, qrs, nrs, nci, brs)
      real, intent(in) :: qci(:,:,:), qrs(:,:,:), nrs(:,:,:), nci(:,:,:), brs(:,:)
      integer :: i, k, state
      do k=1,size(qrs,2)
        do i=1,size(qrs,1)
          state=classify_species_state(qrs(i,k,1),nrs(i,k,1))
          call require_paired_state(state)
          state=classify_species_state(qci(i,k,1),nci(i,k,1))
          call require_paired_state(state)
          state=classify_species_state(qci(i,k,2),nci(i,k,2))
          call require_paired_state(state)
          state=classify_species_state(qrs(i,k,3),brs(i,k))
          call require_paired_state(state)
        enddo
      enddo
    end subroutine validate_kdm6_species_states

    subroutine validate_kdm6_slope_states(qci_current, qrs_current, nrs_current, &
                                            nci_current, brs, qrs, nrs, qci, nci)
      real, intent(in) :: qci_current(:,:,:), qrs_current(:,:,:), nrs_current(:,:,:)
      real, intent(in) :: nci_current(:,:,:), brs(:,:), qrs(:,:,:), nrs(:,:), qci(:,:), nci(:,:)
      integer :: i, k
      do k=1,size(qrs,2)
        do i=1,size(qrs,1)
          call require_paired_state(classify_species_state(qrs_current(i,k,1),nrs_current(i,k,1)))
          call require_paired_state(classify_species_state(qci_current(i,k,1),nci_current(i,k,1)))
          call require_paired_state(classify_species_state(qci_current(i,k,2),nci_current(i,k,2)))
          call require_paired_state(classify_species_state(qrs_current(i,k,3),brs(i,k)))
          call require_paired_state(classify_species_state(qrs(i,k,1),nrs(i,k)))
          call require_paired_state(classify_species_state(qci(i,k),nci(i,k)))
          call require_paired_state(classify_species_state(qrs(i,k,3),brs(i,k)))
        enddo
      enddo
    end subroutine validate_kdm6_slope_states

    subroutine validate_local_species_states(qr, nr, qc, nc, qi, ni, qg, bg)
      real, intent(in) :: qr, nr, qc, nc, qi, ni, qg, bg
      call require_paired_state(classify_species_state(qr,nr))
      call require_paired_state(classify_species_state(qc,nc))
      call require_paired_state(classify_species_state(qi,ni))
      call require_paired_state(classify_species_state(qg,bg))
    end subroutine validate_local_species_states

    subroutine require_paired_state(state)
      integer, intent(in) :: state
      select case(state)
      case(SPECIES_ABSENT,SPECIES_ACTIVE)
        return
      case(SPECIES_MASS_ONLY)
        error stop 'KDM6 unsupported positive mass without number/volume state'
      case(SPECIES_NUMBER_ONLY)
        error stop 'KDM6 orphan number/volume state without positive mass'
      case default
        error stop 'KDM6 invalid nonfinite or negative species state'
      end select
    end subroutine require_paired_state
"""

OLD_CONSTANT_ANCHOR = "   integer, parameter, private :: PROGB_UNSUPPORTED = 3\n"
MODULE_CONTAINS_ANCHOR = "    contains\n\n    ! PR71_STEP_COUNT_CONTRACT_BEGIN"
FIRST_STATE_LOOP = """   do k = kts, kte
     do i = its, ite
       qci(i,k,1) = max(qci(i,k,1),0.0)"""
STATE_LOOP_REPLACEMENT = """   call validate_kdm6_species_states(qci,qrs,nrs,nci,brs)
   do k = kts, kte
     do i = its, ite
       qci(i,k,1) = max(qci(i,k,1),0.0)"""
SLOPE_CALL = "   call slope_kdm6(qrs_tmp,qci_tmp,nrs_tmp,nci_tmp,den_tmp,denfac,t,rslope,  &"
OLD_INTERCEPTS = """          n0r(i,k) = nrs(i,k,1)/(rslope(i,k,1)*rslopemu(i,k,1)*g1pmr)
          n0c(i,k) = (muc+1)*nci(i,k,1)/(rslopec(i,k)*rslopecmu(i,k))
          n0i(i,k) = nci(i,k,2)/(rslope(i,k,4)*rslopemu(i,k,4)*g1pmi)"""
LATE_ICE_PROPERTY = """          if(qci(i,k,2).ge. qmin .and. nci(i,k,2) .ge. ncmin ) then
            lamdi_tmp(i,k) = exp(log((((pidni)*nci(i,k,2))                       &"""
LOCAL_STATE_CALL = "          call validate_local_species_states(qrs(i,k,1),nrs(i,k,1), &\n               qci(i,k,1),nci(i,k,1),qci(i,k,2),nci(i,k,2), &\n               qrs(i,k,3),brs(i,k))\n"
NEW_INTERCEPTS = """          n0r(i,k) = 0.0
          n0c(i,k) = 0.0
          n0i(i,k) = 0.0
          if (classify_species_state(qrs(i,k,1),nrs(i,k,1)) == SPECIES_ACTIVE) &
            n0r(i,k) = nrs(i,k,1)/(rslope(i,k,1)*rslopemu(i,k,1)*g1pmr)
          if (classify_species_state(qci(i,k,1),nci(i,k,1)) == SPECIES_ACTIVE) &
            n0c(i,k) = (muc+1)*nci(i,k,1)/(rslopec(i,k)*rslopecmu(i,k))
          if (classify_species_state(qci(i,k,2),nci(i,k,2)) == SPECIES_ACTIVE) &
            n0i(i,k) = nci(i,k,2)/(rslope(i,k,4)*rslopemu(i,k,4)*g1pmi)"""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def transform(source: Path, output: Path, receipt: Path | None = None) -> dict[str, object]:
    if not source.is_file() or source.is_symlink():
        raise SystemExit(f"source must be a regular non-symlink file: {source}")
    if output.exists() or output.is_symlink():
        raise SystemExit(f"refusing to overwrite output: {output}")
    text = source.read_text(encoding="utf-8")
    input_sha256 = sha256(text.encode("utf-8"))
    if input_sha256 != EXPECTED_INPUT_SHA256:
        raise SystemExit(f"unexpected native-fixed input SHA-256: {input_sha256}")
    if text.count(OLD_CONSTANT_ANCHOR) != 1:
        raise SystemExit("expected one module species-constant insertion anchor")
    if text.count(MODULE_CONTAINS_ANCHOR) != 1:
        raise SystemExit("expected one module procedure insertion anchor")
    if text.count(FIRST_STATE_LOOP) != 1:
        raise SystemExit("expected one initial KDM62D state loop")
    if text.count(SLOPE_CALL) != 7:
        raise SystemExit("expected seven KDM62D slope call sites")
    if text.count(OLD_INTERCEPTS) != 2:
        raise SystemExit("expected two current-state property rebuild sites")
    if text.count(LATE_ICE_PROPERTY) != 1:
        raise SystemExit("expected one late ice-property reconstruction")

    text = text.replace(OLD_CONSTANT_ANCHOR, OLD_CONSTANT_ANCHOR + STATE_CONSTANTS, 1)
    text = text.replace(MODULE_CONTAINS_ANCHOR,
                        "    contains\n\n" + STATE_PROCEDURES +
                        "    ! PR71_STEP_COUNT_CONTRACT_BEGIN", 1)
    text = text.replace(FIRST_STATE_LOOP, STATE_LOOP_REPLACEMENT, 1)
    text = text.replace(SLOPE_CALL,
                        "   call validate_kdm6_slope_states(qci,qrs,nrs,nci,brs, &\n" +
                        "        qrs_tmp,nrs_tmp,qci_tmp,nci_tmp)\n" + SLOPE_CALL)
    intercept_positions = [pos for pos in range(len(text)) if text.startswith(OLD_INTERCEPTS, pos)]
    if len(intercept_positions) != 2:
        raise SystemExit("expected two intercept rebuild sites")
    for pos in reversed(intercept_positions):
        text = text[:pos] + LOCAL_STATE_CALL + text[pos:]
    text = text.replace(OLD_INTERCEPTS, NEW_INTERCEPTS, 2)
    text = text.replace(LATE_ICE_PROPERTY, LOCAL_STATE_CALL + LATE_ICE_PROPERTY, 1)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    result = {
        "schema": "pr72_species_property_state_v1",
        "input": str(source), "input_sha256": sha256(source.read_bytes()),
        "output": str(output), "output_sha256": sha256(output.read_bytes()),
        "classification": {
            "exact_zero_pair": "absent",
            "strictly_positive_pair": "active",
            "positive_mass_zero_number": "unsupported; rejected before PSD work",
            "zero_mass_positive_number": "orphan; rejected before PSD work",
            "negative_or_nonfinite": "invalid; rejected before PSD work",
        },
        "validation_points": {"initial_state": 1, "before_slope_calculation": 7,
                              "before_property_rebuild": 2,
                              "before_late_ice_reconstruction": 1},
        "property_rebuild": "absent states receive zero intercepts; active states retain source equations",
        "policy_limits": ["does not clip or floor mass or number", "does not assign graupel density"],
    }
    if receipt is not None:
        if receipt.exists() or receipt.is_symlink():
            raise SystemExit(f"refusing to overwrite receipt: {receipt}")
        receipt.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    result = transform(args.source, args.output, args.receipt)
    print(f"PR72_SPECIES_INPUT_SHA256 {result['input_sha256']}")
    print(f"PR72_SPECIES_OUTPUT_SHA256 {result['output_sha256']}")


if __name__ == "__main__":
    main()
