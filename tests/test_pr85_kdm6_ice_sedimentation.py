#!/usr/bin/env python3
"""Pinned-Intel source-form regression for unchanged KDM6 ice sedimentation."""
from __future__ import annotations
import hashlib, os, re, subprocess, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
NAME='pr85_kdm6_paired_sediment_column'
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def procedure(text):
    lines=text.splitlines()
    start=None
    interface_depth=0
    for i,line in enumerate(lines):
        if re.match(r"\s*end\s+interface\b",line,re.I):
            interface_depth=max(0,interface_depth-1)
        elif re.match(r"\s*(?:abstract\s+)?interface\b",line,re.I):
            interface_depth+=1
        elif interface_depth==0 and re.match(rf"\s*subroutine\s+{NAME}\s*\(",line,re.I):
            start=i
            break
    assert start is not None, f"no procedure body found for {NAME} outside INTERFACE blocks"
    end=next(i for i in range(start+1,len(lines)) if re.match(rf"\s*end\s+subroutine\s+{NAME}\s*$",lines[i],re.I))
    return "\n".join(lines[start:end+1])+"\n"
def patch_source(path):
    lines=[]
    for line in path.read_text().splitlines():
        if line.startswith(('+++','---','@@')): continue
        if line.startswith(('+',' ')): lines.append(line[1:])
    return "\n".join(lines)
def test_pr85_kdm6_ice_sedimentation_source_form():
    patch=ROOT/'patches/pr85_kdm6_ice_sedimentation.patch'
    helper=ROOT/'tools/pr85_kdm6_ice_sedimentation.F90'
    fixture=ROOT/'tests/fixtures/pr85_kdm6_ice_sedimentation_source.F90'
    applied=os.environ.get('PR85_KDM6_APPLIED_SOURCE')
    production=Path(applied).read_text() if applied else patch_source(patch)
    helper_lines=helper.read_text().splitlines()
    patch_lines=patch_source(patch).splitlines()
    assert any('call pr85_kdm6_paired_sediment_column' in line.lower() for line in patch_lines)
    helper_text='\n'.join(helper_lines).lower()
    assert 'valid,rain_pidn,rain_power,rain_lambda_min,rain_lambda_max)' in helper_text, (
        'extended helper must require native rain distribution coefficients'
    )
    assert 'pr87_sed_rain=3' in helper_text
    if applied:
        assert procedure(helper.read_text())==procedure(production)
    compact=re.sub(r'[\s&]+','',re.sub(r'!.*$','',production,flags=re.M)).lower()
    assert 'pr85_sed_ice,0.0,0.0,0.0,0.0,pr85_ice_qrate' in compact
    if applied:
        assert re.search(r'pr85_ice_valid,0(?:\.0*)?(?:_real32|d0)?,0(?:\.0*)?(?:_real32|d0)?,0(?:\.0*)?(?:_real32|d0)?,0(?:\.0*)?(?:_real32|d0)?\)', compact), (
            'applied ICE call must pass four zero rain coefficients'
        )
    scratch=Path(tempfile.mkdtemp(prefix='pr85_kdm6_ice_sed_',dir='/var/tmp'))
    for opt in ('O0','O2'):
        build=scratch/opt; build.mkdir()
        command=['bash','-c','source "$1/tests/intel_toolchain.sh" && '
          'if [[ "$2" == O0 ]]; then flags=("${CLOUD_BAL_FREE_FLAGS[@]}"); else flags=("${CLOUD_BAL_REPRO_FLAGS[@]}"); fi && '
          '"$CLOUD_BAL_FC" "${flags[@]}" -free "$3" "$4" -o "$5/test.exe" && "$5/test.exe"',
          'pr85-kdm6-ice-test',str(ROOT),opt,str(helper),str(fixture),str(build)]
        result=subprocess.run(command,cwd=build,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,check=False)
        assert result.returncode==0,result.stdout
        assert 'PR85 KDM6 ice sedimentation cases PASS' in result.stdout
        if opt=='O2': assert '#10182' not in result.stdout.lower(),result.stdout
        print(f'{opt}: {result.stdout.strip()}')
    print(f'helper_sha256={sha(helper)} fixture_sha256={sha(fixture)} patch_sha256={sha(patch)}')
if __name__=='__main__':
    test_pr85_kdm6_ice_sedimentation_source_form(); print('PR85 KDM6 ice sedimentation test PASS')
