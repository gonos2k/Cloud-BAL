#!/usr/bin/env python3
"""Add observer-only donor checkpoints to the retained PR69 KDM6 source."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

EXPECTED_SOURCE_SHA256 = "ee688498b32b7a1ccaf69858f62f4e457f7153df4fb8b965acfd069d8eefb425"
CALL_START = "   call ProgB_param(brs,qrs_tmp,rhox,its,ite,jts,jte,kts,kte,qcrmin"
CALL_END = "                   ,g1pbg,g3pbg,g4pbg,g5pbgo2,g1pdgbgmg,dgbgmug1)"


def instrument(source: str) -> str:
    if hashlib.sha256(source.encode()).hexdigest() != EXPECTED_SOURCE_SHA256:
        raise ValueError("selected observer source hash mismatch")
    if source.count(CALL_START) != 7 or source.count(CALL_END) != 8:
        raise ValueError("ProgB_param call inventory changed")
    consumer = "            call kdm6_mass_volume_rate(pgdep(i,k),rhox(i,k), &"
    if source.count(consumer) != 1:
        raise ValueError("pgdep volume consumer anchor mismatch")

    helper = """\n   subroutine pr70_write_progb_checkpoint(trace,phase,stage,lat,its,ite,kts,kte, &\n        qrs,brs,dtcld)\n     implicit none\n     logical,intent(in) :: trace\n     character(len=*),intent(in) :: phase\n     integer,intent(in) :: stage,lat,its,ite,kts,kte\n     real,intent(in) :: qrs(its:ite,kts:kte,3),brs(its:ite,kts:kte),dtcld\n     integer :: i,k\n     if(.not.trace) return\n     i=125\n     k=17\n     if(i.lt.its .or. i.gt.ite .or. k.lt.kts .or. k.gt.kte) return\n     write(*,*) 'PR70_PROGB',trim(phase),stage,lat,i,k,qrs(i,k,3), &\n          brs(i,k),dtcld,qrs(i,k,3).gt.1.e-9 .or. brs(i,k).gt.1.e-15\n   end subroutine pr70_write_progb_checkpoint\n\n"""
    module_anchor = "   subroutine kdm6(th, q, qc, qr, qi, qs, qg,             &"
    if source.count(module_anchor) != 1:
        raise ValueError("module helper insertion anchor mismatch")
    source = source.replace(module_anchor, helper + module_anchor, 1)

    parts = source.split(CALL_START)
    result = parts[0]
    for call_index, tail in enumerate(parts[1:], start=1):
        call_text = CALL_START + tail.split(CALL_END, 1)[0] + CALL_END
        rest = tail.split(CALL_END, 1)[1]
        if call_index <= 5:
            before = (
                f"      call pr70_write_progb_checkpoint(pr67_trace_this_call,'PRE',{call_index}, &\n"
                f"           lat,its,ite,kts,kte,qrs_tmp,brs,dtcld)\n"
            )
            after = (
                f"\n      call pr70_write_progb_checkpoint(pr67_trace_this_call,'POST',{call_index}, &\n"
                f"           lat,its,ite,kts,kte,qrs_tmp,brs,dtcld)"
            )
            result += before + call_text + after + rest
        else:
            result += call_text + rest
    source = result

    donor_trace = (
        "            if(pr67_trace_this_call .and. i.eq.125 .and. k.eq.17) &\n"
        "              write(*,*) 'PR70_PGDEP_DONOR',lat,i,k,qrs(i,k,3), &\n"
        "                   brs(i,k),dtcld,pgdep(i,k),rh(i,k,2),rhox(i,k), &\n"
        "                   qrs(i,k,3).gt.qcrmin .or. brs(i,k).gt.1.e-15, &\n"
        "                   rhox(i,k).ge.100. .and. rhox(i,k).le.900.\n"
    )
    source = source.replace(consumer, donor_trace + consumer, 1)
    if source.count("call pr70_write_progb_checkpoint(pr67_trace_this_call,'PRE'") != 5:
        raise ValueError("pre-call observer insertion count mismatch")
    if source.count("call pr70_write_progb_checkpoint(pr67_trace_this_call,'POST'") != 5:
        raise ValueError("post-call observer insertion count mismatch")
    return source


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        raise SystemExit(f"refusing to overwrite source: {args.output}")
    text = instrument(args.source.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")
    print(hashlib.sha256(text.encode()).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
