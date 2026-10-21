from fractions import Fraction
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from pr96_column_closure import parse_trace, f32_from_bits, f32_bits
from pr97_prepare_liquid_observer import prepare


@pytest.fixture
def intel_scratch():
    with tempfile.TemporaryDirectory(prefix='pr97_liquid_test_', dir='/var/tmp') as directory:
        yield Path(directory)


@pytest.mark.parametrize('optimization', ['-O0', '-O2'])
def test_compact_store_error_matches_exact_reference(intel_scratch, optimization):
    tmp_path = intel_scratch
    cases = []
    for filename in ['off_liquid_transfer.raw', 'nearby_116_141_liquid_transfer.raw']:
        for row in parse_trace(ROOT / 'docs/evidence/pr96_column_20261021' / filename):
            e, q0, c0, q1, c1 = [f32_from_bits(row['bits'][i]) for i in (2,3,4,5,6)]
            cases.extend([(q0,-e,q1), (c0,e,c1)])
    # Transfers far below binary64 spacing must survive in the account's low part.
    cases.extend([(1.0, f32_from_bits(1), 1.0),
                  (1.0, -f32_from_bits(1), 1.0),
                  (f32_from_bits(1), -f32_from_bits(1), 0.0)])
    source = '''program check_store_error
use, intrinsic :: iso_fortran_env, only: real32,real64,int32,int64
use pr97_liquid_observer, only: store_error
implicit none
integer(int32) :: a,b,c
integer :: ios
real(real64) :: error
do
 read(*,'(3(z8,1x))',iostat=ios) a,b,c
 if(ios/=0) exit
 error=store_error(transfer(a,0.0_real32),transfer(b,0.0_real32),transfer(c,0.0_real32))
 write(*,'(z16.16)') transfer(error,0_int64)
enddo
end program
'''
    (tmp_path / 'driver.f90').write_text(source)
    shell = '''set -e
source "$1"
"$CLOUD_BAL_FC" "${CLOUD_BAL_REPRO_FLAGS[@]}" "$2" -module . -I . "$3" driver.f90 -o check.exe
'''
    subprocess.run(['bash','-c',shell,'pr97-test',str(ROOT/'tests/intel_toolchain.sh'),
                    optimization,str(ROOT/'tools/pr97_liquid_observer.f90')],
                   cwd=tmp_path,check=True,capture_output=True,text=True)
    data = ''.join(' '.join(f'{f32_bits(x):08X}' for x in case)+'\n' for case in cases)
    run_shell = 'source "$1"; exec "$2"'
    result = subprocess.run(['bash','-c',run_shell,'pr97-run',
                             str(ROOT/'tests/intel_toolchain.sh'),str(tmp_path/'check.exe')],
                            cwd=tmp_path,input=data,text=True,capture_output=True,check=True)
    rows=result.stdout.splitlines()
    assert len(rows)==len(cases)
    for case,bits in zip(cases,rows):
        before,extent,after=map(Fraction.from_float,case)
        expected=float(after-before-extent)
        actual=struct.unpack('>d',bytes.fromhex(bits))[0]
        assert actual==expected


def test_observer_transform_rejects_unpinned_source():
    with pytest.raises(ValueError,match='frozen compiled C1'):
        prepare(b'changed source')
