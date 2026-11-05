#!/usr/bin/env python3
"""Validate the related suite in a fresh tracked-tree export plus explicit task files."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
BUNDLE = ROOT / 'docs/evidence/cp02_failure_focus_20261105'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    target = ROOT.parent / 'validation' / ('clean_export_' + time.strftime('%Y%m%dT%H%M%S'))
    target.mkdir(parents=True, exist_ok=False)
    archive = subprocess.Popen(['git','archive','HEAD'],cwd=ROOT,stdout=subprocess.PIPE)
    with archive.stdout:
        extracted = subprocess.run(['tar','-xf','-','-C',str(target)],stdin=archive.stdout)
    if archive.wait() or extracted.returncode:
        raise RuntimeError('tracked-tree export failed')
    old = json.loads((ROOT/'docs/evidence/cp02_grouped_forecast_20261105/validation/clean_export.json').read_text())
    tests = [x for x in old['command'] if x.startswith('tests/')]
    additions = ['tests/test_cp02_b1_failure_targets.py', 'tests/test_cp02_b1_failure_state.py', 'tests/test_cp02_b1_failure_context.py', 'tests/test_plot_cp02_b1_failure_focus.py']
    tests = list(dict.fromkeys(tests + additions))
    owned = [p for p in BUNDLE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.lock')]
    owned += [ROOT/name for name in additions]
    owned += [p for p in (ROOT/'tools').glob('*cp02_b1_failure*py')]
    owned += [ROOT/'docs/CP02_B1_FAILURE_FOCUS_20261105.md', ROOT/'README.md', ROOT/'docs/CURRENT_RESEARCH_STATUS.md']
    names = sorted(set(str(p.relative_to(ROOT)) for p in owned))
    hashes = {}
    for name in names:
        src, dst = ROOT/name, target/name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src,dst)
        hashes[name] = sha(src)
    env = os.environ.copy()
    for key in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMEXPR_NUM_THREADS','BLIS_NUM_THREADS'):
        env[key] = '1'
    env.update(PYTHONDONTWRITEBYTECODE='1', MPLCONFIGDIR=str(target/'.mplconfig'))
    cmd = ['taskset','-c','16-23',sys.executable,'-m','pytest','-q',*tests]
    collection = subprocess.run(cmd[:6]+['--collect-only','-q',*tests],cwd=target,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    collected = re.search(r'(\d+) tests collected',collection.stdout)
    if collection.returncode or not collected:
        raise RuntimeError('test collection failed: '+collection.stdout)
    expected = int(collected.group(1))
    if expected < 410:
        raise RuntimeError('related test scope unexpectedly shrank')
    start = time.monotonic()
    proc = subprocess.run(cmd,cwd=target,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    log = BUNDLE/'validation/clean_export_pytest.txt'
    with log.open('x') as stream:
        stream.write(proc.stdout)
    match = re.search(r'(\d+) passed',proc.stdout)
    passed = int(match.group(1)) if match else 0
    unchanged = all(sha(ROOT/name)==value and sha(target/name)==value for name,value in hashes.items())
    result = {'status':'PASS' if proc.returncode==0 and passed==expected and unchanged else 'FAIL',
              'base_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              'export_path':str(target),'command':cmd,'test_files':len(tests),'expected_tests':expected,'passed':passed,
              'exit_code':proc.returncode,'elapsed_seconds':time.monotonic()-start,
              'overlay_sha256':hashes,'overlay_unchanged':unchanged,'log_sha256':sha(log),
              'scope':'Related Python suite from git archive plus explicit current task source/tests/evidence; not the full portable suite or WRF native re-integration.'}
    with (BUNDLE/'validation/clean_export.json').open('x') as stream:
        json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps({k:result[k] for k in ('status','passed','test_files','elapsed_seconds')}),flush=True)
    if result['status']!='PASS':
        raise RuntimeError('fresh export suite failed; inspect preserved log')


if __name__=='__main__':
    main()
