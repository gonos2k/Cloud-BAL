#!/usr/bin/env python3
"""Snapshot an isolated Git tree and reproduce the portable low-threshold outputs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[4]
BUNDLE = Path('docs/evidence/cp02_low_threshold_process_20261110')
BASE = '95a433ac5925ecd283bfdb8d2a02df257441821c'
TESTS = ['tests/test_cp02_low_threshold_cohorts.py', 'tests/test_cp02_low_threshold_process.py',
         'tests/test_cp02_low_threshold_native_source.py', str(BUNDLE/'science/test_column_audit.py')]
SOURCES = ['tools/cp02_low_threshold_cohorts.py', 'tools/cp02_low_threshold_process.py',
           'tools/plot_cp02_low_threshold_process.py', *TESTS, 'README.md',
           'docs/CURRENT_RESEARCH_STATUS.md', 'docs/CP02_LOW_THRESHOLD_PROCESS_20261110.md',
           str(BUNDLE/'review/launch_go.json'), str(BUNDLE/'validation/tree_replay.py')]
COHORT_NAMES = ['classification.csv','selected_points.csv','lead_bins.csv','weak_detection.csv','summary.json']
ANALYSIS_NAMES = ['paired_process_ledger.csv','point_surface_hourly.csv','point_surface_traces.npz',
                  'public_number_ledger.csv','internal_number_stage_sums.csv','summary.json']
INVENTORY = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/Cloud-BAL/scratch/cp02_six_hour_20260914/reference/inventory.json')
PARENT_INPUTS = [Path('/var/tmp/firsthour-runtime-plan-20261030/experiment/build_FIX/module_mp_kdm6.f90'),
    Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_sedimentation_conservation_20261109/Cloud-BAL/docs/evidence/cp02_sedimentation_conservation_20261109/native/source/module_mp_kdm6_FIX.f90'),
    Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_ice_velocity_20261109/Cloud-BAL/docs/evidence/cp02_first_ice_velocity_20261109/native/source/module_mp_kdm6_FIX_new.f90')]


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def identity(path):
    p=Path(path)
    return {'sha256':sha(p),'size_bytes':p.stat().st_size}


def git(*args, env=None):
    return subprocess.check_output(['git',*args], cwd=ROOT, env=env, text=True).strip()


def overlays():
    names = set(SOURCES)
    for sub in ('cohorts','analysis','native','science','figures'):
        for p in (ROOT/BUNDLE/sub).rglob('*'):
            if p.is_file() and not p.is_symlink() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.lock'):
                names.add(str(p.relative_to(ROOT)))
    for name in names:
        if not (ROOT/name).is_file() or (ROOT/name).is_symlink():
            raise ValueError('missing or unsafe overlay: '+name)
    return sorted(names)


def profile_env(profile, temporary):
    result=subprocess.run(['bash','-c','set -e; source "$1"; env -0','profile',str(profile)],
                          stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True)
    env={k.decode():v.decode(errors='surrogateescape') for item in result.stdout.split(b'\0') if item for k,v in [item.split(b'=',1)]}
    for key in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMEXPR_NUM_THREADS','BLIS_NUM_THREADS'):
        env[key]='1'
    mpl=temporary/'mplconfig'; mpl.mkdir()
    env.update(PYTHONDONTWRITEBYTECODE='1', MPLCONFIGDIR=str(mpl), TMPDIR=str(temporary))
    return env


def run_cmd(cmd, cwd, env, logs, name):
    start=time.monotonic()
    proc=subprocess.run(cmd,cwd=cwd,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    path=logs/(name+'.log'); path.write_text(proc.stdout)
    if proc.returncode:
        raise RuntimeError(f'{name} failed (log {path}):\n{proc.stdout[-5000:]}')
    return {'argv':cmd,'exit_code':proc.returncode,'elapsed_seconds':round(time.monotonic()-start,3),
            'log_path':str(path),'log_sha256':sha(path),'output':proc.stdout[-3000:]}


def compare(original, replay, names):
    records={}
    for name in sorted(names):
        a,b=identity(original/name),identity(replay/name)
        if a!=b: raise ValueError(f'byte mismatch for {name}')
        records[name]=a
    return records


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--scratch',type=Path,required=True)
    args=ap.parse_args()
    output=args.output.resolve()
    if os.path.lexists(output): raise FileExistsError(output)
    args.scratch.mkdir(parents=True,exist_ok=True)
    work=Path(tempfile.mkdtemp(prefix='low-tree-replay-',dir=args.scratch.resolve()))
    tree_export=work/'tree';tree_export.mkdir()
    temporary=work/'tmp';temporary.mkdir()
    logs=work/'logs';logs.mkdir()
    head=git('rev-parse','HEAD')
    if head != BASE: raise ValueError('base HEAD changed: '+head)
    names=overlays()
    source_before={name:identity(ROOT/name) for name in names}
    external={str(p):identity(p) for p in [INVENTORY,*PARENT_INPUTS]}
    index_env=os.environ.copy();index_env['GIT_INDEX_FILE']=str(work/'isolated.index')
    git('read-tree',head,env=index_env)
    subprocess.run(['git','add','-f','--',*names],cwd=ROOT,env=index_env,check=True)
    tree=git('write-tree',env=index_env)
    archive=subprocess.Popen(['git','archive','--format=tar',tree],cwd=ROOT,stdout=subprocess.PIPE)
    with archive.stdout:
        extraction=subprocess.run(['tar','-xf','-','-C',str(tree_export)],stdin=archive.stdout)
    if archive.wait() or extraction.returncode: raise RuntimeError('tree archive extraction failed')
    exported={name:identity(tree_export/name) for name in names}
    if source_before!=exported or any(identity(ROOT/n)!=v for n,v in source_before.items()):
        raise ValueError('overlay changed during tree snapshot/export')
    profile=tree_export/'tests/intel_toolchain.sh'
    env=profile_env(profile,temporary)
    out=work/'outputs';out.mkdir()
    cohort=out/'cohort'
    analysis=out/'analysis'
    figures=out/'figures'
    py=sys.executable
    commands={}
    commands['cohort']=run_cmd([py,'tools/cp02_low_threshold_cohorts.py','--results',
        'docs/evidence/cp02_first_ice_velocity_20261109/evaluation/results','--inventory',str(INVENTORY),'--output',str(cohort)],tree_export,env,logs,'cohort')
    commands['analysis']=run_cmd([py,'tools/cp02_low_threshold_process.py','--compact',str(BUNDLE/'native/compact'),
        '--points',str(BUNDLE/'cohorts/results/selected_points.csv'),'--schema',str(BUNDLE/'native/schema/schema.json'),
        '--proof',str(BUNDLE/'native/proof/comparability.json'),'--output',str(analysis)],tree_export,env,logs,'analysis')
    commands['figures']=run_cmd([py,'tools/plot_cp02_low_threshold_process.py','--output',str(figures)],tree_export,env,logs,'figures')
    commands['provenance']=run_cmd([py,str(BUNDLE/'native/proof/verify_provenance.py')],tree_export,env,logs,'provenance')
    commands['tests']=run_cmd([py,'-m','pytest','-q',*TESTS],tree_export,env,logs,'pytest')
    passed=re.search(r'(\d+) passed',commands['tests']['output'])
    if not passed or int(passed.group(1))!=15: raise ValueError('expected exactly 15 focused tests')
    official=tree_export/BUNDLE
    expected_png=json.loads((official/'figures/receipt.json').read_text())['outputs']
    if len(expected_png)!=27: raise ValueError('expected 27 PNG figures')
    comparisons={'cohort':compare(official/'cohorts/results',cohort,COHORT_NAMES),
                 'analysis':compare(official/'analysis',analysis,ANALYSIS_NAMES),
                 'figures':compare(official/'figures',figures,expected_png)}
    for name,expected in expected_png.items():
        if comparisons['figures'][name]['sha256']!=expected: raise ValueError('figure receipt mismatch')
    provenance=json.loads((official/'native/proof/provenance_verification.json').read_text())
    if provenance['status']!='PASS' or provenance['sample_steps']!=[1,2,3] or provenance['arms']!=3:
        raise ValueError('native sample provenance did not pass')
    if any(identity(ROOT/n)!=v for n,v in source_before.items()) or any(identity(p)!=v for p,v in external.items()):
        raise ValueError('inputs changed during replay')
    result={'status':'PASS','base_commit':head,'tree_sha1':tree,'git_index':'private temporary index; shared index untouched',
            'overlay_files':source_before,'export_path':str(tree_export),'scratch':str(work),
            'external_pinned_inputs':external,'profile':identity(profile),'commands':commands,
            'byte_identical_outputs':comparisons,'focused_tests_passed':15,'native_sample':provenance,
            'scope':'Exact Git tree = recorded base plus explicit overlay; six cohort/analysis inputs and compact native captures are tree-contained. Figure/gallery links are outside this replay. Full raw streams and domain forecast runs are not replayed. Existing tests and compiler profile depend on machine-specific pinned external source parents, crop inventory and Intel installation; portability beyond this machine is not established. Receipts containing absolute replay paths are intentionally excluded from byte comparisons.'}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x') as f: json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps({'status':'PASS','tree_sha1':tree,'overlay_files':len(names),
                      'cohort_outputs':len(COHORT_NAMES),'analysis_outputs':len(ANALYSIS_NAMES),
                      'figure_outputs':len(expected_png),'tests':15,'scratch':str(work)},indent=2))


if __name__=='__main__': main()
