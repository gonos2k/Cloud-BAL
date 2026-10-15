#!/usr/bin/env python3
"""Pinned-Intel source-form regression for KDM6 graupel QG/BG transport."""
from __future__ import annotations
import hashlib, os, re, subprocess, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
NAME='pr85_kdm6_paired_sediment_column'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def proc(text):
    lines=text.splitlines()
    start=next(i for i,x in enumerate(lines) if re.match(rf'\s*subroutine\s+{NAME}\s*\(',x,re.I))
    end=next(i for i in range(start+1,len(lines)) if re.match(rf'\s*end\s+subroutine\s+{NAME}\s*$',lines[i],re.I))
    return '\n'.join(lines[start:end+1])+'\n'
def patch_source(path):
    lines=[]
    for line in path.read_text().splitlines():
        if line.startswith(('+++','---','@@')): continue
        if line.startswith(('+',' ')): lines.append(line[1:])
    return '\n'.join(lines)
def test_pr85_kdm6_graupel_sedimentation_source_form():
    patch=ROOT/'patches/pr85_kdm6_ice_sedimentation.patch'
    helper=ROOT/'tools/pr85_kdm6_ice_sedimentation.F90'
    fixture=ROOT/'tests/fixtures/pr85_kdm6_graupel_sedimentation_source.F90'
    applied=os.environ.get('PR85_KDM6_APPLIED_SOURCE')
    production=Path(applied).read_text() if applied else patch_source(patch)
    helper_text=helper.read_text()
    assert proc(helper_text)==proc(patch_source(patch)), 'helper source differs from patch addition'
    if applied: assert proc(helper_text)==proc(production)
    compact=re.sub(r'[\s&]+','',re.sub(r'!.*$','',production,flags=re.M)).lower()
    assert 'pr85_sed_graupel,qcrmin,pr85_brs_min,100.0,900.0' in compact
    assert 'mass_velocity_rate(i,kts:kte,3),mass_velocity_rate(i,kts:kte,3)' in compact, (
        'graupel QG and BG must use the same native V3 rate'
    )
    assert 'pr85_g_qrate(kts:kte),pr85_g_brate(kts:kte)' in compact
    # B stores specific volume per dry-air mass; its column inventory is rho*B*dz.
    assert 'nproposal(k)=real(second_state(k),real64)*second_rate(k)* &' in helper_text.lower()
    assert 'real(second_carrier(k),real64)*real(delz(k),real64)*dt64' in helper_text.lower()
    scratch=Path(tempfile.mkdtemp(prefix='pr85_kdm6_graupel_sed_',dir='/var/tmp'))
    for opt in ('O0','O2'):
        build=scratch/opt; build.mkdir()
        command=['bash','-c',
          'source "$1/tests/intel_toolchain.sh" && '
          'if [[ "$2" == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); '
          'else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi && '
          '"$CLOUD_BAL_FC" "${flags[@]}" -free "$3" "$4" -o "$5/test.exe" && "$5/test.exe"',
          'pr85-kdm6-graupel-test',str(ROOT),opt,str(helper),str(fixture),str(build)]
        result=subprocess.run(command,cwd=build,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,check=False)
        assert result.returncode==0,result.stdout
        assert 'PR85 KDM6 graupel sedimentation cases PASS' in result.stdout
        if opt=='O2': assert '#10182' not in result.stdout,result.stdout
        print(f'{opt}: {result.stdout.strip()}')
    if applied: print(f'applied_source_sha256={sha(Path(applied))}')
    print(f'helper_sha256={sha(helper)} fixture_sha256={sha(fixture)} patch_sha256={sha(patch)}')
if __name__=='__main__':
    test_pr85_kdm6_graupel_sedimentation_source_form(); print('PR85 KDM6 graupel sedimentation test PASS')
