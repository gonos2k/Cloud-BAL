#!/usr/bin/env python3
"""Replay exact V35 cold graupel search operands with pinned Intel ifx."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

SOURCE = Path('/var/tmp/pr87_joint_cycle_sources_20261016_v34/module_mp_kdm6.F')
EXPECTED_SOURCE_SHA256 = '2b10d9f15caa6c91a541428b19a6187bab7d75080e1ab67ae94b2435f7d928ce'
TOOLCHAIN = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr87_two_step_20261016/Cloud-BAL/tests/intel_toolchain.sh')
ROOT = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr87_two_step_20261016/Cloud-BAL')
META = re.compile(r'^\s*PR87_GSEARCH_FAIL_META\s+(.*)$')
STATE = re.compile(r'^\s*PR87_GSEARCH_FAIL_STATE\s+(.*)$')
CONFIG = re.compile(r'^\s*PR87_GSEARCH_FAIL_CONFIG\s+(.*)$')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_log(path: Path) -> str:
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt', encoding='utf-8', errors='replace') as stream:
        return stream.read()


def parse_rows(path: Path) -> list[dict]:
    groups = []
    pending = None
    for line_no, line in enumerate(read_log(path).splitlines(), 1):
        match = META.match(line)
        if match:
            if pending is not None:
                raise ValueError(f'incomplete diagnostic before line {line_no}')
            vals = [int(x) for x in match.group(1).split()]
            if len(vals) != 9:
                raise ValueError(f'META at {line_no} has {len(vals)} fields, expected 9')
            pending = {'meta': vals, 'line': line_no}
            continue
        match = STATE.match(line)
        if match:
            if pending is None or 'state' in pending:
                raise ValueError(f'unexpected STATE at line {line_no}')
            vals = [float(x.replace('D', 'E')) for x in match.group(1).split()]
            if len(vals) != 26:
                raise ValueError(f'STATE at {line_no} has {len(vals)} fields, expected 26')
            pending['state'] = vals
            continue
        match = CONFIG.match(line)
        if match:
            if pending is None or 'state' not in pending:
                raise ValueError(f'unexpected CONFIG at line {line_no}')
            vals = [float(x.replace('D', 'E')) for x in match.group(1).split()]
            if len(vals) != 16:
                raise ValueError(f'CONFIG at {line_no} has {len(vals)} fields, expected 16')
            pending['config'] = vals
            groups.append(pending)
            pending = None
    if pending is not None:
        raise ValueError('trailing incomplete GSEARCH diagnostic')
    if not groups:
        raise ValueError('no PR87_GSEARCH_FAIL_* rows found')
    return groups


def extract_routines(source: str) -> str:
    spans = []
    for name in ('kdm6_rain_process_fraction', 'kdm6_rain_process_state_valid'):
        start = re.search(r'^\s*subroutine\s+' + name + r'\s*\(', source, re.I | re.M)
        end = re.search(r'^\s*end subroutine\s+' + name + r'\b', source, re.I | re.M)
        if not start or not end or end.start() <= start.start():
            raise ValueError(f'cannot extract {name}')
        spans.append(source[start.start():end.end()])
    return '\n\n'.join(spans)


def f64(x: float) -> str:
    return f'{x:.17E}'.replace('E', 'E') + '_8'


def array(name: str, vals: list[float]) -> str:
    parts = [f64(x) for x in vals]
    return f"  {name} = real([ &\n       {', &\n       '.join(parts)}])"


def make_driver(row: dict, index: int) -> str:
    m = row['meta']
    s = row['state']
    c = row['config']
    # Diagnostic schema order is q_fixed[5], q_process[5], n_fixed[3],
    # n_process[3], bg_fixed/process, T_fixed/process, density, pidnr,
    # qmin, ncmin, qcrmin, dmr.
    qf, qp, nf, np_ = s[0:5], s[5:10], s[10:13], s[13:16]
    bgf, bgp, tf, tp, density, pidnr, qmin, ncmin, qcrmin, dmr = s[16:]
    # Config: rain bounds; cloud pid/exponent/bounds; ice pid/exponent/bounds;
    # vapor fixed/process; ice transient threshold; actual returned alpha.
    lmin, lmax, qlmin, qlmax, pidnc, dmc, lcmin, lcmax, pidni, dmi, limin, limax, qvf, qvp, ice_limit, alpha = c
    rain_pending = '.true.' if m[7] else '.false.'
    ice_pending = '.true.' if m[8] else '.false.'
    return f'''program replay_case_{index}
  use replay_kdm6_helpers
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  implicit none
  real :: qf(5), qp(5), nf(3), np(3), bgf, bgp, tf, tp
  real :: density, pidnr, qmin, ncmin, qcrmin, dmr
  real :: lmin, lmax, pidnc, dmc, lcmin, lcmax, pidni, dmi, limin, limax
  real :: qvf, qvp, ice_limit, alpha, fraction
  real :: qbase(5), nbase(3), qfull(5), nfull(3), bgbase, bgfull, tbase, tfull
  real :: qvbase, qvfull, active_lo, active_hi, qlo(5), qhi(5), nlo(3), nhi(3)
  real :: bglo, bghi
  real(kind=8) :: rainmax64, active_lower64, active_upper64, rain_envelope_margin
  logical :: feasible, validbase, validfull, vaporbasevalid, vaporfullvalid
  logical :: validlo, validhi
  integer :: search_status, reasonbase, reasonfull, reasonlo, reasonhi
{array('qf', qf)}
{array('qp', qp)}
{array('nf', nf)}
{array('np', np_)}
  bgf=real({f64(bgf)}); bgp=real({f64(bgp)})
  tf=real({f64(tf)}); tp=real({f64(tp)})
  density=real({f64(density)}); pidnr=real({f64(pidnr)})
  qmin=real({f64(qmin)}); ncmin=real({f64(ncmin)})
  qcrmin=real({f64(qcrmin)}); dmr=real({f64(dmr)})
  lmin=real({f64(lmin)}); lmax=real({f64(lmax)})
  pidnc=real({f64(pidnc)}); dmc=real({f64(dmc)})
  lcmin=real({f64(lcmin)}); lcmax=real({f64(lcmax)})
  pidni=real({f64(pidni)}); dmi=real({f64(dmi)})
  limin=real({f64(limin)}); limax=real({f64(limax)})
  qvf=real({f64(qvf)}); qvp=real({f64(qvp)})
  ice_limit=real({f64(ice_limit)}); alpha=real({f64(alpha)})
  call kdm6_rain_process_fraction(qf,qp,nf,np,bgf,bgp,tf,tp,{rain_pending}, &
       density,pidnr,qmin,ncmin,qcrmin,dmr,lmin,lmax,100.0,900.0,pidnc,dmc, &
       lcmin,lcmax,pidni,dmi,limin,limax,fraction,feasible,search_status, &
       qvf,qvp,ice_transient_mass_limit=ice_limit,ice_sublimation_pending={ice_pending})
  qbase=qf; nbase=nf; bgbase=bgf; tbase=tf; qvbase=qvf
  qfull=qf+qp; nfull=nf+np; bgfull=bgf+bgp; tfull=tf+tp; qvfull=qvf+qvp
  call kdm6_rain_process_state_valid(qbase,nbase,bgbase,tbase,density,pidnr,qmin,ncmin, &
       qcrmin,dmr,lmin,lmax,100.0,900.0,pidnc,dmc,lcmin,lcmax,pidni,dmi,limin,limax, &
       validbase,{rain_pending},ice_transient_mass_limit=ice_limit, &
       failure_reason=reasonbase,ice_sublimation_pending={ice_pending})
  call kdm6_rain_process_state_valid(qfull,nfull,bgfull,tfull,density,pidnr,qmin,ncmin, &
       qcrmin,dmr,lmin,lmax,100.0,900.0,pidnc,dmc,lcmin,lcmax,pidni,dmi,limin,limax, &
       validfull,{rain_pending},ice_transient_mass_limit=ice_limit, &
       failure_reason=reasonfull,ice_sublimation_pending={ice_pending})
  vaporbasevalid=ieee_is_finite(qvbase) .and. qvbase.ge.0.0
  vaporfullvalid=ieee_is_finite(qvfull) .and. qvfull.ge.0.0
  validbase=validbase.and.vaporbasevalid
  validfull=validfull.and.vaporfullvalid
  rainmax64=real(density,8)*real(lmax,8)**real(dmr,8)/real(pidnr,8)
  active_lower64=(real(1.0e-15,8)-real(bgf,8))/real(bgp,8)
  active_upper64=(rainmax64*real(qf(3),8)-real(nf(3),8))/ &
       (real(np(3),8)-rainmax64*real(qp(3),8))
  active_lo=real(active_lower64)
  do while (real(bgf+active_lo*bgp,8).le.real(1.0e-15,8))
    active_lo=nearest(active_lo,1.0)
  enddo
  do while (real(active_lo,8).le.active_lower64)
    active_lo=nearest(active_lo,1.0)
  enddo
  active_hi=real(active_upper64)
  if (real(active_hi,8).gt.active_upper64) active_hi=nearest(active_hi,-1.0)
  qlo=qf+active_lo*qp; nlo=nf+active_lo*np; bglo=bgf+active_lo*bgp
  qhi=qf+active_hi*qp; nhi=nf+active_hi*np; bghi=bgf+active_hi*bgp
  call kdm6_rain_process_state_valid(qlo,nlo,bglo,tf+active_lo*tp,density,pidnr, &
       qmin,ncmin,qcrmin,dmr,lmin,lmax,100.0,900.0,pidnc,dmc,lcmin,lcmax, &
       pidni,dmi,limin,limax,validlo,{rain_pending},ice_transient_mass_limit=ice_limit, &
       failure_reason=reasonlo,ice_sublimation_pending={ice_pending})
  call kdm6_rain_process_state_valid(qhi,nhi,bghi,tf+active_hi*tp,density,pidnr, &
       qmin,ncmin,qcrmin,dmr,lmin,lmax,100.0,900.0,pidnc,dmc,lcmin,lcmax, &
       pidni,dmi,limin,limax,validhi,{rain_pending},ice_transient_mass_limit=ice_limit, &
       failure_reason=reasonhi,ice_sublimation_pending={ice_pending})
  rain_envelope_margin=real(nhi(3),8)-rainmax64*real(qlo(3),8)
  write(*,'(a,4(1x,es26.17),2(1x,i0))') 'GSEARCH_RAIN_ENVELOPE', &
       active_lower64,active_upper64,real(active_lo,8),real(active_hi,8),reasonlo,reasonhi
  write(*,'(a,7(1x,es26.17))') 'GSEARCH_RAIN_ENVELOPE_STATE', &
       real(qlo(3),8),real(nlo(3),8),real(qhi(3),8),real(nhi(3),8),rainmax64,rain_envelope_margin,real(bglo,8)
  write(*,'(a,1x,es26.17)') 'GSEARCH_RAIN_ENVELOPE_BGHI',real(bghi,8)
  write(*,'(a,9(1x,i0))') 'CASE_META', {m[0]}, {m[1]}, {m[2]}, {m[3]}, {m[4]}, {m[5]}, search_status, reasonbase, reasonfull
  write(*,'(a,1x,l1,1x,es26.17,4(1x,l1),1x,es26.17)') &\n       'CASE_RESULT',feasible,fraction,validbase,validfull,vaporbasevalid,vaporfullvalid,alpha
end program replay_case_{index}
'''


def instrument(routines: str) -> str:
    """Clone only: label the search paths without changing search expressions."""
    out = routines
    # The baseline helper remains intact; diagnostic clone labels early exits
    # from validation/precondition section before breakpoint construction.
    head, tail = out.split('      count_breaks=2', 1)
    head += "      write(*,'(a)') 'DIAG_PRECONDITIONS_PASSED'\n"
    # Mark upper-walk exhaustion and nonfinite root/clip events.
    tail = tail.replace('''          if (walks.ge.32) then
            search_failed=.true.''', '''          if (walks.ge.32) then
            write(*,'(a,4(1x,es26.17))') 'DIAG_UPPER_WALK_EXHAUSTED',lower,upper,real(trial,8),real(walks,8)
            search_failed=.true.''')
    tail = tail.replace('''        if (.not.ieee_is_finite(root)) then
          search_failed=.true.''', '''        if (.not.ieee_is_finite(root)) then
          write(*,'(a,3(1x,es26.17))') 'DIAG_NONFINITE_ROOT',initial,slope,cutoff
          search_failed=.true.''')
    tail = tail.replace('''          if (.not.ieee_is_finite(boundary)) search_failed=.true.''', '''          if (.not.ieee_is_finite(boundary)) then
            write(*,'(a,3(1x,es26.17))') 'DIAG_NONFINITE_CLIP',initial,slope,boundary
            search_failed=.true.
          endif''')
    tail = tail.replace('''        if (.not.ieee_is_finite(lo) .or. .not.ieee_is_finite(hi)) then
          valid_interval=.false.
          search_failed=.true.
        endif''', '''        if (.not.ieee_is_finite(lo) .or. .not.ieee_is_finite(hi)) then
          write(*,'(a,2(1x,es26.17))') 'DIAG_NONFINITE_CLIP_BOUNDS',lo,hi
          valid_interval=.false.
          search_failed=.true.
        endif''')
    tail = tail.replace('''        search_status=search_failure_status
        return
      endif
      if (best.le.0.0d0) then''', '''        write(*,'(a,1x,es26.17)') 'DIAG_NO_BEST_SEARCH_FAILED',best
        search_status=search_failure_status
        return
      endif
      if (best.le.0.0d0) then''')
    tail = tail.replace('''      if (.not.step_valid) then
        fraction=0.0
        search_status=search_failure_status''', '''      if (.not.step_valid) then
        write(*,'(a,1x,es26.17)') 'DIAG_FINAL_BEST_INVALID',best
        fraction=0.0
        search_status=search_failure_status''')
    return head + '      count_breaks=2' + tail


def module_source(source: str, diagnostics: bool) -> str:
    routines = extract_routines(source)
    if diagnostics:
        routines = instrument(routines)
    const = re.search(r'^\s*real, parameter, private :: PR85_ICE_NATIVE_INACTIVE_MAX\s*=.*$', source, re.M)
    if not const:
        raise ValueError('missing PR85 ice transient constant')
    constant = const.group(0).replace(', private ::', ' ::')
    return 'module replay_kdm6_helpers\n use, intrinsic :: ieee_arithmetic, only: ieee_is_finite\n implicit none\n ' + constant.strip() + '\ncontains\n' + routines + '\nend module replay_kdm6_helpers\n'


def compile_and_run(ifx: str, flags: list[str], src: str, work: Path, tag: str) -> dict:
    f90 = work / f'{tag}.F90'
    exe = work / tag
    f90.write_text(src)
    cmd = [ifx, *flags, '-free', str(f90), '-o', str(exe)]
    cp = subprocess.run(cmd, text=True, capture_output=True)
    (work / f'{tag}.compile.stdout').write_text(cp.stdout)
    (work / f'{tag}.compile.stderr').write_text(cp.stderr)
    if cp.returncode:
        raise RuntimeError(f'ifx compile failed ({tag}), see {work}/{tag}.compile.stderr')
    rp = subprocess.run(['bash', '-lc', f'source {shlex.quote(str(TOOLCHAIN))}; exec {shlex.quote(str(exe))}'], cwd=ROOT, text=True, capture_output=True)
    (work / f'{tag}.stdout').write_text(rp.stdout)
    (work / f'{tag}.stderr').write_text(rp.stderr)
    if rp.returncode:
        raise RuntimeError(f'replay failed ({tag}), see {work}/{tag}.stderr')
    return {'compile_command': cmd, 'stdout': rp.stdout}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('rsl_out', type=Path)
    ap.add_argument('--work', type=Path, default=Path('/var/tmp/pr87_gsearch_replay_v35'))
    args = ap.parse_args()
    source = SOURCE.read_text()
    actual_hash = hashlib.sha256(source.encode()).hexdigest()
    if actual_hash != EXPECTED_SOURCE_SHA256:
        raise SystemExit(f'frozen V34 source hash mismatch: {actual_hash}')
    rows = parse_rows(args.rsl_out)
    args.work.mkdir(parents=True, exist_ok=False)
    # Source the one authoritative profile and collect only its O0/O2 flags.
    init = subprocess.run(['bash', '-lc', f'source {shlex.quote(str(TOOLCHAIN))}; declare -p CLOUD_BAL_FC CLOUD_BAL_FREE_FLAGS CLOUD_BAL_REPRO_FLAGS'], cwd=ROOT, text=True, capture_output=True)
    if init.returncode:
        raise SystemExit(init.stderr)
    # Bash arrays are not exported; print shell-escaped flags from the authoritative script.
    flag_cmd = f'''source {shlex.quote(str(TOOLCHAIN))}; printf '%s\\n' "$CLOUD_BAL_FC"; printf '%s\\n' "${{CLOUD_BAL_FREE_FLAGS[@]}}"; printf '%s\\n' '---O2---'; printf '%s\\n' "${{CLOUD_BAL_REPRO_FLAGS[@]}}"'''
    fp = subprocess.run(['bash', '-lc', flag_cmd], cwd=ROOT, text=True, capture_output=True, check=True)
    lines = fp.stdout.splitlines()
    sep = lines.index('---O2---')
    ifx, o0, o2 = lines[0], lines[1:sep], lines[sep+1:]
    receipt = {'input_log': str(args.rsl_out), 'input_log_sha256': sha(args.rsl_out),
               'source': str(SOURCE), 'source_sha256': actual_hash,
               'rows': [], 'flags': {'O0': o0, 'O2': o2}}
    for idx, row in enumerate(rows, 1):
        harness = module_source(source, False) + make_driver(row, idx)
        diag_harness = module_source(source, True) + make_driver(row, idx)
        outputs = {}
        for level, flags in [('O0', o0), ('O2', o2)]:
            outputs[level] = compile_and_run(ifx, flags, harness, args.work, f'case{idx}_{level}')
            outputs[level + '_diagnostic'] = compile_and_run(ifx, flags, diag_harness, args.work, f'case{idx}_{level}_diag')
        receipt['rows'].append({'line': row['line'], 'meta': row['meta'], 'state': row['state'],
                                'config': row['config'], 'results': outputs})
    receipt['ifx_version'] = subprocess.run([ifx, '--version'], capture_output=True, text=True).stdout.splitlines()[0]
    receipt_path = args.work / 'receipt.json'
    receipt_path.write_text(json.dumps(receipt, indent=2) + '\n')
    print(receipt_path)
    print(hashlib.sha256(receipt_path.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
