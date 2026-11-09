"""Identity and source-boundary guards for the first ice velocity correction."""
import hashlib
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'docs/evidence/cp02_first_ice_velocity_20261109/native'
CONTROL = EVIDENCE / 'source/module_mp_kdm6_FIX_control.f90'
NEW = EVIDENCE / 'source/module_mp_kdm6_FIX_new.f90'
PATCH = ROOT / 'patches/kdm6_first_ice_velocity.patch'


def test_frozen_patch_and_source_boundary():
    expected = {
        CONTROL: 'ad255ae8b505af6b4ceebd177a54948d8bfff7fcd2c9f6d45c90122be0b57786',
        NEW: 'c2e90bcc04b0f8fac2224c24124cbac0f5fbf0916ee91f679759e5bbb55bfcc2',
        PATCH: 'e84013108baa00b0bec6582f7cd9ec9f3d051a76077730ff9bcfcf29f7444ed2',
    }
    for path, digest in expected.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    with tempfile.TemporaryDirectory() as directory:
        candidate = Path(directory) / 'module_mp_kdm6_FIX.f90'
        candidate.write_bytes(CONTROL.read_bytes())
        subprocess.run(['patch', '--batch', '-p1', '-i', str(PATCH)], cwd=directory, check=True, capture_output=True)
        assert candidate.read_bytes() == NEW.read_bytes()
    source = NEW.read_text()
    for size, name in [(4, 'work1'), (2, 'workn')]:
        assert re.search(r'double precision,\s*dimension\(its:ite,kts:kte,' + str(size) + r'\)\s*::\s*' + name + r'\b', source, re.I)
    warm_end = source.index('      enddo', source.index('   call slope_kdm6', source.index('      do n = 1, mstepmax\n')))
    ice_start = source.index('      do n = 1, mstepmax_i', warm_end)
    boundary = source[warm_end:ice_start]
    assert boundary.count('work1(i,k,4) = work1(i,k,4)/delz(i,k)') == 1
    assert boundary.count('workn(i,k,2) = workn(i,k,2)/delz(i,k)') == 1
