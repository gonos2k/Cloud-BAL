from __future__ import annotations

import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import pr91_fogdes_store_contract as transform

PINNED_FOGDES = ROOT / "docs/evidence/pr91_source_store_contract_20261020/c13/inputs/module_bl_fogdes_c12.F"
STORE_MODULE = ROOT / "docs/evidence/pr91_source_store_contract_20261020/c12/t3_source_replay/cloud_bal_joint_transport.f90"
CONSTANTS = ROOT / "tests/test_pr87_fogdes_model_constants.f90"
PROFILE = ROOT / "tests/intel_toolchain.sh"

DRIVER = r"""
program test_captured_cloud_packet
  use iso_fortran_env, only: real32,real64
  use module_bl_fogdes, only: bl_fogdes_qn
  use cloud_bal_joint_transport, only: joint_moment_store
  implicit none
  integer,parameter :: ims=1,ime=1,jms=1,jme=1,kms=1,kme=2
  integer,parameter :: ids=1,ide=1,jds=1,jde=1,kds=1,kde=2
  integer,parameter :: its=1,ite=1,jts=1,jte=1,kts=1,kte=2
  real(real32) :: vdfg(ims:ime,jms:jme),qc(ims:ime,kms:kme,jms:jme)
  real(real32) :: qnc(ims:ime,kms:kme,jms:jme),qv(ims:ime,kms:kme,jms:jme)
  real(real32) :: temp(ims:ime,kms:kme,jms:jme),rho(ims:ime,kms:kme,jms:jme)
  real(real32) :: dz(ims:ime,kms:kme,jms:jme),dqc(ims:ime,kms:kme,jms:jme)
  real(real32) :: dqnc(ims:ime,kms:kme,jms:jme)
  real(real32) :: ground_q(ims:ime,jms:jme),ground_n(ims:ime,jms:jme)
  real(real64) :: sidecar(ims:ime,kms:kme,jms:jme,2)
  real(real64),parameter :: mmin=523.59881591796875_real64/500000.0_real64**3
  real(real64),parameter :: mmax=523.59881591796875_real64/12000.0_real64**3
  real(real64) :: q_after,n_after,theta_q,theta_n
  real(real32) :: stored_q,stored_n
  integer :: adjustment,store_stage
  logical :: store_valid
  vdfg=0.0_real32; qc=0.0_real32; qnc=0.0_real32; qv=0.0_real32
  temp=280.0_real32; rho=1.08871281147003174_real32; dz=1.0_real32
  ! Exercise a real, nonzero ground flux with the common paired theta.
  qc(1,1,1)=1.0e-5_real32; qnc(1,1,1)=1.0e7_real32
  rho=1.0_real32; dz=100.0_real32; vdfg=1.0e-3_real32
  dqc=0.0_real32; dqnc=0.0_real32; sidecar=0.0_real64
  call bl_fogdes_qn(vdfg,qc,qnc,qv,temp,20.0_real32,rho,dz,1,dqc,dqnc, &
       ids,ide,jds,jde,kds,kde,ims,ime,jms,jme,kms,kme,its,ite,jts,jte,kts,kte, &
       ground_q,ground_n,cloud_source_delta64=sidecar,source_step=3)
  if (ground_q(1,1)<=0.0_real32 .or. ground_n(1,1)<=0.0_real32) stop 11
  q_after=REAL(qc(1,1,1),real64)+20.0_real64*(REAL(dqc(1,1,1),real64)+sidecar(1,1,1,1))
  n_after=REAL(qnc(1,1,1),real64)+20.0_real64*(REAL(dqnc(1,1,1),real64)+sidecar(1,1,1,2))
  call joint_moment_store(q_after,n_after,rho(1,1,1),mmin,mmax,.true., &
       stored_q,stored_n,adjustment,store_valid,allow_normal_q_adjustment=.true., &
       allow_joint_quantum_absence=.true.,strict_mass_ratio=.true.,failure_stage=store_stage)
  if (.not.store_valid .or. store_stage/=0) stop 12
  theta_q=REAL(ground_q(1,1),real64)/(20.0_real64*REAL(rho(1,1,1),real64)* &
       REAL(qc(1,1,1),real64)*REAL(vdfg(1,1),real64))
  theta_n=REAL(ground_n(1,1),real64)/(20.0_real64*REAL(rho(1,1,1),real64)* &
       REAL(qnc(1,1,1),real64)*REAL(vdfg(1,1),real64))
  if (theta_q<=0.0_real64 .or. theta_n<=0.0_real64) stop 13
  if (abs(theta_q-theta_n)>1.0e-6_real64*theta_q) stop 14
  if (abs(REAL(rho(1,1,1),real64)*REAL(dz(1,1,1),real64)* &
       (q_after-REAL(qc(1,1,1),real64))+REAL(ground_q(1,1),real64))>1.0e-10_real64) stop 15
  if (abs(REAL(rho(1,1,1),real64)*REAL(dz(1,1,1),real64)* &
       (n_after-REAL(qnc(1,1,1),real64))+REAL(ground_n(1,1),real64))> &
       1.0e-6_real64*REAL(ground_n(1,1),real64)) stop 16
  if (abs(REAL(stored_q,real64)/REAL(stored_n,real64)- &
       REAL(qc(1,1,1),real64)/REAL(qnc(1,1,1),real64))>1.0e-18_real64) stop 17
  print '(a)','PR91_POSITIVE_FLUX_COMMON_THETA_PASS'
  vdfg=0.0_real32; qc=0.0_real32; qnc=0.0_real32
  rho=1.08871281147003174_real32; dz=1.0_real32
  qc(1,1,1)=7.42170414014253765e-09_real32
  qnc(1,1,1)=1.77180112500000000e+06_real32
  dqc=0.0_real32; dqnc=0.0_real32
  dqc(1,1,1)=8.05719553576000891e-12_real32
  dqnc(1,1,1)=1.92351489257812500e+03_real32
  sidecar=0.0_real64
  call bl_fogdes_qn(vdfg,qc,qnc,qv,temp,20.0_real32,rho,dz,0,dqc,dqnc, &
       ids,ide,jds,jde,kds,kde,ims,ime,jms,jme,kms,kme,its,ite,jts,jte,kts,kte, &
       ground_q,ground_n,cloud_source_delta64=sidecar,source_step=3)
  print '(a)','PR91_RAW_PACKET_CALLBACK_PASS'
  dqc=0.0_real32; dqnc=0.0_real32
  dqc(1,1,1)=8.05719553576000891e-12_real32
  dqnc(1,1,1)=1.92351489257812500e+03_real32
  sidecar=0.0_real64
  sidecar(1,1,1,1)=-1.52211236780719325e-17_real64
  sidecar(1,1,1,2)=-4.95685467740258900e-04_real64
  call bl_fogdes_qn(vdfg,qc,qnc,qv,temp,20.0_real32,rho,dz,0,dqc,dqnc, &
       ids,ide,jds,jde,kds,kde,ims,ime,jms,jme,kms,kme,its,ite,jts,jte,kts,kte, &
       ground_q,ground_n,cloud_source_delta64=sidecar,source_step=3)
  print '(a)','PR91_INVALID_SOURCE_ACCEPTED'
end program test_captured_cloud_packet

subroutine wrf_error_fatal(message)
  character(*),intent(in) :: message
  print '(a)',trim(message)
  stop
end subroutine wrf_error_fatal
"""


class FogdesStoreContractTests(unittest.TestCase):
    def test_transform_is_pinned_and_routes_source_case_to_host_store(self) -> None:
        source = PINNED_FOGDES.read_text()
        self.assertEqual(hashlib.sha256(source.encode()).hexdigest(), transform.FOGDES_SHA256)
        generated = transform.transform_source(source)
        self.assertIn("USE cloud_bal_joint_transport, ONLY: joint_moment_store", generated)
        self.assertIn("strict_mmin,strict_mmax,.TRUE.,stored_q,stored_n", generated)
        self.assertIn("allow_normal_q_adjustment=.TRUE.", generated)
        self.assertIn("allow_joint_quantum_absence=.TRUE.,strict_mass_ratio=.TRUE.", generated)
        self.assertNotIn("qvalue<strict_mmin*nvalue", generated)
        with self.assertRaises(ValueError):
            transform.transform_source(source + "\n")

    def test_captured_raw_and_corrected_packets_on_pinned_intel(self) -> None:
        source = transform.transform_source(PINNED_FOGDES.read_text())
        with tempfile.TemporaryDirectory(prefix="pr91-fogdes-store-", dir="/var/tmp") as temp:
            work = Path(temp)
            (work / "module_bl_fogdes.F90").write_text(source)
            (work / "driver.f90").write_text(DRIVER)
            for profile in ("O0", "O2"):
                build = work / profile
                build.mkdir()
                command = [
                    "bash", "-c",
                    'source "$1/tests/intel_toolchain.sh" && '
                    'if [[ "$2" == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); '
                    'else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi && '
                    '"$CLOUD_BAL_FC" "${flags[@]}" -free -module "$3" -I "$3" '
                    '"$4" "$5" "$6" "$7" -o "$3/test.exe" && "$3/test.exe"',
                    "pr91-fogdes-store-test", str(ROOT), profile, str(build),
                    str(CONSTANTS), str(STORE_MODULE), str(work / "module_bl_fogdes.F90"),
                    str(work / "driver.f90"),
                ]
                result = subprocess.run(command, cwd=build, text=True,
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        check=False)
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertIn("PR91_RAW_PACKET_CALLBACK_PASS", result.stdout)
                self.assertIn("FogDES paired Q/N state outside cloud PSD cone", result.stdout)
                self.assertNotIn("PR91_INVALID_SOURCE_ACCEPTED", result.stdout)


if __name__ == "__main__":
    unittest.main()
