#!/usr/bin/env python3
"""Pinned-source T8 regression for final rain PSD rounding and round trip."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from pr90_prepare_native_roundtrip import prepare  # noqa: E402
from pr90_rain_final_psd import (  # noqa: E402
    C6_KDM6_SOURCE_SHA256,
    add_exact_final_rain_bound_check,
)

C5_MANIFEST = ROOT / "docs/evidence/pr89_process_contract_20261019/sources/c5_sources.json"
C5_SUPPORT = Path("/var/tmp/pr89_native_build_20261019_c5/source/pr87_cloud_cycle_support.f90")
C6_BUILD = Path("/var/tmp/pr90_native_build_c6_20261019")
C6_KDM_SHA256 = C6_KDM6_SOURCE_SHA256
C6_SUPPORT_SHA256 = "d8ade43c7fe053e49a415b3de50680074bd56593ce9b5c9f31fdffb8036e91f6"
C6_EM_SHA256 = "090b9329c817f52f0fba45d6d97f93a6bdb35adc5f46cfed0ae198b15401819b"
T8_REPLAY = ROOT / "docs/evidence/pr90_rain_roundtrip_20261019/c6/OFF_t8_failure_replay.json"
T8_REPLAY_SHA256 = "e084d1738cc14a5efe1c581975502f967ecb7464602fa011295e5626c61196b4"
T8_INPUT = {
    "q": "3481DDEF", "n": "3C9BEEF8", "rho": "3F8E9DE1",
    "pid": "4644597C", "power": "40400000", "lambda_min": "44704000",
    "lambda_max": "4708B800",
}


def fortran_block(source: str, kind: str, name: str) -> str:
    suffix = r"\s*\(" if kind.lower() != "module" else r"(?:\s|$)"
    start = re.search(rf"(?im)^\s*(?:(?:pure|recursive)\s+)?{kind}\s+{name}{suffix}", source)
    if not start:
        raise AssertionError(f"missing {kind} {name}")
    end = re.search(rf"(?im)^\s*end\s+{kind}\s+{name}\s*$", source[start.start():])
    if not end:
        raise AssertionError(f"unterminated {kind} {name}")
    return source[start.start():start.start() + end.end()].strip()


def final_rain_stage3(source: str) -> str:
    anchor = "          if(qrs(i,k,1).ge.qcrmin .and. nrs(i,k,1) .ge. nrmin) then"
    positions = [m.start() for m in re.finditer(re.escape(anchor), source)]
    assert len(positions) == 3
    start = positions[-1]
    end = source.index("          endif\n          if(qci(i,k,1).ge.qmin", start) + len("          endif\n")
    block = source[start:end]
    assert "'rain','stage3'" in block
    assert "PR85_KDM6_PSD_BOUNDARY" not in block
    return block


def final_rain_cap_chain(source: str) -> str:
    start = source.index("            if( nrs(i,k,1).gt.nrmax ) then")
    end = source.index("            if( nci(i,k,1).gt.ncmax ) then", start)
    block = source[start:end]
    assert block.count("pr85_psd_exact_min=") == 1
    assert "kdm6_refresh_graupel_intercept" not in block
    return block


def fixture_source(kdm: str, em: str, support: str) -> str:
    core = fortran_block(em, "module", "cloud_bal_joint_transport")
    psd = fortran_block(kdm, "subroutine", "pr85_kdm6_psd_bound_number")
    consumer = fortran_block(kdm, "subroutine", "kdm6_rain_ng_pair_valid")
    public_store = fortran_block(support, "subroutine", "pr90_rain_public_store_diagnostic")
    store = fortran_block(support, "subroutine", "pr87_number_public_store")
    restore = fortran_block(support, "subroutine", "pr87_number_volume_store")
    stage3 = final_rain_stage3(kdm)
    cap_chain = final_rain_cap_chain(kdm)
    consumer_module = f"""module pr90_t8_consumer
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
contains
{consumer}
end module pr90_t8_consumer
"""
    program = f"""program pr90_t8_stage3_roundtrip
  use iso_fortran_env, only: real32,real64,int32
  use pr90_t8_consumer, only: kdm6_rain_ng_pair_valid
  implicit none
  integer, parameter :: i=188,k=5,lat=222
  real(real32) :: qrs(193,5,3),nrs(193,5,1),lamdr_tmp(193,5)
  real(real32) :: rho,pidnr,dmr,lamdarmin,lamdarmax,qcrmin,nrmin,nrmax
  real(real32) :: dry_carrier_density(193,5)
  real(real32) :: pr85_psd_before,pr85_psd_directed,pr85_psd_native,pr85_psd_legacy
  real(real32) :: q_public,n_public,q_restored,n_restored
  real(real64) :: pr85_psd_exact_min,pr85_psd_exact_max,delta_q,delta_n,delta_q_back,delta_n_back
  real(real64) :: rain_min,rain_max
  integer :: pr85_psd_unit,pr85_psd_adjustment,restore_adjustment,reason,io
  logical :: pr85_psd_native_available,pr85_psd_valid,pr67_trace_this_call
  logical :: store_valid,restore_valid,consumer_valid
  external :: pr87_number_public_store,pr87_number_volume_store
  rho=transfer(int(z'{T8_INPUT['rho']}',int32),0.0_real32)
  pidnr=transfer(int(z'{T8_INPUT['pid']}',int32),0.0_real32)
  lamdarmin=transfer(int(z'{T8_INPUT['lambda_min']}',int32),0.0_real32)
  lamdarmax=transfer(int(z'{T8_INPUT['lambda_max']}',int32),0.0_real32)
  qcrmin=1.e-9_real32; nrmin=1.e-2_real32; nrmax=5.e7_real32; dmr=3.0_real32
  dry_carrier_density=rho
  qrs=0.0_real32; nrs=0.0_real32; lamdr_tmp=0.0_real32
  qrs(i,k,1)=transfer(int(z'{T8_INPUT['q']}',int32),0.0_real32)
  nrs(i,k,1)=transfer(int(z'{T8_INPUT['n']}',int32),0.0_real32)
  pr67_trace_this_call=.false.
  pr85_psd_native_available=.false.
  pr85_psd_legacy=0.0_real32
  open(newunit=pr85_psd_unit,file='pr85_kdm6_psd_boundary.raw',status='replace', &
       form='formatted',action='write',iostat=io)
  if (io /= 0) error stop 'ledger open failed'
  write(pr85_psd_unit,'(a,2i10)') '# PR90_KDM6_PSD_BOUNDARY_CONTEXT timestep,lat',8,lat

  ! The source R32 slope rounds above lambda_min and bypasses its old gate.
  lamdr_tmp(i,k)=exp(log((pidnr*nrs(i,k,1))/(rho*qrs(i,k,1)))*(1.0_real32/ &
       transfer(int(z'{T8_INPUT['power']}',int32),0.0_real32)))
  if (transfer(lamdr_tmp(i,k),0_int32) /= int(z'44704006',int32)) &
    error stop 'captured T8 R32 slope changed'
  if (lamdr_tmp(i,k) <= lamdarmin .or. lamdr_tmp(i,k) >= lamdarmax) &
    error stop 'captured T8 should miss both old slope gates'
  call pr87_number_public_store(qrs(i,k,1),nrs(i,k,1),rho,pidnr, &
       transfer(int(z'{T8_INPUT['power']}',int32),0.0_real32),lamdarmin,lamdarmax, &
       q_public,n_public,store_valid,delta_q,delta_n,pr85_psd_adjustment)
  if (store_valid) error stop 'captured T8 endpoint unexpectedly stored'
{stage3}
{cap_chain}
  if (transfer(nrs(i,k,1),0_int32) /= int(z'3C9BEEF9',int32)) &
    error stop 'final stage did not direct the captured T8 number upward'
  if (transfer(lamdr_tmp(i,k),0_int32) /= int(z'44704000',int32)) &
    error stop 'final stage did not preserve the boundary slope cache'
  call pr87_number_public_store(qrs(i,k,1),nrs(i,k,1),rho,pidnr, &
       transfer(int(z'{T8_INPUT['power']}',int32),0.0_real32),lamdarmin,lamdarmax, &
       q_public,n_public,store_valid,delta_q,delta_n,pr85_psd_adjustment)
  if (.not.store_valid) error stop 'corrected T8 public store failed'
  call pr87_number_volume_store(q_public,n_public,rho,pidnr, &
       transfer(int(z'{T8_INPUT['power']}',int32),0.0_real32),lamdarmin,lamdarmax, &
       q_restored,n_restored,restore_valid,delta_q_back,delta_n_back,restore_adjustment)
  if (.not.restore_valid) error stop 'corrected T8 public restore failed'
  rain_min=(real(rho,real64)*real(lamdarmin,real64)**3)/real(pidnr,real64)
  rain_max=(real(rho,real64)*real(lamdarmax,real64)**3)/real(pidnr,real64)
  call kdm6_rain_ng_pair_valid(q_restored,n_restored,rain_min,rain_max,.false.,.false., &
       consumer_valid,reason)
  if (.not.consumer_valid) error stop 'corrected T8 restored pair failed shared consumer'
  print '(a,1x,z8.8,1x,z8.8,1x,z8.8,1x,z8.8)', 'T8_ROUNDTRIP', &
       transfer(q_public,0_int32),transfer(n_public,0_int32), &
       transfer(q_restored,0_int32),transfer(n_restored,0_int32)

  ! The final source number cap can also round outside the exact upper cone.
  qrs(i,k,1)=transfer(int(z'3CAC0831',int32),0.0_real32)
  nrs(i,k,1)=transfer(int(z'4C6E6B28',int32),0.0_real32)
  lamdr_tmp(i,k)=exp(log((pidnr*nrs(i,k,1))/(rho*qrs(i,k,1)))*(1.0_real32/dmr))
  if (lamdr_tmp(i,k)<=lamdarmin .or. lamdr_tmp(i,k)>=lamdarmax) &
    error stop 'upper-cap control should miss both source slope gates'
{stage3}
{cap_chain}
  if (DBLE(nrs(i,k,1))>pr85_psd_exact_max) &
    error stop 'final cap output remains above the exact upper bound'
  if (transfer(lamdr_tmp(i,k),0_int32)/=int(z'4708B800',int32)) &
    error stop 'upper-cap correction did not preserve the max slope cache'
  call pr87_number_public_store(qrs(i,k,1),nrs(i,k,1),rho,pidnr, &
       transfer(int(z'40400000',int32),0.0_real32),lamdarmin,lamdarmax, &
       q_public,n_public,store_valid,delta_q,delta_n,pr85_psd_adjustment)
  if (.not.store_valid) error stop 'upper-cap public store failed'
  call pr87_number_volume_store(q_public,n_public,rho,pidnr, &
       transfer(int(z'40400000',int32),0.0_real32),lamdarmin,lamdarmax, &
       q_restored,n_restored,restore_valid,delta_q_back,delta_n_back,restore_adjustment)
  if (.not.restore_valid) error stop 'upper-cap public restore failed'
  call kdm6_rain_ng_pair_valid(q_restored,n_restored,rain_min,rain_max,.false.,.false., &
       consumer_valid,reason)
  if (.not.consumer_valid) error stop 'upper-cap restored pair failed shared consumer'
  print '(a,1x,z8.8,1x,z8.8,1x,z8.8,1x,z8.8)', 'T8_CAP_ROUNDTRIP', &
       transfer(q_public,0_int32),transfer(n_public,0_int32), &
       transfer(q_restored,0_int32),transfer(n_restored,0_int32)
  close(pr85_psd_unit)
contains
{psd}
end program pr90_t8_stage3_roundtrip
"""
    return core + "\n" + public_store + "\n" + store + "\n" + restore + "\n" + consumer_module + "\n" + program


def test_pr90_rain_final_psd() -> None:
    assert C5_MANIFEST.is_file() and C5_SUPPORT.is_file() and C6_BUILD.is_dir()
    assert hashlib.sha256(T8_REPLAY.read_bytes()).hexdigest() == T8_REPLAY_SHA256
    replay = json.loads(T8_REPLAY.read_text())
    assert replay["capture"]["raw_sha256"] == (
        "aac2f11ae44d506cdcb35238e86479a26a080980cccf8f5bc91c80c6be48fe2c"
    )
    assert replay["provenance"]["closed_run_receipt"]["status"] == "INCOMPLETE"
    assert replay["event"]["reason"] == "internal_volume_precheck"
    event_hex = replay["event"]["input_hex"]
    assert [event_hex[name] for name in (
        "q_internal", "nvol_internal", "dry_density", "pidnr", "power", "lambda_min", "lambda_max"
    )] == [T8_INPUT[name] for name in (
        "q", "n", "rho", "pid", "power", "lambda_min", "lambda_max"
    )]
    scratch_parent = Path(tempfile.mkdtemp(prefix="pr90_c7_sources_", dir="/var/tmp"))
    scratch_source = scratch_parent / "source"
    generated = prepare(C5_MANIFEST, C5_SUPPORT, scratch_source, columns=True,
                        final_rain_bounds=True)
    assert generated["identity"] == "PR90-C7"
    assert generated["final_rain_bounds_enabled"] is True
    kdm_path = Path(generated["source_overrides"]["module_mp_kdm6.o"])
    support_path = Path(generated["extra_support_source"])
    em_path = Path(generated["source_overrides"]["module_em.o"])
    assert hashlib.sha256(kdm_path.read_bytes()).hexdigest() != C6_KDM_SHA256
    assert hashlib.sha256(support_path.read_bytes()).hexdigest() == C6_SUPPORT_SHA256
    assert hashlib.sha256(em_path.read_bytes()).hexdigest() == C6_EM_SHA256
    kdm = kdm_path.read_text()
    transformed = kdm
    assert transformed.count("PR90_KDM6_PSD_BOUNDARY_CONTEXT") == 1
    assert "DBLE(nrs(i,k,1)).lt.pr85_psd_exact_min" in transformed
    assert "DBLE(nrs(i,k,1)).gt.pr85_psd_exact_max" in transformed
    assert transformed.count("'rain','stage3',i,lat,k,pr85_psd_before,pr85_psd_native_available,.true.") == 2
    assert "# PR90_KDM6_PSD_BOUNDARY_CONTEXT timestep,lat" in transformed
    assert "# PR85_KDM6_PSD_BOUNDARY species,stage,i,lat,k,side,Q,rhoDry" in transformed
    fixture = fixture_source(kdm, em_path.read_text(), support_path.read_text())
    fixture_path = scratch_source / "t8.F90"
    fixture_path.write_text(fixture)

    for optimization in ("O0", "O2"):
        build = Path(tempfile.mkdtemp(prefix=f"pr90_c7_{optimization}_", dir="/var/tmp"))
        command = [
            "bash", "-c",
            'source "$1/tests/intel_toolchain.sh" && '
            'if [[ "$2" == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); '
            'else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi && '
            '"$CLOUD_BAL_FC" "${flags[@]}" -free -fpe0 -module "$3" -I "$3" '
            '"$4" -o "$3/t8.exe" && "$3/t8.exe"',
            "pr90-c7", str(ROOT), optimization, str(build), str(fixture_path),
        ]
        result = subprocess.run(command, cwd=build, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, check=False, timeout=180)
        assert result.returncode == 0, result.stdout
        assert "T8_ROUNDTRIP 3481DDEF 3C8BF3B3 3481DDEF 3C9BEEF9" in result.stdout
        assert "T8_CAP_ROUNDTRIP 3CAC0832 4C88A923 3CAC0832 4C984433" in result.stdout
        ledger = (build / "pr85_kdm6_psd_boundary.raw").read_text().splitlines()
        rows = [line for line in ledger if line.startswith("PR85_KDM6_PSD_BOUNDARY,")]
        assert len(rows) == 2
        fields = rows[0].split(",")
        assert fields[:6] == ["PR85_KDM6_PSD_BOUNDARY", "rain", "stage3", "188", "222", "5"]
        assert fields[6] == "1"
        assert fields[11].strip() == "1.9034847617149353E-002"
        assert fields[13].strip() == "1.9034849479794502E-002"
        assert fields[16].strip() == "1.9034848889916363E-002"
        upper_fields = rows[1].split(",")
        assert upper_fields[:6] == ["PR85_KDM6_PSD_BOUNDARY", "rain", "stage3", "188", "222", "5"]
        assert upper_fields[6] == "2"
        assert upper_fields[13].strip() == "7.9831440000000000E+007"
        assert upper_fields[17].strip() == "7.9831446570108593E+007"
        print(f"{optimization}: T8 exact boundary correction + public roundtrip + NG PASS")
    print("PR90 final rain PSD source contract PASS")


if __name__ == "__main__":
    test_pr90_rain_final_psd()
