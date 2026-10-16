"""Pinned Intel regression for the final V39 REAL128 diffusion arithmetic."""
from __future__ import annotations

import gzip
import hashlib
import re
import shlex
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "tests/intel_toolchain.sh"
FIXTURE = ROOT / "tests/fixtures/pr87_diffusion_intermediate_v39/module_em_pr85.F.gz"
HELPER = ROOT / "tools/pr87_horizontal_diffusion64.f90"
KERNEL = ROOT / "src/common/cloud_bal_joint_transport.f90"
TEST_SOURCE = ROOT / "tests/test_pr87_diffusion_intermediate_precision.f90"

import sys
sys.path.insert(0, str(ROOT / "tools"))
from pr87_all_pair_diffusion_precision import (  # noqa: E402
    HELPER_SHA256,
    INTERMEDIATE_PRECISION_EM_SHA256,
    widen_horizontal_diffusion_intermediates,
)


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _embedded_module(source: str) -> tuple[int, int, str]:
    start_match = re.search(r"^MODULE pr87_horizontal_diffusion64[ \t]*$", source, re.MULTILINE)
    end_match = re.search(r"^END MODULE pr87_horizontal_diffusion64[ \t]*$", source, re.MULTILINE)
    assert start_match is not None and end_match is not None and end_match.start() > start_match.start()
    end = end_match.end()
    if source[end:end + 2] == "\r\n":
        end += 2
    elif source[end:end + 1] == "\n":
        end += 1
    return start_match.start(), end, source[start_match.start():end]


def _compile_profile(profile_name: str) -> tuple[str, list[str]]:
    assert profile_name in {"CLOUD_BAL_FREE_FLAGS", "CLOUD_BAL_REPRO_FLAGS"}
    source = f"source {shlex.quote(str(PROFILE))}; printf '%s\\n' \"${{{profile_name}[@]}}\""
    flags = subprocess.check_output(["bash", "-lc", source], text=True).splitlines()
    compiler = subprocess.check_output(
        ["bash", "-lc", f"source {shlex.quote(str(PROFILE))}; printf %s \"$CLOUD_BAL_FC\""],
        text=True,
    ).strip()
    return compiler, flags


def _run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, check=False)


def test_transform_is_pinned_and_changes_only_embedded_helper() -> None:
    source = gzip.decompress(FIXTURE.read_bytes()).decode("utf-8")
    assert _sha256_bytes(source.encode()) == INTERMEDIATE_PRECISION_EM_SHA256
    original_helper = HELPER.read_text(encoding="utf-8")
    assert _sha256_bytes(original_helper.encode()) == HELPER_SHA256
    start, end, embedded = _embedded_module(source)
    assert embedded == original_helper

    widened = widen_horizontal_diffusion_intermediates(source)
    _, widened_end, widened_module = _embedded_module(widened)
    assert widened[:start] == source[:start]
    assert widened[widened_end:] == source[end:]
    assert widened_module.count(",real128)") > 20
    assert "REAL(real64),INTENT(OUT) :: increment" in widened_module
    assert "REAL(real128),INTENT(OUT) :: increment" not in widened_module
    assert "REAL(real128) :: increment128" in widened_module
    assert "REAL(real128) :: increment128(" not in widened_module
    assert "increment(i,k,j)=REAL(increment128,real64)" in widened_module
    assert "horizontal_diffusion64(" in widened_module
    assert "increment128= &" in widened_module

    with pytest.raises(ValueError, match="source SHA-256 mismatch"):
        widen_horizontal_diffusion_intermediates(source + "! changed input\n")


def test_pinned_intel_actual_manufactured_and_conservation_cases() -> None:
    source = gzip.decompress(FIXTURE.read_bytes()).decode("utf-8")
    widened = widen_horizontal_diffusion_intermediates(source)
    helper = HELPER.read_text(encoding="utf-8")
    _, _, widened_module = _embedded_module(widened)
    baseline_module = helper.replace(
        "horizontal_diffusion64", "horizontal_diffusion64_baseline")
    assert "MODULE pr87_horizontal_diffusion64_baseline" in baseline_module
    assert "SUBROUTINE horizontal_diffusion64_baseline" in baseline_module

    with tempfile.TemporaryDirectory(prefix="pr87-diffusion-intermediate-", dir="/var/tmp") as tmp:
        scratch = Path(tmp)
        (scratch / "baseline.f90").write_text(baseline_module, encoding="utf-8")
        (scratch / "widened.f90").write_text(widened_module, encoding="utf-8")
        (scratch / "kernel.f90").write_bytes(KERNEL.read_bytes())
        (scratch / "driver.f90").write_bytes(TEST_SOURCE.read_bytes())
        assert _embedded_module(widened)[2] == widened_module
        for level, flag_name in (("O0", "CLOUD_BAL_FREE_FLAGS"),
                                 ("O2", "CLOUD_BAL_REPRO_FLAGS")):
            compiler, flags = _compile_profile(flag_name)
            exe = scratch / f"diffusion_precision_{level}.exe"
            compiled = _run([compiler, *flags, "-free", "baseline.f90", "widened.f90",
                             "kernel.f90", "driver.f90", "-o", str(exe)], scratch)
            assert compiled.returncode == 0, f"Intel {level} compile failed:\n{compiled.stdout}"
            assert "#10182" not in compiled.stdout, compiled.stdout
            runtime = f"source {shlex.quote(str(PROFILE))}; {shlex.quote(str(exe))}"
            executed = _run(["bash", "-lc", runtime], scratch)
            assert executed.returncode == 0, f"Intel {level} runtime failed:\n{executed.stdout}"
            assert "PR87_CAPTURED_CASE_PASS" in executed.stdout
            assert "PR87_WEIGHTED_SUMS" in executed.stdout
            assert "PR87_DIFFUSION_INTERMEDIATE_PRECISION_PASS" in executed.stdout
