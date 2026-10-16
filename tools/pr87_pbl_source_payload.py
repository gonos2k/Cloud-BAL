"""Thread an explicit Shinhong REAL64 source correction to the PR87 consumer.

This source-only overlay does not alter Shinhong or the legacy REAL32 tendency
arrays.  It adds a solve-owned, per-step four-channel buffer
``[QC,QNC,QI,QNI]`` and passes it explicitly through the PBL and native call
chain.  The native fragment consumes it alongside the existing raw/coupled/
later source bank; the payload is never cached in module state.
"""

from __future__ import annotations

import hashlib
import re


PINNED_SHA256 = {
    "em": "bf97496a1013b86ac0382fb9dfb22ad9e818af996d5bcb49bebcbdeec790f8b2",
    "solve": "002fc11991f2d51e8e0c1102f1ea8c11443358abeb0cc7ffef481b9efa673122",
    "part1": "de0d6f270dbd2a8aea8bcadcbb6690fc3fc57e2fd4a14261916fb9bbd4dbf880",
    "part2": "007fcce0cdc51cf18c2d8c33de42ec1367c3419e3c2c38770ecf7be8800b44c8",
    "pbl_driver": "c823766673868af27fee9eed3ab11b0d8735b3a5ca0cb2a30c6b65e50f92c5f9",
    "fragment": "da168838410ac7b90de0918b5c340ea0e2017e232c409964f12dc8abed61e296",
}

_ARRAY = "pr87_pbl_tendency_delta64"
_STEP = "pr87_pbl_tendency_step"
_PHASE = "pr87_pbl_tendency_phase"
_SHINHONG_KEYWORD = "PR87_TENDENCY_DELTA64"


def _sha256(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise ValueError(f"expected one {label} anchor, found {count}")
    return source.replace(old, new, 1)


def _append_call_args(source: str, name: str, text: str) -> str:
    from pr87_physical_source_capture import _call_span

    start, end, call = _call_span(source, name)
    if not call.endswith(")"):
        raise ValueError(f"unexpected {name} call terminator")
    prefix = call[:-1]
    last_line_start = prefix.rfind("\n") + 1
    closing_line = prefix[last_line_start:]
    if not closing_line.strip() or closing_line.strip() == "&":
        prefix = prefix[:last_line_start].rstrip()
        call = prefix + "\n     & , " + text + " &\n     & )"
    else:
        call = prefix.rstrip() + ", " + text + ")"
    return source[:start] + call + source[end:]


def _require_hashes(sources: dict[str, str]) -> None:
    if set(sources) != set(PINNED_SHA256):
        raise ValueError("source payload expects exactly the six pinned V24c inputs")
    for name, expected in PINNED_SHA256.items():
        actual = _sha256(sources[name])
        if actual != expected:
            raise ValueError(f"{name} source SHA-256 mismatch: {actual}")


def finalize_source_rate_validation(source: str) -> str:
    """Check the assigned REAL64 source-rate payload and drop its stale REAL32 local."""
    source = _replace_once(
        source,
        "  REAL(real32) :: source_rate32(2),source_increment32(2),source_endpoint32(2)\n",
        "  REAL(real32) :: source_increment32(2),source_endpoint32(2)\n",
        "stale REAL32 source-rate declaration",
    )
    return _replace_once(
        source,
        "        IF (.NOT.ALL(ieee_is_finite(source_rate32))) &\n"
        "          CALL wrf_error_fatal('PR87 nonfinite intensive source payload')\n",
        "        IF (.NOT.ALL(ieee_is_finite(source_rate64))) &\n"
        "          CALL wrf_error_fatal('PR87 nonfinite intensive source payload')\n",
        "REAL64 source-rate finiteness gate",
    )


def _instrument_solve(source: str) -> str:
    from pr87_physical_source_capture import _call_span, _unique_replace

    local_anchor = "   INTEGER                         :: ij , iteration\n"
    source = _unique_replace(
        source,
        local_anchor,
        local_anchor
        + "   REAL(real64), ALLOCATABLE :: pr87_pbl_tendency_delta64(:,:,:,:)\n"
        + "   INTEGER :: pr87_pbl_tendency_step, pr87_pbl_tendency_phase\n",
        "solve PBL payload locals",
    )

    first_start, first_end, first_call = _call_span(source, "first_rk_step_part1")
    source = _append_call_args(
        source,
        "first_rk_step_part1",
        "pr87_pbl_tendency_delta64=pr87_pbl_tendency_delta64, &\n"
        "     & pr87_pbl_tendency_step=pr87_pbl_tendency_step, &\n"
        "     & pr87_pbl_tendency_phase=pr87_pbl_tendency_phase",
    )
    first_start, first_end, first_call = _call_span(source, "first_rk_step_part1")
    # Allocate and initialize in solve before part1 invokes pbl_driver.  This
    # is a per-step buffer, not a SAVE/cache; Shinhong writes only its tile.
    init = (
        "       IF (.NOT.ALLOCATED(pr87_pbl_tendency_delta64)) THEN\n"
        "         ALLOCATE(pr87_pbl_tendency_delta64(ims:ime,kms:kme,jms:jme,4))\n"
        "       END IF\n"
        "       pr87_pbl_tendency_delta64 = 0.0_real64\n"
        "       pr87_pbl_tendency_step = grid%itimestep\n"
        "       pr87_pbl_tendency_phase = 1\n"
    )
    source = source[:first_start] + init + first_call + source[first_end:]

    source = _append_call_args(
        source,
        "first_rk_step_part2",
        "pr87_pbl_tendency_delta64, pr87_pbl_tendency_step, pr87_pbl_tendency_phase",
    )
    source = _append_call_args(
        source,
        "rk_update_joint_moments",
        "pr87_pbl_tendency_delta64, pr87_pbl_tendency_step, pr87_pbl_tendency_phase",
    )
    return source


def _instrument_part1(source: str) -> str:
    from pr87_physical_source_capture import _call_span, _unique_replace

    signature_anchor = "                             , feedback_is_ready                &\n                            )"
    source = _unique_replace(
        source,
        signature_anchor,
        "                             , feedback_is_ready                &\n"
        "                             , pr87_pbl_tendency_delta64           &\n"
        "                             , pr87_pbl_tendency_step, pr87_pbl_tendency_phase)\n",
        "part1 signature",
    )
    use_anchor = "    USE module_state_description\n"
    source = _unique_replace(
        source,
        use_anchor,
        "    USE, INTRINSIC :: iso_fortran_env, ONLY: real64\n" + use_anchor,
        "part1 real64 import",
    )
    dummy_anchor = (
        "    LOGICAL, INTENT(IN), OPTIONAL :: feedback_is_ready  ! For WRF-CMAQ coupled model, indicates feedback information is available\n"
    )
    source = _unique_replace(
        source,
        dummy_anchor,
        dummy_anchor
        + "    REAL(real64), INTENT(INOUT) :: pr87_pbl_tendency_delta64(ims:ime,kms:kme,jms:jme,4)\n"
        + "    INTEGER, INTENT(INOUT) :: pr87_pbl_tendency_step, pr87_pbl_tendency_phase\n",
        "part1 payload declarations",
    )
    source = _append_call_args(source, "pbl_driver", "PR87_TENDENCY_DELTA64=pr87_pbl_tendency_delta64")
    return source


def _instrument_pbl_driver(source: str) -> str:
    from pr87_physical_source_capture import _call_span, _unique_replace

    signature_anchor = "              ,QNORM, fasdas, mp_physics &\n!\n! END FASDAS\n!\n                                                                     )"
    source = _unique_replace(
        source,
        signature_anchor,
        "              ,QNORM, fasdas, mp_physics &\n"
        "              ,pr87_tendency_delta64 &\n"
        "!\n! END FASDAS\n!\n                                                                     )",
        "pbl_driver signature",
    )
    declaration_anchor = "   USE module_model_constants\n"
    source = _unique_replace(
        source,
        declaration_anchor,
        declaration_anchor + "   USE, INTRINSIC :: iso_fortran_env, ONLY: real64\n",
        "pbl_driver real64 import",
    )
    local_anchor = "   USE module_bl_shinhong\n"
    # The local declaration block follows the module imports; use its stable
    # scalar_tend declaration to keep the new argument out of unrelated code.
    scalar_anchor = (
        "    REAL , OPTIONAL   ,DIMENSION(ims:ime,kms:kme,jms:jme,num_scalar),INTENT(INOUT)   :: scalar_tend\n"
    )
    source = _unique_replace(
        source,
        scalar_anchor,
        scalar_anchor
        + "    REAL(real64), INTENT(INOUT) :: pr87_tendency_delta64(ims:ime,kms:kme,jms:jme,4)\n",
        "pbl_driver payload declaration",
    )
    _ = local_anchor  # document the imported producer whose call is extended below
    source = _append_call_args(source, "shinhong", "PR87_TENDENCY_DELTA64=pr87_tendency_delta64")
    return source


def _instrument_part2(source: str) -> str:
    from pr87_physical_source_capture import _call_span, _unique_replace

    signature_anchor = (
        "                             , pr87_source_carrier, pr87_source_step    &\n"
        "                            )"
    )
    source = _unique_replace(
        source,
        signature_anchor,
        "                             , pr87_source_carrier, pr87_source_step    &\n"
        "                             , pr87_pbl_tendency_delta64           &\n"
        "                             , pr87_pbl_tendency_step, pr87_pbl_tendency_phase)\n",
        "part2 signature",
    )
    use_anchor = "    USE module_state_description\n"
    source = _unique_replace(
        source,
        use_anchor,
        "    USE, INTRINSIC :: iso_fortran_env, ONLY: real64\n" + use_anchor,
        "part2 real64 import",
    )
    declaration_anchor = "    INTEGER, INTENT(OUT) :: pr87_source_step\n"
    source = _unique_replace(
        source,
        declaration_anchor,
        "    INTEGER, INTENT(OUT) :: pr87_source_step\n"
        "    REAL(real64), INTENT(IN) :: pr87_pbl_tendency_delta64(ims:ime,kms:kme,jms:jme,4)\n"
        + "    INTEGER, INTENT(IN) :: pr87_pbl_tendency_step, pr87_pbl_tendency_phase\n",
        "part2 payload declarations",
    )
    # Part2 is the explicit bridge between part1's producer and solve's later
    # RK consumer.  Assert its returned payload identity without mutating it.
    init_anchor = "   rk_step = 1\n"
    source = _unique_replace(
        source,
        init_anchor,
        init_anchor
        + "   IF (pr87_pbl_tendency_step /= grid%itimestep .OR. &\n"
        + "       pr87_pbl_tendency_phase /= 1) &\n"
        + "     CALL wrf_error_fatal('PR87 PBL tendency payload epoch mismatch')\n",
        "part2 payload epoch check",
    )
    # The part2 -> solve call chain is via explicit output sidecars already;
    # this routine receives the same payload so the per-step chain is visible
    # and compiler-checked at every boundary.
    return source


def _instrument_fragment(source: str) -> str:
    from pr87_physical_source_capture import _unique_replace

    signature_anchor = "pr87_cloud_rain_diffusion_delta,pr87_cloud_rain_diffusion_step)"
    source = _unique_replace(
        source,
        signature_anchor,
        signature_anchor[:-1]
        + ",pr87_pbl_tendency_delta64,pr87_pbl_tendency_step,pr87_pbl_tendency_phase)",
        "native payload signature",
    )
    declaration_anchor = "  INTEGER,INTENT(IN),OPTIONAL :: pr87_cloud_rain_diffusion_step\n"
    source = _unique_replace(
        source,
        declaration_anchor,
        declaration_anchor
        + "  REAL(real64),INTENT(IN) :: pr87_pbl_tendency_delta64(ims:ime,kms:kme,jms:jme,4)\n"
        + "  INTEGER,INTENT(IN) :: pr87_pbl_tendency_step,pr87_pbl_tendency_phase\n",
        "native payload declarations",
    )
    rate_anchor = "  REAL(real64) :: outflow,cfl,maxcfl,source_candidate(2),source_sum64(2)\n"
    if source.count(rate_anchor) != 1:
        raise ValueError("missing native REAL64 source scratch declaration")
    source = source.replace(
        rate_anchor,
        rate_anchor[:-1]
        + ",source_rate64(2),pbl_source_correction_sum(4),pbl_source_correction_l1(4), &\n"
        + "       pbl_source_correction_max(4),pbl_carrier_min,pbl_carrier_max,pbl_delta\n"
        + "  INTEGER :: pbl_ledger_unit,pbl_ledger_cells,pbl_channel\n",
        1,
    )
    # Validate explicit provenance and values before any state writes.  Delta
    # channels are [QC,QNC,QI,QNI]; only the first two native pairs consume it.
    # The sparse ledger records the proposed dt*captured_carrier*delta by
    # channel for each RK call. These are weighted numerical source-correction
    # amounts, not committed updates, physical budgets, or cross-RK sums.
    anchor = "  IF (spec_zone/=1.OR.il>ih.OR.jl>jh.OR.kl>kh) &\n    CALL wrf_error_fatal('PR85 joint update unsupported domain footprint')\n"
    check = anchor + (
        "  IF (pr87_source_step/=itimestep.OR.pr87_pbl_tendency_step/=itimestep.OR. &\n"
        "      pr87_pbl_tendency_phase/=1) &\n"
        "    CALL wrf_error_fatal('PR87 PBL/source payload epoch mismatch')\n"
        "  pbl_source_correction_sum=0.0_real64; pbl_source_correction_l1=0.0_real64; &\n"
        "       pbl_source_correction_max=0.0_real64\n"
        "  pbl_carrier_min=HUGE(0.0_real64); pbl_carrier_max=-HUGE(0.0_real64); pbl_ledger_cells=0\n"
        "  DO j=jl,jh\n"
        "  DO k=kl,kh\n"
        "  DO i=il,ih\n"
        "    IF (.NOT.ALL(ieee_is_finite(pr87_pbl_tendency_delta64(i,k,j,:)))) &\n"
        "      CALL wrf_error_fatal('PR87 nonfinite PBL tendency correction')\n"
        "    IF (.NOT.ieee_is_finite(pr87_source_carrier(i,k,j)).OR. &\n"
        "        pr87_source_carrier(i,k,j)<=0.0_real64) &\n"
        "      CALL wrf_error_fatal('PR87 invalid captured PBL source carrier')\n"
        "    IF (pr87_coupled_qsrc(i,k,j,1)/=qt(i,k,j,qindex(1)).OR. &\n"
        "        pr87_coupled_qsrc(i,k,j,2)/=qt(i,k,j,qindex(2)).OR. &\n"
        "        pr87_coupled_nsrc(i,k,j,1)/=nt(i,k,j,nindex(1)).OR. &\n"
        "        pr87_coupled_nsrc(i,k,j,2)/=nt(i,k,j,nindex(2))) &\n"
        "      CALL wrf_error_fatal('PR87 PBL source reference mismatch')\n"
        "    pbl_ledger_cells=pbl_ledger_cells+1\n"
        "    pbl_carrier_min=MIN(pbl_carrier_min,pr87_source_carrier(i,k,j))\n"
        "    pbl_carrier_max=MAX(pbl_carrier_max,pr87_source_carrier(i,k,j))\n"
        "    DO pbl_channel=1,4\n"
        "      pbl_delta=REAL(dt,real64)*pr87_source_carrier(i,k,j)* &\n"
        "                  pr87_pbl_tendency_delta64(i,k,j,pbl_channel)\n"
        "      pbl_source_correction_sum(pbl_channel)= &\n"
        "          pbl_source_correction_sum(pbl_channel)+pbl_delta\n"
        "      pbl_source_correction_l1(pbl_channel)= &\n"
        "          pbl_source_correction_l1(pbl_channel)+ABS(pbl_delta)\n"
        "      pbl_source_correction_max(pbl_channel)= &\n"
        "          MAX(pbl_source_correction_max(pbl_channel),ABS(pbl_delta))\n"
        "    END DO\n"
        "  END DO\n"
        "  END DO\n"
        "  END DO\n"
        "  OPEN(NEWUNIT=pbl_ledger_unit,FILE='pr87_pbl_source_correction.raw', &\n"
        "       STATUS='UNKNOWN',POSITION='APPEND')\n"
        "  WRITE(pbl_ledger_unit,'(A,1X,I0,1X,I0,1X,ES24.16,1X,I0,1X,I0, &\n"
        "       & 2(1X,ES24.16),12(1X,ES24.16))') 'PR87_PBL_SOURCE_CORRECTION_RK', &\n"
        "       itimestep,rk,dt,pr87_pbl_tendency_phase,pbl_ledger_cells, &\n"
        "       pbl_carrier_min,pbl_carrier_max,pbl_source_correction_sum, &\n"
        "       pbl_source_correction_l1,pbl_source_correction_max\n"
        "  CLOSE(pbl_ledger_unit)\n"
    )
    source = _unique_replace(source, anchor, check, "native pre-mutation payload validation")

    # Reconstruct the first two source banks from their intensive REAL32
    # capture, the explicit Shinhong correction, the saved carrier, and the
    # post-capture later-source amount.  Diffusion corrections are still added
    # by the existing code below, exactly once.
    old = "      qs64(cell,p)=REAL(qs(cell,p),real64); ns64(cell,p)=REAL(ns(cell,p),real64)\n"
    new = (
        "      IF (p<=2) THEN\n"
        "        IF (p==1) THEN\n"
        "          qs64(cell,p)=(REAL(pr87_raw_qsrc(i,k,j,p),real64)+ &\n"
        "              pr87_pbl_tendency_delta64(i,k,j,1))*REAL(pr87_source_carrier(i,k,j),real64)+ &\n"
        "              pr87_later_qsrc(i,k,j,p)\n"
        "          ns64(cell,p)=(REAL(pr87_raw_nsrc(i,k,j,p),real64)+ &\n"
        "              pr87_pbl_tendency_delta64(i,k,j,2))*REAL(pr87_source_carrier(i,k,j),real64)+ &\n"
        "              pr87_later_nsrc(i,k,j,p)\n"
        "        ELSE\n"
        "          qs64(cell,p)=(REAL(pr87_raw_qsrc(i,k,j,p),real64)+ &\n"
        "              pr87_pbl_tendency_delta64(i,k,j,3))*REAL(pr87_source_carrier(i,k,j),real64)+ &\n"
        "              pr87_later_qsrc(i,k,j,p)\n"
        "          ns64(cell,p)=(REAL(pr87_raw_nsrc(i,k,j,p),real64)+ &\n"
        "              pr87_pbl_tendency_delta64(i,k,j,4))*REAL(pr87_source_carrier(i,k,j),real64)+ &\n"
        "              pr87_later_nsrc(i,k,j,p)\n"
        "        END IF\n"
        "      ELSE\n"
        "        qs64(cell,p)=REAL(qs(cell,p),real64); ns64(cell,p)=REAL(ns(cell,p),real64)\n"
        "      END IF\n"
    )
    source = _unique_replace(source, old, new, "initial PBL-corrected source bank")

    # The source-first retry applies the unweighted correction in the source
    # stage, then lets the existing single carrier factor act on that state.
    old_rates = "        source_rate32=[pr87_raw_qsrc(i,k,j,p),pr87_raw_nsrc(i,k,j,p)]\n"
    new_rates = (
        "        source_rate64=[REAL(pr87_raw_qsrc(i,k,j,p),real64), &\n"
        "                        REAL(pr87_raw_nsrc(i,k,j,p),real64)]\n"
        "        IF (p==1) source_rate64=source_rate64+ &\n"
        "             [pr87_pbl_tendency_delta64(i,k,j,1),pr87_pbl_tendency_delta64(i,k,j,2)]\n"
        "        IF (p==2) source_rate64=source_rate64+ &\n"
        "             [pr87_pbl_tendency_delta64(i,k,j,3),pr87_pbl_tendency_delta64(i,k,j,4)]\n"
    )
    source = _unique_replace(source, old_rates, new_rates, "source-first corrected rates")
    old_candidate = (
        "        source_candidate=[REAL(q1(i,k,j,qindex(p)),real64), &\n"
        "                          REAL(n1(i,k,j,nindex(p)),real64)]+REAL(dt,real64)*REAL(source_rate32,real64)\n"
    )
    new_candidate = (
        "        source_candidate=[REAL(q1(i,k,j,qindex(p)),real64), &\n"
        "                          REAL(n1(i,k,j,nindex(p)),real64)]+REAL(dt,real64)*source_rate64\n"
    )
    source = _unique_replace(source, old_candidate, new_candidate, "source-first corrected candidate")
    old_inc = "        source_increment32=dt*source_rate32\n"
    new_inc = (
        "        source_increment32=REAL(REAL(dt,real64)*source_rate64,real32)\n"
    )
    source = _unique_replace(source, old_inc, new_inc, "source-first corrected stored increment")
    old_sum = "        source_sum64=REAL(dt,real64)*REAL(source_rate32,real64)\n"
    source = _unique_replace(
        source, old_sum,
        "        source_sum64=REAL(dt,real64)*source_rate64\n",
        "source-first corrected increment check",
    )
    # Check the actual REAL32 source-stage pair against strict cloud bounds
    # before any air transport is attempted.  The bounded storage call rejects
    # continuously invalid inputs; this adds no floors or widened PSD band.
    check_anchor = (
        "        source_endpoint32=[q1(i,k,j,qindex(p)),n1(i,k,j,nindex(p))]+source_increment32\n"
    )
    source_stage_check = check_anchor + (
        "        IF (p==1) THEN\n"
        "          CALL joint_moment_store(source_candidate(1),source_candidate(2),drydensity(cell), &\n"
        "               minmass(p),maxmass(p),.TRUE.,source_endpoint32(1),source_endpoint32(2), &\n"
        "               adjustment,full_valid,allow_normal_q_adjustment=.TRUE., &\n"
        "               allow_joint_quantum_absence=.TRUE.,volume_number_bounds=number_bounds(cell,:,p))\n"
        "        ELSE\n"
        "          CALL joint_moment_store(source_candidate(1),source_candidate(2),drydensity(cell), &\n"
        "               minmass(p),maxmass(p),.TRUE.,source_endpoint32(1),source_endpoint32(2), &\n"
        "               adjustment,full_valid,allow_normal_q_adjustment=.TRUE., &\n"
        "               allow_joint_quantum_absence=.TRUE.)\n"
        "        END IF\n"
        "        IF (.NOT.full_valid) &\n"
        "          CALL wrf_error_fatal('PR87 corrected source-stage pair fails strict storage validation')\n"
    )
    source = _unique_replace(source, check_anchor, source_stage_check, "strict corrected source stage")
    return source


def _replace_fragment_in_em(em: str, fragment: str) -> str:
    pattern = re.compile(
        r"(?im)^SUBROUTINE rk_update_joint_moments\b.*?^END SUBROUTINE rk_update_joint_moments\s*"
    , re.S)
    matches = list(pattern.finditer(em))
    if len(matches) != 1:
        raise ValueError(f"expected one embedded native routine, found {len(matches)}")
    fragment_match = pattern.search(fragment)
    if fragment_match is None:
        raise ValueError("native fragment does not contain rk_update_joint_moments")
    return em[:matches[0].start()] + fragment_match.group(0) + em[matches[0].end():]


def extend_pbl_source_payload(
    em: str,
    solve: str,
    part1: str,
    part2: str,
    pbl_driver: str,
    fragment: str,
) -> dict[str, str]:
    """Return hash-pinned sources with the explicit four-channel PBL route."""
    sources = {
        "em": em,
        "solve": solve,
        "part1": part1,
        "part2": part2,
        "pbl_driver": pbl_driver,
        "fragment": fragment,
    }
    _require_hashes(sources)

    generated_fragment = _instrument_fragment(fragment)
    generated = {
        "fragment": generated_fragment,
        "em": _replace_fragment_in_em(em, generated_fragment),
        "solve": _instrument_solve(solve),
        "part1": _instrument_part1(part1),
        "part2": _instrument_part2(part2),
        "pbl_driver": _instrument_pbl_driver(pbl_driver),
    }
    return generated
