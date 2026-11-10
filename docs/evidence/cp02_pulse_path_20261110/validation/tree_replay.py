#!/usr/bin/env python3
"""Replay the final task tree in scratch; never modify the shared Git index."""
import argparse
import hashlib
import importlib.util
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
BUNDLE = Path('docs/evidence/cp02_pulse_path_20261110')
OLD = Path('docs/evidence/cp02_low_threshold_process_20261110')
BASE = '6218dc33cced6a6b41d71a99244d300fb44972cd'
REPORT = Path('docs/CP02_PULSE_PATH_AND_SUBSTEPS_20261110.md')
TESTS = ['tests/test_cp02_pulse_path.py', str(BUNDLE/'evaluation/test_mp10_evaluation.py')]
SOURCES = ['tools/cp02_pulse_path.py', 'tools/plot_cp02_pulse_path.py', *TESTS,
           'README.md', 'docs/CURRENT_RESEARCH_STATUS.md', str(REPORT)]
ANALYSIS = ['calls.csv.gz', 'surface_calls.csv', 'surface_windows.csv', 'window_levels.csv', 'summary.json']
NATIVE = ['core_recount.csv.gz', 'core_qg_partition.csv', 'sediment_substeps.csv', 'sediment_faces_summary.csv']
SCORES = ['categorical_scores.csv', 'continuous_scores.csv', 'admission_constraints.csv',
          'observation_transitions.csv', 'observed_forecast_bands.csv', 'weak_detection.csv',
          'FULL_SCORES.md', 'verdict.json']
EXTERNAL_OLD = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_low_threshold_process_20261110/Cloud-BAL/docs/evidence/cp02_low_threshold_process_20261110')
EXTERNAL = [EXTERNAL_OLD/'native/schema/schema.json', EXTERNAL_OLD/'cohorts/results/selected_points.csv',
            Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/Cloud-BAL/scratch/cp02_six_hour_20260914/reference/inventory.json'),
            Path('/var/tmp/firsthour-runtime-plan-20261030/experiment/build_FIX/module_mp_kdm6.f90'),
            Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_sedimentation_conservation_20261109/Cloud-BAL/docs/evidence/cp02_sedimentation_conservation_20261109/native/source/module_mp_kdm6_FIX.f90'),
            Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_ice_velocity_20261109/Cloud-BAL/docs/evidence/cp02_first_ice_velocity_20261109/native/source/module_mp_kdm6_FIX_new.f90'),
            Path('/usr/share/fonts/truetype/nanum/NanumGothic.ttf')]


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


def score_worker(worker_root, results, output):
    spec = importlib.util.spec_from_file_location('pulse_evaluation', worker_root/BUNDLE/'evaluation/evaluate.py')
    e = importlib.util.module_from_spec(spec); spec.loader.exec_module(e)
    receipt = json.loads((results/'receipt.json').read_text())
    for hour in e.HOURS:
        path = results/f'hour_{hour}_arrays.npz'
        if path.is_symlink() or identity(path)['sha256'] != receipt['outputs'][path.name]:
            raise ValueError('frozen array differs: '+str(path))
    arrays = e.prior.read_arrays(results)
    cat, cont, gates, transitions, bands, weak = e.score(arrays)
    output.mkdir()
    for name, rows in zip(SCORES[:6], (cat, cont, gates, transitions, bands, weak)):
        e.prior.write_csv(output/name, rows)
    e.full_scores(output/'FULL_SCORES.md', cat, cont)
    verdict = {case: {'passed_constraints': sum(r['satisfied'] for r in gates if r['candidate'] == case),
                      'required_constraints': 26} for case in (e.NEW, e.ICE)}
    (output/'verdict.json').write_text(json.dumps(verdict, indent=2)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--scratch', type=Path)
    parser.add_argument('--go', action='store_true')
    parser.add_argument('--score-worker', nargs=3, metavar=('TREE', 'RESULTS', 'OUTPUT'))
    args = parser.parse_args()
    if args.score_worker:
        score_worker(*(Path(p) for p in args.score_worker)); return
    if not args.go or not args.output or not args.scratch:
        parser.error('replay requires explicit --go, --output and --scratch')
    if 'FINAL_FORECAST_RESULTS' in (ROOT/REPORT).read_text():
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
    out = work/'outputs'; out.mkdir(); official = export/BUNDLE; old = export/OLD
    py = sys.executable; commands = {}
    commands['analysis'] = run([py, 'tools/cp02_pulse_path.py', '--compact', str(old/'native/compact'),
        '--points', str(old/'cohorts/results/selected_points.csv'), '--schema', str(old/'native/schema/schema.json'),
        '--proof', str(old/'native/proof/comparability.json'), '--output', str(out/'analysis')], export, env, logs, 'analysis')
    commands['figures'] = run([py, 'tools/plot_cp02_pulse_path.py', '--output', str(out/'figures')], export, env, logs, 'figures')
    native = out/'native'; native.mkdir()
    for name in ('recount.py', 'summarize_core.py', 'recount_sediment.py', 'summarize_faces.py',
                 'read_frames_with_constants.py', 'extract_receipt.json', 'FIX_selected.bin.gz',
                 'CONSERVATIVE_selected.bin.gz', 'ICE_FIXED_selected.bin.gz'):
        shutil.copyfile(official/'native'/name, native/name)
    for name in ('recount.py', 'summarize_core.py', 'recount_sediment.py', 'summarize_faces.py'):
        commands[name] = run([py, str(native/name)], export, env, logs, name)
    results = official/'evaluation/results'
    commands['score'] = run([py, str(worker), '--score-worker', str(export), str(results), str(out/'scores')], export, env, logs, 'score')
    for name, script in (('evaluation_figures', 'plot.py'), ('hourly_maps', 'plot_hourly_maps.py')):
        commands[name] = run([py, str(official/'evaluation'/script), '--results', str(results),
                              '--output', str(out/name)], export, env, logs, name)
    commands['tests'] = run([py, '-m', 'pytest', '-q', *TESTS], export, env, logs, 'pytest')
    match = re.search(r'(\d+) passed', commands['tests']['tail'])
    if not match or int(match.group(1)) != 11: raise ValueError('expected 11 focused tests')
    figure_names = list(json.loads((official/'figures/receipt.json').read_text())['outputs'])
    eval_names = list(json.loads((official/'evaluation/figures/receipt.json').read_text())['outputs'])
    map_names = list(json.loads((official/'evaluation/hourly_maps/receipt.json').read_text())['outputs'])
    if (len(figure_names), len(eval_names), len(map_names)) != (10, 3, 7):
        raise ValueError('figure/data output inventory changed')
    checks = {'analysis': compare(official/'analysis', out/'analysis', ANALYSIS),
              'figures': compare(official/'figures', out/'figures', figure_names),
              'native': compare(official/'native', native, NATIVE),
              'scores': compare(results, out/'scores', SCORES),
              'evaluation_figures': compare(official/'evaluation/figures', out/'evaluation_figures', eval_names),
              'hourly_maps': compare(official/'evaluation/hourly_maps', out/'hourly_maps', map_names)}
    if (any(identity(ROOT/name) != value for name, value in before.items())
            or any(identity(p) != value for p, value in external.items())
            or identity(replay_script) != replay_identity or identity(worker) != replay_identity
            or (identity(index_path) if index_path.exists() else None) != index_before):
        raise ValueError('source or external input changed during replay')
    result = {'status': 'PASS', 'base_commit': head, 'tree_sha1': tree, 'git_index': 'private temporary index',
              'overlay_files': before, 'export_path': str(export), 'scratch': str(work),
              'external_pinned_inputs': external, 'replay_script': replay_identity,
              'shared_index_unchanged': True, 'profile': identity(profile), 'commands': commands,
              'byte_identical_outputs': checks, 'focused_tests_passed': 11,
              'scope': 'Selected native gzip recount, compact analyzer, figures and frozen-array score/plots only. Full raw extraction and WRF forecasts were not replayed. Machine-specific prior schema, selector, inventory, source parents, font and Intel profile remain external dependencies; portability beyond this machine is not established. Path-bearing receipts are excluded from byte comparisons.'}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x') as stream: json.dump(result, stream, indent=2); stream.write('\n')
    print(json.dumps({'status': 'PASS', 'tree_sha1': tree, 'overlays': len(names),
                      'compared_outputs': sum(map(len, checks.values())), 'tests': 11, 'scratch': str(work)}))


if __name__ == '__main__': main()
