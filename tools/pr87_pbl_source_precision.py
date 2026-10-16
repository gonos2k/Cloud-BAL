"""Carry optional REAL64 Shinhong cloud/ice paired-source deltas.

The original REAL32 solve, tendency outputs, and PR85 packet withholding are
preserved.  When an optional REAL64 output is present, this transform reuses
the existing REAL64 replay of the shared REAL32 matrix and RHS and reports
only the difference between its paired tendency and the tendency returned by
the unchanged REAL32 path.
"""

from __future__ import annotations

import hashlib


PINNED_SHA256 = "a1895b765d4768208ed3b642d814fb41690c8325e78fd22a86e08f0a08ae8ed9"


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise ValueError(f"expected one {label} anchor, found {count}")
    return source.replace(old, new, 1)


def _instrument_source(source: str) -> str:
    source = _replace_once(
        source,
        "                  qni_scalar,qni_enabled,p_qni,rqniblten,pr85_packet_enabled )",
        "                  qni_scalar,qni_enabled,p_qni,rqniblten,pr85_packet_enabled, &\n"
        "                  pr87_tendency_delta64 )",
        "outer Shinhong optional argument",
    )
    source = _replace_once(
        source,
        "   logical, intent(in), optional :: pr85_packet_enabled\n",
        "   logical, intent(in), optional :: pr85_packet_enabled\n"
        "   real(kind=8), dimension(ims:ime,kms:kme,jms:jme,4), &\n"
        "        intent(inout), optional :: pr87_tendency_delta64\n",
        "outer Shinhong output declaration",
    )
    source = _replace_once(
        source,
        "             ,pr85_packet_enabled=pr85_packet_active                           &\n",
        "             ,pr85_packet_enabled=pr85_packet_active                           &\n"
        "             ,pr87_tendency_delta64=pr87_tendency_delta64                     &\n",
        "Shinhong 2D keyword forwarding",
    )
    source = _replace_once(
        source,
        "                  its,ite, jts,jte, kts,kte,pr85_packet_enabled,                 &\n"
        "                !optional\n"
        "                  regime )",
        "                  its,ite, jts,jte, kts,kte,pr85_packet_enabled,                 &\n"
        "                !optional\n"
        "                  regime,pr87_tendency_delta64 )",
        "inner Shinhong optional argument",
    )
    source = _replace_once(
        source,
        "   real,     dimension( its:ite, kts:kte*ndiff )                             , &\n"
        "             intent(inout)   ::                                          qtnp\n",
        "   real,     dimension( its:ite, kts:kte*ndiff )                             , &\n"
        "             intent(inout)   ::                                          qtnp\n"
        "   real(kind=8), dimension(ims:ime,kms:kme,jms:jme,4), &\n"
        "             intent(inout), optional :: pr87_tendency_delta64\n",
        "inner Shinhong output declaration",
    )
    source = _replace_once(
        source,
        "   logical :: pr85_reject_pair,pr85_bad_roundtrip\n",
        "   logical :: pr85_reject_pair,pr85_bad_roundtrip\n"
        "   integer :: pr87_delta_qchannel,pr87_delta_nchannel\n"
        "   real :: pr87_qlegacy32,pr87_nlegacy32,pr87_qreturn32,pr87_nreturn32\n"
        "   real(kind=8) :: pr87_qdelta64,pr87_ndelta64\n",
        "Shinhong delta locals",
    )
    source = _replace_once(
        source,
        "   qtnp(its:ite,:) = 0.\n",
        "   qtnp(its:ite,:) = 0.\n"
        "   if (present(pr87_tendency_delta64)) &\n"
        "     pr87_tendency_delta64(its:ite,kts:kte,j,1:4) = 0.d0\n",
        "Shinhong output initialization",
    )

    source = _replace_once(
        source,
        "   if (pr85_packet_enabled) then\n   do pr85_pair=1,2\n",
        "   if (pr85_packet_enabled .or. present(pr87_tendency_delta64)) then\n"
        "   do pr85_pair=1,2\n",
        "paired source replay activation",
    )

    sidecar = """       pr87_delta_qchannel=2*(pr85_pair-1)+1
       pr87_delta_nchannel=pr87_delta_qchannel+1
       if (present(pr87_tendency_delta64) .and. &
           ifvmix(pr85_qchannel) .and. ifvmix(pr85_nchannel)) then
         do k=kts,kte
           pr87_qlegacy32=(f3(i,k,pr85_qchannel)- &
                qx(i,k+(pr85_qchannel-1)*kte))*rdt
           pr87_nlegacy32=(f3(i,k,pr85_nchannel)- &
                qx(i,k+(pr85_nchannel-1)*kte))*rdt
           pr87_qreturn32=qtnp(i,k+(pr85_qchannel-1)*kte)+pr87_qlegacy32
           pr87_nreturn32=qtnp(i,k+(pr85_nchannel-1)*kte)+pr87_nlegacy32
           pr87_qdelta64=real(qtnp(i,k+(pr85_qchannel-1)*kte),8)+ &
                (pr85_sol64(k,1)-real(qx(i,k+(pr85_qchannel-1)*kte),8))*real(rdt,8) &
                -real(pr87_qreturn32,8)
           pr87_ndelta64=real(qtnp(i,k+(pr85_nchannel-1)*kte),8)+ &
                (pr85_sol64(k,2)-real(qx(i,k+(pr85_nchannel-1)*kte),8))*real(rdt,8) &
                -real(pr87_nreturn32,8)
           pr87_tendency_delta64(i,k,j,pr87_delta_qchannel)=pr87_qdelta64
           pr87_tendency_delta64(i,k,j,pr87_delta_nchannel)=pr87_ndelta64
         enddo
       endif
"""
    replay_anchor = (
        "         call pr85_tridin64(kts,kte,pr85_lo64,pr85_diag64,pr85_up64, &\n"
        "                            pr85_rhs64,pr85_sol64(:,pr85_member), &\n"
        "                            pr85_cp64,pr85_dp64,pr85_den64)\n"
        "       enddo\n"
        "       do k=kts,kte\n"
    )
    source = _replace_once(
        source,
        replay_anchor,
        replay_anchor.replace("       do k=kts,kte\n", sidecar +
                              "       if (pr85_packet_enabled) then\n"
                              "       do k=kts,kte\n"),
        "paired output and packet gate insertion",
    )
    source = _replace_once(
        source,
        "         f3(i,k,pr85_qchannel)=qx(i,k+(pr85_qchannel-1)*kte)\n"
        "         f3(i,k,pr85_nchannel)=qx(i,k+(pr85_nchannel-1)*kte)\n",
        "         f3(i,k,pr85_qchannel)=qx(i,k+(pr85_qchannel-1)*kte)\n"
        "         f3(i,k,pr85_nchannel)=qx(i,k+(pr85_nchannel-1)*kte)\n"
        "         if (present(pr87_tendency_delta64)) then\n"
        "           pr87_tendency_delta64(i,k,j,pr87_delta_qchannel)=0.d0\n"
        "           pr87_tendency_delta64(i,k,j,pr87_delta_nchannel)=0.d0\n"
        "         endif\n",
        "withheld packet delta suppression",
    )
    packet_end = (
        "       enddo\n"
        "     enddo\n"
        "   enddo\n"
        "   endif\n"
    )
    source = _replace_once(
        source,
        packet_end,
        "       enddo\n"
        "       endif\n"
        "     enddo\n"
        "   enddo\n"
        "   endif\n",
        "packet gate closure",
    )
    return source


def add_pbl_source_precision(source: str) -> str:
    """Transform only the frozen Shinhong source."""
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if digest != PINNED_SHA256:
        raise ValueError(f"Shinhong source SHA-256 mismatch: {digest}")
    return _instrument_source(source)
