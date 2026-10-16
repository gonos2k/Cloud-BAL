"""Add an opt-in compact ledger mode to the pinned V26c Shinhong PBL source."""
from __future__ import annotations

import hashlib
from collections.abc import Mapping

V26C_SHA256 = {
    "shinhong": "3bd3b9ee0f1aec25eb8a65c2ada0df748d03f785d1a0a28ad2f9b1fccb9afb50",
    "pbl_driver": "106674d12edc3c66b42b1148db40949a1dbe43c2d1ccf98bb6876403c8fccc85",
}


def _sha(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise ValueError(f"expected one {label} anchor, found {count}")
    return source.replace(old, new, 1)


_PACKET_ROW_IO = """         open(newunit=pr85_ledger_unit,file='pr85_pbl_packet_residual.raw', &
              status='unknown',position='append',action='write', &
              iostat=pr85_ledger_iostat)
         if(pr85_ledger_iostat.ne.0) &
           call wrf_error_fatal('PR85 PBL packet ledger open failed')
         write(pr85_ledger_unit,'(A,\",\",I0,\",\",I0,\",\",I0,\",\",I0, &
              \",\",7(ES24.16E3,\",\"),A)',iostat=pr85_ledger_iostat) &
              'CNUM_PAIR',j,i,k,pr85_pair,del(i,k),pr85_qrate64, &
              pr85_nrate64,pr85_qlegacy64,pr85_nlegacy64, &
              del(i,k)*pr85_qres64,del(i,k)*pr85_nres64, &
              ' units=DEL:Pa;Q:kg_water kg_dry-1 s-1;'// &
              'N:kg_dry-1 s-1;residuals:Pa-weighted,not-kg'
         if(pr85_ledger_iostat.ne.0) then
           close(pr85_ledger_unit)
           call wrf_error_fatal('PR85 PBL packet ledger write failed')
         endif
         close(pr85_ledger_unit,iostat=pr85_ledger_iostat)
         if(pr85_ledger_iostat.ne.0) &
           call wrf_error_fatal('PR85 PBL packet ledger close failed')"""

_COMPACT_ROW_IO = """         if (pr87_compact_active) then
           pr87_packet_count=pr87_packet_count+1_8
           pr87_qweighted=real(del(i,k),8)*pr85_qres64
           pr87_nweighted=real(del(i,k),8)*pr85_nres64
           pr87_qsigned=pr87_qsigned+pr87_qweighted
           pr87_ql1=pr87_ql1+abs(pr87_qweighted)
           pr87_qmax=max(pr87_qmax,abs(pr87_qweighted))
           pr87_nsigned=pr87_nsigned+pr87_nweighted
           pr87_nl1=pr87_nl1+abs(pr87_nweighted)
           pr87_nmax=max(pr87_nmax,abs(pr87_nweighted))
           if(pr87_packet_count.eq.1_8) then
             pr87_first_i=i
             pr87_first_k=k
             pr87_first_del=real(del(i,k),8)
             pr87_first_qrate=pr85_qrate64
             pr87_first_nrate=pr85_nrate64
             pr87_first_qlegacy=pr85_qlegacy64
             pr87_first_nlegacy=pr85_nlegacy64
           endif
         else
""" + _PACKET_ROW_IO + """
         endif"""

_SUMMARY_AFTER_COLUMNS = """       enddo
       endif
     enddo
     if(pr87_compact_active .and. pr85_packet_enabled) then
     write(pr87_summary_unit,'(A,1X,10(I0,1X),11(ES25.17E3,1X),A)', &
            iostat=pr87_summary_iostat) 'CNUM_SUMMARY',pr87_compact_step_active,j, &
            its,ite,kts,kte,pr85_pair,pr87_packet_count,pr87_first_i, &
            pr87_first_k,pr87_qsigned,pr87_ql1,pr87_qmax,pr87_nsigned, &
            pr87_nl1,pr87_nmax,pr87_first_del,pr87_first_qrate, &
            pr87_first_nrate,pr87_first_qlegacy,pr87_first_nlegacy, &
            'units=DEL:Pa;rates:kg kg_dry-1 s-1;weighted=Pa*rate;not-kg'
       if(pr87_summary_iostat.ne.0) &
         call wrf_error_fatal('PR87 compact PBL summary write failed')
     endif
   enddo
     if(pr87_compact_active .and. pr85_packet_enabled) then
       close(pr87_summary_unit,iostat=pr87_summary_iostat)
       if(pr87_summary_iostat.ne.0) &
         call wrf_error_fatal('PR87 compact PBL summary close failed')
     endif
   endif
!
!
   if(172.ge.its.and.172.le.ite.and.j.eq.76) then
"""


def _extend_shinhong(source: str) -> str:
    source = _replace_once(
        source,
        "                  qni_scalar,qni_enabled,p_qni,rqniblten,pr85_packet_enabled, &\n"
        "                  pr87_tendency_delta64 )",
        "                  qni_scalar,qni_enabled,p_qni,rqniblten,pr85_packet_enabled, &\n"
        "                  pr87_tendency_delta64,pr87_compact_diagnostics, &\n"
        "                  pr87_compact_step )",
        "Shinhong optional signature",
    )
    source = _replace_once(
        source,
        "   real(kind=8), dimension(ims:ime,kms:kme,jms:jme,4), &\n"
        "        intent(inout), optional :: pr87_tendency_delta64\n",
        "   real(kind=8), dimension(ims:ime,kms:kme,jms:jme,4), &\n"
        "        intent(inout), optional :: pr87_tendency_delta64\n"
        "   logical, intent(in), optional :: pr87_compact_diagnostics\n"
        "   integer, intent(in), optional :: pr87_compact_step\n",
        "Shinhong optional declarations",
    )
    source = _replace_once(
        source,
        "   logical :: pr85_packet_active\n",
        "   logical :: pr85_packet_active,pr87_compact_active\n"
        "   integer :: pr87_compact_step_active\n",
        "Shinhong compact locals",
    )
    source = _replace_once(
        source,
        "   pr85_packet_active = .false.\n"
        "   if (present(pr85_packet_enabled)) pr85_packet_active = pr85_packet_enabled\n",
        "   pr85_packet_active = .false.\n"
        "   if (present(pr85_packet_enabled)) pr85_packet_active = pr85_packet_enabled\n"
        "   pr87_compact_active = .false.\n"
        "   if (present(pr87_compact_diagnostics)) &\n"
        "     pr87_compact_active = pr87_compact_diagnostics\n"
        "   pr87_compact_step_active = 0\n"
        "   if (present(pr87_compact_step)) &\n"
        "     pr87_compact_step_active = pr87_compact_step\n",
        "Shinhong compact defaults",
    )
    source = _replace_once(
        source,
        "             ,pr85_packet_enabled=pr85_packet_active                           &\n"
        "             ,pr87_tendency_delta64=pr87_tendency_delta64                     &\n",
        "             ,pr85_packet_enabled=pr85_packet_active                           &\n"
        "             ,pr87_tendency_delta64=pr87_tendency_delta64                     &\n"
        "             ,pr87_compact_active=pr87_compact_active                         &\n"
        "             ,pr87_compact_step_active=pr87_compact_step_active               &\n",
        "Shinhong inner call",
    )

    source = _replace_once(
        source,
        "                  regime,pr87_tendency_delta64 )",
        "                  regime,pr87_tendency_delta64,pr87_compact_active, &\n"
        "                  pr87_compact_step_active )",
        "Shinhong2d compact signature",
    )
    source = _replace_once(
        source,
        "   logical,  intent(in   )   ::     pr85_packet_enabled\n",
        "   logical,  intent(in   )   ::     pr85_packet_enabled\n"
        "   logical,  intent(in   )   ::     pr87_compact_active\n"
        "   integer,  intent(in   )   ::     pr87_compact_step_active\n",
        "Shinhong2d compact declarations",
    )
    source = _replace_once(
        source,
        "   integer :: pr85_ledger_unit,pr85_ledger_iostat\n",
        "   integer :: pr85_ledger_unit,pr85_ledger_iostat\n"
        "   integer :: pr87_summary_unit,pr87_summary_iostat\n"
        "   integer(kind=8) :: pr87_packet_count\n"
        "   integer :: pr87_first_i,pr87_first_k\n"
        "   real(kind=8) :: pr87_qweighted,pr87_nweighted\n"
        "   real(kind=8) :: pr87_qsigned,pr87_ql1,pr87_qmax\n"
        "   real(kind=8) :: pr87_nsigned,pr87_nl1,pr87_nmax\n"
        "   real(kind=8) :: pr87_first_del,pr87_first_qrate,pr87_first_nrate\n"
        "   real(kind=8) :: pr87_first_qlegacy,pr87_first_nlegacy\n",
        "Shinhong2d compact statistics",
    )

    source = _replace_once(
        source,
        "   if (pr85_packet_enabled .or. present(pr87_tendency_delta64)) then\n"
        "   do pr85_pair=1,2\n",
        "   if (pr85_packet_enabled .or. present(pr87_tendency_delta64)) then\n"
        "   if(pr87_compact_active .and. pr85_packet_enabled) then\n"
        "     open(newunit=pr87_summary_unit,file='pr87_pbl_packet_summary.raw', &\n"
        "          status='unknown',position='append',action='write', &\n"
        "          iostat=pr87_summary_iostat)\n"
        "     if(pr87_summary_iostat.ne.0) &\n"
        "       call wrf_error_fatal('PR87 compact PBL summary open failed')\n"
        "   endif\n"
        "   do pr85_pair=1,2\n",
        "open compact summary once per 2D call",
    )
    pair_init = """     if(pr85_nchannel.le.0 .or. pr85_nchannel.gt.ndiff) cycle
     pr87_packet_count=0_8
     pr87_qsigned=0.d0
     pr87_ql1=0.d0
     pr87_qmax=0.d0
     pr87_nsigned=0.d0
     pr87_nl1=0.d0
     pr87_nmax=0.d0
     pr87_first_i=0
     pr87_first_k=0
     pr87_first_del=0.d0
     pr87_first_qrate=0.d0
     pr87_first_nrate=0.d0
     pr87_first_qlegacy=0.d0
     pr87_first_nlegacy=0.d0
     do i=its,ite
"""
    source = _replace_once(
        source,
        "     if(pr85_nchannel.le.0 .or. pr85_nchannel.gt.ndiff) cycle\n"
        "     do i=its,ite\n",
        pair_init,
        "compact pair accumulator initialization",
    )
    source = _replace_once(
        source,
        _PACKET_ROW_IO,
        _COMPACT_ROW_IO,
        "compact per-row branch",
    )
    source = _replace_once(
        source,
        "       enddo\n       endif\n     enddo\n   enddo\n   endif\n!\n!\n   if(172.ge.its.and.172.le.ite.and.j.eq.76) then\n",
        _SUMMARY_AFTER_COLUMNS,
        "compact per-pair summary and close",
    )
    return source


def _extend_pbl_driver(source: str) -> str:
    source = _replace_once(
        source,
        "              ,pr87_tendency_delta64 &\n!\n! END FASDAS",
        "              ,pr87_tendency_delta64 &\n"
        "              ,pr87_compact_diagnostics &\n!\n! END FASDAS",
        "PBL driver optional signature",
    )
    source = _replace_once(
        source,
        "    REAL(real64), INTENT(INOUT) :: pr87_tendency_delta64(ims:ime,kms:kme,jms:jme,4)\n",
        "    REAL(real64), INTENT(INOUT) :: pr87_tendency_delta64(ims:ime,kms:kme,jms:jme,4)\n"
        "    LOGICAL, OPTIONAL, INTENT(IN) :: pr87_compact_diagnostics\n",
        "PBL driver optional declaration",
    )
    source = _replace_once(
        source,
        "     & , PR87_TENDENCY_DELTA64=pr87_tendency_delta64 &\n",
        "     & , PR87_TENDENCY_DELTA64=pr87_tendency_delta64 &\n"
        "     & , PR87_COMPACT_DIAGNOSTICS=pr87_compact_diagnostics &\n"
        "     & , PR87_COMPACT_STEP=itimestep &\n",
        "PBL driver Shinhong call",
    )
    return source


def extend_pbl_compact_diagnostics(sources: Mapping[str, str]) -> dict[str, str]:
    """Return transformed `shinhong` and `pbl_driver` source, with compact mode opt-in."""
    if set(sources) != set(V26C_SHA256):
        raise ValueError("expected source mapping with shinhong and pbl_driver keys")
    for name, expected in V26C_SHA256.items():
        actual = _sha(sources[name])
        if actual != expected:
            raise ValueError(f"{name} source SHA-256 mismatch: {actual}")
    return {
        "shinhong": _extend_shinhong(sources["shinhong"]),
        "pbl_driver": _extend_pbl_driver(sources["pbl_driver"]),
    }
