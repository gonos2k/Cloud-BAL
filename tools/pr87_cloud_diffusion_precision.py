"""Extend the pinned RK1 diffusion correction to cloud and rain moments.

The host REAL32 diffusion call and tendency accumulator remain unchanged. A
REAL64 replay computes each channel's signed difference around that call and
passes the four source deltas to the existing grouped native consumer. A
single cloud cell also emits pre/post stencil operands for independent replay.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from collections.abc import Mapping

from pr87_rain_diffusion_precision import _call_span, _unique_replace


PINNED_SHA256 = {
    "em": "1a716f5bd90b6673130832198592ecb006ab4f25d746c207b65a0f4ebd826712",
    "solve": "b333a16fef56f669bfb88267a97999281d41a981e50a2c88e44b26cd481fd7d4",
    "fragment": "912acc254708b8ab0a38f13e0b41fdafbf22f9f2f4f4d1684e6d1f475e9baab3",
}
EM_BODY_SHA256 = "d3d9ab3ad03655e833cb17b785f2290e577122f88b64a54bbc27d7c35c4f102d"
EM_KERNEL_SHA256S = {
    "eb3759913af7d89ab5d6a6074c0e452a22d79633c15eb40c597ff83d3ddc5648",
    "60917061915e0452251c27db7b5d4e97061729605c3218cd291c2cbc3e519e74",
}
HELPER_SHA256 = "0a8b2865fff3d7ad6592e0d1bc1d3f7b51970de13ac9ea128066b7cba655bfe3"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _require_pins(em: str, solve: str, fragment: str, helper: str) -> None:
    em_hash = _sha256(em)
    marker = "!WRF:MODEL_LAYER:DYNAMICS"
    if em.count(marker) == 1:
        prefix, body = em.split(marker, 1)
        if (_sha256(prefix.strip() + "\n") in EM_KERNEL_SHA256S and
                _sha256(marker + body) == EM_BODY_SHA256):
            em_hash = PINNED_SHA256["em"]
    actual = {"em": em_hash, "solve": _sha256(solve), "fragment": _sha256(fragment)}
    for label, digest in actual.items():
        if digest != PINNED_SHA256[label]:
            raise ValueError(f"{label} source SHA-256 mismatch: {digest}")
    if _sha256(helper) != HELPER_SHA256:
        raise ValueError("horizontal_diffusion64 helper SHA-256 mismatch")


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    return _unique_replace(source, old, new, label)


def _instrument_em(em: str, helper: str) -> str:
    fragment_start = em.find("SUBROUTINE rk_update_joint_moments")
    if fragment_start < 0:
        raise ValueError("missing embedded native update fragment")
    fragment_end = em.find("END SUBROUTINE rk_update_joint_moments", fragment_start)
    if fragment_end < 0:
        raise ValueError("unterminated embedded native update fragment")
    fragment_end += len("END SUBROUTINE rk_update_joint_moments")
    embedded_fragment = em[fragment_start:fragment_end]
    marker = "PR87_NATIVE_UPDATE_FRAGMENT_PLACEHOLDER"
    em = em[:fragment_start] + marker + em[fragment_end:]
    # Generalize the already-reviewed rain payload to cloud1/cloud2/rain3/rain4.
    em = em.replace("rain_diffusion_delta", "cloud_rain_diffusion_delta")
    em = em.replace("rain_diffusion_step", "cloud_rain_diffusion_step")
    em = _replace_once(
        em,
        "p_qnr, tiedtkescheme",
        "p_qnr, p_qnc, tiedtkescheme",
        "P_QNC import",
    )
    em = _replace_once(
        em,
        "cloud_rain_diffusion_delta(ims:ime,kms:kme,jms:jme,2)",
        "cloud_rain_diffusion_delta(ims:ime,kms:kme,jms:jme,4)",
        "four-channel rk_scalar_tend dummy",
    )
    selector_old = (
        "           IF (moist_step .AND. im == P_QR) THEN\n"
        "             pr87_capture_rain_diffusion = .TRUE.\n"
        "             pr87_diff_channel = 1\n"
        "           ELSE IF (.NOT. moist_step .AND. im == P_QNR) THEN\n"
        "             pr87_capture_rain_diffusion = .TRUE.\n"
        "             pr87_diff_channel = 2\n"
        "           END IF\n"
    )
    selector_new = (
        "           IF (moist_step .AND. im == P_QC) THEN\n"
        "             pr87_capture_rain_diffusion = .TRUE.\n"
        "             pr87_diff_channel = 1\n"
        "           ELSE IF (.NOT. moist_step .AND. im == P_QNC) THEN\n"
        "             pr87_capture_rain_diffusion = .TRUE.\n"
        "             pr87_diff_channel = 2\n"
        "           ELSE IF (moist_step .AND. im == P_QR) THEN\n"
        "             pr87_capture_rain_diffusion = .TRUE.\n"
        "             pr87_diff_channel = 3\n"
        "           ELSE IF (.NOT. moist_step .AND. im == P_QNR) THEN\n"
        "             pr87_capture_rain_diffusion = .TRUE.\n"
        "             pr87_diff_channel = 4\n"
        "           END IF\n"
    )
    em = _replace_once(em, selector_old, selector_new, "cloud/rain diffusion channel mapping")

    # Capture a single failing cloud cell around the original R32 call. The
    # trace is observational; it does not alter the call, its bounds, or data.
    call_start = em.find("CALL horizontal_diffusion ( 'm'")
    if call_start < 0 or em.count("CALL horizontal_diffusion ( 'm'") != 1:
        raise ValueError("expected the single pinned scalar 'm' diffusion call")
    guard_start = em.rfind("IF (.not. mix2_off) THEN", 0, call_start)
    if guard_start < 0:
        raise ValueError("missing enclosing mix2_off guard")
    call_start, call_after, call_text = _call_span(em, "horizontal_diffusion", call_start)
    if "scalar_tends(ims,kms,jms,im)" not in call_text:
        raise ValueError("scalar diffusion call signature changed")
    record_values = [
        "dt_step, khdq,",
        "scalar_tends(90,11,14,im), scalar(90,11,14,im),",
        "scalar(89,11,14,im), scalar(91,11,14,im),",
        "scalar(90,11,13,im), scalar(90,11,15,im),",
        "mut(90,14), mut(89,14), mut(91,14), mut(90,13), mut(90,15),",
        "c1h(11), c2h(11),",
        "xkmhd(90,11,14), xkmhd(89,11,14), xkmhd(91,11,14),",
        "xkmhd(90,11,13), xkmhd(90,11,15),",
        "msfux(89,14), msfux(90,14), msfux(91,14),",
        "msfuy(89,14), msfuy(90,14), msfuy(91,14),",
        "msfvx_inv(90,14), msfvx_inv(90,15), msfvy(90,14), msfvy(90,15),",
        "msftx(90,14), msfty(90,14), rdx, rdy",
    ]
    lines = " &\n".join(f"                 {value}" for value in record_values)
    trace_pre = (
        "           IF (rk_step == 1 .AND. config_flags%mp_physics == 37 .AND. &\n"
        "               config_flags%diff_opt == 1 .AND. &\n"
        "               (im == P_QC .OR. im == P_QNC) .AND. &\n"
        "               90 >= its .AND. 90 <= ite .AND. 14 >= jts .AND. 14 <= jte .AND. &\n"
        "               11 >= kts .AND. 11 <= kte .AND. 90 > ims .AND. 91 < ime .AND. &\n"
        "               14 > jms .AND. 15 < jme) THEN\n"
        "             WRITE(*,'(A,1X,5(I0,1X),2(L1,1X),*(1X,ES25.17E3))') &\n"
        "                 'PR87_CLOUD_DIFFUSION_PRE', rk_step, im, 90, 14, 11, &\n"
        "                 moist_step, mix2_off, &\n" + lines + "\n"
        "           END IF\n"
    )
    trace_post = trace_pre.replace("_PRE'", "_POST'")
    em = em[:call_start] + trace_pre + em[call_start:call_after] + "\n" + trace_post + em[call_after:]
    return em.replace(marker, embedded_fragment, 1)


def _instrument_solve(solve: str) -> str:
    solve = solve.replace("rain_diffusion_delta", "cloud_rain_diffusion_delta")
    solve = solve.replace("rain_diffusion_step", "cloud_rain_diffusion_step")
    solve = _replace_once(
        solve,
        "pr87_cloud_rain_diffusion_delta(ims:ime,kms:kme,jms:jme,2))",
        "pr87_cloud_rain_diffusion_delta(ims:ime,kms:kme,jms:jme,4))",
        "four-channel solve allocation",
    )
    return solve


def _instrument_fragment(fragment: str) -> str:
    fragment = fragment.replace("rain_diffusion_delta", "cloud_rain_diffusion_delta")
    fragment = fragment.replace("rain_diffusion_step", "cloud_rain_diffusion_step")
    fragment = _replace_once(
        fragment,
        "pr87_cloud_rain_diffusion_delta(ims:ime,kms:kme,jms:jme,2)",
        "pr87_cloud_rain_diffusion_delta(ims:ime,kms:kme,jms:jme,4)",
        "four-channel fragment dummy",
    )
    fragment = _replace_once(
        fragment,
        "diffusion_delta_sum(2),diffusion_delta_l1(2),diffusion_delta_max(2)",
        "diffusion_delta_sum(4),diffusion_delta_l1(4),diffusion_delta_max(4)",
        "four-channel budget arrays",
    )
    old = (
        "      IF (p==3.AND.PRESENT(pr87_cloud_rain_diffusion_delta)) THEN\n"
        "        IF (.NOT.ALL(ieee_is_finite(pr87_cloud_rain_diffusion_delta(i,k,j,:)))) &\n"
        "          CALL wrf_error_fatal('PR87 nonfinite rain diffusion correction')\n"
        "        qs64(cell,p)=qs64(cell,p)+pr87_cloud_rain_diffusion_delta(i,k,j,1)\n"
        "        ns64(cell,p)=ns64(cell,p)+pr87_cloud_rain_diffusion_delta(i,k,j,2)\n"
        "        diffusion_delta_sum=diffusion_delta_sum+REAL(dt,real64)* &\n"
        "             pr87_cloud_rain_diffusion_delta(i,k,j,:)\n"
        "        diffusion_delta_l1=diffusion_delta_l1+REAL(dt,real64)* &\n"
        "             ABS(pr87_cloud_rain_diffusion_delta(i,k,j,:))\n"
        "        diffusion_delta_max=MAX(diffusion_delta_max,REAL(dt,real64)* &\n"
        "             ABS(pr87_cloud_rain_diffusion_delta(i,k,j,:)))\n"
        "      END IF\n"
    )
    new = (
        "      IF ((p==1.OR.p==3).AND.PRESENT(pr87_cloud_rain_diffusion_delta)) THEN\n"
        "        IF (.NOT.ALL(ieee_is_finite(pr87_cloud_rain_diffusion_delta(i,k,j,:)))) &\n"
        "          CALL wrf_error_fatal('PR87 nonfinite cloud/rain diffusion correction')\n"
        "        IF (p==1) THEN\n"
        "          qs64(cell,p)=qs64(cell,p)+pr87_cloud_rain_diffusion_delta(i,k,j,1)\n"
        "          ns64(cell,p)=ns64(cell,p)+pr87_cloud_rain_diffusion_delta(i,k,j,2)\n"
        "        ELSE\n"
        "          qs64(cell,p)=qs64(cell,p)+pr87_cloud_rain_diffusion_delta(i,k,j,3)\n"
        "          ns64(cell,p)=ns64(cell,p)+pr87_cloud_rain_diffusion_delta(i,k,j,4)\n"
        "        END IF\n"
        "      END IF\n"
    )
    fragment = _replace_once(fragment, old, new, "cloud and rain source channels")

    # The source-first path replaces qs64 after the initial p=1 addition.
    # Reapply cloud channels there, after the later non-air rates are restored.
    later_anchor = (
        "        qs64(cell,p)=pr87_later_qsrc(i,k,j,p)\n"
        "        ns64(cell,p)=pr87_later_nsrc(i,k,j,p)\n"
    )
    later_update = later_anchor + (
        "        IF (p==1.AND.PRESENT(pr87_cloud_rain_diffusion_delta)) THEN\n"
        "          IF (.NOT.ALL(ieee_is_finite(pr87_cloud_rain_diffusion_delta(i,k,j,1:2)))) &\n"
        "            CALL wrf_error_fatal('PR87 nonfinite cloud diffusion correction')\n"
        "          qs64(cell,p)=qs64(cell,p)+pr87_cloud_rain_diffusion_delta(i,k,j,1)\n"
        "          ns64(cell,p)=ns64(cell,p)+pr87_cloud_rain_diffusion_delta(i,k,j,2)\n"
        "        END IF\n"
    )
    fragment = _replace_once(fragment, later_anchor, later_update, "source-first cloud correction")

    # Report each of the four channel deltas once after any source-first reset.
    budget_anchor = "  IF (PRESENT(pr87_cloud_rain_diffusion_delta)) THEN\n    OPEN(NEWUNIT=u,FILE='pr87_rain_diffusion_precision.raw'"
    if fragment.count(budget_anchor) != 1:
        raise ValueError("missing unique diffusion ledger output")
    aggregate = (
        "  IF (PRESENT(pr87_cloud_rain_diffusion_delta)) THEN\n"
        "    diffusion_delta_sum=0.0_real64\n"
        "    diffusion_delta_l1=0.0_real64\n"
        "    diffusion_delta_max=0.0_real64\n"
        "    DO j=jl,jh\n"
        "      DO k=kl,kh\n"
        "        DO i=il,ih\n"
        "          diffusion_delta_sum=diffusion_delta_sum+REAL(dt,real64)* &\n"
        "               pr87_cloud_rain_diffusion_delta(i,k,j,:)\n"
        "          diffusion_delta_l1=diffusion_delta_l1+REAL(dt,real64)* &\n"
        "               ABS(pr87_cloud_rain_diffusion_delta(i,k,j,:))\n"
        "          diffusion_delta_max=MAX(diffusion_delta_max,REAL(dt,real64)* &\n"
        "               ABS(pr87_cloud_rain_diffusion_delta(i,k,j,:)))\n"
        "        END DO\n"
        "      END DO\n"
        "    END DO\n"
        "    OPEN(NEWUNIT=u,FILE='pr87_qn_diffusion_precision.raw'"
    )
    fragment = _replace_once(fragment, budget_anchor, aggregate, "post-fallback diffusion ledger")
    fragment = _replace_once(
        fragment,
        "WRITE(u,*) 'RAIN_DIFFUSION_RK_CORRECTION',itimestep,rk,cells",
        "WRITE(u,*) 'QN_DIFFUSION_RK_CORRECTION',itimestep,rk,cells",
        "cloud/rain diffusion ledger tag",
    )
    return fragment


def extend_cloud_diffusion_precision(sources: Mapping[str, str]) -> dict[str, str]:
    """Return the pinned four-channel cloud/rain diffusion overlay."""
    em, solve, fragment = sources["em"], sources["solve"], sources["fragment"]
    helper = sources.get("helper")
    if helper is None:
        helper = Path(__file__).with_name("pr87_horizontal_diffusion64.f90").read_text()
    _require_pins(em, solve, fragment, helper)
    updated_fragment = _instrument_fragment(fragment)
    updated_em = _instrument_em(em, helper)
    if updated_em.count(fragment) != 1:
        raise ValueError("pinned native fragment must occur exactly once in module_em")
    updated_em = updated_em.replace(fragment, updated_fragment, 1)
    updated_solve = _instrument_solve(solve)
    return {"em": updated_em, "solve": updated_solve, "fragment": updated_fragment}
