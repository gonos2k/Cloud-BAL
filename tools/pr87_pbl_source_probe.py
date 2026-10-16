"""Add read-only diagnostics for the selected Shinhong cloud source.

The transform is pinned to the V24c source pair.  It writes the common PBL
matrix row, input states, preserved RHS, an independent REAL64 replay, and the
REAL32 tendency at one cell.  A second trace follows that cell through the
existing source weighting/coupling in first_rk_step_part2.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping


PINNED_SHA256 = {
    "shinhong": "a1895b765d4768208ed3b642d814fb41690c8325e78fd22a86e08f0a08ae8ed9",
    "part2": "007fcce0cdc51cf18c2d8c33de42ec1367c3419e3c2c38770ecf7be8800b44c8",
}

_DECLARATION_ANCHOR = (
    "   real(kind=8) :: pr85_minmass64,pr85_maxmass64\n"
)
_REPLAY_ANCHOR = (
    "         call pr85_tridin64(kts,kte,pr85_lo64,pr85_diag64,pr85_up64, &\n"
    "                            pr85_rhs64,pr85_sol64(:,pr85_member), &\n"
    "                            pr85_cp64,pr85_dp64,pr85_den64)\n"
    "       enddo\n"
    "       do k=kts,kte\n"
)
_PART2_PRE_ANCHOR = (
    "        pr87_shadow_ph = ph_tendf\n"
    "        pr87_shadow_t = t_tendf\n"
)
_PART2_RAW_ANCHOR = (
    "          END DO\n"
    "        END DO\n"
    "        END IF\n"
    "CALL calculate_phy_tend"
)
_PART2_COUPLED_ANCHOR = (
    "           pr87_source_step = grid%itimestep\n"
    "         END IF\n"
)


def _sha256(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise ValueError(f"expected one {label} anchor, found {count}")
    return source.replace(old, new, 1)


def _instrument_shinhong(source: str) -> str:
    declarations = (
        _DECLARATION_ANCHOR
        + "   integer, save :: pr87_cloud_target_call = 0\n"
        + "   integer :: pr87_diag_k,pr87_diag_member,pr87_diag_channel\n"
        + "   real(kind=8) :: pr87_diag_lo64(kts:kte),pr87_diag_diag64(kts:kte)\n"
        + "   real(kind=8) :: pr87_diag_up64(kts:kte),pr87_diag_rhs64(kts:kte)\n"
        + "   real(kind=8) :: pr87_diag_sol64(kts:kte,2)\n"
        + "   real(kind=8) :: pr87_diag_cp64(kts:kte),pr87_diag_dp64(kts:kte)\n"
        + "   real(kind=8) :: pr87_diag_den64\n"
    )
    source = _replace_once(source, _DECLARATION_ANCHOR, declarations, "Shinhong diagnostic declaration")

    diagnostic = """       if (pr85_pair.eq.1 .and. i.eq.90 .and. j.eq.14) then
         pr87_cloud_target_call = pr87_cloud_target_call + 1
         do pr87_diag_k=kts,kte
           pr87_diag_lo64(pr87_diag_k)=0.d0
           if(pr87_diag_k.gt.kts) &
             pr87_diag_lo64(pr87_diag_k)=real(al(i,pr87_diag_k-1),8)
           pr87_diag_diag64(pr87_diag_k)=real(ad(i,pr87_diag_k),8)
           pr87_diag_up64(pr87_diag_k)=real(cu(i,pr87_diag_k),8)
         enddo
         do pr87_diag_member=1,2
           pr87_diag_channel=pr85_qchannel
           if(pr87_diag_member.eq.2) pr87_diag_channel=pr85_nchannel
           do pr87_diag_k=kts,kte
             pr87_diag_rhs64(pr87_diag_k)=real( &
                  r3(i,pr87_diag_k,pr87_diag_channel),8)
           enddo
           call pr85_tridin64(kts,kte,pr87_diag_lo64,pr87_diag_diag64, &
                pr87_diag_up64,pr87_diag_rhs64, &
                pr87_diag_sol64(:,pr87_diag_member),pr87_diag_cp64, &
                pr87_diag_dp64,pr87_diag_den64)
         enddo
         if(kts.le.11 .and. 11.le.kte) then
           write(*,'(A,1X,8(I0,1X),*(1X,ES25.17E3))') &
                'PR87_SHINHONG_PBL_HEADER',pr87_cloud_target_call,j,i, &
                pr85_pair,pr85_qchannel,pr85_nchannel,kts,kte,dt,dt2,rdt
           do pr87_diag_k=kts,kte
             write(*,'(A,1X,6(I0,1X),*(1X,ES25.17E3))') &
                  'PR87_SHINHONG_PBL_ROW',pr87_cloud_target_call,j,i, &
                  pr87_diag_k,pr85_qchannel,pr85_nchannel, &
                  pr87_diag_lo64(pr87_diag_k), &
                  pr87_diag_diag64(pr87_diag_k),pr87_diag_up64(pr87_diag_k), &
                  qx(i,pr87_diag_k+(pr85_qchannel-1)*kte), &
                  qx(i,pr87_diag_k+(pr85_nchannel-1)*kte), &
                  r3(i,pr87_diag_k,pr85_qchannel), &
                  r3(i,pr87_diag_k,pr85_nchannel), &
                  pr87_diag_sol64(pr87_diag_k,1), &
                  pr87_diag_sol64(pr87_diag_k,2), &
                  f3(i,pr87_diag_k,pr85_qchannel), &
                  f3(i,pr87_diag_k,pr85_nchannel)
           enddo
         endif
       endif
"""
    return _replace_once(
        source,
        _REPLAY_ANCHOR,
        _REPLAY_ANCHOR.replace("       do k=kts,kte\n", diagnostic + "       do k=kts,kte\n"),
        "Shinhong replay insertion",
    )


def _instrument_part2(source: str) -> str:
    pre_trace = """        IF (90.GE.grid%i_start(ij) .AND. 90.LE.grid%i_end(ij) .AND. &
            14.GE.grid%j_start(ij) .AND. 14.LE.grid%j_end(ij) .AND. &
            11.GE.k_start .AND. 11.LE.MIN(k_end,kde-1)) THEN
          WRITE(*,'(A,1X,5(I0,1X),*(1X,ES25.17E3))') &
               'PR87_PBL_SOURCE_PRE',grid%itimestep,rk_step,90,14,11,grid%dt, &
               moist_tend(90,11,14,P_QC),scalar_tend(90,11,14,P_QNC), &
               grid%rqcblten(90,11,14), &
               grid%c1h(11)*grid%mut(90,14)+grid%c2h(11)
        END IF
"""
    source = _replace_once(
        source,
        _PART2_PRE_ANCHOR,
        pre_trace + _PART2_PRE_ANCHOR,
        "first RK pre-update trace",
    )

    raw_trace = """        IF (90.GE.grid%i_start(ij) .AND. 90.LE.grid%i_end(ij) .AND. &
            14.GE.grid%j_start(ij) .AND. 14.LE.grid%j_end(ij) .AND. &
            11.GE.k_start .AND. 11.LE.MIN(k_end,kde-1)) THEN
          WRITE(*,'(A,1X,5(I0,1X),*(1X,ES25.17E3))') &
               'PR87_PBL_SOURCE_RAW',grid%itimestep,rk_step,90,14,11,grid%dt, &
               pr87_raw_qsrc(90,11,14,1),pr87_raw_nsrc(90,11,14,1), &
               pr87_source_carrier(90,11,14),grid%rqcblten(90,11,14)
        END IF
"""
    source = _replace_once(
        source,
        _PART2_RAW_ANCHOR,
        _PART2_RAW_ANCHOR.replace("CALL calculate_phy_tend", raw_trace + "CALL calculate_phy_tend"),
        "first RK raw-source trace",
    )

    coupled_trace = """           IF (90.GE.grid%i_start(ij) .AND. 90.LE.grid%i_end(ij) .AND. &
               14.GE.grid%j_start(ij) .AND. 14.LE.grid%j_end(ij) .AND. &
               11.GE.k_start .AND. 11.LE.MIN(k_end,kde-1)) THEN
             WRITE(*,'(A,1X,5(I0,1X),*(1X,ES25.17E3))') &
                  'PR87_PBL_SOURCE_COUPLED',grid%itimestep,rk_step,90,14,11,grid%dt, &
                  pr87_coupled_qsrc(90,11,14,1),pr87_coupled_nsrc(90,11,14,1), &
                  moist_tend(90,11,14,P_QC),scalar_tend(90,11,14,P_QNC), &
                  pr87_source_carrier(90,11,14)
           END IF
"""
    return _replace_once(
        source,
        _PART2_COUPLED_ANCHOR,
        _PART2_COUPLED_ANCHOR.replace("         END IF\n", coupled_trace + "         END IF\n"),
        "first RK coupled-source trace",
    )


def extend_pbl_source_probe(sources: Mapping[str, str]) -> dict[str, str]:
    """Return both hash-pinned diagnostic source transforms."""
    if set(sources) != {"shinhong", "part2"}:
        raise ValueError("expected exactly the shinhong and part2 source entries")
    for name, expected in PINNED_SHA256.items():
        actual = _sha256(sources[name])
        if actual != expected:
            raise ValueError(f"{name} source SHA-256 mismatch: {actual}")
    return {
        "shinhong": _instrument_shinhong(sources["shinhong"]),
        "part2": _instrument_part2(sources["part2"]),
    }
