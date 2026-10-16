"""Pin opt-in compact Shinhong diagnostics and compare stored-state effects."""
from __future__ import annotations

import gzip
import hashlib
import subprocess
import tempfile
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from pr87_pbl_compact_diagnostics import (  # noqa: E402
    V26C_SHA256,
    _COMPACT_ROW_IO,
    _PACKET_ROW_IO,
    extend_pbl_compact_diagnostics,
)

FIXTURES = ROOT / "tests/fixtures/pr87_pbl_compact_diagnostics_v26c"
PROFILE = ROOT / "tests/intel_toolchain.sh"


def _read_sources() -> dict[str, str]:
    return {
        "shinhong": gzip.decompress((FIXTURES / "module_bl_shinhong.F.gz").read_bytes()).decode(),
        "pbl_driver": gzip.decompress((FIXTURES / "module_pbl_driver.F.gz").read_bytes()).decode(),
    }


def _procedure(source: str, start: str, end: str) -> str:
    begin = source.index(start)
    finish = source.index(end, begin) + len(end)
    return source[begin:finish]


def test_compact_overlay_is_pinned_opt_in_and_preserves_gate_and_fallback() -> None:
    source = _read_sources()
    assert {name: hashlib.sha256(text.encode()).hexdigest() for name, text in source.items()} == V26C_SHA256
    transformed = extend_pbl_compact_diagnostics(source)
    shinhong, driver = transformed["shinhong"], transformed["pbl_driver"]

    assert "logical, intent(in), optional :: pr87_compact_diagnostics" in shinhong
    assert "pr87_compact_active = .false." in shinhong
    assert "if (present(pr87_compact_diagnostics))" in shinhong
    assert "LOGICAL, OPTIONAL, INTENT(IN) :: pr87_compact_diagnostics" in driver
    assert "PR87_COMPACT_STEP=itimestep" in driver
    assert "pr87_compact_active=pr87_compact_active" in shinhong
    assert "pr87_compact_step_active=pr87_compact_step_active" in shinhong
    assert "pr87_pbl_packet_summary.raw" in shinhong
    assert "'CNUM_SUMMARY',pr87_compact_step_active,j" in shinhong
    assert _PACKET_ROW_IO in shinhong

    # Gate, rollback, and sidecar reset remain the exact pinned source statements.
    for statement in (
        "pr85_qrate64=(pr85_sol64(k,1)-",
        "pr85_nrate64=(pr85_sol64(k,2)-",
        "pr85_bad_roundtrip=pr85_packet_roundtrip(",
        "pr87_qdelta64=real(qtnp(i,k+(pr85_qchannel-1)*kte),8)+",
        "pr87_ndelta64=real(qtnp(i,k+(pr85_nchannel-1)*kte),8)+",
        "pr87_tendency_delta64(i,k,j,pr87_delta_qchannel)=pr87_qdelta64",
        "pr87_tendency_delta64(i,k,j,pr87_delta_nchannel)=pr87_ndelta64",
        "f3(i,k,pr85_qchannel)=qx(i,k+(pr85_qchannel-1)*kte)",
        "pr87_tendency_delta64(i,k,j,pr87_delta_qchannel)=0.d0",
    ):
        assert statement in source["shinhong"] and statement in shinhong
    gate_start = "         if(qx(i,k+(pr85_qchannel-1)*kte).ne.0. .or. &"
    original_prefix = source["shinhong"].split(gate_start, 1)[1].split(
        "         open(newunit=pr85_ledger_unit", 1
    )[0]
    transformed_prefix = shinhong.split(gate_start, 1)[1].split(
        "         if (pr87_compact_active) then", 1
    )[0]
    assert original_prefix == transformed_prefix
    assert "qtnp(i,k+is) = qtnp(i,k+is)+qtend" in shinhong
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        extend_pbl_compact_diagnostics({
            **source, "shinhong": source["shinhong"].replace("pr85_packet_enabled", "changed")
        })


def _fixture(helper: str) -> str:
    reference_branch = """         else
           full_count=full_count+1_8
           full_qsigned=full_qsigned+real(del(i,k),8)*pr85_qres64
           full_ql1=full_ql1+abs(real(del(i,k),8)*pr85_qres64)
           full_qmax=max(full_qmax,abs(real(del(i,k),8)*pr85_qres64))
           full_nsigned=full_nsigned+real(del(i,k),8)*pr85_nres64
           full_nl1=full_nl1+abs(real(del(i,k),8)*pr85_nres64)
           full_nmax=max(full_nmax,abs(real(del(i,k),8)*pr85_nres64))
         endif"""
    compact_block = _COMPACT_ROW_IO.replace(
        _PACKET_ROW_IO,
        reference_branch.removeprefix("         else\n").removesuffix("\n         endif"),
    )
    return r"""program compact_equivalence
  use, intrinsic :: iso_fortran_env, only: real64
  implicit none
  real :: f_full(3,2),f_compact(3,2),qt_full(3,2),qt_compact(3,2)
  real(real64) :: side_full(3,2),side_compact(3,2),stats_full(6),stats_compact(6)
  integer(kind=8) :: count_full,count_compact
  call run_mode(.false.,f_full,qt_full,side_full,count_full,stats_full)
  call run_mode(.true.,f_compact,qt_compact,side_compact,count_compact,stats_compact)
  if (count_compact /= 2_8 .or. count_full /= count_compact) error stop 11
  if (any(transfer(f_full,[0,0,0,0,0,0]) /= transfer(f_compact,[0,0,0,0,0,0]))) error stop 12
  if (any(transfer(qt_full,[0,0,0,0,0,0]) /= transfer(qt_compact,[0,0,0,0,0,0]))) error stop 13
  if (any(transfer(side_full,[0_8,0_8,0_8,0_8,0_8,0_8]) /= &
          transfer(side_compact,[0_8,0_8,0_8,0_8,0_8,0_8]))) error stop 14
  if (any(stats_full /= stats_compact)) error stop 15
  if (f_compact(1,1) /= 0.0 .or. f_compact(2,1) /= 0.0) error stop 16
  if (side_compact(1,1) /= 0.0_real64 .or. side_compact(2,1) /= 0.0_real64) error stop 17
  if (qt_compact(3,1) == 0.4) error stop 18
  print *, 'PR87 PBL compact/full gate equivalence PASS'
contains
  subroutine run_mode(compact,fout,qtout,sideout,count_out,stats_out)
    logical,intent(in) :: compact
    real,intent(out) :: fout(3,2),qtout(3,2)
    real(real64),intent(out) :: sideout(3,2),stats_out(6)
    integer(kind=8),intent(out) :: count_out
    real :: qx(3),nx(3),del(3,3),rdt,dt,f3q,f3n,qtend
    real(real64) :: qrate_source(3),nrate_source(3),qlegacy64,nlegacy64
    real(real64) :: pr85_qrate64,pr85_nrate64,pr85_qlegacy64,pr85_nlegacy64
    real(real64) :: pr85_qres64,pr85_nres64,pr85_minmass64,pr85_maxmass64
    real(real64) :: full_qsigned,full_ql1,full_qmax,full_nsigned,full_nl1,full_nmax
    real(real64) :: pr87_qweighted,pr87_nweighted,pr87_qsigned,pr87_ql1,pr87_qmax
    real(real64) :: pr87_nsigned,pr87_nl1,pr87_nmax
    real(real64) :: pr87_first_del,pr87_first_qrate,pr87_first_nrate
    real(real64) :: pr87_first_qlegacy,pr87_first_nlegacy
    logical :: pr85_bad_roundtrip,pr85_reject_pair,pr87_compact_active
    integer :: i,k,pr85_pair,pr87_first_i,pr87_first_k
    integer(kind=8) :: pr87_packet_count,full_count
    integer :: pr85_ledger_unit,pr85_ledger_iostat
    fout=0.0; qx=0.0; nx=0.0; del=0.0
    del(1,1)=4000.0; del(2,2)=3000.0; del(3,3)=5000.0
    rdt=0.05; dt=20.0
    qtout=reshape([0.2,0.3,0.4,0.5,0.6,0.7],[3,2])
    sideout=reshape([1d0,2d0,3d0,4d0,5d0,6d0],[3,2])
    qrate_source=[1.0300213240370473d-49,1.0d-42,1.0d-6]
    nrate_source=[9.1427002949118670d-38,1.0d-28,1.0d6]
    full_count=0_8; full_qsigned=0d0; full_ql1=0d0; full_qmax=0d0
    full_nsigned=0d0; full_nl1=0d0; full_nmax=0d0
    pr87_packet_count=0_8; pr87_qsigned=0d0; pr87_ql1=0d0; pr87_qmax=0d0
    pr87_nsigned=0d0; pr87_nl1=0d0; pr87_nmax=0d0
    pr87_first_i=0; pr87_first_k=0; pr87_first_del=0d0
    pr87_first_qrate=0d0; pr87_first_nrate=0d0
    pr87_first_qlegacy=0d0; pr87_first_nlegacy=0d0
    pr87_compact_active=compact; pr85_pair=1
    do k=1,3
      i=k
      if (k==1) then
        f3q=0.0; f3n=real(9.1427000840058955d-38/real(rdt,real64))
        pr85_minmass64=4.188790204786391d-15; pr85_maxmass64=3.0300855069345996d-10
      else if (k==2) then
        f3q=real(1.401298464324817d-45/real(rdt,real64))
        f3n=real(1.0d-28/real(rdt,real64))
        pr85_minmass64=4.188790204786391d-15; pr85_maxmass64=3.0300855069345996d-10
      else
        f3q=real(qrate_source(k)/real(rdt,real64))
        f3n=real(nrate_source(k)/real(rdt,real64))
        pr85_minmass64=4.188790204786391d-15; pr85_maxmass64=3.0300855069345996d-10
      endif
      pr85_qrate64=qrate_source(k); pr85_nrate64=nrate_source(k)
      pr85_qlegacy64=real((f3q-qx(k))*rdt,real64)
      pr85_nlegacy64=real((f3n-nx(k))*rdt,real64)
      pr85_bad_roundtrip=pr85_packet_roundtrip(qx(k),nx(k),pr85_qrate64,pr85_nrate64, &
                    pr85_qlegacy64,pr85_nlegacy64,real(dt,real64), &
                    pr85_minmass64,pr85_maxmass64)
      pr85_reject_pair=pr85_bad_roundtrip
      pr85_qres64=0d0; pr85_nres64=0d0
      if (pr85_reject_pair) then
        pr85_qres64=pr85_qrate64; pr85_nres64=pr85_nrate64
        fout(k,1)=qx(k); fout(k,2)=nx(k)
        sideout(k,1)=0d0; sideout(k,2)=0d0
      else
        fout(k,1)=f3q; fout(k,2)=f3n
      endif
      if (pr85_reject_pair) then
""" + compact_block + r"""
      endif
      qtend=(fout(k,1)-qx(k))*rdt
      qtout(k,1)=qtout(k,1)+qtend
      qtend=(fout(k,2)-nx(k))*rdt
      qtout(k,2)=qtout(k,2)+qtend
    enddo
    if (compact) then
      count_out=pr87_packet_count
      stats_out=[pr87_qsigned,pr87_ql1,pr87_qmax,pr87_nsigned,pr87_nl1,pr87_nmax]
    else
      count_out=full_count
      stats_out=[full_qsigned,full_ql1,full_qmax,full_nsigned,full_nl1,full_nmax]
    endif
  end subroutine run_mode
""" + helper + r"""
end program compact_equivalence
"""


def test_pinned_intel_compact_gate_matches_full_mode_o0_o2() -> None:
    source = _read_sources()["shinhong"]
    helper = _procedure(source, "   logical function pr85_packet_roundtrip(",
                        "   end function pr85_packet_roundtrip")
    with tempfile.TemporaryDirectory(prefix="pr87-pbl-compact-", dir="/var/tmp") as tmp:
        scratch = Path(tmp)
        (scratch / "unit.f90").write_text(_fixture(helper))
        for opt, flags in (("O0", "CLOUD_BAL_FREE_FLAGS"), ("O2", "CLOUD_BAL_REPRO_FLAGS")):
            exe = scratch / f"compact_{opt}"
            build = subprocess.run(
                ["bash", "-c", 'source "$1" && flags=("${' + flags + '[@]}") && '
                 '"$CLOUD_BAL_FC" "${flags[@]}" -free unit.f90 -o "$2"',
                 "pr87-pbl-compact", str(PROFILE), str(exe)],
                cwd=scratch, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                check=False,
            )
            assert build.returncode == 0, f"Intel {opt} compile failed:\n{build.stdout}"
            run = subprocess.run(
                ["bash", "-c", 'source "$1" && exec "$2"', "pr87-pbl-compact", str(PROFILE), str(exe)],
                cwd=scratch, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                check=False,
            )
            assert run.returncode == 0, f"Intel {opt} run failed:\n{run.stdout}"
            assert "PR87 PBL compact/full gate equivalence PASS" in run.stdout
