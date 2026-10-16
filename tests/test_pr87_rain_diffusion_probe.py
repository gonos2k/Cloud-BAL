from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from pr87_rain_diffusion_probe import (  # noqa: E402
    _instrument_source,
    add_rain_diffusion_probe,
)


SOURCE = """MODULE module_em
   USE module_state_description, only: param_first_scalar, p_qr, p_qv, p_qc, p_qg, p_qi, p_qs, tiedtkescheme,ntiedtkescheme, heldsuarez, &
        positivedef, gdscheme
SUBROUTINE rk_scalar_tend
       rk_step_1: IF( rk_step == 1 ) THEN
       diff_opt1 : IF (config_flags%diff_opt .eq. 1) THEN
         IF (.not. mix2_off)                                                   &
           CALL horizontal_diffusion ( 'm', scalar(ims,kms,jms,im),            &
                                            scalar_tends(ims,kms,jms,im), mut, &
                                            c1h, c2h, config_flags,            &
                                            msfux, msfuy, msfvx, msfvx_inv,    &
                                            msfvy, msftx, msfty,               &
                                            khdq , xkmhd, rdx, rdy,            &
                                            ids, ide, jds, jde, kds, kde,      &
                                            ims, ime, jms, jme, kms, kme,      &
                                            its, ite, jts, jte, kts, kte      )
       END IF diff_opt1
       END IF rk_step_1
END SUBROUTINE rk_scalar_tend
END MODULE module_em
"""


def test_traces_selected_pair_around_the_original_producer_call() -> None:
    transformed = _instrument_source(SOURCE)
    assert "p_qr, p_qnr, p_qv" in transformed
    assert transformed.count("CALL horizontal_diffusion") == 1
    assert "PR87_RAIN_DIFFUSION_PRE" in transformed
    assert "PR87_RAIN_DIFFUSION_POST" in transformed
    assert transformed.index("PR87_RAIN_DIFFUSION_PRE") < transformed.index(
        "CALL horizontal_diffusion"
    ) < transformed.index("PR87_RAIN_DIFFUSION_POST")
    for expression in (
        "scalar(110,18,5,im)",
        "scalar_tends(110,18,5,im)",
        "scalar(109,18,5,im)",
        "scalar(111,18,5,im)",
        "scalar(110,18,4,im)",
        "scalar(110,18,6,im)",
        "mut(110,5)",
        "c1h(18)",
        "c2h(18)",
        "xkmhd(110,18,5)",
        "msfux(110,5)",
        "msfuy(110,5)",
        "msfvx_inv(110,6)",
        "msfvy(110,6)",
        "msftx(110,5)",
        "msfty(110,5)",
        "rdx, rdy",
        "moist_step, mix2_off",
    ):
        assert expression in transformed


def test_rejects_source_drift_before_returning_partial_source() -> None:
    with pytest.raises(ValueError, match="expected one mix2_off"):
        _instrument_source(SOURCE.replace("mix2_off", "mix_disabled"))

    with pytest.raises(ValueError, match="diffusion call no longer matches"):
        _instrument_source(SOURCE.replace("'m'", "'q'"))

    with pytest.raises(ValueError, match="hash-pinned V16"):
        add_rain_diffusion_probe(SOURCE)
