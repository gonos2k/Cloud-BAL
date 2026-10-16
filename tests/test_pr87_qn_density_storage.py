#!/usr/bin/env python3
"""Pinned-Intel O0/O2 regression for atomic cloud/rain density storage."""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_pr87_qn_density_storage() -> None:
    kernel = ROOT / "src/common/cloud_bal_joint_transport.f90"
    public_store = ROOT / "tools/pr87_rain_public_store.f90"
    observer = ROOT / "tools/pr85_joint_stage_observer.f90"
    wrapper = ROOT / "tools/pr87_qn_density_store.f90"
    fixture = ROOT / "tests/test_pr87_qn_density_storage.f90"
    scratch = Path(tempfile.mkdtemp(prefix="pr87_qn_density_storage_", dir="/var/tmp"))

    for profile in ("O0", "O2"):
        build = scratch / profile
        build.mkdir()
        command = [
            "bash", "-c",
            'set -euo pipefail; source "$1/tests/intel_toolchain.sh"; '
            'if [[ "$2" == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); '
            'else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi; '
            '"$CLOUD_BAL_FC" "${flags[@]}" -free -module "$8" -I "$8" '
            '"$3" "$4" "$5" "$6" "$7" -o "$8/test.exe"; "$8/test.exe"',
            "pr87-qn-density-storage-test", str(ROOT), profile,
            str(kernel), str(public_store), str(observer), str(wrapper),
            str(fixture), str(build),
        ]
        result = subprocess.run(command, cwd=build, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                check=False)
        assert result.returncode == 0, result.stdout
        assert "PASS cloud/rain staged Q commit and tile rollback" in result.stdout, result.stdout
        ledger = build / "pr87_qn_density_storage.raw"
        lines = ledger.read_text().splitlines()
        cells = [line.split() for line in lines if line.startswith("PR87_QN_DENSITY_CELL")]
        assert len(cells) == 2, lines
        assert {int(row[3]) for row in cells} == {1, 2}, cells
        assert sum(line.startswith("PR87_QN_DENSITY_SUM") for line in lines) == 1, lines
        print(f"{profile}: {result.stdout.strip()}; ledger has cloud and rain rows")


if __name__ == "__main__":
    test_pr87_qn_density_storage()
    print("PR87 cloud/rain density storage Intel test PASS")
