#!/usr/bin/env python3
"""Emit the PR71 ProgB_param output-contract patch for frozen PR70 source."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
from pathlib import Path


SOURCE_SHA256 = "487afbf064b6a3598ecb12248224fc3b91c77e1b0ed921d0e0e8130cacb9b583"
CALL_COUNT = 7
OUTPUTS = (
    "rhox", "cmg", "pidn0g", "avtg", "pvtg", "precg2", "bvtg", "bvtg1",
    "bvtg2", "bvtg3", "bvtg4", "rslopegbmax", "g1pbg", "g3pbg", "g4pbg",
    "g5pbgo2", "g1pdgbgmg", "dgbgmug1",
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise ValueError(f"expected one {label} anchor, found {count}")
    return source.replace(old, new, 1)


def regex_once(source: str, pattern: str, replacement: str, label: str) -> str:
    updated, count = re.subn(pattern, replacement, source, count=1, flags=re.I | re.M)
    if count != 1:
        raise ValueError(f"expected one {label} pattern, found {count}")
    return updated


def bounds(source: str, name: str) -> tuple[int, int]:
    lowered = source.lower()
    folded_name = name.lower()
    start = re.search(rf"^\s*subroutine\s+{folded_name}\s*\(", lowered, re.M)
    if start is None:
        raise ValueError(f"missing subroutine {name}")
    end = re.search(rf"^\s*end\s+subroutine\s+{folded_name}\b", lowered[start.end():], re.M)
    if end is None:
        raise ValueError(f"missing end of {name}")
    return start.start(), start.end() + end.end()


def in_subroutine(source: str, name: str, change) -> str:
    start, end = bounds(source, name)
    return source[:start] + change(source[start:end]) + source[end:]


def output_zeroes(indent: str = "          ") -> str:
    return "\n".join(f"{indent}{output}(i,k) = 0.0" for output in OUTPUTS)


def add_status_to_calls(source: str) -> str:
    old = "                   ,g1pbg,g3pbg,g4pbg,g5pbgo2,g1pdgbgmg,dgbgmug1)"
    if source.count(old) != CALL_COUNT:
        raise ValueError(f"expected {CALL_COUNT} ProgB call endings, found {source.count(old)}")
    return source.replace(old, old.replace(")", ",progb_status)"))


def transform_module(source: str) -> str:
    return once(
        source,
        "   use module_model_constants, only : RE_QC_BG, RE_QI_BG, RE_QS_BG\n",
        "   use module_model_constants, only : RE_QC_BG, RE_QI_BG, RE_QS_BG\n"
        "   integer, parameter, private :: PROGB_ABSENT = 0\n"
        "   integer, parameter, private :: PROGB_TRANSIENT = 1\n"
        "   integer, parameter, private :: PROGB_PSD_ACTIVE = 2\n"
        "   integer, parameter, private :: PROGB_UNSUPPORTED = 3\n",
        "status constants",
    )


def transform_outer(source: str) -> str:
    def add_outer_status(routine: str) -> str:
        return once(
            routine,
            "   real, dimension(its:ite,kts:kte) :: rhox\n",
            "   real, dimension(its:ite,kts:kte) :: rhox\n"
            "   integer, dimension(its:ite,kts:kte) :: progb_status\n",
            "outer status array",
        )
    source = in_subroutine(source, "kdm6", add_outer_status)
    source = once(
        source,
        "                ,graupel(ims,j),graupelncv(ims,j)          &\n"
        "                ,pr67_trace_this_call                         &\n",
        "                ,graupel(ims,j),graupelncv(ims,j)          &\n"
        "                ,pr67_trace_this_call                         &\n"
        "                ,progb_status                                 &\n",
        "KDM62D call",
    )
    source = once(
        source,
        "         diag_rhog(i,k,j) = rhox(i,k)\n",
        "         if (progb_status(i,k) == PROGB_PSD_ACTIVE) then\n"
        "           diag_rhog(i,k,j) = rhox(i,k)\n"
        "         else if (progb_status(i,k) == PROGB_ABSENT) then\n"
        "           diag_rhog(i,k,j) = 0.0\n"
        "         else\n"
        "           error stop 'KDM6 invalid ProgB status at return'\n"
        "         endif\n",
        "diagnostic density use",
    )
    source = once(
        source,
        "             cmg1d(k) = cmg(i,k)\n",
        "             if (progb_status(i,k) == PROGB_PSD_ACTIVE) then\n"
        "               cmg1d(k) = cmg(i,k)\n"
        "             else if (progb_status(i,k) == PROGB_ABSENT) then\n"
        "               cmg1d(k) = 0.0\n"
        "             else\n"
        "               error stop 'KDM6 invalid ProgB status at return'\n"
        "             endif\n",
        "diagnostic mass parameter use",
    )
    return source


def transform_kdm62d(source: str) -> str:
    source = once(
        source,
        "                   ,pr67_trace_this_call                            &\n"
        "                    )\n",
        "                   ,pr67_trace_this_call                            &\n"
        "                   ,progb_status                                    &\n"
        "                    )\n",
        "KDM62D status dummy",
    )
    def add_kdm62d_status(routine: str) -> str:
        return once(
            routine,
            "   real, dimension(its:ite,kts:kte)       , intent(out) :: rhox\n",
            "   real, dimension(its:ite,kts:kte)       , intent(out) :: rhox\n"
            "   integer, dimension(its:ite,kts:kte)   , intent(out) :: progb_status\n",
            "KDM62D status declaration",
        )
    source = in_subroutine(source, "kdm62d", add_kdm62d_status)
    source = once(
        source,
        "       rhox(i,k) = max(rhox(i,k),0.0)\n",
        "       ! ProgB supplies density only when its status is active.\n",
        "stale rhox read",
    )
    source = once(
        source,
        "         rhox(i,k) = max(rhox(i,k) ,0.)\n",
        "         ! The next ProgB call initializes density and status.\n",
        "pre-ProgB stale rhox read",
    )
    source = in_subroutine(source, "kdm62d", add_status_to_calls)
    # All seven callers immediately invoke slope_kdm6 with the same status.
    old = "                   ite,kts,kte,qmin,pidn0g,pvtg,bvtg,rslopegbmax)"
    if source.count(old) != CALL_COUNT:
        raise ValueError(f"expected {CALL_COUNT} slope call endings, found {source.count(old)}")
    source = source.replace(old, old.replace(")", ",progb_status)"))
    return source


def transform_progb(source: str) -> str:
    source = once(
        source,
        ",g1pbg,g3pbg,g4pbg,g5pbgo2,g1pdgbgmg,dgbgmug1)\n",
        ",g1pbg,g3pbg,g4pbg,g5pbgo2,g1pdgbgmg,dgbgmug1,progb_status)\n",
        "ProgB status dummy",
    )
    source = regex_once(
        source,
        r"^(\s*REAL, DIMENSION\( its:ite , kts:kte\),INTENT\(OUT\)\s*::\s*rhox\s*)$",
        r"\1\n  INTEGER, DIMENSION( its:ite , kts:kte),INTENT(OUT) :: progb_status",
        "ProgB status declaration",
    )
    source = once(source, "  REAL ::tmp1,tmp2\n", "  REAL ::tmp1,tmp2\n  DOUBLE PRECISION :: raw_density\n", "raw density local")
    source = once(
        source,
        "  implicit none\n  integer           :: i,k,sy, its,ite, jts,jte, kts,kte\n",
        "  use, intrinsic :: ieee_arithmetic, only : ieee_is_finite\n"
        "  implicit none\n  integer           :: i,k,sy, its,ite, jts,jte, kts,kte\n",
        "ProgB IEEE finite import",
    )
    start, end = bounds(source, "ProgB_param")
    routine = source[start:end]
    loop_start = routine.index("      do k = kts, kte")
    loop_end = routine.index("  END subroutine ProgB_param")
    formula_start = routine.index("         if (cmg(i,k).gt. 0) then", loop_start)
    formula_end = routine.index("       endif\n      enddo", formula_start)
    formula = routine[formula_start:formula_end] + "       endif\n"
    # The old outer density gate is removed; the new checks establish the
    # input contract before this table formula executes.
    loop = (
        "      do k = kts, kte\n"
        "        do i = its, ite\n"
        f"{output_zeroes()}\n"
        "          progb_status(i,k) = PROGB_UNSUPPORTED\n"
        "          if (.not. ieee_is_finite(qrs(i,k,3)) .or. &\n"
        "              .not. ieee_is_finite(brs(i,k))) cycle\n"
        "          if (qrs(i,k,3) == 0.0 .and. brs(i,k) == 0.0) then\n"
        "            progb_status(i,k) = PROGB_ABSENT\n"
        "            cycle\n"
        "          endif\n"
        "          if (qrs(i,k,3) <= 0.0 .or. brs(i,k) <= 0.0) cycle\n"
        "          if (qrs(i,k,3) <= qcrmin .and. brs(i,k) <= brs_min) then\n"
        "            progb_status(i,k) = PROGB_TRANSIENT\n"
        "            cycle\n"
        "          endif\n"
        "          raw_density = dble(qrs(i,k,3))/dble(brs(i,k))\n"
        "          if (.not. ieee_is_finite(raw_density)) cycle\n"
        "          if (raw_density < dble(rho_min) .or. &\n"
        "              raw_density > dble(rho_max)) cycle\n"
        "          rhox(i,k) = qrs(i,k,3)/brs(i,k)\n"
        "          cmg(i,k) = pi*rhox(i,k)/6\n"
        "          if (.not. ieee_is_finite(cmg(i,k)) .or. cmg(i,k) <= 0.0) cycle\n"
        "          pidn0g(i,k) = cmg(i,k)*n0g*g1pdgmg/g1pmg\n"
        f"{formula}"
        "          if (.not. ieee_is_finite(rhox(i,k)) .or. &\n"
        "              .not. ieee_is_finite(cmg(i,k)) .or. &\n"
        "              .not. ieee_is_finite(pidn0g(i,k)) .or. &\n"
        "              .not. ieee_is_finite(avtg(i,k)) .or. &\n"
        "              .not. ieee_is_finite(pvtg(i,k)) .or. &\n"
        "              .not. ieee_is_finite(precg2(i,k)) .or. &\n"
        "              .not. ieee_is_finite(bvtg(i,k)) .or. &\n"
        "              .not. ieee_is_finite(bvtg1(i,k)) .or. &\n"
        "              .not. ieee_is_finite(bvtg2(i,k)) .or. &\n"
        "              .not. ieee_is_finite(bvtg3(i,k)) .or. &\n"
        "              .not. ieee_is_finite(bvtg4(i,k)) .or. &\n"
        "              .not. ieee_is_finite(rslopegbmax(i,k)) .or. &\n"
        "              .not. ieee_is_finite(g1pbg(i,k)) .or. &\n"
        "              .not. ieee_is_finite(g3pbg(i,k)) .or. &\n"
        "              .not. ieee_is_finite(g4pbg(i,k)) .or. &\n"
        "              .not. ieee_is_finite(g5pbgo2(i,k)) .or. &\n"
        "              .not. ieee_is_finite(g1pdgbgmg(i,k)) .or. &\n"
        "              .not. ieee_is_finite(dgbgmug1(i,k))) then\n"
        f"{output_zeroes('            ')}\n"
        "            cycle\n"
        "          endif\n"
        "          brs(i,k) = qrs(i,k,3)/rhox(i,k)\n"
        "          progb_status(i,k) = PROGB_PSD_ACTIVE\n"
        "        enddo\n"
        "      enddo\n"
    )
    routine = routine[:loop_start] + loop + routine[loop_end:]
    return source[:start] + routine + source[end:]


def transform_slope(source: str) -> str:
    def add_slope_interface(routine: str) -> str:
        routine = once(
            routine,
            "pvtg,bvtg,rslopegbmax)\n",
            "pvtg,bvtg,rslopegbmax,progb_status)\n",
            "slope status dummy",
        )
        return once(
            routine,
            "  INTEGER       ::               its,ite, jts,jte, kts,kte\n",
            "  INTEGER       ::               its,ite, jts,jte, kts,kte\n"
            "  INTEGER, DIMENSION(its:ite,kts:kte), INTENT(IN) :: progb_status\n",
            "slope status declaration",
        )
    source = in_subroutine(source, "slope_kdm6", add_slope_interface)
    start, end = bounds(source, "slope_kdm6")
    routine = source[start:end]
    anchor = "      do k = kts, kte\n        do i = its, ite\n"
    if routine.count(anchor) != 1:
        raise ValueError("expected one slope cell loop")
    routine = routine.replace(
        anchor,
        anchor +
        "          if (progb_status(i,k) == PROGB_TRANSIENT) &\n"
        "            error stop 'ProgB transient PSD state rejected'\n"
        "          if (progb_status(i,k) == PROGB_UNSUPPORTED) &\n"
        "            error stop 'ProgB unsupported PSD state rejected'\n"
        "          if (progb_status(i,k) /= PROGB_ABSENT .and. &\n"
        "              progb_status(i,k) /= PROGB_PSD_ACTIVE) &\n"
        "            error stop 'ProgB invalid output status'\n",
        1,
    )
    old_start = routine.index("          if(qrs(i,k,3).le.qcrmin) then")
    old_end = routine.index("          vt(i,k,1) =", old_start)
    block = routine[old_start:old_end]
    prefix = "          if(qrs(i,k,3).le.qcrmin) then\n"
    if not block.startswith(prefix) or not block.rstrip().endswith("endif"):
        raise ValueError("unexpected graupel slope block")
    inside = block[len(prefix):].rstrip()
    inside = inside[:-len("endif")].rstrip()
    routine = routine[:old_start] + (
        "          if (progb_status(i,k) == PROGB_ABSENT) then\n"
        "            rslope(i,k,3) = 0.0\n"
        "            rslopeb(i,k,3) = 0.0\n"
        "            rslopemu(i,k,3) = 0.0\n"
        "            rsloped(i,k,3) = 0.0\n"
        "            rslope2(i,k,3) = 0.0\n"
        "            rslope3(i,k,3) = 0.0\n"
        "          else\n"
        "            if(qrs(i,k,3).le.qcrmin) then\n"
        + inside + "\n"
        "            endif\n"
        "          endif\n"
        + routine[old_end:]
    )
    routine = once(
        routine,
        "          vt(i,k,3) = DBLE(pvtg(i,k))*rslopeb(i,k,3)*denfac(i,k)\n",
        "          if (progb_status(i,k) == PROGB_PSD_ACTIVE) then\n"
        "            vt(i,k,3) = DBLE(pvtg(i,k))*rslopeb(i,k,3)*denfac(i,k)\n"
        "          else\n"
        "            vt(i,k,3) = 0.0\n"
        "          endif\n",
        "graupel velocity output read",
    )
    return source[:start] + routine + source[end:]


def transform_consumers(source: str) -> str:
    # These predicates directly protect every equation that reads the PSD
    # outputs avtg, g3pbg, or precg2.
    for old in (
        "if(qrs(i,k,3).gt.qcrmin .and. qci(i,k,1).gt.qmin) then",
        "if(qrs(i,k,3).gt.qcrmin .and. nci(i,k,1).gt.ncmin) then",
        "if(qrs(i,k,3).gt.0.) then",
        "if(qrs(i,k,3).gt.0. .and. ifsat.ne.1) then",
        "if(qrs(i,k,3).gt.0. .and. rh(i,k,1).lt.1.) then",
    ):
        if old not in source:
            raise ValueError(f"missing output-consumer guard: {old}")
        new = old.replace("if(", "if(progb_status(i,k)==PROGB_PSD_ACTIVE .and. ", 1)
        source = source.replace(old, new, 1)
    source = once(
        source,
        "          vt2g(i,k)=DBLE(pvtg(i,k))*rslopeb(i,k,3)*denfac(i,k)\n",
        "          if (progb_status(i,k) == PROGB_PSD_ACTIVE) then\n"
        "            vt2g(i,k)=DBLE(pvtg(i,k))*rslopeb(i,k,3)*denfac(i,k)\n"
        "          else\n"
        "            vt2g(i,k)=0.0\n"
        "          endif\n",
        "vt2g output read",
    )
    source = once(
        source,
        "              brs(i,k) = brs(i,k) + (pgmlt(i,k)/rhox(i,k))\n",
        "              if (progb_status(i,k) /= PROGB_PSD_ACTIVE) &\n"
        "                error stop 'ProgB status invalid for melting volume'\n"
        "              brs(i,k) = brs(i,k) + (pgmlt(i,k)/rhox(i,k))\n",
        "melting density read",
    )
    source = once(
        source,
        "            call kdm6_mass_volume_rate(pgdep(i,k),rhox(i,k), &\n"
        "                 rain_pgdep_bg_rate,rain_bg_rate_valid)\n",
        "            if (progb_status(i,k) == PROGB_PSD_ACTIVE) then\n"
        "              call kdm6_mass_volume_rate(pgdep(i,k),rhox(i,k), &\n"
        "                   rain_pgdep_bg_rate,rain_bg_rate_valid)\n"
        "            else if (progb_status(i,k) == PROGB_ABSENT .and. &\n"
        "                     pgdep(i,k) == 0.0) then\n"
        "              rain_pgdep_bg_rate = 0.0\n"
        "              rain_bg_rate_valid = .true.\n"
        "            else\n"
        "              rain_pgdep_bg_rate = 0.0\n"
        "              rain_bg_rate_valid = .false.\n"
        "            endif\n",
        "deposition density read",
    )
    source = once(
        source,
        "            bgevp(i,k)=pgevp(i,k)/rhox(i,k)\n"
        "            bgeml(i,k)=pgeml(i,k)/rhox(i,k)\n",
        "            if (progb_status(i,k) == PROGB_PSD_ACTIVE) then\n"
        "              bgevp(i,k)=pgevp(i,k)/rhox(i,k)\n"
        "              bgeml(i,k)=pgeml(i,k)/rhox(i,k)\n"
        "            else if (progb_status(i,k) == PROGB_ABSENT .and. &\n"
        "                     pgevp(i,k) == 0.0 .and. pgeml(i,k) == 0.0) then\n"
        "              bgevp(i,k)=0.0\n"
        "              bgeml(i,k)=0.0\n"
        "            else\n"
        "              error stop 'ProgB status invalid for volume conversion'\n"
        "            endif\n",
        "evaporation density reads",
    )
    source = in_subroutine(source, "kdm62d", lambda routine: once(
        routine,
        "           if(qrs(i,k,3).le.qcrmin)then\n"
        "              qrs(i,k,3) = 0.0\n"
        "              brs(i,k) = 0.0\n",
        "           if(qrs(i,k,3).le.qcrmin)then\n"
        "              qrs(i,k,3) = 0.0\n"
        "              brs(i,k) = 0.0\n"
        "              progb_status(i,k) = PROGB_ABSENT\n"
        "              n0go(i,k) = 0.0\n"
        f"{output_zeroes('              ')}\n",
        "terminal graupel cleanup",
    ))
    source = once(
        source,
        "                   ' BGinput/massRates/rho=',brs(i,k),pgdep(i,k),rhox(i,k), &\n",
        "                   ' BGinput/massRates/rho_status=',brs(i,k),pgdep(i,k), &\n"
        "                   progb_status(i,k), &\n",
        "rejection diagnostic density read",
    )
    source = in_subroutine(source, "kdm62d", lambda routine: re.sub(
        r"(?im)^(\s*)if\s*\(\s*qrs\(i,k,3\)\s*\.gt\.",
        lambda match: match.group(1) + "if (progb_status(i,k) == PROGB_PSD_ACTIVE .and. qrs(i,k,3) .gt.",
        routine,
    ))
    def guard_n0go(routine: str) -> str:
        pattern = r"(?im)^(\s*)n0go\(i,k\)\s*=\s*\(n0g\)/g1pmg/\(rslopemu\(i,k,3\)\)\s*$"
        replacement = (
            r"\1if (progb_status(i,k) == PROGB_PSD_ACTIVE) then\n"
            r"\1  n0go(i,k) = (n0g)/g1pmg/(rslopemu(i,k,3))\n"
            r"\1else\n"
            r"\1  n0go(i,k) = 0.0\n"
            r"\1endif"
        )
        updated, count = re.subn(pattern, replacement, routine)
        if count != 2:
            raise ValueError(f"expected both n0go property reads, found {count}")
        return updated
    source = in_subroutine(source, "kdm62d", guard_n0go)
    if source.count("n0go(i,k) = (n0g)/g1pmg/(rslopemu(i,k,3))") != 2:
        raise ValueError("expected both graupel intercept calculations")
    return source


def transform_observer_output(source: str) -> str:
    """Serialize the current named ice mass-velocity rate in stage zero."""
    old = "        write(pr67_unit) work1(its:ite,kts:kte,4)\n"
    new = "        write(pr67_unit) mass_velocity_rate(its:ite,kts:kte,4)\n"
    return once(source, old, new, "stage-0 ice mass-velocity observer field")


def transform(source: str) -> str:
    for action in (transform_module, transform_outer, transform_kdm62d,
                   transform_progb, transform_slope, transform_consumers,
                   transform_observer_output):
        source = action(source)
    if source.count(",dgbgmug1,progb_status)") != CALL_COUNT + 1:
        raise ValueError("not all ProgB calls receive status")
    if source.count("rslopegbmax,progb_status)") != CALL_COUNT + 1:
        raise ValueError("not all slope calls receive status")
    return source


def output_use_inventory(source: str) -> dict[str, list[dict[str, object]]]:
    """List every declaration, assignment, call argument, and read per output."""
    progb_start, progb_end = bounds(source, "ProgB_param")
    slope_start, slope_end = bounds(source, "slope_kdm6")
    records: dict[str, list[dict[str, object]]] = {name: [] for name in OUTPUTS}
    offset = 0
    for line_number, line in enumerate(source.splitlines(keepends=True), 1):
        code = line.split("!", 1)[0]
        lower = code.lower()
        for name in OUTPUTS:
            if not re.search(rf"\b{re.escape(name)}\b", lower):
                continue
            if "intent(out)" in lower or "subroutine progb_param" in lower:
                kind = "declaration_or_interface"
            elif progb_start <= offset < progb_end and "ieee_is_finite" in lower:
                kind = "finite_output_validation"
            elif progb_start <= offset < progb_end and re.search(
                rf"\b{re.escape(name)}\s*\([^)]*\)\s*=", lower
            ):
                kind = "output_assignment"
            elif progb_start <= offset < progb_end:
                kind = "producer_expression"
            elif "call progb_param" in lower:
                kind = "output_actual_argument"
            elif "call slope_kdm6" in lower:
                kind = "status_checked_slope_argument"
            elif slope_start <= offset < slope_end:
                kind = "slope_consumer_status_checked_before_use"
            elif re.search(rf"\b{re.escape(name)}\s*\([^)]*\)\s*=", lower):
                kind = "assignment"
            else:
                kind = "consumer_read_status_gated"
            records[name].append({"line": line_number, "kind": kind, "source": line.strip()})
        offset += len(line)
    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("patch", type=Path)
    parser.add_argument("--inventory-out", type=Path)
    parser.add_argument("--expected-source-sha256", default=SOURCE_SHA256)
    args = parser.parse_args()
    raw = args.source.read_bytes()
    source_hash = digest(raw)
    if source_hash != args.expected_source_sha256:
        raise SystemExit(f"source SHA-256 mismatch: {source_hash}")
    updated = transform(raw.decode("utf-8")).encode("utf-8")
    patch = "".join(difflib.unified_diff(
        raw.decode("utf-8").splitlines(keepends=True),
        updated.decode("utf-8").splitlines(keepends=True),
        fromfile=args.source.name, tofile=args.source.name,
    )).encode("utf-8")
    args.patch.parent.mkdir(parents=True, exist_ok=True)
    if args.patch.exists():
        if args.patch.read_bytes() != patch:
            raise SystemExit(f"refusing to overwrite different patch: {args.patch}")
    else:
        with args.patch.open("xb") as stream:
            stream.write(patch)
    inventory_path = args.inventory_out or args.patch.with_suffix(".output_inventory.json")
    source_text = updated.decode("utf-8")
    lines = source_text.splitlines()
    receipt = {
        "source_sha256": source_hash,
        "patched_source_sha256": digest(updated),
        "patch_sha256": digest(patch),
        "call_sites": {
            "ProgB_param": [i for i, line in enumerate(lines, 1) if re.search(r"\bcall\s+ProgB_param\s*\(", line, re.I)],
            "slope_kdm6": [i for i, line in enumerate(lines, 1) if re.search(r"\bcall\s+slope_kdm6\s*\(", line, re.I)],
        },
        "outputs": output_use_inventory(source_text),
    }
    inventory_bytes = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode("utf-8")
    inventory_path.parent.mkdir(parents=True, exist_ok=True)
    if inventory_path.exists():
        if inventory_path.read_bytes() != inventory_bytes:
            raise SystemExit(f"refusing to overwrite different inventory: {inventory_path}")
    else:
        with inventory_path.open("xb") as stream:
            stream.write(inventory_bytes)
    print(f"SOURCE_SHA256 {source_hash}")
    print(f"PATCH_SHA256 {digest(patch)}")
    print(f"PATCHED_SOURCE_SHA256 {digest(updated)}")
    print(f"INVENTORY_SHA256 {digest(inventory_bytes)}")
    print(f"PATCH_BYTES {len(patch)}")


if __name__ == "__main__":
    main()
