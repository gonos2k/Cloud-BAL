from __future__ import annotations
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pr91_source_store_contract as contract

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "tests/intel_toolchain.sh"
KERNEL = ROOT / "src/common/cloud_bal_joint_transport.f90"

HARNESS = r"""
program test_source_first_volume_gate
  use iso_fortran_env, only: real32, real64
  use cloud_bal_joint_transport, only: joint_moment_store
  implicit none
  real(real64), parameter :: q_bad=6.92664232070072504e-6_real64
  real(real64), parameter :: n=1.65361391965649796e9_real64
  real(real64), parameter :: rho=1.09104347229003906_real64
  real(real64), parameter :: lower_ratio=4.18879052734374980e-15_real64
  real(real64), parameter :: upper_ratio=3.03008574026602271e-10_real64
  real(real64), parameter :: bounds(2)=[3.60070164943336630e9_real64, &
                                        2.60467422557390469e14_real64]
  real(real64) :: q_good, number_volume
  real(real32) :: q_stored,n_stored,nv32
  integer :: adjustment,failure_stage,failures
  logical :: valid
  failures=0
  call joint_moment_store(q_bad,n,real(rho,real32),lower_ratio,upper_ratio,.true., &
       q_stored,n_stored,adjustment,valid,allow_normal_q_adjustment=.true., &
       allow_joint_quantum_absence=.true.,volume_number_bounds=bounds, &
       failure_stage=failure_stage)
  call check(.not.valid .and. failure_stage==3, &
       'captured full candidate is rejected at volume gate 3',failures)
  call joint_moment_store(q_bad,n,real(rho,real32),lower_ratio,upper_ratio,.true., &
       q_stored,n_stored,adjustment,valid,allow_normal_q_adjustment=.true., &
       allow_joint_quantum_absence=.true.,strict_mass_ratio=.true., &
       volume_number_bounds=bounds,failure_stage=failure_stage)
  call check(.not.valid .and. failure_stage==2, &
       'same source endpoint is rejected by the stricter source-stage mass gate',failures)
  q_good=q_bad*(1.0_real64+1.0e-5_real64)
  call joint_moment_store(q_good,n,real(rho,real32),lower_ratio,upper_ratio,.true., &
       q_stored,n_stored,adjustment,valid,allow_normal_q_adjustment=.true., &
       allow_joint_quantum_absence=.true.,strict_mass_ratio=.true., &
       volume_number_bounds=bounds,failure_stage=failure_stage)
  call check(valid .and. failure_stage==0, &
       'nearby continuous source endpoint passes the strict source-stage contract',failures)
  if (valid) then
    call check(real(q_stored,real64)/real(n_stored,real64)>=lower_ratio .and. &
         real(q_stored,real64)/real(n_stored,real64)<=upper_ratio, &
         'stored mean mass remains inside exact bounds',failures)
    number_volume=real(n_stored,real64)*rho
    nv32=real(number_volume,real32)
    call check(real(nv32,real64)>=bounds(1)*real(q_stored,real64) .and. &
         real(nv32,real64)<=bounds(2)*real(q_stored,real64), &
         'stored R32 Q/N satisfies the existing rounded volume contract',failures)
  endif
  if (failures/=0) stop 1
  print *, 'PR91_SOURCE_FIRST_VOLUME_GATE_PASS'
contains
  subroutine check(ok,label,nfail)
    logical,intent(in) :: ok
    character(*),intent(in) :: label
    integer,intent(inout) :: nfail
    if (.not.ok) then
      print *, 'FAIL: ',label
      nfail=nfail+1
    endif
  end subroutine check
end program test_source_first_volume_gate
"""


INITIAL = """subroutine prepare_source_first_rates()
        IF (p==1) THEN
          CALL joint_moment_store(source_candidate(1),source_candidate(2),drydensity(cell), &
               minmass(p),maxmass(p),.TRUE.,source_endpoint32(1),source_endpoint32(2), &
               adjustment,full_valid,allow_normal_q_adjustment=.TRUE., &
               allow_joint_quantum_absence=.TRUE.,strict_mass_ratio=.TRUE.)
        ELSE
          CALL joint_moment_store(source_candidate(1),source_candidate(2),drydensity(cell), &
               minmass(p),maxmass(p),.TRUE.,source_endpoint32(1),source_endpoint32(2), &
               adjustment,full_valid,allow_normal_q_adjustment=.TRUE., &
               allow_joint_quantum_absence=.TRUE., &
               inactive_mass_limit=MERGE(REAL(NEAREST(1.e-14,-1.0),real64),0.0_real64,p==2))
        END IF
        IF (.NOT.full_valid) CALL wrf_error_fatal('failed')
"""
FALLBACK = """        IF (.NOT.prepared_donor_is_safe(source_endpoint32(1),source_endpoint32(2),drydensity(cell))) THEN
          CALL joint_moment_store(source_candidate(1),source_candidate(2),drydensity(cell), &
               minmass(p),maxmass(p),.TRUE.,source_endpoint32(1),source_endpoint32(2),adjustment,full_valid, &
               allow_normal_q_adjustment=.TRUE.,allow_joint_quantum_absence=.TRUE., &
                 inactive_mass_limit=MERGE(REAL(NEAREST(1.e-14,-1.0),real64),0.0_real64,p==2))
        END IF
        donor_q(i,k,j,p)=source_endpoint32(1)
"""


class SourceStoreContractTests(unittest.TestCase):
    def test_connects_existing_volume_bounds_to_both_cloud_stores(self) -> None:
        original = INITIAL + FALLBACK
        transformed = contract.transform_source(original)
        self.assertEqual(transformed.count("volume_number_bounds=number_bounds(cell,:,p)"), 2)
        self.assertEqual(transformed.count("strict_mass_ratio=.TRUE."), 2)
        self.assertIn("donor_q(i,k,j,p)=source_endpoint32(1)", transformed)
        self.assertIn("inactive_mass_limit=MERGE", transformed)
        self.assertNotIn("tolerance", transformed.lower())
        self.assertNotIn("source_endpoint32(1)=", transformed)

    def test_fails_closed_on_anchor_drift_or_double_application(self) -> None:
        with self.assertRaisesRegex(ValueError, "initial strict source-first cloud store"):
            contract.transform_source("unrelated source")
        with self.assertRaisesRegex(ValueError, "already applied"):
            contract.transform_source(contract.INITIAL_CLOUD_CALL_WITH_VOLUME + "\n" + FALLBACK)

    def test_output_is_not_overwritten(self) -> None:
        fixture = INITIAL + FALLBACK
        with tempfile.TemporaryDirectory(prefix="pr91-source-contract-output-") as tmp:
            folder = Path(tmp)
            source = folder / "pinned.f"
            output = folder / "candidate.f"
            source.write_text(fixture)
            output.write_text("keep this content")
            with patch.object(contract, "PINNED_HOST_SHA256",
                              hashlib.sha256(fixture.encode()).hexdigest()):
                with self.assertRaises(FileExistsError):
                    contract.transform_file(source, output)
            self.assertEqual(output.read_text(), "keep this content")

    def test_pinned_intel_rejects_bad_endpoint_and_accepts_valid_neighbor(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pr91-source-volume-", dir="/var/tmp") as tmp:
            scratch = Path(tmp)
            (scratch / "kernel.f90").write_bytes(KERNEL.read_bytes())
            (scratch / "driver.f90").write_text(HARNESS)
            exe = scratch / "source_volume_gate.exe"
            build = subprocess.run(
                ["bash", "-c",
                 'source "$1" && "$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" '
                 '-free kernel.f90 driver.f90 -o "$2"',
                 "pr91-source-volume-gate", str(PROFILE), str(exe)],
                cwd=scratch, text=True, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, check=False)
            self.assertEqual(build.returncode, 0, build.stdout)
            run = subprocess.run(
                ["bash", "-c", 'source "$1" && exec "$2"',
                 "pr91-source-volume-gate", str(PROFILE), str(exe)],
                cwd=scratch, text=True, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, check=False)
            self.assertEqual(run.returncode, 0, run.stdout)
            self.assertIn("PR91_SOURCE_FIRST_VOLUME_GATE_PASS", run.stdout)


if __name__ == "__main__":
    unittest.main()
