#!/usr/bin/env python3
"""Add source-ordered, read-only QC write events to the retained replay source."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import pr94_cloud_response as cloud  # noqa: E402
import pr99_compact_stage_source as compact  # noqa: E402


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def support_points(composition: dict[str, Any]) -> list[tuple[int, int, int]]:
    influence = composition["composed_qc_vertical_influence"]
    support = cloud.make_masks(influence, (39, 280, 232))["original_613_native_support"]
    kji = [(int(k) + 1, int(j) + 2, int(i) + 2)
           for k, j, i in zip(*support.nonzero(), strict=True)]
    if len(kji) != 613 or len(set(kji)) != 613:
        raise ValueError("expected 613 unique source-composed QC locations")
    return kji


def _replace_once(text: str, before: str, after: str, label: str) -> str:
    count = text.count(before)
    if count != 1:
        raise ValueError(f"expected one {label} anchor, found {count}")
    return text.replace(before, after, 1)


def _mask_code(points: list[tuple[int, int, int]]) -> str:
    by_j: dict[int, list[tuple[int, int]]] = {}
    for k, j, i in points:
        by_j.setdefault(j, []).append((i, k))
    lines = ["   pr100_qc_support=.false.", "   select case(lat)"]
    for j, cells in sorted(by_j.items()):
        lines.append(f"   case({j})")
        lines.extend(f"     pr100_qc_support({i},{k})=.true." for i, k in sorted(cells))
    lines.extend(["   case default", "   end select"])
    return "\n".join(lines) + "\n"


def _event_call(label: str, before: str = "pr100_qc_before",
                group_setup: str = "") -> str:
    return (group_setup +
            f"      if (pr87_model_timestep.eq.1 .and. pr100_qc_support(i,k)) &\n"
            f"        call pr100_write_qc_event(pr100_qc_unit,pr100_qc_ordinal, &\n"
            f"          pr87_model_timestep,lat,pr100_loop_tag, i,k,'{label}', &\n"
            f"          {before},qci(i,k,1),pr100_qc_proposal,pr100_qc_alpha, &\n"
            f"          pr100_qc_approved,pr100_qc_deferred)\n")


def _instrument_assignment(text: str, statement: str, label: str,
                           occurrence: int = 1) -> str:
    starts: list[int] = []
    offset = 0
    while (found := text.find(statement, offset)) >= 0:
        starts.append(found)
        offset = found + len(statement)
    if not 1 <= occurrence <= len(starts):
        raise ValueError(f"expected QC write {label!r} occurrence {occurrence}, found {len(starts)}")
    start = starts[occurrence - 1]
    indent = statement[:len(statement) - len(statement.lstrip())]
    capture = (f"{indent}pr100_qc_proposal=0.0; pr100_qc_alpha=0.0\n"
               f"{indent}pr100_qc_approved=0.0; pr100_qc_deferred=0.0\n"
               f"{indent}pr100_qc_before=qci(i,k,1)\n")
    emit = _event_call(label).replace("      if", indent + "if")
    return text[:start] + capture + statement + "\n" + emit.rstrip("\n") + text[start + len(statement):]


def prepare(source: str, composition: dict[str, Any]) -> tuple[str, list[tuple[int, int, int]]]:
    """Apply compact source generation, then add observation-only hooks."""
    staged = compact.prepare(source)
    points = support_points(composition)
    staged = _replace_once(staged,
        "   real :: cloud_evap_extent\n",
        "   real :: cloud_evap_extent\n"
        "   real :: pr100_qc_before,pr100_qc_proposal(4),pr100_qc_approved(4)\n"
        "   real :: pr100_qc_alpha(4),pr100_qc_deferred(4)\n"
        "   logical, allocatable :: pr100_qc_support(:,:)\n"
        "   logical, save :: pr100_qc_open=.false.\n"
        "   integer, save :: pr100_qc_unit,pr100_qc_ordinal=0\n"
        "   integer :: pr100_loop_tag\n", "QC observer declarations")
    staged = _replace_once(staged,
        "   idim = ite-its+1\n",
        "   idim = ite-its+1\n"
        "   allocate(pr100_qc_support(its:ite,kts:kte))\n" + _mask_code(points) +
        "   if (pr87_model_timestep.eq.1 .and. lat.eq.jts .and. .not.pr100_qc_open) then\n"
        "     open(newunit=pr100_qc_unit,file='pr100_qc_process.raw',form='formatted', &\n"
        "          status='replace',action='write')\n"
        "     write(pr100_qc_unit,'(a)') 'PR100_QC_V1 613 fixed_source_support'\n"
        "     pr100_qc_ordinal=0\n"
        "     pr100_qc_open=.true.\n"
        "   endif\n"
        "   pr100_loop_tag=-1\n"
        "   pr100_qc_proposal=0.0; pr100_qc_alpha=0.0\n"
        "   pr100_qc_approved=0.0; pr100_qc_deferred=0.0\n", "QC mask/init")
    entry = ("   call validate_kdm6_species_states(qci,qrs,nrs,nci,brs)\n"
             "   do k = kts, kte\n")
    entry_rows = ("   call validate_kdm6_species_states(qci,qrs,nrs,nci,brs)\n"
        "   if (pr87_model_timestep.eq.1) then\n"
        "     do k=kts,kte\n"
        "       do i=its,ite\n"
        "         if (pr100_qc_support(i,k)) then\n"
        "           pr100_qc_proposal=0.0; pr100_qc_alpha=0.0\n"
        "           pr100_qc_approved=0.0; pr100_qc_deferred=0.0\n"
        "           call pr100_write_qc_event(pr100_qc_unit,pr100_qc_ordinal, &\n"
        "             pr87_model_timestep,lat,-1,i,k,'ENTRY',qci(i,k,1),qci(i,k,1), &\n"
        "             pr100_qc_proposal,pr100_qc_alpha,pr100_qc_approved,pr100_qc_deferred)\n"
        "         endif\n"
        "       enddo\n"
        "     enddo\n"
        "   endif\n"
        "   do k = kts, kte\n")
    staged = _replace_once(staged, entry, entry_rows, "QC entry endpoint")
    staged = _replace_once(staged, "   do loop = 1,loops\n",
                           "   do loop = 1,loops\n     pr100_loop_tag=loop\n",
                           "per-substep QC loop tag")

    writes = (
        ("       qci(i,k,1) = max(qci(i,k,1),0.0)", "NORMALIZE"),
        ("                      qci(i,k,1) = pr85_melt_qc_after", "MELT"),
        ("                  qci(i,k,1) = qci(i,k,1) + qci(i,k,2)", "ICE_TO_CLOUD"),
        ("            qci(i,k,1) = 0.", "ICE_EXTINCTION"),
        ("                      qci(i,k,1)=pr85_freeze_qc_after", "PINU"),
        ("                      qci(i,k,1)=pr85_freeze_qc_after", "PFRZ"),
        ("            qci(i,k,1) = qci(i,k,1)+qrs(i,k,1)", "GRAUPEL_TO_CLOUD"),
        ("            qci(i,k,1) = max(qci(i,k,1)+pcact(i,k)*dtcld,0.)", "ACTIVATION"),
        ("            qci(i,k,1) = 0.", "FULL_EVAPORATION"),
        ("            qci(i,k,1) = max(qci(i,k,1)+pcond(i,k)*dtcld,0.)", "CONDENSATION"),
        ("              qci(i,k,1) = 0.0", "CUTOFF"),
    )
    # Four source writes share qci=0. Replace them by their ordered, unique full-line anchors.
    seen: dict[str, int] = {}
    for statement, label in writes:
        seen[statement] = seen.get(statement, 0) + 1
        staged = _instrument_assignment(staged, statement, label, seen[statement])

    # The cold/warm commits have one stored delta; approved components are diagnostic columns.
    cold_anchor = "            qci(i,k,1)=rain_q_after(1)"
    cold_setup = ("            pr100_qc_before=rain_q_before(1)\n"
        "            pr100_qc_proposal=0.0; pr100_qc_alpha=0.0\n"
        "            pr100_qc_approved=0.0; pr100_qc_deferred=0.0\n"
        "            pr100_qc_proposal(1)=rain_ng_q_process(1)\n"
        "            pr100_qc_alpha(1)=rain_ng_alpha\n"
        "            pr100_qc_approved(1)=rain_ng_alpha*rain_ng_q_process(1)\n"
        "            pr100_qc_deferred(1)=rain_ng_q_process(1)-pr100_qc_approved(1)\n"
        "            pr100_qc_proposal(2)=rain_aut_q_process(1)\n"
        "            pr100_qc_alpha(2)=rain_aut_alpha\n"
        "            pr100_qc_approved(2)=rain_aut_alpha*rain_aut_q_process(1)\n"
        "            pr100_qc_deferred(2)=rain_aut_q_process(1)-pr100_qc_approved(2)\n"
        "            pr100_qc_proposal(3)=rain_q_process_request(1)\n"
        "            pr100_qc_alpha(3)=rain_g_alpha\n"
        "            pr100_qc_approved(3)=rain_g_alpha*rain_q_process_request(1)\n"
        "            pr100_qc_deferred(3)=rain_q_process_request(1)-pr100_qc_approved(3)\n")
    staged = _replace_once(staged, cold_anchor,
        cold_setup + cold_anchor + "\n" + _event_call("COLD_COMMIT").rstrip("\n"),
        "QC cold commit")

    warm_anchor = "            qci(i,k,1)=rain_warm_q_after(1)"
    warm_setup = ("            pr100_qc_before=rain_q_before(1)\n"
        "            pr100_qc_proposal=0.0; pr100_qc_alpha=0.0\n"
        "            pr100_qc_approved=0.0; pr100_qc_deferred=0.0\n"
        "            pr100_qc_proposal(4)=rain_warm_q_process(1)\n"
        "            pr100_qc_alpha(4)=rain_warm_alpha\n"
        "            pr100_qc_approved(4)=rain_warm_alpha*rain_warm_q_process(1)\n"
        "            pr100_qc_deferred(4)=rain_warm_q_process(1)-pr100_qc_approved(4)\n")
    staged = _replace_once(staged, warm_anchor,
        warm_setup + warm_anchor + "\n" + _event_call("WARM_COMMIT").rstrip("\n"),
        "QC warm commit")

    exit_anchor = "   call liquid_end(lat,its,ite)\n"
    exit_code = ("   if (pr87_model_timestep.eq.1) then\n"
        "     do k=kts,kte\n"
        "       do i=its,ite\n"
        "         if (pr100_qc_support(i,k)) then\n"
        "           pr100_qc_proposal=0.0; pr100_qc_alpha=0.0\n"
        "           pr100_qc_approved=0.0; pr100_qc_deferred=0.0\n"
        "           call pr100_write_qc_event(pr100_qc_unit,pr100_qc_ordinal, &\n"
        "             pr87_model_timestep,lat,-1,i,k,'EXIT',qci(i,k,1),qci(i,k,1), &\n"
        "             pr100_qc_proposal,pr100_qc_alpha,pr100_qc_approved,pr100_qc_deferred)\n"
        "         endif\n"
        "       enddo\n"
        "     enddo\n"
        "   endif\n"
        "   deallocate(pr100_qc_support)\n"
        "   if (pr87_model_timestep.eq.1 .and. lat.eq.jte .and. pr100_qc_open) then\n"
        "     close(pr100_qc_unit)\n"
        "     pr100_qc_open=.false.\n"
        "   endif\n")
    staged = _replace_once(staged, exit_anchor, exit_code + exit_anchor, "QC exit endpoint")
    helper_anchor = "        REAL FUNCTION GAMMLN(x)\n"
    helper = '''subroutine pr100_write_qc_event(unit,ordinal,timestep,j,loop,i,k,label,before,after, &
                                proposal,alpha,approved,deferred)
  implicit none
  integer, intent(in) :: unit,timestep,j,loop,i,k
  integer, intent(inout) :: ordinal
  character(len=*), intent(in) :: label
  real, intent(in) :: before,after,proposal(4),alpha(4),approved(4),deferred(4)
  integer :: before_bits,after_bits
  before_bits=transfer(before,0)
  after_bits=transfer(after,0)
  ordinal=ordinal+1
  write(unit,'(a,a,8(",",i0),*(1x,es24.16e3))') 'QCEVENT ',trim(label), &
       ordinal,timestep,j,loop,i,k,before_bits,after_bits, &
       dble(before),dble(after),dble(after)-dble(before), &
       dble(proposal),dble(alpha),dble(approved),dble(deferred)
end subroutine pr100_write_qc_event

'''
    staged = _replace_once(staged, helper_anchor, helper + helper_anchor, "QC event writer helper")
    return staged, points


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("composition", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("mask", type=Path)
    args = parser.parse_args()
    composition_bytes = args.composition.read_bytes()
    composition = json.loads(composition_bytes)
    source = args.source.read_text(encoding="ascii")
    generated, points = prepare(source, composition)
    args.output.write_text(generated, encoding="ascii")
    mask_bytes = "".join(f"{i} {j} {k}\n" for k,j,i in points).encode("ascii")
    args.mask.write_bytes(mask_bytes)
    receipt = {"schema": "pr100_qc_source_v1", "input_source_sha256": sha256_bytes(source.encode("ascii")),
        "input_composition_sha256": sha256_bytes(composition_bytes),
        "generated_source_sha256": sha256_bytes(generated.encode("ascii")),
        "mask_sha256": sha256_bytes(mask_bytes), "mask_points": len(points),
        "mask_columns": len({(j,i) for _k,j,i in points}),
        "output_source": str(args.output.resolve()), "mask_path": str(args.mask.resolve())}
    receipt_path = args.output.with_suffix(args.output.suffix + ".json")
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
