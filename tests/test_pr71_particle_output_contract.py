#!/usr/bin/env python3
"""Check generated ProgB status wiring and emit its source-extracted test."""

from __future__ import annotations

import os
from pathlib import Path
import re
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import pr71_particle_output_contract as contract


OUTPUTS = contract.OUTPUTS
SOURCE = Path(os.environ["PR71_CONTRACT_SOURCE"])


class ParticleOutputContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.progb = cls.source[contract.bounds(cls.source, "ProgB_param")[0]:
                               contract.bounds(cls.source, "ProgB_param")[1]]
        cls.kdm62d = cls.source[contract.bounds(cls.source, "kdm62d")[0]:
                                contract.bounds(cls.source, "kdm62d")[1]]
        cls.slope = cls.source[contract.bounds(cls.source, "slope_kdm6")[0]:
                               contract.bounds(cls.source, "slope_kdm6")[1]]

    def test_all_seven_calls_receive_status(self) -> None:
        self.assertEqual(self.kdm62d.count("call ProgB_param("), contract.CALL_COUNT)
        self.assertEqual(self.kdm62d.count(",dgbgmug1,progb_status)"), contract.CALL_COUNT)
        self.assertEqual(self.kdm62d.count("call slope_kdm6("), contract.CALL_COUNT)
        self.assertEqual(self.kdm62d.count("rslopegbmax,progb_status)"), contract.CALL_COUNT)

    def test_all_outputs_are_defined_and_status_is_explicit(self) -> None:
        for output in OUTPUTS:
            self.assertIn(f"{output}(i,k) = 0.0", self.progb)
            self.assertIn(f"ieee_is_finite({output}(i,k))", self.progb)
        for status in (
            "PROGB_ABSENT", "PROGB_TRANSIENT", "PROGB_PSD_ACTIVE", "PROGB_UNSUPPORTED",
        ):
            self.assertIn(status, self.progb)
        self.assertIn("raw_density < dble(rho_min)", self.progb)
        self.assertIn("raw_density > dble(rho_max)", self.progb)
        self.assertNotIn("min(rho_max,max(rho_min", self.progb)

    def test_every_qg_rate_gate_requires_active_status(self) -> None:
        for line in self.kdm62d.splitlines():
            if re.search(r"if\s*\(\s*qrs\(i,k,3\)\s*\.gt\.", line, re.I):
                self.fail(f"unguarded graupel rate gate: {line.strip()}")

    def test_slope_rejects_before_reading_output_arrays(self) -> None:
        reject = self.slope.find("ProgB transient PSD state rejected")
        first_output_read = self.slope.find("rslopegbmax(i,k)")
        self.assertGreaterEqual(reject, 0)
        self.assertGreater(first_output_read, reject)
        self.assertIn("if (progb_status(i,k) == PROGB_ABSENT)", self.slope)

    def test_terminal_cleanup_invalidates_outputs(self) -> None:
        cleanup = self.kdm62d.index("progb_status(i,k) = PROGB_ABSENT", self.kdm62d.index("qrs(i,k,3) = 0.0"))
        for output in OUTPUTS:
            self.assertIn(f"{output}(i,k) = 0.0", self.kdm62d[cleanup:cleanup + 1400])
        self.assertIn("n0go(i,k) = 0.0", self.kdm62d[cleanup:cleanup + 1400])
        self.assertNotIn("rhox(i,k) = max(rhox(i,k)", self.kdm62d)

    def test_n0go_property_reads_are_status_guarded(self) -> None:
        self.assertEqual(self.kdm62d.count("n0go(i,k) = (n0g)/g1pmg/(rslopemu(i,k,3))"), 2)
        self.assertEqual(self.kdm62d.count("if (progb_status(i,k) == PROGB_PSD_ACTIVE) then\n            n0go"), 2)

    def test_stage_zero_serializes_defined_named_ice_rate(self) -> None:
        self.assertEqual(
            self.source.count("write(pr67_unit) mass_velocity_rate(its:ite,kts:kte,4)"),
            1,
        )
        self.assertNotIn("write(pr67_unit) work1(its:ite,kts:kte,4)", self.source)


def harness_text() -> str:
    routine = SOURCE.read_text(encoding="utf-8")
    start, end = contract.bounds(routine, "ProgB_param")
    progb = routine[start:end]
    slope_start, slope_end = contract.bounds(routine, "slope_kdm6")
    slope = routine[slope_start:slope_end]
    absent_start = slope.index("          if (progb_status(i,k) == PROGB_ABSENT) then")
    absent_end = slope.index("          else\n", absent_start)
    absent_slope_branch = slope[absent_start:absent_end] + "          endif\n"
    kdm_start, kdm_end = contract.bounds(routine, "kdm62d")
    kdm62d = routine[kdm_start:kdm_end]
    n0go_start = kdm62d.index(
        "          if (progb_status(i,k) == PROGB_PSD_ACTIVE) then\n"
        "            n0go(i,k) = (n0g)/g1pmg/(rslopemu(i,k,3))"
    )
    n0go_end = kdm62d.index("          endif\n", n0go_start) + len("          endif\n")
    absent_n0go_branch = kdm62d[n0go_start:n0go_end]
    return f"""module prog_contract_test
  use, intrinsic :: ieee_arithmetic, only : ieee_is_finite
  implicit none
  integer, parameter :: PROGB_ABSENT = 0
  integer, parameter :: PROGB_TRANSIENT = 1
  integer, parameter :: PROGB_PSD_ACTIVE = 2
  integer, parameter :: PROGB_UNSUPPORTED = 3
contains
{progb}
  real function rgmma(x)
    real, intent(in) :: x
    rgmma = gamma(x)
  end function rgmma

  subroutine check_absent_slope_and_n0go()
    integer :: i, k, progb_status(1,1)
    real :: rslope(1,1,4), rslopeb(1,1,4), rsloped(1,1,4)
    real :: rslope2(1,1,4), rslope3(1,1,4), rslopegbmax(1,1)
    real :: bvtg(1,1), n0go(1,1), n0g, g1pmg
    double precision :: rslopemu(1,1,4)
    i=1; k=1
    progb_status = PROGB_ABSENT
    rslope = -77.0; rslopeb = -77.0; rsloped = -77.0
    rslope2 = -77.0; rslope3 = -77.0; rslopegbmax = -77.0
    bvtg = -77.0
{absent_slope_branch.rstrip()}
    if (rslope(1,1,3) /= 0.0 .or. rslopeb(1,1,3) /= 0.0 .or. &
        rsloped(1,1,3) /= 0.0 .or. rslope2(1,1,3) /= 0.0 .or. &
        rslope3(1,1,3) /= 0.0 .or. rslopemu(1,1,3) /= 0.0) &
      error stop 'absent slope branch did not clear graupel slopes'
    rslopemu = 0.0
    n0g = 1.0; g1pmg = 1.0; n0go = -77.0
{absent_n0go_branch.rstrip()}
    if (n0go(1,1) /= 0.0) error stop 'absent n0go branch left stale value'
  end subroutine check_absent_slope_and_n0go
end module prog_contract_test

program test_particle_output_contract
  use prog_contract_test
  use, intrinsic :: ieee_arithmetic, only : ieee_is_finite, ieee_value, ieee_quiet_nan
  implicit none
  call check_case(0.0, 0.0, PROGB_ABSENT, .false.)
  call check_case(1.e-14, 1.e-17, PROGB_TRANSIENT, .false.)
  call check_case(1.e-6, 0.0, PROGB_UNSUPPORTED, .false.)
  call check_case(1.e-6, 1.e-9, PROGB_UNSUPPORTED, .false.)
  call check_case(0.0, 1.e-8, PROGB_UNSUPPORTED, .false.)
  call check_case(-1.e-6, 1.e-8, PROGB_UNSUPPORTED, .false.)
  call check_case(1.e-6, -1.e-8, PROGB_UNSUPPORTED, .false.)
  call check_case(ieee_value(0.0,ieee_quiet_nan), 1.e-8, PROGB_UNSUPPORTED, .false.)
  call check_case(1.e-6, ieee_value(0.0,ieee_quiet_nan), PROGB_UNSUPPORTED, .false.)
  call check_case(25.0*2.0**(-24), 0.25*2.0**(-24), PROGB_PSD_ACTIVE, .true.)
  call check_case(225.0*2.0**(-24), 0.25*2.0**(-24), PROGB_PSD_ACTIVE, .true.)
  call check_absent_slope_and_n0go()
  print '(A)', 'PR71_PROGB_OUTPUT_CONTRACT_PASS'
contains
  subroutine check_case(qg, bg, expected_status, active)
    real, intent(in) :: qg, bg
    integer, intent(in) :: expected_status
    logical, intent(in) :: active
    real :: brs(1,1), qrs(1,1,3), rhox(1,1), cmg(1,1), pidn0g(1,1)
    real :: avtg(1,1), pvtg(1,1), precg2(1,1), bvtg(1,1), bvtg1(1,1)
    real :: bvtg2(1,1), bvtg3(1,1), bvtg4(1,1), rslopegbmax(1,1)
    real :: g1pbg(1,1), g3pbg(1,1), g4pbg(1,1), g5pbgo2(1,1)
    real :: g1pdgbgmg(1,1), dgbgmug1(1,1)
    integer :: status(1,1)
    integer, parameter :: its=1, ite=1, jts=1, jte=1, kts=1, kte=1
    real, parameter :: qcrmin=1.e-9, dmg=3.0, mug=0.0, pi=3.14159265
    real, parameter :: g1pdgmg=1.0, g1pmg=1.0, n0g=1.e6, rslopegmax=1.e-3
    brs = bg
    qrs = 0.0
    qrs(1,1,3) = qg
    rhox = -77.0; cmg = -77.0; pidn0g = -77.0; avtg = -77.0
    pvtg = -77.0; precg2 = -77.0; bvtg = -77.0; bvtg1 = -77.0
    bvtg2 = -77.0; bvtg3 = -77.0; bvtg4 = -77.0; rslopegbmax = -77.0
    g1pbg = -77.0; g3pbg = -77.0; g4pbg = -77.0; g5pbgo2 = -77.0
    g1pdgbgmg = -77.0; dgbgmug1 = -77.0
    call ProgB_param(brs,qrs,rhox,its,ite,jts,jte,kts,kte,qcrmin, &
         dmg,mug,cmg,pi,pidn0g,g1pdgmg,g1pmg,n0g,avtg,pvtg,precg2, &
         bvtg,bvtg1,bvtg2,bvtg3,bvtg4,rslopegbmax,rslopegmax, &
         g1pbg,g3pbg,g4pbg,g5pbgo2,g1pdgbgmg,dgbgmug1,status)
    if (status(1,1) /= expected_status) error stop 'wrong ProgB status'
    if (active) then
      if (.not. ieee_is_finite(rhox(1,1)) .or. rhox(1,1) < 100.0 .or. rhox(1,1) > 900.0) &
        error stop 'active density outside supported range'
      if (.not. all(ieee_is_finite([cmg(1,1),pidn0g(1,1),avtg(1,1),pvtg(1,1), &
           precg2(1,1),bvtg(1,1),bvtg1(1,1),bvtg2(1,1),bvtg3(1,1),bvtg4(1,1), &
           rslopegbmax(1,1),g1pbg(1,1),g3pbg(1,1),g4pbg(1,1),g5pbgo2(1,1), &
           g1pdgbgmg(1,1),dgbgmug1(1,1)]))) error stop 'active output is nonfinite'
    else
      if (any([rhox(1,1),cmg(1,1),pidn0g(1,1),avtg(1,1),pvtg(1,1), &
           precg2(1,1),bvtg(1,1),bvtg1(1,1),bvtg2(1,1),bvtg3(1,1),bvtg4(1,1), &
           rslopegbmax(1,1),g1pbg(1,1),g3pbg(1,1),g4pbg(1,1),g5pbgo2(1,1), &
           g1pdgbgmg(1,1),dgbgmug1(1,1)] /= 0.0)) error stop 'inactive output not initialized'
      if (ieee_is_finite(bg)) then
        if (brs(1,1) /= bg) error stop 'inactive call changed INOUT brs'
      else
        if (ieee_is_finite(brs(1,1))) error stop 'inactive call changed nonfinite INOUT brs'
      endif
    endif
  end subroutine check_case
end program test_particle_output_contract
"""


if __name__ == "__main__":
    test_result = unittest.main(argv=[sys.argv[0]], exit=False)
    if not test_result.result.wasSuccessful():
        raise SystemExit(1)
    output_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if output_path is not None:
        output_path.write_text(harness_text(), encoding="utf-8")
