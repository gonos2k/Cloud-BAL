from __future__ import annotations

import gzip
import hashlib
from pathlib import Path
import re
import subprocess
import tempfile
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/evidence/pr87_two_step_v31_20261016/module_mp_kdm6.F.gz"
TOOLCHAIN = ROOT / "tests/intel_toolchain.sh"
sys.path.insert(0, str(ROOT / "tools"))

from pr87_graupel_process_domain import (  # noqa: E402
    V31_KDM6_SHA256,
    extend_graupel_process_domain,
)


def _routine(source: str, name: str) -> str:
    start = re.search(rf"^\s*subroutine\s+{name}\s*\(", source, re.I | re.M)
    assert start, f"missing {name}"
    end = re.search(
        rf"^\s*end\s+subroutine\s+{name}\s*$",
        source[start.end():], re.I | re.M,
    )
    assert end, f"missing end of {name}"
    return source[start.start():start.end() + end.end()]


def _fixture_source() -> str:
    original = gzip.open(SOURCE, "rt").read()
    transformed = extend_graupel_process_domain(original)
    fraction = _routine(transformed, "kdm6_rain_process_fraction")
    state_valid = _routine(transformed, "kdm6_rain_process_state_valid")
    return f"""module pr87_process_helpers
  implicit none
  real, parameter :: PR85_ICE_NATIVE_INACTIVE_MAX = nearest(1.e-14,-1.0)
contains
{fraction}
{state_valid}
end module pr87_process_helpers

program test_graupel_process_domain
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite, ieee_value, ieee_quiet_nan
  use pr87_process_helpers
  implicit none
  real :: q(5), dq(5), n(3), dn(3), bg, dbg, alpha
  real :: density,pidnr,qmin,ncmin,qcrmin,dmr,lmin,lmax,rhomin,rhomax
  real :: pidnc,dmc,lcmin,lcmax,pidni,dmi,limin,limax,t
  real :: vf,vp
  integer :: reason,status
  logical :: valid,feasible

  density=500.0; pidnr=1.0; pidnc=1.0; pidni=1.0
  qmin=1.0e-15; ncmin=10.0; qcrmin=1.0e-9
  dmr=3.0; dmc=3.0; dmi=3.0
  lmin=1.0; lmax=2.0; lcmin=1.0; lcmax=2.0; limin=1.0; limax=2.0
  rhomin=100.0; rhomax=900.0; t=280.0
  q=0.0; n=0.0; bg=0.0

  ! Exact V32diag context-6 witness: default and pair-only modes agree.
  q(5)=transfer(int(z'2B621F22'),0.0)
  bg=transfer(int(z'2681EB95'),0.0)
  call kdm6_rain_process_state_valid(q,n,bg,t,density,pidnr,qmin,ncmin, &
       qcrmin,dmr,lmin,lmax,rhomin,rhomax,pidnc,dmc,lcmin,lcmax, &
       pidni,dmi,limin,limax,valid,.false.,.true.,failure_reason=reason)
  if (valid .or. reason /= 4) error stop 'pair-only accepted transient graupel'
  call kdm6_rain_process_state_valid(q,n,bg,t,density,pidnr,qmin,ncmin, &
       qcrmin,dmr,lmin,lmax,rhomin,rhomax,pidnc,dmc,lcmin,lcmax, &
       pidni,dmi,limin,limax,valid,failure_reason=reason)
  if (valid .or. reason /= 4) error stop 'default accepted transient graupel'

  ! Exact absence and supported active density remain accepted.
  q=0.0; n=0.0; bg=0.0
  call kdm6_rain_process_state_valid(q,n,bg,t,density,pidnr,qmin,ncmin, &
       qcrmin,dmr,lmin,lmax,rhomin,rhomax,pidnc,dmc,lcmin,lcmax, &
       pidni,dmi,limin,limax,valid)
  if (.not.valid) error stop 'exact absent graupel rejected'
  q(5)=2.0e-9; bg=4.0e-12
  call kdm6_rain_process_state_valid(q,n,bg,t,density,pidnr,qmin,ncmin, &
       qcrmin,dmr,lmin,lmax,rhomin,rhomax,pidnc,dmc,lcmin,lcmax, &
       pidni,dmi,limin,limax,valid)
  if (.not.valid) error stop 'active supported graupel rejected'

  ! At the exact B cutoff, a valid density ratio is still transient. The next
  ! REAL32 value above the cutoff is active and accepted.
  q(5)=8.0e-13; bg=1.0e-15
  call kdm6_rain_process_state_valid(q,n,bg,t,density,pidnr,qmin,ncmin, &
       qcrmin,dmr,lmin,lmax,rhomin,rhomax,pidnc,dmc,lcmin,lcmax, &
       pidni,dmi,limin,limax,valid)
  if (valid) error stop 'exact B threshold transient was accepted'
  bg=nearest(bg,1.0)
  call kdm6_rain_process_state_valid(q,n,bg,t,density,pidnr,qmin,ncmin, &
       qcrmin,dmr,lmin,lmax,rhomin,rhomax,pidnc,dmc,lcmin,lcmax, &
       pidni,dmi,limin,limax,valid)
  if (.not.valid) error stop 'next REAL32 value above B threshold rejected'

  ! Both modes continue rejecting a paired but out-of-domain mean density.
  q(5)=1.0e-6; bg=q(5)/99.0
  call kdm6_rain_process_state_valid(q,n,bg,t,density,pidnr,qmin,ncmin, &
       qcrmin,dmr,lmin,lmax,rhomin,rhomax,pidnc,dmc,lcmin,lcmax, &
       pidni,dmi,limin,limax,valid,.false.,.true.)
  if (valid) error stop 'pair-only accepted unsupported density'
  call kdm6_rain_process_state_valid(q,n,bg,t,density,pidnr,qmin,ncmin, &
       qcrmin,dmr,lmin,lmax,rhomin,rhomax,pidnc,dmc,lcmin,lcmax, &
       pidni,dmi,limin,limax,valid)
  if (valid) error stop 'default accepted unsupported density'

  ! Full generation from absence remains feasible at alpha=1.
  q=0.0; n=0.0; dq=0.0; dn=0.0; bg=0.0; dbg=0.0
  dq(5)=1.0e-6; dbg=2.0e-9
  call process_fraction(alpha,feasible,status)
  if (.not.feasible .or. status /= 0 .or. alpha /= 1.0) &
       error stop 'full graupel generation was not admitted'

  ! A decreasing proposal crosses into the forbidden transient interval.
  ! The default full-PSD search must stop at a valid smaller REAL32 fraction.
  q(5)=2.0e-9; bg=4.0e-12; dq=0.0; dn=0.0
  dq(5)=-1.9996e-9; dbg=-3.9992e-12
  call process_fraction(alpha,feasible,status)
  if (.not.feasible .or. status /= 0 .or. alpha <= 0.0 .or. alpha >= 1.0) &
       error stop 'full-PSD search did not find a smaller valid fraction'
  q(5)=q(5)+alpha*dq(5); bg=bg+alpha*dbg
  call kdm6_rain_process_state_valid(q,n,bg,t,density,pidnr,qmin,ncmin, &
       qcrmin,dmr,lmin,lmax,rhomin,rhomax,pidnc,dmc,lcmin,lcmax, &
       pidni,dmi,limin,limax,valid)
  if (.not.valid .or. q(5)<=qcrmin .and. bg<=1.0e-15) &
       error stop 'selected full-PSD endpoint is outside ProgB domain'

  ! Captured V35 case: the continuous interval is nonempty, but its entire
  ! representable REAL32 alpha range puts rain Q/N on one side of the strict
  ! mass interval. The exact endpoint proof must classify NO_FEASIBLE_STEP,
  ! without walking 32 adjacent fractions and reporting SEARCH_FAILURE.
  q=[2.75130406953394413e-3,4.56007721368223429e-4,1.32635504996869713e-5, &
     2.69387441221624613e-4,0.0]
  dq=[-9.26974962567328475e-7,-1.73324687935405564e-10,-4.06129146313105593e-7, &
      8.07716446615813766e-7,5.25560949427017476e-7]
  n=[558627648.0,254149.421875,30817.58203125]
  dn=[-188002.5625,-378.579254150390625,-452.747161865234375]
  bg=0.0; dbg=7.42865213787524681e-10
  t=272.61529541015625; vp=4.60103998193517327e-4
  density=0.680995941162109375; pidnr=12566.37109375
  qmin=1.00000000362749373e-15; ncmin=10.0; qcrmin=9.99999971718068537e-10
  dmr=3.0; lmin=961.0; lmax=35000.0; rhomin=100.0; rhomax=900.0
  pidnc=523.59881591796875; dmc=3.0; lcmin=12000.0; lcmax=500000.0
  pidni=1570.79638671875; dmi=3.0; limin=9080.0; limax=1820000.0
  vf=6.93657808005809784e-3
  call kdm6_rain_process_state_valid(q,n,bg,t,density,pidnr,qmin,ncmin, &
       qcrmin,dmr,lmin,lmax,rhomin,rhomax,pidnc,dmc,lcmin,lcmax, &
       pidni,dmi,limin,limax,valid)
  if (.not.valid) error stop 'captured V35 base state should be valid'
  call kdm6_rain_process_fraction(q,dq,n,dn,bg,dbg,t,vp,.false.,density, &
       pidnr,qmin,ncmin,qcrmin,dmr,lmin,lmax,rhomin,rhomax,pidnc,dmc, &
       lcmin,lcmax,pidni,dmi,limin,limax,alpha,feasible,status,vf,0.0)
  if (feasible .or. status /= 1 .or. alpha /= 0.0) &
       error stop 'captured impossible rain interval was not pruned to NO_FEASIBLE_STEP'

  ! A supported rain pair at an interval endpoint must still be accepted.
  q=0.0; dq=0.0; n=0.0; dn=0.0; bg=0.0; dbg=0.0; t=280.0
  q(3)=2.0e-6
  n(3)=density*q(3)*(20000.0**3)/pidnr
  call kdm6_rain_process_state_valid(q,n,bg,t,density,pidnr,qmin,ncmin, &
       qcrmin,dmr,lmin,lmax,rhomin,rhomax,pidnc,dmc,lcmin,lcmax, &
       pidni,dmi,limin,limax,valid)
  if (.not.valid) error stop 'countercase rain endpoint setup is invalid'
  call kdm6_rain_process_fraction(q,dq,n,dn,bg,dbg,t,0.0,.false.,density, &
       pidnr,qmin,ncmin,qcrmin,dmr,lmin,lmax,rhomin,rhomax,pidnc,dmc, &
       lcmin,lcmax,pidni,dmi,limin,limax,alpha,feasible,status)
  if (.not.feasible .or. status /= 0 .or. alpha /= 1.0) &
       error stop 'supported endpoint was incorrectly pruned'

  ! Nonfinite proposals remain fail-closed.
  q=0.0; n=0.0; dq=0.0; dn=0.0; bg=0.0; dbg=0.0
  q(5)=2.0e-9; bg=4.0e-12
  dq(5)=ieee_value(0.0,ieee_quiet_nan)
  call process_fraction(alpha,feasible,status)
  if (feasible .or. status /= 2 .or. .not.ieee_is_finite(alpha)) &
       error stop 'nonfinite proposal did not fail closed'
  print '(a)', 'PR87 graupel process domain PASS'
contains
  subroutine process_fraction(factor,ok,search_status)
    real, intent(out) :: factor
    logical, intent(out) :: ok
    integer, intent(out) :: search_status
    call kdm6_rain_process_fraction(q,dq,n,dn,bg,dbg,t,0.0,.false., &
         density,pidnr,qmin,ncmin,qcrmin,dmr,lmin,lmax,rhomin,rhomax, &
         pidnc,dmc,lcmin,lcmax,pidni,dmi,limin,limax,factor,ok,search_status)
  end subroutine process_fraction
end program test_graupel_process_domain
"""


def _progb_roundtrip_fixture(q_bits: str, bg_bits: str, rewritten_bg_bits: str) -> str:
    original = gzip.open(SOURCE, "rt").read()
    transformed = extend_graupel_process_domain(original)
    before = _routine(original, "ProgB_param")
    after = _routine(transformed, "ProgB_param")
    before = re.sub(r"(?i)\bprogb_param\b", "progb_before", before)
    after = re.sub(r"(?i)\bprogb_param\b", "progb_after", after)
    assert "brs(i,k) = qrs(i,k,3)/rhox(i,k)" in before
    assert "brs(i,k) = qrs(i,k,3)/rhox(i,k)" not in after

    outputs = (
        "rhox cmg pidn0g avtg pvtg precg2 bvtg bvtg1 bvtg2 bvtg3 bvtg4 "
        "rslopegbmax g1pbg g3pbg g4pbg g5pbgo2 g1pdgbgmg dgbgmug1"
    ).split()
    declarations = "\n".join(f"  real :: {name}_before(1,1), {name}_after(1,1)" for name in outputs)
    args_before = ["bg_before", "q", "rhox_before", "1", "1", "1", "1", "1", "1",
                   "qcrmin", "dmg", "mug", "cmg_before", "pi", "pidn0g_before",
                   "g1pdgmg", "g1pmg", "n0g", "avtg_before", "pvtg_before",
                   "precg2_before", "bvtg_before", "bvtg1_before", "bvtg2_before",
                   "bvtg3_before", "bvtg4_before", "rslopegbmax_before", "rslopegmax",
                   "g1pbg_before", "g3pbg_before", "g4pbg_before", "g5pbgo2_before",
                   "g1pdgbgmg_before", "dgbgmug1_before", "status_before"]
    args_after = [arg.replace("_before", "_after") for arg in args_before]
    args_after[0] = "bg_after"
    args_after[1] = "q"
    args_after[2] = "rhox_after"
    call_before = ", &\n       ".join(args_before)
    call_after = ", &\n       ".join(args_after)
    property_checks = "\n".join(
        f"  if (any({name}_before /= {name}_after)) error stop 'ProgB property changed: {name}'"
        for name in outputs
    )
    return f"""module progb_test_source
  use, intrinsic :: ieee_arithmetic, only : ieee_is_finite
  implicit none
  integer, parameter :: PROGB_ABSENT=0, PROGB_TRANSIENT=1
  integer, parameter :: PROGB_PSD_ACTIVE=2, PROGB_UNSUPPORTED=3
contains
{before}
{after}
  real function rgmma(x)
    real, intent(in) :: x
    rgmma = x + 1.0
  end function rgmma
end module progb_test_source

  program test_progb_roundtrip
    use, intrinsic :: iso_fortran_env, only: int32, real64
    use progb_test_source
    implicit none
    real :: q(1,1,3), bg_before(1,1), bg_after(1,1)
    real :: qcrmin, dmg, mug, pi, g1pdgmg, g1pmg, n0g, rslopegmax
    integer :: status_before(1,1), status_after(1,1)
{declarations}
    real(real64) :: density_before, density_after

    q = 0.0
    q(1,1,3) = transfer(int(z'{q_bits}',int32), 0.0)
    bg_before(1,1) = transfer(int(z'{bg_bits}',int32), 0.0)
    bg_after = bg_before
    qcrmin=1.0e-9; dmg=3.0; mug=0.0; pi=3.1415927
    g1pdgmg=1.0; g1pmg=1.0; n0g=1.0; rslopegmax=1.0
    density_before=real(q(1,1,3),real64)/real(bg_before(1,1),real64)
    call progb_before({call_before})
    call progb_after({call_after})
    density_after=real(q(1,1,3),real64)/real(bg_after(1,1),real64)
    if (density_before > 900.0_real64 .or. density_after > 900.0_real64) &
      error stop 'preserved ProgB input is outside accepted domain'
    if (transfer(bg_before(1,1),0_int32) /= int(z'{rewritten_bg_bits}',int32)) &
      error stop 'baseline ProgB rewrite witness changed'
    if (transfer(bg_after(1,1),0_int32) /= int(z'{bg_bits}',int32)) &
      error stop 'transformed ProgB did not preserve BG'
    if (status_before(1,1) /= 2 .or. status_after(1,1) /= 2) &
      error stop 'ProgB status changed'
    if (any(rhox_before /= rhox_after) .or. rhox_after(1,1) /= 900.0) &
      error stop 'ProgB density changed'
{property_checks}
    print '(a,2(1x,es24.16))', 'PR87 ProgB BG preserved, accepted density:', &
      density_before, density_after
  end program test_progb_roundtrip
"""


def _graupel_melt_fixture() -> str:
    original = gzip.open(SOURCE, "rt").read()
    transformed = extend_graupel_process_domain(original)
    fraction = _routine(transformed, "kdm6_rain_process_fraction")
    state_valid = _routine(transformed, "kdm6_rain_process_state_valid")
    declarations_start = transformed.index("   real :: pr87_gmelt_q_fixed")
    declarations_end = transformed.index("   logical                            :: rain_process_feasible", declarations_start)
    declarations = transformed[declarations_start:declarations_end]
    fragment_start = transformed.index("              if (pgmlt(i,k) .lt. 0.0) then")
    fragment_end = transformed.index(
        "\n\n\n\n\n\n              if(qci(i,k,2).gt.0) then", fragment_start
    )
    fragment = transformed[fragment_start:fragment_end]
    assert fragment.rstrip().endswith("endif\n              endif\n            endif")
    return f"""module pr87_graupel_melt_helpers
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  implicit none
  integer, parameter :: PROGB_ABSENT=0, PROGB_TRANSIENT=1
  integer, parameter :: PROGB_PSD_ACTIVE=2, PROGB_UNSUPPORTED=3
  real, parameter :: PR85_ICE_NATIVE_INACTIVE_MAX=nearest(1.e-14,-1.0)
contains
{fraction}
{state_valid}
  subroutine apply_melt(qg0,bg0,qr0,nr0,t0,pgmlt_input,xlf_input,cpm_input, &
                        alpha,status,feasible,qg,bg,qr,nr,tout)
    implicit none
    real, intent(in) :: qg0,bg0,qr0,nr0,t0,pgmlt_input,xlf_input,cpm_input
    real, intent(out) :: alpha,qg,bg,qr,nr,tout
    integer, intent(out) :: status
    logical, intent(out) :: feasible
    real :: qci(1,1,2),qrs(1,1,3),nci(1,1,3),nrs(1,1,1),brs(1,1),t(1,1)
    real :: pgmlt(1,1)
    real :: rslope(1,1,4),n0go(1,1),xlf,cpm(1,1),dry_carrier_density(1,1)
    real :: pidnr,qmin,ncmin,qcrmin,dmr,lamdarmin,lamdarmax,pidnc,dmc
    real :: lamdacmin,lamdacmax,pidni,dmi,lamdaimin,lamdaimax,dtcld
    real :: gfac
    logical :: rain_full_evap_pending(1,1),ice_full_sublimation_pending(1,1)
    integer :: progb_status(1,1),i,k,loop,lat
{declarations.rstrip()}
    i=1; k=1; loop=1; lat=1
    qci=0.0; qrs=0.0; nci=0.0; nrs=0.0
    qrs(1,1,3)=qg0; qrs(1,1,1)=qr0; nrs(1,1,1)=nr0; brs(1,1)=bg0; t(1,1)=t0
    pgmlt(1,1)=pgmlt_input
    progb_status=PROGB_PSD_ACTIVE; rslope=1.0; n0go=1.0; xlf=xlf_input; cpm=cpm_input
    dry_carrier_density=1.0; dtcld=1.0; pidnr=1.0; qmin=0.0; ncmin=1.0
    qcrmin=1.0e-9; dmr=3.0; lamdarmin=1.0; lamdarmax=2.0
    pidnc=1.0; dmc=3.0; lamdacmin=1.0; lamdacmax=2.0
    pidni=1.0; dmi=3.0; lamdaimin=1.0; lamdaimax=2.0
    rain_full_evap_pending=.false.; ice_full_sublimation_pending=.false.
    if (progb_status(i,k) == PROGB_PSD_ACTIVE .and. qrs(i,k,3) .gt. 0.0) then
{fragment}
    alpha=pr87_gmelt_alpha; status=pr87_gmelt_search_status
    feasible=pr87_gmelt_feasible
    qg=qrs(1,1,3); bg=brs(1,1); qr=qrs(1,1,1); nr=nrs(1,1,1); tout=t(1,1)
  end subroutine apply_melt
end module pr87_graupel_melt_helpers

program test_graupel_melt_transaction
  use, intrinsic :: ieee_arithmetic, only: ieee_value, ieee_quiet_nan, ieee_positive_inf
  use pr87_graupel_melt_helpers
  implicit none
  real :: alpha,qg,bg,qr,nr,t
  logical :: feasible
  integer :: status
  character(len=16) :: test_mode

  call get_command_argument(1,test_mode)
  if (trim(test_mode) == 'cpm_zero') then
    call apply_melt(2.0e-9,4.0e-12,0.0,0.0,280.0,-2.0e-9,1.0,0.0, &
         alpha,status,feasible,qg,bg,qr,nr,t)
    error stop 'invalid cpm was not rejected'
  elseif (trim(test_mode) == 'xlf_nan') then
    call apply_melt(2.0e-9,4.0e-12,0.0,0.0,280.0,-2.0e-9, &
         ieee_value(0.0,ieee_quiet_nan),1000.0,alpha,status,feasible,qg,bg,qr,nr,t)
    error stop 'NaN xlf was not rejected'
  elseif (trim(test_mode) == 'xlf_inf') then
    call apply_melt(2.0e-9,4.0e-12,0.0,0.0,280.0,-2.0e-9, &
         ieee_value(0.0,ieee_positive_inf),1000.0,alpha,status,feasible,qg,bg,qr,nr,t)
    error stop 'infinite xlf was not rejected'
  endif

  ! Full exhaustion from an absent receiver creates a paired rain state and
  ! exact joint QG/BG absence; mass and latent heating use the same fraction.
  call apply_melt(2.0e-9,4.0e-12,0.0,0.0,280.0,-2.0e-9,1.0,1000.0, &
       alpha,status,feasible,qg,bg,qr,nr,t)
  if (.not.feasible .or. status /= 0 .or. alpha /= 1.0) &
       error stop 'full graupel melt was not accepted atomically'
  if (qg /= 0.0 .or. bg /= 0.0 .or. qr /= 2.0e-9 .or. nr <= 0.0) &
       error stop 'full melt did not preserve paired absence and receiver'
  if (qg+qr /= 2.0e-9 .or. t /= 280.0+0.001*(-2.0e-9)) &
       error stop 'full melt mass or temperature transfer was not linked'

  ! Partial donor just inside the lower strict density endpoint, with a paired receiver.
  call apply_melt(100.01/1048576.0,1.0/1048576.0,2.0e-7,100.0,280.0, &
       -1.0e-8,1.0,1000.0, &
       alpha,status,feasible,qg,bg,qr,nr,t)
  if (.not.feasible .or. status /= 0 .or. alpha <= 0.0 .or. alpha > 1.0) &
       error stop 'lower-bound partial melt was not admitted'
  if (qg <= 0.0 .or. bg <= 0.0 .or. real(qg,8)/real(bg,8) < 100.0d0 .or. &
      real(qg,8)/real(bg,8) > 900.0d0 .or. qr <= 0.0 .or. nr <= 0.0) &
       error stop 'lower-bound melt endpoint left the paired domain'

  ! Partial donor just inside the upper strict density endpoint.
  call apply_melt(899.99/1048576.0,1.0/1048576.0,2.0e-7,100.0,280.0, &
       -9.0e-8,1.0,1000.0, &
       alpha,status,feasible,qg,bg,qr,nr,t)
  if (.not.feasible .or. status /= 0 .or. alpha <= 0.0 .or. alpha > 1.0) &
       error stop 'upper-bound partial melt was not admitted'
  if (qg <= 0.0 .or. bg <= 0.0 .or. real(qg,8)/real(bg,8) < 100.0d0 .or. &
      real(qg,8)/real(bg,8) > 900.0d0 .or. qr <= 0.0 .or. nr <= 0.0) &
       error stop 'upper-bound melt endpoint left the paired domain'

  ! Below the native NR transfer cutoff, no receiver number can be created;
  ! the valid zero step withholds QG, BG, QR, NR and heat together.
  call apply_melt(5.0e-10,1.0e-12,0.0,0.0,280.0,-1.0e-10,1.0,1000.0, &
       alpha,status,feasible,qg,bg,qr,nr,t)
  if (feasible .or. status /= 1 .or. alpha /= 0.0) &
       error stop 'no-donor melt did not report a valid no-step result'
  if (qg /= 5.0e-10 .or. bg /= 1.0e-12 .or. qr /= 0.0 .or. nr /= 0.0 .or. t /= 280.0) &
       error stop 'rejected melt changed part of the linked state'
  print '(a)', 'PR87 graupel melt transaction PASS'
end program test_graupel_melt_transaction
"""


def test_source_contract_and_pinned_identity():
    source = gzip.open(SOURCE, "rt").read()
    assert hashlib.sha256(source.encode()).hexdigest() == V31_KDM6_SHA256
    changed = extend_graupel_process_domain(source)
    assert changed != source
    assert changed.count("call add_breakpoint(q0(5),dq(5),real(qcrmin,8))") == 1
    assert changed.count("call add_breakpoint(bg0,dbg,real(1.0e-15,8))") == 1
    assert changed.count("qm(5).le.real(qcrmin,8) .and. bm.le.real(1.0e-15,8)") == 2
    assert "q(5).le.qcrmin .and. bg.le.real(1.0e-15,8)" in changed
    assert "real(q(5),8)/real(bg,8).lt.real(rho_min,8)" in changed
    assert "real(q(5),8)/real(bg,8).gt.real(rho_max,8)" in changed
    assert changed.count("if (no_storable_rain_interval(lower,upper)) cycle") == 1
    assert "if (.not.pair_only) then\n          if (no_storable_rain_interval(lower,upper)) cycle\n        endif" in changed
    assert "alpha_first=real(lo)" in changed and "alpha_last=real(hi)" in changed
    assert "if (q_min_store.le.0.0d0) return" in changed
    assert "n_min_store.gt.upper_number .or. &" in changed
    assert "n_max_store.lt.lower_number" in changed
    assert source.count("          brs(i,k) = qrs(i,k,3)/rhox(i,k)\n") == 1
    assert "          brs(i,k) = qrs(i,k,3)/rhox(i,k)\n" not in changed
    with pytest.raises(ValueError, match="unexpected V31 KDM6 source hash"):
        extend_graupel_process_domain(source + "\n")


@pytest.mark.parametrize("optimization", ["O0", "O2"])
@pytest.mark.parametrize(
    "q_bits,bg_bits,rewritten_bg_bits",
    [
        pytest.param("3BC8E5CF", "36E493B2", "36E493B1", id="manufactured"),
        pytest.param("3AD8B31A", "35F68E57", "35F68E56", id="captured-v37"),
    ],
)
def test_extracted_progb_preserves_supported_bg_with_pinned_intel(
    optimization: str, q_bits: str, bg_bits: str, rewritten_bg_bits: str,
):
    fixture = _progb_roundtrip_fixture(q_bits, bg_bits, rewritten_bg_bits)
    with tempfile.TemporaryDirectory(
        prefix=f"pr87_progb_roundtrip_{optimization}_", dir="/var/tmp"
    ) as tmp:
        scratch = Path(tmp)
        source_path = scratch / "test_progb_roundtrip.F90"
        executable = scratch / "test_progb_roundtrip.exe"
        source_path.write_text(fixture)
        script = f"""
set -euo pipefail
source '{TOOLCHAIN}'
if [[ '{optimization}' == O0 ]]; then flags=("${{CLOUD_BAL_FREE_FLAGS[@]}}"); else flags=("${{CLOUD_BAL_REPRO_FLAGS[@]}}"); fi
"$CLOUD_BAL_FC" -free "${{flags[@]}}" \\
  '{source_path}' -o '{executable}'
'{executable}'
"""
        result = subprocess.run(
            ["bash", "-lc", script], cwd=scratch, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
        )
        assert result.returncode == 0, result.stdout
        assert "PR87 ProgB BG preserved, accepted density:" in result.stdout


@pytest.mark.parametrize("optimization", ["O0", "O2"])
def test_extracted_graupel_melt_transaction_with_pinned_intel(optimization: str):
    fixture = _graupel_melt_fixture()
    with tempfile.TemporaryDirectory(
        prefix=f"pr87_graupel_melt_{optimization}_", dir="/var/tmp"
    ) as tmp:
        scratch = Path(tmp)
        source_path = scratch / "test_graupel_melt_transaction.F90"
        executable = scratch / "test_graupel_melt_transaction.exe"
        source_path.write_text(fixture)
        script = f"""
set -euo pipefail
source '{TOOLCHAIN}'
if [[ '{optimization}' == O0 ]]; then flags=("${{CLOUD_BAL_FREE_FLAGS[@]}}"); else flags=("${{CLOUD_BAL_REPRO_FLAGS[@]}}"); fi
"$CLOUD_BAL_FC" -free "${{flags[@]}}" \\
  '{source_path}' -o '{executable}'
for mode in cpm_zero xlf_nan xlf_inf; do
  if '{executable}' "$mode" > "$mode.out" 2>&1; then
    echo "$mode was not rejected"; exit 1
  fi
  grep -q 'KDM6 graupel melt heat capacity is invalid' "$mode.out"
done
'{executable}'
"""
        result = subprocess.run(
            ["bash", "-lc", script], cwd=scratch, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
        )
        assert result.returncode == 0, result.stdout
        assert "PR87 graupel melt transaction PASS" in result.stdout


@pytest.mark.parametrize("optimization", ["O0", "O2"])
def test_transformed_helpers_with_pinned_intel(optimization: str):
    fixture = _fixture_source()
    with tempfile.TemporaryDirectory(
        prefix=f"pr87_graupel_domain_{optimization}_", dir="/var/tmp"
    ) as tmp:
        scratch = Path(tmp)
        source_path = scratch / "test_graupel_process_domain.F90"
        executable = scratch / "test_graupel_process_domain.exe"
        source_path.write_text(fixture)
        flags = "-O0" if optimization == "O0" else "-O2"
        script = f"""
set -euo pipefail
source '{TOOLCHAIN}'
"$CLOUD_BAL_FC" -stand f08 -warn all -check all -fpe0 -traceback {flags} \\
  -fp-model strict -fimf-arch-consistency=true -no-ftz \\
  '{source_path}' -o '{executable}'
'{executable}'
"""
        result = subprocess.run(
            ["bash", "-lc", script], cwd=scratch, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
        )
        assert result.returncode == 0, result.stdout
        assert "PR87 graupel process domain PASS" in result.stdout

