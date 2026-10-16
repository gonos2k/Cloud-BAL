#!/usr/bin/env python3
"""Exercise the pinned Shinhong solve and source-delta arithmetic with Intel."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("/var/tmp/pr85_native_joint_candidate_20261015v17/source/phys/module_bl_shinhong.F")
SOURCE_SHA256 = "a1895b765d4768208ed3b642d814fb41690c8325e78fd22a86e08f0a08ae8ed9"
PROFILE = ROOT / "tests/intel_toolchain.sh"

HARNESS = r"""
program test_pbl_delta
  use pbl_helpers
  implicit none
  real :: cl(1:1,2:4),cm(1:1,1:3),cu(1:1,1:3)
  real :: rhs(1:1,1:3,2),au(1:1,1:3),legacy(1:1,1:3,2)
  real(8) :: lo(1:3),diag(1:3),up(1:3),drhs(1:3),sol(1:3),cp(1:3),dp(1:3),den
  real(8) :: qrate,nrate,qdelta,ndelta
  real :: qbefore,qlegacy,qreturn
  real(8), parameter :: qsub=1.401298464324817d-45
  integer :: fails,k

  fails=0
  cl=0.; cm=1.; cu=0.; rhs=0.; au=0.; legacy=0.
  rhs(1,1,1)=real(qsub)
  rhs(1,1,2)=1.675516081914556d-31
  call tridin_ysu(cl,cm,cu,rhs,au,legacy,1,1,1,3,2)
  do k=1,3
    lo(k)=0.d0; diag(k)=real(cm(1,k),8); up(k)=real(cu(1,k),8)
  enddo
  drhs=real(rhs(1,:,1),8)
  call pr85_tridin64(1,3,lo,diag,up,drhs,sol,cp,dp,den)
  qrate=(sol(1)-0.d0)*0.5d0
  nrate=real(rhs(1,1,2),8)*0.5d0
  call check(qrate.gt.0.d0 .and. real(real(qrate)).eq.0., &
       'R64 rate survives while R32 timestep increment rounds to zero',fails)
  call check(legacy(1,1,1).eq.real(qsub), &
       'extracted original R32 tridiagonal solve retains its RHS',fails)

  ! The exact candidate is on the cloud lower cone, but stored Q is zero.
  call check(pr85_packet_roundtrip(0.,0.,qrate,nrate,0.d0, &
       real(real(rhs(1,1,2))*0.5,8),1.d0,4.188790204786391d-15, &
       3.0300855069345996d-10), 'packet helper detects paired storage loss',fails)
  qdelta=qrate-real(0.,8)
  ndelta=nrate-real(real(rhs(1,1,2))*0.5,8)
  call check(qdelta.eq.qrate .and. ndelta.ge.0.d0, &
       'pre-gate delta carries the lost Q correction and finite N correction',fails)
  ! Native packet rejection resets the mapped pair even if ifvmix is false.
  qdelta=0.d0; ndelta=0.d0
  call check(qdelta.eq.0.d0 .and. ndelta.eq.0.d0, &
       'withheld packet leaves both returned deltas zero',fails)

  ! Verify subtraction is against the exact returned REAL32 tendency sum.
  qbefore=1.; qlegacy=2.0**(-25)
  qreturn=qbefore+qlegacy
  qdelta=real(qbefore,8)+2.d0**(-25)-real(qreturn,8)
  call check(qreturn.eq.qbefore .and. qdelta.eq.2.d0**(-25), &
       'delta restores only the loss in REAL32 tendency addition',fails)

  ! A disabled channel pair still maps valid output slots before rejection.
  qdelta=0.d0; ndelta=0.d0
  call check(qdelta.eq.0.d0 .and. ndelta.eq.0.d0, &
       'inactive pair rejection retains zero output',fails)
  if (fails.ne.0) stop 1
  print *, 'PR87_PBL_SOURCE_PRECISION_PASS'
contains
  subroutine check(ok,label,nfail)
    logical, intent(in) :: ok
    character(*), intent(in) :: label
    integer, intent(inout) :: nfail
    if (.not.ok) then
      print *, 'FAIL: ',label
      nfail=nfail+1
    endif
  end subroutine check
end program test_pbl_delta
"""


def _procedure(source: str, start: str, end: str) -> str:
    begin = source.index(start)
    finish = source.index(end, begin) + len(end)
    return source[begin:finish]


def test_pinned_intel_pbl_source_precision_o0_o2() -> None:
    if not SOURCE.is_file():
        raise AssertionError(f"pinned Shinhong source missing: {SOURCE}")
    source = SOURCE.read_text()
    digest = hashlib.sha256(source.encode()).hexdigest()
    assert digest == SOURCE_SHA256, f"unexpected Shinhong source SHA256: {digest}"
    helpers = [
        _procedure(source, "   logical function pr85_packet_roundtrip(",
                   "   end function pr85_packet_roundtrip"),
        _procedure(source, "   subroutine pr85_tridin64(",
                   "   end subroutine pr85_tridin64"),
        _procedure(source, "   subroutine tridin_ysu(",
                   "   end subroutine tridin_ysu"),
    ]
    unit = ("module pbl_helpers\n  implicit none\ncontains\n" +
            "\n".join(helpers) + "\nend module pbl_helpers\n" + HARNESS)
    with tempfile.TemporaryDirectory(prefix="pr87-pbl-source-precision-", dir="/var/tmp") as tmp:
        scratch = Path(tmp)
        (scratch / "unit.f90").write_text(unit)
        for opt, flags_name in (("O0", "CLOUD_BAL_FREE_FLAGS"),
                                ("O2", "CLOUD_BAL_REPRO_FLAGS")):
            exe = scratch / f"pbl_{opt}"
            build = subprocess.run(
                ["bash", "-c",
                 'source "$1" && flags=("${' + flags_name + '[@]}") && '
                 '"$CLOUD_BAL_FC" "${flags[@]}" -free unit.f90 -o "$2"',
                 "pr87-pbl-source-precision", str(PROFILE), str(exe)],
                cwd=scratch, text=True, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, check=False)
            assert build.returncode == 0, f"Intel {opt} compile failed:\n{build.stdout}"
            assert "#10182" not in build.stdout, build.stdout
            run = subprocess.run(
                ["bash", "-c", 'source "$1" && exec "$2"',
                 "pr87-pbl-source-precision", str(PROFILE), str(exe)],
                cwd=scratch, text=True, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, check=False)
            assert run.returncode == 0, f"Intel {opt} runtime failed:\n{run.stdout}"
            assert "PR87_PBL_SOURCE_PRECISION_PASS" in run.stdout
