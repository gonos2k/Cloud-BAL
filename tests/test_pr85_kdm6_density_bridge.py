#!/usr/bin/env python3
"""Pinned-Intel source-form regression for the KDM6 dry-density bridge."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def _patch_source_view(patch_text: str) -> str:
    return "\n".join(
        line[1:]
        for line in patch_text.splitlines()
        if (line.startswith(" ") or line.startswith("+")) and not line.startswith("+++")
    )


def _removed_patch_lines(patch_text: str) -> list[str]:
    return [
        line[1:]
        for line in patch_text.splitlines()
        if line.startswith("-") and not line.startswith("---")
    ]


def _procedure_lines(source: str, start: str, end: str) -> list[str]:
    lines = source.splitlines()
    first = next(i for i, line in enumerate(lines) if line.strip().lower().startswith(start))
    last = next(i for i in range(first, len(lines)) if lines[i].strip().lower() == end)
    return [line.strip().lower() for line in lines[first : last + 1]]


def test_pr85_kdm6_density_bridge() -> None:
    source_path = os.environ.get("PR85_KDM6_APPLIED_SOURCE")
    patch = ROOT / "patches/pr85_kdm6_ice_sedimentation.patch"
    helper = ROOT / "tools/pr85_kdm6_density_bridge.F90"
    fixture = ROOT / "tests/fixtures/pr85_kdm6_density_bridge.F90"
    patch_text = patch.read_text()
    source = Path(source_path) if source_path else ROOT / "phys/module_mp_kdm6.F"
    if source.is_file():
        module_text = source.read_text()
        source_scope = "full_applied_source"
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    else:
        module_text = _patch_source_view(patch_text)
        source_scope = "unified_patch_view"
        source_hash = hashlib.sha256(patch_text.encode()).hexdigest()
    helper_text = helper.read_text()
    patch_lines = [
        line[1:]
        for line in patch_text.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]
    helper_lines = [line.strip().lower() for line in helper_text.splitlines()]
    source_lines = _procedure_lines(
        module_text,
        "pure elemental subroutine dry_to_gas_density(",
        "end subroutine dry_to_gas_density",
    )
    assert source_lines == helper_lines, "applied KDM6 helper differs from tested helper"
    fixture_lines = _procedure_lines(
        fixture.read_text(),
        "pure elemental subroutine dry_to_gas_density(",
        "end subroutine dry_to_gas_density",
    )
    assert fixture_lines == helper_lines, "compiled fixture differs from the applied helper"
    assert any(
        [line.strip().lower() for line in patch_lines[index : index + len(helper_lines)]] == helper_lines
        for index in range(len(patch_lines) - len(helper_lines) + 1)
    ), "the source patch must append the exact tested helper body"
    assert "! pr85 density bridge: den is dry-air density; gas density is reconstructed with q." in module_text.lower()
    assert "dry_density(i,k) = den(i,k,j)" in module_text.lower()
    assert "call dry_to_gas_density(den(i,k), q(i,k), gas_density(i,k), carrier_valid)" in module_text.lower()
    old_call = "call moist_to_dry_density(gas_density(i,k), q(i,k), dry_carrier_density(i,k), carrier_valid)"
    if source_scope == "full_applied_source":
        assert old_call not in module_text.lower()
    else:
        assert any(old_call in line.lower() for line in _removed_patch_lines(patch_text))

    scratch = Path(tempfile.mkdtemp(prefix="pr85_kdm6_density_", dir="/var/tmp"))
    for optimization in ("O0", "O2"):
        build = scratch / optimization
        build.mkdir()
        command = [
            "bash",
            "-c",
            'source "$1/tests/intel_toolchain.sh" && '
            'if [[ "$2" == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); '
            'else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi && '
            '"$CLOUD_BAL_FC" "${flags[@]}" -free '
            '"$3" -o "$4/pr85_kdm6_density_bridge.exe" && '
            '"$4/pr85_kdm6_density_bridge.exe"',
            "pr85-kdm6-density-test",
            str(ROOT),
            optimization,
            str(fixture),
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
        if optimization == "O2":
            assert "warning #10182" not in result.stdout.lower(), result.stdout
        assert "CASE dry carrier preserved" in result.stdout
        assert "CASE invalid density inputs" in result.stdout
        print(f"{optimization}: {result.stdout.strip()}")
    print("source_scope=" + source_scope)
    print("source_sha256=" + source_hash)
    print("helper_sha256=" + hashlib.sha256(helper.read_bytes()).hexdigest())
    print("fixture_sha256=" + hashlib.sha256(fixture.read_bytes()).hexdigest())


if __name__ == "__main__":
    test_pr85_kdm6_density_bridge()
    print("PR85 KDM6 density bridge test PASS")
