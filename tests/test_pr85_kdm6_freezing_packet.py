#!/usr/bin/env python3
"""Pinned-Intel source-form regression for paired KDM6 cloud freezing."""
from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def test_pr85_kdm6_freezing_packet() -> None:
    patch = ROOT / "patches/pr85_kdm6_ice_sedimentation.patch"
    helper = ROOT / "tools/pr85_kdm6_freezing_packet.F90"
    fixture = ROOT / "tests/fixtures/pr85_kdm6_freezing_packet.F90"
    additions = "\n".join(
        line[1:]
        for line in patch.read_text().splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )
    helper_lines = helper.read_text().splitlines()
    helper_source = helper.read_text()
    fixture_source = fixture.read_text()
    added_lines = additions.splitlines()
    assert any(
        added_lines[index : index + len(helper_lines)] == helper_lines
        for index in range(len(added_lines) - len(helper_lines) + 1)
    ), "the source patch must append the exact tested packet helper"
    assert "ice_transient_mass_limit" in helper_source
    assert "qice>0.0_real32 .AND. REAL(qice,real64)<=ice_transient_mass_limit" in helper_source
    assert ".NOT.in_cone(qio,nio,dry_density,ice_min,ice_max)" in helper_source
    assert "captured_subqmin_ice_base_case" in fixture_source
    assert "captured_pfrz_native_inactive_base_case" in fixture_source
    assert "exact_native_ice_threshold_case" in fixture_source
    assert "representable_subqmin_ice_case" in fixture_source
    assert "active_out_of_cone_base_case" in fixture_source
    for source_contract in (
        "rslopecdmax = (rslopecmax) ** dmc",
        "external :: pr85_kdm6_freezing_packet",
        "call pr85_kdm6_freezing_packet(qci(i,k,1),nci(i,k,1), &",
        "DBLE(PR85_ICE_NATIVE_INACTIVE_MAX), &",
        "pr85_freeze_ice_transient_base = qci(i,k,2).gt.0.0 .and. &\n                  qci(i,k,2).le.PR85_ICE_NATIVE_INACTIVE_MAX",
        "if (nci(i,k,1) .gt. 0.0) then",
        "if(nci(i,k,1).gt.0.0) then",
        "file='pr85_kdm6_freezing_budget.raw'",
        "error stop 'PR85 invalid cloud-ice freezing packet base'",
        "pr85_freeze_t_candidate=DBLE(pr85_freeze_t_before)+",
        "real :: pr85_freeze_t_before, pr85_freeze_t_after",
        "cpm(i,k).le.0.0",
        "(a,3i8,1x,3l1,1p,25e24.16)",
        "'PINU',i,lat,k,pr85_freeze_accepted,pr85_freeze_base_valid,",
        "'PFRZ',i,lat,k,pr85_freeze_accepted,pr85_freeze_base_valid,",
    ):
        assert source_contract in additions, f"missing KDM6 source contract: {source_contract}"
    assert additions.count("call pr85_kdm6_freezing_packet(") == 2
    assert additions.count("DBLE(PR85_ICE_NATIVE_INACTIVE_MAX), &") == 2
    assert "PR85_ICE_NATIVE_INACTIVE_MAX = NEAREST(1.e-14,-1.0)" in additions
    assert additions.count("ice_transient_mass_limit=PR85_ICE_NATIVE_INACTIVE_MAX") == 8
    assert "if (nci(i,k,1) .gt. ncmin) then\n              ninuc" not in additions
    assert "if(nci(i,k,1).gt.ncmin) then\n\n              nfrzdtc" not in additions

    scratch = Path(tempfile.mkdtemp(prefix="pr85_kdm6_freezing_", dir="/var/tmp"))
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
            '"$3" "$4" -o "$5/pr85_kdm6_freezing_packet.exe" && '
            '"$5/pr85_kdm6_freezing_packet.exe"',
            "pr85-kdm6-freezing-test",
            str(ROOT),
            optimization,
            str(helper),
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
        assert "PR85 KDM6 freezing packet cases PASS" in result.stdout
        print(f"{optimization}: {result.stdout.strip()}")
    print("helper_sha256=" + hashlib.sha256(helper.read_bytes()).hexdigest())
    print("fixture_sha256=" + hashlib.sha256(fixture.read_bytes()).hexdigest())


if __name__ == "__main__":
    test_pr85_kdm6_freezing_packet()
    print("PR85 KDM6 freezing packet test PASS")
