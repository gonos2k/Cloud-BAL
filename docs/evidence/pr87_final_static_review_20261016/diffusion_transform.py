"""Extend the pinned REAL64 diffusion correction to all four Q/N pairs."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from pathlib import Path

from pr87_rain_diffusion_precision import _unique_replace


PINNED_SHA256 = {
    "em": "9011e9da4c341b60906fa8163290ef3b41b493f21bff547acc4c41b6bfb1333f",
    "solve": "2f6c3290f9888308f5e5b1f99f051c01ad7f30b49612adb083d6dc6fa5bc82bd",
    "fragment": "66f5309e613997b219de44dac4cf2beaa54b4742ee38523b91c095a6eec5024d",
}
HELPER_SHA256 = "0a8b2865fff3d7ad6592e0d1bc1d3f7b51970de13ac9ea128066b7cba655bfe3"
INTERMEDIATE_PRECISION_EM_SHA256 = "e48607da8943caaf86f53c5fc04ff5ba2a2c75e32706142c97c3f9b8fdb70c70"
_OLD = "cloud_rain_diffusion"
_NEW = "all_pair_diffusion"


def _sha256(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    return _unique_replace(source, old, new, label)


def _require_pins(sources: Mapping[str, str], helper: str) -> None:
    for name, expected in PINNED_SHA256.items():
        actual = _sha256(sources[name])
        if actual != expected:
            raise ValueError(f"{name} source SHA-256 mismatch: {actual}")
    if _sha256(helper) != HELPER_SHA256:
        raise ValueError("horizontal_diffusion64 helper SHA-256 mismatch")


def _widen_horizontal_diffusion_module(module_source: str) -> str:
    """Promote only local stencil arithmetic; preserve the R32/R64 API."""
    if _sha256(module_source) != HELPER_SHA256:
        raise ValueError("embedded horizontal_diffusion64 module SHA-256 mismatch")

    source = module_source.replace(
        "USE iso_fortran_env, ONLY: real32, real64",
        "USE iso_fortran_env, ONLY: real32, real64, real128",
        1,
    )
    source = source.replace(
        "REAL(real64),INTENT(OUT) :: increment(ims:ime,kms:kme,jms:jme)",
        "REAL(real64),INTENT(OUT) :: increment(ims:ime,kms:kme,jms:jme)\n"
        "    REAL(real128) :: increment128",
        1,
    )
    if source == module_source:
        raise ValueError("horizontal diffusion module API declaration not found")

    # Promote geometry, face weights, differences, and the local accumulation.
    # Keep input/output declarations in REAL32/REAL64 and cast the completed
    # high-precision increment explicitly at the procedure boundary.
    source = source.replace("REAL(real64) ::", "REAL(real128) ::")
    source = source.replace(",real64)", ",real128)")
    source = source.replace("0.5_real64", "0.5_real128")
    source = source.replace("increment(i,k,j)= &", "increment128= &", 1)
    expression_start = source.find("increment128= &")
    inner_loop_end = source.find("        END DO", expression_start)
    if expression_start < 0 or inner_loop_end < 0:
        raise ValueError("horizontal diffusion inner-loop expression not found")
    source = (source[:inner_loop_end]
              + "          increment(i,k,j)=REAL(increment128,real64)\n"
              + source[inner_loop_end:])
    return source


def widen_horizontal_diffusion_intermediates(source: str) -> str:
    """Widen the pinned final V39 m-diffusion helper without changing its API."""
    if _sha256(source) != INTERMEDIATE_PRECISION_EM_SHA256:
        raise ValueError(f"final module_em source SHA-256 mismatch: {_sha256(source)}")
    starts = list(re.finditer(r"^MODULE pr87_horizontal_diffusion64[ \t]*$", source, re.MULTILINE))
    if len(starts) != 1:
        raise ValueError("expected exactly one embedded horizontal_diffusion64 module")
    start = starts[0].start()
    ends = list(re.finditer(r"^END MODULE pr87_horizontal_diffusion64[ \t]*$", source, re.MULTILINE))
    if len(ends) != 1 or ends[0].start() < start:
        raise ValueError("expected exactly one horizontal_diffusion64 module terminator")
    end = ends[0].end()
    if source[end:end + 2] == "\r\n":
        end += 2
    elif source[end:end + 1] == "\n":
        end += 1
    embedded = source[start:end]
    widened = _widen_horizontal_diffusion_module(embedded)
    return source[:start] + widened + source[end:]


def _rename_and_expand(source: str) -> str:
    source = source.replace(_OLD, _NEW)
    source = source.replace(
        "all_pair_diffusion_delta(ims:ime,kms:kme,jms:jme,4)",
        "all_pair_diffusion_delta(ims:ime,kms:kme,jms:jme,8)",
    )
    source = source.replace("diffusion_delta_sum(4),diffusion_delta_l1(4),diffusion_delta_max(4)",
                            "diffusion_delta_sum(8),diffusion_delta_l1(8),diffusion_delta_max(8)")
    return source


def _instrument_em(em: str) -> str:
    em = _replace_once(em, "p_qnr, p_qnc, tiedtkescheme",
                       "p_qnr, p_qnc, p_qni, p_qib, tiedtkescheme",
                       "ice-number and bulk-volume registry imports")
    start = em.find("SUBROUTINE rk_update_joint_moments")
    end = em.find("END SUBROUTINE rk_update_joint_moments", start)
    if start < 0 or end < 0:
        raise ValueError("missing embedded native update fragment")
    end += len("END SUBROUTINE rk_update_joint_moments")
    embedded = em[start:end]
    marker = "PR87_ALL_PAIR_NATIVE_FRAGMENT_PLACEHOLDER"
    em = em[:start] + marker + em[end:]
    em = _rename_and_expand(em)
    old = (
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
    new = (
        "           IF (moist_step .AND. im == P_QC) THEN\n"
        "             pr87_capture_rain_diffusion = .TRUE.\n"
        "             pr87_diff_channel = 1\n"
        "           ELSE IF (.NOT. moist_step .AND. im == P_QNC) THEN\n"
        "             pr87_capture_rain_diffusion = .TRUE.\n"
        "             pr87_diff_channel = 2\n"
        "           ELSE IF (moist_step .AND. im == P_QI) THEN\n"
        "             pr87_capture_rain_diffusion = .TRUE.\n"
        "             pr87_diff_channel = 3\n"
        "           ELSE IF (.NOT. moist_step .AND. im == P_QNI) THEN\n"
        "             pr87_capture_rain_diffusion = .TRUE.\n"
        "             pr87_diff_channel = 4\n"
        "           ELSE IF (moist_step .AND. im == P_QR) THEN\n"
        "             pr87_capture_rain_diffusion = .TRUE.\n"
        "             pr87_diff_channel = 5\n"
        "           ELSE IF (.NOT. moist_step .AND. im == P_QNR) THEN\n"
        "             pr87_capture_rain_diffusion = .TRUE.\n"
        "             pr87_diff_channel = 6\n"
        "           ELSE IF (moist_step .AND. im == P_QG) THEN\n"
        "             pr87_capture_rain_diffusion = .TRUE.\n"
        "             pr87_diff_channel = 7\n"
        "           ELSE IF (.NOT. moist_step .AND. im == P_QIB) THEN\n"
        "             pr87_capture_rain_diffusion = .TRUE.\n"
        "             pr87_diff_channel = 8\n"
        "           END IF\n"
    )
    return _replace_once(em, old, new, "four-pair scalar/mode mapping").replace(marker, embedded, 1)


def _instrument_solve(solve: str) -> str:
    return _rename_and_expand(solve)


def _instrument_fragment(fragment: str) -> str:
    fragment = _rename_and_expand(fragment)
    fragment = fragment.replace("pr87_qn_diffusion_precision.raw",
                                "pr87_all_pair_diffusion_precision.raw")
    fragment = fragment.replace("QN_DIFFUSION_RK_CORRECTION",
                                "ALL_PAIR_DIFFUSION_RK_CORRECTION")
    fragment = fragment.replace("DT_SUM_PRESSURE_Q_N", "DT_SUM_PRESSURE_QN_CHANNELS")
    fragment = fragment.replace("DT_L1_PRESSURE_Q_N", "DT_L1_PRESSURE_QN_CHANNELS")
    fragment = fragment.replace("DT_MAXABS_PRESSURE_Q_N", "DT_MAXABS_PRESSURE_QN_CHANNELS")
    old = (
        "      IF ((p==1.OR.p==3).AND.PRESENT(pr87_all_pair_diffusion_delta)) THEN\n"
        "        IF (.NOT.ALL(ieee_is_finite(pr87_all_pair_diffusion_delta(i,k,j,:)))) &\n"
        "          CALL wrf_error_fatal('PR87 nonfinite cloud/rain diffusion correction')\n"
        "        IF (p==1) THEN\n"
        "          qs64(cell,p)=qs64(cell,p)+pr87_all_pair_diffusion_delta(i,k,j,1)\n"
        "          ns64(cell,p)=ns64(cell,p)+pr87_all_pair_diffusion_delta(i,k,j,2)\n"
        "        ELSE\n"
        "          qs64(cell,p)=qs64(cell,p)+pr87_all_pair_diffusion_delta(i,k,j,3)\n"
        "          ns64(cell,p)=ns64(cell,p)+pr87_all_pair_diffusion_delta(i,k,j,4)\n"
        "        END IF\n"
        "      END IF\n"
    )
    new = (
        "      IF (p>=1.AND.p<=4.AND.PRESENT(pr87_all_pair_diffusion_delta)) THEN\n"
        "        IF (.NOT.ALL(ieee_is_finite(pr87_all_pair_diffusion_delta(i,k,j,2*p-1:2*p)))) &\n"
        "          CALL wrf_error_fatal('PR87 nonfinite paired diffusion correction')\n"
        "        qs64(cell,p)=qs64(cell,p)+pr87_all_pair_diffusion_delta(i,k,j,2*p-1)\n"
        "        ns64(cell,p)=ns64(cell,p)+pr87_all_pair_diffusion_delta(i,k,j,2*p)\n"
        "      END IF\n"
    )
    fragment = _replace_once(fragment, old, new, "four-pair source correction")

    old_later = (
        "        IF (p==1.AND.PRESENT(pr87_all_pair_diffusion_delta)) THEN\n"
        "          IF (.NOT.ALL(ieee_is_finite(pr87_all_pair_diffusion_delta(i,k,j,1:2)))) &\n"
        "            CALL wrf_error_fatal('PR87 nonfinite cloud diffusion correction')\n"
        "          qs64(cell,p)=qs64(cell,p)+pr87_all_pair_diffusion_delta(i,k,j,1)\n"
        "          ns64(cell,p)=ns64(cell,p)+pr87_all_pair_diffusion_delta(i,k,j,2)\n"
        "        END IF\n"
    )
    new_later = (
        "        IF (p>=1.AND.p<=2.AND.PRESENT(pr87_all_pair_diffusion_delta)) THEN\n"
        "          IF (.NOT.ALL(ieee_is_finite(pr87_all_pair_diffusion_delta(i,k,j,2*p-1:2*p)))) &\n"
        "            CALL wrf_error_fatal('PR87 nonfinite later paired diffusion correction')\n"
        "          qs64(cell,p)=qs64(cell,p)+pr87_all_pair_diffusion_delta(i,k,j,2*p-1)\n"
        "          ns64(cell,p)=ns64(cell,p)+pr87_all_pair_diffusion_delta(i,k,j,2*p)\n"
        "        END IF\n"
    )
    fragment = _replace_once(fragment, old_later, new_later, "source-first pair correction")
    return fragment


def extend_all_pair_diffusion_precision(sources: Mapping[str, str]) -> dict[str, str]:
    """Return an eight-channel extension bound to the frozen post-PBL inputs."""
    helper = sources.get("helper")
    if helper is None:
        helper = Path(__file__).with_name("pr87_horizontal_diffusion64.f90").read_text()
    _require_pins(sources, helper)
    fragment = _instrument_fragment(sources["fragment"])
    em = _instrument_em(sources["em"])
    if em.count(sources["fragment"]) != 1:
        raise ValueError("pinned native fragment must occur exactly once in module_em")
    em = em.replace(sources["fragment"], fragment, 1)
    solve = _instrument_solve(sources["solve"])
    return {"em": em, "solve": solve, "fragment": fragment}
