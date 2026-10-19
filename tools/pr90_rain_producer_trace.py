#!/usr/bin/env python3
"""Hash-bound, target-cell KDM6 producer trace transform for T7 diagnosis."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

SOURCE_SHA256 = "14c6145df549541fae2aab84e98ee480ba6ac8a7c769dd926a6d44f22451c35d"
TRACE_FIELDS = ("stage", "step", "lat", "i", "k", "loop", "rho_hex", "T_hex",
                "Qc_hex", "Nc_hex", "Qi_hex", "Ni_hex", "Qr_hex", "Nr_hex",
                "Qs_hex", "Qg_hex", "Nccn_hex", "Bg_hex", "Qv_hex", "status")
TRACE_BEGIN = "! PR90_T7_TRACE_HELPER_BEGIN"
TRACE_END = "! PR90_T7_TRACE_HELPER_END"
INSERT_BEGIN = "PR90_T7_TRACE_INSERT_BEGIN"
INSERT_END = "PR90_T7_TRACE_INSERT_END"


class TraceTransformError(ValueError):
    """Raised when the pinned KDM6 source does not match expected anchors."""


def _replace_once(source: str, anchor: str, replacement: str, name: str) -> str:
    if source.count(anchor) != 1:
        raise TraceTransformError(f"KDM6 {name} anchor missing or ambiguous")
    return source.replace(anchor, replacement, 1)


def _replace_first(source: str, anchor: str, replacement: str, name: str) -> str:
    if anchor not in source:
        raise TraceTransformError(f"KDM6 {name} anchor missing")
    return source.replace(anchor, replacement, 1)


def _call(stage: str, *, entry: bool = False) -> str:
    if entry:
        when = ("pr87_model_timestep.eq.7 .and. lat.eq.222 .and. "
                "193.ge.its .and. 193.le.ite .and. 4.ge.kts .and. 4.le.kte")
        i, k, loop, rho = "193", "4", "0", "den(193,4)"
        status = "-1"
    else:
        when = "pr87_model_timestep.eq.7 .and. lat.eq.222 .and. i.eq.193 .and. k.eq.4"
        i, k, loop, rho = "i", "k", "loop", "dry_carrier_density(i,k)"
        status = f"progb_status({i},{k})"
    return f"""      ! {INSERT_BEGIN} {stage}
      if ({when}) call pr90_t7_trace('{stage}',pr87_model_timestep,lat,{i},{k},{loop}, &
           {rho},t({i},{k}),qci({i},{k},1),nci({i},{k},1),qci({i},{k},2),nci({i},{k},2), &
           qrs({i},{k},1),nrs({i},{k},1),qrs({i},{k},2),qrs({i},{k},3),nci({i},{k},3), &
           brs({i},{k}),q({i},{k}),{status})
      ! {INSERT_END} {stage}
"""


_TRACE_HELPER = f"""\n{TRACE_BEGIN}
   subroutine pr90_t7_trace(stage,step,lat,cell_i,level,call_loop,rho,temp,qc,nc,qi,ni,qr,nr,qs,qg,ccn,bg,qv,status)
     implicit none
     character(len=*), intent(in) :: stage
     integer, intent(in) :: step,lat,cell_i,level,call_loop,status
     real, intent(in) :: rho,temp,qc,nc,qi,ni,qr,nr,qs,qg,ccn,bg,qv
     integer :: unit,ios
     open(newunit=unit,file='pr90_t7_producer_trace.raw',form='formatted', &
          status='unknown',position='append',action='write',iostat=ios)
     if (ios.ne.0) error stop 'PR90 T7 trace open failed'
     write(unit,'(a,5i8,1x,13(z8.8,1x),i8)',iostat=ios) &
          'PR90_T7_PRODUCER '//stage,step,lat,cell_i,level,call_loop, &
          transfer(rho,0),transfer(temp,0),transfer(qc,0),transfer(nc,0), &
          transfer(qi,0),transfer(ni,0),transfer(qr,0),transfer(nr,0), &
          transfer(qs,0),transfer(qg,0),transfer(ccn,0),transfer(bg,0),transfer(qv,0),status
     if (ios.ne.0) error stop 'PR90 T7 trace write failed'
     close(unit,iostat=ios)
     if (ios.ne.0) error stop 'PR90 T7 trace close failed'
   end subroutine pr90_t7_trace
{TRACE_END}
"""


def add_t7_trace(source: str, expected_sha256: str = SOURCE_SHA256) -> str:
    """Insert bounded exact-state records without changing KDM6 calculations."""
    actual = hashlib.sha256(source.encode()).hexdigest()
    if actual != expected_sha256:
        raise TraceTransformError(f"unexpected KDM6 source hash: {actual}")
    if "PR90_T7_PRODUCER" in source:
        raise TraceTransformError("T7 producer trace already present")

    first_exec = "   idim = ite-its+1\n"
    source = _replace_once(source, first_exec,
        _call("ENTRY", entry=True) + first_exec, "KDM62D entry")

    placements = (
        ("          if(supcol.gt.2. .and. qci(i,k,1).gt.qmin) then  \n",
         "STAGE1_PSD_END", "before"),
        ("          nci(i,k,2) = max(nci(i,k,2),0.0)\n",
         "AFTER_FREEZING", "after"),
        ("          avedia(i,k,1) = rslopec(i,k)*(g3pmc)**(1./3.)\n",
         "STAGE2_PSD_END", "before"),
        ("            ! PR89: same-call column water measure, DEN*DELZ (kg m-2).\n",
         "COLD_COMMIT", "before"),
        ("            qci(i,k,1)=rain_warm_q_after(1)\n",
         "WARM_BEFORE_COMMIT", "before"),
        ("            q(i,k)=rain_warm_qv_after\n",
         "WARM_AFTER_COMMIT", "after"),
        ("           pr85_cutoff_q_before=[qci(i,k,1),qci(i,k,2),qrs(i,k,1),qrs(i,k,2),qrs(i,k,3)]\n",
         "PREFINAL_CUTOFF", "before"),
        ("            call kdm6_refresh_graupel_intercept(progb_status(i,k),n0g,g1pmg, &\n",
         "FINAL_PSD_END", "after-call"),
    )
    for anchor, stage, placement in placements:
        call = _call(stage)
        if placement == "before":
            replacement = call + anchor
        elif placement == "after":
            replacement = anchor + call
        else:
            # Insert after the two-line call and its error-stop check.
            block = (anchor +
                     "                 rslopemu(i,k,3),n0go(i,k),graupel_cache_valid)\n"
                     "            if (.not.graupel_cache_valid) error stop 'KDM6 final graupel intercept cache invalid'\n")
            replacement = block + call
            anchor = block
        if stage == "STAGE2_PSD_END":
            source = _replace_first(source, anchor, replacement, stage)
        else:
            source = _replace_once(source, anchor, replacement, stage)

    # The sedimentation checkpoint is immediately before the first stage-1 PSD
    # reconstruction, after all sedimentation operators and the local slope refresh.
    stage1_anchor = "          if(qrs(i,k,1).ge.qcrmin .and. nrs(i,k,1) .ge. nrmin) then\n"
    source = _replace_first(source, stage1_anchor,
                            _call("POST_SED_PRE_STAGE1") + stage1_anchor,
                            "post-sedimentation checkpoint")

    warm_guard = "            if (rain_warm_search_status.eq.1) then\n"
    warm_target_guard = ("            if (rain_warm_search_status.eq.1 .or. &\n"
        "                (pr87_model_timestep.eq.7 .and. lat.eq.222 .and. i.eq.193 .and. k.eq.4)) then\n")
    source = _replace_once(source, warm_guard, warm_target_guard, "warm ledger target gate")
    if source.count("PR90_T7_TRACE_INSERT_BEGIN") != 10:
        raise TraceTransformError("expected ten target-only trace insertion sites")
    return _replace_once(source, "\nEND MODULE module_mp_kdm6\n",
                         _TRACE_HELPER + "END MODULE module_mp_kdm6\n",
                         "module helper location")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    transformed = add_t7_trace(args.source.read_text(encoding="utf-8"))
    args.output.write_text(transformed, encoding="utf-8")


if __name__ == "__main__":
    main()
