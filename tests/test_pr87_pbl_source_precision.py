from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from pr87_pbl_source_precision import (  # noqa: E402
    _instrument_source,
    add_pbl_source_precision,
)


SOURCE = """SUBROUTINE shinhong
                  qni_scalar,qni_enabled,p_qni,rqniblten,pr85_packet_enabled )
   logical, intent(in), optional :: pr85_packet_enabled
   call shinhong2d(, &
             ,pr85_packet_enabled=pr85_packet_active                           &
             ,cp=cp,g=g,rovcp=rovcp,rd=rd,rovg=rovg                            &
             )
   subroutine shinhong2d
                  its,ite, jts,jte, kts,kte,pr85_packet_enabled,                 &
                !optional
                  regime )
   real,     dimension( its:ite, kts:kte*ndiff )                             , &
             intent(inout)   ::                                          qtnp
   logical, intent(in) :: pr85_packet_enabled
   real(kind=8) :: pr85_lo64(kts:kte),pr85_diag64(kts:kte),pr85_up64(kts:kte)
   real(kind=8) :: pr85_rhs64(kts:kte),pr85_sol64(kts:kte,2)
   real(kind=8) :: pr85_cp64(kts:kte),pr85_dp64(kts:kte),pr85_den64
   logical :: pr85_reject_pair,pr85_bad_roundtrip
   integer :: pr85_pair,pr85_member,pr85_qchannel,pr85_nchannel,pr85_ich
   qtnp(its:ite,:) = 0.
   if (pr85_packet_enabled) then
   do pr85_pair=1,2
     do i=its,ite
       do pr85_member=1,2
         call pr85_tridin64(kts,kte,pr85_lo64,pr85_diag64,pr85_up64, &
                            pr85_rhs64,pr85_sol64(:,pr85_member), &
                            pr85_cp64,pr85_dp64,pr85_den64)
       enddo
       do k=kts,kte
         if(qx(i,k+(pr85_qchannel-1)*kte).ne.0. .or. &
            qx(i,k+(pr85_nchannel-1)*kte).ne.0.) cycle
         pr85_reject_pair=pr85_bad_roundtrip
         if(.not.pr85_reject_pair) cycle
         f3(i,k,pr85_qchannel)=qx(i,k+(pr85_qchannel-1)*kte)
         f3(i,k,pr85_nchannel)=qx(i,k+(pr85_nchannel-1)*kte)
         open(newunit=pr85_ledger_unit,file='packet.raw')
       enddo
     enddo
   enddo
   endif
END SUBROUTINE shinhong
"""


def test_optional_delta_reuses_replay_and_tracks_return_rounding() -> None:
    transformed = _instrument_source(SOURCE)
    assert "dimension(ims:ime,kms:kme,jms:jme,4)" in transformed
    assert "pr87_tendency_delta64=pr87_tendency_delta64" in transformed
    assert "if (pr85_packet_enabled .or. present(pr87_tendency_delta64)) then" in transformed
    assert "if (pr85_packet_enabled) then\n       do k=kts,kte" in transformed
    assert "pr87_qreturn32=qtnp(i,k+(pr85_qchannel-1)*kte)+pr87_qlegacy32" in transformed
    assert "real(qtnp(i,k+(pr85_qchannel-1)*kte),8)+" in transformed
    assert "-real(pr87_qreturn32,8)" in transformed
    assert "ifvmix(pr85_qchannel) .and. ifvmix(pr85_nchannel)" in transformed
    assert "pr87_tendency_delta64(i,k,j,pr87_delta_qchannel)=0.d0" in transformed


def test_packet_withholding_still_zeroes_both_deltas() -> None:
    transformed = _instrument_source(SOURCE)
    qchannel_map = transformed.index("pr87_delta_qchannel=2*(pr85_pair-1)+1")
    nchannel_map = transformed.index("pr87_delta_nchannel=pr87_delta_qchannel+1")
    active_guard = transformed.index("ifvmix(pr85_qchannel) .and. ifvmix(pr85_nchannel)")
    assert qchannel_map < nchannel_map < active_guard
    withheld_at = transformed.index("f3(i,k,pr85_qchannel)=qx")
    zero_at = transformed.index("pr87_tendency_delta64(i,k,j,pr87_delta_qchannel)=0.d0", withheld_at)
    assert zero_at < transformed.index("open(newunit=pr85_ledger_unit", withheld_at)
    assert transformed.index("pr87_tendency_delta64(i,k,j,pr87_delta_nchannel)=0.d0", withheld_at) < zero_at + 150


def test_inactive_pair_has_mapped_channels_before_packet_rejection() -> None:
    transformed = _instrument_source(SOURCE)
    gate = transformed.index("if (present(pr87_tendency_delta64)) then", transformed.index("f3(i,k,pr85_qchannel)=qx"))
    reset = transformed.index("pr87_tendency_delta64(i,k,j,pr87_delta_qchannel)=0.d0", gate)
    mapping = transformed.rindex("pr87_delta_qchannel=2*(pr85_pair-1)+1", 0, gate)
    inactive_guard = transformed.index("ifvmix(pr85_qchannel) .and. ifvmix(pr85_nchannel)")
    assert mapping < inactive_guard < gate < reset


def test_source_pin_and_anchor_drift_are_rejected() -> None:
    with pytest.raises(ValueError, match="Shinhong source SHA-256 mismatch"):
        add_pbl_source_precision(SOURCE)
    with pytest.raises(ValueError, match="outer Shinhong optional argument"):
        _instrument_source(SOURCE.replace("pr85_packet_enabled )", "changed )"))
