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
CORE = ROOT / "docs/evidence/pr91_host_store_20261020/validation/final_i/cloud_bal_joint_transport.f90"
CORE_SHA256 = "9cfc20a3724b9a71b0be912d7f6746cd3ae5f17128dd743539a34ddadfd862a6"
PINNED_MODULE = ROOT / "docs/evidence/pr91_host_store_20261020/validation/final_i/module_em.F"
PINNED_SOLVE = ROOT / "docs/evidence/pr91_source_store_contract_20261020/c12/inputs/solve_em_c7.F"

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
  ! C12 donor formula is inserted from the production transform below.
  C12_DONOR_FORMULA
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


T2_ENDPOINT_HARNESS = r"""
program test_t2_intermediate_mean
  use iso_fortran_env, only: real32, real64, int32
  use cloud_bal_joint_transport, only: joint_moment_store
  implicit none
  real(real32) :: q1,n1,rho,qout,nout,qbad,nbad,qstage,nstage
  real(real64) :: q,n,rateq,raten,mmin,mmax,bmin,bmax,dt
  integer :: adjustment,stage,final_adjustment,final_stage
  logical :: valid,final_valid
  integer(int32) :: qb,nb,qstageb,nstageb,qfinalb,nfinalb
  real(real64) :: upper64
  q1=2.31259036809206009e-7_real64; n1=5.52090240000000000e+07_real64
  rateq=-5.73329534876483977e-13_real64; raten=-1.36871687786769883e+02_real64
  q=2.31247570218508490e-7_real64; n=5.52062865662442669e+07_real64
  rho=1.14675259590148926_real64
  mmin=4.18879052734374980e-15_real64; mmax=3.03008574026602271e-10_real64
  bmin=3.78455494068234348e+09_real64; bmax=2.73766995130377844e+14_real64
  dt=2.0e+01_real64
  qstage=q1+real(real(dt,real64)*rateq,real32)
  nstage=n1+real(real(dt,real64)*raten,real32)
  call joint_moment_store(q,n,rho,mmin,mmax,.true.,qout,nout,adjustment,valid, &
       allow_normal_q_adjustment=.true.,allow_joint_quantum_absence=.true., &
       strict_mass_ratio=.true.,failure_stage=stage)
  if (.not.valid.or.stage/=0.or.adjustment/=2) stop 1
  qb=transfer(qout,qb); nb=transfer(nout,nb)
  qstageb=transfer(qstage,qstageb); nstageb=transfer(nstage,nstageb)
  if (qb/=int(z'34784CDA',int32).or.nb/=int(z'4C529864',int32)) stop 2
  if (qstageb/=int(z'34784CD9',int32).or.nstageb/=nb) stop 3
  call joint_moment_store(q,n,rho,mmin,mmax,.true.,qbad,nbad,adjustment,valid, &
       allow_normal_q_adjustment=.true.,allow_joint_quantum_absence=.true., &
       strict_mass_ratio=.true.,volume_number_bounds=[bmin,bmax],failure_stage=stage)
  if (valid.or.stage/=3) stop 4
  upper64=bmax*real(qout,real64)
  if (real(real(nout*rho,real32),real64)<=upper64) stop 5
  call joint_moment_store(real(qout,real64),real(nout,real64),rho,mmin,mmax,.true., &
       qbad,nbad,final_adjustment,final_valid,allow_normal_q_adjustment=.true., &
       allow_joint_quantum_absence=.true.,strict_mass_ratio=.true., &
       volume_number_bounds=[bmin,bmax],failure_stage=final_stage)
  if (.not.final_valid.or.final_stage/=0.or.final_adjustment/=2) stop 6
  qfinalb=transfer(qbad,qfinalb); nfinalb=transfer(nbad,nfinalb)
  if (qfinalb/=int(z'34784CDB',int32).or.nfinalb/=int(z'4C529864',int32)) stop 7
  if (q/n/=mmin) stop 8
  if (real(n,real64)*real(rho,real64)<=bmax*real(q,real64)) stop 9
  print '(a,1x,i0,1x,i0,2(1x,z8.8))','FINAL_VOLUME_STORE',final_stage,final_adjustment,qfinalb,nfinalb
  print '(a,2(1x,z8.8))','SOURCE_STAGE_R32',qstageb,nstageb
  print '(a,2(1x,z8.8))','D3_MASS_ONLY_INTERMEDIATE',qb,nb
  print '(a,1x,i0)','C8_SOURCE_VOLUME_STAGE',stage
  print '(a,1x,i0)','RETURNED_R32_FINAL_VOLUME_STAGE',final_stage
  print '(a)','PR91_C12_T2_PENDING_MEAN_PASS'
end program test_t2_intermediate_mean
"""


class SourceFirstDiffusionC12Tests(unittest.TestCase):
    def test_transform_is_bound_directly_to_d3_and_c7_solve(self) -> None:
        self.assertEqual(transform.MODULE_SHA256,
                         "dc21f48b29784f7ab6bbb6975ef541d184b31effa796b0e5aab51b16e80d406d")
        self.assertEqual(transform.SOLVE_SHA256,
                         "412183300ea8dd6af028ac1a5254f937477b054630db4eb1f5910a6bf974c3c5")
        self.assertEqual(transform._DIFFUSION_AND_DONOR_PASS.count("horizontal_diffusion64("), 2)
        self.assertIn("prepared_diffusion(i,k,j)-pr87_all_pair_diffusion_old",
                      transform._DIFFUSION_AND_DONOR_PASS)
        self.assertIn("qs64(cell,p)=pr87_all_pair_diffusion_nonD64(i,k,j,2*p-1)",
                      transform._DIFFUSION_AND_DONOR_PASS)
        self.assertIn("qs64(cell,p)=qs64(cell,p)+prepared_diffusion(i,k,j)",
                      transform._DIFFUSION_AND_DONOR_PASS)
        self.assertNotIn("qs64(cell,p)=qs64(cell,p)+source_diff_delta(1)",
                         transform._DIFFUSION_AND_DONOR_PASS)
        self.assertIn("SOURCE_DIFFUSION_DELTA", transform._DIFFUSION_AND_DONOR_PASS)

    def test_d3_transform_emits_source_prepared_consumer_without_c8_endpoint_gate(self) -> None:
        if not (PINNED_MODULE.exists() and PINNED_SOLVE.exists()):
            self.skipTest("pinned D3 native-build inputs are external to this source checkout")
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
        self.assertIn("strict_mass_ratio=.TRUE.)", module)
        source_stage = module[module.index("source_endpoint32="):module.index("IF (.NOT.full_valid)")]
        self.assertNotIn("volume_number_bounds=number_bounds(cell,:,p))", source_stage)
        self.assertIn("volume_number_bounds=number_bounds(c,:,p)", module)
        self.assertNotIn("old_diffusion(:,:,:)\n", module)
        self.assertIn("all_pair_diffusion_old=pr87_all_pair_diffusion_old", solve)
        self.assertIn("pr87_all_pair_diffusion_identity", solve)
        self.assertIn("pr87_all_pair_diffusion_valid", solve)
        self.assertIn("REAL(pr87_all_pair_diffusion_tendency32(i,k,j,5),real64)", solve)
        self.assertIn("pr87_all_pair_diffusion_nonD64(i,k,j,4)", solve)
        self.assertIn("pr87_all_pair_diffusion_nonD64(i,k,j,1)", solve)
        self.assertLess(solve.index("pr87_all_pair_diffusion_nonD64(i,k,j,1) ="),
                        solve.index("pr87_coupled_qsrc(i,k,j,1) = moist_tend"))

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
            driver = HARNESS.replace("  C12_DONOR_FORMULA", "  " + donor_formula.replace("\n", "\n  "))
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

    def test_production_nondiffusion_decomposition_and_orphan_dprepared_preservation(self) -> None:
        if not (PINNED_MODULE.exists() and PINNED_SOLVE.exists()):
            self.skipTest("pinned D3 host sources are external to this source checkout")
        solve = transform.transform_solve(PINNED_SOLVE.read_text())
        start = solve.index("                 pr87_all_pair_diffusion_nonD64(i,k,j,1) = &")
        end = solve.index("                 pr87_coupled_qsrc(i,k,j,1) = moist_tend", start)
        formula = solve[start:end]
        driver = r"""
program test_c12_source_decomposition
  use iso_fortran_env, only: real32,real64
  implicit none
  integer,parameter :: P_QC=1,P_QI=2,P_QNC=3,P_QNI=4
  integer :: i,k,j
  real(real32) :: pr87_all_pair_diffusion_tendency32(1,1,1,8)
  real(real32) :: pr87_coupled_qsrc(1,1,1,2),pr87_coupled_nsrc(1,1,1,2)
  real(real32) :: moist_tend(1,1,1,4),scalar_tend(1,1,1,4)
  real(real64) :: pr87_all_pair_diffusion_nonD64(1,1,1,4),dprepared_q,dprepared_n,rate_q,rate_n
  i=1;k=1;j=1
  pr87_all_pair_diffusion_tendency32=0.0_real32
  pr87_coupled_qsrc=0.0_real32;pr87_coupled_nsrc=0.0_real32
  moist_tend=0.0_real32;scalar_tend=0.0_real32
  ! Native C11 failure shape: old D is large, but the prepared field has tiny positive Q inflow.
  dprepared_q=2.1326302713444503e-23_real64; dprepared_n=2.245324874239295e-10_real64
  pr87_all_pair_diffusion_tendency32(1,1,1,1:8)=0.0_real32
  moist_tend(1,1,1,P_QC)=0.0_real32;scalar_tend(1,1,1,P_QNC)=0.0_real32
  pr87_all_pair_diffusion_tendency32(1,1,1,1)=0.0_real32
  pr87_all_pair_diffusion_tendency32(1,1,1,2)=0.0_real32
  NOND_FORMULA
  rate_q=pr87_all_pair_diffusion_nonD64(1,1,1,1)+dprepared_q
  rate_n=pr87_all_pair_diffusion_nonD64(1,1,1,2)+dprepared_n
  if (rate_q/=dprepared_q.or.rate_n/=dprepared_n) stop 1
  ! A source-stage rounding residual must survive subtraction of large before/coupled values.
  pr87_all_pair_diffusion_tendency32=1.0_real32
  pr87_coupled_qsrc=1.0_real32;pr87_coupled_nsrc=1.0_real32
  pr87_all_pair_diffusion_tendency32(1,1,1,5)=1.0e-30_real32; moist_tend(1,1,1,P_QC)=2.0e-30_real32
  pr87_all_pair_diffusion_tendency32(1,1,1,6)=1.0e-30_real32; scalar_tend(1,1,1,P_QNC)=2.0e-30_real32
  pr87_all_pair_diffusion_tendency32(1,1,1,7)=1.0e-30_real32; moist_tend(1,1,1,P_QI)=2.0e-30_real32
  pr87_all_pair_diffusion_tendency32(1,1,1,8)=1.0e-30_real32; scalar_tend(1,1,1,P_QNI)=2.0e-30_real32
  NOND_FORMULA
  if (pr87_all_pair_diffusion_nonD64(1,1,1,1)/= &
      real(moist_tend(1,1,1,P_QC),real64)-real(pr87_all_pair_diffusion_tendency32(1,1,1,5),real64)) stop 2
  if (pr87_all_pair_diffusion_nonD64(1,1,1,2)/= &
      real(scalar_tend(1,1,1,P_QNC),real64)-real(pr87_all_pair_diffusion_tendency32(1,1,1,6),real64)) stop 3
  if (pr87_all_pair_diffusion_nonD64(1,1,1,3)/= &
      real(moist_tend(1,1,1,P_QI),real64)-real(pr87_all_pair_diffusion_tendency32(1,1,1,7),real64)) stop 4
  if (pr87_all_pair_diffusion_nonD64(1,1,1,4)/= &
      real(scalar_tend(1,1,1,P_QNI),real64)-real(pr87_all_pair_diffusion_tendency32(1,1,1,8),real64)) stop 5
  print '(a)','PR91_C12_PRODUCTION_DECOMPOSITION_PASS'
end program
"""
        driver = driver.replace("NOND_FORMULA", formula.rstrip())
        with tempfile.TemporaryDirectory(prefix="pr91-c12-nond-", dir="/var/tmp") as tmp:
            work = Path(tmp)
            (work / "driver.f90").write_text(driver)
            for level in ("O0", "O2"):
                exe = work / f"nond_{level}.exe"
                build = subprocess.run(
                    ["bash", "-c",
                     'source "$1" && if [[ "$2" == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); '
                     'else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi && '
                     '"$CLOUD_BAL_FC" "${flags[@]}" -free driver.f90 -o "$3"',
                     "pr91-c12-nond", str(PROFILE), level, str(exe)], cwd=work,
                    text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
                self.assertEqual(build.returncode, 0, f"{level}: {build.stdout}")
                run = subprocess.run(
                    ["bash", "-c", 'source "$1" && exec "$2"',
                     "pr91-c12-nond", str(PROFILE), str(exe)], cwd=work,
                    text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
                self.assertEqual(run.returncode, 0, f"{level}: {run.stdout}")
                self.assertIn("PR91_C12_PRODUCTION_DECOMPOSITION_PASS", run.stdout)

    def test_c12_failure_rows_write_expected_typed_words_with_pinned_ifx(self) -> None:
        if not PINNED_MODULE.exists():
            self.skipTest("pinned D3 module is external to this source checkout")
        module = transform.transform_module(PINNED_MODULE.read_text())
        start = module.index("          WRITE(stage_diag_u,'(a,1x,4(z8.8,1x))') 'VDS_C12_BEFORE_AFTER32'")
        last = "TRANSFER(pr87_all_pair_diffusion_delta(i,k,j,2*p),0_int64)"
        end = module.index(last, start) + len(last)
        rows = module[start:end]
        driver = r"""
program test_c12_failure_rows
  use iso_fortran_env, only: int32,int64,real32,real64
  implicit none
  integer :: stage_diag_u,p,i,j,k
  real(real32) :: pr87_all_pair_diffusion_tendency32(1,1,1,8)
  real(real64) :: pr87_all_pair_diffusion_nonD64(1,1,1,4)
  real(real64) :: prepared_diffusion(1,1,1),prepared_n_diffusion(1,1,1)
  real(real64) :: pr87_all_pair_diffusion_old(1,1,1,4)
  real(real64) :: pr87_raw_qsrc(1,1,1,2),pr87_raw_nsrc(1,1,1,2)
  real(real64) :: pr87_later_qsrc(1,1,1,2),pr87_later_nsrc(1,1,1,2)
  real(real64) :: pr87_all_pair_diffusion_delta(1,1,1,8)
  p=1;i=1;j=1;k=1
  pr87_all_pair_diffusion_tendency32=1.0_real32
  pr87_all_pair_diffusion_nonD64=2.0_real64;prepared_diffusion=3.0_real64
  prepared_n_diffusion=4.0_real64;pr87_all_pair_diffusion_old=5.0_real64
  pr87_raw_qsrc=6.0_real64;pr87_raw_nsrc=7.0_real64
  pr87_later_qsrc=8.0_real64;pr87_later_nsrc=9.0_real64
  pr87_all_pair_diffusion_delta=10.0_real64
  open(newunit=stage_diag_u,file='rows.raw',status='replace')
C12_ROWS
  close(stage_diag_u)
end program
"""
        driver = driver.replace("C12_ROWS", "\n".join("  " + line for line in rows.splitlines()))
        with tempfile.TemporaryDirectory(prefix="pr91-c12-writer-", dir="/var/tmp") as tmp:
            work = Path(tmp)
            (work / "driver.f90").write_text(driver)
            outputs = []
            for level in ("O0", "O2"):
                exe = work / f"rows_{level}.exe"
                build = subprocess.run(
                    ["bash", "-c",
                     'source "$1" && if [[ "$2" == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); '
                     'else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi && '
                     '"$CLOUD_BAL_FC" "${flags[@]}" -free driver.f90 -o "$3"',
                     "pr91-c12-writer", str(PROFILE), level, str(exe)], cwd=work,
                    text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
                self.assertEqual(build.returncode, 0, f"{level}: {build.stdout}")
                run = subprocess.run(
                    ["bash", "-c", 'source "$1" && exec "$2"',
                     "pr91-c12-writer", str(PROFILE), str(exe)], cwd=work,
                    text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
                self.assertEqual(run.returncode, 0, f"{level}: {run.stdout}")
                raw = (work / "rows.raw").read_text().splitlines()
                self.assertEqual([row.split()[0] for row in raw], [
                    "VDS_C12_BEFORE_AFTER32", "VDS_C12_SOURCE_COMPONENTS", "VDS_C12_RAW_PROVENANCE"])
                self.assertEqual(len(raw[0].split()), 5)
                self.assertEqual(len(raw[1].split()), 7)
                self.assertEqual(len(raw[2].split()), 7)
                self.assertEqual(raw[0].split()[1:], ["3F800000"] * 4)
                self.assertEqual(raw[1].split()[1:], ["4000000000000000"] * 2 +
                                 ["4008000000000000", "4010000000000000"] +
                                 ["4014000000000000"] * 2)
                outputs.append("\n".join(raw))
            self.assertEqual(outputs[0], outputs[1])

    def test_c11_failure_replay_uses_embedded_real128_kernel_and_c12_source_order(self) -> None:
        replay = ROOT / "docs/evidence/pr91_source_store_contract_20261020/c11d/native_replay"
        if not (replay / "kernel_c10_embedded.f90").exists():
            self.skipTest("archived C11d embedded-kernel replay is unavailable")
        kernel = (replay / "kernel_c10_embedded.f90").read_text()
        driver = (replay / "driver.f90").read_text()
        old = """  qs=qsrc+ dq_later
  qs=qs+(dqnew-dqold)
  ns=nsrc+dn_later
  ns=ns+(dnnew-dnold)
"""
        new = """  ! C12 keeps the source residual separate from the old diffusion cancellation.
  qs=(qsrc+dq_later)-dqold
  ns=(nsrc+dn_later)-dnold
  qs=qs+dqnew
  ns=ns+dnnew
"""
        self.assertEqual(driver.count(old), 1)
        driver = driver.replace(old, new)
        driver = driver.replace("'SOURCE_PLUS_DELTA'", "'NONDIFF_PLUS_DPREPARED'")
        with tempfile.TemporaryDirectory(prefix="pr91-c12-r128-replay-", dir="/var/tmp") as tmp:
            work = Path(tmp)
            (work / "kernel.f90").write_text(kernel)
            (work / "driver.f90").write_text(driver)
            for level in ("O0", "O2"):
                exe = work / f"native_replay_{level}.exe"
                build = subprocess.run(
                    ["bash", "-c",
                     'source "$1" && if [[ "$2" == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); '
                     'else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi && '
                     '"$CLOUD_BAL_FC" "${flags[@]}" -free kernel.f90 driver.f90 -o "$3"',
                     "pr91-c12-r128", str(PROFILE), level, str(exe)], cwd=work,
                    text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
                self.assertEqual(build.returncode, 0, f"{level}: {build.stdout}")
                run = subprocess.run(
                    ["bash", "-c", 'source "$1" && exec "$2"',
                     "pr91-c12-r128", str(PROFILE), str(exe)], cwd=work,
                    text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
                self.assertEqual(run.returncode, 0, f"{level}: {run.stdout}")
                self.assertIn("DONOR_QN_DEC", run.stdout)
                self.assertNotIn("DONOR_QN 0000000000000000", run.stdout)
                self.assertIn("D_PREPARED 3B39C82BC6F72E40 3DEEDC08DA77C3AC", run.stdout)

    def test_t2_pending_mean_uses_original_d3_store_and_final_consumer_keeps_volume_guard(self) -> None:
        import hashlib
        self.assertEqual(hashlib.sha256(CORE.read_bytes()).hexdigest(), CORE_SHA256)
        with tempfile.TemporaryDirectory(prefix="pr91-c10-t2-endpoint-", dir="/var/tmp") as tmp:
            work = Path(tmp)
            (work / "core.f90").write_bytes(CORE.read_bytes())
            (work / "driver.f90").write_text(T2_ENDPOINT_HARNESS)
            for level in ("O0", "O2"):
                exe = work / f"t2_endpoint_{level}.exe"
                build = subprocess.run(
                    ["bash", "-c",
                     'source "$1" && if [[ "$2" == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); '
                     'else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi && '
                     '"$CLOUD_BAL_FC" "${flags[@]}" -free core.f90 driver.f90 -o "$3"',
                     "pr91-c10-t2", str(PROFILE), level, str(exe)],
                    cwd=work, text=True, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, check=False)
                self.assertEqual(build.returncode, 0, f"{level}: {build.stdout}")
                run = subprocess.run(
                    ["bash", "-c", 'source "$1" && exec "$2"',
                     "pr91-c10-t2", str(PROFILE), str(exe)],
                    cwd=work, text=True, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, check=False)
                self.assertEqual(run.returncode, 0, f"{level}: {run.stdout}")
                self.assertIn("PR91_C12_T2_PENDING_MEAN_PASS", run.stdout)
                self.assertIn("C8_SOURCE_VOLUME_STAGE 3", run.stdout)
                self.assertIn("FINAL_VOLUME_STORE 0 2 34784CDB 4C529864", run.stdout)


if __name__ == "__main__":
    unittest.main()
