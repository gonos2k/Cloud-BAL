#!/usr/bin/env python3
"""Make active-ice completion satisfy the strict nongraupel consumer bound."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

C4_SOURCE_SHA256 = "b358064642d81c86ee1f914c52620ade2c7589ccf302dcffd26d25809fd5adaa"

STRICT_PREDICATE = """pure subroutine kdm6_ice_ng_pair_contract(q,n,density,pidni,dmi,lambda_min,lambda_max,valid,n_min,n_max)
      use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
      implicit none
      real, intent(in) :: q,n,density,pidni,dmi,lambda_min,lambda_max
      logical, intent(out) :: valid
      real(kind=8), intent(out) :: n_min,n_max
      valid=.false.
      n_min=0.0d0
      n_max=0.0d0
      if (.not.all(ieee_is_finite([q,n,density,pidni,dmi,lambda_min,lambda_max]))) return
      if (density.le.0.0 .or. pidni.le.0.0 .or. dmi.le.0.0 .or. dmi.gt.8.0 .or. &
          lambda_min.le.0.0 .or. lambda_max.lt.lambda_min) return
      if (q.eq.0.0 .and. n.eq.0.0) then
        valid=.true.
        return
      endif
      if (q.le.0.0 .or. n.le.0.0) return
      n_min=(real(density,8)*real(lambda_min,8)**real(dmi,8)/real(pidni,8))*real(q,8)
      n_max=(real(density,8)*real(lambda_max,8)**real(dmi,8)/real(pidni,8))*real(q,8)
      valid=ieee_is_finite(n_min) .and. ieee_is_finite(n_max) .and. &
          real(n,8).ge.n_min .and. real(n,8).le.n_max
    end subroutine kdm6_ice_ng_pair_contract"""


def _replace_once(source: str, old: str, new: str, label: str, count: int = 1) -> str:
    found = source.count(old)
    if found != count:
        raise ValueError(f"{label}: expected {count} source occurrences, found {found}")
    return source.replace(old, new, count)


def transform(source: str) -> str:
    actual = hashlib.sha256(source.encode()).hexdigest()
    if actual != C4_SOURCE_SHA256:
        raise ValueError(f"C4 KDM6 source identity mismatch: {actual}")

    source = _replace_once(
        source,
        """      elseif (q(2).gt.ice_transient_limit) then
        if (real(n(2),8).lt.ice_min*q(2) .or. real(n(2),8).gt.ice_max*q(2)) then
          if (present(failure_reason)) failure_reason=7
          return
        endif
      endif""",
        """      elseif (q(2).gt.ice_transient_limit) then
        call kdm6_ice_ng_pair_contract(q(2),n(2),density,pidni,dmi, &
             lambda_i_min,lambda_i_max,rain_pair_valid_result,ice_min,ice_max)
        if (.not.rain_pair_valid_result) then
          if (present(failure_reason)) failure_reason=7
          return
        endif
      endif""",
        "shared strict consumer predicate",
    )
    consumer_end = "    end subroutine kdm6_rain_process_state_valid"
    source = _replace_once(source, consumer_end, consumer_end + "\n" + STRICT_PREDICATE,
                           "insert shared strict predicate")
    source = _replace_once(
        source,
        "   logical :: pr93_ice_pair_valid,pr93_ice_direct_repair\n",
        "   logical :: pr93_ice_pair_valid,pr93_ice_ng_valid,pr93_ice_direct_repair\n",
        "producer strict validity state",
    )
    source = _replace_once(
        source,
        "   real(8) :: pr93_ice_mean,pr93_ice_min,pr93_ice_max\n",
        "   real(8) :: pr93_ice_min,pr93_ice_max\n"
        "   real(8) :: pr93_ice_ng_min,pr93_ice_ng_max\n",
        "strict producer number bounds",
    )

    old_check = """            pr93_ice_mean=0.0d0
            if (.not.pr93_ice_pair_valid) then
              pr93_ice_mean=DBLE(dry_carrier_density(i,k))* &
                   DBLE(qci(i,k,2))/DBLE(nci(i,k,2))
            endif"""
    new_check = """            call kdm6_ice_ng_pair_contract(qci(i,k,2),nci(i,k,2), &
                 dry_carrier_density(i,k),pidni,dmi,lamdaimin,lamdaimax, &
                 pr93_ice_ng_valid,pr93_ice_ng_min,pr93_ice_ng_max)
            if (qci(i,k,2).gt.0.0 .and. &
                qci(i,k,2).le.PR85_ICE_NATIVE_INACTIVE_MAX .and. nci(i,k,2).gt.0.0) &
              pr93_ice_ng_valid=.true."""
    source = _replace_once(source, old_check, new_check, "strict pre-repair pair check", count=3)
    source = _replace_once(
        source,
        "(.not.pr93_ice_pair_valid .and. pr93_ice_mean.gt.pr93_ice_max)",
        "(qci(i,k,2).gt.PR85_ICE_NATIVE_INACTIVE_MAX .and. &\n"
        "                  .not.pr93_ice_ng_valid .and. DBLE(nci(i,k,2)).lt.pr93_ice_ng_min)",
        "strict lower-bound repair side", count=3,
    )
    source = _replace_once(
        source,
        "(.not.pr93_ice_pair_valid .and. &\n                  pr93_ice_mean.lt.pr93_ice_min)",
        "(qci(i,k,2).gt.PR85_ICE_NATIVE_INACTIVE_MAX .and. &\n"
        "                  .not.pr93_ice_ng_valid .and. DBLE(nci(i,k,2)).gt.pr93_ice_ng_max)",
        "strict upper-bound repair side", count=3,
    )
    source = _replace_once(
        source,
        "lamdi_tmp(i,k).lt.lamdaimax .and. .not.pr93_ice_pair_valid",
        "lamdi_tmp(i,k).lt.lamdaimax .and. &\n"
        "                 (.not.pr93_ice_pair_valid .or. .not.pr93_ice_ng_valid)",
        "strict repair ledger trigger", count=3,
    )

    old_post = """            pr93_ice_pair_valid=pr93_kdm6_pair_in_cone(qci(i,k,2),nci(i,k,2), &
                 dry_carrier_density(i,k),pr93_ice_min,pr93_ice_max)
            if (qci(i,k,2).gt.0.0 .and. qci(i,k,2).le.PR85_ICE_NATIVE_INACTIVE_MAX &
                 .and. nci(i,k,2).gt.0.0) pr93_ice_pair_valid=.true.
            if (.not.pr93_ice_pair_valid) &
              error stop 'PR93 ice PSD output failed consumer contract'"""
    new_post = """            pr93_ice_pair_valid=pr93_kdm6_pair_in_cone(qci(i,k,2),nci(i,k,2), &
                 dry_carrier_density(i,k),pr93_ice_min,pr93_ice_max)
            if (qci(i,k,2).gt.0.0 .and. qci(i,k,2).le.PR85_ICE_NATIVE_INACTIVE_MAX &
                 .and. nci(i,k,2).gt.0.0) pr93_ice_pair_valid=.true.
            call kdm6_ice_ng_pair_contract(qci(i,k,2),nci(i,k,2), &
                 dry_carrier_density(i,k),pidni,dmi,lamdaimin,lamdaimax, &
                 pr93_ice_ng_valid,pr93_ice_ng_min,pr93_ice_ng_max)
            if (.not.pr93_ice_pair_valid .or. &
                (qci(i,k,2).gt.PR85_ICE_NATIVE_INACTIVE_MAX .and. .not.pr93_ice_ng_valid)) &
              error stop 'PR93 ice PSD output failed consumer contract'"""
    source = _replace_once(source, old_post, new_post, "strict post-repair producer contract", count=3)
    return source


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.read_text()
    generated = transform(source)
    args.output.write_text(generated)
    args.manifest.write_text(json.dumps({
        "schema": "pr96_ice_ng_contract_v1",
        "source_path": str(args.source),
        "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "output_path": str(args.output),
        "output_sha256": hashlib.sha256(generated.encode()).hexdigest(),
    }, indent=2) + "\n")
    print(hashlib.sha256(generated.encode()).hexdigest())


if __name__ == "__main__":
    main()
