"""Pinned native consumer checks for the four-channel cloud/rain payload."""
from __future__ import annotations

import gzip
import hashlib
import struct
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from pr87_cloud_diffusion_precision import extend_cloud_diffusion_precision  # noqa: E402
from pr87_source_first_fallback_regression import (  # noqa: E402
    DENSITY_HELPER,
    KERNEL,
    PROFILE,
    assert_fallback_ledger,
    extract_subroutine,
    profile_flags,
    run,
    source_text,
)


FIXTURE_DIR = ROOT / "tests/fixtures/pr87_cloud_diffusion_v24g_pre2"
FIXTURE_SHA256 = {
    "module_em_pr85.F.gz": "1a716f5bd90b6673130832198592ecb006ab4f25d746c207b65a0f4ebd826712",
    "solve_em.F.gz": "b333a16fef56f669bfb88267a97999281d41a981e50a2c88e44b26cd481fd7d4",
    "native_update.f90.gz": "912acc254708b8ab0a38f13e0b41fdafbf22f9f2f4f4d1684e6d1f475e9baab3",
}
TRANSFORMED_FRAGMENT_SHA256 = "da168838410ac7b90de0918b5c340ea0e2017e232c409964f12dc8abed61e296"


def _read_fixture(name: str) -> str:
    payload = gzip.decompress((FIXTURE_DIR / name).read_bytes())
    if hashlib.sha256(payload).hexdigest() != FIXTURE_SHA256[name]:
        raise AssertionError(f"committed source fixture changed: {name}")
    return payload.decode()


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise AssertionError(f"expected unique {label} anchor")
    return text.replace(old, new, 1)


def _real32(value: float) -> float:
    return struct.unpack("=f", struct.pack("=f", value))[0]


def _ulp32(value: float) -> float:
    bits = struct.unpack("=I", struct.pack("=f", _real32(value)))[0]
    return struct.unpack("=f", struct.pack("=I", bits + 1))[0] - _real32(value)


def _cloud_rk_rows(output: str) -> dict[int, list[float]]:
    rows: dict[int, list[float]] = {}
    for line in output.splitlines():
        if "PR87_CLOUD_RK_OUTPUT" not in line:
            continue
        fields = line.split()
        if len(fields) != 6:
            raise AssertionError(f"malformed cloud RK endpoint row: {line}")
        rk = int(fields[1])
        if rk in rows:
            raise AssertionError(f"duplicate cloud RK endpoint row: {rk}")
        rows[rk] = [float(value) for value in fields[2:]]
    if set(rows) != {1, 2, 3}:
        raise AssertionError(f"missing cloud RK endpoint rows: {sorted(rows)}")
    return rows


def _fixture_source() -> str:
    transformed = extend_cloud_diffusion_precision({
        "em": _read_fixture("module_em_pr85.F.gz"),
        "solve": _read_fixture("solve_em.F.gz"),
        "fragment": _read_fixture("native_update.f90.gz"),
    })
    procedure = extract_subroutine(transformed["fragment"], "rk_update_joint_moments")
    if hashlib.sha256(transformed["fragment"].encode()).hexdigest() != TRANSFORMED_FRAGMENT_SHA256:
        raise AssertionError("cloud diffusion transform output changed")
    observer = DENSITY_HELPER.read_text(encoding="utf-8")
    density = extract_subroutine(observer, "pr85_dry_density_from_al_alb")
    fixture = source_text(procedure, density)
    fixture = re.sub(r"(?<!cloud_)rain_diffusion_delta", "cloud_rain_diffusion_delta", fixture)
    fixture = re.sub(r"(?<!cloud_)rain_diffusion_step", "cloud_rain_diffusion_step", fixture)
    fixture = _replace_once(
        fixture,
        "cloud_rain_diffusion_delta(ims:ime,kms:kme,jms:jme,2)",
        "cloud_rain_diffusion_delta(ims:ime,kms:kme,jms:jme,4)",
        "four-channel consumer fixture payload",
    )

    setup = (
        "  IF (mode==10.OR.mode==12) THEN\n"
        "    later_qsrc(:,:,:,1)=0.000009236385_real64\n"
        "    later_nsrc(:,:,:,1)=9236.385_real64\n"
        "  END IF\n"
    )
    fixture = _replace_once(
        fixture,
        setup,
        "  IF (mode==2) THEN\n"
        "    later_qsrc(:,:,:,1)=2.0e-14_real64\n"
        "    later_nsrc(:,:,:,1)=4.0_real64\n"
        "    cloud_rain_diffusion_delta(:,:,:,1)=4.188790204786391e-14_real64\n"
        "    cloud_rain_diffusion_delta(:,:,:,2)=10.0_real64\n"
        "  ELSE IF (mode==10.OR.mode==12) THEN\n"
        "    later_qsrc(:,:,:,1)=0.000009236385_real64\n"
        "    later_nsrc(:,:,:,1)=9236.385_real64\n"
        "  END IF\n",
        "source-first cloud payload setup",
    )
    fixture = _replace_once(
        fixture,
        "  CASE('rain_diffusion_precision'); mode=14\n",
        "  CASE('rain_diffusion_precision'); mode=14\n"
        "  CASE('cloud_rk_cadence'); mode=20\n",
        "cloud RK cadence mode",
    )

    source_first_anchor = (
        "  ELSE IF (mode==7) THEN\n"
        "    CALL rk_update_joint_moments(q1,q2_state,n1,n2_state,qt,nt,nmoist,nscalar,qindex,nindex,6,5, &\n"
    )
    if fixture.count(source_first_anchor) != 1:
        raise AssertionError("missing unique source-first call split")
    fixture = fixture.replace(
        source_first_anchor,
        "  ELSE IF (mode==2) THEN\n"
        "    CALL rk_update_joint_moments(q1,q2_state,n1,n2_state,qt,nt,nmoist,nscalar,qindex,nindex,6,5, &\n"
        "         ru,rv,ww,muold,munew,mub,c1,c2,msftx,msfty,1.0_real32,1.0_real32,-1.0_real32, &\n"
        "         al,alb,dt,3,1,1,ids,ide,jds,jde,kds,kde,ims,ime,jms,jme,kms,kme, &\n"
        "         its,ite,jts,jte,kts,kte,raw_qsrc,raw_nsrc,coupled_qsrc,coupled_nsrc,source_carrier,1, &\n"
        "         later_qsrc,later_nsrc, &\n"
        "         pr87_cloud_rain_diffusion_delta=cloud_rain_diffusion_delta, &\n"
        "         pr87_cloud_rain_diffusion_step=1)\n"
        + source_first_anchor,
        1,
    )

    q_left = "    expected_q=REAL(1.09375_real64*min_cloud*1.0e8_real64,real32)\n"
    q_right = (
        "    expected_q=REAL(1.03125_real64*min_cloud*1.0e8_real64,real32)\n"
        "    CALL assert_near(q2_state(3,1,2,qindex(1)),expected_q,'source-first right cloud result')\n"
    )
    fixture = _replace_once(
        fixture,
        q_left,
        q_left +
        "    expected_q=REAL(REAL(expected_q,real64)+REAL(dt,real64)* &\n"
        "         (later_qsrc(2,1,2,1)+cloud_rain_diffusion_delta(2,1,2,1))/ &\n"
        "         REAL(source_carrier(2,1,2),real64),real32)\n",
        "source-first cloud left result",
    )
    fixture = _replace_once(
        fixture,
        q_right,
        "    expected_q=REAL(1.03125_real64*min_cloud*1.0e8_real64,real32)\n"
        "    expected_q=REAL(REAL(expected_q,real64)+REAL(dt,real64)* &\n"
        "         (later_qsrc(3,1,2,1)+cloud_rain_diffusion_delta(3,1,2,1))/ &\n"
        "         REAL(source_carrier(3,1,2),real64),real32)\n"
        "    CALL assert_near(q2_state(3,1,2,qindex(1)),expected_q,'source-first right cloud result')\n",
        "source-first cloud right result",
    )
    n_left = "    CALL assert_near(n2_state(2,1,2,nindex(1)),1.0e8_real32,'source-first left number result')\n"
    n_right = "    CALL assert_near(n2_state(3,1,2,nindex(1)),1.0e8_real32,'source-first right number result')\n"
    for old, idx, label in ((n_left, 2, "left"), (n_right, 3, "right")):
        new = (
            f"    expected_n=REAL(1.0e8_real64+REAL(dt,real64)* &\n"
            f"         (later_nsrc({idx},1,2,1)+cloud_rain_diffusion_delta({idx},1,2,2))/ &\n"
            f"         REAL(source_carrier({idx},1,2),real64),real32)\n"
            f"    CALL assert_near(n2_state({idx},1,2,nindex(1)),expected_n, &\n"
            f"                     'source-first {label} number with cloud correction')\n"
        )
        fixture = _replace_once(fixture, old, new, f"source-first cloud {label} number")
    sum_anchor = "    expected_q=REAL(2.125_real64*min_cloud*1.0e8_real64,real32)\n"
    fixture = _replace_once(
        fixture,
        sum_anchor,
        sum_anchor +
        "    expected_q=REAL(REAL(expected_q,real64)+REAL(dt,real64)* &\n"
        "         ((later_qsrc(2,1,2,1)+cloud_rain_diffusion_delta(2,1,2,1))/ &\n"
        "          REAL(source_carrier(2,1,2),real64)+(later_qsrc(3,1,2,1)+ &\n"
        "          cloud_rain_diffusion_delta(3,1,2,1))/REAL(source_carrier(3,1,2),real64)),real32)\n",
        "source-first cloud signed pair budget",
    )

    rain_setup_old = (
        "    cloud_rain_diffusion_delta(:,:,:,1)=rain_delta_q\n"
        "    cloud_rain_diffusion_delta(:,:,:,2)=rain_delta_n\n"
    )
    fixture = _replace_once(
        fixture,
        rain_setup_old,
        "    IF (mode==20) THEN\n"
        "      cloud_rain_diffusion_delta(:,:,:,1)=1.0e-7_real64\n"
        "      cloud_rain_diffusion_delta(:,:,:,2)=2.3841858e7_real64\n"
        "    END IF\n"
        "    cloud_rain_diffusion_delta(:,:,:,3)=rain_delta_q\n"
        "    cloud_rain_diffusion_delta(:,:,:,4)=rain_delta_n\n",
        "cloud/rain channels in four-channel payload",
    )
    fixture = _replace_once(
        fixture,
        "  IF (mode==14) THEN\n",
        "  IF (mode==14.OR.mode==20) THEN\n",
        "cloud and rain RK cadence body",
    )
    for rk in (1, 2, 3):
        anchor = f"    CALL assert_rain_diffusion_stage(dt,'RK{rk}')\n"
        fixture = _replace_once(
            fixture,
            anchor,
            anchor +
            f"    WRITE(*,'(A,1X,I0,4(1X,ES24.16))') 'PR87_CLOUD_RK_OUTPUT',{rk}, &\n"
            "      q2_state(2,1,2,qindex(1)),n2_state(2,1,2,nindex(1)), &\n"
            "      q2_state(3,1,2,qindex(1)),n2_state(3,1,2,nindex(1))\n",
            f"p1 RK{rk} endpoint report",
        )
    fixture = _replace_once(
        fixture,
        "    WRITE(*,'(a)') 'PR87_SOURCE_FIRST_FIXTURE_PASS rain_diffusion_precision'\n",
        "    IF (mode==14) THEN\n"
        "      WRITE(*,'(a)') 'PR87_SOURCE_FIRST_FIXTURE_PASS rain_diffusion_precision'\n"
        "    ELSE\n"
        "      WRITE(*,'(a)') 'PR87_SOURCE_FIRST_FIXTURE_PASS cloud_rk_cadence'\n"
        "    END IF\n",
        "cloud RK cadence pass marker",
    )
    fixture = _replace_once(
        fixture,
        "IF (mode==18) cloud_rain_diffusion_delta(2,1,2,1)=ieee_value",
        "IF (mode==18) cloud_rain_diffusion_delta(2,1,2,3)=ieee_value",
        "rain nonfinite payload channel",
    )
    return fixture


def _assert_guard_rejected(executable: Path, mode: str, expected_reason: str, cwd: Path) -> None:
    result = run([str(executable), mode], cwd, cwd / "run.log")
    if result.returncode == 0:
        raise AssertionError(f"{mode} unexpectedly accepted the diffusion payload")
    if expected_reason not in result.stdout or "PR87_FATAL_ATOMIC_STATE" not in result.stdout:
        raise AssertionError(f"{mode} did not reject atomically for {expected_reason}:\n{result.stdout}")
    values_line = next(line for line in result.stdout.splitlines()
                       if "PR87_FATAL_ATOMIC_STATE" in line)
    values = [float(value) for value in values_line.split()[1:]]
    initial_q = _real32(1.5 * 4.188790204786391e-15 * 1.0e8)
    initial_n = _real32(1.0e8)
    expected = [initial_q, initial_q, initial_n, initial_n]
    if len(values) != 4 or any(actual != target for actual, target in zip(values, expected, strict=True)):
        raise AssertionError(f"{mode} changed public Q/N before rejecting: {values}")
    if any((cwd / name).exists() for name in (
            "pr85_joint_transport_budget.raw", "pr87_joint_storage.raw", "pr87_qn_diffusion_precision.raw")):
        raise AssertionError(f"{mode} emitted post-guard ledgers")


def _run_four_channel_cloud_payload_regression(tmp_path: Path) -> None:
    fixture = _fixture_source()
    source = tmp_path / "cloud_diffusion_consumer.F90"
    source.write_text(fixture, encoding="utf-8")
    for level, profile_flag in (("O0", "CLOUD_BAL_FREE_FLAGS"),
                                ("O2", "CLOUD_BAL_REPRO_FLAGS")):
        compiler, flags = profile_flags(profile_flag)
        build = tmp_path / level
        build.mkdir()
        executable = build / "cloud_diffusion_consumer.exe"
        compile_result = run([compiler, *flags, str(KERNEL), str(source), "-o", str(executable)],
                             build, build / "compile.log")
        if compile_result.returncode:
            raise AssertionError(f"{level} pinned Intel compile failed:\n{compile_result.stdout}")

        cadence_dir = build / "later_cadence"
        cadence_dir.mkdir()
        cadence = run([str(executable), "source_first"], cadence_dir, cadence_dir / "run.log")
        if cadence.returncode or "PR87_SOURCE_FIRST_FIXTURE_PASS source_first" not in cadence.stdout:
            raise AssertionError(f"{level} cloud source-first fallback failed:\n{cadence.stdout}")
        assert_fallback_ledger(cadence_dir / "pr85_joint_transport_budget.raw")

        rain_dir = build / "rain_diffusion_precision"
        rain_dir.mkdir()
        rain = run([str(executable), "rain_diffusion_precision"], rain_dir, rain_dir / "run.log")
        if rain.returncode or "PR87_SOURCE_FIRST_FIXTURE_PASS rain_diffusion_precision" not in rain.stdout:
            raise AssertionError(f"{level} p3 rain channel 3/4 control failed:\n{rain.stdout}")
        cloud_dir = build / "cloud_rk_cadence"
        cloud_dir.mkdir()
        cloud = run([str(executable), "cloud_rk_cadence"], cloud_dir, cloud_dir / "run.log")
        if cloud.returncode or "PR87_SOURCE_FIRST_FIXTURE_PASS cloud_rk_cadence" not in cloud.stdout:
            raise AssertionError(f"{level} p1 cloud channel 1/2 RK cadence failed:\n{cloud.stdout}")
        baseline_rows = _cloud_rk_rows(rain.stdout)
        cloud_rows = _cloud_rk_rows(cloud.stdout)
        mub = _real32(94642.36)
        new_mu = _real32(_real32(94640.8) - mub)
        new_carrier = _real32(new_mu + mub)
        stage_dt = {1: _real32(20.0 / 3.0), 2: 10.0, 3: 20.0}
        for rk in (1, 2, 3):
            q_effect = stage_dt[rk] * 1.0e-7 / new_carrier
            n_effect = stage_dt[rk] * 2.3841858e7 / new_carrier
            for offset, effect, label in ((0, q_effect, "Q"), (1, n_effect, "N")):
                for cell in range(2):
                    baseline = baseline_rows[rk][2 * cell + offset]
                    corrected = cloud_rows[rk][2 * cell + offset]
                    difference = corrected - baseline
                    rounding = 2.0 * max(_ulp32(baseline), _ulp32(corrected))
                    if difference <= 0.0 or abs(difference - effect) > rounding:
                        raise AssertionError(
                            f"RK{rk} cloud {label} correction was omitted/repeated: "
                            f"observed={difference} expected={effect} tolerance={rounding}"
                        )

        guards = (
            ("stale_diffusion_step", "PR87 rain diffusion timestep mismatch"),
            ("partial_diffusion_delta", "PR87 rain diffusion delta/step must be supplied together"),
            ("partial_diffusion_step", "PR87 rain diffusion delta/step must be supplied together"),
            ("nonfinite_diffusion_delta", "PR87 nonfinite cloud/rain diffusion correction"),
        )
        for mode, reason in guards:
            cwd = build / mode
            cwd.mkdir()
            _assert_guard_rejected(executable, mode, reason, cwd)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="pr87_cloud_diffusion_consumer_", dir="/var/tmp") as scratch:
        _run_four_channel_cloud_payload_regression(Path(scratch))
    print("PR87 four-channel cloud diffusion consumer O0/O2 PASS")


def test_four_channel_cloud_payload_reaches_source_first_consumer() -> None:
    with tempfile.TemporaryDirectory(prefix="pr87_cloud_diffusion_consumer_", dir="/var/tmp") as scratch:
        _run_four_channel_cloud_payload_regression(Path(scratch))
