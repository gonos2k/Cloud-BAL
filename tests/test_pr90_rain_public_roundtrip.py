#!/usr/bin/env python3
"""Exercise the real internal/public/volume storage helper chain with pinned Intel."""
from __future__ import annotations

import gzip
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from pr87_rain_storage_contract import extend_kdm6_public_return  # noqa: E402


def test_pr90_rain_public_roundtrip() -> None:
    kernel = ROOT / 'src/common/cloud_bal_joint_transport.f90'
    helper = ROOT / 'tools/pr87_rain_public_store.f90'
    fixture = ROOT / 'tests/test_pr90_rain_public_roundtrip.f90'
    source_form = gzip.decompress(
        (ROOT / 'docs/evidence/pr87_two_step_v12diag_20261016/module_mp_kdm6.F.gz').read_bytes()
    ).decode()
    transformed = extend_kdm6_public_return(source_form)
    handoff = transformed.index('call pr87_rain_public_store(')
    q_store = transformed.index('qr(i,k,j)=pr87_rain_q_public', handoff)
    n_store = transformed.index('number_value=pr87_rain_n_public', handoff)
    assert handoff < q_store < n_store
    helper_source = helper.read_text()
    assert 'subroutine pr90_rain_public_store_diagnostic(' in helper_source
    assert 'subroutine pr87_rain_public_store(' in helper_source
    assert 'call joint_moment_store(' in helper_source
    assert 'subroutine pr87_number_volume_store(' in helper_source

    scratch = Path(tempfile.mkdtemp(prefix='pr90_rain_roundtrip_', dir='/var/tmp'))
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
            'pr90-rain-public-roundtrip-test', str(ROOT), profile,
            str(kernel), str(helper), str(build), str(fixture),
        ]
        result = subprocess.run(command, cwd=build, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                check=False)
        assert result.returncode == 0, result.stdout
        assert 'PR90 rain public roundtrip cases PASS' in result.stdout, result.stdout
        print(f'{profile}: {result.stdout.strip()}')


if __name__ == '__main__':
    test_pr90_rain_public_roundtrip()
    print('PR90 rain public roundtrip Intel test PASS')
