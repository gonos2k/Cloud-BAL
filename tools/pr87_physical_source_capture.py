"""Generate a narrow overlay that captures the unweighted physics source.

The overlay clones the source tree's ``update_phy_ten`` call before
``calculate_phy_tend`` applies hybrid-mass weighting, then records the actual
coupled tendencies immediately after the original update call.  It returns
modified source strings and does not write files.
"""

from __future__ import annotations

import re


_OUTPUTS = (
    "pr87_raw_qsrc",
    "pr87_raw_nsrc",
    "pr87_coupled_qsrc",
    "pr87_coupled_nsrc",
    "pr87_source_carrier",
    "pr87_source_step",
    "pr87_later_qsrc",
    "pr87_later_nsrc",
)


def _call_span(source: str, name: str, start: int = 0) -> tuple[int, int, str]:
    """Return a balanced Fortran CALL statement, including its arguments."""
    marker = f"CALL {name}"
    call_start = source.find(marker, start)
    if call_start < 0:
        raise ValueError(f"missing {marker}")
    open_paren = source.find("(", call_start + len(marker))
    if open_paren < 0:
        raise ValueError(f"missing argument list for {marker}")
    depth = 0
    quote: str | None = None
    index = open_paren
    while index < len(source):
        char = source[index]
        if quote:
            if char == quote:
                if index + 1 < len(source) and source[index + 1] == quote:
                    index += 1
                else:
                    quote = None
        elif char in "'\"":
            quote = char
        elif char == "!":
            newline = source.find("\n", index)
            if newline < 0:
                raise ValueError(f"unterminated comment in {marker}")
            index = newline
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return call_start, index + 1, source[call_start : index + 1]
        index += 1
    raise ValueError(f"unterminated argument list for {marker}")


def _unique_replace(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise ValueError(f"expected one {label} anchor, found {count}")
    return source.replace(old, new, 1)


def _require_single_call(source: str, name: str) -> None:
    count = source.count(f"CALL {name}")
    if count != 1:
        raise ValueError(f"expected one CALL {name}, found {count}")


def _instrument_part2(source: str) -> str:
    _require_single_call(source, "calculate_phy_tend")
    _require_single_call(source, "update_phy_ten")
    signature_tail = ", k_start , k_end                  &\n                            )"
    signature_args = (
        ", k_start , k_end                                      &\n"
        "                             , pr87_raw_qsrc, pr87_raw_nsrc             &\n"
        "                             , pr87_coupled_qsrc, pr87_coupled_nsrc     &\n"
        "                             , pr87_source_carrier, pr87_source_step    &\n"
        "                            )"
    )
    source = _unique_replace(source, signature_tail, signature_args, "part2 signature")

    declaration_anchor = "    INTEGER , INTENT(IN)                          ::  k_start, k_end\n"
    declarations = declaration_anchor + (
        "    REAL, INTENT(OUT) :: pr87_raw_qsrc(ims:ime,kms:kme,jms:jme,2)\n"
        "    REAL, INTENT(OUT) :: pr87_raw_nsrc(ims:ime,kms:kme,jms:jme,2)\n"
        "    REAL, INTENT(OUT) :: pr87_coupled_qsrc(ims:ime,kms:kme,jms:jme,2)\n"
        "    REAL, INTENT(OUT) :: pr87_coupled_nsrc(ims:ime,kms:kme,jms:jme,2)\n"
        "    REAL, INTENT(OUT) :: pr87_source_carrier(ims:ime,kms:kme,jms:jme)\n"
        "    INTEGER, INTENT(OUT) :: pr87_source_step\n"
    )
    source = _unique_replace(source, declaration_anchor, declarations, "part2 declarations")

    local_anchor = "    INTEGER                             :: ij\n"
    local_declarations = local_anchor + (
        "    REAL, ALLOCATABLE :: pr87_shadow_ph(:,:,:), pr87_shadow_t(:,:,:)\n"
        "    REAL, ALLOCATABLE :: pr87_shadow_ru(:,:,:), pr87_shadow_rv(:,:,:)\n"
        "    REAL, ALLOCATABLE :: pr87_shadow_mu(:,:), pr87_shadow_moist(:,:,:,:)\n"
        "    REAL, ALLOCATABLE :: pr87_shadow_scalar(:,:,:,:)\n"
        "    INTEGER :: pr87_i, pr87_j, pr87_k\n"
    )
    source = _unique_replace(source, local_anchor, local_declarations, "part2 locals")

    start_anchor = "   rk_step = 1\n"
    initialize = start_anchor + (
        "   pr87_raw_qsrc = 0.0\n"
        "   pr87_raw_nsrc = 0.0\n"
        "   pr87_coupled_qsrc = 0.0\n"
        "   pr87_coupled_nsrc = 0.0\n"
        "   pr87_source_carrier = 0.0\n"
        "   pr87_source_step = -1\n"
    )
    source = _unique_replace(source, start_anchor, initialize, "part2 initialization")

    calc_start, calc_end, _ = _call_span(source, "calculate_phy_tend")
    call_start, call_end, actual_call = _call_span(source, "update_phy_ten", calc_end)
    shadow_outputs = (
        "pr87_shadow_ph",
        "pr87_shadow_t",
        "pr87_shadow_ru",
        "pr87_shadow_rv",
        "pr87_shadow_moist",
        "pr87_shadow_scalar",
        "pr87_shadow_mu",
    )
    actual_outputs = (
        "ph_tendf",
        "t_tendf",
        "ru_tendf",
        "rv_tendf",
        "moist_tend",
        "scalar_tend",
        "mu_tendf",
    )
    cloned_call = actual_call
    for actual, shadow in zip(actual_outputs, shadow_outputs, strict=True):
        cloned_call = re.sub(rf"\b{actual}\b", shadow, cloned_call, count=1)
    clone = (
        "        IF (config_flags%mp_physics == 37 .AND. grid%num_tiles == 1) THEN\n"
        "        pr87_shadow_ph = ph_tendf\n"
        "        pr87_shadow_t = t_tendf\n"
        "        pr87_shadow_ru = ru_tendf\n"
        "        pr87_shadow_rv = rv_tendf\n"
        "        pr87_shadow_moist = moist_tend\n"
        "        pr87_shadow_scalar = scalar_tend\n"
        "        pr87_shadow_mu = mu_tendf\n"
        f"        {cloned_call}\n"
        "        DO pr87_j = grid%j_start(ij), grid%j_end(ij)\n"
        "          DO pr87_k = k_start, MIN(k_end,kde-1)\n"
        "            DO pr87_i = grid%i_start(ij), grid%i_end(ij)\n"
        "              pr87_raw_qsrc(pr87_i,pr87_k,pr87_j,1) = &\n"
        "                   pr87_shadow_moist(pr87_i,pr87_k,pr87_j,P_QC)\n"
        "              pr87_raw_qsrc(pr87_i,pr87_k,pr87_j,2) = &\n"
        "                   pr87_shadow_moist(pr87_i,pr87_k,pr87_j,P_QI)\n"
        "              pr87_raw_nsrc(pr87_i,pr87_k,pr87_j,1) = &\n"
        "                   pr87_shadow_scalar(pr87_i,pr87_k,pr87_j,P_QNC)\n"
        "              pr87_raw_nsrc(pr87_i,pr87_k,pr87_j,2) = &\n"
        "                   pr87_shadow_scalar(pr87_i,pr87_k,pr87_j,P_QNI)\n"
        "              pr87_source_carrier(pr87_i,pr87_k,pr87_j) = &\n"
        "                   grid%c1h(pr87_k)*grid%mut(pr87_i,pr87_j) + grid%c2h(pr87_k)\n"
        "            END DO\n"
        "          END DO\n"
        "        END DO\n"
        "        END IF\n"
    )
    # Capture the same helper inputs before calculate_phy_tend mutates the
    # process-rate arrays with hybrid-mass weighting.
    source = source[:calc_start] + clone + source[calc_start:]

    alloc_anchor = "BENCH_START(cal_phy_tend)\n"
    allocation = (
        "IF (config_flags%mp_physics == 37 .AND. grid%num_tiles == 1) THEN\n"
        "ALLOCATE(pr87_shadow_ph(ims:ime,kms:kme,jms:jme), &\n"
        "         pr87_shadow_t(ims:ime,kms:kme,jms:jme), &\n"
        "         pr87_shadow_ru(ims:ime,kms:kme,jms:jme), &\n"
        "         pr87_shadow_rv(ims:ime,kms:kme,jms:jme), &\n"
        "         pr87_shadow_mu(ims:ime,jms:jme), &\n"
        "         pr87_shadow_moist(ims:ime,kms:kme,jms:jme,num_moist), &\n"
        "         pr87_shadow_scalar(ims:ime,kms:kme,jms:jme,num_scalar))\n"
        "END IF\n"
        + alloc_anchor
    )
    source = _unique_replace(source, alloc_anchor, allocation, "pre-calculate allocation")

    # The update call found above is the original physical call. Capture its
    # exact result immediately after it, while retaining the original call.
    _, final_calc_end, _ = _call_span(source, "calculate_phy_tend")
    _, call_end, _ = _call_span(source, "update_phy_ten", final_calc_end)
    capture = (
        "         IF (config_flags%mp_physics == 37 .AND. grid%num_tiles == 1) THEN\n"
        "           pr87_coupled_qsrc(:,:,:,1) = moist_tend(:,:,:,P_QC)\n"
        "           pr87_coupled_qsrc(:,:,:,2) = moist_tend(:,:,:,P_QI)\n"
        "           pr87_coupled_nsrc(:,:,:,1) = scalar_tend(:,:,:,P_QNC)\n"
        "           pr87_coupled_nsrc(:,:,:,2) = scalar_tend(:,:,:,P_QNI)\n"
        "           pr87_source_step = grid%itimestep\n"
        "         END IF\n"
    )
    source = source[:call_end] + "\n" + capture + source[call_end:]

    close_anchor = "       !$OMP END PARALLEL DO\nBENCH_END(update_phy_ten_tim)\n"
    source = _unique_replace(
        source,
        close_anchor,
        close_anchor + "IF (config_flags%mp_physics == 37 .AND. grid%num_tiles == 1) THEN\n"
        "DEALLOCATE(pr87_shadow_ph,pr87_shadow_t,pr87_shadow_ru, &\n"
        "           pr87_shadow_rv,pr87_shadow_mu,pr87_shadow_moist,pr87_shadow_scalar)\n"
        "END IF\n",
        "post-update deallocation",
    )

    end_anchor = "  END SUBROUTINE first_rk_step_part2"
    assertion = (
        "  IF (pr87_source_step >= 0) THEN\n"
        "    DO pr87_j = MAX(jds+1,grid%j_start(1)), MIN(jde-2,grid%j_end(1))\n"
        "      DO pr87_k = k_start, MIN(k_end,kde-1)\n"
        "        DO pr87_i = MAX(ids+1,grid%i_start(1)), MIN(ide-2,grid%i_end(1))\n"
        "          IF (pr87_coupled_qsrc(pr87_i,pr87_k,pr87_j,1) /= &\n"
        "              moist_tend(pr87_i,pr87_k,pr87_j,P_QC) .OR. &\n"
        "              pr87_coupled_qsrc(pr87_i,pr87_k,pr87_j,2) /= &\n"
        "              moist_tend(pr87_i,pr87_k,pr87_j,P_QI) .OR. &\n"
        "              pr87_coupled_nsrc(pr87_i,pr87_k,pr87_j,1) /= &\n"
        "              scalar_tend(pr87_i,pr87_k,pr87_j,P_QNC) .OR. &\n"
        "              pr87_coupled_nsrc(pr87_i,pr87_k,pr87_j,2) /= &\n"
        "              scalar_tend(pr87_i,pr87_k,pr87_j,P_QNI)) THEN\n"
        "            pr87_source_step = -1\n"
        "          END IF\n"
        "        END DO\n"
        "      END DO\n"
        "    END DO\n"
        "  END IF\n\n"
    )
    source = _unique_replace(source, end_anchor, assertion + end_anchor, "part2 final assertion")
    return source


def _instrument_solve(source: str) -> str:
    _require_single_call(source, "first_rk_step_part2")
    _require_single_call(source, "rk_update_joint_moments")
    implicit_anchor = "   IMPLICIT NONE\n"
    if implicit_anchor not in source:
        raise ValueError("missing solve IMPLICIT NONE anchor")
    if "USE, INTRINSIC :: iso_fortran_env, ONLY: real64" not in source:
        source = source.replace(
            implicit_anchor,
            "   USE, INTRINSIC :: iso_fortran_env, ONLY: real64\n" + implicit_anchor,
            1,
        )
    local_anchor = "   INTEGER                         :: ij , iteration\n"
    declarations = local_anchor + (
        "   REAL, ALLOCATABLE :: pr87_raw_qsrc(:,:,:,:), pr87_raw_nsrc(:,:,:,:)\n"
        "   REAL, ALLOCATABLE :: pr87_coupled_qsrc(:,:,:,:), pr87_coupled_nsrc(:,:,:,:)\n"
        "   REAL, ALLOCATABLE :: pr87_source_carrier(:,:,:)\n"
        "   REAL(real64), ALLOCATABLE :: pr87_later_qsrc(:,:,:,:), pr87_later_nsrc(:,:,:,:)\n"
        "   INTEGER :: pr87_source_step\n"
    )
    source = _unique_replace(source, local_anchor, declarations, "solve declarations")

    part2_start, part2_end, part2_call = _call_span(source, "first_rk_step_part2")
    if part2_call.rstrip().endswith(")"):
        part2_call_new = part2_call[:-1] + (
            "                             , pr87_raw_qsrc, pr87_raw_nsrc             &\n"
            "                             , pr87_coupled_qsrc, pr87_coupled_nsrc     &\n"
            "                             , pr87_source_carrier, pr87_source_step    )"
        )
    else:
        raise ValueError("unexpected part2 call terminator")
    source = source[:part2_start] + part2_call_new + source[part2_end:]

    # Allocate the handoff once before the source-capturing call; these local
    # arrays remain available to the later RK consumer in this solve invocation.
    source = source[:part2_start] + (
        "       IF (.NOT.ALLOCATED(pr87_raw_qsrc)) THEN\n"
        "         ALLOCATE(pr87_raw_qsrc(ims:ime,kms:kme,jms:jme,2), &\n"
        "                  pr87_raw_nsrc(ims:ime,kms:kme,jms:jme,2), &\n"
        "                  pr87_coupled_qsrc(ims:ime,kms:kme,jms:jme,2), &\n"
        "                  pr87_coupled_nsrc(ims:ime,kms:kme,jms:jme,2), &\n"
        "                  pr87_source_carrier(ims:ime,kms:kme,jms:jme), &\n"
        "                  pr87_later_qsrc(ims:ime,kms:kme,jms:jme,2), &\n"
        "                  pr87_later_nsrc(ims:ime,kms:kme,jms:jme,2))\n"
        "         pr87_later_qsrc = 0.0_real64\n"
        "         pr87_later_nsrc = 0.0_real64\n"
        "       END IF\n"
    ) + source[part2_start:]

    joint_start, joint_end, joint_call = _call_span(source, "rk_update_joint_moments")
    handoff = (
        "         IF (rk_step == 1) THEN\n"
        "           IF (pr87_source_step /= grid%itimestep) THEN\n"
        "             CALL wrf_error_fatal('PR87 source capture timestep mismatch')\n"
        "           END IF\n"
        "           ! Carry post-capture horizontal diffusion, optional diabatic, and boundary additions.\n"
        "           DO j = MAX(jds+1,grid%j_start(ij)), MIN(jde-2,grid%j_end(ij))\n"
        "             DO k = k_start, MIN(k_end,kde-1)\n"
        "               DO i = MAX(ids+1,grid%i_start(ij)), MIN(ide-2,grid%i_end(ij))\n"
        "                 pr87_later_qsrc(i,k,j,1) = &\n"
        "                      REAL(moist_tend(i,k,j,P_QC),real64) - &\n"
        "                      REAL(pr87_coupled_qsrc(i,k,j,1),real64)\n"
        "                 pr87_later_qsrc(i,k,j,2) = &\n"
        "                      REAL(moist_tend(i,k,j,P_QI),real64) - &\n"
        "                      REAL(pr87_coupled_qsrc(i,k,j,2),real64)\n"
        "                 pr87_later_nsrc(i,k,j,1) = &\n"
        "                      REAL(scalar_tend(i,k,j,P_QNC),real64) - &\n"
        "                      REAL(pr87_coupled_nsrc(i,k,j,1),real64)\n"
        "                 pr87_later_nsrc(i,k,j,2) = &\n"
        "                      REAL(scalar_tend(i,k,j,P_QNI),real64) - &\n"
        "                      REAL(pr87_coupled_nsrc(i,k,j,2),real64)\n"
        "                 pr87_coupled_qsrc(i,k,j,1) = moist_tend(i,k,j,P_QC)\n"
        "                 pr87_coupled_qsrc(i,k,j,2) = moist_tend(i,k,j,P_QI)\n"
        "                 pr87_coupled_nsrc(i,k,j,1) = scalar_tend(i,k,j,P_QNC)\n"
        "                 pr87_coupled_nsrc(i,k,j,2) = scalar_tend(i,k,j,P_QNI)\n"
        "               END DO\n"
        "             END DO\n"
        "           END DO\n"
        "         END IF\n"
    )
    source = source[:joint_start] + handoff + source[joint_start:]
    joint_start, joint_end, joint_call = _call_span(source, "rk_update_joint_moments")
    joint_call_new = joint_call[:-1] + (
        ", &\n"
        "              pr87_raw_qsrc, pr87_raw_nsrc, pr87_coupled_qsrc, &\n"
        "              pr87_coupled_nsrc, pr87_source_carrier, pr87_source_step, &\n"
        "              pr87_later_qsrc, pr87_later_nsrc)"
    )
    source = source[:joint_start] + joint_call_new + source[joint_end:]
    return source


def generate_source_capture(part2_source: str, solve_source: str) -> dict[str, str]:
    """Return instrumented part2 and solve source, failing on source drift."""
    return {
        "part2": _instrument_part2(part2_source),
        "solve": _instrument_solve(solve_source),
    }
