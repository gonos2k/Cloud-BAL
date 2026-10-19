from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from pr87_pbl_source_probe import (  # noqa: E402
    _instrument_part2,
    _instrument_shinhong,
    extend_pbl_source_probe,
)


SHINHONG = """SUBROUTINE shinhong2d
   real(kind=8) :: pr85_minmass64,pr85_maxmass64
         call pr85_tridin64(kts,kte,pr85_lo64,pr85_diag64,pr85_up64, &
                            pr85_rhs64,pr85_sol64(:,pr85_member), &
                            pr85_cp64,pr85_dp64,pr85_den64)
       enddo
       do k=kts,kte
         if(qx(i,k+(pr85_qchannel-1)*kte).ne.0. .or. &
END SUBROUTINE shinhong2d
"""


PART2 = """SUBROUTINE first_rk_step_part2
        pr87_shadow_ph = ph_tendf
        pr87_shadow_t = t_tendf
        DO j = grid%j_start(ij), grid%j_end(ij)
          DO k = k_start, MIN(k_end,kde-1)
            DO i = grid%i_start(ij), grid%i_end(ij)
              pr87_raw_qsrc(i,k,j,1) = moist_tend(i,k,j,P_QC)
              pr87_source_carrier(i,k,j) = grid%c1h(k)*grid%mut(i,j)+grid%c2h(k)
            END DO
          END DO
        END DO
        END IF
CALL calculate_phy_tend (config_flags)
           pr87_source_step = grid%itimestep
         END IF
END SUBROUTINE first_rk_step_part2
"""


def test_shinhong_trace_uses_private_replay_and_precedes_zero_base_gate() -> None:
    transformed = _instrument_shinhong(SHINHONG)
    assert "pr87_diag_sol64(kts:kte,2)" in transformed
    assert transformed.count("call pr85_tridin64") == 2
    assert transformed.index("PR87_SHINHONG_PBL_ROW") < transformed.index(
        "if(qx(i,k+(pr85_qchannel-1)*kte).ne.0."
    )
    for operand in (
        "real(al(i,pr87_diag_k-1),8)",
        "real(ad(i,pr87_diag_k),8)",
        "real(cu(i,pr87_diag_k),8)",
        "if(kts.le.11 .and. 11.le.kte)",
        "do pr87_diag_k=kts,kte",
        "r3(i,pr87_diag_k,pr87_diag_channel)",
        "qx(i,pr87_diag_k+(pr85_qchannel-1)*kte)",
        "pr87_diag_sol64(pr87_diag_k,1)",
        "f3(i,pr87_diag_k,pr85_qchannel)",
        "pr87_cloud_target_call,j,i, &\n                  pr87_diag_k",
    ):
        assert operand in transformed


def test_first_rk_trace_records_premix_raw_and_coupled_source() -> None:
    transformed = _instrument_part2(PART2)
    for tag in (
        "PR87_PBL_SOURCE_PRE",
        "PR87_PBL_SOURCE_RAW",
        "PR87_PBL_SOURCE_COUPLED",
    ):
        assert transformed.count(tag) == 1
        assert transformed.index(tag) < transformed.index("END SUBROUTINE")
    assert transformed.index("PR87_PBL_SOURCE_PRE") < transformed.index("pr87_shadow_ph =")
    assert transformed.index("PR87_PBL_SOURCE_RAW") < transformed.index("CALL calculate_phy_tend")
    assert transformed.index("PR87_PBL_SOURCE_COUPLED") < transformed.index("END SUBROUTINE")
    assert "grid%itimestep,rk_step,90,14,11,grid%dt" in transformed
    assert "pr87_coupled_qsrc(90,11,14,1)" in transformed
    assert "pr87_coupled_nsrc(90,11,14,1)" in transformed


def test_source_transform_rejects_unpinned_inputs_and_anchor_drift() -> None:
    with pytest.raises(ValueError, match="expected one Shinhong replay insertion"):
        _instrument_shinhong(SHINHONG.replace("call pr85_tridin64", "call changed_solver"))
    with pytest.raises(ValueError, match="expected one first RK raw-source trace"):
        _instrument_part2(PART2.replace("CALL calculate_phy_tend", "CALL other_tend"))
    with pytest.raises(ValueError, match="source SHA-256 mismatch"):
        extend_pbl_source_probe({"shinhong": SHINHONG, "part2": PART2})
