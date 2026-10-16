"""Generate a pinned, opt-in REAL64 correction for rain diffusion rounding.

This transform leaves the host's REAL32 diffusion tendencies untouched. It
computes the difference between the REAL64 stencil evaluation and the
increment that survived the host REAL32 accumulation, then hands that signed
delta to the grouped rain consumer. The caller controls whether the generated
source is composed into a build.
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

try:
    from pr87_physical_source_capture import _call_span, _unique_replace
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from pr87_physical_source_capture import _call_span, _unique_replace


PINNED_SHA256 = {
    "em": "7052f067b3c84cb247b8245ce8979064c63577dd7aaa851cc6db191aff095f51",
    "solve": "c2d0b35e8543f08ee1d474b14ef7863542676269dc0ebeb87bac9ed415cea5f8",
    "fragment": "716d3958970edeedd61eacf938272e94393ba9177807ecdffdd8b934143b836b",
}
EM_BODY_SHA256 = "d1e13537fb1c0f9fe0af228b60c7bd49fd83f5422041b1c8b5f964b417f7164e"
ACCEPTED_KERNEL_SHA256 = {
    "ffdce6170547fd0416d6073d4542a6a7e6dc4c316d4d04f4dc76a117a58efe19",
    "19d0259c423a3035a418174292c14d8671d778ebfe48a604cc80923c2f854541",
}

# Updated only when the helper implementation has passed its independent
# source review and pinned Intel O0/O2 regression.
HELPER_SHA256 = "0a8b2865fff3d7ad6592e0d1bc1d3f7b51970de13ac9ea128066b7cba655bfe3"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _require_pinned_source(label: str, source: str) -> None:
    actual = _sha256(source)
    expected = PINNED_SHA256[label]
    if label == "em":
        # The host body is fixed independently of its embedded transport kernel.
        # Each reviewed kernel is still accepted by an explicit content hash.
        marker = "!WRF:MODEL_LAYER:DYNAMICS"
        if source.count(marker) == 1:
            prefix, body = source.split(marker, 1)
            if (_sha256(prefix.strip() + "\n") in ACCEPTED_KERNEL_SHA256 and
                    _sha256(marker + body) == EM_BODY_SHA256):
                return
    if actual != expected:
        raise ValueError(f"{label} source SHA-256 mismatch: {actual}")


def _routine_span(source: str, start_marker: str, end_marker: str) -> tuple[int, int, str]:
    start = source.find(start_marker)
    if start < 0:
        raise ValueError(f"missing {start_marker}")
    end = source.find(end_marker, start)
    if end < 0:
        raise ValueError(f"missing {end_marker}")
    return start, end, source[start:end]


def _validate_helper(helper_source: str) -> None:
    if "MODULE pr87_horizontal_diffusion64" not in helper_source:
        raise ValueError("helper module name mismatch")
    if "SUBROUTINE horizontal_diffusion64" not in helper_source:
        raise ValueError("missing horizontal_diffusion64 helper")
    for name in (
        "field", "mut", "c1", "c2", "msfux", "msfuy", "msfvx_inv",
        "msfvy", "msftx", "msfty", "xkmhd", "rdx", "rdy", "increment",
    ):
        if not re.search(rf"\b{name}\b", helper_source, re.IGNORECASE):
            raise ValueError(f"helper API missing {name}")
    if not HELPER_SHA256:
        raise RuntimeError("helper SHA-256 pin is not frozen")
    if _sha256(helper_source) != HELPER_SHA256:
        raise ValueError("helper source SHA-256 mismatch")


def _instrument_em(em_source: str, helper_source: str) -> str:
    use_anchor = "MODULE module_em\n\n   USE module_model_constants"
    if em_source.count(use_anchor) != 1:
        raise ValueError("expected one module_em import anchor")
    em_source = em_source.replace(
        use_anchor, helper_source.rstrip() + "\n\n" + use_anchor, 1
    )
    use_text = (
        "MODULE module_em\n\n"
        "   USE, INTRINSIC :: iso_fortran_env, ONLY: real64\n"
        "   USE pr87_horizontal_diffusion64, ONLY: horizontal_diffusion64\n"
        "   USE module_model_constants"
    )
    em_source = _unique_replace(em_source, use_anchor, use_text, "module_em imports")
    em_source = _unique_replace(
        em_source,
        "p_qs, tiedtkescheme",
        "p_qs, p_qnr, tiedtkescheme",
        "P_QNR import",
    )

    routine_start, routine_end, routine = _routine_span(
        em_source, "SUBROUTINE rk_scalar_tend", "END SUBROUTINE rk_scalar_tend"
    )
    signature_anchor = "its, ite, jts, jte, kts, kte    )"
    routine = _unique_replace(
        routine, signature_anchor,
        "its, ite, jts, jte, kts, kte, rain_diffusion_delta )",
        "rk_scalar_tend signature",
    )
    dummy_anchor = (
        "INTEGER ,                INTENT(IN   ) :: ids, ide, jds, jde, kds, kde, &\n"
        "                                             ims, ime, jms, jme, kms, kme, &\n"
        "                                             its, ite, jts, jte, kts, kte"
    )
    routine = _unique_replace(
        routine,
        dummy_anchor,
        dummy_anchor + "\n   REAL(real64), OPTIONAL, INTENT(INOUT) :: &\n"
        "      rain_diffusion_delta(ims:ime,kms:kme,jms:jme,2)",
        "rk_scalar_tend dimensions and optional delta",
    )
    local_anchor = "   INTEGER :: im, i,j,k\n"
    local_vars = local_anchor + (
        "   REAL, ALLOCATABLE :: pr87_rain_tendency_before(:,:,:)\n"
        "   REAL(real64), ALLOCATABLE :: pr87_rain_diffusion_increment(:,:,:)\n"
        "   INTEGER :: pr87_diff_i_start, pr87_diff_i_end, pr87_diff_j_start, pr87_diff_j_end\n"
        "   INTEGER :: pr87_diff_k_end, pr87_diff_i, pr87_diff_j, pr87_diff_k, pr87_diff_channel\n"
        "   LOGICAL :: pr87_diff_specified, pr87_capture_rain_diffusion\n"
    )
    routine = _unique_replace(routine, local_anchor, local_vars, "rk_scalar_tend local declarations")

    call_start, call_end, call_text = _call_span(routine, "horizontal_diffusion")
    if "'m'" not in call_text[:100]:
        raise ValueError("unexpected horizontal_diffusion call in rk_scalar_tend")
    before_call = (
        "         pr87_capture_rain_diffusion = .FALSE.\n"
        "         pr87_diff_channel = 0\n"
        "         IF (PRESENT(rain_diffusion_delta) .AND. rk_step == 1 .AND. &\n"
        "             config_flags%mp_physics == 37 .AND. config_flags%diff_opt == 1 .AND. &\n"
        "             .NOT. mix2_off) THEN\n"
        "           IF (moist_step .AND. im == P_QR) THEN\n"
        "             pr87_capture_rain_diffusion = .TRUE.\n"
        "             pr87_diff_channel = 1\n"
        "           ELSE IF (.NOT. moist_step .AND. im == P_QNR) THEN\n"
        "             pr87_capture_rain_diffusion = .TRUE.\n"
        "             pr87_diff_channel = 2\n"
        "           END IF\n"
        "         END IF\n"
        "         IF (pr87_capture_rain_diffusion) THEN\n"
        "           ALLOCATE(pr87_rain_tendency_before(ims:ime,kms:kme,jms:jme), &\n"
        "                    pr87_rain_diffusion_increment(ims:ime,kms:kme,jms:jme))\n"
        "           pr87_rain_tendency_before = scalar_tends(:,:,:,im)\n"
        "         END IF\n"
    )

    after_call = (
        "\n         IF (pr87_capture_rain_diffusion) THEN\n"
        "           pr87_diff_specified = config_flags%specified .OR. config_flags%nested\n"
        "           pr87_diff_i_start = its\n"
        "           pr87_diff_i_end = MIN(ite,ide-1)\n"
        "           pr87_diff_j_start = jts\n"
        "           pr87_diff_j_end = MIN(jte,jde-1)\n"
        "           IF (config_flags%open_xs .OR. pr87_diff_specified) &\n"
        "             pr87_diff_i_start = MAX(ids+1,its)\n"
        "           IF (config_flags%open_xe .OR. pr87_diff_specified) &\n"
        "             pr87_diff_i_end = MIN(ide-2,ite)\n"
        "           IF (config_flags%open_ys .OR. pr87_diff_specified) &\n"
        "             pr87_diff_j_start = MAX(jds+1,jts)\n"
        "           IF (config_flags%open_ye .OR. pr87_diff_specified) &\n"
        "             pr87_diff_j_end = MIN(jde-2,jte)\n"
        "           IF (config_flags%periodic_x) pr87_diff_i_start = its\n"
        "           IF (config_flags%periodic_x) pr87_diff_i_end = MIN(ite,ide-1)\n"
        "           pr87_diff_k_end = MIN(kte,kde-1)\n"
        "           CALL horizontal_diffusion64( &\n"
        "               scalar(ims,kms,jms,im), mut, c1h, c2h, &\n"
        "               msfux, msfuy, msfvx_inv, msfvy, msftx, msfty, xkmhd, &\n"
        "               rdx, rdy, ims, ime, kms, kme, jms, jme, &\n"
        "               pr87_diff_i_start, pr87_diff_i_end, &\n"
        "               pr87_diff_j_start, pr87_diff_j_end, kts, pr87_diff_k_end, &\n"
        "               pr87_rain_diffusion_increment)\n"
        "           DO pr87_diff_j = pr87_diff_j_start, pr87_diff_j_end\n"
        "             DO pr87_diff_k = kts, pr87_diff_k_end\n"
        "               DO pr87_diff_i = pr87_diff_i_start, pr87_diff_i_end\n"
        "                 rain_diffusion_delta(pr87_diff_i,pr87_diff_k,pr87_diff_j, &\n"
        "                                      pr87_diff_channel) = &\n"
        "                      REAL(pr87_rain_tendency_before(pr87_diff_i,pr87_diff_k,pr87_diff_j),real64) + &\n"
        "                      pr87_rain_diffusion_increment(pr87_diff_i,pr87_diff_k,pr87_diff_j) - &\n"
        "                      REAL(scalar_tends(pr87_diff_i,pr87_diff_k,pr87_diff_j,im),real64)\n"
        "               END DO\n"
        "             END DO\n"
        "           END DO\n"
        "           DEALLOCATE(pr87_rain_tendency_before,pr87_rain_diffusion_increment)\n"
        "         END IF\n"
    )
    guard_start = routine.rfind("IF (.not. mix2_off)", 0, call_start)
    guard_prefix = routine[guard_start:call_start]
    if guard_start < 0 or "&" not in guard_prefix:
        raise ValueError("missing guarded horizontal_diffusion call")
    guarded_call = (
        "IF (.not. mix2_off) THEN\n"
        + before_call
        + call_text
        + after_call
        + "\n         END IF"
    )
    routine = routine[:guard_start] + guarded_call + routine[call_end:]
    return em_source[:routine_start] + routine + em_source[routine_end:]


def _instrument_solve(solve_source: str) -> str:
    local_anchor = "   REAL(real64), ALLOCATABLE :: pr87_later_qsrc(:,:,:,:), pr87_later_nsrc(:,:,:,:)\n"
    solve_source = _unique_replace(
        solve_source, local_anchor,
        local_anchor +
        "   REAL(real64), ALLOCATABLE :: pr87_rain_diffusion_delta(:,:,:,:)\n"
        "   INTEGER :: pr87_rain_diffusion_step\n",
        "solve rain diffusion delta declarations",
    )

    allocate_anchor = "                  pr87_later_nsrc(ims:ime,kms:kme,jms:jme,2))\n"
    solve_source = _unique_replace(
        solve_source, allocate_anchor,
        "                  pr87_later_nsrc(ims:ime,kms:kme,jms:jme,2), &\n"
        "                  pr87_rain_diffusion_delta(ims:ime,kms:kme,jms:jme,2))\n",
        "solve rain diffusion allocate",
    )
    allocation_end = "       END IF\nCALL first_rk_step_part2"
    solve_source = _unique_replace(
        solve_source,
        allocation_end,
        "       END IF\n"
        "       IF (config_flags%mp_physics == 37 .AND. rk_step == 1) THEN\n"
        "         pr87_rain_diffusion_delta = 0.0_real64\n"
        "         pr87_rain_diffusion_step = grid%itimestep\n"
        "       END IF\n"
        "CALL first_rk_step_part2",
        "per-timestep rain delta initialization",
    )

    # The same extensive tendency correction is reused by this timestep's
    # RK1/RK2/RK3 candidates, matching the host's first-stage diffusion call.
    selected_calls: dict[str, tuple[int, int, str]] = {}
    for match in re.finditer(r"\bCALL\s+rk_scalar_tend\b", solve_source):
        start, end, call = _call_span(solve_source, "rk_scalar_tend", match.start())
        if "moist_old(ims,kms,jms,im)" in call:
            selected_calls["moist"] = (start, end, call)
        elif "scalar_old(ims,kms,jms,is)" in call:
            selected_calls["scalar"] = (start, end, call)
    if set(selected_calls) != {"moist", "scalar"}:
        raise ValueError("expected the moisture and scalar rk_scalar_tend call sites")
    for start, end, call in sorted(selected_calls.values(), reverse=True):
        call_new = call[:-1] + ", &\n                 rain_diffusion_delta=pr87_rain_diffusion_delta)"
        solve_source = solve_source[:start] + call_new + solve_source[end:]

    joint_start, joint_end, joint_call = _call_span(solve_source, "rk_update_joint_moments")
    joint_call_new = joint_call[:-1] + (
        ", &\n              pr87_rain_diffusion_delta, pr87_rain_diffusion_step)"
    )
    solve_source = solve_source[:joint_start] + joint_call_new + solve_source[joint_end:]
    return solve_source


def _instrument_fragment(fragment_source: str) -> str:
    signature_anchor = "pr87_source_carrier,pr87_source_step,pr87_later_qsrc,pr87_later_nsrc)"
    fragment_source = _unique_replace(
        fragment_source, signature_anchor,
        "pr87_source_carrier,pr87_source_step,pr87_later_qsrc,pr87_later_nsrc, &\n"
        "     pr87_rain_diffusion_delta,pr87_rain_diffusion_step)",
        "native fragment signature",
    )
    decl_anchor = "  REAL(real64),INTENT(IN) :: pr87_later_nsrc(ims:ime,kms:kme,jms:jme,2)\n"
    fragment_source = _unique_replace(
        fragment_source, decl_anchor,
        decl_anchor +
        "  REAL(real64),INTENT(IN),OPTIONAL :: &\n"
        "       pr87_rain_diffusion_delta(ims:ime,kms:kme,jms:jme,2)\n"
        "  INTEGER,INTENT(IN),OPTIONAL :: pr87_rain_diffusion_step\n",
        "native rain diffusion dummies",
    )
    declarations = (
        "  REAL(real64) :: diffusion_delta_sum(2),diffusion_delta_l1(2),diffusion_delta_max(2)\n"
    )
    scalar_anchor = "  REAL(real64) :: outflow,cfl,maxcfl,source_candidate(2),source_sum64(2)\n"
    fragment_source = _unique_replace(
        fragment_source, scalar_anchor,
        scalar_anchor + declarations,
        "native rain diffusion budget locals",
    )
    guard_anchor = "  ! Current experiment: one specified domain, one tile, no implicit vertical advection.\n"
    guard = (
        "  IF (PRESENT(pr87_rain_diffusion_delta) .NEQV. &\n"
        "      PRESENT(pr87_rain_diffusion_step)) &\n"
        "    CALL wrf_error_fatal('PR87 rain diffusion delta/step must be supplied together')\n"
        "  IF (PRESENT(pr87_rain_diffusion_delta)) THEN\n"
        "    IF (pr87_rain_diffusion_step /= itimestep) &\n"
        "      CALL wrf_error_fatal('PR87 rain diffusion timestep mismatch')\n"
        "  END IF\n"
        "  diffusion_delta_sum=0.0_real64\n"
        "  diffusion_delta_l1=0.0_real64\n"
        "  diffusion_delta_max=0.0_real64\n"
    )
    fragment_source = _unique_replace(fragment_source, guard_anchor, guard + guard_anchor, "native pair guard")

    source_anchor = "      qs64(cell,p)=REAL(qs(cell,p),real64); ns64(cell,p)=REAL(ns(cell,p),real64)\n"
    updated_source = source_anchor + (
        "      IF (p==3.AND.PRESENT(pr87_rain_diffusion_delta)) THEN\n"
        "        IF (.NOT.ALL(ieee_is_finite(pr87_rain_diffusion_delta(i,k,j,:)))) &\n"
        "          CALL wrf_error_fatal('PR87 nonfinite rain diffusion correction')\n"
        "        qs64(cell,p)=qs64(cell,p)+pr87_rain_diffusion_delta(i,k,j,1)\n"
        "        ns64(cell,p)=ns64(cell,p)+pr87_rain_diffusion_delta(i,k,j,2)\n"
        "        diffusion_delta_sum=diffusion_delta_sum+REAL(dt,real64)* &\n"
        "             pr87_rain_diffusion_delta(i,k,j,:)\n"
        "        diffusion_delta_l1=diffusion_delta_l1+REAL(dt,real64)* &\n"
        "             ABS(pr87_rain_diffusion_delta(i,k,j,:))\n"
        "        diffusion_delta_max=MAX(diffusion_delta_max,REAL(dt,real64)* &\n"
        "             ABS(pr87_rain_diffusion_delta(i,k,j,:)))\n"
        "      END IF\n"
    )
    fragment_source = _unique_replace(fragment_source, source_anchor, updated_source, "native p3 source add")

    budget_anchor = "  CLOSE(u)\n  IF (.NOT.feasible) THEN\n"
    budget = (
        "  CLOSE(u)\n"
        "  IF (PRESENT(pr87_rain_diffusion_delta)) THEN\n"
        "    OPEN(NEWUNIT=u,FILE='pr87_rain_diffusion_precision.raw',STATUS='UNKNOWN', &\n"
        "         POSITION='APPEND',ACTION='WRITE')\n"
        "    WRITE(u,*) 'RAIN_DIFFUSION_RK_CORRECTION',itimestep,rk,cells\n"
        "    WRITE(u,*) 'DT_SUM_PRESSURE_Q_N',diffusion_delta_sum\n"
        "    WRITE(u,*) 'DT_L1_PRESSURE_Q_N',diffusion_delta_l1\n"
        "    WRITE(u,*) 'DT_MAXABS_PRESSURE_Q_N',diffusion_delta_max\n"
        "    CLOSE(u)\n"
        "  END IF\n"
        "  IF (.NOT.feasible) THEN\n"
    )
    fragment_source = _unique_replace(fragment_source, budget_anchor, budget, "native precision ledger")
    return fragment_source


def extend_rain_diffusion_precision(
    em: str, solve: str, fragment: str, helper_source: str
) -> dict[str, str]:
    """Return the three-source overlay after exact source/helper provenance checks."""
    _require_pinned_source("em", em)
    _require_pinned_source("solve", solve)
    _require_pinned_source("fragment", fragment)
    _validate_helper(helper_source)
    updated_fragment = _instrument_fragment(fragment)
    updated_em = _instrument_em(em, helper_source)
    if updated_em.count(fragment) != 1:
        raise ValueError("pinned native fragment must occur exactly once inside module_em")
    updated_em = updated_em.replace(fragment, updated_fragment, 1)
    return {"em": updated_em, "solve": _instrument_solve(solve), "fragment": updated_fragment}
