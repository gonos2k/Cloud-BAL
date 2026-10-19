#!/usr/bin/env python3
"""Check optional store failure reasons without changing legacy results."""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DRIVER = r'''program test_pr90_joint_store_reason
  use iso_fortran_env, only: real32, real64
  use cloud_bal_joint_transport, only: joint_moment_store
  implicit none
  real(real64) :: q, n, low, high, bounds(2), inactive
  real(real32) :: old_q, old_n, new_q, new_n, rho
  integer :: old_adjustment, new_adjustment, stage, failures
  logical :: old_valid, new_valid, allow_normal, allow_subnormal, strict_mass

  failures=0
  rho=1.0_real32
  inactive=0.0_real64
  allow_normal=.false.
  allow_subnormal=.false.
  strict_mass=.false.

  ! Success: omitted and present stage arguments must produce identical bits.
  q=1.0e-6_real64; n=1.0e3_real64; low=1.0e-10_real64; high=1.0e-8_real64
  call compare_calls(q,n,rho,low,high,allow_subnormal,allow_normal,strict_mass,inactive,0)

  ! Early input/configuration gate.
  call compare_calls(q,n,rho,low,high,allow_subnormal,allow_normal,strict_mass, &
                     -1.0_real64,1)

  ! Continuous mass gate.
  q=1.0e-3_real64; n=1.0e3_real64
  call compare_calls(q,n,rho,1.0e-10_real64,1.0e-8_real64,allow_subnormal, &
                     allow_normal,strict_mass,0.0_real64,2)

  ! Continuous volume contract gate.
  q=1.0e-6_real64; n=1.0e3_real64
  bounds=[2.0_real64,3.0_real64]
  call compare_volume(q,n,rho,1.0e-10_real64,1.0e-8_real64,bounds,3)

  ! REAL32 overflow gate.
  q=2.0e40_real64; n=2.0e49_real64
  strict_mass=.true.
  call compare_calls(q,n,rho,1.0e-10_real64,1.0e-8_real64,allow_subnormal, &
                     allow_normal,strict_mass,0.0_real64,4)

  ! Strict point interval has no REAL32 Q representation after N rounding.
  q=1.0e-6_real64; n=1.0e3_real64; strict_mass=.true.; allow_normal=.true.
  low=q/n
  call compare_calls(q,n,rho,low,low,allow_subnormal, &
                     allow_normal,strict_mass,0.0_real64,5)

  ! Continuous volume passes, but rounded Q needs a downward repair to zero;
  ! the resulting Q/N pair fails, exercising the legacy fallback return.
  strict_mass=.false.; allow_normal=.false.; allow_subnormal=.true.
  q=0.6_real64*real(nearest(0.0_real32,1.0_real32),real64); n=1.0_real64
  bounds=[1.1e45_real64,1.3e45_real64]
  call compare_volume_fallback(q,n,rho,1.0e-46_real64,2.0e-45_real64,bounds,6)

  if (failures/=0) error stop 1
  print '(a)', 'PR90 joint store failure reason cases PASS'
contains
  subroutine compare_calls(qv,nv,density,minr,maxr,subnormal,normal,strict,inactivev,want)
    real(real64), intent(in) :: qv,nv,minr,maxr,inactivev
    real(real32), intent(in) :: density
    logical, intent(in) :: subnormal,normal,strict
    integer, intent(in) :: want
    call joint_moment_store(qv,nv,density,minr,maxr,subnormal,old_q,old_n, &
        old_adjustment,old_valid,allow_normal_q_adjustment=normal, &
        allow_joint_quantum_absence=.false.,strict_mass_ratio=strict, &
        inactive_mass_limit=inactivev)
    call joint_moment_store(qv,nv,density,minr,maxr,subnormal,new_q,new_n, &
        new_adjustment,new_valid,allow_normal_q_adjustment=normal, &
        allow_joint_quantum_absence=.false.,strict_mass_ratio=strict, &
        inactive_mass_limit=inactivev,failure_stage=stage)
    call check_pair(want)
  end subroutine compare_calls

  subroutine compare_volume(qv,nv,density,minr,maxr,boundsv,want)
    real(real64), intent(in) :: qv,nv,minr,maxr,boundsv(2)
    real(real32), intent(in) :: density
    integer, intent(in) :: want
    call joint_moment_store(qv,nv,density,minr,maxr,.false.,old_q,old_n, &
        old_adjustment,old_valid,.false.,.false.,boundsv)
    call joint_moment_store(qv,nv,density,minr,maxr,.false.,new_q,new_n, &
        new_adjustment,new_valid,.false.,.false.,boundsv,failure_stage=stage)
    call check_pair(want)
  end subroutine compare_volume

  subroutine compare_volume_fallback(qv,nv,density,minr,maxr,boundsv,want)
    real(real64), intent(in) :: qv,nv,minr,maxr,boundsv(2)
    real(real32), intent(in) :: density
    integer, intent(in) :: want
    call joint_moment_store(qv,nv,density,minr,maxr,.true.,old_q,old_n, &
        old_adjustment,old_valid,allow_normal_q_adjustment=.false., &
        allow_joint_quantum_absence=.false.,volume_number_bounds=boundsv)
    call joint_moment_store(qv,nv,density,minr,maxr,.true.,new_q,new_n, &
        new_adjustment,new_valid,allow_normal_q_adjustment=.false., &
        allow_joint_quantum_absence=.false.,volume_number_bounds=boundsv, &
        failure_stage=stage)
    call check_pair(want)
  end subroutine compare_volume_fallback

  subroutine check_pair(want)
    integer, intent(in) :: want
    if (transfer(old_q,0)/=transfer(new_q,0) .or. &
        transfer(old_n,0)/=transfer(new_n,0) .or. old_adjustment/=new_adjustment .or. &
        (old_valid .neqv. new_valid) .or. (old_valid .neqv. (want==0)) .or. &
        (new_valid .neqv. (want==0)) .or. stage/=want) then
      print *, 'failure stage expected/actual',want,stage
      print *, 'legacy/new q,n,adjustment,valid',old_q,old_n,old_adjustment,old_valid, &
               new_q,new_n,new_adjustment,new_valid
      failures=failures+1
    end if
  end subroutine check_pair
end program test_pr90_joint_store_reason
'''


def test_pr90_joint_store_reason() -> None:
    source = ROOT / 'src/common/cloud_bal_joint_transport.f90'
    scratch = Path(tempfile.mkdtemp(prefix='pr90_joint_store_reason_', dir='/var/tmp'))
    driver = scratch / 'test_pr90_joint_store_reason.f90'
    driver.write_text(DRIVER)
    for profile in ('O0', 'O2'):
        build = scratch / profile
        build.mkdir()
        command = [
            'bash', '-c',
            'source "$1/tests/intel_toolchain.sh" && '
            'if [[ "$2" == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); '
            'else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi && '
            '"$CLOUD_BAL_FC" "${flags[@]}" -free -module "$4" -I "$4" '
            '"$3" "$5" -o "$4/test.exe" && "$4/test.exe"',
            'pr90-joint-store-reason-test', str(ROOT), profile,
            str(source), str(build), str(driver),
        ]
        result = subprocess.run(command, cwd=build, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                check=False)
        assert result.returncode == 0, result.stdout
        assert 'PR90 joint store failure reason cases PASS' in result.stdout, result.stdout
        print(f'{profile}: {result.stdout.strip()}')


if __name__ == '__main__':
    test_pr90_joint_store_reason()
    print('PR90 joint store failure reason Intel test PASS')
