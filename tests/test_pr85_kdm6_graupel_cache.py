#!/usr/bin/env python3
"""Source-bound Intel regression for refreshing final graupel PSD cache."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "tests/fixtures/pr85_kdm6_graupel_cache.F90"
NAME = "kdm6_refresh_graupel_intercept"


def _patch_source_view(patch_text: str) -> str:
    return "\n".join(
        line[1:]
        for line in patch_text.splitlines()
        if (line.startswith(" ") or line.startswith("+")) and not line.startswith("+++")
    )


def _procedure(source: str) -> str:
    lines = source.splitlines()
    start = next(
        i for i, line in enumerate(lines)
        if line.strip().lower().startswith(f"pure subroutine {NAME}(")
    )
    end = next(
        i for i in range(start + 1, len(lines))
        if lines[i].strip().lower() == f"end subroutine {NAME}"
    )
    return "\n".join(line.strip().lower() for line in lines[start : end + 1])


def test_pr85_kdm6_graupel_cache() -> None:
    source_path = os.environ.get("PR85_KDM6_APPLIED_SOURCE")
    source = Path(source_path) if source_path else ROOT / "phys/module_mp_kdm6.F"
    patch = ROOT / "patches/pr85_kdm6_ice_sedimentation.patch"
    patch_text = patch.read_text()
    if source.is_file():
        source_text = source.read_text()
        source_scope = "full_applied_source"
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    else:
        source_text = _patch_source_view(patch_text)
        source_scope = "unified_patch_view"
        source_hash = hashlib.sha256(patch_text.encode()).hexdigest()
    fixture_text = HELPER.read_text()
    expected = _procedure(source_text)
    assert expected == _procedure(fixture_text), "fixture helper differs from applied KDM6 source"
    patch_helpers = [
        line[1:]
        for line in patch_text.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]
    assert any(
        [line.strip().lower() for line in patch_helpers[index : index + len(expected.splitlines())]]
        == expected.splitlines()
        for index in range(len(patch_helpers) - len(expected.splitlines()) + 1)
    ), "source patch must contain the exact tested cache helper"
    assert "call kdm6_refresh_graupel_intercept(progb_status(i,k),n0g,g1pmg," in source_text.lower()
    assert "pr85_trace_removed_qi = dble(pr85_trace_qi)-dble(qci(i,k,2))" in source_text.lower()
    assert "pr85_trace_snow_gain = dble(qrs(i,k,2))-dble(pr85_trace_qs)" in source_text.lower()

    scratch = Path(tempfile.mkdtemp(prefix="pr85_kdm6_graupel_cache_", dir="/var/tmp"))
    for optimization in ("O0", "O2"):
        build = scratch / optimization
        build.mkdir()
        command = [
            "bash",
            "-c",
            'source "$1/tests/intel_toolchain.sh" && '
            'if [[ "$2" == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); '
            'else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi && '
            '"$CLOUD_BAL_FC" "${flags[@]}" -free "$3" -o "$4/test.exe" && '
            '"$4/test.exe"',
            "pr85-kdm6-graupel-cache-test",
            str(ROOT),
            optimization,
            str(HELPER),
            str(build),
        ]
        result = subprocess.run(
            command,
            cwd=build,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        assert result.returncode == 0, result.stdout
        assert "CASE absent-to-active cache refreshed" in result.stdout
        assert "CASE tiny positive slope is rejected before intercept division" in result.stdout
        assert "CASE invalid status and divisor rejected" in result.stdout
        print(f"{optimization}: {result.stdout.strip()}")
    print("source_scope=" + source_scope)
    print("source_sha256=" + source_hash)
    print("fixture_sha256=" + hashlib.sha256(HELPER.read_bytes()).hexdigest())


if __name__ == "__main__":
    test_pr85_kdm6_graupel_cache()
    print("PR85 KDM6 graupel-cache test PASS")
