from __future__ import annotations

import sys
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import pr91_source_first_diffusion_c11 as transform

C10_MODULE = Path("/var/tmp/pr91_sources_c10_20261020/module_em.F")
C11_MODULE = Path("/var/tmp/pr91_sources_c11_20261020d/module_em.F")
PROFILE = ROOT / "tests/intel_toolchain.sh"


class SourceFirstDiffusionC11Tests(unittest.TestCase):
    def test_c11_capture_is_bound_to_immutable_c10_and_guard(self) -> None:
        if not C10_MODULE.exists():
            self.skipTest("immutable C10 source is external to this checkout")
        original = C10_MODULE.read_text()
        transformed = transform.transform_c10_module(original)
        self.assertEqual(transform.sha256(original), transform.C10_MODULE_SHA256)
        self.assertIn("VIRTUAL_DONOR_STAGE", transformed)
        self.assertIn("VDS_SOURCE_DIFFUSION", transformed)
        self.assertIn("VDS_Q_STENCIL", transformed)
        self.assertIn("VDS_N_STENCIL", transformed)
        self.assertIn("VDS_GEOMETRY_FACE", transformed)
        self.assertIn("VDS_OPERANDS_R32", transformed)
        self.assertIn("VDS_OPERANDS_R64", transformed)
        self.assertIn("stage_diag_qdiff=prepared_diffusion(i,k,j)", transformed)
        self.assertIn("stage_diag_ndiff=prepared_n_diffusion(i,k,j)", transformed)
        self.assertIn("pr87_all_pair_diffusion_old(i,k,j,2*p-1)", transformed)
        self.assertEqual(transformed.count("VIRTUAL_DONOR_STAGE"), 1)
        self.assertEqual(transformed.count("PR87 unsafe complete source-prepared virtual donor"), 1)
        # Removing C11's two diagnostic-only insertions restores C10 byte-for-byte.
        without_capture = transformed
        start = without_capture.index(
            "        IF (.NOT.prepared_donor_is_safe(source_sum64(1),source_sum64(2),drydensity(cell))) THEN\n"
            "          ! Failed-call-only C11 capture.")
        end = without_capture.index(
            "          CALL wrf_error_fatal('PR87 unsafe complete source-prepared virtual donor')\n"
            "        END IF\n", start) + len(
            "          CALL wrf_error_fatal('PR87 unsafe complete source-prepared virtual donor')\n"
            "        END IF\n")
        without_capture = without_capture[:start] + (
            "        IF (.NOT.prepared_donor_is_safe(source_sum64(1),source_sum64(2),drydensity(cell))) &\n"
            "          CALL wrf_error_fatal('PR87 unsafe complete source-prepared virtual donor')\n") + without_capture[end:]
        without_capture = without_capture.replace(
            "  INTEGER :: stage_diag_u,stage_diag_dx,stage_diag_dy\n"
            "  REAL(real64) :: stage_diag_qdiff,stage_diag_ndiff\n", "", 1)
        self.assertEqual(without_capture, original)

    def test_extracted_capture_writes_typed_hex_records_with_pinned_ifx(self) -> None:
        if not (C10_MODULE.exists() and C11_MODULE.exists()):
            self.skipTest("pinned C10/C11 host sources are external to this checkout")
        c10 = C10_MODULE.read_text()
        c11 = C11_MODULE.read_text()
        module_start = c10.index("MODULE pr87_horizontal_diffusion64")
        module_end = c10.index("END MODULE pr87_horizontal_diffusion64", module_start)
        kernel = c10[module_start:module_end + len("END MODULE pr87_horizontal_diffusion64")]
        start = c11.index(
            "        IF (.NOT.prepared_donor_is_safe(source_sum64(1),source_sum64(2),drydensity(cell))) THEN\n"
            "          ! Failed-call-only C11 capture.")
        end = c11.index(
            "          CALL wrf_error_fatal('PR87 unsafe complete source-prepared virtual donor')\n"
            "        END IF\n", start) + len(
            "          CALL wrf_error_fatal('PR87 unsafe complete source-prepared virtual donor')\n"
            "        END IF\n")
        capture = c11[start:end]
        driver = r"""
program test_c11_capture
  use iso_fortran_env, only: int32,int64,real32,real64
  use pr87_horizontal_diffusion64, only: horizontal_diffusion64
  implicit none
  integer :: itimestep,rk,p,i,j,k,cell,stage_diag_u,stage_diag_dx,stage_diag_dy
  integer :: ims,ime,kms,kme,jms,jme
  real(real32) :: dt,rdx,rdy,c1(1),c2(1)
  real(real32) :: oldcarrier(1),newcarrier(1),drydensity(1),qb(1,1),nb(1,1)
  real(real32) :: prepared_q(1:5,1:1,1:5,1),prepared_n(1:5,1:1,1:5,1)
  real(real32) :: mut_diff(1:5,1:5),xkmhd_diff(1:5,1:1,1:5)
  real(real32) :: msfux_diff(1:5,1:5),msfuy_diff(1:5,1:5)
  real(real32) :: msfvx_inv_diff(1:5,1:5),msfvy_diff(1:5,1:5)
  real(real32) :: msftx(1:5,1:5),msfty(1:5,1:5)
  real(real64) :: source_sum64(2),qs64(1,1),ns64(1,1),stage_diag_qdiff,stage_diag_ndiff
  real(real64) :: prepared_diffusion(1:5,1:1,1:5),prepared_n_diffusion(1:5,1:1,1:5)
  real(real64) :: pr87_later_qsrc(1:5,1:1,1:5,1),pr87_later_nsrc(1:5,1:1,1:5,1)
  real(real64) :: pr87_all_pair_diffusion_delta(1:5,1:1,1:5,8)
  real(real64) :: pr87_all_pair_diffusion_old(1:5,1:1,1:5,4)
  real(real64) :: minmass(1),maxmass(1),number_bounds(1,2,1)
  ims=1; ime=5; kms=1; kme=1; jms=1; jme=5
  itimestep=2; rk=3; p=1; i=3; j=3; k=1; cell=1
  dt=20.0_real32; rdx=1.0_real32; rdy=1.0_real32; c1=1.0_real32; c2=0.0_real32
  oldcarrier=1.25_real32; newcarrier=1.5_real32; drydensity=0.9_real32
  qb=2.0_real32; nb=3.0_real32; source_sum64=[-1.0_real64,3.0_real64]
  qs64=4.0_real64; ns64=5.0_real64; minmass=6.0_real64; maxmass=7.0_real64
  number_bounds(1,1,1)=8.0_real64; number_bounds(1,2,1)=9.0_real64
  prepared_q=10.0_real32; prepared_n=11.0_real32; mut_diff=1.0_real32
  xkmhd_diff=1.0_real32; msfux_diff=1.0_real32; msfuy_diff=1.0_real32
  msfvx_inv_diff=1.0_real32; msfvy_diff=1.0_real32; msftx=1.0_real32; msfty=1.0_real32
  pr87_later_qsrc=12.0_real64; pr87_later_nsrc=13.0_real64
  pr87_all_pair_diffusion_delta=14.0_real64; pr87_all_pair_diffusion_old=15.0_real64
  if (.not.prepared_donor_is_safe(source_sum64(1),source_sum64(2),drydensity(1))) then
CAPTURE_BLOCK
  endif
contains
  logical function prepared_donor_is_safe(q,n,rho)
    real(real64),intent(in)::q,n
    real(real32),intent(in)::rho
    prepared_donor_is_safe=.false.
  end function
  subroutine wrf_error_fatal(message)
    character(*),intent(in)::message
    print '(a)',trim(message)
  end subroutine
end program
"""
        driver = driver.replace("CAPTURE_BLOCK", "\n".join("    " + line for line in capture.splitlines()))
        with tempfile.TemporaryDirectory(prefix="pr91-c11-writer-", dir="/var/tmp") as tmp:
            work = Path(tmp)
            (work / "kernel.f90").write_text(kernel)
            (work / "driver.f90").write_text(driver)
            for level in ("O0", "O2"):
                exe = work / f"capture_{level}.exe"
                build = subprocess.run(
                    ["bash", "-c",
                     'source "$1" && if [[ "$2" == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); '
                     'else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi && '
                     '"$CLOUD_BAL_FC" "${flags[@]}" -free kernel.f90 driver.f90 -o "$3"',
                     "pr91-c11", str(PROFILE), level, str(exe)], cwd=work,
                    text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
                self.assertEqual(build.returncode, 0, f"{level} build: {build.stdout}")
                (work / "pr85_joint_source_failure.raw").unlink(missing_ok=True)
                run = subprocess.run(
                    ["bash", "-c", 'source "$1" && exec "$2"', "pr91-c11", str(PROFILE), str(exe)],
                    cwd=work, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
                self.assertEqual(run.returncode, 0, f"{level} run: {run.stdout}")
                lines = (work / "pr85_joint_source_failure.raw").read_text().splitlines()
                self.assertEqual(len(lines), 17)
                self.assertEqual(lines[0].split()[0], "VIRTUAL_DONOR_STAGE")
                self.assertEqual(len(lines[0].split()), 9, lines[0])
                self.assertEqual(lines[1].split()[0], "VDS_OPERANDS_R32")
                self.assertEqual(len(lines[1].split()), 7)
                self.assertEqual([len(value) for value in lines[1].split()[1:]], [8] * 6)
                self.assertEqual(lines[2].split()[0], "VDS_OPERANDS_R64")
                self.assertEqual(len(lines[2].split()), 3)
                self.assertEqual([len(value) for value in lines[2].split()[1:]], [16] * 2)
                self.assertEqual(lines[3].split()[0], "VDS_SOURCE_DIFFUSION")
                self.assertEqual(len(lines[3].split()), 13)
                self.assertEqual([len(value) for value in lines[3].split()[1:]], [16] * 12)
                for index in (4, 6, 8):
                    self.assertEqual(lines[index].split()[0], "VDS_Q_STENCIL")
                    self.assertEqual(len(lines[index].split()), 7)
                    self.assertEqual([len(value) for value in lines[index].split()[-3:]], [8] * 3)
                for index in (5, 7, 9):
                    self.assertEqual(lines[index].split()[0], "VDS_N_STENCIL")
                    self.assertEqual(len(lines[index].split()), 7)
                    self.assertEqual([len(value) for value in lines[index].split()[-3:]], [8] * 3)
                self.assertEqual(lines[10].split()[0], "VDS_DIFFUSIVITY")
                self.assertEqual(len(lines[10].split()), 4)
                for index in (11, 12, 13):
                    self.assertEqual(lines[index].split()[0], "VDS_GEOMETRY_X")
                    self.assertEqual(len(lines[index].split()), 10)
                    self.assertEqual([len(value) for value in lines[index].split()[-6:]], [8] * 6)
                self.assertEqual(lines[14].split()[0], "VDS_GEOMETRY_FACE")
                self.assertEqual(len(lines[14].split()), 10)
                self.assertEqual(lines[15].split()[0], "VDS_GEOMETRY_Y")
                self.assertEqual(len(lines[15].split()), 7)
                self.assertEqual(lines[16].split()[0], "VDS_RDY")
                self.assertEqual(len(lines[16].split()), 2)
                self.assertEqual(run.stdout.strip(), "PR87 unsafe complete source-prepared virtual donor")


if __name__ == "__main__":
    unittest.main()
