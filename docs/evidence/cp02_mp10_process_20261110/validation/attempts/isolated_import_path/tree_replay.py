#!/usr/bin/env python3
"""Replay the final task tree in scratch; never modify the shared Git index."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[4]
BUNDLE = Path('docs/evidence/cp02_mp10_process_20261110')
PARENT = Path('docs/evidence/cp02_pulse_path_20261110')
BASE = '0b81ec2f2b2eebe8b8cc797daa201e9780957b83'
REPORT = Path('docs/CP02_MP10_PROCESS_20261110.md')
TESTS = ['tests/test_cp02_mp10_failure_cohorts.py','tests/test_cp02_mp10_process.py',str(BUNDLE/'surface/test_mp10_surface.py')]
SOURCES = ['tools/cp02_mp10_failure_cohorts.py','tools/cp02_mp10_process.py','tools/plot_cp02_mp10_process.py',*TESTS,
           'README.md','docs/CURRENT_RESEARCH_STATUS.md',str(REPORT)]
EXTERNAL = [Path('/usr/share/fonts/truetype/nanum/NanumGothic.ttf')]


def identity(path):
    path = Path(path)
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'sha256': digest, 'size_bytes': path.stat().st_size}


def git(*args, env=None):
    return subprocess.check_output(['git', *args], cwd=ROOT, env=env, text=True).strip()


def overlays():
    names = set(SOURCES)
    for path in (ROOT/BUNDLE).rglob('*'):
        rel = path.relative_to(ROOT/BUNDLE)
        if rel.parts[0] in ('kg', 'validation') or '__pycache__' in rel.parts:
            continue
        if path.is_file() and not path.is_symlink() and path.suffix not in ('.pyc', '.lock'):
            names.add(str(path.relative_to(ROOT)))
    for name in names:
        path = ROOT/name
        if not path.is_file() or path.is_symlink():
            raise ValueError('missing or unsafe overlay: '+name)
    return sorted(names)


def profile_env(profile, temporary):
    result = subprocess.run(['bash', '-c', 'set -e; source "$1"; env -0', 'profile', str(profile)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    env = {k.decode(): v.decode(errors='surrogateescape') for item in result.stdout.split(b'\0')
           if item for k, v in [item.split(b'=', 1)]}
    for key in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'NUMEXPR_NUM_THREADS', 'BLIS_NUM_THREADS'):
        env[key] = '1'
    mpl = temporary/'mplconfig'; mpl.mkdir()
    env.update(PYTHONDONTWRITEBYTECODE='1', MPLCONFIGDIR=str(mpl), TMPDIR=str(temporary))
    return env


def run(cmd, cwd, env, logs, label):
    started = time.monotonic()
    result = subprocess.run(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    log = logs/(label+'.log'); log.write_text(result.stdout)
    if result.returncode:
        raise RuntimeError(f'{label} failed, see {log}:\n{result.stdout[-4000:]}')
    return {'argv': cmd, 'exit_code': result.returncode, 'seconds': round(time.monotonic()-started, 3),
            'log': str(log), 'log_identity': identity(log), 'tail': result.stdout[-2000:]}


def compare(expected, actual, names):
    result = {}
    for name in sorted(names):
        a, b = identity(expected/name), identity(actual/name)
        if a != b:
            raise ValueError('byte mismatch: '+name)
        result[name] = a
    return result


def surface_worker(tree, output):
    sys.path.insert(0,str(tree/'tools'))
    from cp02_ice_surface_components import replay
    import csv
    import numpy as np
    folder=tree/BUNDLE
    with (folder/'cohorts/selected_points.csv').open() as stream: points=list(csv.DictReader(stream))
    rows=[]
    with np.load(folder/'surface/results/native_corners.npz',allow_pickle=False) as data:
        for case in ('FIRST_ICE_VELOCITY','MP10'):
            components,total=replay(data[case],data['u'],data['v'],1e-6)
            for lead in range(1,7):
                for n,point in enumerate(points):
                    rows.append({'lead_hour':lead,'case':case,'flat_index_yx':int(point['flat_index_yx']),
                                 'cohort':point['cohort'],'rainc_mm':float(components[n,lead-1,0]),
                                 'rainnc_mm':float(components[n,lead-1,1]),'total_mm':float(total[n,lead-1]),
                                 'component_sum_minus_total_mm':float(components[n,lead-1].sum()-total[n,lead-1])})
    output.mkdir()
    with (output/'point_components.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=rows[0],lineterminator='\n');writer.writeheader();writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--scratch', type=Path)
    parser.add_argument('--go', action='store_true')
    parser.add_argument('--surface-worker', nargs=2, metavar=('TREE','OUTPUT'))
    args = parser.parse_args()
    if args.surface_worker:
        surface_worker(*(Path(p) for p in args.surface_worker)); return
    if not args.go or not args.output or not args.scratch:
        parser.error('replay requires explicit --go, --output and --scratch')
    if '<!-- 실제 전체 자료 분석 완료 후 수치 결과 추가 -->' in (ROOT/REPORT).read_text():
        raise ValueError('forecast report remains a draft')
    output = args.output.resolve()
    if os.path.lexists(output): raise FileExistsError(output)
    args.scratch.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='pulse-tree-replay-', dir=args.scratch.resolve()))
    export = work/'tree'; export.mkdir()
    temporary = work/'tmp'; temporary.mkdir()
    logs = work/'logs'; logs.mkdir()
    head = git('rev-parse', 'HEAD')
    if head != BASE: raise ValueError('source HEAD differs')
    names = overlays()
    replay_script = Path(__file__).resolve()
    replay_identity = identity(replay_script)
    worker = work/'tree_replay_worker.py'
    shutil.copyfile(replay_script, worker)
    index_path = Path(git('rev-parse', '--git-path', 'index'))
    if not index_path.is_absolute(): index_path = ROOT/index_path
    index_before = identity(index_path) if index_path.exists() else None
    before = {name: identity(ROOT/name) for name in names}
    external = {str(p): identity(p) for p in EXTERNAL}
    index_env = os.environ.copy(); index_env['GIT_INDEX_FILE'] = str(work/'private.index')
    git('read-tree', head, env=index_env)
    subprocess.run(['git', 'add', '-f', '--', *names], cwd=ROOT, env=index_env, check=True)
    tree = git('write-tree', env=index_env)
    archive = subprocess.Popen(['git', 'archive', '--format=tar', tree], cwd=ROOT, stdout=subprocess.PIPE)
    with archive.stdout:
        unpack = subprocess.run(['tar', '-xf', '-', '-C', str(export)], stdin=archive.stdout)
    if archive.wait() or unpack.returncode: raise RuntimeError('Git tree export failed')
    if before != {name: identity(export/name) for name in names}:
        raise ValueError('tree export differs from selected source')
    profile = export/'tests/intel_toolchain.sh'; env = profile_env(profile, temporary)
    out = work/'outputs'; out.mkdir(); official = export/BUNDLE
    py = sys.executable; commands = {}
    commands['cohorts']=run([py,'tools/cp02_mp10_failure_cohorts.py','--results',str(export/PARENT/'evaluation/results'),
                            '--inventory',str(official/'inputs/reference_inventory.json'),'--output',str(out/'cohorts')],export,env,logs,'cohorts')
    commands['analysis']=run([py,'tools/cp02_mp10_process.py','--packed',str(official/'native/packed'),
        '--points',str(official/'cohorts/selected_points.csv'),'--schema',str(official/'native/schema/schema.json'),
        '--proof',str(official/'native/proof/comparability.json'),'--output',str(out/'analysis')],export,env,logs,'analysis')
    commands['figures']=run([py,'tools/plot_cp02_mp10_process.py','--analysis',str(official/'analysis'),
                            '--output',str(out/'figures')],export,env,logs,'figures')
    commands['science']=run([py,str(official/'science/summarize.py'),'--output',str(out/'science')],export,env,logs,'science')
    commands['surface']=run([py,str(worker),'--surface-worker',str(export),str(out/'surface')],export,env,logs,'surface')
    commands['tests']=run([py,'-m','pytest','-q',*TESTS],export,env,logs,'pytest')
    match=re.search(r'(\d+) passed',commands['tests']['tail'])
    if not match or int(match.group(1))!=15:raise ValueError('expected 15 focused tests')
    checks={}
    for name in ('cohorts','analysis','figures'):
        names_to_compare=list(json.loads((official/name/'receipt.json').read_text())['outputs'])
        checks[name]=compare(official/name,out/name,names_to_compare)
    checks['science']=compare(official/'science/results',out/'science',['target_operator_summary.csv','k2_public_ledger.csv'])
    checks['surface']=compare(official/'surface/results',out/'surface',['point_components.csv'])
    if (any(identity(ROOT/name) != value for name, value in before.items())
            or any(identity(p) != value for p, value in external.items())
            or identity(replay_script) != replay_identity or identity(worker) != replay_identity
            or (identity(index_path) if index_path.exists() else None) != index_before):
        raise ValueError('source or external input changed during replay')
    result = {'status': 'PASS', 'base_commit': head, 'tree_sha1': tree, 'git_index': 'private temporary index',
              'overlay_files': before, 'export_path': str(export), 'scratch': str(work),
              'external_pinned_inputs': external, 'replay_script': replay_identity,
              'shared_index_unchanged': True, 'profile': identity(profile), 'commands': commands,
              'byte_identical_outputs': checks, 'focused_tests_passed': 15,
              'scope': 'Sealed lossless compact/wrapper analysis, cohort and surface-array recalculation, figures and 15 focused tests. Full raw extraction, Intel builds and WRF reintegration are not replayed. Parent histories remain external; the source font and pinned Intel profile remain environment dependencies. Path-bearing receipts are excluded from byte comparisons.'}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x') as stream: json.dump(result, stream, indent=2); stream.write('\n')
    print(json.dumps({'status': 'PASS', 'tree_sha1': tree, 'overlays': len(names),
                      'compared_outputs': sum(map(len, checks.values())), 'tests': 15, 'scratch': str(work)}))


if __name__ == '__main__': main()
