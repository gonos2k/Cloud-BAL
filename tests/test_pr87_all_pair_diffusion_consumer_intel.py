"""Check strict G/B storage with the once-per-RK precision delta on Intel."""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "tests/intel_toolchain.sh"
KERNEL = ROOT / "src/common/cloud_bal_joint_transport.f90"

HARNESS = r"""
program test_graupel_diffusion_delta
  use iso_fortran_env, only: real32, real64
  use cloud_bal_joint_transport, only: joint_moment_store
  implicit none
  real(real64), parameter :: q32rate=900.0000008473793_real64
  real(real64), parameter :: q64rate=899.9999534236954_real64
  real(real64), parameter :: b32rate=1.0_real64, b64rate=1.0_real64
  real(real64), parameter :: dq=q64rate-q32rate, db=b64rate-b32rate
  real(real64), parameter :: rk_fraction(3)=[1.0_real64/3.0_real64,0.5_real64,1.0_real64]
  real(real32) :: qstored,bstored
  real(real64) :: qstage,bstage,twice_q
  integer :: adjustment,stage,failures
  logical :: valid
  failures=0

  call joint_moment_store(q32rate,b32rate,1.0_real32,100.0_real64,900.0_real64, &
       .true.,qstored,bstored,adjustment,valid,strict_mass_ratio=.true.)
  call check(.not.valid, 'uncorrected R32 G/B source ratio is strictly rejected', failures)

  do stage=1,3
    qstage=rk_fraction(stage)*(q32rate+dq)
    bstage=rk_fraction(stage)*(b32rate+db)
    twice_q=rk_fraction(stage)*(q32rate+2.0_real64*dq)
    call check(qstage/bstage>=100.0_real64 .and. qstage/bstage<=900.0_real64, &
         'corrected G/B source endpoint is inside exact 100..900 bounds', failures)
    call check(qstage==rk_fraction(stage)*q64rate, &
         'RK endpoint consumes the captured delta once', failures)
    call check(qstage/=twice_q, 'RK endpoint does not apply delta twice', failures)
    call joint_moment_store(qstage,bstage,1.0_real32,100.0_real64,900.0_real64, &
         .true.,qstored,bstored,adjustment,valid,strict_mass_ratio=.true.)
    call check(valid, 'strict native G/B storage accepts the corrected endpoint', failures)
  enddo

  if (failures/=0) stop 1
  print *, 'PR87_ALL_PAIR_DIFFUSION_CONSUMER_PASS'
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
end program test_graupel_diffusion_delta
"""


def test_pinned_intel_strict_graupel_pair_o0_o2() -> None:
    assert KERNEL.is_file()
    with tempfile.TemporaryDirectory(prefix="pr87-all-pair-consumer-", dir="/var/tmp") as tmp:
        scratch = Path(tmp)
        (scratch / "kernel.f90").write_bytes(KERNEL.read_bytes())
        (scratch / "driver.f90").write_text(HARNESS)
        for opt, flags in (("O0", "CLOUD_BAL_FREE_FLAGS"),
                           ("O2", "CLOUD_BAL_REPRO_FLAGS")):
            exe = scratch / f"g_pair_{opt}"
            build = subprocess.run(
                ["bash", "-c",
                 'source "$1" && flags=("${' + flags + '[@]}") && '
                 '"$CLOUD_BAL_FC" "${flags[@]}" -free kernel.f90 driver.f90 -o "$2"',
                 "pr87-all-pair-consumer", str(PROFILE), str(exe)],
                cwd=scratch, text=True, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, check=False)
            assert build.returncode == 0, f"Intel {opt} compile failed:\n{build.stdout}"
            assert "#10182" not in build.stdout, build.stdout
            run = subprocess.run(
                ["bash", "-c", 'source "$1" && exec "$2"',
                 "pr87-all-pair-consumer", str(PROFILE), str(exe)],
                cwd=scratch, text=True, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, check=False)
            assert run.returncode == 0, f"Intel {opt} runtime failed:\n{run.stdout}"
            assert "PR87_ALL_PAIR_DIFFUSION_CONSUMER_PASS" in run.stdout
