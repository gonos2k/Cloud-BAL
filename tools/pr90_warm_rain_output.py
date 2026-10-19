"""Prototype a strict PR90 rain-output gate in the pinned C5 warm endpoint."""
from __future__ import annotations

import hashlib
import re


C5_KDM6_SOURCE_SHA256 = "14c6145df549541fae2aab84e98ee480ba6ac8a7c769dd926a6d44f22451c35d"


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise ValueError(f"expected one {label} anchor, found {count}")
    return source.replace(old, new, 1)


def add_unreconstructed_rain_output_check(source: str) -> str:
    """Add a nonmutating output/store preview only for rain the source skips."""
    source_hash = hashlib.sha256(source.encode()).hexdigest()
    if source_hash != C5_KDM6_SOURCE_SHA256:
        raise ValueError(f"KDM6 source differs from pinned C5: {source_hash}")

    helper = r"""
    logical function kdm6_unreconstructed_rain_output_valid(q,n,density,pidnr,power, &
          lambda_min,lambda_max,qcrmin,nrmin)
      use, intrinsic :: ieee_arithmetic, only : ieee_is_finite
      use iso_fortran_env, only : real32,real64
      implicit none
      real(real32), intent(in) :: q,n,density,pidnr,power,lambda_min,lambda_max
      real(real32), intent(in) :: qcrmin,nrmin
      real(real32) :: q_public,n_specific,q_restored,nvol_restored
      real(real64) :: delta_q,delta_n,delta_q_back,delta_nvol_back
      real(real64) :: rain_min,rain_max
      real(real64) :: diagnostic(12)
      integer :: adjustment,adjustment_back,stage,core_stage,consumer_reason
      character(len=32) :: reason
      logical :: store_valid,restore_valid,consumer_valid
      interface
        subroutine pr90_rain_public_store_diagnostic(q_internal,nvol_internal,dry_density, &
             pidnr,power,lambda_min,lambda_max,q_public,n_specific,valid,delta_q,delta_n, &
             adjustment,failure_reason,diagnostic,stage,core_stage)
          use iso_fortran_env, only : real32,real64
          real(real32), intent(in) :: q_internal,nvol_internal,dry_density,pidnr,power
          real(real32), intent(in) :: lambda_min,lambda_max
          real(real32), intent(out) :: q_public,n_specific
          logical, intent(out) :: valid
          real(real64), intent(out) :: delta_q,delta_n,diagnostic(12)
          integer, intent(out) :: adjustment,stage,core_stage
          character(len=*), intent(out) :: failure_reason
        end subroutine pr90_rain_public_store_diagnostic
        subroutine pr87_number_volume_store(q_specific,n_specific,dry_density,pidnr,power, &
             lambda_min,lambda_max,q_stored,n_volume,valid,delta_q,delta_nvolume,adjustment)
          use iso_fortran_env, only : real32,real64
          real(real32), intent(in) :: q_specific,n_specific,dry_density,pidnr,power
          real(real32), intent(in) :: lambda_min,lambda_max
          real(real32), intent(out) :: q_stored,n_volume
          logical, intent(out) :: valid
          real(real64), intent(out) :: delta_q,delta_nvolume
          integer, intent(out) :: adjustment
        end subroutine pr87_number_volume_store
      end interface

      kdm6_unreconstructed_rain_output_valid=.false.
      if (.not.all(ieee_is_finite([q,n,density,pidnr,power,lambda_min,lambda_max, &
                                   qcrmin,nrmin]))) return
      if (q.lt.0.0_real32 .or. n.lt.0.0_real32 .or. density.le.0.0_real32 .or. &
          pidnr.le.0.0_real32 .or. power.le.0.0_real32 .or. power.gt.8.0_real32 .or. &
          lambda_min.le.0.0_real32 .or. lambda_max.lt.lambda_min .or. &
          qcrmin.lt.0.0_real32 .or. nrmin.lt.0.0_real32) return

      ! The caller's original state validator owns cutoff, zero-pair, and pending rules.
      ! Stage-3 can reconstruct only when both source cutoffs are active.
      kdm6_unreconstructed_rain_output_valid=.true.
      if (q.le.qcrmin .or. n.ge.nrmin) return
      if (q.le.0.0_real32 .or. n.le.0.0_real32) then
        kdm6_unreconstructed_rain_output_valid=.false.
        return
      endif

      call pr90_rain_public_store_diagnostic(q,n,density,pidnr,power,lambda_min, &
           lambda_max,q_public,n_specific,store_valid,delta_q,delta_n,adjustment, &
           reason,diagnostic,stage,core_stage)
      if (.not.store_valid) then
        kdm6_unreconstructed_rain_output_valid=.false.
        return
      endif
      call pr87_number_volume_store(q_public,n_specific,density,pidnr,power, &
           lambda_min,lambda_max,q_restored,nvol_restored,restore_valid,delta_q_back, &
           delta_nvol_back,adjustment_back)
      if (.not.restore_valid) then
        kdm6_unreconstructed_rain_output_valid=.false.
        return
      endif
      rain_min=real(density,real64)*real(lambda_min,real64)**real(power,real64)/real(pidnr,real64)
      rain_max=real(density,real64)*real(lambda_max,real64)**real(power,real64)/real(pidnr,real64)
      if (.not.all(ieee_is_finite([rain_min,rain_max]))) then
        kdm6_unreconstructed_rain_output_valid=.false.
        return
      endif
      call kdm6_rain_ng_pair_valid(q_restored,nvol_restored,rain_min,rain_max, &
           .false.,.false.,consumer_valid,consumer_reason)
      kdm6_unreconstructed_rain_output_valid=consumer_valid
    end function kdm6_unreconstructed_rain_output_valid
"""
    source = _replace_once(
        source,
        "    end subroutine kdm6_rain_ng_pair_valid\n",
        "    end subroutine kdm6_rain_ng_pair_valid\n" + helper,
        "rain output preview helper insertion",
    )

    # Candidate trial: run after source validation and pending CCN transfer, before accept.
    trial_anchor = (
        "              if (rain_warm_state_valid .and. rain_warm_qv_after.ge.0.0 .and. &\n"
        "                  rain_ccn3_after.ge.0.0) exit\n"
    )
    trial_check = (
        "              if (rain_warm_state_valid) &\n"
        "                rain_warm_state_valid=kdm6_unreconstructed_rain_output_valid( &\n"
        "                     rain_warm_q_after(3),rain_warm_n_after(3),dry_carrier_density(i,k), &\n"
        "                     pidnr,dmr,lamdarmin,lamdarmax,qcrmin,nrmin)\n"
    )
    source = _replace_once(source, trial_anchor, trial_check + trial_anchor,
                           "warm trial output gate")

    # The no-feasible-step base check and both post-loop/fallback checks validate
    # the unchanged base before a no-op commit can be selected.
    base_call = (
        "              call kdm6_rain_process_state_valid(rain_q_before,rain_n_before, &\n"
        "                   rain_bg_before,rain_t_before,dry_carrier_density(i,k),pidnr, &\n"
        "                   qmin,ncmin,qcrmin,dmr,lamdarmin,lamdarmax,100.0,900.0, &\n"
        "                   pidnc,dmc,lamdacmin,lamdacmax,pidni,dmi,lamdaimin, &\n"
        "                   lamdaimax,rain_warm_state_valid,rain_full_evap_pending(i,k),.true.)\n"
    )
    base_check = (
        "              if (rain_warm_state_valid) &\n"
        "                rain_warm_state_valid=kdm6_unreconstructed_rain_output_valid( &\n"
        "                     rain_q_before(3),rain_n_before(3),dry_carrier_density(i,k), &\n"
        "                     pidnr,dmr,lamdarmin,lamdarmax,qcrmin,nrmin)\n"
    )
    if source.count(base_call) != 2:
        raise ValueError(f"expected two warm base/fallback validators, found {source.count(base_call)}")
    source = source.replace(base_call, base_call + base_check)

    # Keep the existing warm-row schema and emit any packet that needed retry.
    source = _replace_once(
        source,
        "            if (rain_warm_search_status.eq.1) then\n",
        "            if (rain_warm_search_status.eq.1 .or. rain_warm_retry.gt.0) then\n",
        "backtracked warm-row ledger gate",
    )

    return source


def extract_warm_trial_commit(source: str) -> str:
    """Return the source's real warm retry and atomic commit block."""
    begin = "            rain_warm_abort=.false.\n"
    end = "              bgeml(i,k)=0.0\n            endif\n"
    if source.count(begin) != 1 or source.count(end) != 1:
        raise ValueError("expected one complete warm retry/commit block")
    start = source.index(begin)
    end_start = source.index(end, start) + len(end)
    block = source[start:end_start]
    if "kdm6_unreconstructed_rain_output_valid" not in block:
        raise ValueError("warm block lacks the strict output preview")
    for assignment in (
        "qrs(i,k,1)=rain_warm_q_after(3)",
        "nrs(i,k,1)=rain_warm_n_after(3)",
        "brs(i,k)=rain_warm_bg_after",
        "t(i,k)=rain_warm_t_after",
        "q(i,k)=rain_warm_qv_after",
        "nci(i,k,3)=rain_ccn3_after",
    ):
        if assignment not in re.sub(r"[\s&]+", "", block).lower():
            raise ValueError(f"warm commit block is incomplete: {assignment}")
    return block


def extract_warm_process_setup(source: str) -> str:
    """Return the source's primitive-rate-to-Q/N/B/T/QV process equations."""
    begin = "            rain_warm_rate_base=["
    end = "            call kdm6_rain_process_fraction("
    if source.count(begin) != 1:
        raise ValueError("expected one warm rate/process setup")
    start = source.index(begin)
    try:
        end_start = source.index(end, start)
    except ValueError as exc:
        raise ValueError("warm rate/process setup is unterminated") from exc
    block = source[start:end_start]
    if "rain_warm_qv_process=work2(i,k)*dtcld" not in re.sub(r"[\s&]+", "", block).lower():
        raise ValueError("warm process setup is incomplete")
    return block


def main() -> int:
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    transformed = add_unreconstructed_rain_output_check(args.source.read_text())
    args.output.write_text(transformed)
    print(hashlib.sha256(transformed.encode()).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
