#!/usr/bin/env python3
"""Pinned-Intel checks for freezing packet outcome and rollback semantics."""
from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def test_pr93_freezing_packet_contract() -> None:
    helper = ROOT / "tools/pr85_kdm6_freezing_packet.F90"
    fixture = ROOT / "tests/fixtures/pr93_freezing_packet_contract.F90"
    source = helper.read_text()
    assert "base_valid=.TRUE." in source
    assert "accepted=.TRUE." in source
    assert "IF (mass_requested==0.0_real64 .AND. number_requested==0.0_real64) THEN" in source
    assert "DO attempt=0,48" in source

    scratch = Path(tempfile.mkdtemp(prefix="pr93_freezing_contract_", dir="/var/tmp"))
    for optimization in ("O0", "O2"):
        build = scratch / optimization
        build.mkdir()
        command = [
            "bash",
            "-c",
            'source "$1/tests/intel_toolchain.sh" && '
            'if [[ "$2" == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); '
            'else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi && '
            '"$CLOUD_BAL_FC" "${flags[@]}" -free "$3" "$4" -o "$5/pr93_freezing_contract.exe" && '
            '"$5/pr93_freezing_contract.exe"',
            "pr93-freezing-contract-test",
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
        assert "PR93 freezing packet contract cases PASS" in result.stdout
        print(f"{optimization}: {result.stdout.strip()}")


if __name__ == "__main__":
    test_pr93_freezing_packet_contract()
    print("PR93 freezing packet contract test PASS")
