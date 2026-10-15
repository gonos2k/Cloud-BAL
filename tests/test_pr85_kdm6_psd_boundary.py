#!/usr/bin/env python3
"""Pinned-Intel source-form regression for native KDM6 lambda-bound number stores."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "tests/fixtures/pr85_kdm6_psd_boundary.F90"
NAME = "pr85_kdm6_psd_bound_number"


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
        if line.strip().lower().startswith(f"subroutine {NAME}(")
    )
    end = next(
        i for i in range(start + 1, len(lines))
        if lines[i].strip().lower() == f"end subroutine {NAME}"
    )
    return "\n".join(line.strip().lower() for line in lines[start : end + 1])


def test_pr85_kdm6_psd_boundary() -> None:
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
        source_hash = hashlib.sha256(patch.read_bytes()).hexdigest()

    expected = _procedure(source_text)
    assert expected == _procedure(HELPER.read_text()), "fixture differs from source helper"
    added = [line[1:] for line in patch_text.splitlines() if line.startswith("+") and not line.startswith("+++")]
    assert any(
        [line.strip().lower() for line in added[index : index + len(expected.splitlines())]]
        == expected.splitlines()
        for index in range(len(added) - len(expected.splitlines()) + 1)
    ), "KDM patch must append the exact tested helper"

    assert source_text.lower().count(f"call {NAME}(") == 18, "all three species × three stages × two bounds must use the helper"
    for species in ("rain", "cloud", "ice"):
        for stage in ("stage1", "stage2", "stage3"):
            assert f"'{species}','{stage}'" in source_text.lower()
    assert "exact_min=(rho64*lmin64**3)/pid64*q64" in expected
    assert "exact_max=(rho64*lmax64**3)/pid64*q64" in expected
    assert "rounded_bound=nearest(rounded_bound,1.0)" in expected
    assert "rounded_bound=nearest(rounded_bound,-1.0)" in expected
    assert "pr85_kdm6_psd_boundary.raw" in source_text.lower()
    assert "pr85 psd boundary ledger write failed" in source_text.lower()
    # In a full source file, the two remaining assignments are separate final count-cap branches.
    if source_scope == "full_applied_source":
        assert source_text.count("nrs(i,k,1) = dry_carrier_density(i,k)*qrs(i,k,1)*lamdr_tmp(i,k)**dmr/pidnr") == 1
        assert source_text.count("nci(i,k,1) = dry_carrier_density(i,k)*qci(i,k,1)*lamdc_tmp(i,k)**dmc/pidnc") == 1
        assert "nci(i,k,2) = dry_carrier_density(i,k)*qci(i,k,2)*lamdi_tmp(i,k)**dmi/pidni" not in source_text

    scratch = Path(tempfile.mkdtemp(prefix="pr85_kdm6_psd_boundary_", dir="/var/tmp"))
    for optimization in ("O0", "O2"):
        build = scratch / optimization
        build.mkdir()
        command = [
            "bash", "-c",
            'source "$1/tests/intel_toolchain.sh" && '
            'if [[ "$2" == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); '
            'else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi && '
            '"$CLOUD_BAL_FC" "${flags[@]}" -free "$3" -o "$4/test.exe" && "$4/test.exe"',
            "pr85-kdm6-psd-boundary-test", str(ROOT), optimization, str(HELPER), str(build),
        ]
        result = subprocess.run(command, cwd=build, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        assert result.returncode == 0, result.stdout
        assert "PR85 KDM6 PSD boundary cases PASS" in result.stdout
        print(f"{optimization}: {result.stdout.strip()}")
    print("source_scope=" + source_scope)
    print("source_sha256=" + source_hash)
    print("fixture_sha256=" + hashlib.sha256(HELPER.read_bytes()).hexdigest())


if __name__ == "__main__":
    test_pr85_kdm6_psd_boundary()
    print("PR85 KDM6 PSD boundary test PASS")
