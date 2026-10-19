"""Add read-only consumer context and a T3 replay input to frozen V42 KDM6."""
from __future__ import annotations

import hashlib


V42_SHA256 = "bdb1882afed860068cecbb6c7b958eef0938cadbd4225222ba7522e28ecc071a"
CALL_START = "   call ProgB_param(brs,qrs_tmp,rhox,its,ite,jts,jte,kts,kte,qcrmin"
CALL_END = "                   ,g1pbg,g3pbg,g4pbg,g5pbgo2,g1pdgbgmg,dgbgmug1,progb_status)"


def add_failure_context(source: str) -> str:
    """Preserve all state calculations, gates and original trace ownership."""
    if hashlib.sha256(source.encode()).hexdigest() != V42_SHA256:
        raise ValueError("expected the frozen V42 KDM6 source")
    if source.count(CALL_START) != 7:
        raise ValueError("expected seven native ProgB call sites")
    pieces = source.split(CALL_START)
    for site in range(1, 8):
        call, remainder = pieces[site].split(CALL_END, 1)
        pieces[site] = CALL_START + call + CALL_END + f"""
   call pr87_report_graupel_consumer({site},pr87_model_timestep,lat, &
        its,ite,kts,kte,qrs_tmp,brs,progb_status)
""" + remainder
    source = "".join(pieces)
    anchor = "   end subroutine kdm6\n"
    if source.count(anchor) != 1:
        raise ValueError("expected one KDM6 end")
    report = """
   subroutine pr87_report_graupel_consumer(site,timestep,lat,its,ite,kts,kte,qrs,bg,status)
     implicit none
     integer,intent(in) :: site,timestep,lat,its,ite,kts,kte
     real,intent(in) :: qrs(its:ite,kts:kte,3),bg(its:ite,kts:kte)
     integer,intent(in) :: status(its:ite,kts:kte)
     integer :: i,k
     do k=kts,kte
       do i=its,ite
         if (status(i,k)==PROGB_ABSENT.or.status(i,k)==PROGB_PSD_ACTIVE) cycle
         write(*,'(a,6(1x,i0),2(1x,es26.17),2(1x,z8.8))') &
              'PR87_G_CONSUMER_FAILURE',timestep,site,lat,i,k,status(i,k), &
              dble(qrs(i,k,3)),dble(bg(i,k)),transfer(qrs(i,k,3),0),transfer(bg(i,k),0)
         flush(6)
         return
       enddo
     enddo
   end subroutine pr87_report_graupel_consumer
"""
    source = source.replace(anchor, anchor + report, 1)
    anchor = "   if (pr67_trace_this_call) then\n     call kdm6_trace_dump(1,"
    if source.count(anchor) != 1:
        raise ValueError("expected one original pre-call trace")
    capture = """   if (itimestep == 3) then
     call kdm6_trace_dump(1,itimestep,ids,ide,jds,jde,kds,kde, &
          ims,ime,jms,jme,kms,kme,its,ite,jts,jte,kts,kte, &
          delt,ccn0,scale_h,qnn_land_mult,qnn_sea_mult, &
          th,pii,den,p,delz,q,qc,qr,qi,qs,qg,nn,nc,ni,nr,bg,diag_rhog,xland)
   endif
"""
    source = source.replace(anchor, capture + anchor, 1)
    anchor = "       path='kdm6_first_call_pre.raw'\n"
    if source.count(anchor) != 1:
        raise ValueError("expected one original pre-call filename")
    source = source.replace(anchor, anchor + "       if (itimestep == 3) path='kdm6_third_call_pre.raw'\n", 1)
    return source
