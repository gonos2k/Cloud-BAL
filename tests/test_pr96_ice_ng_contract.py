#!/usr/bin/env python3
"""Compile C4 source-derived active-ice completion against strict NG bounds."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from pr96_ice_ng_contract import transform


ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("/var/tmp/pr93_sources_c4_20261020/module_mp_kdm6.F")


def extract_procedure(source: str, name: str, end_name: str | None = None) -> str:
    end_name = end_name or name
    match = re.search(
        rf"(?ims)^\s*{name}\b.*?^\s*END (?:SUBROUTINE|FUNCTION) {end_name}\s*$", source
    )
    if match is None:
        raise AssertionError(f"could not extract {name}")
    return match.group().strip()


def extract_ice_blocks(source: str) -> list[str]:
    starts = (
        r"^          if\(qci\(i,k,2\) \.ge\. 1\.e-14 \) then$",
        r"^          if\(qci\(i,k,2\)\.ge\. 1\.e-14 \) then$",
        r"^          if\(qci\(i,k,2\)\.ge\. qmin \.and\. nci\(i,k,2\) \.ge\. ncmin \) then$",
    )
    blocks = []
    for start in starts:
        match = re.search(start + r".*?^          endif", source, re.M | re.S)
        if match is None:
            raise AssertionError(f"missing active ice block: {start}")
        blocks.append(match.group())
    return blocks


def build_harness(source: str, blocks: list[str]) -> str:
    strict = extract_procedure(source, "pure subroutine kdm6_ice_ng_pair_contract",
                               "kdm6_ice_ng_pair_contract")
    cone = extract_procedure(source, "pure logical function pr93_kdm6_pair_in_cone",
                             "pr93_kdm6_pair_in_cone")
    psd = extract_procedure(source, "SUBROUTINE pr85_kdm6_psd_bound_number",
                            "pr85_kdm6_psd_bound_number")
    producer = """  subroutine producer_{i}(q,n,rho)
    real :: q,n,rho
    real :: qci(1,1,2),nci(1,1,2),dry_carrier_density(1,1)
    real :: pidni,dmi,lamdaimin,lamdaimax,lamdi_tmp(1,1),n0i(1,1),g1pmi,mui
    real :: pr85_psd_before,pr85_psd_directed,pr85_psd_legacy
    real(8) :: pr85_psd_exact_min,pr85_psd_exact_max,qmin,ncmin
    real(8) :: pr93_ice_min,pr93_ice_max,pr93_ice_ng_min,pr93_ice_ng_max
    integer :: i,k,lat,pr85_psd_unit
    logical :: pr85_psd_native_available,pr67_trace_this_call
    logical :: pr85_psd_valid,pr93_ice_pair_valid,pr93_ice_ng_valid,pr93_ice_direct_repair
    real, parameter :: PR85_ICE_NATIVE_INACTIVE_MAX=NEAREST(1.e-14,-1.0)
    logical, external :: pr93_kdm6_pair_in_cone
    external :: pr85_kdm6_psd_bound_number
    i=1; k=1; lat=1; pr85_psd_unit=6
    pidni=1570.79638671875; dmi=3.0; lamdaimin=9080.0; lamdaimax=1820000.0
    g1pmi=1.0; mui=0.0; qmin=1.e-20_8; ncmin=0.0_8
    dry_carrier_density(1,1)=rho
    qci=0.0; nci=0.0
    qci(1,1,2)=q; nci(1,1,2)=n
    pr85_psd_native_available=.false.; pr67_trace_this_call=.false.
{block}
    n=nci(1,1,2)
  end subroutine producer_{i}"""
    producers = "\n".join(producer.format(i=i + 1, block=block) for i, block in enumerate(blocks))
    module = """module pr96_ice_ng_harness
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  implicit none
contains
""" + strict + "\n" + producers + "\nend module pr96_ice_ng_harness\n" + cone + "\n" + psd + "\n"
    driver = """program test_pr96_ice_ng_contract
  use, intrinsic :: iso_fortran_env, only: int32,real32,real64
  use pr96_ice_ng_harness
  implicit none
  real(real32) :: q,n,rho,expected,legacy,directed
  real(real64) :: nmin,nmax,exact_min,exact_max,mmin,mmax
  logical :: valid,legacy_available,bound_valid
  integer :: i
  logical, external :: pr93_kdm6_pair_in_cone
  external :: pr85_kdm6_psd_bound_number
  q=transfer(int(z'3588833E',int32),0.0_real32)
  n=transfer(int(z'438BCC94',int32),0.0_real32)
  rho=transfer(int(z'3F13A9EB',int32),0.0_real32)
  call kdm6_ice_ng_pair_contract(q,n,rho,1570.79638671875,3.0,9080.0,1820000.0,valid,nmin,nmax)
  if (valid .or. real(n,real64)>=nmin) error stop 'captured T26 ice pair should fail strict NG bound'
  mmin=1570.79638671875_real64/(1820000.0_real64**3)
  mmax=1570.79638671875_real64/(9080.0_real64**3)
  if (.not.pr93_kdm6_pair_in_cone(q,n,rho,mmin,mmax)) &
    error stop 'captured T26 ice pair should pass legacy 8 ULP producer cone'
  call pr85_kdm6_psd_bound_number(q,rho,9080.0,9080.0,1820000.0, &
    1570.79638671875,3.0,1,'ice','test',207,67,19,n,legacy_available,.false., &
    6,legacy,directed,exact_min,exact_max,bound_valid)
  if (.not.bound_valid) error stop 'captured T26 lower-bound helper call failed'
  expected=directed
  do i=1,3
    n=transfer(int(z'438BCC94',int32),0.0_real32)
    select case(i)
    case(1); call producer_1(q,n,rho)
    case(2); call producer_2(q,n,rho)
    case(3); call producer_3(q,n,rho)
    end select
    call kdm6_ice_ng_pair_contract(q,n,rho,1570.79638671875,3.0,9080.0, &
      1820000.0,valid,nmin,nmax)
    if (.not.valid .or. transfer(n,0_int32)/=transfer(expected,0_int32)) &
      error stop 'active ice completion did not use the strict directed lower bound'
    if (.not.pr93_kdm6_pair_in_cone(q,n,rho,mmin,mmax)) &
      error stop 'directed active ice pair left the freezing producer cone'
  end do
  call check_neighbors(2.4385062715737149e-6_real32,0.5360217094421387_real32)
  call check_neighbors(1.e-4_real32,0.7_real32)
  call check_neighbors(1.e-9_real32,1.2_real32)
  q=nearest(1.e-14_real32,-1.0_real32); rho=0.5768114924430847_real32
  call kdm6_ice_ng_pair_contract(q,1.0_real32,rho,1570.79638671875,3.0, &
    9080.0,1820000.0,valid,nmin,nmax)
  n=nearest(real(nmin,real32),-1.0_real32)
  if (real(n,real64)>=nmin) n=nearest(n,-1.0_real32)
  call kdm6_ice_ng_pair_contract(q,n,rho,1570.79638671875,3.0, &
    9080.0,1820000.0,valid,nmin,nmax)
  if (valid) error stop 'inactive strict-bound neighbor should remain strict-invalid'
  call producer_3(q,n,rho)
  if (transfer(n,0_int32)/=transfer(nearest(real(nmin,real32),-1.0_real32),0_int32)) &
    error stop 'inactive ice endpoint was newly reconstructed'
  print '(a)', 'PR96 strict ice NG source contract PASS'
contains
  subroutine check_neighbors(qv,rhov)
    real(real32), intent(in) :: qv,rhov
    real(real32) :: nv,bad_number,expected_number
    real(real32) :: lower,upper
    real(real64) :: lo,hi
    logical :: ok
    call kdm6_ice_ng_pair_contract(qv,1.0_real32,rhov,1570.79638671875,3.0, &
      9080.0,1820000.0,ok,lo,hi)
    lower=real(lo,real32)
    if (real(lower,real64)<lo) lower=nearest(lower,1.0_real32)
    nv=nearest(lower,-1.0_real32)
    call kdm6_ice_ng_pair_contract(qv,nv,rhov,1570.79638671875,3.0, &
      9080.0,1820000.0,ok,lo,hi)
    if (ok) error stop 'lower neighbor below exact NG bound was accepted'
    bad_number=nv
    expected_number=lower
    call check_all_producers(qv,rhov,bad_number,expected_number)
    call kdm6_ice_ng_pair_contract(qv,lower,rhov,1570.79638671875,3.0, &
      9080.0,1820000.0,ok,lo,hi)
    if (.not.ok) error stop 'lower directed NG endpoint was rejected'
    upper=real(hi,real32)
    if (real(upper,real64)>hi) upper=nearest(upper,-1.0_real32)
    call kdm6_ice_ng_pair_contract(qv,upper,rhov,1570.79638671875,3.0, &
      9080.0,1820000.0,ok,lo,hi)
    if (.not.ok) error stop 'upper directed NG endpoint was rejected'
    nv=nearest(upper,1.0_real32)
    call kdm6_ice_ng_pair_contract(qv,nv,rhov,1570.79638671875,3.0, &
      9080.0,1820000.0,ok,lo,hi)
    if (ok) error stop 'upper neighbor above exact NG bound was accepted'
    bad_number=nv
    expected_number=upper
    call check_all_producers(qv,rhov,bad_number,expected_number)
  end subroutine check_neighbors
  subroutine check_all_producers(qv,rhov,bad_n,expected_n)
    real(real32), intent(in) :: qv,rhov,bad_n,expected_n
    real(real32) :: actual_n
    logical :: ok
    real(real64) :: lo,hi
    integer :: producer_index
    logical, external :: pr93_kdm6_pair_in_cone
    real(real64) :: mean_min,mean_max
    mean_min=1570.79638671875_real64/(1820000.0_real64**3)
    mean_max=1570.79638671875_real64/(9080.0_real64**3)
    do producer_index=1,3
      actual_n=bad_n
      select case(producer_index)
      case(1); call producer_1(qv,actual_n,rhov)
      case(2); call producer_2(qv,actual_n,rhov)
      case(3); call producer_3(qv,actual_n,rhov)
      end select
      call kdm6_ice_ng_pair_contract(qv,actual_n,rhov,1570.79638671875,3.0, &
        9080.0,1820000.0,ok,lo,hi)
      if (.not.ok .or. transfer(actual_n,0_int32)/=transfer(expected_n,0_int32)) &
        error stop 'producer failed to repair neighboring strict-bound miss'
      if (.not.pr93_kdm6_pair_in_cone(qv,actual_n,rhov,mean_min,mean_max)) &
        error stop 'neighbor repair left freezing producer cone'
    end do
  end subroutine check_all_producers
end program test_pr96_ice_ng_contract
"""
    return module + driver


def test_pr96_ice_ng_contract() -> None:
    raw = SOURCE.read_text()
    generated = transform(raw)
    before, after = extract_ice_blocks(raw), extract_ice_blocks(generated)
    assert len(before) == len(after) == 3
    assert "8.0_real64*REAL(SPACING" in generated
    assert generated.count("call kdm6_ice_ng_pair_contract(qci(i,k,2),nci(i,k,2)") == 6
    assert generated.count(".not.pr93_ice_ng_valid .and. DBLE(nci(i,k,2)).lt.pr93_ice_ng_min") == 3

    scratch = Path(tempfile.mkdtemp(prefix="pr96_ice_ng_", dir="/var/tmp"))
    fixture = scratch / "test_pr96_ice_ng_contract.F90"
    fixture.write_text(build_harness(generated, after))
    profile = ROOT / "tests/intel_toolchain.sh"
    profile_sha256 = hashlib.sha256(profile.read_bytes()).hexdigest()
    receipts = []
    for optimization in ("O0", "O2"):
        work = scratch / optimization
        work.mkdir()
        command = [
            "bash", "-c",
            'source "$1/tests/intel_toolchain.sh" >/dev/null && '
            'if [[ "$2" == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); '
            'else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi && '
            'printf "compile_cwd=%s\\ncompiler=%s\\nflags=%s\\n" "$PWD" "$CLOUD_BAL_FC" "${flags[*]}" && '
            'printf "compile_command="; printf "%q " "$CLOUD_BAL_FC" "${flags[@]}" -free "$3" -o "$4/contract.exe"; printf "\\n" && '
            '"$CLOUD_BAL_FC" "${flags[@]}" -free "$3" -o "$4/contract.exe" && '
            '"$4/contract.exe"',
            "pr96-ice-ng", str(ROOT), optimization, str(fixture), str(work),
        ]
        result = subprocess.run(command, cwd=work, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, check=False)
        assert result.returncode == 0, result.stdout
        assert "PR96 strict ice NG source contract PASS" in result.stdout
        receipts.append(f"{optimization}: PASS\n{result.stdout.strip()}\n")

    receipt = scratch / "ice_ng_o0_o2.txt"
    receipt.write_text(
        f"source={SOURCE}\nsource_sha256={hashlib.sha256(raw.encode()).hexdigest()}\n"
        f"test={Path(__file__).resolve()}\ntest_sha256={hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}\n"
        f"generated_source_sha256={hashlib.sha256(generated.encode()).hexdigest()}\n"
        f"fixture={fixture}\nfixture_sha256={hashlib.sha256(fixture.read_bytes()).hexdigest()}\n"
        f"intel_profile={profile}\nintel_profile_sha256={profile_sha256}\n"
        + "".join(receipts)
    )
    print(f"PR96 ice NG source test PASS; receipt={receipt}")


if __name__ == "__main__":
    test_pr96_ice_ng_contract()
