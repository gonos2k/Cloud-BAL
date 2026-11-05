#!/usr/bin/env python3
"""Run the previous related suite and new tests from a fresh HEAD export."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BUNDLE = 'docs/evidence/cp02_thermo_cloud_path_20261105'
TESTS = ['tests/test_cp02_thermo_cloud_cohorts.py', 'tests/test_cp02_thermo_cloud_path.py',
         'tests/test_plot_cp02_thermo_cloud_path.py']
TOOLS = ['tools/cp02_thermo_cloud_cohorts.py', 'tools/cp02_thermo_cloud_path.py',
         'tools/plot_cp02_thermo_cloud_path.py']


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def overlay(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def main():
    target = Path(sys.argv[1]).resolve()
    if target.exists():
        raise FileExistsError(target)
    if subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() != '45de814aa346527748fcfe2d8c16e30d46726ca8':
        raise ValueError('unexpected base HEAD')
    for p in TESTS + TOOLS:
        if not (ROOT / p).is_file():
            raise FileNotFoundError(p)
    target.mkdir(parents=True)
    archive = subprocess.Popen(['git', 'archive', 'HEAD'], cwd=ROOT, stdout=subprocess.PIPE)
    extract = subprocess.run(['tar', '-xf', '-', '-C', str(target)], stdin=archive.stdout, check=False)
    archive.stdout.close()
    if archive.wait() or extract.returncode:
        raise RuntimeError('HEAD export failed')
    owned = TESTS + TOOLS + ['README.md', 'docs/CURRENT_RESEARCH_STATUS.md', 'docs/CP02_THERMO_CLOUD_PATH_20261105.md']
    for p in (ROOT / BUNDLE).rglob('*'):
        if p.is_file() and '__pycache__' not in p.parts and not p.name.endswith(('.pyc', '.lock')):
            owned.append(str(p.relative_to(ROOT)))
    if len(owned) != len(set(owned)):
        raise ValueError('duplicate overlay')
    identity = {}
    for name in sorted(owned):
        source = ROOT / name
        identity[name] = {'sha256': sha(source), 'bytes': source.stat().st_size}
        overlay(source, target / name)
    prior = json.loads((ROOT / 'docs/evidence/cp02_failure_regimes_20261104/validation/clean_export_final_pytest.json').read_text())
    old = [x for x in prior['command'] if x.startswith('tests/')]
    if len(old) != 47:
        raise ValueError('prior suite inventory differs')
    suite = old + ['tests/test_package_cp02_failure_gallery.py'] + TESTS
    if len(suite) != len(set(suite)) or len(suite) != 51:
        raise ValueError('test inventory differs')
    command = ['taskset', '-c', '48-55', sys.executable, '-m', 'pytest', '-q', *suite]
    env = os.environ.copy()
    for name in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMEXPR_NUM_THREADS','BLIS_NUM_THREADS','VECLIB_MAXIMUM_THREADS'):
        env[name] = '1'
    env.update(OMP_DYNAMIC='FALSE', PYTHONDONTWRITEBYTECODE='1', MPLCONFIGDIR=str(target / '.mplconfig'))
    start = time.time()
    proc = subprocess.run(command, cwd=target, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    log = ROOT / BUNDLE / 'validation/clean_export_pytest.txt'
    if log.exists():
        raise FileExistsError(log)
    log.write_text(proc.stdout)
    match = re.search(r'(\d+) passed', proc.stdout)
    unchanged = all(sha(ROOT / name) == data['sha256'] and sha(target / name) == data['sha256'] for name, data in identity.items())
    result = {'status': 'PASS' if proc.returncode == 0 and match and int(match.group(1)) == 327 and unchanged else 'FAIL',
              'base_commit': '45de814aa346527748fcfe2d8c16e30d46726ca8', 'export_path': str(target),
              'command': command, 'test_files': len(suite), 'passed': int(match.group(1)) if match else None,
              'exit_code': proc.returncode, 'elapsed_seconds': time.time() - start,
              'overlay_files': identity, 'overlay_unchanged': unchanged,
              'log_path': str(log.relative_to(ROOT)), 'log_sha256': sha(log),
              'scope': 'Fresh git archive of HEAD plus explicit current task source, tests, documentation and evidence; no external runtime files.'}
    receipt = ROOT / BUNDLE / 'validation/clean_export_suite.json'
    receipt.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'passed': result['passed'], 'test_files': len(suite), 'receipt_sha256': sha(receipt)}))
    if result['status'] != 'PASS':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
