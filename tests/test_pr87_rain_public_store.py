#!/usr/bin/env python3
"""Pinned-Intel O0/O2 test for the public rain-store boundary."""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_pr87_rain_public_store() -> None:
    kernel = ROOT / 'src/common/cloud_bal_joint_transport.f90'
    helper = ROOT / 'tools/pr87_rain_public_store.f90'
    fixture = ROOT / 'tests/test_pr87_rain_public_store.f90'
    scratch = Path(tempfile.mkdtemp(prefix='pr87_rain_public_store_', dir='/var/tmp'))

    for profile in ('O0', 'O2'):
        build = scratch / profile
        build.mkdir()
        command = [
            'bash', '-c',
            'source "$1/tests/intel_toolchain.sh" && '
            'if [[ "$2" == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); '
            'else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi && '
            '"$CLOUD_BAL_FC" "${flags[@]}" -free -module "$5" -I "$5" '
            '"$3" "$4" "$6" -o "$5/test.exe" && "$5/test.exe"',
            'pr87-rain-public-store-test', str(ROOT), profile,
            str(kernel), str(helper), str(build), str(fixture),
        ]
        result = subprocess.run(command, cwd=build, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                check=False)
        assert result.returncode == 0, result.stdout
        assert 'PR87 rain public store cases PASS' in result.stdout, result.stdout
        print(f'{profile}: {result.stdout.strip()}')


if __name__ == '__main__':
    test_pr87_rain_public_store()
    print('PR87 public rain-store Intel test PASS')
