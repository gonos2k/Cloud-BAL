"""Add failure-only call-site context to pinned KDM6 ProgB sources."""

from __future__ import annotations

import hashlib


V31_KDM6_SHA256 = "9cb8d19bf676771e5bfd717d07cdaf43b4bc63912b0b7869b977fbd0f2ac1397"
V36_KDM6_SHA256 = "1418f37ec081fe28aff6f72f23c79699f7e57711ed288e6e94beff12557d7f5e"
_CALL = "   call ProgB_param(brs,qrs_tmp,rhox,its,ite,jts,jte,kts,kte,qcrmin"
_CALL_END = (
    "                   ,g1pbg,g3pbg,g4pbg,g5pbgo2,g1pdgbgmg,dgbgmug1,progb_status)"
)
_TRANSIENT = "            progb_status(i,k) = PROGB_TRANSIENT\n            cycle"


def add_progb_failure_context(source: str) -> str:
    """Add the pinned V31 transient or V36 unsupported-status diagnostic."""
    actual_hash = hashlib.sha256(source.encode()).hexdigest()
    if actual_hash == V31_KDM6_SHA256:
        return _add_v31_failure_context(source)
    if actual_hash == V36_KDM6_SHA256:
        return _add_v36_failure_context(source)
    raise ValueError(f"unexpected ProgB KDM6 source hash: {actual_hash}")


def _add_v31_failure_context(source: str) -> str:
    """Preserve the original V31 transient-only context transform."""

    calls = source.count(_CALL)
    if calls != 7:
        raise ValueError(f"expected 7 ProgB call sites, found {calls}")
    call_number = 0
    pieces: list[str] = []
    cursor = 0
    while True:
        start = source.find(_CALL, cursor)
        if start < 0:
            pieces.append(source[cursor:])
            break
        end = source.find("\n", start)
        if end < 0:
            raise ValueError("unterminated ProgB call anchor")
        # The actual call spans several continuation lines. Locate its final actual.
        call_end = source.find(_CALL_END, end)
        if call_end < 0:
            raise ValueError("ProgB call final-argument anchor missing")
        call_end += len(_CALL_END)
        call_number += 1
        pieces.append(source[cursor:call_end - len(")")])
        pieces.append(f",source_context={call_number},source_lat=lat)")
        cursor = call_end
    if call_number != 7:
        raise ValueError(f"expected to annotate 7 calls, annotated {call_number}")
    source = "".join(pieces)

    old_signature = (
        "                         ,g1pbg,g3pbg,g4pbg,g5pbgo2,g1pdgbgmg,dgbgmug1,progb_status)"
    )
    new_signature = (
        "                         ,g1pbg,g3pbg,g4pbg,g5pbgo2,g1pdgbgmg,dgbgmug1,progb_status &\n"
        "                         ,source_context,source_lat)"
    )
    if source.count(old_signature) != 1:
        raise ValueError("ProgB private signature anchor missing or ambiguous")
    source = source.replace(old_signature, new_signature, 1)

    routine_start = source.index("   SUBROUTINE ProgB_param(")
    routine_end = source.index("  END subroutine ProgB_param", routine_start)
    routine = source[routine_start:routine_end]

    declarations = "  INTEGER, DIMENSION( its:ite , kts:kte),INTENT(OUT) :: progb_status\n"
    declarations_new = declarations + (
        "  integer, optional, intent(in) :: source_context, source_lat\n"
        "  integer :: pr87_context, pr87_lat\n"
        "  logical :: pr87_transient_logged\n"
    )
    if routine.count(declarations) != 1:
        raise ValueError("ProgB declaration anchor missing or ambiguous")
    routine = routine.replace(declarations, declarations_new, 1)

    init_anchor = "      do k = kts, kte\n        do i = its, ite\n"
    init_new = (
        "      pr87_context = 0\n"
        "      pr87_lat = 0\n"
        "      if (present(source_context)) pr87_context = source_context\n"
        "      if (present(source_lat)) pr87_lat = source_lat\n"
        "      pr87_transient_logged = .false.\n"
        + init_anchor
    )
    if routine.count(init_anchor) != 1:
        raise ValueError("ProgB loop initialization anchor missing or ambiguous")
    routine = routine.replace(init_anchor, init_new, 1)

    transient_new = (
        "            progb_status(i,k) = PROGB_TRANSIENT\n"
        "            if (present(source_context) .and. present(source_lat) .and. &\n"
        "                .not.pr87_transient_logged) then\n"
        "              write(*,'(A,4(1X,I0),3(1X,ES24.16E3),2(1X,Z8.8))') &\n"
        "                'PR87_PROGB_TRANSIENT',pr87_context,pr87_lat,i,k, &\n"
        "                dble(qrs(i,k,3)),dble(brs(i,k)), &\n"
        "                dble(qrs(i,k,3))/dble(brs(i,k)), &\n"
        "                transfer(qrs(i,k,3),0),transfer(brs(i,k),0)\n"
        "              flush(6)\n"
        "              pr87_transient_logged = .true.\n"
        "            endif\n"
        "            cycle"
    )
    if routine.count(_TRANSIENT) != 1:
        raise ValueError("ProgB transient branch anchor missing or ambiguous")
    routine = routine.replace(_TRANSIENT, transient_new, 1)
    source = source[:routine_start] + routine + source[routine_end:]
    return source


def _add_v36_failure_context(source: str) -> str:
    """Report the first unsupported cell for each annotated ProgB call."""
    calls = source.count(_CALL)
    if calls != 7:
        raise ValueError(f"expected 7 V36 ProgB call sites, found {calls}")
    call_number = 0
    pieces: list[str] = []
    cursor = 0
    while True:
        start = source.find(_CALL, cursor)
        if start < 0:
            pieces.append(source[cursor:])
            break
        end = source.find("\n", start)
        if end < 0:
            raise ValueError("unterminated V36 ProgB call anchor")
        call_end = source.find(_CALL_END, end)
        if call_end < 0:
            raise ValueError("V36 ProgB call final-argument anchor missing")
        call_end += len(_CALL_END)
        call_number += 1
        pieces.append(source[cursor:call_end - len(")")])
        pieces.append(f",source_context={call_number},source_lat=lat)")
        cursor = call_end
    if call_number != 7:
        raise ValueError(f"expected to annotate 7 V36 calls, annotated {call_number}")
    source = "".join(pieces)

    old_signature = (
        "                         ,g1pbg,g3pbg,g4pbg,g5pbgo2,g1pdgbgmg,dgbgmug1,progb_status)"
    )
    new_signature = (
        "                         ,g1pbg,g3pbg,g4pbg,g5pbgo2,g1pdgbgmg,dgbgmug1,progb_status &\n"
        "                         ,source_context,source_lat)"
    )
    if source.count(old_signature) != 1:
        raise ValueError("V36 ProgB private signature anchor missing or ambiguous")
    source = source.replace(old_signature, new_signature, 1)

    routine_start = source.index("   SUBROUTINE ProgB_param(")
    routine_end = source.index("  END subroutine ProgB_param", routine_start)
    routine = source[routine_start:routine_end]
    declaration = "  INTEGER, DIMENSION( its:ite , kts:kte),INTENT(OUT) :: progb_status\n"
    declaration_new = declaration + (
        "  integer, optional, intent(in) :: source_context, source_lat\n"
        "  integer :: pr87_context, pr87_lat\n"
        "  logical :: pr87_unsupported_logged, pr87_ratio_valid\n"
        "  real(kind=8) :: pr87_ratio\n"
        "  real :: pr87_bg_before\n"
        "  logical :: pr87_postbg_logged\n"
    )
    if routine.count(declaration) != 1:
        raise ValueError("V36 ProgB declaration anchor missing or ambiguous")
    routine = routine.replace(declaration, declaration_new, 1)

    loop_anchor = "      do k = kts, kte\n        do i = its, ite\n"
    loop_new = (
        "      pr87_context=0; pr87_lat=0\n"
        "      if (present(source_context)) pr87_context=source_context\n"
        "      if (present(source_lat)) pr87_lat=source_lat\n"
        "      pr87_unsupported_logged=.false.\n"
        "      pr87_postbg_logged=.false.\n"
        + loop_anchor
    )
    if routine.count(loop_anchor) != 1:
        raise ValueError("V36 ProgB loop initialization anchor missing or ambiguous")
    routine = routine.replace(loop_anchor, loop_new, 1)

    report = """          if (present(source_context) .and. present(source_lat) .and. &
              .not.pr87_unsupported_logged) then
            pr87_ratio=0.0d0
            pr87_ratio_valid=.false.
            if (ieee_is_finite(qrs(i,k,3))) then
              if (ieee_is_finite(brs(i,k))) then
                if (brs(i,k).gt.0.0) then
                  pr87_ratio=dble(qrs(i,k,3))/dble(brs(i,k))
                  pr87_ratio_valid=ieee_is_finite(pr87_ratio)
                endif
              endif
            endif
            write(*,'(A,6(1X,I0),3(1X,ES24.16E3),2(1X,Z8.8))') &
                 'PR87_PROGB_UNSUPPORTED',pr87_context,pr87_lat,i,k, &
                 progb_status(i,k),merge(1,0,pr87_ratio_valid), &
                 dble(qrs(i,k,3)),dble(brs(i,k)),pr87_ratio, &
                 transfer(qrs(i,k,3),0),transfer(brs(i,k),0)
            flush(6)
            pr87_unsupported_logged=.true.
          endif
"""

    unsupported_cycle_anchors = [
        "          if (.not. ieee_is_finite(qrs(i,k,3)) .or. &\n"
        "              .not. ieee_is_finite(brs(i,k))) cycle\n",
        "          if (qrs(i,k,3) <= 0.0 .or. brs(i,k) <= 0.0) cycle\n",
        "          if (.not. ieee_is_finite(raw_density)) cycle\n",
        "          if (raw_density < dble(rho_min) .or. &\n"
        "              raw_density > dble(rho_max)) cycle\n",
        "          if (.not. ieee_is_finite(cmg(i,k)) .or. cmg(i,k) <= 0.0) cycle\n",
        "            dgbgmug1(i,k) = 0.0\n            cycle\n          endif\n",
    ]
    for index, anchor in enumerate(unsupported_cycle_anchors):
        if routine.count(anchor) != 1:
            raise ValueError(f"V36 unsupported ProgB cycle anchor {index + 1} missing or ambiguous")
        if index < 5:
            replacement = anchor.replace(
                " cycle\n", " then\n" + report + "            cycle\n          endif\n", 1
            )
        else:
            # Final derived-coefficient failure resets local outputs before cycling.
            replacement = anchor.replace(
                "            cycle\n", report + "            cycle\n", 1
            )
        routine = routine.replace(anchor, replacement, 1)

    source = source[:routine_start] + routine + source[routine_end:]
    old_rewrite = "          brs(i,k) = qrs(i,k,3)/rhox(i,k)\n"
    new_rewrite = """          pr87_bg_before=brs(i,k)
          brs(i,k) = qrs(i,k,3)/rhox(i,k)
          if (present(source_context) .and. present(source_lat) .and. &
              .not.pr87_postbg_logged) then
            if (ieee_is_finite(qrs(i,k,3))) then
              if (ieee_is_finite(brs(i,k))) then
                if (qrs(i,k,3).gt.0.0 .and. brs(i,k).gt.0.0) then
                  pr87_ratio=dble(qrs(i,k,3))/dble(brs(i,k))
                  if (ieee_is_finite(pr87_ratio)) then
                    if (pr87_ratio.lt.dble(rho_min) .or. pr87_ratio.gt.dble(rho_max)) then
                      write(*,'(A,5(1X,I0),5(1X,ES24.16E3),3(1X,Z8.8))') &
                           'PR87_PROGB_POST_BG_RATIO',pr87_context,pr87_lat,i,k,1, &
                           dble(qrs(i,k,3)),dble(pr87_bg_before),dble(brs(i,k)), &
                           pr87_ratio,dble(rhox(i,k)),transfer(qrs(i,k,3),0), &
                           transfer(pr87_bg_before,0),transfer(brs(i,k),0)
                      flush(6)
                      pr87_postbg_logged=.true.
                    endif
                  endif
                endif
              endif
            endif
          endif
"""
    if source.count(old_rewrite) != 1:
        raise ValueError("V36 ProgB graupel B rewrite anchor missing or ambiguous")
    source = source.replace(old_rewrite, new_rewrite, 1)
    return source
