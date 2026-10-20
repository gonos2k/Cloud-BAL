from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import pr91_source_first_diffusion as transform

PROFILE = ROOT / "tests/intel_toolchain.sh"
KERNEL = ROOT / "tools/pr87_horizontal_diffusion64.f90"
PINNED_MODULE = Path("/var/tmp/pr91_native_build_d3_20261020/source/overrides/module_em_c8.F")
PINNED_SOLVE = Path("/var/tmp/pr91_native_build_d3_20261020/source/overrides/solve_em.F")

HARNESS = r"""
program test_source_prepared_diffusion
  use iso_fortran_env, only: real32, real64
  use pr87_horizontal_diffusion64, only: horizontal_diffusion64
  implicit none
  real(real32) :: oldq(1:10,1:1,1:3), oldn(1:10,1:1,1:3)
  real(real32) :: preparedq(1:10,1:1,1:3), preparedn(1:10,1:1,1:3)
  real(real32) :: mut(1:10,1:3), c1(1:1), c2(1:1)
  real(real32) :: ux(1:10,1:3), uy(1:10,1:3), vxinv(1:10,1:3), vy(1:10,1:3)
  real(real32) :: tx(1:10,1:3), ty(1:10,1:3), xkmhd(1:10,1:1,1:3)
  real(real32) :: qb(1,2),nb(1,2)
  real(real64) :: oldcarrier(1),qs64(1,2),ns64(1,2),source_sum64(2),dt
  real(real64) :: doldq(1:10,1:1,1:3), doldn(1:10,1:1,1:3)
  real(real64) :: dnewq(1:10,1:1,1:3), dnewn(1:10,1:1,1:3)
  real(real64) :: stale, corrected
  integer :: cell,p
  oldq=100.0_real32; oldn=1.0_real32
  preparedq=100.0_real32; preparedn=1.0_real32
  oldq(5,1,2)=900.0_real32
  mut=1.0_real32; c1=1.0_real32; c2=0.0_real32
  ux=1.0_real32; uy=1.0_real32; vxinv=1.0_real32; vy=1.0_real32
  tx=1.0_real32; ty=1.0_real32; xkmhd=1.0_real32
  dt=1.0_real64
  call horizontal_diffusion64(oldq,mut,c1,c2,ux,uy,vxinv,vy,tx,ty,xkmhd, &
       1.0_real32,0.0_real32,1,10,1,1,1,3,2,9,2,2,1,1,doldq)
  call horizontal_diffusion64(oldn,mut,c1,c2,ux,uy,vxinv,vy,tx,ty,xkmhd, &
       1.0_real32,0.0_real32,1,10,1,1,1,3,2,9,2,2,1,1,doldn)
  call horizontal_diffusion64(preparedq,mut,c1,c2,ux,uy,vxinv,vy,tx,ty,xkmhd, &
       1.0_real32,0.0_real32,1,10,1,1,1,3,2,9,2,2,1,1,dnewq)
  call horizontal_diffusion64(preparedn,mut,c1,c2,ux,uy,vxinv,vy,tx,ty,xkmhd, &
       1.0_real32,0.0_real32,1,10,1,1,1,3,2,9,2,2,1,1,dnewn)
  if (preparedq(5,1,2)/=100.0_real32 .or. preparedn(5,1,2)/=1.0_real32) stop 1
  stale=real(preparedq(5,1,2),real64)+dt*doldq(5,1,2)
  corrected=real(preparedq(5,1,2),real64)+dt*(doldq(5,1,2)+(dnewq(5,1,2)-doldq(5,1,2)))
  if (stale>=100.0_real64 .or. corrected/=100.0_real64) stop 2
  if (abs(sum(doldq(2:9,1,2))-0.0_real64)>1.0e-12_real64) stop 3
  if (any(preparedq([1,10],1,2)/=oldq([1,10],1,2))) stop 4
  if (any(dnewq(2:9,1,2)/=0.0_real64) .or. any(dnewn(2:9,1,2)/=0.0_real64)) stop 5
  qb(1,1)=100.0_real32; nb(1,1)=1.0_real32; oldcarrier(1)=1.0_real64
  qs64(1,1)=dnewq(5,1,2); ns64(1,1)=dnewn(5,1,2); cell=1; p=1
  ! C9 donor formula is inserted from the production transform below.
  C9_DONOR_FORMULA
  if (source_sum64(1)/=100.0_real64.or.source_sum64(2)/=1.0_real64) stop 6
  if (.not.cache_presence_ok(.true.,.true.,.true.)) stop 7
  if (.not.cache_presence_ok()) stop 8
  if (cache_presence_ok(.true.)) stop 9
  print *, 'PR91_SOURCE_PREPARED_DIFFUSION_PASS',doldq(5,1,2),doldq(6,1,2)
contains
  logical function cache_presence_ok(old_cache,bounds,valid)
    logical,optional,intent(in) :: old_cache,bounds,valid
    cache_presence_ok=.NOT.((PRESENT(old_cache) .NEQV. PRESENT(bounds)).OR. &
         (PRESENT(old_cache) .NEQV. PRESENT(valid)))
  end function cache_presence_ok
end program test_source_prepared_diffusion
"""


class SourceFirstDiffusionTests(unittest.TestCase):
    def test_transform_is_bound_to_c8_and_c7_solve(self) -> None:
        self.assertEqual(transform.MODULE_SHA256,
                         "de21c8b0aad8c99ae1ed7de4e0e4fc77ebfc6050f998754c7ee6c3d27bfc90a2")
        self.assertEqual(transform.SOLVE_SHA256,
                         "412183300ea8dd6af028ac1a5254f937477b054630db4eb1f5910a6bf974c3c5")
        self.assertEqual(transform._DIFFUSION_AND_DONOR_PASS.count("horizontal_diffusion64("), 2)
        self.assertIn("prepared_diffusion(i,k,j)-pr87_all_pair_diffusion_old",
                      transform._DIFFUSION_AND_DONOR_PASS)
        self.assertIn("SOURCE_DIFFUSION_DELTA", transform._DIFFUSION_AND_DONOR_PASS)

    def test_pinned_transform_emits_source_prepared_consumer(self) -> None:
        if not (PINNED_MODULE.exists() and PINNED_SOLVE.exists()):
            self.skipTest("D3 C8 native-build inputs are external to this source checkout")
        module = transform.transform_module(PINNED_MODULE.read_text())
        solve = transform.transform_solve(PINNED_SOLVE.read_text())
        self.assertIn("all_pair_diffusion_old(pr87_diff_i,pr87_diff_k", module)
        self.assertIn("prepared_q(i,k,j,p)=source_endpoint32(1)", module)
        self.assertLess(module.index("prepared_q(i,k,j,p)=source_endpoint32(1)"),
                        module.index("CALL horizontal_diffusion64(prepared_q"))
        self.assertLess(module.index("CALL horizontal_diffusion64(prepared_q"),
                        module.index("source_sum64=(REAL(oldcarrier(cell),real64)*REAL([qb(cell,p),nb(cell,p)],real64)"))
        self.assertIn("PR91 diffusion bounds differ from prepared source footprint", module)
        self.assertIn("missing paired old diffusion cache channel", module)
        self.assertIn("producer diffusion bounds changed within RK1", module)
        self.assertIn("(PRESENT(all_pair_diffusion_old) .NEQV.", module)
        self.assertIn("prepared_n_diffusion", module)
        self.assertNotIn("old_diffusion(:,:,:)\n", module)
        self.assertIn("all_pair_diffusion_old=pr87_all_pair_diffusion_old", solve)
        self.assertIn("pr87_all_pair_diffusion_identity", solve)
        self.assertIn("pr87_all_pair_diffusion_valid", solve)

    def test_pinned_intel_operator_checks_replacement_and_conservation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pr91-source-diffusion-", dir="/var/tmp") as tmp:
            work = Path(tmp)
            (work / "kernel.f90").write_bytes(KERNEL.read_bytes())
            donor_lines = transform._DIFFUSION_AND_DONOR_PASS.splitlines()
            formula_start = next(i for i, line in enumerate(donor_lines)
                                 if line.strip().startswith("source_sum64=("))
            formula_end = next(i for i in range(formula_start, len(donor_lines))
                               if "/REAL(oldcarrier(cell),real64)" in donor_lines[i])
            donor_formula = "\n".join(line.strip() for line in
                                       donor_lines[formula_start:formula_end + 1])
            driver = HARNESS.replace("  C9_DONOR_FORMULA", "  " + donor_formula.replace("\n", "\n  "))
            (work / "driver.f90").write_text(driver)
            for level in ("O0", "O2"):
                exe = work / f"source_prepared_diffusion_{level}.exe"
                build = subprocess.run(
                    ["bash", "-c",
                     'source "$1" && if [[ "$2" == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); '
                     'else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi && '
                     '"$CLOUD_BAL_FC" "${flags[@]}" -free kernel.f90 driver.f90 -o "$3"',
                     "pr91-source-diffusion", str(PROFILE), level, str(exe)],
                    cwd=work, text=True, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, check=False)
                self.assertEqual(build.returncode, 0, f"{level}: {build.stdout}")
                run = subprocess.run(
                    ["bash", "-c", 'source "$1" && exec "$2"',
                     "pr91-source-diffusion", str(PROFILE), str(exe)],
                    cwd=work, text=True, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, check=False)
                self.assertEqual(run.returncode, 0, f"{level}: {run.stdout}")
                self.assertIn("PR91_SOURCE_PREPARED_DIFFUSION_PASS", run.stdout)


if __name__ == "__main__":
    unittest.main()
