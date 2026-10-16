"""Pinned Intel consumer regression for the Shinhong source correction."""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tests")]

from pr87_pbl_source_payload import _append_call_args, _instrument_fragment  # noqa: E402
from pr87_source_first_fallback_regression import (  # noqa: E402
    KERNEL,
    PROFILE,
    DENSITY_HELPER,
    assert_fallback_ledger,
    extract_subroutine,
    profile_flags,
    run,
    source_text,
)
from test_pr87_cloud_diffusion_consumer import (  # noqa: E402
    _cloud_rk_rows,
    _fixture_source,
    _real32,
    _ulp32,
)


def _pbl_fixture() -> str:
    source = _instrument_fragment(_fixture_source())
    source = source.replace("IF (mode==20) THEN\n      cloud_rain_diffusion_delta", 
                            "IF (mode==20.OR.mode==24) THEN\n      cloud_rain_diffusion_delta", 1)
    source = source.replace("IF (mode==14.OR.mode==20) THEN\n", 
                            "IF (mode==14.OR.mode==20.OR.mode==24.OR.mode==25) THEN\n", 1)
    source = source.replace("IF (mode>=14) THEN\n", 
                            "IF (mode==14.OR.mode==20.OR.mode==24.OR.mode==25) THEN\n", 1)
    source = source.replace("IF (mode==14.OR.mode==20) THEN\n", 
                            "IF (mode==14.OR.mode==20.OR.mode==24.OR.mode==25) THEN\n", 1)
    source = source.replace(
        "  REAL(real64) :: cloud_rain_diffusion_delta(ims:ime,kms:kme,jms:jme,4)\n",
        "  REAL(real64) :: cloud_rain_diffusion_delta(ims:ime,kms:kme,jms:jme,4)\n"
        "  REAL(real64) :: pr87_pbl_tendency_delta64(ims:ime,kms:kme,jms:jme,4)\n"
        "  INTEGER :: pbl_step,pbl_phase\n",
        1,
    )
    source = source.replace(
        "  cloud_rain_diffusion_delta=0.0_real64\n",
        "  cloud_rain_diffusion_delta=0.0_real64\n"
        "  pr87_pbl_tendency_delta64=0.0_real64\n"
        "  pbl_step=1; pbl_phase=1\n",
        1,
    )
    source = source.replace(
        "  CASE('cloud_rk_cadence'); mode=20\n",
        "  CASE('cloud_rk_cadence'); mode=20\n"
        "  CASE('pbl_source_first'); mode=21\n"
        "  CASE('pbl_stale_epoch'); mode=22\n"
        "  CASE('pbl_nonfinite'); mode=23\n"
        "  CASE('pbl_source_terms'); mode=24\n"
        "  CASE('pbl_source_control'); mode=25\n",
        1,
    )
    source = source.replace(
        "IF (mode==1.OR.mode==2.OR.(mode>=7.AND.mode<=12)) THEN",
        "IF (mode==1.OR.mode==2.OR.mode==21.OR.(mode>=7.AND.mode<=12)) THEN",
    )
    source = source.replace(
        "IF ((mode==1.OR.mode==2.OR.(mode>=7.AND.mode<=12)).AND.i==3) &",
        "IF ((mode==1.OR.mode==2.OR.mode==21.OR.(mode>=7.AND.mode<=12)).AND.i==3) &",
    )
    source = source.replace(
        "IF (mode==2.OR.(mode>=7.AND.mode/=10.AND.mode/=12)) THEN",
        "IF (mode==2.OR.mode==21.OR.(mode>=7.AND.mode/=10.AND.mode/=12)) THEN",
    )
    setup_anchor = "  IF (mode==8) source_carrier(2,1,2)=2.0_real32\n"
    setup = (
        "  IF (mode==20.OR.mode==24) THEN\n"
        "    source_carrier=REAL(94642.36_real64,real32)\n"
        "    raw_qsrc(:,:,:,1)=1.0e-12_real32; raw_nsrc(:,:,:,1)=0.5_real32\n"
        "    later_qsrc(:,:,:,1)=3.0e-8_real64; later_nsrc(:,:,:,1)=3.0e-2_real64\n"
        "    IF (mode==20) THEN\n"
        "      pr87_pbl_tendency_delta64(:,:,:,1)=2.0e-12_real64\n"
        "      pr87_pbl_tendency_delta64(:,:,:,2)=1.25_real64\n"
        "    END IF\n"
        "  ELSE IF (mode==25) THEN\n"
        "    source_carrier=REAL(94642.36_real64,real32)\n"
        "    raw_qsrc(:,:,:,1)=0.0_real32; raw_nsrc(:,:,:,1)=0.0_real32\n"
        "    later_qsrc(:,:,:,1)=0.0_real64; later_nsrc(:,:,:,1)=0.0_real64\n"
        "  ELSE IF (mode==21) THEN\n"
        "    pr87_pbl_tendency_delta64(2,1,2,1)=0.125_real64*min_cloud*1.0e8_real64\n"
        "    pr87_pbl_tendency_delta64(3,1,2,1)=0.125_real64*min_cloud*1.0e8_real64\n"
        "  ELSE IF (mode==22) THEN\n"
        "    pbl_step=2\n"
        "  ELSE IF (mode==23) THEN\n"
        "    pr87_pbl_tendency_delta64(2,1,2,1)=ieee_value(0.0_real64,ieee_quiet_nan)\n"
        "  END IF\n"
    )
    if source.count(setup_anchor) != 1:
        raise AssertionError("missing PBL mode setup anchor")
    source = source.replace(setup_anchor, setup + setup_anchor, 1)
    # Make the source-first PBL case use the same exact two-cell dyadic source
    # fixture as the existing strict fallback test.
    source = source.replace(
        "  IF (mode==2.OR.mode==21.OR.(mode>=7.AND.mode/=10.AND.mode/=12)) THEN\n"
        "    qt(2,1,2,qindex(1))=REAL(0.125_real64*min_cloud*1.0e8_real64,real32)\n",
        "  IF (mode==2.OR.mode==21.OR.(mode>=7.AND.mode/=10.AND.mode/=12)) THEN\n"
        "    qt(2,1,2,qindex(1))=REAL(0.125_real64*min_cloud*1.0e8_real64,real32)\n",
        1,
    )
    # Pass the source correction explicitly to every native invocation in the
    # test driver, including its internal RK wrappers.
    starts = [m.start() for m in re.finditer(r"CALL\s+rk_update_joint_moments", source, re.I)]
    if not starts:
        raise AssertionError("fixture contains no native consumer call")
    for start in reversed(starts):
        suffix = source[start:]
        suffix = _append_call_args(
            suffix,
            "rk_update_joint_moments",
            "pr87_pbl_tendency_delta64=pr87_pbl_tendency_delta64, "
            "pr87_pbl_tendency_step=pbl_step, pr87_pbl_tendency_phase=pbl_phase",
        )
        source = source[:start] + suffix
    # The pbl source-first endpoint includes the accepted paired source delta
    # before conservative transport; strict storage validation stays in the
    # extracted native routine.
    endpoint_anchor = "    expected_q=REAL(1.09375_real64*min_cloud*1.0e8_real64,real32)\n"
    pbl_endpoint = (
        "    IF (mode==21) THEN\n"
        "      expected_q=REAL(1.1875_real64*min_cloud*1.0e8_real64,real32)\n"
        "      CALL assert_near(q2_state(2,1,2,qindex(1)),expected_q,'PBL source-first left endpoint')\n"
        "      expected_q=REAL(1.15625_real64*min_cloud*1.0e8_real64,real32)\n"
        "      CALL assert_near(q2_state(3,1,2,qindex(1)),expected_q,'PBL source-first right endpoint')\n"
        "      WRITE(*,'(a)') 'PR87_PBL_CONSUMER_PASS source_first'\n"
        "      STOP\n"
        "    END IF\n"
    )
    if source.count(endpoint_anchor) != 1:
        raise AssertionError("missing source-first endpoint anchor")
    source = source.replace(endpoint_anchor, pbl_endpoint + endpoint_anchor, 1)
    return source


def _compile(source: str, scratch: Path) -> dict[str, Path]:
    src = scratch / "pbl_consumer.F90"
    src.write_text(source, encoding="utf-8")
    executables: dict[str, Path] = {}
    for opt, profile in (("O0", "CLOUD_BAL_FREE_FLAGS"), ("O2", "CLOUD_BAL_REPRO_FLAGS")):
        compiler, flags = profile_flags(profile)
        build = scratch / opt
        build.mkdir()
        exe = build / "pbl_consumer.exe"
        result = run([compiler, *flags, str(KERNEL), str(src), "-o", str(exe)], build, build / "compile.log")
        if result.returncode:
            raise AssertionError(f"pinned Intel {opt} compile failed:\n{result.stdout}")
        executables[opt] = exe
    return executables


def _execute(exe: Path, mode: str, cwd: Path) -> str:
    cwd.mkdir()
    result = run([str(exe), mode], cwd, cwd / "run.log")
    if result.returncode:
        raise AssertionError(f"{mode} failed:\n{result.stdout}")
    return result.stdout


def _rejected(exe: Path, mode: str, reason: str, cwd: Path) -> None:
    cwd.mkdir()
    result = run([str(exe), mode], cwd, cwd / "run.log")
    if result.returncode == 0 or reason not in result.stdout:
        raise AssertionError(f"{mode} did not reject for {reason}:\n{result.stdout}")
    line = next((row for row in result.stdout.splitlines() if "PR87_FATAL_ATOMIC_STATE" in row), None)
    if line is None:
        raise AssertionError(f"{mode} omitted precommit state receipt:\n{result.stdout}")
    values = [float(value) for value in line.split()[1:]]
    initial_q = _real32(1.5 * 4.188790204786391e-15 * 1.0e8)
    if len(values) != 4 or values != [initial_q, initial_q, 1.0e8, 1.0e8]:
        raise AssertionError(f"{mode} mutated public state before rejection: {values}")
    if (cwd / "pr87_pbl_source_correction.raw").exists():
        raise AssertionError(f"{mode} emitted source-correction record before validation")


def test_pbl_payload_reaches_real_consumer_o0_o2() -> None:
    procedure = _instrument_fragment(_fixture_source())
    # Bind the test to the transformed native routine rather than a retyped
    # equation. The harness only supplies controlled source/delta arrays.
    native = extract_subroutine(procedure, "rk_update_joint_moments")
    density = extract_subroutine(DENSITY_HELPER.read_text(), "pr85_dry_density_from_al_alb")
    source = source_text(native, density)
    fixture = _pbl_fixture()
    # Keep the source-extracted routine identity explicit in the source that is
    # compiled by checking both helper compositions have the same payload API.
    assert "pr87_pbl_tendency_delta64" in fixture
    assert "pr87_pbl_tendency_delta64" in source

    with tempfile.TemporaryDirectory(prefix="pr87-pbl-consumer-", dir="/var/tmp") as tmp:
        scratch = Path(tmp)
        # _pbl_fixture carries the native procedure plus the existing complete
        # test driver; compile it directly so array setup and endpoint checks
        # exercise actual consumer code.
        executables = _compile(fixture, scratch)
        for opt, exe in executables.items():
            normal_dir = scratch / f"{opt}_combined_sources"
            output = _execute(exe, "cloud_rk_cadence", normal_dir)
            assert "PR87_CLOUD_RK_OUTPUT" in output
            rows = _cloud_rk_rows(output)
            ledger = (normal_dir / "pr87_pbl_source_correction.raw").read_text()
            ledger_rows = [line for line in ledger.splitlines() if "PR87_PBL_SOURCE_CORRECTION_RK" in line]
            assert len(ledger_rows) == 3
            for line in ledger_rows:
                tokens = line.split()
                values = [float(token) for token in tokens[1:]]
                assert len(values) == 19, line
                assert values[3] == 1.0 and values[4] > 0.0
                assert values[7] > 0.0 and values[8] > 0.0

            terms_dir = scratch / f"{opt}_source_terms"
            terms = _execute(exe, "pbl_source_terms", terms_dir)
            terms_rows = _cloud_rk_rows(terms)
            control_dir = scratch / f"{opt}_source_control"
            control = _execute(exe, "pbl_source_control", control_dir)
            control_rows = _cloud_rk_rows(control)
            carrier = _real32(94642.36)
            new_mu = _real32(_real32(94640.8) - _real32(94642.36))
            new_carrier = _real32(new_mu + _real32(94642.36))
            stage_dt = {1: _real32(20.0 / 3.0), 2: 10.0, 3: 20.0}
            source_q = carrier * 1.0e-12 + 3.0e-8 + 1.0e-7
            source_n = carrier * 0.5 + 3.0e-2 + 2.3841858e7
            pbl_q = carrier * 2.0e-12
            pbl_n = carrier * 1.25
            for rk in (1, 2, 3):
                for offset, rate, label in ((0, source_q, "Q source"), (1, source_n, "N source")):
                    for cell in range(2):
                        delta = terms_rows[rk][2 * cell + offset] - control_rows[rk][2 * cell + offset]
                        tol = 2.0 * max(_ulp32(rows[rk][2 * cell + offset]),
                                        _ulp32(control_rows[rk][2 * cell + offset]))
                        expected = stage_dt[rk] * rate / new_carrier
                        if abs(delta - expected) > tol:
                            raise AssertionError(
                                f"RK{rk} weighted raw+later+horizontal {label} mismatch: "
                                f"delta={delta} expected={expected} tolerance={tol}"
                            )
                for offset, rate, label in ((0, pbl_q, "Q PBL"), (1, pbl_n, "N PBL")):
                    for cell in range(2):
                        delta = rows[rk][2 * cell + offset] - terms_rows[rk][2 * cell + offset]
                        tol = 2.0 * max(_ulp32(rows[rk][2 * cell + offset]),
                                        _ulp32(terms_rows[rk][2 * cell + offset]))
                        expected = stage_dt[rk] * rate / new_carrier
                        if abs(delta - expected) > tol:
                            raise AssertionError(
                                f"RK{rk} PBL {label} correction omitted/repeated: "
                                f"delta={delta} expected={expected} tolerance={tol}"
                            )

            fallback_dir = scratch / f"{opt}_pbl_source_first"
            fallback = _execute(exe, "pbl_source_first", fallback_dir)
            assert "PR87_PBL_CONSUMER_PASS source_first" in fallback
            assert_fallback_ledger(fallback_dir / "pr85_joint_transport_budget.raw")
            _rejected(exe, "pbl_stale_epoch", "PR87 PBL/source payload epoch mismatch",
                      scratch / f"{opt}_stale")
            _rejected(exe, "pbl_nonfinite", "PR87 nonfinite PBL tendency correction",
                      scratch / f"{opt}_nonfinite")
