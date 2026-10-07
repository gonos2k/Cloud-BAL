#!/usr/bin/env python3
"""Create a targeted observer derivative from one hash-pinned KDM6 source."""
from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

def _once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ValueError(f"source anchor {label!r} occurs {count} times")
    return text.replace(old, new, 1)


def _call(event: int, rates: bool = False) -> str:
    names = ("praut(i,k)", "pracw(i,k)", "prevp(i,k)", "piacr(i,k)",
             "pgacr(i,k)", "psacr(i,k)", "pmulrs(i,k)", "pmulrg(i,k)",
             "paacw(i,k)", "pseml(i,k)", "pgeml(i,k)", "nraut(i,k)",
             "nrcol(i,k)", "niacr(i,k)", "nraci(i,k)", "nsacr(i,k)",
             "ngacr(i,k)", "nseml(i,k)", "ngeml(i,k)")
    rate_fields = ("praut", "pracw", "prevp", "piacr", "pgacr", "psacr", "pmulrs",
                   "pmulrg", "paacw", "pseml", "pgeml", "nraut", "nrcol", "niacr",
                   "nraci", "nsacr", "ngacr", "nseml", "ngeml")
    cold_rates = {"praut", "pracw", "prevp", "piacr", "pgacr", "psacr", "pmulrs",
                  "pmulrg", "nraut", "nraci", "nrcol", "niacr", "nsacr", "ngacr"}
    warm_rates = {"praut", "pracw", "prevp", "paacw", "pseml", "pgeml",
                  "nraut", "nrcol", "nseml", "ngeml"}
    supported_rates = cold_rates if event in (4, 5) else warm_rates if event in (8, 9) else set()
    rate_args = [
        value if rates and field in supported_rates else "0.0"
        for field, value in zip(rate_fields, names, strict=True)
    ]
    loop_arg, mstep_arg = ("0", "0") if event == 0 else ("loop", "n")
    pending_arg = "0" if event == 0 else "merge(1,0,rain_full_evap_pending(i,k))"
    if event in (4, 5):
        trial_assign = '''            pr68_qr_trial = qrs(i,k,1)+(praut(i,k)+pracw(i,k)+prevp(i,k)    &
                           -piacr(i,k)-pgacr(i,k)-psacr(i,k)-pmulrs(i,k)    &
                           -pmulrg(i,k))*dtcld
            pr68_nr_trial = nrs(i,k,1)+(nraut(i,k)-nrcol(i,k)-niacr(i,k)    &
                           -nraci(i,k)-nsacr(i,k)-ngacr(i,k))*dtcld
'''
        trial_args = "pr68_qr_trial,pr68_nr_trial"
    elif event in (8, 9):
        trial_assign = '''            pr68_qr_trial = qrs(i,k,1)+(praut(i,k)+pracw(i,k)+prevp(i,k)    &
                           +paacw(i,k)+paacw(i,k)-pseml(i,k)-pgeml(i,k))*dtcld
            pr68_nr_trial = nrs(i,k,1)+(nraut(i,k)-nrcol(i,k)                &
                           +nseml(i,k)+ngeml(i,k))*dtcld
'''
        trial_args = "pr68_qr_trial,pr68_nr_trial"
    elif event == 6:
        trial_assign = ""
        trial_args = "pr68_qr_trial, pr68_nr_trial"
    elif event == 10:
        trial_assign = ""
        trial_args = "pr68_qr_trial, pr68_nr_trial"
    else:
        trial_assign = ""
        trial_args = "0.0, 0.0"
    limiter_args = "value,source" if event in (4, 5, 8, 9) else "0.0,0.0"
    rate_lines = [", ".join(rate_args[index:index + 4]) for index in range(0, len(rate_args), 4)]
    continuation = ", &\n              ".join(rate_lines)
    code = f'''          if(pr67_trace_this_call .and. pr68_rain_target(i,lat,k)) then
{trial_assign}            call pr68_write_rain_event(pr68_unit,{event},i,lat,k,{loop_arg},{mstep_arg}, &
              {pending_arg},qrs(i,k,1),nrs(i,k,1), &
              qci(i,k,1),nci(i,k,1),nci(i,k,2),nci(i,k,3),t(i,k),qcrmin, &
              nrmin,dtcld,{trial_args},{limiter_args}, &
              {continuation})
          endif
'''
    if event in (0, 1, 2, 3, 15):
        return "      do k = kts, kte\n        do i = its, ite\n" + code + "        enddo\n      enddo\n"
    return code


def instrument(source: str, expected_sha256: str, targets: list[tuple[int, int, int]]) -> str:
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if digest != expected_sha256:
        raise ValueError(f"selected generated source hash mismatch: {digest}")
    helper = '''
   logical function pr68_rain_target(i,j,k)
     implicit none
     integer, intent(in) :: i,j,k
     pr68_rain_target = .false.
     if (PR68_TARGET_EXPR) pr68_rain_target = .true.
   end function pr68_rain_target

   subroutine pr68_write_rain_event(unit,event,i,j,k,loop,mstep,pending, &
        qr,nr,qc,nc,ni,nccn,temp,qcrmin,nrmin,dtcld,qr_trial,nr_trial, &
        limiter_value,limiter_source, &
        praut,pracw,prevp,piacr, &
        pgacr,psacr,pmulrs,pmulrg,paacw,pseml,pgeml,nraut,nrcol,niacr, &
        nraci,nsacr,ngacr,nseml,ngeml)
     implicit none
     integer,intent(in) :: unit,event,i,j,k,loop,mstep,pending
     real,intent(in) :: qr,nr,qc,nc,ni,nccn,temp,qcrmin,nrmin,dtcld,qr_trial,nr_trial
     real,intent(in) :: limiter_value,limiter_source
     real,intent(in) :: praut,pracw,prevp,piacr,pgacr,psacr,pmulrs,pmulrg
     real,intent(in) :: paacw,pseml,pgeml,nraut,nrcol,niacr,nraci
     real,intent(in) :: nsacr,ngacr,nseml,ngeml
     write(unit,'(a,1x,7(i0,1x),33(es24.16e3,1x))') 'PR68R001', &
       event,i,j,k,loop,mstep,pending,qr,nr,qc,nc,ni,nccn,temp,qcrmin,nrmin, &
       dtcld,qr_trial,nr_trial,limiter_value,limiter_source, &
       praut,pracw,prevp,piacr,pgacr,psacr,pmulrs,pmulrg,paacw,pseml,pgeml, &
       nraut,nrcol,niacr,nraci,nsacr,ngacr,nseml,ngeml
   end subroutine pr68_write_rain_event
'''
    if len(targets) != 25 or len(set(targets)) != 25:
        raise ValueError("target manifest must contain exactly 25 distinct failure coordinates")
    target_expr = " .or. &\n".join(
        f"       (i.eq.{i}.and.j.eq.{j}.and.k.eq.{k})" for i, j, k in targets
    )
    helper = helper.replace("PR68_TARGET_EXPR", target_expr)
    source = _once(source, "    subroutine kdm6(th, q, qc, qr, qi, qs, qg,             &",
                   helper + "\n    subroutine kdm6(th, q, qc, qr, qi, qs, qg,             &", "module helper")
    source = _once(source, "   integer :: pr67_unit\n", "   integer :: pr67_unit\n   integer :: pr68_unit\n   real :: pr68_qr_trial,pr68_nr_trial\n", "unit declaration")
    open_code = '''      if (pr67_trace_this_call) then
        if (lat.eq.jts) then
          open(newunit=pr68_unit,file='pr68_kdm6_rain.raw',status='replace', &
               action='write')
        else
          open(newunit=pr68_unit,file='pr68_kdm6_rain.raw',status='old', &
               position='append',action='write')
        endif
      endif
'''
    clamp = "   do k = kts, kte\n     do i = its, ite\n       qci(i,k,1) = max(qci(i,k,1),0.0)"
    source = _once(source, clamp, open_code + clamp, "observer open")
    entry = '''   do k = kts,kte
     do i = its,ite
       dend(i,k) = den(i,k)
     enddo
   enddo
'''
    entry_observer = '''   do k = kts,kte
     do i = its,ite
       if(pr67_trace_this_call .and. pr68_rain_target(i,lat,k)) then
         pr68_qr_trial = 0.0
         pr68_nr_trial = 0.0
       endif
     enddo
   enddo
'''
    source = _once(source, entry, entry + entry_observer + _call(0), "entry state")
    first_process_capture = '''      if (pr67_trace_this_call) then
        open(newunit=pr67_unit,file='pr67_kdm6_process.raw', &
             access='stream',form='unformatted',status='unknown',position='append')
        write(pr67_unit) 'PR67P001'
        write(pr67_unit) 0,lat,its,ite,kts,kte,dtcld
'''
    source = _once(source, first_process_capture,
                   _call(1) + first_process_capture, "post-rain sedimentation")
    melting = '''      do k = kte, kts, -1
        do i = its, ite
          supcol = t0c-t(i,k)
'''
    source = _once(source, melting, _call(2) + melting, "post-ice sedimentation")
    post_freeze = '''      do k = kts, kte
        do i = its, ite
          nrs(i,k,1) = max(nrs(i,k,1),0.0)
          nci(i,k,1) = max(nci(i,k,1),0.0)
          nci(i,k,2) = max(nci(i,k,2),0.0)
        enddo
      enddo
'''
    source = _once(source, post_freeze, post_freeze + _call(3), "post-freezing transfer")

    cold_limit = '''            source = (-nraut(i,k)+nraci(i,k)+nrcol(i,k)+niacr(i,k)+nsacr(i,k)+ngacr(i,k))*dtcld
            if (source.gt.value) then
'''
    source = _once(source, cold_limit, cold_limit.replace("            if (source.gt.value) then\n", _call(4, True) + "            if (source.gt.value) then\n"), "cold limiter inputs")
    warm_limit = '''            source = (-nraut(i,k)+nrcol(i,k)-nseml(i,k)-ngeml(i,k)             &
                      )*dtcld
            if (source.gt.value) then
'''
    source = _once(source, warm_limit, warm_limit.replace("            if (source.gt.value) then\n", _call(8, True) + "            if (source.gt.value) then\n"), "warm limiter inputs")
    source = _once(source,
        "            work2(i,k)=-(prevp(i,k)+psdep(i,k)+pgdep(i,k)+pinud(i,k)+pidep(i,k))",
        _call(5, True) + "            work2(i,k)=-(prevp(i,k)+psdep(i,k)+pgdep(i,k)+pinud(i,k)+pidep(i,k))",
        "cold number limiter end")
    source = _once(source,
        "            work2(i,k)=-(prevp(i,k)+psevp(i,k)+pgevp(i,k))",
        _call(9, True) + "            work2(i,k)=-(prevp(i,k)+psevp(i,k)+pgevp(i,k))",
        "warm number limiter end")
    cold_update = '''            qrs(i,k,1) = max(qrs(i,k,1)+(praut(i,k)+pracw(i,k)                 &
                           +prevp(i,k)-piacr(i,k)-pgacr(i,k)                   &
                           -psacr(i,k)-pmulrs(i,k)-pmulrg(i,k))*dtcld,0.)
            nrs(i,k,1) = max(nrs(i,k,1)+(nraut(i,k)-nrcol(i,k)-niacr(i,k)      &
                           -nraci(i,k)-nsacr(i,k)-ngacr(i,k))*dtcld,0.)
'''
    cold_trial = '''            pr68_qr_trial = qrs(i,k,1)+(praut(i,k)+pracw(i,k)                 &
                           +prevp(i,k)-piacr(i,k)-pgacr(i,k)                   &
                           -psacr(i,k)-pmulrs(i,k)-pmulrg(i,k))*dtcld
            pr68_nr_trial = nrs(i,k,1)+(nraut(i,k)-nrcol(i,k)-niacr(i,k)      &
                           -nraci(i,k)-nsacr(i,k)-ngacr(i,k))*dtcld
'''
    warm_update = '''            qrs(i,k,1) = max(qrs(i,k,1)+(praut(i,k)+pracw(i,k)                 &
                    +prevp(i,k)+paacw(i,k)+paacw(i,k)-pseml(i,k)               &
                    -pgeml(i,k))*dtcld,0.)
'''
    warm_trial = '''            pr68_qr_trial = qrs(i,k,1)+(praut(i,k)+pracw(i,k)                 &
                    +prevp(i,k)+paacw(i,k)+paacw(i,k)-pseml(i,k)               &
                           -pgeml(i,k))*dtcld
            pr68_nr_trial = nrs(i,k,1)+(nraut(i,k)-nrcol(i,k)+nseml(i,k)      &
                           +ngeml(i,k))*dtcld
'''
    source = _once(source, cold_update, cold_trial + cold_update, "cold QR/NR update")
    source = _once(source, warm_update, warm_trial + warm_update, "warm QR update")

    pending = "            if(rain_full_evap_pending(i,k) .and. qrs(i,k,1).le.qcrmin) then\n"
    if source.count(pending) != 2:
        raise ValueError("expected cold and warm full-evaporation gates")
    pending_end = "              nrs(i,k,1) = 0.\n            endif\n"
    if source.count(pending_end) != 2:
        raise ValueError("expected cold and warm pending transfer statements")
    gate_positions = [match.start() for match in re.finditer(re.escape(pending), source)]
    end_positions = [match.end() for match in re.finditer(re.escape(pending_end), source)]
    if not (gate_positions[0] < end_positions[0] < gate_positions[1] < end_positions[1]):
        raise ValueError("warm/cold full-evaporation blocks are unexpectedly ordered")
    for position, injected in reversed([
        (gate_positions[0], _call(6, True)),
        (end_positions[0], _call(7, True)),
        (gate_positions[1], _call(10, True)),
        (end_positions[1], _call(11, True)),
    ]):
        source = source[:position] + injected + source[position:]

    classification = re.compile(
        r"(?ms)^\s*if\(avedia\(i,k,2\)\.le\.di82\) then\n"
        r".*?^\s*endif\s*$"
    )
    match = classification.search(source)
    if not match or classification.search(source, match.end()):
        raise ValueError("source anchor 'rain to cloud transfer' is missing or ambiguous")
    source = source[:match.end()] + "\n" + _call(12) + source[match.end():]
    threshold = '''           if(qrs(i,k,1).le.qcrmin)then
              qrs(i,k,1) = 0.0
              nrs(i,k,1) = 0.0
           endif
'''
    source = _once(source, threshold, threshold + _call(13), "final threshold")
    slope_bound = '''            if( nrs(i,k,1).gt.nrmax ) then
              lamdr_tmp(i,k) = lamdarmax
              nrs(i,k,1) = den(i,k)*qrs(i,k,1)*lamdr_tmp(i,k)**dmr/pidnr
            endif
'''
    source = _once(source, slope_bound, slope_bound + _call(14), "final slope bound")
    source = _once(source, "   end subroutine kdm62d",
                   _call(15) + "      if (pr67_trace_this_call) close(pr68_unit)\n\n   end subroutine kdm62d",
                   "observer close")
    return source


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--expect-sha256", required=True)
    parser.add_argument("--targets-json", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        raise SystemExit(f"refusing to overwrite observer source: {args.output}")
    source = args.source.read_text(encoding="utf-8")
    target_manifest = __import__("json").loads(args.targets_json.read_text(encoding="utf-8"))
    if target_manifest.get("schema") != "pr68_kdm6_failure_targets_v1":
        raise SystemExit("unsupported target manifest")
    targets = [tuple(int(v) for v in row) for row in target_manifest.get("coordinates_ijk", [])]
    output = instrument(source, args.expect_sha256, targets)
    args.output.write_text(output, encoding="utf-8")
    print(hashlib.sha256(output.encode("utf-8")).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
