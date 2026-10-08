#!/usr/bin/env python3
"""Add a scoped first-species-violation diagnostic to frozen PR72 KDM6 source."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

EXPECTED_INPUT_SHA256 = "1fbd9d5cbc32dc5772682078b4efc63b3dafb28a79499e318faf9520fc55e819"

OLD_VALIDATOR = """    subroutine validate_kdm6_species_states(qci, qrs, nrs, nci, brs)
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
"""

NEW_VALIDATOR = """    subroutine validate_kdm6_species_states(qci, qrs, nrs, nci, brs, &
                                                its, ite, kts, kte, lat)
      real, intent(in) :: qci(:,:,:), qrs(:,:,:), nrs(:,:,:), nci(:,:,:), brs(:,:)
      integer, intent(in) :: its, ite, kts, kte, lat
      integer :: i, k, ii, kk
      do k=kts,kte
        kk=k-kts+1
        do i=its,ite
          ii=i-its+1
          call require_initial_paired_state( &
            classify_species_state(qrs(ii,kk,1),nrs(ii,kk,1)), 'rain', &
            qrs(ii,kk,1),nrs(ii,kk,1),0.0,.true.,.false., &
            i,lat,k,its,ite,kts,kte,'KDM62D_INITIAL_PREFLIGHT')
          call require_initial_paired_state( &
            classify_species_state(qci(ii,kk,1),nci(ii,kk,1)), 'cloud', &
            qci(ii,kk,1),nci(ii,kk,1),0.0,.true.,.false., &
            i,lat,k,its,ite,kts,kte,'KDM62D_INITIAL_PREFLIGHT')
          call require_initial_paired_state( &
            classify_species_state(qci(ii,kk,2),nci(ii,kk,2)), 'ice', &
            qci(ii,kk,2),nci(ii,kk,2),0.0,.true.,.false., &
            i,lat,k,its,ite,kts,kte,'KDM62D_INITIAL_PREFLIGHT')
          call require_initial_paired_state( &
            classify_species_state(qrs(ii,kk,3),brs(ii,kk)), 'graupel', &
            qrs(ii,kk,3),0.0,brs(ii,kk),.false.,.true., &
            i,lat,k,its,ite,kts,kte,'KDM62D_INITIAL_PREFLIGHT')
        enddo
      enddo
    end subroutine validate_kdm6_species_states

    subroutine require_initial_paired_state(state,species,q,n,b,has_n,has_b, &
                                             i,j,k,its,ite,kts,kte,stage)
      integer, intent(in) :: state,i,j,k,its,ite,kts,kte
      real, intent(in) :: q,n,b
      logical, intent(in) :: has_n,has_b
      character(len=*), intent(in) :: species,stage
      character(len=32) :: state_name,q_value,n_value,b_value
      character(len=16) :: i_value,j_value,k_value,its_value,ite_value,kts_value,kte_value
      if (state == SPECIES_ABSENT .or. state == SPECIES_ACTIVE) return
      select case(state)
      case(SPECIES_MASS_ONLY)
        state_name='mass_only'
      case(SPECIES_NUMBER_ONLY)
        state_name='number_only'
      case default
        state_name='invalid_negative_or_nonfinite'
      end select
      if (has_n) then
        write(n_value,'(ES24.16E3)') n
      else
        n_value='null'
      endif
      write(q_value,'(ES24.16E3)') q
      if (has_b) then
        write(b_value,'(ES24.16E3)') b
      else
        b_value='null'
      endif
      write(i_value,'(I0)') i
      write(j_value,'(I0)') j
      write(k_value,'(I0)') k
      write(its_value,'(I0)') its
      write(ite_value,'(I0)') ite
      write(kts_value,'(I0)') kts
      write(kte_value,'(I0)') kte
      write(*,'(*(A))') 'KDM6_FIRST_VIOLATION|stage=',trim(stage), &
        '|species=',trim(species),'|state=',trim(state_name), &
        '|q=',trim(adjustl(q_value)),'|q_unit=kg kg-1|n=', &
        trim(adjustl(n_value)),'|n_unit=m-3|b=',trim(adjustl(b_value)), &
        '|b_unit=m3 kg-1|i=',trim(i_value),'|call_lat_index=',trim(j_value), &
        '|k=',trim(k_value),'|scope_i=',trim(its_value),':',trim(ite_value), &
        '|scope_k=',trim(kts_value),':',trim(kte_value), &
        '|index_origin=KDM62D_dummy_bounds|j_global_mapping=unclaimed'
      error stop 'KDM6 species state rejected at initial preflight'
    end subroutine require_initial_paired_state
"""

OLD_CALL = "   call validate_kdm6_species_states(qci,qrs,nrs,nci,brs)\n"
NEW_CALL = "   call validate_kdm6_species_states(qci,qrs,nrs,nci,brs, &\n" \
            "        its,ite,kts,kte,lat)\n"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def transform(source: Path, output: Path, receipt: Path | None = None) -> dict[str, object]:
    if not source.is_file() or source.is_symlink():
        raise SystemExit(f"source must be a regular non-symlink file: {source}")
    if output.exists() or output.is_symlink():
        raise SystemExit(f"refusing to overwrite output: {output}")
    text = source.read_text(encoding="utf-8")
    actual_sha = sha256(source)
    if actual_sha != EXPECTED_INPUT_SHA256:
        raise SystemExit(f"unexpected frozen PR72 source SHA-256: {actual_sha}")
    if text.count(OLD_VALIDATOR) != 1 or text.count(OLD_CALL) != 1:
        raise SystemExit("expected one initial validator definition and call")
    text = text.replace(OLD_VALIDATOR, NEW_VALIDATOR, 1)
    text = text.replace(OLD_CALL, NEW_CALL, 1)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    result: dict[str, object] = {
        "schema": "pr73_first_violation_composition_v1",
        "input": str(source),
        "input_sha256": actual_sha,
        "output": str(output),
        "output_sha256": sha256(output),
        "diagnostic": {
            "stage": "KDM62D_INITIAL_PREFLIGHT",
            "loop_scope": "i=its:ite, k=kts:kte; lat argument recorded as call_lat_index",
            "indices": "Fortran model indices; assumed-shape storage offset from explicit lower bounds",
            "geographic_latitude": "unavailable; global-j mapping is not claimed",
            "units": {"q": "kg kg-1", "n": "m-3", "b": "m3 kg-1"},
            "first_only": True,
        },
        "policy": "diagnostic only; no species values are changed",
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
    print(f"PR73_FIRST_VIOLATION_INPUT_SHA256 {result['input_sha256']}")
    print(f"PR73_FIRST_VIOLATION_OUTPUT_SHA256 {result['output_sha256']}")


if __name__ == "__main__":
    main()
