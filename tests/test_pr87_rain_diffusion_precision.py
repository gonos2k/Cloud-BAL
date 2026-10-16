from __future__ import annotations

import gzip
import hashlib
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from pr87_rain_diffusion_precision import (  # noqa: E402
    HELPER_SHA256,
    PINNED_SHA256,
    _call_span,
    extend_rain_diffusion_precision,
)


EVIDENCE = ROOT / "docs/evidence/pr87_two_step_v16_20261016"
EM_PATH = EVIDENCE / "module_em_pr85.F.gz"
FRAGMENT_PATH = EVIDENCE / "native_update.f90.gz"
SOLVE_PATH = ROOT / "tests/fixtures/pr87_rain_diffusion_solve_v16.F.gz"
HELPER_PATH = ROOT / "tools/pr87_horizontal_diffusion64.f90"


def _read_gzip(path: Path) -> str:
    return gzip.decompress(path.read_bytes()).decode("utf-8")


@pytest.fixture(scope="module")
def sources() -> tuple[str, str, str, str]:
    return (
        _read_gzip(EM_PATH),
        _read_gzip(SOLVE_PATH),
        _read_gzip(FRAGMENT_PATH),
        HELPER_PATH.read_text(),
    )


@pytest.fixture(scope="module")
def generated(sources: tuple[str, str, str, str]) -> dict[str, str]:
    return extend_rain_diffusion_precision(*sources)


def test_generator_is_bound_to_frozen_v16_sources_and_helper(
    sources: tuple[str, str, str, str],
) -> None:
    em, solve, fragment, helper = sources
    actual = {
        "em": hashlib.sha256(em.encode()).hexdigest(),
        "solve": hashlib.sha256(solve.encode()).hexdigest(),
        "fragment": hashlib.sha256(fragment.encode()).hexdigest(),
        "helper": hashlib.sha256(helper.encode()).hexdigest(),
    }
    assert {name: PINNED_SHA256[name] for name in PINNED_SHA256} == {
        name: actual[name] for name in PINNED_SHA256
    }
    assert HELPER_SHA256 == actual["helper"]


def test_only_rain_rk1_mixing_delta_is_added_and_host_call_stays_exact(
    sources: tuple[str, str, str, str], generated: dict[str, str]
) -> None:
    em, _, old_fragment, _ = sources
    updated = generated["em"]
    assert set(generated) == {"em", "solve", "fragment"}
    assert generated["em"].count(generated["fragment"]) == 1
    assert generated["em"].count(old_fragment) == 0
    assert len(re.findall(r"^MODULE pr87_horizontal_diffusion64$", updated, re.M)) == 1
    assert "USE pr87_horizontal_diffusion64, ONLY: horizontal_diffusion64" in updated
    assert "p_qs, p_qnr, tiedtkescheme" in updated

    old_start = em.index("SUBROUTINE rk_scalar_tend")
    old_end = em.index("END SUBROUTINE rk_scalar_tend", old_start)
    old_routine = em[old_start:old_end]
    new_start = updated.index("SUBROUTINE rk_scalar_tend")
    new_end = updated.index("END SUBROUTINE rk_scalar_tend", new_start)
    new_routine = updated[new_start:new_end]
    _, _, old_call = _call_span(old_routine, "horizontal_diffusion")
    assert new_routine.count("CALL horizontal_diffusion (") == 1
    assert old_call in new_routine
    assert "IF (.not. mix2_off) THEN" in new_routine
    assert "PRESENT(rain_diffusion_delta) .AND. rk_step == 1" in new_routine
    assert "config_flags%mp_physics == 37 .AND. config_flags%diff_opt == 1 .AND. &" in new_routine
    assert ".NOT. mix2_off) THEN" in new_routine
    assert "moist_step .AND. im == P_QR" in new_routine
    assert ".NOT. moist_step .AND. im == P_QNR" in new_routine
    assert "horizontal_diffusion64(" in new_routine
    assert "rain_diffusion_delta(pr87_diff_i,pr87_diff_k,pr87_diff_j" in new_routine
    assert "REAL(pr87_rain_tendency_before(pr87_diff_i,pr87_diff_k,pr87_diff_j),real64) + &" in new_routine
    assert "REAL(scalar_tends(pr87_diff_i,pr87_diff_k,pr87_diff_j,im),real64)" in new_routine
    assert "pr87_rain_tendency_before = scalar_tends(:,:,:,im)" in new_routine


def test_delta_uses_the_host_m_stencil_support_and_no_carrier_rescaling(
    generated: dict[str, str],
) -> None:
    routine = generated["em"].split("SUBROUTINE rk_scalar_tend", 1)[1].split(
        "END SUBROUTINE rk_scalar_tend", 1
    )[0]
    for support in (
        "pr87_diff_i_start = its",
        "pr87_diff_i_end = MIN(ite,ide-1)",
        "MAX(ids+1,its)",
        "MIN(ide-2,ite)",
        "pr87_diff_j_start = jts",
        "pr87_diff_j_end = MIN(jte,jde-1)",
        "MAX(jds+1,jts)",
        "MIN(jde-2,jte)",
        "IF (config_flags%periodic_x) pr87_diff_i_start = its",
        "IF (config_flags%periodic_x) pr87_diff_i_end = MIN(ite,ide-1)",
        "pr87_diff_k_end = MIN(kte,kde-1)",
    ):
        assert support in routine
    assert "grid%mut" not in routine
    assert "rain_diffusion_delta" in generated["solve"]
    assert "pr87_source_carrier" not in generated["em"].split(
        "SUBROUTINE rk_scalar_tend", 1
    )[1].split("END SUBROUTINE rk_scalar_tend", 1)[0]


def test_solve_initializes_once_per_timestep_and_forwards_all_stages(
    generated: dict[str, str],
) -> None:
    solve = generated["solve"]
    initialize = solve.index("pr87_rain_diffusion_delta = 0.0_real64")
    part2 = solve.index("CALL first_rk_step_part2")
    assert initialize < part2
    assert "IF (config_flags%mp_physics == 37 .AND. rk_step == 1) THEN" in solve[:initialize]
    allocation = solve.index("pr87_rain_diffusion_delta(ims:ime,kms:kme,jms:jme,2))")
    assert allocation < initialize

    calls = []
    for match in re.finditer(r"\bCALL\s+rk_scalar_tend\b", solve):
        _, _, call = _call_span(solve, "rk_scalar_tend", match.start())
        calls.append(call)
    assert len(calls) >= 2
    assert sum("rain_diffusion_delta=pr87_rain_diffusion_delta" in call for call in calls) == 2
    assert any("moist_old(ims,kms,jms,im)" in call for call in calls)
    assert any("scalar_old(ims,kms,jms,is)" in call for call in calls)
    assert "pr87_rain_diffusion_delta, pr87_rain_diffusion_step" in solve


def test_native_correction_is_current_step_finite_and_rain_only(
    generated: dict[str, str],
) -> None:
    fragment = generated["fragment"]
    assert "PRESENT(pr87_rain_diffusion_delta) .NEQV." in fragment
    assert "pr87_rain_diffusion_step /= itimestep" in fragment
    assert "IF (p==3.AND.PRESENT(pr87_rain_diffusion_delta)) THEN" in fragment
    assert "ALL(ieee_is_finite(pr87_rain_diffusion_delta(i,k,j,:)))" in fragment
    assert "qs64(cell,p)=qs64(cell,p)+pr87_rain_diffusion_delta(i,k,j,1)" in fragment
    assert "ns64(cell,p)=ns64(cell,p)+pr87_rain_diffusion_delta(i,k,j,2)" in fragment
    assert "diffusion_delta_sum(2),diffusion_delta_l1(2),diffusion_delta_max(2)" in fragment
    assert "DT_SUM_PRESSURE_Q_N" in fragment
    assert "DT_L1_PRESSURE_Q_N" in fragment
    assert "DT_MAXABS_PRESSURE_Q_N" in fragment
    assert "rain_diffusion_delta(i,k,j,1)" not in fragment.split("IF (p==3.AND.", 1)[0]


def test_frozen_source_or_helper_drift_is_rejected_without_partial_output(
    sources: tuple[str, str, str, str],
) -> None:
    em, solve, fragment, helper = sources
    with pytest.raises(ValueError, match="solve source SHA-256 mismatch"):
        extend_rain_diffusion_precision(em, solve + "!", fragment, helper)
    with pytest.raises(ValueError, match="helper source SHA-256 mismatch"):
        extend_rain_diffusion_precision(em, solve, fragment, helper + "!\n")
    with pytest.raises(ValueError, match="em source SHA-256 mismatch"):
        extend_rain_diffusion_precision(em.replace("module cloud_bal_joint_transport", "! drift\nmodule cloud_bal_joint_transport", 1),
                                       solve, fragment, helper)
    with pytest.raises(ValueError, match="em source SHA-256 mismatch"):
        extend_rain_diffusion_precision(em + "! host drift\n", solve, fragment, helper)
