"""Insert the rain public-storage repair at completed KDM6 RK stages."""
from __future__ import annotations

import hashlib


V19_SOLVE_SHA256 = "bbc03db993ca1cab9c56dfe7f31bc6b7c791e3f6c285c1643b557493282dbf87"


def _replace_once(source: str, old: str, new: str) -> str:
    count = source.count(old)
    if count != 1:
        raise ValueError(f"expected one source anchor, found {count}: {old[:80]!r}")
    return source.replace(old, new, 1)


def extend_rain_density_storage(solve_text: str) -> str:
    """Check and repair tile rain Q against post-RK AL+ALB density."""
    if hashlib.sha256(solve_text.encode()).hexdigest() != V19_SOLVE_SHA256:
        raise ValueError("solve_em preimage differs from frozen V19")

    source = _replace_once(
        solve_text,
        "   EXTERNAL :: pr85_joint_stage_dump\n",
        "   EXTERNAL :: pr85_joint_stage_dump,pr87_rain_density_store\n"
        "   LOGICAL :: pr87_rain_density_valid\n",
    )
    anchor = "         CALL pr85_joint_stage_dump('RK_STAGE_END', grid%itimestep, rk_step, &\n"
    insertion = (
        "         ! Recheck public rain storage using density after this RK stage.\n"
        "         CALL pr87_rain_density_store(grid%itimestep,rk_step, &\n"
        "              ims,ime,kms,kme,jms,jme, &\n"
        "              max(ids+1,grid%i_start(ij)),min(ide-2,grid%i_end(ij)), &\n"
        "              max(jds+1,grid%j_start(ij)),min(jde-2,grid%j_end(ij)), &\n"
        "              k_start,min(k_end,kde-1),grid%al,grid%alb, &\n"
        "              moist(ims,kms,jms,P_QR),scalar(ims,kms,jms,P_QNR), &\n"
        "              12566.37109375,3.0,961.0,35000.0,pr87_rain_density_valid)\n"
        "         IF (.NOT.pr87_rain_density_valid) &\n"
        "           CALL wrf_error_fatal('PR87 rain density storage transaction rejected')\n"
    )
    return _replace_once(source, anchor, insertion + anchor)
