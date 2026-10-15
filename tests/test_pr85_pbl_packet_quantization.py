#!/usr/bin/env python3
"""Exercise the exact PBL packet-roundtrip helper from pinned PR74 source."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BASE = Path("/var/tmp/pr74_shinhong_qni_driver.GvfcGi/O0/compile/module_bl_shinhong.F")
PATCH = ROOT / "patches/pr85_pbl_packet_quantization.patch"
PROFILE = ROOT / "tests/intel_toolchain.sh"

HARNESS = r"""
program test_packet_commit
  use pr85_packet_helper_mod
  implicit none
  real(8) :: cl(1:2),cm(1:2),cu(1:2),rhs(1:2),sol(1:2)
  real(8) :: cp(1:2),dp(1:2),denom
  real :: al32(1:3),cm32(1:3),cu32(1:3),rhs32(1:3),legacy32(1:3)
  real(8) :: lower64(1:3),diag64(1:3),upper64(1:3),rhs64(1:3),sol64(1:3)
  real(8) :: cp64(1:3),dp64(1:3),denom64
  real(8) :: qstate64,nstate64
  logical :: bad_roundtrip
  integer :: failures
  failures=0

  ! The exact REAL32 RHS can yield a positive REAL64 solution below REAL32.
  cl=0.d0; cm=3.d0; cu=0.d0
  rhs=0.d0; rhs(1)=1.401298464324817d-45
  call pr85_tridin64(1,2,cl,cm,cu,rhs,sol,cp,dp,denom)
  call check(sol(1)>0.d0 .and. real(sol(1))==0.0, &
             'REAL64 solve retains a source rounded out of REAL32',failures)

  ! Match the legacy tridin_ysu dummy lower bound cl(kts+1:kte+1).
  ! Its row-k lower coefficient is actual al(k-1), including the top row.
  al32=[-0.25,-0.5,0.0]
  cm32=[2.0,2.0,2.0]
  cu32=[-0.25,-0.5,0.0]
  rhs32=0.0; rhs32(1)=nearest(0.0,1.0)
  lower64=0.d0
  diag64=real(cm32,8); upper64=real(cu32,8); rhs64=real(rhs32,8)
  lower64(2)=real(al32(1),8); lower64(3)=real(al32(2),8)
  call pr85_tridin64(1,3,lower64,diag64,upper64,rhs64,sol64,cp64,dp64,denom64)
  call legacy_dummy_lower_solve(al32,cm32,cu32,rhs32,legacy32)
  call check(sol64(3)>0.d0 .and. legacy32(3)==0.0, &
             'top-row PBL import survives REAL64 lower-offset solve',failures)
  call check(abs(sol64(3)-real(legacy32(3),8))>0.d0, &
             'REAL64 reconstruction retains the top import rounded by legacy solve',failures)

  ! Two levels also exercise the first lower coefficient at the upper row.
  lower64(1:2)=0.d0; lower64(2)=real(al32(1),8)
  call pr85_tridin64(1,2,lower64(1:2),diag64(1:2),upper64(1:2),rhs64(1:2), &
                     sol(1:2),cp(1:2),dp(1:2),denom)
  call legacy_dummy_lower_solve(al32(1:2),cm32(1:2),cu32(1:2),rhs32(1:2),legacy32(1:2))
  call check(sol(2)>0.d0 .and. legacy32(2)==0.0, &
             'two-level PBL source uses the shifted lower coefficient',failures)

  ! The observed one-third-step packet rounds to seven QI subnormal units.
  ! Both exact candidates are in cone; REAL32 state storage exceeds ice max.
  qstate64=(1.d0/3.d0)*20.d0*1.401298464324817d-45
  nstate64=(1.d0/3.d0)*20.d0*6.916113032548114d-37
  call check(qstate64/nstate64.lt.2.098274638742861d-9, &
             'exact REAL64 QI/NI candidate is below the PSD maximum',failures)
  call check(real(real(qstate64))/real(real(nstate64)).gt.2.098274638742861d-9, &
             'stored REAL32 QI/NI candidate is above the PSD maximum',failures)
  bad_roundtrip=pr85_packet_roundtrip(0.,0.,1.401298464324817d-45,6.916113032548114d-37, &
       1.401298464324817d-45,6.916113032548114d-37,20.d0, &
       2.605587805918249d-16,2.098274638742861d-9)
  call check(bad_roundtrip, &
             'valid true QI/NI packet rejects when stored RK1 pair exits PSD',failures)

  ! When QI vanishes in the REAL32 tendency, the exact QI proposal still
  ! triggers paired rejection and the source ledger retains its R64 value.
  bad_roundtrip=pr85_packet_roundtrip(0.,0.,1.d-46,1.d-36,0.d0,1.d-36,20.d0, &
       2.605587805918249d-16,2.098274638742861d-9)
  call check(bad_roundtrip,'R64 QI import survives into paired rejection when R32 QI is zero',failures)

  ! This full-step packet has exact mean mass 2.09e-9, inside the ice cone.
  ! Fractions 1/3 and 1/2 store 4/6 Q subnormal units; the full step stores
  ! 13 units and exceeds the maximum, so checking only early stages misses it.
  qstate64=(1.d0/3.d0)*1.795909413943659d-44
  nstate64=(1.d0/3.d0)*8.592868009299804d-36
  call check(real(real(qstate64))/real(real(nstate64)).lt.2.098274638742861d-9, &
             'one-third stored QI/NI packet remains feasible',failures)
  qstate64=0.5d0*1.795909413943659d-44
  nstate64=0.5d0*8.592868009299804d-36
  call check(real(real(qstate64))/real(real(nstate64)).lt.2.098274638742861d-9, &
             'one-half stored QI/NI packet remains feasible',failures)
  qstate64=1.795909413943659d-44
  nstate64=8.592868009299804d-36
  call check(qstate64/nstate64.lt.2.098274638742861d-9 .and. &
             qstate64/nstate64.gt.2.08d-9 .and. &
             real(real(qstate64))/real(real(nstate64)).gt.2.098274638742861d-9, &
             'full stored QI/NI packet alone exits the PSD maximum',failures)
  bad_roundtrip=pr85_packet_roundtrip(0.,0.,1.795909413943659d-44, &
       8.592868009299804d-36,1.795909413943659d-44,8.592868009299804d-36, &
       1.d0,2.605587805918249d-16,2.098274638742861d-9)
  call check(bad_roundtrip,'full RK3 stage is also checked',failures)

  ! A normal paired PBL import remains unchanged through every RK3 fraction.
  bad_roundtrip=pr85_packet_roundtrip(0.,0.,1.d-14,1.d-4,1.d-14,1.d-4,20.d0, &
       4.188790204786391d-15,3.0300855069345996d-10)
  call check(.not.bad_roundtrip,'ordinary paired PBL import remains feasible',failures)

  ! A true source outside the cone is not silently suppressed, even if its
  ! REAL32 water channel vanishes; the grouped source validator sees it.
  bad_roundtrip=pr85_packet_roundtrip(0.,0.,1.d-40,1.d-42,0.d0,1.d-42,20.d0, &
       2.605587805918249d-16,2.098274638742861d-9)
  call check(.not.bad_roundtrip,'invalid true pair is not packet-suppressed',failures)

  ! A one-channel physical source remains visible for process-level diagnosis.
  bad_roundtrip=pr85_packet_roundtrip(0.,0.,1.d-40,0.d0,0.d0,0.d0,20.d0, &
       2.605587805918249d-16,2.098274638742861d-9)
  call check(.not.bad_roundtrip,'number-only source is not reclassified as a pair',failures)

  ! The PBL policy only operates on zero-base paired imports.
  bad_roundtrip=pr85_packet_roundtrip(1.e-20,1.e-10,1.d-12,1.d-4,1.d-12,1.d-4,20.d0, &
       4.188790204786391d-15,3.0300855069345996d-10)
  call check(.not.bad_roundtrip,'existing base pair is outside packet suppression',failures)

  if (failures.ne.0) stop 1
  print *, 'PR85_PBL_PACKET_ROUNDTRIP_PASS'
contains
  subroutine legacy_dummy_lower_solve(al,cm,cu,rhs,solution)
    real, intent(in) :: al(:),cm(:),cu(:),rhs(:)
    real, intent(out) :: solution(:)
    real :: cl(size(al)+1),au(size(al)),forward(size(al)),factor
    integer :: n,k
    n=size(al)
    cl(2:n+1)=al
    factor=1.0/cm(1)
    au(1)=factor*cu(1)
    forward(1)=factor*rhs(1)
    do k=2,n-1
      factor=1.0/(cm(k)-cl(k)*au(k-1))
      au(k)=factor*cu(k)
      forward(k)=factor*(rhs(k)-cl(k)*forward(k-1))
    enddo
    factor=1.0/(cm(n)-cl(n)*au(n-1))
    forward(n)=factor*(rhs(n)-cl(n)*forward(n-1))
    do k=n-1,1,-1
      forward(k)=forward(k)-au(k)*forward(k+1)
    enddo
    solution=forward
  end subroutine legacy_dummy_lower_solve

  subroutine check(ok,label,failures)
    logical, intent(in) :: ok
    character(*), intent(in) :: label
    integer, intent(inout) :: failures
    if (.not.ok) then
      print *, 'FAIL: ',label
      failures=failures+1
    endif
  end subroutine check
end program test_packet_commit
"""


def fail(message: str) -> None:
    raise SystemExit(message)


def main() -> None:
    if not BASE.is_file() or not PATCH.is_file():
        fail("retained PR74 source or PR85 packet patch is missing")
    with tempfile.TemporaryDirectory(prefix="pr85-pbl-packet-", dir="/var/tmp") as tmp:
        scratch = Path(tmp)
        source = scratch / BASE.name
        source.write_bytes(BASE.read_bytes())
        applied = subprocess.run(
            ["patch", "--fuzz=0", "-p1", "-i", str(PATCH)], cwd=scratch,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if applied.returncode:
            fail("pinned PBL patch did not apply cleanly:\n" + applied.stdout)
        patched = source.read_text()
        helpers = []
        for name in ("pr85_packet_roundtrip", "pr85_tridin64"):
            kind = "logical function" if name == "pr85_packet_roundtrip" else "subroutine"
            start = patched.index(f"   {kind} {name}(")
            end_kind = "function" if name == "pr85_packet_roundtrip" else "subroutine"
            marker = f"   end {end_kind} {name}"
            end = patched.index(marker, start)
            helpers.append(patched[start:end + len(marker)])
        solve_at = patched.index("call tridin_ysu(al,ad,cu,r3,au,f3")
        guard_at = patched.index("pr85_bad_roundtrip=pr85_packet_roundtrip(", solve_at)
        aggregation_at = patched.index("qtnp(i,k) = qtnp(i,k)+qtend", guard_at)
        if not solve_at < guard_at < aggregation_at:
            fail("packet gate must follow the shared PBL solve and precede tendency aggregation")
        kernel = (ROOT / "src/common/cloud_bal_joint_transport.f90").read_text()
        if "pr85_packet_roundtrip" in kernel:
            fail("PBL representation policy must remain outside the general joint kernel")
        if "pr85_qrate64=(pr85_sol64(k,1)-" not in patched:
            fail("true Q source is not reconstructed from the REAL64 solve")
        if "pr85_nrate64=(pr85_sol64(k,2)-" not in patched:
            fail("true N source is not reconstructed from the REAL64 solve")
        if "if(k.gt.kts) pr85_lo64(k)=real(al(i,k-1),8)" not in patched:
            fail("REAL64 matrix must match tridin_ysu's shifted cl dummy lower bound")
        if "pr85_qlegacy64,pr85_nlegacy64,real(dt,8)," not in patched:
            fail("PBL packet round-trip must use the actual passed model timestep")
        if "rk_fraction(3)=[1.d0/3.d0,0.5d0,1.d0]" not in patched:
            fail("PBL packet admission must check all three native RK fractions")
        if "pr85_bad_roundtrip" not in patched or "pr85_qres64=pr85_qrate64" not in patched:
            fail("infeasible stored packet must reject and ledger both REAL64 source rates")
        if "call pr85_packet_commit(" in patched:
            fail("all PBL suppression must be conditioned on true paired R64 PSD validity")
        for binding in ("logical, intent(in), optional :: pr85_packet_enabled",
                        "pr85_packet_active = .false.",
                        "if (pr85_packet_enabled) then",
                        "external :: wrf_error_fatal",
                        "PR85 PBL packet ledger open failed",
                        "PR85 PBL packet ledger write failed",
                        "PR85 PBL packet ledger close failed"):
            if binding not in patched:
                fail(f"PBL source-scope or ledger-failure guard missing: {binding}")
        if "kts+1:kte+1" not in patched[patched.index("subroutine tridin_ysu("):]:
            fail("pinned legacy matrix lower-bound ABI changed")
        for ledger_field in ("'CNUM_PAIR'", "del(i,k)*pr85_qres64",
                             "del(i,k)*pr85_nres64", "residuals:Pa-weighted,not-kg"):
            if ledger_field not in patched:
                fail(f"PBL numerical residual ledger is missing {ledger_field}")
        unit_source = ("module pr85_packet_helper_mod\n  implicit none\ncontains\n" +
                       "\n".join(helpers) +
                       "\nend module pr85_packet_helper_mod\n" + HARNESS)
        (scratch / "unit.f90").write_text(unit_source)
        (scratch / "log").write_text("")
        for opt in ("-O0", "-O2"):
            build_command = [
                "bash", "-c",
                'source "$1" && '
                'if [[ "$2" == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); '
                'else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi && '
                '"$CLOUD_BAL_FC" "${flags[@]}" -free unit.f90 -o "$3"',
                "pr85-pbl-packet-test", str(PROFILE), opt[1:],
                "packet_test" + opt[2:],
            ]
            build = subprocess.run(build_command, cwd=scratch,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            if build.returncode:
                fail(f"pinned Intel {opt} helper build failed:\n" + build.stdout)
            if opt == "-O2" and "#10182" in build.stdout:
                fail("optimized Intel build emitted #10182 (optimization was disabled):\n" +
                     build.stdout)
            if build.stdout.strip():
                print(f"{opt} compiler output:\n{build.stdout.rstrip()}")
            runtime = subprocess.run(
                ["bash", "-c", 'source "$1" && exec "$2"',
                 "pr85-pbl-packet-test", str(PROFILE),
                 str(scratch / ("packet_test" + opt[2:]))], cwd=scratch,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            if runtime.returncode:
                fail(f"packet commit tests failed at {opt}:\n" + runtime.stdout)
            print(opt, runtime.stdout.strip())
        print("PR85_PBL_PACKET_SOURCE_BIND", PATCH.name, "pinned PR74 source")


def test_pbl_packet_quantization_pinned_intel() -> None:
    main()


if __name__ == "__main__":
    main()
