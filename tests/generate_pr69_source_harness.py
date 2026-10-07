#!/usr/bin/env python3
"""Build a Fortran test from the candidate's exact cold acceptance/update lines."""
from __future__ import annotations

import re
import sys
from pathlib import Path


def extract(source: str, first: str, last: str) -> str:
    start = source.index(first)
    end = source.index(last, start) + len(last)
    return source[start:end]


def main() -> None:
    source_path, helper_path, output_path = map(Path, sys.argv[1:4])
    source = source_path.read_text()
    helper = helper_path.read_text()
    candidate_pair_and_accept = extract(
        source,
        "            factor=kdm6_shared_pair_fraction(rain_pair_rate_start(i,k,1)",
        "            ngacr(i,k) = ngacr(i,k)*factor",
    )
    candidate_store = extract(
        source,
        "              biacr(i,k) = piacr(i,k)/denr",
        "              error stop 'KDM6 rejected an invalid stored process endpoint'\n            endif",
    )
    arrays = sorted(
        set(
            re.findall(
                r"\b([a-z][a-z0-9_]*)\(i,k(?:,\s*[0-9]+)?\)",
                candidate_pair_and_accept + candidate_store,
                re.IGNORECASE,
            )
        )
    )
    rank3 = {"qci", "qrs", "nci", "nrs", "rain_pair_rate_start"}
    rank1 = {"rain_q_fixed", "rain_q_process", "rain_n_fixed", "rain_n_process"}
    declarations = ["  integer :: i,k", "  real :: pi,dmr,dmc,dmi,pidnr,pidnc,pidni"]
    declarations += [
        "  real :: qcrmin,qmin,ncmin,dtcld,lamdarmin,lamdarmax,lamdacmin,lamdacmax",
        "  real :: lamdaimin,lamdaimax,delta2,delta3,denr,deni,dens,xls,bg_fixed_expected,bg_expected_after,brs_before",
        "  real :: rain_pgdep_bg_rate,rain_pracs_bg_rate,rain_pgaci_bg_rate,rain_paacw_bg_rate",
        "  real :: rain_piacr_bg_rate,rain_praci_bg_rate,rain_psacr_bg_rate,rain_pgacr_bg_rate",
        "  logical :: rain_bg_rates_feasible,rain_bg_rate_valid",
        "  real :: factor,alpha,rain_process_alpha",
        "  real :: rain_bg_fixed,rain_bg_process,rain_t_fixed,rain_t_process",
        "  real :: t_before,temperature_expected,q_before_total,q_new_total",
        "  real :: q_after(5),n_after(3)",
        "  logical :: rain_process_feasible,rain_stored_state_feasible,stale_bg_zero_before",
    ]
    declarations += [f"  real :: {name}(1,1,{10 if name == 'rain_pair_rate_start' else 3})"
                     for name in arrays if name in rank3]
    declarations += [f"  logical :: {name}(1,1)" for name in arrays if name == "rain_full_evap_pending"]
    declarations += [f"  real :: {name}(1,1)" for name in arrays if name not in rank3 | {"rain_full_evap_pending"}]
    declarations += [f"  real :: {name}(5)" if name.startswith("rain_q_") else
                     f"  real :: {name}(3)" for name in rank1]

    initialize = [f"  {name}=.false." if name == "rain_full_evap_pending" else f"  {name}=0.0" for name in arrays]
    initialize += [f"  {name}=0.0" for name in rank1]
    initialize += [
        "  i=1; k=1",
        "  pi=3.14159265; dmr=3.0; dmc=3.0; dmi=3.0",
        "  pidnr=(pi*1000.0/6.0)*24.0",
        "  pidnc=(pi*1000.0/6.0)",
        "  pidni=(pi*500.0/6.0)*6.0",
        "  qcrmin=1.0e-9; qmin=1.0e-12; ncmin=10.0; dtcld=20.0",
        "  lamdarmin=961.0; lamdarmax=35000.0",
        "  lamdacmin=12000.0; lamdacmax=500000.0",
        "  lamdaimin=9080.0; lamdaimax=1820000.0",
        "  delta2=0.5; delta3=0.5; denr=1000.0; deni=500.0; dens=300.0",
        "  xls=2.834e6; xl(1,1)=2.5e6; cpm(1,1)=1004.0; den(1,1)=density_value; rhox(1,1)=0.0",
        "  pracs(1,1)=2.0e-9; pgaci(1,1)=3.0e-9; paacw(1,1)=1.0e-9",
        "  bracs(1,1)=0.0; bgaci(1,1)=0.0; baacw(1,1)=0.0; pgdep(1,1)=0.0",
        "  qci(1,1,1)=2.0e-5; qci(1,1,2)=1.0e-5",
        "  qrs(1,1,1)=1.0e-5; qrs(1,1,2)=1.0e-5; qrs(1,1,3)=1.0e-5",
        "  nci(1,1,1)=den(1,1)*qci(1,1,1)*100000.0**dmc/pidnc",
        "  nci(1,1,2)=den(1,1)*qci(1,1,2)*30000.0**dmi/pidni",
        "  nrs(1,1,1)=den(1,1)*qrs(1,1,1)*5000.0**dmr/pidnr",
        "  brs(1,1)=qrs(1,1,3)/400.0; t(1,1)=270.0",
        "  praut(1,1)=1.0e-7; nraut(1,1)=350.0*den(1,1)",
        "  praci(1,1)=1.0e-8; nraci(1,1)=30.0*den(1,1)",
        "  piacr(1,1)=1.0e-8; niacr(1,1)=35.0*den(1,1)",
        "  psacr(1,1)=1.0e-8; nsacr(1,1)=35.0*den(1,1)",
        "  pgacr(1,1)=1.0e-8; ngacr(1,1)=35.0*den(1,1)",
        "  nrcol(1,1)=400.0*den(1,1)",
    ]
    pairs = ((1,"praut","nraut"),(3,"praci","nraci"),
             (5,"piacr","niacr"),(7,"psacr","nsacr"),(9,"pgacr","ngacr"))
    for index,mass,number in pairs:
        initialize.extend((f"  rain_pair_rate_start(1,1,{index})={mass}(1,1)",
                           f"  rain_pair_rate_start(1,1,{index+1})={number}(1,1)"))
    driver = "\n".join(declarations)
    main = "  call initialize_fixture(0.25)\n  call execute_and_check()\n"
    main += "  call initialize_fixture(2.0)\n  call execute_and_check()\n"
    setup = "  subroutine initialize_fixture(density_value)\n    real, intent(in) :: density_value\n"
    setup += "\n".join(initialize) + "\n  end subroutine initialize_fixture\n"
    check = "  subroutine execute_and_check()\n"
    check += "  q_before_total=sum([qci(1,1,1),qci(1,1,2),qrs(1,1,1),qrs(1,1,2),qrs(1,1,3)])\n"
    check += "  t_before=t(1,1); brs_before=brs(1,1)\n"
    check += "  stale_bg_zero_before=(bracs(1,1).eq.0.0 .and. bgaci(1,1).eq.0.0 .and. baacw(1,1).eq.0.0)\n"
    check += "  call native_excerpt()\n"
    check += "  if (.not.rain_process_feasible) error stop 'native source excerpt rejected valid fixture'\n"
    check += "  if (alpha.le.0.0 .or. alpha.ge.1.0) error stop 'fixture did not exercise shared limiter'\n"
    check += "  bg_fixed_expected=brs_before+(rain_pgdep_bg_rate+rain_pracs_bg_rate+rain_pgaci_bg_rate+rain_paacw_bg_rate)*dtcld\n"
    check += "  if (abs(rain_bg_fixed-bg_fixed_expected).gt.1.0e-12) error stop 'acceptance used stale BG partner temporaries'\n"
    check += "  if (.not.stale_bg_zero_before) error stop 'fixture did not preserve stale zero partner temporaries'\n"
    check += "  bg_expected_after=rain_bg_fixed+alpha*rain_bg_process\n"
    check += "  if (abs(brs(1,1)-bg_expected_after).gt.1.0e-12) error stop 'stored graupel volume did not use the same accepted fraction'\n"
    check += "  q_after=[qci(1,1,1),qci(1,1,2),qrs(1,1,1),qrs(1,1,2),qrs(1,1,3)]\n"
    check += "  n_after=[nci(1,1,1),nci(1,1,2),nrs(1,1,1)]\n"
    check += "  q_new_total=sum(q_after)\n"
    check += "  if (abs(q_new_total-q_before_total).gt.2.0e-10) error stop 'source excerpt mass is not conserved'\n"
    check += "  if (any(q_after.lt.0.0) .or. any(n_after.lt.0.0)) error stop 'source excerpt endpoint is negative'\n"
    check += "  if (brs(1,1).lt.qrs(1,1,3)/900.0 .or. brs(1,1).gt.qrs(1,1,3)/100.0) error stop 'source excerpt BG is inadmissible'\n"
    check += "  if (abs(piacr(1,1)-alpha*rain_pair_rate_start(1,1,5)).gt.1.0e-12 .or. &\n"
    check += "      abs(psacr(1,1)-alpha*rain_pair_rate_start(1,1,7)).gt.1.0e-12 .or. &\n"
    check += "      abs(pgacr(1,1)-alpha*rain_pair_rate_start(1,1,9)).gt.1.0e-12) &\n"
    check += "      error stop 'latent-heat partner rates do not share accepted fraction'\n"
    check += "  temperature_expected=t_before-(-xls*(psdep(1,1)+pgdep(1,1)+pidep(1,1)+pinud(1,1)) &\n"
    check += "    -xl(1,1)*prevp(1,1)-(xls-xl(1,1))*(piacr(1,1)+paacw(1,1)+pmulcs(1,1) &\n"
    check += "    +pmulcg(1,1)+pmulrs(1,1)+pmulrg(1,1)+piacw(1,1)+paacw(1,1) &\n"
    check += "    +pgacr(1,1)+psacr(1,1)))/cpm(1,1)*dtcld\n"
    check += "  if (abs(t(1,1)-temperature_expected).gt.1.0e-6) &\n"
    check += "    error stop 'stored temperature differs from source latent-heat equation'\n"
    check += "  print '(A,ES12.4)', 'source excerpt accepted alpha: ',alpha\n"
    check += "  print '(A)', 'PR69 source-extracted cold endpoint test passed'\n"
    check += "  end subroutine execute_and_check\n"
    # A contained routine permits verbatim source fragments to mutate host-associated state.
    native = "  subroutine native_excerpt()\n    real :: xlf,xlwork2\n"
    native += candidate_pair_and_accept + "\n    alpha=factor\n" + candidate_store + "\n  end subroutine native_excerpt\n"
    # Embed the exact helper procedures from the already extracted module into the program.
    helper_body = helper.split("contains",1)[1].rsplit("end module",1)[0]
    output_path.write_text(
        "program test_pr69_source_excerpt\n" + driver + "\n" + main + "contains\n" + setup + check + native
        + helper_body + "\nend program test_pr69_source_excerpt\n"
    )
    # Add the executable statements in a separate main block before CONTAINS.
    text = output_path.read_text()
    if "call initialize_fixture(0.25)" not in text:
        raise SystemExit("generated harness lost density fixtures")


if __name__ == "__main__":
    main()
