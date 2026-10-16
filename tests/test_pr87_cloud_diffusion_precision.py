from __future__ import annotations

import gzip
import hashlib
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from pr87_cloud_diffusion_precision import (  # noqa: E402
    EM_BODY_SHA256,
    EM_KERNEL_SHA256S,
    HELPER_SHA256,
    PINNED_SHA256,
    extend_cloud_diffusion_precision,
)
from pr87_rain_diffusion_precision import _call_span  # noqa: E402


FIXTURE = ROOT / "tests/fixtures/pr87_cloud_diffusion_v24g_pre2"
HELPER = ROOT / "tools/pr87_horizontal_diffusion64.f90"


def _read_source(name: str) -> str:
    return gzip.decompress((FIXTURE / f"{name}.gz").read_bytes()).decode("utf-8")


@pytest.fixture(scope="module")
def sources() -> dict[str, str]:
    return {
        "em": _read_source("module_em_pr85.F"),
        "solve": _read_source("solve_em.F"),
        "fragment": _read_source("native_update.f90"),
        "helper": HELPER.read_text(encoding="utf-8"),
    }


@pytest.fixture(scope="module")
def generated(sources: dict[str, str]) -> dict[str, str]:
    return extend_cloud_diffusion_precision(sources)


def test_transform_is_bound_to_post_g_frozen_sources(sources: dict[str, str]) -> None:
    actual = {
        "em": hashlib.sha256(sources["em"].encode()).hexdigest(),
        "solve": hashlib.sha256(sources["solve"].encode()).hexdigest(),
        "fragment": hashlib.sha256(sources["fragment"].encode()).hexdigest(),
    }
    assert actual == PINNED_SHA256
    assert hashlib.sha256(sources["helper"].encode()).hexdigest() == HELPER_SHA256
    prefix, body = sources["em"].split("!WRF:MODEL_LAYER:DYNAMICS", 1)
    assert hashlib.sha256((prefix.strip() + "\n").encode()).hexdigest() in EM_KERNEL_SHA256S
    assert hashlib.sha256(("!WRF:MODEL_LAYER:DYNAMICS" + body).encode()).hexdigest() == EM_BODY_SHA256


def test_four_channels_preserve_host_call_and_share_rk_timestep(
    sources: dict[str, str], generated: dict[str, str]
) -> None:
    assert set(generated) == {"em", "solve", "fragment"}
    em = generated["em"]
    old_routine = sources["em"].split("SUBROUTINE rk_scalar_tend", 1)[1].split(
        "END SUBROUTINE rk_scalar_tend", 1
    )[0]
    new_routine = em.split("SUBROUTINE rk_scalar_tend", 1)[1].split(
        "END SUBROUTINE rk_scalar_tend", 1
    )[0]
    _, _, old_call = _call_span(old_routine, "horizontal_diffusion")
    assert new_routine.count("CALL horizontal_diffusion (") == 1
    assert old_call in new_routine
    assert re.search(r"\bkte\s+\)\s*\n\s*IF \(rk_step == 1", new_routine)
    assert "PRESENT(cloud_rain_diffusion_delta) .AND. rk_step == 1" in new_routine
    assert "config_flags%mp_physics == 37 .AND. config_flags%diff_opt == 1 .AND. &" in new_routine
    assert "moist_step .AND. im == P_QC" in new_routine
    assert ".NOT. moist_step .AND. im == P_QNC" in new_routine
    assert "moist_step .AND. im == P_QR" in new_routine
    assert ".NOT. moist_step .AND. im == P_QNR" in new_routine
    assert "pr87_diff_channel = 1" in new_routine
    assert "pr87_diff_channel = 2" in new_routine
    assert "pr87_diff_channel = 3" in new_routine
    assert "pr87_diff_channel = 4" in new_routine
    assert "cloud_rain_diffusion_delta(ims:ime,kms:kme,jms:jme,4)" in new_routine
    assert new_routine.count("CALL horizontal_diffusion64(") == 1

    solve = generated["solve"]
    assert "pr87_cloud_rain_diffusion_delta(ims:ime,kms:kme,jms:jme,4)" in solve
    calls = []
    for match in re.finditer(r"\bCALL\s+rk_scalar_tend\b", solve):
        _, _, call = _call_span(solve, "rk_scalar_tend", match.start())
        calls.append(call)
    assert len(calls) >= 2
    assert sum("cloud_rain_diffusion_delta=pr87_cloud_rain_diffusion_delta" in call for call in calls) == 2
    assert "pr87_cloud_rain_diffusion_delta = 0.0_real64" in solve
    assert "pr87_cloud_rain_diffusion_step = grid%itimestep" in solve
    assert "pr87_cloud_rain_diffusion_delta, pr87_cloud_rain_diffusion_step" in solve


def test_native_mapping_fallback_and_sparse_cloud_trace(
    sources: dict[str, str], generated: dict[str, str]
) -> None:
    fragment = generated["fragment"]
    assert "pr87_cloud_rain_diffusion_delta(ims:ime,kms:kme,jms:jme,4)" in fragment
    assert "IF ((p==1.OR.p==3).AND.PRESENT(pr87_cloud_rain_diffusion_delta)) THEN" in fragment
    assert "p==1) THEN" in fragment
    assert "pr87_cloud_rain_diffusion_delta(i,k,j,1)" in fragment
    assert "pr87_cloud_rain_diffusion_delta(i,k,j,2)" in fragment
    assert "pr87_cloud_rain_diffusion_delta(i,k,j,3)" in fragment
    assert "pr87_cloud_rain_diffusion_delta(i,k,j,4)" in fragment
    later = fragment.index("qs64(cell,p)=pr87_later_qsrc(i,k,j,p)")
    cloud_restore = fragment.index("IF (p==1.AND.PRESENT(pr87_cloud_rain_diffusion_delta))", later)
    source_check = fragment.index("source_sum64=(REAL(oldcarrier(cell),real64)", later)
    assert later < cloud_restore < source_check
    assert "diffusion_delta_sum(4),diffusion_delta_l1(4),diffusion_delta_max(4)" in fragment
    assert "pr87_qn_diffusion_precision.raw" in fragment

    em = generated["em"]
    assert em.count("'PR87_CLOUD_DIFFUSION_PRE'") == 1
    assert em.count("'PR87_CLOUD_DIFFUSION_POST'") == 1
    assert "(im == P_QC .OR. im == P_QNC)" in em
    assert "90 >= its .AND. 90 <= ite .AND. 14 >= jts .AND. 14 <= jte .AND. &" in em
    assert "11 >= kts .AND. 11 <= kte .AND. 90 > ims .AND. 91 < ime .AND. &" in em
    assert "scalar_tends(90,11,14,im), scalar(90,11,14,im)" in em
    assert "xkmhd(90,11,14), xkmhd(89,11,14), xkmhd(91,11,14)" in em
    assert "xkmhd(90,11,13), xkmhd(90,11,15)" in em
    assert "scalar(90,11,13,im), scalar(90,11,15,im)" in em
    assert "mut(90,14), mut(89,14), mut(91,14), mut(90,13), mut(90,15)" in em
    assert "pr87_native_update_fragment" not in em


def test_pin_mismatch_fails_before_returning_partial_sources(sources: dict[str, str]) -> None:
    with pytest.raises(ValueError, match="solve source SHA-256 mismatch"):
        extend_cloud_diffusion_precision({**sources, "solve": sources["solve"] + "! drift\n"})
    with pytest.raises(ValueError, match="horizontal_diffusion64 helper SHA-256 mismatch"):
        extend_cloud_diffusion_precision({**sources, "helper": sources["helper"] + "! drift\n"})
