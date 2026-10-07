#!/usr/bin/env python3
"""Add compact same-call water snapshots to the PR68 KDM6 observer source."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def _once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise ValueError(f"source anchor {label!r} occurs {count} times")
    return source.replace(old, new, 1)


def instrument(source: str, expected_sha256: str) -> str:
    actual = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if actual != expected_sha256:
        raise ValueError(f"selected KDM6 observer source hash mismatch: {actual}")

    helper = '''
   subroutine pr69_write_water_checkpoint(unit,stage,j,jts,its,ite,kts,kte, &
        q,qci,qrs,den,delz,fall,denr,dtcld)
     implicit none
     integer,intent(out) :: unit
     integer,intent(in) :: stage,j,jts,its,ite,kts,kte
     real,intent(in) :: q(its:ite,kts:kte),qci(its:ite,kts:kte,2)
     real,intent(in) :: qrs(its:ite,kts:kte,3),den(its:ite,kts:kte)
     real,intent(in) :: delz(its:ite,kts:kte)
     real,optional,intent(in) :: fall(its:ite,kts:kte,4),denr,dtcld
     integer :: i,k
     double precision :: column(its:ite,6)
     double precision :: bottom_fall(its:ite,4),bottom_delz(its:ite)
     real :: record_dtcld,record_denr
     do i=its,ite
       column(i,:)=0.d0
       do k=kts,kte
         column(i,1)=column(i,1)+dble(q(i,k))*dble(den(i,k))*dble(delz(i,k))
         column(i,2)=column(i,2)+dble(qci(i,k,1))*dble(den(i,k))*dble(delz(i,k))
         column(i,3)=column(i,3)+dble(qrs(i,k,1))*dble(den(i,k))*dble(delz(i,k))
         column(i,4)=column(i,4)+dble(qci(i,k,2))*dble(den(i,k))*dble(delz(i,k))
         column(i,5)=column(i,5)+dble(qrs(i,k,2))*dble(den(i,k))*dble(delz(i,k))
         column(i,6)=column(i,6)+dble(qrs(i,k,3))*dble(den(i,k))*dble(delz(i,k))
       enddo
     enddo
     bottom_fall=0.d0
     bottom_delz=0.d0
     record_dtcld=0.
     record_denr=0.
     if(stage.ge.2) then
       if(.not.present(fall) .or. .not.present(denr) .or. .not.present(dtcld)) return
       record_dtcld=dtcld
       record_denr=denr
       do i=its,ite
         bottom_fall(i,:)=dble(fall(i,kts,:))
         bottom_delz(i)=dble(delz(i,kts))
       enddo
     endif
     if(stage.eq.0 .and. j.eq.jts) then
       open(newunit=unit,file='pr69_water.raw',access='stream',form='unformatted', &
            status='replace',action='write')
     else
       open(newunit=unit,file='pr69_water.raw',access='stream',form='unformatted', &
            status='old',position='append',action='write')
     endif
     write(unit) 'PR69W001'
     write(unit) stage,j,its,ite,kts,kte
     write(unit) record_dtcld,record_denr
     write(unit) column
     write(unit) bottom_fall,bottom_delz
     close(unit)
   end subroutine pr69_write_water_checkpoint
'''
    source = _once(
        source,
        "    subroutine kdm6(th, q, qc, qr, qi, qs, qg,             &",
        helper + "\n    subroutine kdm6(th, q, qc, qr, qi, qs, qg,             &",
        "module helper placement",
    )
    source = _once(
        source,
        "   integer :: pr67_unit\n",
        "   integer :: pr67_unit\n   integer :: pr69_unit\n",
        "observer unit declaration",
    )

    cleanup = "   do k = kts, kte\n     do i = its, ite\n       qci(i,k,1) = max(qci(i,k,1),0.0)"
    source = _once(
        source,
        cleanup,
        "   if(pr67_trace_this_call) call pr69_write_water_checkpoint( &\n"
        "        pr69_unit,0,lat,jts,its,ite,kts,kte,q(its:ite,kts:kte), &\n"
        "        qci(its:ite,kts:kte,:),qrs,den(its:ite,kts:kte), &\n"
        "        delz(its:ite,kts:kte))\n" + cleanup,
        "pre-cleanup snapshot",
    )

    dend_copy = "   do k = kts,kte\n     do i = its,ite\n       dend(i,k) = den(i,k)\n     enddo\n   enddo\n"
    source = _once(
        source,
        dend_copy,
        "   if(pr67_trace_this_call) call pr69_write_water_checkpoint( &\n"
        "        pr69_unit,1,lat,jts,its,ite,kts,kte,q(its:ite,kts:kte), &\n"
        "        qci(its:ite,kts:kte,:),qrs,den(its:ite,kts:kte), &\n"
        "        delz(its:ite,kts:kte))\n"
        + dend_copy,
        "post-cleanup snapshot",
    )

    process_header = '''      if (pr67_trace_this_call) then
        open(newunit=pr67_unit,file='pr67_kdm6_process.raw', &
             access='stream',form='unformatted',status='unknown',position='append')
        write(pr67_unit) 'PR67P001'
        write(pr67_unit) 0,lat,its,ite,kts,kte,dtcld
'''
    source = _once(
        source,
        process_header,
        "      if(pr67_trace_this_call) call pr69_write_water_checkpoint( &\n"
        "           pr69_unit,2,lat,jts,its,ite,kts,kte,q(its:ite,kts:kte), &\n"
        "           qci(its:ite,kts:kte,:),qrs,dend,delz(its:ite,kts:kte), &\n"
        "           fall,denr,dtcld)\n"
        + process_header,
        "post mixed precipitation sedimentation",
    )

    ice_header = '''        if (pr67_trace_this_call .and. n .eq. 1) then
          open(newunit=pr67_unit,file='pr67_kdm6_process.raw', &
               access='stream',form='unformatted',status='unknown',position='append')
          write(pr67_unit) 'PR67P001'
          write(pr67_unit) 1,lat,its,ite,kts,kte,dtcld
'''
    source = _once(
        source,
        ice_header,
        "        if(pr67_trace_this_call .and. n.eq.1) &\n"
        "          call pr69_write_water_checkpoint(pr69_unit,3,lat,jts,its,ite, &\n"
        "               kts,kte,q(its:ite,kts:kte),qci(its:ite,kts:kte,:), &\n"
        "               qrs,dend,delz(its:ite,kts:kte),fall,denr,dtcld)\n" + ice_header,
        "post first ice sedimentation substep",
    )

    source = _once(
        source,
        "   end subroutine kdm62d",
        "      if(pr67_trace_this_call) call pr69_write_water_checkpoint( &\n"
        "           pr69_unit,4,lat,jts,its,ite,kts,kte,q(its:ite,kts:kte), &\n"
        "           qci(its:ite,kts:kte,:),qrs,dend,delz(its:ite,kts:kte), &\n"
        "           fall,denr,dtcld)\n\n"
        "   end subroutine kdm62d",
        "KDM6 return snapshot",
    )
    return source


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--expect-sha256", required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        raise SystemExit(f"refusing to overwrite observer source: {args.output}")
    result = instrument(args.source.read_text(encoding="utf-8"), args.expect_sha256)
    args.output.write_text(result, encoding="utf-8")
    print(hashlib.sha256(result.encode("utf-8")).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
