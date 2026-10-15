#!/usr/bin/env python3
"""Pinned-Intel source-form regression for the KDM6 warm paired transaction."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import struct

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/pr85_kdm6_warm_process_source.F90"
RECEIPT_DEFAULT = ROOT / "tests/fixtures/pr85_kdm6_warm_capture_v20j_receipt.json"
SOURCE_CONTRACT = ROOT / "tests/fixtures/pr85_kdm6_cold_warm_source_contract.json"
PATCH = ROOT / "patches/pr85_kdm6_ice_sedimentation.patch"
RECEIPT_SHA256 = "e6e9201881479ca2e77ac4f102e123d2537ae78de3ffe4c1807c02e4d7e3af5a"
PROCEDURES = ("kdm6_rain_process_fraction", "kdm6_rain_process_state_valid")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def procedure(source: str, name: str) -> str:
    lines = source.splitlines()
    start = next(
        (i for i, line in enumerate(lines)
         if re.match(rf"\s*subroutine\s+{name}\s*\(", line, re.I)),
        None,
    )
    assert start is not None, f"missing {name} procedure"
    end = next(
        (i for i in range(start + 1, len(lines))
         if re.match(rf"\s*end\s+subroutine\s+{name}\s*$", lines[i], re.I)),
        None,
    )
    assert end is not None, f"missing end of {name} procedure"
    return "\n".join(lines[start:end + 1])


def source_contract(source: str) -> None:
    uncommented = re.sub(r"!.*$", "", source, flags=re.MULTILINE)
    compact = re.sub(r"[\s&]+", "", uncommented).lower()
    expected = (
        "rain_warm_rate_base=[praut(i,k),pracw(i,k),paacw(i,k),nraut(i,k),"
        "nccol(i,k),nracw(i,k),naacw(i,k),prevp(i,k),pseml(i,k),"
        "pgeml(i,k),psevp(i,k),pgacs(i,k),pgevp(i,k),nrcol(i,k),"
        "nseml(i,k),ngeml(i,k)]",
        "rain_warm_q_process(1)=-(rain_warm_rate_base(1)+rain_warm_rate_base(2)"
        "+rain_warm_rate_base(3)+rain_warm_rate_base(3))*dtcld",
        "rain_warm_q_process(3)=(rain_warm_rate_base(1)+rain_warm_rate_base(2)"
        "+rain_warm_rate_base(8)+rain_warm_rate_base(3)+rain_warm_rate_base(3)"
        "-rain_warm_rate_base(9)-rain_warm_rate_base(10))*dtcld",
        "rain_warm_q_process(4)=(rain_warm_rate_base(11)-rain_warm_rate_base(12)"
        "+rain_warm_rate_base(9))*dtcld",
        "rain_warm_q_process(5)=(rain_warm_rate_base(12)+rain_warm_rate_base(13)"
        "+rain_warm_rate_base(10))*dtcld",
        "rain_warm_n_process(1)=-(rain_warm_rate_base(4)+rain_warm_rate_base(5)"
        "+rain_warm_rate_base(6)+rain_warm_rate_base(7)+rain_warm_rate_base(7))*dtcld",
        "rain_warm_n_process(3)=(rain_warm_rate_base(4)-rain_warm_rate_base(14)"
        "+rain_warm_rate_base(15)+rain_warm_rate_base(16))*dtcld",
        "rain_warm_bg_process=(bgevp(i,k)+bgeml(i,k))*dtcld",
        "rain_warm_xlwork2=-xl(i,k)*(rain_warm_rate_base(8)+rain_warm_rate_base(11)"
        "+rain_warm_rate_base(13))-rain_warm_xlf*(rain_warm_rate_base(9)"
        "+rain_warm_rate_base(10))",
        "rain_warm_qv_process=work2(i,k)*dtcld",
        "rain_warm_rate_trial=rain_warm_alpha*rain_warm_rate_base",
        "rain_warm_q_after(1)=rain_q_before(1)-(rain_warm_rate_trial(1)"
        "+rain_warm_rate_trial(2)+rain_warm_rate_trial(3)+rain_warm_rate_trial(3))*dtcld",
        "rain_warm_n_after(1)=rain_n_before(1)-(rain_warm_rate_trial(4)"
        "+rain_warm_rate_trial(5)+rain_warm_rate_trial(6)+rain_warm_rate_trial(7)"
        "+rain_warm_rate_trial(7))*dtcld",
        "rain_warm_bg_after=rain_bg_before+(rain_warm_rate_trial(13)/rhox(i,k)"
        "+rain_warm_rate_trial(10)/rhox(i,k))*dtcld",
        "rain_warm_t_after=rain_t_before-rain_warm_xlwork2/cpm(i,k)*dtcld",
        "rain_warm_qv_after=rain_qv_before+work2(i,k)*dtcld",
        "'retry0=fullhelperfraction,1-32=adjacentreal32stepsdownward,33-56=halving;'",
        "dorain_warm_retry=0,56",
        "if(rain_warm_retry.gt.0)thenif(rain_warm_retry.le.32)then"
        "rain_warm_alpha=nearest(rain_warm_alpha,-1.0)"
        "elserain_warm_alpha=0.5*rain_warm_alphaendifendif",
        "consumer_pair_only=.true.",
        "if(pgacs(i,k).ne.0.0)errorstop'kdm6unsupportedwarmgraupelsourcewithoutvolumepartner'",
        "if(progb_status(i,k)==progb_psd_active)thenrain_warm_bg_after=",
        "elserain_warm_bg_after=rain_bg_beforeendif",
        "write(pr85_warm_unit,'(a,7i8,1x,2l1,1p,*(1x,e24.16))'",
        "if(pr85_warm_ios.ne.0)errorstop'pr85warmbudgetwritefailed'",
        "if(rain_warm_abort)errorstop'kdm6warmnativeendpointsearchfailed'",
    )
    for fragment in expected:
        if fragment not in compact:
            raise AssertionError(f"warm source contract missing: {fragment}")

    # The cold NG/AUT/G call sites continue using the default full-PSD mode.
    calls = list(re.finditer(r"call\s+kdm6_rain_process_fraction\s*\(", uncommented, re.I))
    assert len(calls) >= 4, "expected three cold and one warm process-fraction call"
    cold_calls = [uncommented[m.start():uncommented.find(")", m.start()) + 1]
                  for m in calls[:3]]
    assert all("consumer_pair_only" not in call.lower() for call in cold_calls), (
        "warm consumer pair-only option leaked into a cold call"
    )
    warm_call = uncommented[calls[-1].start():uncommented.find("consumer_pair_only=.true.", calls[-1].start())]
    assert "rain_warm_qv_process" in warm_call

    # Validate before any state writes; fatal/invalid paths must not partially commit.
    candidate = compact.index("if(.not.rain_warm_state_valid)then")
    logger = compact.index("write(pr85_warm_unit", candidate)
    abort = compact.index("if(rain_warm_abort)errorstop", logger)
    first_commit = compact.index("praut(i,k)=rain_warm_rate_trial(1)", abort)
    assert candidate < logger < abort < first_commit
    assert compact.index("errorstop'kdm6unsupportedwarmgraupelsourcewithoutvolumepartner'") < compact.index(
        "rain_warm_rate_base=["
    ), "unsupported PGACS must fail before the transaction proposal"


def production_source() -> tuple[str, Path | None, str | None]:
    """Load optional applied source or use the bundled unified patch text."""
    source_path = os.environ.get("PR85_KDM6_APPLIED_SOURCE")
    if source_path:
        source_file = Path(source_path)
        assert source_file.is_file(), f"missing applied KDM6 source: {source_file}"
        return source_file.read_text(), source_file, sha256(source_file)
    lines = []
    for line in PATCH.read_text().splitlines():
        if line.startswith(("+++", "---", "@@")):
            continue
        if line.startswith(("+", " ")):
            lines.append(line[1:])
    return "\n".join(lines), None, None


def test_pr85_kdm6_warm_process() -> None:
    source_text, source_file, source_sha = production_source()
    fixture_text = FIXTURE.read_text()
    contract = json.loads(SOURCE_CONTRACT.read_text())
    assert sha256(PATCH) == contract["patch_sha256"], "source-contract patch identity mismatch"
    constant = re.sub(r"\s+", "", contract["inactive_ice_limit_declaration"]).lower()
    assert constant in re.sub(r"\s+", "", fixture_text).lower(), (
        "warm fixture does not bind the native inactive-ice limit constant"
    )
    assert "pr85_ice_native_inactive_max=nearest(1.e-14,-1.0)" in re.sub(
        r"[\s&]+", "", re.sub(r"!.*$", "", source_text, flags=re.MULTILINE)
    ).lower(), "production patch/source omits the native inactive-ice limit"
    receipt_path = Path(os.environ.get("PR85_KDM6_WARM_RECEIPT", RECEIPT_DEFAULT))
    assert receipt_path.is_file(), f"missing captured warm-cell receipt: {receipt_path}"
    assert sha256(receipt_path) == RECEIPT_SHA256, "warm target receipt hash changed"
    receipt = json.loads(receipt_path.read_text())
    assert receipt["status"] == "DIAGNOSTIC_CAPTURE_RC128"
    assert receipt["target"] == {"i": 132, "lat": 203, "k": 15, "loop": 1,
                                 "stage": "KDM62D_SLOPE_06", "species": "cloud"}
    # Ensure the standalone captured case includes the actual pre-state and
    # post-limiter process rates from the immutable receipt.
    fixture_numbers = {
        struct.unpack("=f", struct.pack("=f", float(token.replace("D", "E").replace("d", "e"))))[0]
        for token in re.findall(r"(?<![A-Za-z_])[+-]?(?:\d+\.?\d*|\.\d+)(?:[EeDd][+-]?\d+)?", fixture_text)
    }
    as_r32 = lambda value: struct.unpack("=f", struct.pack("=f", float(value)))[0]
    captured = receipt["actual_values"]["warm_entry"]
    for key in ("T_K", "XL_Jkg", "CPM_JkgK", "rho_dry_kgm3", "QV", "QC_before",
                "QR_before", "QS_before", "QG_before", "NC_before_m3", "NR_before_m3",
                "BG_before", "qmin", "ncmin", "qcrmin", "dtcld_s"):
        assert as_r32(captured[key]) in fixture_numbers, f"fixture omits captured {key}"
    for key in ("praut", "pracw", "paacw", "nraut", "nccol", "nracw", "naacw", "prevp",
                "pseml", "pgeml", "psevp", "pgacs", "pgevp", "nrcol", "nseml", "ngeml"):
        assert as_r32(receipt["actual_values"]["after_all_limiters_rates"][key]) in fixture_numbers, (
            f"fixture omits captured post-limiter rate {key}"
        )
    for name in PROCEDURES:
        body = procedure(fixture_text, name)
        assert hashlib.sha256(body.encode()).hexdigest() == contract["procedure_sha256"][name], (
            f"fixture {name} differs from verified patch-derived procedure contract"
        )
        if source_file:
            assert body == procedure(source_text, name), (
                f"fixture {name} differs byte-for-byte from optional applied source {source_file}"
            )
    source_contract(source_text)

    scratch = Path(tempfile.mkdtemp(prefix="pr85_kdm6_warm_process_", dir="/var/tmp"))
    for optimization in ("O0", "O2"):
        build = scratch / optimization
        build.mkdir()
        fixture = build / "fixture.F90"
        fixture.write_bytes(FIXTURE.read_bytes())
        command = [
            "bash", "-c",
            'source "$1/tests/intel_toolchain.sh" && '
            'if [[ "$2" == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); '
            'else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi && '
            '"$CLOUD_BAL_FC" "${flags[@]}" -free "$3" -o "$4/test.exe" && '
            '"$4/test.exe"',
            "pr85-kdm6-warm-process-test", str(ROOT), optimization,
            str(fixture), str(build),
        ]
        result = subprocess.run(
            command, cwd=build, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, check=False,
        )
        assert result.returncode == 0, result.stdout
        assert "PR85 KDM6 warm process cases PASS" in result.stdout
        if optimization == "O2":
            assert "#10182" not in result.stdout, result.stdout
        print(f"{optimization}: {result.stdout.strip()}")
    print(f"fixture_sha256={sha256(FIXTURE)}")
    print(f"test_sha256={sha256(Path(__file__))}")
    if source_sha:
        print(f"applied_source_sha256={source_sha}")
    print(f"receipt_sha256={sha256(receipt_path)}")


if __name__ == "__main__":
    test_pr85_kdm6_warm_process()
    print("PR85 KDM6 warm-process test PASS")
