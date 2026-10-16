#!/usr/bin/env python3
"""Pinned-Intel runtime regression for the shared rain sedimentation kernel."""
from __future__ import annotations

import hashlib
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_pr87_rain_sedimentation_kernel() -> None:
    helper = ROOT / 'tools/pr85_kdm6_ice_sedimentation.F90'
    fixture = ROOT / 'tests/fixtures/pr87_kdm6_rain_sedimentation_source.F90'
    text = helper.read_text().lower()
    assert 'pr87_sed_rain=3' in text
    assert 'rain_state_valid64' in text and 'rain_state_valid32' in text
    scratch = Path(tempfile.mkdtemp(prefix='pr87_kdm6_rain_sed_', dir='/var/tmp'))
    for opt in ('O0', 'O2'):
        build = scratch / opt
        build.mkdir()
        command = [
            'bash', '-c',
            'source "$1/tests/intel_toolchain.sh" && '
            'if [[ "$2" == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); '
            'else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi && '
            '"$CLOUD_BAL_FC" "${flags[@]}" -free "$3" "$4" -o "$5/test.exe" && "$5/test.exe"',
            'pr87-kdm6-rain-kernel-test', str(ROOT), opt, str(helper), str(fixture), str(build),
        ]
        result = subprocess.run(command, cwd=build, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, check=False)
        assert result.returncode == 0, result.stdout
        assert 'PR87 KDM6 rain sedimentation cases PASS' in result.stdout
        if opt == 'O2':
            assert '#10182' not in result.stdout, result.stdout
        print(f'{opt}: {result.stdout.strip()}')
    print(f'helper_sha256={sha(helper)} fixture_sha256={sha(fixture)}')


if __name__ == '__main__':
    test_pr87_rain_sedimentation_kernel()
    print('PR87 KDM6 rain sedimentation kernel test PASS')
