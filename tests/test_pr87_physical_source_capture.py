from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from pr87_physical_source_capture import generate_source_capture  # noqa: E402


PART2 = """SUBROUTINE first_rk_step_part2(ims, k_start , k_end                  &
                            )
    INTEGER , INTENT(IN)                          ::  k_start, k_end
    INTEGER                             :: ij
   rk_step = 1
BENCH_START(cal_phy_tend)
CALL calculate_phy_tend(grid)
CALL update_phy_ten(ph_tendf,t_tendf,ru_tendf,rv_tendf,moist_tend,scalar_tend,mu_tendf)
       !$OMP END PARALLEL DO
BENCH_END(update_phy_ten_tim)
  END SUBROUTINE first_rk_step_part2
"""

SOLVE = """SUBROUTINE solve_em
   IMPLICIT NONE
   INTEGER                         :: ij , iteration
CALL first_rk_step_part2(grid)
CALL rk_update_joint_moments(state)
END SUBROUTINE solve_em
"""


@pytest.fixture(scope="module")
def generated() -> dict[str, str]:
    return generate_source_capture(PART2, SOLVE)


def test_clone_redirects_all_update_outputs_to_shadow_arrays(generated: dict[str, str]) -> None:
    import re

    calls = re.findall(r"CALL update_phy_ten\(([^)]*)\)", generated["part2"])
    assert len(calls) == 2
    assert calls[0] == (
        "pr87_shadow_ph,pr87_shadow_t,pr87_shadow_ru,pr87_shadow_rv,"
        "pr87_shadow_moist,pr87_shadow_scalar,pr87_shadow_mu"
    )
    assert calls[1] == "ph_tendf,t_tendf,ru_tendf,rv_tendf,moist_tend,scalar_tend,mu_tendf"


def test_captures_both_cloud_ice_mass_and_number_sources(generated: dict[str, str]) -> None:
    source = generated["part2"]
    for symbol in ("P_QC", "P_QI"):
        assert f"pr87_shadow_moist(pr87_i,pr87_k,pr87_j,{symbol})" in source
    for symbol in ("P_QNC", "P_QNI"):
        assert f"pr87_shadow_scalar(pr87_i,pr87_k,pr87_j,{symbol})" in source
    for target, field, slot in (
        ("pr87_coupled_qsrc", "moist_tend", "P_QC"),
        ("pr87_coupled_qsrc", "moist_tend", "P_QI"),
        ("pr87_coupled_nsrc", "scalar_tend", "P_QNC"),
        ("pr87_coupled_nsrc", "scalar_tend", "P_QNI"),
    ):
        assert f"{target}(:,:,:," in source
        assert f"{field}(:,:,:,{slot})" in source


def test_binds_capture_to_current_step_and_active_footprint(generated: dict[str, str]) -> None:
    part2 = generated["part2"]
    solve = generated["solve"]
    assert "pr87_source_step = grid%itimestep" in part2
    assert "pr87_source_step = -1" in part2
    assert "MAX(jds+1,grid%j_start(1))" in part2
    assert "MIN(jde-2,grid%j_end(1))" in part2
    assert "MAX(ids+1,grid%i_start(1))" in part2
    assert "MIN(ide-2,grid%i_end(1))" in part2
    assert "grid%c1h(pr87_k)*grid%mut(pr87_i,pr87_j) + grid%c2h(pr87_k)" in part2
    assert "pr87_coupled_qsrc(pr87_i,pr87_k,pr87_j,1) /= &" in part2
    assert "pr87_coupled_nsrc(pr87_i,pr87_k,pr87_j,2) /= &" in part2
    assert "pr87_source_carrier, pr87_source_step" in solve
    assert "pr87_raw_qsrc, pr87_raw_nsrc" in solve


def test_forwards_rk1_later_tendencies_as_real64_without_reweighting(
    generated: dict[str, str],
) -> None:
    solve = generated["solve"]
    assert "USE, INTRINSIC :: iso_fortran_env, ONLY: real64" in solve
    assert "REAL(real64), ALLOCATABLE :: pr87_later_qsrc(:,:,:,:), pr87_later_nsrc(:,:,:,:)" in solve
    assert "pr87_later_qsrc(ims:ime,kms:kme,jms:jme,2)" in solve
    assert "pr87_later_nsrc(ims:ime,kms:kme,jms:jme,2)" in solve
    assert "pr87_later_qsrc = 0.0_real64" in solve
    assert "pr87_later_nsrc = 0.0_real64" in solve

    consumer = solve.index("CALL rk_update_joint_moments")
    handoff = solve.index("IF (rk_step == 1) THEN", solve.index("CALL first_rk_step_part2"))
    assert handoff < consumer
    assert "IF (pr87_source_step /= grid%itimestep) THEN" in solve
    assert "post-capture horizontal diffusion, optional diabatic, and boundary additions" in solve
    assert "REAL(moist_tend(i,k,j,P_QC),real64) - &" in solve
    assert "REAL(pr87_coupled_qsrc(i,k,j,1),real64)" in solve
    assert "REAL(scalar_tend(i,k,j,P_QNI),real64) - &" in solve
    assert "pr87_coupled_qsrc(i,k,j,1) = moist_tend(i,k,j,P_QC)" in solve
    assert "pr87_coupled_nsrc(i,k,j,2) = scalar_tend(i,k,j,P_QNI)" in solve
    assert "DO j = MAX(jds+1,grid%j_start(ij)), MIN(jde-2,grid%j_end(ij))" in solve
    assert "DO k = k_start, MIN(k_end,kde-1)" in solve
    assert "DO i = MAX(ids+1,grid%i_start(ij)), MIN(ide-2,grid%i_end(ij))" in solve
    assert solve.count("IF (rk_step == 1) THEN") == 1
    assert "pr87_later_qsrc, pr87_later_nsrc)" in solve
    assert "advect_tend" not in solve
    assert "pr87_coupled_qsrc(i,k,j,1) *" not in solve

    # The unweighted source capture remains a separate part2 output.
    assert "pr87_raw_qsrc(pr87_i,pr87_k,pr87_j,1) = &" in generated["part2"]
    assert "pr87_later_qsrc" not in generated["part2"]


def test_rejects_source_drift_without_writing_partial_outputs() -> None:
    with pytest.raises(ValueError, match="expected one CALL update_phy_ten"):
        generate_source_capture(PART2.replace("CALL update_phy_ten", "CALL replaced_update"), SOLVE)
