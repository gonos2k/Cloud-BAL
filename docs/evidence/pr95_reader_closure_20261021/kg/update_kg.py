#!/usr/bin/env python3
"""Guarded selected-source PR95 Graphify/KG overlay; never copies maintained source."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, re, shutil, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[4]
ROOT = SOURCE.parents[2]
MAINT = ROOT / 'Cloud-BAL'
OUT = MAINT / 'scratch/pr95_reader_closure_20261021/kg'
BASE = '7c2d1e295c1930d64a98e9602c36289aabb1d440'
PRIOR = MAINT / 'scratch/pr94_physics_20261021/kg/kg_receipt.json'
PRIOR_SHA = '7c6b48b7a4841f0eaf9bfb168b46ea22d3082b935b6c4a3f3d34e7734bd70f3c'
PRIOR_HELPER = SOURCE / 'docs/evidence/pr94_physics_20261021/kg/update_kg.py'
PRIOR_HELPER_SHA = 'a17d07a7554df1e337d5123d6dd37c09547fa9d28ec42f2ff47fbe66017a23d0'
GUARD = Path('/var/tmp/pr91_refresh_kg_host_store_20261020.py')
GUARD_SHA = 'a2b4de3e7941e3d0cf2cf8d60ee3956338fe2471df960c1f93c04bcf554ea9cf'
PINNED_PYTHON = Path('/home/korea_keun/.local/share/uv/tools/graphifyy/bin/python3')
PINNED_BIN = PINNED_PYTHON.parent
SNAPSHOT = '2026-10-21-pr95-reader-closure'
GRAPH_SUFFIXES = {'.md', '.py', '.f', '.for', '.f90', '.f95', '.f03', '.f08', '.sh'}
WIKI_FILES = ('graph-report.md', 'graph-report-klaps50.md', 'graph-report-cloud-bal.md', 'index.md', 'log.md')
GRAPH_PINS = {
    'KLAPS50': '5ce523177982640dd3f5428e51af942c2129e503620d33e07d19cdf94ee91b0a',
    'Cloud-BAL': '188873c7826d1b106f9b23e0ba820f9043fc1f15263537a538bb3c54ba7e8f38',
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot_identity(snapshot: dict) -> dict[str, int | str]:
    digest = hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {'entry_count': len(snapshot), 'sha256': digest}


def immutable_pin_snapshot(receipt: dict) -> dict[str, dict[str, str | None]]:
    result = {}
    pins = receipt.get('inherited_immutable_pins_after', {})
    require(len(pins) == 197, 'PR94 receipt must carry all 197 inherited immutable pins')
    for name, pin in pins.items():
        expected = pin['expected_sha256']
        path = Path(name)
        current = sha(path) if path.is_file() else None
        require(current == expected, f'inherited immutable pin changed: {path}')
        result[name] = {'expected_sha256': expected, 'current_sha256': current}
    return result


def normalize_index(data: bytes) -> bytes:
    start = data.find(b'## Graph snapshot')
    require(start >= 0, 'wiki index has no Graph snapshot section')
    end = data.find(b'\n## ', start + 3)
    if end < 0:
        end = len(data)
    data = data[:start] + b'<GRAPH_SNAPSHOT_SECTION>' + data[end:]
    rows = list(re.finditer(rb'(?m)^(date_modified:\s*)[^\r\n]+', data))
    require(len(rows) <= 1, 'wiki index has ambiguous date_modified fields')
    if rows:
        row = rows[0]
        data = data[:row.start()] + row.group(1) + b'<DATE_MODIFIED>' + data[row.end():]
    return data


def require(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


def load(name: str, path: Path, expected: str):
    require(sha(path) == expected, f'helper pin changed: {path}')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def load_previous_helpers():
    pr94 = load('pr95_pr94_helper', PRIOR_HELPER, PRIOR_HELPER_SHA)
    path = Path(pr94.PRIOR_HELPER)
    expected = pr94.PRIOR_HELPER_SHA
    protected = load('pr95_pr92_protected_helper', path, expected)
    require(callable(getattr(protected, 'protected_content', None)),
            f'pinned protected-content helper API missing: {path}')
    chain = {'path': str(path), 'sha256': sha(path), 'expected_sha256': expected}
    return pr94, protected, chain


def git(*args: str) -> str:
    return subprocess.check_output(['git', *args], cwd=SOURCE, text=True).strip()


def selected_path(path: str) -> bool:
    p = Path(path)
    if path.startswith('docs/evidence/'):
        return False
    if path.startswith(('tools/pr95_', 'tests/test_pr95_', 'tests/pr95_',
                        'tests/fixtures/pr95_', 'tests/run_pr95_')):
        return p.suffix.lower() in GRAPH_SUFFIXES
    if path in {'tools/pr86_compare_response.py', 'tools/pr94_cloud_response.py',
                'tools/pr94_longrun_audit.py', 'tools/pr94_water_budget.py', 'tests/test_pr86_compare_response.py',
                'tests/test_pr94_cloud_response.py', 'tests/test_pr94_longrun_audit.py'}:
        return True
    return (path.startswith('docs/PR95_') or path == 'docs/PR94_WATER_BUDGET_20261021.md') and p.suffix.lower() == '.md'


def file_inventory(root: Path) -> dict[str, str]:
    result = {}
    for base in ('src', 'tests', 'docs', 'tools', 'config'):
        folder = root / base
        if not folder.exists():
            continue
        for path in sorted(folder.rglob('*')):
            if path.is_symlink() or path.is_file():
                rel = path.relative_to(root).as_posix()
                if any(part in {'scratch', 'worktrees', '.git', 'graphify-out'} for part in Path(rel).parts):
                    continue
                result[rel] = 'SYMLINK:' + os.readlink(path) if path.is_symlink() else sha(path)
    return result


def preflight(commit: str, pr_url: str) -> dict:
    require(sys.executable == str(PINNED_PYTHON), f'run with pinned interpreter {PINNED_PYTHON}')
    import graphify
    require(Path(graphify.__file__).resolve().is_relative_to(PINNED_BIN.parent.resolve()),
            f'graphify imported outside pinned uv tool: {graphify.__file__}')
    version = subprocess.check_output([str(PINNED_PYTHON), '-m', 'graphify', '--version'], text=True).strip()
    match = re.search(r'(\d+)\.(\d+)\.(\d+)', version)
    require(match and tuple(map(int, match.groups())) >= (0, 8, 24), 'Graphify >= 0.8.24 required for Fortran')
    match_pr = re.fullmatch(r'https://github\.com/gonos2k/Cloud-BAL/pull/(\d+)', pr_url)
    require(match_pr is not None, 'expected actual Cloud-BAL pull request URL')
    require(git('rev-parse', '--show-toplevel') == str(SOURCE), 'source checkout root changed')
    require(git('rev-parse', 'HEAD') == commit, 'source HEAD differs from supplied final commit')
    require(not git('status', '--porcelain'), 'source must be clean at reviewed commit')
    require(git('merge-base', BASE, commit) == BASE, 'final source commit is not based on pinned PR95 base')
    require(sha(PRIOR) == PRIOR_SHA, 'PR94 KG receipt changed')
    prior = json.loads(PRIOR.read_text())
    require(prior['status'] == 'PASS' and prior['physical_approval'] == 'FAIL_OPEN', 'PR94 receipt state changed')
    require(prior['graphify_version'] == 'graphify 0.9.53', 'preceding Graphify version differs')
    require(prior['maintained_source_snapshot_after'] == {'entry_count': 627, 'sha256': '0d11babbb4095a849093a512e499648d5dc51717e83710e1edf206041bb4346f'},
            'PR94 maintained-source baseline changed')
    require(prior['immutable_pin_count_verified'] == 197, 'PR94 immutable pin count changed')
    guard = load('pr93_pr91_guard', GUARD, GUARD_SHA)
    require(sha(PRIOR_HELPER) == PRIOR_HELPER_SHA, 'PR94 guarded helper changed')
    prior_helper, protected_helper, protected_helper_pin = load_previous_helpers()
    maintained = guard.maintained_source_snapshot()
    maintained_identity = snapshot_identity(maintained)
    require(maintained_identity['entry_count'] > 0, 'maintained source inventory is empty')
    inherited_pins = immutable_pin_snapshot(prior)
    for label, directory in (('KLAPS50', ROOT), ('Cloud-BAL', MAINT)):
        require(sha(directory / 'graphify-out/graph.json') == GRAPH_PINS[label],
                f'{label} graph differs from the pinned current baseline')
        require(not (directory / 'graphify-out' / SNAPSHOT).exists(), f'{label} target snapshot already exists')
    wiki_baseline = {f'wiki/{name}': sha(ROOT / 'wiki' / name) for name in WIKI_FILES}
    protected = protected_helper.protected_content(guard)
    snapshot_baseline = {}
    for label, directory in (('KLAPS50', ROOT), ('Cloud-BAL', MAINT)):
        for folder in sorted((directory / 'graphify-out').iterdir()):
            if folder.is_dir() and re.match(r'^2026-\d\d-\d\d', folder.name):
                snapshot_baseline[str(folder)] = {
                    path.name: {'sha256': sha(path)} for path in sorted(folder.iterdir()) if path.is_file()}
    names = git('diff', '--name-only', '--diff-filter=ACMRT', BASE, commit).splitlines()
    require(names, 'no PR95 commit delta from base')
    items = []
    for relative in names:
        path = SOURCE / relative
        require(path.is_file() and not path.is_symlink(), f'unsupported or missing committed path: {relative}')
        before = subprocess.run(['git', 'show', f'{BASE}:{relative}'], cwd=SOURCE,
                                capture_output=True, check=False)
        items.append({'path': relative, 'sha256': sha(path),
                      'base_sha256': hashlib.sha256(before.stdout).hexdigest() if before.returncode == 0 else None,
                      'maintained_before_sha256': sha(MAINT / relative) if (MAINT / relative).is_file() else None,
                      'graphify_extraction': 'SELECTED' if selected_path(relative) else 'HASH_ONLY'})
    graph_items = [row for row in items if selected_path(row['path'])]
    require(graph_items, 'no reviewed PR95 source/docs selected for graph extraction')
    allowed_roots = ('docs/PR95_', 'docs/PR94_WATER_BUDGET_20261021.md', 'tools/pr95_', 'tests/test_pr95_', 'tests/pr95_',
                     'tests/fixtures/pr95_', 'tests/run_pr95_')
    allowed_exact = {'tools/pr86_compare_response.py', 'tools/pr94_cloud_response.py',
                     'tools/pr94_longrun_audit.py', 'tools/pr94_water_budget.py', 'tests/test_pr86_compare_response.py',
                     'tests/test_pr94_cloud_response.py', 'tests/test_pr94_longrun_audit.py'}
    unexpected = [row['path'] for row in graph_items
                  if not row['path'].startswith(allowed_roots) and row['path'] not in allowed_exact]
    require(not unexpected, f'graph allowlist mismatch: {unexpected}')
    pr_number = match_pr.group(1)
    gh = json.loads(subprocess.check_output(['gh', 'api', f'repos/gonos2k/Cloud-BAL/pulls/{pr_number}'], text=True))
    require(gh['html_url'] == pr_url and gh['state'] == 'open' and gh['head']['sha'] == commit and gh['base']['ref'] == 'main',
            'actual GitHub PR does not match clean frozen source commit/base')
    report_rows = (ROOT / 'wiki/graph-report.md').read_text().splitlines()
    require(all(sum(line.startswith(f'| {label} |') for line in report_rows) == 1
                for label in ('KLAPS50', 'Cloud-BAL')), 'multi-corpus wiki rows missing/duplicated')
    return {'source_commit': commit, 'base': BASE, 'pr': pr_url, 'selected_paths': items,
            'graph_source_paths': [row['path'] for row in graph_items], 'prior_receipt_sha256': PRIOR_SHA,
            'maintained_source_snapshot_before': maintained_identity,
            'inherited_immutable_pins': inherited_pins,
            'wiki_baseline': wiki_baseline, 'protected_content_sha256': protected,
            'protected_content_helper': protected_helper_pin,
            'dated_snapshot_baseline': snapshot_baseline,
            'graphify_version': version, 'graphify_interpreter': str(PINNED_PYTHON),
            'prior_receipt_snapshot': prior['new_snapshot'], 'new_snapshot': SNAPSHOT,
            'baseline_graphs': {k: {'sha256': GRAPH_PINS[k]} for k in ('KLAPS50','Cloud-BAL')},
            'immutable_pin_count_verified': len(inherited_pins)}


def apply(plan: dict) -> None:
    """Apply only after final review/runtime gates; all writes have receipt-bound backups."""
    require(not OUT.exists(), 'refuse existing PR95 output directory')
    guard = load('pr93_apply_guard', GUARD, GUARD_SHA)
    prior_helper, protected_helper, protected_helper_pin = load_previous_helpers()
    require(protected_helper_pin == plan['protected_content_helper'],
            'pinned protected-content helper chain changed after preflight')
    require(protected_helper.protected_content(guard) == plan['protected_content_sha256'],
            'protected wiki content changed after preflight')
    maintained = guard.maintained_source_snapshot()
    require(snapshot_identity(maintained) == plan['maintained_source_snapshot_before'],
            'maintained source tree changed after preflight')
    require({f'wiki/{name}': sha(ROOT / 'wiki' / name) for name in WIKI_FILES} == plan['wiki_baseline'],
            'derived wiki changed after preflight')
    for label, directory in (('KLAPS50', ROOT), ('Cloud-BAL', MAINT)):
        require(sha(directory / 'graphify-out/graph.json') == GRAPH_PINS[label],
                f'{label} graph changed after preflight')
    for folder_name, members in plan['dated_snapshot_baseline'].items():
        folder = Path(folder_name)
        require({path.name for path in folder.iterdir() if path.is_file()} == set(members),
                f'dated snapshot membership changed: {folder}')
        require(all(sha(folder / name) == row['sha256'] for name, row in members.items()),
                f'dated snapshot content changed: {folder}')
    prior = json.loads(PRIOR.read_text())
    require(immutable_pin_snapshot(prior) == plan['inherited_immutable_pins'],
            'inherited immutable pins changed after preflight')
    from_dir = MAINT / 'scratch/pr59_publish_kg_20261002'
    updater_path = from_dir / 'update.py'
    auditor_path = MAINT / 'scratch/pr59_team_audit_20261006/update_kg.py'
    updater_sha = '7c626b398f44a4013a607e2a5ae932528d2caaf41e37a479366aa80e0b146aa0'
    auditor_sha = 'bfe6242618e8ca1b60ab1304221d1fd215476d7f23281b69e48963611c0b76e1'
    updater = load('pr93_selected_updater', updater_path, updater_sha)
    auditor = load('pr93_graph_auditor', auditor_path, auditor_sha)
    graph_items = [row for row in plan['selected_paths'] if row['graphify_extraction'] == 'SELECTED']
    updater.SOURCE, updater.OUT, updater.BASE_COMMIT = SOURCE, OUT, BASE
    updater.PR, updater.PATHS = plan['pr'], tuple(row['path'] for row in graph_items)
    auditor.ROOT, auditor.MAINTAINED, auditor.OUT = ROOT, MAINT, OUT
    auditor.PATHS = updater.PATHS
    OUT.mkdir(parents=True)
    protected = plan['protected_content_sha256']
    original_graphs = {label: json.loads((directory / 'graphify-out/graph.json').read_text())
                       for label,directory in (('KLAPS50',ROOT),('Cloud-BAL',MAINT))}
    backups = {}
    for label,directory in (('KLAPS50',ROOT),('Cloud-BAL',MAINT)):
        for name in updater.GRAPH_FILES:
            path = directory / 'graphify-out' / name
            if path.exists():
                dst=OUT/'backups'/label/name; dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(path,dst); backups[path]=dst
        for folder_name in plan['dated_snapshot_baseline']:
            folder=Path(folder_name)
            if folder.parent == directory/'graphify-out':
                for path in folder.iterdir():
                    if path.is_file():
                        dst=OUT/'backups'/label/folder.name/path.name; dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(path,dst); backups[path]=dst
    for name in updater.WIKI_FILES:
        path=ROOT/'wiki'/name; dst=OUT/'backups/wiki'/name; dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(path,dst); backups[path]=dst
    automatic={}
    for folder_name in plan['dated_snapshot_baseline']:
        folder=Path(folder_name)
        automatic[str(folder)]={name:{'backup':str(OUT/'backups'/folder.parent.parent.name/folder.name/name),
                                      'sha256':row['sha256']}
                                for name,row in plan['dated_snapshot_baseline'][folder_name].items()}
    env=os.environ.copy(); env['PATH']=str(PINNED_BIN)+os.pathsep+env.get('PATH','')
    old_path=os.environ.get('PATH',''); os.environ['PATH']=env['PATH']
    records={}
    try:
        for label,directory,prefix in (('KLAPS50',ROOT,'Cloud-BAL'),('Cloud-BAL',MAINT,'')):
            records[label]=updater.update_graph(label,directory,prefix,graph_items)
            extraction=json.loads((OUT/f'{label.lower().replace("-","_")}_extraction.json').read_text())
            auditor.record_snapshot(label,directory,original_graphs[label],extraction)
        private=auditor.verify_private_profile(original_graphs)
        guard.restore_automatic_snapshots(automatic)
        limits=('Separate KLAPS50 and Cloud-BAL snapshots extract allowlisted PR95 docs, tools, and tests; evidence payloads are hash-bound only. '
                'Cross-file Fortran CALL extraction is partial. Graph freshness is navigation evidence, not runtime/scientific approval.')
        for label,directory in (('KLAPS50',ROOT),('Cloud-BAL',MAINT)):
            report=directory/'graphify-out/GRAPH_REPORT.md'; old=report.read_text()
            section=f'## Graph Freshness\n\n- PR95 source `{plan["source_commit"]}` against `{BASE}`; {len(graph_items)} selected paths.\n- {limits}\n'
            new,count=re.subn(r'## Graph Freshness\n.*?(?=\n## |\Z)',section,old,flags=re.S)
            require(count==1,'derived graph freshness section missing')
            report.write_text(new)
            snapshot=directory/'graphify-out'/SNAPSHOT; snapshot.mkdir()
            for name in ('graph.json','GRAPH_REPORT.md','manifest.json'): shutil.copy2(directory/'graphify-out'/name,snapshot/name)
            mirror='graph-report-klaps50.md' if label=='KLAPS50' else 'graph-report-cloud-bal.md'
            shutil.copy2(report,ROOT/'wiki'/mirror)
            records[label]['snapshot']=SNAPSHOT; records[label]['previous_graph_sha256']=GRAPH_PINS[label]
        idx=ROOT/'wiki/graph-report.md'; lines=idx.read_text().splitlines()
        for n,line in enumerate(lines):
            for label,r in records.items():
                if line.startswith(f'| {label} |'):
                    folder='.' if label=='KLAPS50' else 'Cloud-BAL/'; mirror='graph-report-klaps50' if label=='KLAPS50' else 'graph-report-cloud-bal'
                    lines[n]=f'| {label} | `{folder}` | {SNAPSHOT} (PR95 reader closure) | {r["nodes"]} | {r["edges"]} | {r["communities"]} | [[{mirror}]] |'
        idx.write_text('\n'.join(lines)+'\n')
        page=ROOT/'wiki/index.md'; original=page.read_bytes(); start=original.index(b'## Graph snapshot'); end=original.find(b'\n## ',start+3); end=len(original) if end<0 else end
        section='## Graph snapshot\n\n'+'\n'.join(f'- {label}: {SNAPSHOT}; {r["nodes"]} nodes / {r["edges"]} edges / {r["communities"]} communities.' for label,r in records.items())+'\n- Separate corpus reports retain extraction limits; graph freshness is not scientific validation.\n'
        updated = original[:start]+section.encode()+original[end:]
        updated, date_count = re.subn(rb'(?m)^(date_modified:\s*)[^\r\n]+', rb'\g<1>2026-10-21', updated, count=1)
        require(date_count <= 1, 'wiki index has ambiguous date_modified fields')
        require(normalize_index(original) == normalize_index(updated),
                'wiki index edit escaped Graph snapshot/date_modified allowance')
        page.write_bytes(updated)
        with (ROOT/'wiki/log.md').open('a') as log:
            log.write(f'\n## [2026-10-21] kg-update | PR95 reader closure selected overlay\n- Source `{plan["source_commit"]}` against `{BASE}`; PR {plan["pr"]}.\n')
            for label,r in records.items(): log.write(f'- {label}: {SNAPSHOT}; {r["nodes"]} nodes / {r["edges"]} edges / {r["communities"]} communities; delta nodes={r["delta_nodes"]}, edges={r["delta_edges"]}.\n')
            log.write('- PR95 reader-closure changes and their focused reader/longrun audit evidence are bound to the recorded source commit; selected evidence payloads are hash-bound only.\n')
            log.write(f'- {limits} Physical approval remains FAIL_OPEN. Prior PR94 KG receipt SHA-256 `{PRIOR_SHA}`.\n')
        guard.restore_automatic_snapshots(automatic)
        require(protected_helper.protected_content(guard)==protected,'protected wiki content changed')
        maintained_after = snapshot_identity(guard.maintained_source_snapshot())
        require(maintained_after == plan['maintained_source_snapshot_before'],
                'maintained source inventory changed during graph/wiki update')
        inherited_pins_after = immutable_pin_snapshot(prior)
        require(inherited_pins_after == plan['inherited_immutable_pins'],
                'inherited immutable pins changed during graph/wiki update')
        receipt={'schema':'pr95_reader_closure_selected_source_graphify_kg_v1','status':'PASS',**plan,
                 'recorded_utc':datetime.now(timezone.utc).isoformat(),'corpora':records,
                 'private_profile_preservation':private,'physical_approval':'FAIL_OPEN','limitations':limits,
                 'helper_sha256':sha(Path(__file__)),'prior_receipt_sha256':PRIOR_SHA,
                 'maintained_source_snapshot_after': maintained_after,
                 'maintained_source_snapshot_verified_pre_post_equal': True,
                 'inherited_immutable_pins_after': inherited_pins_after,
                 'wiki_sha256':{f'wiki/{n}':sha(ROOT/'wiki'/n) for n in WIKI_FILES}}
        (OUT/'kg_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    except BaseException:
        for path,dst in backups.items():
            if dst.exists(): shutil.copy2(dst,path)
        try:
            guard.restore_automatic_snapshots(automatic)
        except BaseException:
            pass
        for directory in (ROOT,MAINT):
            snap=directory/'graphify-out'/SNAPSHOT
            if snap.exists(): shutil.rmtree(snap)
        raise
    finally:
        os.environ['PATH']=old_path


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit',required=True)
    parser.add_argument('--pr-url',required=True)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check-only',action='store_true')
    mode.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    plan=preflight(args.commit,args.pr_url)
    if args.check_only:
        print(json.dumps({'status':'CHECK_ONLY_NO_WRITES',**plan},indent=2)); return
    apply(plan)

if __name__=='__main__': main()
