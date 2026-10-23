#!/usr/bin/env python3
"""Add a read-only thermodynamic record to the prepared PR100 KDM6 source."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def _replace_once(source: str, before: str, after: str, name: str) -> str:
    count = source.count(before)
    if count != 1:
        raise ValueError(f"expected one {name} anchor, found {count}")
    return source.replace(before, after, 1)


def instrument_thermodynamics(source: str) -> str:
    """Instrument the source liquid-saturation adjustment without changing it."""
    source = _replace_once(source,
        "   real :: cloud_evap_extent\n",
        "   real :: cloud_evap_extent\n"
        "   real :: pr101_t_before,pr101_qv_before,pr101_qc_before\n"
        "   real :: pr101_es,pr101_bounded_e,pr101_source_extent\n"
        "   double precision :: pr101_work1,pr101_e_request\n"
        "   real :: pr101_es_initial,pr101_qs_initial,pr101_es_after,pr101_qs_after\n"
        "   real :: pr101_rh_initial,pr101_rh_branch,pr101_rh_after\n"
        "   real :: pr101_qv_after,pr101_qc_after,pr101_t_after\n"
        "   real, allocatable :: pr101_cpm_basis_q(:,:),pr101_xl_basis_t(:,:)\n"
        "   integer, save :: pr101_unit\n",
        "thermodynamic declarations")

    source = _replace_once(source,
        "   call liquid_begin(its,ite)\n",
        "   call liquid_begin(its,ite)\n"
        "   allocate(pr101_cpm_basis_q(its:ite,kts:kte), &\n"
        "            pr101_xl_basis_t(its:ite,kts:kte))\n",
        "carried heat-property history allocation")
    source = _replace_once(source,
        "            pr101_xl_basis_t(its:ite,kts:kte))\n",
        "            pr101_xl_basis_t(its:ite,kts:kte))\n"
        "   do k=kts,kte\n"
        "     do i=its,ite\n"
        "       pr101_cpm_basis_q(i,k)=q(i,k)\n"
        "       pr101_xl_basis_t(i,k)=t(i,k)\n"
        "     enddo\n"
        "   enddo\n",
        "carried heat-property history initialization")
    source = _replace_once(source,
        "       cpm(i,k) = cpmcal(q(i,k))\n"
        "       xl(i,k) = xlcal(t(i,k))\n",
        "       pr101_cpm_basis_q(i,k)=q(i,k)\n"
        "       pr101_xl_basis_t(i,k)=t(i,k)\n"
        "       cpm(i,k) = cpmcal(q(i,k))\n"
        "       xl(i,k) = xlcal(t(i,k))\n",
        "carried heat-property producer states")
    source = _replace_once(source,
        "   call liquid_end(lat,its,ite)\n",
        "   deallocate(pr101_cpm_basis_q,pr101_xl_basis_t)\n"
        "   call liquid_end(lat,its,ite)\n",
        "carried heat-property history release")

    open_anchor = "     pr100_qc_open=.true.\n"
    source = _replace_once(source, open_anchor,
        open_anchor +
        "     open(newunit=pr101_unit,file='pr101_cloud_thermo.raw', &\n"
        "          form='formatted',status='replace',action='write')\n"
        "     write(pr101_unit,'(a)') 'PR101_CLOUD_THERMO_V1'\n",
        "thermodynamic output open")

    saturation_block = (
        "          qs(i,k,1)=psat*exp(log(tr)*(xa))*exp(xb*(1.-tr))\n"
        "          qs(i,k,1) = min(qs(i,k,1),0.99*p(i,k))\n"
        "          qs(i,k,1) = ep2 * qs(i,k,1) / (p(i,k) - qs(i,k,1))\n"
        "          qs(i,k,1) = max(qs(i,k,1),qmin)\n"
        "          work1(i,k,1) = conden(t(i,k),q(i,k),qs(i,k,1),xl(i,k),cpm(i,k))\n")
    replacement = saturation_block.replace(
        "          qs(i,k,1)=psat*exp(log(tr)*(xa))*exp(xb*(1.-tr))\n",
        "          qs(i,k,1)=psat*exp(log(tr)*(xa))*exp(xb*(1.-tr))\n"
        "          pr101_es=qs(i,k,1)\n")
    source = _replace_once(source, saturation_block, replacement,
        "liquid saturation vapor pressure")

    branch_anchor = ("          if(full_cloud_evap) then\n"
                     "            q(i,k) = q(i,k)+cloud_evap_extent\n")
    branch_capture = (
        "          pr101_t_before=t(i,k)\n"
        "          pr101_qv_before=q(i,k)\n"
        "          pr101_qc_before=qci(i,k,1)\n"
        "          if(full_cloud_evap) then\n"
        "            pr101_source_extent=cloud_evap_extent\n"
        "          else\n"
        "            pr101_source_extent=-pcond(i,k)*dtcld\n"
        "          endif\n"
        "          if(full_cloud_evap) then\n"
        "            q(i,k) = q(i,k)+cloud_evap_extent\n")
    source = _replace_once(source, branch_anchor, branch_capture,
                           "liquid evaporation/condensation state entry")

    after_branch = "          endif\n          if(full_cloud_evap) pr97_extent=-cloud_evap_extent\n"
    record = (
        "          endif\n"
        "          if (pr87_model_timestep.eq.1 .and. pr100_qc_support(i,k)) then\n"
        "            pr101_qv_after=q(i,k)\n"
        "            pr101_qc_after=qci(i,k,1)\n"
        "            pr101_t_after=t(i,k)\n"
        "            pr101_work1=work1(i,k,1)\n"
        "            pr101_e_request=max(-pr101_work1,0.d0)\n"
        "            pr101_bounded_e=max(-pcond(i,k)*dtcld,0.)\n"
        "            call pr101_liquid_qs(pr101_xl_basis_t(i,k),p(i,k),psat,ttp, &\n"
        "              xa,xb,ep2,qmin,pr101_es_initial,pr101_qs_initial)\n"
        "            call pr101_liquid_qs(pr101_t_after,p(i,k),psat,ttp,xa,xb, &\n"
        "              ep2,qmin,pr101_es_after,pr101_qs_after)\n"
        "            pr101_rh_initial=max(pr101_cpm_basis_q(i,k)/pr101_qs_initial,qmin)\n"
        "            pr101_rh_branch=max(pr101_qv_before/qs(i,k,1),qmin)\n"
        "            pr101_rh_after=max(pr101_qv_after/pr101_qs_after,qmin)\n"
        "            call pr101_write_thermo(pr101_unit,pr87_model_timestep,lat,loop,i,k, &\n"
        "              full_cloud_evap,pr101_t_before,p(i,k),pr101_qv_before, &\n"
        "              pr101_qc_before,pr101_es,qs(i,k,1),pr101_work1,pcond(i,k), &\n"
        "              dtcld,xl(i,k),cpm(i,k),pr101_cpm_basis_q(i,k), &\n"
        "              pr101_xl_basis_t(i,k),psat,ttp,xa,xb,ep2,qmin, &\n"
        "              pr101_es_initial,pr101_qs_initial,pr101_es_after, &\n"
        "              pr101_qs_after,pr101_rh_initial,pr101_rh_branch, &\n"
        "              pr101_rh_after,pr101_e_request,pr101_bounded_e,pr101_source_extent, &\n"
        "              pr101_qv_after,pr101_qc_after,pr101_t_after)\n"
        "          endif\n"
        "          if(full_cloud_evap) pr97_extent=-cloud_evap_extent\n")
    source = _replace_once(source, after_branch, record,
                           "thermodynamic event after source state writes")

    close_anchor = "     close(pr100_qc_unit)\n"
    source = _replace_once(source, close_anchor,
        "     close(pr101_unit)\n" + close_anchor,
        "thermodynamic output close")

    helper_anchor = "        REAL FUNCTION GAMMLN(x)\n"
    helper = '''subroutine pr101_liquid_qs(temp,p,psat,ttp,xa,xb,ep2,qmin,es,qs)
  implicit none
  real, intent(in) :: temp,p,psat,ttp,xa,xb,ep2,qmin
  real, intent(out) :: es,qs
  real :: tr
  tr=ttp/temp
  es=psat*exp(log(tr)*(xa))*exp(xb*(1.-tr))
  qs=min(es,0.99*p)
  qs=ep2*qs/(p-qs)
  qs=max(qs,qmin)
end subroutine pr101_liquid_qs

subroutine pr101_write_thermo(unit,timestep,j,loop,i,k,full_evap, &
    t_before,p,qv_before,qc_before,es,qs,work,pcond,dt,xl,cpm,cpm_basis_q, &
    xl_basis_t,psat,ttp,xa,xb,ep2,qmin,es_initial,qs_initial,es_after, &
    qs_after,rh_initial,rh_branch,rh_after,e_request,bounded_e, &
    source_extent,qv_after,qc_after,t_after)
  implicit none
  integer, intent(in) :: unit,timestep,j,loop,i,k
  logical, intent(in) :: full_evap
  real, intent(in) :: t_before,p,qv_before,qc_before,es,qs,pcond,dt,xl,cpm
  double precision, intent(in) :: work
  real, intent(in) :: cpm_basis_q,xl_basis_t
  real, intent(in) :: psat,ttp,xa,xb,ep2,qmin,es_initial,qs_initial,es_after,qs_after
  real, intent(in) :: rh_initial,rh_branch,rh_after,bounded_e
  double precision, intent(in) :: e_request
  real, intent(in) :: source_extent,qv_after,qc_after,t_after
  write(unit,'(a,7(",",i0),*(1x,es24.16e3))') 'PR101THERMO_LIQUID', &
       timestep,j,loop,i,k,merge(1,0,full_evap),transfer(t_before,0), &
       dble(t_before),dble(p),dble(qv_before),dble(qc_before),dble(es), &
       dble(qs),dble(work),dble(pcond),dble(dt),dble(xl),dble(cpm), &
       dble(cpm_basis_q),dble(xl_basis_t),dble(psat),dble(ttp),dble(xa), &
       dble(xb),dble(ep2),dble(qmin),dble(es_initial),dble(qs_initial), &
       dble(es_after),dble(qs_after),dble(rh_initial),dble(rh_branch), &
       dble(rh_after),dble(e_request),dble(bounded_e), &
       dble(source_extent),dble(qv_after),dble(qc_after), &
       dble(t_after),dble(qv_after)-dble(qv_before), &
       dble(qc_after)-dble(qc_before),dble(t_after)-dble(t_before)
end subroutine pr101_write_thermo

'''
    return _replace_once(source, helper_anchor, helper + helper_anchor,
                         "thermodynamic writer helper")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prepared_source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    source = args.prepared_source.read_text(encoding="ascii")
    generated = instrument_thermodynamics(source)
    args.output.write_text(generated, encoding="ascii")
    receipt = {
        "schema": "pr101_cloud_thermo_source_v1",
        "input_sha256": hashlib.sha256(source.encode("ascii")).hexdigest(),
        "output_sha256": hashlib.sha256(generated.encode("ascii")).hexdigest(),
        "output_path": str(args.output.resolve()),
        "phase": "liquid saturation formula as used by source branch",
        "state_mutation": False,
    }
    args.output.with_suffix(args.output.suffix + ".json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
