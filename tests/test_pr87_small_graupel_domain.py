from __future__ import annotations

import gzip
import hashlib
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import pytest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/evidence/pr87_two_step_v42_20261016/module_mp_kdm6.F.gz"
TOOLCHAIN = ROOT / "tests/intel_toolchain.sh"
sys.path.insert(0, str(ROOT / "tools"))

from pr87_small_graupel_domain import (  # noqa: E402
    V42_KDM6_SHA256,
    V43_DIAGNOSTIC_KDM6_SHA256,
    extend_small_positive_graupel_domain,
)
from pr87_graupel_failure_context import add_failure_context  # noqa: E402


def _routine(source: str, name: str, *, after: int = 0) -> str:
    starts = list(re.finditer(rf"^\s*(?:pure\s+)?(?:logical\s+)?(?:subroutine|function)\s+{name}\s*\(", source[after:], re.I | re.M))
    assert starts, f"missing {name}"
    start = starts[-1]
    absolute_start = after + start.start()
    body_start = after + start.end()
    end = re.search(
        rf"^\s*end\s+(?:subroutine|function)\s+{name}\s*$",
        source[body_start:], re.I | re.M,
    )
    assert end, f"missing end of {name}"
    return source[absolute_start:body_start + end.end()]


def _source_pair() -> tuple[str, str]:
    original = gzip.decompress(SOURCE.read_bytes()).decode()
    assert hashlib.sha256(original.encode()).hexdigest() == V42_KDM6_SHA256
    transformed = extend_small_positive_graupel_domain(original)
    module_end = transformed.index("END MODULE module_mp_kdm6")
    return original, transformed


def _v43_pair() -> tuple[str, str]:
    original_v42, _ = _source_pair()
    original_v43 = add_failure_context(original_v42)
    assert hashlib.sha256(original_v43.encode()).hexdigest() == V43_DIAGNOSTIC_KDM6_SHA256
    return original_v43, extend_small_positive_graupel_domain(original_v43)


def _fixture(source: str) -> str:
    module_end = source.index("END MODULE module_mp_kdm6")
    helper_source = source[module_end:]
    pair = _routine(source, "kdm6_progb_density_pair_valid")
    refresh = _routine(source, "kdm6_refresh_graupel_intercept")
    progb = _routine(source, "ProgB_param")
    slope = _routine(source, "slope_kdm6")
    velocity = _routine(source, "kdm6_velocity_rates")
    fraction = _routine(source, "kdm6_rain_process_fraction")
    state = _routine(source, "kdm6_rain_process_state_valid")
    sediment = _routine(helper_source, "pr85_kdm6_paired_sediment_column")
    sediment = sediment.replace(
        "USE module_mp_kdm6, ONLY: kdm6_progb_density_pair_valid\n", ""
    )

    globals_ = """  integer, parameter :: PROGB_ABSENT=0, PROGB_TRANSIENT=1
  integer, parameter :: PROGB_PSD_ACTIVE=2, PROGB_UNSUPPORTED=3
  integer, parameter :: PR85_ICE_NATIVE_INACTIVE_MAX=1
  real, parameter :: qcrmin=1.0e-9
  real :: dmg=3.0,mug=0.0,dms=3.0,mur=1.0,bvtr=0.8,bvts=0.41,bvti=1.0
  real :: alpha=0.12,n0smax=1.0e11,n0s=2.0e6,nrmin=1.0e-2,mus=0.0
  real :: lamdaimin=9080.0,lamdaimax=1820000.0,mui=0.0,dmr=3.0,dmi=3.0
  real :: pidnr=1.0,pidn0s=1.0,pidni=1.0
  real :: pvtr=1.0,pvts=1.0,pvti=1.0,pvtrn=1.0,pvtin=1.0
  real :: rslopermax=1.0e-3,rsloperbmax=1.0e-2,rsloperdmax=1.0e-9
  real :: rsloper2max=1.0e-6,rsloper3max=1.0e-9
  real :: rslopesmax=1.0e-3,rslopesbmax=1.0e-2,rslopesdmax=1.0e-9
  real :: rslopes2max=1.0e-6,rslopes3max=1.0e-9
  real :: rslopegmax=1.0e-3,rslopegdmax=1.0e-9,rslopeg2max=1.0e-6,rslopeg3max=1.0e-9
  real :: rslopeimax=1.0e-3,rslopeibmax=1.0e-2,rslopeidmax=1.0e-9
  real :: rslopei2max=1.0e-6,rslopei3max=1.0e-9
  double precision :: rslopermmax=1.0d-2,rslopesmmax=1.0d-2,rslopegmmax=1.0d-2,rslopeimmax=1.0d-2
"""
    return f"""module small_graupel_fixture
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite, ieee_value, ieee_quiet_nan
  use, intrinsic :: iso_fortran_env, only: int32, real64
  implicit none
{globals_}
contains
{pair}
{refresh}
{progb}
{slope}
{velocity}
{fraction}
{state}
{sediment}
  real function rgmma(x)
    real, intent(in) :: x
    rgmma=gamma(x)
  end function rgmma
end module small_graupel_fixture

program test_small_graupel_domain
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  use, intrinsic :: iso_fortran_env, only: int32, real64
  use small_graupel_fixture, only: PROGB_PSD_ACTIVE,qcrmin, &
       kdm6_progb_density_pair_valid,ProgB_param,slope_kdm6,kdm6_velocity_rates, &
       kdm6_rain_process_fraction,kdm6_rain_process_state_valid, &
       pr85_kdm6_paired_sediment_column
  implicit none
  real :: q(1,1,3),bg(1,1),rho(1,1),cmg(1,1),pidn0g(1,1),avtg(1,1),pvtg(1,1),precg2(1,1)
  real :: bvtg(1,1),bvtg1(1,1),bvtg2(1,1),bvtg3(1,1),bvtg4(1,1),rslopegbmax(1,1)
  real :: g1pbg(1,1),g3pbg(1,1),g4pbg(1,1),g5pbgo2(1,1),g1pdgbgmg(1,1),dgbgmug1(1,1)
  integer :: status(1,1),ierr
  real :: pi,n0g,g1pmg,g1pdgmg,rslopegmax,density,delz(1),qstate(1),bstate(1)
  real :: rs(1,1,4),rsb(1,1,4),rs2(1,1,4),rs3(1,1,4),rsd(1,1,4)
  real(real64) :: rsmu(1,1,4)
  real(real64) :: vt(1,1,4),vtn(1,1,2),mass_rate(1,1,4),number_rate(1,1,2)
  real :: qfixed(5),dq(5),nfixed(3),dn(3),alpha,t
  logical :: valid,feasible
  integer :: search_status
  real(real64) :: approved_q(1),approved_b(1)
  integer :: unit

  pi=3.14159265; n0g=1.0e6; g1pmg=1.0; g1pdgmg=1.0; rslopegmax=1.0e-3
  density=0.6773980855941772
  ! Exact REAL32 T3 PRE_KDM6 representative (i=117,j=32,k=17), reproduced
  ! from the saved V42 activity snapshot for both coupled and OFF arms.
  q(1,1,1)=0.0; q(1,1,2)=0.0
  q(1,1,3)=transfer(int(z'2B638C2A',int32),0.0)
  bg(1,1)=transfer(int(z'268376D7',int32),0.0)
  call call_progb()
  if (status(1,1) /= PROGB_PSD_ACTIVE) error stop 'T3 tiny valid pair did not become active'
  if (.not.ieee_is_finite(rho(1,1)) .or. rho(1,1)<100.0 .or. rho(1,1)>900.0) &
    error stop 'T3 density coefficient is outside support'

  ! Pair validation is scale independent even near REAL32 subnormal limits.
  block
    real :: smallest
    smallest=nearest(0.0,1.0)
    if (.not.kdm6_progb_density_pair_valid(128.0*smallest,smallest,100.0,900.0)) &
      error stop 'representable 128:1 subnormal pair rejected'
    if (kdm6_progb_density_pair_valid(99.0*smallest,smallest,100.0,900.0)) &
      error stop 'out-of-support subnormal pair accepted'
    q(1,1,3)=128.0*smallest; bg(1,1)=smallest
    call call_progb()
    if (status(1,1)/=PROGB_PSD_ACTIVE .or. rho(1,1)/=128.0) &
      error stop 'subnormal 128:1 pair did not produce density-defined ProgB state'
    if (.not.ieee_is_finite(cmg(1,1)) .or. .not.ieee_is_finite(pidn0g(1,1)) .or. &
        .not.ieee_is_finite(avtg(1,1)) .or. .not.ieee_is_finite(pvtg(1,1))) &
      error stop 'subnormal pair ProgB properties are nonfinite'
    q(1,1,3)=transfer(int(z'2B638C2A',int32),0.0)
    bg(1,1)=transfer(int(z'268376D7',int32),0.0)
    call call_progb()
  end block

  ! Scaling QG and BG together preserves ratio-derived ProgB coefficients.
  block
    real :: rho1,cmg1,pid1,avt1,pvt1,prec1,bvt1
    rho1=rho(1,1); cmg1=cmg(1,1); pid1=pidn0g(1,1); avt1=avtg(1,1)
    pvt1=pvtg(1,1); prec1=precg2(1,1); bvt1=bvtg(1,1)
    q(1,1,3)=8.0*q(1,1,3); bg(1,1)=8.0*bg(1,1)
    call call_progb()
    if (status(1,1) /= PROGB_PSD_ACTIVE) error stop 'scaled tiny pair did not remain active'
    if (rho(1,1)/=rho1 .or. cmg(1,1)/=cmg1 .or. pidn0g(1,1)/=pid1 .or. &
        avtg(1,1)/=avt1 .or. pvtg(1,1)/=pvt1 .or. precg2(1,1)/=prec1 .or. bvtg(1,1)/=bvt1) &
      error stop 'small-positive ProgB coefficients lost scale invariance'
    q(1,1,3)=q(1,1,3)/8.0; bg(1,1)=bg(1,1)/8.0
  end block

  ! Exercise the real qcrmin fallback slope, velocity, and sediment packet.
  block
    real :: qci(1,1),nci(1,1),nrs(1,1),den(1,1),denfac(1,1),temp(1,1)
    real :: qcopy(1,1,3),bgcopy(1,1),qactive_min,bactive_min,rhomin,rhomax
    integer :: progb(1,1)
    logical :: trace
    integer :: nlevels
    qci=0.0; nci=0.0; nrs=0.0; den=density; denfac=1.0; temp=273.0
    qcopy=q; bgcopy=bg; progb=status
    call slope_kdm6(qcopy,qci,nrs,nci,den,denfac,temp,rs,rsb,rs2,rs3,rsmu,rsd,vt,vtn, &
         1,1,1,1,qcrmin,pidn0g,pvtg,bvtg,rslopegbmax,progb)
    delz=1000000.0
    call kdm6_velocity_rates(vt,vtn,delz,mass_rate,number_rate,1,1,1,1,1,1,1,1)
    if (.not.ieee_is_finite(vt(1,1,3)) .or. .not.ieee_is_finite(mass_rate(1,1,3)) .or. &
        vt(1,1,3)<=0.0d0 .or. mass_rate(1,1,3)<=0.0d0) &
      error stop 'small-positive mass velocity flux is not finite and positive'
    qstate=q(1,1,3); bstate=bg(1,1)
    qactive_min=1.0e-9; bactive_min=1.0e-15; rhomin=100.0; rhomax=900.0; unit=0
    call pr85_kdm6_paired_sediment_column(1,1,1,1,1,1.0,1,den(1,:),delz, &
         mass_rate(1,1,3:3),mass_rate(1,1,3:3),qstate,bstate,2,qactive_min,bactive_min, &
         rhomin,rhomax,approved_q,approved_b,unit,.false.,valid,1.0,3.0,961.0,35000.0)
    if (.not.valid) error stop 'small-positive graupel sedimentation packet rejected'
    if (.not.ieee_is_finite(approved_q(1)) .or. .not.ieee_is_finite(approved_b(1))) &
      error stop 'small-positive graupel approved flux is nonfinite'
    if (qstate(1)<=0.0 .or. bstate(1)<=0.0 .or. real(qstate(1),8)/real(bstate(1),8)<100.0d0 .or. &
        real(qstate(1),8)/real(bstate(1),8)>900.0d0) error stop 'sedimentation endpoint left density support'
  end block

  ! Both full and pair-only process validators accept a paired active->small
  ! endpoint, including the exact threshold corner that V42 called TRANSIENT.
  qfixed=0.0; dq=0.0; nfixed=0.0; dn=0.0; t=280.0
  qfixed(5)=transfer(int(z'2B638C2A',int32),0.0)
  bg(1,1)=transfer(int(z'268376D7',int32),0.0)
  dq(5)=-0.5*qfixed(5); alpha=0.0
  call kdm6_rain_process_fraction(qfixed,dq,nfixed,dn,bg(1,1),-0.5*bg(1,1),t,0.0, &
       .false.,density,1.0,1.0e-15,1.0e-2,1.0e-9,3.0,961.0,35000.0,100.0,900.0, &
       1.0,3.0,12000.0,500000.0,1.0,3.0,9080.0,1820000.0,alpha,feasible,search_status, &
       consumer_pair_only=.true.)
  if (.not.feasible .or. search_status/=0 .or. alpha/=1.0) &
    error stop 'pair-only process search rejected valid small endpoint'
  qfixed(5)=qfixed(5)+alpha*dq(5); bg(1,1)=bg(1,1)+alpha*(-0.5*transfer(int(z'268376D7',int32),0.0))
  call kdm6_rain_process_state_valid(qfixed,nfixed,bg(1,1),t,density,1.0,1.0e-15,1.0e-2, &
       1.0e-9,3.0,961.0,35000.0,100.0,900.0,1.0,3.0,12000.0,500000.0, &
       1.0,3.0,9080.0,1820000.0,valid,consumer_pair_only=.true.)
  if (.not.valid) error stop 'stored pair-only small endpoint rejected'
  print '(a)', 'PR87 small-positive ProgB, process, slope, and flux PASS'
contains
  subroutine call_progb()
    call ProgB_param(bg,q, rho,1,1,1,1,1,1,1.0e-9,3.0,0.0,cmg,pi,pidn0g, &
         g1pdgmg,g1pmg,n0g,avtg,pvtg,precg2,bvtg,bvtg1,bvtg2,bvtg3,bvtg4, &
         rslopegbmax,rslopegmax,g1pbg,g3pbg,g4pbg,g5pbgo2,g1pdgbgmg,dgbgmug1,status)
  end subroutine call_progb
end program test_small_graupel_domain
"""


def test_pinned_transform_keeps_physics_branches_and_removes_only_state_floor():
    original, transformed = _source_pair()
    assert transformed != original
    assert transformed.count("kdm6_progb_density_pair_valid(qrs(i,k,3),brs(i,k),") == 1
    assert transformed.count("kdm6_progb_density_pair_valid(q(5),bg,rho_min,rho_max)") == 2
    assert "progb_status(i,k) = PROGB_TRANSIENT\n            cycle" not in transformed
    assert "q(5).le.qcrmin .and. bg.le.1.0e-15" not in transformed
    assert "qm(5).le.real(qcrmin,8) .and. bm.le.real(1.0e-15,8)" not in transformed
    assert "IF (q<=qmin .AND. b<=bmin) RETURN" not in transformed
    assert "if(qrs(i,k,3).le.qcrmin)then\n              qrs(i,k,3) = 0.0" in transformed
    assert "if(qrs(i,k,3).le.qcrmin) then\n            rslope(i,k,3) = rslopegmax" in transformed
    assert "if (progb_status(i,k) == PROGB_PSD_ACTIVE .and. qrs(i,k,3) .gt.qcrmin) then" in transformed
    original_v43, transformed_v43 = _v43_pair()
    assert "PR87_G_CONSUMER_FAILURE" in original_v43
    for name in ("kdm6_progb_density_pair_valid", "kdm6_refresh_graupel_intercept", "ProgB_param",
                 "slope_kdm6", "kdm6_velocity_rates", "kdm6_rain_process_fraction",
                 "kdm6_rain_process_state_valid"):
        assert _routine(transformed, name) == _routine(transformed_v43, name)
    sediment_start = transformed.index("END MODULE module_mp_kdm6")
    sediment_v43_start = transformed_v43.index("END MODULE module_mp_kdm6")
    assert _routine(transformed, "pr85_kdm6_paired_sediment_column", after=sediment_start) == \
        _routine(transformed_v43, "pr85_kdm6_paired_sediment_column", after=sediment_v43_start)
    assert "PR87_G_CONSUMER_FAILURE" in transformed_v43
    with pytest.raises(ValueError, match="unexpected pinned KDM6 source hash"):
        extend_small_positive_graupel_domain(original + "\n")


@pytest.mark.parametrize("optimization", ["O0", "O2"])
def test_extracted_prog_b_slope_process_and_sedimentation_with_pinned_intel(optimization: str):
    _, transformed = _source_pair()
    fixture = _fixture(transformed)
    with tempfile.TemporaryDirectory(prefix=f"pr87_small_graupel_{optimization}_", dir="/var/tmp") as tmp:
        scratch = Path(tmp)
        source_path = scratch / "test_small_graupel_domain.F90"
        executable = scratch / "test_small_graupel_domain.exe"
        source_path.write_text(fixture)
        script = f"""
set -euo pipefail
source '{TOOLCHAIN}'
if [[ '{optimization}' == O0 ]]; then flags=("${{CLOUD_BAL_FREE_FLAGS[@]}}"); else flags=("${{CLOUD_BAL_REPRO_FLAGS[@]}}"); fi
"$CLOUD_BAL_FC" -free "${{flags[@]}}" '{source_path}' -o '{executable}'
'{executable}'
"""
        result = subprocess.run(["bash", "-lc", script], cwd=scratch, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        assert result.returncode == 0, result.stdout
        assert "PR87 small-positive ProgB, process, slope, and flux PASS" in result.stdout


if __name__ == "__main__":
    test_pinned_transform_keeps_physics_branches_and_removes_only_state_floor()
    test_extracted_prog_b_slope_process_and_sedimentation_with_pinned_intel("O0")
    print("PR87 small graupel domain tests PASS")
