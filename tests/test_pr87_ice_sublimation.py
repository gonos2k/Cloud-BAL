#!/usr/bin/env python3
"""Source-contract and pinned-Intel tests for pending ice sublimation."""
from __future__ import annotations

import gzip
import hashlib
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA256 = "8679f2e7c51940ab740bbe9e768dbb68156e9c655f459245f522f7983fb99eb9"
V39_FINAL_SOURCE_SHA256 = "6a7f6e154390ad6d5da8ca18ea4115ad66effa5b1dbdbf73754edd357b6b4293"
V39_CAP_ORDER_SOURCE_SHA256 = "faa81931252f6f28cc74ca3367a5c721668fe9ca0f01225641fb495a93ca6959"


def _source_and_overlay() -> tuple[str, str]:
    import runpy

    archive = ROOT / "docs/evidence/pr87_two_step_v21_20261016/module_mp_kdm6.F.gz"
    original = gzip.decompress(archive.read_bytes()).decode("utf-8")
    assert hashlib.sha256(original.encode()).hexdigest() == SOURCE_SHA256
    overlay = runpy.run_path(str(ROOT / "tools/pr87_ice_sublimation.py"))[
        "extend_ice_sublimation_pending"
    ]
    return original, overlay(original)


def _helper_module(generated: str) -> str:
    fraction_start = generated.index("    subroutine kdm6_rain_process_fraction(")
    fraction_end = generated.index(
        "    end subroutine kdm6_rain_process_fraction", fraction_start
    ) + len("    end subroutine kdm6_rain_process_fraction")
    fraction = generated[fraction_start:fraction_end]
    state_match = re.search(
        r"(?m)^[ \t]*subroutine kdm6_rain_process_state_valid\(", generated
    )
    assert state_match is not None
    state_start = state_match.start()
    state_end = generated.index("end subroutine kdm6_rain_process_state_valid", state_start)
    state = generated[state_start:state_end + len("end subroutine kdm6_rain_process_state_valid")]
    return (
        "module pr87_ice_sublimation_helpers\n"
        "  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite\n"
        "  implicit none\n"
        "  real, parameter :: PR85_ICE_NATIVE_INACTIVE_MAX=nearest(1.e-14,-1.0)\n"
        "contains\n"
        f"{fraction}\n{state}\n"
        "end module pr87_ice_sublimation_helpers\n"
    )


def test_pr87_ice_sublimation_source_contract() -> None:
    original, generated = _source_and_overlay()

    early_reset = (
        "              if(pidep(i,k).eq.-(qci(i,k,2))/dtcld) then\n"
        "                 nci(i,k,2) = 0.\n"
        "              endif\n"
    )
    assert original.count(early_reset) == 1
    assert early_reset not in generated
    reset_guard = (
        "if(pidep(i,k).eq.-(qci(i,k,2))/dtcld) then\n"
        "                 nci(i,k,2) = 0."
    )
    assert reset_guard not in generated
    mutant = generated.replace(
        "if(pidep(i,k).eq.-(qci(i,k,2))/dtcld) then\n"
        "                 ice_full_sublimation_pending(i,k) = .true.",
        "if(pidep(i,k).eq.-(qci(i,k,2))/dtcld) then\n"
        "                 nci(i,k,2) = 0.\n"
        "                 ice_full_sublimation_pending(i,k) = .true.",
        1,
    )
    assert mutant != generated and reset_guard in mutant
    assert "ice_full_sublimation_pending(i,k) = .true." in generated
    assert "if (present(ice_sublimation_pending))" in generated
    assert "ice_sublimation_pending=ice_full_sublimation_pending(i,k)" in generated

    # The cold admission/search sites carry the pending bit. Warm and final
    # stored-state validation retain the strict default contract.
    cold, warm = generated.split("call kdm6_rain_process_fraction(rain_q_before,rain_warm_q_process", 1)
    assert cold.count("ice_sublimation_pending=ice_full_sublimation_pending(i,k)") == 8
    assert "ice_sublimation_pending=ice_full_sublimation_pending(i,k)" not in warm
    stored_check = generated.split("call kdm6_rain_process_state_valid(rain_q_after,rain_n_after,brs(i,k)", 1)[1]
    stored_check = stored_check.split("if (.not.rain_stored_state_feasible)", 1)[0]
    assert "ice_sublimation_pending" not in stored_check

    # The endpoint is paired before the unchanged strict validator and commit.
    endpoint = generated.index("if (ice_full_sublimation_pending(i,k) .and. rain_q_after(2).eq.0.0)")
    strict = generated.index("call kdm6_rain_process_state_valid(rain_q_after,rain_n_after,brs(i,k)", endpoint)
    assert endpoint < strict
    assert "rain_n_after(2)=0.0" in generated[endpoint:strict]
    assert "q(2).gt.0.0 .and. n(2).eq.0.0" not in generated
    assert "gammaComposite" in generated
    assert "n_sed" in generated or "loop,n," in generated


def test_pr87_ice_sublimation_fraction_and_pair_validation() -> None:
    _, generated = _source_and_overlay()
    scratch = Path(tempfile.mkdtemp(prefix="pr87_ice_sublimation_", dir="/var/tmp"))
    module = scratch / "ice_helpers.F90"
    driver = scratch / "driver.F90"
    module.write_text(_helper_module(generated))
    driver.write_text(_DRIVER)

    for profile in ("O0", "O2"):
        build = scratch / profile
        build.mkdir()
        command = [
            "bash", "-c",
            'source "$1/tests/intel_toolchain.sh" && '
            'if [[ "$2" == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); '
            'else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi && '
            '"$CLOUD_BAL_FC" "${flags[@]}" -free -module "$5" -I "$5" '
            '"$3" "$4" -o "$5/test.exe" && "$5/test.exe"',
            "pr87-ice-sublimation-test", str(ROOT), profile,
            str(module), str(driver), str(build),
        ]
        result = subprocess.run(command, cwd=build, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                check=False)
        assert result.returncode == 0, result.stdout
        assert "PR87 ice sublimation pending cases PASS" in result.stdout, result.stdout
        print(f"{profile}: {result.stdout.strip()}")


def _v39_source_and_transform() -> tuple[str, str]:
    import runpy

    archive = ROOT / "docs/evidence/pr87_two_step_v39_20261016/module_mp_kdm6.F.gz"
    original = gzip.decompress(archive.read_bytes()).decode("utf-8")
    assert hashlib.sha256(original.encode()).hexdigest() == V39_FINAL_SOURCE_SHA256
    transform = runpy.run_path(str(ROOT / "tools/pr87_ice_sublimation.py"))[
        "correct_ice_sublimation_cap_order"
    ]
    return original, transform(original)


def _v39_cap_fragment(generated: str) -> str:
    start = generated.index("              if(pidep(i,k).lt.0.) then")
    end = generated.index(
        "              if(abs(prevp(i,k)+pinud(i,k)+pidep(i,k)).ge.abs(satdt)) ifsat = 1",
        start,
    )
    return generated[start:end]


def _v39_commit_fragment(generated: str) -> str:
    start = generated.index("            pr87_ice_sublimation_extinctions=0")
    end = generated.index(
        "            if (rain_full_evap_pending(i,k) .and. rain_q_after(3).eq.0.0) then",
        start,
    )
    return generated[start:end]


def test_pr87_v39_pending_follows_both_native_caps() -> None:
    original, generated = _v39_source_and_transform()
    old_cap_lines = (
        "                pidep(i,k) = max(pidep(i,k),-(qci(i,k,2))/dtcld)\n"
        "                pidep(i,k) = max(max(pidep(i,k),(satdt)/2),supice)\n"
    )
    assert original.count(old_cap_lines) == generated.count(old_cap_lines) == 1

    block = _v39_cap_fragment(generated)
    raw_capture = block.index("pr87_ice_raw_pidep_before_caps=pidep(i,k)")
    first_cap = block.index(old_cap_lines.splitlines()[0])
    second_cap = block.index(old_cap_lines.splitlines()[1])
    approved_test = block.index("if (pidep(i,k).eq.-(qci(i,k,2))/dtcld) then")
    assert raw_capture < first_cap < second_cap < approved_test
    assert block.count("ice_full_sublimation_pending(i,k) = .true.") == 1
    assert block.count("ice_sublimation_event_count(i,k) = &") == 1
    assert "ice_sublimation_raw_pidep(i,k) = pr87_ice_raw_pidep_before_caps" in block
    assert "ice_sublimation_capped_pidep(i,k) = pidep(i,k)" in block
    assert "nci(i,k,2) =" not in block

    # The sole number clear remains conditional on a zero stored mass.
    commit = generated.index(
        "if (ice_full_sublimation_pending(i,k) .and. rain_q_after(2).eq.0.0)"
    )
    endpoint_commit = generated[commit:generated.index(
        "            if (rain_full_evap_pending", commit
    )]
    assert "rain_n_after(2)=0.0" in endpoint_commit
    assert "q(2).gt.0.0 .and. n(2).eq.0.0" not in generated


def test_pr87_v39_cap_fragment_intel_o0_o2() -> None:
    _, generated = _v39_source_and_transform()
    scratch = Path(tempfile.mkdtemp(prefix="pr87_ice_cap_order_", dir="/var/tmp"))
    driver = scratch / "driver.F90"
    source = _V39_CAP_DRIVER.replace("! CAP_FRAGMENT", _v39_cap_fragment(generated))
    source = source.replace("! COMMIT_FRAGMENT", _v39_commit_fragment(generated))
    driver.write_text(source)

    for profile in ("O0", "O2"):
        build = scratch / profile
        build.mkdir()
        command = [
            "bash", "-c",
            'source "$1/tests/intel_toolchain.sh" && '
            'if [[ "$2" == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); '
            'else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi && '
            '"$CLOUD_BAL_FC" "${flags[@]}" -free -module "$4" -I "$4" '
            '"$3" -o "$4/test.exe" && "$4/test.exe"',
            "pr87-ice-cap-order-test", str(ROOT), profile, str(driver), str(build),
        ]
        result = subprocess.run(command, cwd=build, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                check=False)
        assert result.returncode == 0, result.stdout
        assert "PR87 V39 capped sublimation cases PASS" in result.stdout, result.stdout
        print(f"V39 {profile}: {result.stdout.strip()}")


def _v39_complete_source_and_transform() -> tuple[str, str]:
    import runpy

    archive = ROOT / "docs/evidence/pr87_two_step_v39_20261016/module_mp_kdm6.F.gz"
    original = gzip.decompress(archive.read_bytes()).decode("utf-8")
    cap = runpy.run_path(str(ROOT / "tools/pr87_ice_sublimation.py"))[
        "correct_ice_sublimation_cap_order"
    ](original)
    assert hashlib.sha256(cap.encode()).hexdigest() == V39_CAP_ORDER_SOURCE_SHA256
    transform = runpy.run_path(str(ROOT / "tools/pr87_ice_sublimation.py"))[
        "complete_cold_ice_extinction"
    ]
    return original, transform(original)


def _v39_aggregate_fragment(generated: str, stage: str) -> str:
    if stage == "NG":
        start = generated.index("            if (ieee_is_finite(rain_q_before(2))) then")
        end = generated.index("            rain_ng_n_process(1)=", start)
    elif stage == "G":
        start = generated.index("            if (ieee_is_finite(rain_q_fixed(2))) then")
        end = generated.index("            rain_ng_aut_q_fixed=rain_q_fixed", start)
    else:
        raise ValueError(stage)
    return generated[start:end]


def test_pr87_v39_cold_aggregate_extinction_contract() -> None:
    _, generated = _v39_complete_source_and_transform()
    assert generated.count("integer, dimension(its:ite,kts:kte) :: ice_extinction_cause") == 1
    assert generated.count("ice_extinction_cause(i,k)=ior(ice_extinction_cause(i,k),1)") == 1
    ng = _v39_aggregate_fragment(generated, "NG")
    g = _v39_aggregate_fragment(generated, "G")
    assert "rain_ng_q_process(2).le.-rain_q_before(2)" in ng
    assert "ice_extinction_cause(i,k)=ior(ice_extinction_cause(i,k),2)" in ng
    assert "rain_g_q_process(2).le.-rain_q_fixed(2)" in g
    assert "ice_extinction_cause(i,k)=ior(ice_extinction_cause(i,k),4)" in g
    assert generated.index("rain_q_fixed=rain_q_before+rain_ng_alpha") < generated.index(g)
    assert generated.index("rain_q_fixed=rain_q_fixed+rain_aut_alpha") < generated.index(g)
    assert generated.index(g) < generated.index("rain_ng_aut_q_fixed=rain_q_fixed")

    # Only an approved process path can set the marker. Final zero-Q pairing
    # still runs before the unchanged strict stored-state validation.
    assert "rain_n_after(2)=0.0" in generated
    marker = generated.index("if (ice_full_sublimation_pending(i,k) .and. &")
    clear = generated.index("rain_n_after(2)=0.0", marker)
    strict = generated.index("call kdm6_rain_process_state_valid(rain_q_after,rain_n_after,brs(i,k)", clear)
    assert marker < clear < strict
    assert "file='pr87_ice_extinction.raw'" in generated
    assert "'PR87_ICE_EXTINCTION'" in generated
    assert "ice_extinction_cause(i,k).le.1" in generated
    assert generated.index("file='pr87_ice_extinction.raw'") < generated.index(
        "! Commit the validated REAL32 transaction atomically."
    )


def test_pr87_v39_cold_aggregate_helpers_intel_o0_o2() -> None:
    _, generated = _v39_complete_source_and_transform()
    scratch = Path(tempfile.mkdtemp(prefix="pr87_ice_aggregate_", dir="/var/tmp"))
    module = scratch / "ice_helpers.F90"
    driver = scratch / "driver.F90"
    module.write_text(_helper_module(generated))
    source = _V39_AGGREGATE_DRIVER.replace("! NG_ELIGIBILITY", _v39_aggregate_fragment(generated, "NG"))
    source = source.replace("! G_ELIGIBILITY", _v39_aggregate_fragment(generated, "G"))
    source = source.replace("! ENDPOINT_COMMIT", _v39_commit_fragment(generated))
    driver.write_text(source)

    for profile in ("O0", "O2"):
        build = scratch / profile
        build.mkdir()
        command = [
            "bash", "-c",
            'source "$1/tests/intel_toolchain.sh" && '
            'if [[ "$2" == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); '
            'else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi && '
            '"$CLOUD_BAL_FC" "${flags[@]}" -fpe0 -free -module "$5" -I "$5" '
            '"$3" "$4" -o "$5/test.exe" && "$5/test.exe"',
            "pr87-ice-aggregate-test", str(ROOT), profile,
            str(module), str(driver), str(build),
        ]
        result = subprocess.run(command, cwd=build, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                check=False)
        assert result.returncode == 0, result.stdout
        assert "PR87 V39 aggregate ice extinction cases PASS" in result.stdout, result.stdout
        print(f"V39 aggregate {profile}: {result.stdout.strip()}")


_DRIVER = r"""
program test_pr87_ice_sublimation
  use pr87_ice_sublimation_helpers
  use, intrinsic :: iso_fortran_env, only: int32
  implicit none
  real :: q(5),n(3),qproc(5),nproc(3),fraction
  real :: bg,bgproc,temp,tempproc,qraw,pidep,qafter,nsource,dt
  logical :: valid,feasible
  integer :: status
  integer(int32) :: qafter_bits

  q=0.0; n=0.0; bg=0.0; temp=273.15
  q(2)=0.0; n(2)=4.0
  call state_check(q,n,.false.,valid)
  if (valid) error stop 'unflagged ice orphan accepted'
  call state_check(q,n,.true.,valid)
  if (.not.valid) error stop 'pending exact-zero ice mass rejected'

  q(2)=-1.0e-44
  call state_check(q,n,.true.,valid)
  if (valid) error stop 'negative ice mass accepted under pending flag'
  q(2)=1.0e-44; n(2)=-1.0
  call state_check(q,n,.true.,valid)
  if (valid) error stop 'negative ice number accepted under pending flag'
  q(2)=1.0e-44; n(2)=0.0
  call state_check(q,n,.true.,valid)
  if (valid) error stop 'positive ice mass with zero number accepted'

  ! Preserve source-order REAL32 behavior for the actual full-rate predicate.
  qraw=transfer(int(z'0000003E',int32),0.0)
  nsource=4.0; dt=20.0
  pidep=-qraw/dt
  if (pidep.ne.-qraw/dt) error stop 'exact full-sublimation predicate changed'
  qafter=qraw+dt*pidep
  qafter_bits=transfer(qafter,qafter_bits)
  if (qafter_bits.ne.int(z'00000002',int32)) error stop 'source order no longer leaves Q bits 0x2'
  if (nsource.ne.4.0) error stop 'source-order full-rate test changed NI before endpoint'
  q=0.0; n=0.0; q(2)=qafter; n(2)=nsource
  call state_check(q,n,.true.,valid)
  if (.not.valid) error stop 'strict transient ice pair rejected after source-order rounding'
  n(2)=0.0
  call state_check(q,n,.true.,valid)
  if (valid) error stop 'early-reset mutation accepted positive-QI with zero NI'

  q=0.0; n=0.0; q(2)=1.0e-44; n(2)=4.0
  qproc=0.0; nproc=0.0; qproc(2)=-q(2); bgproc=0.0; tempproc=0.0
  call fraction_check(q,qproc,n,nproc,bg,bgproc,temp,tempproc,.true.,fraction,feasible,status)
  if (.not.feasible .or. status.ne.0 .or. fraction.ne.1.0) &
    error stop 'pending full sublimation endpoint was not admitted'
  q=q+fraction*qproc; n=n+fraction*nproc
  if (q(2).ne.0.0 .or. n(2).ne.4.0) error stop 'search endpoint changed moments'
  if (q(2).eq.0.0) n(2)=0.0
  call state_check(q,n,.false.,valid)
  if (.not.valid) error stop 'paired full-sublimation endpoint rejected'

  q=0.0; n=0.0; q(2)=1.0e-44; n(2)=4.0
  qproc=0.0; nproc=0.0; qproc(2)=-0.5e-44
  call fraction_check(q,qproc,n,nproc,bg,bgproc,temp,tempproc,.true.,fraction,feasible,status, &
                      vaporfixed=1.0,vaporprocess=-2.0)
  if (.not.feasible .or. abs(fraction-0.5).gt.1.0e-6) &
    error stop 'partial vapor-capped sublimation fraction changed'
  q=q+fraction*qproc; n=n+fraction*nproc
  if (q(2).eq.0.0 .or. n(2).ne.4.0) error stop 'partial endpoint extinguished number'
  call state_check(q,n,.false.,valid)
  if (.not.valid) error stop 'paired partial-sublimation endpoint rejected'

  print '(a)', 'PR87 ice sublimation pending cases PASS'
contains
  subroutine state_check(qin,nin,pending,ok)
    real, intent(in) :: qin(5),nin(3)
    logical, intent(in) :: pending
    logical, intent(out) :: ok
    call kdm6_rain_process_state_valid(qin,nin,0.0,273.15,1.0,1.0, &
      0.0,0.0,0.0,3.0,1.0,2.0,100.0,900.0,1.0,3.0,1.0,2.0, &
      1.0,3.0,1.0,2.0,ok,consumer_pair_only=.false., &
      ice_transient_mass_limit=PR85_ICE_NATIVE_INACTIVE_MAX, &
      ice_sublimation_pending=pending)
  end subroutine state_check

  subroutine fraction_check(qfixed,qprocess,nfixed,nprocess,bgfixed,bgprocess, &
                            tfixed,tprocess,pending,a,ok,istat,vaporfixed,vaporprocess)
    real, intent(in) :: qfixed(5),qprocess(5),nfixed(3),nprocess(3)
    real, intent(in) :: bgfixed,bgprocess,tfixed,tprocess
    logical, intent(in) :: pending
    real, intent(out) :: a
    logical, intent(out) :: ok
    integer, intent(out) :: istat
    real, intent(in), optional :: vaporfixed,vaporprocess
    call kdm6_rain_process_fraction(qfixed,qprocess,nfixed,nprocess, &
      bgfixed,bgprocess,tfixed,tprocess,.false.,1.0,1.0,0.0,0.0, &
      0.0,3.0,1.0,2.0,100.0,900.0,1.0,3.0,1.0,2.0, &
      1.0,3.0,1.0,2.0,a,ok,istat,consumer_pair_only=.false., &
      ice_transient_mass_limit=PR85_ICE_NATIVE_INACTIVE_MAX, &
      ice_sublimation_pending=pending,vapor_fixed=vaporfixed,vapor_process=vaporprocess)
  end subroutine fraction_check
end program test_pr87_ice_sublimation
"""


_V39_AGGREGATE_DRIVER = r"""
program test_v39_aggregate_ice_extinction
  use pr87_ice_sublimation_helpers
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite, ieee_value, &
       ieee_quiet_nan, ieee_positive_inf
  implicit none
  call run_sequence(2.0**(-50),-2.0**(-52),-2.0**(-52),-2.0**(-51), &
       0.0,2,.true.,.true.,8.0)
  call run_sequence(2.0**(-50),-2.0**(-52),0.0,0.0, &
       -3.0*2.0**(-52),4,.true.,.true.,8.0)
  call run_sequence(2.0**(-50),-2.0**(-52),0.0,0.0, &
       0.0,0,.false.,.false.,8.0)
  call run_sequence(2.0**(-50),-2.0**(-50),0.0,0.0, &
       0.0,2,.true.,.false.,8.0,1.0,-2.0)
  call run_sequence(4.2936549e-15,-4.2936549e-15/4.0,-4.2936549e-15/4.0, &
       -4.2936549e-15/2.0,0.0,2,.true.,.true.,8.823875)
  call check_invalid_endpoint(-1.0,.false.)
  call check_invalid_endpoint(ieee_value(0.0,ieee_quiet_nan),.true.)
  call check_invalid_endpoint(ieee_value(0.0,ieee_positive_inf),.true.)
  call check_invalid_endpoint(8.0,.false.)
  call reject_invalid_base()
  print '(a)', 'PR87 V39 aggregate ice extinction cases PASS'
contains
  subroutine run_sequence(qin,ng1,ng2,ng3,gdelta,expected_cause,expected_pending, &
                          expect_zero,nin,vaporfixed,vaporprocess)
    real,intent(in)::qin,ng1,ng2,ng3,gdelta,nin
    integer,intent(in)::expected_cause
    logical,intent(in)::expected_pending,expect_zero
    real,intent(in),optional::vaporfixed,vaporprocess
    real::rain_q_before(5),rain_q_fixed(5),rain_ng_q_process(5),rain_g_q_process(5)
    real::rain_n_before(3),rain_n_fixed(3),rain_ng_n_process(3),rain_g_n_process(3)
    real::rain_bg_fixed,rain_bg_process,rain_t_fixed,rain_t_process
    real::rain_q_after(5),rain_n_after(3),alpha_ng,alpha_g
    real::pr87_ice_sublimation_n_preclear,pr87_ice_sublimation_dn
    logical::ice_full_sublimation_pending(1,1),rain_full_evap_pending(1,1), &
         rain_composite_valid,feasible
    integer::ice_extinction_cause(1,1),i,k,status,pr87_ice_sublimation_extinctions
    i=1;k=1
    rain_q_before=0.0;rain_q_before(2)=qin
    rain_ng_q_process=0.0
    rain_ng_q_process(2)=ng1+ng2+ng3
    rain_g_q_process=0.0;rain_g_q_process(2)=gdelta
    rain_n_before=0.0;rain_n_before(2)=nin
    rain_ng_n_process=0.0;rain_g_n_process=0.0
    rain_bg_fixed=0.0;rain_bg_process=0.0;rain_t_fixed=273.15;rain_t_process=0.0
    ice_full_sublimation_pending=.false.;ice_extinction_cause=0
    ! NG_ELIGIBILITY
    rain_q_fixed=rain_q_before;rain_n_fixed=rain_n_before
    call fraction_check(rain_q_fixed,rain_ng_q_process,rain_n_fixed,rain_ng_n_process, &
         rain_bg_fixed,0.0,rain_t_fixed,0.0,ice_full_sublimation_pending(1,1), &
         alpha_ng,feasible,status,vaporfixed,vaporprocess)
    if (.not.feasible .or. status.ne.0) error stop 'NG fixture fraction rejected'
    rain_q_fixed=rain_q_fixed+alpha_ng*rain_ng_q_process
    rain_n_fixed=rain_n_fixed+alpha_ng*rain_ng_n_process
    ! G proposal is evaluated against the current fixed cloud-ice state.
    ! G_ELIGIBILITY
    rain_q_after=rain_q_fixed;rain_n_after=rain_n_fixed
    alpha_g=0.0
    if (any(rain_g_q_process.ne.0.0)) then
      call fraction_check(rain_q_fixed,rain_g_q_process,rain_n_fixed,rain_g_n_process, &
           rain_bg_fixed,rain_bg_process,rain_t_fixed,rain_t_process, &
           ice_full_sublimation_pending(1,1),alpha_g,feasible,status)
      if (.not.feasible .or. status.ne.0) error stop 'G fixture fraction rejected'
      rain_q_after=rain_q_fixed+alpha_g*rain_g_q_process
      rain_n_after=rain_n_fixed+alpha_g*rain_g_n_process
    endif
    if (ice_extinction_cause(1,1).ne.expected_cause) then
      print *, 'cause,expected,Q,dNG,dG=',ice_extinction_cause(1,1),expected_cause, &
           qin,rain_ng_q_process(2),rain_g_q_process(2)
      error stop 'cold cause bits mismatch'
    endif
    if (ice_full_sublimation_pending(1,1) .neqv. expected_pending) error stop 'cold pending flag mismatch'
    rain_full_evap_pending=.false.
    rain_composite_valid=.true.
    ! ENDPOINT_COMMIT
    if (expect_zero) then
      if (rain_q_after(2).ne.0.0) error stop 'eligible endpoint missed exact zero Q'
      if (rain_n_after(2).ne.0.0) error stop 'exact zero Q did not clear number'
      if (pr87_ice_sublimation_dn.ne.-nin) error stop 'extinction number ledger mismatch'
    else
      if (rain_q_after(2).le.0.0) error stop 'partial process unexpectedly extinguished Q'
      if (rain_n_after(2).ne.nin) error stop 'positive Q did not preserve number'
      if (pr87_ice_sublimation_dn.ne.0.0) error stop 'partial process logged number extinction'
    endif
  end subroutine run_sequence

  subroutine check_invalid_endpoint(nin,composite_ok)
    real,intent(in)::nin
    logical,intent(in)::composite_ok
    real::rain_q_after(5),rain_n_after(3)
    real::pr87_ice_sublimation_n_preclear,pr87_ice_sublimation_dn
    logical::ice_full_sublimation_pending(1,1),rain_full_evap_pending(1,1),rain_composite_valid
    integer::pr87_ice_sublimation_extinctions,i,k
    i=1;k=1;rain_q_after=0.0;rain_n_after=0.0;rain_n_after(2)=nin
    rain_composite_valid=composite_ok
    ice_full_sublimation_pending=.true.;rain_full_evap_pending=.false.
    ! ENDPOINT_COMMIT
    if (ieee_is_finite(nin)) then
      if (rain_n_after(2).ne.nin) error stop 'invalid endpoint changed NI'
    else
      if (ieee_is_finite(rain_n_after(2))) error stop 'nonfinite endpoint changed NI'
    endif
    if (pr87_ice_sublimation_dn.ne.0.0) error stop 'invalid endpoint recorded extinction'
  end subroutine check_invalid_endpoint

  subroutine reject_invalid_base()
    real::rain_q_before(5),rain_ng_q_process(5)
    logical::ice_full_sublimation_pending(1,1)
    integer::ice_extinction_cause(1,1),i,k
    i=1;k=1;rain_q_before=0.0;rain_q_before(2)=-1.0
    rain_ng_q_process=0.0;rain_ng_q_process(2)=1.0
    ice_full_sublimation_pending=.false.;ice_extinction_cause=0
    ! NG_ELIGIBILITY
    if (ice_full_sublimation_pending(1,1) .or. ice_extinction_cause(1,1).ne.0) &
      error stop 'negative base received cold extinction permission'
  end subroutine reject_invalid_base

  subroutine fraction_check(qfixed,qprocess,nfixed,nprocess,bgfixed,bgprocess, &
                            tfixed,tprocess,pending,a,ok,istat,vaporfixed,vaporprocess)
    real,intent(in)::qfixed(5),qprocess(5),nfixed(3),nprocess(3)
    real,intent(in)::bgfixed,bgprocess,tfixed,tprocess
    logical,intent(in)::pending
    real,intent(out)::a
    logical,intent(out)::ok
    integer,intent(out)::istat
    real,intent(in),optional::vaporfixed,vaporprocess
    call kdm6_rain_process_fraction(qfixed,qprocess,nfixed,nprocess, &
      bgfixed,bgprocess,tfixed,tprocess,.false.,1.0,1.0,0.0,0.0, &
      0.0,3.0,1.0,2.0,100.0,900.0,1.0,3.0,1.0,2.0, &
      1.0,3.0,1.0,2.0,a,ok,istat,consumer_pair_only=.false., &
      ice_transient_mass_limit=PR85_ICE_NATIVE_INACTIVE_MAX, &
      ice_sublimation_pending=pending,vapor_fixed=vaporfixed,vapor_process=vaporprocess)
  end subroutine fraction_check
end program test_v39_aggregate_ice_extinction
"""


_V39_CAP_DRIVER = r"""
program test_v39_ice_cap_order
  use, intrinsic :: iso_fortran_env, only: int32
  implicit none
  real :: q,n,dt,full,raw,result_rate,legacy_rate,sat,sup
  real :: q_before,n_before,raw_saved,capped_saved,q_saved,n_saved
  real :: pidep(1,1),qci(1,1,2),nci(1,1,2),dtcld,satdt,supice,prevp(1,1),pinud(1,1)
  real :: ice_sublimation_raw_pidep(1,1),ice_sublimation_capped_pidep(1,1)
  real :: ice_sublimation_q_before(1,1),ice_sublimation_n_before(1,1)
  real :: rain_q_after(5),rain_n_after(3),pr87_ice_sublimation_n_preclear
  real :: pr87_ice_sublimation_dn,pr87_ice_raw_pidep_before_caps
  logical :: ice_full_sublimation_pending(1,1)
  integer :: ice_sublimation_event_count(1,1),pr87_ice_sublimation_extinctions,i,k,case_id
  integer(int32) :: rate_bits

  q=4.2936549e-15; n=8.823875; dt=20.0; full=-(q/dt)
  do case_id=1,4
    select case(case_id)
    case(1) ! Raw tendency is more negative; first cap approves full removal.
      raw=2.0*full; sat=4.0*full; sup=2.0*full
    case(2) ! Raw tendency is exactly the full-removal rate.
      raw=full; sat=4.0*full; sup=2.0*full
    case(3) ! Thermodynamic cap reduces removal below full extinction.
      raw=2.0*full; sat=full; sup=0.25*full
    case(4) ! Raw tendency remains partial after both caps.
      raw=0.5*full; sat=4.0*full; sup=2.0*full
    end select
    call apply_caps(raw,q,n,dt,sat,sup,result_rate,ice_full_sublimation_pending(1,1), &
         raw_saved,capped_saved,q_saved,n_saved,ice_sublimation_event_count(1,1), &
         rain_n_after(2),pr87_ice_sublimation_dn,pr87_ice_sublimation_extinctions)
    legacy_rate=legacy_caps(raw,q,dt,sat,sup)
    rate_bits=transfer(result_rate,rate_bits)
    if (rate_bits.ne.transfer(legacy_rate,rate_bits)) error stop 'cap rate changed from native formula'
    select case(case_id)
    case(1,2)
      if (.not.ice_full_sublimation_pending(1,1)) error stop 'approved full cap was not marked'
      if (raw_saved.ne.raw .or. capped_saved.ne.full) error stop 'raw/capped ledger mismatch'
      if (q_saved.ne.q .or. n_saved.ne.n) error stop 'pre-cap state ledger mismatch'
      if (ice_sublimation_event_count(1,1).ne.1) error stop 'approved event count mismatch'
      if (rain_n_after(2).ne.n) error stop 'positive QI incorrectly cleared NI'
      call apply_endpoint(0.0,n,.true.,rain_n_after(2),pr87_ice_sublimation_dn, &
           pr87_ice_sublimation_extinctions)
      if (rain_n_after(2).ne.0.0 .or. pr87_ice_sublimation_dn.ne.-n) &
        error stop 'zero-mass full-extinction commit changed'
    case(3,4)
      if (ice_full_sublimation_pending(1,1)) error stop 'non-full capped rate was marked'
      if (ice_sublimation_event_count(1,1).ne.0) error stop 'non-full event was counted'
      if (raw_saved.ne.0.0 .or. capped_saved.ne.0.0) error stop 'unapproved event entered ledger'
    end select
  enddo
  print '(a)', 'PR87 V39 capped sublimation cases PASS'
contains
  real function legacy_caps(r,qin,dtin,satin,supin)
    real,intent(in)::r,qin,dtin,satin,supin
    legacy_caps=max(r,-qin/dtin)
    legacy_caps=max(max(legacy_caps,satin/2.0),supin)
  end function legacy_caps

  subroutine apply_caps(r,qin,nin,dtin,satin,supin,rout,pending,rawout,capout,qout,nout, &
                        events,ncommit,dn,extinctions)
    real,intent(in)::r,qin,nin,dtin,satin,supin
    real,intent(out)::rout,rawout,capout,qout,nout,ncommit,dn
    logical,intent(out)::pending
    integer,intent(out)::events,extinctions
    real::pidep(1,1),qci(1,1,2),nci(1,1,2),dtcld,satdt,supice,prevp(1,1),pinud(1,1)
    real::ice_sublimation_raw_pidep(1,1),ice_sublimation_capped_pidep(1,1)
    real::ice_sublimation_q_before(1,1),ice_sublimation_n_before(1,1)
    real::rain_q_after(5),rain_n_after(3),pr87_ice_sublimation_n_preclear
    real::pr87_ice_sublimation_dn,pr87_ice_raw_pidep_before_caps
    logical::ice_full_sublimation_pending(1,1),rain_full_evap_pending(1,1)
    integer::ice_sublimation_event_count(1,1),pr87_ice_sublimation_extinctions,i,k
    i=1;k=1;dtcld=dtin;satdt=satin;supice=supin;prevp=0.0;pinud=0.0
    pidep(1,1)=r;qci=0.0;nci=0.0;qci(1,1,2)=qin;nci(1,1,2)=nin
    ice_sublimation_raw_pidep=0.0;ice_sublimation_capped_pidep=0.0
    ice_sublimation_q_before=0.0;ice_sublimation_n_before=0.0
    ice_sublimation_event_count=0;ice_full_sublimation_pending=.false.
    ! CAP_FRAGMENT
    if (nci(1,1,2).ne.nin) error stop 'cap fragment changed NI'
    rout=pidep(1,1);pending=ice_full_sublimation_pending(1,1)
    rawout=ice_sublimation_raw_pidep(1,1);capout=ice_sublimation_capped_pidep(1,1)
    qout=ice_sublimation_q_before(1,1);nout=ice_sublimation_n_before(1,1)
    events=ice_sublimation_event_count(1,1)
    rain_q_after=0.0;rain_n_after=0.0;rain_q_after(2)=qin;rain_n_after(2)=nin
    rain_full_evap_pending(1,1)=.false.
    ! COMMIT_FRAGMENT
    ncommit=rain_n_after(2)
  end subroutine apply_caps

  subroutine apply_endpoint(qin,nin,pending,nout,dnout,extinctions)
    real,intent(in)::qin,nin
    logical,intent(in)::pending
    real,intent(out)::nout,dnout
    integer,intent(out)::extinctions
    real::rain_q_after(5),rain_n_after(3),pr87_ice_sublimation_n_preclear
    real::pr87_ice_sublimation_dn
    logical::ice_full_sublimation_pending(1,1),rain_full_evap_pending(1,1)
    integer::pr87_ice_sublimation_extinctions
    rain_q_after=0.0;rain_n_after=0.0;rain_q_after(2)=qin;rain_n_after(2)=nin
    ice_full_sublimation_pending=.false.;ice_full_sublimation_pending(1,1)=pending
    rain_full_evap_pending=.false.
    i=1;k=1
    ! COMMIT_FRAGMENT
    nout=rain_n_after(2);dnout=pr87_ice_sublimation_dn
    extinctions=pr87_ice_sublimation_extinctions
  end subroutine apply_endpoint
end program test_v39_ice_cap_order
"""


if __name__ == "__main__":
    test_pr87_ice_sublimation_source_contract()
    test_pr87_ice_sublimation_fraction_and_pair_validation()
    print("PR87 ice sublimation tests PASS")
