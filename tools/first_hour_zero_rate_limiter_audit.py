#!/usr/bin/env python3
"""Compile the retained KDM6 limiter and one conditional change in scratch."""
import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/Cloud-BAL/scratch/cp02_host_unit_contract_x3bcr8ui/host/phys/module_mp_kdm6.f90')
CAPTURE = ROOT / 'docs/evidence/cp02_zero_candidate_20261029/captures'
PROFILE = ROOT / 'tests/intel_toolchain.sh'
EXPECTED = ROOT / 'docs/evidence/cp02_zero_candidate_20261029/analysis/candidate.csv'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--scratch', type=Path, required=True)
    ap.add_argument('--receipt', type=Path, required=True)
    args = ap.parse_args()
    args.scratch.mkdir(parents=True, exist_ok=False)
    text = SOURCE.read_text()
    pattern = r'(?ms)^\s*if\(prevp\(i,k\)\.lt\.0\.\) then\n.*?^\s*else\n\s*prevp\(i,k\) = min\(prevp\(i,k\),\(satdt\)/2\)\n\s*endif'
    matches = list(re.finditer(pattern, text))
    if len(matches) != 1:
        raise ValueError('expected exactly one retained source limiter')
    old = matches[0].group().strip() + '\n'
    new = old.replace('\n            else\n', '\n            else if (prevp(i,k).ne.0.) then\n')
    if old == new or new.count('prevp(i,k).ne.0.') != 1:
        raise ValueError('candidate replacement was not unique')
    (args.scratch / 'old_excerpt.f90').write_text(old)
    (args.scratch / 'new_excerpt.f90').write_text(new)
    inputs = []
    expected = {(r['arm'], int(r['rank'])): r for r in csv.DictReader(EXPECTED.open())}
    def word(h):
        return int.from_bytes(bytes.fromhex(h), 'little')
    for arm in ('OFF', 'HYDRO', 'LIQUID'):
        for rank in (1, 3):
            path = next((CAPTURE / arm).glob(f'raw_*_rank{rank}_pid*.json.gz'))
            record = json.loads(gzip.decompress(path.read_bytes()))
            event = next(e for e in record['candidate_events'] if e['role'] == 'before_double_multiply')
            ops = event['operands']
            row = expected[arm, rank]
            inputs.append({'arm': arm, 'rank': rank, 'capture_sha256': sha(path),
                           'satdt': word(ops['frame_0x18']['raw_hex']),
                           'rain': word(ops['frame_0x50']['raw_hex']),
                           'dt': word(ops['frame_0x140']['raw_hex']),
                           'expected': word(row['source_raw_hex'])})
    init = '\n'.join(f"  sat({i})=transfer(int(z'{r['satdt']:08x}'),0.0)\n  rain({i})=transfer(int(z'{r['rain']:08x}'),0.0)\n  dt({i})=transfer(int(z'{r['dt']:08x}'),0.0)\n  expected({i})=int(z'{r['expected']:08x}')" for i, r in enumerate(inputs, 1))
    def proc(name, body):
        return f'''subroutine {name}(value, satdt, rain, dtcld, nc, nr)
  implicit none
  real :: value, satdt, rain, dtcld, nc, nr
  real :: prevp(1,1), qrs(1,1,1), nci(1,1,3), nrs(1,1,1)
  integer :: i, k
  i=1; k=1; prevp=value; qrs=rain; nci=nc; nrs=nr
{body}
  value=prevp(1,1); nc=nci(1,1,3); nr=nrs(1,1,1)
end subroutine {name}
'''
    harness = '''program check_limiter
  use iso_fortran_env, only: int32, real64
  implicit none
  real :: sat(6), rain(6), dt(6), a, b, nc1, nc2, nr1, nr2, x, s, r, qv0, qr0, t0, qv1, qr1, t1, xlwork2
  real(real64) :: v, dqv, dqr, dtemp, lv, cp, tol
  integer(int32) :: expected(6), origbits, newbits
  integer :: i, j, k
''' + init + '''
  do i=1,6
    a=transfer(int(z'80000000',int32),a); b=a
    nc1=2; nc2=2; nr1=3; nr2=3
    call old_limiter(a,sat(i),rain(i),dt(i),nc1,nr1)
    call new_limiter(b,sat(i),rain(i),dt(i),nc2,nr2)
    origbits=transfer(a,origbits); newbits=transfer(b,newbits)
    if (origbits /= expected(i)) error stop 'captured old rate mismatch'
    if (b /= 0 .or. newbits /= int(z'80000000',int32)) error stop 'negative zero not retained'
    if (sat(i) >= 0 .or. rain(i) < 0 .or. dt(i) <= 0) error stop 'bad captured inputs'
    write(*,'(a,i0,1x,z8.8,1x,z8.8)') 'capture ',i,origbits,newbits
  end do
  ! Finite nonzero values, both saturation signs, zero and positive rain.
  do i=1,5
    select case(i)
    case(1); x=-1.e-6
    case(2); x=1.e-6
    case(3); x=-tiny(x)
    case(4); x=tiny(x)
    case(5); x=-1.e-3
    end select
    do j=-1,1,2
      s=real(j)*1.e-4
      do k=0,1
        r=real(k)*1.e-3
        a=x; b=x; nc1=2; nc2=2; nr1=3; nr2=3
        call old_limiter(a,s,r,20.,nc1,nr1)
        call new_limiter(b,s,r,20.,nc2,nr2)
        if (transfer(a,origbits) /= transfer(b,newbits) .or. nc1 /= nc2 .or. nr1 /= nr2) &
          error stop 'nonzero behavior changed'
      end do
    end do
  end do
  do i=0,1
    do j=-1,1,2
      a=0.
      if (i == 1) a=transfer(int(z'80000000',int32),a)
      origbits=transfer(a,origbits); b=a; s=real(j)*1.e-4
      nc1=2; nc2=2; nr1=3; nr2=3
      call old_limiter(a,s,1.e-3,20.,nc1,nr1)
      call new_limiter(b,s,1.e-3,20.,nc2,nr2)
      if (b /= 0) error stop 'zero rate created'
      if (transfer(b,newbits) /= origbits) error stop 'zero sign changed'
      if (nc2 /= 2 .or. nr2 /= 3) error stop 'zero rate changed number'
      if (s < 0 .and. a >= 0) error stop 'old dry defect not reproduced'
      if (s > 0 .and. a /= 0) error stop 'old wet zero mismatch'
    end do
  end do
  ! Isolated rate increments in double precision; no full-model budget claim.
  lv=2.5e6_real64; cp=1004._real64; tol=1.e-12_real64
  do i=-1,1,2
    v=real(i,real64)*1.e-6_real64; dqv=-v*20; dqr=v*20
    dtemp=lv/cp*v*20
    if (abs(dqv+dqr)>tol) error stop 'water increment mismatch'
    if (abs(cp*dtemp-lv*dqr)>tol) error stop 'heat increment mismatch'
    if (dtemp*v<=0) error stop 'temperature sign mismatch'
    ! Source-order REAL32 update, away from floors and competing processes.
    a=real(v); qv0=.015; qr0=.001; t0=293.
    qv1=qv0-a*20.; qr1=max(qr0+a*20.,0.)
    xlwork2=-real(lv)*a; t1=t0-xlwork2/real(cp)*20.
    if (abs(real(qv1,real64)+real(qr1,real64)-real(qv0,real64)-real(qr0,real64)) > 3.e-9_real64) &
      error stop 'rounded local water conservation'
    if (abs(real(cp,real64)*(real(t1,real64)-real(t0,real64))-real(lv,real64)* &
      (real(qr1,real64)-real(qr0,real64))) > .02_real64) error stop 'rounded local heat balance'
    if ((t1-t0)*a <= 0.) error stop 'rounded temperature sign'
  end do
  print *, 'PASS signed-zero, both humidities, nonzero, floors, isolated mass and heat'
contains
'''+proc('old_limiter',old)+proc('new_limiter',new)+'end program check_limiter\n'
    f90 = args.scratch / 'check.f90'
    f90.write_text(harness)
    runs = []
    for name, flags in (('O0','CLOUD_BAL_FREE_FLAGS'), ('O2','CLOUD_BAL_REPRO_FLAGS')):
        shell = f'source "$1"; shift; flags=("${{{flags}[@]}}"); "$CLOUD_BAL_FC" "${{flags[@]}}" -free -extend-source 132 "$1" -o "$2"'
        exe = args.scratch / f'check_{name}'
        cmd = ['bash','-c',shell,'audit',str(PROFILE),str(f90),str(exe)]
        build = subprocess.run(cmd,cwd=args.scratch,text=True,capture_output=True)
        if build.returncode:
            raise RuntimeError(build.stdout+build.stderr)
        run = subprocess.run(['bash','-c','source "$1"; exec "$2"','audit',str(PROFILE),str(exe)],cwd=args.scratch,text=True,capture_output=True)
        if run.returncode:
            raise RuntimeError(run.stdout+run.stderr)
        runs.append({'profile': name, 'stdout':run.stdout, 'build_stdout':build.stdout, 'build_stderr':build.stderr, 'executable_sha256':sha(exe)})
    args.receipt.parent.mkdir(parents=True,exist_ok=True)
    args.receipt.write_text(json.dumps({'source':str(SOURCE),'source_sha256':sha(SOURCE),'old_excerpt_sha256':sha(args.scratch/'old_excerpt.f90'), 'new_excerpt_sha256':sha(args.scratch/'new_excerpt.f90'), 'tool_sha256':sha(Path(__file__)),'profile_sha256':sha(PROFILE),'captured_summary_sha256':sha(EXPECTED),'inputs':inputs,'runs':runs,'scope':'isolated fragment; no full-model closure or source provenance claim'},indent=2)+'\n')


if __name__ == '__main__':
    main()
