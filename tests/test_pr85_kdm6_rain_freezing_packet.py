#!/usr/bin/env python3
"""Pinned-Intel source-form regression for rain-to-graupel freezing."""
from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def test_pr85_kdm6_rain_freezing_packet() -> None:
    patch = ROOT / "patches/pr85_kdm6_ice_sedimentation.patch"
    helper = ROOT / "tools/pr85_kdm6_rain_freezing_packet.F90"
    fixture = ROOT / "tests/fixtures/pr85_kdm6_rain_freezing_packet.F90"
    additions = "\n".join(
        line[1:]
        for line in patch.read_text().splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )
    helper_lines = helper.read_text().splitlines()
    added_lines = additions.splitlines()
    assert any(
        added_lines[index : index + len(helper_lines)] == helper_lines
        for index in range(len(added_lines) - len(helper_lines) + 1)
    ), "the source patch must append the exact tested rain-freezing helper"
    for contract in (
        "external :: pr85_kdm6_rain_freezing_packet",
        "call pr85_kdm6_rain_freezing_packet(qrs(i,k,1),nrs(i,k,1), &",
        "pr85_rf_volume_request=DBLE(pfrzdtr)/DBLE(denr)",
        "DBLE(pidnr)/(DBLE(lamdarmax)**DBLE(dmr))",
        "DBLE(pidnr)/(DBLE(lamdarmin)**DBLE(dmr))",
        "100.0d0,900.0d0",
        "file='pr85_rain_freezing_budget.raw'",
        "PR85_RAIN_FREEZE: i,lat,k,loop,accepted,base_valid,theta",
        "(a,4i8,1x,2l1,1p,28e24.16)",
        "if (.not.pr85_rf_accepted) then",
        "pr85_rf_mass_approved=0.0d0",
        "pr85_rf_qr_after=pr85_rf_qr_before",
        "pr85_rf_t_after=pr85_rf_t_before",
        "error stop 'PR85 invalid rain-graupel freezing base'",
        "if (pr85_rf_accepted) then",
        "qrs(i,k,3)=pr85_rf_qg_after",
        "brs(i,k)=pr85_rf_bg_after",
        "pr85_rf_t_candidate=DBLE(pr85_rf_t_before)+",
        "if (.not.ieee_is_finite(pr85_rf_t_candidate) .or. &",
        "qrs(i,k,1)=pr85_rf_qr_after",
        "nrs(i,k,1)=pr85_rf_nr_after",
        "t(i,k)=pr85_rf_t_after",
        "(a,4i8,1x,2l1,1p,28e24.16)",
        "if (.not.pr85_rf_accepted) then",
        "pr85_rf_mass_approved=0.0d0",
        "pr85_rf_qr_after=pr85_rf_qr_before",
        "pr85_rf_t_after=pr85_rf_t_before",
        "DBLE(dry_carrier_density(i,k))*((DBLE(pr85_rf_qr_before)+DBLE(pr85_rf_qg_before))-",
    ):
        assert contract in additions, f"missing KDM6 source contract: {contract}"
    assert "qrs(i,k,3) = qrs(i,k,3) + pfrzdtr" not in additions
    assert "brs(i,k) = brs(i,k) + (pfrzdtr/denr)" not in additions

    scratch = Path(tempfile.mkdtemp(prefix="pr85_kdm6_rain_freezing_", dir="/var/tmp"))
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
            '"$3" "$4" -o "$5/pr85_kdm6_rain_freezing_packet.exe" && '
            '"$5/pr85_kdm6_rain_freezing_packet.exe"',
            "pr85-kdm6-rain-freezing-test",
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
        assert "PR85 KDM6 rain-freezing packet cases PASS" in result.stdout
        print(f"{optimization}: {result.stdout.strip()}")
    print("helper_sha256=" + hashlib.sha256(helper.read_bytes()).hexdigest())
    print("fixture_sha256=" + hashlib.sha256(fixture.read_bytes()).hexdigest())


if __name__ == "__main__":
    test_pr85_kdm6_rain_freezing_packet()
    print("PR85 KDM6 rain-freezing packet test PASS")
